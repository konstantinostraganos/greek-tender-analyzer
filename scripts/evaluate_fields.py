"""Score field predictions against the manual labels in data/labels/fields.csv.

Every extraction method writes its answers to data/processed/predictions/<name>.csv
with the same columns as the labels, and this script scores them. Keeping the two
apart means an expensive LLM run happens once and can be re-scored freely, and that
all methods are judged by exactly the same rules, which were fixed before any
method was run.
"""

import csv
import re
import sys

from tender_analyzer.pages import extract_pages

# Works because Python puts this script's own folder (scripts/) on the import path.
from check_fields import FIELDS_PATH, squash
from evaluate_document_check import PDF_DIR, PROJECT_ROOT

PREDICTIONS_DIR = PROJECT_ROOT / "data" / "processed" / "predictions"
FIELDS = ("deadline", "estimated_value", "bid_guarantee")
PRESENT = {"stated", "required", "explicitly_not_required", "optional", "refers_elsewhere"}

PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%")
AMOUNT = re.compile(r"(?<![\d.])\d+\.\d{2}(?![\d.])")


def load(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {(row["adam"], row["field"]): row for row in csv.DictReader(handle)}


def guarantee_numbers(value):
    # Order and wording differ ("2% / 800.00" vs "800.00 (2%)"), the numbers must not.
    percents = {float(p) for p in PERCENT.findall(value)}
    amounts = {float(a) for a in AMOUNT.findall(PERCENT.sub(" ", value))}
    return percents, amounts


def greek_amount(number):
    # 55000.0 -> "55.000,00", the way amounts are printed in the documents.
    return f"{number:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def value_renderings(field, gold):
    """Ways the labelled value can be printed in a document, used to accept a page."""
    value = gold["value"]
    if field == "deadline" and re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", value):
        year, month, day = value[:10].split("-")
        days, months = {day, day.lstrip("0")}, {month, month.lstrip("0")}
        return {f"{d}{sep}{m}{sep}{year}" for d in days for m in months for sep in "/-."}
    if field == "estimated_value" and AMOUNT.fullmatch(value):
        return {greek_amount(float(value))}
    if field == "bid_guarantee":
        return {greek_amount(amount) for amount in guarantee_numbers(value)[1]}
    return set()


def value_scorable(field, gold):
    if gold["status"] not in PRESENT or not gold["value"]:
        return False
    if field == "bid_guarantee":
        # A gold value such as "per lot table" holds no number to compare.
        return any(guarantee_numbers(gold["value"]))
    return True


def value_matches(field, gold, predicted):
    expected, got = gold["value"], (predicted or "").strip()
    if field == "deadline":
        if "relative deadline" in gold["notes"]:
            return squash(expected) == squash(got)
        # When the document gives no time, a predicted time is not held against the method.
        return got == expected if " " in expected else got[:10] == expected
    if field == "estimated_value":
        try:
            return abs(float(got) - float(expected)) < 0.005
        except ValueError:
            return False
    return guarantee_numbers(got) == guarantee_numbers(expected)


def score(method):
    gold_rows = load(FIELDS_PATH)
    predictions_path = PREDICTIONS_DIR / f"{method}.csv"
    if not predictions_path.exists():
        print(f"No predictions at {predictions_path.relative_to(PROJECT_ROOT)}")
        sys.exit(1)
    predicted_rows = load(predictions_path)

    pages_by_adam = {}
    for adam, _ in gold_rows:
        if adam not in pages_by_adam:
            pages_by_adam[adam] = extract_pages(PDF_DIR / f"{adam}.pdf")

    totals = {field: {k: [0, 0] for k in ("status", "value", "page", "full")} for field in FIELDS}
    invented = {field: [0, 0] for field in FIELDS}
    missed = {field: [0, 0] for field in FIELDS}
    quotes = [0, 0]
    errors = []

    for (adam, field), gold in sorted(gold_rows.items()):
        pages = pages_by_adam[adam]
        predicted = predicted_rows.get((adam, field), {})
        p_status = predicted.get("status", "missing") or "missing"
        flags = []

        status_ok = p_status == gold["status"]
        totals[field]["status"][0] += status_ok
        totals[field]["status"][1] += 1
        if not status_ok:
            flags.append("status")

        value_ok = True
        if value_scorable(field, gold):
            value_ok = value_matches(field, gold, predicted.get("value"))
            totals[field]["value"][0] += value_ok
            totals[field]["value"][1] += 1
            if not value_ok:
                flags.append("value")

        # A page counts if it holds the labelled sentence or the value itself, so a
        # method that finds the same value stated in other words elsewhere is not penalised.
        if gold["quote"]:
            targets = {squash(gold["quote"])} | {squash(r) for r in value_renderings(field, gold)}
            gold_pages = {p.number for p in pages if any(t in squash(p.text) for t in targets)}
            page = predicted.get("page", "")
            page_ok = page.isdigit() and int(page) in gold_pages
            totals[field]["page"][0] += page_ok
            totals[field]["page"][1] += 1
            if not page_ok:
                flags.append("page")

        full_ok = status_ok and value_ok
        totals[field]["full"][0] += full_ok
        totals[field]["full"][1] += 1

        # The two costly mistakes are counted apart from ordinary ones.
        if gold["status"] == "not_mentioned":
            invented[field][1] += 1
            if p_status in PRESENT:
                invented[field][0] += 1
                flags.append("INVENTED")
        else:
            missed[field][1] += 1
            if p_status == "not_mentioned":
                missed[field][0] += 1
                flags.append("MISSED")

        # Faithfulness: does the method's own quote exist on the page it names?
        p_quote, p_page = predicted.get("quote", ""), predicted.get("page", "")
        if p_quote and p_page.isdigit() and 1 <= int(p_page) <= len(pages):
            quotes[1] += 1
            if squash(p_quote) in squash(pages[int(p_page) - 1].text):
                quotes[0] += 1
            else:
                flags.append("quote not on page")

        if flags:
            errors.append(
                f"  {adam} {field:<16} [{', '.join(flags)}]\n"
                f"      gold: {gold['status']} {gold['value']!r} p.{gold['page'] or '-'}\n"
                f"      pred: {p_status} {predicted.get('value', '')!r} p.{p_page or '-'}"
            )

    def ratio(pair):
        return f"{pair[0]}/{pair[1]}" if pair[1] else "-"

    print(f"=== {method} ===\n")
    print(f"{'field':<16}{'status':>8}{'value':>8}{'page':>8}{'full':>8}{'invented':>10}{'missed':>8}")
    for field in FIELDS:
        t = totals[field]
        print(f"{field:<16}{ratio(t['status']):>8}{ratio(t['value']):>8}{ratio(t['page']):>8}"
              f"{ratio(t['full']):>8}{ratio(invented[field]):>10}{ratio(missed[field]):>8}")

    # The floor any method must beat: always answering the most common status.
    print("\nAlways-majority status:")
    for field in FIELDS:
        counts = {}
        for (_, f), gold in gold_rows.items():
            if f == field:
                counts[gold["status"]] = counts.get(gold["status"], 0) + 1
        top = max(counts, key=counts.get)
        print(f"  {field:<16} always {top}: {counts[top]}/{sum(counts.values())}")

    print(f"\nQuotes found on the stated page: {ratio(quotes)}")
    print(f"\nRows with errors ({len(errors)}):")
    print("\n".join(errors))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts\\evaluate_fields.py <method>   e.g. rules")
        sys.exit(1)
    score(sys.argv[1])
