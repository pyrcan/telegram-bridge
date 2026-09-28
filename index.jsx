import {ownerRequest} from './owner-handoff.js'
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowRotateCw,
  ArrowUpRight,
  Check,
  Copy,
  Lock,
  Plus,
  ShieldCheck,
  Trash,
} from '@openai/apps-sdk-ui/components/Icon'
import { CSS } from './theme.js'

const DEFAULT_STATUS = {
  state: 'waiting',
  label: 'Waiting for setup',
  detail: 'Add a bot token to begin.',
  events: [],
}

const TELEGRAM_SYSTEM_PROMPT = "This conversation is being used through a text-first Telegram chat. Reply concisely in plain text with simple formatting. When a material choice needs an owner answer, use the platform saved request_question or request_approval card as the final action; the bridge renders its options as Telegram buttons. Do not ask blocking questions only in prose. Do not create widgets, rich proposal previews, or other interface-only artifacts just to communicate; Telegram cannot render them. Use only the tools genuinely needed to complete the request. App-building requests may still use the necessary build and verification tools. Open completed visual work in Möbius. Generated images stay in this Möbius conversation; Bridge sends an authenticated-view link instead of image files. This Store edition has no direct whole-shell screenshot shortcut."

function makePairCode() {
  const alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
  const bytes = new Uint8Array(8)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, value => alphabet[value % alphabet.length]).join('')
}

