"""Artigo · Protocolo e execução: critérios congelados, lançamento seguro e monitor ao vivo."""

from __future__ import annotations

import streamlit as st

from cim26.data.supsi_field import AVAILABLE_MONTHS
from cim26.experiment.config import ExperimentConfig
from cim26.experiment.run_store import active_run, cancel_run, launch_background, read_status
from cim26.experiment.runner import STAGES
from cim26.paths import RUNS_DIR

from .. import components as C
from .. import nav

ss = st.session_state
ML = {m: ["jan", "fev", "mar", "abr", "mai", "jun"][int(m[-2:]) - 1] + "/19" for m in AVAILABLE_MONTHS}
POL = {"sinalizar": ("Apenas sinalizar (padrão)", "A máscara principal mantém as amostras; a exclusão aparece como sensibilidade."),
       "excluir_erros": ("Excluir anomalias «erro»", "Potência sem irradiância, irradiância sem potência, P acima do plausível, Voc implausível."),
       "excluir_erros_suspeitos": ("Excluir «erro» e «suspeito»", "Também Isc incoerente com G, P muito baixa, saltos de temperatura, valores congelados.")}
TH = {"A_tmod_medida": ("A · Tbom medida (principal)", "Huld recebe Tmod = Tbom; M2 e M4 recebem Tcell = Tbom + G/1000·ΔT."),
      "B_faiman": ("B · Tmod estimada por Faiman", "Tmod = Tamb + G/(U0 + U1·v), U0/U1 medidos pela SUPSI.")}


def _config() -> ExperimentConfig:
    return ExperimentConfig(months=tuple(sorted(ss.p_months)) or AVAILABLE_MONTHS, g_threshold_Wm2=float(ss.p_g), max_gap_min=float(ss.p_gap),
                            thermal_strategy=ss.p_strategy, delta_t_C=float(ss.p_dt), repetitions=int(ss.p_reps), order_mode=ss.p_order or "rotativa",
                            seed=int(ss.p_seed), execution_mode=ss.p_mode or "vetorizado", scaling_enabled=bool(ss.p_scaling),
                            sensitivity_enabled=bool(ss.p_sens), tracemalloc_pass=bool(ss.p_tm), anomaly_policy=ss.p_policy, label=ss.p_label)


def monitor() -> None:
    active = active_run(RUNS_DIR) is not None

    @st.fragment(run_every=1.5 if active else None)
    def _live():
        a = active_run(RUNS_DIR)
        if not a:
            if ss.get("_prot_watch"):
                rid = ss.pop("_prot_watch")
                ss.res_run = rid
                ss["_just_done"] = rid
                st.rerun(scope="app")
            return
        ss["_prot_watch"] = a["run_id"]
        s = read_status(RUNS_DIR / a["run_id"])
        b = s.get("benchmark") or {}
        p = nav.progress_of(s)
        if b.get("rodada"):
            tick = (f"Benchmark {b.get('fase', '')} · rodada {b.get('rodada')}/{b.get('R')} · {b.get('modelo')} (posição {b.get('posicao')}) · "
                    f"lote {b.get('batch')} · última medição {b.get('compute_s', 0):.4g} s · {b.get('feitos')}/{b.get('total')} chamadas")
        elif b.get("total"):
            tick = f"{b.get('fase', '')} · {b.get('feitos', 0)}/{b.get('total')} chamadas"
        else:
            tick = s.get("mensagem", "")
        with st.container(border=True):
            C.sun_arc(p, int(s.get("etapa_idx") or 0), STAGES, f"Executando: {s.get('etapa') or 'preparando'}", tick, a["run_id"],
                      (b.get("feitos", 0) / b["total"]) if b.get("total") else 0.0, key="prot_arc")
            c1, c2 = st.columns([3, 1])
            c1.caption("O processo roda separado da interface: recarregar, trocar de página ou abrir outra sessão não o interrompe nem o duplica.")
            if c2.button("Cancelar experimento", icon=":material/stop_circle:", key="prot_cancel", width="stretch"):
                rid = cancel_run(RUNS_DIR)
                ss.pop("_prot_watch", None)
                st.toast(f"Experimento {rid} cancelado; saídas parciais preservadas.")
                st.rerun(scope="app")

    _live()


