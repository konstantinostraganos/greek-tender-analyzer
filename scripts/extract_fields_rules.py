"""Baseline field extraction with simple keyword-and-pattern rules, no LLM.

Each field is found by taking the first number of the right shape that follows a
typical phrase. The rules are deliberately generic: they are the yardstick an
LLM must beat, so they are not tuned to any labelled document.
"""

import csv
import re
import unicodedata

from tender_analyzer.pages import extract_pages

# Works because Python puts this script's own folder (scripts/) on the import path.
from check_fields import FIELDS_PATH
from evaluate_document_check import PDF_DIR, PROJECT_ROOT
from evaluate_fields import PREDICTIONS_DIR

OUT_PATH = PREDICTIONS_DIR / "rules.csv"
COLUMNS = ["adam", "field", "status", "value", "page", "notes", "quote"]

# Phrases are written folded (lowercase, no accents) and matched against folded text.
DEADLINE_PHRASE = re.compile(r"καταληκτικ\w* ημερομηνι\w*|ληξης υποβολης")
VALUE_PHRASE = re.compile(r"εκτιμωμεν\w* αξι\w*|προυπολογισ\w*")
GUARANTEE_PHRASE = re.compile(r"εγγυηση συμμετοχης|εγγυητικη επιστολη συμμετοχης")

DATE = re.compile(r"(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{4})")
TIME = re.compile(r"ωρα\s*:?\s*(\d{1,2})[:.](\d{2})")
GREEK_AMOUNT = re.compile(r"\d{1,3}(?:\.\d{3})*,\d{2}")
PERCENT = re.compile(r"(\d+(?:,\d+)?)\s*%")

# How far after the phrase a value may sit; long enough for "... είναι η Πέμπτη,"
# and similar fillers, short enough not to reach the next paragraph's numbers.
DATE_WINDOW = 200
TIME_WINDOW = 80
AMOUNT_WINDOW = 200
GUARANTEE_WINDOW = 400

# Table-of-contents lines repeat every heading with dot leaders and a page number;
# matching them would point every field at the contents page.
TOC_LINE = re.compile(r"\.{4,}")
TOC_LOOKAHEAD = 40


def fold(text):
    # One character in, one character out, so positions in the folded text are
    # also positions in the original text and a quote can be cut from it.
    return "".join(unicodedata.normalize("NFD", ch)[0].lower() for ch in text)


def flat(text):
    return " ".join(text.split())


def plausible(date):
    day, month, year = (int(g) for g in date.groups())
    return 1 <= day <= 31 and 1 <= month <= 12 and 2000 <= year <= 2100


def greek_amount(text):
    return text.replace(".", "").replace(",", ".")


def phrase_hits(pages, phrase):
    """Yield (page, flattened text, folded text, end of phrase) in document order."""
    for page in pages:
        if not page.reliable:
            continue
        text = flat(page.text)
        folded = fold(text)
        for match in phrase.finditer(folded):
            if TOC_LINE.search(folded[match.end():match.end() + TOC_LOOKAHEAD]):
                continue
            yield page, text, folded, match


def find_deadline(pages):
    for page, text, folded, match in phrase_hits(pages, DEADLINE_PHRASE):
        window = folded[match.end():match.end() + DATE_WINDOW]
        # Phone numbers and reference codes also look like d-d-dddd, so only a
        # plausible calendar date is accepted.
        date = next((d for d in DATE.finditer(window) if plausible(d)), None)
        if not date:
            continue
        day, month, year = (int(g) for g in date.groups())
        value = f"{year:04d}-{month:02d}-{day:02d}"
        end = match.end() + date.end()
        time = TIME.search(folded[end:end + TIME_WINDOW])
        if time:
            value += f" {int(time.group(1)):02d}:{time.group(2)}"
            end += time.end()
        return "stated", value, page.number, text[match.start():end]
    return "not_mentioned", "", "", ""


def find_value(pages):
    for page, text, folded, match in phrase_hits(pages, VALUE_PHRASE):
        amount = GREEK_AMOUNT.search(text, match.end(), match.end() + AMOUNT_WINDOW)
        if amount:
            quote = text[match.start():amount.end()]
            return "stated", greek_amount(amount.group()), page.number, quote
    return "not_mentioned", "", "", ""


def find_guarantee(pages):
    for page, text, folded, match in phrase_hits(pages, GUARANTEE_PHRASE):
        window_end = match.end() + GUARANTEE_WINDOW
        percent = PERCENT.search(text, match.end(), window_end)
        amount = GREEK_AMOUNT.search(text, match.end(), window_end)
        parts = []
        if percent:
            parts.append(f"{percent.group(1).replace(',', '.')}%")
        if amount:
            parts.append(greek_amount(amount.group()))
        ends = [m.end() for m in (percent, amount) if m] or [match.end()]
        return "required", " / ".join(parts), page.number, text[match.start():max(ends)]
    return "not_mentioned", "", "", ""


FINDERS = {
    "deadline": find_deadline,
    "estimated_value": find_value,
    "bid_guarantee": find_guarantee,
}


def main():
    with FIELDS_PATH.open(encoding="utf-8-sig", newline="") as handle:
        # Only the list of documents is read from the labels, never the answers.
        adams = list(dict.fromkeys(row["adam"] for row in csv.DictReader(handle)))

    PREDICTIONS_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        for adam in adams:
            pages = extract_pages(PDF_DIR / f"{adam}.pdf")
            for field, finder in FINDERS.items():
                status, value, page, quote = finder(pages)
                writer.writerow([adam, field, status, value, page, "rules", quote])

    print(f"Wrote {OUT_PATH.relative_to(PROJECT_ROOT)} for {len(adams)} documents")


if __name__ == "__main__":
    main()
