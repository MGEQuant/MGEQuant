# How good is the ENTRY itself? — MAE/MFE study

**2026-09-02.** Answers a question asked for a year and never measured: *"why can't we find an
entry so precise that price doesn't move against it once it fires — enough to take a small
profit, move to breakeven, and be risk-free?"*

Every prior backtest here scored trades on **final R only**, discarding the path. This measures
the path: how much heat each trade took, how fast it paid, and whether breakeven was ever
reachable before the stop.

## The race — reaches +X R before −1R?

| target | ALL | LONG | SHORT |
|---|---|---|---|
| +0.25R | **83.2%** | 83.9% | 82.3% |
| +0.50R | 72.1% | 73.8% | 70.0% |
| +0.75R | 64.4% | 66.7% | 61.5% |
| +1.00R | 58.4% | 62.5% | 53.1% |

Within-bar ties are resolved **against** the trade, so these are floors. **The entries are
well-timed: 83% of the time price offers something before stopping you out.**

## But the scalp economics destroy it

| take at | hit rate | avg_R | per $250 risked |
|---|---|---|---|
| +0.25R | 83.2% | +0.020 | **+$5** |
| +0.50R | 72.1% | +0.062 | +$16 |
| +1.00R | 58.4% | +0.148 | +$37 |
| tested TP1/TP2 | 58.4% | **+0.189** | **+$47** |

Risking 1R for 0.25R needs **80% just to break even**. The realised 83.2% leaves $5/trade —
~1,200 trades to make $6,000, or 22 years at 4.4 trades/month. Higher win rate, lower
expectancy: losses stay full size, only the wins shrink.

## Why "it shouldn't move against me" cannot be engineered

| eventual +1R winners | share |
|---|---|
| never went >0.25R against | **25.3%** |
| never went >0.50R against | 42.0% |
| **median heat before working** | **0.61R** |

**Three-quarters of winners dig substantially against you first**; the typical one travels 61%
of the way to the stop before paying. Consequences:

- Moving to breakeven quickly **scratches ~75% of the trades that would have paid**.
- Halving the stop distance turns **58% of eventual winners into losses** — better R:R, dead edge.

The heat is not a defect in the signal. It is the price of admission for the move that pays.

## No hidden pocket of better entries

+0.50R race by slice: LONG 73.8%, SHORT 70.0%, NY 70.3%, LONDON 73.8%, ASIA 72.9%. Everything
clusters at 70–74%. Nothing to filter toward.

## Bug found and fixed mid-analysis

The first run walked 20 days past each exit, so MAE absorbed price action long after the trade
closed and reported that *every* winner had gone to a full stop (median MAE 1.00R — impossible).
Fixed by bounding the walk to the trade's real lifetime (stop at −1R or TP2 at +2R, whichever
first). All numbers above are post-fix.

## Reproduce

```
python entry_excursion.py
```
