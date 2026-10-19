import { lineChart, divergingBars, hBars, fmt } from "/static/charts.js";

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const DIMS = ["issuance", "channel", "banking"];
const BASE_KEY = "discretionary|banks|fractional";
const COLORS = ["var(--s1)", "var(--s2)", "var(--s3)"];

const PRESETS = [
  { key: BASE_KEY, label: "Sistema actual (BCE)" },
  { key: "gold|banks|fractional", label: "Patrón oro clásico" },
  { key: "fixed_supply|miners|fractional", label: "Bitcoin como moneda (con banca)" },
  { key: "fixed_supply|miners|full_reserve", label: "Bitcoin puro (reserva 100 %)" },
  { key: "rule_2pct|government|full_reserve", label: "Chicago Plan (Benes y Kumhof)" },
  { key: "discretionary|dividend|fractional", label: "«QE para la gente»" },
  { key: "rule_2pct|dividend|full_reserve", label: "Algoritmo 2 % + dividendo, sin banca fraccionaria" },
];

// Resumen: cómo se muestra cada indicador y qué dirección es mejor
const SUMMARY_INFO = {
  "inflation:mean": { label: "Inflación media", kind: "pct", better: "target" },
  "unemployment:mean": { label: "Paro medio", kind: "pct", better: "low" },
  "real_wage:last": { label: "Salario real final", kind: "idx", better: "high", note: "inicio = 100" },
  "gini_wealth:delta": { label: "Δ Gini de la riqueza", kind: "dsign", better: "low" },
  "top10_wealth:delta": { label: "Δ cuota del 10 % más rico", kind: "pp", better: "low" },
  "house_price_real:last": { label: "Vivienda (precio real)", kind: "idx", better: null, note: "inicio = 100" },
  "price_to_income:last": { label: "Años de salario por vivienda", kind: "x", better: "low" },
  "real_gdp:last": { label: "PIB real final", kind: "idx", better: "high", note: "inicio = 100" },
  "debt_gdp:last": { label: "Deuda pública / PIB", kind: "pct", better: "low" },
  "foreclosures:last": { label: "Ejecuciones hipotecarias", kind: "pct", better: "low" },
  "stock_index:last": { label: "Bolsa (valor real)", kind: "idx", better: null, note: "inicio = 100" },
  "bailouts:last": { label: "Rescates bancarios (% PIB)", kind: "pct", better: "low" },
};
const KPI_KEYS = ["inflation:mean", "unemployment:mean", "real_wage:last", "gini_wealth:delta", "top10_wealth:delta", "house_price_real:last"];

const sfmt = (key, v, d) => {
  const kind = SUMMARY_INFO[key]?.kind || "dec";
  if (kind === "dsign") return v == null ? "—" : `${v >= 0 ? "+" : ""}${fmt("dec", v)}`;
  return fmt(kind, v, d);
};
const target = 0.02;
// >0 = mejor que la referencia, <0 = peor
function score(key, v, ref) {
  const b = SUMMARY_INFO[key]?.better;
  if (!b || ref == null) return 0;
  if (b === "low") return ref - v;
  if (b === "high") return v - ref;
  return Math.abs(ref - target) - Math.abs(v - target);
}

const state = { catalog: null, regime: { issuance: "discretionary", channel: "banks", banking: "fractional" }, grid: null, busy: false };

async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
const optLabel = (dim, key, short = false) => state.catalog.dimensions[dim].options[key][short ? "short" : "label"];
const regimeLabel = (r) => DIMS.map((d) => optLabel(d, r[d], true)).join(" · ");
const keyOf = (r) => DIMS.map((d) => r[d]).join("|");
const fromKey = (k) => Object.fromEntries(k.split("|").map((v, i) => [DIMS[i], v]));

