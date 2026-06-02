# Cross-Asset Research

Research branch artifact for testing whether the Leveraged Gold Trend rules have room for improvement and whether they port to other local assets.

## Book-Derived Guardrails

- Evidence-Based Technical Analysis / Aronson: programmable rules only; compare against a nonpredictive benchmark and include data-mining risk.
- Pardo and Masters: use walk-forward thinking, robust regions, costs, and avoid broad post-hoc parameter searches.
- Carver: position sizing should be volatility/risk based, trades should have inertia to reduce costs, and single-instrument Sharpe above 1 deserves skepticism.
- Vince/Kelly literature: leverage is a risk decision; lower-risk variants matter even when CAGR falls.

## Findings

- Tested 19 assets across 9 predeclared variants.
- Headline rules passed the stricter portability screen on 1 assets: XAUUSD.
- Non-headline variants improved headline Sharpe by >0.05 on 16 assets.
- Most common best variants: no_short (7), lower_risk_3pct (4), overlay_ema300_plain (3).
- Skipped 1 configured assets with missing local files.
- The results are cross-asset evidence only; they are not a promotion of any new default without a fuller walk-forward/permutation battery per asset.

## Headline Strategy By Asset

| Asset | TF | CAGR | Sharpe | MaxDD | B&H Sharpe | Cost3 Sharpe | Trades | OOS Sharpe | Verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| ETH-USD | 1d | 12.71% | 0.65 | -28.79% | 0.68 | 0.62 | 42 | 0.36 | asset-specific/weak |
| TLT | 1d | 3.24% | 0.36 | -29.45% | 0.25 | 0.33 | 63 | 0.10 | asset-specific/weak |
| TMF | 1d | 1.39% | 0.17 | -48.76% | 0.15 | 0.15 | 73 | 0.33 | asset-specific/weak |
| DBC | 1d | 1.31% | 0.18 | -45.56% | 0.13 | 0.15 | 105 | 0.16 | asset-specific/weak |
| USO | 1d | -0.33% | 0.03 | -55.09% | 0.02 | 0.01 | 76 | -0.26 | asset-specific/weak |
| IWM | 1d | 3.67% | 0.39 | -19.21% | 0.59 | 0.37 | 55 | 0.69 | asset-specific/weak |
| QQQ | 1d | 7.57% | 0.68 | -19.79% | 0.97 | 0.67 | 39 | 0.72 | asset-specific/weak |
| SPY | 1d | 5.27% | 0.51 | -27.45% | 0.87 | 0.49 | 47 | 0.50 | asset-specific/weak |
| TQQQ | 1d | 12.97% | 0.69 | -32.98% | 0.91 | 0.68 | 44 | 0.63 | asset-specific/weak |
| UPRO | 1d | 9.80% | 0.62 | -37.16% | 0.77 | 0.61 | 56 | 0.64 | asset-specific/weak |
| GLD | 1d | 5.96% | 0.57 | -28.61% | 0.58 | 0.54 | 70 | 1.01 | asset-specific/weak |
| UGL | 1d | 3.87% | 0.36 | -43.97% | 0.56 | 0.33 | 90 | 0.69 | asset-specific/weak |
| AUDUSD | 4h | 0.65% | 0.12 | -56.44% | 0.11 | 0.05 | 288 | -0.23 | asset-specific/weak |
| EURUSD | 4h | 4.33% | 0.37 | -54.83% | 0.14 | 0.30 | 161 | -0.28 | asset-specific/weak |
| GBPUSD | 4h | 0.20% | 0.09 | -67.12% | -0.05 | 0.02 | 269 | 0.05 | asset-specific/weak |
| USDJPY | 4h | 3.11% | 0.28 | -44.19% | 0.17 | 0.21 | 239 | 0.40 | asset-specific/weak |
| XAUUSD | 4h | 19.40% | 1.03 | -24.69% | 0.76 | 1.00 | 158 | 1.17 | portable |
| SPXUSD | 4h | 4.65% | 0.34 | -44.43% | 0.77 | 0.27 | 89 | 0.25 | asset-specific/weak |
| XAGUSD | 4h | 5.71% | 0.37 | -57.81% | 0.38 | 0.34 | 236 | 0.02 | asset-specific/weak |

