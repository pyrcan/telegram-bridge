// Owner handoff fixture only: no real grant, approval, Telegram or model call.
const fs=require('fs');
(async()=>{
 const port=fs.readFileSync(process.env.AGENT_BROWSER_PROFILE+'/DevToolsActivePort','utf8').split('\n')[0];
 const targets=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
 const target=targets.find(t=>t.type==='page'&&t.url==='http://127.0.0.1:8768/bridge.html');
 if(!target)throw Error('Open the isolated Bridge fixture first');
 const ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
 let id=0;const pending=new Map();ws.onmessage=e=>{const m=JSON.parse(e.data);if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}};
 const ev=expression=>new Promise((res,rej)=>{const n=++id;pending.set(n,m=>m.error||m.result.exceptionDetails?rej(Error(JSON.stringify(m.error||m.result.exceptionDetails))):res(m.result.result.value));ws.send(JSON.stringify({id:n,method:'Runtime.evaluate',params:{expression,awaitPromise:true,returnByValue:true}}))});
 try{console.log(JSON.stringify(await ev(`(async()=>{
  const originalPost=window.parent.postMessage;
  if(!window.__syntheticTelegramPreview)throw Error('Synthetic fixture required');
  const frames=async()=>{await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)))};
  const assert=(v,m)=>{if(!v)throw Error(m)};
  let actions=[];
  window.parent.postMessage=value=>{assert(value.type==='moebius:new-chat'&&!value.autoSend,'Editable draft only');const input=JSON.parse(value.draft.slice(value.draft.indexOf('{')));assert(input.action==='connect-access','Wrong action');actions.push(input);};
  try{
   const buttons=[...document.querySelectorAll('button')];
   const matches=buttons.filter(b=>b.textContent==='Enable user management');
   assert(matches.length===1,'Exactly one visible owner connection');
   assert(!buttons.some(b=>b.textContent==='Connect approvals'),'No per-bot access setup');
   assert(document.body.textContent.includes('current and future bots'),'Coverage explained');
   matches[0].click();await frames();
   const ctx=actions[0]?.context;
   assert(ctx?.scope==='owned-bots-v1'&&!ctx.assistant,'Explicit all-owned-bots scope');
   assert(ctx.paired_user_id&&ctx.paired_user_id===ctx.paired_chat_id&&ctx.paired_at,'Exact private pairing');
   assert(matches[0].textContent==='Enable user management','Cancel leaves disconnected');
   assert(actions.length===1,'One handoff, not one per bot');
   return {ok:true,syntheticActions:actions.length,checks:['one visible setup','current and future scope','paired owner','trusted handoff','cancel leaves disconnected']};
  }finally{window.parent.postMessage=originalPost}
 })()`)))}finally{ws.close()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
