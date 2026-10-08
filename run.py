"""Nifty options signal engine - command line entry point.

    python run.py live                 # run continuously during market hours
    python run.py scan                 # evaluate the latest completed bar once and exit
    python run.py backtest [--days 55] # replay history, print signals + metrics
    python run.py status               # show current market state / why no signal
"""
from __future__ import annotations

import argparse
import logging
import sys
import warnings

warnings.filterwarnings("ignore")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Nifty options signal engine")
    p.add_argument("cmd", choices=["live", "scan", "backtest", "paper-replay", "status", "groww-check"])
    p.add_argument("--config", default="config.toml")
    p.add_argument("--days", type=int, default=None, help="history days for backtest")
    p.add_argument("--no-chain", action="store_true", help="skip the option chain (technical factors only)")
    p.add_argument("--verbose", "-v", action="store_true", help="include score breakdown in alerts")
    p.add_argument("--quiet", "-q", action="store_true", help="signals only, no log lines")
    p.add_argument("--csv", default="", help="export backtest trades to CSV")
    p.add_argument("--bars", default="", help="backtest: read 5m bars from this CSV/parquet instead of Groww")
    p.add_argument("--vix", default="", help="backtest: read daily India VIX from this CSV/parquet")
    p.add_argument("--from", dest="start", default="", help="backtest: first session (YYYY-MM-DD)")
    p.add_argument("--to", dest="end", default="", help="backtest: last session (YYYY-MM-DD)")
    p.add_argument("--strategy", default="", help="override [filt].strategy: iron_fly | pa_short | confluence")
    a = p.parse_args(argv)

    from nifty_signals.config import Config

    cfg = Config.load(a.config)
    if a.verbose:
        cfg.alert.verbose = True
    if a.no_chain:
        cfg.data.use_chain = False
    if a.bars:
        cfg.data.csv_path = a.bars
    if a.vix:
        cfg.data.vix_path = a.vix
    if a.strategy:
        cfg.filt.strategy = a.strategy
    logging.basicConfig(level=logging.ERROR if a.quiet else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S", stream=sys.stderr)
    from nifty_signals.indicators.core import warmup

    warmup()

    if a.cmd in ("live", "scan"):
        from nifty_signals.live import run_live

        run_live(cfg, once=(a.cmd == "scan"), no_chain=a.no_chain)
        return 0

    if a.cmd == "status":
        return status(cfg, a.no_chain)
    if a.cmd == "paper-replay":
        return paper_replay(cfg, a)
    if a.cmd == "groww-check":
        return groww_check(cfg)

    import pandas as pd

    from nifty_signals.backtest.runner import run_backtest
    from nifty_signals.live import DataHub

    hub = DataHub(cfg)
    days = a.days
    if a.start and not days:
        days = (pd.Timestamp.now(tz="Asia/Kolkata") - pd.Timestamp(a.start, tz="Asia/Kolkata")).days + 120
    feats = hub.load(days)
    if a.end:
        feats = feats[feats.index < pd.Timestamp(a.end, tz="Asia/Kolkata") + pd.Timedelta(days=1)]
    start = int((feats.index < pd.Timestamp(a.start, tz="Asia/Kolkata")).sum()) if a.start else 0
    res = run_backtest(feats, cfg, hub.bar_minutes, start=start)
    for s in res.signals:
        print(s.line(cfg.alert.verbose))
    print()
    print(f"strategy {cfg.filt.strategy}  bars {feats.index[start] if len(feats) > start else None} -> {feats.index[-1] if len(feats) else None}")
    print(res.report())
    if a.csv and not res.trades.empty:
        res.trades.to_csv(a.csv, index=False)
        print(f"trades written to {a.csv}")
    return 0


def paper_replay(cfg, a) -> int:
    """Feed historical bars through the engine AND the paper executor, exactly as `live` would, so the
    order log (logs/orders_replay.jsonl) shows what would have been sent. Nothing reaches the broker."""
    import pandas as pd

    from nifty_signals.engine.signals import make_engine
    from nifty_signals.execution.broker import Executor
    from nifty_signals.live import DataHub, _heartbeat

    cfg.exec.enabled = True
    cfg.exec.mode = "paper"
    hub = DataHub(cfg)
    days = a.days
    if a.start and not days:
        days = (pd.Timestamp.now(tz="Asia/Kolkata") - pd.Timestamp(a.start, tz="Asia/Kolkata")).days + 120
    feats = hub.load(days)
    if a.end:
        feats = feats[feats.index < pd.Timestamp(a.end, tz="Asia/Kolkata") + pd.Timedelta(days=1)]
    start = int((feats.index < pd.Timestamp(a.start, tz="Asia/Kolkata")).sum()) if a.start else 0
    eng = make_engine(cfg, hub.bar_minutes, cal=hub.cal)
    eng.state.last_i = start - 1
    execu = Executor(cfg, None, "logs/orders_replay.jsonl", replay=True)
    lot = cfg.opt.lot_size
    day_pnl: dict = {}
    for i in range(start, len(feats)):
        sigs = eng.on_bar(feats, i)
        for sig in sigs:
            print(sig.line(cfg.alert.verbose))
            execu.on_signal(sig, None)
            print(f"           executor: day P&L Rs {execu.day.realised:+,.0f}  trades today {execu.day.trades}"
                  f"{'  HALTED' if execu.day.halted else ''}")
            day_pnl[sig.ts.date()] = execu.day.realised
        if a.verbose and (i - start) % 12 == 0:
            print("   " + _heartbeat(cfg, eng, feats, i, None, hub.bar_minutes))
    print()
    total = sum(day_pnl.values())
    wins = sum(1 for v in day_pnl.values() if v > 0)
    lots = min(cfg.exec.max_lots, 1) if cfg.exec.max_lots else 1
    n_fly = sum(1 for v in day_pnl)
    est_cost = n_fly * cfg.sell.cost_pts * lot * lots if cfg.filt.strategy == "iron_fly" else 0.0
    print(f"paper replay {feats.index[start].date()} -> {feats.index[-1].date()}: {len(day_pnl)} trading days with orders, "
          f"{wins} positive, gross Rs {total:+,.0f} at model mid prices on {cfg.exec.max_lots} lot (capital {cfg.opt.capital:,.0f})")
    if est_cost:
        print(f"less estimated spread + brokerage ({cfg.sell.cost_pts:.0f} pts per structure): net Rs {total - est_cost:+,.0f}")
    print("order log: logs/orders_replay.jsonl")
    return 0


def status(cfg, no_chain: bool) -> int:
    """Diagnostic: show the latest bar's state and the scorer verdict for both directions."""
    from nifty_signals.data.chain import ChainHistory
    from nifty_signals.live import DataHub

    from nifty_signals.engine.signals import make_engine

    hub = DataHub(cfg)
    eng = make_engine(cfg, hub.bar_minutes, cal=hub.cal)
    feats = hub.load()
    i = len(feats) - 1
    w = feats.iloc[i].to_dict()
    w["ts"] = feats.index[i]
    hist = []
    for j in range(max(0, i - 6), i):
        h = feats.iloc[j].to_dict()
        h["ts"] = feats.index[j]
        hist.append(h)
    snap = None
    if not no_chain:
        try:
            ch = hub.chain()
            snap = ch.snapshot() if ch is not None else None
        except Exception as exc:  # noqa: BLE001
            print(f"option chain unavailable: {exc}")
    print(f"bar {w['ts']}  close {w['close']:.1f}  atr {w['atr']:.1f} ({w['atr_pct']:.0f}p)  rsi {w['rsi']:.0f}  "
          f"adx {w['adx']:.0f}  er {w['er']:.2f}  st {int(w['st_dir']):+d}  vwap {w['vwap']:.0f}  vix {w['vix']:.1f}  dte {w['dte']:.1f}")
    print(f"15m: ema{cfg.ind.htf_ema_fast} {w['h_ema_f']:.0f} ema{cfg.ind.htf_ema_slow} {w['h_ema_s']:.0f} close {w['h_close']:.0f} rsi {w['h_rsi']:.0f}  "
          f"| daily bias {int(w['d_bias']):+d} pdc {w['d_close']:.0f}")
    if snap is not None:
        print(f"chain {snap.expiry}: spot {snap.spot:.1f} atm {snap.atm:.0f} pcr {snap.pcr_oi:.2f} (chg {snap.pcr_chg:.2f}) "
              f"iv {snap.atm_iv_ce:.1f}/{snap.atm_iv_pe:.1f} maxpain {snap.max_pain:.0f} "
              f"callwall {snap.call_wall:.0f} (+{snap.call_wall_pct:.2f}%) putwall {snap.put_wall:.0f} (-{snap.put_wall_pct:.2f}%)")
    print(f"strategy {cfg.filt.strategy}: {eng.status(w, hist, snap)}")
    return 0


def groww_check(cfg) -> int:
    """Verify Groww credentials, candles and option chain end to end."""
    from nifty_signals.data.groww import GrowwBarSource, GrowwClient, GrowwOptionChain

    client = GrowwClient(cfg.groww)
    try:
        client.api
    except Exception as exc:  # noqa: BLE001
        print(f"AUTH FAILED: {exc}")
        return 1
    print("auth ok")
    src = GrowwBarSource(client, cfg.groww.groww_symbol, cfg.groww.segment, cfg.data.cache_dir)
    try:
        b = src.bars(cfg.data.bar_interval, 5)
        print(f"{cfg.data.bar_interval} candles: {len(b)} rows, last {b.index[-1] if len(b) else None}")
        print(b.tail(3).to_string())
        d = src.bars("1d", 30)
        print(f"daily candles: {len(d)} rows, last {d.index[-1] if len(d) else None}")
    except Exception as exc:  # noqa: BLE001
        print(f"CANDLES FAILED: {exc}")
        return 1
    ch = GrowwOptionChain(client, cfg.groww.underlying, 0, cfg.opt.strike_step, cfg.data.cache_dir)
    try:
        exps = ch.expiries()
        print(f"expiries: {exps[:4]}")
        s = ch.snapshot()
        print(f"chain {s.expiry}: spot {s.spot:.1f} atm {s.atm:.0f} strikes {s.strikes.size} pcr {s.pcr_oi:.2f} "
              f"iv {s.atm_iv_ce:.1f}/{s.atm_iv_pe:.1f} maxpain {s.max_pain:.0f} callwall {s.call_wall:.0f} putwall {s.put_wall:.0f}")
        ltp, bid, ask, iv = s.premium(s.atm, "CE")
        print(f"ATM CE ltp {ltp:.2f} iv {iv:.1f}")
    except Exception as exc:  # noqa: BLE001
        print(f"OPTION CHAIN FAILED: {exc}")
        return 1
    print("groww check passed")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
