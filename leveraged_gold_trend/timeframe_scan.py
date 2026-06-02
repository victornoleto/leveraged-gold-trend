"""Run the SAME strategy (Approach A) across all 9 timeframes and tabulate the result.

This is the study at the heart of the repo: with lookbacks fixed in *days* (so it is genuinely the
same strategy), how does behaviour change from 1m to 1mo — and where do trading costs make the edge
collapse? For each timeframe we report the full-sample metrics, the leverage actually used, the cost
drag, the Sharpe after 3× costs, the walk-forward out-of-sample Sharpe vs buy&hold, and (where the
bar count makes it affordable) the permutation p-value.

    python -m leveraged_gold_trend --scan
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import data, metrics, validate
from .strategy import DEFAULT_PARAMS, target_exposure, trade_stats

RESULTS = Path(__file__).resolve().parent.parent / "results"
HEADLINE_RISK = 0.05

# Permutation count per timeframe — 0 (skip) for the ultra-fast bars where MCPT would take many
# minutes; the cost_drag / cost@3× / walk-forward columns already tell their story.
MCPT_N = {"1m": 0, "5m": 0, "15m": 0, "30m": 60, "1h": 100, "4h": 150, "1d": 200, "1w": 200, "1mo": 200}

COLUMNS = ["tf", "bars", "n_trades", "full_cagr_pct", "full_sharpe", "full_maxdd_pct", "avg_lev",
           "cost_drag_pct", "cost3_sharpe", "wf_oos_sharpe", "bh_oos_sharpe", "wf_oos_maxdd_pct",
           "dsr", "mcpt_p", "gates"]


def scan(intervals=data.INTERVALS, save: bool = True, verbose: bool = True) -> pd.DataFrame:
    rows = []
    for tf in intervals:
        if verbose:
            print(f"  scanning {tf} ...", flush=True)
        p = validate.ppy(tf)
        df = data.load(tf)
        bpd = data.BARS_PER_DAY[tf]

        full = validate.equity_for(tf, {"risk_pct_per_trade": HEADLINE_RISK})
        full0 = validate.equity_for(tf, {"risk_pct_per_trade": HEADLINE_RISK}, cost_mult=0.0)
        m = metrics.from_equity(full, p)
        expo = target_exposure(df, {**DEFAULT_PARAMS, "risk_pct_per_trade": HEADLINE_RISK}, bpd)
        ts = trade_stats(expo)
        g = validate.gates(tf, mcpt_n=MCPT_N[tf])
        wf = g["walk_forward"]

        rows.append({
            "tf": tf,
            "bars": len(df),
            "n_trades": ts["n_trades"],
            "full_cagr_pct": round(m.get("cagr", float("nan")) * 100, 2),
            "full_sharpe": round(m.get("sharpe", float("nan")), 2),
            "full_maxdd_pct": round(m.get("max_drawdown", float("nan")) * 100, 1),
            "avg_lev": round(ts["avg_leverage"], 2),
            "cost_drag_pct": round((metrics.from_equity(full0, p).get("cagr", 0.0) - m.get("cagr", 0.0)) * 100, 2),
            "cost3_sharpe": round(g["cost3_sharpe"], 2),
            "wf_oos_sharpe": round(wf["oos_sharpe"], 2),
            "bh_oos_sharpe": round(wf["bh_oos_sharpe"], 2),
            "wf_oos_maxdd_pct": round(wf["oos_maxdd"] * 100, 1),
            "dsr": round(g["dsr"], 3),
            "mcpt_p": round(g["mcpt"]["p_value"], 3),
            "gates": f"{g['n_pass']}/5",
        })

    table = pd.DataFrame(rows)[COLUMNS]
    if save:
        RESULTS.mkdir(parents=True, exist_ok=True)
        table.to_csv(RESULTS / "timeframe_scan.csv", index=False)
    if verbose:
        print("\n=== TIMEFRAME SCAN — Approach A (risk 5%, cap 3×), XAUUSD, fx costs ===")
        print("full-sample vs walk-forward OOS; 24h-gold (empirical) annualization\n")
        print(table.to_string(index=False))
        passed = [r["tf"] for r in rows if r["gates"] == "5/5"]
        print(f"\ntimeframes clearing all 5 gates: {passed or 'none'}")
        if save:
            print(f"-> {RESULTS / 'timeframe_scan.csv'}")
    return table


if __name__ == "__main__":
    scan()
