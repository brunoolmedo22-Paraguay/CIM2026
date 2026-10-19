// Utilidades da interface: API, formatação pt-BR, gaveta, toasts, contadores e tema dos gráficos.
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];
export const META = { models: [], colors: {} };

export async function api(path, opts = {}) {
  const init = { headers: {} };
  if (opts.body !== undefined) {
    init.method = "POST";
    if (opts.raw) init.body = opts.body;
    else { init.body = JSON.stringify(opts.body); init.headers["Content-Type"] = "application/json"; }
  }
  const r = await fetch(path, init);
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && data.error) || `Erro ${r.status}`);
  return data;
}

const NF = {};
export function fmt(x, d = 2, opts = {}) {
  if (x === null || x === undefined || Number.isNaN(x)) return "—";
  const k = d + (opts.sign ? "s" : "");
  NF[k] ??= new Intl.NumberFormat("pt-BR", { minimumFractionDigits: d, maximumFractionDigits: d, signDisplay: opts.sign ? "exceptZero" : "auto" });
  return NF[k].format(x);
}
export const fint = (x) => (x === null || x === undefined ? "—" : new Intl.NumberFormat("pt-BR").format(Math.round(x)));
export function fsmart(x, unit = "") {
  if (x === null || x === undefined) return "—";
  const a = Math.abs(x);
  const d = a >= 100 ? 0 : a >= 10 ? 1 : a >= 1 ? 2 : a >= 0.01 ? 3 : 4;
  return fmt(x, d) + (unit ? " " + unit : "");
}
export function factor(x) { return x >= 100 ? `${fint(x)}×` : `${fmt(x, 1)}×`; }
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export function mtag(m, withName = true) {
  const info = META.models.find((x) => x.id === m) || { short: "" };
  return `<span class="mtag" style="--c:${META.colors[m]}"><i></i>${m}${withName ? ` <span style="font-weight:500;color:var(--muted)">${esc(info.short)}</span>` : ""}</span>`;
}
export function chip(kind, text) { return `<span class="chip ${kind}">${esc(text)}</span>`; }

export function toast(msg, err = false) {
  const t = document.createElement("div");
  t.className = "toast" + (err ? " err" : "");
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => { t.style.transition = "opacity .3s"; t.style.opacity = "0"; setTimeout(() => t.remove(), 320); }, err ? 6500 : 3200);
}

// Gaveta lateral
export const drawer = {
  open(title, bodyHTML, footHTML = "") {
    $("#dtitle").textContent = title;
    $("#dbody").innerHTML = bodyHTML;
    $("#dfoot").innerHTML = footHTML;
    $("#dfoot").style.display = footHTML ? "" : "none";
    $("#drawer").classList.add("on"); $("#scrim").classList.add("on");
    $("#drawer").setAttribute("aria-hidden", "false");
    setTimeout(() => $("#dbody").querySelector("input,select,button")?.focus(), 350);
    return $("#dbody");
  },
  close() { $("#drawer").classList.remove("on"); $("#scrim").classList.remove("on"); $("#drawer").setAttribute("aria-hidden", "true"); },
};
document.addEventListener("keydown", (e) => { if (e.key === "Escape") drawer.close(); });
setTimeout(() => { $("#scrim").onclick = drawer.close; $("#dclose").onclick = drawer.close; });

