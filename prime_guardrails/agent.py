import logging
from google.adk import Agent

from .config import Config
from .prompt import ROUTER_INSTRUCTIONS
from .callbacks import fast_guardrail_callback
from .compliance import transform_rules

# Configure logging
logger = logging.getLogger(__name__)

# Initialize Config
configs = Config()

# Transform human-readable compliance rules at agent init
logger.info("Initializing PRIME agent...")
if configs.COMPLIANCE_ENABLED and configs.COMPLIANCE_RULES:
    logger.info(f"Transforming {len(configs.COMPLIANCE_RULES)} compliance rules...")
    # Get policy object and update its transformed rules
    policy = configs.current_policy
    policy.compliance.transformed_rules = transform_rules(configs.COMPLIANCE_RULES)
    logger.info(f"Compliance rules transformed: {policy.compliance.transformed_rules}")

# Define the root agent
root_agent = Agent(
    model=configs.agent_settings.model,
    instruction=ROUTER_INSTRUCTIONS,
    name=configs.agent_settings.name,
    tools=[],  # Layer 1 tools can be added here
    before_model_callback=fast_guardrail_callback,
)

logger.info(f"Agent '{configs.agent_settings.name}' initialized with model '{configs.agent_settings.model}'")

# TODO: Add post-processing callback to handle ESCALATE actions
# This would:
# 1. Parse agent response JSON
# 2. If action is "ESCALATE", log to escalation queue
# 3. Return appropriate user-facing message

