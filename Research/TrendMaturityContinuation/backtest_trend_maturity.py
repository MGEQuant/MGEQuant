"""
MGE Trend Maturity Continuation - from-scratch long-only NQ trend-continuation engine.
=======================================================================================

WHAT THIS IS. Not a new concept pulled from nowhere. It is MarketCoach V3.4.1 distilled
down to the parts the fleet audit actually proved carry the edge, plus exactly ONE new
filter aimed at the one failure mode that was diagnosed but never addressed.

WHAT WAS KEPT (each with the evidence that earned it):
  - Long-only. Four independent instances of long>short in this fleet (QAX, MarketCoach,
    Trend Momentum Breakout, TSI Divergence).
  - H4 + M30 + EMA + VWAP alignment, with NO daily bias. Dropping RequireDailyBias took
    MarketCoach from n=128 to n=298 AND improved excl_top5% - it lagged during regime
    transitions.
  - Pullback-then-confirm sequencing, with the dead-code bug fixed from the start
    (confirmation is evaluated against the pullback state as it stood BEFORE this bar's
    own pullback event).
  - Confirmed-swing stop with an 8-tick buffer, risk floored at 8 ticks.
  - Two-leg exit: TP1 +1R on half then stop to breakeven, TP2 +2R on the rest.
  - Entry at the NEXT BAR OPEN. Verified 2026-09-02 to be what a Calculate.OnBarClose
    strategy actually fills at, and it is very slightly BETTER than the Close[0] model.

WHAT WAS DELIBERATELY DROPPED:
  - The whole 8-point "continuation" vote. Diagnostics proved it never independently
    fires - every signal in 7 years qualified via the expansion path. Dead weight.
  - The 10-point composite score. Replaced with the explicit conditions it was really
    gating, so the rules are legible instead of hidden behind a threshold.
  - The opportunity lifecycle / MaximumSignalsPerOpportunity limiter. Proven 2026-09-02
    to block 0 signals in 5.7 years - it cannot bind given cooldown 10 vs expiry 12.
  - RequireDailyBias, per above.

THE ONE NEW IDEA - TREND MATURITY:
  MarketCoach's exhaustionScore is a few-bar extension-from-EMA21 measure. The 2021
  diagnosis found 5 straight long losses into NQ's all-time-high topping process, every
  one with a LOW exhaustion score (1.1-3.1 against a 6.5 ceiling). The filter was not
  broken; it was blind by construction - it has no concept of a multi-month trend being
  old. This adds that missing dimension explicitly:

      maturity = (Close - SMA(daily, 50)) / ATR(daily, 14)

  i.e. how many daily-ATRs price sits above its own multi-month mean, using only
  COMPLETED daily bars. Reject longs above a ceiling: do not buy continuation when price
  is historically stretched against its own baseline.

HONESTY WARNING ON THAT FILTER: it was designed after looking at 2021's losses, and 2021
is inside the test set. That is textbook curve-fitting risk. It is therefore evaluated
with 2021 EXCLUDED as the primary test - if it only helps 2021, it is a patch, not an
edge. See the ex-2021 block in the output.

DATA PIPELINE: deliberately reuses the validated MarketCoach pipeline (UTC->Pacific
stitching, front-month by daily volume, Wilder ATR, confirmed-swing fractal, HTF
last-completed-bar alignment, 1-minute exit resolution, cost model). Rewriting it from
scratch would only add a fresh chance of a different bug - the lesson of Pass Criteria
item 10.

Usage:
    python backtest_trend_maturity.py            # core + maturity sweep
    python backtest_trend_maturity.py --core     # core only, no maturity filter
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

MC_DIR = r"F:\Trading Software\MarketCoach\Releases\NQMarketCoachV340SyncLive"
if MC_DIR not in sys.path:
    sys.path.insert(0, MC_DIR)

import backtest_mc_v340 as pipe  # noqa: E402  (validated data pipeline only)

TICK_SIZE = 0.25
POINT_VALUE = 20.0
COMMISSION_RT = 4.20
SLIPPAGE_TICKS_PER_SIDE = 1.0

FAST_EMA_LEN = 21
SLOW_EMA_LEN = 50
ATR_PERIOD = 14
SWING_STRENGTH = 5
ATR_MIN_TICKS = 20
MAX_EXTENSION_ATR = 1.75
STOP_BUFFER_TICKS = 8
MIN_RISK_TICKS = 8
TARGET1_R = 1.0
TARGET2_R = 2.0
MIN_BARS_BETWEEN_SIGNALS = 10
MAX_SIGNALS_PER_DAY = 5

DAILY_SMA_LEN = 50
DAILY_ATR_LEN = 14


class Signal:
    __slots__ = ("bar_idx", "entry_time", "is_long", "entry", "stop", "tp1", "tp2", "maturity")

    def __init__(self, bar_idx, entry_time, is_long, entry, stop, tp1, tp2, maturity):
        self.bar_idx = bar_idx
        self.entry_time = entry_time
        self.is_long = is_long
        self.entry = entry
        self.stop = stop
        self.tp1 = tp1
        self.tp2 = tp2
        self.maturity = maturity


def daily_maturity(bars5_dt, bars_daily):
    """(Close - SMA50) / ATR14 on completed daily bars, aligned onto the 5-minute index.

    merge_asof backward + close-labelled daily bars means a daily value is only visible
    after that day has actually closed, so there is no lookahead.
    """
    d = bars_daily.copy()
    sma = d["Close"].rolling(DAILY_SMA_LEN).mean()
    atr = pipe.atr_wilder(d, DAILY_ATR_LEN)
    val = ((d["Close"] - sma) / atr).to_numpy()
    aligned = pipe.merge_asof_bool(bars5_dt, d["dt"], val)
    return pd.to_numeric(pd.Series(aligned), errors="coerce").to_numpy()


def run_engine(bars5, maturity_max=None):
    n = len(bars5)
    Open = bars5["Open"].to_numpy()
    High = bars5["High"].to_numpy()
    Low = bars5["Low"].to_numpy()
    Close = bars5["Close"].to_numpy()
    dt = bars5["dt"]
    date_arr = dt.dt.date.to_numpy()

    ema_fast = bars5["Close"].ewm(span=FAST_EMA_LEN, adjust=False).mean().to_numpy()
    ema_slow = bars5["Close"].ewm(span=SLOW_EMA_LEN, adjust=False).mean().to_numpy()
    atr = pipe.atr_wilder(bars5, ATR_PERIOD).to_numpy()
    swing_high, swing_low = pipe.confirmed_swings(High, Low, SWING_STRENGTH)

    h4_up = bars5["h4_up"].to_numpy()
    m30_up = bars5["m30_up"].to_numpy()
    sess_allowed = bars5["session_allowed"].to_numpy()
    first15 = bars5["first15"].to_numpy()
    maturity = bars5["maturity"].to_numpy()

    # Session VWAP, reset daily - same construction as the source indicator.
    typical = (High + Low + Close) / 3.0
    vol = np.maximum(1.0, bars5["Volume"].to_numpy())
    vwap = np.empty(n)
    cum_pv = cum_v = 0.0
    prev_day = None
    for i in range(n):
        if date_arr[i] != prev_day:
            prev_day = date_arr[i]
            cum_pv = cum_v = 0.0
        cum_pv += typical[i] * vol[i]
        cum_v += vol[i]
        vwap[i] = cum_pv / cum_v if cum_v > 0 else Close[i]

    signals = []
    audit = {"aligned": 0, "location_ok": 0, "pullback_armed": 0, "confirmed": 0,
             "maturity_rejects": 0, "cooldown_rejects": 0, "daily_cap_rejects": 0,
             "no_swing_rejects": 0, "gap_rejects": 0, "risk_rejects": 0}

    pullback_seen = False
    pullback_bar = -9999
    last_signal_bar = -9999
    signals_today = 0
    cur_day = None
    min_bars = max(SLOW_EMA_LEN + 5, SWING_STRENGTH * 2 + 5, 80)

    for i in range(min_bars, n - 1):
        if date_arr[i] != cur_day:
            cur_day = date_arr[i]
            signals_today = 0
            last_signal_bar = -9999
            pullback_seen = False
            pullback_bar = -9999

        atr_i = atr[i]
        if not np.isfinite(atr_i) or atr_i <= 0:
            continue

        aligned = (bool(h4_up[i]) and bool(m30_up[i])
                   and Close[i] > ema_fast[i] and ema_fast[i] > ema_slow[i]
                   and ema_fast[i] >= ema_fast[i - 1] and Close[i] > vwap[i])
        if not aligned:
            pullback_seen = False          # trend broke: disarm
            continue
        audit["aligned"] += 1

        extension_atr = abs(Close[i] - ema_fast[i]) / atr_i
        volatility_ok = atr_i >= TICK_SIZE * ATR_MIN_TICKS
        location_ok = extension_atr <= MAX_EXTENSION_ATR
        if location_ok and volatility_ok:
            audit["location_ok"] += 1

        # --- confirmation is judged on the pullback state BEFORE this bar updates it ---
        armed = pullback_seen and i > pullback_bar
        bullish_bos = (not np.isnan(swing_high[i]) and Close[i] > swing_high[i]
                       and Close[i - 1] <= swing_high[i])
        strong_bull = (Close[i] > Open[i] and (Close[i] - Open[i]) > atr_i * 0.35
                       and Close[i] >= High[i] - atr_i * 0.25)
        bullish_reaction = Close[i] > Open[i] and Low[i] <= ema_fast[i] and Close[i] > ema_fast[i]
        confirmed = (armed and bullish_reaction and (bullish_bos or strong_bull)
                     and Close[i] > High[i - 1] and location_ok and volatility_ok
                     and sess_allowed[i] and not first15[i])

        # --- now apply this bar's own pullback event, for future bars ---
        if Low[i] <= ema_fast[i] or extension_atr <= 0.55 or Close[i] < Open[i]:
            pullback_seen = True
            pullback_bar = i
        if not armed:
            audit["pullback_armed"] += 1 if pullback_seen else 0

        if not confirmed:
            continue
        audit["confirmed"] += 1

        if maturity_max is not None:
            mat = maturity[i]
            if not np.isfinite(mat) or mat > maturity_max:
                audit["maturity_rejects"] += 1
                continue

        if i - last_signal_bar < MIN_BARS_BETWEEN_SIGNALS:
            audit["cooldown_rejects"] += 1
            continue
        if signals_today >= MAX_SIGNALS_PER_DAY:
            audit["daily_cap_rejects"] += 1
            continue
        if np.isnan(swing_low[i]):
            audit["no_swing_rejects"] += 1
            continue
        if (dt.iloc[i + 1] - dt.iloc[i]) != pd.Timedelta(minutes=5):
            audit["gap_rejects"] += 1
            continue

        entry = float(Open[i + 1])                       # real Calculate.OnBarClose fill
        stop_raw = float(swing_low[i]) - STOP_BUFFER_TICKS * TICK_SIZE
        risk = max(entry - stop_raw, TICK_SIZE * MIN_RISK_TICKS)
        if risk <= 0:
            audit["risk_rejects"] += 1
            continue
        stop = entry - risk
        signals.append(Signal(i, dt.iloc[i], True, entry, stop,
                              entry + risk * TARGET1_R, entry + risk * TARGET2_R,
                              float(maturity[i]) if np.isfinite(maturity[i]) else np.nan))
        last_signal_bar = i
        signals_today += 1
        pullback_seen = False

    return signals, audit


def resolve(signals, bars1m):
    trades = pipe.resolve_signals(signals, bars1m)
    risk_by_time = {s.entry_time: abs(s.entry - s.stop) for s in signals}
    mat_by_time = {s.entry_time: s.maturity for s in signals}
    df = pipe.apply_costs(trades, risk_by_time)
    if not df.empty:
        df["maturity"] = df["entry_time"].map(mat_by_time) if "entry_time" in df.columns \
            else [mat_by_time.get(t, np.nan) for t in df["dt"]]
    return df


def excl_top5(col):
    if len(col) == 0:
        return float("nan")
    k = max(1, int(len(col) * 0.05))
    return col.sort_values(ascending=False).iloc[k:].mean()


HEADER = "{:<28} {:>5} {:>7} {:>8} {:>9} {:>11} {:>7}".format(
    "scope", "n", "win%", "avg_R", "median_R", "excl_top5%", "yrs+")


def line(label, df):
    if df.empty:
        return "{:<28} {:>5}     -        -         -           -       -".format(label, 0)
    yrs = df.groupby("year")["R_cost"].mean()
    return "{:<28} {:5d} {:6.1f}% {:+8.3f} {:+9.3f} {:+11.3f}   {}/{}".format(
        label, len(df), (df["R"] > 0).mean() * 100, df["R_cost"].mean(),
        df["R_cost"].median(), excl_top5(df["R_cost"]),
        int((yrs > 0).sum()), len(yrs))


def prepare():
    bars1m = pipe.load_1min_cached()
    bars5 = pipe.resample(bars1m, "5min")
    if not pipe.sanity_check_timezone(bars5):
        raise SystemExit("timezone sanity check failed")
    bars5["h4_up"], _ = pipe.htf_votes(bars5["dt"], pipe.resample(bars1m, "4h"))
    bars5["m30_up"], _ = pipe.htf_votes(bars5["dt"], pipe.resample(bars1m, "30min"))
    name, allowed, first15 = pipe.session_info(bars5["dt"])
    bars5["session_allowed"] = allowed
    bars5["first15"] = first15
    bars5["maturity"] = daily_maturity(bars5["dt"], pipe.resample(bars1m, "1D"))
    return bars1m, bars5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", action="store_true", help="core only, skip the maturity sweep")
    args = ap.parse_args()

    bars1m, bars5 = prepare()
    print("5m bars: {:,}   maturity coverage: {:.1f}%".format(
        len(bars5), np.isfinite(bars5["maturity"].to_numpy()).mean() * 100))

    sig, audit = run_engine(bars5, maturity_max=None)
    base = resolve(sig, bars1m)
    print("\nAUDIT (core, no maturity filter)")
    for k, v in audit.items():
        print("  {}: {:,}".format(k, v))
    print("\nCORE ENGINE - long only, no daily bias, expansion path only, next-open fill")
    print(HEADER)
    print(line("CORE", base))
    if not base.empty:
        print("\n  by year: " + "  ".join(
            "{}:{:+.3f}(n={})".format(y, r["R_cost"], int(r["n"]))
            for y, r in base.groupby("year").agg(R_cost=("R_cost", "mean"),
                                                 n=("R_cost", "size")).iterrows()))
        print("  maturity at signal time: min={:.2f} median={:.2f} p90={:.2f} max={:.2f}".format(
            base["maturity"].min(), base["maturity"].median(),
            base["maturity"].quantile(0.9), base["maturity"].max()))
    if args.core:
        return

    print("\n" + "=" * 96)
    print("MATURITY FILTER SWEEP - reject longs when price is > X daily-ATRs above its 50-day mean")
    print("=" * 96)
    print(HEADER)
    print(line("no filter", base))
    results = {}
    for cap in [4.0, 3.5, 3.0, 2.5, 2.0, 1.5, 1.0]:
        s, _ = run_engine(bars5, maturity_max=cap)
        d = resolve(s, bars1m)
        results[cap] = d
        print(line("maturity <= {:.1f}".format(cap), d))

    print("\n" + "=" * 96)
    print("HONESTY CHECK - does it help anywhere OTHER than 2021?")
    print("(the filter was designed after diagnosing 2021, so 2021 cannot validate it)")
    print("=" * 96)
    print(HEADER)
    print(line("no filter (ex-2021)", base[base["year"] != 2021]))
    for cap, d in results.items():
        print(line("maturity <= {:.1f} (ex-2021)".format(cap), d[d["year"] != 2021]))

    print("\n2021 ALONE (the year the filter was designed against)")
    print(HEADER)
    print(line("no filter (2021)", base[base["year"] == 2021]))
    for cap, d in results.items():
        print(line("maturity <= {:.1f} (2021)".format(cap), d[d["year"] == 2021]))

    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trend_maturity_core_trades.csv")
    base.to_csv(out, index=False)
    print("\nCore trade log: {}".format(out))


if __name__ == "__main__":
    main()
