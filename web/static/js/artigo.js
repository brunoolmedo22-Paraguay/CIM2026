// Modo Artigo: dados e qualidade, protocolo/execução, resultados com discussão, histórico.
import { $, $$, api, fmt, fint, fsmart, factor, esc, mtag, chip, toast, countUp, plot, exportPlot, gapped, fillSegments, discussion, table, icon, META } from "./ui.js";

const MONTHS = ["2019_01", "2019_02", "2019_03", "2019_04", "2019_05", "2019_06"];
const ML = { "2019_01": "jan", "2019_02": "fev", "2019_03": "mar", "2019_04": "abr", "2019_05": "mai", "2019_06": "jun" };
const SEV = { erro: "#B83A3A", suspeito: "#D98E04", condicao: "#7F92A4" };
const P = { months: [...MONTHS], g: 100, strategy: "A_tmod_medida", policy: "sinalizar", day: "2019-05-14", dt: 3, reps: 11, order: "rotativa", seed: 20261019, mode: "vetorizado", scaling: true, sens: true, tm: true, label: "" };
const R = { id: null, run: null, tab: "energia", series: null, range: null, ov: { g: true, anom: true, t: false } };
const qs = () => `months=${P.months.join(",")}&g=${P.g}&strategy=${P.strategy}&policy=${P.policy}`;
const card = (inner, cls = "") => `<section class="card pad ${cls}">${inner}</section>`;
const hd = (t, s = "", tools = "") => `<div class="hd"><div class="grow"><h3>${t}</h3>${s ? `<div class="sub">${s}</div>` : ""}</div>${tools}</div>`;

