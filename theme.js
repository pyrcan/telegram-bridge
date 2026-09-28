export const CSS = `
.tg-settings{margin-top:24px}.tg-settings>summary{min-height:44px;cursor:pointer;color:var(--muted);padding:12px 0}.tg-settings .tg-grid{margin-top:16px}

  * { box-sizing: border-box; }
  /* mobius-ui:Root */
  .tg-root { position:relative; min-height:100dvh; overflow-x:clip; background:var(--bg); color:var(--text); font-family:var(--font); }
  /* /mobius-ui:Root */
  .tg-wrap { max-width:760px; margin:auto; padding:32px 20px 48px; }
  /* mobius-ui:Header */
  .tg-hero {display:flex;gap:16px;align-items:center;margin-bottom:24px;}
  .tg-hero-copy{min-width:0;flex:1}
  /* /mobius-ui:Header */
  .tg-eyebrow { display: flex; align-items: center; gap: 7px; color: var(--accent); font-weight: 720; font-size: 13px; letter-spacing: .05em; text-transform: uppercase; }
  .tg-hero h1 { margin: 7px 0 6px; font-size: 28px; line-height: 1.02; letter-spacing: -.045em; }
  .tg-hero p { margin: 0; color: var(--muted); font-size: 16px; max-width: 620px; line-height: 1.5; }
  .tg-live { position: relative; z-index: 1; display: flex; align-items: center; gap: 8px; min-height: 38px; padding: 0 13px; border: 1px solid var(--border); border-radius: 99px; background: color-mix(in srgb, var(--surface) 84%, transparent); font-size: 13px; font-weight: 700; white-space: nowrap; }
  .tg-live span, .tg-status-dot { width: 9px; height: 9px; border-radius: 50%; background: #9aa4ad; box-shadow: 0 0 0 4px color-mix(in srgb, #9aa4ad 15%, transparent); }
  .tg-live.tg-good span, .tg-status-dot.tg-good { background: var(--green); box-shadow: 0 0 0 4px color-mix(in srgb, var(--green) 16%, transparent); }
  .tg-live.tg-working span, .tg-status-dot.tg-working { background: var(--accent); box-shadow: 0 0 0 4px color-mix(in srgb, var(--accent) 18%, transparent); }
  .tg-live.tg-warn span, .tg-status-dot.tg-warn { background: #df8d22; box-shadow: 0 0 0 4px color-mix(in srgb, #df8d22 16%, transparent); }
  .tg-notice { margin-top: 14px; padding: 12px 15px; border-radius: 14px; border: 1px solid color-mix(in srgb, var(--accent) 26%, var(--border)); background: color-mix(in srgb, var(--accent) 8%, var(--surface)); color: var(--text); font-size: 14px; }
  .tg-grid { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(280px, .8fr); gap: 18px; margin-top: 18px; }
  .tg-main-card, .tg-side-card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; box-shadow: 0 14px 36px rgba(15, 35, 50, .055); }
  .tg-section-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
  .tg-section-head > div { display: flex; align-items: center; gap: 10px; }
  .tg-section-head h2, .tg-side-card h2 { margin: 0; font-size: 19px; letter-spacing: -.02em; }
  .tg-section-head a:not(.tg-primary) { min-height: 44px; display: flex; align-items: center; gap: 4px; color: var(--accent); font-size: 13px; font-weight: 700; text-decoration: none; }
  .tg-step { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 9px; background: color-mix(in srgb, var(--accent) 12%, var(--surface2, var(--surface))); color: var(--accent); font-size: 13px; font-weight: 800; }
  .tg-help { margin: 13px 0 16px; color: var(--muted); font-size: 14px; line-height: 1.55; }
  .tg-token-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; }
  .tg-form-actions, .tg-token-actions, .tg-paired-actions { display: flex; align-items: center; gap: 8px; }
  .tg-input-wrap { min-height: 48px; display: flex; align-items: center; gap: 10px; padding: 0 14px; border: 1px solid var(--border); border-radius: 14px; background: var(--surface2, var(--surface)); color: var(--muted); }
  .tg-input-wrap:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 16%, transparent); }
  .tg-input-wrap input { width: 100%; border: 0; outline: 0; background: transparent; color: var(--text); font: inherit; }
  button { font: inherit; }
  .tg-primary, .tg-secondary, .tg-text-btn, .tg-danger, .tg-toggle, .tg-code, .tg-cancel-revoke { min-height: 44px; border-radius: 10px; cursor: pointer; }
  .tg-primary { display:inline-flex;align-items:center;justify-content:center;gap:6px;text-decoration:none;padding: 0 17px; border: 0; background: var(--accent); color: var(--accent-fg); font-weight: 750; box-shadow: 0 8px 18px rgba(34,158,217,.24); }
  .tg-secondary { padding: 0 14px; border: 1px solid var(--border); background: var(--surface2, var(--surface)); color: var(--text); font-weight: 700; }
  .tg-primary:disabled, .tg-text-btn:disabled { cursor: default; opacity: .5; }
  .tg-token-saved { display: flex; align-items: center; justify-content: space-between; gap: 14px; min-height: 64px; padding: 10px 12px 10px 14px; border: 1px solid color-mix(in srgb, var(--green) 25%, var(--border)); border-radius: 10px; background: color-mix(in srgb, var(--green) 6%, var(--surface2, var(--surface))); }
  .tg-token-badge { display: flex; align-items: center; gap: 10px; color: var(--green); }
  .tg-token-badge span, .tg-token-badge strong, .tg-token-badge small { display: block; }
  .tg-token-badge strong { color: var(--text); font-size: 13px; }
  .tg-token-badge small { margin-top: 2px; color: var(--muted); font-size: 11px; }
  .tg-inline-status { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 12px; }
  .tg-inline-status > span { display: flex; align-items: center; gap: 5px; color: var(--muted); font-size: 12px; }
  .tg-inline-status > span.is-ok { color: var(--green); }
  .tg-text-btn { display: flex; align-items: center; gap: 6px; padding: 0 7px; border: 0; background: transparent; color: var(--accent); font-size: 13px; font-weight: 700; }
  .tg-divider { height: 1px; margin: 23px 0; background: var(--border); }
  .tg-pair-box { margin-top: 15px; padding: 18px; border-radius: 18px; background: linear-gradient(135deg, color-mix(in srgb, var(--accent) 8%, var(--surface2, var(--surface))), var(--surface2, var(--surface))); border: 1px dashed color-mix(in srgb, var(--accent) 34%, var(--border)); }
  .tg-pair-box p { margin: 0 0 10px; color: var(--muted); font-size: 13px; }
  .tg-pair-link { min-height: 48px; display: flex; align-items: center; justify-content: center; gap: 7px; margin-bottom: 12px; padding: 0 15px; border-radius: 14px; background: var(--accent); color: var(--accent-fg); font-size: 14px; font-weight: 780; text-decoration: none; box-shadow: 0 8px 18px rgba(34,158,217,.22); }
  .tg-code { width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 0 15px; border: 1px solid color-mix(in srgb, var(--accent) 28%, var(--border)); background: var(--surface); color: var(--text); }
  .tg-code code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: clamp(14px, 2vw, 18px); font-weight: 750; letter-spacing: .04em; }
  .tg-pair-box small { display: block; margin-top: 10px; color: var(--muted); line-height: 1.45; }
  .tg-paired { display: grid; grid-template-columns: 44px 1fr auto; gap: 12px; align-items: center; margin-top: 14px; padding: 14px; border: 1px solid color-mix(in srgb, var(--green) 25%, var(--border)); border-radius: 17px; background: color-mix(in srgb, var(--green) 6%, var(--surface2, var(--surface))); }
  .tg-avatar { width: 44px; height: 44px; display: grid; place-items: center; border-radius: 50%; background: var(--accent); color: var(--accent-fg); font-weight: 800; }
  .tg-paired strong, .tg-paired span { display: block; }
  .tg-paired span { margin-top: 3px; color: var(--muted); font-size: 12px; }
  .tg-danger { display: flex; align-items: center; gap: 6px; padding: 0 11px; border: 1px solid color-mix(in srgb, var(--danger) 30%, var(--border)); background: transparent; color: var(--danger); font-size: 12px; font-weight: 700; }
  .tg-danger.is-confirming { background: var(--danger); color: var(--accent-fg); border-color: var(--danger); }
  .tg-open-bot { min-height: 44px; display: flex; align-items: center; gap: 4px; color: var(--accent); font-size: 12px; font-weight: 750; text-decoration: none; white-space: nowrap; }
  .tg-cancel-revoke { padding: 0 8px; border: 0; background: transparent; color: var(--muted); font-size: 12px; font-weight: 700; }
  .tg-side-card { display: flex; flex-direction: column; }
  .tg-side-top { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
  .tg-side-top span { color: var(--muted); font-size: 12px; }
  .tg-side-top h2 { margin-top: 4px; }
  .tg-status-dot { flex: 0 0 auto; }
  .tg-side-card > p { min-height: 40px; color: var(--muted); font-size: 13px; line-height: 1.5; }
  .tg-side-card dl { margin: 6px 0 17px; }
  .tg-side-card dl div { display: flex; justify-content: space-between; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 12px; }
  .tg-side-card dt { color: var(--muted); }
  .tg-side-card dd { margin: 0; font-weight: 650; text-align: right; }
  .tg-toggle { width: 100%; display: flex; align-items: center; justify-content: space-between; padding: 0 13px; border: 1px solid var(--border); background: var(--surface2, var(--surface)); color: var(--text); }
  .tg-toggle span { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 700; }
  .tg-toggle i { width: 9px; height: 9px; border-radius: 50%; background: #9aa4ad; }
  .tg-toggle.is-on i { background: var(--green); }
  .tg-toggle b { color: var(--accent); font-size: 12px; }
  .tg-activity { margin-top: 22px; }
  .tg-activity h3 { margin: 0 0 10px; font-size: 13px; }
  .tg-event { display: grid; grid-template-columns: 8px 1fr auto; align-items: center; gap: 8px; min-height: 33px; font-size: 11px; }
  .tg-event i { width: 6px; height: 6px; border-radius: 50%; background: #9aa4ad; }
  .tg-event i.is-good { background: var(--green); } .tg-event i.is-warn { background: #df8d22; }
  .tg-event time { color: var(--muted); font-size: 10px; }
  .tg-empty { color: var(--muted); font-size: 12px; padding: 9px 0; }
  .tg-conversations > summary { min-height:44px; cursor:pointer; display:list-item; font-weight:600; padding:10px 0; }
  .tg-conversations[open] > summary { margin-bottom:16px; }
  .tg-conversations { margin-top: 18px; padding: 24px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); box-shadow: 0 14px 36px rgba(15,35,50,.055); }
  .tg-conversation-head { display: flex; align-items: center; justify-content: space-between; gap: 22px; }
  .tg-conversation-head > div > span { color: var(--accent); font-size: 12px; font-weight: 750; letter-spacing: .04em; text-transform: uppercase; }
  .tg-conversation-head h2 { margin: 5px 0 4px; font-size: 22px; letter-spacing: -.025em; }
  .tg-conversation-head p { max-width: 680px; margin: 0; color: var(--muted); font-size: 13px; line-height: 1.5; }
  .tg-new-chat { min-height: 46px; display: flex; align-items: center; gap: 7px; white-space: nowrap; }
  .tg-conversation-list { display: grid; gap: 9px; margin-top: 18px; }
  .tg-conversation-row { width: 100%; min-height: 68px; display: grid; grid-template-columns: 42px minmax(0,1fr) auto auto; align-items: center; gap: 12px; padding: 11px 13px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface2, var(--surface)); color: var(--text); text-align: left; cursor: pointer; }
  .tg-conversation-row:hover { border-color: color-mix(in srgb, var(--accent) 35%, var(--border)); background: color-mix(in srgb, var(--accent) 5%, var(--surface2, var(--surface))); }
  .tg-chat-mark { width: 42px; height: 42px; display: grid; place-items: center; border-radius: 10px; background: var(--accent); color: var(--accent-fg); font-size: 11px; font-weight: 850; letter-spacing: .05em; }
  .tg-chat-copy { min-width: 0; }
  .tg-chat-copy strong, .tg-chat-copy span, .tg-conversation-empty strong, .tg-conversation-empty span { display: block; }
  .tg-chat-copy strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 14px; }
  .tg-chat-copy span, .tg-conversation-empty span { margin-top: 4px; color: var(--muted); font-size: 11px; }
  .tg-conversation-row em { padding: 5px 8px; border-radius: 99px; background: color-mix(in srgb,var(--green) 11%,var(--surface)); color: var(--green); font-size: 10px; font-style: normal; font-weight: 800; }
  .tg-conversation-row em.is-question { background: color-mix(in srgb,#df8d22 14%,var(--surface)); color: #c47813; }
  .tg-open-chat { display: flex; align-items: center; gap: 4px; color: var(--accent); font-size: 12px; font-weight: 750; }
  .tg-conversation-empty { min-height: 68px; display: flex; align-items: center; gap: 12px; padding: 11px 13px; border: 1px dashed var(--border); border-radius: 10px; color: var(--text); }
  footer { display: flex; justify-content: center; align-items: center; gap: 7px; padding: 18px 6px 0; color: var(--muted); font-size: 12px; text-align: center; }
  .tg-loading { min-height: 100vh; display: grid; place-items: center; color: var(--muted); }
  button:focus-visible, a:focus-visible, input:focus-visible { outline: 3px solid color-mix(in srgb, var(--accent) 35%, transparent); outline-offset: 2px; }
  @media (max-width: 760px) {
    .tg-wrap { max-width:760px; margin:auto; padding:32px 20px 48px; }
    /* mobius-ui:Header */
  .tg-hero {display:flex;gap:16px;align-items:center;margin-bottom:24px;}
  .tg-hero-copy{min-width:0;flex:1}
  /* /mobius-ui:Header */
    .tg-hero h1 { margin-top: 4px; font-size: 31px; }
    .tg-hero p { font-size: 14px; line-height: 1.4; }
    .tg-eyebrow { font-size: 11px; }
    .tg-live { grid-column: 2; justify-self: start; }
    .tg-grid { grid-template-columns: 1fr; }
    .tg-main-card, .tg-side-card { padding: 19px; border-radius: 20px; }
    .tg-token-row { grid-template-columns: 1fr; }
    .tg-form-actions { justify-content: flex-end; }
    .tg-token-saved { align-items: stretch; flex-direction: column; }
    .tg-token-actions { justify-content: space-between; }
    .tg-primary { min-height: 48px; }
    .tg-inline-status { align-items: flex-start; flex-direction: column; }
    .tg-help { margin-left: 0; }
    .tg-section-head { align-items: flex-start; }
    .tg-paired { grid-template-columns: 44px 1fr; }
    .tg-paired-actions { grid-column: 1 / -1; justify-content: space-between; flex-wrap: wrap; }
    .tg-conversations { padding: 19px; border-radius: 20px; }
    .tg-conversation-head { align-items: flex-start; flex-direction: column; }
    .tg-new-chat { width: 100%; justify-content: center; }
    .tg-conversation-row { grid-template-columns: 42px minmax(0,1fr) auto; }
    .tg-open-chat { display: none; }
    .tg-conversation-row em { grid-column: 2 / -1; justify-self: start; }
  }
  .tg-conversation-row.tg-bot-row { grid-template-columns: minmax(0,1fr) auto; }
  .tg-bot-row .tg-open-chat { display:flex; max-width:115px; }
  @media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; animation: none !important; } }

.tg-bot-entry { border-bottom: 1px solid var(--border); }
.tg-bot-entry:last-child { border-bottom: 0; }
.tg-connection-line { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 14px 8px; color:var(--muted); font-size:12px; }
.tg-connection-line .tg-text-btn { min-height:44px; flex-shrink:0; }

.tg-user-management { margin-top: 18px; }
 .tg-address { display:grid; gap:12px; }
.tg-address label { font-weight:650; }
.tg-address input { width:100%; min-width:0; min-height:44px; border:1px solid var(--border); border-radius:12px; background:var(--bg); color:var(--text); padding:12px; font:inherit; }
.tg-address .tg-secondary { justify-self:start; }
`
