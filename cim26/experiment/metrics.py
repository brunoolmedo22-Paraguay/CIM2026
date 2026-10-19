"""Métricas de erro e energia calculadas SEMPRE a partir de ``predictions.csv``.

Convenções:
    resíduo e = P_prev − P_obs  (MBE > 0 ⇒ sobrestimação)
    NRMSE/NMAE declaram o normalizador: Pstc ou média observada.
    MAPE não é usado (P_obs pode ser ≈ 0).
Energia: trapézios APENAS em pares temporalmente adjacentes válidos
(ambos na interseção, Δt ≤ max_gap, mesmo dia), mesma máscara para todos.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.supsi_field import valid_pair_mask
from ..pvcore.models import MODEL_IDS

OBS = "P_obs_W"


def pcol(m: str) -> str:
    return f"P_{m}_W"


def intersection_mask(pred: pd.DataFrame, models=MODEL_IDS) -> np.ndarray:
    ok = np.isfinite(pred[OBS].to_numpy(float))
    for m in models:
        ok &= np.isfinite(pred[pcol(m)].to_numpy(float))
    return ok


def error_metrics(p: np.ndarray, o: np.ndarray, p_stc: float) -> dict:
    e = p - o
    n = int(e.size)
    if n == 0:
        return dict(N=0, RMSE_W=np.nan, MAE_W=np.nan, MBE_W=np.nan, NRMSE_Pstc_pct=np.nan,
                    NMAE_Pstc_pct=np.nan, NRMSE_media_pct=np.nan, NMBE_media_pct=np.nan)
    rmse = float(np.sqrt(np.mean(e**2)))
    mae = float(np.mean(np.abs(e)))
    mbe = float(np.mean(e))
    mo = float(np.mean(o))
    return dict(N=n, RMSE_W=rmse, MAE_W=mae, MBE_W=mbe,
                NRMSE_Pstc_pct=100 * rmse / p_stc, NMAE_Pstc_pct=100 * mae / p_stc,
                NRMSE_media_pct=100 * rmse / mo if mo else np.nan,
                NMBE_media_pct=100 * mbe / mo if mo else np.nan)


def pair_energy_kWh(ts: pd.Series, p: np.ndarray, pairs: np.ndarray) -> float:
    t = pd.to_datetime(pd.Series(ts).reset_index(drop=True))
    dt_h = t.diff().dt.total_seconds().to_numpy()[1:] / 3600.0
    p = np.asarray(p, float)
    seg = 0.5 * (p[:-1] + p[1:]) * dt_h
    return float(np.sum(seg[pairs]) / 1000.0)


def common_support(pred: pd.DataFrame, max_gap_min: float, models=MODEL_IDS):
    """Interseção (amostras com todas as previsões finitas) e pares válidos nela."""
    inter = intersection_mask(pred, models)
    pairs = valid_pair_mask(pred["timestamp"], inter, max_gap_min)
    return inter, pairs


def energy_metrics(pred: pd.DataFrame, p_stc: float, max_gap_min: float, models=MODEL_IDS) -> pd.DataFrame:
    pred = pred.sort_values("row_id").reset_index(drop=True)
    inter, pairs = common_support(pred, max_gap_min, models)
    t = pd.to_datetime(pred["timestamp"])
    hours = float(np.sum((t.diff().dt.total_seconds().to_numpy()[1:] / 3600.0)[pairs]))
    o = pred[OBS].to_numpy(float)
    e_obs = pair_energy_kWh(t, o, pairs)
    rows = []
    for m in models:
        p = pred[pcol(m)].to_numpy(float)
        met = error_metrics(p[inter], o[inter], p_stc)
        e_m = pair_energy_kWh(t, p, pairs)
        rows.append({"modelo": m, **met,
                     "N_modelo_finito": int(np.isfinite(p).sum()), "N_total_elegivel": len(pred),
                     "cobertura_modelo_pct": 100 * np.isfinite(p).sum() / max(len(pred), 1),
                     "pares_validos": int(pairs.sum()), "horas_cobertas_h": hours,
                     "E_obs_kWh": e_obs, "E_prev_kWh": e_m,
                     "erro_energia_kWh": e_m - e_obs,
                     "erro_energia_pct": 100 * (e_m - e_obs) / e_obs if e_obs else np.nan,
                     "unidade_potencia": "W (por módulo)", "normalizador_NRMSE": "Pstc e média observada (declarados)"})
    return pd.DataFrame(rows)


def grouped_metrics(pred: pd.DataFrame, p_stc: float, by: str, max_gap_min: float,
                    models=MODEL_IDS) -> pd.DataFrame:
    """Métricas por grupo temporal ('dia' ou 'mes') na interseção comum."""
    pred = pred.sort_values("row_id").reset_index(drop=True)
    inter, pairs = common_support(pred, max_gap_min, models)
    t = pd.to_datetime(pred["timestamp"])
    key = t.dt.date.astype(str) if by == "dia" else t.dt.strftime("%Y-%m")
    rows = []
    pair_key = key.to_numpy()[:-1]
    dt_h = t.diff().dt.total_seconds().to_numpy()[1:] / 3600.0
    o = pred[OBS].to_numpy(float)
    for g in pd.unique(key):
        sel = (key.to_numpy() == g) & inter
        psel = pairs & (pair_key == g)
        if sel.sum() == 0:
            continue
        seg_o = 0.5 * (o[:-1] + o[1:]) * dt_h
        e_obs = float(np.sum(seg_o[psel]) / 1000)
        for m in models:
            p = pred[pcol(m)].to_numpy(float)
            seg = 0.5 * (p[:-1] + p[1:]) * dt_h
            e_m = float(np.sum(seg[psel]) / 1000)
            rows.append({by: g, "modelo": m, **error_metrics(p[sel], o[sel], p_stc),
                         "E_obs_kWh": e_obs, "E_prev_kWh": e_m,
                         "horas_cobertas_h": float(np.sum(dt_h[psel]))})
    return pd.DataFrame(rows)


G_BINS = [100, 200, 400, 600, 800, 1000, 1500]
T_BINS = [-40, 15, 25, 35, 45, 55, 90]


def binned_residuals(pred: pd.DataFrame, models=MODEL_IDS) -> pd.DataFrame:
    inter = intersection_mask(pred, models)
    d = pred[inter]
    lo_g = min(G_BINS[0], float(np.floor(d["g_poa_Wm2"].min() / 50) * 50)) if len(d) else G_BINS[0]
    gb = pd.cut(d["g_poa_Wm2"], [lo_g] + G_BINS[1:], right=False)
    tb = pd.cut(d["t_module_C"], T_BINS, right=False)
    rows = []
    for var, bins in (("Gpoa [W/m²]", gb), ("Tmod [°C]", tb)):
        for b, dd in d.groupby(bins, observed=True):
            o = dd[OBS].to_numpy(float)
            for m in models:
                e = dd[pcol(m)].to_numpy(float) - o
                rows.append({"variavel": var, "faixa": str(b), "modelo": m, "N": len(e),
                             "MBE_W": float(np.mean(e)), "MAE_W": float(np.mean(np.abs(e))),
                             "RMSE_W": float(np.sqrt(np.mean(e**2))),
                             "residuo_p5_W": float(np.percentile(e, 5)), "residuo_p95_W": float(np.percentile(e, 95))})
    return pd.DataFrame(rows)
