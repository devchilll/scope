"""Integration tests for the SCOPE agentic system.

These tests check how the agent is wired together:
- Agent construction and callback registration
- Config, compliance rules and prompt contents
- The decision step's actions and fail-safe, with a mocked Gemini client

No test here calls an LLM.
"""

import json
from unittest.mock import MagicMock

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
        assert policy.escalation is not None


class TestSafetyLayer:
    """Test the safety layers (2a ML gate, 2b LLM contextual safety)."""
    
    def test_safety_callback_importable(self):
        """The pre-model safety callback can be imported.

        Behavioural tests (block / pass) live in tests/test_callbacks.py with a
        fake model.
        """
        from scope.callbacks import fast_guardrail_callback
        assert fast_guardrail_callback is not None
    
    def test_text_safety_tool_available(self):
        """The shared text classifier object can be created (model loads lazily)."""
        from scope.safety import get_text_tool
        assert get_text_tool() is not None


class TestComplianceEnforcement:
    """Test compliance rule enforcement."""
    
    def test_compliance_rules_loaded(self):
        """compliance_rules.yaml is loaded: rules COMP-001..COMP-007 and the
        COMP-004 high-value threshold, and every rule ID appears in the
        formatted rules text and in the agent instruction."""
        from scope.prompt import build_instruction
        from scope.rules import COMPLIANCE_CONFIG, COMPLIANCE_RULES_TEXT

        expected_ids = [f"COMP-00{i}" for i in range(1, 8)]
        assert [rule["id"] for rule in COMPLIANCE_CONFIG["compliance_rules"]] == expected_ids
        assert float(COMPLIANCE_CONFIG["thresholds"]["high_value_amount"]) > 0
        instruction = build_instruction()
        for rule_id in expected_ids:
            assert f"**{rule_id}**" in COMPLIANCE_RULES_TEXT
            assert f"**{rule_id}**" in instruction
    
    def test_rule_transformation(self):
        """Test that rules are transformed correctly."""
        from scope.compliance import transform_rules
        raw = ["Don't discuss competitors"]
        transformed = transform_rules(raw)
        assert len(transformed) == 1
        assert "PRINCIPLE:" in transformed[0]


class TestDecisionActions:
    """The decision step (make_safe_and_compliant_decision) with a mocked Gemini client."""

    @pytest.fixture
    def decide(self, monkeypatch):
        """Run the decision tool against a fake client; returns (decision, prompt)."""
        import scope.observability_tools as obs
        client = MagicMock()
        monkeypatch.setattr(obs, "genai_client", client)
        monkeypatch.setattr(obs, "audit_logger", MagicMock())

        def _decide(model_reply=None, error=None):
            if error is not None:
                client.models.generate_content.side_effect = error
            else:
                client.models.generate_content.return_value.text = json.dumps(model_reply)
            decision = json.loads(obs.make_safe_and_compliant_decision({"safety_score": 0.5}))
            prompt = client.models.generate_content.call_args.kwargs["contents"]
            return decision, prompt

        return _decide

    def test_decision_prompt_defines_all_actions(self, decide):
        """The decision prompt defines approve, reject, rewrite and escalate."""
        _, prompt = decide({"action": "approve", "params": {}, "reasoning": "ok"})
        for action in ("approve", "reject", "rewrite", "escalate"):
            assert f"- **{action}**:" in prompt

    def test_comp001_requires_rewrite(self, decide):
        """COMP-001 (full account number request) must be rewritten, not rejected."""
        _, prompt = decide({"action": "approve", "params": {}, "reasoning": "ok"})
        assert 'If violated_rules contains "COMP-001"' in prompt
        assert 'you MUST choose "rewrite" action, NOT reject' in prompt

    @pytest.mark.parametrize("reply", [
        {"action": "reject", "params": {}, "reasoning": "prompt injection"},
        {"action": "rewrite", "params": {"rewritten_text": "Show the last 4 digits"}, "reasoning": "COMP-001"},
        {"action": "escalate", "params": {}, "reasoning": "ambiguous"},
    ])
    def test_model_decision_returned(self, decide, reply):
        """The model's verdict is returned to the agent unchanged."""
        decision, _ = decide(reply)
        assert decision == reply

    def test_decision_error_escalates(self, decide):
        """If the decision call fails, the tool fails safe to escalate."""
        decision, _ = decide(error=RuntimeError("quota exceeded"))
        assert decision["action"] == "escalate"
        assert "quota exceeded" in decision["reasoning"]


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
