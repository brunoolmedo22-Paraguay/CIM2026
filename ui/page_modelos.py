"""Modo «Modelos»: simulação geral com datasheets, arranjo Ns×Np e entradas meteorológicas."""

from __future__ import annotations

import hashlib
import io
import json

import numpy as np
import pandas as pd
import streamlit as st

from cim26.calibration.classical import calibrate_classical
from cim26.calibration.multipoint import calibrate_multipoint
from cim26.calibration.store import list_calibrations, load_reference, save_calibration
from cim26.constants import SANDIA_DELTA_T_DEFAULT_C
from cim26.data import weather as W
from cim26.data.catalog import library, save_user_module
from cim26.data.supsi_field import load_field
from cim26.data.supsi_lab import read_iec61853_xlsx
from cim26.pvcore.models import MODEL_IDS, MODEL_INFO, availability
from cim26.pvcore.module import KIND_DATASHEET, KIND_EXPERIMENTAL, ModuleSpec, validate_module
from cim26.pvcore.sdm import STATUS_LABELS, SDMReference
from cim26.report.figures import modelos_iv_figure, modelos_power_figure
from cim26.simulate import iv_curve_array, simulate, thermal_options

from . import charts
from .style import chip, lede, model_tag, note, provenance_kind

KIND_LABEL = {KIND_EXPERIMENTAL: ("laboratório", "ficha experimental SUPSI"),
              KIND_DATASHEET: ("medido", "datasheet comercial"), "usuario": ("manual", "módulo do usuário")}


@st.cache_data(show_spinner=False)
def _library() -> dict:
    return {k: v.to_dict() for k, v in library().items()}


@st.cache_data(show_spinner=False)
def _field() -> pd.DataFrame:
    return load_field()[0]


@st.cache_data(show_spinner="Resolvendo as 5 equações de De Soto…")
def _classical(mdict: dict):
    ref, rep = calibrate_classical(ModuleSpec.from_dict(mdict))
    return ref.to_dict(), rep.to_dict()


@st.cache_data(show_spinner="Ajuste multiponto com 66 medições de laboratório (≈10 s)…")
def _multipoint(mdict: dict):
    lab = read_iec61853_xlsx()
    ref, rep = calibrate_multipoint(lab.long, ModuleSpec.from_dict(mdict))
    d = rep.to_json_dict()
    return ref.to_dict(), d


def _fmt(v, nd=3, unit=""):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:.{nd}f}{unit}" if isinstance(v, float) else f"{v}{unit}"


