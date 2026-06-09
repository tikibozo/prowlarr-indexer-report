/* Live front-end: poll /api/data, render charts + table, auto-refresh. */
"use strict";

const C = {usenet:'#4ea1ff', torrent:'#ffb454', remove:'#ff5c6c', watch:'#ffcf5c',
           mut:'#8a96ad', line:'#2a3450', ink:'#e6ebf5'};
const APP_COLORS = ['#4ea1ff','#ffb454','#7ce38b','#c08cff','#ff8fab','#5cd0d0','#d0d0d0'];
Chart.defaults.color = C.mut;
Chart.defaults.borderColor = C.line;
Chart.defaults.font.family = "-apple-system,Segoe UI,Roboto,sans-serif";

// How often the browser re-polls the server's cache. The server itself
// refreshes from Prowlarr on its own (longer) interval; polling more often
// just means we pick up a new server snapshot promptly.
const POLL_MS = 60 * 1000;

const charts = {};           // id -> Chart instance (destroyed/recreated each render)
let sortKey = 'grabsAll', sortDir = -1, lastRows = null;
const proColor = p => p === 'usenet' ? C.usenet : C.torrent;

function fmtAgo(iso) {
  if (!iso) return 'never';
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return Math.round(secs) + 's ago';
  if (secs < 3600) return Math.round(secs / 60) + 'm ago';
  return Math.round(secs / 3600) + 'h ago';
}

function setStatus(data, err) {
  const dot = document.getElementById('dot');
  const txt = document.getElementById('statusText');
  const banner = document.getElementById('banner');
  if (err) {
    dot.className = 'dot err';
    txt.textContent = 'fetch error';
    banner.style.display = 'block';
    banner.textContent = 'Could not reach the report service: ' + err;
    return;
  }
  // History coverage: the full span Prowlarr retains (bounded by its
  // historycleanupdays). Shows we're displaying everything available.
  const h = data.history || {};
  const cov = document.getElementById('coverage');
  if (h.start) {
    const months = h.spanDays != null ? ' (' + (h.spanDays / 30.44).toFixed(1) + ' mo)' : '';
    cov.textContent = ' · full history since ' + h.start + months;
  } else {
    cov.textContent = '';
  }
  const warn = h.truncated ? 'History was truncated at the page cap — some older grabs are not shown. ' : '';
  banner.style.display = (data.lastError || h.truncated) ? 'block' : 'none';
  if (data.lastError) banner.textContent = warn + 'Last Prowlarr refresh failed: ' + data.lastError;
  else if (h.truncated) banner.textContent = warn;
  dot.className = 'dot' + (data.lastError || h.truncated ? ' stale' : '');
  txt.textContent = 'data ' + fmtAgo(data.generatedAt) +
    ' · window ' + data.windowDays + 'd' +
    (data.refreshIntervalMinutes ? ' · server refresh ' + data.refreshIntervalMinutes + 'm' : '');
}

function mkChart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), cfg);
}

