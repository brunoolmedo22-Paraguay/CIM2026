// Simulador (modo Modelos): espaço de trabalho único, configuração por gavetas, resultados ao vivo.
import { $, $$, api, fmt, fint, fsmart, esc, mtag, chip, toast, drawer, countUp, plot, exportPlot, gapped, fillSegments, icon, META } from "./ui.js";

const S = {
  moduleId: "SUPSI_MONO_SI_REFERENCE", ns: 1, np: 1,
  weather: { source: "supsi", days: ["2019-05-14"] },
  thermal: { strategy: null, delta_t: 3 },
  models: new Set(["M2"]), focus: "M2",
  overlay: { g: true, t: false, obs: true },
  lib: [], res: null, days: null, csv: null, iv: { idx: null, playing: false, timer: null },
};
let root, busy = 0, pending = null;
const mod = () => S.lib.find((m) => m.id === S.moduleId);

export async function render(el) {
  root = el;
  el.innerHTML = `<div class="page">
    <p class="lede">Escolha um módulo, o arranjo e o clima; os quatro modelos são avaliados com o mesmo motor físico do Artigo.
    Clique em qualquer cartão para alterar. Nada aqui modifica o ensaio congelado do Artigo.</p>
    <div class="tiles" id="tiles"></div>
    <div class="models" id="mpills"></div>
    <div id="mreason" class="notes" style="margin-top:0"></div>
    <div class="kpis" id="kpis"></div>
    <section class="card pad">
      <div class="hd"><div class="grow"><h3>Potência DC do arranjo</h3><div class="sub" id="chartsub">—</div></div>
        <div class="toolbar">
          <label class="switch sunny"><input type="checkbox" id="ovg" ${S.overlay.g ? "checked" : ""}> Irradiância (eixo direito)</label>
          <label class="switch"><input type="checkbox" id="ovt" ${S.overlay.t ? "checked" : ""}> Temperatura de célula</label>
          <label class="switch" id="ovobsw"><input type="checkbox" id="ovobs" ${S.overlay.obs ? "checked" : ""}> Medida SUPSI</label>
          <button class="btn" id="expcsv">${icon.dl} CSV</button><button class="btn" id="expsvg">${icon.dl} SVG</button><button class="btn" id="exppng">${icon.dl} PNG</button>
        </div></div>
      <div id="pchart" class="chart" style="height:420px"></div>
    </section>
    <section class="card pad mt" id="ivcard" style="display:none">
      <div class="hd"><div class="grow"><h3>Curvas I–V e P–V do arranjo <span class="chip lab">somente SDM</span></h3>
        <div class="sub">Percorra o dia: a curva é recalculada pelo SDM em cada instante (G, Tcell).</div></div>
        <div class="ivplay"><button class="btn sun" id="ivplay">${icon.play} Reproduzir dia</button><span class="t" id="ivt">—</span></div></div>
      <input type="range" id="ivrange" min="0" max="0" value="0">
      <div id="ivchart" class="chart" style="height:360px"></div>
    </section>
    <div id="notes" class="notes"></div>
  </div>`;
  $("#ovg").onchange = (e) => { S.overlay.g = e.target.checked; drawPower(); };
  $("#ovt").onchange = (e) => { S.overlay.t = e.target.checked; drawPower(); };
  $("#ovobs").onchange = (e) => { S.overlay.obs = e.target.checked; drawPower(); };
  $("#expsvg").onclick = () => exportPlot($("#pchart"), "simulador_potencia", "svg");
  $("#exppng").onclick = () => exportPlot($("#pchart"), "simulador_potencia", "png");
  $("#expcsv").onclick = exportCSV;
  $("#ivplay").onclick = togglePlay;
  $("#ivrange").oninput = (e) => { stopPlay(); drawIV(+e.target.value); };
  if (!S.lib.length) S.lib = await api("/api/library");
  drawTiles(); drawPills(); drawKPIs(true);
  simulate();
}

// ------------------------------------------------------------------ cartões
function weatherText() {
  const w = S.weather;
  if (w.source === "supsi") return [w.days.length === 1 ? new Date(w.days[0] + "T12:00").toLocaleDateString("pt-BR") : `${w.days.length} dias`, "SUPSI 2019 · medido (POA)"];
  if (w.source === "csv") return [S.csv?.name || "CSV", `${w.g_kind === "GHI" ? "GHI → POA (horizontal)" : "POA"} · medido`];
  if (w.source === "synthetic") return [w.profile || "Perfil sintético", `${w.season} · ${fmt((w.duration_min || 1440) / 60, 0)} h · simulado`];
  return [`${fint(w.g ?? 800)} W/m² · ${w.t ?? 25} °C`, `condição manual (${w.t_kind || "Tamb"})`];
}
function drawTiles() {
  const m = mod(); const r = S.res;
  const th = r?.thermal; const used = th?.options.find((o) => o.id === th.used);
  const [wa, wb] = weatherText();
  const tiles = [
    ["modulo", "Módulo", m ? esc(m.label) : "—", m ? `${fint(m.p_stc_W)} W · ${esc(m.technology)}` : ""],
    ["arranjo", "Arranjo", `${S.ns} × ${S.np} módulos`, m ? `${fmt((m.p_stc_W * S.ns * S.np) / 1000, 2)} kWp instalados` : ""],
    ["clima", "Clima", wa, wb],
    ["temp", "Temperatura", used ? used.label.split(";")[0] : (r ? "sem temperatura" : "—"), used ? `ΔT ${fmt(S.thermal.delta_t, 1)} °C (hipótese)` : "apenas M1 avaliável"],
  ];
  $("#tiles").innerHTML = tiles.map(([k, l, b, s]) => `<button class="tile" data-k="${k}"><small>${l}</small><b>${b}</b><span>${s}</span><span class="edit">${icon.edit}</span></button>`).join("");
  $$(".tile").forEach((t) => (t.onclick = () => ({ modulo: openModule, arranjo: openArray, clima: openWeather, temp: openThermal }[t.dataset.k]())));
}
function drawPills() {
  const m = mod(); if (!m) return;
  $("#mpills").innerHTML = META.models.map((x) => {
    const av = (S.res?.availability?.[x.id]) || m.availability[x.id];
    const ok = av.available;
    return `<button class="mpill ${S.models.has(x.id) && ok ? "on" : ""} ${ok ? "" : "na"}" data-m="${x.id}" style="--c:${x.color}" title="${esc(av.reason)}"><i></i>${x.id} <small>${esc(x.short)}</small></button>`;
  }).join("") + `<span class="sub" style="margin-left:6px;color:var(--muted);font-size:12.5px">Selecione um ou mais modelos para comparar.</span>`;
  $$(".mpill").forEach((p) => (p.onclick = () => {
    const id = p.dataset.m;
    const av = (S.res?.availability?.[id]) || m.availability[id];
    if (!av.available) { if (id === "M4" && m.sdm_method) openModule(true); else toast(av.reason, true); return; }
    if (S.models.has(id) && S.models.size > 1) { S.models.delete(id); if (S.focus === id) S.focus = [...S.models][0]; }
    else { S.models.add(id); S.focus = id; }
    drawPills(); drawKPIs(); drawPower(); drawIVCard();
  }));
  const na = META.models.filter((x) => !((S.res?.availability?.[x.id]) || m.availability[x.id]).available);
  $("#mreason").innerHTML = na.map((x) => `${mtag(x.id, false)} ${esc(((S.res?.availability?.[x.id]) || m.availability[x.id]).reason)}`).join(" &nbsp;·&nbsp; ");
}

