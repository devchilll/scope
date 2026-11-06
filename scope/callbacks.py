"""ADK model callbacks: pre-model safety gate and post-model audit logging.

``fast_guardrail_callback`` is registered as the agent's ``before_model_callback``
and runs before *every* LLM request. It:

1. Takes the text of the message that started the invocation (the new user
   message, whatever role the client gave it; if it has no text, the latest
   ``user`` turn of the request).
2. Screens it once per invocation (one user turn): logs the input to the audit
   trail and runs the Layer 2a ML text-safety check (``unitary/toxic-bert``)
   inside a ``scope.pre_model_safety_gate`` OpenTelemetry span. The decision
   is cached under a ``temp:`` session-state key, so the later model calls of
   the same turn (ADK's tool loop) reuse it instead of re-screening and
   re-logging. ADK never persists ``temp:`` keys and strips them from
   client-supplied state deltas, so a client cannot pre-seed the decision.
3. Screens every other text turn in the request, whatever its role (earlier
   messages, the model's replies, text a client wrote into the session),
   that this process has not classified yet. Decisions are kept in a bounded
   in-process cache keyed by the text's SHA-256 hash. It lives on the server
   only (not in session state), so a client can neither read nor seed it, and
   each distinct history text is classified at most once per process; it is
   classified again only after a restart or after the cache evicts it.
4. Blocks the request - returning a refusal ``LlmResponse`` so the model is
   never called - when the classifier flags the new message, when it is too
   long to classify, or when anything in the gate raises (fail closed). The
   refusal carries ``custom_metadata`` with the SHA-256 hash of the blocked
   text, which ADK copies onto the refusal event in the session's event log.
5. Otherwise lets the request continue to the LLM, where Layer 2b (LLM
   contextual safety + compliance) runs via the explicit tools. Before it
   does, every turn whose text is blocked is replaced in the request with a
   placeholder, so blocked text never reaches the model as history. A turn is
   blocked when step 3 flags it, or when its hash is recorded on a refusal
   event in the session's event log (which a client cannot rewrite; session
   state, which a client can overwrite, can only add hashes).

Classification runs in a worker thread (``asyncio.to_thread``), so a long
message does not stall the server's event loop.

``after_model_callback`` logs that a model response was produced.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types as genai_types
from opentelemetry import trace

from .config import Config
from .logging import get_audit_logger, AuditEventType
from .safety import get_text_tool
from .safety.text import TOO_LONG_CATEGORY

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

BLOCKED_MESSAGE = (
    "I'm sorry, but I can't help with that request. "
    "If you believe this was flagged in error, please contact our support team."
)

# Refusal for a message too long for the classifier to screen (see
# ``scope.safety.text.MAX_WINDOWS``).
TOO_LONG_MESSAGE = (
    "I'm sorry, but that message is too long for me to check. "
    "Please send a shorter message."
)

# Text that replaces a blocked turn in later model requests.
WITHHELD_MESSAGE = "[message withheld by SCOPE safety gate]"

# Marker the gate puts in the refusal's ``custom_metadata`` (ADK copies it onto
# the refusal event). The event log is the authoritative record of blocked
# turns: clients can overwrite session state, but not events already appended.
BLOCKED_EVENT_METADATA_KEY = "scope_safety_blocked"
BLOCKED_HASH_METADATA_KEY = "input_sha256"

# Session-state keys (prefixed so they don't collide with application state).
# SHA-256 hashes of the texts the gate has blocked in this session. A copy of
# what the event log records; it can add hashes but is never trusted to
# remove any.
BLOCKED_INPUTS_STATE_KEY = "scope_safety_blocked_inputs"
# The gate decision for the current invocation (one user turn). ``temp:`` keys
# live only for the current invocation: ADK does not persist them and drops
# them from client-supplied state deltas.
GATE_DECISION_STATE_KEY = "temp:scope_safety_gate_decision"

GATE_SPAN_NAME = "scope.pre_model_safety_gate"
HISTORY_SPAN_NAME = "scope.pre_model_history_check"
# Audit ``action`` of the event logged when a history turn is classified.
HISTORY_CHECK_ACTION = "history_check"

# Most decisions the in-process cache keeps. Evicting one only means that
# text is classified again the next time it appears in a request.
SCREENED_CACHE_SIZE = 10_000


def _current_user_id() -> str:
    try:
        return Config().IAM_CURRENT_USER_ID
    except Exception:  # pragma: no cover - config should always load
        return "user"


def _content_text(content: Any) -> str:
    parts = getattr(content, "parts", None) or []
    return "".join(p.text for p in parts if getattr(p, "text", None))


def _text_hash(text: str) -> str:
    # ``surrogatepass`` so that any Python string can be hashed, including
    # one with a lone surrogate (valid JSON, e.g. "\ud800"), which strict
    # UTF-8 encoding rejects. Other text hashes exactly as with plain UTF-8.
    return hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()


def _audit(method: str, **kwargs) -> None:
    """Write an audit event; never raises.

    A logging failure (including one while the audit logger is first created)
    is reported through Python's ``logging`` module and never changes the
    gate's decision.
    """
    try:
        getattr(get_audit_logger(), method)(**kwargs)
    except Exception:
        logger.exception("[SCOPE Layer 2a] Could not write audit event (%s).", method)


class _ScreenedCache:
    """Bounded, thread-safe LRU map: text hash -> blocked (bool).

    Holds the classifier's decisions for texts this process has screened.
    It is tied to one ``TextSafetyTool`` (classifier and thresholds); when the
    shared tool is replaced, the cache starts empty.
    """

    def __init__(self, maxsize: int):
        self._maxsize = maxsize
        self._items: "OrderedDict[str, bool]" = OrderedDict()
        self._owner: Any = None
        self._lock = threading.Lock()

    def _for(self, tool: Any) -> None:
        if tool is not self._owner:
            self._items.clear()
            self._owner = tool

    def get(self, tool: Any, text_hash: str) -> Optional[bool]:
        with self._lock:
            self._for(tool)
            blocked = self._items.get(text_hash)
            if blocked is not None:
                self._items.move_to_end(text_hash)
            return blocked

    def put(self, tool: Any, text_hash: str, blocked: bool) -> None:
        with self._lock:
            self._for(tool)
            self._items[text_hash] = bool(blocked)
            self._items.move_to_end(text_hash)
            while len(self._items) > self._maxsize:
                self._items.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._owner = None


_SCREENED = _ScreenedCache(SCREENED_CACHE_SIZE)


def clear_screened_cache() -> None:
    """Forget every in-process screening decision (tests)."""
    _SCREENED.clear()


def extract_latest_user_text(llm_request: LlmRequest) -> str:
    """Return the text of the most recent ``user`` turn in the request.

    Tool results are ``user``-role contents without text, so they are skipped.
    """
    contents = getattr(llm_request, "contents", None) or []
    for content in reversed(contents):
        if getattr(content, "role", None) != "user":
            continue
        text = _content_text(content)
        if text.strip():
            return text
    return ""


def screened_text(callback_context: Any, llm_request: LlmRequest) -> str:
    """Return the text the gate screens as this invocation's message.

    That is the text of the message that started the invocation
    (``callback_context.user_content``, i.e. the client's new message), whatever
    role the client gave it. A client could send its message with role
    ``model``; screening the latest ``user`` turn alone would then skip it.
    Falls back to the latest ``user`` turn of the request when the new message
    has no text (e.g. only a function response or an image).
    """
    text = _content_text(getattr(callback_context, "user_content", None))
    if text.strip():
        return text
    return extract_latest_user_text(llm_request)


def request_text_turns(llm_request: LlmRequest) -> List[Tuple[str, str]]:
    """Return ``(role, text)`` for every content of the request that has text."""
    turns = []
    for content in getattr(llm_request, "contents", None) or []:
        text = _content_text(content)
        if text.strip():
            turns.append((getattr(content, "role", None) or "user", text))
    return turns


def blocked_input_hashes(callback_context: Any) -> set:
    """Return the SHA-256 hashes of every text the gate blocked in this session.

    Read from the refusal events in the session's event log (their
    ``custom_metadata``), which a client cannot rewrite, plus any hashes in
    the ``scope_safety_blocked_inputs`` state key. State only adds to the set:
    clearing or overwriting it (e.g. via a client ``state_delta``) cannot
    remove a hash the event log records.
    """
    hashes = set()
    session = getattr(callback_context, "session", None)
    for event in getattr(session, "events", None) or ():
        metadata = getattr(event, "custom_metadata", None)
        if isinstance(metadata, dict) and metadata.get(BLOCKED_EVENT_METADATA_KEY) is True:
            text_hash = metadata.get(BLOCKED_HASH_METADATA_KEY)
            if isinstance(text_hash, str):
                hashes.add(text_hash)
    state = getattr(callback_context, "state", None)
    stored = state.get(BLOCKED_INPUTS_STATE_KEY) if state is not None else None
    if isinstance(stored, (list, tuple)):
        hashes.update(h for h in stored if isinstance(h, str))
    return hashes


def redact_blocked_inputs(
    llm_request: LlmRequest, blocked_hashes: Iterable[str]
) -> int:
    """Replace blocked turns in ``llm_request`` with a placeholder.

    A blocked message stays in the ADK session (it is part of the conversation
    record), so ADK would otherwise send it to the model as history on later
    turns. Each content whose text matches a blocked hash is swapped for a new
    content (same role) holding only ``WITHHELD_MESSAGE``; every role is
    checked, because the gate screens text turns of every role. The turn
    itself is kept so the user/model ordering of the request stays valid.
    Returns the number of turns replaced.
    """
    blocked = set(blocked_hashes or ())
    contents = getattr(llm_request, "contents", None)
    if not blocked or not contents:
        return 0
    redacted = 0
    for i, content in enumerate(contents):
        text = _content_text(content)
        if text.strip() and _text_hash(text) in blocked:
            contents[i] = genai_types.Content(
                role=getattr(content, "role", None) or "user",
                parts=[genai_types.Part(text=WITHHELD_MESSAGE)],
            )
            redacted += 1
    return redacted


def _blocked_response(
    text_hash: Optional[str] = None, message: str = BLOCKED_MESSAGE
) -> LlmResponse:
    """Build the LlmResponse returned in place of a model call.

    ``custom_metadata`` marks the refusal with the blocked text's hash; ADK
    copies it onto the refusal event, so the session's event log records which
    text was blocked.
    """
    metadata = None
    if text_hash:
        metadata = {
            BLOCKED_EVENT_METADATA_KEY: True,
            BLOCKED_HASH_METADATA_KEY: text_hash,
        }
    return LlmResponse(
        content=genai_types.Content(
            role="model",
            parts=[genai_types.Part(text=message)],
        ),
        custom_metadata=metadata,
    )


def _screen(user_text: str, user_id: str) -> dict:
    """Log and classify ``user_text``.

    Returns ``{"blocked": bool, "checked": bool, "risk_category": str}``. Runs
    inside a ``scope.pre_model_safety_gate`` span so the check shows up in
    ADK's OpenTelemetry traces.
    """
    with tracer.start_as_current_span(GATE_SPAN_NAME) as span:
        logger.info("[SCOPE Layer 2a] Checking input: %s...", user_text[:50])

        # 1. Log user input
        _audit(
            "log_event",
            event_type=AuditEventType.USER_QUERY,
            user_id=user_id,
            action="user_input",
            details={"input": user_text[:500]},  # Truncate for privacy
        )

        # 2. Run the ML safety check (unless explicitly disabled by config)
        policy = Config().current_policy.safety
        if not policy.use_ml_models:
            _audit(
                "log_event",
                event_type=AuditEventType.USER_QUERY,
                user_id=user_id,
                action="safety_check",
                details={
                    "layer": "2a",
                    "checked": False,
                    "note": "ML pre-model check disabled by SAFETY_USE_ML_MODELS=false; "
                            "relying on Layer 2b (LLM) safety tools",
                },
            )
            span.set_attribute("scope.safety.checked", False)
            span.set_attribute("scope.safety.blocked", False)
            span.set_attribute("scope.safety.outcome", "skipped")
            logger.info("[SCOPE Layer 2a] Skipped (SAFETY_USE_ML_MODELS=false).")
            return {"blocked": False, "checked": False, "risk_category": "none"}

        text_tool = get_text_tool()
        result = text_tool.check(user_text)
        max_score = max(result["scores"].values()) if result["scores"] else 0.0

        span.set_attribute("scope.safety.model", result["model"])
        span.set_attribute("scope.safety.checked", result["checked"])
        span.set_attribute("scope.safety.max_score", float(max_score))
        span.set_attribute("scope.safety.risk_category", result["risk_category"])

        # 3. Log the check result
        _audit(
            "log_event",
            event_type=AuditEventType.USER_QUERY,
            user_id=user_id,
            action="safety_check",
            success=result["checked"],
            error=result.get("error"),
            details={
                "layer": "2a",
                "model": result["model"],
                "checked": result["checked"],
                "is_safe": result["is_safe"],
                "risk_category": result["risk_category"],
                "confidence": result["confidence"],
                "scores": result["scores"],
                "threshold_high": text_tool.threshold_high,
                "chunks": result.get("chunks"),
            },
        )

        if not result["checked"]:
            # Classifier unavailable: fail open to Layer 2b, but make it visible.
            span.set_attribute("scope.safety.blocked", False)
            span.set_attribute("scope.safety.outcome", "unchecked")
            logger.error(
                "[SCOPE Layer 2a] Safety model unavailable (%s); "
                "continuing to Layer 2b LLM checks.",
                result.get("error"),
            )
            return {"blocked": False, "checked": False, "risk_category": "none"}

        # 4. Block if unsafe (including text too long to classify)
        if not result["is_safe"]:
            span.set_attribute("scope.safety.blocked", True)
            span.set_attribute("scope.safety.outcome", "blocked")
            logger.warning(
                "[SCOPE Layer 2a] BLOCKED: %s (%.2f)",
                result["risk_category"], result["confidence"],
            )
            _audit(
                "log_safety_block",
                user_id=user_id,
                input_text=user_text[:100],
                risk_category=result["risk_category"],
            )
            return {
                "blocked": True, "checked": True,
                "risk_category": result["risk_category"],
            }

        # 5. Pass
        span.set_attribute("scope.safety.blocked", False)
        span.set_attribute("scope.safety.outcome", "allowed")
        logger.info(
            "[SCOPE Layer 2a] Passed (max score %.2f).", result["confidence"]
        )
        return {"blocked": False, "checked": True, "risk_category": "none"}


def _screen_history(
    turns: List[Tuple[str, str, str]], user_id: str
) -> Tuple[Dict[str, bool], bool]:
    """Classify history turns this process has not screened yet.

    ``turns`` holds ``(hash, role, text)``. All of them are classified in
    batched calls inside a ``scope.pre_model_history_check`` span, and each
    is logged as a ``history_check`` audit event. Returns ``(decisions,
    cacheable)``: ``decisions`` maps hash -> blocked; ``cacheable`` is False
    when classification raised, in which case every turn is reported blocked
    (withheld from this request, fail closed) but the result is not cached.
    If the classifier is unavailable, nothing is classified (fail open, as
    for the new message) and ``decisions`` is empty.
    """
    text_tool = get_text_tool()
    with tracer.start_as_current_span(HISTORY_SPAN_NAME) as span:
        span.set_attribute("scope.safety.history_turns", len(turns))
        if not text_tool.available:
            span.set_attribute("scope.safety.outcome", "unchecked")
            return {}, False
        try:
            results = text_tool.check_many([text for _, _, text in turns])
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:_MAX_LOGGED_CHARS]
            logger.exception(
                "[SCOPE Layer 2a] Screening history raised (%s); "
                "withholding those turns from this request.", error,
            )
            _audit(
                "log_event",
                event_type=AuditEventType.USER_QUERY,
                user_id=user_id,
                action=HISTORY_CHECK_ACTION,
                success=False,
                error=error,
                details={
                    "layer": "2a",
                    "checked": False,
                    "turns": len(turns),
                    "withheld": True,
                    "note": "screening raised; turns withheld from this request",
                },
            )
            span.set_attribute("scope.safety.withheld", len(turns))
            span.set_attribute("scope.safety.outcome", "error")
            return {text_hash: True for text_hash, _, _ in turns}, False

        decisions = {}
        for (text_hash, role, text), result in zip(turns, results):
            if not result["checked"]:
                continue
            blocked = not result["is_safe"]
            decisions[text_hash] = blocked
            _audit(
                "log_event",
                event_type=AuditEventType.USER_QUERY,
                user_id=user_id,
                action=HISTORY_CHECK_ACTION,
                details={
                    "layer": "2a",
                    "role": role,
                    "input_sha256": text_hash,
                    "input": text[:100],  # Truncate for privacy
                    "model": result["model"],
                    "is_safe": result["is_safe"],
                    "risk_category": result["risk_category"],
                    "confidence": result["confidence"],
                    "scores": result["scores"],
                    "chunks": result.get("chunks"),
                    "withheld": blocked,
                },
            )
        withheld = sum(decisions.values())
        span.set_attribute("scope.safety.withheld", withheld)
        span.set_attribute("scope.safety.outcome", "withheld" if withheld else "allowed")
        if withheld:
            logger.warning(
                "[SCOPE Layer 2a] Withholding %d history turn(s) from the model.",
                withheld,
            )
        return decisions, True


def _classify(
    user_text: Optional[str],
    history: List[Tuple[str, str, str]],
    user_id: str,
) -> Tuple[Optional[dict], Dict[str, bool], bool]:
    """Screen the new message and unscreened history (runs in a worker thread).

    History is not screened when the new message is blocked: the request is
    refused, so no history reaches the model.
    """
    decision = _screen(user_text, user_id) if user_text else None
    if history and not (decision and decision["blocked"]):
        decisions, cacheable = _screen_history(history, user_id)
    else:
        decisions, cacheable = {}, True
    return decision, decisions, cacheable


def _screening_failed(user_text: str, user_id: str, exc: Exception) -> dict:
    """Handle an exception raised in the gate: refuse the request.

    The text was not classified, so it is treated like a blocked message (fail
    closed): the request is refused and its hash recorded, so it is also
    withheld from later model calls. Logging is best effort, so a broken audit
    logger cannot turn the refusal back into an exception.
    """
    error = f"{type(exc).__name__}: {exc}"[:_MAX_LOGGED_CHARS]
    logger.exception(
        "[SCOPE Layer 2a] Screening raised (%s); refusing the request.", error
    )
    _audit(
        "log_event",
        event_type=AuditEventType.USER_QUERY,
        user_id=user_id,
        action="safety_check",
        success=False,
        error=error,
        details={
            "layer": "2a",
            "checked": False,
            "blocked": True,
            "note": "screening raised; request refused (fail closed)",
        },
    )
    _audit(
        "log_safety_block",
        user_id=user_id,
        input_text=(user_text or "")[:100],
        risk_category="screening_error",
    )
    return {"blocked": True, "checked": False, "risk_category": "screening_error"}


def _record_block(state: Any, text_hash: str) -> None:
    """Record a blocked text in the in-process cache and the session state.

    The refusal event (written by ADK after the callback returns) is the
    durable record; these copies cover the gap until it is written, and the
    case where it never is (e.g. the invocation is cancelled first).
    """
    try:
        _SCREENED.put(get_text_tool(), text_hash, True)
    except Exception:  # pragma: no cover - get_text_tool should not raise
        logger.exception("[SCOPE Layer 2a] Could not cache the blocked text.")
    if state is not None:
        stored = state.get(BLOCKED_INPUTS_STATE_KEY)
        blocked = list(stored) if isinstance(stored, (list, tuple)) else []
        if text_hash not in blocked:
            # Assign a new list so ADK records the state change.
            state[BLOCKED_INPUTS_STATE_KEY] = blocked + [text_hash]


async def _gate(
    callback_context: Any,
    llm_request: LlmRequest,
    user_text: str,
    text_hash: Optional[str],
) -> Optional[LlmResponse]:
    """The gate's decision for one model call (see ``fast_guardrail_callback``)."""
    state = getattr(callback_context, "state", None)
    invocation_id = getattr(callback_context, "invocation_id", None)
    user_id = _current_user_id()

    decision = None
    if user_text:
        cached = state.get(GATE_DECISION_STATE_KEY) if state is not None else None
        if (
            invocation_id
            and isinstance(cached, dict)
            and cached.get("invocation_id") == invocation_id
            and cached.get("input_sha256") == text_hash
        ):
            # Later model call in the same turn (tool loop): reuse the decision.
            decision = cached

    # Every other text turn in the request: withheld if a refusal recorded it
    # or this process classified it as blocked; classified now if this
    # process has not seen it (skipped when ML screening is disabled).
    withheld = blocked_input_hashes(callback_context)
    unscreened = []
    if Config().current_policy.safety.use_ml_models:
        text_tool = get_text_tool()
        seen = {text_hash}
        for role, text in request_text_turns(llm_request):
            turn_hash = _text_hash(text)
            if turn_hash in seen or turn_hash in withheld:
                continue
            seen.add(turn_hash)
            blocked = _SCREENED.get(text_tool, turn_hash)
            if blocked is None:
                unscreened.append((turn_hash, role, text))
            elif blocked:
                withheld.add(turn_hash)

    if (user_text and decision is None) or unscreened:
        screened, history, cacheable = await asyncio.to_thread(
            _classify, user_text if decision is None else None, unscreened, user_id
        )
        if screened is not None:
            decision = screened
            if decision["checked"]:
                _SCREENED.put(get_text_tool(), text_hash, decision["blocked"])
            if state is not None:
                state[GATE_DECISION_STATE_KEY] = {
                    "invocation_id": invocation_id,
                    "input_sha256": text_hash,
                    **decision,
                }
        if cacheable:
            text_tool = get_text_tool()
            for turn_hash, blocked in history.items():
                _SCREENED.put(text_tool, turn_hash, blocked)
        withheld.update(h for h, blocked in history.items() if blocked)

    if decision and decision["blocked"]:
        _record_block(state, text_hash)
        message = (
            TOO_LONG_MESSAGE
            if decision.get("risk_category") == TOO_LONG_CATEGORY
            else BLOCKED_MESSAGE
        )
        return _blocked_response(text_hash, message)

    # Blocked text must not reach the model, as history or otherwise.
    redact_blocked_inputs(llm_request, withheld)
    return None  # Continue to the LLM


