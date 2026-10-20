"""
config/pv_database.py
=====================
Base de datos de módulos fotovoltaicos.

Fuente: hojas de datos públicas de Canadian Solar (valores en STC:
1000 W/m2, AM 1.5, Tcell = 25 °C). Se incluyen:

    -- Policristalinos --
    CS6P-250P  (Quartech,  60 células, 2013-2015)
    CS6P-260P  (Quartech,  60 células, 2013-2015)
    CS6K-275P  (KuPower,   60 células, 2016-2018)
    CS6X-315P  (MaxPower,  72 células, 2014-2016)
    CS6U-330P  (MaxPower2, 72 células, 2016-2019)

    -- Monocristalinos PERC (HiKu / HiKu7) --
    CS3W-430|435|440|445|450|455MS  (HiKu,  144 células 2x(12x6), 2020)
    CS7L-580|585|590|595|600MS      (HiKu7, 120 células 2x(10x6), 2020)

Los parámetros del SDM (IL, I0, Rs, Rsh, n) NO son publicados por el
fabricante. El campo `sdm` queda por tanto en None y se ESTIMA en tiempo de
ejecución con `simulation.solver.extract_sdm_params()`. Si el usuario dispone
de mejores parámetros (p. ej. de la base CEC o de un ensayo flash), puede:

    * cargarlos aquí, rellenando el diccionario `sdm`;
    * o editarlos directamente desde la pestaña 1 de la aplicación.

--- CÓMO AÑADIR UN MÓDULO NUEVO ---------------------------------------------
Basta con agregar una entrada al diccionario MODULE_DB con la misma estructura.
No hay que tocar ninguna otra parte del código.
-----------------------------------------------------------------------------
"""

from __future__ import annotations

from typing import Dict, List, Optional

from models.pv_module import ModuleSTC, SDMParams, PVModule

CUSTOM_KEY = "Personalizado"

