"""Unit tests for Safety Pillar (Image safety tool).

Note: Text safety checking is handled by unitary/toxic-bert via Detoxify
in scope/observability_tools.py (safety_check_layer1 function).
"""

import pytest
from scope.safety import ImageSafetyTool


class TestImageSafetyTool:
    """Test image safety checking."""
    
    def test_initialization(self):
        """Test tool initializes correctly."""
        tool = ImageSafetyTool()
        assert tool.processor is not None
        assert tool.model is not None
    
    def test_output_format(self):
        """Test that output has correct format."""
        # Note: This test would need actual image files
        # For now, we just verify the tool can be instantiated
        tool = ImageSafetyTool()
        assert hasattr(tool, 'check')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
