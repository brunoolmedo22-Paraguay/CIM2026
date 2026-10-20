"""Persistência de identificações SDM com metadados (arquivos JSON locais)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from ..paths import USER_CALIBRATIONS
from ..pvcore.sdm import SDMReference


def _jsonable(obj):
    import numpy as np
    import pandas as pd
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="records")
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def save_calibration(ref: SDMReference, report: dict, module_id: str,
                     folder: Path = USER_CALIBRATIONS) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", module_id)
    path = folder / f"{safe}__{ref.method}__{stamp}.json"
    payload = {"module_id": module_id, "saved_utc": stamp, "sdm_reference": ref.to_dict(),
               "report": _jsonable(report)}
    path.write_text(json.dumps(_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def list_calibrations(module_id: str | None = None, folder: Path = USER_CALIBRATIONS) -> list[dict]:
    out = []
    for p in sorted(Path(folder).glob("*.json"), reverse=True):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if module_id is None or d.get("module_id") == module_id:
            d["_path"] = str(p)
            out.append(d)
    return out


def load_reference(d: dict) -> SDMReference:
    return SDMReference.from_dict(d["sdm_reference"])
