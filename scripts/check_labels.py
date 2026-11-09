"""Validate the manual document-type labels before they are used as ground truth.

The script only reports problems and never edits the file: an automatic fix
(for example lowercasing a label) could hide a label that needs rethinking.
It also compares the labels with the feasibility spike's keyword rule.
"""

import csv
import sys
from collections import Counter
from pathlib import Path

import pymupdf

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "data" / "sample_manifest.csv"
LABELS_PATH = PROJECT_ROOT / "data" / "labels" / "document_types.csv"
SPIKE_PATH = PROJECT_ROOT / "data" / "raw" / "documents.csv"
PDF_DIR = PROJECT_ROOT / "data" / "raw" / "pdfs"

EXPECTED_COLUMNS = ["adam", "label", "evidence_page", "notes"]
ALLOWED_LABELS = {"full_tender", "summary", "extension", "eu_notice", "decision", "other"}
SUITABLE = "full_tender"


def read_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        # The spike output may carry stray text before "adam" (see build_manifest.py).
        if fieldnames[0].endswith("adam"):
            fieldnames[0] = "adam"
        reader.fieldnames = fieldnames
        return fieldnames, list(reader)


def page_count(adam):
    with pymupdf.open(PDF_DIR / f"{adam}.pdf") as doc:
        return doc.page_count


def validate(rows, manifest_adams):
    errors = []
    counts = Counter(row["adam"].strip() for row in rows)
    expected = set(manifest_adams)

    for adam, n in counts.items():
        if n > 1:
            errors.append(f"{adam}: listed {n} times")
    for adam in manifest_adams:
        if adam not in counts:
            errors.append(f"{adam}: in the manifest but has no label row")
    for adam in counts:
        if adam not in expected:
            errors.append(f"{adam}: labeled but not in the manifest")

    # Line numbers match what VS Code shows: the header is line 1.
    for line_no, row in enumerate(rows, start=2):
        adam = row["adam"].strip()
        if None in row:
            # DictReader puts surplus fields under the key None; a comma inside
            # the notes is the usual cause, and it shifts nothing visible.
            errors.append(f"line {line_no} {adam}: more columns than the header (comma in notes?)")
        label = (row["label"] or "").strip()
        if label not in ALLOWED_LABELS:
            errors.append(f"line {line_no} {adam}: label {label!r} is not one of {sorted(ALLOWED_LABELS)}")
        page = (row["evidence_page"] or "").strip()
        if not page.isdigit():
            errors.append(f"line {line_no} {adam}: evidence_page {page!r} is not a page number")
        elif adam in expected and not 1 <= int(page) <= page_count(adam):
            errors.append(f"line {line_no} {adam}: evidence_page {page} is outside the document")
    return errors


def compare_with_spike(rows):
    _, spike_rows = read_rows(SPIKE_PATH)
    spike = {row["adam"].strip(): row["usable"].strip() == "True" for row in spike_rows}
    table = Counter()
    for row in rows:
        adam = row["adam"].strip()
        table[(spike[adam], row["label"].strip() == SUITABLE)] += 1

    print("\nSpike keyword rule vs manual labels (suitable = full_tender):")
    print(f"{'':<24}{'manual: suitable':>18}{'manual: not':>14}")
    for spike_says in (True, False):
        name = "spike: suitable" if spike_says else "spike: not"
        print(f"{name:<24}{table[(spike_says, True)]:>18}{table[(spike_says, False)]:>14}")
    agree = table[(True, True)] + table[(False, False)]
    print(f"Agreement: {agree}/{len(rows)}")


def main():
    _, manifest = read_rows(MANIFEST_PATH)
    manifest_adams = [row["adam"].strip() for row in manifest]

    fieldnames, rows = read_rows(LABELS_PATH)
    if fieldnames != EXPECTED_COLUMNS:
        sys.exit(f"Unexpected columns {fieldnames}; expected {EXPECTED_COLUMNS}")

    errors = validate(rows, manifest_adams)
    if errors:
        print(f"{len(errors)} problem(s) found:")
        for error in errors:
            print(f"  {error}")
        # Comparisons on a broken label file would be misleading, so stop here.
        sys.exit(1)

    print(f"All {len(rows)} labels valid.\n")
    print("Labels:")
    for label, n in Counter(row["label"].strip() for row in rows).most_common():
        print(f"  {label:<12} {n}")
    compare_with_spike(rows)


if __name__ == "__main__":
    main()