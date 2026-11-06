"""Banking tools for the SCOPE agent.

These tools allow the agent to interact with the banking database
with IAM-protected access control. Every tool runs as the configured
current user; a `user_id` argument only names a target customer, and is
checked against the caller's role.
"""

import threading
from typing import Optional
from datetime import datetime

from ..data import Database, User as DataUser, Account, Transaction, AccountType, TransactionType
from .database import validate_transfer_amount
from ..iam import User as IAMUser, UserRole, AccessControl, AccessDeniedException, Permission, parse_role
from ..logging import get_audit_logger, get_compliance_logger, AuditEventType
from ..config import Config

class _DefaultDatabase:
    """The default banking Database, created on first use rather than at import.

    Importing this module therefore does not create or open
    scope/data/storage/banking.db. The first access to a public attribute
    (e.g. ``db.get_account`` in a tool call) creates ``Database()``; every
    public attribute is then forwarded to it.
    """

    def __init__(self):
        self._database: Optional[Database] = None
        self._lock = threading.Lock()

    def __getattr__(self, name):
        # Only public Database attributes are forwarded. Private and dunder
        # lookups (e.g. mock.patch probing ``__func__`` / ``_is_coroutine``)
        # must not open the database.
        if name.startswith("_"):
            raise AttributeError(name)
        with self._lock:
            if self._database is None:
                self._database = Database()
        return getattr(self._database, name)


# Initialize database (lazily), loggers, and config
db = _DefaultDatabase()
audit_logger = get_audit_logger()
compliance_logger = get_compliance_logger()
config = Config()


def get_current_user() -> IAMUser:
    """Get current user from config (role parsed case-insensitively)."""
    return IAMUser(
        user_id=config.IAM_CURRENT_USER_ID,
        role=parse_role(config.IAM_CURRENT_USER_ROLE),
        name=config.IAM_CURRENT_USER_NAME
    )


def check_target_user(iam_user: IAMUser, target_user_id: Optional[str]) -> None:
    """Check that the caller may act on another user's data.

    USER may only target themselves; STAFF, ADMIN and SYSTEM may target any
    customer (the same rule the database applies to account access).

    Args:
        iam_user: Current user making the request
        target_user_id: User the request is about (None means the caller)

    Raises:
        AccessDeniedException: If a USER targets someone else
    """
    if target_user_id and target_user_id != iam_user.user_id and iam_user.role == UserRole.USER:
        raise AccessDeniedException(
            f"User {iam_user.user_id} cannot access data for {target_user_id}"
        )


def account_unavailable(account_id: str) -> str:
    """Reply for an account the caller cannot see, whether or not it exists."""
    return f"Account {account_id} not found or not accessible."


