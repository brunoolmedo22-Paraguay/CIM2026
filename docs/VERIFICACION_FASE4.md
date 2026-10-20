# Verificación — v2.0 (Streamlit)

## Pruebas v2.0

- **Resultado global:** `python -m pytest -q` da **59 pruebas aprobadas**.
- **Pruebas nuevas** (`tests/test_streamlit_app.py`):
  - ausencia de servidor HTTP o navegador automático en el código;
  - `app.py` sin `__main__`;
  - las 5 páginas renderizan sin excepciones (`AppTest`, componentes JS incluidos);
  - controles del Simulador y estado con M4 calibrado;
  - `services.simulate` igual al motor;
  - la medida solo se compara con el módulo SUPSI;
  - **predicciones M1–M4 de la ejecución v1.1 reproducidas con tolerancia cero**;
  - bloqueo exclusivo entre sesiones;
  - cancelación que conserva las salidas parciales;
  - archivos de despliegue presentes.
- **Recorrido en navegador (Chromium):**
  - las 5 páginas y las 4 pestañas de Resultados, sin excepciones de Streamlit ni errores de consola de la app;
  - mosaico JS → diálogo → calendario JS dentro del diálogo → Python (estado actualizado);
  - píldora M4 bloqueada → diálogo → «Estimar parâmetros SDM» → «Usar este módulo» → M4 activo con I–V animada;
  - modo oscuro detectado (`data-cim-theme=dark`);
  - vista móvil de 390 px.
- **404 en consola:** los únicos 404 observados son sondeos internos del *frontend* de Streamlit (`/<página>/_stcore/health`) al abrir una URL anidada; no provienen de la app.

# Verificación — v1.1 (motor; vigente en v2.0)

## Pruebas automatizadas

- `python -m pytest -q`: **54 pruebas aprobadas**.
- `python tools/verificar_paquete.py`: OK.
- Pruebas originales del paquete (`tests/test_formulas_reference.py`): aprobadas.

| Área | Pruebas |
|---|---|
| Fórmulas M1–M4, térmica y datos (6 CSV, matriz 22×3, sentinela, GHI≠POA, originales intactos) | `test_models.py`, `test_thermal_and_data.py` |
| El código portado coincide con el legado en los 16 módulos | `test_regression_legacy.py` |
| Calibración clásica y multipunto | `test_calibration.py` |
| 11×4 secuencial, sin solapamiento, rotación y determinismo; recálculo desde archivos; ZIP sin reejecución; modos idénticos | `test_experiment.py` |
| Anomalías físicas (reglas sintéticas y conteos SUPSI); clasificación de evidencia; discusión generada desde archivos | `test_anomalies_narrative.py` |
| API web: activos offline, simulación, GHI rechazado, medida solo con módulo SUPSI, SDM→I–V, calidad, ejecución, serie y ZIP | `test_web.py` |

La interfaz se recorrió además con Chromium sin errores de consola: Simulador con estimación SDM e I–V en arreglo 3×1, Dados, Protocolo y las cuatro pestañas de Resultados.

## Ejecución de verificación `20261019-171936_02d45e13e8` — DIAGNÓSTICO DE INGENIERÍA

**Configuración**

- Datos: 6 meses, N = 15457 muestras en la máscara común, 14921 pares válidos que cubren 1243,4 h.
- Calidad: anomalías solo señaladas (política por defecto).
- Térmica: estrategia A con ΔT = 3 °C (hipótesis).
- Benchmark: 11 rondas rotativas, semilla 20261019.

**Entorno**

- CPU: Intel(R) Xeon(R) Processor @ 2.10GHz, 1 núcleo(s) lógico(s).
- Memoria: método `linux_vmhwm_reset`.

**Calibración SDM:** 6,7 s, contabilizados fuera del benchmark.

### Exactitud y costo

Los porcentajes son relativos a la potencia media observada, 164,2 W.

| Modelo | nRMSE % (IC95 por días) | nMAE % | nMBE % | Error de energía % (IC95) | RMSE W | µs/muestra | No dominado (error×tiempo) |
|---|---|---|---|---|---|---|---|
| M1 | 14,93 [13,79; 16,09] | 10,13 | +6,72 | +6,74 [+5,96; +7,45] | 24,5 | 0.0102 | sí |
| M2 | 11,45 [10,13; 12,78] | 5,56 | -0,59 | -0,66 [-0,91; -0,43] | 18,8 | 0.01769 | sí |
| M3 | 11,54 [10,19; 12,89] | 5,64 | -1,23 | -1,27 [-1,53; -1,02] | 19,0 | 0.02712 | no (M2) |
| M4 | 11,43 [10,11; 12,76] | 5,55 | +0,06 | -0,00 [-0,26; +0,25] | 18,8 | 663 | sí |

