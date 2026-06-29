from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Alert
from app.schemas.alerts import AlertOut

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(db: Session = Depends(get_db), include_resolved: bool = False) -> list[Alert]:
    stmt = select(Alert).order_by(Alert.created_at.desc(), Alert.id.desc())
    if not include_resolved:
        stmt = stmt.where(Alert.is_resolved.is_(False))
    return list(db.scalars(stmt))
