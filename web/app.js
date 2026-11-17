"use strict";
/* GASTAT Data Monitor web page. Plain JavaScript, no build step. All data comes from ./data/*.json (written by gastat/webdata.py). */
const $ = (s, r = document) => r.querySelector(s);
const app = $("#app");
const cache = {};
const PAL = ["var(--c1)", "var(--c2)", "var(--c3)", "var(--c4)", "var(--c5)", "var(--c6)"];

/* text helpers: escape, and no long dashes anywhere on screen */
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const tx = s => esc(String(s ?? "").replace(/[\u2013\u2014]/g, "-"));
const fmt = v => v == null ? "" : Math.abs(v) >= 1000 ? Math.round(v).toLocaleString("en-US") : (+v.toFixed(2)).toLocaleString("en-US", { maximumFractionDigits: 2 });
const MONTHS = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"];
const QN = { 1: "الأول", 2: "الثاني", 3: "الثالث", 4: "الرابع" };
function plabel(p) {
  let m = /^(\d{4})-(\d{2})$/.exec(p); if (m) return `${MONTHS[+m[2] - 1]} ${m[1]}`;
  m = /^(\d{4})-Q([1-4])$/.exec(p); if (m) return `الربع ${QN[m[2]]} ${m[1]}`;
  return p;
}
const dlabel = d => { const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(d || ""); return m ? `${+m[3]} ${MONTHS[+m[2] - 1]} ${m[1]}` : (d || ""); };
const norm = s => String(s || "").toLowerCase().replace(/[ً-ْـ]/g, "").replace(/[أإآ]/g, "ا").replace(/ى/g, "ي").replace(/ة/g, "ه").replace(/\s+/g, " ").trim();