### Diferencias pareadas de nRMSE

Bootstrap por días con B = 2000. Las diferencias se expresan en puntos porcentuales (p.p.).

| Comparación | Δ p.p. | IC95 |
|---|---|---|
| M2 − M1 | -3,480 | [-4,095; -2,898] |
| M3 − M1 | -3,392 | [-4,007; -2,799] |
| M4 − M1 | -3,505 | [-4,116; -2,934] |
| M3 − M2 | +0,088 | [+0,057; +0,119] |
| M4 − M2 | -0,024 | [-0,043; -0,006] |
| M4 − M3 | -0,113 | [-0,150; -0,076] |

### Anomalías físicas de medición

Criterios fijados de antemano, usando solo variables medidas.

| Código | Anomalía | Severidad | En todo el conjunto | En la máscara |
|---|---|---|---|---|
| A01 | potência sem irradiância | erro | 0 | 0 (0,00 %) |
| A02 | irradiância sem potência | erro | 0 | 0 (0,00 %) |
| A03 | potência acima do fisicamente plausível | erro | 374 | 374 (2,42 %) |
| A04 | potência muito abaixo do esperado | suspeito | 155 | 155 (1,00 %) |
| A05 | Isc incoerente com Gpoa | suspeito | 1328 | 1328 (8,59 %) |
| A06 | Voc implausível | erro | 12 | 0 (0,00 %) |
| A07 | Tbom incoerente com Tamb | suspeito | 0 | 0 (0,00 %) |
| A08 | salto de temperatura do módulo | suspeito | 2 | 2 (0,01 %) |
| A09 | valor congelado | suspeito | 0 | 0 (0,00 %) |
| T01 | transitório rápido de irradiância | condicao | 673 | 658 (4,26 %) |

La verificación «potencia sin irradiancia» (A01) y su inversa (A02) existen y dan **0 casos** en SUPSI 2019. Las inconsistencias reales del dataset son otras:

- **Isc incoherente con Gpoa** (A05);
- **potencia por encima de lo plausible** (A03), típica de bordes de nube y de desincronización entre el barrido I–V y el piranómetro;
- **transitorios rápidos de G** (T01).

### Sensibilidad a la calidad de los datos

La columna de parcela da la fracción del error cuadrático total que explican las muestras de cada escenario.

| Escenario | % muestras | M1 | M2 | M3 | M4 | Parcela del error cuadrático |
|---|---|---|---|---|---|---|
| todas as amostras elegíveis (máscara principal) | 100,0 % | 14,93 | 11,45 | 11,54 | 11,43 | 100–100 % |
| sem anomalias físicas do tipo «erro» | 97,6 % | 13,86 | 9,58 | 9,59 | 9,64 | 67–84 % |
| sem anomalias «erro» nem «suspeito» | 91,3 % | 10,74 | 4,89 | 4,94 | 4,82 | 17–50 % |
| somente condições estáveis (sem transitório rápido de G) | 95,7 % | 13,54 | 9,46 | 9,52 | 9,44 | 65–78 % |
| somente transitórios rápidos de G | 4,3 % | 32,17 | 31,36 | 31,67 | 31,26 | 22–35 % |
| somente amostras com anomalia «erro» ou «suspeito» | 8,7 % | 51,36 | 50,56 | 50,93 | 50,59 | 50–83 % |

**Lectura técnica, no conclusiva**

- **Exactitud.** M2, M3 y M4 forman un grupo de exactitud práctica equivalente; las diferencias pareadas son menores de 0,5 p.p. M1 queda claramente detrás, con un sesgo positivo que crece con la temperatura del módulo.
- **Costo.** El SDM cuesta del orden de 10⁴–10⁵ veces más por muestra que M1/M2. Este factor varió entre corridas (≈ 56 500× en la v1.0 y ≈ 65 000× aquí) porque el tiempo de M1 está en microsegundos y es ruidoso.
- **Calidad de datos.** Menos del 9 % de las muestras, con anomalías físicas de medición, concentra la mitad o más del error cuadrático. Sin ellas, el nRMSE de M2–M4 baja de ≈ 11,4 % a ≈ 4,8 %. El error dominante, por tanto, es común a todos los modelos y no se debe a su formulación.

## Límites y pendientes

- No hay transposición GHI→POA para planos inclinados; la interfaz la bloquea con una explicación.
- No hay coeficientes Huld verificados para CdTe/CIGS.
- Fuera de Linux no se observa el pico de RSS dentro de la llamada.
- La discusión automática se genera por reglas; los umbrales (0,5 p.p., criterios de anomalía) son convenciones declaradas y requieren revisión científica antes de publicar.
