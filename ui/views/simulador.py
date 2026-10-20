"""Simulador (modo Modelos): espaço de trabalho único — cartões → diálogos, resultados ao vivo."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import streamlit as st

from cim26.calibration.store import save_calibration
from cim26.data import weather as W
from cim26.data.catalog import save_user_module
from cim26.pvcore.models import MODEL_IDS, MODEL_INFO
from cim26.pvcore.module import KIND_DATASHEET, KIND_EXPERIMENTAL, ModuleSpec, validate_module
from cim26.pvcore.sdm import SDMReference
from cim26.report.figures import modelos_iv_figure, modelos_power_figure

from .. import charts, services
from .. import components as C
from ..theme import MODEL_COLORS

ss = st.session_state


def _f(x, d=2):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _module() -> ModuleSpec:
    lib = services.library()
    return lib.get(ss.sim_module) or lib[services.SUPSI_ID]


def _sdm_json(m: ModuleSpec) -> str | None:
    d = ss.sdm.get(m.id)
    return json.dumps(d, sort_keys=True, default=str) if d else None


def _weather_label(w: dict) -> tuple[str, str]:
    if w["source"] == "supsi":
        days = w["days"]
        a = pd.Timestamp(days[0]).strftime("%d/%m/%Y") if len(days) == 1 else f"{len(days)} dias SUPSI"
        return a, "SUPSI 2019 · medido (POA)"
    if w["source"] == "csv":
        return w.get("name", "CSV"), ("GHI → POA (horizontal)" if w.get("g_kind") == "GHI" else "POA") + " · medido"
    if w["source"] == "synthetic":
        return w["profile"], f"{w['season']} · {w['duration_min'] / 60:g} h · simulado"
    return f"{w['g']:g} W/m² · {w['t']:g} °C", f"condição manual ({w['t_kind']})"


# =========================================================================== diálogos
@st.dialog("Módulo fotovoltaico", width="large")
def dlg_module(focus_sdm: bool = False):
    lib = services.library()
    rows = pd.DataFrame([{"id": k, "Módulo": m.label, "Origem": {KIND_EXPERIMENTAL: "laboratório", KIND_DATASHEET: "Canadian Solar"}.get(m.kind, "meus módulos"),
                          "Tecnologia": m.technology, "Pstc [W]": m.p_stc_W, "SDM": "pronto" if k in ss.sdm else (services.sdm_method(m) or "indisponível")}
                         for k, m in lib.items()])
    cur = list(rows.id).index(ss.sim_module) if ss.sim_module in list(rows.id) else 0
    ev = st.dataframe(rows.drop(columns=["id"]), hide_index=True, height=250, on_select="rerun", selection_mode="single-row",
                      key="dlg_mod_tbl", width="stretch",
                      column_config={"Pstc [W]": st.column_config.NumberColumn(format="%.1f")})
    sel_rows = ev.selection.rows if ev and ev.selection else []
    mid = rows.id.iloc[sel_rows[0]] if sel_rows else rows.id.iloc[cur]
    m = lib[mid]
    c1, c2 = st.columns([1, 1.15], gap="large")
    with c1:
        C.show(f"<h4 style='margin:4px 0'>{C.esc(m.label)}</h4>" + C.spec_table([
            ("Pstc", f"{_f(m.p_stc_W)} W"), ("Voc", None if m.v_oc_V is None else f"{_f(m.v_oc_V)} V"), ("Isc", None if m.i_sc_A is None else f"{_f(m.i_sc_A)} A"),
            ("Vmp", None if m.v_mp_V is None else f"{_f(m.v_mp_V)} V"), ("Imp", None if m.i_mp_A is None else f"{_f(m.i_mp_A)} A"),
            ("Ns (células)", m.n_cells_series), ("α Isc", None if m.alpha_isc_pct_C is None else f"{_f(m.alpha_isc_pct_C, 3)} %/°C"),
            ("β Voc", None if m.beta_voc_pct_C is None else f"{_f(m.beta_voc_pct_C, 3)} %/°C"),
            ("γ Pmax", None if m.gamma_pmax_pct_C is None else f"{_f(m.gamma_pmax_pct_C, 3)} %/°C"), ("NOCT", None if m.noct_C is None else f"{_f(m.noct_C, 1)} °C")])
            + f"<p class='cim-notes' style='padding:0'>{C.esc(m.source)} · Pstc = {C.esc(m.p_stc_meaning)}</p>")
        st.download_button("Exportar ficha (JSON)", json.dumps(m.to_dict(), ensure_ascii=False, indent=2), f"{m.id}.json", "application/json",
                           icon=":material/download:", key="dlg_mod_dl")
    with c2:
        st.markdown("**Parâmetros do SDM (M4)**")
        method = services.sdm_method(m)
        if not method:
            C.alert(f"SDM indisponível: faltam {C.esc(', '.join(m.classical_sdm_inputs_missing()))} no datasheet e não há matriz de laboratório.")
        else:
            st.caption("Calibração multiponto com 66 medições IEC 61853-1, sem Ns, Vmp ou Imp (≈ 10 s)." if method == "multiponto"
                       else "Calibração clássica De Soto (5 equações) com Isc, Voc, MPP, dP/dV = 0 e β_Voc do datasheet.")
            b1, b2 = st.columns(2)
            if b1.button("Estimar parâmetros SDM", type="primary", icon=":material/wb_sunny:", key="dlg_sdm_go", width="stretch"):
                ss.sdm[m.id] = services.calibrate(json.dumps(m.to_dict(), sort_keys=True))
            saved = services.saved_calibration(m.id)
            if saved and b2.button("Carregar identificação salva", key="dlg_sdm_load", width="stretch"):
                ss.sdm[m.id] = saved
            d = ss.sdm.get(m.id)
            if d:
                r, rep = d["reference"], d["report"]
                if d["method"] == "classico":
                    C.alert(f"{'Convergiu' if rep['success'] else 'Não convergiu'} · custo {rep['cost']:.1e} · {rep['n_iter']} avaliações", "ok" if rep["success"] else "bad")
                else:
                    C.alert(f"{len(rep['starts'])} arranques no mesmo ótimo · condição do Jacobiano {rep['condition_number']:.0f} · {rep['elapsed_s']:.1f} s", "ok")
                C.show(C.spec_table([("IL_ref", f"{_f(r['IL_ref'], 4)} A"), ("I0_ref", f"{r['I0_ref']:.3e} A"), ("Rs", f"{_f(r['Rs'], 4)} Ω"),
                                     ("Rsh_ref", f"{_f(r['Rsh_ref'], 1)} Ω"), ("a_ref", f"{_f(r['a_ref'], 4)} V"),
                                     ("n", None if r.get("n") is None else _f(r["n"], 4)), ("Ns", r.get("n_cells"))]))
                if d["method"] == "multiponto":
                    st.dataframe(pd.DataFrame(rep["lab_metrics"]).round(4), hide_index=True, width="stretch")
                s1, s2 = st.columns(2)
                if s1.button("Salvar identificação", key="dlg_sdm_save", width="stretch"):
                    p = save_calibration(SDMReference.from_dict(r), rep, m.id)
                    st.toast(f"Identificação salva: {p.name}")
                s2.download_button("Baixar identificação (JSON)", json.dumps(d, ensure_ascii=False, indent=1, default=str),
                                   f"sdm_{m.id}.json", "application/json", key="dlg_sdm_dl", width="stretch")
    with st.expander("Novo módulo comercial (datasheet)", expanded=False):
        _module_form(m if m.kind != KIND_EXPERIMENTAL else None)
    up = st.file_uploader("Importar ficha de módulo (JSON exportado)", type=["json"], key="dlg_mod_up")
    if up is not None and st.button("Importar módulo", key="dlg_mod_imp"):
        try:
            mm = ModuleSpec.from_dict(json.loads(up.getvalue()))
            save_user_module(mm)
            services.refresh_library()
            st.toast(f"Módulo {mm.id} importado.")
        except Exception as exc:
            st.error(str(exc))
    if st.button("Usar este módulo", type="primary", key="dlg_mod_ok", width="stretch"):
        ss.sim_module = m.id
        if "M4" in ss.sim_models and m.id not in ss.sdm:
            ss.sim_models = [x for x in ss.sim_models if x != "M4"] or ["M2"]
            ss.sim_focus = ss.sim_models[0]
        st.rerun()


def _module_form(base: ModuleSpec | None):
    b = base or ModuleSpec(id="", kind="usuario", technology="Mono-Si", p_stc_W=400.0)
    with st.form("new_module", border=False):
        c = st.columns(3)
        mid = c[0].text_input("Identificador", value=f"{b.id}_editado" if base else "")
        manu = c[1].text_input("Fabricante", value=b.manufacturer or "")
        model = c[2].text_input("Modelo", value=b.model or "")
        techs = ["Mono-Si", "Mono-PERC", "Poly-Si", "CdTe", "CIGS"]
        tech = c[0].selectbox("Tecnologia", techs, index=techs.index(b.technology) if b.technology in techs else 0)

        def num(col, label, v, fmt="%.4f"):
            return col.number_input(label, value=None if v is None else float(v), format=fmt, placeholder="não informado")
        p = num(c[1], "Pmax STC [W]", b.p_stc_W, "%.2f"); voc = num(c[2], "Voc [V]", b.v_oc_V)
        isc = num(c[0], "Isc [A]", b.i_sc_A); vmp = num(c[1], "Vmp [V]", b.v_mp_V); imp = num(c[2], "Imp [A]", b.i_mp_A)
        ns = num(c[0], "Ns (células)", b.n_cells_series, "%.0f"); a = num(c[1], "α Isc [%/°C]", b.alpha_isc_pct_C); be = num(c[2], "β Voc [%/°C]", b.beta_voc_pct_C)
        g = num(c[0], "γ Pmax [%/°C]", b.gamma_pmax_pct_C); noct = num(c[1], "NOCT [°C]", b.noct_C, "%.1f"); L = num(c[2], "Comprimento [m]", b.length_m)
        wd = num(c[0], "Largura [m]", b.width_m); src = c[1].text_input("Fonte (datasheet/versão)", value=b.source if base else "")
        ok = st.form_submit_button("Validar e salvar", type="primary")
    if ok:
        mm = ModuleSpec(id=mid or "novo_modulo", kind="usuario", technology=tech, p_stc_W=p or 0.0, v_oc_V=voc, i_sc_A=isc, v_mp_V=vmp,
                        i_mp_A=imp, n_cells_series=int(ns) if ns else None, alpha_isc_pct_C=a, beta_voc_pct_C=be, gamma_pmax_pct_C=g,
                        noct_C=noct, length_m=L, width_m=wd, manufacturer=manu or None, model=model or None, source=src or "inserido pelo usuário")
        issues = validate_module(mm)
        for lvl, msg in issues:
            (st.error if lvl == "erro" else st.warning)(msg)
        if not any(l == "erro" for l, _ in issues) and mid:
            save_user_module(mm)
            services.refresh_library()
            ss.sim_module = mm.id
            st.toast("Módulo salvo (exporte o JSON para guardá-lo fora desta sessão).")
            st.rerun()


@st.dialog("Arranjo série × paralelo")
def dlg_array():
    m = _module()
    c1, c2 = st.columns(2)
    ns = c1.number_input("Módulos em série (Ns)", 1, 60, int(ss.sim_ns), key="dlg_ns")
    npar = c2.number_input("Strings em paralelo (Np)", 1, 60, int(ss.sim_np), key="dlg_np")
    C.show(C.array_grid(int(ns), int(npar)) + f"<p class='cim-notes' style='padding:0'>{ns * npar} módulos · {_f(m.p_stc_W * ns * npar / 1000)} kWp"
           + (f" · Voc do string ≈ {_f(m.v_oc_V * ns, 0)} V" if m.v_oc_V else "") + "<br>Módulos idênticos, sem mismatch, cabeamento ou conversão. "
           "As curvas I–V escalam tensão por Ns e corrente por Np.</p>")
    if st.button("Aplicar", type="primary", width="stretch", key="dlg_arr_ok"):
        ss.sim_ns, ss.sim_np = int(ns), int(npar)
        st.rerun()


@st.dialog("Clima e irradiância", width="large")
def dlg_weather():
    w = ss.sim_weather
    if "dlg_wx_src" not in ss:
        ss.dlg_wx_src = w["source"]
        ss.dlg_wx_days = list(w.get("days", ["2019-05-14"]))
    src = st.segmented_control("Fonte", ["supsi", "csv", "synthetic", "manual"], key="dlg_wx_src", label_visibility="collapsed",
                               format_func={"supsi": "SUPSI medido", "csv": "CSV próprio", "synthetic": "Sintético", "manual": "Manual"}.get)
    spec = None
    if src == "supsi":
        days = services.supsi_days()
        mx = float(days.h.max())

        def col(h):
            t = h / mx
            return f"rgb({round(255 - 13 * t)},{round(244 - 75 * t)},{round(214 - 214 * t)})"
        dd = {r.day: {"c": col(r.h), "t": f"{pd.Timestamp(r.day):%d/%m/%Y} · {r.h:.2f} kWh/m² · Gmax {r.g_max:.0f} W/m²"} for r in days.itertuples()}
        st.caption("Cor = irradiação POA do dia. Clique para escolher; Ctrl/⌘ + clique soma dias (até 10).")
        pick = C.calendar(sorted({d[:7] for d in dd}), dd, ss.dlg_wx_days, key="dlg_cal", multi=True,
                          legend=f"baixa <i style='background:{col(0)}'></i><i style='background:{col(mx / 2)}'></i><i style='background:{col(mx)}'></i> alta irradiação")
        if pick:
            day = pick["day"]
            cur = set(ss.dlg_wx_days)
            if pick.get("add"):
                cur.symmetric_difference_update({day})
                cur = cur or {day}
                if len(cur) > 10:
                    cur.discard(day)
            else:
                cur = {day}
            ss.dlg_wx_days = sorted(cur)
        st.markdown(f"**{len(ss.dlg_wx_days)} dia(s):** " + ", ".join(pd.Timestamp(d).strftime("%d/%m") for d in ss.dlg_wx_days))
        spec = {"source": "supsi", "days": ss.dlg_wx_days}
    elif src == "csv":
        up = st.file_uploader("CSV com tempo e irradiância", type=["csv", "txt"], key="dlg_csv")
        if up is not None:
            text = up.getvalue().decode("utf-8", errors="replace")
            try:
                raw = services.inspect_csv(text)
                cols = list(map(str, raw.columns))
                st.caption(f"{up.name} · {len(raw):,} linhas".replace(",", "."))
                c1, c2 = st.columns(2)
                ts = c1.selectbox("Tempo", cols, key="dlg_csv_ts")
                gcol = c2.selectbox("Irradiância", cols, index=min(1, len(cols) - 1), key="dlg_csv_g")
                kind = st.segmented_control("Essa irradiância é…", ["POA", "GHI"], key="dlg_csv_kind",
                                            format_func={"POA": "POA (plano do módulo)", "GHI": "GHI (horizontal)"}.get) or "POA"
                horiz = False
                if kind == "GHI":
                    C.alert("GHI não é POA. A transposição para plano inclinado não está implementada; só é possível usar GHI com o módulo na horizontal.")
                    horiz = st.checkbox("Módulo instalado na horizontal (inclinação 0°): POA = GHI", key="dlg_csv_h")
                c1, c2, c3 = st.columns(3)
                tcol = c1.selectbox("Temperatura (opcional)", ["—"] + cols, key="dlg_csv_t")
                tkind = c2.selectbox("Tipo", ["Tamb", "Tmod", "Tcell"], key="dlg_csv_tk")
                wcol = c3.selectbox("Vento (opcional)", ["—"] + cols, key="dlg_csv_w")
                spec = {"source": "csv", "name": up.name, "text": text, "ts_col": ts, "g_col": gcol, "g_kind": kind, "horizontal": horiz,
                        "t_col": None if tcol == "—" else tcol, "t_kind": tkind, "w_col": None if wcol == "—" else wcol}
            except Exception as exc:
                st.error(f"CSV ilegível: {exc}")
    elif src == "synthetic":
        c1, c2 = st.columns(2)
        prof = c1.selectbox("Perfil", W.SYNTHETIC_PROFILES, index=1, key="dlg_syn_p")
        season = c2.selectbox("Estação", W.SEASONS, key="dlg_syn_s")
        dur = c1.number_input("Horizonte [h]", 1, 168, 24, key="dlg_syn_d")
        step = c2.number_input("Passo [min]", 1, 60, 5, key="dlg_syn_st")
        gpk = c1.number_input("Pico [W/m²] (0 = padrão do legado)", 0, 1400, 0, step=50, key="dlg_syn_g")
        seed = c2.number_input("Semente", 0, 10**6, 42, key="dlg_syn_seed")
        C.alert("Perfil sintético do código legado; a irradiância gerada é tratada como POA simulada.", "info")
        spec = {"source": "synthetic", "profile": prof, "season": season, "duration_min": int(dur) * 60, "step_min": int(step),
                "g_peak": float(gpk) or None, "seed": int(seed)}
    elif src == "manual":
        g = st.slider("Irradiância POA [W/m²]", 0, 1300, 800, 10, key="dlg_man_g")
        c1, c2, c3 = st.columns(3)
        tk = c1.selectbox("Temperatura informada", ["Tamb", "Tmod", "Tcell"], key="dlg_man_tk")
        t = c2.number_input("Valor [°C]", -30.0, 90.0, 25.0, key="dlg_man_t")
        wind = c3.number_input("Vento [m/s]", 0.0, 30.0, 1.0, key="dlg_man_w")
        dur = st.number_input("Duração [min]", 1, 1440, 60, key="dlg_man_d")
        spec = {"source": "manual", "g": float(g), "t": float(t), "t_kind": tk, "duration_min": int(dur), "wind": float(wind)}
    if st.button("Aplicar", type="primary", width="stretch", key="dlg_wx_ok", disabled=spec is None):
        try:
            services.weather_from_spec(spec)
        except ValueError as exc:
            st.error(str(exc))
            return
        ss.sim_weather = spec
        for k in ("dlg_wx_src", "dlg_wx_days"):
            ss.pop(k, None)
        st.rerun()


@st.dialog("Modelo térmico")
def dlg_thermal(opts: list[dict], used: str | None):
    if not opts:
        C.alert("A entrada meteorológica atual não traz temperatura: somente M1 (que não usa temperatura) é avaliável.")
        return
    ok = [o for o in opts if o["ok"]]
    st.caption("M2 e M4 usam temperatura de célula (Tcell); M3 (Huld) usa a temperatura posterior do módulo (Tmod). As duas nunca são confundidas.")
    ids = [o["id"] for o in ok]
    strat = st.radio("Estratégia", ids, index=ids.index(used) if used in ids else 0, format_func=lambda i: next(o["label"] for o in ok if o["id"] == i),
                     key="dlg_th_s")
    for o in opts:
        if not o["ok"]:
            st.caption(f"Indisponível: {o['label']} — {o['why']}")
    dT = st.slider("ΔT célula–módulo a 1000 W/m² [°C] (hipótese)", 0.0, 10.0, float(ss.sim_thermal["delta_t"]), 0.5, key="dlg_th_dt")
    C.show(C.chip("hipotese", f"ΔT = {dT:g} °C · Sandia eq. 23 (IEA PVPS T13-20:2020, p. 99): Tcell = Tmod + G/1000·ΔT"))
    if st.button("Aplicar", type="primary", width="stretch", key="dlg_th_ok"):
        ss.sim_thermal = {"strategy": strat, "delta_t": float(dT)}
        st.rerun()


# =========================================================================== página
def render():
    m = _module()
    C.page_header("Simulador", "Modo Modelos · quatro modelos sobre qualquer módulo, arranjo e clima, com o mesmo motor físico do Artigo",
                  C.chip("lab" if m.kind == KIND_EXPERIMENTAL else "simulado", "ficha experimental" if m.kind == KIND_EXPERIMENTAL else "datasheet"))
    try:
        res = services.simulate(json.dumps(m.to_dict(), sort_keys=True), json.dumps(ss.sim_weather, sort_keys=True),
                                ss.sim_thermal["strategy"], ss.sim_thermal["delta_t"], int(ss.sim_ns), int(ss.sim_np), _sdm_json(m))
    except ValueError as exc:
        C.alert(f"Entrada inválida: {C.esc(str(exc))}", "bad")
        ss.sim_weather = {"source": "supsi", "days": ["2019-05-14"]}
        return
    th = res["thermal"]
    used = next((o for o in th["options"] if o["id"] == th["used"]), None)
    wa, wb = _weather_label(ss.sim_weather)
    tiles = [{"k": "modulo", "label": "Módulo", "title": m.label, "sub": f"{_f(m.p_stc_W, 0)} W · {m.technology}"},
             {"k": "arranjo", "label": "Arranjo", "title": f"{ss.sim_ns} × {ss.sim_np} módulos", "sub": f"{_f(res['p_inst_W'] / 1000)} kWp instalados"},
             {"k": "clima", "label": "Clima", "title": wa, "sub": wb},
             {"k": "temp", "label": "Temperatura", "title": used["label"].split(";")[0] if used else "sem temperatura",
              "sub": f"ΔT {_f(ss.sim_thermal['delta_t'], 1)} °C (hipótese)" if used else "apenas M1 avaliável"}]
    opened = C.config_tiles(tiles, key="sim_tiles")

    # disponibilidade (motor + motivo de calibração)
    av = services.model_availability(m, ss.sdm.get(m.id))
    for k in MODEL_IDS:
        if av[k]["available"] and not res["availability"][k]["available"]:
            av[k] = res["availability"][k]
    models = [x for x in ss.sim_models if av[x]["available"]] or ["M1"]
    if models != ss.sim_models:
        ss.sim_models = models
    if ss.sim_focus not in models:
        ss.sim_focus = models[0]
    toggle, blocked = C.model_pills([{"id": k, "short": MODEL_INFO[k].short, "color": MODEL_COLORS[k], "available": av[k]["available"],
                                      "reason": av[k]["reason"], "on": k in models} for k in MODEL_IDS], key="sim_pills",
                                    hint="Selecione um ou mais modelos para comparar.")
    if toggle:
        sel = list(models)
        if toggle in sel and len(sel) > 1:
            sel.remove(toggle)
        elif toggle not in sel:
            sel.append(toggle)
        ss.sim_models = [k for k in MODEL_IDS if k in sel]
        ss.sim_focus = toggle if toggle in sel else ss.sim_models[0]
        st.rerun()
    if opened == "modulo" or (blocked == "M4" and services.sdm_method(m)):
        dlg_module(focus_sdm=blocked == "M4")
    elif opened == "arranjo":
        dlg_array()
    elif opened == "clima":
        dlg_weather()
    elif opened == "temp":
        dlg_thermal(th["options"], th["used"])
    elif blocked:
        st.toast(av[blocked]["reason"])

    tab = res["table"]
    kp = res["kpis"].set_index("modelo")
    f = ss.sim_focus
    k = kp.loc[f] if f in kp.index else None
    items = []
    if k is not None:
        big = k.P_max_arranjo_W >= 1000
        when = pd.Timestamp(k.instante_P_max).strftime("%H:%M") if k.instante_P_max is not None and pd.notna(k.instante_P_max) else ""
        items += [{"key": "pmax", "label": f"Potência máxima · {f}", "value": k.P_max_arranjo_W / (1000 if big else 1), "decimals": 2 if big else 1,
                   "unit": "kW" if big else "W", "sub": f"às {when}" if when else "", "color": MODEL_COLORS[f]},
                  {"key": "e", "label": "Energia no período válido", "value": k.E_periodo_valido_kWh, "decimals": 3, "unit": "kWh",
                   "sub": f"{_f(k.E_periodo_valido_kWh / (res['p_inst_W'] / 1000))} kWh/kWp", "color": MODEL_COLORS[f]},
                  {"key": "h", "label": "Horas válidas integradas", "value": k.horas_validas_h, "decimals": 2, "unit": "h",
                   "sub": f"{int(k.amostras_validas)} de {int(k.amostras_total)} amostras · passo {_f(k.passo_nominal_min, 0)} min", "color": MODEL_COLORS[f]}]
        if res["has_obs"]:
            o, p = tab["P_obs_arranjo_W"].to_numpy(float), tab[f"P_{f}_arranjo_W"].to_numpy(float)
            ok = np.isfinite(o) & np.isfinite(p)
            nr = 100 * np.sqrt(np.mean((p[ok] - o[ok]) ** 2)) / np.mean(o[ok]) if ok.any() else np.nan
            t = pd.to_datetime(tab["timestamp"])
            dt = t.diff().dt.total_seconds().to_numpy()[1:] / 3600
            pair = ok[1:] & ok[:-1] & (dt <= 0.125)
            eo = np.sum(((o[1:] + o[:-1]) / 2 * dt)[pair]); ep = np.sum(((p[1:] + p[:-1]) / 2 * dt)[pair])
            items.append({"key": "x", "label": "Desvio frente à medida SUPSI", "value": float(nr), "decimals": 1, "unit": "% nRMSE",
                          "sub": f"energia {100 * (ep - eo) / eo:+.1f} % · Pm medida × {ss.sim_ns * ss.sim_np}".replace(".", ","), "color": MODEL_COLORS[f]})
        else:
            items.append({"key": "x", "label": "Desempenho específico" + (" (outro módulo: sem comparação)" if ss.sim_weather["source"] == "supsi" else ""),
                          "value": k.E_periodo_valido_kWh / (res["p_inst_W"] / 1000), "decimals": 2, "unit": "kWh/kWp",
                          "sub": f"{_f(res['p_inst_W'] / 1000)} kWp instalados", "color": MODEL_COLORS[f]})
    C.kpis(items, key="sim_kpis")

    gap = max(7.5, 1.5 * float(kp["passo_nominal_min"].iloc[0])) if len(kp) else 7.5
    with st.container(border=True):
        h1, h2 = st.columns([1.3, 2])
        h1.markdown(f"**Potência DC do arranjo**  \n<span style='color:var(--cim-muted);font-size:.83rem'>{C.esc(res['weather']['description'])} · "
                    f"{res['weather']['n']} amostras · lacunas > {_f(gap, 1)} min não são ligadas</span>", unsafe_allow_html=True)
        with h2:
            t1, t2, t3 = st.columns(3)
            t1.toggle("Irradiância (eixo direito)", key="sim_ov_g")
            t2.toggle("Temperatura de célula", key="sim_ov_t")
            if res["has_obs"]:
                t3.toggle("Medida SUPSI", key="sim_ov_obs")
        lines = [(charts.model_label(x), tab[f"P_{x}_arranjo_W"], MODEL_COLORS[x], 2.6 if x == f else 1.4)
                 for x in ss.sim_models if f"P_{x}_arranjo_W" in tab]
        fig = charts.power_series(tab["timestamp"], lines, gap, g=tab["g_poa_Wm2"] if ss.sim_ov_g else None,
                                  tcell=tab["t_cell_C"] if ss.sim_ov_t else None,
                                  obs=tab["P_obs_arranjo_W"] if res["has_obs"] and ss.sim_ov_obs else None,
                                  rangeslider=len(tab) > 300)
        charts.show(fig, "simulador_potencia", key="sim_power")
        figp = modelos_power_figure(tab, [x for x in ss.sim_models if f"P_{x}_arranjo_W" in tab], f"{m.label} · {ss.sim_ns}×{ss.sim_np}")
        e1, e2, e3, _ = st.columns([1, 1, 1, 3])
        e1.download_button("CSV", tab.to_csv(index=False).encode(), "simulador_resultados.csv", "text/csv", icon=":material/download:", width="stretch")
        e2.download_button("SVG", figp[0], "simulador_potencia.svg", "image/svg+xml", icon=":material/download:", width="stretch")
        e3.download_button("PNG", figp[1], "simulador_potencia.png", "image/png", icon=":material/download:", width="stretch")

    if "M4" in ss.sim_models and av["M4"]["available"] and m.id in ss.sdm and "P_M4_arranjo_W" in tab:
        _iv_card(m, tab)

    prov = res["provenance"]
    kind = lambda t: "hipotese" if "hip" in t else "estimado" if "estimad" in t else "medido" if "medid" in t else "simulado" if "simul" in t else "manual"  # noqa: E731
    C.show("<div style='display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-top:10px;font-size:.8rem;color:var(--cim-muted)'>Proveniência: "
           + " ".join(C.chip(kind(str(prov[k])), f"{lab}: {str(prov[k]).split(':')[0]}") for k, lab in (("g_poa_Wm2", "G"), ("t_module_C", "Tmod"), ("t_cell_C", "Tcell")) if k in prov) + "</div>")
    warn = [f"{x}: {n} amostra(s) — {lab}" for x, st_ in res["status"].items() if x in ss.sim_models for lab, n in st_.items() if lab != "ok" and not lab.startswith("G=0")]
    C.notes([C.esc(n) for n in res["notes"]] + [f"<span style='color:var(--cim-warn)'>{C.esc(w)}</span>" for w in warn]
            + ["Arranjo ideal: Ns·Np módulos idênticos, sem mismatch, cabeamento ou conversão. Energia por trapézios somente entre amostras válidas."])


def _iv_card(m: ModuleSpec, tab: pd.DataFrame):
    p = tab["P_M4_arranjo_W"].to_numpy(float)
    idx = np.where(np.isfinite(p) & (tab["g_poa_Wm2"].to_numpy(float) > 5))[0]
    if not len(idx):
        return
    if len(idx) > 72:
        idx = idx[np.linspace(0, len(idx) - 1, 72).round().astype(int)]
    g = tuple(float(x) for x in tab["g_poa_Wm2"].to_numpy()[idx])
    t = tuple(float(x) for x in tab["t_cell_C"].to_numpy()[idx])
    frames = services.iv_frames(_sdm_json(m), g, t, int(ss.sim_ns), int(ss.sim_np))
    multi_day = pd.to_datetime(tab["timestamp"]).dt.date.nunique() > 1
    labels = [f"{pd.Timestamp(tab['timestamp'].iloc[i]):{'%d/%m %H:%M' if multi_day else '%H:%M'}} · {gi:.0f} W/m²" for i, gi in zip(idx, g)]
    start = int(np.nanargmax([fr["mpp"]["Pmp"] for fr in frames]))
    vmax = max(max(fr["V"]) for fr in frames) * 1.05 if frames else 50
    imax = max(max(fr["I"]) for fr in frames) * 1.15 if frames else 10
    pmax = max(fr["mpp"]["Pmp"] for fr in frames) * 1.25 if frames else 300
    with st.container(border=True):
        st.markdown("**Curvas I–V e P–V do arranjo** " + C.chip("lab", "somente SDM") + "  \n<span style='color:var(--cim-muted);font-size:.83rem'>"
                    "Reproduza o dia: o SDM recalcula a curva em cada instante (G, Tcell). A animação roda no navegador.</span>", unsafe_allow_html=True)
        charts.show(charts.iv_animation(frames, labels, vmax, imax, pmax, start), "iv_sdm", key="sim_iv")
        fr = frames[start]
        svg, png = modelos_iv_figure(np.asarray(fr["V"]), np.asarray(fr["I"]), np.asarray(fr["P"]), fr["mpp"], labels[start])
        c1, c2, _ = st.columns([1, 1, 4])
        c1.download_button("I–V SVG (pico)", svg, "iv_sdm.svg", "image/svg+xml", icon=":material/download:", width="stretch")
        c2.download_button("I–V PNG (pico)", png, "iv_sdm.png", "image/png", icon=":material/download:", width="stretch")
