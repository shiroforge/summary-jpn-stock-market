import datetime as dt
from pathlib import Path

import httpx

from jpmarket.models import Disclosure
from jpmarket.news.tdnet import BASE, classify, fetch_day, notable, parse_list, window

HTML = (Path(__file__).parent / "fixtures" / "tdnet_list_sample.html").read_text(encoding="utf-8")
D = dt.date(2026, 9, 25)
JST = dt.timezone(dt.timedelta(hours=9))


def test_parse_real_rows() -> None:
    items = parse_list(HTML, D)
    assert len(items) == 4
    first = items[0]
    assert first.code == "464A" and first.name == "Ｇ－ＱＰＳＨＤ"
    assert first.time == dt.datetime(2026, 9, 25, 18, 30, tzinfo=JST)
    assert first.url == BASE + "140120260925540309.pdf"
    orch = next(i for i in items if i.code == "6533")
    assert "増配" in orch.tags and "株主優待" in orch.tags and orch.tone == "pos"


def test_classify() -> None:
    assert classify("業績予想の上方修正に関するお知らせ") == (["上方修正"], "pos")
    assert classify("通期業績予想の修正（下方修正）に関するお知らせ") == (["下方修正", "業績修正"], "neg")
    assert classify("自己株式取得に係る事項の決定に関するお知らせ")[0] == ["自社株買い"]
    assert classify("自己株式の取得状況に関するお知らせ")[0] == []  # progress report, not a new buyback
    assert classify("株式会社○○株式に対する公開買付けの開始に関するお知らせ")[0] == ["TOB・MBO"]
    assert classify("公開買付けの結果に関するお知らせ")[0] == []
    assert classify("当社に関する一部報道について")[0] == ["報道への回答"]
    assert classify("（訂正）決算短信の一部訂正について") == ([], "neutral")
    assert classify("第三者割当による新株式発行に関するお知らせ") == (["増資・希薄化"], "neg")
    # buyback funded by a convertible bond: mixed signals -> neutral tone, both tags shown
    assert classify("ユーロ円建転換社債(CB)発行及び自己株式取得に関するお知らせ") == (
        ["自社株買い", "増資・希薄化"],
        "neutral",
    )


def test_fetch_paginates_and_stops() -> None:
    pages: list[str] = []
    full = HTML

    def handler(req: httpx.Request) -> httpx.Response:
        pages.append(req.url.path.rsplit("/", 1)[-1])
        if "I_list_001" in str(req.url):
            return httpx.Response(200, text=full)
        return httpx.Response(404)

    items = fetch_day(D, client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    assert items is not None and len(items) == 4
    assert pages == ["I_list_001_20260925.html"]  # fewer than 100 rows -> no further pages


def test_fetch_failure_returns_none() -> None:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(503)))
    assert fetch_day(D, client=client, sleep=lambda s: None) is None


def _d(code: str, hhmm: str, tags: list[str], day: dt.date = D) -> Disclosure:
    h, m = map(int, hhmm.split(":"))
    return Disclosure(
        code=code,
        name=code,
        time=dt.datetime.combine(day, dt.time(h, m), JST),
        title="t",
        url=f"https://x/{code}{hhmm}",
        tags=tags,
    )


def test_window_and_notable() -> None:
    items = [
        _d("1111", "15:30", ["決算"]),
        _d("2222", "15:29", ["上方修正"]),
        _d("3333", "15:40", []),
        _d("4444", "16:00", ["増配"]),
        _d("5555", "15:31", ["自社株買い"], dt.date(2026, 9, 24)),
    ]
    close = dt.datetime(2026, 9, 25, 15, 30, tzinfo=JST)
    prev_close = dt.datetime(2026, 9, 24, 15, 30, tzinfo=JST)
    session = window(items, prev_close, close)
    after = window(items, close, close + dt.timedelta(hours=9))
    assert [d.code for d in session] == ["2222", "5555"]
    assert [d.code for d in after] == ["4444", "3333", "1111"]  # 15:30 releases count as after the close
    ranked = notable(after, {"1111": 2.0, "4444": 0.1})
    assert [d.code for d in ranked] == ["1111", "4444"]  # untagged dropped; bigger TOPIX weight first
