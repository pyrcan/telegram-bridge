import importlib.util
import os
import sys
import unittest
import threading
import time
from contextlib import ExitStack
from unittest.mock import MagicMock, patch


os.environ.setdefault("APP_TOKEN", "test-app-token")
_old_argv = sys.argv
sys.argv = ["bridge.py", "18"]
_spec = importlib.util.spec_from_file_location(
  "telegram_bridge_under_test",
  os.path.join(os.path.dirname(__file__), "bridge.py"),
)
bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge)
sys.argv = _old_argv


class TelegramQuestionTests(unittest.TestCase):
  def state(self):
    return {
      "nonce": "abc123",
      "questionId": "question-1",
      "mobiusChatId": "chat-1",
      "telegramChatId": 99,
      "telegramMessageId": 42,
      "questions": [{
        "header": "Direction",
        "question": "Which direction?",
        "multiSelect": False,
        "options": [
          {"label": "Recommended", "description": "Best default"},
          {"label": "Alternative", "description": "More control"},
        ],
      }],
      "selections": {},
      "leadText": "I need one choice.",
      "baselineText": "I need one choice.",
    }

  def test_markup_uses_only_compact_answer_callbacks(self):
    state = self.state()
    markup = bridge.question_markup(state, "https://mobius.example")
    callbacks = [
      button["callback_data"]
      for row in markup["inline_keyboard"]
      for button in row
      if "callback_data" in button
    ]
    self.assertIn("q:abc123:0:0", callbacks)
    self.assertIn("t:abc123:0", callbacks)
    self.assertTrue(all(len(value.encode()) <= 64 for value in callbacks))
    self.assertFalse(any(
      "url" in button
      for row in markup["inline_keyboard"]
      for button in row
    ))

  def test_single_choice_submits_immediately(self):
    state = self.state()
    pairing = {"chatId": 99, "userId": 7}
    callback = {
      "id": "callback-1",
      "from": {"id": 7},
      "message": {"chat": {"id": 99}},
      "data": "q:abc123:0:1",
    }
    calls = []
    with (
      patch.object(bridge, "sync_question_state", return_value=state),
      patch.object(bridge, "storage_put") as put,
      patch.object(bridge, "telegram", side_effect=lambda method, params: calls.append((method, params))),
      patch.object(bridge, "submit_question_state", return_value=True) as submit,
    ):
      bridge.handle_callback_query(callback, pairing, "https://mobius.example")
    self.assertEqual(calls[0][0], "answerCallbackQuery")
    self.assertEqual(state["selections"]["0"], "Alternative")
    put.assert_called_once()
    submit.assert_called_once()

  def test_stale_callback_never_submits(self):
    state = self.state()
    pairing = {"chatId": 99, "userId": 7}
    callback = {
      "id": "callback-old",
      "from": {"id": 7},
      "message": {"chat": {"id": 99}},
      "data": "q:old-nonce:0:0",
    }
    with (
      patch.object(bridge, "sync_question_state", return_value=state),
      patch.object(bridge, "telegram") as telegram,
      patch.object(bridge, "submit_question_state") as submit,
    ):
      bridge.handle_callback_query(callback, pairing, "https://mobius.example")
    submit.assert_not_called()
    self.assertEqual(
      telegram.call_args.args[0], "answerCallbackQuery",
    )
    self.assertIn("no longer active", telegram.call_args.args[1]["text"])

  def test_multi_select_requires_every_answer(self):
    state = self.state()
    state["questions"][0]["multiSelect"] = True
    self.assertIsNone(bridge.resolved_question_answers(state))
    state["selections"] = {"0": ["Recommended", "Custom"]}
    self.assertEqual(
      bridge.resolved_question_answers(state),
      {"Which direction?": "Recommended, Custom"},
    )

  def test_baseline_is_not_repeated_after_resume(self):
    self.assertEqual(
      bridge.after_baseline("Before question.\n\nAfter answer.", "Before question."),
      "After answer.",
    )

  def test_shell_answer_retires_external_buttons(self):
    state = self.state()
    rows = [{"id": "chat-1", "pending_question_id": None}]
    with (
      patch.object(bridge, "storage_get", return_value=state),
      patch.object(bridge, "request_json", return_value=rows),
      patch.object(bridge, "retire_question_state") as retire,
    ):
      result = bridge.sync_question_state("https://mobius.example")
    self.assertIsNone(result)
    retire.assert_called_once_with(
      state,
      "https://mobius.example",
      "This question is no longer active.",
    )

  def test_active_question_is_returned(self):
    state = self.state()
    rows = [{"id": "chat-1", "pending_question_id": "question-1"}]
    with (
      patch.object(bridge, "storage_get", return_value=state),
      patch.object(bridge, "request_json", return_value=rows),
      patch.object(bridge, "retire_question_state") as retire,
    ):
      result = bridge.sync_question_state("https://mobius.example")
    self.assertIs(result, state)
    retire.assert_not_called()

  def test_new_command_rechecks_and_ignores_stale_question(self):
    pairing = {"chatId": 99, "userId": 7}
    update = {
      "message": {
        "message_id": 12,
        "chat": {"id": 99, "type": "private"},
        "from": {"id": 7},
        "text": "/new",
      },
    }
    with (
      patch.object(bridge, "sync_question_state", return_value=None) as sync,
      patch.object(bridge, "storage_delete") as delete,
      patch.object(bridge, "ensure_conversation", return_value="chat-new") as ensure,
      patch.object(bridge, "send_text") as send,
      patch.object(bridge, "activity"),
    ):
      bridge.handle_update(update, {}, pairing, "https://mobius.example")
    sync.assert_called_once_with("https://mobius.example")
    delete.assert_called_once_with("conversation.json")
    ensure.assert_called_once_with(pairing)
    self.assertIn("Fresh Möbius conversation ready", send.call_args.args[1])

  def test_normal_message_rechecks_stale_question_before_chatting(self):
    pairing = {"chatId": 99, "userId": 7}
    message = {"text": "Hello", "message_id": 12}
    with (
      patch.object(bridge, "sync_question_state", return_value=None) as sync,
      patch.object(bridge, "ask_mobius") as ask,
    ):
      handled = bridge.handle_pending_text_answer(
        message, pairing, "https://mobius.example",
      )
    self.assertFalse(handled)
    sync.assert_called_once_with("https://mobius.example")
    ask.assert_not_called()

  def test_submission_is_hidden_and_resumes_same_question(self):
    state = self.state()
    state["selections"] = {"0": "Recommended"}
    pairing = {"chatId": 99, "userId": 7}
    with (
      patch.object(bridge, "request_json", return_value={"status": "answer_delivered"}) as request,
      patch.object(bridge, "clear_question_state") as clear,
      patch.object(bridge, "edit_question_message"),
      patch.object(bridge, "read_agent_stream", return_value={"kind": "reply", "text": "Continued"}) as read,
      patch.object(bridge, "deliver_agent_result") as deliver,
    ):
      self.assertTrue(
        bridge.submit_question_state(state, pairing, "https://mobius.example")
      )
    payload = request.call_args.kwargs["body"]
    self.assertTrue(payload["hidden"])
    self.assertEqual(payload["question_id"], "question-1")
    self.assertEqual(payload["answers"], {"Which direction?": "Recommended"})
    clear.assert_called_once_with()
    read.assert_called_once_with("chat-1", 99, baseline_text="I need one choice.")
    deliver.assert_called_once()

  def test_telegram_preserves_provider_error_code(self):
    with patch.object(bridge.telegram_http, "call_saved",
      side_effect=bridge.telegram_http.TelegramError(400)):
      with self.assertRaises(bridge.BridgeError) as raised:
        bridge.telegram("answerCallbackQuery", {"callback_query_id": "old"})
    self.assertEqual(raised.exception.status, 400)
    self.assertEqual(str(raised.exception), "Telegram could not complete this request.")

  def test_expired_callback_ack_does_not_block_new_conversation(self):
    pairing = {"chatId": 99, "userId": 7}
    callback = {
      "id": "callback-old",
      "from": {"id": 7},
      "message": {"chat": {"id": 99}},
      "data": "cmd:new",
    }
    telegram_calls = []

    def telegram(method, params):
      telegram_calls.append((method, params))
      if method == "answerCallbackQuery":
        raise bridge.BridgeError("query is too old", status=400)

    with (
      patch.object(bridge, "storage_get", return_value=None),
      patch.object(bridge, "storage_delete") as delete,
      patch.object(bridge, "ensure_conversation", return_value="chat-new") as ensure,
      patch.object(bridge, "telegram", side_effect=telegram),
      patch.object(bridge, "send_text") as send,
      patch.object(bridge, "activity") as activity,
    ):
      result = bridge.handle_callback_query(
        callback, pairing, "https://mobius.example",
      )

    self.assertEqual(result, pairing)
    delete.assert_called_once_with("conversation.json")
    ensure.assert_called_once_with(pairing)
    send.assert_called_once()
    activity.assert_called_once()
    self.assertEqual(telegram_calls[0][0], "answerCallbackQuery")

  def test_delegated_ack_skips_duplicate_and_keeps_text_feedback(self):
    update = {'_callback_ack_delegated': True, 'callback_query': {'id': 'callback-1', 'message': {'chat': {'id': 99}}}}
    try:
      bridge._update_context.update = update
      with patch.object(bridge, 'telegram') as telegram, patch.object(bridge, 'send_text') as send:
        bridge.answer_callback('callback-1')
        telegram.assert_not_called()
        bridge.answer_callback('callback-1', text='Answer the current question first.')
        send.assert_called_once_with(99, 'Answer the current question first.')
    finally:
      bridge._update_context.update = None

  def test_non_callback_telegram_errors_still_surface(self):
    with patch.object(
      bridge,
      "telegram",
      side_effect=bridge.BridgeError("Telegram unavailable", status=503),
    ):
      with self.assertRaises(bridge.BridgeError):
        bridge.answer_callback("callback-1")

  def test_routine_agent_reply_has_no_open_button(self):
    pairing = {"chatId": 99, "userId": 7}
    with (
      patch.object(bridge, "send_text") as send,
      patch.object(bridge, "activity"),
    ):
      bridge.deliver_agent_result(
        pairing,
        "chat-1",
        {"kind": "reply", "text": "Routine answer"},
        "https://mobius.example",
      )
    send.assert_called_once_with(
      99, "Routine answer", reply_to_message_id=None, reply_markup=None,
    )

  def test_reply_is_anchored_to_the_originating_telegram_message(self):
    with patch.object(
      bridge,
      "telegram",
      return_value={"message_id": 9},
    ) as telegram:
      bridge.send_text(99, "Reply", reply_to_message_id=123)
    telegram.assert_called_once_with("sendMessage", {
      "chat_id": 99,
      "text": "Reply",
      "reply_parameters": {
        "message_id": 123,
        "allow_sending_without_reply": True,
      },
    })

  def test_native_command_menu_uses_a_chat_specific_scope(self):
    runtime = {}
    calls = []
    with patch.object(
      bridge,
      "telegram",
      side_effect=lambda method, params: calls.append((method, params)),
    ):
      self.assertTrue(bridge.sync_bot_commands({"chatId": 99}, runtime, "my_bot"))
      self.assertFalse(bridge.sync_bot_commands({"chatId": 99}, runtime, "my_bot"))
    self.assertEqual(
      [method for method, _ in calls],
      ["setMyCommands", "setMyCommands", "setChatMenuButton"],
    )
    self.assertEqual(calls[1][1]["scope"], {"type": "chat", "chat_id": 99})
    self.assertEqual(runtime["botCommandChatId"], 99)
    self.assertEqual(runtime["botCommandUsername"], "my_bot")
    self.assertIn(
      {"command": "settings", "description": "Settings"},
      calls[1][1]["commands"],
    )

  def test_available_models_respects_visibility_and_availability(self):
    registry = {
      "providers": {
        "mobius": [{
          "id": "spark", "label": "Spark", "available": True,
        }],
        "codex": [
          {"id": "shown", "label": "Shown", "available": True},
          {"id": "hidden", "label": "Hidden", "available": True},
          {"id": "offline", "label": "Offline", "available": False},
        ],
      },
    }

    def request(path, **_kwargs):
      if path == "/api/models":
        return registry
      if path == "/api/owner/model-prefs":
        return {"hidden_ids": ["hidden"]}
      raise AssertionError(path)

    with patch.object(bridge, "request_json", side_effect=request):
      models = bridge.available_models()
    self.assertEqual([row["id"] for row in models["codex"]], ["shown"])
    self.assertEqual(models["mobius"][0]["label"], "Spark")

  def test_new_conversation_uses_saved_model_choice(self):
    pairing = {"chatId": 99, "displayName": "Alex"}
    created_bodies = []

    def storage(path):
      if path == "conversation.json":
        return None
      if path == bridge.MODEL_STATE_PATH:
        return {"provider": "codex", "model": "gpt-test"}
      raise AssertionError(path)

    def request(path, **kwargs):
      self.assertEqual(path, "/api/app-chats")
      created_bodies.append(kwargs["body"])
      return {"id": "chat-model"}

    with (
      patch.object(bridge, "storage_get", side_effect=storage),
      patch.object(bridge, "storage_put") as put,
      patch.object(bridge, "request_json", side_effect=request),
    ):
      chat_id = bridge.ensure_conversation(pairing)
    self.assertEqual(chat_id, "chat-model")
    self.assertEqual(created_bodies[0]["provider"], "codex")
    self.assertEqual(created_bodies[0]["model"], "gpt-test")
    put.assert_called_once()

  def test_model_selection_starts_fresh_conversation(self):
    pairing = {"chatId": 99, "userId": 7}
    callback = {
      "id": "model-callback",
      "from": {"id": 7},
      "message": {"message_id": 12, "chat": {"id": 99}},
      "data": "mdl:s:codex:gpt-test",
    }
    models = {
      "codex": [{
        "id": "gpt-test", "label": "GPT Test", "provider": "codex",
      }],
    }
    with (
      patch.object(bridge, "storage_get", return_value=None),
      patch.object(bridge, "available_models", return_value=models),
      patch.object(bridge, "current_model", return_value={
        "id": "old", "label": "Old", "provider": "codex",
      }),
      patch.object(bridge, "sync_question_state", return_value=None),
      patch.object(bridge, "answer_callback") as answer,
      patch.object(bridge, "storage_put") as put,
      patch.object(bridge, "storage_delete") as delete,
      patch.object(bridge, "ensure_conversation", return_value="chat-new") as ensure,
      patch.object(bridge, "edit_model_picker") as edit,
      patch.object(bridge, "activity") as activity,
    ):
      bridge.handle_callback_query(callback, pairing, "https://mobius.example")
    answer.assert_called_once_with("model-callback")
    put.assert_called_once()
    saved = put.call_args.args[1]
    self.assertEqual(saved["model"], "gpt-test")
    self.assertEqual(saved["provider"], "codex")
    delete.assert_called_once_with("conversation.json")
    ensure.assert_called_once_with(pairing)
    self.assertIn("Now using GPT Test", edit.call_args.args[1])
    activity.assert_called_once()

  def test_model_selection_does_not_abandon_pending_question(self):
    pairing = {"chatId": 99, "userId": 7}
    callback = {
      "id": "model-callback",
      "from": {"id": 7},
      "message": {"message_id": 12, "chat": {"id": 99}},
      "data": "mdl:s:codex:gpt-test",
    }
    models = {
      "codex": [{
        "id": "gpt-test", "label": "GPT Test", "provider": "codex",
      }],
    }
    with (
      patch.object(bridge, "storage_get", return_value=None),
      patch.object(bridge, "available_models", return_value=models),
      patch.object(bridge, "current_model", return_value=None),
      patch.object(bridge, "sync_question_state", return_value={"questionId": "q1"}),
      patch.object(bridge, "answer_callback") as answer,
      patch.object(bridge, "storage_put") as put,
      patch.object(bridge, "storage_delete") as delete,
    ):
      bridge.handle_callback_query(callback, pairing, "https://mobius.example")
    answer.assert_called_once_with(
      "model-callback", text="Answer the current question first.",
    )
    put.assert_not_called()
    delete.assert_not_called()

  def test_native_command_menu_is_removed_from_revoked_chat(self):
    runtime = {
      "botCommandContract": bridge.BOT_COMMANDS_VERSION,
      "botCommandChatId": 99,
      "botCommandUsername": "my_bot",
    }
    calls = []
    with patch.object(
      bridge,
      "telegram",
      side_effect=lambda method, params: calls.append((method, params)),
    ):
      self.assertTrue(bridge.sync_bot_commands(None, runtime, "my_bot"))
    self.assertEqual(
      [method for method, _ in calls],
      ["setMyCommands", "deleteMyCommands"],
    )
    self.assertEqual(calls[1][1]["scope"], {"type": "chat", "chat_id": 99})
    self.assertIsNone(runtime["botCommandChatId"])

  def test_images_become_authenticated_chat_navigation_not_media_grants(self):
    reply = "Here is your work.\n\n" + "![Image](/api/chats/source-chat/media/shot.png?token=FAKE)\n" * 6
    clean, images = bridge.text_reply(reply)
    self.assertEqual(clean, "Here is your work.")
    self.assertTrue(images)
    with patch.object(bridge,'request_json') as request,patch.object(bridge,'telegram') as telegram,patch.object(bridge,'send_text') as send,patch.object(bridge,'mark_timing'),patch.object(bridge,'activity'):
      bridge.deliver_agent_result({'chatId':99},'current-chat',{'text':reply},'https://mobius.example')
    request.assert_not_called();telegram.assert_not_called()
    self.assertNotIn('FAKE',str(send.call_args))
    self.assertIn('view the images',send.call_args.args[1])
    self.assertEqual(send.call_args.kwargs['reply_markup']['inline_keyboard'][0][0]['url'],'https://mobius.example/shell/?chat=current-chat')

  def test_visual_reply_without_address_explains_where_to_open(self):
    with patch.object(bridge,'send_text') as send,patch.object(bridge,'mark_timing'),patch.object(bridge,'activity'):
      bridge.deliver_agent_result({'chatId':99},'current-chat',{'text':'![Image](/api/chats/c/media/image.png)'},'')
    self.assertIn('Bridge settings',send.call_args.args[1])
    self.assertIsNone(send.call_args.kwargs['reply_markup'])

  def test_navigation_address_is_not_a_credential_or_fetch_target(self):
    self.assertEqual(bridge.navigation_origin({'mobiusAddress':'https://mobius.example:443/'}),'https://mobius.example:443')
    for value in ('http://example.com','https://user:password@example.com','https://example.com/path','https://example.com/?key=fake','https://example.com/#fake','https://example.com:99999','https://example.com:0','https://example.com\\@evil.test','https://example.com\n','javascript:alert(1)',None):
      self.assertEqual(bridge.navigation_origin({'mobiusAddress':value}),'',value)

  def test_thinking_draft_worker_starts_before_reading_without_blocking(self):
    worker = MagicMock()
    with (
      patch.object(bridge.secrets, "randbelow", return_value=41),
      patch.object(bridge, "send_thinking_draft") as thinking,
      patch.object(bridge.threading, "Thread", return_value=worker) as thread,
    ):
      with bridge.thinking_indicator(99):
        thinking.assert_not_called()  # The worker, not the reader, owns I/O.
        worker.start.assert_called_once()
    worker.join.assert_called_once_with(timeout=1)
    self.assertEqual(
      thread.call_args.kwargs["name"],
      "telegram-reply-draft",
    )
    self.assertTrue(thread.call_args.kwargs["daemon"])

  def test_slow_telegram_indicator_does_not_delay_stream_reader(self):
    entered = threading.Event()
    release = threading.Event()

    def slow_indicator(*args):
      entered.set()
      release.wait(3)

    with patch.object(bridge, "send_thinking_draft", side_effect=slow_indicator):
      started = time.monotonic()
      try:
        with bridge.thinking_indicator(99):
          self.assertTrue(entered.wait(1))
          self.assertLess(time.monotonic() - started, 1)
          release.set()
      finally:
        release.set()

  def test_thinking_draft_uses_native_telegram_placeholder(self):
    bridge._thinking_draft_mode = "rich"
    with patch.object(bridge, "telegram") as telegram:
      bridge.send_thinking_draft(99, 42, 3)
    telegram.assert_called_once_with("sendRichMessageDraft", {
      "chat_id": 99,
      "draft_id": 42,
      "rich_message": {
        "blocks": [{"type": "thinking", "text": "Thinking 3s"}],
      },
    })

  def test_thinking_draft_falls_back_without_blocking_the_reply(self):
    bridge._thinking_draft_mode = "rich"
    calls = []

    def telegram(method, params):
      calls.append((method, params))
      if method == "sendRichMessageDraft":
        raise bridge.BridgeError("Draft unsupported", status=400)

    with patch.object(bridge, "telegram", side_effect=telegram):
      bridge.send_thinking_draft(99, 42, 7)
    self.assertEqual(
      [method for method, _ in calls],
      ["sendRichMessageDraft", "sendMessageDraft"],
    )
    self.assertEqual(calls[1][1]["text"], "Thinking 7s")
    calls.clear()
    with patch.object(bridge, "telegram", side_effect=lambda method, params: calls.append((method, params))):
      bridge.send_thinking_draft(99, 42, 8)
    self.assertEqual([method for method, _ in calls], ["sendMessageDraft"])

  def test_thinking_draft_has_typing_fallback_for_older_clients(self):
    bridge._thinking_draft_mode = "rich"
    calls = []

    def telegram(method, params):
      calls.append((method, params))
      if method != "sendChatAction":
        raise bridge.BridgeError("Draft unsupported", status=400)

    with patch.object(bridge, "telegram", side_effect=telegram):
      bridge.send_thinking_draft(99, 42, 1)
    self.assertEqual(
      [method for method, _ in calls],
      ["sendRichMessageDraft", "sendMessageDraft", "sendChatAction"],
    )




  def test_paired_non_text_message_gets_an_honest_reply(self):
    update = {
      "message": {
        "message_id": 321,
        "chat": {"id": 99, "type": "private"},
        "from": {"id": 7},
        "photo": [{"file_id": "photo-1"}],
      },
    }
    pairing = {"chatId": 99, "userId": 7}
    with patch.object(bridge, "send_text") as send:
      result = bridge.handle_update(
        update,
        {"pairingCode": "PAIRCODE"},
        pairing,
        "https://mobius.example",
      )
    self.assertEqual(result, pairing)
    send.assert_called_once_with(
      99,
      "I can currently read text messages only. Send a text prompt or use /help for commands.",
      reply_to_message_id=321,
    )


