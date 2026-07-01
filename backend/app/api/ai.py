from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_account_or_404
from app.db.session import get_db
from app.models import DailyReview
from app.schemas.reviews import DailyReviewOut, DailyReviewRequest
from app.services.ai_review import build_daily_review
from app.services.stats import calculate_stats

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/daily-review", response_model=DailyReviewOut | None)
def latest_review(db: Session = Depends(get_db), account_id: int | None = None) -> DailyReview | None:
    account = current_account_or_404(db, account_id)
    return db.scalar(
        select(DailyReview)
        .where(DailyReview.account_id == account.id)
        .order_by(DailyReview.review_date.desc(), DailyReview.id.desc())
        .limit(1)
    )


@router.post("/daily-review", response_model=DailyReviewOut)
def create_daily_review(payload: DailyReviewRequest, db: Session = Depends(get_db), account_id: int | None = None) -> DailyReview:
    account = current_account_or_404(db, account_id)
    review_date = payload.review_date or date.today()
    draft = build_daily_review(db, account, review_date)
    stats = calculate_stats(db, account.id)
    review = DailyReview(
        account_id=account.id,
        review_date=review_date,
        pnl=Decimal(str(stats["daily_pnl"])),
        trade_count=int(stats["trades_today"]),
        win_rate=Decimal(str(stats["win_rate"])),
        ai_summary=draft.ai_summary,
        mistakes=draft.mistakes,
        best_trade=draft.best_trade,
        worst_trade=draft.worst_trade,
        action_plan=draft.action_plan,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return review
