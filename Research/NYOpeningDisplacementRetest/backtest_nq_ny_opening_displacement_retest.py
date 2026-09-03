"""Fixed research test: NY opening displacement plus retest continuation on NQ/MNQ.

Signals are causal closed 5-minute bars. The first 15 minutes after 09:30 ET define
an opening range. A displacement bar must close outside that range with a directional
body threshold. A later bar, no more than six 5-minute bars later, must retest the
broken edge and close back through it in the displacement direction. Entry is the
next 5-minute open. Exits are resolved on 1-minute bars, stop-first on ambiguity.

This is a falsifiable research signal, not a profitability claim or live approval.
"""
import argparse
import glob
import os
from dataclasses import dataclass
from typing import Dict, List

import numpy as np
import pandas as pd

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_DIR = r"C:\Users\maric\Documents\NinjaTrader 8\export\NQ"
SKIP_FILES = {"NQ 06-26.Last_2025-10-01 to 26-08-21.txt"}
TICK_SIZE = 0.25
POINT_VALUE = 20.0
COMMISSION_RT = 4.20
SLIPPAGE_TICKS_PER_SIDE = 1.0
MAX_DOLLAR_RISK = 250.0
DAILY_LOSS_LIMIT = 500.0
MAX_TRADES_PER_SESSION = 1
STOP_BUFFER_TICKS = 2
MIN_STOP_TICKS = 4
MAX_STOP_TICKS = 50
ATR_PERIOD = 14
DISPLACEMENT_ATR = 0.50
DISPLACEMENT_MIN_BODY_TICKS = 4
RETEST_MAX_BARS = 6
WINDOW_START = 9 * 60 + 30
WINDOW_END = 10 * 60 + 30
RANGE_END = 9 * 60 + 45
EOD_MINUTE = 16 * 60 + 55
HALT_MINUTE = 17 * 60

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
    parsed = pd.to_datetime(frame["dt_str"], format="%Y%m%d %H%M%S",
                             utc=True, errors="coerce")
    frame["dt"] = parsed.dt.tz_convert("America/New_York")
    return (frame.drop(columns=["dt_str"]).dropna(subset=["dt"])
            .sort_values("dt").drop_duplicates("dt").reset_index(drop=True))


def stitch_front_month(data_dir: str) -> pd.DataFrame:
    paths = [p for p in sorted(glob.glob(os.path.join(data_dir, "*.Last.txt")))
             if os.path.basename(p) not in SKIP_FILES]
    if not paths:
        raise FileNotFoundError("No NQ *.Last.txt files found in " + data_dir)
    frames: Dict[str, pd.DataFrame] = {}
    volumes: Dict[str, pd.Series] = {}
    for path in paths:
        frame = load_1min(path)
        frames[path] = frame
        volumes[path] = frame.groupby(frame["dt"].dt.date)["Volume"].sum()
    dates = sorted(set().union(*(v.index for v in volumes.values())))
    chosen = {day: max(paths, key=lambda p: volumes[p].get(day, 0)) for day in dates}
    parts = []
    for path, frame in frames.items():
        days = {day for day, selected in chosen.items() if selected == path}
        if days:
            parts.append(frame[frame["dt"].dt.date.isin(days)])
    result = pd.concat(parts).sort_values("dt").drop_duplicates("dt").reset_index(drop=True)
    # NT exports are stamped at bar close; signal bars below use their true open time.
    result["dt"] -= pd.Timedelta(minutes=1)
    add_time_columns(result)
    return result


