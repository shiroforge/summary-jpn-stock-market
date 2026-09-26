"""Generate a deterministic *dummy* DailySummary for design mocks and render tests.

Run: uv run python tests/fixtures/make_sample.py  ->  tests/fixtures/sample_summary.json
Values are fake (seeded random); names/structure are realistic.
"""

from __future__ import annotations

import datetime as dt
import random
from pathlib import Path

import yaml

from jpmarket.models import (
    Breadth,
    DailySummary,
    NewsItem,
    Quote,
    QuoteCategory,
    Rankings,
    SectorPerf,
    SeriesHistory,
    StockMove,
    ThemePerf,
)

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("sample_summary.json")
DATE = dt.date(2026, 9, 25)

SECTORS33 = [
    ("水産・農林業", 0.1),
    ("鉱業", 0.3),
    ("建設業", 2.1),
    ("食料品", 3.3),
    ("繊維製品", 0.5),
    ("パルプ・紙", 0.2),
    ("化学", 5.6),
    ("医薬品", 4.4),
    ("石油・石炭製品", 0.4),
    ("ゴム製品", 0.6),
    ("ガラス・土石製品", 0.7),
    ("鉄鋼", 0.8),
    ("非鉄金属", 1.2),
    ("金属製品", 0.6),
    ("機械", 6.0),
    ("電気機器", 17.5),
    ("輸送用機器", 7.4),
    ("精密機器", 2.4),
    ("その他製品", 2.3),
    ("電気・ガス業", 1.3),
    ("陸運業", 2.8),
    ("海運業", 0.6),
    ("空運業", 0.4),
    ("倉庫・運輸関連業", 0.2),
    ("情報・通信業", 8.1),
    ("卸売業", 6.9),
    ("小売業", 4.4),
    ("銀行業", 9.2),
    ("証券、商品先物取引業", 1.0),
    ("保険業", 3.5),
    ("その他金融業", 1.3),
    ("不動産業", 2.0),
    ("サービス業", 3.9),
]

STOCKS = [
    ("8306", "三菱UFJ", "銀行業"),
    ("8316", "三井住友FG", "銀行業"),
    ("8411", "みずほFG", "銀行業"),
    ("8035", "東京エレクトロン", "電気機器"),
    ("6857", "アドバンテスト", "電気機器"),
    ("6758", "ソニーG", "電気機器"),
    ("7203", "トヨタ", "輸送用機器"),
    ("9984", "ソフトバンクG", "情報・通信業"),
    ("9432", "NTT", "情報・通信業"),
    ("8058", "三菱商事", "卸売業"),
    ("7011", "三菱重工", "機械"),
    ("6501", "日立", "電気機器"),
    ("4063", "信越化学", "化学"),
    ("8766", "東京海上", "保険業"),
    ("5803", "フジクラ", "非鉄金属"),
    ("6146", "ディスコ", "機械"),
    ("3778", "さくらインターネット", "情報・通信業"),
    ("9101", "日本郵船", "海運業"),
    ("4568", "第一三共", "医薬品"),
    ("8801", "三井不動産", "不動産業"),
    ("7974", "任天堂", "その他製品"),
    ("6920", "レーザーテック", "電気機器"),
    ("5401", "日本製鉄", "鉄鋼"),
    ("9501", "東京電力HD", "電気・ガス業"),
]


def spark(rng: random.Random, start: float, n: int = 20, vol: float = 0.01) -> list[float]:
    out = [start]
    for _ in range(n - 1):
        out.append(round(out[-1] * (1 + rng.gauss(0.0008, vol)), 2))
    return out


def quote(
    rng: random.Random,
    key: str,
    name: str,
    ticker: str,
    cat: QuoteCategory,
    level: float,
    vol: float = 0.01,
    *,
    proxy: bool = False,
    unit: str = "",
    as_of: dt.date = DATE,
) -> Quote:
    s = spark(rng, level, 21, vol)
    close, prev = s[-1], s[-2]
    return Quote(
        key=key,
        name=name,
        ticker=ticker,
        category=cat,
        close=close,
        change=round(close - prev, 2),
        change_pct=round((close / prev - 1) * 100, 2),
        change_5d_pct=round((close / s[-6] - 1) * 100, 2),
        change_20d_pct=round((close / s[0] - 1) * 100, 2),
        change_5d=round(close - s[-6], 4),
        change_20d=round(close - s[0], 4),
        spark=s[1:],
        as_of=as_of,
        is_proxy=proxy,
        unit=unit,
    )


def move(rng: random.Random, code: str, name: str, sector: str, pct: float | None = None) -> StockMove:
    return StockMove(
        code=code,
        name=name,
        sector33=sector,
        close=round(rng.uniform(300, 30000), 0),
        change_pct=round(pct if pct is not None else rng.gauss(0.5, 2.5), 2),
        turnover=round(rng.uniform(2e10, 4e11), -8),
        volume=round(rng.uniform(5e5, 8e7), -3),
        volume_ratio=round(rng.uniform(0.5, 4.5), 2),
    )


