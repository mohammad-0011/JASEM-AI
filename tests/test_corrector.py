from jasem.stt.correction import Corrector, looks_uncertain


def test_close_variant_corrected():
    c = Corrector()
    out, changes = c.correct("جاسم برو تو کروم")
    assert "جاسم" in out
    assert changes == [] or all("->" in ch for ch in changes)


def test_mishear_variant_corrected():
    c = Corrector()
    out, changes = c.correct("جستم بگو چه خبره")
    assert "جاسم" in out


def test_correct_term_untouched():
    c = Corrector()
    out, changes = c.correct("سلام جاسم")
    assert out == "سلام جاسم"
    assert changes == []


def test_unrelated_word_not_changed():
    c = Corrector()
    original = "امروز هوا خیلی عالیه"
    out, changes = c.correct(original)
    assert out == original
    assert changes == []


def test_disabled_corrector_is_noop():
    c = Corrector(enabled=False)
    out, changes = c.correct("جستم بگو")
    assert out == "جستم بگو" and changes == []


def test_extra_vocabulary():
    c = Corrector(extra_terms=["مفیدوبان"])
    out, changes = c.correct("پروژه مفيدوبان رو باز کن")
    assert "مفیدوبان" in out


def test_uncertainty_flags():
    assert looks_uncertain(0.2, 0.55, "متن")
    assert looks_uncertain(0.9, 0.55, "متن") is False
    assert looks_uncertain(0.9, 0.55, "   ")
