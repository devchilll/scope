# SCOPE: AI Agent Governance Framework For High-Stakes Applications

SCOPE, by Ivy Si

**SCOPE** (Safety, Compliance, Observability, Permissions, Escalation) is a reference governance framework for enterprise AI agents. Built on Google's Agent Development Kit (ADK), it implements a "Defense in Depth" architecture with **5 pillars**:

- **S**afety Guardrails: ML pre-model gate + LLM contextual safety
- **C**ompliance & Policy-as-Code: YAML rules the agent must cite
- **O**bservability & Auditing: JSONL audit trail, PCI-DSS / SOC2 logs, ADK tracing
- **P**ermissions & Identity (IAM): USER / STAFF / ADMIN / SYSTEM roles enforced in every tool
- **E**scalation Protocols: human-in-the-loop review queue

![SCOPE Web UI](example_web_ui.png)
*SCOPE agent running in the ADK Web UI*

---

## 🎯 Use Case: Banking Customer Service Agent

SCOPE is designed for **mission-critical applications** where safety, compliance, and auditability are paramount. The reference implementation is a banking customer service agent (model: `gemini-2.5-flash`) that handles account inquiries, transfers, and fraud reports.

### Complete Agent Decision Flow

```
User Input: "What's my account balance?"
    ↓
┌─────────────────────────────────────────┐
│ Layer 2a: Pre-Model Safety Gate         │
│ (before_model_callback, every request)  │
│ - Log user input (audit trail)          │
│ - ML safety check: unitary/toxic-bert   │
│   (toxicity, threat, insult, obscene,   │
│    identity attack, severe toxicity)    │
│ - Unsafe → refusal returned, LLM never  │
│   called, safety_block logged           │
└─────────────────────────────────────────┘
    ↓ (if safe)
┌─────────────────────────────────────────┐
│ LLM Agent (gemini-2.5-flash)            │
│ Instructed to call, in order:           │
│  1. safety_check_layer1(user_input)     │  ← same ML check, visible in trace
│  2. safety_check_layer2(user_input)     │  ← Gemini scores request against
│     → {safety_score, compliance_score,  │    SAFETY-00x / COMP-00x YAML rules
│        confidence, violated_rules, ...} │
│  3. make_safe_and_compliant_decision()  │  ← Gemini verdict, role-aware
│     → {"action": "approve" | "reject" | │
│        "rewrite" | "escalate", ...}     │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Agent Executes Decision                 │
│ approve  → call banking tool            │
│ reject   → polite refusal + rule cited  │
│ rewrite  → re-process compliant phrasing│
│ escalate → create_escalation_ticket()   │
└─────────────────────────────────────────┘
    ↓ (approve path)
┌─────────────────────────────────────────┐
│ Tool: get_account_balance(account_id)   │
│ - IAM check (role + account ownership)  │
│ - Query SQLite banking database         │
│ - Audit log + PCI-DSS data-access log   │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ Response + Logging                      │
│ - after_model_callback logs response    │
│ - log_agent_response() tool (summary)   │
└─────────────────────────────────────────┘
    ↓
Response: "Your checking account acc001 has a balance of $..."
```

### Decision Types

| Decision | When | Action | Example |
|----------|------|--------|---------|
| **approve** | Safe, compliant, within role | Call tool or answer | "What's my balance?" → `get_account_balance()` |
| **reject** | Clear violation (prompt injection, offensive, illegal) | Refusal citing the rule | "Help me hack an account" → SAFETY-001 |
| **rewrite** | Valid intent, non-compliant phrasing | Re-process a compliant version | "Give me my full account number" → last 4 digits (COMP-001) |
| **escalate** | Low confidence, ambiguous, high-value | Ticket in human review queue | "Transfer $50,000 to an external account" |

