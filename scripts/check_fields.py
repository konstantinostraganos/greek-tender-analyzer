"""Validate the manual field labels before anything is scored against them.

The file is typed by hand, so a stray comma, a page typed from the printed
footer instead of the PDF viewer, or a wrong status code would silently turn
into a "model error" later. Errors must be fixed; warnings are cases to look at
together, mostly quotes that cannot be found in our extracted text.
"""

import csv
import re
import sys
from datetime import datetime

from tender_analyzer.normalize import normalize_text
from tender_analyzer.pages import extract_pages

# Works because Python puts this script's own folder (scripts/) on the import path.
from evaluate_document_check import PDF_DIR, POSITIVE_LABEL, PROJECT_ROOT, load_labels

FIELDS_PATH = PROJECT_ROOT / "data" / "labels" / "fields.csv"
COLUMNS = ["adam", "field", "status", "value", "page", "notes", "quote"]

# Informational fields are either stated or absent; "required" only makes sense
# for a requirement such as the guarantee (see FIELD_GUIDELINES.md).
ALLOWED_STATUS = {
    "deadline": {"stated", "refers_elsewhere", "not_mentioned"},
    "estimated_value": {"stated", "refers_elsewhere", "not_mentioned"},
    "bid_guarantee": {
        "required", "explicitly_not_required", "optional", "refers_elsewhere", "not_mentioned",
    },
}

# Same threshold as the Step 0 checker and fields_template.py.
MAX_UNRELIABLE_SHARE = 0.5

AMOUNT = re.compile(r"\d+\.\d{2}")


def squash(text):
    # Labels are copied from the PDF viewer, so line breaks, spacing and case can
    # differ from our extracted text without the quote being wrong.
    return " ".join(normalize_text(text).split()).lower()


def valid_date(value):
    for layout in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            datetime.strptime(value, layout)
            return True
        except ValueError:
            pass
    return False


def check_row(row, pages, errors, warnings, where):
    adam, field, status, value, page, notes, quote = row

    if field not in ALLOWED_STATUS:
        errors.append(f"{where}: unknown field {field!r}")
        return
    if status not in ALLOWED_STATUS[field]:
        errors.append(f"{where}: status {status!r} not allowed for {field}")
        return

    if status == "not_mentioned":
        if value or page or quote:
            errors.append(f"{where}: not_mentioned must leave value, page and quote empty")
        return

    if not page or not quote:
        errors.append(f"{where}: status {status} needs a page and a quote")
        return

    if field == "deadline":
        # A relative deadline is copied as text on purpose, so it has no date format.
        if "relative deadline" not in notes and not valid_date(value):
            errors.append(f"{where}: deadline {value!r} is not YYYY-MM-DD or YYYY-MM-DD HH:MM")
    elif field == "estimated_value":
        if status == "stated" and not AMOUNT.fullmatch(value):
            errors.append(f"{where}: amount {value!r} is not like 15616.13")
    elif field == "bid_guarantee" and status == "required" and not value:
        if "not stated" not in notes:
            warnings.append(f"{where}: required guarantee without value or explanation in notes")

    if not page.isdigit() or not 1 <= int(page) <= len(pages):
        errors.append(f"{where}: page {page!r} is not between 1 and {len(pages)}")
        return

    # The point of this check: if our own text does not contain what the person saw,
    # no extraction method can find it, and the page number may be the printed one.
    target = squash(quote)
    if target in squash(pages[int(page) - 1].text):
        return
    found_on = [p.number for p in pages if target in squash(p.text)]
    if found_on:
        warnings.append(f"{where}: quote not on page {page} but on page(s) {found_on}")
    else:
        warnings.append(f"{where}: quote not found in extracted text (table cell or typo?)")


def main():
    labels = load_labels()
    errors, warnings = [], []

    with FIELDS_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        header = next(reader)
        if header != COLUMNS:
            print(f"Header must be {','.join(COLUMNS)}, found {','.join(header)}")
            sys.exit(1)
        rows = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(COLUMNS):
                errors.append(f"line {reader.line_num}: {len(row)} columns instead of {len(COLUMNS)} "
                              "(a comma in notes or a missing quote mark?)")
                continue
            rows.append((reader.line_num, [cell.strip() for cell in row]))

    pages_by_adam = {}
    for adam, label in labels.items():
        if label != POSITIVE_LABEL:
            continue
        pages = extract_pages(PDF_DIR / f"{adam}.pdf")
        if sum(1 for p in pages if not p.reliable) / max(len(pages), 1) <= MAX_UNRELIABLE_SHARE:
            pages_by_adam[adam] = pages

    seen = {}
    for line, row in rows:
        adam, field = row[0], row[1]
        where = f"line {line} {adam} {field}"
        if adam not in pages_by_adam:
            errors.append(f"{where}: not a readable full tender in document_types.csv")
            continue
        if (adam, field) in seen:
            errors.append(f"{where}: duplicate of line {seen[(adam, field)]}")
            continue
        seen[(adam, field)] = line
        check_row(row, pages_by_adam[adam], errors, warnings, where)

    for adam in pages_by_adam:
        for field in ALLOWED_STATUS:
            if (adam, field) not in seen:
                errors.append(f"{adam} {field}: missing row")

    print(f"Rows checked: {len(rows)} for {len(pages_by_adam)} documents\n")
    # An overview of the labels, useful later to see which statuses a model must handle.
    for field in ALLOWED_STATUS:
        counts = {}
        for _, row in rows:
            if row[1] == field:
                counts[row[2]] = counts.get(row[2], 0) + 1
        print(f"  {field:<16} " + "  ".join(f"{s}={n}" for s, n in sorted(counts.items())))

    print(f"\nErrors ({len(errors)}):")
    for message in errors:
        print(f"  {message}")
    print(f"\nWarnings ({len(warnings)}):")
    for message in warnings:
        print(f"  {message}")

    if errors:
        sys.exit(1)
    print("\nAll field labels valid.")


if __name__ == "__main__":
    main()
