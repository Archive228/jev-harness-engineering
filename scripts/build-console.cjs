// jev-console.html — воспроизводимая сессия харнесса в стиле TypeSafe (1-bit, розовый).
// Таймлайн собирается из НАСТОЯЩИХ артефактов: events.jsonl (решения policy со счётчиками),
// judge/*.json (вызовы Jev с распределениями), state.json (записи проверок), worker-*.json, result.json.
// Ничего не додумывает: нет поля — нет шага.
const fs = require('fs');
const path = require('path');
const base = path.resolve(__dirname, '..');
const LAB = path.join(base, 'jev-harness-lab');

const RUNS = [
  { dir: 'runs/jev-codex-eval-2026-09-20/backend-title-only', id: 'backend', label: 'LIVE · backend · STOP' },
  { dir: 'runs/jev-codex-eval-2026-09-20/ui-title-only',      id: 'ui',      label: 'LIVE · ui · COMPLETE' },
  { dir: 'runs/jev-codex-eval-2026-09-20/both-title-only',    id: 'both',    label: 'LIVE · both · COMPLETE' },
  { dir: 'runs/example',                                      id: 'demo',    label: 'DEMO · synthetic' },
];

const rJSON = p => { try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch (e) { return null; } };
const rLines = p => { try { return fs.readFileSync(p, 'utf8').trim().split('\n').map(l => { try { return JSON.parse(l); } catch (e) { return null; } }).filter(Boolean); } catch (e) { return []; } };
const sh = h => h && h.length > 12 ? h.slice(0, 6) + '…' + h.slice(-4) : (h || '');

