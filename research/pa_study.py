"""Empirical test of price-action setups on 9 years of NIFTY 5-minute bars.

Every setup is defined mechanically, evaluated with the same trade simulator
(stop 1 ATR, target 2 ATR, time stop 24 bars, same-session only, SL-first when both touched),
and reported in R multiples with a 2017-2022 train / 2023-2026 test split.

Usage:  python research/pa_study.py [cache/hist_5m.parquet]
"""
from __future__ import annotations

import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from nifty_signals.indicators import core as I  # noqa: E402

PATH = sys.argv[1] if len(sys.argv) > 1 else "cache/hist_5m.parquet"
SL_ATR, TP_ATR, TIME_BARS = 1.0, 2.0, 24
TRAIN_END = pd.Timestamp("2022-12-31", tz="Asia/Kolkata")

b = pd.read_parquet(PATH)
o, h, l, c = (b[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
idx = b.index
n = len(b)
dates = idx.date
sess_codes, _ = pd.factorize(pd.Index(dates), sort=True)
sess = sess_codes.astype(np.int64)
bar_idx = I.session_bar_index(sess)
atr = I.atr(h, l, c, 14)
tp = (h + l + c) / 3.0
vwap = I.session_vwap(tp, np.zeros(n), sess)
sw_h, sw_l, _, _ = I.swing_pivots(h, l, 3)
hour = idx.hour
minute = idx.minute
tod = hour * 60 + minute
year = idx.year
is_train = (idx <= TRAIN_END)

# previous-day levels
daily = b.groupby(sess_codes).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"), open=("open", "first"))
pdh = daily["high"].shift(1).reindex(sess_codes).to_numpy()
pdl = daily["low"].shift(1).reindex(sess_codes).to_numpy()
pdc = daily["close"].shift(1).reindex(sess_codes).to_numpy()
d_open = daily["open"].reindex(sess_codes).to_numpy()
# running session high/low BEFORE the current bar
run_h = np.full(n, np.nan)
run_l = np.full(n, np.nan)
cur = -1
for i in range(n):
    if sess[i] != cur:
        cur = sess[i]
        hh, ll = -1e300, 1e300
    run_h[i] = hh if hh > -1e300 else np.nan
    run_l[i] = ll if ll < 1e300 else np.nan
    hh = max(hh, h[i])
    ll = min(ll, l[i])
# opening range (first 3 bars = 15 min)
or_h, or_l = I.session_opening_range(h, l, sess, 3)
rng = h - l
body = np.abs(c - o)


def simulate(i: int, d: int) -> float:
    """R-multiple of a trade entered at close of bar i in direction d."""
    a = atr[i]
    if not np.isfinite(a) or a <= 0:
        return np.nan
    e = c[i]
    sl = e - d * SL_ATR * a
    tgt = e + d * TP_ATR * a
    for k in range(i + 1, min(n, i + 1 + TIME_BARS)):
        if sess[k] != sess[i]:
            return (c[k - 1] - e) * d / (SL_ATR * a)
        if (d > 0 and l[k] <= sl) or (d < 0 and h[k] >= sl):
            return -1.0
        if (d > 0 and h[k] >= tgt) or (d < 0 and l[k] <= tgt):
            return TP_ATR / SL_ATR
    k = min(n - 1, i + TIME_BARS)
    return (c[k] - e) * d / (SL_ATR * a)


def ok(i: int) -> bool:
    """Entry allowed: warm-up done, inside 09:30-14:45, not within 24 bars of the close."""
    return np.isfinite(atr[i]) and 570 <= tod[i] <= 885 and bar_idx[i] >= 3


results: dict[str, list[tuple[int, int]]] = defaultdict(list)   # name -> [(i, dir)]

for i in range(30, n - 30):
    if not ok(i):
        continue
    a = atr[i]
    bull = c[i] > o[i] and (c[i] - l[i]) / max(rng[i], 1e-9) >= 0.6
    bear = c[i] < o[i] and (h[i] - c[i]) / max(rng[i], 1e-9) >= 0.6

    # A. prior-day high/low sweep and reject (liquidity grab reversal)
    if np.isfinite(pdh[i]) and h[i] > pdh[i] and c[i] < pdh[i] and c[i - 1] < pdh[i] and bear:
        results["A_pdh_sweep_short"].append((i, -1))
    if np.isfinite(pdl[i]) and l[i] < pdl[i] and c[i] > pdl[i] and c[i - 1] > pdl[i] and bull:
        results["A_pdl_sweep_long"].append((i, 1))
    # A2. prior-day level break-and-hold (acceptance): two closes beyond the level
    if np.isfinite(pdh[i]) and c[i] > pdh[i] and c[i - 1] > pdh[i] and c[i - 2] <= pdh[i] and bull:
        results["A2_pdh_break_hold_long"].append((i, 1))
    if np.isfinite(pdl[i]) and c[i] < pdl[i] and c[i - 1] < pdl[i] and c[i - 2] >= pdl[i] and bear:
        results["A2_pdl_break_hold_short"].append((i, -1))

    # B. session high/low sweep (set >= 12 bars ago) and reject
    if bar_idx[i] >= 15 and np.isfinite(run_h[i]) and h[i] > run_h[i] and c[i] < run_h[i] and bear \
            and np.all(h[i - 12:i] < run_h[i] + 1e-9):
        results["B_session_high_sweep_short"].append((i, -1))
    if bar_idx[i] >= 15 and np.isfinite(run_l[i]) and l[i] < run_l[i] and c[i] > run_l[i] and bull \
            and np.all(l[i - 12:i] > run_l[i] - 1e-9):
        results["B_session_low_sweep_long"].append((i, 1))

    # C. break of structure then retest: close above last swing high (BOS) within last 12 bars,
    #    now a pullback to within 0.3 ATR of that level and a bullish bar
    sh = sw_h[i - 1]
    if np.isfinite(sh):
        bos_bar = None
        for k in range(i - 12, i):
            if c[k] > sh and c[k - 1] <= sh:
                bos_bar = k
        if bos_bar is not None and l[i] <= sh + 0.3 * a and c[i] > sh and bull and np.all(c[bos_bar:i] > sh - 0.5 * a):
            results["C_bos_retest_long"].append((i, 1))
    sl_ = sw_l[i - 1]
    if np.isfinite(sl_):
        bos_bar = None
        for k in range(i - 12, i):
            if c[k] < sl_ and c[k - 1] >= sl_:
                bos_bar = k
        if bos_bar is not None and h[i] >= sl_ - 0.3 * a and c[i] < sl_ and bear and np.all(c[bos_bar:i] < sl_ + 0.5 * a):
            results["C_bos_retest_short"].append((i, -1))

    # D. fair value gap: impulsive 3-bar gap (low[j] > high[j-2]) with middle bar >= 1.2 ATR,
    #    price later returns into the gap and closes bullish above the gap low
    for j in range(i - 12, i - 1):
        if l[j] > h[j - 2] and rng[j - 1] >= 1.2 * atr[j - 1]:
            gap_lo, gap_hi = h[j - 2], l[j]
            if l[i] <= gap_hi and c[i] > gap_lo and bull and np.all(l[j + 1:i] > gap_lo):
                results["D_fvg_long"].append((i, 1))
                break
        if h[j] < l[j - 2] and rng[j - 1] >= 1.2 * atr[j - 1]:
            gap_lo, gap_hi = h[j], l[j - 2]
            if h[i] >= gap_lo and c[i] < gap_hi and bear and np.all(h[j + 1:i] < gap_hi):
                results["D_fvg_short"].append((i, -1))
                break

    # E. order block: last bearish bar before an impulsive move (>= 2 ATR net in <= 3 bars) that
    #    makes a new 20-bar high; later price returns to the OB and prints a bullish bar
    for j in range(i - 24, i - 4):
        if c[j] < o[j] and (c[j + 3] - c[j]) >= 2.0 * a and c[j + 3] > np.max(h[j - 20:j]):
            ob_lo, ob_hi = l[j], h[j]
            if l[i] <= ob_hi and c[i] > ob_lo and bull and np.all(l[j + 4:i] > ob_hi):
                results["E_orderblock_long"].append((i, 1))
                break
        if c[j] > o[j] and (c[j] - c[j + 3]) >= 2.0 * a and c[j + 3] < np.min(l[j - 20:j]):
            ob_lo, ob_hi = l[j], h[j]
            if h[i] >= ob_lo and c[i] < ob_hi and bear and np.all(h[j + 4:i] < ob_lo):
                results["E_orderblock_short"].append((i, -1))
                break

    # F. inside bar breakout (mother bar >= 1 ATR, inside bar, break of mother high/low with a strong close)
    if h[i - 1] <= h[i - 2] and l[i - 1] >= l[i - 2] and rng[i - 2] >= 1.0 * a:
        if c[i] > h[i - 2] and bull:
            results["F_insidebar_break_long"].append((i, 1))
        if c[i] < l[i - 2] and bear:
            results["F_insidebar_break_short"].append((i, -1))

    # G. engulfing at a key level (PDL/PDH/VWAP within 0.3 ATR)
    eng_bull = c[i] > o[i] and c[i - 1] < o[i - 1] and c[i] > o[i - 1] and o[i] < c[i - 1] and body[i] >= 0.6 * a
    eng_bear = c[i] < o[i] and c[i - 1] > o[i - 1] and c[i] < o[i - 1] and o[i] > c[i - 1] and body[i] >= 0.6 * a
    near_lo = (np.isfinite(pdl[i]) and abs(l[i] - pdl[i]) <= 0.3 * a) or abs(l[i] - vwap[i]) <= 0.3 * a
    near_hi = (np.isfinite(pdh[i]) and abs(h[i] - pdh[i]) <= 0.3 * a) or abs(h[i] - vwap[i]) <= 0.3 * a
    if eng_bull and near_lo:
        results["G_engulf_at_level_long"].append((i, 1))
    if eng_bear and near_hi:
        results["G_engulf_at_level_short"].append((i, -1))
    if eng_bull:
        results["G0_engulf_any_long"].append((i, 1))
    if eng_bear:
        results["G0_engulf_any_short"].append((i, -1))

    # H. VWAP: rejection (wick through, close back) and reclaim (close through after 3 bars on the other side)
    if l[i] < vwap[i] < c[i] and np.all(c[i - 3:i] > vwap[i - 3:i]) and bull:
        results["H_vwap_reject_long"].append((i, 1))
    if h[i] > vwap[i] > c[i] and np.all(c[i - 3:i] < vwap[i - 3:i]) and bear:
        results["H_vwap_reject_short"].append((i, -1))
    if c[i] > vwap[i] and np.all(c[i - 3:i] < vwap[i - 3:i]) and bull:
        results["H2_vwap_reclaim_long"].append((i, 1))
    if c[i] < vwap[i] and np.all(c[i - 3:i] > vwap[i - 3:i]) and bear:
        results["H2_vwap_reclaim_short"].append((i, -1))

    # I. open outside prior-day range and holding: first close after 09:45 still beyond PDH/PDL
    if bar_idx[i] == 6 and np.isfinite(pdh[i]):
        if d_open[i] > pdh[i] and c[i] > pdh[i] and np.all(l[i - 6:i + 1] > pdh[i] - 0.3 * a):
            results["I_open_above_pdh_hold_long"].append((i, 1))
        if d_open[i] < pdl[i] and c[i] < pdl[i] and np.all(h[i - 6:i + 1] < pdl[i] + 0.3 * a):
            results["I_open_below_pdl_hold_short"].append((i, -1))
    # I2. opening-range (15m) breakout with retest: close beyond OR, then pullback to OR edge, then resume
    if np.isfinite(or_h[i]) and bar_idx[i] >= 5 and l[i] <= or_h[i] + 0.2 * a and c[i] > or_h[i] and bull \
            and np.any(c[i - 6:i] > or_h[i]) and np.all(c[i - 6:i] > or_h[i] - 0.5 * a):
        results["I2_orb_retest_long"].append((i, 1))
    if np.isfinite(or_l[i]) and bar_idx[i] >= 5 and h[i] >= or_l[i] - 0.2 * a and c[i] < or_l[i] and bear \
            and np.any(c[i - 6:i] < or_l[i]) and np.all(c[i - 6:i] < or_l[i] + 0.5 * a):
        results["I2_orb_retest_short"].append((i, -1))

    # J. round-number (multiple of 100) rejection
    r100 = round(c[i] / 100) * 100
    if h[i] >= r100 >= c[i] and c[i - 1] < r100 and bear and abs(h[i] - r100) <= 0.15 * a:
        results["J_round100_reject_short"].append((i, -1))
    if l[i] <= r100 <= c[i] and c[i - 1] > r100 and bull and abs(l[i] - r100) <= 0.15 * a:
        results["J_round100_reject_long"].append((i, 1))

# baseline: random strong bars in the same window
rng_ = np.random.default_rng(0)
cand = [i for i in range(30, n - 30, 7) if ok(i)]
for i in cand:
    d = 1 if c[i] > o[i] else -1
    results["Z_baseline_strong_bar_dir"].append((i, d))
    results["Z_baseline_random_dir"].append((i, int(rng_.choice([-1, 1]))))


def summarise(name: str, trades: list[tuple[int, int]]) -> dict:
    r = np.array([simulate(i, d) for i, d in trades])
    tr = np.array([is_train[i] for i, _ in trades])
    r = r[np.isfinite(r)]
    tr = tr[: len(r)]
    out = dict(setup=name, n=len(r), win=100 * np.mean(r > 0) if len(r) else np.nan, expR=np.mean(r) if len(r) else np.nan)
    out["train_expR"] = np.mean(r[tr]) if tr.sum() else np.nan
    out["test_expR"] = np.mean(r[~tr]) if (~tr).sum() else np.nan
    out["n_test"] = int((~tr).sum())
    yrs = np.array([year[i] for i, _ in trades])[: len(r)]
    pos_years = sum(np.mean(r[yrs == y]) > 0 for y in np.unique(yrs) if (yrs == y).sum() >= 10)
    tot_years = sum(1 for y in np.unique(yrs) if (yrs == y).sum() >= 10)
    out["pos_years"] = f"{pos_years}/{tot_years}"
    out["t"] = np.mean(r) / (np.std(r) / np.sqrt(len(r))) if len(r) > 2 else np.nan
    return out


rows = [summarise(k, v) for k, v in sorted(results.items())]
df = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(f"bars {n}  sessions {sess.max() + 1}  sim: SL {SL_ATR} ATR, TP {TP_ATR} ATR, time {TIME_BARS} bars (breakeven win rate {100 * SL_ATR / (SL_ATR + TP_ATR):.0f}%)")
print(df.round(3).to_string(index=False))
df.to_csv("cache/pa_study_results.csv", index=False)
