let apiKey = localStorage.getItem('oos_apikey') || '';
let lastSession = null;
let bureauStartTime = null, bureauDecision = '';
let isRunning = {};
document.addEventListener('DOMContentLoaded', () => {
  updateKeyUI();
  document.getElementById('de-question').addEventListener('keydown', e => { if(e.key==='Enter') runDecision(); });
  document.getElementById('modal-key').addEventListener('keydown', e => { if(e.key==='Enter') saveApiKey(); });
  document.getElementById('modal-key').addEventListener('input', e => updateModalKeyUI(e.target.value));
  if(apiKey) document.getElementById('modal-key').value = apiKey;
});
function switchTo(id) {
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
  document.getElementById('panel-'+id).classList.add('active');
  document.getElementById('nav-'+id).classList.add('active');
  if(id==='report') buildReport();
}
function openApiModal(){ document.getElementById('apiModal').classList.add('open'); if(apiKey) document.getElementById('modal-key').value=apiKey; updateModalKeyUI(apiKey); }
function closeApiModal(){ document.getElementById('apiModal').classList.remove('open'); }
function saveApiKey(){ const k=document.getElementById('modal-key').value.trim(); if(!k) return; apiKey=k; localStorage.setItem('oos_apikey',k); updateKeyUI(); updateModalKeyUI(k); }
function clearApiKey(){ apiKey=''; localStorage.removeItem('oos_apikey'); document.getElementById('modal-key').value=''; updateKeyUI(); updateModalKeyUI(''); }
function updateKeyUI(){
  const has=!!apiKey;
  document.getElementById('apikeyBtn').className='btn-apikey'+(has?' keyed':'');
  document.getElementById('apikeyBtn').textContent=has?'✓ API KEY':'⚙ API KEY';
  const el=document.getElementById('sidebarApiStatus');
  el.textContent=has?'● OPENAI CONFIGURED':'● NOT CONFIGURED';
  el.className=has?'ok':'no';
}
function updateModalKeyUI(k){
  const el=document.getElementById('modal-key-status');
  if(!k){el.className='modal-status';el.textContent='No key saved.';return;}
  if(k.startsWith('sk-')){el.className='modal-status ok';el.textContent='✓ Key looks valid. Ready to overthink.';}
  else{el.className='modal-status err';el.textContent='⚠ Key format looks wrong (expected sk-...).';}
}
function rnd(a,b){return Math.floor(Math.random()*(b-a+1))+a;}
function sleep(ms){return new Promise(r=>setTimeout(r,ms));}
async function callAPI(prompt, system='You are a helpful assistant.', maxTokens=250) {
  if(!apiKey) throw new Error('No API key configured. Click ⚙ API KEY to set one.');
  const res = await fetch('https://api.openai.com/v1/chat/completions', {
    method:'POST',
    headers:{'Content-Type':'application/json','Authorization':'Bearer '+apiKey},
    body:JSON.stringify({model:'gpt-4o-mini',max_tokens:maxTokens,messages:[{role:'system',content:system},{role:'user',content:prompt}]})
  });
  const data = await res.json();
  if(data.error) throw new Error(data.error.message);
  if(data.choices && data.choices[0]) return data.choices[0].message.content.trim();
  throw new Error('No response from API.');
}
function setStatus(id,text,active=false){
  const el=document.getElementById(id+'-status'),dot=document.getElementById(id+'-dot');
  if(el)el.textContent=text;if(dot)dot.className='pstatus-dot'+(active?' active':'');
}
function setProgress(id,pct){ const el=document.getElementById(id+'-prog'); if(el)el.style.width=pct+'%'; }
function makeThinking(){return`<div class="thinking"><span></span><span></span><span></span></div>`;}
function makeMetricBar(label,val,color){
  return`<div class="metric"><div class="metric-label">${label}</div><div class="metric-bar-row"><div class="metric-bar"><div class="metric-fill" data-val="${val}" style="width:0%;background:${color}"></div></div><div class="metric-val">${val}%</div></div></div>`;
}
function animateBars(container){ setTimeout(()=>{ container.querySelectorAll('.metric-fill[data-val]').forEach(el=>{el.style.width=el.dataset.val+'%';}); },60); }
function delear(){ document.getElementById('de-agents').innerHTML=''; document.getElementById('de-reveal').style.display='none'; document.getElementById('de-verdict').style.display='none'; setStatus('de','AWAITING QUERY',false); setProgress('de',0); }
function dvclear(){ document.getElementById('dv-angles').innerHTML=''; document.getElementById('dv-summary').innerHTML=''; setStatus('dv','READY TO DESTRUCT',false); setProgress('dv',0); }
function mtclear(){ document.getElementById('mt-verdict').style.display='none'; setStatus('mt','AWAITING INVITE',false); setProgress('mt',0); }
const DE_AGENTS=[
  {name:'OPTIMIST',   emoji:'😄',style:'wildly positive and enthusiastic, certain everything will work out perfectly',color:'#aaff2e'},
  {name:'PESSIMIST',  emoji:'😒',style:'deeply negative and doubtful, foreseeing total catastrophe and regret',color:'#ff2b54'},
  {name:'OVERTHINKER',emoji:'🧠',style:'extremely detailed and analytical, listing every variable, edge case, and sub-problem',color:'#00d9ff'},
  {name:'CHAOS AGENT',emoji:'🔥',style:'completely unpredictable and random, giving nonsensical yet strangely coherent advice',color:'#ffb800'},
  {name:'PHILOSOPHER',emoji:'🏛️',style:'deeply abstract, referencing ancient philosophy, questioning the nature of the question',color:'#b060ff'},
];
const DE_PREAMBLES=['After extensive interdimensional analysis...','Weighing 847 variables and 12 alternate timelines...','Cross-referencing with the Oracle Database v3.1...','Collapsing the probability waveform...','Overriding all rational thought processes...'];
const DE_VERDICTS=['YES.','NO.','MAYBE.','DO THE OPPOSITE.','FLIP A COIN.','YOU ALREADY KNEW.','CONSULT A DUCK.','BOTH. SIMULTANEOUSLY.','ABSOLUTELY NOT.','WHO CARES?','ASK AGAIN TOMORROW.','THE ANSWER IS WITHIN.'];
let deResponses=[];
async function runDecision(){
  if(isRunning.de) return;
  const q=document.getElementById('de-question').value.trim();
  if(!q){document.getElementById('de-question').focus();return;}
  if(!apiKey){openApiModal();return;}
  isRunning.de=true; delear(); deResponses=[];
  document.getElementById('de-btn').disabled=true;
  setStatus('de','INITIALIZING ABSURD ANALYSIS PROTOCOL...',true);
  const container=document.getElementById('de-agents');
  for(let i=0;i<DE_AGENTS.length;i++){
    const a=DE_AGENTS[i];
    const card=document.createElement('div');
    card.className='agent-card';card.style.animationDelay=(i*0.07)+'s';
    card.innerHTML=`<div class="agent-card-head"><span class="agent-emoji">${a.emoji}</span><div class="agent-name" style="color:${a.color}">${a.name}</div></div><div class="agent-body" id="de-body-${i}">${makeThinking()}</div><div class="agent-metrics" id="de-metrics-${i}" style="display:none"></div>`;
    container.appendChild(card);
    setStatus('de',`AGENT ${i+1}/${DE_AGENTS.length}: ${a.name} IS OVERTHINKING...`,true);
    try{
      const reply=await callAPI(`Question: "${q}"`,`You are the "${a.name}" ${a.emoji} analysis module in an absurd AI decision engine. Respond to the question in a ${a.style} way. 2-3 sentences max. Be specific to the question. Be funny. Do not break character.`,200);
      deResponses.push(reply);
      document.getElementById('de-body-'+i).textContent=reply;
      const conf=rnd(61,99),risk=rnd(5,95),chaos=rnd(0,100);
      const mx=document.getElementById('de-metrics-'+i);
      mx.style.display='flex';
      mx.innerHTML=makeMetricBar('CONFIDENCE',conf,a.color)+makeMetricBar('RISK INDEX',risk,'#ff2b54')+makeMetricBar('CHAOS FACTOR',chaos,'#ffb800');
      animateBars(mx);
    }catch(e){document.getElementById('de-body-'+i).innerHTML=`<span class="error-text">// AGENT MALFUNCTION: ${e.message}</span>`;}
    setProgress('de',((i+1)/DE_AGENTS.length)*100);
    await sleep(80);
  }
  setStatus('de','ANALYSIS COMPLETE — SYNTHESIZING VERDICT...',false);
  document.getElementById('de-reveal').style.display='block';
  document.getElementById('de-btn').disabled=false;
  isRunning.de=false;
  lastSession={type:'decision',question:q,responses:deResponses,agents:DE_AGENTS};
}
async function deReveal(){
  document.getElementById('de-reveal').style.display='none';
  const box=document.getElementById('de-verdict');box.style.display='block';
  document.getElementById('de-preamble').textContent=DE_PREAMBLES[Math.floor(Math.random()*DE_PREAMBLES.length)];
  document.getElementById('de-verdict-text').textContent='...';
  await sleep(900);
  const v=DE_VERDICTS[Math.floor(Math.random()*DE_VERDICTS.length)];
  document.getElementById('de-verdict-text').textContent=v;
  setStatus('de',`VERDICT: "${v}" — SESSION COMPLETE`,false);
  if(lastSession)lastSession.verdict=v;
}
const DV_ANGLES=[
  {label:'LOGICAL FALLACY',   color:'#ff2b54',style:'point out every logical flaw and fallacy in this opinion, citing formal logic'},
  {label:'HISTORICAL FAILURE',color:'#ffb800',style:'find historical precedents where this exact viewpoint led to disaster'},
  {label:'PHILOSOPHICAL',     color:'#b060ff',style:'destroy this from a philosophical standpoint using ethics and epistemology'},
  {label:'ECONOMIC IMPACT',   color:'#00d9ff',style:'analyze all the ways this belief is economically irrational and damaging'},
  {label:'THE CONTRARIAN',    color:'#aaff2e',style:'argue the exact opposite with total conviction, as if it is obviously correct'},
];
async function runDevil(){
  if(isRunning.dv) return;
  const opinion=document.getElementById('dv-input').value.trim();
  if(!opinion){document.getElementById('dv-input').focus();return;}
  if(!apiKey){openApiModal();return;}
  isRunning.dv=true; document.getElementById('dv-btn').disabled=true; dvclear();
  setStatus('dv',"DEPLOYING DEVIL'S ADVOCATE PROTOCOL...",true);
  const container=document.getElementById('dv-angles');
  let score=0;
  for(let i=0;i<DV_ANGLES.length;i++){
    const a=DV_ANGLES[i];
    setStatus('dv',`ANGLE ${i+1}/${DV_ANGLES.length}: ${a.label}...`,true);
    const card=document.createElement('div');
    card.className='destruct-card';card.style.animationDelay=(i*0.06)+'s';
    card.innerHTML=`<div class="destruct-angle" style="color:${a.color}">${a.label}</div><div class="destruct-body" id="dv-body-${i}">${makeThinking()}</div><div class="destruct-score" id="dv-score-${i}"></div>`;
    container.appendChild(card);
    try{
      const s=rnd(60,99); score+=s;
      const reply=await callAPI(`Opinion to destroy: "${opinion}"`,`You are a ruthless Devil's Advocate. Your task is to ${a.style}. Be specific, sharp, and devastating in 2-3 sentences. Do not hold back.`,220);
      document.getElementById('dv-body-'+i).textContent=reply;
      document.getElementById('dv-score-'+i).textContent=`Destruction power: ${s}%`;
    }catch(e){document.getElementById('dv-body-'+i).innerHTML=`<span class="error-text">// Angle ${a.label} failed: ${e.message}</span>`;}
    setProgress('dv',((i+1)/DV_ANGLES.length)*100);
    await sleep(60);
  }
  const avg=Math.round(score/DV_ANGLES.length);
  document.getElementById('dv-summary').innerHTML=`<div class="verdict-box" style="display:block;border-color:var(--purple);margin-top:12px;"><div class="verdict-pre">// TOTAL OPINION DESTRUCTION SCORE //</div><div class="verdict-text" style="color:var(--purple)">${avg}%</div><div class="verdict-preamble" style="margin-top:8px;">${avg>=85?'Your opinion has been completely obliterated.':avg>=70?'Your opinion has suffered severe structural damage.':'Your opinion survived, barely. Somehow.'}</div></div>`;
  setStatus('dv',`DESTRUCTION COMPLETE — SCORE: ${avg}%`,false);
  document.getElementById('dv-btn').disabled=false;
  isRunning.dv=false;
  lastSession={type:'devil',opinion,angles:DV_ANGLES,score:avg};
}
async function runMeeting(){
  if(isRunning.mt) return;
  const invite=document.getElementById('mt-input').value.trim();
  if(!invite){document.getElementById('mt-input').focus();return;}
  if(!apiKey){openApiModal();return;}
  isRunning.mt=true; document.getElementById('mt-btn').disabled=true; mtclear();
  setStatus('mt','ANALYZING MEETING NECESSITY...',true); setProgress('mt',50);
  try{
    const raw=await callAPI(`Meeting invite: "${invite}"`,`You are the Meeting Necessity Analyzer. Analyze this meeting invite and respond ONLY with a valid JSON object (no markdown, no explanation) with these exact fields: {"email_score":<number 0-100>,"verdict":<"DEFINITELY AN EMAIL"|"PROBABLY AN EMAIL"|"BORDERLINE"|"ACTUALLY USEFUL"|"NECESSARY EVIL">,"time_wasted_hours":<number>,"attendees_affected":<number>,"agenda_clarity":<number 0-100>,"analysis":<string, 2-3 sentence witty analysis>}`,300);
    let d;
    try{d=JSON.parse(raw);}catch{const m=raw.match(/\{[\s\S]*\}/);d=m?JSON.parse(m[0]):{email_score:rnd(60,95),verdict:'PROBABLY AN EMAIL',time_wasted_hours:rnd(1,8),attendees_affected:rnd(2,15),agenda_clarity:rnd(10,40),analysis:raw.replace(/[{}]/g,'').trim()};}
    setProgress('mt',100);
    const vd=document.getElementById('mt-verdict');vd.style.display='block';
    const score=d.email_score||rnd(60,95);
    const scoreEl=document.getElementById('mt-score');
    scoreEl.textContent=score+'%';scoreEl.style.color=score>=80?'var(--red)':score>=60?'var(--amber)':'var(--lime)';
    document.getElementById('mt-label').textContent=d.verdict||'PROBABLY AN EMAIL';
    document.getElementById('mt-label').style.color=score>=80?'var(--red)':score>=60?'var(--amber)':'var(--lime)';
    const mx=document.getElementById('mt-metrics');
    mx.innerHTML=makeMetricBar('EMAIL PROBABILITY',score,'#ff2b54')+makeMetricBar('TIME WASTED',Math.min(100,Math.round((d.time_wasted_hours||2)/8*100)),'#ffb800')+makeMetricBar('AGENDA CLARITY',d.agenda_clarity||rnd(10,40),'#00d9ff');
    animateBars(mx);
    document.getElementById('mt-analysis').innerHTML=`<div style="display:flex;gap:20px;margin-bottom:10px;flex-wrap:wrap;"><div><div style="font-family:var(--font-m);font-size:9px;color:var(--muted);letter-spacing:2px;">HOURS WASTED</div><div style="font-family:var(--font-d);font-size:22px;color:var(--red)">${d.time_wasted_hours||rnd(1,8)}</div></div><div><div style="font-family:var(--font-m);font-size:9px;color:var(--muted);letter-spacing:2px;">UNNECESSARY ATTENDEES</div><div style="font-family:var(--font-d);font-size:22px;color:var(--amber)">${d.attendees_affected||rnd(2,12)}</div></div></div><div style="font-family:var(--font-m);font-size:12px;line-height:1.7;">${d.analysis||'This meeting shows classic signs of calendar Stockholm Syndrome.'}</div>`;
    setStatus('mt',`ANALYSIS COMPLETE — ${score}% EMAIL PROBABILITY`,false);
    lastSession={type:'meeting',invite,data:d,score};
  }catch(e){
    setStatus('mt','ERROR: '+e.message,false);
    document.getElementById('mt-verdict').innerHTML=`<div class="error-text">// ${e.message}</div>`;
    document.getElementById('mt-verdict').style.display='block';
  }
  document.getElementById('mt-btn').disabled=false;
  isRunning.mt=false;
}
const REJECTIONS=[
  'Your request has been denied because Form 27-B was submitted on a <strong>Wednesday</strong>. Per Regulation 7.4(b), all forms must be submitted on Tuesdays between 9:14am and 9:17am.',
  'Your request has been denied because your Decision Urgency level conflicts with your Stakeholder count. Please resubmit with a matching urgency-to-stakeholder ratio (minimum 2.3:1).',
  'Form 1-A has been rejected due to an outstanding Form 1-A(prev) from a previous session. Please resolve all prior forms before submitting new ones. To obtain Form 1-A(prev), you must first file Form 99-X.',
  'Error: Your estimated stakeholder count exceeds the maximum allowed for Tier-2 decision requests. Please downgrade to a Tier-1 request or obtain a Tier-2 Stakeholder Exception (Form 55-SE).',
];
const CONDITIONS=[
  ['The decision must be made standing up.','You must document the outcome on Form 88-C within 30 business days.','A certified independent observer must witness the decision.','You agree not to reconsider the decision for a minimum of 72 hours.'],
  ['The decision is only valid on business days between 10am and 3pm.','You must file a Pre-Decision Impact Statement (Form 44-PI) before proceeding.','All parties involved must be notified via certified mail.','A secondary review will occur after 90 days.'],
  ['The decision must be logged in the Decision Registry (Form 12-DR).','You agree to submit a 500-word reflection report within 60 days.','This approval is non-transferable.','Approval is void if conditions are disclosed to parties not listed on Form 1-A.'],
];
const FINAL_VERDICTS=['YES.','NO.','MAYBE.','DO IT.',"DON'T DO IT.",'SLEEP ON IT.','ASK SOMEONE ELSE.','YOU ALREADY KNEW.'];
function bureauNext(step){
  document.querySelectorAll('.bureau-step').forEach(s=>s.classList.remove('active'));
  document.getElementById('bureau-'+step).classList.add('active');
  document.querySelectorAll('.step-pip').forEach((p,i)=>{p.className='step-pip'+(i<step?' done':i===step?' active':'');});
  document.getElementById('bureau-step-label').textContent=`Step ${step+1} of 8`;
  if(step===0){bureauStartTime=Date.now();bureauDecision=document.getElementById('b-decision').value||'your decision';}
  if(step===7){
    document.getElementById('bureau-time').textContent=`${Math.round((Date.now()-bureauStartTime)/1000)} seconds`;
    document.getElementById('bureau-final-q').textContent=`"${bureauDecision}"`;
    document.getElementById('bureau-final-v').textContent=FINAL_VERDICTS[Math.floor(Math.random()*FINAL_VERDICTS.length)];
  }
}
function bureauProcess(nextStep){
  document.querySelectorAll('.bureau-step').forEach(s=>s.classList.remove('active'));
  const ps=nextStep===2?2:5;
  document.getElementById('bureau-'+ps).classList.add('active');
  document.querySelectorAll('.step-pip').forEach((p,i)=>{p.className='step-pip'+(i<ps?' done':i===ps?' active':'');});
  document.getElementById('bureau-step-label').textContent=`Step ${ps+1} of 8`;
  const barId=ps===2?'bureau-proc-bar':'bureau-appeal-bar';
  const bar=document.getElementById(barId); bar.style.width='0%';
  let pct=0; const iv=setInterval(()=>{pct+=rnd(3,12);if(pct>=100){pct=100;clearInterval(iv);}bar.style.width=pct+'%';},200);
  setTimeout(()=>{
    if(ps===2){
      document.querySelectorAll('.bureau-step').forEach(s=>s.classList.remove('active'));
      document.getElementById('bureau-3').classList.add('active');
      document.querySelectorAll('.step-pip').forEach((p,i)=>{p.className='step-pip'+(i<3?' done':i===3?' active':'');});
      document.getElementById('bureau-step-label').textContent='Step 4 of 8';
      document.getElementById('bureau-rejection-text').innerHTML=REJECTIONS[Math.floor(Math.random()*REJECTIONS.length)];
    } else {
      document.querySelectorAll('.bureau-step').forEach(s=>s.classList.remove('active'));
      document.getElementById('bureau-6').classList.add('active');
      document.querySelectorAll('.step-pip').forEach((p,i)=>{p.className='step-pip'+(i<6?' done':i===6?' active':'');});
      document.getElementById('bureau-step-label').textContent='Step 7 of 8';
      const conds=CONDITIONS[Math.floor(Math.random()*CONDITIONS.length)];
      document.getElementById('bureau-conditions').innerHTML=conds.map((c,i)=>`${i+1}. ${c}`).join('<br>');
    }
  },rnd(2800,4200));
}
function resetBureau(){
  bureauDecision='';bureauStartTime=null;
  document.querySelectorAll('.bureau-step').forEach(s=>s.classList.remove('active'));
  document.getElementById('bureau-0').classList.add('active');
  document.querySelectorAll('.step-pip').forEach((p,i)=>{p.className='step-pip'+(i===0?' active':'');});
  document.getElementById('bureau-step-label').textContent='Step 1 of 8';
  document.getElementById('b-decision').value='';
  document.getElementById('bureau-proc-bar').style.width='0%';
  document.getElementById('bureau-appeal-bar').style.width='0%';
}
function buildReport(){
  const rc=document.getElementById('report-content');
  if(!lastSession){rc.innerHTML=`<div class="empty-state"><div style="font-size:32px;margin-bottom:12px;">📭</div>Run any analysis tool first, then return here.</div>`;return;}
  const s=lastSession,now=new Date().toLocaleString(),caseId='OOS-'+Math.floor(Math.random()*90000+10000);
  let metaHtml='',chartHtml='',bodyHtml='',titleText='',subtitleText='';
  if(s.type==='decision'){
    titleText='Decision Analysis Report';subtitleText=`Query: "${s.question}"`;
    metaHtml=`<div class="report-meta-item"><div class="report-meta-label">AGENTS CONSULTED</div><div class="report-meta-val">${s.agents.length}</div></div><div class="report-meta-item"><div class="report-meta-label">FINAL VERDICT</div><div class="report-meta-val">${s.verdict||'PENDING'}</div></div><div class="report-meta-item"><div class="report-meta-label">CONFIDENCE</div><div class="report-meta-val">${rnd(62,97)}%</div></div><div class="report-meta-item"><div class="report-meta-label">CHAOS INDEX</div><div class="report-meta-val">${rnd(44,91)}%</div></div>`;
    chartHtml=s.agents.map((a)=>{const v=rnd(55,99);return`<div class="report-bar-row"><div class="report-bar-label">${a.name}</div><div class="report-bar"><div class="report-bar-fill" style="width:${v}%;background:${a.color}"></div></div><div class="report-bar-pct">${v}%</div></div>`;}).join('');
    bodyHtml=(s.responses||[]).map((r,i)=>`<p><strong>${s.agents[i].name}:</strong> ${r}</p>`).join('');
  } else if(s.type==='devil'){
    titleText='Opinion Destruction Analysis';subtitleText=`Belief: "${s.opinion}"`;
    metaHtml=`<div class="report-meta-item"><div class="report-meta-label">DESTRUCTION SCORE</div><div class="report-meta-val">${s.score}%</div></div><div class="report-meta-item"><div class="report-meta-label">ANGLES DEPLOYED</div><div class="report-meta-val">${s.angles.length}</div></div><div class="report-meta-item"><div class="report-meta-label">OPINION VIABILITY</div><div class="report-meta-val">${100-s.score}%</div></div><div class="report-meta-item"><div class="report-meta-label">VERDICT</div><div class="report-meta-val">OBLITERATED</div></div>`;
    chartHtml=s.angles.map(a=>{const v=rnd(60,99);return`<div class="report-bar-row"><div class="report-bar-label">${a.label}</div><div class="report-bar"><div class="report-bar-fill" style="width:${v}%;background:${a.color}"></div></div><div class="report-bar-pct">${v}%</div></div>`;}).join('');
    bodyHtml=`<p>Total opinion destruction score: ${s.score}%. The belief has been systematically dismantled from ${s.angles.length} distinct angles.</p>`;
  } else if(s.type==='meeting'){
    const d=s.data||{};titleText='Meeting Necessity Assessment';subtitleText='Submitted invite analyzed';
    metaHtml=`<div class="report-meta-item"><div class="report-meta-label">EMAIL PROBABILITY</div><div class="report-meta-val">${s.score}%</div></div><div class="report-meta-item"><div class="report-meta-label">VERDICT</div><div class="report-meta-val" style="font-size:12px">${d.verdict||'EMAIL'}</div></div><div class="report-meta-item"><div class="report-meta-label">HOURS WASTED</div><div class="report-meta-val">${d.time_wasted_hours||'?'}</div></div><div class="report-meta-item"><div class="report-meta-label">AGENDA CLARITY</div><div class="report-meta-val">${d.agenda_clarity||rnd(10,40)}%</div></div>`;
    chartHtml=`<div class="report-bar-row"><div class="report-bar-label">Email probability</div><div class="report-bar"><div class="report-bar-fill" style="width:${s.score}%;background:#ef4444"></div></div><div class="report-bar-pct">${s.score}%</div></div><div class="report-bar-row"><div class="report-bar-label">Agenda clarity</div><div class="report-bar"><div class="report-bar-fill" style="width:${d.agenda_clarity||20}%;background:#3b82f6"></div></div><div class="report-bar-pct">${d.agenda_clarity||20}%</div></div>`;
    bodyHtml=`<p>${d.analysis||'This meeting has been flagged for extreme email viability.'}</p>`;
  }
  rc.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:10px;"><div><div style="font-family:var(--font-d);font-size:26px;letter-spacing:2px;color:var(--cyan)">${titleText}</div><div style="font-family:var(--font-m);font-size:11px;color:var(--muted);margin-top:4px;">${subtitleText}</div></div><div style="display:flex;gap:8px;flex-wrap:wrap;"><span class="tag tag-cyan">CASE ${caseId}</span><span class="tag tag-red">CONFIDENTIAL</span><span class="tag tag-lime">OVERTHINKOS v1.0</span></div></div><div style="font-family:var(--font-m);font-size:10px;color:var(--muted);margin-bottom:16px;">${now} &nbsp;|&nbsp; Auto-generated by OverthinkOS</div><div class="report-meta">${metaHtml}</div><div style="font-family:var(--font-m);font-size:9px;letter-spacing:3px;color:var(--muted);margin-bottom:8px;text-transform:uppercase;">Analysis Breakdown</div><div class="report-chart">${chartHtml}</div><div class="report-conclusion"><p>${bodyHtml}</p></div><div style="margin-top:16px;"><button class="btn btn-primary" onclick="printReport('${caseId}','${titleText.replace(/'/g,'')}','${subtitleText.replace(/'/g,'')}')">🖨 GENERATE PRINTABLE REPORT</button></div>`;
}
function printReport(caseId,title,subtitle){
  if(!lastSession) return;
  const s=lastSession,now=new Date().toLocaleString();
  let bars='',summary='';
  if(s.type==='decision'){bars=s.agents.map(a=>{const v=rnd(55,99);return`<div class="po-bar-row"><div class="po-bar-label">${a.name}</div><div class="po-bar"><div class="po-bar-inner" style="width:${v}%"></div></div><div class="po-bar-pct">${v}%</div></div>`;}).join('');summary=`Verdict: ${s.verdict||'PENDING'}`;}
  else if(s.type==='devil'){bars=s.angles.map(a=>{const v=rnd(60,99);return`<div class="po-bar-row"><div class="po-bar-label">${a.label}</div><div class="po-bar"><div class="po-bar-inner" style="width:${v}%"></div></div><div class="po-bar-pct">${v}%</div></div>`;}).join('');summary=`Opinion destruction: ${s.score}%`;}
  else if(s.type==='meeting'){bars=`<div class="po-bar-row"><div class="po-bar-label">Email probability</div><div class="po-bar"><div class="po-bar-inner" style="width:${s.score}%"></div></div><div class="po-bar-pct">${s.score}%</div></div>`;summary=s.data?.verdict||'PROBABLY AN EMAIL';}
  document.getElementById('print-body').innerHTML=`<div class="po-header"><div><div class="po-logo">OVERTHINKOS</div><div style="font-size:11px;color:#666;letter-spacing:2px">ENTERPRISE DECISION INTELLIGENCE PLATFORM</div></div><div class="po-confidential">CONFIDENTIAL</div></div><div class="po-title">${title}</div><div class="po-subtitle">${subtitle} &nbsp;|&nbsp; Case: ${caseId} &nbsp;|&nbsp; Generated: ${now}</div><div class="po-metrics"><div class="po-metric"><div class="po-metric-val">${rnd(62,97)}%</div><div class="po-metric-label">Confidence</div></div><div class="po-metric"><div class="po-metric-val">${rnd(40,89)}%</div><div class="po-metric-label">Chaos Index</div></div><div class="po-metric"><div class="po-metric-val">${rnd(3,12)}</div><div class="po-metric-label">Risk Factors</div></div><div class="po-metric"><div class="po-metric-val">${rnd(847,9999)}</div><div class="po-metric-label">Variables Analyzed</div></div></div><div class="po-section-title">Analysis Breakdown</div>${bars}<div class="po-section-title">Executive Summary</div><div class="po-body">${summary}. This report was generated by OverthinkOS v1.0 using advanced multi-agent AI architecture. All metrics are statistically significant (p &lt; 0.05, probably). The conclusions presented herein are final and binding, except when they are not.</div><div class="po-disclaimer">DISCLAIMER: This report was generated by OverthinkOS, a satirical AI-powered decision tool. All analysis, metrics, confidence scores, and conclusions are algorithmically generated and intentionally absurd. Nothing in this report constitutes actual advice, legal counsel, financial guidance, or medical opinion. OverthinkOS, its agents, subsidiaries, and imaginary board members accept no liability for any decisions made based on this report. For actual decisions, please consult a human. Or don't. We're not your boss.</div>`;
  document.getElementById('printOverlay').classList.add('open');
}
function closePrint(){ document.getElementById('printOverlay').classList.remove('open'); }
let chaosOn=false;
function toggleChaos(){ chaosOn=!chaosOn; document.body.classList.toggle('chaos-mode',chaosOn); document.querySelector('.chaos-btn').textContent=chaosOn?'⚠ DISENGAGE CHAOS PROTOCOL':'⚠ CHAOS PROTOCOL — TOGGLE SCREEN INSTABILITY'; }