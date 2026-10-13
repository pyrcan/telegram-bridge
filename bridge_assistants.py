"""Optional Studio shortcuts: fresh identity/runtime metadata, no grant writer."""
import re

def read_control(data):
 return data=='cmd:assistants' or data.startswith(('studio:list:','studio:view:'))


def catalog(bridge):
 value=bridge.request_json('/api/services/assistant-studio/owner/catalog')
 if not isinstance(value,dict) or value.get('navigation_contract')!='owner-metadata-v1' or type(value.get('app_id')) is not int or value['app_id']<=0 or not isinstance(value.get('assistants'),list):
  raise bridge.BridgeError('Studio metadata is unavailable.')
 def runtime_identity(app):
  if not isinstance(app,dict) or type(app.get('id')) is not int or app['id']!=value['app_id']:
   raise bridge.BridgeError('Studio runtime does not match its metadata.')
  contract=app.get('capability_contract');service=contract.get('service') if isinstance(contract,dict) else None
  if not isinstance(service,dict) or service.get('id')!='assistant-studio' or not app.get('frame_version') or not app.get('storage_generation'):
   raise bridge.BridgeError('Studio runtime does not match its metadata.')
  return app['frame_version'],app['storage_generation']
 app=bridge.request_json(f"/api/apps/{value['app_id']}")
 before=runtime_identity(app)
 # Both metadata and runtime identity are fresh accepted-service reads.
 current=bridge.request_json('/api/services/assistant-studio/owner/catalog')
 after=bridge.request_json(f"/api/apps/{value['app_id']}")
 if (not isinstance(current,dict) or current.get('navigation_contract')!='owner-metadata-v1'
  or type(current.get('app_id')) is not int or current['app_id']!=value['app_id']
  or not isinstance(current.get('assistants'),list) or runtime_identity(after)!=before):
  raise bridge.BridgeError('Studio changed; refresh its metadata.')
 allowed=[]
 for row in current.get('assistants',[]):
  if not isinstance(row,dict) or not isinstance(row.get('id'),str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',row['id']) or not isinstance(row.get('name'),str):raise bridge.BridgeError('Studio metadata is unavailable.')
  if any(row.get(field) is not None and not isinstance(row[field],dict) for field in ('development','connection','editing_chat')):
   raise bridge.BridgeError('Studio metadata is unavailable.')
  development=row.get('development') or {};connection=row.get('connection') or {};editing=row.get('editing_chat') or {}
  allowed.append({'id':row['id'],'name':row['name'][:160],
   'status':str(development.get('status') or 'Review in Studio')[:160],
   'test_label':str(development.get('test_label') or 'Review in Studio')[:160],
   'release_label':str(development.get('release_label') or 'Review in Studio')[:160],
   'username':connection.get('username') if isinstance(connection.get('username'),str) and re.fullmatch(r'[A-Za-z0-9_]{1,64}',connection['username']) else None,
   'editing_chat_id':editing.get('id') if isinstance(editing.get('id'),str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}',editing['id']) else None})
 return {'app_id':current['app_id'],'assistants':allowed}


def show(bridge,pairing,origin,identity=None,page=0,message=None):
 try:value=catalog(bridge)
 except bridge.BridgeError:
  rows=[[{'text':'Check again','callback_data':'cmd:assistants'}]]
  bridge.navigation_reply(int(pairing['chatId']),'Optional Telegram Bot Studio metadata is unavailable or not authorized. Your personal Bridge works without it. Installing or linking apps grants no access.',{'inline_keyboard':rows},message);return
 rows=[];items=value['assistants']
 if identity:
  bot=next((b for b in items if b['id']==identity),None)
  if not bot:bridge.navigation_reply(int(pairing['chatId']),'Bot unavailable. Refresh Your bots.',{'inline_keyboard':[[{'text':'Your bots','callback_data':'cmd:assistants'}]]},message);return
  text=f"{bot['name']}\n{bot['status']}\nYour test: {bot['test_label']}\nPublished: {bot['release_label']}\n\nNavigation only. Setup, customization and access management stay in Möbius."
  if bot['username']:rows.append([{'text':'Open bot','url':'https://t.me/'+bot['username']}])
  if origin and bot['editing_chat_id']:rows.append([{'text':'Customize in Möbius','url':origin+'/shell/?chat='+bot['editing_chat_id']}])
  rows.append([{'text':'‹ Your bots','callback_data':'cmd:assistants'}])
 else:
  page=max(0,min(page,max(0,(len(items)-1)//8)))
  text='Your bots · optional Studio metadata\nNo participant conversations or notes are shown.'
  if not items:text+='\nNo bots yet. Create one in Studio.'
  rows=[[{'text':b['name'][:64],'callback_data':'studio:view:'+b['id']}] for b in items[page*8:(page+1)*8]]
  nav=[]
  if page:nav.append({'text':'‹ Previous','callback_data':f'studio:list:{page-1}'})
  if (page+1)*8<len(items):nav.append({'text':'Next ›','callback_data':f'studio:list:{page+1}'})
  if nav:rows.append(nav)
 if origin:rows.append([{'text':'Open Studio','url':f"{origin}/shell/?app={value['app_id']}"}])
 bridge.navigation_reply(int(pairing['chatId']),text,{'inline_keyboard':rows},message)


def callback(bridge,data,pairing,origin,message=None):
 if data=='cmd:assistants':show(bridge,pairing,origin,message=message);return
 parts=data.split(':')
 if len(parts)==3 and parts[:2]==['studio','list'] and parts[2].isdigit() and len(parts[2])<7:show(bridge,pairing,origin,page=int(parts[2]),message=message);return
 if len(parts)==3 and parts[:2]==['studio','view'] and re.fullmatch(r'[A-Za-z0-9_-]{1,64}',parts[2]):show(bridge,pairing,origin,identity=parts[2],message=message);return
 bridge.navigation_reply(int(pairing['chatId']),'This bot control is not available in this edition. Open Studio in Möbius.',{'inline_keyboard':[[{'text':'Your bots','callback_data':'cmd:assistants'}]]},message)
