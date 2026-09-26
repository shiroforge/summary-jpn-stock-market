"""Rule-based one-paragraph market comment (replaced/augmented by an LLM in Phase 3)."""

from __future__ import annotations

from jpmarket.models import Breadth, Quote, SectorPerf, ThemePerf


def _pct(v: float) -> str:
    return f"{v:+.2f}%"


def market_comment(
    nikkei: Quote | None,
    topix: Quote | None,
    sectors: list[SectorPerf],
    themes: list[ThemePerf],
    breadth: Breadth | None,
) -> str:
    parts: list[str] = []
    idx = [f"{q.name}は{_pct(q.change_pct)}" for q in (nikkei, topix) if q is not None]
    if idx:
        parts.append("、".join(idx) + "。")
    if breadth and breadth.total:
        ratio = breadth.advancers / breadth.total
        if ratio >= 0.8:
            parts.append(f"値上がり銘柄が{ratio:.0%}を占める全面高。")
        elif ratio <= 0.2:
            parts.append(f"値下がり銘柄が{1 - ratio:.0%}を占める全面安。")
    if len(sectors) >= 3:
        up = [s for s in sectors[:2] if s.change_pct > 0]
        down = [s for s in sectors[::-1][:2] if s.change_pct < 0]
        if up and down:
            parts.append(
                f"{'・'.join(s.name for s in up)}が上昇を主導し、{'・'.join(s.name for s in down)}が軟調。"
            )
        elif up:
            parts.append(f"{'・'.join(s.name for s in up)}が上昇を主導。")
        elif down:
            parts.append(f"{'・'.join(s.name for s in down)}の下げが目立つ。")
    if themes:
        best, worst = themes[0], themes[-1]
        if best.change_pct > 0:
            parts.append(f"テーマでは「{best.name}」({_pct(best.change_pct)})が強い。")
        if worst.change_pct < 0 and worst is not best:
            parts.append(f"「{worst.name}」({_pct(worst.change_pct)})は売られた。")
    return "".join(parts)
