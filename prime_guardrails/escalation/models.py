"""Escalation data models."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import uuid

# Import UserRole from IAM module
from ..iam import UserRole


class EscalationTicket(BaseModel):
    """Represents an escalation ticket for human review."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    user_id: str  # For access control
    input_text: str
    agent_reasoning: str
    confidence: float
    status: str = "pending"  # pending, approved, rejected
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None
    resolution_timestamp: Optional[str] = None

