"""The what-if agent (spec §10): an OpenAI-compatible tool-calling loop with guardrails.

The model does the computing; the LLM does the explaining. Live mode sends the question and the
tool schemas to any OpenAI-compatible chat-completions endpoint (D-039), runs the tools it asks
for (at most MAX_TOOL_CALLS per question) and checks the reply: every number must appear in a
tool result from this conversation, allowing rounding and % formatting, and both layers of the
answer must be there (a plain-English answer, then the detailed one under DETAILS_MARKER;
D-053). A reply that fails is
sent back once with the offending numbers named; if it fails again, the answer is templated
straight from the tool results. Rate limits, provider errors and malformed tool calls fall back
to the offline library with a visible notice. Without endpoint settings the agent is offline
from the start (no network); where the settings and key come from is llm_settings.py.

Demo transcript from the project root: python -m src.agent [--offline]
"""

import argparse
import json
import logging
import math
import re
import time
from dataclasses import dataclass, field

import openai

from src.agent_offline import (
    LIBRARY_PATH,
    STRUCTURE,
    WORKED_EXAMPLE_INTENTS,
    describe,
    library_intents,
    match_intent,
    mentioned_site,
    result_ids,
)
from src.agent_plain import PLAIN_STRUCTURE, plain
from src.agent_tools import TOOL_SCHEMAS, ToolBox
from src.llm_settings import OFFLINE, LLMConfig, env_config, redact

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 6  # per user question (spec §10)
REQUEST_TIMEOUT_S = 90
MAX_ERROR_CHARS = 200  # provider error text shown in the fallback notice

DETAILS_MARKER = "#### Details"  # splits a reply into the plain answer and the details (D-053)

SYSTEM_PROMPT = """You are a supply-chain consultant briefing the leadership of a hypothetical \
Indian FMCG client on its distribution network. The optimisation model does all the computing \
through your tools; your job is to pick the right tool and explain the result: what changes, \
why, and what it means.

Answer every question in two layers: a plain-English answer for a busy business manager, then \
a line with exactly "#### Details", then the detailed answer for an analyst.

The plain-English answer has four parts, each starting with its bold label, then one italic line:
**In short:** the answer and its one or two key numbers.
**What changes:** what happens to warehouses and customers.
**Why it costs more:** (or **Why it costs less:**) the main reason in one or two plain sentences.
**What to do:** one clear recommendation.
*Limits: the main limitation. Source: the scenario id(s).*
Keep it to about 120 words and five numbers, rounded for reading ("about 80%", "about 17%", \
"about INR 2.9 Cr"). Use plain words: warehouse (not DC), market area (not zone), trucking from \
factories to warehouses (not primary freight), delivery trucking from warehouses to markets (not \
secondary freight), share of customers who get next-day delivery (not next-day share), cost of \
holding stock (not inventory or carrying cost), running cost per warehouse (not fixed cost), \
distance trucks drive (not tonne-km). Name places by city, e.g. "the Bengaluru warehouse \
(Hosur)". No scenario ids or site codes except on the Source line.

The detailed answer has six parts, each starting with its bold label:
**Headline:** one sentence that answers the question directly: the cost impact and the service \
impact. Never start it with a scenario id; when a value is the same before and after, say \
"unchanged at X", not "X against X".
**What happens in the network:** which sites open, close or swap; which zones move and to which \
DC; how many zones, and what share of demand, lose next-day service.
**Why:** the two or three cost components that move most against the recommended network \
(primary freight, secondary freight, space, inventory, fixed cost) and the mechanism, e.g. \
"zones served from Hyderabad are further away, so secondary freight rises".
**What it means for the client:** one or two sentences of business implication.
**Assumptions and limits:** one line on what the number does not include.
**Source:** the scenario_id(s) you used.
Keep the details under about 180 words unless the user asks for more.

Rules:
- In both layers use ONLY numbers that appear in tool results in this conversation (rounding \
is fine). Never \
estimate, convert or do arithmetic of your own; if a figure is not in a tool result, call a \
tool (explain_network or compare_scenarios give more detail) or leave the figure out.
- Costs are INR Cr per year; next-day share is the share of demand within the next-day radius. \
Cost moves come from vs_recommended.cost_drivers and delta_by_component_cr; zone moves from \
vs_recommended.zones or, for an outage, the outage block.
- The recommended network is scenario {rec}. Recorded scenarios: S0 (today's network), S1 \
(cheapest, no service target), S2_kNN (NN DCs), S3_<radius>km_<target> (service frontier), \
S4_uniform and S4_regional_skew (growth), S6_diesel_20 and S6_diesel_40, S7_rent_minus_20 and \
S7_rent_plus_20, S8_no_puducherry and S8_add_east (plant footprint), COG_kNN (centre of gravity).
- A site shut for weeks or months is simulate_disruption with mode "operational"; a site lost \
for good is mode "strategic". The recommended Bengaluru site is Hosur (BLR_HSR).
- run_scenario takes overrides as a list of {{"key": ..., "value": ...}} items. A fuel price \
change is overrides [{{"key": "diesel_shock_frac", "value": <rise as a fraction>}}]. Which \
assumptions matter most is rank_assumptions.
- If a tool refuses an input, explain the refusal and the accepted range.

Two worked examples. Their numbers come from those tool results only; never reuse them for \
another question.

{examples}"""

