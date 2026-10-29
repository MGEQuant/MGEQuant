---
layout: default
date: "2026-10-23"
title: "Platform — October 2026"
---

## October 13–15 — MGE Labs: a trade journal for NinjaTrader 8, in private beta

A journal that collects every closed trade from the PCs you trade on into one place, scored in R against the risk you set. It covers automated strategies and hand trades, and hand trades can be tagged with your own setup names. Win rate is only ever shown next to expectancy in R. It runs in the browser and can be installed as an app.

On the PC it is one compiled NinjaTrader add-on, paired to the account with a one-time code. Package updates resync on their own the first time NinjaTrader starts, so nobody has to unpair and pair again. The account has two-step sign-in with recovery codes, a support form, and a CSV export of every trade that stays available after cancelling.

Subscriptions were tested end to end in a payment sandbox: a seven-day trial, checkout, a self-service page to change the card or cancel, and access that runs to the end of the paid period and then turns read-only. The test found a real bug. The payment provider timestamps "subscription created" a second before "checkout completed", so the code treated the event carrying the renewal date as stale and dropped it. A completed checkout no longer counts as the newest subscription event, and a test now reproduces that exact order.

Sign-ups stay closed until the business registration and the legal review are done.

## October 17–23 — Payout Guard, Prop Ledger, and guards for the habits that follow a loss

Payout Guard now keeps every prop account on every PC in one searchable list, with the accounts that need you first. Some traders hold dozens of accounts at once, so a page per account does not work. Each account is tracked against the rules you enter for it, and the page has one job: when a payout is within reach, say so before the next trade.

Prop Ledger adds up what prop trading has cost: evaluation fees, resets, activation and monthly fees against payouts, per firm and per account, so the net is one number. Fees are typed in by hand, because they are paid on the firms' own sites. Accounts appear under a nickname you choose, never an account number.

Four habit guards sit inside the same tool: a cooldown after a losing trade, stopping for the day after a set number of losses in a row, no larger size right after a loss, and too many trades too fast. The numbers are yours, and they start as warnings, not blocks. They ran on a simulator account before anyone else got them.

The journal also got a Tilt card. It compares the trades you took within a few minutes of a loss with the rest of your trades, in R or in dollars, using only your own closed trades. It is a record of your habits, not advice, and it says "not enough yet" until there are enough trades to say anything.

One lesson from using it on our own test account: nearly every trade there was automated, so the first version of the card was describing the machines, not the trader. It now has a Hand / All switch, and it starts on hand trades only once there are ten of them.

In the journal package none of these tools places or blocks an order. They warn.
