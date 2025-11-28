"""Audit logging for banking application.

This module provides comprehensive audit logging for all agent actions,
tool calls, and database operations for compliance (PCI-DSS, SOC2).
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
from enum import Enum


class AuditEventType(Enum):
    """Types of audit events."""
    USER_QUERY = "user_query"
    ACCOUNT_ACCESS = "account_access"
    TRANSACTION_QUERY = "transaction_query"
    TOOL_CALL = "tool_call"
    SAFETY_BLOCK = "safety_block"
    COMPLIANCE_VIOLATION = "compliance_violation"
    ESCALATION_CREATED = "escalation_created"
    ESCALATION_RESOLVED = "escalation_resolved"
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"


class AuditLogger:
    """Audit logger for compliance and security tracking."""
    
    def __init__(self, log_dir: Optional[str] = None):
        """Initialize audit logger.
        
        Args:
            log_dir: Directory for audit logs. If None, uses default location.
        """
        if log_dir is None:
            log_dir = Path(__file__).parent / "audit_logs"
        else:
            log_dir = Path(log_dir)
        
        log_dir.mkdir(exist_ok=True)
        self.log_dir = log_dir
        
        # Create rotating log file (one per day)
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"audit_{today}.jsonl"
        
        # Configure logger
        self.logger = logging.getLogger("prime.audit")
        self.logger.setLevel(logging.INFO)
        
        # File handler for JSON logs
        handler = logging.FileHandler(log_file)
        handler.setLevel(logging.INFO)
        self.logger.addHandler(handler)
    
    def log_event(
        self,
        event_type: AuditEventType,
        user_id: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error: Optional[str] = None
    ):
        """Log an audit event.
        
        Args:
            event_type: Type of event
            user_id: User ID performing the action
            action: Description of the action
            details: Additional event details
            success: Whether the action succeeded
            error: Error message if action failed
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type.value,
            "user_id": user_id,
            "action": action,
            "success": success,
            "details": details or {},
        }
        
        if error:
            event["error"] = error
        
        # Log as JSON for structured logging
        self.logger.info(json.dumps(event))
    
    def log_user_query(self, user_id: str, query: str, response_action: str):
        """Log a user query and agent response.
        
        Args:
            user_id: User ID
            query: User's query
            response_action: Agent's action (ALLOW, REFUSE, REWRITE, ESCALATE)
        """
        self.log_event(
            event_type=AuditEventType.USER_QUERY,
            user_id=user_id,
            action="user_query",
            details={
                "query": query[:200],  # Truncate for privacy
                "response_action": response_action
            }
        )
    
    def log_account_access(self, user_id: str, account_id: str, operation: str):
        """Log account access.
        
        Args:
            user_id: User ID
            account_id: Account ID accessed
            operation: Operation performed (view, update, etc.)
        """
        self.log_event(
            event_type=AuditEventType.ACCOUNT_ACCESS,
            user_id=user_id,
            action=f"account_{operation}",
            details={
                "account_id": account_id,
                "operation": operation
            }
        )
    
    def log_transaction_query(self, user_id: str, account_id: str, days: int):
        """Log transaction history query.
        
        Args:
            user_id: User ID
            account_id: Account ID
            days: Number of days queried
        """
        self.log_event(
            event_type=AuditEventType.TRANSACTION_QUERY,
            user_id=user_id,
            action="query_transactions",
            details={
                "account_id": account_id,
                "days": days
            }
        )
    
    def log_tool_call(
        self, 
        user_id: str, 
        tool_name: str, 
        parameters: Dict[str, Any],
        result: Optional[str] = None,
        error: Optional[str] = None
    ):
        """Log a tool call.
        
        Args:
            user_id: User ID
            tool_name: Name of the tool called
            parameters: Tool parameters
            result: Tool result summary
            error: Error message if tool failed
        """
        self.log_event(
            event_type=AuditEventType.TOOL_CALL,
            user_id=user_id,
            action=f"tool_call_{tool_name}",
            details={
                "tool_name": tool_name,
                "parameters": parameters,
                "result": result
            },
            success=error is None,
            error=error
        )
    
    def log_safety_block(self, user_id: str, input_text: str, risk_category: str):
        """Log a safety block event.
        
        Args:
            user_id: User ID
            input_text: Blocked input
            risk_category: Risk category detected
        """
        self.log_event(
            event_type=AuditEventType.SAFETY_BLOCK,
            user_id=user_id,
            action="safety_block",
            details={
                "input_text": input_text[:100],  # Truncate
                "risk_category": risk_category
            }
        )
    
    def log_compliance_violation(
        self, 
        user_id: str, 
        violated_rule: str,
        query: str
    ):
        """Log a compliance violation.
        
        Args:
            user_id: User ID
            violated_rule: Rule that was violated
            query: User's query
        """
        self.log_event(
            event_type=AuditEventType.COMPLIANCE_VIOLATION,
            user_id=user_id,
            action="compliance_violation",
            details={
                "violated_rule": violated_rule,
                "query": query[:200]
            }
        )
    
    def log_escalation(
        self, 
        user_id: str, 
        ticket_id: str,
        reason: str,
        resolved: bool = False,
        resolution: Optional[str] = None
    ):
        """Log an escalation event.
        
        Args:
            user_id: User ID
            ticket_id: Escalation ticket ID
            reason: Reason for escalation
            resolved: Whether this is a resolution event
            resolution: Resolution details
        """
        event_type = (
            AuditEventType.ESCALATION_RESOLVED if resolved 
            else AuditEventType.ESCALATION_CREATED
        )
        
        details = {
            "ticket_id": ticket_id,
            "reason": reason
        }
        
        if resolved and resolution:
            details["resolution"] = resolution
        
        self.log_event(
            event_type=event_type,
            user_id=user_id,
            action="escalation_resolved" if resolved else "escalation_created",
            details=details
        )


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
