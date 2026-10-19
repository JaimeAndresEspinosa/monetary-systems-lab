// Gráficos SVG sin dependencias: líneas con banda 10–90 %, barras divergentes y apiladas.
// Todos tienen tooltip al pasar el ratón y se redibujan al cambiar el ancho.

const SVGNS = "http://www.w3.org/2000/svg";
const el = (tag, attrs = {}, parent) => {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
};

export const FMT = {
  pct: (v, d = 1) => `${(v * 100).toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d })} %`,
  pp: (v, d = 1) => `${v >= 0 ? "+" : ""}${(v * 100).toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d })} pp`,
  idx: (v) => (v * 100).toLocaleString("es-ES", { maximumFractionDigits: 0 }),
  dec: (v) => v.toLocaleString("es-ES", { minimumFractionDigits: 3, maximumFractionDigits: 3 }),
  x: (v) => v.toLocaleString("es-ES", { minimumFractionDigits: 1, maximumFractionDigits: 1 }),
};
export const fmt = (kind, v, d) => (v == null || Number.isNaN(v) ? "—" : (FMT[kind] || FMT.dec)(v, d));

function niceTicks(min, max, count = 4) {
  if (min === max) { min -= 1e-3; max += 1e-3; }
  const span = max - min;
  const step0 = span / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= step0) || step0;
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

const observers = new WeakMap();
function responsive(node, draw) {
  draw();
  if (observers.has(node)) observers.get(node).disconnect();
  let w = node.clientWidth;
  const ro = new ResizeObserver(() => {
    if (Math.abs(node.clientWidth - w) > 4) { w = node.clientWidth; draw(); }
  });
  ro.observe(node);
  observers.set(node, ro);
}

function tooltip(node) {
  let t = node.querySelector(".tip");
  if (!t) { t = document.createElement("div"); t.className = "tip"; t.hidden = true; node.appendChild(t); }
  return t;
}

/**
 * Línea temporal con banda de incertidumbre.
 * series: [{ name, color, p10, p50, p90 }]  (meses)
 */
export function lineChart(node, { series, kind = "dec", height = 210, ref = null, zero = false }) {
  responsive(node, () => {
    node.querySelector("svg")?.remove();
    const W = Math.max(280, node.clientWidth);
    const H = height;
    const m = { t: 10, r: 12, b: 24, l: 52 };
    const n = series[0].p50.length;
    const all = series.flatMap((s) => [...(s.p10 || s.p50), ...(s.p90 || s.p50)]);
    if (ref != null) all.push(ref);
    if (zero) all.push(0);
    let lo = Math.min(...all), hi = Math.max(...all);
    const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 0.01;
    lo -= pad; hi += pad;
    const ticks = niceTicks(lo, hi, 4);
    lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks.at(-1));
    const x = (i) => m.l + (i / (n - 1)) * (W - m.l - m.r);
    const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);

    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img" });
    const g = el("g", { class: "axis" }, svg);
    for (const tv of ticks) {
      if (tv < lo || tv > hi) continue;
      el("line", { x1: m.l, x2: W - m.r, y1: y(tv), y2: y(tv), class: "gridline" }, g);
      el("text", { x: m.l - 8, y: y(tv) + 4, "text-anchor": "end" }, g).textContent = fmt(kind, tv, kind === "pct" ? 0 : undefined);
    }
    const years = Math.round(n / 12);
    const everyY = years > 12 ? 4 : years > 6 ? 2 : 1;
    for (let yr = 0; yr <= years; yr += everyY) {
      const i = Math.min(n - 1, yr * 12);
      el("text", { x: x(i), y: H - 6, "text-anchor": yr === 0 ? "start" : "middle" }, g).textContent = yr === 0 ? "Inicio" : `Año ${yr}`;
    }
    if (zero && lo < 0 && hi > 0) el("line", { x1: m.l, x2: W - m.r, y1: y(0), y2: y(0), class: "zero" }, svg);
    if (ref != null) el("line", { x1: m.l, x2: W - m.r, y1: y(ref), y2: y(ref), class: "ref" }, svg);

    for (const s of series) {
      if (s.p10 && s.p90) {
        let d = `M${x(0)},${y(s.p90[0])}`;
        for (let i = 1; i < n; i++) d += `L${x(i)},${y(s.p90[i])}`;
        for (let i = n - 1; i >= 0; i--) d += `L${x(i)},${y(s.p10[i])}`;
        el("path", { d: d + "Z", fill: s.color, opacity: 0.14 }, svg);
      }
    }
    for (const s of series) {
      let d = "";
      s.p50.forEach((v, i) => (d += `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`));
      el("path", { d, fill: "none", stroke: s.color, "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
    }

    // capa interactiva
    const cross = el("line", { y1: m.t, y2: H - m.b, class: "cross", visibility: "hidden" }, svg);
    const dots = series.map((s) => el("circle", { r: 4, fill: s.color, stroke: "var(--surface)", "stroke-width": 2, visibility: "hidden" }, svg));
    const hit = el("rect", { x: m.l, y: m.t, width: W - m.l - m.r, height: H - m.t - m.b, fill: "transparent" }, svg);
    const tip = tooltip(node);
    const show = (evt) => {
      const r = svg.getBoundingClientRect();
      const px = ((evt.clientX - r.left) / r.width) * W;
      const i = Math.max(0, Math.min(n - 1, Math.round(((px - m.l) / (W - m.l - m.r)) * (n - 1))));
      cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
      series.forEach((s, k) => { dots[k].setAttribute("cx", x(i)); dots[k].setAttribute("cy", y(s.p50[i])); dots[k].setAttribute("visibility", "visible"); });
      const yr = Math.floor(i / 12), mo = (i % 12) + 1;
      tip.innerHTML = `<div class="th">Año ${yr + 1} · mes ${mo}</div>` + series.map((s) =>
        `<div class="tr"><span><i class="sw" style="background:${s.color}"></i>${s.name}</span><b>${fmt(kind, s.p50[i])}</b></div>` +
        (s.p10 ? `<div class="tr muted"><span>banda 10–90 %</span><span>${fmt(kind, s.p10[i])} – ${fmt(kind, s.p90[i])}</span></div>` : "")
      ).join("");
      tip.hidden = false;
      const left = (x(i) / W) * r.width;
      tip.style.left = `${Math.max(90, Math.min(r.width - 90, left))}px`;
      tip.style.top = `${(y(Math.max(...series.map((s) => s.p50[i]))) / H) * r.height - 8}px`;
    };
    hit.addEventListener("pointermove", show);
    hit.addEventListener("pointerleave", () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); dots.forEach((d) => d.setAttribute("visibility", "hidden")); });
    node.prepend(svg);
  });
}

