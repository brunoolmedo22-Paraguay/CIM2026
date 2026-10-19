# 02 — Formulaciones matemáticas e instrucciones de implementación

Convenciones: `Gpoa` = irradiancia incidente en plano (W/m²), `Geff` = efectiva tras pérdidas ópticas **solo si se conocen y aplica igual política documentada**; `Pstc` = potencia STC (W), `Tmod` = superficie posterior (°C), `Tcell` = célula (°C), `Gref=1000 W/m²`, `Tref=25 °C`. Salida principal de cada modelo: `P_mpp_dc_W`, por módulo y escalada a arreglo multiplicando por `Nserie*Nparalelo` solo en modo Modelos. En Artículo: un único módulo SUPSI.

## M1 — Proporcional a irradiancia
`P = Pstc * (Gpoa/1000)`. Usar `P=0` si `Gpoa=0`. No añadir otras pérdidas en el experimento principal. No requiere T. Importar la implementación heredada cuando corresponda.

## M2 — Lineal térmico / PVWatts DC (NO contar como dos modelos)
`P = Pstc * (Gpoa/1000) * [1 + gamma * (Tcell - 25)]`, con `gamma` en **1/°C**, conversion exacta `gamma_pct/100` desde datasheet. `max(0, P)` documentado. El heredado calcula `Tc` vía NOCT antes de ajustar eficiencia con área; se debe separar cálculo térmico de modelo eléctrico y asegurar equivalencia con PVWatts en condiciones equivalentes.

Fuente: https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.pvsystem.pvwatts_dc.html
**Nota importante:** pvlib/PVWatts formula requiere irradiancia *efectiva* desde el punto de vista óptico para su consistencia completa. Para comparación base, usar POA medida en los cuatro modelos bajo hipótesis de pérdidas ópticas comunes no calibradas. Registrar como limitación/analizar sensibilidad de AOI si procede; no dar a un modelo correcciones que otros no reciben.

## M3 — Huld/PVGIS, modelo NUEVO a implementar
Definir `u=Gpoa/1000` y `dT=Tmod-25`. Si `Gpoa=0`, `P=0`, sin log(0).

`P = Pstc*u*eta_rel`

`eta_rel = 1 + k1*ln(u) + k2*[ln(u)]² + k3*dT + k4*dT*ln(u) + k5*dT*[ln(u)]² + k6*dT²`

**Coeficientes JRC PVGIS, familia c-Si CURRENT (congelar conjunto/versión, no confundir con CSI 2025):**

| coef. | c-Si current |
|---|---:|
| k1 | -0.017237 |
| k2 | -0.040465 |
| k3 | -0.004702 |
| k4 | 0.000149 |
| k5 | 0.000170 |
| k6 | 0.000005 |

Fuente primaria: https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/general-information/data-sources-calculation-methods_en
Implementación de contraste: https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.pvarray.huld.html
- Huld usa **temperatura posterior del módulo**, no asumir que necesita Tcell.
- STC `G=1000,Tmod=25`: `P=Pstc`. Para `G=0`: `P=0`.
- Para tecnología no soportada/coeficientes no disponibles: mostrar causa y deshabilitar, no usar coeficientes c-Si por defecto para CdTe/CIGS.
- Coeficientes tecnológicos no calibrados para cada Canadian Solar; reportar este hecho.
- Para bajo G aplicar filtro/calidad común, no extrapolar log fuera de dominio sin advertir. Escalar a arreglo como `Ns*Np*P_mod`.

## M4 — SDM de circuito equivalente, usar núcleo heredado
`I = IL - I0*( exp((V + I*Rs)/a)-1 ) - (V+I*Rs)/Rsh`
`a = n*N_cells*kB*Tcell_K/q`; si Ns desconocido y ajuste multipunto: usar `a_ref` directamente, sin inventar n o N_cells.
En referencia STC: IL_ref, I0_ref, Rs, Rsh_ref, a_ref. Trasladar por irradiancia y temperatura con ecuaciones documentadas en `legacy_core/simulation/solver.py`: 
- `a(T)=a_ref*(T_K/Tref_K)`;
- `IL(G,T)=G/Gref*(IL_ref+alpha_Isc*(T-25))`;
- `Rsh(G)=Rsh_ref*(Gref/G)`;
- `Rs` constante;
- `I0` proporcional a `(T/Tref)^3 exp[Eg_ref/(k_eV*Tref) - Eg(T)/(k_eV*T)]`.
Para G=0 devolver 0 W; para G>0 resolver la I(V) con Lambert W (legado) y maximizar P(V) con búsqueda acotada, registrar tolerancia, estado, iteraciones y fallos. Considerar fallback numérico **solo** documentado, no reemplazar algoritmo silenciosamente.
- **Ruta comercial clásica:** `extract_sdm_params` de `legacy_core/simulation/solver.py`, restricciones Isc,Voc,Vmp,Imp, dP/dV=0, beta_Voc y Ns del datasheet. Preservar comportamiento y botón de calibración. No repetir calibración dentro de las 11 rondas de evaluación.
- **Ruta SUPSI multipunto:** ajustar IL_ref, log10(I0_ref), Rs, log10(Rsh_ref), a_ref a matriz G–T con residuos de Pmp,Isc,Voc normalizados por escalas STC; usar `least_squares` con cotas físicas, multiarranque, reportar límites y sensibilidad/Jacobiano. Solo en laboratorio; campo 2019 intocable para ese ajuste.
- La simulación evaluará `Pmpp` con solver. PVWatts/Huld y SDM son diferentes modelos físicos, no duplicar la misma ecuación renombrada.

## Capa térmica común y dos experimentos
**Artículo A principal (aislar desempeño eléctrico):** usar `Tbom` medido, idéntico por timestamp para todos. Para Huld: `Tmod=Tbom`. Para M2/SDM: `Tcell=Tbom+(Gpoa/1000)*DeltaT` (Sandia eq. 23, pp. 99 del informe; `DeltaT` en °C a irradiancia 1000 W/m²). Propuesta de `DeltaT=3°C` inicialmente, **identificar como hipótesis, no dato medido**. Estudiar sensibilidad con `DeltaT=0,2,3,5 °C`. Esta conversión común para modelos que requieren Tcell no implica una T numéricamente idéntica a Tmod: sus variables físicas son distintas.
**Artículo B opcional (estimación térmica real):** `Tmod=Tamb+Gpoa/(U0+U1*Wind)`, cuando estén disponibles U0/U1 experimentales y con unidades validadas. Para datasheets comerciales sin U0/U1, alternativa NOCT: `Tcell=Tamb+((NOCT-20)/800)*Gpoa` pero tratar temperatura de forma consistente y etiquetar el método, nunca confundir Tcell vs Tmod. Validar fórmula térmica U0/U1 de fuente antes de utilizarla y no mezclar métodos en un mismo gráfico sin etiqueta.

## Métricas físicas
`MAE=mean(abs(Ppred-Pobs))`, `RMSE=sqrt(mean((Ppred-Pobs)^2))`, `MBE=mean(Ppred-Pobs)` (positivo = sobrestimación). NMAE/NRMSE deben declarar normalizador (Pstc o media observada); no usar MAPE en muestras de Pobs≈0. Integrar por trapezoides SOLO intervalos adyacentes temporalmente válidos (e.g. <=7.5 minutos para cadencia nominal 5 min) y sobre la misma máscara; no puentear noche o huecos. `E_kWh = sum[(Pi+Pi+1)/2 * Delta_h]/1000` en pares válidos y en el mismo soporte temporal; reportar tiempo cubierto y energía parcial, no llamar anual/semestral completa si hay cobertura incompleta.
