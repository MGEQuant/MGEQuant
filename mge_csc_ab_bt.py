N=15 pivot on 1-min (flag biggest sensitivity). NOTE: file ends 2026-09-10;
live 2026-09-15 session (j1-j8) is OUT OF RANGE of this data.
"""
import csv
import datetime as dt
import pathlib
import sys
from collections import deque

NQ_PATH = pathlib.Path('f:/Trading Software/backtest_lab/NQ_BackAdjusted/NQ_Continuous_Adjusted.csv')
OUT_DIR = pathlib.Path('f:/Trading Software/Shared/Automation/backtest')
OUT_CSV = OUT_DIR / 'csc_ab_backtest_results.csv'
LOG_DIR = pathlib.Path('f:/Trading Software/Shared/Automation/logs')
LOG_TXT = LOG_DIR / 'csc_ab_backtest_read.txt'
PIVOT_N = 15
AB_MIN_CONSECUTIVE_BREACH = 2
ACCEPT_HOUR_MIN = 0
ACCEPT_HOUR_MAX = 23
MAX_HISTORY = 2000

def parse_ts(ts):
    ts = ts.strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%m/%d/%Y %I:%M %p', '%m/%d/%Y %H:%M'):
        try:
            return dt.datetime.strptime(ts, fmt)
        except Exception:
            continue
    return None

def load_bars(path):
    bars = []
    with path.open('r', encoding='utf-8', errors='replace') as f:
        r = csv.reader(f)
        header = next(r)
        for row in r:
            if not row or not row[0].strip():
                continue
            d = parse_ts(row[0])
            if d is None:
                continue
            try:
                o = float(row[1])
                h = float(row[2])
                l = float(row[3])
                c = float(row[4])
                v = float(row[5]) if len(row) > 5 and row[5].strip() else 0.0
            except Exception:
                continue
            bars.append((d, o, h, l, c, v))
    return header, bars

class RecentPivot:
    def __init__(self, n):
        self.n = n
        self.q = deque(maxlen=n)

    def push(self, h, l):
        self.q.append((h, l))

    @property
    def ready(self):
        return len(self.q) >= self.n

    @property
    def high(self):
        return max(x[0] for x in self.q)

    @property
    def low(self):
        return min(x[1] for x in self.q)

class History:
    def __init__(self, maxlen):
        self.maxlen = maxlen
        self.ts = deque(maxlen=maxlen)
        self.o = deque(maxlen=maxlen)
        self.h = deque(maxlen=maxlen)
        self.l = deque(maxlen=maxlen)
        self.c = deque(maxlen=maxlen)
        self.v = deque(maxlen=maxlen)

    def push(self, d, o, h, l, c, v):
        self.ts.append(d)
        self.o.append(o)
        self.h.append(h)
        self.l.append(l)
        self.c.append(c)
        self.v.append(v)

    def recent(self, start_idx=-1, count=None):
        seq = list(zip(self.ts, self.o, self.h, self.l, self.c, self.v))
        if count is None:
            count = len(seq)
        if start_idx < 0:
            start_idx = len(seq) + start_idx
        start_idx = max(0, min(start_idx, len(seq) - 1))
        return [(i, *seq[i]) for i in range(start_idx, max(-1, start_idx - count), -1)]

def nearest_prior_level(hist, idx, direction, exclude_break=None):
    win = 5
    rows = list(hist.recent(idx, MAX_HISTORY))
    for p, (i, ts, o, h, l, c, v) in enumerate(rows):
        if direction == 'short':
            lo = max(0, p - win)
            hi = min(len(rows), p + win + 1)
            wh = max(rows[k][3] for k in range(lo, hi))
            if h == wh and (exclude_break is None or abs(h - exclude_break) > 0.01):
                return (h, i)
        else:
            lo = max(0, p - win)
            hi = min(len(rows), p + win + 1)
            wl = min(rows[k][4] for k in range(lo, hi))
            if l == wl and (exclude_break is None or abs(l - exclude_break) > 0.01):
                return (l, i)
    return None

def second_prior_level(hist, idx, direction, stop_level):
    win = 5
    rows = list(hist.recent(idx, MAX_HISTORY))
    ff = False
    for p, (i, ts, o, h, l, c, v) in enumerate(rows):
        if direction == 'short':
            lo = max(0, p - win)
            hi = min(len(rows), p + win + 1)
            wh = max(rows[k][3] for k in range(lo, hi))
            ex = (h == wh)
            if ex and abs(h - stop_level) > 0.01:
                if not ff:
                    ff = True
                    continue
                return (h, i)
        else:
            lo = max(0, p - win)
            hi = min(len(rows), p + win + 1)
            wl = min(rows[k][4] for k in range(lo, hi))
            ex = (l == wl)
            if ex and abs(l - stop_level) > 0.01:
                if not ff:
                    ff = True
                    continue
                return (l, i)
    return None

def mm_proj(breakout_point, base_range, direction):
    if direction == 'short':
        return breakout_point - 2.0 * base_range
    return breakout_point + 2.0 * base_range

def run_backtest(bars, header):
    """Scan bars with CSC + AB state machines; returns (results, triggers, piv_n, ab_min)."""
    hist = History(MAX_HISTORY)
    pivot = RecentPivot(PIVOT_N)
    csc = "idle"
    cinfo = {}
    ab = "idle"
    ainfo = {}
    results = []
    triggers = []

    def in_session(ts):
        return ACCEPT_HOUR_MIN <= ts.hour <= ACCEPT_HOUR_MAX

    for idx, (d, o, h, l, c, v) in enumerate(bars):
        hist.push(d, o, h, l, c, v)
        pivot.push(h, l)
        if not pivot.ready:
            continue

        # ---------------- CSC ----------------
        if csc == "idle":
            if c < pivot.low:
                csc = "broken"
                cinfo = dict(
                    break_dir="short",
                    break_level=pivot.low,
                    break_bar_idx=idx,
                    base_range=pivot.high - pivot.low,
                    breakout_point=c,
                )
            elif c > pivot.high:
                csc = "broken"
                cinfo = dict(
                    break_dir="long",
                    break_level=pivot.high,
                    break_bar_idx=idx,
                    base_range=pivot.high - pivot.low,
                    breakout_point=c,
                )
        elif csc == "broken":
            info = cinfo
            if info["break_dir"] == "short" and l >= info["break_level"] and c > info["break_level"]:
                csc = "holding"
                cinfo.update(hold_bar_idx=idx, hold_low=l, hold_high=h, hold_close=c)
            elif info["break_dir"] == "long" and h <= info["break_level"] and c < info["break_level"]:
                csc = "holding"
                cinfo.update(hold_bar_idx=idx, hold_low=l, hold_high=h, hold_close=c)
        elif csc == "holding":
            csc = "pending_entry"

        if csc == "pending_entry":
            info = cinfo
            entry_price = o
            stop_price = info["hold_high"] if info["break_dir"] == "short" else info["hold_low"]
            risk = abs(entry_price - stop_price)
            if risk <= 0:
                csc = "idle"
                cinfo = {}
                continue
            dir_ = info["break_dir"]
            first = nearest_prior_level(hist, info["hold_bar_idx"], dir_, info["break_level"])
            if first is None:
                tp1 = mm_proj(info["breakout_point"], info["base_range"], dir_)
                tp1_note = "measured_move"
            else:
                tp1 = first[0]
                tp1_note = "structural"
            second = second_prior_level(hist, info["hold_bar_idx"], dir_, stop_price)
            if second is None:
                tp2 = mm_proj(info["breakout_point"], info["base_range"], dir_)
                tp2_note = "measured_move"
            else:
                tp2 = second[0]
                tp2_note = "structural"
            csc = "in_trade"
            cinfo.update(
                entry_idx=idx,
                entry_price=entry_price,
                stop_price=stop_price,
                tp1_level=tp1,
                tp2_level=tp2,
                tp1_note=tp1_note,
                tp2_note=tp2_note,
                risk=risk,
                base_range=info["base_range"],
                break_level=info["break_level"],
                break_dir=dir_,
                strategy="CSC",
            )

        if csc == "in_trade":
            info = cinfo
            dir_ = info["break_dir"]
            price = c
            exited = False
            exit_price = None
            exit_reason = None
            if dir_ == "short":
                if price >= info["stop_price"]:
                    exited, exit_price, exit_reason = True, info["stop_price"], "stop"
                elif price <= info["tp1_level"]:
                    exited, exit_price, exit_reason = True, info["tp1_level"], "tp1"
                elif price <= info["tp2_level"]:
                    exited, exit_price, exit_reason = True, info["tp2_level"], "tp2"
            else:
                if price <= info["stop_price"]:
                    exited, exit_price, exit_reason = True, info["stop_price"], "stop"
                elif price >= info["tp1_level"]:
                    exited, exit_price, exit_reason = True, info["tp1_level"], "tp1"
                elif price >= info["tp2_level"]:
                    exited, exit_price, exit_reason = True, info["tp2_level"], "tp2"
            if exited:
                rm = (info["entry_price"] - exit_price) / info["risk"] if dir_ == "short" else (exit_price - info["entry_price"]) / info["risk"]
                results.append(
                    dict(
                        strategy="CSC",
                        entry_idx=info["entry_idx"],
                        entry_ts=(hist.ts[info["entry_idx"]] if info["entry_idx"] < len(hist.ts) else None),
                        entry_price=info["entry_price"],
                        stop_price=info["stop_price"],
                        tp1_level=info["tp1_level"],
                        tp2_level=info["tp2_level"],
                        tp1_note=info["tp1_note"],
                        tp2_note=info["tp2_note"],
                        risk=info["risk"],
                        exit_reason=exit_reason,
                        exit_price=exit_price,
                        r_multiple=rm,
                        break_dir=dir_,
                        break_level=info["break_level"],
                        hold_bar_idx=info["hold_bar_idx"],
                        hold_low=info["hold_low"],
                        hold_high=info["hold_high"],
                    )
                )
                csc = "idle"
                cinfo = {}
