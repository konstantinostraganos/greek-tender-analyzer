import pytest

from tender_analyzer.reliability import assess_reliability


def test_correct_greek_page_is_reliable():
    result = assess_reliability("Η προσφορά της εταιρείας υποβάλλεται στην πλατφόρμα σύμφωνα με τους όρους")
    assert result.reliable
    assert result.issues == ()


def test_table_without_function_words_is_reliable():
    result = assess_reliability("Γάλα πλήρες / Τυρί φέτα / Σαπούνι υγρό / Ρύζι γλασέ / Φασόλια μέτρια / Πατάτες νέες")
    assert result.reliable


def test_sigma_swap_corruption_is_flagged():
    # Lowercase text from 24PROC014975454: no unassigned characters, only sigma errors.
    result = assess_reliability("αντιδραςτθρίων τεςτ ςυντάχκθκε παροφςα ςφμβαςθ ακολοφκωσ")
    assert not result.reliable
    assert result.issues == ("sigma_position_errors",)


def test_uppercase_corruption_is_flagged_by_unassigned_characters():
    # Uppercase-only table of contents: no lowercase sigma, so only this signal can fire.
    result = assess_reliability("ΡΑ\u03a2Α\u03a2ΤΘΜΑΤΑ ΥΡΟΥ\u03a2ΓΕΙΟ")
    assert not result.reliable
    assert result.issues == ("unassigned_greek_characters",)


def test_second_corruption_pattern_is_flagged_when_uppercase_is_present():
    # 24PROC014908295: sigma becomes zeta, so the sigma signal stays low.
    result = assess_reliability("\u03a2ηα πλαίζια ηυν ζύμβαζη ηνπ Γηνηθεηηθνχ \u03a2πκβνπιίνπ")
    assert not result.reliable
    assert "unassigned_greek_characters" in result.issues


@pytest.mark.xfail(reason="Known blind spot: second corruption pattern in lowercase-only text")
def test_second_corruption_pattern_in_lowercase_only_text():
    result = assess_reliability("ηα πλαίζια ηυν ζύμβαζη ηνπ λνζνθνκείνπ παξαθαινχκε")
    assert not result.reliable

def test_scanned_page_is_flagged():
    # Only a header survives extraction; the rest of the page is an image.
    result = assess_reliability("Σελίδα 53", image_coverage=0.6)
    assert not result.reliable
    assert result.issues == ("possibly_scanned",)


def test_blank_page_is_reliable():
    # Nothing to read and nothing hidden: not a problem.
    assert assess_reliability("", image_coverage=0.0).reliable


def test_short_page_without_image_is_reliable():
    # A signature page: little text, but nothing the extractor missed.
    result = assess_reliability("Ο ΥΠΕΥΘΥΝΟΣ ΤΜΗΜΑΤΟΣ", image_coverage=0.0)
    assert result.reliable


def test_page_with_text_and_large_image_is_reliable():
    # A large logo or diagram does not hide anything when the text is extracted.
    text = "Η προσφορά της εταιρείας υποβάλλεται στην πλατφόρμα σύμφωνα με τους όρους της διακήρυξης"
    assert assess_reliability(text, image_coverage=0.6).reliable    