function renderCards(s) {
  const cards = [
    ['Indexers', s.indexers], ['Enabled', s.enabled],
    ['Total grabs', (s.totalGrabs || 0).toLocaleString()],
    ['Remove candidates', s.removeCandidates], ['Watch (high cost)', s.watchCandidates],
  ];
  document.getElementById('cards').innerHTML = cards.map(
    ([l, n]) => `<div class="card"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('');
}

function renderCharts(d) {
  const ROWS = d.indexers;
  mkChart('grabsBar', {type:'bar', data:{
    labels: ROWS.map(r=>r.name),
    datasets:[{label:'Grabs (all-time)', data:ROWS.map(r=>r.grabsAll),
      backgroundColor:ROWS.map(r=>proColor(r.protocol))}]},
    options:{indexAxis:'y', animation:false, plugins:{legend:{display:false}},
      scales:{x:{grid:{color:C.line}}, y:{grid:{display:false},ticks:{autoSkip:false,font:{size:11}}}}}});

  const topRows = ROWS.slice(0, 15);
  mkChart('trend', {type:'bar', data:{
    labels: topRows.map(r=>r.name),
    datasets:[
      {label:'30d', data:topRows.map(r=>r.grabs30), backgroundColor:'#7ce38b'},
      {label:d.windowDays+'d', data:topRows.map(r=>r.grabsWin), backgroundColor:'#4ea1ff'},
      {label:'all-time', data:topRows.map(r=>r.grabsAll), backgroundColor:C.line},
    ]}, options:{animation:false, plugins:{legend:{position:'bottom'}},
      scales:{x:{ticks:{font:{size:10},maxRotation:60,minRotation:60}}, y:{type:'logarithmic'}}}});

  mkChart('scatter', {type:'scatter', data:{datasets:[{
    label:'indexers',
    data:ROWS.map(r=>({x:Math.max(r.queries,1), y:r.grabsAll, r:4+Math.min(r.failRate,10), n:r.name})),
    backgroundColor:ROWS.map(r=>r.flag==='remove'?C.remove:r.flag==='watch'?C.watch:proColor(r.protocol)),
  }]}, options:{animation:false, plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>`${c.raw.n}: ${c.raw.y} grabs / ${c.raw.x.toLocaleString()} queries`}}},
    scales:{x:{type:'logarithmic',title:{display:true,text:'queries (log)'}},
            y:{title:{display:true,text:'grabs'}}}}});

  const withGrabs = ROWS.filter(r=>r.grabsAll>0);
  mkChart('perApp', {type:'bar', data:{
    labels: withGrabs.map(r=>r.name),
    datasets: d.apps.map((app,i)=>({label:app,
      data:withGrabs.map(r=>r.perApp[app]||0),
      backgroundColor:APP_COLORS[i%APP_COLORS.length]}))},
    options:{animation:false, plugins:{legend:{position:'bottom'}},
      scales:{x:{stacked:true,ticks:{font:{size:10},maxRotation:60,minRotation:60}}, y:{stacked:true}}}});

  mkChart('timeline', {type:'line', data:{
    labels: d.timeline.map(t=>t[0]),
    datasets:[{label:'grabs/month', data:d.timeline.map(t=>t[1]), borderColor:C.usenet,
      backgroundColor:'rgba(78,161,255,.15)', fill:true, tension:.25, pointRadius:2}]},
    options:{animation:false, plugins:{legend:{display:false}}, scales:{x:{ticks:{font:{size:10}}}}}});
}

const COLS = [
  ['name','Indexer'],['protocol','Proto'],['priority','Prio'],
  ['grabsAll','Grabs'],['grabsWin','Win'],['grabs30','30d'],
  ['queries','Queries'],['grabRate','Grab %'],['failRate','Fail %'],
  ['respTime','Resp ms'],['lastGrab','Last grab'],['flag','Flag'],['reason','Reason'],
];

function renderTable() {
  if (!lastRows) return;
  const r = [...lastRows].sort((a,b)=>{
    let x=a[sortKey], y=b[sortKey];
    if(typeof x==='string'){return sortDir*x.localeCompare(y);}
    return sortDir*((x||0)-(y||0));
  });
  const winLabel = COLS.find(c=>c[0]==='grabsWin');
  const head = '<thead><tr>'+COLS.map(([k,l])=>
    `<th data-k="${k}">${l}${sortKey===k?(sortDir<0?' ▾':' ▴'):''}</th>`).join('')+'</tr></thead>';
  const body = '<tbody>'+r.map(row=>{
    const cls = row.flag==='remove'?'remove':row.flag==='watch'?'watch':!row.enabled?'disabled':'';
    const cell = k => {
      if(k==='protocol') return `<span class="pill ${row.protocol}">${row.protocol}</span>`;
      if(k==='flag') return row.flag?`<span class="pill ${row.flag}">${row.flag}</span>`:'';
      if(k==='reason') return `<span class="reason">${row.reason||''}</span>`;
      if(k==='grabRate'||k==='failRate') return (row[k]||0).toFixed(2);
      if(k==='name') return row.enabled?esc(row.name):esc(row.name)+' <span class="reason">(off)</span>';
      const v=row[k]; return (typeof v==='number')?v.toLocaleString():esc(v||'');
    };
    return `<tr class="${cls}">`+COLS.map(([k])=>`<td>${cell(k)}</td>`).join('')+'</tr>';
  }).join('')+'</tbody>';
  const tbl = document.getElementById('tbl');
  tbl.innerHTML = head+body;
  tbl.querySelectorAll('th').forEach(th=>th.onclick=()=>{
    const k=th.dataset.k;
    if(k===sortKey){sortDir*=-1;}else{sortKey=k;sortDir=(k==='name'||k==='protocol'||k==='flag')?1:-1;}
    renderTable();
  });
}

function esc(s){return String(s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

function render(d) {
  document.getElementById('loading').style.display = 'none';
  document.getElementById('report').style.display = 'block';
  renderCards(d.summary);
  renderCharts(d);
  lastRows = d.indexers;
  renderTable();
}

async function poll() {
  try {
    const resp = await fetch('/api/data', {cache:'no-store'});
    if (resp.status === 503) {
      const j = await resp.json();
      document.getElementById('statusText').textContent = 'service starting…';
      if (j.error) { const b=document.getElementById('banner'); b.style.display='block'; b.textContent='Waiting on first Prowlarr fetch: '+j.error; }
      return;
    }
    const data = await resp.json();
    setStatus(data, null);
    render(data);
  } catch (e) {
    setStatus(null, e.message || String(e));
  }
}

document.getElementById('refreshBtn').onclick = async (ev) => {
  ev.target.disabled = true;
  ev.target.textContent = 'Refreshing…';
  try { await fetch('/api/refresh', {method:'POST'}); await poll(); }
  finally { ev.target.disabled = false; ev.target.textContent = 'Refresh now'; }
};

poll();
setInterval(poll, POLL_MS);
