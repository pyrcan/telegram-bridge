"""Durable Telegram intake, with one ordered action worker and a live control lane.

Only the coordinator writes the inbox and update cursor. The poller cannot
acknowledge a batch to Telegram until that batch has been saved locally.
"""
from concurrent.futures import ThreadPoolExecutor
import queue
import json
import re
import threading
import time
from bridge_assistants import read_control


INBOX_PATH = 'telegram-inbox.json'
MAX_PENDING = 200


def contains_bot_key(text):
  return bool(re.search(r'[0-9]{5,}:[A-Za-z0-9_-]{20,150}', str(text)))


def admit_update(update):
  """Replace credential-bearing input with an ordered rejection, not an answer."""
  message = update.get('message')
  if not isinstance(message, dict) or not contains_bot_key(json.dumps(message, ensure_ascii=False)):
    return update
  chat, user = message.get('chat') or {}, message.get('from') or {}
  # Only typed Telegram identity metadata survives. No text, quoted reply,
  # caption, forwarded content or arbitrary provider field is persisted.
  minimal = {
    'chat': {'id': chat.get('id') if type(chat.get('id')) is int else 0,
             'type': chat.get('type') if chat.get('type') in ('private','group','supergroup','channel') else ''},
    'from': {'id': user.get('id') if type(user.get('id')) is int else 0},
  }
  for name in ('date','message_id'):
    if type(message.get(name)) is int: minimal[name] = message[name]
  return {'update_id': update['update_id'], 'message': minimal, '_bridge_rejected_input': True}


def responsive_control(update):
  callback = update.get('callback_query') or {}
  data = str(callback.get('data') or '')
  if read_control(data):
    return True
  if data.startswith(('chats:', 'chat:')):
    return True
  if data in ('cmd:model','cmd:settings','cmd:home') or data.startswith('mdl:p:'):
    return True
  text = str((update.get('message') or {}).get('text') or '')
  return text.split(maxsplit=1)[0].split('@')[0].lower() in {'/bridge', '/menu', '/help', '/status', '/model', '/assistants','/bots','/settings','/chats'} if text.strip() else False