// =================================================================== DADOS
export async function dados(el) {
  el.innerHTML = `<div class="page"><p class="lede">O conjunto de validação é independente da calibração. Antes de comparar modelos, esta página mostra o que o dataset
    contém: cobertura, exclusões e <b>inconsistências físicas nas próprias medições</b> — potência sem irradiância, Isc incoerente com Gpoa, saltos de temperatura.</p>
    <div class="toolbar card pad" style="padding:12px 16px"><div><small class="sub">Meses</small><div class="seg" id="dmon">${MONTHS.map((m) => `<button data-m="${m}" class="${P.months.includes(m) ? "on" : ""}">${ML[m]}</button>`).join("")}</div></div>
      <div><small class="sub">Limiar Gpoa</small><div class="seg" id="dg">${[50, 100, 200].map((g) => `<button data-g="${g}" class="${P.g === g ? "on" : ""}">≥ ${g} W/m²</button>`).join("")}</div></div>
      <div><small class="sub">Anomalias</small><div class="seg" id="dpol">${[["sinalizar", "apenas sinalizar"], ["excluir_erros", "excluir erros"], ["excluir_erros_suspeitos", "excluir erros e suspeitas"]].map(([k, l]) => `<button data-p="${k}" class="${P.policy === k ? "on" : ""}">${l}</button>`).join("")}</div></div></div>
    <div class="kpis" id="dk" style="grid-template-columns:repeat(5,minmax(0,1fr))"></div>
    <div class="grid g2"><div id="danom"></div><div class="card pad"><div id="dhist1" style="height:210px"></div><div id="dhist2" style="height:210px"></div></div></div>
    <div class="sec-title"><h2>Explorar um dia</h2><span>cor do calendário = amostras com anomalia (erro ou suspeita) na máscara</span></div>
    <div class="card pad"><div id="dcal"></div></div>
    <div class="card pad mt"><div id="dayhd"></div><div id="daychart" style="height:440px"></div><div id="daytab" class="mt"></div></div>
    <div class="sec-title"><h2>Laboratório SUPSI (IEC 61853-1)</h2><span>fonte exclusiva da calibração do SDM</span></div><div id="dlab"></div></div>`;
  $$("#dmon button").forEach((b) => (b.onclick = () => { const m = b.dataset.m; P.months.includes(m) ? P.months.length > 1 && P.months.splice(P.months.indexOf(m), 1) : P.months.push(m); P.months.sort(); b.classList.toggle("on", P.months.includes(m)); loadQ(); }));
  $$("#dg button").forEach((b) => (b.onclick = () => { P.g = +b.dataset.g; $$("#dg button").forEach((x) => x.classList.toggle("on", x === b)); loadQ(); }));
  $$("#dpol button").forEach((b) => (b.onclick = () => { P.policy = b.dataset.p; $$("#dpol button").forEach((x) => x.classList.toggle("on", x === b)); loadQ(); }));
  $("#dk").innerHTML = Array.from({ length: 5 }, () => `<div class="kpi skel" style="height:92px"></div>`).join("");
  loadQ(); loadLab();
}
async function loadQ() {
  const q = await api(`/api/artigo/quality?${qs()}`);
  const tot = q.monthly[q.monthly.length - 1];
  const an = q.anomalies; const nbad = an.filter((a) => a.severidade !== "condicao").reduce((s, a) => s + a.n_elegiveis, 0);
  const k = [["Registros lidos", tot.n_total, "linhas originais, nenhuma apagada"], ["Elegíveis", tot.n_elegivel, `${fmt(100 * tot.n_elegivel / tot.n_total, 1)} % · mesma máscara p/ 4 modelos`],
    ["Pares integráveis", tot.pares_validos, `${fmt(tot.horas_cobertas_pares_validos, 1)} h cobertas`], ["Excluídas", tot.n_total - tot.n_elegivel, "NaN na fonte, G abaixo do limiar…"],
    ["Marcações de anomalia", nbad, "na máscara (erro + suspeita; podem se sobrepor)"]];
  $("#dk").innerHTML = k.map(([l, v, s], i) => `<div class="kpi" style="${i === 4 ? "border-top:3px solid #B83A3A" : ""}"><small>${l}</small><b id="dk${i}">0</b><span>${s}</span></div>`).join("");
  k.forEach(([, v], i) => countUp($(`#dk${i}`), v, (x) => fint(x)));
  const mx = Math.max(1, ...an.map((a) => a.n_todas));
  $("#danom").innerHTML = card(hd("Inconsistências físicas no dataset", "Critérios fixados antes de olhar os erros dos modelos; usam só grandezas medidas.") +
    an.map((a) => `<div class="anomcard"><code>${a.codigo}</code><div><b>${esc(a.anomalia)}</b> ${chip(a.severidade === "erro" ? "bad" : a.severidade === "suspeito" ? "estimado" : "", a.severidade)}</div><div class="n">${fint(a.n_elegiveis)}<small style="display:block;color:var(--muted);font-weight:400">${fmt(a.pct_elegiveis, 2)} %</small></div>
      <div class="bar"><i style="width:${(100 * a.n_todas) / mx}%;background:${SEV[a.severidade]}"></i></div><small>${esc(a.regra)} · ${fint(a.n_todas)} em todo o conjunto</small></div>`).join(""));
  const hist = (el, counts, lo, hi, band, title, xt) => {
    const w = (hi - lo) / counts.length, x = counts.map((_, i) => lo + w * (i + 0.5));
    plot($(el), [{ x, y: counts, type: "bar", marker: { color: x.map((v) => (v < band[0] || v > band[1] ? "#B83A3A" : "#3B82C4")) }, hovertemplate: "%{x:.2f}: %{y}<extra></extra>" }],
      { margin: { t: 28, b: 38 }, title: { text: title, x: 0, font: { size: 13 } }, xaxis: { title: { text: xt } }, yaxis: { title: { text: "amostras" } }, bargap: 0.05,
        shapes: [{ type: "rect", xref: "x", yref: "paper", x0: band[0], x1: band[1], y0: 0, y1: 1, fillcolor: "rgba(30,158,122,.07)", line: { width: 0 } }] });
  };
  hist("#dhist1", q.isc_ratio_hist, 0.4, 1.6, [0.8, 1.2], "Coerência Isc × Gpoa (vermelho = A05)", "Isc / (Isc_STC · G/1000)");
  hist("#dhist2", q.pr_hist, 0.2, 1.8, [0.5, 1.25], "Razão de desempenho instantânea (vermelho = A03/A04)", "Pm / (Pstc · G/1000)");
  const byDay = Object.fromEntries(q.days.map((d) => [d.day, d]));
  const mxa = Math.max(1, ...q.days.map((d) => d.n_anom));
  const months = [...new Set(q.days.map((d) => d.day.slice(0, 7)))];
  const col = (n) => (n === 0 ? "#DCEFE6" : `rgba(184,58,58,${0.18 + 0.82 * Math.sqrt(n / mxa)})`);
  $("#dcal").innerHTML = `<div class="cal">${months.map((mo) => { const f = new Date(mo + "-01T12:00"), pad = (f.getDay() + 6) % 7, n = new Date(f.getFullYear(), f.getMonth() + 1, 0).getDate();
    return `<div class="mo"><b>${f.toLocaleDateString("pt-BR", { month: "long" })}</b><div class="days">${"<i class='d empty'></i>".repeat(pad)}${Array.from({ length: n }, (_, i) => { const k = `${mo}-${String(i + 1).padStart(2, "0")}`, d = byDay[k];
      return d ? `<button class="d ${k === P.day ? "sel" : ""}" data-k="${k}" style="background:${col(d.n_anom)}" title="${new Date(k + "T12:00").toLocaleDateString("pt-BR")} · ${d.n_el}/${d.n} elegíveis · ${d.n_anom} com anomalia"></button>` : `<i class="d none"></i>`; }).join("")}</div></div>`; }).join("")}</div>
    <div class="legend mt"><i style="background:#DCEFE6"></i> sem anomalias <i style="background:rgba(184,58,58,.35)"></i><i style="background:rgba(184,58,58,1)"></i> mais anomalias · clique em um dia</div>`;
  $$("#dcal .d[data-k]").forEach((b) => (b.onclick = () => { P.day = b.dataset.k; $$("#dcal .d").forEach((x) => x.classList.toggle("sel", x === b)); loadDay(); }));
  if (!byDay[P.day]) P.day = q.days[0]?.day;
  loadDay();
}
async function loadDay() {
  const rows = await api(`/api/artigo/day?${qs()}&day=${P.day}`);
  const ts = rows.map((r) => r.timestamp);
  $("#dayhd").innerHTML = hd(`${new Date(P.day + "T12:00").toLocaleDateString("pt-BR", { weekday: "long", day: "2-digit", month: "long", year: "numeric" })}`,
    `${rows.length} registros · ${rows.filter((r) => r.eligible).length} elegíveis · ${rows.filter((r) => r.anom_codes).length} com marcação`,
    `<div class="toolbar"><label class="switch sunny"><input type="checkbox" id="dyg" checked> Irradiância (eixo direito)</label><label class="switch"><input type="checkbox" id="dyi"> Isc × escala</label><label class="switch"><input type="checkbox" id="dyt"> Temperaturas</label></div>`);
  const draw = () => {
    const tr = [];
    const [x1, y1] = gapped(ts, rows.map((r) => r.p_mpp_measured_W), 7.5);
    if ($("#dyg").checked) tr.push(...fillSegments(ts, rows.map((r) => r.g_poa_Wm2), 7.5, { name: "Gpoa", yaxis: "y2", fill: "tozeroy", fillcolor: "rgba(242,169,0,.15)", line: { color: "rgba(242,169,0,.95)", width: 1.2 }, hovertemplate: "%{y:.0f} W/m²<extra>Gpoa</extra>" }));
    if ($("#dyi").checked) { const [x, y] = gapped(ts, rows.map((r) => r.isc_measured_A == null ? null : r.isc_measured_A * 1000 / 9.4868), 7.5); tr.push({ x, y, name: "Isc → irradiância equivalente", yaxis: "y2", line: { color: "#5B3F8A", width: 1.3, dash: "dot" }, hovertemplate: "%{y:.0f} W/m² eq.<extra>Isc</extra>" }); }
    if ($("#dyt").checked) { const [x, y] = gapped(ts, rows.map((r) => r.t_module_C), 7.5); tr.push({ x, y, name: "Tbom [°C]", line: { color: "#B4507A", width: 1.2 }, yaxis: "y3" }); const [xa, ya] = gapped(ts, rows.map((r) => r.t_amb_C), 7.5); tr.push({ x: xa, y: ya, name: "Tamb [°C]", line: { color: "#3B82C4", width: 1.2 }, yaxis: "y3" }); }
    tr.push({ x: x1, y: y1, name: "Pm medida", line: { color: "#13202D", width: 2.2 }, hovertemplate: "%{y:.1f} W<extra>Pm</extra>" });
    const ex = rows.filter((r) => !r.eligible);
    tr.push({ x: ex.map((r) => r.timestamp), y: ex.map((r) => r.p_mpp_measured_W ?? 0), name: "fora da máscara", mode: "markers", marker: { symbol: "x-thin", size: 9, line: { width: 1.6, color: "#8A99A7" } }, text: ex.map((r) => r.reasons), hovertemplate: "excluída: %{text}<extra></extra>" });
    const an = rows.filter((r) => r.anom_codes && r.anom_severidade !== "condicao");
    tr.push({ x: an.map((r) => r.timestamp), y: an.map((r) => r.p_mpp_measured_W ?? 0), name: "anomalia física", mode: "markers", marker: { symbol: "diamond", size: 10, color: an.map((r) => SEV[r.anom_severidade]), line: { color: "#fff", width: 1 } },
      text: an.map((r) => r.anom_codes.split(";").map((c) => `${c} ${META.anomalies[c][1]}`).join("<br>")), hovertemplate: "%{text}<extra></extra>" });
    const t3 = $("#dyt").checked;
    plot($("#daychart"), tr, { hovermode: "x unified", margin: { r: t3 ? 110 : 64 }, xaxis: { domain: [0, t3 ? 0.9 : 1] }, yaxis: { title: { text: "Potência [W]" }, rangemode: "tozero" },
      yaxis2: { title: { text: "Irradiância [W/m²]" }, overlaying: "y", side: "right", rangemode: "tozero", showgrid: false },
      yaxis3: { title: { text: "°C" }, overlaying: "y", side: "right", anchor: "free", position: 1, showgrid: false } }, `dia_${P.day}`);
  };
  ["#dyg", "#dyi", "#dyt"].forEach((s) => ($(s).onchange = draw));
  draw();
  const bad = rows.filter((r) => r.anom_codes);
  $("#daytab").innerHTML = bad.length ? table(bad, [{ h: "Hora", k: "timestamp", f: (v) => v.slice(11, 16) }, { h: "Pm [W]", k: "p_mpp_measured_W", r: 1, f: (v) => fmt(v, 1) }, { h: "Gpoa [W/m²]", k: "g_poa_Wm2", r: 1, f: (v) => fmt(v, 0) },
    { h: "Pm/(Pstc·G)", k: "pr_inst", r: 1, f: (v) => fmt(v, 2) }, { h: "Isc/(Isc_STC·G)", k: "isc_ratio", r: 1, f: (v) => fmt(v, 2) }, { h: "Marcações", k: "anom_codes", f: (v) => v.split(";").map((c) => `<span title="${esc(META.anomalies[c][2])}">${c} ${esc(META.anomalies[c][1])}</span>`).join("<br>") },
    { h: "Na máscara", k: "eligible", f: (v) => (v ? "sim" : "não") }, { h: "Origem", k: "source_row", f: (v, r) => `${r.source_file}:${v}` }]) : `<div class="alert info">Nenhuma marcação neste dia.</div>`;
}
async function loadLab() {
  const L = await api("/api/lab");
  $("#dlab").innerHTML = `<div class="grid g3">${["Pmp", "Isc", "Voc"].map((v) => card(`<div id="lab${v}" style="height:250px"></div>`)).join("")}</div>
    <div class="grid g2 mt">${card(hd("Verificações automáticas", `Coeficientes medidos: α ${L.coefficients.alpha_isc_pct_per_C} %/°C · β ${L.coefficients.beta_voc_pct_per_C} %/°C · γ ${L.coefficients.gamma_pmax_pct_per_C} %/°C · U0 ${L.thermal.u0_W_m2K} · U1 ${L.thermal.u1_W_s_m3K} · NMOT ${L.thermal.nmot_C} °C`) +
      L.checks.map((c) => `<div class="anomcard" style="grid-template-columns:auto 1fr"><code style="color:${c.ok ? "var(--ok)" : "var(--bad)"}">${c.ok ? "OK" : "FALHA"}</code><div>${esc(c.check)}</div></div>`).join("") +
      `<p class="notes">As 18 células sem medição aparecem no XML como string compartilhada nº 32 (vazia): nenhum «32» é tratado como medição. A fonte rotula a tabela de Voc como «Voc[A]» — erro de unidade documentado, não corrigido.</p>`)}
    ${card(hd("Calibração multiponto do SDM", "Somente as 66 medições de laboratório; o campo 2019 nunca entra no ajuste.", `<button class="btn sun" id="calgo">${icon.sun} Pré-visualizar ajuste</button>`) + `<div id="calout"><p class="notes">O experimento recalibra ao iniciar com a mesma configuração (≈ 10 s, registrado como calibration_s).</p></div>`)}</div>`;
  for (const v of ["Pmp", "Isc", "Voc"]) {
    const m = L.matrices[v];
    plot($(`#lab${v}`), [{ type: "heatmap", z: m.z, x: m.T.map((t) => `${t} °C`), y: m.G.map((g) => `${g}`), colorscale: [[0, "#EAF1F7"], [1, "#1A5276"]], showscale: false, hovertemplate: "G=%{y} · %{x}: %{z:.3f}<extra></extra>",
      text: m.z.map((r) => r.map((x) => (x == null ? "" : fmt(x, v === "Pmp" ? 1 : 2)))), texttemplate: "%{text}", textfont: { size: 11 } }],
      { margin: { t: 30, l: 50, b: 30 }, title: { text: `${v} [${{ Pmp: "W", Isc: "A", Voc: "V" }[v]}]`, x: 0, font: { size: 13 } }, yaxis: { title: { text: "G [W/m²]" } } });
  }
  $("#calgo").onclick = async () => {
    $("#calout").innerHTML = `<div class="skel" style="height:140px"></div>`;
    const d = await api("/api/calibration/preview", { body: {} }); const r = d.reference, rep = d.report;
    $("#calout").innerHTML = `<table class="spec">${[["IL_ref", fmt(r.IL_ref, 4) + " A"], ["I0_ref", r.I0_ref.toExponential(3) + " A"], ["Rs", fmt(r.Rs, 4) + " Ω"], ["Rsh_ref", fmt(r.Rsh_ref, 1) + " Ω"], ["a_ref", fmt(r.a_ref, 4) + " V"],
      ["Condição do Jacobiano", fint(rep.condition_number)], ["Arranques no mesmo ótimo", `${rep.near_optimal_spread.n_near_optimal}/${rep.near_optimal_spread.n_starts}`],
      ...rep.lab_metrics.map((x) => [`RMSE laboratório ${x.variable}`, fmt(x.RMSE, 3)]),
      ...Object.entries(rep.implied_coefficients).map(([k, v]) => [`${k.split("_")[0]} implícito vs medido`, `${fmt(v.modelo_pct_C, 3)} vs ${fmt(v.medido_pct_C, 3)} %/°C`])].map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join("")}</table>
      <ul class="notes">${rep.assumptions.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>`;
  };
}

