import datetime as dt
import math
from pathlib import Path

import httpx
import pandas as pd
import pytest

from jpmarket.calendar import is_trading_day
from jpmarket.config import Settings
from jpmarket.models import Disclosure, NewsItem
from jpmarket.pipeline import Deps, StaleDataError, build_summary, save_summary
from jpmarket.render.builder import render_daily
from jpmarket.render.site import build_site, load_all
from jpmarket.sources.ipo import Listing
from jpmarket.sources.master import parse_topixweight
from jpmarket.sources.yahoo_jp import IndexClose, StockQuote

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


JST = dt.timezone(dt.timedelta(hours=9))
DISCLOSURES = [
    Disclosure(
        code="8306",
        name="三菱ＵＦＪ",
        time=dt.datetime(2026, 9, 25, 12, 0, tzinfo=JST),
        title="業績予想の上方修正に関するお知らせ",
        url="https://x/1.pdf",
        tags=["上方修正"],
        tone="pos",
    ),
    Disclosure(
        code="8306",
        name="三菱ＵＦＪ",
        time=dt.datetime(2026, 9, 25, 15, 30, tzinfo=JST),
        title="自己株式取得に係る事項の決定に関するお知らせ",
        url="https://x/2.pdf",
        tags=["自社株買い"],
    ),
    Disclosure(
        code="9999",
        name="X",
        time=dt.datetime(2026, 9, 25, 16, 10, tzinfo=JST),
        title="株主総会の招集",
        url="https://x/3.pdf",
        tags=[],
    ),
]


PTS = {
    "8306": StockQuote(
        close=None,
        change_pct=None,
        limit="S高",
        pts_price=2000.0,
        pts_time=dt.datetime(2026, 9, 25, 21, 0, tzinfo=JST),
    )
}


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
        disclosures=DISCLOSURES,
        pts_lookup=lambda code: PTS.get(code),
        ipos=[
            Listing(
                date=dt.date(2026, 3, 2), code="0001", name="新規上場A", market="グロース", technical=False
            )
        ],
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
    ipo = next(t for t in s.themes if t.key == "ipo")  # dynamic theme filled from the injected listings
    assert [m.code for m in ipo.members] == ["0001"] and ipo.members[0].name == "新規上場A"
    assert s.breadth is not None and s.breadth.total > 0
    assert s.news and s.news[0].tags == ["banks"]
    assert next(t for t in s.themes if t.key == "banks").news_count == 1
    assert s.comment.startswith("日経平均は")
    assert len(s.sector_history.dates) == 20
    assert any("Yahoo" in src for src in s.sources)


def test_disclosures_attached(tmp_path: Path) -> None:
    d = deps(FakeSource(), IndexClose(T, 4128.59, 4075.30))
    d.now = dt.datetime(2026, 9, 25, 16, 30, tzinfo=JST)
    s = build_summary(T, settings(tmp_path), d)
    assert [x.url for x in s.disclosures_session] == ["https://x/1.pdf"]
    assert [x.url for x in s.disclosures_after] == ["https://x/2.pdf"]  # 15:30 counts as after the close
    assert s.disclosure_counts == {"session": 1, "after": 2, "pts_unavailable": 0}
    banks = next(t for t in s.themes if t.key == "banks")
    mufg = next(m for m in banks.members if m.code == "8306")
    assert [x.tags for x in mufg.disclosures] == [["上方修正"]]
    # price reaction: session disclosure -> that day's change; after-close -> PTS vs. the session close
    sess, aft = s.disclosures_session[0], s.disclosures_after[0]
    assert sess.move_basis == "day" and sess.move_pct == mufg.change_pct
    assert aft.move_basis == "pts" and aft.limit == "S高" and aft.pts_price == 2000.0
    assert aft.move_pct == pytest.approx((2000.0 / mufg.close - 1) * 100, abs=0.01)


