"""Recent IPOs from JPX's new-listing pages, for the dynamic "IPO" theme. DECISIONS D-25.

Technical listings (holding-company reorganisations etc., marked "*" by JPX) are excluded: they are not IPOs.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

CURRENT_URL = "https://www.jpx.co.jp/listing/stocks/new/index.html"
ARCHIVE_URL = "https://www.jpx.co.jp/listing/stocks/new/00-archives-{n:02d}.html"  # 01 = last year, 02 = ...
USER_AGENT = "Mozilla/5.0 (compatible; jpmarket/0.1)"


@dataclass(frozen=True)
class Listing:
    date: dt.date
    code: str
    name: str
    market: str
    technical: bool


def _cells(tr: str) -> list[str]:
    raw = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", c)).strip() for c in raw]


def _short_name(name: str) -> str:
    name = re.sub(r"\s*代表者インタビュー.*$", "", name).rstrip("*").strip()
    return re.sub(r"^(（株）|株式会社)|(（株）|株式会社)$", "", name).strip()


def parse_listings(page: str) -> list[Listing]:
    """Each listing spans two rows: [date (approval), name, code, ...] then [market, ...]."""
    out: list[Listing] = []
    rows = [_cells(tr) for tr in re.findall(r"<tr.*?</tr>", page, re.S)]
    for i, cells in enumerate(rows):
        if len(cells) < 3 or not (m := re.match(r"(\d{4})/(\d{2})/(\d{2})", cells[0])):
            continue
        code = cells[2].strip()
        if not re.fullmatch(r"[0-9][0-9A-Z]{3}", code):
            continue
        market = rows[i + 1][0] if i + 1 < len(rows) and rows[i + 1] else ""
        out.append(
            Listing(
                date=dt.date(int(m[1]), int(m[2]), int(m[3])),
                code=code,
                name=_short_name(cells[1]),
                market=market,
                technical=cells[1].rstrip().endswith("*"),
            )
        )
    return out


def _get(client: httpx.Client, url: str) -> str | None:
    try:
        r = client.get(url, headers={"User-Agent": USER_AGENT})
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("JPX new listings %s failed: %s", url, e)
        return None
    r.encoding = r.encoding or "utf-8"
    return r.text


def load_recent_ipos(
    cache_dir: Path, *, today: dt.date, client: httpx.Client, window_days: int = 365
) -> list[Listing] | None:
    """IPOs listed within `window_days` up to `today` (newest first). None if JPX could not be read at all.

    The current-year page is fetched every run; last year's archive is cached and refreshed monthly.
    """
    pages: list[str] = []
    current = _get(client, CURRENT_URL)
    if current:
        pages.append(current)
    if (today - dt.timedelta(days=window_days)).year < today.year:
        path = cache_dir / "ipo" / f"new_listings_{today.year - 1}.html"
        fresh = path.exists() and dt.date.fromtimestamp(path.stat().st_mtime) >= today.replace(day=1)
        if not fresh and (archive := _get(client, ARCHIVE_URL.format(n=1))):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(archive, encoding="utf-8")
        if path.exists():
            pages.append(path.read_text(encoding="utf-8"))
    if not pages:
        return None
    start = today - dt.timedelta(days=window_days)
    seen: set[str] = set()
    out = []
    for listing in sorted((x for p in pages for x in parse_listings(p)), key=lambda x: x.date, reverse=True):
        if listing.technical or not (start <= listing.date <= today) or listing.code in seen:
            continue
        seen.add(listing.code)
        out.append(listing)
    return out
