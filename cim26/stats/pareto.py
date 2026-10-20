"""Fronteira de Pareto erro × custo e razão de melhoria marginal.

Metodologia declarada:
* Custo: mediana do tempo por amostra (µs) ou mediana do pico ΔRSS (MiB).
* Erro: RMSE global (W) na interseção comum de amostras.
* i é dominado se ∃ j com custo_j ≤ custo_i e erro_j ≤ erro_i, ao menos uma estrita.
* Dominância robusta: exige IC95 sem sobreposição em ambos os eixos.
* Melhoria marginal relativa ao modelo não dominado imediatamente mais barato:
  ΔRMSE = RMSE_ref − RMSE_k (W; > 0 = melhora); Δt = t_k − t_ref (µs/amostra);
  razão = ΔRMSE/Δt [W por µs/amostra]; fator de custo = t_k/t_ref.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def pareto_table(points: pd.DataFrame, cost: str, err: str = "RMSE_W",
                 cost_lo: str | None = None, cost_hi: str | None = None,
                 err_lo: str | None = None, err_hi: str | None = None) -> pd.DataFrame:
    p = points.copy().reset_index(drop=True)
    dom_by, robust_by = [], []
    for i, ri in p.iterrows():
        d, r = [], []
        for j, rj in p.iterrows():
            if i == j:
                continue
            le = rj[cost] <= ri[cost] and rj[err] <= ri[err]
            st = rj[cost] < ri[cost] or rj[err] < ri[err]
            if le and st:
                d.append(rj["modelo"])
                if all(c is not None for c in (cost_lo, cost_hi, err_lo, err_hi)):
                    if rj[cost_hi] < ri[cost_lo] and rj[err_hi] < ri[err_lo]:
                        r.append(rj["modelo"])
        dom_by.append(", ".join(d)); robust_by.append(", ".join(r))
    p["dominado_por"] = dom_by
    p["nao_dominado"] = [s == "" for s in dom_by]
    p["dominancia_robusta_por"] = robust_by
    return p


def marginal_improvement(points: pd.DataFrame, cost: str, err: str = "RMSE_W") -> pd.DataFrame:
    p = points.sort_values(cost).reset_index(drop=True)
    front = p[p["nao_dominado"]] if "nao_dominado" in p else p
    rows = []
    cheapest = p.iloc[0]
    for _, r in p.iterrows():
        cheaper_front = front[front[cost] < r[cost]]
        ref = cheaper_front.iloc[-1] if len(cheaper_front) else None
        for label, base in (("vs mais barato não dominado", ref), ("vs modelo mais barato", cheapest)):
            if base is None or base["modelo"] == r["modelo"]:
                continue
            d_err = base[err] - r[err]
            d_cost = r[cost] - base[cost]
            rows.append({"modelo": r["modelo"], "referencia": base["modelo"], "tipo": label,
                         "delta_erro": d_err, "delta_custo": d_cost,
                         "razao_melhoria_por_custo": d_err / d_cost if d_cost > 0 else np.nan,
                         "fator_custo": r[cost] / base[cost] if base[cost] > 0 else np.nan,
                         "melhoria_relativa_pct": 100 * d_err / base[err] if base[err] else np.nan,
                         "eixo_custo": cost, "eixo_erro": err})
    return pd.DataFrame(rows)
