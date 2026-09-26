"""Government bond yields: Japan from 財務省 (official daily CSV), US 2Y from FRED. Both lag ~1 business day.

Other US tenors come from yfinance (^IRX, ^TNX, ^TYX) via the normal quote path.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import logging
import re
from pathlib import Path

import httpx
import pandas as pd

log = logging.getLogger(__name__)

MOF_CURRENT = "https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv"
MOF_ALL = "https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
# FRED stalls (read timeout) for browser-like User-Agents but answers plain tool UAs immediately.
FRED_HEADERS = {"User-Agent": "jpmarket/0.1 (+https://github.com/)"}
ERA_BASE = {"S": 1925, "H": 1988, "R": 2018}


def parse_wareki(s: str) -> dt.date | None:
    m = re.fullmatch(r"([SHR])(\d+)\.(\d+)\.(\d+)", s.strip())
    if not m:
        return None
    era, y, mo, d = m.groups()
    return dt.date(ERA_BASE[era] + int(y), int(mo), int(d))


def parse_mof_csv(raw: bytes) -> pd.DataFrame:
    """Rows: date (ascending). Columns: tenor labels like "2年", "10年". Values in %."""
    rows = list(csv.reader(io.StringIO(raw.decode("cp932", errors="replace"))))
    header = next((r for r in rows if r and r[0] == "基準日"), None)
    if header is None:
        raise ValueError("MOF CSV header not found")
    data: dict[dt.date, dict[str, float]] = {}
    for r in rows:
        d = parse_wareki(r[0]) if r else None
        if d is None:
            continue
        data[d] = {h: float(v) for h, v in zip(header[1:], r[1:], strict=False) if h and v not in ("", "-")}
    return pd.DataFrame.from_dict(data, orient="index").sort_index()


def load_jgb_yields(cache_dir: Path, *, today: dt.date, client: httpx.Client) -> pd.DataFrame:
    """History (cached, refreshed monthly) + current month (fetched each run)."""
    hist_path = cache_dir / "rates" / "jgbcm_all.csv"
    stale = not hist_path.exists() or dt.date.fromtimestamp(hist_path.stat().st_mtime) < today.replace(day=1)
    if stale:
        try:
            r = client.get(MOF_ALL)
            r.raise_for_status()
            parse_mof_csv(r.content)  # validate before caching
            hist_path.parent.mkdir(parents=True, exist_ok=True)
            hist_path.write_bytes(r.content)
        except (httpx.HTTPError, ValueError) as e:
            log.warning("MOF history refresh failed: %s", e)
    frames = []
    if hist_path.exists():
        hist = parse_mof_csv(hist_path.read_bytes())
        frames.append(hist[hist.index >= today - dt.timedelta(days=400)])
    try:
        r = client.get(MOF_CURRENT)
        r.raise_for_status()
        frames.append(parse_mof_csv(r.content))
    except (httpx.HTTPError, ValueError) as e:
        log.warning("MOF current-month fetch failed: %s", e)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames)
    return df[~df.index.duplicated(keep="last")].sort_index()


def parse_fred_csv(text: str) -> pd.Series[float]:
    out: dict[dt.date, float] = {}
    for r in csv.reader(io.StringIO(text)):
        if len(r) != 2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r[0]) or r[1] in ("", "."):
            continue
        out[dt.date.fromisoformat(r[0])] = float(r[1])
    return pd.Series(out, dtype=float).sort_index()


def load_fred(series: str, *, client: httpx.Client) -> pd.Series[float]:
    try:
        r = client.get(FRED_CSV.format(series=series), headers=FRED_HEADERS)
        r.raise_for_status()
        return parse_fred_csv(r.text).iloc[-200:]
    except (httpx.HTTPError, ValueError) as e:
        log.warning("FRED %s failed: %s", series, e)
        return pd.Series(dtype=float)
