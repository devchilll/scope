# SCOPE: AI Agent Governance Framework For High-Stakes Applications

SCOPE, by Ivy Si

**SCOPE** (Safety, Compliance, Observability, Permissions, Escalation) is a reference governance framework for enterprise AI agents. Built on Google's Agent Development Kit (ADK), it implements a "Defense in Depth" architecture with **5 pillars**:

- **S**afety Guardrails: ML pre-model gate + LLM contextual safety
- **C**ompliance & Policy-as-Code: YAML rules the agent must cite
- **O**bservability & Auditing: JSONL audit trail, PCI-DSS / SOC2 event logs (selected categories), ADK tracing
- **P**ermissions & Identity (IAM): USER / STAFF / ADMIN / SYSTEM roles; every banking tool checks the caller's role and account ownership
- **E**scalation Protocols: human-in-the-loop review queue

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
- 🛡️ **Pre-LLM Safety**: Every request is screened by an ML text classifier in `before_model_callback` before the model acts; flagged inputs never reach the LLM, not even as conversation history on later turns (text only, and the classifier must be enabled and loadable; see the gate's limits under Pillar 1)
- 📜 **Policy-as-Code**: Safety and compliance rules live in YAML with IDs the agent must cite
- 🔐 **Role-Based Access**: USER / STAFF / ADMIN / SYSTEM with role and account-ownership checks in the banking tools; role checks on viewing/resolving escalations and viewing audit logs
- 📊 **Database Tools**: IAM-protected queries to user / account / transaction tables
- 📝 **Audit Logging**: Every input, safety score, model response, and tool call logged; Layer 2b safety decisions logged when the model calls `make_safe_and_compliant_decision`; plus selected PCI-DSS / SOC2 events
- 🚨 **Escalation**: Uncertain cases routed to a human review queue with role-gated resolution

---

## 🏗️ Architecture Overview

```
User Input
    ↓
Layer 2a: Fast ML safety gate (unitary/toxic-bert, before_model_callback)
    ↓ (if safe)
Layer 2b: LLM contextual safety + compliance analysis (safety_check_layer2)
    ↓
Decision: approve / reject / rewrite / escalate, role-aware (make_safe_and_compliant_decision)
    ↓ (if escalate)
Human Review Queue (STAFF/ADMIN resolve via resolve_escalation_ticket)
```

### Modules

1. **Safety** (`scope/safety/`, `scope/callbacks.py`) - ML pre-model gate + LLM contextual checks
2. **Compliance** (`scope/rules/`, `scope/compliance/`) - YAML safety/compliance rules with IDs
3. **Observability** (`scope/logging/`) - Audit trail, compliance logs, terminal viewer
4. **IAM** (`scope/iam/`) - Roles, permissions, access control
5. **Escalation** (`scope/escalation/`) - Human-in-the-loop ticket queue

Supporting layer: **Data** (`scope/data/`) - SQLite banking database + IAM-protected agent tools

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
│   └── tools.py           # ImageSafetyTool (NSFW classifier, not wired into the gate)
├── rules/                 # Pillar 2: policy-as-code
│   ├── safety_rules.yaml      # SAFETY-001..005
│   ├── compliance_rules.yaml  # COMP-001..007
│   └── loader.py          # Renders rules into prompt text
├── compliance/            # Rule transformation helpers + industry example rule sets
├── iam/                   # Pillar 4
│   ├── roles.py           # UserRole, Permission, role → permission map
│   └── acl.py             # User, AccessControl, AccessDeniedException
├── escalation/            # Pillar 5
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

The first screened request loads `unitary/toxic-bert` through Detoxify (one-time, cached): the model checkpoint is downloaded from Detoxify's GitHub release, and the `bert-base-uncased` config and tokenizer from Hugging Face.

### Configuration

Create a `.env` file in the project root. All settings are read by `scope/config.py` with the `GOOGLE_` prefix.

```bash
# Google Cloud
GOOGLE_GENAI_USE_VERTEXAI=true        # false = Gemini API with GOOGLE_API_KEY
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# Pillar 1: Safety
GOOGLE_SAFETY_THRESHOLD_HIGH=0.8      # block when any toxic-bert score >= this
GOOGLE_SAFETY_USE_ML_MODELS=true      # false skips the pre-model classifier (logged)

# Pillar 2: Compliance - extra free-text rules appended to the agent instruction
GOOGLE_COMPLIANCE_ENABLED=true
GOOGLE_COMPLIANCE_RULES='["Never share full account numbers"]'

# Pillar 4: IAM - who the agent is acting for (see "Switching roles")
GOOGLE_IAM_CURRENT_USER_ID=user
GOOGLE_IAM_CURRENT_USER_ROLE=USER     # USER | STAFF | ADMIN | SYSTEM
GOOGLE_IAM_CURRENT_USER_NAME="Alice Johnson"

# Pillar 5: Escalation - Layer 2b confidence below this is escalated
GOOGLE_ESCALATION_THRESHOLD=0.6
```

The agent, the Layer 2b analysis, and the decision step all use the model set in `Config.agent_settings.model` (default `gemini-2.5-flash`).

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

A fast ML text-safety gate in front of the model, backed by LLM contextual analysis.

### Text Safety
- **Model**: `unitary/toxic-bert` via Detoxify
- **Detection**: Toxicity, severe toxicity, obscenity, threats, insults, identity attack
- **Implementation**: `scope/safety/text.py` (`TextSafetyTool`)
- **Where it runs**:
  1. `scope/callbacks.py` → `fast_guardrail_callback`, registered as the agent's `before_model_callback`. Runs before **every** model call. Blocks by returning a refusal response so the model is never called.
  2. `scope/observability_tools.py` → `safety_check_layer1` tool. Re-runs the same check so the result also appears as an explicit tool step (with its output) in the ADK trace viewer, next to the Layer 2b and decision tools.
- **Once per turn**: the new message that started the turn (ADK's `user_content`, whatever role the client gave it) is screened and logged (`user_input`, `safety_check`) once per invocation, inside a `scope.pre_model_safety_gate` OpenTelemetry span. The decision is cached under the `temp:scope_safety_gate_decision` state key (keyed by invocation id and a hash of the message) and applied to every model call of that turn, including the follow-up calls in ADK's tool loop. ADK keeps `temp:` keys for the current invocation only: it never persists them and drops them from client-supplied state, so a client cannot pre-seed the decision.
- **Long messages**: toxic-bert reads at most 512 tokens and Detoxify silently drops the rest, so a message longer than that is split into overlapping windows of 400 tokens (100-token overlap) using the model's own tokenizer (a custom model without a tokenizer gets 500-character windows); every window is classified and each category's highest score is used. Shorter messages are classified whole, as before.
- **Blocked messages stay out of history**: a blocked message remains in the ADK session, so the refusal carries `custom_metadata={"scope_safety_blocked": true, "input_sha256": <SHA-256 of the text>}`, which ADK stores on the refusal event. On every later model call the gate collects those hashes from the session's event log and replaces any turn whose text matches with `[message withheld by SCOPE safety gate]` before the request is sent. The event log is the record because a client can overwrite session state (ADK's `state_delta` on `/run` and `/run_sse`, `PATCH` on a session) but cannot change or remove events already in a session; the hashes are also kept in the `scope_safety_blocked_inputs` state key, which can only add to them. The model never sees the blocked text, on that turn or later ones. (If a previously blocked text is sent again and passes, for example after a threshold change, it is still withheld.)
- **Thresholds**: block when any score ≥ `GOOGLE_SAFETY_THRESHOLD_HIGH` (default 0.8), or `severe_toxicity` ≥ 0.5
- **Disable**: `GOOGLE_SAFETY_USE_ML_MODELS=false` skips the classifier in both the callback and the `safety_check_layer1` tool (each skip is written to the audit log; the tool returns a "SKIPPED" result); Layer 2b LLM checks still run
- **If the model fails to load**: the request is logged as *unchecked* (`success: false`) and continues to the Layer 2b LLM checks (fail-open). Audit logs make this visible.
- **If screening raises** (the classifier is loaded but errors on this message, or the gate itself fails): the request is refused like a blocked one (fail-closed), its hash is recorded the same way so the unscreened text is withheld from later turns too, and the error is logged (`safety_check` with `success: false`, plus `safety_block` with risk category `screening_error`).

### Limits of the pre-model gate
- **Fails open when the classifier is off or unavailable**: if the classifier cannot be loaded, or `GOOGLE_SAFETY_USE_ML_MODELS=false`, requests are not ML-screened and go to the model; only the Layer 2b LLM checks (which the agent is instructed to run) remain. Texts blocked earlier in the session stay withheld. This is different from an error while screening a message, which refuses that message (see above).
- **Text only**: only the text parts of the new message are classified. Images, files and function-response parts are not screened.
- **Scores cover the whole input**: the classifier scores each input (or each window of a long message) as a whole, so a short toxic sentence surrounded by enough benign text can score below the threshold.
- **Client-written history**: the gate screens each new message. ADK's create-session API also accepts a list of `events` to start the session with; text in those events is never screened. Do not expose that endpoint (`adk web` / `adk api_server` are development servers) to untrusted clients.

### Image Safety
- **Model**: `Marqo/nsfw-image-detection-384` (Vision Transformer)
- **Status**: `ImageSafetyTool` (`scope/safety/tools.py`) is available for direct use (it reports `is_safe` as `nsfw_score <= 0.5`, or an unknown result with `checked: false` if the image can't be checked), but it is **not wired into the gate or the agent**: images are not screened.

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
# ADK calls it as callback(callback_context=..., llm_request=...), so the
# parameter names must match.
def fast_guardrail_callback(callback_context, llm_request):
    state = callback_context.state
    user_text = screened_text(callback_context, llm_request)  # the new message

    decision = state.get("temp:scope_safety_gate_decision")
    if not same_invocation_and_text(decision, callback_context.invocation_id, user_text):
        # Once per turn, inside the "scope.pre_model_safety_gate" span:
        # logs user_input, runs toxic-bert, logs safety_check (+ safety_block)
        try:
            decision = _screen(user_text, user_id)
        except Exception as exc:
            decision = _screening_failed(user_text, user_id, exc)  # refuse
        state["temp:scope_safety_gate_decision"] = decision
        if decision["blocked"]:
            state["scope_safety_blocked_inputs"] = blocked + [sha256(user_text)]

    if decision["blocked"]:
        # LLM is never called; ADK stores the metadata on the refusal event
        return LlmResponse(content=refusal, custom_metadata={
            "scope_safety_blocked": True, "input_sha256": sha256(user_text)})
    # hashes from the event log, plus any in state
    redact_blocked_inputs(llm_request, blocked_input_hashes(callback_context))
    return None                                    # Continue to LLM
```

**Benefits:**
- 🚀 **Fast**: a local classifier runs before any LLM call, so unsafe inputs are refused without waiting for the model
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
`GOOGLE_COMPLIANCE_RULES` (a JSON list) adds business-specific rules without editing YAML. When `GOOGLE_COMPLIANCE_ENABLED=true` and the list is non-empty, `scope/agent.py` turns each rule into a `PRINCIPLE:` line (`transform_rules`) and `build_instruction` appends them as a numbered **COMPLIANCE PRINCIPLES** section to the agent instruction (`format_compliance_section`); with no rules the instruction is unchanged. The instruction is passed to ADK as a function (an InstructionProvider), so ADK does not apply its `{state}` templating and braces in a rule are sent to the model as written. These rules are enforced by the agent model itself: they are not included in the Layer 2b analysis prompt and have no rule IDs. `scope/compliance/examples.py` ships starter rule sets (`HEALTHCARE_RULES`, `FINANCIAL_SERVICES_RULES`, `LEGAL_SERVICES_RULES`, `RETAIL_BRAND_RULES`, `SAAS_RULES`, `EDUCATION_RULES`), and `example_config.py` has per-industry templates (rules + escalation threshold) with the matching `.env` lines.

---

## 👥 Pillar 4: IAM (Identity & Access Management)

Role-based access control. Every agent-facing banking tool runs as the configured current user and checks that user's role and account ownership; the escalation-queue and audit-log tools check their own permissions (see the table below).

### User Roles

| Role | Permissions | Use Case |
|------|-------------|----------|
| **USER** | Use agent, view own accounts/transactions, view own escalations | Banking customers |
| **STAFF** | + View any customer's accounts/transactions, view all escalations, resolve escalations, view config, view audit logs | Customer service reps |
| **ADMIN** | + Modify config, modify compliance rules, manage users | Bank managers |
| **SYSTEM** | All permissions | Automated processes |

Exact mapping: `scope/iam/roles.py` (`ROLE_PERMISSIONS`). Roles are read from `GOOGLE_IAM_CURRENT_USER_ROLE` case-insensitively (`parse_role`).

Permissions actually checked by tools today: `VIEW_ACCOUNTS` / `VIEW_TRANSACTIONS` (banking tools), `VIEW_OWN_ESCALATIONS` / `VIEW_ALL_ESCALATIONS` (`list_escalation_tickets`; without `VIEW_ALL_ESCALATIONS` only your own tickets are returned), `RESOLVE_ESCALATIONS` (`resolve_escalation_ticket`), `VIEW_LOGS` (`view_audit_logs`); `USE_AGENT` only decides which tools the prompt advertises. `VIEW_CONFIG`, `MODIFY_CONFIG`, `MODIFY_COMPLIANCE_RULES`, `MANAGE_USERS` and `BYPASS_SAFETY_CHECKS` are defined and granted in `ROLE_PERMISSIONS` but not yet used by any tool, so in the current build ADMIN can do the same things as STAFF, and nothing can bypass the safety checks.

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

Tools that take a `user_id` (`get_transaction_history`, `get_user_accounts`, `report_fraud`) treat it only as the target customer: the call still runs as the current user, a USER passing someone else's id is denied, and the audit log records the real caller. `report_fraud` only files a ticket for an account the caller may access (a USER's own account; any customer account for STAFF/ADMIN), and `transfer_money` only moves money between the caller's own accounts. Before any database access, `transfer_money` rejects a transfer to the same account and any amount that is not a positive, finite number with at most 2 decimal places (no silent rounding). The debit, the credit and both transaction rows are written in one SQLite transaction (`Database.transfer_funds`), which re-checks the source balance under the write lock and rounds the new balances to cents; if any step fails, nothing is written. The database write helpers (`create_user`, `create_account`, `update_account`, `create_transaction`, `create_escalation`, `transfer_funds`) are not agent tools and do no IAM checks themselves.

Agent tools: `get_account_balance`, `get_transaction_history`, `get_user_accounts`, `report_fraud`, `transfer_money` (banking); `safety_check_layer1/2`, `make_safe_and_compliant_decision`, `create_escalation_ticket`, `list_escalation_tickets`, `resolve_escalation_ticket`, `view_audit_logs`, `log_agent_response` (governance). The prompt only advertises the tools the current role is permitted to use.

---

## 🎫 Pillar 5: Escalation

Human-in-the-loop review queue. Tickets are stored in the `escalations` table of the banking SQLite database (`scope/data/storage/banking.db`).

### When Escalation Occurs
- Layer 2b `confidence` below `GOOGLE_ESCALATION_THRESHOLD` (default 0.6): the value is written into the decision prompt, which instructs the decision model to `escalate` below it and to `approve` only when confidence is at or above it (and safety and compliance scores are at least 0.8). This is an instruction to the model, not a check in code; the chosen action is the model's judgement.
- Ambiguous or off-topic requests, edge cases (judged by the decision model)
- High-value transfers (COMP-004), enforced in code: `transfer_money` does not execute a transfer above `thresholds.high_value_amount` in `scope/rules/compliance_rules.yaml` (default $10,000). It creates a pending ticket (`metadata.type = "high_value_transfer"`) and moves no money; resolving the ticket does not execute the transfer.
- Fraud reports (`report_fraud`) create a ticket (`metadata.type = "fraud_report"`)
- Errors in the decision step fail safe to `escalate`

When the agent escalates, `create_escalation_ticket(user_input, reasoning, confidence)` stores the confidence value the agent passes (default 0.0, clamped to 0-1) on the ticket. `get_statistics()["avg_confidence"]` is the mean confidence over all tickets the caller can view, including fraud-report and high-value-transfer tickets, which are always stored with confidence 1.0.

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

## 📊 Data Layer

SQLite banking database. The methods that take an IAM user (`get_account`, `get_user_accounts`, `get_account_transactions`, `get_escalations`, `resolve_escalation`) are IAM-protected; the `create_*` / `update_account` write helpers below are unchecked and meant for seeding or for use after a tool's own checks.

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

## 📝 Pillar 3: Observability & Logging

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

Events written automatically by the agent, by `action` (each event also has an `event_type`: `user_query`, `tool_call`, `account_access`, `transaction_query`, `safety_block`, `escalation_created` or `escalation_resolved`):

- Callbacks: `user_input` and `safety_check` (with toxic-bert scores when the classifier ran) once per turn that has new message text, plus `safety_block` only when that turn is blocked (including screening errors); `llm_response` for every model response (response text truncated to 500 chars, plus requested tool names); and `tool_call_<tool name>` for every tool invocation (arguments redacted/truncated, user ID and role, success or error)
- Tools: `safety_layer1_check`, `safety_layer2_analysis`, `safety_decision_made`, `account_view_balance`, `query_transactions`, `list_accounts`, `transfer_completed`, `fraud_report`, `create_escalation_ticket`, `ticket_resolved`
- Failures and denials are written with `success: false` (e.g. `view_balance_failed`, `transfer_unauthorized_source`, `resolve_ticket_unauthorized`)

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

Written by the agent today: PCI-DSS data access (balance, transaction history, transfers), SOC2 CC7.3 incidents (fraud reports), and SOC2 CC6.1 access-control decisions for `view_audit_logs`. PCI authentication, PCI privileged actions and SOC2 data processing are defined in `compliance_log.py` but not yet called (see `OBSERVABILITY.md`).

**Log Locations** (git-ignored, one JSON object per line):
- Audit: `scope/logging/audit_logs/audit_YYYY-MM-DD.jsonl` (all three roll over to a new file at midnight)
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
uv run python scope/logging/view_logs.py                 # today's log, color-coded table + summary
uv run python scope/logging/view_logs.py --follow --user staff  # tail in real time (filters apply)
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
- 🔍 The pre-model safety gate as a `scope.pre_model_safety_gate` span (once per turn, under `invoke_agent <agent name>`, before the first `call_llm`), with attributes `scope.safety.checked`, `scope.safety.blocked` and `scope.safety.outcome` (`allowed`, `blocked`, `unchecked` or `skipped`); when the classifier ran (or failed to load) it also has `scope.safety.model`, `scope.safety.max_score` and `scope.safety.risk_category`, and when screening raises the span records the exception instead. ADK's own spans cover the invocation (`invocation`), the agent (`invoke_agent <agent name>`), model calls (`call_llm`, `generate_content <model>`) and tools (`execute_tool <tool name>`); callbacks get no spans of their own, so `after_model_callback` shows up only as part of `call_llm`. ADK web lists only traces that contain a `call_llm` span, so a turn the gate blocks does not appear in the Trace tab; its span still goes to any OpenTelemetry exporter you configure (e.g. `adk web --otel_to_cloud`), and the block is in the audit log as `safety_block`.
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
- ✅ Pre-model gate: the new message is screened whatever its role, safe passes, toxic blocked before the LLM, screened once per turn (tool loop reuses the decision), blocked text withheld from later requests (also end-to-end through ADK's runner with a fake LLM, including after the client wipes the session-state copy via `state_delta` or a state-only event), the decision cache can't be seeded by the client, a screening error refuses the request and withholds its text later, gate span attributes, fail-open when model unavailable, config disable (callback and `safety_check_layer1` tool)
- ✅ Image check failure reports an unknown result, never "safe"
- ✅ Text classifier thresholds (high / severe), empty input, unavailable model, long text classified in overlapping windows (toxic tail after a long benign prefix is caught)
- ✅ Compliance rule transformation
- ✅ IAM roles, permissions, access control
- ✅ Escalation queue: add / view by role / resolve by role / statistics / metadata
- ✅ Escalation wiring: configured threshold in the decision prompt, ticket confidence, COMP-004 high-value transfer guard, custom compliance rules in the instruction
- ✅ Transfers: same-account and non-numeric / non-finite / sub-cent amounts rejected, debit + credit + transaction rows all-or-nothing, funds re-checked in the transaction, balances kept in cents, no connection left open after a failed query
- ✅ Agent initialisation and callback registration
- ✅ Audit trail: a `tool_call` event per tool run (checked through a scripted ADK run), daily log rollover, `view_audit_logs` newest-first, viewer filters in follow mode (tests write to temp dirs only)
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
    ESCALATION_THRESHOLD=0.7,          # decision prompt escalates below this confidence (higher = more)
)
policy = config.current_policy          # .safety / .compliance / .escalation
```

---

## 📚 Dependencies

- **google-adk** - Agent Development Kit (agent, callbacks, web UI, tracing)
- **google-cloud-aiplatform** / **google-genai** (`google.genai`, installed with google-adk) - Gemini on Vertex AI or the Gemini API
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
3. **Safety**: decide fail-closed vs fail-open for the pre-model gate when the classifier can't be loaded; wire `ImageSafetyTool` into the callback; don't expose ADK's development session API (which accepts client-written events) to end users
4. **Monitoring**: export ADK traces and JSONL logs to OpenTelemetry / Prometheus / Grafana
5. **Scaling**: deploy with Kubernetes and load balancing
6. **Backup**: automated backups for the banking database and audit logs

---

## 🤝 Contributing

This is a reference implementation of the SCOPE framework. Contributions welcome!

---

## 📄 License

Apache-2.0
