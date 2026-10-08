"""Trading calendar helpers: expiry dates, days-to-expiry, session time windows."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from ..config import SessionConfig

IST = "Asia/Kolkata"


class ExpiryCalendar:
    """Weekly NIFTY expiry rule with holiday roll-back.

    Live mode should prefer the exact dates from NSE (set_known_expiries); the rule is the
    fallback used in backtests and when NSE is unreachable.
    """

    def __init__(self, cfg: SessionConfig, known: list[date] | None = None):
        self.cfg = cfg
        self.holidays = {date.fromisoformat(h) for h in cfg.holidays}
        self.known = sorted(known or [])

    def set_known_expiries(self, dates: list[date]) -> None:
        self.known = sorted(set(dates))

    def is_trading_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    # NIFTY weekly options: launched 11-Feb-2019 (Thursday expiry); moved to Tuesday from 1-Sep-2025.
    WEEKLY_START = date(2019, 2, 11)
    TUESDAY_FROM = date(2025, 9, 1)

    def _rule_expiry(self, d: date) -> date:
        if d < self.WEEKLY_START:                       # monthly contracts only: last Thursday of month
            m_end = (d.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
            exp = m_end - timedelta(days=(m_end.weekday() - 3) % 7)
            while not self.is_trading_day(exp):
                exp -= timedelta(days=1)
            if exp < d:
                return self._rule_expiry(m_end + timedelta(days=1))
            return exp
        wd = self.cfg.weekly_expiry_weekday if d >= self.TUESDAY_FROM else 3
        delta = (wd - d.weekday()) % 7
        exp = d + timedelta(days=delta)
        while not self.is_trading_day(exp):
            exp -= timedelta(days=1)
        if exp < d:  # rolled back before today: next week's contract
            return self._rule_expiry(d + timedelta(days=delta + 1))
        return exp

    def next_expiry(self, d: date) -> date:
        for k in self.known:
            if k >= d:
                return k
        return self._rule_expiry(d)

    def dte(self, ts: pd.Timestamp) -> float:
        """Fractional trading days to expiry (expiry day 15:30 == 0)."""
        d = ts.date()
        exp = self.next_expiry(d)
        close_ = datetime.combine(exp, self.cfg.market_close)
        close_ts = pd.Timestamp(close_).tz_localize(IST)
        secs = (close_ts - ts).total_seconds()
        # count only trading sessions between
        days = 0
        cur = d + timedelta(days=1)
        while cur <= exp:
            if self.is_trading_day(cur):
                days += 1
            cur += timedelta(days=1)
        session_len = (datetime.combine(d, self.cfg.market_close) - datetime.combine(d, self.cfg.market_open)).total_seconds()
        today_frac = max(0.0, min(1.0, (datetime.combine(d, self.cfg.market_close) - ts.tz_localize(None).to_pydatetime()).total_seconds() / session_len))
        return days + today_frac if secs > 0 else 0.0

    def dte_array(self, index: pd.DatetimeIndex) -> np.ndarray:
        """Vectorised DTE for a bar index (same-day values share the expiry lookup)."""
        out = np.empty(len(index))
        cache: dict[date, date] = {}
        session_len = (datetime.combine(date.today(), self.cfg.market_close)
                       - datetime.combine(date.today(), self.cfg.market_open)).total_seconds()
        for i, ts in enumerate(index):
            d = ts.date()
            exp = cache.get(d)
            if exp is None:
                exp = self.next_expiry(d)
                cache[d] = exp
            days = 0
            cur = d + timedelta(days=1)
            while cur <= exp:
                if self.is_trading_day(cur):
                    days += 1
                cur += timedelta(days=1)
            rem = (datetime.combine(d, self.cfg.market_close) - ts.tz_localize(None).to_pydatetime()).total_seconds()
            out[i] = days + max(0.0, min(1.0, rem / session_len))
        return out


def in_window(t: time, start: time, end: time) -> bool:
    return start <= t <= end


def years_to_expiry(dte_trading_days: float) -> float:
    """Convert trading-day DTE to year fraction for option pricing (252 trading days)."""
    return max(dte_trading_days, 0.02) / 252.0
