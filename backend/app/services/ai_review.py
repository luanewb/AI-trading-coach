import json
import logging
from collections import Counter
from datetime import date, datetime, time, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from openai import OpenAI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Account, PreTradeCheck, RiskRule, RuleViolation, Trade

logger = logging.getLogger(__name__)

DISCLAIMER = "Chỉ là huấn luyện hành vi giao dịch cho mục đích giáo dục; không phải lời khuyên tài chính hoặc khuyến nghị mua/bán."

NO_STOP_CODES = {"NO_STOP_LOSS"}
MAX_LOT_CODES = {"MAX_LOT", "MAX_LOT_SIZE"}
REVENGE_CODES = {"REVENGE_TRADING"}
COOLDOWN_CODES = {"COOLDOWN", "COOLDOWN_AFTER_LOSS"}
RISK_CODES = {"RISK_PER_TRADE", "MAX_RISK_PER_TRADE"}


def _money(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _ratio(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _trade_net_pnl(trade: Trade) -> Decimal:
    return Decimal(trade.profit or 0) + Decimal(trade.commission or 0) + Decimal(trade.swap or 0)


def _day_bounds(target_date: date) -> tuple[datetime, datetime]:
    settings = get_settings()
    local_tz = ZoneInfo(settings.ftmo_timezone)
    start_local = datetime.combine(target_date, time.min, tzinfo=local_tz)
    end_local = datetime.combine(target_date, time.max, tzinfo=local_tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _counter_items(counter: Counter[str], limit: int = 5) -> list[dict[str, Any]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit)]


def _daily_trades(db: Session, account_id: int, target_date: date) -> list[Trade]:
    day_start, day_end = _day_bounds(target_date)
    return list(
        db.scalars(
            select(Trade)
            .where(
                Trade.account_id == account_id,
                Trade.status == "closed",
                Trade.close_time >= day_start,
                Trade.close_time <= day_end,
            )
            .order_by(Trade.close_time.asc(), Trade.id.asc())
        )
    )


def _daily_pre_trade_checks(db: Session, account_id: int, target_date: date) -> list[PreTradeCheck]:
    day_start, day_end = _day_bounds(target_date)
    return list(
        db.scalars(
            select(PreTradeCheck)
            .where(
                PreTradeCheck.account_id == account_id,
                PreTradeCheck.created_at >= day_start,
                PreTradeCheck.created_at <= day_end,
            )
            .order_by(PreTradeCheck.created_at.asc(), PreTradeCheck.id.asc())
        )
    )


def _daily_rule_violations(db: Session, account_id: int, target_date: date) -> list[RuleViolation]:
    day_start, day_end = _day_bounds(target_date)
    return list(
        db.scalars(
            select(RuleViolation)
            .where(
                RuleViolation.account_id == account_id,
                RuleViolation.created_at >= day_start,
                RuleViolation.created_at <= day_end,
            )
            .order_by(RuleViolation.created_at.asc(), RuleViolation.id.asc())
        )
    )


def _risk_rule(db: Session, account_id: int) -> RiskRule | None:
    return db.scalar(select(RiskRule).where(RiskRule.account_id == account_id).limit(1))


def _max_consecutive_losses(trades: list[Trade]) -> int:
    longest = 0
    current = 0
    for trade in trades:
        if _trade_net_pnl(trade) < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def build_daily_metrics(db: Session, account: Account, target_date: date) -> dict[str, Any]:
    trades = _daily_trades(db, account.id, target_date)
    checks = _daily_pre_trade_checks(db, account.id, target_date)
    violations = _daily_rule_violations(db, account.id, target_date)

    pnl_values = [_trade_net_pnl(trade) for trade in trades]
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value < 0]
    gross_profit = sum(wins, Decimal("0"))
    gross_loss = abs(sum(losses, Decimal("0")))
    r_values = [Decimal(trade.r_multiple) for trade in trades if trade.r_multiple is not None]
    symbol_counts = Counter(trade.symbol for trade in trades if trade.symbol)
    setup_counts = Counter(trade.setup_name for trade in trades if trade.setup_name)
    emotion_counts = Counter(trade.emotion for trade in trades if trade.emotion)
    mistake_counts = Counter(tag for trade in trades for tag in (trade.mistake_tags or []) if tag)
    violation_counts = Counter(v.rule_code for v in violations if v.rule_code)
    blocked_checks = [check for check in checks if not check.allowed]

    journal_missing = {
        "setup": sum(1 for trade in trades if not trade.setup_name),
        "emotion": sum(1 for trade in trades if not trade.emotion),
        "notes": sum(1 for trade in trades if not trade.notes),
        "mistake_tags_on_losses": sum(1 for trade in trades if _trade_net_pnl(trade) < 0 and not (trade.mistake_tags or [])),
    }

    return {
        "account_id": account.id,
        "trading_date": target_date.isoformat(),
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round((len(wins) / len(trades)) * 100, 2) if trades else 0.0,
        "realized_pnl": _money(sum(pnl_values, Decimal("0"))),
        "average_winner": _money(gross_profit / len(wins)) if wins else None,
        "average_loser": _money(sum(losses, Decimal("0")) / len(losses)) if losses else None,
        "profit_factor": _ratio(gross_profit / gross_loss) if gross_loss else None,
        "average_r_multiple": _ratio(sum(r_values, Decimal("0")) / len(r_values)) if r_values else None,
        "max_consecutive_losses": _max_consecutive_losses(trades),
        "rule_violations": {
            "total": len(violations),
            "by_code": _counter_items(violation_counts, 10),
            "items": [
                {
                    "rule_code": violation.rule_code,
                    "severity": violation.severity,
                    "action": violation.action,
                    "message": violation.message,
                    "created_at": violation.created_at.isoformat() if violation.created_at else None,
                }
                for violation in violations[:20]
            ],
        },
        "blocked_pre_trade_attempts": len(blocked_checks),
        "pre_trade_attempts": len(checks),
        "most_traded_symbols": _counter_items(symbol_counts),
        "setups_used": _counter_items(setup_counts),
        "emotions": _counter_items(emotion_counts),
        "mistakes": _counter_items(mistake_counts),
        "journal": {
            "missing": journal_missing,
            "incomplete_trade_count": sum(
                1
                for trade in trades
                if not trade.setup_name
                or not trade.emotion
                or not trade.notes
                or (_trade_net_pnl(trade) < 0 and not (trade.mistake_tags or []))
            ),
        },
    }


def _count_codes(checks: list[PreTradeCheck], violations: list[RuleViolation], codes: set[str]) -> int:
    check_total = sum(1 for check in checks if codes.intersection(set(check.rule_codes or [])))
    violation_total = sum(1 for violation in violations if violation.rule_code in codes)
    return max(check_total, violation_total)


def _factor(code: str, label: str, count: int, penalty: int, reason: str) -> dict[str, Any]:
    return {"code": code, "label": label, "observed": count, "penalty": penalty, "reason": reason}


def build_discipline_score(db: Session, account: Account, metrics: dict[str, Any], target_date: date) -> tuple[int, list[dict[str, Any]]]:
    checks = _daily_pre_trade_checks(db, account.id, target_date)
    violations = _daily_rule_violations(db, account.id, target_date)
    rule = _risk_rule(db, account.id)

    no_stop = max(_count_codes(checks, violations, NO_STOP_CODES), sum(1 for check in checks if check.sl is None))
    max_lot = _count_codes(checks, violations, MAX_LOT_CODES)
    revenge = _count_codes(checks, violations, REVENGE_CODES) + sum(item["count"] for item in metrics["mistakes"] if "revenge" in item["name"].lower())
    cooldown = _count_codes(checks, violations, COOLDOWN_CODES)
    blocked = int(metrics["blocked_pre_trade_attempts"])
    missing_journal = sum(int(value) for value in metrics["journal"]["missing"].values())
    max_trades_limit = int(rule.max_trades_per_day) if rule else None
    extra_trades = max(0, int(metrics["total_trades"]) - max_trades_limit) if max_trades_limit else 0
    risk_violations = _count_codes(checks, violations, RISK_CODES)

    breakdown = [
        _factor("no_stop_loss", "Stop-loss discipline", no_stop, min(no_stop * 12, 30), f"{no_stop} stop-loss issue(s) found in pre-trade/rule data."),
        _factor("max_lot", "Lot-size discipline", max_lot, min(max_lot * 10, 25), f"{max_lot} max-lot violation(s) found."),
        _factor("revenge_trading", "Revenge-trading control", revenge, min(revenge * 12, 24), f"{revenge} revenge-trading flag(s) found."),
        _factor("cooldown", "Cooldown adherence", cooldown, min(cooldown * 10, 20), f"{cooldown} cooldown violation(s) found."),
        _factor("blocked_orders", "Blocked pre-trade attempts", blocked, min(blocked * 5, 20), f"{blocked} blocked order attempt(s) recorded."),
        _factor("journal_completeness", "Journal completeness", missing_journal, min(missing_journal * 3, 20), f"{missing_journal} required journal field(s) missing across closed trades."),
        _factor("max_trades_per_day", "Max trades/day adherence", extra_trades, min(extra_trades * 8, 16), f"{extra_trades} trade(s) above the configured daily limit." if max_trades_limit else "No max-trades rule configured."),
        _factor("risk_per_trade", "Risk-per-trade adherence", risk_violations, min(risk_violations * 10, 20), f"{risk_violations} risk-per-trade violation(s) found."),
    ]
    score = max(0, 100 - sum(item["penalty"] for item in breakdown))
    return score, breakdown


def build_deterministic_findings(metrics: dict[str, Any], score: int) -> dict[str, Any]:
    positives: list[str] = []
    risks: list[str] = []
    plan: list[str] = []

    if metrics["blocked_pre_trade_attempts"] == 0:
        positives.append("Không ghi nhận lệnh bị chặn trước khi vào lệnh trong ngày này.")
    if metrics["rule_violations"]["total"] == 0:
        positives.append("Không ghi nhận vi phạm quy tắc trong ngày này.")
    if metrics["journal"]["incomplete_trade_count"] == 0 and metrics["total_trades"] > 0:
        positives.append("Tất cả lệnh đã đóng đều có đủ trường nhật ký cần thiết.")

    if metrics["total_trades"] == 0:
        risks.append("Không tìm thấy lệnh đã đóng trong ngày này.")
        plan.append("Dùng review này như bước chuẩn bị và kiểm tra đồng bộ tài khoản trước phiên tiếp theo.")
    if metrics["blocked_pre_trade_attempts"] > 0:
        risks.append(f"{metrics['blocked_pre_trade_attempts']} lần vào lệnh bị chặn cho thấy rule engine đã ngăn một hoặc nhiều lệnh dự kiến.")
        plan.append("Trước khi đặt lệnh, kiểm tra lại SL, khối lượng, cooldown và mức rủi ro đã đúng rule.")
    if metrics["journal"]["incomplete_trade_count"] > 0:
        risks.append(f"{metrics['journal']['incomplete_trade_count']} lệnh đã đóng còn thiếu dữ liệu nhật ký.")
        plan.append("Hoàn thiện setup, cảm xúc, ghi chú và thẻ lỗi trước khi tạo review ngày mai.")
    if metrics["max_consecutive_losses"] >= 2:
        risks.append(f"Chuỗi thua liên tiếp cao nhất trong phiên là {metrics['max_consecutive_losses']} lệnh.")
        plan.append("Sau hai lệnh thua, dừng lại và kiểm tra lệnh tiếp theo có còn khớp setup đã viết hay không.")
    if metrics["mistakes"]:
        top = metrics["mistakes"][0]
        risks.append(f"Lỗi được gắn thẻ nhiều nhất: {top['name']} ({top['count']} lần).")

    if not positives:
        positives.append("Review có đủ dữ liệu đã lưu để tính baseline kỷ luật.")
    if not risks:
        risks.append("Không phát hiện mẫu rủi ro lớn từ dữ liệu đã lưu.")
    if not plan:
        plan.extend([
            "Kiểm tra SL và rủi ro trước mỗi lệnh.",
            "Ghi lại setup và trạng thái cảm xúc ngay sau mỗi lệnh.",
            "Dừng giao dịch khi hệ thống kích hoạt block hoặc lock.",
        ])

    return {
        "facts": [
            f"Có {metrics['total_trades']} lệnh đã đóng, gồm {metrics['wins']} lệnh thắng và {metrics['losses']} lệnh thua.",
            f"PnL đã thực hiện là {metrics['realized_pnl']} với win rate {metrics['win_rate']}%.",
            f"Ghi nhận {metrics['rule_violations']['total']} vi phạm quy tắc và {metrics['blocked_pre_trade_attempts']} lần vào lệnh bị chặn.",
        ],
        "positive_behaviors": positives[:3],
        "risk_patterns": risks[:3],
        "tomorrows_plan": plan[:3],
        "strongest_positive_behavior": positives[0],
        "biggest_mistake_or_risk_pattern": risks[0],
        "score_interpretation": "Kỷ luật tốt" if score >= 80 else "Cần tập trung sửa kỷ luật" if score < 60 else "Kỷ luật còn lẫn lộn",
        "disclaimer": DISCLAIMER,
    }


def deterministic_narrative(metrics: dict[str, Any], findings: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Sự thật từ dữ liệu:",
            *[f"- {fact}" for fact in findings["facts"]],
            "",
            "Quan sát huấn luyện:",
            *[f"- {item}" for item in findings["risk_patterns"]],
            "",
            "Kế hoạch phiên tới:",
            *[f"- {item}" for item in findings["tomorrows_plan"]],
            "",
            DISCLAIMER,
        ]
    )


