#!/usr/bin/env python3
"""Quick user switcher for testing IAM permissions.

Usage:
    python demo/switch_user.py user
    python demo/switch_user.py staff
    python demo/switch_user.py admin
"""
import sys
from pathlib import Path

# User configurations
USERS = {
    "user": {
        "id": "user",
        "name": "Alice Johnson",
        "role": "USER",
        "email": "alice@example.com",
        "phone": "+1-555-0123",
        "address": "123 Customer Street, Banking City, NY 10001"
    },
    "staff": {
        "id": "staff",
        "name": "Bob Smith",
        "role": "STAFF",
        "email": "bob.smith@primebank.com",
        "phone": "+1-555-0456",
        "address": "456 Staff Lane, Banking City, NY 10005"
    },
    "admin": {
        "id": "admin",
        "name": "Carol Admin",
        "role": "ADMIN",
        "email": "carol.admin@primebank.com",
        "phone": "+1-555-0789",
        "address": "789 Admin Boulevard, Banking City, NY 10010"
    }
}

def switch_user(user_key):
    """Switch to a different user by updating config.py."""
    if user_key not in USERS:
        print(f"❌ Unknown user: {user_key}")
        print(f"Available users: {', '.join(USERS.keys())}")
        return False
    
    user = USERS[user_key]
    config_path = Path(__file__).parent.parent / "prime_guardrails" / "config.py"
    
    # Read the config file
    with open(config_path, 'r') as f:
        content = f.read()
    
    # Replace the user settings
    lines = content.split('\n')
    new_lines = []
    
    for line in lines:
        if 'IAM_CURRENT_USER_ROLE: str = Field(default=' in line:
            new_lines.append(f'    IAM_CURRENT_USER_ROLE: str = Field(default="{user["role"]}")')
        elif 'IAM_CURRENT_USER_ID: str = Field(default=' in line:
            new_lines.append(f'    IAM_CURRENT_USER_ID: str = Field(default="{user["id"]}")')
        elif 'IAM_CURRENT_USER_NAME: str = Field(default=' in line:
            new_lines.append(f'    IAM_CURRENT_USER_NAME: str = Field(default="{user["name"]}")')
        elif 'IAM_CURRENT_USER_EMAIL: str = Field(default=' in line:
            new_lines.append(f'    IAM_CURRENT_USER_EMAIL: str = Field(default="{user["email"]}")')
        elif 'IAM_CURRENT_USER_PHONE: str = Field(default=' in line:
            new_lines.append(f'    IAM_CURRENT_USER_PHONE: str = Field(default="{user["phone"]}")')
        elif 'IAM_CURRENT_USER_ADDRESS: str = Field(default=' in line:
            new_lines.append(f'    IAM_CURRENT_USER_ADDRESS: str = Field(default="{user["address"]}")')
        else:
            new_lines.append(line)
    
    # Write back
    with open(config_path, 'w') as f:
        f.write('\n'.join(new_lines))
    
    print(f"✅ Switched to user: {user['name']} ({user['role']})")
    print(f"   User ID: {user['id']}")
    print(f"\n⚠️  IMPORTANT: Restart the server for changes to take effect:")
    print(f"   uv run adk web")
    return True

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python demo/switch_user.py [user|staff|admin]")
        print("\nAvailable users:")
        for key, user in USERS.items():
            print(f"  - {key}: {user['name']} ({user['role']})")
        sys.exit(1)
    
    switch_user(sys.argv[1])
