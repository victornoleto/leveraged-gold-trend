"""Load XAUUSD OHLCV bars from local parquet files.

The raw data is NOT shipped in the repo (the 1-minute file alone is ~100 MB). Fetch it once with
``python scripts/download_data.py`` (Kaggle), which writes ``data/xauusd_<tf>.parquet``. If a
requested timeframe file is missing but ``xauusd_1m.parquet`` exists, it is resampled on the fly.

Data source: Kaggle `novandraanugrah/xauusd-gold-price-historical-data-2004-2024`
(~2004-06 to 2026-01, gold spot, OHLCV; timestamps are broker wall-clock, treated as a single 24h
series). All files share the schema: DatetimeIndex + columns [Open, High, Low, Close, Volume].
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

INTERVALS = ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo")

DATA_DIR = Path(os.environ.get("LGT_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))

# Bars per (calendar) day, gold ~24h. Drives day→bar conversion of the strategy's lookbacks so the
# SAME strategy (windows defined in days) runs comparably on every timeframe.
BARS_PER_DAY = {
    "1m": 1440, "5m": 288, "15m": 96, "30m": 48, "1h": 24, "4h": 6,
    "1d": 1, "1w": 1 / 5, "1mo": 1 / 21,
}

_RESAMPLE_RULE = {
    "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h", "4h": "4h",
    "1d": "1D", "1w": "1W", "1mo": "ME",
}
_AGG = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}


def _path(interval: str) -> Path:
    return DATA_DIR / f"xauusd_{interval}.parquet"


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        date_col = next((c for c in df.columns if c.lower() in ("date", "datetime", "time")), None)
        if date_col is None:
            raise ValueError(f"{path} has no datetime index or date column")
        df = df.set_index(pd.to_datetime(df[date_col])).drop(columns=[date_col])
    return df.sort_index()[["Open", "High", "Low", "Close", "Volume"]]


@lru_cache(maxsize=None)
def load(interval: str = "4h") -> pd.DataFrame:
    """Return the OHLCV DataFrame for a timeframe (native file, else resampled from 1m).

    Cached: do not mutate the returned frame in place (callers here only read it)."""
    if interval not in INTERVALS:
        raise ValueError(f"unknown interval {interval!r}; expected one of {INTERVALS}")
    native = _path(interval)
    if native.exists():
        return _read(native)

    base = _path("1m")
    if not base.exists():
        raise FileNotFoundError(
            f"No data for {interval!r} and no 1m base at {base}.\n"
            f"Run:  python scripts/download_data.py   (downloads XAUUSD from Kaggle)"
        )
    if interval == "1m":
        return _read(base)
    return _read(base).resample(_RESAMPLE_RULE[interval]).agg(_AGG).dropna(how="any")


def close(interval: str = "4h") -> pd.Series:
    return load(interval)["Close"].dropna()
