"""Tests for the audit trail: daily rollover, fail-open writes, tool-call
logging, model-response logging, view_audit_logs ordering, and the terminal
viewer's filters.

All writes go to tmp dirs (see the ``isolated_log_dirs`` fixture in conftest.py).
"""

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from google.adk.models import LlmResponse
from google.genai import types as genai_types

import scope.logging.audit as audit_module
import scope.logging.compliance_log as compliance_module
from scope.callbacks import (
    after_model_callback,
    audit_tool_call_callback,
    audit_tool_error_callback,
)
from scope.logging import AuditLogger, ComplianceLogger, get_audit_logger
from scope.logging import view_logs


def _run_scripted_agent(tool_func, tool_args):
    """Run a real ADK agent whose scripted model calls ``tool_func`` once.

    Returns the function responses ADK sent back to the model.
    """
    from google.adk.agents import LlmAgent
    from google.adk.models import BaseLlm
    from google.adk.runners import InMemoryRunner

    class ScriptedLlm(BaseLlm):
        model: str = "scripted"

        async def generate_content_async(self, llm_request, stream=False):
            answered = any(
                p.function_response
                for c in llm_request.contents for p in (c.parts or [])
            )
            part = (
                genai_types.Part(text="done") if answered
                else genai_types.Part(function_call=genai_types.FunctionCall(
                    name=tool_func.__name__, args=tool_args))
            )
            yield LlmResponse(content=genai_types.Content(role="model", parts=[part]))

    agent = LlmAgent(
        name="audit_wiring_test",
        model=ScriptedLlm(),
        tools=[tool_func],
        after_tool_callback=audit_tool_call_callback,
        on_tool_error_callback=audit_tool_error_callback,
    )

    async def run():
        runner = InMemoryRunner(agent=agent, app_name="audit_test")
        session = await runner.session_service.create_session(
            app_name="audit_test", user_id="u")
        message = genai_types.Content(role="user", parts=[genai_types.Part(text="hi")])
        responses = []
        async for event in runner.run_async(
            user_id="u", session_id=session.id, new_message=message
        ):
            responses.extend(
                p.function_response.response
                for p in (event.content.parts if event.content else None) or []
                if p.function_response
            )
        return responses

    return asyncio.run(run())


def _read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _audit_events(audit_dir):
    events = []
    for path in sorted(audit_dir.glob("audit_*.jsonl")):
        events.extend(_read_jsonl(path))
    return events


class _Clock:
    current = datetime(2026, 1, 1, 23, 59, 59)


class _FakeDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return _Clock.current


@pytest.fixture
def fake_clock(monkeypatch):
    monkeypatch.setattr(audit_module, "datetime", _FakeDatetime)
    monkeypatch.setattr(compliance_module, "datetime", _FakeDatetime)
    _Clock.current = datetime(2026, 1, 1, 23, 59, 59)
    return _Clock


class TestDailyRollover:
    def test_audit_log_rolls_over_at_midnight(self, tmp_path, fake_clock):
        logger = AuditLogger(log_dir=tmp_path / "audit")

        logger.log_event(audit_module.AuditEventType.USER_QUERY, "user", "before_midnight")
        fake_clock.current = datetime(2026, 1, 2, 0, 0, 1)
        logger.log_event(audit_module.AuditEventType.USER_QUERY, "user", "after_midnight")

        day1 = _read_jsonl(tmp_path / "audit" / "audit_2026-01-01.jsonl")
        day2 = _read_jsonl(tmp_path / "audit" / "audit_2026-01-02.jsonl")
        assert [e["action"] for e in day1] == ["before_midnight"]
        assert [e["action"] for e in day2] == ["after_midnight"]
        assert logger.current_log_file().name == "audit_2026-01-02.jsonl"

    def test_compliance_logs_roll_over_at_midnight(self, tmp_path, fake_clock):
        logger = ComplianceLogger(log_dir=tmp_path / "compliance")

        logger.log_soc2_access_control("user", "audit_logs", "view_logs", granted=False)
        fake_clock.current = datetime(2026, 1, 2, 9, 0, 0)
        logger.log_pci_data_access("user", "account", "acc001", "read")
        logger.log_soc2_access_control("staff", "audit_logs", "view_logs", granted=True)

        d = tmp_path / "compliance"
        assert len(_read_jsonl(d / "soc2_2026-01-01.jsonl")) == 1
        assert len(_read_jsonl(d / "soc2_2026-01-02.jsonl")) == 1
        assert _read_jsonl(d / "pci_dss_2026-01-02.jsonl")[0]["event_type"] == "pci_data_access"

    def test_separate_instances_do_not_cross_write(self, tmp_path):
        a = AuditLogger(log_dir=tmp_path / "a")
        b = AuditLogger(log_dir=tmp_path / "b")
        a.log_event(audit_module.AuditEventType.USER_QUERY, "user", "only_a")

        assert [e["action"] for e in _audit_events(tmp_path / "a")] == ["only_a"]
        assert _audit_events(tmp_path / "b") == []


