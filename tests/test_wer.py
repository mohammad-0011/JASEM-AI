from eval.wer import aggregate, cer, wer


def test_perfect_match():
    assert wer("سلام جاسم خوبی", "سلام جاسم خوبی") == 0.0
    assert cer("سلام", "سلام") == 0.0


def test_one_substitution():
    assert wer("a b c d", "a x c d") == 0.25


def test_insertions_and_deletions_count():
    assert wer("a b c", "a b c d e") == 2 / 3
    assert wer("a b c d e", "a b c") == 2 / 5


def test_cer_normalizes_arabic_chars():
    assert cer("جاسم يک برنامه است", "جاسم یک برنامه است") == 0.0


def test_empty_reference():
    assert wer("", "") == 0.0
    assert wer("", "حرف") == 1.0


def test_aggregate_pooled():
    res = aggregate([("a b c", "a b c"), ("x y", "x z")])
    assert res["items"] == 2
    assert abs(res["wer"] - 1 / 5) < 1e-9
