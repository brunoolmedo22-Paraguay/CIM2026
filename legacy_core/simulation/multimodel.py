"""Motor comum dos três modelos fotovoltaicos.

O módulo mantém todos os modelos sobre a mesma irradiância, temperatura,
módulo e arranjo elétrico. O CSV conserva a janela operacional de 120 minutos;
o gerador sintético também pode produzir um dia completo, sempre com passo de
um minuto.

Modelos:
    1. Irradiância: P = P_STC * G/G_STC.
    2. NOCT + eficiência: calcula Tc, corrige eta com gamma_Pmax e usa P=eta*G*A.
    3. SDM: resolve o modelo de um diodo e localiza numericamente o MPP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable
import re

import numpy as np
import pandas as pd

from config.settings import G_REF, T_REF_C
from models.irradiance_model import (
    detect_profile_columns,
    generate_irradiance,
    generate_temperature,
    infer_timestep_hours,
    read_custom_profile_table,
)
from models.pv_module import PVModule
from models.temperature_model import cell_temperature_noct
from simulation.mpp import simulate_timeseries


WINDOW_MINUTES = 120
TIMESTEP_MINUTES = 1

MODEL_SIMPLE = "irradiancia"
MODEL_NOCT = "noct_eficiencia"
MODEL_SDM = "sdm"

MODEL_ORDER = (MODEL_SIMPLE, MODEL_NOCT, MODEL_SDM)
MODEL_LABELS = {
    MODEL_SIMPLE: "Modelo 1 · Irradiância",
    MODEL_NOCT: "Modelo 2 · NOCT + eficiência",
    MODEL_SDM: "Modelo 3 · Single Diode Model",
}
MODEL_SHORT_LABELS = {
    MODEL_SIMPLE: "Irradiância",
    MODEL_NOCT: "NOCT + eficiência",
    MODEL_SDM: "SDM",
}
MODEL_COLORS = {
    MODEL_SIMPLE: "#2F80ED",
    MODEL_NOCT: "#16A085",
    MODEL_SDM: "#F2994A",
}


@dataclass(frozen=True)
class ModelStatus:
    available: bool
    message: str


def read_input_csv(file_or_buffer) -> pd.DataFrame:
    """Lê CSV com separador detectado automaticamente."""
    return read_custom_profile_table(file_or_buffer)


def detect_input_columns(raw: pd.DataFrame) -> dict:
    """Expõe a detecção tolerante de timestamp, GHI e temperatura."""
    return detect_profile_columns(raw.columns)


def _numeric(values: pd.Series) -> pd.Series:
    """Converte números aceitando tanto ponto quanto vírgula decimal."""
    if pd.api.types.is_numeric_dtype(values):
        return pd.to_numeric(values, errors="coerce")
    cleaned = values.astype(str).str.strip().str.replace(" ", "", regex=False)
    cleaned = cleaned.str.replace(",", ".", regex=False)
    return pd.to_numeric(cleaned, errors="coerce")


def _timestamps(values: pd.Series) -> pd.DatetimeIndex:
    parsed = pd.to_datetime(values.astype(str).str.strip(), errors="coerce")
    if parsed.isna().any():
        raise ValueError(
            f"A coluna de timestamp contém {int(parsed.isna().sum())} valor(es) inválido(s)."
        )
    return pd.DatetimeIndex(parsed, name="timestamp")


def candidate_window_starts(raw: pd.DataFrame, timestamp_col: str) -> list[pd.Timestamp]:
    """Retorna instantes que ainda comportam uma janela nominal de 120 min."""
    if timestamp_col not in raw.columns:
        return []
    idx = _timestamps(raw[timestamp_col]).drop_duplicates().sort_values()
    if len(idx) < WINDOW_MINUTES:
        return []
    last_allowed = idx.max() - pd.Timedelta(minutes=WINDOW_MINUTES - 1)
    return [pd.Timestamp(ts) for ts in idx[idx <= last_allowed]]


def prepare_uploaded_profile(
    raw: pd.DataFrame,
    *,
    timestamp_col: str,
    irradiance_col: str,
    temperature_col: str | None,
    start: pd.Timestamp | str | None = None,
) -> pd.DataFrame:
    """Normaliza e valida uma janela CSV de 120 linhas a cada um minuto.

    A temperatura é deliberadamente opcional. Se estiver ausente ou incompleta,
    ela permanece como NaN: o orquestrador executará somente o modelo simples.
    Não há preenchimento térmico silencioso.
    """
    required = [timestamp_col, irradiance_col]
    missing = [col for col in required if col not in raw.columns]
    if missing:
        raise ValueError("Colunas não encontradas: " + ", ".join(missing))
    if temperature_col is not None and temperature_col not in raw.columns:
        raise ValueError(f"A coluna de temperatura {temperature_col!r} não existe.")

    idx = _timestamps(raw[timestamp_col])
    profile = pd.DataFrame(index=idx)
    profile["G"] = _numeric(raw[irradiance_col]).to_numpy()
    if temperature_col is not None:
        profile["Tamb"] = _numeric(raw[temperature_col]).to_numpy()
    else:
        profile["Tamb"] = np.nan

    if profile.index.has_duplicates:
        duplicates = int(profile.index.duplicated(keep=False).sum())
        raise ValueError(f"O CSV contém {duplicates} registro(s) com timestamp duplicado.")
    profile = profile.sort_index()

    if start is None:
        start_ts = pd.Timestamp(profile.index.min())
    else:
        start_ts = pd.Timestamp(start)
    expected_index = pd.date_range(
        start=start_ts,
        periods=WINDOW_MINUTES,
        freq=f"{TIMESTEP_MINUTES}min",
        name="timestamp",
    )
    profile = profile.reindex(expected_index)

    invalid_g = int(profile["G"].isna().sum())
    if invalid_g:
        raise ValueError(
            "A janela deve conter exatamente 120 valores consecutivos de irradiância "
            f"a cada 1 minuto; faltam ou são inválidos {invalid_g} valor(es)."
        )
    if not np.isfinite(profile["G"].to_numpy(dtype=float)).all():
        raise ValueError("A irradiância contém valores não finitos.")
    if (profile["G"] < 0).any():
        raise ValueError("A irradiância não pode conter valores negativos.")

    profile["is_original"] = True
    profile["is_filled"] = False
    profile["fill_type"] = "original"
    profile["is_expected_daylight"] = profile["G"] > 0
    profile["Tamb_filled"] = False
    profile.attrs.update(
        source="csv",
        timestamp_column=timestamp_col,
        irradiance_column=irradiance_col,
        temperature_column=temperature_col,
        temperature_available=bool(profile["Tamb"].notna().all()),
        start=profile.index.min(),
        end=profile.index.max(),
        rows=len(profile),
        timestep_minutes=TIMESTEP_MINUTES,
    )
    return profile


def build_synthetic_profile(
    *,
    start: pd.Timestamp | str,
    irradiance_profile: str,
    season: str,
    duration_minutes: int = WINDOW_MINUTES,
    g_peak: float | None = None,
    t_min: float | None = None,
    t_max: float | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Cria um perfil sintético reproduzível com passo de um minuto."""
    duration_minutes = int(duration_minutes)
    if duration_minutes <= 0:
        raise ValueError("A duração do perfil sintético deve ser maior que zero.")
    idx = pd.date_range(
        start=pd.Timestamp(start), periods=duration_minutes, freq="1min", name="timestamp"
    )
    hours = idx.hour + idx.minute / 60.0 + idx.second / 3600.0
    g = generate_irradiance(
        irradiance_profile,
        np.asarray(hours, dtype=float),
        g_peak=g_peak,
        seed=int(seed),
    )
    tamb = generate_temperature(
        season,
        np.asarray(hours, dtype=float),
        t_min=t_min,
        t_max=t_max,
    )
    profile = pd.DataFrame({"G": g, "Tamb": tamb}, index=idx)
    profile["is_original"] = True
    profile["is_filled"] = False
    profile["fill_type"] = "sintético"
    profile["is_expected_daylight"] = profile["G"] > 0
    profile["Tamb_filled"] = False
    profile.attrs.update(
        source="sintético",
        temperature_available=True,
        start=profile.index.min(),
        end=profile.index.max(),
        rows=len(profile),
        timestep_minutes=TIMESTEP_MINUTES,
        irradiance_profile=irradiance_profile,
        season=season,
        duration_minutes=duration_minutes,
    )
    return profile


