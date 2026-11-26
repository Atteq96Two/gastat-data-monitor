(() => {
'use strict';
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
const MONTHS = ['يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر'];
const SHORT = ['ينا','فبر','مار','أبر','ماي','يون','يول','أغس','سبت','أكت','نوف','ديس'];
const QN = ['الأول','الثاني','الثالث','الرابع'];
const MINUS = '−';
const SERIES_VARS = ['--s1','--s2','--s3','--s4','--s5','--s6'];
const fmt = (v, d = 1) => v == null || isNaN(v) ? '–' : (v < 0 && Math.abs(v) >= Math.pow(10, -d) / 2 ? MINUS : '') + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const ltr = s => `<bdi dir="ltr">${s}</bdi>`;
const plabel = p => {
  if (/^\d{4}-\d{2}$/.test(p)) return MONTHS[+p.slice(5) - 1] + ' ' + p.slice(0, 4);
  const q = /^(\d{4})-Q(\d)$/.exec(p); if (q) return 'الربع ' + QN[q[2] - 1] + ' ' + q[1];
  return p;
};
const pshort = p => {
  if (/^\d{4}-\d{2}$/.test(p)) return SHORT[+p.slice(5) - 1] + ' ' + p.slice(2, 4);
  const q = /^(\d{4})-Q(\d)$/.exec(p); if (q) return 'ر' + q[2] + ' ' + q[1].slice(2);
  return p;
};
const dlabel = iso => { if (!iso) return null; const [y, m, d] = iso.split('-'); return `${+d} ${MONTHS[+m - 1]} ${y}`; };
const shortUnit = u => !u ? '' : u.startsWith('%') ? '%' : u.startsWith('نقطة مئوية') ? ' نقطة مئوية' : ' ' + u.split(' لكل ')[0];
const cardUnit = u => !u ? '' : u === '%' ? '%' : u.split(' لكل ')[0];
const decimalsFor = u => (u && /ريال/.test(u)) ? 2 : 1;
const ARROW = {
  up: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M7 2l5 8H2z" fill="currentColor"/></svg>',
  down: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M7 12L2 4h10z" fill="currentColor"/></svg>',
  flat: '<svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M2 7h10" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>'
};
const deltaHTML = (h) => {
  const c = h.change; const dir = h.direction;
  const word = dir === 'up' ? 'ارتفاع' : dir === 'down' ? 'انخفاض' : 'دون تغيّر';
  const unit = c.kind === 'pp' ? 'نقطة مئوية' : '%';
  return `<span class="delta" title="${c.ref ? 'مقارنة بـ ' + plabel(c.ref) : 'مقارنة بالفترة السابقة'}">${ARROW[dir]}<span aria-label="${word}">${ltr(fmt(Math.abs(c.value), 2))}</span><span class="u">${unit}</span></span>`;
};

/* ------------------------------------------------------------ home */
let HOME = null;
const cache = {};
const getReport = id => cache[id] || (cache[id] = fetch(`data/reports/${id}.json`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }));

async function init() {
  try { HOME = await (await fetch('data/home.json')).json(); }
  catch (e) { $('#home').innerHTML = '<p class="empty">تعذّر تحميل البيانات.</p>'; return; }
  const main = $('#home');
  main.innerHTML = '';
  for (const g of HOME.groups) {
    const sec = el('section', 'group g-' + g.id);
    sec.append(el('h2', null, g.name_ar));
    const grid = el('div', 'grid');
    for (const c of g.cards) grid.append(card(c, g.id));
    sec.append(grid); main.append(sec);
  }
  $('#stamp').textContent = 'آخر تحديث: ' + dlabel(HOME.generated_at.slice(0, 10));
  route();
}

function card(c, gid) {
  const h = c.headline;
  const d = el('div', 'card g-' + gid);
  d.tabIndex = 0; d.setAttribute('role', 'button'); d.dataset.id = c.id;
  d.setAttribute('aria-label', `${c.name_ar}: ${h.label} ${fmt(h.value, decimalsFor(h.unit))} ${cardUnit(h.unit)}`);
  d.innerHTML = `<h3>${c.name_ar}</h3>
    <div class="read"><span class="lab">${h.label}</span><span class="val">${ltr(fmt(h.value, decimalsFor(h.unit)))}<small>${cardUnit(h.unit)}</small></span></div>
    ${deltaHTML(h)}
    ${c.new ? '<span class="badge">جديد</span>' : ''}
    ${c.stale ? '<span class="stale"><i></i>قد تكون البيانات متأخرة</span>' : ''}
    <button class="info" aria-label="معلومات عن التقرير"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M12 11v6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="12" cy="7.6" r="1.1" fill="currentColor"/></svg></button>`;
  d.addEventListener('click', e => { if (e.target.closest('.info')) return; openReport(c.id, d); });
  d.addEventListener('keydown', e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === d) { e.preventDefault(); openReport(c.id, d); } });
  const tipText = () => `<b>آخر إصدار:</b> ${dlabel(c.release_date) || '–'}<br><b>الإصدار القادم:</b> ${dlabel(c.next_release) || 'غير معلن'}<br>${c.description_ar}`;
  d.addEventListener('mouseenter', () => { if (matchMedia('(hover:hover)').matches) showTip(d, tipText()); });
  d.addEventListener('mouseleave', hideTip);
  d.addEventListener('focus', () => { if (matchMedia('(hover:hover)').matches) showTip(d, tipText()); });
  d.addEventListener('blur', hideTip);
  $('.info', d).addEventListener('click', e => { e.stopPropagation(); const t = $('#tip'); if (!t.hidden && t.dataset.for === c.id) hideTip(); else showTip(d, tipText(), true); });
  return d;
}

