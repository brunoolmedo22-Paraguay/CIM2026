# 05 — Contrato funcional de la UI Streamlit

**Claude tiene total libertad creativa visual**: composición, colores, tipografía, controles, navegación y microinteracciones, siempre que se preserve legibilidad, funcionalidad y trazabilidad. No copiar literalmente un mockup. Interfaz preferentemente **portugués brasileño** (aplicativo científico), con identificadores internos estables. No crear páginas de marketing ni funciones que no apoyen las dos operaciones principales.

## App
- Python + Streamlit. Iniciar: `streamlit run app.py`.
- Navegación principal simple con exactamente dos modos **«Modelos»** y **«Artigo»**; comparten motor, catálogo y componentes de presentación, sin lógica física duplicada.
- Apoyo para archivos locales suministrados, no exigir APIs remotas, credenciales ni servicios.
- Progreso de cálculos y avisos de error explicativos. Exportar archivos y lotes de resultados en ZIP descargable.

## Modo «Modelos» — herramienta de simulación familiar
1. Biblioteca Canadian Solar heredada más ficha SUPSI experimental. Selector de módulo y edición de parámetros con fuente; formulario para nuevo módulo vía datasheet comercial sin matrices especiales.
2. Selector modelo M1/M2/M3/M4. Mostrar claramente disponibles/no disponibles y motivos según datos requeridos. Para SDM, botón **«Estimar parâmetros SDM»** (método clásico si datasheet completo, multipunto solo si matriz laboratorio). Mostrar método, residuos, convergencia y permitir guardar identificación con metadatos.
3. Configuración arreglo: `Nserie`, `Nparalelo` enteros positivos, potencia instalada; el motor trata P por módulo y multiplica, generando I–V/P–V eléctricas solo en SDM (jamás I–V falsas en M1/M2/M3).
4. Entrada meteorológica: CSV propio (mapeo explícito POA/GHI), perfiles sintéticos de legado como opción secundaria, o ajuste manual Gpoa, Tamb, Tmod; perfiles variables de 120 min o cualquier horizonte. Indicar si entrada es medida, estimada o simulada; **GHI no es POA**. Si solo GHI, transposición física justificable con inclinación/acimut/posición/irradiancia adecuada o declarar que no se puede calcular automáticamente (NO renombrar GHI).
5. Ejecutar un modelo, KPIs Pmax/E bajo el período válido, curva potencia-tiempo, I–V/P–V solo SDM, avisos de validez, exportación CSV/SVG/PNG. Usuario puede ajustar condiciones libremente; este modo NO cambia parámetros del ensayo Artigo congelado.

## Modo «Artigo» — laboratorio experimental
**Zona de preparación:** seleccionar meses/dataset SUPSI importado, comprobar ficha/matrices de calibración, estado del ajuste, previsualizar tabla completa y gráficos Pm/Gpoa/Tbom/Tamb/wind, mostrar N y motivos de exclusión, elegir estrategia térmica, umbral G, orden, semilla y `repeticiones` (11 por defecto); configurar sin reestimar con campo.

**Botón «Executar experimento científico»**: lanza corrida nueva, secuencial con warmup y orden de modelos rotativo, indicador ronda i/11, M1–M4, progreso, tiempos aproximados solo si medidos. Evitar doble ejecución por rerun de Streamlit. Si falla, mantener progreso/salidas parciales y error explícito; nunca imprimir números falsos.

**Resultados — exactamente 4 pestañas:**
I. **Energia:** curvas Pobs y Pmodelos, energía acumulada sobre pares válidos, RMSE/MAE/MBE, errores por día/mes, residuales G/T, vista tabla. Controles de zoom/intervalo.
II. **Computacional:** tiempo total y por muestra, medianas/p95, RAM pico y delta, escalabilidad, fallos/convergencia, configuración de CPU/soft, comparación por ronda; distinguir calibración fuera del benchmark.
III. **Análise integrada:** scatter error vs tiempo, error vs memoria, frontera Pareto resaltada y criterios, comparaciones de mejora marginal, sensibilidad térmica y requisitos de parametrización de cada modelo.
IV. **Estatística:** boxplots, desviación estándar, coeficiente de variación, percentiles, CI justificables de tiempo, estabilidad temporal, histogramas, bootstrap de errores por bloques/días, resultados numéricos exportables.

**Histórico:** lista de experimentos previos con fecha/config y opción de reabrir, comparar y exportar sin necesidad de volver a correr.

**Arquitectura de GUI:** toda estimación/validación/benchmark implementada en módulos de Python con tests, no en `app.py`. La UI puede ser vistosa, pero el motor debe funcionar por CLI/test sin Streamlit.
