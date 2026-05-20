from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.chart_of_accounts import ChartOfAccount, AccountType, NormalBalance

router = APIRouter(prefix='/chart-of-accounts', tags=['chart-of-accounts'])

class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_code: str
    account_name: str
    account_type: AccountType
    normal_balance: NormalBalance
    description: str | None
    is_active: bool

@router.get('', response_model=list[AccountOut])
def list_accounts(account_type: AccountType | None = None, active_only: bool = True, db: Session = Depends(get_db)) -> list[ChartOfAccount]:
    query = db.query(ChartOfAccount)
    if active_only:
        query = query.filter(ChartOfAccount.is_active.is_(True))
    if account_type:
        query = query.filter(ChartOfAccount.account_type == account_type)
    
    return query.order_by(ChartOfAccount.account_code).all()