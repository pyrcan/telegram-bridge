"""Offline Bridge guards. All values, transports, pairing and state are synthetic."""
import os
import socket
import urllib.request
import pytest

@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
 def blocked(*args,**kwargs):raise AssertionError('Unmocked network is forbidden')
 monkeypatch.setattr(socket.socket,'connect',blocked)
 monkeypatch.setattr(socket.socket,'connect_ex',blocked)
 monkeypatch.setattr(socket,'create_connection',blocked)
 monkeypatch.setattr(urllib.request,'urlopen',blocked)
 monkeypatch.setattr(urllib.request.OpenerDirector,'open',blocked)

@pytest.fixture
def bridge(monkeypatch):
 import sys,importlib
 from pathlib import Path
 root=Path(__file__).resolve().parent
 monkeypatch.syspath_prepend(str(root));monkeypatch.setattr(sys,'argv',['bridge.py','17'])
 monkeypatch.setenv('APP_TOKEN','synthetic-app-job');monkeypatch.setenv('API_BASE_URL','http://127.0.0.1:8000')
 sys.modules.pop('bridge',None);b=importlib.import_module('bridge')
 values={};calls=[]
 monkeypatch.setattr(b,'storage_get',lambda p,**kw:values.get(p))
 monkeypatch.setattr(b,'storage_put',lambda p,v:values.__setitem__(p,__import__('copy').deepcopy(v)))
 monkeypatch.setattr(b,'storage_delete',lambda p:values.pop(p,None))
 monkeypatch.setattr(b,'send_text',lambda *a,**kw:calls.append(('send',a,kw)) or {'message_id':45})
 monkeypatch.setattr(b,'telegram',lambda *a,**kw:calls.append(('telegram',a,kw)) or {'message_id':45})
 b.values=values;b.calls=calls
 b.pair={'chatId':101,'userId':101,'pairedAt':'2026-01-01T00:00:00Z','displayName':'Synthetic Owner'}
 values['pairing.json']=b.pair;values['settings.json']={'enabled':True,'pairingCode':None}
 values['conversation.json']={'chatId':'own-a'}
 b.rows=[{'id':'own-a','scope':'telegram:101','created_by_app_id':17,'pending_question_id':None,'running':False,'title':'Synthetic Personal','model':'model-a','provider':'codex'}]
 def request(path,**kw):
  calls.append(('api',path,kw))
  if path=='/api/app-chats':return b.rows
  if path=='/api/owner/model-prefs':return {'hidden_ids':[]}
  if path=='/api/models':return {'providers':{'codex':[{'id':'model-a','label':'Model A','available':True}]}}
  raise AssertionError('Unexpected route '+path)
 monkeypatch.setattr(b,'request_json',request)
 return b

import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import threading
import time
import urllib.error
import pytest

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
import telegram_http as http

KEY='123456:'+('A'*40)

class Response:
 def __init__(self,body,code=200):self.body=body if isinstance(body,bytes) else json.dumps(body).encode();self.code=self.status=code
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self,size=-1):return self.body[:size] if size>=0 else self.body

class Opener:
 def __init__(self,body,code=200):self.body=body;self.code=code;self.requests=[]
 def open(self,request,**kw):self.requests.append((request,kw));return Response(self.body,self.code)

@pytest.mark.parametrize('method',['../getMe','getMe?x=y','getMe#x','%67etMe','GETME','sendPhoto','deleteWebhook','https://evil.test/'])
def test_transport_canonical_methods(method):
 op=Opener({'ok':True,'result':{}})
 with pytest.raises(http.TelegramError):http.call_key(KEY,method,opener=op)
 assert op.requests==[]

@pytest.mark.parametrize('origin',['http://evil.test','https://api.test/x','https://user:key@api.test','https://api.test?x=1','https://api.test#x','http://127.0.0.1:bad'])
def test_origin_exact(origin):
 with pytest.raises(http.TelegramError):http.safe_origin(origin)

def test_transport_no_proxy_redirect_and_no_secret_echo():
 assert http.NoRedirect().redirect_request(None,None,None,None,None,None) is None
 op=Opener({'ok':True,'result':{'echo':KEY,'text':KEY}})
 result=http.call_key(KEY,'getWebhookInfo',opener=op)
 assert KEY not in json.dumps(result)
 req,_=op.requests[0]
 assert req.full_url=='https://api.telegram.org/bot'+KEY+'/getWebhookInfo'
 assert req.method=='POST'
 assert req.headers.get('Authorization') is None

def test_nested_unicode_escaped_secret_echo():
 # Provider JSON can encode a credential as unicode escapes; raw byte redaction
 # alone is not sufficient and this case must remain filtered after decoding.
 escaped=''.join('\\u%04x'%ord(c) for c in KEY)
 op=Opener((' {"ok":true,"result":{"echo":"'+escaped+'"}}').encode())
 assert KEY not in json.dumps(http.call_key(KEY,'getWebhookInfo',opener=op))

