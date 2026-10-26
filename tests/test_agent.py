"""The agent loop with a scripted fake client (no network, ever), and offline mode end to end.

Covers the spec §10 guardrails: grounding (pass, fail then retry, fail twice then template), the
tool-call cap, refusals passed back to the model, and the offline fallback on rate limits and
malformed tool calls.
"""

import json
from types import SimpleNamespace

import openai
import pytest

from src import agent
from src.agent import Agent, LLMConfig, OfflineAgent, is_grounded, numbers_in_result
from src.agent_offline import describe

LIVE = LLMConfig("https://llm.invalid/v1", "test-placeholder", "test-model")
SOURCE = {"key": "BLR_HSR rent", "value": 24.0, "unit": "INR / sq ft / month"}


def text_reply(content: str):
    message = SimpleNamespace(content=content, tool_calls=None)
    message.model_dump = lambda **_: {"role": "assistant", "content": content}
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def tool_reply(*calls: tuple[str, str]):
    """A reply asking for tools; each call is (name, JSON arguments)."""
    tool_calls = [
        SimpleNamespace(id=f"call_{i}", function=SimpleNamespace(name=n, arguments=a))
        for i, (n, a) in enumerate(calls)
    ]
    message = SimpleNamespace(content=None, tool_calls=tool_calls)
    message.model_dump = lambda **_: {
        "role": "assistant",
        "tool_calls": [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.function.name, "arguments": c.function.arguments},
            }
            for c in tool_calls
        ],
    }
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class FakeClient:
    """Plays back scripted replies; a callable script entry decides from the request."""

    def __init__(self, script):
        self.script, self.requests = list(script), []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs | {"messages": list(kwargs["messages"])})  # snapshot
        step = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(step, Exception):
            raise step
        return step(kwargs) if callable(step) else step


class FakeToolBox:
    def __init__(self, error: str | None = None):
        self.error, self.calls = error, []

    def call(self, name, arguments):
        self.calls.append((name, arguments))
        if self.error:
            raise ValueError(self.error)
        return dict(SOURCE)


@pytest.fixture
def offline():
    return OfflineAgent.from_file()


def live_agent(script, offline, toolbox=None):
    client = FakeClient(script)
    return Agent(LIVE, toolbox or FakeToolBox(), offline, client=client), client


ASK_SOURCE = tool_reply(("get_assumption_source", '{"key": "BLR_HSR"}'))


@pytest.mark.parametrize(
    ("token", "evidence", "grounded"),
    [
        ("244.1", [244.08], True),
        ("80.1", [0.8012], True),  # a fraction shown as a percentage
        ("33.1", [-33.14], True),  # "falls by 33.1"
        ("48,000", [48013.4], True),  # a round figure
        ("2.4", [2.37], True),
        ("17", [244.08, 0.8012], False),
        ("244.2", [244.08], False),
    ],
)
def test_reply_numbers_match_tool_numbers_after_rounding(token, evidence, grounded):
    assert is_grounded(token, evidence) is grounded


def test_identifiers_and_list_markers_are_not_figures():
    assert agent.numbers_in_text("1. See S3_400km_80 and Z001: 244.1 Cr, 80.1%") == [
        "244.1",
        "80.1",
    ]


def test_grounded_reply_passes_and_cites_its_scenario(offline):
    bot, client = live_agent([ASK_SOURCE, text_reply("Hosur rent is INR 24 per sq ft.")], offline)
    reply = bot.ask("What rent does Hosur pay?")
    assert reply.grounding == "passed"
    assert reply.tool_calls == [("get_assumption_source", {"key": "BLR_HSR"})]
    assert len(client.requests) == 2


def test_ungrounded_reply_is_sent_back_once(offline):
    bot, client = live_agent(
        [ASK_SOURCE, text_reply("Rent is INR 31."), text_reply("Rent is INR 24.0.")], offline
    )
    reply = bot.ask("What rent does Hosur pay?")
    assert reply.grounding == "passed after retry"
    assert "31" in client.requests[-1]["messages"][-1]["content"]  # names the offending number
    assert reply.text.startswith("Rent is INR 24.0.")


