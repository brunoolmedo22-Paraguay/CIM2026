"""Camada térmica comum e condições de operação com proveniência.

Separação estrita de variáveis:
    g_poa_Wm2   irradiância no plano (POA). GHI NUNCA é renomeada como POA.
    t_module_C  temperatura posterior do módulo (Tmod / Tbom).
    t_cell_C    temperatura de célula (Tcell).
    t_amb_C     temperatura ambiente.

Relações disponíveis (cada uma rotulada na proveniência):
    Sandia eq. (23), IEA PVPS T13-20:2020 p. 99:  Tcell = Tmod + (G/1000)·ΔT
    NOCT (legado, IEC 61215):                     Tcell = Tamb + (NOCT-20)/800·G
    Faiman (IEC 61853-2; IEA eq. 5):               Tmod  = Tamb + G/(U0 + U1·v)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..constants import G_NOCT, G_REF, SANDIA_DELTA_T_DEFAULT_C, T_AMB_NOCT

# Rótulos de proveniência
MEASURED = "medido"
ESTIMATED = "estimado"
SIMULATED = "simulado"
MANUAL = "manual"
UNAVAILABLE = "indisponível"


def t_cell_from_t_module(t_module_C, g_poa_Wm2, delta_t_C: float = SANDIA_DELTA_T_DEFAULT_C):
    """Sandia eq. (23): Tcell = Tmod + (Gpoa/1000)·ΔT."""
    return np.asarray(t_module_C, float) + np.asarray(g_poa_Wm2, float) / G_REF * float(delta_t_C)


def t_module_from_t_cell(t_cell_C, g_poa_Wm2, delta_t_C: float = SANDIA_DELTA_T_DEFAULT_C):
    """Inversa da eq. (23): Tmod = Tcell − (Gpoa/1000)·ΔT."""
    return np.asarray(t_cell_C, float) - np.asarray(g_poa_Wm2, float) / G_REF * float(delta_t_C)


def t_cell_noct(t_amb_C, g_poa_Wm2, noct_C: float):
    """Modelo NOCT do legado: Tcell = Tamb + (NOCT − 20)/800 · Gpoa."""
    return np.asarray(t_amb_C, float) + (float(noct_C) - T_AMB_NOCT) / G_NOCT * np.asarray(g_poa_Wm2, float)


def t_module_faiman(t_amb_C, g_poa_Wm2, wind_ms, u0: float, u1: float):
    """Faiman: Tmod = Tamb + Gpoa/(U0 + U1·v); U0 [W m⁻² K⁻¹], U1 [W s m⁻³ K⁻¹]."""
    v = np.asarray(wind_ms, float)
    return np.asarray(t_amb_C, float) + np.asarray(g_poa_Wm2, float) / (float(u0) + float(u1) * v)


@dataclass
class Conditions:
    """Arrays alinhados (mesmo comprimento) + proveniência por variável."""

    g_poa_Wm2: np.ndarray
    t_module_C: np.ndarray
    t_cell_C: np.ndarray
    t_amb_C: Optional[np.ndarray] = None
    wind_ms: Optional[np.ndarray] = None
    provenance: dict = field(default_factory=dict)

    def __post_init__(self):
        self.g_poa_Wm2 = np.ascontiguousarray(self.g_poa_Wm2, dtype=float)
        self.t_module_C = np.ascontiguousarray(self.t_module_C, dtype=float)
        self.t_cell_C = np.ascontiguousarray(self.t_cell_C, dtype=float)
        n = self.g_poa_Wm2.shape[0]
        for name in ("t_module_C", "t_cell_C"):
            if getattr(self, name).shape[0] != n:
                raise ValueError(f"{name} não tem o mesmo comprimento de g_poa_Wm2")

    def __len__(self) -> int:
        return int(self.g_poa_Wm2.shape[0])

    def subset(self, idx) -> "Conditions":
        return Conditions(
            g_poa_Wm2=self.g_poa_Wm2[idx], t_module_C=self.t_module_C[idx],
            t_cell_C=self.t_cell_C[idx],
            t_amb_C=None if self.t_amb_C is None else np.asarray(self.t_amb_C)[idx],
            wind_ms=None if self.wind_ms is None else np.asarray(self.wind_ms)[idx],
            provenance=dict(self.provenance),
        )


# ---------------------------------------------------------------------------
# Estratégias térmicas (mesmo código para os modos Modelos e Artigo)
# ---------------------------------------------------------------------------
THERMAL_STRATEGIES = {
    "A_tmod_medida": "A · Tmod medida (Tbom); Tcell = Tmod + G/1000·ΔT (Sandia eq. 23)",
    "B_faiman": "B · Tmod estimada por Faiman (U0, U1, Tamb, vento); Tcell por eq. 23",
    "noct": "Tcell estimada por NOCT a partir de Tamb; Tmod pela inversa da eq. 23",
    "tcell_fornecida": "Tcell fornecida; Tmod pela inversa da eq. 23",
}


def build_conditions(
    strategy: str,
    g_poa_Wm2,
    *,
    g_provenance: str = MEASURED,
    t_module_C=None,
    t_cell_C=None,
    t_amb_C=None,
    wind_ms=None,
    delta_t_C: float = SANDIA_DELTA_T_DEFAULT_C,
    noct_C: float | None = None,
    u0: float | None = None,
    u1: float | None = None,
    t_provenance: str = MEASURED,
) -> Conditions:
    """Constrói ``Conditions`` com a estratégia térmica declarada.

    ``delta_t_C`` é sempre registrado como hipótese (não medido).
    """
    g = np.asarray(g_poa_Wm2, dtype=float)
    dt_label = f"ΔT={float(delta_t_C):g} °C (hipótese, não medido)"
    prov = {"g_poa_Wm2": f"{g_provenance} (POA)", "thermal_strategy": strategy,
            "delta_t_C": float(delta_t_C)}
    if strategy == "A_tmod_medida":
        if t_module_C is None:
            raise ValueError("Estratégia A requer temperatura do módulo (Tmod/Tbom).")
        tm = np.asarray(t_module_C, float)
        tc = t_cell_from_t_module(tm, g, delta_t_C)
        prov["t_module_C"] = f"{t_provenance} (temperatura posterior)"
        prov["t_cell_C"] = f"{ESTIMATED}: Sandia eq. 23, {dt_label}"
    elif strategy == "B_faiman":
        if t_amb_C is None or wind_ms is None or u0 is None or u1 is None:
            raise ValueError("Estratégia B requer Tamb, vento, U0 e U1.")
        tm = t_module_faiman(t_amb_C, g, wind_ms, u0, u1)
        tc = t_cell_from_t_module(tm, g, delta_t_C)
        prov["t_module_C"] = f"{ESTIMATED}: Faiman U0={u0:g}, U1={u1:g}"
        prov["t_cell_C"] = f"{ESTIMATED}: Faiman + Sandia eq. 23, {dt_label}"
    elif strategy == "noct":
        if t_amb_C is None or noct_C is None:
            raise ValueError("Estratégia NOCT requer Tamb e NOCT do módulo.")
        tc = t_cell_noct(t_amb_C, g, noct_C)
        tm = t_module_from_t_cell(tc, g, delta_t_C)
        prov["t_cell_C"] = f"{ESTIMATED}: NOCT={noct_C:g} °C"
        prov["t_module_C"] = f"{ESTIMATED}: inversa da eq. 23 a partir de Tcell(NOCT), {dt_label}"
    elif strategy == "tcell_fornecida":
        if t_cell_C is None:
            raise ValueError("Estratégia requer Tcell.")
        tc = np.asarray(t_cell_C, float)
        tm = t_module_from_t_cell(tc, g, delta_t_C)
        prov["t_cell_C"] = f"{t_provenance} (Tcell)"
        prov["t_module_C"] = f"{ESTIMATED}: inversa da eq. 23, {dt_label}"
    else:
        raise ValueError(f"Estratégia térmica desconhecida: {strategy!r}")
    if t_amb_C is not None:
        prov.setdefault("t_amb_C", t_provenance)
    if wind_ms is not None:
        prov.setdefault("wind_ms", t_provenance)
    return Conditions(g_poa_Wm2=g, t_module_C=tm, t_cell_C=tc,
                      t_amb_C=None if t_amb_C is None else np.asarray(t_amb_C, float),
                      wind_ms=None if wind_ms is None else np.asarray(wind_ms, float),
                      provenance=prov)
