import { lineChart, divergingBars, hBars, fmt } from "/static/charts.js";
import { T, lang, applyStatic, CAT, SHOCKS_EN, METRICS_EN, SECTORS_EN, INSTRUMENTS_EN, FLOWS_EN, LOCALE } from "/static/i18n.js";
import { renderSensitivity, renderData, renderChain } from "/static/insights.js";
import { initPolicy, relabelPolicy } from "/static/policy.js";

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const DIMS = ["issuance", "channel", "banking", "money", "privacy", "fiscal"];
const DEFAULT = { issuance: "discretionary", channel: "banks", banking: "fractional", money: "normal", privacy: "mixed", fiscal: "free" };
const BASE_KEY = DIMS.map((d) => DEFAULT[d]).join("|");
const COLORS = ["var(--s1)", "var(--s2)", "var(--s3)"];

const PRESETS = [
  { key: BASE_KEY, es: "Sistema actual (BCE)", en: "Today's system (ECB)" },
  { key: "gold|banks|fractional", es: "Patrón oro clásico", en: "Classical gold standard" },
  { key: "fixed_supply|miners|fractional", es: "Bitcoin como moneda (con banca)", en: "Bitcoin as currency (with banks)" },
  { key: "fixed_supply|miners|full_reserve|normal|anonymous|balanced", es: "Bitcoin libertario (sin banca fraccionaria, anónimo, sin déficit)", en: "Libertarian Bitcoin (full reserve, anonymous, no deficit)" },
  { key: "rule_2pct|government|full_reserve", es: "Chicago Plan (Benes y Kumhof)", en: "Chicago Plan (Benes & Kumhof)" },
  { key: "discretionary|dividend|fractional", es: "«QE para la gente»", en: "“QE for the people”" },
  { key: "discretionary|banks|fractional|cbdc|traceable|free", es: "Euro digital (diseño BCE)", en: "Digital euro (ECB design)" },
  { key: "discretionary|banks|fractional|demurrage", es: "Dinero que se oxida (Gesell)", en: "Demurrage money (Gesell)" },
  { key: "rule_2pct|dividend|full_reserve|cbdc|traceable|free", es: "Dinero algorítmico público + dividendo + euro digital", en: "Public algorithmic money + dividend + digital euro" },
];

const SUMMARY_INFO = {
  "inflation:mean": { es: "Inflación media", en: "Average inflation", kind: "pct", better: "target" },
  "unemployment:mean": { es: "Paro medio", en: "Average unemployment", kind: "pct", better: "low" },
  "unemployment:max": { es: "Paro máximo", en: "Peak unemployment", kind: "pct", better: "low" },
  "real_gdp:min": { es: "PIB real mínimo", en: "Real GDP trough", kind: "idx", better: "high", note: ["inicio = 100", "start = 100"] },
  "real_wage:last": { es: "Salario real final", en: "Final real wage", kind: "idx", better: "high", note: ["inicio = 100", "start = 100"] },
  "gini_wealth:delta": { es: "Δ Gini de la riqueza", en: "Δ wealth Gini", kind: "dsign", better: "low" },
  "top10_wealth:delta": { es: "Δ cuota del 10 % más rico", en: "Δ share of the richest 10 %", kind: "pp", better: "low" },
  "house_price_real:last": { es: "Vivienda (precio real)", en: "Housing (real price)", kind: "idx", better: null, note: ["inicio = 100", "start = 100"] },
  "price_to_income:last": { es: "Años de salario por vivienda", en: "Years of salary per home", kind: "x", better: "low" },
  "real_gdp:last": { es: "PIB real final", en: "Final real GDP", kind: "idx", better: "high", note: ["inicio = 100", "start = 100"] },
  "debt_gdp:last": { es: "Deuda pública / PIB", en: "Public debt / GDP", kind: "pct", better: "low" },
  "tax_gap:mean": { es: "Impuestos evadidos (% PIB)", en: "Evaded taxes (% GDP)", kind: "pct", better: "low" },
  "foreclosures:last": { es: "Ejecuciones hipotecarias", en: "Foreclosures", kind: "pct", better: "low" },
  "stock_index:last": { es: "Bolsa (valor real)", en: "Stock market (real)", kind: "idx", better: null, note: ["inicio = 100", "start = 100"] },
  "bailouts:last": { es: "Rescates bancarios (% PIB)", en: "Bank bailouts (% GDP)", kind: "pct", better: "low" },
};
export const sumLabel = (k) => SUMMARY_INFO[k][lang()] || SUMMARY_INFO[k].es;

export const state = { catalog: null, regime: { ...DEFAULT }, grids: {}, busy: false, scenario: "none" };

