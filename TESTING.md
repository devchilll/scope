# SCOPE Test Suite

Comprehensive unit and integration tests for the SCOPE framework's 5 pillars.

## Test Structure

```
scope/
├── safety/tests/
│   ├── test_safety.py          # Image safety tool
│   └── test_text_safety.py     # Text safety classifier (fake model)
├── compliance/tests/
│   └── test_compliance.py      # Rule transformation (5 tests)
├── iam/tests/
│   ├── test_iam.py             # Roles, permissions, ACL (14 tests)
│   └── test_tool_enforcement.py # Banking tools act as current user (24 tests)
└── escalation/tests/
    └── test_escalation.py      # Queue, tickets, metadata, SQLite (18 tests)

tests/
├── test_audit_logging.py       # Tool-call audit callback, daily rollover, log viewing
├── test_callbacks.py           # Pre-model safety gate (before_model_callback)
├── test_escalation_config.py   # Escalation threshold, COMP-004 transfer guard, custom rules
├── test_transfer_validation.py # transfer_money validation, atomic transfer, connection cleanup
└── test_agent_integration.py   # Agentic system integration
```

## Running Tests

### All Tests
```bash
uv run pytest -v
```

### By Pillar
```bash
# Safety
uv run pytest scope/safety/tests/ -v

# Compliance
uv run pytest scope/compliance/tests/ -v

# IAM
uv run pytest scope/iam/tests/ -v

# Escalation
uv run pytest scope/escalation/tests/ -v

# Integration
uv run pytest tests/ -v
```

### Specific Test
```bash
uv run pytest scope/iam/tests/test_iam.py::TestAccessControl::test_check_permission_allowed -v
```

## Test Coverage

### Pillar 1: Safety
- ✅ ImageSafetyTool initialization
- ✅ Output format validation
- ✅ A failed image check returns an unknown result (`checked: false`), never "safe"
- ✅ TextSafetyTool: safe / toxic / severe-toxicity / threshold / empty input / model unavailable /
  long text classified in overlapping windows, max score per category
  (`scope/safety/tests/test_text_safety.py`, fake model - no download)

