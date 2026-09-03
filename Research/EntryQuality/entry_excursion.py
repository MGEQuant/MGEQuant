"""
How good is the ENTRY itself? - MAE/MFE study of MarketCoach's signals
======================================================================

THE QUESTION, stated the way it was asked: "why can't we find an entry so precise that once
it fires price does not move against it - enough that I can take a small profit, move the
stop to breakeven, and be risk-free, even if it is only $250?"

That is not a vague wish. It is a measurable property of a signal, and it has never been
measured in this project. Every backtest here scored trades on final R only, which throws
away the entire path - how much heat you took, how fast the trade went your way, whether
breakeven was ever reachable before the stop.

WHAT THIS MEASURES, per trade, walking 1-minute bars from the real next-open fill:
  MAE  maximum ADVERSE excursion in R  - how far underwater before it resolved
  MFE  maximum FAVOURABLE excursion in R - the best it ever offered
  race outcomes - did it reach +0.25R / +0.50R / +0.75R / +1.00R BEFORE hitting -1R?

WHY THE RACE MATTERS MORE THAN MAE ALONE: a "risk-free" workflow needs price to travel far
enough in your favour to justify moving the stop, BEFORE it travels far enough against you
to stop you out. That is a race, and its win rate is exactly the number being asked for.

WHAT THIS CANNOT DO: make an entry that never goes against you. Every entry has adverse
excursion; the question is only how much and how often. If the +0.25R race is won 85% of
the time, the requested workflow is viable. If it is won 55% of the time, it is not, and no
amount of indicator work changes that.

Usage:
    python entry_excursion.py
"""
import os
import sys

import numpy as np
import pandas as pd

MC_DIR = r"F:\Trading Software\MarketCoach\Releases\NQMarketCoachV340SyncLive"
if MC_DIR not in sys.path:
    sys.path.insert(0, MC_DIR)

import backtest_mc_v340 as pipe  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RACE_LEVELS = [0.25, 0.50, 0.75, 1.00]


def build():
    pipe.STOP_BUFFER_TICKS = 8
    pipe.REQUIRE_DAILY = False
    pipe.ENTRY_AT_NEXT_OPEN = True
    pipe.MODEL_OPPORTUNITY_LIMIT = False
    b1 = pipe.load_1min_cached()
    b5 = pipe.resample(b1, "5min")
    if not pipe.sanity_check_timezone(b5):
        raise SystemExit("timezone check failed")
    b5["daily_up"], b5["daily_down"] = pipe.htf_votes(b5["dt"], pipe.resample(b1, "1D"))
    b5["h4_up"], b5["h4_down"] = pipe.htf_votes(b5["dt"], pipe.resample(b1, "4h"))
    b5["m30_up"], b5["m30_down"] = pipe.htf_votes(b5["dt"], pipe.resample(b1, "30min"))
    nm, al, f15 = pipe.session_info(b5["dt"])
    b5["session_name"] = nm
    b5["session_allowed"] = al
    b5["first15"] = f15
    return b1, b5, pipe.run_state_machine(b5), nm


def excursions(signals, bars1m, sessions5):
    """Walk 1-minute bars from the fill and record the path, not just the outcome."""
    t = pd.DatetimeIndex(bars1m["dt"])
    key = t.tz_convert("UTC").tz_localize(None).to_numpy().astype("datetime64[ns]").astype("int64")
    H, L = bars1m["High"].to_numpy(), bars1m["Low"].to_numpy()
    rows = []
    for s in signals:
        risk = abs(s.entry - s.stop)
        if risk <= 0:
            continue
        start = int(key.searchsorted(pd.Timestamp(s.entry_time).as_unit("ns").value, side="right"))
        if start >= len(H):
            continue
        stop_at = min(len(H), start + 20 * 24 * 60)
        mae = mfe = 0.0
        race = {lv: None for lv in RACE_LEVELS}   # True = reached level before -1R
        # The walk must END when the trade ends, or MAE picks up price action from
        # long after the exit. Bound it by the tested structure's own lifetime:
        # stopped at -1R, or TP2 reached at +2R, whichever comes first.
        for j in range(start, stop_at):
            if s.is_long:
                adv = (s.entry - L[j]) / risk
                fav = (H[j] - s.entry) / risk
            else:
                adv = (H[j] - s.entry) / risk
                fav = (s.entry - L[j]) / risk
            hit_stop = adv >= 1.0
            # Within one bar the order is unknowable, so resolve pessimistically:
            # assume the adverse side happened first.
            for lv in RACE_LEVELS:
                if race[lv] is None:
                    if hit_stop:
                        race[lv] = False
                    elif fav >= lv:
                        race[lv] = True
            mae = max(mae, min(adv, 1.0))
            mfe = max(mfe, fav)
            if hit_stop or fav >= 2.0:
                break
        for lv in RACE_LEVELS:
            if race[lv] is None:
                race[lv] = mfe >= lv
        r = {"dt": s.entry_time, "is_long": s.is_long, "mae": mae, "mfe": mfe,
             "session": sessions5[s.bar_idx]}
        for lv in RACE_LEVELS:
            r["won_%.2f" % lv] = race[lv]
        rows.append(r)
    return pd.DataFrame(rows)


