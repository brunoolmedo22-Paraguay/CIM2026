# CIM26 — exactitud × costo computacional de cuatro modelos FV

Aplicación científica Python + Streamlit para comparar **M1** (proporcional a irradiancia), **M2** (corrección
térmica / PVWatts DC), **M3** (Huld / PVGIS c-Si CURRENT) y **M4** (modelo de un diodo, SDM) contra mediciones
exteriores independientes SUPSI 2019, con benchmark computacional secuencial.

La interfaz está en portugués brasileño. El motor (`cim26/`) es independiente de Streamlit y se usa también por
CLI y pruebas.

## Instalación

Requiere Python 3.11 o superior. No necesita Internet una vez instaladas las dependencias.

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

**Windows (PowerShell)**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

`requirements.txt` fija rangos; `requirements-lock.txt` contiene las versiones exactas con que se verificó todo.
Cada experimento guarda además su propio `environment_freeze.txt`.

## Los dos modos

**Modelos** es la herramienta general. Ofrece la biblioteca Canadian Solar heredada (16 módulos, leída del
archivo legado sin copiar valores), la ficha experimental SUPSI y los módulos que cree el usuario. Incluye arreglo
Ns × Np y cuatro fuentes meteorológicas:

- días SUPSI medidos;
- CSV propio, con mapeo explícito POA/GHI;
- perfiles sintéticos heredados, con cualquier horizonte;
- condición manual.

El botón **«Estimar parâmetros SDM»** usa la calibración clásica para datasheets y la multipunto para SUPSI. Las
curvas I–V y P–V aparecen solo con M4. Se exportan CSV, SVG y PNG.

**Artigo** es el laboratorio experimental, con tres áreas:

- **Preparação**: elegir meses, revisar la calidad con los motivos de exclusión, ver la vista previa de datos y las
  matrices de laboratorio con su auditoría, y configurar el protocolo. El botón **«Executar experimento científico»**
  lanza el experimento en un proceso independiente que sobrevive a recargas de la página y bloquea la doble ejecución.
- **Resultados**: cuatro pestañas, I Energia, II Computacional, III Análise integrada y IV Estatística. Incluye la
  exportación ZIP de la ejecución.
- **Histórico**: reabrir, comparar e importar ejecuciones sin recalcular modelos.

## Línea de comandos

```bash
python -m cim26.cli lab                       # verificaciones de la matriz IEC 61853
python -m cim26.cli calibrate                 # calibración SDM multipunto (solo laboratorio)
python -m cim26.cli run                       # experimento por defecto: 6 meses, 11 rondas, rotativo
python -m cim26.cli run --repetitions 21 --order aleatoria --seed 7
python -m cim26.cli analyze runs/<run_id>     # recalcula métricas desde predictions.csv
```

En la máquina de verificación (1 núcleo Xeon a 2,8 GHz) el experimento por defecto tarda ≈ 5 min. El SDM
domina ese tiempo.

## Pruebas

```bash
python -m pytest -q                           # 44 pruebas: unidad, regresión, integración, 11×4, UI
python tools/verificar_paquete.py             # verificador original del paquete
```

## Estructura

```
app.py                     punto de entrada Streamlit (solo navegación)
ui/                        páginas, gráficos Plotly y estilo (sin física)
cim26/pvcore/              M1–M4, núcleo SDM portado, capa térmica, ModuleSpec
cim26/data/                SUPSI campo/laboratorio, catálogo, entradas meteorológicas
cim26/calibration/         calibrador clásico (legado) y multipunto SUPSI, persistencia
cim26/experiment/          configuración, métricas, orquestador, análisis, historial
cim26/benchmark/           worker aislado, medición RSS, entorno
cim26/stats/               tiempos, bootstrap por días, Pareto
cim26/report/              figuras SVG/PNG y README_RUN
cim26/simulate.py          simulación del modo Modelos (mismo código físico)
cim26/cli.py               interfaz de línea de comandos
input/SUPSI/               datos originales (byte a byte) y derivados declarados
legacy_core/, reference_implementations/   referencia intacta (usada en pruebas de regresión)
tests/                     pruebas
runs/                      ejecuciones (incluye la de verificación de la Fase 4)
docs/                      especificación original + AUDITORIA_FASE0, ARQUITECTURA, VERIFICACION_FASE4
```

## Reproducibilidad y trazabilidad

Cada `runs/<run_id>/` contiene lo siguiente:

- configuración inmutable;
- todas las filas de entrada con su elegibilidad;
- predicciones por muestra;
- los 44 registros medidos más los de escalado;
- estadísticas;
- SHA256 de las entradas;
- hardware y versiones;
- tiempos por etapa separados (lectura, calibración, preparación, cómputo);
- figuras;
- `README_RUN.md`.

Las tablas de error se recalculan desde `predictions.csv`. La clave estable de cada muestra es
`source_file + source_row`.

## Límites declarados

- Las rondas repetidas de software no son réplicas físicas independientes.
- ΔT célula–módulo (3 °C) es una hipótesis. Hay una sensibilidad calculada para 0, 2, 3 y 5 °C.
- M3 usa coeficientes tecnológicos genéricos. M2 usa el γ medido. M4 usa 66 mediciones de laboratorio. Estas
  asimetrías de parametrización son parte del estudio.
- Los cuatro modelos reciben la misma POA medida. No se aplican correcciones ópticas (AOI, espectro) a ninguno.
- La memoria pico por llamada es exacta solo en Linux (reinicio de VmHWM). En otros sistemas se registra RSS
  antes/después y se declara el método usado.
- Los tiempos son de un PC; no se extrapolan a hardware embebido.
- La ejecución incluida es un **diagnóstico de ingeniería**: no constituye conclusión científica sin revisión.
