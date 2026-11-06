"""Example configuration demonstrating compliance rules and escalation.

This file shows how to configure the SCOPE agent with custom compliance rules
for different use cases. Each dict holds `scope.config.Config` field values:

    from scope.config import Config
    config = Config(**HEALTHCARE_CONFIG)

The agent builds its own Config from GOOGLE_* env vars / .env, so to apply a
template to the running agent, put the matching lines (see the end of this
file) in .env.

COMPLIANCE_RULES are appended to the agent instruction as numbered
COMPLIANCE PRINCIPLES. ESCALATION_THRESHOLD is the Layer 2b confidence below
which the decision prompt instructs the decision model to escalate (higher
threshold = more escalations).
More starter rule sets live in scope/compliance/examples.py.
"""

# Example 1: Clothing Brand Configuration
CLOTHING_BRAND_CONFIG = {
    "COMPLIANCE_ENABLED": True,
    "COMPLIANCE_RULES": [
        "Don't discuss competitors",
        "Don't provide pricing without website link",
        "No internal product roadmaps"
    ],
    "ESCALATION_THRESHOLD": 0.6
}

# Example 2: Healthcare Service Configuration
HEALTHCARE_CONFIG = {
    "COMPLIANCE_ENABLED": True,
    "COMPLIANCE_RULES": [
        "No medical diagnoses",
        "Always suggest consulting professionals",
        "Never recommend specific medications"
    ],
    "ESCALATION_THRESHOLD": 0.8  # Higher threshold = more escalations
}

# Example 3: Financial Services Configuration
FINANCIAL_CONFIG = {
    "COMPLIANCE_ENABLED": True,
    "COMPLIANCE_RULES": [
        "Do not provide investment advice",
        "Include risk disclaimers for financial topics",
        "Never make market predictions"
    ],
    "ESCALATION_THRESHOLD": 0.7
}

# Or set the same values in your .env file (COMPLIANCE_RULES is a JSON list;
# wrap it in single quotes and avoid apostrophes inside the rules):
# GOOGLE_COMPLIANCE_ENABLED=true
# GOOGLE_COMPLIANCE_RULES='["Do not discuss competitors", "No pricing without website link"]'
# GOOGLE_ESCALATION_THRESHOLD=0.6
