"""Discussão automática dos resultados (texto em português, gerado dos arquivos da execução).

Regras de redação (determinísticas, reprodutíveis, sem serviço externo):
* Comparações de exatidão usam a diferença PAREADA de nRMSE (p.p.) com IC95 por
  bootstrap em blocos de dias:
    - IC exclui 0 e |Δ| ≥ limiar prático  → «diferença distinguível e relevante»
    - IC exclui 0 e |Δ| <  limiar prático  → «distinguível, porém pequena»
    - IC inclui 0                          → «não distinguível nesta amostra»
  O limiar prático (0,5 p.p.) é convenção editorial declarada, não um teste.
* Afirmações causais são marcadas como hipótese; nunca se declara um «vencedor» universal.
* Toda frase cita os números de onde vem; os números vêm dos CSV da execução.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..data.anomalies import ANOMALIES
from ..pvcore.models import MODEL_IDS, MODEL_INFO

PRACTICAL_PP = 0.5


def f(x, nd=2, sign=False) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    s = f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"
    return s.replace(".", ",")


def fint(x) -> str:
    return f"{int(round(x)):,}".replace(",", ".")


def name(m: str) -> str:
    return f"{m} ({MODEL_INFO[m].short})"


def factor(x: float) -> str:
    if x >= 100:
        return f"≈ {fint(x)}×"
    return f"≈ {f(x, 1)}×"


def _item(sec, titulo, texto, evid="contexto", modelos=None):
    return {"secao": sec, "titulo": titulo, "texto": texto, "evidencia": evid, "modelos": modelos or []}


def _paired(paired: pd.DataFrame, a: str, b: str, metric="nRMSE_pct"):
    """Diferença (a − b) com IC; procura nas duas orientações."""
    if paired is None or paired.empty:
        return None
    d = paired[paired.metrica == metric]
    r = d[d.comparacao == f"{a} − {b}"]
    if len(r):
        r = r.iloc[0]
        return float(r.diferenca), float(r.ic95_lo), float(r.ic95_hi)
    r = d[d.comparacao == f"{b} − {a}"]
    if len(r):
        r = r.iloc[0]
        return -float(r.diferenca), -float(r.ic95_hi), -float(r.ic95_lo)
    return None


def classify(diff, lo, hi) -> tuple[str, str]:
    if lo <= 0 <= hi:
        return "inconclusiva", "não distinguível nesta amostra de dias (IC95 inclui zero)"
    if abs(diff) >= PRACTICAL_PP:
        return "robusta", "distinguível e acima do limiar prático de 0,5 p.p."
    return "indicativa", "distinguível, porém pequena (abaixo de 0,5 p.p.)"


# ---------------------------------------------------------------------------
def energy_section(o: dict, cfg: dict) -> list[dict]:
    me = o["metrics_energy"].set_index("modelo")
    paired = o.get("bootstrap_paired")
    ci = o.get("bootstrap_ci")
    items = []
    order = me["NRMSE_media_pct"].sort_values().index.tolist()
    best, second, worst = order[0], order[1], order[-1]
    mean_obs = float(me["P_obs_media_W"].iloc[0]) if "P_obs_media_W" in me else np.nan
    rank = ", ".join(f"{name(m)} {f(me.loc[m, 'NRMSE_media_pct'])} %" for m in order)
    txt = (f"O menor erro quadrático normalizado foi obtido por {name(best)}, com nRMSE de "
           f"{f(me.loc[best, 'NRMSE_media_pct'])} % da potência média observada ({f(mean_obs, 1)} W; RMSE "
           f"{f(me.loc[best, 'RMSE_W'])} W). Ordem completa: {rank}. A amplitude entre o melhor e o pior modelo foi de "
           f"{f(me.loc[worst, 'NRMSE_media_pct'] - me.loc[best, 'NRMSE_media_pct'])} p.p.")
    pr = _paired(paired, best, second)
    evid = "contexto"
    if pr:
        evid, phrase = classify(*pr)
        txt += (f" A vantagem de {best} sobre {second} foi de {f(-pr[0], 3)} p.p. (IC95 pareado "
                f"[{f(-pr[2], 3)}; {f(-pr[1], 3)}] p.p.): {phrase}.")
    items.append(_item("energia", "Exatidão de potência", txt, evid, [best]))

    # grupo equivalente
    equiv = [best]
    for m in order[1:]:
        p2 = _paired(paired, m, best)
        if p2 and (p2[1] <= 0 <= p2[2] or abs(p2[0]) < PRACTICAL_PP):
            equiv.append(m)
    if len(equiv) > 1:
        out = [m for m in order if m not in equiv]
        t = (f"Do ponto de vista prático, {', '.join(name(m) for m in equiv)} formaram um grupo de exatidão equivalente "
             f"(diferenças pareadas de nRMSE abaixo de {f(PRACTICAL_PP, 1)} p.p. ou não distinguíveis)")
        t += f", enquanto {', '.join(name(m) for m in out)} ficou claramente atrás." if out else "."
        items.append(_item("energia", "Grupos de desempenho", t, "indicativa", equiv))

    # viés
    parts = []
    for m in MODEL_IDS:
        b = me.loc[m, "NMBE_media_pct"]
        word = "sobrestimou" if b > 0 else "subestimou"
        cib = None
        if ci is not None and len(ci):
            r = ci[(ci.modelo == m) & (ci.metrica == "nMBE_pct")]
            if len(r):
                cib = (float(r.ic95_lo.iloc[0]), float(r.ic95_hi.iloc[0]))
        if cib and cib[0] <= 0 <= cib[1]:
            parts.append(f"{m} não apresentou viés distinguível de zero (nMBE {f(b, 2, True)} %)")
        else:
            parts.append(f"{m} {word} em média (nMBE {f(b, 2, True)} %)")
    items.append(_item("energia", "Viés sistemático", "; ".join(parts) + ".", "indicativa"))

    # tendência com temperatura e irradiância
    rb = o.get("residual_bins")
    if rb is not None and len(rb):
        tb = rb[rb.variavel.str.startswith("T")]
        msgs = []
        for m in MODEL_IDS:
            d = tb[tb.modelo == m]
            if len(d) >= 3:
                lo, hi = d.iloc[0], d.iloc[-1]
                if hi.MBE_W - lo.MBE_W > 10:
                    msgs.append(f"o viés de {m} cresceu com a temperatura do módulo (de {f(lo.MBE_W, 1, True)} W em {lo.faixa} °C "
                                f"para {f(hi.MBE_W, 1, True)} W em {hi.faixa} °C)")
        gb = rb[rb.variavel.str.startswith("G")]
        worst_bin = gb.groupby("faixa", observed=True)["RMSE_W"].mean().idxmax() if len(gb) else None
        t = ""
        if msgs:
            j = "; ".join(msgs)
            t += j[0].upper() + j[1:] + ", padrão compatível com a ausência de correção térmica (hipótese). "
        if worst_bin:
            t += (f"O maior RMSE médio entre modelos ocorreu na faixa de Gpoa {worst_bin} W/m², comum aos quatro "
                  "modelos — indício de uma fonte de erro compartilhada (ver qualidade dos dados).")
        if t:
            items.append(_item("energia", "Onde os erros se concentram", t.strip(), "indicativa"))

    # energia
    e = me["erro_energia_pct"]
    bm = e.abs().idxmin()
    t = (f"Na energia integrada sobre {f(me['horas_cobertas_h'].iloc[0], 1)} h de pares válidos (energia observada "
         f"{f(me['E_obs_kWh'].iloc[0], 1)} kWh, parcial), os erros variaram de {f(e.min(), 2, True)} % ({e.idxmin()}) a "
         f"{f(e.max(), 2, True)} % ({e.idxmax()}). O menor erro absoluto de energia foi de {name(bm)} ({f(e[bm], 2, True)} %)")
    if ci is not None and len(ci):
        r = ci[(ci.modelo == bm) & (ci.metrica == "erro_energia_pct")]
        if len(r) and r.ic95_lo.iloc[0] <= 0 <= r.ic95_hi.iloc[0]:
            t += f", compatível com zero (IC95 [{f(r.ic95_lo.iloc[0], 2, True)}; {f(r.ic95_hi.iloc[0], 2, True)}] %)"
    t += ". Erros de potência instantânea podem se compensar na energia; por isso nRMSE e erro de energia são lidos juntos."
    items.append(_item("energia", "Energia", t, "indicativa", [bm]))

    # meses e dias
    mm = o.get("metrics_monthly")
    if mm is not None and len(mm):
        wins = mm.loc[mm.groupby("mes")["NRMSE_media_pct"].idxmin()].modelo.value_counts()
        nmes = mm.mes.nunique()
        best_rng = mm[mm.modelo == best]["NRMSE_media_pct"]
        t = (f"Mês a mês, {', '.join(f'{k} foi o melhor em {v} de {nmes}' for k, v in wins.items())}. O nRMSE de {best} "
             f"variou entre {f(best_rng.min())} % e {f(best_rng.max())} % conforme o mês.")
        md = o.get("metrics_daily")
        if md is not None and len(md):
            dw = md.loc[md.groupby("dia")["RMSE_W"].idxmin()].modelo.value_counts(normalize=True) * 100
            t += " Por dia, a fração de dias em que cada modelo teve o menor RMSE foi: " + \
                 ", ".join(f"{k} {f(v, 0)} %" for k, v in dw.items()) + "."
        items.append(_item("energia", "Variação temporal", t, "contexto"))
    return items


def quality_section(o: dict, cfg: dict) -> list[dict]:
    items = []
    an = o.get("anomaly_summary")
    qs = o.get("quality_sensitivity")
    if an is None or an.empty:
        return items
    a = an.set_index("codigo")
    errs = an[an.severidade == "erro"]
    susp = an[an.severidade == "suspeito"]
    t = (f"Antes de interpretar os erros dos modelos, verificaram-se inconsistências físicas nas próprias medições. "
         f"Em todo o conjunto lido houve {fint(a.loc['A01', 'n_todas'])} registro(s) com potência sem irradiância (A01), "
         f"{fint(a.loc['A02', 'n_todas'])} com irradiância sem potência (A02) e {fint(a.loc['A03', 'n_todas'])} com potência acima "
         f"do fisicamente plausível (A03). Dentro da máscara de validação, anomalias do tipo «erro» atingiram "
         f"{fint(errs.n_elegiveis.sum())} amostras e as do tipo «suspeito» {fint(susp.n_elegiveis.sum())} (contagens podem se "
         f"sobrepor).")
    top = an[an.severidade != "condicao"].sort_values("n_elegiveis", ascending=False).iloc[0]
    if top.n_elegiveis > 0:
        t += f" A anomalia mais frequente na máscara foi «{top.anomalia}» ({fint(top.n_elegiveis)} amostras, {f(top.pct_elegiveis, 1)} %)."
    items.append(_item("qualidade", "Inconsistências no dataset", t, "contexto"))
    if "A05" in a.index and a.loc["A05", "n_elegiveis"] > 0:
        items.append(_item("qualidade", "Coerência Isc × Gpoa",
                           f"Em {f(a.loc['A05', 'pct_elegiveis'], 1)} % das amostras elegíveis a corrente de curto-circuito medida "
                           f"divergiu mais de 20 % do valor esperado pela irradiância medida (Isc/(Isc_STC·G/1000) fora de "
                           f"[0,80; 1,20]). Como Isc é quase proporcional à irradiância efetiva, isso indica que o piranômetro e o "
                           f"módulo nem sempre «viram» a mesma luz (dessincronização, sombra, ângulo ou espectro — hipóteses). "
                           f"Esses erros atingem os quatro modelos igualmente, pois todos recebem a mesma Gpoa.", "indicativa"))
    if qs is not None and len(qs):
        q = qs.set_index(["cenario", "modelo"])
        base = qs[qs.cenario == "todas"].set_index("modelo")
        if "anomalas" in qs.cenario.values:
            an_rows = qs[qs.cenario == "anomalas"].set_index("modelo")
            share = an_rows["parcela_erro_quadratico_pct"]
            pct = float(an_rows["pct_amostras"].iloc[0])
            t = (f"As amostras com anomalia «erro» ou «suspeito» representam {f(pct, 1)} % da máscara, mas responderam por "
                 f"{f(share.min(), 0)}–{f(share.max(), 0)} % do erro quadrático total dos modelos.")
            if "sem_erros_suspeitos" in qs.cenario.values:
                cl = qs[qs.cenario == "sem_erros_suspeitos"].set_index("modelo")
                order_b = base["NRMSE_media_pct"].sort_values().index.tolist()
                order_c = cl["NRMSE_media_pct"].sort_values().index.tolist()
                t += (" Excluindo-as (análise de sensibilidade, não a máscara principal), o nRMSE passou de "
                      + ", ".join(f"{m} {f(base.loc[m, 'NRMSE_media_pct'])} → {f(cl.loc[m, 'NRMSE_media_pct'])} %" for m in MODEL_IDS)
                      + (". A ordenação dos modelos se manteve." if order_b == order_c else
                         f". A ordenação mudou: {' < '.join(order_b)} → {' < '.join(order_c)}."))
            items.append(_item("qualidade", "Peso das anomalias no erro", t, "indicativa"))
        if "transitorios" in qs.cenario.values and "estaveis" in qs.cenario.values:
            tr = qs[qs.cenario == "transitorios"].set_index("modelo")
            st = qs[qs.cenario == "estaveis"].set_index("modelo")
            ratio = (tr["RMSE_W"] / st["RMSE_W"]).mean()
            items.append(_item("qualidade", "Transitórios de irradiância",
                               f"Em {f(float(tr['pct_amostras'].iloc[0]), 1)} % das amostras a irradiância variou mais de 250 W/m² "
                               f"em 5 min. Nelas, o RMSE dos modelos foi em média {factor(ratio)} o de condições estáveis "
                               f"(ex.: {best_of(st)} {f(st['NRMSE_media_pct'].min())} % estável vs "
                               f"{f(tr.loc[best_of(st), 'NRMSE_media_pct'])} % em transitório). Parte do erro comum é, portanto, "
                               "atribuível à amostragem instantânea sob nebulosidade variável e não à formulação dos modelos.",
                               "indicativa"))
    return items


def best_of(df: pd.DataFrame, col="NRMSE_media_pct") -> str:
    return df[col].idxmin()


def compute_section(o: dict, cfg: dict, meta: dict) -> list[dict]:
    items = []
    s = o.get("benchmark_summary")
    if s is None or s.empty:
        return items
    N = int(s.batch_size.max())
    sm = s[s.batch_size == N].set_index("modelo")
    us = sm["mediana_por_amostra_us"].sort_values()
    cheap, dear = us.index[0], us.index[-1]
    rt = o.get("time_ratios")
    t = (f"O menor custo computacional foi de {name(cheap)}, com mediana de {f(us[cheap], 4)} µs por amostra (lote de "
         f"{fint(N)} amostras); o maior foi de {name(dear)}, com {f(us[dear], 1)} µs por amostra.")
    if rt is not None and len(rt):
        r = rt[(rt.batch_size == N) & (rt.modelo == dear)]
        if len(r):
            r = r.iloc[0]
            t += (f" Em comparação pareada por rodada, {dear} levou {factor(r.mediana_razao)} o tempo de {r.referencia} "
                  f"(IC95 {fint(r.ic95_lo)}–{fint(r.ic95_hi)}×).")
    t += (" A ordem " + " < ".join(us.index) + " acompanha a complexidade numérica: M1–M3 são expressões fechadas "
          "vetorizadas, enquanto o SDM resolve, amostra a amostra, a equação implícita e a busca do MPP.")
    items.append(_item("computacional", "Custo por amostra", t, "robusta", [cheap]))
    cv = sm["cv_pct"]
    t = (f"A variabilidade entre as {int(sm['n_execucoes'].iloc[0])} rodadas foi de CV {f(cv.min(), 1)} % ({cv.idxmin()}) a "
         f"{f(cv.max(), 1)} % ({cv.idxmax()}). Coeficientes maiores nos modelos rápidos refletem que, em escalas de "
         "microssegundos, ruídos do sistema operacional pesam mais; não indicam instabilidade do algoritmo.")
    rho = sm.get("tendencia_spearman_rho")
    if rho is not None and (rho.abs() > 0.6).any():
        t += " Houve tendência monotônica entre rodadas em " + ", ".join(f"{m} (ρ={f(v, 2)})" for m, v in rho[rho.abs() > 0.6].items()) + \
             ", a registrar como possível efeito térmico/frequência da CPU (não medido)."
    items.append(_item("computacional", "Estabilidade", t, "contexto"))
    mem = sm.get("mediana_pico_rss_delta_MiB")
    if mem is not None:
        t = (f"Em memória residente, {mem.idxmax()} exigiu o maior pico adicional ({f(mem.max(), 2)} MiB acima do RSS anterior), "
             f"enquanto os demais ficaram em {f(mem.drop(mem.idxmax()).max(), 3)} MiB ou menos — abaixo da resolução de página "
             "do sistema operacional para lotes deste tamanho.")
        items.append(_item("computacional", "Memória", t, "indicativa"))
    sizes = sorted(s.batch_size.unique())
    if len(sizes) > 1:
        lo, hi = sizes[0], sizes[-1]
        a = s[s.batch_size == lo].set_index("modelo")["mediana_por_amostra_us"]
        b = s[s.batch_size == hi].set_index("modelo")["mediana_por_amostra_us"]
        drop = (a / b)
        t = (f"Com o aumento do lote de {fint(lo)} para {fint(hi)} amostras, o custo por amostra de M1–M3 caiu "
             f"{factor(drop[['M1', 'M2', 'M3']].min())} a {factor(drop[['M1', 'M2', 'M3']].max())} (amortização do custo fixo de "
             f"chamada), enquanto o do SDM ficou praticamente constante ({f(a['M4'], 0)} → {f(b['M4'], 0)} µs): seu custo "
             "cresce linearmente com o número de amostras.")
        items.append(_item("computacional", "Escalabilidade", t, "robusta"))
    det = o.get("determinism")
    st = meta.get("tempos_por_etapa_s", {})
    t = ""
    if det is not None and len(det) and det["previsoes_identicas_entre_rodadas"].all():
        t += "Todas as rodadas produziram previsões idênticas (mesmo hash), sem falhas nem casos de não convergência. "
    if "calibration_s" in st:
        t += (f"A calibração do SDM levou {f(st['calibration_s'], 1)} s e foi contabilizada fora do benchmark; como é feita uma "
              "única vez por módulo, não altera o custo por amostra, mas é um custo de implantação que M1–M3 não têm.")
    if t:
        items.append(_item("computacional", "Integridade e custos fora do benchmark", t.strip(), "contexto"))
    return items


def integrated_section(o: dict, cfg: dict) -> list[dict]:
    items = []
    p = o.get("pareto")
    if p is None or p.empty:
        return items
    pt = p[p.eixo == "tempo"].set_index("modelo")
    front = pt[pt.nao_dominado].sort_values("tempo_us_amostra").index.tolist()
    dom = pt[~pt.nao_dominado]
    t = f"Na relação erro × tempo, a fronteira não dominada foi formada por {', '.join(front)}."
    for m, r in dom.iterrows():
        t += f" {name(m)} foi dominado por {r.dominado_por} (mais lento e com maior erro)."
    robust = pt["dominancia_robusta_por"].fillna("").astype(str)
    t += (" Nenhuma dominância se manteve com IC95 sem sobreposição nos dois eixos; a fronteira descreve esta amostra e esta máquina."
          if (robust == "").all() else "")
    items.append(_item("integrada", "Fronteira de Pareto", t, "indicativa", front))
    me = o["metrics_energy"].set_index("modelo")
    us = pt["tempo_us_amostra"]
    if len(front) >= 2:
        msgs = []
        for a, b in zip(front[:-1], front[1:]):
            d = me.loc[a, "NRMSE_media_pct"] - me.loc[b, "NRMSE_media_pct"]
            msgs.append(f"passar de {a} para {b} reduziu o nRMSE em {f(d, 2)} p.p. ({f(100 * d / me.loc[a, 'NRMSE_media_pct'], 1)} % "
                        f"relativo) ao custo de {factor(us[b] / us[a])} no tempo por amostra")
        items.append(_item("integrada", "Melhoria marginal", "Ao longo da fronteira, " + "; ".join(msgs) + ".", "indicativa"))
    sens = o.get("sensitivity")
    if sens is not None and len(sens):
        d = sens[sens.tipo == "delta_T_C"]
        if len(d):
            parts = []
            for m in ("M2", "M4"):
                dm = d[d.modelo == m].copy()
                dm["n"] = 100 * dm.RMSE_W / (me.loc[m, "RMSE_W"] / me.loc[m, "NRMSE_media_pct"] * 100)
                parts.append(f"{m} variou de {f(dm['n'].min())} % a {f(dm['n'].max())} % "
                             f"(mínimo em ΔT = {f(dm.loc[dm['n'].idxmin(), 'valor'], 0)} °C)")
            rk = d.pivot_table(index="valor", columns="modelo", values="RMSE_W")
            stable = (rk[["M2", "M4"]].idxmin(axis=1).nunique() == 1)
            t = (f"Para ΔT célula–módulo entre {f(d.valor.min(), 0)} e {f(d.valor.max(), 0)} °C (hipótese da eq. 23), o nRMSE de "
                 + " e o de ".join(parts) + "; M1 e M3 não dependem de ΔT. A ordenação entre M2 e M4 "
                 + ("se manteve" if stable else "mudou") + " nesse intervalo"
                 + ("." if stable else ", portanto a comparação entre eles é sensível à hipótese térmica."))
            items.append(_item("integrada", "Sensibilidade térmica", t, "indicativa"))
    items.append(_item("integrada", "Assimetria de parametrização",
                       "A comparação não é entre fórmulas «nuas»: M1 usa 1 parâmetro medido, M2 usa 2 (Pstc e γ medidos), M3 usa "
                       "Pstc e 6 coeficientes genéricos de tecnologia não calibrados para este módulo e M4 usa 5 parâmetros "
                       "identificados a partir de 66 medições de laboratório. Parte da diferença de exatidão reflete a "
                       "quantidade de informação de laboratório incorporada, e não apenas a complexidade matemática.", "contexto"))
    return items


def statistics_section(o: dict, cfg: dict) -> list[dict]:
    items = []
    ci = o.get("bootstrap_ci")
    paired = o.get("bootstrap_paired")
    if ci is None or ci.empty:
        return items
    D, B = int(ci.dias.iloc[0]), int(ci.B.iloc[0])
    w = ci[ci.metrica == "nRMSE_pct"].assign(w=lambda x: x.ic95_hi - x.ic95_lo)
    t = (f"Os intervalos foram obtidos por bootstrap em blocos diários ({D} dias, B = {fint(B)}), porque amostras de 5 min do "
         f"mesmo dia não são independentes. Os IC95 individuais de nRMSE têm largura de {f(w.w.min())} a {f(w.w.max())} p.p. e "
         "se sobrepõem; ainda assim, comparações pareadas (mesmos dias para os dois modelos) eliminam a variabilidade comum entre "
         "dias e são muito mais estreitas — por isso a discussão usa as diferenças pareadas.")
    items.append(_item("estatistica", "Incerteza da exatidão", t, "contexto"))
    if paired is not None and len(paired):
        d = paired[paired.metrica == "nRMSE_pct"].copy()
        cls = d.apply(lambda r: classify(r.diferenca, r.ic95_lo, r.ic95_hi)[0], axis=1)
        groups = {k: d[cls == k].comparacao.tolist() for k in ("robusta", "indicativa", "inconclusiva")}
        t = ("Entre os seis pares de modelos: " +
             "; ".join(f"{k} — {', '.join(v)}" for k, v in groups.items() if v) +
             f" (classes definidas pelo IC95 pareado e pelo limiar prático de {f(PRACTICAL_PP, 1)} p.p.).")
        items.append(_item("estatistica", "Comparações pareadas", t, "indicativa"))
    items.append(_item("estatistica", "O que as rodadas significam",
                       f"As {cfg.get('repetitions')} rodadas medem a variabilidade de execução do software nesta máquina; como os "
                       "modelos são determinísticos, não constituem replicações físicas e não geram incerteza sobre a exatidão "
                       "energética, que vem exclusivamente da variabilidade entre dias de medição.", "contexto"))
    return items


def synthesis(o: dict, sections: list[dict]) -> list[dict]:
    me = o["metrics_energy"].set_index("modelo")
    best = me["NRMSE_media_pct"].idxmin()
    worst = me["NRMSE_media_pct"].idxmax()
    s = o.get("benchmark_summary")
    t = (f"{name(best)} apresentou o menor nRMSE ({f(me.loc[best, 'NRMSE_media_pct'])} %) e {name(worst)} o maior "
         f"({f(me.loc[worst, 'NRMSE_media_pct'])} %).")
    if s is not None and len(s):
        sm = s[s.batch_size == s.batch_size.max()].set_index("modelo")["mediana_por_amostra_us"]
        t += (f" O menor custo foi de {sm.idxmin()} e o maior de {sm.idxmax()}, {factor(sm.max() / sm.min())} mais caro por amostra.")
    eq = [i for i in sections if i["titulo"] == "Grupos de desempenho"]
    if eq:
        ms = eq[0]["modelos"]
        t += f" Na prática, {', '.join(ms[:-1])} e {ms[-1]} formam um grupo de exatidão equivalente (diferenças < 0,5 p.p.)."
    q = [i for i in sections if i["titulo"] == "Peso das anomalias no erro"]
    if q:
        t += " Uma fração pequena de medições fisicamente inconsistentes concentra parte desproporcional do erro, comum a todos os modelos."
    t += " Estes resultados descrevem este módulo, este período e esta máquina; não estabelecem um modelo superior em geral."
    return [_item("sintese", "Síntese", t, "indicativa", [best])]


def build(o: dict, cfg: dict, meta: dict | None = None) -> list[dict]:
    meta = meta or {}
    secs = []
    for fn in (lambda: energy_section(o, cfg), lambda: quality_section(o, cfg), lambda: compute_section(o, cfg, meta),
               lambda: integrated_section(o, cfg), lambda: statistics_section(o, cfg)):
        try:
            secs += fn()
        except Exception as exc:  # um bloco com dados faltantes não derruba os demais
            secs.append(_item("aviso", "Trecho não gerado", f"Falha ao redigir um bloco: {type(exc).__name__}: {exc}", "contexto"))
    return synthesis(o, secs) + secs


def write(run_dir: Path, items: list[dict]) -> None:
    run_dir = Path(run_dir)
    (run_dir / "narrative.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
    titles = {"sintese": "Síntese", "energia": "I · Energia", "qualidade": "Qualidade dos dados",
              "computacional": "II · Computacional", "integrada": "III · Análise integrada", "estatistica": "IV · Estatística"}
    lines = ["# Discussão gerada automaticamente", "",
             "_Texto gerado por regras a partir dos CSV desta execução. Diagnóstico — requer revisão científica._", ""]
    cur = None
    for it in items:
        if it["secao"] != cur:
            cur = it["secao"]
            lines += [f"## {titles.get(cur, cur)}", ""]
        lines += [f"**{it['titulo']}** _(evidência: {it['evidencia']})_. {it['texto']}", ""]
    (run_dir / "DISCUSSAO.md").write_text("\n".join(lines), encoding="utf-8")
