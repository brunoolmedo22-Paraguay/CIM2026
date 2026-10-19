"""Smoke test da interface (Streamlit AppTest, sem navegador nem rede)."""
from pathlib import Path

import pytest

st_testing = pytest.importorskip("streamlit.testing.v1")
ROOT = Path(__file__).resolve().parents[1]


def _wrapper(tmp_path, body: str) -> str:
    p = tmp_path / "w.py"
    p.write_text(f"import sys\nsys.path.insert(0, r'{ROOT}')\nfrom ui.style import inject_css\ninject_css()\n{body}\n",
                 encoding="utf-8")
    return str(p)


def test_app_entrypoint_runs():
    at = st_testing.AppTest.from_file(str(ROOT / "app.py"), default_timeout=180).run()
    assert not at.exception
    assert [t.value for t in at.title] == ["Modelos"]
    assert len(at.metric) == 4


def test_modelos_supsi_sdm_button(tmp_path):
    at = st_testing.AppTest.from_file(_wrapper(tmp_path, "from ui import page_modelos\npage_modelos.render()"),
                                      default_timeout=240)
    at.session_state["mod_id"] = "SUPSI_MONO_SI_REFERENCE"
    at.run()
    at.segmented_control(key="model_sel").set_value("M4").run()
    btn = [b for b in at.button if b.label == "Estimar parâmetros SDM"]
    assert btn, "botão de calibração SDM ausente"
    btn[0].click().run()
    assert not at.exception
    assert any("arranques" in s.value for s in at.success)
    assert len(at.metric) == 4                        # KPIs do SDM calculados


def test_artigo_three_areas(tmp_path):
    at = st_testing.AppTest.from_file(_wrapper(tmp_path, "from ui import page_artigo\npage_artigo.render()"),
                                      default_timeout=240).run()
    assert not at.exception
    assert any(b.label == "Executar experimento científico" for b in at.button)
    for view in ("Resultados", "Histórico"):
        at.segmented_control(key="art_view").set_value(view).run()
        assert not at.exception
