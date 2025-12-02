"""Seed the banking database with sample data.

This script creates:
- A default user with ID "user" (matching ADK web UI default)
- Sample checking and savings accounts
- Realistic transaction history
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
import uuid

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scope.data import Database, User, Account, Transaction, AccountType, TransactionType


def seed_database():
    """Seed the database with sample data."""
    db = Database()
    
    print("🌱 Seeding banking database...")
    
    # Check if data already exists
    existing_user = db.get_user("user")
    if existing_user:
        print("ℹ️  Database already seeded. Skipping...")
        print(f"\n📊 Current state:")
        print(f"   User: {existing_user.user_id} ({existing_user.name})")
        
        # Show existing accounts
        accounts = db.get_user_accounts("user")
        total_balance = sum(acc.balance for acc in accounts)
        for acc in accounts:
            print(f"   {acc.account_type.value.title()}: {acc.account_id} - ${acc.balance:.2f}")
        print(f"   Total Balance: ${total_balance:.2f}")
        return
    
    # Create default user (matching ADK web UI default)
    user = User(
        user_id="user",
        name="Alice Johnson",
        email="alice@example.com",
        phone="+1-555-0123",
        account_ids=[]  # Will be populated
    )
    
    try:
        db.create_user(user)
        print(f"✅ Created user: {user.user_id} ({user.name})")
    except Exception as e:
        print(f"❌ Error creating user: {e}")
        return
    
    # Create checking account
    checking = Account(
        account_id="acc001",
        user_id="user",
        account_type=AccountType.CHECKING,
        balance=2547.83,
        currency="USD",
        status="active"
    )
    
    try:
        db.create_account(checking)
        print(f"✅ Created checking account: {checking.account_id} (${checking.balance:.2f})")
    except Exception as e:
        print(f"⚠️  Checking account already exists or error: {e}")
    
    # Create savings account
    savings = Account(
        account_id="acc002",
        user_id="user",
        account_type=AccountType.SAVINGS,
        balance=15234.56,
        currency="USD",
        status="active"
    )
    
    try:
        db.create_account(savings)
        print(f"✅ Created savings account: {savings.account_id} (${savings.balance:.2f})")
    except Exception as e:
        print(f"⚠️  Savings account already exists or error: {e}")
    
    # Create sample transactions for checking account
    transactions = [
        # Recent transactions (last 7 days)
        Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id="acc001",
            transaction_type=TransactionType.DEPOSIT,
            amount=2500.00,
            description="Paycheck deposit - Acme Corp",
            timestamp=datetime.now() - timedelta(days=2),
            status="completed"
        ),
        Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id="acc001",
            transaction_type=TransactionType.WITHDRAWAL,
            amount=85.42,
            description="Grocery Store",
            timestamp=datetime.now() - timedelta(days=3),
            status="completed"
        ),
        Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id="acc001",
            transaction_type=TransactionType.PAYMENT,
            amount=45.00,
            description="Internet bill",
            timestamp=datetime.now() - timedelta(days=5),
            status="completed"
        ),
        # Older transactions (last 30 days)
        Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id="acc001",
            transaction_type=TransactionType.WITHDRAWAL,
            amount=120.00,
            description="ATM Withdrawal",
            timestamp=datetime.now() - timedelta(days=10),
            status="completed"
        ),
        Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id="acc001",
            transaction_type=TransactionType.PAYMENT,
            amount=1200.00,
            description="Rent payment",
            timestamp=datetime.now() - timedelta(days=15),
            status="completed"
        ),
        Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id="acc001",
            transaction_type=TransactionType.DEPOSIT,
            amount=2500.00,
            description="Paycheck deposit - Acme Corp",
            timestamp=datetime.now() - timedelta(days=16),
            status="completed"
        ),
        Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id="acc001",
            transaction_type=TransactionType.WITHDRAWAL,
            amount=67.89,
            description="Restaurant",
            timestamp=datetime.now() - timedelta(days=18),
            status="completed"
        ),
    ]
    
    # Create sample transactions for savings account
    savings_transactions = [
        Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id="acc002",
            transaction_type=TransactionType.DEPOSIT,
            amount=500.00,
            description="Monthly savings transfer",
            timestamp=datetime.now() - timedelta(days=15),
            status="completed"
        ),
        Transaction(
            transaction_id=str(uuid.uuid4()),
            account_id="acc002",
            transaction_type=TransactionType.DEPOSIT,
            amount=12.34,
            description="Interest payment",
            timestamp=datetime.now() - timedelta(days=1),
            status="completed"
        ),
    ]
    
    # Add all transactions
    all_transactions = transactions + savings_transactions
    created_count = 0
    
    for txn in all_transactions:
        try:
            db.create_transaction(txn)
            created_count += 1
        except Exception as e:
            print(f"⚠️  Transaction already exists or error: {e}")
    
    print(f"✅ Created {created_count} transactions")
    
    print("\n✨ Database seeding complete!")
    print(f"\n📊 Summary:")
    print(f"   User: {user.user_id} ({user.name})")
    print(f"   Checking: {checking.account_id} - ${checking.balance:.2f}")
    print(f"   Savings: {savings.account_id} - ${savings.balance:.2f}")
    print(f"   Total Balance: ${checking.balance + savings.balance:.2f}")
    print(f"   Transactions: {created_count}")


if __name__ == "__main__":
    seed_database()
