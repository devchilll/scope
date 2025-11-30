"""Escalation queue using main banking database.

This module provides business logic for escalation tickets,
using the main banking database for storage.
"""

import logging
from typing import List, Optional

from ..data import Database
from ..iam import User as IAMUser, Permission, AccessControl
from .models import EscalationTicket

logger = logging.getLogger(__name__)


class EscalationQueue:
    """Escalation queue manager using main banking database."""
    
    def __init__(self, db: Optional[Database] = None):
        """Initialize escalation queue.
        
        Args:
            db: Database instance. If None, creates a new one.
        """
        self.db = db if db is not None else Database()
        logger.info(f"Escalation queue initialized with database: {self.db.db_path}")
    
    def add_ticket(self, ticket: EscalationTicket) -> str:
        """Add a new escalation ticket.
        
        Args:
            ticket: EscalationTicket to add
            
        Returns:
            Ticket ID
        """
        ticket_id = self.db.create_escalation(ticket)
        logger.info(f"Escalation ticket created: {ticket_id}")
        return ticket_id
    
    def view_tickets(
        self,
        iam_user: IAMUser,
        status: Optional[str] = None
    ) -> List[EscalationTicket]:
        """View escalation tickets (IAM-protected).
        
        Args:
            iam_user: IAM user making the request
            status: Filter by status (optional)
            
        Returns:
            List of escalation tickets
            
        Raises:
            AccessDeniedException: If user lacks permission
        """
        tickets = self.db.get_escalations(iam_user, status=status)
        logger.info(f"User {iam_user.user_id} ({iam_user.role.value}) viewed {len(tickets)} tickets")
        return tickets
    
    def resolve_ticket(
        self,
        iam_user: IAMUser,
        ticket_id: str,
        resolution: str
    ) -> bool:
        """Resolve an escalation ticket (IAM-protected).
        
        Args:
            iam_user: IAM user resolving the ticket
            ticket_id: Ticket ID
            resolution: Resolution text
            
        Returns:
            True if successful
            
        Raises:
            AccessDeniedException: If user lacks permission
        """
        success = self.db.resolve_escalation(iam_user, ticket_id, resolution)
        if success:
            logger.info(f"Ticket {ticket_id} resolved by {iam_user.user_id}")
        else:
            logger.warning(f"Failed to resolve ticket {ticket_id}")
        return success
    
    def get_statistics(self, iam_user: IAMUser) -> dict:
        """Get escalation queue statistics (IAM-protected).
        
        Args:
            iam_user: IAM user requesting statistics
            
        Returns:
            Dictionary with statistics
            
        Raises:
            AccessDeniedException: If user lacks permission
        """
        # Get all tickets user has access to
        all_tickets = self.view_tickets(iam_user)
        
        stats = {
            "total": len(all_tickets),
            "pending": len([t for t in all_tickets if t.status == "pending"]),
            "resolved": len([t for t in all_tickets if t.status == "resolved"]),
            "avg_confidence": sum(t.confidence for t in all_tickets) / len(all_tickets) if all_tickets else 0.0
        }
        
        return stats
