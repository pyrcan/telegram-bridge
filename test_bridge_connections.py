"""Lean Store scope: ordinary Bridge chats only, with no grant escalation."""
import unittest
from unittest.mock import MagicMock, patch
from test_bridge import bridge
import bridge_connections as actions
from bridge_assistants import menu, callback
from test_bridge_assistants import CATALOG

PAIR={'chatId':99,'userId':7,'pairedAt':'test-epoch'}
BOT={**CATALOG['assistants'][0],'editing_chat':{'id':'owner-chat'},'connection':{'state':'active','username':'Example_bot'}}
CAT={**CATALOG,'assistants':[BOT]}

class LeanConnectionTests(unittest.TestCase):
    def test_menu_links_to_exact_mobius_chat_without_grant_controls(self):
        _,markup=menu(CAT,'https://example.com','pocket-notes')
        buttons=sum(markup['inline_keyboard'],[])
        self.assertEqual([b['text'] for b in buttons],['Open bot','Customize in Möbius','Users','‹ My bots'])
        self.assertEqual(buttons[1]['url'],'https://example.com/shell/?chat=owner-chat')

    def test_old_continue_control_only_opens_navigation(self):
        b=MagicMock();b.request_json.return_value=CAT
        callback(b,'studio:continue:pocket-notes',PAIR,'https://example.com')
        b.storage_put.assert_not_called();b.ask_mobius.assert_not_called()
        self.assertEqual([c.args[0] for c in b.request_json.call_args_list],['/api/services/assistant-studio/owner/catalog'])

    def test_other_telegram_user_cannot_reach_old_control(self):
        with patch.object(bridge,'answer_callback'),patch.object(bridge,'request_json') as request:
            bridge.handle_callback_query({'id':'c','data':'studio:continue:pocket-notes','from':{'id':8},'message':{'chat':{'id':99}}},PAIR,'')
            request.assert_not_called()

    def test_retained_external_selection_fails_without_replacing_chat(self):
        with patch.object(bridge,'storage_get',return_value={'chatId':'owner-chat','connectionId':'old'}),patch.object(bridge,'request_json') as request,patch.object(bridge,'storage_put') as put:
            with self.assertRaises(bridge.BridgeError):bridge.ensure_conversation(PAIR)
            request.assert_not_called();put.assert_not_called()

    def test_no_platform_screenshot_or_chat_grant_dependency(self):
        from pathlib import Path
        import json
        root=Path(__file__).parent
        manifest=json.loads((root/'mobius.json').read_text())
        self.assertNotIn('owner_screenshot',manifest['permissions'])
        self.assertNotIn('owner_actions',manifest['service'])
        for name in ('bridge.py','bridge_connections.py','bridge_assistants.py','index.jsx'):
            text=(root/name).read_text()
            self.assertNotIn('/chat-connections',text)
            self.assertNotIn('/owner-screenshot',text)
        self.assertNotIn('preview_shell.sh',bridge.TELEGRAM_SYSTEM_PROMPT)

class BotInfoTests(unittest.TestCase):
    def test_management_projection_never_returns_raw_provider_data(self):
        import telegram_http
        with patch.dict('os.environ',{'APP_ID':'18','APP_TOKEN':'fake','API_BASE_URL':'http://localhost'}),patch.object(telegram_http,'call_saved',return_value={'id':42,'is_bot':True,'username':'Fixture_bot','private':'SECRET_SENTINEL'}):
            for actor in ({'scope':'owner'},{'scope':'app','app_id':18}):
                result=actions.dispatch({'method':'GET','path':'bot-info','actor':actor})
                self.assertEqual(result,{'id':42,'is_bot':True,'username':'Fixture_bot'})
    def test_foreign_delegated_and_public_callers_never_read_key(self):
        import telegram_http
        with patch.dict('os.environ',{'APP_ID':'18'}),patch.object(telegram_http,'call_saved') as call:
            for extra in ({'actor':{'scope':'app','app_id':24}}, {'actor':{'scope':'owner','delegated':True}}, {'public':True,'actor':{'scope':'owner'}}, {'actor':{}}):
                with self.assertRaises(ValueError):actions.dispatch({'method':'GET','path':'bot-info',**extra})
            call.assert_not_called()

class BridgeWriteCoordinationTests(unittest.TestCase):
    def test_parallel_status_writers_preserve_both_events(self):
        import threading,time,copy
        state={};start=threading.Barrier(2);errors=[]
        def read(path):
            value=copy.deepcopy(state.get(path));time.sleep(.01);return value
        def write(path,value):state[path]=copy.deepcopy(value)
        def worker(label):
            try:start.wait(2);bridge.activity(label)
            except Exception as exc:errors.append(exc)
        with patch.object(bridge,'storage_get',side_effect=read),patch.object(bridge,'storage_put',side_effect=write):
            threads=[threading.Thread(target=worker,args=(label,)) for label in ('one','two')]
            for thread in threads:thread.start()
            for thread in threads:thread.join(3);self.assertFalse(thread.is_alive())
        self.assertEqual(errors,[])
        self.assertEqual({v['label'] for v in state['status.json']['events']},{'one','two'})
