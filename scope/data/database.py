"""Database operations for banking application.

This module provides database access with IAM-protected queries.
Uses SQLite for development, can be migrated to PostgreSQL for production.
"""

import sqlite3
import json
import math
from contextlib import closing
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, TYPE_CHECKING
from datetime import datetime, timedelta
import uuid

from .models import User, Account, Transaction, AccountType, TransactionType
from ..iam import User as IAMUser, AccessControl, Permission, AccessDeniedException

if TYPE_CHECKING:
    from ..escalation.models import EscalationTicket


def _parse_metadata(raw: Optional[str]) -> Optional[Dict[str, Any]]:
    """Parse an escalation's stored metadata JSON.

    Returns the dict, or None if the column is empty, not valid JSON, or
    not a JSON object, so one malformed row cannot break reading the queue.
    """
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


class Database:
    """Database manager with IAM-protected operations.

    Methods given an `iam_user` check its role: `get_account`,
    `get_user_accounts` (only when one is passed) and
    `get_account_transactions` also check account ownership,
    `get_escalations` limits callers without VIEW_ALL_ESCALATIONS to their
    own tickets, and `resolve_escalation` checks the role only. The write
    helpers (`create_*`, `update_account`, `transfer_funds`) and `get_user`
    do no IAM checks; the write helpers are called by the seed script and
    from inside tools (the banking tools call them only after their own
    checks), and `get_user` only by the seed script.

    Every method opens its own connection and closes it even if a query
    raises, so a failed call cannot leave the database locked.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize database connection.
        
        Args:
            db_path: Path to SQLite database. If None, uses default location.
        """
        if db_path is None:
            data_dir = Path(__file__).parent / "storage"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "banking.db")
        
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """Initialize database schema."""
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
        
            # Users table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    phone TEXT,
                    created_at TEXT NOT NULL
                )
            """)
        
            # Accounts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    account_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    account_type TEXT NOT NULL,
                    balance REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
        
            # Transactions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    description TEXT,
                    timestamp TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'completed',
                    from_account_id TEXT,
                    to_account_id TEXT,
                    FOREIGN KEY (account_id) REFERENCES accounts(account_id)
                )
            """)
        
            # Escalations table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS escalations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    input_text TEXT NOT NULL,
                    agent_reasoning TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    resolved_at TEXT,
                    resolved_by TEXT,
                    resolution TEXT,
                    metadata TEXT
                )
            """)
        
            # Indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_escalations_user ON escalations(user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_escalations_status ON escalations(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_escalations_created ON escalations(created_at)")
        
            conn.commit()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    # User operations
    
    def create_user(self, user: User) -> str:
        """Create a new user.
        
        Args:
            user: User model
            
        Returns:
            User ID
        """
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
        
            cursor.execute("""
                INSERT INTO users (user_id, name, email, phone, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (user.user_id, user.name, user.email, user.phone, user.created_at.isoformat()))
        
            conn.commit()
        return user.user_id
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID.
        
        Args:
            user_id: User ID
            
        Returns:
            User model or None
        """
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
        
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
        
        if not row:
            return None
        
        # Get user's accounts
        accounts = self.get_user_accounts(user_id)
        account_ids = [acc.account_id for acc in accounts]
        
        return User(
            user_id=row["user_id"],
            name=row["name"],
            email=row["email"],
            phone=row["phone"],
            account_ids=account_ids,
            created_at=datetime.fromisoformat(row["created_at"])
        )
    
    # Account operations
    
    def create_account(self, account: Account) -> str:
        """Create a new account.
        
        Args:
            account: Account model
            
        Returns:
            Account ID
        """
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
        
            cursor.execute("""
                INSERT INTO accounts (account_id, user_id, account_type, balance, currency, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                account.account_id,
                account.user_id,
                account.account_type.value,
                account.balance,
                account.currency,
                account.status,
                account.created_at.isoformat()
            ))
        
            conn.commit()
        return account.account_id
    
    def update_account(self, account: Account) -> bool:
        """Update an existing account.
        
        Args:
            account: Account model with updated values
            
        Returns:
            True if successful
        """
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
        
            cursor.execute("""
                UPDATE accounts 
                SET balance = ?,
                    status = ?
                WHERE account_id = ?
            """, (
                account.balance,
                account.status,
                account.account_id
            ))
        
            conn.commit()
            success = cursor.rowcount > 0
        return success
    
    def get_account(self, iam_user: IAMUser, account_id: str) -> Optional[Account]:
        """Get account by ID (IAM-protected).
        
        Args:
            iam_user: IAM user making the request
            account_id: Account ID
            
        Returns:
            Account model or None
            
        Raises:
            AccessDeniedException: If user lacks permission
        """
        # Check permission
        AccessControl.check_permission(iam_user, Permission.VIEW_ACCOUNTS)
        
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
        
            cursor.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,))
            row = cursor.fetchone()
        
        if not row:
            return None
        
        # Users can only view their own accounts
        if iam_user.role.value == "user" and row["user_id"] != iam_user.user_id:
            raise AccessDeniedException(
                f"User {iam_user.user_id} cannot access account {account_id}"
            )
        
        return Account(
            account_id=row["account_id"],
            user_id=row["user_id"],
            account_type=AccountType(row["account_type"]),
            balance=row["balance"],
            currency=row["currency"],
            status=row["status"],
            created_at=datetime.fromisoformat(row["created_at"])
        )
    
    def get_user_accounts(self, user_id: str, iam_user: Optional[IAMUser] = None) -> List[Account]:
        """Get all accounts for a user.
        
        Args:
            user_id: User ID
            iam_user: IAM user making the request (optional for internal use)
            
        Returns:
            List of Account models
            
        Raises:
            AccessDeniedException: If user lacks permission
        """
        if iam_user:
            # Check permission
            AccessControl.check_permission(iam_user, Permission.VIEW_ACCOUNTS)
            
            # Users can only view their own accounts
            if iam_user.role.value == "user" and user_id != iam_user.user_id:
                raise AccessDeniedException(
                    f"User {iam_user.user_id} cannot access accounts for {user_id}"
                )
        
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
        
            cursor.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,))
            rows = cursor.fetchall()
        
        return [
            Account(
                account_id=row["account_id"],
                user_id=row["user_id"],
                account_type=AccountType(row["account_type"]),
                balance=row["balance"],
                currency=row["currency"],
                status=row["status"],
                created_at=datetime.fromisoformat(row["created_at"])
            )
            for row in rows
        ]
    
    # Transaction operations
    
    def create_transaction(self, transaction: Transaction) -> str:
        """Create a new transaction.
        
        Args:
            transaction: Transaction model
            
        Returns:
            Transaction ID
        """
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()

            self._insert_transaction(cursor, transaction)

            conn.commit()
        return transaction.transaction_id

    @staticmethod
    def _insert_transaction(cursor: sqlite3.Cursor, transaction: Transaction) -> None:
        """Insert one transaction row using an open cursor (no commit)."""
        cursor.execute("""
            INSERT INTO transactions
            (transaction_id, account_id, transaction_type, amount, currency,
             description, timestamp, status, from_account_id, to_account_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            transaction.transaction_id,
            transaction.account_id,
            transaction.transaction_type.value,
            transaction.amount,
            transaction.currency,
            transaction.description,
            transaction.timestamp.isoformat(),
            transaction.status,
            transaction.from_account_id,
            transaction.to_account_id
        ))

    def transfer_funds(
        self,
        from_account_id: str,
        to_account_id: str,
        amount: float,
        transactions: List[Transaction]
    ) -> Tuple[float, float]:
        """Move money between two accounts in a single SQLite transaction.

        The debit, the credit and the given transaction rows are committed
        together or not at all, so a failure part-way can neither lose nor
        create money. The debit is conditional (``balance >= amount``) and
        both updates are relative to the stored balance, so the funds check
        and the write cannot be split by a concurrent transfer. Resulting
        balances are rounded to cents.

        Args:
            from_account_id: Account to debit
            to_account_id: Account to credit (must differ from the source)
            amount: Positive, finite amount
            transactions: Transaction rows to record with the transfer

        Returns:
            (new source balance, new destination balance)

        Raises:
            ValueError: Invalid amount, same account, unknown account or
                insufficient funds (nothing is written)
        """
        if from_account_id == to_account_id:
            raise ValueError("Source and destination accounts must be different")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)):
            raise ValueError("Transfer amount must be a number")
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError("Transfer amount must be a positive, finite number")

        with closing(self._get_connection()) as conn:
            try:
                cursor = conn.cursor()
                # Take the write lock before reading/updating balances
                cursor.execute("BEGIN IMMEDIATE")

                cursor.execute("SELECT 1 FROM accounts WHERE account_id = ?", (to_account_id,))
                if cursor.fetchone() is None:
                    raise ValueError(f"Account {to_account_id} not found")

                cursor.execute("""
                    UPDATE accounts
                    SET balance = ROUND(balance - ?, 2)
                    WHERE account_id = ? AND balance >= ?
                """, (amount, from_account_id, amount))
                if cursor.rowcount != 1:
                    cursor.execute("SELECT 1 FROM accounts WHERE account_id = ?", (from_account_id,))
                    if cursor.fetchone() is None:
                        raise ValueError(f"Account {from_account_id} not found")
                    raise ValueError(f"Insufficient funds in account {from_account_id}")

                cursor.execute("""
                    UPDATE accounts
                    SET balance = ROUND(balance + ?, 2)
                    WHERE account_id = ?
                """, (amount, to_account_id))

                for transaction in transactions:
                    self._insert_transaction(cursor, transaction)

                cursor.execute(
                    "SELECT account_id, balance FROM accounts WHERE account_id IN (?, ?)",
                    (from_account_id, to_account_id)
                )
                balances = {row["account_id"]: row["balance"] for row in cursor.fetchall()}

                conn.commit()
            except BaseException:
                conn.rollback()
                raise

        return balances[from_account_id], balances[to_account_id]

    def get_account_transactions(
        self, 
        iam_user: IAMUser, 
        account_id: str, 
        days: int = 30
    ) -> List[Transaction]:
        """Get transactions for an account (IAM-protected).
        
        Args:
            iam_user: IAM user making the request
            account_id: Account ID
            days: Number of days to look back
            
        Returns:
            List of Transaction models
            
        Raises:
            AccessDeniedException: If user lacks permission
        """
        # Check permission
        AccessControl.check_permission(iam_user, Permission.VIEW_TRANSACTIONS)

        # Verify user can access this account
        account = self.get_account(iam_user, account_id)
        if not account:
            return []
        
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
        
            since = (datetime.now() - timedelta(days=days)).isoformat()
            cursor.execute("""
                SELECT * FROM transactions 
                WHERE account_id = ? AND timestamp >= ?
                ORDER BY timestamp DESC
            """, (account_id, since))
        
            rows = cursor.fetchall()
        
        return [
            Transaction(
                transaction_id=row["transaction_id"],
                account_id=row["account_id"],
                transaction_type=TransactionType(row["transaction_type"]),
                amount=row["amount"],
                currency=row["currency"],
                description=row["description"],
                timestamp=datetime.fromisoformat(row["timestamp"]),
                status=row["status"],
                from_account_id=row["from_account_id"],
                to_account_id=row["to_account_id"]
            )
            for row in rows
        ]
    
    # Escalation operations
    
    def create_escalation(self, ticket: "EscalationTicket") -> str:
        """Create a new escalation ticket.
        
        Args:
            ticket: EscalationTicket model
            
        Returns:
            Ticket ID
        """
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
        
            cursor.execute("""
                INSERT INTO escalations 
                (id, user_id, input_text, agent_reasoning, confidence, created_at, 
                 status, resolved_at, resolved_by, resolution, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticket.id,
                ticket.user_id,
                ticket.input_text,
                ticket.agent_reasoning,
                ticket.confidence,
                ticket.created_at.isoformat(),
                ticket.status,
                ticket.resolved_at.isoformat() if ticket.resolved_at else None,
                ticket.resolved_by,
                ticket.resolution,
                json.dumps(ticket.metadata) if ticket.metadata else None
            ))
        
            conn.commit()
        return ticket.id
    
    def get_escalations(
        self,
        iam_user: IAMUser,
        status: Optional[str] = None
    ) -> List["EscalationTicket"]:
        """Get escalation tickets (IAM-protected).
        
        Args:
            iam_user: IAM user making the request
            status: Filter by status (optional)
            
        Returns:
            List of EscalationTicket models
            
        Raises:
            AccessDeniedException: If user lacks permission
        """
        from ..escalation.models import EscalationTicket
        
        # Check permission
        AccessControl.check_permission(iam_user, Permission.VIEW_OWN_ESCALATIONS)
        
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
        
            # Build query based on permission
            if not iam_user.has_permission(Permission.VIEW_ALL_ESCALATIONS):
                # Without VIEW_ALL_ESCALATIONS (USER), only own escalations
                if status:
                    cursor.execute(
                        "SELECT * FROM escalations WHERE user_id = ? AND status = ? ORDER BY created_at DESC",
                        (iam_user.user_id, status)
                    )
                else:
                    cursor.execute(
                        "SELECT * FROM escalations WHERE user_id = ? ORDER BY created_at DESC",
                        (iam_user.user_id,)
                    )
            else:
                # STAFF, ADMIN and SYSTEM (VIEW_ALL_ESCALATIONS) see all escalations
                if status:
                    cursor.execute(
                        "SELECT * FROM escalations WHERE status = ? ORDER BY created_at DESC",
                        (status,)
                    )
                else:
                    cursor.execute("SELECT * FROM escalations ORDER BY created_at DESC")
        
            rows = cursor.fetchall()
        
        return [
            EscalationTicket(
                id=row["id"],
                user_id=row["user_id"],
                input_text=row["input_text"],
                agent_reasoning=row["agent_reasoning"],
                confidence=row["confidence"],
                created_at=datetime.fromisoformat(row["created_at"]),
                status=row["status"],
                resolution_timestamp=datetime.fromisoformat(row["resolved_at"]) if row["resolved_at"] else None,
                resolved_by=row["resolved_by"],
                resolution_note=row["resolution"],
                metadata=_parse_metadata(row["metadata"])
            )
            for row in rows
        ]
    
    def resolve_escalation(
        self,
        iam_user: IAMUser,
        ticket_id: str,
        resolution: str
    ) -> bool:
        """Resolve an escalation ticket (IAM-protected).
        
        Args:
            iam_user: IAM user resolving the ticket
            ticket_id: Ticket ID
            resolution: Resolution text
            
        Returns:
            True if successful
            
        Raises:
            AccessDeniedException: If user lacks permission
        """
        # Check permission
        AccessControl.check_permission(iam_user, Permission.RESOLVE_ESCALATIONS)
        
        with closing(self._get_connection()) as conn:
            cursor = conn.cursor()
        
            cursor.execute("""
                UPDATE escalations 
                SET status = 'resolved',
                    resolved_at = ?,
                    resolved_by = ?,
                    resolution = ?
                WHERE id = ?
            """, (
                datetime.now().isoformat(),
                iam_user.user_id,
                resolution,
                ticket_id
            ))
        
            conn.commit()
            success = cursor.rowcount > 0
        
        return success