def main():
    b1, b5, signals, nm = build()
    df = excursions(signals, b1, nm)
    df["year"] = pd.DatetimeIndex(df.dt).year
    lon = df[df.is_long]

    print("MARKETCOACH ENTRY QUALITY - path of every trade, not just its final R")
    print("  {} signals  ({} long, {} short)\n".format(len(df), len(lon), len(df) - len(lon)))

    print("THE RACE: does price reach +X R BEFORE it reaches -1R (the stop)?")
    print("  (ties inside a bar are resolved AGAINST you, so these are floors)")
    print("{:<16} {:>12} {:>12} {:>12}".format("target", "ALL", "LONG", "SHORT"))
    for lv in RACE_LEVELS:
        c = "won_%.2f" % lv
        print("{:<16} {:>11.1f}% {:>11.1f}% {:>11.1f}%".format(
            "reach +%.2fR" % lv, df[c].mean() * 100,
            lon[c].mean() * 100, df[~df.is_long][c].mean() * 100))

    print("\nMAE - how far underwater did trades go? (1.0 = stopped out)")
    print("  all trades   median {:.2f}R   p75 {:.2f}R   p90 {:.2f}R".format(
        df.mae.median(), df.mae.quantile(.75), df.mae.quantile(.90)))
    win = df[df.mfe >= 1.0]
    print("  trades that eventually reached +1R first dug to:")
    print("     median {:.2f}R   p75 {:.2f}R   p90 {:.2f}R   max {:.2f}R".format(
        win.mae.median(), win.mae.quantile(.75), win.mae.quantile(.90), win.mae.max()))
    print("  share of eventual +1R winners that NEVER went more than 0.25R against: {:.1f}%".format(
        (win.mae <= 0.25).mean() * 100))
    print("  share that never went more than 0.50R against: {:.1f}%".format(
        (win.mae <= 0.50).mean() * 100))

    print("\nWHAT A 'SCALP THEN BREAKEVEN' PLAN WOULD PRODUCE")
    print("  take profit at +X R on the whole position, costs included (~0.02R):")
    print("{:<14} {:>9} {:>12} {:>14}".format("take at", "hit rate", "avg_R", "per $250 risk"))
    for lv in RACE_LEVELS:
        c = "won_%.2f" % lv
        p = df[c].mean()
        avg = p * lv - (1 - p) * 1.0 - 0.02
        print("{:<14} {:>8.1f}% {:>+12.3f} {:>+14.0f}".format(
            "+%.2fR" % lv, p * 100, avg, avg * 250))
    print("  (for comparison, the tested TP1/TP2 structure averages +0.189R = +$47 per $250)")

    print("\nIS ENTRY QUALITY BETTER ANYWHERE? (+0.50R race win rate)")
    print("{:<20} {:>6} {:>12} {:>12}".format("slice", "n", "win +0.50R", "median MAE"))
    for label, g in [("ALL", df), ("LONG", lon), ("SHORT", df[~df.is_long])] + \
                    [(s, df[df.session == s]) for s in ["NY", "LONDON", "ASIA"]]:
        if len(g) == 0:
            continue
        print("{:<20} {:>6} {:>11.1f}% {:>12.2f}".format(
            label, len(g), g["won_0.50"].mean() * 100, g.mae.median()))

    out = os.path.join(HERE, "entry_excursion_trades.csv")
    df.to_csv(out, index=False)
    print("\nPer-trade paths: {}".format(out))


if __name__ == "__main__":
    main()
