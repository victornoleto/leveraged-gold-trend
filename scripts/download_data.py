"""Fetch the XAUUSD price data this project uses, into ./data/ as parquet.

Source: Kaggle dataset `novandraanugrah/xauusd-gold-price-historical-data-2004-2024`
(gold spot OHLCV, ~2004-06 .. 2026-01, one CSV per timeframe).

Usage:
    pip install kaggle                # one-time
    # put your Kaggle API token at ~/.kaggle/kaggle.json (chmod 600), then:
    python scripts/download_data.py                 # download every timeframe -> data/*.parquet
    python scripts/download_data.py --resample-from-1m   # only keep 1m, derive the rest locally

Each Kaggle CSV is MetaTrader-style: semicolon-separated, header Date;Open;High;Low;Close;Volume,
date format "%Y.%m.%d %H:%M". We convert to the parquet schema this package reads
(DatetimeIndex + Open/High/Low/Close/Volume).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

SLUG = "novandraanugrah/xauusd-gold-price-historical-data-2004-2024"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TF_ALIASES = {"1Month": "1mo"}  # Kaggle filename token -> our suffix
RESAMPLE_RULE = {"5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h",
                 "1d": "1D", "1w": "1W", "1mo": "ME"}
AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


def _convert_csv(csv: Path, out: Path) -> None:
    df = pd.read_csv(csv, sep=";")
    df.columns = [c.strip().capitalize() for c in df.columns]
    df["Date"] = pd.to_datetime(df["Date"], format="%Y.%m.%d %H:%M", errors="coerce")
    df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
    df = df[["Open", "High", "Low", "Close", "Volume"]].astype(float)
    df.to_parquet(out)
    print(f"  {out.name}: {len(df):,} rows  {df.index.min()} .. {df.index.max()}")


def _kaggle_download() -> None:
    try:
        import kaggle  # noqa: F401
        from kaggle.api.kaggle_api_extended import KaggleApi
    except Exception:
        sys.exit("kaggle not installed. Run:  pip install kaggle  (and set ~/.kaggle/kaggle.json)")
    api = KaggleApi()
    api.authenticate()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {SLUG} -> {DATA_DIR} ...")
    api.dataset_download_files(SLUG, path=str(DATA_DIR), unzip=True)


def main() -> None:
    ap = argparse.ArgumentParser(description="Download XAUUSD data from Kaggle.")
    ap.add_argument("--resample-from-1m", action="store_true",
                    help="after download, keep only 1m and derive every other timeframe locally")
    args = ap.parse_args()

    _kaggle_download()
    csvs = sorted(DATA_DIR.glob("XAU_*_data.csv"))
    if not csvs:
        sys.exit(f"No XAU_*_data.csv found in {DATA_DIR} after download.")
    for csv in csvs:
        tf_raw = csv.stem.split("_")[1]
        tf = TF_ALIASES.get(tf_raw, tf_raw)
        _convert_csv(csv, DATA_DIR / f"xauusd_{tf}.parquet")

    if args.resample_from_1m:
        base = DATA_DIR / "xauusd_1m.parquet"
        if not base.exists():
            sys.exit("xauusd_1m.parquet not found; cannot resample.")
        df = pd.read_parquet(base)
        for tf, rule in RESAMPLE_RULE.items():
            out = DATA_DIR / f"xauusd_{tf}.parquet"
            df.resample(rule).agg(AGG).dropna(how="any").to_parquet(out)
            print(f"  resampled {out.name}")

    print("Done. Try:  python -m leveraged_gold_trend --interval 4h")


if __name__ == "__main__":
    main()