// Contador animado (responde a uma ação do usuário)
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
export function countUp(el, to, fmtFn) {
  if (!el) return;
  const from = parseFloat(el.dataset.v ?? "0") || 0;
  el.dataset.v = to;
  if (reduce || !Number.isFinite(to)) { el.innerHTML = fmtFn(to); return; }
  const t0 = performance.now(), dur = 650;
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    el.innerHTML = fmtFn(from + (to - from) * e);
    if (k < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// Tema Plotly
const AX = { gridcolor: "#E7ECF1", linecolor: "#D9E1E8", zeroline: false, tickfont: { size: 11.5 }, title: { font: { size: 12.5 } } };
function merge(a, b) {
  const o = { ...a };
  for (const [k, v] of Object.entries(b || {})) o[k] = v && typeof v === "object" && !Array.isArray(v) && a[k] && typeof a[k] === "object" ? merge(a[k], v) : v;
  return o;
}
export function plot(el, data, layout = {}, name = "cim26") {
  if (!el) return;
  const base = {
    font: { family: "Plex, system-ui, sans-serif", size: 12.5, color: "#13202D" },
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "#FFFFFF", margin: { l: 58, r: 22, t: 14, b: 44 },
    hoverlabel: { bgcolor: "#13202D", bordercolor: "#13202D", font: { color: "#fff", family: "Plex, sans-serif", size: 12 } },
    legend: { orientation: "h", y: 1.08, x: 0, yanchor: "bottom", font: { size: 12 } },
    xaxis: AX, yaxis: AX, yaxis2: { ...AX, gridcolor: "rgba(0,0,0,0)" },
  };
  const isDate = data.some((t) => Array.isArray(t.x) && t.x.find((v) => v !== null) && /^\d{4}-\d\d-\d\d/.test(String(t.x.find((v) => v !== null))));
  if (isDate) base.xaxis = { ...AX, hoverformat: "%d/%m/%Y %H:%M", tickformatstops: [
    { dtickrange: [null, 43200000], value: "%H:%M<br>%d/%m" }, { dtickrange: [43200000, "M1"], value: "%d/%m" }, { dtickrange: ["M1", null], value: "%m/%Y" }] };
  const L = merge(base, layout);
  for (const k of Object.keys(L)) if (/^[xy]axis\d*$/.test(k)) L[k] = merge(AX, L[k]);
  return Plotly.react(el, data, L, { displaylogo: false, responsive: true, modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
    toImageButtonOptions: { format: "svg", filename: name, scale: 2 } });
}
export function exportPlot(el, name, format = "svg") { return Plotly.downloadImage(el, { format, filename: name, width: 1200, height: 520, scale: format === "png" ? 2 : 1 }); }

// Insere null nas lacunas (noite/lacunas não são desenhadas como linhas)
export function gapped(ts, ys, maxGapMin) {
  const x = [], y = [];
  for (let i = 0; i < ts.length; i++) {
    if (i && (Date.parse(ts[i]) - Date.parse(ts[i - 1])) / 60000 > maxGapMin) { x.push(ts[i - 1].slice(0, 16) + ":01"); y.push(null); }
    x.push(ts[i]); y.push(ys[i]);
  }
  return [x, y];
}
export const evLabel = { robusta: "evidência robusta", indicativa: "evidência indicativa", inconclusiva: "inconclusiva", contexto: "contexto" };
export function discussion(items, sec) {
  const it = items.filter((i) => i.secao === sec);
  if (!it.length) return "";
  return `<div class="disc">${it.map((i) => `<article class="dc ${i.evidencia}"><header><b>${esc(i.titulo)}</b><span class="ev ${i.evidencia}">${evLabel[i.evidencia] || i.evidencia}</span></header><p>${esc(i.texto)}</p></article>`).join("")}</div>`;
}
export function table(rows, cols) {
  return `<div class="tablewrap"><table class="t"><thead><tr>${cols.map((c) => `<th class="${c.r ? "r" : ""}">${esc(c.h)}</th>`).join("")}</tr></thead><tbody>${rows
    .map((r) => `<tr>${cols.map((c) => `<td class="${c.r ? "r" : ""}">${c.f ? c.f(r[c.k], r) : esc(r[c.k])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
export const icon = {
  edit: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg>`,
  dl: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 4v11m0 0-4-4m4 4 4-4M5 20h14"/></svg>`,
  play: `<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M7 5v14l11-7z"/></svg>`,
  pause: `<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><path d="M7 5h4v14H7zM13 5h4v14h-4z"/></svg>`,
  sun: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="4.5" fill="currentColor"/><path d="M12 2v2.5M12 19.5V22M2 12h2.5M19.5 12H22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/></svg>`,
  up: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 20V9m0 0-4 4m4-4 4 4M5 4h14"/></svg>`,
};

// Relleno por trechos contínuos: cada segmento é um traço próprio (o preenchimento nunca atravessa a noite/lacunas)
export function fillSegments(ts, ys, maxGapMin, trace) {
  const segs = []; let cur = { x: [], y: [] };
  for (let i = 0; i < ts.length; i++) {
    const gap = i && (Date.parse(ts[i]) - Date.parse(ts[i - 1])) / 60000 > maxGapMin;
    if ((gap || ys[i] === null || ys[i] === undefined) && cur.x.length) { segs.push(cur); cur = { x: [], y: [] }; }
    if (ys[i] !== null && ys[i] !== undefined) { cur.x.push(ts[i]); cur.y.push(ys[i]); }
  }
  if (cur.x.length) segs.push(cur);
  const g = "g" + Math.random().toString(36).slice(2, 7);
  return segs.map((sg, k) => ({ ...trace, x: sg.x, y: sg.y, legendgroup: g, showlegend: k === 0 }));
}