function setBusy(on, text) {
  state.busy = on;
  const pill = $("#run-pill");
  pill.classList.toggle("busy", on);
  pill.classList.toggle("ok", !on);
  $("#run-text").textContent = text || (on ? "Simulando…" : "Listo");
  $("#run-btn").disabled = on;
  $("#cmp-btn").disabled = on;
}
function setSfc(err) {
  const p = $("#sfc-pill");
  p.classList.toggle("ok", err < 1e-9);
  p.title = `Error contable máximo: ${err.toExponential(1)} (activos − pasivos en todos los instrumentos y meses)`;
  $("span", p).textContent = err < 1e-9 ? "Contabilidad cuadrada" : "Descuadre contable";
}

// ------------------------------------------------------------------ router
function route() {
  const v = (location.hash.slice(1) || "lab").split("?")[0];
  const view = ["lab", "compare", "explore", "method"].includes(v) ? v : "lab";
  $$(".view").forEach((s) => s.classList.toggle("active", s.id === `view-${view}`));
  $$(".mainnav a").forEach((a) => a.classList.toggle("active", a.dataset.view === view));
  if (view === "explore") loadGrid();
  if (view === "method") renderMethodTable();
  if (location.hash.includes("m-")) return;
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
    card.innerHTML = `<h3>${d.label}</h3><div class="help">${d.help}</div>
      <div class="opts" role="radiogroup" aria-label="${d.label}">${Object.entries(d.options).map(([k, o]) =>
        `<button class="opt${state.regime[dim] === k ? " on" : ""}" role="radio" aria-checked="${state.regime[dim] === k}" data-dim="${dim}" data-k="${k}">${o.short}</button>`).join("")}</div>
      <div class="desc"><b>${d.options[state.regime[dim]].label}.</b> ${d.options[state.regime[dim]].desc}</div>`;
    box.appendChild(card);
  }
  $$(".opt", box).forEach((b) => b.addEventListener("click", () => {
    state.regime[b.dataset.dim] = b.dataset.k;
    syncPreset();
    renderBuilder();
  }));
}
function syncPreset() {
  const k = keyOf(state.regime);
  $("#preset").value = PRESETS.some((p) => p.key === k) ? k : "";
}

const ADV = [
  ["inflation_target", "Objetivo de inflación", 0.005],
  ["natural_unemployment", "Paro natural", 0.01],
  ["productivity_growth", "Crecimiento productividad", 0.001],
  ["gov_spending_share", "Gasto público / PIB", 0.01],
  ["credibility", "Credibilidad de la regla", 0.01],
  ["money_rate_sens", "Sensibilidad del tipo al dinero", 0.01],
  ["reserve_ratio", "Coeficiente de reservas", 0.005],
  ["capital_ratio", "Capital bancario mínimo", 0.01],
  ["ltv", "LTV máximo hipotecas", 0.05],
  ["dsti", "Cuota máx. / renta", 0.05],
  ["gold_growth", "Crecimiento del oro", 0.005],
  ["fixed_initial_issuance", "Emisión inicial (oferta fija)", 0.005],
  ["halving_months", "Meses entre halvings", 12],
  ["wage_floor", "Caída salarial máx. anual", 0.01],
];
function renderAdv() {
  const def = state.catalog.params;
  $("#adv").innerHTML = ADV.map(([k, label, step]) =>
    `<label class="ctl">${label}<input type="number" step="${step}" data-p="${k}" value="${def[k]}"></label>`).join("");
}
function readParams() {
  const out = { months: +$("#p-months").value, households: +$("#p-households").value };
  const def = state.catalog.params;
  $$("#adv input").forEach((i) => { if (i.value !== "" && +i.value !== def[i.dataset.p]) out[i.dataset.p] = +i.value; });
  return out;
}

// ------------------------------------------------------------------- lab
async function runLab() {
  if (state.busy) return;
  const t0 = performance.now();
  const seeds = +$("#p-seeds").value;
  setBusy(true, `Simulando ${seeds} economías…`);
  try {
    const res = await api("/api/simulate", { ...state.regime, seeds, params: readParams() });
    state.last = res;
    renderLab(res, (performance.now() - t0) / 1000);
    try { localStorage.setItem("msl-regime", keyOf(state.regime)); } catch (e) {}
  } catch (err) {
    $("#runinfo").innerHTML = `<span class="neg">Error: ${err.message}</span>`;
  } finally {
    setBusy(false);
  }
}