def _ai_prompt(metrics: dict[str, Any], score: int, breakdown: list[dict[str, Any]], findings: dict[str, Any]) -> str:
    payload = {
        "metrics": metrics,
        "discipline_score": score,
        "discipline_breakdown": breakdown,
        "deterministic_findings": findings,
        "instructions": [
            "Write all user-facing strings in Vietnamese.",
            "Keep trading symbols, rule codes, numbers, and dates unchanged.",
            "Use only facts in this JSON.",
            "Do not invent trades, causes, or unsupported mistakes.",
            "Do not provide buy/sell/asset recommendations.",
            "Label interpretations as observations, not certainty.",
            "Return JSON with keys facts, observations, positive_behaviors, next_session_recommendations, disclaimer.",
            "next_session_recommendations must contain at most 3 items.",
        ],
    }
    return json.dumps(payload, ensure_ascii=True)


def _parse_model_json(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text or "{}")


def _format_ai_narrative(data: dict[str, Any], findings: dict[str, Any]) -> str:
    recommendations = data.get("next_session_recommendations") or findings["tomorrows_plan"]
    lines = [
        "Sự thật từ dữ liệu:",
        *[f"- {item}" for item in (data.get("facts") or findings["facts"])],
        "",
        "Quan sát của AI:",
        *[f"- {item}" for item in (data.get("observations") or findings["risk_patterns"])],
        "",
        "Điểm kỷ luật tích cực:",
        *[f"- {item}" for item in (data.get("positive_behaviors") or findings["positive_behaviors"])],
        "",
        "Kế hoạch phiên tới:",
        *[f"- {item}" for item in recommendations[:3]],
        "",
        data.get("disclaimer") or DISCLAIMER,
    ]
    return "\n".join(lines)