async def fast_guardrail_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Layer 2a pre-model safety gate.

    Runs before every LLM request. Returns an ``LlmResponse`` to block the
    request (the model is never called), or ``None`` to continue.

    The client's new message is screened (and logged) once per invocation;
    the decision is cached under a ``temp:`` state key and applied to every
    model call of that invocation. Every other text turn of the request is
    screened once per process, and blocked turns (flagged now, or recorded on
    a refusal event) are redacted before the request reaches the model. If
    anything in the gate raises, the request is refused and the new message's
    hash recorded (fail closed).
    """
    user_text = ""
    text_hash = None
    try:
        user_text = screened_text(callback_context, llm_request)
        text_hash = _text_hash(user_text) if user_text else None
        return await _gate(callback_context, llm_request, user_text, text_hash)
    except Exception as exc:
        _screening_failed(user_text, _current_user_id(), exc)
        if text_hash:
            try:
                _record_block(getattr(callback_context, "state", None), text_hash)
            except Exception:
                logger.exception("[SCOPE Layer 2a] Could not record the refused text.")
        return _blocked_response(text_hash)


def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> Optional[LlmResponse]:
    """Runs after the LLM generates a response; logs it for the audit trail.

    Records the response text (truncated to 500 chars) and the names of any
    tools the model asked to call. The text is not redacted: if the model
    repeats data from a tool response (e.g. a balance), that data is logged.

    Returns ``None``: ADK treats a non-``None`` return as a replacement
    response, so the model's response is passed on unchanged.
    """
    audit = get_audit_logger()

    content = getattr(llm_response, "content", None)
    parts = (getattr(content, "parts", None) or []) if content else []
    text = "".join(p.text for p in parts if getattr(p, "text", None))
    function_calls = [
        p.function_call.name for p in parts if getattr(p, "function_call", None)
    ]

    audit.log_event(
        event_type=AuditEventType.USER_QUERY,
        user_id=_current_user_id(),
        action="llm_response",
        details={
            "model": Config().agent_settings.model,
            "response_received": llm_response is not None,
            "text": text[:500],  # Truncated for log size; not redacted
            "function_calls": function_calls,
        },
    )

    logger.info("[SCOPE After LLM] Response logged")
    return None


# --- Tool-call audit trail ---------------------------------------------------

# Argument names whose values are never copied into the audit trail.
_SENSITIVE_ARG_MARKERS = ("password", "secret", "token", "api_key", "ssn", "card")
_MAX_LOGGED_CHARS = 200

# String tool responses that start with one of these (after leading
# whitespace) are error / denial messages.
_TOOL_ERROR_PREFIXES = ("Error", "❌", "⚠️ Failed")


def _summarize_tool_args(args: Optional[dict]) -> dict:
    """Copy tool arguments for the audit log without dumping them wholesale.

    Values of sensitive-looking keys are redacted, long strings are truncated,
    and non-scalar values are replaced by their type name.
    """
    summary = {}
    for key, value in (args or {}).items():
        if any(marker in key.lower() for marker in _SENSITIVE_ARG_MARKERS):
            summary[key] = "[REDACTED]"
        elif isinstance(value, str):
            summary[key] = (
                value if len(value) <= _MAX_LOGGED_CHARS
                else value[:_MAX_LOGGED_CHARS] + "..."
            )
        elif value is None or isinstance(value, (bool, int, float)):
            summary[key] = value
        else:
            summary[key] = f"<{type(value).__name__}>"
    return summary


def _tool_response_error(tool_response) -> Optional[str]:
    """Return the error text if a tool response reports a failure, else None.

    A response counts as a failure when it is:

    * a string starting with one of ``_TOOL_ERROR_PREFIXES``;
    * a dict with a non-empty ``"error"`` value; or
    * a string holding a JSON object with a non-empty ``"error"`` value.

    Anything else (including "not found" style replies) counts as success.
    """
    if isinstance(tool_response, str):
        stripped = tool_response.strip()
        if stripped.startswith(_TOOL_ERROR_PREFIXES):
            return stripped[:_MAX_LOGGED_CHARS]
        if stripped.startswith("{"):
            try:
                tool_response = json.loads(stripped)
            except ValueError:
                return None
    if isinstance(tool_response, dict) and tool_response.get("error"):
        return str(tool_response["error"])[:_MAX_LOGGED_CHARS]
    return None


def _current_user_role() -> str:
    try:
        return Config().IAM_CURRENT_USER_ROLE
    except Exception:  # pragma: no cover - config should always load
        return "unknown"


def audit_tool_call_callback(tool, args: dict, tool_context, tool_response):
    """``after_tool_callback``: write one ``tool_call`` audit event per tool run.

    Logs the tool name, a redacted / truncated copy of its arguments, the user
    ID and role, and whether the tool reported an error. The tool's response
    body is not copied into this event (only its length); tools log their own
    domain events. This is not a privacy guarantee for the audit trail as a
    whole: the ``llm_response`` event logs up to 500 chars of model text, which
    may repeat data from the tool response.

    Never raises: a logging failure is reported through Python's ``logging``
    module. Returns ``None`` so the tool's response reaches the model
    unchanged.
    """
    try:
        error = _tool_response_error(tool_response)
        get_audit_logger().log_tool_call(
            user_id=_current_user_id(),
            role=_current_user_role(),
            tool_name=getattr(tool, "name", str(tool)),
            parameters=_summarize_tool_args(args),
            result=None if error else f"returned {len(str(tool_response))} chars",
            error=error,
        )
    except Exception:
        logger.exception("[SCOPE Audit] Failed to log tool call")
    return None


def audit_tool_error_callback(tool, args: dict, tool_context, error: Exception):
    """``on_tool_error_callback``: log a tool call that raised an exception.

    Never raises: a logging failure is reported through Python's ``logging``
    module. Returns ``None`` so ADK still surfaces the original exception.
    """
    try:
        get_audit_logger().log_tool_call(
            user_id=_current_user_id(),
            role=_current_user_role(),
            tool_name=getattr(tool, "name", str(tool)),
            parameters=_summarize_tool_args(args),
            error=f"{type(error).__name__}: {error}"[:_MAX_LOGGED_CHARS],
        )
    except Exception:
        logger.exception("[SCOPE Audit] Failed to log tool error")
    return None
