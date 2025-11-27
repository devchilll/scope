"""IAM (Identity and Access Management) module for PRIME guardrails.

This package provides role-based access control (RBAC) for the agent system.
"""

from .roles import UserRole, Permission
from .acl import AccessControl, check_permission, User, AccessDeniedException

__all__ = ['UserRole', 'Permission', 'AccessControl', 'check_permission', 'User', 'AccessDeniedException']

