"""Componentes visuais do CIM26.

* Construtores HTML (``st.html``): apresentação pura, sem JavaScript.
* Componentes JavaScript (``st.components.v2``, mecanismo oficial e bidirecional):
  o JS só EMITE eventos (``setTriggerValue``); o Python é a única fonte de verdade e
  guarda o estado em ``st.session_state``. Nada aqui contém física.
Todos os dados passados aos componentes são gerados pelo próprio app (não por usuários)
e os textos são escapados antes de virar HTML.
"""

from __future__ import annotations

import html as _h
from typing import Iterable

import streamlit as st

from .theme import MODEL_COLORS, SEV_COLORS

esc = _h.escape


# ===========================================================================
# HTML (apresentação)
# ===========================================================================
def show(markup: str) -> None:
    st.html(markup)


def page_header(title: str, subtitle: str = "", right: str = "") -> None:
    show(f'<div class="cim-hd"><div><h1>{esc(title)}</h1><p>{subtitle}</p></div><div class="sp"></div><div class="ctx">{right}</div></div>')


def chip(kind: str, text: str) -> str:
    return f'<span class="cim-chip {kind}">{esc(text)}</span>'


def mtag(m: str, short: str = "") -> str:
    return f'<span class="cim-mtag"><i style="background:{MODEL_COLORS[m]}"></i>{m}{f" <span>{esc(short)}</span>" if short else ""}</span>'


def sec(title: str, sub: str = "") -> None:
    show(f'<div class="cim-sec"><h2>{esc(title)}</h2><span>{esc(sub)}</span></div>')


def strip(items: list[tuple[str, str]]) -> None:
    show('<div class="cim-strip">' + "".join(f"<div><small>{esc(k)}</small><b>{esc(str(v))}</b></div>" for k, v in items) + "</div>")


def synth(text: str) -> None:
    show(f'<div class="cim-synth"><h4>Síntese da discussão</h4><p>{esc(text)}</p></div>')


EV_LABEL = {"robusta": "evidência robusta", "indicativa": "evidência indicativa", "inconclusiva": "inconclusiva", "contexto": "contexto"}


def discussion(items: list[dict], section: str) -> None:
    it = [i for i in items if i.get("secao") == section]
    if not it:
        return
    cards = "".join(
        f'<article class="cim-dc {i["evidencia"]}" style="animation-delay:{k * 45}ms"><header><b>{esc(i["titulo"])}</b>'
        f'<span class="cim-ev {i["evidencia"]}">{EV_LABEL.get(i["evidencia"], i["evidencia"])}</span></header><p>{esc(i["texto"])}</p></article>'
        for k, i in enumerate(it))
    show(f'<div class="cim-disc">{cards}</div>')


def alert(text: str, kind: str = "") -> None:
    show(f'<div class="cim-alert {kind}">{text}</div>')


def notes(lines: Iterable[str]) -> None:
    show('<ul class="cim-notes">' + "".join(f"<li>{x}</li>" for x in lines) + "</ul>")


def spec_table(rows: list[tuple[str, str | None]]) -> str:
    return '<table class="cim-spec">' + "".join(
        f'<tr><td>{esc(k)}</td><td class="{"na" if v is None else ""}">{"não informado" if v is None else esc(str(v))}</td></tr>'
        for k, v in rows) + "</table>"


def card(inner: str) -> None:
    show(f'<div class="cim-card">{inner}</div>')


def anomaly_list(rows: list[dict]) -> None:
    mx = max([1] + [r["n_todas"] for r in rows])
    out = []
    for r in rows:
        kind = {"erro": "bad", "suspeito": "estimado"}.get(r["severidade"], "")
        out.append(f'<div class="cim-anom"><code>{r["codigo"]}</code><div><b>{esc(r["anomalia"])}</b> {chip(kind, r["severidade"])}</div>'
                   f'<div class="n">{r["n_elegiveis"]:,}<small>{r["pct_elegiveis"]:.2f} %</small></div>'
                   f'<div class="cim-bar"><i style="width:{100 * r["n_todas"] / mx:.1f}%;background:{SEV_COLORS.get(r["severidade"], "#7F92A4")}"></i></div>'
                   f'<div class="rule">{esc(r["regra"])} · {r["n_todas"]:,} em todo o conjunto</div></div>'.replace(",", "."))
    card('<h3>Inconsistências físicas no dataset</h3><div class="sub">Critérios fixados antes de olhar os erros dos modelos; '
         'usam só grandezas medidas. Número = amostras na máscara.</div>' + "".join(out))


