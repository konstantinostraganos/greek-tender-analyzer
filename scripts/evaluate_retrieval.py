"""Measure whether page retrieval finds the pages that hold each labelled field.

Recall@k: among the k pages a method returns, is there at least one that states
the field? A page counts when it holds the labelled quote or the value itself,
the same definition evaluate_fields.py uses. If retrieval misses the page, no
LLM reading the retrieved pages can find the value, so this is measured first.
"""

import csv

from tender_analyzer.pages import extract_pages
from tender_analyzer.retrieval import FIELD_QUERIES, rank_pages

# Works because Python puts this script's own folder (scripts/) on the import path.
from check_fields import FIELDS_PATH, squash
from evaluate_document_check import PDF_DIR
from evaluate_fields import FIELDS, value_renderings

KS = (1, 3, 5)


def first_pages(pages, query):
    # The naive baseline: in short documents everything sits on the first pages.
    return [page.number for page in pages if page.reliable]


METHODS = {
    "first pages": first_pages,
    "bm25": lambda pages, query: rank_pages(pages, query),
    "bm25 stems": lambda pages, query: rank_pages(pages, query, stem=True),
}


def gold_pages(field, gold, pages):
    targets = {squash(gold["quote"])} | {squash(r) for r in value_renderings(field, gold)}
    return {page.number for page in pages if any(t in squash(page.text) for t in targets)}


def main():
    with FIELDS_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = [row for row in csv.DictReader(handle) if row["quote"]]

    pages_by_adam = {}
    cases = []
    for row in rows:
        adam = row["adam"]
        if adam not in pages_by_adam:
            pages_by_adam[adam] = extract_pages(PDF_DIR / f"{adam}.pdf")
        pages = pages_by_adam[adam]
        cases.append((row, pages, gold_pages(row["field"], row, pages)))

    sizes = sorted(len(p) for p in pages_by_adam.values())
    print(f"{len(cases)} labelled fields in {len(pages_by_adam)} documents "
          f"(pages per document: median {sizes[len(sizes) // 2]}, max {sizes[-1]})\n")

    header = f"{'method':<13}{'field':<17}" + "".join(f"{'@' + str(k):>8}" for k in KS)
    print(header)
    misses = {}
    for name, method in METHODS.items():
        for field in FIELDS:
            field_cases = [c for c in cases if c[0]["field"] == field]
            hits = {k: 0 for k in KS}
            for row, pages, wanted in field_cases:
                ranked = method(pages, FIELD_QUERIES[field])
                for k in KS:
                    hits[k] += bool(wanted & set(ranked[:k]))
                if not wanted & set(ranked[:3]):
                    misses.setdefault(name, []).append(
                        f"  {row['adam']} {field:<16} gold pages {sorted(wanted)}  top-3 {ranked[:3]}"
                    )
            cells = "".join(f"{hits[k]:>5}/{len(field_cases):<2}" for k in KS)
            print(f"{name:<13}{field:<17}{cells}")
        print()

    # The misses at k=3 are what the error analysis needs to look at.
    for name in METHODS:
        print(f"Missed at k=3 by {name} ({len(misses.get(name, []))}):")
        print("\n".join(misses.get(name, [])) or "  none")
        print()


if __name__ == "__main__":
    main()
