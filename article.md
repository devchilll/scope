# SCOPE: Building Safe, Compliant, and Observable AI Agents

**Abstract**
> SCOPE: Enterprise Agent Governance Framework
> As Large Language Model (LLM) agents are increasingly deployed in mission-critical applications, ensuring their safety, compliance, and observability becomes paramount. We present SCOPE, a comprehensive governance framework designed for regulated environments like banking and healthcare.
> The SCOPE acronym represents our five core pillars:
> S – Safety (Multi-layer Safety Guardrails)
> C – Compliance (Policy-as-Code)
> O – Observability (Measurable Observability & Audit Trails)
> P – Permissions (Identity-Aware Permissions / IAM)
> E – Escalation (Human-in-the-Loop Escalation)
> Built on Google's Agent Development Kit (ADK), SCOPE implements a "Defense in Depth" architecture. It combines fast ML-based classification (~50ms) with LLM-based contextual analysis for robust protection. It features Role-Based Access Control (RBAC) baked into the agent's core and enables hot-patching of business rules without code changes.
> We demonstrate SCOPE's effectiveness through a live Banking Customer Service Agent that handles account inquiries, transactions, and fraud reports while maintaining compliance with PCI-DSS and SOC2 requirements. The framework is open-source and production-ready, offering a practical blueprint for trustworthy agent deployment.

---

## Introduction

Deploying GenAI agents in regulated industries is not just a prompting challenge; it's a systems engineering challenge. The gap between a demo that "works" and a production system that is consistent, secure, and compliant is vast. The **SCOPE framework** addresses this gap by providing a structured approach to agent governance, built on top of **Google's Agent Development Kit (ADK)**.

This article details the technical implementation of SCOPE, targeted at engineering leaders and practitioners building the next generation of enterprise agents.

## Architecture: Defense in Depth

SCOPE implements a "Defense in Depth" strategy, ensuring that safety and compliance are not afterthoughts but are architectural primitives. The system uses a dual-layer approach:
1.  **Fast Layer (Layer 2a)**: High-performance, deterministic checks (ML classifiers, regex, static analysis) running in ~50ms.
2.  **Contextual Layer (Layer 2b)**: LLM-based reasoning for nuance, intent understanding, and complex policy application.

```mermaid
graph TD
    UserInput[User Input] --> FastCheck{Fast Safety Check<br/>(~50ms)}
    FastCheck -- Unsafe --> Block[Block Response]
    FastCheck -- Safe --> AgentRouter[Agent / Router]
    
    subgraph "SCOPE Context"
        IAM[Permissions / ACL]
        Compliance[Compliance Rules]
    end
    
    AgentRouter -- Context --> LLM[LLM Inference]
    IAM --> AgentRouter
    Compliance --> AgentRouter
    
    LLM --> ToolCall{Tool Call?}
    ToolCall -- Yes --> AuditLog[Audit Log]
    AuditLog --> ToolExec[Execute Tool]
    ToolExec --> AgentRouter
    
    ToolCall -- No --> Response[Final Response]
```

## S - Safety: Multi-layer Guardrails

Safety in SCOPE is not a single prompt instruction. It is a pipeline. 

We utilize local, small-model classifiers for immediate threat detection (e.g., offensive speech, PII leakage) before the request even reaches the main LLM. This significantly reduces cost and latency while improving security filtering.

```python
# scope/observability_tools.py
from detoxify import Detoxify

# Load the toxic-bert model for fast safety classification
safety_model = Detoxify('original', device='cpu')  # uses unitary/toxic-bert

def safety_check_layer1(user_input: str) -> str:
    """Layer 1: Fast ML-based safety check (~50ms)."""
    results = safety_model.predict(user_input)
    # Blocks if toxicity > 0.7 or severe_toxicity > 0.5
    ...
```

By decoupling safety from the main reasoning loop, we avoid "jailbreaks" that rely on confusing the model's instruction following.

## C - Compliance: Policy-as-Code

In banking, rules change faster than release cycles. SCOPE treats compliance policy as data, not code. 

Using a **Policy-as-Code** approach, raw business rules (e.g., "Do not discuss competitors") are dynamically transformed into agent principles and injected into the system prompt at runtime.

```python
# scope/compliance/rules.py
def transform_rules(raw_rules: List[str]) -> List[str]:
    """Convert human-readable rules to agent principles."""
    # Transforms "Don't talk about competitors" 
    # into "PRINCIPLE: Do not discuss, compare, or mention competing..."
    return [f"PRINCIPLE: {rule}" for rule in raw_rules]
```

This ensures the agent is always operating with the latest regulatory guidelines without requiring a full redeployment.

## O - Observability: Audit Ready

For SOC2 and PCI-DSS compliance, tracing "what happened" is critical. Standard LLM traces are insufficient. SCOPE's **AuditLogger** captures semantic events:

-   `USER_QUERY`
-   `TOOL_CALL` (with sanitized parameters)
-   `COMPLIANCE_VIOLATION`
-   `SAFETY_BLOCK`
-   `ESCALATION_CREATED`

```json
{
  "timestamp": "2024-10-24T10:00:00.123Z",
  "event_type": "tool_call",
  "user_id": "user_123",
  "action": "tool_call_transfer_funds",
  "details": {
    "amount": "***", 
    "destination": "Acc-987"
  },
  "success": true
}
```

This structured logging enables real-time compliance dashboards and automated forensic analysis.

## P - Permissions: Identity-Aware Agents

Most agents effectively run as "root," executing any tool they have access to. SCOPE creates **Identity-Aware Agents** by integrating Role-Based Access Control (RBAC) directly into the execution flow.

The agent knows *who* is talking to it. A `USER` role can only view their own accounts. A `STAFF` role can view any customer's account but cannot initiate transfers. An `ADMIN` has full system access.

```python
# scope/iam/roles.py
class UserRole(Enum):
    USER = "user"
    STAFF = "staff"
    ADMIN = "admin"

ROLE_PERMISSIONS = {
    UserRole.USER: {Permission.VIEW_OWN_ACCOUNTS},
    UserRole.STAFF: {Permission.VIEW_ALL_ACCOUNTS, Permission.VIEW_LOGS},
}
```

If an agent attempts a tool call unauthorized for the current user, the system intercepts it and throws a permission error, which the agent then explains to the user.

## E - Escalation: Human-in-the-Loop

Deterministic failure is a feature, not a bug. When the agent encounters high-risk scenarios, uncertain intent, or explicit requests for a human, SCOPE provides a standardized **Escalation Protocol**.

The agent can create an `EscalationTicket`, persisting the conversation context and reason for escalation to a database queue. Support staff can then pick up exactly where the agent left off.

```python
# scope/escalation/queue.py
def resolve_ticket(self, agent_user, ticket_id, resolution):
    """Staff resolves the ticket, feeding back into the loop."""
    # ...
```

## Conclusion

SCOPE moves beyond the "naive agent" paradigm to an engineered, governed system. By rigorously applying these five pillars, organizations can unlock the value of GenAI agents while managing the inherent risks.

The Banking Customer Service Agent demo included in the repository showcases these patterns in action, handling live transactions under strict governance rules. We invite you to explore the code and adapt SCOPE for your enterprise needs.
