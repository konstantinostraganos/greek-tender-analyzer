"""Rank the pages of one tender document by relevance to a field, with BM25.

Only the best few pages are sent to the LLM, because whole documents do not fit
the free tier's token limits. BM25 is written out here rather than imported:
it is short, it adds no dependency, and every step of the ranking stays visible.
The "documents" BM25 compares are the pages of a single PDF, so a word that is
on every page of that PDF (a hospital name in the header) counts for little.
"""

import math
import re
import unicodedata
from collections import Counter

# Standard BM25 settings: K1 limits how much repeating a word can add, B how much
# long pages are held back. These are the defaults of common search engines.
K1 = 1.5
B = 0.75

# Greek inflects heavily (προϋπολογισμός, προϋπολογισθείσα, προϋπολογιζόμενη);
# cutting words to their first letters is a crude stand-in for a Greek stemmer.
STEM_LENGTH = 6

WORD = re.compile(r"[^\W\d_]{2,}")

# One fixed query per field, written from the vocabulary tenders use for it.
FIELD_QUERIES = {
    "deadline": "καταληκτική ημερομηνία λήξη υποβολής παραλαβής προσφορών ώρα",
    "estimated_value": "εκτιμώμενη αξία σύμβασης προϋπολογισμός δαπάνη ΦΠΑ ευρώ",
    "bid_guarantee": "εγγύηση συμμετοχής εγγυητική επιστολή ποσοστό ποσό",
}


def fold(text):
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def tokenize(text, stem=False):
    words = WORD.findall(fold(text))
    return [word[:STEM_LENGTH] for word in words] if stem else words


class BM25:
    def __init__(self, texts, stem=False):
        self.stem = stem
        self.pages = [Counter(tokenize(text, stem)) for text in texts]
        self.lengths = [sum(counts.values()) for counts in self.pages]
        self.average_length = sum(self.lengths) / len(self.lengths) if self.pages else 0
        self.page_frequency = Counter(word for counts in self.pages for word in counts)

    def idf(self, word):
        # Rare words separate pages well; this form never goes negative for very common words.
        n, df = len(self.pages), self.page_frequency.get(word, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def scores(self, query):
        terms = set(tokenize(query, self.stem))
        results = []
        for counts, length in zip(self.pages, self.lengths):
            score = 0.0
            for word in terms:
                tf = counts.get(word, 0)
                if tf:
                    norm = K1 * (1 - B + B * length / (self.average_length or 1))
                    score += self.idf(word) * tf * (K1 + 1) / (tf + norm)
            results.append(score)
        return results


def rank_pages(pages, query, stem=False):
    """Page numbers from most to least relevant, unreadable pages left out."""
    readable = [page for page in pages if page.reliable]
    if not readable:
        return []
    scores = BM25([page.text for page in readable], stem=stem).scores(query)
    # Ties keep document order, so on equal evidence earlier pages come first.
    order = sorted(range(len(readable)), key=lambda i: (-scores[i], i))
    return [readable[i].number for i in order]
