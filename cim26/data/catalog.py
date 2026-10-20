"""Biblioteca de módulos: catálogo Canadian Solar herdado + ficha SUPSI + módulos do usuário.

O catálogo é lido DIRETAMENTE de ``legacy_core/config/pv_database.py`` por
análise sintática (``ast``), sem executar o arquivo nem copiar valores à mão:
os campos são apenas renomeados (normalização), nunca alterados.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from ..paths import LEGACY_CATALOG, USER_MODULES
from ..pvcore.module import KIND_DATASHEET, KIND_USER, ModuleSpec, validate_module
from .supsi_lab import sha256_file, supsi_module_spec

_FIELD_MAP = {
    "p_nom": "p_stc_W", "v_oc": "v_oc_V", "i_sc": "i_sc_A", "v_mp": "v_mp_V", "i_mp": "i_mp_A",
    "n_cells": "n_cells_series", "alpha_isc_pct": "alpha_isc_pct_C", "beta_voc_pct": "beta_voc_pct_C",
    "gamma_pmax_pct": "gamma_pmax_pct_C", "noct": "noct_C", "length": "length_m", "width": "width_m",
    "manufacturer": "manufacturer", "model": "model", "technology": "technology", "notes": "notes",
}


def _literal(node):
    """literal_eval estendido para chamadas ``dict(k=v, ...)``."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
        return {kw.arg: _literal(kw.value) for kw in node.keywords}
    if isinstance(node, ast.Dict):
        return {_literal(k): _literal(v) for k, v in zip(node.keys, node.values)}
    return ast.literal_eval(node)


def read_legacy_catalog(path: Path = LEGACY_CATALOG) -> dict:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    for node in tree.body:
        target = None
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value = node.target.id, node.value
        elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            target, value = node.targets[0].id, node.value
        if target == "MODULE_DB":
            return _literal(value)
    raise ValueError("MODULE_DB não encontrado no catálogo legado.")


def catalog_modules(path: Path = LEGACY_CATALOG) -> dict[str, ModuleSpec]:
    db = read_legacy_catalog(path)
    digest = sha256_file(path)
    out = {}
    for key, entry in db.items():
        stc = entry["stc"]
        kwargs = {_FIELD_MAP[k]: v for k, v in stc.items() if k in _FIELD_MAP}
        out[key] = ModuleSpec(
            id=key, kind=KIND_DATASHEET, source=f"legacy_core/config/pv_database.py (sha256 {digest[:12]}…)",
            p_stc_meaning="potência nominal de placa (datasheet)", **kwargs,
        )
        if entry.get("sdm"):
            out[key].extra["sdm_published"] = entry["sdm"]
    return out


def _safe_id(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", text.strip()).strip("_") or "modulo"


def user_modules(folder: Path = USER_MODULES) -> dict[str, ModuleSpec]:
    out = {}
    if Path(folder).exists():
        for p in sorted(Path(folder).glob("*.json")):
            try:
                m = ModuleSpec.from_dict(json.loads(p.read_text(encoding="utf-8")))
                out[m.id] = m
            except Exception:  # arquivo corrompido não derruba a biblioteca
                continue
    return out


def save_user_module(m: ModuleSpec, folder: Path = USER_MODULES) -> Path:
    errors = [msg for lvl, msg in validate_module(m) if lvl == "erro"]
    if errors:
        raise ValueError("; ".join(errors))
    m.kind = KIND_USER
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    m.id = _safe_id(m.id)
    path = folder / f"{m.id}.json"
    path.write_text(json.dumps(m.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def library() -> dict[str, ModuleSpec]:
    """Biblioteca completa: SUPSI (ficha experimental) + Canadian Solar + usuário."""
    lib: dict[str, ModuleSpec] = {}
    supsi = supsi_module_spec()
    lib[supsi.id] = supsi
    lib.update(catalog_modules())
    for k, v in user_modules().items():
        if k not in lib:
            lib[k] = v
    return lib
