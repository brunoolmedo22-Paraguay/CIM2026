"""
models/irradiance_model.py
==========================
Generación de perfiles temporales de irradiancia G(t) y temperatura ambiente
Tamb(t), y carga/validación de perfiles personalizados desde CSV.

Además de los perfiles sintéticos, este módulo prepara CSV de predicción con:
    * detección flexible de columnas (timestamp, GHI, temperatura);
    * selección explícita de la serie de irradiancia;
    * reconstrucción del eje temporal completo;
    * llenado transparente de faltantes con G = 0;
    * clasificación de datos originales, noche completada y lagunas diurnas;
    * generación de temperatura cuando el CSV no la contiene.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import numpy as np
import pandas as pd

from config.settings import PROFILES, UI

PROFILE_LOADER_API_VERSION = "2026.07.22.2"

IRRADIANCE_PROFILES = [
    "Irradiância perfeita",
    "Día soleado",
    "Día nublado",
    "Día lluvioso",
]
SEASONS = list(PROFILES["seasons"].keys())


# ===========================================================================
# Eje temporal
# ===========================================================================
def time_axis(timestep_min: int = PROFILES["timestep_min"], date: str = "2025-01-01"):
    """Devuelve (índice datetime, horas decimales) para un día completo."""
    n = int(PROFILES["minutes_per_day"] / timestep_min)
    idx = pd.date_range(start=date, periods=n, freq=f"{timestep_min}min")
    hours = idx.hour + idx.minute / 60.0 + idx.second / 3600.0
    return idx, np.asarray(hours, dtype=float)


# ===========================================================================
# Irradiancia
# ===========================================================================
def _clear_sky_envelope(hours: np.ndarray, sunrise: float, sunset: float, g_peak: float):
    """Campana solar: G = Gpeak * sin(pi * (t - amanecer)/(duración del día))**1.3."""
    day_len = sunset - sunrise
    x = (hours - sunrise) / day_len
    g = np.where(
        (x > 0) & (x < 1),
        g_peak * np.sin(np.pi * np.clip(x, 0, 1)) ** 1.3,
        0.0,
    )
    return g


def generate_irradiance(
    profile: str,
    hours: np.ndarray,
    sunrise: float = PROFILES["sunrise_h"],
    sunset: float = PROFILES["sunset_h"],
    g_peak: float | None = None,
    seed: int | None = PROFILES["seed"],
) -> np.ndarray:
    """Genera G(t) [W/m²] según el perfil característico solicitado."""
    rng = np.random.default_rng(seed)

    if profile == "Irradiância perfeita":
        peak = g_peak or PROFILES["g_peak_clear"]
        g = _clear_sky_envelope(hours, sunrise, sunset, peak)

    elif profile == "Día soleado":
        peak = g_peak or PROFILES["g_peak_clear"]
        g = _clear_sky_envelope(hours, sunrise, sunset, peak)
        g = g * (1.0 + 0.01 * rng.standard_normal(g.size))

    elif profile == "Día nublado":
        peak = g_peak or PROFILES["g_peak_cloudy"]
        env = _clear_sky_envelope(hours, sunrise, sunset, PROFILES["g_peak_clear"])
        noise = rng.standard_normal(hours.size)
        kernel = np.ones(15) / 15.0
        smooth = np.convolve(noise, kernel, mode="same")
        smooth = (smooth - smooth.min()) / (np.ptp(smooth) + 1e-9)
        cloud = 1.0 - PROFILES["cloud_depth"] * smooth
        drops = rng.random(hours.size) < 0.05
        cloud[drops] *= rng.uniform(0.35, 0.75, size=drops.sum())
        g = env * cloud * (peak / PROFILES["g_peak_clear"] + 0.35)
        g = np.clip(g, 0.0, PROFILES["g_peak_clear"])

    elif profile == "Día lluvioso":
        peak = g_peak or PROFILES["g_peak_rainy"]
        env = _clear_sky_envelope(hours, sunrise, sunset, peak)
        g = env * (1.0 + PROFILES["rain_noise"] * rng.standard_normal(hours.size))

    else:
        raise ValueError(f"Perfil de irradiancia desconocido: {profile!r}")

    return np.clip(g, 0.0, None)


# ===========================================================================
# Temperatura ambiente
# ===========================================================================
def generate_temperature(
    season: str,
    hours: np.ndarray,
    t_min: float | None = None,
    t_max: float | None = None,
    t_peak_h: float | None = None,
) -> np.ndarray:
    """
    Tamb(t) [°C]: sinusoide con mínimo al amanecer y máximo a t_peak_h.

        Tamb = Tmed + A * cos(2*pi*(t - t_peak)/24)
    """
    if season not in PROFILES["seasons"]:
        raise ValueError(f"Estación desconocida: {season!r}")
    cfg = PROFILES["seasons"][season]

    t_min = cfg["t_min"] if t_min is None else t_min
    t_max = cfg["t_max"] if t_max is None else t_max
    t_peak_h = cfg["t_peak_h"] if t_peak_h is None else t_peak_h

    t_mean = 0.5 * (t_max + t_min)
    amp = 0.5 * (t_max - t_min)
    return t_mean + amp * np.cos(2.0 * np.pi * (hours - t_peak_h) / 24.0)


# ===========================================================================
# Ensamblado de perfiles sintéticos
# ===========================================================================
def build_synthetic_profile(
    irradiance_profile: str,
    season: str,
    timestep_min: int = PROFILES["timestep_min"],
    sunrise: float = PROFILES["sunrise_h"],
    sunset: float = PROFILES["sunset_h"],
    g_peak: float | None = None,
    t_min: float | None = None,
    t_max: float | None = None,
    seed: int | None = PROFILES["seed"],
) -> pd.DataFrame:
    """DataFrame con columnas [G, Tamb] indexado por timestamp."""
    idx, hours = time_axis(timestep_min)
    g = generate_irradiance(irradiance_profile, hours, sunrise, sunset, g_peak, seed)
    t_amb = generate_temperature(season, hours, t_min, t_max)

    df = pd.DataFrame({"G": g, "Tamb": t_amb}, index=idx)
    df.index.name = "timestamp"
    df["hour"] = hours
    df["is_original"] = True
    df["is_filled"] = False
    df["fill_type"] = "sintético"
    df["is_expected_daylight"] = df["G"] > 0
    df["Tamb_filled"] = False
    return df


# ===========================================================================
# Utilidades para CSV personalizados
# ===========================================================================
def normalize_column_name(name: Any) -> str:
    """Normaliza encabezados para detección tolerante a idioma, acentos y símbolos."""
    text = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode("ascii")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def read_custom_profile_table(file_or_buffer) -> pd.DataFrame:
    """Lee CSV con separador coma o punto y coma, sin alterar los encabezados."""
    if hasattr(file_or_buffer, "seek"):
        file_or_buffer.seek(0)
    try:
        df = pd.read_csv(file_or_buffer, sep=None, engine="python")
    finally:
        if hasattr(file_or_buffer, "seek"):
            file_or_buffer.seek(0)
    if df.empty:
        raise ValueError("El CSV está vacío.")
    if len(df.columns) < 2:
        raise ValueError("No fue posible separar las columnas del CSV.")
    return df


def detect_profile_columns(columns) -> dict[str, Any]:
    """Detecta candidatos para timestamp, irradiancia y temperatura."""
    original = list(columns)
    norm = {c: normalize_column_name(c) for c in original}

    timestamp_tokens = {
        "timestamp", "datetime", "date_time", "data_hora", "fecha_hora",
        "datahora", "fechahora", "time", "hora", "date", "data", "fecha",
    }
    temperature_tokens = {
        "tamb", "t_amb", "temp_amb", "temperatura_ambiente", "ambient_temperature",
        "temperature", "temperatura", "temp", "temperatura_c", "temperature_c",
        "t_c", "temp_c",
    }

    ts_candidates = [c for c in original if norm[c] in timestamp_tokens]
    if not ts_candidates:
        ts_candidates = [c for c in original if any(t in norm[c] for t in ("timestamp", "data_hora", "fecha_hora", "datetime"))]

    temp_candidates = [c for c in original if norm[c] in temperature_tokens]
    if not temp_candidates:
        temp_candidates = [
            c for c in original
            if ("temperatura" in norm[c] or "temperature" in norm[c] or norm[c].startswith("temp"))
            and "cel" not in norm[c]
        ]

    def irradiance_score(col: str) -> tuple[int, int]:
        n = norm[col]
        score = 100
        if any(x in n for x in ("predito", "previsto", "predicted", "forecast")):
            score = 0
        elif n in {"g", "ghi"}:
            score = 10
        elif "ghi" in n:
            score = 20
        elif "irradi" in n:
            score = 30
        elif "radiacao" in n or "radiation" in n:
            score = 40
        if any(x in n for x in ("real", "medido", "measured")):
            score += 15
        return score, original.index(col)

    excluded = set(ts_candidates + temp_candidates)
    irr_candidates = [
        c for c in original
        if c not in excluded
        and any(token in norm[c] for token in ("ghi", "irradi", "radiacao", "radiation"))
    ]
    if not irr_candidates:
        irr_candidates = [c for c in original if c not in excluded and norm[c] == "g"]
    irr_candidates = sorted(irr_candidates, key=irradiance_score)

    return {
        "normalized": norm,
        "timestamp_candidates": ts_candidates,
        "irradiance_candidates": irr_candidates,
        "temperature_candidates": temp_candidates,
        "timestamp_default": ts_candidates[0] if ts_candidates else (original[0] if original else None),
        "irradiance_default": irr_candidates[0] if irr_candidates else None,
        "temperature_default": temp_candidates[0] if temp_candidates else None,
    }


def _parse_timestamp(values: pd.Series) -> pd.DatetimeIndex:
    ts = values.astype(str).str.strip()
    parsed = None
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            parsed = pd.to_datetime(ts, format=fmt, errors="raise")
            break
        except (ValueError, TypeError):
            pass
    if parsed is None:
        parsed = pd.to_datetime(ts, errors="coerce")
    if pd.isna(parsed).any():
        n_bad = int(pd.isna(parsed).sum())
        raise ValueError(f"No fue posible interpretar {n_bad} timestamp(s).")
    return pd.DatetimeIndex(parsed, name="timestamp")


def _infer_timestep_seconds(index: pd.DatetimeIndex) -> int:
    if len(index) < 2:
        return 60
    deltas = pd.Series(index.sort_values()).diff().dropna().dt.total_seconds()
    deltas = deltas[deltas > 0]
    if deltas.empty:
        return 60
    mode = deltas.mode()
    value = float(mode.iloc[0]) if not mode.empty else float(deltas.median())
    return max(1, int(round(value)))


def _estimate_daylight_window(
    original_index: pd.DatetimeIndex,
    all_dates: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Interpola, por fecha, el primer y último horario observado en el CSV."""
    observed = pd.DataFrame(index=original_index)
    observed["date"] = observed.index.normalize()
    observed["minute"] = observed.index.hour * 60 + observed.index.minute + observed.index.second / 60.0
    daily = observed.groupby("date")["minute"].agg(first_min="min", last_min="max")
    daily = daily.reindex(all_dates)

    default_first = PROFILES["sunrise_h"] * 60.0
    default_last = PROFILES["sunset_h"] * 60.0
    if daily["first_min"].notna().any():
        daily["first_min"] = daily["first_min"].interpolate(limit_direction="both")
    else:
        daily["first_min"] = default_first
    if daily["last_min"].notna().any():
        daily["last_min"] = daily["last_min"].interpolate(limit_direction="both")
    else:
        daily["last_min"] = default_last
    daily["first_min"] = daily["first_min"].fillna(default_first)
    daily["last_min"] = daily["last_min"].fillna(default_last)
    return daily


