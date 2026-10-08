"""Configuration for the signal engine.

All thresholds live here so the algorithm is tunable without code edits.
Values can be overridden from a TOML file (see config.toml) via Config.load().
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import time
from pathlib import Path
from typing import Any


@dataclass
class DataConfig:
    use_chain: bool = True              # include option-chain factors / vetoes
    bar_interval: str = "5m"            # execution timeframe
    htf_interval: str = "15m"           # structure timeframe
    history_days: int = 90              # bars of history to keep for indicators / backtests
    cache_dir: str = "cache"
    chain_min_refresh_sec: int = 20     # option chain throttle
    csv_path: str = ""                  # if set, bars are read from a CSV/parquet export instead of Groww
    vix_path: str = ""                  # if set, daily India VIX is read from this CSV/parquet (backtests)


@dataclass
class SessionConfig:
    market_open: time = time(9, 15)
    market_close: time = time(15, 30)
    entry_start: time = time(9, 30)     # skip opening volatility
    entry_end: time = time(14, 45)      # no fresh entries after this
    square_off: time = time(15, 10)     # force exit
    expiry_entry_end: time = time(13, 30)   # on expiry day stop entries earlier (theta burn)
    weekly_expiry_weekday: int = 1      # 0=Mon .. 4=Fri (NIFTY weekly = Tuesday since Sep-2025)
    holidays: list[str] = field(default_factory=lambda: [
        # NSE trading holidays 2026 (update yearly). Expiry rolls to previous trading day.
        "2026-01-26", "2026-02-17", "2026-03-03", "2026-03-20", "2026-03-26", "2026-03-31",
        "2026-04-03", "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26", "2026-08-15",
        "2026-09-14", "2026-10-02", "2026-10-20", "2026-11-10", "2026-11-24", "2026-12-25",
    ])


@dataclass
class IndicatorConfig:
    ema_fast: int = 9
    ema_mid: int = 21
    ema_slow: int = 50
    htf_ema_fast: int = 20
    htf_ema_slow: int = 50
    daily_ema: int = 20
    atr_len: int = 14
    rsi_len: int = 14
    adx_len: int = 14
    st_len: int = 10
    st_mult: float = 3.0
    macd_fast: int = 12
    macd_slow: int = 26
    macd_sig: int = 9
    bb_len: int = 20
    bb_k: float = 2.0
    er_len: int = 10                    # Kaufman efficiency ratio
    donchian_len: int = 20
    pivot_k: int = 3                    # swing pivot strength
    pct_window: int = 1500              # bars for percentile ranks (~20 sessions of 5m)
    or_bars: int = 3                    # opening-range bars (3 x 5m = 15 min)


@dataclass
class FilterConfig:
    strategy: str = "iron_fly"          # "iron_fly" (premium selling, see [sell]) | "pa_short" (price-action shorts) | "confluence" (v1)
    # Regime
    adx_trend_min: float = 20.0
    adx_chop_max: float = 17.0
    er_trend_min: float = 0.30
    er_hard_min: float = 0.25           # path efficiency below this = whipsaw, no entries
    bbw_squeeze_pct: float = 25.0       # bandwidth percentile below which market is "coiled"
    atr_pct_min: float = 20.0           # too quiet: no edge after premium/spread
    atr_pct_max: float = 95.0           # too wild: gap/news
    vix_max: float = 24.0               # no signals when VIX above this
    vix_min: float = 9.0
    # Extension / exhaustion
    max_ext_atr: float = 1.6            # |close - ema21| / atr
    rsi_long_min: float = 48.0
    rsi_long_max: float = 70.0
    rsi_short_min: float = 30.0
    rsi_short_max: float = 52.0
    # Options chain
    pcr_hard_min: float = 0.45
    pcr_hard_max: float = 2.2
    pcr_long_min: float = 0.75
    pcr_long_max: float = 1.60
    pcr_short_min: float = 0.55
    pcr_short_max: float = 1.35
    iv_cap: float = 24.0                # ATM IV above this = premium too rich to buy
    wall_veto_pct: float = 0.25         # OI wall closer than this % of spot = veto
    wall_room_pct: float = 0.45         # OI wall farther than this = bonus
    # Scoring
    score_threshold: float = 70.0
    min_categories: int = 4
    # Trade management
    max_signals_per_day: int = 4
    cooldown_bars: int = 3
    cooldown_after_sl: int = 6
    sl_atr: float = 1.5
    sl_min_atr: float = 1.0
    t1_r: float = 1.0
    t2_r: float = 3.0
    time_stop_bars: int = 18            # exit if T1 not reached in N bars (90 min on 5m)
    trail_after_t1: bool = True
    breakeven_after_t1: bool = True     # move the stop to entry once T1 is hit
    exit_on_flip: bool = True           # exit when the 5m supertrend flips against the trade
    pa_entry_start: str = "09:30"       # price-action entries only inside this window (bar close time)
    pa_entry_end: str = "14:45"
    pa_triggers: str = ""               # pa_short: comma list of allowed triggers ("" = all)
    buy_dte_min: float = 0.0            # buyers: no entries when trading days to expiry is below this (theta)
    buy_dte_max: float = 99.0


@dataclass
class OptionsConfig:
    lot_size: int = 75
    strike_step: int = 50
    itm_on_expiry: bool = True          # pick 1-strike ITM when DTE <= 1
    itm_strikes: int = 0                # 0 = ATM otherwise
    capital: float = 0.0                # if > 0, lots are suggested
    risk_per_trade_pct: float = 1.0
    slippage_pct: float = 0.5           # for backtest premium fills (% of premium per side)
    slippage_pts: float = 0.0           # if > 0, used instead: fixed points per side (fairer for ITM options)
    min_premium: float = 40.0           # do not buy options cheaper than this (gamma lottery)
    max_premium: float = 400.0


@dataclass
class SellConfig:
    """Defined-risk premium selling (weekly iron fly): short ATM straddle + long wings.

    Research (docs/RESEARCH.md s.6): NIFTY implied vol runs above realised on average and intraday
    direction has no usable edge, so the engine sells time/volatility with a hard cap on loss and
    uses the regime / price-action modules only to decide when NOT to sell.
    """
    entry_time: time = time(9, 45)      # entries allowed on any bar closing between entry_time and last_entry_time
    last_entry_time: time = time(13, 0)
    expiry_last_entry_time: time = time(13, 0)   # on expiry day stop opening new structures earlier
    reentry_cooldown_bars: int = 3      # bars to wait after an exit before a new structure may be sold
    reentry_after_sl: bool = True       # allow a fresh (re-centred) structure after a stop-out
    exit_time: time = time(14, 45)      # close everything by this bar close
    expiry_exit_time: time = time(14, 45)   # expiry day exit (13:30 is the conservative choice)
    dte_min: float = 0.0                # trade only when trading days to expiry is in [dte_min, dte_max]
    dte_max: float = 2.0                # ... i.e. expiry day and the session before: the only sessions with net theta
    wing_pts: int = 400                 # protective wings this far from the ATM strike
    wing_iv_add: float = 2.0            # vol points added to wing IV in simulation (put skew, conservative)
    tp_frac: float = 0.5                # take profit when this fraction of the credit has decayed
    sl_mult: float = 0.35               # stop when the loss reaches sl_mult x credit
    gap_max_pct: float = 100.0          # skip days that open more than this % away from the prior close
    open_move_max_pct: float = 0.45     # skip if spot has already moved more than this % from the open
    vix_min: float = 9.0
    vix_max: float = 24.0
    vix_spike_ratio: float = 1.3        # skip when VIX / its 20-day mean exceeds this
    adx_max: float = 100.0             # skip when the 15m ADX says the market is trending hard
    event_dates: list[str] = field(default_factory=list)   # yyyy-mm-dd days to skip (budget, policy, results)
    cost_pts: float = 6.0               # round-trip cost per structure in index points (4 legs: spread + brokerage)
    margin_per_lot: float = 40000.0     # approximate exchange margin for one hedged lot (return reporting)
    max_structures_per_day: int = 3


@dataclass
class GrowwConfig:
    access_token: str = ""              # or set GROWW_ACCESS_TOKEN
    api_key: str = ""                   # + api_secret   (daily-approval flow)
    api_secret: str = ""
    totp_token: str = ""                # + totp_secret  (no-expiry flow, needs pyotp)
    totp_secret: str = ""
    groww_symbol: str = "NSE-NIFTY"     # index symbol for candles
    vix_symbol: str = "NSE-INDIAVIX"    # India VIX daily candles ("" to disable the VIX filter)
    segment: str = "CASH"
    underlying: str = "NIFTY"           # option chain underlying


@dataclass
class ExecConfig:
    enabled: bool = False               # False = alerts only; True = route signals to the executor
    mode: str = "paper"                 # "paper" (log orders, send nothing) | "live" (real orders on Groww)
    max_lots: int = 1                   # hard cap per trade regardless of sizing
    max_trades_per_day: int = 3
    max_daily_loss: float = 1500.0      # rupees; realised loss beyond this halts new buys for the day
    kill_file: str = "STOP"             # create this file in the project dir to halt trading and flatten
    flatten_at_square_off: bool = True


@dataclass
class AlertConfig:
    console: bool = True
    file: str = "logs/signals.jsonl"
    webhook_url: str = ""               # generic JSON POST
    telegram_token: str = ""
    telegram_chat_id: str = ""
    verbose: bool = False               # include score breakdown


@dataclass
class Config:
    data: DataConfig = field(default_factory=DataConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    ind: IndicatorConfig = field(default_factory=IndicatorConfig)
    filt: FilterConfig = field(default_factory=FilterConfig)
    sell: SellConfig = field(default_factory=SellConfig)
    opt: OptionsConfig = field(default_factory=OptionsConfig)
    groww: GrowwConfig = field(default_factory=GrowwConfig)
    exec: ExecConfig = field(default_factory=ExecConfig)
    alert: AlertConfig = field(default_factory=AlertConfig)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        cfg = cls()
        if path is None:
            return cfg
        p = Path(path)
        if not p.exists():
            return cfg
        with open(p, "rb") as fh:
            raw = tomllib.load(fh)
        _apply(cfg, raw)
        return cfg


def _coerce(current: Any, value: Any) -> Any:
    if isinstance(current, time) and isinstance(value, str):
        h, m = value.split(":")[:2]
        return time(int(h), int(m))
    if isinstance(current, bool):
        return bool(value)
    if isinstance(current, int) and not isinstance(current, bool):
        return int(value)
    if isinstance(current, float):
        return float(value)
    return value


def _apply(obj: Any, raw: dict) -> None:
    for f in fields(obj):
        if f.name not in raw:
            continue
        cur = getattr(obj, f.name)
        if is_dataclass(cur) and isinstance(raw[f.name], dict):
            _apply(cur, raw[f.name])
        else:
            setattr(obj, f.name, _coerce(cur, raw[f.name]))
