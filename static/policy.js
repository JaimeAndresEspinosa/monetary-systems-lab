// Laboratorio de políticas: palancas, medidas de ejemplo, «¿Y a mí?», ganadores y perdedores y confianza.
import { lineChart, fmt } from "/static/charts.js";
import { T, lang, LOCALE, POLICY_EN } from "/static/i18n.js";

const $ = (s, root = document) => root.querySelector(s);
const $$ = (s, root = document) => [...root.querySelectorAll(s)];
const ps = { cat: null, levers: {}, preset: null, sim: null, body: null, me: null, who: "after_housing", busy: false };
let ctx = null;   // { api, setBusy, shockLabel }

// --------------------------------------------------------------- textos
const en = () => lang() === "en";
const tl = (k, f) => (en() && POLICY_EN.levers[k]?.[f]) || ps.cat.levers[k][f];
const te = (k, f) => (en() && POLICY_EN.elasticities[k]?.[f]) || ps.cat.elasticities[k][f];
const tp = (k, f) => (en() && POLICY_EN.presets[k]?.[f]) || ps.cat.presets[k][f];
const tg = (k) => (en() && POLICY_EN.groups[k]) || ps.cat.groups[k];
const tf = (k, es) => (en() && POLICY_EN.factors[k]) || es;
const CONF = { alta: ["Confianza alta", "High confidence"], media: ["Confianza media", "Medium confidence"], baja: ["Confianza baja", "Low confidence"] };
const eur = (v, d = 0) => (v == null ? "—" : `${v.toLocaleString(LOCALE(), { maximumFractionDigits: d })} €`);
const signed = (s, v) => (v > 0 ? `+${s}` : s);

function decimals(step) {
  for (let d = 0; d < 4; d++) if (Math.abs(step * 100 * 10 ** d - Math.round(step * 100 * 10 ** d)) < 1e-6) return d;
  return 2;
}
function fmtLever(spec, v) {
  if (spec.choices && v >= 1) return T("Sin tope", "No cap");
  if (spec.kind === "pct") return fmt("pct", v, spec.choices ? 0 : decimals(spec.step));
  if (spec.kind === "eur") return eur(v);
  if (spec.kind === "years") return `${v} ${T("años", "years")}`;
  if (spec.kind === "x") return `×${v.toLocaleString(LOCALE(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`;
  return v.toLocaleString(LOCALE(), { maximumFractionDigits: 1 });
}
const cur = (k) => (k in ps.levers ? ps.levers[k] : (ps.cat.levers[k] || ps.cat.elasticities[k]).default);
const confBadge = (c) => `<span class="conf conf-${c}">${T(...CONF[c])}</span>`;

// ----------------------------------------------------------------- init
export async function initPolicy(c) {
  ctx = c;
  ps.cat = await ctx.api("/api/policy/catalog");
  $("#pol-run").addEventListener("click", runPolicy);
  $("#pol-reset").addEventListener("click", () => { ps.levers = {}; ps.preset = null; renderControls(); });
  $("#pol-me-update").addEventListener("click", async () => {
    if (!ps.body || ps.busy) return;
    busy(true, T("Buscando hogares parecidos…", "Finding similar households…"));
    try { await runMe(); renderMe(); } catch (err) { $("#pol-me").innerHTML = `<p class="neg">Error: ${err.message}</p>`; }
    finally { busy(false); }
  });
  $("#pol-robust").addEventListener("click", runRobust);
  renderControls();
}

export function relabelPolicy() {
  if (!ps.cat) return;
  const shock = $("#pol-shock").value || "none";
  $("#pol-shock").innerHTML = Object.keys(ctx.shocks()).map((k) => `<option value="${k}" ${k === shock ? "selected" : ""}>${ctx.shockLabel(k)}</option>`).join("");
  $$("#pol-months option").forEach((o) => (o.textContent = `${o.value / 12} ${T("años", "years")}`));
  $$("#me-years option").forEach((o) => (o.textContent = `${o.value} ${T("años", "years")}`));
  renderControls();
  if (ps.sim) renderResults();
}