// =================================================================== PROTOCOLO
export async function protocolo(el) {
  const pills = (id, opts, cur) => `<div class="seg" id="${id}">${opts.map(([k, l]) => `<button data-k="${k}" class="${String(cur) === String(k) ? "on" : ""}">${l}</button>`).join("")}</div>`;
  el.innerHTML = `<div class="page"><p class="lede">Os critérios são congelados aqui, antes de observar qualquer erro. Cada execução vira um diretório imutável com dados, previsões, medições e discussão — reabrível sem recalcular.</p>
    <div id="runhero"></div>
    <div class="grid" style="grid-template-columns:minmax(0,1.6fr) minmax(300px,1fr);align-items:start">
    <div class="grid">
      ${card(hd("Dados de validação", "Medições exteriores SUPSI 2019 (independentes da calibração)") + `<div class="field"><label>Meses</label>${pills("pm", MONTHS.map((m) => [m, ML[m] + "/19"]), "")}</div>
        <div class="grid g2" style="gap:0 14px"><div class="field"><label>Limiar Gpoa [W/m²]</label><input class="in" id="pg" type="number" value="${P.g}" min="0" max="500"><span class="hint">Sensibilidade a 50/100/200 W/m² calculada à parte.</span></div>
        <div class="field"><label>Lacuna máxima para integrar energia [min]</label><input class="in" id="pgap" type="number" value="7.5" step="0.5"></div></div>`)}
      ${card(hd("Qualidade dos dados", "Anomalias físicas são sempre detectadas e o efeito é sempre reportado; aqui se escolhe se elas saem da máscara principal.") + `<div class="radiocards" id="ppol">${[["sinalizar", "Apenas sinalizar (padrão)", "A máscara principal mantém as amostras; a exclusão aparece como sensibilidade."], ["excluir_erros", "Excluir anomalias «erro»", "Potência sem irradiância, irradiância sem potência, P acima do plausível, Voc implausível."], ["excluir_erros_suspeitos", "Excluir «erro» e «suspeito»", "Também Isc incoerente com G, P muito baixa, saltos de temperatura, valores congelados."]].map(([k, t, s]) => `<div class="radiocard ${P.policy === k ? "on" : ""}" data-k="${k}"><div><b>${t}</b><span>${s}</span></div></div>`).join("")}</div>`)}
      ${card(hd("Modelo térmico", "Mesma temperatura por timestamp para todos os modelos") + `<div class="radiocards" id="pth">${[["A_tmod_medida", "A · Tbom medida (principal)", "Huld recebe Tmod = Tbom; M2 e M4 recebem Tcell = Tbom + G/1000·ΔT."], ["B_faiman", "B · Tmod estimada por Faiman (opcional)", "Tmod = Tamb + G/(U0 + U1·v), U0/U1 medidos pela SUPSI."]].map(([k, t, s]) => `<div class="radiocard ${P.strategy === k ? "on" : ""}" data-k="${k}"><div><b>${t}</b><span>${s}</span></div></div>`).join("")}</div>
        <div class="field mt"><label>ΔT célula–módulo: <b id="pdtv">${fmt(P.dt, 1)}</b> °C ${chip("hipotese", "hipótese")}</label><input type="range" id="pdt" min="0" max="10" step="0.5" value="${P.dt}"></div>`)}
      ${card(hd("Benchmark computacional", "Quatro modelos em sequência, nunca em paralelo; aquecimento não contabilizado") + `<div class="grid g2" style="gap:0 14px">
        <div class="field"><label>Rodadas (3–101)</label><div class="stepper"><button data-d="-1">−</button><input id="preps" value="${P.reps}"><button data-d="1">+</button></div></div>
        <div class="field"><label>Ordem dos modelos</label>${pills("pord", [["rotativa", "rotativa"], ["aleatoria", "aleatória c/ semente"]], P.order)}</div>
        <div class="field"><label>Semente</label><input class="in" id="pseed" type="number" value="${P.seed}"></div>
        <div class="field"><label>Execução</label>${pills("pmode", [["vetorizado", "vetorizada"], ["escalar", "escalar"]], P.mode)}</div></div>
        <div class="toolbar"><label class="switch"><input type="checkbox" id="psc" ${P.scaling ? "checked" : ""}> Escalabilidade (250/1000/4000)</label><label class="switch"><input type="checkbox" id="pse" ${P.sens ? "checked" : ""}> Sensibilidade ΔT e limiar</label><label class="switch"><input type="checkbox" id="ptm" ${P.tm ? "checked" : ""}> Passe tracemalloc</label></div>`)}
    </div>
    <div style="position:sticky;top:84px">${card(`<h3>Resumo congelado</h3><div id="psum" class="mt"></div>
      <div class="field mt"><label>Rótulo</label><input class="in" id="plabel" placeholder="ex.: protocolo principal" value="${esc(P.label)}"></div>
      <button class="btn big sun" id="prun" style="width:100%;justify-content:center">${icon.sun} Executar experimento científico</button><p class="notes" id="pnote"></p>`)}</div></div></div>`;
  const sum = () => {
    const est = 15457 * 0.0007 * (P.reps * (1 + (P.scaling ? 0.34 : 0)) + 2 + (P.sens ? 3 : 0) + (P.tm ? 5 : 0)) * P.months.length / 6;
    $("#psum").innerHTML = `<table class="spec">${[["Meses", P.months.map((m) => ML[m]).join(", ")], ["Limiar Gpoa", `${P.g} W/m²`], ["Anomalias", { sinalizar: "sinalizar", excluir_erros: "excluir erros", excluir_erros_suspeitos: "excluir erros e suspeitas" }[P.policy]], ["Térmica", P.strategy === "A_tmod_medida" ? "A · Tbom" : "B · Faiman"], ["ΔT", `${fmt(P.dt, 1)} °C (hipótese)`],
      ["Rodadas", `${P.reps} × 4 = ${P.reps * 4} medições`], ["Ordem", P.order], ["Semente", P.seed], ["Execução", P.mode], ["Duração estimada", `≈ ${Math.max(1, Math.round(est / 60))}–${Math.max(2, Math.round(est / 40))} min`]].map(([a, b]) => `<tr><td>${a}</td><td>${esc(b)}</td></tr>`).join("")}</table>`;
  };
  $$("#pm button").forEach((b) => { b.classList.toggle("on", P.months.includes(b.dataset.k)); b.onclick = () => { const m = b.dataset.k; P.months.includes(m) ? P.months.length > 1 && P.months.splice(P.months.indexOf(m), 1) : P.months.push(m); P.months.sort(); b.classList.toggle("on", P.months.includes(m)); sum(); }; });
  const seg = (id, key, num) => $$(`#${id} button`).forEach((b) => (b.onclick = () => { P[key] = num ? +b.dataset.k : b.dataset.k; $$(`#${id} button`).forEach((x) => x.classList.toggle("on", x === b)); sum(); }));
  seg("pord", "order"); seg("pmode", "mode");
  const rc = (id, key) => $$(`#${id} .radiocard`).forEach((c) => (c.onclick = () => { P[key] = c.dataset.k; $$(`#${id} .radiocard`).forEach((x) => x.classList.toggle("on", x === c)); sum(); }));
  rc("ppol", "policy"); rc("pth", "strategy");
  $("#pdt").oninput = (e) => { P.dt = +e.target.value; $("#pdtv").textContent = fmt(P.dt, 1); sum(); };
  $$(".stepper button", el).forEach((b) => (b.onclick = () => { P.reps = Math.max(3, Math.min(101, P.reps + +b.dataset.d)); $("#preps").value = P.reps; sum(); }));
  $("#preps").onchange = (e) => { P.reps = Math.max(3, Math.min(101, Math.round(+e.target.value) || 11)); e.target.value = P.reps; sum(); };
  $("#pg").onchange = (e) => { P.g = +e.target.value; sum(); }; $("#pseed").onchange = (e) => { P.seed = +e.target.value; sum(); };
  $("#psc").onchange = (e) => { P.scaling = e.target.checked; sum(); }; $("#pse").onchange = (e) => { P.sens = e.target.checked; sum(); }; $("#ptm").onchange = (e) => { P.tm = e.target.checked; sum(); };
  $("#plabel").oninput = (e) => (P.label = e.target.value);
  $("#prun").onclick = async () => {
    try {
      const r = await api("/api/runs", { body: { months: P.months, g_threshold_Wm2: P.g, max_gap_min: +$("#pgap").value, thermal_strategy: P.strategy, delta_t_C: P.dt, repetitions: P.reps, order_mode: P.order, seed: P.seed,
        execution_mode: P.mode, scaling_enabled: P.scaling, sensitivity_enabled: P.sens, tracemalloc_pass: P.tm, anomaly_policy: P.policy, label: P.label } });
      toast(`Experimento ${r.run_id} iniciado.`); window.dispatchEvent(new Event("pollnow"));
    } catch (e) { toast(e.message, true); }
  };
  sum(); heroUpdate(window.__active);
}
export function heroUpdate(a) {
  const box = $("#runhero"); const btn = $("#prun");
  if (btn) { btn.disabled = !!a; $("#pnote").textContent = a ? "Há um experimento em execução; outro só começa ao final." : "O processo roda separado da interface: fechar ou recarregar a página não o interrompe nem o duplica."; }
  if (!box) return;
  if (!a) { box.innerHTML = ""; return; }
  const s = a.status || {}, b = s.benchmark || {}, idx = s.etapa_idx || 0;
  const p = progressOf(s);
  const th = Math.PI * (1 - p), x = 200 + 170 * Math.cos(th), y = 175 - 170 * Math.sin(th);
  if (!$("#sunarc")) box.innerHTML = card(`<div class="runhero"><svg id="sunarc" class="sunarc" viewBox="0 0 400 200"><path class="arc" d="M30 175 A170 170 0 0 1 370 175"/><path class="done" id="arcdone" pathLength="100" stroke-dasharray="100" d="M30 175 A170 170 0 0 1 370 175"/>
    <line x1="10" y1="175" x2="390" y2="175" stroke="#D9E1E8"/><g class="sun" id="sunpos"><circle class="glow" r="22" fill="rgba(242,169,0,.25)"/><circle r="11" fill="#F2A900"/></g><text x="200" y="168" text-anchor="middle" font-size="26" font-weight="600" fill="#13202D" id="arcpct"></text><text x="200" y="192" text-anchor="middle" font-size="11" fill="#5E6E7E" id="arcsub"></text></svg>
    <div><h3 id="herot"></h3><ul class="stages" id="hstages">${META.stages.map((st, i) => `<li data-i="${i + 1}"><i></i>${esc(st)}</li>`).join("")}</ul><div class="progress"><i id="hbar"></i></div><div class="ticker" id="htick"></div></div></div>`, "mt");
  $("#arcdone").style.strokeDashoffset = 100 - 100 * p;
  $("#sunpos").setAttribute("transform", `translate(${x},${y})`);
  $("#arcpct").textContent = `${Math.round(100 * p)} %`;
  $("#arcsub").textContent = a.run_id;
  $("#herot").textContent = `Executando: ${s.etapa || "preparando"}`;
  $$("#hstages li").forEach((li) => { const i = +li.dataset.i; li.className = i < idx ? "done" : i === idx ? "cur" : ""; });
  $("#hbar").style.width = `${b.total ? (100 * b.feitos) / b.total : 0}%`;
  $("#htick").innerHTML = b.total ? `Benchmark ${esc(b.fase || "")} · ${b.rodada ? `rodada ${b.rodada}/${b.R} · ${mtag(b.modelo, false)} posição ${b.posicao} · lote ${fint(b.batch)} · última medição ${fsmart(b.compute_s, "s")} · ` : ""}${b.feitos}/${b.total} chamadas` : esc(s.mensagem || "");
}
export function progressOf(s) {
  const idx = s.etapa_idx || 0, b = s.benchmark || {};
  if (idx < 7) return 0.03 + 0.17 * (idx / 6);
  if (idx === 7) return 0.2 + 0.7 * (b.total ? b.feitos / b.total : 0);
  return 0.9 + 0.1 * ((idx - 7) / 3);
}

