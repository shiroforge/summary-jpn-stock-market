"""DailySummary: the single contract between the producer (collect/analyze) and consumers (render/notify).

Changing this schema is a design decision: bump SCHEMA_VERSION and record it in docs/DECISIONS.md.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, Field

SCHEMA_VERSION = (
    4  # v4: disclosure price reaction (v3: TDnet disclosures ; v2: rates, absolute 5d/20d changes, volume)
)


class QuoteCategory(StrEnum):
    DOMESTIC = "domestic"  # 国内指数
    FUTURES_VOL = "futures_vol"  # 先物・VI
    FX = "fx"  # 為替
    OVERSEAS = "overseas"  # 海外指数・金利
    COMMODITY = "commodity"  # 商品
    RATES = "rates"  # 金利（国債利回り）


class Quote(BaseModel):
    """An index / FX / commodity quote with short-term performance."""

    key: str  # stable id, e.g. "nikkei225"
    name: str  # display name, e.g. "日経平均"
    ticker: str  # source-specific symbol
    category: QuoteCategory
    close: float
    change: float  # vs previous close, in price units
    change_pct: float  # %
    change_5d_pct: float | None = None
    change_20d_pct: float | None = None
    change_5d: float | None = None  # absolute (price units; for yields: %pt, shown as bp)
    change_20d: float | None = None
    spark: list[float] = Field(default_factory=list)  # last ~20 closes, oldest first
    as_of: dt.date  # date of `close` (overseas markets may lag the JP date)
    is_proxy: bool = False  # True when an ETF etc. stands in for the index
    unit: str = ""  # e.g. "%" for yields, "円" for FX


class Disclosure(BaseModel):
    """A TDnet timely disclosure (title + PDF link only; the document itself is never stored)."""

    code: str  # 4-char TSE code
    name: str
    time: dt.datetime  # tz-aware (JST)
    title: str
    url: str
    tags: list[str] = Field(default_factory=list)  # categories, e.g. ["上方修正", "増配"]
    tone: str = "neutral"  # "pos" | "neg" | "neutral" (keyword-based, not investment advice)
    # price reaction: "day" = that session's close-to-close change; "pts" = PTS price vs. the session close
    move_pct: float | None = None
    move_basis: str | None = None  # "day" | "pts"
    pts_price: float | None = None
    pts_time: dt.datetime | None = None
    limit: str | None = None  # "S高" / "S安" when the session closed at the daily price limit


class StockMove(BaseModel):
    code: str  # 4-digit (or 4-char alnum) TSE code, e.g. "7203"
    name: str
    sector33: str | None = None
    close: float
    change_pct: float
    turnover: float | None = None  # 売買代金 (JPY), close * volume approximation
    volume: float | None = None  # 出来高 (shares)
    volume_ratio: float | None = None  # today's volume / average of the previous 20 sessions
    disclosures: list[Disclosure] = Field(
        default_factory=list
    )  # since the previous close (explains the move)


class SectorPerf(BaseModel):
    """TOPIX 33-sector performance (estimated from constituents unless official=True)."""

    name: str  # e.g. "銀行業"
    change_pct: float  # TOPIX-weight weighted return
    median_pct: float
    advancers: int
    decliners: int
    count: int
    topix_weight_pct: float  # sector share of TOPIX
    leaders: list[StockMove] = Field(default_factory=list)  # top contributors / movers (max 3)
    laggards: list[StockMove] = Field(default_factory=list)


class ThemePerf(BaseModel):
    key: str
    name: str
    change_pct: float  # equal-weighted
    advancers_ratio: float  # 0..1
    count: int
    members: list[StockMove] = Field(default_factory=list)  # sorted by change_pct desc
    news_count: int = 0


class Breadth(BaseModel):
    advancers: int
    decliners: int
    unchanged: int
    total: int
    adv_dec_ratio_25d: float | None = None  # 騰落レシオ(25日), %
    new_highs: int | None = None  # 年初来高値更新
    new_lows: int | None = None


class Rankings(BaseModel):
    gainers: list[StockMove] = Field(default_factory=list)
    losers: list[StockMove] = Field(default_factory=list)
    turnover: list[StockMove] = Field(default_factory=list)
    volume_surge: list[StockMove] = Field(default_factory=list)  # 出来高急増 (volume_ratio desc)


class NewsItem(BaseModel):
    title: str
    url: str
    source: str
    published_at: dt.datetime | None = None
    tags: list[str] = Field(default_factory=list)  # theme keys / sector names matched by keyword


class SeriesHistory(BaseModel):
    """Daily % change history for heatmaps (dates oldest first; each series aligned to dates)."""

    dates: list[dt.date] = Field(default_factory=list)
    series: dict[str, list[float | None]] = Field(default_factory=dict)


class DailySummary(BaseModel):
    schema_version: int = SCHEMA_VERSION
    date: dt.date  # JP trading date
    generated_at: dt.datetime
    sources: list[str] = Field(default_factory=list)  # e.g. ["yfinance", "JPX topixweight 2026-07-31"]
    warnings: list[str] = Field(default_factory=list)  # data gaps etc., shown on the page

    comment: str = ""  # 1-3 sentence market comment (rule-based now, LLM later)

    quotes: list[Quote] = Field(default_factory=list)
    sectors: list[SectorPerf] = Field(default_factory=list)  # sorted by change_pct desc
    sectors_official: bool = False  # False = estimated from constituents
    sector17_etfs: list[Quote] = Field(default_factory=list)
    themes: list[ThemePerf] = Field(default_factory=list)  # sorted by change_pct desc
    breadth: Breadth | None = None
    rankings: Rankings = Field(default_factory=Rankings)
    news: list[NewsItem] = Field(default_factory=list)
    disclosures_session: list[Disclosure] = Field(default_factory=list)  # notable, prev close .. 15:30
    disclosures_after: list[Disclosure] = Field(default_factory=list)  # notable, 15:30 .. generation time
    disclosure_counts: dict[str, int] = Field(default_factory=dict)  # {"session": n, "after": n} (all titles)

    sector_history: SeriesHistory = Field(default_factory=SeriesHistory)
    theme_history: SeriesHistory = Field(default_factory=SeriesHistory)

    def quote(self, key: str) -> Quote | None:
        return next((q for q in self.quotes if q.key == key), None)