// ----------------------------------------------------------------- textos
export const L = {
  dim: (d) => (lang() === "en" ? CAT[d].label : state.catalog.dimensions[d].label),
  help: (d) => (lang() === "en" ? CAT[d].help : state.catalog.dimensions[d].help),
  opt: (d, k, short = false) => (lang() === "en" ? CAT[d].options[k][short ? 1 : 0] : state.catalog.dimensions[d].options[k][short ? "short" : "label"]),
  desc: (d, k) => (lang() === "en" ? CAT[d].options[k][2] : state.catalog.dimensions[d].options[k].desc),
  shock: (k) => (lang() === "en" ? SHOCKS_EN[k][0] : state.catalog.shocks[k].label),
  shockDesc: (k) => (lang() === "en" ? SHOCKS_EN[k][1] : state.catalog.shocks[k].desc),
  metric: (k) => (lang() === "en" ? METRICS_EN[k] || state.catalog.metrics[k].label : state.catalog.metrics[k].label),
  sector: (k) => (lang() === "en" ? SECTORS_EN[k] : state.catalog.sectors[k]),
  instrument: (k, es) => (lang() === "en" ? INSTRUMENTS_EN[k] || es : es),
  flow: (p) => (lang() === "en" ? FLOWS_EN[p] || p : p),
};
export const regimeLabel = (r) => {
  const parts = ["issuance", "channel", "banking"].map((d) => L.opt(d, r[d], true));
  for (const d of ["money", "privacy", "fiscal"]) if (r[d] !== DEFAULT[d]) parts.push(L.opt(d, r[d], true));
  return parts.join(" · ");
};
const keyOf = (r) => DIMS.map((d) => r[d]).join("|");
export const fromKey = (k) => {
  const parts = k.split("|");
  return Object.fromEntries(DIMS.map((d, i) => [d, parts[i] || DEFAULT[d]]));
};
const fullKey = (k) => keyOf(fromKey(k));

export const sfmt = (key, v, d) => {
  const kind = SUMMARY_INFO[key]?.kind || "dec";
  if (kind === "dsign") return v == null ? "—" : `${v >= 0 ? "+" : ""}${fmt("dec", v)}`;
  return fmt(kind, v, d);
};
function score(key, v, ref) {
  const b = SUMMARY_INFO[key]?.better;
  if (!b || ref == null) return 0;
  if (b === "low") return ref - v;
  if (b === "high") return v - ref;
  return Math.abs(ref - 0.02) - Math.abs(v - 0.02);
}

export async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  const ct = r.headers.get("content-type") || "";
  return ct.includes("json") ? r.json() : r.text();
}

function setBusy(on, text) {
  state.busy = on;
  const pill = $("#run-pill");
  pill.classList.toggle("busy", on);
  pill.classList.toggle("ok", !on);
  $("#run-text").textContent = text || (on ? T("Simulando…", "Simulating…") : T("Listo", "Ready"));
  $("#run-btn").disabled = on;
  $("#cmp-btn").disabled = on;
}
function setSfc(err) {
  const p = $("#sfc-pill");
  p.classList.toggle("ok", err < 1e-9);
  p.title = `${T("Error contable máximo", "Max accounting error")}: ${err.toExponential(1)}`;
  $("span", p).textContent = err < 1e-9 ? T("Contabilidad cuadrada", "Books balance") : T("Descuadre contable", "Accounting error");
}

