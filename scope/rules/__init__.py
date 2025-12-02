"""Config package initialization."""

from .loader import (
    load_safety_rules,
    load_compliance_rules,
    SAFETY_CONFIG,
    COMPLIANCE_CONFIG,
    SAFETY_RULES_TEXT,
    COMPLIANCE_RULES_TEXT,
)

__all__ = [
    'load_safety_rules',
    'load_compliance_rules',
    'SAFETY_CONFIG',
    'COMPLIANCE_CONFIG',
    'SAFETY_RULES_TEXT',
    'COMPLIANCE_RULES_TEXT',
]
