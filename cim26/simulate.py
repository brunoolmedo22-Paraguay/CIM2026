"""Simulação do modo Modelos (arranjo Ns×Np) com o MESMO código físico do modo Artigo."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .constants import SANDIA_DELTA_T_DEFAULT_C
from .data.weather import WeatherSeries
from .pvcore import sdm as _sdm
from .pvcore.models import MODEL_IDS, availability, predict, prepare, scale_to_array
from .pvcore.module import ModuleSpec
from .pvcore.thermal import MEASURED, build_conditions

THERMAL_OPTIONS = {
    "Tmod": [("A_tmod_medida", "Tmod fornecida; Tcell pela eq. 23 (Sandia)")],
    "Tcell": [("tcell_fornecida", "Tcell fornecida; Tmod pela inversa da eq. 23")],
    "Tamb": [("noct", "Tcell por NOCT; Tmod pela inversa da eq. 23"),
             ("B_faiman", "Tmod por Faiman (U0, U1, vento); Tcell pela eq. 23")],
}


def thermal_options(weather: WeatherSeries, module: ModuleSpec) -> list[tuple[str, str, bool, str]]:
    """(estratégia, descrição, disponível, motivo) compatíveis com as temperaturas fornecidas."""
    out = []
    for kind in weather.temperature_kinds():
        for sid, desc in THERMAL_OPTIONS[kind]:
            ok, why = True, ""
            if sid == "noct" and module.noct_C is None:
                ok, why = False, "módulo sem NOCT declarado"
            if sid == "B_faiman" and (module.u0_W_m2K is None or module.u1_W_s_m3K is None):
                ok, why = False, "módulo sem U0/U1 medidos"
            if sid == "B_faiman" and weather.wind_ms is None:
                ok, why = False, "sem velocidade do vento"
            out.append((sid, desc, ok, why))
    return out


def conditions_for(weather: WeatherSeries, module: ModuleSpec, strategy: Optional[str],
                   delta_t_C: float = SANDIA_DELTA_T_DEFAULT_C):
    if strategy is None:      # sem temperatura: só M1 é avaliável
        nan = np.full(len(weather), np.nan)
        return build_conditions("tcell_fornecida", weather.g_poa_Wm2, g_provenance=weather.origin,
                                t_cell_C=nan, t_provenance="indisponível", delta_t_C=delta_t_C)
    prov = MEASURED if weather.origin == "medido" else weather.origin
    return build_conditions(strategy, weather.g_poa_Wm2, g_provenance=weather.origin,
                            t_module_C=weather.t_module_C, t_cell_C=weather.t_cell_C, t_amb_C=weather.t_amb_C,
                            wind_ms=weather.wind_ms, delta_t_C=delta_t_C, noct_C=module.noct_C,
                            u0=module.u0_W_m2K, u1=module.u1_W_s_m3K, t_provenance=prov)


@dataclass
class SimulationResult:
    table: pd.DataFrame
    kpis: pd.DataFrame
    statuses: dict
    provenance: dict
    notes: list = field(default_factory=list)


def valid_steps(ts: pd.DatetimeIndex, finite: np.ndarray, tol_factor: float = 1.5):
    t = pd.Series(ts)
    dt_min = t.diff().dt.total_seconds().to_numpy()[1:] / 60.0
    nominal = float(np.median(dt_min)) if len(dt_min) else np.nan
    ok = finite[:-1] & finite[1:] & (dt_min > 0) & (dt_min <= tol_factor * nominal)
    return ok, dt_min / 60.0, nominal


def simulate(module: ModuleSpec, weather: WeatherSeries, model_ids=MODEL_IDS,
             sdm_ref: Optional[_sdm.SDMReference] = None, strategy: Optional[str] = None,
             delta_t_C: float = SANDIA_DELTA_T_DEFAULT_C, n_series: int = 1, n_parallel: int = 1) -> SimulationResult:
    cond = conditions_for(weather, module, strategy, delta_t_C)
    has_t = strategy is not None
    tab = pd.DataFrame({"timestamp": weather.timestamp, "g_poa_Wm2": cond.g_poa_Wm2,
                        "t_module_C": cond.t_module_C, "t_cell_C": cond.t_cell_C})
    statuses, rows, notes = {}, [], list(weather.notes)
    valid_g = np.isfinite(cond.g_poa_Wm2)
    for m in model_ids:
        av = availability(m, module, sdm_ref)
        if av.available and m != "M1" and not has_t:
            av.available, av.reason = False, "Requer temperatura (nenhuma fornecida)."
        statuses[m] = av
        if not av.available:
            continue
        params = prepare(m, module, sdm_ref)
        mask = valid_g & (np.isfinite(cond.t_cell_C) if m != "M1" else True)
        p = np.full(len(cond), np.nan)
        st = np.full(len(cond), _sdm.ST_FAILED, dtype=np.int8)
        if mask.any():
            out = predict(m, cond.subset(np.where(mask)[0]), params)
            p[mask] = out.p_mpp_W
            st[mask] = out.status
        tab[f"P_{m}_modulo_W"] = p
        tab[f"P_{m}_arranjo_W"] = scale_to_array(p, n_series, n_parallel)
        tab[f"status_{m}"] = st
        pa = tab[f"P_{m}_arranjo_W"].to_numpy()
        fin = np.isfinite(pa)
        ok, dt_h, nominal = valid_steps(weather.timestamp, fin)
        e = float(np.sum((0.5 * (pa[:-1] + pa[1:]) * dt_h)[ok]) / 1000.0) if len(ok) else 0.0
        imax = int(np.nanargmax(pa)) if fin.any() else None
        rows.append({"modelo": m, "P_max_arranjo_W": float(np.nanmax(pa)) if fin.any() else np.nan,
                     "instante_P_max": weather.timestamp[imax] if imax is not None else None,
                     "E_periodo_valido_kWh": e, "horas_validas_h": float(np.sum(dt_h[ok])) if len(ok) else 0.0,
                     "amostras_validas": int(fin.sum()), "amostras_total": len(pa),
                     "passo_nominal_min": nominal, "Pstc_arranjo_W": module.p_stc_W * n_series * n_parallel})
    return SimulationResult(table=tab, kpis=pd.DataFrame(rows), statuses=statuses,
                            provenance=dict(cond.provenance, weather=weather.description, origem=weather.origin),
                            notes=notes)


def iv_curve_array(sdm_ref: _sdm.SDMReference, g: float, t_cell: float, n_series: int = 1, n_parallel: int = 1,
                   n_points: int = 300):
    """Curva I–V/P–V elétrica (somente SDM) do arranjo: V·Ns, I·Np (módulos idênticos, sem mismatch)."""
    op = _sdm.translate(sdm_ref, g, t_cell)
    V, I, P = _sdm.iv_curve(op, n_points)
    mpp = _sdm.find_mpp(op)
    return (V * n_series, I * n_parallel, P * n_series * n_parallel,
            {k: mpp[k] * (n_series if k in ("Vmp", "Voc") else n_parallel if k in ("Imp", "Isc")
                          else n_series * n_parallel if k == "Pmp" else 1) for k in ("Vmp", "Imp", "Pmp", "Voc", "Isc")})
