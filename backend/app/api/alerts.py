from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.deps import current_account_or_404
from app.db.session import get_db
from app.models import Alert
from app.schemas.alerts import AlertOut

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(db: Session = Depends(get_db), include_resolved: bool = False, account_id: int | None = None) -> list[Alert]:
    stmt = select(Alert).order_by(Alert.created_at.desc(), Alert.id.desc())
    if account_id is not None:
        account = current_account_or_404(db, account_id)
        stmt = stmt.where(or_(Alert.account_id == account.id, Alert.account_id.is_(None)))
    if not include_resolved:
        stmt = stmt.where(Alert.is_resolved.is_(False))
    return list(db.scalars(stmt))
