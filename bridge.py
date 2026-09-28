#!/usr/bin/env python3
"""Scoped Telegram long-poll bridge for one Möbius app.

The supervised job reads only its declared bot key and handles Telegram here.
The browser never receives the key or raw Telegram responses.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from types import SimpleNamespace
from bridge_loop import run_listener
from bridge_progress import ReplyProgress
import bridge_assistants
import bridge_access
import telegram_http
from datetime import UTC, datetime


APP_ID = int(sys.argv[1])
APP_TOKEN = os.environ["APP_TOKEN"]
API_BASE = os.environ.get("API_BASE_URL", "http://localhost:8000").rstrip("/")
AUTH = {"Authorization": f"Bearer {APP_TOKEN}"}
# Keep listening across cron ticks. The supervisor owns the single-flight lock;
# this bounded session renews well inside its two-hour app credential lifetime.
RUN_SECONDS = 30 * 60
MAINTENANCE_SECONDS = 60
AGENT_TIMEOUT = 12 * 60
BOT_COMMANDS_VERSION = 5
SETUP_COMMANDS = [
  {"command": "start", "description": "Pair or show help"},
  {"command": "pair", "description": "Pair this private chat"},
  {"command": "help", "description": "Show available commands"},
]
PAIRED_COMMANDS = [
  {"command":"chats","description":"Chats"},
  {"command":"bots","description":"My bots"},
  {"command":"settings","description":"Settings"},
  {"command":"help","description":"Home"},
]
TELEGRAM_SYSTEM_PROMPT = (
  "This conversation is being used through a text-first Telegram chat. "
  "Reply concisely in plain text with simple formatting. When a material "
  "choice needs an owner answer, use the platform saved request_question or "
  "request_approval card as the final action; the bridge renders its options as "
  "Telegram buttons. Do not ask blocking questions only in prose. Do not create widgets, rich "
  "proposal previews, or other interface-only artifacts just to communicate; "
  "Telegram cannot render them. Use only the tools genuinely needed to "
  "complete the request. App-building requests may still use the necessary "
  "build and verification tools. Open completed visual work in Möbius. "
  "Generated images stay in this Möbius conversation; Bridge sends an authenticated-view link instead of image files. This Store edition has no direct whole-shell screenshot shortcut."
)
QUESTION_STATE_PATH = "telegram-question.json"
MODEL_STATE_PATH = "model.json"
PROVIDER_LABELS = {
  "mobius": "Möbius",
  "claude": "Claude",
  "codex": "Codex",
}


class BridgeError(RuntimeError):
  def __init__(self, message: str, *, status: int | None = None, reason: str = ""):
    super().__init__(message)
    self.status = status
    self.reason = reason


def now() -> str:
  return datetime.now(UTC).isoformat()


def request_json(
  path: str,
  *,
  method: str = "GET",
  body: object | None = None,
  timeout: float = 20,
  headers: dict[str, str] | None = None,
) -> object:
  data = None
  merged = dict(AUTH)
  if headers:
    merged.update(headers)
  if body is not None:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    merged["Content-Type"] = "application/json"
  req = urllib.request.Request(
    API_BASE + path, data=data, method=method, headers=merged,
  )
  try:
    with urllib.request.urlopen(req, timeout=timeout) as response:
      raw = response.read()
      if not raw:
        return {}
      return json.loads(raw)
  except urllib.error.HTTPError as exc:
    try:
      payload = json.loads(exc.read())
      detail = payload.get("detail") if isinstance(payload, dict) else None
    except Exception:
      detail = None
    raise BridgeError(str(detail or f"Möbius request failed ({exc.code})"), status=exc.code)
  except (OSError, ValueError) as exc:
    raise BridgeError("Möbius is temporarily unavailable") from exc


def storage_get(path: str) -> object | None:
  try:
    return request_json(f"/api/storage/apps/{APP_ID}/{path}")
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


def telegram(method: str, params: dict[str, object] | None = None) -> object:
  try:
    return telegram_http.call_saved('bot-token', method, params,
      app_id=APP_ID, bearer=APP_TOKEN, api_base=API_BASE)
  except telegram_http.TelegramError as exc:
    raise BridgeError(str(exc), status=exc.code or None, reason=exc.reason) from None


_status_lock = threading.RLock()


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


def sync_bot_commands(
  pairing: dict | None,
  runtime: dict,
  bot_username: str | None,
) -> bool:
  """Keep Telegram's native command menu aligned with pairing state."""
  paired_chat_id = int(pairing.get("chatId") or 0) if pairing else 0
  previous_chat_id = int(runtime.get("botCommandChatId") or 0)
  if (
    int(runtime.get("botCommandContract") or 0) == BOT_COMMANDS_VERSION
    and previous_chat_id == paired_chat_id
    and str(runtime.get("botCommandUsername") or "") == str(bot_username or "")
  ):
    return False

  telegram("setMyCommands", {
    "commands": SETUP_COMMANDS,
    "scope": {"type": "default"},
  })
  if previous_chat_id and previous_chat_id != paired_chat_id:
    telegram("deleteMyCommands", {
      "scope": {"type": "chat", "chat_id": previous_chat_id},
    })
  if paired_chat_id:
    scope = {"type": "chat", "chat_id": paired_chat_id}
    telegram("setMyCommands", {
      "commands": PAIRED_COMMANDS,
      "scope": scope,
    })
    telegram("setChatMenuButton", {
      "chat_id": paired_chat_id,
      "menu_button": {"type": "commands"},
    })

  runtime["botCommandContract"] = BOT_COMMANDS_VERSION
  runtime["botCommandChatId"] = paired_chat_id or None
  runtime["botCommandUsername"] = bot_username or None
  runtime["botCommandsUpdatedAt"] = now()
  return True


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


