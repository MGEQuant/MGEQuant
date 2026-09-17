"""Replay a fixed sample of saved trades and export candles for chart review."""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo
import ny_sweep_backtest as bt

PACIFIC = ZoneInfo('America/Los_Angeles')
NUMERIC = {'level', 'entry', 'stop', 'target', 'exit', 'gross', 'net', 'net_r'}


def audit(results, out):
    if out.exists():
        raise FileExistsError('Use a new output directory; existing audits are preserved')
    report = json.loads((results / 'summary.json').read_text(encoding='utf-8'))
    with (results / 'trades.csv').open(newline='', encoding='utf-8') as stream:
        trades = list(csv.DictReader(stream))
    selected = {}
    for trade in sorted(trades, key=lambda t: (t['entry_time'], t['exit_time'])):
        selected.setdefault((trade['level_name'], trade['reason']), trade)
    if not selected:
        raise ValueError('No saved trades')
    dates = {t['date'] for t in selected.values()}
    sessions, references, prior = {}, {}, None
    for day, bars in bt.read_days(Path(report['input'])):
        date = str(day)
        if date in dates:
            sessions[date], references[date] = bars, prior
        morning = [b for b in bars if b.time.hour * 60 + b.time.minute <= 720]
        valid = len(morning) == 150 and all(
            b.time.hour * 60 + b.time.minute == 571 + i for i, b in enumerate(morning))
        prior = (max(b.high for b in bars), min(b.low for b in bars)) if valid and bt.complete_session(bars) else None
        if date >= max(dates):
            break
    checks, candles = [], []
    for number, saved in enumerate(selected.values(), 1):
        sample = f'S{number:02d}'
        bars = sessions[saved['date']]
        morning = [b for b in bars if b.time.hour * 60 + b.time.minute <= 720]
        opening = bt.aggregate(morning[:15])
        prior = references[saved['date']]
        fixed = [('PDL', prior[1], 1), ('PDH', prior[0], -1)] if prior else []

        def levels(time):
            return fixed + ([('ORL', opening.low, 1), ('ORH', opening.high, -1)]
                            if time.hour * 60 + time.minute >= 585 else [])

        replay = bt.simulate(morning, levels, 20 if report['symbol'] == 'NQ' else 2,
                             report['commission_round_trip'], report['slippage_ticks'])
        matches = [t for t in replay if t['entry_time'] == saved['entry_time']]
        assert len(matches) == 1, sample
        for key, value in saved.items():
            actual = matches[0][key]
            assert (math.isclose(float(value), actual, rel_tol=1e-10, abs_tol=1e-8)
                    if key in NUMERIC else value == actual), (sample, key)
        setup_time, entry_time, exit_time = [dt.datetime.fromisoformat(saved[k])
            for k in ('setup_time', 'entry_time', 'exit_time')]
        window = [b for b in bars if setup_time - dt.timedelta(minutes=5) < b.time <= setup_time]
        assert len(window) == 5, sample
        signal = bt.aggregate(window)
        setup = bt.find_setup(signal, levels(setup_time))
        assert setup and setup.name == saved['level_name'] and setup.level == float(saved['level']), sample
        assert setup_time < entry_time <= setup_time + dt.timedelta(minutes=10), sample
        entry_bar = next(b for b in bars if b.time == entry_time)
        slip = report['slippage_ticks'] * bt.TICK
        expected = (max(entry_bar.open, setup.trigger) if setup.side == 1
                    else min(entry_bar.open, setup.trigger)) + setup.side * slip
        assert expected == float(saved['entry']) and setup.stop == float(saved['stop']), sample
        ambiguous = []
        for bar in bars:
            if entry_time <= bar.time <= exit_time:
                stop_hit = bar.low <= setup.stop if setup.side == 1 else bar.high >= setup.stop
                target_hit = bar.high >= float(saved['target']) if setup.side == 1 else bar.low <= float(saved['target'])
                if (stop_hit and target_hit) or (bar.time == entry_time and (stop_hit or target_hit)):
                    ambiguous.append(bar.time.isoformat())
            if setup_time - dt.timedelta(minutes=5) < bar.time <= exit_time:
                candles.append(dict(sample=sample, utc=bar.time.astimezone(dt.timezone.utc).isoformat(),
                    new_york=bar.time.isoformat(), pacific=bar.time.astimezone(PACIFIC).isoformat(),
                    open=bar.open, high=bar.high, low=bar.low, close=bar.close))
        checks.append(dict(sample=sample, **saved, trigger=setup.trigger,
            setup_ohlc=[signal.open, signal.high, signal.low, signal.close],
            setup_pacific=setup_time.astimezone(PACIFIC).isoformat(),
            entry_pacific=entry_time.astimezone(PACIFIC).isoformat(),
            exit_pacific=exit_time.astimezone(PACIFIC).isoformat(),
            ambiguous_minutes=ambiguous, replay_matches=True))
    save(out, checks, candles)


def save(out, checks, candles):
    out.mkdir(parents=True, exist_ok=False)
    (out / 'samples.json').write_text(json.dumps(checks, indent=2), encoding='utf-8')
    with (out / 'candles.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(candles[0]))
        writer.writeheader()
        writer.writerows(candles)
    lines = ['# Fixed-sample trade review', '',
        'Selection: earliest saved entry in each observed (level name, exit reason) category.',
        'Every saved field in this sample matches a replay of the existing simulator.',
        'Setup aggregation, level selection, trigger, stop and entry arithmetic were checked.',
        '**Internal consistency only: this does not independently validate execution or chart prices.**', '',
        'Prices are back-adjusted continuous prices, not necessarily raw contract prices.',
        'Pacific times use America/Los_Angeles with DST, not fixed UTC-08:00.',
        'Times label minute closes, not exact intraminute fills.', '',
        '| ID | Level / exit | NY setup | Pacific setup | Trigger | Entry | Stop | Target | Ambiguous minutes |',
        '| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for c in checks:
        lines.append(f"| {c['sample']} | {c['level_name']} / {c['reason']} | {c['setup_time']} | {c['setup_pacific']} | {c['trigger']} | {c['entry']} | {c['stop']} | {c['target']} | {len(c['ambiguous_minutes'])} |")
    lines += ['', '## Manual NinjaTrader checklist', '',
        '- [ ] Record contract, provider, timezone, trading-hours template and merge policy.',
        '- [ ] Reconcile the raw contract prices with the continuous adjustment.',
        '- [ ] Compare setup minute candles and five-minute OHLC in samples.json.',
        '- [ ] Check prior complete cash-session high/low or 09:30-09:45 ET opening range.',
        '- [ ] Compare entry/exit minute candles in candles.csv; review gap/slippage assumptions.',
        '- [ ] Review ambiguous_minutes with tick data if available; OHLC cannot prove ordering.',
        '- [ ] Record agreements/disagreements; independent chart verification remains pending.', '',
        'Ambiguity flags cover both stop/target touches and entry-minute exit touches.',
        'They are not a comprehensive execution-quality assessment.',
        'No strategy rules, original result files, indicators or live orders were changed.']
    (out / 'CHART_REVIEW.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(dict(samples=len(checks), candle_rows=len(candles),
        samples_with_ambiguity=sum(bool(c['ambiguous_minutes']) for c in checks), output=str(out)), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    audit(args.results, args.out)
