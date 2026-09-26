import datetime as dt
from pathlib import Path

import pandas as pd

from jpmarket.sources.price_store import PriceStore

D = dt.date


class FakeSource:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[list[str], dt.date, dt.date]] = []

    def daily_bars(self, symbols: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        self.calls.append((list(symbols), start, end))
        rows = []
        for s in symbols:
            d = start
            while d <= end:
                if d.weekday() < 5:
                    rows.append(
                        {
                            "symbol": s,
                            "date": d,
                            "open": 1.0,
                            "high": 1.0,
                            "low": 1.0,
                            "close": 100.0 + d.day,
                            "volume": 10.0,
                        }
                    )
                d += dt.timedelta(days=1)
        return pd.DataFrame(rows)


def test_bootstrap_then_incremental(tmp_path: Path) -> None:
    src = FakeSource()
    store = PriceStore(tmp_path / "bars.parquet")
    missing = store.update(src, ["7203", "6758"], D(2026, 9, 24))
    assert missing == []
    assert src.calls[0][1] == D(2025, 12, 22)  # Jan 1 minus 10 days (older than 90 days back)
    store.save()

    store2 = PriceStore(tmp_path / "bars.parquet")
    src2 = FakeSource()
    store2.update(src2, ["7203", "6758", "9984"], D(2026, 9, 25))
    (known, start, _), (fresh, fresh_start, _) = src2.calls
    assert known == ["7203", "6758"] and start == D(2026, 9, 17)
    assert fresh == ["9984"] and fresh_start == D(2025, 12, 22)
    closes = store2.closes(["7203"])
    assert closes.index[-1] == D(2026, 9, 25)
    assert not closes.index.duplicated().any()


def test_reports_missing_target(tmp_path: Path) -> None:
    store = PriceStore(tmp_path / "bars.parquet")
    assert store.update(FakeSource(), ["7203"], D(2026, 9, 26)) == ["7203"]  # Saturday: no bar
