import json
import logging
from datetime import date
from decimal import Decimal

from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Account, Trade
from app.schemas.reviews import DailyReviewDraft
from app.services.stats import calculate_stats
from app.services.timezone import trading_day_bounds

logger = logging.getLogger(__name__)


def _fallback_review(trades: list[Trade], pnl: Decimal, win_rate: float) -> DailyReviewDraft:
    best = max(trades, key=lambda t: Decimal(t.profit or 0), default=None)
    worst = min(trades, key=lambda t: Decimal(t.profit or 0), default=None)
    losing_tags = sorted({tag for trade in trades for tag in (trade.mistake_tags or [])})
    return DailyReviewDraft(
        ai_summary=f"AI is disabled. Closed {len(trades)} trades with PnL {pnl:.2f} and win rate {win_rate:.1f}%.",
        mistakes=", ".join(losing_tags) or "No tagged mistakes yet.",
        best_trade=f"{best.symbol} ticket {best.ticket}: {best.profit}" if best else "No closed trade.",
        worst_trade=f"{worst.symbol} ticket {worst.ticket}: {worst.profit}" if worst else "No closed trade.",
        action_plan="Review every losing trade, tag one mistake, and stop trading after rule alerts.",
    )


def build_daily_review(db: Session, account: Account, review_date: date | None = None) -> DailyReviewDraft:
    day_start, day_end = trading_day_bounds()
    stmt = (
        select(Trade)
        .where(
            Trade.account_id == account.id,
            Trade.status == "closed",
            Trade.close_time >= day_start,
            Trade.close_time <= day_end,
        )
        .order_by(Trade.close_time.asc(), Trade.id.asc())
    )
    trades = list(db.scalars(stmt))
    stats = calculate_stats(db, account.id)
    pnl = sum((Decimal(t.profit or 0) for t in trades), Decimal("0"))
    fallback = _fallback_review(trades, pnl, float(stats["win_rate"]))

    settings = get_settings()
    if not settings.enable_ai:
        return fallback
    if not settings.openai_api_key:
        logger.warning("ENABLE_AI=true but OPENAI_API_KEY is missing")
        return fallback

    payload = [
        {
            "ticket": t.ticket,
            "symbol": t.symbol,
            "type": t.order_type,
            "lot": str(t.lot),
            "profit": str(t.profit),
            "r_multiple": str(t.r_multiple) if t.r_multiple is not None else None,
            "setup": t.setup_name,
            "emotion": t.emotion,
            "mistake_tags": t.mistake_tags or [],
            "notes": t.notes,
        }
        for t in trades
    ]
    prompt = (
        "You are a disciplined FTMO trading coach. Return compact JSON with keys "
        "ai_summary, mistakes, best_trade, worst_trade, action_plan. "
        f"Account equity: {account.equity}. Daily PnL: {pnl}. Trades: {json.dumps(payload)}"
    )

    try:
        client = OpenAI(api_key=settings.openai_api_key)
        response = client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {"role": "system", "content": "Return only valid JSON for the requested trading review."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        text = response.choices[0].message.content or "{}"
        data = json.loads(text)
        return DailyReviewDraft(**data)
    except Exception:
        logger.exception("OpenAI daily review failed; using deterministic fallback")
        return fallback
