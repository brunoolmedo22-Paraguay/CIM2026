"""CIM26 — aplicação Streamlit. Iniciar com:  streamlit run app.py

Apenas apresentação: toda física, calibração, experimento e estatística estão
no pacote ``cim26`` (testável sem Streamlit).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from cim26 import __version__  # noqa: E402
from cim26.paths import ensure_dirs  # noqa: E402
from ui import page_artigo, page_modelos  # noqa: E402
from ui.style import inject_css  # noqa: E402

st.set_page_config(page_title="CIM26 · exatidão × custo FV", page_icon=":material/solar_power:", layout="wide")
ensure_dirs()
inject_css()

nav = st.navigation(
    [st.Page(page_modelos.render, title="Modelos", icon=":material/solar_power:", url_path="modelos", default=True),
     st.Page(page_artigo.render, title="Artigo", icon=":material/science:", url_path="artigo")],
    position="top",
)
nav.run()
st.caption(f"CIM26 v{__version__} · motor independente da interface · dados SUPSI/IEA PVPS T13 · "
           "PVGIS c-Si CURRENT · sem rede externa")
