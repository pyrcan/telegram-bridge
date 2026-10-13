"""Run ONLY with public worktree wt-pytest; all DB/auth/data are disposable."""
import os
import io
import json
import socket
import urllib.request
import urllib.error
from urllib.parse import urlsplit
from pathlib import Path
import sys
import pytest

if os.environ.get('MOBIUS_TEST_DATABASE_ISOLATED')!='1':
 pytest.skip('Public setup integration requires isolated wt-pytest',allow_module_level=True)
import tests.conftest  # isolate fixture-owned DB BEFORE any app module import
pytest_plugins=['tests.conftest']
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from app import auth as auth_mod,models
from app.broadcast import create_broadcast
from app.chat_event_sink import ChatEventSink,register_active_sink,unregister_active_sink
from app.chat_writer import StartTurn,ClaimSecureInput,SettleSecureInput,get_writer
from app.database import SessionLocal
from app import transcript_rows
from app.config import get_settings
from app.applied_app_runtime import runtime_parent
from setup_spec import TITLE,DESCRIPTION,FIELDS,request_identity
import trusted_setup
import connect_telegram

@pytest.fixture(autouse=True)
def offline(monkeypatch):
 def blocked(*args,**kwargs):raise AssertionError("Unmocked network is forbidden")
 monkeypatch.setattr(socket.socket,"connect",blocked)
 monkeypatch.setattr(socket.socket,"connect_ex",blocked)
 monkeypatch.setattr(socket,"create_connection",blocked)
 monkeypatch.setattr(urllib.request,"urlopen",blocked)
 monkeypatch.setattr(urllib.request.OpenerDirector,"open",blocked)



