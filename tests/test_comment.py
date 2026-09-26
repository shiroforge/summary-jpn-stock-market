import datetime as dt

from jpmarket.analytics.comment import market_comment
from jpmarket.models import Breadth, Quote, QuoteCategory, SectorPerf, ThemePerf


def q(name: str, pct: float) -> Quote:
    return Quote(
        key=name,
        name=name,
        ticker=name,
        category=QuoteCategory.DOMESTIC,
        close=1,
        change=0,
        change_pct=pct,
        as_of=dt.date(2026, 9, 25),
    )


def sec(name: str, pct: float) -> SectorPerf:
    return SectorPerf(
        name=name, change_pct=pct, median_pct=pct, advancers=0, decliners=0, count=1, topix_weight_pct=1
    )


def th(name: str, pct: float) -> ThemePerf:
    return ThemePerf(key=name, name=name, change_pct=pct, advancers_ratio=0.5, count=2)


def br(adv: int, dec: int) -> Breadth:
    return Breadth(advancers=adv, decliners=dec, unchanged=0, total=adv + dec)


def test_broad_rally() -> None:
    c = market_comment(
        q("日経平均", 2.1),
        q("TOPIX", 1.8),
        [sec("銀行業", 3), sec("鉄鋼", 2), sec("鉱業", 1)],
        [th("銀行", 3), th("防衛", 1)],
        br(90, 10),
    )
    assert c.startswith("日経平均は+2.10%、TOPIXは+1.80%。値上がり銘柄が90%を占める全面高。")
    assert "銀行業・鉄鋼が上昇を主導。" in c and "「銀行」(+3.00%)が強い" in c and "売られた" not in c


def test_mixed() -> None:
    c = market_comment(
        q("日経平均", 0.1),
        None,
        [sec("銀行業", 1), sec("化学", 0.2), sec("鉱業", -1.5)],
        [th("銀行", 1), th("宇宙", -2)],
        br(50, 50),
    )
    assert "銀行業・化学が上昇を主導し、鉱業が軟調。" in c and "「宇宙」(-2.00%)は売られた。" in c
    assert "全面" not in c


def test_broad_selloff() -> None:
    c = market_comment(
        q("日経平均", -2.5),
        q("TOPIX", -2.0),
        [sec("a", -0.5), sec("b", -1), sec("c", -3)],
        [th("x", -1)],
        br(10, 90),
    )
    assert "全面安" in c and "c・bの下げが目立つ。" in c and "強い" not in c