# ---------------------------------------------------------------------------
# Datos de catálogo (STC)
# ---------------------------------------------------------------------------
MODULE_DB: Dict[str, dict] = {
    "CS6P-250P": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS6P-250P (Quartech)",
            technology="Poly-Si",
            p_nom=250.0, v_oc=37.2, i_sc=8.87, v_mp=30.1, i_mp=8.30,
            n_cells=60,
            alpha_isc_pct=0.065, beta_voc_pct=-0.34, gamma_pmax_pct=-0.43,
            noct=45.0, length=1.638, width=0.982,
            notes="4 busbars. Eficiencia de catálogo 15.54 %.",
        ),
        "sdm": None,
    },
    "CS6P-260P": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS6P-260P (Quartech)",
            technology="Poly-Si",
            p_nom=260.0, v_oc=37.5, i_sc=9.10, v_mp=30.4, i_mp=8.56,
            n_cells=60,
            alpha_isc_pct=0.065, beta_voc_pct=-0.34, gamma_pmax_pct=-0.43,
            noct=45.0, length=1.638, width=0.982,
            notes="Misma plataforma que el CS6P-250P. Eficiencia 16.16 %.",
        ),
        "sdm": None,
    },
    "CS6K-275P": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS6K-275P (KuPower)",
            technology="Poly-Si",
            p_nom=275.0, v_oc=38.0, i_sc=9.45, v_mp=31.0, i_mp=8.88,
            n_cells=60,
            alpha_isc_pct=0.053, beta_voc_pct=-0.31, gamma_pmax_pct=-0.41,
            noct=45.0, length=1.650, width=0.992,
            notes="Generación KuPower, 5 busbars. Eficiencia 16.80 %.",
        ),
        "sdm": None,
    },
    "CS6X-315P": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS6X-315P (MaxPower)",
            technology="Poly-Si",
            p_nom=315.0, v_oc=45.1, i_sc=9.18, v_mp=36.6, i_mp=8.61,
            n_cells=72,
            alpha_isc_pct=0.065, beta_voc_pct=-0.34, gamma_pmax_pct=-0.43,
            noct=45.0, length=1.954, width=0.982,
            notes="72 células. Módulo típico de planta utility. Eficiencia 16.42 %.",
        ),
        "sdm": None,
    },
    "CS6U-330P": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS6U-330P (MaxPower2)",
            technology="Poly-Si",
            p_nom=330.0, v_oc=45.6, i_sc=9.45, v_mp=37.2, i_mp=8.88,
            n_cells=72,
            alpha_isc_pct=0.053, beta_voc_pct=-0.31, gamma_pmax_pct=-0.41,
            noct=45.0, length=1.960, width=0.992,
            notes="Eficiencia 16.97 %. Muy usado en plantas en Brasil/Paraguay.",
        ),
        "sdm": None,
    },

    # -----------------------------------------------------------------------
    # HiKu — mono-PERC, 144 células (2x72), datasheet CS3W-MS (mayo 2020)
    # https://www.canadiansolar.com/wp-content/uploads/2019/12/
    #     Canadian_Solar-Datasheet-HiKu_CS3W-MS_EN.pdf
    # NOCT = NMOT del datasheet (800 W/m2, Tamb 20°C, viento 1 m/s) = 42°C
    # -----------------------------------------------------------------------
    "CS3W-430MS": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS3W-430MS (HiKu)",
            technology="Mono-PERC",
            p_nom=430.0, v_oc=48.3, i_sc=11.37, v_mp=40.3, i_mp=10.68,
            n_cells=72,   # Ns eléctrico: 144 semicélulas = 2 strings paralelos de 72 en serie
            alpha_isc_pct=0.05, beta_voc_pct=-0.27, gamma_pmax_pct=-0.35,
            noct=42.0, length=2.108, width=1.048,
            notes="Mono PERC, 144 células [2x(12x6)]. Eficiencia 19.5 %.",
        ),
        "sdm": None,
    },
    "CS3W-435MS": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS3W-435MS (HiKu)",
            technology="Mono-PERC",
            p_nom=435.0, v_oc=48.5, i_sc=11.42, v_mp=40.5, i_mp=10.75,
            n_cells=72,   # Ns eléctrico: 144 semicélulas = 2 strings paralelos de 72 en serie
            alpha_isc_pct=0.05, beta_voc_pct=-0.27, gamma_pmax_pct=-0.35,
            noct=42.0, length=2.108, width=1.048,
            notes="Mono PERC, 144 células [2x(12x6)]. Eficiencia 19.7 %.",
        ),
        "sdm": None,
    },
    "CS3W-440MS": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS3W-440MS (HiKu)",
            technology="Mono-PERC",
            p_nom=440.0, v_oc=48.7, i_sc=11.48, v_mp=40.7, i_mp=10.82,
            n_cells=72,   # Ns eléctrico: 144 semicélulas = 2 strings paralelos de 72 en serie
            alpha_isc_pct=0.05, beta_voc_pct=-0.27, gamma_pmax_pct=-0.35,
            noct=42.0, length=2.108, width=1.048,
            notes="Mono PERC, 144 células [2x(12x6)]. Eficiencia 19.9 %.",
        ),
        "sdm": None,
    },
    "CS3W-445MS": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS3W-445MS (HiKu)",
            technology="Mono-PERC",
            p_nom=445.0, v_oc=48.9, i_sc=11.54, v_mp=40.9, i_mp=10.89,
            n_cells=72,   # Ns eléctrico: 144 semicélulas = 2 strings paralelos de 72 en serie
            alpha_isc_pct=0.05, beta_voc_pct=-0.27, gamma_pmax_pct=-0.35,
            noct=42.0, length=2.108, width=1.048,
            notes="Mono PERC, 144 células [2x(12x6)]. Eficiencia 20.1 %.",
        ),
        "sdm": None,
    },
    "CS3W-450MS": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS3W-450MS (HiKu)",
            technology="Mono-PERC",
            p_nom=450.0, v_oc=49.1, i_sc=11.60, v_mp=41.1, i_mp=10.96,
            n_cells=72,   # Ns eléctrico: 144 semicélulas = 2 strings paralelos de 72 en serie
            alpha_isc_pct=0.05, beta_voc_pct=-0.27, gamma_pmax_pct=-0.35,
            noct=42.0, length=2.108, width=1.048,
            notes="Mono PERC, 144 células [2x(12x6)]. Eficiencia 20.4 %.",
        ),
        "sdm": None,
    },
    "CS3W-455MS": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS3W-455MS (HiKu)",
            technology="Mono-PERC",
            p_nom=455.0, v_oc=49.3, i_sc=11.66, v_mp=41.3, i_mp=11.02,
            n_cells=72,   # Ns eléctrico: 144 semicélulas = 2 strings paralelos de 72 en serie
            alpha_isc_pct=0.05, beta_voc_pct=-0.27, gamma_pmax_pct=-0.35,
            noct=42.0, length=2.108, width=1.048,
            notes="Mono PERC, 144 células [2x(12x6)]. Eficiencia 20.6 %.",
        ),
        "sdm": None,
    },

    # -----------------------------------------------------------------------
    # HiKu7 — mono-PERC, 120 células (2x60), datasheet CS7L-MS v1.3
    # (preliminar/utility scale), oct-2020. NOCT = NMOT = 42°C.
    # -----------------------------------------------------------------------
    "CS7L-580MS": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS7L-580MS (HiKu7)",
            technology="Mono-PERC",
            p_nom=580.0, v_oc=40.5, i_sc=18.27, v_mp=34.1, i_mp=17.02,
            n_cells=60,   # Ns eléctrico: 120 semicélulas = 2 strings paralelos de 60 en serie
            alpha_isc_pct=0.05, beta_voc_pct=-0.26, gamma_pmax_pct=-0.34,
            noct=42.0, length=2.172, width=1.303,
            notes="Mono PERC utility, 120 células [2x(10x6)]. Eficiencia 20.5 %.",
        ),
        "sdm": None,
    },
    "CS7L-585MS": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS7L-585MS (HiKu7)",
            technology="Mono-PERC",
            p_nom=585.0, v_oc=40.7, i_sc=18.32, v_mp=34.3, i_mp=17.06,
            n_cells=60,   # Ns eléctrico: 120 semicélulas = 2 strings paralelos de 60 en serie
            alpha_isc_pct=0.05, beta_voc_pct=-0.26, gamma_pmax_pct=-0.34,
            noct=42.0, length=2.172, width=1.303,
            notes="Mono PERC utility, 120 células [2x(10x6)]. Eficiencia 20.7 %.",
        ),
        "sdm": None,
    },
    "CS7L-590MS": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS7L-590MS (HiKu7)",
            technology="Mono-PERC",
            p_nom=590.0, v_oc=40.9, i_sc=18.37, v_mp=34.5, i_mp=17.11,
            n_cells=60,   # Ns eléctrico: 120 semicélulas = 2 strings paralelos de 60 en serie
            alpha_isc_pct=0.05, beta_voc_pct=-0.26, gamma_pmax_pct=-0.34,
            noct=42.0, length=2.172, width=1.303,
            notes="Mono PERC utility, 120 células [2x(10x6)]. Eficiencia 20.8 %.",
        ),
        "sdm": None,
    },
    "CS7L-595MS": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS7L-595MS (HiKu7)",
            technology="Mono-PERC",
            p_nom=595.0, v_oc=41.1, i_sc=18.42, v_mp=34.7, i_mp=17.15,
            n_cells=60,   # Ns eléctrico: 120 semicélulas = 2 strings paralelos de 60 en serie
            alpha_isc_pct=0.05, beta_voc_pct=-0.26, gamma_pmax_pct=-0.34,
            noct=42.0, length=2.172, width=1.303,
            notes="Mono PERC utility, 120 células [2x(10x6)]. Eficiencia 21.0 %.",
        ),
        "sdm": None,
    },
    "CS7L-600MS": {
        "stc": dict(
            manufacturer="Canadian Solar",
            model="CS7L-600MS (HiKu7)",
            technology="Mono-PERC",
            p_nom=600.0, v_oc=41.3, i_sc=18.47, v_mp=34.9, i_mp=17.20,
            n_cells=60,   # Ns eléctrico: 120 semicélulas = 2 strings paralelos de 60 en serie
            alpha_isc_pct=0.05, beta_voc_pct=-0.26, gamma_pmax_pct=-0.34,
            noct=42.0, length=2.172, width=1.303,
            notes="Mono PERC utility, 120 células [2x(10x6)]. Eficiencia 21.2 %.",
        ),
        "sdm": None,
    },
}


