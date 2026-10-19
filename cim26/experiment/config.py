"""Configuração imutável e serializável de um experimento do modo Artigo."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, replace

import numpy as np

from ..calibration.multipoint import MultipointConfig
from ..data.anomalies import AnomalyConfig
from ..constants import HULD_DEFAULT_SET, SANDIA_DELTA_T_DEFAULT_C
from ..data.supsi_field import AVAILABLE_MONTHS
from ..pvcore.models import MODEL_IDS

ORDER_MODES = ("rotativa", "aleatoria")
EXEC_MODES = ("vetorizado", "escalar")
ANOMALY_POLICIES = ("sinalizar", "excluir_erros", "excluir_erros_suspeitos")


@dataclass(frozen=True)
class ExperimentConfig:
    months: tuple = AVAILABLE_MONTHS
    module_id: str = "SUPSI_MONO_SI_REFERENCE"
    thermal_strategy: str = "A_tmod_medida"          # | "B_faiman"
    delta_t_C: float = SANDIA_DELTA_T_DEFAULT_C      # hipótese (Sandia eq. 23)
    g_threshold_Wm2: float = 100.0                   # pré-definido ANTES de ver RMSE
    g_max_Wm2: float = 1500.0
    max_gap_min: float = 7.5
    t_module_range_C: tuple = (-40.0, 90.0)
    repetitions: int = 11
    order_mode: str = "rotativa"
    seed: int = 20261019
    warmup_samples: int = 500
    execution_mode: str = "vetorizado"
    scaling_enabled: bool = True
    scaling_sizes: tuple = (250, 1000, 4000)
    tracemalloc_pass: bool = True
    sensitivity_enabled: bool = True
    sensitivity_delta_t: tuple = (0.0, 2.0, 3.0, 5.0)
    sensitivity_g_thresholds: tuple = (50.0, 100.0, 200.0)
    bootstrap_B: int = 2000
    huld_set: str = HULD_DEFAULT_SET
    calibration: dict = field(default_factory=lambda: json.loads(json.dumps(MultipointConfig().to_dict())))
    anomaly_policy: str = "sinalizar"                # | "excluir_erros" | "excluir_erros_suspeitos"
    anomaly: dict = field(default_factory=lambda: AnomalyConfig().to_dict())
    label: str = ""

    def validate(self) -> None:
        if not isinstance(self.repetitions, (int, np.integer)) or not 3 <= int(self.repetitions) <= 101:
            raise ValueError("Repetições deve ser inteiro entre 3 e 101.")
        if self.order_mode not in ORDER_MODES:
            raise ValueError(f"Modo de ordem inválido: {self.order_mode}")
        if self.execution_mode not in EXEC_MODES:
            raise ValueError(f"Modo de execução inválido: {self.execution_mode}")
        if self.thermal_strategy not in ("A_tmod_medida", "B_faiman"):
            raise ValueError("Estratégia térmica do Artigo deve ser A_tmod_medida ou B_faiman.")
        if not self.months or any(m not in AVAILABLE_MONTHS for m in self.months):
            raise ValueError("Meses inválidos.")
        if self.g_threshold_Wm2 < 0 or self.max_gap_min <= 0:
            raise ValueError("Limiar/lacuna inválidos.")
        if self.anomaly_policy not in ANOMALY_POLICIES:
            raise ValueError(f"Política de anomalias inválida: {self.anomaly_policy}")
        if self.warmup_samples < 1:
            raise ValueError("Aquecimento deve usar ≥ 1 amostra.")

    def to_dict(self) -> dict:
        d = asdict(self)
        for k, v in d.items():
            if isinstance(v, tuple):
                d[k] = list(v)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ExperimentConfig":
        keys = set(cls.__dataclass_fields__)
        kw = {}
        for k, v in d.items():
            if k not in keys:
                continue
            kw[k] = tuple(v) if isinstance(v, list) else v
        return cls(**kw)

    def with_(self, **kw) -> "ExperimentConfig":
        return replace(self, **kw)

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.to_dict(), sort_keys=True).encode()).hexdigest()[:10]


def round_order(round_index: int, mode: str, seed: int, models=MODEL_IDS) -> list[str]:
    """Ordem dos modelos na rodada ``round_index`` (1-indexada).

    rotativa: rotação cíclica (r−1) mod 4 → em 11 rodadas cada modelo ocupa
    as posições 1..4 três, três, três e duas vezes.
    aleatoria: permutação com gerador semeado por (seed, r) — reprodutível.
    """
    m = list(models)
    if mode == "rotativa":
        k = (int(round_index) - 1) % len(m)
        return m[k:] + m[:k]
    rng = np.random.default_rng([int(seed), int(round_index)])
    return [m[i] for i in rng.permutation(len(m))]
