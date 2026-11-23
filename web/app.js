"use strict";
const el = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
let TERAI = new Set(["Chitwan", "Rupandehi", "Morang", "Sunsari", "Jhapa", "Kailali", "Banke", "Makwanpur"]);
const VALLEY = new Set(["Kathmandu", "Lalitpur", "Bhaktapur"]);
const SQFT = { ropani: 5476, aana: 342.25, paisa: 85.5625, dam: 21.390625, bigha: 72900, kattha: 3645, dhur: 182.25 };

// Nepali number style: crore / lakh.
function npr(v, digits = 2) {
  if (v >= 1e7) return `Rs ${(v / 1e7).toFixed(digits).replace(/\.?0+$/, "")} crore`;
  if (v >= 1e5) return `Rs ${(v / 1e5).toFixed(digits - 1 < 0 ? 0 : digits - 1).replace(/\.?0+$/, "")} lakh`;
  return "Rs " + Math.round(v).toLocaleString("en-IN");
}
const nprShort = v => v >= 1e7 ? (v / 1e7).toFixed(1).replace(/\.0$/, "") + " Cr" : v >= 1e5 ? (v / 1e5).toFixed(v < 1e6 ? 1 : 0).replace(/\.0$/, "") + " L" : Math.round(v / 1e3) + "K";

const tip = el("tooltip");
function showTip(e, title, rows) {
  tip.innerHTML = `<b>${esc(title)}</b>` + rows.map(([k, v]) => `<div class="row"><span>${esc(k)}</span><span>${esc(v)}</span></div>`).join("");
  tip.hidden = false;
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = e.clientX + 14, y = e.clientY + 14;
  if (x + w > innerWidth - 8) x = e.clientX - w - 14;
  if (y + h > innerHeight - 8) y = e.clientY - h - 14;
  tip.style.left = Math.max(8, x) + "px"; tip.style.top = Math.max(8, y) + "px";
}
function bindTips(svg, lookup) {
  svg.querySelectorAll("[data-tip]").forEach(n => {
    n.addEventListener("pointermove", e => { const t = lookup(n.dataset.tip); showTip(e, t.title, t.rows); });
    n.addEventListener("pointerleave", () => { tip.hidden = true; });
  });
}
function hbar(x, y, w, h, r = 4) {
  w = Math.max(w, 1); r = Math.min(r, w, h / 2);
  return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
}
const median = a => { const s = [...a].sort((x, y) => x - y), m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };

let M, L_;
const state = { type: "House", district: "Kathmandu", locality: "", road_ft: 13, storeys: 2.5 };
Promise.all([fetch("model.json").then(r => r.json()), fetch("listings.json").then(r => r.json())]).then(([m, l]) => { M = m; L_ = l; init(); });

function init() {
  if (M.terai) TERAI = new Set(M.terai);
  renderKPIs();
  chips("type", ["House", "Land"], state.type, v => { state.type = v; el("storey-field").hidden = v !== "House"; update(); renderMarket(); });
  const dcounts = {};
  L_.forEach(r => { dcounts[r.district] = (dcounts[r.district] || 0) + 1; });
  const districts = M.districts.filter(d => d !== "Other" && (dcounts[d] || 0) >= 5).sort((a, b) => dcounts[b] - dcounts[a]);
  const opt = d => `<option value="${esc(d)}"${d === state.district ? " selected" : ""}>${esc(d)} (${dcounts[d].toLocaleString("en-IN")})</option>`;
  el("district").innerHTML = `<optgroup label="Kathmandu Valley">${districts.filter(d => VALLEY.has(d)).map(opt).join("")}</optgroup>` +
    `<optgroup label="Outside the Valley">${districts.filter(d => !VALLEY.has(d)).map(opt).join("")}</optgroup>`;
  el("district").addEventListener("change", e => { state.district = e.target.value; fillLocalities(); toggleUnits(); update(); });
  fillLocalities(); toggleUnits();
  el("locality").addEventListener("change", e => { state.locality = e.target.value; update(); });
  document.querySelectorAll(".area-inputs input").forEach(i => i.addEventListener("input", update));
  el("road").addEventListener("input", e => { state.road_ft = +e.target.value; el("road-o").textContent = e.target.value + " ft"; update(); });
  el("storeys").addEventListener("input", e => { state.storeys = +e.target.value; el("st-o").textContent = e.target.value; update(); });
  chips("mkt-type", ["House", "Land"], "House", v => { mktType = v; renderMarket(); });
  chips("mkt-region", ["All of Nepal", "Kathmandu Valley", "Outside the Valley"], mktRegion, v => { mktRegion = v; renderMarket(); });
  chips("hot-type", ["Land", "House"], hotType, v => { hotType = v; renderHotspots(); });
  document.querySelectorAll("[data-table-toggle]").forEach(btn => btn.addEventListener("click", () => {
    const t = el(btn.dataset.tableToggle + "-table"); t.hidden = !t.hidden; btn.textContent = t.hidden ? "Show table" : "Hide table";
  }));
  renderAbout();
  update(); renderMarket(); renderHotspots(); initMap();
  let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => { update(); renderMarket(); renderHotspots(); }, 120); });
}

