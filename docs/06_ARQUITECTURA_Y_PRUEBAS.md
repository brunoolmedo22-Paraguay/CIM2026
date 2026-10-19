# 06 — Arquitectura de software, entregas y aceptación

## Stack mínimo
- Python 3.11+ (aceptar versiones compatibles con dependencias y registrar), Streamlit, NumPy, pandas, SciPy, Plotly y/o Matplotlib, pytest/unittest. Streamlit debe funcionar localmente Windows y Linux. `openpyxl` opcional para importación de Excel en app, no Excel como dependencia obligatoria de simulación.
- NO Docker/cloud/GPU/database server/API pago/Redis/Celery ni tecnologías sobrantes. Historial con archivos locales; SQLite **solo si realmente se justifica** por persistencia/concurrencia, no por preferencia estética.
- Dependencias en `requirements.txt` con rangos claros; fijar versión exacta en `pip freeze` de cada experimento.

## Separación obligatoria
Propuesta de paquetes (puede reorganizar manteniendo responsabilidades):
`app.py` UI; `pvcore/` modelos y térmica; `data/` lectura, matriz y catálogo; `calibration/` clásico+SUPSI; `experiment/` motor, sincronización, calidad, métricas; `benchmark/` secuencial+memoria+orden; `statistics/` tests e IC; `report/` exportación y figuras; `tests/` unidades, integración y regresión.

Contrato conceptual: `model.prepare(spec, calibration_source) -> fitted_parameters`, `model.predict(conditions, params) -> p_mpp_W + status`; `conditions` contiene POA/Tback/Tcell/Tamb/vento con procedencia. `ExperimentConfig` inmutable y serializable; `ExperimentRun` persiste y se puede volver a cargar.

## Secuencia esperada de Claude
1. Inspeccionar fuentes; explicar plan y ambigüedades críticas antes de codificar; resolver con los defaults y etiquetas señalados en docs sin pedir confirmación por preferencias visuales.
2. Implementar lector SUPSI, módulo experimental, filtros/flags e inventario de datasheets; demostrar `22x3` matriz y checks.
3. Implementar M1/M2/M3 y tests de fórmula y nomenclatura G/T; trasladar M4 del núcleo legado con método de calibración original y nuevo camino laboratorio (sin alterar legado). Registrar trazabilidad de parámetros.
4. Motor artículo (mismo set timestamps, cálculo estimaciones, energía, errores, 11 rondas secuenciales con rotación y warmup, medición precisa), consolidación 4 secciones.
5. Implementar UI Streamlit de dos modos; navegación y exportación e histórico.
6. Ejecutar tests, demostración con CSV reales, reportar métricas del smoke run como **diagnóstico de ingeniería**; prohibido presentarlas como conclusiones definitivas sin revisión científica.
7. Entregar código ejecutable, instrucciones Windows/Unix, resultados de tests y limitaciones. No añadir features fuera de alcance.

## Criterios de aceptación AUTOMATIZABLES
- Lectura 6 CSV + timestamps dd.mm.yyyy; no borrar originales; Gpoa se mantiene distinto de GHI.
- Excel matriz (o derivado) cuenta 22 Pmp, 22 Isc, 22 Voc; STC coincide con archivo experimental dentro de tolerancia; no tratar 32 sentinela como dato real.
- M1/M2/M3 predicen `Pstc` en G=1000, temperatura=25°C; cero en G=0 (incluye Huld sin log inválido). En temperatura alta, M2 decrece para gamma negativo.
- M4 clásico con módulo Canadian Solar del catálogo y comparativa STC; M4 SUPSI puede calibrar sin Ns, Vmp ni Imp y reporta los supuestos/identificabilidad.
- Modo Modelos y Modo Artigo dan predicción física idéntica para las mismas entradas/parametrización; no dos ecuaciones distintas.
- Cualquier ronda completa con R=11, cuatro modelos: 44 registros de compute y **nunca más de un modelo ejecutándose simultáneamente**; orden cambia por ronda; cada muestra/time stamp es el mismo.
- Si el modelo es determinista, las predicciones de las 11 rondas coinciden; tiempos pueden variar, no «promediar» predicciones para inventar incertidumbre de rendimiento energético.
- Gráficas/tablas de errores deben recalcularse desde `predictions.csv`; el ZIP de export debe reabrirse sin reejecutar modelos.
- Fallos, no convergencia, intersección de muestras y cobertura del dataset visibles sin borrar filas clandestinamente.
- Costo computacional no incluye calibración/lectura/render; se deben registrar por separado; benchmark con muestra creciente y estadística en tablas.
- App Streamlit arranca sin conexión Internet ni archivos externos al proyecto, y usa únicamente lo incluido en paquete.

## Precauciones técnicas
- La memoria RSS se mide por proceso, y diferencia de pico puede ser pequeña/ruidosa; reportar limitaciones. Evitar benchmarks en paralelo y los procesos que compartan caché de modo asimétrico.
- Controles de reproducibilidad: hash SHA256 de input, git commit si disponible, versiones, fuente de coeficientes JRC Huld y temperatura; reportar «no medido» para energía de CPU si no hay instrumento.
- No extrapolar resultados de PC a cumplimiento temporal o consumo de hardware embebido.
- No comparar NRMSE sin especificar denominador; no sumar energía a través de intervalos nocturnos faltantes.
- Una gráfica bonita no sustituye verificación de ecuaciones; testear formulas con cuentas hechas a mano/funciones de referencia.
