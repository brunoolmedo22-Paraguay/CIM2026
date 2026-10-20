"""Processo ISOLADO do benchmark computacional (executado como subprocesso).

Protocolo (docs/04): os quatro modelos, um após o outro, R rodadas, ordem
rotativa/aleatória semeada, aquecimento não contabilizado, NUNCA concorrência.
Cada chamada mede apenas ``predict`` sobre arrays pré-processados comuns
(leitura, calibração, preparação, gráficos e exportação ficam fora).
GC: coleta antes de cada chamada e desativado durante a medição (política do timeit).

Uso: python -m cim26.benchmark.worker <diretório_de_trabalho>
"""

from __future__ import annotations

import gc
import hashlib
import json
import sys
import time
import tracemalloc
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

from ..experiment.config import round_order
from ..pvcore import sdm as _sdm
from ..pvcore.models import MODEL_IDS, ModelParams, predict
from ..pvcore.thermal import Conditions
from .envinfo import environment_info
from .memory import RSSMeter


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _sha(p: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(p, dtype=np.float64).tobytes()).hexdigest()[:16]


def measure_call(model_id, cond, params, mode, meter, ref_pred):
    rec = {"modelo": model_id, "n_amostras": len(cond)}
    gc.collect()
    meter.reset_peak()
    rss0 = meter.rss_MiB()
    gc.disable()
    try:
        t0 = time.perf_counter_ns()
        out = predict(model_id, cond, params, mode=mode)
        t1 = time.perf_counter_ns()
        err = ""
    except Exception as exc:  # falha registrada, nunca descartada
        t1 = time.perf_counter_ns(); t0 = t1
        out, err = None, f"{type(exc).__name__}: {exc}"
    finally:
        gc.enable()
    rss1 = meter.rss_MiB()
    peak = meter.peak_MiB(rss0, rss1)
    rec.update(t_inicio_ns=t0, t_fim_ns=t1, compute_ns=t1 - t0, compute_s=(t1 - t0) / 1e9, rss_antes_MiB=rss0, rss_depois_MiB=rss1,
               pico_rss_MiB=peak, pico_rss_delta_MiB=peak - rss0, metodo_memoria=meter.method,
               falha=out is None, erro=err)
    n = len(cond)
    rec["tempo_por_amostra_us"] = rec["compute_s"] / n * 1e6 if n else np.nan
    if out is not None:
        p = out.p_mpp_W
        st = out.status
        rec["n_validas"] = int(np.isfinite(p).sum())
        rec["n_falhas_amostra"] = int((st == _sdm.ST_FAILED).sum())
        rec["n_nao_convergencia"] = int(((st == _sdm.ST_REFINE_NOT_CONVERGED) | (st == _sdm.ST_COARSE_FALLBACK)).sum())
        rec["nfev_total"] = int(out.diagnostics.get("nfev_total", 0))
        rec["pred_sha256_16"] = _sha(p)
        same_nan = np.array_equal(np.isnan(p), np.isnan(ref_pred))
        diff = np.nanmax(np.abs(p - ref_pred)) if np.isfinite(p).any() else np.nan
        rec["max_abs_diff_ref_W"] = float(diff) if same_nan else float("inf")
    return rec


def main(workdir: str) -> int:
    wd = Path(workdir)
    spec = json.loads((wd / "bench_spec.json").read_text(encoding="utf-8"))
    data = np.load(wd / "bench_input.npz")
    cond = Conditions(g_poa_Wm2=data["g_poa_Wm2"], t_module_C=data["t_module_C"], t_cell_C=data["t_cell_C"])
    refs = {m: data[f"ref_{m}"] for m in MODEL_IDS}
    params = {m: ModelParams.from_dict(spec["params"][m]) for m in MODEL_IDS}
    R, mode, seed = int(spec["repetitions"]), spec["order_mode"], int(spec["seed"])
    exec_mode = spec["execution_mode"]
    meter = RSSMeter()
    env = environment_info()
    env["metodo_memoria"] = meter.method
    env["rss_base_MiB"] = meter.rss_MiB()
    (wd / "benchmark_env.json").write_text(json.dumps(env, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    N = len(cond)
    sizes = [N] + [int(s) for s in spec.get("scaling_sizes", []) if 0 < int(s) < N]
    rng = np.random.default_rng([seed, 7])
    perm = rng.permutation(N)
    records = []
    total_calls = len(sizes) * R * len(MODEL_IDS)
    done = 0
    # Aquecimento (não contabilizado): cada modelo uma vez, ordem da rodada 1
    w = min(int(spec["warmup_samples"]), N)
    wcond = cond.subset(slice(0, w))
    for m in round_order(1, mode, seed):
        emit(evt="progress", fase="aquecimento", modelo=m, feitos=0, total=total_calls)
        predict(m, wcond, params[m], mode=exec_mode)
    for bs in sizes:
        idx = np.arange(N) if bs == N else np.sort(perm[:bs])
        c = cond if bs == N else cond.subset(idx)
        exp = "principal" if bs == N else "escala"
        for r in range(1, R + 1):
            order = round_order(r, mode, seed)
            for pos, m in enumerate(order, start=1):
                rec = measure_call(m, c, params[m], exec_mode, meter, refs[m][idx])
                rec.update(experimento=exp, batch_size=bs, rodada=r, posicao=pos, ordem_rodada=">".join(order),
                           modo_execucao=exec_mode, politica_gc="collect antes; desativado durante")
                records.append(rec)
                done += 1
                emit(evt="progress", fase=exp, rodada=r, R=R, modelo=m, posicao=pos, batch=bs,
                     compute_s=rec["compute_s"], feitos=done, total=total_calls)
    cols = ["experimento", "batch_size", "rodada", "posicao", "modelo", "ordem_rodada", "compute_s", "compute_ns", "t_inicio_ns", "t_fim_ns",
            "tempo_por_amostra_us", "n_amostras", "n_validas", "n_falhas_amostra", "n_nao_convergencia", "nfev_total",
            "rss_antes_MiB", "rss_depois_MiB", "pico_rss_MiB", "pico_rss_delta_MiB", "metodo_memoria",
            "max_abs_diff_ref_W", "pred_sha256_16", "falha", "erro", "modo_execucao", "politica_gc"]
    pd.DataFrame(records).reindex(columns=cols).to_csv(wd / "benchmark_runs.csv", index=False)
    if spec.get("tracemalloc_pass", True):
        trows = []
        for m in round_order(1, mode, seed):
            emit(evt="progress", fase="tracemalloc", modelo=m, feitos=done, total=total_calls)
            gc.collect()
            tracemalloc.start()
            tracemalloc.reset_peak()
            t0 = time.perf_counter_ns()
            predict(m, cond, params[m], mode=exec_mode)
            t1 = time.perf_counter_ns()
            cur, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            trows.append({"modelo": m, "batch_size": N, "tracemalloc_pico_MiB": peak / 2**20,
                          "tracemalloc_atual_MiB": cur / 2**20, "tempo_com_tracemalloc_s": (t1 - t0) / 1e9,
                          "nota": "passe separado; só alocações Python; tempo NÃO comparável ao benchmark"})
        pd.DataFrame(trows).to_csv(wd / "benchmark_tracemalloc.csv", index=False)
    emit(evt="done", registros=len(records))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1]))
    except Exception:
        emit(evt="error", traceback=traceback.format_exc())
        sys.exit(1)
