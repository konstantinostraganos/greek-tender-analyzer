"""Download the source PDFs listed in the sample manifest.

PDFs are kept out of git; this script is how anyone recreates
data/raw/pdfs/ from the committed manifest.
"""

import csv
import sys
import time
from pathlib import Path

import requests

BASE_URL = "https://cerpp.eprocurement.gov.gr/khmdhs-opendata"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = PROJECT_ROOT / "data" / "sample_manifest.csv"
PDF_DIR = PROJECT_ROOT / "data" / "raw" / "pdfs"

# The documented limit is 350 requests per minute; staying far below it
# keeps the load on a public service negligible.
REQUEST_PAUSE_SECONDS = 0.3

# Full tenders can be several MB; a generous timeout avoids false failures
# on a slow response.
TIMEOUT_SECONDS = 120


def is_pdf(path):
    # Magic-byte check so a file that is not a real PDF (e.g. a saved error
    # page) is downloaded again instead of being trusted.
    with path.open("rb") as f:
        return f.read(5) == b"%PDF-"


def download(adam, target):
    response = requests.get(f"{BASE_URL}/notice/attachment/{adam}", timeout=TIMEOUT_SECONDS)
    response.raise_for_status()

    content_type = response.headers.get("Content-Type", "")
    if "pdf" not in content_type.lower():
        raise ValueError(f"unexpected Content-Type: {content_type!r}")
    # A server can label an HTML error page as PDF; the body is the real test.
    if not response.content.startswith(b"%PDF-"):
        raise ValueError("response body does not start with %PDF-")

    # Write under a temporary name and rename only when complete, so an
    # interrupted run never leaves a truncated file under the final name.
    partial = target.parent / (target.name + ".part")
    partial.write_bytes(response.content)
    partial.replace(target)


def main():
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    with MANIFEST_PATH.open(encoding="utf-8-sig", newline="") as f:
        adams = [row["adam"] for row in csv.DictReader(f)]

    downloaded, skipped, failed = 0, 0, []
    for index, adam in enumerate(adams, start=1):
        target = PDF_DIR / f"{adam}.pdf"
        if target.exists() and is_pdf(target):
            skipped += 1
            continue

        print(f"[{index}/{len(adams)}] {adam}")
        try:
            download(adam, target)
            downloaded += 1
        except (requests.RequestException, ValueError) as exc:
            # One failed document must not abort the batch; failures are
            # reported below and fetched again simply by rerunning.
            failed.append((adam, str(exc)[:200]))
        time.sleep(REQUEST_PAUSE_SECONDS)

    print(f"Downloaded: {downloaded}  Already present: {skipped}  Failed: {len(failed)}")
    for adam, error in failed:
        print(f"  {adam}: {error}")

    # A non-zero exit code signals that the document set is incomplete.
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()