## Best Variant Per Asset

| Asset | TF | Best variant | CAGR | Sharpe | MaxDD | B&H Sharpe | OOS Sharpe | Params |
|---|---:|---|---:|---:|---:|---:|---:|---|
| ETH-USD | 1d | small_overlay_025 | 11.29% | 0.81 | -16.05% | 0.68 | 0.57 | `{"bull_overlay": 0.25}` |
| TLT | 1d | faster_40_80 | 4.26% | 0.46 | -28.32% | 0.25 | 0.26 | `{"long_entry_days": 40, "long_exit_days": 15, "short_entry_days": 80, "short_exit_days": 40}` |
| TMF | 1d | overlay_ema300_plain | 3.00% | 0.28 | -42.02% | 0.15 | 0.43 | `{"bull_overlay_ma_type": "ema", "bull_overlay_vol_mult": false}` |
| DBC | 1d | pure_trend | 4.18% | 0.42 | -33.27% | 0.13 | 0.35 | `{"bull_overlay": 0.0, "rerisk": false}` |
| USO | 1d | pure_trend | 5.90% | 0.50 | -23.80% | 0.02 | 0.54 | `{"bull_overlay": 0.0, "rerisk": false}` |
| IWM | 1d | lower_risk_3pct | 3.36% | 0.44 | -15.41% | 0.59 | 0.70 | `{"risk_pct_per_trade": 0.03}` |
| QQQ | 1d | no_short | 9.95% | 0.90 | -15.11% | 0.97 | 1.04 | `{"allow_short": false}` |
| SPY | 1d | no_short | 7.86% | 0.76 | -21.18% | 0.87 | 0.75 | `{"allow_short": false}` |
| TQQQ | 1d | overlay_ema300_plain | 12.93% | 0.74 | -31.68% | 0.91 | 0.68 | `{"bull_overlay_ma_type": "ema", "bull_overlay_vol_mult": false}` |
| UPRO | 1d | no_short | 11.34% | 0.70 | -31.34% | 0.77 | 0.65 | `{"allow_short": false}` |
| GLD | 1d | no_short | 6.26% | 0.67 | -27.44% | 0.58 | 1.23 | `{"allow_short": false}` |
| UGL | 1d | no_short | 4.88% | 0.46 | -38.92% | 0.56 | 0.92 | `{"allow_short": false}` |
| AUDUSD | 4h | overlay_ema300_plain | 1.07% | 0.15 | -55.72% | 0.11 | -0.22 | `{"bull_overlay_ma_type": "ema", "bull_overlay_vol_mult": false}` |
| EURUSD | 4h | lower_risk_3pct | 3.74% | 0.42 | -43.43% | 0.14 | -0.26 | `{"risk_pct_per_trade": 0.03}` |
| GBPUSD | 4h | lower_risk_3pct | 1.38% | 0.18 | -46.60% | -0.05 | 0.14 | `{"risk_pct_per_trade": 0.03}` |
| USDJPY | 4h | no_short | 4.84% | 0.49 | -37.96% | 0.17 | 0.93 | `{"allow_short": false}` |
| XAUUSD | 4h | no_short | 18.89% | 1.07 | -23.16% | 0.76 | 1.31 | `{"allow_short": false}` |
| SPXUSD | 4h | lower_risk_3pct | 4.63% | 0.42 | -30.77% | 0.77 | 0.34 | `{"risk_pct_per_trade": 0.03}` |
| XAGUSD | 4h | faster_40_80 | 7.27% | 0.43 | -50.50% | 0.38 | 0.01 | `{"long_entry_days": 40, "long_exit_days": 15, "short_entry_days": 80, "short_exit_days": 40}` |

## Skipped Assets

- BTC-USD 1d: no cache parquet for BTC-USD

## Interpretation

- If gold remains among the few assets clearing the portable screen, the current strategy should stay framed as gold-specific rather than a universal trend engine.
- If a simpler variant such as `pure_trend`, `lower_risk_3pct`, or `small_overlay_025` wins across several unrelated assets, that is the next candidate for a proper walk-forward and permutation validation.
- Leveraged ETF results need extra caution: those products already embed leverage, financing and path decay, so external strategy leverage can compound tail risk.