// =================================================================== RESULTADOS
export async function resultados(el, id) {
  const runs = await api("/api/runs");
  const done = runs.filter((r) => r.estado === "concluido");
  if (!runs.length) { el.innerHTML = `<div class="page"><div class="empty card">Nenhuma execução ainda. <a href="#/artigo/protocolo">Configure e execute um experimento</a>.</div></div>`; return; }
  R.id = id && runs.some((r) => r.run_id === id) ? id : (R.id && runs.some((r) => r.run_id === R.id) ? R.id : (done[0] || runs[0]).run_id);
  el.innerHTML = `<div class="page"><div class="hd"><select class="in" id="rsel" style="max-width:520px">${runs.map((r) => `<option value="${r.run_id}" ${r.run_id === R.id ? "selected" : ""}>${r.run_id} · ${r.estado}${r.rotulo ? " · " + esc(r.rotulo) : ""}</option>`).join("")}</select>
    <div class="grow"></div><a class="btn" href="/api/runs/${R.id}/discussion">${icon.dl} Discussão (.md)</a><a class="btn primary" href="/api/runs/${R.id}/zip">${icon.dl} Exportar execução (ZIP)</a></div><div id="rbody"><div class="skel" style="height:320px"></div></div></div>`;
  $("#rsel").onchange = (e) => (location.hash = `#/artigo/resultados/${e.target.value}`);
  const run = await api(`/api/runs/${R.id}`);
  R.run = run; R.series = null;
  if (run.status.estado !== "concluido") { $("#rbody").innerHTML = `<div class="alert ${run.status.estado === "executando" ? "info" : "bad"}">Estado: ${esc(run.status.estado)} · etapa ${esc(run.status.etapa || "")}. ${run.status.estado === "executando" ? "Os resultados aparecem ao final." : "Saídas parciais preservadas no diretório da execução."}</div>${run.status.traceback ? `<pre class="card pad" style="overflow:auto;font-size:12px">${esc(run.status.traceback.slice(-2500))}</pre>` : ""}`; return; }
  const c = run.config, me = run.metrics_energy, env = run.metadata?.ambiente_benchmark_isolado || {};
  const nar = run.narrative || [];
  $("#rbody").innerHTML = `<div class="strip">${[["Dados", `${c.months.length} mês(es) · N ${fint(me[0].N)}`], ["Anomalias", { sinalizar: "sinalizadas", excluir_erros: "erros excluídos", excluir_erros_suspeitos: "erros+suspeitas excluídos" }[c.anomaly_policy || "sinalizar"]], ["Térmica", `${c.thermal_strategy === "A_tmod_medida" ? "A · Tbom" : "B · Faiman"} · ΔT ${fmt(c.delta_t_C, 1)} °C`], ["Limiar", `${c.g_threshold_Wm2} W/m²`], ["Rodadas", `${c.repetitions} · ${c.order_mode}`], ["Semente", c.seed], ["CPU", (env.cpu_modelo || "—").replace("Processor", "").slice(0, 26)]].map(([a, b]) => `<div><small>${a}</small><b>${esc(b)}</b></div>`).join("")}</div>
    <div class="synth"><h2>Síntese da discussão</h2><p>${esc(nar.find((i) => i.secao === "sintese")?.texto || "—")}</p></div>
    <div class="tabs" id="rtabs">${[["energia", "I · Energia"], ["computacional", "II · Computacional"], ["integrada", "III · Análise integrada"], ["estatistica", "IV · Estatística"]].map(([k, l]) => `<button data-k="${k}" class="${R.tab === k ? "on" : ""}">${l}</button>`).join("")}</div><div id="rtab"></div>`;
  $$("#rtabs button").forEach((b) => (b.onclick = () => { R.tab = b.dataset.k; $$("#rtabs button").forEach((x) => x.classList.toggle("on", x === b)); drawTab(); }));
  drawTab();
}
function drawTab() {
  const el = $("#rtab"); el.style.animation = "none"; el.offsetHeight; el.style.animation = "pagein .3s var(--ease)";
  ({ energia: tabEnergia, computacional: tabComp, integrada: tabInteg, estatistica: tabStat }[R.tab])(el, R.run);
}
const byM = (rows, k = "modelo") => Object.fromEntries((rows || []).map((r) => [r[k], r]));

