# Data Storage

This directory contains the SQLite database for banking data.

## Database Schema

### Users Table
- `user_id` (TEXT, PRIMARY KEY)
- `name` (TEXT)
- `email` (TEXT, UNIQUE)
- `phone` (TEXT)
- `created_at` (TEXT, ISO format)

### Accounts Table
- `account_id` (TEXT, PRIMARY KEY)
- `user_id` (TEXT, FOREIGN KEY)
- `account_type` (TEXT: checking, savings, credit)
- `balance` (REAL)
- `currency` (TEXT, default: USD)
- `status` (TEXT, default: active)
- `created_at` (TEXT, ISO format)

### Transactions Table
- `transaction_id` (TEXT, PRIMARY KEY)
- `account_id` (TEXT, FOREIGN KEY)
- `transaction_type` (TEXT: deposit, withdrawal, transfer, payment)
- `amount` (REAL)
- `currency` (TEXT, default: USD)
- `description` (TEXT)
- `timestamp` (TEXT, ISO format)
- `status` (TEXT, default: completed)
- `from_account_id` (TEXT, nullable)
- `to_account_id` (TEXT, nullable)

## Database File

- **Development**: `banking.db` (SQLite)
- **Production**: Migrate to PostgreSQL or MySQL

## Access Control

Every agent-facing banking tool (`scope/data/tools.py`) runs as the current
user and checks that user's role and account ownership through the
IAM-protected read methods (`get_account`, `get_user_accounts`,
`get_account_transactions`, `get_escalations`, `resolve_escalation`):
- **USER**: Can only access own accounts, transactions and escalations, and only report fraud on / transfer between own accounts
- **STAFF**: Can view any customer's accounts and transactions, file fraud reports for customers, and view and resolve all escalations; cannot move customer money
- **ADMIN**: Same data access as STAFF (its extra config/user-management permissions are not yet used by any tool)

The write helpers (`create_user`, `create_account`, `update_account`,
`create_transaction`, `create_escalation`) and `get_user` do no IAM checks;
they are used for seeding and by tools after the tool's own checks.

## Backup

For production, implement automated backups:
```bash
# Example backup script
sqlite3 banking.db ".backup banking_backup_$(date +%Y%m%d).db"
```

## Seeding Sample Data

To populate the database with sample data for testing:

```bash
# From project root
uv run python scope/data/seed_database.py
```

This creates:
- Default user: `user` (Alice Johnson) - matches ADK web UI default
- Checking account: `acc001` ($2,547.83)
- Savings account: `acc002` ($15,234.56)
- 9 sample transactions (deposits, withdrawals, payments)

