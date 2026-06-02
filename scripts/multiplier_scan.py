"""Test lot-size multipliers on top of the promoted strategy exposure.

This keeps the strategy signals, stops, re-risking, overlay, and costs unchanged, then multiplies the
resulting signed exposure by a scalar. It is intentionally a stress test of extra leverage, not a new
governed-risk default.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from leveraged_gold_trend import costs, data, metrics  # noqa: E402
from leveraged_gold_trend.strategy import DEFAULT_PARAMS, target_exposure, trade_stats  # noqa: E402


INIT_CASH = 10_000.0
HEADLINE_RISK = 0.05
DEFAULT_MULTIPLIERS = (0.5, 1.0, 2.0, 3.0)
RESULTS = Path("results")
PLOTS = RESULTS / "plots"


def _equity_from_exposure(df: pd.DataFrame, exposure: pd.Series, cost_mult: float = 1.0) -> pd.Series:
    rets = df["Close"].pct_change().reindex(exposure.index).fillna(0.0)
    turnover = exposure.diff().abs().fillna(exposure.abs())
    port_ret = exposure.shift(1).fillna(0.0) * rets - costs.round_trip_cost(cost_mult) * turnover
    return INIT_CASH * (1.0 + port_ret).cumprod()


def _benchmark(df: pd.DataFrame) -> pd.Series:
    close = df["Close"].dropna()
    return INIT_CASH * close / close.iloc[0]


def run(interval: str = "4h", multipliers: tuple[float, ...] = DEFAULT_MULTIPLIERS) -> pd.DataFrame:
    df = data.load(interval)
    ppy = metrics.empirical_ppy(df.index)
    base_params = {**DEFAULT_PARAMS, "risk_pct_per_trade": HEADLINE_RISK}
    base_exposure = target_exposure(df, base_params, data.BARS_PER_DAY[interval])

    curves: dict[str, pd.Series] = {"Buy & hold gold": _benchmark(df)}
    rows = []
    for multiplier in multipliers:
        exposure = base_exposure * multiplier
        eq = _equity_from_exposure(df, exposure)
        eq0 = _equity_from_exposure(df, exposure, cost_mult=0.0)
        m = metrics.from_equity(eq, ppy)
        m0 = metrics.from_equity(eq0, ppy)
        ts = trade_stats(exposure)
        curves[f"{multiplier:g}x"] = eq
        rows.append({
            "multiplier": multiplier,
            "final_equity": float(eq.iloc[-1]),
            "total_return": m["total_return"],
            "cagr_pct": m["cagr"] * 100.0,
            "sharpe": m["sharpe"],
            "sortino": m["sortino"],
            "calmar": m["calmar"],
            "maxdd_pct": m["max_drawdown"] * 100.0,
            "cost_drag_pct": (m0["cagr"] - m["cagr"]) * 100.0,
            "entries": ts["n_trades"],
            "avg_leverage": ts["avg_leverage"],
            "max_leverage": ts["max_leverage"],
            "pct_time_in_market": ts["pct_time_in_market"],
        })

    table = pd.DataFrame(rows)
    RESULTS.mkdir(parents=True, exist_ok=True)
    PLOTS.mkdir(parents=True, exist_ok=True)
    csv_out = RESULTS / "multiplier_scan.csv"
    table.to_csv(csv_out, index=False)

    fig, ax = plt.subplots(figsize=(10, 5.8))
    colors = {
        "Buy & hold gold": "black",
        "0.5x": "#64748b",
        "1x": "#2563eb",
        "2x": "#f59e0b",
        "3x": "#dc2626",
    }
    for label, curve in curves.items():
        lw = 2.2 if label in ("Buy & hold gold", "1x") else 1.6
        alpha = 1.0 if label in ("Buy & hold gold", "1x") else 0.9
        ax.plot(curve.index, curve.values, label=label, color=colors.get(label), lw=lw, alpha=alpha)
    ax.set_yscale("log")
    ax.set_title(f"Lot-size multiplier stress test — promoted strategy, {interval} XAUUSD")
    ax.set_ylabel("Equity (log, $10k start)")
    ax.grid(True, which="both", alpha=0.2)
    ax.legend(loc="upper left", frameon=False, ncol=2)
    fig.tight_layout()
    plot_out = PLOTS / f"equity_{interval}_lot_multipliers.png"
    fig.savefig(plot_out, dpi=130)
    plt.close(fig)

    print(table[[
        "multiplier", "final_equity", "cagr_pct", "sharpe", "sortino", "maxdd_pct",
        "cost_drag_pct", "avg_leverage", "max_leverage",
    ]].to_string(index=False, float_format=lambda x: f"{x:.2f}"))
    print(f"wrote {csv_out}")
    print(f"wrote {plot_out}")
    return table


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest lot-size multipliers on the promoted strategy")
    parser.add_argument("--interval", default="4h", choices=data.INTERVALS)
    parser.add_argument("--multipliers", nargs="+", type=float, default=DEFAULT_MULTIPLIERS)
    args = parser.parse_args()
    run(args.interval, tuple(args.multipliers))


if __name__ == "__main__":
    main()
