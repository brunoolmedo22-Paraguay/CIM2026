"""Análise de uma execução a partir dos arquivos exportados (sem reexecutar modelos).

``analyze_run(run_dir)`` reconstrói métricas, estatísticas, Pareto e o
``statistics.csv`` consolidado exclusivamente de ``predictions.csv``,
``benchmark_runs.csv`` e ``config.json``. Usado tanto ao final do experimento
quanto ao reabrir/importar uma execução.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..stats.bootstrap import day_block_bootstrap
from ..stats.pareto import marginal_improvement, pareto_table
from ..stats.timing import paired_time_ratios, timing_summary
from .config import ExperimentConfig
from .metrics import binned_residuals, energy_metrics, grouped_metrics, quality_sensitivity
from ..data.anomalies import AnomalyConfig, anomaly_summary, detect_anomalies


def read_predictions(run_dir: Path) -> pd.DataFrame:
    pred = pd.read_csv(Path(run_dir) / "predictions.csv", float_precision="round_trip")
    pred["timestamp"] = pd.to_datetime(pred["timestamp"])
    return pred


def analyze_run(run_dir: Path, write: bool = True) -> dict:
    run_dir = Path(run_dir)
    cfg = ExperimentConfig.from_dict(json.loads((run_dir / "config.json").read_text(encoding="utf-8")))
    meta_p = run_dir / "calibration.json"
    p_stc = json.loads((run_dir / "module.json").read_text(encoding="utf-8"))["p_stc_W"]
    pred = read_predictions(run_dir)
    q = pd.read_csv(run_dir / "input_quality.csv", low_memory=False)
    q["timestamp"] = pd.to_datetime(q["timestamp"])
    if "anom_codes" not in q:      # execuções antigas: anomalias recalculadas das colunas medidas
        mod = json.loads((run_dir / "module.json").read_text(encoding="utf-8"))
        q = pd.concat([q, detect_anomalies(q, mod["p_stc_W"], mod["i_sc_A"], mod["v_oc_V"],
                                           AnomalyConfig(**getattr(cfg, "anomaly", AnomalyConfig().to_dict())))], axis=1)
    if "anom_codes" not in pred:
        cols = ["anom_codes", "anom_severidade", "pr_inst", "isc_ratio", "transitorio"]
        pred = pred.merge(q[["row_id"] + cols], on="row_id", how="left")
    q["anom_codes"] = q["anom_codes"].fillna("")
    pred["anom_codes"] = pred["anom_codes"].fillna("")
    pred["anom_severidade"] = pred["anom_severidade"].fillna("")
    out: dict[str, pd.DataFrame] = {}
    out["metrics_energy"] = energy_metrics(pred, p_stc, cfg.max_gap_min)
    out["metrics_daily"] = grouped_metrics(pred, p_stc, "dia", cfg.max_gap_min)
    out["metrics_monthly"] = grouped_metrics(pred, p_stc, "mes", cfg.max_gap_min)
    out["residual_bins"] = binned_residuals(pred)
    ci, paired, samples = day_block_bootstrap(pred, cfg.max_gap_min, B=cfg.bootstrap_B, seed=cfg.seed)
    out["bootstrap_ci"], out["bootstrap_paired"] = ci, paired
    bench_p = run_dir / "benchmark_runs.csv"
    if bench_p.exists():
        runs = pd.read_csv(bench_p, float_precision="round_trip")
        out["benchmark_summary"] = timing_summary(runs, B=cfg.bootstrap_B, seed=cfg.seed)
        out["time_ratios"] = paired_time_ratios(runs, B=cfg.bootstrap_B, seed=cfg.seed)
        out["determinism"] = determinism_check(runs)
        out["pareto"], out["marginal"] = pareto_analysis(out["metrics_energy"], out["bootstrap_ci"],
                                                         out["benchmark_summary"], runs)
    out["quality_sensitivity"] = quality_sensitivity(pred, p_stc, cfg.max_gap_min)
    out["anomaly_summary"] = anomaly_summary(q)
    out["statistics"] = consolidate(out)
    if write:
        for k, df in out.items():
            df.to_csv(run_dir / f"{k}.csv", index=False)
        write_narrative(run_dir, out, cfg)
    del meta_p, samples
    return out


def determinism_check(runs: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (bs, m), d in runs.groupby(["batch_size", "modelo"]):
        rows.append({"batch_size": int(bs), "modelo": m, "rodadas": len(d),
                     "hashes_distintos": int(d["pred_sha256_16"].nunique()),
                     "max_abs_diff_ref_W": float(d["max_abs_diff_ref_W"].max()),
                     "previsoes_identicas_entre_rodadas": bool(d["pred_sha256_16"].nunique() == 1),
                     "nota": "modelo determinístico: rodadas repetidas não geram incerteza energética"})
    return pd.DataFrame(rows)


def pareto_analysis(metrics: pd.DataFrame, boot: pd.DataFrame, summary: pd.DataFrame, runs: pd.DataFrame):
    main_bs = int(runs.loc[runs.experimento == "principal", "batch_size"].iloc[0])
    s = summary[summary.batch_size == main_bs].set_index("modelo")
    b = boot[boot.metrica == "RMSE_W"].set_index("modelo")
    pts = []
    for m in metrics["modelo"]:
        pts.append({"modelo": m, "RMSE_W": float(metrics.set_index("modelo").loc[m, "RMSE_W"]),
                    "RMSE_lo": float(b.loc[m, "ic95_lo"]), "RMSE_hi": float(b.loc[m, "ic95_hi"]),
                    "tempo_us_amostra": float(s.loc[m, "mediana_por_amostra_us"]),
                    "tempo_lo": float(s.loc[m, "ic95_mediana_lo_s"]) / main_bs * 1e6,
                    "tempo_hi": float(s.loc[m, "ic95_mediana_hi_s"]) / main_bs * 1e6,
                    "memoria_MiB": float(s.loc[m].get("mediana_pico_rss_delta_MiB", np.nan))})
    pts = pd.DataFrame(pts)
    pt = pareto_table(pts, "tempo_us_amostra", "RMSE_W", "tempo_lo", "tempo_hi", "RMSE_lo", "RMSE_hi")
    pt["eixo"] = "tempo"
    pm = pareto_table(pts, "memoria_MiB", "RMSE_W")
    pm["eixo"] = "memoria"
    pareto = pd.concat([pt, pm], ignore_index=True)
    marg = pd.concat([marginal_improvement(pt, "tempo_us_amostra"), marginal_improvement(pm, "memoria_MiB")],
                     ignore_index=True)
    return pareto, marg


def consolidate(out: dict) -> pd.DataFrame:
    """statistics.csv: tabela longa (seção, modelo, grupo, métrica, valor, IC, unidade)."""
    rows = []

    def add(sec, df, group_col, metrics, unit):
        for r in df.itertuples(index=False):
            d = r._asdict()
            for mt in metrics:
                if mt in d:
                    rows.append({"secao": sec, "modelo": d.get("modelo"), "grupo": d.get(group_col, ""),
                                 "metrica": mt, "valor": d[mt], "ic95_lo": np.nan, "ic95_hi": np.nan, "unidade": unit})

    add("erro_por_dia", out["metrics_daily"], "dia", ["N", "RMSE_W", "MAE_W", "MBE_W"], "W")
    add("erro_por_mes", out["metrics_monthly"], "mes", ["N", "RMSE_W", "MAE_W", "MBE_W", "E_obs_kWh", "E_prev_kWh"], "W/kWh")
    rb = out["residual_bins"].copy()
    rb["grupo"] = rb["variavel"] + " " + rb["faixa"]
    add("residuos_por_faixa", rb, "grupo", ["N", "MBE_W", "RMSE_W"], "W")
    for r in out["bootstrap_ci"].itertuples(index=False):
        rows.append({"secao": "bootstrap_dias", "modelo": r.modelo, "grupo": f"B={r.B}; dias={r.dias}",
                     "metrica": r.metrica, "valor": r.estimativa, "ic95_lo": r.ic95_lo, "ic95_hi": r.ic95_hi,
                     "unidade": "%" if "pct" in r.metrica else "W"})
    for r in out["bootstrap_paired"].itertuples(index=False):
        rows.append({"secao": "bootstrap_pareado", "modelo": r.comparacao, "grupo": "", "metrica": r.metrica,
                     "valor": r.diferenca, "ic95_lo": r.ic95_lo, "ic95_hi": r.ic95_hi, "unidade": "W"})
    return pd.DataFrame(rows)


def write_narrative(run_dir: Path, out: dict | None = None, cfg: ExperimentConfig | None = None) -> list[dict]:
    """(Re)gera a discussão automática a partir dos arquivos da execução."""
    from ..report import narrative
    run_dir = Path(run_dir)
    if out is None:
        out = {}
        for k in ("metrics_energy", "metrics_daily", "metrics_monthly", "residual_bins", "bootstrap_ci", "bootstrap_paired",
                  "benchmark_summary", "time_ratios", "determinism", "pareto", "marginal", "sensitivity",
                  "quality_sensitivity", "anomaly_summary"):
            p = run_dir / f"{k}.csv"
            if p.exists():
                out[k] = pd.read_csv(p, float_precision="round_trip")
    if cfg is None:
        cfg = ExperimentConfig.from_dict(json.loads((run_dir / "config.json").read_text(encoding="utf-8")))
    if "sensitivity" not in out and (run_dir / "sensitivity.csv").exists():
        out["sensitivity"] = pd.read_csv(run_dir / "sensitivity.csv")
    meta_p = run_dir / "metadata.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    items = narrative.build(out, cfg.to_dict(), meta)
    narrative.write(run_dir, items)
    return items
