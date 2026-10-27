"""Build the fixed sample manifest from the earlier sampling outputs.

The manifest pins exactly which documents form the sample, so every later
experiment runs on the same inputs and can be reproduced from the KHMDHS API.
"""

import csv
import sys
from collections import Counter
from pathlib import Path

# Resolve paths from the script location so it works from any working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
NOTICES_PATH = RAW_DIR / "notices.csv"
DOCUMENTS_PATH = RAW_DIR / "documents.csv"
MANIFEST_PATH = PROJECT_ROOT / "data" / "sample_manifest.csv"


def checked_adam_header(header, filename):
    # Excel edits left stray text before "adam"; accept that known pattern only,
    # because silently renaming an unrelated column would corrupt the join.
    if not header.endswith("adam"):
        sys.exit(f"{filename}: expected the first column to be 'adam', found {header!r}")
    return "adam"


def read_rows(path):
    # utf-8-sig removes the BOM that Excel writes; with plain utf-8 it would
    # stay glued to the first header and the 'adam' lookup would fail.
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        fieldnames[0] = checked_adam_header(fieldnames[0], path.name)
        reader.fieldnames = fieldnames
        return fieldnames, list(reader)


def main():
    _, documents = read_rows(DOCUMENTS_PATH)
    sample_adams = [row["adam"].strip() for row in documents]

    repeated = [adam for adam, n in Counter(sample_adams).items() if n > 1]
    if repeated:
        sys.exit(f"documents.csv lists these ADAMs more than once: {repeated}")

    notice_fields, notices = read_rows(NOTICES_PATH)
    counts = Counter(row["adam"].strip() for row in notices)
    by_adam = {row["adam"].strip(): row for row in notices}

    missing = [adam for adam in sample_adams if adam not in by_adam]
    ambiguous = [adam for adam in sample_adams if counts[adam] > 1]
    if missing or ambiguous:
        # Stop instead of writing a partial manifest: a sample that silently
        # shrinks would make later comparisons misleading.
        sys.exit(f"Missing from notices.csv: {missing}\nDuplicated in notices.csv: {ambiguous}")

    # BOM on output so Greek text displays correctly when opened in Excel.
    with MANIFEST_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=notice_fields)
        writer.writeheader()
        for adam in sample_adams:
            writer.writerow({**by_adam[adam], "adam": adam})

    print(f"Wrote {len(sample_adams)} rows to {MANIFEST_PATH.relative_to(PROJECT_ROOT)}")
    print("Contract types:", dict(Counter(by_adam[a]["contract_type"] for a in sample_adams)))


if __name__ == "__main__":
    main()