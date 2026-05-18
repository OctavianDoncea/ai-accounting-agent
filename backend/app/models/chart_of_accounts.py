import enum
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Enum, Text, func
from sqlalchemy.orm import Mapped, mapped_column
from app.database import Base

class AccountType(str, enum.Enum):
    ASSET = 'ASSET'
    LIABILITY = 'LIABILITY'
    EQUITY = 'EQUITY'
    REVENUE = 'REVENUE'
    EXPENSE = 'EXPENSE'


class NormalBalance(str, enum.Enum):
    DEBIT = 'DEBIT'
    CREDIT = 'CREDIT'

class ChartOfAccount(Base):
    __tablename__ = 'chart_of_accounts'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[str] = mapped_column(Enum(AccountType, name='account_type'), nullable=False, index=True)
    normal_balance: Mapped[NormalBalance] = mapped_column(Enum(NormalBalance, name='normal_balance'), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    def __repr__(self) -> str:
        return f'<ChartOfAccount {self.account_code} - {self.account_name}>'