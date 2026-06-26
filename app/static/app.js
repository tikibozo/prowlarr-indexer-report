/* Live front-end: poll /api/data, render verdict + table + charts, auto-refresh. */
"use strict";

/* ---- Tokens: read from CSS so there's a single source of truth (no drift). ---- */
const _cs = getComputedStyle(document.documentElement);
const tok = n => _cs.getPropertyValue('--' + n).trim();
const C = {
  usenet: tok('usenet'), torrent: tok('torrent'),
  remove: tok('remove'), watch: tok('watch'), manual: tok('manual'), ok: tok('ok'),
  mut: tok('mut'), line: tok('line'), ink: tok('ink'), bg: tok('bg'),
};
const APP_COLORS = [1, 2, 3, 4, 5, 6, 7].map(i => tok('app-' + i));

Chart.defaults.color = C.mut;
Chart.defaults.borderColor = C.line;
Chart.defaults.font.family = "-apple-system,Segoe UI,Roboto,sans-serif";

// How often the browser re-polls the server's cache. The server itself
// refreshes from Prowlarr on its own (longer) interval; polling more often
// just means we pick up a new server snapshot promptly.
const POLL_MS = 60 * 1000;

const charts = {};           // id -> Chart instance (destroyed/recreated on real change)
let sortKey = 'grabsAll', sortDir = -1, lastRows = null;
let tableFilter = 'all';     // all | remove | watch | manual | disabled
let lastGeneratedAt = null;  // skip re-rendering charts/table when the snapshot is unchanged
let prowlarrUrl = '';        // browser-facing Prowlarr URL (opt-in); '' = no deep-links
const proColor = p => p === 'usenet' ? C.usenet : C.torrent;
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ---- Grayscale-safe fills: texture distinguishes series when hue can't. ---- */
function pattern(color, type) {
  if (type === 'solid') return color;
  const s = 8, c = document.createElement('canvas');
  c.width = c.height = s;
  const x = c.getContext('2d');
  x.fillStyle = color; x.fillRect(0, 0, s, s);
  x.strokeStyle = 'rgba(10,14,25,.55)'; x.fillStyle = 'rgba(10,14,25,.55)'; x.lineWidth = 1.5;
  if (type === 'hatch') {
    x.beginPath();
    x.moveTo(0, s); x.lineTo(s, 0);
    x.moveTo(-2, 2); x.lineTo(2, -2);
    x.moveTo(s - 2, s + 2); x.lineTo(s + 2, s - 2);
    x.stroke();
  } else if (type === 'dot') {
    x.beginPath(); x.arc(s / 2, s / 2, 1.7, 0, 7); x.fill();
  } else if (type === 'cross') {
    x.beginPath();
    x.moveTo(0, s); x.lineTo(s, 0);
    x.moveTo(0, 0); x.lineTo(s, s);
    x.stroke();
  }
  return x.createPattern(c, 'repeat');
}
const SERIES_TEX = ['solid', 'hatch', 'dot', 'cross'];

function fmtAgo(iso) {
  if (!iso) return 'never';
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return Math.round(secs) + 's ago';
  if (secs < 3600) return Math.round(secs / 60) + 'm ago';
  return Math.round(secs / 3600) + 'h ago';
}

/* ---- Status / freshness ---- */
let lastBannerText = '', lastA11yState = '';
function setBanner(text) {
  const banner = document.getElementById('banner');
  if (text === lastBannerText) return;          // avoid re-announcing role=alert each poll
  lastBannerText = text;
  banner.style.display = text ? 'block' : 'none';
  banner.textContent = text || '';
}
function announce(state) {
  if (state === lastA11yState) return;          // only announce real transitions
  lastA11yState = state;
  document.getElementById('a11yStatus').textContent = state;
}

