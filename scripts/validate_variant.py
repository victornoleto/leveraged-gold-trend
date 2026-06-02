"""Validate the promoted optimized candidate against its neighbouring research family.

The fixed candidate is intentionally explicit. Walk-forward validation uses a small neighbouring
family around that candidate so the result reflects a realistic re-optimization process rather than a
single hindsight-picked parameter set.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from leveraged_gold_trend import data, metrics, validate
from scripts.variant_scan import _benchmark, _equity_from_exposure, _mcpt_variant, _variant_exposure


INTERVAL = "4h"
INIT_CASH = 10_000.0
RESULTS = Path("results")

CANDIDATE_PARAMS = {
    "risk_pct_per_trade": 0.05,
    "rerisk": True,
    "rerisk_inertia": 0.10,
    "bull_overlay": 0.50,
    "bull_overlay_ma_days": 300,
    "bull_overlay_ma_type": "ema",
    "bull_overlay_vol_mult": True,
}

PERIODS = {
    "full": (None, None),
    "pre2013": ("2004-01-01", "2013-12-31"),
    "post2013": ("2014-01-01", None),
}


def candidate_family() -> list[tuple[str, dict]]:
    """Small robust region around the candidate, not an open-ended search."""
    out = []
    for overlay in (0.25, 0.50, 0.75, 1.00):
        for ma_days in (200, 300):
            for vol_mult in (False, True):
                for inertia in (0.10, 0.25):
                    suffix = "volmult" if vol_mult else "plain"
                    name = f"rerisk_i{int(inertia * 100)}_overlay_{overlay:g}x_ema{ma_days}_{suffix}"
                    out.append((name, {
                        "risk_pct_per_trade": 0.05,
                        "rerisk": True,
                        "rerisk_inertia": inertia,
                        "bull_overlay": overlay,
                        "bull_overlay_ma_days": ma_days,
                        "bull_overlay_ma_type": "ema",
                        "bull_overlay_vol_mult": vol_mult,
                    }))
    out.append(("candidate_fixed", CANDIDATE_PARAMS))
    return out


def _series_metrics(eq: pd.Series, bh: pd.Series, start: str | None, end: str | None) -> dict:
    e = eq.loc[start:end].dropna()
    b = bh.loc[start:end].dropna()
    ppy = metrics.empirical_ppy(e.index)
    em = metrics.from_equity(e, ppy)
    bm = metrics.from_equity(b, ppy)
    return {
        "strategy": em,
        "benchmark": bm,
        "strategy_final": float(e.iloc[-1]),
        "benchmark_final": float(b.iloc[-1]),
        "strategy_total": float(e.iloc[-1] / e.iloc[0] - 1.0),
        "benchmark_total": float(b.iloc[-1] / b.iloc[0] - 1.0),
        "excess_cagr": float(em["cagr"] - bm["cagr"]),
        "excess_total": float((e.iloc[-1] / e.iloc[0]) - (b.iloc[-1] / b.iloc[0])),
    }


def _walk_forward(eqs: dict[str, pd.Series], bh: pd.Series, ppy: float) -> dict:
    oos_rets, bh_rets, picks = [], [], []
    for tr_s, tr_e, te_s, te_e in validate.WINDOWS:
        bh_tr_dd = metrics.max_drawdown(bh.loc[tr_s:tr_e])
        scored = []
        for name, eq in eqs.items():
            tr = eq.loc[tr_s:tr_e]
            if len(tr) < validate.MIN_TRAIN_BARS:
                continue
            m = metrics.from_equity(tr, ppy)
            feasible = m.get("max_drawdown", 0.0) >= bh_tr_dd
            scored.append((name, m.get("sharpe", 0.0), feasible, m.get("max_drawdown", 0.0)))
        feasible = [s for s in scored if s[2]] or scored
        name = max(feasible, key=lambda s: (s[1], s[3]))[0]
        oos_rets.append(eqs[name].pct_change().loc[te_s:te_e])
        bh_rets.append(bh.pct_change().loc[te_s:te_e])
        picks.append({"train": [tr_s, tr_e], "test": [te_s, te_e], "pick": name})

    oos_returns = pd.concat(oos_rets).fillna(0.0)
    bh_returns = pd.concat(bh_rets).fillna(0.0)
    oos = INIT_CASH * (1.0 + oos_returns).cumprod()
    bh_oos = INIT_CASH * (1.0 + bh_returns).cumprod()
    trial_sr = [metrics.sharpe(eq, ppy) for eq in eqs.values()]
    oos_sharpe = metrics.sharpe(oos, ppy)
    dsr = validate.deflated_sharpe(oos_returns, trial_sr, oos_sharpe, ppy)
    return {
        "oos_cagr": metrics.from_equity(oos, ppy)["cagr"],
        "oos_sharpe": oos_sharpe,
        "oos_maxdd": metrics.max_drawdown(oos),
        "bh_oos_cagr": metrics.from_equity(bh_oos, ppy)["cagr"],
        "bh_oos_sharpe": metrics.sharpe(bh_oos, ppy),
        "bh_oos_maxdd": metrics.max_drawdown(bh_oos),
        "dsr": dsr,
        "trial_count": len(eqs),
        "picks": picks,
    }


def run(mcpt_n: int = 500) -> dict:
    df = data.load(INTERVAL)
    bh = _benchmark(df)
    ppy = metrics.empirical_ppy(df.index)

    candidate_exposure = _variant_exposure(df, INTERVAL, CANDIDATE_PARAMS)
    candidate_eq = _equity_from_exposure(df, candidate_exposure)
    cost3_eq = _equity_from_exposure(df, candidate_exposure, cost_mult=3.0)

    eqs = {
        name: _equity_from_exposure(df, _variant_exposure(df, INTERVAL, params))
        for name, params in candidate_family()
    }
    wf = _walk_forward(eqs, bh, ppy)
    mcpt = _mcpt_variant(INTERVAL, CANDIDATE_PARAMS, n=mcpt_n)

    checks = {
        "wf_beats_bh": bool(wf["oos_sharpe"] > wf["bh_oos_sharpe"]),
        "oos_dd_le_bh": bool(wf["oos_maxdd"] >= wf["bh_oos_maxdd"]),
        "dsr_gt_0p95": bool(wf["dsr"] > 0.95),
        "cost3_beats_bh": bool(metrics.sharpe(cost3_eq, ppy) > metrics.sharpe(bh, ppy)),
        "mcpt_p_lt_0p05": bool(mcpt["p_value"] < 0.05),
    }

    result = {
        "interval": INTERVAL,
        "candidate_params": CANDIDATE_PARAMS,
        "periods": {name: _series_metrics(candidate_eq, bh, *period) for name, period in PERIODS.items()},
        "cost3_sharpe": metrics.sharpe(cost3_eq, ppy),
        "benchmark_sharpe": metrics.sharpe(bh, ppy),
        "walk_forward": wf,
        "mcpt": mcpt,
        "checks": checks,
        "n_pass": sum(checks.values()),
        "all_pass": all(checks.values()),
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "variant_validation.json"
    out.write_text(json.dumps(result, indent=2, default=float), encoding="utf-8")
    return result


def main() -> None:
    result = run()
    full = result["periods"]["full"]
    pre = result["periods"]["pre2013"]
    wf = result["walk_forward"]
    print("Promoted variant validation")
    print(
        "Full: CAGR %.2f%% Sharpe %.2f MaxDD %.1f%%"
        % (full["strategy"]["cagr"] * 100, full["strategy"]["sharpe"], full["strategy"]["max_drawdown"] * 100)
    )
    print(
        "2004-2013: CAGR %.2f%% vs B&H %.2f%%"
        % (pre["strategy"]["cagr"] * 100, pre["benchmark"]["cagr"] * 100)
    )
    print(
        "WFA: OOS Sharpe %.2f vs B&H %.2f, OOS MaxDD %.1f%% vs B&H %.1f%%, DSR %.3f"
        % (wf["oos_sharpe"], wf["bh_oos_sharpe"], wf["oos_maxdd"] * 100, wf["bh_oos_maxdd"] * 100, wf["dsr"])
    )
    print("Cost@3x Sharpe %.2f vs B&H %.2f" % (result["cost3_sharpe"], result["benchmark_sharpe"]))
    print("MCPT p=%.4f (n=%d)" % (result["mcpt"]["p_value"], result["mcpt"]["n_perm"]))
    for name, passed in result["checks"].items():
        print("  %s  %s" % ("PASS" if passed else "FAIL", name))
    print("-> %d/5 gates" % result["n_pass"])
    print("wrote results/variant_validation.json")


if __name__ == "__main__":
    main()
