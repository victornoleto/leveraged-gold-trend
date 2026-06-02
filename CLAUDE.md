# CLAUDE.md — leveraged-gold-trend

Public (MIT) Python package: a **governed-leverage trend-following strategy on gold (XAUUSD)** with a
small volatility-scaled bull overlay, and a study of how the **same** strategy behaves across **9
timeframes (1m→1mo)** — and how trading costs damage the fast ones. Built for sharing (GitHub + a
LinkedIn post). Reimplemented clean and self-contained from a private research strategy ("017") —
**no vectorbt**; the headline equity is returns-based (numpy/pandas/scipy only).

**Read first:** `README.md` (the full report — source of truth) and `results/timeframe_scan.csv` (the
9-timeframe evidence). `docs/linkedin-post.md` is the post (Portuguese).

## The strategy, in one paragraph

Entry: Donchian breakout (new 55-day high → long; new 100-day low → short). Exit: ATR Chandelier
trailing stop (5×ATR, 20-day ATR) — **no take-profit** (let winners run). Sizing: **risk-per-trade**
— notional set so distance-to-stop = `risk_pct` of equity, with a **hard leverage cap** (3×).
Open winners can be re-risked at new favourable closes with 10% inertia. While the core engine is
flat, a 0.5× long overlay is allowed above the 300-day EMA and scaled down/up by relative volatility.
Leverage is _governed risk_, never a "make more money" dial (over-betting → ruin; Vince/Kelly).

## Key results

- **Headline (4h, risk 5%, cap 3×):** CAGR ~19.4%, Sharpe 1.03, MaxDD −25% — beats buy-&-hold gold on
  return, Sharpe **and** drawdown. It clears all 5 anti-overfit gates (walk-forward, deflated Sharpe,
  cost-stress 3×, permutation/MCPT).
- **Timeframe finding (the point of the repo):** fast TFs die from **cost** (1m: 7.90%/yr cost drag,
  Sharpe negative at 3× cost, 2411 entries/activations); slow TFs (1w/1mo) die from **too few events**
  (~37–50 in 21 yrs → no statistical power). **1h and 4h pass all gates; 4h is the headline sweet
  spot** because it has better Sharpe, lower drawdown, lower cost drag and stronger WFA than 1h.

## How to run

Deps already exist in the sibling quant venv — quickest path (data is already in `data/` locally,
gitignored, so reruns work offline):

```bash
.venv/bin/python -m leveraged_gold_trend --interval 4h     # headline
#   --validate  → the 5 gates   ·   --scan → 9-TF table (several min)   ·   --plots → regen charts
```

Clean-room (as a public user would): create a venv, `pip install -e .`, then
`python scripts/download_data.py` (needs a Kaggle token) to fetch XAUUSD into `data/`.

## Invariants — do NOT break

- **Annualization = empirical periods-per-year** (`metrics.empirical_ppy`, bars/calendar-year). Gold
  is ~24h, so equity-session ppy constants would badly understate intraday Sharpe.
- **No look-ahead:** signals use completed bars; exposure decided at `close[t]` earns the `[t,t+1]`
  return; rolling stats shifted.
- **Costs:** fee + slippage (fx preset) on turnover only. **Overnight swap/carry is NOT charged** —
  documented caveat #1; understates cost of multi-day holds, but does not change the timeframe
  ranking. Don't silently "fix" it without saying so.
- **Language:** everything in the repo is **English** (code, comments, README) — the **only**
  exception is `docs/linkedin-post.md` (Portuguese).
- **Data is never committed** (1m parquet ≈ 100 MB; `.gitignore` excludes `data/*.parquet`).
  Precomputed evidence under `results/` **is** committed.
- Shipped strategy is the promoted `rerisk + 0.5x EMA300 bull overlay + volatility multiplier`
  variant. The original pure Donchian/ATR baseline, B (naked vol-target leverage, blew up −64% DD),
  and C (regime filter ≈ baseline) are documented in the README / research scripts.

## Layout

`leveraged_gold_trend/`: `strategy.py` (the state machine), `data.py` (parquet load+resample,
cached), `costs.py`, `metrics.py`, `validate.py` (the 5 gates), `timeframe_scan.py`, `plots.py`,
`__main__.py` (CLI). `scripts/download_data.py` (Kaggle fetch). `results/` (CSV, JSON, 7 PNGs).

## State

Git initialized on `main`; GitHub remote is `victornoleto/leveraged-gold-trend`. Data source: Kaggle
`novandraanugrah/xauusd-gold-price-historical-data-2004-2024`. Author: Victor Noleto. MIT + "not
financial advice" disclaimer.