function tabEnergia(el, run) {
  const me = byM(run.metrics_energy), ci = run.bootstrap_ci || [], nar = run.narrative || [];
  const rank = [...run.metrics_energy].sort((a, b) => a.NRMSE_media_pct - b.NRMSE_media_pct).map((r) => r.modelo);
  const cib = (m, k) => ci.find((x) => x.modelo === m && x.metrica === k);
  el.innerHTML = `${discussion(nar, "energia")}
    <div class="grid g4 mt">${META.models.map((m) => { const r = me[m.id], c = cib(m.id, "nRMSE_pct"); return `<div class="mcard" style="--c:${m.color}"><div class="hd" style="margin:0"><span class="grow">${mtag(m.id)}</span><span class="rank" title="posição por nRMSE">${rank.indexOf(m.id) + 1}</span></div>
      <div class="big" id="mc${m.id}">—</div><div class="sub">nRMSE · IC95 ${c ? `${fmt(c.ic95_lo, 2)}–${fmt(c.ic95_hi, 2)} %` : "—"}</div>
      <div class="lines"><span>nMAE</span><b>${fmt(r.NMAE_media_pct ?? (100 * r.MAE_W / r.P_obs_media_W), 2)} %</b><span>nMBE (viés)</span><b>${fmt(r.NMBE_media_pct, 2, { sign: true })} %</b><span>Erro de energia</span><b>${fmt(r.erro_energia_pct, 2, { sign: true })} %</b><span>RMSE · MAE</span><b>${fmt(r.RMSE_W, 1)} · ${fmt(r.MAE_W, 1)} W</b><span>nRMSE/Pstc</span><b>${fmt(r.NRMSE_Pstc_pct, 2)} %</b></div></div>`; }).join("")}</div>
    <p class="notes">Percentuais normalizados pela potência média observada na interseção (${fmt(run.metrics_energy[0].P_obs_media_W, 1)} W); nRMSE/Pstc usa a potência STC. N = ${fint(run.metrics_energy[0].N)} · ${fint(run.metrics_energy[0].pares_validos)} pares válidos · ${fmt(run.metrics_energy[0].horas_cobertas_h, 1)} h · energia observada ${fmt(run.metrics_energy[0].E_obs_kWh, 1)} kWh (parcial).</p>
    ${card(hd("Potência medida, prevista e irradiância", "Escolha o intervalo; a irradiância no eixo direito ajuda a separar erro de modelo de erro de medição.",
      `<div class="toolbar"><select class="in" id="d0" style="width:150px"></select><select class="in" id="d1" style="width:150px"></select>
      <label class="switch sunny"><input type="checkbox" id="eg" ${R.ov.g ? "checked" : ""}> Irradiância</label><label class="switch"><input type="checkbox" id="ea" ${R.ov.anom ? "checked" : ""}> Anomalias</label><label class="switch"><input type="checkbox" id="et" ${R.ov.t ? "checked" : ""}> Tcell</label></div>`) + `<div id="eser" style="height:460px"></div>`, "mt")}
    <div class="grid g2 mt">${card(hd("Energia acumulada", "Somente pares válidos, mesma máscara para todos") + `<div id="ecum" style="height:320px"></div>`)}${card(hd("nRMSE por mês", "% da potência média observada no mês") + `<div id="emon" style="height:320px"></div>`)}</div>
    <div class="grid g2 mt">${card(hd("Viés por faixa de irradiância", "MBE [W] — positivo = sobrestima") + `<div id="ebg" style="height:300px"></div>`)}${card(hd("Viés por faixa de temperatura do módulo", "MBE [W]") + `<div id="ebt" style="height:300px"></div>`)}</div>
    ${card(hd("Previsto × medido", "Amostra de 3.000 pontos; losangos vermelhos/laranja = anomalias físicas de medição") + `<div id="esc" style="height:330px"></div>`, "mt")}
    <div class="sec-title"><h2>Qualidade dos dados e seu peso no erro</h2><span>o dataset também erra — e erra igual para os quatro modelos</span></div>
    ${discussion(nar, "qualidade")}
    <div class="grid g2 mt">${card(hd("nRMSE por cenário de qualidade", "Mesmas amostras para os 4 modelos em cada cenário") + `<div id="eqs" style="height:340px"></div>`)}${card(hd("Parcela do erro quadrático", "Fração do erro total explicada pelas amostras de cada cenário") + `<div id="eqp" style="height:340px"></div>`)}</div>
    <div class="mt">${table(run.anomaly_summary || [], [{ h: "Código", k: "codigo" }, { h: "Anomalia", k: "anomalia" }, { h: "Severidade", k: "severidade" }, { h: "Regra", k: "regra" }, { h: "Na máscara", k: "n_elegiveis", r: 1, f: fint }, { h: "% máscara", k: "pct_elegiveis", r: 1, f: (v) => fmt(v, 2) }, { h: "Em todo o conjunto", k: "n_todas", r: 1, f: fint }])}</div>`;
  META.models.forEach((m) => countUp($(`#mc${m.id}`), me[m.id].NRMSE_media_pct, (v) => `${fmt(v, 2)}<em>%</em>`));
  const days = run.days, d0 = $("#d0"), d1 = $("#d1");
  const opts = days.map((d) => `<option value="${d}">${new Date(d + "T12:00").toLocaleDateString("pt-BR")}</option>`).join("");
  d0.innerHTML = opts; d1.innerHTML = opts;
  const def = R.range || [days.includes("2019-05-13") ? "2019-05-13" : days[0], days.includes("2019-05-15") ? "2019-05-15" : days[Math.min(2, days.length - 1)]];
  d0.value = def[0]; d1.value = def[1];
  const load = async () => { if (d1.value < d0.value) d1.value = d0.value; R.range = [d0.value, d1.value]; R.series = await api(`/api/runs/${R.id}/series?start=${d0.value}&end=${d1.value}`); drawSeries(); };
  d0.onchange = load; d1.onchange = load;
  $("#eg").onchange = (e) => { R.ov.g = e.target.checked; drawSeries(); }; $("#ea").onchange = (e) => { R.ov.anom = e.target.checked; drawSeries(); }; $("#et").onchange = (e) => { R.ov.t = e.target.checked; drawSeries(); };
  load();
  // energia acumulada (dias)
  const daily = run.metrics_daily.filter((r) => r.modelo === "M1").sort((a, b) => (a.dia < b.dia ? -1 : 1));
  const cum = (key, rows) => { let s = 0; return rows.map((r) => (s += r[key])); };
  plot($("#ecum"), [{ x: daily.map((r) => r.dia), y: cum("E_obs_kWh", daily), name: "Medida", line: { color: "#13202D", width: 2.6 } },
    ...META.models.map((m) => { const rows = run.metrics_daily.filter((r) => r.modelo === m.id).sort((a, b) => (a.dia < b.dia ? -1 : 1)); return { x: rows.map((r) => r.dia), y: cum("E_prev_kWh", rows), name: m.id, line: { color: m.color, width: 1.5 } }; })],
    { hovermode: "x unified", yaxis: { title: { text: "kWh (pares válidos)" } } });
  const mon = run.metrics_monthly;
  plot($("#emon"), META.models.map((m) => ({ type: "bar", name: m.id, x: mon.filter((r) => r.modelo === m.id).map((r) => r.mes), y: mon.filter((r) => r.modelo === m.id).map((r) => r.NRMSE_media_pct), marker: { color: m.color } })),
    { barmode: "group", yaxis: { title: { text: "nRMSE [%]" } } });
  const bins = run.residual_bins;
  for (const [id, pre] of [["#ebg", "G"], ["#ebt", "T"]]) plot($(id), META.models.map((m) => { const r = bins.filter((b) => b.modelo === m.id && b.variavel.startsWith(pre)); return { type: "bar", name: m.id, x: r.map((b) => b.faixa), y: r.map((b) => b.MBE_W), marker: { color: m.color } }; }),
    { barmode: "group", yaxis: { title: { text: "MBE [W]" }, zeroline: true, zerolinecolor: "#8A99A7" } });
  const sc = run.scatter, mx = Math.max(...sc.obs) * 1.05;
  plot($("#esc"), [...META.models.map((m) => ({ type: "scattergl", mode: "markers", name: m.id, x: sc.obs, y: sc[m.id], marker: { size: 3, color: m.color, opacity: 0.35 }, hoverinfo: "skip" })),
    { type: "scattergl", mode: "markers", name: "anomalia (M4)", x: sc.obs.filter((_, i) => sc.sev[i] === "erro" || sc.sev[i] === "suspeito"), y: sc.M4.filter((_, i) => sc.sev[i] === "erro" || sc.sev[i] === "suspeito"), marker: { size: 6, symbol: "diamond", color: sc.sev.filter((s) => s === "erro" || s === "suspeito").map((s) => SEV[s]) } },
    { x: [0, mx], y: [0, mx], mode: "lines", line: { color: "#8A99A7", width: 1 }, showlegend: false, hoverinfo: "skip" }],
    { xaxis: { title: { text: "Medida [W]" }, range: [0, mx] }, yaxis: { title: { text: "Prevista [W]" }, range: [0, mx] } });
  const qsv = run.quality_sensitivity || []; const scen = [...new Set(qsv.map((r) => r.cenario))];
  const lab = Object.fromEntries(qsv.map((r) => [r.cenario, `${r.descricao.replace("somente ", "").replace(" (máscara principal)", "")}<br>${fmt(r.pct_amostras, 1)} % amostras`]));
  plot($("#eqs"), META.models.map((m) => ({ type: "bar", name: m.id, y: scen.map((s) => lab[s]), x: scen.map((s) => qsv.find((r) => r.cenario === s && r.modelo === m.id)?.NRMSE_media_pct), orientation: "h", marker: { color: m.color } })),
    { barmode: "group", margin: { l: 230 }, xaxis: { title: { text: "nRMSE [%]" } }, yaxis: { autorange: "reversed", tickfont: { size: 11 } } });
  const sp = scen.filter((s) => s !== "todas");
  plot($("#eqp"), META.models.map((m) => ({ type: "bar", name: m.id, y: sp.map((s) => lab[s]), x: sp.map((s) => qsv.find((r) => r.cenario === s && r.modelo === m.id)?.parcela_erro_quadratico_pct), orientation: "h", marker: { color: m.color } })),
    { barmode: "group", margin: { l: 230 }, xaxis: { title: { text: "% do erro quadrático total" }, range: [0, 100] }, yaxis: { autorange: "reversed", tickfont: { size: 11 } } });
}
function drawSeries() {
  const s = R.series; if (!s) return;
  const ts = s.map((r) => r.timestamp), tr = [];
  if (R.ov.g) tr.push(...fillSegments(ts, s.map((r) => r.g_poa_Wm2), 7.5, { name: "Gpoa", yaxis: "y2", fill: "tozeroy", fillcolor: "rgba(242,169,0,.13)", line: { color: "rgba(242,169,0,.9)", width: 1 }, hovertemplate: "%{y:.0f} W/m²<extra>Gpoa</extra>" }));
  if (R.ov.t) { const [x, y] = gapped(ts, s.map((r) => r.t_cell_C), 7.5); tr.push({ x, y, name: "Tcell", yaxis: R.ov.g ? "y3" : "y2", line: { color: "#B83A3A", width: 1.1, dash: "dot" }, hovertemplate: "%{y:.1f} °C<extra>Tcell</extra>" }); }
  const [xo, yo] = gapped(ts, s.map((r) => r.P_obs_W), 7.5);
  tr.push({ x: xo, y: yo, name: "Medida", line: { color: "#13202D", width: 2.4 }, hovertemplate: "%{y:.1f} W<extra>medida</extra>" });
  for (const m of META.models) { const [x, y] = gapped(ts, s.map((r) => r[`P_${m.id}_W`]), 7.5); tr.push({ x, y, name: m.id, line: { color: m.color, width: 1.3 }, hovertemplate: "%{y:.1f} W<extra>" + m.id + "</extra>" }); }
  if (R.ov.anom) { const a = s.filter((r) => r.anom_severidade === "erro" || r.anom_severidade === "suspeito");
    tr.push({ x: a.map((r) => r.timestamp), y: a.map((r) => r.P_obs_W), mode: "markers", name: "anomalia de medição", marker: { symbol: "diamond", size: 10, color: a.map((r) => SEV[r.anom_severidade]), line: { color: "#fff", width: 1 } },
      text: a.map((r) => r.anom_codes.split(";").map((c) => `${c} ${META.anomalies[c]?.[1] || ""}`).join("<br>")), hovertemplate: "%{text}<extra></extra>" }); }
  const both = R.ov.g && R.ov.t;
  plot($("#eser"), tr, { hovermode: "x unified", margin: { r: both ? 110 : 64 }, xaxis: { domain: [0, both ? 0.9 : 1], rangeslider: { visible: true, thickness: 0.05 } }, yaxis: { title: { text: "Potência [W]" }, rangemode: "tozero" },
    yaxis2: { title: { text: R.ov.g ? "Gpoa [W/m²]" : "Tcell [°C]" }, overlaying: "y", side: "right", rangemode: "tozero", showgrid: false }, yaxis3: { title: { text: "Tcell [°C]" }, overlaying: "y", side: "right", anchor: "free", position: 1, showgrid: false } }, "serie_potencia");
}

