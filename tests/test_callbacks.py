"""Tests for the pre-model safety gate (before_model_callback).

These run with a fake classifier injected via ``set_text_tool`` so they are
fast and need no model download or LLM access.
"""

import asyncio
from typing import AsyncGenerator

import pytest
from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import scope.callbacks as callbacks
from scope.callbacks import (
    fast_guardrail_callback,
    after_model_callback,
    extract_latest_user_text,
    redact_blocked_inputs,
    BLOCKED_MESSAGE,
    BLOCKED_INPUTS_STATE_KEY,
    GATE_SPAN_NAME,
    WITHHELD_MESSAGE,
)
from scope.safety import TextSafetyTool, set_text_tool


class FakeModel:
    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def predict(self, text):
        self.calls.append(text)
        return self.scores


class KeywordModel:
    """Fake classifier: TOXIC when the text contains ``stupid``, else SAFE."""

    def __init__(self):
        self.calls = []

    def predict(self, text):
        self.calls.append(text)
        return TOXIC if "stupid" in text else SAFE


SAFE = {"toxicity": 0.02, "severe_toxicity": 0.0, "insult": 0.01}
TOXIC = {"toxicity": 0.95, "severe_toxicity": 0.2, "insult": 0.9}


class RecordingAudit:
    """Stands in for the AuditLogger so tests never write real log files."""

    def __init__(self):
        self.actions = []

    def log_event(self, **kwargs):
        self.actions.append(kwargs["action"])

    def log_safety_block(self, **kwargs):
        self.actions.append("safety_block")


class FakeContext:
    """Minimal CallbackContext: session state + invocation id."""

    def __init__(self, invocation_id="inv-1", state=None):
        self.invocation_id = invocation_id
        self.state = {} if state is None else state


def _request(*turns):
    """Build an LlmRequest from (role, text) tuples."""
    contents = [
        genai_types.Content(role=role, parts=[genai_types.Part(text=text)])
        for role, text in turns
    ]
    return LlmRequest(contents=contents)


def _tool_loop_request(user_text):
    """Request for the 2nd model call of a turn: user text, tool call, tool result."""
    return LlmRequest(contents=[
        genai_types.Content(role="user", parts=[genai_types.Part(text=user_text)]),
        genai_types.Content(role="model", parts=[
            genai_types.Part.from_function_call(name="get_balance", args={}),
        ]),
        genai_types.Content(role="user", parts=[
            genai_types.Part.from_function_response(name="get_balance", response={"balance": 100}),
        ]),
    ])


@pytest.fixture(autouse=True)
def _reset_tool():
    yield
    set_text_tool(None)


@pytest.fixture(autouse=True)
def audit(monkeypatch):
    recorder = RecordingAudit()
    monkeypatch.setattr(callbacks, "get_audit_logger", lambda: recorder)
    return recorder


@pytest.fixture
def ml_enabled(monkeypatch):
    monkeypatch.setenv("GOOGLE_SAFETY_USE_ML_MODELS", "true")


@pytest.fixture
def spans(monkeypatch):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(callbacks, "tracer", provider.get_tracer("test"))
    return exporter


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


class TestOncePerInvocation:
    def test_tool_loop_screens_and_logs_once(self, ml_enabled, audit):
        model = FakeModel(SAFE)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        ctx = FakeContext("inv-1")

        assert fast_guardrail_callback(ctx, _request(("user", "What's my balance?"))) is None
        assert fast_guardrail_callback(ctx, _tool_loop_request("What's my balance?")) is None
        assert fast_guardrail_callback(ctx, _tool_loop_request("What's my balance?")) is None

        assert model.calls == ["What's my balance?"]
        assert audit.actions == ["user_input", "safety_check"]

    def test_new_invocation_is_screened_again(self, ml_enabled):
        model = FakeModel(SAFE)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        state = {}

        fast_guardrail_callback(FakeContext("inv-1", state), _request(("user", "hi")))
        fast_guardrail_callback(
            FakeContext("inv-2", state),
            _request(("user", "hi"), ("model", "hello"), ("user", "hi")),
        )

        assert model.calls == ["hi", "hi"]

    def test_block_applies_to_every_model_call_of_the_invocation(self, ml_enabled):
        model = FakeModel(TOXIC)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        ctx = FakeContext("inv-1")

        first = fast_guardrail_callback(ctx, _request(("user", "you are stupid")))
        again = fast_guardrail_callback(ctx, _tool_loop_request("you are stupid"))

        assert first.content.parts[0].text == BLOCKED_MESSAGE
        assert again.content.parts[0].text == BLOCKED_MESSAGE
        assert model.calls == ["you are stupid"]