function chips(id, values, current, onPick) {
  const box = el(id);
  box.innerHTML = values.map(v => `<button class="chip" role="radio" data-v="${esc(v)}" aria-checked="${v === current}">${esc(v)}</button>`).join("");
  box.addEventListener("click", e => {
    const b = e.target.closest(".chip"); if (!b) return;
    box.querySelectorAll(".chip").forEach(c => c.setAttribute("aria-checked", c === b));
    onPick(b.dataset.v);
  });
}
function fillLocalities() {
  const locs = M.localities.filter(l => l.district === state.district).sort((a, b) => a.name.localeCompare(b.name));
  if (!el("district").value) el("district").value = state.district;
  el("locality").innerHTML = `<option value="">Anywhere in ${esc(state.district)}</option>` +
    locs.map(l => `<option value="${esc(l.name)}">${esc(l.name)} (${l.n} listings)</option>`).join("");
  state.locality = "";
}
function toggleUnits() {
  const terai = TERAI.has(state.district);
  el("area-rapd").hidden = terai; el("area-bkd").hidden = !terai;
}
function areaAana() {
  const n = id => Math.max(0, parseFloat(el(id).value) || 0);
  const sqft = TERAI.has(state.district)
    ? n("b-b") * SQFT.bigha + n("b-k") * SQFT.kattha + n("b-d") * SQFT.dhur
    : n("a-r") * SQFT.ropani + n("a-a") * SQFT.aana + n("a-p") * SQFT.paisa + n("a-d") * SQFT.dam;
  return sqft / SQFT.aana;
}

function renderKPIs() {
  const sources = Object.keys(M.sources).length;
  const years = Object.keys(M.years).map(Number);
  el("lead-n").textContent = M.n.toLocaleString("en-IN");
  const kv = [
    ["Listings analysed", M.n.toLocaleString("en-IN"), `from ${sources} listing sites`],
    ["Areas covered", M.localities.length, `across ${M.districts.filter(d => d !== "Other").length} districts`],
    ["Listing years", `${Math.min(...years)}–${Math.max(...years)}`, `estimates at ${M.latest_year} levels`],
    ["Typical error", `±${M.cv.median_abs_pct_err}%`, "median, on held-out listings"],
  ];
  el("kpis").innerHTML = kv.map(([l, v, n]) => `<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div><div class="note">${n}</div></div>`).join("");
  el("sources").innerHTML = "Data: public listings from " + Object.entries(M.sources).map(([s, n]) => `<a href="https://${esc(s)}">${esc(s)}</a> (${n.toLocaleString("en-IN")})`).join(", ") + `. Refreshed automatically from each site's sitemap within its robots.txt rules; last update ${esc(M.collected || "October 2026")}. No personal data is stored.`;
}

function update() {
  const aana = areaAana();
  el("area-hint").textContent = aana > 0 ? `${aana.toFixed(2)} aana · ${Math.round(aana * SQFT.aana).toLocaleString("en-IN")} sq ft` : "Enter the land area";
  if (!(aana > 0.25)) { el("price").textContent = "–"; el("meta").innerHTML = ""; el("range-chart").innerHTML = ""; el("comps").innerHTML = ""; return; }
  const x = { type: state.type, district: state.district, locality: state.locality, area_aana: aana, road_ft: state.road_ft, storeys: state.type === "House" ? state.storeys : null };
  const p = predictPrice(M, x);
  el("price").textContent = npr(p.price);
  el("meta").innerHTML = `<span>Likely range <strong>${nprShort(p.low)} – ${nprShort(p.high)}</strong></span><span><strong>${npr(p.price / aana)}</strong> per aana</span>`;
  renderRange(p);
  renderComps(x, p.price);
}

