"""
NQ Volatility Regime - build and validate the one structure the data actually contains.
========================================================================================

From explore_nq.py: NQ's returns are null essentially everywhere, but its volatility has a
clean 5x intraday shape (24 ticks of 5-min range at midnight ET, 124 at 10:00). This turns
that into something usable, and then tries hard to kill it.

MODEL. Expected range is decomposed into a LEVEL and a SHAPE:

    expected_range(t) = level(recent, causal) x shape(time-of-day bucket)

  - shape is a normalised time-of-day profile (mean 1.0), estimated on TRAIN ONLY.
  - level is a trailing median of recent true range, computed causally from completed bars,
    so it adapts as absolute volatility drifts between years (2022 vs 2024 are very
    different) without the shape having to re-learn.

THE TEST THAT MATTERS. A trailing volatility estimate alone is already a strong predictor -
volatility clusters. So the question is not "does this predict range" (it will), it is:

    does the time-of-day SHAPE add anything beyond the trailing LEVEL?

If shape adds nothing out of sample, the indicator is decoration and should not be built.
Measured on 2024-2026, untouched during exploration, against three baselines.

Usage:
    python volatility_regime.py
"""
import sys

import numpy as np
import pandas as pd

MC_DIR = r"F:\Trading Software\MarketCoach\Releases\NQMarketCoachV340SyncLive"
if MC_DIR not in sys.path:
    sys.path.insert(0, MC_DIR)

import backtest_mc_v340 as pipe  # noqa: E402

TICK = 0.25
SPLIT = pd.Timestamp("2024-01-01", tz="America/New_York")
BUCKET_MIN = 30          # time-of-day resolution
LEVEL_LOOKBACK = 20 * 78  # ~20 sessions of 5-min bars, trailing


