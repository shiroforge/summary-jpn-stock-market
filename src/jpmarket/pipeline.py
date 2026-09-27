"""Assemble one day's DailySummary from sources; the only place concrete implementations are wired up."""

from __future__ import annotations

import datetime as dt
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from jpmarket.analytics import core
from jpmarket.analytics.charts import build_chart_payload
from jpmarket.analytics.comment import market_comment
from jpmarket.analytics.trends import build_trends
from jpmarket.calendar import is_trading_day, prev_trading_day
from jpmarket.config import QuoteSpec, Settings
from jpmarket.models import DailySummary, Disclosure, NewsItem, Quote, QuoteCategory, StockMove
from jpmarket.news import rss, tdnet
from jpmarket.sources import rates
from jpmarket.sources.base import MarketDataSource
from jpmarket.sources.master import Master, load_master
from jpmarket.sources.price_store import PriceStore
from jpmarket.sources.yahoo_jp import IndexClose, fetch_index_close

log = logging.getLogger(__name__)
JST = dt.timezone(dt.timedelta(hours=9))
FRESHNESS_SYMBOL = "^N225"


class StaleDataError(RuntimeError):
    """Target-day data is not available yet (retryable)."""


@dataclass
class Deps:
    """External dependencies; tests replace these with fakes."""

    source: MarketDataSource
    http: httpx.Client
    now: dt.datetime
    master: Master | None = None  # None -> load from JPX / cache
    topix: IndexClose | bool | None = True  # True -> fetch from Yahoo JP; None -> unavailable
    final: bool = True  # False on early attempts: incomplete data raises StaleDataError to retry later
    news: list[NewsItem] | None = None  # None -> fetch RSS
    disclosures: list[Disclosure] | None = None  # None -> fetch TDnet
    failed_feeds: list[str] = field(default_factory=list)


def summary_path(data_dir: Path, d: dt.date) -> Path:
    return data_dir / "daily" / f"{d.isoformat()}.json"


def last_topix_close(data_dir: Path, before: dt.date) -> float | None:
    """The most recent stored official TOPIX close before `before` (for the estimate fallback)."""
    for p in sorted((data_dir / "daily").glob("*.json"), reverse=True):
        if p.stem >= before.isoformat():
            continue
        s = DailySummary.model_validate_json(p.read_text(encoding="utf-8"))
        q = s.quote("topix")
        if q is not None and not q.is_proxy:
            return q.close
    return None


def topix_quote(
    spec: QuoteSpec,
    official: IndexClose | None,
    est: pd.Series[float],
    target: dt.date,
    fallback_base: float | None,
) -> tuple[Quote | None, str | None]:
    """TOPIX from the official close, or chained from the constituent estimate. Returns (quote, warning)."""
    est = est[est.index <= target].dropna()
    if est.empty or est.index[-1] != target:
        return None, "TOPIXの推計に必要な構成銘柄データが不足しています。"
    if official is not None:
        close, warn = official.close, None
    elif fallback_base is not None:
        close = fallback_base * (1 + float(est.iloc[-1]) / 100)
        warn = "TOPIXの公式値を取得できなかったため、構成銘柄からの推計値を表示しています。"
    else:
        return None, "TOPIXの公式値を取得できず、推計の基準値もありません。"
    levels = core.chain_levels(close, est.iloc[-21:])
    q = core.build_quote(spec, levels, target)
    if q is None:
        return None, "TOPIXの履歴が不足しています。"
    if official is not None:  # use exact official change instead of the chained estimate
        q = q.model_copy(
            update={"change": round(official.change, 2), "change_pct": round(official.change_pct, 2)}
        )
    return q.model_copy(update={"is_proxy": official is None}), warn


@dataclass
class BuildResult:
    summary: DailySummary
    charts: dict[str, Any]  # site/data/charts.json
    trends: dict[str, Any]  # site/data/trends.json


def build_summary(target: dt.date, settings: Settings, deps: Deps) -> DailySummary:
    return build(target, settings, deps).summary


