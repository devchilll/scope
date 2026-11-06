# Observability & Auditing Strategy for SCOPE Banking Agent

## Current Implementation ✅

### 1. **Flow Logging** (Daily Files)
- **Location**: `scope/logging/audit_logs/audit_YYYY-MM-DD.jsonl` (the dated file is resolved on every write, so a long-running `adk web` rolls over to a new file at midnight)
- **Captures**:
  - User input: the new message of each turn (once per turn), truncated to 500 chars (`before_model_callback`)
  - Layer 2a safety-check results (toxic-bert scores) and safety blocks (`before_model_callback`), including screening errors (`success: false`; the request is refused and logged as a `safety_block` with risk category `screening_error`)
  - LLM responses: response text truncated to 500 chars plus the names of any tools the model asked to call (`after_model_callback`). The full prompt sent to the LLM is not logged.
  - Every tool call, as a `tool_call` event: tool name, arguments (sensitive-looking keys redacted, long strings truncated), user ID and role, and success / error (`after_tool_callback`; tools that raise are logged by `on_tool_error_callback`). Error and permission-denied responses are recorded as `success: false`.
  - Domain events written by the tools themselves: account access, transaction queries, transfers, fraud reports, escalation tickets, Layer 2b safety analyses and decisions
  - Final agent responses only when the model calls the optional `log_agent_response` tool; this is not guaranteed for every turn
- **Format**: Structured JSON (one event per line)

### 2. **Compliance Logging** (PCI-DSS, SOC2)
- **PCI-DSS Logs**: `compliance_logs/pci_dss_YYYY-MM-DD.jsonl`
- **SOC2 Logs**: `compliance_logs/soc2_YYYY-MM-DD.jsonl`

`scope/logging/compliance_log.py` defines one method per category. Only some are called by the agent today:

| Category | Method | Written today? |
|----------|--------|----------------|
| PCI-DSS data access (Req. 10.2) | `log_pci_data_access` | ✅ `get_account_balance`, `get_transaction_history`, `transfer_money` |
| SOC2 access control (CC6.1) | `log_soc2_access_control` | ✅ `view_audit_logs` only (its `VIEW_LOGS` decision, granted or denied). Other tools' denials show up in the audit trail as failed `tool_call` events, not in the SOC2 log. |
| SOC2 security incidents (CC7.3) | `log_soc2_incident` | ✅ `report_fraud` |
| PCI-DSS authentication (Req. 10.2.4) | `log_pci_authentication` | ❌ Defined, not called (there is no login flow; the user comes from `GOOGLE_IAM_CURRENT_USER_*` config) |
| PCI-DSS privileged actions (Req. 10.2.2) | `log_pci_privileged_action` | ❌ Defined, not called |
| SOC2 data processing (CC6.7) | `log_soc2_data_processing` | ❌ Defined, not called |
| General data retention | `log_data_retention` | ❌ Defined, not called |

### 3. **IAM Access Control**
- Every agent-facing banking tool checks the caller's role and account ownership
- Access denied exceptions logged

### 4. **Escalation Queue**
- SQLite database for human review tickets
- Fraud reports automatically escalated

---

## Additional Observability & Auditing Recommendations

### 5. **Metrics & Monitoring** (To Implement)

#### **Key Metrics to Track:**
```python
# Response time metrics
- p50, p95, p99 latency for:
  - Safety checks
  - LLM calls
  - Tool calls
  - End-to-end request

# Volume metrics
- Requests per minute/hour/day
- Safety blocks per day
- Escalations per day
- Tool calls per day

# Error metrics
- Failed safety checks
- Failed tool calls
- LLM errors
- Database errors

# Business metrics
- Accounts accessed per day
- Fraud reports per day
- Customer satisfaction (if available)
```

**Implementation**: Use Prometheus + Grafana or Google Cloud Monitoring

---

### 6. **Distributed Tracing** (Partly Built In)

**Tool**: OpenTelemetry

**Available today (from ADK, no SCOPE code):** ADK emits OpenTelemetry spans for each agent invocation, LLM call and tool execution. `adk web` shows them in its Trace tab, and `adk web --trace_to_cloud` exports them to Google Cloud Trace.

**Available today (SCOPE):** the pre-model safety gate runs inside its own `scope.pre_model_safety_gate` span (blocked/allowed, max score, risk category).

**Still to implement:** a request ID shared between spans and the JSONL audit events, finer-grained spans inside tools (IAM check, database query), and an export pipeline for production.

**Target trace shape (illustrative, not measured):**
```
Request ID: abc123
├─ Safety Check
│  └─ ML Model Inference
├─ LLM Call
│  ├─ Prompt Construction
│  ├─ Vertex AI API
│  └─ Response Parsing
├─ Tool Call: get_account_balance
│  ├─ IAM Check
│  ├─ Database Query
│  └─ Audit Logging
└─ Total
```

**Benefits:**
- Identify bottlenecks
- Debug production issues
- Understand user journey

---

### 7. **Session Management** (To Implement)

