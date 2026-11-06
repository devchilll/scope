"""Tests for the pre-model safety gate (before_model_callback).

These run with a fake classifier injected via ``set_text_tool`` so they are
fast and need no model download or LLM access.
"""

import asyncio
import threading
from types import SimpleNamespace
from typing import AsyncGenerator

import pytest
from google.adk.agents import LlmAgent
from google.adk.models import BaseLlm, LlmRequest, LlmResponse
from google.adk.events import Event, EventActions
from google.adk.runners import InMemoryRunner
from google.genai import types as genai_types
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

import scope.callbacks as callbacks
from scope.callbacks import (
    fast_guardrail_callback,
    after_model_callback,
    clear_screened_cache,
    extract_latest_user_text,
    redact_blocked_inputs,
    blocked_input_hashes,
    BLOCKED_MESSAGE,
    BLOCKED_EVENT_METADATA_KEY,
    BLOCKED_HASH_METADATA_KEY,
    BLOCKED_INPUTS_STATE_KEY,
    GATE_DECISION_STATE_KEY,
    GATE_SPAN_NAME,
    HISTORY_CHECK_ACTION,
    TOO_LONG_MESSAGE,
    WITHHELD_MESSAGE,
)
from scope.safety import TextSafetyTool, set_text_tool
from scope.safety.text import MAX_CHARS


class BatchModel:
    """Fake classifier with Detoxify's batch interface.

    ``predict(list)`` returns ``{label: [score per text]}``; subclasses score
    one text in ``_score``. Records every text classified (``calls``) and the
    thread each ``predict`` ran on (``threads``).
    """

    def __init__(self):
        self.calls = []
        self.threads = []

    def predict(self, texts):
        self.threads.append(threading.get_ident())
        self.calls.extend(texts)
        scored = [self._score(t) for t in texts]
        labels = {label for s in scored for label in s}
        return {label: [s.get(label, 0.0) for s in scored] for label in labels}


class FakeModel(BatchModel):
    def __init__(self, scores):
        super().__init__()
        self.scores = scores

    def _score(self, text):
        return self.scores


class KeywordModel(BatchModel):
    """Fake classifier: TOXIC when the text contains ``stupid``, else SAFE."""

    def _score(self, text):
        return TOXIC if "stupid" in text else SAFE


class StrictKeywordModel(KeywordModel):
    """Like ``KeywordModel``, but rejects text that is not valid UTF-8 (a
    lone surrogate), as Detoxify's Rust tokenizer does."""

    def _score(self, text):
        text.encode("utf-8")  # UnicodeEncodeError on a lone surrogate
        return super()._score(text)


SAFE = {"toxicity": 0.02, "severe_toxicity": 0.0, "insult": 0.01}
TOXIC = {"toxicity": 0.95, "severe_toxicity": 0.2, "insult": 0.9}


class RecordingAudit:
    """Stands in for the AuditLogger so tests never write real log files."""

    def __init__(self):
        self.actions = []
        self.events = []

    def log_event(self, **kwargs):
        self.actions.append(kwargs["action"])
        self.events.append(kwargs)

    def log_safety_block(self, **kwargs):
        self.actions.append("safety_block")
        self.events.append(dict(kwargs, action="safety_block"))


class RaisingModel:
    """Fake classifier whose ``predict`` raises (e.g. a runtime error in torch)."""

    def __init__(self):
        self.calls = []

    def predict(self, texts):
        self.calls.extend(texts)
        raise RuntimeError("classifier crashed")


class FakeContext:
    """Minimal CallbackContext: session state, invocation id, optional events."""

    def __init__(self, invocation_id="inv-1", state=None, events=None, user_content=None):
        self.invocation_id = invocation_id
        self.state = {} if state is None else state
        self.session = SimpleNamespace(events=list(events or []))
        self.user_content = user_content