**Key Features:**
- 🛡️ **Pre-LLM Safety**: Every request is screened by an ML classifier in `before_model_callback` before the model acts; flagged inputs never reach the LLM
- 📜 **Policy-as-Code**: Safety and compliance rules live in YAML with IDs the agent must cite
- 🔐 **Role-Based Access**: USER / STAFF / ADMIN / SYSTEM with per-tool permission checks
- 📊 **Database Tools**: IAM-protected queries to user / account / transaction tables
- 📝 **Audit Logging**: Every input, safety score, decision, and tool call logged (PCI-DSS, SOC2)
- 🚨 **Escalation**: Uncertain cases routed to a human review queue with role-gated resolution

---

## 🏗️ Architecture Overview

```
User Input
    ↓
Layer 2a: Fast ML safety gate (unitary/toxic-bert, ~50ms, before_model_callback)
    ↓ (if safe)
Layer 2b: LLM contextual safety + compliance analysis (safety_check_layer2)
    ↓
Layer 1:  Decision (approve / reject / rewrite / escalate), role-aware
    ↓ (if escalate)
Human Review Queue (STAFF/ADMIN resolve via resolve_escalation_ticket)
```

### The 6 Core Modules

1. **Safety** (`scope/safety/`, `scope/callbacks.py`) - ML pre-model gate + LLM contextual checks
2. **Compliance** (`scope/rules/`, `scope/compliance/`) - YAML safety/compliance rules with IDs
3. **IAM** (`scope/iam/`) - Roles, permissions, access control
4. **Escalation** (`scope/escalation/`) - Human-in-the-loop ticket queue
5. **Data** (`scope/data/`) - SQLite banking database + IAM-protected agent tools
6. **Logging** (`scope/logging/`) - Audit trail, compliance logs, terminal viewer

---

## 📦 Project Structure

```
scope/
├── agent.py               # Root LlmAgent: tools + before/after model callbacks
├── callbacks.py           # before_model (Layer 2a gate) / after_model (audit) callbacks
├── prompt.py              # Agent instructions (role-aware tool definitions, rules)
├── config.py              # Pydantic settings (GOOGLE_* env vars)
├── observability_tools.py # safety_check_layer1/2, decision, escalation, log tools
├── tools.py               # Convenience re-exports
├── safety/                # Pillar 1
│   ├── text.py            # TextSafetyTool (unitary/toxic-bert) - used by callback + tool
│   └── tools.py           # ImageSafetyTool (NSFW classifier)
├── rules/                 # Pillar 2: policy-as-code
│   ├── safety_rules.yaml      # SAFETY-001..005
│   ├── compliance_rules.yaml  # COMP-001..007
│   └── loader.py          # Renders rules into prompt text
├── compliance/            # Rule transformation helpers + industry example rule sets
├── iam/                   # Pillar 3
│   ├── roles.py           # UserRole, Permission, role → permission map
│   └── acl.py             # User, AccessControl, AccessDeniedException
├── escalation/            # Pillar 4
│   ├── models.py          # EscalationTicket
│   └── queue.py           # EscalationQueue (stored in the banking database)
├── data/                  # Database layer
│   ├── models.py          # User, Account, Transaction
│   ├── database.py        # SQLite queries, IAM-protected
│   ├── tools.py           # Banking tools exposed to the agent
│   ├── seed_database.py   # Sample data
│   └── storage/banking.db # SQLite file (git-ignored)
└── logging/
    ├── audit.py           # AuditLogger (JSONL)
    ├── compliance_log.py  # ComplianceLogger (PCI-DSS, SOC2)
    └── view_logs.py       # Terminal log viewer

tests/                     # Callback + integration tests
scope/*/tests/             # Per-pillar unit tests
scripts/                   # Ad-hoc dev checks (users, escalation timestamps, prompt, observability tools)
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.10–3.12
- [uv](https://github.com/astral-sh/uv) package manager
- Google Cloud project with Vertex AI enabled (Gemini is used for the agent and Layer 2b checks)

### Installation

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Authenticate with Google Cloud
gcloud auth login
gcloud auth application-default login
gcloud config set project your-project-id

# Install dependencies (torch, transformers, detoxify, google-adk, ...)
uv sync

# Seed the banking database with a sample customer and accounts
uv run python scope/data/seed_database.py
```