function tabComp(el, run) {
  const s = run.benchmark_summary, N = Math.max(...s.map((r) => r.batch_size)), sm = byM(s.filter((r) => r.batch_size === N));
  const main = run.benchmark_runs.filter((r) => r.experimento === "principal"), st = run.metadata?.tempos_por_etapa_s || {}, env = run.metadata?.ambiente_benchmark_isolado || {};
  el.innerHTML = `${discussion(run.narrative || [], "computacional")}
    <div class="grid g4 mt">${META.models.map((m) => { const r = sm[m.id]; return `<div class="mcard" style="--c:${m.color}">${mtag(m.id)}<div class="big">${fsmart(r.mediana_por_amostra_us)}<em>µs/amostra</em></div>
      <div class="lines"><span>Mediana do lote</span><b>${fsmart(r.mediana_s, "s")}</b><span>p95</span><b>${fsmart(r.p95_s, "s")}</b><span>CV</span><b>${fmt(r.cv_pct, 1)} %</b><span>Pico ΔRSS</span><b>${fmt(r.mediana_pico_rss_delta_MiB, 2)} MiB</b><span>Falhas</span><b>${r.n_falhas}</b></div></div>`; }).join("")}</div>
    <div class="grid g2 mt">${card(hd("Tempo por amostra", `Todas as ${main.length} execuções medidas (escala log)`) + `<div id="cbox" style="height:320px"></div>`)}${card(hd("Estabilidade entre rodadas", "compute_s ÷ mediana do modelo; hover mostra a posição na rodada") + `<div id="crnd" style="height:320px"></div>`)}</div>
    <div class="grid g2 mt">${card(hd("Escalabilidade", "Custo por amostra × tamanho do lote") + `<div id="cscl" style="height:320px"></div>`)}${card(hd("Memória residente", `pico − RSS antes · método ${esc(main[0]?.metodo_memoria || "")}`) + `<div id="cmem" style="height:320px"></div>`)}</div>
    <div class="grid g2 mt">${card(hd("Tempos fora do benchmark", "Não compõem o custo por amostra") + table(Object.entries(st).map(([k, v]) => ({ k, v })), [{ h: "Etapa", k: "k" }, { h: "Segundos", k: "v", r: 1, f: (v) => fmt(v, 2) }]))}
      ${card(hd("Ambiente isolado do benchmark") + `<table class="spec">${[["CPU", env.cpu_modelo], ["Núcleos lógicos", env.cpu_logicos], ["RAM", env.ram_total_GiB + " GiB"], ["SO", env.so], ["Python", env.python], ["NumPy / SciPy", `${env.versao_numpy} / ${env.versao_scipy}`], ["Threads BLAS", Object.values(env.threads_env || {}).join(", ")], ["Relógio", env.relogio?.funcao], ["Temperatura CPU", typeof env.cpu_temperatura === "string" ? env.cpu_temperatura : "medida"], ["Energia da CPU", env.energia_cpu]].map(([a, b]) => `<tr><td>${a}</td><td>${esc(b)}</td></tr>`).join("")}</table>`)}</div>
    <div class="mt">${table(s, [{ h: "Lote", k: "batch_size", r: 1, f: fint }, { h: "Modelo", k: "modelo" }, { h: "Mediana [s]", k: "mediana_s", r: 1, f: (v) => fsmart(v) }, { h: "µs/amostra", k: "mediana_por_amostra_us", r: 1, f: (v) => fsmart(v) }, { h: "Média [s]", k: "media_s", r: 1, f: (v) => fsmart(v) }, { h: "DP [s]", k: "dp_s_ddof1", r: 1, f: (v) => fsmart(v) }, { h: "CV %", k: "cv_pct", r: 1, f: (v) => fmt(v, 1) }, { h: "p5", k: "p5_s", r: 1, f: (v) => fsmart(v) }, { h: "p95", k: "p95_s", r: 1, f: (v) => fsmart(v) }, { h: "IC95 mediana", k: "ic95_mediana_lo_s", r: 1, f: (v, r) => `${fsmart(v)}–${fsmart(r.ic95_mediana_hi_s)}` }, { h: "ρ rodadas", k: "tendencia_spearman_rho", r: 1, f: (v) => fmt(v, 2) }])}</div>
    <div class="mt">${table(run.determinism || [], [{ h: "Lote", k: "batch_size", r: 1, f: fint }, { h: "Modelo", k: "modelo" }, { h: "Rodadas", k: "rodadas", r: 1 }, { h: "Hashes distintos", k: "hashes_distintos", r: 1 }, { h: "Máx |Δ| vs referência [W]", k: "max_abs_diff_ref_W", r: 1, f: (v) => fmt(v, 3) }])}</div>`;
  plot($("#cbox"), META.models.map((m) => ({ type: "box", name: m.id, y: main.filter((r) => r.modelo === m.id).map((r) => r.tempo_por_amostra_us), marker: { color: m.color }, boxpoints: "all", jitter: 0.5, pointpos: 0 })), { showlegend: false, yaxis: { type: "log", title: { text: "µs por amostra" } } });
  plot($("#crnd"), META.models.map((m) => { const r = main.filter((x) => x.modelo === m.id).sort((a, b) => a.rodada - b.rodada); const med = r.map((x) => x.compute_s).sort((a, b) => a - b)[Math.floor(r.length / 2)];
    return { x: r.map((x) => x.rodada), y: r.map((x) => x.compute_s / med), name: m.id, mode: "lines+markers", line: { color: m.color }, text: r.map((x) => `posição ${x.posicao}`), hovertemplate: "rodada %{x} · %{text} · %{y:.2f}<extra>" + m.id + "</extra>" }; }),
    { xaxis: { title: { text: "Rodada" }, dtick: 1 }, yaxis: { title: { text: "÷ mediana" } } });
  plot($("#cscl"), META.models.map((m) => { const r = s.filter((x) => x.modelo === m.id).sort((a, b) => a.batch_size - b.batch_size); return { x: r.map((x) => x.batch_size), y: r.map((x) => x.mediana_por_amostra_us), name: m.id, mode: "lines+markers", line: { color: m.color } }; }),
    { xaxis: { type: "log", title: { text: "Amostras no lote" } }, yaxis: { type: "log", title: { text: "µs por amostra" } } });
  plot($("#cmem"), META.models.map((m) => ({ type: "box", name: m.id, y: main.filter((r) => r.modelo === m.id).map((r) => r.pico_rss_delta_MiB), marker: { color: m.color }, boxpoints: "all", pointpos: 0 })), { showlegend: false, yaxis: { title: { text: "MiB" } } });
}

