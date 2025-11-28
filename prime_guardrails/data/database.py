"""Database operations for banking application.

This module provides database access with IAM-protected queries.
Uses SQLite for development, can be migrated to PostgreSQL for production.
"""

import sqlite3
from pathlib import Path
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

from .models import User, Account, Transaction, AccountType, TransactionType
from ..iam import User as IAMUser, AccessControl, Permission, AccessDeniedException


class Database:
    """Database manager with IAM-protected operations."""
    
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
        conn = sqlite3.connect(self.db_path)
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
        
        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_accounts_user ON accounts(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_timestamp ON transactions(timestamp)")
        
        conn.commit()
        conn.close()
    
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
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO users (user_id, name, email, phone, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user.user_id, user.name, user.email, user.phone, user.created_at.isoformat()))
        
        conn.commit()
        conn.close()
        return user.user_id
    
    def get_user(self, user_id: str) -> Optional[User]:
        """Get user by ID.
        
        Args:
            user_id: User ID
            
        Returns:
            User model or None
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
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
        conn = self._get_connection()
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
        conn.close()
        return account.account_id
    
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
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM accounts WHERE account_id = ?", (account_id,))
        row = cursor.fetchone()
        conn.close()
        
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
    
    def get_user_accounts(self, user_id: str) -> List[Account]:
        """Get all accounts for a user.
        
        Args:
            user_id: User ID
            
        Returns:
            List of Account models
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM accounts WHERE user_id = ?", (user_id,))
        rows = cursor.fetchall()
        conn.close()
        
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
        conn = self._get_connection()
        cursor = conn.cursor()
        
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
        
        conn.commit()
        conn.close()
        return transaction.transaction_id
    
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
        # Verify user can access this account
        account = self.get_account(iam_user, account_id)
        if not account:
            return []
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        since = (datetime.now() - timedelta(days=days)).isoformat()
        cursor.execute("""
            SELECT * FROM transactions 
            WHERE account_id = ? AND timestamp >= ?
            ORDER BY timestamp DESC
        """, (account_id, since))
        
        rows = cursor.fetchall()
        conn.close()
        
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