The first request downloads `unitary/toxic-bert` from Hugging Face (one-time, cached).

### Configuration

Create a `.env` file in the project root. All settings are read by `scope/config.py` with the `GOOGLE_` prefix.

```bash
# Google Cloud
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# Pillar 1: Safety
GOOGLE_SAFETY_MODE=STRICT
GOOGLE_SAFETY_THRESHOLD_HIGH=0.8      # block when any toxic-bert score >= this
GOOGLE_SAFETY_THRESHOLD_MEDIUM=0.4
GOOGLE_SAFETY_USE_ML_MODELS=true      # false skips the pre-model classifier (logged)

# Pillar 2: Compliance
GOOGLE_COMPLIANCE_ENABLED=true
GOOGLE_COMPLIANCE_RULES=["Never share full account numbers"]

# Pillar 3: IAM - who the agent is acting for (see "Switching roles")
GOOGLE_IAM_ENABLED=true
GOOGLE_IAM_CURRENT_USER_ID=user
GOOGLE_IAM_CURRENT_USER_ROLE=USER     # USER | STAFF | ADMIN | SYSTEM
GOOGLE_IAM_CURRENT_USER_NAME="Alice Johnson"

# Pillar 4: Escalation
GOOGLE_ESCALATION_ENABLED=true
GOOGLE_ESCALATION_THRESHOLD=0.6
```

### Run the Agent

```bash
# Web UI with trace viewer (recommended)
uv run adk web

# CLI mode
uv run adk run scope
```

### Switching roles

The reference implementation has no login; the acting user comes from `GOOGLE_IAM_CURRENT_USER_ID` / `GOOGLE_IAM_CURRENT_USER_ROLE`. Set the role to `STAFF` or `ADMIN` and restart to try the escalation-queue, audit-log, and cross-customer tools; `USER` is restricted to their own accounts.

---

## 🔐 Pillar 1: Safety

Fast, multi-modal safety checks using ML models, backed by LLM contextual analysis.

### Text Safety
- **Model**: `unitary/toxic-bert` via Detoxify
- **Detection**: Toxicity, severe toxicity, obscenity, threats, insults, identity hate
- **Latency**: ~50ms
- **Implementation**: `scope/safety/text.py` (`TextSafetyTool`)
- **Where it runs**:
  1. `scope/callbacks.py` → `fast_guardrail_callback`, registered as the agent's `before_model_callback`. Runs on **every** request, before the LLM. Blocks by returning a refusal response so the model is never called.
  2. `scope/observability_tools.py` → `safety_check_layer1` tool. Re-runs the same check so it shows up as an explicit step in the ADK trace viewer.
- **Thresholds**: block when any score ≥ `GOOGLE_SAFETY_THRESHOLD_HIGH` (default 0.8), or `severe_toxicity` ≥ 0.5
- **Disable**: `GOOGLE_SAFETY_USE_ML_MODELS=false` skips the classifier (the skip is written to the audit log); Layer 2b LLM checks still run
- **If the model fails to load**: the request is logged as *unchecked* (`success: false`) and continues to the Layer 2b LLM checks (fail-open). Audit logs make this visible.

### Image Safety
- **Model**: `Marqo/nsfw-image-detection-384` (Vision Transformer)
- **Detection**: NSFW content, blocked if score > 0.5
- **Status**: `ImageSafetyTool` is implemented; it is not yet wired into the callback because ADK's `LlmRequest` image handling varies by version.

