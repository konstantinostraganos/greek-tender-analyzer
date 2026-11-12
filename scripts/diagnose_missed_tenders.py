"""Show why the baseline missed full tenders, before any new rule is written.

For every full tender the spike rule rejected, this reports how many pages the
reliability detector flags (to test the corrupted-text explanation with numbers)
and the text of the labelled evidence page (to see which wording small
invitations actually use, instead of guessing new marker phrases).
"""

import csv

from tender_analyzer.pages import extract_pages

# Works because Python puts this script's own folder (scripts/) on the import path.
from evaluate_document_check import (
    LABELS_PATH,
    PDF_DIR,
    POSITIVE_LABEL,
    PROJECT_ROOT,
    spike_baseline,
)

OUT_PATH = PROJECT_ROOT / "data" / "processed" / "missed_tenders.txt"

# Long enough to cover a participation-terms section, short enough to read 12 of them.
EVIDENCE_CHARS = 1500


def main():
    with LABELS_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["label"].strip() == POSITIVE_LABEL]

    report = []
    print(f"{'adam':<17}{'pages':>6}{'unreliable':>12}  issues")
    for row in rows:
        adam = row["adam"].strip()
        pages = extract_pages(PDF_DIR / f"{adam}.pdf")
        # Re-running the baseline here keeps this list in sync with the evaluation script.
        if spike_baseline(pages).is_full_tender:
            continue

        unreliable = [page for page in pages if not page.reliable]
        issues = sorted({issue for page in unreliable for issue in page.issues})
        print(f"{adam:<17}{len(pages):>6}{len(unreliable):>12}  {', '.join(issues) or '-'}")

        evidence_page = int(row["evidence_page"])
        page = pages[evidence_page - 1]  # labels use physical 1-based page numbers
        report.append(
            f"===== {adam}  evidence page {evidence_page}/{len(pages)}  "
            f"reliable={page.reliable} =====\n{page.text[:EVIDENCE_CHARS]}\n"
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(report), encoding="utf-8")
    print(f"\nEvidence page texts written to {OUT_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
