"""TOPIX constituent master from JPX's free `topixweight_j.csv` (code, name, 33-sector, TOPIX weight).

The file is updated monthly. We cache it under .cache/master/ (not committed: JPX data, redistribution
is not ours to do) and refresh it when stale.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
from dataclasses import dataclass
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

TOPIXWEIGHT_URL = "https://www.jpx.co.jp/automation/markets/indices/topix/files/topixweight_j.csv"
USER_AGENT = "Mozilla/5.0 (compatible; jpmarket/0.1; +https://github.com/)"


@dataclass(frozen=True)
class Constituent:
    code: str
    name: str
    sector33: str
    topix_weight_pct: float
    size_class: str  # e.g. "TOPIX Core30", "TOPIX Small 1"


@dataclass(frozen=True)
class Master:
    as_of: dt.date
    constituents: list[Constituent]

    def by_code(self) -> dict[str, Constituent]:
        return {c.code: c for c in self.constituents}


def parse_topixweight(raw: bytes) -> Master:
    text = raw.decode("cp932", errors="replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    out: list[Constituent] = []
    as_of: dt.date | None = None
    for r in rows:
        code = (r.get("コード") or "").strip()
        weight = (r.get("TOPIXに占める個別銘柄のウエイト") or "").strip().rstrip("%")
        if not code or not weight:
            continue  # footer / blank lines
        if as_of is None and r.get("日付"):
            as_of = dt.datetime.strptime(r["日付"].strip(), "%Y%m%d").date()
        out.append(
            Constituent(
                code=code,
                name=(r.get("銘柄名") or "").strip(),
                sector33=(r.get("業種") or "").strip(),
                topix_weight_pct=float(weight),
                size_class=(r.get("ニューインデックス区分") or "").strip(),
            )
        )
    if not out or as_of is None:
        raise ValueError("topixweight CSV had no constituents")
    return Master(as_of=as_of, constituents=out)


def load_master(
    cache_dir: Path, *, today: dt.date, max_age_days: int = 30, client: httpx.Client | None = None
) -> Master:
    """Load the cached master, refreshing from JPX when the file is older than `max_age_days`.

    Falls back to the cached copy if the download fails.
    """
    path = cache_dir / "master" / "topixweight_j.csv"
    cached: Master | None = parse_topixweight(path.read_bytes()) if path.exists() else None
    fresh_enough = cached is not None and path.stat().st_mtime > _epoch(
        today - dt.timedelta(days=max_age_days)
    )
    if cached is not None and fresh_enough:
        return cached
    try:
        c = client or httpx.Client(timeout=30, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        r = c.get(TOPIXWEIGHT_URL)
        r.raise_for_status()
        master = parse_topixweight(r.content)
    except (httpx.HTTPError, ValueError) as e:
        if cached is None:
            raise
        log.warning("topixweight refresh failed, using cached copy: %s", e)
        return cached
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(r.content)
    return master


def _epoch(d: dt.date) -> float:
    return dt.datetime(d.year, d.month, d.day, tzinfo=dt.UTC).timestamp()