ANSWER_RETRY = (
    "Rewrite your reply. {problems} First the plain answer (In short, What changes, Why it costs "
    "more or less, What to do, then the italic Limits and Source line), then a line with exactly "
    f"'{DETAILS_MARKER}', then the six bold-labelled parts (Headline, What happens in the "
    "network, Why, What it means for the client, Assumptions and limits, Source). Use only "
    "numbers that appear in the tool results (rounding is fine)."
)

# Provider errors worth retrying before falling back offline (D-051); 400/401/403/404 are not
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})
RETRY_BACKOFF_S = (2.0, 5.0)  # one wait per retry
MAX_RETRY_AFTER_S = 10.0


# --- Grounding check ------------------------------------------------------------------------

IDENTIFIER = re.compile(r"\b\w*[A-Za-z]\w*_\w+\b|\b[A-Za-z]+\d\w*\b")  # S3_400km_80, Z001, k09
LIST_MARKER = re.compile(r"^\s*\d+[.)]\s", re.MULTILINE)
NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


def numbers_in_text(text: str) -> list[str]:
    """Numbers a reader would see as figures: identifiers and list markers are skipped."""
    text = LIST_MARKER.sub(" ", IDENTIFIER.sub(" ", text))
    return [m.group().rstrip(",") for m in NUMBER.finditer(text)]


def numbers_in_result(value: object) -> list[float]:
    """Every number in a tool result, including numbers written inside its strings."""
    if isinstance(value, bool):
        return []
    if isinstance(value, int | float):
        return [float(value)]
    if isinstance(value, str):
        return [float(n.replace(",", "")) for n in numbers_in_text(value)]
    if isinstance(value, dict):
        return [n for v in value.values() for n in numbers_in_result(v)]
    if isinstance(value, list | tuple):
        return [n for v in value for n in numbers_in_result(v)]
    return []


def is_grounded(token: str, evidence: list[float]) -> bool:
    """A reply number is grounded if some tool number rounds to it at the reply's precision.

    The tool number may be a fraction shown as a percentage (0.801 -> 80.1) and may have lost
    its sign ("falls by 33.1" for -33.1). A round number with trailing zeros also matches at its
    own magnitude (48,000 for 48,013), keeping two significant figures, so "100" is not
    grounded by 80.1.
    """
    x = float(token.replace(",", ""))
    decimals = len(token.split(".")[1]) if "." in token else 0
    digits = token.replace(",", "").split(".")[0]
    zeros = len(digits) - len(digits.rstrip("0")) if decimals == 0 and x >= 100 else 0
    zeros = min(zeros, len(digits) - 2)
    for t in evidence:
        for v in (abs(t), abs(100 * t)):
            if math.isclose(round(v, decimals), x, abs_tol=1e-9):
                return True
            if zeros and math.isclose(round(v, -zeros), x, abs_tol=1e-9):
                return True
    return False


