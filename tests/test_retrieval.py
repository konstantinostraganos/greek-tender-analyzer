from types import SimpleNamespace

from tender_analyzer.retrieval import BM25, rank_pages, tokenize


def page(number, text, reliable=True):
    return SimpleNamespace(number=number, text=text, reliable=reliable)


def test_tokens_are_folded_and_digits_dropped():
    assert tokenize("Εγγύηση ΣΥΜΜΕΤΟΧΗΣ 2%") == ["εγγυηση", "συμμετοχης"]


def test_stems_join_inflected_forms():
    assert tokenize("προϋπολογισθείσα προϋπολογιζόμενη", stem=True) == ["προυπο", "προυπο"]


def test_page_with_all_query_words_ranks_first():
    pages = [
        page(1, "προμήθεια υλικών για το νοσοκομείο"),
        page(2, "εγγύηση συμμετοχής ποσού 2%"),
        page(3, "εγγύηση καλής εκτέλεσης"),
    ]
    assert rank_pages(pages, "εγγύηση συμμετοχής")[0] == 2


def test_word_on_every_page_adds_less_than_a_rare_word():
    model = BM25(["νοσοκομείο εγγύηση", "νοσοκομείο", "νοσοκομείο"])
    common, rare = model.scores("νοσοκομείο"), model.scores("εγγύηση")
    assert rare[0] > common[0]


def test_unreadable_pages_are_never_returned():
    pages = [page(1, "εγγύηση συμμετοχής", reliable=False), page(2, "κείμενο")]
    assert rank_pages(pages, "εγγύηση") == [2]


def test_ties_keep_document_order():
    pages = [page(1, "άλλο κείμενο"), page(2, "διαφορετικό κείμενο")]
    assert rank_pages(pages, "εγγύηση") == [1, 2]
