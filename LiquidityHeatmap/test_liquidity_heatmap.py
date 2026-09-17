#!/usr/bin/env python3
"""Checks for the liquidity heatmap engine.

Run directly, no test framework needed (same style as the other MGEQuant
engine checks):

    python test_liquidity_heatmap.py

Every check prints PASS/FAIL and the script exits non-zero if anything fails.
"""
from __future__ import annotations

import json
import math
import pathlib
import sys
import tempfile

import liquidity_heatmap as lh

FAILURES = []
CHECKS = [0]


def check(name, condition, detail=""):
    CHECKS[0] += 1
    if condition:
        print(f"  PASS  {name}" + (f"  ({detail})" if detail else ""))
    else:
        print(f"  FAIL  {name}" + (f"  ({detail})" if detail else ""))
        FAILURES.append(name)


def section(title):
    print()
    print(title)


def test_demo_every_asset_class():
    section("Demo data across all four asset classes")
    for asset in lh.ASSET_ORDER:
        bars = lh.demo_bars(asset, 600)
        report = lh.liquidity_report(bars, asset=asset, bins=60, matrix_bars=300)
        meta = report["meta"]
        summary = report["summary"]
        fields = report["fields"]

        check(f"{asset}: bars built", len(bars) == 600, f"{len(bars)} bars")
        check(f"{asset}: high/low ordering", meta["high"] > meta["low"])
        check(f"{asset}: volume profile populated", sum(fields["volume"]) > 0)
        check(f"{asset}: every bar logged time-at-price",
              sum(fields["tpo"]) >= len(bars), f"tpo total {sum(fields['tpo']):.0f}")
        check(f"{asset}: resting liquidity present", sum(fields["resting"]) > 0)
        check(f"{asset}: pools found", summary["pool_count"] > 0, f"{summary['pool_count']} pools")
        check(f"{asset}: pools sorted by strength",
              all(report["pools"][i]["strength"] >= report["pools"][i + 1]["strength"]
                  for i in range(len(report["pools"]) - 1)))
        check(f"{asset}: round numbers inside range",
              all(meta["low"] <= r["price"] <= meta["high"] for r in report["round_numbers"]))
        check(f"{asset}: major handle is twice the minor",
              math.isclose(meta["round_major"], meta["round_minor"] * 2, rel_tol=1e-9),
              f"{meta['round_major']} / {meta['round_minor']}")
        check(f"{asset}: voids sorted by score",
              all(report["voids"][i]["score"] >= report["voids"][i + 1]["score"]
                  for i in range(len(report["voids"]) - 1)))
        check(f"{asset}: voids inside range",
              all(meta["low"] - 1e-9 <= v["low"] and v["high"] <= meta["high"] + 1e-9
                  for v in report["voids"]))
        check(f"{asset}: delta bias in range", -1.0 <= summary["delta_bias"] <= 1.0,
              f"{summary['delta_bias']:+.3f}")
        check(f"{asset}: bias label set",
              summary["bias"] in ("balanced", "buy-side liquidity above", "sell-side liquidity below"))
        check(f"{asset}: session levels built",
              "vwap" in report["levels"] and "or_high" in report["levels"])
        check(f"{asset}: ATR positive", meta["atr"] > 0, f"{meta['atr']:.6g}")


def test_adaptive_round_steps():
    section("Adaptive round-number steps per asset class")
    cases = [
        ("futures", "NQ", 20150.0, 100.0, 50.0),
        ("stocks", "AAPL", 232.0, 1.0, 0.5),
        ("crypto", "BTCUSD", 64250.0, 100.0, 50.0),
        ("forex", "EURUSD", 1.0850, 0.01, 0.005),
        ("forex", "USDJPY", 152.30, 1.0, 0.5),
    ]
    for asset, symbol, price, expected_major, expected_minor in cases:
        prof = lh.profile_for(asset, price, symbol)
        check(f"{asset} {symbol}: major handle {expected_major}",
              math.isclose(prof["round_major"], expected_major, rel_tol=1e-9),
              f"got {prof['round_major']}")
        check(f"{asset} {symbol}: minor handle {expected_minor}",
              math.isclose(prof["round_minor"], expected_minor, rel_tol=1e-9),
              f"got {prof['round_minor']}")


