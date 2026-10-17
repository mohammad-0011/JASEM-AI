from jasem.nlp.intents import match_confirmation, match_intent


def test_open_app():
    it = match_intent("برنامه کروم رو باز کن")
    assert it and it.name == "open_app" and "کروم" in it.args["name"]


def test_open_app_english():
    it = match_intent("notepad باز کن")
    assert it and it.name == "open_app"


def test_volume_up():
    it = match_intent("صدا رو ببر بالا")
    assert it and it.name == "volume_set" and it.args["direction"] == "up"


def test_volume_set_level():
    it = match_intent("صدا رو روی ۵۰ بذار")
    assert it and it.name == "volume_set" and it.args["level"] == 50


def test_system_info():
    it = match_intent("وضعیت سیستمم چطوره")
    assert it and it.name == "system_info"


def test_disk_space():
    it = match_intent("فضای دیسک چقدره")
    assert it and it.name == "disk_space"


def test_calculate_expression():
    it = match_intent("حساب کن ۲۵ * ۴")
    assert it and it.name == "calculate"
    assert "25" in it.args["expression"]


def test_calculate_words():
    it = match_intent("حساب کن ۲۵ به علاوه ۱۷")
    assert it and it.name == "calculate"
    assert "25" in it.args["expression"] and "17" in it.args["expression"]


def test_web_search():
    it = match_intent("دنبال آموزش پایتون بگرد")
    assert it and it.name == "web_search" and "پایتون" in it.args["query"]


def test_find_file():
    it = match_intent("فایل گزارش رو پیدا کن")
    assert it and it.name == "find_file" and "گزارش" in it.args["query"]


def test_reminder():
    it = match_intent("یادآوری کن که قرصمو بخورم ۲۰ دقیقه دیگه")
    assert it and it.name == "reminder" and it.args["seconds"] == 1200


def test_create_note():
    it = match_intent("یادداشت خرید هفتگی بنویس")
    assert it and it.name == "create_note"


def test_open_url():
    it = match_intent("سایت github.com رو باز کن")
    assert it and it.name == "open_url"


def test_stop_and_repeat():
    assert match_intent("ساکت شو").name == "stop_speaking"
    assert match_intent("دوباره بگو").name == "repeat"


def test_confirmation_answers():
    assert match_confirmation("بله") is True
    assert match_confirmation("آره") is True
    assert match_confirmation("خیر") is False
    assert match_confirmation("نه") is False
    assert match_confirmation("ساعت چنده") is None


def test_no_false_positive_on_chat():
    assert match_intent("دیشب خواب خوبی دیدم") is None
