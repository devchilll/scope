"""Unit tests for Escalation Pillar (Queue, Tickets, SQLite storage)."""

import pytest
from pathlib import Path
from scope.escalation import EscalationQueue, EscalationTicket
from scope.data import Database
from scope.iam import User, UserRole, AccessDeniedException


@pytest.fixture
def test_queue(tmp_path):
    """Create a test queue backed by a temporary banking database."""
    db = Database(str(tmp_path / "test_escalation.db"))
    yield EscalationQueue(db)


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
        assert test_queue.db.db_path is not None
        assert Path(test_queue.db.db_path).exists()
    
    def test_add_ticket(self, test_queue, sample_ticket):
        """Test adding a ticket."""
        ticket_id = test_queue.add_ticket(sample_ticket)
        assert ticket_id == sample_ticket.id
    
    def test_get_pending_tickets(self, test_queue, sample_ticket):
        """Test retrieving pending tickets."""
        test_queue.add_ticket(sample_ticket)
        staff = User("staff1", UserRole.STAFF)
        pending = test_queue.view_tickets(staff, status="pending")
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
        success = test_queue.resolve_ticket(admin, ticket_id, "Looks good")
        
        assert success is True
        resolved = test_queue.view_tickets(admin, status="resolved")
        assert any(t.id == ticket_id for t in resolved)
    
    def test_resolve_ticket_staff_allowed(self, test_queue, sample_ticket):
        """STAFF can resolve tickets (resolve_escalation_ticket tool is STAFF/ADMIN)."""
        ticket_id = test_queue.add_ticket(sample_ticket)
        
        staff = User("staff1", UserRole.STAFF)
        assert test_queue.resolve_ticket(staff, ticket_id, "Test") is True
    
    def test_resolve_ticket_user_denied(self, test_queue, sample_ticket):
        """USER cannot resolve tickets."""
        ticket_id = test_queue.add_ticket(sample_ticket)
        
        user = User("user", UserRole.USER)
        with pytest.raises(AccessDeniedException):
            test_queue.resolve_ticket(user, ticket_id, "Test")
    
    def test_get_stats(self, test_queue, sample_ticket):
        """Test queue statistics."""
        test_queue.add_ticket(sample_ticket)
        
        admin = User("admin1", UserRole.ADMIN)
        stats = test_queue.get_statistics(admin)
        assert "total" in stats
        assert "pending" in stats
        assert "resolved" in stats
        assert "avg_confidence" in stats
        assert stats["total"] >= 1


class TestDatabaseLocation:
    """Test database storage location."""
    
    def test_default_location(self):
        """Queue shares the main banking database by default."""
        queue = EscalationQueue()
        assert "data/storage" in queue.db.db_path.replace("\\", "/")
        assert queue.db.db_path.endswith("banking.db")
    
    def test_custom_location(self, tmp_path):
        """Queue uses whatever database it is given."""
        custom_path = str(tmp_path / "custom_test.db")
        queue = EscalationQueue(Database(custom_path))
        assert queue.db.db_path == custom_path


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
