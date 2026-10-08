"""Option-chain snapshot model and derived analytics (PCR, OI walls, max pain, near-ATM flow).

A ChainHistory keeps recent snapshots so OI / PCR *trends* can be scored, not just levels.
"""
from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

@dataclass
class ChainSnapshot:
    ts: pd.Timestamp
    spot: float
    expiry: str                      # "13-Oct-2026"
    strikes: np.ndarray
    ce_oi: np.ndarray
    pe_oi: np.ndarray
    ce_chg_oi: np.ndarray
    pe_chg_oi: np.ndarray
    ce_vol: np.ndarray
    pe_vol: np.ndarray
    ce_iv: np.ndarray
    pe_iv: np.ndarray
    ce_ltp: np.ndarray
    pe_ltp: np.ndarray
    ce_bid: np.ndarray
    ce_ask: np.ndarray
    pe_bid: np.ndarray
    pe_ask: np.ndarray
    # derived
    atm: float = 0.0
    pcr_oi: float = 0.0
    pcr_vol: float = 0.0
    pcr_chg: float = 0.0             # change-in-OI ratio PE/CE (flow, not stock)
    atm_iv_ce: float = 0.0
    atm_iv_pe: float = 0.0
    max_pain: float = 0.0
    call_wall: float = 0.0           # strike with max CE OI at/above spot
    put_wall: float = 0.0            # strike with max PE OI at/below spot
    call_wall_pct: float = 0.0       # distance from spot (%)
    put_wall_pct: float = 0.0
    ce_chg_near: float = 0.0         # sum of CE change-in-OI, ATM +/- 2 strikes
    pe_chg_near: float = 0.0
    ce_chg_above: float = 0.0        # CE OI change in 1..3 strikes above ATM (resistance build/unwind)
    pe_chg_below: float = 0.0        # PE OI change in 1..3 strikes below ATM (support build/unwind)
    skew: float = 0.0                # OTM put IV - OTM call IV (fear gauge)
    extras: dict = field(default_factory=dict)

    def strike_idx(self, strike: float) -> int:
        return int(np.argmin(np.abs(self.strikes - strike)))

    def premium(self, strike: float, kind: str) -> tuple[float, float, float, float]:
        """Returns (ltp, bid, ask, iv) for the strike."""
        i = self.strike_idx(strike)
        if kind == "CE":
            return float(self.ce_ltp[i]), float(self.ce_bid[i]), float(self.ce_ask[i]), float(self.ce_iv[i])
        return float(self.pe_ltp[i]), float(self.pe_bid[i]), float(self.pe_ask[i]), float(self.pe_iv[i])


def derive(s: ChainSnapshot, strike_step: int = 50) -> None:
    n = s.strikes.size
    if n == 0:
        return
    s.atm = float(round(s.spot / strike_step) * strike_step)
    ia = s.strike_idx(s.atm)
    tot_ce, tot_pe = s.ce_oi.sum(), s.pe_oi.sum()
    s.pcr_oi = float(tot_pe / tot_ce) if tot_ce > 0 else 0.0
    vce, vpe = s.ce_vol.sum(), s.pe_vol.sum()
    s.pcr_vol = float(vpe / vce) if vce > 0 else 0.0
    cce, cpe = s.ce_chg_oi.sum(), s.pe_chg_oi.sum()
    s.pcr_chg = float(cpe / cce) if cce > 0 else (2.0 if cpe > 0 else 1.0)
    # ATM IV: fall back to nearest non-zero
    s.atm_iv_ce = _nearest_nonzero(s.ce_iv, ia)
    s.atm_iv_pe = _nearest_nonzero(s.pe_iv, ia)
    # max pain: strike minimising total payoff to option buyers
    pain = np.empty(n)
    for i in range(n):
        k = s.strikes[i]
        pain[i] = np.sum(s.ce_oi * np.maximum(s.strikes * 0 + k - s.strikes, 0)) + \
            np.sum(s.pe_oi * np.maximum(s.strikes - k, 0))
    s.max_pain = float(s.strikes[int(np.argmin(pain))])
    above = s.strikes >= s.spot
    below = s.strikes <= s.spot
    if above.any():
        j = int(np.argmax(np.where(above, s.ce_oi, -1)))
        s.call_wall = float(s.strikes[j])
        s.call_wall_pct = (s.call_wall - s.spot) / s.spot * 100.0
    if below.any():
        j = int(np.argmax(np.where(below, s.pe_oi, -1)))
        s.put_wall = float(s.strikes[j])
        s.put_wall_pct = (s.spot - s.put_wall) / s.spot * 100.0
    lo, hi = max(0, ia - 2), min(n, ia + 3)
    s.ce_chg_near = float(s.ce_chg_oi[lo:hi].sum())
    s.pe_chg_near = float(s.pe_chg_oi[lo:hi].sum())
    s.ce_chg_above = float(s.ce_chg_oi[ia + 1:min(n, ia + 4)].sum())
    s.pe_chg_below = float(s.pe_chg_oi[max(0, ia - 3):ia].sum())
    jp, jc = max(0, ia - 4), min(n - 1, ia + 4)
    s.skew = float(_nearest_nonzero(s.pe_iv, jp) - _nearest_nonzero(s.ce_iv, jc))


def _nearest_nonzero(a: np.ndarray, i: int) -> float:
    if a[i] > 0:
        return float(a[i])
    for d in range(1, 4):
        for j in (i - d, i + d):
            if 0 <= j < a.size and a[j] > 0:
                return float(a[j])
    return 0.0


class ChainHistory:
    """Rolling window of snapshots used for flow / trend features."""

    def __init__(self, maxlen: int = 24):
        self.buf: deque[ChainSnapshot] = deque(maxlen=maxlen)

    def push(self, s: ChainSnapshot) -> None:
        if self.buf and self.buf[-1].ts == s.ts:
            return
        self.buf.append(s)

    @property
    def last(self) -> ChainSnapshot | None:
        return self.buf[-1] if self.buf else None

    def pcr_trend(self, n: int = 3) -> float:
        """Slope sign of PCR(OI) over the last n snapshots (+1 rising, -1 falling, 0 flat/insufficient)."""
        if len(self.buf) < n + 1:
            return 0.0
        a = self.buf[-n - 1].pcr_oi
        b = self.buf[-1].pcr_oi
        if a == 0:
            return 0.0
        d = (b - a) / a
        return 1.0 if d > 0.02 else -1.0 if d < -0.02 else 0.0

    def oi_delta(self, n: int = 2) -> tuple[float, float]:
        """Net CE / PE OI change near ATM between now and n snapshots ago (intraday flow)."""
        if len(self.buf) < n + 1:
            return 0.0, 0.0
        a, b = self.buf[-n - 1], self.buf[-1]
        if a.strikes.size != b.strikes.size or not np.array_equal(a.strikes, b.strikes):
            return 0.0, 0.0
        ia = b.strike_idx(b.atm)
        lo, hi = max(0, ia - 2), min(b.strikes.size, ia + 3)
        return float((b.ce_oi - a.ce_oi)[lo:hi].sum()), float((b.pe_oi - a.pe_oi)[lo:hi].sum())
