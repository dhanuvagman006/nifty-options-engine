"""Signal engine: a deterministic state machine that turns scored setups into BUY / EXIT alerts.

Rules
  * one open position at a time, max N entries per session
  * entry only on a bar whose setup passes the scorer
  * stop = max(sl_min_atr, min(sl_atr * ATR, distance to last swing)) below/above entry (spot terms)
  * T1 = t1_r * risk, T2 = t2_r * risk; after T1 the stop moves to breakeven and trails
    the supertrend / mid EMA (whichever is tighter); T2 is a full exit
  * time stop if T1 not reached within `time_stop_bars`
  * forced exit at square-off time, on supertrend flip against the trade, or on an opposite setup
  * cooldown after any exit (longer after a stop-out)
Option premiums are translated from spot levels with Black-Scholes so the alert carries both.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from ..config import Config
from ..data.chain import ChainHistory, ChainSnapshot
from .calendar import ExpiryCalendar, years_to_expiry
from .options import bs, implied_vol, select_strike
from .pa_scorer import evaluate_pa
from .scorer import ScoreResult, evaluate as evaluate_confluence


@dataclass
class Signal:
    ts: pd.Timestamp
    action: str                 # BUY | SELL (open a short structure) | EXIT
    kind: str                   # CE | PE | FLY (multi-leg structure)
    strike: float
    expiry: str
    premium: float
    spot: float
    sl_prem: float = 0.0
    t1_prem: float = 0.0
    t2_prem: float = 0.0
    sl_spot: float = 0.0
    t1_spot: float = 0.0
    t2_spot: float = 0.0
    score: float = 0.0
    reason: str = ""            # for EXIT: SL / T1 / T2 / TRAIL / TIME / SQOFF / FLIP / REVERSE
    pnl_pct: float = 0.0
    lots: int = 0
    detail: str = ""
    legs: list = field(default_factory=list)   # multi-leg: [{"kind","strike","side","premium"}, ...]
    structure: str = ""                        # e.g. "IRON FLY"

    def line(self, verbose: bool = False) -> str:
        t = self.ts.strftime("%d-%b %H:%M")
        k = int(self.strike)
        if self.legs:
            s = self._structure_line(t)
        elif self.action == "BUY":
            lots = f"  x{self.lots} lot" if self.lots else ""
            s = (f"{t}  BUY  NIFTY {k} {self.kind}  @{self.premium:.1f}  SL {self.sl_prem:.0f}  "
                 f"T1 {self.t1_prem:.0f}  T2 {self.t2_prem:.0f}{lots}  | spot {self.spot:.0f} "
                 f"SL {self.sl_spot:.0f} T1 {self.t1_spot:.0f} T2 {self.t2_spot:.0f} | exp {self.expiry}")
        else:
            s = (f"{t}  EXIT NIFTY {k} {self.kind}  @{self.premium:.1f}  {self.reason}  "
                 f"{self.pnl_pct:+.0f}%  | spot {self.spot:.0f}")
        if verbose and self.detail:
            s += f"\n           {self.detail}"
        return s

    def _structure_line(self, t: str) -> str:
        longs = [l for l in self.legs if l["side"] == "BUY"]
        wings = "/".join(str(int(l["strike"])) for l in sorted(longs, key=lambda x: x["strike"]))
        k = int(self.strike)
        if self.action == "SELL":
            lots = f"  x{self.lots} lot" if self.lots else ""
            legs = " ".join(f"{l['side'][0]}{int(l['strike'])}{l['kind']}@{l['premium']:.1f}" for l in self.legs)
            return (f"{t}  SELL {self.structure} NIFTY {k}  wings {wings}  credit {self.premium:.1f}  "
                    f"TP {self.t1_prem:.0f}  SL {self.t2_prem:.0f}{lots}  | spot {self.spot:.0f} | exp {self.expiry}\n"
                    f"           legs {legs}")
        return (f"{t}  EXIT {self.structure} NIFTY {k}  @{self.premium:.1f}  {self.reason}  "
                f"{self.pnl_pct:+.0f}% of credit  | spot {self.spot:.0f}")

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["ts"] = self.ts.isoformat()
        return d


@dataclass
class Position:
    kind: str
    direction: int
    strike: float
    expiry: str
    entry_ts: pd.Timestamp
    entry_spot: float
    entry_prem: float
    iv: float
    t_years: float
    sl_spot: float
    t1_spot: float
    t2_spot: float
    risk: float
    bars: int = 0
    t1_hit: bool = False
    t1_prem: float = 0.0
    trail: float = 0.0
    lots: int = 0
    session: int = 0
    trigger: str = ""
    score: float = 0.0


@dataclass
class EngineState:
    pos: Position | None = None
    cooldown_until: int = -1        # bar index
    signals_today: int = 0
    session: int = -1
    last_i: int = -1
    trades: list[dict] = field(default_factory=list)


class BarEngine:
    """Shared plumbing for bar-driven engines: cached row dicts, premium lookup, expiry labels."""

    def __init__(self, cfg: Config, bar_minutes: int = 5, iv_mult: float = 1.05, cal: ExpiryCalendar | None = None):
        self.cfg = cfg
        self.bar_minutes = bar_minutes
        self.iv_mult = iv_mult
        self.cal = cal or ExpiryCalendar(cfg.session)
        self.state = EngineState()
        self._rows_key: tuple | None = None
        self._rows: list[dict] = []

    def on_bar(self, feats: pd.DataFrame, i: int, chain: ChainSnapshot | None = None,
               chist: ChainHistory | None = None, expiry_label: str | None = None) -> list[Signal]:
        raise NotImplementedError

    def status(self, w: dict, hist: list[dict], chain: ChainSnapshot | None) -> str:
        """Per-bar state for the heartbeat / status command."""
        return ""

    # ------------------------------------------------------------------ helpers
    def _records(self, feats: pd.DataFrame) -> list[dict]:
        """Row dicts for the frame, converted once per frame (cached by identity + shape + last stamp)."""
        key = (id(feats), len(feats), feats.index[-1] if len(feats) else None)
        if key != self._rows_key:
            recs = feats.to_dict("records")
            for r, ts in zip(recs, feats.index):
                r["ts"] = ts
            self._rows = recs
            self._rows_key = key
        return self._rows

    def _row(self, feats: pd.DataFrame, i: int) -> dict:
        return self._records(feats)[i]

    def _iv_for(self, w: dict, chain: ChainSnapshot | None, kind: str, strike: float, t_years: float) -> tuple[float, float]:
        """(premium, iv) at the current bar close."""
        if chain is not None:
            ltp, bid, ask, iv = chain.premium(strike, kind)
            if ask > 0 and bid > 0 and (ask - bid) / ask < 0.08:
                px = 0.5 * (bid + ask)
            else:
                px = ltp
            if px > 0:
                iv_eff = implied_vol(px, w["close"], strike, t_years, kind) or iv
                return px, iv_eff if iv_eff > 0 else max(iv, 10.0)
        vix = w.get("vix")
        iv = (vix if vix is not None and not np.isnan(vix) else 14.0) * self.iv_mult
        return bs(w["close"], strike, t_years, iv, kind).price, iv

    def _prem_at(self, spot: float, pos: Position, t_years: float | None = None) -> float:
        return bs(spot, pos.strike, pos.t_years if t_years is None else t_years, pos.iv, pos.kind).price

    def _expiry_str(self, w: dict, cal_expiry: str | None) -> str:
        if cal_expiry:
            try:
                return datetime.strptime(cal_expiry, "%d-%b-%Y").strftime("%d-%b")
            except ValueError:
                return cal_expiry
        return self.cal.next_expiry(w["ts"].date()).strftime("%d-%b")



class SignalEngine(BarEngine):
    """Directional option buying driven by the price-action or confluence scorer."""

    def __init__(self, cfg: Config, bar_minutes: int = 5, iv_mult: float = 1.05, cal: ExpiryCalendar | None = None):
        super().__init__(cfg, bar_minutes, iv_mult, cal)
        self.evaluate = evaluate_pa if cfg.filt.strategy == "pa_short" else evaluate_confluence
        f = cfg.filt
        self._pa_window = None
        if cfg.filt.strategy == "pa_short":
            h1, m1 = (int(x) for x in f.pa_entry_start.split(":")[:2])
            h2, m2 = (int(x) for x in f.pa_entry_end.split(":")[:2])
            self._pa_window = (h1 * 60 + m1, h2 * 60 + m2)

    def status(self, w: dict, hist: list[dict], chain: ChainSnapshot | None) -> str:
        pos = self.state.pos
        if pos is not None:
            return f"OPEN {int(pos.strike)} {pos.kind} sl {pos.sl_spot:.0f} t1 {pos.t1_spot:.0f} t2 {pos.t2_spot:.0f} bars {pos.bars}"
        parts = []
        for d, name in ((1, "CE"), (-1, "PE")):
            r = self.evaluate(d, w, hist, chain, None, self.cfg, self.bar_minutes)
            if r.vetoes:
                parts.append(f"{name}: no [{','.join(r.vetoes[:3])}]")
            else:
                parts.append(f"{name}: score {r.score:.0f}/{self.cfg.filt.score_threshold:.0f} cats {r.categories} {r.trigger}")
        return " | ".join(parts)

    # ------------------------------------------------------------------ core
    def on_bar(self, feats: pd.DataFrame, i: int, chain: ChainSnapshot | None = None,
               chist: ChainHistory | None = None, expiry_label: str | None = None) -> list[Signal]:
        """Process bar i (must be a completed bar). Returns zero or more signals."""
        st = self.state
        if i <= st.last_i:
            return []
        st.last_i = i
        w = self._row(feats, i)
        out: list[Signal] = []
        if w["session"] != st.session:
            st.session = w["session"]
            st.signals_today = 0
        recs = self._records(feats)
        hist = recs[max(0, i - 6):i]
        f = self.cfg.filt
        s = self.cfg.session
        close_t = (w["ts"] + timedelta(minutes=self.bar_minutes)).time()

        # ---------------------------------------------------------- manage open position
        if st.pos is not None:
            pos = st.pos
            pos.bars += 1
            d = pos.direction
            hi, lo, c = w["high"], w["low"], w["close"]
            t_years = years_to_expiry(w["dte"])
            exit_reason = ""
            exit_spot = c
            # stop first (conservative when both touched in one bar)
            if (d > 0 and lo <= pos.sl_spot) or (d < 0 and hi >= pos.sl_spot):
                exit_reason = "SL" if not pos.t1_hit else "TRAIL"
                exit_spot = pos.sl_spot
            elif (d > 0 and hi >= pos.t2_spot) or (d < 0 and lo <= pos.t2_spot):
                exit_reason = "T2"
                exit_spot = pos.t2_spot
            else:
                if not pos.t1_hit and ((d > 0 and hi >= pos.t1_spot) or (d < 0 and lo <= pos.t1_spot)):
                    pos.t1_hit = True
                    if f.breakeven_after_t1:
                        pos.sl_spot = pos.entry_spot
                    t1 = Signal(w["ts"], "EXIT", pos.kind, pos.strike, pos.expiry,
                                self._prem_at(pos.t1_spot, pos, t_years), pos.t1_spot, reason="T1 HIT (book half, SL->entry)")
                    t1.pnl_pct = (t1.premium / pos.entry_prem - 1) * 100
                    pos.t1_prem = t1.premium
                    out.append(t1)
                if pos.t1_hit and f.trail_after_t1:
                    trail = max(w["st_line"], w["ema_m"]) if d > 0 else min(w["st_line"], w["ema_m"])
                    if not np.isnan(trail):
                        pos.sl_spot = max(pos.sl_spot, trail) if d > 0 else min(pos.sl_spot, trail)
                if f.exit_on_flip and w["st_dir"] == -d:
                    exit_reason = "FLIP"
                elif not pos.t1_hit and pos.bars >= f.time_stop_bars:
                    exit_reason = "TIME"
                elif close_t >= s.square_off:
                    exit_reason = "SQOFF"
                elif pos.t1_hit and ((d > 0 and c < pos.sl_spot) or (d < 0 and c > pos.sl_spot)):
                    exit_reason = "TRAIL"
            if not exit_reason:
                opp = self.evaluate(-d, w, hist, chain, chist, self.cfg, self.bar_minutes)
                if opp.passed:
                    exit_reason = "REVERSE"
            if exit_reason:
                prem = self._prem_at(exit_spot, pos, t_years)
                if chain is not None and exit_reason in ("TIME", "SQOFF", "FLIP", "REVERSE", "TRAIL"):
                    ltp = chain.premium(pos.strike, pos.kind)[0]
                    if ltp > 0:
                        prem = ltp
                sig = Signal(w["ts"], "EXIT", pos.kind, pos.strike, pos.expiry, prem, exit_spot, reason=exit_reason)
                sig.pnl_pct = (prem / pos.entry_prem - 1) * 100
                out.append(sig)
                # blended exit: half booked at T1 when it was hit
                blended = 0.5 * (pos.t1_prem + prem) if pos.t1_hit else prem
                st.trades.append({
                    "entry_ts": pos.entry_ts, "exit_ts": w["ts"], "kind": pos.kind, "strike": pos.strike,
                    "entry_prem": pos.entry_prem, "exit_prem": blended, "pnl_pct": (blended / pos.entry_prem - 1) * 100,
                    "reason": exit_reason, "bars": pos.bars, "t1_hit": pos.t1_hit, "lots": pos.lots,
                    "entry_spot": pos.entry_spot, "exit_spot": exit_spot, "trigger": pos.trigger, "score": pos.score,
                })
                st.pos = None
                st.cooldown_until = i + (f.cooldown_after_sl if exit_reason == "SL" else f.cooldown_bars)
                if exit_reason != "REVERSE":
                    return out
            else:
                return out

        # ---------------------------------------------------------- look for an entry
        if i < st.cooldown_until or st.signals_today >= f.max_signals_per_day:
            return out
        if close_t >= s.square_off:
            return out
        if self._pa_window is not None:
            cm = close_t.hour * 60 + close_t.minute
            if not (self._pa_window[0] <= cm <= self._pa_window[1]):
                return out
        if not (f.buy_dte_min <= w["dte"] <= f.buy_dte_max):
            return out
        best: ScoreResult | None = None
        for d in (1, -1):
            r = self.evaluate(d, w, hist, chain, chist, self.cfg, self.bar_minutes)
            if r.passed and (best is None or r.score > best.score):
                best = r
        if best is None:
            return out
        d = best.direction
        kind = "CE" if d > 0 else "PE"
        oc = self.cfg.opt
        itm = 1 if (oc.itm_on_expiry and w["dte"] <= 1.0) else oc.itm_strikes
        strike = select_strike(w["close"], kind, oc.strike_step, itm)
        t_years = years_to_expiry(w["dte"])
        prem, iv = self._iv_for(w, chain, kind, strike, t_years)
        if not (oc.min_premium <= prem <= oc.max_premium):
            return out
        c = w["close"]
        atr = w["atr"]
        risk = f.sl_atr * atr
        swing = w["sw_l"] if d > 0 else w["sw_h"]
        if not np.isnan(swing):
            dist = (c - swing) if d > 0 else (swing - c)
            if 0 < dist < risk:
                risk = max(dist, f.sl_min_atr * atr)
        sl_spot = c - d * risk
        t1_spot = c + d * f.t1_r * risk
        t2_spot = c + d * f.t2_r * risk
        pos = Position(kind, d, strike, self._expiry_str(w, expiry_label), w["ts"], c, prem, iv, t_years,
                       sl_spot, t1_spot, t2_spot, risk, session=int(w["session"]))
        sl_p = bs(sl_spot, strike, t_years, iv, kind).price
        t1_p = bs(t1_spot, strike, t_years, iv, kind).price
        t2_p = bs(t2_spot, strike, t_years, iv, kind).price
        lots = 0
        if oc.capital > 0:
            per_lot = max(prem - sl_p, 1.0) * oc.lot_size
            lots = max(1, int(oc.capital * oc.risk_per_trade_pct / 100.0 // per_lot))
        pos.lots = lots
        pos.trigger = best.trigger
        pos.score = best.score
        st.pos = pos
        st.signals_today += 1
        sig = Signal(w["ts"], "BUY", kind, strike, pos.expiry, prem, c, sl_p, t1_p, t2_p,
                     sl_spot, t1_spot, t2_spot, best.score, best.trigger, lots=lots, detail=best.summary())
        out.append(sig)
        return out


def make_engine(cfg: Config, bar_minutes: int = 5, cal: ExpiryCalendar | None = None, iv_mult: float = 1.05) -> BarEngine:
    """Engine for cfg.filt.strategy: "iron_fly" (premium selling) or the directional buyers."""
    if cfg.filt.strategy == "iron_fly":
        from .premium import PremiumEngine

        return PremiumEngine(cfg, bar_minutes, iv_mult, cal)
    return SignalEngine(cfg, bar_minutes, iv_mult, cal)
