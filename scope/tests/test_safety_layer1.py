"""Tests for the safety_check_layer1 tool's result strings and audit event.

A fake classifier is injected with ``set_text_tool`` and the audit logger is
mocked, so no toxic-bert download and no log files are needed. The
config-disabled path is covered in tests/test_callbacks.py.
"""

from unittest.mock import MagicMock

import pytest

import scope.observability_tools as obs
from scope.safety import TextSafetyTool, set_text_tool


SAFE = {"toxicity": 0.02, "severe_toxicity": 0.0, "insult": 0.01}
TOXIC = {"toxicity": 0.95, "severe_toxicity": 0.2, "insult": 0.1}


class FakeModel:
    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def predict(self, text):
        self.calls.append(text)
        return self.scores


@pytest.fixture(autouse=True)
def audit(monkeypatch):
    monkeypatch.setenv("GOOGLE_SAFETY_USE_ML_MODELS", "true")
    logger = MagicMock()
    monkeypatch.setattr(obs, "audit_logger", logger)
    yield logger
    set_text_tool(None)


def _logged_details(audit):
    audit.log_event.assert_called_once()
    kwargs = audit.log_event.call_args.kwargs
    assert kwargs["action"] == "safety_layer1_check"
    return kwargs


def test_safe_input_passes(audit):
    model = FakeModel(SAFE)
    set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))

    result = obs.safety_check_layer1("Hello, I would like to check my account balance.")

    assert result.startswith("✅ Layer 2a (ML) Safety Check PASSED")
    assert "Toxicity: 0.02" in result
    assert model.calls == ["Hello, I would like to check my account balance."]
    kwargs = _logged_details(audit)
    assert kwargs["success"] is True
    assert kwargs["details"]["checked"] is True
    assert kwargs["details"]["is_safe"] is True


def test_toxic_input_fails(audit):
    set_text_tool(TextSafetyTool(threshold_high=0.8, model=FakeModel(TOXIC)))

    result = obs.safety_check_layer1("You are stupid and I hate you.")

    assert "Layer 2a (ML) Safety Check FAILED" in result
    assert "Category: toxicity" in result
    assert "Request blocked" in result
    details = _logged_details(audit)["details"]
    assert details["is_safe"] is False
    assert details["risk_category"] == "toxicity"


def test_model_unavailable_is_skipped_not_passed(audit):
    tool = TextSafetyTool()
    tool._load_error = "OSError: model download failed"  # model never loads
    set_text_tool(tool)

    result = obs.safety_check_layer1("hello")

    assert "SKIPPED (model not loaded)" in result
    assert "PASSED" not in result
    kwargs = _logged_details(audit)
    assert kwargs["success"] is False
    assert kwargs["error"] == "OSError: model download failed"
    assert kwargs["details"]["checked"] is False