def ungrounded_numbers(text: str, evidence: list[float]) -> list[str]:
    return [n for n in numbers_in_text(text) if not is_grounded(n, evidence)]


def scenario_ids(results: list[tuple[str, dict]]) -> list[str]:
    """Scenario ids named by tool results, in first-seen order."""
    return list(dict.fromkeys(i for _, result in results for i in result_ids(result)))


def with_citation(text: str, ids: list[str]) -> str:
    """Append the scenario ids if the reply cites none of them (spec §10: always cite)."""
    if not ids or any(i in text for i in ids):
        return text
    return f"{text}\n\nSource: {', '.join(ids)}"


def split_reply(text: str) -> tuple[str, str]:
    """(plain answer, details): the two layers of a reply, split at DETAILS_MARKER (D-053)."""
    plain_text, _, details = text.partition(DETAILS_MARKER)
    return plain_text.strip(), details.strip()


def missing_parts(text: str) -> list[str]:
    """The labelled parts a reply leaves out: the plain answer's four (D-053), the details
    marker, and the six parts of the details (D-049)."""
    plain_text, details = split_reply(text)

    def absent(labels: tuple[str, ...], part: str) -> list[str]:
        return [label for label in labels if not re.search(re.escape(label), part, re.IGNORECASE)]

    if DETAILS_MARKER not in text:
        return [*absent(PLAIN_STRUCTURE, plain_text), DETAILS_MARKER]
    return absent(PLAIN_STRUCTURE, plain_text) + absent(STRUCTURE, details)


def two_layers(results: list[tuple[str, dict]], intent=None) -> tuple[str, str]:
    """(plain answer, details) templated straight from tool results: the plain answer is about
    the first result, the details cover them all."""
    action, caveat = (intent.action, intent.caveat) if intent else (None, None)
    meaning, limits = (intent.meaning, intent.limits) if intent else (None, None)
    name, result = results[0]
    details = "\n\n".join(describe(n, r, meaning, limits) for n, r in results)
    return plain(name, result, action, caveat), details


def worked_examples(library: dict) -> str:
    """Two worked answers for the live system prompt, built from real library records by the
    same writers as the offline answers, so they model both layers and pass grounding."""
    entries = {e["intent_id"]: e for e in library["entries"]}
    intents = {i.intent_id: i for i in library_intents(library["recommended_id"])}
    blocks = []
    for intent_id in WORKED_EXAMPLE_INTENTS:
        entry = entries[intent_id]
        name, args = entry["calls"][0]
        plain_text, details = two_layers(entry["results"][:1], intents[intent_id])
        blocks.append(
            f"Question: {entry['example']}\nTool call: {name} {json.dumps(args)}\nAnswer:\n"
            f"{plain_text}\n\n{DETAILS_MARKER}\n\n{details}"
        )
    return "\n\n---\n\n".join(blocks)


def retry_delay(err: Exception, attempt: int) -> float | None:
    """Seconds to wait before retrying a provider call, or None to give up (D-051).

    Retries only RETRY_STATUS codes, once per RETRY_BACKOFF_S entry. A numeric Retry-After
    header replaces the backoff, capped at MAX_RETRY_AFTER_S.
    """
    if getattr(err, "status_code", None) not in RETRY_STATUS or attempt >= len(RETRY_BACKOFF_S):
        return None
    headers = getattr(getattr(err, "response", None), "headers", None) or {}
    try:
        wait_s = float(headers.get("retry-after"))
    except (TypeError, ValueError):  # absent, or an HTTP date
        wait_s = RETRY_BACKOFF_S[attempt]
    return min(wait_s, MAX_RETRY_AFTER_S)