class TestBlockedInputRedaction:
    def test_blocked_text_recorded_as_hash_only(self, ml_enabled):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=KeywordModel()))
        ctx = FakeContext("inv-1")

        fast_guardrail_callback(ctx, _request(("user", "you are stupid")))

        stored = ctx.state[BLOCKED_INPUTS_STATE_KEY]
        assert len(stored) == 1
        assert "stupid" not in str(ctx.state)

    def test_blocked_turn_withheld_from_later_requests(self, ml_enabled):
        model = KeywordModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        state = {}

        fast_guardrail_callback(FakeContext("inv-1", state), _request(("user", "you are stupid")))
        req = _request(
            ("user", "you are stupid"),
            ("model", BLOCKED_MESSAGE),
            ("user", "What's my balance?"),
        )
        result = fast_guardrail_callback(FakeContext("inv-2", state), req)

        assert result is None
        assert [c.role for c in req.contents] == ["user", "model", "user"]
        assert req.contents[0].parts[0].text == WITHHELD_MESSAGE
        assert req.contents[2].parts[0].text == "What's my balance?"
        assert all("stupid" not in (p.text or "") for c in req.contents for p in c.parts)
        # Only the new turn is screened.
        assert model.calls == ["you are stupid", "What's my balance?"]

    def test_redaction_also_applies_in_tool_loop(self, ml_enabled):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=KeywordModel()))
        state = {}
        fast_guardrail_callback(FakeContext("inv-1", state), _request(("user", "you are stupid")))

        ctx = FakeContext("inv-2", state)
        fast_guardrail_callback(ctx, _request(("user", "you are stupid"), ("model", "no"), ("user", "hi")))
        req = _tool_loop_request("hi")
        req.contents[:0] = _request(("user", "you are stupid"), ("model", "no")).contents
        assert fast_guardrail_callback(ctx, req) is None

        assert req.contents[0].parts[0].text == WITHHELD_MESSAGE

    def test_redact_ignores_model_turns_and_unblocked_text(self):
        req = _request(("user", "hello"), ("model", "hello"))
        assert redact_blocked_inputs(req, []) == 0
        assert redact_blocked_inputs(req, [callbacks._text_hash("hello")]) == 1
        assert req.contents[0].parts[0].text == WITHHELD_MESSAGE
        assert req.contents[1].parts[0].text == "hello"


class TestGateSpan:
    def test_allowed_request_span(self, ml_enabled, spans):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=FakeModel(SAFE)))

        fast_guardrail_callback(FakeContext(), _request(("user", "hi")))

        (span,) = spans.get_finished_spans()
        assert span.name == GATE_SPAN_NAME
        assert span.attributes["scope.safety.blocked"] is False
        assert span.attributes["scope.safety.outcome"] == "allowed"
        assert span.attributes["scope.safety.max_score"] == pytest.approx(0.02)

    def test_blocked_request_span(self, ml_enabled, spans):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=FakeModel(TOXIC)))

        fast_guardrail_callback(FakeContext(), _request(("user", "you are stupid")))

        (span,) = spans.get_finished_spans()
        assert span.attributes["scope.safety.blocked"] is True
        assert span.attributes["scope.safety.risk_category"] == "insult"
        assert span.attributes["scope.safety.max_score"] == pytest.approx(0.95)

    def test_one_span_per_invocation(self, ml_enabled, spans):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=FakeModel(SAFE)))
        ctx = FakeContext("inv-1")

        fast_guardrail_callback(ctx, _request(("user", "hi")))
        fast_guardrail_callback(ctx, _tool_loop_request("hi"))

        assert len(spans.get_finished_spans()) == 1