def test_transport_errors_sanitized():
 op=Opener({'ok':False,'error_code':400,'description':'secret '+KEY+' https://evil.test'})
 with pytest.raises(http.TelegramError) as e:http.call_key(KEY,'sendMessage',opener=op)
 assert KEY not in str(e.value) and 'evil' not in str(e.value)
 op=Opener({'ok':True,'result':{}},302)
 with pytest.raises(http.TelegramError):http.call_key(KEY,'getMe',opener=op)

def test_transport_size_and_poll_bounds():
 with pytest.raises(http.TelegramError):http.call_key(KEY,'getUpdates',{'timeout':11},opener=Opener({}))
 with pytest.raises(http.TelegramError):http.call_key(KEY,'sendMessage',{'text':'x'*(http.MAX_REQUEST+1)},opener=Opener({}))
 with pytest.raises(http.TelegramError):http.call_key(KEY,'getMe',opener=Opener(b'x'*(http.MAX_RESPONSE+1)))

def test_ram_secret_read_fixed_own_route():
 class Client:
  def __init__(self):self.requests=[]
  def open(self,request,**kw):
   self.requests.append(request)
   if len(self.requests)==1:return Response(KEY.encode())
   return Response({'ok':True,'result':{'id':9,'is_bot':True,'username':'synthetic_bot','extra':KEY}})
 op=Client();client=http.TelegramHTTP(17,'synthetic-job','http://127.0.0.1:8000',opener=op)
 result=client.call('getMe')
 assert result=={'id':9,'is_bot':True,'username':'synthetic_bot'}
 assert op.requests[0].full_url.endswith('/api/apps/17/secrets/bot-token')
 assert op.requests[0].headers['Authorization']=='Bearer synthetic-job'
 assert KEY not in repr(client) and KEY not in str(client.__dict__)

def test_foreign_private_and_group_ignored(bridge):
 for chat,user,kind in [(102,102,'private'),(101,102,'private'),(101,101,'group')]:
  update={'update_id':1,'message':{'chat':{'id':chat,'type':kind},'from':{'id':user},'message_id':1,'text':'do something'}}
  bridge.handle_update(update,bridge.values['settings.json'],bridge.pair,'https://host.test')
 assert not bridge.calls

def test_pair_code_consumed_and_private_identity(bridge):
 settings={'enabled':True,'pairingCode':'SYNTHETICCODE'}
 update={'update_id':2,'message':{'chat':{'id':101,'type':'private'},'from':{'id':101},'text':'/pair SYNTHETICCODE'}}
 result=bridge.handle_update(update,settings,None,'')
 assert result['userId']==101 and bridge.values['settings.json']['pairingCode'] is None

def test_fresh_routing_rejects_foreign_selection_and_keeps_cid(bridge):
 bridge.values['conversation.json']={'chatId':'foreign'}
 with pytest.raises(bridge.BridgeError):bridge.ensure_conversation(bridge.pair)
 assert not any(c[0]=='api' and c[2].get('method')=='POST' for c in bridge.calls)

def test_unknown_pending_status_fails_closed(bridge):
 bridge.rows[0].pop('pending_question_id')
 with pytest.raises(bridge.BridgeError):bridge.sync_question_state('')

def test_pending_original_card_without_telegram_state_blocks(bridge):
 bridge.rows[0]['pending_question_id']='card-exact'
 pending=bridge.sync_question_state('')
 assert pending['external'] and pending['questionId']=='card-exact'
 with pytest.raises(bridge.BridgeError):bridge.chat_callback('go:own-a',bridge.pair,'',{})

def card(bridge):
 question={'id':'q-identity','question':'Do this exact long canonical prompt?','multiSelect':False,
  'options':[{'id':'option-a','label':'Canonical option A','effect':'continue'},{'id':'option-b','label':'Canonical option B','effect':'close'}]}
 state={'nonce':'nonce','questionId':'card-exact','mobiusChatId':'own-a','telegramChatId':101,'telegramMessageId':45,
  'pairingBinding':hashlib.sha256(json.dumps(bridge.pair,sort_keys=True).encode()).hexdigest(),
  'questions':[question],'selections':{'0':'Canonical option A'},'selectedOptions':{'q-identity':['option-a']}}
 bridge.rows[0]['pending_question_id']='card-exact';bridge.values[bridge.QUESTION_STATE_PATH]=state
 return state

def test_canonical_card_normalization_untruncated(bridge):
 q={'id':'q','question':'q'*800,'options':[{'id':'a','label':'label'*100}]}
 assert bridge.normalize_questions([q])==[q]
 assert bridge.normalize_questions([{'question':'no id','options':[{'label':'A'}]}])==[]

def test_answer_exact_ids_typed_options_and_no_work_turn(bridge,monkeypatch):
 state=card(bridge);sent=[]
 old=bridge.request_json
 def request(path,**kw):
  if path.endswith('/messages'):sent.append(kw['body']);return {'status':'answered','answer_turn':'none'}
  return old(path,**kw)
 monkeypatch.setattr(bridge,'request_json',request)
 monkeypatch.setattr(bridge,'read_agent_stream',lambda *a,**kw:pytest.fail('must not read no-work stream'))
 assert bridge.submit_question_state(state,bridge.pair,'')
 assert sent[0]['question_id']=='card-exact' and sent[0]['answers']=={'q-identity':'Canonical option A'}
 assert sent[0]['selected_options']=={'q-identity':['option-a']}