# ---------------------------------------------------------------------------
# API de la base de datos
# ---------------------------------------------------------------------------
def list_manufacturers() -> List[str]:
    """Fabricantes disponibles (+ opción personalizada)."""
    mans = sorted({e["stc"]["manufacturer"] for e in MODULE_DB.values()})
    return mans + [CUSTOM_KEY]


def list_models(manufacturer: str) -> List[str]:
    """Modelos de un fabricante dado."""
    if manufacturer == CUSTOM_KEY:
        return [CUSTOM_KEY]
    return [k for k, e in MODULE_DB.items() if e["stc"]["manufacturer"] == manufacturer]


def get_module(key: str) -> PVModule:
    """Devuelve un PVModule (con sdm=None si no hay parámetros publicados)."""
    if key not in MODULE_DB:
        raise KeyError(f"Módulo no encontrado en la base de datos: {key!r}")
    entry = MODULE_DB[key]
    stc = ModuleSTC(**entry["stc"])

    sdm: Optional[SDMParams] = None
    if entry.get("sdm"):
        sdm = SDMParams(n_cells=stc.n_cells, source="datasheet", **entry["sdm"])

    return PVModule(stc=stc, sdm=sdm)


def default_custom_stc() -> ModuleSTC:
    """Plantilla editable para el modo 'Personalizado'."""
    return ModuleSTC(
        manufacturer="Personalizado",
        model="Módulo definido por el usuario",
        technology="Poly-Si",
        p_nom=300.0, v_oc=40.0, i_sc=9.50, v_mp=32.5, i_mp=9.23,
        n_cells=60,
        alpha_isc_pct=0.05, beta_voc_pct=-0.30, gamma_pmax_pct=-0.39,
        noct=45.0, length=1.700, width=1.000,
        notes="Editable en su totalidad.",
    )
