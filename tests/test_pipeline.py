import datetime as dt
import math
from pathlib import Path

import httpx
import pandas as pd
import pytest

from jpmarket.calendar import is_trading_day
from jpmarket.config import Settings
from jpmarket.models import NewsItem
from jpmarket.pipeline import Deps, StaleDataError, build_summary, save_summary
from jpmarket.render.site import build_site, load_all
from jpmarket.sources.master import parse_topixweight
from jpmarket.sources.yahoo_jp import IndexClose

FIX = Path(__file__).parent / "fixtures"
D = dt.date
T = D(2026, 9, 25)


class FakeSource:
    """Deterministic bars for every requested symbol on every trading day up to `last_day`."""

    name = "fake"

    def __init__(self, last_day: dt.date = T) -> None:
        self.last_day = last_day

    def daily_bars(self, symbols: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        rows = []
        d = start
        while d <= min(end, self.last_day):
            if is_trading_day(d):
                n = (d - D(2025, 1, 1)).days
                for i, s in enumerate(symbols):
                    close = 1000 + 50 * math.sin(n / 7 + i)
                    rows.append(
                        {
                            "symbol": s,
                            "date": d,
                            "open": close,
                            "high": close,
                            "low": close,
                            "close": close,
                            "volume": 2e6,
                        }
                    )
            d += dt.timedelta(days=1)
        return pd.DataFrame(rows)


def settings(tmp: Path) -> Settings:
    return Settings(data_dir=tmp / "data", cache_dir=tmp / "cache", site_dir=tmp / "site")


def deps(source: FakeSource, topix: IndexClose | None) -> Deps:
    news = [
        NewsItem(
            title="日銀、利上げを示唆",
            url="https://example.com/1",
            source="t",
            published_at=dt.datetime(2026, 9, 25, 3, 0, tzinfo=dt.UTC),
        )
    ]
    return Deps(
        source=source,
        http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500))),
        now=dt.datetime(2026, 9, 25, 7, 40, tzinfo=dt.UTC),
        master=parse_topixweight((FIX / "topixweight_sample.csv").read_bytes()),
        topix=topix,
        news=news,
    )


def test_build_with_official_topix(tmp_path: Path) -> None:
    s = build_summary(T, settings(tmp_path), deps(FakeSource(), IndexClose(T, 4128.59, 4075.30)))
    tp = s.quote("topix")
    assert tp is not None and not tp.is_proxy
    assert tp.close == 4128.59 and tp.change_pct == pytest.approx(1.31, abs=0.01)
    assert len(tp.spark) == 20
    assert s.quote("nikkei225") is not None and s.quote("usdjpy") is not None
    assert s.sectors and len(s.sector17_etfs) == 17
    assert s.themes and all(t.count > 0 for t in s.themes)
    assert s.breadth is not None and s.breadth.total > 0
    assert s.news and s.news[0].tags == ["banks"]
    assert next(t for t in s.themes if t.key == "banks").news_count == 1
    assert s.comment.startswith("日経平均は")
    assert len(s.sector_history.dates) == 20
    assert any("Yahoo" in src for src in s.sources)


def test_topix_fallback_uses_previous_close(tmp_path: Path) -> None:
    st = settings(tmp_path)
    prev = build_summary(
        D(2026, 9, 24), st, deps(FakeSource(D(2026, 9, 24)), IndexClose(D(2026, 9, 24), 4000.0, 3990.0))
    )
    save_summary(prev, st.data_dir)
    s = build_summary(T, st, deps(FakeSource(), None))
    tp = s.quote("topix")
    assert tp is not None and tp.is_proxy
    assert any("推計値" in w for w in s.warnings)


def test_topix_missing_without_base(tmp_path: Path) -> None:
    s = build_summary(T, settings(tmp_path), deps(FakeSource(), None))
    assert s.quote("topix") is None
    assert any("TOPIX" in w for w in s.warnings)


def test_stale(tmp_path: Path) -> None:
    with pytest.raises(StaleDataError):
        build_summary(T, settings(tmp_path), deps(FakeSource(D(2026, 9, 24)), None))


def test_site(tmp_path: Path) -> None:
    st = settings(tmp_path)
    for d in (D(2026, 9, 24), T):
        save_summary(build_summary(d, st, deps(FakeSource(d), IndexClose(d, 4000.0, 3990.0))), st.data_dir)
    build_site(load_all(st.data_dir), st.site_dir)
    day = (st.site_dir / "2026-09-25" / "index.html").read_text(encoding="utf-8")
    assert 'href="../2026-09-24/"' in day and "翌営業日 →</span>" in day
    assert "2026-09-25" in (st.site_dir / "index.html").read_text(encoding="utf-8")
    assert "2026年9月24日" in (st.site_dir / "archive" / "index.html").read_text(encoding="utf-8")


class HolidayFxSource(FakeSource):
    """FX trades on JP holidays (e.g. 2026-09-21..23); stocks do not."""

    def daily_bars(self, symbols: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        df = super().daily_bars(symbols, start, end)
        extra = [
            {
                "symbol": "USDJPY=X",
                "date": d,
                "open": 150.0,
                "high": 150.0,
                "low": 150.0,
                "close": 150.0,
                "volume": 0.0,
            }
            for d in (D(2026, 9, 21), D(2026, 9, 22), D(2026, 9, 23))
            if start <= d <= end and "USDJPY=X" in symbols
        ]
        return pd.concat([df, pd.DataFrame(extra)], ignore_index=True)


def test_histories_skip_jp_holidays(tmp_path: Path) -> None:
    s = build_summary(T, settings(tmp_path), deps(HolidayFxSource(), IndexClose(T, 4128.59, 4075.30)))
    assert all(is_trading_day(d) for d in s.sector_history.dates)
    assert all(is_trading_day(d) for d in s.theme_history.dates)
    assert all(v is not None for series in s.sector_history.series.values() for v in series[1:])