def ensure_conversation(pairing: dict) -> str:
  saved = storage_get("conversation.json")
  if isinstance(saved, dict) and saved.get("chatId"):
    if saved.get("connectionId"):
      raise BridgeError("This Store edition cannot continue external chats. Choose a Bridge conversation in Chats.", status=403)
    return str(saved["chatId"])
  body: dict[str, object] = {
    "title": conversation_title(pairing),
    "scope": f"telegram:{pairing['chatId']}",
    "scope_label": pairing.get("displayName") or "Telegram",
    "owner_visible": True,
    "system_prompt": TELEGRAM_SYSTEM_PROMPT,
  }
  model_choice = storage_get(MODEL_STATE_PATH)
  if isinstance(model_choice, dict):
    model = str(model_choice.get("model") or "").strip()
    provider = str(model_choice.get("provider") or "").strip()
    if model and provider in PROVIDER_LABELS:
      body["model"] = model
      body["provider"] = provider
  created = request_json(
    "/api/app-chats",
    method="POST",
    body=body,
  )
  chat_id = str(created["id"])
  storage_put("conversation.json", {"chatId": chat_id, "createdAt": now()})
  return chat_id


def normalize_questions(value: object) -> list[dict]:
  if not isinstance(value, list):
    return []
  questions: list[dict] = []
  for raw in value[:3]:
    if not isinstance(raw, dict):
      continue
    prompt = str(raw.get("question") or "").strip()
    if not prompt:
      continue
    options: list[dict] = []
    for raw_option in (raw.get("options") or [])[:3]:
      if isinstance(raw_option, dict):
        label = str(raw_option.get("label") or "").strip()
        description = str(raw_option.get("description") or "").strip()
      else:
        label = str(raw_option or "").strip()
        description = ""
      if label:
        options.append({"label": label[:80], "description": description[:100]})
    if not options:
      continue
    questions.append({
      "header": str(raw.get("header") or "").strip()[:80],
      "question": prompt[:320],
      "multiSelect": bool(raw.get("multiSelect")),
      "options": options,
    })
  return questions


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


def edit_question_message(state: dict, public_origin: str, *, answered=None) -> None:
  message_id = state.get("telegramMessageId")
  if not message_id:
    return
  markup = (
    {"inline_keyboard": []}
    if answered else question_markup(state, public_origin)
  )
  telegram("editMessageText", {
    "chat_id": state["telegramChatId"],
    "message_id": message_id,
    "text": question_text(state, answered=answered),
    "reply_markup": markup or {"inline_keyboard": []},
  })


def publish_question(
  telegram_chat_id: int,
  mobius_chat_id: str,
  result: dict,
  public_origin: str,
  *,
  reply_to_message_id: int | None = None,
) -> bool:
  questions = normalize_questions(result.get("questions"))
  question_id = str(result.get("questionId") or "")
  if not questions or not question_id:
    return False
  state = {
    "nonce": secrets.token_urlsafe(6),
    "questionId": question_id,
    "mobiusChatId": mobius_chat_id,
    "telegramChatId": telegram_chat_id,
    "questions": questions,
    "selections": {},
    "leadText": str(result.get("text") or "").strip()[:1000],
    "baselineText": str(result.get("baselineText") or "").strip(),
    "createdAt": now(),
  }
  sent = send_text(
    telegram_chat_id,
    question_text(state),
    reply_markup=question_markup(state, public_origin),
    reply_to_message_id=reply_to_message_id,
  )
  if not isinstance(sent, dict) or not sent.get("message_id"):
    return False
  state["telegramMessageId"] = sent["message_id"]
  storage_put(QUESTION_STATE_PATH, state)
  return True


