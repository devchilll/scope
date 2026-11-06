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

Viewing and resolving are IAM-protected: USER sees own tickets, STAFF/ADMIN see
and resolve all tickets. `add_ticket` has no permission check; tickets are
created by the agent's own tools (`create_escalation_ticket`, `report_fraud`,
and `transfer_money` for COMP-004 high-value transfers).

`metadata` holds a JSON object when the creating tool supplies one (e.g.
`{"account_id": "acc001", "type": "fraud_report"}`) and is read back as
`EscalationTicket.metadata`; otherwise it is NULL.
