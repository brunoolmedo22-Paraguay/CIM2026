"""
simulation/mpp.py
=================
Búsqueda del Maximum Power Point (MPP) y motor de simulación temporal.

IMPORTANTE (hipótesis del enunciado):
    No se implementa ningún algoritmo MPPT (P&O, IncCond, ...).
    Se asume que el sistema opera SIEMPRE en el MPP:  Pout(t) = Pmp(t).

El MPP NO se asume ni se aproxima: en cada instante se resuelve la curva P(V)
del SDM y se localiza numéricamente su máximo.

Estrategia de búsqueda (robusta y sin derivadas de segundo orden):
  1. Barrido grueso vectorizado de P(V) sobre [0, Voc] (Lambert W).
  2. Refinamiento con minimización acotada de -P(V) (método de Brent,
     `scipy.optimize.minimize_scalar(method="bounded")`) en el intervalo
     que rodea al máximo del barrido.

Esto evita quedar atrapado en el óptimo local aproximado del barrido y
garantiza convergencia a la tolerancia definida en config/settings.py.
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar

from config.settings import SOLVER, G_REF, T_REF_C
from models.pv_module import PVModule, SDMOperating
from models.single_diode import (
    current_from_voltage,
    open_circuit_voltage,
    short_circuit_current,
)
from models.temperature_model import cell_temperature_noct
from simulation.solver import translate_params


# ===========================================================================
# MPP en una condición (G, Tc)
# ===========================================================================
def find_mpp(p: SDMOperating, coarse_points: int = 60, method: str | None = None) -> dict:
    """
    Localiza el MPP de la curva P-V correspondiente a los parámetros `p`.

    Returns
    -------
    dict con Vmp, Imp, Pmp, Voc, Isc, FF
    """
    voc = open_circuit_voltage(p)
    if voc <= 0.0 or p.IL <= 0.0:
        return dict(Vmp=0.0, Imp=0.0, Pmp=0.0, Voc=0.0, Isc=0.0, FF=0.0)

    isc = short_circuit_current(p)

    # --- 1) Barrido grueso vectorizado ------------------------------------
    V = np.linspace(0.35 * voc, voc, coarse_points)
    I = np.asarray(current_from_voltage(V, p, method="lambertw"))
    P = V * np.clip(I, 0.0, None)
    k = int(np.argmax(P))
    lo = V[max(k - 1, 0)]
    hi = V[min(k + 1, coarse_points - 1)]

    # --- 2) Refinamiento (Brent acotado sobre -P(V)) ----------------------
    def neg_power(v: float) -> float:
        i = float(current_from_voltage(float(v), p, method=method or "lambertw"))
        return -v * max(i, 0.0)

    res = minimize_scalar(
        neg_power, bounds=(lo, hi), method="bounded",
        options={"xatol": SOLVER["mpp_tol"], "maxiter": SOLVER["max_iter"]},
    )

    v_mp = float(res.x)
    p_mp = float(-res.fun)
    i_mp = p_mp / v_mp if v_mp > 0 else 0.0

    # Si el refinamiento empeoró (no debería), se conserva el barrido
    if p_mp < P[k]:
        v_mp, p_mp = float(V[k]), float(P[k])
        i_mp = p_mp / v_mp if v_mp > 0 else 0.0

    ff = p_mp / (voc * isc) if (voc * isc) > 0 else 0.0
    return dict(Vmp=v_mp, Imp=i_mp, Pmp=p_mp, Voc=voc, Isc=isc, FF=ff)


def mpp_at_conditions(module: PVModule, G: float, Tc: float) -> dict:
    """Atajo: MPP directamente desde (módulo, G, Tc)."""
    if G < SOLVER["g_min"]:
        return dict(Vmp=0.0, Imp=0.0, Pmp=0.0, Voc=0.0, Isc=0.0, FF=0.0)
    p = translate_params(module.sdm, module.stc, G, Tc)
    return find_mpp(p)


# ===========================================================================
# Simulación temporal
# ===========================================================================
def simulate_timeseries(
    module: PVModule,
    profile: pd.DataFrame,
    noct: Optional[float] = None,
    n_series: int = 1,
    n_parallel: int = 1,
    soiling_losses: float = 0.0,
    progress_callback: Optional[Callable[[float], None]] = None,
) -> pd.DataFrame:
    """
    Ejecuta la simulación paso a paso (típicamente minuto a minuto).

    Para CADA instante:
        1. Obtener G y Tamb del perfil.
        2. Calcular Tc con el modelo térmico (NOCT).
        3. Trasladar los 5 parámetros del SDM a (G, Tc).
        4. Resolver la curva I-V / P-V completa.
        5. Encontrar el MPP (Vmp, Imp, Pmp).
        6. Guardar resultados + eficiencia instantánea.

    Parameters
    ----------
    module    : PVModule con parámetros SDM asignados.
    profile   : DataFrame con columnas [G, Tamb] indexado por timestamp.
    noct      : NOCT [°C] (si None se toma el del módulo).
    n_series / n_parallel : nº de módulos del string/array (escalado del array).
    soiling_losses : pérdidas ópticas de suciedad aplicadas a G [0-1].

    Returns
    -------
    DataFrame con G, Tamb, Tc, Vmp, Imp, Pmp, Voc, Isc, FF, eta,
    P_array, P_disp.
    """
    stc = module.stc
    noct = stc.noct if noct is None else float(noct)
    n_mod = int(n_series) * int(n_parallel)

    g_raw = profile["G"].to_numpy(dtype=float)
    g_eff = g_raw * (1.0 - float(soiling_losses))       # irradiancia efectiva
    t_amb = profile["Tamb"].to_numpy(dtype=float)
    t_cell = np.asarray(cell_temperature_noct(t_amb, g_eff, noct), dtype=float)

    n = len(profile)
    cols = {k: np.zeros(n) for k in ("Vmp", "Imp", "Pmp", "Voc", "Isc", "FF")}

    for i in range(n):
        g_i = g_eff[i]
        if g_i < SOLVER["g_min"]:
            continue                                    # noche: módulo inactivo
        p = translate_params(module.sdm, stc, g_i, t_cell[i])
        mpp = find_mpp(p)
        for k in cols:
            cols[k][i] = mpp[k]

        if progress_callback is not None and (i % 25 == 0 or i == n - 1):
            progress_callback((i + 1) / n)

    out = pd.DataFrame(cols, index=profile.index)
    out.insert(0, "G", g_raw)
    out.insert(1, "G_eff", g_eff)
    out.insert(2, "Tamb", t_amb)
    out.insert(3, "Tc", t_cell)

    # Mantener la trazabilidad del CSV preparado. Estas columnas no participan
    # de la física, pero permiten identificar qué filas fueron originales y
    # cuáles fueron completadas por la plataforma.
    for trace_col in (
        "is_original", "is_filled", "fill_type",
        "is_expected_daylight", "Tamb_filled",
    ):
        if trace_col in profile.columns:
            out[trace_col] = profile[trace_col].to_numpy()

    # Eficiencia instantánea de conversión del módulo (área bruta)
    denom = out["G_eff"].to_numpy() * stc.area
    with np.errstate(divide="ignore", invalid="ignore"):
        eta = np.where(denom > 0, out["Pmp"].to_numpy() / denom, 0.0)
    out["eta"] = eta

    # Potencia del array (escalado por nº de módulos, MPPT ideal)
    out["P_array"] = out["Pmp"] * n_mod

    # Potencia solar DISPONIBLE sobre la superficie de captación [W]
    out["P_disp"] = out["G"] * stc.area * n_mod

    # Referencia lineal SOLO para comparación gráfica (NO se usa en el modelo)
    out["P_lineal_ref"] = stc.p_nom * out["G"] / G_REF * n_mod

    out.attrs["n_modules"] = n_mod
    out.attrs["n_series"] = int(n_series)
    out.attrs["n_parallel"] = int(n_parallel)
    out.attrs["p_nom_array_W"] = stc.p_nom * n_mod
    out.attrs["area_array_m2"] = stc.area * n_mod
    out.attrs["noct"] = noct
    return out
