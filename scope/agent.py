import logging
from google.adk.agents import LlmAgent
from google.adk.agents.readonly_context import ReadonlyContext
from google.genai import types as genai_types

from .config import Config
from .prompt import build_instruction
from .callbacks import fast_guardrail_callback, after_model_callback
from .callbacks import audit_tool_call_callback, audit_tool_error_callback
from .compliance import transform_rules
from .data.tools import BANKING_TOOLS
from .observability_tools import OBSERVABILITY_TOOLS

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Config
configs = Config()
policy = configs.current_policy

# Transform human-readable compliance rules at agent init
logger.info("Initializing SCOPE agent...")
if policy.compliance.enabled and policy.compliance.raw_rules:
    logger.info(f"Transforming {len(policy.compliance.raw_rules)} compliance rules...")
    policy.compliance.transformed_rules = transform_rules(policy.compliance.raw_rules)
    logger.info(f"Compliance rules transformed: {policy.compliance.transformed_rules}")

# Combine all tools
ALL_TOOLS = BANKING_TOOLS + OBSERVABILITY_TOOLS

# Custom GOOGLE_COMPLIANCE_RULES (if any) are appended to the instruction
INSTRUCTION = build_instruction(policy.compliance.transformed_rules)


def _instruction(ctx: ReadonlyContext) -> str:
    """Return the agent instruction verbatim.

    ADK treats a plain-string instruction as a template and replaces
    ``{name}`` with session state, raising KeyError for unknown names. An
    InstructionProvider bypasses that, so braces in custom compliance rules
    reach the model as written. The base instruction uses no templating.
    """
    return INSTRUCTION

# Define the root agent
root_agent = LlmAgent(
    name=configs.agent_settings.name,
    model=configs.agent_settings.model,
    instruction=_instruction,
    tools=ALL_TOOLS,  # Add banking + observability tools
    # Layer 2a: every request is screened by the ML safety check BEFORE the
    # model runs. The explicit safety_check_layer1/2 tools remain for trace
    # visibility and Layer 2b (LLM contextual) checks.
    before_model_callback=fast_guardrail_callback,
    after_model_callback=after_model_callback,
    # Every tool invocation (including errors) gets a tool_call audit event.
    after_tool_callback=audit_tool_call_callback,
    on_tool_error_callback=audit_tool_error_callback,
    generate_content_config=genai_types.GenerateContentConfig(
        temperature=0.7,  # More natural responses
        # Removed response_mime_type - let agent respond naturally
    )
)

logger.info(f"Agent '{root_agent.name}' initialized with model '{root_agent.model}' and {len(ALL_TOOLS)} tools")
