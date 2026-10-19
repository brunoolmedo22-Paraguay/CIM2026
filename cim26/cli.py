"""Interface de linha de comando do motor CIM26 (sem Streamlit).

  python -m cim26.cli run [--repetitions 11] [--months 2019_01 ...] [--config cfg.json]
  python -m cim26.cli analyze <run_dir>      # recalcula métricas a partir dos arquivos
  python -m cim26.cli calibrate              # calibração SUPSI multiponto (laboratório)
  python -m cim26.cli lab                    # verificações da matriz IEC 61853
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cim26")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config")
    r.add_argument("--run-id")
    r.add_argument("--runs-dir")
    r.add_argument("--repetitions", type=int)
    r.add_argument("--months", nargs="+")
    r.add_argument("--order", choices=["rotativa", "aleatoria"])
    r.add_argument("--seed", type=int)
    r.add_argument("--no-sensitivity", action="store_true")
    r.add_argument("--no-scaling", action="store_true")
    r.add_argument("--label", default=None)
    a = sub.add_parser("analyze")
    a.add_argument("run_dir")
    sub.add_parser("calibrate")
    sub.add_parser("lab")
    args = ap.parse_args(argv)

    if args.cmd == "run":
        from .experiment.config import ExperimentConfig
        from .experiment.runner import run_experiment
        from .paths import RUNS_DIR
        cfg = ExperimentConfig()
        if args.config:
            cfg = ExperimentConfig.from_dict(json.loads(Path(args.config).read_text(encoding="utf-8")))
        kw = {}
        if args.repetitions is not None:
            kw["repetitions"] = args.repetitions
        if args.months:
            kw["months"] = tuple(args.months)
        if args.order:
            kw["order_mode"] = args.order
        if args.seed is not None:
            kw["seed"] = args.seed
        if args.no_sensitivity:
            kw["sensitivity_enabled"] = False
        if args.no_scaling:
            kw["scaling_enabled"] = False
        if args.label is not None:
            kw["label"] = args.label
        cfg = cfg.with_(**kw) if kw else cfg

        def prog(s):
            b = s.get("benchmark") or {}
            extra = f" | {b.get('fase')} r{b.get('rodada', '-')} {b.get('modelo', '')} {b.get('feitos', 0)}/{b.get('total', '?')}" if b else ""
            print(f"[{s['etapa_idx']}/{s['n_etapas']}] {s['etapa']}: {s['mensagem']}{extra}", flush=True)

        rd = run_experiment(cfg, Path(args.runs_dir) if args.runs_dir else RUNS_DIR, run_id=args.run_id,
                            progress=prog, use_lock=True)
        print(f"OK: {rd}")
        return 0
    if args.cmd == "analyze":
        from .experiment.analysis import analyze_run
        out = analyze_run(Path(args.run_dir))
        print(out["metrics_energy"].to_string())
        return 0
    if args.cmd == "calibrate":
        from .calibration.multipoint import calibrate_multipoint
        from .data.supsi_lab import read_iec61853_xlsx, supsi_module_spec
        ref, rep = calibrate_multipoint(read_iec61853_xlsx().long, supsi_module_spec())
        print(json.dumps(ref.to_dict(), indent=2, default=str))
        print(rep.lab_metrics.to_string())
        return 0
    if args.cmd == "lab":
        from .data.supsi_lab import check_lab, load_supsi_module_json, read_iec61853_xlsx
        ok = True
        for c in check_lab(read_iec61853_xlsx(), load_supsi_module_json()):
            print(("OK  " if c["ok"] else "FALHA ") + c["check"], c["detail"])
            ok &= bool(c["ok"])
        return 0 if ok else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
