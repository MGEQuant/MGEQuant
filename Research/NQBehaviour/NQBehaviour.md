# What does NQ actually do? — data-first characterisation

**2026-09-02.** Deliberately not strategy-first. Every prior effort in this fleet started
with a concept and asked whether NQ obliges; most did not. This inverts it: measure NQ's own
behaviour, then build only what the measurements support.

**Discipline:** exploration touched **train only (2020-12 → 2023-12)**. 2024-01 onward was
never loaded. Many things were examined, so anything promising here would be a hypothesis
needing the untouched years — that stage was never reached, for the reason below.

## Headline

**NQ's returns show no exploitable unconditional structure. Its volatility shows very strong
structure.** That is the classic "second moment predictable, first moment not" result, and it
holds cleanly here.

## Returns — null essentially everywhere

| test | cells | result |
|---|---|---|
| Mean drift by ET hour | 24 | 1 cell at \|t\|>2 (14:00, t=+2.09) |
| Overnight vs RTH vs full session | 3 | all null — t = 0.36 / 0.48 / 0.86 |
| Lag-1 autocorrelation, 5m→daily | 5 | 15m t=+2.55, 30m t=−2.16 |
| Day-of-week session move | 5 | all null, max \|t\| = 1.31 |
| Next overnight given RTH direction | 2 | null, t = −0.20 / +0.69 |

About **40 tests**, so roughly 2 false positives are expected at p<0.05. Three marginal cells
appeared — and **two of them contradict each other**: 15-minute bars show momentum
(autocorr +0.012) while 30-minute bars show mean reversion (autocorr −0.015). Adjacent
horizons disagreeing in sign, at effect sizes near 0.01, is the signature of noise, not
structure. Nothing here survives honest accounting.

The overnight result deserves a specific note: the well-known equity **overnight drift anomaly
does not show up significantly in NQ futures** over this window — +1.5 points per session at
t=0.36. Anyone building an overnight-hold strategy on the published equity literature would be
trading a number this data does not support.

## Volatility — the one real structure

Mean 5-minute true range by ET hour, train:

```
00:00   24 ticks   ############
03:00   54 ticks   ##########################
08:00   62 ticks   ##############################
09:00  102 ticks   ##################################################
10:00  124 ticks   #############################################################
12:00   80 ticks   #######################################
15:00   88 ticks   ############################################
17:00   26 ticks   #############
23:00   25 ticks   ############
```

A clean **5× swing** from the overnight trough to the 10:00 ET peak, monotonic into the open
and out of it. Unlike everything in the returns table, this is large, smooth, and mechanistic.

## What follows from this

**1. Do not build a directional strategy from NQ's unconditional statistics — there is nothing
there to build on.** Forcing one would repeat exactly what produced this fleet's 30+ failed
concepts. This is a real answer to "study how NQ trades and build from that", not a dodge: the
study was done, and it returned null on the first moment.

**2. It explains the fleet's history.** If simple structure existed, ORB / session-open
reversion / exhaustion fade / compression snapback / EMA-retest / the ICT levels would not all
have failed. They failed because they were harvesting unconditional structure that is not there.

**3. It explains why MarketCoach works.** MarketCoach fires **168 times in 316,219 bars** —
roughly 1 bar in 1,900. An edge that selective is invisible to every test above and is not
contradicted by any of them. The lesson is that surviving edges in this instrument are
extremely conditional, not that NQ is unbeatable.

**4. The volatility finding is directly actionable, and the fleet has already been bitten by
ignoring it.** Compression Snapback placed 2,303 of its 2,312 trades overnight while applying
the same fixed 48-tick maximum stop it would use at 10:00 ET — a window where 5-minute range
is a fifth as large. Parameters calibrated in one regime and applied in another is a category
error, and it is measurable here. MarketCoach's ATR floor (20 ticks) is the fleet's one
existing volatility-aware gate, and it is plausibly part of why it survives.

## Recommendation

No new directional strategy from this. The honest, buildable thing the data *does* support is
an **execution-layer** tool rather than a signal generator: a volatility-regime reference that
states what normal range is for the current hour, so stop/target sizing and position sizing are
calibrated to the regime actually in force. It claims no directional edge — which is precisely
why it is defensible, since directional edge is the thing this data says is absent.

