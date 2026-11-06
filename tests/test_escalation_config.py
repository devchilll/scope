"""Tests for escalation wiring and config-driven behaviour.

Covers: configured escalation threshold and model in the decision prompt,
GOOGLE_GENAI_USE_VERTEXAI, ticket confidence pass-through, the deterministic
COMP-004 high-value transfer guard, fraud-report metadata, and custom
compliance rules in the agent instruction.

All database access uses a temporary SQLite file and loggers are mocked, so
nothing is written to scope/data/storage or scope/logging.
"""

import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import scope.data.tools as data_tools
import scope.escalation as escalation_pkg
import scope.observability_tools as obs_tools
from scope.config import Config
from scope.data import Database
from scope.data.models import Account, AccountType, User as DataUser
from scope.escalation import EscalationQueue
from scope.iam import User as IAMUser, UserRole
from scope.rules import COMPLIANCE_CONFIG


@pytest.fixture
def tmp_db(tmp_path):
    """Temporary banking database with one user owning two accounts."""
    db = Database(str(tmp_path / "banking_test.db"))
    db.create_user(DataUser(user_id="user1", name="Test User", email="t@example.com"))
    for acc_id, balance in (("acc1", 50000.0), ("acc2", 100.0)):
        db.create_account(Account(
            account_id=acc_id,
            user_id="user1",
            account_type=AccountType.CHECKING,
            balance=balance,
            currency="USD",
            status="active",
            created_at=datetime.now()
        ))
    return db


@pytest.fixture
def banking_tools(monkeypatch, tmp_db):
    """Point scope.data.tools at the temp database, a test user and mock loggers."""
    monkeypatch.setattr(data_tools, "db", tmp_db)
    monkeypatch.setattr(data_tools, "config", Config(
        IAM_CURRENT_USER_ID="user1", IAM_CURRENT_USER_ROLE="USER", IAM_CURRENT_USER_NAME="Test User"
    ))
    monkeypatch.setattr(data_tools, "audit_logger", MagicMock())
    monkeypatch.setattr(data_tools, "compliance_logger", MagicMock())
    return tmp_db


def _all_tickets(db):
    return EscalationQueue(db).view_tickets(IAMUser("staff1", UserRole.STAFF))


class TestDecisionPrompt:
    """make_safe_and_compliant_decision uses configured threshold and model."""

    def _run_decision(self, monkeypatch, cfg):
        client = MagicMock()
        client.models.generate_content.return_value.text = json.dumps(
            {"action": "approve", "params": {}, "reasoning": "ok"}
        )
        monkeypatch.setattr(obs_tools, "genai_client", client)
        monkeypatch.setattr(obs_tools, "audit_logger", MagicMock())
        monkeypatch.setattr(obs_tools, "config", cfg)
        obs_tools.make_safe_and_compliant_decision({"safety_score": 0.9, "confidence": 0.5})
        return client.models.generate_content.call_args.kwargs

    def test_prompt_uses_configured_threshold(self, monkeypatch):
        kwargs = self._run_decision(monkeypatch, Config(ESCALATION_THRESHOLD=0.85))
        assert "confidence < 0.85" in kwargs["contents"]
        assert "confidence < 0.7" not in kwargs["contents"]

    def test_default_threshold_is_0_6(self, monkeypatch):
        assert Config.model_fields["ESCALATION_THRESHOLD"].default == 0.6
        kwargs = self._run_decision(monkeypatch, Config(ESCALATION_THRESHOLD=0.6))
        assert "confidence < 0.6" in kwargs["contents"]

    def test_decision_uses_configured_model(self, monkeypatch):
        cfg = Config()
        cfg.agent_settings.model = "gemini-test-model"
        kwargs = self._run_decision(monkeypatch, cfg)
        assert kwargs["model"] == "gemini-test-model"


class TestGenaiClient:
    """GOOGLE_GENAI_USE_VERTEXAI selects Vertex AI or the Gemini API."""

    def test_vertexai_true(self, monkeypatch):
        fake_client = MagicMock()
        monkeypatch.setattr(obs_tools, "Client", fake_client)
        obs_tools._make_genai_client(Config(GENAI_USE_VERTEXAI="true", CLOUD_PROJECT="p", CLOUD_LOCATION="l"))
        fake_client.assert_called_once_with(vertexai=True, project="p", location="l")

    def test_vertexai_false(self, monkeypatch):
        fake_client = MagicMock()
        monkeypatch.setattr(obs_tools, "Client", fake_client)
        obs_tools._make_genai_client(Config(GENAI_USE_VERTEXAI="false"))
        fake_client.assert_called_once_with(vertexai=False)


