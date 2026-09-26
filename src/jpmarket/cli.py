"""jpmarket CLI: run (collect -> analyze -> save -> build site), build, render."""

from __future__ import annotations

import datetime as dt
import logging
from pathlib import Path
from typing import Annotated

import httpx
import typer

from jpmarket.calendar import is_trading_day, latest_trading_day
from jpmarket.config import Settings
from jpmarket.models import DailySummary
from jpmarket.pipeline import Deps, StaleDataError, build_summary, save_summary, summary_path
from jpmarket.render.builder import render_daily
from jpmarket.render.site import build_site, load_all
from jpmarket.sources.yfinance_src import YFinanceSource

app = typer.Typer(no_args_is_help=True, add_completion=False)
EXIT_NOT_TRADING_DAY = 0
EXIT_STALE = 75  # EX_TEMPFAIL: retry later


def _parse_date(s: str | None) -> dt.date:
    if s:
        return dt.date.fromisoformat(s)
    return latest_trading_day(dt.datetime.now(dt.UTC))


@app.callback()
def main(verbose: Annotated[bool, typer.Option("-v", "--verbose")] = False) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )


@app.command()
def run(
    date: Annotated[
        str | None, typer.Option(help="Trading date YYYY-MM-DD (default: latest closed session)")
    ] = None,
    force: Annotated[bool, typer.Option(help="Rebuild even if the day's JSON exists")] = False,
) -> None:
    """Collect data for one day, save data/daily/<date>.json, and rebuild the site."""
    settings = Settings()
    target = _parse_date(date)
    if not is_trading_day(target):
        typer.echo(f"{target} is not a trading day; nothing to do")
        raise typer.Exit(EXIT_NOT_TRADING_DAY)
    path = summary_path(settings.data_dir, target)
    if path.exists() and not force:
        typer.echo(f"{path} exists; skipping collection (use --force to rebuild)")
    else:
        with httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}) as http:
            deps = Deps(
                source=YFinanceSource(
                    chunk_size=settings.yf_chunk_size,
                    pause_sec=settings.yf_pause_sec,
                    max_retries=settings.yf_max_retries,
                ),
                http=http,
                now=dt.datetime.now(dt.UTC),
            )
            try:
                summary = build_summary(target, settings, deps)
            except StaleDataError as e:
                typer.echo(f"data not ready: {e}", err=True)
                raise typer.Exit(EXIT_STALE) from e
        path = save_summary(summary, settings.data_dir)
        typer.echo(f"wrote {path}")
        for w in summary.warnings:
            typer.echo(f"warning: {w}", err=True)
    written = build_site(load_all(settings.data_dir), settings.site_dir)
    typer.echo(f"site: {len(written)} files under {settings.site_dir}")


@app.command()
def build() -> None:
    """Rebuild the whole site from data/daily/*.json."""
    settings = Settings()
    written = build_site(load_all(settings.data_dir), settings.site_dir)
    typer.echo(f"site: {len(written)} files under {settings.site_dir}")


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
