import unittest
from unittest.mock import patch, MagicMock
from test_bridge import bridge
from bridge_assistants import menu, read_control, input_reply, PENDING
from bridge_loop import responsive_control

CATALOG={'app_id':24,'assistants':[{'id':'pocket-notes','name':'Pocket Notes','description':'Notes',
 'development':{'status':'Not connected','test_label':'Not running','release_label':'Not published','next_step':'Connect Telegram first.'},'version':2,'draft_model':'luna','published_model':'luna','draft_changed':False}]}
PAIR={'chatId':99,'userId':7}

class AssistantControlsTests(unittest.TestCase):
 def callback(self,data,user=7):
  return {'id':'cb','from':{'id':user},'message':{'chat':{'id':99}},'data':data}
 def test_list_and_detail_have_real_controls(self):
  for identity in (None,'pocket-notes'):
   text,markup=menu(CATALOG,'https://example.com',identity)
   self.assertIn('Pocket Notes',text if identity else str(markup))
   for row in markup['inline_keyboard']:
    for button in row:self.assertLessEqual(len(button.get('callback_data','').encode()),64)
  self.assertIn('Not connected',menu(CATALOG,'', 'pocket-notes')[0])
 def test_menu_has_discoverable_assistants_command(self):
  self.assertIn('bots',[x['command'] for x in bridge.PAIRED_COMMANDS])
  self.assertNotIn('cmd:assistants',str(bridge.command_markup('',None)))
 def test_unpaired_cannot_read_or_manage(self):
  with patch.object(bridge,'answer_callback'),patch.object(bridge,'request_json') as req,patch.object(bridge,'ask_mobius') as ask:
   bridge.handle_callback_query(self.callback('cmd:assistants',8),PAIR,'')
   req.assert_not_called();ask.assert_not_called()
 def test_browse_does_not_call_model_or_question_state(self):
  with patch.object(bridge,'answer_callback'),patch.object(bridge,'request_json',return_value=CATALOG) as req,patch.object(bridge,'send_text') as send,patch.object(bridge,'ask_mobius') as ask,patch.object(bridge,'sync_question_state') as sync:
   bridge.handle_callback_query(self.callback('studio:view:pocket-notes'),PAIR,'')
   req.assert_called_once_with('/api/services/assistant-studio/owner/catalog');ask.assert_not_called();sync.assert_not_called();send.assert_called_once()
 def test_old_edit_opens_canonical_navigation_without_model(self):
  with patch.object(bridge,'answer_callback'),patch.object(bridge,'request_json',return_value=CATALOG),patch.object(bridge,'send_text') as send,patch.object(bridge,'storage_put') as put,patch.object(bridge,'ask_mobius') as ask:
   bridge.handle_callback_query(self.callback('studio:edit:pocket-notes'),PAIR,'https://example.com')
   ask.assert_not_called();put.assert_not_called();self.assertIn('Set up in Studio',str(send.call_args))
 def test_older_pending_edit_does_not_create_competing_owner_turn(self):
  pending={'prompt_id':55,'chat_id':99,'user_id':7,'assistant':'pocket-notes','action':'edit'}
  with patch.object(bridge,'storage_get',return_value=pending),patch.object(bridge,'sync_question_state',return_value=None),patch.object(bridge,'ask_mobius') as ask,patch.object(bridge,'storage_put'),patch.object(bridge,'request_json',return_value=CATALOG),patch.object(bridge,'send_text') as send:
   self.assertTrue(input_reply(bridge,{'text':'Be concise','reply_to_message':{'message_id':55}},PAIR,'https://example.com'))
   ask.assert_not_called();self.assertIn('Nothing was changed',send.call_args_list[0].args[1])
 def test_unrelated_reply_is_not_intercepted(self):
  with patch.object(bridge,'storage_get',return_value={'prompt_id':55}),patch.object(bridge,'ask_mobius') as ask:
   self.assertFalse(input_reply(bridge,{'text':'hi','reply_to_message':{'message_id':56}},PAIR,''));ask.assert_not_called()
 def test_publish_enters_review_not_blind_mutation(self):
  with patch.object(bridge,'answer_callback'),patch.object(bridge,'request_json',return_value=CATALOG) as req,patch.object(bridge,'sync_question_state',return_value=None),patch.object(bridge,'ask_mobius') as ask,patch.object(bridge,'send_text') as send:
   bridge.handle_callback_query(self.callback('studio:publish:pocket-notes'),PAIR,'')
   ask.assert_not_called();self.assertEqual(req.call_count,1)
 def test_only_navigation_overtakes_ai_turn(self):
  for data,expected in [('cmd:assistants',True),('studio:view:pocket-notes',True),('studio:list:1',True),('studio:edit:pocket-notes',False),('studio:publish:pocket-notes',False),('studio:create',False)]:
   self.assertEqual(responsive_control({'callback_query':{'data':data}}),expected)
 def test_paginated_list_keeps_callbacks_bounded(self):
  catalog={'assistants':[{**CATALOG['assistants'][0],'id':f'{i:032x}'} for i in range(25)]}
  text,markup=menu(catalog,'',page=1)
  self.assertEqual(len(markup['inline_keyboard']),10)
  self.assertIn('studio:list:2',str(markup))
 def test_unavailable_studio_does_not_invoke_model(self):
  with patch.object(bridge,'answer_callback'),patch.object(bridge,'request_json',side_effect=bridge.BridgeError('offline')),patch.object(bridge,'send_text') as send,patch.object(bridge,'ask_mobius') as ask:
   bridge.handle_callback_query(self.callback('cmd:assistants'),PAIR,'');ask.assert_not_called();self.assertIn('unavailable',send.call_args.args[1])

