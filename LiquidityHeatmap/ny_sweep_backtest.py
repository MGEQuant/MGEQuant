"""Fixed NY sweep/reclaim research baseline. No live orders.
Input: UTC one-minute OHLCV; timestamps assumed to mark bar CLOSE.
"""
import argparse
import csv
import datetime as dt
import json
import math
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo('America/New_York')
TICK = 0.25


@dataclass(frozen=True)
class Bar:
    time: dt.datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class Setup:
    time: dt.datetime
    side: int
    level: float
    name: str
    trigger: float
    stop: float


def read_days(path):
    """Stream sorted UTC data; retain cash-session minute closes only."""
    previous, day, bars = None, None, []
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        reader = csv.DictReader(stream)
        needed = {'timestamp_utc', 'open', 'high', 'low', 'close', 'volume'}
        if not needed.issubset(reader.fieldnames or []):
            raise ValueError('CSV requires timestamp_utc,open,high,low,close,volume')
        for row_number, row in enumerate(reader, 2):
            stamp = dt.datetime.fromisoformat(row['timestamp_utc'])
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=dt.timezone.utc)
            stamp = stamp.astimezone(dt.timezone.utc)
            if previous is not None and stamp <= previous:
                raise ValueError(f'Unsorted or duplicate timestamp at row {row_number}')
            previous = stamp
            local = stamp.astimezone(NY)
            minute = local.hour * 60 + local.minute
            if local.second or local.microsecond:
                raise ValueError(f'Non-minute timestamp at row {row_number}')
            if local.weekday() >= 5 or not 570 < minute <= 960:
                continue
            o, h, l, c = [float(row[k]) for k in ('open', 'high', 'low', 'close')]
            if not all(math.isfinite(v) for v in (o, h, l, c)) or not l <= min(o, c) <= max(o, c) <= h:
                raise ValueError(f'Invalid OHLC at row {row_number}')
            if day != local.date():
                if bars:
                    yield day, bars
                day, bars = local.date(), []
            bars.append(Bar(local, o, h, l, c))
        if bars:
            yield day, bars


def complete_session(bars):
    return len(bars) == 390 and all(
        b.time.hour * 60 + b.time.minute == 571 + i
        for i, b in enumerate(bars))


def aggregate(bars):
    return Bar(bars[-1].time, bars[0].open, max(b.high for b in bars),
               min(b.low for b in bars), bars[-1].close)


def find_setup(bar, levels):
    candidates = []
    for name, level, side in levels:
        swept = (bar.low <= level - 2 * TICK and bar.close > level) if side == 1 else (
            bar.high >= level + 2 * TICK and bar.close < level)
        if swept:
            trigger = bar.high + TICK if side == 1 else bar.low - TICK
            stop = bar.low - 2 * TICK if side == 1 else bar.high + 2 * TICK
            candidates.append(Setup(bar.time, side, level, name, trigger, stop))
    # Skip two-sided sweeps; PD levels have deterministic priority otherwise.
    if len({s.side for s in candidates}) > 1:
        return None
    return candidates[0] if candidates else None


def exit_price(bar, side, stop, target, slippage):
    """Conservative OHLC execution: stop wins if both prices trade."""
    stop_hit = bar.low <= stop if side == 1 else bar.high >= stop
    target_hit = bar.high >= target if side == 1 else bar.low <= target
    if stop_hit:
        base = min(bar.open, stop) if side == 1 else max(bar.open, stop)
        return base - side * slippage, 'stop'
    if target_hit:
        return target, 'target'
    return None


def simulate(bars, levels, point_value=20.0, commission=5.0, slip_ticks=1.0):
    """One contract, two fills/day. levels(time) supplies already-known levels.
    Supply contiguous minute-close bars through noon if a position remains open.
    """
    pending, position = None, None
    trades, window = [], []
    fills, blocked_until = 0, None
    slip = slip_ticks * TICK
    for bar in bars:
        minute = bar.time.hour * 60 + bar.time.minute
        if minute > 720:
            break
        if window and bar.time - window[-1].time != dt.timedelta(minutes=1):
            raise ValueError('Execution bars must be contiguous one-minute bars')
        window.append(bar)
        window = window[-5:]
        if pending and (minute > 690 or bar.time > pending.time + dt.timedelta(minutes=10)):
            pending = None
        entered = False
        if pending and position is None:
            side = pending.side
            touched = bar.high >= pending.trigger if side == 1 else bar.low <= pending.trigger
            if touched:
                entry = (max(bar.open, pending.trigger) if side == 1 else min(bar.open, pending.trigger)) + side * slip
                risk = side * (entry - pending.stop)
                position = (pending, entry, risk, entry + side * 2 * risk, bar.time)
                fills += 1
                entered = True
                pending = None
        if position:
            setup, entry, risk, target, entry_time = position
            outcome = exit_price(bar, setup.side, setup.stop, target, slip)
            if entered and outcome and outcome[1] == 'stop':
                outcome = (setup.stop - setup.side * slip, 'stop')
            # Favorable entry-minute ordering is unknown: do not credit targets.
            if entered and outcome and outcome[1] == 'target':
                outcome = None
            if outcome is None and minute == 720:
                outcome = (bar.close - setup.side * slip, 'noon')
            if outcome:
                price, reason = outcome
                gross = setup.side * (price - entry) * point_value
                net = gross - commission
                trades.append(dict(date=str(bar.time.date()), level_name=setup.name,
                    level=setup.level, side='long' if setup.side == 1 else 'short',
                    setup_time=setup.time.isoformat(), entry_time=entry_time.isoformat(),
                    exit_time=bar.time.isoformat(), entry=entry, stop=setup.stop,
                    target=target, exit=price, reason=reason, gross=gross, net=net,
                    net_r=net / (risk * point_value)))
                position = None
                blocked_until = bar.time + dt.timedelta(minutes=(5 - minute % 5) % 5)
        if minute % 5 == 0 and len(window) == 5:
            signal = aggregate(window)
            if pending:
                invalid = signal.close <= pending.level if pending.side == 1 else signal.close >= pending.level
                if invalid or bar.time >= pending.time + dt.timedelta(minutes=10):
                    pending = None
            if (585 <= minute < 690 and not pending and not position and fills < 2
                    and (blocked_until is None or bar.time > blocked_until)):
                pending = find_setup(signal, levels(bar.time))
    if position:
        raise ValueError('Open position at end of input: need minute bars through noon')
    return trades


