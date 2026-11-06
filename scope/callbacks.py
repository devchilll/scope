"""ADK model callbacks: pre-model safety gate and post-model audit logging.

``fast_guardrail_callback`` is registered as the agent's ``before_model_callback``
and runs on *every* LLM request, before the model acts. It:

1. Extracts the latest user turn from the request.
2. Logs the input to the audit trail.
3. Runs the Layer 2a ML text-safety check (``unitary/toxic-bert``).
4. Blocks the request - returning a refusal ``LlmResponse`` so the model is
   never called - when the classifier flags it, and logs the block.
5. Otherwise logs the pass and lets the request continue to the LLM, where
   Layer 2b (LLM contextual safety + compliance) runs via the explicit tools.

``after_model_callback`` logs that a model response was produced.
"""

from __future__ import annotations

import logging
from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types as genai_types

from .config import Config
from .logging import get_audit_logger, AuditEventType
from .safety import ImageSafetyTool, get_text_tool

logger = logging.getLogger(__name__)

# Lazy loading globals
_IMAGE_TOOL = None

BLOCKED_MESSAGE = (
    "I'm sorry, but I can't help with that request. "
    "If you believe this was flagged in error, please contact our support team."
)


def get_image_tool():
    global _IMAGE_TOOL
    if _IMAGE_TOOL is None:
        logger.info("Initializing ImageSafetyTool (Lazy Load)...")
        _IMAGE_TOOL = ImageSafetyTool()
    return _IMAGE_TOOL


def _current_user_id() -> str:
    try:
        return Config().IAM_CURRENT_USER_ID
    except Exception:  # pragma: no cover - config should always load
        return "user"


def extract_latest_user_text(llm_request: LlmRequest) -> str:
    """Return the text of the most recent ``user`` turn in the request.

    Only the latest user turn is screened: earlier turns were already checked
    when they arrived, and model turns are not user input.
    """
    contents = getattr(llm_request, "contents", None) or []
    for content in reversed(contents):
        if getattr(content, "role", None) != "user":
            continue
        parts = getattr(content, "parts", None) or []
        text = "".join(p.text for p in parts if getattr(p, "text", None))
        if text.strip():
            return text
    return ""


def _blocked_response(message: str = BLOCKED_MESSAGE) -> LlmResponse:
    """Build the LlmResponse returned in place of a model call."""
    return LlmResponse(
        content=genai_types.Content(
            role="model",
            parts=[genai_types.Part(text=message)],
        )
    )


def fast_guardrail_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Layer 2a pre-model safety gate.

    Runs before the LLM processes the request. Returns an ``LlmResponse`` to
    block the request (the model is never called), or ``None`` to continue.
    """
    audit = get_audit_logger()
    user_id = _current_user_id()
    user_text = extract_latest_user_text(llm_request)

    if not user_text:
        return None

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
        logger.info("[SCOPE Layer 2a] Skipped (SAFETY_USE_ML_MODELS=false).")
        return None

    text_tool = get_text_tool()
    result = text_tool.check(user_text)

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
        },
    )

    if not result["checked"]:
        # Classifier unavailable: fail open to Layer 2b, but make it visible.
        logger.error(
            "[SCOPE Layer 2a] Safety model unavailable (%s); "
            "continuing to Layer 2b LLM checks.",
            result.get("error"),
        )
        return None

    # 4. Block if unsafe
    if not result["is_safe"]:
        logger.warning(
            "[SCOPE Layer 2a] BLOCKED: %s (%.2f)",
            result["risk_category"], result["confidence"],
        )
        audit.log_safety_block(
            user_id=user_id,
            input_text=user_text[:100],
            risk_category=result["risk_category"],
        )
        return _blocked_response()

    # 5. Pass
    logger.info(
        "[SCOPE Layer 2a] Passed (max score %.2f).", result["confidence"]
    )
    return None  # Continue to the LLM


def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> LlmResponse:
    """Runs after the LLM generates a response; logs it for the audit trail.

    Records the response text (truncated to 500 chars) and the names of any
    tools the model asked to call.
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
            "text": text[:500],  # Truncate for privacy / log size
            "function_calls": function_calls,
        },
    )

    logger.info("[SCOPE After LLM] Response logged")
    return llm_response


# --- Tool-call audit trail ---------------------------------------------------

# Argument names whose values are never copied into the audit trail.
_SENSITIVE_ARG_MARKERS = ("password", "secret", "token", "api_key", "ssn", "card")
_MAX_LOGGED_CHARS = 200

# Tool responses that start with one of these are error / denial messages.
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
    """Return the error text if a tool response reports a failure, else None."""
    if isinstance(tool_response, str):
        if tool_response.lstrip().startswith(_TOOL_ERROR_PREFIXES):
            return tool_response.strip()[:_MAX_LOGGED_CHARS]
    elif isinstance(tool_response, dict) and tool_response.get("error"):
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
    body is not copied (only its length); tools log their own domain events.

    Returns ``None`` so the tool's response reaches the model unchanged.
    """
    error = _tool_response_error(tool_response)
    get_audit_logger().log_tool_call(
        user_id=_current_user_id(),
        role=_current_user_role(),
        tool_name=getattr(tool, "name", str(tool)),
        parameters=_summarize_tool_args(args),
        result=None if error else f"returned {len(str(tool_response))} chars",
        error=error,
    )
    return None


def audit_tool_error_callback(tool, args: dict, tool_context, error: Exception):
    """``on_tool_error_callback``: log a tool call that raised an exception.

    Returns ``None`` so ADK still surfaces the original exception.
    """
    get_audit_logger().log_tool_call(
        user_id=_current_user_id(),
        role=_current_user_role(),
        tool_name=getattr(tool, "name", str(tool)),
        parameters=_summarize_tool_args(args),
        error=f"{type(error).__name__}: {error}"[:_MAX_LOGGED_CHARS],
    )
    return None