def retire_question_state(state: dict, public_origin: str, label: str) -> None:
  try:
    telegram("editMessageText", {
      "chat_id": state["telegramChatId"],
      "message_id": state["telegramMessageId"],
      "text": question_text(state) + f"\n\n{label}",
      "reply_markup": {"inline_keyboard": []},
    })
  except (BridgeError, KeyError):
    pass
  clear_question_state()


def sync_question_state(public_origin: str) -> dict | None:
  """Return the pending question only while Möbius still considers it active.

  Question state can change while a long poll is already running (for example,
  when the owner answers in Möbius).  Callers handling a Telegram update must
  use this result instead of trusting the cached storage record.
  """
  state = storage_get(QUESTION_STATE_PATH)
  if not isinstance(state, dict):
    return None
  chats = request_json("/api/app-chats")
  if not isinstance(chats, list):
    return state
  current = next(
    (
      chat for chat in chats
      if isinstance(chat, dict)
      and str(chat.get("id") or "") == str(state.get("mobiusChatId") or "")
    ),
    None,
  )
  # Older running backends do not expose this field. Leave the question alone
  # until the committed status contract is activated by the approved restart.
  if isinstance(current, dict) and "pending_question_id" not in current:
    return state
  if (
    current is None
    or str(current.get("pending_question_id") or "")
    != str(state.get("questionId") or "")
  ):
    retire_question_state(state, public_origin, "This question is no longer active.")
    return None
  return state


_MEDIA_EMBED_RE = re.compile(r"!\[[^\]]*\]\(/api/[^)]+\)")


def text_reply(reply: str) -> tuple[str, bool]:
  """Keep generated visuals in the authenticated chat, never mint media grants."""
  clean, images = _MEDIA_EMBED_RE.subn("", reply)
  return re.sub(r"\n{3,}", "\n\n", clean).strip(), bool(images)


def navigation_origin(settings: dict) -> str:
  """App-owned navigation only. Never used for credentialed requests."""
  value = settings.get("mobiusAddress", "")
  if not isinstance(value, str) or any(ord(c) < 32 for c in value):
    return ""
  value = value.strip()
  try:
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or parsed.path not in ("", "/")
        or parsed.query or parsed.fragment or "\\" in value
        or any(c.isspace() for c in value) or parsed.port == 0):
      return ""
  except ValueError:
    return ""
  return urllib.parse.urlunsplit(("https", parsed.netloc, "", "", ""))


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


_thinking_draft_mode = "rich"


def send_thinking_draft(
  telegram_chat_id: int,
  draft_id: int,
  elapsed_seconds: int,
) -> None:
  """Show Telegram's native temporary Thinking message for AI bots."""
  global _thinking_draft_mode
  label = f"Thinking {max(0, elapsed_seconds)}s"
  if _thinking_draft_mode == "rich":
    try:
      telegram("sendRichMessageDraft", {
        "chat_id": telegram_chat_id,
        "draft_id": draft_id,
        "rich_message": {
          "blocks": [{"type": "thinking", "text": label}],
        },
      })
      return
    except BridgeError as exc:
      if exc.status in {400, 404}:
        _thinking_draft_mode = "plain"

  if _thinking_draft_mode in {"rich", "plain"}:
    try:
      telegram("sendMessageDraft", {
        "chat_id": telegram_chat_id,
        "draft_id": draft_id,
        "text": label,
      })
      return
    except BridgeError as exc:
      if exc.status in {400, 404}:
        _thinking_draft_mode = "typing"

  try:
    telegram("sendChatAction", {
      "chat_id": telegram_chat_id,
      "action": "typing",
    })
  except BridgeError:
    # The response itself is more important than a cosmetic activity hint.
    pass


