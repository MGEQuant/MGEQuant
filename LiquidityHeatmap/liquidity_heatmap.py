#!/usr/bin/env python3
"""Liquidity Heatmap engine for Futures, Stocks, Crypto and Forex.

Reads OHLCV bars and builds a liquidity picture of the auction:

  * traded volume-at-price and TPO (time at price)
  * resting (wick) liquidity above and below each price bin
  * buy / sell pressure per bin (delta proxy from bar direction)
  * estimated liquidation bands per leverage ladder
  * swing-pivot liquidity pools (equal highs / equal lows)
  * adaptive round-number levels (major and minor handles)
  * sweep detection (liquidity grabs that reclaim the level)
  * HVN magnet nodes and LVN liquidity voids

Bar input format matches the rest of this repo (see mge_csc_ab_bt.py):
    timestamp,open,high,low,close,volume

Stdlib only on purpose. This module mirrors liquidity-heatmap.html so a
backtest and the browser chart agree on the same numbers.

Usage:
    python liquidity_heatmap.py --csv bars.csv --asset futures --symbol NQ
    python liquidity_heatmap.py --demo --asset crypto --json out.json
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import math
import pathlib
import random
import sys

# --------------------------------------------------------------------------- #
# Asset class profiles
# --------------------------------------------------------------------------- #

ASSET_PROFILES = {
    "futures": {
        "label": "Futures",
        "tick": 0.25,
        "session_bars": 8,
        "leverages": (10, 20, 25, 50, 100),
        "symbols": ("NQ", "ES", "CL", "GC", "RTY"),
        "session_label": "RTH 09:30-16:00 ET",
    },
    "stocks": {
        "label": "Stocks",
        "tick": 0.01,
        "session_bars": 15,
        "leverages": (2, 4, 10, 20),
        "symbols": ("AAPL", "NVDA", "TSLA", "SPY", "MSFT"),
        "session_label": "RTH 09:30-16:00 ET",
    },
    "crypto": {
        "label": "Crypto",
        "tick": 0.5,
        "session_bars": 4,
        "leverages": (5, 10, 25, 50, 100),
        "symbols": ("BTCUSD", "ETHUSD", "SOLUSD"),
        "session_label": "24/7 UTC",
    },
    "forex": {
        "label": "Forex",
        "tick": 0.00001,
        "session_bars": 12,
        "leverages": (10, 30, 50, 100),
        "symbols": ("EURUSD", "GBPUSD", "USDJPY", "XAUUSD"),
        "session_label": "London / New York",
    },
}

ASSET_ORDER = ("futures", "stocks", "crypto", "forex")


def profile_for(asset, price=None, symbol=None):
    """Return the profile for an asset class, tuned to the traded price scale."""
    key = asset if asset in ASSET_PROFILES else "futures"
    prof = dict(ASSET_PROFILES[key])
    prof["asset"] = key
    prof["symbol"] = symbol or prof["symbols"][0]
    if price is None or price <= 0:
        return prof
    mag = 10.0 ** math.floor(math.log10(price))
    # major handle (NQ 100s, AAPL 1s, EURUSD big figure, BTC 100s) and its half
    major = mag / 100.0
    minor = mag / 200.0
    prof["round_major"] = major
    prof["round_minor"] = minor
    tick = prof["tick"]
    if key == "forex" and price >= 20.0:
        tick = 0.001
    prof["tick"] = min(tick, major / 10.0) if major else tick
    return prof


# --------------------------------------------------------------------------- #
# Bar loading
# --------------------------------------------------------------------------- #

TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
)


def parse_timestamp(text):
    text = str(text).strip()
    for fmt in TIMESTAMP_FORMATS:
        try:
            return dt.datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def load_bars_csv(path):
    """Load `timestamp,open,high,low,close,volume` bars. Returns (header, bars)."""
    bars = []
    path = pathlib.Path(path)
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        for row in reader:
            if not row or not row[0].strip():
                continue
            stamp = parse_timestamp(row[0])
            if stamp is None:
                continue
            try:
                o = float(row[1])
                h = float(row[2])
                l = float(row[3])
                c = float(row[4])
                v = float(row[5]) if len(row) > 5 and str(row[5]).strip() else 0.0
            except (ValueError, IndexError):
                continue
            if not all(math.isfinite(x) for x in (o, h, l, c, v)):
                continue
            bars.append({"t": stamp, "o": o, "h": h, "l": l, "c": c, "v": v})
    bars.sort(key=lambda b: b["t"])
    return header, bars


# --------------------------------------------------------------------------- #
# Small statistical helpers
# --------------------------------------------------------------------------- #

def atr(bars, period=14):
    """Simple average true range over the last `period` bars."""
    if not bars:
        return 0.0
    if len(bars) < 2:
        return bars[0]["h"] - bars[0]["l"]
    prev_close = bars[0]["c"]
    true_ranges = []
    for bar in bars[1:]:
        true_ranges.append(max(
            bar["h"] - bar["l"],
            abs(bar["h"] - prev_close),
            abs(bar["l"] - prev_close),
        ))
        prev_close = bar["c"]
    window = min(period, len(true_ranges))
    return sum(true_ranges[-window:]) / window


def bin_index(price, low, bin_size, bins):
    if bin_size <= 0:
        return 0
    idx = int((price - low) / bin_size)
    return max(0, min(bins - 1, idx))


def bin_center(idx, low, bin_size):
    return low + (idx + 0.5) * bin_size


def pivot_points(bars, strength):
    """Return (pivot_highs, pivot_lows) as lists of (index, price)."""
    highs, lows = [], []
    n = len(bars)
    k = max(1, int(strength))
    for i in range(k, n - k):
        hi = bars[i]["h"]
        lo = bars[i]["l"]
        if hi >= max(bars[j]["h"] for j in range(i - k, i + k + 1)):
            highs.append((i, hi))
        if lo <= min(bars[j]["l"] for j in range(i - k, i + k + 1)):
            lows.append((i, lo))
    return highs, lows


def cluster_levels(levels, tolerance):
    """Greedy 1-D clustering of (index, price) levels into equal-high/low pools."""
    clusters = []
    for idx, price in sorted(levels, key=lambda item: item[1]):
        if clusters and price - clusters[-1]["last"] <= tolerance:
            cluster = clusters[-1]
            cluster["prices"].append(price)
            cluster["idxs"].append(idx)
            cluster["last"] = price
        else:
            clusters.append({"prices": [price], "idxs": [idx], "last": price})
    out = []
    for cluster in clusters:
        prices = cluster["prices"]
        idxs = cluster["idxs"]
        out.append({
            "price": sum(prices) / len(prices),
            "touches": len(prices),
            "first_idx": min(idxs),
            "last_idx": max(idxs),
        })
    return out


# --------------------------------------------------------------------------- #
# Heat fields: volume profile, resting liquidity, delta, liquidation
# --------------------------------------------------------------------------- #

def _spread(total, first, last, out, matrix=None, col=None):
    """Spread `total` evenly across bins first..last inclusive.

    Pass out=None when only the price x time matrix column needs the value.
    """
    span = last - first + 1
    share = total / span
    for i in range(first, last + 1):
        if out is not None:
            out[i] += share
        if matrix is not None and col is not None:
            matrix[i][col] += share


def _price_profile(bars, low, bin_size, bins):
    """Full-sample price profile: volume, TPO, delta split and resting wicks."""
    fields = {
        "volume": [0.0] * bins,
        "tpo": [0.0] * bins,
        "buy": [0.0] * bins,
        "sell": [0.0] * bins,
        "resting_up": [0.0] * bins,
        "resting_dn": [0.0] * bins,
    }
    for bar in bars:
        o, h, l, c, v = bar["o"], bar["h"], bar["l"], bar["c"], bar["v"]
        span = max(h - l, bin_size)
        first = bin_index(l, low, bin_size, bins)
        last = bin_index(h, low, bin_size, bins)
        share = v / (last - first + 1)
        buy_side = c >= o
        for i in range(first, last + 1):
            fields["volume"][i] += share
            fields["tpo"][i] += 1.0
            fields["buy" if buy_side else "sell"][i] += share
        body_hi = max(o, c)
        body_lo = min(o, c)
        if h > body_hi:
            _spread(v * ((h - body_hi) / span),
                    bin_index(body_hi, low, bin_size, bins), last, fields["resting_up"])
        if l < body_lo:
            _spread(v * ((body_lo - l) / span), first,
                    bin_index(body_lo, low, bin_size, bins), fields["resting_dn"])
    fields["resting"] = [a + b for a, b in zip(fields["resting_up"], fields["resting_dn"])]
    fields["delta"] = [a - b for a, b in zip(fields["buy"], fields["sell"])]
    return fields


def anchor_bins(volume, bins, count=6, min_gap=2):
    """Highest-volume nodes: liquidation anchors and magnet levels."""
    if not any(volume):
        return []
    picks = []
    for i in sorted(range(bins), key=lambda k: volume[k], reverse=True):
        if volume[i] <= 0:
            break
        if all(abs(i - p) > min_gap for p in picks):
            picks.append(i)
        if len(picks) >= count:
            break
    return [(i, volume[i]) for i in picks]


def build_heat_fields(bars, low, bin_size, bins, window,
                      leverages, lookback, weight_by_leverage=True,
                      anchor_count=6):
    """Build every price-binned field plus the price x time heat matrices.

    `window` is the number of trailing bars used for the rendered matrices.
    """
    n = len(bars)
    start = max(0, n - int(window))
    times = list(range(start, n))
    n_t = len(times)

    profile = _price_profile(bars, low, bin_size, bins)
    anchors = anchor_bins(profile["volume"], bins, count=anchor_count)
    max_anchor_volume = max((v for _, v in anchors), default=0.0) or 1.0
    sample_volume = (sum(profile["volume"]) / bins) or 1.0

    m_vol = [[0.0] * n_t for _ in range(bins)]
    m_rest = [[0.0] * n_t for _ in range(bins)]
    m_delta = [[0.0] * n_t for _ in range(bins)]
    m_liq = [[0.0] * n_t for _ in range(bins)]

    max_lev = max(leverages) if leverages else 1
    for col, idx in enumerate(times):
        bar = bars[idx]
        o, h, l, c, v = bar["o"], bar["h"], bar["l"], bar["c"], bar["v"]
        spread = max(h - l, bin_size)
        lo_bin = bin_index(l, low, bin_size, bins)
        hi_bin = bin_index(h, low, bin_size, bins)
        touch_span = hi_bin - lo_bin + 1

        # heat matrix for traded volume across the whole bar range
        _spread(v, lo_bin, hi_bin, None, m_vol, col)

        # directional split as a delta proxy
        body_hi = max(o, c)
        body_lo = min(o, c)
        share = v / touch_span
        if c >= o:
            for i in range(lo_bin, hi_bin + 1):
                m_delta[i][col] += share
        else:
            for i in range(lo_bin, hi_bin + 1):
                m_delta[i][col] -= share

        # resting liquidity: volume that wicked past the body and was rejected
        if h > body_hi:
            _spread(v * ((h - body_hi) / spread),
                    bin_index(body_hi, low, bin_size, bins), hi_bin, None, m_rest, col)
        if l < body_lo:
            _spread(v * ((body_lo - l) / spread), lo_bin,
                    bin_index(body_lo, low, bin_size, bins), None, m_rest, col)

        # estimated liquidation clusters: volume anchors x leverage ladder
        freshness_window = max(1, int(lookback))
        for anchor_i, anchor_volume in anchors:
            anchor_price = bin_center(anchor_i, low, bin_size)
            touched = 0
            for j in range(max(0, idx - freshness_window + 1), idx + 1):
                if bars[j]["l"] <= anchor_price <= bars[j]["h"]:
                    touched += 1
            if touched == 0:
                continue
            freshness = min(1.0, touched / (freshness_window * 0.25))
            base = (anchor_volume / max_anchor_volume) * freshness
            for lev in leverages:
                weight = base * (lev / max_lev if weight_by_leverage else 1.0)
                # longs opened at the node liquidate below it, shorts above it
                for price in (anchor_price * (1.0 - 1.0 / lev),
                              anchor_price * (1.0 + 1.0 / lev)):
                    if low <= price <= low + bin_size * bins:
                        m_liq[bin_index(price, low, bin_size, bins)][col] += weight

        # fresh extremes: recent swing anchors add momentum liquidation clusters
        win_start = max(0, idx - freshness_window + 1)
        if win_start < idx:
            recent = bars[win_start:idx + 1]
            swing_high = max(b["h"] for b in recent)
            swing_low = min(b["l"] for b in recent)
            momentum_volume = sum(b["v"] for b in recent) / len(recent)
            base = 0.5 * momentum_volume / sample_volume
            for lev in leverages:
                weight = base * (lev / max_lev if weight_by_leverage else 1.0)
                for price in (swing_low * (1.0 - 1.0 / lev), swing_high * (1.0 + 1.0 / lev)):
                    if low <= price <= low + bin_size * bins:
                        m_liq[bin_index(price, low, bin_size, bins)][col] += weight

    return {
        **profile,
        "matrix": {"volume": m_vol, "resting": m_rest, "delta": m_delta, "liquidation": m_liq},
        "times": times,
    }


def find_voids(volume, low, bin_size, bins, threshold=0.20, gap=1):
    """Contiguous low-volume runs (liquidity voids / LVN travel zones)."""
    positive = [v for v in volume if v > 0]
    if not positive:
        return []
    mean = sum(positive) / len(positive)
    if mean <= 0:
        return []
    cut = mean * threshold
    runs = []
    run = []
    for i in range(bins):
        if volume[i] < cut:
            run.append(i)
        else:
            runs.append(run)
            run = []
    runs.append(run)
    merged = []
    for run in runs:
        if merged and run and merged[-1] and run[0] - merged[-1][-1] - 1 <= gap:
            merged[-1] = merged[-1] + run
        else:
            merged.append(list(run))
    out = []
    for run in merged:
        if not run:
            continue
        span = len(run)
        depth = sum(volume[i] for i in run) / max(1e-12, mean * span)
        lo_price = low + run[0] * bin_size
        hi_price = low + (run[-1] + 1) * bin_size
        out.append({
            "low": lo_price,
            "high": hi_price,
            "center": (lo_price + hi_price) / 2.0,
            "bins": span,
            "depth": depth,
            "score": span * (1.0 - min(1.0, depth)),
        })
    out.sort(key=lambda z: z["score"], reverse=True)
    return out


def find_nodes(volume, low, bin_size, bins, count=6):
    """High-volume nodes (magnets): the strongest volume peaks in the profile."""
    picks = anchor_bins(volume, bins, count=count)
    total = sum(volume) or 1.0
    return [{
        "price": bin_center(i, low, bin_size),
        "volume": value,
        "share": value / total * 100.0,
    } for i, value in sorted(picks, key=lambda item: -item[0])]


# --------------------------------------------------------------------------- #
# Session levels, sweeps, pools and round numbers
# --------------------------------------------------------------------------- #

def session_levels(bars, session_bars, week_sessions=5):
    """Prior-day, opening-range, weekly levels and session VWAP."""
    if not bars:
        return {}
    sessions = []
    current_day = bars[0]["t"].date()
    bucket = []
    for bar in bars:
        day = bar["t"].date()
        if day != current_day and bucket:
            sessions.append(bucket)
            bucket = []
            current_day = day
        bucket.append(bar)
    if bucket:
        sessions.append(bucket)

    levels = {}
    latest = sessions[-1]
    levels["session"] = latest[0]["t"].date().isoformat()
    levels["session_high"] = max(b["h"] for b in latest)
    levels["session_low"] = min(b["l"] for b in latest)
    levels["session_close"] = latest[-1]["c"]
    open_range = latest[:max(1, int(session_bars))]
    levels["or_bars"] = len(open_range)
    levels["or_high"] = max(b["h"] for b in open_range)
    levels["or_low"] = min(b["l"] for b in open_range)

    if len(sessions) >= 2:
        prior = sessions[-2]
        levels["prior_date"] = prior[0]["t"].date().isoformat()
        levels["pdh"] = max(b["h"] for b in prior)
        levels["pdl"] = min(b["l"] for b in prior)
        levels["pdc"] = prior[-1]["c"]

    week = [b for sess in sessions[-int(week_sessions):] for b in sess]
    if week:
        levels["week_high"] = max(b["h"] for b in week)
        levels["week_low"] = min(b["l"] for b in week)

    typical = 0.0
    total = 0.0
    for bar in latest:
        tp = (bar["h"] + bar["l"] + bar["c"]) / 3.0
        typical += tp * bar["v"]
        total += bar["v"]
    levels["vwap"] = (typical / total) if total > 0 else latest[-1]["c"]
    return levels


def detect_sweeps(bars, price, tolerance, since=0):
    """Count liquidity grabs: price takes the level, then closes back inside.

    A sweep only counts when the previous close was on the far side of the
    level, so a slow grind through a level is one event, not one per bar.

    Returns (total_sweeps, last_index, last_direction).
    """
    total = 0
    last_idx = None
    last_dir = None
    for i in range(max(1, int(since)), len(bars)):
        bar = bars[i]
        prev_close = bars[i - 1]["c"]
        if bar["l"] < price - tolerance and prev_close >= price and bar["c"] > price:
            total += 1
            last_idx, last_dir = i, "sell_side_swept"
        elif bar["h"] > price + tolerance and prev_close <= price and bar["c"] < price:
            total += 1
            last_idx, last_dir = i, "buy_side_swept"
    return total, last_idx, last_dir


def build_pools(bars, highs, lows, tolerance, price, bin_size, sweep_since=0):
    """Equal-high / equal-low liquidity pools with strength scoring."""
    n = max(1, len(bars))
    pools = []
    for kind, raw in (("high", highs), ("low", lows)):
        for cluster in cluster_levels(raw, tolerance):
            sweeps, sweep_idx, sweep_dir = detect_sweeps(
                bars, cluster["price"], tolerance * 0.5, since=sweep_since)
            recency = cluster["last_idx"] / n
            strength = cluster["touches"] * (1.0 + sweeps) * (0.5 + 0.5 * recency)
            side = "buy_side" if cluster["price"] > price else "sell_side"
            pools.append({
                "kind": kind,
                "side": side,
                "price": cluster["price"],
                "touches": cluster["touches"],
                "equal": cluster["touches"] >= 2,
                "sweeps": sweeps,
                "last_sweep_idx": sweep_idx,
                "last_sweep_dir": sweep_dir,
                "first_idx": cluster["first_idx"],
                "last_idx": cluster["last_idx"],
                "strength": strength,
                "distance": cluster["price"] - price,
                "distance_ticks": (cluster["price"] - price) / bin_size if bin_size else 0.0,
            })
    pools.sort(key=lambda p: p["strength"], reverse=True)
    return pools


def round_number_levels(low, high, major, minor, price):
    """Round-number handles (stop-cluster levels) inside the visible range."""
    out = []
    for step, label in ((minor, "minor"), (major, "major")):
        if not step or step <= 0:
            continue
        start = math.floor(low / step) * step
        end = math.ceil(high / step) * step
        value = start
        guard = 0
        while value <= end + step * 0.5 and guard < 5000:
            guard += 1
            if low <= value <= high:
                # a level that is both a minor and a major handle is reported once
                if label == "minor" and major > 0 and abs(value / major - round(value / major)) < 1e-9:
                    value += step
                    continue
                out.append({
                    "price": value,
                    "step": step,
                    "label": label,
                    "distance": value - price,
                    "side": "buy_side" if value > price else "sell_side",
                })
            value += step
    out.sort(key=lambda item: abs(item["distance"]))
    return out


# --------------------------------------------------------------------------- #
# Report assembly
# --------------------------------------------------------------------------- #

def _side_sums(values, low, bin_size, price):
    above = below = 0.0
    for i, v in enumerate(values):
        if bin_center(i, low, bin_size) > price:
            above += v
        else:
            below += v
    return above, below


def _nearest_liquidation(matrix, price, low, bin_size, bins):
    """Strongest estimated liquidation cluster above and below the last price."""
    if not matrix or not matrix[0]:
        return None, None
    col = [row[-1] for row in matrix]
    best_up = best_dn = None
    for i, value in enumerate(col):
        if value <= 0:
            continue
        center = bin_center(i, low, bin_size)
        if center > price and (best_up is None or value > best_up[1]):
            best_up = (center, value)
        elif center <= price and (best_dn is None or value > best_dn[1]):
            best_dn = (center, value)
    return best_up, best_dn


def liquidity_report(bars, asset="futures", symbol=None, bins=80, pivot_k=3,
                     lookback=60, matrix_bars=480, include_matrix=False,
                     void_threshold=0.20):
    """Full liquidity picture for one instrument."""
    if not bars:
        raise ValueError("no bars supplied")

    price = bars[-1]["c"]
    low = min(b["l"] for b in bars)
    high = max(b["h"] for b in bars)
    span = max(high - low, 1e-9)
    bins = max(12, min(400, int(bins)))
    bin_size = span / bins
    prof = profile_for(asset, price, symbol)
    atr_value = atr(bars)
    tolerance = max(prof["tick"], 0.10 * atr_value)

    heat = build_heat_fields(bars, low, bin_size, bins, matrix_bars,
                            prof["leverages"], lookback)
    voids = find_voids(heat["volume"], low, bin_size, bins, void_threshold)
    nodes = find_nodes(heat["volume"], low, bin_size, bins)
    highs, lows = pivot_points(bars, pivot_k)
    sweep_since = max(1, int(len(bars) * 0.34))
    pools = build_pools(bars, highs, lows, tolerance, price, bin_size,
                        sweep_since=sweep_since)
    rounds = round_number_levels(low, high, prof["round_major"], prof["round_minor"], price)
    levels = session_levels(bars, prof["session_bars"])

    above, below = _side_sums(heat["resting"], low, bin_size, price)
    total_resting = above + below
    buy_total = sum(heat["buy"])
    sell_total = sum(heat["sell"])
    delta_total = buy_total + sell_total
    liq_up, liq_dn = _nearest_liquidation(heat["matrix"]["liquidation"], price, low, bin_size, bins)
    pool_above = [p for p in pools if p["price"] > price]
    pool_below = [p for p in pools if p["price"] <= price]
    sweeps_total = sum(p["sweeps"] for p in pools)
    swept_levels = sum(1 for p in pools if p["sweeps"] > 0)
    top_node = max(nodes, key=lambda n: n["volume"]) if nodes else None

    if above > below * 1.15:
        bias = "buy-side liquidity above"
    elif below > above * 1.15:
        bias = "sell-side liquidity below"
    else:
        bias = "balanced"

    summary = {
        "price": price,
        "bias": bias,
        "resting_above": above,
        "resting_below": below,
        "resting_ratio": (above / below) if below > 0 else float("inf"),
        "resting_share_above": (above / total_resting * 100.0) if total_resting else 0.0,
        "delta_bias": ((buy_total - sell_total) / delta_total) if delta_total else 0.0,
        "nearest_pool_above": pool_above[-1] if pool_above else None,
        "nearest_pool_below": pool_below[0] if pool_below else None,
        "strongest_pool": pools[0] if pools else None,
        "top_void": voids[0] if voids else None,
        "top_node": top_node,
        "sweeps_total": sweeps_total,
        "swept_levels": swept_levels,
        "pool_count": len(pools),
        "equal_highs": sum(1 for p in pools if p["kind"] == "high" and p["equal"]),
        "equal_lows": sum(1 for p in pools if p["kind"] == "low" and p["equal"]),
        "liquidation_above": liq_up,
        "liquidation_below": liq_dn,
        "void_count": len(voids),
    }

    # nearest pool extremes, ignoring noise levels sitting inside the current bar
    min_gap = bin_size * 1.0
    fresh_above = [p for p in pool_above if p["distance"] > min_gap]
    fresh_below = [p for p in pool_below if -p["distance"] > min_gap]
    near_above = min(fresh_above, key=lambda p: p["distance"]) if fresh_above else (
        min(pool_above, key=lambda p: p["distance"]) if pool_above else None)
    near_below = max(fresh_below, key=lambda p: p["distance"]) if fresh_below else (
        max(pool_below, key=lambda p: p["distance"]) if pool_below else None)
    summary["nearest_pool_above"] = near_above
    summary["nearest_pool_below"] = near_below
    summary["sweep_window_start"] = sweep_since

    report = {
        "meta": {
            "asset": prof["asset"],
            "asset_label": prof["label"],
            "symbol": prof["symbol"],
            "session_label": prof["session_label"],
            "bars": len(bars),
            "from": bars[0]["t"].isoformat(sep=" "),
            "to": bars[-1]["t"].isoformat(sep=" "),
            "price": price,
            "low": low,
            "high": high,
            "bin_size": bin_size,
            "bins": bins,
            "tick": prof["tick"],
            "round_major": prof["round_major"],
            "round_minor": prof["round_minor"],
            "leverages": list(prof["leverages"]),
            "atr": atr_value,
            "pool_tolerance": tolerance,
            "pivot_k": pivot_k,
            "lookback": lookback,
            "matrix_bars": matrix_bars,
        },
        "fields": {
            "volume": heat["volume"],
            "tpo": heat["tpo"],
            "buy": heat["buy"],
            "sell": heat["sell"],
            "resting": heat["resting"],
            "resting_up": heat["resting_up"],
            "resting_dn": heat["resting_dn"],
            "delta": heat["delta"],
        },
        "matrix_times": heat["times"],
        "pools": pools,
        "round_numbers": rounds,
        "levels": levels,
        "voids": voids,
        "nodes": nodes,
        "summary": summary,
    }
    if include_matrix:
        report["matrix"] = heat["matrix"]
    return report


# --------------------------------------------------------------------------- #
# Text report
# --------------------------------------------------------------------------- #

def _decimals(tick):
    if tick >= 0.01:
        return 2
    if tick >= 0.001:
        return 3
    return 5


def _money(value, decimals=2):
    return f"{value:,.{decimals}f}"


def format_report(report, top=8):
    meta = report["meta"]
    summary = report["summary"]
    levels = report["levels"]
    decimals = _decimals(meta["tick"])
    p = lambda v: _money(v, decimals) if v is not None else "n/a"

    lines = []
    lines.append("=" * 92)
    lines.append(f"LIQUIDITY HEATMAP  |  {meta['asset_label']} ({meta['symbol']})  "
                 f"{meta['session_label']}")
    lines.append("=" * 92)
    lines.append(f"Bars            : {meta['bars']}  ({meta['from']} -> {meta['to']})")
    lines.append(f"Last price      : {p(meta['price'])}        ATR(14): {p(meta['atr'])}")
    lines.append(f"Range           : {p(meta['low'])} - {p(meta['high'])}")
    lines.append(f"Bins            : {meta['bins']} @ {p(meta['bin_size'])}   Tick: {meta['tick']}")
    lines.append(f"Pool tolerance  : {p(meta['pool_tolerance'])}   Pivot k: {meta['pivot_k']}   "
                 f"Lookback: {meta['lookback']}   Matrix bars: {meta['matrix_bars']}")
    lines.append(f"Round numbers   : major {p(meta['round_major'])} / minor {p(meta['round_minor'])}")
    lines.append("")

    lines.append("LIQUIDITY SUMMARY")
    lines.append(f"  Bias                  : {summary['bias']}")
    lines.append(f"  Resting above / below : {summary['resting_share_above']:.1f}% / "
                 f"{100 - summary['resting_share_above']:.1f}%")
    lines.append(f"  Delta bias            : {summary['delta_bias'] * 100:+.2f}% "
                 f"({'buy' if summary['delta_bias'] >= 0 else 'sell'} pressure)")
    lines.append(f"  Pools                 : {summary['pool_count']} "
                 f"({summary['equal_highs']} equal highs, {summary['equal_lows']} equal lows)")
    lines.append(f"  Sweeps detected       : {summary['sweeps_total']} across "
                 f"{summary['swept_levels']} levels")
    lines.append(f"  Liquidity voids       : {summary['void_count']}")
    lines.append("")

    lines.append("NEAREST LIQUIDITY")
    for label, pool in (("Above", summary["nearest_pool_above"]), ("Below", summary["nearest_pool_below"])):
        if pool is None:
            lines.append(f"  {label:<5} : none")
            continue
        lines.append(f"  {label:<5} : {p(pool['price'])}  {pool['side']:<10} touches {pool['touches']}  "
                     f"sweeps {pool['sweeps']}  dist {pool['distance']:+,.{decimals}f} "
                     f"({pool['distance_ticks']:+.1f} bins)")
    for label, band in (("above", summary["liquidation_above"]), ("below", summary["liquidation_below"])):
        if band is None:
            lines.append(f"  Est. liquidation {label}: none")
        else:
            lines.append(f"  Est. liquidation {label}: {p(band[0])} (intensity {band[1]:.2f})")
    if summary["top_node"]:
        lines.append(f"  Top magnet (HVN)      : {p(summary['top_node']['price'])} "
                     f"({summary['top_node']['share']:.1f}% of traded volume)")
    lines.append("")

    lines.append("SESSION LEVELS")
    if "prior_date" in levels:
        lines.append(f"  Prior day {levels['prior_date']}    : high {p(levels['pdh'])}  "
                     f"low {p(levels['pdl'])}  close {p(levels['pdc'])}")
    lines.append(f"  Opening range ({levels.get('or_bars', 0)} bars): high {p(levels.get('or_high'))}  "
                 f"low {p(levels.get('or_low'))}")
    lines.append(f"  Session {levels.get('session')}      : high {p(levels.get('session_high'))}  "
                 f"low {p(levels.get('session_low'))}")
    lines.append(f"  Week high / low        : {p(levels.get('week_high'))} / {p(levels.get('week_low'))}")
    lines.append(f"  VWAP (session)         : {p(levels.get('vwap'))}")
    lines.append("")

    lines.append(f"STRONGEST POOLS (top {top})")
    lines.append(f"  {'#':>2}  {'Side':<10} {'Price':>14}  {'Kind':<5} {'Touch':>5} {'Sweep':>5} "
                 f"{'Strength':>9}  {'Dist':>9}")
    for i, pool in enumerate(report["pools"][:top], start=1):
        lines.append(f"  {i:>2}  {pool['side']:<10} {p(pool['price']):>14}  {pool['kind']:<5} "
                     f"{pool['touches']:>5} {pool['sweeps']:>5} {pool['strength']:>9.2f}  "
                     f"{pool['distance_ticks']:>+9.1f}")
    lines.append("")

    if report["voids"]:
        lines.append("LIQUIDITY VOIDS (low-volume travel zones)")
        for void in report["voids"][:5]:
            lines.append(f"  {p(void['low'])} - {p(void['high'])}  "
                         f"center {p(void['center'])}  bins {void['bins']:<3} "
                         f"depth {void['depth'] * 100:.0f}% of mean")
        lines.append("")

    if report["round_numbers"]:
        nearest = report["round_numbers"][:8]
        majors = ", ".join(f"{p(r['price'])} ({r['label']})" for r in nearest)
        lines.append("ROUND NUMBERS NEAR PRICE")
        lines.append(f"  {majors}")
        lines.append("")

    lines.append("Notes: volume, delta and resting liquidity are derived from OHLCV bars.")
    lines.append("Liquidation bands are leverage-based estimates, not exchange order book data.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Demo data (so every asset class can be exercised offline)
# --------------------------------------------------------------------------- #

DEMO_CONFIG = {
    "futures": {"symbol": "NQ", "price": 20150.0, "step_min": 5, "vol": 18.0,
                "volume": 900.0, "window": (9, 30, 16, 0), "sessions": True},
    "stocks": {"symbol": "AAPL", "price": 232.0, "step_min": 5, "vol": 0.85,
               "volume": 38000.0, "window": (9, 30, 16, 0), "sessions": True},
    "crypto": {"symbol": "BTCUSD", "price": 64250.0, "step_min": 15, "vol": 310.0,
               "volume": 240.0, "window": (0, 0, 24, 0), "sessions": False},
    "forex": {"symbol": "EURUSD", "price": 1.0850, "step_min": 15, "vol": 0.0011,
              "volume": 1500.0, "window": (0, 0, 24, 0), "sessions": True},
}


def demo_timestamps(count, asset, start=None):
    cfg = DEMO_CONFIG.get(asset, DEMO_CONFIG["futures"])
    step = dt.timedelta(minutes=cfg["step_min"])
    hour, minute, end_hour, end_minute = cfg["window"]
    cursor = start or dt.datetime(2026, 1, 5, hour, minute)
    stamps = []
    guard = 0
    while len(stamps) < count and guard < count * 12:
        guard += 1
        if cfg["sessions"] and cursor.weekday() >= 5:
            cursor = (cursor + dt.timedelta(days=7 - cursor.weekday())).replace(
                hour=hour, minute=minute)
            continue
        if cfg["sessions"] and (cursor.hour * 60 + cursor.minute) >= end_hour * 60 + end_minute:
            cursor = (cursor + dt.timedelta(days=1)).replace(hour=hour, minute=minute)
            continue
        stamps.append(cursor)
        cursor += step
    return stamps


def demo_bars(asset="futures", count=900, seed=20260105):
    """Deterministic synthetic OHLCV with pools, sweeps and voids."""
    cfg = DEMO_CONFIG.get(asset, DEMO_CONFIG["futures"])
    rng = random.Random(seed)
    profile = profile_for(asset, cfg["price"], cfg["symbol"])
    major = profile["round_major"]
    stamps = demo_timestamps(count, asset)
    bars = []
    price = cfg["price"]
    drift = 0.0
    for i, stamp in enumerate(stamps):
        if i % 90 == 0:
            drift = rng.uniform(-0.08, 0.08) * cfg["vol"]
        handle = round(price / major) * major
        pull = (handle - price) * 0.02
        move = drift + pull + rng.gauss(0.0, cfg["vol"])
        open_px = price
        close_px = price + move
        wick_up = abs(rng.gauss(0.0, cfg["vol"])) * 0.55
        wick_dn = abs(rng.gauss(0.0, cfg["vol"])) * 0.55
        sweep = rng.random() < 0.035
        if sweep:
            body_hi = max(open_px, close_px)
            body_lo = min(open_px, close_px)
            if rng.random() < 0.5:
                wick_dn = abs(body_lo - (handle - major)) + cfg["vol"] * 0.4
                close_px = body_hi
            else:
                wick_up = abs((handle + major) - body_hi) + cfg["vol"] * 0.4
                close_px = body_lo
        high_px = max(open_px, close_px) + wick_up
        low_px = min(open_px, close_px) - wick_dn
        volume = cfg["volume"] * (1.0 + 0.45 * abs(move) / max(cfg["vol"], 1e-9))
        volume *= rng.uniform(0.6, 1.5)
        if sweep:
            volume *= 2.4
        bars.append({
            "t": stamp,
            "o": round(open_px, 6),
            "h": round(high_px, 6),
            "l": round(low_px, 6),
            "c": round(close_px, 6),
            "v": round(volume, 2),
        })
        price = close_px
    return bars


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def build_parser():
    parser = argparse.ArgumentParser(
        description="Liquidity heatmap engine for futures, stocks, crypto and forex.")
    parser.add_argument("--csv", help="OHLCV csv: timestamp,open,high,low,close,volume")
    parser.add_argument("--asset", default="futures", choices=list(ASSET_ORDER))
    parser.add_argument("--symbol", default=None)
    parser.add_argument("--bins", type=int, default=80, help="price bins (12-400)")
    parser.add_argument("--pivot-k", type=int, default=3, help="swing pivot strength")
    parser.add_argument("--lookback", type=int, default=60,
                        help="bars used for liquidation anchors")
    parser.add_argument("--matrix-bars", type=int, default=480,
                        help="trailing bars kept in the heat matrices")
    parser.add_argument("--void-threshold", type=float, default=0.20,
                        help="void cut as a fraction of mean bin volume")
    parser.add_argument("--top", type=int, default=8, help="pools shown in the text report")
    parser.add_argument("--demo", action="store_true", help="use synthetic demo bars")
    parser.add_argument("--demo-bars", type=int, default=900)
    parser.add_argument("--json", help="write the full report as JSON to this path")
    parser.add_argument("--include-matrix", action="store_true",
                        help="include price x time matrices in the JSON output")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.csv:
        _, bars = load_bars_csv(args.csv)
        if not bars:
            print(f"No usable bars parsed from {args.csv}", file=sys.stderr)
            return 2
    elif args.demo:
        bars = demo_bars(args.asset, args.demo_bars)
    else:
        print("Provide --csv path or --demo. Use --help for options.", file=sys.stderr)
        return 2

    report = liquidity_report(
        bars,
        asset=args.asset,
        symbol=args.symbol,
        bins=args.bins,
        pivot_k=args.pivot_k,
        lookback=args.lookback,
        matrix_bars=args.matrix_bars,
        include_matrix=args.include_matrix,
        void_threshold=args.void_threshold,
    )
    print(format_report(report, top=args.top))
    if args.json:
        payload = dict(report)
        if not args.include_matrix and "matrix" in payload:
            del payload["matrix"]
        out = pathlib.Path(args.json)
        if str(out.parent) not in ("", "."):
            out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"\nJSON report written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