def provider_error(err: Exception) -> str:
    """The provider's own error text: the response body when there is one (Gemini sends
    [{"error": {"message": ...}}], which the SDK's message reduces to "Error code: 400"; D-056),
    else the SDK message. Not redacted: callers redact before showing or logging it."""
    body = getattr(err, "body", None)
    if isinstance(body, list) and len(body) == 1:
        body = body[0]
    if isinstance(body, dict):
        inner = body.get("error", body)
        message = inner.get("message") if isinstance(inner, dict) else None
        return str(message) if message else json.dumps(body)
    if body:
        return str(body)
    return getattr(err, "message", None) or str(err)


def make_client(config: LLMConfig) -> openai.OpenAI:
    return openai.OpenAI(
        base_url=config.base_url,
        api_key=config.api_key,
        max_retries=0,  # retries follow RETRY_STATUS / RETRY_BACKOFF_S instead (D-051)
        timeout=REQUEST_TIMEOUT_S,
    )


def check_connection(config: LLMConfig, client=None) -> str:
    """Send one tiny request carrying every tool schema, so a provider that rejects the key, the
    model or the schemas says so at once (D-056). Returns the line the app shows."""
    if not config.live:
        return "No live settings: enter a key and press Use this key."
    client = client or make_client(config)
    try:
        client.chat.completions.create(
            model=config.model,
            messages=[{"role": "user", "content": "Reply with OK."}],
            tools=TOOL_SCHEMAS,
        )
    except openai.APIError as err:
        status = getattr(err, "status_code", None)
        reason = type(err).__name__ + (f" (HTTP {status})" if status else "")
        detail = redact(f"{reason}: {provider_error(err)[:MAX_ERROR_CHARS]}", config.api_key)
        logger.warning("Connection test failed: %s", detail)
        return f"Connection failed: {detail}"
    return f"Connected: {config.model} accepted tools"


class MalformedToolCallError(Exception):
    """The model asked for an unknown tool or sent arguments that are not a JSON object."""


# --- Replies --------------------------------------------------------------------------------


@dataclass
class Reply:
    """One answer, with how it was produced (shown in the app and the demo transcripts)."""

    text: str  # the plain-English answer (D-053)
    mode: str  # "live" or "offline"
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)
    scenario_ids: list[str] = field(default_factory=list)
    notice: str | None = None  # e.g. why a live question fell back to offline
    grounding: str = "not checked"  # "passed", "passed after retry", "templated", "offline"
    details: str = ""  # the six-part analytical answer, shown under "Show details"


class OfflineAgent:
    """Answers from the pre-computed library by intent matching; no network, no solver."""

    def __init__(self, library: dict) -> None:
        self.library = library
        self.intents = library_intents(library["recommended_id"])
        self.entries = {e["intent_id"]: e for e in library["entries"]}
        self.last_site: str | None = None

    @classmethod
    def from_file(cls) -> "OfflineAgent":
        return cls(json.loads(LIBRARY_PATH.read_text()))

    def ask(self, question: str) -> Reply:
        intent = match_intent(question, self.intents, self.last_site)
        self.last_site = mentioned_site(question) or self.last_site
        if intent is None:
            examples = "\n".join(f"- {e['example']}" for e in self.library["entries"])
            return Reply(
                "Offline mode answers these pre-computed questions:\n" + examples,
                "offline",
                grounding="offline",
            )
        entry = self.entries[intent.intent_id]
        results = [(name, result) for name, result in entry["results"]]
        plain_text, details = two_layers(results, intent)
        return Reply(
            plain_text,
            "offline",
            [(name, args) for name, args in entry["calls"]],
            scenario_ids(results),
            grounding="offline",
            details=details,
        )