def thinking_indicator(telegram_chat_id: int, interval: float = 1):
  draft_id = secrets.randbelow(2_147_483_647) + 1
  timing = getattr(_update_context, "timing", None)
  draft_available = True

  def text_draft(text):
    nonlocal draft_available
    if not draft_available:
      return
    try:
      telegram("sendMessageDraft", {
        "chat_id": telegram_chat_id, "draft_id": draft_id, "text": text,
      })
      if isinstance(timing, dict) and "first_draft_ms" not in timing:
        timing["first_draft_ms"] = round((time.monotonic() - timing["started"]) * 1000, 1)
    except BridgeError as exc:
      if exc.status in {400, 404}:
        draft_available = False
      # Drafts are optional. Durable final replies never depend on them.
      pass

  return ReplyProgress(text_draft,
                       lambda elapsed: send_thinking_draft(telegram_chat_id, draft_id, elapsed),
                       interval=interval)


def _read_agent_stream(
  chat_id: str,
  telegram_chat_id: int,
  *,
  baseline_text: str = "",
  progress=None,
) -> dict:
  deadline = time.monotonic() + AGENT_TIMEOUT
  items: list[dict] = []
  error = None
  while time.monotonic() < deadline:
    req = urllib.request.Request(
      f"{API_BASE}/api/chats/{chat_id}/stream?snapshot=1", headers=AUTH,
    )
    try:
      with urllib.request.urlopen(req, timeout=AGENT_TIMEOUT + 20) as response:
        if response.status == 204:
          time.sleep(0.25)
          continue
        for raw in response:
          line = raw.decode("utf-8", "replace").strip()
          if not line.startswith("data: "):
            continue
          try:
            event = json.loads(line[6:])
          except ValueError:
            continue
          kind = event.get("type")
          if kind == "stream_snapshot" and isinstance(event.get("items"), list):
            items = [item for item in event["items"] if isinstance(item, dict)]
          elif kind == "text":
            append_stream_text(items, str(event.get("content") or ""), event.get("text_item_id"))
          elif kind == "text_final":
            finalize_stream_text(items, str(event.get("content") or ""), event.get("text_item_id"))
          if kind in {"stream_snapshot", "text", "text_final"}:
            current_text = after_baseline(stream_text(items), baseline_text)
            if current_text:
              mark_timing("first_text_ms", once=True)
              if progress is not None:
                # Do not expose raw private media URLs in transient drafts.
                progress.show(text_reply(current_text)[0])
          if kind == "error":
            error = str(event.get("message") or "Möbius could not complete that request.")
          elif kind == "question":
            complete_text = stream_text(items)
            return {
              "kind": "question",
              "text": after_baseline(complete_text, baseline_text),
              "baselineText": complete_text,
              "questionId": event.get("question_id"),
              "questions": event.get("questions"),
            }
          elif kind == "done":
            mark_timing("stream_done_ms")
            answer = after_baseline(stream_text(items), baseline_text)
            return {
              "kind": "reply",
              "text": answer or error or "Möbius completed the turn without a text reply.",
            }
        return {
          "kind": "reply",
          "text": error or "The Möbius response stream ended early. Please try again.",
        }
    except urllib.error.HTTPError as exc:
      raise BridgeError(f"Could not read the Möbius reply ({exc.code})")
    except OSError as exc:
      raise BridgeError("The Möbius reply stream was interrupted") from exc
  return {
    "kind": "reply",
    "text": "Möbius is still working on that request. Open the app to continue there.",
  }


def read_agent_stream(
  chat_id: str,
  telegram_chat_id: int,
  *,
  baseline_text: str = "",
) -> dict:
  with thinking_indicator(telegram_chat_id) as progress:
    return _read_agent_stream(
      chat_id,
      telegram_chat_id,
      baseline_text=baseline_text,
      progress=progress,
    )


def deliver_agent_result(
  pairing: dict,
  mobius_chat_id: str,
  result: dict,
  public_origin: str,
  *,
  reply_to_message_id: int | None = None,
) -> None:
  telegram_chat_id = int(pairing["chatId"])
  if result.get("kind") == "question":
    if publish_question(
      telegram_chat_id,
      mobius_chat_id,
      result,
      public_origin,
      reply_to_message_id=reply_to_message_id,
    ):
      activity("Asked a question in Telegram", "good")
      return
    send_text(
      telegram_chat_id,
      "Möbius needs an answer. Open this conversation in Möbius to continue.",
      reply_markup=open_chat_markup(public_origin, mobius_chat_id),
      reply_to_message_id=reply_to_message_id,
    )
    activity("A Telegram question needed Möbius", "warn")
    return
  reply = str(result.get("text") or "")
  clean_reply, has_images = text_reply(reply)
  if has_images:
    hint = "Open this conversation in Möbius to view the images."
    if not public_origin:
      hint += " Add your Möbius address in Bridge settings to enable the link."
    clean_reply = (clean_reply + "\n\n" + hint).strip()
  send_text(
    telegram_chat_id,
    clean_reply or "Done.",
    reply_markup=open_chat_markup(public_origin, mobius_chat_id) if has_images else None,
    reply_to_message_id=reply_to_message_id,
  )
  mark_timing("delivered_ms")
  activity("Replied to a Telegram message", "good")


