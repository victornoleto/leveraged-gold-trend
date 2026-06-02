"""Leveraged Gold Trend — a governed-leverage trend-following strategy on gold (XAUUSD).

Public, self-contained package (numpy/pandas/scipy only — no vectorbt). The headline equity is
returns-based: a signed exposure series (capped at a hard leverage ceiling) times asset returns,
net of turnover cost. See README.md for the full report and the timeframe study.
"""

from . import costs, data, metrics, strategy  # noqa: F401

__version__ = "1.0.0"