**Track per session:**
```json
{
  "session_id": "sess_abc123",
  "user_id": "user123",
  "start_time": "2025-11-28T13:00:00Z",
  "end_time": "2025-11-28T13:15:00Z",
  "interactions": 5,
  "tools_used": ["get_account_balance", "get_transaction_history"],
  "safety_blocks": 0,
  "escalations": 0,
  "total_cost": "$0.05"
}
```

**Benefits:**
- User behavior analysis
- Cost attribution
- Session replay for debugging

---

### 8. **Error Tracking** (To Implement)

**Tool**: Sentry or Google Cloud Error Reporting

**What to track:**
- Unhandled exceptions
- Failed tool calls
- LLM errors
- Database connection issues
- IAM access denials

**Alert on:**
- Error rate > 5%
- Specific critical errors (database down, LLM unavailable)

---

### 9. **Cost Tracking** (To Implement)

**Track per request:**
```json
{
  "request_id": "req_abc123",
  "user_id": "user123",
  "llm_calls": 1,
  "tokens_input": 500,
  "tokens_output": 200,
  "cost_llm": "$0.001",
  "cost_ml_models": "$0.0001",
  "total_cost": "$0.0011"
}
```

**Aggregate:**
- Cost per user
- Cost per day/month
- Cost by tool
- Cost by model

---

### 10. **Data Retention & Archival**

**Policy:**
```
Hot storage (7 days):
- All logs in JSONL files
- Fast query access

Warm storage (30 days):
- Compressed logs
- Slower query access

Cold storage (7 years for compliance):
- Archived to cloud storage
- Compliance requirement for financial data
```

**Implementation:**
```bash
# Daily cron job
0 0 * * * /path/to/archive_logs.sh
```

---

### 11. **Alerting** (To Implement)

**Critical Alerts:**
- Database connection failure
- LLM API unavailable
- Error rate > 10%
- Fraud report spike (>10 in 1 hour)
- Escalation queue backlog (>100 tickets)

**Warning Alerts:**
- Response time p95 > 5s
- Safety block rate > 20%
- Cost spike (>2x daily average)

**Tool**: PagerDuty, Opsgenie, or Google Cloud Monitoring

---

### 12. **Audit Log Analysis** (To Implement)

**Daily Reports:**
- Total requests
- Top users
- Top tools used
- Safety blocks by category
- Compliance violations
- Escalations by reason

**Weekly Reports:**
- Trends over time
- Anomaly detection
- Cost analysis
- User satisfaction

**Tool**: Custom Python scripts or BI tools (Looker, Tableau)

---

### 13. **Security Monitoring** (To Implement)

**Monitor for:**
- Brute force attempts (multiple failed auth)
- Unusual access patterns (accessing many accounts)
- Data exfiltration attempts
- Privilege escalation attempts

**Tool**: SIEM (Security Information and Event Management)
- Splunk
- Google Chronicle
- Elastic Security

---

### 14. **Real-time Dashboard** (To Implement)

**Metrics to display:**
- Requests per minute (live graph)
- Active sessions
- Error rate
- Average response time
- Safety blocks (last hour)
- Escalation queue size
- System health (green/yellow/red)

**Tool**: Grafana or custom React dashboard

---

## Implementation Priority

### **Phase 1: Essential** (Implement Now)
1. ✅ Flow logging (user input → safety check → LLM response → tool calls)
2. ✅ Compliance logging (PCI-DSS, SOC2), partial: see the table in section 2
3. ✅ IAM access control
4. ✅ Escalation queue

### **Phase 2: Production-Ready** (Next 2 weeks)
5. Metrics & monitoring (Prometheus + Grafana)
6. Error tracking (Sentry)
7. Alerting (critical alerts only)
8. Session management

### **Phase 3: Scale & Optimize** (Next month)
9. Distributed tracing: request IDs and custom spans on top of ADK's built-in OpenTelemetry spans
10. Cost tracking
11. Data retention & archival
12. Audit log analysis

### **Phase 4: Advanced** (Future)
13. Security monitoring (SIEM)
14. Real-time dashboard
15. ML-based anomaly detection
16. Automated incident response

---

## Quick Wins

### **Today:**
- ✅ All logs in daily files (YYYY-MM-DD format), rolling over at midnight
- ✅ Structured JSON format
- ✅ Simple log viewer script (`scope/logging/view_logs.py`)

### **This Week:**
- Add request IDs to all logs
- Add session tracking

### **Next Week:**
- Set up basic Grafana dashboard
- Configure critical alerts
- Implement log retention / archival (see section 10)

---

## Log Viewer Script (Quick Win)

`scope/logging/view_logs.py` filters and colorizes the audit log (see `scope/logging/README.md`). The same queries with plain `jq`:

```bash
# View today's audit logs
tail -f scope/logging/audit_logs/audit_$(date +%Y-%m-%d).jsonl | jq '.'

# Search for specific user
cat audit_*.jsonl | jq 'select(.user_id == "user123")'

# Count events by type
cat audit_*.jsonl | jq -r '.event_type' | sort | uniq -c

# Find all safety blocks
cat audit_*.jsonl | jq 'select(.event_type == "safety_block")'
```

Sections 1-4 describe what the code does today; sections 5 onward are recommendations for a production deployment.
