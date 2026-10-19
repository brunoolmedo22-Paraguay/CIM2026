"""Identidade visual: tokens, CSS mínimo e componentes de proveniência."""

from __future__ import annotations

import html

import streamlit as st

from cim26.pvcore.models import MODEL_IDS, MODEL_INFO

INK = "#1C2B39"
MUTED = "#5A6B7B"
RULE = "#D3DCE5"
SURFACE = "#FFFFFF"
SUN = "#E8B04B"
COLORS = {m: MODEL_INFO[m].color for m in MODEL_IDS}
OBS = INK

PROV_STYLE = {
    "medido": ("#E4F1EA", "#1E6B4E"),
    "estimado": ("#FBF0DA", "#8A5A00"),
    "hipótese": ("#FBE6E6", "#9B2C2C"),
    "simulado": ("#E8EEF9", "#2F4F8A"),
    "manual": ("#EEE8F6", "#5B3F8A"),
    "laboratório": ("#E6F0F6", "#1F5F8B"),
    "indisponível": ("#EEF1F4", "#5A6B7B"),
}

CSS = f"""
<style>
.block-container {{ padding-top: 2.2rem; max-width: 1480px; }}
h1, h2, h3 {{ letter-spacing: -0.01em; color: {INK}; }}
h1 {{ font-size: 2.05rem !important; }}
.cim-lede {{ color: {MUTED}; font-size: 0.98rem; max-width: 74ch; margin: -0.4rem 0 1.1rem 0; }}
.cim-chip {{ display:inline-block; padding: 0.06rem 0.5rem; border-radius: 0.3rem; font-size: 0.78rem;
            font-weight: 600; margin: 0 0.25rem 0.2rem 0; white-space: nowrap; }}
.cim-tag {{ display:inline-flex; align-items:center; gap:0.35rem; font-weight:600; font-size:0.86rem; }}
.cim-tag i {{ display:inline-block; width:0.72rem; height:0.72rem; border-radius:2px; }}
.cim-strip {{ display:grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 0;
             border: 1px solid {RULE}; border-radius: 0.4rem; background: {SURFACE}; margin: 0.2rem 0 1rem 0; }}
.cim-strip div {{ padding: 0.5rem 0.8rem; border-right: 1px solid {RULE}; }}
.cim-strip div:last-child {{ border-right: none; }}
.cim-strip span {{ display:block; color:{MUTED}; font-size:0.74rem; }}
.cim-strip b {{ font-size: 0.95rem; color:{INK}; font-weight: 600; }}
.cim-note {{ border-left: 3px solid {RULE}; padding: 0.15rem 0 0.15rem 0.8rem; color: {MUTED};
            font-size: 0.86rem; margin: 0.4rem 0 0.8rem 0; max-width: 92ch; }}
.cim-avail {{ font-size: 0.84rem; line-height: 1.35; margin-bottom: 0.35rem; }}
.cim-avail .no {{ color: #9B2C2C; }}
div[data-testid="stMetricValue"] {{ font-variant-numeric: tabular-nums; }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def chip(kind: str, text: str | None = None) -> str:
    bg, fg = PROV_STYLE.get(kind, PROV_STYLE["indisponível"])
    return f'<span class="cim-chip" style="background:{bg};color:{fg}">{html.escape(text or kind)}</span>'


def model_tag(m: str, with_name: bool = True) -> str:
    name = f" {html.escape(MODEL_INFO[m].short)}" if with_name else ""
    return f'<span class="cim-tag"><i style="background:{COLORS[m]}"></i>{m}{name}</span>'


def strip(items: list[tuple[str, str]]) -> None:
    cells = "".join(f"<div><span>{html.escape(k)}</span><b>{html.escape(str(v))}</b></div>" for k, v in items)
    st.markdown(f'<div class="cim-strip">{cells}</div>', unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<div class="cim-note">{text}</div>', unsafe_allow_html=True)


def lede(text: str) -> None:
    st.markdown(f'<p class="cim-lede">{text}</p>', unsafe_allow_html=True)


def provenance_kind(text: str) -> str:
    t = (text or "").lower()
    for k in ("hipótese", "estimado", "medido", "simulado", "manual", "indisponível"):
        if k in t:
            return k
    return "indisponível"
