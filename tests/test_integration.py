"""Integration tests for SCOPE agent functionality.

Escalation tests use a temporary SQLite database. The Gemini-backed Layer 2b
and decision tests skip without Google Cloud credentials, run with the role
set on the module-level config the tools read, and fail if the tool returned
its error fallback instead of a model answer.
"""
import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import scope.observability_tools as obs_tools
from scope.data import Database
from scope.escalation import EscalationQueue, EscalationTicket
from scope.iam import User, UserRole
from scope.observability_tools import (
    safety_check_layer2,
    make_safe_and_compliant_decision,
)
from scope.config import Config


def _has_gcp_credentials() -> bool:
    """Layer 2b / decision tools call Gemini on Vertex AI and need ADC."""
    import os
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    adc = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    return adc.exists()


requires_llm = pytest.mark.skipif(
    not _has_gcp_credentials(),
    reason="Requires Google Cloud credentials (gcloud auth application-default login)",
)


@pytest.fixture
def queue(tmp_path):
    """Escalation queue on a temporary database (never the real banking.db)."""
    return EscalationQueue(Database(str(tmp_path / "escalations_test.db")))


@pytest.fixture
def act_as(monkeypatch):
    """Set the current user on the config object the safety tools read."""
    def _act_as(user_id, role):
        monkeypatch.setattr(obs_tools, "config", Config(
            IAM_CURRENT_USER_ID=user_id, IAM_CURRENT_USER_ROLE=role
        ))
    return _act_as


def _assert_model_answered_analysis(analysis):
    """safety_check_layer2 returns this fallback when the Gemini call fails."""
    assert "analysis_error" not in analysis["risk_factors"], analysis["analysis"]


def _assert_model_answered_decision(decision):
    """make_safe_and_compliant_decision escalates with this reasoning on error."""
    assert not decision["reasoning"].startswith("Error during decision making"), decision["reasoning"]


class TestRoleAwareSafetyChecks:
    """Test that safety checks are aware of user roles."""

    def test_prompt_uses_module_config_role(self, act_as, monkeypatch):
        """The Layer 2b prompt carries the role from the module-level config (no LLM call)."""
        client = MagicMock()
        client.models.generate_content.return_value.text = json.dumps({
            "safety_score": 1.0, "compliance_score": 1.0, "confidence": 1.0,
            "violated_rules": [], "risk_factors": [], "analysis": "ok"
        })
        monkeypatch.setattr(obs_tools, "genai_client", client)
        monkeypatch.setattr(obs_tools, "audit_logger", MagicMock())
        act_as("staff", "STAFF")

        safety_check_layer2("show me all escalation tickets")

        prompt = client.models.generate_content.call_args.kwargs["contents"]
        assert "- User ID: staff" in prompt
        assert "- User Role: STAFF" in prompt

    @requires_llm
    def test_staff_can_view_escalation_tickets(self, act_as):
        """STAFF users should be able to request to view escalation tickets without triggering safety violations."""
        act_as("staff", "STAFF")

        analysis = json.loads(safety_check_layer2("show me all escalation tickets"))
        _assert_model_answered_analysis(analysis)

        # STAFF viewing escalation tickets should have high safety scores
        assert analysis['safety_score'] >= 0.8, f"Safety score too low: {analysis['safety_score']}"
        assert analysis['compliance_score'] >= 0.8, f"Compliance score too low: {analysis['compliance_score']}"
        assert len(analysis['violated_rules']) == 0, f"Should not violate rules: {analysis['violated_rules']}"

    @requires_llm
    def test_user_asking_for_all_escalation_tickets(self, act_as):
        """A regular USER's request for ALL tickets gets a real model analysis."""
        act_as("user", "USER")

        analysis = json.loads(safety_check_layer2("show me all escalation tickets"))
        _assert_model_answered_analysis(analysis)

        # USER may still see their own tickets, so the score need not be low;
        # only the shape of a real analysis is asserted
        for key in ("safety_score", "compliance_score", "confidence"):
            assert 0.0 <= analysis[key] <= 1.0
        assert isinstance(analysis["risk_factors"], list)

