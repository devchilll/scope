# Audit Logging System

This directory contains the audit logging system for PRIME, which tracks all user actions, safety decisions, and system events for compliance and security monitoring.

## Components

- **`audit.py`** - Core audit logging functionality
- **`view_logs.py`** - Terminal-based log viewer and analyzer
- **`audit_logs/`** - Directory containing daily log files (JSONL format)

## Log Format

Logs are stored in JSONL (JSON Lines) format, with one JSON object per line:

```json
{
  "timestamp": "2025-11-30T15:46:38.916406",
  "event_type": "user_query",
  "user_id": "admin",
  "action": "safety_layer2_analysis",
  "success": true,
  "details": {
    "input": "can you show me the audit logs?",
    "model": "gemini-2.5-flash",
    "analysis": {
      "safety_score": 1.0,
      "compliance_score": 1.0,
      "confidence": 0.95,
      "violated_rules": [],
      "risk_factors": [],
      "analysis": "The user 'Carol Admin' has an ADMIN role..."
    }
  }
}
```

## Event Types

- **`user_query`** - User requests and agent responses
- **`account_access`** - Account balance and information access
- **`transaction_query`** - Transaction history queries
- **`safety_block`** - Requests blocked by safety system
- **`escalation_created`** - New escalation tickets
- **`escalation_resolved`** - Resolved escalation tickets

## Using the Log Viewer

### Installation

The log viewer is a standalone Python script with no additional dependencies beyond the standard library.

```bash
cd prime_guardrails/logging
python view_logs.py --help
```

### Quick Start

```bash
# View all logs from today
python view_logs.py

# View last 10 entries with details
python view_logs.py --tail 10 --verbose

# Show summary statistics
python view_logs.py --summary
```

### Filtering Options

```bash
# Filter by user
python view_logs.py --user admin
python view_logs.py --user user1

# Filter by action (partial match)
python view_logs.py --action safety_decision
python view_logs.py --action resolved
python view_logs.py --action escalation

# Filter by event type
python view_logs.py --event user_query
python view_logs.py --event escalation_created
python view_logs.py --event safety_block

# View specific date
python view_logs.py --date 2025-11-30

# Combine filters
python view_logs.py --user admin --action safety --tail 20 --verbose
```

### Display Modes

```bash
# Compact view (default) - one line per entry
python view_logs.py

# Verbose view - shows full details, reasoning, analysis
python view_logs.py --verbose
python view_logs.py -v

# Summary only - statistics and counts
python view_logs.py --summary
python view_logs.py -s
```

### Real-Time Monitoring

```bash
# Follow mode (like tail -f)
python view_logs.py --follow
python view_logs.py -f

# Follow with verbose output
python view_logs.py --follow --verbose
```

## Common Use Cases

### 1. Monitor Admin Activity

Track what administrators are doing:

```bash
python view_logs.py --user admin --verbose
```

### 2. Audit Safety Decisions

Review how the safety system is making decisions:

```bash
python view_logs.py --action safety_decision --verbose
```

### 3. Investigate Escalations

See what requests are being escalated and why:

```bash
python view_logs.py --event escalation_created --verbose
```

### 4. Check for Failures

Find and investigate failed operations:

```bash
python view_logs.py --action failed --verbose
```

### 5. Real-Time Debugging

Watch logs as they happen during development/testing:

```bash
python view_logs.py --follow --verbose
```

### 6. Daily Compliance Report

Generate a summary of the day's activity:

```bash
python view_logs.py --summary
```

### 7. User Activity Audit

Review a specific user's actions:

```bash
python view_logs.py --user user1 --verbose
```

## Output Examples

### Compact View

```
15:46:13 ✓ user_query            admin    llm_response
15:46:31 ✓ user_query            admin    safety_layer1_check
15:46:38 ✓ user_query            admin    safety_layer2_analysis
```

### Verbose View

```
15:46:38 ✓ user_query            admin    safety_layer2_analysis
  Input: can you show me the audit logs?
  Safety: 1.00
  Analysis: The user 'Carol Admin' has an ADMIN role, which grants full access...

15:46:44 ✓ user_query            admin    safety_decision_made
  Decision: approve
  Reasoning: The user 'Carol Admin' has an ADMIN role. The request to view audit logs...
```

### Summary Output

```
=== Summary ===
Total entries: 50
Success: 48 | Failures: 2

Event Types:
  user_query                         30
  account_access                     10
  escalation_created                  5
  safety_block                        3
  escalation_resolved                 2

Users:
  admin                              25
  user                               15
  staff                              10
```

## Color Coding

The log viewer uses colors to make information easier to scan:

- **Green ✓** - Successful operations
- **Red ✗** - Failed operations
- **Cyan** - User queries
- **Yellow** - Safety checks and warnings
- **Blue** - Account access
- **Magenta** - Transactions
- **Red background** - Safety blocks
- **Green** - Approved decisions
- **Red** - Rejected decisions

## Tips

1. **Start with summary** to get an overview:
   ```bash
   python view_logs.py --summary
   ```

2. **Use tail for recent activity**:
   ```bash
   python view_logs.py --tail 20 --verbose
   ```

3. **Follow mode for debugging**:
   ```bash
   python view_logs.py --follow --verbose
   ```

4. **Combine filters for specific investigations**:
   ```bash
   python view_logs.py --user admin --action escalation --verbose
   ```

5. **Check different dates for historical analysis**:
   ```bash
   python view_logs.py --date 2025-11-29 --summary
   ```

## Compliance and Security

The audit logging system captures:

- **WHO**: User ID and role
- **WHAT**: Action performed
- **WHEN**: Timestamp (ISO format)
- **WHY**: Reasoning and analysis from safety system
- **RESULT**: Success/failure and details

This provides a complete audit trail for:
- SOC2 compliance
- PCI-DSS requirements
- GDPR accountability
- Security incident investigation
- User behavior analysis
- System debugging

## Log Retention

Logs are stored in daily files (`audit_YYYY-MM-DD.jsonl`) and should be:
- Retained according to compliance requirements (typically 90 days minimum)
- Backed up regularly
- Protected with appropriate access controls
- Reviewed periodically for security incidents

## Programmatic Access

You can also read logs programmatically:

```python
import json
from pathlib import Path

log_file = Path("audit_logs/audit_2025-11-30.jsonl")

with open(log_file) as f:
    for line in f:
        entry = json.loads(line)
        print(f"{entry['timestamp']} - {entry['user_id']} - {entry['action']}")
```