def build(target: dt.date, settings: Settings, deps: Deps) -> BuildResult:
    """The day's summary plus the payloads for the chart dialog and the trends page."""
    warnings: list[str] = []
    master = deps.master or load_master(settings.cache_dir, today=target, client=deps.http)
    codes = [c.code for c in master.constituents]
    theme_codes = [c for t in settings.themes for c in t.members]
    etf_codes = [e.code for e in settings.sector17_etfs]
    quote_tickers = [q.ticker for q in settings.quotes if q.source == "yfinance"]

    store = PriceStore(settings.cache_dir / "prices" / "bars.parquet")
    store.update(deps.source, list(dict.fromkeys(codes + theme_codes + etf_codes + quote_tickers)), target)
    store.save()
    all_closes = store.closes(end=target)
    if FRESHNESS_SYMBOL not in all_closes.columns or pd.isna(all_closes[FRESHNESS_SYMBOL].get(target)):
        raise StaleDataError(f"{FRESHNESS_SYMBOL} has no close for {target} yet")
    # Overseas/FX tickers trade on JP holidays; stock-level analytics use TSE sessions only.
    tse_days = [d for d in all_closes.index if is_trading_day(d)]
    closes = all_closes.loc[tse_days]
    vols = store.volumes(end=target).reindex(tse_days)
    rets = core.returns_pct(closes)

    weights = pd.Series({c.code: c.topix_weight_pct for c in master.constituents}, dtype=float)
    cov = core.coverage_pct(core.row(rets, target), weights)
    if cov < settings.coverage_warn_pct:
        if not deps.final:
            raise StaleDataError(f"only {cov:.1f}% of TOPIX weight has a close for {target}")
        warnings.append(
            f"当日の株価を取得できた銘柄がTOPIXウエイトの{cov:.1f}%にとどまります（推計値の誤差が大きくなります）。"
        )

    # quotes
    quotes: list[Quote] = []
    est = core.topix_estimate(master.constituents, rets)
    official = fetch_index_close(target, client=deps.http) if deps.topix is True else deps.topix
    assert official is None or isinstance(official, IndexClose)
    if official is None and not deps.final:
        raise StaleDataError(f"official TOPIX close for {target} not published yet")
    jgb = (
        rates.load_jgb_yields(settings.cache_dir, today=target, client=deps.http)
        if any(s.source == "mof_jgb" for s in settings.quotes)
        else pd.DataFrame()
    )
    missing_rates: list[str] = []
    fred: dict[str, pd.Series[float]] = {}
    for spec in settings.quotes:
        if spec.key == "topix":
            q, warn = topix_quote(spec, official, est, target, last_topix_close(settings.data_dir, target))
            if warn:
                warnings.append(warn)
        elif spec.source == "mof_jgb":
            q = core.build_quote(spec, jgb[spec.ticker].astype(float), target) if spec.ticker in jgb else None
        elif spec.source == "fred":
            fred[spec.ticker] = rates.load_fred(spec.ticker, client=deps.http)
            q = core.build_quote(spec, fred[spec.ticker], target)
        elif spec.ticker in all_closes.columns:
            q = core.build_quote(spec, all_closes[spec.ticker].astype(float), target)
        else:
            q = None
        if q is not None:
            quotes.append(q)
        elif spec.key != "topix":
            log.warning("no data for quote %s", spec.key)
            if spec.category == QuoteCategory.RATES:
                missing_rates.append(spec.name)
    if missing_rates:
        warnings.append(f"金利データを取得できませんでした（{'、'.join(missing_rates)}）。")
    etf_quotes = [
        q
        for e in settings.sector17_etfs
        if e.code in closes.columns
        and (
            q := core.build_quote(
                QuoteSpec(
                    key=f"etf{e.code}",
                    name=e.name,
                    ticker=f"{e.code}.T",
                    category=QuoteCategory.DOMESTIC,
                    is_proxy=True,
                ),
                closes[e.code].astype(float),
                target,
            )
        )
        is not None
    ]

    sectors = core.sector_perf(master.constituents, closes, rets, vols, target)
    sector_of = {c.code: c.sector33 for c in master.constituents}
    moves = [
        m
        for c in master.constituents
        if (m := core.stock_move(c.code, c.name, c.sector33, closes, rets, vols, target)) is not None
    ]
    themes = core.theme_perf(settings.themes, closes, rets, vols, target, sector_of)
    breadth = core.breadth(codes, closes, rets, target)

    # news: from the previous close (15:30 JST) until now
    since = dt.datetime.combine(prev_trading_day(target), dt.time(15, 30), JST)
    until = min(deps.now, dt.datetime.combine(target + dt.timedelta(days=1), dt.time(9, 0), JST))
    if deps.news is None:
        raw, failed = rss.fetch_feeds(settings.feeds, client=deps.http)
    else:
        raw, failed = deps.news, deps.failed_feeds
    window = rss.select(rss.tag(raw, settings.themes), since=since, until=until, max_items=len(raw))
    news = rss.rank(window)[: settings.news_max_items]
    if failed:
        warnings.append(f"一部のニュースを取得できませんでした（{'、'.join(failed)}）。")
    counts: dict[str, int] = {}
    for n in news:
        for t in n.tags:
            counts[t] = counts.get(t, 0) + 1
    themes = [t.model_copy(update={"news_count": counts.get(t.key, 0)}) for t in themes]

    # TDnet: since the previous close -> explains today's moves; after 15:30 -> tomorrow's material
    prev_close = dt.datetime.combine(prev_trading_day(target), dt.time(15, 30), JST)
    close = dt.datetime.combine(target, dt.time(15, 30), JST)
    if deps.disclosures is None:
        fetched: list[Disclosure] = []
        day, ok = prev_close.date(), True
        while day <= target:
            got = tdnet.fetch_day(day, client=deps.http)
            ok = ok and got is not None
            fetched.extend(got or [])
            day += dt.timedelta(days=1)
        if not ok:
            warnings.append("適時開示（TDnet）の一部を取得できませんでした。")
    else:
        fetched = deps.disclosures
    weight_by_code = {c.code: c.topix_weight_pct for c in master.constituents}
    session = tdnet.window(fetched, prev_close, close)
    after = tdnet.window(fetched, close, max(deps.now, close))
    by_code: dict[str, list[Disclosure]] = {}
    for d in sorted(session, key=lambda d: (not tdnet.NOTABLE.intersection(d.tags), -d.time.timestamp())):
        if d.tags and len(by_code.get(d.code, [])) < 2:
            by_code.setdefault(d.code, []).append(d)

    def attach(ms: list[StockMove]) -> list[StockMove]:
        return [m.model_copy(update={"disclosures": by_code[m.code]}) if m.code in by_code else m for m in ms]

    rankings = core.rankings(moves, settings.min_turnover_for_ranking)
    rankings = rankings.model_copy(
        update={k: attach(getattr(rankings, k)) for k in ("gainers", "losers", "turnover", "volume_surge")}
    )
    themes = [t.model_copy(update={"members": attach(t.members)}) for t in themes]
    sectors = [
        s.model_copy(update={"leaders": attach(s.leaders), "laggards": attach(s.laggards)}) for s in sectors
    ]

    by_key = {q.key: q for q in quotes}
    summary = DailySummary(
        date=target,
        generated_at=deps.now,
        sources=[
            "yfinance",
            f"JPX TOPIX構成銘柄ウエイト（{master.as_of.isoformat()}時点）",
            *(["Yahoo!ファイナンス（TOPIX）"] if official else []),
            "RSS（" + "、".join(f.name for f in settings.feeds if f.name not in failed) + "）",
        ],
        warnings=warnings,
        comment=market_comment(by_key.get("nikkei225"), by_key.get("topix"), sectors, themes, breadth),
        quotes=quotes,
        sectors=sectors,
        sectors_official=False,
        sector17_etfs=etf_quotes,
        themes=themes,
        breadth=breadth,
        rankings=rankings,
        news=news,
        disclosures_session=tdnet.notable(session, weight_by_code),
        disclosures_after=tdnet.notable(after, weight_by_code),
        disclosure_counts={"session": len(session), "after": len(after)},
        sector_history=core.sector_history(master.constituents, rets, target),
        theme_history=core.theme_history(settings.themes, rets, target),
    )
    tq = by_key.get("topix")
    charts = build_chart_payload(
        summary,
        settings,
        bars=store.bars,
        master=master.constituents,
        rets=rets,
        jgb=jgb,
        fred=fred,
        topix_close=tq.close if tq else None,
    )
    trends = build_trends(master.constituents, settings.themes, rets, target)
    return BuildResult(summary=summary, charts=charts, trends=trends)


def save_site_data(result: BuildResult, site_dir: Path) -> list[Path]:
    """charts.json / trends.json live only in the built site (raw OHLC; not committed, see D-12/D-18)."""
    out = []
    for name, payload in (("charts", result.charts), ("trends", result.trends)):
        p = site_dir / "data" / f"{name}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        out.append(p)
    return out


def save_summary(summary: DailySummary, data_dir: Path) -> Path:
    p = summary_path(data_dir, summary.date)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(summary.model_dump_json(indent=1), encoding="utf-8")
    return p
