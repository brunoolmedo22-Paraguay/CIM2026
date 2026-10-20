# CIM26 — Photovoltaic Model Laboratory (v2, Streamlit)

Laboratorio científico para comparar la **exactitud** y el **costo computacional** de cuatro modelos de potencia fotovoltaica:

- **M1**: proporcional a irradiancia.
- **M2**: corrección térmica / PVWatts DC.
- **M3**: Huld / PVGIS c-Si.
- **M4**: modelo de un diodo (SDM).

La validación usa mediciones exteriores independientes SUPSI 2019 e incluye un benchmark secuencial reproducible.

> Streamlit por dentro, aplicación profesional por fuera. Interfaz en portugués brasileño; motor científico independiente de la interfaz.

## Ejecutar localmente

Requiere Python 3.12 (también es compatible con 3.11–3.13).

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
streamlit run app.py
```

## Desplegar en Streamlit Community Cloud

1. Sube **todo** el contenido de esta carpeta a un repositorio de GitHub. Incluye `input/`, `static/`, `.streamlit/` y `runs/`; `.gitignore` ya excluye cachés y datos de usuario.
2. En share.streamlit.io elige **Create app → Deploy a public app from GitHub** e indica el repositorio, la rama y el **Main file path `app.py`**.
3. En **Advanced settings**, selecciona **Python 3.12**. No se necesitan *secrets*.
4. Despliega. Cloud instala `requirements.txt` y ejecuta `streamlit run app.py`.

No hay servidores secundarios, puertos ni direcciones fijas. Fuentes y logotipo se sirven con `server.enableStaticServing`; Plotly y los componentes JS se cargan desde los paquetes instalados.

### Ejecuciones largas y almacenamiento en Cloud

- **Proceso aparte.** El experimento del modo Artigo (≈ 6 min con 11 rondas en 1 núcleo) corre en un proceso separado. La interfaz sigue respondiendo y se puede navegar, recargar o abrir otras sesiones sin interrumpirlo ni duplicarlo.
- **Un experimento a la vez.** Un bloqueo atómico impide que dos sesiones lancen dos experimentos.
- **Monitor y cancelación.** El progreso se ve en vivo y la ejecución se puede **cancelar** conservando las salidas parciales.
- **Disco efímero.** Cloud puede reiniciar la app, así que conviene descargar los resultados al terminar: el ZIP de la ejecución, `DISCUSSAO.md`, los CSV de cada tabla y las figuras SVG/PNG.
  - Los ZIP se **reimportan** en *Histórico* y se reabren sin recalcular.
  - Las fichas de módulo y las identificaciones SDM se exportan e importan en JSON.
- **Datos incluidos.** Los datos originales SUPSI se cargan siempre desde `input/`. La ejecución de verificación incluida en `runs/` está siempre disponible.
- **Carpeta de resultados.** Se puede cambiar con la variable de entorno opcional `CIM26_RUNS_DIR`.
- **Tiempos.** Los de Cloud corresponden a CPU compartida. Para mediciones de artículo, ejecuta el benchmark localmente o por CLI y documenta la máquina; queda registrada en `metadata.json`.

## Interfaz

| Área | Contenido |
|---|---|
| **Simulador** (modo Modelos) | Mosaicos de configuración (JS) que abren diálogos: biblioteca de módulos con tabla seleccionable, ficha, alta e importación de módulos, calibración SDM clásica o multipunto, arreglo Ns × Np, clima (calendario SUPSI en JS, CSV con mapeo POA/GHI, perfiles sintéticos, manual) y modelo térmico. Píldoras de modelos (JS), KPIs animados, potencia con irradiancia y temperatura superpuestas, curva I–V/P–V animada del SDM, exportación CSV/SVG/PNG. |
| **Dados e qualidade** | Cobertura, anomalías físicas A01–A09/T01, histogramas de coherencia, calendario de anomalías (JS), explorador diario con Pm, Gpoa, Isc equivalente y temperaturas, matrices IEC 61853 con verificaciones y auditoría, previsualización de la calibración. |
| **Protocolo e execução** | Criterios congelados (meses, umbral, política de anomalías, térmica, ΔT, rondas 3–101, orden, semilla, modo), resumen, lanzamiento, monitor con arco solar (JS) y cancelación. |
| **Resultados e discussão** | Síntesis redactada y cuatro áreas: I Energía, II Computacional, III Análisis integrado, IV Estadística. Cada una abre con su discusión basada en evidencia, seguida de gráficos interactivos, tablas descargables y figuras de publicación. |
| **Histórico** | Reabrir, comparar, descargar e importar ejecuciones sin recalcular. |

Hay tema claro y oscuro (menú ⋮ → *Settings*), diseño adaptable a móvil y animaciones que respetan `prefers-reduced-motion`.

## Línea de comandos (sin interfaz)

```bash
python -m cim26.cli run                      # 6 meses, 11 rondas, rotativo
python -m cim26.cli analyze runs/<run_id>    # recalcula métricas, anomalías y discusión desde archivos
python -m cim26.cli lab                      # verificaciones de la matriz IEC 61853
```

## Pruebas

```bash
python -m pytest -q              # 59 pruebas
python tools/verificar_paquete.py
```

Las pruebas cubren:

- las fórmulas;
- la regresión contra el código heredado;
- los datos y la calibración;
- 11 rondas × 4 modelos secuenciales;
- la exportación e importación ZIP;
- la identidad entre los modos Modelos y Artigo;
- la reproducción exacta de la ejecución v1.1;
- las cinco páginas Streamlit (`AppTest`);
- la ausencia de servidores HTTP;
- el bloqueo exclusivo y la cancelación.

## Estructura

```
app.py                  entrada Streamlit (navegación, tema, estado, barra lateral)
ui/                     interfaz: theme, components (HTML + JS v2), charts, services, state, nav, views/
cim26/                  motor científico independiente
  pvcore/               M1–M4, núcleo SDM, capa térmica
  data/                 campo y laboratorio SUPSI, anomalías, catálogo, clima
  calibration/          SDM clásico (legado) y multipunto SUPSI
  experiment/           configuración, métricas, orquestador, análisis, historial
  benchmark/            worker aislado, RSS, entorno
  stats/                tiempos, bootstrap por días, Pareto
  report/               figuras SVG/PNG, discusión automática