def test_typed_label_must_not_become_close_option(bridge,monkeypatch):
 state=card(bridge);state['selectedOptions']={};state['selections']={'0':'Canonical option B'}
 bridge.values[bridge.QUESTION_STATE_PATH]=copy.deepcopy(state);sent=[];old=bridge.request_json
 def request(path,**kw):
  if path.endswith('/messages'):sent.append(kw['body']);return {'status':'answered','answer_turn':'none'}
  return old(path,**kw)
 monkeypatch.setattr(bridge,'request_json',request)
 bridge.submit_question_state(state,bridge.pair,'')
 assert not sent[0].get('selected_options')

def test_409_does_not_retire_open_card(bridge,monkeypatch):
 state=card(bridge);old=bridge.request_json
 def request(path,**kw):
  if path.endswith('/messages'):raise bridge.BridgeError(status=409)
  return old(path,**kw)
 monkeypatch.setattr(bridge,'request_json',request)
 bridge.submit_question_state(state,bridge.pair,'')
 assert bridge.values[bridge.QUESTION_STATE_PATH]['questionId']=='card-exact'
 assert next(iter(bridge.values['telegram-answer-attempts.json'].values()))['state']=='uncertain'

def test_replayed_submission_no_post_or_history(bridge):
 bridge._update_context.update={'update_id':77}
 cid=bridge.message_cid('telegram');bridge.values['telegram-attempts.json']={cid:{'cid':cid,'chatId':'own-a','state':'uncertain'}}
 bridge.ask_mobius(bridge.pair,'synthetic message','')
 assert not any(c[0]=='api' and (c[2].get('method')=='POST' or c[1].startswith('/api/chats/')) for c in bridge.calls)

def test_telegram_key_text_not_sent_to_model(bridge):
 bridge.ask_mobius(bridge.pair,'my key '+KEY,'')
 assert not any(c[0]=='api' for c in bridge.calls)

def test_outbound_reservation_fences_uncertain_send(bridge,monkeypatch):
 # Restore original transport wrapper isolated from its fixture mock.
 source=ROOT.joinpath('bridge.py').read_text();import ast
 node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='telegram')
 namespace=vars(bridge);exec(compile(ast.Module(body=[node],type_ignores=[]),str(ROOT/'bridge.py'),'exec'),namespace)
 class Transport:
  calls=0
  def call(self,*a):self.calls+=1;raise http.TelegramError(reason='lost-response')
 trans=Transport();monkeypatch.setattr(bridge,'_transport',trans);bridge._update_context.update={'update_id':80}
 for _ in range(2):
  with pytest.raises(bridge.BridgeError):bridge.telegram('sendMessage',{'chat_id':101,'text':'synthetic result'})
 assert trans.calls==1
 assert list(bridge.values['telegram-outbox.json'].values())[0]['state']=='uncertain'

def test_sensitive_setup_no_implicit_start_and_no_wrong_bot_write():
 import connect_telegram as setup
 calls=[]
 def inspect(key,method,params=None):return {'id':9,'is_bot':True,'username':'synthetic_bot'} if method=='getMe' else {'url':''}
 def api(method,name,body=None):calls.append((method,name,body));return None
 fields={'bot_token':KEY};setup.connect(fields,17,api,inspect)
 assert [c[:2] for c in calls]==[('GET','bot-identity'),('PUT','bot-token'),('PUT','bot-identity')]
 calls.clear()
 def mismatch(method,name,body=None):calls.append((method,name,body));return {'id':10}
 with pytest.raises(ValueError):setup.connect(fields,17,mismatch,inspect)
 assert not any(c[0]=='PUT' for c in calls)

def test_setup_app_process_cannot_open_sealed_consumer(monkeypatch):
 import trusted_setup
 monkeypatch.setenv('APP_TOKEN','synthetic-frame');monkeypatch.setenv('CHAT_ID','synthetic-chat')
 monkeypatch.setattr(trusted_setup,'platform',lambda:pytest.fail('must reject before platform import'))
 with pytest.raises(ValueError):trusted_setup.installed_context(17)

def test_read_controls_do_not_overtake_ordered_mutations():
 from bridge_loop import responsive_control
 for cb in ['chats:0','chat:own-a','cmd:model','mdl:p:codex','studio:view:synthetic-bot']:assert responsive_control({'callback_query':{'data':cb}})
 for cb in ['go:own-a','cmd:new','mdl:s:codex:model-a','q:nonce:0:0','s:nonce']:assert not responsive_control({'callback_query':{'data':cb}})

def test_manifest_supported_source_closure():
 manifest=json.loads((ROOT/'mobius.json').read_text())
 assert manifest['permissions']=={'job_secret_read':['bot-token']}
 assert 'service' not in manifest and 'capabilities' not in manifest
 assert not any('mini' in f or 'topic' in f for f in manifest['source_files'])
 assert not any(p.is_symlink() for p in ROOT.rglob('*'))

