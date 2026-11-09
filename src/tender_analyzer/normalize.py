"""Targeted text normalization for Greek tender PDFs.

Each rule fixes a problem observed in the sample documents; the characters
were chosen with scripts/scan_odd_characters.py. A blanket Unicode
normalization (NFKC) is deliberately avoided: it also rewrites superscripts as
plain digits, which would glue footnote markers onto amounts
('15.000²' would become '15.0002').
"""

import re

# Look-alikes that should be Greek when they appear inside a Greek word:
# Latin letters, MICRO SIGN and Latin 'ï', all seen in the sample.
# Latin 'c' is deliberately absent: in the sample 'οC' means degrees Celsius,
# and mapping it would corrupt every temperature in the specifications.
LOOKALIKE_TO_GREEK = str.maketrans({
    "\u00b5": "\u03bc",  # MICRO SIGN -> GREEK SMALL LETTER MU
    "\u00ef": "\u03ca",  # LATIN SMALL I WITH DIAERESIS -> GREEK SMALL IOTA WITH DIALYTIKA
    "\u00cf": "\u03aa",  # LATIN CAPITAL I WITH DIAERESIS -> GREEK CAPITAL IOTA WITH DIALYTIKA
    "A": "Α", "B": "Β", "E": "Ε", "H": "Η", "I": "Ι", "K": "Κ", "M": "Μ",
    "N": "Ν", "O": "Ο", "P": "Ρ", "T": "Τ", "X": "Χ", "Y": "Υ", "Z": "Ζ",
    "o": "ο", "t": "τ", "v": "ν", "x": "χ",
})
LOOKALIKE_CODES = set(LOOKALIKE_TO_GREEK)

# Roman numerals ("Παράρτημα IV") are written in Latin letters, so a mixed word
# made only of I, V, X look-alikes goes the other way: Greek Iota and Chi to Latin.
ROMAN_LETTERS = set("IVXivx") | {"Ι", "Χ", "ι", "χ"}
GREEK_TO_LATIN_ROMAN = str.maketrans({"Ι": "I", "Χ": "X", "ι": "i", "χ": "x"})

# INCREMENT (a math symbol) used in place of capital delta by some fonts.
# It is not a letter, so it splits words ("ΤΣΟΛΑΚΙ∆ΟΥ") before the mixed-word
# rule can see them; it is therefore replaced first and everywhere.
INCREMENT_SIGN = "\u2206"
GREEK_CAPITAL_DELTA = "\u0394"

# One font in the sample maps lowercase pi to COMBINING PLUS SIGN BELOW
# followed by a space or line break ("Υ̟ ηρεσιών"). The mark has no legitimate
# use in Greek text, so it and that one following break become pi.
BROKEN_PI = re.compile("\u031f\\s?")

# Invisible hyphenation hint from word processors; inside a word it breaks search.
SOFT_HYPHEN = "\u00ad"

LETTER_RUN = re.compile(r"[^\W\d_]+")

# The KHMDHS registry stamps "<ADAM> <date>" on every page. It is registry
# metadata, not tender content, and would otherwise repeat in every search hit.
# Matched only as a whole line, so an ADAM quoted inside a sentence is kept.
REGISTRY_STAMP_LINE = re.compile(
    r"^[ \t]*\d{2}PROC\d{9}[ \t]+\d{4}-\d{2}-\d{2}[ \t]*(?:\n|$)", re.MULTILINE
)


def _is_greek(ch):
    code = ord(ch)
    return 0x0370 <= code <= 0x03FF or 0x1F00 <= code <= 0x1FFF


def _is_non_greek_letter(ch):
    return ch.isalpha() and not _is_greek(ch)


def _fix_mixed_word(match):
    word = match.group()
    if not (any(_is_greek(c) for c in word) and any(_is_non_greek_letter(c) for c in word)):
        return word
    # Must run before the Greek mapping, which would otherwise turn 'ΙX' into
    # the pure-Greek 'ΙΧ' and lose the numeral.
    if set(word) <= ROMAN_LETTERS:
        return word.translate(GREEK_TO_LATIN_ROMAN)
    if any(ord(c) in LOOKALIKE_CODES for c in word):
        return word.translate(LOOKALIKE_TO_GREEK)
    return word


def normalize_text(text):
    """Return a search-friendly version of page text; the raw text is kept separately."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = REGISTRY_STAMP_LINE.sub("", text)
    # Character-level repairs come before the word-level rule, because they
    # rejoin words that the mixed-word rule would otherwise see in pieces.
    text = text.replace(INCREMENT_SIGN, GREEK_CAPITAL_DELTA)
    text = BROKEN_PI.sub("π", text)
    text = text.replace(SOFT_HYPHEN, "")
    return LETTER_RUN.sub(_fix_mixed_word, text)