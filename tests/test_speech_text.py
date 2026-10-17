from jasem.tts.speech_text import prepare_chunks, to_spoken


def test_urls_removed():
    out = to_spoken("این لینک رو ببین https://example.com/path و تمام")
    assert "https" not in out and "example" not in out


def test_markdown_symbols_removed():
    out = to_spoken("**مهم**: این یک `کد` است و [لینک](http://x.com) دارد")
    assert "*" not in out and "`" not in out and "](" not in out
    assert "کد" in out


def test_code_fence_removed():
    out = to_spoken("قبل از کد:\n```python\nprint('hi')\n```\nبعد از کد")
    assert "print" not in out
    assert "بعد از کد" in out


def test_numbers_become_words():
    out = to_spoken("۱۵ دقیقه دیگه یادم بنداز")
    assert "پانزده" in out


def test_numbers_preserved_when_disabled():
    out = to_spoken("۱۵ دقیقه", convert_numbers="never")
    assert "15" in out or "۱۵" in out


def test_prepare_chunks_respects_max():
    long_text = "این جمله بسیار طولانی است و باید تکه‌تکه شود. " * 20
    chunks = prepare_chunks(long_text, sentence_max_chars=120)
    assert all(len(c) <= 120 for c in chunks)
    assert len(chunks) > 1


def test_empty_input():
    assert to_spoken("") == ""
    assert prepare_chunks("") == []
