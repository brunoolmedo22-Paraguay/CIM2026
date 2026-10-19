"""Entradas meteorológicas do modo Modelos, com origem declarada.

GHI NÃO é POA. Um CSV com apenas GHI só é aceito se o usuário declarar o
módulo horizontal (inclinação 0°), caso em que POA = GHI por geometria.
Para qualquer outra inclinação a transposição não está implementada nesta
versão e o cálculo é bloqueado com explicação (nunca se renomeia GHI).
Nenhum valor ausente é preenchido: lacunas permanecem NaN e ficam fora da energia.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from ..constants import PROFILES

SYNTHETIC_PROFILES = ["Irradiância ideal (céu claro)", "Dia ensolarado", "Dia nublado", "Dia chuvoso"]
SEASONS = list(PROFILES["seasons"])


@dataclass
class WeatherSeries:
    timestamp: pd.DatetimeIndex
    g_poa_Wm2: np.ndarray
    origin: str                                  # medido | simulado | manual
    description: str
    t_amb_C: Optional[np.ndarray] = None
    t_module_C: Optional[np.ndarray] = None
    t_cell_C: Optional[np.ndarray] = None
    wind_ms: Optional[np.ndarray] = None
    notes: list = field(default_factory=list)

    def __len__(self):
        return len(self.timestamp)

    def temperature_kinds(self) -> list[str]:
        return [k for k, v in (("Tmod", self.t_module_C), ("Tcell", self.t_cell_C), ("Tamb", self.t_amb_C))
                if v is not None]


def _num(s: pd.Series) -> np.ndarray:
    if pd.api.types.is_numeric_dtype(s):
        return s.to_numpy(float)
    return pd.to_numeric(s.astype(str).str.strip().str.replace(",", ".", regex=False), errors="coerce").to_numpy(float)


def from_dataframe(df: pd.DataFrame, ts_col: str, g_col: str, g_kind: str, *, horizontal: bool = False,
                   temp_col: Optional[str] = None, temp_kind: Optional[str] = None,
                   wind_col: Optional[str] = None, ts_format: Optional[str] = None) -> WeatherSeries:
    if g_kind not in ("POA", "GHI"):
        raise ValueError("Tipo de irradiância deve ser POA ou GHI.")
    notes = []
    if g_kind == "GHI":
        if not horizontal:
            raise ValueError("A coluna é GHI (horizontal). GHI não é POA: a transposição para um plano "
                             "inclinado não está implementada nesta versão. Forneça POA medida ou declare o "
                             "módulo horizontal (inclinação 0°), quando POA = GHI.")
        notes.append("POA = GHI porque o módulo foi declarado horizontal (inclinação 0°).")
    ts = pd.to_datetime(df[ts_col].astype(str).str.strip(), format=ts_format, errors="coerce")
    if ts.isna().any():
        raise ValueError(f"{int(ts.isna().sum())} timestamp(s) inválido(s) na coluna {ts_col!r}.")
    order = np.argsort(ts.to_numpy(), kind="stable")
    if ts.duplicated().any():
        raise ValueError(f"{int(ts.duplicated().sum())} timestamp(s) duplicado(s).")
    g = _num(df[g_col])[order]
    if np.any(g[np.isfinite(g)] < 0):
        raise ValueError("Irradiância negativa encontrada; corrija a fonte.")
    w = WeatherSeries(timestamp=pd.DatetimeIndex(ts.to_numpy()[order]), g_poa_Wm2=g, origin="medido",
                      description=f"CSV do usuário ({g_kind} → POA)" if g_kind == "GHI" else "CSV do usuário (POA)",
                      notes=notes)
    if temp_col:
        t = _num(df[temp_col])[order]
        if temp_kind == "Tamb":
            w.t_amb_C = t
        elif temp_kind == "Tmod":
            w.t_module_C = t
        elif temp_kind == "Tcell":
            w.t_cell_C = t
        else:
            raise ValueError("Tipo de temperatura deve ser Tamb, Tmod ou Tcell.")
    if wind_col:
        w.wind_ms = _num(df[wind_col])[order]
    n_nan = int((~np.isfinite(g)).sum())
    if n_nan:
        w.notes.append(f"{n_nan} irradiância(s) ausente(s) mantidas como NaN (sem preenchimento).")
    return w


def _clear_sky(hours, sunrise, sunset, g_peak):
    x = (hours - sunrise) / (sunset - sunrise)
    return np.where((x > 0) & (x < 1), g_peak * np.sin(np.pi * np.clip(x, 0, 1)) ** 1.3, 0.0)


def synthetic(profile: str, season: str, start: str = "2025-01-01 00:00", duration_min: int = 1440,
              step_min: int = 1, g_peak: Optional[float] = None, t_min: Optional[float] = None,
              t_max: Optional[float] = None, seed: int = PROFILES["seed"]) -> WeatherSeries:
    """Gerador sintético do legado (mesmas fórmulas), com horizonte e passo livres."""
    if duration_min <= 0 or step_min <= 0:
        raise ValueError("Duração e passo devem ser positivos.")
    idx = pd.date_range(start=pd.Timestamp(start), periods=int(duration_min // step_min), freq=f"{int(step_min)}min")
    hours = np.asarray(idx.hour + idx.minute / 60.0 + idx.second / 3600.0, float)
    rng = np.random.default_rng(seed)
    sr, ss = PROFILES["sunrise_h"], PROFILES["sunset_h"]
    if profile == SYNTHETIC_PROFILES[0]:
        g = _clear_sky(hours, sr, ss, g_peak or PROFILES["g_peak_clear"])
    elif profile == SYNTHETIC_PROFILES[1]:
        g = _clear_sky(hours, sr, ss, g_peak or PROFILES["g_peak_clear"]) * (1 + 0.01 * rng.standard_normal(hours.size))
    elif profile == SYNTHETIC_PROFILES[2]:
        peak = g_peak or PROFILES["g_peak_cloudy"]
        env = _clear_sky(hours, sr, ss, PROFILES["g_peak_clear"])
        smooth = np.convolve(rng.standard_normal(hours.size), np.ones(15) / 15.0, mode="same")
        smooth = (smooth - smooth.min()) / (np.ptp(smooth) + 1e-9)
        cloud = 1.0 - PROFILES["cloud_depth"] * smooth
        drops = rng.random(hours.size) < 0.05
        cloud[drops] *= rng.uniform(0.35, 0.75, size=drops.sum())
        g = np.clip(env * cloud * (peak / PROFILES["g_peak_clear"] + 0.35), 0.0, PROFILES["g_peak_clear"])
    elif profile == SYNTHETIC_PROFILES[3]:
        env = _clear_sky(hours, sr, ss, g_peak or PROFILES["g_peak_rainy"])
        g = env * (1.0 + PROFILES["rain_noise"] * rng.standard_normal(hours.size))
    else:
        raise ValueError(f"Perfil desconhecido: {profile!r}")
    cfg = PROFILES["seasons"][season]
    tmin = cfg["t_min"] if t_min is None else t_min
    tmax = cfg["t_max"] if t_max is None else t_max
    tamb = 0.5 * (tmax + tmin) + 0.5 * (tmax - tmin) * np.cos(2 * np.pi * (hours - cfg["t_peak_h"]) / 24.0)
    return WeatherSeries(timestamp=idx, g_poa_Wm2=np.clip(g, 0.0, None), origin="simulado",
                         description=f"Perfil sintético do legado: {profile}, {season}", t_amb_C=tamb,
                         notes=["Irradiância sintética assumida no plano do módulo (POA simulada)."])


def manual(g_poa: float, temperature: float, temp_kind: str, duration_min: int = 60, step_min: int = 1,
           start: str = "2025-01-01 12:00", wind: Optional[float] = None) -> WeatherSeries:
    idx = pd.date_range(start=pd.Timestamp(start), periods=max(int(duration_min // step_min), 1), freq=f"{int(step_min)}min")
    n = len(idx)
    w = WeatherSeries(timestamp=idx, g_poa_Wm2=np.full(n, float(g_poa)), origin="manual",
                      description=f"Condição constante manual: Gpoa={g_poa:g} W/m², {temp_kind}={temperature:g} °C")
    arr = np.full(n, float(temperature))
    if temp_kind == "Tamb":
        w.t_amb_C = arr
    elif temp_kind == "Tmod":
        w.t_module_C = arr
    else:
        w.t_cell_C = arr
    if wind is not None:
        w.wind_ms = np.full(n, float(wind))
    return w


def supsi_days(field_df: pd.DataFrame, days: list[str]) -> WeatherSeries:
    """Dias medidos SUPSI (POA + Tbom + Tamb + vento), sem filtragem nem preenchimento."""
    d = field_df[field_df["timestamp"].dt.date.astype(str).isin(days)].sort_values("row_id")
    return WeatherSeries(timestamp=pd.DatetimeIndex(d["timestamp"]), g_poa_Wm2=d["g_poa_Wm2"].to_numpy(float),
                         origin="medido", description=f"SUPSI 2019 medido: {', '.join(days)}",
                         t_amb_C=d["t_amb_C"].to_numpy(float), t_module_C=d["t_module_C"].to_numpy(float),
                         wind_ms=d["wind_ms"].to_numpy(float),
                         notes=["Gpoa medida (piranômetro no plano); Tbom = temperatura posterior medida."])
