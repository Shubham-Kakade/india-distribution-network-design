"""Bring-your-own-key (D-045): where the settings come from, and the key never leaking.

Every live call goes to a scripted fake client; CI never calls an LLM API.
"""

import json
import logging

import openai
import pytest

from src import llm_settings
from src.agent import Agent, OfflineAgent, print_demo_transcript
from src.llm_settings import (
    OFFLINE,
    SOURCE_ENV,
    SOURCE_USER,
    active_config,
    check_base_url,
    provider_presets,
    redact,
    user_config,
)
from tests.test_agent import FakeClient, text_reply, tool_reply

# Fake keys are assembled at run time, so the source holds nothing that looks like a key
# (the pre-push scan and GitHub secret scanning both look for these prefixes)
FILLER = "TestOnlyNotARealKey0123456789"
KEY = "AI" + "za" + FILLER
ENV = {
    "LLM_BASE_URL": "https://env.invalid/v1",
    "LLM_API_KEY": "env-key-placeholder",
    "LLM_MODEL": "m",
}


@pytest.fixture
def no_dotenv(monkeypatch):
    monkeypatch.setattr(llm_settings, "load_dotenv", lambda: None)
    for name in (*ENV, "PUBLIC_DEMO"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def offline():
    return OfflineAgent.from_file()


def visitor() -> llm_settings.LLMConfig:
    return user_config("https://generativelanguage.googleapis.com/v1beta/openai/", KEY, "m", True)


def test_offline_is_the_default_without_any_key(no_dotenv, monkeypatch, offline):
    monkeypatch.setattr(openai, "OpenAI", None)  # constructing a client would fail
    config = active_config(None, public=False)
    assert config == OFFLINE
    assert Agent(config, None, offline).mode == "offline"


def test_local_use_reads_the_environment_and_says_so(no_dotenv, monkeypatch):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    config = active_config(None, public=False)
    assert config.live and config.source == SOURCE_ENV


def test_public_demo_ignores_environment_keys_and_dotenv(no_dotenv, monkeypatch):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("PUBLIC_DEMO", "1")

    def dotenv_must_not_load():
        raise AssertionError(".env read in public mode")

    monkeypatch.setattr(llm_settings, "load_dotenv", dotenv_must_not_load)
    assert llm_settings.is_public_demo()
    assert active_config(None, public=True) == OFFLINE
    assert active_config(visitor(), public=True).source == SOURCE_USER


def test_forgetting_the_key_returns_to_offline_in_public_mode(no_dotenv):
    assert active_config(visitor(), public=True).live
    assert active_config(None, public=True) == OFFLINE  # "Forget key" sets the user config to None


def test_public_mode_hides_local_ollama_and_local_urls():
    assert "Local Ollama" in provider_presets(public=False)
    assert "Local Ollama" not in provider_presets(public=True)
    check_base_url("http://localhost:11434/v1", public=False)
    for url in (
        "http://localhost:11434/v1",
        "https://localhost/v1",
        "https://127.0.0.1/v1",
        "https://169.254.169.254/latest",
        "https://10.0.0.5/v1",
        "ftp://example.com",
    ):
        with pytest.raises(ValueError):
            check_base_url(url, public=True)
    check_base_url("https://api.groq.com/openai/v1", public=True)


def test_missing_fields_are_refused_without_echoing_the_key():
    with pytest.raises(ValueError) as err:
        user_config("", KEY, "m", public=True)
    assert KEY not in str(err.value)


def test_key_is_not_in_the_config_repr():
    assert KEY not in repr(visitor())


@pytest.mark.parametrize(
    "text",
    [
        f"bad key {KEY} sent",
        "Authorization: " + "Bear" + "er " + FILLER,
        "groq " + "gs" + "k_" + FILLER.replace("-", ""),
        "openai " + "s" + "k-proj-" + FILLER,
    ],
)
def test_redact_removes_key_like_text(text):
    out = redact(text, KEY)
    assert llm_settings.REDACTED in out
    assert not llm_settings.KEY_LIKE.search(out) and KEY not in out


def test_provider_error_echoing_the_key_is_redacted_in_notice_and_logs(offline, caplog):
    response = type("R", (), {"status_code": 400, "headers": {}, "request": None})()
    leak = openai.BadRequestError(f"API key {KEY} not valid", response=response, body=None)
    bot = Agent(visitor(), object(), offline, client=FakeClient([leak]))
    with caplog.at_level(logging.DEBUG):
        reply = bot.ask("What's our recommended network and what does it cost?")
    assert reply.mode == "offline" and "not valid" in reply.notice
    assert KEY not in reply.notice
    assert all(KEY not in r.getMessage() for r in caplog.records)


def test_key_stays_out_of_cache_logs_history_and_transcripts(
    toolbox,
    offline,
    caplog,
    capsys,
):
    script = [
        tool_reply(
            (
                "run_scenario",
                '{"name": "x", "overrides": [{"key": "diesel_shock_frac", "value": 0.2}]}',
            )
        ),
        text_reply("Done."),
    ]
    bot = Agent(visitor(), toolbox, offline, client=FakeClient(script))
    with caplog.at_level(logging.DEBUG):
        print_demo_transcript(bot, pause_s=0)
    cached = list(toolbox.cache_dir.glob("*.json"))
    assert cached  # the run was cached ...
    for path in cached:  # ... under a hash of the arguments, with no key in name or content
        assert KEY not in path.name and KEY not in path.read_text()
    assert KEY not in json.dumps(bot.messages)
    assert all(KEY not in r.getMessage() for r in caplog.records)
    assert KEY not in capsys.readouterr().out
