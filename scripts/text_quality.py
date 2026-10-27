"""Score per-page text quality for every extraction, without a reference text.

These measures need no ground truth: share of Greek letters, share of common
Greek function words, and word-level agreement between libraries. They catch
large-scale corruption; subtler errors are left to the reference-set step.
"""

import csv
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTIONS_DIR = PROJECT_ROOT / "data" / "processed" / "extractions"
OUT_PATH = PROJECT_ROOT / "data" / "processed" / "page_quality.csv"

TOOLS = ["pypdf", "pymupdf", "pdfplumber", "pypdfium2"]
PROBLEM_DOCS = ["24PROC014094049", "24PROC014586179", "24PROC014975454", "24PROC014924049"]

# Below this many letters a ratio is dominated by noise (a page number, a stamp),
# so the page is reported as unscored rather than as good or bad.
MIN_LETTERS = 50

# Lowercase, accent-free forms. Frequent in any real Greek prose and
# practically absent from garbled output.
FUNCTION_WORDS = {
    "και", "του", "της", "των", "την", "τον", "το", "τα", "τη", "η", "ο", "οι",
    "τις", "τους", "για", "με", "σε", "να", "απο", "που", "στο", "στην", "στη",
    "στον", "στα", "στις", "στους", "κατα", "ειναι", "δεν", "θα", "οτι", "ως", "αν",
}

# Letters only, in any script: digits and punctuation are not words here.
WORD_RE = re.compile(r"[^\W\d_]+")


def normalize_for_metrics(text):
    # Unify line endings (PDFium emits \r\n) and Unicode composition, so the
    # same visible text compares equal whichever library produced it.
    return unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))


def fold(word):
    # Lowercase and strip accents so 'ΚΑΙ' and 'και' count as the same word.
    decomposed = unicodedata.normalize("NFD", word.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def is_greek(ch):
    # Basic Greek block plus Greek Extended (polytonic forms).
    code = ord(ch)
    return 0x0370 <= code <= 0x03FF or 0x1F00 <= code <= 0x1FFF

def is_latin(ch):
    # ASCII plus Latin-1 and Latin Extended letters: where Greek look-alikes
    # (A, E, O, P, ...) land when a PDF encodes them with the wrong alphabet.
    return ch.isalpha() and ord(ch) < 0x0250


def mixed_script(word):
    # A real word is written in one alphabet; mixing Greek and Latin letters
    # usually means look-alike characters, which silently defeat search and regex.
    return any(is_greek(ch) for ch in word) and any(is_latin(ch) for ch in word)    


def page_scores(text):
    letters = [ch for ch in text if ch.isalpha()]
    words = Counter(fold(w) for w in WORD_RE.findall(text))
    total_words = sum(words.values())
    if len(letters) < MIN_LETTERS or total_words == 0:
        return len(letters), None, None, words
    greek_ratio = sum(is_greek(ch) for ch in letters) / len(letters)
    function_ratio = sum(n for w, n in words.items() if w in FUNCTION_WORDS) / total_words
    return len(letters), greek_ratio, function_ratio, words


def weighted_jaccard(a, b):
    # Counts repeated words, so a page that loses half its text scores lower
    # than one that merely reads the same words in a different order.
    union = sum((a | b).values())
    return sum((a & b).values()) / union if union else None


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def fmt(value):
    return "  n/a" if value is None else f"{value:.3f}"


def load(tool, adam):
    return json.loads((EXTRACTIONS_DIR / tool / f"{adam}.json").read_text(encoding="utf-8"))


def score_all():
    adams = sorted(p.stem for p in (EXTRACTIONS_DIR / TOOLS[0]).glob("*.json"))
    rows = []
    for adam in adams:
        docs = {tool: load(tool, adam) for tool in TOOLS}
        # Tools that failed on a document were already reported by the extraction run.
        docs = {tool: doc for tool, doc in docs.items() if not doc["error"]}
        if not docs:
            continue
        page_count = len(next(iter(docs.values()))["pages"])

        for i in range(page_count):
            scored = {
                tool: page_scores(normalize_for_metrics(doc["pages"][i]["text"]))
                for tool, doc in docs.items()
            }
            for tool, (letters, greek, function, words) in scored.items():
                agreement = None
                if greek is not None:
                    pairs = [weighted_jaccard(words, scored[other][3]) for other in scored if other != tool]
                    agreement = mean(pairs)
                rows.append({
                    "adam": adam,
                    "tool": tool,
                    "page": i + 1,
                    "letters": letters,
                    "greek_ratio": greek,
                    "function_word_ratio": function,
                    "agreement": agreement,
                    "mixed_words": sum(n for w, n in words.items() if mixed_script(w)),
                    "mixed_examples": " ".join(sorted(w for w in words if mixed_script(w)))[:200],
                })
    return rows


def write_csv(rows):
    # BOM so the file opens correctly in Excel; values rounded for readability only.
    with OUT_PATH.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: round(v, 3) if isinstance(v, float) else v for k, v in row.items()})


def print_summary(rows):
    scored = [r for r in rows if r["greek_ratio"] is not None]

    # A histogram rather than a threshold: where good and bad pages separate
    # should be read from the data, not guessed in advance.
    print("Pages per Greek-letter ratio bucket (scored pages only):")
    print("bucket     " + "".join(f"{t:>12}" for t in TOOLS))
    for b in range(10):
        counts = [
            sum(1 for r in scored if r["tool"] == t and min(int(r["greek_ratio"] * 10), 9) == b)
            for t in TOOLS
        ]
        print(f"{b / 10:.1f}-{(b + 1) / 10:.1f}    " + "".join(f"{c:>12}" for c in counts))

    print("\nPer tool:")
    print(f"{'tool':<11} {'scored':>7} {'unscored':>9} {'greek':>7} {'function':>9} {'agree':>7}")
    for t in TOOLS:
        mine = [r for r in rows if r["tool"] == t]
        ok = [r for r in mine if r["greek_ratio"] is not None]
        print(
            f"{t:<11} {len(ok):>7} {len(mine) - len(ok):>9} "
            f"{fmt(mean(r['greek_ratio'] for r in ok)):>7} "
            f"{fmt(mean(r['function_word_ratio'] for r in ok)):>9} "
            f"{fmt(mean(r['agreement'] for r in ok)):>7}"
        )

    print("\nKnown problem documents (mean greek / min greek / mean function words):")
    for adam in PROBLEM_DOCS:
        print(f"  {adam}")
        for t in TOOLS:
            mine = [r for r in scored if r["adam"] == adam and r["tool"] == t]
            greek = [r["greek_ratio"] for r in mine]
            print(
                f"    {t:<11} {fmt(mean(greek))} / {fmt(min(greek) if greek else None)} / "
                f"{fmt(mean(r['function_word_ratio'] for r in mine))}"
            )

    print("\nMixed Greek/Latin words (words / pages / most frequent):")
    for t in TOOLS:
        mine = [r for r in rows if r["tool"] == t]
        total = sum(r["mixed_words"] for r in mine)
        pages = sum(1 for r in mine if r["mixed_words"])
        examples = Counter(w for r in mine for w in r["mixed_examples"].split())
        top = ", ".join(w for w, _ in examples.most_common(8))
        print(f"  {t:<11} {total:>5} / {pages:>4} / {top}")            


def main():
    rows = score_all()
    write_csv(rows)
    print(f"Wrote {len(rows)} rows to {OUT_PATH.relative_to(PROJECT_ROOT)}\n")
    print_summary(rows)


if __name__ == "__main__":
    main()