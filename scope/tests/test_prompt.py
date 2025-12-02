"""Tests for prompt module - permission-driven tool descriptions."""

import pytest
from scope.prompt import (
    TOOL_DEFINITIONS,
    get_tool_descriptions,
    format_tool
)
from scope.iam import UserRole, Permission, get_permissions


class TestToolDefinitions:
    """Test TOOL_DEFINITIONS structure."""
    
    def test_all_tools_have_permissions(self):
        """All tools should have a permissions field."""
        for tool_name, tool_def in TOOL_DEFINITIONS.items():
            assert 'permissions' in tool_def, f"Tool {tool_name} missing permissions field"
            assert isinstance(tool_def['permissions'], list), f"Tool {tool_name} permissions should be a list"
    
    def test_all_tools_have_required_fields(self):
        """All tools should have title, tool, and notes fields."""
        required_fields = ['title', 'tool', 'notes']
        for tool_name, tool_def in TOOL_DEFINITIONS.items():
            for field in required_fields:
                assert field in tool_def, f"Tool {tool_name} missing {field} field"
    
    def test_permission_types(self):
        """All permissions should be Permission enum values."""
        for tool_name, tool_def in TOOL_DEFINITIONS.items():
            for perm in tool_def['permissions']:
                assert isinstance(perm, Permission), f"Tool {tool_name} has invalid permission type: {perm}"
    
    def test_notes_format(self):
        """Notes should be either a list or a dict with USER/STAFF_ADMIN keys."""
        for tool_name, tool_def in TOOL_DEFINITIONS.items():
            notes = tool_def['notes']
            assert isinstance(notes, (list, dict)), f"Tool {tool_name} notes should be list or dict"
            
            if isinstance(notes, dict):
                # If dict, should have USER and/or STAFF_ADMIN keys
                valid_keys = {'USER', 'STAFF_ADMIN'}
                assert set(notes.keys()).issubset(valid_keys), \
                    f"Tool {tool_name} has invalid note keys: {notes.keys()}"


class TestPermissionMapping:
    """Test that tool permissions match IAM permissions."""
    
    def test_user_tools_match_permissions(self):
        """USER should only see tools they have permissions for."""
        user_perms = get_permissions(UserRole.USER)
        tools_desc = get_tool_descriptions('user')
        
        # Check that USER has basic permissions
        assert Permission.USE_AGENT in user_perms
        assert Permission.VIEW_ACCOUNTS in user_perms
        assert Permission.VIEW_TRANSACTIONS in user_perms
        
        # Check that USER sees expected tools
        assert 'Check Account Balances' in tools_desc
        assert 'Transfer Money' in tools_desc
        assert 'List Escalation Tickets' in tools_desc
        
        # Check that USER does NOT see admin tools
        assert 'View Audit Logs' not in tools_desc
        assert Permission.VIEW_LOGS not in user_perms
    
    def test_staff_tools_match_permissions(self):
        """STAFF should see additional tools based on their permissions."""
        staff_perms = get_permissions(UserRole.STAFF)
        tools_desc = get_tool_descriptions('staff')
        
        # Check that STAFF has additional permissions
        assert Permission.VIEW_LOGS in staff_perms
        assert Permission.RESOLVE_ESCALATIONS in staff_perms
        assert Permission.VIEW_ALL_ESCALATIONS in staff_perms
        
        # Check that STAFF sees admin tools
        assert 'View Audit Logs' in tools_desc
        assert 'Resolve Escalation' in tools_desc
    
    def test_admin_tools_match_permissions(self):
        """ADMIN should see all tools."""
        admin_perms = get_permissions(UserRole.ADMIN)
        tools_desc = get_tool_descriptions('admin')
        
        # Check that ADMIN has all necessary permissions
        assert Permission.VIEW_LOGS in admin_perms
        assert Permission.RESOLVE_ESCALATIONS in admin_perms
        assert Permission.MODIFY_CONFIG in admin_perms
        
        # Check that ADMIN sees all tools
        assert 'View Audit Logs' in tools_desc
        assert 'Resolve Escalation' in tools_desc
        assert 'Transfer Money' in tools_desc


