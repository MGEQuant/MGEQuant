"""Fixed V2 test of CompressionSnapback on 3-minute primary signal bars.

Hypothesis: preserving the compression snapback signal but using 3-minute bars
for signal formation and next-bar entry may reduce missed intrabar reversals
and improve fill/exit resolution. This is falsifiable and is not a claim of
profitability. It is a new timeframe variant, not an execution-only comparison.
"""

import argparse
import glob
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

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
MAX_TRADES_PER_SESSION = 2
COOLDOWN_BARS = 6
CLUSTER_BARS = 3
REFERENCE_CLUSTERS = 20
COMPRESSION_FACTOR = 0.75
PROBE_TICKS = 2
STOP_BUFFER_TICKS = 2
MIN_STOP_TICKS = 4
MAX_STOP_TICKS = 48
SIGNAL_MINUTES = 3
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
    parsed = pd.to_datetime(frame["dt_str"], format="%Y%m%d %H%M%S", utc=True, errors="coerce")
    frame["dt"] = parsed.dt.tz_convert("America/New_York")
    frame = frame.drop(columns=["dt_str"]).dropna(subset=["dt"])
    return frame.sort_values("dt").drop_duplicates("dt").reset_index(drop=True)


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
    dates = sorted(set().union(*(series.index for series in volumes.values())))
    chosen = {day: max(paths, key=lambda path: volumes[path].get(day, 0)) for day in dates}
    parts = []
    for path, frame in frames.items():
        days = {day for day, selected in chosen.items() if selected == path}
        if days:
            parts.append(frame[frame["dt"].dt.date.isin(days)])
    result = pd.concat(parts).sort_values("dt").drop_duplicates("dt").reset_index(drop=True)
    result["dt"] -= pd.Timedelta(minutes=1)
    add_time_columns(result)
    return result


def add_time_columns(frame: pd.DataFrame) -> None:
    frame["minute"] = frame["dt"].dt.hour * 60 + frame["dt"].dt.minute
    frame["session"] = np.where(frame["dt"].dt.hour < 17,
                                frame["dt"].dt.date - pd.Timedelta(days=1),
                                frame["dt"].dt.date)


def resample_3m(bars: pd.DataFrame) -> pd.DataFrame:
    grouped = bars.set_index("dt").resample("3min", closed="left", label="left").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    ).dropna(subset=["Open"]).reset_index()
    add_time_columns(grouped)
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


def in_electronic_session(minute: int) -> bool:
    return minute >= ELECTRONIC_START_MINUTE or minute < HALT_MINUTE


def finish(plan: dict, exit_time: pd.Timestamp, outcome: str, raw_r: float) -> Trade:
    risk_dollars = plan["risk_points"] * POINT_VALUE
    cost = COMMISSION_RT + 2.0 * SLIPPAGE_TICKS_PER_SIDE * TICK_SIZE * POINT_VALUE
    net_r = raw_r - cost / risk_dollars
    return Trade(plan["entry_time"], exit_time, plan["direction"], plan["entry"],
                 plan["stop"], plan["target"], plan["risk_points"], outcome, raw_r,
                 net_r, net_r * risk_dollars, plan["session"])


def exit_trade(plan: dict, bars: pd.DataFrame) -> Trade:
    times = bars["dt"].to_list()
    key = pd.Timestamp(plan["entry_time"]).value
    index = bars["dt"].array.asi8
    row = int(np.searchsorted(index, key, side="left"))
    if row >= len(bars) or times[row] != plan["entry_time"]:
        raise RuntimeError("entry timestamp not found in 1-minute series")
    for current in range(row, len(bars)):
        minute = int(bars.iloc[current]["minute"])
        if bars.iloc[current]["session"] != plan["session"] or EOD_MINUTE <= minute < HALT_MINUTE:
            price = float(bars.iloc[current]["Open"])
            move = price - plan["entry"] if plan["direction"] == "LONG" else plan["entry"] - price
            return finish(plan, times[current], "EOD", move / plan["risk_points"])
        high, low = float(bars.iloc[current]["High"]), float(bars.iloc[current]["Low"])
        hit_stop = low <= plan["stop"] if plan["direction"] == "LONG" else high >= plan["stop"]
        hit_target = high >= plan["target"] if plan["direction"] == "LONG" else low <= plan["target"]
        if hit_stop:
            return finish(plan, times[current], "STOP", -1.0)
        if hit_target:
            return finish(plan, times[current], "TARGET", 1.0)
    raise RuntimeError("trade reached dataset end without a genuine DATA_END exit")


def excl_top5(series: pd.Series) -> float:
    k = max(1, int(len(series) * 0.05))
    return series.sort_values(ascending=False).iloc[k:].mean() if len(series) else float("nan")


