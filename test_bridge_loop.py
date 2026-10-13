"""Retained durable-inbox and ordered-work regressions; no network."""
import copy
import queue
import threading
import time
import unittest
from types import SimpleNamespace
from contextlib import nullcontext
from test_bridge import forbid_network

from bridge_loop import run_listener, INBOX_PATH, responsive_control


class ListenerTests(unittest.TestCase):
  def fixture(self, batches=(), dispatch=None, duration=0.12):
    updates = queue.Queue()
    for batch in batches:
      updates.put(batch)
    records = {'settings.json': {'enabled': True}, 'pairing.json': {'chatId': 99, 'userId': 99}}
    writes, handled, cursors, acks = [], [], [], []

    def put(path, value):
      records[path] = copy.deepcopy(value)
      writes.append((path, copy.deepcopy(value)))

    def telegram(method, params):
      self.assertEqual(method, 'getUpdates')
      cursors.append(params['offset'])
      try:
        return updates.get(timeout=0.02)
      except queue.Empty:
        return []

    def action(update, settings, pairing, origin):
      handled.append((update['update_id'], pairing))
      if dispatch:
        dispatch(update, records)

    def ack(update, pairing):
      if update.get('callback_query'):
        # The inbox must contain the message BEFORE any Telegram ack.
        self.assertTrue(any(path == INBOX_PATH and update['update_id'] in [u['update_id'] for u in value['updates']] for path, value in writes))
        acks.append(update['update_id'])
        return True
      return False

    b = SimpleNamespace(
      RUN_SECONDS=duration, MAINTENANCE_SECONDS=0.04, APP_ID=18, inbox_lease=nullcontext,
      storage_get=lambda path: copy.deepcopy(records.get(path)), storage_put=put,
      telegram=telegram, dispatch_update=action, acknowledge_received_callback=ack,
      request_json=lambda path: {'runtime_dir': 'old'}, now=lambda: 'now',
      set_status=lambda *a, **k: None,
      sync_bot_commands=lambda *a: False, sync_question_state=lambda *a: None,
      navigation_origin=lambda settings: settings.get("mobiusAddress", ""),
      BridgeError=RuntimeError,
    )
    return b, records, writes, handled, cursors, acks

  def test_navigation_uses_job_context_not_untrusted_storage_address(self):
    seen=[]
    b,records,*_=self.fixture(batches=[[{'update_id':1,'message':{'text':'hello'}},{'update_id':2,'message':{'text':'again'}}]])
    records['settings.json']['mobiusAddress']='https://first.example'
    def action(update,settings,pairing,origin):
      seen.append(origin)
      records['settings.json']['mobiusAddress']='https://second.example'
    b.dispatch_update=action
    run_listener(b,{}, {'runtime_dir':'old','public_origin':'https://accepted.example'}, 'fixture_bot')
    self.assertEqual(seen,['https://accepted.example','https://accepted.example'])

  def test_intake_and_navigation_continue_during_slow_reply(self):
    release = threading.Event()
    started = threading.Event()
    events = []

    def dispatch(update, records):
      if update['update_id'] == 1:
        events.append('reply-start')
        started.set()
        self.assertTrue(release.wait(1))
        events.append('reply-end')
      elif update['update_id'] == 2:
        self.assertTrue(started.wait(1))
        events.append('control')
        release.set()
      else:
        events.append('next-message')

    first = {'update_id': 1, 'message': {'text': 'hello'}}
    control = {'update_id': 2, 'callback_query': {'data': 'cmd:model'}}
    followup = {'update_id': 3, 'message': {'text': 'next'}}
    b, records, writes, handled, cursors, acks = self.fixture([[first], [control, followup]], dispatch)
    try:
      run_listener(b, {}, {'runtime_dir': 'old'}, 'bot')
    finally:
      release.set()
    self.assertEqual(events, ['reply-start', 'control', 'reply-end', 'next-message'])
    self.assertEqual(acks, [2])
    self.assertEqual(records[INBOX_PATH]['updates'], [])
    self.assertIn(4, cursors)
    self.assertGreater(len(cursors), 2)

  def test_saved_inbox_recovers_and_keeps_message_order(self):
    b, records, writes, handled, cursors, _ = self.fixture()
    records[INBOX_PATH] = {'updates': [{'update_id': 9}, {'update_id': 10}]}
    run_listener(b, {'offset': 5}, {'runtime_dir': 'old'}, 'bot')
    self.assertEqual([row[0] for row in handled], [9, 10])
    self.assertTrue(all(cursor >= 11 for cursor in cursors))
    self.assertEqual(records[INBOX_PATH]['updates'], [])

  def test_pause_preserves_received_messages_for_resume(self):
    b, records, writes, handled, cursors, _ = self.fixture([[{'update_id': 1}]])
    original = b.telegram
    def pause(method, params):
      result = original(method, params)
      records['settings.json']['enabled'] = False
      return result
    b.telegram = pause
    run_listener(b, {}, {'runtime_dir': 'old'}, 'bot')
    self.assertFalse(handled)
    # Unlike the old synchronous loop we may acknowledge intake, but only
    # after a durable save. Pausing must never discard the received update.
    self.assertEqual(records[INBOX_PATH]['updates'][0]['update_id'], 1)

  def test_revocation_is_checked_before_dispatch(self):
    b, records, writes, handled, cursors, _ = self.fixture([[{'update_id': 1}]])
    original = b.telegram
    def revoke(method, params):
      result = original(method, params)
      records.pop('pairing.json', None)
      return result
    b.telegram = revoke
    run_listener(b, {}, {'runtime_dir': 'old'}, 'bot')
    self.assertIsNone(handled[0][1])

  def test_failed_inbox_save_never_advances_telegram_cursor(self):
    b, records, writes, handled, cursors, _ = self.fixture([[{'update_id': 1}]])
    def fail(*args):
      raise OSError('disk unavailable')
    b.storage_put = fail
    with self.assertRaises(OSError):
      run_listener(b, {}, {'runtime_dir': 'old'}, 'bot')
    self.assertEqual(cursors, [0])
    self.assertFalse(handled)

  def test_new_accepted_revision_yields_for_activation(self):
    b, *_ = self.fixture(duration=5)
    b.request_json = lambda path: {'runtime_dir': 'new'}
    started = time.monotonic()
    run_listener(b, {}, {'runtime_dir': 'old'}, 'bot')
    self.assertLess(time.monotonic() - started, 0.5)

  def test_only_read_only_navigation_can_overtake_actions(self):
    for data in ['cmd:new', 'mdl:s:codex:model', 'q:nonce:0:0', 's:nonce']:
      self.assertFalse(responsive_control({'callback_query': {'data': data}}))
    self.assertTrue(responsive_control({'callback_query': {'data': 'mdl:p:codex'}}))

  def test_optional_menu_failure_does_not_stop_listener(self):
    b, records, writes, handled, cursors, _ = self.fixture()
    def fail(*args):
      raise RuntimeError('menu unavailable')
    b.sync_bot_commands = fail
    run_listener(b, {}, {'runtime_dir': 'old'}, 'bot')
    self.assertGreater(len(cursors), 2)

  def test_active_action_is_not_replayed_when_navigation_overtakes_it(self):
    # Intake persistence retains only still-pending items; no cursor bypass.
    b, records, writes, handled, cursors, _ = self.fixture([
      [{'update_id': 1}, {'update_id': 2, 'message': {'text': '/status'}}],
      [{'update_id': 1}, {'update_id': 2, 'message': {'text': '/status'}}],
    ])
    run_listener(b, {}, {'runtime_dir': 'old'}, 'bot')
    self.assertEqual(sorted(row[0] for row in handled), [1, 2])


  def test_slow_ack_does_not_block_menu(self):
    started = threading.Event()
    release = threading.Event()
    menu = threading.Event()
    update = {'update_id': 1, 'callback_query': {'data': 'cmd:settings', 'from': {'id': 99}, 'message': {'chat': {'id': 99}}}}
    def dispatch(update, records):
      self.assertTrue(update['_callback_ack_delegated'])
      self.assertTrue(started.wait(1))
      menu.set()
      release.set()
    b, records, writes, handled, cursors, acks = self.fixture([[update]], dispatch)
    original = b.acknowledge_received_callback
    def slow_ack(update, pairing):
      result = original(update, pairing)
      started.set()
      self.assertTrue(release.wait(1), 'Menu blocked behind callback acknowledgement')
      return result
    b.acknowledge_received_callback = slow_ack
    try:
      run_listener(b, {}, {'runtime_dir': 'old'}, 'bot')
    finally:
      release.set()
    self.assertTrue(menu.is_set())
    self.assertNotIn('_callback_ack_delegated', str(writes))
    self.assertEqual(records[INBOX_PATH]['updates'], [])

  def test_recovered_callback_is_acknowledged_without_persisting_a_promise(self):
    b, records, writes, handled, cursors, acks = self.fixture()
    records[INBOX_PATH] = {'updates': [{'update_id': 9, 'callback_query': {'data': 'cmd:settings'}}]}
    writes.append((INBOX_PATH, copy.deepcopy(records[INBOX_PATH])))
    run_listener(b, {'offset': 10}, {'runtime_dir': 'old'}, 'bot')
    self.assertEqual(acks, [9])
    self.assertEqual([h[0] for h in handled], [9])


  def test_revoked_callback_does_not_suppress_dispatch_pairing_feedback(self):
    update = {'update_id': 1, 'callback_query': {'data': 'cmd:settings', 'from': {'id': 8}, 'message': {'chat': {'id': 99}}}}
    def dispatch(update, records):
      self.assertNotIn('_callback_ack_delegated', update)
    b, *_ = self.fixture([[update]], dispatch)
    run_listener(b, {}, {'runtime_dir': 'old'}, 'bot')


  def test_ack_lane_is_bounded_and_overflow_keeps_inline_path(self):
    from unittest.mock import patch
    release = threading.Event()
    handled = []
    def dispatch(update, records):
      handled.append(update.get('_callback_ack_delegated', False))
      if len(handled) == 2:release.set()
    batches = [[{'update_id': i, 'callback_query': {'data': 'cmd:settings', 'from': {'id': 99}, 'message': {'chat': {'id': 99}}}} for i in (1, 2)]]
    b, *_ = self.fixture(batches, dispatch)
    original = b.acknowledge_received_callback
    def ack(update, pairing):
      self.assertTrue(release.wait(1));return original(update, pairing)
    b.acknowledge_received_callback = ack
    try:
      with patch('bridge_loop.MAX_PENDING', 20):
        # Poll batch capacity is20; fill its ack capacity using the same fixture.
        batches[0].extend({'update_id': i, 'callback_query': {'data': 'cmd:settings', 'from': {'id': 99}, 'message': {'chat': {'id': 99}}}} for i in range(3, 22))
        run_listener(b, {}, {'runtime_dir': 'old'}, 'bot')
    finally:release.set()
    self.assertEqual(handled, [True]*20+[False])


