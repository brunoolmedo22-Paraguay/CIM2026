"""Servidor local da interface CIM26 (biblioteca padrão; sem dependências extras, sem rede externa).

Serve a SPA em web/static (HTML/CSS/JS), o Plotly.js empacotado com o pacote Python
``plotly`` e uma API JSON fina sobre o motor ``cim26`` (nenhuma física aqui).
"""

from __future__ import annotations

import io
import json
import mimetypes
import threading
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import numpy as np
import pandas as pd

from cim26 import __version__
from cim26.calibration.classical import calibrate_classical
from cim26.calibration.multipoint import calibrate_multipoint
from cim26.calibration.store import _jsonable, list_calibrations, save_calibration
from cim26.constants import SANDIA_DELTA_T_DEFAULT_C
from cim26.data import weather as W
from cim26.data.anomalies import ANOMALIES, AnomalyConfig, anomaly_summary
from cim26.data.catalog import library, save_user_module
from cim26.data.supsi_field import AVAILABLE_MONTHS, FLAGS, REASONS, QualityConfig, load_field, monthly_summary
from cim26.data.supsi_lab import check_lab, load_supsi_module_json, read_iec61853_xlsx, supsi_module_spec
from cim26.experiment.config import ExperimentConfig
from cim26.experiment.metrics import common_support
from cim26.experiment.run_store import active_run, import_zip, launch_background, list_runs, read_status, zip_run
from cim26.experiment.runner import STAGES, quality_with_anomalies
from cim26.paths import RUNS_DIR
from cim26.pvcore.models import MODEL_IDS, MODEL_INFO, availability
from cim26.pvcore.module import KIND_EXPERIMENTAL, ModuleSpec, validate_module
from cim26.pvcore.sdm import STATUS_LABELS, SDMReference
from cim26.pvcore.thermal import THERMAL_STRATEGIES
from cim26.simulate import iv_curve_array, simulate, thermal_options

STATIC = Path(__file__).resolve().parent / "static"
_LOCK = threading.RLock()
_CACHE: dict = {}
RUN_FILES = {"predictions", "metrics_energy", "metrics_daily", "metrics_monthly", "residual_bins", "bootstrap_ci",
             "bootstrap_paired", "benchmark_runs", "benchmark_summary", "time_ratios", "determinism", "pareto",
             "marginal", "sensitivity", "quality_sensitivity", "anomaly_summary", "statistics", "input_quality",
             "quality_summary", "calibration_residuals", "benchmark_tracemalloc"}


class ApiError(Exception):
    def __init__(self, msg, code=400):
        super().__init__(msg)
        self.code = code


def recs(df: pd.DataFrame) -> list:
    return json.loads(df.to_json(orient="records", date_format="iso", double_precision=10))


def clean(obj):
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return clean(obj.tolist())
    if isinstance(obj, (np.floating,)):
        return clean(float(obj))
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, (pd.Timestamp,)):
        return obj.isoformat()
    return obj


def cached(key, fn):
    with _LOCK:
        if key not in _CACHE:
            _CACHE[key] = fn()
        return _CACHE[key]


def lib() -> dict[str, ModuleSpec]:
    return cached("lib", library)


def field() -> pd.DataFrame:
    return cached("field", lambda: load_field()[0])


def lab():
    return cached("lab", read_iec61853_xlsx)


def sdm_ref(module_id: str) -> SDMReference | None:
    d = _CACHE.get(("sdm", module_id))
    return SDMReference.from_dict(d["reference"]) if d else None


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------
def h_meta(q, body):
    return {"version": __version__,
            "models": [{"id": m, "name": MODEL_INFO[m].name, "short": MODEL_INFO[m].short, "color": MODEL_INFO[m].color,
                        "equation": MODEL_INFO[m].equation, "requirements": MODEL_INFO[m].requirements,
                        "temperature": MODEL_INFO[m].temperature_input} for m in MODEL_IDS],
            "status_labels": STATUS_LABELS, "thermal": THERMAL_STRATEGIES, "synthetic_profiles": W.SYNTHETIC_PROFILES,
            "seasons": W.SEASONS, "months": list(AVAILABLE_MONTHS), "anomalies": ANOMALIES, "reasons": REASONS,
            "flags": FLAGS, "stages": STAGES, "delta_t_default": SANDIA_DELTA_T_DEFAULT_C}