// ------------------------------------------------------------------ router
const VIEWS = ["lab", "policy", "compare", "explore", "sensitivity", "data", "chain", "method"];
function route() {
  const v = (location.hash.slice(1) || "lab").split("?")[0];
  const view = VIEWS.includes(v) ? v : v.startsWith("m-") ? "method" : "lab";
  $$(".view").forEach((s) => s.classList.toggle("active", s.id === `view-${view}`));
  $$(".mainnav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  if (view === "explore") loadGrid();
  if (view === "sensitivity") renderSensitivity();
  if (view === "data") renderData();
  if (view === "chain") renderChain();
  if (view === "method") renderMethodTables();
  if (v.startsWith("m-")) { document.getElementById(v)?.scrollIntoView(); return; }
  window.scrollTo({ top: 0 });
}

// --------------------------------------------------------------- builder
function renderBuilder() {
  const box = $("#builder");
  box.innerHTML = "";
  for (const dim of DIMS) {
    const d = state.catalog.dimensions[dim];
    const card = document.createElement("div");
    card.className = "card card-pad dim";
    card.innerHTML = `<h3>${L.dim(dim)}</h3><div class="help">${L.help(dim)}</div>
      <div class="opts" role="radiogroup" aria-label="${L.dim(dim)}">${Object.keys(d.options).map((k) =>
        `<button class="opt${state.regime[dim] === k ? " on" : ""}" role="radio" aria-checked="${state.regime[dim] === k}" data-dim="${dim}" data-k="${k}">${L.opt(dim, k, true)}</button>`).join("")}</div>
      <div class="desc"><b>${L.opt(dim, state.regime[dim])}.</b> ${L.desc(dim, state.regime[dim])}</div>`;
    box.appendChild(card);
  }
  $$(".opt", box).forEach((b) => b.addEventListener("click", () => {
    state.regime[b.dataset.dim] = b.dataset.k;
    syncPreset();
    renderBuilder();
  }));
}
function presetOptions(sel, current) {
  sel.innerHTML = `<option value="">${T("— Personalizado —", "— Custom —")}</option>` +
    PRESETS.map((p) => `<option value="${fullKey(p.key)}" ${fullKey(p.key) === current ? "selected" : ""}>${p[lang()]}</option>`).join("");
}
function syncPreset() {
  const k = keyOf(state.regime);
  presetOptions($("#preset"), k);
  $("#preset").value = PRESETS.some((p) => fullKey(p.key) === k) ? k : "";
}
function shockOptions(sel, value) {
  sel.innerHTML = Object.keys(state.catalog.shocks).map((k) => `<option value="${k}" ${k === value ? "selected" : ""}>${L.shock(k)}</option>`).join("");
}
function syncShockDesc() {
  const k = $("#p-shock").value;
  $("#shock-desc").textContent = k === "none" ? "" : `${L.shock(k)}: ${L.shockDesc(k)}`;
  $("#p-shock-month").disabled = k === "none";
}

const ADV = [
  ["inflation_target", "Objetivo de inflación", "Inflation target", 0.005],
  ["natural_unemployment", "Paro natural", "Natural unemployment", 0.01],
  ["productivity_growth", "Crecimiento productividad", "Productivity growth", 0.001],
  ["gov_spending_share", "Gasto público / PIB", "Public spending / GDP", 0.01],
  ["credibility", "Credibilidad de la regla", "Credibility of the rule", 0.01],
  ["money_rate_sens", "Sensibilidad del tipo al dinero", "Rate sensitivity to money", 0.01],
  ["spirits_sd", "Volatilidad de la confianza", "Volatility of confidence", 0.01],
  ["reserve_ratio", "Coeficiente de reservas", "Reserve requirement", 0.005],
  ["capital_ratio", "Capital bancario mínimo", "Minimum bank capital", 0.01],
  ["ltv", "LTV máximo hipotecas", "Maximum mortgage LTV", 0.05],
  ["demurrage_rate", "Oxidación mensual", "Monthly demurrage", 0.001],
  ["cbdc_limit", "Límite del euro digital (€)", "Digital euro limit (€)", 500],
  ["evasion_anonymous", "Evasión con anonimato", "Evasion if anonymous", 0.01],
  ["fixed_initial_issuance", "Emisión inicial (oferta fija)", "Initial issuance (fixed supply)", 0.001],
  ["shock_size", "Intensidad de la crisis", "Crisis intensity", 0.1],
];
function renderAdv() {
  const def = state.catalog.params;
  const prev = Object.fromEntries($$("#adv input").map((i) => [i.dataset.p, i.value]));
  $("#adv").innerHTML = ADV.map(([k, es, en, step]) =>
    `<label class="ctl">${T(es, en)}<input type="number" step="${step}" data-p="${k}" value="${prev[k] ?? def[k]}"></label>`).join("");
}
function readParams(shockSel = "#p-shock") {
  const out = { months: +$("#p-months").value, households: +$("#p-households").value,
                shock: $(shockSel).value, shock_month: +$("#p-shock-month").value };
  const def = state.catalog.params;
  $$("#adv input").forEach((i) => { if (i.value !== "" && +i.value !== def[i.dataset.p]) out[i.dataset.p] = +i.value; });
  return out;
}

// ------------------------------------------------------------------- lab
async function runLab() {
  if (state.busy) return;
  const t0 = performance.now();
  const seeds = +$("#p-seeds").value;
  setBusy(true, `${T("Simulando", "Simulating")} ${seeds} ${T("economías…", "economies…")}`);
  try {
    const res = await api("/api/simulate", { ...state.regime, seeds, params: readParams() });
    state.last = res;
    state.lastSecs = (performance.now() - t0) / 1000;
    renderLab();
    try { localStorage.setItem("msl-regime", keyOf(state.regime)); } catch (e) {}
  } catch (err) {
    $("#runinfo").innerHTML = `<span class="neg">Error: ${err.message}</span>`;
  } finally {
    setBusy(false);
  }
}

async function baselineSummary(scenario) {
  const g = await getGrid(scenario).catch(() => null);
  return g?.cells.find((c) => c.key === BASE_KEY)?.summary;
}

async function renderLab() {
  const res = state.last;
  if (!res) return;
  $("#lab-empty").hidden = true;
  $("#lab-results").hidden = false;
  setSfc(res.sfc_max_error);
  const p = res.params, shock = p.shock || "none";
  const r = res.regime;
  $("#runinfo").innerHTML = `
    <span><b>${regimeLabel(r)}</b>${shock !== "none" ? ` · ${L.shock(shock)}` : ""}</span>
    <span>${res.seeds} ${T("simulaciones", "runs")} × ${p.households.toLocaleString(LOCALE())} ${T("hogares", "households")} × ${p.months / 12} ${T("años", "years")}</span>
    <span>${(state.lastSecs || 0).toFixed(1)} s</span>
    <span class="check">✓ ${T("contabilidad cuadrada", "books balance")} (${T("error máx.", "max error")} ${res.sfc_max_error.toExponential(1)})</span>`;

  const isBase = keyOf(r) === BASE_KEY;
  const base = isBase ? null : await baselineSummary(shock);
  const keys = shock === "none" ? ["inflation:mean", "unemployment:mean", "real_wage:last", "gini_wealth:delta", "top10_wealth:delta", "house_price_real:last"]
    : ["inflation:mean", "unemployment:max", "real_gdp:min", "real_wage:last", "top10_wealth:delta", "debt_gdp:last"];
  $("#kpis").innerHTML = keys.map((k) => {
    const info = SUMMARY_INFO[k], s = res.summary[k];
    const sc = base ? score(k, s.p50, base[k]) : 0;
    const cls = Math.abs(sc) < 1e-3 ? "" : sc > 0 ? "good" : "bad";
    const note = info.note ? ` · ${T(...info.note)}` : "";
    return `<div class="card kpi"><div class="k">${sumLabel(k)}</div><div class="v ${cls}">${sfmt(k, s.p50)}</div>
      <div class="r">${base ? `${T("Sistema actual", "Today's system")}: ${sfmt(k, base[k])}` : `${T("Rango", "Range")}: ${sfmt(k, s.p10)} – ${sfmt(k, s.p90)}`}${note}</div></div>`;
  }).join("");

  renderGroups(res);
  const start = res.wealth_share_start, end = res.wealth_share_end;
  divergingBars($("#decile-chart"), {
    labels: start.map((_, i) => `D${i + 1}`),
    values: end.map((v, i) => v - start[i]),
    extra: { start, end, names: start.map((_, i) => `${T("Decil", "Decile")} ${i + 1} (${i * 10}–${(i + 1) * 10} %)`) },
    title: T("Variación de la cuota de riqueza por decil", "Change in wealth share by decile"),
  });
  const to = res.new_money_to;
  const created = (to.Bancos || 0) + (to.Estado || 0) + (to.Hogares || 0);
  const nd = $("#newmoney-deciles");
  $("#newmoney-dec-title").hidden = created < 1e-6;
  if (created < 1e-6) {
    $("#newmoney-sectors").innerHTML = `<p class="t2" style="font-size:13px">${T("En esta simulación no se ha creado dinero base nuevo: ", "No new base money was created in this run: ")}${r.issuance === "discretionary"
      ? T("con la regla discrecional el banco central solo compra activos (QE) cuando la inflación cae por debajo del objetivo o el paro se dispara, y no ha ocurrido. Todo el dinero nuevo lo han creado los bancos al prestar. Prueba con una crisis.",
          "under the discretionary rule the central bank only buys assets (QE) when inflation falls below target or unemployment spikes, and that did not happen. All new money was created by banks when lending. Try a crisis.")
      : T("la regla no ha emitido en este horizonte.", "the rule did not issue over this horizon.")}</p>`;
    nd.innerHTML = "";
  } else {
    hBars($("#newmoney-sectors"), { rows: [
      { label: T("Bancos", "Banks"), value: to.Bancos || 0, color: "var(--s1)" },
      { label: T("Estado", "Government"), value: to.Estado || 0, color: "var(--s2)" },
      { label: T("Hogares", "Households"), value: to.Hogares || 0, color: "var(--s3)" },
    ] });
    const dec = res.new_money_deciles, tot = dec.reduce((a, b) => a + b, 0);
    if (tot < 1e-6) nd.innerHTML = `<p class="muted" style="font-size:13px;margin-top:8px">${T("Con este canal el dinero nuevo no llega directamente a ningún hogar.", "With this channel new money does not reach any household directly.")}</p>`;
    else hBars(nd, { rows: dec.map((v, i) => ({ label: `D${i + 1}`, value: v / tot, color: "var(--s3)" })) });
  }
  renderAcct(res, $("#acct-tabs .on").dataset.t);
  const ev = res.events || [];
  $("#events-card").hidden = !ev.length;
  $("#events").innerHTML = ev.slice(0, 12).map((e) => `<div><span class="tag">${T("Año", "Year")} ${Math.floor(e.t / 12) + 1}</span><span>${eventText(e)}</span></div>`).join("");
}
function eventText(e) {
  if (lang() !== "en") return e.text;
  if (e.type === "shock") return `Crisis begins: ${e.text.split(": ").pop()}`;
  if (e.type === "austerity") return "The State cannot place its debt and cuts spending";
  if (e.type === "bailout") return e.text.replace("Rescate bancario de", "Bank bailout of").replace("del PIB", "of GDP");
  return e.text;
}

const GROUPS = {
  pe: { es: "Precios y empleo", en: "Prices & jobs", keys: ["inflation", "unemployment", "real_wage", "real_gdp"] },
  ineq: { es: "Desigualdad", en: "Inequality", keys: ["gini_wealth", "top10_wealth", "bottom50_wealth", "gini_income"] },
  house: { es: "Vivienda", en: "Housing", keys: ["house_price_real", "price_to_income", "homeownership", "rent_burden"] },
  money: { es: "Dinero y tipos", en: "Money & rates", keys: ["broad_money", "new_money", "policy_rate", "credit_gdp"] },
  state: { es: "Estado y privacidad", en: "State & privacy", keys: ["debt_gdp", "tax_gap", "demurrage", "cbdc_share"] },
  fin: { es: "Finanzas", en: "Finance", keys: ["stock_index", "foreclosures", "bank_capital", "bailouts"] },
};
let currentGroup = "pe";
function renderGroups(res) {
  const tabs = $("#group-tabs");
  tabs.innerHTML = Object.entries(GROUPS).map(([k, g]) => `<button data-g="${k}" class="${k === currentGroup ? "on" : ""}">${g[lang()]}</button>`).join("");
  $$("button", tabs).forEach((b) => b.addEventListener("click", () => { currentGroup = b.dataset.g; renderGroups(res); }));
  const box = $("#charts");
  box.innerHTML = "";
  const shockAt = res.params.shock && res.params.shock !== "none" ? res.params.shock_month : null;
  for (const key of GROUPS[currentGroup].keys) {
    const m = state.catalog.metrics[key];
    const card = document.createElement("div");
    card.className = "card chart-card";
    const ref = key === "inflation" ? res.params.inflation_target : key === "unemployment" ? res.params.natural_unemployment : null;
    const sub = m.fmt === "idx" ? T("Índice, inicio = 100", "Index, start = 100")
      : ref != null ? T(`Línea discontinua: ${key === "inflation" ? "objetivo" : "paro natural"}`, `Dashed line: ${key === "inflation" ? "target" : "natural rate"}`) : "&nbsp;";
    card.innerHTML = `<h4>${L.metric(key)}</h4><div class="sub">${sub}</div><div class="chart"></div>`;
    box.appendChild(card);
    lineChart($(".chart", card), { series: [{ name: L.metric(key), color: "var(--s1)", ...res.series[key] }], kind: m.fmt, ref, zero: m.fmt === "pct", marker: shockAt });
  }
}

function renderAcct(res, tab) {
  const box = $("#acct");
  const n = res.params.households;
  const loc = LOCALE();
  const k = (v) => (Math.abs(v) < 0.5 ? `<td class="zero">·</td>` : `<td class="${v < 0 ? "neg" : ""}">${(v / n / 1000).toLocaleString(loc, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>`);
  if (tab === "flows") {
    box.innerHTML = `<table class="data"><thead><tr><th>${T("Concepto", "Item")}</th><th>${T("De", "From")}</th><th>${T("A", "To")}</th><th>${T("€ por hogar", "€ per household")}</th></tr></thead><tbody>` +
      res.flows.slice(0, 22).map((f) => `<tr><td>${L.flow(f.purpose)}</td><td style="font-family:var(--sans)">${L.sector(f.from)}</td><td style="font-family:var(--sans)">${L.sector(f.to)}</td><td>${(f.amount / n).toLocaleString(loc, { maximumFractionDigits: 0 })}</td></tr>`).join("") +
      `</tbody></table>`;
    return;
  }
  const bs = res.balance_sheet;
  box.innerHTML = `<table class="data"><thead><tr><th>${T("Miles de € por hogar", "Thousand € per household")}</th>${bs.sectors.map((s) => `<th>${L.sector(s.key)}</th>`).join("")}<th>Σ</th></tr></thead><tbody>` +
    bs.rows.map((r) => `<tr class="${r.key === "net" ? "total" : ""}"><td>${L.instrument(r.key, r.label)}</td>${bs.sectors.map((s) => k(r[s.key])).join("")}${k(r.total)}</tr>`).join("") +
    `</tbody></table>`;
}

// --------------------------------------------------------------- compare
const slots = [
  { key: BASE_KEY },
  { key: fullKey("fixed_supply|miners|fractional") },
  { key: fullKey("rule_2pct|dividend|full_reserve|cbdc|traceable|free") },
];
function renderSlots() {
  $("#slots").innerHTML = slots.map((s, i) => {
    const r = fromKey(s.key);
    const sel = document.createElement("select");
    presetOptions(sel, s.key);
    return `<div class="card slot" style="--c:${COLORS[i]}">
      <h3><i></i>${T("Sistema", "System")} ${String.fromCharCode(65 + i)}</h3>
      <label class="ctl">${T("Conocido", "Known")}<select data-i="${i}" data-role="preset">${sel.innerHTML}</select></label>
      ${DIMS.map((d) => `<label class="ctl">${L.dim(d)}<select data-i="${i}" data-dim="${d}">${Object.keys(state.catalog.dimensions[d].options).map((k) => `<option value="${k}" ${r[d] === k ? "selected" : ""}>${L.opt(d, k)}</option>`).join("")}</select></label>`).join("")}
    </div>`;
  }).join("");
  $$("#slots select").forEach((sel) => sel.addEventListener("change", () => {
    const i = +sel.dataset.i;
    if (sel.dataset.role === "preset") { if (sel.value) slots[i].key = sel.value; }
    else { const r = fromKey(slots[i].key); r[sel.dataset.dim] = sel.value; slots[i].key = keyOf(r); }
    renderSlots();
  }));
}
let cmpMetric = "inflation";
async function runCompare() {
  if (state.busy) return;
  const params = readParams("#cmp-shock"), seeds = +$("#p-seeds").value;
  const out = [];
  try {
    for (let i = 0; i < slots.length; i++) {
      setBusy(true, `${T("Simulando sistema", "Simulating system")} ${String.fromCharCode(65 + i)}…`);
      out.push(await api("/api/simulate", { ...fromKey(slots[i].key), seeds, params }));
    }
    state.cmp = out;
    setSfc(Math.max(...out.map((r) => r.sfc_max_error)));
    renderCompare();
  } catch (err) {
    alert(`Error: ${err.message}`);
  } finally {
    setBusy(false);
  }
}
function renderCompare() {
  const res = state.cmp;
  if (!res) return;
  $("#cmp-results").hidden = false;
  const chips = Object.values(GROUPS).flatMap((g) => g.keys);
  $("#cmp-metrics").innerHTML = chips.map((k) => `<button class="opt${k === cmpMetric ? " on" : ""}" data-k="${k}">${L.metric(k)}</button>`).join("");
  $$("#cmp-metrics .opt").forEach((b) => b.addEventListener("click", () => { cmpMetric = b.dataset.k; renderCompare(); }));
  const m = state.catalog.metrics[cmpMetric];
  $("#cmp-title").textContent = L.metric(cmpMetric) + (m.fmt === "idx" ? T(" (inicio = 100)", " (start = 100)") : "");
  const shockAt = res[0].params.shock !== "none" ? res[0].params.shock_month : null;
  const name = (r, i) => `${String.fromCharCode(65 + i)} · ${regimeLabel(r.regime)}`;
  lineChart($("#cmp-chart"), { series: res.map((r, i) => ({ name: name(r, i), color: COLORS[i], ...r.series[cmpMetric] })),
    kind: m.fmt, height: 300, zero: m.fmt === "pct", marker: shockAt });
  $("#cmp-legend").innerHTML = res.map((r, i) => `<span><i style="background:${COLORS[i]}"></i>${name(r, i)}</span>`).join("") +
    `<span><i class="band" style="background:var(--muted)"></i>${T("Banda 10–90 %", "10–90 % band")}</span>`;
  const keys = Object.keys(SUMMARY_INFO);
  $("#cmp-table").innerHTML = `<table class="data"><thead><tr><th>${T("Indicador", "Indicator")}</th>${res.map((r, i) => `<th><i class="sw" style="display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;background:${COLORS[i]}"></i>${String.fromCharCode(65 + i)}</th>`).join("")}</tr></thead><tbody>` +
    keys.map((k) => {
      const vals = res.map((r) => r.summary[k]);
      let best = -1;
      if (SUMMARY_INFO[k].better) { const sc = vals.map((v) => score(k, v.p50, 0)); best = sc.indexOf(Math.max(...sc)); }
      return `<tr><td>${sumLabel(k)}</td>${vals.map((v, i) => `<td class="${i === best ? "pos-c" : ""}">${sfmt(k, v.p50)} <span class="muted">(${sfmt(k, v.p10)} – ${sfmt(k, v.p90)})</span></td>`).join("")}</tr>`;
    }).join("") + `</tbody></table>`;
}

// ---------------------------------------------------------------- explore
async function getGrid(scenario) {
  if (!state.grids[scenario]) state.grids[scenario] = await api(`/api/grid?scenario=${scenario}`);
  return state.grids[scenario];
}
const exploreState = { sort: "top10_wealth:delta", dir: 1, filters: {}, all: false };
async function loadGrid() {
  let g;
  try { g = await getGrid(state.scenario); } catch (err) {
    $("#explore-table").innerHTML = `<div class="empty">${err.message}</div>`;
    return;
  }
  const sel = $("#exp-scenario");
  sel.innerHTML = g.scenarios.map((k) => `<option value="${k}" ${k === state.scenario ? "selected" : ""}>${L.shock(k)}</option>`).join("");
  $("#explore-sub").textContent = T(
    `${g.cells.length} sistemas monetarios × ${g.seeds} simulaciones cada uno en cada escenario (${(g.cells.length * g.seeds * g.scenarios.length).toLocaleString("es-ES")} economías). Error contable máximo: ${Math.max(...g.cells.map((c) => c.sfc_max_error)).toExponential(1)}.`,
    `${g.cells.length} monetary systems × ${g.seeds} runs each in every scenario (${(g.cells.length * g.seeds * g.scenarios.length).toLocaleString("en-GB")} economies). Max accounting error: ${Math.max(...g.cells.map((c) => c.sfc_max_error)).toExponential(1)}.`);
  renderFilters();
  renderEffects(g);
  renderExplore(g);
}
function exploreCols() {
  return state.scenario === "none"
    ? ["inflation:mean", "unemployment:mean", "real_wage:last", "gini_wealth:delta", "top10_wealth:delta", "price_to_income:last", "debt_gdp:last", "tax_gap:mean"]
    : ["inflation:mean", "unemployment:max", "real_gdp:min", "real_wage:last", "top10_wealth:delta", "debt_gdp:last", "bailouts:last", "foreclosures:last"];
}
function renderFilters() {
  const box = $("#explore-filters");
  box.innerHTML = DIMS.map((d) => `<label class="ctl">${L.dim(d)}<select data-dim="${d}"><option value="">${T("Todas", "All")}</option>${Object.keys(state.catalog.dimensions[d].options).map((k) => `<option value="${k}" ${exploreState.filters[d] === k ? "selected" : ""}>${L.opt(d, k, true)}</option>`).join("")}</select></label>`).join("");
  $$("select", box).forEach((s) => s.addEventListener("change", async () => { exploreState.filters[s.dataset.dim] = s.value; renderExplore(await getGrid(state.scenario)); }));
  const em = $("#effect-metric");
  const cur = em.value || "top10_wealth:delta";
  em.innerHTML = Object.keys(SUMMARY_INFO).map((k) => `<option value="${k}">${sumLabel(k)}</option>`).join("");
  em.value = cur;
}
function renderEffects(g) {
  const k = $("#effect-metric").value;
  const cells = g.cells;
  const mean = cells.reduce((a, c) => a + c.summary[k], 0) / cells.length;
  const effects = DIMS.map((d) => Object.keys(state.catalog.dimensions[d].options).map((o) => {
    const sub = cells.filter((c) => c[d] === o);
    return { d, o, v: sub.reduce((a, c) => a + c.summary[k], 0) / sub.length - mean };
  }));
  const maxAbs = Math.max(...effects.flat().map((e) => Math.abs(e.v)), 1e-9);
  const better = SUMMARY_INFO[k].better;
  $("#effects").innerHTML = effects.map((rows, i) => `<div class="card card-pad"><h4 style="font-size:13px;margin-bottom:8px">${L.dim(DIMS[i])}</h4>` +
    rows.map((e) => {
      const w = (Math.abs(e.v) / maxAbs) * 50;
      const good = better ? (better === "low" ? e.v < 0 : e.v > 0) : e.v > 0;
      return `<div class="effect-row"><span>${L.opt(e.d, e.o, true)}</span><span class="bar-bg"><span class="bar" style="${e.v >= 0 ? "left:50%" : "right:50%"};width:${w}%;background:${good ? "var(--pos)" : "var(--neg)"}"></span></span><span class="val">${deltaFmt(k, e.v)}</span></div>`;
    }).join("") + `</div>`).join("");
}
function deltaFmt(k, v) {
  const kind = SUMMARY_INFO[k].kind;
  if (kind === "pct" || kind === "pp") return fmt("pp", v, 2);
  if (kind === "idx") return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}`;
  return `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;
}
function renderExplore(g) {
  const cols = exploreCols();
  if (!cols.includes(exploreState.sort)) exploreState.sort = "top10_wealth:delta";
  const base = g.cells.find((c) => c.key === BASE_KEY).summary;
  let cells = g.cells.filter((c) => DIMS.every((d) => !exploreState.filters[d] || c[d] === exploreState.filters[d]));
  const { sort, dir } = exploreState;
  cells = [...cells].sort((a, b) => dir * (a.summary[sort] - b.summary[sort]));
  const total = cells.length;
  if (!exploreState.all) cells = cells.slice(0, 40);
  const spread = Object.fromEntries(cols.map((k) => [k, Math.max(...g.cells.map((c) => Math.abs(score(k, c.summary[k], base[k]))), 1e-9)]));
  $("#explore-table").innerHTML = `<table class="data"><thead><tr><th>${T("Sistema", "System")}</th>${cols.map((k) => `<th class="sortable ${k === sort ? "sorted" : ""}" data-k="${k}">${sumLabel(k)}${k === sort ? (dir > 0 ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead><tbody>` +
    cells.map((c) => `<tr class="clickable" data-key="${c.key}"><td>${DIMS.filter((d, i) => i < 3 || c[d] !== DEFAULT[d]).map((d) => `<span class="tag">${L.opt(d, c[d], true)}</span>`).join(" ")}${c.key === BASE_KEY ? ` <b style="color:var(--accent);font-size:12px">${T("actual", "today")}</b>` : ""}</td>` +
      cols.map((k) => {
        const v = c.summary[k], sc = score(k, v, base[k]) / spread[k];
        const bg = !SUMMARY_INFO[k].better || Math.abs(sc) < 0.04 ? "transparent" : `color-mix(in srgb, ${sc > 0 ? "var(--pos)" : "var(--neg)"} ${Math.round(Math.min(1, Math.abs(sc)) * 32)}%, transparent)`;
        return `<td><span class="heat" style="background:${bg}">${sfmt(k, v)}</span></td>`;
      }).join("") + `</tr>`).join("") + `</tbody></table>`;
  $("#explore-count").textContent = T(`${Math.min(total, exploreState.all ? total : 40)} de ${total} sistemas`, `${Math.min(total, exploreState.all ? total : 40)} of ${total} systems`);
  $("#explore-more").hidden = exploreState.all || total <= 40;
  $$("#explore-table th.sortable").forEach((th) => th.addEventListener("click", () => {
    if (exploreState.sort === th.dataset.k) exploreState.dir *= -1; else { exploreState.sort = th.dataset.k; exploreState.dir = 1; }
    renderExplore(g);
  }));
  $$("#explore-table tr.clickable").forEach((tr) => tr.addEventListener("click", () => {
    state.regime = fromKey(tr.dataset.key);
    $("#p-shock").value = state.scenario;
    syncShockDesc(); renderBuilder(); syncPreset();
    location.hash = "#lab";
    runLab();
  }));
}

// ------------------------------------------------------------ methodology
function renderMethodTables() {
  $("#m-regimes-table").innerHTML = `<thead><tr><th>${T("Dimensión", "Dimension")}</th><th>${T("Opción", "Option")}</th><th style="text-align:left">${T("Qué significa", "Meaning")}</th></tr></thead><tbody>` +
    DIMS.flatMap((d) => Object.keys(state.catalog.dimensions[d].options).map((o, i) =>
      `<tr><td>${i === 0 ? `<b>${L.dim(d)}</b>` : ""}</td><td style="font-family:var(--sans);text-align:left">${L.opt(d, o)}</td><td style="text-align:left">${L.desc(d, o)}</td></tr>`)).join("") + `</tbody>`;
  $("#m-shocks-table").innerHTML = `<thead><tr><th>${T("Crisis", "Crisis")}</th><th style="text-align:left">${T("Qué ocurre", "What happens")}</th></tr></thead><tbody>` +
    Object.keys(state.catalog.shocks).filter((k) => k !== "none").map((k) => `<tr><td>${L.shock(k)}</td><td style="text-align:left">${L.shockDesc(k)}</td></tr>`).join("") + `</tbody>`;
}

// ------------------------------------------------------------------- init
function relabel() {
  applyStatic();
  renderBuilder(); syncPreset(); renderAdv(); renderSlots();
  const s1 = $("#p-shock").value, s2 = $("#cmp-shock").value;
  shockOptions($("#p-shock"), s1 || "none");
  shockOptions($("#cmp-shock"), s2 || "none");
  syncShockDesc();
  $$("#p-months option").forEach((o) => (o.textContent = `${o.value / 12} ${T("años", "years")}`));
  $$("#p-shock-month option").forEach((o) => (o.textContent = `${T("Año", "Year")} ${o.value / 12 + 1}`));
  setBusy(state.busy);
  relabelPolicy();
  if (state.last) renderLab();
  if (state.cmp) renderCompare();
  route();
}

async function init() {
  $("#theme-btn").addEventListener("click", () => {
    const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("msl-theme", t); } catch (e) {}
    if (state.last) renderLab();
    if (state.cmp) renderCompare();
    route();
  });
  $("#lang-btn").addEventListener("click", () => {
    const l = lang() === "en" ? "es" : "en";
    document.documentElement.lang = l;
    try { localStorage.setItem("msl-lang", l); } catch (e) {}
    relabel();
  });
  state.catalog = await api("/api/catalog");
  try { const k = localStorage.getItem("msl-regime"); if (k) state.regime = fromKey(k); } catch (e) {}
  $("#preset").addEventListener("change", (e) => { if (e.target.value) { state.regime = fromKey(e.target.value); renderBuilder(); } });
  $("#p-shock").addEventListener("change", syncShockDesc);
  $("#exp-scenario").addEventListener("change", (e) => { state.scenario = e.target.value; loadGrid(); });
  $("#effect-metric").addEventListener("change", async () => renderEffects(await getGrid(state.scenario)));
  $("#explore-more").addEventListener("click", async () => { exploreState.all = true; renderExplore(await getGrid(state.scenario)); });
  $("#run-btn").addEventListener("click", runLab);
  $("#cmp-btn").addEventListener("click", runCompare);
  $$("#acct-tabs button").forEach((b) => b.addEventListener("click", () => {
    $$("#acct-tabs button").forEach((x) => x.classList.toggle("on", x === b));
    if (state.last) renderAcct(state.last, b.dataset.t);
  }));
  window.addEventListener("hashchange", route);
  relabel();
  initPolicy({ api, setBusy, setSfc, shockLabel: L.shock, shocks: () => state.catalog.shocks })
    .then(relabelPolicy)
    .catch((err) => { document.getElementById("pol-levers").innerHTML = `<div class="empty">${err.message}</div>`; });
  getGrid("none").catch(() => {}).finally(runLab);
}
init();
