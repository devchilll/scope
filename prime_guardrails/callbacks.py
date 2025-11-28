import logging
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse, Content, Part
from .safety import TextSafetyTool, ImageSafetyTool

logger = logging.getLogger(__name__)

# Lazy loading globals
_TEXT_TOOL = None
_IMAGE_TOOL = None

def get_text_tool():
    global _TEXT_TOOL
    if _TEXT_TOOL is None:
        logger.info("Initializing TextSafetyTool (Lazy Load)...")
        _TEXT_TOOL = TextSafetyTool()
    return _TEXT_TOOL

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
    # Extract text from request
    user_text = ""
    for content in llm_request.contents:
        for part in content.parts:
            if part.text:
                user_text += part.text

    if not user_text:
        return None

    logger.info(f"[PRIME Layer 2] Checking input: {user_text[:50]}...")
    
    # Text Check
    text_tool = get_text_tool()
    text_result = text_tool.check(user_text)
    
    if not text_result['is_safe']:
        logger.warning(f"[PRIME Layer 2] BLOCKED: {text_result['risk_category']}")
        
        # Return a safety refusal response instead of raising exception
        refusal_message = (
            "I cannot process this request as it was flagged by our safety systems. "
            f"Reason: {text_result['risk_category']}. "
            "Please rephrase your question in a respectful manner."
        )
        
        return LlmResponse(
            candidates=[
                Content(
                    parts=[Part(text=refusal_message)],
                    role="model"
                )
            ]
        )

    # Image Check (Placeholder for future implementation if artifacts are accessible in LlmRequest)
    # Currently LlmRequest structure for artifacts/images depends on specific ADK version usage.
    # If images are passed as parts with mime_type, we would iterate them here.
    
    logger.info("[PRIME Layer 2] Passed.")
    return None  # Continue to agent

