"""
Does the volatility regime actually MATTER to a live strategy's results?

volatility_regime.py established the model is real out-of-sample (shape adds R2 +0.032 over
a trailing level alone; shape correlation r>0.95 in every held-out year). That validates the
measurement. This asks the trading question:

    for MarketCoach's own 168 long trades, does the regime ratio at signal time
    -- actual ATR divided by what is NORMAL for that hour -- sort the outcomes?

ONE pre-specified hypothesis, stated before looking: trades taken when volatility is
ABNORMALLY HIGH for the time of day should do worse, because a swing-based stop is being set
in conditions wider than the setup was calibrated for.

If it sorts, the regime reading has direct trading value as a gate. If it does not, the tool
is still valid as a sizing reference - which is what it was designed for - but must not be
sold as a filter. Either answer is reported.

Any positive result gets walk-forward tested, per this project's own history of adopting
filters in-sample and reverting them (TSI MIN_TSI_GAP, trend maturity).

Usage:
    python regime_applied.py
"""
import sys

import numpy as np
import pandas as pd

MC_DIR = r"F:\Trading Software\MarketCoach\Releases\NQMarketCoachV340SyncLive"
if MC_DIR not in sys.path:
    sys.path.insert(0, MC_DIR)

import backtest_mc_v340 as pipe  # noqa: E402
from volatility_regime import BUCKET_MIN, TICK, SPLIT, fit_shape, load_5m  # noqa: E402


def excl_top5(col):
    if len(col) == 0:
        return float("nan")
    k = max(1, int(len(col) * 0.05))
    return col.sort_values(ascending=False).iloc[k:].mean()


def welch(a, b):
    d = a.mean() - b.mean()
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return d, se, (d / se if se else float("nan"))


