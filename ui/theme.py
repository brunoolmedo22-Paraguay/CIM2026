"""Sistema visual CIM26 (identidade da v1.1 portada para Streamlit).

* Cores base, fontes e barra lateral vêm de ``.streamlit/config.toml`` (mecanismo
  documentado: [theme.light], [theme.dark], [[theme.fontFaces]]).
* Este módulo injeta o CSS dos componentes próprios (classes ``cim-*``) e um pequeno
  bloco de ajustes de layout do Streamlit, isolado em ``ST_OVERRIDES``: se um seletor
  interno mudar numa versão futura, só a aparência é afetada, nunca a função.
* Tokens claro/escuro: o servidor escolhe pelo ``st.context.theme``; no navegador, o
  componente ``theme_sync`` confirma o tema real e ajusta ``<html data-cim-theme>``.
"""

from __future__ import annotations

import streamlit as st

MODEL_COLORS = {"M1": "#3B82C4", "M2": "#1E9E7A", "M3": "#C77700", "M4": "#B4507A"}
SUN = "#F2A900"
SEV_COLORS = {"erro": "#B83A3A", "suspeito": "#D98E04", "condicao": "#7F92A4"}

LIGHT = {
    "ink": "#13202D", "ink-2": "#22313F", "ink-3": "#33475A", "muted": "#5E6E7E", "faint": "#8A99A7",
    "line": "#D9E1E8", "line-2": "#E7ECF1", "bg": "#EDF1F4", "surface": "#FFFFFF", "surface-2": "#F6F8FA",
    "primary": "#1A5276", "primary-2": "#2471A3", "primary-soft": "#E6EFF6",
    "ok": "#1E7F5C", "ok-soft": "#E3F3EC", "warn": "#A86A12", "warn-soft": "#FBF0DC", "bad": "#B83A3A", "bad-soft": "#FBE7E7",
    "lab": "#5B3F8A", "lab-soft": "#EDE9F7", "synth": "#13202D", "synth-ink": "#E8EEF3",
    "shadow": "0 1px 2px rgba(19,32,45,.06),0 1px 1px rgba(19,32,45,.04)",
    "shadow-hover": "0 10px 26px -14px rgba(19,32,45,.38)",
}
DARK = {
    "ink": "#E3EAF1", "ink-2": "#C9D4DE", "ink-3": "#AFC0CF", "muted": "#8FA2B4", "faint": "#6B7F91",
    "line": "#2A3A4A", "line-2": "#22303D", "bg": "#0E161F", "surface": "#15202B", "surface-2": "#1B2835",
    "primary": "#5DADE2", "primary-2": "#7FC0EA", "primary-soft": "#173246",
    "ok": "#3FB98A", "ok-soft": "#12302A", "warn": "#E0A33A", "warn-soft": "#3A2C12", "bad": "#E06464", "bad-soft": "#3A1A1A",
    "lab": "#B9A3E6", "lab-soft": "#2A2240", "synth": "#0A1118", "synth-ink": "#E8EEF3",
    "shadow": "0 1px 2px rgba(0,0,0,.4)", "shadow-hover": "0 10px 26px -14px rgba(0,0,0,.7)",
}


def _vars(t: dict) -> str:
    return ";".join(f"--cim-{k}:{v}" for k, v in t.items())


