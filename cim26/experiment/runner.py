"""Orquestração de um experimento completo do modo Artigo (sem Streamlit).

Etapas (tempos registrados SEPARADAMENTE em ``metadata.json``):
  leitura → qualidade → calibração (laboratório) → preparação → previsões de
  referência → sensibilidade → benchmark (subprocesso isolado) → análise →
  figuras → metadados. Falhas preservam as saídas parciais e o erro explícito.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from .. import __version__
from ..calibration.multipoint import MultipointConfig, calibrate_multipoint
from ..calibration.store import _jsonable
from ..data.supsi_field import QualityConfig, assess_quality, interval_report, load_field, monthly_summary
from ..data.supsi_lab import check_lab, load_supsi_module_json, read_iec61853_xlsx, sha256_file, supsi_module_spec
from ..paths import PROJECT_ROOT, RUNS_DIR, SUPSI_MODULE_JSON
from ..pvcore.models import MODEL_IDS, MODEL_INFO, predict, prepare
from ..pvcore.thermal import build_conditions
from .analysis import analyze_run
from .config import ExperimentConfig
from .metrics import energy_metrics
from .run_store import acquire_lock, release_lock

STAGES = ["leitura", "qualidade", "calibração", "preparação", "previsões", "sensibilidade",
          "benchmark", "análise", "figuras", "metadados"]


class Status:
    def __init__(self, run_dir: Path, cb: Optional[Callable[[dict], None]] = None):
        self.path = run_dir / "status.json"
        self.cb = cb
        self.state = {"estado": "executando", "etapa": None, "etapa_idx": 0, "n_etapas": len(STAGES),
                      "pid": os.getpid(), "inicio_utc": _now(), "mensagem": "", "benchmark": {}}
        self.write()

    def write(self):
        self.state["atualizado_utc"] = _now()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        os.replace(tmp, self.path)
        if self.cb:
            self.cb(dict(self.state))

    def stage(self, name: str, msg: str = ""):
        self.state.update(etapa=name, etapa_idx=STAGES.index(name) + 1, mensagem=msg)
        self.write()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id(cfg: ExperimentConfig) -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}_{cfg.digest()}"


def _conditions(cfg: ExperimentConfig, d: pd.DataFrame, module, delta_t: float):
    if cfg.thermal_strategy == "A_tmod_medida":
        return build_conditions("A_tmod_medida", d["g_poa_Wm2"].to_numpy(), t_module_C=d["t_module_C"].to_numpy(),
                                t_amb_C=d["t_amb_C"].to_numpy(), wind_ms=d["wind_ms"].to_numpy(), delta_t_C=delta_t)
    return build_conditions("B_faiman", d["g_poa_Wm2"].to_numpy(), t_amb_C=d["t_amb_C"].to_numpy(),
                            wind_ms=d["wind_ms"].to_numpy(), u0=module.u0_W_m2K, u1=module.u1_W_s_m3K,
                            delta_t_C=delta_t)


def _write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(_jsonable(obj), ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def run_experiment(cfg: ExperimentConfig, runs_dir: Path = RUNS_DIR, run_id: str | None = None,
                   progress: Optional[Callable[[dict], None]] = None, use_lock: bool = True) -> Path:
    cfg.validate()
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = run_id or new_run_id(cfg)
    rd = runs_dir / run_id
    (rd / "figures").mkdir(parents=True, exist_ok=True)
    if use_lock:
        acquire_lock(runs_dir, run_id)
    st = Status(rd, progress)
    stage_s: dict[str, float] = {}
    _write_json(rd / "config.json", cfg.to_dict())
    try:
        # 1 leitura -------------------------------------------------------------
        st.stage("leitura", "lendo CSV de campo e XLSX de laboratório")
        t = time.perf_counter()
        field, field_hashes = load_field(cfg.months)
        lab = read_iec61853_xlsx()
        module = supsi_module_spec()
        lab_checks = check_lab(lab, load_supsi_module_json())
        stage_s["leitura_s"] = time.perf_counter() - t
        _write_json(rd / "module.json", module.to_dict())

        # 2 qualidade -----------------------------------------------------------
        st.stage("qualidade", "máscara de elegibilidade comum")
        t = time.perf_counter()
        qcfg = QualityConfig(g_threshold_Wm2=cfg.g_threshold_Wm2, g_max_Wm2=cfg.g_max_Wm2,
                             t_module_range_C=tuple(cfg.t_module_range_C),
                             require_ambient=cfg.thermal_strategy == "B_faiman",
                             voc_stc_V=module.v_oc_V, p_stc_W=module.p_stc_W)
        q = assess_quality(field, qcfg)
        q.to_csv(rd / "input_quality.csv", index=False)
        monthly_summary(q, cfg.max_gap_min).to_csv(rd / "quality_summary.csv", index=False)
        interval_report(q).to_csv(rd / "intervals.csv", index=False)
        stage_s["qualidade_s"] = time.perf_counter() - t

        # 3 calibração (somente laboratório) -------------------------------------
        st.stage("calibração", "SDM multiponto com 66 medições de laboratório")
        t = time.perf_counter()
        sdm_ref, cal_rep = calibrate_multipoint(lab.long, module, MultipointConfig(**cfg.calibration))
        stage_s["calibration_s"] = time.perf_counter() - t
        _write_json(rd / "calibration.json", {"sdm_reference": sdm_ref.to_dict(), "report": cal_rep.to_json_dict(),
                                               "lab_checks": lab_checks, "lab_coefficients": lab.coefficients,
                                               "lab_thermal": lab.thermal, "lab_sentinel_audit": lab.audit_missing_cells})
        cal_rep.residuals.to_csv(rd / "calibration_residuals.csv", index=False)

        # 4 preparação ------------------------------------------------------------
        st.stage("preparação", "condições comuns e parâmetros dos 4 modelos")
        t = time.perf_counter()
        el = q[q["eligible"]].sort_values("row_id").reset_index(drop=True)
        cond = _conditions(cfg, el, module, cfg.delta_t_C)
        params = {m: prepare(m, module, sdm_ref, cfg.huld_set) for m in MODEL_IDS}
        stage_s["prepare_s"] = time.perf_counter() - t
        _write_json(rd / "params.json", {m: p.to_dict() for m, p in params.items()})
        _write_json(rd / "conditions_provenance.json", cond.provenance)

        # 5 previsões de referência (bloco A) ------------------------------------
        st.stage("previsões", "passe de referência dos 4 modelos (fora do benchmark)")
        t = time.perf_counter()
        outs = {m: predict(m, cond, params[m], mode=cfg.execution_mode) for m in MODEL_IDS}
        stage_s["reference_predictions_s"] = time.perf_counter() - t
        pred = pd.DataFrame({
            "row_id": el["row_id"], "source_file": el["source_file"], "source_row": el["source_row"],
            "timestamp": el["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S"),
            "g_poa_Wm2": el["g_poa_Wm2"], "t_module_C": cond.t_module_C, "t_cell_C": cond.t_cell_C,
            "t_amb_C": el["t_amb_C"], "wind_ms": el["wind_ms"], "P_obs_W": el["p_mpp_measured_W"],
        })
        for m in MODEL_IDS:
            pred[f"P_{m}_W"] = outs[m].p_mpp_W
            pred[f"res_{m}_W"] = outs[m].p_mpp_W - pred["P_obs_W"].to_numpy()
            pred[f"status_{m}"] = outs[m].status
        for k, v in outs["M4"].extra.items():
            pred[f"M4_{k}"] = v
        pred["Voc_obs_V"] = el["voc_measured_V"].to_numpy()
        pred["Isc_obs_A"] = el["isc_measured_A"].to_numpy()
        pred.to_csv(rd / "predictions.csv", index=False)
        model_diag = {m: o.diagnostics for m, o in outs.items()}

        # 6 sensibilidade -----------------------------------------------------------
        if cfg.sensitivity_enabled:
            st.stage("sensibilidade", "ΔT e limiar de irradiância (somente métricas energéticas)")
            t = time.perf_counter()
            sensitivity(cfg, q, field, module, params, pred, rd)
            stage_s["sensitivity_s"] = time.perf_counter() - t

        # 7 benchmark ---------------------------------------------------------------
        st.stage("benchmark", f"{cfg.repetitions} rodadas × 4 modelos, processo isolado")
        t = time.perf_counter()
        np.savez(rd / "bench_input.npz", g_poa_Wm2=cond.g_poa_Wm2, t_module_C=cond.t_module_C,
                 t_cell_C=cond.t_cell_C, **{f"ref_{m}": outs[m].p_mpp_W for m in MODEL_IDS})
        _write_json(rd / "bench_spec.json", {"params": {m: p.to_dict() for m, p in params.items()},
                                             "repetitions": cfg.repetitions, "order_mode": cfg.order_mode,
                                             "seed": cfg.seed, "execution_mode": cfg.execution_mode,
                                             "warmup_samples": cfg.warmup_samples,
                                             "scaling_sizes": list(cfg.scaling_sizes) if cfg.scaling_enabled else [],
                                             "tracemalloc_pass": cfg.tracemalloc_pass})
        run_benchmark_subprocess(rd, st)
        stage_s["benchmark_wall_s"] = time.perf_counter() - t
        (rd / "bench_input.npz").unlink(missing_ok=True)   # reconstruível de predictions.csv

        # 8 análise -----------------------------------------------------------------
        st.stage("análise", "métricas, bootstrap por dias, Pareto")
        t = time.perf_counter()
        analyze_run(rd)
        stage_s["analysis_s"] = time.perf_counter() - t

        # 9 figuras -----------------------------------------------------------------
        st.stage("figuras", "SVG/PNG para lâminas e LaTeX")
        t = time.perf_counter()
        from ..report.figures import make_all_figures
        make_all_figures(rd)
        stage_s["figures_s"] = time.perf_counter() - t

        # 10 metadados ----------------------------------------------------------------
        st.stage("metadados", "hashes, ambiente e README_RUN")
        write_metadata(rd, cfg, field_hashes, lab, stage_s, model_diag, cal_rep, q)
        st.state.update(estado="concluido", mensagem="experimento concluído")
        st.write()
    except Exception:
        st.state.update(estado="falhou", mensagem="erro — ver traceback", traceback=traceback.format_exc())
        st.write()
        _write_json(rd / "stage_times_partial.json", stage_s)
        raise
    finally:
        if use_lock:
            release_lock(runs_dir, run_id)
    return rd


def sensitivity(cfg, q, field, module, params, pred, rd: Path) -> None:
    rows = []
    base = pred.copy()
    base["timestamp"] = pd.to_datetime(base["timestamp"])
    el = q[q["eligible"]].sort_values("row_id").reset_index(drop=True)
    for dt in cfg.sensitivity_delta_t:
        if float(dt) == float(cfg.delta_t_C):
            df = base
        else:
            c = _conditions(cfg, el, module, float(dt))
            df = base.copy()
            for m in MODEL_IDS:
                if MODEL_INFO[m].temperature_input == "t_cell_C":
                    df[f"P_{m}_W"] = predict(m, c, params[m]).p_mpp_W
        em = energy_metrics(df, module.p_stc_W, cfg.max_gap_min)
        for r in em.itertuples():
            rows.append({"tipo": "delta_T_C", "valor": float(dt), "modelo": r.modelo, "N": r.N, "RMSE_W": r.RMSE_W,
                         "MAE_W": r.MAE_W, "MBE_W": r.MBE_W, "erro_energia_pct": r.erro_energia_pct,
                         "nota": "ΔT afeta apenas modelos com Tcell (M2, M4)"})
    for gth in cfg.sensitivity_g_thresholds:
        qq = assess_quality(field, QualityConfig(g_threshold_Wm2=float(gth), g_max_Wm2=cfg.g_max_Wm2,
                                                 t_module_range_C=tuple(cfg.t_module_range_C),
                                                 require_ambient=cfg.thermal_strategy == "B_faiman"))
        e2 = qq[qq["eligible"]].sort_values("row_id").reset_index(drop=True)
        c = _conditions(cfg, e2, module, cfg.delta_t_C)
        df = pd.DataFrame({"row_id": e2["row_id"], "timestamp": e2["timestamp"], "P_obs_W": e2["p_mpp_measured_W"]})
        known = base.set_index("row_id")
        for m in MODEL_IDS:
            p = np.full(len(e2), np.nan)
            hit = e2["row_id"].isin(known.index).to_numpy()
            p[hit] = known.loc[e2["row_id"][hit], f"P_{m}_W"].to_numpy()
            if (~hit).any():
                p[~hit] = predict(m, c.subset(np.where(~hit)[0]), params[m]).p_mpp_W
            df[f"P_{m}_W"] = p
        em = energy_metrics(df, module.p_stc_W, cfg.max_gap_min)
        for r in em.itertuples():
            rows.append({"tipo": "limiar_G_Wm2", "valor": float(gth), "modelo": r.modelo, "N": r.N,
                         "RMSE_W": r.RMSE_W, "MAE_W": r.MAE_W, "MBE_W": r.MBE_W,
                         "erro_energia_pct": r.erro_energia_pct,
                         "nota": "máscara reconstruída com o limiar; demais critérios iguais"})
    pd.DataFrame(rows).to_csv(rd / "sensitivity.csv", index=False)


def run_benchmark_subprocess(rd: Path, st: Status) -> None:
    env = dict(os.environ)
    for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
        env[k] = "1"
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen([sys.executable, "-m", "cim26.benchmark.worker", str(rd)], cwd=PROJECT_ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    last = 0.0
    for line in proc.stdout:
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("evt") == "error":
            st.state["benchmark"] = {"erro": ev.get("traceback")}
        elif ev.get("evt") in ("progress", "done"):
            st.state["benchmark"] = ev
            if time.time() - last > 0.25 or ev.get("evt") == "done":
                st.write()
                last = time.time()
    err = proc.stderr.read()
    rc = proc.wait()
    (rd / "benchmark_worker.log").write_text(err or "", encoding="utf-8")
    if rc != 0:
        raise RuntimeError(f"benchmark terminou com código {rc}: {st.state['benchmark'].get('erro', err)[-2000:]}")


def write_metadata(rd, cfg, field_hashes, lab, stage_s, model_diag, cal_rep, q) -> None:
    from ..benchmark.envinfo import environment_info, pip_freeze
    env = environment_info(PROJECT_ROOT)
    bench_env_p = rd / "benchmark_env.json"
    bench_env = json.loads(bench_env_p.read_text(encoding="utf-8")) if bench_env_p.exists() else {}
    (rd / "environment_freeze.txt").write_text(pip_freeze(), encoding="utf-8")
    meta = {
        "app": "CIM26", "versao_app": __version__, "gerado_utc": _now(),
        "entradas_sha256": {**field_hashes, "IEC61853_1-2.xlsx": lab.source_sha256,
                            "SUPSI_module_experimental.json": sha256_file(SUPSI_MODULE_JSON)},
        "ambiente_orquestrador": env, "ambiente_benchmark_isolado": bench_env,
        "tempos_por_etapa_s": stage_s,
        "nota_tempos": "calibration_s, leitura, prepare_s e figuras NÃO compõem o tempo do modelo (compute_s).",
        "diagnosticos_modelos_passe_referencia": model_diag,
        "calibracao": {"metodo": "multiponto SUPSI (laboratório)", "custo": cal_rep.best_cost,
                       "condicao_jacobiano": cal_rep.condition_number, "sucesso": cal_rep.success},
        "amostras": {"total": int(len(q)), "elegiveis": int(q["eligible"].sum())},
        "limites": [
            "Rodadas repetidas de software não são replicações físicas independentes.",
            "ΔT célula–módulo = hipótese (Sandia eq. 23), não medida; ver sensitivity.csv.",
            "M3 usa coeficientes tecnológicos genéricos (PVGIS c-Si CURRENT), não calibrados para o módulo.",
            "M4 calibrado com 66 medições de laboratório; M2 usa γ medido; assimetrias de parametrização declaradas.",
            "Mesma POA medida para os 4 modelos; perdas ópticas (AOI, espectro) não modeladas em nenhum.",
            "Tempos medidos neste PC; não extrapolar para hardware embarcado.",
            "Energia parcial: somente pares válidos; não é energia semestral completa.",
            "Resultados de uma execução de verificação são diagnóstico de engenharia, não conclusões publicáveis.",
        ],
    }
    _write_json(rd / "metadata.json", meta)
    from ..report.export import write_readme_run
    write_readme_run(rd, cfg, meta)