function tabInteg(el, run) {
  const pt = (run.pareto || []).filter((r) => r.eixo === "tempo"), pm = (run.pareto || []).filter((r) => r.eixo === "memoria");
  const me = byM(run.metrics_energy), cal = run.calibration;
  el.innerHTML = `${discussion(run.narrative || [], "integrada")}
    <div class="grid g2 mt">${card(hd("Erro × custo de tempo", "nRMSE vs mediana por amostra; contorno = não dominado; barras = IC95 por dias") + `<div id="ipt" style="height:380px"></div>`)}${card(hd("Erro × memória", "nRMSE vs mediana do pico ΔRSS") + `<div id="ipm" style="height:380px"></div>`)}</div>
    <div class="grid g2 mt">${card(hd("Sensibilidade à hipótese térmica", "ΔT célula–módulo (afeta M2 e M4)") + `<div id="isdt" style="height:300px"></div>`)}${card(hd("Sensibilidade ao limiar de irradiância", "A máscara é reconstruída com cada limiar") + `<div id="isg" style="height:300px"></div>`)}</div>
    <div class="mt">${table(run.marginal || [], [{ h: "Modelo", k: "modelo" }, { h: "Referência", k: "referencia" }, { h: "Tipo", k: "tipo" }, { h: "Eixo de custo", k: "eixo_custo" }, { h: "ΔRMSE [W]", k: "delta_erro", r: 1, f: (v) => fmt(v, 3, { sign: true }) }, { h: "Melhoria relativa", k: "melhoria_relativa_pct", r: 1, f: (v) => fmt(v, 2, { sign: true }) + " %" }, { h: "Fator de custo", k: "fator_custo", r: 1, f: (v) => (v ? factor(v) : "—") }])}</div>
    ${card(hd("O que cada modelo exige", "Assimetria de parametrização declarada") + table(META.models.map((m) => ({ ...m, nrmse: me[m.id].NRMSE_media_pct })), [{ h: "Modelo", k: "id", f: (v) => mtag(v) }, { h: "Equação", k: "equation" }, { h: "Entradas", k: "requirements" }, { h: "Temperatura", k: "temperature" }, { h: "nRMSE", k: "nrmse", r: 1, f: (v) => fmt(v, 2) + " %" }]) +
      `<p class="notes">SDM calibrado com 66 medições de laboratório · condição do Jacobiano ${fint(cal.condition)} · STC previsto ${fmt(cal.stc.Pmp_prev_W, 1)} W vs ${fmt(cal.stc.Pmp_med_W, 1)} W medido. ${cal.implied ? "Coeficientes implícitos: " + Object.entries(cal.implied).map(([k, v]) => `${k.split("_")[0]} ${fmt(v.modelo_pct_C, 3)} vs ${fmt(v.medido_pct_C, 3)} %/°C`).join(" · ") : ""}</p>`, "mt")}`;
  const nr = (m) => me[m].NRMSE_media_pct, scale = (m) => me[m].NRMSE_media_pct / me[m].RMSE_W;
  const par = (el2, rows, xcol, xt, log) => { const f = rows.filter((r) => r.nao_dominado).sort((a, b) => a[xcol] - b[xcol]);
    plot($(el2), [{ x: f.map((r) => r[xcol]), y: f.map((r) => nr(r.modelo)), mode: "lines", line: { color: "#13202D", dash: "dot", width: 1 }, showlegend: false, hoverinfo: "skip" },
      ...rows.map((r) => ({ x: [r[xcol]], y: [nr(r.modelo)], mode: "markers+text", text: [r.modelo], textposition: "top right", name: r.modelo, showlegend: false,
        error_y: r.RMSE_lo != null ? { type: "data", symmetric: false, array: [(r.RMSE_hi - r.RMSE_W) * scale(r.modelo)], arrayminus: [(r.RMSE_W - r.RMSE_lo) * scale(r.modelo)], color: "#8A99A7", thickness: 1 } : undefined,
        marker: { size: r.nao_dominado ? 18 : 12, color: META.colors[r.modelo], line: { color: "#13202D", width: r.nao_dominado ? 2 : 0 } },
        hovertemplate: `${r.modelo}<br>${xt}: %{x:.4g}<br>nRMSE %{y:.2f} %<br>${r.nao_dominado ? "não dominado" : "dominado por " + r.dominado_por}<extra></extra>` }))],
      { xaxis: { type: log ? "log" : "linear", title: { text: xt } }, yaxis: { title: { text: "nRMSE [%]" } } }); };
  par("#ipt", pt, "tempo_us_amostra", "µs por amostra (log)", true); par("#ipm", pm, "memoria_MiB", "Pico ΔRSS [MiB]", false);
  const sens = run.sensitivity || [];
  for (const [id, tipo, xt] of [["#isdt", "delta_T_C", "ΔT [°C]"], ["#isg", "limiar_G_Wm2", "Limiar Gpoa [W/m²]"]])
    plot($(id), META.models.map((m) => { const r = sens.filter((x) => x.tipo === tipo && x.modelo === m.id).sort((a, b) => a.valor - b.valor); return { x: r.map((x) => x.valor), y: r.map((x) => x.NRMSE_media_pct ?? x.RMSE_W * scale(m.id)), name: m.id, mode: "lines+markers", line: { color: m.color } }; }),
      { xaxis: { title: { text: xt } }, yaxis: { title: { text: "nRMSE [%]" } } });
}