def metrics(label: str, subset: pd.DataFrame) -> str:
    if subset.empty:
        return "| {} | 0 | - | - | - | - | - | - |".format(label)
    equity = subset.pnl.cumsum()
    return "| {} | {} | {:.1%} | {:+.3f} | {:+.3f} | {:+.3f} | {:.2f} | {:.2f} |".format(
        label, len(subset), (subset.raw_r > 0).mean(), subset.net_r.mean(),
        subset.net_r.median(), excl_top5(subset.net_r), subset.pnl.sum(),
        (equity - equity.cummax()).min())


def run(data_dir: str) -> str:
    bars1m = stitch_front_month(data_dir)
    bars3m = resample_3m(bars1m)
    timezone_check(bars3m)
    print("Data: {:,} 1m bars, {} to {}".format(len(bars1m), bars1m.dt.min(), bars1m.dt.max()))
    print("3m signal bars: {:,}".format(len(bars3m)))
    highs, lows = bars3m.High.to_numpy(), bars3m.Low.to_numpy()
    closes, opens = bars3m.Close.to_numpy(), bars3m.Open.to_numpy()
    rolling_high = pd.Series(highs).rolling(CLUSTER_BARS).max().to_numpy()
    rolling_low = pd.Series(lows).rolling(CLUSTER_BARS).min().to_numpy()
    widths = rolling_high - rolling_low
    trades: List[Trade] = []
    audit = {"compression_candidates": 0, "failed_high": 0, "failed_low": 0,
             "gap_rejects": 0, "risk_rejects": 0, "cooldown_rejects": 0,
             "daily_lock_rejects": 0, "trade_limit_rejects": 0, "signals": 0}
    session_trades: Dict[object, int] = {}
    session_pnl: Dict[object, float] = {}
    last_entry_index = -10 ** 9
    warmup = CLUSTER_BARS * (REFERENCE_CLUSTERS + 1) + 1
    i = warmup
    while i < len(bars3m) - 1:
        if not in_electronic_session(int(bars3m.iloc[i]["minute"])):
            i += 1
            continue
        prior = [i - CLUSTER_BARS - 1 - block * CLUSTER_BARS for block in range(REFERENCE_CLUSTERS)]
        median_width = float(np.median(widths[prior]))
        cluster_width = float(widths[i - 1])
        if not np.isfinite(median_width) or median_width <= 0 or cluster_width > COMPRESSION_FACTOR * median_width:
            i += 1
            continue
        audit["compression_candidates"] += 1
        cluster_high, cluster_low = float(rolling_high[i - 1]), float(rolling_low[i - 1])
        direction: Optional[str] = None
        if highs[i] >= cluster_high + PROBE_TICKS * TICK_SIZE and cluster_low < closes[i] < cluster_high:
            direction = "SHORT"; audit["failed_high"] += 1
        elif lows[i] <= cluster_low - PROBE_TICKS * TICK_SIZE and cluster_low < closes[i] < cluster_high:
            direction = "LONG"; audit["failed_low"] += 1
        if direction is None:
            i += 1
            continue
        session = bars3m.iloc[i]["session"]
        if (bars3m.iloc[i + 1]["dt"] - bars3m.iloc[i]["dt"] != pd.Timedelta(minutes=SIGNAL_MINUTES)
                or bars3m.iloc[i + 1]["session"] != session):
            audit["gap_rejects"] += 1; i += 1; continue
        if session_trades.get(session, 0) >= MAX_TRADES_PER_SESSION:
            audit["trade_limit_rejects"] += 1; i += 1; continue
        if i - last_entry_index <= COOLDOWN_BARS:
            audit["cooldown_rejects"] += 1; i += 1; continue
        if session_pnl.get(session, 0.0) <= -DAILY_LOSS_LIMIT:
            audit["daily_lock_rejects"] += 1; i += 1; continue
        entry_time = bars3m.iloc[i + 1]["dt"]
        entry = float(opens[i + 1])
        stop = float(highs[i] + STOP_BUFFER_TICKS * TICK_SIZE) if direction == "SHORT" else float(lows[i] - STOP_BUFFER_TICKS * TICK_SIZE)
        risk_ticks = max(MIN_STOP_TICKS, int(round(abs(entry - stop) / TICK_SIZE)))
        risk_points = risk_ticks * TICK_SIZE
        if risk_ticks > MAX_STOP_TICKS or risk_points * POINT_VALUE > MAX_DOLLAR_RISK:
            audit["risk_rejects"] += 1; i += 1; continue
        target = entry - risk_points if direction == "SHORT" else entry + risk_points
        plan = {"direction": direction, "entry": entry, "stop": stop, "target": target,
                "risk_points": risk_points, "entry_time": entry_time, "session": session}
        trade = exit_trade(plan, bars1m)
        trades.append(trade); session_trades[session] = session_trades.get(session, 0) + 1
        session_pnl[session] = session_pnl.get(session, 0.0) + trade.pnl
        last_entry_index = i + 1; audit["signals"] += 1; i += 1

    if not trades:
        raise RuntimeError("No trades; strategy is not evaluable on this export")
    frame = pd.DataFrame([trade.__dict__ for trade in trades])
    frame["year"] = pd.DatetimeIndex(frame.entry_time).year
    outcomes = frame.outcome.value_counts().to_dict()
    if outcomes.get("DATA_END", 0) > 0:
        raise RuntimeError("DATA_END occurred without a genuine dataset-end trade")
    if set(outcomes) - {"STOP", "TARGET", "EOD"}:
        raise RuntimeError("Unexpected exit outcome: {}".format(outcomes))
    if frame.raw_r.min() < -1.05 or frame.raw_r.max() > 1.05:
        raise RuntimeError("Raw R outside reasonable 1:1 bound: [{:.3f}, {:.3f}]".format(frame.raw_r.min(), frame.raw_r.max()))
    if len(frame) < 100 or (frame.outcome.isin(["STOP", "TARGET", "EOD"]).mean() < 0.99):
        raise RuntimeError("Exit coverage assertion failed")
    output_csv = os.path.join(SCRIPT_DIR, "compression_snapback_v2_trades.csv")
    frame.to_csv(output_csv, index=False)
    lines = ["# Compression Snapback V2 Report", "", "## Verdict", "", "Preliminary screening only; this result is not profitability or live approval.", "",
             "## Hypothesis", "", "Preserving the compression snapback signal but using 3-minute primary signal bars may reduce missed intrabar reversals and improve fill/exit resolution. The hypothesis is falsifiable. This is a new timeframe variant, not an execution-only comparison.", "",
             "## Fixed Configuration", "", "3-minute primary bars; 3 compression bars (9 minutes); 20 non-overlapping reference clusters of 3 bars (60 minutes); factor 0.75; probe 2 ticks; buffer 2 ticks; minimum stop 4 ticks; maximum stop 48 ticks; max risk $250; daily loss $500; max 2 trades per CME session; cooldown 6 signal bars; fixed 1:1; electronic sessions excluding 17:00-18:00 ET. Entry is the next 3-minute open after the closed signal bar. Exits use 1-minute bars, stop-first on ambiguity.", "",
             "## Data Quality Assertions", "", "- {} 1-minute bars; {} 3-minute signal bars; {} to {}.".format(len(bars1m), len(bars3m), bars1m.dt.min(), bars1m.dt.max()),
             "- Outcomes: {}; DATA_END count: 0; raw R range: [{:.3f}, {:.3f}].".format(outcomes, frame.raw_r.min(), frame.raw_r.max()),
             "- Exit coverage assertion passed: all trades ended STOP, TARGET, or EOD and trade count was {}.".format(len(frame)), "",
             "## Results", "", "| scope | n | win% | avg_R | median_R | excl_top5% | net_PnL | max_DD |", "|---|---:|---:|---:|---:|---:|---:|---:|",
             metrics("COMBINED", frame), metrics("LONG", frame[frame.direction == "LONG"]), metrics("SHORT", frame[frame.direction == "SHORT"]), "", "## Yearly", "", "| year | n | win% | avg_R | median_R | excl_top5% | net_PnL | max_DD |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    lines += [metrics(str(year), subset) for year, subset in frame.groupby("year")]
    lines += ["", "## Audit", ""] + ["- {}: {}".format(key, value) for key, value in audit.items()]
    lines += ["", "## Control Comparison", "", "Original 5-minute electronic control: 2,312 trades, 49.6% win, avg net R -0.178, net PnL -$33,570.40, negative in all seven years. V2 is not a direct execution-only comparison because its signal bars and clock-scaled lookback are 3 minutes.", "", "## Verdict", "", "The V2 result must be read from this generated report. If it remains negative after costs or fails the preliminary screen, stop and do not add another arbitrary tweak. If it passes preliminary screening, test only on untouched out-of-sample data; do not approve live trading."]
    report_path = os.path.join(SCRIPT_DIR, "NqCompressionSnapbackResearchV2_results.md")
    with open(report_path, "w", encoding="ascii") as handle:
        handle.write("\n".join(lines) + "\n")
    print("\nRESULTS")
    print(metrics("COMBINED", frame)); print(metrics("LONG", frame[frame.direction == "LONG"])); print(metrics("SHORT", frame[frame.direction == "SHORT"]))
    print("OUTCOMES: {}".format(outcomes)); print("Raw R: [{:+.3f}, {:+.3f}]".format(frame.raw_r.min(), frame.raw_r.max()))
    print("Trade log written to {}".format(output_csv)); print("Report written to {}".format(report_path))
    return report_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    run(args.data_dir)