# ---------------------------------------------------------------------------
@st.dialog("Módulo comercial", width="large")
def module_dialog(base: ModuleSpec | None):
    st.caption("Valores de datasheet em STC. Campos vazios ficam indisponíveis (nunca são inventados).")
    b = base or ModuleSpec(id="", kind="usuario", technology="Mono-Si", p_stc_W=400.0)
    c1, c2, c3 = st.columns(3)
    mid = c1.text_input("Identificador", value=(b.id + "_editado") if base else "")
    manu = c2.text_input("Fabricante", value=b.manufacturer or "")
    model = c3.text_input("Modelo", value=b.model or "")
    tech = c1.selectbox("Tecnologia", ["Mono-Si", "Mono-PERC", "Poly-Si", "CdTe", "CIGS", "Outra"],
                        index=["Mono-Si", "Mono-PERC", "Poly-Si", "CdTe", "CIGS", "Outra"].index(b.technology)
                        if b.technology in ["Mono-Si", "Mono-PERC", "Poly-Si", "CdTe", "CIGS"] else 0)

    def num(col, label, val, fmt="%.4f"):
        return col.number_input(label, value=None if val is None else float(val), format=fmt, placeholder="não informado")

    p = num(c2, "Pmax STC [W]", b.p_stc_W, "%.2f")
    voc = num(c3, "Voc [V]", b.v_oc_V); isc = num(c1, "Isc [A]", b.i_sc_A)
    vmp = num(c2, "Vmp [V]", b.v_mp_V); imp = num(c3, "Imp [A]", b.i_mp_A)
    ns = c1.number_input("Ns (células em série)", value=b.n_cells_series, min_value=1, step=1, placeholder="não informado")
    a = num(c2, "α_Isc [%/°C]", b.alpha_isc_pct_C); be = num(c3, "β_Voc [%/°C]", b.beta_voc_pct_C)
    g = num(c1, "γ_Pmax [%/°C]", b.gamma_pmax_pct_C); noct = num(c2, "NOCT [°C]", b.noct_C, "%.1f")
    L = num(c3, "Comprimento [m]", b.length_m); Wd = num(c1, "Largura [m]", b.width_m)
    src = st.text_input("Fonte (datasheet, versão, URL)", value=b.source if base else "")
    m = ModuleSpec(id=mid or "novo_modulo", kind="usuario", technology=tech, p_stc_W=p or 0.0, v_oc_V=voc, i_sc_A=isc,
                   v_mp_V=vmp, i_mp_A=imp, n_cells_series=int(ns) if ns else None, alpha_isc_pct_C=a,
                   beta_voc_pct_C=be, gamma_pmax_pct_C=g, noct_C=noct, length_m=L, width_m=Wd,
                   manufacturer=manu or None, model=model or None, source=src or "inserido pelo usuário")
    issues = validate_module(m)
    for lvl, msg in issues:
        (st.error if lvl == "erro" else st.warning)(msg)
    if st.button("Salvar módulo", type="primary", disabled=any(l == "erro" for l, _ in issues) or not mid):
        path = save_user_module(m)
        _library.clear()
        st.session_state["mod_id"] = m.id
        st.toast(f"Módulo salvo em {path.name}")
        st.rerun()


# ---------------------------------------------------------------------------
def _weather_controls(module: ModuleSpec) -> W.WeatherSeries | None:
    src = st.radio("Fonte", ["SUPSI 2019 (medido)", "CSV próprio", "Perfil sintético (legado)", "Condição manual"],
                   horizontal=False, key="wx_src", label_visibility="collapsed")
    try:
        if src.startswith("SUPSI"):
            f = _field()
            days = sorted(f["timestamp"].dt.date.astype(str).unique())
            sel = st.multiselect("Dias", days, default=[days[days.index("2019-05-14")] if "2019-05-14" in days else days[0]],
                                 max_selections=10)
            return W.supsi_days(f, sel) if sel else None
        if src == "CSV próprio":
            up = st.file_uploader("CSV com timestamp e irradiância", type=["csv", "txt"])
            if up is None:
                st.caption("Separador detectado automaticamente; vírgula decimal aceita.")
                return None
            raw = pd.read_csv(up, sep=None, engine="python")
            cols = list(raw.columns)
            c1, c2 = st.columns(2)
            ts = c1.selectbox("Coluna de tempo", cols)
            gcol = c2.selectbox("Coluna de irradiância", cols, index=min(1, len(cols) - 1))
            kind = st.radio("Essa irradiância é…", ["POA (no plano do módulo)", "GHI (horizontal global)"], horizontal=True)
            horiz = False
            if kind.startswith("GHI"):
                horiz = st.checkbox("Módulo instalado na horizontal (inclinação 0°) → POA = GHI")
                if not horiz:
                    st.error("GHI não é POA. A transposição para plano inclinado não está implementada; "
                             "forneça POA medida ou declare o módulo horizontal.")
                    return None
            tcol = st.selectbox("Coluna de temperatura (opcional)", ["—"] + cols)
            tkind = st.radio("Tipo de temperatura", ["Tamb", "Tmod", "Tcell"], horizontal=True) if tcol != "—" else None
            wcol = st.selectbox("Coluna de vento (opcional)", ["—"] + cols)
            return W.from_dataframe(raw, ts, gcol, "GHI" if kind.startswith("GHI") else "POA", horizontal=horiz,
                                    temp_col=None if tcol == "—" else tcol, temp_kind=tkind,
                                    wind_col=None if wcol == "—" else wcol)
        if src.startswith("Perfil"):
            c1, c2 = st.columns(2)
            prof = c1.selectbox("Perfil", W.SYNTHETIC_PROFILES, index=2)
            season = c2.selectbox("Estação", W.SEASONS)
            dur = c1.number_input("Horizonte [min]", 10, 60 * 24 * 7, 1440, step=60)
            step = c2.number_input("Passo [min]", 1, 60, 1)
            gpk = c1.number_input("Pico de irradiância [W/m²] (0 = padrão)", 0.0, 1400.0, 0.0, step=50.0)
            seed = c2.number_input("Semente", 0, 10**6, 42)
            return W.synthetic(prof, season, duration_min=int(dur), step_min=int(step), g_peak=gpk or None, seed=int(seed))
        c1, c2 = st.columns(2)
        g = c1.number_input("Gpoa [W/m²]", 0.0, 1500.0, 800.0, step=50.0)
        tk = c2.selectbox("Temperatura informada", ["Tamb", "Tmod", "Tcell"])
        t = c1.number_input(f"{tk} [°C]", -30.0, 90.0, 25.0, step=1.0)
        dur = c2.number_input("Duração [min]", 1, 1440, 60)
        wind = c1.number_input("Vento [m/s]", 0.0, 30.0, 1.0) if tk == "Tamb" else None
        return W.manual(g, t, tk, duration_min=int(dur), wind=wind)
    except ValueError as exc:
        st.error(str(exc))
        return None


