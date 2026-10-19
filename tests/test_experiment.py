import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cim26.data import weather as W
from cim26.experiment.analysis import analyze_run, read_predictions
from cim26.experiment.config import ExperimentConfig, round_order
from cim26.experiment.run_store import import_zip, list_runs, load_run, zip_run
from cim26.experiment.runner import run_experiment
from cim26.pvcore.models import MODEL_IDS, prepare
from cim26.pvcore.sdm import SDMReference
from cim26.pvcore.thermal import build_conditions
from cim26.simulate import simulate
from tests.conftest import ROOT


def test_round_order_rotation_and_random():
    orders = [round_order(r, "rotativa", 1) for r in range(1, 12)]
    assert all(sorted(o) == list(MODEL_IDS) for o in orders)
    assert all(orders[i] != orders[i + 1] for i in range(10))
    for m in MODEL_IDS:
        pos = Counter(o.index(m) + 1 for o in orders)
        assert sorted(pos.values()) == [2, 3, 3, 3]
    a = [round_order(r, "aleatoria", 42) for r in range(1, 12)]
    assert a == [round_order(r, "aleatoria", 42) for r in range(1, 12)]
    assert all(sorted(o) == list(MODEL_IDS) for o in a)


def test_config_validation():
    with pytest.raises(ValueError):
        ExperimentConfig(repetitions=2).validate()
    with pytest.raises(ValueError):
        ExperimentConfig(repetitions=102).validate()
    ExperimentConfig(repetitions=101).validate()
    c = ExperimentConfig()
    assert c.repetitions == 11
    assert ExperimentConfig.from_dict(json.loads(json.dumps(c.to_dict()))) == c