async function get(path) {
  if (!cache[path]) {
    cache[path] = fetch(`data/${path}`, { cache: "no-cache" }).then(r => { if (!r.ok) throw new Error(path); return r.json(); });
  }
  return cache[path];
}
function table(head, rows, cls = "") {
  return `<div class="tw"><table class="${cls}"><thead><tr>${head.map(h => `<th scope="col">${h}</th>`).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
}
const chip = (t, k = "") => `<span class="chip ${k}">${tx(t)}</span>`;
const KIND = { series_change: "تغيّر", mover_up: "أكبر ارتفاع", mover_down: "أكبر انخفاض", cross_section: "مقارنة بين البنود", revision: "تعديل" };

/* ---------------------------------------------------------------- home */
async function home() {
  const [d, q] = await Promise.all([get("latest.json"), get("quality.json")]);
  const withData = d.releases.filter(r => r.has_data);
  const total = withData.reduce((a, r) => a + r.insight_count, 0);
  let h = `<h2>أحدث الإصدارات</h2><p class="lead">كل إصدار جديد من الهيئة يُحمَّل ويُفكَّك ويُفحَص، ثم تُحسب منه أرقام أساسية. المصدر: الهيئة العامة للإحصاء.</p>
  <div class="banner">نطاق البيانات الحالي: إصدارات نوفمبر 2026. الإصدارات الأقدم مسجّلة كعناوين وتواريخ فقط.</div>
  <div class="grid" style="margin-bottom:16px">
   <div class="stat"><b>${q.ingested}</b><span>إصداراً بالبيانات الكاملة من ${q.registered} مسجّلاً</span></div>
   <div class="stat"><b>${q.datasets}</b><span>جدول بيانات</span></div>
   <div class="stat"><b>${(q.values || 0).toLocaleString("en-US")}</b><span>قيمة مخزّنة</span></div>
   <div class="stat"><b>${total}</b><span>استنتاج محسوب</span></div>
  </div>`;
  const rows = d.releases.slice(0, 40);
  h += rows.map(r => {
    const hs = r.headlines.slice(0, 3);
    return `<article class="card"><div class="row spread"><h3>${tx(r.title_ar)}</h3><span class="muted">${dlabel(r.release_date)}</span></div>
    <div class="row">${chip(r.domain_ar)}${chip(r.frequency_ar)}${r.has_data ? chip("بيانات متاحة", "ok") : chip("عنوان وتاريخ فقط")}${r.has_data ? chip(r.insight_count + " استنتاج", "info") : ""}</div>
    ${hs.length ? `<ul class="insights">${hs.map(i => `<li><span class="kind">${KIND[i.kind] || ""}</span>${tx(i.text_ar)}</li>`).join("")}</ul>` : ""}
    ${r.has_data ? `<details><summary>كل الاستنتاجات (${r.insight_count})</summary><div data-ins="${r.publication_id}" class="muted">جارٍ التحميل...</div></details>` : ""}
    <div class="row" style="margin-top:8px">${r.xlsx ? `<a class="btn ghost" href="${esc(r.xlsx)}" rel="noopener">ملف الإكسل من الهيئة</a>` : ""}${r.pdf ? `<a class="btn ghost" href="${esc(r.pdf)}" rel="noopener">النشرة (PDF)</a>` : ""}${r.has_data ? `<a class="btn ghost" href="#/explore?pub=${r.publication_id}">استكشاف جداول الإصدار</a>` : ""}</div>
    </article>`;
  }).join("");
  app.innerHTML = h;
  app.querySelectorAll("details").forEach(dt => dt.addEventListener("toggle", async () => {
    const box = dt.querySelector("[data-ins]"); if (!dt.open || box.dataset.done) return;
    const ins = await get(`insights/${box.dataset.ins}.json`);
    box.dataset.done = 1; box.classList.remove("muted");
    box.innerHTML = `<ul class="insights">${ins.insights.map(i => `<li><span class="kind">${KIND[i.kind] || ""}</span>${tx(i.text_ar)}</li>`).join("")}</ul>`;
  }));
}

/* ---------------------------------------------------------------- explorer */
const ex = { q: "", domain: "", freq: "", pub: "", ds: null, picked: [], filter: "" };
async function explore(params) {
  const [cat, idx] = await Promise.all([get("catalog.json"), get("search_index.json")]);
  if (params.pub) ex.pub = params.pub;
  const doms = [...new Set(cat.datasets.map(d => d.domain_ar))];
  const freqs = [...new Set(cat.datasets.map(d => d.frequency_ar))];
  app.innerHTML = `<h2>مستكشف المؤشرات</h2><p class="lead">ابحث بالعربية أو الإنجليزية في أسماء الجداول والبنود، ثم اختر السلاسل لرؤية الرسم والأرقام. المصدر: الهيئة العامة للإحصاء.</p>
  <div class="row" style="margin-bottom:12px"><label class="sr" for="q">بحث</label><input id="q" type="search" placeholder="مثال: التضخم، الناتج المحلي، Gas" value="${esc(ex.q)}">
  <label class="sr" for="fd">المجال</label><select id="fd"><option value="">كل المجالات</option>${doms.map(x => `<option ${x === ex.domain ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>
  <label class="sr" for="ff">التكرار</label><select id="ff"><option value="">كل الأنواع</option>${freqs.map(x => `<option ${x === ex.freq ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>
  ${ex.pub ? `<button class="ghost" id="clearpub">إلغاء تصفية الإصدار</button>` : ""}</div>
  <div class="layout"><div><div id="count" class="muted" style="margin-bottom:6px" aria-live="polite"></div><div class="list" id="dlist"></div></div><div id="detail"><div class="card muted">اختر جدولاً من القائمة.</div></div></div>`;
  const draw = () => {
    const q = norm(ex.q);
    const hit = cat.datasets.filter(d => (!ex.domain || d.domain_ar === ex.domain) && (!ex.freq || d.frequency_ar === ex.freq) && (!ex.pub || String(d.publication_id) === ex.pub) &&
      (!q || q.split(" ").every(w => norm(d.title_ar + " " + d.title_en + " " + d.publication_title_ar + " " + d.publication_title_en + " " + (idx.labels[d.dataset_id] || []).join(" ")).includes(w))));
    $("#count").textContent = `${hit.length} جدول`;
    $("#dlist").innerHTML = hit.slice(0, 150).map(d => `<button type="button" data-id="${esc(d.dataset_id)}" aria-pressed="${ex.ds && ex.ds.dataset_id === d.dataset_id}">${tx(d.title_ar)}<small>${tx(d.publication_title_ar)} | ${tx(d.last_period)} | ${d.series} سلسلة</small></button>`).join("") + (hit.length > 150 ? `<p class="muted" style="padding:8px 12px">يُعرض أول 150 نتيجة. ضيّق البحث لرؤية الباقي.</p>` : "") || `<p class="muted" style="padding:12px">لا نتائج.</p>`;
    $("#dlist").querySelectorAll("button").forEach(b => b.onclick = () => openDataset(cat.datasets.find(d => d.dataset_id === b.dataset.id), draw));
  };
  $("#q").oninput = e => { ex.q = e.target.value; draw(); };
  $("#fd").onchange = e => { ex.domain = e.target.value; draw(); };
  $("#ff").onchange = e => { ex.freq = e.target.value; draw(); };
  const cp = $("#clearpub"); if (cp) cp.onclick = () => { ex.pub = ""; location.hash = "#/explore"; };
  draw();
  if (ex.ds) openDataset(ex.ds, draw, true);
}

async function openDataset(d, redraw, keep) {
  if (!keep) { ex.ds = d; ex.picked = []; ex.filter = ""; }
  const box = $("#detail"); box.innerHTML = `<div class="card muted">جارٍ تحميل الجدول...</div>`;
  const s = await get(`series/${d.dataset_id}.json`);
  if (!keep) {
    const tot = s.series.map((x, i) => [x, i]).filter(([x]) => x.total && x.values.some(v => v != null));
    const first = (tot.length ? tot : s.series.map((x, i) => [x, i])).slice(0, 1).map(([, i]) => i);
    ex.picked = first;
  }
  const f = d.freshness || {};
  const st = { current: ["حديث", "ok"], scheduled: ["الإصدار القادم مجدول", "info"], overdue: ["تجاوز الدورة المعتادة", "warn"] }[f.status] || ["", ""];
  box.innerHTML = `<div class="card"><h3>${tx(d.title_ar)}</h3><p class="muted" style="margin:0">${tx(d.title_en)}</p>
   <div class="row" style="margin:8px 0">${chip(d.publication_title_ar)}${chip(d.frequency_ar)}${chip("آخر فترة: " + plabel(d.last_period))}${chip("نُشر " + dlabel(d.release_date))}${st[0] ? chip(st[0], st[1]) : ""}</div>
   <div class="row"><a class="btn ghost" href="${esc(d.parquet_url)}" rel="noopener">تنزيل الجدول الكامل (Parquet)</a>${d.csv_url ? `<a class="btn ghost" href="${esc(d.csv_url)}" rel="noopener">تنزيل CSV</a>` : ""}<button class="ghost" id="dlsel" type="button">تنزيل السلاسل المختارة</button></div></div>
   <div class="card"><label for="sf" class="muted">اختر حتى 6 سلاسل (${s.series.length} متاحة)</label><div class="row" style="margin:6px 0"><input id="sf" type="search" placeholder="تصفية السلاسل بالاسم" value="${esc(ex.filter)}"></div><div class="list" id="slist" style="max-height:230px"></div></div>
   <div class="card"><div id="chart"></div></div><div id="data"></div>`;
  const drawList = () => {
    const q = norm(ex.filter);
    const items = s.series.map((x, i) => [x, i]).filter(([x]) => !q || q.split(" ").every(w => norm(x.label + " " + x.label_en).includes(w)));
    $("#slist").innerHTML = items.slice(0, 200).map(([x, i]) => `<label style="display:flex;gap:10px;padding:8px 12px;border-bottom:1px solid var(--line);cursor:pointer;min-height:44px;align-items:center"><input type="checkbox" data-i="${i}" ${ex.picked.includes(i) ? "checked" : ""}><span>${tx(x.label || x.label_en || "(بلا اسم)")}${x.unit_text ? ` <small class="muted">${tx(x.unit_text)}</small>` : ""}</span></label>`).join("") || `<p class="muted" style="padding:12px">لا نتائج.</p>`;
    $("#slist").querySelectorAll("input").forEach(c => c.onchange = () => {
      const i = +c.dataset.i;
      if (c.checked) { if (ex.picked.length >= 6) { c.checked = false; return; } ex.picked.push(i); } else ex.picked = ex.picked.filter(x => x !== i);
      drawChart(d, s);
    });
  };
  $("#sf").oninput = e => { ex.filter = e.target.value; drawList(); };
  $("#dlsel").onclick = () => download(d, s);
  drawList(); drawChart(d, s); redraw();
}

function download(d, s) {
  const sel = ex.picked.map(i => s.series[i]);
  const rows = [["period", ...sel.map(x => `"${(x.label || x.label_en).replace(/"/g, '""')}"`)].join(",")];
  s.periods.forEach((p, k) => rows.push([p, ...sel.map(x => x.values[k] ?? "")].join(",")));
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob(["﻿" + rows.join("\n")], { type: "text/csv;charset=utf-8" }));
  a.download = `${d.dataset_id}.csv`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function drawChart(d, s) {
  const sel = ex.picked.map(i => s.series[i]);
  const ch = $("#chart"), dt = $("#data");
  if (!sel.length) { ch.innerHTML = `<p class="muted">اختر سلسلة واحدة على الأقل.</p>`; dt.innerHTML = ""; return; }
  const P = s.periods;
  const idx = P.map((_, k) => k).filter(k => sel.some(x => x.values[k] != null));
  const multi = idx.length >= 2;
  const unitTxt = [...new Set(sel.map(x => x.unit_text))].filter(Boolean).join("، ");
  const note = sel.some(x => !x.unit_ok) ? `<p class="muted">وحدة بعض السلاسل غير محسومة في المصدر، والأرقام معروضة كما نُشرت.</p>` : "";
  let h = `<div class="legend">${sel.map((x, j) => `<span><i class="sw" style="background:${PAL[j]}"></i>${tx(x.label || x.label_en)}</span>`).join("")}</div>`;
  const W = 720, H = 300, L = 56, R = 14, T = 14, B = 34;
  const vals = sel.flatMap(x => idx.map(k => x.values[k]).filter(v => v != null));
  let lo = Math.min(...vals), hi = Math.max(...vals); if (lo === hi) { lo -= 1; hi += 1; }
  if (lo > 0 && lo < hi * 0.6) lo = 0;
  const pad = (hi - lo) * 0.06; hi += pad; if (lo !== 0) lo -= pad;
  const y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));
  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="رسم بياني: ${esc(unitTxt)}">`;
  for (let t = 0; t <= 4; t++) { const v = lo + (hi - lo) * t / 4, yy = y(v); svg += `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" stroke="var(--line)"/><text x="${L - 6}" y="${yy + 4}" text-anchor="end" direction="ltr">${fmt(v)}</text>`; }
  if (multi) {
    const x = k => L + (W - L - R) * (idx.indexOf(k)) / (idx.length - 1);
    const step = Math.ceil(idx.length / 7);
    idx.forEach((k, n) => { if (n % step === 0 || (n === idx.length - 1 && (idx.length - 1) % step >= step * 0.6)) svg += `<text x="${x(k)}" y="${H - 12}" text-anchor="middle" direction="ltr">${esc(P[k])}</text>`; });
    sel.forEach((sr, j) => {
      let path = "", pen = false;
      idx.forEach(k => { const v = sr.values[k]; if (v == null) { pen = false; return; } path += `${pen ? "L" : "M"}${x(k).toFixed(1)},${y(v).toFixed(1)}`; pen = true; });
      svg += `<path d="${path}" fill="none" stroke="${PAL[j]}" stroke-width="2.2" stroke-linejoin="round"/>`;
      if (idx.length <= 40) idx.forEach(k => { const v = sr.values[k]; if (v != null) svg += `<circle cx="${x(k).toFixed(1)}" cy="${y(v).toFixed(1)}" r="2.6" fill="${PAL[j]}"/>`; });
    });
    svg += `<line id="xh" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="var(--muted)" stroke-dasharray="3 3" visibility="hidden"/><rect id="ov" x="${L}" y="${T}" width="${W - L - R}" height="${H - T - B}" fill="transparent"/></svg>`;
    ch.innerHTML = h + `<div class="cw">${svg}<div class="tip" id="tip" hidden></div></div>` + note;
    const ov = $("#ov"), tip = $("#tip"), xh = $("#xh"), svgEl = $(".chart", ch);
    ov.addEventListener("pointermove", e => {
      const r = svgEl.getBoundingClientRect(), px = (e.clientX - r.left) / r.width * W;
      const n = Math.max(0, Math.min(idx.length - 1, Math.round((px - L) / (W - L - R) * (idx.length - 1)))), k = idx[n];
      xh.setAttribute("x1", x(k)); xh.setAttribute("x2", x(k)); xh.setAttribute("visibility", "visible");
      tip.hidden = false; tip.innerHTML = `<b>${esc(plabel(P[k]))}</b><br>` + sel.map((sr, j) => `<i class="sw" style="background:${PAL[j]}"></i>${fmt(sr.values[k]) || "لا قيمة"}`).join("<br>");
      const left = (x(k) / W) * r.width; tip.style.left = Math.min(Math.max(left - 60, 0), r.width - 180) + "px"; tip.style.top = "10px";
    });
    ov.addEventListener("pointerleave", () => { tip.hidden = true; xh.setAttribute("visibility", "hidden"); });
  } else {
    // one period only: horizontal bars, one per selected series
    const k = idx[0] ?? 0; const bw = 28, gap = 10, hh = sel.length * (bw + gap) + 10;
    const mx = Math.max(...sel.map(x => Math.abs(x.values[k] ?? 0)), 1e-9);
    svg = `<svg class="chart" viewBox="0 0 ${W} ${hh}" role="img" aria-label="رسم أعمدة">`;
    sel.forEach((sr, j) => { const v = sr.values[k]; const w = v == null ? 0 : Math.abs(v) / mx * (W - 190); svg += `<rect x="${W - 10 - w}" y="${j * (bw + gap) + 5}" width="${w}" height="${bw}" rx="4" fill="${PAL[j]}"/><text x="${W - 14 - w}" y="${j * (bw + gap) + 24}" text-anchor="end" direction="ltr" style="fill:var(--ink)">${fmt(v)}</text>`; });
    ch.innerHTML = h + svg + `</svg><p class="muted">فترة واحدة: ${esc(plabel(P[k]))}</p>` + note;
  }
  // data table (latest 24 periods)
  const show = idx.slice(-24).reverse();
  dt.innerHTML = `<h3>الأرقام ${unitTxt ? `<small class="muted">(${tx(unitTxt)})</small>` : ""}</h3>` + table(["الفترة", ...sel.map(x => tx(x.label || x.label_en))], show.map(k => `<tr><td style="white-space:nowrap">${esc(plabel(P[k]))}</td>${sel.map(x => `<td class="num">${fmt(x.values[k])}</td>`).join("")}</tr>`)) +
    `<p class="muted" style="margin-top:8px">الخلية المصدر في ملف الهيئة لآخر فترة معروضة (${esc(plabel(P[idx[idx.length - 1]] || ""))}): ${sel.map(x => `<span class="num">${esc(s.sheet)}!${esc(x.cells[idx[idx.length - 1]] || "")}</span>`).join("، ")}</p>`;
}