def build_synthetic_profile_120min(
    *,
    start: pd.Timestamp | str,
    irradiance_profile: str,
    season: str,
    g_peak: float | None = None,
    t_min: float | None = None,
    t_max: float | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Compatibilidade: cria a janela sintética original de 120 minutos."""
    return build_synthetic_profile(
        start=start,
        irradiance_profile=irradiance_profile,
        season=season,
        duration_minutes=WINDOW_MINUTES,
        g_peak=g_peak,
        t_min=t_min,
        t_max=t_max,
        seed=seed,
    )


def _common_result(
    module: PVModule,
    profile: pd.DataFrame,
    *,
    n_series: int,
    n_parallel: int,
    soiling_losses: float,
) -> tuple[pd.DataFrame, np.ndarray, int]:
    n_modules = int(n_series) * int(n_parallel)
    if n_modules < 1:
        raise ValueError("O arranjo deve conter pelo menos um módulo.")
    if not 0.0 <= float(soiling_losses) < 1.0:
        raise ValueError("As perdas ópticas devem estar no intervalo [0, 1).")

    g_raw = profile["G"].to_numpy(dtype=float)
    g_eff = g_raw * (1.0 - float(soiling_losses))
    tamb = profile["Tamb"].to_numpy(dtype=float) if "Tamb" in profile else np.full(len(profile), np.nan)
    out = pd.DataFrame(
        {"G": g_raw, "G_eff": g_eff, "Tamb": tamb}, index=profile.index.copy()
    )
    out["P_disp"] = g_raw * module.stc.area * n_modules
    for col in ("is_original", "is_filled", "fill_type", "is_expected_daylight", "Tamb_filled"):
        if col in profile.columns:
            out[col] = profile[col].to_numpy()
    out.attrs.update(
        n_modules=n_modules,
        n_series=int(n_series),
        n_parallel=int(n_parallel),
        p_nom_array_W=module.stc.p_nom * n_modules,
        area_array_m2=module.stc.area * n_modules,
        soiling_losses=float(soiling_losses),
        module_name=module.name,
    )
    return out, g_eff, n_modules


def _finalize_result(out: pd.DataFrame, model_id: str) -> pd.DataFrame:
    dt_h = infer_timestep_hours(out)
    out["energy_step_Wh"] = out["P_array"].astype(float) * dt_h
    out.attrs["model_id"] = model_id
    out.attrs["model_label"] = MODEL_LABELS[model_id]
    out.attrs["dt_hours"] = dt_h
    return out


def simulate_irradiance_model(
    module: PVModule,
    profile: pd.DataFrame,
    *,
    n_series: int = 2,
    n_parallel: int = 3,
    soiling_losses: float = 0.0,
) -> pd.DataFrame:
    """Modelo 1: potência proporcional à irradiância e à potência de placa."""
    out, g_eff, n_modules = _common_result(
        module,
        profile,
        n_series=n_series,
        n_parallel=n_parallel,
        soiling_losses=soiling_losses,
    )
    p_module = module.stc.p_nom * g_eff / G_REF
    eta_const = module.stc.efficiency_stc
    out["Tc"] = np.nan
    out["eta"] = np.where(g_eff > 0, eta_const, 0.0)
    out["P_module"] = p_module
    out["P_array"] = p_module * n_modules
    out["P_lineal_ref"] = out["P_array"]
    return _finalize_result(out, MODEL_SIMPLE)


def simulate_noct_efficiency_model(
    module: PVModule,
    profile: pd.DataFrame,
    *,
    n_series: int = 2,
    n_parallel: int = 3,
    soiling_losses: float = 0.0,
    noct: float | None = None,
) -> pd.DataFrame:
    """Modelo 2: temperatura NOCT e eficiência corrigida por gamma_Pmax."""
    if "Tamb" not in profile or profile["Tamb"].isna().any():
        raise ValueError("O modelo NOCT + eficiência requer Tamb completa em toda a janela.")
    out, g_eff, n_modules = _common_result(
        module,
        profile,
        n_series=n_series,
        n_parallel=n_parallel,
        soiling_losses=soiling_losses,
    )
    noct_value = module.stc.noct if noct is None else float(noct)
    tc = np.asarray(cell_temperature_noct(out["Tamb"].to_numpy(), g_eff, noct_value), dtype=float)
    gamma_rel = module.stc.gamma_pmax_pct / 100.0
    thermal_factor = np.clip(1.0 + gamma_rel * (tc - T_REF_C), 0.0, None)
    eta = module.stc.efficiency_stc * thermal_factor
    p_module = eta * g_eff * module.stc.area

    out["Tc"] = tc
    out["thermal_factor"] = thermal_factor
    out["eta"] = np.where(g_eff > 0, eta, 0.0)
    out["P_module"] = p_module
    out["P_array"] = p_module * n_modules
    out["P_lineal_ref"] = module.stc.p_nom * g_eff / G_REF * n_modules
    out.attrs["noct"] = noct_value
    out.attrs["gamma_pmax_pct_C"] = module.stc.gamma_pmax_pct
    return _finalize_result(out, MODEL_NOCT)


def simulate_sdm_model(
    module: PVModule,
    profile: pd.DataFrame,
    *,
    n_series: int = 2,
    n_parallel: int = 3,
    soiling_losses: float = 0.0,
    noct: float | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> pd.DataFrame:
    """Modelo 3: SDM completo com MPP ideal resolvido em cada minuto."""
    if module.sdm is None:
        raise ValueError("O módulo não possui parâmetros SDM.")
    if "Tamb" not in profile or profile["Tamb"].isna().any():
        raise ValueError("O SDM requer Tamb completa em toda a janela.")

    out = simulate_timeseries(
        module,
        profile,
        noct=module.stc.noct if noct is None else float(noct),
        n_series=int(n_series),
        n_parallel=int(n_parallel),
        soiling_losses=float(soiling_losses),
        progress_callback=progress_callback,
    )
    out["P_module"] = out["Pmp"]
    out["Vmp_array"] = out["Vmp"] * int(n_series)
    out["Imp_array"] = out["Imp"] * int(n_parallel)
    out["Voc_array"] = out["Voc"] * int(n_series)
    out["Isc_array"] = out["Isc"] * int(n_parallel)
    return _finalize_result(out, MODEL_SDM)


def run_all_models(
    module: PVModule,
    profile: pd.DataFrame,
    *,
    n_series: int = 2,
    n_parallel: int = 3,
    soiling_losses: float = 0.0,
    noct: float | None = None,
    progress_callback: Callable[[float], None] | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, ModelStatus]]:
    """Executa todos os modelos possíveis e registra a degradação por falta de Tamb."""
    results: dict[str, pd.DataFrame] = {}
    statuses: dict[str, ModelStatus] = {}

    results[MODEL_SIMPLE] = simulate_irradiance_model(
        module,
        profile,
        n_series=n_series,
        n_parallel=n_parallel,
        soiling_losses=soiling_losses,
    )
    statuses[MODEL_SIMPLE] = ModelStatus(True, "Executado com irradiância e potência nominal.")

    has_temperature = "Tamb" in profile and bool(profile["Tamb"].notna().all())
    if not has_temperature:
        reason = "Temperatura ambiente ausente ou incompleta; modelo não executado."
        statuses[MODEL_NOCT] = ModelStatus(False, reason)
        statuses[MODEL_SDM] = ModelStatus(False, reason)
        return results, statuses

    try:
        results[MODEL_NOCT] = simulate_noct_efficiency_model(
            module,
            profile,
            n_series=n_series,
            n_parallel=n_parallel,
            soiling_losses=soiling_losses,
            noct=noct,
        )
        statuses[MODEL_NOCT] = ModelStatus(True, "Executado com temperatura de célula via NOCT.")
    except Exception as exc:
        statuses[MODEL_NOCT] = ModelStatus(False, f"Falha no modelo: {exc}")

    try:
        results[MODEL_SDM] = simulate_sdm_model(
            module,
            profile,
            n_series=n_series,
            n_parallel=n_parallel,
            soiling_losses=soiling_losses,
            noct=noct,
            progress_callback=progress_callback,
        )
        statuses[MODEL_SDM] = ModelStatus(True, "Executado com o SDM completo e MPP ideal.")
    except Exception as exc:
        statuses[MODEL_SDM] = ModelStatus(False, f"Falha no modelo: {exc}")

    return results, statuses


def compute_model_kpis(results: pd.DataFrame, module: PVModule) -> dict[str, float | pd.Timestamp]:
    """Indicadores comparáveis para qualquer um dos três modelos."""
    dt_h = float(results.attrs.get("dt_hours", infer_timestep_hours(results)))
    p = results["P_array"].to_numpy(dtype=float)
    g_eff = results["G_eff"].to_numpy(dtype=float)
    n_modules = int(results.attrs.get("n_modules", 1))
    area_array = float(results.attrs.get("area_array_m2", module.stc.area * n_modules))
    p_nom_kw = float(results.attrs.get("p_nom_array_W", module.stc.p_nom * n_modules)) / 1000.0

    energy_kwh = float(np.sum(p) * dt_h / 1000.0)
    irradiation_kwh_m2 = float(np.sum(g_eff) * dt_h / 1000.0)
    incident_kwh = irradiation_kwh_m2 * area_array
    eta_energy = energy_kwh / incident_kwh if incident_kwh > 0 else 0.0
    specific_yield = energy_kwh / p_nom_kw if p_nom_kw > 0 else 0.0
    pr = specific_yield / irradiation_kwh_m2 if irradiation_kwh_m2 > 0 else 0.0
    duration_h = len(results) * dt_h
    cf = energy_kwh / (p_nom_kw * duration_h) if p_nom_kw > 0 and duration_h > 0 else 0.0

    peak_i = int(np.argmax(p)) if len(p) else 0
    tc = results["Tc"].to_numpy(dtype=float) if "Tc" in results else np.full(len(results), np.nan)
    finite_tc = tc[np.isfinite(tc)]
    eta = results["eta"].to_numpy(dtype=float) if "eta" in results else np.zeros(len(results))

    return {
        "energy_kWh": energy_kwh,
        "p_max_W": float(np.max(p)) if len(p) else 0.0,
        "p_mean_W": float(np.mean(p)) if len(p) else 0.0,
        "t_peak": results.index[peak_i] if len(results) else pd.NaT,
        "eta_energy": eta_energy,
        "eta_max": float(np.max(eta)) if len(eta) else 0.0,
        "tc_max_C": float(np.max(finite_tc)) if finite_tc.size else np.nan,
        "tc_mean_C": float(np.mean(finite_tc)) if finite_tc.size else np.nan,
        "irradiation_kWh_m2": irradiation_kwh_m2,
        "specific_yield_kWh_kWp": specific_yield,
        "PR": pr,
        "CF": cf,
        "duration_h": duration_h,
        "rows": len(results),
    }


EXPORT_COLUMN_SPECS: dict[str, tuple[str, str | None, Callable | None]] = {
    "Timestamp": ("timestamp", None, None),
    "Irradiância GHI [W/m²]": ("ghi_W_m2", "G", None),
    "Irradiância efetiva [W/m²]": ("irradiancia_efetiva_W_m2", "G_eff", None),
    "Temperatura ambiente [°C]": ("temperatura_ambiente_C", "Tamb", None),
    "Temperatura da célula [°C]": ("temperatura_celula_C", "Tc", None),
    "Potência do módulo [W]": ("potencia_modulo_W", "P_module", None),
    "Potência gerada pelo arranjo [W]": ("potencia_gerada_W", "P_array", None),
    "Energia gerada no passo [Wh]": ("energia_passo_Wh", "energy_step_Wh", None),
    "Eficiência [%]": ("eficiencia_pct", "eta", lambda s: s.astype(float) * 100.0),
    "Potência solar incidente [W]": ("potencia_solar_incidente_W", "P_disp", None),
    "Tensão MPP do módulo [V]": ("vmp_modulo_V", "Vmp", None),
    "Corrente MPP do módulo [A]": ("imp_modulo_A", "Imp", None),
    "Tensão MPP do arranjo [V]": ("vmp_arranjo_V", "Vmp_array", None),
    "Corrente MPP do arranjo [A]": ("imp_arranjo_A", "Imp_array", None),
    "Tensão de circuito aberto [V]": ("voc_modulo_V", "Voc", None),
    "Corrente de curto-circuito [A]": ("isc_modulo_A", "Isc", None),
    "Fator de forma [-]": ("fator_forma", "FF", None),
}

DEFAULT_EXPORT_COLUMNS = ("Timestamp", "Potência gerada pelo arranjo [W]")


def available_export_columns(results: pd.DataFrame) -> list[str]:
    return [
        label
        for label, (_, source, _) in EXPORT_COLUMN_SPECS.items()
        if source is None or source in results.columns
    ]


def build_export_dataframe(results: pd.DataFrame, selected_labels: Iterable[str]) -> pd.DataFrame:
    labels = list(selected_labels)
    if not labels:
        raise ValueError("Selecione pelo menos uma coluna para exportar.")
    unknown = [label for label in labels if label not in EXPORT_COLUMN_SPECS]
    if unknown:
        raise KeyError("Colunas desconhecidas: " + ", ".join(unknown))

    export = pd.DataFrame(index=results.index)
    for label in labels:
        csv_name, source, transform = EXPORT_COLUMN_SPECS[label]
        if source is None:
            export[csv_name] = results.index.strftime("%Y-%m-%d %H:%M:%S")
            continue
        if source not in results.columns:
            raise KeyError(f"A coluna {source!r} não existe neste modelo.")
        series = results[source]
        export[csv_name] = transform(series).to_numpy() if transform else series.to_numpy()
    return export.reset_index(drop=True)


def normalize_filename(value: str, default: str = "modelo_solar_120min") -> str:
    name = (value or "").strip()
    if name.lower().endswith(".csv"):
        name = name[:-4]
    name = re.sub(r"[<>:\"/\\|?*]+", "_", name)
    name = re.sub(r"\s+", "_", name).strip("._ ") or default
    return f"{name}.csv"
