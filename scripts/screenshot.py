"""Screenshot an HTML page at desktop/phone widths in light/dark for visual review.

uv run python scripts/screenshot.py site/index.html --out screenshots/
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

VIEWPORTS = {"desktop": (1280, 900), "phone": (390, 844)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("html", type=Path)
    ap.add_argument("--out", type=Path, default=Path("screenshots"))
    ap.add_argument("--schemes", default="light,dark")
    ap.add_argument("--full", action="store_true", help="full-page screenshots")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    url = args.html.resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for vp_name, (w, h) in VIEWPORTS.items():
            for scheme in args.schemes.split(","):
                page = browser.new_page(viewport={"width": w, "height": h}, color_scheme=scheme)  # type: ignore[arg-type]
                page.goto(url, wait_until="networkidle")
                overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth")
                path = args.out / f"{args.html.stem}-{vp_name}-{scheme}.png"
                page.screenshot(path=str(path), full_page=args.full)
                print(f"{path}{'  [horizontal overflow!]' if overflow else ''}")
                page.close()
        browser.close()


if __name__ == "__main__":
    main()
