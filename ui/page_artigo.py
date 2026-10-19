"""Modo «Artigo»: laboratório experimental SUPSI (preparação, execução, 4 áreas de resultados, histórico)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cim26.calibration.multipoint import calibrate_multipoint
from cim26.data.supsi_field import AVAILABLE_MONTHS, FLAGS, REASONS, QualityConfig, assess_quality, load_field, monthly_summary
from cim26.data.supsi_lab import check_lab, load_supsi_module_json, read_iec61853_xlsx, supsi_module_spec
from cim26.experiment.config import ExperimentConfig
from cim26.experiment.metrics import common_support
from cim26.experiment.run_store import active_run, import_zip, launch_background, list_runs, load_run, read_status, zip_run
from cim26.experiment.runner import STAGES
from cim26.paths import RUNS_DIR
from cim26.pvcore.models import MODEL_IDS, MODEL_INFO

from . import charts
from .style import COLORS, chip, lede, model_tag, note, strip

MONTH_LABEL = {m: ["jan", "fev", "mar", "abr", "mai", "jun"][int(m[-2:]) - 1] + "/2019" for m in AVAILABLE_MONTHS}


@st.cache_data(show_spinner=False)
def _lab():
    lab = read_iec61853_xlsx()
    return lab.long, lab.coefficients, lab.thermal, lab.audit_missing_cells, check_lab(lab, load_supsi_module_json())


@st.cache_data(show_spinner=False)
def _quality(months: tuple, g_th: float, strategy: str) -> pd.DataFrame:
    m = supsi_module_spec()
    df, _ = load_field(months)
    return assess_quality(df, QualityConfig(g_threshold_Wm2=g_th, require_ambient=strategy == "B_faiman",
                                            voc_stc_V=m.v_oc_V, p_stc_W=m.p_stc_W))


@st.cache_data(show_spinner="Ajuste multiponto com 66 medições de laboratório (≈10 s)…")
def _calibration_preview():
    lab = read_iec61853_xlsx()
    ref, rep = calibrate_multipoint(lab.long, supsi_module_spec())
    return ref.to_dict(), rep.to_json_dict()


@st.cache_data(show_spinner="Carregando execução…")
def _run(run_id: str, stamp: float) -> dict:
    return load_run(RUNS_DIR / run_id)


# ---------------------------------------------------------------------------
@st.fragment(run_every=1.5)
def monitor():
    a = active_run()
    if not a:
        if st.session_state.pop("was_running", None):
            st.session_state["art_view"] = "Resultados"
            st.rerun()
        return
    st.session_state["was_running"] = a["run_id"]
    st.session_state["run_open"] = a["run_id"]
    s = read_status(RUNS_DIR / a["run_id"])
    with st.container(border=True):
        st.markdown(f"**Experimento em execução** · `{a['run_id']}`")
        idx = int(s.get("etapa_idx") or 0)
        st.progress(idx / len(STAGES), text=f"Etapa {idx}/{len(STAGES)}: {s.get('etapa') or '—'} — {s.get('mensagem', '')}")
        b = s.get("benchmark") or {}
        if b.get("total"):
            txt = f"Benchmark: {b.get('fase')}"
            if b.get("rodada"):
                txt += f" · rodada {b['rodada']}/{b.get('R')} · {b.get('modelo')} (posição {b.get('posicao')}) · lote {b.get('batch')}"
                if b.get("compute_s") is not None:
                    txt += f" · última medição {b['compute_s']:.4g} s"
            st.progress(min(b.get("feitos", 0) / b["total"], 1.0), text=txt + f" · {b.get('feitos', 0)}/{b['total']} chamadas")
        st.caption("O processo é independente da interface: recarregar a página não interrompe nem duplica a execução.")


# ---------------------------------------------------------------------------
def preparation():
    lab_long, coeffs, thermal, audit, checks = _lab()
    module = supsi_module_spec()
    st.subheader("Conjunto de dados e qualidade")
    months = st.pills("Meses de campo (validação independente)", AVAILABLE_MONTHS, selection_mode="multi",
                      default=list(AVAILABLE_MONTHS), format_func=lambda m: MONTH_LABEL[m], key="months")
    c1, c2, c3 = st.columns(3)
    strategy = c1.radio("Estratégia térmica", ["A_tmod_medida", "B_faiman"],
                        format_func=lambda s: {"A_tmod_medida": "A · Tbom medida (principal)",
                                               "B_faiman": "B · Tmod estimada por Faiman (opcional)"}[s])
    g_th = c2.number_input("Limiar de irradiância Gpoa [W/m²]", 0.0, 500.0, 100.0, 10.0,
                           help="Pré-definido antes de observar erros (sensibilidade 50/100/200 calculada à parte).")
    gap = c3.number_input("Lacuna máxima para integrar energia [min]", 5.0, 30.0, 7.5, 0.5)
    if not months:
        st.warning("Selecione ao menos um mês.")
        return
    q = _quality(tuple(sorted(months)), g_th, strategy)
    summ = monthly_summary(q, gap)
    tot = summ.iloc[-1]
    m = st.columns(4)
    m[0].metric("Registros lidos", f"{int(tot.n_total):,}".replace(",", "."))
    m[1].metric("Elegíveis (máscara comum)", f"{int(tot.n_elegivel):,}".replace(",", "."))
    m[2].metric("Pares integráveis", f"{int(tot.pares_validos):,}".replace(",", "."))
    m[3].metric("Horas cobertas", f"{float(tot.horas_cobertas_pares_validos):.1f} h")
    with st.expander("Resumo mensal e motivos de exclusão", expanded=False):
        st.dataframe(summ, hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame([{"código": k, "motivo": v, "efeito": "exclui"} for k, v in REASONS.items()] +
                                  [{"código": k, "motivo": v, "efeito": "informativo"} for k, v in FLAGS.items()]),
                     hide_index=True, width="stretch")
        note("Nenhuma linha é apagada, promediada ou imputada. Os registros 'NaN' da fonte permanecem como motivo R03; "
             "a mesma máscara vale para os quatro modelos.")
    days = sorted(q["timestamp"].dropna().dt.date.astype(str).unique())
    day = st.select_slider("Pré-visualizar dia", options=days, value="2019-05-14" if "2019-05-14" in days else days[0])
    d = q[q["timestamp"].dt.date.astype(str) == day]
    st.plotly_chart(charts.field_preview(d, gap), config=charts.CONFIG)
    with st.expander("Tabela completa do dia (com motivos)"):
        st.dataframe(d, hide_index=True, width="stretch")

    st.subheader("Laboratório e calibração do SDM")
    st.markdown(chip("laboratório", "IEC 61853-1 · SUPSI PVLab") + chip("indisponível", "fabricante, modelo, Vmp, Imp e Ns não divulgados"),
                unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["Matrizes", "Verificações", "Calibração (pré-visualização)"])
    with t1:
        cols = st.columns(3)
        for col, (var, unit) in zip(cols, (("Pmp", "W"), ("Isc", "A"), ("Voc", "V"))):
            mat = lab_long[lab_long.variable == var].pivot(index="irradiance_poa_Wm2", columns="temperature_module_C",
                                                           values="measured_value").sort_index(ascending=False)
            col.plotly_chart(charts.heat_matrix(mat, unit, f"{var} [{unit}]"), config=charts.CONFIG)
        st.caption(f"Coeficientes medidos: α {coeffs['alpha_isc_pct_per_C']} %/°C · β {coeffs['beta_voc_pct_per_C']} %/°C · "
                   f"δ {coeffs['gamma_pmax_pct_per_C']} %/°C · U0 {thermal['u0_W_m2K']} W/m²K · U1 {thermal['u1_W_s_m3K']} W·s/m³K · "
                   f"NMOT {thermal['nmot_C']} °C. A fonte rotula a tabela de Voc como «Voc[A]»: erro de unidade documentado, não corrigido.")
    with t2:
        st.dataframe(pd.DataFrame(checks).assign(ok=lambda x: x.ok.map({True: "ok", False: "FALHA"}), detail=lambda x: x.detail.astype(str)),
                     hide_index=True, width="stretch")
        note("As células sem medição aparecem no XML como string compartilhada nº 32, cujo conteúdo é vazio. "
             "Nenhum valor 32 é tratado como medição.")
        with st.expander("Auditoria XML das 18 células ausentes"):
            st.dataframe(pd.DataFrame(audit), hide_index=True, width="stretch")
    with t3:
        note("O experimento recalibra sempre ao iniciar (determinístico, registrado em calibration_s) usando somente o "
             "laboratório. Esta pré-visualização usa a mesma configuração e nunca toca os dados de campo.")
        if st.button("Pré-visualizar calibração multiponto"):
            st.session_state["cal_prev"] = True
        if st.session_state.get("cal_prev"):
            ref, rep = _calibration_preview()
            c = st.columns(5)
            for col, (k, u) in zip(c, (("IL_ref", "A"), ("I0_ref", "A"), ("Rs", "Ω"), ("Rsh_ref", "Ω"), ("a_ref", "V"))):
                col.metric(k, f"{ref[k]:.4g} {u}")
            st.dataframe(pd.DataFrame(rep["lab_metrics"]).round(4), hide_index=True, width="stretch")
            st.caption(f"Condição do Jacobiano {rep['condition_number']:.0f}; {rep['near_optimal_spread']['n_near_optimal']}/"
                       f"{rep['near_optimal_spread']['n_starts']} arranques no mesmo ótimo; cotas ativas: {rep['active_bounds'] or 'nenhuma'}.")
            ic = rep["implied_coefficients"]
            st.dataframe(pd.DataFrame([{"coeficiente": k, "SDM implícito [%/°C]": v["modelo_pct_C"], "medido [%/°C]": v["medido_pct_C"]}
                                       for k, v in ic.items()]).round(4), hide_index=True, width="stretch")
            for a in rep["assumptions"]:
                st.markdown(f"- {a}")

    st.subheader("Protocolo do benchmark")
    c1, c2, c3, c4 = st.columns(4)
    reps = c1.number_input("Rodadas", 3, 101, 11, 1, help="Inteiro entre 3 e 101; padrão 11.")
    order = c2.radio("Ordem dos modelos", ["rotativa", "aleatoria"],
                     format_func=lambda s: "rotativa (cíclica)" if s == "rotativa" else "aleatória com semente")
    seed = c3.number_input("Semente", 0, 2**31 - 1, 20261019)
    mode = c4.radio("Execução", ["vetorizado", "escalar"], help="Experimentos separados: nunca misturar modos.")
    c1, c2, c3, c4 = st.columns(4)
    dT = c1.number_input("ΔT célula–módulo [°C]", 0.0, 10.0, 3.0, 0.5, help="Hipótese (Sandia eq. 23).")
    scaling = c2.toggle("Escalabilidade (250/1000/4000)", True)
    sens = c3.toggle("Sensibilidade ΔT e limiar G", True)
    tm = c4.toggle("Passe tracemalloc separado", True)
    label = st.text_input("Rótulo da execução", placeholder="ex.: protocolo principal, ΔT=3 °C")
    cfg = ExperimentConfig(months=tuple(sorted(months)), thermal_strategy=strategy, delta_t_C=float(dT),
                           g_threshold_Wm2=float(g_th), max_gap_min=float(gap), repetitions=int(reps), order_mode=order,
                           seed=int(seed), execution_mode=mode, scaling_enabled=scaling, sensitivity_enabled=sens,
                           tracemalloc_pass=tm, label=label)
    est = int(tot.n_elegivel) * 0.0007 * (int(reps) * (1 + (0.34 if scaling else 0)) + 2 + (3 if sens else 0) + (4 if tm else 0))
    st.caption(f"Estimativa grosseira de duração: {est / 60:.0f}–{est / 40:.0f} min, dominada pelo SDM; tempos reais só após medição.")
    busy = active_run() is not None
    if st.button("Executar experimento científico", type="primary", disabled=busy, width="stretch"):
        try:
            rid = launch_background(cfg.to_dict())
            st.session_state["run_open"] = rid
            st.toast(f"Experimento {rid} iniciado")
            st.rerun()
        except Exception as exc:
            st.error(f"Não foi possível iniciar: {exc}")
    if busy:
        st.caption("Há um experimento em execução; um novo só pode começar ao final.")


# ---------------------------------------------------------------------------
def _fmt_tbl(df: pd.DataFrame, nd: int = 3) -> pd.DataFrame:
    return df.round(nd)


def tab_energy(run: dict, cfg: dict):
    me = run["metrics_energy"]
    pred = run["predictions"].sort_values("row_id").reset_index(drop=True)
    cols = st.columns(4)
    for col, mm in zip(cols, MODEL_IDS):
        r = me.set_index("modelo").loc[mm]
        with col.container(border=True):
            st.markdown(model_tag(mm), unsafe_allow_html=True)
            st.metric("RMSE", f"{r.RMSE_W:.2f} W", help="Interseção comum de amostras")
            st.caption(f"MAE {r.MAE_W:.2f} W · MBE {r.MBE_W:+.2f} W · NRMSE/Pstc {r.NRMSE_Pstc_pct:.2f} % · "
                       f"energia {r.erro_energia_pct:+.2f} %")
    note(f"N = {int(me.N.iloc[0])} amostras na interseção; {int(me.pares_validos.iloc[0])} pares válidos "
         f"({me.horas_cobertas_h.iloc[0]:.1f} h). Energia observada {me.E_obs_kWh.iloc[0]:.2f} kWh — parcial, só sobre pares "
         "válidos; não é energia semestral. MBE > 0 indica sobrestimação.")
    st.dataframe(_fmt_tbl(me.drop(columns=["unidade_potencia", "normalizador_NRMSE"])), hide_index=True, width="stretch")

    st.markdown("##### Potência medida e prevista")
    t = pred["timestamp"]
    days = sorted(t.dt.date.astype(str).unique())
    c1, c2 = st.columns([2, 1])
    rng = c1.select_slider("Intervalo de dias", options=days, value=(days[0], days[min(2, len(days) - 1)]))
    sel = (t.dt.date.astype(str) >= rng[0]) & (t.dt.date.astype(str) <= rng[1])
    show = c2.multiselect("Modelos", MODEL_IDS, default=list(MODEL_IDS))
    d = pred[sel]
    st.plotly_chart(charts.power_timeseries(d["timestamp"], d["P_obs_W"], {mm: d[f"P_{mm}_W"] for mm in show},
                                            cfg["max_gap_min"]), config=charts.CONFIG)
    inter, pairs = common_support(pred, cfg["max_gap_min"])
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Energia acumulada (pares válidos)")
        st.plotly_chart(charts.cumulative_energy(pred, pairs), config=charts.CONFIG)
    with c2:
        st.markdown("##### Erro por mês")
        st.plotly_chart(charts.bars_by_group(run["metrics_monthly"], "mes", "RMSE_W", "RMSE [W]"), config=charts.CONFIG)
    st.markdown("##### Erro por dia")
    metric = st.segmented_control("Métrica diária", ["RMSE_W", "MAE_W", "MBE_W"], default="RMSE_W", key="daily_metric")
    st.plotly_chart(charts.lines_by_group(run["metrics_daily"], "dia", metric or "RMSE_W", f"{metric} [W]", markers=False,
                                          xtitle="Dia"), config=charts.CONFIG)
    st.markdown("##### Resíduos por faixa de irradiância e temperatura")
    rb = run["residual_bins"]
    c1, c2 = st.columns(2)
    c1.plotly_chart(charts.bars_by_group(rb[rb.variavel.str.startswith("G")], "faixa", "MBE_W", "MBE [W] (Gpoa)", zero_line=True),
                    config=charts.CONFIG)
    c2.plotly_chart(charts.bars_by_group(rb[rb.variavel.str.startswith("T")], "faixa", "MBE_W", "MBE [W] (Tmod)", zero_line=True),
                    config=charts.CONFIG)
    st.markdown("##### Previsto × medido")
    st.plotly_chart(charts.scatter_pred_obs(pred), config=charts.CONFIG)
    with st.expander("Diagnóstico do SDM: Isc e Voc previstos × medidos em campo"):
        ok = np.isfinite(pred.M4_Isc_A) & np.isfinite(pred.Isc_obs_A)
        e_i = (pred.M4_Isc_A - pred.Isc_obs_A)[ok]
        ok2 = np.isfinite(pred.M4_Voc_V) & np.isfinite(pred.Voc_obs_V)
        e_v = (pred.M4_Voc_V - pred.Voc_obs_V)[ok2]
        st.dataframe(pd.DataFrame([{"grandeza": "Isc [A]", "N": len(e_i), "MBE": e_i.mean(), "RMSE": np.sqrt((e_i**2).mean())},
                                   {"grandeza": "Voc [V]", "N": len(e_v), "MBE": e_v.mean(), "RMSE": np.sqrt((e_v**2).mean())}]).round(4),
                     hide_index=True, width="stretch")
        st.caption("Diagnóstico de onde surge o erro do SDM (corrente vs tensão). Voc medido contém valores anômalos sinalizados (F01).")
    with st.expander("Tabela de previsões do intervalo"):
        st.dataframe(d, hide_index=True, width="stretch")


def tab_compute(run: dict, cfg: dict):
    runs = run["benchmark_runs"]
    summ = run["benchmark_summary"]
    main = runs[runs.experimento == "principal"]
    N = int(main.batch_size.iloc[0])
    meta = run.get("metadata", {})
    st_s = meta.get("tempos_por_etapa_s", {})
    s_main = summ[summ.batch_size == N].set_index("modelo")
    cols = st.columns(4)
    for col, mm in zip(cols, MODEL_IDS):
        r = s_main.loc[mm]
        with col.container(border=True):
            st.markdown(model_tag(mm), unsafe_allow_html=True)
            st.metric("Mediana por amostra", f"{r.mediana_por_amostra_us:.4g} µs")
            st.caption(f"mediana {r.mediana_s:.4g} s/lote · p95 {r.p95_s:.4g} s · CV {r.cv_pct:.1f} % · "
                       f"{int(r.n_falhas)} falha(s)")
    note(f"Lote principal = {N} amostras; {int(main.rodada.max())} rodadas × 4 modelos = {len(main)} execuções medidas, "
         "estritamente sequenciais, com aquecimento não contabilizado. compute_s mede só a avaliação física.")
    stages = pd.DataFrame([{"etapa": k, "segundos": v} for k, v in st_s.items()])
    if len(stages):
        with st.expander("Tempos fora do benchmark (não compõem o custo do modelo)"):
            st.dataframe(stages.round(3), hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Tempo por amostra (todas as rodadas)")
        st.plotly_chart(charts.box_by_model(main, "tempo_por_amostra_us", "µs por amostra (log)", log=True), config=charts.CONFIG)
    with c2:
        st.markdown("##### Estabilidade entre rodadas")
        st.plotly_chart(charts.rounds_chart(main), config=charts.CONFIG)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Memória: pico RSS − RSS antes")
        st.plotly_chart(charts.box_by_model(main, "pico_rss_delta_MiB", "MiB"), config=charts.CONFIG)
        st.caption(f"Método: {main.metodo_memoria.iloc[0]}. Resolução de página; diferenças pequenas são ruidosas.")
        if "benchmark_tracemalloc" in run:
            st.dataframe(run["benchmark_tracemalloc"].round(4), hide_index=True, width="stretch")
    with c2:
        st.markdown("##### Escalabilidade")
        st.plotly_chart(charts.lines_by_group(summ, "batch_size", "mediana_s", "compute_s mediano [s]", log_x=True, log_y=True,
                                              xtitle="Tamanho do lote [amostras]"), config=charts.CONFIG)
        st.plotly_chart(charts.lines_by_group(summ, "batch_size", "mediana_por_amostra_us", "µs por amostra", log_x=True, log_y=True,
                                              xtitle="Tamanho do lote [amostras]"), config=charts.CONFIG)
    st.markdown("##### Falhas, convergência e determinismo")
    fc = runs.groupby(["batch_size", "modelo"]).agg(execucoes=("falha", "size"), falhas_execucao=("falha", "sum"),
                                                   falhas_amostra=("n_falhas_amostra", "sum"),
                                                   nao_convergencia=("n_nao_convergencia", "sum"),
                                                   nfev_total=("nfev_total", "sum")).reset_index()
    st.dataframe(fc, hide_index=True, width="stretch")
    st.dataframe(run["determinism"], hide_index=True, width="stretch")
    st.markdown("##### Razões pareadas por rodada (t_modelo / t_M1)")
    st.dataframe(run["time_ratios"].round(3), hide_index=True, width="stretch")
    with st.expander("Ambiente de execução do benchmark"):
        st.json(meta.get("ambiente_benchmark_isolado", {}))
    with st.expander("Registros brutos (benchmark_runs.csv)"):
        st.dataframe(runs, hide_index=True, width="stretch")


def tab_integrated(run: dict, cfg: dict):
    pareto = run["pareto"]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Erro × tempo por amostra")
        st.plotly_chart(charts.pareto_chart(pareto[pareto.eixo == "tempo"], "tempo_us_amostra", "Mediana por amostra [µs] (log)", True),
                        config=charts.CONFIG)
    with c2:
        st.markdown("##### Erro × memória")
        st.plotly_chart(charts.pareto_chart(pareto[pareto.eixo == "memoria"], "memoria_MiB", "Mediana do pico ΔRSS [MiB]", False),
                        config=charts.CONFIG)
    note("Critério: i é dominado se outro modelo tem custo ≤ e RMSE ≤, com ao menos uma desigualdade estrita (estimativas "
         "pontuais). «Dominância robusta» exige IC95 sem sobreposição nos dois eixos. Contorno escuro = não dominado. "
         "Isto descreve esta amostra e esta máquina; não é declaração de superioridade geral.")
    st.dataframe(pareto[["eixo", "modelo", "RMSE_W", "RMSE_lo", "RMSE_hi", "tempo_us_amostra", "memoria_MiB", "nao_dominado",
                         "dominado_por", "dominancia_robusta_por"]].round(4), hide_index=True, width="stretch")
    st.markdown("##### Melhoria marginal")
    note("ΔRMSE = RMSE_ref − RMSE_modelo (W; positivo = melhora). Δcusto = custo_modelo − custo_ref. "
         "Razão = ΔRMSE/Δcusto. Fator de custo = custo_modelo/custo_ref.")
    st.dataframe(run["marginal"].round(5), hide_index=True, width="stretch")
    if "sensitivity" in run:
        sens = run["sensitivity"]
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### Sensibilidade a ΔT (hipótese térmica)")
            st.plotly_chart(charts.lines_by_group(sens[sens.tipo == "delta_T_C"], "valor", "RMSE_W", "RMSE [W]", xtitle="ΔT [°C]"),
                            config=charts.CONFIG)
        with c2:
            st.markdown("##### Sensibilidade ao limiar de Gpoa")
            st.plotly_chart(charts.lines_by_group(sens[sens.tipo == "limiar_G_Wm2"], "valor", "RMSE_W", "RMSE [W]",
                                                  xtitle="Limiar [W/m²]"), config=charts.CONFIG)
    st.markdown("##### Requisitos de parametrização")
    cal = run.get("calibration", {}).get("report", {})
    rows = [{"modelo": mm, "equação": MODEL_INFO[mm].equation, "entradas do módulo": MODEL_INFO[mm].requirements,
             "temperatura usada": MODEL_INFO[mm].temperature_input,
             "dados para parametrizar": {"M1": "1 valor (Pstc medida)", "M2": "2 valores (Pstc, γ medidos)",
                                         "M3": "Pstc + 6 coeficientes tecnológicos genéricos (não calibrados)",
                                         "M4": f"66 medições de laboratório → 5 parâmetros (condição {cal.get('condition_number', float('nan')):.0f})"}[mm]}
            for mm in MODEL_IDS]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    note("Assimetria declarada: M2 recebe γ medido em laboratório; M4 recebe 66 medições; M3 usa coeficientes genéricos "
         "PVGIS c-Si CURRENT. Os quatro usam a mesma Gpoa medida, sem correção óptica.")


def tab_statistics(run: dict, cfg: dict):
    ci = run["bootstrap_ci"]
    B, D = int(ci.B.iloc[0]), int(ci.dias.iloc[0])
    note(f"Bootstrap em blocos por dia: {D} dias reamostrados com reposição, B = {B}, semente {cfg['seed']}. "
         "Amostras de 5 min não são tratadas como independentes. Rodadas repetidas de software não geram incerteza energética.")
    c = st.columns(3)
    for col, (k, t) in zip(c, (("RMSE_W", "RMSE [W]"), ("MBE_W", "MBE [W]"), ("erro_energia_pct", "Erro de energia [%]"))):
        col.plotly_chart(charts.ci_chart(ci, k, t), config=charts.CONFIG)
    st.dataframe(ci.round(4), hide_index=True, width="stretch")
    st.markdown("##### Diferenças pareadas por dia")
    st.dataframe(run["bootstrap_paired"].round(4), hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("##### Distribuição dos resíduos")
        pred = run["predictions"]
        fig = go.Figure()
        for mm in MODEL_IDS:
            fig.add_histogram(x=pred[f"res_{mm}_W"], name=mm, marker_color=COLORS[mm], opacity=0.55, nbinsx=120)
        fig.update_layout(barmode="overlay")
        fig.update_xaxes(title="Resíduo previsto − medido [W]", range=[-80, 80])
        st.plotly_chart(charts.base(fig, 320), config=charts.CONFIG)
    with c2:
        st.markdown("##### RMSE diário")
        st.plotly_chart(charts.box_by_model(run["metrics_daily"], "RMSE_W", "RMSE diário [W]"), config=charts.CONFIG)
    st.markdown("##### Tempos: estatística descritiva por modelo e lote")
    st.dataframe(run["benchmark_summary"].round(6), hide_index=True, width="stretch")
    note("DP com ddof=1; CV = DP/média; IC95 da mediana por bootstrap das rodadas (instável com poucas rodadas; "
         "autocorrelação de execução não modelada). ρ de Spearman descreve tendência entre rodadas.")
    st.download_button("statistics.csv", run["statistics"].to_csv(index=False).encode(), "statistics.csv", "text/csv")


def results(run_id: str | None):
    runs = list_runs()
    if runs.empty:
        st.info("Nenhuma execução ainda. Configure e execute um experimento em Preparação.")
        return
    ids = list(runs.run_id)
    run_id = run_id if run_id in ids else next((r for r, e in zip(runs.run_id, runs.estado) if e == "concluido"), ids[0])
    run_id = st.selectbox("Execução", ids, index=ids.index(run_id),
                          format_func=lambda r: f"{r} · {runs.set_index('run_id').loc[r, 'estado']}"
                                                + (f" · {runs.set_index('run_id').loc[r, 'rotulo']}" if runs.set_index('run_id').loc[r, 'rotulo'] else ""))
    st.session_state["run_open"] = run_id
    rd = RUNS_DIR / run_id
    status = read_status(rd)
    if status.get("estado") != "concluido":
        if status.get("estado") == "executando":
            st.info("Execução em andamento; os resultados aparecem ao final.")
        else:
            st.error(f"Estado: {status.get('estado')}. Etapa: {status.get('etapa')}. Saídas parciais preservadas em {rd}.")
            if status.get("traceback"):
                st.code(status["traceback"][-3000:])
        return
    run = _run(run_id, (rd / "status.json").stat().st_mtime)
    cfg = run["config"]
    me = run["metrics_energy"]
    bench = run["benchmark_runs"]
    meta = run.get("metadata", {})
    env = meta.get("ambiente_benchmark_isolado", {})
    strip([("Dados", f"{len(cfg['months'])} mês(es) · N={int(me.N.iloc[0])}"),
           ("Térmica", f"{'A · Tbom' if cfg['thermal_strategy'] == 'A_tmod_medida' else 'B · Faiman'} · ΔT {cfg['delta_t_C']:g} °C"),
           ("Limiar Gpoa", f"{cfg['g_threshold_Wm2']:g} W/m²"),
           ("Rodadas", f"{cfg['repetitions']} · {cfg['order_mode']}"),
           ("Semente", str(cfg["seed"])),
           ("Execução", cfg["execution_mode"]),
           ("Memória", str(bench.metodo_memoria.iloc[0])),
           ("CPU", (env.get("cpu_modelo") or "—")[:28])])
    st.markdown(chip("hipótese", "diagnóstico de engenharia") + chip("laboratório", "SDM calibrado só com laboratório") +
                chip("medido", "validação: campo 2019 independente"), unsafe_allow_html=True)
    c1, c2 = st.columns([1, 3])
    c1.download_button("Exportar execução (ZIP)", zip_run(rd), f"{run_id}.zip", "application/zip", width="stretch", type="primary")
    c2.caption(f"Diretório: {rd}. O ZIP contém CSV, JSON, figuras SVG/PNG e README_RUN.md; reabre sem reexecutar modelos.")
    t1, t2, t3, t4 = st.tabs(["I · Energia", "II · Computacional", "III · Análise integrada", "IV · Estatística"])
    with t1:
        tab_energy(run, cfg)
    with t2:
        tab_compute(run, cfg)
    with t3:
        tab_integrated(run, cfg)
    with t4:
        tab_statistics(run, cfg)


def history():
    runs = list_runs()
    st.subheader("Execuções registradas")
    if runs.empty:
        st.info("Nenhuma execução registrada.")
    else:
        ev = st.dataframe(runs, hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row", key="hist_tbl")
        rows = ev.selection.rows if ev and hasattr(ev, "selection") else []
        sel = [runs.run_id.iloc[i] for i in rows]
        c1, c2 = st.columns(2)
        if c1.button("Abrir selecionada", disabled=len(sel) != 1):
            st.session_state["run_open"] = sel[0]
            st.session_state["art_view"] = "Resultados"
            st.rerun()
        if len(sel) >= 2:
            comp = []
            for r in sel:
                p = RUNS_DIR / r / "metrics_energy.csv"
                if p.exists():
                    d = pd.read_csv(p)
                    d.insert(0, "run_id", r)
                    comp.append(d[["run_id", "modelo", "N", "RMSE_W", "MAE_W", "MBE_W", "erro_energia_pct"]])
            if comp:
                st.markdown("##### Comparação (sem recalcular)")
                st.dataframe(pd.concat(comp).round(4), hide_index=True, width="stretch")
        elif len(sel) == 1:
            c2.download_button("Baixar ZIP", zip_run(RUNS_DIR / sel[0]), f"{sel[0]}.zip", "application/zip")
    st.subheader("Importar execução exportada")
    up = st.file_uploader("ZIP de execução", type=["zip"])
    if up is not None and st.button("Importar"):
        try:
            p = import_zip(up.getvalue())
            st.success(f"Importada em {p.name}; reaberta sem reexecutar modelos.")
        except Exception as exc:
            st.error(str(exc))


def render():
    st.title("Artigo")
    lede("Validação dos quatro modelos contra medições exteriores SUPSI 2019 e benchmark computacional sequencial. "
         "Calibração só com laboratório; mesma máscara de amostras para todos os modelos.")
    monitor()
    view = st.segmented_control("Área", ["Preparação", "Resultados", "Histórico"], key="art_view",
                                default="Preparação", label_visibility="collapsed")
    if view == "Resultados":
        results(st.session_state.get("run_open"))
    elif view == "Histórico":
        history()
    else:
        preparation()
