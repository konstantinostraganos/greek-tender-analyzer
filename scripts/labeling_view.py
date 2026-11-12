"""Build a reading view and an empty label sheet for manual document-type labeling.

The view shows only extracted page text, not registry metadata or the earlier
automatic verdict, so the labels reflect the documents and not prior guesses.
"""

import csv
import html
from pathlib import Path

from tender_analyzer.pages import extract_pages

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "data" / "sample_manifest.csv"
PDF_DIR = PROJECT_ROOT / "data" / "raw" / "pdfs"
VIEW_PATH = PROJECT_ROOT / "data" / "processed" / "labeling_view.html"
LABELS_PATH = PROJECT_ROOT / "data" / "labels" / "document_types.csv"

# The first pages usually carry the title and table of contents, which is
# enough to tell a full tender from an extension or summary notice.
PAGES_SHOWN = 3
CHARS_PER_PAGE = 2500
LABEL_FIELDS = ["adam", "label", "evidence_page", "notes"]

STYLE = """
body { font-family: sans-serif; margin: 24px; max-width: 1000px; }
pre { white-space: pre-wrap; font-size: 13px; border: 1px solid #ccc; padding: 8px; }
.warn { background: #ffe08a; padding: 6px; }
section { margin-bottom: 56px; }
"""


def read_adams():
    with MANIFEST_PATH.open(encoding="utf-8-sig", newline="") as f:
        return [row["adam"] for row in csv.DictReader(f)]


def build_section(adam):
    pages = extract_pages(PDF_DIR / f"{adam}.pdf")
    unreliable = sum(not p.reliable for p in pages)
    warning = ""
    if unreliable:
        # Extracted text is misleading on these pages, so the label must come
        # from the PDF as displayed, not from this view.
        warning = (
            f"<p class='warn'>{unreliable}/{len(pages)} pages unreliable: "
            f"label this document from the PDF itself.</p>"
        )
    blocks = [
        f"<h3>Page {p.number}</h3><pre>{html.escape(p.text[:CHARS_PER_PAGE])}</pre>"
        for p in pages[:PAGES_SHOWN]
    ]
    link = (PDF_DIR / f"{adam}.pdf").as_uri()
    return (
        f"<section id='{adam}'><h2>{adam} — {len(pages)} pages</h2>"
        f"<p><a href='{link}' target='_blank'>open PDF</a></p>"
        f"{warning}{''.join(blocks)}</section>"
    )


def write_view(adams):
    index = " · ".join(f"<a href='#{a}'>{a}</a>" for a in adams)
    sections = "".join(build_section(a) for a in adams)
    VIEW_PATH.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><title>Labeling view</title>"
        f"<style>{STYLE}</style></head><body><p>{index}</p>{sections}</body></html>",
        encoding="utf-8",
    )
    print(f"Wrote {VIEW_PATH.relative_to(PROJECT_ROOT)}")


def write_label_template(adams):
    # Never overwrite: this file holds manual work that no script can regenerate.
    if LABELS_PATH.exists():
        print(f"{LABELS_PATH.relative_to(PROJECT_ROOT)} already exists, left unchanged")
        return
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LABELS_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=LABEL_FIELDS)
        writer.writeheader()
        for adam in adams:
            writer.writerow({"adam": adam})
    print(f"Wrote {LABELS_PATH.relative_to(PROJECT_ROOT)} with {len(adams)} empty rows")


def main():
    adams = read_adams()
    write_view(adams)
    write_label_template(adams)


if __name__ == "__main__":
    main()
