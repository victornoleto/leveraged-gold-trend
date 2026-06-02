"""Anti-overfitting validation for the promoted gold trend strategy.

Five gates a timeframe must clear to be trustworthy:
  1. WALK-FORWARD (Pardo): pick from the small neighbouring promoted-strategy family on each TRAIN
     window by max train-Sharpe s.t. train MaxDD <= train buy&hold MaxDD; apply out-of-sample;
     stitch. PASS: OOS Sharpe > buy&hold.
  2. OOS MaxDD <= buy&hold gold (hard constraint).
  3. DEFLATED SHARPE > 0.95 over the trial count (López de Prado).
  4. COST-STRESS: edge survives 3× nominal cost (the honesty check for fast timeframes).
  5. PERMUTATION / MCPT: i.i.d.-shuffle returns (destroys trend structure), rebuild the price path,
     re-run; PASS: p < 0.05 that the real ordering's Sharpe beats random (Masters / Aronson).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew

from . import costs, data, metrics
from .strategy import DEFAULT_PARAMS, equity

INIT_CASH = 10_000.0
HEADLINE_RISK = 0.05
MIN_TRAIN_BARS = 30

# Small, predeclared robustness region around the shipped default. The headline candidate is one of
# these variants: r=5%, re-risk inertia 0.10, 0.50x EMA300 overlay with volatility multiplier.
OVERLAY_LEVELS = (0.25, 0.50, 0.75, 1.00)
OVERLAY_MA_DAYS = (200, 300)
OVERLAY_VOL_MULT = (False, True)
RERISK_INERTIA = (0.10, 0.25)

# Train ~6y, test 2y; OOS spans 2012–2025.
WINDOWS = [
    ("2006-01-01", "2011-12-31", "2012-01-01", "2013-12-31"),
    ("2008-01-01", "2013-12-31", "2014-01-01", "2015-12-31"),
    ("2010-01-01", "2015-12-31", "2016-01-01", "2017-12-31"),
    ("2012-01-01", "2017-12-31", "2018-01-01", "2019-12-31"),
    ("2014-01-01", "2019-12-31", "2020-01-01", "2021-12-31"),
    ("2016-01-01", "2021-12-31", "2022-01-01", "2023-12-31"),
    ("2018-01-01", "2023-12-31", "2024-01-01", "2025-12-31"),
]


def ppy(interval: str) -> float:
    return metrics.empirical_ppy(data.close(interval).index)


def equity_for(interval: str, params: dict, cost_mult: float = 1.0) -> pd.Series:
    df = data.load(interval)
    p = {**DEFAULT_PARAMS, **params}
    return equity(df, p, data.BARS_PER_DAY[interval], init_cash=INIT_CASH,
                  cost=costs.round_trip_cost(cost_mult))


def benchmark(interval: str) -> pd.Series:
    c = data.close(interval)
    return INIT_CASH * c / c.iloc[0]


def _cid(c: dict) -> str:
    suffix = "vol" if c["bull_overlay_vol_mult"] else "plain"
    return (f"r{int(c['risk_pct_per_trade'] * 100)}_i{int(c['rerisk_inertia'] * 100)}_"
            f"ov{c['bull_overlay']:g}_ema{c['bull_overlay_ma_days']}_{suffix}")


def _candidates() -> list[dict]:
    return [
        {
            "risk_pct_per_trade": HEADLINE_RISK,
            "rerisk": True,
            "rerisk_increase_only": False,
            "rerisk_inertia": inertia,
            "bull_overlay": overlay,
            "bull_overlay_ma_days": ma_days,
            "bull_overlay_ma_type": "ema",
            "bull_overlay_vol_mult": vol_mult,
        }
        for overlay in OVERLAY_LEVELS
        for ma_days in OVERLAY_MA_DAYS
        for vol_mult in OVERLAY_VOL_MULT
        for inertia in RERISK_INERTIA
    ]


def deflated_sharpe(returns: pd.Series, sr_trials: list[float], sr_obs: float, p: float) -> float:
    """P(true Sharpe > 0) after deflating for the number of trials and non-normality."""
    r = returns.dropna()
    T = len(r)
    if T < 3:
        return float("nan")
    sr_o = sr_obs / np.sqrt(p)
    tr = np.array(sr_trials) / np.sqrt(p)
    N = max(len(tr), 2)
    var_sr = float(np.var(tr, ddof=1)) if len(tr) > 1 else 0.0
    g = 0.5772156649
    sr0 = np.sqrt(var_sr) * ((1 - g) * norm.ppf(1 - 1 / N) + g * norm.ppf(1 - 1 / (N * np.e)))
    sk, kt = float(skew(r)), float(kurtosis(r, fisher=False))
    den = np.sqrt(max(1e-9, 1 - sk * sr_o + (kt - 1) / 4 * sr_o ** 2))
    return float(norm.cdf((sr_o - sr0) * np.sqrt(T - 1) / den))


def _df_from_close(close: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({"Open": close, "High": close, "Low": close, "Close": close, "Volume": 0.0})


def mcpt(interval: str, params: dict, n: int, seed: int = 42) -> dict:
    """Permutation test: shuffle log-returns i.i.d. (kills trend), rebuild the price, re-run."""
    p = ppy(interval)
    bpd = data.BARS_PER_DAY[interval]
    cost = costs.round_trip_cost()
    pp = {**DEFAULT_PARAMS, **params}
    c = data.close(interval)
    obs = metrics.sharpe(equity(_df_from_close(c), pp, bpd, cost=cost), p)
    logret = np.log(c / c.shift(1)).dropna().to_numpy()
    rng = np.random.default_rng(seed)
    ge = 0
    for _ in range(n):
        synth = c.iloc[0] * np.exp(np.r_[0.0, rng.permutation(logret)].cumsum())
        eq = equity(_df_from_close(pd.Series(synth, index=c.index)), pp, bpd, cost=cost)
        if metrics.sharpe(eq, p) >= obs:
            ge += 1
    return {"obs_sharpe": obs, "p_value": (ge + 1) / (n + 1), "n_perm": n}


def walk_forward(interval: str) -> dict:
    p = ppy(interval)
    eqs = {_cid(c): equity_for(interval, c) for c in _candidates()}
    bh = benchmark(interval)
    trial_sr = [metrics.sharpe(eq, p) for eq in eqs.values()]

    oos_rets, bh_rets, picks = [], [], []
    for tr_s, tr_e, te_s, te_e in WINDOWS:
        bh_tr_dd = metrics.max_drawdown(bh.loc[tr_s:tr_e])
        scored = []
        for cid, eq in eqs.items():
            tr = eq.loc[tr_s:tr_e]
            if len(tr) < MIN_TRAIN_BARS:
                continue
            m = metrics.from_equity(tr, p)
            scored.append((cid, m.get("sharpe", 0.0), m.get("max_drawdown", 0.0) >= bh_tr_dd))
        if not scored:
            continue
        feasible = [s for s in scored if s[2]] or scored
        cid = max(feasible, key=lambda s: s[1])[0]
        oos_rets.append(eqs[cid].pct_change().loc[te_s:te_e])
        bh_rets.append(bh.pct_change().loc[te_s:te_e])
        picks.append(cid)

    if not oos_rets:
        return {"oos_sharpe": float("nan"), "oos_cagr": float("nan"), "oos_maxdd": float("nan"),
                "bh_oos_sharpe": float("nan"), "bh_oos_maxdd": float("nan"), "picks": [],
                "trial_sr": trial_sr, "oos_returns": pd.Series(dtype=float)}

    oos = INIT_CASH * (1 + pd.concat(oos_rets).fillna(0.0)).cumprod()
    bh_oos = INIT_CASH * (1 + pd.concat(bh_rets).fillna(0.0)).cumprod()
    return {
        "oos_sharpe": metrics.sharpe(oos, p), "oos_cagr": metrics.from_equity(oos, p).get("cagr", float("nan")),
        "oos_maxdd": metrics.max_drawdown(oos), "bh_oos_sharpe": metrics.sharpe(bh_oos, p),
        "bh_oos_maxdd": metrics.max_drawdown(bh_oos), "picks": picks, "trial_sr": trial_sr,
        "oos_returns": pd.concat(oos_rets).fillna(0.0),
    }


def gates(interval: str, mcpt_n: int = 200) -> dict:
    """Run all five gates for a timeframe and return a verdict dict."""
    p = ppy(interval)
    wf = walk_forward(interval)
    dsr = deflated_sharpe(wf["oos_returns"], wf["trial_sr"], wf["oos_sharpe"], p)
    cost3 = metrics.sharpe(equity_for(interval, {"risk_pct_per_trade": HEADLINE_RISK}, cost_mult=3.0), p)
    bh_sharpe = metrics.sharpe(benchmark(interval), p)
    perm = mcpt(interval, {"risk_pct_per_trade": HEADLINE_RISK}, mcpt_n) if mcpt_n else {"p_value": float("nan")}

    checks = {
        "wf_beats_bh": bool(wf["oos_sharpe"] > wf["bh_oos_sharpe"]),
        "oos_dd_le_bh": bool(wf["oos_maxdd"] >= wf["bh_oos_maxdd"]),
        "dsr_gt_0p95": bool(dsr > 0.95),
        "cost3_beats_bh": bool(cost3 > bh_sharpe),
        "mcpt_p_lt_0p05": bool(perm["p_value"] < 0.05),
    }
    return {"interval": interval, "walk_forward": wf, "dsr": dsr, "cost3_sharpe": cost3,
            "bh_sharpe": bh_sharpe, "mcpt": perm, "checks": checks,
            "trial_count": len(wf["trial_sr"]),
            "n_pass": sum(checks.values()), "all_pass": all(checks.values())}
