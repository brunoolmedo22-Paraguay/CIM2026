"""Serviços da interface: acesso ao motor ``cim26`` com cache de VISUALIZAÇÃO.

O cache (st.cache_data/st.cache_resource) é usado apenas para dados de entrada,
simulações interativas e leitura de execuções já concluídas. O benchmark nunca
passa por aqui: ele roda em processo separado e executa os modelos de verdade.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from cim26.calibration.classical import calibrate_classical
from cim26.calibration.multipoint import calibrate_multipoint
from cim26.calibration.store import _jsonable, list_calibrations
from cim26.data import weather as W
from cim26.data.anomalies import anomaly_summary
from cim26.data.catalog import library as _library
from cim26.data.supsi_field import QualityConfig, load_field, monthly_summary
from cim26.data.supsi_lab import check_lab, load_supsi_module_json, read_iec61853_xlsx, supsi_module_spec
from cim26.experiment.config import ExperimentConfig
from cim26.experiment.metrics import common_support
from cim26.experiment.run_store import list_runs, read_status
from cim26.experiment.runner import quality_with_anomalies
from cim26.paths import RUNS_DIR
from cim26.pvcore.models import MODEL_IDS, availability
from cim26.pvcore.module import KIND_EXPERIMENTAL, ModuleSpec
from cim26.pvcore.sdm import STATUS_LABELS, SDMReference
from cim26.simulate import iv_curve_array, simulate as _simulate, thermal_options

SUPSI_ID = "SUPSI_MONO_SI_REFERENCE"


# ---------------------------------------------------------------- entradas
@st.cache_resource(show_spinner=False)
def field_df() -> pd.DataFrame:
    return load_field()[0]


@st.cache_resource(show_spinner=False)
def lab_obj():
    return read_iec61853_xlsx()


@st.cache_data(show_spinner=False)
def _library_dicts() -> dict:
    return {k: v.to_dict() for k, v in _library().items()}


def library() -> dict[str, ModuleSpec]:
    return {k: ModuleSpec.from_dict(v) for k, v in _library_dicts().items()}


def refresh_library() -> None:
    _library_dicts.clear()


def sdm_method(m: ModuleSpec) -> str | None:
    if m.kind == KIND_EXPERIMENTAL:
        return "multiponto"
    return "classico" if not m.classical_sdm_inputs_missing() else None


def model_availability(m: ModuleSpec, sdm: dict | None) -> dict:
    ref = SDMReference.from_dict(sdm["reference"]) if sdm else None
    out = {k: availability(k, m, ref if k == "M4" else None).__dict__ for k in MODEL_IDS}
    if not out["M4"]["available"] and sdm_method(m):
        out["M4"]["reason"] = "Calibrável: clique em M4 para estimar os parâmetros SDM."
    return out


@st.cache_data(show_spinner="Estimando parâmetros do SDM…")
def calibrate(module_json: str) -> dict:
    """Calibração SDM (clássica ou multiponto). Cache de interface: o experimento sempre recalibra."""
    m = ModuleSpec.from_dict(json.loads(module_json))
    if m.kind == KIND_EXPERIMENTAL:
        ref, rep = calibrate_multipoint(lab_obj().long, m)
        return _jsonable({"method": "multiponto", "reference": ref.to_dict(), "report": rep.to_json_dict()})
    ref, rep = calibrate_classical(m)
    return _jsonable({"method": "classico", "reference": ref.to_dict(), "report": rep.to_dict()})


def saved_calibration(module_id: str) -> dict | None:
    saved = list_calibrations(module_id)
    if not saved:
        return None
    d = saved[0]
    return {"method": d["sdm_reference"]["method"], "reference": d["sdm_reference"], "report": d["report"], "file": d["_path"]}


@st.cache_data(show_spinner=False)
def supsi_days() -> pd.DataFrame:
    f = field_df()
    d = f.assign(day=f["timestamp"].dt.date.astype(str))
    return d.groupby("day").agg(n=("row_id", "size"), g_max=("g_poa_Wm2", "max"),
                                h=("g_poa_Wm2", lambda s: float(np.nansum(s)) * 5 / 60 / 1000)).reset_index()


def inspect_csv(text: str) -> pd.DataFrame:
    return pd.read_csv(io.StringIO(text), sep=None, engine="python")


def weather_from_spec(spec: dict) -> W.WeatherSeries:
    src = spec.get("source", "supsi")
    if src == "supsi":
        return W.supsi_days(field_df(), spec.get("days") or ["2019-05-14"])
    if src == "csv":
        raw = inspect_csv(spec["text"])
        return W.from_dataframe(raw, spec["ts_col"], spec["g_col"], spec.get("g_kind", "POA"),
                                horizontal=bool(spec.get("horizontal")), temp_col=spec.get("t_col") or None,
                                temp_kind=spec.get("t_kind") or None, wind_col=spec.get("w_col") or None)
    if src == "synthetic":
        return W.synthetic(spec["profile"], spec["season"], duration_min=int(spec["duration_min"]),
                           step_min=int(spec["step_min"]), g_peak=spec.get("g_peak") or None, seed=int(spec.get("seed", 42)))
    return W.manual(float(spec["g"]), float(spec["t"]), spec["t_kind"], duration_min=int(spec["duration_min"]),
                    step_min=1, wind=spec.get("wind"))


@st.cache_data(show_spinner=False, max_entries=48)
def simulate(module_json: str, weather_json: str, strategy: str | None, delta_t: float, ns: int, npar: int,
             sdm_json: str | None) -> dict:
    """Simulação do modo Modelos com o motor físico comum (mesmo código do Artigo)."""
    m = ModuleSpec.from_dict(json.loads(module_json))
    spec = json.loads(weather_json)
    wx = weather_from_spec(spec)
    opts = thermal_options(wx, m)
    usable = [o[0] for o in opts if o[2]]
    strat = strategy if strategy in usable else (usable[0] if usable else None)
    ref = SDMReference.from_dict(json.loads(sdm_json)["reference"]) if sdm_json else None
    res = _simulate(m, wx, MODEL_IDS, ref, strat, float(delta_t), int(ns), int(npar))
    tab = res.table.copy()
    if wx.t_amb_C is not None:
        tab["t_amb_C"] = wx.t_amb_C
    obs = None
    if spec.get("source") == "supsi" and m.kind == KIND_EXPERIMENTAL:   # medida só é comparável ao próprio módulo SUPSI
        f = field_df()
        d = f[f["timestamp"].dt.date.astype(str).isin(spec.get("days") or ["2019-05-14"])].sort_values("row_id")
        obs = (d["p_mpp_measured_W"].to_numpy(float) * ns * npar)
        tab["P_obs_arranjo_W"] = obs
    status = {k: {STATUS_LABELS.get(int(s), str(s)): int(n) for s, n in tab[f"status_{k}"].value_counts().items()}
              for k in MODEL_IDS if f"status_{k}" in tab}
    return {"table": tab, "kpis": res.kpis, "availability": {k: v.__dict__ for k, v in res.statuses.items()},
            "provenance": res.provenance, "notes": res.notes, "status": status,
            "weather": {"origin": wx.origin, "description": wx.description, "n": len(wx), "temps": wx.temperature_kinds()},
            "thermal": {"options": [{"id": o[0], "label": o[1], "ok": o[2], "why": o[3]} for o in opts], "used": strat},
            "p_inst_W": m.p_stc_W * ns * npar, "has_obs": obs is not None}


@st.cache_data(show_spinner="Calculando curvas I–V ao longo do dia…", max_entries=16)
def iv_frames(sdm_json: str, g: tuple, t: tuple, ns: int, npar: int) -> list[dict]:
    ref = SDMReference.from_dict(json.loads(sdm_json)["reference"])
    out = []
    for gi, ti in zip(g, t):
        V, I, P, mpp = iv_curve_array(ref, gi, ti, ns, npar, 120)
        out.append({"V": V, "I": I, "P": P, "mpp": mpp})
    return out


# ---------------------------------------------------------------- Artigo: dados
@st.cache_data(show_spinner="Avaliando qualidade e anomalias…")
def quality(months: tuple, g: float, strategy: str, policy: str) -> pd.DataFrame:
    m = supsi_module_spec()
    df, _ = load_field(months)
    cfg = ExperimentConfig(months=months, g_threshold_Wm2=g, thermal_strategy=strategy, anomaly_policy=policy)
    return quality_with_anomalies(df, QualityConfig(g_threshold_Wm2=g, require_ambient=strategy == "B_faiman",
                                                    voc_stc_V=m.v_oc_V, p_stc_W=m.p_stc_W), m, cfg)


@st.cache_data(show_spinner=False)
def quality_views(months: tuple, g: float, strategy: str, policy: str, gap: float = 7.5) -> dict:
    q = quality(months, g, strategy, policy)
    days = q.assign(day=q["timestamp"].dt.date.astype(str)).groupby("day").agg(
        n=("row_id", "size"), n_el=("eligible", "sum"),
        n_anom=("anom_severidade", lambda s: int(s.isin(["erro", "suspeito"]).sum()))).reset_index()
    return {"monthly": monthly_summary(q, gap), "anomalies": anomaly_summary(q), "days": days,
            "isc_ratio": q.loc[q.eligible, "isc_ratio"].dropna().to_numpy(), "pr": q.loc[q.eligible, "pr_inst"].dropna().to_numpy()}


@st.cache_data(show_spinner=False)
def lab_view() -> dict:
    L = lab_obj()
    return {"matrices": {v: L.matrix(v) for v in ("Pmp", "Isc", "Voc")}, "coefficients": L.coefficients,
            "thermal": L.thermal, "checks": check_lab(L, load_supsi_module_json()), "audit": L.audit_missing_cells}


@st.cache_data(show_spinner="Ajuste multiponto com 66 medições de laboratório (≈ 10 s)…")
def calibration_preview() -> dict:
    ref, rep = calibrate_multipoint(lab_obj().long, supsi_module_spec())
    return _jsonable({"reference": ref.to_dict(), "report": rep.to_json_dict()})


# ---------------------------------------------------------------- execuções
def runs() -> pd.DataFrame:
    return list_runs(RUNS_DIR)


def run_stamp(run_id: str) -> float:
    p = RUNS_DIR / run_id / "status.json"
    return p.stat().st_mtime if p.exists() else 0.0


def _csv(rd: Path, name: str):
    p = rd / f"{name}.csv"
    return pd.read_csv(p, float_precision="round_trip", low_memory=False) if p.exists() else None


@st.cache_data(show_spinner="Carregando execução…", max_entries=8)
def run_bundle(run_id: str, stamp: float) -> dict:
    """Carrega uma execução concluída a partir dos arquivos (sem recalcular modelos)."""
    rd = RUNS_DIR / run_id
    out = {"run_id": run_id, "status": read_status(rd), "config": json.loads((rd / "config.json").read_text(encoding="utf-8"))}
    if out["status"].get("estado") != "concluido":
        return out
    for k in ("metrics_energy", "metrics_daily", "metrics_monthly", "residual_bins", "bootstrap_ci", "bootstrap_paired",
              "benchmark_summary", "benchmark_runs", "time_ratios", "determinism", "pareto", "marginal", "sensitivity",
              "quality_sensitivity", "anomaly_summary", "benchmark_tracemalloc", "statistics"):
        out[k] = _csv(rd, k)
    for j in ("narrative", "metadata", "calibration"):
        p = rd / f"{j}.json"
        out[j] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    pred = _csv(rd, "predictions")
    pred["timestamp"] = pd.to_datetime(pred["timestamp"])
    out["days"] = sorted(pred["timestamp"].dt.date.astype(str).unique().tolist())
    out["scatter"] = pred.sample(min(3000, len(pred)), random_state=0)
    edges = np.linspace(-120, 120, 97)
    out["residual_hist"] = {"edges": edges, **{m: np.histogram(pred[f"res_{m}_W"].dropna(), bins=edges)[0] for m in MODEL_IDS}}
    out["figures"] = sorted(p.name for p in (rd / "figures").glob("*.svg")) if (rd / "figures").exists() else []
    return out


@st.cache_data(show_spinner=False, max_entries=16)
def run_series(run_id: str, stamp: float, start: str, end: str) -> pd.DataFrame:
    rd = RUNS_DIR / run_id
    pred = _csv(rd, "predictions")
    pred["timestamp"] = pd.to_datetime(pred["timestamp"])
    pred = pred.sort_values("row_id").reset_index(drop=True)
    cfg = json.loads((rd / "config.json").read_text(encoding="utf-8"))
    _, pairs = common_support(pred, cfg["max_gap_min"])
    pred["pair_next"] = np.r_[pairs, False]
    d = pred["timestamp"].dt.date.astype(str)
    return pred[(d >= start) & (d <= end)].reset_index(drop=True)
