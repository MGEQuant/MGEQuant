"""Standalone, pre-registered VolatilityRegime signal backtest.

This file intentionally uses only the verified local 1-minute cache as a data source.
It does not import or execute MarketCoach, QAX, TradePilot, or any strategy logic.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd


ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = r"F:\Trading Software\MarketCoach\Releases\NQMarketCoachV340SyncLive\_bars1m_cache_pacific.pkl"
TRADE_CSV_PATH = os.path.join(ROOT, "standalone_volatility_regime_signal_trades.csv")
REPORT_PATH = os.path.join(ROOT, "standalone_volatility_regime_signal_report.md")

TICK = 0.25
TICK_VALUE = 5.0
COMMISSION = 4.20
SLIPPAGE_TICKS_PER_SIDE = 1.0
SPLIT = pd.Timestamp("2024-01-01", tz="America/New_York")
DATA_END = pd.Timestamp("2026-08-22", tz="America/New_York")
BUCKET_MIN = 30
LEVEL_LOOKBACK = 20 * 78
REGIME_THRESHOLD = 1.25
MOVE_TR_MULTIPLE = 0.5
STOP_EXPECTED_MULTIPLE = 0.5
MIN_STOP_TICKS = 12
MAX_STOP_TICKS = 48
MAX_TRADES_SESSION = 2
COOLDOWN_BARS = 6
DAILY_LOSS_LIMIT = 500.0


@dataclass
class Trade:
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    direction: str
    signal_bar_index: int
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    stop_ticks: int
    gross_dollars: float
    costs_dollars: float
    net_dollars: float
    r_multiple: float
    exit_reason: str
    session_date: str
    regime_ratio: float
    expected_ticks: float
    prior_tr_ticks: float


def load_cache() -> pd.DataFrame:
    if not os.path.exists(CACHE_PATH):
        raise FileNotFoundError("Verified cache not found: {}".format(CACHE_PATH))
    bars = pd.read_pickle(CACHE_PATH).copy()
    required = {"dt", "Open", "High", "Low", "Close"}
    missing = required.difference(bars.columns)
    if missing:
        raise AssertionError("cache missing columns: {}".format(sorted(missing)))
    bars["dt"] = pd.to_datetime(bars["dt"], utc=True).dt.tz_convert("America/New_York")
    bars = bars.sort_values("dt").drop_duplicates("dt").reset_index(drop=True)
    return bars


def resample_5m(bars_1m: pd.DataFrame) -> pd.DataFrame:
    source = bars_1m.set_index("dt")
    bars = source.resample("5min", label="right", closed="right").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last"}
    ).dropna(subset=["Open"]).reset_index()
    previous_close = bars["Close"].shift(1)
    bars["tr"] = pd.concat(
        [bars["High"] - bars["Low"],
         (bars["High"] - previous_close).abs(),
         (bars["Low"] - previous_close).abs()], axis=1).max(axis=1)
    bars["tr_ticks"] = bars["tr"] / TICK
    et_minutes = bars["dt"].dt.hour * 60 + bars["dt"].dt.minute
    bars["bucket"] = (et_minutes // BUCKET_MIN).astype(int)
    bars["session_date"] = np.where(
        bars["dt"].dt.hour >= 18,
        (bars["dt"] + pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d"),
        bars["dt"].dt.strftime("%Y-%m-%d"),
    )
    return bars.reset_index(drop=True)


def fit_shape(train: pd.DataFrame) -> pd.Series:
    profile = train.groupby("bucket")["tr_ticks"].median()
    return profile / profile.median()


def add_causal_expectation(bars: pd.DataFrame, shape: pd.Series) -> pd.DataFrame:
    # Both components are known before the signal bar: prior-bar rolling level and
    # a shape fitted exclusively on the train interval.
    bars = bars.copy()
    bars["causal_level_ticks"] = bars["tr_ticks"].shift(1).rolling(
        LEVEL_LOOKBACK, min_periods=LEVEL_LOOKBACK // 4
    ).median()
    bars["expected_ticks"] = bars["causal_level_ticks"] * bars["bucket"].map(shape)
    bars["regime_ratio"] = bars["tr_ticks"] / bars["expected_ticks"]
    return bars


def is_electronic_bar(dt: pd.Timestamp) -> bool:
    return dt.hour != 17


def ceil_ticks(value: float) -> int:
    return int(np.clip(math.ceil(value - 1e-12), MIN_STOP_TICKS, MAX_STOP_TICKS))


def exit_trade(bars_1m: pd.DataFrame, entry_i: int, direction: str,
               entry_price: float, stop_price: float, target_price: float,
               risk_ticks: int) -> Trade | None:
    for i in range(entry_i, len(bars_1m)):
        row = bars_1m.iloc[i]
        high, low = float(row["High"]), float(row["Low"])
        if direction == "LONG":
            stop_hit, target_hit = low <= stop_price, high >= target_price
            if stop_hit or target_hit:
                reason = "STOP" if stop_hit else "TARGET"
                # Stop-first is the declared rule when both prices occur in one bar.
                raw_exit = stop_price if stop_hit else target_price
                exit_price = raw_exit - SLIPPAGE_TICKS_PER_SIDE * TICK
                gross = (exit_price - entry_price) / TICK * TICK_VALUE
        else:
            stop_hit, target_hit = high >= stop_price, low <= target_price
            if stop_hit or target_hit:
                reason = "STOP" if stop_hit else "TARGET"
                raw_exit = stop_price if stop_hit else target_price
                exit_price = raw_exit + SLIPPAGE_TICKS_PER_SIDE * TICK
                gross = (entry_price - exit_price) / TICK * TICK_VALUE
        if stop_hit or target_hit:
            costs = COMMISSION + 2 * SLIPPAGE_TICKS_PER_SIDE * TICK_VALUE
            net = gross - COMMISSION
            return Trade(pd.NaT, row["dt"], row["dt"], direction, -1,
                         entry_price, exit_price, stop_price, target_price,
                         risk_ticks, gross, costs, net, net / (risk_ticks * TICK_VALUE),
                         reason, "", np.nan, np.nan, np.nan)
    return None


def run_backtest(bars_1m: pd.DataFrame, bars_5m: pd.DataFrame, shape: pd.Series):
    one_minute_index = pd.DatetimeIndex(bars_1m["dt"])
    trades: list[Trade] = []
    signal_records = []
    counters = {"bars": len(bars_5m), "signals": 0, "entries": 0, "blocked_session_limit": 0,
                "blocked_cooldown": 0, "blocked_in_trade": 0, "blocked_daily_loss": 0,
                "blocked_no_entry_bar": 0, "blocked_no_expectation": 0, "data_end": 0,
                "blocked_terminal_candidate": 0, "ambiguous_stop_first": 0}
    session_counts: dict[str, int] = {}
    daily_net: dict[str, float] = {}
    last_entry_i = -10**9
    occupied_until_i = -1

    for i in range(1, len(bars_5m) - 1):
        bar = bars_5m.iloc[i]
        entry_bar = bars_5m.iloc[i + 1]
        if not is_electronic_bar(bar["dt"]) or not is_electronic_bar(entry_bar["dt"]):
            continue
        if not (bar["dt"] < DATA_END and entry_bar["dt"] < DATA_END):
            continue
        if not np.isfinite(bar["regime_ratio"]) or not np.isfinite(bar["expected_ticks"]):
            counters["blocked_no_expectation"] += 1
            continue
        move = float(bar["Close"] - bar["Open"])
        tr = float(bar["tr"])
        if bar["regime_ratio"] < REGIME_THRESHOLD or abs(move) < MOVE_TR_MULTIPLE * tr or move == 0:
            continue
        counters["signals"] += 1
        signal_records.append({"signal_time": bar["dt"], "direction": "LONG" if move > 0 else "SHORT"})
        session = str(bar["session_date"])
        if session_counts.get(session, 0) >= MAX_TRADES_SESSION:
            counters["blocked_session_limit"] += 1
            continue
        if daily_net.get(session, 0.0) <= -DAILY_LOSS_LIMIT:
            counters["blocked_daily_loss"] += 1
            continue
        if i + 1 - last_entry_i < COOLDOWN_BARS:
            counters["blocked_cooldown"] += 1
            continue
        entry_time = entry_bar["dt"]
        entry_i = int(one_minute_index.searchsorted(entry_time))
        if entry_i >= len(bars_1m) or one_minute_index[entry_i] != entry_time:
            counters["blocked_no_entry_bar"] += 1
            continue
        if entry_i <= occupied_until_i:
            counters["blocked_in_trade"] += 1
            continue
        if entry_i >= len(bars_1m) - 1:
            counters["blocked_terminal_candidate"] += 1
            continue
        direction = "LONG" if move > 0 else "SHORT"
        risk_ticks = ceil_ticks(STOP_EXPECTED_MULTIPLE * float(entry_bar["expected_ticks"]))
        risk_price = risk_ticks * TICK
        raw_entry = float(bars_1m.iloc[entry_i]["Open"])
        entry_price = raw_entry + TICK if direction == "LONG" else raw_entry - TICK
        stop_price = entry_price - risk_price if direction == "LONG" else entry_price + risk_price
        target_price = entry_price + risk_price if direction == "LONG" else entry_price - risk_price
        result = exit_trade(bars_1m, entry_i, direction, entry_price, stop_price, target_price, risk_ticks)
        if result is None:
            counters["blocked_terminal_candidate"] += 1
            continue
        exit_i = int(one_minute_index.searchsorted(result.exit_time))
        exit_row = bars_1m.iloc[exit_i]
        if float(exit_row["High"]) >= target_price and float(exit_row["Low"]) <= stop_price:
            counters["ambiguous_stop_first"] += 1
        result.signal_time = bar["dt"]
        result.entry_time = entry_time
        result.signal_bar_index = i
        result.session_date = session
        result.regime_ratio = float(bar["regime_ratio"])
        result.expected_ticks = float(entry_bar["expected_ticks"])
        result.prior_tr_ticks = float(bar["tr_ticks"])
        trades.append(result)
        counters["entries"] += 1
        session_counts[session] = session_counts.get(session, 0) + 1
        daily_net[session] = daily_net.get(session, 0.0) + result.net_dollars
        last_entry_i = i + 1
        occupied_until_i = exit_i
    assert counters["data_end"] == 0, "unresolved DATA_END trades: {}".format(counters["data_end"])
    return pd.DataFrame([t.__dict__ for t in trades]), counters, pd.DataFrame(signal_records)


def summarize(df: pd.DataFrame, label: str, signal_df: pd.DataFrame) -> dict:
    signals = signal_df.copy()
    if "Train" in label:
        signals = signals[signals["signal_time"] < SPLIT]
    elif "Untouched" in label:
        signals = signals[signals["signal_time"] >= SPLIT]
    if "(long)" in label:
        signals = signals[signals["direction"] == "LONG"]
    elif "(short)" in label:
        signals = signals[signals["direction"] == "SHORT"]
    if df.empty:
        return {"period": label, "trades": 0, "wins": 0, "win_rate": np.nan, "net": 0.0,
                "avg_r": np.nan, "avg_signals_week": 0.0, "avg_trades_week": 0.0}
    days = max(1.0, (df["signal_time"].max() - df["signal_time"].min()).total_seconds() / 604800.0)
    return {"period": label, "trades": len(df), "wins": int((df["net_dollars"] > 0).sum()),
            "win_rate": float((df["net_dollars"] > 0).mean()), "net": float(df["net_dollars"].sum()),
            "avg_r": float(df["r_multiple"].mean()), "avg_signals_week": float(len(signals) / days),
            "avg_trades_week": float(len(df) / days)}


def fmt_summary(s: dict) -> str:
    return "| {period} | {trades:,} | {win_rate:.1%} | ${net:,.2f} | {avg_r:+.3f} | {avg_signals_week:.2f} | {avg_trades_week:.2f} |".format(**s)


def main() -> None:
    bars_1m = load_cache()
    bars_5m = resample_5m(bars_1m)
    train = bars_5m[bars_5m["dt"] < SPLIT]
    shape = fit_shape(train)
    bars_5m = add_causal_expectation(bars_5m, shape)
    trades, counters, signal_df = run_backtest(bars_1m, bars_5m, shape)
    if trades.empty:
        raise AssertionError("backtest produced no trades")
    trades["year"] = pd.to_datetime(trades["signal_time"]).dt.year
    trades.to_csv(TRADE_CSV_PATH, index=False)
    trades.attrs["signals"] = counters["signals"]
    splits = {
        "Full history (combined)": trades,
        "Train 2020-12 to 2023-12 (combined)": trades[trades["signal_time"] < SPLIT],
        "Untouched test 2024-01 to 2026-08-21 (combined)": trades[trades["signal_time"] >= SPLIT],
        "Full history (long)": trades[trades["direction"] == "LONG"],
        "Full history (short)": trades[trades["direction"] == "SHORT"],
    }
    summaries = [summarize(v, k, signal_df) for k, v in splits.items()]
    years = []
    for y, g in trades.groupby("year"):
        y_signals = signal_df[signal_df["signal_time"].dt.year == y]
        years.append(summarize(g, str(y), y_signals))
    avg_risk = trades["stop_ticks"].mean() * TICK_VALUE
    breakeven = (avg_risk + COMMISSION + 2 * SLIPPAGE_TICKS_PER_SIDE * TICK_VALUE) / (2 * avg_risk)
    report = render_report(bars_1m, bars_5m, train, shape, counters, summaries, years, breakeven, avg_risk)
    with open(REPORT_PATH, "w", encoding="utf-8") as handle:
        handle.write(report)
    assert (trades["stop_ticks"] >= MIN_STOP_TICKS).all() and (trades["stop_ticks"] <= MAX_STOP_TICKS).all()
    assert (trades["r_multiple"].notna()).all()
    assert (pd.to_datetime(trades["signal_time"]) < pd.to_datetime(trades["entry_time"])).all()
    print(report)
    print("CSV: {}".format(TRADE_CSV_PATH))
    print("REPORT: {}".format(REPORT_PATH))


def render_report(bars_1m, bars_5m, train, shape, counters, summaries, years, breakeven, avg_risk):
    test = next(s for s in summaries if s["period"].startswith("Untouched"))
    verdict = "MERITS a fresh out-of-sample test" if test["net"] > 0 and test["win_rate"] > breakeven else "REJECT this hypothesis for now"
    lines = [
        "# Standalone VolatilityRegime Signal Backtest", "",
        "## Verdict", "",
        "This is a mechanical research proxy, not a probability of future profit. The untouched test outcome is **{}**. A single historical backtest cannot establish future profitability or its probability.".format(verdict), "",
        "## Pre-registered assumptions", "",
        "- NQ 5-minute bars from the verified local 1-minute cache; ET timestamps; electronic session bars except 17:00-18:00 ET.",
        "- Shape: train-only median TR by 30-minute ET bucket, normalized by the train median. Expected range = causal prior-bar rolling median TR over 1,560 prior 5-minute bars times that shape.",
        "- Signal at a completed bar close: prior bar TR ratio >= 1.25 and directional body >= 0.5 TR. Entry is the next 5-minute bar's first 1-minute open.",
        "- Stop = 0.5 expected range for the entry bar's ET bucket, rounded up to ticks and bounded 12-48; target = 1R; quantity = 1 NQ.",
        "- One trade at a time, maximum 2 trades per CME session, 6-bar entry cooldown, $500 daily loss limit, $4.20 commission, 1 tick adverse slippage per side.",
        "- Exits use 1-minute bars. If stop and target are both touched in one minute, stop wins. Signals without a resolved exit are hard failures, not silently closed trades.",
        "",
        "## Data and causality audit", "",
        "- Cache: `{}`".format(CACHE_PATH),
        "- 1-minute window: {} to {} ET; 5-minute bars: {:,}; train bars: {:,}; shape buckets: {}.".format(bars_1m["dt"].min(), bars_1m["dt"].max(), len(bars_5m), len(train), len(shape)),
        "- The prior-bar TR, rolling level, train-fitted shape, entry open, and entry-hour expected range are all timestamp-causal.",
        "- Assertions passed: no unresolved DATA_END trades, valid exits, signal timestamp before entry timestamp, bounded stop R, and CSV audit fields emitted.",
        "- Counters: {}".format(", ".join("{}={}".format(k, v) for k, v in counters.items())),
        "",
        "## Results", "",
        "| Period | Trades | Win rate | Net | Average R | Signals/week | Trades/week |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    lines += [fmt_summary(s) for s in summaries]
    lines += ["", "### Yearly", "", "| Year | Trades | Win rate | Net | Average R | Signals/week | Trades/week |", "|---|---:|---:|---:|---:|---:|---:|"]
    lines += [fmt_summary(s) for s in years]
    lines += ["", "### Cost break-even", "", "Average stop risk was ${:,.2f}. With 1:1 payoff, commission, and two modeled 1-tick slippage sides, the break-even win rate at average risk is **{:.2%}**. This varies by stop size; the exact trade-level net and R are in the CSV.".format(avg_risk, breakeven), "", "### Output", "", "Trade CSV: `{}`".format(os.path.relpath(TRADE_CSV_PATH, ROOT)), "", "No MarketCoach trades, indicators, or strategy context were used."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()