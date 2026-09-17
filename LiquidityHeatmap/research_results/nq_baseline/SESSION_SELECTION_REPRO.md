# Session-selection reproduction

## Result

The existing 20 synthetic checks passed. A separate temporary-CSV experiment
reproduced the documented full-session selection bias in `backtest()`.

Both inputs contain identical New York minute-close bars from 09:31 through
12:00 on January 6, 2025. One input additionally contains bars through 16:00.
The default prices are O/H/L/C = 101/102/100.5/101. At 09:50 they are
101/102/99/101; at 09:51 they are 101/103/100.5/102. Volume is 1 throughout.
Timestamps are written as timezone-aware UTC. Costs are $5 round trip and one
slippage tick, with a $20 point value.

| Input | Morning trades | Complete sessions | Skipped sessions |
| --- | ---: | ---: | ---: |
| Through 16:00 (390 minutes) | 1 | 1 | 0 |
| Through noon (150 minutes) | 0 | 0 | 1 |

The assertion that the complete input trades and the noon-only input does not
passed. `backtest()` rejects a day unless `complete_session()` sees all 390
minutes, even though `simulate()` stops at noon. Thus future afternoon data
availability affects inclusion of morning trades. This is sample-selection
bias, not evidence that the sweep entry itself reads future prices.

## Recommended correction

Separate morning execution coverage from prior-day reference coverage:

1. Allow a complete 09:31–12:00 execution window regardless of afternoon data.
2. Require complete prior cash-session coverage before supplying its PDH/PDL.
3. Do not manufacture fills across missing morning minutes; record exclusions.
4. Test afternoon deletion invariance and incomplete-prior-day handling.
5. Save any corrected historical run separately from the original baseline.

A complete-morning requirement would still condition the sample on future
morning data availability. Disclose that residual selection limitation rather
than calling this a fully causal missing-data policy. Exchange-calendar and
entirely absent-session handling also remain unresolved.

No strategy code, input dataset, or saved baseline result was changed by this
experiment. This reproduction does not explain how much of the historical loss
comes from selection bias and does not establish a profitable trading edge.
