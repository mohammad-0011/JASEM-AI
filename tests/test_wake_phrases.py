from jasem.wake.phrases import PhraseMatcher


def make_matcher(cooldown_ms=0):
    return PhraseMatcher(
        phrases=["هی جاسم", "سلام جاسم", "جاسم", "hey jasem"],
        stop_phrases=["ساکت شو", "stop"],
        cooldown_ms=cooldown_ms,
    )


def test_primary_phrase_matches():
    m = make_matcher()
    hit = m.match("هی جاسم یه سوال دارم")
    assert hit is not None and hit.phrase == "هی جاسم"


def test_zwnj_variant_matches():
    m = make_matcher()
    assert m.match("هی‌جاسم") is not None


def test_salam_phrase_matches():
    m = make_matcher()
    hit = m.match("سلام جاسم خوبی؟")
    assert hit is not None and hit.phrase == "سلام جاسم"


def test_english_phrase_matches():
    m = make_matcher()
    assert m.match("hey jasem", source="en") is not None


def test_bare_name_in_long_sentence_rejected():
    m = make_matcher()
    # A random sentence merely containing the name should NOT activate.
    assert m.match("دیشب که جاسم اومد خونه ما خیلی خندیدیم") is None


def test_bare_name_short_utterance_matches():
    m = make_matcher()
    assert m.match("جاسم") is not None


def test_cooldown_debounce():
    m = make_matcher(cooldown_ms=10_000)
    assert m.match("هی جاسم") is not None
    assert m.match("هی جاسم") is None  # debounced
    m.reset_cooldown()
    assert m.match("هی جاسم") is not None


def test_stop_phrases():
    m = make_matcher()
    assert m.is_stop("ساکت شو لطفاً")
    assert m.is_stop("stop")
    assert not m.is_stop("ادامه بده")
