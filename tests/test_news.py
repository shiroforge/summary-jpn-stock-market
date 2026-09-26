import datetime as dt
from pathlib import Path

import httpx

from jpmarket.config import FeedSpec, ThemeSpec
from jpmarket.news.rss import fetch_feeds, highlight, parse_feed, rank, select, tag

XML = (Path(__file__).parent / "fixtures" / "sample_feed.xml").read_bytes()
UTC = dt.UTC
THEMES = [
    ThemeSpec(key="banks", name="銀行", keywords=["日銀", "利上げ"], members={"8306": "MUFG"}),
    ThemeSpec(key="semi", name="半導体", keywords=["半導体"], members={"8035": "TEL"}),
]


def test_parse_google_style_source() -> None:
    items = parse_feed(XML, FeedSpec(name="Google News 株式", url="x"))
    assert items[0].title == "日銀、追加利上げを検討" and items[0].source == "テスト新聞"
    assert items[0].published_at == dt.datetime(2026, 9, 25, 5, 0, tzinfo=UTC)
    assert all(i.url.startswith("http") for i in items)  # item without link dropped
    other = parse_feed(XML, FeedSpec(name="NHK経済", url="x"))
    assert other[0].source == "NHK経済" and other[0].title.endswith("テスト新聞")


def test_filter() -> None:
    items = parse_feed(XML, FeedSpec(name="x", url="x", filter=["東証"]))
    assert [i.title for i in items] == ["半導体株が高い 東証"]  # whitespace normalized


def test_select_window_and_dedupe() -> None:
    items = parse_feed(XML, FeedSpec(name="Google News 株式", url="x"))
    got = select(
        items,
        since=dt.datetime(2026, 9, 24, 6, 30, tzinfo=UTC),
        until=dt.datetime(2026, 9, 25, 7, 30, tzinfo=UTC),
        max_items=10,
    )
    assert [i.url for i in got] == ["https://example.com/c", "https://example.com/b", "https://example.com/a"]


def test_tag_and_highlight() -> None:
    items = tag(parse_feed(XML, FeedSpec(name="Google News 株式", url="x")), THEMES)
    assert items[0].tags == ["banks"] and items[2].tags == ["semi"] and items[3].tags == []
    top = highlight(items, n=2)
    assert [i.url for i in top] == ["https://example.com/b", "https://example.com/a"]


def test_fetch_records_failures() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=XML) if "ok" in str(req.url) else httpx.Response(403)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    items, failed = fetch_feeds(
        [FeedSpec(name="A", url="https://ok/"), FeedSpec(name="B", url="https://ng/")], client=client
    )
    assert len(items) == 5 and failed == ["B"]


def test_rank_puts_relevant_first() -> None:
    items = tag(parse_feed(XML, FeedSpec(name="Google News 株式", url="x")), THEMES)
    ranked = rank(items)
    assert ranked[-1].title in ("週末の天気", "古いニュース")
    assert ranked[0].url == "https://example.com/b"


def test_strip_site_suffix() -> None:
    xml = (
        b'<?xml version="1.0"?><rss version="2.0"><channel><item><title>'
        + "見出しです | ライフ | 東洋経済オンライン".encode()
        + b"</title><link>https://example.com/x</link></item></channel></rss>"
    )
    assert parse_feed(xml, FeedSpec(name="東洋経済", url="x"))[0].title == "見出しです"
