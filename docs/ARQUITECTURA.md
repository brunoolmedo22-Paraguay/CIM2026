# Arquitectura (v1.1)

## Capas

```
navegador ──HTTP/JSON──▶ web/server.py ──▶ cim26 (motor)          ──▶ runs/<run_id>/ (archivos)
 web/static (HTML/CSS/JS, Plotly.js local)     │  experimento ──proceso aparte──▶ worker del benchmark
```

- **Interfaz (`web/static`).** SPA sin framework ni paso de compilación, organizada en módulos ES:
  - `main.js`: enrutador y monitor de ejecución;
  - `ui.js`: API, formato pt-BR, panel lateral, contadores y tema Plotly;
  - `modelos.js`: Simulador;
  - `artigo.js`: Dados, Protocolo, Resultados e Histórico.

  No contiene física.
- **Servidor (`web/server.py`).** Usa `ThreadingHTTPServer` de la biblioteca estándar y escucha solo en 127.0.0.1. Expone una API JSON fina sobre el motor y sirve `plotly.min.js` desde el paquete Python `plotly`, sin CDN.
- **Discusión (`cim26/report/narrative.py`).** Reglas deterministas sobre los CSV de la ejecución:
  - la redacción de cada comparación depende de la diferencia **pareada** de nRMSE (IC95 por bloques de días) y de un umbral práctico declarado de 0,5 p.p.;
  - las hipótesis causales se rotulan como tales.

  Genera `narrative.json` y `DISCUSSAO.md` y se puede regenerar con `cli analyze`.
- **Anomalías (`cim26/data/anomalies.py`).** A01–A09 (error o sospechoso) y T01 (condición de transitorio). Solo usan variables medidas.

  La exclusión depende de la política del protocolo, y `quality_sensitivity.csv` cuantifica siempre su efecto y su parcela del error cuadrático.

## Métricas porcentuales

Las métricas principales son nRMSE, nMAE y nMBE como % de la potencia media observada en la intersección común, junto con el error de energía en %. Se reporta además nRMSE/Pstc.

El bootstrap por días entrega un IC95 para cada métrica en % y las diferencias pareadas en puntos porcentuales.

## Contratos

- `pvcore.models.prepare(model_id, ModuleSpec, SDMReference|None) -> ModelParams` y
  `predict(model_id, Conditions, ModelParams, mode) -> ModelOutput(p_mpp_W, status, diagnostics)`.
  La salida es siempre por módulo. `scale_to_array` (Ns·Np) solo se usa en el modo Modelos.
- `pvcore.thermal.Conditions` contiene `g_poa_Wm2`, `t_module_C`, `t_cell_C`, `t_amb_C` y `wind_ms`, cada uno con
  su procedencia. `build_conditions` es la única vía por la que ambos modos obtienen temperaturas.
- `ExperimentConfig` es inmutable y serializable (`config.json`). `run_store.load_run` reabre una ejecución sin
  recalcular.
- El modo Modelos (`cim26/simulate.py`) y el modo Artigo (`experiment/runner.py`) llaman al mismo `predict`. La
  prueba `test_modelos_and_artigo_identical` exige igualdad bit a bit.

## Decisiones de ingeniería

| Decisión | Motivo |
|---|---|
| Experimento en un proceso aparte (`cli run`) lanzado por la UI | Un rerun de Streamlit no lo interrumpe ni lo duplica. Un archivo de bloqueo con PID impide la doble ejecución y un PID muerto marca la ejecución como «interrompido». |
| Benchmark en un *worker* aislado con BLAS a 1 hilo | Línea base RSS limpia sin pandas ni Streamlit cargados. No hay concurrencia: las marcas `t_inicio_ns`/`t_fim_ns` prueban intervalos disjuntos. |
| RAM pico por llamada mediante reinicio de VmHWM (Linux) | Pico real sin hilos muestreadores que perturben el tiempo. tracemalloc va en un pase separado y no se equipara con RSS. |
| Modos de ejecución `vetorizado` y `escalar` | En modo escalar, M1–M3 se llaman muestra a muestra con la misma función física. Cada modo es un experimento separado y nunca se mezclan. |
| Lectura de CSV con `float_precision="round_trip"` | Las métricas recalculadas desde archivos coinciden exactamente. |
| Catálogo leído del legado mediante `ast` | No se copian valores a mano y el código legado no se ejecuta. |
| Figuras de exportación en matplotlib (Agg) | SVG/PNG sin navegador ni red. Plotly se usa solo en la UI interactiva. |
| Paquete `cim26/stats` en vez de `statistics` | Evita la sombra con el módulo estándar `statistics`. |

## Códigos de estado por muestra

| Código | Significado |
|---|---|
| 0 | ok |
| 1 | G = 0 → P = 0 por definición |
| 2 | Fórmula negativa recortada a 0 |
| 3 | Extrapolación logarítmica de Huld señalada (G < 50 W/m²) |
| 4 | Refinamiento del MPP sin convergencia declarada |
| 5 | Fallo numérico (NaN) |
| 6 | El refinamiento empeoró el resultado y se conservó el barrido (comportamiento del legado) |

## Relación con la propuesta de paquetes de `docs/06`

| Propuesto en `docs/06` | Implementado como |
|---|---|
| `pvcore/` | `cim26/pvcore` |
| `data/` | `cim26/data` |
| `calibration/` | `cim26/calibration` |
| `experiment/` | `cim26/experiment` |
| `benchmark/` | `cim26/benchmark` |
| `statistics/` | `cim26/stats` |
| `report/` | `cim26/report` |