def test_sweep_detection_counts_once():
    section("Sweep detection: level taken, then closed back through")
    level = 105.0
    bars = []
    # start above the level
    for i in range(5):
        bars.append({"t": lh.dt.datetime(2026, 1, 1) + lh.dt.timedelta(minutes=i),
                     "o": 106.0, "h": 106.4, "l": 105.6, "c": 106.0, "v": 100.0})
    # bar 5: sell-side liquidity taken (wick under the level) and reclaimed
    bars.append({"t": lh.dt.datetime(2026, 1, 1, 0, 5), "o": 106.0, "h": 106.2,
                 "l": 103.5, "c": 105.4, "v": 500.0})
    # bars 6-10: price stays below the level, so these are not reclaims
    for i in range(5):
        bars.append({"t": lh.dt.datetime(2026, 1, 1, 0, 6 + i), "o": 105.0, "h": 105.0,
                     "l": 103.9, "c": 104.5, "v": 120.0})
    # bar 11: buy-side liquidity taken (wick over the level) and rejected
    bars.append({"t": lh.dt.datetime(2026, 1, 1, 0, 11), "o": 104.5, "h": 106.8,
                 "l": 104.4, "c": 104.7, "v": 450.0})

    sweeps, last_index, direction = lh.detect_sweeps(bars, level, 0.1)
    check("a reclaim from above counts as one sweep", sweeps >= 1, f"counted {sweeps}")
    check("the sweep is labelled sell-side taken",
          direction == "buy_side_swept", str(direction))
    check("sweep index points at the rejection bar", last_index == 11, str(last_index))

    only_reclaim = bars[:6]
    single, index, side = lh.detect_sweeps(only_reclaim, level, 0.1)
    check("exactly one reclaim is counted once", single == 1, f"counted {single}")
    check("first reclaim labelled sell-side taken", side == "sell_side_swept", str(side))
    check("first reclaim index is the dip bar", index == 5, str(index))

    below = bars[:1] + bars[6:11]
    none, _, _ = lh.detect_sweeps(below, level, 0.1)
    check("bars that stay below the level are not sweeps", none == 0, f"counted {none}")


def test_csv_round_trip():
    section("CSV loading matches the repo bar format")
    bars = lh.demo_bars("futures", 120)
    with tempfile.TemporaryDirectory() as tmp:
        path = pathlib.Path(tmp) / "bars.csv"
        lines = ["timestamp,open,high,low,close,volume"]
        for bar in bars:
            lines.append(f"{bar['t']:%Y-%m-%d %H:%M:%S},{bar['o']},{bar['h']},{bar['l']},{bar['c']},{bar['v']}")
        path.write_text("\n".join(lines), encoding="utf-8")

        header, loaded = lh.load_bars_csv(path)
        check("header read", header is not None and header[0] == "timestamp", str(header))
        check("row count round trips", len(loaded) == len(bars), f"{len(loaded)} rows")
        check("values round trip",
              all(abs(a["c"] - b["c"]) < 1e-6 for a, b in zip(loaded, bars)))
        check("bars sorted by time",
              all(loaded[i]["t"] <= loaded[i + 1]["t"] for i in range(len(loaded) - 1)))

        report = lh.liquidity_report(loaded, asset="futures", symbol="NQ")
        check("report builds from CSV bars", report["meta"]["bars"] == len(loaded))

        broken = pathlib.Path(tmp) / "broken.csv"
        broken.write_text("timestamp,open,high,low,close,volume\nnot-a-date,1,2,0.5,1.5,10\n"
                          "2026-01-05 09:30:00,1,2,0.5,1.5,10\n", encoding="utf-8")
        _, survivors = lh.load_bars_csv(broken)
        check("junk rows are skipped", len(survivors) == 1, f"{len(survivors)} usable rows")


