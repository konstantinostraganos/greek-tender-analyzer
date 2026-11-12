"""Create the empty field-label file for the readable full tenders.

The rows are generated so that every document and field appears exactly once
and nothing has to be typed except the answers. An existing file is never
overwritten, because it holds manual work.
"""

import csv

from tender_analyzer.pages import extract_pages

# Works because Python puts this script's own folder (scripts/) on the import path.
from evaluate_document_check import PDF_DIR, POSITIVE_LABEL, PROJECT_ROOT, load_labels

OUT_PATH = PROJECT_ROOT / "data" / "labels" / "fields.csv"
FIELDS = ("deadline", "estimated_value", "bid_guarantee")
COLUMNS = ("adam", "field", "status", "value", "page", "notes", "quote")

# Same threshold as the Step 0 checker: such documents cannot be read, so a value
# labeled from the PDF could never be found in their text by any method.
MAX_UNRELIABLE_SHARE = 0.5


def main():
    if OUT_PATH.exists():
        print(f"{OUT_PATH.relative_to(PROJECT_ROOT)} already exists, left unchanged")
        return

    adams, skipped = [], []
    for adam, label in load_labels().items():
        if label != POSITIVE_LABEL:
            continue
        pages = extract_pages(PDF_DIR / f"{adam}.pdf")
        unreliable_share = sum(1 for page in pages if not page.reliable) / max(len(pages), 1)
        (skipped if unreliable_share > MAX_UNRELIABLE_SHARE else adams).append(adam)

    with OUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for adam in adams:
            for field in FIELDS:
                writer.writerow([adam, field, "", "", "", "", ""])

    print(f"Wrote {OUT_PATH.relative_to(PROJECT_ROOT)}: {len(adams)} documents x {len(FIELDS)} fields")
    print(f"Skipped as unreadable: {', '.join(skipped) or 'none'}")


if __name__ == "__main__":
    main()