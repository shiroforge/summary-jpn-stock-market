import datetime as dt
from pathlib import Path

import httpx
import pytest

from jpmarket.sources.yahoo_jp import fetch_index_close, parse_index_page

HTML = (Path(__file__).parent / "fixtures" / "yahoo_jp_topix.html").read_text(encoding="utf-8")


def _client(text: str, status: int = 200) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(status, text=text)))


def test_parse() -> None:
    p = parse_index_page(HTML, year=2026)
    assert p is not None
    assert p.date == dt.date(2026, 9, 25)
    assert p.close == 4128.59 and p.prev_close == 4075.30
    assert p.change_pct == pytest.approx(1.31, abs=0.005)


def test_fetch_checks_date() -> None:
    assert fetch_index_close(dt.date(2026, 9, 25), client=_client(HTML)) is not None
    assert fetch_index_close(dt.date(2026, 9, 28), client=_client(HTML)) is None


def test_fetch_failures_return_none() -> None:
    assert fetch_index_close(dt.date(2026, 9, 25), client=_client("", 503)) is None
    assert fetch_index_close(dt.date(2026, 9, 25), client=_client("<html>changed</html>")) is None


STOCK = (Path(__file__).parent / "fixtures" / "yahoo_jp_stock_sample.html").read_text(encoding="utf-8")


def test_parse_stock_page_with_pts() -> None:
    from jpmarket.sources.yahoo_jp import JST, parse_stock_page

    q = parse_stock_page(STOCK, year=2026)
    assert q is not None
    assert q.close == 6885 and q.change_pct == 16.99 and q.limit == "S高"
    assert q.pts_price == 6870 and q.pts_time == dt.datetime(2026, 9, 25, 23, 58, tzinfo=JST)


def test_parse_stock_page_without_pts() -> None:
    from jpmarket.sources.yahoo_jp import parse_stock_page

    html = STOCK.replace('ptsPrice\\":\\"6,870', 'ptsPrice\\":\\"$undefined').replace(
        "ストップ高", "$undefined"
    )
    q = parse_stock_page(html, year=2026)
    assert q is not None and q.pts_price is None and q.pts_time is None and q.limit is None
    assert parse_stock_page("<html>changed</html>", year=2026) is None


def test_stock_client_stops_when_blocked() -> None:
    from jpmarket.sources.yahoo_jp import YahooStockClient

    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return httpx.Response(403)

    yc = YahooStockClient(httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    assert yc.quote("4967", year=2026) is None and yc.quote("7203", year=2026) is None
    assert yc.blocked and len(calls) == 1


HIST = (Path(__file__).parent / "fixtures" / "yahoo_jp_topix_history.html").read_text(encoding="utf-8")


def test_parse_history_and_quote_ohlc() -> None:
    from jpmarket.sources.yahoo_jp import parse_history

    rows = parse_history(HIST)
    assert len(rows) == 20
    assert rows[0] == (dt.date(2026, 9, 25), 4092.19, 4132.11, 4089.19, 4128.59)
    q = parse_index_page(HTML, year=2026)
    assert q is not None and (q.open, q.high, q.low) == (4092.19, 4132.11, 4089.19)


def test_fetch_history_stops_at_since() -> None:
    from jpmarket.sources.yahoo_jp import fetch_index_history

    pages: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        pages.append(str(req.url))
        return httpx.Response(200, text=HIST)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    rows = fetch_index_history("998405.T", since=dt.date(2026, 9, 1), client=client, sleep=lambda s: None)
    assert len(pages) == 1 and len(rows) == 20  # page 1 already reaches back past `since`
    rows = fetch_index_history(
        "998405.T", since=dt.date(2026, 1, 1), client=client, max_pages=3, sleep=lambda s: None
    )
    assert len(pages) == 4