def test_listener_persists_intake_before_cursor_and_orders_work():
 from contextlib import nullcontext
 from types import SimpleNamespace
 from bridge_loop import run_listener
 values={};writes=[];seen=[];polls=[];release=threading.Event();started=threading.Event();menu=threading.Event()
 updates=[{'update_id':1,'message':{'text':'long work'}},{'update_id':2,'callback_query':{'data':'cmd:home'}},{'update_id':3,'message':{'text':'ordered next'}}]
 values['settings.json']={'enabled':True};values['pairing.json']={'chatId':101,'userId':101}
 def put(path,value):values[path]=copy.deepcopy(value);writes.append((path,copy.deepcopy(value)))
 def telegram(method,params):
  assert method=='getUpdates';polls.append(params['offset'])
  if len(polls)==1:return updates
  time.sleep(.015);return []
 def dispatch(update,*args):
  if update['update_id']==1:seen.append(1);started.set();release.wait(2)
  elif update['update_id']==2:menu.set();seen.append(2)
  else:seen.append(3)
 bridge=SimpleNamespace(storage_get=lambda p:values.get(p),storage_put=put,telegram=telegram,dispatch_update=dispatch,
  inbox_lease=nullcontext,acknowledge_received_callback=lambda *a:False,RUN_SECONDS=.15,MAINTENANCE_SECONDS=100,
  APP_ID=17,now=lambda:'synthetic',BridgeError=Exception)
 result=[];thread=threading.Thread(target=lambda:result.append(run_listener(bridge,{}, {'runtime_dir':'synthetic'},'synthetic_bot')))
 thread.start();assert started.wait(1);assert menu.wait(1);assert 3 not in seen
 release.set();thread.join(3);assert not thread.is_alive();assert result==[0]
 assert seen.index(1)<seen.index(3)
 cursor_write=next(i for i,w in enumerate(writes) if w[0]=='bridge-runtime.json' and w[1].get('offset')==4)
 intake_write=next(i for i,w in enumerate(writes) if w[0]=='telegram-inbox.json' and len(w[1]['updates'])==3)
 assert intake_write<cursor_write
 assert values['telegram-inbox.json']['updates']==[]

def test_actual_button_tracks_option_identity(bridge,monkeypatch):
 state=card(bridge);state['selections']={};state['selectedOptions']={};bridge.values[bridge.QUESTION_STATE_PATH]=state
 observed=[]
 monkeypatch.setattr(bridge,'submit_question_state',lambda s,*a:observed.append(copy.deepcopy(s)))
 callback={'id':'cb','from':{'id':101},'message':{'message_id':45,'chat':{'id':101,'type':'private'}},'data':'q:nonce:0:1'}
 bridge.handle_callback_query(callback,bridge.pair,'')
 assert observed[0]['selectedOptions']=={'q-identity':['option-b']}

def test_actual_typed_answer_clears_option_identity(bridge,monkeypatch):
 state=card(bridge);state['awaitingTextQuestion']=0;bridge.values[bridge.QUESTION_STATE_PATH]=state
 observed=[];monkeypatch.setattr(bridge,'submit_question_state',lambda s,*a:observed.append(copy.deepcopy(s)))
 bridge.handle_pending_text_answer({'text':'Canonical option B'},bridge.pair,'')
 assert observed[0]['selectedOptions']=={}

def test_unmatched_card_callback_never_submits(bridge,monkeypatch):
 card(bridge);monkeypatch.setattr(bridge,'submit_question_state',lambda *a:pytest.fail('stale submit'))
 callback={'id':'cb','from':{'id':101},'message':{'message_id':45,'chat':{'id':101,'type':'private'}},'data':'q:other:0:0'}
 bridge.handle_callback_query(callback,bridge.pair,'')
 assert bridge.values[bridge.QUESTION_STATE_PATH]['questionId']=='card-exact'

def test_studio_metadata_checks_matching_fresh_runtime(bridge,monkeypatch):
 import bridge_assistants
 calls=[]
 def request(path,**kw):
  calls.append(path)
  if path.endswith('/catalog'):return {'app_id':18,'navigation_contract':'owner-metadata-v1','assistants':[{'id':'synthetic-bot','name':'Synthetic Bot','development':{'status':'Not connected'},'private_participant_notes':'must not render'}]}
  if path=='/api/apps/18':return {'id':18,'frame_version':'v1','storage_generation':'g1','capability_contract':{'service':{'id':'wrong-service'}}}
  raise AssertionError()
 monkeypatch.setattr(bridge,'request_json',request)
 with pytest.raises(bridge.BridgeError):bridge_assistants.catalog(bridge)
 assert calls==['/api/services/assistant-studio/owner/catalog','/api/apps/18']

def test_inflight_key_change_is_not_used():
 class Changing:
  count=0
  def open(self,request,**kw):
   self.count+=1
   if '/secrets/' in request.full_url:return Response((KEY if self.count<3 else '999999:'+('B'*40)).encode())
   return Response({'ok':True,'result':{'id':9,'is_bot':True,'username':'synthetic_bot'}})
 op=Changing();client=http.TelegramHTTP(17,'synthetic-job','http://127.0.0.1:8000',opener=op)
 client.call('getMe')
 with pytest.raises(http.TelegramError) as e:client.call('sendMessage',{'chat_id':101,'text':'synthetic'})
 assert e.value.reason=='key-changed' and op.count==3

