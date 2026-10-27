"""
Feasibility spike for the public-tenders project.

Answers three questions before we commit to building anything:
  1. Can we list tender notices (diakirykseis) in bulk from the KIMDIS OpenData API?
  2. Are the attached documents full, text-extractable tender documents?
  3. Are notices linked to later awards, so automatic ground truth is possible?

This is not part of the final application. It only reads public data
and writes its results into a local folder (spike_output/).
"""

import csv
import random
import time
import unicodedata
from pathlib import Path

import requests
from pypdf import PdfReader

BASE_URL = "https://cerpp.eprocurement.gov.gr/khmdhs-opendata"

# The API silently shrinks any date range longer than 180 days,
# so we stay inside that window to know exactly what we asked for.
DATE_FROM = "2024-01-01"
DATE_TO = "2024-06-28"

# 9 = services, 13 = supplies. Public works (10) are out of scope for v1
# because their criteria live in registries and laws, not in the document.
CONTRACT_TYPES = {"9": "services", "13": "supplies"}

# Open procedures are the ones that publish a full tender document;
# direct awards and negotiations usually do not.
PROCEDURE_TYPE_OPEN = "1"

SAMPLE_SIZE = 30
RANDOM_SEED = 42  # fixed so the exact same sample can be re-checked later

# A page with less extractable text than this is almost certainly a scanned image.
MIN_CHARS_PER_PAGE = 200

# Phrases found in a full tender document but not in a one-page summary.
# Stored without accents because we compare against accent-stripped text.
FULL_DOC_MARKERS = [
    "κριτηρια ποιοτικης επιλογης",
    "κριτηρια επιλογης",
    "εγγυηση συμμετοχης",
]

OUT_DIR = Path("spike_output")
PDF_DIR = OUT_DIR / "pdfs"

# The documented limit is 350 requests per minute; this keeps us far below it.
REQUEST_PAUSE_SECONDS = 0.3

# Safety net against an infinite loop if the API ever misreports the last page.
MAX_PAGES = 500


def normalize(text):
    """Lowercase and strip accents so 'Κριτήρια' and 'ΚΡΙΤΗΡΙΑ' match the same marker."""
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def post_with_retry(url, payload, max_attempts=5):
    """POST that waits and retries on rate limiting instead of failing the whole run."""
    for attempt in range(1, max_attempts + 1):
        response = requests.post(
            url, json=payload, headers={"Accept": "application/json"}, timeout=60
        )
        if response.status_code == 429:
            time.sleep(5 * attempt)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError(f"Gave up after {max_attempts} attempts: {url}")


def fetch_notices(contract_type):
    """Return every open-procedure notice of one contract type in the date window."""
    payload = {
        "contractType": contract_type,
        "procedureType": PROCEDURE_TYPE_OPEN,
        "dateFrom": DATE_FROM,
        "dateTo": DATE_TO,
        # False means "do not restrict to amendments"; we separate them ourselves below.
        "isModified": False,
    }
    notices = []
    for page in range(MAX_PAGES):
        data = post_with_retry(f"{BASE_URL}/notice?page={page}", payload)
        notices.extend(data.get("content", []))
        total_pages = data.get("totalPages", "?")
        print(f"    page {page + 1}/{total_pages}  ({len(notices)} notices so far)")
        if data.get("last", True):
            break
        time.sleep(REQUEST_PAUSE_SECONDS)
    return notices


def summarize_notice(notice):
    """Keep only the metadata fields the spike actually needs."""

    def value_of(field):
        # Many API fields are {"key": ..., "value": ...}; we want the readable value.
        item = notice.get(field)
        return item.get("value") if isinstance(item, dict) else item

    return {
        "adam": notice.get("referenceNumber"),
        "title": notice.get("title"),
        "organization": value_of("organization"),
        "contract_type": value_of("contractType"),
        "procedure": value_of("typeOfProcedure"),
        "notice_type": value_of("noticeType"),
        "legal_context": value_of("legalContext"),
        "budget_without_vat": notice.get("totalCostWithoutVAT"),
        "final_submission_date": notice.get("finalSubmissionDate"),
        "number_of_lots": notice.get("numberOfSections"),
        "is_amendment": bool(notice.get("amendPreviousNotice")),
        "amends_adam": notice.get("amendedNoticeADAM"),
        "linked_awards": len(notice.get("auctionRefNo") or []),
        "amended_by_count": len(notice.get("amendsNoticeRefNo") or []),
    }


