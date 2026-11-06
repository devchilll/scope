# SCOPE Test Suite

Unit and integration tests for the SCOPE framework's 5 pillars: 240 tests
collected (`uv run pytest --co -q`). Without Google Cloud credentials 236 pass
and the 4 Gemini-backed tests skip.

## Test Structure

```
scope/
├── safety/tests/
│   ├── test_safety.py          # Image safety tool (3 tests)
│   └── test_text_safety.py     # Text safety classifier, fake model (11 tests)
├── compliance/tests/
│   └── test_compliance.py      # Rule transformation (5 tests)
├── iam/tests/
│   ├── test_iam.py             # Roles, permissions, ACL (14 tests)
│   └── test_tool_enforcement.py # Banking tools act as current user (33 tests)
├── escalation/tests/
│   └── test_escalation.py      # Queue, tickets, metadata, SQLite (18 tests)
└── tests/
    ├── test_db_writes_and_tool_permissions.py # DB writes, tool role checks, transfer persistence (5 tests)
    ├── test_prompt.py          # Permission-driven tool list in the prompt (22 tests)
    └── test_safety_layer1.py   # safety_check_layer1 tool output, fake model (3 tests)

tests/
├── test_agent_integration.py   # Agent wiring, prompt, decision actions (16 tests)
├── test_audit_logging.py       # Tool-call audit callback, daily rollover, log viewing (22 tests)
├── test_callbacks.py           # Pre-model safety gate (before_model_callback) (35 tests)
├── test_escalation_config.py   # Escalation threshold, COMP-004 transfer guard, custom rules (17 tests)
├── test_integration.py         # Escalation queue on a temp DB, Gemini-backed Layer 2b / decision (9 tests, 4 need credentials)
└── test_transfer_validation.py # transfer_money validation, atomic transfer, connection cleanup (27 tests)
```

## Running Tests

`pytest` is in the `dev` dependency group, which `uv run` installs by default.

### All Tests
```bash
uv run pytest -v
```

### By Pillar
```bash
# Safety (test_safety.py downloads the NSFW image model on first run)
uv run pytest scope/safety/tests/ -v

# Compliance
uv run pytest scope/compliance/tests/ -v

# IAM
uv run pytest scope/iam/tests/ -v

# Escalation
uv run pytest scope/escalation/tests/ -v

# Prompt, safety_check_layer1 tool, DB writes
uv run pytest scope/tests/ -v

# Integration
uv run pytest tests/ -v
```

### Specific Test
```bash
uv run pytest scope/iam/tests/test_iam.py::TestAccessControl::test_check_permission_allowed -v
```

## Test Coverage

### Pillar 1: Safety (14 tests)
- ✅ ImageSafetyTool initialises (processor and model loaded) and exposes `check`
- ✅ A failed image check returns an unknown result (`checked: false`), never "safe"
- ✅ TextSafetyTool: safe / toxic / severe-toxicity / threshold / empty input / model unavailable /
  long text classified in overlapping windows, max score per category
  (`scope/safety/tests/test_text_safety.py`, fake model - no download)

### `safety_check_layer1` tool (3 tests, `scope/tests/test_safety_layer1.py`)
- ✅ Safe input → `PASSED` with the toxicity score; toxic input → `FAILED` with the risk category
- ✅ Model unavailable → `SKIPPED (model not loaded)`, logged with `success: false`, never `PASSED`
- Fake classifier and mocked audit logger, no download (the config-disabled path is in `tests/test_callbacks.py`)

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
- ✅ User permission checking (USER, STAFF)
- ✅ Permission check (allowed)
- ✅ Permission check (denied)
- ✅ Permission check (raises exception)
- ✅ Escalation viewing permissions
- ✅ Escalation resolution permissions

### IAM tool enforcement (33 tests, `scope/iam/tests/test_tool_enforcement.py`)
- ✅ Case-insensitive role parsing (`parse_role`)
- ✅ Role descriptions match `ROLE_PERMISSIONS`
- ✅ USER cannot read another user's transactions or accounts, even by passing their `user_id`
- ✅ STAFF can read a customer's transactions; audit log records STAFF as the actor
- ✅ `report_fraud` only files tickets for accounts the caller may access

### Prompt tool list (22 tests, `scope/tests/test_prompt.py`)
- ✅ Every tool definition has title, call signature, notes and `Permission` values
- ✅ Each role sees only the tools its permissions allow (USER 12, STAFF 14, ADMIN 14)
- ✅ Role-specific notes ("your own" for USER, "any customer" for STAFF/ADMIN)
- ✅ Unknown roles fall back to USER; role names are case-insensitive

### DB writes and tool role checks (5 tests, `scope/tests/test_db_writes_and_tool_permissions.py`)
- ✅ `update_account` persists balance and status; `get_user_accounts` enforces ownership for USER
- ✅ `view_audit_logs` and `resolve_escalation_ticket` deny USER and allow STAFF
- ✅ `transfer_money` persists through one `Database.transfer_funds` call

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
- ✅ Default database location (path only; the real database is not opened)
- ✅ Custom database location

