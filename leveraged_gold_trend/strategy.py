"""The Leveraged Gold Trend strategy (Approach A) — pure numpy/pandas, no vectorbt.

Edge: gold trends (long safe-haven / inflation moves) between extended ranges. We
  • ENTER on a Donchian breakout (new N-day high → long; new N-day low → short),
  • EXIT on an ATR (Chandelier) trailing stop that ratchets toward price, locking gains and letting
    winners run — no take-profit, because a profit target caps the right tail where trend following
    makes its money,
  • SIZE by risk-per-trade so leverage *emerges* from the stop distance and is bounded by a hard cap.

Risk-per-trade sizing (the heart of "governed leverage"): if notional = f·equity and price moves
``stop_frac`` against us, the loss is f·equity·stop_frac. Setting that equal to ``risk_pct``·equity
gives f = risk_pct / stop_frac, clamped to ``leverage_cap``. A tight stop (low vol) → larger size,
but never beyond the cap. Leverage is a *consequence of risk*, never a "win-more" dial.

Headline equity is returns-based: a causal signed-exposure series (decided at each bar's close,
earning the next bar's return — so it is effectively lagged) times asset returns, minus turnover
cost. The optional ``regime_ma`` (off by default) adds a trend filter — that variant is "Approach C"
in the report.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import costs as _costs

DEFAULT_PARAMS: dict = {
    "long_entry_days": 55,
    "long_exit_days": 20,
    "short_entry_days": 100,
    "short_exit_days": 50,
    "atr_days": 20,
    "stop_atr": 5.0,             # Chandelier trailing-stop distance, in ATRs
    "risk_pct_per_trade": 0.05,  # f% of equity risked to the initial stop (sweep 0.02–0.05)
    "leverage_cap": 3.0,         # hard ceiling on gross exposure (× notional)
    "allow_short": True,
    "regime_ma": 0,              # 0 = off (Approach A); >0 days = Approach C (trend filter)
}


def _bars(days: float, bars_per_day: float) -> int:
    return max(1, int(round(float(days) * bars_per_day)))


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, span: int) -> pd.Series:
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(span=span, adjust=False, min_periods=span).mean()


def _signals(df: pd.DataFrame, params: dict, bars_per_day: float) -> dict:
    close, high, low = df["Close"], df["High"], df["Low"]
    le = _bars(params["long_entry_days"], bars_per_day)
    lx = _bars(params["long_exit_days"], bars_per_day)
    se = _bars(params.get("short_entry_days", params["long_entry_days"]), bars_per_day)
    sx = _bars(params.get("short_exit_days", params["long_exit_days"]), bars_per_day)
    atr_span = _bars(params.get("atr_days", 20), bars_per_day)

    long_entry = close >= close.shift(1).rolling(le, min_periods=le).max()
    long_exit = close <= close.shift(1).rolling(lx, min_periods=lx).min()
    if bool(params.get("allow_short", True)):
        short_entry = close <= close.shift(1).rolling(se, min_periods=se).min()
        short_exit = close >= close.shift(1).rolling(sx, min_periods=sx).max()
    else:
        short_entry = pd.Series(False, index=close.index)
        short_exit = pd.Series(False, index=close.index)

    regime_ma = int(params.get("regime_ma", 0))
    if regime_ma > 0:  # Approach C: only longs above the MA, only shorts below
        win = _bars(regime_ma, bars_per_day)
        ma = close.rolling(win, min_periods=win).mean()
        long_entry = long_entry & (close > ma)
        short_entry = short_entry & (close < ma)

    return {
        "close": close,
        "atr": _atr(high, low, close, atr_span),
        "long_entry": long_entry.fillna(False).to_numpy(bool),
        "long_exit": long_exit.fillna(False).to_numpy(bool),
        "short_entry": short_entry.fillna(False).to_numpy(bool),
        "short_exit": short_exit.fillna(False).to_numpy(bool),
    }


def target_exposure(df: pd.DataFrame, params: dict, bars_per_day: float) -> pd.Series:
    """Signed exposure (fraction of equity) from a causal state machine. Entry sizes to risk_pct at
    the initial ATR stop, capped at leverage_cap; exit on a Chandelier ATR trailing stop or the
    opposite Donchian channel."""
    sig = _signals(df, params, bars_per_day)
    c = sig["close"].to_numpy(float)
    a = sig["atr"].to_numpy(float)
    le, lx = sig["long_entry"], sig["long_exit"]
    se, sx = sig["short_entry"], sig["short_exit"]

    stop_atr = float(params.get("stop_atr", 5.0))
    risk_pct = float(params.get("risk_pct_per_trade", 0.05))
    cap = float(params.get("leverage_cap", 3.0))
    allow_short = bool(params.get("allow_short", True))

    n = len(c)
    exposure = np.zeros(n)
    pos = 0.0
    peak = trough = 0.0
    for t in range(n):
        atr_t = a[t]
        exited = False
        if pos > 0.0:
            peak = max(peak, c[t])
            if (not np.isnan(atr_t) and c[t] <= peak - stop_atr * atr_t) or lx[t]:
                pos, exited = 0.0, True
        elif pos < 0.0:
            trough = min(trough, c[t])
            if (not np.isnan(atr_t) and c[t] >= trough + stop_atr * atr_t) or sx[t]:
                pos, exited = 0.0, True

        if pos == 0.0 and not exited and not np.isnan(atr_t) and atr_t > 0.0:
            size = min(risk_pct * c[t] / (stop_atr * atr_t), cap)
            if le[t]:
                pos, peak = size, c[t]
            elif allow_short and se[t]:
                pos, trough = -size, c[t]
        exposure[t] = pos
    return pd.Series(exposure, index=sig["close"].index)


def equity(df: pd.DataFrame, params: dict, bars_per_day: float,
           init_cash: float = 10_000.0, cost: float | None = None) -> pd.Series:
    """Returns-based equity curve: exposure(t-1)·return(t) − cost·|Δexposure|, compounded."""
    exposure = target_exposure(df, params, bars_per_day)
    rets = df["Close"].pct_change().reindex(exposure.index).fillna(0.0)
    if cost is None:
        cost = _costs.round_trip_cost()
    turnover = exposure.diff().abs().fillna(exposure.abs())
    port_ret = exposure.shift(1).fillna(0.0) * rets - cost * turnover
    return init_cash * (1.0 + port_ret).cumprod()


def trade_stats(exposure: pd.Series) -> dict:
    """Trade count / time-in-market / leverage from the signed-exposure series."""
    gross = exposure.abs()
    active = gross > 1e-9
    sign = np.sign(exposure.to_numpy())
    n_trades = int(np.sum((sign[1:] != sign[:-1]) & (sign[1:] != 0))) if len(sign) > 1 else 0
    return {
        "n_trades": n_trades,
        "avg_leverage": float(gross[active].mean()) if active.any() else 0.0,
        "max_leverage": float(gross.max()) if len(gross) else 0.0,
        "pct_time_in_market": float(active.mean()) if len(active) else 0.0,
    }
