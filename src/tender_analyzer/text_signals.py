"""Measurable signals of whether a page's extracted text can be trusted."""

import re
import unicodedata

# Lowercase, accent-free forms. Frequent in any real Greek prose; a broken font
# map turns them into non-words ("την" -> "τθν"), so their share drops sharply.
FUNCTION_WORDS = {
    "και", "του", "της", "των", "την", "τον", "το", "τα", "τη", "η", "ο", "οι",
    "τις", "τους", "για", "με", "σε", "να", "απο", "που", "στο", "στην", "στη",
    "στον", "στα", "στις", "στους", "κατα", "ειναι", "δεν", "θα", "οτι", "ως", "αν",
}

WORD_RE = re.compile(r"[^\W\d_]+")


def _fold(word):
    decomposed = unicodedata.normalize("NFD", word.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def _in_greek_blocks(ch):
    code = ord(ch)
    return 0x0370 <= code <= 0x03FF or 0x1F00 <= code <= 0x1FFF


def letter_count(text):
    return sum(ch.isalpha() for ch in text)


def greek_letter_ratio(text):
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return None
    return sum(_in_greek_blocks(ch) for ch in letters) / len(letters)


def function_word_ratio(text):
    words = [_fold(w) for w in WORD_RE.findall(text)]
    if not words:
        return None
    return sum(w in FUNCTION_WORDS for w in words) / len(words)


def unassigned_greek_count(text):
    # Code points inside the Greek blocks that map to no character (e.g. U+03A2).
    # Real text never contains them; a broken font map can.
    return sum(
        1 for ch in text if _in_greek_blocks(ch) and unicodedata.category(ch) == "Cn"
    )

# Below this many sigma-bearing words, one misplaced sigma swings the ratio too
# much to mean anything, so the signal is reported as unavailable.
MIN_SIGMA_WORDS = 5


def sigma_position_error_ratio(text):
    """Share of words with a sigma in an impossible position.

    Correct Greek uses 'ς' only at the end of a word and 'σ' never there.
    A broken font map swaps them, so the rule breaks constantly; tables and
    lists keep it even when they contain no function words.
    """
    words = [w for w in WORD_RE.findall(text) if len(w) >= 2 and ("σ" in w or "ς" in w)]
    if len(words) < MIN_SIGMA_WORDS:
        return None
    errors = sum(1 for w in words if "ς" in w[:-1] or w[-1] == "σ")
    return errors / len(words)