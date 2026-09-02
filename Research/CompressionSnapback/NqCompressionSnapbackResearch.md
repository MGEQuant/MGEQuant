# NQ Compression Snapback Research

## Status

**DECISIVE FAIL (2026-09-02).** Not approved for live trading, Sim101, or an indicator build. The backtest ran clean on the full 5.7-year NQ chain and the hypothesis is not supported.

## Distinct Hypothesis

After three unusually narrow completed 5-minute bars, a two-tick probe beyond that three-bar cluster that closes back inside the cluster may revert far enough to reach a fixed 1:1 target before the probe extreme is revisited.

This is deliberately different from the prior EMA/VWAP pullback, ORB breakout, session-open reversion, exhaustion fade, Renko pullback, QAX/MarketCoach continuation, and failed-2 concepts. It uses no EMA, VWAP, multi-timeframe bias, opening range, or directional trend filter.

## Fixed Configuration

- Instrument: NQ or MNQ, verified by the chart instrument.
- Signal bars: 5-minute bars, `Calculate.OnBarClose`.
- Sessions: electronic session from 18:00 through 16:55 Eastern, with the 17:00-18:00 maintenance period excluded.
- Compression: the prior three-bar high-low width is at most 75% of the median width of the prior 20 non-overlapping three-bar clusters.
- Trigger: current bar probes two ticks beyond the cluster high or low and closes back inside the cluster.
- Entry: next 5-minute bar open in the reversal direction.
- Stop: trigger-bar probe extreme plus a two-tick buffer.
- Target: exactly 1.0R.
- Default quantity: one contract.
- Maximum trade risk: `$250` before costs. On NQ, one tick is `$5`; on MNQ, one tick is `$0.50`.
- Daily loss limit: `$500`.
- Maximum two trades per session and six-bar cooldown.
- Exit-on-session-close: five minutes before the session close.

## Backtest Method

`backtest_compression_snapback.py` uses the local NQ exports at `C:\Users\maric\Documents\NinjaTrader 8\export\NQ`, converts UTC timestamps to DST-aware Eastern time, stitches quarterly contracts by highest daily volume, resamples to 5-minute bars for signals, and uses 1-minute bars for exit resolution. It models `$4.20` round-turn commission, one tick slippage per side, stop-first ordering on ambiguous bars, and next-bar-open entry fills.

Data verification passed both gates before any rule ran: volume steps up `+2,757` at 09:30 ET versus `+14` at 06:30, and the 17:00-17:55 maintenance halt shows mean volume `0` against `101` at 18:00-18:55. Timezone handling is correct.

Fill realism was checked against the Renko fill-artifact bug class. Entries fill at the genuine open of the next 5-minute bar, never at a synthetic price, and a gap guard rejects any signal whose next bar is not a contiguous same-session 5-minute bar (304 rejected). Outcomes are bounded at exactly `STOP`/`TARGET` with net R in `[-1.710, +0.941]`, which matches the 1:1 stop/target design. No artifact.

### Bugs found and fixed in the harness before these numbers were trusted

1. **Report crash** — `Trade` had no `risk_points` field but the report read `subset.risk_points`. This is why the earlier session captured no result; the run reached the results table and died there. The "terminal replayed stale output" explanation in the previous write-up was wrong.
2. **Instant EOD exit on every overnight trade** — the exit loop treated any bar at or past minute 1015 as end-of-day, which is true for the entire 18:00-23:59 block. Every overnight entry closed on its first bar. Narrowed to the real 16:55-17:00 window plus session change.
3. **Exit scan started five minutes late** — entries filled at a 5-minute bar's open but the exit scan began at that bar's close timestamp, skipping the first five minutes of every trade in both directions. Bars are close-stamped by NinjaTrader (the 18:00 session open appears as the `18:01` bar), so timestamps are now shifted to bar-open time and the entry bar is scanned.
4. **Negative-index wraparound** — the warm-up guard started at bar 23 while the oldest reference block reaches back 62 bars, so early bars silently indexed backwards into the end of the array. Warm-up raised to `CLUSTER_BARS * (REFERENCE_CLUSTERS + 1) + 2`.
5. **Microsecond/nanosecond index mismatch** — pandas 3.0 stores these timestamps at microsecond resolution, so an int64 search key built from the array was 1000x off from `Timestamp.value`. Caught because every trade returned `DATA_END`; the index is now forced to nanoseconds.

