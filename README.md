# CIM26 — exactitud × costo computacional de cuatro modelos FV (v1.1)

Aplicación científica para comparar cuatro modelos de estimación de potencia fotovoltaica:

- **M1**, proporcional a la irradiancia;
- **M2**, con corrección térmica (PVWatts DC);
- **M3**, Huld / PVGIS c-Si CURRENT;
- **M4**, modelo de un diodo (SDM).

La comparación se hace contra mediciones exteriores independientes SUPSI 2019 e incluye un benchmark computacional secuencial.

- **Motor científico:** Python (`cim26/`), probado y usable por línea de comandos.
- **Interfaz:** aplicación web propia en HTML, CSS y JavaScript (`web/static`), en portugués brasileño. La sirve localmente un servidor de la biblioteca estándar de Python, sin Streamlit, servicios externos ni conexión a Internet. Plotly.js se carga desde el propio paquete `plotly` y las tipografías (IBM Plex Sans y Source Serif 4, licencia OFL) van incluidas.

## Instalación y arranque

Requiere Python 3.11 o superior.

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

**Windows (PowerShell)**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Se abre `http://127.0.0.1:8765` en el navegador. Las opciones `--port 9000` y `--no-browser` permiten cambiar el puerto o no abrir el navegador.

## Interfaz

**Simulador (modo Modelos)** es un espacio de trabajo único:

- Cuatro tarjetas de configuración (módulo, arreglo, clima y temperatura) abren paneles laterales; los resultados se recalculan al aplicar.
- Píldoras de modelo para comparar uno o varios modelos a la vez; el modelo sin parámetros indica el motivo y ofrece la calibración.
- KPIs animados.
- Potencia con la irradiancia y la temperatura superpuestas en ejes secundarios.
- La curva I–V/P–V del SDM se puede **reproducir a lo largo del día**.
- Fuentes de clima:
  - calendario de días SUPSI coloreado por irradiación;
  - CSV propio con mapeo explícito POA/GHI (GHI solo se acepta con módulo horizontal);
  - perfiles sintéticos heredados;
  - condición manual.
- La medida SUPSI solo se compara cuando el módulo simulado es el SUPSI.

**Artigo** tiene cuatro secciones:

- **Dados e qualidade**: cobertura y exclusiones, **anomalías físicas de medición** (A01–A09, T01), histogramas de coherencia Isc×G y P/(Pstc·G), calendario de anomalías, explorador diario con Pm, Gpoa, Isc equivalente y temperaturas superpuestas, y las matrices de laboratorio con su auditoría y la previsualización de la calibración.
- **Protocolo e execução**: criterios congelados (meses, umbral G, política de anomalías, estrategia térmica, ΔT, rondas 3–101, orden, semilla, modo) y el botón «Executar experimento científico». La ejecución corre en un proceso aparte, con un arco solar animado que muestra etapa, ronda y modelo.
- **Resultados e discussão**: síntesis redactada y cuatro pestañas (I Energia, II Computacional, III Análise integrada, IV Estatística). Cada pestaña abre con **párrafos de discusión** generados a partir de los datos («M4 apresentou o menor nRMSE…», «M1 teve o menor custo…»), con la etiqueta de evidencia robusta, indicativa, inconclusiva o de contexto. Las métricas principales están en **%** (nRMSE, nMAE, nMBE y error de energía), y los vatios quedan como dato secundario.
- **Histórico**: reabrir, comparar e importar ejecuciones sin recalcular.

## Calidad de los datos

Las anomalías se detectan solo con variables medidas y con criterios fijados de antemano; las mismas afectan a los cuatro modelos. Por defecto se **señalan** sin excluir, y el efecto sobre los errores se reporta siempre como sensibilidad: escenarios sin errores, sin errores ni sospechas, solo condiciones estables y solo transitorios. La exclusión de la máscara principal es una política explícita del protocolo y queda registrada en `config.json`.

## Línea de comandos

```bash
python -m cim26.cli run                     # 6 meses, 11 rondas, rotativo (≈ 6 min en 1 núcleo)
python -m cim26.cli run --repetitions 21 --order aleatoria --seed 7
python -m cim26.cli analyze runs/<run_id>   # recalcula métricas, anomalías y discusión desde los archivos
python -m cim26.cli lab                     # verificaciones de la matriz IEC 61853
```

## Pruebas

```bash
python -m pytest -q                         # 54 pruebas: unidad, regresión, integración, 11×4, API web
python tools/verificar_paquete.py
```

## Estructura

```
app.py                 inicia el servidor local y abre el navegador
web/server.py          API JSON sobre el motor (sin física)
web/static/            index.html, app.css, js/ (main, ui, modelos, artigo), fonts/
cim26/pvcore/          M1–M4, núcleo SDM portado, capa térmica
cim26/data/            SUPSI campo/laboratorio, anomalías, catálogo, clima
cim26/calibration/     calibrador clásico (legado) y multipunto SUPSI
cim26/experiment/      configuración, métricas, orquestador, análisis, historial
cim26/benchmark/       worker aislado, RSS, entorno
cim26/stats/           tiempos, bootstrap por días, Pareto
cim26/report/          figuras SVG/PNG, discusión automática, README_RUN
input/SUPSI/           datos originales (byte a byte) y derivados
legacy_core/           referencia intacta (pruebas de regresión)
runs/                  ejecución de verificación
docs/                  especificación + AUDITORIA_FASE0, ARQUITECTURA, VERIFICACION_FASE4
```

## Límites declarados

- Las rondas de software no son réplicas físicas independientes.
- ΔT célula–módulo es una hipótesis, con sensibilidad calculada para 0–5 °C.
- Asimetría de parametrización: M2 usa el γ medido, M3 coeficientes genéricos y M4 66 mediciones de laboratorio.
- La misma POA medida va a los cuatro modelos, sin corrección óptica en ninguno.
- La memoria pico por llamada es exacta solo en Linux.
- Los tiempos son de un PC.
- La discusión automática se genera por reglas y es un **diagnóstico que requiere revisión científica**.