function baselineSummary() {
  return state.grid?.cells.find((c) => c.key === BASE_KEY)?.summary;
}

function renderLab(res, secs) {
  $("#lab-empty").hidden = true;
  $("#lab-results").hidden = false;
  setSfc(res.sfc_max_error);
  const p = res.params;
  $("#runinfo").innerHTML = `
    <span><b>${res.regime.label}</b></span>
    <span>${res.seeds} simulaciones × ${p.households.toLocaleString("es-ES")} hogares × ${p.months / 12} años</span>
    <span>${secs.toFixed(1)} s</span>
    <span class="check" title="activos − pasivos en todos los instrumentos y meses">✓ contabilidad cuadrada (error máx. ${res.sfc_max_error.toExponential(1)})</span>`;

  const base = keyOf(state.regime) === BASE_KEY ? null : baselineSummary();
  $("#kpis").innerHTML = KPI_KEYS.map((k) => {
    const info = SUMMARY_INFO[k], s = res.summary[k];
    const sc = base ? score(k, s.p50, base[k].p50) : 0;
    const cls = Math.abs(sc) < 1e-3 ? "" : sc > 0 ? "good" : "bad";
    return `<div class="card kpi">
      <div class="k">${info.label}</div>
      <div class="v ${cls}">${sfmt(k, s.p50)}</div>
      <div class="r">${base ? `Sistema actual: ${sfmt(k, base[k].p50)}` : `Rango: ${sfmt(k, s.p10)} – ${sfmt(k, s.p90)}`}${info.note ? ` · ${info.note}` : ""}</div>
    </div>`;
  }).join("");

  renderGroups(res);
  const start = res.wealth_share_start, end = res.wealth_share_end;
  divergingBars($("#decile-chart"), {
    labels: start.map((_, i) => `D${i + 1}`),
    values: end.map((v, i) => v - start[i]),
    extra: { start, end, names: start.map((_, i) => `Decil ${i + 1} (${i * 10}–${(i + 1) * 10} %)`) },
    title: "Variación de la cuota de riqueza por decil",
  });
  const to = res.new_money_to;
  const created = (to.Bancos || 0) + (to.Estado || 0) + (to.Hogares || 0);
  if (created < 1e-6) {
    $("#newmoney-sectors").innerHTML = `<p class="t2" style="font-size:13px">En esta simulación no se ha creado dinero base nuevo: ${state.regime.issuance === "discretionary"
      ? "con la regla discrecional el banco central solo compra activos (QE) cuando la inflación cae por debajo del objetivo o el paro se dispara, y no ha ocurrido. Todo el dinero nuevo lo han creado los bancos al prestar."
      : "la regla no ha emitido en este horizonte."}</p>`;
    $("#newmoney-deciles").innerHTML = "";
  } else hBars($("#newmoney-sectors"), {
    rows: [
      { label: "Bancos", value: to.Bancos || 0, color: "var(--s1)" },
      { label: "Estado", value: to.Estado || 0, color: "var(--s2)" },
      { label: "Hogares", value: to.Hogares || 0, color: "var(--s3)" },
    ],
  });
  const dec = res.new_money_deciles, tot = dec.reduce((a, b) => a + b, 0);
  const nd = $("#newmoney-deciles");
  $("#newmoney-dec-title").hidden = created < 1e-6;
  if (created < 1e-6) {
    // ya explicado arriba
  } else if (tot < 1e-6) {
    nd.innerHTML = `<p class="muted" style="font-size:13px;margin-top:8px">Con este canal el dinero nuevo no llega directamente a ningún hogar.</p>`;
  } else {
    hBars(nd, { rows: dec.map((v, i) => ({ label: `D${i + 1}`, value: v / tot, color: "var(--s3)" })) });
  }
  renderAcct(res, $("#acct-tabs .on").dataset.t);
  const ev = res.events || [];
  $("#events-card").hidden = !ev.length;
  $("#events").innerHTML = ev.slice(0, 12).map((e) => `<div><span class="tag">Año ${Math.floor(e.t / 12) + 1}</span><span>${e.text}</span></div>`).join("");
}

