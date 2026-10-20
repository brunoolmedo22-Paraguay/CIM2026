"""Artigo · Dados e qualidade: cobertura, anomalias físicas, explorador diário e laboratório."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from cim26.data.supsi_field import AVAILABLE_MONTHS

from .. import charts, services
from .. import components as C

ss = st.session_state
ML = {m: ["jan", "fev", "mar", "abr", "mai", "jun"][int(m[-2:]) - 1] for m in AVAILABLE_MONTHS}
POL = {"sinalizar": "apenas sinalizar", "excluir_erros": "excluir erros", "excluir_erros_suspeitos": "excluir erros e suspeitas"}


def render():
    C.page_header("Dados e qualidade", "Artigo · conjunto de validação SUPSI 2019 e caracterização IEC 61853",
                  C.chip("medido", "campo 2019") + C.chip("lab", "laboratório"))
    C.show('<p class="cim-lede">O conjunto de validação é independente da calibração. Antes de comparar modelos, esta página mostra o que o '
           'dataset contém: cobertura, exclusões e <b>inconsistências físicas nas próprias medições</b> — potência sem irradiância, '
           'Isc incoerente com Gpoa, saltos de temperatura.</p>')
    with st.container(border=True):
        c1, c2, c3 = st.columns([1.5, 1, 1.4])
        c1.pills("Meses", AVAILABLE_MONTHS, selection_mode="multi", key="dq_months", format_func=ML.get)
        c2.segmented_control("Limiar Gpoa", [50, 100, 200], key="dq_g", format_func=lambda g: f"≥ {g} W/m²")
        c3.segmented_control("Anomalias", list(POL), key="dq_policy", format_func=POL.get)
    months = tuple(sorted(ss.dq_months)) or AVAILABLE_MONTHS
    g = float(ss.dq_g or 100)
    policy = ss.dq_policy or "sinalizar"
    v = services.quality_views(months, g, "A_tmod_medida", policy)
    tot = v["monthly"].iloc[-1]
    an = v["anomalies"]
    nbad = int(an[an.severidade != "condicao"].n_elegiveis.sum())
    C.kpis([{"key": "n", "label": "Registros lidos", "value": float(tot.n_total), "decimals": 0, "sub": "linhas originais, nenhuma apagada"},
            {"key": "e", "label": "Elegíveis (máscara comum)", "value": float(tot.n_elegivel), "decimals": 0,
             "sub": f"{100 * tot.n_elegivel / tot.n_total:.1f} % · mesma máscara p/ 4 modelos".replace(".", ",")},
            {"key": "p", "label": "Pares integráveis", "value": float(tot.pares_validos), "decimals": 0,
             "sub": f"{float(tot.horas_cobertas_pares_validos):.1f} h cobertas".replace(".", ",")},
            {"key": "x", "label": "Excluídas", "value": float(tot.n_total - tot.n_elegivel), "decimals": 0, "sub": "NaN na fonte, G abaixo do limiar…"},
            {"key": "a", "label": "Marcações de anomalia", "value": float(nbad), "decimals": 0, "sub": "erro + suspeita (podem se sobrepor)", "color": "#B83A3A"}],
           key="dq_kpis")
    c1, c2 = st.columns([1.05, 1], gap="medium")
    with c1:
        C.anomaly_list(an.to_dict("records"))
    with c2:
        with st.container(border=True):
            st.markdown("**Coerência Isc × Gpoa** <span style='color:var(--cim-muted);font-size:.8rem'>(vermelho = A05)</span>", unsafe_allow_html=True)
            charts.show(charts.hist_band(v["isc_ratio"], 0.4, 1.6, (0.8, 1.2), "Isc / (Isc_STC · G/1000)"), "coerencia_isc", key="dq_h1")
            st.markdown("**Razão de desempenho instantânea** <span style='color:var(--cim-muted);font-size:.8rem'>(vermelho = A03/A04)</span>", unsafe_allow_html=True)
            charts.show(charts.hist_band(v["pr"], 0.2, 1.8, (0.5, 1.25), "Pm / (Pstc · G/1000)"), "razao_desempenho", key="dq_h2")
    with st.expander("Resumo mensal e motivos de exclusão"):
        st.dataframe(v["monthly"], hide_index=True, width="stretch")

    C.sec("Explorar um dia", "cor do calendário = amostras com anomalia (erro ou suspeita) na máscara")
    days = v["days"]
    mxa = max(1, int(days.n_anom.max()))
    col = lambda n: "#DCEFE6" if n == 0 else f"rgba(184,58,58,{0.18 + 0.82 * (n / mxa) ** 0.5:.2f})"  # noqa: E731
    dd = {r.day: {"c": col(r.n_anom), "t": f"{pd.Timestamp(r.day):%d/%m/%Y} · {r.n_el}/{r.n} elegíveis · {r.n_anom} com anomalia"} for r in days.itertuples()}
    if ss.dq_day not in dd:
        ss.dq_day = next(iter(dd))
    with st.container(border=True):
        pick = C.calendar(sorted({d[:7] for d in dd}), dd, [ss.dq_day], key="dq_cal",
                          legend="<i style='background:#DCEFE6'></i> sem anomalias <i style='background:rgba(184,58,58,.35)'></i>"
                                 "<i style='background:rgba(184,58,58,1)'></i> mais anomalias · clique em um dia")
    if pick and pick.get("day") != ss.dq_day:
        ss.dq_day = pick["day"]
        st.rerun()
    q = services.quality(months, g, "A_tmod_medida", policy)
    d = q[q["timestamp"].dt.date.astype(str) == ss.dq_day]
    with st.container(border=True):
        h1, h2 = st.columns([1.2, 2])
        h1.markdown(f"**{pd.Timestamp(ss.dq_day):%d/%m/%Y}**  \n<span style='color:var(--cim-muted);font-size:.83rem'>{len(d)} registros · "
                    f"{int(d.eligible.sum())} elegíveis · {int((d.anom_codes != '').sum())} com marcação</span>", unsafe_allow_html=True)
        with h2:
            t1, t2, t3 = st.columns(3)
            t1.toggle("Irradiância (eixo direito)", key="dq_show_g")
            t2.toggle("Isc × escala", key="dq_show_isc", help="Isc convertida em irradiância equivalente: Isc·1000/Isc_STC")
            t3.toggle("Temperaturas", key="dq_show_t")
        charts.show(charts.day_explorer(d, ss.dq_show_g, ss.dq_show_isc, ss.dq_show_t), f"dia_{ss.dq_day}", key="dq_day_chart")
        bad = d[d.anom_codes != ""]
        if len(bad):
            st.dataframe(bad[["timestamp", "p_mpp_measured_W", "g_poa_Wm2", "pr_inst", "isc_ratio", "anom_codes", "anom_severidade", "eligible",
                              "source_file", "source_row"]], hide_index=True, width="stretch",
                         column_config={"timestamp": st.column_config.DatetimeColumn("Hora", format="HH:mm"),
                                        "p_mpp_measured_W": st.column_config.NumberColumn("Pm [W]", format="%.1f"),
                                        "g_poa_Wm2": st.column_config.NumberColumn("Gpoa [W/m²]", format="%.0f"),
                                        "pr_inst": st.column_config.NumberColumn("Pm/(Pstc·G)", format="%.2f"),
                                        "isc_ratio": st.column_config.NumberColumn("Isc/(Isc_STC·G)", format="%.2f"),
                                        "anom_codes": "Marcações", "anom_severidade": "Severidade", "eligible": "Na máscara",
                                        "source_file": "Arquivo", "source_row": "Linha"})
        else:
            C.alert("Nenhuma marcação neste dia.", "info")

    C.sec("Laboratório SUPSI (IEC 61853-1)", "fonte exclusiva da calibração do SDM")
    L = services.lab_view()
    cols = st.columns(3)
    for col_, (var, unit, dg) in zip(cols, (("Pmp", "W", 1), ("Isc", "A", 2), ("Voc", "V", 2))):
        with col_, st.container(border=True):
            charts.show(charts.heat_matrix(L["matrices"][var], f"{var} [{unit}]", dg), f"lab_{var}", key=f"lab_{var}")
    c1, c2 = st.columns(2)
    with c1:
        co, th = L["coefficients"], L["thermal"]
        C.card(f"<h3>Verificações automáticas</h3><div class='sub'>α {co['alpha_isc_pct_per_C']} %/°C · β {co['beta_voc_pct_per_C']} %/°C · "
               f"γ {co['gamma_pmax_pct_per_C']} %/°C · U0 {th['u0_W_m2K']} · U1 {th['u1_W_s_m3K']} · NMOT {th['nmot_C']} °C</div>"
               + "".join(f"<div class='cim-check'><code style='color:var(--cim-{'ok' if c['ok'] else 'bad'})'>{'OK' if c['ok'] else 'FALHA'}</code>"
                         f"{C.esc(c['check'])}</div>" for c in L["checks"])
               + "<p class='cim-notes' style='padding:0'>As 18 células sem medição são strings compartilhadas nº 32 (vazias) no XML: nenhum «32» "
                 "é tratado como medição. A fonte rotula a tabela de Voc como «Voc[A]» — erro de unidade documentado, não corrigido.</p>")
    with c2, st.container(border=True):
        st.markdown("**Calibração multiponto do SDM**  \n<span style='color:var(--cim-muted);font-size:.83rem'>Somente as 66 medições de laboratório; "
                    "o campo 2019 nunca entra no ajuste. O experimento recalibra ao iniciar.</span>", unsafe_allow_html=True)
        if st.button("Pré-visualizar ajuste", icon=":material/wb_sunny:", key="dq_cal_btn"):
            ss["_cal_prev"] = True
        if ss.get("_cal_prev"):
            d2 = services.calibration_preview()
            r, rep = d2["reference"], d2["report"]
            rows = [("IL_ref", f"{r['IL_ref']:.4f} A"), ("I0_ref", f"{r['I0_ref']:.3e} A"), ("Rs", f"{r['Rs']:.4f} Ω"), ("Rsh_ref", f"{r['Rsh_ref']:.1f} Ω"),
                    ("a_ref", f"{r['a_ref']:.4f} V"), ("Condição do Jacobiano", f"{rep['condition_number']:.0f}"),
                    ("Arranques no mesmo ótimo", f"{rep['near_optimal_spread']['n_near_optimal']}/{rep['near_optimal_spread']['n_starts']}")]
            rows += [(f"RMSE laboratório {x['variable']}", f"{x['RMSE']:.3f}") for x in rep["lab_metrics"]]
            rows += [(f"{k.split('_')[0]} implícito vs medido", f"{v_['modelo_pct_C']:.3f} vs {v_['medido_pct_C']:.3f} %/°C") for k, v_ in rep["implied_coefficients"].items()]
            C.show(C.spec_table(rows))
            C.notes([C.esc(a) for a in rep["assumptions"]])
    with st.expander("Auditoria XML das 18 células ausentes"):
        st.dataframe(pd.DataFrame(L["audit"]), hide_index=True, width="stretch")
