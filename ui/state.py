"""Estado da sessão: valores padrão únicos e persistência entre páginas.

Regras (evitam avisos de widget e perdas ao navegar):
* todo valor padrão é definido AQUI, via setdefault, nunca no widget;
* widgets usam ``key=`` sem ``value=``/``default=``;
* chaves de widgets reatribuídas a cada execução para sobreviverem à troca de página.
"""

from __future__ import annotations

import copy

import streamlit as st

from cim26.data.supsi_field import AVAILABLE_MONTHS

SUPSI_ID = "SUPSI_MONO_SI_REFERENCE"

DEFAULTS = {
    # Simulador
    "sim_module": SUPSI_ID, "sim_ns": 1, "sim_np": 1,
    "sim_weather": {"source": "supsi", "days": ["2019-05-14"]},
    "sim_thermal": {"strategy": None, "delta_t": 3.0},
    "sim_models": ["M2"], "sim_focus": "M2",
    "sim_ov_g": True, "sim_ov_t": False, "sim_ov_obs": True,
    "sdm": {},
    # Artigo · dados
    "dq_months": list(AVAILABLE_MONTHS), "dq_g": 100, "dq_policy": "sinalizar", "dq_day": "2019-05-14",
    "dq_show_g": True, "dq_show_isc": False, "dq_show_t": False,
    # Artigo · protocolo
    "p_months": list(AVAILABLE_MONTHS), "p_g": 100.0, "p_gap": 7.5, "p_policy": "sinalizar", "p_strategy": "A_tmod_medida",
    "p_dt": 3.0, "p_reps": 11, "p_order": "rotativa", "p_seed": 20261019, "p_mode": "vetorizado",
    "p_scaling": True, "p_sens": True, "p_tm": True, "p_label": "",
    # Artigo · resultados
    "res_run": None, "res_range": None, "res_ov_g": True, "res_ov_anom": True, "res_ov_t": False, "res_daily_metric": "NRMSE_media_pct",
}

PERSIST = [k for k in DEFAULTS if k not in ("sdm", "sim_weather", "sim_thermal", "sim_models", "res_range")]


def init() -> None:
    for k, v in DEFAULTS.items():
        if k not in st.session_state:
            st.session_state[k] = copy.deepcopy(v)
    for k in PERSIST:                      # mantém valores de widgets entre páginas
        st.session_state[k] = st.session_state[k]
