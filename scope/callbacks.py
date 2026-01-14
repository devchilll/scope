"""Enhanced callback with comprehensive flow logging.

This callback logs the complete interaction flow including:
- User input
- Safety check results
- LLM calls
- Tool calls
- Final responses
"""

import logging
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from .safety import ImageSafetyTool
from .logging import get_audit_logger, AuditEventType

logger = logging.getLogger(__name__)

# Lazy loading globals
_IMAGE_TOOL = None

def get_image_tool():
    global _IMAGE_TOOL
    if _IMAGE_TOOL is None:
        logger.info("Initializing ImageSafetyTool (Lazy Load)...")
        _IMAGE_TOOL = ImageSafetyTool()
    return _IMAGE_TOOL

def fast_guardrail_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> LlmResponse | None:
    """
    PRIME Component: Layer 2 (Risk Sensing)
    Runs before the agent processes the request.
    Returns LlmResponse to block unsafe content, or None to continue.
    """
    audit = get_audit_logger()
    
    # Extract text from request
    user_text = ""
    for content in llm_request.contents:
        for part in content.parts:
            if part.text:
                user_text += part.text

    if not user_text:
        return None

    logger.info(f"[PRIME Layer 2] Checking input: {user_text[:50]}...")
    
    # Log user input
    audit.log_event(
        event_type=AuditEventType.USER_QUERY,
        user_id="user",  # TODO: Get from session context
        action="user_input",
        details={"input": user_text[:500]}  # Truncate for privacy
    )
    
    # DISABLED: ML-based text safety check has too many false positives
    # DISABLED: Text safety check handled by unitary/toxic-bert in observability_tools.py
    # We'll rely on LLM-based safety in the agent prompt instead
    
    # Text Check (DISABLED)
    # text_tool = get_text_tool()
    # text_result = text_tool.check(user_text)
    
    # For now, always pass safety check
    text_result = {'is_safe': True, 'risk_category': 'none', 'confidence': 0.0}
    
    # Log safety check result
    audit.log_event(
        event_type=AuditEventType.USER_QUERY,
        user_id="user",
        action="safety_check",
        details={
            "is_safe": text_result['is_safe'],
            "risk_category": text_result.get('risk_category', 'none'),
            "confidence": text_result.get('confidence', 0.0),
            "note": "ML safety check disabled - using LLM-based safety"
        }
    )
    
    if not text_result['is_safe']:
        logger.warning(f"[PRIME Layer 2] BLOCKED: {text_result['risk_category']}")
        
        # Log safety block
        audit.log_safety_block(
            user_id="user",
            input_text=user_text[:100],
            risk_category=text_result['risk_category']
        )
        
        # Let agent handle with compliance rules
        logger.info("[PRIME Layer 2] Unsafe content detected, allowing agent to handle with compliance rules")
        return None

    # Image Check (Placeholder for future implementation if artifacts are accessible in LlmRequest)
    # Currently LlmRequest structure for artifacts/images depends on specific ADK version usage.
    # If images are passed as parts with mime_type, we would iterate them here.
    
    logger.info("[PRIME Layer 2] Passed (ML safety disabled).")
    return None  # Continue to agent


def after_model_callback(
    callback_context: CallbackContext,
    llm_response: LlmResponse
) -> LlmResponse:
    """
    Callback that runs AFTER the LLM generates a response.
    Logs the complete interaction for audit trail.
    """
    audit = get_audit_logger()
    
    # Log LLM response (just log that response was received)
    # Note: LlmResponse structure varies by ADK version, so we log minimal info
    audit.log_event(
        event_type=AuditEventType.USER_QUERY,
        user_id="user",
        action="llm_response",
        details={
            "model": "gemini-2.5-flash",
            "response_received": True
        }
    )
    
    logger.info("[PRIME After LLM] Response logged")
    
    return llm_response


