"""Banking tools for the PRIME agent.

These tools allow the agent to interact with the banking database
with IAM-protected access control.
"""

from typing import Optional
from datetime import datetime

from ..data import Database, User as DataUser, Account, Transaction, AccountType, TransactionType
from ..iam import User as IAMUser, UserRole, AccessControl, Permission
from ..logging import get_audit_logger, get_compliance_logger, AuditEventType
from ..config import Config

# Initialize database, loggers, and config
db = Database()
audit_logger = get_audit_logger()
compliance_logger = get_compliance_logger()
config = Config()


def get_current_user() -> IAMUser:
    """Get current user from config."""
    return IAMUser(
        user_id=config.IAM_CURRENT_USER_ID,
        role=UserRole[config.IAM_CURRENT_USER_ROLE],
        name=config.IAM_CURRENT_USER_NAME
    )


def get_account_balance(account_id: str) -> str:
    """Get the current balance for a customer's account.
    
    Args:
        account_id: The account ID to check
        
    Returns:
        Account balance information as a formatted string
    """
    try:
        # Get current user from config
        iam_user = get_current_user()
        user_id = iam_user.user_id
        
        # Get account (IAM-protected)
        account = db.get_account(iam_user, account_id)
        
        if not account:
            return f"Account {account_id} not found."
        
        # Log account access for audit
        audit_logger.log_account_access(
            user_id=user_id,
            account_id=account_id,
            operation="view_balance"
        )
        
        # Log for PCI-DSS compliance
        compliance_logger.log_pci_data_access(
            user_id=user_id,
            data_type="account",
            account_id=account_id,
            operation="read"
        )
        
        return f"Account {account_id} ({account.account_type.value}): ${account.balance:.2f} {account.currency}"
        
    except Exception as e:
        audit_logger.log_event(
            event_type=AuditEventType.ACCOUNT_ACCESS,
            user_id=user_id,
            action="view_balance_failed",
            success=False,
            error=str(e)
        )
        return f"Error accessing account: {str(e)}"


def get_transaction_history(account_id: str, days: int = 30, user_id: Optional[str] = None) -> str:
    """Get recent transaction history for an account.
    
    Args:
        account_id: The account ID
        days: Number of days to look back (default: 30)
        user_id: Optional user ID (defaults to current user from config)
        
    Returns:
        Transaction history as a formatted string
    """
    try:
        # Get current user from config if user_id not provided
        if user_id is None:
            iam_user = get_current_user()
            user_id = iam_user.user_id
        else:
            iam_user = IAMUser(user_id, UserRole.USER, user_id)
        
        # Get transactions (IAM-protected)
        transactions = db.get_account_transactions(iam_user, account_id, days=days)
        
        if not transactions:
            return f"No transactions found for account {account_id} in the last {days} days."
        
        # Log transaction query
        audit_logger.log_transaction_query(
            user_id=user_id,
            account_id=account_id,
            days=days
        )
        
        # Log for PCI-DSS compliance
        compliance_logger.log_pci_data_access(
            user_id=user_id,
            data_type="transaction",
            account_id=account_id,
            operation="read"
        )
        
        # Format transactions
        result = f"Recent transactions for account {account_id} (last {days} days):\n\n"
        for txn in transactions[:10]:  # Limit to 10 most recent
            result += f"- {txn.timestamp.strftime('%Y-%m-%d %H:%M')}: "
            result += f"{txn.transaction_type.value.upper()} ${txn.amount:.2f} "
            if txn.description:
                result += f"({txn.description})"
            result += "\n"
        
        if len(transactions) > 10:
            result += f"\n... and {len(transactions) - 10} more transactions"
        
        return result
        
    except Exception as e:
        audit_logger.log_event(
            event_type=AuditEventType.TRANSACTION_QUERY,
            user_id=user_id,
            action="view_transactions_failed",
            success=False,
            error=str(e)
        )
        return f"Error accessing transactions: {str(e)}"


