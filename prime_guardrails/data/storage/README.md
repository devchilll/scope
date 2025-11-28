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

All database operations are IAM-protected:
- **USER**: Can only access own accounts and transactions
- **STAFF**: Can view all accounts (read-only)
- **ADMIN**: Full access to all operations

## Backup

For production, implement automated backups:
```bash
# Example backup script
sqlite3 banking.db ".backup banking_backup_$(date +%Y%m%d).db"
```
