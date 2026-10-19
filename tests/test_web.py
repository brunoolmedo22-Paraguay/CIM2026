"""API local e arquivos estáticos da interface (sem navegador)."""
import json
import threading
import urllib.error
import urllib.request

import pytest

import web.server as srvmod


@pytest.fixture(scope="module")
def base(small_run):
    srvmod.RUNS_DIR = small_run.parent
    srv = srvmod.make_server(port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def get(url):
    with urllib.request.urlopen(url, timeout=120) as r:
        return r.status, r.headers.get("Content-Type"), r.read()


def post(url, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_static_assets_offline(base):
    st, ct, html = get(base + "/")
    assert st == 200 and b"CIM26" in html and b"/vendor/plotly.min.js" in html
    for path, kind in (("/vendor/plotly.min.js", "javascript"), ("/static/js/main.js", "javascript"),
                       ("/static/app.css", "css"), ("/static/fonts/ibm-plex-sans-latin-400-normal.woff2", "font")):
        st, ct, _ = get(base + path)
        assert st == 200 and kind in ct, path


def test_meta_and_library(base):
    meta = json.loads(get(base + "/api/meta")[2])
    assert [m["id"] for m in meta["models"]] == ["M1", "M2", "M3", "M4"]
    lib = {m["id"]: m for m in json.loads(get(base + "/api/library")[2])}
    assert "SUPSI_MONO_SI_REFERENCE" in lib and "CS6K-275P" in lib
    assert lib["SUPSI_MONO_SI_REFERENCE"]["sdm_method"] == "multiponto"
    assert lib["CS6K-275P"]["sdm_method"] == "classico"


def test_simulate_measured_only_for_supsi_module(base):
    w = {"source": "supsi", "days": ["2019-05-14"]}
    st, r = post(base + "/api/simulate", {"module_id": "SUPSI_MONO_SI_REFERENCE", "weather": w, "array": {"ns": 2, "np": 1}})
    assert st == 200 and "P_obs" in r["series"] and r["array"]["ns"] == 2
    assert r["thermal"]["used"] == "A_tmod_medida"
    st, r = post(base + "/api/simulate", {"module_id": "CS6K-275P", "weather": w})
    assert st == 200 and "P_obs" not in r["series"]          # outro módulo: sem comparação com a medida


def test_ghi_rejected_via_api(base):
    text = "t,ghi\n2025-01-01 10:00,500\n2025-01-01 10:05,520\n"
    st, r = post(base + "/api/simulate", {"module_id": "CS6K-275P", "weather": {"source": "csv", "text": text, "ts_col": "t",
                                                                                 "g_col": "ghi", "g_kind": "GHI"}})
    assert st == 400 and "GHI não é POA" in r["error"]


def test_sdm_estimate_then_iv(base):
    st, r = post(base + "/api/sdm/estimate", {"module_id": "CS6K-275P"})
    assert st == 200 and r["method"] == "classico" and r["report"]["success"]
    st, iv = post(base + "/api/iv", {"module_id": "CS6K-275P", "g": 1000, "t_cell": 25, "ns": 2, "np": 3})
    assert st == 200 and iv["mpp"]["Pmp"] == pytest.approx(31.0 * 8.88 * 6, rel=2e-3)


def test_quality_endpoint(base):
    q = json.loads(get(base + "/api/artigo/quality?months=2019_02&g=100&strategy=A_tmod_medida&policy=sinalizar")[2])
    assert {a["codigo"] for a in q["anomalies"]} >= {"A01", "A02", "A03", "A05", "T01"}
    assert q["monthly"][-1]["n_total"] == 2536


def test_run_bundle_series_and_zip(base, small_run):
    runs = json.loads(get(base + "/api/runs")[2])
    rid = small_run.name
    assert any(r["run_id"] == rid for r in runs)
    d = json.loads(get(base + f"/api/runs/{rid}")[2])
    assert d["narrative"] and d["metrics_energy"][0]["NRMSE_media_pct"] > 0 and d["quality_sensitivity"]
    s = json.loads(get(base + f"/api/runs/{rid}/series?start={d['days'][0]}&end={d['days'][0]}")[2])
    assert s and "P_obs_W" in s[0] and "pair_next" in s[0]
    st, ct, z = get(base + f"/api/runs/{rid}/zip")
    assert z[:2] == b"PK"