def recover_completed_reply(chat_id, cid):
  """Recover a completed accepted message without re-running the agent."""
  chat = request_json(f"/api/chats/{chat_id}?limit=100")
  found = False
  texts = []
  for row in chat.get("messages", []):
    if row.get("role") == "user":
      if found:
        break
      found = row.get("cid") == cid
    elif found and row.get("role") == "assistant" and row.get("content"):
      texts.append(str(row["content"]))
  return {"kind": "reply", "text": "\n\n".join(texts) or
          "Your earlier request was already accepted. Open this conversation in Möbius to see its result."}


def ask_mobius(
  pairing: dict,
  text: str,
  public_origin: str,
  *,
  reply_to_message_id: int | None = None,
) -> None:
  telegram_chat_id = int(pairing["chatId"])
  cid = message_cid("telegram")
  journal = storage_get("telegram-delivery.json")
  chat_id = (str(journal["chatId"]) if isinstance(journal, dict)
             and journal.get("cid") == cid and journal.get("chatId")
             else ensure_conversation(pairing))
  if isinstance(journal, dict) and journal.get('cid') == cid and journal.get('connectionId'):
    raise BridgeError("Continue this earlier request in Möbius.", status=403)
  storage_put("telegram-delivery.json", {"cid": cid, "chatId": chat_id})
  mark_timing("conversation_ready_ms")
  submitted = request_json(
    f"/api/chats/{chat_id}/messages",
    method="POST",
    body={"content": text[:12000]+"\n\n"+bridge_assistants.CONTEXT, "cid": cid},
  )
  mark_timing("submitted_ms")
  if isinstance(submitted, dict) and submitted.get("status") == "duplicate" and not submitted.get("running"):
    result = recover_completed_reply(chat_id, cid)
  else:
    result = read_agent_stream(chat_id, telegram_chat_id)
  deliver_agent_result(
    pairing,
    chat_id,
    result,
    public_origin,
    reply_to_message_id=reply_to_message_id,
  )


def command_markup(public_origin: str, current_chat_id: str | None) -> dict:
  # Global navigation lives in Telegram's native menu, not repeated footers.
  rows=[]
  if public_origin:rows.append([{"text":"Open Möbius","url":f"{public_origin}/shell/"+(f"?chat={current_chat_id}" if current_chat_id else "")}])
  return {"inline_keyboard":rows}


OWNER_SETTINGS = 'Owner settings\nThese control your Möbius conversation. Manage specialist bots separately in My bots.'

def owner_home(pairing, public_origin, current_chat_id):
  text='Your Möbius\nType what you want to do. Use Telegram’s menu for Chats, My bots or Settings.'
  markup=command_markup(public_origin,current_chat_id)
  try:chats=request_json('/api/app-chats')
  except BridgeError:
    return text+'\n\nCurrent chat status is unavailable. Open Chats to check.',markup
  current=next((c for c in chats if isinstance(c,dict) and str(c.get('id'))==str(current_chat_id) and c.get('scope')==f"telegram:{pairing['chatId']}"),None) if isinstance(chats,list) else None
  if current:
    text+='\n\nCurrent chat: '+str(current.get('title') or 'Conversation')
    if current.get('pending_question_id'):
      text+='\nWaiting for your answer. Use the question buttons above or open it in Möbius.'
      if public_origin:markup['inline_keyboard']=[[{'text':'Answer in Möbius','url':f'{public_origin}/shell/?chat={current_chat_id}'}]]
  else:
    text+='\n\nChoose a conversation in Chats.'
  return text,markup

def navigation_reply(chat_id,text,markup,message=None):
  """A tap edits that message; only a definite missing edit gets a fresh reply."""
  if message and message.get('message_id'):
    try:
      telegram('editMessageText',{'chat_id':chat_id,'message_id':message['message_id'],'text':text,'reply_markup':markup})
      return
    except BridgeError as exc:
      if exc.reason == 'not-modified':return
      if exc.status != 400 or exc.reason != 'edit-unavailable':raise
  send_text(chat_id,text,reply_markup=markup)