// ------------------------------------------------------------------ simulação
function simulate() {
  pending = { module_id: S.moduleId, array: { ns: S.ns, np: S.np }, weather: S.weather, thermal: S.thermal };
  if (busy) return;
  run();
}
async function run() {
  const body = pending; pending = null; busy++;
  $("#chartsub").innerHTML = `<span class="spin dark"></span> calculando…`;
  try {
    const r = await api("/api/simulate", { body });
    S.res = r; S.thermal.strategy = r.thermal.used;
    for (const id of [...S.models]) if (!r.availability[id]?.available) S.models.delete(id);
    if (!S.models.size) S.models.add("M1");
    if (!S.models.has(S.focus)) S.focus = [...S.models][0];
    drawTiles(); drawPills(); drawKPIs(); drawPower(); drawIVCard(); drawNotes();
  } catch (e) { toast(e.message, true); $("#chartsub").textContent = e.message; }
  busy--; if (pending) run();
}

function drawKPIs(skeleton = false) {
  const k = S.res?.kpis?.find((x) => x.modelo === S.focus);
  const c = META.colors[S.focus];
  const items = [["pmax", "Potência máxima", ""], ["e", "Energia no período válido", ""], ["h", "Horas válidas", ""], ["x", "", ""]];
  if (!$("#kpis").children.length || skeleton) $("#kpis").innerHTML = items.map(([id]) => `<div class="kpi" style="border-top:3px solid ${c}"><small id="k${id}l"></small><b id="k${id}">—</b><span id="k${id}s"></span></div>`).join("");
  $$(".kpi").forEach((x) => (x.style.borderTopColor = c));
  if (!k) return;
  const ser = S.res.series;
  $("#kpmaxl").innerHTML = `Potência máxima · ${mtag(S.focus, false)}`;
  countUp($("#kpmax"), k.P_max_arranjo_W >= 1000 ? k.P_max_arranjo_W / 1000 : k.P_max_arranjo_W, (v) => `${fmt(v, k.P_max_arranjo_W >= 1000 ? 2 : 1)}<em>${k.P_max_arranjo_W >= 1000 ? "kW" : "W"}</em>`);
  $("#kpmaxs").textContent = k.instante_P_max && k.instante_P_max !== "None" ? `às ${new Date(k.instante_P_max).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}` : "";
  $("#kel").textContent = "Energia no período válido";
  countUp($("#ke"), k.E_periodo_valido_kWh, (v) => `${fmt(v, 3)}<em>kWh</em>`);
  $("#kes").textContent = `${fmt(k.E_periodo_valido_kWh / (S.res.array.p_inst_W / 1000), 2)} kWh/kWp`;
  $("#khl").textContent = "Horas válidas integradas";
  countUp($("#kh"), k.horas_validas_h, (v) => `${fmt(v, 2)}<em>h</em>`);
  $("#khs").textContent = `${fint(k.amostras_validas)} de ${fint(k.amostras_total)} amostras · passo ${fmt(k.passo_nominal_min, 0)} min`;
  if (ser.P_obs) {
    const p = ser.P[S.focus], o = ser.P_obs; let eo = 0, ep = 0, se = 0, n = 0, so = 0;
    for (let i = 0; i < o.length; i++) if (o[i] !== null && p[i] !== null) {
      n++; se += (p[i] - o[i]) ** 2; so += o[i];
      if (i && (Date.parse(ser.timestamp[i]) - Date.parse(ser.timestamp[i - 1])) <= 450000 && o[i - 1] !== null && p[i - 1] !== null) {
        const dt = (Date.parse(ser.timestamp[i]) - Date.parse(ser.timestamp[i - 1])) / 3.6e6; eo += (o[i] + o[i - 1]) / 2 * dt; ep += (p[i] + p[i - 1]) / 2 * dt;
      }
    }
    $("#kxl").textContent = "Desvio frente à medida (SUPSI)";
    countUp($("#kx"), n ? 100 * Math.sqrt(se / n) / (so / n) : NaN, (v) => `${fmt(v, 1)}<em>% nRMSE</em>`);
    $("#kxs").textContent = `energia ${fmt(100 * (ep - eo) / eo, 1, { sign: true })} % · referência: Pm medida × ${S.ns * S.np}`;
  } else {
    $("#kxl").textContent = S.weather.source === "supsi" ? "Desempenho específico (sem comparação: outro módulo)" : "Desempenho específico";
    countUp($("#kx"), k.E_periodo_valido_kWh / (S.res.array.p_inst_W / 1000), (v) => `${fmt(v, 2)}<em>kWh/kWp</em>`);
    $("#kxs").textContent = `${fmt(S.res.array.p_inst_W / 1000, 2)} kWp instalados`;
  }
}

