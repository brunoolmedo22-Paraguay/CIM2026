"""Gráficos Plotly interativos (apenas apresentação; dados vêm do motor/arquivos)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from cim26.pvcore.models import MODEL_IDS, MODEL_INFO

from .style import COLORS, INK, MUTED, OBS, RULE, SUN

FONT = dict(family="Source Sans Pro, Source Sans 3, Arial, sans-serif", size=13, color=INK)
CONFIG = {"displaylogo": False, "toImageButtonOptions": {"format": "svg", "scale": 2},
          "modeBarButtonsToRemove": ["lasso2d", "select2d"]}


def base(fig: go.Figure, height: int = 360, title: str | None = None) -> go.Figure:
    fig.update_layout(template="plotly_white", font=FONT, height=height, margin=dict(l=10, r=10, t=46 if title else 18, b=10),
                      title=dict(text=title, x=0, xanchor="left", font=dict(size=15)) if title else None,
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, font=dict(size=12)),
                      hoverlabel=dict(font_size=12), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#FFFFFF")
    fig.update_xaxes(gridcolor=RULE, linecolor=RULE, zeroline=False)
    fig.update_yaxes(gridcolor=RULE, linecolor=RULE, zeroline=False)
    return fig


def _gapped(t: pd.Series, y: np.ndarray, max_gap_min: float):
    """Insere None nas lacunas para não desenhar linhas sobre a noite/lacunas."""
    t = pd.to_datetime(pd.Series(t)).reset_index(drop=True)
    gap = (t.diff().dt.total_seconds() / 60.0 > max_gap_min).to_numpy()
    xs, ys = [], []
    for i in range(len(t)):
        if gap[i]:
            xs.append(None); ys.append(None)
        xs.append(t.iloc[i]); ys.append(y[i])
    return xs, ys


def power_timeseries(t, obs, preds: dict, max_gap_min: float, title=None, unit="W", height=380):
    fig = go.Figure()
    if obs is not None:
        x, y = _gapped(t, np.asarray(obs, float), max_gap_min)
        fig.add_scatter(x=x, y=y, name="Medida (Pm)", line=dict(color=OBS, width=2.4))
    for m, p in preds.items():
        x, y = _gapped(t, np.asarray(p, float), max_gap_min)
        fig.add_scatter(x=x, y=y, name=f"{m} {MODEL_INFO[m].short}", line=dict(color=COLORS[m], width=1.4))
    fig.update_yaxes(title=f"Potência [{unit}]")
    fig.update_xaxes(rangeslider=dict(visible=True, thickness=0.06))
    return base(fig, height, title)


def cumulative_energy(pred: pd.DataFrame, pairs: np.ndarray):
    t = pd.to_datetime(pred["timestamp"]).reset_index(drop=True)
    dt_h = t.diff().dt.total_seconds().to_numpy()[1:] / 3600.0
    fig = go.Figure()
    for name, col, color, w in [("Medida", "P_obs_W", OBS, 2.4)] + [(m, f"P_{m}_W", COLORS[m], 1.4) for m in MODEL_IDS]:
        p = pred[col].to_numpy(float)
        seg = np.where(pairs, 0.5 * (p[:-1] + p[1:]) * dt_h / 1000.0, 0.0)
        fig.add_scatter(x=t.iloc[1:], y=np.cumsum(seg), name=name, line=dict(color=color, width=w))
    fig.update_yaxes(title="Energia acumulada em pares válidos [kWh]")
    return base(fig, 330)


def scatter_pred_obs(pred: pd.DataFrame, max_points: int = 4000):
    d = pred.sample(min(max_points, len(pred)), random_state=0) if len(pred) > max_points else pred
    fig = make_subplots(rows=1, cols=4, shared_yaxes=True, horizontal_spacing=0.02,
                        subplot_titles=[f"{m} · {MODEL_INFO[m].short}" for m in MODEL_IDS])
    lim = float(np.nanmax(pred["P_obs_W"])) * 1.05
    for i, m in enumerate(MODEL_IDS, 1):
        fig.add_scattergl(x=d["P_obs_W"], y=d[f"P_{m}_W"], mode="markers", marker=dict(size=3, color=COLORS[m], opacity=0.35),
                          showlegend=False, row=1, col=i)
        fig.add_scatter(x=[0, lim], y=[0, lim], mode="lines", line=dict(color=MUTED, width=1), showlegend=False, row=1, col=i)
        fig.update_xaxes(title="Medida [W]", row=1, col=i)
    fig.update_yaxes(title="Prevista [W]", row=1, col=1)
    return base(fig, 300)


def bars_by_group(df: pd.DataFrame, group: str, value: str, ytitle: str, height=320, zero_line=False):
    fig = go.Figure()
    for m in MODEL_IDS:
        d = df[df.modelo == m]
        fig.add_bar(x=d[group].astype(str), y=d[value], name=m, marker_color=COLORS[m])
    fig.update_layout(barmode="group", bargap=0.25)
    fig.update_yaxes(title=ytitle)
    if zero_line:
        fig.add_hline(y=0, line_color=MUTED, line_width=1)
    return base(fig, height)


def lines_by_group(df, x, y, ytitle, height=320, markers=True, log_x=False, log_y=False, xtitle=None):
    fig = go.Figure()
    for m in MODEL_IDS:
        d = df[df.modelo == m].sort_values(x)
        fig.add_scatter(x=d[x], y=d[y], name=m, mode="lines+markers" if markers else "lines",
                        line=dict(color=COLORS[m], width=1.6), marker=dict(size=5))
    fig.update_yaxes(title=ytitle, type="log" if log_y else None)
    fig.update_xaxes(title=xtitle or x, type="log" if log_x else None)
    return base(fig, height)


def box_by_model(df, value, ytitle, log=False, height=330):
    fig = go.Figure()
    for m in MODEL_IDS:
        fig.add_box(y=df[df.modelo == m][value], name=m, marker_color=COLORS[m], boxpoints="all", jitter=0.4,
                    pointpos=0, line=dict(width=1.3))
    fig.update_yaxes(title=ytitle, type="log" if log else None)
    fig.update_layout(showlegend=False)
    return base(fig, height)


def rounds_chart(runs: pd.DataFrame):
    fig = go.Figure()
    for m in MODEL_IDS:
        d = runs[runs.modelo == m].sort_values("rodada")
        rel = d["compute_s"] / d["compute_s"].median()
        fig.add_scatter(x=d["rodada"], y=rel, name=m, mode="lines+markers", line=dict(color=COLORS[m]),
                        customdata=np.c_[d["posicao"], d["compute_s"]],
                        hovertemplate="rodada %{x}<br>posição %{customdata[0]}<br>%{customdata[1]:.6f} s<extra>" + m + "</extra>")
    fig.add_hline(y=1, line_color=MUTED, line_width=1)
    fig.update_yaxes(title="compute_s ÷ mediana do modelo")
    fig.update_xaxes(title="Rodada", dtick=1)
    return base(fig, 320)


def pareto_chart(p: pd.DataFrame, xcol: str, xtitle: str, log_x: bool):
    fig = go.Figure()
    front = p[p.nao_dominado].sort_values(xcol)
    fig.add_scatter(x=front[xcol], y=front["RMSE_W"], mode="lines", line=dict(color=INK, dash="dot", width=1),
                    name="fronteira não dominada", hoverinfo="skip")
    for r in p.itertuples():
        err = dict(type="data", symmetric=False, array=[r.RMSE_hi - r.RMSE_W], arrayminus=[r.RMSE_W - r.RMSE_lo],
                   color=MUTED, thickness=1) if hasattr(r, "RMSE_hi") and pd.notna(r.RMSE_hi) else None
        fig.add_scatter(x=[getattr(r, xcol)], y=[r.RMSE_W], mode="markers+text", text=[r.modelo],
                        textposition="top right", name=r.modelo, error_y=err, showlegend=False,
                        marker=dict(size=16 if r.nao_dominado else 11, color=COLORS[r.modelo],
                                    line=dict(color=INK, width=2 if r.nao_dominado else 0)))
    fig.update_xaxes(title=xtitle, type="log" if log_x else None)
    fig.update_yaxes(title="RMSE [W] (IC95 bootstrap por dias)")
    return base(fig, 360)


def ci_chart(ci: pd.DataFrame, metric: str, title: str):
    d = ci[ci.metrica == metric].set_index("modelo").reindex(MODEL_IDS)
    fig = go.Figure()
    for m in MODEL_IDS:
        r = d.loc[m]
        fig.add_scatter(x=[r.estimativa], y=[m], mode="markers", marker=dict(size=12, color=COLORS[m]), showlegend=False,
                        error_x=dict(type="data", symmetric=False, array=[r.ic95_hi - r.estimativa],
                                     arrayminus=[r.estimativa - r.ic95_lo], color=MUTED, thickness=1.5))
    if metric != "RMSE_W" and metric != "MAE_W":
        fig.add_vline(x=0, line_color=MUTED, line_width=1)
    fig.update_yaxes(autorange="reversed")
    return base(fig, 230, title)


def field_preview(d: pd.DataFrame, max_gap_min=7.5):
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.42, 0.33, 0.25])
    t = d["timestamp"]
    for col, name, color, row in (("p_mpp_measured_W", "Pm [W]", OBS, 1), ("g_poa_Wm2", "Gpoa [W/m²]", SUN, 1)):
        x, y = _gapped(t, d[col].to_numpy(float), max_gap_min)
        fig.add_scatter(x=x, y=y, name=name, line=dict(color=color, width=1.6), row=row, col=1,
                        yaxis="y2" if col == "g_poa_Wm2" else None)
    for col, name, color in (("t_module_C", "Tbom [°C]", "#B4507A"), ("t_amb_C", "Tamb [°C]", "#3B82C4")):
        x, y = _gapped(t, d[col].to_numpy(float), max_gap_min)
        fig.add_scatter(x=x, y=y, name=name, line=dict(color=color, width=1.4), row=2, col=1)
    x, y = _gapped(t, d["wind_ms"].to_numpy(float), max_gap_min)
    fig.add_scatter(x=x, y=y, name="vento [m/s]", line=dict(color=MUTED, width=1.2), row=3, col=1)
    excl = d[~d["eligible"]]
    fig.add_scatter(x=excl["timestamp"], y=excl["p_mpp_measured_W"].fillna(0), mode="markers", name="excluída",
                    marker=dict(symbol="x", size=6, color="#9B2C2C"), row=1, col=1)
    fig.update_yaxes(title="W · W/m²", row=1, col=1)
    fig.update_yaxes(title="°C", row=2, col=1)
    fig.update_yaxes(title="m/s", row=3, col=1)
    return base(fig, 520)


def iv_chart(V, I, P, mpp, title):
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_scatter(x=V, y=I, name="I–V", line=dict(color=COLORS["M4"], width=2.2), secondary_y=False)
    fig.add_scatter(x=V, y=P, name="P–V", line=dict(color=INK, width=1.6, dash="dash"), secondary_y=True)
    fig.add_scatter(x=[mpp["Vmp"]], y=[mpp["Pmp"]], mode="markers+text", text=[f"MPP {mpp['Pmp']:.1f} W"],
                    textposition="top center", marker=dict(size=10, color=INK), name="MPP", secondary_y=True)
    fig.update_xaxes(title="Tensão [V]")
    fig.update_yaxes(title="Corrente [A]", secondary_y=False)
    fig.update_yaxes(title="Potência [W]", secondary_y=True, showgrid=False)
    return base(fig, 380, title)


def heat_matrix(mat: pd.DataFrame, unit: str, title: str):
    fig = go.Figure(go.Heatmap(z=mat.values, x=[f"{c:g} °C" for c in mat.columns], y=[f"{i:g}" for i in mat.index],
                               colorscale=[[0, "#EAF1F7"], [1, "#1F5F8B"]], showscale=False,
                               text=[[("" if np.isnan(v) else f"{v:.2f}") for v in row] for row in mat.values],
                               texttemplate="%{text}", hovertemplate="G=%{y} W/m², T=%{x}: %{z:.4f} " + unit + "<extra></extra>"))
    fig.update_yaxes(title="G [W/m²]")
    return base(fig, 300, title)