def test_newer_pending_card_still_blocks_after_retirement(bridge):
 card(bridge);bridge.rows[0]['pending_question_id']='newer-exact-card'
 state=bridge.sync_question_state('')
 assert state['external'] and state['questionId']=='newer-exact-card'
 assert bridge.values[bridge.QUESTION_STATE_PATH] is None

def test_public_sealed_prompt_is_bounded_and_run_identity_bound():
 from setup_spec import DESCRIPTION,request_identity
 assert len(DESCRIPTION)<=240
 command=['/synthetic/python','/synthetic/consumer.py','--owner-run','owner-run-a']
 assert request_identity('owner-chat','owner-run-a',command,'/synthetic')!=request_identity('owner-chat','guest-run-b',command,'/synthetic')

def test_multiselect_typed_then_button_never_promotes_prose(bridge,monkeypatch):
 state=card(bridge);state['questions'][0]['multiSelect']=True;state['awaitingTextQuestion']=0;state['selections']={};state['selectedOptions']={};bridge.values[bridge.QUESTION_STATE_PATH]=state
 bridge.handle_pending_text_answer({'text':'Canonical option B'},bridge.pair,'')
 cb={'id':'cb','from':{'id':101},'message':{'message_id':45,'chat':{'id':101,'type':'private'}},'data':'q:nonce:0:0'}
 bridge.handle_callback_query(cb,bridge.pair,'')
 latest=bridge.values[bridge.QUESTION_STATE_PATH]
 assert latest['selections']['0']==['Canonical option B','Canonical option A']
 assert not latest['selectedOptions'].get('q-identity')

def test_primary_menu_navigation_and_ordinary_reply(bridge,monkeypatch):
 text,markup=bridge.owner_home(bridge.pair,'https://host.test','own-a')
 assert 'Synthetic Personal' in text and markup['inline_keyboard']
 monkeypatch.setattr(bridge,'read_agent_stream',lambda *a,**kw:{'kind':'reply','text':'Synthetic final result'})
 old=bridge.request_json
 def request(path,**kw):
  if path.endswith('/messages'):return {'status':'started'}
  return old(path,**kw)
 monkeypatch.setattr(bridge,'request_json',request)
 bridge._update_context.update={'update_id':90}
 bridge.ask_mobius(bridge.pair,'synthetic ordinary text','https://host.test')
 assert bridge.values['telegram-attempts.json']['telegram-17-90']['state']=='accepted'
 assert any(c[0]=='send' and c[1][1]=='Synthetic final result' for c in bridge.calls)

def test_source_has_no_unresolved_runtime_globals():
 import symtable,builtins
 for path in ROOT.glob('*.py'):
  if path.name.startswith('test_'):continue
  table=symtable.symtable(path.read_text(),str(path),'exec');known=set(table.get_identifiers())|set(dir(builtins))|{'__file__'}
  def check(tab):
   for symbol in tab.get_symbols():assert not (symbol.is_global() and symbol.is_referenced() and symbol.get_name() not in known),(path.name,symbol.get_name())
   for child in tab.get_children():check(child)
  check(table)

def test_public_event_log_stream_and_sensitive_card_redirect(bridge,monkeypatch):
 from contextlib import nullcontext
 event={'type':'question','question_id':'approval-exact','action_key':'reviewed-owner-action',
  'questions':[{'id':'approval','question':'Approve privileged work?','options':[{'id':'yes','label':'Approve'}]}]}
 class Stream:
  status=200
  def __enter__(self):return self
  def __exit__(self,*a):pass
  def __iter__(self):return iter([('data: '+json.dumps(event)+'\n').encode()])
 class Op:
  def open(self,req,**kw):
   assert req.full_url=='http://127.0.0.1:8000/api/chats/own-a/stream'
   assert not req.headers.get('X-mobius-stream-snapshot')
   return Stream()
 monkeypatch.setattr(bridge.urllib.request,'build_opener',lambda *a:Op())
 monkeypatch.setattr(bridge,'thinking_indicator',lambda *a,**kw:nullcontext())
 result=bridge.read_agent_stream('own-a',101)
 assert result['ownerOnly']
 assert not bridge.publish_question(101,'own-a',result,'')
 assert bridge.QUESTION_STATE_PATH not in bridge.values

def test_stream_204_is_unknown_not_success(bridge,monkeypatch):
 from contextlib import nullcontext
 class Stream:
  status=204
  def __enter__(self):return self
  def __exit__(self,*a):pass
 class Op:
  def open(self,*a,**kw):return Stream()
 monkeypatch.setattr(bridge.urllib.request,'build_opener',lambda *a:Op())
 monkeypatch.setattr(bridge,'thinking_indicator',lambda *a,**kw:nullcontext())
 assert bridge.read_agent_stream('own-a',101)['kind']=='pending'


