"""Price-action strategy ("pa_short"): the setups that survived the 9-year NIFTY study.

Research (research/pa_study.py, research/pa_study2.py; results in docs/RESEARCH.md):
  * short-side setups aligned with the 15m trend carried a small positive expectancy after costs;
    the long-side mirrors did not (NIFTY's intraday drift is negative, its gains come overnight).
  * context that helped: 15m EMA20 < EMA50, ADX >= 25 for VWAP rejection, first 90 minutes for the
    prior-day-high sweep, ATR percentile 40-80 for VWAP reclaim and PDL break-and-hold.
  * exits: stop 1.0 ATR, target 3.0 ATR, time stop 24 bars (the 1:3 payoff carried the edge).

Setups (all require a bearish bar: close < open, close in the bottom 40% of the range):
  vwap_reject  : wick above session VWAP, close back below, after >= 3 closes below VWAP
  vwap_reclaim : first close below VWAP after >= 3 closes above
  pdh_sweep    : high takes out the prior-day high, close back below it (liquidity grab)
  pdl_break    : second consecutive close below the prior-day low (acceptance)
"""
from __future__ import annotations

import numpy as np

from ..config import Config
from ..data.chain import ChainHistory, ChainSnapshot
from .scorer import ScoreResult, common_vetoes

PA_REQUIRED = ["atr", "atr_pct", "adx", "vwap", "h_ema_f", "h_ema_s", "d_high", "d_low", "dte"]


def evaluate_pa(direction: int, w: dict, hist: list[dict], chain: ChainSnapshot | None,
                chist: ChainHistory | None, cfg: Config, bar_minutes: int) -> ScoreResult:
    r = ScoreResult(direction=direction)
    if direction > 0:                      # long side has no edge intraday on NIFTY
        r.vetoes.append("long_disabled")
        return r
    r.vetoes = common_vetoes(w, hist[-1] if hist else w, cfg, bar_minutes)
    if "warmup" in r.vetoes or len(hist) < 3:
        return r
    for k in PA_REQUIRED:
        v = w.get(k)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            r.vetoes.append("warmup")
            return r
    c, o, h, l = w["close"], w["open"], w["high"], w["low"]
    a = w["atr"]
    rng = max(h - l, 1e-9)
    bear = c < o and (h - c) / rng >= 0.6
    if not bear:
        r.vetoes.append("no_trigger")
        return r
    if not (w["h_ema_f"] < w["h_ema_s"]):
        r.vetoes.append("htf")
    minute = w["ts"].hour * 60 + w["ts"].minute
    vw = w["vwap"]
    prev3_above = all(x["close"] > x["vwap"] for x in hist[-3:])
    prev3_below = all(x["close"] < x["vwap"] for x in hist[-3:])
    trig = ""
    if h > vw > c and prev3_below and w["adx"] >= 25:
        trig = "vwap_reject"
    elif c < vw and prev3_above and 40 <= w["atr_pct"] <= 80:
        trig = "vwap_reclaim"
    elif h > w["d_high"] and c < w["d_high"] and hist[-1]["close"] < w["d_high"] and minute < 660:
        trig = "pdh_sweep"
    elif c < w["d_low"] and hist[-1]["close"] < w["d_low"] and hist[-2]["close"] >= w["d_low"] and 40 <= w["atr_pct"] <= 80:
        trig = "pdl_break"
    if not trig:
        r.vetoes.append("no_trigger")
    elif cfg.filt.pa_triggers and trig not in cfg.filt.pa_triggers.replace(" ", "").split(","):
        r.vetoes.append("trigger_off")
    r.trigger = trig
    if chain is not None:
        f = cfg.filt
        if not (f.pcr_hard_min <= chain.pcr_oi <= f.pcr_hard_max):
            r.vetoes.append("pcr_extreme")
        if chain.atm_iv_pe > f.iv_cap:
            r.vetoes.append("iv")
        if 0 < chain.put_wall_pct < f.wall_veto_pct:
            r.vetoes.append("wall")
    if r.vetoes:
        return r
    r.score = 100.0
    r.categories = 4
    r.passed = True
    r.factors = {trig: 1.0}
    return r
