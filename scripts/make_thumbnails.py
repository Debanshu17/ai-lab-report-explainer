"""Renders the first page of each report layout to PNG thumbnails for visual inspection."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pymupdf


def make_thumbnails(
    manifest_path: Path = Path("data/synthetic/manifest.csv"),
    reports_dir: Path = Path("data/synthetic/reports"),
    thumbnails_dir: Path = Path("data/synthetic/thumbnails"),
) -> list[Path]:
    """Generate PNG thumbnails for the first instance of each layout."""
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    thumbnails_dir.mkdir(parents=True, exist_ok=True)
    first_by_layout: dict[str, str] = {}

    with open(manifest_path, mode="r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            layout = row["layout"]
            if layout not in first_by_layout:
                first_by_layout[layout] = row["filename"]

    generated_thumbnails: list[Path] = []
    print(f"Generating thumbnails for layouts: {list(first_by_layout.keys())}")

    for layout, filename in sorted(first_by_layout.items()):
        pdf_path = reports_dir / filename
        if not pdf_path.is_file():
            print(f"[!] PDF not found: {pdf_path}")
            continue

        doc = pymupdf.open(pdf_path)
        first_page = doc[0]
        # Render at 150 DPI for sharp, legible thumbnails
        pixmap = first_page.get_pixmap(dpi=150)
        thumb_path = thumbnails_dir / f"{layout}.png"
        pixmap.save(str(thumb_path))
        doc.close()
        generated_thumbnails.append(thumb_path)
        print(f"  [+] Saved {layout} thumbnail from {filename} -> {thumb_path}")

    return generated_thumbnails


if __name__ == "__main__":
    make_thumbnails()