@pytest.mark.parametrize('marker',[None,'wrong-contract'])
def test_studio_missing_or_wrong_navigation_contract_denied(bridge,monkeypatch,marker):
 import bridge_assistants
 calls=[]
 def request(path,**kw):
  calls.append(path)
  if path.endswith('/catalog'):return {'app_id':18,'navigation_contract':marker,'assistants':[]}
  raise AssertionError('must deny before shortcuts/runtime resolution')
 monkeypatch.setattr(bridge,'request_json',request)
 with pytest.raises(bridge.BridgeError):bridge_assistants.catalog(bridge)
 assert calls==['/api/services/assistant-studio/owner/catalog']


@pytest.mark.parametrize('requested',['https://foreign.test','http://127.0.0.1:8001'])
def test_sealed_setup_api_origin_is_exact_configured_host(monkeypatch,requested):
 import connect_telegram
 monkeypatch.setenv('API_BASE_URL','http://127.0.0.1:8000')
 assert connect_telegram.local_api_origin('http://127.0.0.1:8000')=='http://127.0.0.1:8000'
 with pytest.raises(ValueError):connect_telegram.local_api_origin(requested)


@pytest.mark.parametrize("text", [KEY, "The new key is "+KEY])
def test_pending_typed_key_never_stored_or_submitted(bridge,monkeypatch,text):
 state=card(bridge);state["awaitingTextQuestion"]=0
 bridge.values[bridge.QUESTION_STATE_PATH]=copy.deepcopy(state)
 before=copy.deepcopy(bridge.values)
 def forbidden(*args,**kwargs):pytest.fail("Credential-looking prose reached write/submit")
 monkeypatch.setattr(bridge,"storage_put",forbidden)
 monkeypatch.setattr(bridge,"submit_question_state",forbidden)
 assert bridge.handle_pending_text_answer({"text":text},bridge.pair,"https://host.test")
 assert bridge.values==before
 assert KEY not in json.dumps(bridge.calls)
 assert any(c[0]=="send" and "secure-input" in c[1][1] for c in bridge.calls)


def test_question_private_media_never_projects_capability_link(bridge):
 state=card(bridge)
 uri='/api/chats/own-a/media/synthetic.png?token=synthetic-private-capability'
 result={'kind':'question','questionId':'card-exact','questions':state['questions'],
  'text':'Inspect '+uri,'baselineText':'Inspect '+uri}
 bridge.deliver_agent_result(bridge.pair,'own-a',result,'https://host.test')
 assert 'synthetic-private-capability' not in json.dumps(bridge.values)
 assert uri not in json.dumps(bridge.calls)


@pytest.mark.parametrize('field',['question','label','description','id'])
def test_canonical_private_media_card_redirects_without_reinterpretation(bridge,field):
 state=card(bridge);questions=copy.deepcopy(state['questions'])
 uri='/api/chats/own-a/media/synthetic.png?token=synthetic-private-capability'
 if field=='question':questions[0][field]=uri
 else:questions[0]['options'][0][field]=uri
 # No cached safe representation may be confused with the original unsafe card.
 bridge.values[bridge.QUESTION_STATE_PATH]=None
 result={'kind':'question','questionId':'card-exact','questions':questions,'text':'Safe lead','baselineText':'Safe lead'}
 bridge.deliver_agent_result(bridge.pair,'own-a',result,'https://host.test')
 assert bridge.values[bridge.QUESTION_STATE_PATH] is None
 assert uri not in json.dumps(bridge.calls)
 assert any(c[0]=='send' and 'saved card' in c[1][1] for c in bridge.calls)
 assert bridge.sync_question_state('')['questionId']=='card-exact'


def test_safe_card_preserves_all_canonical_option_identity(bridge):
 state=card(bridge);questions=copy.deepcopy(state['questions'])
 bridge.values[bridge.QUESTION_STATE_PATH]=None
 assert bridge.publish_question(101,'own-a',{'questionId':'card-exact','questions':questions,'text':'Safe lead'},'')
 assert bridge.values[bridge.QUESTION_STATE_PATH]['questions']==questions


def test_rejected_credential_receipt_preserves_pending_card_and_pairing(bridge):
 from bridge_loop import admit_update
 state=card(bridge);before=copy.deepcopy(bridge.values)
 update={'update_id':93,'message':{'chat':{'id':101,'type':'private'},'from':{'id':101},'message_id':8,'text':KEY}}
 projected=admit_update(update)
 assert bridge.handle_update(projected,bridge.values['settings.json'],bridge.pair,'')==bridge.pair
 assert bridge.values==before
 assert KEY not in json.dumps(bridge.calls)
 assert not any(c[0]=='api' for c in bridge.calls)
 assert any(c[0]=='send' and 'secure-input' in c[1][1] for c in bridge.calls)


@pytest.mark.parametrize('pair,chat,user,kind',[(None,101,101,'private'),('paired',102,102,'private'),('paired',101,102,'private'),('paired',101,101,'group')])
def test_rejected_input_cannot_admit_unpaired_foreign_or_group(bridge,pair,chat,user,kind):
 from bridge_loop import admit_update
 pairing=bridge.pair if pair else None
 update=admit_update({'update_id':92,'message':{'chat':{'id':chat,'type':kind},'from':{'id':user},'text':KEY}})
 bridge.handle_update(update,bridge.values['settings.json'],pairing,'')
 assert bridge.calls==[]


