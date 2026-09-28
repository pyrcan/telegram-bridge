import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from test_bridge import bridge
import bridge_access as access
from bridge_assistants import menu
from test_bridge_assistants import CATALOG

PAIR={'userId':77,'chatId':77,'pairedAt':'now'}
OWNER={'scope':'owned-bots-v1','grant':'c'*12,'app_id':18,'studio_app_id':24,'binding':access.digest(PAIR)}
GRANT={'connection':OWNER['grant'],'grant':'a'*12,'assistant':'pocket-notes','app_id':18,'studio_app_id':24,'name':'Pocket Notes','binding':access.digest(PAIR),'epoch':'e','generation':0}
USER={'user_id':88,'name':'Tester','username':'test','created':1,'state':'pending','owner':False,'review':'b'*24}
STATE={'users':[USER],'epoch':'e','generation':0,'notifications':True}

class AccessTests(unittest.TestCase):
 def fixture(self):
  saved={'pairing.json':PAIR,'settings.json':{'enabled':True},access.CONNECTIONS:OWNER}
  b=MagicMock();b.APP_ID=18;b.BridgeError=bridge.BridgeError
  b.storage_get.side_effect=lambda path:saved.get(path)
  b.storage_put.side_effect=lambda path,data:saved.__setitem__(path,json.loads(json.dumps(data)))
  b.fixture_state=STATE.copy()
  def request(path,**kw):
   if path.endswith('/bots'):return {'bots':[GRANT]}
   if path.endswith('/notifications'):
    b.fixture_state['notifications']=kw['body']['enabled'];return {'notifications':kw['body']['enabled']}
   return b.fixture_state
  b.request_json.side_effect=request;b.send_text.return_value={'message_id':123}
  return b,saved
 def test_notification_is_once_and_status_edits_same_message(self):
  b,saved=self.fixture();access.sync(b);access.sync(b)
  self.assertEqual(b.send_text.call_count,1)
  b.fixture_state={**STATE,'users':[{**USER,'state':'allowed','review':'c'*24}]}
  access.sync(b)
  self.assertEqual(b.send_text.call_count,1)
  self.assertEqual(b.telegram.call_args.args[1]['message_id'],123)
  self.assertIn('Approved',b.telegram.call_args.args[1]['text'])
 def test_ambiguous_send_never_repeats(self):
  b,saved=self.fixture();b.send_text.side_effect=bridge.BridgeError('timeout')
  access.sync(b);access.sync(b)
  self.assertEqual(b.send_text.call_count,1)
  self.assertEqual(next(iter(saved[access.RECEIPTS].values()))['status'],'uncertain')
 def test_receipt_is_durable_before_send(self):
  b,saved=self.fixture()
  def send(*args,**kw):
   self.assertIn(access.RECEIPTS,saved);return {'message_id':12}
  b.send_text.side_effect=send;access.sync(b)
 def test_pause_repair_and_disconnected_never_notify(self):
  for change in ({'settings.json':{'enabled':False}},{'pairing.json':{**PAIR,'pairedAt':'changed'}},{access.CONNECTIONS:{}}):
   b,saved=self.fixture();saved.update(change);access.sync(b);b.send_text.assert_not_called()
 def test_live_binding_exact_studio_and_pair_only(self):
  b,saved=self.fixture()
  request={'path':'access-binding/'+OWNER['grant'],'method':'GET','actor':{'scope':'app','app_id':24}}
  with patch.dict(os.environ,{'APP_ID':'18'}):
   self.assertEqual(access.binding(request,read=saved.get)['binding'],GRANT['binding'])
   for actor in ({'scope':'app','app_id':25},{'scope':'public'},{'scope':'app','app_id':24,'delegated':True}):
    with self.assertRaises(ValueError):access.binding({**request,'actor':actor},read=saved.get)
   saved['pairing.json']={**PAIR,'pairedAt':'changed'}
   with self.assertRaises(ValueError):access.binding(request,read=saved.get)
 def test_other_telegram_user_cannot_read_or_mutate(self):
  with patch.object(bridge,'answer_callback'),patch.object(bridge,'request_json') as call,patch('bridge_access.callback') as callback:
   bridge.handle_callback_query({'id':'x','data':access.cb('a',GRANT,USER,USER['review']),'from':{'id':99},'message':{'chat':{'id':77}}},PAIR,'')
   callback.assert_not_called();call.assert_not_called()
 def test_stale_review_never_posts(self):
  b,saved=self.fixture()
  access.callback(b,access.cb('a',GRANT,USER,'c'*24),PAIR,'')
  self.assertTrue(all(c.kwargs.get('method','GET')=='GET' for c in b.request_json.call_args_list))
 def test_exact_review_posts_existing_domain_operation(self):
  b,saved=self.fixture();access.callback(b,access.cb('a',GRANT,USER,USER['review']),PAIR,'')
  self.assertEqual(b.request_json.call_args.kwargs['body'],{'user_id':88,'operation':'allow','review':USER['review'],'epoch':'e','generation':0})
  b.ask_mobius.assert_not_called()
 def test_remove_access_requires_review_not_immediate_mutation(self):
  b,saved=self.fixture();b.fixture_state={**STATE,'users':[{**USER,'state':'allowed'}]}
  access.callback(b,access.cb('x',GRANT,USER,USER['review']),PAIR,'')
  self.assertTrue(all(c.kwargs.get('method','GET')=='GET' for c in b.request_json.call_args_list))
  self.assertIn('Confirm removal',str(b.navigation_reply.call_args))
 def test_callback_byte_limit_and_no_regular_menu_footer(self):
  _,markup=access.detail(GRANT,{**USER,'user_id':9223372036854775807})
  self.assertTrue(all(len(button['callback_data'].encode())<=64 for row in markup['inline_keyboard'] for button in row))
 def test_users_discoverable_before_permission_setup(self):
  catalog={**CATALOG,'assistants':[{**CATALOG['assistants'][0],'connection':{'username':'Fixture_bot'}}]}
  _,markup=menu(catalog,'https://example.com','pocket-notes')
  self.assertIn('Users',[b['text'] for row in markup['inline_keyboard'] for b in row])
 def test_access_controls_can_progress_during_model_work(self):
  from bridge_loop import responsive_control
  self.assertTrue(responsive_control({'callback_query':{'data':access.cb('a',GRANT,USER,USER['review'])}}))

 def test_notifications_toggle_is_explicit_desired_state(self):
  b,saved=self.fixture()
  access.callback(b,f"ua:n:{GRANT['grant']}:0",PAIR,'')
  self.assertFalse(b.fixture_state['notifications'])
  self.assertIn('Turn on',str(b.navigation_reply.call_args))
  access.sync(b);b.send_text.assert_not_called()
  access.callback(b,f"ua:n:{GRANT['grant']}:1",PAIR,'')
  access.sync(b);b.send_text.assert_called_once()
 def test_old_per_bot_storage_is_not_a_global_permission(self):
  b,saved=self.fixture();saved[access.CONNECTIONS]={'pocket-notes':GRANT}
  access.sync(b);b.request_json.assert_not_called();b.send_text.assert_not_called()
 def test_old_handle_never_posts_after_bot_connection_changes(self):
  b,saved=self.fixture()
  access.callback(b,'ua:a:'+'e'*12+':88:'+USER['review'],PAIR,'')
  self.assertTrue(all(c.kwargs.get('method','GET')=='GET' for c in b.request_json.call_args_list))

