"""Check extract_pages on the sample PDFs.

Reports reliability flags per document, the effect of normalization on
mixed-script words, registry-stamp removal, and pages with too little text
to judge, so each design decision can be checked against real data.
"""

import csv
import re
from collections import Counter
from pathlib import Path

from tender_analyzer.pages import extract_pages
from tender_analyzer.text_signals import letter_count

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "data" / "sample_manifest.csv"
PDF_DIR = PROJECT_ROOT / "data" / "raw" / "pdfs"

# Documents with a known reason for unreliable pages: three with broken font
# maps, and one whose technical annex is scanned images (checked by eye).
KNOWN_BROKEN_DOCS = {"24PROC014975454", "24PROC014924049", "24PROC014908295", "24PROC015024073"}
LOW_TEXT_LETTERS = 50

LETTER_RUN = re.compile(r"[^\W\d_]+")
STAMP_LINE = re.compile(r"^[ \t]*\d{2}PROC\d{9}[ \t]+\d{4}-\d{2}-\d{2}[ \t]*$", re.MULTILINE)


def is_greek(ch):
    code = ord(ch)
    return 0x0370 <= code <= 0x03FF or 0x1F00 <= code <= 0x1FFF


def is_latin(ch):
    # Same definition as the earlier quality measurement, so before/after
    # counts are comparable with the ~940 mixed words reported there.
    return ch.isalpha() and ord(ch) < 0x0250


def mixed_words(text):
    return [
        w for w in LETTER_RUN.findall(text)
        if any(is_greek(c) for c in w) and any(is_latin(c) for c in w)
    ]


def main():
    with MANIFEST_PATH.open(encoding="utf-8-sig", newline="") as f:
        adams = [row["adam"] for row in csv.DictReader(f)]

    per_doc = {}
    mixed_before, mixed_after = Counter(), Counter()
    stamps_before = stamps_after = 0
    low_text = []

    for adam in adams:
        pages = extract_pages(PDF_DIR / f"{adam}.pdf")
        issues = Counter(issue for p in pages for issue in p.issues)
        per_doc[adam] = (sum(not p.reliable for p in pages), len(pages), issues)

        for p in pages:
            mixed_before.update(mixed_words(p.raw_text))
            mixed_after.update(mixed_words(p.text))
            stamps_before += len(STAMP_LINE.findall(p.raw_text))
            stamps_after += len(STAMP_LINE.findall(p.text))
            letters = letter_count(p.text)
            if letters < LOW_TEXT_LETTERS:
                preview = " ".join(p.text.split())[:80]
                low_text.append((adam, p.number, letters, preview))

    print("Unreliable pages per document:")
    for adam, (bad, total, issues) in per_doc.items():
        if bad == 0:
            continue
        tag = "known" if adam in KNOWN_BROKEN_DOCS else "UNEXPECTED"
        print(f"  [{tag:<10}] {adam}: {bad}/{total} pages  {dict(issues)}")
    unexpected = sum(bad for adam, (bad, _, _) in per_doc.items() if adam not in KNOWN_BROKEN_DOCS)
    print(f"  Unreliable pages outside the known broken documents: {unexpected}")

    print("\nMixed Greek/Latin words:")
    print(f"  before normalization: {sum(mixed_before.values())}")
    print(f"  after normalization:  {sum(mixed_after.values())}")
    print("  most frequent remaining:")
    for word, n in mixed_after.most_common(15):
        print(f"    {n:>4}  {word}")

    print("\nRegistry stamp lines:")
    print(f"  in raw text: {stamps_before}")
    print(f"  in normalized text: {stamps_after}")

    print(f"\nPages with fewer than {LOW_TEXT_LETTERS} letters: {len(low_text)}")
    for adam, number, letters, preview in low_text:
        print(f"  {adam} page {number:>3}  letters={letters:>3}  {preview!r}")


if __name__ == "__main__":
    main()