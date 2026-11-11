"""Count, per label, how many documents contain each candidate phrase.

New marker phrases for the Step 0 checker are chosen from this table instead of
by eye: a useful positive phrase appears in most full tenders and in few other
documents, a useful negative phrase the opposite. Checking this before writing
the rule avoids tuning phrases by trial and error on the same 30 documents.
"""

import re

from tender_analyzer.pages import extract_pages

# Works because Python puts this script's own folder (scripts/) on the import path.
from evaluate_document_check import PDF_DIR, POSITIVE_LABEL, fold, load_labels

# Written without accents and in lowercase, because they are compared with folded text.
POSITIVE_CANDIDATES = [
    # The spike's original markers, kept for comparison.
    "εγγυηση συμμετοχης",
    "κριτηρια επιλογης",
    "κριτηρια ποιοτικης επιλογης",
    # Wording seen in the evidence pages of the missed small invitations.
    "υποβολης προσφορ",
    "υποβαλετε προσφορα",
    "καταθεσετε την προσφορα",
    "καταληκτικη ημερομηνια",
    "ημερομηνια ληξης υποβολης",
    "τροπος υποβολης",
    "δικαιωμα συμμετοχης",
    "οροι συμμετοχης",
    "δικαιολογητικα",
    "κριτηριο αναθεσης",
    "κατακυρωση",
    "τεχνικη προσφορα",
    "οικονομικη προσφορα",
    "επι ποινη",
]

# Phrases that might reveal a document which only points to, changes or follows a tender.
NEGATIVE_CANDIDATES = [
    "περιληψη",
    "κειμενο της διακηρυξης",
    "παραταση",
    "προκηρυξη συμβασης",
    "ii.1.1)",
    "αποφασιζουμε",
    "συμφωνια πλαισιο",
    "τροποποιηση",
]

# A document whose pages are mostly corrupted would report every phrase as missing,
# which says nothing about the phrase, so such documents are left out of the counts.
MAX_UNRELIABLE_SHARE = 0.5

WHITESPACE = re.compile(r"\s+")


def searchable_text(pages):
    # Line breaks are collapsed because PDFs often split a phrase across two lines
    # ('Καταληκτική Ημερομηνία' / 'Υποβολής Προσφορών'), which would hide a match.
    return WHITESPACE.sub(" ", fold(" ".join(page.text for page in pages)))


def main():
    labels = load_labels()
    texts_by_label, excluded = {}, []
    for adam, label in labels.items():
        pages = extract_pages(PDF_DIR / f"{adam}.pdf")
        unreliable_share = sum(1 for page in pages if not page.reliable) / max(len(pages), 1)
        if unreliable_share > MAX_UNRELIABLE_SHARE:
            excluded.append(f"{adam} ({label})")
            continue
        texts_by_label.setdefault(label, []).append(searchable_text(pages))

    # Full tenders first, so the column we compare against is always the leftmost one.
    columns = [POSITIVE_LABEL] + sorted(label for label in texts_by_label if label != POSITIVE_LABEL)
    header = f"{'phrase':<30}" + "".join(f"{label:>13}" for label in columns)

    print(f"Excluded as mostly unreliable: {', '.join(excluded) or 'none'}")
    for title, phrases in (("POSITIVE candidates", POSITIVE_CANDIDATES),
                           ("NEGATIVE candidates", NEGATIVE_CANDIDATES)):
        print(f"\n{title}\n{header}")
        for phrase in phrases:
            cells = []
            for label in columns:
                texts = texts_by_label[label]
                found = sum(1 for text in texts if phrase in text)
                cells.append(f"{found}/{len(texts)}".rjust(13))
            print(f"{phrase:<30}" + "".join(cells))


if __name__ == "__main__":
    main()