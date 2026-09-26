"""RSS headlines (title + link only; bodies are never stored — DECISIONS D-07)."""

from __future__ import annotations

import calendar
import datetime as dt
import logging
import re
from collections.abc import Sequence
from time import struct_time

import feedparser
import httpx

from jpmarket.config import FeedSpec, ThemeSpec
from jpmarket.models import NewsItem

log = logging.getLogger(__name__)
USER_AGENT = "Mozilla/5.0 (compatible; jpmarket/0.1)"

# Headlines containing these are treated as market-relevant when choosing what to highlight.
MARKET_WORDS = [
    "株",
    "日経平均",
    "東証",
    "TOPIX",
    "円安",
    "円高",
    "為替",
    "金利",
    "日銀",
    "決算",
    "FRB",
    "米国債",
]


def _ts(entry: feedparser.FeedParserDict) -> dt.datetime | None:
    st: struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
    return dt.datetime.fromtimestamp(calendar.timegm(st), tz=dt.UTC) if st else None


def _clean_title(title: str, source: str) -> tuple[str, str]:
    """Google News appends ' - 媒体名'; split it off to credit the actual publisher."""
    title = re.sub(r"\s+", " ", title).strip()
    # "見出し | カテゴリ | 東洋経済オンライン" -> "見出し"
    if " | " in title:
        title = title.split(" | ")[0].strip()
    if source.startswith("Google News"):
        m = re.match(r"^(.*) - ([^-]{1,40})$", title)
        if m:
            return m.group(1).strip(), m.group(2).strip()
    return title, source


def parse_feed(content: bytes, feed: FeedSpec) -> list[NewsItem]:
    parsed = feedparser.parse(content)
    items: list[NewsItem] = []
    for e in parsed.entries:
        title, link = str(e.get("title", "")), str(e.get("link", ""))
        if not title or not link.startswith("http"):
            continue
        if feed.filter and not any(w in title for w in feed.filter):
            continue
        title, source = _clean_title(title, feed.name)
        items.append(NewsItem(title=title, url=link, source=source, published_at=_ts(e)))
    return items


def fetch_feeds(
    feeds: Sequence[FeedSpec], *, client: httpx.Client | None = None
) -> tuple[list[NewsItem], list[str]]:
    """All items from all feeds, plus the names of feeds that failed."""
    c = client or httpx.Client(timeout=15, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    items: list[NewsItem] = []
    failed: list[str] = []
    for f in feeds:
        try:
            r = c.get(f.url)
            r.raise_for_status()
            items.extend(parse_feed(r.content, f))
        except httpx.HTTPError as e:
            log.warning("feed %s failed: %s", f.name, e)
            failed.append(f.name)
    return items, failed


def _norm(title: str) -> str:
    return re.sub(r"[\s　「」『』（）()、。・,.!！?？]", "", title)[:40]


def tag(items: Sequence[NewsItem], themes: Sequence[ThemeSpec]) -> list[NewsItem]:
    out = []
    for it in items:
        tags = [t.key for t in themes if any(k in it.title for k in t.keywords)]
        out.append(it.model_copy(update={"tags": tags}))
    return out


def select(
    items: Sequence[NewsItem], *, since: dt.datetime, until: dt.datetime, max_items: int
) -> list[NewsItem]:
    """Window by publish time, drop near-duplicate headlines, newest first."""
    seen: set[str] = set()
    out: list[NewsItem] = []
    for it in sorted(items, key=lambda i: i.published_at or since, reverse=True):
        if it.published_at is None or not (since <= it.published_at <= until):
            continue
        key = _norm(it.title)
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out[:max_items]


def relevance(it: NewsItem) -> int:
    return len(it.tags) * 2 + sum(w in it.title for w in MARKET_WORDS)


def rank(items: Sequence[NewsItem]) -> list[NewsItem]:
    """Market-relevant items first (stable: ties keep their newest-first order)."""
    return [it for _, it in sorted(enumerate(items), key=lambda p: (-relevance(p[1]), p[0]))]


def highlight(items: Sequence[NewsItem], n: int = 3) -> list[NewsItem]:
    """Most market-relevant items for the notification."""
    return rank(items)[:n]
