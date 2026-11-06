"""Tests that the agent-facing banking tools enforce IAM as the current user.

Each test runs against a temporary SQLite database and mocked loggers, so
nothing is written to scope/data/storage/banking.db or the audit log files.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from scope.data import tools
from scope.data.database import Database
from scope.data.models import Account, AccountType, Transaction, TransactionType
from scope.iam import (
    User as IAMUser,
    UserRole,
    Permission,
    AccessDeniedException,
    ROLE_PERMISSIONS,
    parse_role,
    get_role_description,
    get_all_role_descriptions,
)


@pytest.fixture
def db(tmp_path):
    """Temporary database: user1 owns acc001, user2 owns acc002."""
    database = Database(str(tmp_path / "test.db"))
    for account_id, owner in [("acc001", "user1"), ("acc002", "user2")]:
        database.create_account(Account(
            account_id=account_id,
            user_id=owner,
            account_type=AccountType.CHECKING,
            balance=100.0,
        ))
        database.create_transaction(Transaction(
            transaction_id=f"txn_{account_id}",
            account_id=account_id,
            transaction_type=TransactionType.DEPOSIT,
            amount=50.0,
            description=f"Deposit to {account_id}",
        ))
    return database


@pytest.fixture
def env(db, monkeypatch):
    """Point the banking tools at the temp DB and mock config/loggers."""
    cfg = SimpleNamespace(
        IAM_CURRENT_USER_ID="user1",
        IAM_CURRENT_USER_ROLE="USER",
        IAM_CURRENT_USER_NAME="Test User",
    )
    audit = MagicMock()
    compliance = MagicMock()
    monkeypatch.setattr(tools, "db", db)
    monkeypatch.setattr(tools, "config", cfg)
    monkeypatch.setattr(tools, "audit_logger", audit)
    monkeypatch.setattr(tools, "compliance_logger", compliance)

    def act_as(user_id, role):
        cfg.IAM_CURRENT_USER_ID = user_id
        cfg.IAM_CURRENT_USER_ROLE = role

    return SimpleNamespace(db=db, audit=audit, compliance=compliance, act_as=act_as)


def all_tickets(db):
    return db.get_escalations(IAMUser("admin1", UserRole.ADMIN))


class TestParseRole:
    """parse_role accepts any casing and rejects unknown roles."""

    @pytest.mark.parametrize("raw,expected", [
        ("USER", UserRole.USER),
        ("staff", UserRole.STAFF),
        (" Admin ", UserRole.ADMIN),
        ("system", UserRole.SYSTEM),
        (UserRole.STAFF, UserRole.STAFF),
    ])
    def test_parses_case_insensitively(self, raw, expected):
        assert parse_role(raw) == expected

    def test_unknown_role_raises(self):
        with pytest.raises(ValueError):
            parse_role("superuser")

    def test_current_user_accepts_lowercase_role(self, env):
        env.act_as("staff1", "staff")
        assert tools.get_current_user().role == UserRole.STAFF

    @patch("scope.observability_tools.EscalationQueue")
    @patch("scope.observability_tools.audit_logger")
    @patch("scope.observability_tools.config")
    def test_resolve_ticket_accepts_lowercase_role(self, mock_config, mock_logger, mock_queue):
        from scope.observability_tools import resolve_escalation_ticket

        mock_config.IAM_CURRENT_USER_ID = "staff1"
        mock_config.IAM_CURRENT_USER_ROLE = "staff"
        mock_config.IAM_CURRENT_USER_NAME = "Staff"
        mock_queue.return_value.resolve_ticket.return_value = True
        assert "resolved successfully" in resolve_escalation_ticket("t1", "done")


class TestRoleDescriptions:
    """Role descriptions fed to prompts match ROLE_PERMISSIONS."""

    def test_all_roles_described(self):
        text = get_all_role_descriptions()
        for role in UserRole:
            assert f"**{role.name}** role" in text

    def test_resolve_mentioned_only_for_roles_that_can_resolve(self):
        for role in (UserRole.USER, UserRole.STAFF, UserRole.ADMIN):
            can_resolve = Permission.RESOLVE_ESCALATIONS in ROLE_PERMISSIONS[role]
            assert ("resolv" in get_role_description(role)) == can_resolve


class TestTransactionHistoryIAM:
    """get_transaction_history always acts as the current user."""

    def test_user_reads_own_transactions(self, env):
        result = tools.get_transaction_history("acc001")
        assert "Deposit to acc001" in result
        env.audit.log_transaction_query.assert_called_once_with(
            user_id="user1", account_id="acc001", days=30
        )

    def test_user_cannot_read_other_users_transactions_by_passing_their_id(self, env):
        result = tools.get_transaction_history("acc002", user_id="user2")
        assert "Deposit to acc002" not in result
        assert "Error accessing transactions" in result
        env.audit.log_transaction_query.assert_not_called()
        # The failure is logged against the real caller, not the victim
        failure = env.audit.log_event.call_args.kwargs
        assert failure["user_id"] == "user1"
        assert failure["success"] is False

    def test_user_cannot_read_other_users_transactions_without_user_id(self, env):
        result = tools.get_transaction_history("acc002")
        assert "Deposit to acc002" not in result
        assert "Error accessing transactions" in result

    def test_staff_reads_customer_transactions_as_staff(self, env):
        env.act_as("staff1", "STAFF")
        result = tools.get_transaction_history("acc002", user_id="user2")
        assert "Deposit to acc002" in result
        # Audit records the staff member as the actor
        env.audit.log_transaction_query.assert_called_once_with(
            user_id="staff1", account_id="acc002", days=30
        )

    def test_staff_user_id_must_match_account_owner(self, env):
        env.act_as("staff1", "STAFF")
        result = tools.get_transaction_history("acc002", user_id="user1")
        assert "does not belong to user user1" in result
        assert "Deposit to acc002" not in result

    def test_transactions_require_view_transactions_permission(self, db):
        no_txn_perms = {UserRole.USER: {Permission.VIEW_ACCOUNTS}}
        with patch.dict(ROLE_PERMISSIONS, no_txn_perms):
            with pytest.raises(AccessDeniedException):
                db.get_account_transactions(IAMUser("user1", UserRole.USER), "acc001")


class TestUserAccountsIAM:

    def test_user_cannot_list_other_users_accounts(self, env):
        result = tools.get_user_accounts(user_id="user2")
        assert "acc002" not in result
        assert "Error accessing accounts" in result

    def test_staff_can_list_customer_accounts(self, env):
        env.act_as("staff1", "staff")
        result = tools.get_user_accounts(user_id="user2")
        assert "acc002" in result


class TestReportFraudIAM:
    """report_fraud checks account ownership before filing a ticket."""

    def test_user_reports_fraud_on_own_account(self, env):
        result = tools.report_fraud("acc001", "Unknown charge")
        assert "Fraud report submitted" in result
        tickets = all_tickets(env.db)
        assert len(tickets) == 1
        assert tickets[0].user_id == "user1"

    def test_user_cannot_report_fraud_on_other_users_account(self, env):
        result = tools.report_fraud("acc002", "Unknown charge")
        assert "Error submitting fraud report" in result
        assert all_tickets(env.db) == []

    def test_user_cannot_file_for_another_user(self, env):
        result = tools.report_fraud("acc002", "Unknown charge", user_id="user2")
        assert "Error submitting fraud report" in result
        assert all_tickets(env.db) == []
        assert env.audit.log_event.call_args.kwargs["user_id"] == "user1"

    def test_unknown_account_is_rejected(self, env):
        result = tools.report_fraud("acc999", "Unknown charge")
        assert "not found" in result
        assert all_tickets(env.db) == []

    def test_staff_files_for_customer(self, env):
        env.act_as("staff1", "STAFF")
        result = tools.report_fraud("acc002", "Customer called in", user_id="user2")
        assert "Fraud report submitted" in result
        tickets = all_tickets(env.db)
        assert len(tickets) == 1
        # Ticket belongs to the account owner; audit records the staff actor
        assert tickets[0].user_id == "user2"
        details = env.audit.log_event.call_args.kwargs
        assert details["user_id"] == "staff1"
        assert details["details"]["account_owner"] == "user2"

    def test_staff_user_id_must_match_account_owner(self, env):
        env.act_as("staff1", "STAFF")
        result = tools.report_fraud("acc002", "Customer called in", user_id="user1")
        assert "does not belong to user user1" in result
        assert all_tickets(env.db) == []