def test_saved_consumer_canonical_identity_and_plain_app_authority(client,chat,db,owner_token,monkeypatch,tmp_path,capsys):
 owner=db.query(models.Owner).first()
 app=models.App(source_dir=str(tmp_path/'source'),name='Telegram Bridge',slug='telegram-bridge',description='Synthetic',jsx_source='export default function App(){return null}',compiled_path=str(tmp_path/'compiled.js'),runtime_revision='a'*64,capability_contract={'data':{'job_secret_read':['bot-token']}})
 db.add(app);db.commit();db.refresh(app)
 root=runtime_parent(app.id)/app.runtime_revision;root.mkdir(parents=True)
 monkeypatch.setattr(trusted_setup,'__file__',str(root/'trusted_setup.py'))
 monkeypatch.setenv('CHAT_ID',chat.id);monkeypatch.delenv('APP_TOKEN',raising=False);monkeypatch.delenv('AGENT_TOKEN',raising=False)
 run_id='synthetic-owner-run'
 get_writer().submit(StartTurn(chat_id=chat.id,run_token=run_id,user_msg={'role':'user','content':'Synthetic secure setup','ts':1})).result(timeout=5)
 bc=create_broadcast(chat.id);sink=ChatEventSink(bc,chat.id,run_token=run_id);register_active_sink(chat.id,sink)
 bearer=auth_mod.create_agent_token(chat.id,owner.username,owner.token_epoch,run_id=run_id)
 command=[sys.executable,str(root/'connect_telegram.py'),'--app-id',str(app.id),'--nonce',app.token_nonce,'--revision',app.runtime_revision,'--api-base','http://127.0.0.1:9','--owner-run',run_id]
 try:
  r=client.post(f'/api/secure-inputs/{chat.id}/saved',headers={'Authorization':'Bearer '+bearer},json={'title':TITLE,'description':DESCRIPTION,'mode':'sealed','fields':FIELDS,'command':command,'cwd':str(root),'action':'run'})
  assert r.status_code==200,r.text
  qid=r.json()['question_id'];assert qid==request_identity(chat.id,run_id,command,str(root))
  monkeypatch.setattr(trusted_setup,'platform',lambda:(auth_mod,models,SessionLocal,runtime_parent))
  monkeypatch.setenv('AGENT_TOKEN',bearer)
  prepared=trusted_setup.installed_context(app.id,owner_prepare=True)
  assert prepared['owner_run']==run_id
  monkeypatch.delenv('AGENT_TOKEN')
  def preflight(**overrides):
   args=dict(expected_nonce=app.token_nonce,expected_revision=app.runtime_revision,command=command,owner_run=run_id)
   args.update(overrides)
   return trusted_setup.installed_context(app.id,**args)
  # A known chat/command is not submitted input. Public writer owns admission.
  with pytest.raises(ValueError):preflight()
  assert get_writer().submit(ClaimSecureInput(chat_id=chat.id,request_id=qid)).result(timeout=5)['status']=='claimed'
  ctx=trusted_setup.installed_context(app.id,expected_nonce=app.token_nonce,expected_revision=app.runtime_revision,command=command,owner_run=run_id)
  claims=auth_mod.decode_access_token(ctx['bearer'])
  assert claims['scope']=='app' and claims['app_id']==app.id and claims['app_nonce']==app.token_nonce
  assert not any(k in claims for k in ('service','job_secrets','agent_chat','delegation_id'))
  headers={'Authorization':'Bearer '+ctx['bearer']}
  assert client.put(f'/api/apps/{app.id}/secrets/bot-token',headers=headers,json={'value':'synthetic-key-only'}).status_code==204
  assert client.get(f'/api/apps/{app.id}/secrets/bot-token',headers=headers).status_code==403
  # Execute the real app consumer, but only in-process TestClient + fake Telegram.
  # No consumer process, key-bearing shell argument or live HTTP is launched.
  key='123456:'+('A'*40)
  calls=[]
  class Response:
   def __init__(self,body,code=200):self.body=body;self.code=code
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,size=-1):return self.body[:size] if size>=0 else self.body
  class LocalOnly:
   def open(self,request,**kwargs):
    parsed=urlsplit(request.full_url)
    if parsed.scheme=='https' and parsed.netloc=='api.telegram.org':
     method=parsed.path.rsplit('/',1)[1]
     assert parsed.path=='/bot'+key+'/'+method and method in ('getMe','getWebhookInfo')
     assert request.method=='POST'
     calls.append(('telegram',method))
     result={'id':9,'is_bot':True,'username':'synthetic_bot'} if method=='getMe' else {'url':''}
     return Response(json.dumps({'ok':True,'result':result}).encode())
    assert parsed.scheme=='http' and parsed.netloc=='127.0.0.1:9' and not parsed.query
    assert parsed.path in (f'/api/apps/{app.id}/secrets/bot-token',f'/api/storage/apps/{app.id}/bot-identity.json')
    calls.append(('core',request.method,parsed.path))
    response=client.request(request.method,parsed.path,headers=dict(request.header_items()),content=request.data)
    if response.status_code>=400:
     raise urllib.error.HTTPError('http://synthetic.invalid',response.status_code,'Synthetic',{},io.BytesIO(response.content))
    return Response(response.content,response.status_code)
  monkeypatch.setattr(urllib.request,'build_opener',lambda *args:LocalOnly())
  monkeypatch.setattr(connect_telegram,'__file__',str(root/'connect_telegram.py'))
  monkeypatch.setenv('API_BASE_URL','http://127.0.0.1:9')
  monkeypatch.setattr(sys,'argv',[str(root/'connect_telegram.py'),*command[2:]])
  monkeypatch.setattr(sys,'stdin',io.StringIO(json.dumps({'bot_token':key})))
  connect_telegram.main()
  assert calls==[('telegram','getMe'),('telegram','getWebhookInfo'),
   ('core','GET',f'/api/storage/apps/{app.id}/bot-identity.json'),
   ('core','PUT',f'/api/apps/{app.id}/secrets/bot-token'),
   ('core','PUT',f'/api/storage/apps/{app.id}/bot-identity.json')]
  encrypted=Path(get_settings().data_dir)/'app-secrets'/str(app.id)/'bot-token'
  assert key not in encrypted.read_text()
  assert key not in capsys.readouterr().out
  with SessionLocal() as current:
   assert key not in json.dumps(list(transcript_rows.history(current.get(models.Chat,chat.id))))
  # Wrong nonce/runtime/owner-run/card identities fail before minting authority.
  with pytest.raises(ValueError):trusted_setup.installed_context(app.id,expected_nonce='wrong',expected_revision=app.runtime_revision,command=command,owner_run=run_id)
  with pytest.raises(ValueError):trusted_setup.installed_context(app.id,expected_nonce=app.token_nonce,expected_revision='b'*64,command=command,owner_run=run_id)
  with pytest.raises(ValueError):trusted_setup.installed_context(app.id,expected_nonce=app.token_nonce,expected_revision=app.runtime_revision,command=command,owner_run='guest-run')
  with pytest.raises(ValueError):preflight(command=[*command,'unexpected'])
  # Even a real consuming row cannot substitute an older/different pending card.
  with SessionLocal() as current:
   row=current.get(models.Chat,chat.id);row.pending_question_id='different-card';current.commit()
  with pytest.raises(ValueError):preflight()
  with SessionLocal() as current:
   row=current.get(models.Chat,chat.id);row.pending_question_id=qid;current.commit()
   origin=current.get(models.ChatRun,run_id);origin.browser_grant_id='synthetic-guest';current.commit()
  with pytest.raises(ValueError):trusted_setup.installed_context(app.id,expected_nonce=app.token_nonce,expected_revision=app.runtime_revision,command=command,owner_run=run_id)
  with SessionLocal() as current:
   origin=current.get(models.ChatRun,run_id);origin.browser_grant_id=None;current.commit()
  get_writer().submit(SettleSecureInput(chat_id=chat.id,request_id=qid,status='completed',outcome='success')).result(timeout=5)
  with pytest.raises(ValueError):preflight()
  with SessionLocal() as current:
   assert key not in json.dumps(list(transcript_rows.history(current.get(models.Chat,chat.id))))
 finally:unregister_active_sink(chat.id,sink)