### Agent integration (16 tests, `tests/test_agent_integration.py`)
- ✅ Agent initialization
- ✅ Config loading (safety / compliance / escalation policy)
- ✅ Safety callback importable; shared text classifier object can be created (no behaviour checked here)
- ✅ Compliance rules loaded
- ✅ Rule transformation
- ✅ Decision prompt defines approve / reject / rewrite / escalate and requires `rewrite` for COMP-001 (mocked Gemini client)
- ✅ The model's decision is returned unchanged; a failed decision call fails safe to `escalate`
- ✅ Callback registration
- ✅ Prompt runs the safety tools in order and lists all four actions
- ✅ Prompt includes escalation handling

### Integration (9 tests, `tests/test_integration.py`)
- ✅ Ticket datetime fields; persistence and retrieval on a temporary database
- ✅ STAFF sees every user's tickets; USER sees exactly their own
- ✅ The Layer 2b prompt carries the role from the module-level config the tool reads (mocked client)
- ⏭️ Gemini-backed: STAFF request for all tickets scores as safe; USER request gets a real analysis;
  high scores → `approve`; low scores → `reject` or `escalate`. These skip without Google Cloud
  credentials and fail if the tool returned its error fallback instead of a model answer.

### Escalation & config wiring (`tests/test_escalation_config.py`)
- ✅ Decision prompt uses `GOOGLE_ESCALATION_THRESHOLD` (default 0.6) for both the escalate and approve conditions, and the configured model
- ✅ `GOOGLE_GENAI_USE_VERTEXAI` selects Vertex AI or the Gemini API client
- ✅ `create_escalation_ticket` stores the Layer 2b confidence (default 0.0, clamped to 0-1)
- ✅ COMP-004: transfers above `high_value_amount` are not executed and create a ticket; at the limit they execute; the limit follows the YAML value; an over-limit transfer from an account the caller does not own is refused without a ticket
- ✅ `report_fraud` ticket metadata is persisted
- ✅ `GOOGLE_COMPLIANCE_RULES` appended to the agent instruction (unchanged when empty); rules set in the environment, including braces, appear verbatim in the system instruction produced by ADK's instruction processing

### Audit logging (22 tests, `tests/test_audit_logging.py`)
- ✅ A `tool_call` event per tool run (checked through a scripted ADK run), with role and arguments; errors and denials marked failed; sensitive and long arguments not dumped
- ✅ `after_model_callback` logs truncated response text and function calls
- ✅ Audit and compliance logs roll over at midnight; separate logger instances do not cross-write
- ✅ `view_audit_logs` newest-first, event-type filter, access decision logged as SOC2 CC6.1
- ✅ `view_logs.py` follow mode applies filters

### Transfers (27 tests, `tests/test_transfer_validation.py`)
- ✅ Same-account transfers rejected (tool and database), no balance change
- ✅ NaN / ±inf, an int too large for a float (`10**400`), non-numeric (`"50"`, `None`, `True`), zero / negative and sub-cent (> 2 decimal places) amounts rejected before any database access
- ✅ `Database.transfer_funds` called directly rejects the same invalid amounts (e.g. `0.005`, `0.025`, NaN) with `ValueError`; nothing is written
- ✅ A failed query closes its connection (no "database is locked" on the next call)
- ✅ Debit, credit and transaction rows roll back together on failure; unknown destination does not debit; funds re-checked inside the transaction, so a transfer that passes `transfer_money`'s pre-check on an out-of-date (higher) balance is refused with nothing written
- ✅ Balances rounded to cents (ten $0.10 transfers leave exact balances)

## Test Configuration

**pytest.ini:**
- Test paths: `scope/safety/tests`, `scope/compliance/tests`, `scope/iam/tests`, `scope/escalation/tests`, `scope/tests`, `tests`
- Verbose output enabled
- Short traceback format

**Dependencies:**
- `pytest>=7.0.0` in the `dev` dependency group of `pyproject.toml` (installed by `uv run` / `uv sync` by default; not a runtime dependency)

## Notes

- Gemini-backed tests in `tests/test_integration.py` use `pytest.mark.skipif` (`requires_llm`) and run only when `GOOGLE_APPLICATION_CREDENTIALS` is set or `gcloud auth application-default login` has been run
- Tests that write rows use temporary SQLite files (`tmp_path`); no test writes to `scope/data/storage/banking.db`. Importing `scope.data.tools` (the agent's banking tools) still initialises the schema of that default database, creating an empty file if it does not exist
- `conftest.py` redirects the audit and compliance loggers to per-test temporary directories, so tests never write to `scope/logging/audit_logs` or `scope/logging/compliance_logs`
- All tests use pytest fixtures for setup/teardown
