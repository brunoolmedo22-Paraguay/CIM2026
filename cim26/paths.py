"""Caminhos do projeto (todos locais; nenhuma dependência de rede)."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_ROOT / "input"
SUPSI_RAW_FIELD = INPUT_DIR / "SUPSI" / "raw" / "field_2019"
SUPSI_RAW_LAB_XLSX = INPUT_DIR / "SUPSI" / "raw" / "laboratory" / "IEC61853_1-2.xlsx"
SUPSI_DERIVED = INPUT_DIR / "SUPSI" / "derived"
SUPSI_LAB_LONG_CSV = SUPSI_DERIVED / "lab_IEC61853_matrix_long.csv"
SUPSI_MODULE_JSON = SUPSI_DERIVED / "SUPSI_module_experimental.json"
LEGACY_DIR = PROJECT_ROOT / "legacy_core"
LEGACY_CATALOG = LEGACY_DIR / "config" / "pv_database.py"
RUNS_DIR = PROJECT_ROOT / "runs"
USER_DATA = PROJECT_ROOT / "user_data"
USER_MODULES = USER_DATA / "modules"
USER_CALIBRATIONS = USER_DATA / "calibrations"


def ensure_dirs() -> None:
    for p in (RUNS_DIR, USER_MODULES, USER_CALIBRATIONS):
        p.mkdir(parents=True, exist_ok=True)