class DeliveryTests(unittest.TestCase):
  def test_streamed_public_text_is_available_before_done(self):
    import json
    progress = MagicMock()
    class Stream:
      status = 200
      def __enter__(self): return self
      def __exit__(self, *args): pass
      def __iter__(self):
        for event in [
          {"type": "text", "content": "Hello", "text_item_id": "a"},
          {"type": "text", "content": " there", "text_item_id": "a"},
          {"type": "text_final", "content": "Hello there!", "text_item_id": "a"},
        ]:
          yield ('data: ' + json.dumps(event)).encode()
        self_test.assertEqual(progress.show.call_args.args[0], "Hello there!")
        yield b'data: {"type":"done"}'
    self_test = self
    with patch.object(bridge.urllib.request, "urlopen", return_value=Stream()):
      result = bridge._read_agent_stream("chat", 99, progress=progress)
    self.assertEqual(result["text"], "Hello there!")
    self.assertEqual(progress.show.call_count, 3)

  def test_duplicate_completed_send_recovers_without_new_agent_stream(self):
    cid = "telegram-18-10"
    records = {"telegram-delivery.json": {"cid": cid, "chatId": "original-chat"}}
    bridge._update_context.update = {"update_id": 10}
    try:
      with (
        patch.object(bridge, "storage_get", side_effect=records.get),
        patch.object(bridge, "storage_put"),
        patch.object(bridge, "ensure_conversation") as ensure,
        patch.object(bridge, "request_json", return_value={"status": "duplicate", "running": False}) as request,
        patch.object(bridge, "recover_completed_reply", return_value={"kind": "reply", "text": "Recovered"}),
        patch.object(bridge, "read_agent_stream") as stream,
        patch.object(bridge, "deliver_agent_result") as deliver,
      ):
        bridge.ask_mobius({"chatId": 99}, "hi", "")
      ensure.assert_not_called()
      stream.assert_not_called()
      self.assertEqual(request.call_args.args[0], "/api/chats/original-chat/messages")
      self.assertEqual(request.call_args.kwargs["body"]["cid"], cid)
      self.assertEqual(deliver.call_args.args[1], "original-chat")
    finally:
      bridge._update_context.update = None

  def test_recovery_does_not_return_a_later_turn(self):
    with patch.object(bridge, "request_json", return_value={"messages": [
      {"role": "user", "cid": "wanted"}, {"role": "assistant", "content": "original"},
      {"role": "user", "cid": "later"}, {"role": "assistant", "content": "unrelated"},
    ]}):
      self.assertEqual(bridge.recover_completed_reply("chat", "wanted")["text"], "original")


