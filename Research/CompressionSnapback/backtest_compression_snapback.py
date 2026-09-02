"""
Compression Snapback research backtest for NQ/MNQ.

Hypothesis: after three unusually narrow completed 5-minute bars, a two-tick
expansion beyond that cluster that closes back inside the cluster tends to
revert far enough to reach a fixed 1:1 target before the probe extreme is
revisited. This is a new volatility-structure test, not an EMA/VWAP, ORB,
trend-continuation, session-open, exhaustion, Renko, or failed-2 strategy.

Data: local NinjaTrader 1-minute exports are UTC-native, converted to true
DST-aware America/New_York, then front-month stitched by highest daily volume.
NinjaTrader stamps each bar at its CLOSE, so timestamps are shifted back one
minute to bar-open time before resampling; this makes the 5-minute bars line up
with what NinjaTrader itself would draw. Signals use closed 5-minute bars;
entries fill at the next 5-minute open, and that entry bar is itself scanned for
the exit. Exits use 1-minute bars. On an ambiguous 1-minute bar, stop wins.

One pre-registered configuration. No parameter sweep or optimization.
"""

import argparse
import glob
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

DATA_DIR = r"C:\Users\maric\Documents\NinjaTrader 8\export\NQ"
SKIP_FILES = {"NQ 06-26.Last_2025-10-01 to 26-08-21.txt"}
TICK_SIZE = 0.25
POINT_VALUE = 20.0
COMMISSION_RT = 4.20
SLIPPAGE_TICKS_PER_SIDE = 1.0
MAX_DOLLAR_RISK = 250.0
DAILY_LOSS_LIMIT = 500.0
MAX_TRADES_PER_SESSION = 2
COOLDOWN_BARS = 6
CLUSTER_BARS = 3
REFERENCE_CLUSTERS = 20
COMPRESSION_FACTOR = 0.75
PROBE_TICKS = 2
STOP_BUFFER_TICKS = 2
MIN_STOP_TICKS = 4
MAX_STOP_TICKS = 48
EOD_MINUTE = 16 * 60 + 55
HALT_MINUTE = 17 * 60
ELECTRONIC_START_MINUTE = 18 * 60


@dataclass
class Trade:
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: str
    entry: float
    stop: float
    target: float
    risk_points: float
    outcome: str
    raw_r: float
    net_r: float
    pnl: float
    session: object


def load_1min(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path, sep=";", header=None,
                        names=["dt_str", "Open", "High", "Low", "Close", "Volume"])
    frame["dt"] = pd.to_datetime(frame["dt_str"], format="%Y%m%d %H%M%S", utc=True)
    frame["dt"] = frame["dt"].dt.tz_convert("America/New_York")
    return frame.drop(columns=["dt_str"]).dropna(subset=["dt"]).sort_values("dt").reset_index(drop=True)


def stitch_front_month(data_dir: str) -> pd.DataFrame:
    paths = [p for p in sorted(glob.glob(os.path.join(data_dir, "*.Last.txt")))
             if os.path.basename(p) not in SKIP_FILES]
    if not paths:
        raise FileNotFoundError("No NQ *.Last.txt files found in " + data_dir)
    frames: Dict[str, pd.DataFrame] = {}
    daily_volume: Dict[str, pd.Series] = {}
    for path in paths:
        frame = load_1min(path)
        frames[path] = frame
        daily_volume[path] = frame.groupby(frame["dt"].dt.date)["Volume"].sum()
    dates = sorted(set().union(*(series.index for series in daily_volume.values())))
    chosen = {day: max(paths, key=lambda path: daily_volume[path].get(day, 0)) for day in dates}
    parts = []
    for path, frame in frames.items():
        days = {day for day, selected in chosen.items() if selected == path}
        if days:
            parts.append(frame[frame["dt"].dt.date.isin(days)])
    result = pd.concat(parts).sort_values("dt").drop_duplicates("dt").reset_index(drop=True)
    # NinjaTrader stamps a bar at its close; work in bar-open time from here on.
    result["dt"] = result["dt"] - pd.Timedelta(minutes=1)
    result["minute"] = result["dt"].dt.hour * 60 + result["dt"].dt.minute
    result["session"] = np.where(result["dt"].dt.hour < 17,
                                 result["dt"].dt.date - pd.Timedelta(days=1),
                                 result["dt"].dt.date)
    return result


