from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_account_or_404, require_mt5_api_key
from app.db.session import get_db
from app.models import Account, PreTradeCheck, RiskRule
from app.schemas.pre_trade import PreTradeCheckHistoryOut, PreTradeCheckIn, PreTradeCheckOut
from app.schemas.rules import RiskRuleIn, RiskRuleOut, RuleEvaluationOut
from app.services.rule_engine import evaluate_rules, get_or_create_rule, pre_trade_check

router = APIRouter(prefix="/api/rules", tags=["rules"])


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
    for field, value in payload.model_dump().items():
        setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.post("/evaluate", response_model=RuleEvaluationOut)
def evaluate(db: Session = Depends(get_db)) -> dict[str, object]:
    account: Account = current_account_or_404(db)
    result = evaluate_rules(db, account)
    db.commit()
    return result


@router.post("/pre-trade-check", response_model=PreTradeCheckOut, dependencies=[Depends(require_mt5_api_key)])
def run_pre_trade_check(payload: PreTradeCheckIn, db: Session = Depends(get_db)) -> dict[str, object]:
    account = db.scalar(select(Account).where(Account.account_number == payload.account_number))
    if not account:
        raise HTTPException(status_code=404, detail="Account not found. Send heartbeat before pre-trade checks.")
    result = pre_trade_check(db, account, payload)
    db.commit()
    return result


@router.get("/pre-trade-checks", response_model=list[PreTradeCheckHistoryOut])
def list_pre_trade_checks(db: Session = Depends(get_db), blocked_only: bool = True) -> list[PreTradeCheck]:
    stmt = select(PreTradeCheck).order_by(PreTradeCheck.created_at.desc(), PreTradeCheck.id.desc()).limit(200)
    if blocked_only:
        stmt = stmt.where(PreTradeCheck.allowed.is_(False))
    return list(db.scalars(stmt))