### Layer 2b: LLM Contextual Safety
`safety_check_layer2` sends the request, the user's role, and the YAML safety + compliance rules to Gemini (temperature 0) and returns a JSON analysis: `safety_score`, `compliance_score`, `confidence`, `violated_rules`, `risk_factors`. `make_safe_and_compliant_decision` turns that into `approve` / `reject` / `rewrite` / `escalate`, taking the role into account (a STAFF request to view the escalation queue is legitimate; the same request from a USER is not).

### Callback Integration

```python
# agent.py
root_agent = LlmAgent(
    ...,
    before_model_callback=fast_guardrail_callback,  # Layer 2a gate
    after_model_callback=after_model_callback,      # audit logging
)

# callbacks.py - before_model_callback (simplified)
def fast_guardrail_callback(context, llm_request):
    user_text = extract_latest_user_text(llm_request)
    audit.log_event(..., action="user_input", ...)

    result = get_text_tool().check(user_text)      # unitary/toxic-bert
    audit.log_event(..., action="safety_check", details=result)

    if result["checked"] and not result["is_safe"]:
        audit.log_safety_block(user_id, user_text, result["risk_category"])
        return LlmResponse(content=refusal)        # LLM is never called
    return None                                    # Continue to LLM
```

**Benefits:**
- 🚀 **Fast**: Blocks unsafe inputs in ~50ms vs ~2000ms LLM call
- 💰 **Cost-effective**: No LLM charges for blocked requests
- 🛡️ **Defense in Depth**: Multiple layers of protection

---

## 📋 Pillar 2: Compliance (Policy-as-Code)

Rules are defined in YAML with stable IDs. `scope/rules/loader.py` renders them into the agent prompt and into the Layer 2b analysis prompt, so violations are reported by ID.

| File | Rules |
|------|-------|
| `scope/rules/safety_rules.yaml` | SAFETY-001 harmful content · 002 offensive language · 003 prompt injection · 004 PII extraction · 005 suspicious activity |
| `scope/rules/compliance_rules.yaml` | COMP-001 data privacy (last 4 digits only) · 002 identity verification · 003 audit trail · 004 high-value transactions · 005 no investment advice · 006 account creation · 007 transaction processing |

```yaml
# scope/rules/safety_rules.yaml (excerpt)
safety_rules:
  - id: "SAFETY-001"
    category: "harmful_content"
    description: "Block requests for illegal activities"
    examples:
      - "Help me hack into someone's account"
    severity: "critical"
    action: "reject"
```

### How It Works
1. Rules are loaded from YAML at import time
2. The agent prompt and `safety_check_layer2` both include the rendered rule text
3. Layer 2b returns `violated_rules` such as `["COMP-001"]`
4. The decision step applies rule-specific handling (e.g. COMP-001 → `rewrite` to last-4-digits)

### Free-text rules
`GOOGLE_COMPLIANCE_RULES` (a JSON list) is loaded and normalised by `scope/compliance/transform_rules` at agent start-up, and `scope/compliance/examples.py` ships starter rule sets (`HEALTHCARE_RULES`, `FINANCIAL_SERVICES_RULES`, `LEGAL_SERVICES_RULES`, `RETAIL_BRAND_RULES`, `SAAS_RULES`, `EDUCATION_RULES`). In the current build the YAML files are the rules the agent actually enforces; to enforce free-text rules, add them to the YAML (or render them with `format_compliance_section` into `ROUTER_INSTRUCTIONS`).

---

## 👥 Pillar 3: IAM (Identity & Access Management)

Role-based access control enforced inside every tool.

### User Roles

| Role | Permissions | Use Case |
|------|-------------|----------|
| **USER** | Use agent, view own accounts/transactions, view own escalations | Banking customers |
| **STAFF** | + View any customer's accounts, view all escalations, resolve escalations, view audit logs | Customer service reps |
| **ADMIN** | + Modify config, modify compliance rules, manage users | Bank managers |
| **SYSTEM** | All permissions | Automated processes |

Exact mapping: `scope/iam/roles.py` (`ROLE_PERMISSIONS`).

