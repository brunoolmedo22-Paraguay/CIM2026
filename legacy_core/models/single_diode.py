"""
models/single_diode.py
======================
Núcleo FÍSICO del simulador: ecuación del circuito equivalente de un diodo.

    I = IL - I0 * [ exp( (V + I*Rs) / a ) - 1 ] - (V + I*Rs) / Rsh          (1)

con  a = n * Ns * k * Tc / q   (tensión térmica modificada del módulo).

La ecuación (1) es IMPLÍCITA en I (I aparece dentro de la exponencial), por lo
que se resuelve numéricamente. Se implementan tres caminos independientes:

  * "lambertw" : solución EXACTA y cerrada mediante la función W de Lambert.
                 Es la más rápida y la que se usa en la simulación temporal.
  * "brentq"   : método de Brent sobre f(I) = 0. f es monótona decreciente en I,
                 por lo que el bracketing es siempre válido. Muy robusto.
  * "newton"   : Newton-Raphson con derivada analítica. El más rápido de los
                 iterativos, con fallback automático a Brent si no converge.

Los tres deben coincidir hasta tolerancia numérica: eso se verifica en
`tests/validate.py`.

NO existe en este archivo ninguna aproximación del tipo P = Pnom*G/1000.
"""

from __future__ import annotations

from typing import Union

import numpy as np
from scipy.optimize import brentq, newton
from scipy.special import lambertw

from config.settings import SOLVER
from models.pv_module import SDMOperating

ArrayLike = Union[float, np.ndarray]


# ===========================================================================
# Utilidad: W de Lambert evaluada a partir del LOGARITMO del argumento
# ===========================================================================
def _lambertw_from_log(log_z: ArrayLike) -> np.ndarray:
    """
    Devuelve W(exp(log_z)) evitando el overflow de exp() para argumentos grandes.

    Para log_z < 500 se evalúa directamente scipy.special.lambertw.
    Para log_z >= 500 se usa la expansión asintótica (Corless et al., 1996):

        W(z) ~ L1 - L2 + L2/L1 + L2*(L2-2)/(2*L1^2) + ...
        con L1 = ln(z) = log_z ,  L2 = ln(L1)
    """
    log_z = np.asarray(log_z, dtype=float)
    out = np.empty_like(log_z)

    small = log_z < 500.0
    if np.any(small):
        out[small] = np.real(lambertw(np.exp(log_z[small])))

    big = ~small
    if np.any(big):
        L1 = log_z[big]
        L2 = np.log(L1)
        out[big] = L1 - L2 + L2 / L1 + L2 * (L2 - 2.0) / (2.0 * L1**2)

    return out


# ===========================================================================
# Residuo de la ecuación del diodo y su derivada (usados por Brent / Newton)
# ===========================================================================
def sdm_residual(I: float, V: float, p: SDMOperating) -> float:
    """f(I) = IL - I0*[exp((V+I*Rs)/a) - 1] - (V+I*Rs)/Rsh - I   ->  f(I)=0."""
    rs = max(p.Rs, SOLVER["rs_min"])
    arg = (V + I * rs) / p.a
    arg = min(arg, 700.0)                      # protección de overflow
    return (
        p.IL
        - p.I0 * (np.exp(arg) - 1.0)
        - (V + I * rs) / p.Rsh
        - I
    )


def sdm_residual_prime(I: float, V: float, p: SDMOperating) -> float:
    """df/dI (derivada analítica, para Newton-Raphson)."""
    rs = max(p.Rs, SOLVER["rs_min"])
    arg = (V + I * rs) / p.a
    arg = min(arg, 700.0)
    return -p.I0 * (rs / p.a) * np.exp(arg) - rs / p.Rsh - 1.0


# ===========================================================================
# I(V): tres implementaciones
# ===========================================================================
def _current_lambertw(V: ArrayLike, p: SDMOperating) -> np.ndarray:
    """
    Solución analítica exacta de (1) mediante la W de Lambert:

        I(V) = (Rsh*(IL + I0) - V) / (Rs + Rsh) - (a/Rs) * W(z)

        z = (Rs*I0*Rsh) / (a*(Rs+Rsh)) * exp[ Rsh*(Rs*IL + Rs*I0 + V) / (a*(Rs+Rsh)) ]

    Se evalúa W a partir de ln(z) para evitar el overflow de exp().
    """
    V = np.asarray(V, dtype=float)
    rs = max(p.Rs, SOLVER["rs_min"])
    rsh, a, IL, I0 = p.Rsh, p.a, p.IL, p.I0

    denom = a * (rs + rsh)
    log_z = np.log(rs * I0 * rsh / denom) + rsh * (rs * IL + rs * I0 + V) / denom
    W = _lambertw_from_log(log_z)

    I = (rsh * (IL + I0) - V) / (rs + rsh) - (a / rs) * W
    return I