const tip = () => $('#tip');
function showTip(anchor, html, touch) {
  const t = tip(); t.innerHTML = html; t.hidden = false; t.dataset.for = anchor.dataset.id; t.classList.toggle('touch', !!touch);
  const r = anchor.getBoundingClientRect(), tw = t.offsetWidth, th = t.offsetHeight;
  let x = r.left + r.width / 2 - tw / 2; x = Math.max(8, Math.min(innerWidth - tw - 8, x));
  let y = r.top - th - 8; if (y < 8) y = r.bottom + 8;
  t.style.left = x + 'px'; t.style.top = y + 'px';
}
function hideTip() { tip().hidden = true; }
document.addEventListener('click', e => { if (!e.target.closest('.info') && !e.target.closest('#tip')) hideTip(); });
addEventListener('scroll', hideTip, { passive: true });

/* ------------------------------------------------------------ report sheet */
let lastFocus = null;
async function openReport(id, from) {
  lastFocus = from || null; hideTip();
  const ov = $('#overlay'), body = $('#sheet-body'), sheet = $('.sheet', ov);
  body.innerHTML = '<p class="empty">جارٍ التحميل…</p>';
  ov.hidden = false; document.body.style.overflow = 'hidden'; sheet.focus({ preventScroll: true });
  const grp = HOME.groups.find(g => g.cards.some(c => c.id === id));
  sheet.className = 'sheet g-' + (grp ? grp.id : 'prices');
  if (location.hash !== '#' + id) history.replaceState(null, '', '#' + id);
  try { const rep = await getReport(id); if (ov.hidden) return; render(rep, body); }
  catch (e) { body.innerHTML = '<p class="empty">تعذّر تحميل التقرير.</p>'; }
}
function closeReport() {
  const ov = $('#overlay'); if (ov.hidden) return;
  ov.hidden = true; document.body.style.overflow = ''; history.replaceState(null, '', location.pathname);
  if (lastFocus) lastFocus.focus({ preventScroll: true });
}
document.addEventListener('click', e => { if (e.target.closest('[data-close]')) closeReport(); });
addEventListener('keydown', e => { if (e.key === 'Escape') closeReport(); });
const route = () => { const id = location.hash.slice(1); if (id && HOME.groups.some(g => g.cards.some(c => c.id === id))) openReport(id); };
addEventListener('hashchange', () => { if (!location.hash) closeReport(); else route(); });