const GROUP_ORDER = ["Precios", "Empleo", "Actividad", "Desigualdad", "Vivienda", "Dinero", "Finanzas"];
const GROUPS = {
  "Precios y empleo": ["inflation", "unemployment", "real_wage", "real_gdp"],
  "Desigualdad": ["gini_wealth", "top10_wealth", "bottom50_wealth", "gini_income"],
  "Vivienda": ["house_price_real", "price_to_income", "homeownership", "rent_burden"],
  "Dinero y tipos": ["broad_money", "new_money", "policy_rate", "credit_gdp"],
  "Finanzas y Estado": ["debt_gdp", "stock_index", "foreclosures", "bank_capital"],
};
let currentGroup = "Precios y empleo";
function renderGroups(res) {
  const tabs = $("#group-tabs");
  tabs.innerHTML = Object.keys(GROUPS).map((g) => `<button class="${g === currentGroup ? "on" : ""}">${g}</button>`).join("");
  $$("button", tabs).forEach((b) => b.addEventListener("click", () => { currentGroup = b.textContent; renderGroups(res); }));
  const box = $("#charts");
  box.innerHTML = "";
  for (const key of GROUPS[currentGroup]) {
    const m = state.catalog.metrics[key];
    const card = document.createElement("div");
    card.className = "card chart-card";
    const ref = key === "inflation" ? res.params.inflation_target : key === "unemployment" ? res.params.natural_unemployment : null;
    card.innerHTML = `<h4>${m.label}</h4><div class="sub">${m.fmt === "idx" ? "Índice, inicio = 100" : ref != null ? `Línea discontinua: ${key === "inflation" ? "objetivo" : "paro natural"}` : "&nbsp;"}</div><div class="chart"></div>`;
    box.appendChild(card);
    const s = res.series[key];
    lineChart($(".chart", card), { series: [{ name: m.label, color: "var(--s1)", ...s }], kind: m.fmt, ref, zero: m.fmt === "pct" });
  }
}

function renderAcct(res, tab) {
  const box = $("#acct");
  const n = res.params.households;
  const k = (v) => (Math.abs(v) < 0.5 ? `<td class="zero">·</td>` : `<td class="${v < 0 ? "neg" : ""}">${(v / n / 1000).toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</td>`);
  if (tab === "flows") {
    const S = state.catalog.sectors;
    box.innerHTML = `<table class="data"><thead><tr><th>Concepto</th><th>De</th><th>A</th><th>€ por hogar</th></tr></thead><tbody>` +
      res.flows.slice(0, 22).map((f) => `<tr><td>${f.purpose}</td><td style="font-family:var(--sans)">${S[f.from]}</td><td style="font-family:var(--sans)">${S[f.to]}</td><td>${(f.amount / n).toLocaleString("es-ES", { maximumFractionDigits: 0 })}</td></tr>`).join("") +
      `</tbody></table>`;
    return;
  }
  const bs = res.balance_sheet;
  box.innerHTML = `<table class="data"><thead><tr><th>Miles de € por hogar</th>${bs.sectors.map((s) => `<th>${s.label}</th>`).join("")}<th>Σ</th></tr></thead><tbody>` +
    bs.rows.map((r) => `<tr class="${r.key === "net" ? "total" : ""}"><td>${r.label}</td>${bs.sectors.map((s) => k(r[s.key])).join("")}${k(r.total)}</tr>`).join("") +
    `</tbody></table>`;
}

