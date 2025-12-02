"""Data models for banking application.

This module defines Pydantic models for User, Account, and Transaction entities.
"""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class AccountType(Enum):
    """Types of bank accounts."""
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT = "credit"


class TransactionType(Enum):
    """Types of transactions."""
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"
    PAYMENT = "payment"


class User(BaseModel):
    """User model for banking customers."""
    user_id: str = Field(..., description="Unique user identifier")
    name: str = Field(..., description="Full name")
    email: str = Field(..., description="Email address")
    phone: Optional[str] = Field(None, description="Phone number")
    account_ids: List[str] = Field(default_factory=list, description="List of account IDs owned by user")
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user",
                "name": "Alice Johnson",
                "email": "alice@example.com",
                "phone": "+1-555-0123",
                "account_ids": ["acc001", "acc002"]
            }
        }


class Account(BaseModel):
    """Bank account model."""
    account_id: str = Field(..., description="Unique account identifier")
    user_id: str = Field(..., description="Owner's user ID")
    account_type: AccountType = Field(..., description="Type of account")
    balance: float = Field(..., description="Current balance")
    currency: str = Field(default="USD", description="Currency code")
    status: str = Field(default="active", description="Account status")
    created_at: datetime = Field(default_factory=datetime.now)
    
    class Config:
        json_schema_extra = {
            "example": {
                "account_id": "acc001",
                "user_id": "user",
                "account_type": "checking",
                "balance": 1234.56,
                "currency": "USD",
                "status": "active"
            }
        }


class Transaction(BaseModel):
    """Transaction model."""
    transaction_id: str = Field(..., description="Unique transaction identifier")
    account_id: str = Field(..., description="Account ID")
    transaction_type: TransactionType = Field(..., description="Type of transaction")
    amount: float = Field(..., description="Transaction amount")
    currency: str = Field(default="USD", description="Currency code")
    description: Optional[str] = Field(None, description="Transaction description")
    timestamp: datetime = Field(default_factory=datetime.now)
    status: str = Field(default="completed", description="Transaction status")
    
    # For transfers
    from_account_id: Optional[str] = Field(None, description="Source account for transfers")
    to_account_id: Optional[str] = Field(None, description="Destination account for transfers")
    
    class Config:
        json_schema_extra = {
            "example": {
                "transaction_id": "txn001",
                "account_id": "acc001",
                "transaction_type": "deposit",
                "amount": 500.00,
                "currency": "USD",
                "description": "Paycheck deposit",
                "status": "completed"
            }
        }