function render(rep, body) {
  if (rep.schema === 2) return render2(rep, body);
  const h = rep.headline;
  body.innerHTML = '';
  const head = el('div', 'rep-head');
  head.innerHTML = `<h2 id="sheet-title">${rep.name_ar}</h2>
    <div class="hl"><span class="val">${ltr(fmt(h.value, decimalsFor(h.unit)))}<small class="lab"> ${cardUnit(h.unit)}</small></span><span class="lab">${h.label} · ${plabel(h.period)}</span>${deltaHTML(h)}</div>`;
  body.append(head);
  body.append(chartBlock(rep.level1, rep, 'line', [ 'var(--accent)' ]));
  if (rep.level2) body.append(chartBlock(rep.level2, rep, rep.level2.kind));
  if (rep.level3 && rep.level3.length) {
    const more = el('div', 'more'); const btn = el('button', null, 'تفاصيل أكثر'); btn.setAttribute('aria-expanded', 'false'); more.append(btn);
    const box = el('div', 'l3'); box.hidden = true;
    btn.addEventListener('click', () => {
      const open = box.hidden; box.hidden = !open; btn.textContent = open ? 'إخفاء التفاصيل' : 'تفاصيل أكثر'; btn.setAttribute('aria-expanded', String(open));
      if (open && !box.childElementCount) for (const s of rep.level3) box.append(chartBlock(s, rep, s.kind));
      else if (open) box.querySelectorAll('.plot').forEach(p => p._redraw && p._redraw());
    });
    body.append(more, box);
  }
}

