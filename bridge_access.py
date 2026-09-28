"""One owner connection with per-bot access controls. No participant content or owner credentials.

Only the notification lane writes its receipts. Ambiguous sends are not replayed;
Users remains the recoverable source of truth. The service exposes only a live
binding assertion to the specifically connected Studio app.
"""
import hashlib
import json
import os
import re
from pathlib import Path
import secrets

CONNECTIONS='owner-access.json'
SCOPE='owned-bots-v1'
RECEIPTS='access-notices.json'
BASE='/api/services/assistant-studio/'


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def connection(bridge,pairing):
    value=bridge.storage_get(CONNECTIONS)
    return value if isinstance(value,dict) and value.get('scope')==SCOPE and value.get('binding')==digest(pairing) else None


def connected(bridge,pairing):
    value=connection(bridge,pairing)
    if not value:return {}
    result=bridge.request_json(BASE+'bridge-access/'+value['grant']+'/bots')
    return {bot['assistant']:bot for bot in result['bots']}


def binding(request,read=None):
    read=read or (lambda name:json.loads((Path(os.environ['APP_STORAGE_DIR'])/name).read_text()))
    parts=request.get('path','').split('/')
    if request.get('method')!='GET' or len(parts)!=2 or parts[0]!='access-binding':raise ValueError()
    if not re.fullmatch(r'[a-f0-9]{12}',parts[1]):raise ValueError()
    actor=request.get('actor') or {}
    found=read(CONNECTIONS) or {}
    if found.get('scope')!=SCOPE or found.get('grant')!=parts[1]:raise ValueError()
    if (request.get('public') or actor.get('scope')!='app' or actor.get('delegated') or not found
        or actor.get('app_id')!=found['studio_app_id']):raise ValueError()
    pair=read('pairing.json');settings=read('settings.json')
    if not pair or not settings or settings.get('enabled') is False or digest(pair)!=found['binding']:raise ValueError()
    return {'binding':found['binding'],'app_id':int(os.environ['APP_ID'])}


def owner_action(request,api):
    # Two owner dialogs can finish concurrently. Serialize the mapping update;
    # each individual storage write remains platform-atomic. No job uses this.
    import fcntl
    if not os.environ.get('AGENT_TOKEN') or os.environ.get('APP_TOKEN'):raise ValueError()
    with (Path(os.environ['APP_STORAGE_DIR'])/'access-connect.lock').open('a') as lock:
        fcntl.flock(lock.fileno(),fcntl.LOCK_EX)
        return _owner_action(request,api)


def _owner_action(request,api):
    """Runs only after trusted confirmation of the current-and-future scope."""
    if not os.environ.get('AGENT_TOKEN') or os.environ.get('APP_TOKEN'):raise ValueError()
    app_id=int(os.environ['APP_ID']);ctx=request['context']
    path=f'/api/storage/apps/{app_id}/{CONNECTIONS}'
    try:previous=api(path) or {}
    except __import__('urllib.error',fromlist=['HTTPError']).HTTPError as exc:
        if exc.code!=404:raise
        previous={}
    if request['action']=='disconnect-access':
        if not previous or previous['grant']!=ctx.get('grant'):raise ValueError('Connection changed')
        api(BASE+'owner/access-bridge',{'app_id':app_id,'grant':previous['grant'],'operation':'disconnect'})
        api(path,{},'PUT');return
    if request['action']!='connect-access' or ctx.get('scope')!=SCOPE:raise ValueError()
    pair=api(f'/api/storage/apps/{app_id}/pairing.json')
    if not pair or int(pair['chatId'])!=int(pair['userId']):raise ValueError('Private pairing required')
    for key,field in [('userId','paired_user_id'),('chatId','paired_chat_id'),('pairedAt','paired_at')]:
        if str(pair[key])!=str(ctx.get(field,'')):raise ValueError('Pairing changed')
    catalog=api(BASE+'owner/catalog')
    grant=previous.get('grant') if previous.get('scope')==SCOPE and previous.get('binding')==digest(pair) else secrets.token_hex(6)
    record={'scope':SCOPE,'app_id':app_id,'grant':grant,'owner_user_id':int(pair['userId']),'binding':digest(pair)}
    api(BASE+'owner/access-bridge',record)
    api(path,{**record,'studio_app_id':catalog['app_id'],'paired_at':pair['pairedAt']},'PUT')


