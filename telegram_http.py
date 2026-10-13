"""Job-local Telegram HTTP. Fixed HTTPS origin, canonical methods, RAM key only."""
import hashlib
import threading
import json
import re
import urllib.error
import urllib.parse
import urllib.request

METHODS=frozenset({'getMe','getWebhookInfo','getUpdates','sendMessage','editMessageText',
 'answerCallbackQuery','setMyCommands','deleteMyCommands','setChatMenuButton',
 'sendChatAction','sendMessageDraft'})
KEY=re.compile(r'[0-9]+:[A-Za-z0-9_-]{20,150}\Z')
MAX_REQUEST=256*1024
MAX_RESPONSE=2*1024*1024

class TelegramError(RuntimeError):
 def __init__(self,code=0,reason=''):
  super().__init__('Telegram request could not be completed.')
  self.code=code if type(code) is int and 100<=code<=599 else 0
  self.reason=reason

class NoRedirect(urllib.request.HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):return None


def safe_origin(origin):
 p=urllib.parse.urlsplit(origin)
 if (p.scheme not in ('https','http') or not p.hostname or p.username or p.password
  or p.path or p.query or p.fragment or (p.scheme=='http' and p.hostname not in ('127.0.0.1','localhost','::1'))):
  raise TelegramError(reason='invalid-origin')
 try:p.port
 except ValueError:raise TelegramError(reason='invalid-origin') from None
 return origin


def bot_identity(bot):
 if (not isinstance(bot,dict) or type(bot.get('id')) is not int or bot['id']<=0
  or bot.get('is_bot') is not True or not isinstance(bot.get('username'),str)
  or not re.fullmatch(r'[A-Za-z0-9_]{1,64}',bot['username'])):raise TelegramError(reason='invalid-response')
 return {'id':bot['id'],'is_bot':True,'username':bot['username']}


def call_key(key,method,params=None,*,opener=None):
 if not isinstance(key,str) or not KEY.fullmatch(key):raise TelegramError(reason='invalid-key')
 if not isinstance(method,str) or method not in METHODS or (params is not None and not isinstance(params,dict)):
  raise TelegramError(reason='invalid-method')
 values=dict(params or {});wait=values.get('timeout',0) if method=='getUpdates' else 0
 if type(wait) is not int or not 0<=wait<=10:raise TelegramError(reason='invalid-request')
 try:data=json.dumps(values,ensure_ascii=False,allow_nan=False).encode()
 except (TypeError,ValueError):raise TelegramError(reason='invalid-request') from None
 if len(data)>MAX_REQUEST:raise TelegramError(reason='request-too-large')
 request=urllib.request.Request('https://api.telegram.org/bot'+key+'/'+method,data=data,
  headers={'Content-Type':'application/json'},method='POST')
 opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 try:
  try:response=opener.open(request,timeout=wait+5)
  except urllib.error.HTTPError as exc:response=exc
  with response:
   status=response.code;raw=response.read(MAX_RESPONSE+1)
  if len(raw)>MAX_RESPONSE:raise TelegramError(reason='response-too-large')
  # A provider response is untrusted. Its key echo must never reach storage/UI.
  raw=raw.replace(key.encode(),b'[redacted]')
  body=json.loads(raw)
  def redact(value):
   if isinstance(value,str):return value.replace(key,'[redacted]')
   if isinstance(value,list):return [redact(v) for v in value]
   if isinstance(value,dict):return {redact(k):redact(v) for k,v in value.items()}
   return value
  body=redact(body)
  if not isinstance(body,dict):raise TelegramError(reason='invalid-response')
 except TelegramError:raise
 except Exception:raise TelegramError(reason='transport-unavailable') from None
 if status!=200 or body.get('ok') is not True:
  description=str(body.get('description','')).lower()
  reason='not-modified' if 'message is not modified' in description else 'edit-unavailable' if any(x in description for x in ('message to edit not found',"message can't be edited",'message_id_invalid')) else ''
  raise TelegramError(code=body.get('error_code',status),reason=reason)
 result=body.get('result')
 return bot_identity(result) if method=='getMe' else result

class TelegramHTTP:
 def __init__(self,app_id,bearer,api_base,*,opener=None):
  if type(app_id) is not int or app_id<=0:raise TelegramError(reason='invalid-app')
  self.app_id=app_id;self._bearer=bearer;self._base=safe_origin(api_base)
  self._fingerprint=None;self._binding_lock=threading.Lock()
  self._opener=opener or urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
 def __repr__(self):return '<TelegramHTTP app-local RAM transport>'
 def call(self,method,params=None):
  # Read with the actual job bearer on every call. Accepted-grant removal fences
  # subsequent API calls; no key is cached on disk, object, or environment.
  key=None
  try:
   request=urllib.request.Request(self._base+f'/api/apps/{self.app_id}/secrets/bot-token',
    headers={'Authorization':'Bearer '+self._bearer})
   with self._opener.open(request,timeout=10) as response:raw=response.read(8193)
   if len(raw)>8192:raise ValueError()
   key=raw.decode()
   fingerprint=hashlib.sha256(key.encode()).digest()
   with self._binding_lock:
    if self._fingerprint is None:self._fingerprint=fingerprint
    elif self._fingerprint!=fingerprint:raise TelegramError(reason='key-changed')
   return call_key(key,method,params,opener=self._opener)
  except TelegramError:raise
  except Exception:raise TelegramError(reason='key-unavailable') from None
  finally:key=None
