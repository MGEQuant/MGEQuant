# Standalone VolatilityRegime Signal Backtest

## Verdict

This is a mechanical research proxy, not a probability of future profit. The untouched test outcome is **REJECT this hypothesis for now**. A single historical backtest cannot establish future profitability or its probability.

## Pre-registered assumptions

- NQ 5-minute bars from the verified local 1-minute cache; ET timestamps; electronic session bars except 17:00-18:00 ET.
- Shape: train-only median TR by 30-minute ET bucket, normalized by the train median. Expected range = causal prior-bar rolling median TR over 1,560 prior 5-minute bars times that shape.
- Signal at a completed bar close: prior bar TR ratio >= 1.25 and directional body >= 0.5 TR. Entry is the next 5-minute bar's first 1-minute open.
- Stop = 0.5 expected range for the entry bar's ET bucket, rounded up to ticks and bounded 12-48; target = 1R; quantity = 1 NQ.
- One trade at a time, maximum 2 trades per CME session, 6-bar entry cooldown, $500 daily loss limit, $4.20 commission, 1 tick adverse slippage per side.
- Exits use 1-minute bars. If stop and target are both touched in one minute, stop wins. Signals without a resolved exit are hard failures, not silently closed trades.

## Data and causality audit

- Cache: `F:\Trading Software\MarketCoach\Releases\NQMarketCoachV340SyncLive\_bars1m_cache_pacific.pkl`
- 1-minute window: 2020-12-09 03:01:00-05:00 to 2026-08-21 17:00:00-04:00 ET; 5-minute bars: 316,219; train bars: 129,068; shape buckets: 48.
- The prior-bar TR, rolling level, train-fitted shape, entry open, and entry-hour expected range are all timestamp-causal.
- Assertions passed: no unresolved DATA_END trades, valid exits, signal timestamp before entry timestamp, bounded stop R, and CSV audit fields emitted.
- Counters: bars=316219, signals=47480, entries=2304, blocked_session_limit=44124, blocked_cooldown=1049, blocked_in_trade=0, blocked_daily_loss=0, blocked_no_entry_bar=3, blocked_no_expectation=387, data_end=0, blocked_terminal_candidate=0, ambiguous_stop_first=1154

## Results

| Period | Trades | Win rate | Net | Average R | Signals/week | Trades/week |
|---|---:|---:|---:|---:|---:|---:|
| Full history (combined) | 2,304 | 46.0% | $-41,476.80 | -0.181 | 159.85 | 7.76 |
| Train 2020-12 to 2023-12 (combined) | 943 | 47.0% | $-13,290.60 | -0.177 | 118.61 | 5.93 |
| Untouched test 2024-01 to 2026-08-21 (combined) | 1,361 | 45.3% | $-28,186.20 | -0.183 | 208.24 | 9.90 |
| Full history (long) | 1,166 | 46.7% | $-21,332.20 | -0.165 | 78.46 | 3.93 |
| Full history (short) | 1,138 | 45.3% | $-20,144.60 | -0.196 | 81.52 | 3.84 |

### Yearly

| Year | Trades | Win rate | Net | Average R | Signals/week | Trades/week |
|---|---:|---:|---:|---:|---:|---:|
| 2020 | 30 | 46.7% | $-241.00 | -0.210 | 167.48 | 10.38 |
| 2021 | 228 | 45.2% | $-4,212.60 | -0.217 | 110.65 | 4.71 |
| 2022 | 268 | 49.3% | $-2,105.60 | -0.102 | 130.02 | 6.83 |
| 2023 | 417 | 46.5% | $-6,731.40 | -0.200 | 190.36 | 10.03 |
| 2024 | 518 | 46.1% | $-6,855.60 | -0.189 | 210.20 | 9.96 |
| 2025 | 511 | 44.4% | $-12,951.20 | -0.199 | 203.22 | 9.85 |
| 2026 | 332 | 45.5% | $-8,379.40 | -0.151 | 216.57 | 10.06 |

### Cost break-even

Average stop risk was $107.37. With 1:1 payoff, commission, and two modeled 1-tick slippage sides, the break-even win rate at average risk is **56.61%**. This varies by stop size; the exact trade-level net and R are in the CSV.

### Output

Trade CSV: `standalone_volatility_regime_signal_trades.csv`

No MarketCoach trades, indicators, or strategy context were used.
