# Arquitectura (v2.0 — Streamlit)

## Capas

```
navegador ◀── Streamlit (app.py · st.navigation) ──▶ ui/ ──▶ cim26 (motor) ──▶ runs/<run_id>/ (arquivos)
                 │                                              experimento: processo à parte ──▶ worker do benchmark
                 └─ componentes JS v2 (setTriggerValue) ──▶ Python (st.session_state é a única fonte de verdade)
```

- **`app.py`.** Configura la página, inyecta el tema (`ui/theme.py`), inicializa el estado (`ui/state.py`), arma la navegación con secciones Modelos / Artigo y la barra lateral con el monitor global (`ui/nav.py`), y ejecuta la página.
- **`ui/views/`.**
  - **`simulador`:** modo Modelos.
  - **`dados`, `protocolo`, `resultados`, `historico`:** modo Artigo.
  - **Funciones de página:** cada página es una función `render()` y ninguna contiene física.
- **`ui/services.py`.** Puente hacia el motor, con caché de **visualización** (`st.cache_data` / `st.cache_resource`). El benchmark no pasa nunca por la caché.
- **`ui/components.py`.**
  - **Constructores HTML (`st.html`):** cabecera, chips, franja de protocolo, síntesis, discusión, tarjetas de modelo, anomalías y tablas de ficha.
  - **Componentes `st.components.v2`:** `theme_sync`, `config_tiles`, `model_pills`, `kpis`, `calendar` y `sun_arc`.
- **`ui/charts.py`.** Figuras Plotly con tema claro/oscuro, formato pt-BR y huecos sin unir. El relleno de irradiancia se dibuja por tramos continuos y la I–V usa fotogramas nativos.
- **Experimentos.** `run_store.launch_background` reserva el bloqueo de forma atómica y lanza `python -m cim26.cli run` en otra sesión de proceso. Ese proceso, a su vez, lanza el *worker* aislado del benchmark. El monitor usa `st.fragment(run_every)` y `cancel_run` termina el árbol de procesos.
- **Persistencia.** Es local mientras la app vive. En Cloud el disco es efímero, así que ZIP, CSV, JSON y figuras se exportan y luego se reimportan.

## Mecanismos de Streamlit documentados que se usan

- `st.navigation` / `st.Page`.
- `st.logo`.
- `st.dialog`.
- `st.fragment(run_every)`.
- `st.components.v2.component`.
- `st.context.theme`.
- `[theme.light]` y `[theme.dark]` con sus barras laterales.
- `[[theme.fontFaces]]` + `server.enableStaticServing`.
- `st.dataframe(on_select)`.
- `st.plotly_chart(theme=None, config=…)`.

Los selectores internos se limitan a 4 reglas cosméticas en `ui/theme.py::ST_OVERRIDES`.

## Discusión, anomalías y métricas

Estos componentes no cambiaron respecto de la v1.1 (motor `cim26`):

- **Discusión:** la genera `cim26/report/narrative.py`.
- **Anomalías:** las detecta `cim26/data/anomalies.py`.
- **Métricas porcentuales:** son las de las secciones siguientes.

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