class Agent:
    """Live tool-calling agent with the spec §10 guardrails; falls back to OfflineAgent."""

    def __init__(
        self, config: LLMConfig, toolbox: ToolBox | None, offline: OfflineAgent, client=None
    ) -> None:
        self.config, self.toolbox, self.offline = config, toolbox, offline
        self.client = client
        if client is None and config.live:
            self.client = make_client(config)
        self.sleep = time.sleep  # replaced in tests
        prompt = SYSTEM_PROMPT.format(
            rec=offline.library["recommended_id"], examples=worked_examples(offline.library)
        )
        self.messages: list[dict] = [{"role": "system", "content": prompt}]
        self.evidence: list[float] = []  # every number from every tool result so far
        self.last_results: list[tuple[str, dict]] = []  # for citations on follow-up answers

    @property
    def mode(self) -> str:
        return "live" if self.client is not None and self.toolbox is not None else "offline"

    def ask(self, question: str) -> Reply:
        if self.mode == "offline":
            return self.offline.ask(question)
        self.offline.last_site = mentioned_site(question) or self.offline.last_site
        history_len = len(self.messages)  # rolled back to here if the provider fails
        self.messages.append({"role": "user", "content": question})
        results: list[tuple[str, dict]] = []
        calls: list[tuple[str, dict]] = []
        try:
            text = self.complete(results, calls)
            grounding = "passed"
            problems = self.answer_problems(text)
            if problems:
                logger.info("Answer check failed (%s); asking once more", problems)
                retry = ANSWER_RETRY.format(problems=problems)
                self.messages.append({"role": "user", "content": retry})
                text = self.complete(results, calls)
                grounding = "passed after retry"
                if self.answer_problems(text):
                    text = (
                        f"\n\n{DETAILS_MARKER}\n\n".join(two_layers(results))
                        if results
                        else "I could not ground an answer in the model results; please rephrase."
                    )
                    self.messages.append({"role": "assistant", "content": text})
                    grounding = "templated"
        except (openai.APIError, MalformedToolCallError) as err:
            del self.messages[history_len:]  # the next turn starts from a well-formed history
            return self.fall_back(question, err)
        ids = scenario_ids(results) or scenario_ids(self.last_results)
        self.last_results = results or self.last_results
        plain_text, details = split_reply(text)
        if details:
            details = with_citation(details, ids)
        else:
            plain_text = with_citation(plain_text, ids)
        return Reply(plain_text, "live", calls, ids, grounding=grounding, details=details)

    def answer_problems(self, text: str) -> str:
        """Why a reply fails the guardrail: ungrounded numbers (the grounding check, D-041) or
        missing parts of the answer structure (D-050). Empty when it passes."""
        problems = []
        offending = ungrounded_numbers(text, self.evidence)
        if offending:
            problems.append(f"These numbers are not in any tool result: {', '.join(offending)}.")
        missing = missing_parts(text)
        if missing:
            problems.append(f"These parts are missing: {', '.join(missing)}.")
        return " ".join(problems)

    def create(self, **request) -> object:
        """One chat-completions call, retried on rate limits and server errors (D-051)."""
        attempt = 0
        while True:
            try:
                return self.client.chat.completions.create(**request)
            except openai.APIStatusError as err:
                wait_s = retry_delay(err, attempt)  # None once retries are spent
                if wait_s is None:
                    raise
                attempt += 1
                logger.info(
                    "Provider HTTP %s; retry %d in %.0f s", err.status_code, attempt, wait_s
                )
                self.sleep(wait_s)

    def complete(self, results: list, calls: list) -> str:
        """Call the model until it answers in text, running tools within the per-question cap."""
        while True:
            capped = len(calls) >= MAX_TOOL_CALLS
            response = self.create(
                model=self.config.model,
                messages=self.messages,
                tools=TOOL_SCHEMAS,
                tool_choice="none" if capped else "auto",
            )
            message = response.choices[0].message
            self.messages.append(message.model_dump(exclude_none=True))
            if not message.tool_calls:
                return message.content or ""
            for tool_call in message.tool_calls:
                result = self.run_tool(tool_call, calls, results)
                self.messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)}
                )

    def run_tool(self, tool_call, calls: list, results: list) -> dict:
        """One requested tool call: refused past the cap, ValueErrors returned as {"error"}."""
        name = tool_call.function.name
        if len(calls) >= MAX_TOOL_CALLS:
            return {
                "error": f"Tool-call cap of {MAX_TOOL_CALLS} per question reached; answer "
                "with the results you already have."
            }
        try:
            arguments = json.loads(tool_call.function.arguments or "{}")
        except json.JSONDecodeError as err:
            raise MalformedToolCallError(f"{name}: arguments are not valid JSON") from err
        if not isinstance(arguments, dict):
            raise MalformedToolCallError(f"{name}: arguments are not an object")
        calls.append((name, arguments))
        logger.info("Tool call %s %s", name, arguments)
        try:
            result = self.toolbox.call(name, arguments)
        except ValueError as err:
            if str(err).startswith("Unknown tool"):
                raise MalformedToolCallError(str(err)) from err
            result = {"error": str(err)}
        results.append((name, result))
        self.evidence += numbers_in_result(result)
        return result

    def fall_back(self, question: str, err: Exception) -> Reply:
        """Answer from the offline library and say why (spec §10: visible notice)."""
        reason = type(err).__name__
        status = getattr(err, "status_code", None)
        if status:
            reason += f" (HTTP {status})"
        # The provider's own words help the visitor fix a bad key; never echo a key (D-045)
        reason = redact(f"{reason}: {provider_error(err)[:MAX_ERROR_CHARS]}", self.config.api_key)
        logger.warning("Live model unavailable: %s; answering offline", reason)
        reply = self.offline.ask(question)
        reply.notice = f"Live model unavailable ({reason}); answered from the offline library."
        return reply


