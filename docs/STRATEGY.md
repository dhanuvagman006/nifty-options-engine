# Strategy

Plain-language description of what the system trades and why. Numbers are from the 9-year replay
(`docs/PROOF.md`); the reasoning is in `docs/RESEARCH.md`.

## Why sell premium, hedged

Nine years of NIFTY 5-minute data show no intraday directional edge large enough to pay for an
option: the best price-action setups earn about 2.5 index points a trade, less than a round trip costs.
What is persistent is the gap between implied and realised volatility, and the fact that an option's
time value must reach zero at expiry. The system sells that time value with the loss capped by long
wings, and only in the sessions where the structure actually decays.

## The structure: weekly iron fly

| Leg | Strike |
|---|---|
| Sell call | ATM (spot rounded to 50) |
| Sell put | ATM |
| Buy call | ATM + 400 |
| Buy put | ATM - 400 |

All four legs in the nearest weekly expiry, intraday (MIS). Credit received is roughly 130-200 points
(Rs 10-15k per lot). Maximum possible loss is wing width minus credit, about Rs 15-20k per lot,
and the stop closes the structure long before that in normal markets.

## When it enters

Only on the **expiry day and the session before it** (Tuesday and Monday for NIFTY). Earlier in the
week a 400-point fly has almost no net decay: the wings lose value as fast as the straddle, so every
point the index moves is a loss (that variant lost 89% of days in the replay).

On those days a structure can be sold on any bar closing between 09:45 and 13:00 (13:00 on expiry
day too), while all of these hold:

| Filter | Default | Purpose |
|---|---|---|
| days to expiry | 0 to 2 | net theta exists |
| not an `event_dates` day | list in config | budget, RBI policy, election results, big earnings |
| move since the open | under 0.45% | not already a trend day |
| India VIX (prev close) | 9 to 24 | not a panic regime |
| VIX / 20-day mean | under 1.3 | not a vol spike in progress |
| chain PCR (live only) | 0.45 to 2.2 | no extreme one-sided positioning |
| gap at the open, 15m ADX | off (100) | both removed profitable days in the sweep; set 0.6 / 32 to enable |

Up to three structures a day. After a stop or take-profit the engine waits three bars and may sell a
fresh structure centred on the new ATM if the filters still pass (in practice rare).

## How it exits

The structure's close-out value is recomputed every bar from the chain (live) or the model (backtest).

| Exit | Rule |
|---|---|
| Take profit | value has fallen to 50% of the credit |
| Stop | loss reaches 0.35 x credit, checked at the bar's high and low |
| Time | 14:45 on any day; expiry day is held to 14:45 as well |
| Square-off | 15:10, enforced by the executor regardless of the engine |

## Sizing and capital

`lots = capital // margin_per_lot`, capped by `exec.max_lots`. One lot needs about Rs 40,000 of
hedged margin plus one maximum loss in reserve: **minimum Rs 60,000, Rs 1,00,000 recommended, and
not two lots below Rs 2,00,000.**

## What to expect (model)

About 7 structures a month, 83% winners, average +Rs 1,850 per structure, worst single structure
about Rs 6,000, drawdowns around Rs 10,000. Roughly Rs 12,000-13,500 a month per lot in the model;
plan on half until live paper trading confirms it. Details and caveats in `docs/PROOF.md`.

## The other strategies

- `pa_short`: buys an ITM weekly put on four short-side price-action setups (VWAP rejection, VWAP
  reclaim, prior-day-high sweep, prior-day-low break-and-hold) with the 15m trend down. Real spot edge,
  thin option result (profit factor 0.8-0.96, negative in 2026). Kept as a signal source for those who
  cannot sell.
- `confluence`: the original multi-factor option buyer. Loses over nine years; kept for comparison.

## Tuning without fooling yourself

Every parameter was chosen for a structural reason first and checked in a sweep second
(`docs/proof/sweep_*.txt`). If you change one, re-run the 9-year replay and look at the by-year line,
the worst trade and the drawdown, not just the total. Things that raise the total and the risk together:
500-point wings, holding past 14:45, removing the VIX filters, more than one lot per Rs 60,000.
