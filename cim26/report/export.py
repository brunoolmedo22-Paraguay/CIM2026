"""README_RUN.md de cada execução (como reproduzir e o que cada arquivo contém)."""

from __future__ import annotations

from pathlib import Path

FILES = {
    "config.json": "configuração imutável (dataset, térmica, limiares, rodadas, semente, ordem)",
    "module.json": "ficha experimental SUPSI usada (Vmp/Imp/Ns = null, não inventados)",
    "input_quality.csv": "TODAS as linhas lidas, com elegibilidade, motivos (R..) e flags informativas (F..)",
    "quality_summary.csv": "resumo mensal: n_total, n_elegível, motivos, pares válidos, horas cobertas",
    "calibration.json / calibration_residuals.csv": "calibração SDM multiponto (laboratório) e resíduos por ponto",
    "params.json": "parâmetros efetivos dos 4 modelos e proveniência",
    "predictions.csv": "timestamp, Pm medida, M1…M4, resíduos e status por amostra elegível",
    "metrics_energy.csv": "N, RMSE, MAE, MBE, energias e cobertura na interseção comum",
    "metrics_daily.csv / metrics_monthly.csv / residual_bins.csv": "erros por dia, mês e faixas G/T",
    "bootstrap_ci.csv / bootstrap_paired.csv": "IC95 bootstrap por blocos de dias e diferenças pareadas",
    "sensitivity.csv": "sensibilidade a ΔT e ao limiar de irradiância",
    "benchmark_runs.csv": "cada execução medida (rodada, posição, modelo, compute_s, memória, convergência, falha)",
    "benchmark_summary.csv": "média, mediana, DP, CV, percentis e IC por modelo e lote",
    "benchmark_tracemalloc.csv": "passe separado de tracemalloc (não comparável ao RSS)",
    "time_ratios.csv / determinism.csv": "razões pareadas por rodada e verificação de determinismo",
    "pareto.csv / marginal.csv": "fronteira erro×custo e razões de melhoria marginal",
    "statistics.csv": "tabela longa consolidada (dia/mês/faixa/bootstrap)",
    "metadata.json / environment_freeze.txt": "SHA256 das entradas, hardware/SO, versões, tempos por etapa, limites",
    "figures/": "SVG e PNG para lâminas/LaTeX (regeneráveis a partir dos CSV)",
}


def write_readme_run(rd: Path, cfg, meta: dict) -> None:
    lines = [f"# Execução {Path(rd).name}", "",
             "Diagnóstico de engenharia do protocolo CIM26 — não constitui conclusão científica sem revisão.", "",
             "## Reproduzir", "", "```bash",
             f"python -m cim26.cli run --config runs/{Path(rd).name}/config.json",
             f"python -m cim26.cli analyze runs/{Path(rd).name}   # recalcula métricas sem rodar modelos",
             "```", "", "As entradas devem ter os SHA256 listados em `metadata.json`.", "",
             "## Configuração", ""]
    for k, v in cfg.to_dict().items():
        if k != "calibration":
            lines.append(f"- `{k}`: {v}")
    lines += ["", "## Arquivos", ""]
    lines += [f"- `{k}` — {v}" for k, v in FILES.items()]
    lines += ["", "## Limites declarados", ""] + [f"- {x}" for x in meta.get("limites", [])]
    Path(rd, "README_RUN.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