### Usage

```python
from scope.iam import User, UserRole, Permission, AccessControl, AccessDeniedException

customer = User("user", UserRole.USER, "Alice")
rep      = User("staff456", UserRole.STAFF, "Bob")
manager  = User("admin789", UserRole.ADMIN, "Charlie")

customer.has_permission(Permission.VIEW_OWN_ESCALATIONS)   # True
rep.has_permission(Permission.RESOLVE_ESCALATIONS)         # True
manager.has_permission(Permission.MODIFY_CONFIG)           # True

AccessControl.check_permission(customer, Permission.VIEW_ALL_ESCALATIONS)  # raises AccessDeniedException
AccessControl.check_permission(customer, Permission.VIEW_ALL_ESCALATIONS, raise_on_deny=False)  # False
```

### How tools enforce it

```python
# scope/data/tools.py (simplified)
def get_account_balance(account_id: str) -> str:
    iam_user = get_current_user()                 # from GOOGLE_IAM_CURRENT_USER_*
    account = db.get_account(iam_user, account_id)  # raises if USER doesn't own it
    audit_logger.log_account_access(iam_user.user_id, account_id, "view_balance")
    compliance_logger.log_pci_data_access(iam_user.user_id, "account", account_id, "read")
    return f"Account {account_id}: ${account.balance:.2f}"
```

Agent tools: `get_account_balance`, `get_transaction_history`, `get_user_accounts`, `report_fraud`, `transfer_money` (banking); `safety_check_layer1/2`, `make_safe_and_compliant_decision`, `create_escalation_ticket`, `list_escalation_tickets`, `resolve_escalation_ticket`, `view_audit_logs`, `log_agent_response` (governance). The prompt only advertises the tools the current role is permitted to use.

---

## 🎫 Pillar 4: Escalation

Human-in-the-loop review queue. Tickets are stored in the `escalations` table of the banking SQLite database (`scope/data/storage/banking.db`).

### When Escalation Occurs
- Decision confidence below `GOOGLE_ESCALATION_THRESHOLD` (default 0.6)
- Ambiguous or off-topic requests, edge cases
- High-value transactions (COMP-004)
- Errors in the decision step fail safe to `escalate`

### API

```python
from scope.escalation import EscalationQueue, EscalationTicket
from scope.iam import User, UserRole

queue = EscalationQueue()          # or EscalationQueue(Database("path.db"))

# Agent side
ticket = EscalationTicket(
    user_id="user",
    input_text="Transfer $50,000 to external account",
    agent_reasoning="High-value transfer - requires approval",
    confidence=0.55,
)
ticket_id = queue.add_ticket(ticket)

# Review side (IAM-protected)
staff = User("staff1", UserRole.STAFF)
queue.view_tickets(staff, status="pending")           # all tickets
queue.resolve_ticket(staff, ticket_id, "Verified with customer")
queue.get_statistics(staff)                           # {"total", "pending", "resolved", "avg_confidence"}

customer = User("user", UserRole.USER)
queue.view_tickets(customer)                          # own tickets only
queue.resolve_ticket(customer, ticket_id, "...")      # raises AccessDeniedException
```

In the agent, STAFF/ADMIN use the `list_escalation_tickets` and `resolve_escalation_ticket` tools.

---

## 📊 Module 5: Data

SQLite banking database with IAM-protected operations.

```python
from scope.data import Database, User, Account, Transaction, AccountType, TransactionType
from scope.iam import User as IAMUser, UserRole

db = Database()                                   # scope/data/storage/banking.db

db.create_user(User(user_id="user", name="Alice Johnson", email="alice@example.com"))
db.create_account(Account(account_id="acc001", user_id="user",
                          account_type=AccountType.CHECKING, balance=1234.56))
db.create_transaction(Transaction(transaction_id="txn001", account_id="acc001",
                                  transaction_type=TransactionType.DEPOSIT, amount=500.0,
                                  description="Paycheck deposit"))

customer = IAMUser("user", UserRole.USER)
db.get_account(customer, "acc001")                # ✅ own account
db.get_account_transactions(customer, "acc001", days=30)

staff = IAMUser("staff1", UserRole.STAFF)
db.get_account(staff, "acc001")                   # ✅ staff privilege
db.get_user_accounts("user", iam_user=staff)
```

