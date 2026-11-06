"""Unit tests for Safety Pillar (Image safety tool).

Note: Text safety checking is handled by unitary/toxic-bert via Detoxify
in scope/safety/text.py (TextSafetyTool); see test_text_safety.py.
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

    def test_failed_check_is_not_reported_safe(self, tmp_path):
        """An image that can't be checked yields an unknown result, never is_safe=True."""
        # Skip __init__ so no model is downloaded; the failure happens before the model runs.
        tool = ImageSafetyTool.__new__(ImageSafetyTool)

        result = tool.check(str(tmp_path / "missing.png"))

        assert result["is_safe"] is None
        assert result["nsfw_score"] is None
        assert result["checked"] is False
        assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