// ------------------------------------------------------- medidas y palancas
function renderControls() {
  $("#pol-presets").innerHTML = Object.keys(ps.cat.presets).map((k) =>
    `<button class="card pol-preset${ps.preset === k ? " on" : ""}" data-p="${k}"><b>${tp(k, "label")}</b>
      <span>${Object.entries(ps.cat.presets[k].levers).map(([l, v]) => `${shortLever(l)}: ${fmtLever(ps.cat.levers[l], v)}`).join(" · ")}</span></button>`).join("");
  $$("#pol-presets .pol-preset").forEach((b) => b.addEventListener("click", () => {
    ps.preset = b.dataset.p;
    ps.levers = { ...ps.cat.presets[ps.preset].levers };
    renderControls();
    runPolicy();
  }));
  renderPresetInfo();
  const groups = Object.keys(ps.cat.groups);
  $("#pol-levers").innerHTML = groups.map((g) => `<div class="card card-pad pol-group"><h3>${tg(g)}</h3>` +
    Object.entries(ps.cat.levers).filter(([, s]) => s.group === g).map(([k, s]) => leverHTML(k, s)).join("") + `</div>`).join("");
  $$("#pol-levers [data-lever]").forEach((inp) => inp.addEventListener("input", () => setLever(inp.dataset.lever, +inp.value)));
  $$("#pol-levers [data-ela]").forEach((inp) => inp.addEventListener("change", () => {
    const s = ps.cat.elasticities[inp.dataset.ela];
    const v = Math.min(s.hi, Math.max(s.lo, +inp.value));
    inp.value = v;
    setLever(inp.dataset.ela, v, false);
  }));
  $$("#pol-levers [data-reset]").forEach((b) => b.addEventListener("click", () => { delete ps.levers[b.dataset.reset]; ps.preset = matchPreset(); renderControls(); }));
  renderLeverSummary();
}
function shortLever(k) {
  const lab = tl(k, "label");
  return lab.length > 34 ? lab.split(/[(:]/)[0].trim() : lab;
}
function leverHTML(k, s) {
  const v = cur(k), def = s.default, changed = v !== def;
  let ctl;
  if (s.choices) {
    ctl = `<select data-lever="${k}">${s.choices.map((c) => `<option value="${c}" ${c === v ? "selected" : ""}>${fmtLever(s, c)}</option>`).join("")}</select>`;
  } else {
    const pos = ((def - s.min) / (s.max - s.min)) * 100;
    ctl = `<span class="range-wrap"><input type="range" data-lever="${k}" min="${s.min}" max="${s.max}" step="${s.step}" value="${v}" aria-label="${tl(k, "label")}"><i class="tick" style="left:calc(${pos}% + ${(0.5 - pos / 100) * 16}px)" title="${T("Hoy", "Today")}"></i></span>`;
  }
  const ela = s.elasticity ? (() => {
    const e = ps.cat.elasticities[s.elasticity];
    return `<div class="ela"><label class="ctl">${te(s.elasticity, "label")}<input type="number" data-ela="${s.elasticity}" min="${e.lo}" max="${e.hi}" step="${e.step}" value="${cur(s.elasticity)}"></label>
      <p>${te(s.elasticity, "help")} ${T("Rango plausible", "Plausible range")}: ${e.lo} – ${e.hi} · ${T("valor central", "central value")}: ${e.default}.</p></div>`;
  })() : "";
  return `<div class="lever${changed ? " changed" : ""}${s.sub ? " sub" : ""}" data-k="${k}">
    <div class="lever-top"><span class="lever-label">${tl(k, "label")}</span>${confBadge(s.conf)}</div>
    <div class="lever-ctl">${ctl}<output>${fmtLever(s, v)}</output></div>
    <div class="lever-today">${T("Hoy", "Today")}: ${fmtLever(s, def)}${changed ? ` · <button class="linkbtn" data-reset="${k}">${T("volver a hoy", "reset")}</button>` : ""}</div>
    <details class="lever-more"><summary>${T("Evidencia y supuestos", "Evidence & assumptions")}</summary>
      <p>${tl(k, "help")}</p><p>${tl(k, "evidence")}</p>${ela}</details>
  </div>`;
}
function setLever(k, v, rerender = true) {
  const spec = ps.cat.levers[k] || ps.cat.elasticities[k];
  if (Math.abs(v - spec.default) < 1e-12) delete ps.levers[k]; else ps.levers[k] = v;
  ps.preset = matchPreset();
  const box = $(`#pol-levers .lever[data-k="${k}"]`);
  if (box && rerender) {
    $("output", box).textContent = fmtLever(spec, v);
    box.classList.toggle("changed", k in ps.levers);
    $(".lever-today", box).innerHTML = `${T("Hoy", "Today")}: ${fmtLever(spec, spec.default)}`;
  }
  $$("#pol-presets .pol-preset").forEach((b) => b.classList.toggle("on", b.dataset.p === ps.preset));
  renderPresetInfo();
  renderLeverSummary();
}
function matchPreset() {
  const keys = Object.keys(ps.levers).filter((k) => ps.cat.levers[k]);
  for (const [p, def] of Object.entries(ps.cat.presets)) {
    const pk = Object.keys(def.levers);
    if (pk.length === keys.length && pk.every((k) => Math.abs(def.levers[k] - (ps.levers[k] ?? NaN)) < 1e-12)) return p;
  }
  return null;
}
function renderPresetInfo() {
  const box = $("#pol-preset-info");
  box.hidden = !ps.preset;
  if (!ps.preset) return;
  const k = ps.preset;
  box.innerHTML = `<h3 class="pol-h3">${tp(k, "label")}</h3><p>${tp(k, "desc")}</p>
    <div class="grid-2 pol-ev"><div><h4>${T("Qué dice la evidencia", "What the evidence says")}</h4><p>${tp(k, "evidence")}</p></div>
    <div><h4>${T("Advertencias", "Caveats")}</h4><p>${tp(k, "caveats")}</p></div></div>`;
}
function renderLeverSummary() {
  const ch = Object.keys(ps.levers);
  $("#pol-summary-levers").innerHTML = ch.length
    ? `<b>${T("Cambios respecto a hoy", "Changes from today")}:</b> ` + ch.map((k) => {
      const s = ps.cat.levers[k] || ps.cat.elasticities[k];
      const name = ps.cat.levers[k] ? shortLever(k) : te(k, "label");
      return `${name} ${fmtLever(s.kind ? s : { kind: "num" }, s.default)} → <b>${fmtLever(s.kind ? s : { kind: "num" }, ps.levers[k])}</b>`;
    }).join(" · ")
    : T("Ninguna palanca cambiada: todo como hoy.", "No lever changed: everything as today.");
}

// -------------------------------------------------------------- simular
function busy(on, text) {
  ps.busy = on;
  ctx.setBusy(on, text);
  $("#pol-run").disabled = on;
  $("#pol-me-update").disabled = on;
  $("#pol-robust").disabled = on;
}
function requestBody() {
  return { levers: { ...ps.levers }, shock: $("#pol-shock").value || "none", shock_month: 24,
           months: +$("#pol-months").value, households: +$("#pol-households").value, seeds: +$("#pol-seeds").value };
}
function meBody() {
  return { ...ps.body, age: +$("#me-age").value || 25, income: Math.max(0, +$("#me-income").value || 0),
           tenure: $("#me-tenure").value, savings: Math.max(0, +$("#me-savings").value || 0),
           years: +$("#me-years").value, region_factor: +$("#me-region").value };
}
async function runPolicy() {
  if (ps.busy) return;
  if (!Object.keys(ps.levers).length) {
    $("#pol-runinfo").innerHTML = `<span class="t2">${T("Mueve al menos una palanca o elige una medida de ejemplo.", "Move at least one lever or pick an example policy.")}</span>`;
    return;
  }
  const body = requestBody();
  const t0 = performance.now();
  busy(true, T(`Simulando ${body.seeds} economías con y sin la medida…`, `Simulating ${body.seeds} economies with and without the policy…`));
  $("#pol-runinfo").innerHTML = `<span><span class="loading"></span> ${T("Puede tardar hasta un minuto en el servidor gratuito.", "It can take up to a minute on the free server.")}</span>`;
  try {
    ps.sim = await ctx.api("/api/policy/simulate", body);
    ps.body = body;
    ps.robust = null;
    ps.secs = (performance.now() - t0) / 1000;
    ps.me = null;
    await runMe().catch(() => null);
    renderResults();
    if (location.hash !== "#policy") location.hash = "#policy";
  } catch (err) {
    $("#pol-runinfo").innerHTML = `<span class="neg">Error: ${err.message}</span>`;
  } finally {
    busy(false);
  }
}
async function runMe() {
  ps.me = await ctx.api("/api/policy/household", meBody());
}
async function runRobust() {
  if (!ps.body || ps.busy) return;
  busy(true, T("Repitiendo la medida con supuestos extremos…", "Re-running with extreme assumptions…"));
  try {
    const res = await ctx.api("/api/policy/simulate", { ...ps.body, robustness: true });
    ps.robust = res.robustness;
    renderRobust();
  } catch (err) {
    $("#pol-robust-out").hidden = false;
    $("#pol-robust-out").innerHTML = `<p class="neg">Error: ${err.message}</p>`;
  } finally {
    busy(false);
  }
}

// -------------------------------------------------------------- resultados
const KPIS = [
  ["unemployment:mean", ["Paro medio", "Average unemployment"], "pp"],
  ["real_wage:last", ["Salario real de referencia", "Reference real wage"], "rel"],
  ["_rent_paid:last", ["Alquiler que se paga / salario mediano", "Rent paid / median wage"], "pp"],
  ["price_to_income:last", ["Años de salario por vivienda", "Years of salary per home"], "x"],
  ["homeownership:last", ["Hogares propietarios", "Home-owning households"], "pp"],
  ["debt_gdp:last", ["Deuda pública / PIB", "Public debt / GDP"], "pp"],
  ["inflation:mean", ["Inflación media", "Average inflation"], "pp"],
  ["gini_income:mean", ["Desigualdad de la renta (Gini)", "Income inequality (Gini)"], "dec"],
];
function level(kind, v) {
  if (kind === "pp") return fmt("pct", v);
  if (kind === "rel") return fmt("idx", v);
  if (kind === "x") return fmt("x", v);
  return fmt("dec", v);
}
function delta(kind, v, base) {
  if (v == null) return "—";
  if (kind === "pp") return fmt("pp", v, Math.abs(v) < 0.001 ? 2 : 1);
  if (kind === "rel") return signed(fmt("pct", v / base, 1), v);
  if (kind === "x") return signed(fmt("x", v), v);
  return signed(v.toLocaleString(LOCALE(), { minimumFractionDigits: 3, maximumFractionDigits: 3 }), v);
}

function renderResults() {
  const s = ps.sim;
  if (!s) return;
  $("#pol-empty").hidden = true;
  $("#pol-results").hidden = false;
  ctx.setSfc(s.sfc_max_error);
  $("#pol-runinfo").innerHTML = `
    <span><b>${ps.preset ? tp(ps.preset, "label") : T("Medida personalizada", "Custom policy")}</b>${s.shock !== "none" ? ` · ${ctx.shockLabel(s.shock)} (${T("año 3", "year 3")})` : ""}</span>
    <span>${s.seeds} × 2 ${T("simulaciones", "runs")} × ${s.households.toLocaleString(LOCALE())} ${T("hogares", "households")} × ${s.months / 12} ${T("años", "years")}</span>
    <span>${(ps.secs || 0).toFixed(1)} s</span>
    <span class="check">✓ ${T("contabilidad cuadrada", "books balance")} (${s.sfc_max_error.toExponential(1)})</span>`;
  renderTradeoffs();
  $("#pol-kpis").innerHTML = KPIS.map(([k, lab, kind]) => {
    const m = s.macro[k];
    const b = m.base.p50, p = m.policy.p50;
    return `<div class="card kpi"><div class="k">${T(...lab)}</div><div class="v">${delta(kind, m.diff.p50, b)}</div>
      <div class="r">${T("Sin", "Without")}: ${level(kind, b)} → ${T("con", "with")}: ${level(kind, p)}</div>
      <div class="r">${T("Rango", "Range")}: ${delta(kind, m.diff.p10, b)} … ${delta(kind, m.diff.p90, b)}</div></div>`;
  }).join("");
  renderMe();
  renderWho();
  renderCharts();
  renderConfidence();
  renderRobust();
  renderSobol();
  renderLimits();
}

function groupNames() {
  return {
    decile: Array.from({ length: 10 }, (_, i) => T(`Decil ${i + 1} de renta`, `Income decile ${i + 1}`)),
    age: ps.cat.age_groups.map((a) => `${a} ${T("años", "years")}`),
    tenure: Object.keys(ps.cat.tenures).map((k) => (en() && POLICY_EN.tenures[k]) || ps.cat.tenures[k]),
  };
}
function renderTradeoffs() {
  const s = ps.sim, names = groupNames(), win = [], lose = [];
  for (const dim of ["decile", "age", "tenure"]) {
    s.groups[dim].forEach((r, i) => {
      const v = r.after_housing;
      if (v.p50 > 0.003 && v.p10 > 0) win.push({ name: names[dim][i], v: v.p50 });
      if (v.p50 < -0.003 && v.p90 < 0) lose.push({ name: names[dim][i], v: v.p50 });
    });
  }
  const list = (arr) => arr.sort((a, b) => Math.abs(b.v) - Math.abs(a.v)).slice(0, 6)
    .map((x) => `${x.name} <b class="mono">${fmt("pp", x.v, 1).replace(" pp", " %")}</b>`).join(", ");
  const debt = s.macro["debt_gdp:last"].diff, un = s.macro["unemployment:mean"].diff;
  const yrs = s.months / 12;
  const lines = [];
  lines.push(`<p><span class="tw win">${T("Ganan", "Gain")}</span> ${win.length ? list(win) : T("ningún grupo de forma clara.", "no group clearly.")}</p>`);
  lines.push(`<p><span class="tw lose">${T("Pierden", "Lose")}</span> ${lose.length ? list(lose) : T("ningún grupo de forma clara.", "no group clearly.")}</p>`);
  lines.push(`<p class="t2 pol-small">${T("Medido como renta que queda tras pagar la vivienda (alquiler o hipoteca), media de los", "Measured as income left after paying for housing (rent or mortgage), average over the")} ${yrs} ${T("años. «De forma clara»: el signo se mantiene en el 80 % de las simulaciones.", "years. “Clearly”: the sign holds in 80 % of runs.")}</p>`);
  const dDebt = fmt("pp", debt.p50, 1);
  lines.push(`<p><span class="tw neutral">${T("Estado", "State")}</span> ${T("la deuda pública acaba", "public debt ends")} <b class="mono">${dDebt}</b> ${T("del PIB respecto a no hacer nada", "of GDP relative to doing nothing")} (${fmt("pp", debt.p10, 1)} … ${fmt("pp", debt.p90, 1)}).
    ${T("Paro medio", "Average unemployment")}: <b class="mono">${fmt("pp", un.p50, 2)}</b>.${s.levers.public_housing ? ` ${T("A cambio de la deuda, el Estado es dueño de las viviendas públicas que construye.", "In exchange for the debt, the State owns the public homes it builds.")}` : ""}</p>`);
  lines.push(`<p class="pol-neutral">${T("Esto no dice si la medida es buena o mala: depende de cuánto valore cada uno a cada grupo y cada objetivo (empleo, vivienda, deuda, igualdad). Compara varias medidas antes de opinar.", "This does not say whether the policy is good or bad: that depends on how much one values each group and each goal (jobs, housing, debt, equality). Compare several policies before forming a view.")}</p>`);
  $("#pol-tradeoffs").innerHTML = lines.join("");
}

// ------------------------------------------------------------ ¿Y a mí?
const ME = [
  ["disp", ["Ingresos netos al mes", "Net income per month"], ["Tras IRPF, cotizaciones y otros impuestos directos; media de los años simulados", "After income tax and contributions; average over the simulated years"]],
  ["housing", ["Gasto en vivienda al mes", "Housing cost per month"], ["Alquiler o cuota de la hipoteca (con amortización)", "Rent or mortgage payment (including principal)"]],
  ["after_housing", ["Te queda tras pagar la vivienda", "Left after paying for housing"], ["Ingresos netos menos gasto en vivienda", "Net income minus housing cost"]],
  ["buy", ["Probabilidad de comprar casa", "Chance of buying a home"], null],
  ["wealth", ["Patrimonio al final", "Net worth at the end"], ["Ahorros, acciones y vivienda menos deudas, en euros de hoy", "Savings, shares and housing minus debts, in today's euros"]],
  ["pension", ["Pensión pública estimada", "Estimated public pension"], ["Al mes, en euros de hoy, con las reglas y salarios del final de la simulación", "Per month, in today's euros, with the rules and wages at the end of the run"]],
];
function renderMe() {
  const box = $("#pol-me");
  if (!ps.me) { box.innerHTML = `<p class="t2">${T("Rellena «Tu hogar» y pulsa «Actualizar con mis datos».", "Fill in “Your household” and press “Update with my data”.")}</p>`; $("#pol-me-sub").textContent = ""; return; }
  const h = ps.me, m = h.matched, o = h.outcomes, tenure = $("#me-tenure").selectedOptions[0].textContent.toLowerCase();
  $("#pol-me-sub").innerHTML = T(
    `Comparado con <b>${m.n}</b> hogares simulados parecidos al tuyo: ${Math.round(m.age.p10)}–${Math.round(m.age.p90)} años, ${eur(m.income.p10)}–${eur(m.income.p90)} brutos al mes, ahorros ${eur(m.savings.p10)}–${eur(m.savings.p90)}${m.same_tenure === 1 ? `, todos con tu misma situación de vivienda (${tenure})` : ""}. Las bandas son el rango 10–90 % entre esos hogares: no a todos los hogares parecidos les va igual.`,
    `Compared with <b>${m.n}</b> simulated households similar to yours: aged ${Math.round(m.age.p10)}–${Math.round(m.age.p90)}, ${eur(m.income.p10)}–${eur(m.income.p90)} gross a month, savings ${eur(m.savings.p10)}–${eur(m.savings.p90)}${m.same_tenure === 1 ? `, all in your housing situation (${tenure})` : ""}. Bands are the 10–90 % range across those households: similar households do not all fare the same.`);
  box.innerHTML = ME.map(([k, lab, sub]) => {
    if (k === "buy") {
      const b = o.buy;
      const title = `${T(...lab)} ${T("en", "within")} ${h.years} ${T("años", "years")}`;
      if (!b) return `<div class="card me-card"><h4>${title}</h4><p class="t2 pol-small">${$("#me-tenure").value === "renter" ? T("No hay suficientes inquilinos parecidos para estimarlo.", "Not enough similar renters to estimate it.") : T("Ya eres propietario.", "You already own a home.")}</p></div>`;
      const pc = (v) => fmt("pct", v, 0);
      return `<div class="card me-card"><h4>${title}</h4>
        <div class="me-row"><span>${T("Sin la medida", "Without")}</span><b>${pc(b.base.p50)}</b><i>${pc(b.base.p10)} – ${pc(b.base.p90)}</i></div>
        <div class="me-row"><span>${T("Con la medida", "With")}</span><b>${pc(b.policy.p50)}</b><i>${pc(b.policy.p10)} – ${pc(b.policy.p90)}</i></div>
        <div class="me-row d"><span>${T("Diferencia", "Difference")}</span><b>${fmt("pp", b.diff.p50, 0)}</b><i>${fmt("pp", b.diff.p10, 0)} … ${fmt("pp", b.diff.p90, 0)}</i></div>
        <p class="muted pol-small">${T("Banda: incertidumbre de la estimación (remuestreo). En el modelo la barrera principal es la entrada: no hay ayuda familiar.", "Band: estimation uncertainty (bootstrap). In the model the main barrier is the down payment: there is no family help.")}</p></div>`;
    }
    const x = o[k];
    const dv = (v) => (v == null ? "—" : `${v > 0 ? "+" : ""}${eur(v)}`);
    let extra = "";
    if (k === "housing") extra = `<p class="muted pol-small">${T("Sobre tus ingresos netos", "Of your net income")}: ${fmt("pct", o.burden.base.p50, 0)} → ${fmt("pct", o.burden.policy.p50, 0)}${h.region_factor !== 1 ? ` · ${T("ajustado por zona", "adjusted for area")} ×${h.region_factor}` : ""}</p>`;
    if (k === "pension" && h.retired_by_end < 0.5) extra = `<p class="muted pol-small">${T("Proyección: la pensión depende de reglas que pueden cambiar muchas veces antes de que te jubiles.", "Projection: the pension depends on rules that may change many times before you retire.")}</p>`;
    return `<div class="card me-card"><h4>${T(...lab)}</h4>
      <div class="me-row"><span>${T("Sin la medida", "Without")}</span><b>${eur(x.base.p50)}</b><i>${eur(x.base.p10)} – ${eur(x.base.p90)}</i></div>
      <div class="me-row"><span>${T("Con la medida", "With")}</span><b>${eur(x.policy.p50)}</b><i>${eur(x.policy.p10)} – ${eur(x.policy.p90)}</i></div>
      <div class="me-row d"><span>${T("Diferencia", "Difference")}</span><b>${dv(x.diff.p50)}</b><i>${dv(x.diff.p10)} … ${dv(x.diff.p90)}</i></div>
      ${sub ? `<p class="muted pol-small">${T(...sub)}</p>` : ""}${extra}</div>`;
  }).join("");
}

// -------------------------------------------------------- quién gana
const WHO = { after_housing: ["Renta tras pagar la vivienda", "Income after housing"], disp: ["Renta disponible", "Disposable income"], wealth: ["Patrimonio (€)", "Net worth (€)"] };
function renderWho() {
  const tabs = $("#pol-who-tabs");
  tabs.innerHTML = Object.entries(WHO).map(([k, l]) => `<button data-w="${k}" class="${k === ps.who ? "on" : ""}">${T(...l)}</button>`).join("");
  $$("button", tabs).forEach((b) => b.addEventListener("click", () => { ps.who = b.dataset.w; renderWho(); }));
  const s = ps.sim, names = groupNames(), f = ps.who, money = f === "wealth";
  const all = Object.values(s.groups).flat().flatMap((r) => [r[f].p10, r[f].p90]).filter((v) => v != null);
  const maxAbs = Math.max(...all.map(Math.abs), money ? 1 : 1e-4);
  const val = (v) => (money ? `${v > 0 ? "+" : ""}${eur(v)}` : fmt("pp", v, 1).replace(" pp", " %"));
  const pos = (v) => 50 + (v / maxAbs) * 48;
  const titles = { decile: ["Por decil de renta", "By income decile"], age: ["Por edad", "By age"], tenure: ["Por vivienda", "By housing tenure"] };
  $("#pol-who").innerHTML = ["decile", "age", "tenure"].map((dim) => `<div class="card card-pad"><h4 class="pol-h4">${T(...titles[dim])}</h4>` +
    s.groups[dim].map((r, i) => {
      const v = r[f], m = v.p50;
      const a = pos(Math.min(0, m)), w = Math.abs(pos(m) - pos(0));
      return `<div class="rb-row" title="${names[dim][i]} · n≈${r.n}"><span>${dim === "decile" ? `D${i + 1}` : names[dim][i]}</span>
        <span class="rb"><i class="rb-zero"></i><i class="rb-bar ${m >= 0 ? "up" : "down"}" style="left:${a}%;width:${w}%"></i>
        <i class="rb-band" style="left:${pos(v.p10)}%;width:${Math.max(0.5, pos(v.p90) - pos(v.p10))}%"></i></span>
        <span class="val">${val(m)}</span></div>`;
    }).join("") + (dim === "decile" ? `<p class="muted pol-small">${T("D1 = 10 % con menos renta al empezar (incluye pensiones y prestaciones)", "D1 = lowest-income 10 % at the start (pensions and benefits included)")}</p>` : "") + `</div>`).join("");
}

// ------------------------------------------------------------ gráficos
const CHARTS = [
  ["unemployment", ["Paro", "Unemployment"], "pct", true],
  ["real_wage", ["Salario real de referencia", "Reference real wage"], "idx", false],
  ["_rent_paid", ["Alquiler que se paga / salario mediano", "Rent paid / median wage"], "pct", false],
  ["price_to_income", ["Años de salario por vivienda", "Years of salary per home"], "x", false],
  ["homeownership", ["Hogares propietarios", "Home-owning households"], "pct", false],
  ["debt_gdp", ["Deuda pública / PIB", "Public debt / GDP"], "pct", false],
];
function renderCharts() {
  const s = ps.sim, box = $("#pol-charts");
  box.innerHTML = "";
  const marker = s.shock !== "none" ? s.shock_month : null;
  for (const [k, lab, kind, zero] of CHARTS) {
    const card = document.createElement("div");
    card.className = "card chart-card";
    card.innerHTML = `<h4>${T(...lab)}</h4><div class="sub">${kind === "idx" ? T("Índice, inicio = 100", "Index, start = 100") : "&nbsp;"}</div><div class="chart"></div>`;
    box.appendChild(card);
    lineChart($(".chart", card), { kind, zero, marker, height: 190, series: [
      { name: T("Sin la medida", "Without the policy"), color: "var(--muted)", ...s.series[k].base },
      { name: T("Con la medida", "With the policy"), color: "var(--s2)", ...s.series[k].policy },
    ] });
  }
}

// ------------------------------------------------------------ confianza
function renderConfidence() {
  const keys = Object.keys(ps.sim.levers).filter((k) => ps.cat.levers[k]);
  const rows = keys.map((k) => {
    const s = ps.cat.levers[k];
    const e = s.elasticity ? ps.cat.elasticities[s.elasticity] : null;
    const used = e ? (ps.sim.levers[s.elasticity] ?? e.default) : null;
    return `<tr><td>${tl(k, "label")}</td><td>${fmtLever(s, s.default)} → <b>${fmtLever(s, ps.sim.levers[k])}</b></td><td>${confBadge(s.conf)}</td>
      <td style="white-space:normal">${e ? `${te(s.elasticity, "label")}: <b>${used}</b> (${T("rango", "range")} ${e.lo} – ${e.hi})` : `<span class="muted">${T("Sin elasticidad propia: efecto mecánico + supuestos generales", "No own elasticity: mechanical effect + general assumptions")}</span>`}</td></tr>`;
  }).join("");
  const ev = keys.map((k) => `<p><b>${shortLever(k)}.</b> ${tl(k, "evidence")}</p>`).join("");
  $("#pol-conf").innerHTML = `<div class="table-wrap"><table class="data pol-table"><thead><tr><th>${T("Palanca", "Lever")}</th><th>${T("Hoy → medida", "Today → policy")}</th><th>${T("Confianza", "Confidence")}</th><th>${T("Supuesto clave", "Key assumption")}</th></tr></thead><tbody>${rows}</tbody></table></div>
    <div class="pol-evidence">${ev}</div>
    <p class="muted pol-small">${T("Confianza alta: efecto mecánico bien medido. Media: mecanismo claro pero tamaño discutido. Baja: la evidencia discrepa o el modelo omite reacciones importantes.", "High confidence: well-measured mechanical effect. Medium: clear mechanism but disputed size. Low: the evidence disagrees or the model omits important reactions.")}</p>`;
}
const RKEYS = { "unemployment:mean": [["Paro", "Unemployment"], "pp"], "real_wage:last": [["Salario real", "Real wage"], "idx"], "debt_gdp:last": [["Deuda / PIB", "Debt / GDP"], "pp"], "homeownership:last": [["Propietarios", "Homeowners"], "pp"], "_rent_paid:last": [["Alquiler pagado", "Rent paid"], "pp"] };
function rfmt(kind, v) { return kind === "idx" ? signed(fmt("pct", v, 1), v).replace("%", "pt") : fmt("pp", v, 2); }
function renderRobust() {
  const box = $("#pol-robust-out");
  const r = ps.robust;
  box.hidden = !r;
  if (!r) return;
  const elas = Object.entries(r.elasticities);
  if (!elas.length) {
    box.innerHTML = `<p class="t2">${T("Las palancas elegidas no dependen de una elasticidad de comportamiento propia en el modelo. Su incertidumbre está en los supuestos generales (abajo, si es una medida de ejemplo) y en lo que el modelo no tiene en cuenta (lista final).", "The chosen levers do not depend on a behavioural elasticity of their own in the model. Their uncertainty lies in the general assumptions (below, for example policies) and in what the model leaves out (final list).")}</p>`;
    return;
  }
  box.innerHTML = `<h4 class="pol-h4">${T("Efecto de la medida con cada supuesto en sus extremos", "Effect of the policy with each assumption at its extremes")}</h4>
    <p class="t2 pol-small">${T(`Diferencia con y sin la medida; mediana de ${r.seeds} simulaciones. Si las dos filas de un supuesto dicen cosas distintas, la conclusión depende de él.`, `Difference with vs without the policy; median of ${r.seeds} runs. If a pair of rows disagree, the conclusion hinges on that assumption.`)}</p>
    <div class="table-wrap"><table class="data"><thead><tr><th>${T("Supuesto", "Assumption")}</th>${r.keys.map((k) => `<th>${T(...RKEYS[k][0])}</th>`).join("")}</tr></thead><tbody>` +
    elas.flatMap(([k, row]) => ["lo", "hi"].map((end) => `<tr><td>${te(k, "label")} = <b>${row[`${end}_value`]}</b></td>${r.keys.map((key) => `<td>${rfmt(RKEYS[key][1], row[end][key])}</td>`).join("")}</tr>`)).join("") +
    `</tbody></table></div>`;
}
const SOBOL_OUT = {
  "unemployment:mean": [["Paro medio", "Average unemployment"], "pp"],
  "disp_bottom50": [["Renta del 50 % con menos ingresos", "Income of the bottom 50 %"], "rel"],
  "disp_top10": [["Renta del 10 % con más ingresos", "Income of the top 10 %"], "rel"],
  "_rent_paid:last": [["Alquiler pagado / salario", "Rent paid / wage"], "pp"],
  "homeownership:last": [["Hogares propietarios", "Home-owning households"], "pp"],
  "debt_gdp:last": [["Deuda pública / PIB", "Public debt / GDP"], "pp"],
};
function renderSobol() {
  const box = $("#pol-sobol");
  const sens = ps.cat.sensitivity?.presets?.[ps.preset];
  const same = sens && ps.preset && Object.keys(ps.sim.levers).every((k) => k in ps.cat.presets[ps.preset].levers);
  box.hidden = !same;
  if (!same) return;
  const f = (kind, v) => (kind === "rel" ? fmt("pp", v, 1).replace(" pp", " %") : fmt("pp", v, 2));
  box.innerHTML = `<h4 class="pol-h4">${T("¿Qué supuesto pesa más? (análisis de Sobol)", "Which assumption matters most? (Sobol analysis)")}</h4>
    <p class="t2 pol-small">${T(`Para esta medida de ejemplo se precalcularon ${sens.runs} simulaciones variando a la vez, dentro de su rango plausible, ${sens.factors.length} supuestos. Rango: efecto de la medida entre el percentil 10 y el 90. «Lo decide» es el supuesto con mayor índice total de Sobol, sin contar el azar.`, `For this example policy ${sens.runs} runs were precomputed, varying ${sens.factors.length} assumptions at once within their plausible range. Range: effect of the policy between the 10th and 90th percentile. “Driven by” is the assumption with the largest total Sobol index, net of randomness.`)}</p>
    <div class="table-wrap"><table class="data"><thead><tr><th>${T("Resultado", "Outcome")}</th><th>${T("Rango del efecto", "Effect range")}</th><th style="text-align:left">${T("Lo decide sobre todo", "Driven mostly by")}</th></tr></thead><tbody>` +
    Object.entries(SOBOL_OUT).map(([k, [lab, kind]]) => {
      const o = sens.outputs[k];
      if (!o) return "";
      const st = o.STc || o.ST;
      const i = st.indexOf(Math.max(...st.map((x) => x ?? -1)));
      const fac = sens.factors[i];
      const driver = o.noise_share > 0.6 || st[i] == null
        ? `<span class="muted">${T("sobre todo el azar de la simulación (efecto pequeño)", "mostly simulation randomness (small effect)")}</span>`
        : `${en() && POLICY_EN.elasticities[fac.key] ? POLICY_EN.elasticities[fac.key].label : tf(fac.key, fac.label)} <span class="muted">(ST ${st[i].toFixed(2)})</span>`;
      return `<tr><td>${T(...lab)}</td><td>${f(kind, o.p10)} … ${f(kind, o.p90)}</td><td style="text-align:left;font-family:var(--sans);white-space:normal">${driver}</td></tr>`;
    }).join("") + `</tbody></table></div>`;
}
function renderLimits() {
  const L = [
    ["Población estable: no envejece. Es la razón principal del debate sobre las pensiones, así que el modelo infravalora su coste a largo plazo.", "A stable population that does not age. That is the main reason for the pensions debate, so the model understates their long-run cost."],
    ["Nadie cambia cuántas horas trabaja por los impuestos; solo hay las reacciones explícitas del SMI, la prestación, las políticas activas y el tope al alquiler.", "Nobody changes how many hours they work because of taxes; the only reactions are the explicit ones for the minimum wage, benefits, active labour-market policies and the rent cap."],
    ["Economía cerrada: sin comercio exterior, inmigración ni empresas que se van. La deuda no sube la prima de riesgo.", "A closed economy: no foreign trade, migration or firms leaving. Debt does not raise the risk premium."],
    ["Un solo mercado de vivienda: todas las viviendas valen lo mismo y no hay regiones; el factor de zona solo escala tu gasto en vivienda.", "A single housing market: every home is worth the same and there are no regions; the area factor only scales your housing cost."],
    ["Las herencias pasan a un hogar de 20 años, así que hay más jóvenes propietarios que en la realidad, y no hay ayuda familiar para la entrada.", "Inheritances pass to a 20-year-old household, so there are more young homeowners than in reality, and there is no family help with the down payment."],
    ["Las medidas se pagan con deuda salvo que combines subidas de impuestos. El modelo no valora los servicios públicos en sí.", "Policies are debt-financed unless you combine them with tax rises. The model does not value public services in themselves."],
    ["Muestra mecanismos y órdenes de magnitud, no predicciones. Lo importante es la diferencia con y sin la medida, no el nivel.", "It shows mechanisms and orders of magnitude, not forecasts. What matters is the difference with vs without the policy, not the level."],
  ];
  $("#pol-limits").innerHTML = L.map((l) => `<li>${T(...l)}</li>`).join("");
}
