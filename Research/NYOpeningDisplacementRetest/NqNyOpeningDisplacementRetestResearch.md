# NQ NY Opening Displacement Retest Research

## Status

New, standalone research concept. The objective is a falsifiable, timing-aware opportunity signal, not a profitability claim. MarketCoach is not used as context.

## Hypothesis

The first hour after the New York cash open has the most reliable intraday activity expansion. A directional displacement outside the first 15-minute range, followed by a later retest that reclaims the broken edge, may distinguish accepted continuation from a raw opening-range probe.

## Exact Pre-Registered Rules

- Primary signal bars: 5-minute. Exit resolution: 1-minute.
- True UTC to `America/New_York` conversion; front-month stitched by highest daily volume.
- Opening range: 09:30-09:45 ET, high and low of three completed bars.
- Opportunity window: 09:30-10:30 ET. Displacement must close outside the range, have a same-direction body of at least `max(4 ticks, 0.50 x ATR(14))`, and close in the outer 25% of its bar.
- Retest: a later closed 5-minute bar within six bars of displacement must touch the broken edge, close back through the edge, and close in the displacement direction. No raw first-break entry and no sweep/reclaim reversal.
- Entry: next 5-minute bar open after confirmed retest. Stop: retest extreme or broken edge, plus 2 ticks of adverse buffer. Target: fixed 1R.
- One trade per CME session; no overnight hold; EOD flatten at 16:55 ET.
- NQ/MNQ-compatible quantity 1. On NQ, risk is capped at $250 (4-50 ticks); MNQ deployment uses one MNQ-equivalent contract. Daily realized loss lock is $500.
- One tick per side slippage and $4.20 round-turn commission.

## Why This Is Not Raw ORB

Raw ORB enters the first break and is exposed to opening probes and immediate reversals. This design requires displacement evidence first and continuation evidence second. The retest is required because it tests whether price can hold the broken edge after the initial impulse; a failed test produces no trade. The six-bar expiry keeps the signal tied to the observed New York volatility window.

## Validation

The Python engine writes exact results and a trade log beside itself. It aborts on timezone failure, invalid exits, excess risk, overlapping entries, non-causal timestamps, or non-genuine `DATA_END` exits. A negative economic result is a rejection; no optimization or rescue variant is permitted.

Generated result details are in `nq_ny_opening_displacement_retest_results.md` after the full run.
