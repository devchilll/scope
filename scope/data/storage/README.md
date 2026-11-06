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
IAM-protected methods `get_account`, `get_user_accounts` and
`get_account_transactions`. The escalation tools (`scope/observability_tools.py`)
reach the IAM-protected `get_escalations` and `resolve_escalation` through
`EscalationQueue`. Together they give:
- **USER**: Can only access own accounts, transactions and escalations, and only report fraud on / transfer between own accounts
- **STAFF**: Can view any customer's accounts and transactions, file fraud reports for customers, and view and resolve all escalations; cannot move customer money
- **ADMIN**: Same data access as STAFF (its extra config/user-management permissions are not yet used by any tool)

The write helpers (`create_user`, `create_account`, `update_account`,
`create_transaction`, `create_escalation`, `transfer_funds`) and `get_user` do no IAM checks.
The write helpers are called by `seed_database.py` and from inside tools
(the banking tools call them only after their own checks); `get_user` is only
used by `seed_database.py`.

## Transfers

`transfer_money` rejects same-account transfers and amounts that are not
positive, finite numbers with at most 2 decimal places (they are rejected, not
rounded) before touching the database. `Database.transfer_funds` applies the
same amount check itself (`validate_transfer_amount`, raising `ValueError`), so
direct calls are covered too, then applies
the debit, the credit and both `transactions` rows in a single SQLite
transaction (`BEGIN IMMEDIATE`): the debit only succeeds if the stored balance
still covers the amount, both balances are rounded to cents (`ROUND(..., 2)`),
and any failure rolls the whole transfer back. Balances remain `REAL` (floats).

Every `Database` method closes its connection even when a query raises, so a
failed call cannot leave the database locked.

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

