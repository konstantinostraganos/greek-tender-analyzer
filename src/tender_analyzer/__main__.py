"""Command line entry point: python -m tender_analyzer <tender.pdf>

Prints the participation sheet for one tender PDF: the Step 0 document check,
then the three fields, each with page, quote and a confidence indicator.
"""

import argparse
import sys
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path

from openai import RateLimitError

from tender_analyzer.document_check import DEFAULT_MODEL, classify_document, make_client
from tender_analyzer.field_extraction import extract_field_with_second_look, quote_found
from tender_analyzer.pages import extract_pages

# Same cache folders as the evaluation scripts, so a PDF already processed there
# costs no tokens here. Assumes the package runs from the repository (editable install);
# the demo will need a configurable location instead.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = PROJECT_ROOT / "data" / "processed" / "llm_cache"
MODEL_FOLDER = DEFAULT_MODEL.replace("/", "_")
CHECK_CACHE_DIR = CACHE_ROOT / MODEL_FOLDER
FIELDS_CACHE_DIR = CACHE_ROOT / "fields" / MODEL_FOLDER

FULL_TENDER = "full_tender"
FIELDS = ("deadline", "estimated_value", "bid_guarantee")

DOCUMENT_NAMES = {
    "full_tender": "πλήρης διακήρυξη",
    "summary": "περίληψη διακήρυξης",
    "eu_notice": "προκήρυξη ΕΕ",
    "decision": "απόφαση",
    "extension": "παράταση",
    "other": "άλλο έγγραφο",
}
FIELD_NAMES = {"deadline": "Προθεσμία", "estimated_value": "Αξία", "bid_guarantee": "Εγγύηση"}
# Statuses whose answer is the value itself; the rest are described in words.
VALUE_STATUSES = {"stated", "required"}
STATUS_TEXT = {
    "explicitly_not_required": "Δεν απαιτείται",
    "optional": "Προαιρετική",
    "refers_elsewhere": "Παραπέμπει αλλού",
    "not_mentioned": "Δεν αναφέρεται",
}


@dataclass
class Analysis:
    check: object
    fields: list = dataclass_field(default_factory=list)
    # Checked here, not at display time, so any front end (CLI now, demo later)
    # gets the same verdict without needing the page texts.
    quote_ok: dict = dataclass_field(default_factory=dict)

    @property
    def tokens(self):
        # Cached answers keep the token counts of their original call;
        # only fresh calls cost anything now.
        items = [self.check, *self.fields]
        return sum(item.prompt_tokens + item.completion_tokens for item in items if not item.cached)


def analyze(pdf_path, client):
    pages = extract_pages(pdf_path)
    check = classify_document(pages, client, cache_dir=CHECK_CACHE_DIR)
    analysis = Analysis(check=check)
    # Fields were only measured on full tenders; on anything else the answers
    # would come with no known accuracy, so we stop rather than guess.
    if check.label != FULL_TENDER:
        return analysis

    text_by_page = {page.number: page.text for page in pages}
    for name in FIELDS:
        answer = extract_field_with_second_look(pages, name, client, cache_dir=FIELDS_CACHE_DIR)
        analysis.fields.append(answer)
        page_text = text_by_page.get(answer.page, "")
        analysis.quote_ok[name] = bool(answer.quote) and quote_found(answer.quote, page_text)
    return analysis


def _indicator(answer, quote_ok):
    # An unverified quote is the stronger warning: the evidence itself is in doubt.
    if not quote_ok:
        return "⚠️ η απόδειξη δεν ταιριάζει ακριβώς, έλεγξε τη σελίδα"
    if answer.second_look:
        return "⚠️ χαμηλότερη βεβαιότητα, έλεγξε τη σελίδα"
    return "✅"


def _field_lines(answer, quote_ok):
    label = f"{FIELD_NAMES[answer.field]}:".ljust(11)
    if answer.status is None:
        return [f"{label}σφάλμα ({answer.error})"]
    if answer.status in VALUE_STATUSES:
        text = answer.value or "(χωρίς τιμή)"
    else:
        text = STATUS_TEXT.get(answer.status, answer.status)
    if answer.page is None:
        return [f"{label}{text}"]
    return [
        f"{label}{text}  (σελ. {answer.page})  {_indicator(answer, quote_ok)}",
        f"           «{answer.quote}»",
    ]


def format_sheet(pdf_path, analysis):
    check = analysis.check
    lines = [f"Αρχείο: {Path(pdf_path).name}", ""]
    if check.label is None:
        lines.append(f"Έγγραφο: δεν ήταν δυνατό να κριθεί ⚠️  ({check.reason})")
        return "\n".join(lines)

    page = f" (σελ. {check.evidence_page})" if check.evidence_page else ""
    mark = "✅" if check.label == FULL_TENDER else "⛔"
    lines.append(f"Έγγραφο:   {DOCUMENT_NAMES.get(check.label, check.label)}{page} {mark}")
    if not check.quotes_verified:
        lines.append("           ⚠️ η απόδειξη δεν ταιριάζει ακριβώς, έλεγξε τη σελίδα")
    if check.label != FULL_TENDER:
        lines.append(f"           Λόγος: {check.reason}")
        lines.append("           Τα πεδία δεν εξάγονται: η ακρίβειά τους μετρήθηκε μόνο σε πλήρεις διακηρύξεις.")
        return "\n".join(lines)

    lines.append("")
    for answer in analysis.fields:
        lines.extend(_field_lines(answer, analysis.quote_ok[answer.field]))
    lines.append("")
    lines.append(f"Tokens: {analysis.tokens}" + ("  (όλα από την cache)" if analysis.tokens == 0 else ""))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m tender_analyzer",
        description="Participation sheet for a Greek public tender PDF.",
    )
    parser.add_argument("pdf", type=Path, help="path to the tender PDF")
    args = parser.parse_args(argv)
    if not args.pdf.is_file():
        parser.error(f"δεν βρέθηκε το αρχείο: {args.pdf}")

    try:
        analysis = analyze(args.pdf, make_client())
    except RateLimitError:
        # The client already retried; finished calls are cached, so a rerun resumes.
        print("Εξαντλήθηκε το όριο του Groq. Δοκίμασε αργότερα, ό,τι έγινε ήδη είναι στην cache.",
              file=sys.stderr)
        return 1
    print(format_sheet(args.pdf, analysis))
    return 0


if __name__ == "__main__":
    sys.exit(main())
