---
layout: default
date: "2026-09-26"
title: "Strategies — September 2026"
---

# Strategies - September 2026

Strategies and rule sets, whether coded or read by hand. A rule appearing here does not mean it works. Each entry says how far it has been tested.

## September 15 — Two discretionary setups, and what the mechanical test said

Two rules are read by hand on NQ during the New York session.

**Confirmed Structural Continuation.** A real, pre-existing swing level breaks on one-sided order flow. Price then pulls back toward the broken level and holds. Entry waits for the hold's confirmation and never happens on the break itself. The stop sits beyond the failed pullback's extreme, and targets are the next structural levels. If the leg into the break was already at maximum exhaustion, one extra confirmation bar is required.

**Attrition Break.** Time replaces flow as the confirmation. Two or more consecutive closes beyond a short-term level, with no reclaim, is enough. It fires far more often, so it carries a higher false-signal rate, and every trade is tagged by setup so the two can be separated later.

A scanner indicator now logs both setups' mechanical signals to a file, and both were written as code and tested against the same trade taken in the opposite direction. Neither beat its mirror. There was no directional edge in the mechanical version of either rule.

Two bugs in our own test surfaced along the way. The first run showed both setups losing badly, and that was a scale mismatch: the target search looked back about fifteen minutes on one-minute bars, found tiny local levels, and placed targets closer than the stop. The second run showed the mirror trade winning wildly, and that was a sign error that put the mirror's stop on the wrong side of entry. Both were fixed, and only the rerun counts. A mirror control that scores far better than the real trade is a bug alert until proven otherwise.

That result does not settle whether a human reading real structure adds anything. The code's version of "a real level" is a rolling pivot proxy, and that may not capture what a discretionary read is doing. Until that is tested, both setups stay unvalidated, and three further ideas defined the same day (a coil after an exhaustion extreme, a doji followed by a confirming candle, and a failed push beyond the Initial Balance) are defined but untested.

## September 18 — EMA50 Chandelier: what it is for

A strategy built from a public trading-education walkthrough. A 50-period EMA sets the trend. After an EMA cross it waits for a run of pullback bars, then rests a stop-entry order beyond the extreme of that group. The stop is a chandelier level, the target is 2R, the stop moves to breakeven at 1R, and a chandelier trail takes over after that. It scales its lookback and expiry by chart timeframe.

It ships with the fleet's standard safeguards: it stays disabled unless the connected account name matches, it caps dollar risk and stop size per trade, it locks out for the day after a loss limit, and it caps entries per session. A visual companion indicator draws the setup and the trade on the chart.

No results are claimed. Every backtest number quoted for a strategy has to pass the same independent audit as the rest of the fleet, and this one is still in that process.

## September 21 — Exhaustion Coil: first backtest

The third idea from September 15 ("a coil after an exhaustion extreme") was formalized into exact rules and backtested in Python against the NQ back-adjusted continuous contract. A bug was found and fixed during the process (coil boundaries were not being locked at confirmation, causing every setup to self-invalidate before a breakout could fire).

The pattern was tested across RSI thresholds, timeframes, and sessions. Full backtest numbers, the NT8 strategy source, and all diagnostic scripts are in the private Research repo (`Research/ExhaustionCoil/`).

Status: stays in Python / backtest-only until an explicit go/no-go decision.

## September 23 — A rule generator searched 13,608 rules. One survived, then failed.

Instead of testing one idea at a time, we built a generator that writes and tests rules mechanically: a session window, a trigger (a sweep and reclaim of a prior high or low, a run of lower lows or higher highs, an Initial Balance break, a VWAP band cross and a few more), follow or fade, and a fixed stop, target and time exit. Every rule pays realistic costs, fills on the next bar and can hold one position at a time.

The generator is only allowed to discover. It never judges. The data is split three ways before anything runs: a discovery period to search, a confirmation period that gets exactly one pre-registered rule and one run, and a final holdout that stays sealed. The code refuses a confirmation run unless the rule was written down and committed first.

Two flaws were caught before any real result counted. The random control first drew entries from every hour of the day, so a rule that only fired in the strongest hours "beat random" by timing alone; every trade is now compared with random entries from the same hour, direction and stop size. And a daily loss lockout applied to the rules but not to the random control, which flattered the rules; grading now runs without it on both sides.

On NQ, 13,608 rules were tried across two runs. One cleared every discovery gate. On the confirmation period it lost to its random control. That is the expected shape of a search this wide: the best of thirteen thousand tries is mostly luck, and the confirmation period exists to show it. The holdout stays sealed, and the confirmation period is now used up for this set of rules.

## September 25 — Bar-type sequences: no configuration passed

A popular method labels every bar as inside, directional or outside, and reads short sequences of those labels as reversal or continuation signals, ideally with several timeframes agreeing. We wrote down the rules and the pass bar before running anything, then tested five sequences, long and short, on 30- and 60-minute NQ bars, with entries and stops resolved on one-minute data, costs included, and a matched random control.

No configuration cleared the bar. The frequent sequences won often but lost money net: the targets sat close and the stops wide. Two rare 60-minute sequences looked interesting but were too thin to measure, and one of them turned negative in the second half of the data. Requiring the higher timeframes to agree did not help. The same test on crypto, currencies, Russell and bond futures found nothing that held up either.

One bug was caught by checking three trades by hand: the daily trading halt was being read as an ordinary bar, which created sequences that do not exist. The labels are still a useful way to read a chart, so they became an indicator with no edge claim (see Indicators, September 25).

## September 26 — Deviation Reversal: closed as a strategy, kept as a chart aid

The rule fades a stretch of two standard deviations or more from the session VWAP after a reversal bar, targeting a return to VWAP. Over 743 trades it lost money before costs as well as after, and it was negative in six of eight years. A pre-registered second version produced too few trades to count, and other timeframes were negative too. The backtest was re-checked for next-bar fills, stop-first ordering and look-ahead, and the verdict held.

So there is no strategy. The bands stay on the chart as an indicator that places no orders, after its session hours and volatility setting were corrected to match the backtest exactly.