def _gate(ctx, req):
    """Run the (async) gate once, as ADK does before a model call."""
    return asyncio.run(fast_guardrail_callback(ctx, req))


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
    clear_screened_cache()
    yield
    set_text_tool(None)
    clear_screened_cache()


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

        result = _gate(None, _request(("user", "What's my balance?")))

        assert result is None
        assert model.calls == ["What's my balance?"]

    def test_toxic_input_blocked_before_model(self, ml_enabled):
        model = FakeModel(TOXIC)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))

        result = _gate(None, _request(("user", "You are stupid and I hate you.")))

        assert isinstance(result, LlmResponse)
        assert result.content.role == "model"
        assert result.content.parts[0].text == BLOCKED_MESSAGE

    def test_check_runs_on_every_request(self, ml_enabled):
        model = FakeModel(SAFE)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))

        _gate(None, _request(("user", "one")))
        _gate(None, _request(("user", "one"), ("model", "ok"), ("user", "two")))

        # The new message each time, then the model reply this process had not
        # classified yet; "one" is not classified again.
        assert model.calls == ["one", "two", "ok"]

    def test_empty_input_skips_check(self, ml_enabled):
        model = FakeModel(TOXIC)
        set_text_tool(TextSafetyTool(model=model))

        assert _gate(None, LlmRequest(contents=[])) is None
        assert model.calls == []

    def test_unavailable_model_fails_open(self, ml_enabled):
        tool = TextSafetyTool()
        tool._load_error = "no model"
        set_text_tool(tool)

        assert _gate(None, _request(("user", "hi"))) is None

    def test_ml_disabled_by_config_skips_classifier(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_SAFETY_USE_ML_MODELS", "false")
        model = FakeModel(TOXIC)
        set_text_tool(TextSafetyTool(model=model))

        assert _gate(None, _request(("user", "anything"))) is None
        assert model.calls == []


class TestOncePerInvocation:
    def test_tool_loop_screens_and_logs_once(self, ml_enabled, audit):
        model = FakeModel(SAFE)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        ctx = FakeContext("inv-1")

        assert _gate(ctx, _request(("user", "What's my balance?"))) is None
        assert _gate(ctx, _tool_loop_request("What's my balance?")) is None
        assert _gate(ctx, _tool_loop_request("What's my balance?")) is None

        assert model.calls == ["What's my balance?"]
        assert audit.actions == ["user_input", "safety_check"]

    def test_new_invocation_is_screened_again(self, ml_enabled):
        model = FakeModel(SAFE)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        state = {}

        _gate(FakeContext("inv-1", state), _request(("user", "hi")))
        _gate(
            FakeContext("inv-2", state),
            _request(("user", "hi"), ("model", "hello"), ("user", "hi")),
        )

        # The new message once per invocation (even if seen before), and the
        # history turn this process had not classified.
        assert model.calls == ["hi", "hi", "hello"]

    def test_block_applies_to_every_model_call_of_the_invocation(self, ml_enabled):
        model = FakeModel(TOXIC)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        ctx = FakeContext("inv-1")

        first = _gate(ctx, _request(("user", "you are stupid")))
        again = _gate(ctx, _tool_loop_request("you are stupid"))

        assert first.content.parts[0].text == BLOCKED_MESSAGE
        assert again.content.parts[0].text == BLOCKED_MESSAGE
        assert model.calls == ["you are stupid"]


class TestBlockedInputRedaction:
    def test_blocked_text_recorded_as_hash_only(self, ml_enabled):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=KeywordModel()))
        ctx = FakeContext("inv-1")

        _gate(ctx, _request(("user", "you are stupid")))

        stored = ctx.state[BLOCKED_INPUTS_STATE_KEY]
        assert len(stored) == 1
        assert "stupid" not in str(ctx.state)

    def test_blocked_turn_withheld_from_later_requests(self, ml_enabled):
        model = KeywordModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        state = {}

        _gate(FakeContext("inv-1", state), _request(("user", "you are stupid")))
        req = _request(
            ("user", "you are stupid"),
            ("model", BLOCKED_MESSAGE),
            ("user", "What's my balance?"),
        )
        result = _gate(FakeContext("inv-2", state), req)

        assert result is None
        assert [c.role for c in req.contents] == ["user", "model", "user"]
        assert req.contents[0].parts[0].text == WITHHELD_MESSAGE
        assert req.contents[2].parts[0].text == "What's my balance?"
        assert all("stupid" not in (p.text or "") for c in req.contents for p in c.parts)
        # The blocked turn is not classified again; the refusal text, never
        # seen before, is.
        assert model.calls == ["you are stupid", "What's my balance?", BLOCKED_MESSAGE]

    def test_redaction_also_applies_in_tool_loop(self, ml_enabled):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=KeywordModel()))
        state = {}
        _gate(FakeContext("inv-1", state), _request(("user", "you are stupid")))

        ctx = FakeContext("inv-2", state)
        _gate(ctx, _request(("user", "you are stupid"), ("model", "no"), ("user", "hi")))
        req = _tool_loop_request("hi")
        req.contents[:0] = _request(("user", "you are stupid"), ("model", "no")).contents
        assert _gate(ctx, req) is None

        assert req.contents[0].parts[0].text == WITHHELD_MESSAGE

    def test_redact_matches_any_role_and_keeps_roles(self):
        # A client can send its message with role "model"; the gate screens it
        # anyway, so a blocked text is withheld whatever role it carries.
        req = _request(("user", "hello"), ("model", "hello"), ("user", "other"))
        assert redact_blocked_inputs(req, []) == 0
        assert redact_blocked_inputs(req, [callbacks._text_hash("hello")]) == 2
        assert [c.role for c in req.contents] == ["user", "model", "user"]
        assert req.contents[0].parts[0].text == WITHHELD_MESSAGE
        assert req.contents[1].parts[0].text == WITHHELD_MESSAGE
        assert req.contents[2].parts[0].text == "other"

    def test_refusal_marks_blocked_hash_in_custom_metadata(self, ml_enabled):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=KeywordModel()))

        result = _gate(FakeContext(), _request(("user", "you are stupid")))

        assert result.custom_metadata == {
            BLOCKED_EVENT_METADATA_KEY: True,
            BLOCKED_HASH_METADATA_KEY: callbacks._text_hash("you are stupid"),
        }

    def test_blocked_hashes_come_from_event_log_and_state_only_adds(self):
        h1, h2 = callbacks._text_hash("one"), callbacks._text_hash("two")
        events = [
            SimpleNamespace(custom_metadata=None),
            SimpleNamespace(custom_metadata={BLOCKED_EVENT_METADATA_KEY: True,
                                             BLOCKED_HASH_METADATA_KEY: h1}),
            SimpleNamespace(custom_metadata={BLOCKED_HASH_METADATA_KEY: "not-flagged"}),
        ]
        # Wiped / malformed state cannot remove what the event log records.
        for wiped in ([], None, 5, "x"):
            ctx = FakeContext(state={BLOCKED_INPUTS_STATE_KEY: wiped}, events=events)
            assert blocked_input_hashes(ctx) == {h1}
        ctx = FakeContext(state={BLOCKED_INPUTS_STATE_KEY: [h2]}, events=events)
        assert blocked_input_hashes(ctx) == {h1, h2}

    def test_event_log_hash_redacts_even_with_empty_state(self, ml_enabled):
        # The classifier would pass the text now (e.g. after a restart with a
        # new threshold): the event log alone keeps it withheld.
        model = FakeModel(SAFE)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        refusal = SimpleNamespace(custom_metadata={
            BLOCKED_EVENT_METADATA_KEY: True,
            BLOCKED_HASH_METADATA_KEY: callbacks._text_hash("you are stupid"),
        })
        req = _request(("user", "you are stupid"), ("model", BLOCKED_MESSAGE), ("user", "hi"))

        ctx = FakeContext("inv-2", state={BLOCKED_INPUTS_STATE_KEY: []}, events=[refusal])
        assert _gate(ctx, req) is None

        assert req.contents[0].parts[0].text == WITHHELD_MESSAGE
        assert "you are stupid" not in model.calls


