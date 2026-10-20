"""Artigo · Histórico: execuções imutáveis — reabrir, comparar, exportar e importar sem recalcular."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from cim26.experiment.run_store import import_zip, zip_run
from cim26.paths import RUNS_DIR

from .. import charts, nav, services
from .. import components as C

ss = st.session_state


def render():
    C.page_header("Histórico", "Artigo · cada execução é imutável; reabrir não recalcula modelos",
                  C.chip("estimado", "disco efêmero no Streamlit Cloud: exporte ZIPs"))
    runs = services.runs()
    if runs.empty:
        C.alert("Nenhuma execução registrada.", "info")
    else:
        view = runs.copy()
        view.insert(0, "situação", view.estado.map({"concluido": "● concluído", "executando": "◐ executando", "falhou": "✕ falhou",
                                                     "interrompido": "○ interrompido", "cancelado": "○ cancelado"}).fillna(view.estado))
        ev = st.dataframe(view.drop(columns=["estado"]), hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row", key="hist_tbl",
                          column_config={c: st.column_config.NumberColumn(format="%.3f") for c in view.columns if c.startswith("RMSE_")})
        rows = ev.selection.rows if ev and ev.selection else []
        sel = [runs.run_id.iloc[i] for i in rows]
        c1, c2, c3 = st.columns([1, 1, 3])
        if c1.button("Abrir em Resultados", icon=":material/insights:", disabled=len(sel) != 1, width="stretch", key="hist_open"):
            ss.res_run = sel[0]
            nav.go("resultados")
        if len(sel) == 1:
            c2.download_button("Baixar ZIP", zip_run(RUNS_DIR / sel[0]), f"{sel[0]}.zip", "application/zip", icon=":material/download:",
                               width="stretch", key="hist_zip")
        c3.caption("Selecione uma execução para abrir ou baixar; duas ou mais para comparar.")
        if len(sel) >= 2:
            comp = []
            for r in sel:
                p = RUNS_DIR / r / "metrics_energy.csv"
                if p.exists():
                    d = pd.read_csv(p)
                    d.insert(0, "execucao", r)
                    comp.append(d)
            if comp:
                cm = pd.concat(comp)
                C.sec("Comparação sem recalcular", f"{len(comp)} execuções")
                with st.container(border=True):
                    fig = charts.base(320, barmode="group", yaxis=dict(title=dict(text="nRMSE [%]")))
                    for m in ("M1", "M2", "M3", "M4"):
                        d = cm[cm.modelo == m]
                        fig.add_bar(x=d.execucao, y=d.NRMSE_media_pct if "NRMSE_media_pct" in d else d.RMSE_W, name=m,
                                    marker_color=charts.MODEL_COLORS[m])
                    charts.show(fig, "comparacao_execucoes", key="hist_cmp")
                cols = [c for c in ("execucao", "modelo", "N", "NRMSE_media_pct", "NMBE_media_pct", "erro_energia_pct", "RMSE_W") if c in cm]
                st.dataframe(cm[cols], hide_index=True, width="stretch")
    C.sec("Importar execução exportada", "reabre a partir dos arquivos, sem rodar modelos")
    up = st.file_uploader("ZIP de execução do CIM26", type=["zip"], key="hist_up")
    if up is not None and st.button("Importar", type="primary", icon=":material/upload:", key="hist_imp"):
        try:
            p = import_zip(up.getvalue(), RUNS_DIR)
            st.toast(f"Execução importada: {p.name}")
            ss.res_run = p.name
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
