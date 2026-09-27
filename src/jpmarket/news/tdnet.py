"""TDnet timely disclosures from the public list pages (release.tdnet.info). DECISIONS D-23.

Only the title, time and PDF link are kept. Pages are fetched politely (sequential, with a pause).
"""

from __future__ import annotations

import datetime as dt
import html
import logging
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence

import httpx

from jpmarket.models import Disclosure

log = logging.getLogger(__name__)

BASE = "https://www.release.tdnet.info/inbs/"
LIST_URL = BASE + "I_list_{page:03d}_{ymd}.html"
USER_AGENT = "Mozilla/5.0 (compatible; jpmarket/0.1)"
JST = dt.timezone(dt.timedelta(hours=9))
MAX_PAGES = 30

ROW = re.compile(
    r'kjTime"[^>]*>\s*(?P<time>\d{1,2}:\d{2})\s*</td>.*?'
    r'kjCode"[^>]*>\s*(?P<code>[0-9A-Z]{4,5})\s*</td>.*?'
    r'kjName"[^>]*>(?P<name>.*?)</td>.*?'
    r'kjTitle"[^>]*>\s*<a href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
    re.S,
)

# (category, tone, include-patterns, exclude-patterns). Order = display priority. Keyword-based; a title
# can match several categories.
RULES: list[tuple[str, str, list[str], list[str]]] = [
    ("TOB・MBO", "pos", ["公開買付け", "公開買付", "ＭＢＯ", "MBO", "ＴＯＢ", "TOB"], ["結果", "終了"]),
    ("上方修正", "pos", ["上方修正"], []),
    ("下方修正", "neg", ["下方修正"], []),
    ("増配", "pos", ["増配", "記念配当", "特別配当"], []),
    ("減配", "neg", ["減配", "無配"], []),
    ("自社株買い", "pos", ["自己株式の取得", "自己株式取得", "自社株買い"], ["状況", "結果", "終了", "完了"]),
    ("株式分割", "pos", ["株式分割"], []),
    ("業績修正", "neutral", ["業績予想の修正", "業績予想修正", "通期業績予想"], []),
    ("決算", "neutral", ["決算短信"], ["訂正"]),
    (
        "提携・買収",
        "neutral",
        ["資本業務提携", "業務提携", "株式の取得", "子会社化", "買収", "経営統合", "合併"],
        ["自己株式"],
    ),
    (
        "増資・希薄化",
        "neg",
        [
            "第三者割当",
            "新株式発行",
            "公募",
            "新株予約権の発行",
            "行使価額修正",
            "転換社債",
            "新株予約権付社債",
            "(CB)",
            "（CB）",
        ],
        [],
    ),
    ("特別損失", "neg", ["特別損失", "減損"], []),
    ("株主優待", "neutral", ["株主優待"], []),
    ("報道への回答", "neutral", ["一部報道", "報道について", "報道に関する"], []),
]
NOTABLE = {
    "TOB・MBO",
    "上方修正",
    "下方修正",
    "増配",
    "減配",
    "自社株買い",
    "株式分割",
    "業績修正",
    "決算",
    "提携・買収",
    "増資・希薄化",
    "特別損失",
    "報道への回答",
}


def classify(title: str) -> tuple[list[str], str]:
    tags: list[str] = []
    tones: list[str] = []
    for tag, tone, inc, exc in RULES:
        if any(k in title for k in inc) and not any(k in title for k in exc):
            tags.append(tag)
            tones.append(tone)
    if "訂正" in title[:6]:  # corrections of earlier releases are rarely market-moving
        return [], "neutral"
    has_pos, has_neg = "pos" in tones, "neg" in tones
    tone = "pos" if has_pos and not has_neg else "neg" if has_neg and not has_pos else "neutral"
    return tags, tone


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()


def parse_list(page_html: str, day: dt.date) -> list[Disclosure]:
    out = []
    for m in ROW.finditer(page_html):
        hh, mm = map(int, m["time"].split(":"))
        title = _clean(m["title"])
        tags, tone = classify(title)
        out.append(
            Disclosure(
                code=m["code"][:4],
                name=_clean(m["name"]),
                time=dt.datetime.combine(day, dt.time(hh, mm), JST),
                title=title,
                url=BASE + m["href"],
                tags=tags,
                tone=tone,
            )
        )
    return out


def fetch_day(
    day: dt.date, *, client: httpx.Client, pause: float = 0.5, sleep: Callable[[float], None] = time.sleep
) -> list[Disclosure] | None:
    """All disclosures listed for `day`, or None if TDnet could not be read."""
    ymd = day.strftime("%Y%m%d")
    items: list[Disclosure] = []
    for page in range(1, MAX_PAGES + 1):
        if page > 1:
            sleep(pause)
        try:
            r = client.get(LIST_URL.format(page=page, ymd=ymd), headers={"User-Agent": USER_AGENT})
        except httpx.HTTPError as e:
            log.warning("TDnet %s page %d failed: %s", ymd, page, e)
            return items or None
        if r.status_code == 404:
            break  # no more pages (or no disclosures that day)
        if r.status_code != 200:
            log.warning("TDnet %s page %d: HTTP %d", ymd, page, r.status_code)
            return items or None
        r.encoding = "utf-8"
        rows = parse_list(r.text, day)
        items.extend(rows)
        if len(rows) < 100 or f"I_list_{page + 1:03d}_{ymd}.html" not in r.text:
            break
    return items


def window(items: Iterable[Disclosure], start: dt.datetime, end: dt.datetime) -> list[Disclosure]:
    """Disclosures with start <= time < end, newest first, de-duplicated by URL."""
    seen: set[str] = set()
    out = []
    for d in sorted(items, key=lambda d: d.time, reverse=True):
        if start <= d.time < end and d.url not in seen:
            seen.add(d.url)
            out.append(d)
    return out


def notable(
    items: Sequence[Disclosure], weights: Mapping[str, float], *, limit: int = 40
) -> list[Disclosure]:
    """Market-moving categories only, larger companies (TOPIX weight) first, then newest."""
    picked = [d for d in items if NOTABLE.intersection(d.tags)]
    return sorted(picked, key=lambda d: (-weights.get(d.code, 0.0), -d.time.timestamp()))[:limit]
