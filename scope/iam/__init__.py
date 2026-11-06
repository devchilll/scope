"""IAM (Identity and Access Management) module for SCOPE."""

from .acl import User, AccessControl, AccessDeniedException, check_permission
from .roles import (
    UserRole,
    Permission,
    ROLE_PERMISSIONS,
    parse_role,
    get_permissions,
    has_permission,
    get_role_description,
    get_all_role_descriptions
)

__all__ = [
    "User",
    "UserRole",
    "Permission",
    "ROLE_PERMISSIONS",
    "AccessControl",
    "AccessDeniedException",
    "check_permission",
    "parse_role",
    "get_permissions",
    "has_permission",
    "get_role_description",
    "get_all_role_descriptions",
]
