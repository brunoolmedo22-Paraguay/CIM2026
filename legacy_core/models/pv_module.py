"""
models/pv_module.py
===================
Estructuras de datos que describen un módulo fotovoltaico.

Se separan deliberadamente dos capas:

1. `ModuleSTC`  -> datos de catálogo (hoja de datos del fabricante).
2. `SDMParams`  -> los 5 parámetros del Single Diode Model en condiciones
                   de referencia (STC): IL_ref, I0_ref, Rs, Rsh_ref, n.

Los parámetros del SDM se pueden:
  * leer de la base de datos (si el fabricante/literatura los publica);
  * estimar a partir de `ModuleSTC` (simulation/solver.extract_sdm_params);
  * editar manualmente desde la interfaz.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional

from config.settings import (
    K_BOLTZMANN,
    Q_ELECTRON,
    KELVIN_0C,
    T_REF_K,
    G_REF,
    EG_REF_SI,
    DEGDT_SI,
    THERMAL,
)


# ===========================================================================
# 1. Datos de catálogo
# ===========================================================================
@dataclass
class ModuleSTC:
    """Datos eléctricos y mecánicos de la hoja de datos (condiciones STC)."""

    manufacturer: str
    model: str
    technology: str                 # "Poly-Si", "Mono-Si", ...
    p_nom: float                    # Potencia nominal Pmax [W]
    v_oc: float                     # Tensión de circuito abierto [V]
    i_sc: float                     # Corriente de cortocircuito [A]
    v_mp: float                     # Tensión en el MPP [V]
    i_mp: float                     # Corriente en el MPP [A]
    n_cells: int                    # Nº de células en serie (Ns)

    # Coeficientes de temperatura, tal como los publica el fabricante [%/°C]
    alpha_isc_pct: float            # Coef. de Isc  (positivo)
    beta_voc_pct: float             # Coef. de Voc  (negativo)
    gamma_pmax_pct: float           # Coef. de Pmax (negativo)

    noct: float = THERMAL["default_noct"]   # [°C]
    length: float = 1.650           # [m]
    width: float = 0.992            # [m]
    eg_ref: float = EG_REF_SI       # Energy gap a 25 °C [eV]
    degdt: float = DEGDT_SI         # d(Eg)/dT relativo [1/K]
    notes: str = ""

    # ---- Propiedades derivadas -------------------------------------------
    @property
    def area(self) -> float:
        """Área bruta del módulo [m2]."""
        return self.length * self.width

    @property
    def efficiency_stc(self) -> float:
        """Eficiencia del módulo en STC [-] (referida al área bruta)."""
        return self.p_nom / (self.area * G_REF)

    @property
    def alpha_isc(self) -> float:
        """Coeficiente de temperatura de Isc en unidades absolutas [A/°C]."""
        return self.alpha_isc_pct / 100.0 * self.i_sc

    @property
    def beta_voc(self) -> float:
        """Coeficiente de temperatura de Voc en unidades absolutas [V/°C]."""
        return self.beta_voc_pct / 100.0 * self.v_oc

    @property
    def gamma_pmax(self) -> float:
        """Coeficiente de temperatura de Pmax en unidades absolutas [W/°C]."""
        return self.gamma_pmax_pct / 100.0 * self.p_nom

    @property
    def p_mp_datasheet(self) -> float:
        """Vmp * Imp del catálogo (puede diferir levemente de p_nom)."""
        return self.v_mp * self.i_mp

    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# 2. Parámetros del Single Diode Model
# ===========================================================================
@dataclass
class SDMParams:
    """
    Cinco parámetros del SDM en condiciones de REFERENCIA (STC).

        I = IL - I0*[exp((V + I*Rs)/(n*Ns*Vt)) - 1] - (V + I*Rs)/Rsh
    """

    IL_ref: float        # Corriente fotogenerada de referencia [A]
    I0_ref: float        # Corriente de saturación inversa del diodo [A]
    Rs: float            # Resistencia serie [ohm]  (se asume cte con G y T)
    Rsh_ref: float       # Resistencia paralelo de referencia [ohm]
    n: float             # Factor de idealidad del diodo [-]
    n_cells: int         # Ns: nº de células en serie [-]
    source: str = "extracted"   # "datasheet" | "extracted" | "manual"

    @property
    def a_ref(self) -> float:
        """
        Tensión térmica modificada del módulo en STC:
            a_ref = n * Ns * k * Tref / q     [V]
        """
        return self.n * self.n_cells * K_BOLTZMANN * T_REF_K / Q_ELECTRON

    @property
    def vt_ref(self) -> float:
        """Tensión térmica de una célula en STC: Vt = kT/q [V]."""
        return K_BOLTZMANN * T_REF_K / Q_ELECTRON

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SDMOperating:
    """
    Parámetros del SDM ya trasladados a una condición de operación (G, Tc).
    Es lo que consume directamente el solver de la curva I-V.
    """

    IL: float            # [A]
    I0: float            # [A]
    Rs: float            # [ohm]
    Rsh: float           # [ohm]
    a: float             # Tensión térmica modificada n*Ns*k*Tc/q [V]
    Tc: float            # Temperatura de célula [°C]
    G: float             # Irradiancia efectiva [W/m2]

    def to_dict(self) -> dict:
        return asdict(self)


# ===========================================================================
# 3. Contenedor de alto nivel
# ===========================================================================
@dataclass
class PVModule:
    """Módulo PV completo = datos de catálogo + parámetros SDM."""

    stc: ModuleSTC
    sdm: Optional[SDMParams] = field(default=None)

    @property
    def name(self) -> str:
        return f"{self.stc.manufacturer} {self.stc.model}"

    def cell_temperature_kelvin(self, tc_celsius: float) -> float:
        return tc_celsius + KELVIN_0C
