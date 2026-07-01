from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.analytics import AnalyticsBreakdownOut, AnalyticsInsightsOut, AnalyticsOverviewOut
from app.services.analytics import AnalyticsDataset, GROUP_BY_OPTIONS, build_breakdown, build_insights, build_overview, load_dataset
from app.services.stats import get_selected_account

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def _dataset(db: Session, account_id: int | None, start_date: date | None, end_date: date | None):
    account = get_selected_account(db, account_id)
    if not account:
        return None
    return load_dataset(db, account.id, start_date, end_date)


def _empty_dataset(start_date: date | None, end_date: date | None) -> AnalyticsDataset:
    return AnalyticsDataset(account_id=None, start_date=start_date, end_date=end_date, trades=[], checks=[], violations=[])


@router.get("/overview", response_model=AnalyticsOverviewOut)
def overview(
    db: Session = Depends(get_db),
    account_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> AnalyticsOverviewOut:
    dataset = _dataset(db, account_id, start_date, end_date)
    if dataset is None:
        return build_overview(_empty_dataset(start_date, end_date))
    return build_overview(dataset)


@router.get("/breakdown", response_model=AnalyticsBreakdownOut)
def breakdown(
    db: Session = Depends(get_db),
    account_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    group_by: str = Query(default="symbol"),
) -> AnalyticsBreakdownOut:
    if group_by not in GROUP_BY_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported group_by. Use one of: {', '.join(sorted(GROUP_BY_OPTIONS))}")
    dataset = _dataset(db, account_id, start_date, end_date)
    if dataset is None:
        return build_breakdown(_empty_dataset(start_date, end_date), group_by)
    return build_breakdown(dataset, group_by)


@router.get("/insights", response_model=AnalyticsInsightsOut)
def insights(
    db: Session = Depends(get_db),
    account_id: int | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> AnalyticsInsightsOut:
    dataset = _dataset(db, account_id, start_date, end_date)
    if dataset is None:
        return build_insights(_empty_dataset(start_date, end_date))
    return build_insights(dataset)
