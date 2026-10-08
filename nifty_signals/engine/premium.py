"""Premium-selling engine: weekly NIFTY iron fly with defined risk.

Structure (one per session, opened at `sell.entry_time`):
    SELL ATM CE + SELL ATM PE (straddle)  +  BUY CE at ATM + wing_pts  +  BUY PE at ATM - wing_pts
Entry filters (the regime / price-action work is used to decide when NOT to sell):
    * trading days to expiry inside [dte_min, dte_max]; not an event date
    * no large gap at the open, no large move already made since the open
    * VIX inside [vix_min, vix_max] and not spiking versus its 20-day mean
    * 15m ADX below adx_max (no strong trend day in progress)
    * live only: chain PCR not extreme (crowded one-sided positioning)
Exits (checked every bar on the structure's mark-to-market value, i.e. the cost to close it):
    * TP    value <= credit * (1 - tp_frac)
    * SL    value >= credit * (1 + sl_mult) at the bar's spot extremes (conservative)
    * TIME  bar closing at/after exit_time (expiry_exit_time on expiry day) or square-off
Simulation prices every leg with Black-Scholes at IV = VIX x iv_mult (wings get +wing_iv_add vol
points for skew); live mode prices from the option chain. Costs: `sell.cost_pts` per round trip.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ..config import Config
from ..data.chain import ChainHistory, ChainSnapshot
from .calendar import ExpiryCalendar, years_to_expiry
from .options import bs, implied_vol
from .scorer import ScoreResult
from .signals import BarEngine, Signal


@dataclass
class Leg:
    kind: str           # CE | PE
    strike: float
    side: str           # SELL | BUY
    iv: float = 0.0
    entry: float = 0.0  # premium at entry

    @property
    def sign(self) -> int:
        return 1 if self.side == "SELL" else -1   # contribution to the structure's close-out value


@dataclass
class Structure:
    legs: list[Leg]
    atm: float
    expiry: str
    entry_ts: pd.Timestamp
    entry_spot: float
    credit: float
    tp_value: float
    sl_value: float
    lots: int = 0
    bars: int = 0
    session: int = 0
    dte: float = 0.0
    vix: float = 0.0


@dataclass
class PremiumState:
    pos: Structure | None = None
    session: int = -1
    last_i: int = -1
    opened_today: int = 0
    cooldown_until: int = -1
    sl_today: bool = False
    trades: list[dict] = field(default_factory=list)
    last_veto: str = ""


class PremiumEngine(BarEngine):
    def __init__(self, cfg: Config, bar_minutes: int = 5, iv_mult: float = 1.05, cal: ExpiryCalendar | None = None):
        super().__init__(cfg, bar_minutes, iv_mult, cal)
        self.state = PremiumState()
        self._events = set(cfg.sell.event_dates)

    # ------------------------------------------------------------------ pricing
    def _leg_price(self, w: dict, chain: ChainSnapshot | None, leg: Leg, t_years: float, spot: float | None = None,
                   use_chain: bool = True) -> float:
        """Premium of one leg at `spot` (bar close when None). Chain mid/LTP when available, else BS."""
        s = w["close"] if spot is None else spot
        if chain is not None and use_chain and spot is None:
            ltp, bid, ask, iv = chain.premium(leg.strike, leg.kind)
            px = 0.5 * (bid + ask) if (bid > 0 and ask > 0 and (ask - bid) / ask < 0.1) else ltp
            if px > 0:
                return px
        return bs(s, leg.strike, t_years, leg.iv, leg.kind).price

    def _value(self, w: dict, chain: ChainSnapshot | None, pos: Structure, t_years: float, spot: float | None = None,
               use_chain: bool = True) -> float:
        """Cost to close the structure (positive = debit): short legs bought back minus long legs sold."""
        return sum(l.sign * self._leg_price(w, chain, l, t_years, spot, use_chain) for l in pos.legs)

    def _iv_for_leg(self, w: dict, chain: ChainSnapshot | None, leg: Leg, t_years: float) -> float:
        vix = w.get("vix")
        base = (vix if vix is not None and not np.isnan(vix) else 14.0) * self.iv_mult
        if chain is not None:
            ltp, bid, ask, iv = chain.premium(leg.strike, leg.kind)
            px = 0.5 * (bid + ask) if (bid > 0 and ask > 0) else ltp
            if px > 0:
                solved = implied_vol(px, w["close"], leg.strike, t_years, leg.kind)
                if solved > 0:
                    return solved
            if iv > 0:
                return iv
        return base + (self.cfg.sell.wing_iv_add if leg.side == "BUY" else 0.0)

    # ------------------------------------------------------------------ filters
    def evaluate_entry(self, w: dict, hist: list[dict], chain: ChainSnapshot | None) -> ScoreResult:
        r = ScoreResult(direction=0)
        sc = self.cfg.sell
        f = self.cfg.filt
        for k in ("atr", "vix", "dte", "h_adx", "d_close", "sess_open"):
            v = w.get(k)
            if v is None or (isinstance(v, float) and np.isnan(v)):
                r.vetoes.append("warmup")
                return r
        day = w["ts"].strftime("%Y-%m-%d")
        if day in self._events:
            r.vetoes.append("event_day")
        if not (sc.dte_min <= w["dte"] <= sc.dte_max):
            r.vetoes.append("dte")
        gap = abs(w["sess_open"] / w["d_close"] - 1.0) * 100.0
        if gap > sc.gap_max_pct:
            r.vetoes.append("gap")
        moved = abs(w["close"] / w["sess_open"] - 1.0) * 100.0
        if moved > sc.open_move_max_pct:
            r.vetoes.append("open_move")
        if not (sc.vix_min <= w["vix"] <= sc.vix_max):
            r.vetoes.append("vix")
        vma = w.get("vix_ma")
        if vma is not None and not np.isnan(vma) and vma > 0 and w["vix"] / vma > sc.vix_spike_ratio:
            r.vetoes.append("vix_spike")
        if w["h_adx"] > sc.adx_max:
            r.vetoes.append("trend")
        if chain is not None:
            if not (f.pcr_hard_min <= chain.pcr_oi <= f.pcr_hard_max):
                r.vetoes.append("pcr_extreme")
        r.trigger = "iron_fly"
        if not r.vetoes:
            r.passed = True
            r.score = 100.0
            r.categories = 4
        return r

    def status(self, w: dict, hist: list[dict], chain: ChainSnapshot | None) -> str:
        pos = self.state.pos
        if pos is not None:
            t_years = years_to_expiry(w["dte"])
            v = self._value(w, chain, pos, t_years)
            return (f"OPEN FLY {int(pos.atm)} credit {pos.credit:.0f} value {v:.0f} "
                    f"({(pos.credit - v) / pos.credit * 100:+.0f}%) tp {pos.tp_value:.0f} sl {pos.sl_value:.0f} bars {pos.bars}")
        r = self.evaluate_entry(w, hist, chain)
        if r.vetoes:
            return f"FLY: no [{','.join(r.vetoes[:4])}]"
        sc = self.cfg.sell
        close_t = (w["ts"] + timedelta(minutes=self.bar_minutes)).time()
        if self.state.opened_today >= sc.max_structures_per_day:
            return "FLY: done for today"
        last = sc.expiry_last_entry_time if w["dte"] < 1.0 else sc.last_entry_time
        if not (sc.entry_time <= close_t <= last):
            return f"FLY: filters pass, outside entry window ({sc.entry_time.strftime('%H:%M')}-{last.strftime('%H:%M')})"
        return "FLY: filters pass"

    # ------------------------------------------------------------------ core
    def on_bar(self, feats: pd.DataFrame, i: int, chain: ChainSnapshot | None = None,
               chist: ChainHistory | None = None, expiry_label: str | None = None) -> list[Signal]:
        st = self.state
        if i <= st.last_i:
            return []
        st.last_i = i
        w = self._row(feats, i)
        out: list[Signal] = []
        if w["session"] != st.session:
            st.session = w["session"]
            st.opened_today = 0
            st.sl_today = False
            st.cooldown_until = -1
        sc = self.cfg.sell
        ses = self.cfg.session
        close_t = (w["ts"] + timedelta(minutes=self.bar_minutes)).time()
        t_years = years_to_expiry(w["dte"])
        expiry_day = w["dte"] < 1.0

        # ---------------------------------------------------------- manage the open structure
        if st.pos is not None:
            pos = st.pos
            pos.bars += 1
            reason = ""
            # stop at the bar's extremes (conservative: assumes the worst print was tradeable)
            v_hi = self._value(w, chain, pos, t_years, spot=w["high"], use_chain=False)
            v_lo = self._value(w, chain, pos, t_years, spot=w["low"], use_chain=False)
            v_close = self._value(w, chain, pos, t_years)
            worst = max(v_hi, v_lo, v_close)
            if worst >= pos.sl_value:
                reason, value = "SL", max(pos.sl_value, v_close) if chain is not None else pos.sl_value
            elif v_close <= pos.tp_value:
                reason, value = "TP", v_close
            elif close_t >= ses.square_off:
                reason, value = "SQOFF", v_close
            elif close_t >= (sc.expiry_exit_time if expiry_day else sc.exit_time):
                reason, value = "TIME", v_close
            if reason:
                pnl_pts = pos.credit - value - sc.cost_pts
                sig = Signal(w["ts"], "EXIT", "FLY", pos.atm, pos.expiry, value, w["close"], reason=reason,
                             lots=pos.lots, structure="IRON FLY",
                             legs=[{"kind": l.kind, "strike": l.strike, "side": "BUY" if l.side == "SELL" else "SELL",
                                    "premium": self._leg_price(w, chain, l, t_years)} for l in pos.legs])
                sig.pnl_pct = pnl_pts / pos.credit * 100.0
                out.append(sig)
                st.trades.append({
                    "entry_ts": pos.entry_ts, "exit_ts": w["ts"], "kind": "FLY", "strike": pos.atm,
                    "entry_prem": pos.credit, "exit_prem": value, "pnl_pts": pnl_pts, "pnl_pct": sig.pnl_pct,
                    "reason": reason, "bars": pos.bars, "t1_hit": False, "lots": pos.lots,
                    "entry_spot": pos.entry_spot, "exit_spot": w["close"], "trigger": "iron_fly", "score": 100.0,
                    "dte": pos.dte, "vix": pos.vix,
                })
                st.pos = None
                st.cooldown_until = i + sc.reentry_cooldown_bars
                if reason == "SL":
                    st.sl_today = True
            return out

        # ---------------------------------------------------------- look for an entry
        if st.opened_today >= sc.max_structures_per_day or i < st.cooldown_until:
            return out
        if st.sl_today and not sc.reentry_after_sl:
            return out
        last = sc.expiry_last_entry_time if expiry_day else sc.last_entry_time
        if not (sc.entry_time <= close_t <= last):
            return out
        r = self.evaluate_entry(w, hist=self._records(feats)[max(0, i - 6):i], chain=chain)
        st.last_veto = ",".join(r.vetoes)
        if not r.passed:
            return out
        step = self.cfg.opt.strike_step
        atm = float(round(w["close"] / step) * step)
        legs = [Leg("CE", atm, "SELL"), Leg("PE", atm, "SELL"),
                Leg("CE", atm + sc.wing_pts, "BUY"), Leg("PE", atm - sc.wing_pts, "BUY")]
        for l in legs:
            l.iv = self._iv_for_leg(w, chain, l, t_years)
            l.entry = self._leg_price(w, chain, l, t_years)
        credit = sum(l.sign * l.entry for l in legs)
        if credit <= 0:
            return out
        lots = 0
        oc = self.cfg.opt
        if oc.capital > 0:
            lots = max(1, int(oc.capital // max(sc.margin_per_lot, 1.0)))
        expiry = self._expiry_str(w, expiry_label)
        pos = Structure(legs, atm, expiry, w["ts"], w["close"], credit,
                        tp_value=credit * (1.0 - sc.tp_frac), sl_value=credit * (1.0 + sc.sl_mult),
                        lots=lots, session=int(w["session"]), dte=float(w["dte"]), vix=float(w["vix"]))
        st.pos = pos
        st.opened_today += 1
        sig = Signal(w["ts"], "SELL", "FLY", atm, expiry, credit, w["close"], t1_prem=pos.tp_value, t2_prem=pos.sl_value,
                     score=100.0, lots=lots, structure="IRON FLY",
                     legs=[{"kind": l.kind, "strike": l.strike, "side": l.side, "premium": l.entry} for l in legs],
                     detail=f"dte {w['dte']:.1f} vix {w['vix']:.1f} adx15 {w['h_adx']:.0f}")
        out.append(sig)
        return out
