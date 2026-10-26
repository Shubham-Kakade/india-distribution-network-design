"""The agent loop with a scripted fake client (no network, ever), and offline mode end to end.

Covers the spec §10 guardrails: grounding and the six-part answer structure (pass, fail then
retry, fail twice then template), the tool-call cap, refusals passed back to the model, provider
retries (D-051), and the offline fallback on persistent errors and malformed tool calls.
"""

import json
from types import SimpleNamespace

import openai
import pytest

from src import agent
from src.agent import Agent, OfflineAgent, is_grounded, numbers_in_result
from src.agent_offline import STRUCTURE, describe, library_intents, worked_examples
from src.llm_settings import LLMConfig

LIVE = LLMConfig("https://llm.invalid/v1", "test-placeholder", "test-model")
MAX_ANSWER_WORDS = 220  # "about 180 words" plus the six labels and scenario ids (D-049)
SOURCE = {"key": "BLR_HSR rent", "value": 24.0, "unit": "INR / sq ft / month"}


def structured(headline: str) -> str:
    """A reply with the six labelled parts and one headline sentence (D-049)."""
    body = {"Headline": headline, "Source": "BLR_HSR rent"}
    return "\n\n".join(f"**{label}:** {body.get(label, 'Explained.')}" for label in STRUCTURE)


def status_error(cls, status: int, headers: dict | None = None):
    # Only the attributes the SDK error reads; avoids depending on its HTTP library
    response = SimpleNamespace(status_code=status, headers=headers or {}, request=None)
    return cls(f"HTTP {status} from the provider", response=response, body=None)


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
    bot = Agent(LIVE, toolbox or FakeToolBox(), offline, client=client)
    bot.sleeps = []
    bot.sleep = bot.sleeps.append  # record retry waits instead of sleeping
    return bot, client


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
        ("100", [0.8012], False),  # a round figure keeps two significant figures
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
    bot, client = live_agent(
        [ASK_SOURCE, text_reply(structured("Hosur rent is INR 24 per sq ft."))], offline
    )
    reply = bot.ask("What rent does Hosur pay?")
    assert reply.grounding == "passed"
    assert reply.tool_calls == [("get_assumption_source", {"key": "BLR_HSR"})]
    assert len(client.requests) == 2


def test_ungrounded_reply_is_sent_back_once(offline):
    bot, client = live_agent(
        [
            ASK_SOURCE,
            text_reply(structured("Rent is INR 31.")),
            text_reply(structured("Rent is INR 24.0.")),
        ],
        offline,
    )
    reply = bot.ask("What rent does Hosur pay?")
    assert reply.grounding == "passed after retry"
    assert "31" in client.requests[-1]["messages"][-1]["content"]  # names the offending number
    assert reply.text.startswith("**Headline:** Rent is INR 24.0.")


def test_reply_ungrounded_twice_is_templated_from_the_tool_results(offline):
    bot, _ = live_agent(
        [
            ASK_SOURCE,
            text_reply(structured("Rent is INR 31.")),
            text_reply(structured("Rent is INR 32.")),
        ],
        offline,
    )
    reply = bot.ask("What rent does Hosur pay?")
    assert reply.grounding == "templated"
    assert reply.text == describe("get_assumption_source", SOURCE)
    assert "31" not in reply.text and "32" not in reply.text


def test_reply_missing_the_structure_is_sent_back_once(offline):
    bot, client = live_agent(
        [ASK_SOURCE, text_reply("Rent is INR 24."), text_reply(structured("Rent is INR 24."))],
        offline,
    )
    reply = bot.ask("What rent does Hosur pay?")
    assert reply.grounding == "passed after retry"
    retry = client.requests[-1]["messages"][-1]["content"]
    assert "missing" in retry and "What happens in the network" in retry


def test_reply_missing_the_structure_twice_is_templated(offline):
    bot, _ = live_agent(
        [ASK_SOURCE, text_reply("Rent is INR 24."), text_reply("Still INR 24.")], offline
    )
    reply = bot.ask("What rent does Hosur pay?")
    assert reply.grounding == "templated"
    assert reply.text == describe("get_assumption_source", SOURCE)
    assert all(f"**{label}:**" in reply.text for label in STRUCTURE)


def test_tool_calls_are_capped_at_six_per_question(offline):
    def keep_asking(request):
        if request["tool_choice"] == "none":
            return text_reply(structured("Rent is INR 24."))
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
        text_reply(structured("That is refused: the accepted circuity range is 0.65 to 1.9.")),
    ]
    bot, client = live_agent(script, offline, toolbox)
    reply = bot.ask("Set circuity to 9")
    tool_message = client.requests[-1]["messages"][-1]
    assert (
        tool_message["role"] == "tool" and "refused" in json.loads(tool_message["content"])["error"]
    )
    assert reply.grounding == "passed"


