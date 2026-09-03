"""
NQ Volatility Regime - the missing baseline.
========================================================================================
volatility_regime.py concluded the time-of-day SHAPE "ADDS REAL VALUE" because
level x shape beat a trailing LEVEL alone out of sample. That test is real but it is
not discriminating: the level there is a rolling median over ~20 full SESSIONS
(LEVEL_LOOKBACK = 20*78 = 1560 five-minute bars), which averages across every hour of
the day and is therefore STRUCTURALLY INCAPABLE of carrying time-of-day information.
Since the same study already established that NQ volatility swings ~5x by hour, that
comparison could only ever come out one way.

The test that actually discriminates: a PER-BUCKET trailing median - the median true
range of the SAME time-of-day bucket over the last N sessions, computed causally. That
adapts to level drift AND carries the intraday shape, with no train-fitted static
profile at all. Algebraically it is the "causal adaptive shape" version of the same
model (bucket_level = global_level x (bucket_median/global_median)).

THE QUESTION: does freezing a 2020-23 shape buy anything over just re-estimating it
from recent data as you go? If it does not, the hard-coded EasternShape[] table in
MGE_NQVolatilityRegime_Indicator.cs is unnecessary - and, more importantly, it is the
part exposed to the drift already visible in the stability section (shape correlation
vs train: .9976 in 2023 -> .9966 -> .9887 -> .9501 in 2026, monotonically down).

Two fixes to the original scoring are applied here:
  1. ALL predictors are scored on one common bar mask. The original dropped the 8
     maintenance-halt bars (shape = 0.00 fails its `pred > 0` filter) for the model but
     kept them for the baselines, so the compared samples were not identical. The
     effect is immaterial (0.004% of bars) but the comparison should be like-for-like.
  2. Paired significance on the MAE differences, which the original reported without
     any interval.

Usage:
    python volatility_regime_baseline_check.py
"""
import numpy as np
import pandas as pd

import volatility_regime as vr

SESSION_BARS_PER_BUCKET = 6      # a 30-min bucket holds 6 five-minute bars per session


def causal_bucket_level(df, sessions):
    """Median TR of the SAME time-of-day bucket over the last `sessions` sessions,
    using only COMPLETED prior bars (shift(1) inside each bucket = no lookahead)."""
    lookback = sessions * SESSION_BARS_PER_BUCKET
    out = pd.Series(np.nan, index=df.index)
    for _, g in df.groupby("bucket", sort=False):
        out.loc[g.index] = (g["tr_ticks"].shift(1)
                            .rolling(lookback, min_periods=max(5, lookback // 4))
                            .median())
    return out


def paired_mae_test(actual, pred_a, pred_b, mask):
    """Paired test on |err_a| - |err_b| over the common mask. Positive mean => a worse."""
    ea = np.abs(actual[mask] - pred_a[mask])
    eb = np.abs(actual[mask] - pred_b[mask])
    d = ea - eb
    n = len(d)
    mean = d.mean()
    se = d.std(ddof=1) / np.sqrt(n)
    return mean, se, (mean / se if se > 0 else np.nan)


def main():
    r = vr.load_5m()
    train = r[r["dt"] < vr.SPLIT]
    shape = vr.fit_shape(train)

    r["level"] = vr.causal_level(r["tr_ticks"].to_numpy(), vr.LEVEL_LOOKBACK)
    for s in (20, 60):
        r["bucket_level_{}".format(s)] = causal_bucket_level(r, s)

    test = r[r["dt"] >= vr.SPLIT].copy()
    actual = test["tr_ticks"].to_numpy()
    lvl = test["level"].to_numpy()
    shp = test["bucket"].map(shape).to_numpy().astype(float)
    med_train = float(np.nanmedian(train["tr_ticks"]))

    preds = {
        "constant (train median)": np.full_like(actual, med_train),
        "trailing level only": lvl,
        "level x FROZEN shape  <-- shipped model": lvl * shp,
        "per-bucket trailing (20 sess)  <-- fair baseline": test["bucket_level_20"].to_numpy(),
        "per-bucket trailing (60 sess)  <-- fair baseline": test["bucket_level_60"].to_numpy(),
    }

    # ONE common mask so every predictor is scored on identical bars (fix #1).
    mask = np.isfinite(actual)
    for p in preds.values():
        mask &= np.isfinite(p) & (p > 0)

    print("TEST WINDOW {} .. {}".format(test["dt"].min().date(), test["dt"].max().date()))
    print("scored on {:,} bars common to every predictor "
          "(of {:,} test bars)\n".format(int(mask.sum()), len(test)))

    print("{:<50} {:>10} {:>9} {:>9}".format("predictor", "MAE(ticks)", "R2", "medAPE"))
    rows = {}
    a = actual[mask]
    ss_tot = np.sum((a - a.mean()) ** 2)
    for label, p in preds.items():
        pm = p[mask]
        mae = np.mean(np.abs(a - pm))
        r2 = 1 - np.sum((a - pm) ** 2) / ss_tot
        mape = np.median(np.abs(a - pm) / np.maximum(a, 1e-9))
        rows[label] = mae
        print("{:<50} {:>10.2f} {:>9.3f} {:>9.1%}".format(label, mae, r2, mape))

    print("\n" + "=" * 92)
    print("THE COMPARISON THAT DISCRIMINATES")
    print("=" * 92)
    frozen = "level x FROZEN shape  <-- shipped model"
    for s in (20, 60):
        fair = "per-bucket trailing ({} sess)  <-- fair baseline".format(s)
        mean, se, t = paired_mae_test(actual, preds[frozen], preds[fair], mask)
        better = "FROZEN shape better" if mean < 0 else "per-bucket better"
        print("  frozen-shape MAE - per-bucket({} sess) MAE = {:+.3f} ticks "
              "(SE {:.3f}, t={:+.1f})  -> {}".format(s, mean, se, t, better))

    print("\n  Reference - the original study's own headline comparison, same mask:")
    mean, se, t = paired_mae_test(actual, preds["trailing level only"], preds[frozen], mask)
    print("  level-only MAE - frozen-shape MAE = {:+.3f} ticks (SE {:.3f}, t={:+.1f})".format(
        mean, se, t))

    print("\n" + "=" * 92)
    print("READING IT")
    print("=" * 92)
    print("  If per-bucket trailing matches or beats the frozen shape, the hard-coded")
    print("  EasternShape[] table earns nothing over re-estimating from recent data - and")
    print("  re-estimating is immune to the drift the stability section already shows.")
    print("  If the frozen shape wins clearly, it is carrying real long-run structure that")
    print("  a 20-60 session window is too noisy to recover, and shipping it is justified.")


if __name__ == "__main__":
    main()
