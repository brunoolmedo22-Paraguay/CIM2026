"""Estatística descritiva dos tempos do benchmark (por modelo e tamanho de lote).

As R rodadas de software NÃO são replicações físicas independentes: os
intervalos descrevem a variabilidade de execução observada nesta máquina.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

PCTS = (5, 25, 75, 95)


def _boot_ci_median(x: np.ndarray, B: int, rng: np.random.Generator) -> tuple[float, float]:
    if len(x) < 3:
        return (np.nan, np.nan)
    idx = rng.integers(0, len(x), size=(B, len(x)))
    med = np.median(x[idx], axis=1)
    return float(np.percentile(med, 2.5)), float(np.percentile(med, 97.5))


def timing_summary(runs: pd.DataFrame, B: int = 2000, seed: int = 0) -> pd.DataFrame:
    rows = []
    ok = runs[runs["falha"] == False]  # noqa: E712
    for (bs, m), d in runs.groupby(["batch_size", "modelo"], sort=True):
        x = ok[(ok.batch_size == bs) & (ok.modelo == m)].sort_values("rodada")
        t = x["compute_s"].to_numpy(float)
        ps = x["tempo_por_amostra_us"].to_numpy(float)
        rng = np.random.default_rng([seed, int(bs), int(m[1])])
        lo, hi = _boot_ci_median(t, B, rng)
        row = {"batch_size": int(bs), "modelo": m, "n_execucoes": len(d), "n_falhas": int(d["falha"].sum()),
               "media_s": float(np.mean(t)) if len(t) else np.nan,
               "mediana_s": float(np.median(t)) if len(t) else np.nan,
               "dp_s_ddof1": float(np.std(t, ddof=1)) if len(t) > 1 else np.nan,
               "min_s": float(np.min(t)) if len(t) else np.nan, "max_s": float(np.max(t)) if len(t) else np.nan}
        row["cv_pct"] = 100 * row["dp_s_ddof1"] / row["media_s"] if row["media_s"] and row["media_s"] > 0 else np.nan
        for p in PCTS:
            row[f"p{p}_s"] = float(np.percentile(t, p)) if len(t) else np.nan
        row.update({"ic95_mediana_lo_s": lo, "ic95_mediana_hi_s": hi,
                    "ic95_metodo": f"bootstrap percentil das rodadas (B={B}); instável com poucas rodadas",
                    "mediana_por_amostra_us": float(np.median(ps)) if len(ps) else np.nan,
                    "p95_por_amostra_us": float(np.percentile(ps, 95)) if len(ps) else np.nan})
        if "pico_rss_delta_MiB" in x:
            mem = x["pico_rss_delta_MiB"].to_numpy(float)
            row["mediana_pico_rss_delta_MiB"] = float(np.nanmedian(mem)) if np.isfinite(mem).any() else np.nan
            row["max_pico_rss_MiB"] = float(np.nanmax(x["pico_rss_MiB"])) if x["pico_rss_MiB"].notna().any() else np.nan
        if len(t) >= 3:
            rho, pval = spearmanr(x["rodada"], t)
            row["tendencia_spearman_rho"] = float(rho)
            row["tendencia_inclinacao_s_por_rodada"] = float(np.polyfit(x["rodada"], t, 1)[0])
        rows.append(row)
    return pd.DataFrame(rows)


def paired_time_ratios(runs: pd.DataFrame, reference: str = "M1", B: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Razão pareada por rodada t_modelo/t_referência (mesma rodada) com IC bootstrap."""
    ok = runs[runs["falha"] == False]  # noqa: E712
    rows = []
    for bs, d in ok.groupby("batch_size"):
        wide = d.pivot_table(index="rodada", columns="modelo", values="compute_s")
        if reference not in wide:
            continue
        for m in wide.columns:
            r = (wide[m] / wide[reference]).dropna().to_numpy()
            if len(r) == 0:
                continue
            rng = np.random.default_rng([seed, int(bs), 99, int(m[1])])
            lo, hi = _boot_ci_median(r, B, rng)
            rows.append({"batch_size": int(bs), "modelo": m, "referencia": reference,
                         "mediana_razao": float(np.median(r)), "ic95_lo": lo, "ic95_hi": hi, "n_rodadas": len(r)})
    return pd.DataFrame(rows)
