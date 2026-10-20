"""Calibração multiponto do SDM com a caracterização de laboratório SUPSI (IEC 61853-1).

* Ajusta 5 parâmetros efetivos x = [IL_ref, log10 I0_ref, Rs, log10 Rsh_ref, a_ref]
  a 66 observações (22 condições G–T × Pmp, Isc, Voc), SEM Ns, Vmp ou Imp.
* Resíduos normalizados pelas escalas STC medidas: (pred − obs)/obs_STC(grandeza).
* Previsão pelo MESMO código físico usado em M4 (``translate`` + ``find_mpp``).
* Somente dados de laboratório: o campo 2019 nunca entra neste ajuste.
* Hipótese declarada: a temperatura da matriz (módulo em caixa térmica, regime
  estacionário) é tomada como temperatura de célula na tradução do SDM.
* Multiarranque determinístico (chute físico + hipercubo latino com semente),
  cotas físicas, resíduos por ponto, SVD do Jacobiano, covariância aproximada,
  correlações, cotas ativas e dispersão entre arranques (identificabilidade).
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import least_squares
from scipy.stats import qmc

from ..constants import G_REF, T_REF_C
from ..pvcore.module import ModuleSpec
from ..pvcore.sdm import SDMReference, find_mpp, translate

PARAM_NAMES = ["IL_ref [A]", "log10 I0_ref [log10 A]", "Rs [Ω]", "log10 Rsh_ref [log10 Ω]", "a_ref [V]"]
VARS = ("Pmp", "Isc", "Voc")


@dataclass(frozen=True)
class MultipointConfig:
    n_starts: int = 8
    seed: int = 20261019
    ftol: float = 1e-10
    xtol: float = 1e-10
    gtol: float = 1e-10
    max_nfev: int = 400
    il_factor_bounds: tuple = (0.90, 1.20)
    log10_i0_bounds: tuple = (-15.0, -3.0)
    rs_bounds: tuple = (1e-4, 3.0)
    log10_rsh_bounds: tuple = (1.5, 5.5)
    a_ref_bounds: tuple = (0.3, 4.0)
    near_optimal_rel: float = 0.01      # arranques com custo ≤ (1+1%)·melhor custo

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MultipointReport:
    success: bool
    best_cost: float
    best_x: list
    starts: list
    jacobian_singular_values: list
    condition_number: float
    param_std_transformed: list
    correlation: list
    active_bounds: list
    residuals: pd.DataFrame
    lab_metrics: pd.DataFrame
    stc_check: dict
    near_optimal_spread: dict
    implied_coefficients: dict
    n_eval_failures: int
    elapsed_s: float
    config: dict
    assumptions: list = field(default_factory=list)

    def to_json_dict(self) -> dict:
        d = asdict(self)
        d["residuals"] = self.residuals.to_dict(orient="records")
        d["lab_metrics"] = self.lab_metrics.to_dict(orient="records")
        return d


def _ref(x, module: ModuleSpec) -> SDMReference:
    IL, lI0, Rs, lRsh, a = (float(v) for v in x)
    return SDMReference(IL_ref=IL, I0_ref=10.0**lI0, Rs=Rs, Rsh_ref=10.0**lRsh, a_ref=a,
                        alpha_isc_A_per_C=float(module.alpha_isc_A_per_C), eg_ref_eV=module.eg_ref_eV,
                        degdt_per_K=module.degdt_per_K, n=None, n_cells=None, method="multiponto_SUPSI_lab")


def forward(ref: SDMReference, conditions: list[tuple[float, float]]) -> dict:
    """Pmp, Isc, Voc previstos para cada (G, T) com o código físico de M4."""
    out = {}
    for G, T in conditions:
        r = find_mpp(translate(ref, G, T))
        out[(G, T)] = {"Pmp": r["Pmp"], "Isc": r["Isc"], "Voc": r["Voc"], "Vmp": r["Vmp"], "Imp": r["Imp"]}
    return out


def implied_temperature_coefficients(ref: SDMReference, module: ModuleSpec,
                                     temps=(15.0, 25.0, 50.0, 75.0)) -> dict:
    """Coeficientes α, β, γ implícitos do SDM a 1000 W/m² (regressão linear em T),
    em %/°C relativos ao valor previsto a 25 °C. Diagnóstico: NÃO entra no ajuste."""
    pred = forward(ref, [(G_REF, t) for t in temps])
    out = {}
    for var, key, meas in (("Isc", "alpha_isc_pct_C", module.alpha_isc_pct_C),
                           ("Voc", "beta_voc_pct_C", module.beta_voc_pct_C),
                           ("Pmp", "gamma_pmax_pct_C", module.gamma_pmax_pct_C)):
        y = np.array([pred[(G_REF, t)][var] for t in temps])
        slope = float(np.polyfit(np.array(temps), y, 1)[0])
        out[key] = {"modelo_pct_C": 100.0 * slope / pred[(G_REF, T_REF_C)][var], "medido_pct_C": meas}
    return out


def calibrate_multipoint(lab_long: pd.DataFrame, module: ModuleSpec,
                         cfg: MultipointConfig = MultipointConfig()) -> tuple[SDMReference, MultipointReport]:
    t0 = time.perf_counter()
    obs = lab_long[["variable", "irradiance_poa_Wm2", "temperature_module_C", "measured_value"]].copy()
    if len(obs) != 66:
        raise ValueError(f"Esperadas 66 observações de laboratório, recebidas {len(obs)}.")
    if module.alpha_isc_A_per_C is None:
        raise ValueError("α_Isc ausente na ficha experimental.")
    stc = {v: float(obs[(obs.variable == v) & (obs.irradiance_poa_Wm2 == G_REF)
                        & (obs.temperature_module_C == T_REF_C)].measured_value.iloc[0]) for v in VARS}
    conds = sorted({(float(r.irradiance_poa_Wm2), float(r.temperature_module_C)) for r in obs.itertuples()})
    y = obs.measured_value.to_numpy(float)
    keys = list(zip(obs.variable, obs.irradiance_poa_Wm2.astype(float), obs.temperature_module_C.astype(float)))
    scale = np.array([stc[v] for v, _, _ in keys])
    fails = {"n": 0}

    def residuals(x):
        try:
            pred = forward(_ref(x, module), conds)
            p = np.array([pred[(G, T)][v] for v, G, T in keys])
            if not np.all(np.isfinite(p)):
                raise FloatingPointError
            return (p - y) / scale
        except Exception:
            fails["n"] += 1
            return np.full(len(y), 1e3)

    isc = stc["Isc"]
    lower = np.array([cfg.il_factor_bounds[0] * isc, cfg.log10_i0_bounds[0], cfg.rs_bounds[0],
                      cfg.log10_rsh_bounds[0], cfg.a_ref_bounds[0]])
    upper = np.array([cfg.il_factor_bounds[1] * isc, cfg.log10_i0_bounds[1], cfg.rs_bounds[1],
                      cfg.log10_rsh_bounds[1], cfg.a_ref_bounds[1]])
    # Chute físico a partir do próprio laboratório: dVoc/d lnG a 25 °C ≈ a (diodo ideal)
    v25 = obs[(obs.variable == "Voc") & (obs.temperature_module_C == 25.0)].sort_values("irradiance_poa_Wm2")
    a0 = float(np.polyfit(np.log(v25.irradiance_poa_Wm2), v25.measured_value, 1)[0])
    a0 = float(np.clip(a0, lower[4] * 1.01, upper[4] * 0.99))
    i0_0 = np.log10(max(isc * np.exp(-stc["Voc"] / a0), 1e-15))
    starts = [np.clip(np.array([isc, i0_0, 0.3, np.log10(500.0), a0]), lower + 1e-9, upper - 1e-9)]
    if cfg.n_starts > 1:
        lhs = qmc.LatinHypercube(d=5, seed=cfg.seed).random(cfg.n_starts - 1)
        starts += list(qmc.scale(lhs, lower, upper))
    results = []
    for k, x0 in enumerate(starts):
        sol = least_squares(residuals, x0, bounds=(lower, upper), method="trf", ftol=cfg.ftol,
                            xtol=cfg.xtol, gtol=cfg.gtol, max_nfev=cfg.max_nfev)
        results.append((k, x0, sol))
    best_k, _, best = min(results, key=lambda r: r[2].cost)
    x = best.x
    ref = _ref(x, module)

    # Identificabilidade
    J = best.jac
    sv = np.linalg.svd(J, compute_uv=False)
    cond = float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf")
    m_obs, p = J.shape
    s2 = 2.0 * best.cost / max(m_obs - p, 1)
    try:
        cov = np.linalg.inv(J.T @ J) * s2
        std = np.sqrt(np.clip(np.diag(cov), 0, None))
        corr = cov / np.outer(std, std)
    except np.linalg.LinAlgError:
        std = np.full(p, np.nan)
        corr = np.full((p, p), np.nan)
    active = [PARAM_NAMES[i] for i in range(p) if (abs(x[i] - lower[i]) < 1e-6 * max(1, abs(lower[i]))
                                                   or abs(x[i] - upper[i]) < 1e-6 * max(1, abs(upper[i])))]
    near = [r for r in results if r[2].cost <= best.cost * (1 + cfg.near_optimal_rel)]
    near_x = np.array([r[2].x for r in near])
    spread = {"n_near_optimal": len(near), "n_starts": len(results),
              "max_abs_diff": dict(zip(PARAM_NAMES, (near_x.max(0) - near_x.min(0)).tolist())) if len(near) > 1 else {}}

    # Resíduos e métricas de laboratório
    pred = forward(ref, conds)
    lab_long = lab_long.copy()
    res_rows = []
    for r in lab_long.itertuples():
        G, T = float(r.irradiance_poa_Wm2), float(r.temperature_module_C)
        pv = pred[(G, T)][r.variable]
        u_abs = (r.u_rel_k2 * r.measured_value) if hasattr(r, "u_rel_k2") and pd.notna(getattr(r, "u_rel_k2", None)) else np.nan
        res_rows.append({"variable": r.variable, "G_Wm2": G, "T_C": T, "observado": r.measured_value,
                         "previsto": pv, "residuo": pv - r.measured_value,
                         "residuo_rel_pct": 100 * (pv - r.measured_value) / r.measured_value,
                         "residuo_normalizado_STC": (pv - r.measured_value) / stc[r.variable],
                         "U_k2_abs": u_abs,
                         "dentro_U_k2": bool(abs(pv - r.measured_value) <= u_abs) if np.isfinite(u_abs) else None})
    resid = pd.DataFrame(res_rows)
    lab_metrics = (resid.groupby("variable")
                   .apply(lambda d: pd.Series({"n": len(d), "MAE": d.residuo.abs().mean(),
                                               "RMSE": float(np.sqrt((d.residuo**2).mean())),
                                               "MBE": d.residuo.mean(), "max_abs": d.residuo.abs().max(),
                                               "frac_dentro_U_k2": d.dentro_U_k2.mean() if d.dentro_U_k2.notna().any() else np.nan}),
                          include_groups=False)
                   .reset_index())
    stc_pred = pred[(G_REF, T_REF_C)]
    report = MultipointReport(
        success=bool(best.success), best_cost=float(best.cost), best_x=x.tolist(),
        starts=[{"start": k, "x0": list(map(float, x0)), "x": list(map(float, s.x)), "cost": float(s.cost),
                 "nfev": int(s.nfev), "status": int(s.status), "message": str(s.message), "success": bool(s.success)}
                for k, x0, s in results],
        jacobian_singular_values=sv.tolist(), condition_number=cond, param_std_transformed=std.tolist(),
        correlation=np.asarray(corr).tolist(), active_bounds=active, residuals=resid, lab_metrics=lab_metrics,
        stc_check={"Pmp_prev_W": stc_pred["Pmp"], "Pmp_med_W": stc["Pmp"], "Isc_prev_A": stc_pred["Isc"],
                   "Isc_med_A": stc["Isc"], "Voc_prev_V": stc_pred["Voc"], "Voc_med_V": stc["Voc"],
                   "Vmp_prev_V (saída do modelo, não medida)": stc_pred["Vmp"],
                   "Imp_prev_A (saída do modelo, não medida)": stc_pred["Imp"]},
        near_optimal_spread=spread, implied_coefficients=implied_temperature_coefficients(ref, module),
        n_eval_failures=int(fails["n"]), elapsed_s=time.perf_counter() - t0,
        config=cfg.to_dict(),
        assumptions=[
            "Somente 66 medições de laboratório (IEC 61853-1); dados de campo 2019 não usados.",
            "Temperatura da matriz (módulo em caixa térmica) tomada como Tcell na tradução do SDM.",
            "a_ref efetivo identificado diretamente; n e Ns não são atribuídos.",
            "Tradução G–T De Soto/CEC do legado: Eg_ref=1,121 eV, dEg/dT=−0,0002677 1/K, Rs constante, Rsh∝1/G.",
            "α_Isc = 0,046 %/°C × Isc_STC (ficha experimental).",
            "Resíduos normalizados pelas grandezas medidas em STC (pesos iguais por grandeza relativa).",
        ],
    )
    ref.provenance = {"module_id": module.id, "inputs": "66 medições IEC 61853-1 (22 G–T × Pmp, Isc, Voc)",
                      "algorithm": "least_squares TRF, multiarranque", "best_start": int(best_k),
                      "cost": float(best.cost), "converged": bool(best.success)}
    return ref, report
