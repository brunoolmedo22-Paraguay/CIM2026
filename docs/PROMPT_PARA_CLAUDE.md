# PROMPT MAESTRO — entregar completo a Claude Pro con este ZIP adjunto

Claude, actúa como **desarrollador científico principal, ingeniero de software Python/Streamlit y revisor numérico** para el proyecto de investigación fotovoltaica CIM26. Te adjunto `CIM26_CLAUDE_HANDOFF_v1.0.zip`. Trátalo como **única fuente de entradas y contrato técnico** de esta tarea; úsalo íntegramente, no inventes datasets ni parámetros de fabricante.

**MISIÓN:** desarrollar desde cero una nueva aplicación **Python + Streamlit** con dos modos: «Modelos» (herramienta general de simulación y datasheets con arranjo serie/paralelo) y «Artigo» (laboratorio de validación SUPSI y benchmarking experimental), reutilizando las formulaciones/solvers Python herederos incluidas, completando M3 Huld/PVGIS y la calibración multipunto SUPSI del SDM. M1 irradiancia, M2 térmico/PVWatts, M3 Huld/PVGIS, M4 SDM; NO añadir DDM ni IEC 61853 como quinto modelo, ni eólica, térmica, baterías, hidrógeno o MPPT. **Libertad creativa total para el diseño visual**: quiero interfaz profesional, contemporánea, legible y poderosa, pero no sacrifiques exactitud por decoración.

## ORDEN DE TRABAJO OBLIGATORIO

**FASE 0 — Auditoría:** descomprime ZIP, lee `README_INICIO.md` y TODOS los documentos numerados `docs/01...06`, examina `legacy_core` y `reference_implementations`, el catálogo Canadian Solar, el Excel y los CSV SUPSI, y `PROMPT_PARA_CLAUDE.md`. Expón brevemente tu entendimiento y el plan de archivos nuevos; no escribas todavía UI. Usa los requisitos documentados para resolver decisiones obvias. Si descubres errores o inconsistencias de fuentes, documenta, no silenciosamente «corrijas» datos.

**FASE 1 — Motor científico:** implementa parser de SUPSI, datasheets de Canadian Solar y ficha experimental; módulo de calidad/columnas/intervalos; M1–M4 con interfaz común y verificación de unidades. Distingue estrictamente Gpoa vs GHI, Tmod/Tback vs Tcell. **Usa `Gpoa` medida para artículo**. Para Modo Modelos, no renombres GHI como POA. SDM: conservar calibrador clásico original y añadir calibración SUPSI multipunto (laboratorio: 22×3 observaciones), parámetros efectivos `a_ref` sin inventar Ns/Vmp/Imp. No ajustar con CSV de campo que servirán de validación. Reportar límites y validación de calibración.

**FASE 2 — Experimentos:** calcular 4 estimaciones sobre mismos timestamps elegibles, RMSE/MAE/MBE y energía solo sobre intervalos válidos; plan de temperatura principal medido Tbom con conversión explícita a Tcell para M2/M4 y Tmod para Huld. **Once rondas por defecto; nunca en paralelo**. Cada ronda ejecuta los cuatro modelos uno detrás del otro, con orden rotativo y calentamiento no contado. Guardar 44 registros crudos con tiempo/memoria/fallos, intervalos y contexto; separar calibración, lectura, cómputo y gráficas. Métricas estadísticas media/mediana/std/CV/percentiles/IC con límites reconocidos y bootstrap energético por días, frontera Pareto error×tiempo, error×memoria.

**FASE 3 — Interfaz Streamlit:** Modo Modelos con catálogo/módulo nuevo, configuración Ns/Np, meteorología y resultados exportables, botón SDM «Estimar parâmetros». Modo Artigo: pantalla dataset+variables medidas+filtrado+config rondas+botón «Executar experimento científico», progreso y **4 bloques de resultados**: Energia, Computacional, Análise integrada, Estatística. Tabla y gráficos reales interactivos, estado y exportación de experimentos, historial local con posibilidad de reabrir resultados. Mantener exactamente el mismo código físico para ambas modalidades. Visibilidad de procedencia, estado y límites. Puedes crear diseño visual libremente; idioma UI portugués brasileño.

**FASE 4 — Verificación y entrega:** pruebas unitarias, integración, regresión sobre catálogo, smoke test de CSV reales y test 11×4 secuencial; corregir todo antes de dar por finalizado. Entrega el proyecto Streamlit ejecutable en ZIP, README, requirements y resultados de pruebas. Una corrida piloto NO significa validación/publicación; jamás inventar desempeño ni afirmar mejor modelo sin ensayo verificado.

## REGLAS NO NEGOCIABLES

- Respeta las fórmulas/coeficientes y orígenes descritos en `docs/02_FORMULACIONES.md`, con PVGIS cSi CURRENT y modo térmico documentado. M2 PVWatts y el modelo NOCT original no se cuentan como dos modelos físicos distintos.
- Los 6 CSV originales de 2019 y la caracterización XLSX son fuentes experimentales. El campo `32` en tablas de laboratorio es sentinela. SUPSI no tiene datasheet comercial identificable; su ficha experimental no debe incluir fabricante/imp/vmp/Ns inventados.
- Modelos deben funcionar también con los módulos Canadian Solar; Huld usa coeficientes tecnológicos, mientras SDM comerciales se calibran clásicamente.
- **Igualdad experimental = condiciones controladas y mismas muestras, no promesa de CPU matemáticamente idéntica**; ejecución serial con rotación y variabilidad medida.
- Solo usar datos de laboratorio para calibrar SUPSI; datos exteriores para validar. Rondas repetidas de software NO generan replicaciones físicas independientes.
- No incluir líneas ficticias ni resultados inventados; curvas I-V y P-V eléctricas sólo en SDM; procesamiento de noche/gaps debe ser honesto.
- No agregar dependencias, servicios externos ni pantallas ajenas al proyecto. No crear un «framework por amor al framework»; Python modular suficiente.
- Cumple los checks en `docs/06_ARQUITECTURA_Y_PRUEBAS.md` antes de cerrar.

## GESTIÓN Y ENTREGAS

Trabaja por fases, con nombres de archivos y responsabilidades claros, usa el paquete como fuente de verdad. No destruyas el código legado ni modifiques datasets originales. Si una ambigüedad afecta una conclusión científica, muestra opción y limitación; para cuestiones meramente visuales decide tú. **Empieza ahora con FASE 0** y continúa implementación FASE 1 tan pronto la auditoría esté completa. Al terminar cada fase explica concisamente qué funciona, cómo lo probaste, qué falta y cualquier supuesto relevante. El artículo LaTeX y el DDM se harán posteriormente; NO redactes el artículo ahora.