def rank_html(r: dict) -> str:
    return f'<span class="rank" title="posição">{r["rank"]}</span>' if r.get("rank") else ""


def model_cards(rows: list[dict]) -> None:
    show('<div class="cim-mcards">' + "".join(
        f'<div class="cim-mcard" style="--c:{MODEL_COLORS[r["m"]]};animation-delay:{k * 60}ms"><div class="top">{mtag(r["m"], r["short"])}'
        f'{rank_html(r)}</div>'
        f'<div class="big">{r["big"]}<em>{esc(r["unit"])}</em></div><div class="ci">{esc(r["ci"])}</div>'
        f'<dl>{"".join(f"<dt>{esc(a)}</dt><dd>{esc(b)}</dd>" for a, b in r["lines"])}</dl></div>'
        for k, r in enumerate(rows)) + "</div>")


def array_grid(ns: int, npar: int) -> str:
    cols, rows = min(ns, 24), min(npar, 10)
    cells = "".join(f'<i style="animation-delay:{min(i, 40) * 12}ms"></i>' for i in range(cols * rows))
    return f'<div class="cim-arraygrid" style="grid-template-columns:repeat({cols},20px)">{cells}</div>'


# ===========================================================================
# Componentes JavaScript (st.components.v2)
# ===========================================================================
_FMT_JS = r"""
const fmt = (v, d) => (v === null || v === undefined || Number.isNaN(v)) ? "—" :
  new Intl.NumberFormat("pt-BR", {minimumFractionDigits: d, maximumFractionDigits: d}).format(v);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const host = (parent, cls) => { let el = parent.querySelector("." + cls); if (!el) { el = document.createElement("div"); el.className = cls; parent.appendChild(el); } return el; };
"""

_THEME_SYNC = st.components.v2.component(
    "cim_theme_sync",
    js=r"""
export default function () {
  const apply = () => {
    const m = getComputedStyle(document.body).backgroundColor.match(/\d+(\.\d+)?/g);
    if (!m) return;
    const [r, g, b] = m.map(Number);
    document.documentElement.dataset.cimTheme = (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5 ? "dark" : "light";
  };
  apply();
  if (window.__cimThemeTimer) clearInterval(window.__cimThemeTimer);
  window.__cimThemeTimer = setInterval(apply, 700);
}
""")


def theme_sync() -> None:
    _THEME_SYNC(key="cim_theme_sync", height=0)


_TILES = st.components.v2.component(
    "cim_tiles",
    css=r"""
.t{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;font-family:inherit}
.t button{all:unset;box-sizing:border-box;position:relative;cursor:pointer;background:var(--cim-surface);border:1px solid var(--cim-line);border-radius:12px;padding:14px 16px 13px;
  box-shadow:var(--cim-shadow);transition:transform .2s cubic-bezier(.2,.8,.2,1),border-color .2s,box-shadow .2s;min-width:0}
.t button:hover{transform:translateY(-2px);border-color:var(--cim-primary-2);box-shadow:var(--cim-shadow-hover)}
.t button:focus-visible{outline:2px solid var(--cim-primary-2);outline-offset:2px}
.t small{display:block;font-size:12px;color:var(--cim-muted);font-weight:500}
.t b{display:block;font-size:17px;margin:5px 0 2px;color:var(--cim-ink);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-weight:600}
.t span{display:block;font-size:12.5px;color:var(--cim-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.t svg{position:absolute;right:12px;top:12px;color:var(--cim-faint);transition:color .2s}
.t button:hover svg{color:var(--cim-primary-2)}
@media (max-width:900px){.t{grid-template-columns:repeat(2,minmax(0,1fr))}}
""",
    js=_FMT_JS + r"""
export default function (c) {
  const { data, setTriggerValue, parentElement } = c;
  const el = host(parentElement, "t");
  el.innerHTML = (data.tiles || []).map((t) => `<button data-k="${esc(t.k)}" title="Editar ${esc(t.label)}"><small>${esc(t.label)}</small><b>${esc(t.title)}</b><span>${esc(t.sub)}</span>
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 20h4L19 9l-4-4L4 16z"/></svg></button>`).join("");
  el.querySelectorAll("button").forEach((b) => (b.onclick = () => setTriggerValue("open", b.dataset.k)));
}
""")