def _module_payload(m: ModuleSpec) -> dict:
    ref = sdm_ref(m.id)
    av = {k: availability(k, m, ref if k == "M4" else None).__dict__ for k in MODEL_IDS}
    method = "multiponto" if m.kind == KIND_EXPERIMENTAL else ("classico" if not m.classical_sdm_inputs_missing() else None)
    if not av["M4"]["available"] and method:
        av["M4"]["reason"] = "Calibrável: estime os parâmetros SDM."
        av["M4"]["calibratable"] = True
    return {**m.to_dict(), "label": m.label, "area_m2": m.area_m2, "sdm_method": method,
            "sdm_missing": m.classical_sdm_inputs_missing(), "sdm_ready": ref is not None,
            "saved_calibrations": len(list_calibrations(m.id)), "availability": av}


def h_library(q, body):
    return [_module_payload(m) for m in lib().values()]


def h_module_validate(q, body):
    m = ModuleSpec.from_dict({**body, "kind": "usuario"})
    return {"issues": [{"level": l, "msg": s} for l, s in validate_module(m)]}


def h_module_save(q, body):
    m = ModuleSpec.from_dict({**body, "kind": "usuario"})
    path = save_user_module(m)
    _CACHE.pop("lib", None)
    return {"ok": True, "id": m.id, "path": path.name}


def h_sdm_estimate(q, body):
    m = lib().get(body.get("module_id"))
    if m is None:
        raise ApiError("Módulo desconhecido.")
    if body.get("load_saved"):
        saved = list_calibrations(m.id)
        if not saved:
            raise ApiError("Nenhuma identificação salva para este módulo.")
        d = {"method": saved[0]["sdm_reference"]["method"], "reference": saved[0]["sdm_reference"], "report": saved[0]["report"]}
    elif m.kind == KIND_EXPERIMENTAL:
        ref, rep = calibrate_multipoint(lab().long, m)
        d = {"method": "multiponto", "reference": ref.to_dict(), "report": rep.to_json_dict()}
    else:
        ref, rep = calibrate_classical(m)
        d = {"method": "classico", "reference": ref.to_dict(), "report": rep.to_dict()}
    _CACHE[("sdm", m.id)] = _jsonable(d)
    if body.get("save"):
        save_calibration(SDMReference.from_dict(d["reference"]), d["report"], m.id)
    return _CACHE[("sdm", m.id)]


def h_sdm_save(q, body):
    d = _CACHE.get(("sdm", body.get("module_id")))
    if not d:
        raise ApiError("Estime os parâmetros antes de salvar.")
    p = save_calibration(SDMReference.from_dict(d["reference"]), d["report"], body["module_id"])
    return {"ok": True, "file": p.name}


def h_supsi_days(q, body):
    def build():
        f = field()
        d = f.assign(day=f["timestamp"].dt.date.astype(str))
        g = d.groupby("day").agg(n=("row_id", "size"), g_max=("g_poa_Wm2", "max"),
                                 h=("g_poa_Wm2", lambda s: float(np.nansum(s)) * 5 / 60 / 1000),
                                 t_max=("t_module_C", "max"))
        return recs(g.reset_index())
    return cached("days", build)


def h_csv_inspect(q, body):
    raw = pd.read_csv(io.StringIO(body.get("text", "")), sep=None, engine="python")
    return {"columns": list(map(str, raw.columns)), "rows": len(raw), "preview": recs(raw.head(6).astype(str))}


