# Does MarketCoach transfer to RTY? — instrument portability test

**2026-09-02. Verdict: NOT CONFIRMED, leaning negative, but the RTY sample is too thin to be
decisive. It does not solve the trade-frequency problem, which was the reason for running it.**

## Why this test mattered

Every result in the fleet is NQ-only, so every result carries the same doubt: real edge, or
seven years of curve-fitting to one instrument? Running the same rules with **frozen**
parameters on a different market answers that more directly than any walk-forward, because
nothing was ever tuned on this data.

Contract translation is unusually clean: RTY is $50/point with a 0.10 tick = **$5.00/tick,
identical to NQ**. Every tick-denominated parameter transfers with its dollar meaning intact
(stop buffer $40, ATR floor $100, risk floor $40), and the cost model is unchanged.

## Result — NQ parameters frozen, nothing re-tuned

| scope | n | win% | avg_R | excl_top5% | yrs+ |
|---|---|---|---|---|---|
| COMBINED | 103 | 52.4% | +0.073 | **+0.001** | 3/6 |
| LONG | 48 | 50.0% | +0.035 | **−0.028** | 3/6 |
| SHORT | 55 | 54.5% | +0.107 | +0.054 | 4/6 |

**NQ reference: LONG n=168, win 62.5%, excl_top5% +0.206, 7/7 years.**

## Two structural reversals

**Direction tilt flips.** NQ long−short = **+0.180**; RTY long−short = **−0.072**. The long
bias that shows up in four separate NQ strategies is absent here, and mildly inverted.

**Session pattern flips too.** On NQ: Asia best (+0.228), NY worst (+0.009). On RTY: **NY best
(+0.171), Asia worst (−0.402)**, on n=12. A complete inversion.

If the edge were a genuine market mechanism — trend continuation after a pullback — you would
expect at least the same *sign* of tilt on a closely correlated index future. Getting the
opposite on both axes is the most concerning part of this result.

## But the honest statistics say inconclusive

| slice | n | avg_R | 95% CI | contains 0? | contains the NQ value? |
|---|---|---|---|---|---|
| RTY long | 48 | +0.035 | [−0.285, +0.354] | **yes** | **yes** (+0.267) |
| RTY combined | 103 | +0.073 | [−0.142, +0.289] | **yes** | **yes** (+0.189) |

NQ-long minus RTY-long: +0.254, SE 0.183, **t = +1.39 — not distinguishable.** With n=48 the
confidence interval is wide enough to contain both "no edge at all" and "exactly the NQ edge."
This test cannot separate them, so it is weak evidence, not proof of curve-fitting.

## Data caveat, stated plainly

RTY's export is patchier than NQ's: 1,132,165 bars over **1,088 trading days** vs NQ's
1,578,647 over ~1,430. Whole quarters are missing, and **2023 produced no trades at all** (only
98 days of 2023 data exist). RTY is also less liquid than NQ, so the identical 1-tick slippage
assumption is if anything generous — meaning the real RTY numbers would be worse, not better.

## The practical finding that matters most

**It does not fix trade frequency.** RTY generates **1.52 trades/month**, *lower* than NQ's
2.48. Even had the edge held, adding it would have taken the combined rate to ~4/month — not
the step change needed to make this system livable for a human.

## Conclusion

Do not deploy MarketCoach on RTY. The point estimates are flat, both structural tilts invert,
and the frequency is worse. The NQ result is not disproven — the sample cannot do that — but it
is **not corroborated**, and anyone treating the NQ numbers as a law of markets rather than a
property of one instrument should downgrade that belief.

## Reproduce

```
python backtest_mc_rty.py
```