def bot_path(grant):
    return BASE+'bridge-access/'+grant['connection']+'/'+grant['grant']


def users(bridge,grant):
    return bridge.request_json(bot_path(grant)+'/users')


def cb(action,grant,user,review=None):
    value=f"ua:{action}:{grant['grant']}:{user['user_id']}"+((':'+review) if review else '')
    if len(value.encode())>64:raise ValueError('Oversized callback')
    return value


def label(user):
    # Plain text only, bounded names cannot inject markup or forge a new card.
    name=' '.join(str(user.get('name') or 'Telegram user').split())[:80]
    username=''.join(c for c in str(user.get('username') or '') if c.isascii() and (c.isalnum() or c=='_'))[:32]
    return name+(f' · @{username}' if username else '')+f"\nTelegram ID: {user['user_id']}"


def detail(grant,user,confirm=False):
    state=user['state'];rows=[]
    text=f"{grant['name']} · {state.title()}\n{label(user)}"
    if not user['owner']:
        if state=='pending':
            rows.append([{'text':'Approve','callback_data':cb('a',grant,user,user['review'])},
                         {'text':'Decline','callback_data':cb('b',grant,user,user['review'])}])
            text+='\nApprove allows use and sends a welcome notice. Decline keeps access closed.'
        elif state=='allowed':
            if confirm:
                text+='\n\nRemove access? Pending work stops; saved data is kept. An in-flight reply may still arrive.'
                rows.append([{'text':'Confirm removal','callback_data':cb('b',grant,user,user['review'])}])
            else:rows.append([{'text':'Remove access…','callback_data':cb('x',grant,user,user['review'])}])
        else:
            text+='\nAllow again grants access and sends a notice; cancelled work is not replayed.'
            rows.append([{'text':'Allow again','callback_data':cb('a',grant,user,user['review'])}])
    rows.append([{'text':'‹ Users','callback_data':f"ua:l:{grant['grant']}:0"}])
    return text,{'inline_keyboard':rows}


