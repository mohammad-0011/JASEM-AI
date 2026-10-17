import json

from jasem.config import AppConfig, load_config, save_config


def test_defaults_load_when_missing(tmp_path):
    cfg = load_config(tmp_path / "nope.json")
    assert cfg.audio.sample_rate == 16000
    assert cfg.tts.engine == "edge"


def test_roundtrip(tmp_path):
    cfg = AppConfig()
    cfg.tts.engine = "piper"
    cfg.stt.model_size = "medium"
    cfg.personality.sarcasm = 0.9
    p = tmp_path / "config.json"
    save_config(cfg, p)
    loaded = load_config(p)
    assert loaded.tts.engine == "piper"
    assert loaded.stt.model_size == "medium"
    assert abs(loaded.personality.sarcasm - 0.9) < 1e-9


def test_unknown_keys_ignored(tmp_path):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"tts": {"engine": "piper"}, "future_section": {"x": 1},
                             "audio": {"sample_rate": 8000, "bogus": True}}),
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg.tts.engine == "piper"
    assert cfg.audio.sample_rate == 8000
    assert not hasattr(cfg, "future_section")


def test_corrupt_config_falls_back(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{ not valid json", encoding="utf-8")
    cfg = load_config(p)
    assert cfg.audio.sample_rate == 16000


def test_env_overrides_ai_provider(tmp_path, monkeypatch):
    """OPENAI_BASE_URL / OPENAI_MODEL from .env win over saved JSON."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"ai": {"base_url": "https://api.openai.com/v1",
                                    "model": "gpt-4o-mini"}}), encoding="utf-8")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("OPENAI_MODEL", "some-model-1")
    cfg = load_config(p)
    assert cfg.ai.base_url == "https://example.com/v1"
    assert cfg.ai.model == "some-model-1"


def test_no_env_keeps_saved_ai_config(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"ai": {"model": "my-saved-model"}}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.ai.model == "my-saved-model"


def test_persisted_in_user_dir_does_not_leak_secrets(tmp_path):
    cfg = AppConfig()
    saved = json.dumps({
        "ai": {"api_key_env": "OPENAI_API_KEY", "model": "gpt-4o-mini"}
    })
    assert "sk-" not in saved
