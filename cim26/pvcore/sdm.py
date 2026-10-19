"""Núcleo físico do modelo de um diodo (M4 · SDM).

Portado de ``legacy_core/models/single_diode.py``, ``legacy_core/simulation/solver.py``
(função ``translate_params``) e ``legacy_core/simulation/mpp.py`` (``find_mpp``).
As equações, tolerâncias e a sequência algorítmica são as do legado; a única
mudança é que a tradução recebe ``a_ref`` diretamente (necessário para a
calibração SUPSI sem Ns) e que o MPP devolve diagnósticos de convergência.
A equivalência numérica com o legado é verificada em
``tests/test_regression_legacy.py``.

    I = IL - I0 [exp((V + I Rs)/a) - 1] - (V + I Rs)/Rsh                      (1)

Tradução De Soto/CEC (legado):
    a   = a_ref · Tc_K/Tref_K
    IL  = (G/Gref) · [IL_ref + alpha_Isc (Tc - 25)]
    I0  = I0_ref (Tc_K/Tref_K)^3 exp[Eg_ref/(k Tref_K) - Eg(T)/(k Tc_K)]
    Eg  = Eg_ref [1 + dEg/dT (Tc - 25)]
    Rsh = Rsh_ref · Gref/G ;  Rs constante
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional, Union

import numpy as np
from scipy.optimize import brentq, minimize_scalar, newton
from scipy.special import lambertw

from ..constants import (
    DEGDT_SI,
    EG_REF_SI,
    G_REF,
    K_BOLTZMANN,
    K_EV,
    KELVIN_0C,
    Q_ELECTRON,
    SOLVER,
    T_REF_C,
    T_REF_K,
)

ArrayLike = Union[float, np.ndarray]

# Códigos de estado por amostra (compartilhados com os demais modelos)
ST_OK = 0
ST_ZERO_IRRADIANCE = 1
ST_CLIPPED_ZERO = 2
ST_LOW_G_EXTRAPOLATION = 3
ST_REFINE_NOT_CONVERGED = 4      # Brent limitado não reportou sucesso; valor mantido
ST_COARSE_FALLBACK = 6           # refinamento piorou; mantido o ponto da varredura (legado)
ST_FAILED = 5                    # exceção numérica; P = NaN

STATUS_LABELS = {
    ST_OK: "ok",
    ST_ZERO_IRRADIANCE: "G=0 → P=0 (definição)",
    ST_CLIPPED_ZERO: "fórmula negativa → recortada a 0",
    ST_LOW_G_EXTRAPOLATION: "baixa irradiância: extrapolação logarítmica sinalizada",
    ST_REFINE_NOT_CONVERGED: "refinamento do MPP sem convergência declarada",
    ST_COARSE_FALLBACK: "refinamento pior que a varredura → varredura mantida (legado)",
    ST_FAILED: "falha numérica (NaN)",
}


# ---------------------------------------------------------------------------
# Parâmetros
# ---------------------------------------------------------------------------
@dataclass
class SDMReference:
    """Cinco parâmetros efetivos do SDM na referência (STC) + dados de tradução.

    ``a_ref`` [V] é o parâmetro identificado. ``n`` e ``n_cells`` só existem
    na rota clássica (datasheet com Ns); na rota SUPSI ficam ``None``.
    """

    IL_ref: float
    I0_ref: float
    Rs: float
    Rsh_ref: float
    a_ref: float
    alpha_isc_A_per_C: float
    eg_ref_eV: float = EG_REF_SI
    degdt_per_K: float = DEGDT_SI
    n: Optional[float] = None
    n_cells: Optional[int] = None
    method: str = "manual"
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "SDMReference":
        keys = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in keys})


def a_ref_from_n(n: float, n_cells: int) -> float:
    """a_ref = n · Ns · k · Tref / q  [V] (legado ``SDMParams.a_ref``)."""
    return n * n_cells * K_BOLTZMANN * T_REF_K / Q_ELECTRON


@dataclass
class SDMOperating:
    IL: float
    I0: float
    Rs: float
    Rsh: float
    a: float
    Tc: float
    G: float


# ---------------------------------------------------------------------------
# Tradução a (G, Tc)
# ---------------------------------------------------------------------------
def translate(ref: SDMReference, G: float, Tc: float) -> SDMOperating:
    G = max(float(G), SOLVER["g_min"])
    Tc_K = float(Tc) + KELVIN_0C
    a = ref.a_ref * (Tc_K / T_REF_K)
    IL = (G / G_REF) * (ref.IL_ref + ref.alpha_isc_A_per_C * (Tc - T_REF_C))
    IL = max(IL, 0.0)
    eg = ref.eg_ref_eV * (1.0 + ref.degdt_per_K * (Tc - T_REF_C))
    I0 = (
        ref.I0_ref
        * (Tc_K / T_REF_K) ** 3
        * np.exp((ref.eg_ref_eV / (K_EV * T_REF_K)) - (eg / (K_EV * Tc_K)))
    )
    Rsh = ref.Rsh_ref * (G_REF / G)
    return SDMOperating(IL=IL, I0=float(I0), Rs=ref.Rs, Rsh=Rsh, a=a, Tc=float(Tc), G=G)


# ---------------------------------------------------------------------------
# I(V)
# ---------------------------------------------------------------------------
def _lambertw_from_log(log_z: ArrayLike) -> np.ndarray:
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


def sdm_residual(I: float, V: float, p: SDMOperating) -> float:
    rs = max(p.Rs, SOLVER["rs_min"])
    arg = min((V + I * rs) / p.a, 700.0)
    return p.IL - p.I0 * (np.exp(arg) - 1.0) - (V + I * rs) / p.Rsh - I


def sdm_residual_prime(I: float, V: float, p: SDMOperating) -> float:
    rs = max(p.Rs, SOLVER["rs_min"])
    arg = min((V + I * rs) / p.a, 700.0)
    return -p.I0 * (rs / p.a) * np.exp(arg) - rs / p.Rsh - 1.0


def _current_lambertw(V: ArrayLike, p: SDMOperating) -> np.ndarray:
    V = np.asarray(V, dtype=float)
    rs = max(p.Rs, SOLVER["rs_min"])
    rsh, a, IL, I0 = p.Rsh, p.a, p.IL, p.I0
    denom = a * (rs + rsh)
    log_z = np.log(rs * I0 * rsh / denom) + rsh * (rs * IL + rs * I0 + V) / denom
    W = _lambertw_from_log(log_z)
    return (rsh * (IL + I0) - V) / (rs + rsh) - (a / rs) * W


def _current_brentq(V: float, p: SDMOperating) -> float:
    lo = -abs(p.IL) - 5.0
    hi = p.IL + p.I0 + 5.0
    if sdm_residual(lo, V, p) * sdm_residual(hi, V, p) > 0:
        return float(_current_lambertw(V, p))
    return brentq(sdm_residual, lo, hi, args=(V, p),
                  xtol=SOLVER["current_tol"], maxiter=SOLVER["max_iter"])


def _current_newton(V: float, p: SDMOperating) -> float:
    try:
        I = newton(sdm_residual, x0=p.IL, fprime=sdm_residual_prime, args=(V, p),
                   tol=SOLVER["current_tol"], maxiter=SOLVER["max_iter"])
        if not np.isfinite(I):
            raise RuntimeError
        return float(I)
    except (RuntimeError, OverflowError, FloatingPointError):
        return _current_brentq(V, p)


def current_from_voltage(V: ArrayLike, p: SDMOperating, method: str | None = None) -> ArrayLike:
    method = method or SOLVER["method"]
    if method == "lambertw":
        out = _current_lambertw(V, p)
        return float(out) if np.ndim(V) == 0 else out
    scalar_solver = _current_brentq if method == "brentq" else _current_newton
    if np.ndim(V) == 0:
        return scalar_solver(float(V), p)
    return np.array([scalar_solver(float(v), p) for v in np.asarray(V)])


def short_circuit_current(p: SDMOperating) -> float:
    return float(current_from_voltage(0.0, p, method="lambertw"))


def open_circuit_voltage(p: SDMOperating, diag: dict | None = None) -> float:
    """Voc por Brent sobre I(V)=0 (legado). ``diag`` recebe iterações/convergência."""
    if p.IL <= 0.0:
        return 0.0
    v_hi = p.a * np.log(p.IL / max(p.I0, 1e-30) + 1.0)
    v_hi = max(v_hi, 1e-3) * 1.05

    def f(V):
        return float(current_from_voltage(V, p, method="lambertw"))

    if f(0.0) <= 0.0:
        return 0.0
    if f(v_hi) > 0.0:
        v_hi *= 2.0
        if f(v_hi) > 0.0:
            if diag is not None:
                diag["voc_converged"] = False
            return v_hi
    root, rr = brentq(f, 0.0, v_hi, xtol=1e-9, maxiter=SOLVER["max_iter"], full_output=True)
    if diag is not None:
        diag["voc_converged"] = bool(rr.converged)
        diag["voc_iterations"] = int(rr.iterations)
    return root


def iv_curve(p: SDMOperating, n_points: int | None = None, method: str | None = None):
    """Curva I–V e P–V completas entre 0 e Voc (malha não uniforme do legado)."""
    n_points = n_points or SOLVER["iv_points"]
    v_oc = open_circuit_voltage(p)
    if v_oc <= 0.0:
        z = np.zeros(n_points)
        return z, z, z
    u = np.linspace(0.0, 1.0, n_points)
    V = v_oc * (0.55 * u + 0.45 * u**2)
    V = np.unique(np.concatenate([V, [v_oc]]))
    I = np.clip(np.asarray(current_from_voltage(V, p, method=method)), 0.0, None)
    return V, I, V * I


# ---------------------------------------------------------------------------
# MPP
# ---------------------------------------------------------------------------
def find_mpp(p: SDMOperating, coarse_points: int | None = None, method: str | None = None) -> dict:
    """MPP: varredura grossa vetorizada + Brent limitado sobre -P(V) (legado).

    Devolve também ``status``, ``nfev`` e ``refine_success``.
    """
    coarse_points = coarse_points or SOLVER["coarse_points"]
    diag: dict = {}
    voc = open_circuit_voltage(p, diag)
    if voc <= 0.0 or p.IL <= 0.0:
        return dict(Vmp=0.0, Imp=0.0, Pmp=0.0, Voc=0.0, Isc=0.0, FF=0.0,
                    status=ST_OK, nfev=0, refine_success=True, **diag)
    isc = short_circuit_current(p)

    V = np.linspace(0.35 * voc, voc, coarse_points)
    I = np.asarray(current_from_voltage(V, p, method="lambertw"))
    P = V * np.clip(I, 0.0, None)
    k = int(np.argmax(P))
    lo = V[max(k - 1, 0)]
    hi = V[min(k + 1, coarse_points - 1)]

    def neg_power(v: float) -> float:
        i = float(current_from_voltage(float(v), p, method=method or "lambertw"))
        return -v * max(i, 0.0)

    res = minimize_scalar(neg_power, bounds=(lo, hi), method="bounded",
                          options={"xatol": SOLVER["mpp_tol"], "maxiter": SOLVER["max_iter"]})
    v_mp = float(res.x)
    p_mp = float(-res.fun)
    i_mp = p_mp / v_mp if v_mp > 0 else 0.0
    status = ST_OK if bool(res.success) else ST_REFINE_NOT_CONVERGED
    if p_mp < P[k]:
        v_mp, p_mp = float(V[k]), float(P[k])
        i_mp = p_mp / v_mp if v_mp > 0 else 0.0
        status = ST_COARSE_FALLBACK
    ff = p_mp / (voc * isc) if (voc * isc) > 0 else 0.0
    if diag.get("voc_converged") is False:
        status = ST_REFINE_NOT_CONVERGED
    return dict(Vmp=v_mp, Imp=i_mp, Pmp=p_mp, Voc=voc, Isc=isc, FF=ff,
                status=status, nfev=int(res.nfev), refine_success=bool(res.success), **diag)


def mpp_at(ref: SDMReference, G: float, Tc: float) -> dict:
    """MPP em (G, Tc). G < g_min → 0 W (legado ``mpp_at_conditions``)."""
    if not np.isfinite(G) or not np.isfinite(Tc):
        return dict(Vmp=np.nan, Imp=np.nan, Pmp=np.nan, Voc=np.nan, Isc=np.nan, FF=np.nan,
                    status=ST_FAILED, nfev=0, refine_success=False)
    if G < SOLVER["g_min"]:
        return dict(Vmp=0.0, Imp=0.0, Pmp=0.0, Voc=0.0, Isc=0.0, FF=0.0,
                    status=ST_ZERO_IRRADIANCE, nfev=0, refine_success=True)
    return find_mpp(translate(ref, G, Tc))