function setStatus(data, err) {
  const dot = document.getElementById('dot');
  const txt = document.getElementById('statusText');
  if (err) {
    dot.className = 'dot err';
    txt.textContent = 'fetch error';
    setBanner('Could not reach the report service: ' + err);
    announce('Connection lost: ' + err);
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
  let banner = '';
  if (data.lastError) banner = warn + 'Last Prowlarr refresh failed: ' + data.lastError;
  else if (h.truncated) banner = warn;
  setBanner(banner);
  const stale = data.lastError || h.truncated;
  dot.className = 'dot' + (stale ? ' stale' : '');
  announce(stale ? 'Data may be stale' : 'Live, data current');
  txt.textContent = 'data ' + fmtAgo(data.generatedAt) +
    ' · window ' + data.windowDays + 'd' +
    (data.refreshIntervalMinutes ? ' · server refresh ' + data.refreshIntervalMinutes + 'm' : '');
}

function mkChart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), cfg);
}

/* ---- Cards: inventory (quiet) + verdict (colored, clickable). ---- */
function renderCards(s) {
  const inv = [
    ['Indexers', s.indexers], ['Enabled', s.enabled],
    ['Total grabs', (s.totalGrabs || 0).toLocaleString()],
  ];
  const verdict = [
    ['remove', 'Remove candidates', s.removeCandidates, C.remove],
    ['watch', 'Watch (high cost)', s.watchCandidates, C.watch],
    ['manual', 'Manual (interactive-only)', s.manual ?? 0, C.manual],
  ];
  const invHtml = inv.map(([l, n]) =>
    `<div class="card"><div class="n">${n}</div><div class="l">${l}</div></div>`).join('');
  const verdictHtml = verdict.map(([f, l, n, c]) => {
    const active = tableFilter === f ? ' active' : '';
    const dead = n > 0 ? '' : ' aria-disabled="true"';
    const attrs = n > 0 ? `tabindex="0" role="button" data-filter="${f}"` : '';
    return `<div class="card verdict-card${active}" style="--c:${c}" ${attrs}${dead}>` +
      `<div class="n">${n}</div><div class="l">${l}</div></div>`;
  }).join('');
  document.getElementById('cards').innerHTML = invHtml + '<div class="card-sep"></div>' + verdictHtml;
}

/* ---- Verdict: the kill-list, the lede of the page. ---- */
function renderVerdict(rows) {
  const removes = rows.filter(r => r.flag === 'remove');
  const watches = rows.filter(r => r.flag === 'watch');
  const vsub = document.getElementById('vsub');
  const copyBtn = document.getElementById('copyDisable');
  copyBtn.disabled = removes.length === 0;

  if (!removes.length && !watches.length) {
    vsub.textContent = '';
    document.getElementById('verdictBody').innerHTML =
      `<div class="empty"><b>Nothing to prune.</b> Every enabled auto-search indexer is earning its keep — no removals or high-cost warnings in this window.</div>`;
    return;
  }
  vsub.textContent = removes.length
    ? `— ${removes.length} safe to disable` + (watches.length ? `, ${watches.length} to watch` : '')
    : `— ${watches.length} to watch, nothing to remove`;

  const item = r => {
    const last = r.lastGrab ? `last ${r.lastGrab}` : 'never grabbed';
    // Prowlarr edits indexers in a modal (no per-indexer route), so the link
    // opens the indexer list; the tooltip is honest about that.
    const name = prowlarrUrl
      ? `<a class="kname" href="${esc(prowlarrUrl)}" target="_blank" rel="noopener noreferrer" title="Open Prowlarr's indexer list">${esc(r.name)}</a>`
      : `<span class="kname">${esc(r.name)}</span>`;
    return `<li class="kill ${r.flag}">` + name +
      `<span class="kmeta">${(r.grabsAll || 0).toLocaleString()} grabs · ${(r.queries || 0).toLocaleString()} queries · ${last}</span>` +
      `<span class="kreason">${esc(r.reason || '')}</span></li>`;
  };
  const col = (title, color, list, none) => {
    const body = list.length
      ? `<ul class="killlist">${list.map(item).join('')}</ul>`
      : `<div class="empty">${none}</div>`;
    return `<div class="vcol"><div class="vcol-head">` +
      `<span class="pill ${title}">${title}</span> ${list.length} ${list.length === 1 ? 'indexer' : 'indexers'}` +
      `</div>${body}</div>`;
  };
  document.getElementById('verdictBody').innerHTML =
    `<div class="vlists">` +
    col('remove', C.remove, removes, 'No removal candidates.') +
    col('watch', C.watch, watches, 'No high-cost indexers.') +
    `</div>`;
}