def main() -> None:
    rng = random.Random(20260925)
    us_date = DATE - dt.timedelta(days=1)
    quotes = [
        quote(rng, "nikkei225", "日経平均", "^N225", QuoteCategory.DOMESTIC, 65400, 0.012),
        quote(rng, "topix", "TOPIX", "998405.T", QuoteCategory.DOMESTIC, 4075, 0.009),
        quote(rng, "growth250", "グロース250", "2516.T", QuoteCategory.DOMESTIC, 640, 0.015, proxy=True),
        quote(rng, "jpx400", "JPX日経400", "1591.T", QuoteCategory.DOMESTIC, 36500, 0.009, proxy=True),
        quote(rng, "nk_futures", "日経平均先物(CME)", "NIY=F", QuoteCategory.FUTURES_VOL, 65600, 0.012),
        quote(rng, "nikkei_vi", "日経VI", "^NKVI.OS", QuoteCategory.FUTURES_VOL, 21.0, 0.04),
        quote(rng, "usdjpy", "ドル円", "USDJPY=X", QuoteCategory.FX, 156.8, 0.004, unit="円"),
        quote(rng, "eurjpy", "ユーロ円", "EURJPY=X", QuoteCategory.FX, 178.9, 0.004, unit="円"),
        quote(rng, "sp500", "S&P500", "^GSPC", QuoteCategory.OVERSEAS, 7700, 0.008, as_of=us_date),
        quote(rng, "nasdaq", "NASDAQ", "^IXIC", QuoteCategory.OVERSEAS, 26900, 0.011, as_of=us_date),
        quote(rng, "dow", "NYダウ", "^DJI", QuoteCategory.OVERSEAS, 51600, 0.007, as_of=us_date),
        quote(rng, "sox", "SOX指数", "^SOX", QuoteCategory.OVERSEAS, 12500, 0.018, as_of=us_date),
        quote(rng, "vix", "VIX", "^VIX", QuoteCategory.OVERSEAS, 15.2, 0.05, as_of=us_date),
        quote(rng, "wti", "WTI原油", "CL=F", QuoteCategory.COMMODITY, 91.5, 0.015, as_of=us_date),
        quote(rng, "gold", "金", "GC=F", QuoteCategory.COMMODITY, 4300, 0.008, as_of=us_date),
        quote(rng, "jgb1y", "日本 1年", "1年", QuoteCategory.RATES, 1.62, 0.004, unit="%", as_of=us_date),
        quote(rng, "jgb2y", "日本 2年", "2年", QuoteCategory.RATES, 1.91, 0.004, unit="%", as_of=us_date),
        quote(rng, "jgb10y", "日本 10年", "10年", QuoteCategory.RATES, 3.07, 0.004, unit="%", as_of=us_date),
        quote(rng, "jgb30y", "日本 30年", "30年", QuoteCategory.RATES, 4.11, 0.004, unit="%", as_of=us_date),
        quote(rng, "ust2y", "米国 2年", "DGS2", QuoteCategory.RATES, 4.87, 0.006, unit="%", as_of=us_date),
        quote(rng, "us10y", "米国 10年", "^TNX", QuoteCategory.RATES, 5.18, 0.006, unit="%", as_of=us_date),
    ]

    by_sector = {s: [st for st in STOCKS if st[2] == s] for s, _ in SECTORS33}
    sectors = []
    for name, weight in SECTORS33:
        pct = round(rng.gauss(0.8, 1.1) + (3.0 if name == "銀行業" else 0), 2)
        cnt = rng.randint(8, 150)
        adv = max(0, min(cnt, int(cnt * (0.5 + pct / 8) + rng.randint(-3, 3))))
        members = [move(rng, c, n, s, pct + rng.gauss(0, 1.2)) for c, n, s in by_sector.get(name, [])]
        members.sort(key=lambda m: m.change_pct, reverse=True)
        sectors.append(
            SectorPerf(
                name=name,
                change_pct=pct,
                median_pct=round(pct + rng.gauss(0, 0.3), 2),
                advancers=adv,
                decliners=cnt - adv,
                count=cnt,
                topix_weight_pct=weight,
                leaders=members[:3],
                laggards=list(reversed(members[-2:])) if len(members) > 3 else [],
            )
        )
    sectors.sort(key=lambda s: s.change_pct, reverse=True)

    etf_cfg = yaml.safe_load((ROOT / "config/indices.yaml").read_text())["sector17_etfs"]
    etfs = [
        quote(
            rng,
            f"etf{e['code']}",
            e["name"],
            f"{e['code']}.T",
            QuoteCategory.DOMESTIC,
            rng.uniform(20000, 60000),
            0.011,
            proxy=True,
        )
        for e in etf_cfg
    ]

    themes_cfg = yaml.safe_load((ROOT / "config/themes.yaml").read_text())["themes"]
    themes = []
    for t in themes_cfg:
        base = rng.gauss(0.6, 1.6) + (2.5 if t["key"] == "banks" else 0)
        members = [move(rng, c, n, None, base + rng.gauss(0, 1.5)) for c, n in t["members"].items()]
        members.sort(key=lambda m: m.change_pct, reverse=True)
        avg = sum(m.change_pct for m in members) / len(members)
        themes.append(
            ThemePerf(
                key=t["key"],
                name=t["name"],
                change_pct=round(avg, 2),
                advancers_ratio=round(sum(m.change_pct > 0 for m in members) / len(members), 2),
                count=len(members),
                members=members,
                news_count=rng.randint(0, 5),
            )
        )
    themes.sort(key=lambda t: t.change_pct, reverse=True)

    movers = [move(rng, c, n, s) for c, n, s in STOCKS]
    rankings = Rankings(
        gainers=sorted(movers, key=lambda m: m.change_pct, reverse=True)[:10],
        losers=sorted(movers, key=lambda m: m.change_pct)[:10],
        turnover=sorted(movers, key=lambda m: m.turnover or 0, reverse=True)[:10],
        volume_surge=sorted(movers, key=lambda m: m.volume_ratio or 0, reverse=True)[:10],
    )

    news = [
        NewsItem(
            title="日銀、年内の追加利上げを示唆　植田総裁が講演",
            url="https://example.com/n1",
            source="NHK経済",
            published_at=dt.datetime(2026, 9, 25, 14, 10, tzinfo=dt.UTC) - dt.timedelta(hours=9),
            tags=["banks"],
        ),
        NewsItem(
            title="米エヌビディア決算、データセンター売上が過去最高",
            url="https://example.com/n2",
            source="Google News 株式",
            published_at=dt.datetime(2026, 9, 25, 6, 30, tzinfo=dt.UTC),
            tags=["semiconductor", "ai_datacenter"],
        ),
        NewsItem(
            title="防衛装備品の輸出ルール見直しへ　政府が検討",
            url="https://example.com/n3",
            source="日経速報",
            published_at=dt.datetime(2026, 9, 25, 3, 5, tzinfo=dt.UTC),
            tags=["defense"],
        ),
        NewsItem(
            title="訪日客数、8月として過去最多を更新",
            url="https://example.com/n4",
            source="Yahoo!ニュース経済",
            published_at=dt.datetime(2026, 9, 25, 7, 45, tzinfo=dt.UTC),
            tags=["inbound"],
        ),
        NewsItem(
            title="原油先物が続伸、中東情勢の緊迫で",
            url="https://example.com/n5",
            source="Yahoo!ニュース国際",
            published_at=dt.datetime(2026, 9, 25, 1, 20, tzinfo=dt.UTC),
            tags=[],
        ),
        NewsItem(
            title="東証大引け　反発、銀行株が高い　日経平均は3日ぶり最高値",
            url="https://example.com/n6",
            source="日経速報",
            published_at=dt.datetime(2026, 9, 25, 6, 20, tzinfo=dt.UTC),
            tags=["banks"],
        ),
    ]

    dates: list[dt.date] = []
    d = DATE
    while len(dates) < 20:
        if d.weekday() < 5:
            dates.append(d)
        d -= dt.timedelta(days=1)
    dates.reverse()
    sector_hist = SeriesHistory(
        dates=dates,
        series={
            s.name: [round(rng.gauss(0.05, 1.2), 2) for _ in dates[:-1]] + [s.change_pct] for s in sectors
        },
    )
    theme_hist = SeriesHistory(
        dates=dates,
        series={t.key: [round(rng.gauss(0.05, 1.6), 2) for _ in dates[:-1]] + [t.change_pct] for t in themes},
    )

    total_adv = sum(s.advancers for s in sectors)
    total_dec = sum(s.decliners for s in sectors)
    summary = DailySummary(
        date=DATE,
        generated_at=dt.datetime(2026, 9, 25, 7, 42, tzinfo=dt.UTC),
        sources=["yfinance", "JPX TOPIX構成銘柄ウエイト (2026-07-31)", "Yahoo!ファイナンス", "RSS 各社"],
        warnings=["【ダミーデータ】デザイン確認用のサンプルです。数値は実在の相場ではありません。"],
        comment=(
            f"日経平均は{quotes[0].change_pct:+.2f}%、TOPIXは{quotes[1].change_pct:+.2f}%。"
            f"{sectors[0].name}・{sectors[1].name}が上昇を主導し、{sectors[-1].name}が最も弱い。"
            f"テーマでは「{themes[0].name}」が強い。"
        ),
        quotes=quotes,
        sectors=sectors,
        sectors_official=False,
        sector17_etfs=etfs,
        themes=themes,
        breadth=Breadth(
            advancers=total_adv,
            decliners=total_dec,
            unchanged=41,
            total=total_adv + total_dec + 41,
            adv_dec_ratio_25d=112.4,
            new_highs=87,
            new_lows=6,
        ),
        rankings=rankings,
        news=news,
        sector_history=sector_hist,
        theme_history=theme_hist,
    )
    OUT.write_text(summary.model_dump_json(indent=1), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
