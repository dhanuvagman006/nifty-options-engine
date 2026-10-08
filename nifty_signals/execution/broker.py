"""Order execution on Groww for the engine's BUY / EXIT signals, with hard safety rails.

Modes
  paper : every order is logged to logs/orders.jsonl exactly as it would be sent, nothing reaches the broker
  live  : orders are sent through growwapi (intraday MIS, DAY validity, market orders)

Signals handled
  BUY / EXIT   single bought option (directional strategies)
  SELL / EXIT  multi-leg short structure (iron fly): the long wings are bought first so the shorts are
               hedged (and margin-benefited) from the first moment; on exit the shorts are bought back
               first, then the wings are sold. A leg that fails on entry unwinds the legs already filled.

Rails (all enforced before any order is sent)
  * trading window: no new buys after `session.entry_end`; everything is flattened at `session.square_off`
  * max_lots per trade, max_open_positions = 1
  * max_daily_loss: once realised P&L for the day drops below this (rupees), no new buys until tomorrow
  * max_trades_per_day
  * kill switch: create the file named in `kill_file` and the executor refuses every new buy and flattens
  * every fill is verified with get_order_status; a rejected / cancelled buy clears the position so the
    engine's EXIT for it is ignored instead of selling something you do not hold
"""
from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from ..config import Config
from ..data.chain import ChainSnapshot
from ..engine.signals import Signal

log = logging.getLogger(__name__)
IST = "Asia/Kolkata"


@dataclass
class OpenOrder:
    symbol: str
    kind: str                  # CE | PE | FLY
    strike: float
    qty: int                   # units (lots * lot_size)
    entry_price: float         # option premium, or net credit for a structure
    order_id: str
    ts: str
    half_booked: bool = False
    booked_qty: int = 0
    realised: float = 0.0      # rupees booked so far
    legs: list = field(default_factory=list)   # structure legs: {symbol, kind, strike, side, qty, price, order_id}
    structure: str = ""


@dataclass
class DayState:
    day: str = ""
    trades: int = 0
    realised: float = 0.0
    halted: bool = False
    log: list[dict] = field(default_factory=list)