/* ------------------------------------------------------------ schema 2: one chart, up to three, then tabs; caption, explanation, weights */
function render2(rep, body) {
  const h = rep.headline;
  body.innerHTML = '';
  const head = el('div', 'rep-head');
  head.innerHTML = `<h2 id="sheet-title">${rep.name_ar}</h2>
    <div class="hl"><span class="val">${ltr(fmt(h.value, decimalsFor(h.unit)))}<small class="lab"> ${cardUnit(h.unit)}</small></span><span class="lab">${h.label} · ${plabel(h.period)}</span>${deltaHTML(h)}</div>`;
  body.append(head);
  body.append(chart2(rep.level1));
  for (const c of rep.level2 || []) body.append(chart2(c));
  if (rep.level3 && rep.level3.length) {
    const more = el('div', 'more'); const btn = el('button', null, 'تفاصيل أكثر'); btn.setAttribute('aria-expanded', 'false'); more.append(btn);
    const box = el('div', 'l3'); box.hidden = true;
    btn.addEventListener('click', () => {
      const open = box.hidden; box.hidden = !open; btn.textContent = open ? 'إخفاء التفاصيل' : 'تفاصيل أكثر'; btn.setAttribute('aria-expanded', String(open));
      if (open && !box.childElementCount) tabs(box, rep.level3);
      else if (open) box.querySelectorAll('.plot').forEach(p => p._redraw && p._redraw());
    });
    body.append(more, box);
  }
  if (rep.differs) body.append(differs(rep.differs));
}
function tabs(box, charts) {
  const bar = el('div', 'tabs'); bar.setAttribute('role', 'tablist');
  const panel = el('div', 'panel'); panel.setAttribute('role', 'tabpanel');
  const built = new Map();
  const show = i => {
    [...bar.children].forEach((b, j) => { b.setAttribute('aria-selected', String(i === j)); b.tabIndex = i === j ? 0 : -1; });
    if (!built.has(i)) built.set(i, chart2(charts[i]));
    panel.replaceChildren(built.get(i));
    panel.querySelectorAll('.plot').forEach(p => p._redraw && p._redraw());
  };
  charts.forEach((c, i) => { const b = el('button', 'tab', c.tab || c.title); b.setAttribute('role', 'tab'); b.addEventListener('click', () => show(i)); bar.append(b); });
  box.append(bar, panel); show(0);
}
function chart2(c) {
  const d = el('div', 'chart');
  d.append(el('h4', null, c.title));
  const meta = c.kind === 'table' || c.kind === 'updown' || c.kind === 'bars' || c.kind === 'bars_filter' ? 'الفترة: ' : 'حتى ';
  d.append(el('div', 'meta', `${c.unit ? 'الوحدة: ' + c.unit + ' · ' : ''}${meta}${plabel(c.period)}`));
  if (c.kind === 'line') c.selectable ? pickLine(d, c) : fixedLine(d, c);
  else if (c.kind === 'bars') bars(d, c);
  else if (c.kind === 'bars_filter') barsFilter(d, c);
  else if (c.kind === 'table') table(d, c);
  else if (c.kind === 'updown') updown(d, c);
  d.append(el('p', 'why', c.why));
  if (c.note) d.append(el('p', 'note', c.note));
  if (c.computed) d.append(el('p', 'note', 'الأرقام هنا محسوبة من نسب الهيئة المنشورة، وليست رقماً منشوراً بذاته.'));
  for (const x of c.explain || []) {
    const e = el('details', 'explain');
    e.innerHTML = `<summary>${x.term_ar}</summary><p>${x.text_ar}</p><p class="q">من منهجية الهيئة: «${x.quote}»</p><p class="s"><a href="${x.url}" target="_blank" rel="noopener">${x.source_ar}</a></p>`;
    d.append(e);
  }
  d.append(srcLine(c.source));
  return d;
}
const colorOf = i => `var(${SERIES_VARS[i]})`;
function fixedLine(d, c) {
  const cols = c.series.map((_, i) => colorOf(i % 6));
  if (c.series.length > 1) d.append(legend(c.series.map(s => ({ ...s, label: s.label + (s.weight != null ? ' · الوزن ' + fmt(s.weight, 1) + '%' : '') })), cols));
  const host = el('div', 'plot'); d.append(host); line(host, c.series, cols, { unit: c.unit });
}
function pickLine(d, c) {
  const slots = Array(6).fill(null), chosen = [];
  const take = l => { let i = slots.indexOf(null); if (i < 0) { const old = chosen.shift(); i = slots.indexOf(old); slots[i] = null; } slots[i] = l; chosen.push(l); };
  c.default.slice(0, 6).forEach(take);
  const chips = el('div', 'chips'); chips.setAttribute('role', 'group'); chips.setAttribute('aria-label', 'اختر حتى ستة خطوط');
  const host = el('div', 'plot');
  const draw = () => {
    chips.querySelectorAll('button').forEach(b => { const l = b.dataset.l, i = slots.indexOf(l); b.setAttribute('aria-pressed', String(i >= 0)); b.querySelector('i').style.background = i >= 0 ? colorOf(i) : 'transparent'; });
    const sel = chosen.map(l => c.series.find(s => s.label === l)).filter(Boolean);
    line(host, sel, sel.map(s => colorOf(slots.indexOf(s.label))), { unit: c.unit, force: true }); host._redraw = draw;
  };
  for (const s of c.series) {
    const b = el('button', 'chip', `<i></i><span>${s.label}</span>${s.weight != null ? `<small>الوزن ${ltr(fmt(s.weight, 1) + '%')}</small>` : ''}`); b.type = 'button'; b.dataset.l = s.label;
    b.addEventListener('click', () => { const i = chosen.indexOf(s.label); if (i >= 0) { if (chosen.length === 1) return; chosen.splice(i, 1); slots[slots.indexOf(s.label)] = null; } else take(s.label); draw(); });
    chips.append(b);
  }
  d.append(chips, host); host._redraw = draw; draw();
  if (window.ResizeObserver) new ResizeObserver(() => { if (host.clientWidth) draw(); }).observe(host);
}
function barsFilter(d, c) {
  const sel = el('select', 'pick'); sel.setAttribute('aria-label', 'القسم');
  for (const f of c.filters) { const o = el('option', null, f); o.value = f; if (f === c.default) o.selected = true; sel.append(o); }
  const box = el('div');
  const draw = () => { box.innerHTML = ''; bars(box, { bars: c.groups[sel.value] }); };
  sel.addEventListener('change', draw); d.append(sel, box); draw();
}
function chg(v) { return v == null ? '<span class="na">–</span>' : `<span class="chg">${v > 0.005 ? ARROW.up : v < -0.005 ? ARROW.down : ARROW.flat}${ltr(fmt(Math.abs(v), 2))}</span>`; }
function spark(pp) {
  if (!pp || pp.length < 2) return '';
  const pts = pp.map(x => x[1]); const W = 72, H = 22, mn = Math.min(...pts), mx = Math.max(...pts), rg = (mx - mn) || 1;
  const p = pts.map((v, i) => (i / (pts.length - 1) * (W - 4) + 2).toFixed(1) + ',' + (H - 3 - (v - mn) / rg * (H - 6)).toFixed(1)).join(' ');
  return `<svg class="spark" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" aria-hidden="true"><polyline points="${p}" fill="none" stroke="currentColor" stroke-width="1.5"/></svg>`;
}
function table(d, c) {
  const cols = c.columns, keys = Object.keys(cols);
  const w = el('div', 'tblwrap'); const t = el('table', 'tbl');
  t.innerHTML = '<thead><tr><th class="l">البند</th>' + keys.map(k => `<th>${cols[k]}</th>`).join('') + (c.rows.some(r => r.spark) ? '<th>منذ 2025</th>' : '') + '</tr></thead>';
  const tb = el('tbody');
  for (const r of c.rows) {
    const tr = el('tr', 'lv' + (r.level || 1));
    let h = `<td class="l" style="padding-inline-start:${Math.max(0, (r.level || 1) - 1) * 14}px">${r.label}${r.pack ? `<small>${r.pack}</small>` : ''}</td>`;
    for (const k of keys) h += '<td>' + (k === 'weight' ? (r.weight == null ? '' : ltr(fmt(r.weight, 2))) : k === 'value' ? (r.value == null ? '' : ltr(fmt(r.value, 2))) : chg(r[k])) + '</td>';
    if (c.rows.some(x => x.spark)) h += `<td>${spark(r.spark)}</td>`;
    tr.innerHTML = h; tb.append(tr);
  }
  t.append(tb); w.append(t); d.append(w);
}
function updown(d, c) {
  const w = el('div', 'ud');
  w.append(el('div', 'udlg', '<span><i class="u"></i>ارتفع</span><span><i class="f"></i>ثابت</span><span><i class="d"></i>انخفض</span>'));
  const mx = Math.max(...c.rows.map(r => r.total));
  for (const r of c.rows) {
    const row = el('div', 'udr' + (r.label === 'كل البنود' ? ' all' : ''));
    const wd = x => (x / r.total * 100).toFixed(1) + '%';
    row.innerHTML = `<span class="l">${r.label}</span><span class="t" style="width:${Math.max(18, r.total / mx * 100)}%"><i class="u" style="width:${wd(r.up)}"></i><i class="f" style="width:${wd(r.flat)}"></i><i class="d" style="width:${wd(r.down)}"></i></span><span class="v">ارتفع ${ltr(r.up)} · انخفض ${ltr(r.down)}${r.flat ? ' · ثابت ' + ltr(r.flat) : ''}</span>`;
    w.append(row);
  }
  d.append(w);
}
function differs(x) {
  const s = el('section', 'differs'); s.append(el('h3', null, x.title_ar));
  const g = el('div', 'dgrid');
  for (const it of x.items) g.append(el('div', 'ditem' + (it.self ? ' self' : ''), `<b>${it.name_ar}</b><p>${it.text_ar}</p><a href="${it.url}" target="_blank" rel="noopener">${it.source_ar}</a>`));
  s.append(g); return s;
}

