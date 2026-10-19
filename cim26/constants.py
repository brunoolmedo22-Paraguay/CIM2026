"""Constantes físicas, condições de referência e parâmetros numéricos.

Valores transcritos sem alteração de ``legacy_core/config/settings.py``
(verificado por ``tests/test_regression_legacy.py``). Novos valores
introduzidos pelo CIM26 estão marcados com ``# CIM26`` e têm origem declarada.
"""

from __future__ import annotations

# --- Constantes fundamentais (CODATA) -------------------------------------
Q_ELECTRON = 1.602176634e-19      # C
K_BOLTZMANN = 1.380649e-23        # J/K
KELVIN_0C = 273.15                # K
K_EV = K_BOLTZMANN / Q_ELECTRON   # eV/K

# --- Condições de referência (STC, IEC 61215) ------------------------------
G_REF = 1000.0                    # W/m²
T_REF_C = 25.0                    # °C
T_REF_K = T_REF_C + KELVIN_0C     # K

# --- NOCT (IEC 61215) -------------------------------------------------------
G_NOCT = 800.0                    # W/m²
T_AMB_NOCT = 20.0                 # °C

# --- Semicondutor (c-Si, De Soto et al. 2006) ------------------------------
EG_REF_SI = 1.121                 # eV
DEGDT_SI = -0.0002677             # 1/K

# --- Solver SDM (legado) ----------------------------------------------------
SOLVER = {
    "method": "lambertw",
    "iv_points": 300,
    "mpp_tol": 1e-6,              # V (xatol do Brent limitado)
    "current_tol": 1e-10,         # A
    "max_iter": 200,
    "g_min": 1.0,                 # W/m²
    "rs_min": 1e-6,               # ohm
    "coarse_points": 60,          # varredura grossa do MPP (legado: argumento padrão)
}

# Cotas da extração clássica (De Soto, 5 equações) — legado
EXTRACTION_BOUNDS = {
    "IL_factor": (0.90, 1.20),
    "log10_I0": (-14.0, -4.0),
    "Rs": (1e-4, 2.5),
    "log10_Rsh": (1.5, 5.0),
    "n": (0.80, 2.20),
}
EXTRACTION_INITIAL_GUESS = {"n": 1.10, "Rs": 0.30, "Rsh": 500.0}

# --- Térmico ------------------------------------------------------------------
DEFAULT_NOCT_C = 45.0
SANDIA_DELTA_T_DEFAULT_C = 3.0    # IEA PVPS T13-20:2020 eq. (23), p. 99 — HIPÓTESE, não medido

# --- Huld / PVGIS (CIM26) -----------------------------------------------------
# Conjunto congelado: JRC PVGIS, família c-Si "CURRENT" (docs/02_FORMULACIONES.md).
HULD_COEFFICIENT_SETS = {
    "PVGIS_cSi_current": {
        "k": (-0.017237, -0.040465, -0.004702, 0.000149, 0.000170, 0.000005),
        "technology_family": "c-Si",
        "source": (
            "JRC PVGIS — data sources and calculation methods; família c-Si CURRENT "
            "(https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-"
            "information-system-pvgis/general-information/data-sources-calculation-methods_en)"
        ),
        "temperature_input": "t_module_C (temperatura posterior do módulo)",
    }
}
HULD_DEFAULT_SET = "PVGIS_cSi_current"
HULD_LOW_G_FLAG_WM2 = 50.0        # CIM26: sinalização de extrapolação logarítmica (não exclui)

# Tecnologias aceitas como c-Si para os coeficientes Huld (nomes normalizados)
CSI_TECHNOLOGY_ALIASES = {
    "poly-si", "mono-si", "mono-perc", "multi-si", "c-si", "mc-si", "sc-si",
    "mono-crystalline silicon", "monocrystalline silicon", "multicrystalline silicon",
    "polycrystalline silicon", "mono", "poly",
}

# --- Perfis sintéticos (legado, opção secundária do modo Modelos) ------------
PROFILES = {
    "sunrise_h": 6.0,
    "sunset_h": 18.0,
    "g_peak_clear": 1000.0,
    "g_peak_cloudy": 700.0,
    "g_peak_rainy": 220.0,
    "cloud_depth": 0.55,
    "rain_noise": 0.15,
    "seed": 42,
    "seasons": {
        "Verão": {"t_min": 22.0, "t_max": 34.0, "t_peak_h": 15.0},
        "Inverno": {"t_min": 8.0, "t_max": 20.0, "t_peak_h": 15.0},
        "Outono/Primavera": {"t_min": 15.0, "t_max": 27.0, "t_peak_h": 15.0},
    },
}