def lookup_account(
    iam_user: IAMUser,
    account_id: str,
    event_type: AuditEventType,
    action: str,
) -> Optional[Account]:
    """Get an account without revealing to the caller whether it exists.

    Returns None both when the account does not exist and when the caller may
    not access it (e.g. a USER asking for another customer's account), so the
    caller's reply cannot be used to probe which account ids exist. The precise
    reason is written to the audit log.

    Args:
        iam_user: Current user making the request
        account_id: Account to look up
        event_type: Audit event type for a failed lookup
        action: Audit action name for a failed lookup

    Returns:
        The account, or None if it is missing or not accessible
    """
    try:
        account = db.get_account(iam_user, account_id)
        reason = None if account else f"Account {account_id} does not exist"
    except AccessDeniedException as e:
        account, reason = None, str(e)

    if reason:
        audit_logger.log_event(
            event_type=event_type,
            user_id=iam_user.user_id,
            action=action,
            details={"account_id": account_id},
            success=False,
            error=reason
        )
    return account


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
        
        # Get account (IAM-protected; missing and inaccessible look the same)
        account = lookup_account(
            iam_user, account_id, AuditEventType.ACCOUNT_ACCESS, "view_balance_failed"
        )
        if not account:
            return account_unavailable(account_id)
        
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
            user_id=config.IAM_CURRENT_USER_ID,
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
        user_id: Optional owner of the account (STAFF/ADMIN looking up a
            customer). The call always runs as the current user from config.

    Returns:
        Transaction history as a formatted string
    """
    try:
        # Always act as the current user; user_id is only the target owner
        iam_user = get_current_user()
        check_target_user(iam_user, user_id)

        # Get account (IAM-protected: USER may only access own accounts;
        # missing and inaccessible look the same)
        account = lookup_account(
            iam_user, account_id, AuditEventType.TRANSACTION_QUERY, "view_transactions_failed"
        )
        if not account:
            return account_unavailable(account_id)
        if user_id and account.user_id != user_id:
            return f"Account {account_id} does not belong to user {user_id}."

        # Get transactions (IAM-protected)
        transactions = db.get_account_transactions(iam_user, account_id, days=days)

        if not transactions:
            return f"No transactions found for account {account_id} in the last {days} days."

        # Log transaction query (actor is the current user, not the target)
        audit_logger.log_transaction_query(
            user_id=iam_user.user_id,
            account_id=account_id,
            days=days
        )

        # Log for PCI-DSS compliance
        compliance_logger.log_pci_data_access(
            user_id=iam_user.user_id,
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
            user_id=config.IAM_CURRENT_USER_ID,
            action="view_transactions_failed",
            details={"account_id": account_id, "target_user": user_id},
            success=False,
            error=str(e)
        )
        return f"Error accessing transactions: {str(e)}"


def get_user_accounts(user_id: Optional[str] = None) -> str:
    """Get all accounts for a customer.
    
    Args:
        user_id: Optional customer to look up (STAFF/ADMIN only; defaults to
            the current user from config)

    Returns:
        List of accounts as a formatted string
    """
    try:
        # Always act as the current user; user_id is only the target
        current_iam_user = get_current_user()
        check_target_user(current_iam_user, user_id)
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
            user_id=config.IAM_CURRENT_USER_ID,
            action="list_accounts_failed",
            details={"target_user": user_id},
            success=False,
            error=str(e)
        )
        return f"Error accessing accounts: {str(e)}"


def report_fraud(account_id: str, description: str, user_id: Optional[str] = None) -> str:
    """Report potential fraud or suspicious activity.
    
    Args:
        account_id: The account ID with suspicious activity
        description: Description of the suspicious activity
        user_id: Optional owner of the account (STAFF/ADMIN filing for a
            customer). The call always runs as the current user from config.

    Returns:
        Confirmation message with ticket ID
    """
    try:
        from ..escalation import EscalationQueue, EscalationTicket

        # Always act as the current user; user_id is only the target owner
        iam_user = get_current_user()
        check_target_user(iam_user, user_id)

        # Ownership check (IAM-protected: USER may only report on own accounts;
        # missing and inaccessible look the same)
        account = lookup_account(
            iam_user, account_id, AuditEventType.ESCALATION_CREATED, "fraud_report_failed"
        )
        if not account:
            return account_unavailable(account_id)
        if user_id and account.user_id != user_id:
            return f"Account {account_id} does not belong to user {user_id}."

        # Create escalation ticket for the account owner, so it appears in
        # their own escalations even when STAFF/ADMIN filed it
        queue = EscalationQueue(db)
        ticket = EscalationTicket(
            user_id=account.user_id,
            input_text=f"Fraud report for account {account_id}: {description}",
            agent_reasoning="Fraud report - requires immediate human review",
            confidence=1.0,
            metadata={"account_id": account_id, "type": "fraud_report"}
        )

        queue.add_ticket(ticket)

        # Log fraud report (actor is the current user, not the account owner)
        audit_logger.log_event(
            event_type=AuditEventType.ESCALATION_CREATED,
            user_id=iam_user.user_id,
            action="fraud_report",
            details={
                "account_id": account_id,
                "account_owner": account.user_id,
                "ticket_id": ticket.id,
                "description": description[:200]
            }
        )

        # Log as SOC2 incident
        compliance_logger.log_soc2_incident(
            user_id=iam_user.user_id,
            incident_type="fraud_report",
            severity="high",
            description=f"Account {account_id}: {description[:200]}"
        )
        
        return (
            f"Fraud report submitted successfully. Ticket ID: {ticket.id}\n\n"
            f"Our fraud prevention team will review this report within 24 hours. "
            f"If you need immediate assistance, please call our fraud hotline at 1-800-FRAUD-HELP."
        )
        
    except Exception as e:
        audit_logger.log_event(
            event_type=AuditEventType.ESCALATION_CREATED,
            user_id=config.IAM_CURRENT_USER_ID,
            action="fraud_report_failed",
            details={"account_id": account_id, "target_user": user_id},
            success=False,
            error=str(e)
        )
        return f"Error submitting fraud report: {str(e)}"


def transfer_money(from_account_id: str, to_account_id: str, amount: float, description: Optional[str] = None) -> str:
    """Transfer money between accounts (USER can only transfer between their own accounts).
    
    Transfers above the COMP-004 high-value limit (compliance_rules.yaml
    ``thresholds.high_value_amount``) are not executed; an escalation ticket
    is created for human review instead. Same-account transfers and amounts
    that are not positive, finite numbers with at most 2 decimal places are
    rejected before any database access. The debit, credit and transaction
    records are written in one database transaction.

    Args:
        from_account_id: Source account ID
        to_account_id: Destination account ID (must differ from the source)
        amount: Amount to transfer (positive, at most 2 decimal places)
        description: Optional description for the transfer
        
    Returns:
        Confirmation message with transaction details
    """
    try:
        import uuid
        
        # Get current user
        iam_user = get_current_user()
        user_id = iam_user.user_id
        
        # Validate amount: a real number (not bool/str), finite, positive and
        # in whole cents. Amounts with more than 2 decimal places are rejected
        # rather than silently rounded. Database.transfer_funds applies the
        # same check.
        try:
            amount = validate_transfer_amount(amount)
        except ValueError as e:
            return f"❌ {e}"

        # A transfer to the same account would credit money that was never debited
        if from_account_id == to_account_id:
            return "❌ Source and destination accounts must be different."

        # Get both accounts to verify ownership and balances (missing and
        # inaccessible accounts look the same)
        from_account = lookup_account(
            iam_user, from_account_id, AuditEventType.TRANSACTION_QUERY, "transfer_failed"
        )
        to_account = lookup_account(
            iam_user, to_account_id, AuditEventType.TRANSACTION_QUERY, "transfer_failed"
        )
        
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
        
        # COMP-004: transfers above the high-value limit (compliance_rules.yaml
        # thresholds.high_value_amount) are not executed - escalate to a human
        from ..rules import COMPLIANCE_CONFIG
        from ..escalation import EscalationQueue, EscalationTicket
        high_value_amount = float(COMPLIANCE_CONFIG["thresholds"]["high_value_amount"])
        if amount > high_value_amount:
            ticket = EscalationTicket(
                user_id=user_id,
                input_text=(
                    f"Transfer ${amount:.2f} from {from_account_id} to {to_account_id}"
                    + (f": {description}" if description else "")
                ),
                agent_reasoning=(
                    f"COMP-004: transfer exceeds the high-value limit of ${high_value_amount:,.2f} "
                    f"- not executed, requires human review"
                ),
                confidence=1.0,  # Deterministic rule, not a model judgement
                metadata={
                    "type": "high_value_transfer",
                    "rule_id": "COMP-004",
                    "from_account_id": from_account_id,
                    "to_account_id": to_account_id,
                    "amount": amount,
                    "description": description,
                }
            )
            ticket_id = EscalationQueue(db).add_ticket(ticket)
            
            audit_logger.log_event(
                event_type=AuditEventType.ESCALATION_CREATED,
                user_id=user_id,
                action="transfer_escalated_high_value",
                details={
                    "from_account": from_account_id,
                    "to_account": to_account_id,
                    "amount": amount,
                    "high_value_amount": high_value_amount,
                    "ticket_id": ticket_id
                }
            )
            
            return (
                f"⏸️ Transfer not executed: ${amount:.2f} exceeds the ${high_value_amount:,.2f} "
                f"high-value limit (COMP-004).\n\n"
                f"Escalation ticket {ticket_id} has been created for staff review. "
                f"No money has been moved.\n\n"
                f"The review does not carry out the transfer. Requesting it again here "
                f"creates another ticket rather than moving money; after approval, "
                f"contact the bank to complete it."
            )
        
        # Create transaction ID
        transaction_id = str(uuid.uuid4())

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
        
        # Debit, credit and both transaction rows commit atomically (or not at
        # all); the database re-checks funds under its write lock, so a balance
        # that changed since it was read above refuses the transfer here
        try:
            from_balance, to_balance = db.transfer_funds(
                from_account_id, to_account_id, amount, [from_txn, to_txn]
            )
        except ValueError as e:
            audit_logger.log_event(
                event_type=AuditEventType.TRANSACTION_QUERY,
                user_id=user_id,
                action="transfer_failed",
                success=False,
                error=str(e)
            )
            return f"❌ Transfer not executed: {e}. No money has been moved."

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
            f"From: {from_account_id} ({from_account.account_type.value}) - New balance: ${from_balance:.2f}\n"
            f"To: {to_account_id} ({to_account.account_type.value}) - New balance: ${to_balance:.2f}\n"
            f"Transaction ID: {transaction_id}\n"
            f"Description: {transfer_desc}"
        )
        
    except Exception as e:
        audit_logger.log_event(
            event_type=AuditEventType.TRANSACTION_QUERY,
            user_id=config.IAM_CURRENT_USER_ID,
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
