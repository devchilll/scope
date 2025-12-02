"""User roles and permissions for PRIME system."""

from enum import Enum
from typing import Set


class Permission(Enum):
    """System permissions."""
    # Escalation queue permissions
    VIEW_OWN_ESCALATIONS = "view_own_escalations"
    VIEW_ALL_ESCALATIONS = "view_all_escalations"
    RESOLVE_ESCALATIONS = "resolve_escalations"
    
    # Agent interaction permissions
    USE_AGENT = "use_agent"
    BYPASS_SAFETY_CHECKS = "bypass_safety_checks"
    
    # Banking permissions
    VIEW_ACCOUNTS = "view_accounts"
    VIEW_TRANSACTIONS = "view_transactions"
    
    # Configuration permissions
    VIEW_CONFIG = "view_config"
    MODIFY_CONFIG = "modify_config"
    MODIFY_COMPLIANCE_RULES = "modify_compliance_rules"
    
    # System administration
    VIEW_LOGS = "view_logs"
    MANAGE_USERS = "manage_users"


class UserRole(Enum):
    """User roles with associated permissions."""
    
    # Regular user - can use agent, view own escalations
    USER = "user"
    
    # Staff - can view all escalations to help resolve them (read-only)
    STAFF = "staff"
    
    # Admin - full access including resolving escalations and config
    ADMIN = "admin"
    
    # System - internal system operations
    SYSTEM = "system"


# Role to permissions mapping
ROLE_PERMISSIONS: dict[UserRole, Set[Permission]] = {
    UserRole.USER: {
        Permission.USE_AGENT,
        Permission.VIEW_OWN_ESCALATIONS,
        Permission.VIEW_ACCOUNTS,
        Permission.VIEW_TRANSACTIONS,
    },
    
    UserRole.STAFF: {
        Permission.USE_AGENT,
        Permission.VIEW_OWN_ESCALATIONS,
        Permission.VIEW_ALL_ESCALATIONS,  # Can read queue
        Permission.RESOLVE_ESCALATIONS,  # Can resolve tickets (added for consistency)
        Permission.VIEW_ACCOUNTS,
        Permission.VIEW_TRANSACTIONS,
        Permission.VIEW_CONFIG,
        Permission.VIEW_LOGS,
    },
    
    UserRole.ADMIN: {
        Permission.USE_AGENT,
        Permission.VIEW_OWN_ESCALATIONS,
        Permission.VIEW_ALL_ESCALATIONS,
        Permission.RESOLVE_ESCALATIONS,  # Can write to queue
        Permission.VIEW_ACCOUNTS,
        Permission.VIEW_TRANSACTIONS,
        Permission.VIEW_CONFIG,
        Permission.MODIFY_CONFIG,
        Permission.MODIFY_COMPLIANCE_RULES,
        Permission.VIEW_LOGS,
        Permission.MANAGE_USERS,
    },
    
    UserRole.SYSTEM: {
        # System has all permissions
        perm for perm in Permission
    }
}


def get_permissions(role: UserRole) -> Set[Permission]:
    """Get all permissions for a given role.
    
    Args:
        role: User role
        
    Returns:
        Set of permissions
    """
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(role: UserRole, permission: Permission) -> bool:
    """Check if a role has a specific permission.
    
    Args:
        role: User role to check
        permission: Permission to check for
        
    Returns:
        True if role has permission, False otherwise
    """
    return permission in get_permissions(role)


def get_role_description(role: UserRole) -> str:
    """Get a human-readable description of what a role can do.
    
    Args:
        role: User role to describe
        
    Returns:
        Description of the role's capabilities
    """
    descriptions = {
        UserRole.USER: "Regular customer, can only access their own data (accounts, transactions, escalations)",
        UserRole.STAFF: "Bank employee, authorized to view customer data and all escalation tickets for support purposes",
        UserRole.ADMIN: "Administrator, full access to all systems, data, and can resolve escalations and modify configurations",
        UserRole.SYSTEM: "Internal system operations, full access to all functions"
    }
    return descriptions.get(role, "Unknown role")


def get_all_role_descriptions() -> str:
    """Get formatted descriptions of all roles for prompts.
    
    Returns:
        Formatted string with all role descriptions
    """
    return """- **USER** role: Regular customer, can only access their own data (accounts, transactions, escalations)
- **STAFF** role: Bank employee, authorized to view customer data and all escalation tickets for support purposes
- **ADMIN** role: Administrator, full access to all systems, data, and can resolve escalations and modify configurations"""
