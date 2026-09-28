"""Owner navigation for Telegram Bot Studio: live metadata, not specialist traffic.

Only the already-paired owner reaches this adapter. Read navigation calls no
model. Customization links open Studio’s canonical owner chat; continuation stays
in Möbius in this Store edition.
"""
import re
import bridge_access

CONTEXT = ('[Owner capability: Telegram Bot Studio manages your assistants. For assistant/bot '
           'management, read /data/shared/skills/assistant-studio.md and query live Studio '
           'state via its owner helper. Do not infer channel connections from memory. '
           'This is the personal owner channel, not a specialist participant channel.]')
PENDING = 'studio-input.json'

def valid_id(value):
    return value=='pocket-notes' or bool(re.fullmatch(r'[a-f0-9]{32}',value))

def read_control(data):
    return data=='cmd:assistants' or data.startswith(('studio:list:','studio:view:','studio:settings:','studio:users:'))

def menu(catalog, origin, identity=None, page=0, settings=False):
    items=catalog.get('assistants',[]);rows=[]
    if identity:
        item=next((a for a in items if a['id']==identity),None)
        if not item:return 'This bot is unavailable.',{'inline_keyboard':[[{'text':'‹ My bots','callback_data':'cmd:assistants'}]]}
        conn=item.get('connection') or {};ready=conn.get('state') in ('active','testing')
        development=item['development']
        text=f"{item['name']}\n{development['status']}\n\nYour test: {development['test_label']}\nPublished bot: {development['release_label']}"
        text+='\n\n'+development['next_step']
        if settings:
            text+='\n\nSettings and releases are managed in Studio. No changes are applied here.'
            if origin:rows.append([{'text':'Open Studio','url':f"{origin}/shell/?app={catalog['app_id']}"}])
        else:
            if ready and conn.get('username'):rows.append([{'text':'Open bot','url':f"https://t.me/{conn['username']}"}])
            editing=(item.get('editing_chat') or {}).get('id')
            if origin and editing:
                from urllib.parse import quote
                rows.append([{'text':'Customize in Möbius','url':f"{origin}/shell/?chat={quote(editing,safe='')}"}])
            elif origin:
                rows.append([{'text':'Set up in Studio' if not conn.get('username') else 'Customize in Studio','url':f"{origin}/shell/?app={catalog['app_id']}"}])
            else:
                text+='\n\nOpen Telegram Bot Studio in Möbius to customize this bot.'
        if conn.get('username'):
            rows.append([{'text':'Users','callback_data':f'studio:users:{identity}'}])
        rows.append([{'text':'‹ My bots','callback_data':'cmd:assistants'}])
    else:
        pages=max(1,(len(items)+7)//8);page=max(0,min(page,pages-1))
        text='My bots · management only\nConversations stay with each bot’s users.' if items else 'Your first bot starts here.'
        for item in items[page*8:page*8+8]:rows.append([{'text':item['name'][:64],'callback_data':f"studio:view:{item['id']}"}])
        nav=[]
        if page:nav.append({'text':'‹ Previous','callback_data':f'studio:list:{page-1}'})
        if page+1<pages:nav.append({'text':'Next ›','callback_data':f'studio:list:{page+1}'})
        if nav:rows.append(nav)
        rows.append([{'text':'Create bot','callback_data':'studio:create'}])
        if origin:rows[-1].append({'text':'Open Studio','url':f"{origin}/shell/?app={catalog['app_id']}"})
    return text,{'inline_keyboard':rows}


def show(bridge, pairing, origin, identity=None, page=0, message=None, settings=False):
    try:
        catalog=bridge.request_json('/api/services/assistant-studio/owner/catalog')
        text,markup=menu(catalog,origin,identity,page,settings)
    except bridge.BridgeError:
        # The access-management grant is deliberately narrower than catalog
        # navigation. It must work on a fresh install without that second grant.
        try:grants=bridge_access.connected(bridge,pairing)
        except bridge.BridgeError:grants={}
        if not grants:
            bridge.send_text(int(pairing['chatId']),'Telegram Bot Studio is unavailable or owner navigation is not connected. Your Telegram conversation still works. Enable user management in Bridge to manage published bots, or review catalog navigation separately in Möbius.',reply_markup={'inline_keyboard':[[{'text':'Try again','callback_data':'cmd:assistants'}]]})
            return
        if identity in grants:
            bridge_access.callback(bridge,f"ua:l:{grants[identity]['grant']}:0",pairing,origin,message)
            return
        items=list(grants.values());page=max(0,min(page,(len(items)-1)//8))
        rows=[[{'text':item['name'][:64],'callback_data':f"ua:l:{item['grant']}:0"}] for item in items[page*8:page*8+8]]
        nav=[]
        if page:nav.append({'text':'‹ Previous','callback_data':f'studio:list:{page-1}'})
        if (page+1)*8<len(items):nav.append({'text':'Next ›','callback_data':f'studio:list:{page+1}'})
        if nav:rows.append(nav)
        text='My bots · user management\nChoose a published bot to review users. Customization stays in Möbius.'
        markup={'inline_keyboard':rows}
    bridge.navigation_reply(int(pairing['chatId']),text,markup,message)


def callback(bridge, data, pairing, origin, message=None):
    if data=='cmd:assistants':show(bridge,pairing,origin,message=message);return
    parts=data.split(':')
    if len(parts)==3 and parts[1]=='list' and parts[2].isdigit():
        show(bridge,pairing,origin,page=int(parts[2]),message=message);return
    if len(parts)==3 and parts[1] in ('view','settings') and valid_id(parts[2]):
        show(bridge,pairing,origin,identity=parts[2],message=message,settings=parts[1]=='settings');return
    if len(parts)==3 and parts[1] in ('edit','model','publish') and valid_id(parts[2]):
        show(bridge,pairing,origin,identity=parts[2],message=message,settings=parts[1] in ('model','publish'));return
    if len(parts)==3 and parts[1]=='users' and valid_id(parts[2]):
        try:
            grant=bridge_access.connected(bridge,pairing).get(parts[2])
            if grant:
                bridge_access.callback(bridge,f"ua:l:{grant['grant']}:0",pairing,origin,message);return
            linked=bridge_access.connection(bridge,pairing)
            text=('This bot needs a published release and a connection owned by your paired account before managing users.' if linked else
                  'Enable user management once in Möbius. Then approvals and request alerts for all your bots are controlled here in Telegram.')
        except bridge.BridgeError:
            text='User management could not be checked. Reopen Users or check the connection in Möbius.'
        rows=[]
        if origin:rows.append([{'text':'Open one-time setup in Möbius','url':f'{origin}/shell/?app={bridge.APP_ID}'}])
        rows.append([{'text':'‹ Bot','callback_data':f'studio:view:{parts[2]}'}])
        bridge.navigation_reply(int(pairing['chatId']),text,{'inline_keyboard':rows},message);return
    if len(parts)==3 and parts[1]=='continue' and valid_id(parts[2]):
        show(bridge,pairing,origin,identity=parts[2],message=message);return
    if bridge.sync_question_state(origin):
        bridge.send_text(int(pairing['chatId']),'Answer the current Möbius question first. You can still browse My bots.');return
    if data=='studio:create':
        action='create';identity=None
        prompt='What should your bot be called? Reply here. Möbius will create a blank bot; connect Telegram next, then customize and test privately.'
    else:
        bridge.send_text(int(pairing['chatId']),'This assistant control is unavailable. Open My bots again.');return
    sent=bridge.send_text(int(pairing['chatId']),prompt,reply_markup={'force_reply':True,'selective':True})
    if isinstance(sent,dict) and sent.get('message_id'):
        bridge.storage_put(PENDING,{'prompt_id':sent['message_id'],'chat_id':int(pairing['chatId']),
          'user_id':int(pairing['userId']),'assistant':identity,'action':action})

def input_reply(bridge, message, pairing, origin):
    reply=(message.get('reply_to_message') or {}).get('message_id')
    if not reply:return False
    pending=bridge.storage_get(PENDING)
    if not isinstance(pending,dict) or pending.get('prompt_id')!=reply or pending.get('chat_id')!=int(pairing['chatId']) or pending.get('user_id')!=int(pairing['userId']):return False
    text=str(message.get('text') or '').strip()
    if text=='/cancel':
        bridge.storage_put(PENDING,None);bridge.send_text(int(pairing['chatId']),'Assistant edit cancelled. Nothing changed.');return True
    if bridge.sync_question_state(origin):
        bridge.send_text(int(pairing['chatId']),'Answer the current Möbius question first, then reply to the assistant edit prompt again.');return True
    identity=pending.get('assistant')
    if pending['action']=='create':
        instruction='Create a blank, unconfigured assistant draft in Telegram Bot Studio using the name below. No preset purpose or note-taking. Next guide me to connect Telegram securely, then privately test and customize in Studio. Do not publish, activate, call its model, invite anyone or connect Telegram on this request.'
    else:
        bridge.send_text(int(pairing['chatId']),'This older edit prompt has been replaced. Your text is still here; continue it in the bot’s customization chat. Nothing was changed.')
        show(bridge,pairing,origin,identity=identity)
        bridge.storage_put(PENDING,None)
        return True
    bridge.ask_mobius(pairing,instruction+'\n\nMy request:\n'+text,origin,reply_to_message_id=message.get('message_id'))
    bridge.storage_put(PENDING,None)
    return True
