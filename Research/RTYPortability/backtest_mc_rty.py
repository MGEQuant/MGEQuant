"""
MarketCoach V3.4.1 on RTY - does the edge transfer to a second instrument?
=========================================================================

WHY THIS IS THE STRONGEST TEST AVAILABLE. Every result in this fleet is NQ-only, so every
result carries the same unanswerable doubt: is this an edge, or is it seven years of
curve-fitting to one instrument? Running the SAME rules with FROZEN parameters on a
different market answers that directly. It is a harder test than any walk-forward, because
nothing here was ever tuned on this data.

THE RULE FOR THIS SCRIPT: nothing may be optimised. Parameters are exactly what NQ
validated - StopBufferTicks=8, RequireDailyBias=false, everything else at its default. If
RTY needs different settings to work, that is a FAIL, not a finding.

CONTRACT TRANSLATION. RTY is $50/point with a 0.10 tick, so a tick is worth $5.00 - exactly
the same as NQ ($20/point, 0.25 tick). That is a genuinely lucky coincidence: every
tick-denominated parameter transfers with its DOLLAR meaning intact.
    StopBufferTicks 8   -> $40 on both
    ATR floor 20 ticks  -> $100 of ATR on both
    risk floor 8 ticks  -> $40 on both
Cost model transfers unchanged for the same reason.

DATA CAVEAT, stated before any result: the RTY export is patchier than NQ's. Whole quarters
are missing (roughly Mar-Sep 2021, Jun-Sep 2022, most of 2023 H1). Coverage is reported
below and must be read alongside any verdict - a thin sample is a thin sample.

Usage:
    python backtest_mc_rty.py
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

# --- instrument swap: RTY -------------------------------------------------------------
pipe.DATA_DIR = r"C:\Users\maric\Documents\NinjaTrader 8\export\RTY"
pipe.SKIP_FILES = set()
pipe.TICK_SIZE = 0.10
pipe.POINT_VALUE = 50.0
pipe.CACHE_1MIN = os.path.join(HERE, "_bars1m_cache_rty_pacific.pkl")

# --- the NQ-validated configuration, FROZEN -------------------------------------------
pipe.STOP_BUFFER_TICKS = 8
pipe.REQUIRE_DAILY = False
pipe.ENTRY_AT_NEXT_OPEN = True       # the real Calculate.OnBarClose fill
pipe.MODEL_OPPORTUNITY_LIMIT = False  # proven inert on NQ


def excl_top5(col):
    if len(col) == 0:
        return float("nan")
    k = max(1, int(len(col) * 0.05))
    return col.sort_values(ascending=False).iloc[k:].mean()


HEADER = "{:<26} {:>5} {:>7} {:>8} {:>9} {:>11} {:>7}".format(
    "scope", "n", "win%", "avg_R", "median_R", "excl_top5%", "yrs+")


def line(label, df):
    if df.empty:
        return "{:<26} {:>5}      -        -         -           -       -".format(label, 0)
    yrs = df.groupby("year")["R_cost"].mean()
    return "{:<26} {:5d} {:6.1f}% {:+8.3f} {:+9.3f} {:+11.3f}   {}/{}".format(
        label, len(df), (df["R"] > 0).mean() * 100, df["R_cost"].mean(),
        df["R_cost"].median(), excl_top5(df["R_cost"]),
        int((yrs > 0).sum()), len(yrs))


def main():
    bars1m = pipe.load_1min_cached()
    bars5 = pipe.resample(bars1m, "5min")

    days = pd.Series(bars1m["dt"].dt.date.unique())
    print("RTY DATA COVERAGE")
    print("  {:,} 1-min bars, {:,} 5-min bars".format(len(bars1m), len(bars5)))
    print("  {} .. {}   ({} distinct trading days)".format(
        bars1m["dt"].min().date(), bars1m["dt"].max().date(), len(days)))
    by_year = bars1m.groupby(bars1m["dt"].dt.year)["dt"].agg(
        bars="size", days=lambda s: s.dt.date.nunique())
    print("  by year: " + "  ".join("{}:{}d".format(y, r["days"]) for y, r in by_year.iterrows()))
    print("  (NQ for comparison: 1,578,647 bars over ~1,430 days)")

    if not pipe.sanity_check_timezone(bars5):
        print("  TIMEZONE CHECK FAILED - stopping, results would be meaningless.")
        return
    print("  timezone check PASSED\n")

    bars5["daily_up"], bars5["daily_down"] = pipe.htf_votes(bars5["dt"], pipe.resample(bars1m, "1D"))
    bars5["h4_up"], bars5["h4_down"] = pipe.htf_votes(bars5["dt"], pipe.resample(bars1m, "4h"))
    bars5["m30_up"], bars5["m30_down"] = pipe.htf_votes(bars5["dt"], pipe.resample(bars1m, "30min"))
    name, allowed, first15 = pipe.session_info(bars5["dt"])
    bars5["session_name"] = name
    bars5["session_allowed"] = allowed
    bars5["first15"] = first15

    signals = pipe.run_state_machine(bars5)
    risk = {s.entry_time: abs(s.entry - s.stop) for s in signals}
    sess = {s.entry_time: name[s.bar_idx] for s in signals}
    df = pipe.apply_costs(pipe.resolve_signals(signals, bars1m), risk)
    if df.empty:
        print("No trades produced on RTY.")
        return
    df["session"] = df["dt"].map(sess)

    print("MARKETCOACH ON RTY - NQ parameters frozen, nothing re-tuned")
    print("(NQ reference: LONG n=168 win 62.5% avg_R +0.267 excl_top5% +0.206, 7/7 years)")
    print(HEADER)
    print(line("COMBINED", df))
    print(line("LONG", df[df.is_long]))
    print(line("SHORT", df[~df.is_long]))

    print("\nBY YEAR (combined, avg_R with costs)")
    for y, g in df.groupby("year"):
        print("  {}: n={:3d}  avg_R={:+.3f}  excl_top5%={:+.3f}".format(
            y, len(g), g["R_cost"].mean(), excl_top5(g["R_cost"])))

    print("\nBY SESSION")
    print(HEADER)
    for s in ["NY", "LONDON", "ASIA"]:
        print(line(s, df[df.session == s]))
        print(line("  " + s + " long", df[(df.session == s) & df.is_long]))

    print("\nR distribution (should be exactly -1.0 / +0.5 / +1.5): {}".format(
        dict(df.R.round(2).value_counts())))
    print("Trades per month: {:.2f}   (NQ long-only was 2.48)".format(
        len(df) / max(1, (df.dt.max() - df.dt.min()).days / 30.4)))

    out = os.path.join(HERE, "mc_rty_trades.csv")
    df.to_csv(out, index=False)
    print("\nTrade log: {}".format(out))


if __name__ == "__main__":
    main()