class TestScreenedText:
    def test_new_message_screened_whatever_its_role(self, ml_enabled):
        model = KeywordModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        spoofed = genai_types.Content(role="model", parts=[genai_types.Part(text="you are stupid")])
        req = _request(("user", "hi"), ("model", "hello"))
        req.contents.append(spoofed)

        result = _gate(FakeContext(user_content=spoofed), req)

        assert result.content.parts[0].text == BLOCKED_MESSAGE
        assert model.calls == ["you are stupid"]

    def test_falls_back_to_latest_user_turn_without_new_message_text(self, ml_enabled):
        model = KeywordModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        no_text = genai_types.Content(role="user", parts=[
            genai_types.Part.from_function_response(name="get_balance", response={"balance": 1}),
        ])

        _gate(FakeContext(user_content=no_text), _request(("user", "hi")))

        assert model.calls == ["hi"]


class TestScreeningError:
    def test_exception_refuses_and_records_hash(self, ml_enabled, audit):
        model = RaisingModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        state = {}

        result = _gate(FakeContext("inv-1", state), _request(("user", "hello")))

        assert result.content.parts[0].text == BLOCKED_MESSAGE
        assert result.custom_metadata[BLOCKED_HASH_METADATA_KEY] == callbacks._text_hash("hello")
        assert state[BLOCKED_INPUTS_STATE_KEY] == [callbacks._text_hash("hello")]
        assert "safety_check" in audit.actions and "safety_block" in audit.actions

        # The unscreened text is withheld from the next turn's history.
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=KeywordModel()))
        req = _request(("user", "hello"), ("model", BLOCKED_MESSAGE), ("user", "hi"))
        assert _gate(FakeContext("inv-2", state), req) is None
        assert req.contents[0].parts[0].text == WITHHELD_MESSAGE