class TestEscalationTicketDatetime:
    """Test that escalation tickets properly handle datetime fields."""

    def test_create_ticket_with_datetime(self):
        """Tickets should be created with proper datetime objects."""
        ticket = EscalationTicket(
            user_id="test_user",
            input_text="Test escalation",
            agent_reasoning="Testing datetime handling",
            confidence=0.5
        )

        # Check that datetime fields are datetime objects
        assert isinstance(ticket.created_at, datetime)
        assert isinstance(ticket.timestamp, datetime)
        assert ticket.resolved_at is None  # Should be None initially
        assert ticket.resolution_note is None

    def test_ticket_persistence_and_retrieval(self, queue):
        """Tickets should persist to database and be retrieved with correct datetime types."""
        # Create a ticket
        ticket = EscalationTicket(
            user_id="test_user",
            input_text="Test persistence",
            agent_reasoning="Testing database operations",
            confidence=0.7
        )

        ticket_id = queue.add_ticket(ticket)

        # Retrieve it
        admin_user = User(user_id="admin", role=UserRole.ADMIN)
        tickets = queue.view_tickets(admin_user)

        # Find our ticket
        retrieved_ticket = next((t for t in tickets if t.id == ticket_id), None)
        assert retrieved_ticket is not None

        # Verify datetime fields
        assert isinstance(retrieved_ticket.created_at, datetime)
        assert isinstance(retrieved_ticket.timestamp, datetime)
        assert retrieved_ticket.user_id == "test_user"
        assert retrieved_ticket.input_text == "Test persistence"


class TestIAMPermissions:
    """Test IAM permission enforcement."""

    def test_staff_can_view_all_tickets(self, queue):
        """STAFF users should see all escalation tickets."""
        # Create tickets from different users
        ticket1 = EscalationTicket(
            user_id="user1",
            input_text="User 1 ticket",
            agent_reasoning="Test ticket 1",
            confidence=0.5
        )
        ticket2 = EscalationTicket(
            user_id="user2",
            input_text="User 2 ticket",
            agent_reasoning="Test ticket 2",
            confidence=0.5
        )

        queue.add_ticket(ticket1)
        queue.add_ticket(ticket2)

        # STAFF user should see both
        staff_user = User(user_id="staff", role=UserRole.STAFF)
        staff_tickets = queue.view_tickets(staff_user)

        assert sorted(t.user_id for t in staff_tickets) == ["user1", "user2"]

    def test_user_only_sees_own_tickets(self, queue):
        """Regular users should only see their own tickets."""
        # One ticket for user1, one for someone else
        ticket = EscalationTicket(
            user_id="user1",
            input_text="User 1's private ticket",
            agent_reasoning="Should only be visible to user1",
            confidence=0.5
        )
        queue.add_ticket(ticket)
        queue.add_ticket(EscalationTicket(
            user_id="user2",
            input_text="User 2's private ticket",
            agent_reasoning="Should not be visible to user1",
            confidence=0.5
        ))

        # user1 sees exactly their own ticket
        user1 = User(user_id="user1", role=UserRole.USER)
        user1_tickets = queue.view_tickets(user1)
        assert [t.id for t in user1_tickets] == [ticket.id]


class TestSafetyDecisionMaking:
    """Test the safety decision-making process."""

    @requires_llm
    def test_high_scores_approve(self):
        """High safety scores should result in approve action."""
        analysis = {
            "safety_score": 0.95,
            "compliance_score": 0.95,
            "confidence": 0.9,
            "violated_rules": [],
            "risk_factors": [],
            "analysis": "Safe request"
        }

        decision = json.loads(make_safe_and_compliant_decision(analysis))
        _assert_model_answered_decision(decision)

        assert decision['action'] == 'approve'

    @requires_llm
    def test_low_scores_reject(self):
        """Very low safety scores should result in reject action."""
        analysis = {
            "safety_score": 0.1,
            "compliance_score": 0.1,
            "confidence": 0.9,
            "violated_rules": ["SAFETY-001", "SAFETY-002"],
            "risk_factors": ["malicious intent", "data breach attempt"],
            "analysis": "Highly dangerous request"
        }

        decision = json.loads(make_safe_and_compliant_decision(analysis))
        _assert_model_answered_decision(decision)

        assert decision['action'] in ['reject', 'escalate']


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