function renderRange(p) {
  const host = el("range-chart"), W = Math.max(300, host.clientWidth), H = 64, m = { l: 8, r: 8 };
  const lo = p.low * 0.85, hi = p.high * 1.1, x = v => m.l + ((v - lo) / (hi - lo)) * (W - m.l - m.r);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Likely price range">`;
  s += `<rect x="${x(p.low)}" y="18" width="${x(p.high) - x(p.low)}" height="14" rx="4" fill="var(--accent-wash)"/>`;
  s += `<rect x="${x(p.q1)}" y="18" width="${x(p.q3) - x(p.q1)}" height="14" rx="4" fill="var(--accent)" opacity=".35"/>`;
  s += `<circle cx="${x(p.price)}" cy="25" r="7" fill="var(--accent)" class="dot"/>`;
  s += `<text class="tick" x="${x(p.low)}" y="50" text-anchor="middle">${nprShort(p.low)}</text><text class="tick" x="${x(p.high)}" y="50" text-anchor="middle">${nprShort(p.high)}</text>`;
  s += `<text class="tick" x="${x(p.low)}" y="12">Likely range (80%); darker band = middle 50%</text></svg>`;
  host.innerHTML = s;
}

function renderComps(x, est) {
  const score = r => (r.type === x.type ? 0 : 3) + (r.locality && r.locality === x.locality ? 0 : r.district === x.district ? 1 : 3) + Math.abs(Math.log(r.area / x.area_aana)) * 2 + (M.latest_year - r.year) * 0.15;
  const comps = L_.filter(r => r.district === x.district).sort((a, b) => score(a) - score(b)).slice(0, 5);
  el("comps").innerHTML = comps.map(r => `
    <a class="comp" href="${esc(r.url)}" target="_blank" rel="noopener noreferrer">
      <span class="t">${esc(r.title)}</span><span class="p">${nprShort(r.price)}</span>
      <span class="m">${esc(r.type)} · ${r.area.toFixed(1)} aana · ${esc([r.locality, r.district].filter(Boolean).join(", "))}<span class="badge">${esc(r.source.replace(/\.com.*/, ""))} ${r.year}</span></span>
      <span class="m r">${nprShort(r.price / r.area)}/aana</span>
    </a>`).join("") || `<p class="sub">No listings in this district yet.</p>`;
}

let mktType = "House", mktRegion = "All of Nepal", hotType = "Land";
const inRegion = r => mktRegion === "All of Nepal" || (mktRegion === "Kathmandu Valley") === VALLEY.has(r.district);
function renderMarket() {
  const groups = {};
  L_.filter(r => r.type === mktType && r.locality && inRegion(r)).forEach(r => { const k = r.locality + " | " + r.district; (groups[k] = groups[k] || []).push(r.price / r.area); });
  const rows = Object.entries(groups).filter(([, v]) => v.length >= 4)
    .map(([k, v]) => ({ loc: k.split(" | ")[0], dist: k.split(" | ")[1], med: median(v), n: v.length }))
    .sort((a, b) => b.med - a.med).slice(0, 20);
  const host = el("mkt-chart");
  if (!rows.length) { host.innerHTML = `<p class="sub">Not enough ${mktType.toLowerCase()} listings per area yet.</p>`; el("mkt-table").innerHTML = ""; return; }
  const W = Math.max(300, host.clientWidth), labelW = Math.min(190, W * 0.4), rowH = 26, barH = 14, H = rows.length * rowH + 24;
  const max = Math.max(...rows.map(r => r.med)) * 1.12, x = v => labelW + (v / max) * (W - labelW - 60);
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Median price per aana by area">`;
  const narrow = W < 520;
  const step = [1e6, 2e6, 5e6, 1e7, 2e7, 5e7].find(st => max / st <= (narrow ? 3 : 6));
  for (let t = 0; t <= max; t += step) s += `<line class="gridline" x1="${x(t)}" x2="${x(t)}" y1="0" y2="${H - 20}"/><text class="tick" x="${x(t)}" y="${H - 6}" text-anchor="middle">${t ? nprShort(t) : "0"}</text>`;
  rows.forEach((r, i) => {
    const y = i * rowH + 5;
    s += `<text class="lbl" x="${labelW - 8}" y="${y + barH / 2 + 4}" text-anchor="end">${esc(narrow ? r.loc : r.loc + ", " + r.dist)}</text>`;
    s += `<path d="${hbar(labelW, y, x(r.med) - labelW, barH)}" fill="var(--accent)"/>`;
    s += `<text class="val" x="${x(r.med) + 6}" y="${y + barH / 2 + 4}">${nprShort(r.med)}</text>`;
    s += `<rect class="hit" data-tip="${i}" x="0" y="${y - 6}" width="${W}" height="${rowH}"/>`;
  });
  s += `<line class="baseline" x1="${labelW}" x2="${labelW}" y1="0" y2="${H - 20}"/></svg>`;
  host.innerHTML = s;
  bindTips(host.querySelector("svg"), i => ({ title: `${rows[i].loc}, ${rows[i].dist}`, rows: [["Median per aana", npr(rows[i].med)], ["Listings", rows[i].n]] }));
  el("mkt-table").innerHTML = `<table><thead><tr><th>Area</th><th>District</th><th class="n">Median per aana</th><th class="n">Listings</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td>${esc(r.loc)}</td><td>${esc(r.dist)}</td><td class="n">${npr(r.med)}</td><td class="n">${r.n}</td></tr>`).join("") + "</tbody></table>";
}

