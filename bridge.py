#!/usr/bin/env python3
"""Public-core edition: one paired private owner; app-scoped job auth only.

A reviewed job_secret_read grant permits this job to hold its own bot key in
RAM for fixed-origin Telegram requests. No frame, model, or response gets it.
"""
from __future__ import annotations
import hashlib, hmac, json, os, re, secrets, sys, threading, time, urllib.error, urllib.parse, urllib.request, uuid
from types import SimpleNamespace
from datetime import UTC, datetime
from contextlib import contextmanager
from bridge_loop import run_listener, contains_bot_key
from bridge_progress import ReplyProgress
import bridge_assistants
from telegram_http import TelegramHTTP, TelegramError, NoRedirect, bot_identity, safe_origin

APP_ID = int(sys.argv[1])
APP_TOKEN = os.environ["APP_TOKEN"]
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
AUTH = {"Authorization": f"Bearer {APP_TOKEN}"}
RUN_SECONDS = 30 * 60
MAINTENANCE_SECONDS = 60
AGENT_TIMEOUT = 12 * 60
QUESTION_STATE_PATH = "telegram-question.json"
MODEL_STATE_PATH = "model.json"
PROVIDER_LABELS = {"mobius":"Möbius", "claude":"Claude", "codex":"Codex"}
TELEGRAM_SYSTEM_PROMPT = (
 "This is a private text-first Telegram conversation owned by Telegram Bridge. "
 "Reply concisely in plain text. Saved ordinary question cards can be answered "
 "here as agent-scoped input, NEVER as trusted owner permission. Privileged "
 "approval, secure input, setup and rich/media artifacts must be completed "
 "in Möbius. Do not request credentials in Telegram or paste transcripts. "
 "No screenshot or private media transport is provided by this edition."
)
_status_lock = threading.RLock()
_inbox_lock = threading.RLock()
_outbox_lock = threading.RLock()
_update_context = threading.local()
_model_cache = None
_model_cache_at = 0.0
_model_cache_lock = threading.Lock()
_transport = None

class BridgeError(RuntimeError):
 def __init__(self, message="Bridge request could not be completed.", *, status=None, reason=""):
  super().__init__(message); self.status=status; self.reason=reason

@contextmanager
def inbox_lease():
 with _inbox_lock: yield


def request_json(path, *, method="GET", body=None, timeout=20, headers=None, response_headers=None):
 if not isinstance(path,str) or not path.startswith('/api/') or '?' in path or '#' in path:
  raise BridgeError('Invalid Möbius route.')
 data=json.dumps(body,ensure_ascii=False,allow_nan=False).encode() if body is not None else None
 req=urllib.request.Request(API_BASE+path,data=data,method=method,headers={**AUTH,**(headers or {}),'Content-Type':'application/json'})
 try:
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
  with opener.open(req,timeout=timeout) as response:
   raw=response.read(4*1024*1024+1)
   if len(raw)>4*1024*1024: raise BridgeError('Möbius response exceeded its bound.')
   if response_headers is not None:response_headers['ETag']=response.headers.get('ETag')
   return json.loads(raw) if raw else {}
 except urllib.error.HTTPError as exc:
  # Never surface upstream bodies, URLs, content, or credentials.
  raise BridgeError(f'Möbius request could not be completed ({exc.code}).',status=exc.code) from None
 except (OSError,ValueError):raise BridgeError('Möbius is temporarily unavailable.') from None


