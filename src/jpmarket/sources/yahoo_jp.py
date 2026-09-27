"""TOPIX close from Yahoo!ファイナンス (Japan). One request per day; see DECISIONS D-03 for the ToS caveat.

yfinance has no TOPIX series, so this is the only free source for the official level. Any failure
returns None and the pipeline falls back to the constituent-weighted estimate.
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


# --- individual stocks: TSE close + evening PTS (Japannext J-Market, 17:00-06:00) -----------------

STOCK_URL = "https://finance.yahoo.co.jp/quote/{code}.T"
JST = dt.timezone(dt.timedelta(hours=9))


@dataclass(frozen=True)
class StockQuote:
    close: float | None  # latest TSE close
    change_pct: float | None
    limit: str | None  # "S高" / "S安"
    pts_price: float | None  # evening PTS last price
    pts_time: dt.datetime | None


def _board_field(text: str, name: str) -> str | None:
    m = re.search(rf'"{name}":(?:\{{"value":)?"([^"]*)"', text)
    if not m or m.group(1) in ("", "$undefined", "---"):
        return None
    return m.group(1)


def parse_stock_page(html: str, *, year: int) -> StockQuote | None:
    """Parse the quote board embedded (as escaped JSON) in the stock page."""
    text = html.replace('\\"', '"')
    i = text.find('"board":{')
    if i < 0:
        return None
    board = text[i : i + 4000]
    close = _num(_board_field(board, "price"))
    if close is None:
        return None
    rate = _board_field(board, "priceChangeRate")
    limit = (
        "S高"
        if _board_field(board, "highStopText")
        else "S安"
        if _board_field(board, "lowStopText")
        else None
    )
    pts_price = _num(_board_field(board, "ptsPrice"))
    pts_time = None
    stamp = _board_field(board, "ptsUpdateTime")  # e.g. "9/25 23:58"
    if (
        pts_price is not None
        and stamp
        and (m := re.fullmatch(r"(\d{1,2})/(\d{1,2}) (\d{1,2}):(\d{2})", stamp))
    ):
        mo, dd, hh, mm = map(int, m.groups())
        pts_time = dt.datetime(year, mo, dd, hh, mm, tzinfo=JST)
    return StockQuote(
        close=close,
        change_pct=float(rate) if rate else None,
        limit=limit,
        pts_price=pts_price if pts_time else None,
        pts_time=pts_time,
    )


class YahooStockClient:
    """Sequential, paced lookups; stops asking if the site starts refusing requests."""

    def __init__(
        self, client: httpx.Client, *, pause: float = 1.0, sleep: Callable[[float], None] = time.sleep
    ):
        self._client = client
        self._pause = pause
        self._sleep = sleep
        self._calls = 0
        self.blocked = False

    def quote(self, code: str, *, year: int) -> StockQuote | None:
        if self.blocked:
            return None
        if self._calls:
            self._sleep(self._pause)
        self._calls += 1
        try:
            r = self._client.get(STOCK_URL.format(code=code), headers={"User-Agent": USER_AGENT})
        except httpx.HTTPError as e:
            log.warning("yahoo_jp %s failed: %s", code, e)
            return None
        if r.status_code in (403, 405, 429):
            self.blocked = True
            log.warning("yahoo_jp refused access (HTTP %d); skipping remaining PTS lookups", r.status_code)
            return None
        if r.status_code != 200:
            return None
        return parse_stock_page(r.text, year=year)