def render():
    C.page_header("Protocolo e execução", "Artigo · critérios congelados antes de observar qualquer erro",
                  C.chip("medido", "validação independente") + C.chip("hipotese", "ΔT = hipótese"))
    if ss.get("_just_done"):
        rid = ss["_just_done"]
        st_ = read_status(RUNS_DIR / rid).get("estado")
        C.alert(f"Experimento <b>{C.esc(rid)}</b> terminou com estado «{C.esc(str(st_))}».", "ok" if st_ == "concluido" else "bad")
        if st_ == "concluido" and st.button("Abrir resultados e discussão", type="primary", icon=":material/insights:", key="prot_open"):
            ss.pop("_just_done", None)
            nav.go("resultados")
    monitor()
    busy = active_run(RUNS_DIR) is not None
    left, right = st.columns([1.6, 1], gap="large")
    with left:
        with st.container(border=True):
            st.markdown("**Dados de validação** · medições exteriores SUPSI 2019, independentes da calibração")
            st.pills("Meses", AVAILABLE_MONTHS, selection_mode="multi", key="p_months", format_func=ML.get)
            c1, c2 = st.columns(2)
            c1.number_input("Limiar Gpoa [W/m²]", 0.0, 500.0, step=10.0, key="p_g", help="Sensibilidade a 50/100/200 W/m² calculada à parte.")
            c2.number_input("Lacuna máxima para integrar energia [min]", 5.0, 30.0, step=0.5, key="p_gap")
        with st.container(border=True):
            st.markdown("**Qualidade dos dados** · anomalias físicas são sempre detectadas e o efeito sempre reportado")
            st.radio("Política", list(POL), key="p_policy", format_func=lambda k: f"{POL[k][0]} — {POL[k][1]}", label_visibility="collapsed")
        with st.container(border=True):
            st.markdown("**Modelo térmico** · mesma temperatura por timestamp para os quatro modelos")
            st.radio("Estratégia", list(TH), key="p_strategy", format_func=lambda k: f"{TH[k][0]} — {TH[k][1]}", label_visibility="collapsed")
            st.slider("ΔT célula–módulo [°C] (hipótese, Sandia eq. 23)", 0.0, 10.0, step=0.5, key="p_dt")
        with st.container(border=True):
            st.markdown("**Benchmark computacional** · quatro modelos em sequência, nunca em paralelo; aquecimento não contabilizado")
            c1, c2 = st.columns(2)
            c1.number_input("Rodadas (3–101)", 3, 101, step=1, key="p_reps")
            c2.number_input("Semente", 0, 2**31 - 1, step=1, key="p_seed")
            c1.segmented_control("Ordem dos modelos", ["rotativa", "aleatoria"], key="p_order",
                                 format_func={"rotativa": "rotativa", "aleatoria": "aleatória c/ semente"}.get)
            c2.segmented_control("Execução", ["vetorizado", "escalar"], key="p_mode", format_func={"vetorizado": "vetorizada", "escalar": "escalar"}.get)
            t1, t2, t3 = st.columns(3)
            t1.toggle("Escalabilidade (250/1000/4000)", key="p_scaling")
            t2.toggle("Sensibilidade ΔT e limiar", key="p_sens")
            t3.toggle("Passe tracemalloc", key="p_tm")
    with right:
        ok = True
        try:
            cfg = _config()
            cfg.validate()
        except Exception as exc:
            ok = False
            C.alert(f"Configuração inválida: {C.esc(str(exc))}", "bad")
            cfg = ExperimentConfig()
        n_el = 15457 * len(cfg.months) / 6
        est = n_el * 0.0007 * (cfg.repetitions * (1 + (0.34 if cfg.scaling_enabled else 0)) + 2 + (3 if cfg.sensitivity_enabled else 0)
                               + (5 if cfg.tracemalloc_pass else 0))
        C.card("<h3>Resumo congelado</h3>" + C.spec_table([
            ("Meses", ", ".join(ML[m] for m in cfg.months)), ("Limiar Gpoa", f"{cfg.g_threshold_Wm2:g} W/m²"),
            ("Anomalias", POL[cfg.anomaly_policy][0]), ("Térmica", TH[cfg.thermal_strategy][0]), ("ΔT", f"{cfg.delta_t_C:g} °C (hipótese)"),
            ("Rodadas", f"{cfg.repetitions} × 4 = {cfg.repetitions * 4} medições"), ("Ordem", cfg.order_mode), ("Semente", cfg.seed),
            ("Execução", cfg.execution_mode), ("Duração estimada", f"≈ {max(1, round(est / 60))}–{max(2, round(est / 40))} min (1 núcleo)")]))
        st.text_input("Rótulo da execução", key="p_label", placeholder="ex.: protocolo principal")
        if st.button("Executar experimento científico", type="primary", icon=":material/wb_sunny:", width="stretch", disabled=busy or not ok, key="p_run"):
            try:
                rid = launch_background(cfg.to_dict(), RUNS_DIR)
                ss["_prot_watch"] = rid
                st.toast(f"Experimento {rid} iniciado.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        st.caption("Há um experimento em execução; outro só começa ao final (bloqueio entre todas as sessões)." if busy else
                   "No Streamlit Cloud o disco é temporário: ao final, baixe o ZIP da execução em Resultados ou Histórico.")
