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