COMPONENT_CSS = """
.cim-hd{display:flex;align-items:flex-end;gap:16px;margin:-6px 0 18px;padding-bottom:14px;border-bottom:1px solid var(--cim-line);animation:cimIn .35s cubic-bezier(.2,.8,.2,1)}
.cim-hd h1{font-size:1.75rem;font-weight:600;letter-spacing:-.015em;margin:0;line-height:1.15;color:var(--cim-ink)}
.cim-hd p{margin:4px 0 0;color:var(--cim-muted);font-size:.92rem;max-width:80ch}
.cim-hd .sp{flex:1}
.cim-hd .ctx{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}
@keyframes cimIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.cim-lede{color:var(--cim-muted);max-width:82ch;font-size:.95rem;margin:0 0 4px}
.cim-chip{display:inline-flex;align-items:center;gap:6px;padding:2px 10px;border-radius:999px;font-size:.76rem;font-weight:500;white-space:nowrap;
  background:var(--cim-surface-2);border:1px solid var(--cim-line);color:var(--cim-ink-3)}
.cim-chip.medido{background:var(--cim-ok-soft);color:var(--cim-ok);border-color:transparent}
.cim-chip.estimado,.cim-chip.hipotese{background:var(--cim-warn-soft);color:var(--cim-warn);border-color:transparent}
.cim-chip.simulado,.cim-chip.manual{background:var(--cim-primary-soft);color:var(--cim-primary);border-color:transparent}
.cim-chip.lab{background:var(--cim-lab-soft);color:var(--cim-lab);border-color:transparent}
.cim-chip.bad{background:var(--cim-bad-soft);color:var(--cim-bad);border-color:transparent}
.cim-mtag{display:inline-flex;align-items:center;gap:7px;font-weight:600;color:var(--cim-ink)}
.cim-mtag i{width:10px;height:10px;border-radius:3px;display:inline-block}
.cim-mtag span{font-weight:500;color:var(--cim-muted)}
.cim-card{background:var(--cim-surface);border:1px solid var(--cim-line);border-radius:12px;padding:16px 18px;box-shadow:var(--cim-shadow);color:var(--cim-ink)}
.cim-card h3{font-size:1rem;margin:0 0 2px;font-weight:600}
.cim-card .sub{color:var(--cim-muted);font-size:.83rem}
.cim-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));background:var(--cim-surface);border:1px solid var(--cim-line);border-radius:12px;overflow:hidden}
.cim-strip div{padding:10px 14px;border-right:1px solid var(--cim-line-2)}
.cim-strip div:last-child{border-right:0}
.cim-strip small{display:block;font-size:.72rem;color:var(--cim-muted)}
.cim-strip b{font-size:.9rem;font-weight:600;color:var(--cim-ink)}
.cim-synth{background:var(--cim-synth);color:var(--cim-synth-ink);border-radius:14px;padding:24px 30px;position:relative;overflow:hidden;border:1px solid var(--cim-line);animation:cimIn .45s cubic-bezier(.2,.8,.2,1)}
.cim-synth::after{content:"";position:absolute;right:-70px;top:-70px;width:240px;height:240px;border-radius:50%;background:radial-gradient(circle,rgba(242,169,0,.36),rgba(242,169,0,0) 70%)}
.cim-synth h4{font-size:.8rem;color:#FFC94D;font-weight:600;margin:0 0 8px;letter-spacing:.02em}
.cim-synth p{font-family:SerifCIM,Georgia,serif;font-size:1.18rem;line-height:1.55;margin:0;max-width:82ch;position:relative;z-index:1}
.cim-disc{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:14px;margin:4px 0 6px}
.cim-dc{background:var(--cim-surface);border:1px solid var(--cim-line);border-left:3px solid var(--ev,var(--cim-line));border-radius:10px;padding:14px 18px;animation:cimIn .4s both}
.cim-dc header{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.cim-dc header b{font-size:.86rem;color:var(--cim-ink)}
.cim-dc p{font-family:SerifCIM,Georgia,serif;font-size:1rem;line-height:1.6;margin:0;color:var(--cim-ink-2)}
.cim-ev{font-size:.68rem;font-weight:600;padding:2px 8px;border-radius:999px;margin-left:auto;white-space:nowrap}
.cim-ev.robusta{background:var(--cim-ok-soft);color:var(--cim-ok)} .cim-dc.robusta{--ev:var(--cim-ok)}
.cim-ev.indicativa{background:var(--cim-warn-soft);color:var(--cim-warn)} .cim-dc.indicativa{--ev:#F2A900}
.cim-ev.inconclusiva{background:var(--cim-surface-2);color:var(--cim-muted)} .cim-dc.inconclusiva{--ev:var(--cim-faint)}
.cim-ev.contexto{background:var(--cim-primary-soft);color:var(--cim-primary)} .cim-dc.contexto{--ev:#9FB6CA}
.cim-mcards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}
.cim-mcard{background:var(--cim-surface);border:1px solid var(--cim-line);border-top:3px solid var(--c);border-radius:12px;padding:14px 16px;box-shadow:var(--cim-shadow);animation:cimIn .4s both;transition:transform .2s,box-shadow .2s}
.cim-mcard:hover{transform:translateY(-2px);box-shadow:var(--cim-shadow-hover)}
.cim-mcard .top{display:flex;align-items:center}
.cim-mcard .rank{margin-left:auto;display:inline-grid;place-items:center;width:21px;height:21px;border-radius:50%;background:var(--cim-ink);color:var(--cim-surface);font-size:.7rem;font-weight:700}
.cim-mcard .big{font-size:1.85rem;font-weight:600;letter-spacing:-.02em;color:var(--cim-ink);margin-top:4px;font-variant-numeric:tabular-nums}
.cim-mcard .big em{font-style:normal;font-size:.95rem;color:var(--cim-muted);font-weight:500;margin-left:2px}
.cim-mcard .ci{font-size:.78rem;color:var(--cim-muted)}
.cim-mcard dl{display:grid;grid-template-columns:1fr auto;gap:2px 10px;font-size:.8rem;color:var(--cim-muted);margin:8px 0 0}
.cim-mcard dd{margin:0;color:var(--cim-ink);font-weight:600;text-align:right;font-variant-numeric:tabular-nums}
.cim-anom{display:grid;grid-template-columns:auto 1fr auto;gap:3px 12px;align-items:center;padding:9px 2px;border-bottom:1px solid var(--cim-line-2)}
.cim-anom code{font-weight:700;font-size:.75rem;color:var(--cim-ink-3);background:none}
.cim-anom .n{font-weight:600;text-align:right;color:var(--cim-ink);font-variant-numeric:tabular-nums}
.cim-anom .n small{display:block;color:var(--cim-muted);font-weight:400}
.cim-anom .rule{grid-column:2/4;color:var(--cim-muted);font-size:.75rem}
.cim-bar{height:6px;border-radius:3px;background:var(--cim-line-2);overflow:hidden;grid-column:2/4}
.cim-bar i{display:block;height:100%;border-radius:3px;animation:cimGrow .8s cubic-bezier(.2,.8,.2,1) both}
@keyframes cimGrow{from{width:0!important}}
.cim-spec{width:100%;border-collapse:collapse;font-size:.84rem}
.cim-spec td{padding:5px 0;border-bottom:1px solid var(--cim-line-2);color:var(--cim-ink)}
.cim-spec td:last-child{text-align:right;font-weight:500;font-variant-numeric:tabular-nums}
.cim-spec td.na{color:var(--cim-faint);font-weight:400}
.cim-notes{font-size:.8rem;color:var(--cim-muted);margin:6px 0 0;padding-left:18px}
.cim-notes li{margin:2px 0}
.cim-alert{display:flex;gap:10px;padding:11px 14px;border-radius:10px;font-size:.86rem;background:var(--cim-warn-soft);color:var(--cim-warn);border:1px solid transparent}
.cim-alert.info{background:var(--cim-primary-soft);color:var(--cim-primary)}
.cim-alert.bad{background:var(--cim-bad-soft);color:var(--cim-bad)}
.cim-alert.ok{background:var(--cim-ok-soft);color:var(--cim-ok)}
.cim-check{display:flex;gap:10px;padding:6px 0;border-bottom:1px solid var(--cim-line-2);font-size:.84rem;color:var(--cim-ink)}
.cim-check code{font-weight:700;background:none}
.cim-sec{display:flex;align-items:baseline;gap:12px;margin:26px 0 8px}
.cim-sec h2{font-size:1.12rem;margin:0;font-weight:600;color:var(--cim-ink)}
.cim-sec span{color:var(--cim-muted);font-size:.84rem}
.cim-arraygrid{display:grid;gap:5px;margin:6px 0}
.cim-arraygrid i{width:20px;height:31px;border-radius:3px;background:linear-gradient(180deg,#24435E,#13202D);box-shadow:inset 0 0 0 1px rgba(255,255,255,.18);animation:cimPop .3s cubic-bezier(.2,.8,.2,1) both}
@keyframes cimPop{from{transform:scale(.6);opacity:0}}
.cim-side{font-size:.78rem;color:#93A4B4;line-height:1.5}
.cim-side .dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:#1E7F5C;margin-right:6px}
.cim-run{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:10px;background:rgba(242,169,0,.12);border:1px solid rgba(242,169,0,.35);color:#F7E2AE;font-size:.8rem}
.cim-run b{color:#FFFFFF}
@media (max-width:1100px){.cim-mcards{grid-template-columns:repeat(2,minmax(0,1fr))}.cim-disc{grid-template-columns:1fr}}
@media (max-width:640px){.cim-mcards{grid-template-columns:1fr}.cim-hd{flex-direction:column;align-items:flex-start}}
@media (prefers-reduced-motion:reduce){.cim-hd,.cim-synth,.cim-dc,.cim-mcard,.cim-bar i,.cim-arraygrid i{animation:none!important;transition:none!important}}
"""

