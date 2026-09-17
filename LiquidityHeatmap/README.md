# Liquidity Heatmaps

Price x time liquidity heatmaps for **Futures, Stocks, Crypto and Forex**.

The same analytics are implemented twice, deliberately:

| File | Runs where | Purpose |
| --- | --- | --- |
| `liquidity_heatmap.py` | Python 3.12 (stdlib only) | Research and backtests: reads the repo's standard OHLCV CSV, prints a text report, writes JSON |
| `MGE_LiquidityHeatmap.cs` | NinjaTrader 8 (NinjaScript) | Live chart overlay: heat field plus liquidity levels on any instrument |
| `test_liquidity_heatmap.py` | Python 3.12 | 112 checks over the engine, run directly |
| `liquidity-heatmap.html` | Browser (planned) | Multi-asset planning screen on GitHub Pages |

## What it measures

Everything is derived from standard OHLCV bars - **no Order Flow+, no Level 2, no
premium licence required**.

| Layer | What it shows |
| --- | --- |
| Traded volume | Volume-at-price (how much business each price did) |
| Resting liquidity | Volume that wicked past the bar body and was rejected - where stops hide |
| Delta pressure | Buy vs sell pressure per price bin (bar-direction proxy) |
| Liquidation bands | High-volume anchors projected onto a leverage ladder, weighted by how recently price traded there |

Levels drawn from the same model:

* **Liquidity pools** - swing highs/lows clustered into equal highs / equal lows, scored by touches, sweep count and recency
* **Sweeps** - a level is taken and price closes back through it (a grab, not a break)
* **Round number handles** - major and minor handles derived from the price magnitude (NQ 100/50, AAPL 1.00/0.50, EURUSD 0.0100/0.0050, BTC 100/50)
* **HVN magnets and LVN voids** - high-volume nodes pull price, low-volume voids let it travel
* **Session levels** - prior day high/low/close, opening range, week high/low, session VWAP

## NinjaTrader 8 indicator

### Install