class SimpleNavigationTests(unittest.TestCase):
 def test_navigation_updates_same_message(self):
  callback={'id':'cb','from':{'id':7},'message':{'message_id':123,'chat':{'id':99}},'data':'studio:view:pocket-notes'}
  with patch.object(bridge,'answer_callback'),patch.object(bridge,'request_json',return_value=CATALOG),patch.object(bridge,'telegram') as tg,patch.object(bridge,'send_text') as send:
   bridge.handle_callback_query(callback,PAIR,'https://example.com');tg.assert_called_once();self.assertEqual(tg.call_args.args[0],'editMessageText');self.assertEqual(tg.call_args.args[1]['message_id'],123);send.assert_not_called()
 def test_global_navigation_is_native_menu_only(self):
  buttons=[b for row in bridge.command_markup('',None)['inline_keyboard'] for b in row]
  self.assertEqual(buttons,[])
 def test_bot_overview_hides_model_and_versions(self):
  text,markup=menu(CATALOG,'https://example.com','pocket-notes')
  self.assertNotIn('luna',text);self.assertNotIn('version',text);self.assertNotIn('Draft',text)
 def test_settings_link_to_studio_without_duplicate_edit_controls(self):
  text,markup=menu(CATALOG,'https://example.com','pocket-notes',settings=True)
  self.assertNotIn('luna',text);self.assertNotIn('studio:model:',str(markup));self.assertIn('Open Studio',str(markup))

class ChatNavigationTests(unittest.TestCase):
 def test_home_has_app_handoff_when_origin_known(self):
  buttons=[b for row in bridge.command_markup('https://mobius.example','id')['inline_keyboard'] for b in row]
  self.assertEqual([b['text'] for b in buttons],['Open Möbius'])
 def test_chat_list_scoped_and_bounded(self):
  pairing={'chatId':99,'userId':7}
  chats=[{'id':str(i),'title':'Chat '+str(i),'scope':'telegram:99'} for i in range(9)]+[{'id':'other','title':'PRIVATE_OTHER','scope':'telegram:88'}]
  with patch.object(bridge,'request_json',side_effect=lambda path: chats if path=='/api/app-chats' else {'connections':[]}),patch.object(bridge,'storage_get',return_value={'chatId':'1'}),patch.object(bridge,'send_text') as send:
   bridge.show_chats(pairing,'https://example.com')
   raw=str(send.call_args);self.assertNotIn('PRIVATE_OTHER',raw);self.assertIn('Next',raw);self.assertIn('✓ Chat 1',raw)
 def test_switch_validates_scope_and_pending_questions(self):
  pairing={'chatId':99,'userId':7};callback={'id':'cb','from':{'id':7},'message':{'chat':{'id':99},'message_id':1},'data':'chat:other'}
  with patch.object(bridge,'sync_question_state',return_value=None),patch.object(bridge,'request_json',side_effect=lambda path: [{'id':'other','scope':'telegram:88'}] if path=='/api/app-chats' else {'connections':[]}),patch.object(bridge,'answer_callback'),patch.object(bridge,'storage_put') as put:
   bridge.handle_callback_query(callback,pairing,'https://example.com');put.assert_not_called()
 def test_switch_own_chat_without_model(self):
  pairing={'chatId':99,'userId':7};callback={'id':'cb','from':{'id':7},'message':{'chat':{'id':99},'message_id':1},'data':'chat:mine'}
  with patch.object(bridge,'sync_question_state',return_value=None),patch.object(bridge,'request_json',return_value=[{'id':'mine','scope':'telegram:99','title':'Mine'}]),patch.object(bridge,'answer_callback'),patch.object(bridge,'telegram'),patch.object(bridge,'storage_put') as put:
   bridge.handle_callback_query(callback,pairing,'https://example.com');self.assertEqual(put.call_args.args[1]['chatId'],'mine')
 def test_only_chat_listing_uses_responsive_lane(self):
  from bridge_loop import responsive_control
  self.assertTrue(responsive_control({'callback_query':{'data':'chats:0'}}))
  self.assertFalse(responsive_control({'callback_query':{'data':'chat:mine'}}))

