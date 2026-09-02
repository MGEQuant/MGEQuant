"""
Walk-forward validation of the trend-maturity filter - the decisive test.

The in-sample picture is ambiguous: the pre-specified "stretched trends underperform"
hypothesis clears significance at t=+2.05, but the tuned ceiling fails a Bonferroni
correction for the 6 ceilings tested (t=2.31 vs a 2.64 threshold). That is precisely the
situation where this project's own history says to walk it forward rather than argue
about it - the TSI MIN_TSI_GAP filter looked good in-sample, was adopted, and was then
REVERTED when walk-forward exposed it as overfitting.

Method: choose the maturity ceiling on the TRAIN half only, then apply that single
frozen choice to the untouched TEST half. If the filter is real, the train-chosen
ceiling should still help out of sample. If it is curve-fitting, it will not.

Usage:
    python maturity_walk_forward.py
"""
import sys

import numpy as np
import pandas as pd

MC_DIR = r"F:\Trading Software\MarketCoach\Releases\NQMarketCoachV340SyncLive"
if MC_DIR not in sys.path:
    sys.path.insert(0, MC_DIR)

import backtest_mc_v340 as pipe  # noqa: E402
from backtest_trend_maturity import daily_maturity, excl_top5  # noqa: E402

CAPS = [4.0, 3.5, 3.0, 2.5, 2.0, 1.5]
SPLIT_YEAR = 2024   # train < 2024, test >= 2024


def build():
    pipe.STOP_BUFFER_TICKS = 8
    pipe.REQUIRE_DAILY = False
    pipe.ENTRY_AT_NEXT_OPEN = True
    pipe.MODEL_OPPORTUNITY_LIMIT = False
    bars1m = pipe.load_1min_cached()
    bars5 = pipe.resample(bars1m, "5min")
    if not pipe.sanity_check_timezone(bars5):
        raise SystemExit("timezone sanity check failed")
    bars5["daily_up"], bars5["daily_down"] = pipe.htf_votes(bars5["dt"], pipe.resample(bars1m, "1D"))
    bars5["h4_up"], bars5["h4_down"] = pipe.htf_votes(bars5["dt"], pipe.resample(bars1m, "4h"))
    bars5["m30_up"], bars5["m30_down"] = pipe.htf_votes(bars5["dt"], pipe.resample(bars1m, "30min"))
    name, allowed, first15 = pipe.session_info(bars5["dt"])
    bars5["session_name"] = name
    bars5["session_allowed"] = allowed
    bars5["first15"] = first15
    bars5["maturity"] = daily_maturity(bars5["dt"], pipe.resample(bars1m, "1D"))

    signals = pipe.run_state_machine(bars5)
    risk = {s.entry_time: abs(s.entry - s.stop) for s in signals}
    mat = {s.entry_time: bars5["maturity"].to_numpy()[s.bar_idx] for s in signals}
    df = pipe.apply_costs(pipe.resolve_signals(signals, bars1m), risk)
    df["maturity"] = df["dt"].map(mat)
    return df[df["is_long"]].dropna(subset=["maturity"]).copy()


def main():
    lon = build()
    train = lon[lon["year"] < SPLIT_YEAR]
    test = lon[lon["year"] >= SPLIT_YEAR]
    print("Walk-forward split at {}:  train n={} ({}-{})   test n={} ({}-{})".format(
        SPLIT_YEAR, len(train), train["year"].min(), train["year"].max(),
        len(test), test["year"].min(), test["year"].max()))

    print("\nSTEP 1 - choose the ceiling on TRAIN only")
    print("{:<20} {:>5} {:>11}".format("ceiling", "n", "excl_top5%"))
    print("{:<20} {:5d} {:+11.3f}".format("no filter", len(train), excl_top5(train["R_cost"])))
    best, best_cap = None, None
    for cap in CAPS:
        g = train[train["maturity"] <= cap]
        if len(g) < 20:
            print("{:<20} {:5d}   (too thin)".format("<= {:.1f}".format(cap), len(g)))
            continue
        e = excl_top5(g["R_cost"])
        print("{:<20} {:5d} {:+11.3f}".format("<= {:.1f}".format(cap), len(g), e))
        if best is None or e > best:
            best, best_cap = e, cap
    print("  -> train picks maturity <= {:.1f} (train excl_top5% {:+.3f} vs {:+.3f} unfiltered)".format(
        best_cap, best, excl_top5(train["R_cost"])))

    print("\nSTEP 2 - apply that frozen choice to the untouched TEST half")
    base_e = excl_top5(test["R_cost"])
    kept = test[test["maturity"] <= best_cap]
    filt_e = excl_top5(kept["R_cost"])
    print("{:<28} {:>5} {:>7} {:>9} {:>11}".format("test set", "n", "win%", "avg_R", "excl_top5%"))
    print("{:<28} {:5d} {:6.1f}% {:+9.3f} {:+11.3f}".format(
        "unfiltered", len(test), (test["R"] > 0).mean() * 100,
        test["R_cost"].mean(), base_e))
    print("{:<28} {:5d} {:6.1f}% {:+9.3f} {:+11.3f}".format(
        "maturity <= {:.1f} (frozen)".format(best_cap), len(kept),
        (kept["R"] > 0).mean() * 100, kept["R_cost"].mean(), filt_e))
    print("  out-of-sample change: {:+.3f}".format(filt_e - base_e))

    dropped = test[test["maturity"] > best_cap]["R_cost"]
    if len(dropped) > 1:
        d = kept["R_cost"].mean() - dropped.mean()
        se = np.sqrt(kept["R_cost"].var(ddof=1) / len(kept) + dropped.var(ddof=1) / len(dropped))
        print("  kept minus dropped on TEST: {:+.3f}R  SE={:.3f}  t={:+.2f}".format(d, se, d / se))
        print("  trades the filter removed from test: n={}, their avg_R={:+.3f}".format(
            len(dropped), dropped.mean()))

    print("\nVERDICT")
    if filt_e > base_e and len(kept) >= 30:
        print("  Filter HELD OUT OF SAMPLE ({:+.3f} -> {:+.3f}).".format(base_e, filt_e))
    else:
        print("  Filter did NOT hold out of sample ({:+.3f} -> {:+.3f}).".format(base_e, filt_e))
    print("\nReversed split (train on recent, test on early) as a robustness check:")
    tr2, te2 = lon[lon["year"] >= SPLIT_YEAR], lon[lon["year"] < SPLIT_YEAR]
    b2, c2 = None, None
    for cap in CAPS:
        g = tr2[tr2["maturity"] <= cap]
        if len(g) < 20:
            continue
        e = excl_top5(g["R_cost"])
        if b2 is None or e > b2:
            b2, c2 = e, cap
    k2 = te2[te2["maturity"] <= c2]
    print("  train picks <= {:.1f}; early-half unfiltered {:+.3f} -> filtered {:+.3f} (n={} -> {})".format(
        c2, excl_top5(te2["R_cost"]), excl_top5(k2["R_cost"]), len(te2), len(k2)))


if __name__ == "__main__":
    main()
