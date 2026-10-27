"""Turn a tender PDF into per-page text ready for every later stage.

This is the only module that talks to the PDF library, so switching
libraries later (for example, to reduce deployment size) changes this file alone.
"""

from dataclasses import dataclass
from pathlib import Path

import pymupdf

from tender_analyzer.normalize import normalize_text
from tender_analyzer.reliability import assess_reliability


@dataclass(frozen=True)
class Page:
    number: int
    raw_text: str
    text: str
    reliable: bool
    issues: tuple[str, ...]


def _image_coverage(pdf_page):
    # Overlapping images may be counted twice, so the result is capped at 1.0;
    # the question is only whether a page is mostly image, not the exact share.
    page_area = pdf_page.rect.width * pdf_page.rect.height
    if page_area == 0:
        return 0.0
    covered = 0.0
    for info in pdf_page.get_image_info():
        box = pymupdf.Rect(info["bbox"]) & pdf_page.rect
        if not box.is_empty:
            covered += box.width * box.height
    return min(covered / page_area, 1.0)


def extract_pages(pdf_path):
    pages = []
    with pymupdf.open(Path(pdf_path)) as doc:
        for index, pdf_page in enumerate(doc):
            # raw_text is kept untouched so quotes shown to users match the PDF exactly;
            # all searching and matching happens on the normalized text instead.
            raw = pdf_page.get_text()
            text = normalize_text(raw)
            verdict = assess_reliability(text, image_coverage=_image_coverage(pdf_page))
            pages.append(
                Page(
                    # Physical page number, starting at 1, to match what a PDF viewer shows.
                    number=index + 1,
                    raw_text=raw,
                    text=text,
                    reliable=verdict.reliable,
                    issues=verdict.issues,
                )
            )
    return pages