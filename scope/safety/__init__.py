"""Safety module for PRIME guardrails.

This package contains safety checking tools for image content.

Note: Text safety checking is handled by unitary/toxic-bert via Detoxify
in scope/observability_tools.py (safety_check_layer1 function).
"""

from .tools import ImageSafetyTool

__all__ = ['ImageSafetyTool']