def _weather(spec: dict) -> W.WeatherSeries:
    src = spec.get("source", "supsi")
    if src == "supsi":
        days = spec.get("days") or ["2019-05-14"]
        return W.supsi_days(field(), days)
    if src == "csv":
        raw = pd.read_csv(io.StringIO(spec["text"]), sep=None, engine="python")
        return W.from_dataframe(raw, spec["ts_col"], spec["g_col"], spec.get("g_kind", "POA"),
                                horizontal=bool(spec.get("horizontal")), temp_col=spec.get("t_col") or None,
                                temp_kind=spec.get("t_kind") or None, wind_col=spec.get("w_col") or None)
    if src == "synthetic":
        return W.synthetic(spec.get("profile", W.SYNTHETIC_PROFILES[1]), spec.get("season", W.SEASONS[0]),
                           duration_min=int(spec.get("duration_min", 1440)), step_min=int(spec.get("step_min", 5)),
                           g_peak=float(spec["g_peak"]) if spec.get("g_peak") else None, seed=int(spec.get("seed", 42)))
    if src == "manual":
        return W.manual(float(spec.get("g", 800)), float(spec.get("t", 25)), spec.get("t_kind", "Tamb"),
                        duration_min=int(spec.get("duration_min", 60)), step_min=int(spec.get("step_min", 1)),
                        wind=float(spec["wind"]) if spec.get("wind") not in (None, "") else None)
    raise ApiError(f"Fonte meteorológica desconhecida: {src}")


def h_simulate(q, body):
    m = lib().get(body.get("module_id"))
    if m is None:
        raise ApiError("Módulo desconhecido.")
    try:
        wx = _weather(body.get("weather", {}))
    except ValueError as exc:
        raise ApiError(str(exc))
    opts = thermal_options(wx, m)
    usable = [o[0] for o in opts if o[2]]
    th = body.get("thermal", {})
    strategy = th.get("strategy") if th.get("strategy") in usable else (usable[0] if usable else None)
    dT = float(th.get("delta_t", SANDIA_DELTA_T_DEFAULT_C))
    ns, npar = int(body.get("array", {}).get("ns", 1)), int(body.get("array", {}).get("np", 1))
    res = simulate(m, wx, MODEL_IDS, sdm_ref(m.id), strategy, dT, ns, npar)
    tab = res.table
    out = {"timestamp": tab["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S").tolist(),
           "g_poa": tab["g_poa_Wm2"].tolist(), "t_cell": tab["t_cell_C"].tolist(), "t_module": tab["t_module_C"].tolist(),
           "t_amb": None if wx.t_amb_C is None else list(wx.t_amb_C),
           "P": {k: tab[f"P_{k}_arranjo_W"].tolist() for k in MODEL_IDS if f"P_{k}_arranjo_W" in tab},
           "status": {k: {STATUS_LABELS.get(int(s), str(s)): int(n) for s, n in tab[f"status_{k}"].value_counts().items()}
                      for k in MODEL_IDS if f"status_{k}" in tab}}
    if body.get("weather", {}).get("source") == "supsi" and m.kind == KIND_EXPERIMENTAL:
        # medida só é comparável quando o módulo simulado É o módulo SUPSI medido
        f = field()
        days = body["weather"].get("days") or ["2019-05-14"]
        d = f[f["timestamp"].dt.date.astype(str).isin(days)].sort_values("row_id")
        out["P_obs"] = (d["p_mpp_measured_W"] * ns * npar).tolist()
    return clean({"series": out, "kpis": recs(res.kpis.assign(instante_P_max=res.kpis.instante_P_max.astype(str))),
                  "availability": {k: v.__dict__ for k, v in res.statuses.items()},
                  "provenance": res.provenance, "notes": res.notes, "weather": {"origin": wx.origin,
                  "description": wx.description, "n": len(wx), "temperatures": wx.temperature_kinds()},
                  "thermal": {"options": [{"id": o[0], "label": o[1], "ok": o[2], "why": o[3]} for o in opts],
                              "used": strategy, "delta_t": dT},
                  "array": {"ns": ns, "np": npar, "p_inst_W": m.p_stc_W * ns * npar}})


