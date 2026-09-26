"""TSE trading calendar: weekends, national holidays (jpholiday), and the 12/31-1/3 year-end closure."""

from __future__ import annotations

import datetime as dt

import jpholiday


def is_trading_day(d: dt.date) -> bool:
    if d.weekday() >= 5:
        return False
    if (d.month == 12 and d.day == 31) or (d.month == 1 and d.day <= 3):
        return False
    return not jpholiday.is_holiday(d)


def prev_trading_day(d: dt.date) -> dt.date:
    d -= dt.timedelta(days=1)
    while not is_trading_day(d):
        d -= dt.timedelta(days=1)
    return d


def next_trading_day(d: dt.date) -> dt.date:
    d += dt.timedelta(days=1)
    while not is_trading_day(d):
        d += dt.timedelta(days=1)
    return d


def trading_days_back(end: dt.date, n: int) -> list[dt.date]:
    """The n trading days ending at `end` (inclusive if `end` is a trading day), oldest first."""
    out: list[dt.date] = []
    d = end if is_trading_day(end) else prev_trading_day(end)
    while len(out) < n:
        out.append(d)
        d = prev_trading_day(d)
    return out[::-1]


def latest_trading_day(now: dt.datetime, close_hour_jst: int = 15, close_minute: int = 30) -> dt.date:
    """Most recent trading day whose close has passed at `now` (tz-aware)."""
    jst = now.astimezone(dt.timezone(dt.timedelta(hours=9)))
    d = jst.date()
    closed = (jst.hour, jst.minute) >= (close_hour_jst, close_minute)
    if is_trading_day(d) and closed:
        return d
    return prev_trading_day(d)
