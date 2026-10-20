# 01 — Alcance científico y prioridades

## Propósito
Evaluar el compromiso entre exactitud de predicción de potencia máxima y energía FV DC, costo de cálculo y robustez de implementación, utilizando condiciones equivalentes y referencia experimental independiente.

## Alcance cerrado v1
- **4 modelos, exactamente**: M1 proporcional; M2 térmico/PVWatts; M3 Huld/PVGIS; M4 SDM.
- **2 modos:** Modelos (libre, módulo comercial, serie/paralelo) y Artículo (ensayo reproducible sobre SUPSI).
- **4 paneles de resultados en Artículo:** I Energética, II Computacional, III Compromiso ciencia/costo, IV Estadística/repetibilidad.
- **11 repeticiones por modelo por defecto**, 3–101 configurables; evaluación estrictamente secuencial y orden rotativo o aleatorizado de semilla conocida.
- Exportación reproducible de datos, resultados, parámetros, entorno y figuras SVG/PNG, además de CSV/JSON.
- Prioridad absoluta: motor científico correcto antes de estética; Claude tiene total libertad visual razonable.

## Exclusiones explícitas
No DDM; no IEC 61853 como uno de los 4 modelos; no SAPM; no modos eólicos, térmicos, PEMFC, baterías ni híbridos; no MPPT P&O ni convertidores; no inferencias sobre microcontrolador ensayado; no entrenamiento automático con validación; no «ganador» universal.

## Preguntas de investigación
1. ¿Cuál es la distribución del error independiente (RMSE/MAE/MBE) según modelo y condiciones meteorológicas?
2. ¿Cómo cambian tiempo, memoria, fallos y variabilidad entre 11 rondas idénticas?
3. ¿Qué modelos no están dominados simultáneamente en error y coste computacional? ¿Cómo cambia esto para distintos tamaños de lote?
4. ¿Qué papel juega el nivel de datos requeridos para calibrar cada modelo frente al aumento de su complejidad matemática?

## Los cuatro modelos deben admitir datasheets comerciales
En Modo Modelos, la biblioteca Canadian Solar heredada debe seguir funcionando; M3 usa coeficientes de tecnología PVGIS que NO son coeficientes manufacturer-specific; M4 requiere parámetros SDM calibrados por método clásico cuando el datasheet contiene Voc/Isc/Vmp/Imp/Ns/beta. Si falta un parámetro: estado «no disponible + motivo», NUNCA inventar ni sustituir silenciosamente por otro módulo.

## Concordancia con artículo
Cada gráfica publicada debe poder rehacerse desde un directorio de ejecución exportado; etiquetar laboratorio de calibración, pruebas de campo, entorno de ejecución y supuestos térmicos. Los resultados exploratorios previos NO deben aparecer como resultados validados del artículo.
