"""Synthetic checks for the fixed NY sweep baseline; no external test framework."""
import csv
import datetime as dt
import tempfile
from unittest.mock import patch
from pathlib import Path

import ny_sweep_backtest as bt


def bar(minute, o=101, h=102, l=100.5, c=101):
    return bt.Bar(dt.datetime(2025, 1, 6, minute // 60, minute % 60, tzinfo=bt.NY), o, h, l, c)


def run():
    checks = 0

    def check(name, condition):
        nonlocal checks
        assert condition, name
        checks += 1
        print('PASS', name)

    sweep = bar(585, 101, 102, 99, 101)
    setup = bt.find_setup(sweep, [('PDL', 100, 1)])
    check('long sweep trigger and stop', setup.trigger == 102.25 and setup.stop == 98.5)
    short = bt.find_setup(bar(585, 99, 101, 98, 99), [('PDH', 100, -1)])
    check('short symmetry', short.trigger == 97.75 and short.stop == 101.5)
    check('must reclaim strictly', bt.find_setup(bar(585, 100, 102, 99, 100), [('PDL', 100, 1)]) is None)
    check('reject two-sided sweep', bt.find_setup(sweep, [('PDL', 100, 1), ('PDH', 101.5, -1)]) is None)
    check('stop before target', bt.exit_price(bar(600, 101, 110, 95), 1, 98, 108, .25) == (97.75, 'stop'))
    check('long gap stop', bt.exit_price(bar(600, 95, 99, 94, 96), 1, 98, 108, .25) == (94.75, 'stop'))
    check('short gap stop', bt.exit_price(bar(600, 105, 106, 99, 104), -1, 102, 92, .25) == (105.25, 'stop'))

    def sample():
        bars = [bar(m) for m in range(571, 721)]
        bars[14] = sweep
        bars[15] = bar(586, 101, 103, 100.5, 102)
        return bars

    levels = lambda time: [('PDL', 100, 1)]
    trades = bt.simulate(sample(), levels)
    t = trades[0]
    check('entry only after completed setup', len(trades) == 1 and '09:46:' in t['entry_time'])
    check('entry slippage and 2R target', t['entry'] == 102.5 and t['target'] == 110.5)
    check('noon liquidation and costs', t['reason'] == 'noon' and t['exit'] == 100.75 and t['net'] == -40)
    bars = sample()
    bars[15] = bar(586, 101, 111, 100.5, 102)
    check('no entry-minute target credit', bt.simulate(bars, levels)[0]['reason'] == 'noon')
    bars[16] = bar(587, 102, 111, 101, 110)
    check('subsequent target fill', bt.simulate(bars, levels)[0]['reason'] == 'target')
    bars[15] = bar(586, 101, 111, 98, 102)
    check('entry-minute stop conservative', bt.simulate(bars, levels)[0]['exit'] == 98.25)
    bars = sample()
    bars[15:25] = [bar(m) for m in range(586, 596)]
    bars[25] = bar(596, 101, 103, 100.5, 102)
    check('pending expires after ten minutes', not bt.simulate(bars, levels))
    bars = sample()
    bars[16] = bar(587, 101, 102, 98, 100)
    micro = bt.simulate(bars, levels, point_value=2, commission=1)
    check('MNQ point value and commission', micro[0]['net'] == -9.5)
    try:
        bt.simulate(sample()[:16], levels)
    except ValueError:
        check('reject truncated open position', True)
    else:
        check('reject truncated open position', False)
    check('complete session', bt.complete_session([bar(m) for m in range(571, 961)]))
    check('reject incomplete session', not bt.complete_session(sample()))
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'minutes.csv'
        path.write_text('timestamp_utc,open,high,low,close,volume\n'
                        '2025-01-06T14:31:00Z,101,102,100,101,1\n'
                        '2025-07-07T13:31:00Z,101,102,100,101,1\n', encoding='utf-8')
        days = list(bt.read_days(path))
        check('NY daylight saving conversion', len(days) == 2 and all(b[0].time.hour == 9 and b[0].time.minute == 31 for _, b in days))
    # CSV-level regression: afternoon deletion must not remove morning trades.
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / 'coverage.csv'

        def run_days(day_bars):
            with path.open('w', newline='', encoding='utf-8') as stream:
                writer = csv.writer(stream)
                writer.writerow(['timestamp_utc', 'open', 'high', 'low', 'close', 'volume'])
                for bars in day_bars:
                    for b in bars:
                        writer.writerow([b.time.astimezone(dt.timezone.utc).isoformat(),
                                         b.open, b.high, b.low, b.close, 1])
            return bt.backtest(path, 20, 5, 1)

        full = [bar(m) for m in range(571, 961)]
        full[19] = bar(590, 101, 102, 99, 101)
        full[20] = bar(591, 101, 103, 100.5, 102)
        full_trades, full_coverage = run_days([full])
        morning_trades, morning_coverage = run_days([full[:150]])
        check('afternoon deletion preserves exact morning trades',
              len(full_trades) == 1 and full_trades == morning_trades)
        check('execution coverage separate from full-session coverage',
              morning_coverage['execution_sessions'] == 1
              and morning_coverage['complete_sessions'] == 0
              and full_coverage['complete_sessions'] == 1)
        for label, missing in [('first minute', 0), ('middle minute', 60), ('noon', 149)]:
            incomplete = full[:150]
            del incomplete[missing]
            found, coverage = run_days([incomplete])
            check('exclude missing ' + label, not found
                  and coverage['execution_sessions'] == 0
                  and coverage['skipped_sessions'][0]['reason'] == 'incomplete_morning')

        tomorrow = [bt.Bar(b.time + dt.timedelta(days=1), b.open, b.high, b.low, b.close)
                    for b in full[:150]]

        def capture_levels(bars, levels, *costs):
            captured.append(levels(bars[14].time))
            return []

        captured = []
        with patch.object(bt, 'simulate', side_effect=capture_levels):
            run_days([full, tomorrow])
        check('complete prior day supplies PDH and PDL',
              captured[1][:2] == [('PDL', 99, 1), ('PDH', 103, -1)])
        captured = []
        with patch.object(bt, 'simulate', side_effect=capture_levels):
            run_days([full[:150], tomorrow])
        check('incomplete prior day supplies only opening range',
              [name for name, _, _ in captured[1]] == ['ORL', 'ORH'])
        captured = []
        third = [bt.Bar(b.time + dt.timedelta(days=2), b.open, b.high, b.low, b.close)
                 for b in full[:150]]
        with patch.object(bt, 'simulate', side_effect=capture_levels):
            run_days([full, tomorrow[1:], third])
        check('skipped day clears older prior-day references',
              len(captured) == 2
              and [name for name, _, _ in captured[1]] == ['ORL', 'ORH'])

    check('empty metrics defined', bt.metrics([])['trades'] == 0)
    print(f'All {checks} checks passed')


if __name__ == '__main__':
    run()