# Ajustes do layout Streamlit (únicos seletores internos usados; puramente cosméticos).
ST_OVERRIDES = """
[data-testid="stMainBlockContainer"]{padding-top:2.2rem;max-width:1500px}
[data-testid="stHeader"]{background:transparent}
[data-testid="stSidebar"]{background-image:linear-gradient(90deg,rgba(255,255,255,.03) 1px,transparent 1px),linear-gradient(rgba(255,255,255,.03) 1px,transparent 1px);background-size:26px 26px}
[data-testid="stVerticalBlockBorderWrapper"]{transition:box-shadow .2s}
@media (max-width:640px){[data-testid="stMainBlockContainer"]{padding-top:4.2rem}}
"""


def inject() -> None:
    """Injeta tokens + CSS global. Chamado uma vez por execução do script (app.py)."""
    ctx = getattr(st.context, "theme", None)
    dark = bool(ctx and getattr(ctx, "type", None) == "dark")
    css = (f":root{{{_vars(DARK if dark else LIGHT)}}}"
           f":root[data-cim-theme=light]{{{_vars(LIGHT)}}}:root[data-cim-theme=dark]{{{_vars(DARK)}}}"
           + COMPONENT_CSS + ST_OVERRIDES)
    st.html(f"<style>{css}</style>")