static/                 fuentes OFL y logotipo (static serving)
.streamlit/config.toml  temas claro/oscuro, fuentes, barra lateral
input/SUPSI/            datos originales (byte a byte) y derivados
runs/                   ejecución de verificación incluida
legacy_core/            código heredado intacto (pruebas de regresión)
docs/                   especificación, auditoría, arquitectura, verificación
```

## Limitaciones conocidas

- **Tiempos en Cloud.** El benchmark en Streamlit Cloud mide CPU compartida, con más ruido. Para el artículo conviene una máquina dedicada.
- **Memoria pico.** Solo es exacta en Linux (reinicio de VmHWM); otros sistemas registran RSS antes y después, con el método declarado.
- **Disco efímero en Cloud.** Los resultados deben exportarse en ZIP para conservarlos.
- **Cambio de tema.** Las figuras Plotly toman los colores del tema en la última ejecución del script. Al alternar claro/oscuro sin interacción, los gráficos se actualizan en la siguiente interacción; los componentes HTML/JS cambian al instante.
- **Mosaicos y calendarios.** Son componentes JS v2 que necesitan Streamlit ≥ 1.66 (fijado en `requirements.txt`).
- **Animación I–V.** Usa hasta 72 instantes por día (submuestreo uniforme) para mantener la fluidez.
- **Alcance científico.** No hay transposición GHI→POA para planos inclinados, ni coeficientes Huld verificados para CdTe/CIGS.
- **Discusión automática.** Se genera por reglas, con umbrales declarados (0,5 p.p. y criterios de anomalía), y requiere revisión científica.
- **Rodadas.** Las rondas de software no son réplicas físicas; ΔT célula–módulo es una hipótesis con sensibilidad calculada.

Consulta `CHANGELOG.md` para el registro de modificaciones y `docs/` para la auditoría, la arquitectura y la verificación.
