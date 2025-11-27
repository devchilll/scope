# PRIME Test Suite

Comprehensive unit and integration tests for the PRIME framework's 4 pillars.

## Test Structure

```
prime_guardrails/
├── safety/tests/
│   └── test_safety.py          # Text & Image safety tools (6 tests)
├── compliance/tests/
│   └── test_compliance.py      # Rule transformation (5 tests)
├── iam/tests/
│   └── test_iam.py             # Roles, permissions, ACL (14 tests)
└── escalation/tests/
    └── test_escalation.py      # Queue, tickets, SQLite (14 tests)

tests/
└── test_agent_integration.py   # Agentic system integration (18 tests)
```

## Running Tests

### All Tests
```bash
uv run pytest -v
```

### By Pillar
```bash
# Safety
uv run pytest prime_guardrails/safety/tests/ -v

# Compliance
uv run pytest prime_guardrails/compliance/tests/ -v

# IAM
uv run pytest prime_guardrails/iam/tests/ -v

# Escalation
uv run pytest prime_guardrails/escalation/tests/ -v

# Integration
uv run pytest tests/ -v
```

### Specific Test
```bash
uv run pytest prime_guardrails/iam/tests/test_iam.py::TestAccessControl::test_check_permission_allowed -v
```

## Test Coverage

### Pillar 1: Safety (6 tests)
- ✅ TextSafetyTool initialization
- ✅ Safe text detection
- ✅ Offensive text detection
- ✅ Error handling
- ✅ ImageSafetyTool initialization
- ✅ Output format validation

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
