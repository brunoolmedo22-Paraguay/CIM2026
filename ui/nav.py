"""Navegação (st.navigation) e barra lateral com monitor global de execução."""

from __future__ import annotations

import streamlit as st

from cim26 import __version__
from cim26.experiment.run_store import active_run, read_status
from cim26.paths import RUNS_DIR

PAGES: dict = {}


def progress_of(s: dict) -> float:
    idx, b = s.get("etapa_idx") or 0, s.get("benchmark") or {}
    if idx < 7:
        return 0.03 + 0.17 * idx / 6
    if idx == 7:
        return 0.2 + 0.7 * (b.get("feitos", 0) / b["total"] if b.get("total") else 0)
    return 0.9 + 0.1 * (idx - 7) / 3


def build() -> dict:
    from .views import dados, historico, protocolo, resultados, simulador
    PAGES.update(
        simulador=st.Page(simulador.render, title="Simulador", icon=":material/solar_power:", url_path="simulador", default=True),
        dados=st.Page(dados.render, title="Dados e qualidade", icon=":material/monitoring:", url_path="dados"),
        protocolo=st.Page(protocolo.render, title="Protocolo e execução", icon=":material/tune:", url_path="protocolo"),
        resultados=st.Page(resultados.render, title="Resultados e discussão", icon=":material/insights:", url_path="resultados"),
        historico=st.Page(historico.render, title="Histórico", icon=":material/history:", url_path="historico"),
    )
    return {"Modelos": [PAGES["simulador"]],
            "Artigo · SUPSI 2019": [PAGES["dados"], PAGES["protocolo"], PAGES["resultados"], PAGES["historico"]]}


def go(name: str) -> None:
    st.switch_page(PAGES[name])


def sidebar() -> None:
    active = active_run(RUNS_DIR) is not None

    @st.fragment(run_every=2.5 if active else 20)
    def run_status():
        a = active_run(RUNS_DIR)
        if not a:
            if st.session_state.get("_was_running"):
                st.session_state["_was_running"] = None
                st.rerun(scope="app")
            return
        st.session_state["_was_running"] = a["run_id"]
        s = read_status(RUNS_DIR / a["run_id"])
        p = progress_of(s)
        st.html(f'<div class="cim-run"><svg width="22" height="22" viewBox="0 0 22 22"><circle cx="11" cy="11" r="8" fill="none" stroke="rgba(255,255,255,.15)" stroke-width="3"/>'
                f'<circle cx="11" cy="11" r="8" fill="none" stroke="#F2A900" stroke-width="3" stroke-dasharray="{50.27 * p:.1f} 50.27" transform="rotate(-90 11 11)" stroke-linecap="round"/></svg>'
                f'<span><b>{round(100 * p)} %</b> · {s.get("etapa") or "iniciando"}</span></div>')
        st.page_link(PAGES["protocolo"], label="Acompanhar execução", icon=":material/arrow_forward:")

    with st.sidebar:
        run_status()
        st.html(f'<div class="cim-side"><span class="dot"></span>Motor local · Streamlit<br>CIM26 v{__version__} · M1–M4 · SUPSI 2019</div>')
