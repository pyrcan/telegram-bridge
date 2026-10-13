export const CSS = `

  * { box-sizing: border-box; }
  /* mobius-ui:Root */
  .tg-root { position:relative; min-height:100dvh; overflow-x:clip; background:var(--bg); color:var(--text); font-family:var(--font); }
  /* /mobius-ui:Root */
  .tg-wrap { max-width:760px; margin:auto; padding:24px 20px 36px; }
  /* mobius-ui:Header */
  .tg-hero {display:flex;gap:16px;align-items:center;margin-bottom:20px;}
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
  .tg-overview { display:flex; align-items:center; justify-content:space-between; gap:22px; border-left:3px solid var(--accent); }
  .tg-overview.tg-good { border-left-color:var(--green); }
  .tg-overview.tg-warn { border-left-color:#df8d22; }
  .tg-overview.tg-idle { border-left-color:var(--muted); }
  .tg-overview-copy { min-width:0; }
  .tg-overview-kicker { display:block; margin-bottom:5px; color:var(--muted); font-size:11px; font-weight:750; letter-spacing:.05em; text-transform:uppercase; }
  .tg-overview h2 { margin:0; font-size:20px; letter-spacing:-.025em; }
  .tg-overview .tg-help { margin:7px 0 0; }
  .tg-overview-meta { margin:7px 0 0; color:var(--muted); font-size:12px; }
  .tg-overview-action { flex:none; }
  .tg-section-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
  .tg-section-head > div { display: flex; align-items: center; gap: 10px; }
  .tg-section-head h2, .tg-side-card h2 { margin: 0; font-size: 19px; letter-spacing: -.02em; }
  .tg-section-head a:not(.tg-primary) { min-height: 44px; display: flex; align-items: center; gap: 4px; color: var(--accent); font-size: 13px; font-weight: 700; text-decoration: none; }
  .tg-step { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 9px; background: color-mix(in srgb, var(--accent) 12%, var(--surface2, var(--surface))); color: var(--accent); font-size: 13px; font-weight: 800; }
  .tg-help { margin: 13px 0 16px; color: var(--muted); font-size: 14px; line-height: 1.55; }
  .tg-token-actions, .tg-paired-actions { display: flex; align-items: center; gap: 8px; }
  button { font: inherit; }
  .tg-primary, .tg-secondary, .tg-text-btn, .tg-danger, .tg-toggle, .tg-code, .tg-cancel-revoke { min-height: 44px; border-radius: 10px; cursor: pointer; }
  .tg-primary { display:inline-flex;align-items:center;justify-content:center;gap:6px;text-decoration:none;padding: 0 17px; border: 0; background: var(--accent); color: var(--accent-fg); font-weight: 750; }
  .tg-secondary { padding: 0 14px; border: 1px solid var(--border); background: var(--surface2, var(--surface)); color: var(--text); font-weight: 700; }
  .tg-primary:disabled, .tg-text-btn:disabled { cursor: default; opacity: .5; }
  .tg-token-saved { display: flex; flex-direction:column; align-items: stretch; justify-content: space-between; gap: 14px; min-height: 64px; padding: 10px 12px 10px 14px; border: 1px solid color-mix(in srgb, var(--green) 25%, var(--border)); border-radius: 10px; background: color-mix(in srgb, var(--green) 6%, var(--surface2, var(--surface))); }
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
/* mobius-ui:AppShell — Bridge owns the fixed menu chrome and body scroll. */
.tg-root {
  --tg-soft: color-mix(in srgb, var(--accent) 11%, var(--surface));
  display:flex; flex-direction:column; height:100dvh; min-height:0; width:100%; max-width:100%;
  overflow:hidden; background:var(--surface); color-scheme:inherit; -webkit-font-smoothing:antialiased;
}
.tg-header { flex:0 0 auto; display:flex; align-items:center; justify-content:space-between; gap:12px;
  min-height:65px; padding:10px 18px; padding-top:max(10px,env(safe-area-inset-top)); border-bottom:1px solid var(--border); background:var(--surface); }
.tg-header h1 { margin:0; font-size:18px; letter-spacing:-.5px; font-weight:650; }
.tg-icon-btn { width:44px; height:44px; display:grid; place-items:center; border:0; border-radius:12px; background:transparent; color:var(--text); cursor:pointer; }
.tg-icon-btn:hover { background:var(--tg-soft); }
.tg-scroll { flex:1; min-height:0; overflow-y:auto; overflow-x:hidden; padding:22px 18px 28px; overscroll-behavior-y:contain; scrollbar-width:thin; scrollbar-color:var(--border) transparent; }
.tg-scroll > * { flex-shrink:0; }
.tg-page { width:100%; max-width:680px; margin:0 auto; }
.tg-view-title { margin:0 0 19px; font-size:25px; line-height:1.2; font-weight:650; letter-spacing:-.9px; }
.tg-current-card { width:100%; display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:100px;
  padding:15px 16px; margin:0 0 24px; text-align:left; border:0; border-radius:15px; background:var(--tg-soft); color:var(--text); cursor:pointer; }
.tg-current-card > div { min-width:0; flex:1; }
.tg-context-label { display:block; color:var(--accent); font-size:10px; font-weight:650; text-transform:uppercase; letter-spacing:1.15px; }
.tg-current-card strong { display:block; margin-top:7px; font-size:15px; font-weight:600; line-height:1.35; }
.tg-current-card p { margin:5px 0 0; color:var(--muted); font-size:12px; }
.tg-current-card > svg { flex:none; color:var(--accent); }
.tg-section-label { margin:0; font-size:11px; font-weight:650; text-transform:uppercase; letter-spacing:1px; color:var(--muted); }
.tg-recent-head { display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:6px; margin:0 0 2px; }
.tg-recent-head .tg-conversation-tabs { margin:0; gap:1px; }
.tg-recent-head .tg-conversation-tabs button { flex:none; padding:0 8px; font-weight:500; font-size:11px; border:0; }
.tg-recent-head .tg-conversation-tabs button[aria-pressed=true] { color:var(--accent); background:var(--tg-soft); }
.tg-bottom-nav { flex:0 0 auto; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:3px; padding:7px 9px max(9px,env(safe-area-inset-bottom)); border-top:1px solid var(--border); background:var(--surface); }
.tg-nav-btn { display:flex; align-items:center; justify-content:center; flex-direction:column; gap:4px; min-height:53px; border:0; border-radius:12px; background:transparent; color:var(--muted); font-size:10px; cursor:pointer; }
.tg-nav-btn[aria-current=page] { color:var(--accent); background:var(--tg-soft); font-weight:650; }
.tg-list-row { display:flex; align-items:center; width:100%; gap:11px; padding:13px 0; min-height:75px; text-align:left; border:0; border-bottom:1px solid var(--border); background:transparent; color:var(--text); cursor:pointer; }
.tg-list-row .tg-chat-copy { flex:1; }
.tg-list-row .tg-chat-copy strong { font-weight:600; }
.tg-list-row > svg { flex:none; color:var(--muted); }
.tg-list-row:hover { background:var(--tg-soft); }
.tg-bot-row .tg-chat-copy span { display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.tg-bot-tag.is-draft { color:var(--muted); background:var(--bg); }
.tg-bot-tag { flex:none; display:inline-block; max-width:110px; padding:5px 7px; border-radius:7px; font-size:10px; font-weight:600; color:var(--accent); background:var(--tg-soft); }
.tg-detail-icon { width:58px; height:58px; display:grid; place-items:center; margin:5px 0 16px; border-radius:17px; color:var(--accent); background:var(--tg-soft); }
.tg-back { display:inline-flex; align-items:center; gap:5px; min-height:44px; margin:-9px 0 10px; padding:0; background:transparent; border:0; color:var(--accent); font-size:12px; cursor:pointer; }
.tg-bot-facts { margin:20px 0; }
.tg-bot-facts > div { display:flex; justify-content:space-between; gap:16px; padding:12px 0; border-bottom:1px solid var(--border); font-size:12px; line-height:1.5; }
.tg-bot-facts dt { color:var(--muted); } .tg-bot-facts dd { margin:0; text-align:right; }
.tg-button-stack { display:grid; gap:9px; margin:24px 0 18px; }
.tg-button-stack button { min-height:46px; white-space:normal; padding:10px 14px; }
.tg-quiet-note { margin:16px 0 0; color:var(--muted); font-size:12px; line-height:1.5; }
.tg-studio-link { display:inline-flex; align-items:center; gap:6px; margin-top:16px; }
.tg-studio-empty { background:var(--bg); border:0; border-radius:15px; padding:20px 17px; }
.tg-studio-options { margin-top:22px; }
.tg-overview { box-shadow:none; padding:18px; }
.tg-settings .tg-grid, #tg-connection-body .tg-grid { grid-template-columns:minmax(0,1fr); }
.tg-main-card, .tg-side-card { box-shadow:none; }
.tg-notice { margin:0 0 16px; font-size:13px; line-height:1.5; }
.tg-scroll footer { padding-bottom:6px; }
@media (min-width:760px) { .tg-header { padding-inline:max(18px,calc((100% - 680px)/2)); } .tg-bottom-nav { padding-inline:max(9px,calc((100% - 680px)/2)); } }
@media (max-width:360px) { .tg-scroll { padding:20px 16px 24px; } }
.tg-root {font-family:var(--font); --green:#238452;}
.tg-main-card {margin:16px 0;padding:18px;box-shadow:none}
.tg-main-card h3{margin:8px 0;font-size:16px}
.tg-chat-copy{min-width:0;display:flex;flex-direction:column;gap:5px;text-align:left}
.tg-chat-copy strong{font-size:14px}.tg-chat-copy span{color:var(--muted);font-size:12px;line-height:1.5}
.tg-code code{font-size:14px;letter-spacing:.02em}
.tg-current-empty{margin:16px 0;padding:18px;border-radius:14px;background:var(--bg)}
.tg-primary,.tg-secondary{min-height:44px;white-space:normal;padding:10px 16px;gap:6px}
.tg-studio-empty{padding:18px;background:var(--bg);border-radius:14px}
a.tg-primary,a.tg-secondary{text-decoration:none}
button:focus-visible,a:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
button:disabled{opacity:.55;cursor:not-allowed}
.tg-current-card{text-align:left;cursor:pointer;padding:18px;border:1px solid var(--border);border-radius:15px;background:var(--tg-soft)}
.tg-current-card h3{margin:8px 0;font-size:17px}.tg-current-card p{margin:0;font-size:12px;color:var(--muted)}
.tg-notice{margin:0 0 16px;font-size:13px;line-height:1.5}
@media(max-width:480px){.tg-scroll{padding:20px 16px 24px}.tg-main-card{padding:16px}.tg-primary{max-width:100%}}
@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation:none!important;transition:none!important;scroll-behavior:auto!important}}

`