function renderAbout() {
  el("about-text").innerHTML = `A hedonic regression on the log of asking price, the standard approach for property valuation. It uses property type, land area, district, locality (shrunk toward its district when listings are few), road width, storeys and listing year, and estimates are given at ${M.latest_year} price levels. In 5-fold cross-validation it explains ${Math.round(M.cv.r2_log * 100)}% of the variation in log price (gradient boosting: ${Math.round(M.cv_gboost.r2_log * 100)}%, median error ${M.cv_gboost.median_abs_pct_err}%), so the simpler, explainable model was kept.`;
  const c = M.cv, g = M.cv_gboost;
  const tiles = [
    ["Median error", `${c.median_abs_pct_err}%`, "on held-out listings (5-fold CV)"],
    ["Within ±25%", `${c.within_25pct}%`, "of held-out listings"],
    ["R² (log price)", c.r2_log.toFixed(2), `gradient boosting: ${g.r2_log.toFixed(2)}`],
    ["Training listings", M.n.toLocaleString("en-IN"), "after cleaning and outlier removal"],
  ];
  el("model-stats").innerHTML = tiles.map(([l, v, n]) => `<div class="kpi"><div class="label">${l}</div><div class="value">${v}</div><div class="note">${n}</div></div>`).join("");
}

// Towns outside the Kathmandu Valley: median asking price per aana from recent listings,
// with the change against the 2021–23 listings where both periods have enough data.
function renderHotspots() {
  const recentFrom = M.latest_year - 1, MIN = 5;
  const groups = {};
  L_.filter(r => r.city && !VALLEY.has(r.district)).forEach(r => {
    const g = groups[r.city] = groups[r.city] || { city: r.city, dist: r.district, land: [], house: [], landOld: [], houseOld: [], n: 0 };
    g.n++;
    const v = r.price / r.area, recent = r.year >= recentFrom, old = r.year <= 2023;
    if (r.type === "Land") (recent ? g.land : old ? g.landOld : []).push(v);
    else (recent ? g.house : old ? g.houseOld : []).push(v);
  });
  const key = hotType === "Land" ? "land" : "house";
  // Fall back to all years when a town has too few recent listings.
  const all = g => g[key].length >= MIN ? g[key] : g[key].concat(g[key + "Old"]);
  const rows = Object.values(groups).map(g => {
    const vals = all(g), recent = g[key].length >= MIN;
    const chg = recent && g[key + "Old"].length >= 4 ? median(g[key]) / median(g[key + "Old"]) - 1 : null;
    return { ...g, vals, med: vals.length ? median(vals) : 0, k: vals.length, recent, chg };
  }).filter(r => r.k >= MIN).sort((a, b) => b.med - a.med).slice(0, 20);
  el("hot-sub").textContent = `Median asking ${hotType === "Land" ? "land" : "house"} price per aana in towns with at least ${MIN} listings. Recent = ${recentFrom}–${M.latest_year}; towns marked * use all years.`;
  const host = el("hot-chart");
  if (!rows.length) { host.innerHTML = `<p class="sub">Not enough ${hotType.toLowerCase()} listings per town yet.</p>`; el("hot-table").innerHTML = ""; el("hot-insight").hidden = true; return; }
  const W = Math.max(300, host.clientWidth), labelW = Math.min(170, W * 0.38), rowH = 26, barH = 14, H = rows.length * rowH + 24;
  const max = Math.max(...rows.map(r => r.med)) * 1.15, x = v => labelW + (v / max) * (W - labelW - 60);
  const narrow = W < 520;
  const step = [1e5, 2e5, 5e5, 1e6, 2e6, 5e6, 1e7].find(st => max / st <= (narrow ? 3 : 6));
  let s = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Median price per aana by town outside the Kathmandu Valley">`;
  for (let t = 0; t <= max; t += step) s += `<line class="gridline" x1="${x(t)}" x2="${x(t)}" y1="0" y2="${H - 20}"/><text class="tick" x="${x(t)}" y="${H - 6}" text-anchor="middle">${t ? nprShort(t) : "0"}</text>`;
  rows.forEach((r, i) => {
    const y = i * rowH + 5;
    s += `<text class="lbl" x="${labelW - 8}" y="${y + barH / 2 + 4}" text-anchor="end">${esc((narrow ? r.city : r.city + ", " + r.dist) + (r.recent ? "" : " *"))}</text>`;
    s += `<path d="${hbar(labelW, y, x(r.med) - labelW, barH)}" fill="var(--accent)"${r.recent ? "" : ' opacity=".55"'}/>`;
    s += `<text class="val" x="${x(r.med) + 6}" y="${y + barH / 2 + 4}">${nprShort(r.med)}</text>`;
    s += `<rect class="hit" data-tip="${i}" x="0" y="${y - 6}" width="${W}" height="${rowH}"/>`;
  });
  s += `<line class="baseline" x1="${labelW}" x2="${labelW}" y1="0" y2="${H - 20}"/></svg>`;
  host.innerHTML = s;
  const pct = c => c == null ? "–" : (c >= 0 ? "+" : "−") + Math.abs(Math.round(c * 100)) + "%";
  bindTips(host.querySelector("svg"), i => ({ title: `${rows[i].city}, ${rows[i].dist}`, rows: [["Median per aana", npr(rows[i].med)], ["Listings used", rows[i].k + (rows[i].recent ? ` (${recentFrom}–${M.latest_year})` : " (all years)")], ["vs 2021–23", pct(rows[i].chg)]] }));
  const top = rows.filter(r => r.recent).slice(0, 3).map(r => r.city);
  const up = rows.filter(r => r.chg != null).sort((a, b) => b.chg - a.chg)[0];
  el("hot-insight").hidden = !top.length;
  el("hot-insight").textContent = top.length ? `Priciest ${hotType.toLowerCase()} outside the Valley right now: ${top.join(", ")}.` + (up ? ` Biggest rise since 2021–23: ${up.city} (${pct(up.chg)}).` : "") : "";
  el("hot-table").innerHTML = `<table><thead><tr><th>Town</th><th>District</th><th class="n">Median per aana</th><th class="n">Listings</th><th class="n">vs 2021–23</th></tr></thead><tbody>` +
    rows.map(r => `<tr><td>${esc(r.city)}${r.recent ? "" : " *"}</td><td>${esc(r.dist)}</td><td class="n">${npr(r.med)}</td><td class="n">${r.k}</td><td class="n">${pct(r.chg)}</td></tr>`).join("") + "</tbody></table>";
}

