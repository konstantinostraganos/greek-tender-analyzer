"""Build a side-by-side HTML report of the pages where libraries disagree most.

Automatic metrics showed all libraries read Greek correctly overall, so the
remaining differences are concentrated on a few hard pages; those are the
pages worth inspecting by eye against the original PDF.
"""

import csv
import html
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUALITY_PATH = PROJECT_ROOT / "data" / "processed" / "page_quality.csv"
EXTRACTIONS_DIR = PROJECT_ROOT / "data" / "processed" / "extractions"
PDF_DIR = PROJECT_ROOT / "data" / "raw" / "pdfs"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "disagreements.html"

TOOLS = ["pypdf", "pymupdf", "pdfplumber", "pypdfium2"]
PAGES_TO_SHOW = 8
# Stops one unusual document (e.g. table-heavy) from filling the whole report.
MAX_PAGES_PER_DOC = 2

WORD_RE = re.compile(r"[^\W\d_]+")


def fold(word):
    # Same folding as the quality metrics, so highlights match what was measured.
    decomposed = unicodedata.normalize("NFD", word.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def word_keys(text):
    return {fold(w) for w in WORD_RE.findall(text)}


def select_pages():
    with QUALITY_PATH.open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    by_page = defaultdict(dict)
    for row in rows:
        if row["agreement"]:
            by_page[(row["adam"], int(row["page"]))][row["tool"]] = float(row["agreement"])

    # A page is ranked by its most divergent library: one outlier is enough
    # to make the page worth inspecting.
    ranked = sorted(
        (min(scores.values()), key, min(scores, key=scores.get))
        for key, scores in by_page.items()
        if len(scores) == len(TOOLS)
    )

    chosen, per_doc = [], Counter()
    for score, (adam, page), outlier in ranked:
        if per_doc[adam] >= MAX_PAGES_PER_DOC:
            continue
        chosen.append((adam, page, score, outlier))
        per_doc[adam] += 1
        if len(chosen) == PAGES_TO_SHOW:
            break
    return chosen


def page_text(tool, adam, page):
    doc = json.loads((EXTRACTIONS_DIR / tool / f"{adam}.json").read_text(encoding="utf-8"))
    # Display-only line-ending fix; the stored extraction is left untouched.
    return doc["pages"][page - 1]["text"].replace("\r\n", "\n")


def render(text, other_words):
    parts = []
    for token in re.split(r"(\s+)", text):
        escaped = html.escape(token)
        runs = [fold(w) for w in WORD_RE.findall(token)]
        # Highlight tokens containing a word no other library produced on this
        # page: that is where the libraries actually differ.
        unique = any(run not in other_words for run in runs)
        parts.append(f"<mark>{escaped}</mark>" if unique else escaped)
    return "".join(parts)


def build_section(adam, page, score, outlier):
    texts = {tool: page_text(tool, adam, page) for tool in TOOLS}
    words = {tool: word_keys(text) for tool, text in texts.items()}
    pdf_link = (PDF_DIR / f"{adam}.pdf").as_uri() + f"#page={page}"

    columns = []
    for tool in TOOLS:
        others = set().union(*(words[t] for t in TOOLS if t != tool))
        columns.append(f"<div><h3>{tool}</h3><pre>{render(texts[tool], others)}</pre></div>")

    return (
        f"<section><h2>{adam} — page {page}</h2>"
        f"<p>Lowest agreement: {score:.3f} ({outlier}) · "
        f"<a href='{pdf_link}' target='_blank'>open original page</a></p>"
        f"<div class='grid'>{''.join(columns)}</div></section>"
    )


STYLE = """
body { font-family: sans-serif; margin: 24px; }
.grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
pre { white-space: pre-wrap; font-size: 12px; border: 1px solid #ccc; padding: 8px; }
mark { background: #ffe08a; }
section { margin-bottom: 48px; }
"""


def main():
    chosen = select_pages()
    sections = [build_section(*item) for item in chosen]
    OUT_PATH.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'><title>Extraction disagreements</title>"
        f"<style>{STYLE}</style></head><body>{''.join(sections)}</body></html>",
        encoding="utf-8",
    )
    print(f"Wrote {OUT_PATH.relative_to(PROJECT_ROOT)}")
    for adam, page, score, outlier in chosen:
        print(f"  {adam} page {page:>3}  agreement {score:.3f}  most divergent: {outlier}")


if __name__ == "__main__":
    main()