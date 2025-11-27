# PRIME: Agentic Safety Framework

**PRIME** (Policy, Risk, Intervention, Monitoring, Evaluation) is a production-ready, multi-modal safety guardrail system for Generative AI applications. Built on Google's Agent Development Kit (ADK), it implements a "Defense in Depth" architecture with **4 core pillars**: Safety, Compliance, IAM, and Escalation.

![PRIME Web UI](example_web_ui.png)
*PRIME agent running in the ADK Web UI*

---

## 🏗️ Architecture Overview

PRIME uses a **layered defense** approach with modular, scalable components:

```
User Input
    ↓
Layer 2a: Fast Safety Checks (ML models or LLM)
    ↓ (if safe)
Layer 2b: LLM Contextual Safety + Compliance
    ↓ (if safe & compliant)
Layer 1: Decision (ALLOW / REFUSE / REWRITE / ESCALATE)
    ↓ (if ESCALATE)
Human Review Queue (Role-based access)
```

### The 4 Pillars

1. **Safety** - Fast ML-based + LLM contextual safety checks
2. **Compliance** - Custom business rules and brand policies
3. **IAM** - Role-based access control (USER, STAFF, ADMIN, SYSTEM)
4. **Escalation** - Human-in-the-loop with SQLite queue

---

## 📦 Project Structure

```
prime_guardrails/
├── safety/              # Pillar 1: Text/Image safety tools
│   ├── __init__.py
│   └── tools.py         # TextSafetyTool, ImageSafetyTool
├── compliance/          # Pillar 2: Business rules
│   ├── __init__.py
│   ├── rules.py         # Rule transformation
│   └── examples.py      # Industry templates
├── iam/                 # Pillar 3: Access control
│   ├── __init__.py
│   ├── roles.py         # UserRole, Permission enums
│   └── acl.py           # AccessControl, User class
├── escalation/          # Pillar 4: Human review queue
│   ├── __init__.py
│   ├── models.py        # EscalationTicket model
│   └── queue.py         # SQLite-based queue
├── config.py            # 4-pillar configuration
├── agent.py             # Main ADK agent
├── callbacks.py         # Layer 2 safety callbacks
├── prompt.py            # Agent instructions
└── tools.py             # Unified imports
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10-3.12
- [uv](https://github.com/astral-sh/uv) package manager
- Google Cloud account with Vertex AI enabled

### Installation

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Authenticate with Google Cloud
gcloud auth login
gcloud auth application-default login
gcloud config set project your-project-id

# Install dependencies
uv sync
```

### Configuration

Create `.env` file:

```bash
# Google Cloud
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# Pillar 1: Safety
GOOGLE_SAFETY_MODE=STRICT
GOOGLE_SAFETY_THRESHOLD_HIGH=0.8
GOOGLE_SAFETY_THRESHOLD_MEDIUM=0.4

# Pillar 2: Compliance
GOOGLE_COMPLIANCE_ENABLED=true
GOOGLE_COMPLIANCE_RULES='["Don't discuss competitors", "No pricing without link"]'

# Pillar 3: IAM
GOOGLE_IAM_ENABLED=true
GOOGLE_IAM_DEFAULT_USER_ROLE=USER

# Pillar 4: Escalation
GOOGLE_ESCALATION_ENABLED=true
GOOGLE_ESCALATION_THRESHOLD=0.6
GOOGLE_ESCALATION_STORAGE_TYPE=sqlite
```

### Run the Agent

```bash
# Web UI (recommended)
uv run adk web

# CLI mode
uv run adk run prime_guardrails
```

---

## 🔐 Pillar 1: Safety

Fast, multi-modal safety checks using ML models or LLM.

### Text Safety
- **Model**: `Falconsai/offensive_speech_detection` (DistilBERT)
- **Detection**: Offensive language, hate speech
- **Latency**: ~50ms

### Image Safety
- **Model**: `Marqo/nsfw-image-detection-384` (Vision Transformer)
- **Detection**: NSFW content
- **Threshold**: Block if score > 0.5

### Configuration
```python
from prime_guardrails.safety import TextSafetyTool, ImageSafetyTool

text_tool = TextSafetyTool()
result = text_tool.check("Your text here")
# Returns: {"is_safe": bool, "risk_category": str, "confidence": float}
```

---

## 📋 Pillar 2: Compliance

Custom business rules enforced by the LLM agent.

### How It Works
1. Define human-readable rules (e.g., "Don't discuss competitors")
2. Rules are transformed at agent initialization
3. Agent consults rules for every decision
4. Violations cite specific rule numbers

### Industry Templates

```python
from prime_guardrails.compliance.examples import (
    CLOTHING_BRAND,      # Retail rules
    HEALTHCARE,          # Medical compliance
    FINANCIAL_SERVICES_RULES,  # Finance regulations
    SAAS_RULES,          # SaaS policies
)
```

### Example Rules
- **Retail**: "Never discuss or compare competitors' products"
- **Healthcare**: "No medical diagnoses; always suggest consulting professionals"
- **Finance**: "Do not provide investment advice or market predictions"