def test_worker_11x4_sequential_isolated(tmp_path, field, supsi_module, supsi_cal):
    df, _ = field
    d = df[(df.g_poa_Wm2 >= 100) & df.t_module_C.notna() & df.p_mpp_measured_W.notna()].head(120)
    cond = build_conditions("A_tmod_medida", d.g_poa_Wm2.to_numpy(), t_module_C=d.t_module_C.to_numpy())
    params = {m: prepare(m, supsi_module, supsi_cal[0]) for m in MODEL_IDS}
    from cim26.pvcore.models import predict
    refs = {f"ref_{m}": predict(m, cond, params[m]).p_mpp_W for m in MODEL_IDS}
    np.savez(tmp_path / "bench_input.npz", g_poa_Wm2=cond.g_poa_Wm2, t_module_C=cond.t_module_C,
             t_cell_C=cond.t_cell_C, **refs)
    (tmp_path / "bench_spec.json").write_text(json.dumps({
        "params": {m: p.to_dict() for m, p in params.items()}, "repetitions": 11, "order_mode": "rotativa",
        "seed": 5, "execution_mode": "vetorizado", "warmup_samples": 20, "scaling_sizes": [],
        "tracemalloc_pass": False}, default=str))
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    r = subprocess.run([sys.executable, "-m", "cim26.benchmark.worker", str(tmp_path)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr
    runs = pd.read_csv(tmp_path / "benchmark_runs.csv")
    assert len(runs) == 44
    assert runs.groupby("rodada").modelo.apply(lambda s: sorted(s) == list(MODEL_IDS)).all()
    # nunca dois modelos ao mesmo tempo: intervalos [início, fim] disjuntos e na ordem declarada
    s = runs.sort_values("t_inicio_ns")
    assert (s["t_inicio_ns"].to_numpy()[1:] >= s["t_fim_ns"].to_numpy()[:-1]).all()
    assert list(zip(s.rodada, s.posicao)) == sorted(zip(s.rodada, s.posicao))
    for rd, g in runs.groupby("rodada"):
        assert list(g.sort_values("posicao").modelo) == round_order(rd, "rotativa", 5)
    assert runs.n_amostras.nunique() == 1
    assert (runs.groupby("modelo").pred_sha256_16.nunique() == 1).all()
    assert (runs.max_abs_diff_ref_W == 0).all() and not runs.falha.any()


@pytest.fixture(scope="module")
def small_run(tmp_path_factory):
    cfg = ExperimentConfig(months=("2019_02",), repetitions=3, scaling_sizes=(200,), bootstrap_B=300,
                           sensitivity_delta_t=(0.0, 3.0), calibration={**ExperimentConfig().calibration, "n_starts": 2},
                           tracemalloc_pass=False, label="teste")
    return run_experiment(cfg, tmp_path_factory.mktemp("runs"), use_lock=True)


def test_run_artifacts(small_run):
    for f in ["config.json", "input_quality.csv", "predictions.csv", "metrics_energy.csv", "benchmark_runs.csv",
              "benchmark_summary.csv", "statistics.csv", "metadata.json", "README_RUN.md", "calibration.json",
              "pareto.csv", "sensitivity.csv"]:
        assert (small_run / f).exists(), f
    assert len(list((small_run / "figures").glob("*.svg"))) >= 8
    q = pd.read_csv(small_run / "input_quality.csv")
    assert len(q) == 2536                                         # nenhuma linha apagada
    meta = json.loads((small_run / "metadata.json").read_text(encoding="utf-8"))
    assert "calibration_s" in meta["tempos_por_etapa_s"] and len(meta["entradas_sha256"]) == 3
    assert json.loads((small_run / "status.json").read_text())["estado"] == "concluido"


def test_metrics_recomputed_from_predictions(small_run):
    pred = read_predictions(small_run)
    m = pd.read_csv(small_run / "metrics_energy.csv").set_index("modelo")
    ok = np.isfinite(pred[[f"P_{k}_W" for k in MODEL_IDS] + ["P_obs_W"]]).all(axis=1)
    for k in MODEL_IDS:      # fórmula independente
        e = (pred.loc[ok, f"P_{k}_W"] - pred.loc[ok, "P_obs_W"]).to_numpy()
        assert m.loc[k, "RMSE_W"] == pytest.approx(np.sqrt(np.mean(e**2)), rel=1e-12)
        assert m.loc[k, "MBE_W"] == pytest.approx(np.mean(e), rel=1e-12, abs=1e-12)
    out = analyze_run(small_run, write=False)
    pd.testing.assert_frame_equal(out["metrics_energy"].reset_index(drop=True),
                                  pd.read_csv(small_run / "metrics_energy.csv"), check_dtype=False, atol=1e-12)


def test_zip_roundtrip_without_rerun(small_run, tmp_path, monkeypatch):
    import cim26.pvcore.models as Mmod
    data = zip_run(small_run)
    target = import_zip(data, tmp_path)
    monkeypatch.setattr(Mmod, "predict", lambda *a, **k: (_ for _ in ()).throw(AssertionError("não deve rodar")))
    run = load_run(target)
    assert run["metrics_energy"].equals(pd.read_csv(small_run / "metrics_energy.csv", float_precision="round_trip"))
    assert len(list_runs(tmp_path)) == 1
    from cim26.report.figures import make_all_figures
    assert len(make_all_figures(target)) >= 16


def test_modelos_and_artigo_identical(small_run, supsi_module, field):
    """Mesmas entradas e parametrização ⇒ mesma previsão física nos dois modos."""
    pred = read_predictions(small_run)
    raw = field[0].set_index(["source_file", "source_row"]).loc[list(zip(pred.source_file, pred.source_row))]
    cal = json.loads((small_run / "calibration.json").read_text(encoding="utf-8"))
    ref = SDMReference.from_dict(cal["sdm_reference"])
    cfg = json.loads((small_run / "config.json").read_text(encoding="utf-8"))
    w = W.WeatherSeries(timestamp=pd.DatetimeIndex(raw.timestamp), g_poa_Wm2=raw.g_poa_Wm2.to_numpy(),
                        origin="medido", description="teste", t_module_C=raw.t_module_C.to_numpy())
    res = simulate(supsi_module, w, MODEL_IDS, ref, strategy="A_tmod_medida", delta_t_C=cfg["delta_t_C"])
    for k in MODEL_IDS:
        np.testing.assert_array_equal(res.table[f"P_{k}_modulo_W"].to_numpy(), pred[f"P_{k}_W"].to_numpy())