def prepare_custom_profile(
    raw_df: pd.DataFrame,
    *,
    timestamp_col: str,
    irradiance_col: str,
    temperature_col: str | None = None,
    complete_days: bool = True,
    temperature_strategy: str = "constant_day_night",
    temp_day: float = 30.0,
    temp_night: float = 20.0,
    season: str = "Otoño/Primavera",
    t_min: float | None = None,
    t_max: float | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Prepara un CSV externo para la simulación.

    Los faltantes temporales se completan con G = 0 y quedan explícitamente
    clasificados en `fill_type`:
        * original
        * preenchido_noite
        * preenchido_lacuna_diurna
    """
    for col in (timestamp_col, irradiance_col):
        if col not in raw_df.columns:
            raise ValueError(f"La columna {col!r} no existe en el CSV.")
    if temperature_col is not None and temperature_col not in raw_df.columns:
        raise ValueError(f"La columna de temperatura {temperature_col!r} no existe en el CSV.")

    idx = _parse_timestamp(raw_df[timestamp_col])
    work = pd.DataFrame(index=idx)
    work["G"] = pd.to_numeric(raw_df[irradiance_col], errors="coerce").to_numpy()
    if temperature_col is not None:
        work["Tamb"] = pd.to_numeric(raw_df[temperature_col], errors="coerce").to_numpy()

    if work["G"].isna().any():
        raise ValueError(f"La columna de irradiancia contiene {int(work['G'].isna().sum())} valor(es) vacío(s) o no numérico(s).")
    if (work["G"] < 0).any():
        raise ValueError("El CSV contiene irradiancias negativas.")

    work = work.sort_index()
    duplicate_count = int(work.index.duplicated(keep=False).sum())
    if duplicate_count:
        work = work.groupby(level=0).mean(numeric_only=True)
        work.index.name = "timestamp"

    original_index = pd.DatetimeIndex(work.index)
    timestep_s = _infer_timestep_seconds(original_index)
    freq = pd.to_timedelta(timestep_s, unit="s")

    if complete_days:
        start = original_index.min().normalize()
        end = original_index.max().normalize() + pd.Timedelta(days=1) - freq
    else:
        start, end = original_index.min(), original_index.max()
    full_index = pd.date_range(start=start, end=end, freq=freq, name="timestamp")

    out = work.reindex(full_index)
    out["is_original"] = out.index.isin(original_index)
    out["is_filled"] = ~out["is_original"]

    all_dates = pd.date_range(start.normalize(), end.normalize(), freq="D")
    daylight = _estimate_daylight_window(original_index, all_dates)
    date_lookup = out.index.normalize()
    minute_of_day = out.index.hour * 60 + out.index.minute + out.index.second / 60.0
    first = daylight.loc[date_lookup, "first_min"].to_numpy()
    last = daylight.loc[date_lookup, "last_min"].to_numpy()
    expected_daylight = (minute_of_day >= first) & (minute_of_day <= last)
    out["is_expected_daylight"] = expected_daylight

    out["fill_type"] = "original"
    missing = out["is_filled"].to_numpy()
    out.loc[missing & ~expected_daylight, "fill_type"] = "preenchido_noite"
    out.loc[missing & expected_daylight, "fill_type"] = "preenchido_lacuna_diurna"
    out["G"] = out["G"].fillna(0.0)

    if temperature_col is not None:
        temp_missing_before = out["Tamb"].isna()
        out["Tamb"] = out["Tamb"].interpolate(method="time", limit_direction="both")
        if out["Tamb"].isna().any():
            raise ValueError("No fue posible completar los valores faltantes de temperatura.")
        out["Tamb_filled"] = temp_missing_before
        temperature_source = f"CSV: {temperature_col} (interpolada en faltantes)"
    elif temperature_strategy == "constant_day_night":
        out["Tamb"] = np.where(expected_daylight, float(temp_day), float(temp_night))
        out["Tamb_filled"] = True
        temperature_source = f"definida: día {temp_day:.1f} °C / noche {temp_night:.1f} °C"
    elif temperature_strategy == "standard_curve":
        hours = out.index.hour + out.index.minute / 60.0 + out.index.second / 3600.0
        out["Tamb"] = generate_temperature(
            season,
            np.asarray(hours, dtype=float),
            t_min=t_min,
            t_max=t_max,
        )
        out["Tamb_filled"] = True
        temperature_source = f"curva estándar: {season}"
    else:
        raise ValueError(f"Estrategia de temperatura desconocida: {temperature_strategy!r}")

    out["hour"] = out.index.hour + out.index.minute / 60.0 + out.index.second / 3600.0

    counts = out["fill_type"].value_counts()
    meta = {
        "timestamp_column": timestamp_col,
        "irradiance_column": irradiance_col,
        "temperature_column": temperature_col,
        "temperature_source": temperature_source,
        "start": out.index.min(),
        "end": out.index.max(),
        "timestep_seconds": timestep_s,
        "timestep_minutes": timestep_s / 60.0,
        "original_rows": int((out["fill_type"] == "original").sum()),
        "filled_rows": int(out["is_filled"].sum()),
        "filled_night_rows": int(counts.get("preenchido_noite", 0)),
        "filled_day_gap_rows": int(counts.get("preenchido_lacuna_diurna", 0)),
        "total_rows": len(out),
        "duplicates_aggregated": duplicate_count,
        "complete_days": complete_days,
    }
    out.attrs["profile_meta"] = meta
    return out, meta


def load_custom_profile(
    file_or_buffer,
    *,
    timestamp_col: str | None = None,
    irradiance_col: str | None = None,
    temperature_col: str | None = None,
    complete_days: bool = False,
    temperature_strategy: str = "constant_day_night",
    temp_day: float = 30.0,
    temp_night: float = 20.0,
    season: str = "Otoño/Primavera",
    t_min: float | None = None,
    t_max: float | None = None,
) -> pd.DataFrame:
    """
    Carga y prepara un CSV. Mantiene compatibilidad con `timestamp,G,Tamb`,
    pero también reconoce encabezados como `Timestamp,GHI_PREDITO`.
    """
    raw = read_custom_profile_table(file_or_buffer)
    detected = detect_profile_columns(raw.columns)
    timestamp_col = timestamp_col or detected["timestamp_default"]
    irradiance_col = irradiance_col or detected["irradiance_default"]
    if temperature_col is None:
        temperature_col = detected["temperature_default"]

    if timestamp_col is None:
        raise ValueError("No fue posible identificar la columna de timestamp.")
    if irradiance_col is None:
        raise ValueError("No fue posible identificar una columna de irradiancia/GHI.")
    if temperature_col is None and temperature_strategy is None:
        raise ValueError("El CSV no contiene temperatura y no se definió una estrategia térmica.")

    out, _ = prepare_custom_profile(
        raw,
        timestamp_col=timestamp_col,
        irradiance_col=irradiance_col,
        temperature_col=temperature_col,
        complete_days=complete_days,
        temperature_strategy=temperature_strategy,
        temp_day=temp_day,
        temp_night=temp_night,
        season=season,
        t_min=t_min,
        t_max=t_max,
    )
    return out


def infer_timestep_hours(df: pd.DataFrame) -> float:
    """Paso temporal representativo del perfil, en horas (para integrar energía)."""
    if len(df) < 2:
        return 1.0
    return _infer_timestep_seconds(pd.DatetimeIndex(df.index)) / 3600.0
