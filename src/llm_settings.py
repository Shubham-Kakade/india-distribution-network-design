"""Where the agent's LLM settings come from, and keeping the key out of sight (D-039, D-045).

Three sources, first match wins:
1. a key the visitor typed into the app, held only in that browser session's memory;
2. LLM_BASE_URL, LLM_API_KEY and LLM_MODEL from the environment or a git-ignored .env
   (local use only);
3. none, which is offline mode.

With PUBLIC_DEMO=1, set only in the hosting platform's settings, the environment and .env are
ignored entirely: a public deployment can only ever use the visitor's own key, never the owner's.
"""

import ipaddress
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import load_dotenv

PUBLIC_DEMO_ENV = "PUBLIC_DEMO"
KEY_NOTICE = (
    "Your key is sent only to the provider you choose; this app is open source and stores "
    "nothing. Use a restricted, free-tier key."
)
SOURCE_ENV = "your .env"
SOURCE_USER = "key entered here"
PROVIDERS = {  # name: (base URL, model), both editable in the app
    "Gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-3.8-flash"),
    "Groq": ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
    "Other OpenAI-compatible": ("", ""),
    "Local Ollama": ("http://localhost:11434/v1", "qwen2.5:7b"),
}
LOCAL_ONLY_PROVIDERS = ("Local Ollama",)
KEY_LIKE = re.compile(
    r"AIza[0-9A-Za-z_\-]{10,}|sk-[0-9A-Za-z_\-]{10,}|gsk_[0-9A-Za-z]{10,}"
    r"|(?<=Bearer )[0-9A-Za-z._\-]{10,}"
)
REDACTED = "[redacted]"


@dataclass(frozen=True)
class LLMConfig:
    """Endpoint settings for the live agent. The key is left out of repr, logs and messages."""

    base_url: str | None
    api_key: str | None = field(repr=False)
    model: str | None
    source: str = "none"  # SOURCE_ENV or SOURCE_USER; shown in the app instead of the key

    @property
    def live(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    @property
    def provider(self) -> str:
        return urlparse(self.base_url).hostname if self.base_url else "none"


OFFLINE = LLMConfig(None, None, None)


def is_public_demo() -> bool:
    return os.getenv(PUBLIC_DEMO_ENV) == "1"


def env_config() -> LLMConfig:
    """Settings from LLM_* variables or a git-ignored .env (real environment variables win)."""
    load_dotenv()
    config = LLMConfig(
        os.getenv("LLM_BASE_URL") or None,
        os.getenv("LLM_API_KEY") or None,
        os.getenv("LLM_MODEL") or None,
        SOURCE_ENV,
    )
    return config if config.live else OFFLINE


def active_config(user: LLMConfig | None, public: bool) -> LLMConfig:
    """The visitor's key if given; else, outside public mode, the environment; else offline."""
    if user is not None and user.live:
        return user
    return OFFLINE if public else env_config()


def provider_presets(public: bool) -> dict[str, tuple[str, str]]:
    """Providers offered in the app; a public deployment cannot reach a local model."""
    return {k: v for k, v in PROVIDERS.items() if not (public and k in LOCAL_ONLY_PROVIDERS)}


def check_base_url(url: str, public: bool) -> None:
    """Refuse a base URL the server should not call. In public mode it must be https to a public
    host, so a visitor cannot point the server at localhost or a private network address."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("Base URL must look like https://host/path")
    if not public:
        return
    if parsed.scheme != "https":
        raise ValueError("The public demo only calls https endpoints")
    host = parsed.hostname
    try:
        private = not ipaddress.ip_address(host).is_global
    except ValueError:  # a host name, not an address
        private = host == "localhost" or host.endswith((".localhost", ".local", ".internal"))
    if private:
        raise ValueError("The public demo only calls public hosts")


def user_config(base_url: str, api_key: str, model: str, public: bool) -> LLMConfig:
    """Settings typed by the visitor, checked before use; error messages never echo the key."""
    base_url, api_key, model = base_url.strip(), api_key.strip(), model.strip()
    if not (base_url and api_key and model):
        raise ValueError("Base URL, model and API key are all needed for live mode")
    check_base_url(base_url, public)
    return LLMConfig(base_url, api_key, model, SOURCE_USER)


def redact(text: str, secret: str | None = None) -> str:
    """Text with the given secret and anything key-like (AIza..., sk-..., gsk_..., Bearer ...)
    replaced, for showing or logging provider errors."""
    if secret:
        text = text.replace(secret, REDACTED)
    return KEY_LIKE.sub(REDACTED, text)
