# Trend Maturity Continuation — from-scratch redesign attempt

**Verdict: DO NOT BUILD. 2026-09-02.** Both halves of the redesign failed. MarketCoach V3.4.1
as it already stands remains the best expression of this idea in the fleet. No NinjaScript
was written, deliberately.

## The question

Knowing how MarketCoach works and what its backtest showed, what would a from-scratch
strategy look like? Two changes were proposed, each grounded in a specific audit finding
rather than invented:

1. **Strip the machinery that the diagnostics proved inert** — the 8-point "continuation"
   vote (never independently fires in 7 years), the opportunity rate limiter (blocks 0
   signals in 5.7 years), `RequireDailyBias` (already validated off), and the 10-point
   composite score, replaced by the explicit conditions it was gating.
2. **Add the one filter aimed at the diagnosed failure** — MarketCoach's `exhaustionScore`
   is a few-bar extension-from-EMA21 measure. The 2021 post-mortem found 5 straight long
   losses into NQ's all-time-high topping process, every one with a *low* exhaustion score
   (1.1–3.1 against a 6.5 ceiling). The filter was not broken, it was blind by construction.
   So: `maturity = (Close − SMA(daily,50)) / ATR(daily,14)` — how many daily-ATRs price sits
   above its own multi-month mean, using only completed daily bars.

## Result 1 — the "strip the machinery" half was wrong

| engine | n | win% | avg_R | excl_top5% | yrs+ |
|---|---|---|---|---|---|
| MarketCoach V3.4.1 long-only (real fill) | 168 | 62.5% | +0.267 | **+0.206** | 7/7 |
| From-scratch distilled core | 414 | 52.9% | +0.080 | **+0.008** | 6/7 |

Replacing the 10-point composite score with legible explicit conditions produced 2.5× the
signals at a quarter of the quality. **The composite score was not dead weight — it was doing
real selection**, and the assumption that it could be unpacked into a handful of readable
gates without loss was simply wrong.

The "continuation path is dead" and "rate limiter never binds" findings remain true and were
verified. But those two are genuinely inert; the composite score is not. Dropping all four at
once conflated them, which is the exact failure mode the project's "one principled change at
a time" rule exists to prevent.

## Result 2 — the maturity filter looked real in-sample, then failed validation

Applied to MarketCoach's own proven 165-trade long set (no refitting, just attaching each
trade's maturity reading at signal time), it initially looks like a find:

| bucket | n | win% | avg_R | excl_top5% |
|---|---|---|---|---|
| Q1 fresh | 42 | 61.9% | +0.221 | +0.157 |
| Q2 | 41 | 63.4% | +0.293 | +0.232 |
| Q3 | 41 | 73.2% | +0.538 | +0.490 |
| **Q4 stretched** | 41 | 48.8% | −0.047 | **−0.126** |

The stretched quartile is the only negative bucket, and the pre-specified hypothesis
("stretched trends underperform") clears significance: +0.396R, SE 0.193, **t = +2.05**,
95% CI [+0.018, +0.775].

But three checks in sequence dismantle it:

- **Not monotonic.** Q3 (+0.490) beats Q1 (+0.157), so "fresher is better" is false. Only the
  top quartile is bad, and Spearman ρ is just −0.088.
- **Fails multiple comparisons.** The tuned ceiling (≤3.5, excl_top5% +0.302) gives t = +2.31
  against a Bonferroni threshold of 2.64 for the 6 ceilings tested. Same correction that
  reclassified Exhaustion Fade.
- **Fails walk-forward — decisively.** Train on 2021–2023, freeze the choice, test on 2024–2026:

| | n | avg_R | excl_top5% |
|---|---|---|---|
| train (2021–23) unfiltered | 61 | | +0.087 |
| train picks ceiling ≤2.5 | 37 | | **+0.311** |
| **test (2024–26) unfiltered** | 104 | +0.307 | **+0.247** |
| **test, frozen ceiling ≤2.5** | 69 | +0.248 | **+0.191** |

Out-of-sample change: **−0.056**. The 35 trades the filter removed from the test half averaged
**+0.423R** — it was cutting good trades, not bad ones.

The reversed split (train recent, test early) *does* improve the early half, +0.087 → +0.251.
That inconsistency is the tell: a real effect shows in both directions. What this actually
describes is a **regime dependency** — the filter helps during topping and transition periods
like 2021 and hurts during sustained trends like 2024–26. Since the regime is not knowable in
advance, that is not a tradable edge.

Same outcome as the TSI `MIN_TSI_GAP` filter: convincing in-sample, reverted by walk-forward.

## What this closes

The "exhaustion filter is blind to multi-month trend age" hypothesis has been open in the
MarketCoach notes since 2026-08-29 as a diagnosed-but-untested idea. It is now tested and
**does not survive**. The 2021 weakness is real, but this is not the fix, and nobody should
spend more time on trend-age filters for this system without new evidence.

## Recommendation

**Build nothing.** Leave MarketCoach V3.4.1 exactly as it is — long-only, `RequireDailyBias=false`,
`StopBufferTicks=8`. It is already the strongest single-direction result in the fleet and both
attempts to improve it made it worse. The genuinely inert components (continuation path,
opportunity limiter) could be deleted as a pure code-simplification with zero behaviour change,
but that is cosmetic and carries recompile risk on a live Strategy for no gain.

## Reproduce

```
python backtest_trend_maturity.py --core    # the distilled engine alone
python backtest_trend_maturity.py           # + maturity sweep and ex-2021 honesty check
python maturity_on_marketcoach.py           # the decisive test on the proven trade set
python maturity_walk_forward.py             # walk-forward validation
```

Reuses MarketCoach's validated data pipeline (UTC→Pacific stitching, Wilder ATR, confirmed-swing
fractal, HTF last-completed-bar alignment, 1-minute exit resolution, cost model) rather than
rebuilding it — per Pass Criteria item 10, a fresh data layer only adds a fresh chance of a
different bug. Entries use the next-bar open, the real `Calculate.OnBarClose` fill verified
earlier the same day.