def telegram(method, params=None):
 global _transport
 if _transport is None: _transport=TelegramHTTP(APP_ID,APP_TOKEN,API_BASE)
 # A job-bound RAM key; no service/frame route exports the transport.
 try:
  update=getattr(_update_context,'update',None)
  if method=='sendMessage' and isinstance(update,dict):
   # Durable before send. A lost response is not permission to resend.
   receipt_key=hashlib.sha256(json.dumps([update.get('update_id'),method,params],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
   with _outbox_lock:
    receipts=storage_get('telegram-outbox.json') or {}
    old=receipts.get(receipt_key)
    if old:
     if old.get('state')=='sent':return {'message_id':old['message_id']}
     raise BridgeError('Telegram delivery is uncertain; no automatic resend. Open Möbius to check the result.')
    if len(receipts)>=2000:raise BridgeError('Delivery receipt limit reached. Pause Bridge and review in Möbius.')
    receipts[receipt_key]={'state':'uncertain','at':now()}
    storage_put('telegram-outbox.json',receipts)
   result=_transport.call(method,params)
   if not isinstance(result,dict) or type(result.get('message_id')) is not int:raise TelegramError(reason='invalid-response')
   with _outbox_lock:
    receipts=storage_get('telegram-outbox.json') or {}
    receipts[receipt_key]={'state':'sent','at':now(),'message_id':result['message_id']}
    storage_put('telegram-outbox.json',receipts)
   return result
  return _transport.call(method,params)
 except TelegramError as exc:
  raise BridgeError('Telegram request could not be completed.',status=exc.code or None,reason=exc.reason) from None

def now() -> str:
  return datetime.now(UTC).isoformat()


def storage_get(path: str, *, response_headers=None) -> object | None:
  try:
    return request_json(f"/api/storage/apps/{APP_ID}/{path}", **({'response_headers': response_headers} if response_headers is not None else {}))
  except BridgeError as exc:
    if exc.status == 404:
      return None
    raise


def storage_put(path: str, value: object) -> None:
  request_json(
    f"/api/storage/apps/{APP_ID}/{path}", method="PUT", body=value,
  )


def ensure_storage_null(path: str) -> None:
  """Materialize an optional record once, so polling does not emit 404s."""
  try:
    request_json(f"/api/storage/apps/{APP_ID}/{path}")
  except BridgeError as exc:
    if exc.status != 404:
      raise
    storage_put(path, None)


def storage_delete(path: str) -> None:
  try:
    request_json(f"/api/storage/apps/{APP_ID}/{path}", method="DELETE")
  except BridgeError as exc:
    if exc.status != 404:
      raise


def clear_question_state() -> None:
  """Clear pending-question state without reintroducing a poll-time 404."""
  storage_put(QUESTION_STATE_PATH, None)


def activity(label: str, tone: str = "neutral") -> None:
  with _status_lock:
    status = storage_get("status.json") or {}
    events = [{"at": now(), "label": label[:120], "tone": tone}]
    if isinstance(status, dict) and isinstance(status.get("events"), list):
      events.extend(status["events"][:7])
    if not isinstance(status, dict):
      status = {}
    status["events"] = events
    storage_put("status.json", status)


def set_status(state: str, label: str, detail: str, **extra: object) -> None:
  with _status_lock:
    current = storage_get("status.json") or {}
    events = current.get("events", []) if isinstance(current, dict) else []
    value = {
      "state": state,
      "label": label,
      "detail": detail,
      "checkedAt": now(),
      "events": events[:8] if isinstance(events, list) else [],
      **extra,
    }
    storage_put("status.json", value)


def send_text(
  chat_id: int,
  text: str,
  *,
  reply_markup: dict | None = None,
  reply_to_message_id: int | None = None,
  disable_link_preview: bool = False,
) -> dict | None:
  clean = str(text or "").strip()
  if not clean:
    clean = "Möbius completed the turn without a text reply."
  chunks: list[str] = []
  while clean:
    if len(clean) <= 3900:
      chunk, clean = clean, ""
    else:
      split = clean.rfind("\n", 0, 3900)
      if split < 1000:
        split = clean.rfind(" ", 0, 3900)
      if split < 1000:
        split = 3900
      chunk, clean = clean[:split].rstrip(), clean[split:].lstrip()
    chunks.append(chunk)
  sent = None
  for index, chunk in enumerate(chunks):
    params: dict[str, object] = {"chat_id": chat_id, "text": chunk}
    if disable_link_preview:
      params['link_preview_options'] = {'is_disabled': True}
    if reply_to_message_id and index == 0:
      params["reply_parameters"] = {
        "message_id": reply_to_message_id,
        "allow_sending_without_reply": True,
      }
    if reply_markup and index == len(chunks) - 1:
      params["reply_markup"] = reply_markup
    result = telegram("sendMessage", params)
    sent = result if isinstance(result, dict) else sent
  return sent


def open_chat_markup(public_origin: str, chat_id: str) -> dict | None:
  if not public_origin or not chat_id:
    return None
  return {
    "inline_keyboard": [[{
      "text": "Open in Möbius",
      "url": f"{public_origin}/shell/?chat={chat_id}",
    }]],
  }


def display_name(user: dict) -> str:
  parts = [str(user.get("first_name") or "").strip(), str(user.get("last_name") or "").strip()]
  return " ".join(part for part in parts if part) or "Telegram user"


def conversation_title(pairing: dict, created_at: str | None = None) -> str:
  stamp = datetime.now(UTC)
  if created_at:
    try:
      stamp = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
      pass
  name = pairing.get("displayName") or "Private chat"
  return f"Telegram · {name} · {stamp.strftime('%b %-d, %H:%M')}"


def question_text(state: dict, *, answered: dict | None = None) -> str:
  parts: list[str] = []
  lead = str(state.get("leadText") or "").strip()
  if lead:
    parts.append(lead)
  parts.append("Möbius needs your answer")
  selections = state.get("selections") if isinstance(state.get("selections"), dict) else {}
  for index, question in enumerate(state.get("questions") or []):
    heading = str(question.get("header") or "").strip()
    prefix = f"{index + 1}. " if len(state.get("questions") or []) > 1 else ""
    line = prefix + (f"{heading}: " if heading else "") + str(question.get("question") or "")
    parts.append(line)
    option_lines = []
    for option in question.get("options") or []:
      description = str(option.get("description") or "").strip()
      if description:
        option_lines.append(f"• {option.get('label')} — {description}")
    if option_lines:
      parts.append("\n".join(option_lines))
    if question.get("multiSelect") and not answered:
      parts.append("Select all that apply, then tap Submit answers.")
    selected = (answered or selections).get(str(index))
    if selected:
      values = selected if isinstance(selected, list) else [selected]
      parts.append("Selected: " + ", ".join(str(item) for item in values))
  if answered:
    parts.append("✓ Answer sent to Möbius")
  return "\n\n".join(part for part in parts if part)


def question_markup(state: dict, public_origin: str) -> dict:
  rows: list[list[dict[str, str]]] = []
  nonce = str(state.get("nonce") or "")
  selections = state.get("selections") if isinstance(state.get("selections"), dict) else {}
  questions = state.get("questions") or []
  for question_index, question in enumerate(questions):
    selected = selections.get(str(question_index))
    selected_values = selected if isinstance(selected, list) else [selected]
    for option_index, option in enumerate(question.get("options") or []):
      label = str(option.get("label") or "")
      chosen = label in selected_values
      marker = "☑ " if question.get("multiSelect") and chosen else ("● " if chosen else "")
      question_prefix = f"{question_index + 1} · " if len(questions) > 1 else ""
      rows.append([{
        "text": (question_prefix + marker + label)[:64],
        "callback_data": f"q:{nonce}:{question_index}:{option_index}",
      }])
    rows.append([{
      "text": "✍ Type another answer",
      "callback_data": f"t:{nonce}:{question_index}",
    }])
  if len(questions) > 1 or any(q.get("multiSelect") for q in questions):
    rows.append([{"text": "Submit answers", "callback_data": f"s:{nonce}"}])
  return {"inline_keyboard": rows}


def resolved_question_answers(state: dict) -> dict[str, str] | None:
  selections = state.get("selections") if isinstance(state.get("selections"), dict) else {}
  result: dict[str, str] = {}
  for index, question in enumerate(state.get("questions") or []):
    selected = selections.get(str(index))
    if isinstance(selected, list):
      values = [str(item).strip() for item in selected if str(item).strip()]
      if not values:
        return None
      answer = ", ".join(values)
    else:
      answer = str(selected or "").strip()
      if not answer:
        return None
    result[str(question.get("question") or "")] = answer
  return result


def append_stream_text(items: list[dict], content: str, item_id: str | None) -> None:
  if not content:
    return
  if item_id:
    for item in reversed(items):
      if item.get("type") == "text" and item.get("text_item_id") == item_id:
        item["content"] = str(item.get("content") or "") + content
        return
  if items and items[-1].get("type") == "text" and not item_id:
    items[-1]["content"] = str(items[-1].get("content") or "") + content
  else:
    items.append({"type": "text", "content": content, "text_item_id": item_id})


def finalize_stream_text(items: list[dict], content: str, item_id: str | None) -> None:
  if not content:
    return
  if item_id:
    for item in reversed(items):
      if item.get("type") == "text" and item.get("text_item_id") == item_id:
        item["content"] = content
        return
  for item in reversed(items):
    if item.get("type") == "text":
      item["content"] = content
      return
  items.append({"type": "text", "content": content, "text_item_id": item_id})


def stream_text(items: list[dict]) -> str:
  texts = [
    str(item.get("content") or "").strip()
    for item in items if item.get("type") == "text"
  ]
  return "\n\n".join(text for text in texts if text).strip()


def after_baseline(text: str, baseline: str) -> str:
  clean = str(text or "").strip()
  prior = str(baseline or "").strip()
  if prior and clean.startswith(prior):
    return clean[len(prior):].lstrip()
  return clean


def available_models(*, refresh=False) -> dict[str, list[dict[str, str]]]:
  """Return visible, available models grouped for Telegram's compact picker."""
  global _model_cache, _model_cache_at
  with _model_cache_lock:
    if not refresh and _model_cache is not None and time.monotonic() - _model_cache_at < 60:
      return _model_cache
  payload = request_json("/api/models")
  providers = payload.get("providers") if isinstance(payload, dict) else None
  if not isinstance(providers, dict):
    raise BridgeError("Möbius could not load the model list")
  hidden: set[str] = set()
  try:
    preferences = request_json("/api/owner/model-prefs")
    if isinstance(preferences, dict) and isinstance(preferences.get("hidden_ids"), list):
      hidden = {str(item) for item in preferences["hidden_ids"]}
  except BridgeError:
    # Availability is authoritative when optional owner preferences are restricted.
    pass
  result: dict[str, list[dict[str, str]]] = {}
  for provider in PROVIDER_LABELS:
    rows = providers.get(provider)
    if not isinstance(rows, list):
      continue
    models = []
    for row in rows:
      if not isinstance(row, dict) or row.get("available") is not True:
        continue
      model = str(row.get("id") or "").strip()
      if not model or model in hidden or len(f"mdl:s:{provider}:{model}".encode())>64:
        continue
      models.append({
        "id": model,
        "label": str(row.get("label") or model).strip()[:80],
        "provider": provider,
      })
    if models:
      result[provider] = models
  with _model_cache_lock:
    _model_cache, _model_cache_at = result, time.monotonic()
  return result


def current_model(models: dict[str, list[dict[str, str]]]) -> dict | None:
  conversation = storage_get("conversation.json")
  chat_id = (
    str(conversation.get("chatId") or "")
    if isinstance(conversation, dict) else ""
  )
  if chat_id:
    chats = request_json("/api/app-chats")
    if isinstance(chats, list):
      row = next(
        (item for item in chats if isinstance(item, dict) and str(item.get("id") or "") == chat_id),
        None,
      )
      if row:
        provider = str(row.get("provider") or "")
        model = str(row.get("model") or "")
        for option in models.get(provider, []):
          if option["id"] == model:
            return option
        if model:
          return {"id": model, "label": model, "provider": provider}
  saved = storage_get(MODEL_STATE_PATH)
  if isinstance(saved, dict):
    provider = str(saved.get("provider") or "")
    model = str(saved.get("model") or "")
    for option in models.get(provider, []):
      if option["id"] == model:
        return option
  return None


def model_picker_text(current: dict | None, provider: str | None = None) -> str:
  current_label = str(current.get("label") or "") if current else "Möbius default"
  if provider:
    return (
      f"Choose a {PROVIDER_LABELS.get(provider, provider)} model.\n\n"
      f"Current: {current_label}\n"
      "Changing model preserves this chat and starts a fresh conversation."
    )
  return (
    "Choose a model provider.\n\n"
    f"Current: {current_label}\n"
    "Changing model preserves this chat and starts a fresh conversation."
  )


def model_picker_markup(
  models: dict[str, list[dict[str, str]]],
  current: dict | None,
  provider: str | None = None,
) -> dict:
  rows: list[list[dict[str, str]]] = []
  if provider:
    current_id = str(current.get("id") or "") if current else ""
    for option in models.get(provider, []):
      marker = "✓ " if option["id"] == current_id else ""
      rows.append([{
        "text": (marker + option["label"])[:64],
        "callback_data": f"mdl:s:{provider}:{option['id']}",
      }])
    rows.append([{"text": "‹ Providers", "callback_data": "cmd:model"}])
  else:
    for name in PROVIDER_LABELS:
      if models.get(name):
        rows.append([{
          "text": PROVIDER_LABELS[name],
          "callback_data": f"mdl:p:{name}",
        }])
  return {"inline_keyboard": rows}


def edit_model_picker(
  message: dict,
  text: str,
  reply_markup: dict,
) -> None:
  telegram("editMessageText", {
    "chat_id": (message.get("chat") or {}).get("id"),
    "message_id": message.get("message_id"),
    "text": text,
    "reply_markup": reply_markup,
  })


def send_model_picker(chat_id: int) -> None:
  models = available_models()
  current = current_model(models)
  send_text(
    chat_id,
    model_picker_text(current),
    reply_markup=model_picker_markup(models, current),
  )


def stale_callback(callback_id: str) -> None:
  answer_callback(
    callback_id, text="This question is no longer active.",
  )


def mark_timing(name, *, once=False):
  timing = getattr(_update_context, "timing", None)
  if isinstance(timing, dict) and (not once or name not in timing):
    timing[name] = round((time.monotonic() - timing["started"]) * 1000, 1)


def message_cid(prefix):
  update = getattr(_update_context, "update", None)
  if isinstance(update, dict) and isinstance(update.get("update_id"), int):
    return f"{prefix}-{APP_ID}-{update['update_id']}"
  return f"{prefix}-{uuid.uuid4()}"


def answer_callback(callback_id: str, **params: object) -> None:
  """Acknowledge a Telegram button without failing its actual action.

  Telegram rejects acknowledgements after its short callback deadline with a
  400 even though the update and requested action remain valid. Möbius turns
  can legitimately outlive that deadline, so an expired acknowledgement is a
  cosmetic failure: suppress it instead of showing a misleading bridge error
  or preventing a command such as "New conversation" from running.
  """
  if not callback_id:
    return
  update = getattr(_update_context, "update", None) or {}
  callback = update.get("callback_query") or {}
  if (update.get("_callback_acknowledged") or update.get("_callback_ack_delegated")) and callback.get("id") == callback_id:
    if params.get("text"):
      send_text(int(callback["message"]["chat"]["id"]), str(params["text"]))
    return
  try:
    telegram("answerCallbackQuery", {
      "callback_query_id": callback_id,
      **params,
    })
  except BridgeError as exc:
    if exc.status != 400:
      raise


def handle_callback_query(
  callback: dict,
  pairing: dict | None,
  public_origin: str,
) -> dict | None:
  callback_id = str(callback.get("id") or "")
  user = callback.get("from") or {}
  message = callback.get("message") or {}
  chat = message.get("chat") or {}
  data = str(callback.get("data") or "")
  if (
    not pairing
    or int(user.get("id") or 0) != int(pairing.get("userId") or 0)
    or chat.get("type") != "private"
    or int(chat.get("id") or 0) != int(pairing.get("chatId") or 0)
  ):
    answer_callback(
      callback_id, text="This button is not paired to your chat.",
    )
    return pairing

  if data.startswith(('chats:', 'chat:', 'go:')):
    answer_callback(callback_id)
    chat_callback(data,pairing,public_origin,message)
    return pairing

  # Older Telegram messages retain their Settings callback after a menu update.
  if data == 'cmd:settings':
    data = 'cmd:model'

  if data == 'cmd:home':
    answer_callback(callback_id)
    conversation=storage_get('conversation.json') or {}
    text,markup=owner_home(pairing,public_origin,conversation.get('chatId'))
    navigation_reply(int(pairing['chatId']),text,markup,message)
    return pairing

  if data == "cmd:assistants" or data.startswith("studio:"):
    answer_callback(callback_id)
    bridge_assistants.callback(SimpleNamespace(**globals()), data, pairing, public_origin, message)
    return pairing

  if data == "cmd:new":
    pending = sync_question_state(public_origin)
    if isinstance(pending, dict):
      answer_callback(callback_id, text="Answer the current question first.")
      return pairing
    answer_callback(callback_id)
    storage_delete("conversation.json")
    new_chat_id = ensure_conversation(pairing)
    send_text(
      int(pairing["chatId"]),
      "Personal · New conversation ready.\nYour next message goes here.",
    )
    activity("Started a fresh Telegram conversation")
    return pairing

  if data == "cmd:model" or data.startswith("mdl:"):
    models = available_models(refresh=data.startswith("mdl:s:"))
    current = current_model(models)
    if data == "cmd:model":
      answer_callback(callback_id)
      edit_model_picker(
        message,
        model_picker_text(current),
        model_picker_markup(models, current),
      )
      return pairing
    parts = data.split(":", 3)
    if len(parts) == 3 and parts[:2] == ["mdl", "p"]:
      provider = parts[2]
      if provider not in models:
        stale_callback(callback_id)
        return pairing
      answer_callback(callback_id)
      edit_model_picker(
        message,
        model_picker_text(current, provider),
        model_picker_markup(models, current, provider),
      )
      return pairing
    if len(parts) == 4 and parts[:2] == ["mdl", "s"]:
      provider, model = parts[2], parts[3]
      option = next(
        (item for item in models.get(provider, []) if item["id"] == model),
        None,
      )
      if not option:
        stale_callback(callback_id)
        return pairing
      pending = sync_question_state(public_origin)
      if isinstance(pending, dict):
        answer_callback(callback_id, text="Answer the current question first.")
        return pairing
      answer_callback(callback_id)
      storage_put(MODEL_STATE_PATH, {
        "provider": provider,
        "model": model,
        "label": option["label"],
        "selectedAt": now(),
      })
      if current and current.get("id") == model and current.get("provider") == provider:
        edit_model_picker(
          message,
          f"Already using {option['label']}. Future /new conversations will use it too.",
          {"inline_keyboard": [[{"text": "Choose another", "callback_data": "cmd:model"}]]},
        )
        return pairing
      storage_delete("conversation.json")
      new_chat_id = ensure_conversation(pairing)
      rows: list[list[dict[str, str]]] = [[{
        "text": "Choose another",
        "callback_data": "cmd:model",
      }]]
      if public_origin:
        rows.append([{
          "text": "Open conversation",
          "url": f"{public_origin}/shell/?chat={new_chat_id}",
        }])
      edit_model_picker(
        message,
        f"Personal · New conversation ready.\nNow using {option['label']}.",
        {"inline_keyboard": rows},
      )
      activity(f"Changed Telegram model to {option['label']}", "good")
      return pairing
    stale_callback(callback_id)
    return pairing

  state = sync_question_state(public_origin)
  if not isinstance(state, dict) or state.get("external") or not state.get("telegramMessageId"):
    stale_callback(callback_id)
    return pairing
  question_guard(state, pairing)
  parts = data.split(":")
  if len(parts) < 2 or parts[1] != str(state.get("nonce") or ""):
    stale_callback(callback_id)
    return pairing
  questions = state.get("questions") or []
  selections = state.get("selections") if isinstance(state.get("selections"), dict) else {}

  if parts[0] == "q" and len(parts) == 4:
    try:
      question_index, option_index = int(parts[2]), int(parts[3])
      if question_index < 0 or option_index < 0: raise ValueError()
      question = questions[question_index]
      label = str(question["options"][option_index]["label"])
    except (IndexError, KeyError, TypeError, ValueError):
      stale_callback(callback_id)
      return pairing
    answer_callback(callback_id)
    key = str(question_index)
    if question.get("multiSelect"):
      selected = selections.get(key)
      values = list(selected) if isinstance(selected, list) else []
      if label in values:
        values.remove(label)
      else:
        values.append(label)
      selections[key] = values
    else:
      selections[key] = label
    state["selections"] = selections
    chosen=state.get('selectedOptions') or {}
    typed_questions=set(state.get('typedQuestions') or [])
    option_id=question['options'][option_index].get('id')
    if not question.get('multiSelect'):
      typed_questions.discard(question['id'])
      if isinstance(option_id,str) and option_id:chosen[question['id']]=[option_id]
      else:chosen.pop(question['id'],None)
    elif question['id'] in typed_questions:
      # A mixed free-text/button answer never promotes typed labels to consent.
      chosen.pop(question['id'],None)
    elif isinstance(option_id,str) and option_id:
      ids=list(chosen.get(question['id']) or [])
      if option_id in ids:ids.remove(option_id)
      else:ids.append(option_id)
      chosen[question['id']]=ids
    state['typedQuestions']=list(typed_questions)
    state['selectedOptions']=chosen
    state.pop("awaitingTextQuestion", None)
    state.pop("promptMessageId", None)
    storage_put(QUESTION_STATE_PATH, state)
    if len(questions) == 1 and not question.get("multiSelect"):
      submit_question_state(state, pairing, public_origin)
    else:
      edit_question_message(state, public_origin)
    return pairing

  if parts[0] == "t" and len(parts) == 3:
    try:
      question_index = int(parts[2])
      if question_index < 0: raise ValueError()
      prompt = str(questions[question_index]["question"])
    except (IndexError, KeyError, TypeError, ValueError):
      stale_callback(callback_id)
      return pairing
    answer_callback(callback_id)
    sent = send_text(
      int(pairing["chatId"]),
      f"Type your answer to:\n{prompt}",
      reply_markup={"force_reply": True, "selective": True},
    )
    state["awaitingTextQuestion"] = question_index
    if isinstance(sent, dict):
      state["promptMessageId"] = sent.get("message_id")
    storage_put(QUESTION_STATE_PATH, state)
    return pairing

  if parts[0] == "s" and len(parts) == 2:
    if not resolved_question_answers(state):
      answer_callback(
        callback_id,
        text="Choose an answer for each question.",
        show_alert=True,
      )
    else:
      answer_callback(callback_id)
      submit_question_state(state, pairing, public_origin)
    return pairing

  stale_callback(callback_id)
  return pairing


def handle_pending_text_answer(
  message: dict,
  pairing: dict,
  public_origin: str,
) -> bool:
  text = str(message.get("text") or "").strip()
  if contains_bot_key(text):
    send_text(int(pairing['chatId']), 'Do not send bot keys in Telegram. Use the saved secure-input form in your Möbius owner chat.')
    return True
  state = sync_question_state(public_origin)
  if not isinstance(state, dict):
    return False
  if state.get("external") or not state.get("telegramMessageId"):
    send_text(int(pairing["chatId"]), "Answer the saved card in Möbius before continuing.", reply_markup=open_chat_markup(public_origin,state["mobiusChatId"]))
    return True
  question_guard(state, pairing)
  awaiting = state.get("awaitingTextQuestion")
  if type(awaiting) is not int or awaiting < 0:
    send_text(
      int(pairing["chatId"]),
      "Möbius is waiting for your answer. Use the buttons above, or tap “Type another answer”.",
      reply_markup=open_chat_markup(
        public_origin, str(state.get("mobiusChatId") or ""),
      ),
    )
    return True
  questions = state.get("questions") or []
  try:
    question = questions[awaiting]
  except (IndexError, TypeError):
    clear_question_state()
    return False
  selections = state.get("selections") if isinstance(state.get("selections"), dict) else {}
  if question.get("multiSelect"):
    current = selections.get(str(awaiting))
    values = list(current) if isinstance(current, list) else []
    values.append(text[:500])
    selections[str(awaiting)] = values
  else:
    selections[str(awaiting)] = text[:500]
  state["selections"] = selections
  chosen=state.get('selectedOptions') or {}
  chosen.pop(question['id'],None)
  state['typedQuestions']=list(set(state.get('typedQuestions') or [])|{question['id']})
  state['selectedOptions']=chosen
  state.pop("awaitingTextQuestion", None)
  state.pop("promptMessageId", None)
  storage_put(QUESTION_STATE_PATH, state)
  if len(questions) == 1 and not question.get("multiSelect"):
    submit_question_state(state, pairing, public_origin)
  else:
    edit_question_message(state, public_origin)
    send_text(int(pairing["chatId"]), "Answer saved. Complete the remaining choices above.")
  return True


def handle_update(
  update: dict,
  settings: dict,
  pairing: dict | None,
  public_origin: str,
) -> dict | None:
  callback = update.get("callback_query")
  if isinstance(callback, dict):
    return handle_callback_query(callback, pairing, public_origin)
  message = update.get("message")
  if not isinstance(message, dict):
    return pairing
  chat = message.get("chat") or {}
  user = message.get("from") or {}
  if chat.get("type") != "private":
    return pairing
  chat_id = int(chat["id"])
  user_id = int(user.get("id") or 0)
  message_id = int(message.get("message_id") or 0) or None
  raw_text = message.get("text")
  text = raw_text.strip() if isinstance(raw_text, str) else ""

  if not pairing:
    if not text:
      return pairing
    parts = text.split(maxsplit=1)
    supplied = parts[1].strip().upper() if len(parts) == 2 and parts[0].split("@", 1)[0] in {"/pair", "/start"} else ""
    expected = str(settings.get("pairingCode") or "").upper()
    if chat_id != user_id or user_id <= 0: return pairing
    if supplied and expected and hmac.compare_digest(supplied, expected):
      pairing = {
        "chatId": chat_id,
        "userId": user_id,
        "displayName": display_name(user),
        "username": user.get("username"),
        "pairedAt": now(),
      }
      # Consume the one-time code durably before external acknowledgement.
      storage_put("pairing.json", pairing)
      storage_put("settings.json", {**settings, "pairingCode": None})
      send_text(chat_id, "Paired securely. Send me a message and I’ll pass it to Möbius. Use /new for a fresh conversation or /menu for commands.")
      activity("Telegram chat paired", "good")
    elif text.startswith(("/start", "/pair")):
      send_text(chat_id, "Open Telegram Bridge in Möbius and use the current pairing code shown there.")
    return pairing

  if chat_id != int(pairing.get("chatId") or 0) or user_id != int(pairing.get("userId") or 0):
    return pairing
  if update.get('_bridge_rejected_input') is True:
    send_text(chat_id, 'Do not send bot keys in Telegram. Use the saved secure-input form in your Möbius owner chat.', reply_to_message_id=message_id)
    return pairing
  if not text:
    send_text(
      chat_id,
      "I can currently read text messages only. Send a text prompt or use /menu for commands.",
      reply_to_message_id=message_id,
    )
    return pairing
  command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
  if command=="/chats":
    show_chats(pairing,public_origin)
  elif command=="/bridge":
    show_bridge(pairing,public_origin)
  elif command in ("/bots","/assistants"):
    bridge_assistants.show(SimpleNamespace(**globals()), pairing, public_origin)
  elif command == "/new":
    pending = sync_question_state(public_origin)
    if isinstance(pending, dict):
      send_text(
        chat_id,
        "Möbius is waiting for your answer. Answer the current question before starting a new conversation.",
        reply_markup=open_chat_markup(
          public_origin, str(pending.get("mobiusChatId") or ""),
        ),
      )
      return pairing
    storage_delete("conversation.json")
    new_chat_id = ensure_conversation(pairing)
    send_text(
      chat_id,
      "Personal · New conversation ready.\nYour next message goes here.",
    )
    activity("Started a fresh Telegram conversation")
  elif command == "/settings":
    send_text(chat_id, "Use /model to choose your model.", reply_to_message_id=message_id)
  elif command == "/model":
    send_model_picker(chat_id)
  elif command == "/status":
    conversation = storage_get("conversation.json")
    current_chat_id = (
      str(conversation.get("chatId") or "")
      if isinstance(conversation, dict) else ""
    )
    context,_ = owner_context(pairing,current_chat_id)
    send_text(
      chat_id,
      "Bridge connected · private chat paired.\n\n"+context,
      reply_markup=command_markup(public_origin, current_chat_id),
    )
  elif command == "/help":
    # Old command-list entries can remain cached in Telegram clients.
    send_text(chat_id, "Use /menu for Conversations and Model.", reply_to_message_id=message_id)
  elif command in {"/menu", "/start"}:
    conversation = storage_get("conversation.json")
    current_chat_id = (
      str(conversation.get("chatId") or "")
      if isinstance(conversation, dict) else ""
    )
    text,markup=owner_home(pairing,public_origin,current_chat_id)
    send_text(chat_id,text,reply_markup=markup)
  elif handle_pending_text_answer(message, pairing, public_origin):
    pass
  elif text:
    ask_mobius(
      pairing,
      text,
      public_origin,
      reply_to_message_id=message_id,
    )
  return pairing



def own_chats(pairing):
 rows=request_json('/api/app-chats')
 if not isinstance(rows,list):raise BridgeError('Conversation status unavailable.')
 result=[r for r in rows if isinstance(r,dict) and r.get('created_by_app_id')==APP_ID and r.get('scope')==f"telegram:{pairing['chatId']}"]
 if any(not isinstance(r.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',r['id']) or 'pending_question_id' not in r for r in result):
  raise BridgeError('Conversation status unavailable.')
 return result


def ensure_conversation(pairing):
 saved=storage_get('conversation.json')
 if isinstance(saved,dict) and saved.get('chatId'):
  if saved.get('connectionId') or not any(r['id']==saved['chatId'] for r in own_chats(pairing)):
   raise BridgeError('Selected conversation is unavailable. Nothing was rerouted. Choose /chats or /new.')
  return saved['chatId']
 body={'title':conversation_title(pairing),'scope':f"telegram:{pairing['chatId']}",
  'scope_label':pairing.get('displayName') or 'Telegram','owner_visible':True,'system_prompt':TELEGRAM_SYSTEM_PROMPT}
 model=storage_get(MODEL_STATE_PATH)
 if isinstance(model,dict):
  options=available_models(refresh=True)
  if not any(m['id']==model.get('model') for m in options.get(model.get('provider'),[])):
   raise BridgeError('Selected model is unavailable. Choose /model before starting.')
  body.update(provider=model['provider'],model=model['model'])
 created=request_json('/api/app-chats',method='POST',body=body)
 cid=str(created['id']);storage_put('conversation.json',{'chatId':cid,'createdAt':now()});return cid


def owner_context(pairing,current_chat_id):
 row=next((r for r in own_chats(pairing) if r['id']==current_chat_id),None)
 if not row:return 'No current personal conversation. Choose /chats or /new.',None
 text='Personal · Current conversation: '+str(row.get('title') or 'Conversation')[:180]
 if row.get('pending_question_id'):text+='\nWaiting for your answer; trusted owner actions stay in Möbius.'
 elif row.get('running'):text+='\nWorking.'
 return text,row


def command_markup(public_origin,current_chat_id):
 rows=[]
 if public_origin:
  path='/shell/'+('?' + urllib.parse.urlencode({'chat':current_chat_id}) if current_chat_id else '')
  rows.append([{'text':'Open Möbius','url':public_origin+path}])
 return {'inline_keyboard':rows}


def owner_home(pairing,public_origin,current_chat_id):
 context,row=owner_context(pairing,current_chat_id)
 rows=[[{'text':'Conversations','callback_data':'chats:0'},{'text':'Model','callback_data':'cmd:model'}],
  [{'text':'Your bots','callback_data':'cmd:assistants'},{'text':'New conversation','callback_data':'cmd:new'}]]
 rows+=command_markup(public_origin,current_chat_id)['inline_keyboard']
 return 'Menu\nSend a message to continue.\n\n'+context,{'inline_keyboard':rows}


def show_bridge(pairing,public_origin):
 send_text(int(pairing['chatId']),'Open Bridge in Möbius for Chats, Bots and Tools. No Telegram panel is included.',
  reply_markup={'inline_keyboard':[[{'text':'Open Bridge','url':f'{public_origin}/shell/?app={APP_ID}'}]]} if public_origin else None)


def navigation_reply(chat_id,text,markup,message=None,*,disable_link_preview=False):
 if message and message.get('message_id'):
  try:
   telegram('editMessageText',{'chat_id':chat_id,'message_id':message['message_id'],'text':text,'reply_markup':markup});return
  except BridgeError as exc:
   if exc.reason=='not-modified':return
   if exc.reason!='edit-unavailable':raise
 send_text(chat_id,text,reply_markup=markup,disable_link_preview=disable_link_preview)


def show_chats(pairing,public_origin,message=None,page=0):
 rows=own_chats(pairing);page=max(0,min(page,max(0,(len(rows)-1)//6)))
 current=(storage_get('conversation.json') or {}).get('chatId')
 buttons=[[{'text':('✓ ' if r['id']==current else '')+str(r.get('title') or 'Conversation')[:50],'callback_data':'chat:'+r['id']}] for r in rows[page*6:(page+1)*6]]
 nav=[]
 if page:nav.append({'text':'‹ Previous','callback_data':f'chats:{page-1}'})
 if (page+1)*6<len(rows):nav.append({'text':'Next ›','callback_data':f'chats:{page+1}'})
 if nav:buttons.append(nav)
 buttons.append([{'text':'New conversation','callback_data':'cmd:new'}])
 navigation_reply(int(pairing['chatId']),'Personal conversations\nBrowsing never switches your destination.\n'+('Choose a conversation to review its status.' if rows else 'No personal conversations yet.'),{'inline_keyboard':buttons},message)


def chat_callback(data,pairing,origin,message):
 if data.startswith('chats:') and data[6:].isdigit() and len(data)<16:
  show_chats(pairing,origin,message,int(data[6:]));return
 prefix,_,cid=data.partition(':')
 if prefix not in ('chat','go') or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',cid):raise BridgeError('Unavailable conversation control.')
 row=next((r for r in own_chats(pairing) if r['id']==cid),None)
 if not row:raise BridgeError('This conversation is unavailable. Nothing was switched.')
 if prefix=='go':
  if sync_question_state(origin):raise BridgeError('Answer the current question before switching conversations.')
  storage_put('conversation.json',{'chatId':cid,'createdAt':row.get('created_at') or now()})
  navigation_reply(int(pairing['chatId']),'Personal · Your next message goes to '+str(row.get('title') or 'Conversation'),command_markup(origin,cid),message);return
 buttons=[[{'text':'Continue here','callback_data':'go:'+cid}]]
 if origin:buttons.append([{'text':'Open in Möbius','url':f'{origin}/shell/?chat={urllib.parse.quote(cid,safe="")}'}])
 buttons.append([{'text':'‹ Conversations','callback_data':'chats:0'}])
 text=str(row.get('title') or 'Conversation')+'\n'+('Waiting for your answer' if row.get('pending_question_id') else 'Working' if row.get('running') else 'Ready to continue')
 navigation_reply(int(pairing['chatId']),text+'\nNo transcript preview is exposed. Review or Continue here.',{'inline_keyboard':buttons},message)


def normalize_questions(value):
 if not isinstance(value,list) or not 1<=len(value)<=6:return []
 output=[]
 for q in value:
  if not isinstance(q,dict) or not isinstance(q.get('id'),str) or not q['id'] or not isinstance(q.get('question'),str):return []
  opts=q.get('options')
  if not isinstance(opts,list) or not 1<=len(opts)<=10:return []
  if any(not isinstance(o,dict) or not isinstance(o.get('label'),str) or not o['label'] for o in opts):return []
  # Preserve canonical ids, prompts and labels exactly. UI labels alone truncate.
  output.append({**q,'options':[dict(o) for o in opts]})
 if len({q['id'] for q in output})!=len(output):return []
 return output


def question_guard(state,pairing):
 if int(state.get('telegramChatId') or 0)!=int(pairing['chatId']) or state.get('pairingBinding')!=hashlib.sha256(json.dumps(pairing,sort_keys=True).encode()).hexdigest():
  raise BridgeError('Question pairing changed. Answer in Möbius.')
 if not any(r['id']==state.get('mobiusChatId') for r in own_chats(pairing)):raise BridgeError('Question conversation is unavailable.')


def edit_question_message(state,public_origin,*,answered=None):
 if state.get('telegramMessageId'):
  telegram('editMessageText',{'chat_id':state['telegramChatId'],'message_id':state['telegramMessageId'],
   'text':question_text(state,answered=answered),'reply_markup':{'inline_keyboard':[]} if answered else question_markup(state,public_origin)})


def retire_question_state(state,public_origin,label):
 try:
  telegram('editMessageText',{'chat_id':state['telegramChatId'],'message_id':state['telegramMessageId'],
   'text':question_text(state)+'\n\n'+label,'reply_markup':{'inline_keyboard':[]}})
 except (BridgeError,KeyError):pass
 clear_question_state()


def sync_question_state(public_origin):
 pairing=storage_get('pairing.json')
 state=storage_get(QUESTION_STATE_PATH)
 if not isinstance(pairing,dict):raise BridgeError('Private owner pairing unavailable.')
 rows=own_chats(pairing)
 current_id=(storage_get('conversation.json') or {}).get('chatId')
 # A canonical pending card can exist without a Telegram card after restart or
 # failed delivery. It still blocks /new, model and routing; never guess empty.
 if not isinstance(state,dict):
  row=next((r for r in rows if r['id']==current_id),None)
  if row and row.get('pending_question_id'):
   return {'mobiusChatId':current_id,'questionId':row['pending_question_id'],'external':True}
  return None
 question_guard(state,pairing)
 row=next((r for r in rows if r['id']==state['mobiusChatId']),None)
 if not row or row.get('pending_question_id')!=state.get('questionId'):
  retire_question_state(state,public_origin,'This question is no longer active.')
  selected=next((r for r in rows if r['id']==current_id),None)
  if selected and selected.get('pending_question_id'):return {'mobiusChatId':current_id,'questionId':selected['pending_question_id'],'external':True}
  return None
 return state


def publish_question(telegram_chat_id,mobius_chat_id,result,public_origin,*,reply_to_message_id=None):
 qs=normalize_questions(result.get('questions'));pair=storage_get('pairing.json')
 if not qs or not isinstance(pair,dict) or result.get('secure') or result.get('ownerOnly'):return False
 # Canonical card fields are never rewritten into a different saved question.
 # A private-media card must be answered in its authenticated Möbius view.
 canonical=json.dumps(qs,ensure_ascii=False)
 if clean_text(canonical)!=canonical:return False
 state={'nonce':secrets.token_urlsafe(6),'questionId':result.get('questionId'),'mobiusChatId':mobius_chat_id,
  'telegramChatId':telegram_chat_id,'questions':qs,'selections':{},'createdAt':now(),'leadText':clean_text(result.get('text') or '')[:1000],
  'baselineText':clean_text(result.get('baselineText') or ''), 'pairingBinding':hashlib.sha256(json.dumps(pair,sort_keys=True).encode()).hexdigest()}
 question_guard(state,pair)
 row=next(r for r in own_chats(pair) if r['id']==mobius_chat_id)
 if row.get('pending_question_id')!=state['questionId'] or len(question_text(state))>3700:return False
 # Reserve the card before delivery so a crash never silently republishes it.
 storage_put(QUESTION_STATE_PATH,state)
 sent=send_text(telegram_chat_id,question_text(state),reply_markup=question_markup(state,public_origin),reply_to_message_id=reply_to_message_id)
 if not isinstance(sent,dict) or not sent.get('message_id'):return False
 state['telegramMessageId']=sent['message_id'];storage_put(QUESTION_STATE_PATH,state);return True


def submit_question_state(state,pairing,public_origin):
 question_guard(state,pairing)
 if sync_question_state(public_origin)!=state:raise BridgeError('Question changed. Answer in Möbius.')
 selections=state.get('selections') or {};answers={};typed={}
 for i,q in enumerate(state['questions']):
  v=selections.get(str(i))
  if not v:return False
  labels=v if isinstance(v,list) else [v]
  answers[q['id']]=', '.join(labels)
  ids=(state.get('selectedOptions') or {}).get(q['id'])
  if ids:typed[q['id']]=list(ids)
 cid=message_cid('telegram-answer')
 attempts=storage_get('telegram-answer-attempts.json') or {};journal=attempts.get(cid)
 if journal and journal.get('cid')==cid:
  send_text(int(pairing['chatId']),'Your answer delivery needs review in Möbius; it was not submitted again.',reply_markup=open_chat_markup(public_origin,state['mobiusChatId']));return True
 if len(attempts)>=2000:raise BridgeError('Answer receipt limit reached. Review in Möbius before continuing.')
 attempts[cid]={'cid':cid,'questionId':state['questionId'],'chatId':state['mobiusChatId'],'state':'uncertain'}
 storage_put('telegram-answer-attempts.json',attempts)
 try:
  submitted=request_json(f"/api/chats/{state['mobiusChatId']}/messages",method='POST',body={'content':'Answering the saved card.','hidden':True,'question_id':state['questionId'],'answers':answers,'selected_options':typed or None,'cid':cid})
 except BridgeError as exc:
  # 409 can mean secure input, invalid answer, or a still-open claim conflict.
  # Preserve the card and show a safe redirect, never stale-retire or retry.
  send_text(int(pairing['chatId']),'The answer was not confirmed. Review this card in Möbius before retrying.',reply_markup=open_chat_markup(public_origin,state['mobiusChatId']));return True
 clear_question_state()
 attempts[cid]={'cid':cid,'questionId':state['questionId'],'chatId':state['mobiusChatId'],'state':'accepted'}
 storage_put('telegram-answer-attempts.json',attempts)
 try:edit_question_message(state,public_origin,answered={str(i):answers[q['id']] for i,q in enumerate(state['questions'])})
 except BridgeError:pass
 # queued is not a completed answer and must not consume another turn's stream.
 if submitted.get('status') in ('queued','duplicate') or submitted.get('answer_turn') in ('none','retry','queued'):
  send_text(int(pairing['chatId']),'Answer accepted. Check progress and the result in Möbius.',reply_markup=open_chat_markup(public_origin,state['mobiusChatId']));return True
 result=read_agent_stream(state['mobiusChatId'],int(pairing['chatId']),baseline_text=str(state.get('baselineText') or ''))
 deliver_agent_result(pairing,state['mobiusChatId'],result,public_origin);return True


_MEDIA=re.compile(r'(?:!\[[^\]]*\]\()?/api/chats/[A-Za-z0-9_-]+/media/[^\s)]+\)?')
def clean_text(text):
 return _MEDIA.sub('[Private media is available in Möbius.]',str(text))


def thinking_indicator(telegram_chat_id,interval=1):
 draft_id=secrets.randbelow(2_147_483_647)+1
 def send_draft(text):
  try:telegram('sendMessageDraft',{'chat_id':telegram_chat_id,'draft_id':draft_id,'text':clean_text(text)[-3900:]})
  except BridgeError:pass
 def send_thinking(elapsed):
  try:telegram('sendChatAction',{'chat_id':telegram_chat_id,'action':'typing'})
  except BridgeError:pass
 return ReplyProgress(send_draft,send_thinking,interval=interval)


def read_agent_stream(chat_id,telegram_chat_id,*,baseline_text=''):
 # Public replay-safe event-log mode, not unsupported query snapshot/reader.
 req=urllib.request.Request(API_BASE+f'/api/chats/{chat_id}/stream',headers=AUTH)
 items=[];deadline=time.monotonic()+AGENT_TIMEOUT
 with thinking_indicator(telegram_chat_id) as progress:
  try:
   opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
   with opener.open(req,timeout=AGENT_TIMEOUT+20) as response:
    if response.status==204:return {'kind':'pending','text':'Work is accepted. Check the result in Möbius.'}
    for raw in response:
     if len(raw)>256*1024:raise BridgeError('Reply event exceeded its bound.')
     if time.monotonic()>deadline:return {'kind':'pending','text':'Möbius is still working. Check progress there.'}
     if not raw.startswith(b'data: '):continue
     try:event=json.loads(raw[6:])
     except ValueError:continue
     kind=event.get('type')
     if kind=='text':append_stream_text(items,str(event.get('content') or ''),event.get('text_item_id'))
     elif kind=='text_final':finalize_stream_text(items,str(event.get('content') or ''),event.get('text_item_id'))
     if kind in ('text','text_final'):progress.show(clean_text(after_baseline(stream_text(items),baseline_text)))
     if kind=='question':
      return {'kind':'question','questionId':event.get('question_id'),'questions':event.get('questions'),'text':after_baseline(stream_text(items),baseline_text),'baselineText':stream_text(items),'secure':event.get('secure_input') or event.get('secure'),'ownerOnly':event.get('owner_action') or event.get('approval') or event.get('platform_action') or event.get('action_key') or any(q.get('id')=='approval' for q in event.get('questions',[]) if isinstance(q,dict))}
     if kind=='done':return {'kind':'reply','text':after_baseline(stream_text(items),baseline_text) or 'Möbius completed the turn without a text reply.'}
    return {'kind':'pending','text':'The reply stream ended before completion. Do not resubmit automatically; open Möbius.'}
  except (OSError,urllib.error.HTTPError):return {'kind':'pending','text':'The reply could not be confirmed. Work may continue in Möbius; no request was repeated.'}


def deliver_agent_result(pairing,mobius_chat_id,result,public_origin,*,reply_to_message_id=None):
 if result.get('kind')=='question' and publish_question(int(pairing['chatId']),mobius_chat_id,result,public_origin,reply_to_message_id=reply_to_message_id):return
 if result.get('kind')=='question':
  text='Möbius needs an answer. Use its saved card there; trusted owner approvals and secure input are not Telegram controls.'
 else:text=clean_text(result.get('text') or 'Check the result in Möbius.')
 send_text(int(pairing['chatId']),text,reply_to_message_id=reply_to_message_id,
  reply_markup=open_chat_markup(public_origin,mobius_chat_id) if result.get('kind')!='reply' or '[Private media' in text else None)


def ask_mobius(pairing,text,public_origin,*,reply_to_message_id=None):
 if contains_bot_key(text):
  send_text(int(pairing['chatId']),'Do not send bot keys in Telegram. Use the saved secure-input form in your Möbius owner chat.');return
 cid=message_cid('telegram');attempts=storage_get('telegram-attempts.json') or {};journal=attempts.get(cid)
 if isinstance(journal,dict) and journal.get('cid')==cid:
  chat_id=journal['chatId']
  if not any(r['id']==chat_id for r in own_chats(pairing)):raise BridgeError('Accepted conversation unavailable. Nothing was rerouted.')
  # Public core has no bounded completed-result recovery reader for app auth.
  send_text(int(pairing['chatId']),'Your earlier request may already be accepted. It was not resubmitted. Check its result in Möbius.',reply_markup=open_chat_markup(public_origin,chat_id));return
 chat_id=ensure_conversation(pairing)
 if len(attempts)>=2000:raise BridgeError('Request receipt limit reached. Review in Möbius before continuing.')
 attempts[cid]={'cid':cid,'chatId':chat_id,'state':'uncertain'}
 storage_put('telegram-attempts.json',attempts)
 submitted=request_json(f'/api/chats/{chat_id}/messages',method='POST',body={'content':text[:12000],'cid':cid})
 attempts[cid]={'cid':cid,'chatId':chat_id,'state':'accepted'}
 storage_put('telegram-attempts.json',attempts)
 mark_timing('submitted_ms')
 if not isinstance(submitted,dict):
  send_text(int(pairing['chatId']),'The submission result is unknown. Check this conversation in Möbius before retrying.',reply_markup=open_chat_markup(public_origin,chat_id));return
 if submitted.get('status') in ('queued','duplicate'):
  send_text(int(pairing['chatId']),'Request accepted. Follow progress and the result in Möbius.',reply_markup=open_chat_markup(public_origin,chat_id));return
 result=read_agent_stream(chat_id,int(pairing['chatId']))
 deliver_agent_result(pairing,chat_id,result,public_origin,reply_to_message_id=reply_to_message_id)


def sync_bot_commands(pairing,runtime,bot_username,public_origin=''):
 paired=int((pairing or {}).get('chatId') or 0)
 if runtime.get('botCommandContract')==1 and runtime.get('botCommandChatId')==paired and runtime.get('botCommandUsername')==bot_username:return False
 telegram('setMyCommands',{'commands':[{'command':'start','description':'Pair or show help'},{'command':'pair','description':'Pair this private chat'}],'scope':{'type':'default'}})
 old=int(runtime.get('botCommandChatId') or 0)
 if old and old!=paired:telegram('deleteMyCommands',{'scope':{'type':'chat','chat_id':old}})
 if paired:
  telegram('setMyCommands',{'commands':[{'command':c,'description':d} for c,d in [('menu','Conversations and model'),('chats','Conversations'),('bots','Optional bot shortcuts'),('model','Choose model'),('new','New conversation'),('status','Current status'),('bridge','Open Bridge in Möbius')]],'scope':{'type':'chat','chat_id':paired}})
  telegram('setChatMenuButton',{'chat_id':paired,'menu_button':{'type':'commands'}})
 runtime.update(botCommandContract=1,botCommandChatId=paired,botCommandUsername=bot_username);return True


def acknowledge_received_callback(update,pairing):
 cb=update.get('callback_query') or {};chat=(cb.get('message') or {}).get('chat') or {}
 if not pairing or chat.get('type')!='private' or chat.get('id')!=pairing.get('chatId') or (cb.get('from') or {}).get('id')!=pairing.get('userId'):return False
 try:telegram('answerCallbackQuery',{'callback_query_id':cb['id']});return True
 except BridgeError:return False


def dispatch_update(update,settings,pairing,public_origin):
 _update_context.update=update;_update_context.timing={'started':time.monotonic()}
 try:
  if settings.get('enabled') is False:return pairing
  return handle_update(update,settings,pairing,public_origin)
 except BridgeError:
  activity('A Telegram operation needs review in Möbius.','warn')
  return pairing
 finally:_update_context.update=None;_update_context.timing=None


def main():
 global API_BASE
 safe_origin(API_BASE)
 settings=storage_get('settings.json')
 if not isinstance(settings,dict) or settings.get('enabled') is not True:
  set_status('paused','Bridge paused','Enable after secure setup and private pairing.');return 0
 ensure_storage_null(QUESTION_STATE_PATH)
 try:bot=bot_identity(telegram('getMe'));hook=telegram('getWebhookInfo')
 except (TelegramError,BridgeError):
  set_status('needs_token','Check secure setup','The dedicated bot key or Telegram connection is unavailable.');return 0
 identity=storage_get('bot-identity.json')
 if not isinstance(identity,dict) or identity.get('id')!=bot['id']:
  set_status('identity_changed','Bot identity needs review','Run secure setup for this dedicated installation before listening.');return 0
 if not isinstance(hook,dict) or hook.get('url'):
  set_status('webhook_conflict','Bot connected elsewhere','Remove its webhook in the previous service; Bridge does not change it.');return 0
 context=request_json(f'/api/apps/{APP_ID}/job-context')
 origin=str(context.get('public_origin') or '').rstrip('/')
 if origin:
  try:safe_origin(origin)
  except TelegramError:origin=''
 context['public_origin']=origin
 pairing=storage_get('pairing.json');pairing=pairing if isinstance(pairing,dict) else None
 runtime=storage_get('bridge-runtime.json');runtime=runtime if isinstance(runtime,dict) else {}
 try:
  if sync_bot_commands(pairing,runtime,bot['username'],origin):storage_put('bridge-runtime.json',runtime)
 except BridgeError:pass
 set_status('connected','Connected','Listening only for the paired private owner.',botUsername=bot['username'])
 if pairing:sync_question_state(origin)
 return run_listener(SimpleNamespace(**globals()),runtime,context,bot['username'])

if __name__=='__main__':
 try:raise SystemExit(main())
 except Exception:
  # No traceback: urllib exceptions can contain a token-bearing URL.
  try:set_status('error','Bridge stopped','Review connection status in Möbius; no automatic request replay.')
  except Exception:pass
  raise SystemExit(1)