def test_reply_ungrounded_twice_is_templated_from_the_tool_results(offline):
    bot, _ = live_agent(
        [ASK_SOURCE, text_reply("Rent is INR 31."), text_reply("Rent is INR 32.")], offline
    )
    reply = bot.ask("What rent does Hosur pay?")
    assert reply.grounding == "templated"
    assert reply.text == describe("get_assumption_source", SOURCE)
    assert "31" not in reply.text and "32" not in reply.text


def test_tool_calls_are_capped_at_six_per_question(offline):
    def keep_asking(request):
        if request["tool_choice"] == "none":
            return text_reply("Rent is INR 24.")
        return tool_reply(*[("get_assumption_source", '{"key": "BLR_HSR"}')] * 4)

    toolbox = FakeToolBox()
    bot, client = live_agent([keep_asking], offline, toolbox)
    reply = bot.ask("Tell me everything")
    assert len(toolbox.calls) == agent.MAX_TOOL_CALLS == len(reply.tool_calls)
    assert client.requests[-1]["tool_choice"] == "none"
    capped = [m for m in client.requests[-1]["messages"] if "cap of 6" in m.get("content", "")]
    assert len(capped) == 2  # the two calls requested past the cap were refused


def test_refused_override_goes_back_to_the_model(offline):
    toolbox = FakeToolBox(error="circuity_factor = 9 is refused: accepted values are [0.65, 1.9]")
    script = [
        tool_reply(("run_scenario", '{"name": "x", "overrides": {"distance.circuity_factor": 9}}')),
        text_reply("That is refused: the accepted circuity range is 0.65 to 1.9."),
    ]
    bot, client = live_agent(script, offline, toolbox)
    reply = bot.ask("Set circuity to 9")
    tool_message = client.requests[-1]["messages"][-1]
    assert (
        tool_message["role"] == "tool" and "refused" in json.loads(tool_message["content"])["error"]
    )
    assert reply.grounding == "passed"


def test_rate_limit_falls_back_to_offline_with_a_notice(offline):
    # Only the attributes the SDK error reads; avoids depending on its HTTP library
    response = SimpleNamespace(status_code=429, headers={}, request=None)
    limit = openai.RateLimitError("rate limited", response=response, body=None)
    bot, _ = live_agent([limit], offline)
    reply = bot.ask("What's our recommended network and what does it cost?")
    assert reply.mode == "offline"
    assert "RateLimitError (HTTP 429)" in reply.notice
    assert bot.messages[-1]["role"] == "system"  # the unanswered question was dropped


def test_malformed_tool_call_falls_back_to_offline(offline):
    bot, _ = live_agent([tool_reply(("explain_network", "{not json"))], offline)
    reply = bot.ask("What's our recommended network and what does it cost?")
    assert reply.mode == "offline" and "MalformedToolCallError" in reply.notice


def test_offline_is_the_default_without_endpoint_settings(monkeypatch, offline):
    monkeypatch.setattr(agent, "load_dotenv", lambda: None)
    for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(openai, "OpenAI", None)  # constructing a client would fail
    bot = Agent(LLMConfig.from_env(), None, offline)
    assert bot.mode == "offline"


DEMO = [
    ("What's our recommended network and what does it cost?", "S3_400km_80"),
    ("What if Hosur shuts for a month?", "AG_outage_BLR_HSR_1m"),
    ("And if we lost it permanently?", "AG_loss_BLR_HSR"),
    ("Diesel just went up 20%. Should we change anything?", "AG_diesel_20_"),
    ("Which of our assumptions should I worry about most?", "S9_tornado"),
]


def test_offline_mode_answers_the_demo_script_from_tool_numbers(offline):
    """Spec §10 demo, offline: the right scenario each time, every number from a tool result."""
    for question, scenario_prefix in DEMO:
        reply = offline.ask(question)
        assert any(i.startswith(scenario_prefix) for i in reply.scenario_ids), question
        entry = next(
            e
            for e in offline.library["entries"]
            if [list(c) for c in reply.tool_calls] == e["calls"]
        )
        evidence = numbers_in_result(entry["results"])
        assert agent.ungrounded_numbers(reply.text, evidence) == [], question
