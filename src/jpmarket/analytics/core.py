"""Pure computations over wide close/volume matrices (index=date ascending, columns=symbol).

No I/O here: everything is testable with small synthetic frames.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping, Sequence
from typing import Any, cast

import pandas as pd

from jpmarket.config import QuoteSpec, ThemeSpec
from jpmarket.models import Breadth, Quote, Rankings, SectorPerf, SeriesHistory, StockMove, ThemePerf
from jpmarket.sources.master import Constituent

SPARK_LEN = 20
HISTORY_LEN = 20
VOLUME_AVG_LEN = 20


def returns_pct(closes: pd.DataFrame) -> pd.DataFrame:
    """Day-over-day % change per symbol, using each symbol's previous *available* close."""
    out = {c: closes[c].dropna().pct_change() * 100 for c in closes.columns}
    return pd.DataFrame(out, index=closes.index, columns=closes.columns, dtype=float)


def row(df: pd.DataFrame, d: dt.date) -> pd.Series[float]:
    """One date's values as a float Series (pandas-stubs types .loc[label] as Series | DataFrame)."""
    return cast("pd.Series[float]", df.loc[d]).astype(float)


def _cell(df: pd.DataFrame, row: dt.date, col: str) -> float:
    v: Any = df.at[row, col]
    return float(v)


def _r2(v: float) -> float:
    return round(float(v), 2)


# --- quotes -----------------------------------------------------------------------------------


def build_quote(spec: QuoteSpec, series: pd.Series[float], target: dt.date) -> Quote | None:
    """Quote from a close series (index=date). Uses the last close on/before `target`."""
    s = series.dropna()
    s = s[s.index <= target]
    if len(s) < 2:
        return None
    close, prev = float(s.iloc[-1]), float(s.iloc[-2])

    def back(n: int) -> float | None:
        return _r2((close / float(s.iloc[-1 - n]) - 1) * 100) if len(s) > n else None

    def diff(n: int) -> float | None:
        return round(close - float(s.iloc[-1 - n]), 4) if len(s) > n else None

    return Quote(
        key=spec.key,
        name=spec.name,
        ticker=spec.ticker,
        category=spec.category,
        close=round(close, 4) if spec.unit == "%" else _r2(close),
        change=round(close - prev, 4),
        change_pct=_r2((close / prev - 1) * 100),
        change_5d_pct=back(5),
        change_20d_pct=back(20),
        change_5d=diff(5),
        change_20d=diff(20),
        spark=[round(float(v), 4) for v in s.iloc[-SPARK_LEN:]],
        as_of=s.index[-1],
        is_proxy=spec.is_proxy,
        unit=spec.unit,
    )


# --- stocks -----------------------------------------------------------------------------------


def stock_move(
    code: str,
    name: str,
    sector: str | None,
    closes: pd.DataFrame,
    rets: pd.DataFrame,
    vols: pd.DataFrame,
    target: dt.date,
) -> StockMove | None:
    if code not in closes.columns or target not in closes.index:
        return None
    close, r = _cell(closes, target, code), _cell(rets, target, code)
    if pd.isna(close) or pd.isna(r):
        return None
    vol = _cell(vols, target, code) if code in vols.columns and target in vols.index else None
    if vol is not None and pd.isna(vol):
        vol = None
    turnover = close * vol if vol is not None else None
    ratio = None
    if vol is not None:
        past = vols.loc[vols.index < target, code].dropna().iloc[-VOLUME_AVG_LEN:]
        avg = float(past.mean()) if len(past) >= VOLUME_AVG_LEN // 2 else 0.0
        ratio = round(vol / avg, 2) if avg > 0 else None
    return StockMove(
        code=code,
        name=name,
        sector33=sector,
        close=_r2(close),
        change_pct=_r2(r),
        turnover=round(turnover, -6) if turnover is not None else None,
        volume=vol,
        volume_ratio=ratio,
    )


# --- sectors ----------------------------------------------------------------------------------


def weighted_return(rets_row: pd.Series[float], weights: pd.Series[float]) -> float | None:
    ok = rets_row.dropna().index.intersection(weights.index)
    w = weights[ok]
    if w.sum() <= 0:
        return None
    return float((rets_row[ok] * w).sum() / w.sum())


def coverage_pct(rets_row: pd.Series[float], weights: pd.Series[float]) -> float:
    ok = rets_row.dropna().index.intersection(weights.index)
    return float(weights[ok].sum() / weights.sum() * 100)


def sector_perf(
    master: Sequence[Constituent],
    closes: pd.DataFrame,
    rets: pd.DataFrame,
    vols: pd.DataFrame,
    target: dt.date,
) -> list[SectorPerf]:
    today = row(rets, target)
    out: list[SectorPerf] = []
    by_sector: dict[str, list[Constituent]] = {}
    for c in master:
        by_sector.setdefault(c.sector33, []).append(c)
    total_w = sum(c.topix_weight_pct for c in master)
    for name, members in by_sector.items():
        w = pd.Series({c.code: c.topix_weight_pct for c in members}, dtype=float)
        r = today.reindex(w.index).dropna()
        if r.empty:
            continue
        wr = weighted_return(r, w)
        assert wr is not None
        contrib = (r * w[r.index]).sort_values()
        names = {c.code: c.name for c in members}

        def moves(
            codes: Sequence[str], sector: str = name, labels: Mapping[str, str] = names
        ) -> list[StockMove]:
            ms = [stock_move(c, labels[c], sector, closes, rets, vols, target) for c in codes]
            return [m for m in ms if m is not None]

        out.append(
            SectorPerf(
                name=name,
                change_pct=_r2(wr),
                median_pct=_r2(float(r.median())),
                advancers=int((r > 0).sum()),
                decliners=int((r < 0).sum()),
                count=len(r),
                topix_weight_pct=round(float(w.sum()) / total_w * 100, 2),
                leaders=moves([c for c in contrib.index[::-1][:3] if contrib[c] > 0]),
                laggards=moves([c for c in contrib.index[:3] if contrib[c] < 0]),
            )
        )
    return sorted(out, key=lambda s: s.change_pct, reverse=True)


