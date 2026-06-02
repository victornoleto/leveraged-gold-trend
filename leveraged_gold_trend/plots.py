"""Generate the README/LinkedIn charts (matplotlib, headless).

Two families of chart:
  * single-timeframe: the headline equity vs buy&hold (``equity_vs_gold``);
  * cross-timeframe comparisons driven by ``results/timeframe_scan.csv`` — the equity overlay,
    risk/return scatter, anti-overfit gate heatmap, trade-count ("two ways to die") and max-drawdown
    charts. These read the precomputed scan so they stay fast (no strategy re-run), except the
    equity overlay which rebuilds each timeframe's curve.

Convention: buy&hold gold is always BLACK, strategy equity is BLUE, and 4h — the only timeframe
clearing all five gates — is highlighted in AMBER across every comparison.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from . import validate  # noqa: E402

PLOTS = Path(__file__).resolve().parent.parent / "results" / "plots"
HEADLINE_RISK = 0.05
ORDER = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"]
SWEET_SPOT = "4h"

# Shared palette.
BENCHMARK_COLOR = "black"      # buy & hold gold
EQUITY_COLOR = "#2563eb"       # strategy equity (blue)
ACCENT = "#f59e0b"             # the 4h sweet spot (amber)
MUTED = "#94a3b8"              # de-emphasised series/bars

# Per-gate columns persisted by timeframe_scan, with short display labels.
GATE_COLS = ["gate_wf", "gate_dd", "gate_dsr", "gate_cost3", "gate_mcpt"]
GATE_LABELS = ["WF > B&H", "OOS DD ≤ B&H", "Deflated SR", "Cost 3×", "MCPT p<0.05"]


def _gates_int(s: object) -> int:
    """'5/5' -> 5."""
    return int(str(s).split("/")[0])


def _truthy(v: object) -> bool:
    """Robust pass/fail read (handles bool, numpy bool, and 'True'/'False' strings from CSV)."""
    if isinstance(v, str):
        return v.strip().lower() == "true"
    return bool(v)


def _save(fig: plt.Figure, name: str) -> Path:
    PLOTS.mkdir(parents=True, exist_ok=True)
    out = PLOTS / name
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


def equity_vs_gold(interval: str = "4h") -> Path:
    """Strategy equity vs buy&hold gold (log scale)."""
    eq = validate.equity_for(interval, {"risk_pct_per_trade": HEADLINE_RISK})
    bh = validate.benchmark(interval)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(eq.index, eq.values, lw=1.5, color=EQUITY_COLOR,
            label=f"Leveraged Gold Trend ({interval}, risk 5%)")
    ax.plot(bh.index, bh.values, lw=1.3, color=BENCHMARK_COLOR, label="Buy & hold gold")
    ax.set_yscale("log")
    ax.set_title("Leveraged Gold Trend vs buy & hold gold (XAUUSD, log scale)")
    ax.set_ylabel("Equity (log, $10k start)")
    ax.legend(loc="upper left", frameon=False)
    ax.grid(True, which="both", alpha=0.2)
    fig.tight_layout()
    return _save(fig, "equity_4h_vs_gold.png")


def equity_all_timeframes() -> Path:
    """Every timeframe's strategy equity (risk 5%) vs buy&hold gold, daily-resampled, log scale.

    Curves are coloured fast→slow (hot red → cold blue); 4h is emphasised. Cost-bled fast
    timeframes sit low and flat; the slow ones barely lever up. Buy&hold gold is the black line."""
    fig, ax = plt.subplots(figsize=(11, 6))
    cmap = plt.get_cmap("coolwarm")
    n = len(ORDER)
    for i, tf in enumerate(ORDER):
        eq = validate.equity_for(tf, {"risk_pct_per_trade": HEADLINE_RISK})
        eqd = eq.resample("1D").last().dropna()
        sweet = tf == SWEET_SPOT
        ax.plot(eqd.index, eqd.values,
                lw=2.8 if sweet else 1.1,
                color=ACCENT if sweet else cmap(1.0 - i / (n - 1)),
                alpha=1.0 if sweet else 0.8,
                zorder=6 if sweet else 2,
                label=f"{tf} (sweet spot)" if sweet else tf)

    bh = validate.benchmark("1d").resample("1D").last().dropna()
    ax.plot(bh.index, bh.values, lw=2.4, color=BENCHMARK_COLOR, zorder=5, label="Buy & hold gold")

    ax.set_yscale("log")
    ax.set_title("Same strategy, every timeframe — equity vs buy & hold gold (XAUUSD, log scale)")
    ax.set_ylabel("Equity (log, $10k start)")
    ax.legend(loc="upper left", ncol=2, fontsize=8, frameon=False)
    ax.grid(True, which="both", alpha=0.2)
    fig.tight_layout()
    return _save(fig, "equity_all_timeframes_vs_gold.png")


def cost_decay(table: pd.DataFrame) -> Path:
    """The money chart: Sharpe after 3× costs vs timeframe, with cost-drag bars. Shows fast
    timeframes destroyed by cost (drag explodes, Sharpe collapses) and slow ones fading on too few
    trades — 4h is the sweet spot."""
    t = table.set_index("tf").reindex(ORDER)
    x = range(len(ORDER))
    bh = float(t["bh_oos_sharpe"].dropna().median())

    fig, ax1 = plt.subplots(figsize=(10, 5.5))
    ax1.bar(x, t["cost_drag_pct"].values, color="#fca5a5", alpha=0.7, label="Cost drag (CAGR pts lost to costs)")
    ax1.set_ylabel("Cost drag (CAGR percentage points)", color="#b91c1c")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(ORDER)
    ax1.set_xlabel("Timeframe (fast → slow)")

    ax2 = ax1.twinx()
    ax2.plot(x, t["full_sharpe"].values, "-o", color="#1d4ed8", lw=1.6, label="Sharpe (nominal cost)")
    ax2.plot(x, t["cost3_sharpe"].values, "--o", color="#0f766e", lw=1.6, label="Sharpe (3× cost)")
    ax2.axhline(bh, color="#64748b", ls=":", lw=1.2, label=f"Buy & hold gold Sharpe ≈ {bh:.2f}")
    ax2.set_ylabel("Sharpe ratio")

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper center", frameon=False, fontsize=9, ncol=2)
    ax1.set_title("How costs kill fast timeframes — same strategy, XAUUSD")
    fig.tight_layout()
    return _save(fig, "cost_decay_by_timeframe.png")


def risk_return_by_timeframe(table: pd.DataFrame) -> Path:
    """Risk vs return scatter: CAGR × Sharpe per timeframe, bubble size = #trades, colour = number
    of anti-overfit gates passed. 4h sits alone in the top-right with all five gates green."""
    t = table.set_index("tf").reindex(ORDER)
    gates = t["gates"].map(_gates_int)
    sizes = np.sqrt(t["n_trades"].clip(lower=1).to_numpy()) * 13.0

    fig, ax = plt.subplots(figsize=(10, 6))
    sc = ax.scatter(t["full_cagr_pct"], t["full_sharpe"], s=sizes, c=gates,
                    cmap="RdYlGn", vmin=0, vmax=5, edgecolor="black", lw=0.7, zorder=3)
    for tf in ORDER:
        ax.annotate(tf, (t.loc[tf, "full_cagr_pct"], t.loc[tf, "full_sharpe"]),
                    xytext=(7, 6), textcoords="offset points", fontsize=9,
                    fontweight="bold" if tf == SWEET_SPOT else "normal")

    bh = float(t["bh_oos_sharpe"].dropna().median())
    ax.axhline(bh, color=BENCHMARK_COLOR, ls=":", lw=1.2, label=f"Buy & hold gold Sharpe ≈ {bh:.2f}")

    cbar = fig.colorbar(sc, ax=ax, ticks=range(6), pad=0.02)
    cbar.set_label("Anti-overfit gates passed (of 5)")
    ax.set_xlabel("CAGR (%, full sample)")
    ax.set_ylabel("Sharpe (full sample)")
    ax.set_title("Risk vs return by timeframe — bubble = #trades, colour = gates passed")
    ax.legend(loc="lower right", frameon=False)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    return _save(fig, "risk_return_by_timeframe.png")


def gates_heatmap(table: pd.DataFrame) -> Path:
    """9 timeframes × 5 anti-overfit gates: green = pass, red = fail, grey = not tested (MCPT is
    skipped on the ultra-fast bars). Only 4h is all-green."""
    t = table.set_index("tf").reindex(ORDER)
    mcpt_j = GATE_COLS.index("gate_mcpt")

    M = np.zeros((len(ORDER), len(GATE_COLS)))
    for i, tf in enumerate(ORDER):
        for j, col in enumerate(GATE_COLS):
            M[i, j] = 1.0 if _truthy(t.loc[tf, col]) else 0.0
        if pd.isna(t.loc[tf, "mcpt_p"]):  # MCPT skipped -> mark as "not tested"
            M[i, mcpt_j] = np.nan

    cmap = matplotlib.colors.ListedColormap(["#ef4444", "#22c55e"])  # 0=fail (red), 1=pass (green)
    cmap.set_bad("#cbd5e1")  # not tested (grey)

    fig, ax = plt.subplots(figsize=(8.5, 6))
    ax.imshow(np.ma.masked_invalid(M), cmap=cmap, vmin=0, vmax=1, aspect="auto")

    for i, tf in enumerate(ORDER):
        for j in range(len(GATE_COLS)):
            v = M[i, j]
            txt = "n/a" if np.isnan(v) else ("✓" if v == 1.0 else "✗")
            ax.text(j, i, txt, ha="center", va="center", color="white",
                    fontsize=13, fontweight="bold")

    ax.set_xticks(range(len(GATE_LABELS)))
    ax.set_xticklabels(GATE_LABELS, rotation=20, ha="right")
    ax.set_yticks(range(len(ORDER)))
    ax.set_yticklabels(ORDER)
    for lbl in ax.get_yticklabels():
        if lbl.get_text() == SWEET_SPOT:
            lbl.set_fontweight("bold")
            lbl.set_color(ACCENT)
    ax.set_ylabel("Timeframe (fast → slow)")
    ax.set_title("Anti-overfit gates by timeframe — only 4h clears all five")
    fig.tight_layout()
    return _save(fig, "gates_heatmap.png")


def trades_by_timeframe(table: pd.DataFrame) -> Path:
    """Two ways to die: trade count by timeframe (log scale). Fast timeframes generate hundreds-to-
    thousands of trades from trailing-stop whipsaw (cost bleed); slow ones produce too few to be
    statistically meaningful. 4h lands in the middle."""
    t = table.set_index("tf").reindex(ORDER)
    x = np.arange(len(ORDER))
    colors = [ACCENT if tf == SWEET_SPOT else MUTED for tf in ORDER]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(x, t["n_trades"].to_numpy(), color=colors)
    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels(ORDER)
    ax.set_xlabel("Timeframe (fast → slow)")
    ax.set_ylabel("Number of trades (log)")

    for xi, tf in zip(x, ORDER):
        ax.annotate(f"{int(t.loc[tf, 'n_trades'])}", (xi, t.loc[tf, "n_trades"]),
                    ha="center", va="bottom", fontsize=8)

    arrow = dict(arrowstyle="->", lw=1.2)
    ax.annotate("whipsaw → cost bleed\n(too many trades)",
                xy=(0, t.loc["1m", "n_trades"]), xytext=(1.4, 1300),
                fontsize=9, color="#b91c1c", ha="left",
                arrowprops={**arrow, "color": "#b91c1c"})
    ax.annotate("too few trades\n→ no statistical power",
                xy=(len(ORDER) - 1, t.loc["1mo", "n_trades"]), xytext=(5.5, 170),
                fontsize=9, color="#1d4ed8", ha="left",
                arrowprops={**arrow, "color": "#1d4ed8"})

    ax.set_title("Two ways to die: trade count by timeframe (same strategy, XAUUSD)")
    fig.tight_layout()
    return _save(fig, "trades_by_timeframe.png")


def maxdd_by_timeframe(table: pd.DataFrame) -> Path:
    """Max drawdown by timeframe: full sample vs walk-forward out-of-sample. Drawdowns plot
    downward; 4h's bars are outlined in amber."""
    t = table.set_index("tf").reindex(ORDER)
    x = np.arange(len(ORDER))
    w = 0.38
    edges = [ACCENT if tf == SWEET_SPOT else "none" for tf in ORDER]
    lws = [2.2 if tf == SWEET_SPOT else 0.0 for tf in ORDER]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.bar(x - w / 2, t["full_maxdd_pct"].to_numpy(), width=w, color=MUTED,
           edgecolor=edges, linewidth=lws, label="Full sample")
    ax.bar(x + w / 2, t["wf_oos_maxdd_pct"].to_numpy(), width=w, color=EQUITY_COLOR,
           edgecolor=edges, linewidth=lws, label="Walk-forward OOS")
    ax.axhline(0, color="black", lw=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(ORDER)
    ax.set_xlabel("Timeframe (fast → slow)")
    ax.set_ylabel("Max drawdown (%)")
    ax.set_title("Max drawdown by timeframe — full sample vs walk-forward OOS")
    ax.legend(frameon=False)
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    return _save(fig, "maxdd_by_timeframe.png")