function drawPower() {
  const r = S.res; if (!r) return;
  const s = r.series, gap = Math.max(7.5, (r.kpis[0]?.passo_nominal_min || 5) * 1.5);
  const traces = [];
  const both = S.overlay.g && S.overlay.t;
  if (S.overlay.g) traces.push(...fillSegments(s.timestamp, s.g_poa, gap, { name: "Irradiância POA", yaxis: "y2", type: "scatter", mode: "lines", line: { color: "rgba(242,169,0,.9)", width: 1 }, fill: "tozeroy", fillcolor: "rgba(242,169,0,.14)", hovertemplate: "%{y:.0f} W/m²<extra>Gpoa</extra>" }));
  if (S.overlay.t) { const [x, y] = gapped(s.timestamp, s.t_cell, gap); traces.push({ x, y, name: "Tcell", yaxis: both ? "y3" : "y2", type: "scatter", mode: "lines", line: { color: "#B83A3A", width: 1.2, dash: "dot" }, hovertemplate: "%{y:.1f} °C<extra>Tcell</extra>" }); }
  if (s.P_obs && S.overlay.obs) { const [x, y] = gapped(s.timestamp, s.P_obs, gap); traces.push({ x, y, name: "Medida (Pm × Ns·Np)", type: "scatter", mode: "lines", line: { color: "#13202D", width: 2.4 }, hovertemplate: "%{y:.1f} W<extra>medida</extra>" }); }
  for (const m of META.models) if (S.models.has(m.id) && s.P[m.id]) {
    const [x, y] = gapped(s.timestamp, s.P[m.id], gap);
    traces.push({ x, y, name: `${m.id} ${m.short}`, type: "scatter", mode: "lines", line: { color: m.color, width: S.focus === m.id ? 2.4 : 1.4 }, hovertemplate: "%{y:.1f} W<extra>" + m.id + "</extra>" });
  }
  const P = r.array.p_inst_W;
  plot($("#pchart"), traces, {
    hovermode: "x unified", margin: { r: both ? 110 : 64 },
    xaxis: { domain: [0, both ? 0.9 : 1], rangeslider: { visible: s.timestamp.length > 300, thickness: 0.06 } },
    yaxis: { title: { text: "Potência [W]" }, rangemode: "tozero" },
    yaxis2: { title: { text: S.overlay.g ? "Gpoa [W/m²]" : "Tcell [°C]" }, overlaying: "y", side: "right", rangemode: "tozero", showgrid: false },
    yaxis3: { title: { text: "Tcell [°C]" }, overlaying: "y", side: "right", anchor: "free", position: 1, showgrid: false },
    shapes: S.iv.idx !== null && S.models.has("M4") ? [{ type: "line", xref: "x", yref: "paper", x0: s.timestamp[S.iv.idx], x1: s.timestamp[S.iv.idx], y0: 0, y1: 1, line: { color: "#B4507A", width: 1.5, dash: "dot" } }] : [],
  }, "simulador_potencia");
  $("#ovobsw").style.display = s.P_obs ? "" : "none";
  if (S.weather.source === "supsi" && !s.P_obs) $("#chartsub").dataset.note = "1";
  $("#chartsub").innerHTML = `${esc(r.weather.description)} · ${fint(r.weather.n)} amostras · ${S.ns}×${S.np} = ${fmt(P / 1000, 2)} kWp · lacunas &gt; ${fmt(gap, 1)} min não são ligadas`;
}

function drawNotes() {
  const r = S.res; const p = r.provenance || {};
  const kind = (t) => /hip/.test(t) ? "hipotese" : /estimad/.test(t) ? "estimado" : /medid/.test(t) ? "medido" : /simul/.test(t) ? "simulado" : "manual";
  const prov = Object.entries(p).filter(([k]) => ["g_poa_Wm2", "t_module_C", "t_cell_C"].includes(k)).map(([k, v]) => `${chip(kind(String(v)), { g_poa_Wm2: "G", t_module_C: "Tmod", t_cell_C: "Tcell" }[k] + ": " + String(v).split(":")[0])}`).join(" ");
  const warn = Object.entries(r.series.status).filter(([m]) => S.models.has(m)).flatMap(([m, st]) => Object.entries(st).filter(([l]) => !/^ok$|G=0/.test(l)).map(([l, n]) => `${m}: ${fint(n)} amostra(s) — ${l}`));
  $("#notes").innerHTML = `<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">Proveniência: ${prov}</div>
    <ul>${(r.notes || []).map((n) => `<li>${esc(n)}</li>`).join("")}${warn.map((w) => `<li style="color:var(--warn)">${esc(w)}</li>`).join("")}
    <li>Arranjo ideal: Ns·Np módulos idênticos, sem mismatch, cabeamento ou conversão. Energia por trapézios somente entre amostras válidas.</li></ul>`;
}