function build(spec) {
  const dir = path.join(LAB, spec.dir);
  if (!fs.existsSync(dir)) return null;
  const result = rJSON(path.join(dir, 'result.json'));
  const state = rJSON(path.join(dir, 'state.json'));
  const policy = rJSON(path.join(dir, 'policy.json')) || {};
  const events = rLines(path.join(dir, 'events.jsonl'));
  const records = (state && state.records) || [];

  const judge = [];
  const jdir = path.join(dir, 'judge');
  if (fs.existsSync(jdir)) {
    for (const f of fs.readdirSync(jdir).filter(x => x.endsWith('.json')).sort()) {
      const d = rJSON(path.join(jdir, f)); if (!d) continue;
      const qs = (d.request && d.request.questions) || {};
      const ans = (d.response && d.response.answers) || {};
      judge.push({
        file: f.replace('.json', ''),
        model: (d.response && d.response.model) || 'jev-1.13.0',
        synthetic: !!d.synthetic,
        usage: (d.response && d.response.usage) || null,
        rows: Object.keys(qs).map(k => ({
          id: k,
          type: (qs[k] && qs[k].type) || (ans[k] && ans[k].type) || '',
          instructions: (qs[k] && qs[k].instructions) || '',
          a: ans[k] || null,
        })),
      });
    }
  }
  const workers = fs.readdirSync(dir).filter(f => /^worker-\d+\.json$/.test(f)).sort()
    .map(f => rJSON(path.join(dir, f))).filter(Boolean);

  const steps = [];
  const push = s => steps.push(s);

  push({
    k: 'boot',
    lines: [
      ['sys', `snapshot ${sh(state && state.snapshot)} · case ${(state && state.case) || '—'}`],
      ['sys', `policy: min_choice_confidence ${policy.min_choice_confidence} · scope_threshold ${policy.scope_threshold} · max_iterations ${policy.max_iterations}`],
      ['sys', `worker: ${(result && result.synthetic_judge_and_worker) ? 'synthetic demo' : 'Codex CLI'}`],
    ],
    meters: { checks: 0, jev: 0, iter: 0, sec: 0 },
  });
  // state.worker_claim хранит ПОСЛЕДНЕЕ утверждение. Если worker отработал,
  // его претензии покажут шаги worker; на старте строку даём только когда он не запускался.
  if (state && state.worker_claim && workers.length === 0) {
    push({ k: 'claim', lines: [['worker', `claim: ${state.worker_claim}`], ['sys', 'stored as an assertion by the author of the change, never as a test result']] });
  }

  let jI = 0, cI = 0, wI = 0;

  function flushJudge(upto) {
    while (jI < upto && jI < judge.length) {
      const j = judge[jI++];
      const a = (j.rows[0] && j.rows[0].a) || {};
      const probs = a.probabilities || null;
      const n = probs ? Object.keys(probs).length : 2;
      const pmax = probs ? Math.max(...Object.values(probs).map(Number)) : Number(a.noul || 0);
      const need = (policy.min_choice_confidence != null && probs && n > 1)
        ? (policy.min_choice_confidence * (n - 1) + 1) / n : null;
      const lines = [['jev', `POST /v1/systemone · ${j.rows.length} question${j.rows.length > 1 ? 's' : ''} · ${j.model}${j.synthetic ? ' · SYNTHETIC' : ''}`]];
      for (const r of j.rows) {
        const aa = r.a || {};
        if (aa.type === 'noul') lines.push(['jevr', `${r.id} = ${Number(aa.noul).toFixed(2)}`]);
        else if (aa.type === 'choice') lines.push(['jevr', `${r.id} = ${aa.choice}    ` + Object.entries(aa.probabilities || {}).sort((x, y) => y[1] - x[1]).map(([k, v]) => `p(${k})=${Number(v).toFixed(2)}`).join('  ')]);
        else if (aa.type === 'score') lines.push(['jevr', `${r.id} = ${Number(aa.score).toFixed(2)}`]);
      }
      if (a.confidence != null && probs && n > 1) {
        lines.push(['calc', `confidence ${Number(a.confidence).toFixed(2)} = (${n}×${pmax.toFixed(2)}−1)/${n - 1}`]);
        if (need != null) lines.push(['calc', `threshold ${policy.min_choice_confidence} needs p_max ≥ ${need.toFixed(2)} · got ${pmax.toFixed(2)} · ${pmax >= need ? 'ABOVE' : 'SHORT by ' + (need - pmax).toFixed(2)}`]);
      }
      if (j.usage) lines.push(['sys', `usage ${j.usage.input_tokens} in / ${j.usage.output_tokens} out`]);
      push({ k: 'jev', lines, jev: { file: j.file, model: j.model, synthetic: j.synthetic, rows: j.rows, need } });
    }
  }
  function flushChecks(upto) {
    while (cI < upto && cI < records.length) {
      const r = records[cI++];
      let detail = '';
      try { const o = JSON.parse(r.stdout); detail = o.detail || (o.observation ? JSON.stringify(o.observation) : ''); } catch (e) { }
      push({
        k: 'exec',
        lines: [
          ['exec', `check_runner.py ${r.check_id}`],
          ['execr', `exit ${r.exit_code} · ${Math.round(r.elapsed_ms)}ms · snapshot ${sh(r.snapshot)}${r.snapshot === r.snapshot_after ? ' · unchanged' : ' · CHANGED'}`],
          ...(detail ? [['execd', detail.slice(0, 170)]] : []),
        ],
      });
    }
  }
  function flushWorkers(upto) {
    while (wI < upto && wI < workers.length) {
      const w = workers[wI++];
      push({ k: 'worker', lines: [['worker', `claim: ${w.claim || '—'}`], ['sys', 'harness reruns acceptance itself; the claim decides nothing']] });
    }
  }

  const REASON = {
    mandatory_acceptance: 'rule 1 · mandatory confirmation missing or stale',
    choose_optional_diagnostic: 'rule 2 · a check failed, ask for one extra fact',
    jev_selected_diagnostic: 'rule 2 · run the diagnostic Jev chose',
    repair_observed_failure: 'rule 2 · hand the worker a reproducible failure',
    acceptance_contract_satisfied: 'rule 3 · every mandatory criterion confirmed',
    no_supported_diagnostic: 'rule 5 · Choice under the confidence threshold',
    no_new_evidence: 'rule 4 · nothing changed',
    budget_exhausted: 'rule 4 · a limit is spent',
  };

  for (const ev of events) {
    const c = ev.context || {};
    flushJudge(c.jev_calls || 0);
    flushChecks(c.checks_used || 0);
    flushWorkers(c.iterations || 0);
    const rep = (c.report && c.report.criteria) || null;
    if (rep) push({ k: 'report', criteria: rep, meters: { checks: c.checks_used || 0, jev: c.jev_calls || 0, iter: c.iterations || 0, sec: c.elapsed_seconds || 0 } });
    const d = ev.decision || {};
    push({
      k: 'policy',
      lines: [['policy', `${String(d.action || '').toUpperCase()}${d.check_id ? ' ' + d.check_id : ''}   ← ${REASON[d.reason] || d.reason || ''}`]],
      policy: { action: d.action, reason: d.reason },
    });
  }
  flushJudge(judge.length); flushChecks(records.length); flushWorkers(workers.length);

  const res = result || {};
  push({
    k: 'end',
    lines: [
      ['end', `${String(res.status || '?').toUpperCase()} · ${res.reason || ''}`],
      ['sys', `checks ${res.checks_executed} · worker iterations ${res.worker_iterations} · jev calls ${res.judge_invocations} · remote requests ${res.remote_jev_requests}`],
      ['sys', `elapsed ${res.elapsed_ms != null ? (res.elapsed_ms / 1000).toFixed(2) + ' s' : '—'}${res.usage ? ` · tokens ${res.usage.input_tokens}/${res.usage.output_tokens}` : ''}`],
    ],
  });

  return { id: spec.id, label: spec.label, policy, steps };
}

