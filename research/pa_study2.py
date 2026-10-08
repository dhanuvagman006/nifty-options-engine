"""Stage 2: condition the surviving price-action setups on context and exit variants.

Survivors from pa_study.py (positive in both train and test, t > 1.3):
  H_vwap_reject_short, H2_vwap_reclaim_short, A2_pdl_break_hold_short, A_pdh_sweep_short, D_fvg_short
Also tests the long mirrors for completeness. Reports R after a cost haircut of COST_R per trade.
"""
from __future__ import annotations

import sys
from collections import defaultdict

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from nifty_signals.indicators import core as I  # noqa: E402

PATH = sys.argv[1] if len(sys.argv) > 1 else "cache/hist_5m.parquet"
COST_R = 0.08          # ~2 index points round trip (spread + brokerage + slippage) on a 25-point ATR
TRAIN_END = pd.Timestamp("2022-12-31", tz="Asia/Kolkata")

b = pd.read_parquet(PATH)
o, h, l, c = (b[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
idx = b.index
n = len(b)
sess_codes, _ = pd.factorize(pd.Index(idx.date), sort=True)
sess = sess_codes.astype(np.int64)
bar_idx = I.session_bar_index(sess)
atr = I.atr(h, l, c, 14)
atr_pct = I.pct_rank(atr, 1500)
vwap = I.session_vwap((h + l + c) / 3.0, np.zeros(n), sess)
ema_m = I.ema(c, 21)
adx, pdi, mdi = I.adx(h, l, c, 14)
er = I.efficiency_ratio(c, 10)
tod = idx.hour * 60 + idx.minute
year = idx.year
is_train = (idx <= TRAIN_END)
rng = h - l
daily = b.groupby(sess_codes).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"), open=("open", "first"))
pdh = daily["high"].shift(1).reindex(sess_codes).to_numpy()
pdl = daily["low"].shift(1).reindex(sess_codes).to_numpy()
pdc = daily["close"].shift(1).reindex(sess_codes).to_numpy()
d_ema20 = daily["close"].ewm(span=20, adjust=False).mean().shift(1).reindex(sess_codes).to_numpy()
d_bias = np.sign(pdc - d_ema20)
# 15m trend: ema20 > ema50 on resampled closes, mapped to completed 15m bars
b15 = b.resample("15min", label="left", closed="left", origin="start_day", offset="555min").agg({"close": "last"}).dropna()
e20 = pd.Series(I.ema(b15["close"].to_numpy(), 20), index=b15.index)
e50 = pd.Series(I.ema(b15["close"].to_numpy(), 50), index=b15.index)
h_trend = np.sign(e20 - e50)
h_end = b15.index + pd.Timedelta(minutes=15)
m = pd.merge_asof(pd.DataFrame({"_end": idx + pd.Timedelta(minutes=5)}), pd.DataFrame({"_end": h_end, "ht": h_trend.values}).sort_values("_end"), on="_end", direction="backward")
ht = m["ht"].to_numpy()
open_vs_pdc = np.sign(daily["open"].reindex(sess_codes).to_numpy() - pdc)


def simulate(i, d, sl_atr, tp_atr, time_bars):
    a = atr[i]
    e = c[i]
    sl = e - d * sl_atr * a
    tgt = e + d * tp_atr * a
    for k in range(i + 1, min(n, i + 1 + time_bars)):
        if sess[k] != sess[i]:
            return (c[k - 1] - e) * d / (sl_atr * a)
        if (d > 0 and l[k] <= sl) or (d < 0 and h[k] >= sl):
            return -1.0
        if (d > 0 and h[k] >= tgt) or (d < 0 and l[k] <= tgt):
            return tp_atr / sl_atr
    k = min(n - 1, i + time_bars)
    return (c[k] - e) * d / (sl_atr * a)


def ok(i):
    return np.isfinite(atr[i]) and np.isfinite(ht[i]) and 570 <= tod[i] <= 885 and bar_idx[i] >= 3


setups = defaultdict(list)
for i in range(30, n - 30):
    if not ok(i):
        continue
    a = atr[i]
    bull = c[i] > o[i] and (c[i] - l[i]) / max(rng[i], 1e-9) >= 0.6
    bear = c[i] < o[i] and (h[i] - c[i]) / max(rng[i], 1e-9) >= 0.6
    if h[i] > vwap[i] > c[i] and np.all(c[i - 3:i] < vwap[i - 3:i]) and bear:
        setups["vwap_reject_S"].append((i, -1))
    if l[i] < vwap[i] < c[i] and np.all(c[i - 3:i] > vwap[i - 3:i]) and bull:
        setups["vwap_reject_L"].append((i, 1))
    if c[i] < vwap[i] and np.all(c[i - 3:i] > vwap[i - 3:i]) and bear:
        setups["vwap_reclaim_S"].append((i, -1))
    if c[i] > vwap[i] and np.all(c[i - 3:i] < vwap[i - 3:i]) and bull:
        setups["vwap_reclaim_L"].append((i, 1))
    if np.isfinite(pdl[i]) and c[i] < pdl[i] and c[i - 1] < pdl[i] and c[i - 2] >= pdl[i] and bear:
        setups["pdl_break_hold_S"].append((i, -1))
    if np.isfinite(pdh[i]) and c[i] > pdh[i] and c[i - 1] > pdh[i] and c[i - 2] <= pdh[i] and bull:
        setups["pdh_break_hold_L"].append((i, 1))
    if np.isfinite(pdh[i]) and h[i] > pdh[i] and c[i] < pdh[i] and c[i - 1] < pdh[i] and bear:
        setups["pdh_sweep_S"].append((i, -1))
    if np.isfinite(pdl[i]) and l[i] < pdl[i] and c[i] > pdl[i] and c[i - 1] > pdl[i] and bull:
        setups["pdl_sweep_L"].append((i, 1))
    for j in range(i - 12, i - 1):
        if h[j] < l[j - 2] and rng[j - 1] >= 1.2 * atr[j - 1]:
            gap_lo, gap_hi = h[j], l[j - 2]
            if h[i] >= gap_lo and c[i] < gap_hi and bear and np.all(h[j + 1:i] < gap_hi):
                setups["fvg_S"].append((i, -1))
                break


def stats(trades, sl=1.0, tp=2.0, tb=24, mask=None):
    sel = [(i, d) for i, d in trades if mask is None or mask(i)]
    if len(sel) < 30:
        return dict(n=len(sel), win=np.nan, expR=np.nan, train=np.nan, test=np.nan, t=np.nan)
    r = np.array([simulate(i, d, sl, tp, tb) for i, d in sel]) - COST_R
    tr = np.array([is_train[i] for i, _ in sel])
    return dict(n=len(r), win=round(100 * np.mean(r > 0), 1), expR=round(r.mean(), 3),
                train=round(r[tr].mean(), 3) if tr.sum() else np.nan,
                test=round(r[~tr].mean(), 3) if (~tr).sum() else np.nan,
                t=round(r.mean() / (r.std() / np.sqrt(len(r))), 2))


pd.set_option("display.width", 220)
print(f"cost haircut {COST_R} R per trade\n")
print("== Base (SL 1 / TP 2 / 24 bars) ==")
print(pd.DataFrame([{"setup": k, **stats(v)} for k, v in setups.items()]).to_string(index=False))

conds = {
    "all": None,
    "hour 09:30-11:00": lambda i: tod[i] < 660,
    "hour 11:00-13:00": lambda i: 660 <= tod[i] < 780,
    "hour 13:00-14:45": lambda i: tod[i] >= 780,
    "15m trend with": lambda i: ht[i] == setups_dir[i],
    "15m trend against": lambda i: ht[i] == -setups_dir[i],
    "daily bias with": lambda i: d_bias[i] == setups_dir[i],
    "daily bias against": lambda i: d_bias[i] == -setups_dir[i],
    "open vs pdc with": lambda i: open_vs_pdc[i] == setups_dir[i],
    "ATR pct < 40": lambda i: atr_pct[i] < 40,
    "ATR pct 40-80": lambda i: 40 <= atr_pct[i] <= 80,
    "ATR pct > 80": lambda i: atr_pct[i] > 80,
    "ADX >= 25": lambda i: adx[i] >= 25,
    "ADX < 20": lambda i: adx[i] < 20,
    "ER >= 0.3": lambda i: er[i] >= 0.3,
    "below ema21 (short) / above (long)": lambda i: np.sign(c[i] - ema_m[i]) == setups_dir[i],
}
for name in ["vwap_reject_S", "vwap_reclaim_S", "pdl_break_hold_S", "pdh_sweep_S", "fvg_S", "vwap_reject_L", "pdh_break_hold_L"]:
    trades = setups[name]
    setups_dir = {i: d for i, d in trades}
    print(f"\n== {name} by condition ==")
    rows = []
    for cn, fn in conds.items():
        rows.append({"cond": cn, **stats(trades, mask=fn)})
    print(pd.DataFrame(rows).to_string(index=False))

print("\n== exit variants on vwap_reject_S + vwap_reclaim_S + pdl_break_hold_S + pdh_sweep_S (15m trend with) ==")
combo = []
for name in ["vwap_reject_S", "vwap_reclaim_S", "pdl_break_hold_S", "pdh_sweep_S"]:
    combo += [(i, d) for i, d in setups[name] if ht[i] == d]
combo = sorted(set(combo))
rows = []
for sl, tp, tb in [(1, 1.5, 24), (1, 2, 24), (1, 3, 24), (0.7, 2, 24), (1.5, 3, 24), (1, 2, 12), (1, 2, 36), (1, 4, 48)]:
    rows.append({"sl": sl, "tp": tp, "bars": tb, **stats(combo, sl, tp, tb)})
print(pd.DataFrame(rows).to_string(index=False))
yrs = np.array([year[i] for i, _ in combo])
r = np.array([simulate(i, d, 1, 2, 24) for i, d in combo]) - COST_R
print("\ncombo by year (SL1/TP2):")
print(pd.DataFrame({"year": yrs, "r": r}).groupby("year").r.agg(["size", "mean", lambda x: 100 * (x > 0).mean()]).round(3).to_string())