def h_iv(q, body):
    ref = sdm_ref(body.get("module_id"))
    if ref is None:
        raise ApiError("SDM sem parâmetros: estime primeiro.")
    V, I, P, mpp = iv_curve_array(ref, float(body["g"]), float(body["t_cell"]), int(body.get("ns", 1)), int(body.get("np", 1)), 160)
    return clean({"V": V, "I": I, "P": P, "mpp": mpp})


def _q(q, k, default):
    return q.get(k, [default])[0]


def _art_quality(q):
    months = tuple(sorted(_q(q, "months", ",".join(AVAILABLE_MONTHS)).split(",")))
    g = float(_q(q, "g", 100))
    strategy = _q(q, "strategy", "A_tmod_medida")
    policy = _q(q, "policy", "sinalizar")
    key = ("quality", months, g, strategy, policy)

    def build():
        m = supsi_module_spec()
        df, _ = load_field(months)
        cfg = ExperimentConfig(months=months, g_threshold_Wm2=g, thermal_strategy=strategy, anomaly_policy=policy)
        return quality_with_anomalies(df, QualityConfig(g_threshold_Wm2=g, require_ambient=strategy == "B_faiman",
                                                        voc_stc_V=m.v_oc_V, p_stc_W=m.p_stc_W), m, cfg)
    return cached(key, build)


def h_art_quality(q, body):
    qq = _art_quality(q)
    gap = float(_q(q, "gap", 7.5))
    days = qq.assign(day=qq["timestamp"].dt.date.astype(str)).groupby("day").agg(
        n=("row_id", "size"), n_el=("eligible", "sum"),
        n_anom=("anom_severidade", lambda s: int(s.isin(["erro", "suspeito"]).sum())))
    return clean({"monthly": recs(monthly_summary(qq, gap)), "anomalies": recs(anomaly_summary(qq)),
                  "days": recs(days.reset_index()), "isc_ratio_hist": np.histogram(qq.loc[qq.eligible, "isc_ratio"].dropna(),
                                                                                  bins=np.linspace(0.4, 1.6, 49))[0].tolist(),
                  "pr_hist": np.histogram(qq.loc[qq.eligible, "pr_inst"].dropna(), bins=np.linspace(0.2, 1.8, 49))[0].tolist()})


def h_art_day(q, body):
    qq = _art_quality(q)
    day = _q(q, "day", "2019-05-14")
    d = qq[qq["timestamp"].dt.date.astype(str) == day]
    cols = ["timestamp", "p_mpp_measured_W", "g_poa_Wm2", "ghi_Wm2", "t_module_C", "t_amb_C", "wind_ms", "isc_measured_A",
            "voc_measured_V", "eligible", "reasons", "anom_codes", "anom_severidade", "pr_inst", "isc_ratio", "source_file", "source_row"]
    return clean(recs(d[cols]))


def h_lab(q, body):
    L = lab()
    mats = {}
    for v in ("Pmp", "Isc", "Voc"):
        mt = L.matrix(v)
        mats[v] = {"G": mt.index.tolist(), "T": mt.columns.tolist(), "z": [[None if pd.isna(x) else x for x in r] for r in mt.values]}
    return clean({"matrices": mats, "coefficients": L.coefficients, "thermal": L.thermal, "header": L.header,
                  "checks": [{**c, "detail": str(c["detail"])} for c in check_lab(L, load_supsi_module_json())],
                  "audit": L.audit_missing_cells, "module": supsi_module_spec().to_dict()})


def h_cal_preview(q, body):
    def build():
        ref, rep = calibrate_multipoint(lab().long, supsi_module_spec())
        return _jsonable({"reference": ref.to_dict(), "report": rep.to_json_dict()})
    return clean(cached("calprev", build))


def h_runs(q, body):
    return clean(recs(list_runs(RUNS_DIR)))


def h_run_launch(q, body):
    cfg = ExperimentConfig.from_dict(body)
    cfg.validate()
    return {"run_id": launch_background(cfg.to_dict())}


def h_active(q, body):
    a = active_run(RUNS_DIR)
    if not a:
        return None
    return clean({**a, "status": read_status(RUNS_DIR / a["run_id"])})