def _current_brentq(V: float, p: SDMOperating) -> float:
    """Método de Brent: f(I)=0 sobre un bracket garantizado."""
    lo = -abs(p.IL) - 5.0                       # f(lo) > 0
    hi = p.IL + p.I0 + 5.0                      # f(hi) < 0
    f_lo, f_hi = sdm_residual(lo, V, p), sdm_residual(hi, V, p)
    if f_lo * f_hi > 0:                         # bracket degenerado (G ~ 0)
        return float(_current_lambertw(V, p))
    return brentq(
        sdm_residual, lo, hi, args=(V, p),
        xtol=SOLVER["current_tol"], maxiter=SOLVER["max_iter"],
    )


def _current_newton(V: float, p: SDMOperating) -> float:
    """Newton-Raphson con derivada analítica; fallback a Brent si diverge."""
    try:
        I = newton(
            sdm_residual, x0=p.IL, fprime=sdm_residual_prime, args=(V, p),
            tol=SOLVER["current_tol"], maxiter=SOLVER["max_iter"],
        )
        if not np.isfinite(I):
            raise RuntimeError
        return float(I)
    except (RuntimeError, OverflowError, FloatingPointError):
        return _current_brentq(V, p)


def current_from_voltage(V: ArrayLike, p: SDMOperating, method: str | None = None) -> ArrayLike:
    """
    Corriente del módulo para una tensión V [V] y una condición (G, Tc).

    method: "lambertw" (vectorizado) | "brentq" | "newton"
    """
    method = method or SOLVER["method"]

    if method == "lambertw":
        out = _current_lambertw(V, p)
        return float(out) if np.ndim(V) == 0 else out

    scalar_solver = _current_brentq if method == "brentq" else _current_newton
    if np.ndim(V) == 0:
        return scalar_solver(float(V), p)
    return np.array([scalar_solver(float(v), p) for v in np.asarray(V)])


def voltage_from_current(I: float, p: SDMOperating) -> float:
    """
    Tensión del módulo para una corriente dada (útil para curvas V(I)).
    Se despeja explícitamente de (1) usando la forma logarítmica:

        V = a*ln( (IL + I0 - I - (V+I*Rs)/Rsh)/I0 + 1 ) - I*Rs
    -> implícita también; se resuelve con Brent sobre V in [0, Voc].
    """
    v_oc = open_circuit_voltage(p)
    if I <= 0.0:
        return v_oc

    def f(V):
        return current_from_voltage(V, p, method="lambertw") - I

    if f(0.0) < 0:      # I mayor que Isc -> no hay solución física
        return 0.0
    return brentq(f, 0.0, v_oc, xtol=1e-8, maxiter=SOLVER["max_iter"])


# ===========================================================================
# Puntos característicos
# ===========================================================================
def short_circuit_current(p: SDMOperating) -> float:
    """Isc = I(V=0)."""
    return float(current_from_voltage(0.0, p, method="lambertw"))


def open_circuit_voltage(p: SDMOperating) -> float:
    """
    Voc: raíz de I(V) = 0.
    Cota superior segura: Voc_ideal = a*ln(IL/I0 + 1) (caso Rsh -> inf, Rs -> 0).
    """
    if p.IL <= 0.0:
        return 0.0
    v_hi = p.a * np.log(p.IL / max(p.I0, 1e-30) + 1.0)
    v_hi = max(v_hi, 1e-3) * 1.05

    f = lambda V: float(current_from_voltage(V, p, method="lambertw"))
    if f(0.0) <= 0.0:
        return 0.0
    if f(v_hi) > 0.0:                          # ampliar por seguridad
        v_hi *= 2.0
        if f(v_hi) > 0.0:
            return v_hi
    return brentq(f, 0.0, v_hi, xtol=1e-9, maxiter=SOLVER["max_iter"])


# ===========================================================================
# Curvas I-V y P-V completas
# ===========================================================================
def iv_curve(p: SDMOperating, n_points: int | None = None, method: str | None = None):
    """
    Devuelve (V, I, P) con la curva I-V y P-V completas entre 0 y Voc.

    El muestreo se densifica cerca del codo (zona del MPP) usando una
    distribución no uniforme, para no perder resolución donde importa.
    """
    n_points = n_points or SOLVER["iv_points"]
    v_oc = open_circuit_voltage(p)
    if v_oc <= 0.0:
        z = np.zeros(n_points)
        return z, z, z

    # Malla no uniforme: más densa en el tramo alto (codo + rodilla)
    u = np.linspace(0.0, 1.0, n_points)
    V = v_oc * (0.55 * u + 0.45 * u**2)
    V = np.unique(np.concatenate([V, [v_oc]]))

    I = np.asarray(current_from_voltage(V, p, method=method))
    I = np.clip(I, 0.0, None)                  # 1er cuadrante
    P = V * I
    return V, I, P