def show_chats(pairing, public_origin, message=None, page=0):
  chats=request_json('/api/app-chats')
  chats=[c for c in chats if isinstance(c,dict) and c.get('scope')==f"telegram:{pairing['chatId']}"] if isinstance(chats,list) else []
  page=max(0,min(page,max(0,(len(chats)-1)//6)))
  current=(storage_get('conversation.json') or {}).get('chatId')
  rows=[[{'text':('✓ ' if c['id']==current else '')+str(c.get('title') or 'Conversation')[:50],'callback_data':'chat:'+str(c['id'])}] for c in chats[page*6:(page+1)*6]]
  nav=[]
  if page:nav.append({'text':'← Previous','callback_data':f'chats:{page-1}'})
  if (page+1)*6<len(chats):nav.append({'text':'Next →','callback_data':f'chats:{page+1}'})
  if nav:rows.append(nav)
  rows.append([{'text':'New chat','callback_data':'cmd:new'}])
  body={'chat_id':int(pairing['chatId']),'text':'Chats\n✓ marks your current conversation. Choose where your next message goes.','reply_markup':{'inline_keyboard':rows}}
  navigation_reply(body['chat_id'],body['text'],body['reply_markup'],message)


def settings_markup(public_origin, current_chat_id):
  rows=[[{"text":"Choose model","callback_data":"cmd:model"}]]
  if public_origin and current_chat_id:rows.append([{"text":"Open Möbius","url":f"{public_origin}/shell/?chat={current_chat_id}"}])
  return {"inline_keyboard":rows}


_model_cache = None
_model_cache_at = 0.0
_model_cache_lock = threading.Lock()


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
    prefs = request_json("/api/owner/model-prefs")
    if isinstance(prefs, dict) and isinstance(prefs.get("hidden_ids"), list):
      hidden = {str(item) for item in prefs["hidden_ids"]}
  except BridgeError:
    # Visibility preferences are optional; model availability is authoritative.
    pass
  result: dict[str, list[dict[str, str]]] = {}
  for provider in PROVIDER_LABELS:
    rows = providers.get(provider)
    if not isinstance(rows, list):
      continue
    models = []
    for row in rows:
      if not isinstance(row, dict) or row.get("available") is False:
        continue
      model = str(row.get("id") or "").strip()
      if not model or model in hidden:
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


def submit_question_state(
  state: dict,
  pairing: dict,
  public_origin: str,
) -> bool:
  answers = resolved_question_answers(state)
  if not answers:
    return False
  chat_id = str(state.get("mobiusChatId") or "")
  lines = [f"- {question}: {answer}" for question, answer in answers.items()]
  try:
    request_json(
      f"/api/chats/{chat_id}/messages",
      method="POST",
      body={
        "content": "\n".join(lines),
        "hidden": True,
        "answers": answers,
        "question_id": state.get("questionId"),
        "cid": message_cid("telegram-answer"),
      },
    )
  except BridgeError as exc:
    if exc.status in {404, 409, 410}:
      retire_question_state(
        state, public_origin, "This question is no longer active.",
      )
      send_text(
        int(pairing["chatId"]),
        "That question was already answered or stopped in Möbius.",
        reply_markup=open_chat_markup(public_origin, chat_id),
      )
      return True
    raise
  clear_question_state()
  indexed_answers = {
    str(index): answers.get(str(question.get("question") or ""), "")
    for index, question in enumerate(state.get("questions") or [])
  }
  try:
    edit_question_message(state, public_origin, answered=indexed_answers)
  except BridgeError:
    pass
  result = read_agent_stream(
    chat_id,
    int(pairing["chatId"]),
    baseline_text=str(state.get("baselineText") or ""),
  )
  deliver_agent_result(pairing, chat_id, result, public_origin)
  return True


def stale_callback(callback_id: str) -> None:
  answer_callback(
    callback_id, text="This question is no longer active.",
  )


_update_context = threading.local()


def acknowledge_received_callback(update: dict, pairing: dict | None) -> bool:
  callback = update.get("callback_query")
  if not isinstance(callback, dict) or not pairing:
    return False
  if (int((callback.get("from") or {}).get("id") or 0) != int(pairing.get("userId") or 0)
      or int(((callback.get("message") or {}).get("chat") or {}).get("id") or 0) != int(pairing.get("chatId") or 0)):
    return False
  try:
    telegram("answerCallbackQuery", {"callback_query_id": callback["id"]})
    return True
  except BridgeError:
    return False


def dispatch_update(update, settings, pairing, public_origin):
  _update_context.update = update
  _update_context.timing = {"started": time.monotonic()}
  try:
    return handle_update(update, settings, pairing, public_origin)
  except BridgeError as exc:
    if pairing:
      try:
        send_text(int(pairing["chatId"]), f"Bridge error: {str(exc)[:300]}")
      except BridgeError:
        pass
    activity("A Telegram message failed", "warn")
    return pairing
  finally:
    timing = dict(getattr(_update_context, "timing", {}))
    started = timing.pop("started", None)
    if started is not None and "submitted_ms" in timing:
      timing["finished_ms"] = round((time.monotonic() - started) * 1000, 1)
      timing["at"] = now()
      try:
        storage_put("latency.json", timing)
      except BridgeError:
        pass
    _update_context.update = None
    _update_context.timing = None


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
    or int(chat.get("id") or 0) != int(pairing.get("chatId") or 0)
  ):
    answer_callback(
      callback_id, text="This button is not paired to your chat.",
    )
    return pairing

  if data.startswith('chats:'):
    answer_callback(callback_id)
    page=data.split(':',1)[1]
    show_chats(pairing,public_origin,message,int(page) if page.isdigit() else 0)
    return pairing
  if data.startswith('chat:'):
    if sync_question_state(public_origin):
      answer_callback(callback_id,text='Answer the current question before switching chats.');return pairing
    identity=data.split(':',1)[1]
    chats=request_json('/api/app-chats')
    selected=next((c for c in chats if isinstance(c,dict) and str(c.get('id'))==identity and c.get('scope')==f"telegram:{pairing['chatId']}"),None) if isinstance(chats,list) else None
    if not selected:
      answer_callback(callback_id,text='This chat is unavailable. Open Chats again.');return pairing
    storage_put('conversation.json',{'chatId':identity,'createdAt':selected.get('created_at') or now()})
    answer_callback(callback_id)
    navigation_reply(int(pairing['chatId']),'Current chat: '+str(selected.get('title') or 'Conversation')+'\nYour next message goes here.',command_markup(public_origin,identity),message)
    return pairing

  if data in ('cmd:settings','cmd:home'):
    answer_callback(callback_id)
    conversation=storage_get('conversation.json') or {}
    markup=settings_markup(public_origin,conversation.get('chatId')) if data=='cmd:settings' else command_markup(public_origin,conversation.get('chatId'))
    if data=='cmd:settings':text=OWNER_SETTINGS
    else:text,markup=owner_home(pairing,public_origin,conversation.get('chatId'))
    navigation_reply(int(pairing['chatId']),text,markup,message)
    return pairing

  if data.startswith("ua:"):
    answer_callback(callback_id)
    bridge_access.callback(SimpleNamespace(**globals()), data, pairing, public_origin, message)
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
      "Fresh Möbius conversation ready.",
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
        f"Now using {option['label']}. A fresh Möbius conversation is ready.",
        {"inline_keyboard": rows},
      )
      activity(f"Changed Telegram model to {option['label']}", "good")
      return pairing
    stale_callback(callback_id)
    return pairing

  state = sync_question_state(public_origin)
  if not isinstance(state, dict):
    stale_callback(callback_id)
    return pairing
  parts = data.split(":")
  if len(parts) < 2 or parts[1] != str(state.get("nonce") or ""):
    stale_callback(callback_id)
    return pairing
  questions = state.get("questions") or []
  selections = state.get("selections") if isinstance(state.get("selections"), dict) else {}

  if parts[0] == "q" and len(parts) == 4:
    try:
      question_index, option_index = int(parts[2]), int(parts[3])
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
  state = sync_question_state(public_origin)
  if not isinstance(state, dict):
    return False
  text = str(message.get("text") or "").strip()
  awaiting = state.get("awaitingTextQuestion")
  if not isinstance(awaiting, int):
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
    if supplied and expected and hmac.compare_digest(supplied, expected):
      pairing = {
        "chatId": chat_id,
        "userId": user_id,
        "displayName": display_name(user),
        "username": user.get("username"),
        "pairedAt": now(),
      }
      storage_put("pairing.json", pairing)
      send_text(chat_id, "Paired securely. Send me a message and I’ll pass it to Möbius. Use /new for a fresh conversation or /help for commands.")
      activity("Telegram chat paired", "good")
    elif text.startswith(("/start", "/pair")):
      send_text(chat_id, "Open Telegram Bridge in Möbius and use the current pairing code shown there.")
    return pairing

  if chat_id != int(pairing.get("chatId") or 0) or user_id != int(pairing.get("userId") or 0):
    return pairing
  if not text:
    send_text(
      chat_id,
      "I can currently read text messages only. Send a text prompt or use /help for commands.",
      reply_to_message_id=message_id,
    )
    return pairing
  command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
  if command=="/chats":
    show_chats(pairing,public_origin)
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
      "Fresh Möbius conversation ready. It is now visible in your Möbius chat list.",
    )
    activity("Started a fresh Telegram conversation")
  elif command == "/settings":
    conversation=storage_get('conversation.json') or {}
    send_text(chat_id,OWNER_SETTINGS,reply_markup=settings_markup(public_origin,conversation.get('chatId')))
  elif command == "/model":
    send_model_picker(chat_id)
  elif command == "/status":
    conversation = storage_get("conversation.json")
    current_chat_id = (
      str(conversation.get("chatId") or "")
      if isinstance(conversation, dict) else ""
    )
    send_text(
      chat_id,
      "Telegram Bridge is connected and this private chat is paired.",
      reply_markup=command_markup(public_origin, current_chat_id),
    )
  elif command in {"/help", "/start"}:
    conversation = storage_get("conversation.json")
    current_chat_id = (
      str(conversation.get("chatId") or "")
      if isinstance(conversation, dict) else ""
    )
    text,markup=owner_home(pairing,public_origin,current_chat_id)
    send_text(chat_id,text,reply_markup=markup)
  elif bridge_assistants.input_reply(SimpleNamespace(**globals()), message, pairing, public_origin):
    pass
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


