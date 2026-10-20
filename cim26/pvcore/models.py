"""Os quatro modelos do CIM26 com interface comum.

    prepare(model_id, module, sdm_ref) -> parâmetros ajustados (ou Availability negativa)
    predict(model_id, conditions, params) -> ModelOutput(p_mpp_W, status, diagnostics)

Saída sempre por MÓDULO; o escalonamento a arranjo (Ns·Np) é feito fora
(``scale_to_array``), apenas no modo Modelos.

M1  P = Pstc · G/1000
M2  P = max(0, Pstc · G/1000 · [1 + γ (Tcell − 25)])       (PVWatts DC; γ em 1/°C)
M3  P = Pstc · u · η_rel(u, Tmod),  u = G/1000              (Huld / PVGIS, c-Si CURRENT)
M4  P = Pmp do SDM resolvido por Lambert W + busca limitada (núcleo legado)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

import numpy as np

from ..constants import (
    G_REF,
    HULD_COEFFICIENT_SETS,
    HULD_DEFAULT_SET,
    HULD_LOW_G_FLAG_WM2,
    T_REF_C,
)
from . import sdm as _sdm
from .module import ModuleSpec
from .thermal import Conditions

MODEL_IDS = ("M1", "M2", "M3", "M4")


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    short: str
    temperature_input: str          # "nenhuma" | "t_cell_C" | "t_module_C"
    equation: str
    requirements: str
    color: str


MODEL_INFO = {
    "M1": ModelInfo("M1", "Proporcional à irradiância", "Irradiância", "nenhuma",
                    "P = Pstc·G/1000", "Pstc", "#3B82C4"),
    "M2": ModelInfo("M2", "Correção térmica / PVWatts DC", "Térmico/PVWatts", "t_cell_C",
                    "P = max(0, Pstc·G/1000·[1+γ(Tcell−25)])", "Pstc, γ (1/°C), Tcell", "#1E9E7A"),
    "M3": ModelInfo("M3", "Huld / PVGIS (c-Si CURRENT)", "Huld/PVGIS", "t_module_C",
                    "P = Pstc·u·[1+k1 ln u+k2 ln²u+k3ΔT+k4ΔT ln u+k5ΔT ln²u+k6ΔT²]",
                    "Pstc, família tecnológica (6 coeficientes genéricos), Tmod", "#D98E04"),
    "M4": ModelInfo("M4", "Modelo de um diodo (SDM)", "SDM", "t_cell_C",
                    "I = IL − I0[exp((V+IRs)/a)−1] − (V+IRs)/Rsh; Pmp numérico",
                    "5 parâmetros efetivos (IL, I0, Rs, Rsh, a_ref), α_Isc, Eg; calibração", "#B4507A"),
}


@dataclass
class Availability:
    available: bool
    reason: str


@dataclass
class ModelParams:
    model_id: str
    p_stc_W: Optional[float] = None
    gamma_per_C: Optional[float] = None
    huld_k: Optional[tuple] = None
    huld_set: Optional[str] = None
    sdm: Optional[_sdm.SDMReference] = None
    source: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.sdm is not None:
            d["sdm"] = self.sdm.to_dict()
        if self.huld_k is not None:
            d["huld_k"] = list(self.huld_k)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ModelParams":
        d = dict(d)
        if d.get("sdm") is not None:
            d["sdm"] = _sdm.SDMReference.from_dict(d["sdm"])
        if d.get("huld_k") is not None:
            d["huld_k"] = tuple(d["huld_k"])
        return cls(**d)


@dataclass
class ModelOutput:
    model_id: str
    p_mpp_W: np.ndarray
    status: np.ndarray
    diagnostics: dict = field(default_factory=dict)
    extra: dict = field(default_factory=dict)      # p.ex. Vmp/Imp/Voc/Isc do SDM

    @property
    def n_valid(self) -> int:
        return int(np.isfinite(self.p_mpp_W).sum())


# ---------------------------------------------------------------------------
# Disponibilidade e preparação
# ---------------------------------------------------------------------------
def availability(model_id: str, module: ModuleSpec, sdm_ref: Optional[_sdm.SDMReference] = None) -> Availability:
    if module.p_stc_W is None or not module.p_stc_W > 0:
        return Availability(False, "Pstc ausente ou inválida.")
    if model_id == "M1":
        return Availability(True, "Requer apenas Pstc.")
    if model_id == "M2":
        if module.gamma_pmax_pct_C is None:
            return Availability(False, "γ_Pmax não disponível na ficha do módulo.")
        return Availability(True, "Pstc e γ_Pmax disponíveis.")
    if model_id == "M3":
        if not module.is_csi:
            return Availability(False, f"Tecnologia '{module.technology}' sem coeficientes Huld "
                                       "verificados no pacote; c-Si não é usado por padrão.")
        return Availability(True, "Coeficientes tecnológicos genéricos PVGIS c-Si CURRENT "
                                  "(não calibrados para este módulo).")
    if model_id == "M4":
        if sdm_ref is None:
            return Availability(False, "Parâmetros SDM ainda não estimados (use “Estimar parâmetros SDM”).")
        return Availability(True, f"Parâmetros SDM disponíveis (método: {sdm_ref.method}).")
    raise KeyError(model_id)


def prepare(model_id: str, module: ModuleSpec, sdm_ref: Optional[_sdm.SDMReference] = None,
            huld_set: str = HULD_DEFAULT_SET) -> ModelParams:
    av = availability(model_id, module, sdm_ref)
    if not av.available:
        raise ValueError(f"{model_id} indisponível: {av.reason}")
    src = {"module_id": module.id, "module_source": module.source,
           "p_stc_meaning": module.p_stc_meaning}
    if model_id == "M1":
        return ModelParams("M1", p_stc_W=float(module.p_stc_W), source=src)
    if model_id == "M2":
        src["gamma"] = f"γ = {module.gamma_pmax_pct_C} %/°C ÷ 100"
        return ModelParams("M2", p_stc_W=float(module.p_stc_W), gamma_per_C=float(module.gamma_per_C), source=src)
    if model_id == "M3":
        cs = HULD_COEFFICIENT_SETS[huld_set]
        src["huld"] = cs["source"]
        return ModelParams("M3", p_stc_W=float(module.p_stc_W), huld_k=tuple(cs["k"]), huld_set=huld_set, source=src)
    src["sdm_method"] = sdm_ref.method
    return ModelParams("M4", sdm=sdm_ref, source=src)


# ---------------------------------------------------------------------------
# Equações
# ---------------------------------------------------------------------------
def _check_g(g: np.ndarray) -> None:
    finite = np.isfinite(g)
    if np.any(g[finite] < 0):
        raise ValueError("Gpoa negativa: limpe/filtre o dataset antes de prever.")


def m1_power(g_poa, p_stc_W: float) -> np.ndarray:
    g = np.asarray(g_poa, dtype=float)
    return p_stc_W * (g / G_REF)


def m2_power(g_poa, t_cell_C, p_stc_W: float, gamma_per_C: float) -> np.ndarray:
    g = np.asarray(g_poa, dtype=float)
    t = np.asarray(t_cell_C, dtype=float)
    return np.maximum(0.0, p_stc_W * (g / G_REF) * (1.0 + gamma_per_C * (t - T_REF_C)))


def _huld(g: np.ndarray, t: np.ndarray, p_stc_W: float, k):
    """Retorna (P recortada, η_rel). G<=0 → P=0 sem avaliar log(0)."""
    k1, k2, k3, k4, k5, k6 = k
    pos = g > 0
    u = np.where(pos, g / G_REF, 1.0)          # u=1 onde G<=0 (posições descartadas)
    lu = np.log(u)
    dT = t - T_REF_C
    eta = 1.0 + k1 * lu + k2 * lu**2 + k3 * dT + k4 * dT * lu + k5 * dT * lu**2 + k6 * dT**2
    p = np.where(pos, np.maximum(0.0, p_stc_W * u * eta), np.where(np.isfinite(g), 0.0, np.nan))
    return p, eta


def m3_power(g_poa, t_module_C, p_stc_W: float, k) -> np.ndarray:
    """Huld. G=0 → 0 sem avaliar log(0); resultado negativo recortado a 0."""
    return _huld(np.asarray(g_poa, float), np.asarray(t_module_C, float), p_stc_W, k)[0]


def _status_simple(g: np.ndarray, p: np.ndarray, raw: Optional[np.ndarray] = None,
                   low_g_flag: Optional[float] = None) -> np.ndarray:
    st = np.zeros(g.shape, dtype=np.int8)
    st[g == 0] = _sdm.ST_ZERO_IRRADIANCE
    if low_g_flag is not None:
        st[(g > 0) & (g < low_g_flag)] = _sdm.ST_LOW_G_EXTRAPOLATION
    if raw is not None:
        st[(g > 0) & (raw <= 0)] = _sdm.ST_CLIPPED_ZERO
    st[~np.isfinite(p)] = _sdm.ST_FAILED
    return st


def _predict_vector(model_id: str, cond: Conditions, params: ModelParams) -> ModelOutput:
    g = cond.g_poa_Wm2
    _check_g(g)
    if model_id == "M1":
        p = m1_power(g, params.p_stc_W)
        return ModelOutput("M1", p, _status_simple(g, p))
    if model_id == "M2":
        raw = params.p_stc_W * (g / G_REF) * (1.0 + params.gamma_per_C * (cond.t_cell_C - T_REF_C))
        p = m2_power(g, cond.t_cell_C, params.p_stc_W, params.gamma_per_C)
        return ModelOutput("M2", p, _status_simple(g, p, raw))
    if model_id == "M3":
        p, eta = _huld(g, cond.t_module_C, params.p_stc_W, params.huld_k)
        st = _status_simple(g, p, None, HULD_LOW_G_FLAG_WM2)
        st[(g > 0) & (eta <= 0)] = _sdm.ST_CLIPPED_ZERO
        return ModelOutput("M3", p, st)
    if model_id == "M4":
        return _predict_sdm(cond, params)
    raise KeyError(model_id)


def _predict_sdm(cond: Conditions, params: ModelParams) -> ModelOutput:
    ref = params.sdm
    n = len(cond)
    p = np.empty(n)
    st = np.empty(n, dtype=np.int8)
    vmp = np.empty(n); imp = np.empty(n); voc = np.empty(n); isc = np.empty(n)
    nfev_total = 0
    n_fail = 0
    g_arr, t_arr = cond.g_poa_Wm2, cond.t_cell_C
    for i in range(n):
        try:
            r = _sdm.mpp_at(ref, float(g_arr[i]), float(t_arr[i]))
        except Exception:  # falha numérica registrada, nunca silenciada
            r = dict(Pmp=np.nan, Vmp=np.nan, Imp=np.nan, Voc=np.nan, Isc=np.nan,
                     status=_sdm.ST_FAILED, nfev=0)
        p[i] = r["Pmp"]; vmp[i] = r["Vmp"]; imp[i] = r["Imp"]; voc[i] = r["Voc"]; isc[i] = r["Isc"]
        st[i] = r["status"]
        nfev_total += r.get("nfev", 0)
        if r["status"] == _sdm.ST_FAILED:
            n_fail += 1
    diag = {
        "solver": "Lambert W (I(V)) + varredura 60 pts + Brent limitado (xatol=1e-6 V)",
        "nfev_total": int(nfev_total),
        "n_failed": int(n_fail),
        "n_refine_not_converged": int((st == _sdm.ST_REFINE_NOT_CONVERGED).sum()),
        "n_coarse_fallback": int((st == _sdm.ST_COARSE_FALLBACK).sum()),
    }
    return ModelOutput("M4", p, st, diag, extra={"Vmp_V": vmp, "Imp_A": imp, "Voc_V": voc, "Isc_A": isc})


def predict(model_id: str, cond: Conditions, params: ModelParams, mode: str = "vetorizado") -> ModelOutput:
    """Avalia o modelo.

    mode="vetorizado": M1–M3 operam sobre o array; M4 itera amostra a amostra
    (o algoritmo do SDM é intrinsecamente escalar).
    mode="escalar": TODOS os modelos são chamados amostra a amostra com a MESMA
    função física (arrays de 1 elemento). Usado em experimento separado.
    """
    if mode == "vetorizado" or model_id == "M4":
        return _predict_vector(model_id, cond, params)
    if mode != "escalar":
        raise ValueError(f"modo desconhecido: {mode}")
    n = len(cond)
    p = np.empty(n)
    st = np.empty(n, dtype=np.int8)
    for i in range(n):
        out = _predict_vector(model_id, cond.subset(slice(i, i + 1)), params)
        p[i] = out.p_mpp_W[0]
        st[i] = out.status[0]
    return ModelOutput(model_id, p, st, {"mode": "escalar"})


def scale_to_array(p_module_W: np.ndarray, n_series: int, n_parallel: int) -> np.ndarray:
    """P_arranjo = Ns·Np·P_módulo (sem perdas de mismatch/cabeamento)."""
    if int(n_series) < 1 or int(n_parallel) < 1:
        raise ValueError("Ns e Np devem ser inteiros positivos.")
    return np.asarray(p_module_W, float) * int(n_series) * int(n_parallel)
