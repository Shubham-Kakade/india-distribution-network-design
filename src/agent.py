"""The what-if agent (spec §10): an OpenAI-compatible tool-calling loop with guardrails.

The model does the computing; the LLM does the explaining. Live mode sends the question and the
tool schemas to any OpenAI-compatible chat-completions endpoint (D-039), runs the tools it asks
for (at most MAX_TOOL_CALLS per question) and checks the reply: every number must appear in a
tool result from this conversation, allowing rounding and % formatting. A reply that fails is
sent back once with the offending numbers named; if it fails again, the answer is templated
straight from the tool results. Rate limits, provider errors and malformed tool calls fall back
to the offline library with a visible notice. With LLM_BASE_URL or LLM_API_KEY unset the agent
is offline from the start (no network).
"""

import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import openai
from dotenv import load_dotenv

from src.agent_offline import (
    LIBRARY_PATH,
    describe,
    library_intents,
    match_intent,
    mentioned_site,
)
from src.agent_tools import TOOL_SCHEMAS, ToolBox

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 6  # per user question (spec §10)
MAX_RETRIES = 4  # SDK retries on 429 / 5xx, with exponential backoff that honours Retry-After
REQUEST_TIMEOUT_S = 90

SYSTEM_PROMPT = """You are a supply-chain network analyst presenting a distribution network \
study for a hypothetical Indian FMCG client to its leadership. The optimisation model does all \
the computing through your tools; your job is to pick the right tool and explain the trade-off.

Rules:
- Every number in your reply must come from a tool result in this conversation. Never estimate, \
convert currencies, or do arithmetic of your own; if a figure is not in a tool result, call a \
tool or leave the figure out.
- Cite the scenario_id of every result you use, in brackets, e.g. [{rec}].
- Costs are INR Cr per year; next-day share is the share of demand within the next-day radius.
- The recommended network is scenario {rec}. Recorded scenarios: S0 (today's network), S1 \
(cheapest, no service target), S2_kNN (NN DCs), S3_<radius>km_<target> (service frontier), \
S4_uniform and S4_regional_skew (growth), S6_diesel_20 and S6_diesel_40, S7_rent_minus_20 and \
S7_rent_plus_20, S8_no_puducherry and S8_add_east (plant footprint), COG_kNN (centre of gravity).
- A site shut for weeks or months is simulate_disruption with mode "operational"; a site lost \
for good is mode "strategic". The recommended Bengaluru site is Hosur (BLR_HSR).
- A fuel price change is run_scenario with overrides {{"diesel_shock_frac": <rise as a \
fraction>}}. Which assumptions matter most is rank_assumptions.
- If a tool refuses an input, explain the refusal and the accepted range.
- Answer in 3 to 6 short sentences or bullets, for a steering committee."""

GROUNDING_RETRY = (
    "Your reply contains numbers that are not in any tool result: {numbers}. Rewrite it using "
    "only numbers that appear in the tool results (rounding is fine), and cite scenario ids."
)


