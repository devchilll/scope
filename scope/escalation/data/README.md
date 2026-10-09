# Escalation Queue Data

Escalation tickets are stored in the `escalations` table of the main banking
database (`scope/data/storage/banking.db`), not in a separate file. This
directory is kept only for test databases (`*.db`, ignored by git).

## Schema

```sql
CREATE TABLE escalations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    input_text TEXT NOT NULL,
    agent_reasoning TEXT NOT NULL,
    confidence REAL NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    resolved_at TEXT,
    resolved_by TEXT,
    resolution TEXT,
    metadata TEXT
);
```

## Access

```python
from scope.escalation import EscalationQueue
from scope.data import Database

queue = EscalationQueue()                      # shares the banking database
queue = EscalationQueue(Database("custom.db")) # custom location (tests)
```

All queue operations are IAM-protected: USER sees own tickets, STAFF/ADMIN see
and resolve all tickets.
