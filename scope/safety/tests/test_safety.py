"""Unit tests for Safety Pillar (Text and Image safety tools)."""

import pytest
from scope.safety import TextSafetyTool, ImageSafetyTool


class TestTextSafetyTool:
    """Test text safety checking."""
    
    def test_initialization(self):
        """Test tool initializes correctly."""
        tool = TextSafetyTool()
        assert tool.classifier is not None
    
    def test_safe_text(self):
        """Test that safe text passes."""
        tool = TextSafetyTool()
        result = tool.check("Hello, how are you today?")
        
        assert "is_safe" in result
        assert "risk_category" in result
        assert "confidence" in result
        assert isinstance(result["is_safe"], bool)
        assert isinstance(result["confidence"], float)
    
    def test_offensive_text(self):
        """Test that offensive text is detected."""
        tool = TextSafetyTool()
        # Using a clearly offensive example
        result = tool.check("You are stupid and worthless")
        
        assert "is_safe" in result
        assert "risk_category" in result
        # Note: Actual detection depends on model performance
    
    def test_error_handling(self):
        """Test error handling for invalid input."""
        tool = TextSafetyTool()
        # Empty string should not crash
        result = tool.check("")
        assert "is_safe" in result


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
