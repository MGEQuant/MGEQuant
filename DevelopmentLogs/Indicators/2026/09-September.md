---
layout: default
date: "2026-09-23"
title: "Indicators — September 2026"
---

# Indicators - September 2026

Indicators read the market and draw on the chart. None of them place orders.

## September 3 — Discretionary Governor: the daily stop rule for trades placed by hand

Every coded strategy in the fleet stops for the day after two wins or one loss. It cannot be forgotten under pressure, because it is a line of code that runs before every entry. Trades placed by hand never had that.

The Discretionary Governor is an indicator that applies the same rule, on the same clock, to manual trading. Each closed trade's result is logged into it, and it shows the day's count and a clear LOCKED state, on a clock that makes a timezone slip hard to make by accident. It cannot see real fills, cannot block an order, and has no undo button on purpose, because a one-click way to erase a logged loss is a one-click way around the lockout. It is a warning tool. Actually stopping is still the trader's job.

## September 14 — Discretionary Journal: a hand-read trade plan, tracked by the bars

A journal indicator for discretionary reads. Each entry is drawn as static levels on the chart: entry, stop, two targets and a short label describing the read. Once an entry is logged, the outcome (stopped, breakeven or target) is tracked mechanically from real bars, and every result is appended to a log file, so nothing has to be re-entered by hand.

It is not an order and not an automated signal, and none of the reads it records are backtested. Its job is a clean record: what was planned before the outcome was known.

## September 15 — IB 25/75: the indicator stays, the strategy was closed

The Initial Balance is the first hour of the New York session, 09:30 to 10:30 Eastern. We took a published description of an Initial Balance retracement model, turned it into explicit rules, and tested it on about seven years of NQ. The rules: price breaks out of the range, retests the 25% or 75% level, holds, and enters with the stop at the retest extreme.

The rule fired 22 times in about seven years, roughly three trades a year against a working bar of 300 or more a year. Nineteen of the 22 stopped out. That is too few trades to prove anything and too few to trade.

The reason it fires so rarely is worth keeping. There were 2,225 breakouts. Only 101 produced a valid retest that held. Of those, 79 were rejected outright by the per-trade dollar risk cap, because projecting the full range as a target implies a stop that NQ's typical Initial Balance width rarely fits. That is a property of the target choice, not evidence about the level itself.

So there is no strategy. The indicator stays as a visualization: the Initial Balance box, the 25% and 75% lines, and a marker where the mechanical rule would have fired. Asia and London boxes were added the same day as context only, with no signal logic attached. It places no orders.

## September 15 — News Wire: an indicator that says when it cannot be trusted

An economic calendar and headline wire on the chart. The first version mirrored a note that was typed by hand each cycle. It had no source, no age, and no way to show failure. A retracted alert stayed on the chart after it was withdrawn, and a missing feed rendered as an empty box, which reads as "nothing is happening" instead of "nothing is working."

The rebuild reads a machine-generated feed: a calendar with real scheduled times and a headline wire with per-source attribution. Every line carries a time and a source. The panel's color reports the feed's trustworthiness, not decoration: grey is fresh, khaki means a source is down, red means stale or failed. Staleness is also written out in words, for example FEED STALE 47m, so a dead feed cannot be read as a live one.

All ages and countdowns are computed from the feed's own timestamp against the machine clock at render time, so a stored relative value cannot quietly go wrong as the file ages. It places no orders.

## September 18 — Liquidity Heatmap: a map of where price has done business

An indicator built from standard OHLCV bars, so it does not need order flow data. It draws four layers: traded volume at price, liquidity that wicked past a body and was rejected, buy and sell pressure per price bin, and estimated liquidation bands. On top of those it marks equal highs and lows as liquidity pools with sweep counts, sweeps where a level is taken and then reclaimed, round-number handles, and volume magnets and voids.

The buy and sell pressure layer is a bar-direction proxy, and the liquidation bands are estimates. Neither is a real order book, and the indicator is labeled that way. The same analytics run in a separate script, so a backtest and the chart agree on the same numbers. The script has its own test suite and the indicator compiles clean.

A first test of the obvious strategy, trading a sweep that reclaims its level, found no standalone edge on NQ. The heatmap is therefore a context tool. It shows where liquidity sits. It does not say to trade it.

## September 23 — FlowEdge: the same order flow, dressed to be read at a glance

FlowEdge already carried a delta heatmap with absorption, divergence and sweep detection. What it lacked was the reading experience of a professional order-flow chart, so we added a look layer on top of the existing analytics.

Four new things draw on price now. A volume-intensity color mode shades each price row by how much traded there rather than which side was pressing, so a cold yellow climbs to orange and then red as volume concentrates. A session VWAP comes with standard-deviation bands, which give the day's mean price and how far a move has stretched from it. A fast moving average is drawn in red as a short-term trend reference. Unusually busy bars get a translucent bubble, green or red by direction, sized by how much traded. A cumulative-delta strip runs along the bottom of the panel with a per-bar histogram and a dashed running total.

None of that changes what the indicator claims to do. It marks where volume concentrated and which side absorbed it. It places no orders, and no strategy is attached to it. The color mode is a volume measure, not a signal, and the trend line is decoration until someone tests it.

Two defects turned up while adding the layers. The heatmap was adding a new row on every incoming tick instead of once per bar, and the drawing pass read price data directly, which fails when a chart reloads and the indicator and the chart briefly disagree about how many bars exist. Both were patched the same day.

Those patches did not make it right. Checked on the live chart that evening, the indicator was still wrong in five ways, and the chart showed it: every delta bar in the strip was identical, and most of the new layers were drawn in empty space to the right of the last candle.

1. Every heatmap row was built from the first bar loaded on the chart, not the current one. The code asked for "bar number N" where the platform reads "N bars ago", so the whole heatmap, the delta strip and the cumulative delta were copies of one old bar. Divergence detection had the same mistake.
2. The layers were spread evenly across the panel instead of being placed at each bar's own position, so they did not move with the candles when the chart scrolled or zoomed, and the newest bars were never drawn.
3. On a live chart, the session VWAP added the current bar's volume again on every tick, the trend line stepped once per tick instead of once per bar, and absorption, divergence and sweep checks ran on every tick.
4. The first tick of each new bar has no range yet. That tick added no row, so the next tick deleted the previous, finished bar instead.
5. Live buy and sell counts classified trades before a bid and ask were known, so early prints all counted as buying.

All five are fixed. Everything that accumulates now updates once per closed bar, every layer is drawn at its own bar, and the dashboard labels its live delta as counted since the chart loaded and its cumulative delta as an estimate. It compiles clean and was re-checked on the same chart. The buy and sell split is still an estimate from bar direction, not real order flow, and the divergence count runs high for that reason. It is a reading tool, not a signal.