def resample_5m(bars: pd.DataFrame) -> pd.DataFrame:
    grouped = bars.set_index("dt").resample("5min", closed="left", label="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna(subset=["Open"]).reset_index()
    grouped["minute"] = grouped["dt"].dt.hour * 60 + grouped["dt"].dt.minute
    grouped["session"] = np.where(grouped["dt"].dt.hour < 17,
                                  grouped["dt"].dt.date - pd.Timedelta(days=1),
                                  grouped["dt"].dt.date)
    return grouped


def timezone_check(bars: pd.DataFrame) -> None:
    volume = bars.groupby("minute")["Volume"].mean().reindex(range(1440), fill_value=0.0)
    et_step = volume.loc[570:585].mean() - volume.loc[540:565].mean()
    wrong_step = volume.loc[390:405].mean() - volume.loc[360:385].mean()
    halt = volume.loc[HALT_MINUTE:HALT_MINUTE + 55].mean()
    active = volume.loc[ELECTRONIC_START_MINUTE:ELECTRONIC_START_MINUTE + 55].mean()
    print("Timezone check: 09:30 ET step={:+,.0f}; 06:30 step={:+,.0f}".format(et_step, wrong_step))
    print("Halt check: 17:00-17:55 mean vol={:,.0f} vs 18:00-18:55 mean vol={:,.0f}".format(halt, active))
    if et_step <= wrong_step or et_step <= 0:
        raise RuntimeError("UTC-to-Eastern sanity check failed")
    if halt >= active * 0.05:
        raise RuntimeError("Maintenance-halt sanity check failed")


RTH_START_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60


def in_electronic_session(minute: int) -> bool:
    return minute >= ELECTRONIC_START_MINUTE or minute < HALT_MINUTE


def in_regular_session(minute: int) -> bool:
    return RTH_START_MINUTE <= minute < RTH_END_MINUTE


def exit_trade(plan: dict, index_i8: np.ndarray, times, opens, highs, lows,
               closes, sessions, minutes) -> "Trade":
    direction = plan["direction"]
    entry = plan["entry"]
    stop = plan["stop"]
    target = plan["target"]
    risk_points = plan["risk_points"]
    key = pd.Timestamp(plan["entry_time"]).as_unit("ns").value
    start_index = int(index_i8.searchsorted(key, side="left"))
    if start_index >= len(opens):
        raise RuntimeError("entry timestamp not found in the 1-minute series")
    for row in range(start_index, len(opens)):
        if sessions[row] != plan["session"] or EOD_MINUTE <= minutes[row] < HALT_MINUTE:
            exit_price = float(opens[row])
            raw_r = ((exit_price - entry) if direction == "LONG" else (entry - exit_price)) / risk_points
            return finish(plan, times[row], "EOD", raw_r)
        hit_stop = float(lows[row]) <= stop if direction == "LONG" else float(highs[row]) >= stop
        hit_target = float(highs[row]) >= target if direction == "LONG" else float(lows[row]) <= target
        if hit_stop:
            return finish(plan, times[row], "STOP", -1.0)
        if hit_target:
            return finish(plan, times[row], "TARGET", 1.0)
    exit_price = float(closes[-1])
    raw_r = ((exit_price - entry) if direction == "LONG" else (entry - exit_price)) / risk_points
    return finish(plan, times[-1], "DATA_END", raw_r)


def finish(plan: dict, exit_time: pd.Timestamp, outcome: str, raw_r: float) -> Trade:
    risk_dollars = plan["risk_points"] * POINT_VALUE
    cost = COMMISSION_RT + 2.0 * SLIPPAGE_TICKS_PER_SIDE * TICK_SIZE * POINT_VALUE
    net_r = raw_r - cost / risk_dollars
    return Trade(plan["entry_time"], exit_time, plan["direction"], plan["entry"],
                 plan["stop"], plan["target"], plan["risk_points"], outcome, raw_r,
                 net_r, net_r * risk_dollars, plan["session"])


def run(rth_only: bool = False) -> None:
    bars1m = stitch_front_month(DATA_DIR)
    bars5m = resample_5m(bars1m)
    timezone_check(bars5m)
    print("Data: {:,} 1m bars, {} to {}".format(len(bars1m), bars1m.dt.min(), bars1m.dt.max()))
    print("5m bars: {:,}".format(len(bars5m)))

    # pandas may store these at microsecond resolution; force ns so the int64 keys
    # match Timestamp.value, which is always nanoseconds.
    index_i8 = (bars1m["dt"].dt.tz_convert("UTC").dt.tz_localize(None)
                .to_numpy().astype("datetime64[ns]").astype("int64"))
    m_times = bars1m["dt"].to_list()
    m_open, m_high = bars1m["Open"].to_numpy(), bars1m["High"].to_numpy()
    m_low, m_close = bars1m["Low"].to_numpy(), bars1m["Close"].to_numpy()
    m_session, m_minute = bars1m["session"].to_numpy(), bars1m["minute"].to_numpy()

    highs, lows = bars5m["High"].to_numpy(), bars5m["Low"].to_numpy()
    rolling_high = pd.Series(highs).rolling(CLUSTER_BARS).max().to_numpy()
    rolling_low = pd.Series(lows).rolling(CLUSTER_BARS).min().to_numpy()
    three_bar_width = rolling_high - rolling_low
    times5 = bars5m["dt"].to_list()
    sessions5 = bars5m["session"].to_numpy()
    minutes5 = bars5m["minute"].to_numpy()
    opens5 = bars5m["Open"].to_numpy()
    closes5 = bars5m["Close"].to_numpy()

    trades: List[Trade] = []
    audit = {"compression_candidates": 0, "failed_high": 0, "failed_low": 0,
             "gap_rejects": 0, "risk_rejects": 0, "cooldown_rejects": 0,
             "daily_lock_rejects": 0, "trade_limit_rejects": 0, "signals": 0}
    session_trades: Dict[object, int] = {}
    session_pnl: Dict[object, float] = {}
    last_entry_index = -10 ** 9
    # Warm-up: the oldest reference block reaches back CLUSTER_BARS*(REFERENCE_CLUSTERS+1)+1 bars.
    i = CLUSTER_BARS * (REFERENCE_CLUSTERS + 1) + 2
    while i < len(bars5m) - 1:
        window_ok = in_regular_session(int(minutes5[i])) if rth_only             else in_electronic_session(int(minutes5[i]))
        if not window_ok:
            i += 1
            continue
        cluster_width = float(three_bar_width[i - 1])
        prior_indexes = [i - CLUSTER_BARS - 1 - block * CLUSTER_BARS
                         for block in range(REFERENCE_CLUSTERS)]
        median_width = float(np.median(three_bar_width[prior_indexes]))
        if not np.isfinite(median_width) or median_width <= 0 \
                or cluster_width > COMPRESSION_FACTOR * median_width:
            i += 1
            continue
        audit["compression_candidates"] += 1
        cluster_high = float(rolling_high[i - 1])
        cluster_low = float(rolling_low[i - 1])
        close = float(closes5[i])
        direction: Optional[str] = None
        if highs[i] >= cluster_high + PROBE_TICKS * TICK_SIZE and cluster_low < close < cluster_high:
            direction = "SHORT"
            audit["failed_high"] += 1
        elif lows[i] <= cluster_low - PROBE_TICKS * TICK_SIZE and cluster_low < close < cluster_high:
            direction = "LONG"
            audit["failed_low"] += 1
        if direction is None:
            i += 1
            continue
        session = sessions5[i]
        # The entry bar must be the genuinely next 5-minute bar in the same session.
        if (times5[i + 1] - times5[i]) != pd.Timedelta(minutes=5) or sessions5[i + 1] != session:
            audit["gap_rejects"] += 1
            i += 1
            continue
        if session_trades.get(session, 0) >= MAX_TRADES_PER_SESSION:
            audit["trade_limit_rejects"] += 1
            i += 1
            continue
        if i - last_entry_index <= COOLDOWN_BARS:
            audit["cooldown_rejects"] += 1
            i += 1
            continue
        if session_pnl.get(session, 0.0) <= -DAILY_LOSS_LIMIT:
            audit["daily_lock_rejects"] += 1
            i += 1
            continue
        entry = float(opens5[i + 1])
        stop = (float(highs[i]) + STOP_BUFFER_TICKS * TICK_SIZE) if direction == "SHORT" \
            else (float(lows[i]) - STOP_BUFFER_TICKS * TICK_SIZE)
        risk_points = abs(entry - stop)
        risk_ticks = int(round(risk_points / TICK_SIZE))
        if risk_ticks < MIN_STOP_TICKS or risk_ticks > MAX_STOP_TICKS \
                or risk_points * POINT_VALUE > MAX_DOLLAR_RISK:
            audit["risk_rejects"] += 1
            i += 1
            continue
        target = entry - risk_points if direction == "SHORT" else entry + risk_points
        plan = {"direction": direction, "entry": entry, "stop": stop, "target": target,
                "risk_points": risk_points, "entry_time": times5[i + 1], "session": session}
        trade = exit_trade(plan, index_i8, m_times, m_open, m_high, m_low,
                           m_close, m_session, m_minute)
        trades.append(trade)
        session_trades[session] = session_trades.get(session, 0) + 1
        session_pnl[session] = session_pnl.get(session, 0.0) + trade.pnl
        last_entry_index = i + 1
        audit["signals"] += 1
        i += 1

    report_results(trades, audit, rth_only)


def excl_top5(series: pd.Series) -> float:
    if len(series) == 0:
        return float("nan")
    k = max(1, int(len(series) * 0.05))
    return series.sort_values(ascending=False).iloc[k:].mean()


HEADER = "{:>10} {:>5} {:>7} {:>8} {:>9} {:>11} {:>11} {:>10}".format(
    "scope", "n", "win%", "avg_R", "median_R", "excl_top5%", "net_PnL", "max_DD")


def line(scope: str, subset: pd.DataFrame) -> None:
    if subset.empty:
        print("{:>10} {:5d} {:>7} {:>8} {:>9} {:>11} {:>11} {:>10}".format(
            scope, 0, "-", "-", "-", "-", "-", "-"))
        return
    equity = subset.pnl.cumsum()
    print("{:>10} {:5d} {:6.1%} {:+8.3f} {:+9.3f} {:+11.3f} {:11.2f} {:10.2f}".format(
        scope, len(subset), (subset.raw_r > 0).mean(), subset.net_r.mean(),
        subset.net_r.median(), excl_top5(subset.net_r), subset.pnl.sum(),
        (equity - equity.cummax()).min()))


def report_results(trades: List[Trade], audit: dict, rth_only: bool = False) -> None:
    print("\nAUDIT")
    for key, value in audit.items():
        print("  {}: {:,}".format(key, value))
    frame = pd.DataFrame([t.__dict__ for t in trades])
    if frame.empty:
        print("No trades; strategy is not evaluable on this export.")
        return
    entry_index = pd.DatetimeIndex(frame.entry_time)
    frame["year"] = entry_index.year
    print("\nRESULTS (NQ 1 contract, costs: ${:.2f} RT + {:.0f} tick/side slippage)".format(
        COMMISSION_RT, SLIPPAGE_TICKS_PER_SIDE))
    print(HEADER)
    line("COMBINED", frame)
    line("LONG", frame[frame.direction == "LONG"])
    line("SHORT", frame[frame.direction == "SHORT"])

    print("\nYEARLY (combined)")
    print(HEADER)
    for year, subset in frame.groupby("year"):
        line(str(year), subset)

    print("\nSESSION SEGMENT (combined)")
    print(HEADER)
    entry_minute = entry_index.hour * 60 + entry_index.minute
    segments = {"overnight": (entry_minute >= 18 * 60) | (entry_minute < 8 * 60),
                "premarket": (entry_minute >= 8 * 60) & (entry_minute < 9 * 60 + 30),
                "rth": (entry_minute >= 9 * 60 + 30) & (entry_minute < 16 * 60)}
    for label, mask in segments.items():
        line(label, frame[mask])

    print("\nOUTCOMES: {}".format(frame.outcome.value_counts().to_dict()))
    print("R distribution (net): min={:+.3f} max={:+.3f}".format(frame.net_r.min(), frame.net_r.max()))
    print("Avg risk: ${:.2f}  |  stop ticks: min={} median={} max={}".format(
        frame.risk_points.mean() * POINT_VALUE,
        int(round(frame.risk_points.min() / TICK_SIZE)),
        int(round(frame.risk_points.median() / TICK_SIZE)),
        int(round(frame.risk_points.max() / TICK_SIZE))))
    top = frame.nlargest(max(1, int(len(frame) * 0.05)), "net_r")
    print("Top 5% winners land on {} distinct sessions (of {} traded sessions).".format(
        top.session.nunique(), frame.session.nunique()))
    out = "compression_snapback_trades_rth.csv" if rth_only else "compression_snapback_trades.csv"
    frame.to_csv(out, index=False)
    print("\nTrade log written to " + out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rth", action="store_true",
                        help="Diagnostic: restrict signals to the 09:30-16:00 ET regular session, "
                             "which the two-trades-per-session cap otherwise starves.")
    args = parser.parse_args()
    print("MODE: {}".format("RTH-only diagnostic" if args.rth else "pre-registered electronic session"))
    run(rth_only=args.rth)
