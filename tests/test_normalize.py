from tender_analyzer.normalize import normalize_text


def test_micro_sign_inside_greek_word_becomes_greek_mu():
    assert normalize_text("συ\u00b5βάσεων") == "συμβάσεων"


def test_micro_sign_in_latin_unit_is_kept():
    assert normalize_text("10 \u00b5m") == "10 \u00b5m"


def test_latin_lookalikes_inside_greek_word_are_fixed():
    # Inputs mix ASCII letters with Greek ones, as observed in the sample.
    assert normalize_text("to" + "ν") == "τον"
    assert normalize_text("ΧΡ" + "O" + "ΝΟΣ") == "ΧΡΟΝΟΣ"


def test_pure_latin_text_is_untouched():
    text = "Azure Kubernetes Services (AKS), ISO 9001"
    assert normalize_text(text) == text


def test_plain_greek_text_is_untouched():
    text = "Εγγύηση συμμετοχής 2% επί της εκτιμώμενης αξίας"
    assert normalize_text(text) == text


def test_superscript_is_not_turned_into_a_digit():
    assert normalize_text("15.000² €") == "15.000² €"


def test_registry_stamp_line_is_removed():
    text = "κείμενο\n24PROC014901882 2024-06-07\nσυνέχεια"
    assert normalize_text(text) == "κείμενο\nσυνέχεια"


def test_adam_quoted_inside_a_sentence_is_kept():
    text = "Η ανάρτηση 24PROC014901882 2024-06-07 ισχύει."
    assert normalize_text(text) == text


def test_windows_line_endings_are_unified():
    assert normalize_text("α\r\nβ") == "α\nβ"

def test_roman_numeral_with_greek_iota_becomes_latin():
    # Greek capital Iota mixed with Latin V, as found in "Παράρτημα ΙV".
    assert normalize_text("\u0399V") == "IV"
    assert normalize_text("V\u0399\u0399") == "VII"


def test_roman_numeral_is_not_turned_into_greek():
    # Without the roman-numeral rule running first, this would become Greek 'ΙΧ'.
    assert normalize_text("\u0399X") == "IX"


def test_latin_x_inside_greek_word_becomes_chi():
    assert normalize_text("τουλά" + "x" + "ιστον") == "τουλάχιστον"


def test_latin_i_with_diaeresis_inside_greek_word_is_fixed():
    assert normalize_text("Ευρωπα\u00efκού") == "Ευρωπα\u03caκού"


def test_degrees_celsius_is_untouched():
    # Greek omicron used as a degree sign next to Latin C: must stay as written.
    assert normalize_text("25 οC") == "25 οC"    

def test_latin_capital_i_with_diaeresis_inside_greek_word_is_fixed():
    assert normalize_text("ΕΥΡΩΠΑ\u00cfΚΟΥ") == "ΕΥΡΩΠΑ\u03aaΚΟΥ"