/* ---------------------------------------------------------------- freshness */
async function fresh() {
  const d = await get("freshness.json");
  const S = { overdue: ["تجاوز الدورة المعتادة", "warn"], scheduled: ["الإصدار القادم مجدول", "info"], current: ["حديث", "ok"] };
  const cnt = k => d.items.filter(i => i.status === k).length;
  let only = "";
  const render = () => {
    const items = d.items.filter(i => !only || (only === "data" ? i.has_data : i.status === only));
    $("#ft").innerHTML = table(["المنشور", "التكرار", "آخر إصدار", "منذ", "الإصدار القادم", "الحالة", "البيانات"],
      items.map(i => `<tr><td>${tx(i.title_ar)}</td><td>${tx(i.frequency_ar)}</td><td>${dlabel(i.last_release)}</td><td class="num">${i.days_since} يوماً</td><td>${i.calendar_next ? dlabel(i.calendar_next) : `<span class="muted">متوقع ${dlabel(i.expected_next)}</span>`}</td><td>${chip(...S[i.status])}</td><td>${i.has_data ? chip("متاحة", "ok") : chip("عنوان فقط")}</td></tr>`));
    $("#fc").textContent = `${items.length} منشور`;
  };
  app.innerHTML = `<h2>حداثة البيانات</h2><p class="lead">لكل منشور: تاريخ آخر إصدار، والإصدار القادم من جدول الهيئة إن وُجد، وإلا فالمتوقع حسب التكرار. «تجاوز الدورة المعتادة» يعني مرور دورة كاملة (شهر أو ربع أو سنة) و10 أيام دون أي إصدار مسجّل لهذا المنشور، حتى لو كان الإصدار القادم مجدولاً. المصدر: الهيئة العامة للإحصاء.</p>
  <div class="grid" style="margin-bottom:12px"><div class="stat"><b>${cnt("overdue")}</b><span>تجاوز الدورة المعتادة</span></div><div class="stat"><b>${cnt("scheduled")}</b><span>إصدار قادم مجدول</span></div><div class="stat"><b>${cnt("current")}</b><span>حديث</span></div><div class="stat"><b>${d.items.filter(i => i.has_data).length}</b><span>منشوراً بالبيانات الكاملة</span></div></div>
  <div class="row" style="margin-bottom:10px"><label class="sr" for="fs">تصفية</label><select id="fs"><option value="">كل المنشورات</option><option value="data">التي لها بيانات فقط</option><option value="overdue">التي تجاوزت دورتها</option><option value="scheduled">المجدولة</option><option value="current">الحديثة</option></select><span class="muted" id="fc" aria-live="polite"></span><span class="muted">تاريخ اليوم: ${dlabel(d.today)}</span></div><div id="ft"></div>`;
  $("#fs").onchange = e => { only = e.target.value; render(); };
  render();
}

