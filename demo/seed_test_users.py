"""Seed admin and staff users for testing IAM permissions."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from prime_guardrails.data import Database, User, Account, AccountType
from datetime import datetime

def seed_test_users():
    """Seed admin and staff users for testing."""
    db = Database()
    
    print("🌱 Seeding test users (admin and staff)...")
    
    # Create staff user
    staff_user = User(
        user_id="staff",
        name="Bob Smith",
        email="bob.smith@primebank.com",
        phone="+1-555-0456",
        account_ids=[]
    )
    
    try:
        db.create_user(staff_user)
        print(f"✅ Created staff user: {staff_user.user_id} ({staff_user.name})")
    except Exception as e:
        print(f"⚠️  Staff user already exists or error: {e}")
    
    # Create admin user
    admin_user = User(
        user_id="admin",
        name="Carol Admin",
        email="carol.admin@primebank.com",
        phone="+1-555-0789",
        account_ids=[]
    )
    
    try:
        db.create_user(admin_user)
        print(f"✅ Created admin user: {admin_user.user_id} ({admin_user.name})")
    except Exception as e:
        print(f"⚠️  Admin user already exists or error: {e}")
    
    # Create a test account for staff
    staff_account = Account(
        account_id="acc_staff_001",
        user_id="staff",
        account_type=AccountType.CHECKING,
        balance=5000.00,
        currency="USD",
        status="active"
    )
    
    try:
        db.create_account(staff_account)
        print(f"✅ Created staff account: {staff_account.account_id}")
    except Exception as e:
        print(f"⚠️  Staff account already exists or error: {e}")
    
    # Create a test account for admin
    admin_account = Account(
        account_id="acc_admin_001",
        user_id="admin",
        account_type=AccountType.CHECKING,
        balance=10000.00,
        currency="USD",
        status="active"
    )
    
    try:
        db.create_account(admin_account)
        print(f"✅ Created admin account: {admin_account.account_id}")
    except Exception as e:
        print(f"⚠️  Admin account already exists or error: {e}")
    
    print("\n✨ Test users seeded successfully!")
    print("\n📊 Summary:")
    print("  - user (USER role): Alice Johnson")
    print("  - staff (STAFF role): Bob Smith")
    print("  - admin (ADMIN role): Carol Admin")

if __name__ == "__main__":
    seed_test_users()
