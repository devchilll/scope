"""Example configuration demonstrating compliance rules and escalation.

This file shows how to configure the PRIME agent with custom compliance rules
for different use cases.
"""

# Example 1: Clothing Brand Configuration
CLOTHING_BRAND_CONFIG = {
    "COMPLIANCE_ENABLED": True,
    "COMPLIANCE_RULES": [
        "Don't discuss competitors",
        "Don't provide pricing without website link",
        "No internal product roadmaps"
    ],
    "ESCALATION_ENABLED": True,
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
    "ESCALATION_ENABLED": True,
    "ESCALATION_THRESHOLD": 0.5  # Lower threshold = more escalations
}

# Example 3: Financial Services Configuration
FINANCIAL_CONFIG = {
    "COMPLIANCE_ENABLED": True,
    "COMPLIANCE_RULES": [
        "Do not provide investment advice",
        "Include risk disclaimers for financial topics",
        "Never make market predictions"
    ],
    "ESCALATION_ENABLED": True,
    "ESCALATION_THRESHOLD": 0.7
}

# To use these, add them to your .env file:
# GOOGLE_COMPLIANCE_ENABLED=true
# GOOGLE_COMPLIANCE_RULES='["Don't discuss competitors", "No pricing without link"]'
# GOOGLE_ESCALATION_ENABLED=true
# GOOGLE_ESCALATION_THRESHOLD=0.6
