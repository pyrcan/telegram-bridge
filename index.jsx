import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowRotateCw, ArrowUpRight, Chat, ChevronLeft, ChevronRight, Copy, Grid, Robot, Settings, ShieldCheck } from '@openai/apps-sdk-ui/components/Icon'
import { CSS } from './theme.js'
import { useBoundedRequests } from './ui-requests.js'

function pairCode() {
 const bytes=new Uint8Array(12);crypto.getRandomValues(bytes)
 return Array.from(bytes,b=>'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'[b%32]).join('')
}
const safeId=v=>typeof v==='string'&&/^[A-Za-z0-9_-]{1,64}$/.test(v)
const botName=v=>typeof v==='string'&&/^[A-Za-z0-9_]{1,64}$/.test(v)
const time=v=>v&&!Number.isNaN(new Date(v).getTime())?new Date(v).toLocaleString([],{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}):'Not checked'

export default function App({appId,token}) {
 const request=useBoundedRequests(appId,token)
 const [tab,setTab]=useState('chats'),[settingsOpen,setSettingsOpen]=useState(false)
 const [settings,setSettings]=useState(null),[pairing,setPairing]=useState(null),[status,setStatus]=useState(null)
 const [keySaved,setKeySaved]=useState(null),[current,setCurrent]=useState(null),[chats,setChats]=useState([])
 const [studio,setStudio]=useState(null),[studioState,setStudioState]=useState('idle'),[selected,setSelected]=useState(null)
 const [error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false)
 const mounted=useRef(true),refreshing=useRef(null),scroll=useRef(null)
 const auth={Authorization:`Bearer ${token}`}
 const read=useCallback(async(path,{optional=false,...options}={})=>{
  const r=await request(path,{...options,headers:{Authorization:`Bearer ${token}`}})
  if (optional&&r.status===404)return null
  if (!r.ok)throw new Error('The request could not be confirmed. Refresh before retrying.')
  return r.json()
 },[request,token])
 const refresh=useCallback(()=>{
  if(refreshing.current)return refreshing.current
  refreshing.current=(async()=>{
   try{
    const values=await Promise.all(['settings.json','pairing.json','status.json','conversation.json'].map(name=>read(`/api/storage/apps/${appId}/${name}`,{optional:true})))
    const key=await request(`/api/apps/${appId}/secrets/bot-token`,{method:'HEAD',headers:{Authorization:`Bearer ${token}`}})
    if(!key.ok&&key.status!==404)throw new Error('Saved-key status unavailable.')
    const rows=await read('/api/app-chats')
    if(!Array.isArray(rows)||rows.some(row=>!row||!safeId(row.id)||row.created_by_app_id!==appId||!('pending_question_id' in row)))throw new Error('Conversation metadata unavailable.')
    if(!mounted.current)return
    const [saved,pair,health,conversation]=values
    if(saved!==null&&(typeof saved!=='object'||Array.isArray(saved)||typeof saved.enabled!=='boolean'))throw new Error('Saved settings unavailable.')
    setSettings(saved);setPairing(pair);setStatus(health);setCurrent(conversation);setChats(rows)
    setKeySaved(key.ok);setError('')
   }catch(e){if(e.name!=='AbortError'&&mounted.current)setError('Could not refresh Bridge. Existing metadata is not fresh; no state was changed.')}
   finally{refreshing.current=null}
  })();return refreshing.current
 },[appId,token,read,request])
 const loadStudio=useCallback(async()=>{
  setStudioState('loading');setStudio(null)
  try{
   const first=await read('/api/services/assistant-studio/owner/catalog')
   if(first?.navigation_contract!=='owner-metadata-v1'||!Number.isSafeInteger(first?.app_id)||first.app_id<=0)throw new Error()
   const before=await read(`/api/apps/${first.app_id}`)
   if(before.id!==first.app_id||before.capability_contract?.service?.id!=='assistant-studio'||!before.frame_version||!before.storage_generation)throw new Error()
   const value=await read('/api/services/assistant-studio/owner/catalog')
   const after=await read(`/api/apps/${first.app_id}`)
   if(value.navigation_contract!=='owner-metadata-v1'||value.app_id!==first.app_id||after.id!==before.id||after.frame_version!==before.frame_version||after.storage_generation!==before.storage_generation||after.capability_contract?.service?.id!=='assistant-studio'||!Array.isArray(value.assistants))throw new Error()
   const bots=value.assistants.map(b=>{
    if(!safeId(b?.id)||typeof b.name!=='string'||typeof b.development?.status!=='string')throw new Error()
    // Explicit content-free projection. Unknown service fields never render.
    return {id:b.id,name:b.name.slice(0,160),status:b.development.status.slice(0,160),test:b.development.test_label,release:b.development.release_label,username:botName(b.connection?.username)?b.connection.username:null,chat:safeId(b.editing_chat?.id)?b.editing_chat.id:null}
   })
   setStudio({app_id:value.app_id,bots});setStudioState('ready')
  }catch(e){if(e.name!=='AbortError')setStudioState('unavailable')}
 },[read])
 useEffect(()=>{
  mounted.current=true;refresh()
  const onVisible=v=>{if(v)refresh()}
  const unsubscribe=window.mobius?.onVisibilityChange?.(onVisible)
  const timer=setInterval(()=>{if(window.mobius?.visible!==false&&!document.hidden)refresh()},10000)
  return()=>{mounted.current=false;clearInterval(timer);unsubscribe?.()}
 },[refresh])
 useEffect(()=>{if(tab==='bots')loadStudio()},[tab,loadStudio])
 const navigate=destination=>{setTab(destination);setSettingsOpen(false);setSelected(null);scroll.current?.scrollTo(0,0)}
 const openChat=id=>window.parent.postMessage({type:'moebius:open-chat',chatId:id},'*')
 const openStudio=async()=>{
  // Re-resolve its accepted runtime before navigation; stale cached catalog is
  // neither authority nor a reason to install another app.
  if(!studio)return
  try{const app=await read(`/api/apps/${studio.app_id}`);if(app.id!==studio.app_id||app.capability_contract?.service?.id!=='assistant-studio')throw new Error();window.parent.postMessage({type:'moebius:open-app',appId:studio.app_id},'*')}
  catch{setStudio(null);setStudioState('unavailable')}
 }
 function ownerSetup(){
  const draft=`Help me securely connect Telegram Bridge (app ${appId}). Read the installed README and inspect this app's accepted job-context runtime. Run its owner.py connect --app-id ${appId} from that accepted runtime in this nondelegated owner chat to save the existing sealed-input form as the final action. Never ask for a key in chat or an app input. Opening this draft is navigation, not approval or execution. Do not start listening, publish, migrate pairing or change other apps.`
  window.parent.postMessage({type:'moebius:new-chat',draft},'*')
  setNotice('An editable setup request was opened in Möbius. Send it there to request the secure form; no key was collected here.')
 }
 async function updateListening(){
  if(busy||error)return;setBusy(true);setNotice('')
  try{
   const saved=await read(`/api/storage/apps/${appId}/settings.json`,{optional:true})
   const next=saved?{...saved,enabled:!saved.enabled}:{enabled:true,pairingCode:pairCode()}
   if(!next.enabled||keySaved===true){
    await read(`/api/storage/apps/${appId}/settings.json`,{method:'PUT',body:JSON.stringify(next)})
    setSettings(next)
    if(next.enabled)await read(`/api/apps/${appId}/run-job`,{method:'POST',body:'{}'})
    setNotice(next.enabled?'Listening requested. Check the saved status below; cron owns the listener.':'Paused. Accepted work or an in-flight reply may still finish.')
   }else setNotice('Save the dedicated bot key securely before enabling listening.')
  }catch{setNotice('The listening change could not be confirmed. Refresh status before trying again; it was not retried.')}
  finally{setBusy(false);await refresh()}
 }
 async function preparePairing(){
  if(busy||pairing||error)return;setBusy(true)
  try{
   const saved=await read(`/api/storage/apps/${appId}/settings.json`,{optional:true})
   if(!saved?.pairingCode){const next={...(saved||{}),enabled:saved?.enabled===true,pairingCode:pairCode()};await read(`/api/storage/apps/${appId}/settings.json`,{method:'PUT',body:JSON.stringify(next)});setSettings(next)}
  }catch{setNotice('The code was not confirmed. Refresh saved status before retrying.')}
  finally{setBusy(false);await refresh()}
 }
 const username=botName(status?.botUsername)?status.botUsername:null
 const personal=chats.filter(c=>pairing&&c.scope===`telegram:${pairing.chatId}`)
 const active=personal.find(c=>c.id===current?.chatId)
 const chosen=studio?.bots.find(b=>b.id===selected)
 return <div className="tg-root"><style>{CSS}</style>
  <header className="tg-header"><h1>Bridge</h1><button className="tg-icon-btn" aria-label="Settings" aria-expanded={settingsOpen} onClick={()=>setSettingsOpen(!settingsOpen)}><Settings width={22} height={22}/></button></header>
  <main className="tg-scroll" ref={scroll}><div className="tg-page">
   {error&&<div className="tg-notice" role="alert">{error}<button className="tg-text-btn" onClick={refresh}><ArrowRotateCw width={16} height={16}/>Refresh</button></div>}
   {notice&&<div className="tg-notice" role="status">{notice}</div>}
   {settingsOpen?<section aria-label="Connection settings">
    <button className="tg-back" onClick={()=>setSettingsOpen(false)}><ChevronLeft width={17} height={17}/>Back to {tab}</button><h2 className="tg-view-title">Settings</h2>
    <section className="tg-main-card"><h3>Dedicated bot key</h3><p className="tg-help">{keySaved===null?'Saved-key status not checked.':keySaved?'An encrypted bot key is saved. Its value never reaches this frame.':'Create your personal bot with BotFather, then use the secure form in your Möbius owner chat.'}</p><button className="tg-primary" onClick={ownerSetup}>{keySaved?'Review secure setup':'Set up securely in Möbius'}</button><p className="tg-quiet-note">This opens an editable request, not a key input or approval. A different bot is never substituted into this installation.</p></section>
    <section className="tg-main-card"><h3>One private owner</h3>{pairing?<><p className="tg-help">{pairing.displayName||'Private owner'} · paired {time(pairing.pairedAt)}</p><p className="tg-quiet-note">Groups and other Telegram accounts are ignored. Pairing revocation and replacement require review in your Möbius owner chat.</p></>:<><p className="tg-help">Prepare a one-time pairing code, enable listening after secure setup, then send the code to your personal bot.</p>{settings?.pairingCode?<button className="tg-code" onClick={async()=>{try{await navigator.clipboard.writeText(`/pair ${settings.pairingCode}`);setNotice('Pairing command copied.')}catch{setNotice('Copy is unavailable. Enter the visible pairing command manually.')}}}><code>/pair {settings.pairingCode}</code><Copy width={18} height={18}/></button>:<button className="tg-secondary" disabled={busy||!!error} onClick={preparePairing}>Prepare pairing code</button>}{username&&settings?.pairingCode&&<a className="tg-primary tg-studio-link" href={`https://t.me/${username}?start=${settings.pairingCode}`} target="_blank" rel="noreferrer">Open bot to pair <ArrowUpRight width={16} height={16}/></a>}</>}
    </section><section className="tg-main-card"><h3>{status?.label||'Waiting for setup'}</h3><p className="tg-help">{status?.detail||'Save the key securely before enabling listening.'}</p><p className="tg-quiet-note">Last check: {time(status?.checkedAt)}. Enabling accepts paired-owner text; configured provider usage may be incurred. Pause prevents future intake, not already accepted work.</p><button className="tg-secondary" disabled={busy||!!error||(!settings?.enabled&&keySaved!==true)} onClick={updateListening}>{busy?'Checking…':settings?.enabled?'Pause Bridge':'Enable listening'}</button></section>
   </section>:tab==='chats'?<section aria-label="Chats"><h2 className="tg-view-title">Chats</h2>
    <div className="tg-connection-alert"><span>{status?.label||'Setup needed'} · {pairing?'Private owner paired':'Not paired'}</span><button className="tg-text-btn" onClick={()=>setSettingsOpen(true)}>Settings</button></div>
    {active?<button className="tg-current-card" onClick={()=>openChat(active.id)}><div><span className="tg-section-label">Current in Telegram</span><h3>{active.title||'Personal conversation'}</h3><p>{active.pending_question_id?'Waiting for your answer':active.running?'Working':'Ready to continue'}</p></div><ArrowUpRight width={20} height={20}/></button>:<div className="tg-current-empty"><strong>Your personal conversations</strong><p className="tg-help">Send a message to your paired Telegram bot to begin. Use /new for a fresh conversation and /chats to choose where to continue.</p><button className="tg-text-btn" onClick={()=>setSettingsOpen(true)}>Review connection</button></div>}
    <h3 className="tg-section-label">Saved conversations · metadata only</h3>
    {personal.length?personal.map(c=><button className="tg-list-row" key={c.id} onClick={()=>openChat(c.id)}><Chat width={22} height={22}/><div className="tg-chat-copy"><strong>{c.title||'Personal conversation'}</strong><span>{c.pending_question_id?'Waiting for your answer':c.running?'Working':'Saved'} · {time(c.activity_at||c.updated_at||c.created_at)}</span></div><ArrowUpRight width={18} height={18}/></button>):<p className="tg-help">No personal conversations are available yet.</p>}
    <p className="tg-quiet-note">Opening a conversation here does not switch Telegram routing. Archive state and transcript previews are not exposed by this edition; filing stays in Möbius.</p>
   </section>:tab==='bots'?<section aria-label="Bots">
    {chosen?<><button className="tg-back" onClick={()=>setSelected(null)}><ChevronLeft width={17} height={17}/>Your bots</button><div className="tg-detail-icon"><Robot width={28} height={28}/></div><h2 className="tg-view-title">{chosen.name}</h2><p className="tg-help">{chosen.status}</p><dl className="tg-bot-facts"><div><dt>Your test</dt><dd>{chosen.test||'Review in Studio'}</dd></div><div><dt>Published</dt><dd>{chosen.release||'Review in Studio'}</dd></div></dl><div className="tg-button-stack">{chosen.chat&&<button className="tg-secondary" onClick={()=>openChat(chosen.chat)}>Customize in Möbius <ArrowUpRight width={16} height={16}/></button>}{chosen.username&&<a className="tg-primary" href={`https://t.me/${chosen.username}`} target="_blank" rel="noreferrer">Open bot</a>}<button className="tg-secondary" onClick={openStudio}>Open Studio</button></div><p className="tg-quiet-note">Navigation is not a Telegram continuation grant. Publishing, private tests and user access remain in Studio.</p></>:<><h2 className="tg-view-title">Bots</h2><p className="tg-help">Optional Telegram Bot Studio shortcuts. Only owner configuration metadata, never participant notes or conversations.</p>{studioState==='loading'?<p className="tg-help">Checking the current Studio runtime…</p>:studioState==='ready'?<>{studio.bots.length?studio.bots.map(b=><button className="tg-list-row tg-bot-row" key={b.id} onClick={()=>setSelected(b.id)}><Robot width={22} height={22}/><div className="tg-chat-copy"><strong>{b.name}</strong><span>{b.status}</span></div><ChevronRight width={18} height={18}/></button>):<p className="tg-help">No bots yet. Create one in Studio.</p>}<button className="tg-secondary tg-studio-link" onClick={openStudio}>Open Studio <ArrowUpRight width={16} height={16}/></button></>:<div className="tg-studio-empty"><h3>Studio is optional</h3><p className="tg-help">Its metadata is unavailable, not authorized, or its runtime does not match. Bridge works on its own. Installing or linking an app grants no access.</p><button className="tg-secondary" onClick={loadStudio}>Check again</button></div>}</>}
   </section>:<section aria-label="Tools"><h2 className="tg-view-title">Tools</h2><button className="tg-list-row" onClick={()=>setSettingsOpen(true)}><Settings width={22} height={22}/><div className="tg-chat-copy"><strong>Personal connection</strong><span>Secure setup, pairing and listening</span></div><ChevronRight width={18} height={18}/></button><button className="tg-list-row" onClick={refresh}><ArrowRotateCw width={22} height={22}/><div className="tg-chat-copy"><strong>Refresh saved status</strong><span>Reads only; no Telegram test or model call</span></div></button><section className="tg-main-card"><ShieldCheck width={24} height={24}/><h3>Public-core edition</h3><p className="tg-help">Private text, menus, model choice, progress and Bridge-owned conversation routing. Ordinary saved cards retain exact identities; their Telegram answers are agent-scoped, not trusted owner permission.</p><p className="tg-quiet-note">Mini App, screenshots, media transport, exact customization-chat connections, filing, deletion and Telegram user management are not included. Sensitive actions and credentials stay in Möbius.</p><p className="tg-quiet-note">The reviewed background job can read its own encrypted key into RAM solely for the Telegram API. This frame never receives it. Telegram and configured model providers process their respective requests; hosting operators control the machine.</p><p className="tg-quiet-note">Uncertain external delivery is never automatically repeated. Lost completed-result streams link to Möbius rather than read transcripts or rerun work.</p></section></section>}
  </div></main><nav className="tg-bottom-nav" aria-label="Bridge sections">{[['chats','Chats',Chat],['bots','Bots',Robot],['tools','Tools',Grid]].map(([id,label,Icon])=><button className="tg-nav-btn" key={id} aria-current={!settingsOpen&&tab===id?'page':undefined} onClick={()=>navigate(id)}><Icon width={22} height={22}/><span>{label}</span></button>)}</nav>
 </div>
}
