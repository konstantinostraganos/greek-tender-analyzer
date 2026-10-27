from tender_analyzer.text_signals import sigma_position_error_ratio, unassigned_greek_count


def test_correct_greek_has_no_sigma_errors():
    text = "Η προσφορά της εταιρείας υποβάλλεται στην πλατφόρμα σύμφωνα με τους όρους"
    assert sigma_position_error_ratio(text) == 0


def test_broken_font_map_text_has_many_sigma_errors():
    # Real output from 24PROC014975454, a document with a broken font map.
    text = "αντιδραςτθρίων τεςτ ςυντάχκθκε παροφςα ςφμβαςθ ακολοφκωσ"
    assert sigma_position_error_ratio(text) > 0.8


def test_table_without_function_words_is_not_flagged():
    # The case where the function-word ratio fails: correct text, no short words.
    text = "Γάλα πλήρες / Τυρί φέτα / Σαπούνι υγρό / Ρύζι γλασέ / Φασόλια μέτρια / Πατάτες νέες"
    assert sigma_position_error_ratio(text) == 0


def test_too_few_sigma_words_gives_no_verdict():
    assert sigma_position_error_ratio("Γάλα πλήρες 1 λίτρο") is None


def test_unassigned_greek_code_point_is_counted():
    assert unassigned_greek_count("ΥΡΟΥ\u03a2ΓΕΙΟ") == 1
    assert unassigned_greek_count("ΥΠΟΥΡΓΕΙΟ") == 0