if __name__ == "__main__":
  unittest.main()

class SafeTransportReasonTests(unittest.TestCase):
  def test_edit_fallback_uses_safe_provider_reason_end_to_end(self):
    import io
    import json
    for description in ('Bad Request: message to edit not found', "Bad Request: message can't be edited", 'Bad Request: MESSAGE_ID_INVALID'):
      body=io.BytesIO(json.dumps({'ok':False,'description':description+' PRIVATE KEY'}).encode())
      body.code=400
      opener=MagicMock();opener.open.return_value=body
      def saved(*args, **kwargs):
        return bridge.telegram_http.call('123:'+'a'*24, args[1], args[2], opener=opener)
      with patch.object(bridge.telegram_http,'call_saved',side_effect=saved),patch.object(bridge,'send_text') as send:
        bridge.navigation_reply(99,'Menu',{}, {'message_id':10})
        send.assert_called_once_with(99,'Menu',reply_markup={})

  def test_missing_key_is_setup_not_a_server_restart(self):
    with patch.object(bridge,'storage_get',return_value={'enabled':True}),patch.object(bridge,'ensure_storage_null'),patch.object(bridge.telegram_http,'call_saved',side_effect=bridge.telegram_http.TelegramError(reason='key-unavailable')),patch.object(bridge,'set_status') as status:
      self.assertEqual(bridge.main(),0)
      self.assertEqual(status.call_args.args[0],'needs_token')
      self.assertIn('secure card',status.call_args.args[2])
      self.assertNotIn('restart',str(status.call_args).lower())
