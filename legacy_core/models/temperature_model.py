"""
models/temperature_model.py
===========================
Modelos de temperatura de célula Tc = f(Tamb, G, viento).

Modelo principal (el pedido en la especificación) — NOCT:

    Tc = Tamb + (NOCT - 20) / 800 * G                                     (2)

donde 20 °C y 800 W/m2 son las condiciones del ensayo NOCT (IEC 61215).
El NOCT es un parámetro EDITABLE desde la interfaz.

Modelo alternativo (opcional, para sensibilidad) — Sandia:

    Tm = G * exp(a + b*ws) + Tamb
    Tc = Tm + (G/G_ref) * dT
"""

from __future__ import annotations

from typing import Union

import numpy as np

from config.settings import THERMAL, G_REF

ArrayLike = Union[float, np.ndarray]


def cell_temperature_noct(
    t_amb: ArrayLike,
    G: ArrayLike,
    noct: float = THERMAL["default_noct"],
) -> ArrayLike:
    """
    Temperatura de célula por el modelo NOCT (ecuación 2).

    Parameters
    ----------
    t_amb : Temperatura ambiente [°C]
    G     : Irradiancia en el plano del módulo [W/m2]
    noct  : NOCT del módulo [°C]  (editable)

    Returns
    -------
    Tc : Temperatura de célula [°C]
    """
    t_amb = np.asarray(t_amb, dtype=float)
    G = np.asarray(G, dtype=float)
    factor = (noct - THERMAL["noct_tamb_ref"]) / THERMAL["noct_g_ref"]
    return t_amb + factor * G


def cell_temperature_sandia(
    t_amb: ArrayLike,
    G: ArrayLike,
    wind_speed: ArrayLike = 1.0,
    a: float = THERMAL["sandia_a"],
    b: float = THERMAL["sandia_b"],
    delta_t: float = THERMAL["sandia_dT"],
) -> ArrayLike:
    """Modelo térmico de Sandia (King et al., 2004). Alternativa al NOCT."""
    t_amb = np.asarray(t_amb, dtype=float)
    G = np.asarray(G, dtype=float)
    ws = np.asarray(wind_speed, dtype=float)

    t_module = G * np.exp(a + b * ws) + t_amb
    return t_module + (G / G_REF) * delta_t


# Registro de modelos disponibles (fácil de extender)
TEMPERATURE_MODELS = {
    "NOCT": cell_temperature_noct,
    "Sandia": cell_temperature_sandia,
}