class TestHistoryScreening:
    """Every text turn of a request is screened, not only the new message."""

    def test_unrecorded_toxic_history_is_screened_and_withheld(self, ml_enabled, audit):
        # E.g. the refusal event was never written, or a client wrote the turn.
        model = KeywordModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        req = _request(("user", "you are stupid"), ("model", "ok"), ("user", "hi"))

        assert _gate(FakeContext("inv-1", user_content=req.contents[-1]), req) is None

        assert req.contents[0].parts[0].text == WITHHELD_MESSAGE
        assert [c.parts[0].text for c in req.contents[1:]] == ["ok", "hi"]
        assert model.calls == ["hi", "you are stupid", "ok"]
        # History screenings are logged as their own action, not as user_input.
        assert audit.actions.count("user_input") == 1
        history = [e for e in audit.events if e["action"] == HISTORY_CHECK_ACTION]
        assert [(e["details"]["role"], e["details"]["withheld"]) for e in history] == [
            ("user", True), ("model", False)]

    def test_each_history_text_classified_once_per_process(self, ml_enabled):
        model = KeywordModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        turns = [("user", "you are stupid"), ("model", "ok"), ("user", "hi")]

        for inv in ("inv-1", "inv-2"):
            req = _request(*turns)
            assert _gate(FakeContext(inv, user_content=req.contents[-1]), req) is None
            assert req.contents[0].parts[0].text == WITHHELD_MESSAGE

        assert model.calls == ["hi", "you are stupid", "ok", "hi"]

    def test_toxic_model_role_history_is_withheld_not_refused(self, ml_enabled):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=KeywordModel()))
        req = _request(("user", "hello"), ("model", "you are stupid"), ("user", "hi"))

        assert _gate(FakeContext(user_content=req.contents[-1]), req) is None
        assert req.contents[1].role == "model"
        assert req.contents[1].parts[0].text == WITHHELD_MESSAGE

    def test_history_not_screened_when_new_message_is_blocked(self, ml_enabled):
        model = KeywordModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        req = _request(("user", "hello"), ("model", "ok"), ("user", "you are stupid"))

        result = _gate(FakeContext(user_content=req.contents[-1]), req)

        assert result.content.parts[0].text == BLOCKED_MESSAGE
        assert model.calls == ["you are stupid"]

    def test_history_error_withholds_turns_without_caching(self, ml_enabled, audit):
        class FailsOnHistory(KeywordModel):
            def _score(self, text):
                if text == "old turn":
                    raise RuntimeError("classifier crashed")
                return super()._score(text)

        model = FailsOnHistory()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        req = _request(("user", "old turn"), ("model", "ok"), ("user", "hi"))

        assert _gate(FakeContext(user_content=req.contents[-1]), req) is None

        # Both turns of the failed batch are withheld from this request.
        assert [c.parts[0].text for c in req.contents] == [
            WITHHELD_MESSAGE, WITHHELD_MESSAGE, "hi"]
        assert HISTORY_CHECK_ACTION in audit.actions
        # Not cached: the next request classifies them again.
        req = _request(("user", "old turn"), ("model", "ok"), ("user", "hi"))
        _gate(FakeContext("inv-2", user_content=req.contents[-1]), req)
        assert model.calls.count("ok") == 2

    def test_ml_disabled_skips_history_screening(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_SAFETY_USE_ML_MODELS", "false")
        model = KeywordModel()
        set_text_tool(TextSafetyTool(model=model))
        req = _request(("user", "you are stupid"), ("model", "ok"), ("user", "hi"))

        assert _gate(FakeContext(user_content=req.contents[-1]), req) is None
        assert model.calls == []

    def test_classification_runs_off_the_event_loop_thread(self, ml_enabled):
        model = KeywordModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        loop_threads = []

        async def go():
            loop_threads.append(threading.get_ident())
            req = _request(("user", "earlier"), ("model", "ok"), ("user", "hi"))
            return await fast_guardrail_callback(FakeContext(user_content=req.contents[-1]), req)

        assert asyncio.run(go()) is None
        assert model.threads and loop_threads[0] not in model.threads


class TestTooLong:
    def test_message_over_cap_is_refused_unclassified_and_recorded(self, ml_enabled, audit):
        model = KeywordModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        state = {}
        text = "a" * (MAX_CHARS + 1)

        result = _gate(FakeContext("inv-1", state), _request(("user", text)))

        assert result.content.parts[0].text == TOO_LONG_MESSAGE
        assert result.custom_metadata[BLOCKED_HASH_METADATA_KEY] == callbacks._text_hash(text)
        assert state[BLOCKED_INPUTS_STATE_KEY] == [callbacks._text_hash(text)]
        assert model.calls == []
        assert "safety_block" in audit.actions


class TestGateFailsClosed:
    """Any exception in the gate refuses the request and records the hash."""

    def test_lone_surrogate_is_hashed_and_refused(self, ml_enabled, audit):
        model = StrictKeywordModel()
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=model))
        state = {}
        text = "hello \ud800"

        result = _gate(FakeContext("inv-1", state), _request(("user", text)))

        assert result.content.parts[0].text == BLOCKED_MESSAGE
        text_hash = callbacks._text_hash(text)
        assert result.custom_metadata[BLOCKED_HASH_METADATA_KEY] == text_hash
        assert state[BLOCKED_INPUTS_STATE_KEY] == [text_hash]
        assert "safety_block" in audit.actions

    @pytest.mark.parametrize("target", [
        "screened_text", "request_text_turns", "blocked_input_hashes", "redact_blocked_inputs",
    ])
    def test_exception_anywhere_in_the_gate_refuses(self, ml_enabled, monkeypatch, target):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=FakeModel(SAFE)))

        def broken(*args, **kwargs):
            raise RuntimeError("gate bug")

        monkeypatch.setattr(callbacks, target, broken)
        state = {}
        req = _request(("user", "hello"))

        result = _gate(FakeContext("inv-1", state, user_content=req.contents[0]), req)

        assert result.content.parts[0].text == BLOCKED_MESSAGE
        if target != "screened_text":  # the hash is known once the text is
            assert state[BLOCKED_INPUTS_STATE_KEY] == [callbacks._text_hash("hello")]

    def test_audit_logger_failure_does_not_change_decision(self, ml_enabled, monkeypatch):
        def broken():
            raise PermissionError("log dir unwritable")

        monkeypatch.setattr(callbacks, "get_audit_logger", broken)
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=KeywordModel()))

        assert _gate(FakeContext("inv-1"), _request(("user", "hi"))) is None
        blocked = _gate(FakeContext("inv-2"), _request(("user", "you are stupid")))
        assert blocked.content.parts[0].text == BLOCKED_MESSAGE


