"""Render DailySummary into static HTML (Jinja2 + server-side SVG; no JS required to read the page)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from jinja2 import Environment, PackageLoader, StrictUndefined, select_autoescape

from jpmarket.models import DailySummary, QuoteCategory

WEEKDAYS_JA = "月火水木金土日"
JST = dt.timezone(dt.timedelta(hours=9), "JST")
STATIC_DIR = Path(__file__).with_name("static")


def tone(v: float | None, eps: float = 0.005) -> str:
    if v is None or abs(v) < eps:
        return "flat"
    return "up" if v > 0 else "down"


def pct(v: float | None, digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:+.{digits}f}%".replace("+0.00%", "0.00%").replace("-0.00%", "0.00%")


def num(v: float | None) -> str:
    """Format a price level: large values without decimals, small with 2."""
    if v is None:
        return "—"
    if abs(v) >= 1000:
        return f"{v:,.0f}" if abs(v) >= 10000 else f"{v:,.2f}"
    return f"{v:,.2f}"


def signed(v: float | None) -> str:
    if v is None:
        return "—"
    s = num(abs(v))
    return ("+" if v > 0 else "−" if v < 0 else "±") + s


def oku(v: float | None) -> str:
    """JPY -> 億円."""
    if v is None:
        return "—"
    return f"{v / 1e8:,.0f}億円"


def jdate(d: dt.date) -> str:
    return f"{d.year}年{d.month}月{d.day}日({WEEKDAYS_JA[d.weekday()]})"


def jst(t: dt.datetime, fmt: str) -> str:
    if t.tzinfo is None:
        t = t.replace(tzinfo=dt.UTC)
    return t.astimezone(JST).strftime(fmt)


def spark_path(values: list[float], w: float = 120, h: float = 36, pad: float = 3) -> dict[str, object]:
    """Polyline + area paths for a sparkline, scaled to its own min/max."""
    if len(values) < 2:
        return {"line": "", "area": "", "x": 0.0, "y": 0.0}
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = (w - 2 * pad) / (len(values) - 1)
    pts = [(pad + i * step, pad + (h - 2 * pad) * (1 - (v - lo) / span)) for i, v in enumerate(values)]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = line + f" L{pts[-1][0]:.1f},{h:.1f} L{pts[0][0]:.1f},{h:.1f} Z"
    return {"line": line, "area": area, "x": pts[-1][0], "y": pts[-1][1]}


def heat_level(v: float | None, cap: float = 3.0) -> str:
    """Bucket a % change into a diverging class: dn3..dn1, z, up1..up3."""
    if v is None:
        return "na"
    a = abs(v)
    if a < 0.25:
        return "z"
    lvl = 1 if a < 1.0 else 2 if a < cap - 1.0 else 3
    return f"{'up' if v > 0 else 'dn'}{lvl}"


def nice_max(values: list[float], floor: float = 1.0) -> float:
    """Symmetric axis bound for diverging bars: the smallest 'nice' value >= max(|v|)."""
    m = max([abs(v) for v in values] + [floor])
    for cand in (1, 1.5, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 50):
        if m <= cand:
            return float(cand)
    return float(m)


def make_env() -> Environment:
    env = Environment(
        loader=PackageLoader("jpmarket.render", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters.update(
        tone=tone, pct=pct, num=num, signed=signed, oku=oku, jdate=jdate, heat=heat_level, jst=jst
    )
    env.globals.update(spark_path=spark_path, nice_max=nice_max, pct=pct, QuoteCategory=QuoteCategory)
    return env


def render_daily(
    summary: DailySummary,
    *,
    standalone: bool = True,
    base_url: str = "..",
    prev_date: dt.date | None = None,
    next_date: dt.date | None = None,
) -> str:
    """Render the daily page.

    standalone=False omits <!doctype>/<html>/<head>/<body> (for embedding, e.g. Artifact previews).
    CSS/JS are always inlined so a single HTML file is self-contained.
    """
    env = make_env()
    tpl = env.get_template("daily.html.j2")
    return tpl.render(
        s=summary,
        standalone=standalone,
        base_url=base_url,
        prev_date=prev_date,
        next_date=next_date,
        css=(STATIC_DIR / "style.css").read_text(encoding="utf-8"),
        js=(STATIC_DIR / "app.js").read_text(encoding="utf-8"),
    )
