# NQ data-convention audit — preliminary

## Scope and conclusion

Read-only inspection of the research input and simulator; no strategy rules changed.
**Not cleared for strategy validation:** NinjaTrader documents UTC, end-of-bar
exports, and the March 2025 contract comparison supports this interpretation.
Continuous-series stitching, other contracts' adjustments, and data-quality issues
remain unverified. No independent chart/feed comparison or individual trade
reconstruction is claimed in this report.

Input: `F:\Trading Software\backtest_lab\NQ_BackAdjusted\NQ_Continuous_Adjusted.csv`
Simulator: `F:\Trading Software\MGEQuant\LiquidityHeatmap\ny_sweep_backtest.py`

## Verified timestamp conversions

The CSV header is `timestamp_utc,open,high,low,close,volume`. Values sampled below
are timezone-naive strings. Treating them as UTC produces these conversions using
Python `zoneinfo.ZoneInfo('America/New_York')`. These are adjusted-file prices,
not independently verified exchange prices.

| Raw timestamp (assumed UTC) | New York timestamp | CSV close |
| --- | --- | ---: |
| 2025-03-07 14:30:00 | 2025-03-07 09:30:00 -05:00 | 21439.75 |
| 2025-03-07 14:31:00 | 2025-03-07 09:31:00 -05:00 | 21468.25 |
| 2025-03-10 13:30:00 | 2025-03-10 09:30:00 -04:00 | 21285.00 |
| 2025-03-10 13:31:00 | 2025-03-10 09:31:00 -04:00 | 21282.75 |
| 2025-10-31 13:30:00 | 2025-10-31 09:30:00 -04:00 | 26946.25 |
| 2025-10-31 13:31:00 | 2025-10-31 09:31:00 -04:00 | 26926.50 |
| 2025-11-03 14:30:00 | 2025-11-03 09:30:00 -05:00 | 26983.00 |
| 2025-11-03 14:31:00 | 2025-11-03 09:31:00 -05:00 | 26995.25 |
| 2026-03-09 13:30:00 | 2026-03-09 09:30:00 -04:00 | 24923.75 |
| 2026-03-09 13:31:00 | 2026-03-09 09:31:00 -04:00 | 25001.75 |

Correct conversion arithmetic does not establish the original export timezone or
whether a timestamp denotes the start or end of a minute. The presence of both
09:30 and 09:31 bars cannot establish either convention.

## Simulator findings from source inspection

- Naive timestamps are assigned UTC, then converted to New York time.
- The cash-session selection is strictly after 09:30 through 16:00 inclusive.
  This is appropriate only under the stated minute-close convention.
- A retained day must contain all 390 minute closes; that uses information after
  the noon exit and introduces full-session selection bias.
- Incomplete observed days clear the prior-day reference. Entirely absent dates
  are not detected. PDH/PDL mean the previous retained cash-session high/low,
  not the entire overnight futures session.
- The opening range uses the first 15 retained minutes. Five-minute setups are
  evaluated at completed five-minute boundaries; entry processing precedes new
  setup generation, so newly generated setups cannot enter on their own bar.
- Stop takes priority when a minute touches stop and target. Entry-minute target
  credit is suppressed. These are modeling choices, not verified fill ordering.

## Roll provenance search

The input directory contains a continuous CSV and quarterly named CSVs. A bounded
recursive search of Python/PowerShell files under
`F:\Trading Software\backtest_lab` found consumers of the adjusted file, but no
construction implementation in the searched matches. This does not prove that
construction code or records do not exist elsewhere.

Required evidence remains: source contract per timestamp, roll dates/times,
roll-price reference, additive versus proportional adjustment method, cumulative
adjustment values, original export timezone, and bar-label convention. Quarterly
files in the same adjusted directory are not an independent reference.

Additional provenance flag: sampled first rows of quarterly files have Sunday
labels `2024-12-15 21:30:00`, `2025-03-16 15:22:00`, and
`2025-09-14 12:42:00`. These warrant checking against the applicable exchange
schedule and export timezone. No timezone correction is justified from these
three rows alone.

## Export provenance and direct comparison

The user identified the source as NinjaTrader historical exports and reported the
platform display timezone as `(UTC-08:00) Pacific Time (US & Canada)`.
Located original files:

- `C:\Users\maric\Documents\NinjaTrader 8\export\NQ\Full_NQ_Data`
- `C:\Users\maric\Documents\NinjaTrader 8\export\NQ\Rollover_Offset\ContractSymbolRolloverDateOffse.txt`

NinjaTrader's [Exporting documentation](https://ninjatrader.com/support/helpguides/nt8/exporting.htm)
states: "The historical data is exported with End of Bar time stamps" and
"The exported data will be in the UTC time zone."
Its [bar-building documentation](https://ninjatrader.com/support/helpguides/nt8/how_bars_are_built.htm)
explains that a 09:31 minute bar contains 09:30:00 through 09:30:59 data.
Thus the Pacific display setting is **not a reason to shift these export timestamps**.
These documents support the loader's UTC/end-of-minute convention; they do not
independently validate the provider's underlying prices.

### March 2025 contract: full-file comparison

Compared `NQ 03-25.Last.txt` from the original folder to
`F:\Trading Software\backtest_lab\NQ_BackAdjusted\NQ 03-25.Last.csv` by timestamp:

- 85,771 unique original timestamps and 85,771 adjusted rows.
- No adjusted timestamp missing from the original lookup; no volume mismatches.
- Every matched OHLC field is original price **plus 1,403.00 points**.
- Both files span `2024-12-15 21:30:00` to `2025-03-14 21:00:00`.
- Later listed roll offsets sum to 1,403.00:
  `203.5 + 214.5 + 237.5 + 256.5 + 208.75 + 282.25`.

This supports additive cumulative adjustment for this contract only. The offset
file says `03-06` next to `2025-12-15`; this apparent contract-label typo must be
resolved before treating it as a machine-readable roll specification.

### Actual loader assertion

Ran `ny_sweep_backtest.read_days` on the adjusted March contract and asserted:

- Raw `20250307 143100` maps to `2025-03-07T09:31:00-05:00`.
- Original OHLC: `20037.50 / 20077.00 / 20023.75 / 20065.25`.
- Loaded OHLC: `21440.50 / 21480.00 / 21426.75 / 21468.25`.
- All four loaded prices equal original plus 1,403.00.
- That day's loader output contains 390 bars, 09:31 through 16:00 New York.

All assertions passed. This checks the real loader on one contract/day, not the
entire continuous file or an independent feed. No data or strategy rules changed.

## Required next checks (not yet completed)

1. Locate the construction script or reconstruct and verify its contract-selection
   and roll-boundary rules. A broader Python/PowerShell search under
   `F:\Trading Software` found consumers, not the construction implementation.
2. Verify all original-to-adjusted contracts and continuous-series stitching,
   including the offset-table typo and suspicious Sunday records above.
3. Compare sampled OHLC against an independent one-minute contract chart with
   documented timezone and adjustment settings.
4. Reconstruct a deterministic sample of recorded winners, losers, noon exits,
   and ambiguous fill bars; verify setup levels were available before entry.
5. Resolve data/session issues before testing another strategy variant. Preserve
   the existing baseline as provisional; do not silently overwrite its results.
