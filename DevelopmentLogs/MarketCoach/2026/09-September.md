# September 2026 — Development Log

## September 2 — Kraken VolSqueeze Breakout: first real test, no edge demonstrated

Ran the first proper test of the volatility-squeeze breakout concept across all four
Kraken pairs. Kraken's REST OHLC caps at roughly 7.5 days of 15-minute bars, which is
why every result on file was n=4–6 — a sample where the standard error is about half
an R and nothing is distinguishable from anything. Pulled 52 days per pair from a
second data vendor instead and re-ran.

**Result: no edge.** Pooled across three pairs, 109 trades, gross expectancy −0.05 R
with a 95% CI spanning zero.

The number that settled it: a fixed 2R target breaks even at a 33.33% win rate. The
three pairs came in at 33.3%, 30.0% and 32.6%. On BTC the gross expectancy was
*exactly* zero — twelve winners at +2R against twenty-four losers at −1R. That is what
a coin flip looks like once you draw an R-structure on it. The breakout was producing
geometry, not direction.

Swept 45 parameter combinations. The best one failed its **uncorrected** 95% CI, before
any multiple-comparisons adjustment was applied. So there is nothing here to tune toward,
and tuning is off the table.

**The bots stay running.** They use public endpoints only — no keys, no signing, every
fill logged as simulated — so accumulating real out-of-sample bars costs nothing, and
out-of-sample data is the one thing that can move a result the in-sample sweep cannot.
This remains the Kraken candidate; MarketCoach is the NQ strategy. The distinction being
drawn is between *running a candidate* and *believing it works*, and only the second is
ruled out today.

The bar is set now, in advance, so it cannot be moved later: **a win rate clearing the
33.33% break-even line over 100+ forward trades, at a realistic cost basis.**

That last clause turned out to matter more than expected. The backtest prices at spot
taker rates, which cost 0.90 R per trade against a gross expectancy of −0.05 R — the
strategy would have to win 63% of its trades just to break even. On the exchange's
futures maker schedule the same trades cost 0.04 R. A forward test graded against a cost
model that forecloses its own conclusion is not a forward test, so the venue decision
comes before any more accumulation.

Worth recording that the code was clean. Entries booked at a real traded price, not a
synthetic level; costs correctly applied; the rolling-range contract honoured. An
independent re-implementation driven by a different data vendor reproduced the
published trade counts and win rates exactly. **A null from a good process is a result,
not a failure.**

Two governance findings from the same pass:

- The live bot and the backtest disagreed about whether to keep feeding the indicator
  state while a position was open. The bot did; the backtest did not. A code comment in
  the bot claimed the two matched. Trade counts differed by up to 20% between them.
- The shared daily win/loss governor is applied across several projects and validated in
  none. On all three pairs the trades it discarded outperformed the trades it kept.

## September 5 — MarketCoach V3.4.1: session-anchor correction

Found and fixed a divergence between the MarketCoach research harness and the live
strategy, then re-graded everything downstream of it.

The live strategy re-anchors its session state twice a day — at the futures session
open and at calendar midnight — clearing the session VWAP, the daily signal count, the
signal cooldown, the whipsaw window and the opportunity lifecycle together. The harness
re-anchored once, on the calendar date only. For the nine hours between the session open
and midnight the harness was carrying the previous day's accumulated volume and stale
counters while the live code had already reset. The VWAP side is a term in a hard
five-way AND, so the divergence added and removed signals outright rather than merely
shifting them, and the entire Asia session sat inside the affected window.

**The correction costs more than expected.** An earlier partial patch — VWAP only —
looked mild. The faithful fix, which re-anchors every piece of state the live code
resets, is materially worse: expectancy down by about a quarter, positive years down
from 7/7 to 5/7, and the two years that were previously positive only by rounding both
flip negative. One of those is the largest year in the sample.

The strategy still clears the break-even win rate for its own payoff structure by about
ten percentage points, so it is still producing genuine directional information. What it
no longer does is survive a multiple-comparisons correction against the search budget
already spent on it — roughly twenty distinct configurations across stop buffers, bias
filters, moving-average lengths and direction slices.

**What changes as a result:**

- The old headline is retired. Results are now quoted with the plain interval and the
  search budget stated alongside, not a corrected interval claimed as passing.
- Forward testing moves from nice-to-have to the primary evidence path. It is
  out-of-sample by construction and costs nothing in multiplicity.
- The remaining question is regime dependence, not implementation: three years carry
  the whole result and two are below break-even. That is the next thing to investigate.

The fix ships behind a flag that defaults to matching live, and reproduces every
previously published number byte-identically when switched off, so nothing in the
history becomes unverifiable.

### Two method lessons worth keeping

**Check the win rate against the break-even rate for the payoff structure before
anything else.** A fixed-target strategy breaks even at 1/(1 + average winner). If the
measured win rate sits on that line, the setup contributes no directional information
and every downstream statistic is describing noise. One division. It would have ended
the VolSqueeze investigation on the first page, and it is the check that most clearly
separates the two projects logged above.

**A boundary condition written twice will eventually be written two ways.** The session
anchor existed in two places in one file, neither wrong on its own terms, disagreeing
for months. Where live code resets a block of state on one condition, the harness must
derive every one of those resets from a single expression — and a test must assert the
two implementations agree. This is the same defect family as the bot/backtest divergence
found in the Kraken project three days earlier.
