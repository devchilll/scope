import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from scope.data.database import Database
from scope.data.models import Account, AccountType, Transaction, TransactionType
from scope.iam import User as IAMUser, UserRole, Permission, AccessDeniedException
from scope.observability_tools import view_audit_logs, resolve_escalation_ticket
from scope.data.tools import transfer_money

class TestDatabaseFixes:
    @pytest.fixture
    def db(self, tmp_path):
        db_path = tmp_path / "test.db"
        return Database(str(db_path))

    def test_update_account(self, db):
        # Create account
        account = Account(
            account_id="acc001",
            user_id="user1",
            account_type=AccountType.CHECKING,
            balance=100.0,
            currency="USD",
            status="active",
            created_at=datetime.now()
        )
        db.create_account(account)
        
        # Update account
        account.balance = 200.0
        account.status = "frozen"
        success = db.update_account(account)
        
        assert success is True
        
        # Verify update
        iam_user = IAMUser("user1", UserRole.USER)
        updated = db.get_account(iam_user, "acc001")
        assert updated.balance == 200.0
        assert updated.status == "frozen"

    def test_get_user_accounts_permissions(self, db):
        # Setup data
        account = Account(
            account_id="acc001",
            user_id="user1",
            account_type=AccountType.CHECKING,
            balance=100.0,
            currency="USD",
            status="active",
            created_at=datetime.now()
        )
        db.create_account(account)
        
        # 1. User viewing own accounts - Should Pass
        user1 = IAMUser("user1", UserRole.USER)
        accounts = db.get_user_accounts("user1", user1)
        assert len(accounts) == 1
        assert accounts[0].account_id == "acc001"
        
        # 2. User viewing other's accounts - Should Fail
        user2 = IAMUser("user2", UserRole.USER)
        with pytest.raises(AccessDeniedException):
            db.get_user_accounts("user1", user2)
            
        # 3. Staff viewing user's accounts - Should Pass
        staff = IAMUser("staff1", UserRole.STAFF)
        accounts = db.get_user_accounts("user1", staff)
        assert len(accounts) == 1

class TestObservabilityToolsPermissions:
    @patch('scope.observability_tools.config')
    @patch('scope.observability_tools.audit_logger')
    def test_view_audit_logs_permissions(self, mock_logger, mock_config):
        # 1. Test as USER (Should fail)
        mock_config.IAM_CURRENT_USER_ID = "user1"
        mock_config.IAM_CURRENT_USER_ROLE = "USER"
        mock_config.IAM_CURRENT_USER_NAME = "Test User"
        
        result = view_audit_logs()
        assert "Permission denied" in result
        
        # 2. Test as STAFF (Should pass - though returns 'No audit logs' since mocked)
        mock_config.IAM_CURRENT_USER_ID = "staff1"
        mock_config.IAM_CURRENT_USER_ROLE = "STAFF"
        
        # Mock file reading to avoid actual file system access
        with patch('pathlib.Path.glob', return_value=[]):
            result = view_audit_logs()
            assert "Permission denied" not in result

    @patch('scope.observability_tools.config')
    @patch('scope.observability_tools.audit_logger')
    @patch('scope.observability_tools.EscalationQueue')
    def test_resolve_escalation_permissions(self, mock_queue, mock_logger, mock_config):
        # 1. Test as USER (Should fail)
        mock_config.IAM_CURRENT_USER_ID = "user1"
        mock_config.IAM_CURRENT_USER_ROLE = "USER"
        mock_config.IAM_CURRENT_USER_NAME = "Test User"
        
        result = resolve_escalation_ticket("ticket1", "resolved")
        assert "Permission denied" in result
        
        # 2. Test as STAFF (Should pass)
        mock_config.IAM_CURRENT_USER_ID = "staff1"
        mock_config.IAM_CURRENT_USER_ROLE = "STAFF"
        
        mock_queue_instance = MagicMock()
        mock_queue_instance.resolve_ticket.return_value = True
        mock_queue.return_value = mock_queue_instance
        
        result = resolve_escalation_ticket("ticket1", "resolved")
        assert "Permission denied" not in result
        assert "resolved successfully" in result

class TestTransferMoney:
    @patch('scope.data.tools.db')
    @patch('scope.data.tools.config')
    @patch('scope.data.tools.audit_logger')
    @patch('scope.data.tools.compliance_logger')
    def test_transfer_money_method_call(self, mock_comp, mock_audit, mock_config, mock_db):
        # Setup mocks
        mock_config.IAM_CURRENT_USER_ID = "user1"
        mock_config.IAM_CURRENT_USER_ROLE = "USER"
        mock_config.IAM_CURRENT_USER_NAME = "Test User"
        
        # Mock accounts
        acc1 = MagicMock(user_id="user1", balance=500.0, account_id="acc1")
        acc2 = MagicMock(user_id="user1", balance=100.0, account_id="acc2")
        
        mock_db.get_account.side_effect = [acc1, acc2]
        
        # Call transfer
        result = transfer_money("acc1", "acc2", 100.0)
        
        # Verify db.create_transaction was called (NOT add_transaction)
        assert mock_db.create_transaction.called
        assert mock_db.create_transaction.call_count == 2
        
        # Verify db.update_account was called
        assert mock_db.update_account.called
        assert mock_db.update_account.call_count == 2
        
        assert "Transfer successful" in result