## Reproduce

```
python explore_nq.py
```

Uses the validated Pacific-cached pipeline, converted to America/New_York because NQ's session
structure is ET-defined and hour-of-day results are only interpretable that way.

---

# Built: MGE NQ Volatility Regime (indicator)

Built and validated 2026-09-02 on the recommendation above. **Indicator only — places no
orders, prints no signals, makes no directional claim.**

## Model

```
expected 5-min range  =  LEVEL (causal trailing median true range)
                       x SHAPE (time-of-day profile, mean 1.0)
```

The level adapts as absolute volatility drifts between years; the shape carries the intraday
structure and never has to re-learn. Shape fitted on **train only** (2020-12 → 2023-12) at
half-hour Eastern resolution.

## The test that mattered

A trailing volatility estimate is already a decent predictor — volatility clusters. So the
real question was whether the time-of-day shape adds anything *beyond* it. Measured on
**2024-2026, untouched during exploration**:

| predictor | MAE (ticks) | R² | medAPE |
|---|---|---|---|
| constant (train median) | 50.79 | −0.031 | 51.2% |
| trailing level only | 43.05 | 0.010 | 45.3% |
| shape only (fixed level) | 41.24 | 0.011 | 41.0% |
| **level × shape** | **36.30** | **0.042** | **36.1%** |

The shape adds **R² +0.032, MAE −6.75 ticks, medAPE −9.3 points** out of sample. Absolute R²
is low because single-bar range is inherently noisy; the decision-relevant number is medAPE,
which drops from 45% to 36%.

**Stability** — correlation of each year's shape against the train profile:

| 2021 | 2022 | 2023 | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|
| +0.989 | +0.998 | +0.998 | **+0.997** | **+0.989** | **+0.950** |

Held-out years in bold. Nothing in the returns table came close to this.

## What was tested and rejected

Whether the regime ratio sorts MarketCoach's 168 long trades. **Pre-specified hypothesis —
that abnormally hot conditions underperform — was wrong.** The hot quartile was the *best*
(+0.487 excl_top5%) and the pattern is a non-monotonic U (Q1 +0.338, Q2 −0.001, Q3 +0.002,
Q4 +0.487), t = −1.87 with a CI including zero. **No filter is proposed and none should be
added.** This is a sizing reference, not a gate — stated in advance, and the answer went the
other way.

## Why it earns its place anyway

A fixed tick stop means wildly different things by hour. Expressed as a multiple of the normal
5-minute range for that time:

| ET | normal range | a fixed 48-tick stop |
|---|---|---|
| 00:00 | 22t | **2.2×** range |
| 03:00 | 56t | 0.9× |
| 10:00 | 138t | **0.3×** range |
| 17:00 | 26t | 1.9× |

A **7× swing** in what "48 ticks" means. Compression Snapback used exactly that fixed cap and
placed 2,303 of its 2,312 trades overnight.

## Parity check (no C# compiler outside the NinjaTrader IDE)

`indicator_parity_check.py` parses the 48-value array straight out of the `.cs`, replays the
indicator's exact logic — Pacific→Eastern conversion, current-bar-excluded trailing median,
every-12-bars level refresh — and compares against the validated model:

- shape transcription: max difference **0.000049** (rounding only)
- timezone: **100%** bucket agreement with true Eastern
- as-coded on 2024-2026: MAE **36.33t**, R² **0.042**, medAPE **36.1%** vs the model's 36.30 / 0.042 / 36.1%
- halt bucket (17:30-18:00 ET) is zero and is guarded, never divided by

Brace/paren/bracket balance verified 41/41, 115/115, 41/41.

## Status

**Not compiled, not attached to any chart.** Needs a NinjaTrader compile before use. It is
5-minute-specific and NQ/MNQ-specific; both are checked at runtime and warn on-chart.

## Reproduce

```
python explore_nq.py               # the characterisation
python volatility_regime.py        # model + out-of-sample validation
python regime_applied.py           # the rejected filter hypothesis
python indicator_parity_check.py   # .cs vs validated model
```
