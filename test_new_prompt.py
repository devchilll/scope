"""Quick test of the new banking agent prompt."""

from scope.prompt import ROUTER_INSTRUCTIONS

print("=" * 80)
print("NEW BANKING AGENT PROMPT")
print("=" * 80)
print(ROUTER_INSTRUCTIONS[:1000])
print("\n... (truncated)")
print("\n" + "=" * 80)
print("KEY CHANGES:")
print("=" * 80)
print("✅ ROLE: Banking Customer Service Agent (not just safety checker)")
print("✅ CAPABILITIES: Account access, balance checks, transaction history")
print("✅ LIMITATIONS: Cannot create accounts, process transactions")
print("✅ CUSTOMER SERVICE: Professional, empathetic, clear communication")
print("✅ OUTPUT: Includes 'response' field for customer-facing messages")
print("=" * 80)
