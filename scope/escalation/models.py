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
    timestamp: datetime = Field(default_factory=lambda: datetime.now())  # Legacy field, same as created_at
    user_id: str  # For access control
    input_text: str
    agent_reasoning: str
    confidence: float
    status: str = "pending"  # pending, approved, rejected
    resolved_by: Optional[str] = None
    resolution_note: Optional[str] = None
    resolution_timestamp: Optional[datetime] = None  # When ticket was resolved
    created_at: datetime = Field(default_factory=lambda: datetime.now())  # datetime of creation
    updated_at: Optional[datetime] = None  # datetime of last update
    
    # Add resolved_at as an alias for resolution_timestamp for database compatibility
    @property
    def resolved_at(self) -> Optional[datetime]:
        """Alias for resolution_timestamp for database compatibility."""
        return self.resolution_timestamp
    
    @property
    def resolution(self) -> Optional[str]:
        """Alias for resolution_note for database compatibility."""
        return self.resolution_note
    
    @property
    def metadata(self) -> Optional[dict]:
        """Metadata field for database compatibility."""
        return None

