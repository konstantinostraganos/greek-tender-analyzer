"""List unusual characters that sit next to Greek letters in the extracted text.

So far two were found by eye: U+031F in place of lowercase pi and U+2206 in
place of capital delta. This scan finds every such character at once, so new
normalization rules rest on what actually occurs, not on cases seen by chance.
"""

import sys
import json
import unicodedata
from tender_analyzer.normalize import normalize_text
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTIONS_DIR = PROJECT_ROOT / "data" / "processed" / "extractions" / "pymupdf"

# Marks (M), symbols (S) and other/unassigned code points (C) are where
# look-alikes and broken font maps show up. Letters, digits and ordinary
# punctuation are excluded, and so are currency signs such as €.
SUSPECT_CLASSES = ("M", "S", "C")
IGNORED_CATEGORIES = {"Sc"}
LINE_BREAKS = {"\n", "\r", "\t"}

TOP = 25
EXAMPLES_PER_CHAR = 3
CONTEXT = 8


def is_greek_letter(ch):
    code = ord(ch)
    return ch.isalpha() and (0x0370 <= code <= 0x03FF or 0x1F00 <= code <= 0x1FFF)


def is_suspect(ch):
    category = unicodedata.category(ch)
    return (
        ch not in LINE_BREAKS
        and category[0] in SUSPECT_CLASSES
        and category not in IGNORED_CATEGORIES
    )


def near_greek(text, i):
    # Looks one step past a space on each side, because U+031F is followed by
    # a space before the rest of the word ("Υ̟ ηρεσιών").
    for j in (i - 1, i - 2, i + 1, i + 2):
        if 0 <= j < len(text) and is_greek_letter(text[j]):
            return True
    return False


def scan():
    counts = Counter()
    docs = defaultdict(set)
    examples = defaultdict(list)
    for path in sorted(EXTRACTIONS_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for page in doc["pages"]:
            # "--normalized" scans the text the application uses, to confirm
            # that normalization rules removed what they were meant to.
            text = normalize_text(page["text"]) if "--normalized" in sys.argv else page["text"]
            for i, ch in enumerate(text):
                if not (is_suspect(ch) and near_greek(text, i)):
                    continue
                counts[ch] += 1
                docs[ch].add(doc["adam"])
                if len(examples[ch]) < EXAMPLES_PER_CHAR:
                    snippet = text[max(0, i - CONTEXT): i + CONTEXT + 1].replace("\n", " | ")
                    examples[ch].append(f"{doc['adam']} p{page['page']}: {snippet!r}")
    return counts, docs, examples


def main():
    counts, docs, examples = scan()
    print(f"Distinct suspect characters next to Greek letters: {len(counts)}\n")

    # Ranked by how many documents are affected: one document with thousands
    # of hits matters less than a character that recurs across publishers.
    ranked = sorted(counts, key=lambda ch: (-len(docs[ch]), -counts[ch]))
    for ch in ranked[:TOP]:
        name = unicodedata.name(ch, "<unassigned>")
        category = unicodedata.category(ch)
        print(f"U+{ord(ch):04X}  {category}  count={counts[ch]:>6}  docs={len(docs[ch]):>2}  {name}")
        for example in examples[ch]:
            print(f"      {example}")


if __name__ == "__main__":
    main()