def test_parallel_status_updates_keep_both_content_free_events(bridge,monkeypatch):
 barrier=threading.Barrier(2);errors=[]
 def worker(label):
  try:barrier.wait(2);bridge.activity(label)
  except Exception as exc:errors.append(exc)
 threads=[threading.Thread(target=worker,args=(label,)) for label in ('Synthetic one','Synthetic two')]
 for t in threads:t.start()
 for t in threads:t.join(3);assert not t.is_alive()
 assert errors==[]
 assert {v['label'] for v in bridge.values['status.json']['events']}=={'Synthetic one','Synthetic two'}


def test_retired_permission_callers_and_raw_key_frame_are_absent():
 manifest=json.loads((ROOT/'mobius.json').read_text())
 assert manifest['permissions']=={'job_secret_read':['bot-token']}
 assert 'service' not in manifest and 'miniapp' not in manifest and 'owner_actions' not in manifest
 for name in ('bridge.py','bridge_assistants.py','index.jsx'):
  source=(ROOT/name).read_text()
  for route in ('/credentialed-fetch','/owner-screenshot','/chat-connections','/filing','/owner-actions'):
   assert route not in source
 ui=(ROOT/'index.jsx').read_text()
 assert '<input' not in ui and '<textarea' not in ui
 assert 'APP_OWNER_ACTION' not in (ROOT/'owner.py').read_text().split('if __name__')[0].replace('# No ordinary input, pasted instruction, APP_OWNER_ACTION or owner token file.','')


@pytest.mark.parametrize('reason,status,expected',[('not-modified',400,'none'),('edit-unavailable',400,'send'),('',503,'raise')])
def test_navigation_fallback_only_for_definite_missing_edit(bridge,monkeypatch,reason,status,expected):
 def fail(*args,**kwargs):raise bridge.BridgeError('Synthetic safe error',status=status,reason=reason)
 monkeypatch.setattr(bridge,'telegram',fail)
 if expected=='raise':
  with pytest.raises(bridge.BridgeError):bridge.navigation_reply(101,'Menu',{}, {'message_id':45})
 else:bridge.navigation_reply(101,'Menu',{}, {'message_id':45})
 assert sum(c[0]=='send' for c in bridge.calls)==(1 if expected=='send' else 0)


def test_expired_callback_ack_does_not_block_ordered_new_chat(bridge,monkeypatch):
 def fail(method,*args,**kwargs):
  if method=='answerCallbackQuery':raise bridge.BridgeError(status=400)
 monkeypatch.setattr(bridge,'telegram',fail)
 created=[];monkeypatch.setattr(bridge,'ensure_conversation',lambda *args:created.append(True) or 'new-own')
 callback={'id':'cb','from':{'id':101},'message':{'chat':{'id':101,'type':'private'},'message_id':45},'data':'cmd:new'}
 bridge.handle_callback_query(callback,bridge.pair,'')
 assert created==[True] and 'conversation.json' not in bridge.values


def test_native_menu_is_private_scoped_and_revoked_menu_removed(bridge):
 runtime={}
 assert bridge.sync_bot_commands(bridge.pair,runtime,'synthetic_bot')
 assert not bridge.sync_bot_commands(bridge.pair,runtime,'synthetic_bot')
 calls=[c for c in bridge.calls if c[0]=='telegram']
 assert calls[1][1][1]['scope']=={'type':'chat','chat_id':101}
 assert calls[-1][1][1]['menu_button']=={'type':'commands'}
 bridge.calls.clear()
 assert bridge.sync_bot_commands(None,runtime,'synthetic_bot')
 assert any(c[1][0]=='deleteMyCommands' and c[1][1]['scope']['chat_id']==101 for c in bridge.calls)


def test_nontext_input_is_not_an_implicit_media_transfer(bridge):
 update={'message':{'message_id':8,'chat':{'id':101,'type':'private'},'from':{'id':101},'photo':[{'file_id':'synthetic'}]}}
 bridge.handle_update(update,bridge.values['settings.json'],bridge.pair,'')
 assert all(c[0]=='send' for c in bridge.calls)
 assert 'text messages only' in bridge.calls[0][1][1]


def test_reply_progress_private_links_and_canonical_final(bridge,monkeypatch):
 shown=[]
 class Progress:
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def show(self,text):shown.append(text)
 class Stream:
  status=200
  def __enter__(self):return self
  def __exit__(self,*args):pass
  def __iter__(self):
   for event in [{'type':'text','text_item_id':'a','content':'Hello'}, {'type':'text','text_item_id':'a','content':' there'},
     {'type':'text_final','text_item_id':'a','content':'Final ![image](/api/chats/own-a/media/a.png?token=synthetic-private)'},{'type':'done'}]:
    yield ('data: '+json.dumps(event)).encode()
 class Opener:
  def open(self,*args,**kwargs):return Stream()
 monkeypatch.setattr(bridge,'thinking_indicator',lambda *args:Progress())
 monkeypatch.setattr(bridge.urllib.request,'build_opener',lambda *args:Opener())
 result=bridge.read_agent_stream('own-a',101)
 assert shown[:2]==['Hello','Hello there'] and 'synthetic-private' not in json.dumps(shown)
 bridge.deliver_agent_result(bridge.pair,'own-a',result,'https://host.test')
 assert 'synthetic-private' not in json.dumps(bridge.calls)
 assert any(c[0]=='send' and c[2]['reply_markup']['inline_keyboard'][0][0]['url']=='https://host.test/shell/?chat=own-a' for c in bridge.calls)


