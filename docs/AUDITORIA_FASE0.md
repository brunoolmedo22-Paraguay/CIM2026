# Auditoría — Fase 0

Fuentes revisadas: `README_INICIO.md`, `PROMPT_PARA_CLAUDE.md`, `docs/01–06`, `LEGACY_UI_CALIBRATION_NOTES.md`,
`legacy_core/` completo, `reference_implementations/`, el Excel IEC 61853, los 6 CSV de campo y el Anexo 1 del
informe IEA PVPS T13-20:2020 (pp. 99, 164–165). El verificador del paquete y sus 3 pruebas pasaban al iniciar.

## Hallazgos en las fuentes (documentados, no corregidos)

1. **El «32» del Excel no es un número.** Las 18 celdas sin medición (6 por matriz) son cadenas compartidas
   (`t="s"`) con `<v>32</v>`, un índice a `sharedStrings`, cuyo elemento 32 es una cadena vacía. Un lector XML
   ingenuo vería «32» y openpyxl devuelve `''`. El importador trata como ausente toda celda no numérica y guarda
   la auditoría XML (`calibration.json → lab_sentinel_audit`).
2. **Etiqueta de unidad errónea.** La tabla de Voc dice `Voc[A]` (celda B27). Se documenta y no se cambia.
3. **Incertidumbres en el Excel.** La fila 10 (I–K) contiene las incertidumbres relativas (k=2) de α, β y δ, y
   la columna F la incertidumbre de cada fila de irradiancia. Se usan solo para informar si el residuo de
   calibración cae dentro de U(k=2).
4. **La fórmula Faiman queda validada con los propios datos:** 800/(29,84 + 3,44·1) + 20 = 44,04 °C, que coincide
   con el NMOT del Excel. Esto confirma la forma `Tmod = Tamb + G/(U0 + U1·v)` y sus unidades. La ecuación (5) del
   PDF aparece truncada en el texto extraído.
5. **Campo.** Hay 18 705 filas, todas a intervalos intradiarios exactos de 5 min y solo en horario diurno. Los
   huecos son literales `NaN` en la fuente: 638 en Pm/Voc/Isc, 206 en Gpoa, 204 en Tbom y 919 en Tamb/viento. No hay
   timestamps duplicados ni faltantes dentro del día.
6. **Voc anómalos.** Hay valores como 2,8 V o 61,6 V frente a Voc_STC = 39,7 V. Quedan como bandera informativa F01
   y no excluyen filas, para no seleccionar muestras según el resultado.
7. **Zona horaria.** No se declara en los CSV. No afecta a los modelos porque no se usa posición solar.

## Hallazgos en el código heredado

- `extract_sdm_params` converge en los 16 Canadian Solar. Los valores de n resultan entre 0,93 y 0,98, un parámetro
  efectivo de módulo que no se marca como error.
- `multimodel.py` impone una ventana de 120 min. `irradiance_model.py` rellena huecos con G = 0 y trata GHI como G.
  Nada de esto se hereda: las lagunas quedan como NaN y GHI solo se acepta como POA si el módulo es horizontal.
- El modelo NOCT + eficiencia del legado (`η·G·A`) es algebraicamente idéntico a PVWatts (`Pstc·G/1000·[1+γΔT]`), así
  que no se cuenta como modelo distinto. Hay una prueba de regresión para esta equivalencia.
- En el catálogo, Vmp·Imp difiere ligeramente de la potencia de placa; por ejemplo, 260,22 W frente a 260 W.
  M1–M3 usan la potencia de placa, mientras que el SDM clásico reproduce Vmp·Imp.

## Hallazgos de la calibración multipunto (diagnóstico)

- Los 8 arranques convergen al mismo óptimo, con una dispersión del orden de 1e-7. La condición del Jacobiano es ≈ 248 y la correlación log I0–a_ref es de 0,98, una compensación esperable. log10 Rsh es el parámetro peor determinado.
- En STC el modelo predice 283,6 W frente a 285,7 W medidos.
- Los coeficientes implícitos del SDM ajustado difieren de los medidos. β_Voc sale en −0,300 %/°C frente a −0,285, y γ en −0,379 %/°C frente a −0,405. Es una limitación de forma de la traslación De Soto con Eg fijo. M2 recibe γ medido directamente, así que la asimetría se declara.
- El piloto `piloto_sdm_resultado_NO_VALIDADO.json` no se usa. El calibrador nuevo recalcula su resultado de forma independiente y coincide hasta ~1e-8.

## Decisiones tomadas con los valores por defecto documentados

- Experimento principal con la estrategia A: Tbom medida, Tcell = Tbom + G/1000·3 °C para M2 y M4, y Tmod = Tbom para Huld.
- Umbral Gpoa ≥ 100 W/m², con sensibilidad a 50 y 200 W/m².
- Integración de energía solo en pares con Δt ≤ 7,5 min dentro del mismo día.
- 11 rondas con rotación cíclica, semilla 20261019, calentamiento de 500 muestras no contabilizado y GC desactivado durante cada medición.
