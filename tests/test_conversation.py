from jasem.ai.conversation import Conversation
from jasem.config import ConversationConfig


def make_conv(tmp_path, **kw):
    import jasem.paths as paths

    cfg = ConversationConfig(persist_history=False, **kw)
    conv = Conversation(cfg)
    # keep tests off the real user data dir
    conv._save_history = lambda: None
    conv._save_memory = lambda: None
    return conv


def test_history_window_limits_turns(tmp_path):
    conv = make_conv(tmp_path, history_max_turns=3)
    for i in range(10):
        conv.add("user", f"msg {i}")
    msgs = conv.messages_for_prompt("SYSTEM")
    # 3 user turns kept (plus system prompt)
    assert len(msgs) == 4


def test_prompt_structure(tmp_path):
    conv = make_conv(tmp_path)
    conv.add("user", "سلام")
    conv.add("assistant", "سلامت")
    msgs = conv.messages_for_prompt("SYSTEM")
    assert msgs[0] == {"role": "system", "content": "SYSTEM"}
    assert msgs[1]["role"] == "user" and msgs[2]["role"] == "assistant"


def test_clear(tmp_path):
    conv = make_conv(tmp_path)
    conv.add("user", "x")
    conv.clear()
    assert conv.messages_for_prompt("S") == [{"role": "system", "content": "S"}]


def test_last_assistant_text(tmp_path):
    conv = make_conv(tmp_path)
    conv.add("user", "اول")
    conv.add("assistant", "جواب اول")
    assert conv.last_assistant_text() == "جواب اول"


def test_memory_disabled_by_default(tmp_path):
    conv = make_conv(tmp_path)
    conv.remember("کاربر برنامه‌نویس است")
    assert conv._memory["facts"] == []


def test_memory_enabled_stores_fact(tmp_path):
    conv = make_conv(tmp_path)
    conv.set_memory_enabled(True)
    conv.remember("کاربر برنامه‌نویس است")
    conv.remember("کاربر برنامه‌نویس است")  # dedupe
    assert conv._memory["facts"] == ["کاربر برنامه‌نویس است"]
    msgs = conv.messages_for_prompt("S")
    assert any("برنامه‌نویس" in m["content"] for m in msgs)
