# Leveraged Gold Trend

A trend-following strategy on **gold (XAUUSD)** with **governed leverage** — and a study of a
question every systematic trader runs into: *if I take the **same** strategy and the **same** asset
and only change the **timeframe**, what happens?* The short answer, with evidence across nine
timeframes from 1-minute to monthly: **fast timeframes are destroyed by trading costs, slow ones by
having too few trades, and there is a narrow sweet spot in the middle.** For this strategy on gold,
that sweet spot is **4-hour bars**.

> ⚠️ **Not financial advice. Educational/research only.** This is a backtest. Leverage can wipe out
> your account (and more). Past simulated performance does not predict the future. See
> [Limitations & risks](#limitations--risks) and [LICENSE](LICENSE).

---

## TL;DR — the headline (4h)

Same rules, 4-hour gold bars, 2004–2026, realistic costs:

| Metric | Strategy (4h) | Buy & hold gold |
|---|---|---|
| CAGR | **16.1%** | 12.5% |
| Sharpe | **0.88** | 0.76 |
| Sortino | 0.69 | — |
| Calmar | **0.61** | 0.28 |
| Max drawdown | **−26%** | −45% |
| Avg leverage | 2.0× (cap 3×) | 1× |
| Time in market | 28% | 100% |
| Trades (21 yrs) | 112 | — |

It beats simply holding gold on **return, risk-adjusted return, and drawdown** — and it does so
while being out of the market 72% of the time and structurally **long *and* short**, so it is
weakly correlated to gold itself.

![Equity vs gold](results/plots/equity_4h_vs_gold.png)

It passed a full anti-overfitting battery (walk-forward, deflated Sharpe, cost-stress, permutation
test — see [Methodology](#methodology--why-we-believe-it)). **It is the only timeframe that did.**

---

## Why gold?

Gold (the XAUUSD spot pair, i.e. the price of one ounce in US dollars) is an unusually good asset
for a trend strategy like this:

- **It's a commodity with persistent macro trends.** Gold is a monetary/safe-haven and
  inflation-hedge asset. Its price is driven by real interest rates, the dollar, and risk sentiment
  — slow-moving macro forces that produce **long, sustained trends** (2004–2011 up, 2011–2015 down,
  2019–2026 up) interspersed with multi-year ranges. Trend-following lives on exactly that.
- **It's deeply liquid and trades ~24 hours a day.** XAUUSD is one of the most heavily traded
  instruments in the world, with **tight spreads** at major brokers and continuous ~24×5 trading.
  Tight cost + deep liquidity is what makes a leveraged, stop-based system *plausible* (and it's why
  this exact study would look very different on an illiquid asset).
- **It's decorrelated from equities.** Gold often rises when stocks fall, so a gold strategy is a
  useful diversifier rather than one more bet on the S&P 500.
- **Leverage is cheap and native.** Via spot CFDs, spread bets, or futures (GC / micro MGC), you can
  run gold at 2–3× notional without huge capital — which is precisely why retail traders are drawn
  to it, and precisely why disciplined position sizing matters so much (see below).

These properties — trends + liquidity + cheap leverage — are why gold is such a popular vehicle for
exactly this kind of leveraged trend trade, and why we use it as the laboratory for the timeframe
question.

---

## How the strategy works

Three independent ideas, kept deliberately simple (few parameters → less room to overfit).

### 1. Entry — Donchian breakout (ride the trend)

At each bar's close, enter in the direction of a breakout of the recent range:

- **Go long** when the close makes a new **55-day** high.
- **Go short** when the close makes a new **100-day** low.

Breakouts are the classic, robust trend entry: you only get long after strength has been confirmed,
and you're flat in the chop.

### 2. Exit — ATR "Chandelier" trailing stop (let winners run)

There is **no take-profit**. Instead the position is closed by a trailing stop that ratchets toward
price as the trade moves your way:

- For a long: `stop = (highest close since entry) − k × ATR`, with **k = 5** and a 20-day ATR.
  Exit when price closes below the stop (or below the 20-day low). Symmetric for shorts.

Why no profit target? Trend-following makes its money from a **few very large winners** that pay for
many small losses. A take-profit caps exactly that right tail — it feels good and lowers your win
rate's volatility, but it quietly removes the source of the edge. So we let winners run and only cut
losers. (This is the Clenow / Carver school of trend design.)

### 3. Position sizing — risk-per-trade → *governed, emergent* leverage

This is the heart of the strategy, and the part most retail traders get backwards. **Leverage is not
a "make me more money" dial.** Over-betting a positive-expectation system mathematically drives it
toward ruin (Ralph Vince's leverage-space work; the Kelly literature). So leverage here is an
*output of a risk decision*, not an input:

> Size each trade so that **if the trailing stop is hit, you lose a fixed fraction `r` of equity**.

With a stop `stop_frac` away from entry (as a fraction of price), the position notional that risks
exactly `r` of equity is:

```
notional_fraction = r / stop_frac        # e.g. r = 5%
leverage = min(notional_fraction, CAP)   # hard ceiling, CAP = 3×
```

So a **tight** stop (calm market, low ATR) earns a **larger** position, a **wide** stop earns a
smaller one — and the gross exposure is **never** allowed above a hard cap (3×). Leverage *emerges*
from volatility and is *governed* by the cap. On 4h gold this averages ≈2.0× and only touches 3× in
the calmest regimes.

**The leverage is not free.** Sweeping `r` from 1% → 20% reproduces Vince's growth-then-ruin curve
exactly: CAGR rises until ≈5%, then **Sharpe and Calmar fall while drawdown explodes**. The
risk-adjusted optimum is a *modest* 2–5% per trade (≈1–2× average leverage), not the cap. We ship
`r = 5%` as the "grow faster but still beat buy-&-hold on every axis" setting; `r = 2%` is the more
conservative choice (≈−11% max drawdown).

---

## How to actually follow it

A concrete recipe (this is description, not advice):

- **Instrument:** XAUUSD spot (CFD/spread bet) at a tight-spread broker, or gold futures (GC / micro
  MGC). Pick the cheapest, most liquid one you can access.
- **Timeframe:** 4-hour bars. Gold trades ~24h, so that's ~6 bars/day; you make a decision only at
  each 4h close (~6 checks/day — not a screen-watching system).
- **Each 4h close, do this:**
  1. Update the 55-day high, 100-day low, the 20/50-day exit channels, and the 20-day ATR (in 4h
     bars: 55 days ≈ 330 bars, 20 days ≈ 120 bars).
  2. **If flat:** new 55-day-high close → go long; new 100-day-low close → go short.
  3. **Size it:** stop distance = 5 × ATR. Risk 5% of equity to that stop →
     `units = 0.05 × equity / (5 × ATR × point_value)`, capped so notional ≤ 3 × equity.
  4. **If in a position:** trail the stop (highest-close-since-entry − 5×ATR for longs); exit on a
     stop hit or the opposite channel. No take-profit.
- **Worked example:** equity \$10,000, gold \$2,000, ATR = \$20 → stop distance \$100 (5% of price).
  Risk \$500 → notional \$500 / 0.05 = \$10,000 = **1.0×**. If the market is calmer (ATR \$10), the
  stop is 2.5% → size doubles to **2.0×**; the 3× cap binds only when ATR gets very small.
- **Watch in live trading:** overnight **swap/financing** (charged daily on leveraged positions —
  *not* modelled here, see below) and **slippage** in thin sessions. Both hurt more the faster you
  trade — which is the whole point of the next section.

---

## The timeframe question (the main event)

Here is the same strategy (`r = 5%`, cap 3×), the same asset, run on **all nine timeframes**.
`cost_drag` = CAGR percentage points lost to costs; `cost3 Sharpe` = Sharpe after **3× nominal
cost**; `WF Sharpe` = walk-forward out-of-sample Sharpe (vs buy-&-hold "B&H"); `MCPT p` = permutation
p-value (blank where skipped for runtime); `gates` = how many of the 5 anti-overfit gates pass.

| TF | bars | trades | CAGR | Sharpe | MaxDD | avg lev | cost_drag | cost3 Sharpe | WF Sharpe (B&H) | DSR | MCPT p | gates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|:--|
| 1m | 6.8M | 2151 | 0.4% | 0.09 | −47% | 3.00 | **7.46%** | **−1.71** | 0.40 (0.51) | 0.868 | — | 1/5 |
| 5m | 1.4M | 939 | 6.0% | 0.57 | −33% | 3.00 | 3.37% | 0.02 | 0.62 (0.53) | 0.988 | — | 3/5 |
| 15m | 494k | 547 | 6.7% | 0.52 | −35% | 3.00 | 1.97% | 0.26 | 0.65 (0.54) | 0.988 | — | 3/5 |
| 30m | 249k | 372 | 10.7% | 0.67 | −41% | 2.99 | 1.38% | 0.53 | 0.86 (0.54) | 0.999 | 0.016 | 4/5 |
| 1h | 125k | 243 | 12.8% | 0.71 | −29% | 2.93 | 0.90% | 0.63 | 0.77 (0.54) | 0.996 | 0.010 | 4/5 |
| **4h** | **33k** | **112** | **16.1%** | **0.88** | **−26%** | **2.04** | **0.29%** | **0.86** | **0.80 (0.55)** | **0.998** | **0.007** | **5/5 ✅** |
| 1d | 5.5k | 68 | 5.2% | 0.50 | −33% | 0.81 | 0.06% | 0.49 | 0.28 (0.53) | 0.840 | 0.119 | 1/5 |
| 1w | 1.1k | 65 | 1.9% | 0.44 | −17% | 0.32 | 0.02% | 0.43 | 0.08 (0.54) | 0.588 | 0.154 | 1/5 |
| 1mo | 260 | 55 | 1.2% | 0.56 | −6% | 0.15 | 0.01% | 0.55 | 0.43 (0.52) | 0.949 | 0.030 | 2/5 |

The headline chart, but for **all nine timeframes at once** (each at `r = 5%`, daily-sampled, log
scale). Only **4h** (amber) pulls clearly above buy-&-hold gold (black); the fast timeframes are
dragged flat along the bottom by cost, and the slow ones barely lever up. One strategy, nine speeds —
almost the entire spread between them is a cost-and-sample-size story, which the rest of this section
unpacks.

![Strategy equity for every timeframe vs gold](results/plots/equity_all_timeframes_vs_gold.png)

![Cost decay by timeframe](results/plots/cost_decay_by_timeframe.png)

### How costs "kill" the fast timeframes

Look at the `cost_drag` column climb as the bars get finer: **0.01% at monthly → 0.29% at 4h →
7.46% at 1-minute**. The 1m version loses *seven and a half CAGR points* to costs, and once you
stress costs to a realistic 3× its Sharpe goes **negative (−1.71)** — it is a *losing* system after
fees. Why does turnover (and therefore cost) explode on fast bars even though the lookbacks are the
same number of days? Because the **trailing stop whipsaws**: on 1-minute bars the 5×ATR stop is hit
and re-entered far more often within the *same* trend (2151 trades vs 112 on 4h), and every one of
those round-trips pays the spread. Faster ≠ more edge; faster = **more friction**.

![Trade count by timeframe — two ways to die](results/plots/trades_by_timeframe.png)

This is the whole study in one chart — **two ways to die.** Trade count *explodes* toward fast bars
(2151 at 1m, almost all of it trailing-stop whipsaw *within* the same trend) and *starves* toward
slow ones (55 at monthly). The fast end pays that turnover away in spread; the slow end runs out of
statistical evidence (next subsection). 4h (amber) lands where there are enough trades to mean
something, yet few enough that cost stays a rounding error.

And remember costs here are modelled at a *nominal* tight spread. Real intraday gold spreads in thin
hours are wider, and **overnight financing is not charged at all** — both of which would punish the
fast timeframes even harder. So if anything this *understates* the cost cliff.

### Why the slow timeframes fail too

The other end is more subtle. At weekly/monthly bars cost is negligible (`cost_drag` ≈ 0) — but the
strategy now makes only ~55–65 trades in 21 years, and **a handful of trades carries almost no
statistical evidence.** Their walk-forward Sharpe collapses (1w: 0.08), their deflated Sharpe falls
below the 0.95 bar (1w: 0.59), and the permutation test can't distinguish them from luck. They also
under-use leverage (avg 0.15–0.32×), because over a long bar the ATR stop is wide in percentage
terms, so the risk-per-trade sizing keeps positions small. Daily (1d) sits in a dead zone: too few
trades to beat buy-&-hold (WF Sharpe 0.28) and no longer fast enough to add timing value.

### The sweet spot

**4h is the only timeframe that clears all five gates.** It is fast enough to time gold's trends
finely (16% CAGR, 0.88 Sharpe, deflated Sharpe 0.998, permutation p = 0.007) yet slow enough that
costs are still a rounding error (0.29% drag; survives 3× cost with Sharpe 0.86). 1h and 30m have a
*real* edge too (permutation p ≈ 0.01) but flunk the cost-stress gate. That's the lesson in one
sentence: **the right timeframe is the one where your edge is real *and* your costs are still
negligible — and for leveraged gold trend, that's 4 hours.**

![Risk vs return by timeframe](results/plots/risk_return_by_timeframe.png)

Plotting every timeframe by return (x) against risk-adjusted return (y) — bubble size = number of
trades, colour = anti-overfit gates passed — makes the sweet spot visually obvious: **4h sits alone
in the top-right, dark green (5/5 gates).** The huge orange 1m bubble (most trades, lowest Sharpe, a
single gate) is the cost cliff in one dot, and the small bubbles hugging the buy-&-hold line are the
trade-starved slow timeframes.

![Max drawdown by timeframe](results/plots/maxdd_by_timeframe.png)

Drawdown tells the same story from the risk side: it is worst exactly where the leverage cap binds
hardest (full-sample −47% at 1m, −41% at 30m), while 4h's −26% is among the mildest of the
*leveraged* timeframes. The blue bars are the walk-forward out-of-sample drawdowns — and **every**
timeframe clears the "OOS drawdown ≤ buy-&-hold gold" gate, because that ceiling is a hard constraint
baked into the parameter selection, never a quantity we maximize.

---

## Methodology — why we believe it

Backtests lie if you let them. Every result above is gated by five standard anti-overfitting tests
(run on a 2008–2019 *search* window, then confirmed on an untouched 2020–2025 *holdout*; parameters
are selected only on training data):

1. **Walk-forward analysis** (Pardo) — pick the breakout/risk parameters on each in-sample window,
   apply them to the next out-of-sample window, stitch the OOS pieces. PASS only if OOS Sharpe beats
   buy-&-hold gold.
2. **Drawdown constraint** — OOS max drawdown must be ≤ buy-&-hold gold's. Drawdown is a hard limit,
   never the thing we maximize.
3. **Deflated Sharpe ratio** (López de Prado) — corrects the observed Sharpe for the number of
   configurations tried and for non-normal returns. PASS if > 0.95.
4. **Cost stress** — re-run at 2× and 3× the nominal spread. The edge must survive realistic, even
   pessimistic, costs.
5. **Permutation test / MCPT** (Masters, Aronson) — shuffle the return sequence (destroying trend
   structure), rebuild a synthetic price path, and re-run thousands of times. PASS if the real
   ordering's Sharpe beats the random ones with p < 0.05 — i.e. the edge comes from *trend*, not from
   curve-fitting.

![Anti-overfit gates by timeframe](results/plots/gates_heatmap.png)

Running all five gates across all nine timeframes makes the verdict unambiguous — **only 4h is green
on every gate.** The fast timeframes (1m–15m) fail the cost-stress gate (1m fails most of them); the
slow ones (1d–1mo) fail walk-forward and deflated-Sharpe for lack of trades. MCPT is marked *n/a* on
the three fastest bars, where the permutation test is too expensive to run (the other columns already
condemn them).

We also built three variants and let the backtest pick (rather than arguing from authority):
**(A)** the breakout + trailing-stop system above; **(B)** a continuous volatility-targeted EWMAC
trend with the same leverage cap; **(C)** A plus a moving-average regime filter. **B blew up** — naked
volatility-target leverage on a single asset over-levers in calm regimes and took a −64% drawdown,
the textbook over-betting failure. **C ≈ A** — the regime filter added nothing on gold. So the shipped
strategy is **A**.

---

## Limitations & risks

Read these before taking any of the numbers seriously.

- **Overnight financing/swap is not modelled.** The cost model charges spread + commission on
  turnover but not the daily carry on a held leveraged position. For a system that holds trades for
  days/weeks this **understates real cost** — treat the headline as a mild upper bound. (It does not
  change the *timeframe ranking*; if anything it widens the gap against the fast TFs.)
- **One asset, one (favourable) sample.** 2004–2026 is largely a secular gold bull. Long/short and
  the permutation test mitigate the long bias, but a single asset over a single regime is thin
  evidence. Don't extrapolate to other assets or regimes without re-testing.
- **It's a returns-based simulation, not an order-book backtest.** Fills are modelled at bar
  granularity with a close-based trailing stop and constant-fraction (daily-rebalanced) leverage;
  live execution (gaps, intrabar stop fills, partial fills, slippage spikes) will differ.
- **Drawdown is real.** −26% at `r = 5%` (and the fast/leverage-pinned variants hit −40%+). Leverage
  cuts both ways. Size down (`r = 2%`) if that hurts.
- **No look-ahead, by construction** — signals use only completed bars; exposure decided at a bar's
  close earns the *next* bar's return; rolling stats are shifted. But verify it yourself.

---

## Reproduce it

```bash
pip install -e .                              # numpy, pandas, scipy, pyarrow, matplotlib
pip install kaggle                            # only for the data download
python scripts/download_data.py               # fetch XAUUSD -> data/*.parquet (needs a Kaggle token)

python -m leveraged_gold_trend --interval 4h            # headline metrics
python -m leveraged_gold_trend --interval 4h --validate # + the 5 gates
python -m leveraged_gold_trend --scan                   # the 9-timeframe table -> results/
python -m leveraged_gold_trend --plots                  # regenerate the charts
```

The precomputed evidence is committed under [`results/`](results/) (the 9-timeframe table, the
headline metrics JSON, and all seven charts), so you can read the whole study without downloading
anything or re-running the heavy 1-minute pass (which takes a couple of minutes).

**Data:** Kaggle `novandraanugrah/xauusd-gold-price-historical-data-2004-2024`. Not redistributed
here (the 1-minute file alone is ~100 MB); `download_data.py` fetches it.

---

## References

The strategy and its validation are grounded in the systematic-trading literature:

- Robert Carver — *Leveraged Trading* (2019) and *Systematic Trading* (2015): risk-target position
  sizing; leverage as the central danger of retail trading.
- Andreas Clenow — *Following the Trend* (2023) and *Stocks on the Move* (2015): diversified trend
  following; let winners run, exit by stop/rank not profit target.
- Ralph Vince — *The Leverage Space Trading Model* (2009): over-betting drives positive-expectation
  systems to ruin.
- Van K. Tharp — *Trade Your Way to Financial Freedom* (1998): position sizing and expectancy.
- Robert Pardo — *The Evaluation and Optimization of Trading Strategies* (2008): walk-forward analysis.
- Timothy Masters — *Testing and Tuning Market Trading Systems* (2018); David Aronson —
  *Evidence-Based Technical Analysis* (2007): permutation tests and data-mining bias.
- Marcos López de Prado — *Advances in Financial Machine Learning* (2018): the deflated Sharpe ratio.

---

## License

[MIT](LICENSE). **Not financial advice — educational and research use only. Trading leveraged
products carries a high risk of loss.**
