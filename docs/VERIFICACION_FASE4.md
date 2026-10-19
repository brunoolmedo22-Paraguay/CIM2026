# Verificación — Fase 4

## Pruebas automatizadas

`python -m pytest -q` da **44 pruebas aprobadas**. `python tools/verificar_paquete.py` responde OK, y las 3 pruebas
originales del paquete (`tests/test_formulas_reference.py`) también pasan.

| Criterio de aceptación (`docs/06`) | Prueba |
|---|---|
| Lectura de 6 CSV con timestamps dd.mm.yyyy, originales sin cambios, Gpoa ≠ GHI | `test_six_csv_timestamps_and_poa_vs_ghi`, `test_raw_inputs_unchanged` (SHA256 = manifiesto), `test_ghi_is_never_renamed_poa` |
| Matriz 22 Pmp + 22 Isc + 22 Voc, STC = ficha, 32 no se trata como dato | `test_lab_matrix_and_sentinel` (además, el derivado regenerado es byte a byte idéntico) |
| M1/M2/M3 dan Pstc en STC y 0 con G=0 (Huld sin log inválido); M2 decrece con T | `test_stc_gives_pstc`, `test_zero_irradiance_no_log_warning`, `test_m2_hand_calculation_and_decreasing`, `test_huld_hand_and_reference_impl` |
| M4 clásico con Canadian Solar y STC; M4 SUPSI sin Ns/Vmp/Imp con supuestos e identificabilidad | `test_canadian_catalog_all_models_with_classical_sdm`, `test_multipoint_without_ns_vmp_imp`, `test_classical_refuses_incomplete_datasheet` |
| Código portado = legado (16 módulos, MPP, M1, M2≡NOCT+eficiencia, SDM de arreglo) | `test_regression_legacy.py` (rtol 1e-9 a 1e-14) |
| Modelos y Artigo dan predicción idéntica | `test_modelos_and_artigo_identical` (igualdad bit a bit) |
| R=11 × 4 = 44 registros, nunca simultáneos, orden cambia por ronda, mismas muestras, determinismo | `test_worker_11x4_sequential_isolated`, `test_round_order_rotation_and_random` |
| Errores recalculables desde `predictions.csv`; ZIP reabre sin reejecutar | `test_metrics_recomputed_from_predictions`, `test_zip_roundtrip_without_rerun` (llamar a `predict` provoca fallo) |
| Ninguna fila borrada; cobertura visible | `test_quality_keeps_all_rows_and_common_pairs`, `test_run_artifacts` |
| Calibración, lectura y render separados del costo | `test_run_artifacts` (`metadata.json → tempos_por_etapa_s`) |
| La app arranca sin red y usa solo el paquete | `test_app_smoke.py` (AppTest de ambos modos, botón SDM y las 3 áreas de Artigo) |

## Ejecución de verificación `20261019-143115_4fefd61fcd` — DIAGNÓSTICO DE INGENIERÍA

**Configuración**

- Datos: 6 meses, 18 705 filas leídas, de las cuales 15 457 son elegibles (Gpoa ≥ 100 W/m²).
- Integración: 14 921 pares válidos, que cubren 1 243,4 h.
- Térmica: estrategia A con ΔT = 3 °C (hipótesis).
- Benchmark: 11 rondas rotativas, semilla 20261019, modo vectorizado.

**Entorno**

- CPU: Intel(R) Xeon(R) Processor @ 2.80GHz, 1 núcleo(s) lógico(s).
- Memoria: método `linux_vmhwm_reset`.
- Hilos BLAS: 1.
- Python 3.12.3, NumPy 2.4.4, SciPy 1.17.1.

**Registros del benchmark**

- 176 registros: 44 del lote principal y 132 de escalado (250, 1000 y 4000 muestras).
- 0 fallos y 0 no convergencias.
- Predicciones idénticas entre las 11 rondas, con una diferencia máxima frente a la referencia de 0 W.

**Tiempos por etapa**, fuera del costo del modelo: calibración 10.6 s, lectura 0.50 s, preparación 0.005 s, figuras 5.1 s.

| Modelo | RMSE [W] (IC95, bloques por día) | MAE [W] | MBE [W] | Error de energía [%] (IC95) | Mediana [µs/muestra] | CV tiempo [%] | Pico ΔRSS [MiB] | No dominado (error×tiempo) |
|---|---|---|---|---|---|---|---|---|
| M1 | 24.52 [22.97; 26.25] | 16.63 | +11.03 | +6.74 [+5.96; +7.45] | 0.01256 | 9.6 | 0.000 | sí |
| M2 | 18.81 [16.81; 20.95] | 9.12 | -0.97 | -0.66 [-0.91; -0.43] | 0.02148 | 5.1 | 0.000 | sí |
| M3 | 18.95 [16.98; 21.11] | 9.26 | -2.01 | -1.27 [-1.53; -1.02] | 0.03876 | 10.3 | 0.004 | no (M2) |
| M4 | 18.77 [16.80; 20.91] | 9.12 | +0.10 | -0.00 [-0.26; +0.25] | 709.5 | 3.9 | 2.844 | sí |

Diferencias pareadas de RMSE (bootstrap por días, B = 2000):

| Comparación | ΔRMSE [W] | IC95 |
|---|---|---|
| M2 − M1 | -5.714 | [-6.753; -4.740] |
| M3 − M1 | -5.569 | [-6.634; -4.592] |
| M4 − M1 | -5.754 | [-6.785; -4.803] |
| M3 − M2 | +0.145 | [+0.097; +0.190] |
| M4 − M2 | -0.040 | [-0.071; -0.010] |
| M4 − M3 | -0.185 | [-0.239; -0.129] |

**Lectura técnica, no conclusiva**

- **M1 frente al resto.** M1 sobrestima (MBE ≈ +11 W) y su sesgo crece con G y con la temperatura del módulo. M2, M3 y M4 quedan en un RMSE parecido, entre 18,8 y 19,0 W, con intervalos individuales solapados.
- **Diferencias pareadas.** Las pareadas entre M2, M3 y M4 son pequeñas, de décimas de W, pero sus intervalos no incluyen 0 en varios casos. Los IC no pareados son mucho más anchos que esas diferencias, así que el criterio de «dominancia robusta» (IC sin solapamiento) es conservador y no se cumple en ningún caso.
- **Energía.** M4 obtiene el menor error de energía en esta muestra.
- **Costo.** El SDM cuesta del orden de 10⁴ veces más por muestra que M1 y M2.
- **Error común.** Existe un componente común de error de ≈ 18 W en todos los modelos. Hipótesis a investigar: desfase entre el barrido I–V y la irradiancia en nubosidad variable, y efectos ópticos o espectrales no modelados.

Nada de lo anterior es una conclusión publicable sin revisión científica.

## Pendiente / fuera de alcance de esta versión

- La transposición GHI→POA para planos inclinados no está implementada; se bloquea con explicación.
- No hay coeficientes Huld verificados para CdTe/CIGS en el paquete; M3 queda deshabilitado con su motivo.
- En Windows y macOS no se observa el pico de RSS dentro de la llamada; se registra RSS antes y después y se declara el método.