class TestFailOpenWrites:
    """An audit-log write failure must never change a tool's outcome."""

    def test_missing_log_dir_is_recreated(self, tmp_path):
        logger = AuditLogger(log_dir=tmp_path / "audit")
        (tmp_path / "audit").rmdir()  # deleted while the process runs

        logger.log_event(audit_module.AuditEventType.USER_QUERY, "user", "after_delete")

        assert [e["action"] for e in _audit_events(tmp_path / "audit")] == ["after_delete"]

    def test_unwritable_log_dir_does_not_raise(self, tmp_path, caplog):
        blocker = tmp_path / "not_a_dir"
        blocker.write_text("")  # a file where the log directory should be

        audit_module.append_daily_jsonl(blocker, "audit", {"action": "x"})

        assert "Failed to write log record" in caplog.text

    def test_logger_construction_with_unwritable_dir_does_not_raise(self, tmp_path, caplog):
        blocker = tmp_path / "not_a_dir"
        blocker.write_text("")

        AuditLogger(log_dir=str(blocker / "audit")).log_event(
            audit_module.AuditEventType.USER_QUERY, "user", "x")
        ComplianceLogger(log_dir=str(blocker / "compliance"))

        assert "Failed to create audit log directory" in caplog.text
        assert "Failed to create compliance log directory" in caplog.text
        assert "Failed to write log record" in caplog.text

    def test_non_json_values_are_written_as_strings(self, tmp_path):
        when = datetime(2026, 1, 1, 12, 0, 0)
        path = audit_module.append_daily_jsonl(
            tmp_path, "audit", {"at": when}, when=when)

        assert _read_jsonl(path) == [{"at": "2026-01-01 12:00:00"}]

    def test_log_agent_response_reports_failed_write(self, tmp_path, monkeypatch):
        from scope.observability_tools import log_agent_response

        blocker = tmp_path / "not_a_dir"
        blocker.write_text("")
        monkeypatch.setattr(get_audit_logger(), "log_dir", blocker)

        assert log_agent_response("summary", "text").startswith("⚠️ Failed to log response")

    def test_tool_callbacks_do_not_raise_when_logging_fails(self, monkeypatch, caplog):
        def broken(*args, **kwargs):
            raise RuntimeError("disk on fire")

        monkeypatch.setattr(get_audit_logger(), "log_tool_call", broken)
        tool = SimpleNamespace(name="transfer_money")

        assert audit_tool_call_callback(tool, {}, None, "✅ Transfer complete") is None
        assert audit_tool_error_callback(tool, {}, None, ValueError("x")) is None
        assert "Failed to log tool call" in caplog.text
        assert "Failed to log tool error" in caplog.text

    def test_tool_result_unchanged_when_log_dir_unwritable(
        self, tmp_path, monkeypatch, caplog
    ):
        blocker = tmp_path / "not_a_dir"
        blocker.write_text("")
        monkeypatch.setattr(get_audit_logger(), "log_dir", blocker)

        def lookup_account(account_id: str) -> str:
            """Look up an account."""
            return f"Account {account_id} found"

        responses = _run_scripted_agent(lookup_account, {"account_id": "acc001"})

        assert responses == [{"result": "Account acc001 found"}]
        assert "Failed to write log record" in caplog.text


