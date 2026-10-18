---
layout: default
date: "2026-10-15"
title: "Platform — October 2026"
---

## October 13–15 — MGE Labs: a trade journal for NinjaTrader 8, in private beta

A journal that collects every closed trade from the PCs you trade on into one place, scored in R against the risk you set. It covers automated strategies and hand trades, and hand trades can be tagged with your own setup names. Win rate is only ever shown next to expectancy in R. It runs in the browser and can be installed as an app.

On the PC it is one compiled NinjaTrader add-on, paired to the account with a one-time code. Package updates resync on their own the first time NinjaTrader starts, so nobody has to unpair and pair again. The account has two-step sign-in with recovery codes, a support form, and a CSV export of every trade that stays available after cancelling.

Subscriptions were tested end to end in a payment sandbox: a seven-day trial, checkout, a self-service page to change the card or cancel, and access that runs to the end of the paid period and then turns read-only. The test found a real bug. The payment provider timestamps "subscription created" a second before "checkout completed", so the code treated the event carrying the renewal date as stale and dropped it. A completed checkout no longer counts as the newest subscription event, and a test now reproduces that exact order.

An AI desk is in development and is not part of the subscription. Sign-ups stay closed until the business registration and the legal review are done.
