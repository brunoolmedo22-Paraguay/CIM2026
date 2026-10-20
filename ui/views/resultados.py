"""Artigo · Resultados e discussão: síntese + 4 áreas (energia, computacional, integrada, estatística)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from cim26.experiment.run_store import zip_run
from cim26.paths import RUNS_DIR
from cim26.pvcore.models import MODEL_IDS, MODEL_INFO

from .. import charts, services
from .. import components as C
from ..theme import MODEL_COLORS

ss = st.session_state
POL = {"sinalizar": "sinalizadas", "excluir_erros": "erros excluídos", "excluir_erros_suspeitos": "erros+suspeitas excluídos"}


def f(x, d=2, sign=False):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    s = f"{x:+,.{d}f}" if sign else f"{x:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_data(show_spinner="Empacotando execução…", max_entries=4)
def _zip(run_id: str, stamp: float) -> bytes:
    return zip_run(RUNS_DIR / run_id)


def _figures(run_id: str, prefix: str, figs: list[str]):
    names = [n for n in figs if n.startswith(prefix)]
    if not names:
        return
    with st.expander("Figuras de publicação (SVG vetorial e PNG 200 dpi)"):
        for n in names:
            stem = n[:-4]
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.markdown(f"`{stem}`")
            for col, ext, mime in ((c2, "svg", "image/svg+xml"), (c3, "png", "image/png")):
                p = RUNS_DIR / run_id / "figures" / f"{stem}.{ext}"
                if p.exists():
                    col.download_button(ext.upper(), p.read_bytes(), p.name, mime, key=f"fig_{run_id}_{stem}_{ext}", width="stretch")


def render():
    C.page_header("Resultados e discussão", "Artigo · energia, custo computacional, análise integrada e estatística")
    runs = services.runs()
    if runs.empty:
        C.alert("Nenhuma execução ainda. Configure e execute um experimento em <b>Protocolo e execução</b>.", "info")
        return
    ids = list(runs.run_id)
    done = [r for r, e in zip(runs.run_id, runs.estado) if e == "concluido"]
    if ss.res_run not in ids:
        ss.res_run = (done or ids)[0]
    lab = {r.run_id: f"{r.run_id} · {r.estado}" + (f" · {r.rotulo}" if r.rotulo else "") for r in runs.itertuples()}
    c1, c2, c3 = st.columns([3, 1, 1.3])
    c1.selectbox("Execução", ids, key="res_run", format_func=lab.get, label_visibility="collapsed")
    rid = ss.res_run
    stamp = services.run_stamp(rid)
    b = services.run_bundle(rid, stamp)
    if b["status"].get("estado") != "concluido":
        s = b["status"]
        C.alert(f"Estado: <b>{C.esc(str(s.get('estado')))}</b> · etapa {C.esc(str(s.get('etapa') or ''))}. "
                + ("Os resultados aparecem ao final." if s.get("estado") == "executando" else "Saídas parciais preservadas no diretório da execução."),
                "info" if s.get("estado") == "executando" else "bad")
        if s.get("traceback"):
            st.code(s["traceback"][-2500:])
        return
    disc = RUNS_DIR / rid / "DISCUSSAO.md"
    if disc.exists():
        c2.download_button("Discussão (.md)", disc.read_bytes(), f"DISCUSSAO_{rid}.md", "text/markdown", icon=":material/description:", width="stretch")
    c3.download_button("Exportar execução (ZIP)", _zip(rid, stamp), f"{rid}.zip", "application/zip", type="primary", icon=":material/download:", width="stretch")

    cfg, me = b["config"], b["metrics_energy"]
    env = (b.get("metadata") or {}).get("ambiente_benchmark_isolado", {})
    C.strip([("Dados", f"{len(cfg['months'])} mês(es) · N {int(me.N.iloc[0]):,}".replace(",", ".")),
             ("Anomalias", POL.get(cfg.get("anomaly_policy", "sinalizar"), "sinalizadas")),
             ("Térmica", f"{'A · Tbom' if cfg['thermal_strategy'] == 'A_tmod_medida' else 'B · Faiman'} · ΔT {f(cfg['delta_t_C'], 1)} °C"),
             ("Limiar", f"{cfg['g_threshold_Wm2']:g} W/m²"), ("Rodadas", f"{cfg['repetitions']} · {cfg['order_mode']}"),
             ("Semente", cfg["seed"]), ("CPU", (env.get("cpu_modelo") or "—").replace("Processor", "")[:28])])
    nar = b.get("narrative") or []
    C.synth(next((i["texto"] for i in nar if i["secao"] == "sintese"), "—"))
    t1, t2, t3, t4 = st.tabs(["I · Energia", "II · Computacional", "III · Análise integrada", "IV · Estatística"])
    with t1:
        tab_energy(b, rid, stamp, nar)
    with t2:
        tab_compute(b, rid, nar)
    with t3:
        tab_integrated(b, rid, nar)
    with t4:
        tab_stats(b, rid, nar)


def tab_energy(b, rid, stamp, nar):
    me, ci = b["metrics_energy"].set_index("modelo"), b["bootstrap_ci"]
    rank = list(me["NRMSE_media_pct"].sort_values().index)
    C.discussion(nar, "energia")

    def cib(m, k):
        r = ci[(ci.modelo == m) & (ci.metrica == k)]
        return (r.ic95_lo.iloc[0], r.ic95_hi.iloc[0]) if len(r) else (np.nan, np.nan)
    C.model_cards([{"m": m, "short": MODEL_INFO[m].short, "rank": rank.index(m) + 1, "big": f(me.loc[m, "NRMSE_media_pct"]), "unit": "% nRMSE",
                    "ci": f"IC95 {f(cib(m, 'nRMSE_pct')[0])}–{f(cib(m, 'nRMSE_pct')[1])} %",
                    "lines": [("nMAE", f"{f(me.loc[m, 'NMAE_media_pct'])} %"), ("nMBE (viés)", f"{f(me.loc[m, 'NMBE_media_pct'], 2, True)} %"),
                              ("Erro de energia", f"{f(me.loc[m, 'erro_energia_pct'], 2, True)} %"),
                              ("RMSE · MAE", f"{f(me.loc[m, 'RMSE_W'], 1)} · {f(me.loc[m, 'MAE_W'], 1)} W"), ("nRMSE/Pstc", f"{f(me.loc[m, 'NRMSE_Pstc_pct'])} %")]}
                   for m in MODEL_IDS])
    r0 = me.iloc[0]
    C.notes([f"Percentuais relativos à potência média observada na interseção ({f(r0.P_obs_media_W, 1)} W); nRMSE/Pstc usa a potência STC. "
             f"N = {int(r0.N):,} · {int(r0.pares_validos):,} pares válidos · {f(r0.horas_cobertas_h, 1)} h · energia observada {f(r0.E_obs_kWh, 1)} kWh (parcial).".replace(",", "§").replace("§", ".")])
    days = b["days"]
    key = "res_range_sel"
    if key not in ss or ss[key][0] not in days or ss[key][1] not in days:
        a = "2019-05-13" if "2019-05-13" in days else days[0]
        z = "2019-05-15" if "2019-05-15" in days else days[min(2, len(days) - 1)]
        ss[key] = (a, z)
    with st.container(border=True):
        st.markdown("**Potência medida, prevista e irradiância** — <span style='color:var(--cim-muted);font-size:.85rem'>a irradiância no eixo direito "
                    "ajuda a separar erro de modelo de erro de medição</span>", unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        c1.select_slider("Intervalo de dias", options=days, key=key, format_func=lambda d: pd.Timestamp(d).strftime("%d/%m"))
        c2.toggle("Irradiância", key="res_ov_g")
        c3.toggle("Anomalias", key="res_ov_anom")
        c4.toggle("Tcell", key="res_ov_t")
        a, z = ss[key]
        s = services.run_series(rid, stamp, a, z)
        lines = [(m, s[f"P_{m}_W"], MODEL_COLORS[m], 1.4) for m in MODEL_IDS]
        anom = None
        if ss.res_ov_anom and "anom_severidade" in s:
            x = s[s.anom_severidade.isin(["erro", "suspeito"])]
            anom = {"timestamp": x["timestamp"], "y": x["P_obs_W"], "sev": list(x["anom_severidade"]),
                    "text": ["<br>".join(c for c in str(cc).split(";") if c) for cc in x["anom_codes"]]}
        charts.show(charts.power_series(s["timestamp"], lines, 7.5, g=s["g_poa_Wm2"] if ss.res_ov_g else None,
                                        tcell=s["t_cell_C"] if ss.res_ov_t else None, obs=s["P_obs_W"], anomalies=anom, height=470),
                    "serie_potencia", key="res_series")
        st.download_button("CSV do intervalo", s.to_csv(index=False).encode(), f"predicoes_{a}_{z}.csv", "text/csv", icon=":material/download:")
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Energia acumulada** · somente pares válidos, mesma máscara para todos")
        charts.show(charts.cumulative_energy(b["metrics_daily"]), "energia_acumulada", key="res_cum")
    with c2, st.container(border=True):
        st.markdown("**nRMSE por mês** · % da potência média observada no mês")
        charts.show(charts.bars(b["metrics_monthly"], "mes", "NRMSE_media_pct", "nRMSE [%]"), "nrmse_mes", key="res_mon")
    rb = b["residual_bins"]
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Viés por faixa de irradiância** · MBE [W], positivo = sobrestima")
        charts.show(charts.bars(rb[rb.variavel.str.startswith("G")], "faixa", "MBE_W", "MBE [W]", height=300), "vies_G", key="res_bg")
    with c2, st.container(border=True):
        st.markdown("**Viés por faixa de temperatura do módulo** · MBE [W]")
        charts.show(charts.bars(rb[rb.variavel.str.startswith("T")], "faixa", "MBE_W", "MBE [W]", height=300), "vies_T", key="res_bt")
    with st.container(border=True):
        st.markdown("**Previsto × medido** · amostra de 3.000 pontos; losangos = anomalias físicas de medição")
        charts.show(charts.scatter_pred_obs(b["scatter"]), "previsto_medido", key="res_sc")
    C.sec("Qualidade dos dados e seu peso no erro", "o dataset também erra — e erra igual para os quatro modelos")
    C.discussion(nar, "qualidade")
    qs = b.get("quality_sensitivity")
    if qs is not None and len(qs):
        qs = qs.assign(rotulo=lambda d: d.descricao.str.replace("somente ", "").str.replace(" (máscara principal)", "")
                       + " · " + d.pct_amostras.map(lambda v: f(v, 1)) + " %")
        c1, c2 = st.columns(2)
        with c1, st.container(border=True):
            st.markdown("**nRMSE por cenário de qualidade** · mesmas amostras para os 4 modelos")
            charts.show(charts.bars(qs, "rotulo", "NRMSE_media_pct", "nRMSE [%]", height=360, horizontal=True, margin_l=260), "nrmse_cenarios", key="res_qs")
        with c2, st.container(border=True):
            st.markdown("**Parcela do erro quadrático total** explicada pelas amostras de cada cenário")
            charts.show(charts.bars(qs[qs.cenario != "todas"], "rotulo", "parcela_erro_quadratico_pct", "% do erro quadrático", height=360,
                                    horizontal=True, margin_l=260), "parcela_erro", key="res_qp")
    if b.get("anomaly_summary") is not None:
        st.dataframe(b["anomaly_summary"], hide_index=True, width="stretch",
                     column_config={"pct_elegiveis": st.column_config.NumberColumn("% máscara", format="%.2f")})
    _figures(rid, "energia", b["figures"])


def tab_compute(b, rid, nar):
    s = b["benchmark_summary"]
    N = int(s.batch_size.max())
    sm = s[s.batch_size == N].set_index("modelo")
    runs = b["benchmark_runs"]
    main = runs[runs.experimento == "principal"]
    C.discussion(nar, "computacional")
    C.model_cards([{"m": m, "short": MODEL_INFO[m].short, "big": f(sm.loc[m, "mediana_por_amostra_us"], 4 if sm.loc[m, "mediana_por_amostra_us"] < 1 else 1),
                    "unit": "µs/amostra", "ci": f"lote de {N:,} amostras".replace(",", "."),
                    "lines": [("Mediana do lote", f"{sm.loc[m, 'mediana_s']:.4g} s"), ("p95", f"{sm.loc[m, 'p95_s']:.4g} s"), ("CV", f"{f(sm.loc[m, 'cv_pct'], 1)} %"),
                              ("Pico ΔRSS", f"{f(sm.loc[m, 'mediana_pico_rss_delta_MiB'])} MiB"), ("Falhas", str(int(sm.loc[m, "n_falhas"])))]} for m in MODEL_IDS])
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown(f"**Tempo por amostra** · todas as {len(main)} execuções medidas (escala log)")
        charts.show(charts.boxes(main, "tempo_por_amostra_us", "µs por amostra", log=True), "tempo_amostra", key="cmp_box")
    with c2, st.container(border=True):
        st.markdown("**Estabilidade entre rodadas** · hover mostra a posição do modelo na rodada")
        charts.show(charts.rounds(main), "estabilidade_rodadas", key="cmp_rnd")
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Escalabilidade** · custo por amostra × tamanho do lote")
        charts.show(charts.lines(s, "batch_size", "mediana_por_amostra_us", "Amostras no lote", "µs por amostra", logx=True, logy=True), "escalabilidade", key="cmp_scl")
    with c2, st.container(border=True):
        st.markdown(f"**Memória residente** · pico − RSS antes · método `{main.metodo_memoria.iloc[0]}`")
        charts.show(charts.boxes(main, "pico_rss_delta_MiB", "MiB"), "memoria", key="cmp_mem")
    c1, c2 = st.columns(2)
    meta = b.get("metadata") or {}
    with c1, st.container(border=True):
        st.markdown("**Tempos fora do benchmark** · não compõem o custo por amostra")
        st.dataframe(pd.DataFrame([{"etapa": k, "segundos": v} for k, v in meta.get("tempos_por_etapa_s", {}).items()]), hide_index=True, width="stretch",
                     column_config={"segundos": st.column_config.NumberColumn(format="%.2f")})
        if b.get("benchmark_tracemalloc") is not None:
            st.markdown("**tracemalloc** (passe separado; alocações Python)")
            st.dataframe(b["benchmark_tracemalloc"].drop(columns=["nota"], errors="ignore"), hide_index=True, width="stretch")
    with c2:
        env = meta.get("ambiente_benchmark_isolado", {})
        C.card("<h3>Ambiente isolado do benchmark</h3>" + C.spec_table([
            ("CPU", env.get("cpu_modelo")), ("Núcleos lógicos", env.get("cpu_logicos")), ("RAM", f"{env.get('ram_total_GiB')} GiB"), ("SO", env.get("so")),
            ("Python", env.get("python")), ("NumPy / SciPy", f"{env.get('versao_numpy')} / {env.get('versao_scipy')}"),
            ("Threads BLAS", ", ".join(map(str, (env.get("threads_env") or {}).values()))), ("Relógio", (env.get("relogio") or {}).get("funcao")),
            ("Temperatura CPU", env.get("cpu_temperatura") if isinstance(env.get("cpu_temperatura"), str) else "medida"), ("Energia da CPU", env.get("energia_cpu"))]))
    st.markdown("**Estatística descritiva dos tempos** (por modelo e lote)")
    st.dataframe(s, hide_index=True, width="stretch")
    fc = runs.groupby(["batch_size", "modelo"]).agg(execucoes=("falha", "size"), falhas_execucao=("falha", "sum"), falhas_amostra=("n_falhas_amostra", "sum"),
                                                   nao_convergencia=("n_nao_convergencia", "sum"), nfev_total=("nfev_total", "sum")).reset_index()
    c1, c2 = st.columns(2)
    c1.markdown("**Falhas e convergência**")
    c1.dataframe(fc, hide_index=True, width="stretch")
    c2.markdown("**Determinismo entre rodadas**")
    c2.dataframe(b["determinism"], hide_index=True, width="stretch")
    st.markdown("**Razões pareadas por rodada** (t_modelo / t_M1)")
    st.dataframe(b["time_ratios"], hide_index=True, width="stretch")
    with st.expander(f"Registros brutos do benchmark ({len(runs)} execuções medidas)"):
        st.dataframe(runs, hide_index=True, width="stretch")
    _figures(rid, "computacional", b["figures"])


def tab_integrated(b, rid, nar):
    me = b["metrics_energy"].set_index("modelo")
    nr = me["NRMSE_media_pct"].to_dict()
    scale = (me["NRMSE_media_pct"] / me["RMSE_W"]).to_dict()
    p = b["pareto"]
    C.discussion(nar, "integrada")
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Erro × custo de tempo** · contorno = não dominado; barras = IC95 por dias")
        charts.show(charts.pareto(p[p.eixo == "tempo"], "tempo_us_amostra", "µs por amostra (log)", True, nr, scale), "pareto_tempo", key="int_pt")
    with c2, st.container(border=True):
        st.markdown("**Erro × memória** · mediana do pico ΔRSS")
        charts.show(charts.pareto(p[p.eixo == "memoria"], "memoria_MiB", "Pico ΔRSS [MiB]", False, nr, scale), "pareto_memoria", key="int_pm")
    sens = b.get("sensitivity")
    if sens is not None and len(sens):
        sens = sens.copy()
        if "NRMSE_media_pct" not in sens:
            sens["NRMSE_media_pct"] = sens.RMSE_W * sens.modelo.map(scale)
        c1, c2 = st.columns(2)
        with c1, st.container(border=True):
            st.markdown("**Sensibilidade à hipótese térmica** · ΔT célula–módulo (afeta M2 e M4)")
            charts.show(charts.lines(sens[sens.tipo == "delta_T_C"], "valor", "NRMSE_media_pct", "ΔT [°C]", "nRMSE [%]"), "sens_dT", key="int_sdt")
        with c2, st.container(border=True):
            st.markdown("**Sensibilidade ao limiar de irradiância** · máscara reconstruída com cada limiar")
            charts.show(charts.lines(sens[sens.tipo == "limiar_G_Wm2"], "valor", "NRMSE_media_pct", "Limiar Gpoa [W/m²]", "nRMSE [%]"), "sens_G", key="int_sg")
    st.markdown("**Melhoria marginal** · ΔRMSE = RMSE_ref − RMSE_modelo (positivo = melhora); fator de custo = custo_modelo/custo_ref")
    st.dataframe(b["marginal"], hide_index=True, width="stretch")
    cal = b.get("calibration") or {}
    rep = cal.get("report", {})
    st.markdown("**O que cada modelo exige** · assimetria de parametrização declarada")
    st.dataframe(pd.DataFrame([{"Modelo": m, "Equação": MODEL_INFO[m].equation, "Entradas": MODEL_INFO[m].requirements,
                                "Temperatura": MODEL_INFO[m].temperature_input, "nRMSE [%]": round(nr[m], 2)} for m in MODEL_IDS]),
                 hide_index=True, width="stretch")
    if rep:
        ic = rep.get("implied_coefficients", {})
        C.notes([f"SDM calibrado com 66 medições de laboratório · condição do Jacobiano {rep.get('condition_number', 0):.0f} · STC previsto "
                 f"{f(rep['stc_check']['Pmp_prev_W'], 1)} W vs {f(rep['stc_check']['Pmp_med_W'], 1)} W medido."]
                + ([("Coeficientes implícitos vs medidos: " + " · ".join(f"{k.split('_')[0]} {f(v['modelo_pct_C'], 3)} vs {f(v['medido_pct_C'], 3)} %/°C" for k, v in ic.items()))] if ic else []))
    _figures(rid, "integrada", b["figures"])


def tab_stats(b, rid, nar):
    ci, pr = b["bootstrap_ci"], b["bootstrap_paired"]
    C.discussion(nar, "estatistica")
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown(f"**IC95 por modelo** · bootstrap em blocos de {int(ci.dias.iloc[0])} dias · B = {int(ci.B.iloc[0]):,}".replace(",", "."))
        charts.show(charts.forest(ci[ci.metrica == "nRMSE_pct"], "modelo", "nRMSE [%]"), "ic95_modelos", key="st_ci")
    with c2, st.container(border=True):
        st.markdown("**Diferenças pareadas de nRMSE** · faixa = limiar prático ±0,5 p.p.")
        charts.show(charts.forest(pr[pr.metrica == "nRMSE_pct"], "comparacao", "Δ nRMSE [p.p.] (negativo = primeiro modelo melhor)", practical=0.5),
                    "diferencas_pareadas", key="st_pr")
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown("**Distribuição dos resíduos** · previsto − medido [W]")
        charts.show(charts.residual_hist(b["residual_hist"]), "residuos", key="st_hist")
    with c2, st.container(border=True):
        st.markdown("**nRMSE diário** · cada ponto é um dia (unidade do bootstrap)")
        charts.show(charts.boxes(b["metrics_daily"], "NRMSE_media_pct", "nRMSE diário [%]"), "nrmse_diario", key="st_day")
    st.markdown("**Intervalos de confiança (métricas percentuais)**")
    st.dataframe(ci[ci.metrica.str.contains("pct")], hide_index=True, width="stretch")
    st.markdown("**Comparações pareadas (p.p.)**")
    st.dataframe(pr[pr.metrica == "nRMSE_pct"], hide_index=True, width="stretch")
    st.markdown("**Tempos: média, mediana, DP, CV, percentis e IC**")
    st.dataframe(b["benchmark_summary"], hide_index=True, width="stretch")
    if b.get("statistics") is not None:
        st.download_button("statistics.csv (tabela longa consolidada)", b["statistics"].to_csv(index=False).encode(), "statistics.csv", "text/csv",
                           icon=":material/download:")
    _figures(rid, "estatistica", b["figures"])