def _sdm_panel(module: ModuleSpec) -> SDMReference | None:
    key = f"sdm::{module.id}"
    refs = st.session_state.setdefault("sdm_refs", {})
    method = None
    if module.kind == KIND_EXPERIMENTAL:
        method = "multiponto"
        st.markdown(f"{chip('laboratório', 'calibração multiponto')} 66 medições IEC 61853-1 "
                    "(22 G–T × Pmp, Isc, Voc); sem Ns, Vmp ou Imp.", unsafe_allow_html=True)
    elif not module.classical_sdm_inputs_missing():
        method = "classico"
        st.markdown(f"{chip('medido', 'calibração clássica')} Isc, Voc, MPP, dP/dV=0 e β_Voc do datasheet "
                    "(De Soto, 5 equações).", unsafe_allow_html=True)
    else:
        st.warning("SDM indisponível: faltam " + ", ".join(module.classical_sdm_inputs_missing())
                   + " no datasheet e não há matriz de laboratório para este módulo.")
        return None
    saved = list_calibrations(module.id)
    c1, c2 = st.columns([1, 1.6])
    if c1.button("Estimar parâmetros SDM", type="primary", key=f"est_{module.id}", width="stretch"):
        if method == "classico":
            refs[key] = _classical(module.to_dict())
        else:
            refs[key] = _multipoint(module.to_dict())
    if saved and key not in refs:
        if c2.button(f"Carregar identificação salva ({saved[0]['saved_utc']})", key=f"load_{module.id}"):
            refs[key] = (saved[0]["sdm_reference"], saved[0]["report"])
    if key not in refs:
        st.caption("Os parâmetros não são estimados automaticamente; nenhuma calibração é refeita dentro das rodadas.")
        return None
    ref_d, rep = refs[key]
    ref = SDMReference.from_dict(ref_d)
    with st.container(border=True):
        if method == "classico":
            ok = rep.get("success")
            (st.success if ok else st.error)(f"{'Convergiu' if ok else 'Não convergiu'} · custo {rep['cost']:.2e} · "
                                             f"{rep['n_iter']} avaliações · {rep['elapsed_s']:.2f} s")
            st.dataframe(pd.DataFrame({"equação": list(rep["residuals"]), "resíduo normalizado": list(rep["residuals"].values())}),
                         hide_index=True, width="stretch")
            sc = rep["stc_check"]
            st.caption(f"STC previsto: Pmp {sc['Pmp_W']:.2f} W (Vmp·Imp datasheet {sc['VmpImp_datasheet_W']:.2f} W; "
                       f"placa {sc['Pnom_datasheet_W']:.0f} W).")
        else:
            st.success(f"Melhor de {len(rep['starts'])} arranques · custo {rep['best_cost']:.3e} · "
                       f"condição do Jacobiano {rep['condition_number']:.0f} · {rep['elapsed_s']:.1f} s")
            st.dataframe(pd.DataFrame(rep["lab_metrics"]).round(4), hide_index=True, width="stretch")
            ic = rep["implied_coefficients"]
            st.caption("Coeficientes implícitos do SDM vs medidos [%/°C]: "
                       + "; ".join(f"{k.split('_')[0]} {v['modelo_pct_C']:.3f} vs {v['medido_pct_C']:.3f}" for k, v in ic.items()))
        params = pd.DataFrame({"parâmetro": ["IL_ref [A]", "I0_ref [A]", "Rs [Ω]", "Rsh_ref [Ω]", "a_ref [V]", "n", "Ns"],
                               "valor": [f"{ref.IL_ref:.5f}", f"{ref.I0_ref:.4e}", f"{ref.Rs:.5f}", f"{ref.Rsh_ref:.2f}",
                                         f"{ref.a_ref:.5f}", "—" if ref.n is None else f"{ref.n:.4f}",
                                         "—" if ref.n_cells is None else str(ref.n_cells)]})
        st.dataframe(params, hide_index=True, width="stretch")
        if st.button("Salvar identificação", key=f"save_{module.id}"):
            p = save_calibration(ref, rep, module.id)
            st.toast(f"Identificação salva: {p.name}")
    return ref


