"""jpmarket CLI. Phase 0: render only. Phase 1 adds run/collect/notify."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from jpmarket.models import DailySummary
from jpmarket.render.builder import render_daily

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.command()
def render(
    summary: Annotated[Path, typer.Argument(exists=True, help="DailySummary JSON")],
    out: Annotated[Path, typer.Option(help="Output HTML path")] = Path("site/index.html"),
    fragment: Annotated[bool, typer.Option(help="Omit <html>/<head>/<body> (for Artifact previews)")] = False,
) -> None:
    """Render one DailySummary JSON into a self-contained HTML page."""
    s = DailySummary.model_validate_json(summary.read_text(encoding="utf-8"))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_daily(s, standalone=not fragment), encoding="utf-8")
    typer.echo(f"wrote {out}")


@app.command()
def version() -> None:
    """Show version."""
    from importlib.metadata import version as v

    typer.echo(v("jpmarket"))