class TestToolCallAudit:
    def test_success_is_logged_with_role_and_args(self, isolated_log_dirs, monkeypatch):
        monkeypatch.setenv("GOOGLE_IAM_CURRENT_USER_ROLE", "STAFF")
        audit_dir, _ = isolated_log_dirs
        tool = SimpleNamespace(name="get_account_balance")

        # Called with the keyword names ADK 1.25 uses for after_tool_callback.
        result = audit_tool_call_callback(
            tool=tool,
            args={"account_id": "acc001"},
            tool_context=None,
            tool_response="Account acc001 (checking): $1234.56 USD",
        )

        assert result is None  # response passes through unchanged
        [event] = _audit_events(audit_dir)
        assert event["event_type"] == "tool_call"
        assert event["action"] == "tool_call_get_account_balance"
        assert event["success"] is True
        assert event["details"]["parameters"] == {"account_id": "acc001"}
        assert event["details"]["role"] == "STAFF"
        # The response body (a balance) is not copied into the tool_call event.
        # (The llm_response event may still contain it if the model repeats it.)
        assert "1234.56" not in json.dumps(event)

    def test_error_and_denial_responses_are_marked_failed(self, isolated_log_dirs):
        audit_dir, _ = isolated_log_dirs
        tool = SimpleNamespace(name="view_audit_logs")

        audit_tool_call_callback(
            tool, {}, None,
            "❌ Permission denied: You do not have permission to view audit logs",
        )
        audit_tool_call_callback(
            SimpleNamespace(name="list_escalation_tickets"), {"status": None}, None,
            "Error listing tickets: boom",
        )

        denied, errored = _audit_events(audit_dir)
        assert denied["success"] is False
        assert "Permission denied" in denied["error"]
        assert errored["success"] is False
        assert errored["action"] == "tool_call_list_escalation_tickets"

    def test_json_response_with_error_key_is_marked_failed(self, isolated_log_dirs):
        audit_dir, _ = isolated_log_dirs
        tool = SimpleNamespace(name="make_safe_and_compliant_decision")

        audit_tool_call_callback(tool, {}, None, json.dumps(
            {"action": "escalate", "params": {}, "reasoning": "...", "error": "boom"},
            indent=2,
        ))
        audit_tool_call_callback(tool, {}, None, json.dumps(
            {"action": "approve", "params": {}, "reasoning": "ok"}))
        audit_tool_call_callback(tool, {}, None, "{not json")

        failed, ok, unparsable = _audit_events(audit_dir)
        assert failed["success"] is False
        assert failed["error"] == "boom"
        assert ok["success"] is True
        assert unparsable["success"] is True

    def test_other_replies_are_recorded_as_success(self, isolated_log_dirs):
        audit_dir, _ = isolated_log_dirs

        audit_tool_call_callback(
            SimpleNamespace(name="get_ticket"), {}, None, "Ticket T-1 not found")

        [event] = _audit_events(audit_dir)
        assert event["success"] is True

    def test_sensitive_and_long_args_are_not_dumped(self, isolated_log_dirs):
        audit_dir, _ = isolated_log_dirs
        long_text = "x" * 5000

        audit_tool_call_callback(
            SimpleNamespace(name="log_agent_response"),
            {"full_response": long_text, "api_key": "sk-test", "meta": {"a": 1}},
            None,
            "✅ Response logged",
        )

        [event] = _audit_events(audit_dir)
        params = event["details"]["parameters"]
        assert len(params["full_response"]) < 300
        assert params["api_key"] == "[REDACTED]"
        assert params["meta"] == "<dict>"

    def test_raised_tool_error_is_logged(self, isolated_log_dirs):
        audit_dir, _ = isolated_log_dirs

        result = audit_tool_error_callback(
            tool=SimpleNamespace(name="transfer_money"),
            args={"amount": 10.0},
            tool_context=None,
            error=RuntimeError("db down"),
        )

        assert result is None  # ADK re-raises the original exception
        [event] = _audit_events(audit_dir)
        assert event["success"] is False
        assert event["error"] == "RuntimeError: db down"

    def test_callbacks_registered_on_agent(self):
        from scope.agent import root_agent

        assert root_agent.after_tool_callback is audit_tool_call_callback
        assert root_agent.on_tool_error_callback is audit_tool_error_callback

    def test_adk_runner_invokes_callback_for_each_tool_call(self, isolated_log_dirs):
        """Drive a real ADK run with a scripted model to check the wiring."""
        def lookup_account(account_id: str) -> str:
            """Look up an account."""
            return f"Account {account_id} found"

        responses = _run_scripted_agent(lookup_account, {"account_id": "acc001"})

        assert responses == [{"result": "Account acc001 found"}]
        audit_dir, _ = isolated_log_dirs
        tool_events = [e for e in _audit_events(audit_dir) if e["event_type"] == "tool_call"]
        assert len(tool_events) == 1
        assert tool_events[0]["action"] == "tool_call_lookup_account"
        assert tool_events[0]["details"]["parameters"] == {"account_id": "acc001"}
        assert tool_events[0]["success"] is True


