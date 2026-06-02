"""Performance/risk metrics from an equity curve (pure numpy/pandas).

Annualization uses the EMPIRICAL periods-per-year of the series (bars / calendar-year span). This
matters for gold: it trades ~24h, so the equity-session constants many libraries hard-code (e.g.
1m = 252×390) would badly understate intraday Sharpe. Empirical ppy is correct for every timeframe
and robust to weekend/holiday gaps.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def empirical_ppy(index: pd.DatetimeIndex) -> float:
    """Average bars per year of a datetime index."""
    if len(index) < 2:
        return 252.0
    span_years = (index[-1] - index[0]).days / 365.25
    return len(index) / span_years if span_years > 0 else 252.0


def max_drawdown(equity: pd.Series) -> float:
    equity = equity.dropna()
    if len(equity) == 0:
        return 0.0
    return float((equity / equity.cummax() - 1.0).min())


def sharpe(equity: pd.Series, ppy: float) -> float:
    rets = equity.dropna().pct_change().dropna()
    sd = rets.std(ddof=1)
    if len(rets) < 2 or sd == 0 or np.isnan(sd):
        return 0.0
    return float(rets.mean() / sd * np.sqrt(ppy))


def from_equity(equity: pd.Series, ppy: float, rf_annual: float = 0.0) -> dict:
    """Return/risk metrics derived from the equity curve."""
    equity = equity.dropna()
    rets = equity.pct_change().dropna()
    n = len(rets)
    if n == 0 or equity.iloc[0] == 0:
        return {}

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1.0)
    years = n / ppy
    cagr = float((equity.iloc[-1] / equity.iloc[0]) ** (1.0 / years) - 1.0) if years > 0 else 0.0

    vol_annual = float(rets.std(ddof=1) * np.sqrt(ppy)) if n > 1 else 0.0
    rf_per = (1.0 + rf_annual) ** (1.0 / ppy) - 1.0
    excess = rets - rf_per
    sd = rets.std(ddof=1)
    sr = float(excess.mean() / sd * np.sqrt(ppy)) if sd > 0 else 0.0

    downside = rets[rets < 0]
    dstd = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    sortino = float(excess.mean() / dstd * np.sqrt(ppy)) if dstd > 0 else 0.0

    dd = float((equity / equity.cummax() - 1.0).min())
    calmar = float(cagr / abs(dd)) if dd < 0 else 0.0

    return {
        "total_return": total_return,
        "cagr": cagr,
        "volatility_annual": vol_annual,
        "sharpe": sr,
        "sortino": sortino,
        "max_drawdown": dd,
        "calmar": calmar,
        "n_periods": int(n),
    }