def _read(rd: Path, name: str):
    p = rd / f"{name}.csv"
    return pd.read_csv(p, float_precision="round_trip", low_memory=False) if p.exists() else None


def h_run(q, body, run_id):
    rd = RUNS_DIR / run_id
    if not (rd / "config.json").exists():
        raise ApiError("Execução não encontrada.", 404)
    st = read_status(rd)
    out = {"run_id": run_id, "status": st, "config": json.loads((rd / "config.json").read_text(encoding="utf-8"))}
    if st.get("estado") != "concluido":
        return clean(out)
    for k in ("metrics_energy", "metrics_daily", "metrics_monthly", "residual_bins", "bootstrap_ci", "bootstrap_paired",
              "benchmark_summary", "time_ratios", "determinism", "pareto", "marginal", "sensitivity", "quality_sensitivity",
              "anomaly_summary", "benchmark_tracemalloc", "quality_summary"):
        df = _read(rd, k)
        out[k] = None if df is None else recs(df)
    br = _read(rd, "benchmark_runs")
    out["benchmark_runs"] = recs(br.drop(columns=["erro", "politica_gc", "pred_sha256_16"], errors="ignore"))
    for j in ("narrative", "metadata"):
        p = rd / f"{j}.json"
        out[j] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    cal = json.loads((rd / "calibration.json").read_text(encoding="utf-8"))
    rep = cal["report"]
    out["calibration"] = {"reference": cal["sdm_reference"], "lab_metrics": rep["lab_metrics"],
                          "implied": rep.get("implied_coefficients"), "condition": rep["condition_number"],
                          "stc": rep["stc_check"], "assumptions": rep["assumptions"]}
    pred = _read(rd, "predictions")
    out["days"] = sorted(pd.to_datetime(pred["timestamp"]).dt.date.astype(str).unique().tolist())
    sample = pred.sample(min(3000, len(pred)), random_state=0)
    out["scatter"] = {"obs": sample["P_obs_W"].tolist(), **{m: sample[f"P_{m}_W"].tolist() for m in MODEL_IDS},
                      "g": sample["g_poa_Wm2"].tolist(),
                      "sev": sample.get("anom_severidade", pd.Series("", index=sample.index)).fillna("").tolist()}
    edges = np.linspace(-120, 120, 97)
    out["residual_hist"] = {"edges": edges.tolist(),
                            **{m: np.histogram(pred[f"res_{m}_W"].dropna(), bins=edges)[0].tolist() for m in MODEL_IDS}}
    return clean(out)


def h_run_series(q, body, run_id):
    rd = RUNS_DIR / run_id
    pred = _read(rd, "predictions")
    pred["timestamp"] = pd.to_datetime(pred["timestamp"])
    pred = pred.sort_values("row_id").reset_index(drop=True)
    cfg = json.loads((rd / "config.json").read_text(encoding="utf-8"))
    inter, pairs = common_support(pred, cfg["max_gap_min"])
    pred["pair_next"] = np.r_[pairs, False]
    a, b = _q(q, "start", None), _q(q, "end", None)
    dd = pred["timestamp"].dt.date.astype(str)
    sel = pred[(dd >= (a or dd.min())) & (dd <= (b or a or dd.max()))]
    cols = ["timestamp", "P_obs_W"] + [f"P_{m}_W" for m in MODEL_IDS] + ["g_poa_Wm2", "t_module_C", "t_cell_C", "pair_next"]
    cols += [c for c in ("anom_codes", "anom_severidade", "transitorio", "isc_ratio") if c in sel]
    return clean(recs(sel[cols]))


def h_run_import(q, body_bytes):
    p = import_zip(body_bytes, RUNS_DIR)
    return {"ok": True, "run_id": p.name}


ROUTES_GET = {"/api/meta": h_meta, "/api/library": h_library, "/api/supsi/days": h_supsi_days,
              "/api/artigo/quality": h_art_quality, "/api/artigo/day": h_art_day, "/api/lab": h_lab,
              "/api/runs": h_runs, "/api/runs/active": h_active}
