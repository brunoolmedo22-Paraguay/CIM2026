"""Figuras estáticas (SVG + PNG) geradas EXCLUSIVAMENTE a partir dos arquivos da execução.

Matplotlib (backend Agg): sem navegador, sem rede. Cada figura pode ser
refeita com ``make_all_figures(run_dir)`` após reabrir/importar um ZIP.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ..pvcore.models import MODEL_IDS, MODEL_INFO  # noqa: E402

COLORS = {m: MODEL_INFO[m].color for m in MODEL_IDS}
OBS_COLOR = "#1C2B39"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.color": "#E3E8EE",
                     "grid.linewidth": 0.6, "axes.edgecolor": "#5A6B7B", "figure.dpi": 110,
                     "savefig.bbox": "tight", "legend.frameon": False})


def _save(fig, folder: Path, name: str) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for ext in ("svg", "png"):
        p = folder / f"{name}.{ext}"
        fig.savefig(p, dpi=200 if ext == "png" else None)
        paths.append(str(p))
    plt.close(fig)
    return paths


def representative_day(pred: pd.DataFrame) -> str:
    t = pd.to_datetime(pred["timestamp"])
    return str(t.dt.date.value_counts().idxmax())


def fig_day_power(pred, day, folder):
    t = pd.to_datetime(pred["timestamp"])
    d = pred[t.dt.date.astype(str) == day].copy()
    d["t"] = pd.to_datetime(d["timestamp"])
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    ax.plot(d["t"], d["P_obs_W"], color=OBS_COLOR, lw=1.8, label="Medida (Pm)")
    for m in MODEL_IDS:
        ax.plot(d["t"], d[f"P_{m}_W"], color=COLORS[m], lw=1.0, label=f"{m} {MODEL_INFO[m].short}")
    ax.set_ylabel("Potência DC por módulo [W]")
    ax.set_title(f"Dia com mais amostras válidas: {day} (lacunas não interpoladas)", fontsize=9, loc="left")
    ax.legend(ncol=5, fontsize=7, loc="upper left")
    fig.autofmt_xdate()
    return _save(fig, folder, "energia_potencia_dia")


def fig_scatter(pred, folder):
    fig, axes = plt.subplots(1, 4, figsize=(10, 2.9), sharex=True, sharey=True)
    o = pred["P_obs_W"].to_numpy()
    lim = float(np.nanmax(o)) * 1.05
    for ax, m in zip(axes, MODEL_IDS):
        ax.scatter(o, pred[f"P_{m}_W"], s=1.5, alpha=0.25, color=COLORS[m], rasterized=True)
        ax.plot([0, lim], [0, lim], color="#8795A1", lw=0.8)
        ax.set_title(f"{m} · {MODEL_INFO[m].short}", fontsize=8, loc="left")
        ax.set_xlabel("Medida [W]")
    axes[0].set_ylabel("Prevista [W]")
    return _save(fig, folder, "energia_dispersao")


def fig_residual_bins(bins, folder):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3))
    for ax, var in zip(axes, ["Gpoa [W/m²]", "Tmod [°C]"]):
        d = bins[bins.variavel == var]
        faixas = list(dict.fromkeys(d.faixa))
        x = np.arange(len(faixas))
        for k, m in enumerate(MODEL_IDS):
            dm = d[d.modelo == m].set_index("faixa").reindex(faixas)
            ax.bar(x + (k - 1.5) * 0.2, dm["MBE_W"], width=0.2, color=COLORS[m], label=m)
        ax.axhline(0, color="#5A6B7B", lw=0.7)
        ax.set_xticks(x, faixas, rotation=30, fontsize=7)
        ax.set_title(f"MBE por faixa de {var}", fontsize=9, loc="left")
        ax.set_ylabel("MBE [W] (>0 sobrestima)")
    axes[0].legend(fontsize=7, ncol=4)
    return _save(fig, folder, "energia_residuos_faixas")


def fig_daily_rmse(daily, folder):
    fig, ax = plt.subplots(figsize=(7.2, 3))
    data = [daily[daily.modelo == m]["RMSE_W"].dropna().to_numpy() for m in MODEL_IDS]
    bp = ax.boxplot(data, patch_artist=True, widths=0.5)
    ax.set_xticks(range(1, 5), [f"{m}\n{MODEL_INFO[m].short}" for m in MODEL_IDS])
    for patch, m in zip(bp["boxes"], MODEL_IDS):
        patch.set_facecolor(COLORS[m]); patch.set_alpha(0.55)
    ax.set_ylabel("RMSE diário [W]")
    ax.set_title("Distribuição do RMSE por dia (unidade de bloco do bootstrap)", fontsize=9, loc="left")
    return _save(fig, folder, "estatistica_rmse_diario")


def fig_bootstrap(ci, folder):
    fig, axes = plt.subplots(1, 3, figsize=(10, 2.8))
    for ax, k in zip(axes, ["RMSE_W", "MBE_W", "erro_energia_pct"]):
        d = ci[ci.metrica == k].set_index("modelo").reindex(MODEL_IDS)
        y = np.arange(4)
        ax.errorbar(d["estimativa"], y, xerr=[d["estimativa"] - d["ic95_lo"], d["ic95_hi"] - d["estimativa"]],
                    fmt="o", color="#1C2B39", ecolor="#8795A1", capsize=3)
        for i, m in enumerate(MODEL_IDS):
            ax.plot(d.loc[m, "estimativa"], i, "o", color=COLORS[m])
        ax.set_yticks(y, MODEL_IDS)
        ax.set_title({"RMSE_W": "RMSE [W]", "MBE_W": "MBE [W]", "erro_energia_pct": "Erro de energia [%]"}[k]
                     + " · IC95 bootstrap por dias", fontsize=8, loc="left")
        if k != "RMSE_W":
            ax.axvline(0, color="#8795A1", lw=0.7)
    return _save(fig, folder, "estatistica_bootstrap_ic95")


def fig_timing(runs, folder):
    main = runs[runs.experimento == "principal"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.2))
    data = [main[main.modelo == m]["tempo_por_amostra_us"].to_numpy() for m in MODEL_IDS]
    bp = axes[0].boxplot(data, patch_artist=True, widths=0.5)
    for patch, m in zip(bp["boxes"], MODEL_IDS):
        patch.set_facecolor(COLORS[m]); patch.set_alpha(0.55)
    axes[0].set_yscale("log")
    axes[0].set_xticks(range(1, 5), MODEL_IDS)
    axes[0].set_ylabel("Tempo por amostra [µs] (log)")
    axes[0].set_title(f"Benchmark sequencial · {main.rodada.max()} rodadas", fontsize=9, loc="left")
    for m in MODEL_IDS:
        d = main[main.modelo == m].sort_values("rodada")
        axes[1].plot(d["rodada"], d["compute_s"] / d["compute_s"].median(), "o-", ms=3, color=COLORS[m], label=m)
    axes[1].set_xlabel("Rodada")
    axes[1].set_ylabel("compute_s / mediana do modelo")
    axes[1].set_title("Estabilidade entre rodadas", fontsize=9, loc="left")
    axes[1].legend(fontsize=7, ncol=4)
    return _save(fig, folder, "computacional_tempos")


def fig_memory(runs, folder):
    main = runs[runs.experimento == "principal"]
    fig, ax = plt.subplots(figsize=(6, 3))
    data = [main[main.modelo == m]["pico_rss_delta_MiB"].to_numpy() for m in MODEL_IDS]
    bp = ax.boxplot(data, patch_artist=True, widths=0.5)
    for patch, m in zip(bp["boxes"], MODEL_IDS):
        patch.set_facecolor(COLORS[m]); patch.set_alpha(0.55)
    ax.set_xticks(range(1, 5), MODEL_IDS)
    ax.set_ylabel("Pico RSS − RSS antes [MiB]")
    ax.set_title(f"Memória ({main['metodo_memoria'].iloc[0]})", fontsize=9, loc="left")
    return _save(fig, folder, "computacional_memoria")


def fig_scaling(summary, folder):
    fig, ax = plt.subplots(figsize=(6, 3.2))
    for m in MODEL_IDS:
        d = summary[summary.modelo == m].sort_values("batch_size")
        ax.errorbar(d["batch_size"], d["mediana_s"], yerr=[d["mediana_s"] - d["p5_s"], d["p95_s"] - d["mediana_s"]],
                    fmt="o-", ms=3, color=COLORS[m], label=m, capsize=2)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("Tamanho do lote [amostras]")
    ax.set_ylabel("compute_s (mediana; barras p5–p95)")
    ax.set_title("Escalabilidade com o tamanho do lote", fontsize=9, loc="left")
    ax.legend(fontsize=7)
    return _save(fig, folder, "computacional_escalabilidade")


def fig_pareto(pareto, folder):
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.4))
    for ax, eixo, xcol, xl in ((axes[0], "tempo", "tempo_us_amostra", "Tempo por amostra [µs] (log)"),
                               (axes[1], "memoria", "memoria_MiB", "Pico ΔRSS [MiB]")):
        d = pareto[pareto.eixo == eixo]
        for r in d.itertuples():
            ax.scatter(getattr(r, xcol), r.RMSE_W, s=70 if r.nao_dominado else 35, color=COLORS[r.modelo],
                       edgecolor="#1C2B39" if r.nao_dominado else "none", linewidth=1.2, zorder=3)
            ax.annotate(r.modelo, (getattr(r, xcol), r.RMSE_W), xytext=(5, 4), textcoords="offset points", fontsize=8)
            if eixo == "tempo":
                ax.errorbar(r.tempo_us_amostra, r.RMSE_W, yerr=[[r.RMSE_W - r.RMSE_lo], [r.RMSE_hi - r.RMSE_W]],
                            color="#8795A1", lw=0.8, capsize=2, zorder=2)
        f = d[d.nao_dominado].sort_values(xcol)
        ax.plot(f[xcol], f["RMSE_W"], "--", color="#1C2B39", lw=0.8)
        if eixo == "tempo":
            ax.set_xscale("log")
        ax.set_xlabel(xl)
        ax.set_ylabel("RMSE [W]")
        ax.set_title(f"Erro × {'memória' if eixo == 'memoria' else eixo}: contorno = não dominado", fontsize=9, loc="left")
    return _save(fig, folder, "integrada_pareto")


def fig_sensitivity(sens, folder):
    d = sens[sens.tipo == "delta_T_C"]
    if d.empty:
        return []
    fig, ax = plt.subplots(figsize=(6, 3))
    for m in MODEL_IDS:
        dm = d[d.modelo == m].sort_values("valor")
        ax.plot(dm["valor"], dm["RMSE_W"], "o-", color=COLORS[m], label=m, ms=4)
    ax.set_xlabel("ΔT célula–módulo a 1000 W/m² [°C] (hipótese)")
    ax.set_ylabel("RMSE [W]")
    ax.set_title("Sensibilidade térmica (afeta M2 e M4)", fontsize=9, loc="left")
    ax.legend(fontsize=7, ncol=4)
    return _save(fig, folder, "integrada_sensibilidade_deltaT")


def make_all_figures(run_dir: Path) -> list[str]:
    run_dir = Path(run_dir)
    folder = run_dir / "figures"
    pred = pd.read_csv(run_dir / "predictions.csv", float_precision="round_trip")
    made = []
    made += fig_day_power(pred, representative_day(pred), folder)
    made += fig_scatter(pred, folder)
    for name, fn in (("residual_bins", fig_residual_bins), ("metrics_daily", fig_daily_rmse),
                     ("bootstrap_ci", fig_bootstrap), ("sensitivity", fig_sensitivity)):
        p = run_dir / f"{name}.csv"
        if p.exists():
            made += fn(pd.read_csv(p), folder)
    if (run_dir / "benchmark_runs.csv").exists():
        runs = pd.read_csv(run_dir / "benchmark_runs.csv", float_precision="round_trip")
        made += fig_timing(runs, folder)
        made += fig_memory(runs, folder)
        made += fig_scaling(pd.read_csv(run_dir / "benchmark_summary.csv", float_precision="round_trip"), folder)
        made += fig_pareto(pd.read_csv(run_dir / "pareto.csv", float_precision="round_trip"), folder)
    (folder / "index.json").write_text(json.dumps(made, indent=1), encoding="utf-8")
    return made


# ---------------------------------------------------------------------------
# Figuras exportáveis do modo Modelos (bytes SVG, PNG)
# ---------------------------------------------------------------------------
def _to_bytes(fig) -> tuple[bytes, bytes]:
    import io
    out = []
    for ext in ("svg", "png"):
        buf = io.BytesIO()
        fig.savefig(buf, format=ext, dpi=200 if ext == "png" else None)
        out.append(buf.getvalue())
    plt.close(fig)
    return out[0], out[1]


def modelos_power_figure(table: pd.DataFrame, models: list, title: str) -> tuple[bytes, bytes]:
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    t = pd.to_datetime(table["timestamp"])
    for m in models:
        ax.plot(t, table[f"P_{m}_arranjo_W"], color=COLORS[m], lw=1.3, label=f"{m} {MODEL_INFO[m].short}")
    ax.set_ylabel("Potência DC do arranjo [W]")
    ax.set_title(title, fontsize=9, loc="left")
    ax.legend(fontsize=7, ncol=4)
    fig.autofmt_xdate()
    return _to_bytes(fig)


def modelos_iv_figure(V, I, P, mpp: dict, title: str) -> tuple[bytes, bytes]:
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ax.plot(V, I, color=COLORS["M4"], lw=2, label="I–V")
    ax.set_xlabel("Tensão [V]"); ax.set_ylabel("Corrente [A]")
    ax2 = ax.twinx()
    ax2.plot(V, P, color=OBS_COLOR, lw=1.3, ls="--", label="P–V")
    ax2.plot([mpp["Vmp"]], [mpp["Pmp"]], "o", color=OBS_COLOR)
    ax2.set_ylabel("Potência [W]"); ax2.grid(False)
    ax.set_title(f"SDM · {title} · MPP {mpp['Pmp']:.1f} W", fontsize=9, loc="left")
    return _to_bytes(fig)