Seed data (`uv run python scope/data/seed_database.py`): user `user` (Alice Johnson) with checking `acc001`, savings `acc002`, and sample transactions. Schema details: `scope/data/storage/README.md`.

---

## 📝 Module 6: Logging

### Audit Logging

```python
from scope.logging import get_audit_logger, AuditEventType

audit = get_audit_logger()
audit.log_user_query(user_id="user", query="What's my balance?", response_action="approve")
audit.log_account_access(user_id="user", account_id="acc001", operation="view_balance")
audit.log_tool_call(user_id="user", tool_name="get_account_balance",
                    parameters={"account_id": "acc001"}, result="$1,234.56")
audit.log_safety_block(user_id="user", input_text="...", risk_category="insult")
audit.log_event(event_type=AuditEventType.USER_QUERY, user_id="user",
                action="custom", details={...})
```

Events written automatically by the agent: `user_input`, `safety_check` (with toxic-bert scores), `safety_block`, `safety_layer1_check`, `safety_layer2_analysis`, `safety_decision_made`, `account_access`, `transaction_query`, `escalation_created`, `escalation_resolved`, `llm_response`.

### Compliance Logging (PCI-DSS, SOC2)

```python
from scope.logging import get_compliance_logger

compliance = get_compliance_logger()
compliance.log_pci_data_access(user_id="user", data_type="account", account_id="acc001", operation="read")
compliance.log_pci_authentication(user_id="user", success=True, method="oauth2", ip_address="192.168.1.1")
compliance.log_soc2_access_control(user_id="user", resource="account_balance", permission="VIEW_ACCOUNTS", granted=True)
compliance.log_soc2_incident(user_id="user", incident_type="unauthorized_access_attempt",
                             severity="medium", description="Failed login attempt detected")
```

**Log Locations** (git-ignored, one JSON object per line):
- Audit: `scope/logging/audit_logs/audit_YYYY-MM-DD.jsonl`
- PCI-DSS: `scope/logging/compliance_logs/pci_dss_YYYY-MM-DD.jsonl`
- SOC2: `scope/logging/compliance_logs/soc2_YYYY-MM-DD.jsonl`

```json
{"timestamp": "2026-10-08T15:10:47", "event_type": "user_query", "user_id": "user",
 "action": "safety_check", "success": true,
 "details": {"layer": "2a", "model": "unitary/toxic-bert", "checked": true, "is_safe": false,
             "risk_category": "insult", "confidence": 0.94, "scores": {"toxicity": 0.95, "...": 0}}}
```

### 🖥️ Terminal Log Viewer

```bash
uv run python scope/logging/view_logs.py                 # today's log, interactive
uv run python scope/logging/view_logs.py --follow        # tail in real time
uv run python scope/logging/view_logs.py --event safety_block --tail 20
uv run python scope/logging/view_logs.py --date 2026-10-08 --user staff --summary
```

Flags: `--date`, `--user`, `--action`, `--event`, `--tail N`, `--verbose`, `--follow`, `--summary`.

![Terminal Viewer](logging.png)
*Color-coded audit logs in the terminal*

---

## 🔍 Observability & Tracing

```bash
uv run adk web
# http://127.0.0.1:8000 → open a conversation → "Trace" tab
```

**You'll see:**
- 🔍 Every callback execution (`fast_guardrail_callback`, `after_model_callback`)
- 🛠️ Every tool call with parameters and results (`safety_check_layer1` → `safety_check_layer2` → `make_safe_and_compliant_decision` → banking tool)
- 💬 Every LLM request and response, with timing and token usage

