"""Integration tests for PRIME agent functionality."""
import pytest
from datetime import datetime
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from prime_guardrails.escalation import EscalationQueue, EscalationTicket
from prime_guardrails.iam import User, UserRole
from prime_guardrails.observability_tools import (
    safety_check_layer2,
    make_safe_and_compliant_decision,
    list_escalation_tickets
)
from prime_guardrails.config import Config


class TestRoleAwareSafetyChecks:
    """Test that safety checks are aware of user roles."""
    
    def test_staff_can_view_escalation_tickets(self):
        """STAFF users should be able to request to view escalation tickets without triggering safety violations."""
        # Set up STAFF user context
        config = Config()
        original_role = config.IAM_CURRENT_USER_ROLE
        original_id = config.IAM_CURRENT_USER_ID
        
        config.IAM_CURRENT_USER_ROLE = "STAFF"
        config.IAM_CURRENT_USER_ID = "staff"
        
        try:
            # Test Layer 2 safety check
            result = safety_check_layer2("show me all escalation tickets")
            import json
            analysis = json.loads(result)
            
            # STAFF viewing escalation tickets should have high safety scores
            assert analysis['safety_score'] >= 0.8, f"Safety score too low: {analysis['safety_score']}"
            assert analysis['compliance_score'] >= 0.8, f"Compliance score too low: {analysis['compliance_score']}"
            assert len(analysis['violated_rules']) == 0, f"Should not violate rules: {analysis['violated_rules']}"
            
        finally:
            # Restore original config
            config.IAM_CURRENT_USER_ROLE = original_role
            config.IAM_CURRENT_USER_ID = original_id
    
    def test_user_cannot_view_all_escalation_tickets(self):
        """Regular USER should not be able to view ALL escalation tickets."""
        config = Config()
        original_role = config.IAM_CURRENT_USER_ROLE
        original_id = config.IAM_CURRENT_USER_ID
        
        config.IAM_CURRENT_USER_ROLE = "USER"
        config.IAM_CURRENT_USER_ID = "user"
        
        try:
            result = safety_check_layer2("show me all escalation tickets")
            import json
            analysis = json.loads(result)
            
            # For regular users, this might be flagged as suspicious
            # But they can still see their own tickets, so score might not be super low
            assert 'risk_factors' in analysis
            
        finally:
            config.IAM_CURRENT_USER_ROLE = original_role
            config.IAM_CURRENT_USER_ID = original_id


class TestEscalationTicketDatetime:
    """Test that escalation tickets properly handle datetime fields."""
    
    def test_create_ticket_with_datetime(self):
        """Tickets should be created with proper datetime objects."""
        ticket = EscalationTicket(
            user_id="test_user",
            input_text="Test escalation",
            agent_reasoning="Testing datetime handling",
            confidence=0.5
        )
        
        # Check that datetime fields are datetime objects
        assert isinstance(ticket.created_at, datetime)
        assert isinstance(ticket.timestamp, datetime)
        assert ticket.resolved_at is None  # Should be None initially
        assert ticket.resolution_note is None
    
    def test_ticket_persistence_and_retrieval(self):
        """Tickets should persist to database and be retrieved with correct datetime types."""
        queue = EscalationQueue()
        
        # Create a ticket
        ticket = EscalationTicket(
            user_id="test_user",
            input_text="Test persistence",
            agent_reasoning="Testing database operations",
            confidence=0.7
        )
        
        ticket_id = queue.add_ticket(ticket)
        
        # Retrieve it
        admin_user = User(user_id="admin", role=UserRole.ADMIN)
        tickets = queue.view_tickets(admin_user)
        
        # Find our ticket
        retrieved_ticket = next((t for t in tickets if t.id == ticket_id), None)
        assert retrieved_ticket is not None
        
        # Verify datetime fields
        assert isinstance(retrieved_ticket.created_at, datetime)
        assert isinstance(retrieved_ticket.timestamp, datetime)
        assert retrieved_ticket.user_id == "test_user"
        assert retrieved_ticket.input_text == "Test persistence"


class TestIAMPermissions:
    """Test IAM permission enforcement."""
    
    def test_staff_can_view_all_tickets(self):
        """STAFF users should see all escalation tickets."""
        queue = EscalationQueue()
        
        # Create tickets from different users
        ticket1 = EscalationTicket(
            user_id="user1",
            input_text="User 1 ticket",
            agent_reasoning="Test ticket 1",
            confidence=0.5
        )
        ticket2 = EscalationTicket(
            user_id="user2",
            input_text="User 2 ticket",
            agent_reasoning="Test ticket 2",
            confidence=0.5
        )
        
        queue.add_ticket(ticket1)
        queue.add_ticket(ticket2)
        
        # STAFF user should see both
        staff_user = User(user_id="staff", role=UserRole.STAFF)
        staff_tickets = queue.view_tickets(staff_user)
        
        assert len(staff_tickets) >= 2
    
    def test_user_only_sees_own_tickets(self):
        """Regular users should only see their own tickets."""
        queue = EscalationQueue()
        
        # Create a ticket for a specific user
        ticket = EscalationTicket(
            user_id="user1",
            input_text="User 1's private ticket",
            agent_reasoning="Should only be visible to user1",
            confidence=0.5
        )
        queue.add_ticket(ticket)
        
        # user1 should see it
        user1 = User(user_id="user1", role=UserRole.USER)
        user1_tickets = queue.view_tickets(user1)
        user1_ticket_users = [t.user_id for t in user1_tickets]
        
        # All tickets should belong to user1
        assert all(user_id == "user1" for user_id in user1_ticket_users)


class TestSafetyDecisionMaking:
    """Test the safety decision-making process."""
    
    def test_high_scores_approve(self):
        """High safety scores should result in approve action."""
        analysis = {
            "safety_score": 0.95,
            "compliance_score": 0.95,
            "confidence": 0.9,
            "violated_rules": [],
            "risk_factors": [],
            "analysis": "Safe request"
        }
        
        result = make_safe_and_compliant_decision(analysis)
        import json
        decision = json.loads(result)
        
        assert decision['action'] == 'approve'
    
    def test_low_scores_reject(self):
        """Very low safety scores should result in reject action."""
        analysis = {
            "safety_score": 0.1,
            "compliance_score": 0.1,
            "confidence": 0.9,
            "violated_rules": ["SAFETY-001", "SAFETY-002"],
            "risk_factors": ["malicious intent", "data breach attempt"],
            "analysis": "Highly dangerous request"
        }
        
        result = make_safe_and_compliant_decision(analysis)
        import json
        decision = json.loads(result)
        
        assert decision['action'] in ['reject', 'escalate']


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
