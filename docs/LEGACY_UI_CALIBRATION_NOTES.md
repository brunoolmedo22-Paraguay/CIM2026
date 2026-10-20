# Referencia de UI de calibración solar original

Archivo fuente: `solarsdm-main/app.py` (ZIP suministrado por el usuario). Estos extractos sirven para localizar el flujo del botón; NO son una app ejecutable.

### app.py lines 89-114
```python
  89: from simulation.export import (
  90:     DEFAULT_EXPORT_COLUMNS,
  91:     available_export_columns,
  92:     build_export_dataframe,
  93:     normalize_csv_filename,
  94:     slice_results_interval,
  95: )
  96: from simulation.mpp import find_mpp, simulate_timeseries
  97: from simulation.solver import extract_sdm_params, translate_params
  98: from visualization.plots import (
  99:     plot_efficiency,
 100:     plot_energy,
 101:     plot_irradiance,
 102:     plot_iv_family,
 103:     plot_iv_pv,
 104:     plot_mpp_trajectory,
 105:     plot_power,
 106:     plot_profile_coverage,
 107:     plot_temperatures,
 108: )
 109: 
 110: # ===========================================================================
 111: # Configuración de la página
 112: # ===========================================================================
 113: st.set_page_config(
 114:     page_title=UI["app_title"],
```

### app.py lines 162-187
```python
 162: init_state()
 163: 
 164: 
 165: @st.cache_data(show_spinner=False)
 166: def cached_extraction(stc_dict: dict):
 167:     """Extracción de los 5 parámetros SDM (cacheada por hoja de datos)."""
 168:     from models.pv_module import ModuleSTC
 169:     stc = ModuleSTC(**stc_dict)
 170:     sdm, report = extract_sdm_params(stc)
 171:     return sdm.to_dict(), report
 172: 
 173: 
 174: def select_date_window(df: pd.DataFrame, key_prefix: str) -> tuple[pd.DataFrame, str]:
 175:     """Selector reutilizable para mostrar un día o un intervalo de fechas."""
 176:     if df is None or df.empty:
 177:         return df, "—"
 178: 
 179:     min_date = df.index.min().date()
 180:     max_date = df.index.max().date()
 181:     if min_date == max_date:
 182:         return df, min_date.isoformat()
 183: 
 184:     mode = st.radio(
 185:         "Período mostrado", ["Um dia", "Intervalo de dias"],
 186:         horizontal=True, key=f"{key_prefix}_mode",
 187:     )
```

### app.py lines 306-331
```python
 306:         "sobre los puntos de catálogo (Isc, Voc, MPP, dP/dV = 0 y β<sub>Voc</sub>). "
 307:         "Todos los valores son editables.</div>",
 308:         unsafe_allow_html=True,
 309:     )
 310:     st.write("")
 311: 
 312:     col_btn, col_msg = st.columns([1, 3])
 313:     with col_btn:
 314:         do_extract = st.button("⚙️ Estimar parámetros SDM", type="primary", width="stretch")
 315: 
 316:     if do_extract or st.session_state["module"] is None:
 317:         with st.spinner("Resolviendo el sistema de 5 ecuaciones…"):
 318:             sdm_dict, report = cached_extraction(stc.to_dict())
 319:         st.session_state["module"] = PVModule(stc=stc, sdm=SDMParams(**sdm_dict))
 320:         st.session_state["extraction"] = report
 321: 
 322:     module: PVModule = st.session_state["module"]
 323:     module.stc = stc                                # mantener STC sincronizado
 324:     sdm = module.sdm
 325:     report = st.session_state["extraction"]
 326: 
 327:     with col_msg:
 328:         if report is not None:
 329:             if report.success:
 330:                 st.success(
 331:                     f"Ajuste convergido · residuo cuadrático = {report.cost:.2e} "
```
