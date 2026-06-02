"""Scan research variants aimed at improving the 2004-2013 benchmark gap.

This is a research script, not the shipped default path. It keeps the original pure Donchian/ATR
system as an explicit baseline, then evaluates two small, literature-led families:

1. Trade re-risking / pyramiding at new favorable closes.
2. A benchmark-aware long overlay while the main state machine is flat and gold is above a trend MA.

The output is a CSV under results/ plus a concise ranking by pre-2013 excess performance.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from leveraged_gold_trend import costs, data, metrics
from leveraged_gold_trend.strategy import DEFAULT_PARAMS, target_exposure, trade_stats


INIT_CASH = 10_000.0
RESULTS = Path("results")

PURE_TREND_PARAMS = {
    **DEFAULT_PARAMS,
    "rerisk": False,
    "rerisk_increase_only": False,
    "rerisk_inertia": 0.0,
    "bull_overlay": 0.0,
    "bull_overlay_ma_type": "sma",
    "bull_overlay_vol_mult": False,
}

PERIODS = {
    "full": (None, None),
    "pre2013": ("2004-01-01", "2013-12-31"),
    "post2013": ("2014-01-01", None),
}


def _bars(days: float, bars_per_day: float) -> int:
    return max(1, int(round(float(days) * bars_per_day)))


def _equity_from_exposure(df: pd.DataFrame, exposure: pd.Series, cost_mult: float = 1.0) -> pd.Series:
    rets = df["Close"].pct_change().reindex(exposure.index).fillna(0.0)
    turnover = exposure.diff().abs().fillna(exposure.abs())
    port_ret = exposure.shift(1).fillna(0.0) * rets - costs.round_trip_cost(cost_mult) * turnover
    return INIT_CASH * (1.0 + port_ret).cumprod()


def _benchmark(df: pd.DataFrame) -> pd.Series:
    close = df["Close"].dropna()
    return INIT_CASH * close / close.iloc[0]


def _slice_metrics(eq: pd.Series, bh: pd.Series, start: str | None, end: str | None) -> dict:
    e = eq.loc[start:end].dropna()
    b = bh.loc[start:end].dropna()
    if len(e) < 3 or len(b) < 3:
        return {}
    ppy = metrics.empirical_ppy(e.index)
    em = metrics.from_equity(e, ppy)
    bm = metrics.from_equity(b, ppy)
    strat_total = e.iloc[-1] / e.iloc[0] - 1.0
    bh_total = b.iloc[-1] / b.iloc[0] - 1.0
    return {
        "strat_cagr": em["cagr"],
        "strat_sharpe": em["sharpe"],
        "strat_maxdd": em["max_drawdown"],
        "strat_calmar": em["calmar"],
        "strat_total": strat_total,
        "bh_cagr": bm["cagr"],
        "bh_sharpe": bm["sharpe"],
        "bh_maxdd": bm["max_drawdown"],
        "bh_total": bh_total,
        "excess_cagr": em["cagr"] - bm["cagr"],
        "excess_total": strat_total - bh_total,
        "beats_bh_total": strat_total > bh_total,
        "beats_bh_sharpe": em["sharpe"] > bm["sharpe"],
        "beats_bh_dd": em["max_drawdown"] >= bm["max_drawdown"],
    }


def _candidate_params() -> list[tuple[str, dict]]:
    rerisk_variants = [
        ("none", {}),
        ("rerisk_rebalance_i10", {"rerisk": True, "rerisk_inertia": 0.10}),
        ("rerisk_rebalance_i25", {"rerisk": True, "rerisk_inertia": 0.25}),
        ("rerisk_pyramid_i10", {"rerisk": True, "rerisk_increase_only": True, "rerisk_inertia": 0.10}),
        ("rerisk_pyramid_i25", {"rerisk": True, "rerisk_increase_only": True, "rerisk_inertia": 0.25}),
    ]

    overlays = [("none", {})]
    for ma_days in (100, 200, 300):
        for overlay in (0.25, 0.50, 1.00):
            overlays.append((
                f"overlay_{overlay:g}x_sma{ma_days}",
                {"bull_overlay": overlay, "bull_overlay_ma_days": ma_days},
            ))
            overlays.append((
                f"overlay_{overlay:g}x_ema{ma_days}",
                {"bull_overlay": overlay, "bull_overlay_ma_days": ma_days, "bull_overlay_ma_type": "ema"},
            ))

    out = [("baseline", {})]
    for rerisk_name, rerisk_params in rerisk_variants:
        for overlay_name, overlay_params in overlays:
            if rerisk_name == overlay_name == "none":
                continue
            name = "+".join(part for part in (rerisk_name, overlay_name) if part != "none")
            out.append((name, {**rerisk_params, **overlay_params}))

    # Second-wave research overlays from the absorbed literature. These are applied only while the
    # Donchian/ATR state machine is flat, so they are direct alternatives to the simple bull overlay.
    research_overlays = []
    for amount in (0.50, 0.75, 1.00):
        research_overlays.extend([
            (f"research_overlay_{amount:g}x_absmom252", {
                "research_overlay": amount, "research_overlay_mode": "abs_mom", "research_overlay_days": 252,
            }),
            (f"research_overlay_{amount:g}x_absmom300", {
                "research_overlay": amount, "research_overlay_mode": "abs_mom", "research_overlay_days": 300,
            }),
            (f"research_overlay_{amount:g}x_ema64_256", {
                "research_overlay": amount, "research_overlay_mode": "ema_cross",
                "research_overlay_fast_days": 64, "research_overlay_slow_days": 256,
            }),
            (f"research_overlay_{amount:g}x_ema50_200", {
                "research_overlay": amount, "research_overlay_mode": "ema_cross",
                "research_overlay_fast_days": 50, "research_overlay_slow_days": 200,
            }),
            (f"overlay_{amount:g}x_ema300_volmult", {
                "bull_overlay": amount, "bull_overlay_ma_days": 300,
                "bull_overlay_ma_type": "ema", "bull_overlay_vol_mult": True,
            }),
            (f"research_overlay_{amount:g}x_breakout160", {
                "research_overlay": amount, "research_overlay_mode": "breakout_cont",
                "research_overlay_days": 160,
            }),
            (f"research_overlay_{amount:g}x_breakout320", {
                "research_overlay": amount, "research_overlay_mode": "breakout_cont",
                "research_overlay_days": 320,
            }),
        ])
    for name, overlay_params in research_overlays:
        out.append((f"rerisk_rebalance_i10+{name}", {"rerisk": True, "rerisk_inertia": 0.10, **overlay_params}))
    return out


def _target_params(params: dict) -> dict:
    """Drop script-only research keys before calling the strategy state machine."""
    return {k: v for k, v in params.items() if not k.startswith("research_overlay")}


def _research_overlay(df: pd.DataFrame, params: dict, bars_per_day: float, cap: float) -> pd.Series | None:
    amount = float(params.get("research_overlay", 0.0))
    mode = params.get("research_overlay_mode")
    if amount <= 0.0 or not mode:
        return None

    close = df["Close"]
    amount = min(amount, cap)
    overlay = pd.Series(0.0, index=close.index)

    if mode == "abs_mom":
        win = _bars(params.get("research_overlay_days", 252), bars_per_day)
        overlay[close > close.shift(win)] = amount
    elif mode == "ema_cross":
        fast = _bars(params.get("research_overlay_fast_days", 64), bars_per_day)
        slow = _bars(params.get("research_overlay_slow_days", 256), bars_per_day)
        f = close.ewm(span=fast, adjust=False, min_periods=fast).mean()
        s = close.ewm(span=slow, adjust=False, min_periods=slow).mean()
        overlay[f > s] = amount
    elif mode == "ma_vol_mult":
        win = _bars(params.get("research_overlay_days", 300), bars_per_day)
        if str(params.get("research_overlay_ma_type", "sma")).lower() == "ema":
            ma = close.ewm(span=win, adjust=False, min_periods=win).mean()
        else:
            ma = close.rolling(win, min_periods=win).mean()
        rets = close.pct_change()
        vol_win = _bars(32, bars_per_day)
        hist_win = _bars(252 * 5, bars_per_day)
        min_hist = _bars(252, bars_per_day)
        current_vol = rets.rolling(vol_win, min_periods=vol_win).std()
        long_vol = current_vol.expanding(min_periods=min_hist).mean()
        rel_vol = current_vol / long_vol
        vol_rank = rel_vol.rolling(hist_win, min_periods=min_hist).rank(pct=True)
        mult = (2.0 - 1.5 * vol_rank).ewm(span=_bars(10, bars_per_day), adjust=False).mean()
        overlay[close > ma] = (amount * mult[close > ma]).clip(lower=0.0, upper=cap)
    elif mode == "breakout_cont":
        win = _bars(params.get("research_overlay_days", 160), bars_per_day)
        hi = close.rolling(win, min_periods=win).max()
        lo = close.rolling(win, min_periods=win).min()
        rng = (hi - lo).replace(0.0, pd.NA)
        raw = 40.0 * (close - 0.5 * (hi + lo)) / rng
        scale = (raw.clip(lower=0.0, upper=20.0) / 20.0).fillna(0.0)
        overlay = amount * scale
    else:
        raise ValueError(f"unknown research overlay mode: {mode!r}")

    return overlay.fillna(0.0).clip(lower=0.0, upper=cap)


def _variant_exposure(df: pd.DataFrame, interval: str, params: dict) -> pd.Series:
    full_params = {**PURE_TREND_PARAMS, **_target_params(params)}
    exposure = target_exposure(df, full_params, data.BARS_PER_DAY[interval])
    overlay = _research_overlay(df, params, data.BARS_PER_DAY[interval], full_params["leverage_cap"])
    if overlay is not None:
        exposure = exposure.where(exposure.abs() > 1e-9, overlay)
    return exposure


def _df_from_close(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 0.0})


def _mcpt_variant(interval: str, params: dict, n: int, seed: int = 42) -> dict:
    ppy = metrics.empirical_ppy(data.close(interval).index)
    close = data.close(interval)
    df = _df_from_close(close)
    obs_exposure = _variant_exposure(df, interval, params)
    obs = metrics.sharpe(_equity_from_exposure(df, obs_exposure), ppy)

    logret = np.log(close / close.shift(1)).dropna().to_numpy()
    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(n):
        synth = close.iloc[0] * np.exp(np.r_[0.0, rng.permutation(logret)].cumsum())
        synth_df = _df_from_close(pd.Series(synth, index=close.index))
        exposure = _variant_exposure(synth_df, interval, params)
        eq = _equity_from_exposure(synth_df, exposure)
        if metrics.sharpe(eq, ppy) >= obs:
            ge += 1
    return {"obs_sharpe": obs, "p_value": (ge + 1) / (n + 1), "n_perm": n}


def scan(interval: str = "4h", mcpt_top: int = 0, mcpt_n: int = 100) -> pd.DataFrame:
    df = data.load(interval)
    bh = _benchmark(df)
    ppy = metrics.empirical_ppy(df.index)
    rows = []

    for name, params in _candidate_params():
        exposure = _variant_exposure(df, interval, params)
        eq = _equity_from_exposure(df, exposure)
        eq_cost3 = _equity_from_exposure(df, exposure, cost_mult=3.0)
        ts = trade_stats(exposure)
        row = {
            "variant": name,
            "params": json.dumps(params, sort_keys=True),
            "cost3_sharpe": metrics.sharpe(eq_cost3, ppy),
            **ts,
        }
        for period, (start, end) in PERIODS.items():
            for key, value in _slice_metrics(eq, bh, start, end).items():
                row[f"{period}_{key}"] = value
        rows.append(row)

    table = pd.DataFrame(rows)
    table = table.sort_values(
        ["pre2013_excess_total", "full_strat_sharpe", "full_strat_maxdd"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    if mcpt_top > 0:
        top_variants = table.head(mcpt_top)["variant"].tolist()
        params_by_name = dict(_candidate_params())
        mcpt = {}
        for name in top_variants:
            mcpt[name] = _mcpt_variant(interval, params_by_name[name], n=mcpt_n)
        table["mcpt_p"] = table["variant"].map(lambda x: mcpt.get(x, {}).get("p_value"))
        table["mcpt_obs_sharpe"] = table["variant"].map(lambda x: mcpt.get(x, {}).get("obs_sharpe"))

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / "variant_scan.csv"
    table.to_csv(out, index=False)
    return table


def _fmt_pct(value: float) -> str:
    return f"{100.0 * value:.2f}%"


def _print_view(table: pd.DataFrame, cols: list[str], n: int = 12) -> None:
    view = table[cols].head(n).copy()
    for col in view.columns:
        if col.endswith(("cagr", "maxdd", "excess_total", "pct_time_in_market")):
            view[col] = view[col].map(_fmt_pct)
        elif col not in ("variant", "n_trades"):
            view[col] = view[col].map(lambda x: "" if pd.isna(x) else f"{x:.3f}")
    print(view.to_string(index=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan Leveraged Gold Trend research variants")
    parser.add_argument("--interval", default="4h", choices=data.INTERVALS)
    parser.add_argument("--mcpt-top", type=int, default=0, help="run MCPT for the top N variants")
    parser.add_argument("--mcpt-n", type=int, default=100, help="number of MCPT permutations")
    args = parser.parse_args()

    table = scan(args.interval, mcpt_top=args.mcpt_top, mcpt_n=args.mcpt_n)
    cols = [
        "variant",
        "pre2013_strat_cagr",
        "pre2013_bh_cagr",
        "pre2013_excess_total",
        "full_strat_cagr",
        "full_strat_sharpe",
        "full_strat_maxdd",
        "post2013_strat_cagr",
        "cost3_sharpe",
        "n_trades",
        "pct_time_in_market",
        "avg_leverage",
    ]
    if "mcpt_p" in table.columns:
        cols.append("mcpt_p")

    print("Top by 2004-2013 excess total return")
    _print_view(table, cols)

    baseline = table.loc[table["variant"] == "baseline"].iloc[0]
    balanced = table[
        (table["pre2013_beats_bh_total"])
        & (table["full_strat_sharpe"] >= baseline["full_strat_sharpe"])
        & (table["full_strat_maxdd"] >= baseline["full_strat_maxdd"])
    ]
    if len(balanced):
        print("\nBest while preserving baseline full-period Sharpe and MaxDD")
        _print_view(balanced, cols, n=8)
    print(f"\nwrote {RESULTS / 'variant_scan.csv'}")


if __name__ == "__main__":
    main()