---

## 👥 Pillar 3: IAM (Identity & Access Management)

Role-based access control for the entire system.

### User Roles

| Role | Permissions |
|------|-------------|
| **USER** | Use agent, view own escalations |
| **STAFF** | + View all escalations (read-only) |
| **ADMIN** | + Resolve escalations, modify config |
| **SYSTEM** | All permissions (internal use) |

### Usage Example

```python
from prime_guardrails.iam import User, UserRole, AccessControl

# Create users
user = User("user123", UserRole.USER, "Alice")
staff = User("staff456", UserRole.STAFF, "Bob")
admin = User("admin789", UserRole.ADMIN, "Charlie")

# Check permissions
user.has_permission(Permission.VIEW_OWN_ESCALATIONS)  # True
staff.has_permission(Permission.VIEW_ALL_ESCALATIONS)  # True
admin.has_permission(Permission.RESOLVE_ESCALATIONS)  # True
```

---

## 🎫 Pillar 4: Escalation

Human-in-the-loop review queue with SQLite storage.

### When Escalation Occurs
- Agent confidence < threshold (default: 0.6)
- Edge cases requiring human judgment
- Ambiguous content

### SQLite Queue

```python
from prime_guardrails.escalation import EscalationQueue, EscalationTicket
from prime_guardrails.iam import User, UserRole

queue = EscalationQueue("escalations.db")

# Add ticket (agent)
ticket = EscalationTicket(
    user_id="user123",
    input_text="How do I make fireworks?",
    agent_reasoning="Educational vs dangerous - uncertain",
    confidence=0.55
)
queue.add_ticket(ticket)

# View tickets (role-based)
user = User("user123", UserRole.USER)
my_tickets = queue.view_tickets(user)  # Sees only own tickets

admin = User("admin1", UserRole.ADMIN)
all_tickets = queue.view_tickets(admin)  # Sees all tickets

# Resolve ticket (admin only)
queue.resolve_ticket(
    user=admin,
    ticket_id=ticket.id,
    decision="approved",
    note="Educational purpose confirmed"
)
```

---

## 🧪 Testing

```bash
# Test all features
uv run python test_features.py

# Test IAM/ACL
uv run python test_iam.py
```

**Test Coverage:**
- ✅ Configuration loading (4 pillars)
- ✅ Compliance rule transformation
- ✅ Escalation queue with SQLite
- ✅ Role-based access control
- ✅ Permission enforcement

---

## 📊 Agent Actions

The agent can take 4 actions based on safety + compliance analysis:

| Action | When | Output |
|--------|------|--------|
| **ALLOW** | Safe & compliant | Pass to generator |
| **REFUSE** | Violates policy/rules | Polite refusal + reason |
| **REWRITE** | Unsafe but valid intent | Sanitized version |
| **ESCALATE** | Low confidence | Queue for human review |

### Response Format

```json
{
  "action": "ALLOW|REFUSE|REWRITE|ESCALATE",
  "reasoning": "Brief explanation",
  "violated_rule": "Rule #2",
  "confidence": 0.75,
  "rewritten_content": "..."
}
```

---

## 🔧 Advanced Configuration

### Custom Compliance Rules

```python
from prime_guardrails.config import Config

config = Config(
    COMPLIANCE_RULES=[
        "Never share internal metrics",
        "Redirect pricing questions to sales team",
        "Do not commit to feature timelines"
    ]
)
```

### IAM Settings

```python
config = Config(
    IAM_ENABLED=True,
    IAM_DEFAULT_USER_ROLE="USER",
    IAM_REQUIRE_AUTHENTICATION=True,
    IAM_SESSION_TIMEOUT_MINUTES=30
)
```

### Escalation Settings

```python
config = Config(
    ESCALATION_ENABLED=True,
    ESCALATION_THRESHOLD=0.7,  # Higher = fewer escalations
    ESCALATION_STORAGE_TYPE="sqlite",
    ESCALATION_AUTO_NOTIFY_ADMINS=True
)
```

---

## 📚 Dependencies

- **google-adk** - Agent Development Kit
- **google-cloud-aiplatform** - Vertex AI integration
- **transformers** - ML model pipelines
- **torch** - Deep learning runtime
- **pydantic-settings** - Configuration management
- **pillow** - Image processing
- **SQLite** - Escalation queue storage (built-in)

---

## 🎯 Success Criteria

- ✅ Explicit profanity blocked by ML model (no LLM call)
- ✅ Nuanced harmful requests caught by LLM reasoning
- ✅ Compliance rules enforced with rule citations
- ✅ Role-based access control working
- ✅ Escalation queue with SQLite persistence
- ✅ Multi-modal support (text + images)

---

## 📖 Documentation

- `example_config.py` - Industry-specific configuration templates
- `test_features.py` - Feature testing examples
- `test_iam.py` - IAM/ACL testing examples

---

## 🤝 Contributing

This is a reference implementation of the PRIME framework. Contributions welcome!

---

## 📄 License

Apache-2.0
