from fastapi import Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Account
from app.services.stats import get_current_account


def require_mt5_api_key(x_api_key: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid x-api-key")


def current_account_or_404(db: Session) -> Account:
    account = get_current_account(db)
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No real MT5 account has been connected yet")
    return account