function renderCharts(d) {
  const ROWS = d.indexers;

  mkChart('grabsBar', { type: 'bar', data: {
    labels: ROWS.map(r => r.name),
    datasets: [{ label: 'Grabs (all-time)', data: ROWS.map(r => r.grabsAll),
      backgroundColor: ROWS.map(r => r.protocol === 'usenet'
        ? pattern(C.usenet, 'solid') : pattern(C.torrent, 'hatch')) }] },
    options: { indexAxis: 'y', animation: false, plugins: { legend: { display: false } },
      scales: { x: { grid: { color: C.line } },
        y: { grid: { display: false }, ticks: { autoSkip: false, font: { size: 11 } } } } } });

  const topRows = ROWS.slice(0, 15);
  mkChart('trend', { type: 'bar', data: {
    labels: topRows.map(r => r.name),
    datasets: [
      { label: '30d', data: topRows.map(r => r.grabs30), backgroundColor: pattern(C.ok, 'solid') },
      { label: d.windowDays + 'd', data: topRows.map(r => r.grabsWin), backgroundColor: pattern(C.usenet, 'hatch') },
      { label: 'all-time', data: topRows.map(r => r.grabsAll), backgroundColor: pattern(C.mut, 'dot') },
    ] }, options: { animation: false, plugins: { legend: { position: 'bottom' } },
      scales: { x: { ticks: { font: { size: 10 }, maxRotation: 60, minRotation: 60 } }, y: { type: 'logarithmic' } } } });

  // Flag conveyed by point SHAPE as well as color, so it survives grayscale.
  const ptStyle = f => f === 'remove' ? 'triangle' : f === 'watch' ? 'rect' : 'circle';
  mkChart('scatter', { type: 'scatter', data: { datasets: [{
    label: 'indexers',
    data: ROWS.map(r => ({ x: Math.max(r.queries, 1), y: r.grabsAll, r: 4 + Math.min(r.failRate, 10), n: r.name })),
    backgroundColor: ROWS.map(r => r.flag === 'remove' ? C.remove : r.flag === 'watch' ? C.watch : proColor(r.protocol)),
    pointStyle: ROWS.map(r => ptStyle(r.flag)),
  }] }, options: { animation: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: c => `${c.raw.n}: ${c.raw.y} grabs / ${c.raw.x.toLocaleString()} queries` } } },
    scales: { x: { type: 'logarithmic', title: { display: true, text: 'queries (log)' } },
      y: { title: { display: true, text: 'grabs' } } } } });

  const withGrabs = ROWS.filter(r => r.grabsAll > 0);
  mkChart('perApp', { type: 'bar', data: {
    labels: withGrabs.map(r => r.name),
    datasets: d.apps.map((app, i) => ({ label: app,
      data: withGrabs.map(r => r.perApp[app] || 0),
      backgroundColor: pattern(APP_COLORS[i % APP_COLORS.length], SERIES_TEX[i % SERIES_TEX.length]) })) },
    options: { animation: false, plugins: { legend: { position: 'bottom' } },
      scales: { x: { stacked: true, ticks: { font: { size: 10 }, maxRotation: 60, minRotation: 60 } }, y: { stacked: true } } } });

  mkChart('timeline', { type: 'line', data: {
    labels: d.timeline.map(t => t[0]),
    datasets: [{ label: 'grabs/month', data: d.timeline.map(t => t[1]), borderColor: C.usenet,
      backgroundColor: 'rgba(78,161,255,.15)', fill: true, tension: .25, pointRadius: 2 }] },
    options: { animation: false, plugins: { legend: { display: false } }, scales: { x: { ticks: { font: { size: 10 } } } } } });
}