def metrics(trades):
    nets = [t['net'] for t in trades]
    wins = sum(v > 0 for v in nets)
    losses = -sum(v for v in nets if v < 0)
    equity = peak = drawdown = 0.0
    for value in nets:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return dict(trades=len(nets), wins=wins,
                win_rate_pct=100 * wins / len(nets) if nets else None,
                net_dollars=sum(nets), expectancy_dollars=sum(nets)/len(nets) if nets else None,
                mean_net_r=sum(t['net_r'] for t in trades)/len(nets) if nets else None,
                profit_factor=sum(v for v in nets if v > 0)/losses if losses else None,
                closed_trade_max_drawdown=drawdown)


def backtest(path, point_value, commission, slip_ticks):
    trades, skipped = [], []
    prior = None
    sessions = execution_sessions = 0
    first = last = None
    for day, bars in read_days(path):
        first = first or str(day)
        last = str(day)
        full_session = complete_session(bars)
        morning = [b for b in bars if b.time.hour * 60 + b.time.minute <= 720]
        morning_complete = len(morning) == 150 and all(
            b.time.hour * 60 + b.time.minute == 571 + i
            for i, b in enumerate(morning))
        if full_session:
            sessions += 1
        if not morning_complete:
            skipped.append(dict(date=str(day), minute_bars=len(bars),
                                reason='incomplete_morning'))
            prior = None
            continue
        execution_sessions += 1
        opening = aggregate(morning[:15])
        fixed = [('PDL', prior[1], 1), ('PDH', prior[0], -1)] if prior else []

        def levels(time):
            if time.hour * 60 + time.minute >= 585:
                return fixed + [('ORL', opening.low, 1), ('ORH', opening.high, -1)]
            return fixed

        trades.extend(simulate(morning, levels, point_value, commission, slip_ticks))
        # Afternoon completeness controls tomorrow's references, not today's trades.
        prior = (max(b.high for b in bars), min(b.low for b in bars)) if full_session else None
    return trades, dict(first_date=first, last_date=last, complete_sessions=sessions,
                        execution_sessions=execution_sessions, skipped_sessions=skipped)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--symbol', choices=['NQ', 'MNQ'], default='NQ')
    parser.add_argument('--commission', type=float, required=True, help='Round-trip dollars per contract')
    parser.add_argument('--slippage-ticks', type=float, required=True, help='Adverse ticks per market/stop fill')
    args = parser.parse_args()
    if not all(math.isfinite(v) and v >= 0 for v in (args.commission, args.slippage_ticks)):
        parser.error('Costs must be finite and nonnegative')
    trades, coverage = backtest(args.csv, 20 if args.symbol == 'NQ' else 2,
                               args.commission, args.slippage_ticks)
    report = dict(input=str(args.csv.resolve()), symbol=args.symbol,
                  commission_round_trip=args.commission, slippage_ticks=args.slippage_ticks,
                  timestamp_assumption='UTC minute CLOSE; vendor convention unverified',
                  coverage_policy='morning_0931_1200_v2; PDH/PDL require complete prior observed cash session',
                  warning='Research only: complete-morning selection bias, no exchange holiday calendar or absent-session detection, OHLC fill uncertainty. Not out-of-sample validation.',
                  coverage=coverage, overall=metrics(trades),
                  by_year={year: metrics([t for t in trades if t['date'].startswith(year)])
                           for year in sorted({t['date'][:4] for t in trades})})
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'summary.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    columns = ['date', 'level_name', 'level', 'side', 'setup_time', 'entry_time', 'exit_time',
               'entry', 'stop', 'target', 'exit', 'reason', 'gross', 'net', 'net_r']
    with (args.out / 'trades.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(trades)
    print(json.dumps(dict(overall=report['overall'], complete_sessions=coverage['complete_sessions'],
                          execution_sessions=coverage['execution_sessions'],
                          skipped_sessions=len(coverage['skipped_sessions'])), indent=2))


if __name__ == '__main__':
    main()

