"""Detecção de anomalias físicas nas medições de campo (independente dos modelos).

Os critérios usam SOMENTE grandezas medidas (Pm, Gpoa, Isc, Voc, Tbom, Tamb) e
limiares fixados ANTES de observar erros de modelo; a mesma marcação vale para
os quatro modelos. Por padrão as anomalias são apenas sinalizadas; a exclusão é
uma política explícita do experimento (registrada em config.json) e o efeito
sobre as métricas é sempre reportado como análise de sensibilidade.

Severidade:
  erro      — inconsistência física praticamente certa (ex.: potência sem irradiância)
  suspeito  — inconsistência provável (sombra, dessincronização, sensor)
  condicao  — não é erro, é condição de medição difícil (transitório rápido)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

ANOMALIES = {
    "A01": ("erro", "potência sem irradiância", "Pm > 5 % Pstc com Gpoa < 20 W/m²"),
    "A02": ("erro", "irradiância sem potência", "Gpoa ≥ 200 W/m² com Pm < 2 % Pstc"),
    "A03": ("erro", "potência acima do fisicamente plausível", "Pm/(Pstc·G/1000) > 1,25 com G ≥ 100 W/m²"),
    "A04": ("suspeito", "potência muito abaixo do esperado", "Pm/(Pstc·G/1000) < 0,50 com G ≥ 100 W/m²"),
    "A05": ("suspeito", "Isc incoerente com Gpoa", "Isc/(Isc_STC·G/1000) fora de [0,80; 1,20] com G ≥ 100 W/m²"),
    "A06": ("erro", "Voc implausível", "Voc fora de [0,5; 1,2]×Voc_STC"),
    "A07": ("suspeito", "Tbom incoerente com Tamb", "Tbom − Tamb fora de [−5; 45] °C com G ≥ 100 W/m²"),
    "A08": ("suspeito", "salto de temperatura do módulo", "|ΔTbom| > 10 °C entre registros consecutivos"),
    "A09": ("suspeito", "valor congelado", "Gpoa ou Pm idênticos em ≥ 4 registros consecutivos"),
    "T01": ("condicao", "transitório rápido de irradiância", "|ΔGpoa| > 250 W/m² em relação a um vizinho (5 min)"),
}
SEVERITY_ORDER = {"erro": 3, "suspeito": 2, "condicao": 1, "": 0}


@dataclass(frozen=True)
class AnomalyConfig:
    p_without_g_frac: float = 0.05
    g_dark_Wm2: float = 20.0
    g_without_p_Wm2: float = 200.0
    p_floor_frac: float = 0.02
    pr_high: float = 1.25
    pr_low: float = 0.50
    min_g_ratio_Wm2: float = 100.0
    isc_band: tuple = (0.80, 1.20)
    voc_band: tuple = (0.5, 1.2)
    dt_mod_amb_C: tuple = (-5.0, 45.0)
    t_jump_C: float = 10.0
    g_ramp_Wm2: float = 250.0
    stuck_n: int = 4

    def to_dict(self) -> dict:
        d = asdict(self)
        return {k: list(v) if isinstance(v, tuple) else v for k, v in d.items()}


def _runs_of_equal(x: np.ndarray, n: int, same_day: np.ndarray) -> np.ndarray:
    """Marca valores finitos repetidos em ≥ n registros consecutivos do mesmo dia."""
    out = np.zeros(len(x), bool)
    start = 0
    for i in range(1, len(x) + 1):
        brk = i == len(x) or not (np.isfinite(x[i]) and x[i] == x[i - 1] and same_day[i])
        if brk:
            if i - start >= n and np.isfinite(x[start]):
                out[start:i] = True
            start = i
    return out


def detect_anomalies(df: pd.DataFrame, p_stc_W: float, isc_stc_A: float, voc_stc_V: float,
                     cfg: AnomalyConfig = AnomalyConfig()) -> pd.DataFrame:
    """Retorna DataFrame alinhado a ``df`` com códigos, severidade e razões diagnósticas."""
    d = df.sort_values("row_id") if "row_id" in df else df
    g = d["g_poa_Wm2"].to_numpy(float)
    p = d["p_mpp_measured_W"].to_numpy(float)
    isc = d["isc_measured_A"].to_numpy(float)
    voc = d["voc_measured_V"].to_numpy(float)
    tm = d["t_module_C"].to_numpy(float)
    ta = d["t_amb_C"].to_numpy(float)
    ts = pd.to_datetime(d["timestamp"])
    day = ts.dt.normalize().to_numpy()
    same_day = np.r_[False, day[1:] == day[:-1]]
    with np.errstate(invalid="ignore", divide="ignore"):
        pr = np.where(g > 0, p / (p_stc_W * g / 1000.0), np.nan)
        iscr = np.where(g > 0, isc / (isc_stc_A * g / 1000.0), np.nan)
        hit = {
            "A01": (p > cfg.p_without_g_frac * p_stc_W) & (g < cfg.g_dark_Wm2),
            "A02": (g >= cfg.g_without_p_Wm2) & (p < cfg.p_floor_frac * p_stc_W),
            "A03": (g >= cfg.min_g_ratio_Wm2) & (pr > cfg.pr_high),
            "A04": (g >= cfg.min_g_ratio_Wm2) & (pr < cfg.pr_low),
            "A05": (g >= cfg.min_g_ratio_Wm2) & ((iscr < cfg.isc_band[0]) | (iscr > cfg.isc_band[1])),
            "A06": np.isfinite(voc) & ((voc < cfg.voc_band[0] * voc_stc_V) | (voc > cfg.voc_band[1] * voc_stc_V)),
            "A07": (g >= cfg.min_g_ratio_Wm2) & (((tm - ta) < cfg.dt_mod_amb_C[0]) | ((tm - ta) > cfg.dt_mod_amb_C[1])),
        }
        dtm = np.r_[np.nan, np.abs(np.diff(tm))]
        dtm[~same_day] = np.nan
        jump = dtm > cfg.t_jump_C
        hit["A08"] = jump | np.r_[jump[1:], False]
        hit["A09"] = _runs_of_equal(g, cfg.stuck_n, same_day) | _runs_of_equal(p, cfg.stuck_n, same_day)
        dg = np.r_[np.nan, np.abs(np.diff(g))]
        dg[~same_day] = np.nan
        ramp = dg > cfg.g_ramp_Wm2
        hit["T01"] = ramp | np.r_[ramp[1:], False]
    codes = list(ANOMALIES)
    mat = np.vstack([np.asarray(hit[c], bool) for c in codes])
    labels = [";".join(c for c, h in zip(codes, mat[:, i]) if h) for i in range(len(d))]
    sev = []
    for lab in labels:
        s = ""
        for c in lab.split(";") if lab else []:
            cand = ANOMALIES[c][0]
            if SEVERITY_ORDER[cand] > SEVERITY_ORDER[s]:
                s = cand
        sev.append(s)
    out = pd.DataFrame({"anom_codes": labels, "anom_severidade": sev, "pr_inst": pr, "isc_ratio": iscr,
                        "transitorio": hit["T01"]}, index=d.index)
    return out.reindex(df.index)


def anomaly_summary(q: pd.DataFrame) -> pd.DataFrame:
    """Contagem por código, em todas as linhas e nas elegíveis."""
    rows = []
    el = q["eligible"].to_numpy(bool) if "eligible" in q else np.ones(len(q), bool)
    for c, (sev, name, rule) in ANOMALIES.items():
        has = q["anom_codes"].fillna("").str.contains(c, regex=False).to_numpy()
        rows.append({"codigo": c, "severidade": sev, "anomalia": name, "regra": rule,
                     "n_todas": int(has.sum()), "n_elegiveis": int((has & el).sum()),
                     "pct_elegiveis": 100 * float((has & el).sum()) / max(int(el.sum()), 1)})
    return pd.DataFrame(rows)
