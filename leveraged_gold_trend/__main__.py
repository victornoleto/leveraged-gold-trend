"""CLI for the Leveraged Gold Trend strategy.

    python -m leveraged_gold_trend --interval 4h         # headline metrics for one timeframe
    python -m leveraged_gold_trend --interval 4h --validate   # + the 5 anti-overfit gates
    python -m leveraged_gold_trend --scan                # the 9-timeframe study (writes results/)
    python -m leveraged_gold_trend --plots               # regenerate the README charts
"""

from __future__ import annotations

import argparse
import json

from . import data, metrics, validate
from .strategy import DEFAULT_PARAMS, target_exposure, trade_stats

HEADLINE_RISK = 0.05
HEADLINE_LABEL = "Donchian/ATR + 0.5x EMA300 volatility-scaled bull overlay"


def _headline(interval: str, run_gates: bool) -> None:
    p = validate.ppy(interval)
    eq = validate.equity_for(interval, {"risk_pct_per_trade": HEADLINE_RISK})
    bh = validate.benchmark(interval)
    m = metrics.from_equity(eq, p)
    expo = target_exposure(data.load(interval),
                           {**DEFAULT_PARAMS, "risk_pct_per_trade": HEADLINE_RISK}, data.BARS_PER_DAY[interval])
    ts = trade_stats(expo)

    print(f"\n=== Leveraged Gold Trend — XAUUSD {interval} (risk 5%, cap 3×) ===")
    print(f"  {HEADLINE_LABEL}")
    print(f"  CAGR {m['cagr'] * 100:.2f}%   Sharpe {m['sharpe']:.2f}   Sortino {m['sortino']:.2f}   "
          f"Calmar {m['calmar']:.2f}   MaxDD {m['max_drawdown'] * 100:.1f}%")
    print(f"  buy&hold gold: CAGR {metrics.from_equity(bh, p)['cagr'] * 100:.2f}%   "
          f"Sharpe {metrics.sharpe(bh, p):.2f}")
    print(f"  entries {ts['n_trades']}   avg leverage {ts['avg_leverage']:.2f}×   "
          f"max {ts['max_leverage']:.2f}×   time in market {ts['pct_time_in_market'] * 100:.0f}%")

    if run_gates:
        g = validate.gates(interval, mcpt_n=150)
        wf = g["walk_forward"]
        print(f"\n  walk-forward OOS Sharpe {wf['oos_sharpe']:.2f} (B&H {wf['bh_oos_sharpe']:.2f}), "
              f"MaxDD {wf['oos_maxdd'] * 100:.1f}%")
        print(f"  deflated Sharpe {g['dsr']:.3f}   cost@3× Sharpe {g['cost3_sharpe']:.2f}   "
              f"MCPT p={g['mcpt']['p_value']:.3f}")
        for k, v in g["checks"].items():
            print(f"    {'PASS' if v else 'FAIL'}  {k}")
        print(f"  -> {g['n_pass']}/5 gates")


def main() -> None:
    ap = argparse.ArgumentParser(prog="leveraged_gold_trend", description="Leveraged Gold Trend strategy")
    ap.add_argument("--interval", default="4h", choices=data.INTERVALS, help="timeframe (default 4h)")
    ap.add_argument("--validate", action="store_true", help="also run the 5 anti-overfit gates")
    ap.add_argument("--scan", action="store_true", help="run the 9-timeframe study (writes results/)")
    ap.add_argument("--plots", action="store_true", help="regenerate the README charts")
    args = ap.parse_args()

    if args.scan:
        from .timeframe_scan import scan
        scan()
    elif args.plots:
        from pathlib import Path

        import pandas as pd

        from . import plots
        from .timeframe_scan import RESULTS, scan
        csv = RESULTS / "timeframe_scan.csv"
        t = pd.read_csv(csv) if csv.exists() else scan(save=True, verbose=False)
        # the gate heatmap needs the per-gate columns; re-scan once if the CSV predates them
        if not set(plots.GATE_COLS).issubset(t.columns):
            print("scan CSV missing per-gate columns; re-running scan ...")
            t = scan(save=True, verbose=False)
        # headline metrics JSON (evidence for the README)
        p = validate.ppy("4h")
        m = metrics.from_equity(validate.equity_for("4h", {"risk_pct_per_trade": HEADLINE_RISK}), p)
        ts = trade_stats(target_exposure(data.load("4h"),
                         {**DEFAULT_PARAMS, "risk_pct_per_trade": HEADLINE_RISK}, data.BARS_PER_DAY["4h"]))
        RESULTS.mkdir(parents=True, exist_ok=True)
        (RESULTS / "headline_4h_metrics.json").write_text(
            json.dumps({**{k: round(v, 4) for k, v in m.items()}, **ts}, indent=2), encoding="utf-8")
        print("wrote", RESULTS / "headline_4h_metrics.json")
        print("wrote", plots.equity_vs_gold("4h"))
        print("wrote", plots.equity_all_timeframes())
        print("wrote", plots.cost_decay(t))
        print("wrote", plots.risk_return_by_timeframe(t))
        print("wrote", plots.gates_heatmap(t))
        print("wrote", plots.trades_by_timeframe(t))
        print("wrote", plots.maxdd_by_timeframe(t))
    else:
        _headline(args.interval, run_gates=args.validate)


if __name__ == "__main__":
    main()