def main() -> int:
  settings = storage_get("settings.json")
  if not isinstance(settings, dict):
    set_status("waiting", "Open the app once", "Telegram Bridge needs its first-time pairing code.")
    return 0
  if settings.get("enabled") is False:
    set_status("paused", "Bridge paused", "Resume it in the app when you want Telegram messages handled.")
    return 0

  # Optional question state is read during each paired poll. Create the empty
  # record once rather than treating its expected absence as a recurring 404.
  ensure_storage_null(QUESTION_STATE_PATH)

  try:
    bot = telegram("getMe")
  except BridgeError as exc:
    if exc.reason in ("key-unavailable", "invalid-key") or exc.status in (401, 404):
      set_status("needs_token", "Check your bot connection", "Open the app and connect or replace the bot key using the secure card in Möbius chat.")
    else:
      set_status("error", "Bot connection failed", str(exc)[:180])
    return 0

  username = bot.get("username") if isinstance(bot, dict) else None
  context = request_json(f"/api/apps/{APP_ID}/job-context")
  public_origin = navigation_origin(settings)
  try:
    webhook = telegram("getWebhookInfo")
  except BridgeError as exc:
    set_status("error", "Could not inspect the bot", str(exc)[:180], botUsername=username)
    return 0
  if isinstance(webhook, dict) and webhook.get("url"):
    set_status(
      "webhook_conflict",
      "Bot already connected elsewhere",
      "Remove its existing webhook in the previous service before using it here. Nothing was changed automatically.",
      botUsername=username,
    )
    return 0

  set_status("connected", "Connected", "Listening for messages from the paired private chat.", botUsername=username)
  pairing = storage_get("pairing.json")
  pairing = pairing if isinstance(pairing, dict) else None
  runtime = storage_get("bridge-runtime.json")
  runtime = runtime if isinstance(runtime, dict) else {}
  try:
    if sync_bot_commands(pairing, runtime, username):
      storage_put("bridge-runtime.json", runtime)
  except BridgeError:
    # Command-menu setup is progressive enhancement; message delivery wins.
    pass
  if pairing:
    sync_question_state(public_origin)
  return run_listener(SimpleNamespace(**globals()), runtime, context, username)


if __name__ == "__main__":
  try:
    raise SystemExit(main())
  except Exception as exc:
    # Keep logs free of message content and provider URLs. The UI gets only a
    # bounded class-level failure; the supervisor records the non-zero exit.
    try:
      set_status("error", "Bridge stopped", type(exc).__name__)
    except Exception:
      pass
    raise