class TestSafetyCheckLayer1Tool:
    """The trace-visibility tool re-runs the 2a check and honours the config flag."""

    @pytest.fixture(autouse=True)
    def _tool_audit(self, monkeypatch, audit):
        import scope.observability_tools as obs
        monkeypatch.setattr(obs, "audit_logger", audit)
        return obs

    def test_disabled_by_config_skips_classifier(self, monkeypatch, _tool_audit):
        monkeypatch.setenv("GOOGLE_SAFETY_USE_ML_MODELS", "false")
        model = FakeModel(TOXIC)
        set_text_tool(TextSafetyTool(model=model))

        result = _tool_audit.safety_check_layer1("you are stupid")

        assert "SKIPPED" in result and "SAFETY_USE_ML_MODELS=false" in result
        assert model.calls == []

    def test_enabled_runs_classifier(self, ml_enabled, _tool_audit):
        model = FakeModel(TOXIC)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))

        result = _tool_audit.safety_check_layer1("you are stupid")

        assert "Layer 2a (ML) Safety Check FAILED" in result
        assert model.calls == ["you are stupid"]


def get_balance() -> dict:
    """Return the balance."""
    return {"balance": 100}


class RecordingLlm(BaseLlm):
    """Fake Gemini: calls ``get_balance`` once, then answers. Records requests."""

    model: str = "fake-llm"
    requests: list = []

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request.model_copy(deep=True))
        last = llm_request.contents[-1]
        if any(p.function_response for p in last.parts):
            part = genai_types.Part(text="Your balance is 100.")
        else:
            part = genai_types.Part.from_function_call(name="get_balance", args={})
        yield LlmResponse(content=genai_types.Content(role="model", parts=[part]))


class TestWithAdkRunner:
    """End-to-end through ADK's real flow (sessions, state, tool loop)."""

    def _run(self, runner, session_id, text):
        async def go():
            events = []
            async for event in runner.run_async(
                user_id="u",
                session_id=session_id,
                new_message=genai_types.Content(role="user", parts=[genai_types.Part(text=text)]),
            ):
                events.append(event)
            return events

        return asyncio.run(go())

    def test_blocked_text_never_reaches_model(self, ml_enabled, audit):
        classifier = KeywordModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=classifier))
        llm = RecordingLlm(requests=[])
        agent = LlmAgent(
            name="gate_test",
            model=llm,
            tools=[get_balance],
            before_model_callback=fast_guardrail_callback,
        )
        runner = InMemoryRunner(agent=agent, app_name="gate_test")
        session = asyncio.run(
            runner.session_service.create_session(app_name="gate_test", user_id="u")
        )

        blocked_events = self._run(runner, session.id, "you are stupid")
        assert llm.requests == []
        assert blocked_events[-1].content.parts[0].text == BLOCKED_MESSAGE

        self._run(runner, session.id, "What's my balance?")

        # Two model calls (tool call + answer), one classifier run per turn.
        assert len(llm.requests) == 2
        assert classifier.calls == ["you are stupid", "What's my balance?"]
        assert audit.actions.count("user_input") == 2
        for request in llm.requests:
            texts = [p.text for c in request.contents for p in c.parts if p.text]
            assert not any("stupid" in t for t in texts)
            assert WITHHELD_MESSAGE in texts


class TestAfterModelCallback:
    def test_returns_response_unchanged(self):
        resp = LlmResponse(
            content=genai_types.Content(role="model", parts=[genai_types.Part(text="hi")])
        )
        assert after_model_callback(None, resp) is resp