def run_listener(bridge, runtime, context, username):
  """Run against the bridge's app-scoped operations; no owner credentials."""
  saved = bridge.storage_get(INBOX_PATH)
  pending = saved.get('updates', []) if isinstance(saved, dict) else []
  pending = [admit_update(u) for u in pending if isinstance(u, dict)]
  offset = max([int(runtime.get('offset') or 0)] + [int(u['update_id']) + 1 for u in pending])
  events = queue.Queue(maxsize=4)
  polls = queue.Queue(maxsize=1)
  stop = threading.Event()
  deadline = time.monotonic() + bridge.RUN_SECONDS
  maintained = time.monotonic()
  active = None
  acknowledgements = {}
  polling = False
  paused = False
  runtime_dir = context.get('runtime_dir')
  public_origin = str(context.get('public_origin') or '').rstrip('/')

  def persist():
    bridge.storage_put(INBOX_PATH, {'updates': pending})

  def poll():
    while not stop.is_set():
      try:
        cursor = polls.get(timeout=0.5)
      except queue.Empty:
        continue
      try:
        result = bridge.telegram('getUpdates', {
          'offset': cursor, 'timeout': 10, 'limit': 20,
          'allowed_updates': ['message', 'callback_query'],
        })
        events.put(('updates', result))
      except Exception as exc:
        events.put(('poll_error', exc))
        return

  def dispatch(update):
    settings = bridge.storage_get('settings.json')
    pairing = bridge.storage_get('pairing.json')
    if not isinstance(settings, dict) or settings.get('enabled') is False:
      return False
    # In-memory ownership only: never persist a scheduled ack as completed.
    callback = update.get('callback_query') or {}
    if (update['update_id'] in acknowledgements and isinstance(pairing, dict)
        and int((callback.get('from') or {}).get('id') or 0) == int(pairing.get('userId') or 0)
        and int(((callback.get('message') or {}).get('chat') or {}).get('id') or 0) == int(pairing.get('chatId') or 0)):
      update = {**update, '_callback_ack_delegated': True}
    bridge.dispatch_update(update, settings, pairing if isinstance(pairing, dict) else None, public_origin)
    return True

  def acknowledge(update):
    settings = bridge.storage_get('settings.json')
    pairing = bridge.storage_get('pairing.json')
    if isinstance(settings, dict) and settings.get('enabled') is not False:
      return bridge.acknowledge_received_callback(update, pairing if isinstance(pairing, dict) else None)
    return False

  def finish_item(update):
    with bridge.inbox_lease():
      pending.remove(update)
      persist()

  poller = threading.Thread(target=poll, name='telegram-intake', daemon=True)
  poller.start()
  executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='telegram-action')
  ack_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='telegram-ack')
  try:
    while True:
      if active is None and (paused or time.monotonic() >= deadline):
        break
      settings = bridge.storage_get('settings.json')
      paused = not isinstance(settings, dict) or settings.get('enabled') is False
      if paused and active is None:
        break
      pairing = bridge.storage_get('pairing.json')
      pairing = pairing if isinstance(pairing, dict) else None
      # Pure navigation may overtake a long AI turn; anything that changes
      # conversation/model/question state remains on the ordered action lane.
      # One bounded cosmetic lane, after durable intake. A slow acknowledgement
      # cannot delay the menu edit. Overflow keeps the ordinary inline ack path.
      pending_ids = {u['update_id'] for u in pending}
      for identity, future in list(acknowledgements.items()):
        if identity not in pending_ids and future.done():
          del acknowledgements[identity]
      if not paused:
        for update in pending:
          identity = update['update_id']
          if (update.get('callback_query') and not update.get('_callback_acknowledged')
              and identity not in acknowledgements and len(acknowledgements) < MAX_PENDING):
            acknowledgements[identity] = ack_executor.submit(acknowledge, update)
        for update in list(pending):
          if active is not None and update is active[0]:
            continue
          if responsive_control(update):
            if dispatch(update):
              finish_item(update)
      if active is None and pending and not paused:
        update = pending[0]
        future = executor.submit(dispatch, update)
        active = (update, future)
        future.add_done_callback(lambda f: events.put(('completed', f)))
      if not polling and not paused and len(pending) <= MAX_PENDING - 20 and time.monotonic() < deadline:
        polls.put(offset)
        polling = True
      if time.monotonic() - maintained >= bridge.MAINTENANCE_SECONDS:
        current = bridge.request_json(f'/api/apps/{bridge.APP_ID}/job-context')
        if current.get('runtime_dir') != runtime_dir:
          # Drain only the active action; the next accepted worker owns backlog.
          deadline = 0
        try:
          # Connection removal must refresh the native menu even during a long
          # owner reply; the last menu projection is not an authorization cache.
          if bridge.sync_bot_commands(pairing, runtime, username, public_origin):
            bridge.storage_put('bridge-runtime.json', runtime)
        except bridge.BridgeError:
          pass
        if active is None:
          try:
            with bridge.inbox_lease():
              if pairing:
                bridge.sync_question_state(public_origin)
          except bridge.BridgeError:
            pass
        bridge.set_status('paused' if paused else 'connected', 'Bridge paused' if paused else 'Connected',
                          'Messages are queued.' if paused else 'Listening while replies are generated.', botUsername=username)
        maintained = time.monotonic()
      # Poll completion and action completion both wake this coordinator.
      # No timer/poll interval sits between a finished reply and the next action.
      remaining = deadline - time.monotonic()
      timeout = min(bridge.MAINTENANCE_SECONDS, remaining) if remaining > 0 else bridge.MAINTENANCE_SECONDS
      try:
        kind, value = events.get(timeout=timeout)
      except queue.Empty:
        continue
      if kind == 'completed':
        update, future = active
        active = None
        if future.result():
          finish_item(update)
        else:
          paused = True
      elif kind == 'poll_error':
        raise value
      elif kind == 'updates':
        polling = False
        known = {int(u['update_id']) for u in pending}
        additions = [admit_update(u) for u in (value if isinstance(value, list) else [])
                     if isinstance(u, dict) and isinstance(u.get('update_id'), int)
                     and u['update_id'] >= offset and u['update_id'] not in known]
        with bridge.inbox_lease():
          pending.extend(additions)
          if additions:
            persist()  # Durable before advancing Telegram's acknowledgement cursor.
            offset = max(offset, max(u['update_id'] for u in additions) + 1)
            runtime.update({'offset': offset, 'updatedAt': bridge.now()})
            bridge.storage_put('bridge-runtime.json', runtime)
    return 0
  finally:
    stop.set()
    # Never abandon an accepted action on normal session renewal.
    executor.shutdown(wait=True)
    ack_executor.shutdown(wait=True)
