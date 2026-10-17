from jasem.nlp.normalize import (
    convert_numbers_for_speech,
    fold_chars,
    normalize_digits,
    normalize_text,
    number_to_persian_words,
    split_sentences,
    wake_normalize,
)


def test_arabic_variants_folded():
    assert fold_chars("جاسم يك برنامه كاربردي است") == "جاسم یک برنامه کاربردی است"


def test_arabic_and_persian_digits():
    assert normalize_digits("سال ۱۴۰۳ و ٥ واحد") == "سال 1403 و 5 واحد"


def test_diacritics_stripped():
    assert normalize_text("جاسِم داره حرف می‌زنه") == "جاسم داره حرف می‌زنه"


def test_normalize_whitespace():
    assert normalize_text("  سلام   جاسم ") == "سلام جاسم"


def test_wake_normalize_removes_spaces_zwnj():
    assert wake_normalize("هی‌جاسم !") == wake_normalize("هی جاسم")
    assert wake_normalize("سلام جاسم") == "سلامجاسم"


def test_number_words():
    assert number_to_persian_words(0) == "صفر"
    assert number_to_persian_words(21) == "بیست و یک"
    assert number_to_persian_words(125) == "صد و بیست و پنج"
    assert number_to_persian_words(1205) == "یک هزار و دویست و پنج"
    assert number_to_persian_words(-3) == "منفی سه"


def test_convert_numbers_for_speech():
    out = convert_numbers_for_speech("۵ + ۷")
    assert "پنج" in out and "هفت" in out


def test_split_sentences():
    parts = split_sentences("سلام جاسم. حالت چطوره؟ خوبی!")
    assert parts == ["سلام جاسم.", "حالت چطوره؟", "خوبی!"]


def test_split_long_sentence_respects_max():
    long_text = "این یک جملهٔ خیلی طولانی است " * 30
    parts = split_sentences(long_text, max_chars=80)
    assert all(len(p) <= 80 for p in parts)
    assert len(parts) > 1
