"""Access Control List (ACL) implementation."""

from typing import Optional
from .roles import UserRole, Permission, has_permission


class AccessDeniedException(Exception):
    """Raised when a user attempts an action they don't have permission for."""
    pass


class User:
    """Represents a user in the system."""
    
    def __init__(self, user_id: str, role: UserRole, name: Optional[str] = None):
        """Initialize a user.
        
        Args:
            user_id: Unique user identifier
            role: User's role
            name: Optional display name
        """
        self.user_id = user_id
        self.role = role
        self.name = name or user_id
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission.
        
        Args:
            permission: Permission to check
            
        Returns:
            True if user has permission
        """
        return has_permission(self.role, permission)
    
    def __repr__(self) -> str:
        return f"User(id={self.user_id}, role={self.role.value}, name={self.name})"


class AccessControl:
    """Access control manager for the PRIME system."""
    
    @staticmethod
    def check_permission(user: User, permission: Permission, raise_on_deny: bool = True) -> bool:
        """Check if a user has a specific permission.
        
        Args:
            user: User to check
            permission: Permission required
            raise_on_deny: If True, raise exception on denial
            
        Returns:
            True if user has permission
            
        Raises:
            AccessDeniedException: If user lacks permission and raise_on_deny is True
        """
        has_perm = user.has_permission(permission)
        
        if not has_perm and raise_on_deny:
            raise AccessDeniedException(
                f"User {user.user_id} (role: {user.role.value}) "
                f"does not have permission: {permission.value}"
            )
        
        return has_perm
    
    @staticmethod
    def can_view_escalations(user: User, target_user_id: Optional[str] = None) -> bool:
        """Check if user can view escalations.
        
        Args:
            user: User requesting access
            target_user_id: If provided, check if user can view this specific user's escalations
            
        Returns:
            True if user can view the escalations
        """
        # Can always view own escalations
        if target_user_id and target_user_id == user.user_id:
            return user.has_permission(Permission.VIEW_OWN_ESCALATIONS)
        
        # STAFF and ADMIN can view all escalations
        if target_user_id:
            return user.has_permission(Permission.VIEW_ALL_ESCALATIONS)
        
        # If no target specified, check general view permission
        return (user.has_permission(Permission.VIEW_OWN_ESCALATIONS) or 
                user.has_permission(Permission.VIEW_ALL_ESCALATIONS))
    
    @staticmethod
    def can_resolve_escalations(user: User) -> bool:
        """Check if user can resolve escalations.
        
        Args:
            user: User to check
            
        Returns:
            True if user can resolve escalations (STAFF and ADMIN)
        """
        return user.has_permission(Permission.RESOLVE_ESCALATIONS)
    
    @staticmethod
    def can_modify_compliance_rules(user: User) -> bool:
        """Check if user can modify compliance rules.
        
        Args:
            user: User to check
            
        Returns:
            True if user can modify compliance rules (ADMIN only)
        """
        return user.has_permission(Permission.MODIFY_COMPLIANCE_RULES)


# Convenience function for permission checking
def check_permission(user: User, permission: Permission, raise_on_deny: bool = True) -> bool:
    """Convenience function for checking permissions.
    
    Args:
        user: User to check
        permission: Permission required
        raise_on_deny: If True, raise exception on denial
        
    Returns:
        True if user has permission
    """
    return AccessControl.check_permission(user, permission, raise_on_deny)
