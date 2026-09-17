# Fixed-sample trade review

Selection: earliest saved entry in each observed (level name, exit reason) category.
Every saved field in this sample matches a replay of the existing simulator.
Setup aggregation, level selection, trigger, stop and entry arithmetic were checked.
**Internal consistency only: this does not independently validate execution or chart prices.**

Prices are back-adjusted continuous prices, not necessarily raw contract prices.
Pacific times use America/Los_Angeles with DST, not fixed UTC-08:00.
Times label minute closes, not exact intraminute fills.

| ID | Level / exit | NY setup | Pacific setup | Trigger | Entry | Stop | Target | Ambiguous minutes |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| S01 | ORH / target | 2019-12-12T11:15:00-05:00 | 2019-12-12T08:15:00-08:00 | 11781.75 | 11781.5 | 11793.25 | 11758.0 | 0 |
| S02 | ORH / stop | 2019-12-13T09:50:00-05:00 | 2019-12-13T06:50:00-08:00 | 11785.0 | 11784.75 | 11797.25 | 11759.75 | 0 |
| S03 | PDH / noon | 2019-12-13T10:15:00-05:00 | 2019-12-13T07:15:00-08:00 | 11812.5 | 11812.25 | 11843.25 | 11750.25 | 0 |
| S04 | ORL / stop | 2019-12-17T09:55:00-05:00 | 2019-12-17T06:55:00-08:00 | 11899.0 | 11899.25 | 11893.75 | 11910.25 | 0 |
| S05 | ORL / noon | 2019-12-17T10:05:00-05:00 | 2019-12-17T07:05:00-08:00 | 11903.0 | 11903.25 | 11892.75 | 11924.25 | 0 |
| S06 | PDH / stop | 2019-12-18T09:50:00-05:00 | 2019-12-18T06:50:00-08:00 | 11912.0 | 11911.75 | 11925.5 | 11884.25 | 0 |
| S07 | PDL / target | 2020-01-06T09:45:00-05:00 | 2020-01-06T06:45:00-08:00 | 12073.0 | 12073.25 | 12060.5 | 12098.75 | 0 |
| S08 | ORL / target | 2020-01-07T09:50:00-05:00 | 2020-01-07T06:50:00-08:00 | 12145.0 | 12145.25 | 12131.0 | 12173.75 | 0 |
| S09 | PDH / target | 2020-01-08T10:25:00-05:00 | 2020-01-08T07:25:00-08:00 | 12180.75 | 12180.5 | 12192.0 | 12157.5 | 0 |
| S10 | ORH / noon | 2020-01-23T10:50:00-05:00 | 2020-01-23T07:50:00-08:00 | 12487.25 | 12487.0 | 12500.75 | 12459.5 | 0 |
| S11 | PDL / stop | 2020-01-31T11:20:00-05:00 | 2020-01-31T08:20:00-08:00 | 12347.75 | 12348.0 | 12313.75 | 12416.5 | 0 |
| S12 | PDL / noon | 2020-04-24T10:15:00-04:00 | 2020-04-24T07:15:00-07:00 | 11940.25 | 11940.5 | 11904.75 | 12012.0 | 0 |

## Manual NinjaTrader checklist

- [ ] Record contract, provider, timezone, trading-hours template and merge policy.
- [ ] Reconcile the raw contract prices with the continuous adjustment.
- [ ] Compare setup minute candles and five-minute OHLC in samples.json.
- [ ] Check prior complete cash-session high/low or 09:30-09:45 ET opening range.
- [ ] Compare entry/exit minute candles in candles.csv; review gap/slippage assumptions.
- [ ] Review ambiguous_minutes with tick data if available; OHLC cannot prove ordering.
- [ ] Record agreements/disagreements; independent chart verification remains pending.

Ambiguity flags cover both stop/target touches and entry-minute exit touches.
They are not a comprehensive execution-quality assessment.
No strategy rules, original result files, indicators or live orders were changed.
