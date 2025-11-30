import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from prime_guardrails.data.seed_database import seed_database

def reset_demo():
    print("🔄 Resetting PRIME Demo Environment...")
    
    # 1. Delete Databases
    # Banking DB
    db_path = project_root / "prime_guardrails/data/storage/banking.db"
    if db_path.exists():
        print(f"🗑️  Deleting {db_path}...")
        os.remove(db_path)
    
    # Escalation DB
    escalation_db_path = project_root / "prime_guardrails/escalation/data/escalations.db"
    if escalation_db_path.exists():
        print(f"🗑️  Deleting {escalation_db_path}...")
        os.remove(escalation_db_path)

    # 2. Re-seed Database
    print("\n🌱 Re-seeding database...")
    seed_database()
    
    print("\n✅ Demo environment reset complete!")

if __name__ == "__main__":
    reset_demo()
