"""Historical replay of the signal engine with Black-Scholes premium simulation.

Spot bars are real; option premiums are synthesised from India VIX (previous close) and the
true weekly expiry calendar, so theta decay and delta are modelled. Option-chain factors are
unavailable historically and are therefore excluded from the score normalisation.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..config import Config
from ..engine.calendar import ExpiryCalendar
from ..engine.signals import Signal, make_engine


@dataclass
class BacktestResult:
    signals: list[Signal]
    trades: pd.DataFrame
    metrics: dict

    def report(self) -> str:
        m = self.metrics
        if not m:
            return "no trades"
        rows = [
            ("Trades", f"{m['trades']}  ({m['sessions']} sessions, {m['per_session']:.2f}/session)"),
            ("Win rate", f"{m['win_rate']:.1f}%"),
            ("Avg win / loss", f"{m['avg_win']:+.1f}% / {m['avg_loss']:+.1f}%"),
            ("Profit factor", f"{m['profit_factor']:.2f}"),
            ("Expectancy / trade", f"{m['expectancy']:+.1f}%  ({m['exp_pts']:+.1f} pts, Rs {m['exp_rs']:+.0f}/lot)"),
            ("Net P&L (1 lot)", f"{m['total_pts']:+.0f} pts = Rs {m['total_rs']:+,.0f}"),
            ("Max drawdown (1 lot)", f"{m['max_dd_pts']:.0f} pts = Rs {m['max_dd_rs']:,.0f}"),
            ("Worst trade", f"{m['worst_pts']:+.0f} pts = Rs {m['worst_rs']:+,.0f}"),
            ("Avg bars held", f"{m['avg_bars']:.1f}"),
            ("Exit reasons", m["reasons"]),
        ]
        if m.get("margin"):
            rows.insert(6, ("Return on margin", f"{m['ret_on_margin']:+.1f}% on Rs {m['margin']:,.0f} per lot ({m['days']} days)"))
        if m.get("by_year"):
            rows.append(("By year (trades / win% / pts)", m["by_year"]))
        w = max(len(a) for a, _ in rows)
        return "\n".join(f"{a.ljust(w)}  {b}" for a, b in rows)


def run_backtest(feats: pd.DataFrame, cfg: Config, bar_minutes: int = 5, slippage_pct: float | None = None,
                 start: int = 0) -> BacktestResult:
    """Replay bars [start, n). Bars before `start` only warm the engine's history window."""
    eng = make_engine(cfg, bar_minutes, cal=ExpiryCalendar(cfg.session))
    slip = (cfg.opt.slippage_pct if slippage_pct is None else slippage_pct) / 100.0
    sigs: list[Signal] = []
    n = len(feats)
    eng.state.last_i = max(start, 0) - 1
    for i in range(max(start, 0), n):
        for s in eng.on_bar(feats, i):
            if s.kind != "FLY":                    # the fly carries its own cost model (sell.cost_pts)
                if s.action == "BUY":
                    s.premium *= 1 + slip
                elif s.action == "EXIT":
                    s.premium *= 1 - slip
            sigs.append(s)
    trades = pd.DataFrame(eng.state.trades)
    sessions = int(feats["session"].iloc[max(start, 0):].nunique()) if n else 0
    return BacktestResult(sigs, trades, metrics_for(trades, cfg, slip, sessions))


def metrics_for(trades: pd.DataFrame, cfg: Config, slip: float, sessions: int) -> dict:
    if trades.empty:
        return {}
    trades = trades.copy()
    directional = trades["kind"] != "FLY"
    if directional.any():
        # apply slippage symmetrically to bought-option trades
        if cfg.opt.slippage_pts > 0:
            trades.loc[directional, "entry_prem"] += cfg.opt.slippage_pts
            trades.loc[directional, "exit_prem"] -= cfg.opt.slippage_pts
        else:
            trades.loc[directional, "entry_prem"] *= 1 + slip
            trades.loc[directional, "exit_prem"] *= 1 - slip
        trades.loc[directional, "pnl_pts"] = trades.loc[directional, "exit_prem"] - trades.loc[directional, "entry_prem"]
        trades.loc[directional, "pnl_pct"] = trades.loc[directional, "pnl_pts"] / trades.loc[directional, "entry_prem"] * 100
    lot = cfg.opt.lot_size
    pts = trades["pnl_pts"].to_numpy()
    pnl = trades["pnl_pct"].to_numpy()
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    gross_w = pts[pts > 0].sum()
    gross_l = -pts[pts <= 0].sum()
    eq = np.cumsum(pts)
    dd = np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:] - eq
    yrs = pd.DatetimeIndex(trades["entry_ts"]).year
    by_year = {}
    for y, g in trades.groupby(yrs):
        by_year[int(y)] = f"{len(g)} / {100 * (g['pnl_pts'] > 0).mean():.0f}% / {g['pnl_pts'].sum():+.0f}"
    days = int(pd.DatetimeIndex(trades["entry_ts"]).normalize().nunique())
    m = {
        "trades": int(len(trades)),
        "sessions": sessions,
        "days": days,
        "win_rate": 100.0 * len(wins) / len(pnl),
        "avg_win": float(wins.mean()) if len(wins) else 0.0,
        "avg_loss": float(losses.mean()) if len(losses) else 0.0,
        "profit_factor": float(gross_w / gross_l) if gross_l > 0 else float("inf"),
        "expectancy": float(pnl.mean()),
        "exp_pts": float(pts.mean()),
        "exp_rs": float(pts.mean() * lot),
        "total_pts": float(pts.sum()),
        "total_rs": float(pts.sum() * lot),
        "max_dd_pts": float(dd.max()) if len(dd) else 0.0,
        "max_dd_rs": float(dd.max() * lot) if len(dd) else 0.0,
        "worst_pts": float(pts.min()),
        "worst_rs": float(pts.min() * lot),
        "avg_bars": float(trades["bars"].mean()),
        "per_session": len(trades) / max(sessions, 1),
        "reasons": trades["reason"].value_counts().to_dict(),
        "by_year": by_year,
    }
    if (~directional).any():
        margin = cfg.sell.margin_per_lot
        m["margin"] = margin
        m["ret_on_margin"] = float(pts.sum() * lot / margin * 100.0) if margin > 0 else 0.0
    return m
