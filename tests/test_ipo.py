import datetime as dt
from pathlib import Path

import httpx

from jpmarket.sources.ipo import _short_name, load_recent_ipos, parse_listings

HTML = (Path(__file__).parent / "fixtures" / "jpx_new_listings_sample.html").read_text(encoding="utf-8")


def test_parse_listings() -> None:
    ls = parse_listings(HTML)
    assert [(x.code, x.technical) for x in ls] == [
        ("648A", False),
        ("640A", True),
        ("641A", True),
        ("500A", False),
    ]
    assert ls[0].date == dt.date(2026, 10, 15) and ls[0].name == "ルクレ" and ls[0].market == "グロース"


def test_short_name() -> None:
    assert _short_name("（株）技術承継機構 代表者インタビュー") == "技術承継機構"
    assert _short_name("NOK Group（株） *") == "NOK Group"
    assert _short_name("株式会社ABC") == "ABC"


def test_load_recent_filters_future_and_technical(tmp_path: Path) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=HTML)))
    got = load_recent_ipos(tmp_path, today=dt.date(2026, 9, 25), client=client)
    assert got is not None and [x.code for x in got] == ["500A"]  # 648A lists in October; 640A/641A technical
    assert (tmp_path / "ipo" / "new_listings_2025.html").exists()  # last year's archive cached


def test_load_recent_unreachable(tmp_path: Path) -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    assert load_recent_ipos(tmp_path, today=dt.date(2026, 9, 25), client=client) is None
