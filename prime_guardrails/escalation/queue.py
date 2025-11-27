"""SQLite-based escalation queue for human-in-the-loop review.

This module provides a production-ready escalation queue using SQLite
as a local database, mimicking what could be an MCP database or other
production storage system.
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from .models import EscalationTicket, UserRole
from ..iam import User, AccessControl, Permission


class EscalationQueue:
    """Escalation queue with SQLite storage and IAM access control.
    
    This implementation uses SQLite to store escalation tickets and
    enforces role-based access control via the IAM module.
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """Initialize the escalation queue with SQLite storage.
        
        Args:
            db_path: Path to SQLite database file. If None, uses default location
                    in prime_guardrails/escalation/data/escalations.db
        """
        if db_path is None:
            # Default to data/ subdirectory within escalation package
            data_dir = Path(__file__).parent / "data"
            data_dir.mkdir(exist_ok=True)
            db_path = str(data_dir / "escalations.db")
        
        self.db_path = db_path
        self._init_database()

    
    def _init_database(self):
        """Initialize the SQLite database schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS escalations (
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
            )
        """)
        
        # Create indexes for common queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id 
            ON escalations(user_id)
        """)
        
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status 
            ON escalations(status)
        """)
        
        conn.commit()
        conn.close()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn
    
    # Agent Interface
    
    def add_ticket(self, ticket: EscalationTicket) -> str:
        """Agent adds a new escalation ticket.
        
        Args:
            ticket: The escalation ticket to add
            
        Returns:
            The ticket ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO escalations 
            (id, timestamp, user_id, input_text, agent_reasoning, 
             confidence, status, resolved_by, resolution_note, resolution_timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ticket.id,
            ticket.timestamp,
            ticket.user_id,
            ticket.input_text,
            ticket.agent_reasoning,
            ticket.confidence,
            ticket.status,
            ticket.resolved_by,
            ticket.resolution_note,
            ticket.resolution_timestamp
        ))
        
        conn.commit()
        conn.close()
        
        return ticket.id
    
    def get_pending_tickets(self) -> List[EscalationTicket]:
        """Agent reads all pending escalation tickets.
        
        Returns:
            List of tickets with status='pending'
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM escalations 
            WHERE status = 'pending'
            ORDER BY timestamp DESC
        """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_ticket(row) for row in rows]
    
    # Human Interface with IAM Access Control
    
    def view_tickets(self, user: User) -> List[EscalationTicket]:
        """Human views tickets based on their role (IAM-controlled).
        
        Args:
            user: User requesting access (with IAM role)
            
        Returns:
            List of tickets the user has access to
            
        Raises:
            AccessDeniedException: If user lacks permission
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Check permissions based on role
        if user.role == UserRole.USER:
            # Regular users only see their own tickets
            AccessControl.check_permission(user, Permission.VIEW_OWN_ESCALATIONS)
            cursor.execute("""
                SELECT * FROM escalations 
                WHERE user_id = ?
                ORDER BY timestamp DESC
            """, (user.user_id,))
            
        elif user.role == UserRole.STAFF:
            # Staff can view all tickets (read-only)
            AccessControl.check_permission(user, Permission.VIEW_ALL_ESCALATIONS)
            cursor.execute("""
                SELECT * FROM escalations 
                ORDER BY timestamp DESC
            """)
            
        elif user.role in [UserRole.ADMIN, UserRole.SYSTEM]:
            # Admin/System see all tickets
            AccessControl.check_permission(user, Permission.VIEW_ALL_ESCALATIONS)
            cursor.execute("""
                SELECT * FROM escalations 
                ORDER BY timestamp DESC
            """)
        
        rows = cursor.fetchall()
        conn.close()
        
        return [self._row_to_ticket(row) for row in rows]
    
    def resolve_ticket(
        self, 
        user: User,
        ticket_id: str, 
        decision: str, 
        note: str
    ) -> bool:
        """Admin resolves an escalation ticket (IAM-controlled).
        
        Args:
            user: User attempting to resolve (must be ADMIN)
            ticket_id: ID of the ticket to resolve
            decision: Resolution decision (e.g., 'approved', 'rejected')
            note: Admin's resolution note
            
        Returns:
            True if ticket was found and resolved, False otherwise
            
        Raises:
            AccessDeniedException: If user is not ADMIN
        """
        # Only ADMIN can resolve tickets
        AccessControl.check_permission(user, Permission.RESOLVE_ESCALATIONS)
        
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE escalations 
            SET status = ?,
                resolved_by = ?,
                resolution_note = ?,
                resolution_timestamp = ?
            WHERE id = ?
        """, (
            decision,
            user.user_id,  # Use the user's ID
            note,
            datetime.now().isoformat(),
            ticket_id
        ))
        
        rows_affected = cursor.rowcount
        conn.commit()
        conn.close()
        
        return rows_affected > 0
    
    def get_stats(self) -> dict:
        """Get statistics about the escalation queue.
        
        Returns:
            Dictionary with queue statistics
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get counts by status
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'approved' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected,
                AVG(confidence) as avg_confidence
            FROM escalations
        """)
        
        row = cursor.fetchone()
        conn.close()
        
        return {
            "total": row["total"] or 0,
            "pending": row["pending"] or 0,
            "approved": row["approved"] or 0,
            "rejected": row["rejected"] or 0,
            "avg_confidence": row["avg_confidence"] or 0.0
        }
    
    def _row_to_ticket(self, row: sqlite3.Row) -> EscalationTicket:
        """Convert a database row to an EscalationTicket.
        
        Args:
            row: SQLite row object
            
        Returns:
            EscalationTicket instance
        """
        return EscalationTicket(
            id=row["id"],
            timestamp=row["timestamp"],
            user_id=row["user_id"],
            input_text=row["input_text"],
            agent_reasoning=row["agent_reasoning"],
            confidence=row["confidence"],
            status=row["status"],
            resolved_by=row["resolved_by"],
            resolution_note=row["resolution_note"],
            resolution_timestamp=row["resolution_timestamp"]
        )
