# How We Grade a Backtest

Plain-English version of the question "is this actually good, or does it just look good?"

## FAIL — walk away

- It only looks good because of a handful of lucky trades. Take away the best 5% of wins and it goes flat or negative.
- It falls apart most years, even if the overall average looks fine. One great year is hiding several bad ones.
- The "it wins 70-80% of the time" claim turns out false once you actually count it.
- It only looks good because of a mistake in how it was tested (a bug), not because the idea actually works. **The data itself measuring the wrong thing counts here too** — e.g. a "9:30-9:45 AM opening range" rule silently reading the wrong hour because the raw data's timezone was never verified. This isn't rare or exotic — it produced false PASS verdicts on three separate strategies in one sweep (2026-08-28).

## PASS — a real, usable edge

- Still makes money after you throw out the best few winners — the profit isn't resting entirely on a couple of freak trades.
- Positive in most years tested, not just one lucky stretch.
- Enough real trades behind it (hundreds, not a handful) that you're not just looking at a coin-flip sample.
- Any known weakness is understood and small, not a mystery.

## A+ — the best of what's here

Everything in PASS, plus:

- Positive in *every single year* tested, no exceptions. Not "mostly good" — genuinely consistent.
- Works both directions (long and short) on its own, not just one side carrying it.
- Wins and losses are shaped the way they're supposed to be — capped losses, real profit targets — not a "usually loses small, occasionally wins huge" lottery-ticket shape that just happens to average out positive.

## The full process, in order

1. **Formalize the idea into exact, no-lookahead rules.** Pin down every vague term before writing code (e.g. "2 hours" in a transcript turned out to mean "2 R" — auto-caption mangling "R" into "hour").
2. **Verify the data source's timezone BEFORE writing any rule that depends on time-of-day.** Raw export files carry no timezone label — don't assume they're already in ET, or already in whatever timezone the live platform displays. Run a quick sanity check first: after converting, does trading volume spike exactly at the real, known market open (and drop to near-zero at the real daily maintenance halt)? If it doesn't line up cleanly, the conversion is wrong — fix it before running anything else. This is not optional for any strategy with a session window, opening range, or "X:XX AM" rule anywhere in its logic. Skipping this step produced false PASS verdicts on three separate strategies in one sweep (2026-08-28) — the strategies weren't broken, the data feeding them was silently mistimed.
3. **Smoke test first** — a few months of data, not years. Cheap, catches obvious dead ends fast.
4. **Full multi-year test** on real sample size (the ~5-7yr back-adjusted NQ chain). A great smoke test is a hypothesis, not a result — small samples lie.
5. **Report multiple numbers, never just the average**: avg_R, median_R, real win rate (count of R>0 trades), and — most important — **excl_top5%** (strip the best 5% of trades and see if what's left is still positive).
6. **Year-by-year breakdown.** A flat blended average can hide a strategy that's quietly dying in recent years.
7. **Check where the outliers live.** Big winners spread across many different days = real edge. Big winners clustered on a handful of freak days = illusion.
8. **Hunt for bugs before trusting a good number.** Is the R-multiple distribution bounded where the stop/target design says it should be? Any suspicious result gets traced back to the raw data before it's trusted.
9. **Avoid overfitting.** One principled change at a time, not a parameter grid search. If a few values do get compared, re-validate the "winner" on the full-scale chain, not just the smoke sample — a smoke-sample improvement that doesn't hold at full scale is a red flag for a curve-fit, not a find.
10. **Save the script and its raw output somewhere durable the moment it stops being a throwaway experiment** — a git-tracked project folder, not a session scratchpad. A script that only ever lived in an ephemeral folder is gone the next time it's needed (e.g. when a new bug class is discovered and every past result needs re-checking against it) — forcing a from-scratch rebuild instead of just re-running the original with the fix, which is slower and adds a fresh chance of introducing a *different* discrepancy. Anything shaping a real go/no-go decision should be durable from its first real run, not just once it "passes."
11. **The actual bar for "pass."** Positive excl_top5%, consistent across most years, a real distributed tail, no unresolved bugs. Even after clearing that bar, it stays in Python / manual-indicator-only until there's an explicit decision to build it into a live, auto-trading strategy.