function chartBlock(c, rep, kind, colors) {
  const d = el('div', 'chart');
  d.append(el('h4', null, c.title));
  d.append(el('div', 'meta', `${c.unit ? 'الوحدة: ' + c.unit + ' · ' : ''}${kind === 'line' || kind === 'small_multiples' ? 'حتى ' : 'الفترة: '}${plabel(c.period)}`));
  if (kind === 'line') {
    if (c.series.length > 1) d.append(legend(c.series, colors || SERIES_VARS.map(v => `var(${v})`)));
    let series = c.series;
    const long = series[0].points.length > 48 && series.length > 1;   // several lines over a decade are unreadable: show the last 36 periods
    if (long) { series = series.map(s => ({ ...s, points: s.points.slice(-36) })); d.querySelector('.meta').textContent += ' · آخر 36 ' + (/^\d{4}-\d{2}$/.test(series[0].points[0][0]) ? 'شهراً' : 'فترة'); }
    const host = el('div', 'plot'); d.append(host); line(host, series, colors || SERIES_VARS.map(v => `var(${v})`), { unit: c.unit });
  } else if (kind === 'small_multiples') {
    const g = el('div', 'multi');
    for (const s of c.series) {
      const m = el('div', 'mini'); const last = s.points[s.points.length - 1];
      m.innerHTML = `<div class="mt"><b>${s.label}</b><span class="mv">${fmt(last[1], 2)}</span></div><div class="mu">${s.unit}</div>`;
      const host = el('div', 'plot'); m.append(host); g.append(m);
      line(host, [s], ['var(--accent)'], { unit: s.unit, compact: true });
    }
    d.append(g);
  } else bars(d, c);
  d.append(srcLine(c.source));
  return d;
}
function srcLine(s) {
  const r = el('div', 'src');
  r.innerHTML = `<span>المصدر: الهيئة العامة للإحصاء</span>` + (s && s.file ? `<a href="${s.file}" target="_blank" rel="noopener">ملف الإكسل الأصلي${s.sheet ? ' (ورقة ' + s.sheet + ')' : ''}</a>` : '') + (s && s.release ? `<span>نُشر ${dlabel(s.release)}</span>` : '');
  return r;
}
function legend(series, colors) {
  const l = el('div', 'legend');
  series.forEach((s, i) => l.append(el('span', null, `<i style="background:${colors[i % colors.length]}"></i>${s.label}`)));
  return l;
}

