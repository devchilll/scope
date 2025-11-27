"""Unit tests for Compliance Pillar (Rule transformation and formatting)."""

import pytest
from prime_guardrails.compliance import transform_rules, format_compliance_section


class TestRuleTransformation:
    """Test compliance rule transformation."""
    
    def test_transform_single_rule(self):
        """Test transforming a single rule."""
        raw = ["Don't discuss competitors"]
        transformed = transform_rules(raw)
        
        assert len(transformed) == 1
        assert "PRINCIPLE:" in transformed[0]
        assert "Don't discuss competitors" in transformed[0]
    
    def test_transform_multiple_rules(self):
        """Test transforming multiple rules."""
        raw = [
            "Don't discuss competitors",
            "No pricing without website link",
            "No internal roadmaps"
        ]
        transformed = transform_rules(raw)
        
        assert len(transformed) == 3
        for rule in transformed:
            assert "PRINCIPLE:" in rule
    
    def test_transform_empty_list(self):
        """Test transforming empty rule list."""
        transformed = transform_rules([])
        assert transformed == []
    
    def test_format_compliance_section(self):
        """Test formatting rules for agent prompt."""
        rules = [
            "PRINCIPLE: Don't discuss competitors",
            "PRINCIPLE: No pricing without link"
        ]
        formatted = format_compliance_section(rules)
        
        assert "COMPLIANCE PRINCIPLES:" in formatted
        assert "1." in formatted
        assert "2." in formatted
        assert "REFUSE" in formatted
    
    def test_format_empty_section(self):
        """Test formatting empty rule section."""
        formatted = format_compliance_section([])
        assert formatted == ""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
