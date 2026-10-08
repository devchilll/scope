"""Tests for the pre-model safety gate (before_model_callback).

These run with a fake classifier injected via ``set_text_tool`` so they are
fast and need no model download or LLM access.
"""

import pytest
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types as genai_types

from scope.callbacks import (
    fast_guardrail_callback,
    after_model_callback,
    extract_latest_user_text,
    BLOCKED_MESSAGE,
)
from scope.safety import TextSafetyTool, set_text_tool


class FakeModel:
    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def predict(self, text):
        self.calls.append(text)
        return self.scores


SAFE = {"toxicity": 0.02, "severe_toxicity": 0.0, "insult": 0.01}
TOXIC = {"toxicity": 0.95, "severe_toxicity": 0.2, "insult": 0.9}


def _request(*turns):
    """Build an LlmRequest from (role, text) tuples."""
    contents = [
        genai_types.Content(role=role, parts=[genai_types.Part(text=text)])
        for role, text in turns
    ]
    return LlmRequest(contents=contents)


@pytest.fixture(autouse=True)
def _reset_tool():
    yield
    set_text_tool(None)


@pytest.fixture
def ml_enabled(monkeypatch):
    monkeypatch.setenv("GOOGLE_SAFETY_USE_ML_MODELS", "true")


class TestExtractLatestUserText:
    def test_returns_last_user_turn_only(self):
        req = _request(("user", "first"), ("model", "reply"), ("user", "second"))
        assert extract_latest_user_text(req) == "second"

    def test_ignores_model_turns(self):
        req = _request(("user", "hello"), ("model", "you are stupid"))
        assert extract_latest_user_text(req) == "hello"

    def test_empty_request(self):
        assert extract_latest_user_text(LlmRequest(contents=[])) == ""


class TestFastGuardrailCallback:
    def test_safe_input_continues_to_model(self, ml_enabled):
        model = FakeModel(SAFE)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))

        result = fast_guardrail_callback(None, _request(("user", "What's my balance?")))

        assert result is None
        assert model.calls == ["What's my balance?"]

    def test_toxic_input_blocked_before_model(self, ml_enabled):
        model = FakeModel(TOXIC)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))

        result = fast_guardrail_callback(None, _request(("user", "You are stupid and I hate you.")))

        assert isinstance(result, LlmResponse)
        assert result.content.role == "model"
        assert result.content.parts[0].text == BLOCKED_MESSAGE

    def test_check_runs_on_every_request(self, ml_enabled):
        model = FakeModel(SAFE)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))

        fast_guardrail_callback(None, _request(("user", "one")))
        fast_guardrail_callback(None, _request(("user", "one"), ("model", "ok"), ("user", "two")))

        assert model.calls == ["one", "two"]

    def test_empty_input_skips_check(self, ml_enabled):
        model = FakeModel(TOXIC)
        set_text_tool(TextSafetyTool(model=model))

        assert fast_guardrail_callback(None, LlmRequest(contents=[])) is None
        assert model.calls == []

    def test_unavailable_model_fails_open(self, ml_enabled):
        tool = TextSafetyTool()
        tool._load_error = "no model"
        set_text_tool(tool)

        assert fast_guardrail_callback(None, _request(("user", "hi"))) is None

    def test_ml_disabled_by_config_skips_classifier(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_SAFETY_USE_ML_MODELS", "false")
        model = FakeModel(TOXIC)
        set_text_tool(TextSafetyTool(model=model))

        assert fast_guardrail_callback(None, _request(("user", "anything"))) is None
        assert model.calls == []


class TestAfterModelCallback:
    def test_returns_response_unchanged(self):
        resp = LlmResponse(
            content=genai_types.Content(role="model", parts=[genai_types.Part(text="hi")])
        )
        assert after_model_callback(None, resp) is resp
