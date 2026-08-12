"""M2 配置读取与类型转换测试。"""

from pathlib import Path

import pytest

from app.config import ConfigurationError, PROJECT_ROOT, Settings


def valid_env() -> dict[str, str]:
    """返回不含真实密钥的完整测试配置。"""

    return {
        "LLM_PROVIDER": "openai_compatible",
        "LLM_BASE_URL": "https://api.deepseek.com/v1/",
        "LLM_MODEL": "deepseek-v4-flash",
        "LLM_API_KEY": "test-key-not-real",
        "LLM_TIMEOUT": "60",
        "LLM_MAX_RETRIES": "2",
        "LLM_THINKING_ENABLED": "false",
        "LLM_JSON_MODE": "true",
        "EXTRACT_MAX_CHARS": "12000",
        "BATCH_CONCURRENCY": "3",
        "DB_PATH": "storage/test.db",
        "LOG_LEVEL": "info",
        "LOG_PATH": "logs/test.log",
    }


def test_settings_converts_env_strings_to_types() -> None:
    settings = Settings.from_env(valid_env())

    assert settings.llm_timeout == 60.0
    assert settings.llm_max_retries == 2
    assert settings.llm_thinking_enabled is False
    assert settings.llm_json_mode is True
    assert settings.llm_base_url == "https://api.deepseek.com/v1"
    assert settings.db_path == PROJECT_ROOT / Path("storage/test.db")
    assert settings.log_level == "INFO"


def test_missing_api_key_has_friendly_error() -> None:
    env = valid_env()
    env["LLM_API_KEY"] = ""

    with pytest.raises(ConfigurationError, match="LLM_API_KEY"):
        Settings.from_env(env)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM_TIMEOUT", "0"),
        ("LLM_MAX_RETRIES", "-1"),
        ("BATCH_CONCURRENCY", "many"),
        ("LLM_JSON_MODE", "sometimes"),
    ],
)
def test_invalid_setting_has_friendly_error(name: str, value: str) -> None:
    env = valid_env()
    env[name] = value

    with pytest.raises(ConfigurationError, match=name):
        Settings.from_env(env)
