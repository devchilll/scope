# User Switching Guide for IAM Testing

## Available Test Users

After running `demo/seed_test_users.py`, you have three users:

| User ID | Name | Role | Permissions |
|---------|------|------|-------------|
| `user` | Alice Johnson | USER | View own accounts, own escalations |
| `staff` | Bob Smith | STAFF | View all accounts, all escalations, resolve escalations |
| `admin` | Carol Admin | ADMIN | Full access to everything |

## How to Switch Users

### Method 1: Environment Variables (Recommended for Testing)

Set environment variables before starting the server:

```bash
# Login as regular user (default)
export IAM_CURRENT_USER_ID="user"
export IAM_CURRENT_USER_NAME="Alice Johnson"
export IAM_CURRENT_USER_ROLE="USER"
uv run adk web

# Login as staff
export IAM_CURRENT_USER_ID="staff"
export IAM_CURRENT_USER_NAME="Bob Smith"
export IAM_CURRENT_USER_ROLE="STAFF"
uv run adk web

# Login as admin
export IAM_CURRENT_USER_ID="admin"
export IAM_CURRENT_USER_NAME="Carol Admin"
export IAM_CURRENT_USER_ROLE="ADMIN"
uv run adk web
```

### Method 2: Edit `.env` File

Edit `/Users/yiransi/Documents/prime/.env` and add/modify:

```bash
# For USER
IAM_CURRENT_USER_ID=user
IAM_CURRENT_USER_NAME=Alice Johnson
IAM_CURRENT_USER_ROLE=USER

# For STAFF
# IAM_CURRENT_USER_ID=staff
# IAM_CURRENT_USER_NAME=Bob Smith
# IAM_CURRENT_USER_ROLE=STAFF

# For ADMIN
# IAM_CURRENT_USER_ID=admin
# IAM_CURRENT_USER_NAME=Carol Admin
# IAM_CURRENT_USER_ROLE=ADMIN
```

Then restart the server:
```bash
uv run adk web
```

### Method 3: Edit `config.py` Directly (Quick Testing)

Edit `prime_guardrails/config.py` lines 124-126:

```python
# Current user for testing
IAM_CURRENT_USER_ROLE: str = Field(default="ADMIN")  # Change this
IAM_CURRENT_USER_ID: str = Field(default="admin")     # Change this
IAM_CURRENT_USER_NAME: str = Field(default="Carol Admin")  # Change this
```

Then restart the server.

## Testing Different Permissions

### Test as USER (Alice)
- ✅ Can view own accounts
- ✅ Can view own escalation tickets
- ❌ Cannot view all escalation tickets
- ❌ Cannot resolve escalations

**Test**: Ask "Show me the escalation queue"
- Expected: Only shows tickets created by Alice

### Test as STAFF (Bob)
- ✅ Can view all accounts
- ✅ Can view all escalation tickets
- ✅ Can resolve escalations
- ❌ Cannot modify system settings

**Test**: Ask "Show me the escalation queue"
- Expected: Shows ALL tickets from all users

### Test as ADMIN (Carol)
- ✅ Full access to everything
- ✅ Can view all accounts
- ✅ Can view and resolve all escalations
- ✅ Can modify system settings

**Test**: Ask "Show me the escalation queue"
- Expected: Shows ALL tickets from all users

## Quick Switch Commands

```bash
# Switch to USER
export IAM_CURRENT_USER_ID="user" IAM_CURRENT_USER_NAME="Alice Johnson" IAM_CURRENT_USER_ROLE="USER" && uv run adk web

# Switch to STAFF
export IAM_CURRENT_USER_ID="staff" IAM_CURRENT_USER_NAME="Bob Smith" IAM_CURRENT_USER_ROLE="STAFF" && uv run adk web

# Switch to ADMIN
export IAM_CURRENT_USER_ID="admin" IAM_CURRENT_USER_NAME="Carol Admin" IAM_CURRENT_USER_ROLE="ADMIN" && uv run adk web
```