def load_5m():
    b = pipe.load_1min_cached().copy()
    b["dt"] = b["dt"].dt.tz_convert("America/New_York")
    r = pipe.resample(b, "5min")
    r["tr"] = np.maximum(
        r["High"] - r["Low"],
        np.maximum((r["High"] - r["Close"].shift(1)).abs(),
                   (r["Low"] - r["Close"].shift(1)).abs()))
    r["tr_ticks"] = r["tr"] / TICK
    mins = r["dt"].dt.hour * 60 + r["dt"].dt.minute
    r["bucket"] = (mins // BUCKET_MIN).astype(int)
    return r.dropna(subset=["tr_ticks"]).reset_index(drop=True)


def fit_shape(train):
    """Normalised time-of-day profile, median-based for robustness. TRAIN ONLY."""
    med = train.groupby("bucket")["tr_ticks"].median()
    return med / med.median()


def causal_level(tr_ticks, lookback):
    """Trailing median true range using only COMPLETED prior bars (shift(1) = no lookahead)."""
    return pd.Series(tr_ticks).shift(1).rolling(lookback, min_periods=lookback // 4).median()


def score(actual, pred, label):
    m = np.isfinite(actual) & np.isfinite(pred) & (pred > 0)
    a, p = actual[m], pred[m]
    mae = np.mean(np.abs(a - p))
    # R^2 against the mean of actual
    ss_res = np.sum((a - p) ** 2)
    ss_tot = np.sum((a - a.mean()) ** 2)
    r2 = 1 - ss_res / ss_tot
    # Median absolute proportional error - scale-free, the number that matters for sizing
    mape = np.median(np.abs(a - p) / np.maximum(a, 1e-9))
    return {"label": label, "n": int(m.sum()), "MAE": mae, "R2": r2, "medAPE": mape}


def main():
    r = load_5m()
    train = r[r["dt"] < SPLIT]
    test = r[r["dt"] >= SPLIT].copy()
    print("TRAIN {:,} 5-min bars ({} .. {})".format(
        len(train), train["dt"].min().date(), train["dt"].max().date()))
    print("TEST  {:,} 5-min bars ({} .. {})  - untouched during exploration".format(
        len(test), test["dt"].min().date(), test["dt"].max().date()))

    shape = fit_shape(train)
    print("\nTIME-OF-DAY SHAPE fitted on TRAIN (multiplier, 1.0 = a typical bar)")
    print("{:>8} {:>10}   {}".format("ET", "shape", "profile"))
    for bkt in sorted(shape.index):
        h, m = divmod(bkt * BUCKET_MIN, 60)
        s = shape[bkt]
        print("{:>5}:{:02d} {:>10.2f}   {}".format(h, m, s, "#" * int(s * 20)))

    # Causal level, computed across the WHOLE series so the test half warms up naturally
    r["level"] = causal_level(r["tr_ticks"].to_numpy(), LEVEL_LOOKBACK)
    test = r[r["dt"] >= SPLIT].copy()

    actual = test["tr_ticks"].to_numpy()
    lvl = test["level"].to_numpy()
    shp = test["bucket"].map(shape).to_numpy().astype(float)

    print("\n" + "=" * 92)
    print("OUT-OF-SAMPLE TEST (2024-2026): does the time-of-day SHAPE add anything")
    print("beyond a trailing volatility LEVEL? If not, do not build this.")
    print("=" * 92)
    results = [
        score(actual, np.full_like(actual, np.nanmedian(train["tr_ticks"])), "constant (train median)"),
        score(actual, lvl, "trailing level only"),
        score(actual, test["bucket"].map(shape).to_numpy().astype(float)
              * np.nanmedian(train["tr_ticks"]), "shape only (fixed level)"),
        score(actual, lvl * shp, "level x shape  <-- the model"),
    ]
    print("{:<32} {:>9} {:>10} {:>9} {:>9}".format("predictor", "n", "MAE(ticks)", "R2", "medAPE"))
    for s in results:
        print("{:<32} {:>9,} {:>10.2f} {:>9.3f} {:>9.1%}".format(
            s["label"], s["n"], s["MAE"], s["R2"], s["medAPE"]))

    lvl_only = next(s for s in results if s["label"] == "trailing level only")
    model = next(s for s in results if s["label"].startswith("level x shape"))
    print("\n  shape contribution out-of-sample:  MAE {:+.2f} ticks   R2 {:+.3f}   medAPE {:+.1f}pp".format(
        model["MAE"] - lvl_only["MAE"], model["R2"] - lvl_only["R2"],
        (model["medAPE"] - lvl_only["medAPE"]) * 100))
    verdict = "ADDS REAL VALUE" if model["R2"] > lvl_only["R2"] + 0.01 else "adds little or nothing"
    print("  -> {}".format(verdict))

    # ---- stability: does the shape drift year to year? ----
    print("\n" + "=" * 92)
    print("STABILITY - is the shape the same every year, or is it drifting?")
    print("=" * 92)
    r["year"] = r["dt"].dt.year
    yearly = {}
    for y, g in r.groupby("year"):
        if len(g) < 5000:
            continue
        med = g.groupby("bucket")["tr_ticks"].median()
        yearly[y] = med / med.median()
    ys = sorted(yearly)
    print("  correlation of each year's shape with the TRAIN shape:")
    for y in ys:
        common = shape.index.intersection(yearly[y].index)
        c = np.corrcoef(shape[common], yearly[y][common])[0, 1]
        flag = "  (test year)" if y >= 2024 else ""
        print("    {}: r={:+.4f}{}".format(y, c, flag))

    # ---- what it means in practice ----
    print("\n" + "=" * 92)
    print("PRACTICAL CONSEQUENCE - a FIXED stop means wildly different things by hour")
    print("=" * 92)
    med_train = float(np.nanmedian(train["tr_ticks"]))
    print("  Compression Snapback used a fixed 48-tick max stop at every hour.")
    print("  Expressed as a multiple of the NORMAL 5-min range for that hour:")
    print("{:>8} {:>14} {:>18}".format("ET", "normal range", "48t stop = x range"))
    for bkt in sorted(shape.index):
        h, m = divmod(bkt * BUCKET_MIN, 60)
        if m:
            continue
        normal = shape[bkt] * med_train
        print("{:>5}:{:02d} {:>13.0f}t {:>17.1f}x".format(h, m, normal, 48 / normal))


if __name__ == "__main__":
    main()
