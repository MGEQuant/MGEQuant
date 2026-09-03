"""
NQ empirical characterisation - what does this instrument actually DO?
======================================================================

Deliberately NOT strategy-first. Every previous effort in this fleet started with a
concept (ORB, exhaustion fade, EMA retest, compression snapback, ICT levels...) and asked
whether NQ obliges. Most did not. This inverts it: measure NQ's own behaviour first, then
build only what the measurements support.

DISCIPLINE. Exploration touches TRAIN ONLY (2020-12 .. 2023-12). 2024-01 onward is held
out and is not read by this script at all - it does not even get loaded into the frames
being measured. Many things are examined here, so anything that looks good is a
HYPOTHESIS, not a result; it has to survive the untouched years before it means anything.

Timezone: the cached bars are Pacific (validated pipeline); converted to America/New_York
here because NQ's session structure is defined in ET and hour-of-day results are only
interpretable that way.

Usage:
    python explore_nq.py
"""
import sys

import numpy as np
import pandas as pd

MC_DIR = r"F:\Trading Software\MarketCoach\Releases\NQMarketCoachV340SyncLive"
if MC_DIR not in sys.path:
    sys.path.insert(0, MC_DIR)

import backtest_mc_v340 as pipe  # noqa: E402  (data pipeline only)

TRAIN_END = pd.Timestamp("2024-01-01", tz="America/New_York")
POINT_VALUE = 20.0


def load_train():
    bars = pipe.load_1min_cached().copy()
    bars["dt"] = bars["dt"].dt.tz_convert("America/New_York")
    bars = bars[bars["dt"] < TRAIN_END].reset_index(drop=True)
    return bars


def session_of(dt):
    """Futures session date: 18:00 ET starts the next session."""
    return np.where(dt.dt.hour >= 18, dt.dt.date + pd.Timedelta(days=1), dt.dt.date)


def hdr(title):
    print("\n" + "=" * 88)
    print(title)
    print("=" * 88)


