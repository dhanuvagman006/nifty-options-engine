"""Executor tests: paper mode never touches the broker; live mode uses a fake API; rails hold."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from nifty_signals.config import Config
from nifty_signals.data.chain import ChainSnapshot, derive
from nifty_signals.engine.signals import Signal
from nifty_signals.execution.broker import Executor

IST = "Asia/Kolkata"


def _snap() -> ChainSnapshot:
    ks = np.arange(22100.0, 22501.0, 50.0)
    n = ks.size
    s = ChainSnapshot(ts=pd.Timestamp.now(tz=IST), spot=22281.8, expiry="13-Oct-2026", strikes=ks,
                      ce_oi=np.full(n, 1000.0), pe_oi=np.full(n, 1000.0), ce_chg_oi=np.zeros(n), pe_chg_oi=np.zeros(n),
                      ce_vol=np.zeros(n), pe_vol=np.zeros(n), ce_iv=np.full(n, 13.0), pe_iv=np.full(n, 13.0),
                      ce_ltp=np.full(n, 100.0), pe_ltp=np.full(n, 100.0), ce_bid=np.full(n, 99.0), ce_ask=np.full(n, 101.0),
                      pe_bid=np.full(n, 99.0), pe_ask=np.full(n, 101.0),
                      extras={"ce_sym": [f"NIFTY26O13{int(k)}CE" for k in ks], "pe_sym": [f"NIFTY26O13{int(k)}PE" for k in ks]})
    derive(s, 50)
    return s


def _buy(ts="2026-10-08 10:15", strike=22300, kind="PE", lots=1) -> Signal:
    return Signal(pd.Timestamp(ts, tz=IST), "BUY", kind, strike, "13-Oct", 100.0, 22281.8, 80, 120, 160,
                  22320, 22240, 22200, 80, "dc", lots=lots)


def _exit(ts, reason, prem, strike=22300, kind="PE") -> Signal:
    s = Signal(pd.Timestamp(ts, tz=IST), "EXIT", kind, strike, "13-Oct", prem, 22250, reason=reason)
    return s


class FakeAPI:
    VALIDITY_DAY = "DAY"; EXCHANGE_NSE = "NSE"; ORDER_TYPE_MARKET = "MARKET"; PRODUCT_MIS = "MIS"
    SEGMENT_FNO = "FNO"; TRANSACTION_TYPE_BUY = "BUY"; TRANSACTION_TYPE_SELL = "SELL"

    def __init__(self, reject=False):
        self.orders = []
        self.reject = reject

    def place_order(self, **kw):
        self.orders.append(kw)
        return {"groww_order_id": f"GO{len(self.orders)}"}

    def get_order_status(self, segment, groww_order_id):
        return {"order_status": "REJECTED" if self.reject else "EXECUTED"}

    def get_order_detail(self, segment, groww_order_id):
        return {"average_fill_price": 101.5}


class FakeClient:
    def __init__(self, api):
        self.api = api


@pytest.fixture
def cfg(tmp_path):
    c = Config()
    c.exec.enabled = True
    c.exec.mode = "paper"
    c.exec.kill_file = str(tmp_path / "STOP")
    c.data.cache_dir = str(tmp_path / "cache")
    return c


def test_paper_mode_logs_without_client(cfg, tmp_path):
    ex = Executor(cfg, None, tmp_path / "orders.jsonl")
    ex.on_signal(_buy(), _snap())
    assert ex.pos is not None and ex.pos.qty == 75 and ex.pos.symbol == "NIFTY26O1322300PE"
    ex.on_signal(_exit("2026-10-08 10:40", "T1 HIT (book half, SL->entry)", 120.0), _snap())
    assert ex.pos is not None and ex.pos.qty == 75          # single lot: no partial
    ex.on_signal(_exit("2026-10-08 11:25", "T2", 160.0), _snap())
    assert ex.pos is None
    assert ex.day.realised == pytest.approx(60.0 * 75)
    lines = (tmp_path / "orders.jsonl").read_text().strip().splitlines()
    assert [l.split('"event": "')[1].split('"')[0] for l in lines] == ["BUY", "SELL"]


def test_partial_booking_with_two_lots(cfg, tmp_path):
    cfg.exec.max_lots = 2
    ex = Executor(cfg, None, tmp_path / "o.jsonl")
    ex.on_signal(_buy(lots=2), _snap())
    assert ex.pos.qty == 150
    ex.on_signal(_exit("2026-10-08 10:40", "T1 HIT (book half, SL->entry)", 120.0), _snap())
    assert ex.pos.qty == 75 and ex.pos.half_booked
    ex.on_signal(_exit("2026-10-08 11:00", "TRAIL", 110.0), _snap())
    assert ex.pos is None
    assert ex.day.realised == pytest.approx(20 * 75 + 10 * 75)


def test_live_mode_sends_market_orders_and_uses_fill_price(cfg, tmp_path):
    cfg.exec.mode = "live"
    api = FakeAPI()
    ex = Executor(cfg, FakeClient(api), tmp_path / "o.jsonl")
    ex.on_signal(_buy(), _snap())
    assert api.orders[0]["transaction_type"] == "BUY" and api.orders[0]["product"] == "MIS"
    assert api.orders[0]["quantity"] == 75 and api.orders[0]["trading_symbol"] == "NIFTY26O1322300PE"
    assert ex.pos.entry_price == 101.5
    ex.on_signal(_exit("2026-10-08 11:00", "SL", 80.0), _snap())
    assert api.orders[1]["transaction_type"] == "SELL" and ex.pos is None


def test_rejected_buy_leaves_no_position_and_exit_is_ignored(cfg, tmp_path):
    cfg.exec.mode = "live"
    api = FakeAPI(reject=True)
    ex = Executor(cfg, FakeClient(api), tmp_path / "o.jsonl")
    ex.on_signal(_buy(), _snap())
    assert ex.pos is None
    ex.on_signal(_exit("2026-10-08 11:00", "SL", 80.0), _snap())
    assert len(api.orders) == 1                              # no sell was attempted


def test_rails_daily_loss_and_trade_cap_and_kill(cfg, tmp_path):
    cfg.exec.max_daily_loss = 1000
    cfg.exec.max_trades_per_day = 2
    ex = Executor(cfg, None, tmp_path / "o.jsonl")
    ex.on_signal(_buy("2026-10-08 10:15"), _snap())
    ex.on_signal(_exit("2026-10-08 10:30", "SL", 80.0), _snap())    # -20 * 75 = -1500
    assert ex.day.halted
    ex.on_signal(_buy("2026-10-08 11:15"), _snap())
    assert ex.pos is None                                      # halted
    ex2 = Executor(cfg, None, tmp_path / "o2.jsonl")
    ex2.day.halted = False
    ex2.day.realised = 0
    ex2.day.trades = 2
    ex2.on_signal(_buy("2026-10-08 11:15"), _snap())
    assert ex2.pos is None                                     # trade cap
    (tmp_path / "STOP").write_text("")
    ex3 = Executor(cfg, None, tmp_path / "o3.jsonl")
    ex3.day.trades = 0
    ex3.day.halted = False
    ex3.day.realised = 0
    ex3.on_signal(_buy("2026-10-08 11:15"), _snap())
    assert ex3.pos is None                                     # kill switch


def test_no_buy_after_square_off_and_missing_symbol(cfg, tmp_path):
    ex = Executor(cfg, None, tmp_path / "o.jsonl")
    ex.on_signal(_buy("2026-10-08 15:12"), _snap())
    assert ex.pos is None
    ex.on_signal(_buy("2026-10-08 10:15"), None)               # no chain -> no symbol -> error logged, no position
    assert ex.pos is None


def _fly(ts="2026-10-08 09:40", atm=22300) -> Signal:
    legs = [{"kind": "CE", "strike": atm, "side": "SELL", "premium": 100.0},
            {"kind": "PE", "strike": atm, "side": "SELL", "premium": 100.0},
            {"kind": "CE", "strike": atm + 200, "side": "BUY", "premium": 30.0},
            {"kind": "PE", "strike": atm - 200, "side": "BUY", "premium": 30.0}]
    return Signal(pd.Timestamp(ts, tz=IST), "SELL", "FLY", atm, "13-Oct", 140.0, 22281.8, t1_prem=70, t2_prem=210,
                  lots=1, legs=legs, structure="IRON FLY")


def _fly_exit(ts, reason, atm=22300, short_px=80.0, wing_px=25.0) -> Signal:
    legs = [{"kind": "CE", "strike": atm, "side": "BUY", "premium": short_px},
            {"kind": "PE", "strike": atm, "side": "BUY", "premium": short_px},
            {"kind": "CE", "strike": atm + 200, "side": "SELL", "premium": wing_px},
            {"kind": "PE", "strike": atm - 200, "side": "SELL", "premium": wing_px}]
    return Signal(pd.Timestamp(ts, tz=IST), "EXIT", "FLY", atm, "13-Oct", 2 * short_px - 2 * wing_px, 22290,
                  reason=reason, legs=legs, structure="IRON FLY")


def test_iron_fly_paper_round_trip_hedges_first(cfg, tmp_path):
    ex = Executor(cfg, None, tmp_path / "o.jsonl")
    ex.on_signal(_fly(), _snap())
    assert ex.pos is not None and ex.pos.kind == "FLY" and len(ex.pos.legs) == 4
    assert [l["side"] for l in ex.pos.legs] == ["BUY", "BUY", "SELL", "SELL"]      # wings first
    assert ex.pos.entry_price == pytest.approx(140.0)
    ex.on_signal(_fly_exit("2026-10-08 14:40", "TIME"), _snap())
    assert ex.pos is None
    # shorts: (100-80)*75*2 = 3000 ; wings: (25-30)*75*2 = -750
    assert ex.day.realised == pytest.approx(2250.0)
    events = [l.split('"event": "')[1].split('"')[0] for l in (tmp_path / "o.jsonl").read_text().strip().splitlines()]
    assert events[0] == "SELL_STRUCTURE" and events[-1] == "EXIT_STRUCTURE"
    assert events[1:3] == ["BUY", "BUY"] and events[3:5] == ["SELL", "SELL"]      # exit: shorts bought back first


def test_iron_fly_live_leg_failure_unwinds(cfg, tmp_path):
    cfg.exec.mode = "live"

    class FlakyAPI(FakeAPI):
        def get_order_status(self, segment, groww_order_id):
            # third order (first short leg) is rejected
            return {"order_status": "REJECTED" if groww_order_id == "GO3" else "EXECUTED"}

    api = FlakyAPI()
    ex = Executor(cfg, FakeClient(api), tmp_path / "o.jsonl")
    ex.on_signal(_fly(), _snap())
    assert ex.pos is None
    sides = [o["transaction_type"] for o in api.orders]
    assert sides == ["BUY", "BUY", "SELL", "SELL", "SELL"]        # 2 wings, failed short, 2 wing unwinds
    assert ex.day.trades == 0


def test_iron_fly_flatten_uses_chain_prices(cfg, tmp_path):
    ex = Executor(cfg, None, tmp_path / "o.jsonl")
    ex.on_signal(_fly(), _snap())
    ex.flatten("KILL", _snap())                                      # chain LTP = 100 for every strike
    assert ex.pos is None
    # shorts flat (100 -> 100), wings 30 -> 100: +70*75*2
    assert ex.day.realised == pytest.approx(70 * 75 * 2)