def studio_responses(bridge,monkeypatch,*,after_id=18,current_rows='valid'):
 first={'app_id':18,'navigation_contract':'owner-metadata-v1','assistants':[{'id':'synthetic-bot','name':'Synthetic Bot','development':{'status':'Not connected'}}]}
 current=copy.deepcopy(first)
 if current_rows!='valid':current['assistants']=None
 app={'id':18,'frame_version':'v1','storage_generation':'g1','capability_contract':{'service':{'id':'assistant-studio'}}}
 catalog_reads=0;app_reads=0
 def request(path,**kwargs):
  nonlocal catalog_reads,app_reads
  if path.endswith('/catalog'):
   catalog_reads+=1;return copy.deepcopy(first if catalog_reads==1 else current)
  if path=='/api/apps/18':
   app_reads+=1;return {**copy.deepcopy(app),'id':18 if app_reads==1 else after_id}
  pytest.fail('Unexpected route')
 monkeypatch.setattr(bridge,'request_json',request)


def test_studio_second_runtime_identity_is_exact(bridge,monkeypatch):
 import bridge_assistants
 studio_responses(bridge,monkeypatch,after_id=19)
 with pytest.raises(bridge.BridgeError):bridge_assistants.catalog(bridge)


def test_malformed_optional_studio_is_unavailable_not_listener_failure(bridge,monkeypatch):
 import bridge_assistants
 studio_responses(bridge,monkeypatch,current_rows=None)
 bridge_assistants.show(bridge,bridge.pair,'')
 assert any(c[0]=='send' and 'unavailable' in c[1][1] for c in bridge.calls)


def test_model_picker_preserves_owner_hidden_preferences(bridge,monkeypatch):
 bridge._model_cache=None
 def request(path,**kwargs):
  if path=='/api/models':return {'providers':{'codex':[{'id':'shown','available':True},{'id':'hidden','available':True}]}}
  if path=='/api/owner/model-prefs':return {'hidden_ids':['hidden']}
  pytest.fail('Unexpected route')
 monkeypatch.setattr(bridge,'request_json',request)
 assert [item['id'] for item in bridge.available_models(refresh=True)['codex']]==['shown']


def model_callback():
 return {'id':'model-cb','from':{'id':101},'message':{'message_id':45,'chat':{'id':101,'type':'private'}},'data':'mdl:s:codex:model-b'}


def test_model_change_preserves_old_chat_and_uses_fresh_selection(bridge,monkeypatch):
 old=bridge.request_json;created=[]
 def request(path,**kwargs):
  if path=='/api/models':return {'providers':{'codex':[{'id':'model-a','available':True},{'id':'model-b','label':'Model B','available':True}]}}
  if path=='/api/app-chats' and kwargs.get('method')=='POST':
   body=copy.deepcopy(kwargs['body']);created.append(body)
   bridge.rows.append({'id':'own-b','created_by_app_id':17,'scope':'telegram:101','pending_question_id':None,**body})
   return {'id':'own-b'}
  return old(path,**kwargs)
 monkeypatch.setattr(bridge,'request_json',request)
 bridge.handle_callback_query(model_callback(),bridge.pair,'https://host.test')
 assert bridge.values['conversation.json']['chatId']=='own-b'
 assert any(row['id']=='own-a' for row in bridge.rows)
 assert created[0]['model']=='model-b' and created[0]['provider']=='codex' and created[0]['scope']=='telegram:101'
 assert 'Bridge' in created[0]['system_prompt']


def test_model_change_cannot_abandon_original_pending_card(bridge,monkeypatch):
 card(bridge);before=copy.deepcopy(bridge.values)
 old=bridge.request_json
 def request(path,**kwargs):
  if path=='/api/models':return {'providers':{'codex':[{'id':'model-b','available':True}]}}
  return old(path,**kwargs)
 monkeypatch.setattr(bridge,'request_json',request)
 bridge.handle_callback_query(model_callback(),bridge.pair,'')
 assert bridge.values==before
 assert not any(c[0]=='api' and c[2].get('method')=='POST' for c in bridge.calls)


def test_unavailable_model_callback_cannot_mutate_routing(bridge,monkeypatch):
 before=copy.deepcopy(bridge.values);old=bridge.request_json
 def request(path,**kwargs):
  if path=='/api/models':return {'providers':{'codex':[{'id':'model-b','available':False}]}}
  return old(path,**kwargs)
 monkeypatch.setattr(bridge,'request_json',request)
 bridge.handle_callback_query(model_callback(),bridge.pair,'')
 assert bridge.values==before