def get_user_accounts(user_id: Optional[str] = None) -> str:
    """Get all accounts for a customer.
    
    Args:
        user_id: Optional user ID (defaults to current user from config)
    
    Returns:
        List of accounts as a formatted string
    """
    try:
        # Get current user from config if user_id not provided
        current_iam_user = get_current_user()
        is_current_user = (user_id is None)
        
        if user_id is None:
            user_id = current_iam_user.user_id
        
        # Get user's accounts (pass IAM user for permission check)
        accounts = db.get_user_accounts(user_id, current_iam_user)
        
        if not accounts:
            return f"No accounts found for user {user_id}."
        
        # Log account access
        audit_logger.log_event(
            event_type=AuditEventType.ACCOUNT_ACCESS,
            user_id=current_iam_user.user_id,
            action="list_accounts",
            details={"account_count": len(accounts), "target_user": user_id}
        )
        
        # Format accounts with appropriate wording
        if is_current_user:
            result = f"Your accounts:\n\n"
        else:
            result = f"Accounts for user '{user_id}':\n\n"
        
        total_balance = 0.0
        
        for acc in accounts:
            result += f"- {acc.account_id} ({acc.account_type.value}): "
            result += f"${acc.balance:.2f} {acc.currency}\n"
            total_balance += acc.balance
        
        result += f"\nTotal balance across all accounts: ${total_balance:.2f}"
        
        return result
        
    except Exception as e:
        audit_logger.log_event(
            event_type=AuditEventType.ACCOUNT_ACCESS,
            user_id=get_current_user().user_id,
            action="list_accounts_failed",
            success=False,
            error=str(e)
        )
        return f"Error accessing accounts: {str(e)}"


def report_fraud(account_id: str, description: str, user_id: Optional[str] = None) -> str:
    """Report potential fraud or suspicious activity.
    
    Args:
        account_id: The account ID with suspicious activity
        description: Description of the suspicious activity
        user_id: Optional user ID (defaults to current user from config)
        
    Returns:
        Confirmation message with ticket ID
    """
    try:
        from ..escalation import EscalationQueue, EscalationTicket
        
        # Get current user from config if user_id not provided
        if user_id is None:
            iam_user = get_current_user()
            user_id = iam_user.user_id
        
        # Create escalation ticket
        queue = EscalationQueue()
        ticket = EscalationTicket(
            user_id=user_id,
            input_text=f"Fraud report for account {account_id}: {description}",
            agent_reasoning="Fraud report - requires immediate human review",
            confidence=1.0,
            metadata={"account_id": account_id, "type": "fraud_report"}
        )
        
        queue.add_ticket(ticket)
        
        # Log fraud report
        audit_logger.log_event(
            event_type=AuditEventType.ESCALATION_CREATED,
            user_id=user_id,
            action="fraud_report",
            details={
                "account_id": account_id,
                "ticket_id": ticket.id,
                "description": description[:200]
            }
        )
        
        # Log as SOC2 incident
        compliance_logger.log_soc2_incident(
            user_id=user_id,
            incident_type="fraud_report",
            severity="high",
            description=f"Account {account_id}: {description[:200]}"
        )
        
        return (
            f"Fraud report submitted successfully. Ticket ID: {ticket.id}\n\n"
            f"Our fraud prevention team will review this report within 24 hours. "
            f"Your account has been flagged for monitoring. "
            f"If you need immediate assistance, please call our fraud hotline at 1-800-FRAUD-HELP."
        )
        
    except Exception as e:
        audit_logger.log_event(
            event_type=AuditEventType.ESCALATION_CREATED,
            user_id=user_id,
            action="fraud_report_failed",
            success=False,
            error=str(e)
        )
        return f"Error submitting fraud report: {str(e)}"