def test_matrix_shapes():
    section("Price x time heat matrices")
    bars = lh.demo_bars("crypto", 400)
    report = lh.liquidity_report(bars, asset="crypto", bins=48, matrix_bars=200, include_matrix=True)
    matrix = report["matrix"]
    times = report["matrix_times"]
    check("matrix has four layers",
          set(matrix.keys()) == {"volume", "resting", "delta", "liquidation"}, ", ".join(matrix.keys()))
    for name, grid in matrix.items():
        check(f"{name}: rows equal bins", len(grid) == report["meta"]["bins"], f"{len(grid)} rows")
        check(f"{name}: columns equal matrix times", all(len(row) == len(times) for row in grid))
    check("matrix covers the trailing window only", len(times) == min(200, len(bars)), f"{len(times)} cols")
    check("liquidation layer has content",
          any(v > 0 for row in matrix["liquidation"] for v in row))
    check("delta layer is signed both ways",
          any(v > 0 for row in matrix["delta"] for v in row) and
          any(v < 0 for row in matrix["delta"] for v in row))
    check("matrix omitted unless asked",
          "matrix" not in lh.liquidity_report(bars, asset="crypto", bins=40, matrix_bars=120))


def test_json_output_is_serialisable():
    section("JSON output")
    bars = lh.demo_bars("stocks", 200)
    report = lh.liquidity_report(bars, asset="stocks", symbol="AAPL", bins=40)
    payload = json.dumps(report)
    check("report serialises to JSON", len(payload) > 500, f"{len(payload)} chars")
    reloaded = json.loads(payload)
    check("summary survives serialisation",
          reloaded["summary"]["price"] == report["summary"]["price"])
    check("pools survive serialisation", len(reloaded["pools"]) == len(report["pools"]))


def test_text_report_sections():
    section("Text report")
    bars = lh.demo_bars("forex", 300)
    report = lh.liquidity_report(bars, asset="forex", symbol="EURUSD", bins=50)
    text = lh.format_report(report, top=5)
    for heading in ("LIQUIDITY HEATMAP", "LIQUIDITY SUMMARY", "NEAREST LIQUIDITY",
                    "SESSION LEVELS", "STRONGEST POOLS"):
        check(f"report contains '{heading}'", heading in text)
    check("report warns about estimates",
          "Liquidation bands are leverage-based estimates" in text)
    check("report line count sane", len(text.splitlines()) > 25, f"{len(text.splitlines())} lines")


def test_cli_wiring():
    section("CLI wiring")
    spec = lh.build_parser().parse_args(["--demo", "--asset", "crypto"])
    check("demo flag parsed", spec.demo is True)
    check("asset choice parsed", spec.asset == "crypto")
    check("default bins", spec.bins == 80)
    check("default matrix bars", spec.matrix_bars == 480)
    check("unknown asset rejected", _rejects_unknown_asset())


def _rejects_unknown_asset():
    # argparse prints usage to stderr and raises SystemExit for a bad choice
    quiet = open("nul", "w")
    try:
        import contextlib
        with contextlib.redirect_stderr(quiet):
            lh.build_parser().parse_args(["--demo", "--asset", "bonds"])
        return False
    except SystemExit:
        return True
    finally:
        quiet.close()


def test_invalid_input_is_rejected():
    section("Input validation")
    try:
        lh.liquidity_report([])
        check("empty bar list raises", False)
    except ValueError:
        check("empty bar list raises", True)


def main():
    print("=" * 72)
    print("Liquidity heatmap engine checks")
    print("=" * 72)
    test_demo_every_asset_class()
    test_adaptive_round_steps()
    test_sweep_detection_counts_once()
    test_csv_round_trip()
    test_matrix_shapes()
    test_json_output_is_serialisable()
    test_text_report_sections()
    test_cli_wiring()
    test_invalid_input_is_rejected()

    print()
    print("=" * 72)
    if FAILURES:
        print(f"FAILED {len(FAILURES)} of {CHECKS[0]} checks:")
        for name in FAILURES:
            print(f"  - {name}")
        return 1
    print(f"PASSED all {CHECKS[0]} checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