def _generate_openai_narrative(settings: Any, metrics: dict[str, Any], score: int, breakdown: list[dict[str, Any]], findings: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not settings.openai_api_key:
        logger.warning("ENABLE_AI=true and AI_PROVIDER=openai but OPENAI_API_KEY is missing")
        return deterministic_narrative(metrics, findings), {"ai_enabled": False, "fallback_reason": "OPENAI_API_KEY missing", "provider": "openai"}

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a trading behavior coach. You review discipline only. "
                    "Return compact valid JSON in Vietnamese and never recommend buying or selling an asset."
                ),
            },
            {"role": "user", "content": _ai_prompt(metrics, score, breakdown, findings)},
        ],
        temperature=0.2,
    )
    raw_text = response.choices[0].message.content or "{}"
    data = _parse_model_json(raw_text)
    return _format_ai_narrative(data, findings), {
        "ai_enabled": True,
        "model": settings.openai_model,
        "provider": "openai",
        "generated_with": "chat.completions",
    }


def _gemini_text(response_data: dict[str, Any]) -> str:
    candidates = response_data.get("candidates") or []
    if not candidates:
        return "{}"
    parts = (((candidates[0] or {}).get("content") or {}).get("parts") or [])
    return "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict)).strip() or "{}"


def _generate_gemini_narrative(settings: Any, metrics: dict[str, Any], score: int, breakdown: list[dict[str, Any]], findings: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    if not settings.gemini_api_key:
        logger.warning("ENABLE_AI=true and AI_PROVIDER=gemini but GEMINI_API_KEY is missing")
        return deterministic_narrative(metrics, findings), {"ai_enabled": False, "fallback_reason": "GEMINI_API_KEY missing", "provider": "gemini"}

    model_name = settings.gemini_model if settings.gemini_model.startswith("models/") else f"models/{settings.gemini_model}"
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent"
    response = httpx.post(
        url,
        headers={"x-goog-api-key": settings.gemini_api_key},
        json={
            "systemInstruction": {
                "parts": [
                    {
                        "text": (
                            "You are a trading behavior coach. You review discipline only. "
                            "Return compact valid JSON in Vietnamese and never recommend buying or selling an asset."
                        )
                    }
                ]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": _ai_prompt(metrics, score, breakdown, findings)}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        },
        timeout=30,
    )
    response.raise_for_status()
    data = _parse_model_json(_gemini_text(response.json()))
    return _format_ai_narrative(data, findings), {
        "ai_enabled": True,
        "model": settings.gemini_model,
        "provider": "gemini",
        "generated_with": "generateContent",
    }


def maybe_generate_ai_narrative(metrics: dict[str, Any], score: int, breakdown: list[dict[str, Any]], findings: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    settings = get_settings()
    fallback = deterministic_narrative(metrics, findings)
    if not settings.enable_ai:
        return fallback, {"ai_enabled": False, "fallback_reason": "ENABLE_AI=false"}

    provider = settings.ai_provider.strip().lower()
    try:
        if provider == "gemini":
            return _generate_gemini_narrative(settings, metrics, score, breakdown, findings)
        if provider == "openai":
            return _generate_openai_narrative(settings, metrics, score, breakdown, findings)

        logger.warning("Unsupported AI_PROVIDER=%s; using deterministic fallback", settings.ai_provider)
        return fallback, {"ai_enabled": False, "fallback_reason": f"Unsupported AI_PROVIDER={settings.ai_provider}"}
    except httpx.HTTPStatusError as exc:
        status_code = exc.response.status_code
        logger.warning("%s daily review request failed with HTTP %s; using deterministic fallback", provider, status_code)
        return fallback, {"ai_enabled": False, "fallback_reason": f"{provider} request failed: HTTP {status_code}", "provider": provider}
    except Exception:
        logger.exception("%s daily review failed; using deterministic fallback", provider)
        return fallback, {"ai_enabled": False, "fallback_reason": f"{provider} request failed", "provider": provider}


def build_daily_review_payload(db: Session, account: Account, target_date: date) -> dict[str, Any]:
    metrics = build_daily_metrics(db, account, target_date)
    score, breakdown = build_discipline_score(db, account, metrics, target_date)
    findings = build_deterministic_findings(metrics, score)
    narrative, metadata = maybe_generate_ai_narrative(metrics, score, breakdown, findings)
    return {
        "metrics_snapshot": metrics,
        "discipline_score": score,
        "discipline_breakdown": breakdown,
        "deterministic_findings": findings,
        "ai_narrative": narrative,
        "model_metadata": metadata,
    }