function prettyTime(value) {
  if (!value) return 'Not yet'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Not yet' : date.toLocaleString([], {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

function stateTone(state) {
  if (state === 'connected') return 'good'
  if (state === 'paused' || state === 'waiting' || state === 'needs_token') return 'idle'
  if (state === 'checking') return 'working'
  return 'warn'
}

export default function App({ appId, token }) {
  const [settings, setSettings] = useState(null)
  const [pairing, setPairing] = useState(null)
  const [status, setStatus] = useState(DEFAULT_STATUS)
  const [hasToken, setHasToken] = useState(false)
  const [saving, setSaving] = useState(false)
  const [address, setAddress] = useState('')
  const [checking, setChecking] = useState(false)
  const [notice, setNotice] = useState('')
  const [copyState, setCopyState] = useState('copy')
  const [chats, setChats] = useState([])
  const [studio, setStudio] = useState(null)
  const [studioError, setStudioError] = useState('')
  const [accessConnection,setAccessConnection]=useState(null)
  const [connectionBusy, setConnectionBusy] = useState(null)
  const studioRequest = useRef(null)
  const [showAllChats,setShowAllChats]=useState(false)
  const [activeChatId, setActiveChatId] = useState(null)
  const [creatingChat, setCreatingChat] = useState(false)
  const [confirmRevoke, setConfirmRevoke] = useState(false)
  const chatsRequest = useRef(null)
  const store = window.mobius?.storage

  const loadChats = useCallback(() => {
    if (chatsRequest.current) return chatsRequest.current
    chatsRequest.current = (async () => {
      try {
        const response = await fetch('/api/app-chats', { headers: { Authorization: `Bearer ${token}` } })
        if (!response.ok) throw new Error()
        const value = await response.json()
        setChats(Array.isArray(value) ? value : [])
      } catch {
        setNotice('Could not refresh conversations. Your existing list is still available.')
      } finally {
        chatsRequest.current = null
      }
    })()
    return chatsRequest.current
  }, [token])

  const loadStudio = useCallback(() => {
    if (studioRequest.current) return studioRequest.current
    studioRequest.current = (async () => {
      try {
        const response = await fetch('/api/services/assistant-studio/owner/catalog', {headers:{Authorization:`Bearer ${token}`}})
        if (!response.ok) throw new Error('Could not load Studio. Your owner conversation still works.')
        setStudio(await response.json()); setStudioError('')
      } catch (error) { setStudioError(error.message) }
      finally { studioRequest.current = null }
    })()
    return studioRequest.current
  }, [token, appId])

  const accessCurrent=accessConnection?.scope==='owned-bots-v1'&&accessConnection.owner_user_id===Number(pairing?.userId)&&accessConnection.paired_at===pairing?.pairedAt
  async function changeAccessConnection(disconnect=false) {
    if (connectionBusy) return
    setConnectionBusy('access'); setNotice('')
    try {
      const context=disconnect?{grant:accessConnection.grant}:{scope:'owned-bots-v1',coverage:'User access and request alerts for current and future bots owned by this paired account',paired_user_id:String(pairing.userId),paired_chat_id:String(pairing.chatId),paired_at:pairing.pairedAt}
      ownerRequest(appId,'Telegram Bridge',disconnect?'disconnect-access':'connect-access',context)
      setNotice('Review and send the prepared request in Möbius chat. User management is unchanged until you confirm there.')
    } catch(error){if(error.name!=='AbortError'&&error.code!=='aborted')setNotice(error.message)}
    finally{setConnectionBusy(null);await loadStudio()}
  }

  useEffect(() => {
    loadStudio()
    const returned=()=>{if(!document.hidden)loadStudio()}
    window.addEventListener('focus',returned)
    document.addEventListener('visibilitychange',returned)
    return()=>{window.removeEventListener('focus',returned);document.removeEventListener('visibilitychange',returned)}
  }, [loadStudio])

  useEffect(() => {
    let alive = true
    const initial = async () => {
      try {
        let next = await store?.get('settings.json')
        if (!next?.pairingCode) {
          next = { enabled: true, pairingCode: makePairCode(), createdAt: new Date().toISOString() }
          await store?.set('settings.json', next)
        }
        if (alive) { setSettings(next); setAddress(next.mobiusAddress || '') }
      } catch {
        if (alive) setSettings({ enabled: true, pairingCode: makePairCode() })
      }
    }
    // Credential availability is independent of settings and pairing loading.
    fetch(`/api/apps/${appId}/secrets/bot-token`, {
      method: 'HEAD', headers: { Authorization: `Bearer ${token}` },
    }).then(response => { if (alive) setHasToken(response.ok) })
      .catch(() => { if (alive) setHasToken(false) })
    initial()
    const unStatus = store?.subscribe?.('status.json', value => setStatus(value || DEFAULT_STATUS))
    const unAccess=store?.subscribe?.('owner-access.json',value=>setAccessConnection(value?.scope==='owned-bots-v1'?value:null))
    const unPair = store?.subscribe?.('pairing.json', value => setPairing(value || null))
    const unSettings = store?.subscribe?.('settings.json', value => value && setSettings(value))
    const unConversation = store?.subscribe?.('conversation.json', value => {
      setActiveChatId(value?.chatId || null)
      loadChats()
    })
    loadChats()
    return () => { alive = false; unStatus?.(); unPair?.(); unAccess?.(); unSettings?.(); unConversation?.() }
  }, [appId, token])

  useEffect(() => {
    if (status.events?.length) loadChats()
  }, [status.events?.[0]?.at, loadChats])

  const saveSettings = useCallback(async next => {
    setSettings(next)
    try {
      await store?.set('settings.json', next)
      return true
    } catch {
      setNotice('Could not save that change. Try again while online.')
      return false
    }
  }, [store])

  const saveAddress = async event => {
    event.preventDefault()
    let origin = ''
    if (address.trim()) {
      try {
        const url = new URL(address.trim())
        if (url.protocol !== 'https:' || url.username || url.password || url.pathname !== '/' || url.search || url.hash || /[\\\s]/.test(address.trim()) || /[\x00-\x1f]/.test(address) || url.port === '0') throw new Error()
        origin = url.origin
      } catch { setNotice('Use your HTTPS Möbius address only, without a path, password or query.'); return }
    }
    if (await saveSettings({...settings, mobiusAddress: origin})) {
      setAddress(origin)
      setNotice(origin ? 'Möbius links saved. Images open there after sign-in; no key is sent with the link.' : 'Möbius links turned off. Telegram text replies still work.')
    }
  }

  const connectTelegram = async () => {
    if (saving) return
    setSaving(true); setNotice('')
    try {
      ownerRequest(appId,'Telegram Bridge','connect-telegram',{operation:hasToken?'Replace the saved Bridge key':'Connect a dedicated owner bot'})
      setNotice('Review and send the request in Möbius chat. Enter the key only in its secure card—not a chat message.')
    } catch (error) {
      if (error.name !== 'AbortError' && error.code !== 'aborted') setNotice('Setup was interrupted. Check the saved connection before trying again.')
    } finally {
      try {
        const response = await fetch(`/api/apps/${appId}/secrets/bot-token`, {
          method: 'HEAD', headers: { Authorization: `Bearer ${token}` },
        })
        if (response.ok || response.status === 404) setHasToken(response.ok)
      } catch { /* Preserve the last known state if the check is offline. */ }
      setSaving(false)
    }
  }

  const runCheck = async () => {
    if (checking) return
    setChecking(true)
    setNotice('Checking the bot…')
    try {
      const response = await fetch(`/api/apps/${appId}/service/bot-info`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!response.ok) throw new Error()
      const result = await response.json()
      if (!result.is_bot) throw new Error()
      setNotice(`Bot connection verified${result.username ? `: @${result.username}` : ''}.`)
    } catch {
      setNotice('Could not verify the bot connection. Check the saved token and try again.')
    } finally {
      setChecking(false)
    }
  }

  const toggleEnabled = async () => {
    if (!settings) return
    const previous = settings
    const enabled = !settings.enabled
    if (await saveSettings({ ...settings, enabled })) {
      setNotice(enabled ? 'Starting the bridge…' : 'Bridge paused. An already-running reply may finish.')
      if (enabled) {
        try {
          const response = await fetch(`/api/apps/${appId}/run-job`, {
            method: 'POST', headers: { Authorization: `Bearer ${token}` },
          })
          if (!response.ok) throw new Error()
          setNotice('Resume requested. Connection status updates automatically.')
        } catch {
          setNotice('Resume saved. The scheduled bridge will pick it up shortly.')
        }
      }
    } else {
      setSettings(previous)
    }
  }

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(`/pair ${settings.pairingCode}`)
      setCopyState('done')
      setTimeout(() => setCopyState('copy'), 1800)
    } catch {
      setNotice(`Send /pair ${settings.pairingCode} to your bot.`)
    }
  }

  const resetPairing = async () => {
    if (!confirmRevoke) {
      setConfirmRevoke(true)
      setNotice('Tap “Confirm revoke” to disconnect this Telegram chat.')
      return
    }
    const next = { ...settings, pairingCode: makePairCode() }
    try {
      await Promise.all([
        store?.remove('pairing.json'),
        store?.remove('conversation.json'),
        store?.set('settings.json', next),
      ])
      setPairing(null)
      setSettings(next)
      setConfirmRevoke(false)
      setNotice('Telegram access revoked. A new pairing code is ready.')
    } catch {
      setNotice('Could not reset pairing. Try again while online.')
    }
  }

  const createConversation = async () => {
    if (!pairing || creatingChat) return
    setCreatingChat(true)
    setNotice('Starting a fresh Telegram conversation…')
    try {
      const stamp = new Date().toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
      const response = await fetch('/api/app-chats', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: `Telegram · ${pairing.displayName || 'Private chat'} · ${stamp}`,
          scope: `telegram:${pairing.chatId}`,
          scope_label: pairing.displayName || 'Telegram',
          owner_visible: true,
          system_prompt: TELEGRAM_SYSTEM_PROMPT,
        }),
      })
      if (!response.ok) throw new Error()
      const created = await response.json()
      await store?.set('conversation.json', { chatId: created.id, createdAt: new Date().toISOString() })
      setActiveChatId(created.id)
      setNotice('Fresh conversation ready in Möbius and Telegram.')
      await loadChats()
    } catch {
      setNotice('Could not create the conversation. Try again while online.')
    } finally {
      setCreatingChat(false)
    }
  }

  const openConversation = chatId => {
    window.parent.postMessage({ type: 'moebius:open-chat', chatId }, '*')
  }

  const displayChatTitle = chat => {
    const title = String(chat.title || '').trim()
    if (title && !title.startsWith('[Telegram bridge note:')) return title
    return `Telegram · ${chat.scope_label || pairing?.displayName || 'Conversation'}`
  }

  const botUsername = String(status.botUsername || '').replace(/^@/, '')
  const pairLink = botUsername && settings?.pairingCode
    ? `https://t.me/${botUsername}?start=${encodeURIComponent(settings.pairingCode)}`
    : ''

  if (!settings) return <div className="tg-root"><style>{CSS}</style><div className="tg-loading">Preparing your bridge…</div></div>

  const tone = stateTone(status.state)
  const setupPanel = (
        <details className="tg-settings" open={!hasToken||!pairing}><summary>{!hasToken||!pairing?'Finish setup':'Settings · connection, pairing & diagnostics'}</summary>
        <section className="tg-grid">
          <div className="tg-main-card">
            <div className="tg-section-head">
              <div><span className="tg-step">1</span><h2>Connect your bot</h2></div>
              <a href="https://t.me/BotFather" target="_blank" rel="noreferrer">Open BotFather <ArrowUpRight size={15} /></a>
            </div>
            <p className="tg-help">Create a dedicated bot with BotFather, then continue in Möbius chat for a secure key card. The key bypasses this app screen and is encrypted locally.</p>
            {hasToken ? (
              <div className="tg-token-saved">
                <div className="tg-token-badge"><Check size={17} /><span><strong>Token stored</strong><small>{botUsername ? `Connected as @${botUsername}` : 'Ready for a connection check'}</small></span></div>
                <div className="tg-token-actions">
                  <button className="tg-text-btn" onClick={connectTelegram} disabled={saving}>{saving ? 'Opening…' : 'Replace key'}</button>
                  <button className="tg-text-btn" onClick={runCheck} disabled={checking}><ArrowRotateCw size={15} />{checking ? 'Checking…' : 'Check now'}</button>
                </div>
              </div>
            ) : (
              <button className="tg-primary" onClick={connectTelegram} disabled={saving}><Lock size={17} />{saving ? 'Opening secure setup…' : 'Connect securely'}</button>
            )}

            <div className="tg-divider" />

            <div className="tg-section-head">
              <div><span className="tg-step">2</span><h2>Pair one private chat</h2></div>
            </div>
            {pairing ? (
              <div className="tg-paired">
                <div className="tg-avatar">{(pairing.displayName || 'T').slice(0, 1).toUpperCase()}</div>
                <div><strong>{pairing.displayName || 'Telegram user'}</strong><span>{pairing.username ? `@${pairing.username}` : 'Private chat'} · paired {prettyTime(pairing.pairedAt)}</span></div>
                <div className="tg-paired-actions">
                  {botUsername && <a className="tg-open-bot" href={`https://t.me/${botUsername}`} target="_blank" rel="noreferrer">Open bot <ArrowUpRight size={14} /></a>}
                  <button className={`tg-danger ${confirmRevoke ? 'is-confirming' : ''}`} onClick={resetPairing}><Trash size={15} /> {confirmRevoke ? 'Confirm revoke' : 'Revoke'}</button>
                  {confirmRevoke && <button className="tg-cancel-revoke" onClick={() => { setConfirmRevoke(false); setNotice('') }}>Cancel</button>}
                </div>
              </div>
            ) : (
              <div className="tg-pair-box">
                {pairLink && <a className="tg-pair-link" href={pairLink} target="_blank" rel="noreferrer">Open @{botUsername} and pair <ArrowUpRight size={16} /></a>}
                <p>{pairLink ? 'Or send this command manually:' : 'Open your bot in Telegram and send:'}</p>
                <button className="tg-code" onClick={copyCode}><code>/pair {settings.pairingCode}</code>{copyState === 'done' ? <Check size={18} /> : <Copy size={18} />}</button>
                <small>{pairLink ? 'Telegram passes the one-time code securely when you tap Start.' : 'Run a connection check to enable one-tap pairing.'} Only the first private chat is accepted.</small>
              </div>
            )}
            <div className="tg-divider" />
            <form onSubmit={saveAddress} className="tg-address">
              <label htmlFor="mobius-address">Möbius address</label>
              <p className="tg-help">Images stay in Möbius. Add its HTTPS address for open-in-Möbius buttons in Telegram. Links contain no sign-in key.</p>
              <input id="mobius-address" type="url" value={address} onChange={event=>setAddress(event.target.value)} placeholder="https://your-mobius.example" autoComplete="url" />
              <button className="tg-secondary" type="submit">Save address</button>
            </form>
          </div>

          <aside className="tg-side-card">
            <div className="tg-side-top"><div><span>Bridge status</span><h2>{status.label || DEFAULT_STATUS.label}</h2></div><div className={`tg-status-dot tg-${tone}`} /></div>
            <p>{status.detail || DEFAULT_STATUS.detail}</p>
            <dl>
              <div><dt>Bot</dt><dd>{status.botUsername ? `@${status.botUsername}` : 'Not checked'}</dd></div>
              <div><dt>Last check</dt><dd>{prettyTime(status.checkedAt)}</dd></div>
              <div><dt>Delivery</dt><dd>Text + Möbius links</dd></div>
            </dl>
            <button className={`tg-toggle ${settings.enabled ? 'is-on' : ''}`} onClick={toggleEnabled}><span><i />{settings.enabled ? 'Bridge on' : 'Bridge paused'}</span><b>{settings.enabled ? 'Pause' : 'Resume'}</b></button>
            <div className="tg-activity">
              <h3>Recent activity</h3>
              {(status.events || []).length ? status.events.slice(0, 5).map((item, index) => (
                <div className="tg-event" key={`${item.at}-${index}`}><i className={`is-${item.tone || 'neutral'}`} /><span>{item.label}</span><time>{prettyTime(item.at)}</time></div>
              )) : <div className="tg-empty">Activity appears after the first check.</div>}
            </div>
          </aside>
        </section>

        </details>
  )
  return (
    <div className="tg-root">
      <style>{CSS}</style>
      <main className="tg-wrap">
        <section className="tg-hero">
          <div className="tg-hero-copy">
            <div className="tg-eyebrow"><ShieldCheck size={16} /> Owner remote</div>
            <h1>Telegram Bridge</h1>
            <p>Build and manage through your owner bot. Use each specialist in its own Telegram chat.</p>
          </div>
        </section>

        {notice && <div className="tg-notice" role="status">{notice}</div>}

        {!pairing && setupPanel}
        {pairing&&<section className="tg-main-card"><div className="tg-section-head"><div><h2>{settings.enabled?(status.label||'Checking connection'):'Paused'}</h2></div>{botUsername&&<a className="tg-primary" href={`https://t.me/${botUsername}`} target="_blank" rel="noreferrer">Open Telegram <ArrowUpRight size={16}/></a>}</div><p className="tg-help">{chats.find(c=>c.id===activeChatId)?`Current chat: ${displayChatTitle(chats.find(c=>c.id===activeChatId))}`:'Send a message in Telegram to continue.'}</p></section>}
        <section className="tg-main-card tg-user-management" aria-label="Telegram user management">
          <div className="tg-section-head"><div><h2>User management in Telegram</h2></div></div>
          <p className="tg-help">{accessCurrent?'Connected for your current and future bots. In Telegram, open My bots → choose a bot → Users. Approve requests and control alerts there.':'Connect once, then manage users and request alerts for your current and future bots directly in your owner Telegram chat. Private conversations and notes stay hidden.'}</p>
          <button className="tg-primary" disabled={!pairing||!!connectionBusy} onClick={()=>changeAccessConnection(!!accessCurrent)}>{connectionBusy==='access'?'Opening…':accessCurrent?'Disconnect user management':accessConnection?'Reconnect user management':'Enable user management'}</button>
          {!pairing&&<p className="tg-help">Pair your owner Telegram chat first.</p>}
          {accessConnection&&!accessCurrent&&<button className="tg-text-btn" disabled={!!connectionBusy} onClick={()=>changeAccessConnection(true)}>Disconnect old connection</button>}
        </section>
        <details className="tg-conversations" onToggle={event=>{if(event.currentTarget.open)loadStudio()}}><summary>Your bots{studio?` · ${studio.assistants.length}`:''}</summary>
          <div className="tg-conversation-head"><div><h2>Build in one place</h2><p>Telegram Bot Studio is a separate, optional app for building bots. Open customization in Möbius; user management in Telegram needs its own approval. Private user conversations are not shown.</p></div>{studio&&<button className="tg-secondary" onClick={()=>window.parent.postMessage({type:'moebius:open-app',appId:studio.app_id},'*')}>Open Studio <ArrowUpRight size={15}/></button>}</div>
          {studioError?<p className="tg-notice" role="alert">{studioError} <button className="tg-text-btn" onClick={loadStudio}>Try again</button></p>:!studio?<p>Loading bots…</p>:studio.assistants.length===0?<p>No bots yet. Create your first one in Studio.</p>:<div className="tg-conversation-list">{studio.assistants.map(bot=>{
            return <div className="tg-bot-entry" key={bot.id}>
              <button className="tg-conversation-row tg-bot-row" onClick={()=>bot.editing_chat?.id?openConversation(bot.editing_chat.id):window.parent.postMessage({type:'moebius:open-app',appId:studio.app_id},'*')}><div className="tg-chat-copy"><strong>{bot.name}</strong><span>{bot.development.status} · {bot.development.release_label}</span></div><span className="tg-open-chat">{bot.editing_chat?.id?'Customize':bot.connection?.username?'Customize in Studio':'Set up in Studio'} <ArrowUpRight size={15}/></span></button>
            </div>
          })}</div>}
        </details>
        <details className="tg-conversations"><summary>Conversations · {chats.length}</summary>
          <div className="tg-conversation-head">
            <div>
              <span>Telegram conversations</span>
              <h2>Your chats</h2>
              <p>Continue a conversation here. In Telegram, use Chats or My bots.</p>
            </div>
            <button className="tg-primary tg-new-chat" onClick={createConversation} disabled={!pairing || creatingChat}>
              <Plus size={16} />{creatingChat ? 'Starting…' : 'New conversation'}
            </button>
          </div>
          <div className="tg-conversation-list">
            {chats.length ? (showAllChats?chats:chats.slice(0,3)).map(chat => (
              <button className="tg-conversation-row" key={chat.id} onClick={() => openConversation(chat.id)}>
                <div className="tg-chat-mark">TG</div>
                <div className="tg-chat-copy">
                  <strong>{displayChatTitle(chat)}</strong>
                  <span>{chat.pending_question_id ? 'Waiting for your answer' : (chat.has_messages ? 'Conversation in progress' : 'Ready for its first message')} · {prettyTime(chat.activity_at || chat.created_at)}</span>
                </div>
                {chat.pending_question_id
                  ? <em className="is-question">Question</em>
                  : (chat.id === activeChatId && <em>Current</em>)}
                <span className="tg-open-chat">Open <ArrowUpRight size={15} /></span>
              </button>
            )) : (
              <div className="tg-conversation-empty">
                <div className="tg-chat-mark">TG</div>
                <div><strong>No conversations yet</strong><span>Send a message to your bot or start one here.</span></div>
              </div>
            )}
          </div>
          {chats.length>3&&<button className="tg-text-btn" onClick={()=>setShowAllChats(v=>!v)}>{showAllChats?'Show recent chats':`Show all ${chats.length} chats`}</button>}
        </details>

        {pairing && setupPanel}
        <footer><ShieldCheck size={15} /> Your personal owner channel. Specialist users have separate bots and private data.</footer>
      </main>
    </div>
  )
}