def inspect_document(adam):
    """Download one notice PDF and measure whether it is usable for extraction."""
    result = {
        "adam": adam,
        "downloaded": False,
        "size_kb": None,
        "pages": None,
        "avg_chars_per_page": None,
        "low_text_pages_pct": None,
        "has_full_doc_markers": False,
        "first_page_says_summary": False,
        "usable": False,
        "error": "",
    }
    pdf_path = PDF_DIR / f"{adam}.pdf"

    try:
        response = requests.get(f"{BASE_URL}/notice/attachment/{adam}", timeout=120)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower():
            raise ValueError(f"unexpected content type: {content_type}")
        pdf_path.write_bytes(response.content)
        result["downloaded"] = True
        result["size_kb"] = round(len(response.content) / 1024)
    except Exception as exc:
        # Recorded, not raised: a failed download is itself a finding of the spike.
        result["error"] = f"download: {exc}"[:200]
        return result

    try:
        reader = PdfReader(pdf_path)
        page_texts = [(page.extract_text() or "") for page in reader.pages]
    except Exception as exc:
        result["error"] = f"parse: {exc}"[:200]
        return result

    if not page_texts:
        result["error"] = "parse: zero pages"
        return result

    char_counts = [len(text.strip()) for text in page_texts]
    low_text_pages = sum(1 for count in char_counts if count < MIN_CHARS_PER_PAGE)
    full_text = normalize(" ".join(page_texts))

    result["pages"] = len(page_texts)
    result["avg_chars_per_page"] = round(sum(char_counts) / len(char_counts))
    result["low_text_pages_pct"] = round(100 * low_text_pages / len(page_texts))
    result["has_full_doc_markers"] = any(marker in full_text for marker in FULL_DOC_MARKERS)
    # A summary-only upload typically announces itself on the first page.
    result["first_page_says_summary"] = "περιληψη" in normalize(page_texts[0])

    # Usable = mostly real text (not scans) and contains the sections we will extract.
    result["usable"] = (
        result["avg_chars_per_page"] >= MIN_CHARS_PER_PAGE
        and result["low_text_pages_pct"] < 50
        and result["has_full_doc_markers"]
    )
    return result


def write_csv(path, rows):
    if not rows:
        return
    # utf-8-sig adds a BOM so Excel on Windows shows Greek characters correctly.
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def pct(part, whole):
    return f"{100 * part / whole:.0f}%" if whole else "n/a"


def main():
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: bulk listing.
    print("Step 1/4: listing notices from KIMDIS")
    all_rows = []
    for code, label in CONTRACT_TYPES.items():
        print(f"  contract type: {label}")
        all_rows.extend(summarize_notice(n) for n in fetch_notices(code))

    # A notice could in principle appear under both queries; keep one copy per ADAM.
    notices = list({row["adam"]: row for row in all_rows if row["adam"]}.values())
    write_csv(OUT_DIR / "notices.csv", notices)

    originals = [n for n in notices if not n["is_amendment"]]
    amendments = [n for n in notices if n["is_amendment"]]
    print(f"  {len(notices)} notices ({len(originals)} originals, {len(amendments)} amendments)")

    # Step 2: document quality on a random sample of originals.
    print(f"Step 2/4: downloading and inspecting a sample of {SAMPLE_SIZE} documents")
    random.seed(RANDOM_SEED)
    sample = random.sample(originals, min(SAMPLE_SIZE, len(originals)))
    documents = []
    for index, notice in enumerate(sample, start=1):
        print(f"  [{index}/{len(sample)}] {notice['adam']}")
        documents.append(inspect_document(notice["adam"]))
        time.sleep(REQUEST_PAUSE_SECONDS)
    write_csv(OUT_DIR / "documents.csv", documents)

    # Step 3: links from notices to awards (needed for automatic ground truth).
    print("Step 3/4: checking links to awards and amendments")
    with_awards = sum(1 for n in originals if n["linked_awards"] > 0)
    amendments_with_parent = sum(1 for n in amendments if n["amends_adam"])

    # Step 4: summary against the success criteria we agreed on.
    downloaded = sum(1 for d in documents if d["downloaded"])
    usable = sum(1 for d in documents if d["usable"])
    summaries = sum(1 for d in documents if d["first_page_says_summary"])
    scanned = sum(
        1 for d in documents if d["low_text_pages_pct"] is not None and d["low_text_pages_pct"] >= 50
    )

    lines = [
        "SPIKE SUMMARY",
        f"Date window: {DATE_FROM} to {DATE_TO}, open procedures, services + supplies",
        "",
        "Check 1 - bulk listing (target: at least 100 notices)",
        f"  notices listed: {len(notices)}  -> {'PASS' if len(notices) >= 100 else 'FAIL'}",
        "",
        f"Check 2 - document quality (target: at least 80% usable), sample of {len(documents)}",
        f"  downloaded:            {downloaded} ({pct(downloaded, len(documents))})",
        f"  usable for extraction: {usable} ({pct(usable, len(documents))})"
        f"  -> {'PASS' if documents and usable / len(documents) >= 0.8 else 'FAIL'}",
        f"  mostly scanned:        {scanned}",
        f"  first page mentions 'summary': {summaries}",
        "",
        "Check 3 - links for ground truth",
        f"  originals with at least one linked award: {with_awards} ({pct(with_awards, len(originals))})",
        f"  amendments pointing to their original:    {amendments_with_parent} ({pct(amendments_with_parent, len(amendments))})",
        "",
        "Details: spike_output/notices.csv and spike_output/documents.csv",
    ]
    summary = "\n".join(lines)
    (OUT_DIR / "summary.txt").write_text(summary, encoding="utf-8")
    print("Step 4/4: done\n")
    print(summary)


if __name__ == "__main__":
    main()