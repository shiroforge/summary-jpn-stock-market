"""TOPIX close from Yahoo!ファイナンス (Japan). One request per day; see DECISIONS D-03 for the ToS caveat.

yfinance has no TOPIX series, so this is the only free source for the official level. Any failure
returns None and the pipeline falls back to the constituent-weighted estimate.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

URL = "https://finance.yahoo.co.jp/quote/{code}"
USER_AGENT = "Mozilla/5.0 (compatible; jpmarket/0.1)"


@dataclass(frozen=True)
class IndexClose:
    date: dt.date
    close: float
    prev_close: float

    @property
    def change(self) -> float:
        return self.close - self.prev_close

    @property
    def change_pct(self) -> float:
        return (self.close / self.prev_close - 1) * 100


def _field(html: str, name: str) -> str | None:
    m = re.search(rf'"{name}":"([^"]*)"', html)
    return m.group(1) if m else None


def _num(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def parse_index_page(html: str, *, year: int) -> IndexClose | None:
    close = _num(_field(html, "price"))
    prev = _num(_field(html, "previousPrice"))
    day = _field(html, "openPriceDatetime")  # "MM/DD" of the session the price belongs to
    if close is None or prev is None or not day or not re.fullmatch(r"\d{2}/\d{2}", day):
        return None
    month, dom = map(int, day.split("/"))
    return IndexClose(date=dt.date(year, month, dom), close=close, prev_close=prev)


def fetch_index_close(
    target: dt.date, code: str = "998405.T", *, client: httpx.Client | None = None
) -> IndexClose | None:
    """The index close for `target`, or None if unavailable / not yet updated for that date."""
    try:
        c = client or httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        r = c.get(URL.format(code=code))
        r.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("yahoo_jp fetch failed: %s", e)
        return None
    parsed = parse_index_page(r.text, year=target.year)
    if parsed is None or parsed.date != target:
        log.warning("yahoo_jp %s not updated for %s (got %s)", code, target, parsed and parsed.date)
        return None
    return parsed
