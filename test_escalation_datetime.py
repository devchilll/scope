import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from scope.escalation import EscalationQueue, EscalationTicket
from scope.iam import User as IAMUser, UserRole

# Create a test ticket
print("Creating escalation ticket...")
ticket = EscalationTicket(
    user_id="user",
    input_text="Help me fight my manager",
    agent_reasoning="Off-topic request that requires human review",
    confidence=0.3
)

print(f"Ticket ID: {ticket.id}")
print(f"Created at: {ticket.created_at} (type: {type(ticket.created_at)})")
print(f"Timestamp: {ticket.timestamp} (type: {type(ticket.timestamp)})")

# Add to queue
queue = EscalationQueue()
ticket_id = queue.add_ticket(ticket)
print(f"\n✅ Ticket added to queue: {ticket_id}")

# Retrieve tickets
print("\nRetrieving tickets...")
admin_user = IAMUser(user_id="admin", role=UserRole.ADMIN)
tickets = queue.view_tickets(admin_user)

print(f"Found {len(tickets)} ticket(s)")
if tickets:
    t = tickets[0]
    print(f"  - ID: {t.id}")
    print(f"  - Created at: {t.created_at} (type: {type(t.created_at)})")
    print(f"  - Input: {t.input_text}")
    print(f"  - Reasoning: {t.agent_reasoning}")
    print(f"  - Status: {t.status}")