function tabStat(el, run) {
  const ci = run.bootstrap_ci || [], pr = run.bootstrap_paired || [];
  const b0 = ci[0] || {};
  el.innerHTML = `${discussion(run.narrative || [], "estatistica")}
    <div class="grid g2 mt">${card(hd("IC95 por modelo", `Bootstrap em blocos de ${b0.dias} dias · B = ${fint(b0.B)}`) + `<div id="sci" style="height:300px"></div>`)}
      ${card(hd("Diferenças pareadas de nRMSE", "Mesmos dias para os dois modelos; faixa = limiar prático ±0,5 p.p.") + `<div id="spr" style="height:300px"></div>`)}</div>
    <div class="grid g2 mt">${card(hd("Distribuição dos resíduos", "previsto − medido [W]") + `<div id="shist" style="height:300px"></div>`)}${card(hd("nRMSE diário", "Cada ponto é um dia (unidade do bootstrap)") + `<div id="sday" style="height:300px"></div>`)}</div>
    <div class="mt">${table(ci.filter((r) => /pct/.test(r.metrica)), [{ h: "Modelo", k: "modelo" }, { h: "Métrica", k: "metrica" }, { h: "Estimativa", k: "estimativa", r: 1, f: (v) => fmt(v, 3) }, { h: "IC95 inf.", k: "ic95_lo", r: 1, f: (v) => fmt(v, 3) }, { h: "IC95 sup.", k: "ic95_hi", r: 1, f: (v) => fmt(v, 3) }])}</div>
    <div class="mt">${table(pr.filter((r) => r.metrica === "nRMSE_pct"), [{ h: "Comparação", k: "comparacao" }, { h: "Δ nRMSE [p.p.]", k: "diferenca", r: 1, f: (v) => fmt(v, 3, { sign: true }) }, { h: "IC95", k: "ic95_lo", r: 1, f: (v, r) => `[${fmt(v, 3)}; ${fmt(r.ic95_hi, 3)}]` }, { h: "Fração bootstrap < 0", k: "frac_boot_negativa", r: 1, f: (v) => fmt(100 * v, 1) + " %" }])}</div>`;
  const c = ci.filter((r) => r.metrica === "nRMSE_pct");
  plot($("#sci"), c.map((r) => ({ x: [r.estimativa], y: [r.modelo], mode: "markers", marker: { size: 13, color: META.colors[r.modelo] }, showlegend: false, error_x: { type: "data", symmetric: false, array: [r.ic95_hi - r.estimativa], arrayminus: [r.estimativa - r.ic95_lo], color: "#5E6E7E", thickness: 1.5 }, hovertemplate: `${r.modelo}: %{x:.2f} % [${fmt(r.ic95_lo, 2)}; ${fmt(r.ic95_hi, 2)}]<extra></extra>` })),
    { xaxis: { title: { text: "nRMSE [%]" } }, yaxis: { autorange: "reversed" } });
  const p = pr.filter((r) => r.metrica === "nRMSE_pct");
  plot($("#spr"), [{ x: p.map((r) => r.diferenca), y: p.map((r) => r.comparacao), mode: "markers", marker: { size: 11, color: p.map((r) => (r.ic95_lo > 0 || r.ic95_hi < 0 ? "#13202D" : "#8A99A7")) },
    error_x: { type: "data", symmetric: false, array: p.map((r) => r.ic95_hi - r.diferenca), arrayminus: p.map((r) => r.diferenca - r.ic95_lo), color: "#5E6E7E" }, hovertemplate: "%{y}: %{x:.3f} p.p.<extra></extra>" }],
    { margin: { l: 80 }, xaxis: { title: { text: "Δ nRMSE [p.p.] (negativo = primeiro modelo melhor)" }, zeroline: true, zerolinecolor: "#13202D" }, yaxis: { autorange: "reversed" },
      shapes: [{ type: "rect", xref: "x", yref: "paper", x0: -0.5, x1: 0.5, y0: 0, y1: 1, fillcolor: "rgba(242,169,0,.10)", line: { width: 0 } }] });
  const h = run.residual_hist, mids = h.edges.slice(0, -1).map((e, i) => (e + h.edges[i + 1]) / 2);
  plot($("#shist"), META.models.map((m) => ({ x: mids, y: h[m.id], name: m.id, mode: "lines", line: { color: m.color, width: 1.6, shape: "hvh" } })), { xaxis: { title: { text: "Resíduo [W]" } }, yaxis: { title: { text: "amostras" } } });
  plot($("#sday"), META.models.map((m) => ({ type: "box", name: m.id, y: run.metrics_daily.filter((r) => r.modelo === m.id).map((r) => r.NRMSE_media_pct), marker: { color: m.color }, boxpoints: "all", jitter: 0.5, pointpos: 0 })), { showlegend: false, yaxis: { title: { text: "nRMSE diário [%]" } } });
}

// =================================================================== HISTÓRICO
export async function historico(el) {
  const runs = await api("/api/runs");
  el.innerHTML = `<div class="page"><p class="lede">Cada execução é imutável. Reabrir não recalcula modelos; uma mudança de critério gera uma nova execução.</p>
    <div class="card">${runs.length ? runs.map((r) => `<div class="runcard" data-id="${r.run_id}"><span class="st" style="background:${{ concluido: "var(--ok)", executando: "var(--sun)", falhou: "var(--bad)", interrompido: "var(--faint)" }[r.estado] || "var(--faint)"}"></span>
      <div><b>${esc(r.rotulo || r.run_id)}</b> <small>${r.run_id} · ${esc(r.estado)}</small><div class="vals"><small>${r.meses} mês(es) · ${r.rodadas} rodadas · ${esc(r.ordem)} · ΔT ${r.delta_T} °C · G ≥ ${r.limiar_G}</small>
      ${META.models.map((m) => (r[`RMSE_${m.id}_W`] != null ? `<small>${m.id} RMSE ${fmt(r[`RMSE_${m.id}_W`], 2)} W</small>` : "")).join("")}</div></div>
      <div class="row" style="flex:none"><label class="switch"><input type="checkbox" class="cmp" value="${r.run_id}"> comparar</label><a class="btn" href="/api/runs/${r.run_id}/zip" onclick="event.stopPropagation()">${icon.dl} ZIP</a></div></div>`).join("") : `<div class="empty">Nenhuma execução.</div>`}</div>
    <div id="hcmp" class="mt"></div>
    <div class="sec-title"><h2>Importar execução exportada</h2></div>
    <label class="drop card" id="hdrop"><input type="file" accept=".zip" id="hfile" hidden><b>Solte um ZIP de execução</b><br>ela será reaberta sem rodar modelos</label></div>`;
  $$(".runcard").forEach((c) => (c.onclick = (e) => { if (e.target.closest("label,a")) return; location.hash = `#/artigo/resultados/${c.dataset.id}`; }));
  $$(".cmp").forEach((x) => (x.onchange = async () => {
    const ids = $$(".cmp").filter((y) => y.checked).map((y) => y.value);
    if (ids.length < 2) { $("#hcmp").innerHTML = ""; return; }
    const data = await Promise.all(ids.map((i) => api(`/api/runs/${i}`)));
    const rows = data.flatMap((d) => (d.metrics_energy || []).map((m) => ({ run: d.run_id, ...m })));
    $("#hcmp").innerHTML = `<h3 style="margin-bottom:8px">Comparação sem recalcular</h3>` + table(rows, [{ h: "Execução", k: "run" }, { h: "Modelo", k: "modelo" }, { h: "N", k: "N", r: 1, f: fint }, { h: "nRMSE %", k: "NRMSE_media_pct", r: 1, f: (v) => fmt(v, 2) }, { h: "nMBE %", k: "NMBE_media_pct", r: 1, f: (v) => fmt(v, 2, { sign: true }) }, { h: "Erro energia %", k: "erro_energia_pct", r: 1, f: (v) => fmt(v, 2, { sign: true }) }]);
  }));
  const up = async (f) => { try { const r = await api("/api/runs/import", { body: await f.arrayBuffer(), raw: true }); toast(`Importada: ${r.run_id}`); historico(el); } catch (e) { toast(e.message, true); } };
  $("#hfile").onchange = (e) => e.target.files[0] && up(e.target.files[0]);
  const dz = $("#hdrop"); dz.ondragover = (e) => { e.preventDefault(); dz.classList.add("over"); }; dz.ondragleave = () => dz.classList.remove("over"); dz.ondrop = (e) => { e.preventDefault(); dz.classList.remove("over"); e.dataTransfer.files[0] && up(e.dataTransfer.files[0]); };
}
