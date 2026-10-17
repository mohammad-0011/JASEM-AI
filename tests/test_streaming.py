from jasem.orchestrator import _pop_sentence


def test_waits_until_sentence_complete():
    rest = "سلام جاسم"
    sent, rest2 = _pop_sentence(rest, 280)
    assert sent is None and rest2 == rest


def test_splits_on_punctuation():
    sent, rest = _pop_sentence("سلام جاسم. حالت چطوره؟", 280)
    assert sent == "سلام جاسم."
    assert rest.strip() == "حالت چطوره؟"


def test_splits_on_question_mark():
    sent, rest = _pop_sentence("حالت چطوره؟ خوبی", 280)
    assert sent == "حالت چطوره؟"
    assert rest == "خوبی"


def test_splits_on_persian_ellipsis_chars():
    sent, rest = _pop_sentence("یک؛ دو؛ سه", 280)
    assert sent == "یک؛"
    assert rest.strip() == "دو؛ سه"


def test_force_split_on_max_chars():
    long_text = "کلمه " * 200  # no punctuation, > max
    sent, rest = _pop_sentence(long_text, 80)
    assert sent is not None and len(sent) <= 80
    assert rest


def test_empty_buffer():
    sent, rest = _pop_sentence("", 280)
    assert sent is None and rest == ""
