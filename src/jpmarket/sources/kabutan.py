"""Close and PTS (after-hours) price per stock from 株探 (kabutan.jp). DECISIONS D-24.

Used only for the few stocks with notable after-close disclosures; requests are sequential with a pause.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

URL = "https://kabutan.jp/stock/?code={code}"
USER_AGENT = "Mozilla/5.0 (compatible; jpmarket/0.1)"
JST = dt.timezone(dt.timedelta(hours=9))


@dataclass(frozen=True)
class KabutanQuote:
    close: float | None  # latest session close (or current price during the session)
    change_pct: float | None
    limit: str | None  # "S高" / "S安"
    pts_price: float | None
    pts_time: dt.datetime | None


def _num(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(",", "").replace("円", "").strip())
    except ValueError:
        return None


def parse_quote(html: str, *, year: int) -> KabutanQuote | None:
    m_close = re.search(r'<span class="kabuka">([\d,.]+)円</span>', html)
    if not m_close:
        return None
    block = html[m_close.end() : m_close.end() + 600]
    m_pct = re.search(r"<dd>\s*<span[^>]*>([+\-−]?[\d.]+)</span>\s*%</dd>", block)
    m_limit = re.search(r"<dt>\s*<span[^>]*>(S高|S安)</span>", block)
    m_pts = re.search(
        r'kabuka1">PTS</div>\s*<div class="kabuka2">([\d,.]+)円</div>\s*'
        r'<div class="kabuka3">(\d{1,2}):(\d{2})\s*　?\s*(\d{2})/(\d{2})</div>',
        html,
    )
    pts_price = pts_time = None
    if m_pts:
        pts_price = _num(m_pts.group(1))
        hh, mm, mo, dd = (int(m_pts.group(i)) for i in range(2, 6))
        pts_time = dt.datetime(year, mo, dd, hh, mm, tzinfo=JST)
    return KabutanQuote(
        close=_num(m_close.group(1)),
        change_pct=float(m_pct.group(1).replace("−", "-")) if m_pct else None,
        limit=m_limit.group(1) if m_limit else None,
        pts_price=pts_price,
        pts_time=pts_time,
    )


class KabutanClient:
    def __init__(
        self, client: httpx.Client, *, pause: float = 1.0, sleep: Callable[[float], None] = time.sleep
    ):
        self._client = client
        self._pause = pause
        self._sleep = sleep
        self._calls = 0
        self.blocked = False  # kabutan refuses cloud/datacenter IPs (HTTP 403/405); stop asking once it does

    def quote(self, code: str, *, year: int) -> KabutanQuote | None:
        if self.blocked:
            return None
        if self._calls:
            self._sleep(self._pause)
        self._calls += 1
        try:
            r = self._client.get(URL.format(code=code), headers={"User-Agent": USER_AGENT})
            if r.status_code in (403, 405, 429):
                self.blocked = True
                log.warning("kabutan refused access (HTTP %d); skipping remaining PTS lookups", r.status_code)
                return None
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning("kabutan %s failed: %s", code, e)
            return None
        return parse_quote(r.text, year=year)
