"""Cross-asset research for the Leveraged Gold Trend engine.

This script is intentionally a research artifact, not a change to the shipped strategy. It applies
the existing Donchian/ATR state machine and a small predeclared variant family to local datasets
under /var/www/victor/finances/quant/datasets. The goal is to test whether the gold result is a
portable trend-following/risk-sizing effect or a single-asset fit.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from leveraged_gold_trend import costs, metrics
from leveraged_gold_trend.strategy import DEFAULT_PARAMS, equity, target_exposure, trade_stats


DATASETS = Path("/var/www/victor/finances/quant/datasets")
RESULTS = Path("results")
INIT_CASH = 10_000.0

AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
RESAMPLE_RULES = {"4h": "4h", "1d": "1D"}
BARS_PER_DAY = {"4h": 6.0, "1d": 1.0}


@dataclass(frozen=True)
class AssetSpec:
    symbol: str
    interval: str
    source: str
    cost_mult: float
    group: str


ASSETS = [
    AssetSpec("XAUUSD", "4h", "xauusd", 1.0, "gold_spot"),
    AssetSpec("XAGUSD", "4h", "forex", 1.2, "metals_fx"),
    AssetSpec("EURUSD", "4h", "forex", 1.0, "fx"),
    AssetSpec("USDJPY", "4h", "forex", 1.0, "fx"),
    AssetSpec("GBPUSD", "4h", "forex", 1.0, "fx"),
    AssetSpec("AUDUSD", "4h", "forex", 1.0, "fx"),
    AssetSpec("SPXUSD", "4h", "spxusd", 1.5, "index_cfd"),
    AssetSpec("GLD", "1d", "cache", 1.5, "etf_gold"),
    AssetSpec("UGL", "1d", "cache", 2.0, "etf_gold_levered"),
    AssetSpec("SPY", "1d", "cache", 1.5, "etf_equity"),
    AssetSpec("QQQ", "1d", "cache", 1.5, "etf_equity"),
    AssetSpec("IWM", "1d", "cache", 1.5, "etf_equity"),
    AssetSpec("UPRO", "1d", "cache", 2.0, "etf_equity_levered"),
    AssetSpec("TQQQ", "1d", "cache", 2.0, "etf_equity_levered"),
    AssetSpec("TLT", "1d", "cache", 1.5, "etf_bonds"),
    AssetSpec("TMF", "1d", "cache", 2.0, "etf_bonds_levered"),
    AssetSpec("DBC", "1d", "cache", 1.5, "etf_commodities"),
    AssetSpec("USO", "1d", "cache", 2.0, "etf_commodities"),
    AssetSpec("BTC-USD", "1d", "cache", 4.0, "crypto"),
    AssetSpec("ETH-USD", "1d", "cache", 4.0, "crypto"),
]


VARIANTS = {
    "headline": {},
    "pure_trend": {"rerisk": False, "bull_overlay": 0.0},
    "lower_risk_3pct": {"risk_pct_per_trade": 0.03},
    "no_short": {"allow_short": False},
    "no_rerisk": {"rerisk": False},
    "small_overlay_025": {"bull_overlay": 0.25},
    "overlay_ema300_plain": {"bull_overlay_ma_type": "ema", "bull_overlay_vol_mult": False},
    "faster_40_80": {
        "long_entry_days": 40,
        "long_exit_days": 15,
        "short_entry_days": 80,
        "short_exit_days": 40,
    },
    "slower_80_150": {
        "long_entry_days": 80,
        "long_exit_days": 30,
        "short_entry_days": 150,
        "short_exit_days": 75,
    },
}

BOOK_GUARDRAILS = [
    "Evidence-Based Technical Analysis / Aronson: programmable rules only; compare against a "
    "nonpredictive benchmark and include data-mining risk.",
    "Pardo and Masters: use walk-forward thinking, robust regions, costs, and avoid broad "
    "post-hoc parameter searches.",
    "Carver: position sizing should be volatility/risk based, trades should have inertia to reduce "
    "costs, and single-instrument Sharpe above 1 deserves skepticism.",
    "Vince/Kelly literature: leverage is a risk decision; lower-risk variants matter even when CAGR "
    "falls.",
]


def _read_parquet(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        date_col = next((c for c in df.columns if c.lower() in ("date", "datetime", "time")), None)
        if date_col is None:
            raise ValueError(f"{path} has no datetime index or date column")
        df = df.set_index(pd.to_datetime(df[date_col])).drop(columns=[date_col])
    out = df.sort_index()[["Open", "High", "Low", "Close", "Volume"]].copy()
    out = out.apply(pd.to_numeric, errors="coerce").dropna(subset=["Close"])
    return out[~out.index.duplicated(keep="last")]


def _latest_cache_file(symbol: str) -> Path:
    files = sorted((DATASETS / "cache").glob(f"{symbol}__1d__*.parquet"))
    if not files:
        raise FileNotFoundError(f"no cache parquet for {symbol}")

    def key(path: Path) -> tuple[pd.Timestamp, pd.Timedelta, float]:
        match = re.search(r"__1d__(\d{4}-\d{2}-\d{2})__(\d{4}-\d{2}-\d{2})\.parquet$", path.name)
        if not match:
            return (pd.Timestamp.min, pd.Timedelta(0), path.stat().st_mtime)
        start, end = pd.Timestamp(match.group(1)), pd.Timestamp(match.group(2))
        return (end, end - start, path.stat().st_mtime)

    return max(files, key=key)


def _base_path(asset: AssetSpec) -> Path:
    key = asset.symbol.lower().replace("-", "")
    if asset.source == "cache":
        return _latest_cache_file(asset.symbol)
    if asset.source == "forex":
        return DATASETS / "forex" / f"{key}_1m.parquet"
    return DATASETS / asset.source / f"{asset.source}_1m.parquet"


def load_asset(asset: AssetSpec) -> pd.DataFrame:
    if asset.source == "xauusd":
        path = DATASETS / "xauusd" / f"xauusd_{asset.interval}.parquet"
        if path.exists():
            return _read_parquet(path)
    if asset.source == "spxusd":
        path = DATASETS / "spxusd" / f"spxusd_{asset.interval}.parquet"
        if path.exists():
            return _read_parquet(path)

    df = _read_parquet(_base_path(asset))
    if asset.interval == "1d":
        if df.index.to_series().diff().dropna().median() >= pd.Timedelta(hours=20):
            return df
    return df.resample(RESAMPLE_RULES[asset.interval]).agg(AGG).dropna(subset=["Open", "High", "Low", "Close"])


def benchmark(df: pd.DataFrame) -> pd.Series:
    close = df["Close"].dropna()
    return INIT_CASH * close / close.iloc[0]


def _variant_params(params: dict) -> dict:
    return {**DEFAULT_PARAMS, **params}


def evaluate(asset: AssetSpec, variant: str, params: dict) -> dict:
    df = load_asset(asset)
    bpd = BARS_PER_DAY[asset.interval]
    p = metrics.empirical_ppy(df.index)
    tx_cost = costs.round_trip_cost(asset.cost_mult)
    eq = equity(df, _variant_params(params), bpd, init_cash=INIT_CASH, cost=tx_cost)
    bh = benchmark(df)
    m = metrics.from_equity(eq, p)
    bm = metrics.from_equity(bh, p)
    exposure = target_exposure(df, _variant_params(params), bpd)
    ts = trade_stats(exposure)
    cost3 = equity(df, _variant_params(params), bpd, init_cash=INIT_CASH, cost=tx_cost * 3.0)

    split = df.index[0] + (df.index[-1] - df.index[0]) * 0.6
    oos_eq = eq.loc[split:]
    oos_bh = bh.loc[split:]
    oos_ppy = metrics.empirical_ppy(oos_eq.index)
    oos_m = metrics.from_equity(oos_eq, oos_ppy) if len(oos_eq) > 252 else {}
    oos_bm = metrics.from_equity(oos_bh, oos_ppy) if len(oos_bh) > 252 else {}

    return {
        "symbol": asset.symbol,
        "interval": asset.interval,
        "group": asset.group,
        "variant": variant,
        "start": df.index[0].date().isoformat(),
        "end": df.index[-1].date().isoformat(),
        "bars": len(df),
        "cost_mult": asset.cost_mult,
        "cagr": m.get("cagr"),
        "sharpe": m.get("sharpe"),
        "maxdd": m.get("max_drawdown"),
        "calmar": m.get("calmar"),
        "bh_cagr": bm.get("cagr"),
        "bh_sharpe": bm.get("sharpe"),
        "bh_maxdd": bm.get("max_drawdown"),
        "excess_cagr": m.get("cagr", 0.0) - bm.get("cagr", 0.0),
        "cost3_sharpe": metrics.sharpe(cost3, p),
        "n_trades": ts["n_trades"],
        "avg_leverage": ts["avg_leverage"],
        "max_leverage": ts["max_leverage"],
        "pct_time_in_market": ts["pct_time_in_market"],
        "oos_start": split.date().isoformat(),
        "oos_cagr": oos_m.get("cagr"),
        "oos_sharpe": oos_m.get("sharpe"),
        "oos_maxdd": oos_m.get("max_drawdown"),
        "oos_bh_cagr": oos_bm.get("cagr"),
        "oos_bh_sharpe": oos_bm.get("sharpe"),
        "params": json.dumps(params, sort_keys=True),
    }


def scan(assets: list[AssetSpec]) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    rows = []
    skipped = []
    for asset in assets:
        print(f"scanning {asset.symbol} {asset.interval} ...", flush=True)
        try:
            for variant, params in VARIANTS.items():
                rows.append(evaluate(asset, variant, params))
        except FileNotFoundError as exc:
            skipped.append(f"{asset.symbol} {asset.interval}: {exc}")
    table = pd.DataFrame(rows)
    best = (
        table.sort_values(["symbol", "sharpe", "calmar", "excess_cagr"], ascending=[True, False, False, False])
        .groupby(["symbol", "interval"], as_index=False)
        .head(1)
        .reset_index(drop=True)
    )
    return table, best, skipped


def _fmt_pct(value: float | None) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{100.0 * value:.2f}%"


def _fmt_num(value: float | None) -> str:
    if value is None or pd.isna(value):
        return ""
    return f"{value:.2f}"


def write_report(table: pd.DataFrame, best: pd.DataFrame, skipped: list[str]) -> Path:
    headline = table[table["variant"] == "headline"].copy()
    portable = headline[
        (headline["sharpe"] > headline["bh_sharpe"])
        & (headline["sharpe"] >= 0.50)
        & (headline["maxdd"] >= headline["bh_maxdd"])
        & (headline["cost3_sharpe"] > headline["bh_sharpe"])
        & (headline["oos_sharpe"] > headline["oos_bh_sharpe"])
    ]
    portable_keys = set(zip(portable["symbol"], portable["interval"]))
    improved = best.merge(
        headline[["symbol", "interval", "variant", "sharpe", "maxdd", "cagr"]],
        on=["symbol", "interval"],
        suffixes=("_best", "_headline"),
    )
    improved = improved[
        (improved["variant_best"] != "headline")
        & (improved["sharpe_best"] > improved["sharpe_headline"] + 0.05)
    ]
    best_counts = best["variant"].value_counts()

    lines = [
        "# Cross-Asset Research",
        "",
        "Research branch artifact for testing whether the Leveraged Gold Trend rules have room for "
        "improvement and whether they port to other local assets.",
        "",
        "## Book-Derived Guardrails",
        "",
        *[f"- {item}" for item in BOOK_GUARDRAILS],
        "",
        "## Findings",
        "",
        f"- Tested {headline['symbol'].nunique()} assets across {len(VARIANTS)} predeclared variants.",
        f"- Headline rules passed the stricter portability screen on {len(portable)} assets: "
        f"{', '.join(portable['symbol'].tolist()) or 'none'}.",
        f"- Non-headline variants improved headline Sharpe by >0.05 on {len(improved)} assets.",
        f"- Most common best variants: "
        f"{', '.join(f'{name} ({count})' for name, count in best_counts.head(3).items())}.",
        f"- Skipped {len(skipped)} configured assets with missing local files.",
        "- The results are cross-asset evidence only; they are not a promotion of any new default "
        "without a fuller walk-forward/permutation battery per asset.",
        "",
        "## Headline Strategy By Asset",
        "",
        "| Asset | TF | CAGR | Sharpe | MaxDD | B&H Sharpe | Cost3 Sharpe | Trades | OOS Sharpe | Verdict |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for _, row in headline.sort_values(["group", "symbol"]).iterrows():
        verdict = "portable" if (row["symbol"], row["interval"]) in portable_keys else "asset-specific/weak"
        lines.append(
            f"| {row['symbol']} | {row['interval']} | {_fmt_pct(row['cagr'])} | {_fmt_num(row['sharpe'])} | "
            f"{_fmt_pct(row['maxdd'])} | {_fmt_num(row['bh_sharpe'])} | {_fmt_num(row['cost3_sharpe'])} | "
            f"{int(row['n_trades'])} | {_fmt_num(row['oos_sharpe'])} | {verdict} |"
        )
    lines.extend([
        "",
        "## Best Variant Per Asset",
        "",
        "| Asset | TF | Best variant | CAGR | Sharpe | MaxDD | B&H Sharpe | OOS Sharpe | Params |",
        "|---|---:|---|---:|---:|---:|---:|---:|---|",
    ])
    for _, row in best.sort_values(["group", "symbol"]).iterrows():
        lines.append(
            f"| {row['symbol']} | {row['interval']} | {row['variant']} | {_fmt_pct(row['cagr'])} | "
            f"{_fmt_num(row['sharpe'])} | {_fmt_pct(row['maxdd'])} | {_fmt_num(row['bh_sharpe'])} | "
            f"{_fmt_num(row['oos_sharpe'])} | `{row['params']}` |"
        )
    lines.extend([
        "",
        "## Skipped Assets",
        "",
        *([f"- {item}" for item in skipped] if skipped else ["- None."]),
        "",
        "## Interpretation",
        "",
        "- If gold remains among the few assets clearing the portable screen, the current strategy should "
        "stay framed as gold-specific rather than a universal trend engine.",
        "- If a simpler variant such as `pure_trend`, `lower_risk_3pct`, or `small_overlay_025` wins "
        "across several unrelated assets, that is the next candidate for a proper walk-forward and "
        "permutation validation.",
        "- Leveraged ETF results need extra caution: those products already embed leverage, financing "
        "and path decay, so external strategy leverage can compound tail risk.",
    ])

    out = RESULTS / "cross_asset_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-asset research for Leveraged Gold Trend")
    parser.add_argument("--assets", nargs="*", help="optional symbols to scan")
    args = parser.parse_args()

    selected = ASSETS
    if args.assets:
        wanted = {s.upper() for s in args.assets}
        selected = [a for a in ASSETS if a.symbol.upper() in wanted]
        missing = wanted - {a.symbol.upper() for a in selected}
        if missing:
            raise SystemExit(f"unknown assets: {', '.join(sorted(missing))}")

    RESULTS.mkdir(parents=True, exist_ok=True)
    table, best, skipped = scan(selected)
    table.to_csv(RESULTS / "cross_asset_scan.csv", index=False)
    best.to_csv(RESULTS / "cross_asset_best.csv", index=False)
    report = write_report(table, best, skipped)
    print(f"wrote {RESULTS / 'cross_asset_scan.csv'}")
    print(f"wrote {RESULTS / 'cross_asset_best.csv'}")
    print(f"wrote {report}")


if __name__ == "__main__":
    main()
