import sys
import os
from pathlib import Path
import json

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from prime_guardrails.observability_tools import (
    safety_check_layer2,
    make_safety_decision,
    list_escalation_tickets,
    create_escalation_ticket
)

def test_tools():
    print("🧪 Testing Observability Tools...")
    
    # 1. Test Safety Check Layer 2
    print("\n1. Testing safety_check_layer2...")
    try:
        analysis_json = safety_check_layer2("I want to check my balance")
        print(f"✅ Analysis result: {analysis_json[:100]}...")
        analysis = json.loads(analysis_json)
    except Exception as e:
        print(f"❌ safety_check_layer2 failed: {e}")
        return

    # 2. Test Make Safety Decision
    print("\n2. Testing make_safety_decision...")
    try:
        decision_json = make_safety_decision(analysis)
        print(f"✅ Decision result: {decision_json}")
    except Exception as e:
        print(f"❌ make_safety_decision failed: {e}")

    # 3. Test List Escalation Tickets
    print("\n3. Testing list_escalation_tickets...")
    try:
        tickets = list_escalation_tickets()
        print(f"✅ Tickets: {tickets}")
    except Exception as e:
        print(f"❌ list_escalation_tickets failed: {e}")

if __name__ == "__main__":
    test_tools()
