"""
The decisive test of the trend-maturity idea: does it separate winners from losers on
MarketCoach's OWN proven trade set (long-only, n=168, excl_top5% +0.206)?

The from-scratch engine's own maturity sweep was spiky rather than monotonic, which this
project treats as a noise signature. But that engine is itself weak (excl_top5% +0.008),
so a filter could look bad simply because the base is bad. This removes that confound
entirely: take the 168 trades that ARE validated, attach each trade's trend-maturity
reading at signal time, and ask directly whether maturity sorts them.

No refitting, no sweep, no state-machine interaction - just: are stretched-trend entries
worse than fresh-trend ones? If the idea has any substance it must show up here.

Usage:
    python maturity_on_marketcoach.py
"""
import sys

import numpy as np
import pandas as pd

MC_DIR = r"F:\Trading Software\MarketCoach\Releases\NQMarketCoachV340SyncLive"
if MC_DIR not in sys.path:
    sys.path.insert(0, MC_DIR)

import backtest_mc_v340 as pipe  # noqa: E402
from backtest_trend_maturity import daily_maturity, excl_top5  # noqa: E402

pipe.STOP_BUFFER_TICKS = 8
pipe.REQUIRE_DAILY = False


def main():
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

    pipe.ENTRY_AT_NEXT_OPEN = True          # the live Strategy's real fill
    pipe.MODEL_OPPORTUNITY_LIMIT = False    # proven inert
    signals = pipe.run_state_machine(bars5)
    risk_by_time = {s.entry_time: abs(s.entry - s.stop) for s in signals}
    mat_by_time = {s.entry_time: bars5["maturity"].to_numpy()[s.bar_idx] for s in signals}
    df = pipe.apply_costs(pipe.resolve_signals(signals, bars1m), risk_by_time)
    df["maturity"] = df["dt"].map(mat_by_time)
    lon = df[df["is_long"]].dropna(subset=["maturity"]).copy()

    print("MarketCoach long-only trade set, trend-maturity attached")
    print("  n={}  excl_top5%(cost)={:+.3f}  (maturity available on {} of {})".format(
        len(lon), excl_top5(lon["R_cost"]), len(lon), (df["is_long"]).sum()))
    print("  maturity: min={:.2f} p25={:.2f} median={:.2f} p75={:.2f} max={:.2f}".format(
        lon["maturity"].min(), lon["maturity"].quantile(.25), lon["maturity"].median(),
        lon["maturity"].quantile(.75), lon["maturity"].max()))

    print("\nDoes maturity sort the trades? (quartiles, low = fresh trend, high = stretched)")
    print("{:<22} {:>5} {:>7} {:>9} {:>11}".format("bucket", "n", "win%", "avg_R", "excl_top5%"))
    lon["q"] = pd.qcut(lon["maturity"], 4, labels=["Q1 fresh", "Q2", "Q3", "Q4 stretched"])
    for q, g in lon.groupby("q", observed=True):
        print("{:<22} {:5d} {:6.1f}% {:+9.3f} {:+11.3f}".format(
            str(q), len(g), (g["R"] > 0).mean() * 100, g["R_cost"].mean(), excl_top5(g["R_cost"])))

    print("\nCeiling test - keep only trades at or below each maturity level")
    print("{:<22} {:>5} {:>7} {:>9} {:>11} {:>7}".format(
        "keep maturity <=", "n", "win%", "avg_R", "excl_top5%", "yrs+"))
    print("{:<22} {:5d} {:6.1f}% {:+9.3f} {:+11.3f}   {}/{}".format(
        "no filter", len(lon), (lon["R"] > 0).mean() * 100, lon["R_cost"].mean(),
        excl_top5(lon["R_cost"]),
        int((lon.groupby("year")["R_cost"].mean() > 0).sum()), lon["year"].nunique()))
    for cap in [4.0, 3.5, 3.0, 2.5, 2.0, 1.5]:
        g = lon[lon["maturity"] <= cap]
        if g.empty:
            continue
        yrs = g.groupby("year")["R_cost"].mean()
        print("{:<22} {:5d} {:6.1f}% {:+9.3f} {:+11.3f}   {}/{}".format(
            "{:.1f}".format(cap), len(g), (g["R"] > 0).mean() * 100, g["R_cost"].mean(),
            excl_top5(g["R_cost"]), int((yrs > 0).sum()), len(yrs)))

    # Spearman without scipy: Pearson on ranks.
    rho = lon["maturity"].rank().corr(lon["R_cost"].rank())
    print("\nSpearman rank correlation, maturity vs outcome: {:+.4f}".format(rho))

    def welch(a, b):
        d = a.mean() - b.mean()
        se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
        return d, se, (d / se if se else float("nan"))

    print("\nPRE-SPECIFIED HYPOTHESIS: stretched trends underperform")
    cut = lon["maturity"].quantile(0.75)
    q4 = lon[lon["maturity"] > cut]["R_cost"]
    rest = lon[lon["maturity"] <= cut]["R_cost"]
    d, se, t = welch(rest, q4)
    print("  rest (n={}) minus stretched quartile (n={}): {:+.3f}R  SE={:.3f}  t={:+.2f}".format(
        len(rest), len(q4), d, se, t))
    print("  95% CI: [{:+.3f}, {:+.3f}]  -> {}".format(
        d - 1.96 * se, d + 1.96 * se,
        "excludes zero" if abs(t) > 1.96 else "INCLUDES ZERO - not significant"))

    print("\nMULTIPLE-COMPARISONS CHECK on the ceiling sweep (6 ceilings tested)")
    best, best_cap = None, None
    for cap in [4.0, 3.5, 3.0, 2.5, 2.0, 1.5]:
        e = excl_top5(lon[lon["maturity"] <= cap]["R_cost"])
        if best is None or e > best:
            best, best_cap = e, cap
    kept = lon[lon["maturity"] <= best_cap]["R_cost"]
    dropped = lon[lon["maturity"] > best_cap]["R_cost"]
    d, se, t = welch(kept, dropped)
    print("  best cell: maturity<={:.1f}  excl_top5%={:+.3f}  vs unfiltered {:+.3f}".format(
        best_cap, best, excl_top5(lon["R_cost"])))
    print("  kept (n={}) minus dropped (n={}): {:+.3f}R  SE={:.3f}  t={:+.2f}".format(
        len(kept), len(dropped), d, se, t))
    print("  Bonferroni threshold for 6 tests: |t| > 2.64  ->  {}".format(
        "SURVIVES" if abs(t) > 2.64 else "does NOT survive"))

    print("\nYEAR BY YEAR at the best ceiling vs unfiltered (avg_R with costs)")
    ya, na = lon.groupby("year")["R_cost"].mean(), lon.groupby("year").size()
    f = lon[lon["maturity"] <= best_cap]
    yb, nb = f.groupby("year")["R_cost"].mean(), f.groupby("year").size()
    print("{:>6} {:>8} {:>8} {:>11} {:>11}".format("year", "n base", "n filt", "base", "filtered"))
    for y in sorted(set(ya.index) | set(yb.index)):
        print("{:>6} {:>8} {:>8} {:>+11.3f} {:>+11.3f}".format(
            y, na.get(y, 0), nb.get(y, 0), ya.get(y, float("nan")), yb.get(y, float("nan"))))


if __name__ == "__main__":
    main()