1. Copy `MGE_LiquidityHeatmap.cs` to
   `Documents\NinjaTrader 8\bin\Custom\Indicators\MGE_QUANT_INDICATORS\`
2. In NinjaTrader 8 press **F5** in the NinjaScript Editor (or use *Tools -> Compile*).
3. Add **Liquidity Heatmap** to any chart. Works on futures, stocks, crypto and forex
   as long as NT8 can chart the instrument.

No Order Flow+ subscription is needed. The indicator uses only standard bar data plus
custom SharpDX rendering, which is available on a free licence.

### Settings

| Group | Setting | Default | Notes |
| --- | --- | --- | --- |
| Heatmap | Layer | RestingLiquidity | TradedVolume, RestingLiquidity, DeltaPressure, LiquidationBands |
| Heatmap | Heat opacity | 45 | Lower it if you want the candles more visible |
| Engine | Lookback bars | 300 | Bars used to build the picture |
| Engine | Price bins | 80 | Price rows in the field (12-400) |
| Engine | Pivot strength | 3 | Bars either side of a swing high/low |
| Engine | Pool tolerance ticks | 0 | 0 = auto (10% of ATR) for equal highs/lows |
| Engine | Liquidation leverages | 10,20,50,100 | Ladder used for the estimated bands |
| Engine | Refresh every N bars | 1 | Rebuild cost is small; raise it on slow machines |
| Levels | Show pools / Max pools shown | on / 6 | Strongest pools get a line and a label |
| Levels | Show sweeps / Max sweep markers | on / 25 | Diamonds at the level that was grabbed |
| Levels | Show round numbers | off | Turn on for forex and index futures |
| Levels | Show session levels | on | Enables PDH/PDL, opening range, VWAP and week high/low names; missing prior-day levels are omitted |
| Levels | Show level tags | on | Names and prices with short lines ending at the latest completed candle |
| Levels | Show live arrows | on | Optional level pointers that move with each completed candle; not entry signals |
| Levels | Show voids | off | Largest liquidity void - see note above |
| Display | Show summary | on | Compact text panel (bias, nearest pool above/below, HVN/void, PDH-PDL+VWAP), pinned to the chart's top-right corner |
| Display | Show liquidity ladder | on | Volume-profile style histogram in the right margin |
| Display | Ladder metric | RestingLiquidity | RestingLiquidity, TradedVolume or DeltaPressure |
| Display | Ladder width | 18 | Strip width, % of panel width (5-45) |
| Display | Ladder opacity | 70 | Ladder bar opacity (20-100) |

### How it renders

The heat field is drawn per frame with Direct2D `FillRectangle` cells (one cell per
bar x price bin, sampled to at most ~5000 cells), so it compiles with the default
NinjaScript reference set - no `SharpDX.DXGI` reference needed. Levels, sweeps and
the summary use NinjaTrader's `Draw` objects with stable tags, so they update in place
instead of piling up on the chart.

The **liquidity ladder** (right margin histogram) is drawn per frame with Direct2D
primitives: the strip is dimmed first so the ladder never fights the heat field or the
price axis, then one bar is drawn per price bin from the same `Profile` the heatmap
uses. The strongest bin of the chosen metric is highlighted with a POC line.
The optional POC name uses NinjaTrader `Draw.Text`, not DirectWrite.
With RestingLiquidity or DeltaPressure selected, this is the selected metric's peak,
not a conventional traded-volume POC; select TradedVolume for that estimate.
The `DeltaPressure` metric diverges from a centre line - buy side right, sell side left.

### Moving level names and pointers

Enable **Show level tags**, **Show live arrows** (optional), and **Show session levels**
in the indicator settings. Existing chart templates may retain the old disabled settings.
Labels include POC, the strongest HVN, the largest LVN/void center, PDH/PDL,
ORH/ORL, VWAP, WH/WL and up to six swept pool levels when available.
Names sit three bars left of the latest completed candle, with short horizontal
connectors at the level price. Optional arrows point toward the levels at that candle's
horizontal position; they do not identify the candle that originally formed a level.
Stable tags replace previous labels and remove unused connectors rather than leaving a trail.

Updates use **Calculate = OnBarClose**. Keep **Refresh every N bars = 1** for prices
that recalculate every completed bar. Larger values still move the labels each bar but
retain the previous model's prices between rebuilds. Dense levels can still overlap.
Session calculations use calendar-date buckets within the lookback, not exchange
trading-session boundaries; load enough history for prior-day levels. These remain
OHLCV-based estimates, including the volume profile and VWAP.

## NQ/MNQ five-minute NY sweep research baseline

`ny_sweep_backtest.py` is a separate, fixed-rule research simulator, not a live
NinjaTrader strategy or a backtest of the entire heatmap. It uses five-minute
setup candles and one-minute execution bars. No orders are sent.

### Frozen baseline rules

- Timezone: `America/New_York`, including daylight saving changes.
- Current coverage policy (v2): require all 150 minute-close bars from 09:31
  through 12:00 for morning execution. Afternoon availability does not determine
  today's trades. PDH/PDL require all 390 bars from 09:31 through 16:00 in the
  prior observed cash session; incomplete sessions clear that reference.
  No exchange holiday calendar or entirely absent-session detection is used.
  The original baseline used full-session coverage for execution as well.
- Levels: previous retained cash-session high/low (PDH/PDL), plus the first
  15-minute opening range (ORH/ORL), available at 09:45.
- Setup candles close from 09:45 through 11:25. A long sweeps a low level by
  at least two ticks and closes strictly above it; a short is the reverse.
  Skip candles sweeping both sides. Prior-day levels take precedence.
- Entry: stop trigger one tick beyond the setup candle's high/low, active only
  on subsequent minute bars. Expires after ten minutes; no entries after 11:30.
  A subsequent five-minute close back across the level cancels a pending setup.
- Protective stop: two ticks beyond the sweep extreme. Target: 2R measured from
  the simulated entry including entry slippage. One contract, one position,
  at most two entries per day; close remaining positions at noon.
- Conservative fills: adverse slippage on entry, stop and noon exits; gap-aware
  entry/stop prices. Stop wins if both stop and target trade in a minute. No
  target profit is credited on the entry minute because ordering is unknown.
- No HVN/LVN, VWAP, trend filters, account sizing, daily-loss limit or optimization
  has been added. These rules are a testable starting hypothesis, not signals
  already enabled in the chart indicator.

### Reproduce and test (PowerShell)

```powershell
python 'F:\Trading Software\MGEQuant\LiquidityHeatmap\test_ny_sweep_backtest.py'
python 'F:\Trading Software\MGEQuant\LiquidityHeatmap\ny_sweep_backtest.py' --csv 'F:\Trading Software\backtest_lab\NQ_BackAdjusted\NQ_Continuous_Adjusted.csv' --out 'F:\Trading Software\MGEQuant\LiquidityHeatmap\research_results\nq_coverage_v2' --symbol NQ --commission 5 --slippage-ticks 1
```

The standalone tests cover 28 synthetic checks, including afternoon-deletion
invariance, missing morning minutes, and prior-day reference handling. Use a new
output folder for each experiment: the CLI overwrites files in the selected
folder. Preserve `research_results/nq_baseline` as the original full-session run.
Outputs are `summary.json` and
`trades.csv` in the selected output folder. Commission is round-trip dollars per
contract; slippage is ticks per market/stop fill. These are assumptions, not a
verified broker fee schedule. `--symbol MNQ` changes point value to $2 versus
$20 for NQ; running it against NQ data is only a cost-scaling proxy, not an MNQ
execution validation.

### Initial full-dataset result (unoptimized, provisional)

Input coverage: **2019-12-09 through 2026-09-09**, with **1,654 complete sessions**
and **88 incomplete sessions skipped**. One NQ contract; $5 round-trip commission;
one tick adverse slippage per market/stop fill.

| Metric | Result |
| --- | ---: |
| Closed trades | 1,918 |
| Win rate after costs | 37.28% |
| Net P&L | -$48,890 |
| Average net per trade | -$25.49 |
| Profit factor | 0.9522 |
| Closed-trade maximum drawdown | $79,025 |

**This baseline does not establish a profitable edge and is not ready for live
trading.** The profitable one-session smoke test was only an execution check.
Drawdown above uses closed trades, not intratrade equity, margin or account risk.

Timestamp labels are assumed to be UTC minute **closes**, still unverified with
the vendor. Full-session completeness selection uses information from after the
trading window and can bias the sample. Back-adjusted continuous futures also
require roll/price-adjustment validation; one-minute OHLC cannot establish fill
ordering, queue position or actual slippage. This is not out-of-sample validation.

### Corrected coverage run (v2, unoptimized, provisional)

Saved separately in `research_results/nq_coverage_v2`; the original baseline is
unchanged. Entry, exit, sizing and cost rules are unchanged. Only execution
coverage was separated from prior-day reference coverage.

| Metric | Original full-session filter | Morning coverage v2 |
| --- | ---: | ---: |
| Eligible execution sessions | 1,654 | 1,725 |
| Skipped observed sessions | 88 | 17 |
| Closed trades | 1,918 | 1,992 |
| Win rate after costs | 37.28% | 36.95% |
| Net P&L | -$48,890 | -$60,045 |
| Average net per trade | -$25.49 | -$30.14 |
| Profit factor | 0.9522 | 0.9426 |
| Closed-trade maximum drawdown | $79,025 | $88,770 |

The corrected run includes 74 more trades and has $11,155 lower net P&L.
Fixing the coverage defect does not establish an edge: **this baseline remains
unprofitable under the tested assumptions**. This is a software correction,
not a strategy optimization or independent validation.

Verification: all 28 synthetic checks passed. The saved CSV agrees with its
summary on count, wins, net P&L, profit factor and closed-trade drawdown. Trades
respect the two-entry daily limit and entry-after-setup ordering. Identical
synthetic mornings produce identical trades with or without afternoon bars.

Residual limitations: requiring a complete morning still selects on data
availability through noon; entirely absent sessions and exchange holidays are
not detected. PDH/PDL refer to the prior observed complete cash session, which
may not be the actual preceding trading session. OHLC execution uncertainty,
continuous-contract assumptions and lack of out-of-sample validation remain.
See `research_results/nq_baseline/DATA_AUDIT.md` for the data-audit evidence and
`research_results/nq_baseline/SESSION_SELECTION_REPRO.md` for the original defect.

Next: audit representative corrected-run trades against charts, then write a
fixed research/validation plan before adding filters. Previously inspected
historical data cannot be relabeled as an untouched holdout. No live strategy
or NinjaTrader indicator changes are part of this correction.

Next: confirm timestamp and contract-roll conventions, audit individual trades
against charts, improve session/data-quality handling, and predefine a separate
validation period before changing the rules. Do not tune repeatedly on this
entire dataset and describe the result as independent validation.

## Python engine

```bash
# text report for any asset class, no data file needed
python liquidity_heatmap.py --demo --asset futures --symbol NQ