# ---------------------------------------------------------------------------
def render():
    st.title("Modelos")
    lede("Simulação de potência DC com os quatro modelos sobre um módulo da biblioteca, um arranjo série × paralelo "
         "e entradas meteorológicas declaradas. Este modo não altera o ensaio congelado do Artigo.")
    lib = {k: ModuleSpec.from_dict(v) for k, v in _library().items()}
    left, right = st.columns([1, 2.3], gap="large")

    with left:
        st.subheader("Módulo")
        ids = list(lib)
        default = st.session_state.get("mod_id", "CS6K-275P" if "CS6K-275P" in ids else ids[0])
        mod_id = st.selectbox("Módulo", ids, index=ids.index(default) if default in ids else 0,
                              format_func=lambda k: f"{lib[k].label}" + ("  (SUPSI, laboratório)" if lib[k].kind == KIND_EXPERIMENTAL else ""),
                              label_visibility="collapsed")
        st.session_state["mod_id"] = mod_id
        m = lib[mod_id]
        kind, kind_txt = KIND_LABEL.get(m.kind, ("manual", m.kind))
        st.markdown(chip(kind, kind_txt) + chip("indisponível", m.technology), unsafe_allow_html=True)
        spec = pd.DataFrame({"grandeza": ["Pstc", "Voc", "Isc", "Vmp", "Imp", "Ns", "α_Isc", "β_Voc", "γ_Pmax", "NOCT"],
                             "valor": [_fmt(m.p_stc_W, 2, " W"), _fmt(m.v_oc_V, 3, " V"), _fmt(m.i_sc_A, 3, " A"),
                                       _fmt(m.v_mp_V, 3, " V"), _fmt(m.i_mp_A, 3, " A"), _fmt(m.n_cells_series),
                                       _fmt(m.alpha_isc_pct_C, 4, " %/°C"), _fmt(m.beta_voc_pct_C, 4, " %/°C"),
                                       _fmt(m.gamma_pmax_pct_C, 3, " %/°C"), _fmt(m.noct_C, 1, " °C")]})
        st.dataframe(spec, hide_index=True, width="stretch", height=388)
        st.caption(f"Fonte: {m.source}. Pstc = {m.p_stc_meaning}.")
        b1, b2 = st.columns(2)
        if b1.button("Novo módulo", width="stretch"):
            module_dialog(None)
        if b2.button("Copiar e editar", width="stretch", disabled=m.kind == KIND_EXPERIMENTAL,
                     help="A ficha SUPSI é experimental e não pode virar datasheet comercial."):
            module_dialog(m)

        st.subheader("Arranjo")
        c1, c2 = st.columns(2)
        ns = c1.number_input("Módulos em série (Ns)", 1, 200, 1)
        npar = c2.number_input("Strings em paralelo (Np)", 1, 500, 1)
        st.caption(f"Potência instalada: {m.p_stc_W * ns * npar / 1000:.3f} kWp ({ns * npar} módulos). "
                   "Sem perdas de mismatch, cabeamento ou conversão.")

        st.subheader("Meteorologia")
        wx = _weather_controls(m)
        strategy, dT = None, SANDIA_DELTA_T_DEFAULT_C
        if wx is not None:
            opts = thermal_options(wx, m)
            st.subheader("Temperatura")
            if not opts:
                st.info("Sem temperatura: somente M1 pode ser avaliado.")
            else:
                labels = {o[0]: o[1] + ("" if o[2] else f" — indisponível: {o[3]}") for o in opts}
                usable = [o[0] for o in opts if o[2]]
                if usable:
                    strategy = st.radio("Estratégia térmica", usable, format_func=lambda s: labels[s])
                for o in opts:
                    if not o[2]:
                        st.caption(labels[o[0]])
                dT = st.number_input("ΔT célula–módulo a 1000 W/m² [°C]", 0.0, 10.0, SANDIA_DELTA_T_DEFAULT_C, 0.5,
                                     help="Sandia eq. 23 (IEA PVPS T13-20:2020, p. 99). Hipótese, não medida.")
                st.markdown(chip("hipótese", f"ΔT = {dT:g} °C"), unsafe_allow_html=True)

    with right:
        st.subheader("Modelo")
        sdm_ref = st.session_state.get("sdm_refs", {}).get(f"sdm::{m.id}")
        sdm_ref = SDMReference.from_dict(sdm_ref[0]) if sdm_ref else None
        avs = {k: availability(k, m, sdm_ref if k == "M4" else None) for k in MODEL_IDS}
        if "M4" in avs and not avs["M4"].available and (m.kind == KIND_EXPERIMENTAL or not m.classical_sdm_inputs_missing()):
            avs["M4"].reason = "Calibrável: use “Estimar parâmetros SDM”."
        sel = st.segmented_control("Modelo", MODEL_IDS, default="M4" if sdm_ref else "M2", key="model_sel",
                                   format_func=lambda k: f"{k} · {MODEL_INFO[k].short}", label_visibility="collapsed")
        sel = sel or "M1"
        st.markdown("".join(f'<div class="cim-avail">{model_tag(k)} — '
                            f'<span class="{"" if avs[k].available else "no"}">{avs[k].reason}</span></div>'
                            for k in MODEL_IDS), unsafe_allow_html=True)
        st.caption(f"{MODEL_INFO[sel].equation}")
        if sel == "M4":
            sdm_ref = _sdm_panel(m)

        if wx is None:
            st.info("Defina a entrada meteorológica para simular.")
            return
        st.markdown(" ".join([chip(wx.origin, f"G: {wx.origin} (POA)")] +
                             [chip(provenance_kind(wx.origin), f"temperaturas fornecidas: {', '.join(wx.temperature_kinds()) or 'nenhuma'}")]),
                    unsafe_allow_html=True)
        for n in wx.notes:
            note(n)
        compare = st.toggle("Sobrepor os demais modelos disponíveis", value=False)
        run_models = MODEL_IDS if compare else [sel]
        if len(wx) > 20000 and "M4" in run_models and not st.button("Simular (série longa com SDM)"):
            st.info(f"{len(wx)} amostras: o SDM leva ≈{len(wx) * 0.0007:.0f} s. Clique para simular.")
            return
        key = hashlib.sha256(json.dumps([m.to_dict(), wx.description, len(wx), float(np.nansum(wx.g_poa_Wm2)),
                                         strategy, dT, int(ns), int(npar), list(run_models),
                                         None if sdm_ref is None else sdm_ref.to_dict()], default=str).encode()).hexdigest()
        cache = st.session_state.setdefault("sim_cache", {})
        if key not in cache:
            with st.spinner("Simulando…"):
                cache.clear()
                cache[key] = simulate(m, wx, run_models, sdm_ref, strategy, dT, int(ns), int(npar))
        res = cache[key]
        if not res.statuses[sel].available:
            st.warning(f"{sel} indisponível: {res.statuses[sel].reason}")
            return
        k = res.kpis.set_index("modelo").loc[sel]
        c = st.columns(4)
        c[0].metric("P máx do arranjo", f"{k.P_max_arranjo_W / 1000:.3f} kW" if k.P_max_arranjo_W >= 1000 else f"{k.P_max_arranjo_W:.1f} W")
        c[1].metric("Energia (período válido)", f"{k.E_periodo_valido_kWh:.3f} kWh")
        c[2].metric("Horas válidas", f"{k.horas_validas_h:.2f} h")
        c[3].metric("Amostras válidas", f"{int(k.amostras_validas)} / {int(k.amostras_total)}")
        st.caption(f"Energia por trapézios somente entre amostras finitas com Δt ≤ 1,5 × passo nominal "
                   f"({k.passo_nominal_min:g} min); lacunas e noite não são interpoladas.")
        preds = {mm: res.table[f"P_{mm}_arranjo_W"] for mm in run_models if res.statuses[mm].available}
        obs = None
        st.plotly_chart(charts.power_timeseries(res.table["timestamp"], obs, preds, 1.5 * k.passo_nominal_min,
                                                title=f"Potência DC do arranjo ({ns}×{npar})"), config=charts.CONFIG)
        stc = res.table[f"status_{sel}"].value_counts()
        bad = {STATUS_LABELS.get(int(s), s): int(n) for s, n in stc.items() if int(s) not in (0, 1)}
        if bad:
            st.warning("Avisos de validade: " + "; ".join(f"{v} amostra(s) — {k_}" for k_, v in bad.items()))

        figs = {}
        if sel == "M4" and sdm_ref is not None:
            st.subheader("Curvas I–V e P–V (somente SDM)")
            valid_idx = np.where(np.isfinite(res.table["P_M4_arranjo_W"]) & (res.table["g_poa_Wm2"] > 1))[0]
            if len(valid_idx):
                i = st.select_slider("Instante", options=list(valid_idx),
                                     value=int(valid_idx[np.nanargmax(res.table["P_M4_arranjo_W"].to_numpy()[valid_idx])]),
                                     format_func=lambda j: str(res.table["timestamp"].iloc[j]))
                row = res.table.iloc[i]
                V, I, P, mpp = iv_curve_array(sdm_ref, row.g_poa_Wm2, row.t_cell_C, int(ns), int(npar))
                st.plotly_chart(charts.iv_chart(V, I, P, mpp, f"G = {row.g_poa_Wm2:.0f} W/m², Tcell = {row.t_cell_C:.1f} °C"),
                                config=charts.CONFIG)
                figs["iv"] = modelos_iv_figure(V, I, P, mpp, f"G={row.g_poa_Wm2:.0f} W/m², Tcell={row.t_cell_C:.1f} °C")
        else:
            note("Curvas I–V/P–V elétricas existem apenas no SDM; M1–M3 não descrevem a curva.")

        st.subheader("Exportar")
        figs["potencia"] = modelos_power_figure(res.table, list(preds), f"{m.label} · {ns}×{npar}")
        c = st.columns(5)
        c[0].download_button("CSV de resultados", res.table.to_csv(index=False).encode(), "modelos_resultados.csv",
                             "text/csv", width="stretch")
        c[1].download_button("Potência SVG", figs["potencia"][0], "modelos_potencia.svg", "image/svg+xml", width="stretch")
        c[2].download_button("Potência PNG", figs["potencia"][1], "modelos_potencia.png", "image/png", width="stretch")
        if "iv" in figs:
            c[3].download_button("I–V SVG", figs["iv"][0], "modelos_iv.svg", "image/svg+xml", width="stretch")
            c[4].download_button("I–V PNG", figs["iv"][1], "modelos_iv.png", "image/png", width="stretch")
        with st.expander("Proveniência das condições"):
            st.json(res.provenance)
        with st.expander("Tabela completa"):
            st.dataframe(res.table, hide_index=True, width="stretch")