def sector_history(master: Sequence[Constituent], rets: pd.DataFrame, target: dt.date) -> SeriesHistory:
    dates = [d for d in rets.index if d <= target][-HISTORY_LEN:]
    weights: dict[str, dict[str, float]] = {}
    for c in master:
        weights.setdefault(c.sector33, {})[c.code] = c.topix_weight_pct
    series: dict[str, list[float | None]] = {}
    for name, wd in weights.items():
        w = pd.Series(wd, dtype=float)
        vals = [weighted_return(row(rets, d).reindex(w.index), w) for d in dates]
        series[name] = [None if v is None else _r2(v) for v in vals]
    return SeriesHistory(dates=dates, series=series)


def topix_estimate(master: Sequence[Constituent], rets: pd.DataFrame) -> pd.Series:
    """Estimated TOPIX daily % change per date (weighted by current TOPIX weights)."""
    w = pd.Series({c.code: c.topix_weight_pct for c in master}, dtype=float)
    return pd.Series({d: weighted_return(row(rets, d).reindex(w.index), w) for d in rets.index}, dtype=float)


def chain_levels(last_close: float, daily_pct: pd.Series[float]) -> pd.Series[float]:
    """Back out a level series ending at `last_close` from daily % changes (index ascending)."""
    levels = [last_close]
    for r in reversed(daily_pct.iloc[1:].tolist()):
        levels.append(levels[-1] / (1 + (r or 0.0) / 100))
    return pd.Series(list(reversed(levels)), index=daily_pct.index)


# --- breadth & rankings -----------------------------------------------------------------------


def breadth(codes: Sequence[str], closes: pd.DataFrame, rets: pd.DataFrame, target: dt.date) -> Breadth:
    r = rets.loc[:target, rets.columns.intersection(list(codes))]
    today = row(r, target).dropna()
    adv, dec = int((today > 0).sum()), int((today < 0).sum())
    unch = len(today) - adv - dec
    last25 = r.iloc[-25:]
    ratio = None
    if len(last25) == 25:
        a, d = (last25 > 0).sum().sum(), (last25 < 0).sum().sum()
        ratio = round(float(a / d * 100), 1) if d else None
    highs = lows = None
    c = closes.loc[:target, closes.columns.intersection(list(codes))]
    ytd = c[[d >= dt.date(target.year, 1, 1) for d in c.index]]
    first_day_covered = not c.empty and c.index[0] <= dt.date(target.year, 1, 5)
    if first_day_covered and len(ytd) > 1:
        prior = ytd.iloc[:-1]
        last = ytd.iloc[-1]
        highs = int((last > prior.max()).sum())
        lows = int((last < prior.min()).sum())
    return Breadth(
        advancers=adv,
        decliners=dec,
        unchanged=unch,
        total=len(today),
        adv_dec_ratio_25d=ratio,
        new_highs=highs,
        new_lows=lows,
    )


def rankings(moves: Sequence[StockMove], min_turnover: float, n: int = 10) -> Rankings:
    liquid = [m for m in moves if (m.turnover or 0) >= min_turnover]
    return Rankings(
        gainers=sorted(liquid, key=lambda m: m.change_pct, reverse=True)[:n],
        losers=sorted(liquid, key=lambda m: m.change_pct)[:n],
        turnover=sorted(moves, key=lambda m: m.turnover or 0, reverse=True)[:n],
        volume_surge=sorted(
            [m for m in liquid if m.volume_ratio is not None], key=lambda m: m.volume_ratio or 0, reverse=True
        )[:n],
    )


# --- themes -----------------------------------------------------------------------------------


def theme_perf(
    themes: Sequence[ThemeSpec],
    closes: pd.DataFrame,
    rets: pd.DataFrame,
    vols: pd.DataFrame,
    target: dt.date,
    sectors_by_code: Mapping[str, str],
) -> list[ThemePerf]:
    out: list[ThemePerf] = []
    for t in themes:
        ms = [
            stock_move(c, n, sectors_by_code.get(c), closes, rets, vols, target) for c, n in t.members.items()
        ]
        members = sorted([m for m in ms if m is not None], key=lambda m: m.change_pct, reverse=True)
        if not members:
            continue
        avg = sum(m.change_pct for m in members) / len(members)
        out.append(
            ThemePerf(
                key=t.key,
                name=t.name,
                change_pct=_r2(avg),
                advancers_ratio=round(sum(m.change_pct > 0 for m in members) / len(members), 2),
                count=len(members),
                members=members,
            )
        )
    return sorted(out, key=lambda t: t.change_pct, reverse=True)


def theme_history(themes: Sequence[ThemeSpec], rets: pd.DataFrame, target: dt.date) -> SeriesHistory:
    dates = [d for d in rets.index if d <= target][-HISTORY_LEN:]
    series: dict[str, list[float | None]] = {}
    for t in themes:
        cols = rets.columns.intersection(list(t.members))
        if cols.empty:
            continue
        means = rets.loc[dates, cols].mean(axis=1, skipna=True)
        series[t.key] = [None if pd.isna(v) else _r2(v) for v in means]
    return SeriesHistory(dates=dates, series=series)
