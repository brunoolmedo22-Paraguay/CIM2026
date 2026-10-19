"""Registro do ambiente de execução (hardware, SO, versões, sementes)."""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import time
from importlib import metadata
from pathlib import Path

THREAD_VARS = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def cpu_model() -> str:
    try:
        for line in open("/proc/cpuinfo"):
            if line.lower().startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "não identificado"


def environment_info(project_root: Path | None = None) -> dict:
    info = {"cpu_modelo": cpu_model(), "cpu_logicos": os.cpu_count(), "so": platform.platform(),
            "python": sys.version.split()[0], "implementacao": platform.python_implementation(),
            "threads_env": {k: os.environ.get(k, "não definido") for k in THREAD_VARS}}
    for mod in ("numpy", "scipy", "pandas", "streamlit", "plotly", "matplotlib", "openpyxl", "psutil"):
        try:
            info[f"versao_{mod}"] = metadata.version(mod)
        except metadata.PackageNotFoundError:
            info[f"versao_{mod}"] = "não instalado"
    try:
        import psutil
        info["cpu_fisicos"] = psutil.cpu_count(logical=False)
        info["ram_total_GiB"] = round(psutil.virtual_memory().total / 2**30, 2)
        f = psutil.cpu_freq()
        info["cpu_freq_MHz"] = {"atual": f.current, "min": f.min, "max": f.max} if f else "não medida"
        temps = getattr(psutil, "sensors_temperatures", lambda: {})()
        info["cpu_temperatura"] = {k: [t.current for t in v] for k, v in temps.items()} if temps else "não medida"
    except Exception:
        info["cpu_freq_MHz"] = "não medida"
        info["cpu_temperatura"] = "não medida"
    ci = time.get_clock_info("perf_counter")
    info["relogio"] = {"funcao": "time.perf_counter_ns", "resolucao_s": ci.resolution,
                       "monotonico": ci.monotonic, "implementacao": ci.implementation}
    info["energia_cpu"] = "não medida (sem instrumento)"
    info["git_commit"] = git_commit(project_root) if project_root else "não disponível"
    return info


def git_commit(root: Path) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else "não disponível (sem repositório git)"
    except Exception:
        return "não disponível"


def pip_freeze() -> str:
    pkgs = sorted({f"{d.metadata['Name']}=={d.version}" for d in metadata.distributions() if d.metadata["Name"]},
                  key=str.lower)
    return "\n".join(pkgs) + "\n"
