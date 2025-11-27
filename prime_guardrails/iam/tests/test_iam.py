"""Unit tests for IAM Pillar (Roles, Permissions, Access Control)."""

import pytest
from prime_guardrails.iam import (
    User, UserRole, Permission, AccessControl, 
    AccessDeniedException
)
from prime_guardrails.iam.roles import has_permission, get_permissions


class TestUserRoles:
    """Test user role definitions."""
    
    def test_user_role_enum(self):
        """Test UserRole enum values."""
        assert UserRole.USER.value == "user"
        assert UserRole.STAFF.value == "staff"
        assert UserRole.ADMIN.value == "admin"
        assert UserRole.SYSTEM.value == "system"
    
    def test_permission_enum(self):
        """Test Permission enum has expected values."""
        assert Permission.VIEW_OWN_ESCALATIONS
        assert Permission.VIEW_ALL_ESCALATIONS
        assert Permission.RESOLVE_ESCALATIONS
        assert Permission.USE_AGENT


class TestPermissions:
    """Test permission mappings."""
    
    def test_user_permissions(self):
        """Test USER role permissions."""
        perms = get_permissions(UserRole.USER)
        assert Permission.USE_AGENT in perms
        assert Permission.VIEW_OWN_ESCALATIONS in perms
        assert Permission.VIEW_ALL_ESCALATIONS not in perms
        assert Permission.RESOLVE_ESCALATIONS not in perms
    
    def test_staff_permissions(self):
        """Test STAFF role permissions."""
        perms = get_permissions(UserRole.STAFF)
        assert Permission.VIEW_ALL_ESCALATIONS in perms
        assert Permission.RESOLVE_ESCALATIONS not in perms
    
    def test_admin_permissions(self):
        """Test ADMIN role permissions."""
        perms = get_permissions(UserRole.ADMIN)
        assert Permission.VIEW_ALL_ESCALATIONS in perms
        assert Permission.RESOLVE_ESCALATIONS in perms
        assert Permission.MODIFY_COMPLIANCE_RULES in perms
    
    def test_has_permission_function(self):
        """Test has_permission helper function."""
        assert has_permission(UserRole.USER, Permission.USE_AGENT)
        assert not has_permission(UserRole.USER, Permission.RESOLVE_ESCALATIONS)
        assert has_permission(UserRole.ADMIN, Permission.RESOLVE_ESCALATIONS)


class TestUser:
    """Test User class."""
    
    def test_user_creation(self):
        """Test creating a user."""
        user = User("user123", UserRole.USER, "Alice")
        assert user.user_id == "user123"
        assert user.role == UserRole.USER
        assert user.name == "Alice"
    
    def test_user_has_permission(self):
        """Test user permission checking."""
        user = User("user123", UserRole.USER)
        assert user.has_permission(Permission.USE_AGENT)
        assert not user.has_permission(Permission.RESOLVE_ESCALATIONS)
    
    def test_user_repr(self):
        """Test user string representation."""
        user = User("user123", UserRole.STAFF, "Bob")
        repr_str = repr(user)
        assert "user123" in repr_str
        assert "staff" in repr_str


class TestAccessControl:
    """Test AccessControl class."""
    
    def test_check_permission_allowed(self):
        """Test permission check when allowed."""
        admin = User("admin1", UserRole.ADMIN)
        result = AccessControl.check_permission(
            admin, 
            Permission.RESOLVE_ESCALATIONS,
            raise_on_deny=False
        )
        assert result is True
    
    def test_check_permission_denied(self):
        """Test permission check when denied."""
        user = User("user1", UserRole.USER)
        result = AccessControl.check_permission(
            user,
            Permission.RESOLVE_ESCALATIONS,
            raise_on_deny=False
        )
        assert result is False
    
    def test_check_permission_raises(self):
        """Test permission check raises exception."""
        user = User("user1", UserRole.USER)
        with pytest.raises(AccessDeniedException):
            AccessControl.check_permission(
                user,
                Permission.RESOLVE_ESCALATIONS,
                raise_on_deny=True
            )
    
    def test_can_view_escalations(self):
        """Test escalation viewing permissions."""
        user = User("user1", UserRole.USER)
        staff = User("staff1", UserRole.STAFF)
        
        # User can view own
        assert AccessControl.can_view_escalations(user, "user1")
        # User cannot view others
        assert not AccessControl.can_view_escalations(user, "other_user")
        # Staff can view all
        assert AccessControl.can_view_escalations(staff, "any_user")
    
    def test_can_resolve_escalations(self):
        """Test escalation resolution permissions."""
        user = User("user1", UserRole.USER)
        staff = User("staff1", UserRole.STAFF)
        admin = User("admin1", UserRole.ADMIN)
        
        assert not AccessControl.can_resolve_escalations(user)
        assert not AccessControl.can_resolve_escalations(staff)
        assert AccessControl.can_resolve_escalations(admin)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
