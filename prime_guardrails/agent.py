import logging
from google.adk.agents import LlmAgent
from google.genai import types as genai_types

from .config import Config
from .prompt import ROUTER_INSTRUCTIONS
from .callbacks import fast_guardrail_callback, after_model_callback
from .compliance import transform_rules
from .data.tools import BANKING_TOOLS

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Config
configs = Config()
policy = configs.current_policy

# Transform human-readable compliance rules at agent init
logger.info("Initializing PRIME agent...")
if policy.compliance.enabled and policy.compliance.raw_rules:
    logger.info(f"Transforming {len(policy.compliance.raw_rules)} compliance rules...")
    policy.compliance.transformed_rules = transform_rules(policy.compliance.raw_rules)
    logger.info(f"Compliance rules transformed: {policy.compliance.transformed_rules}")

# Define the root agent
root_agent = LlmAgent(
    name="prime_safety_router",
    model="gemini-2.5-flash",
    instruction=ROUTER_INSTRUCTIONS,
    tools=BANKING_TOOLS,  # Add banking tools
    before_model_callback=fast_guardrail_callback,
    after_model_callback=after_model_callback,  # Log LLM responses
    generate_content_config=genai_types.GenerateContentConfig(
        temperature=0.7,  # More natural responses
        # Removed response_mime_type - let agent respond naturally
    )
)

logger.info(f"Agent '{root_agent.name}' initialized with model '{root_agent.model}' and {len(BANKING_TOOLS)} tools")

# TODO: Add post-processing callback to handle ESCALATE actions
# This would:
# 1. Parse agent response JSON
# 2. If action is "ESCALATE", log to escalation queue
