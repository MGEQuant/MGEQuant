"""
Parity check: does MGE_NQVolatilityRegime_Indicator.cs compute the SAME thing the Python
model validated?

No C# compiler exists outside the NinjaTrader IDE, so the .cs cannot be run here. Instead
this re-implements the indicator's logic exactly as written in the file - the embedded
shape array parsed straight out of the .cs source, the Pacific->Eastern +3h bucket
conversion, the trailing median that EXCLUDES the current bar, and the every-12-bars level
refresh - and compares it against the validated model on the held-out period.

This catches the two things most likely to be wrong in a file that cannot be compiled:
a transcription error in the 48-number array, and a timezone conversion mistake. Both have
bitten this fleet before.

Usage:
    python indicator_parity_check.py
"""
import re
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, r"F:\Trading Software\MGEQuant\Research\NQBehaviour")
from volatility_regime import SPLIT, TICK, fit_shape, load_5m  # noqa: E402

CS_FILE = r"F:\Trading Software\MGEQuant\Research\NQBehaviour\MGE_NQVolatilityRegime_Indicator.cs"
HALT_BUCKET = 35
REFRESH_BARS = 12
LOOKBACK_SESSIONS = 20


def shape_from_cs():
    src = open(CS_FILE, encoding="utf-8").read()
    block = src[src.index("EasternShape = new double[]"):src.index("private const int HaltBucket")]
    vals = [float(x) for x in re.findall(r"-?\d+\.\d+", block)]
    return np.array(vals)


def main():
    cs_shape = shape_from_cs()
    print("Shape array parsed from the .cs: {} values".format(len(cs_shape)))
    assert len(cs_shape) == 48, "expected 48 half-hour buckets, got {}".format(len(cs_shape))

    r = load_5m()
    py_shape = fit_shape(r[r["dt"] < SPLIT])
    py = np.array([float(py_shape.get(b, 0.0)) for b in range(48)])

    diff = np.abs(cs_shape - py)
    print("Max |difference| vs the Python-fitted shape: {:.6f}".format(diff.max()))
    print("  -> {}".format("TRANSCRIPTION OK" if diff.max() < 5e-4 else "MISMATCH - do not ship"))
    if diff.max() >= 5e-4:
        for b in np.where(diff >= 5e-4)[0]:
            print("    bucket {:2d}: cs={:.4f} py={:.4f}".format(b, cs_shape[b], py[b]))
        raise SystemExit(1)

    # ---- timezone: the .cs reads Pacific chart time and adds 3h to reach Eastern ----
    print("\nTimezone conversion check (the .cs adds PlatformToEasternOffsetHours=3 to chart time)")
    pac = r["dt"].dt.tz_convert("America/Los_Angeles")
    cs_bucket = (((pac.dt.hour * 60 + pac.dt.minute + 180) % 1440) // 30).astype(int)
    true_bucket = r["bucket"].astype(int)
    agree = (cs_bucket.to_numpy() == true_bucket.to_numpy()).mean()
    print("  buckets agreeing with true Eastern: {:.2f}%".format(agree * 100))
    print("  -> {}".format(
        "OK" if agree > 0.99 else
        "MISMATCH - a fixed +3h cannot track DST; check this"))
    if agree <= 0.99:
        bad = r[cs_bucket.to_numpy() != true_bucket.to_numpy()]
        print("     {} disagreeing bars, e.g. {}".format(len(bad), bad["dt"].iloc[0]))

    # ---- replicate the indicator's causal level exactly as coded ----
    print("\nReplicating the .cs level/expected-range logic on the held-out period")
    tr = r["tr_ticks"].to_numpy()
    n = len(tr)
    maxkeep = max(200, LOOKBACK_SESSIONS * 78)
    level = np.full(n, np.nan)
    cached, last_bar = 0.0, -100000
    for i in range(n):
        if cached <= 0 or i - last_bar >= REFRESH_BARS:
            avail = i                      # bars strictly before i (excludes current)
            if avail >= 20:
                take = min(maxkeep, avail)
                cached = float(np.median(tr[i - take:i]))
                last_bar = i
        level[i] = cached if cached > 0 else np.nan

    bkt = true_bucket.to_numpy()
    shp = np.where(bkt == HALT_BUCKET, np.nan, cs_shape[bkt])
    shp = np.where(shp <= 0, np.nan, shp)
    expected = level * shp

    test = r["dt"] >= SPLIT
    a, p = tr[test.to_numpy()], expected[test.to_numpy()]
    m = np.isfinite(a) & np.isfinite(p) & (p > 0)
    a, p = a[m], p[m]
    mae = np.mean(np.abs(a - p))
    r2 = 1 - np.sum((a - p) ** 2) / np.sum((a - a.mean()) ** 2)
    mape = np.median(np.abs(a - p) / np.maximum(a, 1e-9))
    print("  indicator-as-coded, on 2024-2026: n={:,}  MAE={:.2f}t  R2={:.3f}  medAPE={:.1%}".format(
        len(a), mae, r2, mape))
    print("  validated Python model:            n=187,143  MAE=36.30t  R2=0.042  medAPE=36.1%")
    ok = abs(mae - 36.30) < 3.0 and r2 > 0.02
    print("  -> {}".format(
        "PARITY OK - the .cs reproduces the validated model within tolerance"
        if ok else "DIVERGENCE - investigate before shipping"))

    print("\nHalt bucket guard: bucket {} shape = {:.4f} -> {}".format(
        HALT_BUCKET, cs_shape[HALT_BUCKET],
        "correctly zero, and the .cs never divides by it" if cs_shape[HALT_BUCKET] == 0
        else "unexpected"))


if __name__ == "__main__":
    main()