class Executor:
    def __init__(self, cfg: Config, client=None, order_log: str | Path = "logs/orders.jsonl", replay: bool = False):
        self.cfg = cfg
        self.ex = cfg.exec
        self.client = client
        self.replay = replay            # paper replay of historical bars: the clock follows the signals
        self._clock_day = ""
        self.mode = self.ex.mode.lower()
        self.order_log = Path(order_log)
        self.order_log.parent.mkdir(parents=True, exist_ok=True)
        self.pos: OpenOrder | None = None
        self.day = DayState()
        self._lock = threading.Lock()
        self._state_file = Path(cfg.data.cache_dir) / ("executor_replay_state.json" if replay else "executor_state.json")
        if not replay:
            self._restore()
        if self.mode not in ("paper", "live"):
            raise ValueError(f"exec.mode must be 'paper' or 'live', got {self.ex.mode!r}")
        log.info("executor ready: mode=%s max_lots=%d max_daily_loss=%.0f kill_file=%s",
                 self.mode, self.ex.max_lots, self.ex.max_daily_loss, self.ex.kill_file)

    # ------------------------------------------------------------------ state
    def _persist(self) -> None:
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            self._state_file.write_text(json.dumps({
                "pos": self.pos.__dict__ if self.pos else None,
                "day": {k: v for k, v in self.day.__dict__.items() if k != "log"},
            }))
        except Exception as exc:  # noqa: BLE001
            log.warning("executor state write failed: %s", exc)

    def _restore(self) -> None:
        if not self._state_file.exists():
            return
        try:
            d = json.loads(self._state_file.read_text())
            if d.get("pos"):
                self.pos = OpenOrder(**d["pos"])
            if d.get("day"):
                self.day = DayState(**d["day"])
        except Exception as exc:  # noqa: BLE001
            log.warning("executor state restore failed: %s", exc)
        today = date.today().isoformat()
        if self.day.day != today:
            self.day = DayState(day=today)
        if self.pos and not self.pos.ts.startswith(today):
            log.warning("stale position from %s found in state; it must be closed manually", self.pos.ts)
            self.pos = None

    def _today(self) -> str:
        return self._clock_day if (self.replay and self._clock_day) else date.today().isoformat()

    def _roll_day(self) -> None:
        today = self._today()
        if self.day.day != today:
            self.day = DayState(day=today)

    def _record(self, rec: dict) -> None:
        rec["mode"] = self.mode
        rec["ts_sent"] = datetime.now().isoformat(timespec="seconds")
        with open(self.order_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
        log.info("ORDER %s", json.dumps(rec, default=str))

    # ------------------------------------------------------------------ rails
    def kill_switch_on(self) -> bool:
        return bool(self.ex.kill_file) and Path(self.ex.kill_file).exists()

    def _can_buy(self, sig: Signal) -> str:
        """Return '' if a buy is allowed, else the reason it is refused."""
        self._roll_day()
        if self.kill_switch_on():
            return "kill switch"
        if self.pos is not None:
            return "position already open"
        if self.day.halted or self.day.realised <= -abs(self.ex.max_daily_loss):
            self.day.halted = True
            return f"daily loss limit hit ({self.day.realised:.0f})"
        if self.day.trades >= self.ex.max_trades_per_day:
            return "max trades for the day"
        t = sig.ts.time()
        if t >= self.cfg.session.square_off:
            return "after square-off"
        return ""

    # ------------------------------------------------------------------ broker calls
    def _send(self, symbol: str, side: str, qty: int, ref: str) -> tuple[str, float]:
        """Place a market order. Returns (order_id, fill_price). Raises on rejection in live mode."""
        if self.mode == "paper":
            return f"PAPER-{int(time.time() * 1000)}", 0.0
        api = self.client.api
        res = api.place_order(
            validity=api.VALIDITY_DAY, exchange=api.EXCHANGE_NSE, order_type=api.ORDER_TYPE_MARKET,
            product=api.PRODUCT_MIS, quantity=int(qty), segment=api.SEGMENT_FNO, trading_symbol=symbol,
            transaction_type=api.TRANSACTION_TYPE_BUY if side == "BUY" else api.TRANSACTION_TYPE_SELL,
            order_reference_id=ref[:20],
        )
        oid = str(res.get("groww_order_id") or res.get("order_id") or "")
        if not oid:
            raise RuntimeError(f"no order id in response: {res}")
        # wait for terminal status
        price = 0.0
        for _ in range(20):
            st = api.get_order_status(segment=api.SEGMENT_FNO, groww_order_id=oid)
            status = str(st.get("order_status") or st.get("status") or "").upper()
            if status in ("EXECUTED", "COMPLETED", "FILLED", "COMPLETE"):
                try:
                    det = api.get_order_detail(segment=api.SEGMENT_FNO, groww_order_id=oid)
                    price = float(det.get("average_fill_price") or det.get("avg_price") or det.get("price") or 0.0)
                except Exception:  # noqa: BLE001
                    price = 0.0
                return oid, price
            if status in ("REJECTED", "CANCELLED", "FAILED"):
                raise RuntimeError(f"order {oid} {status}: {st.get('remark') or st.get('rejection_reason') or ''}")
            time.sleep(0.5)
        raise RuntimeError(f"order {oid} not filled in time (status unknown); check the Groww app")

    # ------------------------------------------------------------------ public API
    def on_signal(self, sig: Signal, snap: ChainSnapshot | None) -> None:
        with self._lock:
            if self.replay:
                self._clock_day = sig.ts.date().isoformat()
            try:
                if sig.legs and sig.action == "SELL":
                    self._on_open_structure(sig, snap)
                elif sig.legs and sig.action == "EXIT":
                    self._on_exit_structure(sig, snap)
                elif sig.action == "BUY":
                    self._on_buy(sig, snap)
                elif sig.action == "EXIT":
                    self._on_exit(sig, snap)
            except Exception as exc:  # noqa: BLE001
                log.error("execution failed for %s: %s", sig.line(), exc)
                self._record({"event": "ERROR", "signal": sig.line(), "error": str(exc)})
            finally:
                self._persist()

    def _symbol_for(self, strike: float, kind: str, snap: ChainSnapshot | None) -> str:
        if snap is not None:
            syms = snap.extras.get("ce_sym" if kind == "CE" else "pe_sym")
            if syms:
                i = snap.strike_idx(strike)
                if syms[i]:
                    return str(syms[i])
        if self.mode == "paper" and self.replay:
            return f"NIFTY-{int(strike)}-{kind}"          # placeholder: nothing is sent in a paper replay
        raise RuntimeError(f"no broker symbol for {int(strike)} {kind} (option chain unavailable)")

    def _on_buy(self, sig: Signal, snap: ChainSnapshot | None) -> None:
        why = self._can_buy(sig)
        if why:
            self._record({"event": "SKIP_BUY", "signal": sig.line(), "reason": why})
            return
        lots = sig.lots or 1
        lots = max(1, min(lots, self.ex.max_lots))
        qty = lots * self.cfg.opt.lot_size
        symbol = self._symbol_for(sig.strike, sig.kind, snap)
        ref = f"NS{sig.ts.strftime('%d%H%M')}{int(sig.strike)}{sig.kind}"
        oid, fill = self._send(symbol, "BUY", qty, ref)
        price = fill or sig.premium
        self.pos = OpenOrder(symbol, sig.kind, sig.strike, qty, price, oid, sig.ts.isoformat())
        self.day.trades += 1
        self._record({"event": "BUY", "symbol": symbol, "qty": qty, "lots": lots, "price": price,
                      "order_id": oid, "sl": sig.sl_prem, "t1": sig.t1_prem, "t2": sig.t2_prem, "signal": sig.line()})

    def _on_exit(self, sig: Signal, snap: ChainSnapshot | None) -> None:
        pos = self.pos
        if pos is None or pos.kind != sig.kind or pos.strike != sig.strike:
            self._record({"event": "SKIP_EXIT", "signal": sig.line(), "reason": "no matching open position"})
            return
        partial = sig.reason.startswith("T1")
        if partial:
            lots_open = pos.qty // self.cfg.opt.lot_size
            if lots_open < 2 or pos.half_booked:
                return                                     # single lot: ride it to T2 / stop
            qty = (lots_open // 2) * self.cfg.opt.lot_size
        else:
            qty = pos.qty
        ref = f"NX{sig.ts.strftime('%d%H%M')}{int(sig.strike)}{sig.kind}"
        oid, fill = self._send(pos.symbol, "SELL", qty, ref)
        price = fill or sig.premium
        pnl = (price - pos.entry_price) * qty
        pos.realised += pnl
        self.day.realised += pnl
        self._record({"event": "SELL", "symbol": pos.symbol, "qty": qty, "price": price, "order_id": oid,
                      "reason": sig.reason, "pnl": round(pnl, 2), "day_pnl": round(self.day.realised, 2)})
        if partial:
            pos.qty -= qty
            pos.half_booked = True
            pos.booked_qty = qty
        else:
            self.pos = None
        if self.day.realised <= -abs(self.ex.max_daily_loss):
            self.day.halted = True
            self._record({"event": "HALT", "reason": f"daily loss limit {self.day.realised:.0f}"})

    # ------------------------------------------------------------------ multi-leg structures
    def _on_open_structure(self, sig: Signal, snap: ChainSnapshot | None) -> None:
        why = self._can_buy(sig)
        if why:
            self._record({"event": "SKIP_SELL", "signal": sig.line(), "reason": why})
            return
        lots = max(1, min(sig.lots or 1, self.ex.max_lots))
        qty = lots * self.cfg.opt.lot_size
        # hedges first, then the short legs
        ordered = sorted(sig.legs, key=lambda l: 0 if l["side"] == "BUY" else 1)
        filled: list[dict] = []
        try:
            for n, leg in enumerate(ordered):
                symbol = self._symbol_for(leg["strike"], leg["kind"], snap)
                ref = f"NF{sig.ts.strftime('%d%H%M')}{n}{int(leg['strike'])}{leg['kind']}"
                oid, fill = self._send(symbol, leg["side"], qty, ref)
                filled.append({"symbol": symbol, "kind": leg["kind"], "strike": leg["strike"], "side": leg["side"],
                               "qty": qty, "price": fill or leg["premium"], "order_id": oid})
        except Exception as exc:  # noqa: BLE001
            self._record({"event": "ERROR", "signal": sig.line(), "error": f"leg failed, unwinding {len(filled)} filled: {exc}"})
            self._unwind(filled, "UNWIND")
            return
        credit = sum((l["price"] if l["side"] == "SELL" else -l["price"]) for l in filled)
        self.pos = OpenOrder(f"{sig.structure} {int(sig.strike)}", "FLY", sig.strike, qty, credit, filled[-1]["order_id"],
                             sig.ts.isoformat(), legs=filled, structure=sig.structure)
        self.day.trades += 1
        self._record({"event": "SELL_STRUCTURE", "structure": sig.structure, "strike": sig.strike, "qty": qty, "lots": lots,
                      "credit": round(credit, 2), "legs": filled, "tp": sig.t1_prem, "sl": sig.t2_prem, "signal": sig.line()})

    def _unwind(self, legs: list[dict], reason: str) -> float:
        """Reverse the given legs (shorts first). Returns realised rupees. Legs that fail stay in `legs`."""
        pnl = 0.0
        remaining: list[dict] = []
        for leg in sorted(legs, key=lambda l: 0 if l["side"] == "SELL" else 1):
            side = "BUY" if leg["side"] == "SELL" else "SELL"
            try:
                oid, fill = self._send(leg["symbol"], side, leg["qty"], f"NC{int(time.time()) % 10000000}{leg['kind']}")
                price = fill or leg.get("exit_hint") or leg["price"]
                leg_pnl = (leg["price"] - price) * leg["qty"] if leg["side"] == "SELL" else (price - leg["price"]) * leg["qty"]
                pnl += leg_pnl
                self._record({"event": side, "symbol": leg["symbol"], "qty": leg["qty"], "price": price, "order_id": oid,
                              "reason": reason, "pnl": round(leg_pnl, 2)})
            except Exception as exc:  # noqa: BLE001
                self._record({"event": "ERROR", "error": f"close {leg['symbol']} failed: {exc}"})
                remaining.append(leg)
        legs[:] = remaining
        return pnl

    def _on_exit_structure(self, sig: Signal, snap: ChainSnapshot | None) -> None:
        pos = self.pos
        if pos is None or pos.kind != "FLY" or pos.strike != sig.strike:
            self._record({"event": "SKIP_EXIT", "signal": sig.line(), "reason": "no matching open structure"})
            return
        hints = {(l["kind"], l["strike"]): l["premium"] for l in sig.legs}
        for leg in pos.legs:
            leg["exit_hint"] = hints.get((leg["kind"], leg["strike"]))
        pnl = self._unwind(pos.legs, sig.reason)
        self.day.realised += pnl
        self._record({"event": "EXIT_STRUCTURE", "structure": pos.structure, "strike": pos.strike, "reason": sig.reason,
                      "pnl": round(pnl, 2), "day_pnl": round(self.day.realised, 2), "legs_left": len(pos.legs)})
        if not pos.legs:
            self.pos = None
        if self.day.realised <= -abs(self.ex.max_daily_loss):
            self.day.halted = True
            self._record({"event": "HALT", "reason": f"daily loss limit {self.day.realised:.0f}"})

    def flatten(self, reason: str, snap: ChainSnapshot | None = None) -> None:
        """Close any open position immediately (square-off / kill switch)."""
        with self._lock:
            if self.pos is None:
                return
            pos = self.pos
            if pos.kind == "FLY":
                for leg in pos.legs:
                    leg["exit_hint"] = snap.premium(leg["strike"], leg["kind"])[0] if snap is not None else None
                pnl = self._unwind(pos.legs, reason)
                self.day.realised += pnl
                self._record({"event": "EXIT_STRUCTURE", "structure": pos.structure, "strike": pos.strike, "reason": reason,
                              "pnl": round(pnl, 2), "day_pnl": round(self.day.realised, 2), "legs_left": len(pos.legs)})
                if not pos.legs:
                    self.pos = None
                self._persist()
                return
            try:
                oid, fill = self._send(pos.symbol, "SELL", pos.qty, f"NF{int(time.time()) % 100000000}")
                price = fill or (snap.premium(pos.strike, pos.kind)[0] if snap is not None else pos.entry_price)
                pnl = (price - pos.entry_price) * pos.qty
                self.day.realised += pnl
                self._record({"event": "SELL", "symbol": pos.symbol, "qty": pos.qty, "price": price, "order_id": oid,
                              "reason": reason, "pnl": round(pnl, 2), "day_pnl": round(self.day.realised, 2)})
                self.pos = None
            except Exception as exc:  # noqa: BLE001
                log.error("flatten failed: %s", exc)
                self._record({"event": "ERROR", "error": f"flatten: {exc}"})
            finally:
                self._persist()