# --- Configuration --------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMConfig:
    """Endpoint settings from the environment (D-039). The key is never logged or displayed."""

    base_url: str | None
    api_key: str | None
    model: str | None

    @classmethod
    def from_env(cls) -> "LLMConfig":
        load_dotenv()  # a git-ignored .env, if present; real environment variables win
        return cls(
            os.getenv("LLM_BASE_URL") or None,
            os.getenv("LLM_API_KEY") or None,
            os.getenv("LLM_MODEL") or None,
        )

    @property
    def live(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    @property
    def provider(self) -> str:
        return urlparse(self.base_url).hostname if self.base_url else "none"


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
    own magnitude (48,000 for 48,013).
    """
    x = float(token.replace(",", ""))
    decimals = len(token.split(".")[1]) if "." in token else 0
    digits = token.replace(",", "").split(".")[0]
    zeros = len(digits) - len(digits.rstrip("0")) if decimals == 0 and x >= 100 else 0
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
    ids = []
    for _, result in results:
        for key in ("scenario_id", "source_id"):
            if key in result and result[key] not in ids:
                ids.append(result[key])
        for row in result.get("scenarios", []):
            if row["scenario_id"] not in ids:
                ids.append(row["scenario_id"])
    return ids


def with_citation(text: str, ids: list[str]) -> str:
    """Append the scenario ids if the reply cites none of them (spec §10: always cite)."""
    if not ids or any(i in text for i in ids):
        return text
    return f"{text}\n\nSource: {', '.join(ids)}"


class MalformedToolCallError(Exception):
    """The model asked for an unknown tool or sent arguments that are not a JSON object."""


# --- Replies --------------------------------------------------------------------------------


@dataclass
class Reply:
    """One answer, with how it was produced (shown in the app and the demo transcripts)."""

    text: str
    mode: str  # "live" or "offline"
    tool_calls: list[tuple[str, dict]] = field(default_factory=list)
    scenario_ids: list[str] = field(default_factory=list)
    notice: str | None = None  # e.g. why a live question fell back to offline
    grounding: str = "not checked"  # "passed", "passed after retry", "templated", "offline"


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
        text = "\n\n".join(describe(name, result) for name, result in results)
        return Reply(
            text,
            "offline",
            [(name, args) for name, args in entry["calls"]],
            scenario_ids(results),
            grounding="offline",
        )


class Agent:
    """Live tool-calling agent with the spec §10 guardrails; falls back to OfflineAgent."""

    def __init__(
        self, config: LLMConfig, toolbox: ToolBox | None, offline: OfflineAgent, client=None
    ) -> None:
        self.config, self.toolbox, self.offline = config, toolbox, offline
        self.client = client
        if client is None and config.live:
            self.client = openai.OpenAI(
                base_url=config.base_url,
                api_key=config.api_key,
                max_retries=MAX_RETRIES,
                timeout=REQUEST_TIMEOUT_S,
            )
        rec = offline.library["recommended_id"]
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT.format(rec=rec)}]
        self.evidence: list[float] = []  # every number from every tool result so far
        self.last_results: list[tuple[str, dict]] = []  # for citations on follow-up answers

    @property
    def mode(self) -> str:
        return "live" if self.client is not None and self.toolbox is not None else "offline"

    def ask(self, question: str) -> Reply:
        if self.mode == "offline":
            return self.offline.ask(question)
        self.offline.last_site = mentioned_site(question) or self.offline.last_site
        self.messages.append({"role": "user", "content": question})
        results: list[tuple[str, dict]] = []
        calls: list[tuple[str, dict]] = []
        try:
            text = self.complete(results, calls)
            offending = ungrounded_numbers(text, self.evidence)
            grounding = "passed"
            if offending:
                logger.info("Grounding check failed on %s; asking once more", offending)
                retry = GROUNDING_RETRY.format(numbers=", ".join(offending))
                self.messages.append({"role": "user", "content": retry})
                text = self.complete(results, calls)
                grounding = "passed after retry"
                if ungrounded_numbers(text, self.evidence):
                    text = "\n\n".join(describe(n, r) for n, r in results) or (
                        "I could not ground an answer in the model results; please rephrase."
                    )
                    self.messages.append({"role": "assistant", "content": text})
                    grounding = "templated"
        except (openai.APIError, MalformedToolCallError) as err:
            return self.fall_back(question, err)
        ids = scenario_ids(results) or scenario_ids(self.last_results)
        self.last_results = results or self.last_results
        return Reply(with_citation(text, ids), "live", calls, ids, grounding=grounding)

    def complete(self, results: list, calls: list) -> str:
        """Call the model until it answers in text, running tools within the per-question cap."""
        while True:
            capped = len(calls) >= MAX_TOOL_CALLS
            response = self.client.chat.completions.create(
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
        logger.warning("Live model unavailable: %s; answering offline", reason)
        # Drop the unanswered question so the live history stays well formed for the next turn
        while self.messages and self.messages[-1]["role"] != "system":
            if self.messages.pop()["role"] == "user":
                break
        reply = self.offline.ask(question)
        reply.notice = f"Live model unavailable ({reason}); answered from the offline library."
        return reply