def main():
    b = load_train()
    print("TRAIN ONLY: {:,} 1-min bars, {} .. {}".format(
        len(b), b["dt"].min(), b["dt"].max()))
    print("2024-01-01 onward is held out and not loaded.")

    b["ret"] = b["Close"].diff()
    b["minute"] = b["dt"].dt.hour * 60 + b["dt"].dt.minute
    b["hour"] = b["dt"].dt.hour
    b["dow"] = b["dt"].dt.dayofweek
    b["sess"] = session_of(b["dt"])

    # ---------------------------------------------------------------- 1. drift by hour
    hdr("1. WHERE DOES NQ ACTUALLY MOVE? mean point drift per ET hour (train)")
    g = b.groupby("hour")["ret"].agg(["sum", "mean", "count", "std"])
    g["pts_per_day"] = g["sum"] / b["sess"].nunique()
    g["t"] = g["mean"] / (g["std"] / np.sqrt(g["count"]))
    print("{:>5} {:>12} {:>12} {:>9} {:>8}".format("hour", "total pts", "pts/day", "n bars", "t-stat"))
    for h, r in g.iterrows():
        mark = "  <<<" if abs(r["t"]) > 2 else ""
        print("{:>5} {:>12,.0f} {:>12.3f} {:>9,} {:>8.2f}{}".format(
            h, r["sum"], r["pts_per_day"], int(r["count"]), r["t"], mark))

    # ------------------------------------------------- 2. overnight vs RTH decomposition
    hdr("2. OVERNIGHT vs REGULAR HOURS - where does the drift live?")
    day = b.groupby("sess").agg(
        first=("Close", "first"), last=("Close", "last"))
    rth = b[(b["minute"] >= 570) & (b["minute"] < 960)].groupby("sess")["Close"]
    rth_agg = rth.agg(["first", "last"]).rename(columns={"first": "r_open", "last": "r_close"})
    j = day.join(rth_agg).dropna()
    j["overnight"] = j["r_open"] - j["first"]     # session start -> RTH open
    j["rth"] = j["r_close"] - j["r_open"]         # RTH open -> RTH close
    j["total"] = j["last"] - j["first"]
    n = len(j)
    print("  sessions: {}".format(n))
    for name in ["overnight", "rth", "total"]:
        s = j[name]
        t = s.mean() / (s.std() / np.sqrt(n))
        print("  {:<10} total={:>10,.0f} pts   mean/session={:>8.3f}   t={:>6.2f}   ${:>10,.0f}".format(
            name, s.sum(), s.mean(), t, s.sum() * POINT_VALUE))
    print("  -> a positive, significant leg here is a real directional bias to exploit;")
    print("     a flat one says do not bother trading that window directionally.")

    # ------------------------------------------- 3. momentum vs mean reversion by horizon
    hdr("3. MOMENTUM OR MEAN REVERSION? lag-1 autocorrelation of returns by bar size")
    print("{:>10} {:>10} {:>12} {:>10}".format("bar", "n", "autocorr", "t-stat"))
    for rule, label in [("5min", "5m"), ("15min", "15m"), ("30min", "30m"),
                        ("60min", "1h"), ("1D", "daily")]:
        r = pipe.resample(b.rename(columns={"dt": "dt"}), rule)
        ret = r["Close"].diff().dropna()
        if len(ret) < 30:
            continue
        ac = ret.autocorr(lag=1)
        t = ac * np.sqrt(len(ret))
        note = "  momentum" if t > 2 else ("  reversion" if t < -2 else "  (flat)")
        print("{:>10} {:>10,} {:>12.4f} {:>10.2f}{}".format(label, len(ret), ac, t, note))

    # ------------------------------------------------------------ 4. day-of-week effect
    hdr("4. DAY OF WEEK - mean session move in points (train)")
    j2 = j.copy()
    j2["dow"] = pd.to_datetime(pd.Series(j2.index)).dt.dayofweek.to_numpy()
    print("{:>10} {:>8} {:>12} {:>12} {:>8}".format("day", "n", "overnight", "rth", "t(total)"))
    for d, gg in j2.groupby("dow"):
        if len(gg) < 20:
            continue
        t = gg["total"].mean() / (gg["total"].std() / np.sqrt(len(gg)))
        print("{:>10} {:>8} {:>12.2f} {:>12.2f} {:>8.2f}".format(
            ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][d], len(gg),
            gg["overnight"].mean(), gg["rth"].mean(), t))

    # ------------------------------------------------- 5. conditional follow-through
    hdr("5. FOLLOW-THROUGH - given the RTH session direction, what does the NEXT overnight do?")
    j3 = j.copy()
    j3["next_on"] = j3["overnight"].shift(-1)
    j3 = j3.dropna(subset=["next_on"])
    up = j3[j3["rth"] > 0]["next_on"]
    dn = j3[j3["rth"] <= 0]["next_on"]
    for label, s in [("after an UP RTH day", up), ("after a DOWN RTH day", dn)]:
        t = s.mean() / (s.std() / np.sqrt(len(s)))
        print("  {:<24} n={:>4}  next overnight mean={:+8.3f} pts  t={:+6.2f}".format(
            label, len(s), s.mean(), t))

    # -------------------------------------------------------- 6. volatility by hour
    hdr("6. VOLATILITY BY HOUR - mean 5-min true range in ticks (for stop sizing)")
    r5 = pipe.resample(b, "5min")
    r5["hour"] = r5["dt"].dt.hour
    r5["rng"] = (r5["High"] - r5["Low"]) / 0.25
    v = r5.groupby("hour")["rng"].mean()
    for h in range(24):
        if h in v.index:
            print("  {:>02}:00  {:>6.1f} ticks  {}".format(h, v[h], "#" * int(v[h] / 2)))


if __name__ == "__main__":
    main()