class TestToolVisibility:
    """Test tool visibility for different roles."""
    
    def test_user_tool_count(self):
        """USER should see 12 tools (banking + universal + own escalations)."""
        tools_desc = get_tool_descriptions('user')
        tool_count = tools_desc.count('✅')
        # 12 tools + 1 general banking info = 13 checkmarks
        assert tool_count == 12, f"Expected 12 tools for USER, got {tool_count}"
    
    def test_staff_tool_count(self):
        """STAFF should see 14 tools (USER + audit logs + resolve escalations)."""
        tools_desc = get_tool_descriptions('staff')
        tool_count = tools_desc.count('✅')
        assert tool_count == 14, f"Expected 14 tools for STAFF, got {tool_count}"
    
    def test_admin_tool_count(self):
        """ADMIN should see 14 tools (same as STAFF)."""
        tools_desc = get_tool_descriptions('admin')
        tool_count = tools_desc.count('✅')
        assert tool_count == 14, f"Expected 14 tools for ADMIN, got {tool_count}"
    
    def test_or_logic_for_escalations(self):
        """list_escalations should be visible if user has ANY required permission."""
        # USER has VIEW_OWN_ESCALATIONS
        user_tools = get_tool_descriptions('user')
        assert 'List Escalation Tickets' in user_tools
        
        # STAFF has VIEW_ALL_ESCALATIONS
        staff_tools = get_tool_descriptions('staff')
        assert 'List Escalation Tickets' in staff_tools
        
        # Both should see it (OR logic)
        user_perms = get_permissions(UserRole.USER)
        staff_perms = get_permissions(UserRole.STAFF)
        
        assert Permission.VIEW_OWN_ESCALATIONS in user_perms
        assert Permission.VIEW_ALL_ESCALATIONS in staff_perms


class TestRoleSpecificNotes:
    """Test that role-specific notes are shown correctly."""
    
    def test_user_sees_own_account_notes(self):
        """USER should see notes about 'your own' accounts."""
        tools_desc = get_tool_descriptions('user')
        assert 'your own account' in tools_desc.lower() or 'your own' in tools_desc.lower()
    
    def test_staff_sees_any_customer_notes(self):
        """STAFF should see notes about 'any customer' accounts."""
        tools_desc = get_tool_descriptions('staff')
        assert 'any customer' in tools_desc.lower()
    
    def test_admin_sees_any_customer_notes(self):
        """ADMIN should see notes about 'any customer' accounts."""
        tools_desc = get_tool_descriptions('admin')
        assert 'any customer' in tools_desc.lower()
    
    def test_format_tool_with_dict_notes(self):
        """format_tool should handle dict notes correctly."""
        tool_def = {
            'title': 'Test Tool',
            'tool': 'test_tool()',
            'notes': {
                'USER': ['User note'],
                'STAFF_ADMIN': ['Staff note']
            }
        }
        
        user_output = format_tool(tool_def, UserRole.USER)
        assert 'User note' in user_output
        assert 'Staff note' not in user_output
        
        staff_output = format_tool(tool_def, UserRole.STAFF)
        assert 'Staff note' in staff_output
        assert 'User note' not in staff_output
    
    def test_format_tool_with_list_notes(self):
        """format_tool should handle list notes correctly."""
        tool_def = {
            'title': 'Test Tool',
            'tool': 'test_tool()',
            'notes': ['Universal note']
        }
        
        user_output = format_tool(tool_def, UserRole.USER)
        assert 'Universal note' in user_output
        
        staff_output = format_tool(tool_def, UserRole.STAFF)
        assert 'Universal note' in staff_output


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_invalid_role_defaults_to_user(self):
        """Invalid role string should default to USER."""
        tools_desc = get_tool_descriptions('invalid_role')
        user_tools = get_tool_descriptions('user')
        
        # Should have same number of tools as USER
        assert tools_desc.count('✅') == user_tools.count('✅')
    
    def test_case_insensitive_role(self):
        """Role string should be case-insensitive."""
        tools_upper = get_tool_descriptions('ADMIN')
        tools_lower = get_tool_descriptions('admin')
        tools_mixed = get_tool_descriptions('AdMiN')
        
        assert tools_upper == tools_lower == tools_mixed
    
    def test_general_banking_info_always_shown(self):
        """General banking info should be shown for all roles."""
        for role in ['user', 'staff', 'admin']:
            tools_desc = get_tool_descriptions(role)
            assert 'General Banking Information' in tools_desc


class TestConsistencyWithIAM:
    """Test that prompt system is consistent with IAM."""
    
    def test_no_hardcoded_role_checks(self):
        """get_tool_descriptions should not have hardcoded role checks."""
        import inspect
        source = inspect.getsource(get_tool_descriptions)
        
        # Should not have "if role == UserRole.ADMIN" patterns
        assert 'if role == UserRole.ADMIN:' not in source
        assert 'if role == UserRole.STAFF:' not in source
        
        # Should use get_permissions
        assert 'get_permissions' in source
    
    def test_all_permissions_are_valid(self):
        """All permissions in TOOL_DEFINITIONS should exist in Permission enum."""
        valid_perms = set(Permission)
        
        for tool_name, tool_def in TOOL_DEFINITIONS.items():
            for perm in tool_def['permissions']:
                assert perm in valid_perms, f"Tool {tool_name} has invalid permission: {perm}"
    
    def test_staff_has_resolve_permission(self):
        """STAFF should have RESOLVE_ESCALATIONS permission (consistency fix)."""
        staff_perms = get_permissions(UserRole.STAFF)
        assert Permission.RESOLVE_ESCALATIONS in staff_perms, \
            "STAFF should have RESOLVE_ESCALATIONS permission"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
