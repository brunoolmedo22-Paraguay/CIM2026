"""Histórico local de execuções: bloqueio, listagem, reabertura, exportação ZIP e importação.

Reabrir NÃO recalcula modelos e não altera arquivos existentes.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pandas as pd

from ..paths import PROJECT_ROOT, RUNS_DIR

LOCK_NAME = ".execucao_ativa.json"


def _pid_alive(pid: int) -> bool:
    try:
        import psutil
        return psutil.pid_exists(int(pid)) and psutil.Process(int(pid)).status() != "zombie"
    except Exception:
        try:
            os.kill(int(pid), 0)
            return True
        except OSError:
            return False


def active_run(runs_dir: Path = RUNS_DIR) -> dict | None:
    lock = Path(runs_dir) / LOCK_NAME
    if not lock.exists():
        return None
    try:
        info = json.loads(lock.read_text(encoding="utf-8"))
    except Exception:
        return None
    if _pid_alive(info.get("pid", -1)):
        return info
    # bloqueio órfão: marca a execução como interrompida, preservando saídas parciais
    st = Path(runs_dir) / info.get("run_id", "") / "status.json"
    if st.exists():
        s = json.loads(st.read_text(encoding="utf-8"))
        if s.get("estado") == "executando":
            s["estado"] = "interrompido"
            st.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")
    lock.unlink(missing_ok=True)
    return None


def acquire_lock(runs_dir: Path, run_id: str, pid: int | None = None) -> None:
    runs_dir = Path(runs_dir)
    cur = active_run(runs_dir)
    if cur and cur.get("run_id") != run_id:
        raise RuntimeError(f"Já existe um experimento em execução: {cur['run_id']} (pid {cur['pid']}).")
    (runs_dir / LOCK_NAME).write_text(json.dumps({"run_id": run_id, "pid": pid or os.getpid()}), encoding="utf-8")


def release_lock(runs_dir: Path, run_id: str) -> None:
    lock = Path(runs_dir) / LOCK_NAME
    if lock.exists():
        try:
            if json.loads(lock.read_text(encoding="utf-8")).get("run_id") == run_id:
                lock.unlink()
        except Exception:
            lock.unlink(missing_ok=True)


def launch_background(cfg_dict: dict, runs_dir: Path = RUNS_DIR) -> str:
    """Inicia o experimento em processo separado (sobrevive a reruns da UI)."""
    from .config import ExperimentConfig
    from .runner import new_run_id
    cfg = ExperimentConfig.from_dict(cfg_dict)
    cfg.validate()
    runs_dir = Path(runs_dir)
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = new_run_id(cfg)
    rd = runs_dir / run_id
    rd.mkdir(parents=True)
    cfg_path = rd / "config.json"
    cfg_path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    log = open(rd / "orquestrador.log", "w", encoding="utf-8")
    kw = {"start_new_session": True} if os.name != "nt" else {"creationflags": 0x00000200}
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.Popen([sys.executable, "-m", "cim26.cli", "run", "--config", str(cfg_path),
                             "--run-id", run_id, "--runs-dir", str(runs_dir)],
                            cwd=PROJECT_ROOT, stdout=log, stderr=subprocess.STDOUT, env=env, **kw)
    acquire_lock(runs_dir, run_id, pid=proc.pid)
    return run_id


def read_status(run_dir: Path) -> dict:
    p = Path(run_dir) / "status.json"
    if not p.exists():
        return {"estado": "pendente"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"estado": "executando"}


def list_runs(runs_dir: Path = RUNS_DIR) -> pd.DataFrame:
    rows = []
    for d in sorted(Path(runs_dir).glob("*"), reverse=True):
        if not d.is_dir() or not (d / "config.json").exists():
            continue
        cfg = json.loads((d / "config.json").read_text(encoding="utf-8"))
        st = read_status(d)
        row = {"run_id": d.name, "estado": st.get("estado"), "inicio_utc": st.get("inicio_utc"),
               "rotulo": cfg.get("label", ""), "meses": len(cfg.get("months", [])),
               "rodadas": cfg.get("repetitions"), "ordem": cfg.get("order_mode"),
               "termica": cfg.get("thermal_strategy"), "delta_T": cfg.get("delta_t_C"),
               "limiar_G": cfg.get("g_threshold_Wm2"), "modo": cfg.get("execution_mode")}
        me = d / "metrics_energy.csv"
        if me.exists():
            m = pd.read_csv(me).set_index("modelo")
            for k in m.index:
                row[f"RMSE_{k}_W"] = round(float(m.loc[k, "RMSE_W"]), 3)
        rows.append(row)
    return pd.DataFrame(rows)


def load_run(run_dir: Path) -> dict:
    """Carrega todos os CSV/JSON de uma execução (sem recalcular)."""
    run_dir = Path(run_dir)
    out: dict = {"run_dir": run_dir, "status": read_status(run_dir)}
    for p in run_dir.glob("*.csv"):
        out[p.stem] = pd.read_csv(p, low_memory=False, float_precision="round_trip")
    for p in run_dir.glob("*.json"):
        if p.name != "status.json":
            try:
                out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
    if "predictions" in out:
        out["predictions"]["timestamp"] = pd.to_datetime(out["predictions"]["timestamp"])
    return out


def zip_run(run_dir: Path) -> bytes:
    run_dir = Path(run_dir)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(run_dir.rglob("*")):
            if p.is_file():
                z.write(p, Path(run_dir.name) / p.relative_to(run_dir))
    return buf.getvalue()


def import_zip(data: bytes, runs_dir: Path = RUNS_DIR) -> Path:
    """Importa um ZIP exportado (sem sobrescrever execuções existentes)."""
    runs_dir = Path(runs_dir)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        roots = {Path(n).parts[0] for n in names}
        if len(roots) != 1:
            raise ValueError("ZIP inválido: esperado um único diretório de execução.")
        root = roots.pop()
        if any(".." in Path(n).parts for n in names):
            raise ValueError("ZIP inválido (caminho inseguro).")
        if f"{root}/config.json" not in names or f"{root}/predictions.csv" not in names:
            raise ValueError("ZIP sem config.json/predictions.csv.")
        target = runs_dir / root
        if target.exists():
            target = runs_dir / f"{root}_importado"
            if target.exists():
                raise FileExistsError(f"Já existe {target.name}.")
        tmp = runs_dir / f".tmp_{root}"
        shutil.rmtree(tmp, ignore_errors=True)
        z.extractall(tmp)
        shutil.move(str(tmp / root), str(target))
        shutil.rmtree(tmp, ignore_errors=True)
    return target