class TrustedAccessTests(unittest.TestCase):
 def test_connect_and_disconnect_are_exact_reviewed_actions(self):
  import tempfile
  bot={**CATALOG['assistants'][0],'generation':0,'connection':{'epoch':'e','state':'active'}}
  catalog={**CATALOG,'assistants':[bot]}
  state={'pairing.json':PAIR,access.CONNECTIONS:{}}
  calls=[]
  def api(path,body=None,method=None):
   calls.append((path,body,method))
   if path.endswith('owner/catalog'):return catalog
   if '/api/storage/' in path:
    name=path.rsplit('/',1)[-1]
    if method=='PUT':state[name]=body;return {}
    return state.get(name)
   return {'ok':True}
  context={'scope':'owned-bots-v1','paired_user_id':'77','paired_chat_id':'77','paired_at':'now'}
  with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'APP_ID':'18','APP_STORAGE_DIR':root,'AGENT_TOKEN':'synthetic-owner','APP_TOKEN':''}):
   for field in ('scope','paired_user_id','paired_chat_id','paired_at'):
    with self.assertRaises(ValueError):access.owner_action({'action':'connect-access','context':{**context,field:'changed'}},api)
   self.assertFalse(any(path.endswith('owner/access-bridge') for path,_,_ in calls))
   access.owner_action({'action':'connect-access','context':context},api)
   grant=state[access.CONNECTIONS]
   self.assertEqual(grant['binding'],access.digest(PAIR));self.assertEqual(grant['studio_app_id'],24)
   access.owner_action({'action':'disconnect-access','context':{'assistant':'pocket-notes','grant':grant['grant']}},api)
   self.assertEqual(state[access.CONNECTIONS],{})
   self.assertEqual(calls[-2][1]['operation'],'disconnect')
 def test_job_cannot_invoke_consumer(self):
  with patch.dict(os.environ,{'APP_TOKEN':'scoped','AGENT_TOKEN':'synthetic-owner'}):
   with self.assertRaises(ValueError):access.owner_action({},MagicMock())
 def test_permission_consumer_failure_does_not_publish_local_grant(self):
  import tempfile
  calls=[]
  context={'scope':'owned-bots-v1','paired_user_id':'77','paired_chat_id':'77','paired_at':'now'}
  def api(path,body=None,method=None):
   if method=='PUT':calls.append(path)
   if path.endswith('owner/catalog'):return {**CATALOG,'assistants':[{**CATALOG['assistants'][0],'generation':0,'connection':{'epoch':'e','state':'active'}}]}
   if path.endswith('pairing.json'):return PAIR
   if path.endswith('owner/access-bridge'):raise ValueError('Unavailable')
   return {}
  with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'APP_ID':'18','APP_STORAGE_DIR':root,'AGENT_TOKEN':'synthetic-owner','APP_TOKEN':''}):
   with self.assertRaises(ValueError):access.owner_action({'action':'connect-access','context':context},api)
  self.assertEqual(calls,[])