class TestAfterModelCallbackLogging:
    def test_logs_truncated_text_and_function_calls(self, isolated_log_dirs):
        audit_dir, _ = isolated_log_dirs
        resp = LlmResponse(
            content=genai_types.Content(
                role="model",
                parts=[
                    genai_types.Part(text="a" * 800),
                    genai_types.Part(
                        function_call=genai_types.FunctionCall(
                            name="get_account_balance", args={"account_id": "acc001"}
                        )
                    ),
                ],
            )
        )

        assert after_model_callback(None, resp) is None  # response not replaced

        [event] = _audit_events(audit_dir)
        assert event["action"] == "llm_response"
        assert len(event["details"]["text"]) == 500
        assert event["details"]["function_calls"] == ["get_account_balance"]


class TestViewAuditLogs:
    @pytest.fixture
    def staff_config(self):
        with patch("scope.observability_tools.config") as cfg:
            cfg.IAM_CURRENT_USER_ID = "staff"
            cfg.IAM_CURRENT_USER_ROLE = "STAFF"
            cfg.IAM_CURRENT_USER_NAME = "Bob Staff"
            yield cfg

    def _write_entries(self, audit_dir, n, event_type="user_query"):
        path = audit_dir / "audit_2026-01-01.jsonl"
        with open(path, "a") as f:
            for i in range(n):
                f.write(json.dumps({
                    "timestamp": f"2026-01-01T10:00:{i:02d}",
                    "event_type": event_type,
                    "user_id": "user",
                    "action": f"action_{i}",
                    "success": True,
                    "details": {},
                }) + "\n")

    def test_returns_newest_entries_newest_first(self, isolated_log_dirs, staff_config):
        from scope.observability_tools import view_audit_logs

        audit_dir, _ = isolated_log_dirs
        self._write_entries(audit_dir, 30)

        output = view_audit_logs(limit=3)

        shown = [line.split("] ✓ ")[1] for line in output.splitlines() if "] ✓ " in line]
        assert shown == ["action_29", "action_28", "action_27"]

    def test_event_type_filter_applies_before_limit(self, isolated_log_dirs, staff_config):
        from scope.observability_tools import view_audit_logs

        audit_dir, _ = isolated_log_dirs
        self._write_entries(audit_dir, 5, event_type="tool_call")
        self._write_entries(audit_dir, 5, event_type="user_query")

        output = view_audit_logs(limit=2, event_type="tool_call")

        assert "Type: tool_call" in output
        assert "Type: user_query" not in output
        assert output.count("] ✓ ") == 2

    def test_access_decision_logged_as_soc2_cc61(self, isolated_log_dirs, staff_config):
        from scope.observability_tools import view_audit_logs

        _, compliance_dir = isolated_log_dirs
        view_audit_logs()
        staff_config.IAM_CURRENT_USER_ID = "user"
        staff_config.IAM_CURRENT_USER_ROLE = "USER"
        assert "Permission denied" in view_audit_logs()

        events = []
        for path in compliance_dir.glob("soc2_*.jsonl"):
            events.extend(_read_jsonl(path))
        assert [(e["user_id"], e["details"]["granted"]) for e in events] == [
            ("staff", True), ("user", False)
        ]
        assert all(e["details"]["control"] == "SOC2 CC6.1" for e in events)


class TestViewLogsFollowFilters:
    def test_follow_mode_applies_filters(self, tmp_path, monkeypatch, capsys):
        log = tmp_path / "audit_2026-01-01.jsonl"
        log.write_text("")
        calls = {"n": 0}

        def fake_sleep(_):
            calls["n"] += 1
            if calls["n"] > 1:
                raise KeyboardInterrupt
            with open(log, "a") as f:
                for user, action in [("alice", "kept_action"), ("bob", "dropped_action")]:
                    f.write(json.dumps({
                        "timestamp": "2026-01-01T10:00:00",
                        "event_type": "tool_call",
                        "user_id": user,
                        "action": action,
                    }) + "\n")

        monkeypatch.setattr(view_logs.time, "sleep", fake_sleep)
        view_logs.follow_logs(log, user_filter="alice")

        out = capsys.readouterr().out
        assert "kept_action" in out
        assert "dropped_action" not in out