const COLS = [
  ['name', 'Indexer'], ['protocol', 'Proto'], ['priority', 'Prio'],
  ['grabsAll', 'Grabs'], ['grabsWin', 'Win'], ['grabs30', '30d'],
  ['queries', 'Queries'], ['grabRate', 'Grab %'], ['failRate', 'Fail %'],
  ['respTime', 'Resp ms'], ['lastGrab', 'Last grab'], ['flag', 'Flag'], ['reason', 'Reason'],
];
// Tooltips so the compact headers don't rely on the reader already knowing them.
const COL_TITLES = {
  protocol: 'Protocol — usenet or torrent', priority: 'Prowlarr indexer priority (lower = preferred)',
  grabsAll: 'Total grabs, all-time', grabsWin: `Grabs within the report window`,
  grabs30: 'Grabs in the last 30 days', queries: 'Search queries sent to this indexer',
  grabRate: 'Grabs ÷ queries, as a percentage', failRate: 'Failed queries ÷ queries, as a percentage',
  respTime: 'Average query response time, milliseconds', lastGrab: 'Date of the most recent grab',
  flag: 'Verdict: remove / watch / manual', reason: 'Why this indexer got its verdict',
};

const FILTERS = [
  ['all', 'All', r => true],
  ['remove', 'Remove', r => r.flag === 'remove'],
  ['watch', 'Watch', r => r.flag === 'watch'],
  ['manual', 'Manual', r => r.flag === 'manual'],
  ['disabled', 'Disabled', r => !r.enabled],
];
const filterFn = key => (FILTERS.find(f => f[0] === key) || FILTERS[0])[2];

function renderChips() {
  if (!lastRows) return;
  document.getElementById('filters').innerHTML = FILTERS.map(([key, label, fn]) => {
    const n = lastRows.filter(fn).length;
    const pressed = tableFilter === key;
    return `<button class="chip" aria-pressed="${pressed}" data-filter="${key}">` +
      `${label} <span class="cn">${n}</span></button>`;
  }).join('');
}

function renderTable() {
  if (!lastRows) return;
  const rows = lastRows.filter(filterFn(tableFilter));
  const r = [...rows].sort((a, b) => {
    let x = a[sortKey], y = b[sortKey];
    if (typeof x === 'string') { return sortDir * x.localeCompare(y); }
    return sortDir * ((x || 0) - (y || 0));
  });
  const head = '<thead><tr>' + COLS.map(([k, l]) => {
    const sorted = sortKey === k;
    const ariaSort = sorted ? (sortDir < 0 ? 'descending' : 'ascending') : 'none';
    const arrow = sorted ? (sortDir < 0 ? ' ▾' : ' ▴') : '';
    const title = COL_TITLES[k] ? ` title="${esc(COL_TITLES[k])}"` : '';
    return `<th aria-sort="${ariaSort}"><button data-k="${k}"${title}>${l}${arrow}</button></th>`;
  }).join('') + '</tr></thead>';
  const body = '<tbody>' + (r.length ? r.map(row => {
    const cls = row.flag === 'remove' ? 'remove' : row.flag === 'watch' ? 'watch'
      : row.flag === 'manual' ? 'manual' : !row.enabled ? 'disabled' : '';
    const cell = k => {
      if (k === 'protocol') return `<span class="pill ${row.protocol}">${row.protocol}</span>`;
      if (k === 'flag') return row.flag ? `<span class="pill ${row.flag}">${row.flag}</span>` : '';
      if (k === 'reason') return `<span class="reason">${esc(row.reason || '')}</span>`;
      if (k === 'grabRate' || k === 'failRate') return (row[k] || 0).toFixed(2);
      if (k === 'name') return row.enabled ? esc(row.name) : esc(row.name) + ' <span class="reason">(off)</span>';
      const v = row[k]; return (typeof v === 'number') ? v.toLocaleString() : esc(v || '');
    };
    return `<tr class="${cls}">` + COLS.map(([k]) => `<td>${cell(k)}</td>`).join('') + '</tr>';
  }).join('') : `<tr><td colspan="${COLS.length}" class="reason" style="text-align:center;padding:24px">No indexers match this filter.</td></tr>`) + '</tbody>';

  const tbl = document.getElementById('tbl');
  tbl.innerHTML = head + body;
  tbl.querySelectorAll('th button').forEach(btn => btn.onclick = () => {
    const k = btn.dataset.k;
    if (k === sortKey) { sortDir *= -1; }
    else { sortKey = k; sortDir = (k === 'name' || k === 'protocol' || k === 'flag') ? 1 : -1; }
    renderTable();
  });
}

