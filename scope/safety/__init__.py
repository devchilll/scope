"""Safety module for SCOPE guardrails (Layer 2a: fast ML checks).

- ``TextSafetyTool`` / ``get_text_tool``: unitary/toxic-bert text classifier.
  Used by the ``before_model_callback`` to screen every user turn *before*
  the LLM runs, and by the ``safety_check_layer1`` tool for trace visibility.
- ``ImageSafetyTool``: NSFW image classifier.
"""

from .tools import ImageSafetyTool
from .text import TextSafetyTool, get_text_tool, set_text_tool, MODEL_NAME

__all__ = [
    'ImageSafetyTool',
    'TextSafetyTool',
    'get_text_tool',
    'set_text_tool',
    'MODEL_NAME',
]
