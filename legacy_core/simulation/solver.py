"""
simulation/solver.py
====================
Dos responsabilidades:

A) EXTRACCIÓN de los 5 parámetros del SDM (IL_ref, I0_ref, Rs, Rsh_ref, n) a
   partir de los datos de catálogo (Voc, Isc, Vmp, Imp, beta_Voc, Ns).
   Se resuelve el sistema no lineal de 5 ecuaciones de De Soto et al. (2006):

     (E1) I(V=0)   = Isc                       -> punto de cortocircuito
     (E2) I(V=Voc) = 0                         -> punto de circuito abierto
     (E3) I(Vmp)   = Imp                       -> punto de máxima potencia
     (E4) dP/dV|_{MPP} = 0                     -> el MPP es un extremo de P(V)
     (E5) dVoc/dT  = beta_Voc (catálogo)       -> cierra el sistema en T

   La (E5) se impone numéricamente: se trasladan los parámetros a
   Tc = 25 + dT, se resuelve el Voc y se compara la pendiente resultante con
   el coeficiente del fabricante. Es más robusta que la forma analítica.

   El sistema se resuelve con `scipy.optimize.least_squares` (Trust Region
   Reflective) en un espacio escalado: [IL, log10(I0), Rs, log10(Rsh), n],
   con cotas físicas. El escalado logarítmico de I0/Rsh es imprescindible:
   I0 ~ 1e-10 A y Rsh ~ 1e3 ohm difieren en 13 órdenes de magnitud.

B) TRASLACIÓN de los parámetros de referencia a cualquier condición (G, Tc)
   según De Soto et al. (2006) / modelo CEC:

     a   = a_ref * Tc/Tref
     IL  = (G/Gref) * [ IL_ref + alpha_Isc * (Tc - Tref) ]
     I0  = I0_ref * (Tc/Tref)^3 * exp[ (Eg_ref/(k*Tref) - Eg/(k*Tc)) ]
     Rsh = Rsh_ref * (Gref/G)
     Rs  = Rs_ref                     (independiente de G y Tc)
     Eg  = Eg_ref * [1 + dEgdT*(Tc - Tref)]
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import least_squares

from config.settings import (
    G_REF,
    T_REF_C,
    T_REF_K,
    KELVIN_0C,
    K_BOLTZMANN,
    Q_ELECTRON,
    SOLVER,
    EXTRACTION_BOUNDS,
    EXTRACTION_INITIAL_GUESS,
)
from models.pv_module import ModuleSTC, SDMParams, SDMOperating
from models.single_diode import open_circuit_voltage

# Constante de Boltzmann en eV/K (para el término del gap)
K_EV = K_BOLTZMANN / Q_ELECTRON


# ===========================================================================
# B) TRASLACIÓN A CONDICIONES DE OPERACIÓN
# ===========================================================================
def translate_params(
    sdm: SDMParams,
    stc: ModuleSTC,
    G: float,
    Tc: float,
) -> SDMOperating:
    """
    Traslada los 5 parámetros de referencia (STC) a la condición (G, Tc).

    G  : irradiancia efectiva [W/m2]
    Tc : temperatura de célula [°C]
    """
    G = max(float(G), SOLVER["g_min"])
    Tc_K = float(Tc) + KELVIN_0C

    # Tensión térmica modificada
    a = sdm.a_ref * (Tc_K / T_REF_K)

    # Corriente fotogenerada: lineal con G, con corrección por alpha_Isc
    IL = (G / G_REF) * (sdm.IL_ref + stc.alpha_isc * (Tc - T_REF_C))
    IL = max(IL, 0.0)

    # Corriente de saturación: dependencia ~T^3 * exp(-Eg/kT)
    eg = stc.eg_ref * (1.0 + stc.degdt * (Tc - T_REF_C))
    I0 = (
        sdm.I0_ref
        * (Tc_K / T_REF_K) ** 3
        * np.exp((stc.eg_ref / (K_EV * T_REF_K)) - (eg / (K_EV * Tc_K)))
    )

    # Resistencia paralelo: inversamente proporcional a la irradiancia
    Rsh = sdm.Rsh_ref * (G_REF / G)

    return SDMOperating(IL=IL, I0=float(I0), Rs=sdm.Rs, Rsh=Rsh, a=a, Tc=float(Tc), G=G)


# ===========================================================================
# A) EXTRACCIÓN DE LOS 5 PARÁMETROS
# ===========================================================================
@dataclass
class ExtractionReport:
    """Diagnóstico del ajuste, para mostrar en la interfaz."""
    success: bool
    cost: float
    n_iter: int
    residuals: dict
    message: str


def _residuals(x, stc: ModuleSTC, dT: float = 10.0):
    """Vector de residuos normalizados de las 5 ecuaciones de De Soto."""
    IL, log_I0, Rs, log_Rsh, n = x
    I0 = 10.0**log_I0
    Rsh = 10.0**log_Rsh
    a = n * stc.n_cells * K_BOLTZMANN * T_REF_K / Q_ELECTRON

    Voc, Isc, Vmp, Imp = stc.v_oc, stc.i_sc, stc.v_mp, stc.i_mp

    def diode(v_eq):                       # término exponencial protegido
        return np.exp(np.minimum(v_eq / a, 700.0))

    # (E1) Cortocircuito: I(0) = Isc
    r1 = IL - I0 * (diode(Isc * Rs) - 1.0) - (Isc * Rs) / Rsh - Isc

    # (E2) Circuito abierto: I(Voc) = 0
    r2 = IL - I0 * (diode(Voc) - 1.0) - Voc / Rsh

    # (E3) MPP: I(Vmp) = Imp
    v_eq_mp = Vmp + Imp * Rs
    r3 = IL - I0 * (diode(v_eq_mp) - 1.0) - v_eq_mp / Rsh - Imp

    # (E4) dP/dV = 0 en el MPP  ->  Imp + Vmp * (dI/dV)|mp = 0
    num = I0 / a * diode(v_eq_mp) + 1.0 / Rsh
    den = 1.0 + I0 * Rs / a * diode(v_eq_mp) + Rs / Rsh
    didv = -num / den
    r4 = Imp + Vmp * didv

    # (E5) Coeficiente de temperatura de Voc (impuesto numéricamente)
    sdm_try = SDMParams(IL_ref=IL, I0_ref=I0, Rs=Rs, Rsh_ref=Rsh, n=n, n_cells=stc.n_cells)
    try:
        p_hot = translate_params(sdm_try, stc, G_REF, T_REF_C + dT)
        voc_hot = open_circuit_voltage(p_hot)
        beta_model = (voc_hot - Voc) / dT
    except Exception:
        beta_model = 0.0
    r5 = beta_model - stc.beta_voc

    # Normalización: todos los residuos adimensionales y del mismo orden
    return np.array([
        r1 / Isc,
        r2 / Isc,
        r3 / Isc,
        r4 / Imp,
        r5 / abs(stc.beta_voc),
    ])


def extract_sdm_params(stc: ModuleSTC, verbose: bool = False):
    """
    Estima (IL_ref, I0_ref, Rs, Rsh_ref, n) a partir de la hoja de datos.

    Returns
    -------
    (SDMParams, ExtractionReport)
    """
    n0 = EXTRACTION_INITIAL_GUESS["n"]
    a0 = n0 * stc.n_cells * K_BOLTZMANN * T_REF_K / Q_ELECTRON
    I0_0 = stc.i_sc * np.exp(-stc.v_oc / a0)          # estimación clásica

    x0 = np.array([
        stc.i_sc,
        np.log10(max(I0_0, 1e-13)),
        EXTRACTION_INITIAL_GUESS["Rs"],
        np.log10(EXTRACTION_INITIAL_GUESS["Rsh"]),
        n0,
    ])

    b = EXTRACTION_BOUNDS
    lower = np.array([
        b["IL_factor"][0] * stc.i_sc, b["log10_I0"][0], b["Rs"][0], b["log10_Rsh"][0], b["n"][0],
    ])
    upper = np.array([
        b["IL_factor"][1] * stc.i_sc, b["log10_I0"][1], b["Rs"][1], b["log10_Rsh"][1], b["n"][1],
    ])
    x0 = np.clip(x0, lower + 1e-9, upper - 1e-9)

    sol = least_squares(
        _residuals, x0, args=(stc,), bounds=(lower, upper),
        method="trf", xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=8000,
        verbose=2 if verbose else 0,
    )

    IL, log_I0, Rs, log_Rsh, n = sol.x
    params = SDMParams(
        IL_ref=float(IL),
        I0_ref=float(10.0**log_I0),
        Rs=float(Rs),
        Rsh_ref=float(10.0**log_Rsh),
        n=float(n),
        n_cells=stc.n_cells,
        source="extracted",
    )

    names = ["Isc (E1)", "Voc (E2)", "MPP (E3)", "dP/dV=0 (E4)", "beta_Voc (E5)"]
    report = ExtractionReport(
        success=bool(sol.success) and float(sol.cost) < 1e-6,
        cost=float(sol.cost),
        n_iter=int(sol.nfev),
        residuals={k: float(v) for k, v in zip(names, sol.fun)},
        message=str(sol.message),
    )
    return params, report


# ===========================================================================
# Utilidad: parámetros SDM listos para una condición dada
# ===========================================================================
def operating_params(module, G: float, Tc: float) -> SDMOperating:
    """Atajo: PVModule + (G, Tc) -> SDMOperating."""
    if module.sdm is None:
        raise ValueError("El módulo no tiene parámetros SDM asignados.")
    return translate_params(module.sdm, module.stc, G, Tc)
