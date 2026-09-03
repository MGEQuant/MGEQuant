# Compression Snapback V2

## Status

This is a separate, research-only revision. The original files remain the failed control and are unchanged.

## Falsifiable Hypothesis

Preserving the compression snapback signal but using 3-minute primary signal bars for signal formation and entry may reduce missed intrabar reversals and improve fill and exit resolution. This is a hypothesis, not a claim that the strategy can be made profitable.

The V2 timeframe is a new 3-minute signal variant, not a direct execution-only overlay comparison. Signals are formed only from closed 3-minute bars. Entry is the next 3-minute bar open. Exits are evaluated using the underlying 1-minute bars.

## Fixed Pre-Registered Configuration

- Instrument: NQ or MNQ, one contract.
- Signal bars: 3-minute primary bars, `Calculate.OnBarClose`.
- Compression: 3 bars = 9 minutes; width at most 75% of the median width of 20 prior non-overlapping 3-bar clusters = 60 minutes.
- Trigger: 2-tick probe beyond the cluster, with the signal bar closing back inside.
- Stop: trigger-bar probe extreme plus 2 ticks; minimum 4 ticks; maximum 48 ticks.
- Target: exactly 1:1 from the actual entry price.
- Maximum risk: $250; daily loss limit: $500.
- Maximum 2 trades per CME session; cooldown 6 three-minute bars.
- Sessions: electronic hours, excluding the 17:00-18:00 ET maintenance halt.
- Costs: $4.20 round-turn commission and 1 tick slippage per side.
- Ambiguous 1-minute bars: stop wins.
- No optimization or parameter sweep.

## Implementation Changes

`NqCompressionSnapbackResearchV2.cs` fixes the source defects without changing the original control:

- `BarsRequiredToTrade = 64`, and the runtime guard covers the deepest `High[63]`/`Low[63]` reference access.
- Adds the explicit `MinimumStopTicks` property, fixed at 4.
- Configures `SetStopLoss` and `SetProfitTarget` with the same computed stop ticks and matching entry signal before each entry.
- Uses older NinjaTrader-compatible syntax.

`backtest_compression_snapback_v2.py`:

- Reads the same 1-minute exports, converts UTC to DST-aware Eastern time, stitches by highest daily volume, and resamples to 3-minute bars.
- Uses next-3-minute-open entries and 1-minute exit lookup from the exact timezone-aware timestamp.
- Writes `compression_snapback_v2_trades.csv` and the generated results report beside the script, independent of the current working directory.
- Rejects invalid timestamps, unexpected outcomes, unbounded raw R, missing exits, and accidental `DATA_END` outcomes.

## Validation and Verdict

Run from any directory with:

```text
python "f:\Trading Software\MGEQuant\Research\CompressionSnapback\backtest_compression_snapback_v2.py"
```

The exact results are generated in `NqCompressionSnapbackResearchV2_results.md`. Compare them with the unchanged 5-minute control: 2,312 trades, 49.6% win rate, -0.178 average net R, and -$33,570.40 after costs, negative in all seven years.

A negative V2 result is a failure and the recommendation is to stop rather than apply another arbitrary tweak. A preliminary pass would justify only an untouched out-of-sample test, never live approval.
