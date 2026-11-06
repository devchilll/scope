"""ADK model callbacks: pre-model safety gate and post-model audit logging.

``fast_guardrail_callback`` is registered as the agent's ``before_model_callback``
and runs before *every* LLM request. It:

1. Takes the text of the message that started the invocation (the new user
   message, whatever role the client gave it).
2. Screens it once per invocation (one user turn): logs the input to the audit
   trail and runs the Layer 2a ML text-safety check (``unitary/toxic-bert``)
   inside a ``scope.pre_model_safety_gate`` OpenTelemetry span. The decision
   is cached under a ``temp:`` session-state key, so the later model calls of
   the same turn (ADK's tool loop) reuse it instead of re-screening and
   re-logging. ADK never persists ``temp:`` keys and strips them from
   client-supplied state deltas, so a client cannot pre-seed the decision.
3. Blocks the request - returning a refusal ``LlmResponse`` so the model is
   never called - when the classifier flags it, or when screening raises
   (fail closed). The refusal carries ``custom_metadata`` with the SHA-256
   hash of the blocked text, which ADK copies onto the refusal event in the
   session's event log.
4. Otherwise lets the request continue to the LLM, where Layer 2b (LLM
   contextual safety + compliance) runs via the explicit tools. Before it
   does, any earlier turn whose text was blocked is replaced in the request
   with a placeholder, so blocked text never reaches the model as history.
   Blocked hashes are read from the session's event log, which a client
   cannot rewrite; session state (which a client can overwrite) can only add
   to them.

``after_model_callback`` logs that a model response was produced.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Iterable, Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types as genai_types
from opentelemetry import trace

from .config import Config
from .logging import get_audit_logger, AuditEventType
from .safety import get_text_tool

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

BLOCKED_MESSAGE = (
    "I'm sorry, but I can't help with that request. "
    "If you believe this was flagged in error, please contact our support team."
)

# Text that replaces a previously blocked user turn in later model requests.
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


def _current_user_id() -> str:
    try:
        return Config().IAM_CURRENT_USER_ID
    except Exception:  # pragma: no cover - config should always load
        return "user"


def _content_text(content: Any) -> str:
    parts = getattr(content, "parts", None) or []
    return "".join(p.text for p in parts if getattr(p, "text", None))


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_latest_user_text(llm_request: LlmRequest) -> str:
    """Return the text of the most recent ``user`` turn in the request.

    Only the latest user turn is screened: earlier turns were already checked
    when they arrived, and model turns are not user input. Tool results are
    ``user``-role contents without text, so they are skipped.
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
    """Return the text the gate screens for this invocation.

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
    """Replace previously blocked turns in ``llm_request`` with a placeholder.

    A blocked message stays in the ADK session (it is part of the conversation
    record), so ADK would otherwise send it to the model as history on later
    turns. Each content whose text matches a blocked hash is swapped for a new
    content (same role) holding only ``WITHHELD_MESSAGE``; every role is
    checked, because the gate screens the client's message whatever its role.
    The turn itself is kept so the user/model ordering of the request stays
    valid. Returns the number of turns replaced.
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
    """Log and classify ``user_text``; return ``{"blocked": bool, "checked": bool}``.

    Runs inside a ``scope.pre_model_safety_gate`` span so the check shows up
    in ADK's OpenTelemetry traces.
    """
    audit = get_audit_logger()

    with tracer.start_as_current_span(GATE_SPAN_NAME) as span:
        logger.info("[SCOPE Layer 2a] Checking input: %s...", user_text[:50])

        # 1. Log user input
        audit.log_event(
            event_type=AuditEventType.USER_QUERY,
            user_id=user_id,
            action="user_input",
            details={"input": user_text[:500]},  # Truncate for privacy
        )

        # 2. Run the ML safety check (unless explicitly disabled by config)
        policy = Config().current_policy.safety
        if not policy.use_ml_models:
            audit.log_event(
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
            return {"blocked": False, "checked": False}

        text_tool = get_text_tool()
        result = text_tool.check(user_text)
        max_score = max(result["scores"].values()) if result["scores"] else 0.0

        span.set_attribute("scope.safety.model", result["model"])
        span.set_attribute("scope.safety.checked", result["checked"])
        span.set_attribute("scope.safety.max_score", float(max_score))
        span.set_attribute("scope.safety.risk_category", result["risk_category"])

        # 3. Log the check result
        audit.log_event(
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
            return {"blocked": False, "checked": False}

        # 4. Block if unsafe
        if not result["is_safe"]:
            span.set_attribute("scope.safety.blocked", True)
            span.set_attribute("scope.safety.outcome", "blocked")
            logger.warning(
                "[SCOPE Layer 2a] BLOCKED: %s (%.2f)",
                result["risk_category"], result["confidence"],
            )
            audit.log_safety_block(
                user_id=user_id,
                input_text=user_text[:100],
                risk_category=result["risk_category"],
            )
            return {"blocked": True, "checked": True}

        # 5. Pass
        span.set_attribute("scope.safety.blocked", False)
        span.set_attribute("scope.safety.outcome", "allowed")
        logger.info(
            "[SCOPE Layer 2a] Passed (max score %.2f).", result["confidence"]
        )
        return {"blocked": False, "checked": True}


def _screening_failed(user_text: str, user_id: str, exc: Exception) -> dict:
    """Handle an exception raised while screening: refuse the request.

    The text was not classified, so it is treated like a blocked message (fail
    closed): the request is refused and its hash recorded, so it is also
    withheld from later model calls. Logging is best effort, so a broken audit
    logger cannot turn the refusal back into an exception.
    """
    error = f"{type(exc).__name__}: {exc}"[:_MAX_LOGGED_CHARS]
    logger.exception(
        "[SCOPE Layer 2a] Screening raised (%s); refusing the request.", error
    )
    try:
        audit = get_audit_logger()
        audit.log_event(
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
        audit.log_safety_block(
            user_id=user_id,
            input_text=user_text[:100],
            risk_category="screening_error",
        )
    except Exception:  # pragma: no cover - logging must not undo the refusal
        logger.exception("[SCOPE Layer 2a] Could not audit-log the screening error.")
    return {"blocked": True, "checked": False}


def fast_guardrail_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Layer 2a pre-model safety gate.

    Runs before every LLM request. Returns an ``LlmResponse`` to block the
    request (the model is never called), or ``None`` to continue.

    The client's new message is screened (and logged) once per invocation;
    the decision is cached under a ``temp:`` state key and applied to every
    model call of that invocation. If screening raises, the request is
    refused. Previously blocked turns, found via the event log, are redacted
    from the request before it reaches the model.
    """
    state = getattr(callback_context, "state", None)
    invocation_id = getattr(callback_context, "invocation_id", None)
    user_text = screened_text(callback_context, llm_request)

    decision = None
    text_hash = None
    if user_text:
        text_hash = _text_hash(user_text)
        cached = state.get(GATE_DECISION_STATE_KEY) if state is not None else None
        if (
            invocation_id
            and isinstance(cached, dict)
            and cached.get("invocation_id") == invocation_id
            and cached.get("input_sha256") == text_hash
        ):
            # Later model call in the same turn (tool loop): reuse the decision.
            decision = cached
        else:
            user_id = _current_user_id()
            try:
                decision = _screen(user_text, user_id)
            except Exception as exc:
                decision = _screening_failed(user_text, user_id, exc)
            if state is not None:
                state[GATE_DECISION_STATE_KEY] = {
                    "invocation_id": invocation_id,
                    "input_sha256": text_hash,
                    **decision,
                }
                if decision["blocked"]:
                    stored = state.get(BLOCKED_INPUTS_STATE_KEY)
                    blocked = list(stored) if isinstance(stored, (list, tuple)) else []
                    if text_hash not in blocked:
                        # Assign a new list so ADK records the state change.
                        state[BLOCKED_INPUTS_STATE_KEY] = blocked + [text_hash]

    if decision and decision["blocked"]:
        return _blocked_response(text_hash)

    # Earlier blocked messages must not reach the model as conversation history.
    redact_blocked_inputs(llm_request, blocked_input_hashes(callback_context))
    return None  # Continue to the LLM


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