# --- Demo script (spec §10) -----------------------------------------------------------------

DEMO_QUESTIONS = (
    "What's our recommended network and what does it cost?",
    "What if Hosur shuts for a month?",
    "And if we lost it permanently?",
    "Diesel just went up 20%. Should we change anything?",
    "Which of our assumptions should I worry about most?",
)


def print_demo_transcript(bot: Agent, pause_s: float) -> None:
    """Ask the five demo questions in order and print a Markdown transcript."""
    config = bot.config
    where = f"{config.provider}, model {config.model}" if bot.mode == "live" else "no network"
    print(f"Mode: {bot.mode} ({where})\n")  # noqa: T201
    for i, question in enumerate(DEMO_QUESTIONS, start=1):
        if i > 1 and bot.mode == "live":
            time.sleep(pause_s)  # space out live calls for free-tier rate limits
        reply = bot.ask(question)
        tools = "; ".join(f"{n}({json.dumps(a)})" for n, a in reply.tool_calls) or "none"
        print(f"**Q{i}. {question}**\n")  # noqa: T201
        if reply.notice:
            print(f"> Notice: {reply.notice}\n")  # noqa: T201
        print(f"{reply.text}\n")  # noqa: T201
        if reply.details:
            print(f"*Show details:*\n\n{reply.details}\n")  # noqa: T201
        print(  # noqa: T201
            f"*{reply.mode} · tools: {tools} · grounding: {reply.grounding} · "
            f"scenarios: {', '.join(reply.scenario_ids) or 'none'}*\n"
        )


def main() -> None:
    from src.config import load_params
    from src.data_prep import load_network_data

    parser = argparse.ArgumentParser(description="Run the spec §10 demo questions.")
    parser.add_argument("--offline", action="store_true", help="ignore LLM_* settings")
    parser.add_argument("--pause-s", type=float, default=20.0, help="gap between live questions")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    offline = OfflineAgent.from_file()
    config = OFFLINE if args.offline else env_config()
    toolbox = ToolBox(load_params(), load_network_data()) if config.live else None
    print_demo_transcript(Agent(config, toolbox, offline), args.pause_s)


if __name__ == "__main__":
    main()