# your own bars (timestamp,open,high,low,close,volume - same format as mge_csc_ab_bt.py)
python liquidity_heatmap.py --csv bars.csv --asset crypto --symbol BTCUSD --json out.json

# include the price x time matrices
python liquidity_heatmap.py --csv bars.csv --asset forex --bins 120 --include-matrix --json out.json
```

Options: `--bins`, `--pivot-k`, `--lookback`, `--matrix-bars`, `--void-threshold`,
`--top`, `--demo`, `--demo-bars`, `--json`, `--include-matrix`.

Checks:

```bash
python test_liquidity_heatmap.py
```

## How to trade it (MGE method)

> Educational only, not financial advice. `MGE_LiquidityHeatmap` is a **map of
> where liquidity hides**, not a buy/sell signal.

### What you are actually looking at

All 4 layers come from normal OHLCV bars:

| Layer | Question it answers | How to read it |
| --- | --- | --- |
| **RestingLiquidity (default)** | Where are stops resting? | Bright = wicks rejected there. Price is attracted to it. |
| **TradedVolume** | Where did business happen? | Bright = accepted price / HVN magnet. Dim = rejected / LVN void. |
| **DeltaPressure** | Who was pressing? | Warm = close>open bars dominated. Cool = close<open dominated. Bar-direction proxy, **not** real bid/ask delta. |
| **LiquidationBands** | Where would leverage hurt? | Estimated clusters: high-volume anchor x `anchor x (1 +/- 1/leverage)`. Model, not exchange data. |

Levels drawn on top:

* **Pools:** equal highs / equal lows. `buy 24100 x3` = 3 touches above = sell-side stops below / buy-stops above. More touches + sweeps = stronger.
* **Sweeps:** diamond = level taken **and reclaimed**. That is a grab. A level blown straight through is a break, not a sweep.
* **Ladder (right side):** volume-profile of the same model. Longest bar = POC. Dimmed strip so it does not fight candles.
* **HVN / LVN:** HVN pulls and stalls, LVN lets price travel fast.
* **Session:** PDH/PDL, opening range, VWAP, week high/low.
* **Summary text:** bias, nearest pool above/below, magnets/voids. Orientation, not entry.

Core principle: **bright resting liquidity attracts price, then price reacts at how
it arrives there.** Trade the reaction, not the color.

### The 3 tradable ideas

#### A. Sweep + reclaim - best MGE setup

Liquidity raid, then failure to hold beyond the pool.

1. Bright resting pool above/below + pool label `x2/x3` + prior sweep count.
2. Bar wicks through pool, **closes back inside**.
3. Next bar does not re-take the extreme.
4. Entry on reclaim, stop beyond sweep extreme + tolerance, target: opposite edge of void / HVN / VWAP / prior balance.

Avoid if: it closes and holds beyond + retests and holds. That is acceptance, not a grab.

#### B. Pool raid continuation

Used in trends / open drive.

1. Price consolidates under a bright pool.
2. Sweeps it, holds beyond, retests and holds.
3. That is fuel. Continuation toward next pool / liquidation band / round handle.

Do not fade the first strong acceptance.

#### C. HVN magnet -> LVN transit

1. Price stuck in dim void -> moves fast to bright HVN / ladder POC.
2. At HVN: expect stall/chop. Take partials, not new full risk.
3. Through HVN into next void: moves fast again. Do not chase the middle of a void.

### Practical workflow on the chart

1. **Bias (30 sec):** Summary says `buy-side liquidity above` + price under PDH + ladder POC above = longs have room, shorts are crowded below. Opposite = mirror.
2. **Mark 2 levels only:** nearest pool above, nearest pool below. Ignore the other lines.
3. **Pick one layer:** RestingLiquidity for stops/raids, TradedVolume for magnets/targets, DeltaPressure only to see if pressing into a level is one-sided, LiquidationBands only for crypto/futures leverage extensions.
4. **Wait at the level:** No sweep/reclaim or acceptance = no trade.
5. **Manage by structure:** Stop beyond the grab extreme, not inside the heat. Target next HVN, opposite pool, VWAP, OR high/low. In a void, use smaller size - it travels.

### Per asset notes

* **Futures (e.g. NQ/ES):** Turn on Round Numbers + Session Levels. 100/50 handles matter. Best on 1-5m for sweeps, 15m+ for pools. Opening range + PDH/PDL sweep is the A+ pattern.
* **Stocks:** Volume profile is real traded volume. Overnight gap + premarket HVN = magnet. Lower `LookbackBars` to ~150 on opens because range expands.
* **Crypto (e.g. BTC 24/7):** Session levels mean little. Use LiquidationBands layer + 50/100 handles. Weekends = thin voids, expect overshoot of pools.
* **Forex:** Tick volume is broker volume, not central. Trust pools/sweeps/round numbers (`1.1000/1.1050`) more than brightness. Raise `PriceBins` to 100-120 because ranges are small.

Recommended starting points:

* Scalp: Lookback 200-300, Bins 80, Pivot 3, Heat opacity 35-45 so candles show.
* Swing/day: Lookback 300-500, Bins 80-100, Pivot 4-5, MaxPools 4-6.

### What NOT to do

* Do not buy bright color alone. Bright = attraction, not direction.
* Do not use DeltaPressure as CVD. It just says green-bodied bars traded there.
* Do not treat liquidation bands as real liquidations.
* Do not fade strong acceptance back into a pool. Sweeps need reclaim.
* Do not stack all levels on. Pools + sweeps + summary + ladder is enough to start. If you show pools + rounds + session + voids + sweeps + ladder + heat at 80 opacity, you will see nothing.

## Can this logic become a trade signal?

**Yes, but the current arrows are level pointers, not buy/sell signals.**
In `MGE_LiquidityHeatmap`, an arrow points toward a calculated level above or below
price. Its direction does **not** mean "buy" or "sell." Moving with each completed
candle simply keeps the level visible. The ideas below are proposed rules to test,
not an implemented signal engine or evidence of a profitable strategy.

### From levels to potential setups

Use the heatmap for **location**, then require price confirmation:

| Setup | Potential long trigger | Potential short trigger |
| --- | --- | --- |
| Sweep and reclaim | Price trades below a previously identified low/pool, then closes back above it | Price trades above a previously identified high/pool, then closes back below it |
| Breakout and retest | A close above a level, followed by a retest that holds above | A close below a level, followed by a retest that holds below |
| VWAP confirmation | Reclaim of VWAP alongside a bullish setup | Rejection of VWAP alongside a bearish setup |

**Example: sweep, reclaim, then confirmation (not an existing indicator signal)**

1. A low-side pool is identified **before** the setup candle.
2. Price breaks below it and closes back above.
3. A later candle breaks the reclaim candle's high.
4. This provides a potential long entry, with invalidation below the sweep low.
5. Consider the next opposing level as a target only if the available reward
   justifies the risk, including trading costs. Stops do not guarantee a fill at
   the specified price.

### Requirements before automation

* **Use levels known at the time.** Do not test historical entries against today's
  recalculated heatmap. Store the level and its availability time when evaluating
  a setup; retrospective sweep marks are not proof of a causal signal.
* **Respect pivot confirmation.** With pivot strength 3, a swing needs three
  subsequent bars before it is known.
* **Separate signals from moving pointers.** Entry markers should remain on their
  trigger candle and must not disappear merely because the profile changes.
* **Validate session levels.** Current day calculations use calendar dates within
  the lookback, not exchange-session boundaries. This matters for overnight futures.
* **Make the rules explicit.** Define confirmation timing, retest tolerance,
  expiration, entry execution, stop placement and exits before testing.
* **Backtest with commissions and slippage**, then validate out of sample and in
  playback/simulation. Check performance across different market conditions.

The indicator estimates liquidity from **OHLCV bars**; it does not observe resting
orders or actual bid/ask delta. Neither the level colors nor the current arrows
establish a trading edge.

**Suggested starting point:** one explicit **sweep -> reclaim -> confirmation**
rule with fixed historical signal markers and alerts. Those signal markers and
alerts would be a separate implementation. No profitable edge has been established.
This guidance is educational, not a recommendation to enter a trade.

## Honest limitations

* **No real order book.** Depth, resting size and liquidation clusters are *estimates*
  built from bars. Inside NinjaTrader 8 you can upgrade this with Order Flow+ Volumetric
  bars (real bid/ask volume) or market depth, but neither is required, and neither is
  available retroactively - depth heat only accumulates forward from when you start it.
* **Liquidation bands are a leverage model**, not exchange data: anchors are the
  highest-volume nodes, projected to `anchor x (1 - 1/leverage)` and
  `anchor x (1 + 1/leverage)`. Treat them as "where leveraged positions are likely to
  get uncomfortable", not as fact.
* **Delta is a bar-direction proxy.** Without bid/ask data, a bar closing above its open
  counts as buy pressure. It is good enough for locating absorption, but it is not
  cumulative delta.
* **"Day" means the calendar day of the bar timestamp** on the chart, so instruments with
  an overnight session group by calendar date rather than exchange trading day.
* **A sweep is a reclaim** (level taken, then closed back through). A level that gets
  blown through does not count - that is a break, not a grab.
* The two implementations (Python and NinjaScript) mirror each other's maths; if you
  change one, change the other.

## Verification

* `liquidity_heatmap.py` - `python -m py_compile` clean; `test_liquidity_heatmap.py`
  passes all 112 checks across all four asset classes.
* `MGE_LiquidityHeatmap.cs` - compiled with the Roslyn compiler against the real
  NinjaTrader assemblies (`NinjaTrader.Core.dll`, `NinjaTrader.Custom.dll`,
  `NinjaTrader.Gui.dll`, `SharpDX*.dll`) from
  `Documents\NinjaTrader 8\bin\Custom\bin\Release\`: zero errors, zero warnings.
  NinjaTrader's own compile (F5) is still the final word.

## Still to come

* `liquidity-heatmap.html` - the browser version of the same heatmap with a paste/upload
  CSV loader and a canvas render, for planning outside NinjaTrader.