def config_tiles(tiles: list[dict], key: str) -> str | None:
    r = _TILES(key=key, data={"tiles": tiles}, on_open_change=lambda: None)
    return r.open


_PILLS = st.components.v2.component(
    "cim_model_pills",
    css=r"""
.p{display:flex;gap:10px;flex-wrap:wrap;align-items:center;font-family:inherit}
.p button{all:unset;--c:#3B82C4;display:inline-flex;align-items:center;gap:9px;padding:9px 15px 9px 11px;border-radius:999px;border:1.5px solid var(--cim-line);
  background:var(--cim-surface);cursor:pointer;font-weight:600;font-size:14px;color:var(--cim-ink);transition:all .2s cubic-bezier(.2,.8,.2,1)}
.p button i{width:12px;height:12px;border-radius:50%;border:2px solid var(--c);transition:background .2s,transform .2s}
.p button small{font-weight:500;color:var(--cim-muted);font-size:12.5px}
.p button:hover{border-color:var(--c)}
.p button.on{border-color:var(--c);background:color-mix(in srgb,var(--c) 12%,var(--cim-surface))}
.p button.on i{background:var(--c);transform:scale(1.1)}
.p button.na{opacity:.6;border-style:dashed}
.p .hint{font-size:12.5px;color:var(--cim-muted);margin-left:4px}
.r{font-size:12.5px;color:var(--cim-muted);margin-top:8px;line-height:1.6}
.r b{color:var(--cim-ink)}
""",
    js=_FMT_JS + r"""
export default function (c) {
  const { data, setTriggerValue, parentElement } = c;
  const el = host(parentElement, "p"), why = host(parentElement, "r");
  el.innerHTML = data.models.map((m) => `<button data-m="${m.id}" class="${m.on ? "on" : ""} ${m.available ? "" : "na"}" style="--c:${m.color}" title="${esc(m.reason)}"><i></i>${m.id} <small>${esc(m.short)}</small></button>`).join("")
    + `<span class="hint">${esc(data.hint || "")}</span>`;
  why.innerHTML = data.models.filter((m) => !m.available).map((m) => `<b>${m.id}</b> ${esc(m.reason)}`).join(" &nbsp;·&nbsp; ");
  el.querySelectorAll("button").forEach((b) => (b.onclick = () => {
    const m = data.models.find((x) => x.id === b.dataset.m);
    setTriggerValue(m.available ? "toggle" : "blocked", m.id);
  }));
}
""")


def model_pills(models: list[dict], key: str, hint: str = "") -> tuple[str | None, str | None]:
    r = _PILLS(key=key, data={"models": models, "hint": hint}, on_toggle_change=lambda: None, on_blocked_change=lambda: None)
    return r.toggle, r.blocked


_KPIS = st.components.v2.component(
    "cim_kpis",
    css=r"""
.k{display:grid;grid-template-columns:repeat(var(--n,4),minmax(0,1fr));gap:12px;font-family:inherit}
.k div{background:var(--cim-surface);border:1px solid var(--cim-line);border-top:3px solid var(--c,var(--cim-line));border-radius:12px;padding:13px 16px;box-shadow:var(--cim-shadow);min-width:0}
.k small{display:block;font-size:12px;color:var(--cim-muted);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.k b{display:block;font-size:26px;font-weight:600;letter-spacing:-.02em;margin-top:2px;color:var(--cim-ink);font-variant-numeric:tabular-nums}
.k b em{font-style:normal;font-size:14px;color:var(--cim-muted);font-weight:500;margin-left:4px}
.k span{font-size:12.5px;color:var(--cim-muted)}
@media (max-width:900px){.k{grid-template-columns:repeat(2,minmax(0,1fr))}}
""",
    js=_FMT_JS + r"""
export default function (c) {
  const { data, parentElement } = c;
  const el = host(parentElement, "k");
  const prev = parentElement.__prev || {};
  const items = data.items || [];
  el.style.setProperty("--n", items.length);
  el.innerHTML = items.map((it, i) => `<div style="--c:${it.color || "var(--cim-line)"}"><small>${esc(it.label)}</small><b data-i="${i}">—</b><span>${esc(it.sub || "")}</span></div>`).join("");
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  items.forEach((it, i) => {
    const b = el.querySelector(`b[data-i="${i}"]`);
    const to = it.value, from = prev[it.key] ?? (typeof to === "number" ? 0 : to);
    const paint = (v) => (b.innerHTML = (typeof v === "number" ? fmt(v, it.decimals ?? 2) : esc(v)) + (it.unit ? `<em>${esc(it.unit)}</em>` : ""));
    if (typeof to !== "number" || !Number.isFinite(to) || reduce) return paint(to ?? "—");
    const t0 = performance.now(), dur = 650;
    const step = (t) => { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3); paint(from + (to - from) * e); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  });
  parentElement.__prev = Object.fromEntries(items.map((it) => [it.key, it.value]));
}
""")


