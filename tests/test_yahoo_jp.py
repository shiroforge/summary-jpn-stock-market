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
