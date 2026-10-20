"""Figuras Plotly da interface (tema CIM26, claro/escuro, rótulos pt-BR).

Todas as figuras: zoom, hover, legenda clicável (liga/desliga séries), exportação SVG
pela barra do gráfico. Lacunas temporais nunca são ligadas e o preenchimento da
irradiância é desenhado por trechos contínuos (nada é inventado à noite).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from cim26.pvcore.models import MODEL_IDS, MODEL_INFO

from .theme import MODEL_COLORS, SEV_COLORS, SUN, is_dark, plotly_config, plotly_layout

DATE_STOPS = [dict(dtickrange=[None, 43200000], value="%H:%M<br>%d/%m"), dict(dtickrange=[43200000, "M1"], value="%d/%m"),
              dict(dtickrange=["M1", None], value="%m/%Y")]


def ink() -> str:
    return "#E3EAF1" if is_dark() else "#13202D"


def base(height: int = 380, **kw) -> go.Figure:
    fig = go.Figure()
    lay = plotly_layout()
    lay.update(height=height)
    for k, v in kw.items():
        if isinstance(v, dict) and isinstance(lay.get(k), dict):
            lay[k] = {**lay[k], **v}
        else:
            lay[k] = v
    fig.update_layout(**lay)
    return fig


def show(fig: go.Figure, name: str, key: str | None = None) -> None:
    st.plotly_chart(fig, theme=None, config=plotly_config(name), key=key, width="stretch")


def _ts(ts) -> list:
    return pd.to_datetime(pd.Series(ts)).dt.strftime("%Y-%m-%dT%H:%M:%S").tolist()


def gapped(ts, ys, max_gap_min: float):
    t = pd.to_datetime(pd.Series(ts)).reset_index(drop=True)
    y = np.asarray(ys, float)
    gap = (t.diff().dt.total_seconds() / 60.0 > max_gap_min).to_numpy()
    xs, vs = [], []
    for i in range(len(t)):
        if gap[i]:
            xs.append((t.iloc[i - 1] + pd.Timedelta(seconds=1)).isoformat()); vs.append(None)
        xs.append(t.iloc[i].isoformat()); vs.append(None if not np.isfinite(y[i]) else float(y[i]))
    return xs, vs


def segments(ts, ys, max_gap_min: float):
    t = pd.to_datetime(pd.Series(ts)).reset_index(drop=True)
    y = np.asarray(ys, float)
    segs, cur = [], ([], [])
    for i in range(len(t)):
        brk = i > 0 and (t.iloc[i] - t.iloc[i - 1]).total_seconds() / 60.0 > max_gap_min
        if (brk or not np.isfinite(y[i])) and cur[0]:
            segs.append(cur); cur = ([], [])
        if np.isfinite(y[i]):
            cur[0].append(t.iloc[i].isoformat()); cur[1].append(float(y[i]))
    if cur[0]:
        segs.append(cur)
    return segs


def add_fill(fig, ts, ys, gap, name, axis="y2", color=SUN, alpha=.14):
    for k, (x, y) in enumerate(segments(ts, ys, gap)):
        fig.add_scatter(x=x, y=y, name=name, yaxis=axis, mode="lines", line=dict(color=color, width=1), fill="tozeroy",
                        fillcolor=f"rgba(242,169,0,{alpha})", legendgroup=name, showlegend=k == 0,
                        hovertemplate="%{y:.0f} W/m²<extra>" + name + "</extra>")


def power_series(ts, lines: list[tuple], gap: float, g=None, tcell=None, obs=None, anomalies=None, marker_x=None,
                 height=440, ytitle="Potência [W]", rangeslider=True) -> go.Figure:
    both = g is not None and tcell is not None
    fig = base(height, hovermode="x unified", margin=dict(r=110 if both else 66),
               xaxis=dict(domain=[0, 0.9 if both else 1], tickformatstops=DATE_STOPS, hoverformat="%d/%m/%Y %H:%M",
                          rangeslider=dict(visible=rangeslider, thickness=0.05)),
               yaxis=dict(title=dict(text=ytitle), rangemode="tozero"),
               yaxis2=dict(title=dict(text="Gpoa [W/m²]" if g is not None else "Tcell [°C]"), overlaying="y", side="right",
                           rangemode="tozero", showgrid=False),
               yaxis3=dict(title=dict(text="Tcell [°C]"), overlaying="y", side="right", anchor="free", position=1, showgrid=False))
    if g is not None:
        add_fill(fig, ts, g, gap, "Irradiância POA")
    if tcell is not None:
        x, y = gapped(ts, tcell, gap)
        fig.add_scatter(x=x, y=y, name="Tcell", yaxis="y3" if both else "y2", line=dict(color="#B83A3A", width=1.2, dash="dot"),
                        hovertemplate="%{y:.1f} °C<extra>Tcell</extra>")
    if obs is not None:
        x, y = gapped(ts, obs, gap)
        fig.add_scatter(x=x, y=y, name="Medida", line=dict(color=ink(), width=2.4), hovertemplate="%{y:.1f} W<extra>medida</extra>")
    for name, ys, color, width in lines:
        x, y = gapped(ts, ys, gap)
        fig.add_scatter(x=x, y=y, name=name, line=dict(color=color, width=width), hovertemplate="%{y:.1f} W<extra>" + name + "</extra>")
    if anomalies is not None and len(anomalies):
        a = anomalies
        fig.add_scatter(x=_ts(a["timestamp"]), y=a["y"], mode="markers", name="anomalia de medição",
                        marker=dict(symbol="diamond", size=10, color=[SEV_COLORS.get(s, "#7F92A4") for s in a["sev"]],
                                    line=dict(color="#fff", width=1)), text=a["text"], hovertemplate="%{text}<extra></extra>")
    if marker_x is not None:
        fig.add_vline(x=marker_x, line=dict(color=MODEL_COLORS["M4"], width=1.5, dash="dot"))
    return fig


def iv_animation(frames: list[dict], labels: list[str], vmax: float, imax: float, pmax: float, start: int = 0) -> go.Figure:
    """Curvas I–V/P–V do SDM com quadros Plotly (play/pausa e cursor rodam no navegador)."""
    def traces(fr):
        return [go.Scatter(x=fr["V"], y=fr["I"], name="I–V", line=dict(color=MODEL_COLORS["M4"], width=2.8),
                           hovertemplate="%{x:.1f} V · %{y:.2f} A<extra></extra>"),
                go.Scatter(x=fr["V"], y=fr["P"], name="P–V", yaxis="y2", line=dict(color=ink(), width=1.6, dash="dash"),
                           hovertemplate="%{y:.1f} W<extra></extra>"),
                go.Scatter(x=[fr["mpp"]["Vmp"]], y=[fr["mpp"]["Pmp"]], yaxis="y2", mode="markers+text",
                           text=[f"MPP {fr['mpp']['Pmp']:.1f} W".replace(".", ",")], textposition="top center",
                           marker=dict(size=12, color=SUN, line=dict(color="#13202D", width=1.5)), showlegend=False, hoverinfo="skip")]
    fig = base(420, margin=dict(r=66, b=110), xaxis=dict(title=dict(text="Tensão do arranjo [V]"), range=[0, vmax]),
               yaxis=dict(title=dict(text="Corrente [A]"), range=[0, imax]),
               yaxis2=dict(title=dict(text="Potência [W]"), overlaying="y", side="right", range=[0, pmax], showgrid=False))
    for tr in traces(frames[start]):
        fig.add_trace(tr)
    fig.frames = [go.Frame(data=traces(fr), name=str(i)) for i, fr in enumerate(frames)]
    anim = dict(frame=dict(duration=110, redraw=True), transition=dict(duration=60), mode="immediate")
    fig.update_layout(
        updatemenus=[dict(type="buttons", direction="left", x=0, y=-0.2, xanchor="left", yanchor="top", showactive=False,
                          bgcolor="#13202D", font=dict(color="#fff"), pad=dict(r=8, t=4),
                          buttons=[dict(label="▶  Reproduzir dia", method="animate", args=[None, {**anim, "fromcurrent": True}]),
                                   dict(label="❚❚  Pausar", method="animate", args=[[None], {**anim, "frame": dict(duration=0)}])])],
        sliders=[dict(active=start, x=0.26, y=-0.13, len=0.74, pad=dict(t=26), ticklen=3, font=dict(size=10),
                      currentvalue=dict(prefix="Instante: ", xanchor="right", font=dict(size=12)),
                      steps=[dict(label=labels[i], method="animate", args=[[str(i)], {**anim, "frame": dict(duration=0)}])
                             for i in range(len(frames))])])
    return fig


def hist_band(values: np.ndarray, lo: float, hi: float, band: tuple, xtitle: str, height=230) -> go.Figure:
    edges = np.linspace(lo, hi, 49)
    counts, _ = np.histogram(values, bins=edges)
    mids = (edges[:-1] + edges[1:]) / 2
    fig = base(height, margin=dict(t=10, b=40), xaxis=dict(title=dict(text=xtitle)), yaxis=dict(title=dict(text="amostras")), bargap=0.05)
    fig.add_bar(x=mids, y=counts, marker_color=["#B83A3A" if (m < band[0] or m > band[1]) else "#3B82C4" for m in mids],
                hovertemplate="%{x:.2f}: %{y}<extra></extra>")
    fig.add_vrect(x0=band[0], x1=band[1], fillcolor="rgba(30,158,122,.08)", line_width=0)
    return fig


def day_explorer(d: pd.DataFrame, show_g=True, show_isc=False, show_t=False, isc_stc=9.4868) -> go.Figure:
    gap = 7.5
    fig = base(450, hovermode="x unified", margin=dict(r=110 if show_t else 66),
               xaxis=dict(domain=[0, 0.9 if show_t else 1], tickformatstops=DATE_STOPS, hoverformat="%H:%M"),
               yaxis=dict(title=dict(text="Potência [W]"), rangemode="tozero"),
               yaxis2=dict(title=dict(text="Irradiância [W/m²]"), overlaying="y", side="right", rangemode="tozero", showgrid=False),
               yaxis3=dict(title=dict(text="°C"), overlaying="y", side="right", anchor="free", position=1, showgrid=False))
    ts = d["timestamp"]
    if show_g:
        add_fill(fig, ts, d["g_poa_Wm2"], gap, "Gpoa", alpha=.15)
    if show_isc:
        x, y = gapped(ts, d["isc_measured_A"] * 1000 / isc_stc, gap)
        fig.add_scatter(x=x, y=y, name="Isc → irradiância equivalente", yaxis="y2", line=dict(color="#7E57C2", width=1.4, dash="dot"),
                        hovertemplate="%{y:.0f} W/m² eq.<extra>Isc</extra>")
    if show_t:
        for col, name, color in (("t_module_C", "Tbom", "#B4507A"), ("t_amb_C", "Tamb", "#3B82C4")):
            x, y = gapped(ts, d[col], gap)
            fig.add_scatter(x=x, y=y, name=name, yaxis="y3", line=dict(color=color, width=1.2))
    x, y = gapped(ts, d["p_mpp_measured_W"], gap)
    fig.add_scatter(x=x, y=y, name="Pm medida", line=dict(color=ink(), width=2.3), hovertemplate="%{y:.1f} W<extra>Pm</extra>")
    ex = d[~d["eligible"]]
    fig.add_scatter(x=_ts(ex["timestamp"]), y=ex["p_mpp_measured_W"].fillna(0), mode="markers", name="fora da máscara",
                    marker=dict(symbol="x-thin", size=9, line=dict(width=1.6, color="#8A99A7")), text=ex["reasons"],
                    hovertemplate="excluída: %{text}<extra></extra>")
    an = d[d["anom_severidade"].isin(["erro", "suspeito"])]
    fig.add_scatter(x=_ts(an["timestamp"]), y=an["p_mpp_measured_W"].fillna(0), mode="markers", name="anomalia física",
                    marker=dict(symbol="diamond", size=10, color=[SEV_COLORS[s] for s in an["anom_severidade"]], line=dict(color="#fff", width=1)),
                    text=an["anom_codes"], hovertemplate="%{text}<extra></extra>")
    return fig


def heat_matrix(mat: pd.DataFrame, title: str, digits: int) -> go.Figure:
    fig = base(270, margin=dict(t=34, l=52, b=30), title=dict(text=title, x=0, font=dict(size=13)),
               yaxis=dict(title=dict(text="G [W/m²]")))
    z = mat.values
    fig.add_heatmap(z=z, x=[f"{c:g} °C" for c in mat.columns], y=[f"{i:g}" for i in mat.index], showscale=False,
                    colorscale=[[0, "#EAF1F7"], [1, "#1A5276"]], text=[["" if np.isnan(v) else f"{v:.{digits}f}".replace(".", ",") for v in r] for r in z],
                    texttemplate="%{text}", textfont=dict(size=11), hovertemplate="G=%{y} · %{x}: %{z:.4f}<extra></extra>")
    return fig


def bars(df: pd.DataFrame, x: str, y: str, ytitle: str, height=320, horizontal=False, xtitle=None, margin_l=None) -> go.Figure:
    fig = base(height, barmode="group", margin=dict(l=margin_l) if margin_l else {},
               xaxis=dict(title=dict(text=ytitle if horizontal else (xtitle or ""))),
               yaxis=dict(title=dict(text="" if horizontal else ytitle), autorange="reversed" if horizontal else True))
    for m in MODEL_IDS:
        d = df[df.modelo == m]
        if horizontal:
            fig.add_bar(y=d[x].astype(str), x=d[y], name=m, orientation="h", marker_color=MODEL_COLORS[m])
        else:
            fig.add_bar(x=d[x].astype(str), y=d[y], name=m, marker_color=MODEL_COLORS[m])
    return fig


def lines(df: pd.DataFrame, x: str, y: str, xtitle: str, ytitle: str, height=320, logx=False, logy=False, dates=False) -> go.Figure:
    fig = base(height, xaxis=dict(title=dict(text=xtitle), type="log" if logx else ("date" if dates else None),
                                  tickformatstops=DATE_STOPS if dates else None),
               yaxis=dict(title=dict(text=ytitle), type="log" if logy else None))
    for m in MODEL_IDS:
        d = df[df.modelo == m].sort_values(x)
        fig.add_scatter(x=d[x], y=d[y], name=m, mode="lines+markers", line=dict(color=MODEL_COLORS[m], width=1.6), marker=dict(size=5))
    return fig


def boxes(df: pd.DataFrame, y: str, ytitle: str, log=False, height=320) -> go.Figure:
    fig = base(height, showlegend=False, yaxis=dict(title=dict(text=ytitle), type="log" if log else None))
    for m in MODEL_IDS:
        fig.add_box(y=df[df.modelo == m][y], name=m, marker_color=MODEL_COLORS[m], boxpoints="all", jitter=0.5, pointpos=0)
    return fig


def rounds(main: pd.DataFrame) -> go.Figure:
    fig = base(320, xaxis=dict(title=dict(text="Rodada"), dtick=1), yaxis=dict(title=dict(text="compute_s ÷ mediana do modelo")))
    for m in MODEL_IDS:
        d = main[main.modelo == m].sort_values("rodada")
        fig.add_scatter(x=d["rodada"], y=d["compute_s"] / d["compute_s"].median(), name=m, mode="lines+markers",
                        line=dict(color=MODEL_COLORS[m]), customdata=np.c_[d["posicao"], d["compute_s"]],
                        hovertemplate="rodada %{x} · posição %{customdata[0]}<br>%{customdata[1]:.6f} s<extra>" + m + "</extra>")
    fig.add_hline(y=1, line=dict(color="#8A99A7", width=1))
    return fig


def pareto(p: pd.DataFrame, xcol: str, xtitle: str, log: bool, nrmse: dict, scale: dict) -> go.Figure:
    fig = base(380, xaxis=dict(title=dict(text=xtitle), type="log" if log else None), yaxis=dict(title=dict(text="nRMSE [%]")), showlegend=False)
    f = p[p.nao_dominado].sort_values(xcol)
    fig.add_scatter(x=f[xcol], y=[nrmse[m] for m in f.modelo], mode="lines", line=dict(color=ink(), dash="dot", width=1), hoverinfo="skip")
    for r in p.itertuples():
        err = None
        if hasattr(r, "RMSE_lo") and pd.notna(r.RMSE_lo):
            err = dict(type="data", symmetric=False, array=[(r.RMSE_hi - r.RMSE_W) * scale[r.modelo]],
                       arrayminus=[(r.RMSE_W - r.RMSE_lo) * scale[r.modelo]], color="#8A99A7", thickness=1)
        fig.add_scatter(x=[getattr(r, xcol)], y=[nrmse[r.modelo]], mode="markers+text", text=[r.modelo], textposition="top right", error_y=err,
                        marker=dict(size=18 if r.nao_dominado else 12, color=MODEL_COLORS[r.modelo], line=dict(color=ink(), width=2 if r.nao_dominado else 0)),
                        hovertemplate=f"{r.modelo}<br>%{{x:.4g}}<br>nRMSE %{{y:.2f}} %<br>{'não dominado' if r.nao_dominado else 'dominado por ' + str(r.dominado_por)}<extra></extra>")
    return fig


def forest(rows: pd.DataFrame, label_col: str, title: str, practical: float | None = None, height=300) -> go.Figure:
    fig = base(height, showlegend=False, margin=dict(l=90), xaxis=dict(title=dict(text=title)), yaxis=dict(autorange="reversed"))
    if practical:
        fig.add_vrect(x0=-practical, x1=practical, fillcolor="rgba(242,169,0,.12)", line_width=0)
        fig.add_vline(x=0, line=dict(color=ink(), width=1))
    for r in rows.itertuples():
        label = getattr(r, label_col)
        color = MODEL_COLORS.get(label, ink() if (r.ic95_lo > 0 or r.ic95_hi < 0) else "#8A99A7")
        est = getattr(r, "estimativa", getattr(r, "diferenca", np.nan))
        fig.add_scatter(x=[est], y=[label], mode="markers", marker=dict(size=12, color=color),
                        error_x=dict(type="data", symmetric=False, array=[r.ic95_hi - est], arrayminus=[est - r.ic95_lo], color="#5E6E7E", thickness=1.5),
                        hovertemplate=f"{label}: %{{x:.3f}} [{r.ic95_lo:.3f}; {r.ic95_hi:.3f}]<extra></extra>")
    return fig


def residual_hist(h: dict) -> go.Figure:
    e = np.asarray(h["edges"])
    mids = (e[:-1] + e[1:]) / 2
    fig = base(300, xaxis=dict(title=dict(text="Resíduo previsto − medido [W]")), yaxis=dict(title=dict(text="amostras")))
    for m in MODEL_IDS:
        fig.add_scatter(x=mids, y=h[m], name=m, mode="lines", line=dict(color=MODEL_COLORS[m], width=1.6, shape="hvh"))
    return fig


def cumulative_energy(daily: pd.DataFrame) -> go.Figure:
    fig = base(320, hovermode="x unified", xaxis=dict(tickformatstops=DATE_STOPS), yaxis=dict(title=dict(text="kWh (pares válidos)")))
    obs = daily[daily.modelo == "M1"].sort_values("dia")
    fig.add_scatter(x=obs["dia"], y=obs["E_obs_kWh"].cumsum(), name="Medida", line=dict(color=ink(), width=2.6))
    for m in MODEL_IDS:
        d = daily[daily.modelo == m].sort_values("dia")
        fig.add_scatter(x=d["dia"], y=d["E_prev_kWh"].cumsum(), name=m, line=dict(color=MODEL_COLORS[m], width=1.5))
    return fig


def scatter_pred_obs(sc: pd.DataFrame) -> go.Figure:
    mx = float(sc["P_obs_W"].max()) * 1.05
    fig = base(340, xaxis=dict(title=dict(text="Medida [W]"), range=[0, mx]), yaxis=dict(title=dict(text="Prevista [W]"), range=[0, mx]))
    for m in MODEL_IDS:
        fig.add_scattergl(x=sc["P_obs_W"], y=sc[f"P_{m}_W"], mode="markers", name=m, marker=dict(size=3, color=MODEL_COLORS[m], opacity=0.35), hoverinfo="skip")
    if "anom_severidade" in sc:
        a = sc[sc["anom_severidade"].isin(["erro", "suspeito"])]
        fig.add_scattergl(x=a["P_obs_W"], y=a["P_M4_W"], mode="markers", name="anomalia (M4)",
                          marker=dict(size=6, symbol="diamond", color=[SEV_COLORS[s] for s in a["anom_severidade"]]))
    fig.add_scatter(x=[0, mx], y=[0, mx], mode="lines", line=dict(color="#8A99A7", width=1), showlegend=False, hoverinfo="skip")
    return fig


def model_label(m: str) -> str:
    return f"{m} {MODEL_INFO[m].short}"
