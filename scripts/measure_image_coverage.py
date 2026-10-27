"""Measure how much of each page is covered by raster images.

Used once to choose the threshold for the scanned-page signal: pages with
almost no text but a large image are likely scans whose content cannot be read.
"""

import csv
from pathlib import Path

import pymupdf

from tender_analyzer.normalize import normalize_text
from tender_analyzer.text_signals import letter_count

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "data" / "sample_manifest.csv"
PDF_DIR = PROJECT_ROOT / "data" / "raw" / "pdfs"

LOW_TEXT_LETTERS = 50
BUCKETS = [(0.0, 0.0), (0.0, 0.25), (0.25, 0.5), (0.5, 0.9), (0.9, 1.0)]


def image_coverage(page):
    # Overlapping images may be counted twice, so the result is capped at 1.0;
    # the question is only whether a page is mostly image, not the exact share.
    page_area = page.rect.width * page.rect.height
    if page_area == 0:
        return 0.0
    covered = 0.0
    for info in page.get_image_info():
        box = pymupdf.Rect(info["bbox"]) & page.rect
        if not box.is_empty:
            covered += box.width * box.height
    return min(covered / page_area, 1.0)


def bucket_label(value):
    if value == 0.0:
        return "none"
    for low, high in BUCKETS[1:]:
        if low < value <= high or (low == 0.0 and 0.0 < value <= high):
            return f"{low:.2f}-{high:.2f}"
    return "0.90-1.00"


def main():
    with MANIFEST_PATH.open(encoding="utf-8-sig", newline="") as f:
        adams = [row["adam"] for row in csv.DictReader(f)]

    low_text = []
    text_pages_by_bucket = {}

    for adam in adams:
        with pymupdf.open(PDF_DIR / f"{adam}.pdf") as doc:
            for index, page in enumerate(doc):
                # Count letters on the normalized text, as the application will,
                # so the registry stamp does not inflate scanned pages.
                letters = letter_count(normalize_text(page.get_text()))
                coverage = image_coverage(page)
                if letters < LOW_TEXT_LETTERS:
                    low_text.append((coverage, adam, index + 1, letters))
                else:
                    label = bucket_label(coverage)
                    text_pages_by_bucket[label] = text_pages_by_bucket.get(label, 0) + 1

    print(f"Pages with fewer than {LOW_TEXT_LETTERS} letters, by image coverage:")
    for coverage, adam, number, letters in sorted(low_text, reverse=True):
        print(f"  coverage={coverage:.2f}  letters={letters:>3}  {adam} page {number}")

    # Reference: how image-heavy ordinary pages with real text are.
    print("\nPages with enough text, by image coverage:")
    for label in ["none", "0.00-0.25", "0.25-0.50", "0.50-0.90", "0.90-1.00"]:
        print(f"  {label:<10} {text_pages_by_bucket.get(label, 0)}")


if __name__ == "__main__":
    main()