/* ------------------------------------------------------------ charts */
function niceTicks(min, max, n) {
  if (min === max) { min -= 1; max += 1; }
  const raw = (max - min) / n, p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * p;
  const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step, t = [];
  for (let v = lo; v <= hi + step / 2; v += step) t.push(+v.toFixed(10));
  return t;
}
function line(host, series, colors, o) {
  let lastW = 0;
  const draw = () => {
    const W = Math.max(240, host.clientWidth || 600); if (W === lastW && host.firstChild && !o.force) return; lastW = W;
    const compact = o.compact, H = compact ? 96 : (W < 520 ? 210 : 250);
    const L = compact ? 34 : 44, R = compact ? 10 : (series.length <= 4 ? 52 : 14), T = 10, B = compact ? 18 : 24;
    const periods = [...new Set(series.flatMap(s => s.points.map(p => p[0])))].sort();
    const idx = new Map(periods.map((p, i) => [p, i]));
    const vals = series.flatMap(s => s.points.map(p => p[1]).filter(v => v != null));
    let mn = Math.min(...vals), mx = Math.max(...vals);
    const pct = /%|نقطة مئوية/.test(o.unit || '');
    if (pct) { mn = Math.min(mn, 0); mx = Math.max(mx, 0); }
    const ticks = niceTicks(mn, mx, compact ? 2 : 4), y0 = ticks[0], y1 = ticks[ticks.length - 1];
    const n = periods.length, X = i => L + (n === 1 ? (W - L - R) / 2 : i / (n - 1) * (W - L - R)), Y = v => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
    const stp = (y1 - y0) / (ticks.length - 1), dec = Math.abs(stp - Math.round(stp)) < 1e-9 ? 0 : Math.abs(stp * 10 - Math.round(stp * 10)) < 1e-9 ? 1 : 2;
    let xt = [];
    if (n > 36) { periods.forEach((p, i) => { if (/-(01|Q1)$/.test(p) || /^\d{4}$/.test(p)) xt.push(i); }); const k = Math.ceil(xt.length / 6); xt = xt.filter((_, j) => j % k === 0); }
    else { const m = Math.min(n, compact ? 3 : (W < 520 ? 4 : 6)); for (let j = 0; j < m; j++) xt.push(Math.round(j * (n - 1) / Math.max(1, m - 1))); xt = [...new Set(xt)]; }
    const xl = i => n > 36 ? periods[i].slice(0, 4) : pshort(periods[i]);
    let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${(series[0] && series[0].label) || ''}">`;
    for (const t of ticks) s += `<line x1="${L}" x2="${W - R}" y1="${Y(t)}" y2="${Y(t)}" style="stroke:var(${t === 0 && y0 < 0 ? '--line' : '--grid'})" stroke-width="1"/><text x="${L - 6}" y="${Y(t) + 4}" text-anchor="end">${fmt(t, dec)}</text>`;
    for (const i of xt) s += `<text x="${X(i)}" y="${H - 4}" text-anchor="${i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}">${xl(i)}</text>`;
    series.forEach((sr, k) => {
      const col = colors[k % colors.length]; let dpath = '', pen = false;
      for (const [p, v] of sr.points) { if (v == null) { pen = false; continue; } dpath += (pen ? 'L' : 'M') + X(idx.get(p)).toFixed(1) + ' ' + Y(v).toFixed(1); pen = true; }
      s += `<path d="${dpath}" fill="none" style="stroke:${col}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
      const lp = [...sr.points].reverse().find(p => p[1] != null);
      if (lp) {
        s += `<circle cx="${X(idx.get(lp[0]))}" cy="${Y(lp[1])}" r="4.5" style="fill:${col};stroke:var(--surface)" stroke-width="2"/>`;
        if (series.length <= 4 && !compact) s += `<text x="${X(idx.get(lp[0])) + 9}" y="${Y(lp[1]) + 4}" style="fill:var(--ink);font-size:12px;font-weight:500">${fmt(lp[1], decimalsFor(o.unit))}</text>`;
      }
    });
    s += `<line class="cx" y1="${T}" y2="${H - B}" style="stroke:var(--ink-3)" stroke-width="1" stroke-dasharray="3 3" visibility="hidden"/><g class="dots"></g>`;
    s += `<rect class="hit" x="${L}" y="0" width="${W - L}" height="${H}" fill="transparent"/></svg><div class="ptip" hidden></div>`;
    host.innerHTML = s;
    const svg = host.firstChild, hit = svg.querySelector('.hit'), cx = svg.querySelector('.cx'), dots = svg.querySelector('.dots'), pt = host.querySelector('.ptip');
    const move = e => {
      const r = svg.getBoundingClientRect(), px = (e.clientX - r.left) * (W / r.width);
      const i = Math.max(0, Math.min(n - 1, Math.round((px - L) / (W - L - R) * (n - 1))));
      cx.setAttribute('x1', X(i)); cx.setAttribute('x2', X(i)); cx.setAttribute('visibility', 'visible');
      let rows = '', dd = '';
      series.forEach((sr, k) => { const f = sr.points.find(p => p[0] === periods[i]); if (!f || f[1] == null) return; const col = colors[k % colors.length];
        dd += `<circle cx="${X(i)}" cy="${Y(f[1])}" r="4" style="fill:${col};stroke:var(--surface)" stroke-width="2"/>`;
        rows += `<div class="r"><span><i style="background:${col}"></i>${series.length > 1 ? sr.label : ''}</span><span class="n">${ltr(fmt(f[1], 2) + shortUnit(o.unit))}</span></div>`; });
      dots.innerHTML = dd; pt.innerHTML = `<div class="p">${plabel(periods[i])}</div>${rows}`; pt.hidden = false;
      const sx = X(i) * (r.width / W), tw = pt.offsetWidth; pt.style.left = Math.max(0, Math.min(r.width - tw, sx + 12 + tw > r.width ? sx - tw - 12 : sx + 12)) + 'px'; pt.style.top = '0px';
    };
    const leave = () => { cx.setAttribute('visibility', 'hidden'); dots.innerHTML = ''; pt.hidden = true; };
    hit.addEventListener('pointermove', move); hit.addEventListener('pointerdown', move); hit.addEventListener('pointerleave', leave);
  };
  host._redraw = () => { lastW = 0; draw(); };
  draw();
  if (window.ResizeObserver && !o.force) new ResizeObserver(() => { if (host.clientWidth) draw(); }).observe(host);
}

function bars(d, c) {
  const vs = c.bars.map(b => b.value), mn = Math.min(0, ...vs), mx = Math.max(0, ...vs), rg = (mx - mn) || 1, z = -mn / rg * 100;
  const dec = Math.max(...vs.map(Math.abs)) < 1 ? 2 : 1;
  const w = el('div', 'bars');
  for (const b of c.bars) {
    const len = Math.abs(b.value) / rg * 100, left = b.value >= 0 ? z : z - len;
    const r = el('div', 'bar');
    r.innerHTML = `<span class="l">${b.label}${b.weight != null ? `<small>الوزن ${ltr(fmt(b.weight, 1) + '%')}</small>` : ''}</span><span class="t" style="--z:${z}%"><span class="f" style="left:${left}%;width:${Math.max(len, .4)}%"></span></span><span class="v">${fmt(b.value, dec)}</span>`;
    w.append(r);
  }
  d.append(w);
}

init();
})();
