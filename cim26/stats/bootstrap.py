"""Bootstrap em blocos por DIA (dias completos reamostrados com reposição).

Amostras de 5 min não são independentes; o dia é a unidade de reamostragem.
Implementação vetorizada: contagens multinomiais B×D aplicadas a somas diárias.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from ..experiment.metrics import OBS, common_support, pcol
from ..pvcore.models import MODEL_IDS


def day_block_bootstrap(pred: pd.DataFrame, max_gap_min: float, B: int = 2000, seed: int = 0,
                        models=MODEL_IDS) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pred = pred.sort_values("row_id").reset_index(drop=True)
    inter, pairs = common_support(pred, max_gap_min, models)
    t = pd.to_datetime(pred["timestamp"])
    day = t.dt.date.astype(str).to_numpy()
    days = np.array(sorted(set(day[inter])))
    D = len(days)
    if D < 5:
        raise ValueError(f"Dias insuficientes para bootstrap por blocos ({D}).")
    di = {d: i for i, d in enumerate(days)}
    o = pred[OBS].to_numpy(float)
    dt_h = t.diff().dt.total_seconds().to_numpy()[1:] / 3600.0
    n_d = np.zeros(D)
    for i in np.where(inter)[0]:
        n_d[di[day[i]]] += 1
    S = {}
    E = {}
    seg_o = 0.5 * (o[:-1] + o[1:]) * dt_h
    E_obs = np.zeros(D)
    for j in np.where(pairs)[0]:
        E_obs[di[day[j]]] += seg_o[j] / 1000
    for m in models:
        e = pred[pcol(m)].to_numpy(float) - o
        s1 = np.zeros(D); s2 = np.zeros(D); sa = np.zeros(D)
        for i in np.where(inter)[0]:
            k = di[day[i]]
            s1[k] += e[i]; s2[k] += e[i] ** 2; sa[k] += abs(e[i])
        S[m] = (s1, s2, sa)
        p = pred[pcol(m)].to_numpy(float)
        seg = 0.5 * (p[:-1] + p[1:]) * dt_h
        Em = np.zeros(D)
        for j in np.where(pairs)[0]:
            Em[di[day[j]]] += seg[j] / 1000
        E[m] = Em
    rng = np.random.default_rng(seed)
    C = rng.multinomial(D, np.full(D, 1.0 / D), size=B).astype(float)   # B×D
    N = C @ n_d
    eo = C @ E_obs
    boot = {}
    for m in models:
        s1, s2, sa = S[m]
        boot[(m, "RMSE_W")] = np.sqrt((C @ s2) / N)
        boot[(m, "MAE_W")] = (C @ sa) / N
        boot[(m, "MBE_W")] = (C @ s1) / N
        boot[(m, "erro_energia_pct")] = 100 * (C @ E[m] - eo) / eo

    def point(m, k):
        s1, s2, sa = S[m]
        if k == "RMSE_W":
            return float(np.sqrt(s2.sum() / n_d.sum()))
        if k == "MAE_W":
            return float(sa.sum() / n_d.sum())
        if k == "MBE_W":
            return float(s1.sum() / n_d.sum())
        return float(100 * (E[m].sum() - E_obs.sum()) / E_obs.sum())

    rows = []
    for (m, k), v in boot.items():
        rows.append({"modelo": m, "metrica": k, "estimativa": point(m, k),
                     "ic95_lo": float(np.percentile(v, 2.5)), "ic95_hi": float(np.percentile(v, 97.5)),
                     "dp_bootstrap": float(np.std(v, ddof=1)), "B": B, "dias": D, "semente": seed})
    ci = pd.DataFrame(rows)
    prow = []
    for a, b in combinations(models, 2):
        for k in ("RMSE_W", "MAE_W"):
            dlt = boot[(b, k)] - boot[(a, k)]
            prow.append({"comparacao": f"{b} − {a}", "metrica": k, "diferenca": point(b, k) - point(a, k),
                         "ic95_lo": float(np.percentile(dlt, 2.5)), "ic95_hi": float(np.percentile(dlt, 97.5)),
                         "frac_boot_negativa": float(np.mean(dlt < 0)), "B": B, "dias": D,
                         "interpretacao": "diferença < 0 ⇒ segundo modelo com menor erro nesta amostra de dias"})
    paired = pd.DataFrame(prow)
    samples = pd.DataFrame({f"{m}|{k}": v for (m, k), v in boot.items()})
    return ci, paired, samples
