"""Unit tests for the Layer 2a text safety classifier wrapper.

Uses an injected fake model so no network / model download is required.
"""

import pytest

from scope.safety.text import TextSafetyTool, MODEL_NAME


class FakeModel:
    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def predict(self, text):
        self.calls.append(text)
        return self.scores


SAFE = {"toxicity": 0.01, "severe_toxicity": 0.0, "obscene": 0.0,
        "threat": 0.0, "insult": 0.01, "identity_attack": 0.0}
TOXIC = {"toxicity": 0.97, "severe_toxicity": 0.1, "obscene": 0.2,
         "threat": 0.05, "insult": 0.92, "identity_attack": 0.01}


class TestTextSafetyTool:
    def test_safe_input_passes(self):
        tool = TextSafetyTool(threshold_high=0.8, model=FakeModel(SAFE))
        result = tool.check("What's my account balance?")
        assert result["checked"] is True
        assert result["is_safe"] is True
        assert result["risk_category"] == "none"
        assert result["model"] == MODEL_NAME

    def test_toxic_input_blocked(self):
        tool = TextSafetyTool(threshold_high=0.8, model=FakeModel(TOXIC))
        result = tool.check("You are stupid and I hate you.")
        assert result["checked"] is True
        assert result["is_safe"] is False
        assert result["risk_category"] == "insult"
        assert result["confidence"] == pytest.approx(0.92)

    def test_severe_toxicity_uses_lower_threshold(self):
        scores = dict(SAFE, severe_toxicity=0.6)
        tool = TextSafetyTool(threshold_high=0.8, threshold_severe=0.5,
                              model=FakeModel(scores))
        result = tool.check("...")
        assert result["is_safe"] is False
        assert result["risk_category"] == "severe_toxicity"

    def test_threshold_is_respected(self):
        scores = dict(SAFE, toxicity=0.7)
        assert TextSafetyTool(threshold_high=0.8, model=FakeModel(scores)).check("x")["is_safe"]
        assert not TextSafetyTool(threshold_high=0.6, model=FakeModel(scores)).check("x")["is_safe"]

    def test_empty_input_is_safe_without_calling_model(self):
        model = FakeModel(TOXIC)
        tool = TextSafetyTool(model=model)
        result = tool.check("   ")
        assert result["is_safe"] is True
        assert model.calls == []

    def test_unavailable_model_reports_unchecked(self):
        tool = TextSafetyTool()
        tool._load_error = "boom"  # simulate failed load
        result = tool.check("hello")
        assert result["checked"] is False
        assert result["is_safe"] is True
        assert result["error"] == "boom"
        assert tool.available is False
