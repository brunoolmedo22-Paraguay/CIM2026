"""Calibração clássica do SDM a partir de datasheet comercial (rota herdada).

Porte fiel de ``extract_sdm_params`` (``legacy_core/simulation/solver.py``):
mesmas 5 equações de De Soto et al. (2006), mesmo espaço escalado
[IL, log10 I0, Rs, log10 Rsh, n], mesmas cotas, chute inicial e tolerâncias.
Independente dos dados SUPSI. Equivalência verificada em testes de regressão.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass

import numpy as np
from scipy.optimize import least_squares

from ..constants import (
    EXTRACTION_BOUNDS,
    EXTRACTION_INITIAL_GUESS,
    G_REF,
    K_BOLTZMANN,
    Q_ELECTRON,
    T_REF_C,
    T_REF_K,
)
from ..pvcore.module import ModuleSpec
from ..pvcore.sdm import SDMReference, a_ref_from_n, find_mpp, open_circuit_voltage, translate


@dataclass
class ClassicalReport:
    success: bool
    cost: float
    n_iter: int
    residuals: dict
    message: str
    elapsed_s: float
    stc_check: dict

    def to_dict(self) -> dict:
        return asdict(self)


def _ref_from_x(x, m: ModuleSpec, method: str = "classico_datasheet") -> SDMReference:
    IL, log_I0, Rs, log_Rsh, n = x
    return SDMReference(
        IL_ref=float(IL), I0_ref=float(10.0**log_I0), Rs=float(Rs), Rsh_ref=float(10.0**log_Rsh),
        a_ref=float(a_ref_from_n(float(n), int(m.n_cells_series))),
        alpha_isc_A_per_C=float(m.alpha_isc_A_per_C), eg_ref_eV=m.eg_ref_eV, degdt_per_K=m.degdt_per_K,
        n=float(n), n_cells=int(m.n_cells_series), method=method,
    )


def _residuals(x, m: ModuleSpec, dT: float = 10.0):
    IL, log_I0, Rs, log_Rsh, n = x
    I0 = 10.0**log_I0
    Rsh = 10.0**log_Rsh
    a = n * m.n_cells_series * K_BOLTZMANN * T_REF_K / Q_ELECTRON
    Voc, Isc, Vmp, Imp = m.v_oc_V, m.i_sc_A, m.v_mp_V, m.i_mp_A

    def diode(v_eq):
        return np.exp(np.minimum(v_eq / a, 700.0))

    r1 = IL - I0 * (diode(Isc * Rs) - 1.0) - (Isc * Rs) / Rsh - Isc
    r2 = IL - I0 * (diode(Voc) - 1.0) - Voc / Rsh
    v_eq_mp = Vmp + Imp * Rs
    r3 = IL - I0 * (diode(v_eq_mp) - 1.0) - v_eq_mp / Rsh - Imp
    num = I0 / a * diode(v_eq_mp) + 1.0 / Rsh
    den = 1.0 + I0 * Rs / a * diode(v_eq_mp) + Rs / Rsh
    r4 = Imp + Vmp * (-num / den)
    try:
        p_hot = translate(_ref_from_x(x, m), G_REF, T_REF_C + dT)
        beta_model = (open_circuit_voltage(p_hot) - Voc) / dT
    except Exception:
        beta_model = 0.0
    r5 = beta_model - m.beta_voc_V_per_C
    return np.array([r1 / Isc, r2 / Isc, r3 / Isc, r4 / Imp, r5 / abs(m.beta_voc_V_per_C)])


def calibrate_classical(m: ModuleSpec) -> tuple[SDMReference, ClassicalReport]:
    missing = m.classical_sdm_inputs_missing()
    if missing:
        raise ValueError("Datasheet incompleto para a rota clássica: faltam " + ", ".join(missing))
    t0 = time.perf_counter()
    n0 = EXTRACTION_INITIAL_GUESS["n"]
    a0 = n0 * m.n_cells_series * K_BOLTZMANN * T_REF_K / Q_ELECTRON
    I0_0 = m.i_sc_A * np.exp(-m.v_oc_V / a0)
    x0 = np.array([m.i_sc_A, np.log10(max(I0_0, 1e-13)), EXTRACTION_INITIAL_GUESS["Rs"],
                   np.log10(EXTRACTION_INITIAL_GUESS["Rsh"]), n0])
    b = EXTRACTION_BOUNDS
    lower = np.array([b["IL_factor"][0] * m.i_sc_A, b["log10_I0"][0], b["Rs"][0], b["log10_Rsh"][0], b["n"][0]])
    upper = np.array([b["IL_factor"][1] * m.i_sc_A, b["log10_I0"][1], b["Rs"][1], b["log10_Rsh"][1], b["n"][1]])
    x0 = np.clip(x0, lower + 1e-9, upper - 1e-9)
    sol = least_squares(_residuals, x0, args=(m,), bounds=(lower, upper), method="trf",
                        xtol=1e-14, ftol=1e-14, gtol=1e-14, max_nfev=8000)
    ref = _ref_from_x(sol.x, m)
    names = ["Isc (E1)", "Voc (E2)", "MPP (E3)", "dP/dV=0 (E4)", "beta_Voc (E5)"]
    stc = find_mpp(translate(ref, G_REF, T_REF_C))
    report = ClassicalReport(
        success=bool(sol.success) and float(sol.cost) < 1e-6, cost=float(sol.cost), n_iter=int(sol.nfev),
        residuals={k: float(v) for k, v in zip(names, sol.fun)}, message=str(sol.message),
        elapsed_s=time.perf_counter() - t0,
        stc_check={"Pmp_W": stc["Pmp"], "Vmp_V": stc["Vmp"], "Imp_A": stc["Imp"], "Voc_V": stc["Voc"],
                   "Isc_A": stc["Isc"], "Pnom_datasheet_W": m.p_stc_W, "VmpImp_datasheet_W": m.v_mp_V * m.i_mp_A},
    )
    ref.provenance = {"module_id": m.id, "inputs": "Voc, Isc, Vmp, Imp, Ns, β_Voc, α_Isc (datasheet)",
                      "algorithm": "De Soto 5 equações, least_squares TRF (legado)",
                      "converged": report.success, "cost": report.cost}
    return ref, report
