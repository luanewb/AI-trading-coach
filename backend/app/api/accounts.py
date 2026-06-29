from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.stats import get_current_account

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


class AccountOut(BaseModel):
    id: int
    account_number: str
    broker: str
    server: str
    balance: float
    equity: float
    margin: float
    free_margin: float

    model_config = {"from_attributes": True}


@router.get("/current", response_model=AccountOut)
def current_account(db: Session = Depends(get_db)):
    account = get_current_account(db)
    if not account:
        raise HTTPException(status_code=404, detail="No account has been connected yet")
    return account
