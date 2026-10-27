"""Print every line containing an unassigned Greek code point, with page context.

Used to decide whether a single such character should mark a whole page as
unreliable, or whether the damage is confined to headers and footers.
"""

import json
from pathlib import Path

from tender_analyzer.normalize import normalize_text
from tender_analyzer.text_signals import sigma_position_error_ratio, unassigned_greek_count

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTIONS_DIR = PROJECT_ROOT / "data" / "processed" / "extractions" / "pymupdf"


def main():
    for path in sorted(EXTRACTIONS_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for page in doc["pages"]:
            text = normalize_text(page["text"])
            count = unassigned_greek_count(text)
            if count == 0:
                continue
            sigma = sigma_position_error_ratio(text)
            # Pages that are clearly broken throughout are not the question here;
            # only pages where the two signals disagree need a closer look.
            if sigma is not None and sigma >= 0.5:
                continue
            sigma_text = "n/a" if sigma is None else f"{sigma:.3f}"
            print(f"\n{doc['adam']} page {page['page']}: {count} unassigned, sigma={sigma_text}")
            for line in text.splitlines():
                if unassigned_greek_count(line):
                    print(f"    {line.strip()[:120]}")


if __name__ == "__main__":
    main()