// Vistas de Sensibilidad (Sobol), Datos reales (calibración) y Blockchain (on-chain y contratos).
import { lineChart, fmt } from "/static/charts.js";
import { T, lang, LOCALE } from "/static/i18n.js";
import { api, state, regimeLabel, fromKey, sumLabel, sfmt } from "/static/app.js";

const $ = (s, root = document) => root.querySelector(s);
const cache = {};
async function load(path) {
  if (!cache[path]) cache[path] = await api(path);
  return cache[path];
}
const kpi = (k, v, r = "") => `<div class="card kpi"><div class="k">${k}</div><div class="v">${v}</div><div class="r">${r}</div></div>`;
const fail = (sel, err) => { $(sel).innerHTML = `<div class="card empty">${err.message}</div>`; };

// ============================================================ sensibilidad
const FACTORS_EN = {
  natural_unemployment: "Natural unemployment", phillips: "Phillips curve slope", mpc_high: "Propensity to consume (high incomes)",
  hoarding: "Consumption sensitivity to real rate", credibility: "Credibility of the rule", money_rate_sens: "Rate sensitivity to money",
  investment_rate_sens: "Investment sensitivity to rates", ltv: "Maximum mortgage LTV",
};
export async function renderSensitivity() {
  let d;
  try { d = await load("/api/sensitivity"); } catch (err) { return fail("#sens-bars", err); }
  const rs = $("#sens-regime"), os = $("#sens-output");
  const curR = rs.value || d.results[0].regime, curO = os.value || "inflation:mean";
  rs.innerHTML = d.results.map((r) => `<option value="${r.regime}">${regimeLabel(fromKey(r.regime))}</option>`).join("");
  os.innerHTML = Object.keys(d.results[0].outputs).map((k) => `<option value="${k}">${sumLabel(k)}</option>`).join("");
  rs.value = curR; os.value = curO;
  rs.onchange = os.onchange = renderSensitivity;
  const res = d.results.find((r) => r.regime === rs.value);
  const out = res.outputs[os.value];
  const fl = (f) => (lang() === "en" ? FACTORS_EN[f.key] : f.label);
  const noise = out.noise_share ?? 0;
  const usable = out.STc && out.STc[0] != null;
  const dec2 = (v) => v.toLocaleString(LOCALE(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const share = (x) => `${Math.round(x * 100)} %`;
  const rows = res.factors.map((f, i) => ({ f, s1: usable ? out.S1c[i] : 0, st: usable ? out.STc[i] : 0 }))
    .sort((a, b) => b.st - a.st);
  $("#sens-chart-title").textContent = `${sumLabel(os.value)} · ${regimeLabel(fromKey(res.regime))}`;
  const bar = (w, color, label) => `<div class="sens-bar" style="width:${Math.max(0.4, w * 80)}%;background:${color}"><span>${label}</span></div>`;
  $("#sens-bars").innerHTML =
    `<div class="sens-row"><span><b>${T("Azar de la simulación", "Simulation randomness")}</b></span><div class="sens-bars">${bar(noise, "var(--muted)", share(noise) + T(" de la varianza", " of the variance"))}</div></div>` +
    (usable ? rows.map((r) => `<div class="sens-row"><span>${fl(r.f)}</span><div class="sens-bars">${bar(r.st, "var(--s2)", dec2(r.st))}</div></div>`).join("")
      : `<p class="t2" style="font-size:13px;margin-top:12px">${T("El azar explica casi toda la varianza: ningún supuesto concreto determina este resultado dentro de este sistema.", "Chance explains almost all the variance: no single assumption determines this outcome within this system.")}</p>`);
  const top = rows[0], second = rows[1];
  $("#sens-text").innerHTML = T(
    `<p>En este sistema, <b>${sumLabel(os.value)}</b> vale de media ${sfmt(os.value, out.mean)} (desviación ${sfmt(os.value, out.std)}) cuando los ocho supuestos varían a la vez.</p>
     <p><b>El azar de la simulación explica ${share(noise)} de esa varianza</b>: es lo que varía el resultado con los mismos supuestos y distinta semilla. Los índices de la izquierda reparten el resto.</p>
     ${usable ? `<p>El supuesto que más pesa es <b>${fl(top.f)}</b>: interviene en ${share(top.st)} de la varianza no aleatoria (efecto total, con sus interacciones). Le sigue ${fl(second.f)} (${share(second.st)}).</p>`
              : `<p>Con tanto peso del azar, la lectura correcta es otra: las diferencias de reparto <i>entre sistemas</i> (Explorador) son sólidas, pero <i>dentro</i> de un sistema dependen sobre todo de la historia concreta de cada simulación.</p>`}
     <p>Un supuesto con ST cercano a 0 apenas importa: la conclusión es robusta a él.</p>`,
    `<p>In this system, <b>${sumLabel(os.value)}</b> averages ${sfmt(os.value, out.mean)} (std. ${sfmt(os.value, out.std)}) when the eight assumptions vary together.</p>
     <p><b>Simulation randomness explains ${share(noise)} of that variance</b>: how much the outcome moves with the same assumptions and a different seed. The indices on the left split the rest.</p>
     ${usable ? `<p>The most influential assumption is <b>${fl(top.f)}</b>: it is involved in ${share(top.st)} of the non-random variance (total effect, with interactions). Next is ${fl(second.f)} (${share(second.st)}).</p>`
              : `<p>With so much weight on chance, the right reading is different: distribution differences <i>between systems</i> (Explorer) are solid, but <i>within</i> a system they depend mostly on each run's particular history.</p>`}
     <p>An assumption with ST close to 0 barely matters: the conclusion is robust to it.</p>`);
  $("#sens-table").innerHTML = `<table class="data"><thead><tr><th>${T("Parámetro", "Parameter")}</th><th>${T("Rango", "Range")}</th><th>S1</th><th>ST</th></tr></thead><tbody>` +
    rows.map((r) => `<tr><td>${fl(r.f)}</td><td>${r.f.lo} – ${r.f.hi}</td><td>${usable ? dec2(r.s1) : "—"}</td><td>${usable ? dec2(r.st) : "—"}</td></tr>`).join("") +
    `</tbody></table><p class="muted" style="font-size:12px;margin-top:8px">${res.runs.toLocaleString(LOCALE())} ${T("simulaciones", "runs")} · N = ${res.n} · ${T("Jansen (ST) y Saltelli (S1), corregidos por el ruido de la simulación. S1 converge más despacio: con N = 128 es orientativo", "Jansen (ST) and Saltelli (S1), corrected for simulation noise. S1 converges more slowly: with N = 128 it is indicative")}</p>`;
}

// ============================================================ datos reales
const MOMENT_EN = {
  unemployment: "Average unemployment", inflation: "Average inflation", debt_gdp: "Public debt / GDP", credit_gdp: "Private debt / GDP",
  top10_wealth: "Wealth of the richest 10 %", bottom50_wealth: "Wealth of the poorest 50 %", gini_income: "Income Gini",
};
const PARAM_LABELS = {
  natural_unemployment: ["Paro natural", "Natural unemployment"], spirits_sd: ["Volatilidad de la confianza", "Volatility of confidence"],
  debt_to_gdp0: ["Deuda pública inicial / PIB", "Initial public debt / GDP"], gov_spending_share: ["Gasto público / PIB", "Public spending / GDP"],
  firm_leverage: ["Apalancamiento empresarial", "Corporate leverage"], mortgage_prob: ["Propietarios < 55 con hipoteca", "Owners < 55 with a mortgage"],
  wealth_sigma: ["Dispersión de la riqueza", "Wealth dispersion"],
};
export async function renderData() {
  let d;
  try { d = await load("/api/validation"); } catch (err) { return fail("#moments-table", err); }
  const c = d.calibration, sp = d.spain;
  const f = (kind, v) => (kind === "pct" ? fmt("pct", v) : fmt("dec", v));
  const d2 = (v) => v.toLocaleString(LOCALE(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const d1 = (v) => v.toLocaleString(LOCALE(), { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  $("#data-window").textContent = T(`España, media ${c.window} · modelo: sistema actual, mediana de 6 simulaciones`, `Spain, ${c.window} average · model: today's system, median of 6 runs`);
  $("#data-kpis").innerHTML = [
    kpi(T("Distancia a los datos", "Distance to data"), `${d1(c.distance_before)} → ${d1(c.distance_after)}`, T("antes → después de calibrar", "before → after calibration")),
    kpi(T("Paro: España / modelo", "Unemployment: Spain / model"), `${fmt("pct", c.real.unemployment, 0)} / ${fmt("pct", c.after.unemployment, 0)}`, c.window),
    kpi(T("10 % más rico", "Richest 10 %"), `${fmt("pct", c.real.top10_wealth, 0)} / ${fmt("pct", c.after.top10_wealth, 0)}`, T("España (BCE) / modelo", "Spain (ECB) / model")),
    kpi(T("Ley de Okun", "Okun's law"), `${d2(c.real.okun)} / ${d2(c.after.okun)}`, T("corr. PIB–Δparo · España / modelo", "corr. GDP–Δunemployment · Spain / model")),
    kpi(T("Curva de Phillips", "Phillips curve"), `${d2(c.real.phillips)} / ${d2(c.after.phillips)}`, T("corr. paro–salarios · España / modelo", "corr. unemployment–wages · Spain / model")),
    kpi(T("Datos descargados", "Data fetched"), sp.fetched, `${Object.keys(sp.series).length} ${T("series · Eurostat y BCE", "series · Eurostat & ECB")}`),
  ].join("");
  const rows = Object.entries(c.moments).map(([k, m]) => {
    const err = (c.after[k] - c.real[k]) / Math.max(Math.abs(c.real[k]), 0.02);
    const ok = Math.abs(err) < 0.25;
    return `<tr><td>${lang() === "en" ? MOMENT_EN[k] : m.label}</td><td>${f(m.fmt, c.real[k])}</td><td class="muted">${f(m.fmt, c.before[k])}</td><td><b>${f(m.fmt, c.after[k])}</b></td><td class="${ok ? "pos-c" : "neg"}">${err >= 0 ? "+" : ""}${Math.round(err * 100)} %</td></tr>`;
  });
  $("#moments-table").innerHTML = `<table class="data"><thead><tr><th>${T("Momento", "Moment")}</th><th>${T("España", "Spain")}</th><th>${T("Antes", "Before")}</th><th>${T("Calibrado", "Calibrated")}</th><th>${T("Desvío", "Gap")}</th></tr></thead><tbody>${rows.join("")}</tbody></table>`;
  const sty = [
    ["okun", T("Ley de Okun (corr. crecimiento–Δparo)", "Okun's law (corr. growth–Δunemployment)"), T("negativa", "negative")],
    ["phillips", T("Curva de Phillips (corr. paro–salarios)", "Phillips curve (corr. unemployment–wages)"), T("negativa", "negative")],
    ["vol_ratio", T("Volatilidad inflación / crecimiento", "Volatility inflation / growth"), "< 1"],
  ];
  $("#stylized-table").innerHTML = `<table class="data"><thead><tr><th>${T("Hecho", "Fact")}</th><th>${T("Esperado", "Expected")}</th><th>${T("España", "Spain")}</th><th>${T("Antes", "Before")}</th><th>${T("Calibrado", "Calibrated")}</th></tr></thead><tbody>` +
    sty.map(([k, label, exp]) => `<tr><td>${label}</td><td>${exp}</td><td>${d2(c.real[k])}</td><td class="muted">${d2(c.before[k])}</td><td><b>${d2(c.after[k])}</b></td></tr>`).join("") + `</tbody></table>`;
  $("#params-table").innerHTML = `<table class="data"><thead><tr><th>${T("Parámetro", "Parameter")}</th><th>${T("Ilustrativo", "Illustrative")}</th><th>${T("Calibrado", "Calibrated")}</th></tr></thead><tbody>` +
    Object.entries(c.params).map(([k, v]) => `<tr><td>${T(...PARAM_LABELS[k])}</td><td class="muted">${c.params_before[k]}</td><td><b>${v}</b></td></tr>`).join("") + `</tbody></table>`;
  $("#data-sources").textContent = T(`Fuentes: Eurostat (une_rt_a, prc_hicp_aind, gov_10dd_edpt1, tipspd20, prc_hpi_a, nama_10_gdp, ilc_di12) y BCE (Distributional Wealth Accounts). Descargadas el ${sp.fetched} con scripts/fetch_data.py. La línea discontinua es la media del modelo calibrado.`,
    `Sources: Eurostat (une_rt_a, prc_hicp_aind, gov_10dd_edpt1, tipspd20, prc_hpi_a, nama_10_gdp, ilc_di12) and the ECB (Distributional Wealth Accounts). Fetched on ${sp.fetched} with scripts/fetch_data.py. The dashed line is the calibrated model's mean.`);
  const s = sp.series;
  const hpiReal = Object.fromEntries(Object.entries(s.house_index.values).filter(([y]) => s.hicp_index.values[y]).map(([y, v]) => [y, (v / s.hicp_index.values[y])]));
  const charts = [
    ["unemployment", T("Paro", "Unemployment"), "pct", s.unemployment.values, c.after.unemployment],
    ["inflation", T("Inflación (IPCA)", "Inflation (HICP)"), "pct", s.inflation.values, c.after.inflation],
    ["debt_gdp", T("Deuda pública / PIB", "Public debt / GDP"), "pct", s.debt_gdp.values, c.after.debt_gdp],
    ["top10_wealth", T("Riqueza del 10 % más rico", "Wealth of the richest 10 %"), "pct", s.top10_wealth.values, c.after.top10_wealth],
    ["credit_gdp", T("Deuda privada / PIB", "Private debt / GDP"), "pct", s.credit_gdp.values, c.after.credit_gdp],
    ["house", T("Precio real de la vivienda (2015 = 100)", "Real house price (2015 = 100)"), "idx", hpiReal, null],
  ];
  const box = $("#spain-charts");
  box.innerHTML = charts.map(([k, title]) => `<div class="card chart-card"><h4>${title}</h4><div class="sub">${T("España", "Spain")} · ${k === "top10_wealth" ? T("BCE", "ECB") : "Eurostat"}</div><div class="chart" id="sp-${k}"></div></div>`).join("");
  for (const [k, title, kind, values, ref] of charts) {
    const years = Object.keys(values).filter((y) => values[y] != null);
    lineChart($(`#sp-${k}`), { series: [{ name: title, color: "var(--s1)", p50: years.map((y) => values[y]) }], kind, ref, xLabels: years, zero: kind === "pct" && k === "inflation" });
  }
}

// ============================================================ blockchain
export async function renderChain() {
  let oc, ct;
  try { [oc, ct] = await Promise.all([load("/api/onchain"), load("/api/contracts")]); } catch (err) { return fail("#chain-kpis", err); }
  const b = oc.bitcoin, st = oc.stablecoins, loc = LOCALE();
  const lastUsd = st.monthly_usd.at(-1).usd;
  const eur = st.by_peg.peggedEUR || 0;
  $("#chain-kpis").innerHTML = [
    kpi(T("Bloque de Bitcoin", "Bitcoin block"), b.height.toLocaleString(loc), `${b.blocks_to_halving.toLocaleString(loc)} ${T("bloques al próximo halving", "blocks to next halving")}`),
    kpi(T("Bitcoin emitidos", "Bitcoin issued"), `${(b.supply_reported / 1e6).toLocaleString(loc, { maximumFractionDigits: 2 })} M`, `${T("de", "of")} ${(b.max_supply / 1e6).toLocaleString(loc, { maximumFractionDigits: 0 })} M · ${fmt("pct", b.supply_reported / b.max_supply)}`),
    kpi(T("Inflación de Bitcoin", "Bitcoin inflation"), fmt("pct", b.annual_inflation, 2), T("anual · calibra la oferta fija", "annual · calibrates fixed supply")),
    kpi(T("Recompensa por bloque", "Block reward"), `${b.reward.toLocaleString(loc, { maximumFractionDigits: 3 })} BTC`, T("según el protocolo", "per the protocol")),
    kpi("Stablecoins", `${fmt("big", lastUsd)} $`, `${st.top_usd[0].symbol} ${fmt("pct", st.top_usd[0].circulating / lastUsd, 0)} · ${st.top_usd[1].symbol} ${fmt("pct", st.top_usd[1].circulating / lastUsd, 0)}`),
    kpi(T("Stablecoins en euros", "Euro stablecoins"), `${fmt("big", eur)} €`, `${fmt("pct", eur / lastUsd, 2)} ${T("del total", "of the total")}`),
  ].join("");
  // calendario del protocolo
  const sched = b.schedule.filter((r) => r.year <= 2060);
  const yearNow = new Date(oc.fetched).getFullYear();
  $("#btc-sub").textContent = T(`Millones de BTC · oferta real hoy ${(b.supply_reported / 1e6).toLocaleString(loc, { maximumFractionDigits: 3 })} M frente a ${(b.supply_protocol / 1e6).toLocaleString(loc, { maximumFractionDigits: 3 })} M que implica el protocolo (la diferencia son recompensas no reclamadas)`,
    `Million BTC · actual supply today ${(b.supply_reported / 1e6).toLocaleString(loc, { maximumFractionDigits: 3 })} M vs ${(b.supply_protocol / 1e6).toLocaleString(loc, { maximumFractionDigits: 3 })} M implied by the protocol (the gap is unclaimed rewards)`);
  lineChart($("#btc-chart"), { series: [{ name: T("Oferta", "Supply"), color: "var(--s2)", p50: sched.map((r) => r.supply / 1e6) }], kind: "x",
    xLabels: sched.map((r) => String(r.year)), marker: sched.findIndex((r) => r.year === yearNow),
    tipLabel: (i) => `${sched[i].year} · ${T("inflación", "inflation")} ${sched[i].inflation != null ? fmt("pct", sched[i].inflation, 2) : "—"}` });
  const months = st.monthly_usd.filter((_, i) => i % 1 === 0);
  $("#stable-sub").textContent = T(`Miles de millones de dólares · ${st.top_usd.slice(0, 3).map((t) => t.symbol).join(", ")} dominan; las de euros son ${fmt("pct", eur / lastUsd, 2)}`,
    `Billion dollars · ${st.top_usd.slice(0, 3).map((t) => t.symbol).join(", ")} dominate; euro ones are ${fmt("pct", eur / lastUsd, 2)}`);
  lineChart($("#stable-chart"), { series: [{ name: "Stablecoins", color: "var(--s1)", p50: months.map((m) => m.usd / 1e9) }], kind: "x", xLabels: months.map((m) => m.month) });

  const demo = ct.demo;
  if (demo) {
    const yrs = (n) => Array.from({ length: n }, (_, i) => `${T("mes", "month")} ${i + 1}`);
    const pair = (sel, legendSel, a, bvals, subSel, diff) => {
      lineChart($(sel), { series: [
        { name: T("Contrato (Ethereum)", "Contract (Ethereum)"), color: "var(--s1)", p50: a, width: 5 },
        { name: T("Simulador", "Simulator"), color: "var(--s2)", p50: bvals, dash: "6 5" },
      ], kind: "idx", tipLabel: (i) => `${T("Año", "Year")} ${Math.floor(i / 12) + 1} · ${T("mes", "month")} ${(i % 12) + 1}` });
      $(legendSel).innerHTML = `<span><i style="background:var(--s1);height:5px"></i>${T("Contrato (Ethereum)", "Contract (Ethereum)")}</span><span><i style="background:repeating-linear-gradient(90deg,var(--s2) 0 6px,transparent 6px 10px)"></i>${T("Simulador (discontinua)", "Simulator (dashed)")}</span>`;
      $(subSel).textContent = T(`Oferta, inicio = 100 · diferencia máxima ${diff.toExponential(1)}`, `Supply, start = 100 · max difference ${diff.toExponential(1)}`);
    };
    pair("#halving-chart", "#halving-legend", demo.halving.chain, demo.halving.model, "#halving-sub", demo.halving.max_abs_diff);
    pair("#dividend-chart", "#dividend-legend", demo.dividend.chain, demo.dividend.model, "#dividend-sub", demo.dividend.max_abs_diff);
    const dm = demo.demurrage;
    $("#demurrage-sub").textContent = T(`Oxidación ${fmt("pct", dm.rate)} al mes sobre lo que supera ${dm.exemption.toLocaleString(loc)}; tras 24 meses el Tesoro ha recibido ${dm.treasury.toLocaleString(loc, { maximumFractionDigits: 0 })}`,
      `Demurrage ${fmt("pct", dm.rate)} a month above ${dm.exemption.toLocaleString(loc)}; after 24 months the Treasury has received ${dm.treasury.toLocaleString(loc, { maximumFractionDigits: 0 })}`);
    lineChart($("#demurrage-chart"), { series: [{ name: T("Saldo", "Balance"), color: "var(--s3)", p50: dm.path }], kind: "num",
      xLabels: dm.path.map((_, i) => `${T("mes", "month")} ${i}`) });
    const cb = demo.cbdc;
    const e = (v) => `${v.toLocaleString(loc, { maximumFractionDigits: 0 })} €`;
    $("#cbdc-steps").innerHTML = [
      [T("Nómina", "Salary"), T(`Llega una nómina de ${e(cb.salary)}. El límite es ${e(cb.limit)}: el contrato deja ${e(cb.after_salary.holder)} en el monedero y envía ${e(cb.after_salary.bank)} al banco vinculado (cascada inversa).`, `A ${e(cb.salary)} salary arrives. The limit is ${e(cb.limit)}: the contract keeps ${e(cb.after_salary.holder)} in the wallet and sends ${e(cb.after_salary.bank)} to the linked bank (reverse waterfall).`)],
      [T("Estímulo", "Stimulus"), T(`El banco central emite ${e(cb.stimulus)} programables que caducan en 6 meses y solo valen en comercios autorizados.`, `The central bank issues ${e(cb.stimulus)} of programmable money that expires in 6 months and only works at authorised shops.`)],
      [T("Compra", "Purchase"), T(`Gasta ${e(cb.spent_at_shop)} en un comercio: primero el saldo libre y luego el estímulo. Quedan ${e(cb.stimulus_left_before_expiry)} de estímulo.`, `Spends ${e(cb.spent_at_shop)} at a shop: free balance first, then stimulus. ${e(cb.stimulus_left_before_expiry)} of stimulus remain.`)],
      [T("Caducidad", "Expiry"), T(`A los 7 meses cualquiera puede ejecutar expire(): lo no gastado vuelve al banco central. Saldo final: ${e(cb.after_expiry)}.`, `After 7 months anyone can call expire(): unspent money returns to the central bank. Final balance: ${e(cb.after_expiry)}.`)],
      [T("Control", "Control"), T("El contrato también tiene freeze(): el banco central puede congelar una cuenta. Está ahí, con evento público, porque es exactamente el riesgo que señalan los críticos de las CBDC.", "The contract also has freeze(): the central bank can freeze an account. It is there, with a public event, because it is exactly the risk CBDC critics point to.")],
    ].map(([h, t]) => `<div><span class="tag">${h}</span><span>${t}</span></div>`).join("");
    const mg = demo.mortgage;
    $("#mortgage-sub").textContent = T(`${e(mg.principal)} a ${mg.months / 12} años al ${(mg.rate_bps / 100).toLocaleString(loc)} % · cuota calculada en el contrato: ${mg.installment.toLocaleString(loc, { maximumFractionDigits: 2 })} € · la vivienda sigue en garantía`,
      `${e(mg.principal)} over ${mg.months / 12} years at ${(mg.rate_bps / 100).toLocaleString(loc)} % · installment computed on-chain: €${mg.installment.toLocaleString(loc, { maximumFractionDigits: 2 })} · the home stays as collateral`);
    $("#mortgage-table").innerHTML = `<table class="data"><thead><tr><th>${T("Cuota", "Payment")}</th><th>${T("Intereses", "Interest")}</th><th>${T("Capital", "Principal")}</th><th>${T("Pendiente", "Outstanding")}</th></tr></thead><tbody>` +
      mg.first_year.map((r) => `<tr><td>${r.n}</td><td>${r.interest.toLocaleString(loc, { maximumFractionDigits: 2 })}</td><td>${r.principal.toLocaleString(loc, { maximumFractionDigits: 2 })}</td><td>${r.remaining.toLocaleString(loc, { maximumFractionDigits: 0 })}</td></tr>`).join("") + `</tbody></table>`;
    const GAS_EN = { "Emitir un periodo (oferta fija)": "Issue one period (fixed supply)", "Transferencia ERC-20": "ERC-20 transfer", "Registrar un ciudadano": "Register a citizen",
      "Emitir el dividendo del mes": "Issue the monthly dividend", "Cobrar el dividendo": "Claim the dividend", "Transferencia con oxidación": "Transfer with demurrage",
      "Pago con cascada al banco": "Payment with bank waterfall", "Emitir estímulo programable": "Issue programmable stimulus", "Hacer caducar el estímulo": "Expire the stimulus",
      "Inscribir una vivienda (NFT)": "Register a home (NFT)", "Conceder la hipoteca": "Grant the mortgage", "Pagar una cuota": "Pay an installment" };
    $("#gas-table").innerHTML = `<table class="data"><thead><tr><th>${T("Operación", "Operation")}</th><th>Gas</th></tr></thead><tbody>` +
      Object.entries(demo.gas).map(([k, v]) => `<tr><td>${lang() === "en" ? GAS_EN[k] || k : k}</td><td>${v.toLocaleString(loc)}</td></tr>`).join("") + `</tbody></table>`;
  }
  const DESC_EN = {
    HalvingToken: "Bitcoin-style fixed supply: issuance halves every 4 years and is shared among validators.",
    AlgorithmicDividend: "2 % algorithm: supply grows at a fixed rate and new money is shared equally among citizens.",
    DemurrageToken: "Demurrage money: idle balances lose 0.5 % a month, paid to the Treasury.",
    ProgrammableCBDC: "Digital euro: €3,000 limit, bank waterfall, expiring stimulus and account freezing.",
    TokenizedMortgage: "Mortgage as a contract: the home (NFT) is held as collateral until the last payment.",
    BaseToken: "Minimal ERC-20, fixed-point maths and access control used by all the others.",
  };
  $("#contract-cards").innerHTML = ct.sources.map((s) => `<div class="card contract"><h4>${s.name}.sol</h4><p>${lang() === "en" ? DESC_EN[s.name] : s.desc}</p>
    <div style="display:flex;justify-content:space-between;align-items:center"><span class="muted" style="font-size:12px">${s.lines} ${T("líneas", "lines")} · Solidity 0.8.24</span>
    <button class="btn small" data-src="${s.name}">${T("Ver código", "View code")}</button></div></div>`).join("");
  document.querySelectorAll("[data-src]").forEach((btn) => btn.addEventListener("click", async () => {
    const code = await load(`/api/contracts/${btn.dataset.src}`);
    $("#code-title").textContent = `${btn.dataset.src}.sol`;
    $("#code").textContent = code;
    $("#code-view").hidden = false;
    $("#code-view").scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  $("#code-close").onclick = () => ($("#code-view").hidden = true);
  const dep = ct.deployments;
  $("#deploy-info").innerHTML = dep
    ? T("Desplegados en la red ", "Deployed on network ") + `${dep.chain_id}: ` + Object.entries(dep.contracts).map(([n, a]) => `<a href="https://sepolia.etherscan.io/address/${a}" target="_blank" rel="noopener">${n}</a>`).join(" · ")
    : T("Cinco contratos sin dependencias externas, probados con eth-tester. Para desplegarlos en la testnet Sepolia: <code>python scripts/deploy_contracts.py</code> con tu RPC_URL y una clave de pruebas.",
        "Five dependency-free contracts, tested with eth-tester. To deploy them on the Sepolia testnet: <code>python scripts/deploy_contracts.py</code> with your RPC_URL and a test key.");
}