// ------------------------------------------------------------------ I–V (somente SDM)
function ivIndices() { const s = S.res.series; return s.timestamp.map((_, i) => i).filter((i) => s.g_poa[i] > 5 && s.P.M4 && s.P.M4[i] !== null); }
function drawIVCard() {
  const show = S.models.has("M4") && S.res?.availability?.M4?.available;
  $("#ivcard").style.display = show ? "" : "none";
  if (!show) { stopPlay(); S.iv.idx = null; return; }
  const idx = ivIndices(); if (!idx.length) return;
  const rg = $("#ivrange"); rg.max = idx.length - 1;
  const pm = S.res.series.P.M4; let best = 0;
  idx.forEach((i, k) => { if (pm[i] > pm[idx[best]]) best = k; });
  if (S.iv.idx === null || !idx.includes(S.iv.idx)) rg.value = best; else rg.value = idx.indexOf(S.iv.idx);
  drawIV(+rg.value);
}
let ivBusy = false;
async function drawIV(k) {
  const idx = ivIndices(); const i = idx[k]; if (i === undefined || ivBusy) return;
  ivBusy = true; S.iv.idx = i;
  const s = S.res.series, m = mod();
  try {
    const d = await api("/api/iv", { body: { module_id: S.moduleId, g: s.g_poa[i], t_cell: s.t_cell[i], ns: S.ns, np: S.np } });
    const vmax = (m.v_oc_V || 45) * S.ns * 1.08, imax = (m.i_sc_A || 10) * S.np * 1.3;
    plot($("#ivchart"), [
      { x: d.V, y: d.I, name: "I–V", line: { color: META.colors.M4, width: 2.6 }, hovertemplate: "%{x:.1f} V · %{y:.2f} A<extra></extra>" },
      { x: d.V, y: d.P, name: "P–V", yaxis: "y2", line: { color: "#13202D", width: 1.6, dash: "dash" }, hovertemplate: "%{y:.1f} W<extra></extra>" },
      { x: [d.mpp.Vmp], y: [d.mpp.Pmp], yaxis: "y2", mode: "markers+text", text: [`MPP ${fmt(d.mpp.Pmp, 1)} W`], textposition: "top center", marker: { size: 11, color: "#F2A900", line: { color: "#13202D", width: 1.5 } }, showlegend: false, hoverinfo: "skip" },
    ], { xaxis: { title: { text: "Tensão do arranjo [V]" }, range: [0, vmax] }, yaxis: { title: { text: "Corrente [A]" }, range: [0, imax] },
      yaxis2: { title: { text: "Potência [W]" }, overlaying: "y", side: "right", range: [0, (m.p_stc_W || 300) * S.ns * S.np * 1.3] }, margin: { r: 64 }, transition: { duration: 0 } }, "iv_sdm");
    $("#ivt").innerHTML = `${new Date(s.timestamp[i]).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })} · G ${fint(s.g_poa[i])} W/m² · Tcell ${fmt(s.t_cell[i], 1)} °C`;
    if (!S.iv.playing) drawPower();
  } catch (e) { toast(e.message, true); stopPlay(); }
  ivBusy = false;
}
function togglePlay() { S.iv.playing ? stopPlay() : startPlay(); }
function startPlay() {
  S.iv.playing = true; $("#ivplay").innerHTML = `${icon.pause} Pausar`;
  const rg = $("#ivrange"); if (+rg.value >= +rg.max) rg.value = 0;
  const step = Math.max(1, Math.round(+rg.max / 90));
  S.iv.timer = setInterval(() => { if (ivBusy) return; const v = Math.min(+rg.max, +rg.value + step); rg.value = v; drawIV(v); if (v >= +rg.max) stopPlay(); }, 90);
}
function stopPlay() { S.iv.playing = false; clearInterval(S.iv.timer); const b = $("#ivplay"); if (b) b.innerHTML = `${icon.play} Reproduzir dia`; if (S.res) drawPower(); }

function exportCSV() {
  const s = S.res?.series; if (!s) return;
  const cols = ["timestamp", "g_poa_W_m2", "t_cell_C", "t_module_C", ...Object.keys(s.P).map((m) => `P_${m}_arranjo_W`), ...(s.P_obs ? ["P_medida_x_NsNp_W"] : [])];
  const lines = [cols.join(",")];
  s.timestamp.forEach((t, i) => lines.push([t, s.g_poa[i], s.t_cell[i], s.t_module[i], ...Object.values(s.P).map((a) => a[i]), ...(s.P_obs ? [s.P_obs[i]] : [])].map((v) => v ?? "").join(",")));
  const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([lines.join("\n")], { type: "text/csv" })); a.download = "simulador_resultados.csv"; a.click();
}