def callback(bridge,data,pairing,origin,message=None):
    parts=data.split(':')
    if len(parts) not in (4,5):return
    _,action,grant_id,value,*review=parts
    try:grants=connected(bridge,pairing)
    except bridge.BridgeError:grants={}
    grant=next((g for g in grants.values() if g['grant']==grant_id),None)
    if not grant:
        bridge.navigation_reply(int(pairing['chatId']),'This control is disconnected or outdated. Reopen My bots. Initial user-management permission is set once in Möbius.',{'inline_keyboard':[[{'text':'My bots','callback_data':'cmd:assistants'}]]},message);return
    try:
        state=users(bridge,grant)
        if action=='n':
            if value not in ('0','1'):return
            result=bridge.request_json(bot_path(grant)+'/notifications',method='POST',body={'enabled':value=='1'})
            state['notifications']=result['notifications'];action='l';value='0'
        if action=='l':
            items=state['users'];page=max(0,min(int(value),max(0,(len(items)-1)//6)))
            rows=[[{'text':f"{u['state'].title()} · {' '.join(u['name'].split())[:40]}",'callback_data':cb('u',grant,u)}] for u in items[page*6:page*6+6]]
            nav=[]
            if page:nav.append({'text':'‹ Previous','callback_data':f'ua:l:{grant_id}:{page-1}'})
            if (page+1)*6<len(items):nav.append({'text':'Next ›','callback_data':f'ua:l:{grant_id}:{page+1}'})
            if nav:rows.append(nav)
            rows.append([{'text':'Request alerts: on · Turn off' if state['notifications'] else 'Request alerts: off · Turn on','callback_data':f"ua:n:{grant_id}:{0 if state['notifications'] else 1}"}])
            rows.append([{'text':'‹ Bot','callback_data':f"studio:view:{grant['assistant']}"}])
            text=f"{grant['name']} · Users\n"+('Choose a person. Only identity and access are shown.' if items else 'No access requests yet.')
            markup={'inline_keyboard':rows}
        else:
            user=next((u for u in state['users'] if str(u['user_id'])==value),None)
            if not user:raise bridge.BridgeError('This user is unavailable.',status=409)
            if action in ('a','b','x') and (not review or review[0]!=user['review']):
                bridge.navigation_reply(int(pairing['chatId']),'This person’s access changed. Open Users to review the current state.',{'inline_keyboard':[[{'text':'Users','callback_data':f'ua:l:{grant_id}:0'}]]},message);return
            if action in ('a','b'):
                bridge.request_json(bot_path(grant)+'/change',method='POST',body={
                    'user_id':user['user_id'],'operation':'allow' if action=='a' else 'block','review':review[0],
                    'epoch':state['epoch'],'generation':state['generation']})
                text=f"{grant['name']} · "+('Approved' if action=='a' else 'Declined' if user['state']=='pending' else 'Access removed')+'\n'+label(user)
                markup={'inline_keyboard':[[{'text':'Users','callback_data':f'ua:l:{grant_id}:0'}]]}
            elif action in ('u','x'):text,markup=detail(grant,user,confirm=action=='x')
            else:return
        bridge.navigation_reply(int(pairing['chatId']),text,markup,message)
    except (ValueError,bridge.BridgeError):
        bridge.navigation_reply(int(pairing['chatId']),'The result could not be confirmed. Reopen Users to check the current state before trying again, or reconnect in Möbius.',{'inline_keyboard':[[{'text':'Users','callback_data':f'ua:l:{grant_id}:0'}]]},message)


def sync(bridge):
    """One bounded notification lane, independent of owner model work."""
    pairing=bridge.storage_get('pairing.json');settings=bridge.storage_get('settings.json')
    if not pairing or not settings or settings.get('enabled') is False:return
    owner_connection=connection(bridge,pairing)
    if not owner_connection:return
    grants=connected(bridge,pairing)
    if not grants:return
    receipts=bridge.storage_get(RECEIPTS) or {}
    sent_count=0
    for grant in grants.values():
        try:state=users(bridge,grant)
        except bridge.BridgeError:continue
        if not state['notifications']:continue
        for user in state['users']:
            if user['owner']:continue
            key=f"{grant['grant']}:{user['user_id']}";old=receipts.get(key)
            if not old and user['state']!='pending':continue
            if old and old.get('review')==user['review']:continue
            # Revalidate pairing/permission immediately before external delivery.
            current=bridge.storage_get('pairing.json');settings=bridge.storage_get('settings.json') or {}
            if current!=pairing or settings.get('enabled') is False or connection(bridge,current)!=owner_connection:return
            if old:
                if not old.get('message_id'):
                    continue  # An uncertain send is never silently repeated.
                text=f"{grant['name']} · "+('Approved' if user['state']=='allowed' else ('Access removed' if old.get('access_state')=='allowed' else 'Declined') if user['state']=='blocked' else 'Pending')+'\n'+label(user)
                markup={'inline_keyboard':[[{'text':'Users','callback_data':f"ua:l:{grant['grant']}:0"}]]}
                try:
                    bridge.telegram('editMessageText',{'chat_id':int(pairing['chatId']),'message_id':old['message_id'],'text':text,'reply_markup':markup})
                except bridge.BridgeError as exc:
                    if exc.status!=400:continue
                receipts[key]={**old,'review':user['review'],'access_state':user['state']}
                bridge.storage_put(RECEIPTS,receipts)
                continue
            if sent_count>=3:return # Bounded burst; remaining requests stay visible in Users.
            receipts[key]={'review':user['review'],'status':'uncertain','access_state':user['state']}
            bridge.storage_put(RECEIPTS,receipts) # Durable before send; no duplicate on crash.
            text,markup=detail(grant,user);text='New access request\n'+text
            try:
                result=bridge.send_text(int(pairing['chatId']),text,reply_markup=markup)
                receipts[key]={**receipts[key],'status':'sent','message_id':result['message_id']}
                bridge.storage_put(RECEIPTS,receipts)
            except (bridge.BridgeError,KeyError,TypeError):pass
            sent_count+=1
