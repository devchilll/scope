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
    """Runs after the LLM generates a response; logs it for the audit trail."""
    audit = get_audit_logger()

    audit.log_event(
        event_type=AuditEventType.USER_QUERY,
        user_id=_current_user_id(),
        action="llm_response",
        details={
            "model": Config().agent_settings.model,
            "response_received": llm_response is not None,
        },
    )

    logger.info("[SCOPE After LLM] Response logged")
    return llm_response