def transfer_money(from_account_id: str, to_account_id: str, amount: float, description: Optional[str] = None) -> str:
    """Transfer money between accounts (USER can only transfer between their own accounts).
    
    Args:
        from_account_id: Source account ID
        to_account_id: Destination account ID
        amount: Amount to transfer
        description: Optional description for the transfer
        
    Returns:
        Confirmation message with transaction details
    """
    try:
        import uuid
        
        # Get current user
        iam_user = get_current_user()
        user_id = iam_user.user_id
        
        # Validate amount
        if amount <= 0:
            return "❌ Transfer amount must be greater than zero."
        
        # Get both accounts to verify ownership and balances
        from_account = db.get_account(iam_user, from_account_id)
        to_account = db.get_account(iam_user, to_account_id)
        
        if not from_account:
            return f"❌ Source account {from_account_id} not found or you don't have access to it."
        
        if not to_account:
            return f"❌ Destination account {to_account_id} not found or you don't have access to it."
        
        # Verify both accounts belong to the current user
        if from_account.user_id != user_id:
            audit_logger.log_event(
                event_type=AuditEventType.SAFETY_BLOCK,
                user_id=user_id,
                action="transfer_unauthorized_source",
                success=False,
                details={"from_account": from_account_id, "actual_owner": from_account.user_id}
            )
            return f"❌ You can only transfer from your own accounts."
        
        if to_account.user_id != user_id:
            audit_logger.log_event(
                event_type=AuditEventType.SAFETY_BLOCK,
                user_id=user_id,
                action="transfer_unauthorized_destination",
                success=False,
                details={"to_account": to_account_id, "actual_owner": to_account.user_id}
            )
            return f"❌ You can only transfer to your own accounts."
        
        # Check sufficient balance
        if from_account.balance < amount:
            return f"❌ Insufficient funds. Account {from_account_id} balance: ${from_account.balance:.2f}, requested transfer: ${amount:.2f}"
        
        # Create transaction ID
        transaction_id = str(uuid.uuid4())
        
        # Update balances
        from_account.balance -= amount
        to_account.balance += amount
        
        # Create transaction records
        transfer_desc = description or f"Transfer from {from_account_id} to {to_account_id}"
        
        # Transaction for source account (withdrawal)
        from_txn = Transaction(
            transaction_id=f"{transaction_id}_from",
            account_id=from_account_id,
            transaction_type=TransactionType.TRANSFER,
            amount=-amount,  # Negative for withdrawal
            description=f"Transfer to {to_account_id}: {transfer_desc}",
            from_account_id=from_account_id,
            to_account_id=to_account_id
        )
        
        # Transaction for destination account (deposit)
        to_txn = Transaction(
            transaction_id=f"{transaction_id}_to",
            account_id=to_account_id,
            transaction_type=TransactionType.TRANSFER,
            amount=amount,  # Positive for deposit
            description=f"Transfer from {from_account_id}: {transfer_desc}",
            from_account_id=from_account_id,
            to_account_id=to_account_id
        )
        
        # Save to database (simplified - in real system would be atomic transaction)
        db.update_account(from_account)
        db.update_account(to_account)
        db.create_transaction(from_txn)
        db.create_transaction(to_txn)
        
        # Log for audit
        audit_logger.log_event(
            event_type=AuditEventType.TRANSACTION_QUERY,
            user_id=user_id,
            action="transfer_completed",
            details={
                "from_account": from_account_id,
                "to_account": to_account_id,
                "amount": amount,
                "transaction_id": transaction_id,
                "description": transfer_desc
            }
        )
        
        # Log for PCI-DSS compliance
        compliance_logger.log_pci_data_access(
            user_id=user_id,
            data_type="transaction",
            account_id=from_account_id,
            operation="transfer"
        )
        
        return (
            f"✅ Transfer successful!\n\n"
            f"Amount: ${amount:.2f}\n"
            f"From: {from_account_id} ({from_account.account_type.value}) - New balance: ${from_account.balance:.2f}\n"
            f"To: {to_account_id} ({to_account.account_type.value}) - New balance: ${to_account.balance:.2f}\n"
            f"Transaction ID: {transaction_id}\n"
            f"Description: {transfer_desc}"
        )
        
    except Exception as e:
        audit_logger.log_event(
            event_type=AuditEventType.TRANSACTION_QUERY,
            user_id=get_current_user().user_id,
            action="transfer_failed",
            success=False,
            error=str(e)
        )
        return f"❌ Error processing transfer: {str(e)}"


# Export all tools
BANKING_TOOLS = [
    get_account_balance,
    get_transaction_history,
    get_user_accounts,
    report_fraud,
    transfer_money,
]