def test_persistent_rate_limit_is_retried_twice_then_falls_back(offline):
    bot, client = live_agent([status_error(openai.RateLimitError, 429)], offline)
    reply = bot.ask("What's our recommended network and what does it cost?")
    assert len(client.requests) == 3 and bot.sleeps == [2.0, 5.0]  # two retries, then give up
    assert reply.mode == "offline"
    assert "RateLimitError (HTTP 429)" in reply.notice
    assert [m["role"] for m in bot.messages] == ["system"]  # the question was rolled back


def test_server_error_then_success_gives_a_live_answer(offline):
    script = [
        status_error(openai.InternalServerError, 503),
        ASK_SOURCE,
        text_reply(structured("Hosur rent is INR 24 per sq ft.")),
    ]
    bot, client = live_agent(script, offline)
    reply = bot.ask("What rent does Hosur pay?")
    assert reply.mode == "live" and reply.grounding == "passed"
    assert bot.sleeps == [2.0] and len(client.requests) == 3


def test_three_server_errors_fall_back_with_the_status_in_the_notice(offline):
    bot, client = live_agent([status_error(openai.InternalServerError, 503)], offline)
    reply = bot.ask("What's our recommended network and what does it cost?")
    assert len(client.requests) == 3 and reply.mode == "offline"
    assert "InternalServerError (HTTP 503)" in reply.notice


@pytest.mark.parametrize(
    ("cls", "status"),
    [
        (openai.BadRequestError, 400),
        (openai.AuthenticationError, 401),
        (openai.PermissionDeniedError, 403),
        (openai.NotFoundError, 404),
    ],
)
def test_client_errors_are_not_retried(offline, cls, status):
    bot, client = live_agent([status_error(cls, status)], offline)
    reply = bot.ask("What's our recommended network and what does it cost?")
    assert len(client.requests) == 1 and bot.sleeps == []
    assert reply.mode == "offline" and f"HTTP {status}" in reply.notice


@pytest.mark.parametrize(("retry_after", "wait_s"), [("1", 1.0), ("60", 10.0), ("soon", 2.0)])
def test_retry_after_is_respected_and_capped(offline, retry_after, wait_s):
    error = status_error(openai.RateLimitError, 429, {"retry-after": retry_after})
    bot, _ = live_agent([error, ASK_SOURCE, text_reply(structured("INR 24."))], offline)
    bot.ask("What rent does Hosur pay?")
    assert bot.sleeps == [wait_s]


def test_failure_during_the_grounding_retry_rolls_back_the_whole_turn(offline):
    outage = status_error(openai.InternalServerError, 503)
    bot, _ = live_agent([ASK_SOURCE, text_reply(structured("Rent is INR 31.")), outage], offline)
    reply = bot.ask("What's our recommended network and what does it cost?")
    assert reply.mode == "offline" and "HTTP 503" in reply.notice
    assert [m["role"] for m in bot.messages] == ["system"]


def test_the_key_never_appears_in_the_config_repr():
    assert "test-placeholder" not in repr(LIVE)


def test_malformed_tool_call_falls_back_to_offline(offline):
    bot, _ = live_agent([tool_reply(("explain_network", "{not json"))], offline)
    reply = bot.ask("What's our recommended network and what does it cost?")
    assert reply.mode == "offline" and "MalformedToolCallError" in reply.notice


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


def test_every_library_answer_has_the_six_parts_and_passes_grounding(offline):
    """All 20 offline answers: the D-049 structure, every number from a tool result, short."""
    for entry in offline.library["entries"]:
        reply = OfflineAgent(offline.library).ask(entry["example"])
        assert [list(c) for c in reply.tool_calls] == entry["calls"], entry["intent_id"]
        assert all(f"**{label}:**" in reply.text for label in STRUCTURE), entry["intent_id"]
        evidence = numbers_in_result(entry["results"])
        assert agent.ungrounded_numbers(reply.text, evidence) == [], entry["intent_id"]
        assert len(reply.text.split()) <= MAX_ANSWER_WORDS, entry["intent_id"]


def test_worked_examples_in_the_prompt_are_structured_and_grounded(offline):
    examples = worked_examples(offline.library)
    entries = {e["intent_id"]: e for e in offline.library["entries"]}
    evidence = numbers_in_result([entries[i]["results"] for i in ("outage_BLR_HSR", "diesel_20")])
    answers = [block.split("Answer:\n", 1)[1] for block in examples.split("\n\n---\n\n")]
    assert len(answers) == 2
    for text in answers:
        assert all(f"**{label}:**" in text for label in STRUCTURE)
        assert agent.ungrounded_numbers(text, evidence) == []
    bot, _ = live_agent([None], offline)
    assert examples in bot.messages[0]["content"]  # the system prompt carries them


def test_library_intents_cover_every_library_entry(offline):
    ids = {i.intent_id for i in library_intents(offline.library["recommended_id"])}
    assert ids == {e["intent_id"] for e in offline.library["entries"]}