/* ---------------------------------------------------------------- quality */
async function quality() {
  const q = await get("quality.json");
  const SEV = { source: ["تعارض في المصدر", "bad"], open: ["مفتوح", "warn"], question: ["بانتظار تأكيد", "warn"], info: ["معلومة", "info"] };
  const rc = q.recipes || {};
  app.innerHTML = `<h2>جودة البيانات</h2><p class="lead">ما الذي فُحص، وما نتيجته، وما المفتوح. لا يُنشر جدول إلا إذا اجتاز كل الفحوص. المصدر: الهيئة العامة للإحصاء.</p>
  <div class="grid" style="margin-bottom:16px">
   <div class="stat"><b>${(q.cells_checked || 0).toLocaleString("en-US")}</b><span>قيمة قورنت بخليتها الأصلية في ملف الإكسل</span></div>
   <div class="stat"><b>${q.cells_different ?? 0}</b><span>فرق بين القيمة المخزّنة والأصلية</span></div>
   <div class="stat"><b>${q.quarantined_releases}</b><span>إصدار في الحجر (بانتظار مراجعة)</span></div>
   <div class="stat"><b>${rc.reviewed || 0}</b><span>تخطيطاً مراجَعاً من ${(rc.reviewed || 0) + (rc.draft || 0) + (rc.pending_review || 0)}</span></div></div>
  <div class="card"><h3>الفحوص التي يجتازها كل جدول قبل نشره</h3><ul style="margin:6px 0 0;padding-inline-start:20px"><li>كل القيم أرقام صالحة ولكل قيمة فترة زمنية، ولا تكرار في المفاتيح.</li><li>فحص النطاق حسب نوع القياس: نسب بين 0 و100، أرقام قياسية ضمن حدود معقولة.</li><li>مجموع المكوّنات يساوي الإجمالي، ومجموع التوزيعات 100 أو 1، والأب يساوي مجموع أبنائه.</li><li>الوحدة ونوع القياس معروفان. غير المعروف يُوقَف للمراجعة ولا يُنشر.</li><li>تخطيط جدول لم يُرَ من قبل يُحجَر ويصل تنبيه بريدي.</li><li>مقارنة كل قيمة مخزّنة بخليتها الأصلية في ملف الإكسل (النتيجة أعلاه).</li>${q.insights_check && q.insights_check.cells ? `<li>اختبار الاستنتاجات: ${q.insights_check.cells.toLocaleString("en-US")} خلية أُعيدت قراءتها، ${q.insights_check.changes} تغيّراً أُعيد حسابه، ${q.insights_check.consistency} مقارنة بين جدولين، والأخطاء: ${q.insights_check.failures}.</li>` : ""}</ul></div>
  <h3 style="margin-top:20px">الإصدارات المستوردة</h3>
  ${table(["الإصدار", "التاريخ", "جداول", "قيم", "قيم قورنت بالأصل", "فروق", "في الحجر"], q.releases.map(r => `<tr><td>${tx(r.title_ar)}</td><td>${dlabel(r.release_date)}</td><td class="num">${r.datasets}</td><td class="num">${r.values.toLocaleString("en-US")}</td><td class="num">${r.cells_checked != null ? r.cells_checked.toLocaleString("en-US") : ""}</td><td class="num">${r.cells_different ?? ""}</td><td class="num">${r.quarantined}</td></tr>`))}
  <h3 style="margin-top:20px">ملاحظات ومسائل مفتوحة</h3>
  ${q.known_issues.map(i => `<div class="card issue ${i.severity}"><div class="row spread"><b>${tx(i.title_ar)}</b>${chip(...(SEV[i.severity] || ["", ""]))}</div><p style="margin:6px 0 0">${tx(i.detail_ar)}</p></div>`).join("")}
  <h3 style="margin-top:20px">تعديلات الهيئة على قيم نُشرت سابقاً</h3>
  <p class="muted">${q.revisions_total} تعديلاً مسجّلاً. لا تُستبدل قيمة بصمت، وكل تغيير يُسجَّل بالقيمة القديمة والجديدة.</p>
  ${q.revisions.length ? table(["الجدول", "الفترة", "البند", "القيمة القديمة", "القيمة الجديدة"], q.revisions.slice(-15).reverse().map(r => `<tr><td>${tx(r.dataset_id)}</td><td>${tx(r.period)}</td><td>${tx(r.row)}${r.col ? " | " + tx(r.col) : ""}</td><td class="num">${fmt(r.old_value)}</td><td class="num">${fmt(r.new_value)}</td></tr>`)) : ""}`;
}

/* ---------------------------------------------------------------- router */
const routes = { home, explore, fresh, quality };
async function route() {
  const raw = location.hash.replace(/^#\/?/, ""); const [name, qs] = raw.split("?");
  const key = routes[name] ? name : "home";
  const params = Object.fromEntries(new URLSearchParams(qs || ""));
  document.querySelectorAll("#nav a").forEach(a => a.toggleAttribute("aria-current", a.dataset.r === key) || a.removeAttribute("aria-current"));
  document.querySelectorAll("#nav a").forEach(a => { if (a.dataset.r === key) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
  try { await routes[key](params); } catch (e) { app.innerHTML = `<div class="card"><b>تعذّر تحميل البيانات.</b><p class="muted">${esc(e.message)}. حاول مرة أخرى بعد قليل.</p></div>`; }
  window.scrollTo(0, 0);
  try { const m = await get("latest.json"); $("#stamp").textContent = `آخر تحديث للبيانات: ${m.generated_at.slice(0, 10)}`; } catch (e) { /* stamp is optional */ }
}
addEventListener("hashchange", route);
route();