// --------------------------------------------------------------- compare
const slots = [
  { key: BASE_KEY },
  { key: "fixed_supply|miners|fractional" },
  { key: "rule_2pct|dividend|full_reserve" },
];
function renderSlots() {
  $("#slots").innerHTML = slots.map((s, i) => {
    const r = fromKey(s.key);
    return `<div class="card slot" style="--c:${COLORS[i]}">
      <h3><i></i>Sistema ${String.fromCharCode(65 + i)}</h3>
      <label class="ctl">Conocido<select data-i="${i}" data-role="preset"><option value="">— Personalizado —</option>${PRESETS.map((p) => `<option value="${p.key}" ${p.key === s.key ? "selected" : ""}>${p.label}</option>`).join("")}</select></label>
      ${DIMS.map((d) => `<label class="ctl">${state.catalog.dimensions[d].label}<select data-i="${i}" data-dim="${d}">${Object.entries(state.catalog.dimensions[d].options).map(([k, o]) => `<option value="${k}" ${r[d] === k ? "selected" : ""}>${o.label}</option>`).join("")}</select></label>`).join("")}
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
  const params = readParams(), seeds = +$("#p-seeds").value;
  const out = [];
  try {
    for (let i = 0; i < slots.length; i++) {
      setBusy(true, `Simulando sistema ${String.fromCharCode(65 + i)}…`);
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
  $("#cmp-results").hidden = false;
  const chips = Object.values(GROUPS).flat();
  $("#cmp-metrics").innerHTML = chips.map((k) => `<button class="opt${k === cmpMetric ? " on" : ""}" data-k="${k}">${state.catalog.metrics[k].label}</button>`).join("");
  $$("#cmp-metrics .opt").forEach((b) => b.addEventListener("click", () => { cmpMetric = b.dataset.k; renderCompare(); }));
  const m = state.catalog.metrics[cmpMetric];
  $("#cmp-title").textContent = m.label + (m.fmt === "idx" ? " (inicio = 100)" : "");
  lineChart($("#cmp-chart"), {
    series: res.map((r, i) => ({ name: `${String.fromCharCode(65 + i)} · ${r.regime.label}`, color: COLORS[i], ...r.series[cmpMetric] })),
    kind: m.fmt, height: 300, zero: m.fmt === "pct",
  });
  $("#cmp-legend").innerHTML = res.map((r, i) => `<span><i style="background:${COLORS[i]}"></i>${String.fromCharCode(65 + i)} · ${r.regime.label}</span>`).join("") +
    `<span><i class="band" style="background:var(--muted)"></i>Banda 10–90 %</span>`;
  const keys = Object.keys(SUMMARY_INFO);
  $("#cmp-table").innerHTML = `<table class="data"><thead><tr><th>Indicador</th>${res.map((r, i) => `<th><i class="sw" style="display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:6px;background:${COLORS[i]}"></i>${String.fromCharCode(65 + i)}</th>`).join("")}</tr></thead><tbody>` +
    keys.map((k) => {
      const vals = res.map((r) => r.summary[k]);
      const b = SUMMARY_INFO[k].better;
      let best = -1;
      if (b) { const sc = vals.map((v) => score(k, v.p50, 0) * (b === "target" ? 1 : 1)); best = sc.indexOf(Math.max(...sc)); }
      return `<tr><td>${SUMMARY_INFO[k].label}</td>${vals.map((v, i) => `<td class="${i === best ? "pos-c" : ""}">${sfmt(k, v.p50)} <span class="muted">(${sfmt(k, v.p10)} – ${sfmt(k, v.p90)})</span></td>`).join("")}</tr>`;
    }).join("") + `</tbody></table>`;
}

// ---------------------------------------------------------------- explore
async function loadGrid() {
  if (!state.grid) {
    try { state.grid = await api("/api/grid"); } catch (err) {
      $("#explore-table").innerHTML = `<div class="empty">${err.message}</div>`;
      return;
    }
  }
  const g = state.grid;
  $("#explore-sub").innerHTML = `${g.cells.length} sistemas monetarios × ${g.seeds} simulaciones cada uno (${(g.cells.length * g.seeds).toLocaleString("es-ES")} economías). Error contable máximo: ${Math.max(...g.cells.map((c) => c.sfc_max_error)).toExponential(1)}. Ordena por cualquier columna o pulsa una fila para abrirla en el laboratorio.`;
  renderFilters();
  renderEffects();
  renderExplore();
}
const exploreState = { sort: "top10_wealth:delta", dir: 1, filters: {} };
function renderFilters() {
  const box = $("#explore-filters");
  if (box.childElementCount) return;
  box.innerHTML = DIMS.map((d) => `<label class="ctl">${state.catalog.dimensions[d].label}<select data-dim="${d}"><option value="">Todas</option>${Object.entries(state.catalog.dimensions[d].options).map(([k, o]) => `<option value="${k}">${o.short}</option>`).join("")}</select></label>`).join("");
  $$("select", box).forEach((s) => s.addEventListener("change", () => { exploreState.filters[s.dataset.dim] = s.value; renderExplore(); }));
  const em = $("#effect-metric");
  em.innerHTML = Object.entries(SUMMARY_INFO).map(([k, v]) => `<option value="${k}">${v.label}</option>`).join("");
  em.value = "top10_wealth:delta";
  em.addEventListener("change", renderEffects);
}
function renderEffects() {
  const k = $("#effect-metric").value;
  const cells = state.grid.cells;
  const mean = cells.reduce((a, c) => a + c.summary[k].p50, 0) / cells.length;
  const effects = DIMS.map((d) => Object.keys(state.catalog.dimensions[d].options).map((o) => {
    const sub = cells.filter((c) => c[d] === o);
    return { d, o, v: sub.reduce((a, c) => a + c.summary[k].p50, 0) / sub.length - mean };
  }));
  const maxAbs = Math.max(...effects.flat().map((e) => Math.abs(e.v)), 1e-9);
  const isLowBetter = SUMMARY_INFO[k].better === "low";
  $("#effects").innerHTML = effects.map((rows, i) => `<div class="card card-pad"><h4 style="font-size:13px;margin-bottom:8px">${state.catalog.dimensions[DIMS[i]].label}</h4>` +
    rows.map((e) => {
      const w = (Math.abs(e.v) / maxAbs) * 50;
      const good = SUMMARY_INFO[k].better ? (isLowBetter ? e.v < 0 : e.v > 0) : e.v > 0;
      return `<div class="effect-row"><span>${optLabel(e.d, e.o, true)}</span><span class="bar-bg"><span class="bar" style="${e.v >= 0 ? `left:50%` : `right:50%`};width:${w}%;background:${good ? "var(--pos)" : "var(--neg)"}"></span></span><span class="val">${deltaFmt(k, e.v)}</span></div>`;
    }).join("") + `</div>`).join("");
}
function deltaFmt(k, v) {
  const kind = SUMMARY_INFO[k].kind;
  if (kind === "pct" || kind === "pp") return fmt("pp", v, 2);
  if (kind === "idx") return `${v >= 0 ? "+" : ""}${(v * 100).toFixed(1)}`;
  return `${v >= 0 ? "+" : ""}${v.toFixed(3)}`;
}
const EXPLORE_COLS = ["inflation:mean", "unemployment:mean", "real_wage:last", "gini_wealth:delta", "top10_wealth:delta", "price_to_income:last", "debt_gdp:last", "stock_index:last"];
function renderExplore() {
  const base = baselineSummary();
  let cells = state.grid.cells.filter((c) => DIMS.every((d) => !exploreState.filters[d] || c[d] === exploreState.filters[d]));
  const { sort, dir } = exploreState;
  cells = [...cells].sort((a, b) => dir * (a.summary[sort].p50 - b.summary[sort].p50));
  const spread = Object.fromEntries(EXPLORE_COLS.map((k) => {
    const vals = state.grid.cells.map((c) => Math.abs(score(k, c.summary[k].p50, base[k].p50)));
    return [k, Math.max(...vals, 1e-9)];
  }));
  $("#explore-table").innerHTML = `<table class="data"><thead><tr><th>Sistema</th>${EXPLORE_COLS.map((k) => `<th class="sortable ${k === sort ? "sorted" : ""}" data-k="${k}">${SUMMARY_INFO[k].label}${k === sort ? (dir > 0 ? " ↑" : " ↓") : ""}</th>`).join("")}</tr></thead><tbody>` +
    cells.map((c) => `<tr class="clickable" data-key="${c.key}"><td>${DIMS.map((d) => `<span class="tag">${optLabel(d, c[d], true)}</span>`).join(" ")}${c.key === BASE_KEY ? ` <b style="color:var(--accent);font-size:12px">actual</b>` : ""}</td>` +
      EXPLORE_COLS.map((k) => {
        const v = c.summary[k].p50, sc = score(k, v, base[k].p50) / spread[k];
        const bg = !SUMMARY_INFO[k].better || Math.abs(sc) < 0.04 ? "transparent" : `color-mix(in srgb, ${sc > 0 ? "var(--pos)" : "var(--neg)"} ${Math.round(Math.min(1, Math.abs(sc)) * 32)}%, transparent)`;
        return `<td><span class="heat" style="background:${bg}">${sfmt(k, v)}</span></td>`;
      }).join("") + `</tr>`).join("") + `</tbody></table>`;
  $$("#explore-table th.sortable").forEach((th) => th.addEventListener("click", () => {
    if (exploreState.sort === th.dataset.k) exploreState.dir *= -1; else { exploreState.sort = th.dataset.k; exploreState.dir = 1; }
    renderExplore();
  }));
  $$("#explore-table tr.clickable").forEach((tr) => tr.addEventListener("click", () => {
    state.regime = fromKey(tr.dataset.key);
    renderBuilder(); syncPreset();
    location.hash = "#lab";
    runLab();
  }));
}

// ------------------------------------------------------------ methodology
function renderMethodTable() {
  const t = $("#m-regimes-table");
  if (t.childElementCount) return;
  t.innerHTML = `<thead><tr><th>Dimensión</th><th>Opción</th><th style="text-align:left">Qué significa</th></tr></thead><tbody>` +
    DIMS.flatMap((d) => Object.values(state.catalog.dimensions[d].options).map((o, i) =>
      `<tr><td>${i === 0 ? `<b>${state.catalog.dimensions[d].label}</b>` : ""}</td><td style="font-family:var(--sans);text-align:left">${o.label}</td><td style="text-align:left">${o.desc}</td></tr>`)).join("") + `</tbody>`;
}

// ------------------------------------------------------------------- init
async function init() {
  $("#theme-btn").addEventListener("click", () => {
    const t = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem("msl-theme", t); } catch (e) {}
    if (state.last) renderLab(state.last, 0);
    if (state.cmp) renderCompare();
  });
  state.catalog = await api("/api/catalog");
  try { const k = localStorage.getItem("msl-regime"); if (k) state.regime = fromKey(k); } catch (e) {}
  $("#preset").innerHTML = `<option value="">— Personalizado —</option>` + PRESETS.map((p) => `<option value="${p.key}">${p.label}</option>`).join("");
  $("#preset").addEventListener("change", (e) => { if (e.target.value) { state.regime = fromKey(e.target.value); renderBuilder(); } });
  renderBuilder(); syncPreset(); renderAdv(); renderSlots();
  $("#run-btn").addEventListener("click", runLab);
  $("#cmp-btn").addEventListener("click", runCompare);
  $$("#acct-tabs button").forEach((b) => b.addEventListener("click", () => {
    $$("#acct-tabs button").forEach((x) => x.classList.toggle("on", x === b));
    if (state.last) renderAcct(state.last, b.dataset.t);
  }));
  window.addEventListener("hashchange", route);
  route();
  setBusy(false);
  api("/api/grid").then((g) => (state.grid = g)).catch(() => {}).finally(runLab);
}
init();