### Pre-model safety gate (`tests/test_callbacks.py`)
- ✅ The new message is screened, whatever role the client gave it; without text, the latest user turn
- ✅ Safe input continues to the LLM
- ✅ Toxic input returns a refusal `LlmResponse` before the model is called
- ✅ Screened and logged once per turn; the decision applies to every model call of that turn (tool loop)
- ✅ Blocked text is withheld from later model requests (unit + end-to-end through ADK's runner with a fake LLM)
- ✅ Blocked hashes come from the refusal events' `custom_metadata`; wiping the state copy (`state_delta`, state-only event) doesn't bring the text back
- ✅ A client-supplied `temp:scope_safety_gate_decision` can't make a toxic message pass
- ✅ Screening error → request refused, text withheld from later turns
- ✅ `scope.pre_model_safety_gate` span with blocked / max-score attributes
- ✅ Model unavailable → logged, fails open to Layer 2b
- ✅ `GOOGLE_SAFETY_USE_ML_MODELS=false` → classifier skipped (logged), in the callback and the `safety_check_layer1` tool

### Pillar 2: Compliance (5 tests)
- ✅ Single rule transformation
- ✅ Multiple rules transformation
- ✅ Empty list handling
- ✅ Compliance section formatting
- ✅ Empty section formatting

### Pillar 4: IAM (14 tests)
- ✅ UserRole enum values
- ✅ Permission enum values
- ✅ USER role permissions
- ✅ STAFF role permissions
- ✅ ADMIN role permissions
- ✅ Permission checking function
- ✅ User creation
- ✅ User permission checking
- ✅ User representation
- ✅ Permission check (allowed)
- ✅ Permission check (denied)
- ✅ Permission check (raises exception)
- ✅ Escalation viewing permissions
- ✅ Escalation resolution permissions

### IAM tool enforcement (24 tests, `scope/iam/tests/test_tool_enforcement.py`)
- ✅ Case-insensitive role parsing (`parse_role`)
- ✅ Role descriptions match `ROLE_PERMISSIONS`
- ✅ USER cannot read another user's transactions or accounts, even by passing their `user_id`
- ✅ STAFF can read a customer's transactions; audit log records STAFF as the actor
- ✅ `report_fraud` only files tickets for accounts the caller may access

### Pillar 5: Escalation (18 tests)
- ✅ Ticket creation
- ✅ Auto-generated fields (ID, timestamp)
- ✅ Optional fields defaults
- ✅ Queue initialization
- ✅ Add ticket
- ✅ Get pending tickets
- ✅ View tickets (USER role)
- ✅ View tickets (STAFF role)
- ✅ View tickets (ADMIN role)
- ✅ Resolve ticket (ADMIN)
- ✅ Resolve ticket allowed (STAFF), denied (USER)
- ✅ Ticket metadata stored and read back (and NULL → None)
- ✅ Malformed metadata (invalid JSON or not an object) reads back as None without breaking the queue
- ✅ Queue statistics
- ✅ Default database location
- ✅ Custom database location

### Integration Tests (18 tests)
- ✅ Agent initialization
- ✅ Config loading (safety / compliance / escalation policy)
- ✅ Safety callback exists
- ✅ Safety tools functional
- ✅ Compliance rules loaded
- ✅ Rule transformation
- ✅ Agent actions defined (ALLOW, REFUSE, REWRITE, ESCALATE)
- ✅ Callback registration
- ✅ Prompt includes safety policy
- ✅ Prompt includes all actions
- ✅ Prompt includes output format
- ⏭️ End-to-end flows (skipped - requires LLM calls)

### Escalation & config wiring (`tests/test_escalation_config.py`)
- ✅ Decision prompt uses `GOOGLE_ESCALATION_THRESHOLD` (default 0.6) for both the escalate and approve conditions, and the configured model
- ✅ `GOOGLE_GENAI_USE_VERTEXAI` selects Vertex AI or the Gemini API client
- ✅ `create_escalation_ticket` stores the Layer 2b confidence (default 0.0, clamped to 0-1)
- ✅ COMP-004: transfers above `high_value_amount` are not executed and create a ticket; at the limit they execute; the limit follows the YAML value; an over-limit transfer from an account the caller does not own is refused without a ticket
- ✅ `report_fraud` ticket metadata is persisted
- ✅ `GOOGLE_COMPLIANCE_RULES` appended to the agent instruction (unchanged when empty); rules set in the environment, including braces, appear verbatim in the system instruction produced by ADK's instruction processing

### Transfers (`tests/test_transfer_validation.py`)
- ✅ Same-account transfers rejected (tool and database), no balance change
- ✅ NaN / ±inf, an int too large for a float (`10**400`), non-numeric (`"50"`, `None`, `True`), zero / negative and sub-cent (> 2 decimal places) amounts rejected before any database access
- ✅ `Database.transfer_funds` called directly rejects the same invalid amounts (e.g. `0.005`, `0.025`, NaN) with `ValueError`; nothing is written
- ✅ A failed query closes its connection (no "database is locked" on the next call)
- ✅ Debit, credit and transaction rows roll back together on failure; unknown destination does not debit; funds re-checked inside the transaction, so a transfer that passes `transfer_money`'s pre-check on an out-of-date (higher) balance is refused with nothing written
- ✅ Balances rounded to cents (ten $0.10 transfers leave exact balances)

## Test Configuration

**pytest.ini:**
- Test paths: All pillar test directories + integration tests
- Verbose output enabled
- Short traceback format

**Dependencies:**
- pytest >= 7.0.0

## Notes

- Integration tests for actual LLM calls are marked as `@pytest.mark.skip` to avoid API costs during development
- Database tests use temporary files that are cleaned up automatically
- All tests use pytest fixtures for proper setup/teardown