ROUTES_POST = {"/api/modules/validate": h_module_validate, "/api/modules": h_module_save,
               "/api/sdm/estimate": h_sdm_estimate, "/api/sdm/save": h_sdm_save, "/api/csv/inspect": h_csv_inspect,
               "/api/simulate": h_simulate, "/api/iv": h_iv, "/api/calibration/preview": h_cal_preview,
               "/api/runs": h_run_launch}


class Handler(BaseHTTPRequestHandler):
    server_version = "CIM26/" + __version__

    def log_message(self, fmt, *args):  # silencioso
        pass

    def _send(self, code, data: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store" if ctype.startswith("application/json") else "max-age=3600")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

    def _err(self, exc):
        code = getattr(exc, "code", 500) if isinstance(exc, ApiError) else 500
        msg = str(exc) if isinstance(exc, (ApiError, ValueError, KeyError, FileExistsError, RuntimeError)) else f"{type(exc).__name__}: {exc}"
        self._json({"error": msg, "trace": traceback.format_exc()[-1500:] if code == 500 else None}, code)

    def do_GET(self):
        u = urlparse(self.path)
        path, q = unquote(u.path), parse_qs(u.query)
        try:
            if path in ROUTES_GET:
                return self._json(ROUTES_GET[path](q, None))
            if path.startswith("/api/runs/"):
                parts = path.split("/")[3:]
                rid = parts[0]
                if len(parts) == 1:
                    return self._json(h_run(q, None, rid))
                if parts[1] == "series":
                    return self._json(h_run_series(q, None, rid))
                if parts[1] == "zip":
                    return self._send(200, zip_run(RUNS_DIR / rid), "application/zip",
                                      {"Content-Disposition": f'attachment; filename="{rid}.zip"'})
                if parts[1] == "file" and parts[2].removesuffix(".csv") in RUN_FILES:
                    p = RUNS_DIR / rid / f"{parts[2].removesuffix('.csv')}.csv"
                    return self._send(200, p.read_bytes(), "text/csv; charset=utf-8",
                                      {"Content-Disposition": f'attachment; filename="{p.name}"'})
                if parts[1] == "discussion":
                    return self._send(200, (RUNS_DIR / rid / "DISCUSSAO.md").read_bytes(), "text/markdown; charset=utf-8",
                                      {"Content-Disposition": 'attachment; filename="DISCUSSAO.md"'})
                if parts[1] == "figure":
                    p = RUNS_DIR / rid / "figures" / Path(parts[2]).name
                    return self._send(200, p.read_bytes(), mimetypes.guess_type(p.name)[0] or "image/svg+xml")
                raise ApiError("Rota desconhecida.", 404)
            if path == "/vendor/plotly.min.js":
                import plotly
                p = Path(plotly.__file__).parent / "package_data" / "plotly.min.js"
                return self._send(200, p.read_bytes(), "application/javascript")
            rel = "index.html" if path in ("/", "/index.html") or not path.startswith("/static/") else path[len("/static/"):]
            p = (STATIC / rel).resolve()
            if STATIC.resolve() not in p.parents and p != STATIC.resolve() / "index.html" or not p.exists():
                raise ApiError("Não encontrado.", 404)
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if p.suffix == ".js":
                ctype = "application/javascript"
            return self._send(200, p.read_bytes(), ctype)
        except Exception as exc:
            self._err(exc)

    def do_POST(self):
        u = urlparse(self.path)
        path = unquote(u.path)
        n = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(n) if n else b""
        try:
            if path == "/api/runs/import":
                return self._json(h_run_import(None, raw))
            if path not in ROUTES_POST:
                raise ApiError("Rota desconhecida.", 404)
            body = json.loads(raw.decode("utf-8")) if raw else {}
            return self._json(ROUTES_POST[path](parse_qs(u.query), body))
        except Exception as exc:
            self._err(exc)


def make_server(host="127.0.0.1", port=8765) -> ThreadingHTTPServer:
    mimetypes.add_type("font/woff2", ".woff2")
    mimetypes.add_type("text/css", ".css")
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv
