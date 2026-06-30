import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import current_account_or_404, require_mt5_api_key
from app.db.session import get_db
from app.models import Account, PreTradeCheck, RiskRule, Rule
from app.schemas.pre_trade import PreCloseCheckIn, PreCloseCheckOut, PreTradeCheckHistoryOut, PreTradeCheckIn, PreTradeCheckOut
from app.schemas.rules import RiskRuleIn, RiskRuleOut, RuleCatalogCreateIn, RuleCatalogOut, RuleCatalogUpdateIn, RuleEvaluationOut
from app.services.rule_engine import create_catalog_rule, delete_catalog_rule, ensure_rule_catalog, evaluate_rules, get_or_create_rule, pre_close_check, pre_trade_check, update_catalog_rule
from app.services.timezone import now_utc

router = APIRouter(prefix="/api/rules", tags=["rules"])
logger = logging.getLogger(__name__)


def safe_block_response(reason: str, message: str, error_type: str | None = None) -> dict[str, object]:
    violation = {
        "rule_code": reason,
        "severity": "critical",
        "action": "block",
        "message": message,
        "metadata": {"error_type": error_type} if error_type else {},
    }
    return {
        "allowed": False,
        "status": "blocked",
        "decision": "BLOCK",
        "reason": reason,
        "message": message,
        "violations": [violation],
        "warnings": [],
        "checked_at": now_utc(),
        "rule_evaluation_id": None,
        "alerts": [reason],
    }


@router.get("", response_model=RiskRuleOut)
def get_rules(db: Session = Depends(get_db)) -> RiskRule:
    account = current_account_or_404(db)
    rule = get_or_create_rule(db, account)
    db.commit()
    return rule


@router.put("", response_model=RiskRuleOut)
def update_rules(payload: RiskRuleIn, db: Session = Depends(get_db)) -> RiskRule:
    account = current_account_or_404(db)
    rule = get_or_create_rule(db, account)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/catalog", response_model=list[RuleCatalogOut])
def list_rule_catalog(db: Session = Depends(get_db)) -> list[Rule]:
    rules = ensure_rule_catalog(db)
    db.commit()
    return rules


@router.post("/catalog", response_model=RuleCatalogOut, status_code=201)
def create_rule_catalog(payload: RuleCatalogCreateIn, db: Session = Depends(get_db)) -> Rule:
    try:
        rule = create_catalog_rule(db, payload.model_dump())
        db.commit()
        db.refresh(rule)
        return rule
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Rule code already exists") from exc


@router.put("/catalog/{code}", response_model=RuleCatalogOut)
def update_rule_catalog(code: str, payload: RuleCatalogUpdateIn, db: Session = Depends(get_db)) -> Rule:
    rule = update_catalog_rule(db, code, payload.model_dump(exclude_unset=True))
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/catalog/{code}", status_code=204)
def delete_rule_catalog(code: str, db: Session = Depends(get_db)) -> Response:
    result = delete_catalog_rule(db, code)
    if result is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    if result is False:
        raise HTTPException(status_code=400, detail="Built-in rules cannot be deleted")
    db.commit()
    return Response(status_code=204)


@router.post("/evaluate", response_model=RuleEvaluationOut)
def evaluate(db: Session = Depends(get_db)) -> dict[str, object]:
    account: Account = current_account_or_404(db)
    result = evaluate_rules(db, account)
    db.commit()
    return result


@router.post("/pre-trade-check", response_model=PreTradeCheckOut, dependencies=[Depends(require_mt5_api_key)])
def run_pre_trade_check(payload: PreTradeCheckIn, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        account = db.scalar(select(Account).where(Account.account_number == payload.account_number))
        if not account:
            raise HTTPException(status_code=404, detail="Account not found. Send heartbeat before pre-trade checks.")
        result = pre_trade_check(db, account, payload)
        db.commit()
        return result
    except HTTPException:
        raise
    except (SQLAlchemyError, Exception) as exc:
        db.rollback()
        logger.exception(
            "Pre-trade rule evaluation failed; returning safe block response",
            extra={
                "account_number": payload.account_number,
                "symbol": payload.symbol,
                "order_type": payload.order_type,
            },
        )
        message = f"Rule engine error. Trade blocked for safety: {exc.__class__.__name__}."
        return safe_block_response("RULE_ENGINE_ERROR", message, exc.__class__.__name__)


@router.post("/pre-close-check", response_model=PreCloseCheckOut, dependencies=[Depends(require_mt5_api_key)])
def run_pre_close_check(payload: PreCloseCheckIn, db: Session = Depends(get_db)) -> dict[str, object]:
    try:
        account = db.scalar(select(Account).where(Account.account_number == payload.account_number))
        if not account:
            raise HTTPException(status_code=404, detail="Account not found. Send heartbeat before close checks.")
        result = pre_close_check(db, account, payload)
        db.commit()
        return result
    except HTTPException:
        raise
    except (SQLAlchemyError, Exception) as exc:
        db.rollback()
        logger.exception(
            "Pre-close rule evaluation failed; returning safe block response",
            extra={
                "account_number": payload.account_number,
                "ticket": payload.ticket,
                "symbol": payload.symbol,
            },
        )
        message = f"Rule engine error. Close blocked for safety: {exc.__class__.__name__}."
        return safe_block_response("RULE_ENGINE_ERROR", message, exc.__class__.__name__)


@router.get("/pre-trade-checks", response_model=list[PreTradeCheckHistoryOut])
def list_pre_trade_checks(db: Session = Depends(get_db), blocked_only: bool = True) -> list[PreTradeCheck]:
    stmt = select(PreTradeCheck).order_by(PreTradeCheck.created_at.desc(), PreTradeCheck.id.desc()).limit(200)
    if blocked_only:
        stmt = stmt.where(PreTradeCheck.allowed.is_(False))
    return list(db.scalars(stmt))
