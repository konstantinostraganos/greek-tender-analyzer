"""Score document checkers against the human labels of Step 0.

A checker reads the pages of one PDF and decides whether it is a full tender.
All checkers are scored by the same code below, so that a new checker can only
look better or worse because of its rule, never because it was measured
differently.

The first checker is the feasibility spike's rule, reproduced unchanged but run
on our cleaned text, so that it serves as an honest baseline.
"""

import csv
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from tender_analyzer.pages import extract_pages

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = PROJECT_ROOT / "data" / "raw" / "pdfs"
LABELS_PATH = PROJECT_ROOT / "data" / "labels" / "document_types.csv"

# Only this label is suitable for field extraction; every other label must be rejected.
POSITIVE_LABEL = "full_tender"

# Values copied from scripts/feasibility_spike.py. They are deliberately left as
# they were: improving them here would hide how good the original rule really was.
MIN_CHARS_PER_PAGE = 200
MAX_LOW_TEXT_PAGES_PCT = 50
FULL_DOC_MARKERS = [
    "κριτηρια ποιοτικης επιλογης",
    "κριτηρια επιλογης",
    "εγγυηση συμμετοχης",
]


@dataclass(frozen=True)
class Verdict:
    is_full_tender: bool
    # Kept for error analysis: a bare yes/no would not tell us why a checker failed.
    details: str


def fold(text):
    """Lowercase and strip accents, as the spike did, so 'ΚΡΙΤΗΡΙΑ' matches 'κριτηρια'."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def spike_baseline(pages):
    if not pages:
        return Verdict(False, "no pages")

    char_counts = [len(page.text.strip()) for page in pages]
    avg_chars = round(sum(char_counts) / len(char_counts))
    low_text_pct = round(
        100 * sum(1 for count in char_counts if count < MIN_CHARS_PER_PAGE) / len(pages)
    )
    full_text = fold(" ".join(page.text for page in pages))
    markers_found = [marker for marker in FULL_DOC_MARKERS if marker in full_text]

    accepted = (
        avg_chars >= MIN_CHARS_PER_PAGE
        and low_text_pct < MAX_LOW_TEXT_PAGES_PCT
        and bool(markers_found)
    )
    details = (
        f"pages={len(pages)} avg_chars={avg_chars} low_text={low_text_pct}% "
        f"markers={', '.join(markers_found) or 'none'}"
    )
    return Verdict(accepted, details)


# New checkers are added here and are then scored by exactly the same code.
CHECKERS = {
    "spike_baseline": spike_baseline,
}


def load_labels():
    # utf-8-sig reads the file correctly whether or not Excel added a BOM.
    with LABELS_PATH.open(encoding="utf-8-sig", newline="") as handle:
        return {row["adam"].strip(): row["label"].strip() for row in csv.DictReader(handle)}


def evaluate(name, checker, labels, pages_by_adam):
    missed, wrongly_accepted = [], []
    for adam, label in labels.items():
        verdict = checker(pages_by_adam[adam])
        is_positive = label == POSITIVE_LABEL
        if is_positive and not verdict.is_full_tender:
            missed.append((adam, label, verdict.details))
        elif not is_positive and verdict.is_full_tender:
            wrongly_accepted.append((adam, label, verdict.details))

    positives = sum(1 for label in labels.values() if label == POSITIVE_LABEL)
    negatives = len(labels) - positives

    # The two error types are reported separately because they cost different things:
    # a missed tender is lost, a wrongly accepted one yields misleading "not mentioned" fields.
    print(f"\n=== {name} ===")
    print(f"Full tenders accepted:     {positives - len(missed)}/{positives}")
    print(f"Other documents rejected:  {negatives - len(wrongly_accepted)}/{negatives}")
    for title, errors in (("Missed full tenders", missed), ("Wrongly accepted", wrongly_accepted)):
        print(f"\n{title} ({len(errors)}):")
        for adam, label, details in errors:
            print(f"  {adam}  {label:<12} {details}")


def main():
    labels = load_labels()
    missing = [adam for adam in labels if not (PDF_DIR / f"{adam}.pdf").exists()]
    if missing:
        print(f"Missing PDFs: {', '.join(missing)}")
        sys.exit(1)

    # Extracted once and shared, so adding checkers does not multiply the PDF reading time.
    pages_by_adam = {adam: extract_pages(PDF_DIR / f"{adam}.pdf") for adam in labels}

    for name, checker in CHECKERS.items():
        evaluate(name, checker, labels, pages_by_adam)


if __name__ == "__main__":
    main()