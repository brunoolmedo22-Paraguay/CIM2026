# 03 — Datos, mapeo, módulo experimental y calibración

## Origen y estructura
- `input/SUPSI/raw/laboratory/IEC61853_1-2.xlsx`: carácter experimental, hoja `61853-1 & 2`.
- `input/SUPSI/raw/field_2019/2019_01.csv` … `2019_06.csv`: mediciones exteriores originales, delimitador `;`, etiquetas `Date; Time; Pm; Voc; Isc; Tbom; Gpoa; Gglob_hor; Gdiff_hor; RH_AIR; AIR_TEMP; WIND_SPEED` (algunas con espacios iniciales).
- `input/SUPSI/derived/lab_IEC61853_matrix_long.csv`: exportado de las 3 matrices del Excel, 22 pares irradiancia–temperatura × 3 magnitudes; columnas `variable`, `irradiance_poa_Wm2`, `temperature_module_C`, `measured_value`, `unit`, `xlsx_row`, `xlsx_col`. **Derivado**, no fuente primaria.
- `input/SUPSI/derived/SUPSI_module_experimental.json`: ficha de datos medidos y campos unknown `null` para Vmp, Imp, Ns, fabricante y modelo. **No inventar** ninguno.
- Report IEA cap 2,4 Anexo 1: `input/references/...pdf`.

## Limpieza científicamente auditable
1. Leer `dd.mm.yyyy HH:MM:SS` explícitamente, preservar fecha/hora original, orden, fuente mensual y número de fila.
2. Convertir columnas a unidades SI/definidas; detectar duplicados timestamp, NaN, Pm<0, Gpoa<0, temperaturas no plausibles. **No promediar ni borrar registros sin contabilizarlo**.
3. Asignar `eligible` y lista de razones por fila; aplicar **misma máscara de validez** a los cuatro modelos (no máscaras por resultado del modelo). Registros nocturnos o Gpoa muy baja: mostrar cobertura; no asignar valores inventados a potencia medida.
4. La selección de umbral de irradiancia es configurable y predefinida ANTES de analizar RMSE (sugerencia principal `Gpoa>=100 W/m²`, sensibilidad 50/200); no eliminar selectivamente grandes errores.
5. Columna `Gpoa` es irradiancia POA medida. `Gglob_hor` es GHI; NO intercambiar. `Tbom` es temperatura posterior, NO Tcell.
6. Monitorear intervalos; los CSV incluyen solo franja de medición, no inventar noche; integración energética solo sobre parejas realmente consecutivas con laguna tolerada <=7.5 min o criterio explícito.
7. Mantener CSV brutos sin cambios. Generar resumen por mes con n_total, n_valid, motivos, cobertura de tiempo; todos los modelos comparten esos índices.

## Extracción laboratorio
Las matrices están en Excel:
- Pmp: filas 9–15 (columnas A:G)
- Isc: filas 19–25
- Voc: filas 29–35
- columnas B,C,D,E representan temperaturas 15,25,50,75°C y A irradiancias 1100→100.
- `32` en combinaciones inválidas es **sentinela de dato ausente**, NO valor de magnitud; verificar con el patrón de posiciones y normas IEC.
- STC (`G=1000,T=25`): Pmp=285.685917... W, Isc=9.486848514... A, Voc=39.714731230... V.
- Contacto identificador posible: `gabi.friesen@supsi.ch` (documentado en Excel). Identidad comercial del módulo no comunicada.

## Dos calibradores para un solo SDM
- **Comercial:** mantener `extract_sdm_params()` original con Voc/Isc/Vmp/Imp/beta/Ns, NO hacerlo depender de SUPSI.
- **SUPSI:** mínimos cuadrados multipunto con 66 observaciones en laboratorio (22 Pmp + 22 Isc + 22 Voc). Los cinco parámetros efectivos usan `a_ref` en lugar de `n` individual. Incluir multiarranques, límites, residuos desglosados, normas de convergencia, métricas de sensibilidad e informe.
- Evitar fuga de información: CSV de campo 2019 nunca se usa para ajustar parámetros con los que se calculan sus RMSE/MAE. Si se desea ajustar con campo en el futuro, retener meses completos para validación temporal posterior.
- El piloto incluido en `reference_implementations/` sirve solo para factibilidad. No hardcodear sus parámetros, no citar sus RMSE como estudio principal, revisar escalado y fiabilidad numérica.
- M1 necesita Pstc; M2 agrega gamma, M3 agrega familia y coeficientes tecnológicos publicados, M4 agrega identificación clásica o multipunto. **Estas asimetrías se declaran en el artículo**.

## Parametrización general de biblioteca
Importar catálogo Canadian Solar desde `legacy_core/config/pv_database.py`; normalizar sus campos sin cambiar valores. Permitir crear/editar/guardar una ficha comercial con origen, unidades y validaciones físicas (0<Pmp<=Voc*Isc, gamma<0 usual salvo excepción explicada, etc.). Mostrar explícitamente datos incompletos y permitir deshabilitar solo modelos inviables. Para artículo no sustituir SUPSI por un Canadian Solar aproximadamente parecido.

## Derivados reproducibles
Tener un importador Python que permita regenerar `lab_IEC61853_matrix_long.csv` desde el Excel original, preservando metadatos de posiciones. No modificar los originales. Si prefieres usar `artifact_tool` durante desarrollo, documentarlo; en la app final se permite `openpyxl` para lectura de Excel sin escribir sobre originales.
