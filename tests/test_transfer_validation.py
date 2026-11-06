"""Tests for transfer_money input validation and the atomic database transfer.

Covers: same-account transfers, non-numeric / non-finite / sub-cent amounts,
connections being closed when a query raises (no "database is locked"),
all-or-nothing debit + credit + transaction rows, the in-transaction funds
check, and cent rounding of balances.

All database access uses a temporary SQLite file and loggers are mocked, so
nothing is written to scope/data/storage or scope/logging.
"""

import sqlite3
from datetime import datetime
from unittest.mock import MagicMock

import pytest

import scope.data.tools as data_tools
from scope.config import Config
from scope.data import Database
from scope.data.models import (
    Account, AccountType, Transaction, TransactionType, User as DataUser
)
from scope.iam import User as IAMUser, UserRole


USER = IAMUser("user1", UserRole.USER)


@pytest.fixture
def tmp_db(tmp_path):
    """Temporary banking database: user1 owns acc001 ($100) and acc002 ($50)."""
    db = Database(str(tmp_path / "banking_test.db"))
    db.create_user(DataUser(user_id="user1", name="Test User", email="t@example.com"))
    for acc_id, balance in (("acc001", 100.0), ("acc002", 50.0)):
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


def balances(db):
    return (db.get_account(USER, "acc001").balance, db.get_account(USER, "acc002").balance)


def transaction_count(db):
    return sum(len(db.get_account_transactions(USER, acc, days=30)) for acc in ("acc001", "acc002"))


def assert_not_locked(db):
    """A new writer can take the lock immediately (no connection left open mid-write)."""
    conn = sqlite3.connect(db.db_path, timeout=0)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.rollback()
    finally:
        conn.close()


def _txns(amount, from_id="acc001", to_id="acc002"):
    common = dict(transaction_type=TransactionType.TRANSFER, from_account_id=from_id, to_account_id=to_id)
    return [
        Transaction(transaction_id="t_from", account_id=from_id, amount=-amount, **common),
        Transaction(transaction_id="t_to", account_id=to_id, amount=amount, **common),
    ]


class TestSameAccountTransfer:
    """A transfer to the source account would credit money never debited."""

    def test_same_account_rejected(self, banking_tools):
        db = banking_tools
        result = data_tools.transfer_money("acc001", "acc001", 50.0)

        assert "must be different" in result
        assert balances(db) == (100.0, 50.0)
        assert transaction_count(db) == 0

    def test_database_rejects_same_account(self, tmp_db):
        with pytest.raises(ValueError, match="must be different"):
            tmp_db.transfer_funds("acc001", "acc001", 50.0, _txns(50.0, to_id="acc001"))
        assert balances(tmp_db) == (100.0, 50.0)


