"""Leitura das medições exteriores SUPSI 2019 e controle de qualidade auditável.

* Lê ``dd.mm.yyyy HH:MM:SS`` explicitamente; preserva Date/Time originais,
  arquivo mensal e número da linha (1 = primeira linha de dados; linha do
  arquivo = source_row + 1).
* ``Gpoa`` → ``g_poa_Wm2`` (POA medida); ``Gglob_hor`` → ``ghi_Wm2`` (GHI).
  Nunca se intercambiam. ``Tbom`` → ``t_module_C`` (temperatura posterior; NÃO Tcell).
* Nenhuma linha é apagada, promediada ou imputada: a elegibilidade é uma máscara
  com lista de motivos; flags informativas não excluem.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from ..paths import SUPSI_RAW_FIELD
from .supsi_lab import sha256_file

COLUMN_MAP = {
    "Pm": "p_mpp_measured_W", "Voc": "voc_measured_V", "Isc": "isc_measured_A",
    "Tbom": "t_module_C", "Gpoa": "g_poa_Wm2", "Gglob_hor": "ghi_Wm2", "Gdiff_hor": "dhi_Wm2",
    "RH_AIR": "rh_pct", "AIR_TEMP": "t_amb_C", "WIND_SPEED": "wind_ms",
}
UNITS = {"p_mpp_measured_W": "W", "voc_measured_V": "V", "isc_measured_A": "A", "t_module_C": "°C",
         "g_poa_Wm2": "W/m²", "ghi_Wm2": "W/m²", "dhi_Wm2": "W/m²", "rh_pct": "%", "t_amb_C": "°C",
         "wind_ms": "m/s"}
MANDATORY = {"Date", "Time", "Pm", "Gpoa", "Tbom"}
AVAILABLE_MONTHS = tuple(f"2019_{m:02d}" for m in range(1, 7))


def month_path(month: str, base: Path = SUPSI_RAW_FIELD) -> Path:
    return Path(base) / f"{month}.csv"


def read_month(path: Path | str) -> pd.DataFrame:
    path = Path(path)
    df = pd.read_csv(path, sep=";", encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    miss = MANDATORY - set(df.columns)
    if miss:
        raise ValueError(f"{path.name}: colunas SUPSI ausentes {sorted(miss)}")
    out = pd.DataFrame({
        "source_file": path.name,
        "source_row": np.arange(1, len(df) + 1, dtype=int),
        "date_raw": df["Date"].str.strip(),
        "time_raw": df["Time"].str.strip(),
    })
    out["timestamp"] = pd.to_datetime(out["date_raw"] + " " + out["time_raw"],
                                      format="%d.%m.%Y %H:%M:%S", errors="coerce")
    for raw, new in COLUMN_MAP.items():
        if raw in df.columns:
            out[new] = pd.to_numeric(df[raw].str.strip().replace("", np.nan), errors="coerce")
        else:
            out[new] = np.nan
    return out


def load_field(months: Iterable[str] = AVAILABLE_MONTHS, base: Path = SUPSI_RAW_FIELD) -> tuple[pd.DataFrame, dict]:
    frames, hashes = [], {}
    for m in months:
        p = month_path(m, base)
        frames.append(read_month(p))
        hashes[p.name] = sha256_file(p)
    df = pd.concat(frames, ignore_index=True)
    # row_id é local à seleção de meses; a chave estável é (source_file, source_row)
    df.insert(0, "row_id", np.arange(len(df), dtype=int))
    return df, hashes


# ---------------------------------------------------------------------------
# Qualidade
# ---------------------------------------------------------------------------
REASONS = {
    "R01": "timestamp inválido",
    "R02": "timestamp duplicado",
    "R03": "valor obrigatório ausente/não numérico (Pm, Gpoa, Tbom)",
    "R04": "Gpoa < 0",
    "R05": "Pm < 0",
    "R06": "Tbom fora da faixa plausível",
    "R07": "Gpoa abaixo do limiar de irradiância",
    "R08": "Gpoa acima do limite plausível",
    "R09": "Tamb ou vento ausentes/implausíveis (exigidos pela estratégia térmica B)",
}
FLAGS = {
    "F01": "Voc medido fora de [0,5; 1,2]×Voc_STC (informativo; não exclui)",
    "F02": "Pm/(Pstc·G/1000) fora de [0,5; 1,2] (informativo; não exclui)",
}


@dataclass(frozen=True)
class QualityConfig:
    g_threshold_Wm2: float = 100.0
    g_max_Wm2: float = 1500.0
    t_module_range_C: tuple = (-40.0, 90.0)
    t_amb_range_C: tuple = (-40.0, 60.0)
    wind_range_ms: tuple = (0.0, 50.0)
    require_ambient: bool = False         # True na estratégia B (Faiman)
    voc_stc_V: float | None = None
    p_stc_W: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def assess_quality(df: pd.DataFrame, cfg: QualityConfig) -> pd.DataFrame:
    """Acrescenta ``eligible`` (bool), ``reasons`` e ``info_flags`` (códigos separados por ';')."""
    q = df.copy()
    n = len(q)
    reasons = {code: np.zeros(n, bool) for code in REASONS}
    ts = q["timestamp"]
    reasons["R01"] = ts.isna().to_numpy()
    reasons["R02"] = (ts.duplicated(keep=False) & ts.notna()).to_numpy()
    g = q["g_poa_Wm2"].to_numpy(float)
    pm = q["p_mpp_measured_W"].to_numpy(float)
    tm = q["t_module_C"].to_numpy(float)
    reasons["R03"] = ~(np.isfinite(g) & np.isfinite(pm) & np.isfinite(tm))
    with np.errstate(invalid="ignore"):
        reasons["R04"] = g < 0
        reasons["R05"] = pm < 0
        lo, hi = cfg.t_module_range_C
        reasons["R06"] = np.isfinite(tm) & ((tm < lo) | (tm > hi))
        reasons["R07"] = np.isfinite(g) & (g >= 0) & (g < cfg.g_threshold_Wm2)
        reasons["R08"] = np.isfinite(g) & (g > cfg.g_max_Wm2)
        if cfg.require_ambient:
            ta = q["t_amb_C"].to_numpy(float)
            ws = q["wind_ms"].to_numpy(float)
            bad = ~(np.isfinite(ta) & np.isfinite(ws))
            bad |= np.isfinite(ta) & ((ta < cfg.t_amb_range_C[0]) | (ta > cfg.t_amb_range_C[1]))
            bad |= np.isfinite(ws) & ((ws < cfg.wind_range_ms[0]) | (ws > cfg.wind_range_ms[1]))
            reasons["R09"] = bad
    flags = {code: np.zeros(n, bool) for code in FLAGS}
    with np.errstate(invalid="ignore", divide="ignore"):
        if cfg.voc_stc_V:
            voc = q["voc_measured_V"].to_numpy(float)
            flags["F01"] = np.isfinite(voc) & ((voc < 0.5 * cfg.voc_stc_V) | (voc > 1.2 * cfg.voc_stc_V))
        if cfg.p_stc_W:
            ratio = pm / (cfg.p_stc_W * g / 1000.0)
            flags["F02"] = np.isfinite(ratio) & (g > 0) & ((ratio < 0.5) | (ratio > 1.2))
    q["eligible"] = ~np.any(np.vstack(list(reasons.values())), axis=0)
    q["reasons"] = _join_codes(reasons, n)
    q["info_flags"] = _join_codes(flags, n)
    return q


def _join_codes(d: dict, n: int) -> list[str]:
    codes = list(d)
    mat = np.vstack([d[c] for c in codes]) if codes else np.zeros((0, n), bool)
    return [";".join(c for c, hit in zip(codes, mat[:, i]) if hit) for i in range(n)]


def valid_pair_mask(timestamps: pd.Series, eligible: np.ndarray, max_gap_min: float = 7.5) -> np.ndarray:
    """Pares (i, i+1) válidos para integração trapezoidal: ambos elegíveis,
    consecutivos no tempo (0 < Δt ≤ max_gap_min) e no mesmo dia civil."""
    ts = pd.to_datetime(pd.Series(timestamps).reset_index(drop=True))
    el = np.asarray(eligible, bool)
    if len(ts) < 2:
        return np.zeros(0, bool)
    dt = (ts.diff().dt.total_seconds() / 60.0).to_numpy()[1:]
    same_day = (ts.dt.normalize().to_numpy()[1:] == ts.dt.normalize().to_numpy()[:-1])
    return el[:-1] & el[1:] & np.isfinite(dt) & (dt > 0) & (dt <= max_gap_min) & same_day


def monthly_summary(q: pd.DataFrame, max_gap_min: float = 7.5) -> pd.DataFrame:
    rows = []
    for name, d in q.groupby("source_file", sort=True):
        d = d.sort_values("row_id")
        pairs = valid_pair_mask(d["timestamp"], d["eligible"].to_numpy(), max_gap_min)
        dt_h = d["timestamp"].diff().dt.total_seconds().to_numpy()[1:] / 3600.0
        row = {"arquivo": name, "n_total": len(d), "n_elegivel": int(d["eligible"].sum()),
               "dias_com_dados": int(d["timestamp"].dt.date.nunique()),
               "dias_com_elegiveis": int(d.loc[d.eligible, "timestamp"].dt.date.nunique()),
               "pares_validos": int(pairs.sum()),
               "horas_cobertas_pares_validos": float(np.nansum(dt_h[pairs])) if len(pairs) else 0.0}
        for code in REASONS:
            row[code] = int(d["reasons"].str.contains(code, regex=False).sum())
        for code in FLAGS:
            row[code] = int(d["info_flags"].str.contains(code, regex=False).sum())
        rows.append(row)
    out = pd.DataFrame(rows)
    if len(out):
        tot = out.drop(columns=["arquivo"]).sum(numeric_only=True)
        tot["arquivo"] = "TOTAL"
        out = pd.concat([out, tot.to_frame().T], ignore_index=True)
    return out


def interval_report(q: pd.DataFrame) -> pd.DataFrame:
    """Distribuição de intervalos entre registros consecutivos (todas as linhas)."""
    d = q.sort_values("row_id")
    dt = d["timestamp"].diff().dt.total_seconds() / 60.0
    same_day = d["timestamp"].dt.normalize().eq(d["timestamp"].dt.normalize().shift())
    cats = pd.cut(dt[same_day], bins=[0, 4.99, 5.01, 7.5, 30, 1e9],
                  labels=["<5 min", "5 min", "5–7,5 min", "7,5–30 min", ">30 min"])
    rep = cats.value_counts().sort_index().rename_axis("intervalo_intradiario").reset_index(name="n")
    return rep
