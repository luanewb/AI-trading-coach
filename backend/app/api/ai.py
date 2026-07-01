from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_account_or_404
from app.db.session import get_db
from app.models import DailyReview
from app.schemas.reviews import DailyReviewOut, DailyReviewRequest
from app.services.ai_review import build_daily_review_payload

router = APIRouter(prefix="/api/ai", tags=["ai"])


def _review_query(account_id: int, review_date: date | None = None):
    stmt = select(DailyReview).where(DailyReview.account_id == account_id)
    if review_date:
        stmt = stmt.where(DailyReview.review_date == review_date)
    return stmt.order_by(DailyReview.review_date.desc(), DailyReview.id.desc())


def _legacy_action_plan(findings: dict) -> str:
    return "\n".join(str(item) for item in findings.get("tomorrows_plan", [])[:3])


def _legacy_mistakes(findings: dict) -> str:
    patterns = findings.get("risk_patterns", [])
    return "\n".join(str(item) for item in patterns[:3]) or "No major risk pattern was detected from stored data."


def _legacy_best(findings: dict) -> str:
    positives = findings.get("positive_behaviors", [])
    return str(positives[0]) if positives else "No positive behavior detected from stored data."


def _legacy_worst(findings: dict) -> str:
    return str(findings.get("biggest_mistake_or_risk_pattern") or "No major risk pattern was detected from stored data.")


def _apply_payload(review: DailyReview, payload: dict) -> DailyReview:
    metrics = payload["metrics_snapshot"]
    findings = payload["deterministic_findings"]
    review.pnl = Decimal(str(metrics["realized_pnl"]))
    review.trade_count = int(metrics["total_trades"])
    review.win_rate = Decimal(str(metrics["win_rate"]))
    review.ai_summary = payload["ai_narrative"]
    review.mistakes = _legacy_mistakes(findings)
    review.best_trade = _legacy_best(findings)
    review.worst_trade = _legacy_worst(findings)
    review.action_plan = _legacy_action_plan(findings)
    review.metrics_snapshot = metrics
    review.discipline_score = int(payload["discipline_score"])
    review.discipline_breakdown = payload["discipline_breakdown"]
    review.deterministic_findings = findings
    review.ai_narrative = payload["ai_narrative"]
    review.model_metadata = payload["model_metadata"]
    review.generated_at = datetime.now(timezone.utc)
    return review


def _generate_review(db: Session, account_id: int, review_date: date, regenerate: bool = False) -> DailyReview:
    existing = db.scalar(_review_query(account_id, review_date).limit(1))
    if existing and not regenerate:
        return existing

    account = current_account_or_404(db, account_id)
    payload = build_daily_review_payload(db, account, review_date)
    review = existing or DailyReview(account_id=account.id, review_date=review_date)
    _apply_payload(review, payload)
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@router.get("/daily-review", response_model=DailyReviewOut | None)
def latest_review(
    review_date: date | None = None,
    db: Session = Depends(get_db),
    account_id: int | None = None,
) -> DailyReview | None:
    account = current_account_or_404(db, account_id)
    return db.scalar(_review_query(account.id, review_date).limit(1))


@router.post("/daily-review", response_model=DailyReviewOut)
def create_daily_review(
    payload: DailyReviewRequest,
    db: Session = Depends(get_db),
    account_id: int | None = None,
) -> DailyReview:
    account = current_account_or_404(db, account_id or payload.account_id)
    review_date = payload.review_date or date.today()
    return _generate_review(db, account.id, review_date, regenerate=False)


@router.get("/daily-review/history", response_model=list[DailyReviewOut])
def review_history(
    db: Session = Depends(get_db),
    account_id: int | None = None,
    limit: int = 20,
) -> list[DailyReview]:
    account = current_account_or_404(db, account_id)
    return list(db.scalars(_review_query(account.id).limit(max(1, min(limit, 100)))))


@router.post("/daily-review/regenerate", response_model=DailyReviewOut)
def regenerate_daily_review(
    payload: DailyReviewRequest,
    db: Session = Depends(get_db),
    account_id: int | None = None,
) -> DailyReview:
    account = current_account_or_404(db, account_id or payload.account_id)
    review_date = payload.review_date or date.today()
    return _generate_review(db, account.id, review_date, regenerate=True)
