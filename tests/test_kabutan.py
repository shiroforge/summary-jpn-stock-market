import datetime as dt
from pathlib import Path

import httpx

from jpmarket.sources.kabutan import JST, KabutanClient, parse_quote

HTML = (Path(__file__).parent / "fixtures" / "kabutan_quote_sample.html").read_text(encoding="utf-8")


def test_parse_quote() -> None:
    q = parse_quote(HTML, year=2026)
    assert q is not None
    assert q.close == 6885 and q.change_pct == 16.99 and q.limit == "S高"
    assert q.pts_price == 6870 and q.pts_time == dt.datetime(2026, 9, 25, 23, 58, tzinfo=JST)


def test_parse_without_pts() -> None:
    html = HTML.split('<div class="si_i1_3">')[0]
    q = parse_quote(html, year=2026)
    assert q is not None and q.pts_price is None and q.pts_time is None
    assert parse_quote("<html>changed layout</html>", year=2026) is None


def test_client_pauses_between_calls_and_handles_errors() -> None:
    sleeps: list[float] = []
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return httpx.Response(200, text=HTML) if "4967" in str(req.url) else httpx.Response(500)

    kc = KabutanClient(httpx.Client(transport=httpx.MockTransport(handler)), pause=1.5, sleep=sleeps.append)
    assert kc.quote("4967", year=2026) is not None
    assert kc.quote("1234", year=2026) is None
    assert sleeps == [1.5] and len(calls) == 2
