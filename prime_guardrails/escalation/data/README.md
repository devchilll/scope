# Escalation Queue Data

This directory stores SQLite databases for the escalation queue.

## Files

- `escalations.db` - Production escalation queue database
- `*.db` - Test databases (ignored by git)

## Database Schema

```sql
CREATE TABLE escalations (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    user_id TEXT NOT NULL,
    input_text TEXT NOT NULL,
    agent_reasoning TEXT NOT NULL,
    confidence REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    resolved_by TEXT,
    resolution_note TEXT,
    resolution_timestamp TEXT
);

CREATE INDEX idx_user_id ON escalations(user_id);
CREATE INDEX idx_status ON escalations(status);
```

## Access

Use the `EscalationQueue` class to interact with the database:

```python
from prime_guardrails.escalation import EscalationQueue

# Default location: prime_guardrails/escalation/data/escalations.db
queue = EscalationQueue()

# Custom location
queue = EscalationQueue("custom_path.db")
```