class ConnectedExperienceTests(unittest.TestCase):
 def test_home_shows_current_chat_and_pending_answer_readonly(self):
  chats=[{'id':'mine','scope':'telegram:99','title':'My work','pending_question_id':'q'},{'id':'other','scope':'telegram:88','title':'PRIVATE'}]
  with patch.object(bridge,'request_json',return_value=chats),patch.object(bridge,'storage_put') as put,patch.object(bridge,'ask_mobius') as ask,patch.object(bridge,'sync_question_state') as sync:
   text,markup=bridge.owner_home(PAIR,'https://example.com','mine')
   self.assertIn('Current chat: My work',text);self.assertIn('Waiting for your answer',text)
   self.assertNotIn('PRIVATE',text);self.assertIn('Answer in Möbius',str(markup))
   put.assert_not_called();ask.assert_not_called();sync.assert_not_called()
 def test_home_never_shows_unscoped_chat(self):
  with patch.object(bridge,'request_json',side_effect=lambda path: [{'id':'other','scope':'telegram:88','title':'PRIVATE'}] if path=='/api/app-chats' else {'connections':[]}):
   self.assertNotIn('PRIVATE',str(bridge.owner_home(PAIR,'','other')))
 def test_repeated_settings_does_not_send_duplicate(self):
  with patch.object(bridge,'telegram',side_effect=bridge.BridgeError('Safe error',status=400,reason='not-modified')),patch.object(bridge,'send_text') as send:
   bridge.navigation_reply(99,'Settings',{}, {'message_id':10});send.assert_not_called()
 def test_missing_navigation_message_reopens_only_on_definite_failure(self):
  with patch.object(bridge,'telegram',side_effect=bridge.BridgeError('Safe error',status=400,reason='edit-unavailable')),patch.object(bridge,'send_text') as send:
   bridge.navigation_reply(99,'Settings',{}, {'message_id':10});send.assert_called_once()
  with patch.object(bridge,'telegram',side_effect=bridge.BridgeError('uncertain',status=502)),patch.object(bridge,'send_text') as send:
   with self.assertRaises(bridge.BridgeError):bridge.navigation_reply(99,'Settings',{}, {'message_id':10})
   send.assert_not_called()
 def test_bot_use_and_management_are_distinct(self):
  catalog={**CATALOG,'assistants':[{**CATALOG['assistants'][0],'development':{**CATALOG['assistants'][0]['development'],'status':'Needs attention'},'connection':{'state':'active','username':'Fixture_bot','error':'offline'}}]}
  text,markup=menu(catalog,'https://example.com','pocket-notes')
  self.assertIn('Needs attention',text)
  buttons=[b for r in markup['inline_keyboard'] for b in r]
  self.assertEqual(buttons[0]['text'],'Open bot');self.assertEqual(buttons[1]['text'],'Customize in Studio')
  self.assertNotIn('studio:edit:',str(markup))

class QuietOwnerTests(unittest.TestCase):
 def test_bot_detail_has_use_customize_users_and_back(self):
  catalog={**CATALOG,'assistants':[{**CATALOG['assistants'][0],'connection':{'state':'active','username':'Fixture_bot'}}]}
  _,markup=menu(catalog,'https://example.com','pocket-notes')
  buttons=[b for row in markup['inline_keyboard'] for b in row]
  self.assertEqual([b['text'] for b in buttons],['Open bot','Customize in Studio','Users','‹ My bots'])
 def test_chats_does_not_repeat_global_menu(self):
  with patch.object(bridge,'request_json',side_effect=lambda path: [] if path=='/api/app-chats' else {'connections':[]}),patch.object(bridge,'storage_get',return_value={}),patch.object(bridge,'send_text') as send:
   bridge.show_chats(PAIR,'https://example.com')
   buttons=[b for row in send.call_args.kwargs['reply_markup']['inline_keyboard'] for b in row]
   self.assertEqual([b['text'] for b in buttons],['New chat'])
 def test_pending_home_has_one_relevant_link_not_two(self):
  with patch.object(bridge,'request_json',return_value=[{'id':'mine','scope':'telegram:99','pending_question_id':'q'}]):
   _,markup=bridge.owner_home(PAIR,'https://example.com','mine')
   self.assertEqual(len(markup['inline_keyboard']),1)
   self.assertEqual(markup['inline_keyboard'][0][0]['text'],'Answer in Möbius')

