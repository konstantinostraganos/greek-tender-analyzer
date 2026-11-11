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
# Cached LLM answers live outside git, like every other derived file in data/processed.
LLM_CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "llm_cache"

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
    # None means the checker declined to decide, which is scored apart from wrong answers.
    is_full_tender: bool | None
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


def llm_checker(model):
    # Imported here so the keyword baseline still runs without an API key or network.
    from tender_analyzer.document_check import classify_document, make_client

    client = make_client()
    cache_dir = LLM_CACHE_DIR / model.replace("/", "_")

    def check(pages):
        result = classify_document(pages, client, model=model, cache_dir=cache_dir)
        if result.cached:
            source = "cached"
        elif result.prompt_tokens == 0:
            source = "no request"
        else:
            source = f"tokens={result.prompt_tokens}+{result.completion_tokens}"
        details = f"label={result.label} page={result.evidence_page} {source} | {result.reason}"
        decided = None if result.label is None else result.label == POSITIVE_LABEL
        return Verdict(decided, details)

    return check


# Factories rather than checkers, so that an LLM client is only created when it is run.
CHECKERS = {
    "spike_baseline": lambda: spike_baseline,
    "llm gpt-oss-120b": lambda: llm_checker("openai/gpt-oss-120b"),
}


def load_labels():
    # utf-8-sig reads the file correctly whether or not Excel added a BOM.
    with LABELS_PATH.open(encoding="utf-8-sig", newline="") as handle:
        return {row["adam"].strip(): row["label"].strip() for row in csv.DictReader(handle)}


def evaluate(name, checker, labels, pages_by_adam):
    missed, wrongly_accepted, undecided = [], [], []
    print(f"\n=== {name} ===")
    for index, (adam, label) in enumerate(labels.items(), start=1):
        # Progress line, because an LLM run waits on rate limits and can take many minutes.
        print(f"  [{index}/{len(labels)}] {adam}", end="\r", flush=True)
        verdict = checker(pages_by_adam[adam])
        is_positive = label == POSITIVE_LABEL
        if verdict.is_full_tender is None:
            undecided.append((adam, label, verdict.details))
        elif is_positive and not verdict.is_full_tender:
            missed.append((adam, label, verdict.details))
        elif not is_positive and verdict.is_full_tender:
            wrongly_accepted.append((adam, label, verdict.details))

    positives = sum(1 for label in labels.values() if label == POSITIVE_LABEL)
    negatives = len(labels) - positives
    undecided_positives = sum(1 for _, label, _ in undecided if label == POSITIVE_LABEL)
    undecided_negatives = len(undecided) - undecided_positives

    # The two error types are reported separately because they cost different things:
    # a missed tender is lost, a wrongly accepted one yields misleading "not mentioned" fields.
    print(" " * 40, end="\r")
    print(f"Full tenders accepted:     {positives - len(missed) - undecided_positives}/{positives}")
    print(f"Other documents rejected:  {negatives - len(wrongly_accepted) - undecided_negatives}/{negatives}")
    print(f"Undecided:                 {len(undecided)}")
    for title, errors in (
        ("Missed full tenders", missed),
        ("Wrongly accepted", wrongly_accepted),
        ("Undecided", undecided),
    ):
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

    # An optional argument runs only the checkers whose name contains it, e.g. "llm".
    selected = sys.argv[1] if len(sys.argv) > 1 else ""
    for name, make_checker in CHECKERS.items():
        if selected in name:
            evaluate(name, make_checker(), labels, pages_by_adam)


if __name__ == "__main__":
    main()