"""Interface Streamlit: arquitetura (sem servidor próprio), páginas sem exceções, serviços e consistência numérica."""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tests.conftest import ROOT

st_testing = pytest.importorskip("streamlit.testing.v1")
FORBIDDEN = re.compile(r"http\.server|ThreadingHTTPServer|serve_forever|webbrowser|uvicorn|socketserver")


def test_no_independent_http_server_in_codebase():
    offenders = []
    for p in list(ROOT.glob("*.py")) + list((ROOT / "cim26").rglob("*.py")) + list((ROOT / "ui").rglob("*.py")):
        if FORBIDDEN.search(p.read_text(encoding="utf-8")):
            offenders.append(str(p.relative_to(ROOT)))
    assert offenders == []
    assert not (ROOT / "web").exists()
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "st.navigation" in app and "__main__" not in app


def _wrapper(tmp_path, view: str) -> str:
    p = tmp_path / f"w_{view}.py"
    p.write_text(f"import sys\nsys.path.insert(0, r'{ROOT}')\nimport streamlit as st\nfrom ui import theme, state, nav\n"
                 f"theme.inject()\nstate.init()\nnav.build()\nfrom ui.views import {view}\n{view}.render()\n", encoding="utf-8")
    return str(p)


def test_app_entrypoint_runs_without_exceptions():
    at = st_testing.AppTest.from_file(str(ROOT / "app.py"), default_timeout=240).run()
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("view", ["simulador", "dados", "protocolo", "resultados", "historico"])
def test_every_page_renders(tmp_path, view, small_run, monkeypatch):
    import ui.services as S
    at = st_testing.AppTest.from_file(_wrapper(tmp_path, view), default_timeout=300)
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_simulador_controls_and_sdm(tmp_path):
    at = st_testing.AppTest.from_file(_wrapper(tmp_path, "simulador"), default_timeout=300).run()
    assert not at.exception
    at.toggle(key="sim_ov_t").set_value(True).run()
    assert not at.exception
    at.session_state["sdm"] = {}
    # calibração SDM via serviço (mesma função chamada pelo diálogo) e M4 disponível no estado
    import ui.services as S
    from cim26.data.supsi_lab import supsi_module_spec
    d = S.calibrate(json.dumps(supsi_module_spec().to_dict(), sort_keys=True))
    at.session_state["sdm"] = {"SUPSI_MONO_SI_REFERENCE": d}
    at.session_state["sim_models"] = ["M2", "M4"]
    at.run()
    assert not at.exception, [e.value for e in at.exception]


def test_services_simulate_equals_engine():
    import ui.services as S
    from cim26.data import weather as W
    from cim26.data.supsi_lab import supsi_module_spec
    from cim26.simulate import simulate
    m = supsi_module_spec()
    spec = {"source": "supsi", "days": ["2019-05-14"]}
    r = S.simulate(json.dumps(m.to_dict(), sort_keys=True), json.dumps(spec), "A_tmod_medida", 3.0, 2, 3, None)
    ref = simulate(m, W.supsi_days(S.field_df(), ["2019-05-14"]), ("M1", "M2", "M3"), None, "A_tmod_medida", 3.0, 2, 3)
    for k in ("M1", "M2", "M3"):
        np.testing.assert_array_equal(r["table"][f"P_{k}_arranjo_W"].to_numpy(), ref.table[f"P_{k}_arranjo_W"].to_numpy())
    assert r["has_obs"] and "P_obs_arranjo_W" in r["table"]
    other = S.simulate(json.dumps(S.library()["CS6K-275P"].to_dict(), sort_keys=True), json.dumps(spec), None, 3.0, 1, 1, None)
    assert not other["has_obs"]                      # medida só comparável ao próprio módulo SUPSI


def test_bundled_v11_run_reproduced_by_current_engine():
    """Mesmas entradas e parâmetros ⇒ mesmas previsões antes (v1.1) e depois (v2.0) da migração."""
    from cim26.data.supsi_field import load_field
    from cim26.data.supsi_lab import supsi_module_spec
    from cim26.pvcore.models import prepare, predict
    from cim26.pvcore.sdm import SDMReference
    from cim26.pvcore.thermal import build_conditions
    runs = sorted((ROOT / "runs").glob("2*/predictions.csv"))
    assert runs, "execução de verificação ausente"
    rd = runs[-1].parent
    pred = pd.read_csv(rd / "predictions.csv", float_precision="round_trip").head(400)
    cfg = json.loads((rd / "config.json").read_text(encoding="utf-8"))
    ref = SDMReference.from_dict(json.loads((rd / "calibration.json").read_text(encoding="utf-8"))["sdm_reference"])
    raw = load_field()[0].set_index(["source_file", "source_row"]).loc[list(zip(pred.source_file, pred.source_row))]
    cond = build_conditions("A_tmod_medida", raw.g_poa_Wm2.to_numpy(), t_module_C=raw.t_module_C.to_numpy(), delta_t_C=cfg["delta_t_C"])
    m = supsi_module_spec()
    for k in ("M1", "M2", "M3", "M4"):
        out = predict(k, cond, prepare(k, m, ref)).p_mpp_W
        np.testing.assert_allclose(out, pred[f"P_{k}_W"].to_numpy(), rtol=0, atol=1e-12)


def test_lock_is_exclusive_and_cancel_preserves_partial(tmp_path):
    from cim26.experiment.run_store import LOCK_NAME, _claim_lock, acquire_lock, active_run, cancel_run
    _claim_lock(tmp_path, "run_a")
    with pytest.raises(RuntimeError):
        _claim_lock(tmp_path, "run_b")                # segunda sessão não lança outro experimento
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    (tmp_path / "run_a").mkdir()
    (tmp_path / "run_a" / "status.json").write_text(json.dumps({"estado": "executando"}))
    acquire_lock(tmp_path, "run_a", pid=proc.pid)
    assert active_run(tmp_path)["run_id"] == "run_a"
    assert cancel_run(tmp_path) == "run_a"
    proc.wait(timeout=10)
    assert json.loads((tmp_path / "run_a" / "status.json").read_text())["estado"] == "cancelado"
    assert not (tmp_path / LOCK_NAME).exists()


def test_streamlit_cloud_files():
    req = (ROOT / "requirements.txt").read_text()
    assert "streamlit" in req and "fastapi" not in req and "uvicorn" not in req
    cfg = (ROOT / ".streamlit" / "config.toml").read_text()
    assert "enableStaticServing = true" in cfg and "[theme.dark]" in cfg and "[theme.light]" in cfg
    for f in ("static/logo.svg", "static/fonts/ibm-plex-sans-latin-400-normal.woff2"):
        assert (ROOT / f).exists()
    assert "localhost" not in "".join(p.read_text(encoding="utf-8") for p in (ROOT / "ui").rglob("*.py"))
