---
layout: default
date: "2026-10-24"
title: "Indicators — October 2026"
---

Indicators read the market and draw on the chart. None of them place orders.

## October 23 — FlowEdge: a truth check found a backwards estimate

FlowEdge splits each bar's volume into buying and selling. On live bars it uses the real bid and ask. On history and playback there is no bid and ask, so it estimates the split from the candle. In September we wrote that this estimate was only an estimate. We had not yet measured how good it was.

We measured it against real trade-by-trade data from a data vendor, bar by bar. On down bars the estimate was backwards: it read them as buying, with a correlation between −0.4 and −0.5 against the real figure, on the recent sample and on an older one. Over all bars it carried almost nothing, about 0.1 or less. The formula had been mirrored on down bars.

The fix is the plain close-location estimate: the closer a bar closes to its high, the larger its buy share, whatever the direction of the bar. Against the same real data it now correlates at about 0.5 to 0.6 and agrees in sign on roughly seven bars in ten. That is a rough estimate, not a measurement, and the captions on this site already say which bars are estimated. The same line was in our BookMap indicator and is fixed there too.

## October 24 — IB 25/75: a check we failed first

The Initial Balance indicator draws the first hour of a session as a box with 25% and 75% lines. Before we call an indicator finished we check that it draws what its description says. For this one we rebuilt each session's first-hour range on its own, from one-minute bars, and compared it with the box over about 65 sessions each in New York, Asia and London.

The first run failed badly. The box matched on 34 of 65 New York sessions, 18 of 65 Asia sessions and 37 of 64 London sessions. There were three faults, all ours:

1. The code assumed the chart clock was Pacific time, so every other platform setting drew the box in the wrong place.
2. The window started one 5-minute bar early, because NinjaTrader stamps a bar with the time it closes.
3. The Asia box was fixed to Pacific minutes, but Tokyo has no daylight saving, so for half the year it was an hour off.

The corrected build reads the platform's own time zone, anchors the window to the bar's start, and ties the Asia box to the Tokyo clock. Re-run in five different platform time zones, it matched 65 of 65 New York, 65 of 65 Asia and 64 of 64 London sessions. It needs a 5-minute chart and says so on the chart.

This check tests the drawing, not the trading. It says the boxes sit where they should, and nothing about whether anything made money. The retracement strategy built on these levels stays closed.
