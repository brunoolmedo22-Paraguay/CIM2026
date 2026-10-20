"""Importa o núcleo legado (inalterado) de forma isolada para testes de regressão."""
import importlib
import sys
import types
from contextlib import contextmanager
from pathlib import Path

LEGACY = Path(__file__).resolve().parents[1] / "legacy_core"
_PKGS = ("config", "models", "simulation")


@contextmanager
def legacy():
    saved = {k: sys.modules.pop(k) for k in list(sys.modules) if k.split(".")[0] in _PKGS}
    sys.path.insert(0, str(LEGACY))
    try:
        yield types.SimpleNamespace(
            db=importlib.import_module("config.pv_database"),
            solver=importlib.import_module("simulation.solver"),
            mpp=importlib.import_module("simulation.mpp"),
            mm=importlib.import_module("simulation.multimodel"),
            sd=importlib.import_module("models.single_diode"),
        )
    finally:
        sys.path.remove(str(LEGACY))
        for k in list(sys.modules):
            if k.split(".")[0] in _PKGS:
                del sys.modules[k]
        sys.modules.update(saved)
