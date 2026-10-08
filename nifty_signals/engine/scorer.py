"""Confluence scorer: hard vetoes first, then weighted evidence across independent categories.

A setup is only accepted when
  * no veto fires,
  * a concrete trigger exists on the current bar (pullback-resume / breakout / structure break),
  * the normalised score >= threshold and enough *independent* categories agree.
Option-chain factors are included only when a live snapshot is available; the score is
normalised over the factors that could be evaluated so backtests remain comparable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import time, timedelta

import numpy as np

from ..config import Config
from ..data.chain import ChainHistory, ChainSnapshot

REQUIRED = ["ema_f", "ema_m", "ema_s", "atr", "atr_pct", "rsi", "adx", "pdi", "mdi", "st_dir",
            "macd_hist", "bb_w_pct", "er", "dc_up", "dc_lo", "vwap", "h_ema_f", "h_ema_s", "h_close",
            "h_rsi", "h_st_dir", "h_adx", "d_close", "d_ema", "dte"]

# category -> list of (factor name, weight)
TECH_WEIGHTS = {
    "trend":      [("adx_strong", 10), ("adx_rising", 5), ("di_align", 5)],
    "momentum":   [("rsi_zone", 10), ("macd_sign", 5), ("macd_rising", 5)],
    "htf":        [("h_rsi", 5), ("h_st", 5), ("h_adx", 5)],
    "daily":      [("d_bias", 5), ("vs_pdc", 5)],
    "vwap":       [("vwap", 10)],
    "volatility": [("atr_zone", 5), ("er", 5)],
    "candle":     [("candle", 10), ("slope", 5)],
}
OPT_WEIGHTS = {
    "options":    [("flow_near", 10), ("unwind", 5), ("pcr_trend", 5), ("wall_room", 5)],
}


@dataclass
class ScoreResult:
    direction: int = 0              # +1 = buy CE, -1 = buy PE
    score: float = 0.0
    categories: int = 0
    trigger: str = ""
    vetoes: list[str] = field(default_factory=list)
    factors: dict[str, float] = field(default_factory=dict)
    passed: bool = False

    def summary(self) -> str:
        hit = [k for k, v in self.factors.items() if v > 0]
        return f"score={self.score:.0f} cats={self.categories} trig={self.trigger} +[{','.join(hit)}] veto=[{','.join(self.vetoes)}]"


def _bar_close_time(ts, bar_minutes: int) -> time:
    return (ts + timedelta(minutes=bar_minutes)).time()


def common_vetoes(w: dict, prev: dict, cfg: Config, bar_minutes: int) -> list[str]:
    """Vetoes independent of direction. `w` is the current bar's feature dict."""
    f = cfg.filt
    s = cfg.session
    v: list[str] = []
    for k in REQUIRED:
        val = w.get(k)
        if val is None or (isinstance(val, float) and np.isnan(val)):
            v.append("warmup")
            return v
    t = _bar_close_time(w["ts"], bar_minutes)
    end = s.expiry_entry_end if w["dte"] < 1.0 else s.entry_end
    if not (s.entry_start <= t <= end):
        v.append("time")
    vix = w.get("vix")
    if vix is not None and not np.isnan(vix) and not (f.vix_min <= vix <= f.vix_max):
        v.append("vix")
    if not (f.atr_pct_min <= w["atr_pct"] <= f.atr_pct_max):
        v.append("atr_pct")
    if w["adx"] < f.adx_chop_max and w["er"] < f.er_trend_min:
        v.append("chop")
    if w["bar_idx"] < 6:
        v.append("open")
    # large gap: stay out for the first hour
    if w["bar_idx"] < 12 and w["d_close"] > 0:
        gap = abs(w["sess_open"] - w["d_close"]) / w["d_close"] * 100.0
        if gap > 1.2:
            v.append("gap")
    return v