def add_time_columns(frame: pd.DataFrame) -> None:
    frame["minute"] = frame["dt"].dt.hour * 60 + frame["dt"].dt.minute
    dates = frame["dt"].dt.normalize()
    frame["session"] = np.where(frame["dt"].dt.hour < 17,
                                (dates - pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d"),
                                dates.dt.strftime("%Y-%m-%d"))


def resample_5m(bars: pd.DataFrame) -> pd.DataFrame:
    result = (bars.set_index("dt").resample("5min", closed="left", label="left")
              .agg({"Open": "first", "High": "max", "Low": "min",
                    "Close": "last", "Volume": "sum"})
              .dropna(subset=["Open"]).reset_index())
    add_time_columns(result)
    return result


def atr_wilder(bars: pd.DataFrame, period: int) -> np.ndarray:
    high, low, close = (bars[c].to_numpy() for c in ["High", "Low", "Close"])
    previous = np.concatenate([[close[0]], close[:-1]])
    tr = np.maximum(high - low, np.maximum(abs(high - previous), abs(low - previous)))
    result = np.empty(len(tr))
    result[0] = tr[0]
    for i in range(1, len(tr)):
        n = min(i + 1, period)
        result[i] = ((n - 1) * result[i - 1] + tr[i]) / n
    return result


def timezone_check(bars: pd.DataFrame) -> None:
    volume = bars.groupby("minute")["Volume"].mean().reindex(range(1440), fill_value=0.0)
    et_step = volume.loc[570:585].mean() - volume.loc[540:565].mean()
    wrong_step = volume.loc[390:405].mean() - volume.loc[360:385].mean()
    print("Timezone check: 09:30 ET step={:+,.0f}; 06:30 step={:+,.0f}".format(et_step, wrong_step))
    if et_step <= wrong_step or et_step <= 0:
        raise RuntimeError("UTC-to-America/New_York sanity check failed")


def finish(plan: dict, exit_time, outcome: str, raw_r: float) -> Trade:
    risk_dollars = plan["risk_points"] * POINT_VALUE
    costs = COMMISSION_RT + 2 * SLIPPAGE_TICKS_PER_SIDE * TICK_SIZE * POINT_VALUE
    net_r = raw_r - costs / risk_dollars
    return Trade(plan["entry_time"], exit_time, plan["direction"], plan["entry"],
                 plan["stop"], plan["target"], plan["risk_points"], outcome,
                 raw_r, net_r, net_r * risk_dollars, plan["session"])


def exit_trade(plan: dict, bars1: pd.DataFrame) -> Trade:
    index = bars1["dt"].array.asi8
    times = bars1["dt"].to_numpy()
    minutes = bars1["minute"].to_numpy()
    sessions = bars1["session"].to_numpy()
    opens = bars1["Open"].to_numpy()
    highs = bars1["High"].to_numpy()
    lows = bars1["Low"].to_numpy()
    closes = bars1["Close"].to_numpy()
    start = int(np.searchsorted(index, pd.Timestamp(plan["entry_time"]).value, side="left"))
    if start >= len(index) or index[start] != pd.Timestamp(plan["entry_time"]).value:
        raise RuntimeError("entry timestamp is not an exact 1-minute bar")
    for i in range(start, len(index)):
        if sessions[i] != plan["session"] or EOD_MINUTE <= minutes[i] < HALT_MINUTE:
            move = opens[i] - plan["entry"] if plan["direction"] == "LONG" else plan["entry"] - opens[i]
            return finish(plan, times[i], "EOD", move / plan["risk_points"])
        hit_stop = lows[i] <= plan["stop"] if plan["direction"] == "LONG" else highs[i] >= plan["stop"]
        hit_target = highs[i] >= plan["target"] if plan["direction"] == "LONG" else lows[i] <= plan["target"]
        if hit_stop:  # conservative ordering when both levels occur in one minute
            return finish(plan, times[i], "STOP", -1.0)
        if hit_target:
            return finish(plan, times[i], "TARGET", 1.0)
    return finish(plan, times[-1], "DATA_END", 0.0)


def simulate(bars5: pd.DataFrame, bars1: pd.DataFrame):
    high, low, close, open_ = (bars5[c].to_numpy() for c in ["High", "Low", "Close", "Open"])
    times, minutes, sessions = (bars5[c].to_numpy() for c in ["dt", "minute", "session"])
    atr = atr_wilder(bars5, ATR_PERIOD)
    trades: List[Trade] = []
    audit = {"range_days": 0, "displacements": 0, "retest_candidates": 0,
             "gap_rejects": 0, "risk_rejects": 0, "daily_lock_rejects": 0,
             "entry_timestamp_rejects": 0, "trade_limit_rejects": 0,
             "signals": 0, "data_end": 0}
    session_trades, session_pnl = {}, {}
    displacement = None
    current_session = None
    i = ATR_PERIOD
    while i < len(bars5) - 1:
        session = sessions[i]
        if session != current_session:
            current_session, displacement = session, None
            session_trades[session] = 0
            session_pnl[session] = 0.0
        minute = int(minutes[i])
        if minute == WINDOW_START:
            audit["range_days"] += 1
        # Range is exactly the three completed 5-minute bars starting 09:30.
        if minute == RANGE_END and i >= 3 and sessions[i - 3] == session:
            range_high = float(np.max(high[i - 3:i]))
            range_low = float(np.min(low[i - 3:i]))
            displacement = {"high": range_high, "low": range_low, "bar": i}
        if displacement is None or minute < RANGE_END or minute >= WINDOW_END:
            i += 1
            continue
        age = i - displacement["bar"]
        if age > RETEST_MAX_BARS:
            displacement = None
            i += 1
            continue
        body = close[i] - open_[i]
        body_abs = abs(body)
        threshold = max(DISPLACEMENT_MIN_BODY_TICKS * TICK_SIZE, DISPLACEMENT_ATR * atr[i])
        if age == 0 and body_abs >= threshold:
            if close[i] > displacement["high"] and body > 0 and close[i] >= low[i] + 0.75 * (high[i] - low[i]):
                displacement.update(direction="LONG", edge=displacement["high"])
                audit["displacements"] += 1
            elif close[i] < displacement["low"] and body < 0 and close[i] <= high[i] - 0.75 * (high[i] - low[i]):
                displacement.update(direction="SHORT", edge=displacement["low"])
                audit["displacements"] += 1
        if "direction" not in displacement or age <= 0:
            i += 1
            continue
        edge = displacement["edge"]
        long_retest = displacement["direction"] == "LONG" and low[i] <= edge and close[i] > edge and close[i] > open_[i]
        short_retest = displacement["direction"] == "SHORT" and high[i] >= edge and close[i] < edge and close[i] < open_[i]
        if not (long_retest or short_retest):
            i += 1
            continue
        audit["retest_candidates"] += 1
        if i + 1 >= len(bars5) or times[i + 1] - times[i] != pd.Timedelta(minutes=5) or sessions[i + 1] != session:
            audit["gap_rejects"] += 1; i += 1; continue
        entry_key = pd.Timestamp(times[i + 1]).value
        entry_position = int(np.searchsorted(bars1["dt"].array.asi8, entry_key, side="left"))
        if entry_position >= len(bars1) or bars1["dt"].array.asi8[entry_position] - entry_key > pd.Timedelta(minutes=1).value:
            audit["entry_timestamp_rejects"] += 1; i += 1; continue
        if session_trades[session] >= MAX_TRADES_PER_SESSION:
            audit["trade_limit_rejects"] += 1; i += 1; continue
        if session_pnl[session] <= -DAILY_LOSS_LIMIT:
            audit["daily_lock_rejects"] += 1; i += 1; continue
        direction = displacement["direction"]
        entry = float(open_[i + 1])
        stop_raw = min(float(low[i]), edge) - STOP_BUFFER_TICKS * TICK_SIZE if direction == "LONG" else max(float(high[i]), edge) + STOP_BUFFER_TICKS * TICK_SIZE
        risk_ticks = int(round(abs(entry - stop_raw) / TICK_SIZE))
        if risk_ticks < MIN_STOP_TICKS or risk_ticks > MAX_STOP_TICKS or risk_ticks * TICK_SIZE * POINT_VALUE > MAX_DOLLAR_RISK:
            audit["risk_rejects"] += 1; i += 1; continue
        risk = risk_ticks * TICK_SIZE
        stop = entry - risk if direction == "LONG" else entry + risk
        target = entry + risk if direction == "LONG" else entry - risk
        plan = {"entry_time": bars1.iloc[entry_position]["dt"], "direction": direction, "entry": entry,
                "stop": stop, "target": target, "risk_points": risk, "session": session}
        trade = exit_trade(plan, bars1)
        trades.append(trade); audit["signals"] += 1
        if trade.outcome == "DATA_END": audit["data_end"] += 1
        session_trades[session] += 1; session_pnl[session] += trade.pnl
        displacement = None
        i += 1
    return trades, audit


def metrics(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"trades": 0, "win_rate": np.nan, "avg_r": np.nan, "pnl": 0.0, "max_dd": 0.0, "trades_per_week": 0.0}
    equity = frame["pnl"].cumsum()
    weeks = max((frame["entry_time"].max() - frame["entry_time"].min()).days / 7.0, 1 / 7.0)
    return {"trades": len(frame), "win_rate": float((frame["raw_r"] > 0).mean()),
            "avg_r": float(frame["net_r"].mean()), "pnl": float(frame["pnl"].sum()),
            "max_dd": float((equity - equity.cummax()).min()), "trades_per_week": len(frame) / weeks}


def validate(frame: pd.DataFrame, bars1: pd.DataFrame, bars5: pd.DataFrame, audit: dict) -> None:
    if frame.empty: raise RuntimeError("No trades; strategy is not evaluable")
    if audit["data_end"] > 1: raise RuntimeError("More than one DATA_END exit")
    if set(frame["outcome"]) - {"STOP", "TARGET", "EOD", "DATA_END"}: raise RuntimeError("Invalid exit outcome")
    if (frame["outcome"] == "DATA_END").any() and frame.iloc[-1]["exit_time"] != bars1.iloc[-1]["dt"]:
        raise RuntimeError("DATA_END was not at genuine data end")
    if frame["risk_points"].mul(POINT_VALUE).max() > MAX_DOLLAR_RISK + 1e-9: raise RuntimeError("Risk cap violated")
    if frame["entry_time"].duplicated().any(): raise RuntimeError("Duplicate/overlapping entry timestamps")
    if not frame["exit_time"].gt(frame["entry_time"]).all(): raise RuntimeError("Exit is not after entry")
    if not frame["entry_time"].is_monotonic_increasing: raise RuntimeError("Trade timestamps are not ordered")
    if len(bars1) == 0 or len(bars5) == 0: raise RuntimeError("Empty bar set")


def report(trades, audit, bars1, bars5, output_csv, output_md) -> None:
    if not trades:
        raise RuntimeError("No accepted trades; audit counters: {}".format(audit))
    frame = pd.DataFrame([t.__dict__ for t in trades]).sort_values("entry_time").reset_index(drop=True)
    validate(frame, bars1, bars5, audit)
    frame["year"] = frame.entry_time.dt.year
    frame.to_csv(output_csv, index=False)
    scopes = [("COMBINED", frame), ("LONG", frame[frame.direction == "LONG"]), ("SHORT", frame[frame.direction == "SHORT"])]
    lines = ["# NY Opening Displacement Retest Research", "", "## Verdict", "", "Preliminary research only; no profitability or live approval claim.", "", "## Results", "", "| scope | trades | win rate | avg net R | net P&L | max DD | trades/week |", "|---|---:|---:|---:|---:|---:|---:|"]
    for name, subset in scopes:
        m = metrics(subset); lines.append("| {} | {} | {} | {} | ${:,.2f} | ${:,.2f} | {:.2f} |".format(name, m["trades"], "-" if np.isnan(m["win_rate"]) else "{:.1%}".format(m["win_rate"]), "-" if np.isnan(m["avg_r"]) else "{:+.3f}".format(m["avg_r"]), m["pnl"], m["max_dd"], m["trades_per_week"]))
    lines += ["", "## Yearly Combined", "", "| year | trades | win rate | avg net R | net P&L | max DD | trades/week |", "|---|---:|---:|---:|---:|---:|---:|"]
    for year, subset in frame.groupby("year"):
        m = metrics(subset); lines.append("| {} | {} | {:.1%} | {:+.3f} | ${:,.2f} | ${:,.2f} | {:.2f} |".format(year, m["trades"], m["win_rate"], m["avg_r"], m["pnl"], m["max_dd"], m["trades_per_week"]))
    lines += ["", "## Audit", "", "- Outcomes: {}".format(frame.outcome.value_counts().to_dict()), "- Data: {:,} 1-minute bars, {:,} 5-minute bars, {} to {}.".format(len(bars1), len(bars5), bars1.dt.min(), bars1.dt.max())]
    lines += ["- {}: {}".format(k, v) for k, v in audit.items()]
    lines += ["- Invariants passed: causal closed-bar entries, exact 1-minute entry lookup, stop-first ambiguity, risk cap, ordered non-overlapping trades, valid exits, and genuine data-end handling.", "", "## Fixed Rules", "", "5-minute signals; 1-minute exits; 09:30-10:30 ET opportunity window; 09:30-09:45 first range; displacement body >= max(4 ticks, 0.50 ATR14), close outside edge in outer quarter; later retest within 30 minutes touches edge and closes back through it in same direction; next-bar-open entry; stop at retest low/high or edge plus 2 ticks; target 1R; one trade per CME session; $250 max NQ risk; $500 daily lock; 1 tick/side slippage; $4.20 round-turn commission.", "", "## Difference From Raw ORB", "", "Raw ORB takes the first range break. This signal deliberately does not: it requires a strong closed displacement bar, then waits for a later test of the broken edge and continuation close. A failed retest produces no entry, and the opportunity expires after six 5-minute bars. This isolates continuation after acceptance from the known raw-breakout failure pattern.", "", "## Conservative Call", "", "Read the exact train, untouched test, and full-history figures above. A negative net result is rejection with no optimization. A positive preliminary result still requires untouched OOS review and Sim101 forward testing before any live decision."]
    open(output_md, "w", encoding="ascii").write("\n".join(lines) + "\n")
    print("Wrote " + output_csv); print("Wrote " + output_md)
    print("\n" + "\n".join(lines[6:15]))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    bars1 = stitch_front_month(args.data_dir); bars5 = resample_5m(bars1)
    timezone_check(bars1)
    print("Data: {:,} 1m bars, {} to {}".format(len(bars1), bars1.dt.min(), bars1.dt.max()))
    trades, audit = simulate(bars5, bars1)
    output_csv = os.path.join(SCRIPT_DIR, "nq_ny_opening_displacement_retest_trades.csv")
    output_md = os.path.join(SCRIPT_DIR, "nq_ny_opening_displacement_retest_results.md")
    report(trades, audit, bars1, bars5, output_csv, output_md)
    frame = pd.DataFrame([t.__dict__ for t in trades]); frame["year"] = frame.entry_time.dt.year
    for label, mask in [("TRAIN_2020-12_to_2023-12", frame.entry_time < pd.Timestamp("2024-01-01", tz="America/New_York")), ("TEST_2024-01_to_2026-08-21", frame.entry_time >= pd.Timestamp("2024-01-01", tz="America/New_York")), ("FULL_HISTORY", np.ones(len(frame), dtype=bool))]:
        m = metrics(frame[mask]); print("{}: trades={} win={:.1%} avg_net_R={:+.3f} pnl=${:,.2f} maxDD=${:,.2f} trades/week={:.2f}".format(label, m["trades"], m["win_rate"], m["avg_r"], m["pnl"], m["max_dd"], m["trades_per_week"]))

if __name__ == "__main__":
    main()