class TestAmountValidation:
    """Only positive, finite numbers in whole cents reach the database."""

    @pytest.mark.parametrize("amount", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_rejected(self, banking_tools, monkeypatch, amount):
        db = banking_tools
        db_spy = MagicMock(wraps=db)
        monkeypatch.setattr(data_tools, "db", db_spy)

        result = data_tools.transfer_money("acc001", "acc002", amount)

        assert "finite" in result
        assert not db_spy.method_calls  # rejected before any database access
        assert balances(db) == (100.0, 50.0)
        assert_not_locked(db)

    @pytest.mark.parametrize("amount", ["50", None, True, [50]])
    def test_non_numeric_rejected(self, banking_tools, amount):
        result = data_tools.transfer_money("acc001", "acc002", amount)
        assert "must be a number" in result
        assert balances(banking_tools) == (100.0, 50.0)

    @pytest.mark.parametrize("amount", [0, 0.0, -5.0])
    def test_non_positive_rejected(self, banking_tools, amount):
        result = data_tools.transfer_money("acc001", "acc002", amount)
        assert "greater than zero" in result
        assert balances(banking_tools) == (100.0, 50.0)

    @pytest.mark.parametrize("amount", [10.001, 0.005, 0.1 + 0.2])
    def test_more_than_two_decimals_rejected(self, banking_tools, amount):
        result = data_tools.transfer_money("acc001", "acc002", amount)
        assert "2 decimal places" in result
        assert balances(banking_tools) == (100.0, 50.0)
        assert transaction_count(banking_tools) == 0

    @pytest.mark.parametrize("amount,expected", [
        (10.25, (89.75, 60.25)),
        (10.1, (89.9, 60.1)),
        (10, (90.0, 60.0)),
    ])
    def test_whole_cent_amounts_accepted(self, banking_tools, amount, expected):
        result = data_tools.transfer_money("acc001", "acc002", amount)
        assert "Transfer successful" in result
        assert balances(banking_tools) == expected
        assert transaction_count(banking_tools) == 2

    def test_nan_then_next_call_works(self, banking_tools):
        """A rejected NaN transfer leaves the database usable for the next tool call."""
        data_tools.transfer_money("acc001", "acc002", float("nan"))
        result = data_tools.transfer_money("acc001", "acc002", 25.0)
        assert "Transfer successful" in result
        assert balances(banking_tools) == (75.0, 75.0)


class TestConnectionsClosedOnError:
    """A query that raises must not leave its connection (and write lock) open."""

    def test_failed_update_releases_lock(self, tmp_db):
        account = tmp_db.get_account(USER, "acc001")
        account.balance = float("nan")  # stored as NULL -> NOT NULL constraint fails

        with pytest.raises(sqlite3.IntegrityError):
            tmp_db.update_account(account)

        assert_not_locked(tmp_db)
        assert balances(tmp_db) == (100.0, 50.0)

    def test_failed_insert_releases_lock(self, tmp_db):
        txn = _txns(10.0)[0]
        tmp_db.create_transaction(txn)
        with pytest.raises(sqlite3.IntegrityError):
            tmp_db.create_transaction(txn)  # duplicate primary key

        assert_not_locked(tmp_db)


class TestAtomicTransfer:
    """Debit, credit and transaction rows commit together or not at all."""

    def test_failure_after_debit_rolls_back(self, tmp_db, monkeypatch):
        def fail(*args, **kwargs):
            raise RuntimeError("disk full")
        monkeypatch.setattr(Database, "_insert_transaction", staticmethod(fail))

        with pytest.raises(RuntimeError):
            tmp_db.transfer_funds("acc001", "acc002", 30.0, _txns(30.0))

        assert balances(tmp_db) == (100.0, 50.0)
        assert_not_locked(tmp_db)

    def test_tool_reports_failure_and_moves_nothing(self, banking_tools, monkeypatch):
        def fail(*args, **kwargs):
            raise RuntimeError("disk full")
        monkeypatch.setattr(Database, "_insert_transaction", staticmethod(fail))

        result = data_tools.transfer_money("acc001", "acc002", 30.0)

        assert "Error processing transfer" in result
        assert balances(banking_tools) == (100.0, 50.0)
        assert transaction_count(banking_tools) == 0

    def test_unknown_destination_does_not_debit(self, tmp_db):
        with pytest.raises(ValueError, match="acc999 not found"):
            tmp_db.transfer_funds("acc001", "acc999", 30.0, _txns(30.0, to_id="acc999"))
        assert balances(tmp_db) == (100.0, 50.0)

    def test_funds_checked_inside_transaction(self, tmp_db):
        """A stale balance read cannot overdraw: the debit itself re-checks funds."""
        with pytest.raises(ValueError, match="Insufficient funds"):
            tmp_db.transfer_funds("acc001", "acc002", 100.01, _txns(100.01))
        assert balances(tmp_db) == (100.0, 50.0)
        assert transaction_count(tmp_db) == 0

    def test_success_records_both_rows_and_conserves_total(self, tmp_db):
        new_balances = tmp_db.transfer_funds("acc001", "acc002", 40.0, _txns(40.0))

        assert new_balances == (60.0, 90.0)
        assert balances(tmp_db) == (60.0, 90.0)
        assert sum(balances(tmp_db)) == 150.0
        rows = tmp_db.get_account_transactions(USER, "acc001") + tmp_db.get_account_transactions(USER, "acc002")
        assert sorted(t.amount for t in rows) == [-40.0, 40.0]


class TestCentRounding:
    """Balances are stored rounded to cents, so float error does not accumulate."""

    def test_repeated_small_transfers_stay_exact(self, banking_tools):
        for _ in range(10):
            assert "Transfer successful" in data_tools.transfer_money("acc001", "acc002", 0.1)

        assert balances(banking_tools) == (99.0, 51.0)