def test_pts_before_close_is_ignored(tmp_path: Path) -> None:
    d = deps(FakeSource(), IndexClose(T, 4128.59, 4075.30))
    d.now = dt.datetime(2026, 9, 25, 16, 30, tzinfo=JST)
    d.pts_lookup = lambda code: StockQuote(
        close=1000.0,
        change_pct=1.0,
        limit=None,
        pts_price=1010.0,
        pts_time=dt.datetime(2026, 9, 25, 15, 10, tzinfo=JST),
    )
    aft = build_summary(T, settings(tmp_path), d).disclosures_after[0]
    assert aft.move_basis == "pts" and aft.move_pct is None and aft.pts_price is None


def test_pts_unavailable_flag(tmp_path: Path) -> None:
    d = deps(FakeSource(), IndexClose(T, 4128.59, 4075.30))
    d.now = dt.datetime(2026, 9, 25, 16, 30, tzinfo=JST)
    d.pts_lookup = lambda code: None  # e.g. blocked from the CI network
    s = build_summary(T, settings(tmp_path), d)
    assert s.disclosure_counts["pts_unavailable"] == 1
    html = render_daily(s)
    assert "今回はPTSの価格を取得できませんでした" in html and "finance.yahoo.co.jp/quote/8306.T" in html


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


def test_chart_payload(tmp_path: Path) -> None:
    from jpmarket.pipeline import build

    res = build(T, settings(tmp_path), deps(FakeSource(), IndexClose(T, 4128.59, 4075.30)))
    summary, charts = res.summary, res.charts
    assert res.trends["sectors"] and res.trends["dates"][-1] == "2026-09-25"
    s = charts["series"]
    assert charts["asof"] == "2026-09-25"
    code = summary.rankings.turnover[0].code
    assert s[code]["kind"] == "ohlc" and len(s[code]["dt"]) + 1 == len(s[code]["c"]) == len(s[code]["v"])
    assert s[code]["t0"] < "2026-09-25" and all(d >= 1 for d in s[code]["dt"])
    assert "株探" in s[code]["links"]
    assert s["q:nikkei225"]["kind"] == "ohlc" and "TradingView" in s["q:nikkei225"]["links"]
    assert s["q:topix"]["kind"] == "line" and s["q:topix"]["c"][-1] == 4128.59
    assert s["q:us10y"]["kind"] == "line" and s["q:us10y"]["unit"] == "%"
    for sid, ser in s.items():  # every series uses the compact date encoding, aligned with values
        assert "t" not in ser and len(ser["dt"]) + 1 == len(ser["c"]), sid
    assert s["s:" + summary.sectors[0].name]["c"][0] == 100
    assert "t:banks" in s


def test_early_attempt_waits_for_complete_data(tmp_path: Path) -> None:
    st = settings(tmp_path)
    early = deps(FakeSource(), None)
    early.final = False
    with pytest.raises(StaleDataError, match="TOPIX"):
        build_summary(T, st, early)  # official TOPIX not out yet -> retry later
    final = deps(FakeSource(), None)
    assert build_summary(T, st, final).quote("topix") is None  # last attempt builds with a warning


class PartialSource(FakeSource):
    """Only half of the constituents have today's bar."""

    def daily_bars(self, symbols: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        df = super().daily_bars(symbols, start, end)
        late = set(symbols[::2]) - {"^N225"}
        return df[~((df["date"] == T) & df["symbol"].isin(late))]


def test_early_attempt_waits_for_coverage(tmp_path: Path) -> None:
    early = deps(PartialSource(), IndexClose(T, 4128.59, 4075.30))
    early.final = False
    with pytest.raises(StaleDataError, match="TOPIX weight"):
        build_summary(T, settings(tmp_path), early)
    s = build_summary(T, settings(tmp_path / "b"), deps(PartialSource(), IndexClose(T, 4128.59, 4075.30)))
    assert any("TOPIXウエイト" in w for w in s.warnings)
