"""Feature construction: multi-timeframe technical state per execution bar, with no look-ahead.

Columns produced (all aligned to the 5m bar index):
  price:   open high low close volume
  5m:      ema_f ema_m ema_s atr atr_pct rsi adx pdi mdi st_line st_dir macd macd_sig macd_hist
           bb_mid bb_up bb_lo bb_w bb_w_pct er dc_up dc_lo vwap or_h or_l sw_h sw_l sw_h2 sw_l2 slope
           bar_idx (bar number within the session)
  15m:     h_ema_f h_ema_s h_close h_adx h_rsi h_st_dir  (last COMPLETED 15m bar)
  daily:   d_ema d_close d_high d_low (previous completed day)  d_bias (+1/-1/0)
  context: vix vix_ma (20-day mean) dte session
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import Config
from ..data.feed import IST, resample, session_ids
from ..indicators import core as I
from .calendar import ExpiryCalendar


def _htf_align(base: pd.DataFrame, htf: pd.DataFrame, htf_minutes: int, base_minutes: int) -> pd.DataFrame:
    """Map each base bar to the last HTF bar that *completed* at or before the base bar's close."""
    h = htf.copy()
    h["_end"] = h.index + pd.Timedelta(minutes=htf_minutes)
    h = h.sort_values("_end")
    b = pd.DataFrame(index=base.index)
    b["_end"] = b.index + pd.Timedelta(minutes=base_minutes)
    b = b.reset_index()
    merged = pd.merge_asof(b.sort_values("_end"), h.reset_index(drop=True), on="_end", direction="backward")
    merged = merged.set_index(base.index.name or "index").sort_index()
    merged.index = base.index
    return merged.drop(columns=["_end"])


def build_features(bars5: pd.DataFrame, daily: pd.DataFrame, vix: pd.DataFrame | None,
                   cfg: Config, cal: ExpiryCalendar) -> pd.DataFrame:
    ic = cfg.ind
    df = bars5.copy()
    o, h, l, c = (df[k].to_numpy(np.float64) for k in ("open", "high", "low", "close"))
    v = df["volume"].to_numpy(np.float64)
    sess = session_ids(df.index)

    df["session"] = sess
    df["bar_idx"] = I.session_bar_index(sess)
    df["sess_open"] = df.groupby("session")["open"].transform("first")
    df["ema_f"] = I.ema(c, ic.ema_fast)
    df["ema_m"] = I.ema(c, ic.ema_mid)
    df["ema_s"] = I.ema(c, ic.ema_slow)
    df["atr"] = I.atr(h, l, c, ic.atr_len)
    df["atr_pct"] = I.pct_rank(df["atr"].to_numpy(), ic.pct_window)
    df["rsi"] = I.rsi(c, ic.rsi_len)
    adx, pdi, mdi = I.adx(h, l, c, ic.adx_len)
    df["adx"], df["pdi"], df["mdi"] = adx, pdi, mdi
    st_line, st_dir = I.supertrend(h, l, c, ic.st_len, ic.st_mult)
    df["st_line"], df["st_dir"] = st_line, st_dir
    m, s_, hist = I.macd(c, ic.macd_fast, ic.macd_slow, ic.macd_sig)
    df["macd"], df["macd_sig"], df["macd_hist"] = m, s_, hist
    mid, up, lo, bw = I.bollinger(c, ic.bb_len, ic.bb_k)
    df["bb_mid"], df["bb_up"], df["bb_lo"], df["bb_w"] = mid, up, lo, bw
    df["bb_w_pct"] = I.pct_rank(bw, ic.pct_window)
    df["er"] = I.efficiency_ratio(c, ic.er_len)
    dcu, dcl = I.donchian(h, l, ic.donchian_len)
    df["dc_up"], df["dc_lo"] = dcu, dcl
    tp = (h + l + c) / 3.0
    df["vwap"] = I.session_vwap(tp, v, sess)
    orh, orl = I.session_opening_range(h, l, sess, ic.or_bars)
    df["or_h"], df["or_l"] = orh, orl
    sh, sl, sh2, sl2 = I.swing_pivots(h, l, ic.pivot_k)
    df["sw_h"], df["sw_l"], df["sw_h2"], df["sw_l2"] = sh, sl, sh2, sl2
    df["slope"] = I.linreg_slope(c, ic.ema_mid)

    # ---- higher timeframe (15m) -------------------------------------------------
    base_min = int(cfg.data.bar_interval[:-1])
    htf_min = int(cfg.data.htf_interval[:-1])
    htf = resample(bars5, htf_min)
    hc = htf["close"].to_numpy(np.float64)
    hh = htf["high"].to_numpy(np.float64)
    hl = htf["low"].to_numpy(np.float64)
    hf = pd.DataFrame(index=htf.index)
    hf["h_ema_f"] = I.ema(hc, ic.htf_ema_fast)
    hf["h_ema_s"] = I.ema(hc, ic.htf_ema_slow)
    hf["h_close"] = hc
    hf["h_adx"] = I.adx(hh, hl, hc, ic.adx_len)[0]
    hf["h_rsi"] = I.rsi(hc, ic.rsi_len)
    hf["h_st_dir"] = I.supertrend(hh, hl, hc, ic.st_len, ic.st_mult)[1]
    aligned = _htf_align(df, hf, htf_min, base_min)
    for col in hf.columns:
        df[col] = aligned[col].to_numpy()

    # ---- daily context (previous completed day only) -----------------------------
    d = daily.copy()
    d.index = pd.DatetimeIndex(d.index).tz_convert(IST).normalize()
    dc = d["close"].to_numpy(np.float64)
    dd = pd.DataFrame(index=d.index)
    dd["d_ema"] = I.ema(dc, ic.daily_ema)
    dd["d_close"] = dc
    dd["d_high"] = d["high"].to_numpy()
    dd["d_low"] = d["low"].to_numpy()
    # look up the last daily row strictly BEFORE each bar's date (no same-day leakage)
    day_key = df.index.tz_convert(IST).normalize()
    prev_key = day_key - pd.Timedelta(days=1)
    dj = dd.reindex(prev_key, method="ffill")
    for col in dd.columns:
        df[col] = dj[col].to_numpy()
    df["d_bias"] = np.sign(df["d_close"] - df["d_ema"]).fillna(0.0)

    # ---- VIX (previous close, so it is known intraday) ---------------------------
    if vix is not None and not vix.empty:
        vx = vix.copy()
        vx.index = pd.DatetimeIndex(vx.index).tz_convert(IST).normalize()
        vxc = vx["close"]
        df["vix"] = vxc.reindex(prev_key, method="ffill").to_numpy()
        df["vix_ma"] = vxc.rolling(20, min_periods=5).mean().reindex(prev_key, method="ffill").to_numpy()
    else:
        # no VIX series: proxy with 20-day realised vol (annualised, %) scaled by the median India VIX /
        # realised-vol ratio 2018-2026 (1.27; the premium is 1.17-1.32 in every year)
        lr = np.log(d["close"]).diff()
        rv = (lr.rolling(20).std() * np.sqrt(252) * 100.0 * 1.27)
        df["vix"] = rv.reindex(prev_key, method="ffill").to_numpy()
        df["vix_ma"] = rv.rolling(20, min_periods=5).mean().reindex(prev_key, method="ffill").to_numpy()

    # ---- expiry -----------------------------------------------------------------
    df["dte"] = cal.dte_array(df.index)
    return df
