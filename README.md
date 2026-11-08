<div align="center">

<img src="https://avatars.githubusercontent.com/u/105890687?s=400" width="180" alt="MGEQuant logo">

<h1>MGEQuant</h1>
<h3>Honest quant trading research, built in the open.</h3>

<a href="https://x.com/MGEQuant"><img src="https://img.shields.io/badge/Follow-@MGEQuant-000000?style=for-the-badge&logo=x&logoColor=white" alt="Follow on X"></a>
<a href="https://mgequant.github.io/MGEQuant/mgequant-propfirm-calculator.html"><img src="https://img.shields.io/badge/Free_tool-Prop--firm_calculator-1f6feb?style=for-the-badge" alt="Prop-firm calculator"></a>
<a href="DevelopmentLogs/"><img src="https://img.shields.io/badge/Dev_logs-Updated_Oct_2026-0b1730?style=for-the-badge&labelColor=1f6feb" alt="Development logs"></a>

<img src="assets/banner.svg" width="100%" alt="8 tools built and tracked in the open. 2 retired after failing their own test. 0 have cleared every evidence test, so far.">

</div>

Most trading accounts show you the winners. **We publish the failures too**, with the numbers. We build indicators and strategies (started on NQ futures, now testing indices, forex, crypto and stocks), and most ideas do not survive testing. When they don't, we say so.

## Latest from the lab

| Date | What we tested | What we found |
|---|---|---|
| **Oct&nbsp;24** | [IB 25/75 indicator](DevelopmentLogs/Indicators/2026/10-October.md) | **Failed our own check first**: the box matched only 34 of 65 New York sessions. Three timezone bugs fixed. Now matches **65/65 NY, 65/65 Asia, 64/64 London**. |
| **Oct&nbsp;23** | [FlowEdge volume split](DevelopmentLogs/Indicators/2026/10-October.md) | Checked against real trade-by-trade data, the estimate was **backwards on down bars**. Fixed and re-measured. |
| **Oct&nbsp;4** | [90-minute bias strategy](DevelopmentLogs/Strategies/2026/10-October.md) | **~4,100 NQ trades, no edge.** Lost slightly after costs and did no better than random-direction entries. |

## How every idea is graded

```mermaid
flowchart LR
    A[Idea, written as<br/>exact rules] --> C[Backtest vs<br/>random entries]
    C --> D[Drop best 5% of trades<br/>+ check every year]
    D --> E[Forward test<br/>on a live account]
    E --> F((Counts))
    C -. fails .-> X[Published<br/>as a failure]
    D -. fails .-> X
    E -. fails .-> X
    style F fill:#1f6feb,color:#fff,stroke:#1f6feb
    style X fill:#3a1418,color:#ffb4b4,stroke:#e5484d
```

Every entry says how far an idea has been tested. **A rule appearing here does not mean it works.**

## What's here

| Section | What you'll find |
|---|---|
| [**Indicators**](DevelopmentLogs/Indicators/2026/10-October.md) | News Wire, Liquidity Heatmap, FlowEdge, IB 25/75 and more |
| [**Strategies**](DevelopmentLogs/Strategies/2026/10-October.md) | The setups we trade by hand, and how far each has been tested |
| [**MarketCoach**](DevelopmentLogs/MarketCoach/2026/09-September.md) | Including a passing test that turned out to be resting on roll gaps |
| [**Platform**](DevelopmentLogs/Platform/2026/10-October.md) | MGE Labs: a NinjaTrader 8 trade journal with prop-account and tilt guards (private beta) |
| [**Screenshots**](Screenshots/) | The tools on real charts |
| [**Mission and vision**](Mission%20and%20Vision/) | Why this exists, and what M-G-E stands for |
| [**Prop-firm calculator**](https://mgequant.github.io/MGEQuant/mgequant-propfirm-calculator.html) | Free tool |

## What we don't do

No trade signals · no trade advice · no performance promises · source code stays private

> [!WARNING]
> Educational and research content only. Not investment advice. Trading futures involves substantial risk of loss. Backtested results are hypothetical and do not represent actual trading.
