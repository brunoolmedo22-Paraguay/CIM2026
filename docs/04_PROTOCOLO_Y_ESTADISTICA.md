# 04 — Protocolo experimental, benchmark secuencial y estadísticas

## Diseño por bloques
A — Validez energética: para los 4 modelos misma serie `Gpoa`, temperaturas según convención, `Pm` medida, un módulo, sin pérdidas de inversor, mismos timestamps elegibles. Reportar RMSE/MAE/MBE, error relativo normalizado (denominador declarado), energía observada vs predicha en pares válidos, residuales por rango G/T y por día/mes.

B — Benchmark computacional: cuatro modelos **uno detrás de otro**, 11 rondas predeterminadas, configurar 3…101 (permitir personalizar en número entero 3…101). El orden se rota entre rondas (o aleatoriza con semilla fija anotada). Cada llamada mide solo evaluación física sobre un arreglo *preprocesado* común, nunca importación Excel/CSV, carga de app, preparación de fichas, entrenamiento, render o exportación. Calentar previamente cada modelo sin contabilizar. **44 ejecuciones medidas para 4 modelos×11**, más calentamientos excluidos. Cada ronda=los 4 modelos exactamente una vez, sin concurrencia. Comparar también múltiples tamaños de lotes si coste razonable.

C — Compromiso error-coste: scatter error vs mediana tiempo por registro, error vs memoria, análisis de modelos dominados (frontera de Pareto) con metodología declarada, razón de mejora marginal con denominador y sentido claramente definidos, sensibilidad térmica y mapeo de requisitos de parametrización. Jamás declarar «superioridad» general sin evidencia independiente.

D — Estadística: 
- Por modelo, sobre 11 tiempos individuales: media, mediana, SD muestral (ddof=1), CV cuando media>0, mínimo, máximo, percentiles 5/25/75/95, boxplots y tendencia entre rondas; registrar cada observación y orden, incluido fallo.
- IC95 de tiempos si resulta apropiado: método bootstrap a nivel ronda/pareado o método robusto justificado. Once rondas pueden no ser suficientes para intervalos estables; tener semilla y advertencia de limitaciones/autocorrelación; no extrapolar «verdad» estadística.
- Para error energético: RMSE/MAE/MBE por día y global; distribución por condición, variación mes-a-mes; intervalos y comparación **pareada por bloque temporal (día)** si hay días suficientes. Remuestrear días completos (bootstrap de bloques), **no** tratar muestras de 5 min como independientes.
- Los 11 pasos de un modelo determinista NO significan 11 experimentos físicos independientes: validar que sus salidas energéticas coincidan dentro de tolerancia, no promediar para fingir replicación de laboratorio.
- Pruebas de comparación opcionales solo con hipótesis, supuestos y multiplicidad documentados. Más importante mostrar tamaños del efecto + intervalos que producir p-valores decorativos.

## Mediciones concretas
- Reloj monotónico alta precisión (`time.perf_counter_ns`); muestras muy rápidas deben cronometrarse en lotes de igual tamaño y dividir entre N, no una sola evaluación de microsegundos.
- Medir tiempo wall-clock **por ejecución** y tiempo por muestra `total/len(input)`; comparar vectorización vs escalar en experimentos separados, nunca mezclar.
- RAM: memoria residente pico del **proceso aislado** (RSS), reportar valor absoluto y delta respecto al baseline; también `tracemalloc` si interesa (solo asignaciones Python), **no equipararlos**. Si se usan subprocesos, un modelo por vez; dar a cada uno mismo política de warmup, carga y reutilización. Tener en cuenta sobrecarga del sampler, registrar precisión/intervalo.
- Registrar fallos, código de salida, número de predicciones válidas, veces que solver no convergió, diferencia contra referencia algorítmica; incluir fracasos en el reporte y no seleccionar solo las corridas favorables.
- Guardar nombre CPU/hilos, RAM, OS, versión Python/NumPy/SciPy/pandas, proceso aislado, temperatura/frecuencia si son accesibles (si no, «no medida»), semilla y hash de archivos.
- Discriminar tiempos `calibration_s`, `prepare_s`, `compute_s`, `postprocess_s` sin mezclar en el headline «tiempo del modelo».
- No asegurar «igual poder de CPU» solo porque sea serial; se controlan concurrencia, orden, entorno y dispersión observada.

## Reglas sobre selección y sesgo
- Congelar criterios antes de observar cuál modelo gana.
- Fuera de dominio no se omite de forma silenciosa; reportar cobertura y motivos. Si un modelo no puede producir determinada predicción, comparaciones pareadas sobre **intersección fija** y reportar también cobertura por modelo.
- Cualquier cambio de tolerancias o parametrización se registra como **nuevo experimento**, no se sobreescribe el previo.
- No optimizar el SDM usando resultados del campo de validación. Si se decide comparar varios solvers, hacerlo posteriormente en un experimento dedicado y etiquetar distinto del cotejo entre modelos.

## Artefactos mínimos exportados para cada corrida
`run_id/`:
- `config.json` (dataset, modelo, parametros, termica, umbrales, rondas, semilla, hilos, versiones)
- `input_quality.csv` (todas las filas, elegibilidad y motivo)
- `predictions.csv` (timestamp, Pm medida, M1…M4, residuales)
- `metrics_energy.csv` (N, RMSE, MAE, MBE, Eobservada, Eestimadas, cobertura, unidad)
- `benchmark_runs.csv` (ronda, posición, modelo, `compute_s`, tiempo/muestra, memoria, convergencia, fallo)
- `benchmark_summary.csv` (media, mediana, sd, CV, cuantiles, IC si corresponde)
- `statistics.csv` (errores por día/mes/bins e incertidumbres)
- `metadata.json` (SHA256 inputs, commit/versiones, hardware/OS, calibración, límites)
- `figures/` (SVG y PNG para láminas/LaTeX)
- `README_RUN.md` (cómo reproducir el experimento)
La interfaz debe poder reabrir `run_id` sin recalcular y sin alterar histórico.
