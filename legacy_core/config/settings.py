"""
config/settings.py
==================
Constantes físicas, condiciones de referencia y parámetros por defecto.

Ningún módulo del proyecto debe hardcodear valores numéricos:
todo lo que sea "constante" vive aquí.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constantes físicas fundamentales (CODATA)
# ---------------------------------------------------------------------------
Q_ELECTRON = 1.602176634e-19      # Carga elemental [C]
K_BOLTZMANN = 1.380649e-23        # Constante de Boltzmann [J/K]
KELVIN_0C = 273.15                # 0 °C en Kelvin [K]

# ---------------------------------------------------------------------------
# Condiciones estándar de ensayo (STC) - IEC 61215
# ---------------------------------------------------------------------------
G_REF = 1000.0                    # Irradiancia de referencia [W/m2]
T_REF_C = 25.0                    # Temperatura de célula de referencia [°C]
T_REF_K = T_REF_C + KELVIN_0C     # [K]

# Condiciones NOCT (Nominal Operating Cell Temperature) - IEC 61215
G_NOCT = 800.0                    # Irradiancia de ensayo NOCT [W/m2]
T_AMB_NOCT = 20.0                 # Temperatura ambiente de ensayo NOCT [°C]
V_WIND_NOCT = 1.0                 # Velocidad de viento de ensayo NOCT [m/s]

# ---------------------------------------------------------------------------
# Semiconductor (silicio cristalino) - De Soto et al. (2006)
# ---------------------------------------------------------------------------
EG_REF_SI = 1.121                 # Energy gap del Si a 25 °C [eV]
DEGDT_SI = -0.0002677             # Variación relativa del gap [1/K]

# ---------------------------------------------------------------------------
# Parámetros numéricos por defecto del solver
# ---------------------------------------------------------------------------
SOLVER = {
    "method": "lambertw",         # "lambertw" | "brentq" | "newton"
    "iv_points": 300,             # Nº de puntos de la curva I-V
    "mpp_tol": 1e-6,              # Tolerancia relativa en la búsqueda del MPP [V]
    "current_tol": 1e-10,         # Tolerancia del solver implícito I(V) [A]
    "max_iter": 200,              # Iteraciones máximas
    "g_min": 1.0,                 # Irradiancia mínima para resolver el SDM [W/m2]
    "rs_min": 1e-6,               # Rs mínima admisible (evita división por cero) [ohm]
}

# Rangos (bounds) admisibles para la extracción de los 5 parámetros del SDM
EXTRACTION_BOUNDS = {
    "IL_factor": (0.90, 1.20),    # IL_ref / Isc_stc
    "log10_I0": (-14.0, -4.0),    # log10(I0_ref [A])
    "Rs": (1e-4, 2.5),            # [ohm]
    "log10_Rsh": (1.5, 5.0),      # log10(Rsh_ref [ohm])  -> 31 ohm .. 100 kohm
    "n": (0.80, 2.20),            # Factor de idealidad
}

EXTRACTION_INITIAL_GUESS = {
    "n": 1.10,
    "Rs": 0.30,                   # [ohm]
    "Rsh": 500.0,                 # [ohm]
}

# ---------------------------------------------------------------------------
# Modelo térmico
# ---------------------------------------------------------------------------
THERMAL = {
    "default_noct": 45.0,         # [°C]
    "noct_g_ref": G_NOCT,         # [W/m2]
    "noct_tamb_ref": T_AMB_NOCT,  # [°C]
    # Coeficientes del modelo de Sandia (alternativa a NOCT), techo abierto
    "sandia_a": -3.56,
    "sandia_b": -0.075,
    "sandia_dT": 3.0,             # dT célula-módulo a 1000 W/m2 [°C]
}

# ---------------------------------------------------------------------------
# Generador de perfiles sintéticos
# ---------------------------------------------------------------------------
PROFILES = {
    "timestep_min": 1,            # Resolución temporal por defecto [min]
    "minutes_per_day": 1440,
    "sunrise_h": 6.0,             # Hora de salida del sol por defecto
    "sunset_h": 18.0,             # Hora de puesta del sol por defecto
    "g_peak_clear": 1000.0,       # Irradiancia pico día soleado [W/m2]
    "g_peak_cloudy": 700.0,       # Irradiancia pico (envolvente) día nublado [W/m2]
    "g_peak_rainy": 220.0,        # Irradiancia pico día lluvioso [W/m2]
    "cloud_depth": 0.55,          # Profundidad de las caídas por nubes [0-1]
    "rain_noise": 0.15,           # Ruido relativo en día lluvioso
    "seed": 42,                   # Semilla del generador aleatorio (reproducibilidad)
    "seasons": {
        "Verano": {"t_min": 22.0, "t_max": 34.0, "t_peak_h": 15.0},
        "Invierno": {"t_min": 8.0, "t_max": 20.0, "t_peak_h": 15.0},
        "Otoño/Primavera": {"t_min": 15.0, "t_max": 27.0, "t_peak_h": 15.0},
    },
}

# ---------------------------------------------------------------------------
# Interfaz / estilo (tema claro, minimalista)
# ---------------------------------------------------------------------------
UI = {
    "app_title": "PV Simulator — Single Diode Model",
    "template": "plotly_white",
    "colors": {
        "irradiance": "#F2A65A",
        "t_amb": "#4C9BE8",
        "t_cell": "#E05C5C",
        "power": "#2E7D6B",
        "power_alt": "#9BC1B0",
        "efficiency": "#7A5EA8",
        "energy": "#3C6E9E",
        "grid": "#E6E9EE",
        "neutral": "#6B7280",
    },
    "csv_template_cols": ["timestamp", "G", "Tamb"],
}