class TestGateSpan:
    def test_allowed_request_span(self, ml_enabled, spans):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=FakeModel(SAFE)))

        _gate(FakeContext(), _request(("user", "hi")))

        (span,) = spans.get_finished_spans()
        assert span.name == GATE_SPAN_NAME
        assert span.attributes["scope.safety.blocked"] is False
        assert span.attributes["scope.safety.outcome"] == "allowed"
        assert span.attributes["scope.safety.max_score"] == pytest.approx(0.02)

    def test_blocked_request_span(self, ml_enabled, spans):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=FakeModel(TOXIC)))

        _gate(FakeContext(), _request(("user", "you are stupid")))

        (span,) = spans.get_finished_spans()
        assert span.attributes["scope.safety.blocked"] is True
        assert span.attributes["scope.safety.risk_category"] == "insult"
        assert span.attributes["scope.safety.max_score"] == pytest.approx(0.95)

    def test_one_span_per_invocation(self, ml_enabled, spans):
        set_text_tool(TextSafetyTool(threshold_high=0.8, model=FakeModel(SAFE)))
        ctx = FakeContext("inv-1")

        _gate(ctx, _request(("user", "hi")))
        _gate(ctx, _tool_loop_request("hi"))

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

    def _run(self, runner, session_id, text, role="user", **kwargs):
        async def go():
            events = []
            async for event in runner.run_async(
                user_id="u",
                session_id=session_id,
                new_message=genai_types.Content(role=role, parts=[genai_types.Part(text=text)]),
                **kwargs,
            ):
                events.append(event)
            return events

        return asyncio.run(go())

    def _setup(self, classifier):
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
        return llm, runner, session

    @staticmethod
    def _texts(llm):
        return [p.text for r in llm.requests for c in r.contents for p in c.parts if p.text]

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

        # Two model calls (tool call + answer). Each text is classified once:
        # the blocked text is not re-classified, the refusal text is.
        assert len(llm.requests) == 2
        assert classifier.calls == ["you are stupid", "What's my balance?", BLOCKED_MESSAGE]
        assert audit.actions.count("user_input") == 2
        for request in llm.requests:
            texts = [p.text for c in request.contents for p in c.parts if p.text]
            assert not any("stupid" in t for t in texts)
            assert WITHHELD_MESSAGE in texts

    def test_refusal_event_records_blocked_hash(self, ml_enabled):
        llm, runner, session = self._setup(KeywordModel())

        events = self._run(runner, session.id, "you are stupid")

        assert events[-1].custom_metadata == {
            BLOCKED_EVENT_METADATA_KEY: True,
            BLOCKED_HASH_METADATA_KEY: callbacks._text_hash("you are stupid"),
        }
        stored = asyncio.run(runner.session_service.get_session(
            app_name="gate_test", user_id="u", session_id=session.id))
        assert any(
            (e.custom_metadata or {}).get(BLOCKED_EVENT_METADATA_KEY) for e in stored.events
        )

    @pytest.mark.parametrize("wipe", ["run_state_delta", "state_only_event"])
    def test_client_cannot_undo_redaction_by_wiping_state(self, ml_enabled, wipe):
        llm, runner, session = self._setup(KeywordModel())
        self._run(runner, session.id, "you are stupid")
        assert llm.requests == []

        wiped = {BLOCKED_INPUTS_STATE_KEY: []}
        if wipe == "run_state_delta":
            # What /run and /run_sse do with RunAgentRequest.state_delta.
            self._run(runner, session.id, "What's my balance?", state_delta=wiped)
        else:
            # What PATCH /apps/.../sessions/{id} does: append a state-only event.
            async def patch():
                s = await runner.session_service.get_session(
                    app_name="gate_test", user_id="u", session_id=session.id)
                await runner.session_service.append_event(s, Event(
                    invocation_id="p-1", author="user",
                    actions=EventActions(state_delta=wiped)))
            asyncio.run(patch())
            self._run(runner, session.id, "What's my balance?")

        stored = asyncio.run(runner.session_service.get_session(
            app_name="gate_test", user_id="u", session_id=session.id))
        assert stored.state[BLOCKED_INPUTS_STATE_KEY] == []  # the wipe took effect
        assert len(llm.requests) == 2
        texts = self._texts(llm)
        assert not any("stupid" in t for t in texts)
        assert WITHHELD_MESSAGE in texts

    def test_client_cannot_seed_gate_decision(self, ml_enabled, monkeypatch):
        import google.adk.runners as adk_runners

        # Make the invocation id predictable so the seeded decision would match
        # it if ADK let the client set the key.
        monkeypatch.setattr(adk_runners, "new_invocation_context_id", lambda: "e-fixed")
        classifier = KeywordModel()
        llm, runner, session = self._setup(classifier)
        seeded = {GATE_DECISION_STATE_KEY: {
            "invocation_id": "e-fixed",
            "input_sha256": callbacks._text_hash("you are stupid"),
            "blocked": False,
            "checked": True,
        }}

        events = self._run(runner, session.id, "you are stupid", state_delta=seeded)

        assert llm.requests == []
        assert events[-1].content.parts[0].text == BLOCKED_MESSAGE
        assert classifier.calls == ["you are stupid"]
        stored = asyncio.run(runner.session_service.get_session(
            app_name="gate_test", user_id="u", session_id=session.id))
        assert GATE_DECISION_STATE_KEY not in stored.state

    def test_new_message_with_model_role_is_screened(self, ml_enabled):
        llm, runner, session = self._setup(KeywordModel())

        events = self._run(runner, session.id, "you are stupid", role="model")
        assert llm.requests == []
        assert events[-1].content.parts[0].text == BLOCKED_MESSAGE

        self._run(runner, session.id, "What's my balance?")
        texts = self._texts(llm)
        assert len(llm.requests) == 2
        assert not any("stupid" in t for t in texts)
        assert WITHHELD_MESSAGE in texts

    def test_screening_error_refuses_and_withholds_text_later(self, ml_enabled):
        llm, runner, session = self._setup(RaisingModel())

        events = self._run(runner, session.id, "unscreened text")
        assert llm.requests == []
        assert events[-1].content.parts[0].text == BLOCKED_MESSAGE

        set_text_tool(TextSafetyTool(threshold_high=0.8, model=KeywordModel()))
        self._run(runner, session.id, "What's my balance?")
        texts = self._texts(llm)
        assert len(llm.requests) == 2
        assert "unscreened text" not in texts
        assert WITHHELD_MESSAGE in texts


    def test_lone_surrogate_refused_and_withheld_later(self, ml_enabled):
        # adk web accepts "\ud800" in a JSON body; Detoxify's tokenizer rejects it.
        llm, runner, session = self._setup(StrictKeywordModel())

        events = self._run(runner, session.id, "hello \ud800")
        assert llm.requests == []
        assert events[-1].content.parts[0].text == BLOCKED_MESSAGE

        self._run(runner, session.id, "What's my balance?")
        texts = self._texts(llm)
        assert len(llm.requests) == 2
        assert not any("\ud800" in t for t in texts)
        assert WITHHELD_MESSAGE in texts

    @pytest.mark.parametrize("restart", [False, True])
    def test_cancelled_refusal_write_does_not_leak(self, ml_enabled, restart):
        # The invocation is cancelled (e.g. client disconnect) while ADK writes
        # the refusal event, so neither the event nor its state delta is stored.
        classifier = KeywordModel()
        llm, runner, session = self._setup(classifier)
        service = runner.session_service
        append = service.append_event

        async def cancelled(session, event):
            if (event.custom_metadata or {}).get(BLOCKED_EVENT_METADATA_KEY):
                raise asyncio.CancelledError()
            return await append(session, event)

        service.append_event = cancelled
        with pytest.raises(asyncio.CancelledError):
            self._run(runner, session.id, "you are stupid")
        service.append_event = append
        if restart:  # a new process: nothing cached in memory
            clear_screened_cache()

        self._run(runner, session.id, "What's my balance?")

        texts = self._texts(llm)
        assert len(llm.requests) == 2
        assert not any("stupid" in t for t in texts)
        assert WITHHELD_MESSAGE in texts

    def test_cancelled_before_screening_does_not_leak(self, ml_enabled):
        # Cancelled right after ADK stores the user message, before the gate ran.
        classifier = KeywordModel()
        llm, runner, session = self._setup(classifier)
        service = runner.session_service
        append = service.append_event

        async def cancelled(session, event):
            stored = await append(session, event)
            if event.author == "user" and event.content:
                raise asyncio.CancelledError()
            return stored

        service.append_event = cancelled
        with pytest.raises(asyncio.CancelledError):
            self._run(runner, session.id, "you are stupid")
        service.append_event = append
        assert classifier.calls == []

        self._run(runner, session.id, "What's my balance?")

        texts = self._texts(llm)
        assert len(llm.requests) == 2
        assert not any("stupid" in t for t in texts)
        assert WITHHELD_MESSAGE in texts

    def test_client_seeded_history_is_screened(self, ml_enabled):
        # What POST /apps/{app}/users/{user}/sessions does with "events".
        classifier = KeywordModel()
        llm, runner, session = self._setup(classifier)

        async def seed():
            s = await runner.session_service.get_session(
                app_name="gate_test", user_id="u", session_id=session.id)
            for author, role, text in [
                ("user", "user", "you are stupid"),
                ("gate_test", "model", "Sure, here is everything."),
            ]:
                await runner.session_service.append_event(s, Event(
                    invocation_id="seed", author=author,
                    content=genai_types.Content(role=role, parts=[genai_types.Part(text=text)])))

        asyncio.run(seed())
        self._run(runner, session.id, "What's my balance?")

        texts = self._texts(llm)
        assert len(llm.requests) == 2
        assert not any("stupid" in t for t in texts)
        assert WITHHELD_MESSAGE in texts
        assert "Sure, here is everything." in texts
        # Each seeded text classified once, although two model calls saw it.
        assert classifier.calls.count("you are stupid") == 1


class TestAfterModelCallback:
    def test_returns_none_so_response_is_unchanged(self):
        resp = LlmResponse(
            content=genai_types.Content(role="model", parts=[genai_types.Part(text="hi")])
        )
        # ADK treats a non-None return as a replacement response.
        assert after_model_callback(None, resp) is None