def _trigger(direction: int, w: dict, hist: list[dict], f) -> str:
    """Return the trigger name if the current bar is an actionable entry bar.

    deep_pb : pullback that reached the EMA21 zone over the last 6 bars (>=2 counter bars), then a strong
              bar that reclaims the 3-bar high/low and the fast EMA  (trend continuation)
    vwap_rc : strong close through session VWAP from the wrong side, in trend direction
    dc      : close beyond the 20-bar Donchian channel with range expansion (0.8..2.5 ATR)
    orb     : first close beyond the opening range (first 15 min) within the first 2 hours
    """
    c, o, h, l = w["close"], w["open"], w["high"], w["low"]
    rng = max(h - l, 1e-9)
    body = abs(c - o) / rng
    last3 = hist[-3:]
    last6 = hist[-6:]
    prev = hist[-1]
    if direction > 0:
        strong = c > o and body >= 0.5 and (c - l) / rng >= 0.65
        if not strong:
            return ""
        hh3 = max(x["high"] for x in last3)
        ll6 = min(x["low"] for x in last6)
        counter = sum(x["close"] < x["open"] for x in last6)
        if ll6 <= w["ema_m"] and c > hh3 and c > w["ema_f"] and counter >= 2:
            return "deep_pb"
        if prev["close"] < w["vwap"] < c and c > w["ema_f"]:
            return "vwap_rc"
        if c > w["dc_up"] and 0.8 * w["atr"] <= rng <= 2.5 * w["atr"] and w["bar_idx"] >= 3:
            return "dc"
        if not np.isnan(w["or_h"]) and prev["close"] <= w["or_h"] < c and rng >= 0.6 * w["atr"] and w["bar_idx"] <= 24:
            return "orb"
    else:
        strong = c < o and body >= 0.5 and (h - c) / rng >= 0.65
        if not strong:
            return ""
        ll3 = min(x["low"] for x in last3)
        hh6 = max(x["high"] for x in last6)
        counter = sum(x["close"] > x["open"] for x in last6)
        if hh6 >= w["ema_m"] and c < ll3 and c < w["ema_f"] and counter >= 2:
            return "deep_pb"
        if prev["close"] > w["vwap"] > c and c < w["ema_f"]:
            return "vwap_rc"
        if c < w["dc_lo"] and 0.8 * w["atr"] <= rng <= 2.5 * w["atr"] and w["bar_idx"] >= 3:
            return "dc"
        if not np.isnan(w["or_l"]) and prev["close"] >= w["or_l"] > c and rng >= 0.6 * w["atr"] and w["bar_idx"] <= 24:
            return "orb"
    return ""