/** Barras verticales divergentes (p. ej. variación de la cuota de riqueza por decil). */
export function divergingBars(node, { labels, values, kind = "pp", height = 220, title = "", extra = null }) {
  responsive(node, () => {
    node.querySelector("svg")?.remove();
    const W = Math.max(280, node.clientWidth), H = height;
    const m = { t: 12, r: 10, b: 30, l: 52 };
    const maxAbs = Math.max(...values.map(Math.abs), 1e-4) * 1.15;
    const ticks = niceTicks(-maxAbs, maxAbs, 4);
    const lo = ticks[0], hi = ticks.at(-1);
    const y = (v) => m.t + (1 - (v - lo) / (hi - lo)) * (H - m.t - m.b);
    const bw = (W - m.l - m.r) / values.length;
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, height: H, role: "img", "aria-label": title });
    for (const tv of ticks) {
      el("line", { x1: m.l, x2: W - m.r, y1: y(tv), y2: y(tv), class: "gridline" }, svg);
      el("text", { x: m.l - 8, y: y(tv) + 4, "text-anchor": "end" }, svg).textContent = fmt(kind, tv, 1);
    }
    el("line", { x1: m.l, x2: W - m.r, y1: y(0), y2: y(0), stroke: "var(--muted)" }, svg);
    const tip = tooltip(node);
    values.forEach((v, i) => {
      const x0 = m.l + i * bw + bw * 0.18, w = bw * 0.64;
      const y0 = y(Math.max(v, 0)), h = Math.max(1, Math.abs(y(v) - y(0)));
      const r = Math.min(4, w / 2, h);
      // extremo redondeado (4 px) en el lado del dato, base recta sobre el cero
      const d = v >= 0
        ? `M${x0},${y0 + h}V${y0 + r}Q${x0},${y0} ${x0 + r},${y0}H${x0 + w - r}Q${x0 + w},${y0} ${x0 + w},${y0 + r}V${y0 + h}Z`
        : `M${x0},${y0}V${y0 + h - r}Q${x0},${y0 + h} ${x0 + r},${y0 + h}H${x0 + w - r}Q${x0 + w},${y0 + h} ${x0 + w},${y0 + h - r}V${y0}Z`;
      el("path", { d, fill: v >= 0 ? "var(--pos)" : "var(--neg)" }, svg);
      el("text", { x: x0 + w / 2, y: H - 10, "text-anchor": "middle" }, svg).textContent = labels[i];
      const hit = el("rect", { x: m.l + i * bw, y: m.t, width: bw, height: H - m.t - m.b, fill: "transparent" }, svg);
      hit.addEventListener("pointermove", () => {
        tip.innerHTML = `<div class="th">${extra?.names?.[i] || labels[i]}</div><div class="tr"><span>Variación</span><b>${fmt(kind, v, 2)}</b></div>` +
          (extra ? `<div class="tr"><span>Cuota inicial</span><b>${fmt("pct", extra.start[i])}</b></div><div class="tr"><span>Cuota final</span><b>${fmt("pct", extra.end[i])}</b></div>` : "");
        tip.hidden = false;
        const rr = svg.getBoundingClientRect();
        tip.style.left = `${Math.max(90, Math.min(rr.width - 90, ((x0 + w / 2) / W) * rr.width))}px`;
        tip.style.top = `${(Math.min(y(v), y(0)) / H) * rr.height - 6}px`;
      });
      hit.addEventListener("pointerleave", () => (tip.hidden = true));
    });
    node.prepend(svg);
  });
}

/** Barras horizontales simples (reparto del dinero nuevo). */
export function hBars(node, { rows, kind = "pct" }) {
  node.innerHTML = rows.map((r) => `
    <div class="effect-row" style="grid-template-columns:120px 1fr 64px">
      <span>${r.label}</span>
      <span style="background:var(--surface-2);border-radius:4px;height:14px;position:relative">
        <span style="position:absolute;left:0;top:0;bottom:0;width:${Math.max(0, Math.min(1, r.value)) * 100}%;background:${r.color || "var(--s1)"};border-radius:4px"></span>
      </span>
      <span class="val">${fmt(kind, r.value, 0)}</span>
    </div>`).join("");
}
