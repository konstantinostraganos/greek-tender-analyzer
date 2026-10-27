"""Extract per-page text from every sample PDF with each candidate library.

Raw output only: no cleaning, so that differences between libraries stay
visible for the quality comparison that follows.
"""

import csv
import json
import time
from importlib.metadata import version
from pathlib import Path

import pdfplumber
import pymupdf
import pypdfium2
from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "data" / "sample_manifest.csv"
PDF_DIR = PROJECT_ROOT / "data" / "raw" / "pdfs"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "extractions"


# Every extractor uses its library's default text extraction on purpose:
# tuning one library more than the others would bias the comparison.
def extract_pypdf(path):
    reader = PdfReader(path)
    return [page.extract_text() or "" for page in reader.pages]


def extract_pymupdf(path):
    with pymupdf.open(path) as doc:
        return [page.get_text() for page in doc]


def extract_pdfplumber(path):
    with pdfplumber.open(path) as pdf:
        return [page.extract_text() or "" for page in pdf.pages]


def extract_pypdfium2(path):
    pdf = pypdfium2.PdfDocument(path)
    try:
        texts = []
        for index in range(len(pdf)):
            page = pdf[index]
            textpage = page.get_textpage()
            texts.append(textpage.get_text_range())
            # PDFium holds native memory per page; releasing it promptly keeps
            # long documents from accumulating it.
            textpage.close()
            page.close()
        return texts
    finally:
        pdf.close()


# Keys double as the installed package names, used to record exact versions.
EXTRACTORS = {
    "pypdf": extract_pypdf,
    "pymupdf": extract_pymupdf,
    "pdfplumber": extract_pdfplumber,
    "pypdfium2": extract_pypdfium2,
}


def run_one(tool, extractor, adam, pdf_path):
    result = {
        "adam": adam,
        "tool": tool,
        "tool_version": version(tool),
        "seconds": None,
        "error": None,
        "pages": [],
    }
    start = time.perf_counter()
    try:
        texts = extractor(pdf_path)
        # Libraries index pages from 0; stored numbers start at 1 to match
        # the physical page a reader sees in a PDF viewer.
        result["pages"] = [{"page": i, "text": t} for i, t in enumerate(texts, start=1)]
    except Exception as exc:
        # Parsers raise many unrelated exception types on malformed files;
        # a crash on one document is itself a comparison result, so record it.
        result["error"] = f"{type(exc).__name__}: {exc}"[:300]
    result["seconds"] = round(time.perf_counter() - start, 3)
    return result


def main():
    with MANIFEST_PATH.open(encoding="utf-8-sig", newline="") as f:
        adams = [row["adam"] for row in csv.DictReader(f)]

    for tool in EXTRACTORS:
        (OUT_DIR / tool).mkdir(parents=True, exist_ok=True)

    totals = {tool: 0.0 for tool in EXTRACTORS}
    failures = {tool: [] for tool in EXTRACTORS}
    page_mismatches = []

    for index, adam in enumerate(adams, start=1):
        pdf_path = PDF_DIR / f"{adam}.pdf"
        page_counts = {}
        for tool, extractor in EXTRACTORS.items():
            result = run_one(tool, extractor, adam, pdf_path)
            out_path = OUT_DIR / tool / f"{adam}.json"
            # ensure_ascii=False keeps Greek readable when files are inspected by eye.
            out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

            totals[tool] += result["seconds"]
            if result["error"]:
                failures[tool].append(adam)
            else:
                page_counts[tool] = len(result["pages"])

        # A page-by-page comparison is only valid if every library sees the same pages.
        if len(set(page_counts.values())) > 1:
            page_mismatches.append((adam, page_counts))
        print(f"[{index}/{len(adams)}] {adam}  pages={max(page_counts.values(), default=0)}")

    print("\nTotal seconds per tool:")
    for tool, seconds in totals.items():
        print(f"  {tool:<11} {seconds:8.1f}s  failures: {len(failures[tool])} {failures[tool] or ''}")

    print(f"\nPage-count mismatches: {len(page_mismatches)}")
    for adam, counts in page_mismatches:
        print(f"  {adam}: {counts}")


if __name__ == "__main__":
    main()