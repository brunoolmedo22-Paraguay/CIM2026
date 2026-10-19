# Execução 20261019-143115_4fefd61fcd

Diagnóstico de engenharia do protocolo CIM26 — não constitui conclusão científica sem revisão.

## Reproduzir

```bash
python -m cim26.cli run --config runs/20261019-143115_4fefd61fcd/config.json
python -m cim26.cli analyze runs/20261019-143115_4fefd61fcd   # recalcula métricas sem rodar modelos
```

As entradas devem ter os SHA256 listados em `metadata.json`.

## Configuração

- `months`: ['2019_01', '2019_02', '2019_03', '2019_04', '2019_05', '2019_06']
- `module_id`: SUPSI_MONO_SI_REFERENCE
- `thermal_strategy`: A_tmod_medida
- `delta_t_C`: 3.0
- `g_threshold_Wm2`: 100.0
- `g_max_Wm2`: 1500.0
- `max_gap_min`: 7.5
- `t_module_range_C`: [-40.0, 90.0]
- `repetitions`: 11
- `order_mode`: rotativa
- `seed`: 20261019
- `warmup_samples`: 500
- `execution_mode`: vetorizado
- `scaling_enabled`: True
- `scaling_sizes`: [250, 1000, 4000]
- `tracemalloc_pass`: True
- `sensitivity_enabled`: True
- `sensitivity_delta_t`: [0.0, 2.0, 3.0, 5.0]
- `sensitivity_g_thresholds`: [50.0, 100.0, 200.0]
- `bootstrap_B`: 2000
- `huld_set`: PVGIS_cSi_current
- `label`: verificação Fase 4 (padrão)

## Arquivos

- `config.json` — configuração imutável (dataset, térmica, limiares, rodadas, semente, ordem)
- `module.json` — ficha experimental SUPSI usada (Vmp/Imp/Ns = null, não inventados)
- `input_quality.csv` — TODAS as linhas lidas, com elegibilidade, motivos (R..) e flags informativas (F..)
- `quality_summary.csv` — resumo mensal: n_total, n_elegível, motivos, pares válidos, horas cobertas
- `calibration.json / calibration_residuals.csv` — calibração SDM multiponto (laboratório) e resíduos por ponto
- `params.json` — parâmetros efetivos dos 4 modelos e proveniência
- `predictions.csv` — timestamp, Pm medida, M1…M4, resíduos e status por amostra elegível
- `metrics_energy.csv` — N, RMSE, MAE, MBE, energias e cobertura na interseção comum
- `metrics_daily.csv / metrics_monthly.csv / residual_bins.csv` — erros por dia, mês e faixas G/T
- `bootstrap_ci.csv / bootstrap_paired.csv` — IC95 bootstrap por blocos de dias e diferenças pareadas
- `sensitivity.csv` — sensibilidade a ΔT e ao limiar de irradiância
- `benchmark_runs.csv` — cada execução medida (rodada, posição, modelo, compute_s, memória, convergência, falha)
- `benchmark_summary.csv` — média, mediana, DP, CV, percentis e IC por modelo e lote
- `benchmark_tracemalloc.csv` — passe separado de tracemalloc (não comparável ao RSS)
- `time_ratios.csv / determinism.csv` — razões pareadas por rodada e verificação de determinismo
- `pareto.csv / marginal.csv` — fronteira erro×custo e razões de melhoria marginal
- `statistics.csv` — tabela longa consolidada (dia/mês/faixa/bootstrap)
- `metadata.json / environment_freeze.txt` — SHA256 das entradas, hardware/SO, versões, tempos por etapa, limites
- `figures/` — SVG e PNG para lâminas/LaTeX (regeneráveis a partir dos CSV)

## Limites declarados

- Rodadas repetidas de software não são replicações físicas independentes.
- ΔT célula–módulo = hipótese (Sandia eq. 23), não medida; ver sensitivity.csv.
- M3 usa coeficientes tecnológicos genéricos (PVGIS c-Si CURRENT), não calibrados para o módulo.
- M4 calibrado com 66 medições de laboratório; M2 usa γ medido; assimetrias de parametrização declaradas.
- Mesma POA medida para os 4 modelos; perdas ópticas (AOI, espectro) não modeladas em nenhum.
- Tempos medidos neste PC; não extrapolar para hardware embarcado.
- Energia parcial: somente pares válidos; não é energia semestral completa.
- Resultados de uma execução de verificação são diagnóstico de engenharia, não conclusões publicáveis.
