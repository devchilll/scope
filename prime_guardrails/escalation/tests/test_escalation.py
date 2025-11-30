"""Unit tests for Escalation Pillar (Queue, Tickets, SQLite storage)."""

import pytest
from pathlib import Path
from prime_guardrails.escalation import EscalationQueue, EscalationTicket
from prime_guardrails.iam import User, UserRole, AccessDeniedException


@pytest.fixture
def test_queue():
    """Create a test queue with temporary database."""
    test_db = Path(__file__).parent / "test_escalation.db"
    queue = EscalationQueue(str(test_db))
    yield queue
    # Cleanup
    test_db.unlink(missing_ok=True)


@pytest.fixture
def sample_ticket():
    """Create a sample escalation ticket."""
    return EscalationTicket(
        user_id="user",
        input_text="Test question",
        agent_reasoning="Uncertain",
        confidence=0.55
    )


class TestEscalationTicket:
    """Test EscalationTicket model."""
    
    def test_ticket_creation(self, sample_ticket):
        """Test creating a ticket."""
        assert sample_ticket.user_id == "user"
        assert sample_ticket.input_text == "Test question"
        assert sample_ticket.confidence == 0.55
        assert sample_ticket.status == "pending"
    
    def test_ticket_auto_fields(self, sample_ticket):
        """Test auto-generated fields."""
        assert sample_ticket.id is not None
        assert sample_ticket.timestamp is not None
        assert len(sample_ticket.id) > 0
    
    def test_ticket_optional_fields(self, sample_ticket):
        """Test optional fields default to None."""
        assert sample_ticket.resolved_by is None
        assert sample_ticket.resolution_note is None
        assert sample_ticket.resolution_timestamp is None


class TestEscalationQueue:
    """Test EscalationQueue functionality."""
    
    def test_queue_initialization(self, test_queue):
        """Test queue initializes correctly."""
        assert test_queue.db_path is not None
        assert Path(test_queue.db_path).exists()
    
    def test_add_ticket(self, test_queue, sample_ticket):
        """Test adding a ticket."""
        ticket_id = test_queue.add_ticket(sample_ticket)
        assert ticket_id == sample_ticket.id
    
    def test_get_pending_tickets(self, test_queue, sample_ticket):
        """Test retrieving pending tickets."""
        test_queue.add_ticket(sample_ticket)
        pending = test_queue.get_pending_tickets()
        assert len(pending) >= 1
        assert all(t.status == "pending" for t in pending)
    
    def test_view_tickets_user(self, test_queue, sample_ticket):
        """Test USER can only see own tickets."""
        test_queue.add_ticket(sample_ticket)
        
        user = User("user", UserRole.USER)
        tickets = test_queue.view_tickets(user)
        
        assert all(t.user_id == "user" for t in tickets)
    
    def test_view_tickets_staff(self, test_queue, sample_ticket):
        """Test STAFF can see all tickets."""
        test_queue.add_ticket(sample_ticket)
        
        staff = User("staff1", UserRole.STAFF)
        tickets = test_queue.view_tickets(staff)
        
        assert len(tickets) >= 1
    
    def test_view_tickets_admin(self, test_queue, sample_ticket):
        """Test ADMIN can see all tickets."""
        test_queue.add_ticket(sample_ticket)
        
        admin = User("admin1", UserRole.ADMIN)
        tickets = test_queue.view_tickets(admin)
        
        assert len(tickets) >= 1
    
    def test_resolve_ticket_admin(self, test_queue, sample_ticket):
        """Test ADMIN can resolve tickets."""
        ticket_id = test_queue.add_ticket(sample_ticket)
        
        admin = User("admin1", UserRole.ADMIN)
        success = test_queue.resolve_ticket(
            admin, ticket_id, "approved", "Looks good"
        )
        
        assert success is True
    
    def test_resolve_ticket_staff_denied(self, test_queue, sample_ticket):
        """Test STAFF cannot resolve tickets."""
        ticket_id = test_queue.add_ticket(sample_ticket)
        
        staff = User("staff1", UserRole.STAFF)
        with pytest.raises(AccessDeniedException):
            test_queue.resolve_ticket(
                staff, ticket_id, "approved", "Test"
            )
    
    def test_get_stats(self, test_queue, sample_ticket):
        """Test queue statistics."""
        test_queue.add_ticket(sample_ticket)
        
        stats = test_queue.get_stats()
        assert "total" in stats
        assert "pending" in stats
        assert "approved" in stats
        assert "avg_confidence" in stats
        assert stats["total"] >= 1


class TestDatabaseLocation:
    """Test database storage location."""
    
    def test_default_location(self):
        """Test default database location."""
        queue = EscalationQueue()
        assert "escalation/data" in queue.db_path
        assert queue.db_path.endswith("escalations.db")
    
    def test_custom_location(self):
        """Test custom database location."""
        custom_path = "custom_test.db"
        queue = EscalationQueue(custom_path)
        assert queue.db_path == custom_path
        # Cleanup
        Path(custom_path).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