## Results

Full chain, 1,578,647 one-minute bars, 2020-12-09 to 2026-08-21. NQ, one contract, costs included.

### Pre-registered electronic-session configuration

| scope | n | win% | avg_R | median_R | excl_top5% | net_PnL | max_DD |
|---|---|---|---|---|---|---|---|
| COMBINED | 2312 | 49.6% | -0.178 | -1.059 | **-0.237** | -33,570 | -34,119 |
| LONG | 1070 | 51.0% | -0.149 | +0.527 | -0.206 | -12,384 | -12,280 |
| SHORT | 1242 | 48.4% | -0.204 | -1.065 | -0.263 | -21,186 | -23,006 |

Year by year (excl_top5%): 2020 `-0.297`, 2021 `-0.166`, 2022 `-0.235`, 2023 `-0.245`, 2024 `-0.209`, 2025 `-0.257`, 2026 `-0.268`. **Negative in all seven years, and negative in both directions.**

### Why it fails

On a fixed 1:1 target the strategy needs a win rate above roughly 50% plus costs. It gets 49.6%, with a 95% confidence interval of `[0.476, 0.516]` — a coin flip. Stripped of costs entirely, avg_R is `-0.008` and excl_top5% is `-0.061`: the compression-probe signal carries no directional information at all, and the `$14.20` round-turn cost against an average `$111.86` of risk (a `0.171R` drag) then does the rest.

### Structural finding: it was never an RTH strategy

The 18:00 session start plus the two-trades-per-session cap means the overnight block consumes both trades before the regular session opens. Of 2,312 pre-registered trades, **2,303 are overnight and only 4 are RTH** (20,585 trade-limit rejects). The live `.cs` shares this structure, so it would behave the same way on a chart.

A single diagnostic re-run restricted to 09:30-16:00 ET (`--rth`) gives RTH a real sample and does not rescue the concept — it is worse:

| scope | n | win% | avg_R | median_R | excl_top5% | net_PnL |
|---|---|---|---|---|---|---|
| COMBINED | 1758 | 46.1% | -0.196 | -1.063 | **-0.255** | -36,584 |
| LONG | 754 | 44.7% | -0.220 | -1.063 | -0.280 | -20,837 |
| SHORT | 1004 | 47.2% | -0.178 | -1.063 | -0.237 | -15,747 |

Negative in all seven years and both directions here too; no-cost avg_R is `-0.077`. This was one principled diagnostic, not a sweep, and it closes the last plausible "it was tested in the wrong place" objection.

## Open bugs in `NqCompressionSnapbackResearch.cs`

Reported, not fixed — the strategy is failed and should not be built out. If it is ever revived, both must be corrected first:

1. **Index-out-of-range on the reference window.** The guard is `CurrentBar < ReferenceClusterCount + CompressionBars + 2` (25), but the oldest reference block reads `High[63]`/`Low[63]`. It should be `CompressionBars * (ReferenceClusterCount + 1) + 1` (64). `BarsRequiredToTrade = 30` does not cover this either.
2. **Python/C# divergence.** The backtest enforces `MIN_STOP_TICKS = 4`; the strategy has no minimum-stop rule, so live behaviour would take tighter stops than anything tested.

## Verdict

**FAIL** under `DeveloperGuide/Backtest Pass Criteria.md`: negative excl_top5% in every scope, negative in every year tested, both directions negative, and the underlying signal is a verified coin flip on a large sample (n=2,312). This is not a thin or borderline result and there is no lever left worth pulling. Park it.

Reproduce with `python backtest_compression_snapback.py` and `python backtest_compression_snapback.py --rth`; raw output is saved as `run_electronic.txt` and `run_rth.txt`, trade logs as `compression_snapback_trades.csv` and `compression_snapback_trades_rth.csv`.
