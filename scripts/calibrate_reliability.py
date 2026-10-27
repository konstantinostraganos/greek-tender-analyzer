"""Show how reliability signals separate broken pages from normal ones.

Run once to choose the detector's thresholds from data instead of guessing.
Pages containing unassigned Greek code points are treated as known-broken;
pages from the other documents serve as the normal reference.
"""

import json
from collections import Counter
from pathlib import Path

from tender_analyzer.normalize import normalize_text
from tender_analyzer.text_signals import (
    function_word_ratio,
    greek_letter_ratio,
    letter_count,
    sigma_position_error_ratio,
    unassigned_greek_count,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTIONS_DIR = PROJECT_ROOT / "data" / "processed" / "extractions" / "pymupdf"
KNOWN_BROKEN_DOCS = {"24PROC014975454", "24PROC014924049"}
GROUPS = ["broken", "broken_doc_other_pages", "normal_docs"]

# Same minimum as the quality metrics: ratios on near-empty pages are noise.
MIN_LETTERS = 50


def collect():
    groups = {name: [] for name in GROUPS}
    skipped = 0
    for path in sorted(EXTRACTIONS_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for page in doc["pages"]:
            # Measure what the application will see: the normalized text.
            text = normalize_text(page["text"])
            if letter_count(text) < MIN_LETTERS:
                skipped += 1
                continue
            row = {
                "adam": doc["adam"],
                "page": page["page"],
                "fwr": function_word_ratio(text),
                "sigma": sigma_position_error_ratio(text),
                "greek": greek_letter_ratio(text),
                "unassigned": unassigned_greek_count(text),
            }
            # The unassigned-character signal decides first, so a broken page in a
            # document we did not know about is still counted as broken.
            if row["unassigned"] > 0:
                groups["broken"].append(row)
            elif doc["adam"] in KNOWN_BROKEN_DOCS:
                groups["broken_doc_other_pages"].append(row)
            else:
                groups["normal_docs"].append(row)
    return groups, skipped


def quantiles(values):
    ordered = sorted(values)
    return [ordered[round(q * (len(ordered) - 1))] for q in (0, 0.05, 0.25, 0.5, 0.75, 0.95, 1)]


def print_quantiles(groups, key, label):
    print(f"\n{label} (min / p5 / p25 / median / p75 / p95 / max):")
    for name in GROUPS:
        values = [r[key] for r in groups[name] if r[key] is not None]
        missing = len(groups[name]) - len(values)
        if not values:
            print(f"  {name:<24} no pages with a value")
            continue
        q = " / ".join(f"{v:.3f}" for v in quantiles(values))
        print(f"  {name:<24} n={len(values):>4} (no value: {missing:>3})  {q}")


def print_histogram(groups, key, label, step, buckets):
    print(f"\n{label} histogram:")
    print("bucket       " + "".join(f"{n:>24}" for n in GROUPS))
    for b in range(buckets):
        low, high = b * step, (b + 1) * step
        last = b == buckets - 1
        counts = [
            sum(
                1 for r in groups[n]
                if r[key] is not None and (low <= r[key] < high or (last and r[key] >= low))
            )
            for n in GROUPS
        ]
        label_text = f"{low:.2f}+" if last else f"{low:.2f}-{high:.2f}"
        print(f"{label_text:<13}" + "".join(f"{c:>24}" for c in counts))


def main():
    groups, skipped = collect()
    print(f"Pages skipped for too little text: {skipped}")

    print_quantiles(groups, "fwr", "Function-word ratio")
    print_quantiles(groups, "sigma", "Sigma position error ratio")
    print_histogram(groups, "sigma", "Sigma position error ratio", step=0.1, buckets=10)

    print("\nDocuments with pages containing unassigned Greek code points:")
    for adam, n in Counter(r["adam"] for r in groups["broken"]).most_common():
        print(f"  {adam}: {n} pages")

    print("\nHighest sigma error ratios among normal documents (false-positive candidates):")
    scored = [r for r in groups["normal_docs"] if r["sigma"] is not None]
    for r in sorted(scored, key=lambda r: r["sigma"], reverse=True)[:10]:
        print(f"  {r['adam']} page {r['page']:>3}  sigma={r['sigma']:.3f}  fwr={r['fwr']:.3f}")


if __name__ == "__main__":
    main()