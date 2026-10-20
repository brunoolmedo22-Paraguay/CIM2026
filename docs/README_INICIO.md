# CIM26 — paquete de trabajo para Claude Pro (v1.0)

**Destino:** desarrollo de una aplicación **Python + Streamlit**. Este ZIP es un *handoff*: incluye código heredado, datos originales y diseño detallado; **NO contiene ni promete una aplicación Streamlit nueva ya desarrollada**.

## Comienza por aquí

1. Leer `PROMPT_PARA_CLAUDE.md`, que contiene la orden principal y el modo de ejecución por etapas.
2. Leer en orden `docs/01_ALCANCE.md`, `docs/02_FORMULACIONES.md`, `docs/03_DATOS_Y_CALIBRACION.md`, `docs/04_PROTOCOLO_Y_ESTADISTICA.md`, `docs/05_INTERFAZ_STREAMLIT.md`, `docs/06_ARQUITECTURA_Y_PRUEBAS.md`.
3. Examinar los módulos Python existentes en `legacy_core/`. **Son fuentes de referencia, no una especificación de diseño obligatorio**. Refactorizar para eliminar restricción de 120 min y confusión GHI/POA; no cambiar ecuaciones sin justificar ni testear.
4. Revisar `input/SUPSI/raw/` (copias byte a byte) y `input/SUPSI/derived/` (derivados declarados de laboratorio).
5. Usar `reference_implementations/` solo como material matemático/técnico, **no copiar el piloto como si fuera código validado**.
6. Programar, probar y demostrar cada fase; cada entrega debe ser utilizable y reproducible.
7. Opcional: `python reference_implementations/piloto_sdm_original.py` reproduce un ajuste de factibilidad con `numpy`/`scipy` y el CSV de laboratorio derivado. **No es validación final**.

## Dos modos / cuatro modelos

**Modo Modelos:** herramienta general con datasheets Canadian Solar, selector de módulo, arreglo Ns/Np, entradas meteorológicas, curva y exportación.

**Modo Artículo:** referencia SUPSI, 4 modelos corridos *secuencialmente*, **11 rondas** por defecto con alternancia de orden, resultados energéticos, computacionales, integrados y estadísticos, exportables con trazabilidad.

M1 irradiancia; M2 corrección térmica/PVWatts; M3 Huld/PVGIS; M4 SDM. **NO DDM**. No agregar modelos irrelevantes, baterías, eólica, térmica, hidrógeno, MPPT P&O ni conversiones AC a esta versión.

## Orígenes importantes

- Datos SUPSI / IEA PVPS: https://pvpmc.sandia.gov/datasets/iea-pvps-task-13-module-validation-dataset/
- Fórmula y coeficientes Huld: https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/general-information/data-sources-calculation-methods_en
- pvlib PVWatts: https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.pvsystem.pvwatts_dc.html
- Informe IEA: contenido íntegro en `input/references/IEA_PVPS_T13_20_2020_Climatic_Rating.pdf` (Anexo 1, pp.164–165).
- `PROPOSTA_CIM26_ORIGINAL.pdf`: justificación original y requisitos del congreso, no sustituyen decisiones actuales documentadas aquí.

## Restricciones y límites

- SUPSI no identifica su fabricante/modelo comercial ni publica Vmp, Imp, Ns. No inventarlos; usar ficha experimental y, para SDM, calibración multipunto de laboratorio.
- Los 66 puntos de calibración derivados equivalen a 22 pares G–T × [Pmp,Isc,Voc]. El literal `32` en las matrices originales es ausencia de medición, no 32 W/A/V.
- La validación de campo debe ser independiente y se debe reportar la cobertura real de timestamps/intervalos, con faltantes y calidad de datos, no una energía anual reconstruida por silencio.
- `reference_implementations/piloto_sdm_resultado_NO_VALIDADO.json` NO es una conclusión científica; no lo use como valor fijo sin recalibración documentada.
- No introducir números de rendimiento ni interpretaciones de "mejor modelo" sin ejecutar el protocolo definitivo.

## Comprobación del paquete

```bash
python tools/verificar_paquete.py
python -m unittest discover -s tests -v
```

Este paquete es deliberadamente pequeño en código nuevo: Claude debe implementar la aplicación científica a partir de estas especificaciones y referencias, no heredar funcionalidades no relacionadas.