def kpis(items: list[dict], key: str) -> None:
    _KPIS(key=key, data={"items": items})


_CAL = st.components.v2.component(
    "cim_calendar",
    css=r"""
.c{font-family:inherit}
.g{display:grid;grid-template-columns:repeat(var(--m,6),minmax(0,1fr));gap:14px}
.mo b{font-size:12px;color:var(--cim-muted);font-weight:600;display:block;margin-bottom:6px;text-transform:capitalize}
.d7{display:grid;grid-template-columns:repeat(7,1fr);gap:3px}
.d{all:unset;aspect-ratio:1;border-radius:4px;cursor:pointer;transition:transform .12s cubic-bezier(.2,.8,.2,1),box-shadow .12s}
.d:hover{transform:scale(1.2);box-shadow:0 0 0 2px var(--cim-ink);z-index:2}
.d.sel{box-shadow:0 0 0 2px var(--cim-primary-2),0 0 0 4px var(--cim-surface)}
.d.pad{visibility:hidden;cursor:default}
.d.none{background:transparent;border:1px dashed var(--cim-line);box-sizing:border-box;cursor:default}
.lg{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--cim-muted);margin-top:12px;flex-wrap:wrap}
.lg i{width:12px;height:12px;border-radius:3px;display:inline-block}
@media (max-width:900px){.g{grid-template-columns:repeat(3,minmax(0,1fr))}}
""",
    js=_FMT_JS + r"""
export default function (c) {
  const { data, setTriggerValue, parentElement } = c;
  const el = host(parentElement, "c");
  const sel = new Set(data.selected || []);
  const mlabel = (mo) => new Date(mo + "-01T12:00").toLocaleDateString("pt-BR", { month: "long" });
  el.innerHTML = `<div class="g" style="--m:${data.months.length}">` + data.months.map((mo) => {
    const f = new Date(mo + "-01T12:00"), pad = (f.getDay() + 6) % 7, n = new Date(f.getFullYear(), f.getMonth() + 1, 0).getDate();
    let cells = "<i class='d pad'></i>".repeat(pad);
    for (let i = 1; i <= n; i++) {
      const k = `${mo}-${String(i).padStart(2, "0")}`, d = data.days[k];
      cells += d ? `<button class="d ${sel.has(k) ? "sel" : ""}" data-k="${k}" style="background:${d.c}" title="${esc(d.t)}"></button>` : `<i class="d none" title="sem dados"></i>`;
    }
    return `<div class="mo"><b>${mlabel(mo)}</b><div class="d7">${cells}</div></div>`;
  }).join("") + `</div><div class="lg">${data.legend || ""}</div>`;
  el.querySelectorAll("button.d").forEach((b) => (b.onclick = (e) => setTriggerValue("pick", { day: b.dataset.k, add: !!(data.multi && (e.ctrlKey || e.metaKey)) })));
}
""")


def calendar(months: list[str], days: dict, selected: list[str], key: str, multi: bool = False, legend: str = "") -> dict | None:
    r = _CAL(key=key, data={"months": months, "days": days, "selected": selected, "multi": multi, "legend": legend},
             on_pick_change=lambda: None)
    return r.pick