def is_dark() -> bool:
    ctx = getattr(st.context, "theme", None)
    return bool(ctx and getattr(ctx, "type", None) == "dark")


# ---------------------------------------------------------------------------
# Plotly
# ---------------------------------------------------------------------------
def plotly_layout(dark: bool | None = None) -> dict:
    dark = is_dark() if dark is None else dark
    t = DARK if dark else LIGHT
    ax = dict(gridcolor=t["line-2"], linecolor=t["line"], zeroline=False, tickfont=dict(size=11.5, color=t["muted"]),
              title=dict(font=dict(size=12.5, color=t["ink-3"])))
    return dict(font=dict(family="Plex, system-ui, sans-serif", size=12.5, color=t["ink"]),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=t["surface"],
                margin=dict(l=58, r=24, t=18, b=44),
                hoverlabel=dict(bgcolor="#13202D", bordercolor="#13202D", font=dict(color="#fff", family="Plex, sans-serif", size=12)),
                legend=dict(orientation="h", y=1.02, x=0, yanchor="bottom", font=dict(size=12), bgcolor="rgba(0,0,0,0)"),
                xaxis=dict(ax), yaxis=dict(ax), colorway=list(MODEL_COLORS.values()))


def plotly_config(name: str = "cim26") -> dict:
    return {"displaylogo": False, "responsive": True, "scrollZoom": False,
            "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
            "toImageButtonOptions": {"format": "svg", "filename": name, "scale": 2}}