// ---- Map: price per aana by area (bubbles) and where listings cluster (heatmap) ----
const mapState = { type: "Land", layer: "Price per aana", period: "Last 2 years" };
let MAP, mapLayer;
const dark = () => document.documentElement.dataset.theme === "dark" ||
  (document.documentElement.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
// One-hue sequential ramp, light -> dark on a light map; reversed on a dark map so "more" is always more contrast.
const RAMP_LIGHT = ["#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#104281"];
const RAMP_DARK = ["#184f95", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"];

function initMap() {
  if (typeof L === "undefined" || !L_.map) { el("map").innerHTML = `<p class="sub" style="padding:16px">The map could not load.</p>`; return; }
  MAP = L.map("map", { scrollWheelZoom: false, zoomSnap: 0.5 }).setView([28.2, 84.1], 7);
  MAP.fitBounds([[26.35, 80.06], [30.45, 88.2]]);
  L.tileLayer(`https://{s}.basemaps.cartocdn.com/${dark() ? "dark_all" : "light_all"}/{z}/{x}/{y}{r}.png`, {
    maxZoom: 17, subdomains: "abcd",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
  }).addTo(MAP);
  chips("map-type", ["Land", "House"], mapState.type, v => { mapState.type = v; renderMap(); });
  chips("map-layer", ["Price per aana", "Listing heatmap"], mapState.layer, v => { mapState.layer = v; renderMap(); });
  chips("map-period", ["Last 2 years", "All years"], mapState.period, v => { mapState.period = v; renderMap(); });
  renderMap();
}

function mapRows() {
  const from = mapState.period === "All years" ? 0 : M.latest_year - 1;
  return L_.filter(r => r.type === mapState.type && r.year >= from && r.lat != null);
}

function renderMap() {
  if (!MAP) return;
  if (mapLayer) { MAP.removeLayer(mapLayer); mapLayer = null; }
  const rows = mapRows(), legend = el("map-legend");
  if (mapState.layer === "Listing heatmap") {
    // District-centre points would create false hot spots, so only pins, localities and towns.
    const pts = rows.filter(r => r.geo !== "district").map(r => [r.lat, r.lon, 1]);
    mapLayer = L.heatLayer(pts, { radius: 18, blur: 22, maxZoom: 12, minOpacity: 0.25,
      gradient: dark() ? { 0.3: "#184f95", 0.6: "#3987e5", 1: "#cde2fb" } : { 0.3: "#9ec5f4", 0.6: "#3987e5", 1: "#0d366b" } }).addTo(MAP);
    legend.innerHTML = `<span class="key">Fewer listings</span><span class="ramp">${(dark() ? RAMP_DARK : RAMP_LIGHT).map(c => `<span style="background:${c}"></span>`).join("")}</span><span class="key">More listings</span>`;
    el("map-note").textContent = `${pts.length.toLocaleString("en-IN")} ${mapState.type.toLowerCase()} listings placed by map pin, locality or town.`;
    return;
  }
  // Group by area: locality where known, else town, else district.
  const groups = {};
  rows.forEach(r => {
    const name = r.geo === "district" ? r.district : (r.geo === "town" ? r.city : r.locality) || r.district;
    const k = name + "|" + r.district;
    const g = groups[k] = groups[k] || { name, dist: r.district, v: [], lat: [], lon: [], level: r.geo };
    g.v.push(r.price / r.area); g.lat.push(r.lat); g.lon.push(r.lon);
  });
  const areas = Object.values(groups).filter(g => g.v.length >= 3).map(g => ({ ...g, med: median(g.v), n: g.v.length, la: median(g.lat), lo: median(g.lon) }));
  if (!areas.length) { legend.innerHTML = ""; el("map-note").textContent = "Not enough listings for this selection."; return; }
  // Quintile bins so every shade is used whatever the price range.
  const sorted = areas.map(a => a.med).sort((a, b) => a - b);
  const cuts = [0.2, 0.4, 0.6, 0.8].map(q => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))]);
  const ramp = dark() ? RAMP_DARK : RAMP_LIGHT, ring = getComputedStyle(document.documentElement).getPropertyValue("--raised").trim() || "#fff";
  const bin = v => cuts.filter(c => v >= c).length;
  const maxN = Math.max(...areas.map(a => a.n));
  mapLayer = L.layerGroup(areas.sort((a, b) => b.n - a.n).map(a => {
    const m = L.circleMarker([a.la, a.lo], { radius: 5 + 11 * Math.sqrt(a.n / maxN), color: ring, weight: 2, fillColor: ramp[bin(a.med)], fillOpacity: 0.9 });
    m.bindTooltip(`<b>${esc(a.name)}${a.name !== a.dist ? ", " + esc(a.dist) : ""}</b><div class="row"><span>Median per aana</span><span>${npr(a.med)}</span></div><div class="row"><span>${esc(mapState.type)} listings</span><span>${a.n}</span></div>`, { className: "map-tip", direction: "top", offset: [0, -4] });
    return m;
  })).addTo(MAP);
  const edges = [sorted[0], ...cuts, sorted[sorted.length - 1]];
  legend.innerHTML = `<span class="key">Median asking price per aana</span>` + ramp.map((c, i) =>
    `<span class="lbl-row"><span class="sw" style="background:${c}"></span>${nprShort(edges[i])}–${nprShort(edges[i + 1])}</span>`).join("");
  el("map-note").textContent = `${areas.length} areas with at least 3 ${mapState.type.toLowerCase()} listings. Areas are placed at the listings' map pins where the site publishes them, otherwise at the locality or town centre.`;
}