_ARC = st.components.v2.component(
    "cim_sun_arc",
    css=r"""
.w{display:grid;grid-template-columns:minmax(240px,400px) 1fr;gap:26px;align-items:center;font-family:inherit;color:var(--cim-ink)}
svg{width:100%;height:auto}
.arc{fill:none;stroke:var(--cim-line);stroke-width:2;stroke-dasharray:3 6}
.done{fill:none;stroke:#F2A900;stroke-width:3.2;stroke-linecap:round;transition:stroke-dashoffset .9s cubic-bezier(.2,.8,.2,1)}
.sun{transition:transform .9s cubic-bezier(.2,.8,.2,1)}
.glow{animation:g 2.4s ease-in-out infinite}
@keyframes g{50%{opacity:.3}}
h3{font-size:16px;margin:0 0 10px;font-weight:600}
ul{list-style:none;margin:0;padding:0;display:grid;gap:4px}
li{display:flex;align-items:center;gap:10px;font-size:13.5px;color:var(--cim-faint)}
li i{width:16px;height:16px;border-radius:50%;border:2px solid var(--cim-line);flex:none;box-sizing:border-box}
li.done{color:var(--cim-ink-3)} li.done i{background:var(--cim-ok);border-color:var(--cim-ok)}
li.cur{color:var(--cim-ink);font-weight:600} li.cur i{border-color:#F2A900;border-top-color:transparent;animation:s 1s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}
.bar{height:8px;border-radius:999px;background:var(--cim-line-2);overflow:hidden;margin-top:12px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,#F2A900,#FFC94D);border-radius:999px;transition:width .6s cubic-bezier(.2,.8,.2,1)}
.tk{font-size:13px;color:var(--cim-muted);margin-top:8px}
@media (max-width:800px){.w{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){.done,.sun,.bar i{transition:none}.glow,li.cur i{animation:none}}
""",
    js=_FMT_JS + r"""
export default function (c) {
  const { data, parentElement } = c;
  let el = parentElement.querySelector(".w");
  if (!el) {
    el = document.createElement("div"); el.className = "w"; parentElement.appendChild(el);
    el.innerHTML = `<svg viewBox="0 0 400 205"><path class="arc" d="M30 180 A170 170 0 0 1 370 180"/><path class="done" pathLength="100" stroke-dasharray="100" stroke-dashoffset="100" d="M30 180 A170 170 0 0 1 370 180"/>
      <line x1="10" y1="180" x2="390" y2="180" stroke="var(--cim-line)"/><g class="sun" transform="translate(30,180)"><circle class="glow" r="22" fill="rgba(242,169,0,.25)"/><circle r="11" fill="#F2A900"/></g>
      <text class="pct" x="200" y="172" text-anchor="middle" font-size="27" font-weight="600" fill="currentColor"></text><text class="rid" x="200" y="198" text-anchor="middle" font-size="11" fill="var(--cim-muted)"></text></svg>
      <div><h3></h3><ul></ul><div class="bar"><i></i></div><div class="tk"></div></div>`;
  }
  const p = Math.max(0, Math.min(1, data.p || 0)), th = Math.PI * (1 - p);
  requestAnimationFrame(() => {
    el.querySelector(".done").style.strokeDashoffset = 100 - 100 * p;
    el.querySelector(".sun").setAttribute("transform", `translate(${200 + 170 * Math.cos(th)},${180 - 170 * Math.sin(th)})`);
    el.querySelector(".bar i").style.width = `${100 * (data.bench || 0)}%`;
  });
  el.querySelector(".pct").textContent = `${Math.round(100 * p)} %`;
  el.querySelector(".rid").textContent = data.run || "";
  el.querySelector("h3").textContent = data.title || "";
  el.querySelector(".tk").innerHTML = esc(data.ticker || "");
  el.querySelector("ul").innerHTML = (data.stages || []).map((s, i) => `<li class="${i + 1 < data.idx ? "done" : i + 1 === data.idx ? "cur" : ""}"><i></i>${esc(s)}</li>`).join("");
}
""")


def sun_arc(p: float, idx: int, stages: list[str], title: str, ticker: str, run: str, bench: float, key: str) -> None:
    _ARC(key=key, data={"p": p, "idx": idx, "stages": stages, "title": title, "ticker": ticker, "run": run, "bench": bench})