const data = RUNS.map(build).filter(Boolean);
if (!data.length) { console.error('нет прогонов'); process.exit(1); }

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&display=swap');
:root{--pink:#F386A1;--ink:#1E1E1E;--paper:#FEFEFE;--chrome:#DEDEDE;--chrome2:#C4C4C4}
*{box-sizing:border-box}
body{margin:0;background:var(--pink);color:var(--ink);font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
font-size:13px;line-height:1.5;background-image:radial-gradient(var(--ink) .5px,transparent .5px);background-size:4px 4px}
.sheet{max-width:1460px;margin:0 auto;padding:22px 26px 60px;position:relative}
.crop{position:absolute;width:14px;height:14px;border:1px solid var(--ink)}
.crop.tl{top:6px;left:8px;border-right:0;border-bottom:0}.crop.tr{top:6px;right:8px;border-left:0;border-bottom:0}
.os{display:inline-block;background:var(--ink);color:var(--paper);padding:3px 10px;font-size:11px;letter-spacing:.14em}
.bar1{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:12px 0 14px;position:relative;z-index:2}
.tab,.ctl{font:inherit;font-size:11px;letter-spacing:.06em;background:var(--paper);color:var(--ink);border:1px solid var(--ink);
padding:5px 11px;cursor:pointer;box-shadow:2px 2px 0 var(--ink)}
.tab.on{background:var(--ink);color:var(--paper)}
.ctl:active{transform:translate(1px,1px);box-shadow:1px 1px 0 var(--ink)}
.sep{width:1px;height:20px;background:var(--ink);opacity:.4}
.scrub{flex:1;min-width:170px;height:11px;background:var(--chrome);border:1px solid var(--ink);position:relative;cursor:pointer}
.scrub i{position:absolute;left:0;top:0;bottom:0;background:var(--ink)}
.scrub b{position:absolute;top:-3px;width:9px;height:15px;background:var(--ink)}
.stepn{font-size:11px;min-width:58px;text-align:right}
.cols{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:20px;align-items:start}
.win{background:var(--paper);border:1px solid var(--ink);box-shadow:3px 3px 0 var(--ink);margin-bottom:20px;position:relative;z-index:1}
.tb{background:var(--ink);color:var(--paper);font-size:11px;letter-spacing:.14em;padding:4px 10px;display:flex;justify-content:space-between;gap:10px}
.body{padding:12px 13px 14px}
#term{height:600px;overflow:auto;padding:12px 13px;font-size:12.5px;line-height:1.62}
.ln{white-space:pre-wrap;word-break:break-word;display:flex;gap:8px}
.ln .pre{flex:0 0 56px;font-weight:700;font-size:10.5px;letter-spacing:.04em;padding-top:2px;text-align:right}
.ln.sys,.ln.sys .pre{color:#6d6d6d}
.ln.policy{background:var(--chrome);margin:5px -13px;padding:3px 13px;font-weight:700}
.ln.jevr,.ln.execr,.ln.worker{font-weight:700}
.ln.calc{color:#333;font-size:11.5px}
.ln.execd{color:#555;font-size:11.5px}
.ln.end{background:var(--ink);color:var(--paper);margin:8px -13px 0;padding:6px 13px;font-weight:700;font-size:14px}
.ln.end .pre{color:var(--paper)}
.crow{display:grid;grid-template-columns:32px 54px 1fr;gap:7px;padding:6px 0;border-bottom:1px dotted var(--chrome2);font-size:11.5px;align-items:start}
.crow:last-child{border-bottom:0}
.cid{font-weight:700}
.chip{display:inline-block;text-align:center;border:1px solid var(--ink);font-size:9.5px;padding:1px 3px;letter-spacing:.05em}
.chip.passed{background:var(--paper)}.chip.failed{background:var(--ink);color:var(--paper)}.chip.unverified{background:var(--chrome)}
.muted{color:#6d6d6d}
.qh{font-weight:700;font-size:12px;margin-bottom:2px}
.qi{font-size:11px;color:#444;margin-bottom:9px}
.big{display:inline-block;border:1px solid var(--ink);padding:3px 9px;font-size:15px;font-weight:700;margin-bottom:9px}
.bar{display:grid;grid-template-columns:98px 1fr 36px;gap:7px;align-items:center;margin:5px 0}
.bl{font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.bl.top{font-weight:700}
.track{position:relative;height:11px;background:var(--chrome);border:1px solid var(--ink)}
.track i{position:absolute;left:0;top:0;bottom:0;background:var(--ink);transition:width .5s cubic-bezier(.2,.8,.2,1)}
.thr{position:absolute;top:-5px;bottom:-5px;width:2px;background:var(--ink)}
.bv{font-size:11px;text-align:right}
.calcbox{margin-top:10px;border-top:1px dotted var(--chrome2);padding-top:7px;font-size:11.5px;line-height:1.7}
.verdict{display:inline-block;border:1px solid var(--ink);padding:2px 7px;font-size:11px;font-weight:700;margin-top:7px}
.verdict.short{background:var(--ink);color:var(--paper)}
.rule{padding:5px 8px;border-bottom:1px dotted var(--chrome2);opacity:.4;font-size:11.5px}
.rule:last-child{border-bottom:0}
.rule.on{opacity:1;background:var(--chrome);font-weight:700}
.mt{display:grid;grid-template-columns:repeat(2,1fr);gap:0 14px}
.m{display:flex;justify-content:space-between;border-bottom:1px dotted var(--chrome2);padding:4px 0;font-size:11.5px}
.m b{font-variant-numeric:tabular-nums}
.sq{position:absolute;width:9px;height:9px;background:var(--ink);z-index:0;pointer-events:none}
.legend{margin-top:18px;font-size:11px;color:#3a3a3a;max-width:920px;position:relative;z-index:1}
@media(max-width:1060px){.cols{grid-template-columns:1fr}#term{height:420px}}
@media print{.bar1{display:none}#term{height:auto}}
`;

const JS = String.raw`
var DATA = __DATA__;
var cur=null, idx=0, timer=null, speed=1, playing=false;
function $(s){return document.querySelector(s)}
var RULES=[
 ['rule 1','mandatory confirmation missing or stale → run that check'],
 ['rule 2','a check failed → get one extra fact, hand the worker a reproducible failure'],
 ['rule 3','every mandatory criterion confirmed → complete under the contract'],
 ['rule 4','nothing changed, no suitable diagnostic, or a limit spent → stop'],
 ['rule 5','Choice unavailable, invalid or under the threshold → stop']];
var RMAP={mandatory_acceptance:'rule 1',choose_optional_diagnostic:'rule 2',jev_selected_diagnostic:'rule 2',
 repair_observed_failure:'rule 2',acceptance_contract_satisfied:'rule 3',no_new_evidence:'rule 4',
 budget_exhausted:'rule 4',no_supported_diagnostic:'rule 5'};
var PRE={sys:'sys',policy:'policy',jev:'jev ▸',jevr:'jev ◂',calc:'',exec:'exec ▸',execr:'exec ◂',execd:'',worker:'worker',end:'■'};
function esc(t){return String(t==null?'':t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function meters(m){$('#meters').innerHTML=
 '<div class="m"><span>checks</span><b>'+m.checks+'</b></div>'+
 '<div class="m"><span>jev calls</span><b>'+m.jev+'</b></div>'+
 '<div class="m"><span>worker iter</span><b>'+m.iter+'</b></div>'+
 '<div class="m"><span>elapsed</span><b>'+Number(m.sec||0).toFixed(2)+'s</b></div>';}
function board(cs){$('#crit').innerHTML=cs.map(function(c){
 var st=c.status==='passed'?'PASS':c.status==='failed'?'FAIL':'UNVER';
 return '<div class="crow"><span class="cid">'+esc(c.criterion)+'</span><span class="chip '+esc(c.status)+'">'+st+'</span><span>'+
  esc(c.requirement||'')+(c.scope_noul!=null?' <span class="muted">· noul '+Number(c.scope_noul).toFixed(2)+'</span>':'')+'</span></div>';}).join('');}
function mind(j){
 var r=j.rows[0]||{}, a=r.a||{}, probs=a.probabilities;
 if(a.type==='noul') probs={yes:Number(a.noul), no:1-Number(a.noul)};
 var keys=Object.keys(probs||{}).sort(function(x,y){return probs[y]-probs[x]});
 var head=a.type==='choice'?'choice '+esc(a.choice):a.type==='score'?'score '+Number(a.score).toFixed(2):'noul '+Number(a.noul).toFixed(2);
 var h='<div class="qh">'+esc(r.id)+' <span class="muted">'+esc(r.type)+(j.synthetic?' · synthetic':'')+'</span></div>'+
       '<div class="qi">'+esc(r.instructions)+'</div><div class="big">'+head+'</div>';
 h+=keys.map(function(k,i){var p=Number(probs[k]);
  var thr=(i===0&&j.need!=null)?'<span class="thr" style="left:'+(j.need*100).toFixed(1)+'%"></span>':'';
  return '<div class="bar"><span class="bl'+(i===0?' top':'')+'">'+esc(k)+'</span><span class="track"><i data-w="'+(p*100).toFixed(1)+'"></i>'+thr+'</span><span class="bv">'+p.toFixed(2)+'</span></div>';}).join('');
 if(a.confidence!=null&&keys.length>1){var n=keys.length,pmax=Number(probs[keys[0]]);
  h+='<div class="calcbox">confidence <b>'+Number(a.confidence).toFixed(2)+'</b> = ('+n+'×'+pmax.toFixed(2)+'−1)/'+(n-1)+
    (j.need!=null?'<br>threshold needs p_max ≥ <b>'+j.need.toFixed(2)+'</b>, got <b>'+pmax.toFixed(2)+'</b>':'')+'</div>';
  if(j.need!=null){var ok=pmax>=j.need;
   h+='<div class="verdict'+(ok?'':' short')+'">'+(ok?'ABOVE THRESHOLD':'SHORT BY '+(j.need-pmax).toFixed(2))+'</div>';}}
 $('#mind').innerHTML=h;
 requestAnimationFrame(function(){Array.prototype.forEach.call($('#mind').querySelectorAll('.track i'),function(el){el.style.width=el.dataset.w+'%';});});}
function emit(s){
 var t=$('#term');
 (s.lines||[]).forEach(function(l){var d=document.createElement('div');d.className='ln '+l[0];
  d.innerHTML='<span class="pre">'+(PRE[l[0]]||'')+'</span><span>'+esc(l[1])+'</span>';t.appendChild(d);});
 if(s.criteria) board(s.criteria);
 if(s.meters) meters(s.meters);
 if(s.jev) mind(s.jev);
 if(s.policy){var r=RMAP[s.policy.reason];
  Array.prototype.forEach.call($('#rules').querySelectorAll('.rule'),function(el){el.classList.toggle('on',el.dataset.r===r);});}
 t.scrollTop=t.scrollHeight;}
function scrub(){var n=cur?cur.steps.length:0,p=n?idx/n:0;
 $('#sc').firstElementChild.style.width=(p*100)+'%';
 $('#sc').lastElementChild.style.left='calc('+(p*100)+'% - 4px)';
 $('#stepn').textContent=idx+' / '+n;}
function step(){if(!cur||idx>=cur.steps.length){pause();return false;}emit(cur.steps[idx++]);scrub();return true;}
function play(){if(playing)return;playing=true;$('#play').textContent='⏸ pause';
 timer=setInterval(function(){if(!step())pause();},640/speed);}
function pause(){playing=false;if(timer)clearInterval(timer);timer=null;var b=$('#play');if(b)b.textContent='▶ play';}
function load(id){cur=DATA.filter(function(d){return d.id===id})[0];idx=0;pause();
 $('#term').innerHTML='';$('#crit').innerHTML='<div class="muted">—</div>';
 $('#mind').innerHTML='<div class="qi">Jev ещё не вызывался. Нажмите play.</div>';
 $('#rules').innerHTML=RULES.map(function(r){return '<div class="rule" data-r="'+r[0]+'"><b>'+r[0]+'</b> · '+r[1]+'</div>';}).join('');
 meters({checks:0,jev:0,iter:0,sec:0});$('#runlab').textContent=cur.label;scrub();}
function all(){pause();while(step()){}}
document.addEventListener('DOMContentLoaded',function(){
 load(DATA[0].id);
 Array.prototype.forEach.call(document.querySelectorAll('.tab'),function(t){t.onclick=function(){
  Array.prototype.forEach.call(document.querySelectorAll('.tab'),function(x){x.classList.remove('on');});
  t.classList.add('on');load(t.dataset.go);};});
 $('#play').onclick=function(){playing?pause():play();};
 $('#stepb').onclick=function(){pause();step();};
 $('#allb').onclick=all;
 $('#resetb').onclick=function(){load(cur.id);};
 $('#speedb').onclick=function(){speed=speed===1?2:speed===2?4:1;this.textContent='×'+speed;if(playing){pause();play();}};
 $('#sc').onclick=function(e){var r=this.getBoundingClientRect();var target=Math.round((e.clientX-r.left)/r.width*cur.steps.length);
  pause();load(cur.id);for(var i=0;i<target;i++)step();};});
`;

const tabs = data.map((r, i) => `<button class="tab${i === 0 ? ' on' : ''}" data-go="${r.id}">${r.label}</button>`).join('');
const squares = [[6, 500], [20, 640], [38, 575], [1420, 450], [1406, 545]]
  .map(([l, t]) => `<div class="sq" style="left:${l}px;top:${t}px"></div>`).join('');

const html = `<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JEV HARNESS · SESSION CONSOLE</title><style>${CSS}</style></head><body>
<div class="sheet">
 <div class="crop tl"></div><div class="crop tr"></div>
 <span class="os">TS.HARNESS.OS1 · SESSION REPLAY</span>
 <div class="bar1">${tabs}</div>
 <div class="bar1">
  <button class="ctl" id="play">▶ play</button>
  <button class="ctl" id="stepb">⏭ step</button>
  <button class="ctl" id="allb">⏩ all</button>
  <button class="ctl" id="resetb">↺ reset</button>
  <button class="ctl" id="speedb">×1</button>
  <div class="sep"></div>
  <div class="scrub" id="sc"><i></i><b></b></div>
  <span class="stepn" id="stepn">0 / 0</span>
 </div>
 ${squares}
 <div class="cols">
  <div><div class="win"><div class="tb"><span>SESSION</span><span id="runlab"></span></div><div id="term"></div></div></div>
  <div>
   <div class="win"><div class="tb"><span>JEV · WHAT IT IS DECIDING</span></div><div class="body" id="mind"></div></div>
   <div class="win"><div class="tb"><span>REQUIREMENTS</span></div><div class="body" id="crit"></div></div>
   <div class="win"><div class="tb"><span>POLICY · WHICH RULE FIRED</span></div><div class="body" id="rules"></div></div>
   <div class="win"><div class="tb"><span>METERS</span></div><div class="body"><div class="mt" id="meters"></div></div></div>
  </div>
 </div>
 <div class="legend">Сессия воспроизводится из сохранённых артефактов: <code>events.jsonl</code> хранит решение policy и счётчики на каждом шаге, <code>judge/*.json</code> — вызовы Jev с распределениями, <code>state.json</code> — записи проверок с exit code и снимками, <code>result.json</code> — итог. Вертикальная метка на верхней полоске показывает, какой p_max требует порог policy: при трёх вариантах и <code>min_choice_confidence 0.6</code> это 0.73.</div>
</div>
<script>${JS.replace('__DATA__', JSON.stringify(data))}</script></body></html>`;

fs.writeFileSync(path.join(base, 'jev-console.html'), html);
console.log(JSON.stringify({ file: 'jev-console.html', bytes: Buffer.byteLength(html), runs: data.map(d => ({ id: d.id, steps: d.steps.length })) }));
