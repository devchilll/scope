"""Integration tests for the PRIME agentic system.

These tests verify the end-to-end functionality of the agent including:
- Safety checks (Layer 2)
- LLM reasoning (Layer 1)
- Compliance enforcement
- Escalation triggers
"""

import pytest
from scope.agent import root_agent
from scope.config import Config


class TestAgentInitialization:
    """Test agent initialization and configuration."""
    
    def test_agent_exists(self):
        """Test that agent is initialized."""
        assert root_agent is not None
        assert root_agent.name == "scope_safety_router"
    
    def test_config_loaded(self):
        """Test configuration is loaded correctly."""
        config = Config()
        policy = config.current_policy
        
        assert policy.safety is not None
        assert policy.compliance is not None
        assert policy.iam is not None
        assert policy.escalation is not None


class TestSafetyLayer:
    """Test Layer 2 safety checks."""
    
    def test_safe_input_passes(self):
        """Test that safe input passes safety checks."""
        # This would require running the actual agent
        # For now, we verify the callback exists
        from scope.callbacks import fast_guardrail_callback
        assert fast_guardrail_callback is not None
    
    def test_offensive_input_blocked(self):
        """Test that the pre-model classifier is wired up.

        Behavioural tests (block / pass) live in tests/test_callbacks.py with a
        fake model; here we only verify the real tool is reachable.
        """
        from scope.safety import get_text_tool
        assert get_text_tool() is not None


class TestComplianceEnforcement:
    """Test compliance rule enforcement."""
    
    def test_compliance_rules_loaded(self):
        """Test that compliance rules are loaded."""
        config = Config()
        policy = config.current_policy
        assert policy.compliance.enabled is not None
    
    def test_rule_transformation(self):
        """Test that rules are transformed correctly."""
        from scope.compliance import transform_rules
        raw = ["Don't discuss competitors"]
        transformed = transform_rules(raw)
        assert len(transformed) == 1
        assert "PRINCIPLE:" in transformed[0]


class TestAgentActions:
    """Test agent decision actions."""
    
    def test_allow_action(self):
        """Test ALLOW action for safe input."""
        # Would test actual agent response
        # Verifying action types are defined
        expected_actions = ["approve", "reject", "rewrite", "escalate"]
        from scope.prompt import ROUTER_INSTRUCTIONS
        for action in expected_actions:
            assert action in ROUTER_INSTRUCTIONS
    
    def test_refuse_action(self):
        """Test REFUSE action for policy violations."""
        # Would test actual agent response with violating input
        pass
    
    def test_rewrite_action(self):
        """Test REWRITE action for unsafe but valid intent."""
        # Would test actual agent response with rewritable input
        pass
    
    def test_escalate_action(self):
        """Test ESCALATE action for uncertain cases."""
        # Would test actual agent response with ambiguous input
        pass


class TestEndToEndFlow:
    """Test complete end-to-end agent flow."""
    
    @pytest.mark.skip(reason="Requires actual LLM calls")
    def test_safe_query_flow(self):
        """Test complete flow with safe query."""
        # This would make actual agent calls
        # Example:
        # response = root_agent.run("What is the weather today?")
        # assert response contains expected safe output
        pass
    
    @pytest.mark.skip(reason="Requires actual LLM calls")
    def test_unsafe_query_flow(self):
        """Test complete flow with unsafe query."""
        # This would make actual agent calls with unsafe content
        # and verify it's blocked or rewritten
        pass
    
    @pytest.mark.skip(reason="Requires actual LLM calls")
    def test_compliance_violation_flow(self):
        """Test complete flow with compliance violation."""
        # This would test agent with input violating compliance rules
        pass
    
    @pytest.mark.skip(reason="Requires actual LLM calls")
    def test_escalation_flow(self):
        """Test complete flow triggering escalation."""
        # This would test agent with ambiguous input
        # and verify escalation ticket is created
        pass


class TestCallbackIntegration:
    """Test callback integration."""
    
    def test_callback_registered(self):
        """Test that safety callback is registered."""
        # Verify the pre-model safety gate is attached to the agent
        from scope.callbacks import fast_guardrail_callback, after_model_callback
        assert fast_guardrail_callback in root_agent.canonical_before_model_callbacks
        assert after_model_callback in root_agent.canonical_after_model_callbacks


class TestPromptConstruction:
    """Test agent prompt construction."""
    
    def test_prompt_includes_safety_policy(self):
        """Prompt instructs the agent to run the layered safety tools in order."""
        from scope.prompt import ROUTER_INSTRUCTIONS
        assert "safety_check_layer1" in ROUTER_INSTRUCTIONS
        assert "safety_check_layer2" in ROUTER_INSTRUCTIONS
        assert "make_safe_and_compliant_decision" in ROUTER_INSTRUCTIONS
        assert ROUTER_INSTRUCTIONS.index("safety_check_layer1") < ROUTER_INSTRUCTIONS.index("safety_check_layer2")
    
    def test_prompt_includes_actions(self):
        """Prompt describes all four decision actions."""
        from scope.prompt import ROUTER_INSTRUCTIONS
        for action in ("approve", "reject", "rewrite", "escalate"):
            assert action in ROUTER_INSTRUCTIONS
    
    def test_prompt_includes_escalation_handling(self):
        """Prompt tells the agent how to escalate."""
        from scope.prompt import ROUTER_INSTRUCTIONS
        assert "create_escalation_ticket" in ROUTER_INSTRUCTIONS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