def test_intake_never_persists_credential_looking_plaintext():
  key='123456:'+('A'*40)
  fixture=ListenerTests()
  update={'update_id':1,'message':{'chat':{'id':99,'type':'private'},'from':{'id':99},'text':key}}
  b,records,writes,handled,cursors,acks=fixture.fixture([[update]])
  run_listener(b,{}, {'runtime_dir':'old'}, 'synthetic_bot')
  import json
  assert key not in json.dumps(writes)


def test_rejected_receipt_is_durable_before_receive_cursor_and_ordered():
  key='123456:'+('A'*40)
  fixture=ListenerTests();seen=[]
  first={'update_id':1,'message':{'text':'ordinary'}}
  reject={'update_id':2,'message':{'chat':{'id':99,'type':'private','title':key},'from':{'id':99,'first_name':key},'date':7,'message_id':8,'text':key,'reply_to_message':{'text':key}}}
  third={'update_id':3,'message':{'text':'after'}}
  b,records,writes,handled,cursors,acks=fixture.fixture([[first,reject,third]])
  def dispatch(update,settings,pairing,origin):seen.append(copy.deepcopy(update))
  b.dispatch_update=dispatch
  run_listener(b,{}, {'runtime_dir':'old'}, 'synthetic_bot')
  assert [u['update_id'] for u in seen]==[1,2,3]
  receipt=seen[1]
  assert receipt=={'update_id':2,'_bridge_rejected_input':True,'message':{'chat':{'id':99,'type':'private'},'from':{'id':99},'date':7,'message_id':8}}
  initial=next(value for path,value in writes if path==INBOX_PATH)
  assert initial['updates'][1]==receipt
  first_inbox=next(i for i,(p,v) in enumerate(writes) if p==INBOX_PATH)
  cursor_write=next(i for i,(p,v) in enumerate(writes) if p=='bridge-runtime.json' and v.get('offset')==4)
  assert first_inbox<cursor_write and 4 in cursors
  assert records[INBOX_PATH]['updates']==[]


def test_admission_does_not_persist_nested_quoted_key_or_caption():
  from bridge_loop import admit_update,responsive_control
  key='123456:'+('A'*40)
  import json
  for extra in ({'reply_to_message':{'text':key}}, {'caption':key}, {'forward_origin':{'sender_user':{'first_name':key}}}):
    update={'update_id':1,'message':{'chat':{'id':99,'type':'private'},'from':{'id':99},'text':'/menu',**extra}}
    projected=admit_update(update)
    assert key not in json.dumps(projected)
    assert projected['_bridge_rejected_input'] is True
    assert not responsive_control(projected)
