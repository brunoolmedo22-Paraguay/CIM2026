// Roteador, navegação e monitor global de execução.
import { $, $$, api, META, toast, esc } from "./ui.js";
import * as modelos from "./modelos.js";
import * as artigo from "./artigo.js";

const ROUTES = {
  simulador: { t: "Simulador", c: "Modo Modelos · quatro modelos sobre qualquer módulo, arranjo e clima", f: (el) => modelos.render(el) },
  dados: { t: "Dados e qualidade", c: "Artigo · conjunto SUPSI 2019 e laboratório IEC 61853", f: (el) => artigo.dados(el) },
  protocolo: { t: "Protocolo e execução", c: "Artigo · critérios congelados antes de observar erros", f: (el) => artigo.protocolo(el) },
  resultados: { t: "Resultados e discussão", c: "Artigo · energia, custo computacional, análise integrada e estatística", f: (el, id) => artigo.resultados(el, id) },
  historico: { t: "Histórico", c: "Artigo · execuções imutáveis, reabertas sem recalcular", f: (el) => artigo.historico(el) },
};
let current = null;

async function route() {
  const parts = (location.hash || "#/simulador").replace(/^#\//, "").split("/");
  const key = parts[0] === "artigo" ? parts[1] || "dados" : "simulador";
  const r = ROUTES[key] || ROUTES.simulador;
  $$("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.r === key));
  $("#title").textContent = r.t; $("#crumb").textContent = r.c;
  document.title = `${r.t} · CIM26`;
  current = key;
  const view = $("#view"); view.innerHTML = "";
  window.scrollTo({ top: 0 });
  try { await r.f(view, parts[2]); } catch (e) { console.error(e); view.innerHTML = `<div class="page"><div class="alert bad">${esc(e.message)}</div></div>`; }
}

let last = null, timer = null;
async function poll() {
  clearTimeout(timer);
  let a = null;
  try { a = await api("/api/runs/active"); } catch { /* servidor ocupado */ }
  window.__active = a;
  const pill = $("#runpill");
  if (a) {
    const p = artigo.progressOf(a.status || {});
    const ang = 2 * Math.PI * p, x = 11 + 8 * Math.sin(ang), y = 11 - 8 * Math.cos(ang);
    pill.innerHTML = `<svg class="mini" viewBox="0 0 22 22"><circle cx="11" cy="11" r="8" fill="none" stroke="#E7ECF1" stroke-width="3"/><path d="M11 3 A8 8 0 ${p > 0.5 ? 1 : 0} 1 ${x.toFixed(2)} ${y.toFixed(2)}" fill="none" stroke="#F2A900" stroke-width="3" stroke-linecap="round"/></svg><span><b>${Math.round(p * 100)} %</b> · ${esc(a.status?.etapa || "iniciando")}</span>`;
    pill.classList.add("show"); pill.onclick = () => (location.hash = "#/artigo/protocolo");
    if (current === "protocolo") artigo.heroUpdate(a);
  } else {
    pill.classList.remove("show");
    if (current === "protocolo") artigo.heroUpdate(null);
    if (last) { toast(`Experimento ${last} concluído.`); location.hash = `#/artigo/resultados/${last}`; }
  }
  last = a ? a.run_id : null;
  timer = setTimeout(poll, a ? 1200 : 4000);
}

(async function boot() {
  const m = await api("/api/meta");
  Object.assign(META, m);
  META.colors = Object.fromEntries(m.models.map((x) => [x.id, x.color]));
  $("#ver").textContent = `v${m.version}`;
  window.addEventListener("hashchange", route);
  window.addEventListener("pollnow", poll);
  await route();
  poll();
})();
