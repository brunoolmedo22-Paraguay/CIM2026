# Registro de modificaciones

## v2.0.0 — Migración a Streamlit

### Arquitectura

- **Entrada `streamlit run app.py`.** `app.py` es un script Streamlit real: hace `st.navigation` con 5 páginas, inyecta el tema, inicializa el estado y monta la barra lateral.
- **Eliminados el servidor HTTP propio y la SPA** (`web/server.py`, `web/static/*.js`, `ThreadingHTTPServer`, puerto 8765 y `webbrowser`).
  - **Causa del `OSError: [Errno 98] Address already in use`:** Streamlit Cloud ejecutaba `app.py` con `__name__ == "__main__"`, eso arrancaba el `ThreadingHTTPServer` dentro de Streamlit y cada *rerun* volvía a abrir el puerto.
  - **Garantía:** una prueba recorre el código y falla si reaparece `http.server`, `serve_forever`, `webbrowser`, `uvicorn` o `socketserver`.
- **Nueva capa `ui/`:**
  - `theme`: sistema de diseño;
  - `components`: HTML y componentes JS;
  - `charts`: Plotly;
  - `services`: acceso al motor con caché de visualización;
  - `state`: estado de sesión;
  - `nav`: navegación y monitor;
  - `views/`: las páginas.
- **Componentes JavaScript con el sistema oficial `st.components.v2`:** sincronización de tema, mosaicos de configuración, píldoras de modelos, KPIs con contador animado, calendario de días y arco solar de ejecución. El JS solo emite eventos (`setTriggerValue`) y Python es la única fuente de verdad (`st.session_state`). No hay `st.html` con scripts ni iframes que escriban en el estado.
- **Animación I–V del SDM con fotogramas nativos de Plotly:** reproducir, pausar y el deslizador se ejecutan en el navegador, sin *reruns*.
- **Diseño visual:**
  - Paleta, tipografías (IBM Plex Sans y Source Serif 4, servidas desde `static/` con `[[theme.fontFaces]]`) y barra lateral de tinta trasladadas desde la v1.1.
  - Temas claro y oscuro (`[theme.light]` / `[theme.dark]`), con detección del tema real en el navegador.
  - Los únicos selectores internos de Streamlit están aislados en `ui/theme.py::ST_OVERRIDES` y son solo cosméticos.

### Estado y ejecuciones largas

- **Sin avisos de widgets.** Los valores por defecto se definen una sola vez en `ui/state.py` y los widgets no reciben `value`/`default` cuando su clave ya existe; las claves se reasignan en cada ejecución para sobrevivir al cambio de página.
- **Experimento en un proceso aparte.** Lo lanza `run_store.launch_background`, que ahora reserva el bloqueo de forma atómica (`O_CREAT|O_EXCL`), de modo que dos sesiones no pueden lanzar dos experimentos.
- **Monitor en vivo** con `st.fragment(run_every=…)`: solo el fragmento se refresca.
- **Nuevo `cancel_run`:** termina el árbol de procesos, marca la ejecución como `cancelado` y conserva las salidas parciales.
- **`CIM26_RUNS_DIR`:** variable de entorno opcional para la carpeta de ejecuciones.
- **Caché solo para visualización.** El benchmark nunca pasa por la caché y ejecuta los modelos de verdad en su *worker* aislado.

### Persistencia

- Las ejecuciones se exportan e importan como ZIP; también se exportan `DISCUSSAO.md`, los CSV de cada tabla y las figuras SVG/PNG de publicación.
- Las fichas de módulo y las identificaciones SDM se exportan e importan en JSON, porque el disco de Streamlit Cloud es efímero.

### Motor científico (sin cambios de ecuaciones, parámetros, calibración ni métricas)

- `ModuleSpec.label` muestra «SUPSI · mono-Si (laboratório)» en lugar del identificador interno del módulo experimental. Es un cambio cosmético.
- `__version__` pasa a 2.0.0.
- **Consistencia numérica:** `test_bundled_v11_run_reproduced_by_current_engine` exige que el motor actual reproduzca **con tolerancia cero** las predicciones M1–M4 de la ejecución de verificación v1.1.

### Problemas reportados

- **`Address already in use`:** corregido por diseño; ya no existe servidor propio.
- **Errores de importación de `cim26.stats` / `cim26.calibration` y de `dataclass`:** no se reproducen con Python 3.12; todos los paquetes tienen `__init__.py` y las 59 pruebas importan todo el motor. Esos errores aparecen típicamente cuando Cloud usa otra versión de Python o una subida parcial del repositorio. Por eso se fija Python 3.12 en `.python-version` y en las instrucciones.
- **Avisos de estado de widgets:** eliminados, como se describe en «Estado y ejecuciones largas».

## v1.1.0

Interfaz HTML/CSS/JS propia, anomalías físicas, métricas porcentuales y discusión automática.

## v1.0.0

Motor científico, protocolo experimental y la primera interfaz Streamlit.
