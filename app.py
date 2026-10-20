"""CIM26 — Photovoltaic Model Laboratory (entrada Streamlit).

    streamlit run app.py

Streamlit gerencia todo o ciclo de vida: nenhum servidor HTTP próprio, nenhuma porta
fixa, nenhum navegador aberto pelo app. O motor científico está em ``cim26/`` e é
independente desta interface (``ui/``).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="CIM26 · Exatidão × custo FV", page_icon=":material/solar_power:", layout="wide",
                   initial_sidebar_state="auto")

from cim26.paths import ensure_dirs  # noqa: E402
from ui import components, nav, state, theme  # noqa: E402

ensure_dirs()
theme.inject()
state.init()
st.logo(str(ROOT / "static" / "logo.svg"), icon_image=str(ROOT / "static" / "logo_icon.svg"), size="large")
page = st.navigation(nav.build(), position="sidebar")
nav.sidebar()
with st.sidebar:
    components.theme_sync()
page.run()