Application logs:

```
INFO - [SCOPE Layer 2a] Checking input: What's my balance?...
INFO - [SCOPE Layer 2a] Passed (max score 0.01).
INFO - [SCOPE After LLM] Response logged
```

See `OBSERVABILITY.md` for the logging strategy and `ADK_TOOL_CALLING.md` for how ADK dispatches tool calls.

---

## 🧪 Testing

```bash
# Everything (Gemini-backed tests skip automatically without GCP credentials)
uv run pytest

# Pre-model safety gate + classifier wrapper (fast, fake model, no download)
uv run pytest tests/test_callbacks.py scope/safety/tests/test_text_safety.py -v

# Individual pillars
uv run pytest scope/safety/tests/ -v        # image test downloads the NSFW model
uv run pytest scope/compliance/tests/ -v
uv run pytest scope/iam/tests/ -v
uv run pytest scope/escalation/tests/ -v
uv run pytest tests/ -v
```

**Coverage:**
- ✅ Pre-model gate: latest user turn only, safe passes, toxic blocked before the LLM, runs on every request, fail-open when model unavailable, config disable
- ✅ Text classifier thresholds (high / severe), empty input, unavailable model
- ✅ Compliance rule transformation
- ✅ IAM roles, permissions, access control
- ✅ Escalation queue: add / view by role / resolve by role / statistics
- ✅ Agent initialisation and callback registration
- ⏭️ Gemini-backed Layer 2b / decision tests (require `gcloud auth application-default login`)

See `TESTING.md` for details.

---

## 🔧 Advanced Configuration

All `Config` fields can be set in code as well as via `GOOGLE_*` env vars:

```python
from scope.config import Config

config = Config(
    SAFETY_THRESHOLD_HIGH=0.7,
    SAFETY_USE_ML_MODELS=True,
    IAM_CURRENT_USER_ROLE="STAFF",
    ESCALATION_THRESHOLD=0.7,          # higher = fewer escalations
)
policy = config.current_policy          # .safety / .compliance / .iam / .escalation
```

---

## 📚 Dependencies

- **google-adk** - Agent Development Kit (agent, callbacks, web UI, tracing)
- **google-cloud-aiplatform** / **google-generativeai** - Gemini on Vertex AI
- **detoxify** + **transformers (<5)** + **torch 2.2.2** - `unitary/toxic-bert` text safety (transformers 5.x requires torch ≥ 2.4)
- **timm**, **pillow** - image safety model
- **pydantic-settings** - configuration
- **pyyaml** - policy-as-code rule files
- **numpy<2** - NumPy 1.x compatibility
- **SQLite** - banking database and escalation queue (built-in)

---

## 📖 Documentation

- `TESTING.md` - test layout and coverage
- `OBSERVABILITY.md` - audit logging strategy
- `ADK_TOOL_CALLING.md` - how ADK dispatches tool calls
- `example_config.py` - industry-specific configuration templates
- `scope/data/storage/README.md` - database schema
- `scope/logging/README.md` - log format and viewer

---

## 🚀 Production Deployment

For production banking applications:

1. **Identity**: replace the `GOOGLE_IAM_CURRENT_USER_*` settings with real authentication (OAuth2/SAML) and pass the user through the session
2. **Database**: migrate from SQLite to PostgreSQL/MySQL
3. **Safety**: decide fail-closed vs fail-open for the pre-model gate; wire `ImageSafetyTool` into the callback
4. **Monitoring**: export ADK traces and JSONL logs to OpenTelemetry / Prometheus / Grafana
5. **Scaling**: deploy with Kubernetes and load balancing
6. **Backup**: automated backups for the banking database and audit logs

---

## 🤝 Contributing

This is a reference implementation of the SCOPE framework. Contributions welcome!

---

## 📄 License

Apache-2.0
