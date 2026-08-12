"""从本地 ``.env`` 读取并校验项目配置。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"


class ConfigurationError(ValueError):
    """配置缺失或取值无效。"""


@dataclass(frozen=True, slots=True)
class Settings:
    """经过类型转换和校验的集中配置。"""

    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    llm_timeout: float
    llm_max_retries: int
    llm_thinking_enabled: bool
    llm_json_mode: bool
    extract_max_chars: int
    batch_concurrency: int
    input_dir: Path
    output_dir: Path
    db_path: Path
    log_level: str
    log_path: Path

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        env_path: Path = DEFAULT_ENV_PATH,
    ) -> "Settings":
        """加载配置。

        正常运行时读取项目根目录的 ``.env``；测试可以传入字典，完全绕开真实
        API Key，避免测试意外消耗余额。
        """

        if env is None:
            load_dotenv(dotenv_path=env_path, override=False)
            source: Mapping[str, str] = os.environ
        else:
            source = env

        provider = _required(source, "LLM_PROVIDER")
        if provider != "openai_compatible":
            raise ConfigurationError(
                "LLM_PROVIDER 当前仅支持 openai_compatible"
            )

        api_key = _required(source, "LLM_API_KEY")
        if api_key == "your-api-key-here":
            raise ConfigurationError("LLM_API_KEY 仍是模板值，请在 .env 中填写")

        base_url = _required(source, "LLM_BASE_URL").rstrip("/")
        if not base_url.startswith(("https://", "http://")):
            raise ConfigurationError("LLM_BASE_URL 必须以 http:// 或 https:// 开头")

        return cls(
            llm_provider=provider,
            llm_base_url=base_url,
            llm_model=_required(source, "LLM_MODEL"),
            llm_api_key=api_key,
            llm_timeout=_positive_float(source, "LLM_TIMEOUT", "60"),
            llm_max_retries=_non_negative_int(
                source, "LLM_MAX_RETRIES", "2"
            ),
            llm_thinking_enabled=_boolean(
                source, "LLM_THINKING_ENABLED", "false"
            ),
            llm_json_mode=_boolean(source, "LLM_JSON_MODE", "true"),
            extract_max_chars=_positive_int(
                source, "EXTRACT_MAX_CHARS", "12000"
            ),
            batch_concurrency=_positive_int(
                source, "BATCH_CONCURRENCY", "3"
            ),
            input_dir=_path_setting(source, "INPUT_DIR", "data/inbox"),
            output_dir=_path_setting(source, "OUTPUT_DIR", "data/output"),
            db_path=_path_setting(source, "DB_PATH", "storage/app.db"),
            log_level=source.get("LOG_LEVEL", "INFO").upper(),
            log_path=_path_setting(source, "LOG_PATH", "logs/app.log"),
        )


def get_settings() -> Settings:
    """供业务模块按需获取配置，避免仅导入模块就读取密钥。"""

    return Settings.from_env()


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"缺少必填配置：{name}")
    return value


def _path_setting(
    env: Mapping[str, str],
    name: str,
    default: str,
) -> Path:
    """把相对路径解释为项目内路径，同时允许用户填写绝对路径。"""

    raw_value = env.get(name, default).strip()
    if not raw_value:
        raise ConfigurationError(f"{name} 不能为空")
    path = Path(raw_value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _boolean(env: Mapping[str, str], name: str, default: str) -> bool:
    value = env.get(name, default).strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} 必须是 true 或 false，当前为：{value}")


def _positive_int(env: Mapping[str, str], name: str, default: str) -> int:
    value = _integer(env, name, default)
    if value <= 0:
        raise ConfigurationError(f"{name} 必须大于 0")
    return value


def _non_negative_int(
    env: Mapping[str, str], name: str, default: str
) -> int:
    value = _integer(env, name, default)
    if value < 0:
        raise ConfigurationError(f"{name} 不能小于 0")
    return value


def _integer(env: Mapping[str, str], name: str, default: str) -> int:
    raw_value = env.get(name, default).strip()
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} 必须是整数，当前为：{raw_value}") from exc


def _positive_float(env: Mapping[str, str], name: str, default: str) -> float:
    raw_value = env.get(name, default).strip()
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ConfigurationError(
            f"{name} 必须是数字，当前为：{raw_value}"
        ) from exc
    if value <= 0:
        raise ConfigurationError(f"{name} 必须大于 0")
    return value
