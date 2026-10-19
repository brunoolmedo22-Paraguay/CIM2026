"""Descrição de módulo FV comum aos dois modos (datasheet comercial ou ficha experimental).

Campos desconhecidos permanecem ``None``: nunca são inventados nem substituídos
por valores de outro módulo.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional

from ..constants import CSI_TECHNOLOGY_ALIASES, DEGDT_SI, EG_REF_SI, G_REF

KIND_DATASHEET = "datasheet_comercial"
KIND_EXPERIMENTAL = "ficha_experimental"
KIND_USER = "usuario"


@dataclass
class ModuleSpec:
    id: str
    kind: str
    technology: str
    p_stc_W: float
    v_oc_V: Optional[float] = None
    i_sc_A: Optional[float] = None
    v_mp_V: Optional[float] = None
    i_mp_A: Optional[float] = None
    n_cells_series: Optional[int] = None
    alpha_isc_pct_C: Optional[float] = None
    beta_voc_pct_C: Optional[float] = None
    gamma_pmax_pct_C: Optional[float] = None
    noct_C: Optional[float] = None
    u0_W_m2K: Optional[float] = None
    u1_W_s_m3K: Optional[float] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    eg_ref_eV: float = EG_REF_SI
    degdt_per_K: float = DEGDT_SI
    source: str = ""
    p_stc_meaning: str = "potência nominal de placa (datasheet)"
    notes: str = ""
    extra: dict = field(default_factory=dict)

    # -- derivadas --------------------------------------------------------
    @property
    def label(self) -> str:
        if self.manufacturer and self.model:
            return f"{self.manufacturer} {self.model}"
        return self.id

    @property
    def gamma_per_C(self) -> Optional[float]:
        """γ em 1/°C, conversão exata γ_pct/100."""
        return None if self.gamma_pmax_pct_C is None else self.gamma_pmax_pct_C / 100.0

    @property
    def alpha_isc_A_per_C(self) -> Optional[float]:
        if self.alpha_isc_pct_C is None or self.i_sc_A is None:
            return None
        return self.alpha_isc_pct_C / 100.0 * self.i_sc_A

    @property
    def beta_voc_V_per_C(self) -> Optional[float]:
        if self.beta_voc_pct_C is None or self.v_oc_V is None:
            return None
        return self.beta_voc_pct_C / 100.0 * self.v_oc_V

    @property
    def area_m2(self) -> Optional[float]:
        if self.length_m and self.width_m:
            return self.length_m * self.width_m
        return None

    @property
    def efficiency_stc(self) -> Optional[float]:
        a = self.area_m2
        return None if not a else self.p_stc_W / (a * G_REF)

    @property
    def is_csi(self) -> bool:
        return self.technology.strip().lower() in CSI_TECHNOLOGY_ALIASES

    def classical_sdm_inputs_missing(self) -> list[str]:
        req = {
            "Voc": self.v_oc_V, "Isc": self.i_sc_A, "Vmp": self.v_mp_V, "Imp": self.i_mp_A,
            "Ns": self.n_cells_series, "α_Isc": self.alpha_isc_pct_C, "β_Voc": self.beta_voc_pct_C,
        }
        return [k for k, v in req.items() if v is None]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ModuleSpec":
        keys = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in keys})


def validate_module(m: ModuleSpec) -> list[tuple[str, str]]:
    """Validações físicas. Retorna lista de (nível, mensagem); nível ∈ {erro, aviso}."""
    out: list[tuple[str, str]] = []
    if not m.id.strip():
        out.append(("erro", "Identificador vazio."))
    if not (m.p_stc_W and m.p_stc_W > 0):
        out.append(("erro", "Pstc deve ser > 0 W."))
    for name, v in (("Voc", m.v_oc_V), ("Isc", m.i_sc_A), ("Vmp", m.v_mp_V), ("Imp", m.i_mp_A)):
        if v is not None and v <= 0:
            out.append(("erro", f"{name} deve ser > 0."))
    if m.v_oc_V and m.i_sc_A and m.p_stc_W and m.p_stc_W > m.v_oc_V * m.i_sc_A:
        out.append(("erro", "Pmp > Voc·Isc é fisicamente impossível."))
    if m.v_mp_V and m.v_oc_V and m.v_mp_V >= m.v_oc_V:
        out.append(("erro", "Vmp deve ser menor que Voc."))
    if m.i_mp_A and m.i_sc_A and m.i_mp_A >= m.i_sc_A:
        out.append(("erro", "Imp deve ser menor que Isc."))
    if m.v_mp_V and m.i_mp_A and m.p_stc_W:
        rel = abs(m.v_mp_V * m.i_mp_A - m.p_stc_W) / m.p_stc_W
        if rel > 0.02:
            out.append(("aviso", f"Vmp·Imp difere {rel:.1%} de Pstc; verifique o datasheet."))
    if m.n_cells_series is not None and (int(m.n_cells_series) != m.n_cells_series or m.n_cells_series <= 0):
        out.append(("erro", "Ns deve ser inteiro positivo."))
    if m.gamma_pmax_pct_C is not None and m.gamma_pmax_pct_C >= 0:
        out.append(("aviso", "γ_Pmax ≥ 0 é incomum para c-Si; confirme a fonte."))
    if m.beta_voc_pct_C is not None and m.beta_voc_pct_C >= 0:
        out.append(("aviso", "β_Voc ≥ 0 é incomum; confirme a fonte."))
    if m.alpha_isc_pct_C is not None and m.alpha_isc_pct_C < 0:
        out.append(("aviso", "α_Isc < 0 é incomum; confirme a fonte."))
    if m.noct_C is not None and not (30 <= m.noct_C <= 60):
        out.append(("aviso", "NOCT fora de 30–60 °C."))
    return out