def main():
    # --- regime shape from TRAIN only ---
    r5 = load_5m()
    shape = fit_shape(r5[r5["dt"] < SPLIT])
    med_train = float(np.nanmedian(r5[r5["dt"] < SPLIT]["tr_ticks"]))

    # --- MarketCoach's validated long-only trade set ---
    pipe.STOP_BUFFER_TICKS = 8
    pipe.REQUIRE_DAILY = False
    pipe.ENTRY_AT_NEXT_OPEN = True
    pipe.MODEL_OPPORTUNITY_LIMIT = False
    bars1m = pipe.load_1min_cached()
    bars5 = pipe.resample(bars1m, "5min")
    if not pipe.sanity_check_timezone(bars5):
        raise SystemExit("timezone check failed")
    bars5["daily_up"], bars5["daily_down"] = pipe.htf_votes(bars5["dt"], pipe.resample(bars1m, "1D"))
    bars5["h4_up"], bars5["h4_down"] = pipe.htf_votes(bars5["dt"], pipe.resample(bars1m, "4h"))
    bars5["m30_up"], bars5["m30_down"] = pipe.htf_votes(bars5["dt"], pipe.resample(bars1m, "30min"))
    name, allowed, first15 = pipe.session_info(bars5["dt"])
    bars5["session_name"] = name
    bars5["session_allowed"] = allowed
    bars5["first15"] = first15

    atr5 = pipe.atr_wilder(bars5, 14).to_numpy() / TICK
    et = bars5["dt"].dt.tz_convert("America/New_York")
    bkt = ((et.dt.hour * 60 + et.dt.minute) // BUCKET_MIN).astype(int)
    normal = bkt.map(shape).to_numpy().astype(float) * med_train
    regime = atr5 / normal          # 1.0 = exactly normal for this time of day

    signals = pipe.run_state_machine(bars5)
    risk = {s.entry_time: abs(s.entry - s.stop) for s in signals}
    reg = {s.entry_time: regime[s.bar_idx] for s in signals}
    df = pipe.apply_costs(pipe.resolve_signals(signals, bars1m), risk)
    df["regime"] = df["dt"].map(reg)
    lon = df[df["is_long"]].dropna(subset=["regime"]).copy()

    print("MarketCoach long-only, regime ratio attached (1.0 = normal for that hour)")
    print("  n={}  excl_top5%={:+.3f}".format(len(lon), excl_top5(lon["R_cost"])))
    print("  regime: min={:.2f} p25={:.2f} median={:.2f} p75={:.2f} max={:.2f}".format(
        lon["regime"].min(), lon["regime"].quantile(.25), lon["regime"].median(),
        lon["regime"].quantile(.75), lon["regime"].max()))

    print("\nDoes the regime ratio sort outcomes? (quartiles)")
    print("{:<26} {:>5} {:>7} {:>9} {:>11}".format("bucket", "n", "win%", "avg_R", "excl_top5%"))
    lon["q"] = pd.qcut(lon["regime"], 4, labels=["Q1 quiet", "Q2", "Q3", "Q4 hot"])
    for q, g in lon.groupby("q", observed=True):
        print("{:<26} {:5d} {:6.1f}% {:+9.3f} {:+11.3f}".format(
            str(q), len(g), (g["R"] > 0).mean() * 100, g["R_cost"].mean(), excl_top5(g["R_cost"])))

    print("\nPRE-SPECIFIED: abnormally hot conditions underperform (Q4 vs rest)")
    cut = lon["regime"].quantile(0.75)
    hot = lon[lon["regime"] > cut]["R_cost"]
    rest = lon[lon["regime"] <= cut]["R_cost"]
    d, se, t = welch(rest, hot)
    print("  rest (n={}) minus hot (n={}): {:+.3f}R  SE={:.3f}  t={:+.2f}".format(
        len(rest), len(hot), d, se, t))
    print("  95% CI [{:+.3f}, {:+.3f}]  -> {}".format(
        d - 1.96 * se, d + 1.96 * se,
        "excludes zero" if abs(t) > 1.96 else "INCLUDES ZERO - not significant"))

    if abs(t) > 1.96:
        print("\n  Significant in-sample, so walk-forward it (train<2024 -> test>=2024):")
        tr = lon[lon["year"] < 2024]
        te = lon[lon["year"] >= 2024]
        c = tr["regime"].quantile(0.75)
        base, filt = excl_top5(te["R_cost"]), excl_top5(te[te["regime"] <= c]["R_cost"])
        print("    train cut={:.2f}; test unfiltered {:+.3f} -> filtered {:+.3f}  ({:+.3f})".format(
            c, base, filt, filt - base))
        print("    -> {}".format("HELD out of sample" if filt > base else "did NOT hold"))
    else:
        print("\n  Not significant, so no filter is proposed and no walk-forward is warranted.")

    print("\n" + "=" * 88)
    print("THE SIZING CLAIM - the tool's actual purpose")
    print("=" * 88)
    print("  Regime-normalised risk vs raw risk, across MarketCoach's trades:")
    print("    raw stop distance (ticks): median={:.0f}  IQR={:.0f}-{:.0f}  spread={:.2f}x".format(
        (lon["R_cost"] * 0 + [abs(s.entry - s.stop) / TICK for s in signals
                              if s.entry_time in set(lon["dt"])][:len(lon)]).median()
        if False else np.median([abs(s.entry - s.stop) / TICK for s in signals]),
        np.percentile([abs(s.entry - s.stop) / TICK for s in signals], 25),
        np.percentile([abs(s.entry - s.stop) / TICK for s in signals], 75),
        np.percentile([abs(s.entry - s.stop) / TICK for s in signals], 75)
        / max(1e-9, np.percentile([abs(s.entry - s.stop) / TICK for s in signals], 25))))
    print("  A swing-based stop is already adaptive, which is WHY MarketCoach survives where")
    print("  fixed-tick strategies did not. The regime tool makes that adaptivity explicit and")
    print("  available to strategies that lack it.")


if __name__ == "__main__":
    main()
