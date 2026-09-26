import datetime as dt

from jpmarket.calendar import (
    is_trading_day,
    latest_trading_day,
    next_trading_day,
    prev_trading_day,
    trading_days_back,
)

D = dt.date


def test_weekend_and_holidays() -> None:
    assert is_trading_day(D(2026, 9, 25))  # Fri
    assert not is_trading_day(D(2026, 9, 26))  # Sat
    assert not is_trading_day(D(2026, 9, 21))  # 敬老の日
    assert not is_trading_day(D(2026, 9, 22))  # 国民の休日 (between 敬老の日 and 秋分の日)
    assert not is_trading_day(D(2026, 9, 23))  # 秋分の日
    assert not is_trading_day(D(2026, 5, 6))  # 振替休日
    assert not is_trading_day(D(2025, 12, 31))
    assert not is_trading_day(D(2026, 1, 2))
    assert is_trading_day(D(2026, 1, 5))


def test_prev_next() -> None:
    assert prev_trading_day(D(2026, 9, 24)) == D(2026, 9, 18)  # across the silver week
    assert next_trading_day(D(2026, 9, 18)) == D(2026, 9, 24)
    assert next_trading_day(D(2025, 12, 30)) == D(2026, 1, 5)


def test_trading_days_back() -> None:
    days = trading_days_back(D(2026, 9, 27), 3)
    assert days == [D(2026, 9, 18), D(2026, 9, 24), D(2026, 9, 25)]


def test_latest_trading_day() -> None:
    jst = dt.timezone(dt.timedelta(hours=9))
    assert latest_trading_day(dt.datetime(2026, 9, 25, 16, 0, tzinfo=jst)) == D(2026, 9, 25)
    assert latest_trading_day(dt.datetime(2026, 9, 25, 15, 0, tzinfo=jst)) == D(2026, 9, 24)
    assert latest_trading_day(dt.datetime(2026, 9, 27, 10, 0, tzinfo=jst)) == D(2026, 9, 25)