function setFilter(key, scroll) {
  tableFilter = key;
  renderChips();
  renderTable();
  // keep verdict-card active states in sync
  document.querySelectorAll('.verdict-card').forEach(c =>
    c.classList.toggle('active', c.dataset.filter === key));
  // Announce the result so assistive tech isn't left guessing what the filter did.
  if (lastRows) {
    const shown = lastRows.filter(filterFn(key)).length;
    const label = (FILTERS.find(f => f[0] === key) || FILTERS[0])[1].toLowerCase();
    document.getElementById('filterStatus').textContent = key === 'all'
      ? `Showing all ${shown} indexers`
      : `Showing ${shown} ${label} ${shown === 1 ? 'indexer' : 'indexers'}`;
  }
  if (scroll) {
    document.getElementById('tableSection')
      .scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
    // Move keyboard/screen-reader focus to the table so the next Tab lands in context.
    document.getElementById('tableHeading').focus({ preventScroll: true });
  }
}

function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }

function render(d) {
  // Skip the churn (chart destroy/recreate, table rebuild) when the server's
  // snapshot is unchanged — most 60s polls return the same data and a re-render
  // would only flash the charts and reset the user's hover/scroll.
  if (d.generatedAt && d.generatedAt === lastGeneratedAt) return;
  lastGeneratedAt = d.generatedAt;

  document.getElementById('loading').style.display = 'none';
  document.getElementById('report').style.display = 'block';
  lastRows = d.indexers;
  prowlarrUrl = d.prowlarrUrl || '';
  const openLink = document.getElementById('openProwlarr');
  if (prowlarrUrl) { openLink.href = prowlarrUrl; openLink.hidden = false; }
  else { openLink.hidden = true; }
  renderCards(d.summary);
  renderVerdict(d.indexers);
  renderChips();
  renderTable();
  renderCharts(d);
  // re-apply active state after cards re-render
  document.querySelectorAll('.verdict-card').forEach(c =>
    c.classList.toggle('active', c.dataset.filter === tableFilter));
}

async function poll() {
  try {
    const resp = await fetch('/api/data', { cache: 'no-store' });
    if (resp.status === 503) {
      const j = await resp.json();
      document.getElementById('statusText').textContent = 'service starting…';
      announce('Service starting');
      if (j.error) setBanner('Waiting on first Prowlarr fetch: ' + j.error);
      return;
    }
    const data = await resp.json();
    setStatus(data, null);
    render(data);
  } catch (e) {
    setStatus(null, e.message || String(e));
  }
}

/* ---- Wiring (attached once) ---- */
document.getElementById('refreshBtn').onclick = async (ev) => {
  ev.target.disabled = true;
  ev.target.textContent = 'Refreshing…';
  try { await fetch('/api/refresh', { method: 'POST' }); await poll(); }
  finally { ev.target.disabled = false; ev.target.textContent = 'Refresh now'; }
};

// Verdict cards filter the table (click + keyboard).
document.getElementById('cards').addEventListener('click', e => {
  const card = e.target.closest('.verdict-card[data-filter]');
  if (card) setFilter(card.dataset.filter, true);
});
document.getElementById('cards').addEventListener('keydown', e => {
  if (e.key !== 'Enter' && e.key !== ' ') return;
  const card = e.target.closest('.verdict-card[data-filter]');
  if (card) { e.preventDefault(); setFilter(card.dataset.filter, true); }
});

// Filter chips.
document.getElementById('filters').addEventListener('click', e => {
  const chip = e.target.closest('.chip[data-filter]');
  if (chip) setFilter(chip.dataset.filter, false);
});

// Copy the names of the remove candidates, newline-separated.
document.getElementById('copyDisable').onclick = async (ev) => {
  const names = (lastRows || []).filter(r => r.flag === 'remove').map(r => r.name);
  if (!names.length) return;
  const btn = ev.currentTarget;
  try {
    await navigator.clipboard.writeText(names.join('\n'));
    btn.textContent = `Copied ${names.length} ✓`;
  } catch {
    btn.textContent = 'Copy failed';
  }
  setTimeout(() => { btn.textContent = 'Copy disable list'; }, 2000);
};

poll();
setInterval(poll, POLL_MS);