class TestEscalationTicketConfidence:
    """create_escalation_ticket stores the Layer 2b confidence."""

    @pytest.fixture
    def obs_with_tmp_db(self, monkeypatch, tmp_db):
        monkeypatch.setattr(obs_tools, "EscalationQueue", lambda: EscalationQueue(tmp_db))
        monkeypatch.setattr(obs_tools, "audit_logger", MagicMock())
        monkeypatch.setattr(obs_tools, "config", Config(IAM_CURRENT_USER_ID="user1"))
        return tmp_db

    def test_confidence_passed_through(self, obs_with_tmp_db):
        result = obs_tools.create_escalation_ticket("ambiguous request", "low confidence", confidence=0.55)
        assert "Ticket ID" in result
        tickets = _all_tickets(obs_with_tmp_db)
        assert len(tickets) == 1
        assert tickets[0].confidence == 0.55

    def test_confidence_default_and_clamp(self, obs_with_tmp_db):
        obs_tools.create_escalation_ticket("a", "r")
        obs_tools.create_escalation_ticket("b", "r", confidence=7.0)
        by_input = {t.input_text: t.confidence for t in _all_tickets(obs_with_tmp_db)}
        assert by_input == {"a": 0.0, "b": 1.0}


class TestHighValueTransferGuard:
    """COMP-004: transfers above thresholds.high_value_amount are escalated, not executed."""

    def test_threshold_read_from_yaml(self):
        assert COMPLIANCE_CONFIG["thresholds"]["high_value_amount"] == 10000.0

    def test_transfer_over_limit_is_escalated(self, banking_tools):
        db = banking_tools
        result = data_tools.transfer_money("acc1", "acc2", 15000.0, "Car purchase")

        assert "not executed" in result
        assert "COMP-004" in result

        # No money moved, no transactions recorded
        user = IAMUser("user1", UserRole.USER)
        assert db.get_account(user, "acc1").balance == 50000.0
        assert db.get_account(user, "acc2").balance == 100.0
        assert db.get_account_transactions(user, "acc1", days=30) == []

        # A pending ticket carries the transfer details
        tickets = _all_tickets(db)
        assert len(tickets) == 1
        ticket = tickets[0]
        assert ticket.status == "pending"
        assert ticket.user_id == "user1"
        assert ticket.id in result
        assert ticket.metadata["type"] == "high_value_transfer"
        assert ticket.metadata["rule_id"] == "COMP-004"
        assert ticket.metadata["amount"] == 15000.0

    def test_transfer_at_limit_executes(self, banking_tools):
        db = banking_tools
        result = data_tools.transfer_money("acc1", "acc2", 10000.0)

        assert "Transfer successful" in result
        user = IAMUser("user1", UserRole.USER)
        assert db.get_account(user, "acc1").balance == 40000.0
        assert db.get_account(user, "acc2").balance == 10100.0
        assert _all_tickets(db) == []

    def test_limit_follows_config(self, banking_tools, monkeypatch):
        monkeypatch.setitem(COMPLIANCE_CONFIG["thresholds"], "high_value_amount", 50.0)
        result = data_tools.transfer_money("acc1", "acc2", 60.0)
        assert "not executed" in result
        assert len(_all_tickets(banking_tools)) == 1


class TestFraudReportMetadata:
    """report_fraud's metadata is persisted on the ticket."""

    def test_fraud_report_metadata_stored(self, banking_tools, monkeypatch):
        db = banking_tools
        monkeypatch.setattr(escalation_pkg, "EscalationQueue", lambda *a, **k: EscalationQueue(db))

        result = data_tools.report_fraud("acc1", "Unknown charge")

        assert "Ticket ID" in result
        tickets = _all_tickets(db)
        assert len(tickets) == 1
        assert tickets[0].metadata == {"account_id": "acc1", "type": "fraud_report"}


class TestCustomComplianceRules:
    """GOOGLE_COMPLIANCE_RULES are appended to the agent instruction."""

    def test_no_rules_leaves_instruction_unchanged(self):
        from scope.prompt import ROUTER_INSTRUCTIONS, build_instruction
        assert build_instruction([]) == ROUTER_INSTRUCTIONS
        assert build_instruction(None) == ROUTER_INSTRUCTIONS

    def test_rules_appended(self):
        from scope.compliance import transform_rules
        from scope.prompt import ROUTER_INSTRUCTIONS, build_instruction
        instruction = build_instruction(transform_rules(["Do not discuss competitors"]))
        assert instruction.startswith(ROUTER_INSTRUCTIONS)
        assert "COMPLIANCE PRINCIPLES:" in instruction
        assert "1. PRINCIPLE: Do not discuss competitors" in instruction

    def test_agent_uses_build_instruction(self):
        from scope.agent import policy, root_agent
        from scope.prompt import build_instruction
        assert root_agent.instruction == build_instruction(policy.compliance.transformed_rules)
