# SCOPE Test Suite

Comprehensive unit and integration tests for the SCOPE framework's 4 pillars.

## Test Structure

```
scope/
├── safety/tests/
│   ├── test_safety.py          # Image safety tool
│   └── test_text_safety.py     # Text safety classifier (fake model)
├── compliance/tests/
│   └── test_compliance.py      # Rule transformation (5 tests)
├── iam/tests/
│   └── test_iam.py             # Roles, permissions, ACL (14 tests)
└── escalation/tests/
    └── test_escalation.py      # Queue, tickets, SQLite (14 tests)

tests/
├── test_callbacks.py           # Pre-model safety gate (before_model_callback)
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
- ✅ TextSafetyTool: safe / toxic / severe-toxicity / threshold / empty input / model unavailable
  (`scope/safety/tests/test_text_safety.py`, fake model - no download)

### Pre-model safety gate (`tests/test_callbacks.py`)
- ✅ Only the latest user turn is screened (model turns ignored)
- ✅ Safe input continues to the LLM
- ✅ Toxic input returns a refusal `LlmResponse` before the model is called
- ✅ Check runs on every request
- ✅ Model unavailable → logged, fails open to Layer 2b
- ✅ `GOOGLE_SAFETY_USE_ML_MODELS=false` → classifier skipped (logged)

### Pillar 2: Compliance (5 tests)
- ✅ Single rule transformation
- ✅ Multiple rules transformation
- ✅ Empty list handling
- ✅ Compliance section formatting
- ✅ Empty section formatting

### Pillar 3: IAM (14 tests)
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

### Pillar 4: Escalation (14 tests)
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
- ✅ Resolve ticket denied (STAFF)
- ✅ Queue statistics
- ✅ Default database location
- ✅ Custom database location

### Integration Tests (18 tests)
- ✅ Agent initialization
- ✅ Config loading (4 pillars)
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
