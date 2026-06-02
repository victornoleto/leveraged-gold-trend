"""Generate the two README/LinkedIn charts (matplotlib, headless)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from . import validate  # noqa: E402

PLOTS = Path(__file__).resolve().parent.parent / "results" / "plots"
HEADLINE_RISK = 0.05
ORDER = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"]


def equity_vs_gold(interval: str = "4h") -> Path:
    """Strategy equity vs buy&hold gold (log scale)."""
    eq = validate.equity_for(interval, {"risk_pct_per_trade": HEADLINE_RISK})
    bh = validate.benchmark(interval)
    fig, ax = plt.subplots(figsize=(10, 5.5))
    ax.plot(eq.index, eq.values, lw=1.4, color="#c2410c", label=f"Leveraged Gold Trend ({interval}, risk 5%)")
    ax.plot(bh.index, bh.values, lw=1.2, color="#64748b", label="Buy & hold gold")
    ax.set_yscale("log")
    ax.set_title("Leveraged Gold Trend vs buy & hold gold (XAUUSD, log scale)")
    ax.set_ylabel("Equity (log, $10k start)")
    ax.legend(loc="upper left", frameon=False)
    ax.grid(True, which="both", alpha=0.2)
    fig.tight_layout()
    PLOTS.mkdir(parents=True, exist_ok=True)
    out = PLOTS / "equity_4h_vs_gold.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out


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
    PLOTS.mkdir(parents=True, exist_ok=True)
    out = PLOTS / "cost_decay_by_timeframe.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    return out