def test_public_named_secret_grant_is_not_frame_authority(client,auth,db,tmp_path):
 owner=db.query(models.Owner).first()
 app=models.App(source_dir=str(tmp_path/'source'),name='Synthetic Bridge',slug='telegram-bridge',description='Synthetic',jsx_source='export default function App(){return null}',compiled_path=str(tmp_path/'compiled.js'),capability_contract={'data':{'job_secret_read':['bot-token']}})
 db.add(app);db.commit();db.refresh(app)
 def headers(**claims):
  token=auth_mod.create_app_token(app.id,owner.username,owner.token_epoch,app.token_nonce,**claims)
  return {'Authorization':'Bearer '+token}
 path=f'/api/apps/{app.id}/secrets/bot-token'
 assert client.put(path,headers=auth,json={'value':'synthetic-only'}).status_code==204
 assert client.get(path,headers=headers()).status_code==403
 job=headers(job_secrets=['bot-token'])
 assert client.get(path,headers=job).text=='synthetic-only'
 assert client.get(f'/api/apps/{app.id}/secrets/unapproved',headers=job).status_code==403
 assert client.get(f'/api/apps/{app.id+1}/secrets/bot-token',headers=job).status_code==403
 assert client.post('/api/auth/app-job-token',headers=job,json={'app_id':app.id}).status_code==403
 assert client.post('/api/auth/app-job-token',headers=headers(),json={'app_id':app.id}).status_code==403
 app.capability_contract={'data':{}};db.commit()
 assert client.get(path,headers=job).status_code==403


def test_public_canonical_quiet_close_never_infers_consent_from_prose():
 from app.questions import validate_saved_answer,closes_without_reply,AnswerConflict
 card={'response_mode':'continuation','questions':[{'id':'q','question':'Exact prompt','multiSelect':True,
  'options':[{'id':'close','label':'No further work','on_answer':'close'}, {'id':'reply','label':'Continue','on_answer':'reply'}]}]}
 validate_saved_answer(card,{'q':'No further work'},None)
 assert not closes_without_reply(card,{'q':'No further work'},None)
 assert closes_without_reply(card,{'q':'No further work'},{'q':['close']})
 assert not closes_without_reply(card,{'q':'No further work, Continue'},None)
 with pytest.raises(AnswerConflict):validate_saved_answer(card,{'q':'No further work'},{'q':['reply']})
 with pytest.raises(AnswerConflict):validate_saved_answer(card,{'truncated prompt':'No further work'},None)


def test_manifest_tree_uses_actual_public_validator():
 import importlib.util
 script=Path(tests.conftest.__file__).resolve().parent.parent/'scripts'/'validate-app.py'
 spec=importlib.util.spec_from_file_location('bridge_public_validator',script)
 validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
 manifest=json.loads((ROOT/'mobius.json').read_text())
 validator.validate_manifest_contract(manifest)
 checked=validator.check_manifest_tree(manifest,validator._load_tree(ROOT))
 assert checked.errors==[]
 errors,warnings=validator._referenced_file_findings(ROOT,manifest)
 assert errors==[]
