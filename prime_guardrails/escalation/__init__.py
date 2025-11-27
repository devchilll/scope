"""Escalation module for PRIME guardrails.

This package contains escalation queue management with SQLite storage.
"""

from .queue import EscalationQueue
from .models import EscalationTicket
from ..iam import UserRole, User

__all__ = ['EscalationQueue', 'EscalationTicket', 'UserRole', 'User']