// ------------------------------------------------------------------ gavetas
function specTable(m) {
  const rows = [["Pstc", m.p_stc_W, "W", 2], ["Voc", m.v_oc_V, "V", 2], ["Isc", m.i_sc_A, "A", 2], ["Vmp", m.v_mp_V, "V", 2], ["Imp", m.i_mp_A, "A", 2],
    ["Ns (células)", m.n_cells_series, "", 0], ["α Isc", m.alpha_isc_pct_C, "%/°C", 3], ["β Voc", m.beta_voc_pct_C, "%/°C", 3], ["γ Pmax", m.gamma_pmax_pct_C, "%/°C", 3], ["NOCT", m.noct_C, "°C", 1]];
  return `<table class="spec">${rows.map(([k, v, u, d]) => `<tr><td>${k}</td><td class="${v == null ? "na" : ""}">${v == null ? "não informado" : fmt(v, d) + " " + u}</td></tr>`).join("")}</table>
    <p class="notes">${esc(m.source)} · Pstc = ${esc(m.p_stc_meaning)}</p>`;
}
function openModule(sdmFocus = false) {
  const groups = [["Laboratório", S.lib.filter((m) => m.kind === "ficha_experimental")], ["Canadian Solar", S.lib.filter((m) => m.kind === "datasheet_comercial")], ["Meus módulos", S.lib.filter((m) => m.kind === "usuario")]];
  const body = drawer.open("Módulo fotovoltaico", `
    <input class="in" id="msearch" placeholder="Buscar módulo…" style="margin-bottom:12px">
    <div id="mlist"></div>
    <div class="sec-title" style="margin-top:22px"><h2 style="font-size:15px">Ficha</h2></div><div id="mspec"></div>
    <div class="sec-title" style="margin-top:22px"><h2 style="font-size:15px">Parâmetros do SDM (M4)</h2></div><div id="msdm"></div>`,
    `<button class="btn" id="mnew">Novo módulo</button><button class="btn primary" id="mok">Usar este módulo</button>`);
  let sel = S.moduleId;
  const list = () => {
    const q = $("#msearch").value.toLowerCase();
    $("#mlist").innerHTML = groups.map(([g, ms]) => { const f = ms.filter((m) => (m.label + m.id).toLowerCase().includes(q)); return f.length ? `<div class="sub" style="margin:10px 0 6px;font-weight:600">${g}</div><div class="modlist">${f.map((m) => `<div class="moditem ${m.id === sel ? "on" : ""}" data-id="${esc(m.id)}"><div><b>${esc(m.label)}</b><small>${esc(m.technology)}${m.sdm_ready ? " · SDM pronto" : ""}</small></div><span class="w">${fint(m.p_stc_W)} W</span></div>`).join("")}</div>` : ""; }).join("");
    $$(".moditem", body).forEach((x) => (x.onclick = () => { sel = x.dataset.id; list(); spec(); }));
  };
  const spec = () => { const m = S.lib.find((x) => x.id === sel); $("#mspec").innerHTML = specTable(m); sdmBox(m); };
  $("#msearch").oninput = list; list(); spec();
  $("#mok").onclick = () => { S.moduleId = sel; drawer.close(); S.iv.idx = null; drawTiles(); drawPills(); simulate(); };
  $("#mnew").onclick = () => openNewModule();
  if (sdmFocus) setTimeout(() => $("#msdm").scrollIntoView({ behavior: "smooth" }), 380);
}
function sdmBox(m) {
  const box = $("#msdm");
  if (!m.sdm_method) { box.innerHTML = `<div class="alert">SDM indisponível: faltam ${esc(m.sdm_missing.join(", "))} no datasheet e não há matriz de laboratório.</div>`; return; }
  const desc = m.sdm_method === "classico" ? "Calibração clássica (De Soto, 5 equações) com Isc, Voc, MPP, dP/dV = 0 e β_Voc do datasheet."
    : "Calibração multiponto com 66 medições IEC 61853-1 (22 G–T × Pmp, Isc, Voc), sem Ns, Vmp ou Imp. ≈ 10 s.";
  box.innerHTML = `<p class="notes" style="margin-top:0">${desc}</p><div class="row" style="flex:none"><button class="btn sun" id="sdmgo">${icon.sun} Estimar parâmetros SDM</button>
    ${m.saved_calibrations ? `<button class="btn" id="sdmload">Carregar salva</button>` : ""}</div><div id="sdmout" class="mt"></div>`;
  const go = async (load) => {
    $("#sdmout").innerHTML = `<div class="skel" style="height:120px"></div>`;
    try {
      const d = await api("/api/sdm/estimate", { body: { module_id: m.id, load_saved: !!load } });
      const r = d.reference, rep = d.report;
      const conv = d.method === "classico" ? `${rep.success ? "Convergiu" : "Não convergiu"} · custo ${rep.cost.toExponential(1)} · ${rep.n_iter} avaliações`
        : `${rep.starts.length} arranques no mesmo ótimo · condição ${fint(rep.condition_number)} · ${fmt(rep.elapsed_s, 1)} s`;
      $("#sdmout").innerHTML = `<div class="alert info">${esc(conv)}</div>
        <table class="spec mt">${[["IL_ref", r.IL_ref, "A", 4], ["I0_ref", r.I0_ref, "A", -1], ["Rs", r.Rs, "Ω", 4], ["Rsh_ref", r.Rsh_ref, "Ω", 1], ["a_ref", r.a_ref, "V", 4], ["n", r.n, "", 4], ["Ns", r.n_cells, "", 0]]
          .map(([k, v, u, dd]) => `<tr><td>${k}</td><td class="${v == null ? "na" : ""}">${v == null ? "não atribuído" : (dd < 0 ? v.toExponential(3) : fmt(v, dd)) + " " + u}</td></tr>`).join("")}</table>
        ${d.method === "multiponto" ? `<table class="spec mt">${rep.lab_metrics.map((x) => `<tr><td>Laboratório ${x.variable}: RMSE</td><td>${fmt(x.RMSE, 3)} ${x.variable === "Pmp" ? "W" : x.variable === "Isc" ? "A" : "V"}</td></tr>`).join("")}</table>` : ""}
        <div class="row mt" style="flex:none"><button class="btn" id="sdmsave">Salvar identificação</button></div>`;
      $("#sdmsave").onclick = async () => { const s = await api("/api/sdm/save", { body: { module_id: m.id } }); toast(`Identificação salva: ${s.file}`); };
      S.lib = await api("/api/library");
      toast("Parâmetros SDM estimados. M4 disponível.");
      if (m.id === S.moduleId) { S.models.add("M4"); S.focus = "M4"; simulate(); }
    } catch (e) { $("#sdmout").innerHTML = `<div class="alert bad">${esc(e.message)}</div>`; }
  };
  $("#sdmgo").onclick = () => go(false);
  if ($("#sdmload")) $("#sdmload").onclick = () => go(true);
}
function openNewModule() {
  const f = [["id", "Identificador", "text"], ["manufacturer", "Fabricante", "text"], ["model", "Modelo", "text"], ["p_stc_W", "Pmax STC [W]"], ["v_oc_V", "Voc [V]"], ["i_sc_A", "Isc [A]"],
    ["v_mp_V", "Vmp [V]"], ["i_mp_A", "Imp [A]"], ["n_cells_series", "Ns (células em série)"], ["alpha_isc_pct_C", "α Isc [%/°C]"], ["beta_voc_pct_C", "β Voc [%/°C]"], ["gamma_pmax_pct_C", "γ Pmax [%/°C]"],
    ["noct_C", "NOCT [°C]"], ["length_m", "Comprimento [m]"], ["width_m", "Largura [m]"], ["source", "Fonte (datasheet/versão)", "text"]];
  drawer.open("Novo módulo comercial", `<p class="notes" style="margin-top:0">Valores de datasheet em STC. Campos vazios ficam indisponíveis e nunca são inventados.</p>
    <div class="field"><label>Tecnologia</label><select class="in" id="nf_technology">${["Mono-Si", "Mono-PERC", "Poly-Si", "CdTe", "CIGS"].map((t) => `<option>${t}</option>`).join("")}</select></div>
    <div class="grid g2" style="gap:0 12px">${f.map(([k, l, t]) => `<div class="field"><label>${l}</label><input class="in" id="nf_${k}" type="${t || "number"}" step="any"></div>`).join("")}</div>
    <div id="nfissues"></div>`, `<button class="btn" id="nfback">Voltar</button><button class="btn primary" id="nfsave">Salvar módulo</button>`);
  const read = () => { const o = { technology: $("#nf_technology").value }; for (const [k, , t] of f) { const v = $("#nf_" + k).value.trim(); o[k] = v === "" ? null : t === "text" ? v : +v; } if (o.n_cells_series) o.n_cells_series = Math.round(o.n_cells_series); o.p_stc_W ??= 0; return o; };
  const check = async () => { const r = await api("/api/modules/validate", { body: read() }); $("#nfissues").innerHTML = r.issues.map((i) => `<div class="alert ${i.level === "erro" ? "bad" : ""}" style="margin-top:6px">${esc(i.msg)}</div>`).join(""); return r.issues; };
  $$("input,select", $("#dbody")).forEach((x) => (x.onchange = check));
  $("#nfback").onclick = () => openModule();
  $("#nfsave").onclick = async () => {
    const iss = await check(); if (iss.some((i) => i.level === "erro")) return;
    try { const r = await api("/api/modules", { body: read() }); S.lib = await api("/api/library"); S.moduleId = r.id; drawer.close(); toast("Módulo salvo."); drawTiles(); drawPills(); simulate(); }
    catch (e) { toast(e.message, true); }
  };
}
function openArray() {
  drawer.open("Arranjo série × paralelo", `
    <div class="grid g2"><div class="field"><label>Módulos em série (Ns)</label><div class="stepper"><button data-d="-1" data-k="ns">−</button><input id="ans" value="${S.ns}" inputmode="numeric"><button data-d="1" data-k="ns">+</button></div></div>
    <div class="field"><label>Strings em paralelo (Np)</label><div class="stepper"><button data-d="-1" data-k="np">−</button><input id="anp" value="${S.np}" inputmode="numeric"><button data-d="1" data-k="np">+</button></div></div></div>
    <div id="agrid" class="arraygrid"></div><p id="ainfo" class="sub"></p>
    <p class="notes">O motor calcula a potência de um módulo e multiplica por Ns·Np (módulos idênticos, sem perdas de mismatch, cabeamento ou conversão). As curvas I–V escalam tensão por Ns e corrente por Np.</p>`,
    `<button class="btn primary" id="aok">Aplicar</button>`);
  const upd = () => {
    const ns = Math.max(1, Math.min(60, +$("#ans").value || 1)), np = Math.max(1, Math.min(60, +$("#anp").value || 1));
    $("#ans").value = ns; $("#anp").value = np;
    const shown = Math.min(ns, 24), shownp = Math.min(np, 10);
    $("#agrid").style.gridTemplateColumns = `repeat(${shown},22px)`;
    $("#agrid").innerHTML = Array.from({ length: shown * shownp }, (_, i) => `<i style="animation-delay:${Math.min(i, 40) * 12}ms"></i>`).join("");
    const m = mod(); $("#ainfo").innerHTML = `${ns * np} módulos · ${fmt((m.p_stc_W * ns * np) / 1000, 2)} kWp${m.v_oc_V ? ` · Voc do string ≈ ${fmt(m.v_oc_V * ns, 0)} V` : ""}${ns > 24 || np > 10 ? " · (desenho parcial)" : ""}`;
  };
  $$(".stepper button").forEach((b) => (b.onclick = () => { const i = $(b.dataset.k === "ns" ? "#ans" : "#anp"); i.value = Math.max(1, (+i.value || 1) + +b.dataset.d); upd(); }));
  $("#ans").oninput = upd; $("#anp").oninput = upd; upd();
  $("#aok").onclick = () => { S.ns = +$("#ans").value; S.np = +$("#anp").value; drawer.close(); drawTiles(); simulate(); };
}
async function openWeather() {
  const w = { ...S.weather };
  drawer.open("Clima e irradiância", `<div class="seg" id="wseg">${[["supsi", "SUPSI medido"], ["csv", "CSV próprio"], ["synthetic", "Sintético"], ["manual", "Manual"]].map(([k, l]) => `<button data-k="${k}" class="${w.source === k ? "on" : ""}">${l}</button>`).join("")}</div><div id="wbody" class="mt"></div>`,
    `<button class="btn primary" id="wok">Aplicar</button>`);
  const tabs = {
    supsi: async () => {
      S.days ??= await api("/api/supsi/days");
      const sel = new Set(w.source === "supsi" ? w.days : ["2019-05-14"]);
      const max = Math.max(...S.days.map((d) => d.h));
      const byMonth = {}; S.days.forEach((d) => ((byMonth[d.day.slice(0, 7)] ??= {})[d.day] = d));
      const col = (h) => { const t = h / max; return `rgb(${Math.round(255 - 13 * t)},${Math.round(244 - 75 * t)},${Math.round(214 - 214 * t)})`; };
      const cal = () => {
        $("#wbody").innerHTML = `<p class="notes" style="margin-top:0">Cor = irradiação POA do dia. Clique para escolher; Ctrl/⌘+clique para somar dias (até 10).</p>
        <div class="cal">${Object.entries(byMonth).map(([mo, ds]) => { const first = new Date(mo + "-01T12:00"); const pad = (first.getDay() + 6) % 7; const n = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
          return `<div class="mo"><b>${first.toLocaleDateString("pt-BR", { month: "short" })}</b><div class="days">${"<i class='d empty'></i>".repeat(pad)}${Array.from({ length: n }, (_, i) => { const k = `${mo}-${String(i + 1).padStart(2, "0")}`; const d = ds[k];
            return d ? `<button class="d ${sel.has(k) ? "sel" : ""}" data-k="${k}" style="background:${col(d.h)}" title="${new Date(k + "T12:00").toLocaleDateString("pt-BR")} · ${fmt(d.h, 2)} kWh/m² · Gmax ${fint(d.g_max)} W/m²"></button>` : `<i class="d none" title="sem dados"></i>`; }).join("")}</div></div>`; }).join("")}</div>
        <div class="legend mt">baixa <i style="background:${col(0)}"></i><i style="background:${col(max / 2)}"></i><i style="background:${col(max)}"></i> alta irradiação · <span id="wsel"></span></div>`;
        $("#wsel").textContent = `${sel.size} dia(s) selecionado(s)`;
        $$(".cal .d[data-k]").forEach((b) => (b.onclick = (e) => { const k = b.dataset.k; if (e.ctrlKey || e.metaKey) { sel.has(k) ? sel.delete(k) : sel.size < 10 && sel.add(k); if (!sel.size) sel.add(k); } else { sel.clear(); sel.add(k); } w.days = [...sel].sort(); cal(); }));
      };
      w.days = [...sel]; cal();
    },
    csv: () => {
      $("#wbody").innerHTML = `<label class="drop" id="wdrop"><input type="file" accept=".csv,.txt" id="wfile" hidden><b>Solte um CSV aqui</b><br>ou clique para escolher · separador detectado automaticamente</label><div id="wmap" class="mt"></div>`;
      const load = async (file) => { const text = await file.text(); try { const r = await api("/api/csv/inspect", { body: { text } }); S.csv = { name: file.name, text, ...r }; mapping(); } catch (e) { toast(e.message, true); } };
      $("#wfile").onchange = (e) => e.target.files[0] && load(e.target.files[0]);
      const dz = $("#wdrop"); dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("over"); }; dz.ondragleave = () => dz.classList.remove("over"); dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove("over"); e.dataTransfer.files[0] && load(e.dataTransfer.files[0]); };
      const mapping = () => {
        const c = S.csv; if (!c) return; const opt = (sel) => c.columns.map((x) => `<option ${x === sel ? "selected" : ""}>${esc(x)}</option>`).join("");
        $("#wmap").innerHTML = `<p class="sub"><b>${esc(c.name)}</b> · ${fint(c.rows)} linhas</p>
          <div class="grid g2" style="gap:0 12px"><div class="field"><label>Tempo</label><select class="in" id="m_ts">${opt(w.ts_col || c.columns[0])}</select></div>
          <div class="field"><label>Irradiância</label><select class="in" id="m_g">${opt(w.g_col || c.columns[1])}</select></div></div>
          <div class="field"><label>Essa irradiância é…</label><div class="seg" id="m_kind"><button data-k="POA" class="${w.g_kind !== "GHI" ? "on" : ""}">POA (plano do módulo)</button><button data-k="GHI" class="${w.g_kind === "GHI" ? "on" : ""}">GHI (horizontal)</button></div></div>
          <div id="m_ghi"></div>
          <div class="grid g2" style="gap:0 12px"><div class="field"><label>Temperatura (opcional)</label><select class="in" id="m_t"><option value="">—</option>${opt(w.t_col)}</select></div>
          <div class="field"><label>Tipo</label><select class="in" id="m_tk">${["Tamb", "Tmod", "Tcell"].map((k) => `<option ${w.t_kind === k ? "selected" : ""}>${k}</option>`).join("")}</select></div></div>
          <div class="field"><label>Vento (opcional)</label><select class="in" id="m_w"><option value="">—</option>${opt(w.w_col)}</select></div>`;
        const ghi = () => { $("#m_ghi").innerHTML = w.g_kind === "GHI" ? `<div class="alert">GHI não é POA. A transposição para plano inclinado não está implementada; só é possível usar GHI se o módulo estiver na horizontal.</div><label class="switch mt"><input type="checkbox" id="m_h" ${w.horizontal ? "checked" : ""}> Módulo instalado na horizontal (inclinação 0°): POA = GHI</label>` : ""; if ($("#m_h")) $("#m_h").onchange = (e) => (w.horizontal = e.target.checked); };
        $$("#m_kind button").forEach((b) => (b.onclick = () => { w.g_kind = b.dataset.k; $$("#m_kind button").forEach((x) => x.classList.toggle("on", x === b)); ghi(); }));
        ghi();
      };
      mapping();
    },
    synthetic: () => {
      $("#wbody").innerHTML = `<div class="field"><label>Perfil</label><select class="in" id="s_p">${META.synthetic_profiles.map((p) => `<option ${p === (w.profile || META.synthetic_profiles[1]) ? "selected" : ""}>${esc(p)}</option>`).join("")}</select></div>
        <div class="field"><label>Estação</label><select class="in" id="s_s">${META.seasons.map((p) => `<option ${p === w.season ? "selected" : ""}>${esc(p)}</option>`).join("")}</select></div>
        <div class="grid g2" style="gap:0 12px"><div class="field"><label>Horizonte [h]</label><input class="in" id="s_d" type="number" value="${(w.duration_min || 1440) / 60}" min="1" max="168"></div>
        <div class="field"><label>Passo [min]</label><input class="in" id="s_st" type="number" value="${w.step_min || 5}" min="1" max="60"></div>
        <div class="field"><label>Pico [W/m²] (vazio = padrão)</label><input class="in" id="s_g" type="number" value="${w.g_peak || ""}"></div>
        <div class="field"><label>Semente</label><input class="in" id="s_seed" type="number" value="${w.seed ?? 42}"></div></div>
        <div class="alert info">Perfil sintético do código legado. A irradiância gerada é tratada como POA simulada.</div>`;
    },
    manual: () => {
      $("#wbody").innerHTML = `<div class="field"><label>Irradiância POA: <b id="mgv">${fint(w.g ?? 800)}</b> W/m²</label><input type="range" id="m_gg" min="0" max="1300" step="10" value="${w.g ?? 800}"></div>
        <div class="grid g2" style="gap:0 12px"><div class="field"><label>Temperatura informada</label><select class="in" id="m_tk2">${["Tamb", "Tmod", "Tcell"].map((k) => `<option ${(w.t_kind || "Tamb") === k ? "selected" : ""}>${k}</option>`).join("")}</select></div>
        <div class="field"><label>Valor [°C]</label><input class="in" id="m_tv" type="number" value="${w.t ?? 25}"></div>
        <div class="field"><label>Duração [min]</label><input class="in" id="m_du" type="number" value="${w.duration_min ?? 60}"></div>
        <div class="field"><label>Vento [m/s] (Faiman)</label><input class="in" id="m_wi" type="number" value="${w.wind ?? 1}"></div></div>`;
      $("#m_gg").oninput = (e) => ($("#mgv").textContent = fint(+e.target.value));
    },
  };
  const show = async (k) => { w.source = k; $$("#wseg button").forEach((b) => b.classList.toggle("on", b.dataset.k === k)); $("#wbody").innerHTML = `<div class="skel" style="height:180px"></div>`; await tabs[k](); };
  $$("#wseg button").forEach((b) => (b.onclick = () => show(b.dataset.k)));
  await show(w.source);
  $("#wok").onclick = () => {
    const src = w.source;
    if (src === "supsi") S.weather = { source: "supsi", days: w.days };
    else if (src === "csv") { if (!S.csv) return toast("Carregue um CSV primeiro.", true); S.weather = { source: "csv", text: S.csv.text, ts_col: $("#m_ts").value, g_col: $("#m_g").value, g_kind: w.g_kind || "POA", horizontal: !!w.horizontal, t_col: $("#m_t").value, t_kind: $("#m_tk").value, w_col: $("#m_w").value }; }
    else if (src === "synthetic") S.weather = { source: "synthetic", profile: $("#s_p").value, season: $("#s_s").value, duration_min: Math.round(+$("#s_d").value * 60), step_min: +$("#s_st").value, g_peak: $("#s_g").value || null, seed: +$("#s_seed").value };
    else S.weather = { source: "manual", g: +$("#m_gg").value, t: +$("#m_tv").value, t_kind: $("#m_tk2").value, duration_min: +$("#m_du").value, wind: +$("#m_wi").value };
    S.iv.idx = null; drawer.close(); drawTiles(); simulate();
  };
}
function openThermal() {
  const th = S.res?.thermal;
  if (!th || !th.options.length) { drawer.open("Temperatura", `<div class="alert">A entrada meteorológica atual não traz temperatura. Somente M1 (que não usa temperatura) pode ser avaliado. Use os dados SUPSI, um CSV com temperatura, o perfil sintético ou a condição manual.</div>`); return; }
  let sel = th.used, dT = S.thermal.delta_t;
  drawer.open("Modelo térmico", `<p class="notes" style="margin-top:0">M2 e M4 usam temperatura de célula (Tcell); M3 (Huld) usa temperatura posterior do módulo (Tmod). As duas nunca são confundidas.</p>
    <div class="radiocards" id="tcards">${th.options.map((o) => `<div class="radiocard ${o.id === sel ? "on" : ""} ${o.ok ? "" : "off"}" data-id="${o.id}"><div><b>${esc(o.label.split(";")[0])}</b><span>${esc(o.label.split(";")[1] || "")}${o.ok ? "" : " — indisponível: " + esc(o.why)}</span></div></div>`).join("")}</div>
    <div class="field mt2"><label>ΔT célula–módulo a 1000 W/m²: <b id="dtv">${fmt(dT, 1)}</b> °C ${chip("hipotese", "hipótese")}</label><input type="range" id="dtr" min="0" max="10" step="0.5" value="${dT}">
    <span class="hint">Sandia eq. 23 (IEA PVPS T13-20:2020, p. 99): Tcell = Tmod + G/1000·ΔT. Valor típico 3 °C, não medido.</span></div>`,
    `<button class="btn primary" id="tok">Aplicar</button>`);
  $$("#tcards .radiocard").forEach((c) => (c.onclick = () => { if (c.classList.contains("off")) return; sel = c.dataset.id; $$("#tcards .radiocard").forEach((x) => x.classList.toggle("on", x === c)); }));
  $("#dtr").oninput = (e) => { dT = +e.target.value; $("#dtv").textContent = fmt(dT, 1); };
  $("#tok").onclick = () => { S.thermal = { strategy: sel, delta_t: dT }; drawer.close(); simulate(); };
}