class PrivateDevelopmentNavigationTests(unittest.TestCase):
 def test_private_testing_keeps_contextual_user_navigation(self):
  catalog={**CATALOG,'assistants':[{**CATALOG['assistants'][0],'connection':{'state':'testing','username':'Fixture_bot'},'private_test':{'enabled':True},'development':{**CATALOG['assistants'][0]['development'],'status':'Private test','test_label':'Latest draft loaded'}}]}
  text,markup=menu(catalog,'https://example.com','pocket-notes')
  self.assertIn('Private test',text);self.assertNotIn('Not connected',text);self.assertIn('Published bot: Not published',text)
  self.assertEqual([b['text'] for row in markup['inline_keyboard'] for b in row],['Open bot','Customize in Studio','Users','‹ My bots'])
 def test_connected_unpublished_bot_is_not_ready_for_live_activation(self):
  catalog={**CATALOG,'assistants':[{**CATALOG['assistants'][0],'development':{**CATALOG['assistants'][0]['development'],'status':'Connected'},'version':None,'connection':{'state':'verified','username':'Fixture_bot'}}]}
  text,_=menu(catalog,'https://example.com','pocket-notes')
  self.assertIn('Connected',text);self.assertNotIn('activate',text)
 def test_create_handoff_starts_blank_not_notes(self):
  pending={'prompt_id':55,'chat_id':99,'user_id':7,'assistant':None,'action':'create'}
  with patch.object(bridge,'storage_get',return_value=pending),patch.object(bridge,'storage_put'),patch.object(bridge,'sync_question_state',return_value=None),patch.object(bridge,'ask_mobius') as ask:
   self.assertTrue(input_reply(bridge,{'text':'My helper','message_id':56,'reply_to_message':{'message_id':55}},PAIR,''))
   instruction=ask.call_args.args[1]
   self.assertIn('blank, unconfigured',instruction);self.assertNotIn('notes-v1',instruction);self.assertIn('Do not publish, activate',instruction)

class CanonicalCustomizationTests(unittest.TestCase):
 def test_existing_chat_link_never_switches_bridge_authority(self):
  catalog={**CATALOG,'assistants':[{**CATALOG['assistants'][0],'editing_chat':{'id':'owner-chat-id'},'connection':{'state':'testing','username':'Fixture_bot'}}]}
  _,markup=menu(catalog,'https://example.com','pocket-notes')
  buttons=[b for row in markup['inline_keyboard'] for b in row]
  self.assertEqual([b['text'] for b in buttons],['Open bot','Customize in Möbius','Users','‹ My bots'])
  self.assertEqual(buttons[1]['url'],'https://example.com/shell/?chat=owner-chat-id')
  self.assertNotIn('callback_data',buttons[1])
 def test_no_origin_does_not_construct_fake_navigation(self):
  text,markup=menu(CATALOG,'','pocket-notes')
  self.assertIn('Open Telegram Bot Studio',text)
  self.assertFalse(any('url' in b for row in markup['inline_keyboard'] for b in row))
 def test_studio_remains_accessible_from_bot_list(self):
  _,markup=menu(CATALOG,'https://example.com')
  self.assertEqual(markup['inline_keyboard'][-1][1],{'text':'Open Studio','url':'https://example.com/shell/?app=24'})

class AccessOnlyNavigationTests(unittest.TestCase):
 def test_access_management_needs_no_broader_catalog_permission(self):
  import bridge_assistants
  grants={'pocket-notes':{'assistant':'pocket-notes','name':'My published bot','grant':'abcdef123456','connection':'feedfeedfeed'}}
  with patch.object(bridge,'request_json',side_effect=bridge.BridgeError('Catalog denied',status=403)),patch.object(bridge_assistants.bridge_access,'connected',return_value=grants),patch.object(bridge,'navigation_reply') as reply:
   bridge_assistants.show(bridge,PAIR,'')
   self.assertEqual(reply.call_args.args[2]['inline_keyboard'][0][0]['callback_data'],'ua:l:abcdef123456:0')
   self.assertNotIn('editing_chat',str(reply.call_args))
   self.assertNotIn('Create bot',str(reply.call_args))
 def test_access_only_back_link_returns_to_same_scoped_users(self):
  import bridge_assistants
  grant={'grant':'abcdef123456'}
  with patch.object(bridge,'request_json',side_effect=bridge.BridgeError('Catalog denied')),patch.object(bridge_assistants.bridge_access,'connected',return_value={'pocket-notes':grant}),patch.object(bridge_assistants.bridge_access,'callback') as call:
   bridge_assistants.show(bridge,PAIR,'',identity='pocket-notes')
   self.assertEqual(call.call_args.args[1],'ua:l:abcdef123456:0')