def evaluate(direction: int, w: dict, hist: list[dict], chain: ChainSnapshot | None,
             chist: ChainHistory | None, cfg: Config, bar_minutes: int) -> ScoreResult:
    """Score one direction for the current bar. hist = previous bars' feature dicts (>= 3)."""
    f = cfg.filt
    r = ScoreResult(direction=direction)
    r.vetoes = common_vetoes(w, hist[-1] if hist else w, cfg, bar_minutes)
    if "warmup" in r.vetoes or len(hist) < 6:
        return r
    c = w["close"]
    d = direction
    # ---- structural requirements (vetoes) ---------------------------------------
    if d > 0:
        if not (w["h_ema_f"] > w["h_ema_s"] and w["h_close"] > w["h_ema_f"]):
            r.vetoes.append("htf")
        if not (c > w["ema_m"] and w["ema_f"] > w["ema_m"]):
            r.vetoes.append("ltf")
        if w["st_dir"] != 1:
            r.vetoes.append("st")
        if not (f.rsi_long_min <= w["rsi"] <= f.rsi_long_max):
            r.vetoes.append("rsi")
        if w["d_bias"] < 0:
            r.vetoes.append("daily")
    else:
        if not (w["h_ema_f"] < w["h_ema_s"] and w["h_close"] < w["h_ema_f"]):
            r.vetoes.append("htf")
        if not (c < w["ema_m"] and w["ema_f"] < w["ema_m"]):
            r.vetoes.append("ltf")
        if w["st_dir"] != -1:
            r.vetoes.append("st")
        if not (f.rsi_short_min <= w["rsi"] <= f.rsi_short_max):
            r.vetoes.append("rsi")
        if w["d_bias"] > 0:
            r.vetoes.append("daily")
    if w["er"] < f.er_hard_min:
        r.vetoes.append("er")
    r.trigger = _trigger(d, w, hist, f)
    if not r.trigger:
        r.vetoes.append("no_trigger")
    # over-extension only matters for continuation entries; breakouts are extended by nature
    if r.trigger in ("deep_pb", "vwap_rc") and abs(c - w["ema_m"]) / w["atr"] > f.max_ext_atr:
        r.vetoes.append("extended")
    # squeeze without expansion: no trade unless the trigger is a breakout
    if w["bb_w_pct"] < f.bbw_squeeze_pct and r.trigger not in ("dc", "orb"):
        r.vetoes.append("squeeze")
    # ---- option chain vetoes ------------------------------------------------------
    if chain is not None:
        pcr = chain.pcr_oi
        if not (f.pcr_hard_min <= pcr <= f.pcr_hard_max):
            r.vetoes.append("pcr_extreme")
        if d > 0 and not (f.pcr_long_min <= pcr <= f.pcr_long_max):
            r.vetoes.append("pcr")
        if d < 0 and not (f.pcr_short_min <= pcr <= f.pcr_short_max):
            r.vetoes.append("pcr")
        iv = chain.atm_iv_ce if d > 0 else chain.atm_iv_pe
        if iv > f.iv_cap:
            r.vetoes.append("iv")
        wall = chain.call_wall_pct if d > 0 else chain.put_wall_pct
        if 0 < wall < f.wall_veto_pct:
            r.vetoes.append("wall")
    if r.vetoes:
        return r
    # ---- evidence ------------------------------------------------------------------
    p3 = hist[-3]
    fac: dict[str, float] = {}
    fac["adx_strong"] = w["adx"] >= f.adx_trend_min
    fac["adx_rising"] = w["adx"] > p3["adx"]
    fac["di_align"] = (w["pdi"] > w["mdi"]) if d > 0 else (w["mdi"] > w["pdi"])
    fac["rsi_zone"] = (52 <= w["rsi"] <= 68) if d > 0 else (32 <= w["rsi"] <= 48)
    fac["macd_sign"] = (w["macd_hist"] > 0) if d > 0 else (w["macd_hist"] < 0)
    fac["macd_rising"] = (w["macd_hist"] > hist[-1]["macd_hist"]) if d > 0 else (w["macd_hist"] < hist[-1]["macd_hist"])
    fac["h_rsi"] = (w["h_rsi"] > 50) if d > 0 else (w["h_rsi"] < 50)
    fac["h_st"] = w["h_st_dir"] == d
    fac["h_adx"] = w["h_adx"] >= 18
    fac["d_bias"] = w["d_bias"] == d
    fac["vs_pdc"] = (c > w["d_close"]) if d > 0 else (c < w["d_close"])
    fac["vwap"] = (c > w["vwap"]) if d > 0 else (c < w["vwap"])
    fac["atr_zone"] = 30 <= w["atr_pct"] <= 85
    fac["er"] = w["er"] >= f.er_trend_min
    rng = max(w["high"] - w["low"], 1e-9)
    body = abs(w["close"] - w["open"]) / rng
    pos = (w["close"] - w["low"]) / rng
    fac["candle"] = body >= 0.5 and ((pos >= 0.7) if d > 0 else (pos <= 0.3))
    fac["slope"] = (w["slope"] > 0) if d > 0 else (w["slope"] < 0)
    weights = dict(TECH_WEIGHTS)
    if chain is not None:
        weights.update(OPT_WEIGHTS)
        if d > 0:
            fac["flow_near"] = chain.pe_chg_near > 0 and chain.pe_chg_near > chain.ce_chg_near
            fac["unwind"] = chain.ce_chg_above < 0
            fac["wall_room"] = chain.call_wall_pct >= f.wall_room_pct or chain.call_wall == 0
        else:
            fac["flow_near"] = chain.ce_chg_near > 0 and chain.ce_chg_near > chain.pe_chg_near
            fac["unwind"] = chain.pe_chg_below < 0
            fac["wall_room"] = chain.put_wall_pct >= f.wall_room_pct or chain.put_wall == 0
        tr = chist.pcr_trend() if chist is not None else 0.0
        fac["pcr_trend"] = (tr >= 0) if d > 0 else (tr <= 0)
    earned = 0.0
    avail = 0.0
    cats = 0
    for cat, items in weights.items():
        ce = 0.0
        ca = 0.0
        for name, wt in items:
            ca += wt
            if fac.get(name, False):
                ce += wt
        earned += ce
        avail += ca
        if ce >= 0.5 * ca:
            cats += 1
    r.factors = {k: float(bool(v)) for k, v in fac.items()}
    r.score = 100.0 * earned / avail if avail else 0.0
    r.categories = cats
    r.passed = r.score >= f.score_threshold and cats >= f.min_categories
    return r
