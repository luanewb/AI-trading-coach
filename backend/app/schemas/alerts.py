from datetime import datetime

from pydantic import BaseModel


class AlertOut(BaseModel):
    id: int
    account_id: int | None
    severity: str
    type: str
    message: str
    is_resolved: bool
    created_at: datetime

    model_config = {"from_attributes": True}
