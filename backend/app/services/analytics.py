from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Callable, Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PreTradeCheck, RuleViolation, Trade
from app.schemas.analytics import (
    AnalyticsBreakdownOut,
    AnalyticsInsightOut,
    AnalyticsInsightsOut,
    AnalyticsMetricsOut,
    AnalyticsOverviewOut,
    BreakdownRowOut,
    ConfidenceOut,
    EquityCurvePointOut,
)
from app.services.trade_direction import normalize_order_type

MIN_EARLY_SIGNAL_TRADES = 10
MIN_MEANINGFUL_TRADES = 30
RULE_LOOKBACK = timedelta(hours=4)

GROUP_BY_OPTIONS = {
    "symbol",
    "setup",
    "direction",
    "weekday",
    "hour",
    "session",
    "emotion",
    "mistake",
    "rule_violation",
}


@dataclass(frozen=True)
class AnalyticsDataset:
    account_id: int | None
    start_date: date | None
    end_date: date | None
    trades: list[Trade]
    checks: list[PreTradeCheck]
    violations: list[RuleViolation]


def _to_float(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 4)


def _money(value: Decimal) -> float:
    return round(float(value), 2)


def _confidence(sample_size: int) -> ConfidenceOut:
    if sample_size < MIN_EARLY_SIGNAL_TRADES:
        return ConfidenceOut(code="insufficient_sample", label="Insufficient sample", sample_size=sample_size)
    if sample_size < MIN_MEANINGFUL_TRADES:
        return ConfidenceOut(code="early_signal", label="Early signal", sample_size=sample_size)
    return ConfidenceOut(code="meaningful_sample", label="Meaningful sample", sample_size=sample_size)


def _trade_net_pnl(trade: Trade) -> Decimal:
    return Decimal(trade.profit or 0) + Decimal(trade.commission or 0) + Decimal(trade.swap or 0)


def _trade_time(trade: Trade) -> datetime | None:
    return trade.close_time or trade.open_time or trade.created_at


def _trade_direction(trade: Trade) -> str:
    return normalize_order_type(trade.order_type, trade.entry_price, trade.sl, trade.tp)


def _calculated_r_multiple(trade: Trade) -> Decimal | None:
    if trade.r_multiple is not None:
        return Decimal(trade.r_multiple)
    if trade.entry_price is None or trade.sl is None or trade.close_price is None:
        return None
    risk = abs(Decimal(trade.entry_price) - Decimal(trade.sl))
    if risk == 0:
        return None
    direction = _trade_direction(trade)
    reward = Decimal(trade.entry_price) - Decimal(trade.close_price) if direction == "SELL" else Decimal(trade.close_price) - Decimal(trade.entry_price)
    if reward == 0 and _trade_net_pnl(trade) != 0:
        return None
    return reward / risk


def _average(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def calculate_metrics(trades: Iterable[Trade]) -> AnalyticsMetricsOut:
    ordered = sorted(list(trades), key=lambda trade: (_trade_time(trade) or datetime.min.replace(tzinfo=timezone.utc), trade.id or 0))
    pnl_values = [_trade_net_pnl(trade) for trade in ordered]
    wins = [value for value in pnl_values if value > 0]
    losses = [value for value in pnl_values if value < 0]
    breakeven = [value for value in pnl_values if value == 0]
    gross_profit = sum(wins, Decimal("0"))
    gross_loss = abs(sum(losses, Decimal("0")))
    total = len(ordered)
    r_values = [value for value in (_calculated_r_multiple(trade) for trade in ordered) if value is not None]
    holding_minutes = [
        Decimal((trade.close_time - trade.open_time).total_seconds()) / Decimal("60")
        for trade in ordered
        if trade.open_time is not None and trade.close_time is not None and trade.close_time >= trade.open_time
    ]

    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0
    for pnl in pnl_values:
        if pnl > 0:
            current_wins += 1
            current_losses = 0
        elif pnl < 0:
            current_losses += 1
            current_wins = 0
        else:
            current_wins = 0
            current_losses = 0
        max_wins = max(max_wins, current_wins)
        max_losses = max(max_losses, current_losses)

    profit_factor = None
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss

    return AnalyticsMetricsOut(
        total_closed_trades=total,
        wins=len(wins),
        losses=len(losses),
        breakeven=len(breakeven),
        win_rate=round((len(wins) / total) * 100, 2) if total else 0.0,
        total_realized_pnl=_money(sum(pnl_values, Decimal("0"))),
        gross_profit=_money(gross_profit),
        gross_loss=_money(gross_loss),
        profit_factor=_to_float(profit_factor),
        expectancy=_money(_average(pnl_values) or Decimal("0")),
        average_winner=_money(_average(wins)) if wins else None,
        average_loser=_money(_average(losses)) if losses else None,
        average_r_multiple=_to_float(_average(r_values)),
        r_multiple_count=len(r_values),
        best_r_multiple=_to_float(max(r_values)) if r_values else None,
        worst_r_multiple=_to_float(min(r_values)) if r_values else None,
        average_holding_minutes=_to_float(_average(holding_minutes)),
        max_consecutive_wins=max_wins,
        max_consecutive_losses=max_losses,
        confidence=_confidence(total),
    )


def _date_bounds(start_date: date | None, end_date: date | None) -> tuple[datetime | None, datetime | None]:
    start = datetime.combine(start_date, time.min, tzinfo=timezone.utc) if start_date else None
    end = datetime.combine(end_date, time.max, tzinfo=timezone.utc) if end_date else None
    return start, end


def load_dataset(db: Session, account_id: int, start_date: date | None = None, end_date: date | None = None) -> AnalyticsDataset:
    start, end = _date_bounds(start_date, end_date)
    trade_time = func.coalesce(Trade.close_time, Trade.open_time, Trade.created_at)
    trade_stmt = (
        select(Trade)
        .where(Trade.account_id == account_id, Trade.status == "closed")
        .order_by(trade_time.asc(), Trade.id.asc())
    )
    if start:
        trade_stmt = trade_stmt.where(trade_time >= start)
    if end:
        trade_stmt = trade_stmt.where(trade_time <= end)

    rule_start = start - RULE_LOOKBACK if start else None
    check_stmt = select(PreTradeCheck).where(PreTradeCheck.account_id == account_id).order_by(PreTradeCheck.created_at.asc(), PreTradeCheck.id.asc())
    violation_stmt = select(RuleViolation).where(RuleViolation.account_id == account_id).order_by(RuleViolation.created_at.asc(), RuleViolation.id.asc())
    if rule_start:
        check_stmt = check_stmt.where(PreTradeCheck.created_at >= rule_start)
        violation_stmt = violation_stmt.where(RuleViolation.created_at >= rule_start)
    if end:
        check_stmt = check_stmt.where(PreTradeCheck.created_at <= end)
        violation_stmt = violation_stmt.where(RuleViolation.created_at <= end)

    return AnalyticsDataset(
        account_id=account_id,
        start_date=start_date,
        end_date=end_date,
        trades=list(db.scalars(trade_stmt)),
        checks=list(db.scalars(check_stmt)),
        violations=list(db.scalars(violation_stmt)),
    )


def build_equity_curve(trades: list[Trade]) -> list[EquityCurvePointOut]:
    by_date: dict[date, list[Trade]] = defaultdict(list)
    for trade in trades:
        event_time = _trade_time(trade)
        if event_time:
            by_date[event_time.date()].append(trade)

    cumulative = Decimal("0")
    curve: list[EquityCurvePointOut] = []
    for trade_date in sorted(by_date):
        day_pnl = sum((_trade_net_pnl(trade) for trade in by_date[trade_date]), Decimal("0"))
        cumulative += day_pnl
        curve.append(EquityCurvePointOut(date=trade_date, cumulative_pnl=_money(cumulative), trade_count=len(by_date[trade_date])))
    return curve


def build_overview(dataset: AnalyticsDataset) -> AnalyticsOverviewOut:
    metrics = calculate_metrics(dataset.trades)
    return AnalyticsOverviewOut(
        account_id=dataset.account_id,
        start_date=dataset.start_date,
        end_date=dataset.end_date,
        no_data=len(dataset.trades) == 0,
        metrics=metrics,
        equity_curve=build_equity_curve(dataset.trades),
    )


def _session_label(timestamp: datetime | None) -> str:
    if timestamp is None:
        return "Unknown"
    hour = timestamp.hour
    if 0 <= hour < 8:
        return "Asia (00-07 UTC)"
    if 8 <= hour < 13:
        return "London (08-12 UTC)"
    if 13 <= hour < 21:
        return "New York (13-20 UTC)"
    return "Rollover (21-23 UTC)"


def _rule_codes_for_trade(trade: Trade, checks: list[PreTradeCheck], violations: list[RuleViolation]) -> list[str]:
    opened_at = trade.open_time or trade.close_time
    if opened_at is None:
        return []
    window_start = opened_at - RULE_LOOKBACK
    codes: set[str] = set()
    trade_symbol = (trade.symbol or "").upper()
    for check in checks:
        if check.created_at is None or check.created_at < window_start or check.created_at > opened_at:
            continue
        if check.symbol and trade_symbol and check.symbol.upper() != trade_symbol:
            continue
        codes.update(str(code) for code in (check.rule_codes or []) if code)
    for violation in violations:
        if violation.created_at is None or violation.created_at < window_start or violation.created_at > opened_at:
            continue
        symbol = str((violation.violation_metadata or {}).get("symbol") or "").upper()
        if symbol and trade_symbol and symbol != trade_symbol:
            continue
        if violation.rule_code:
            codes.add(violation.rule_code)
    return sorted(codes)


def _group_values(group_by: str, trade: Trade, dataset: AnalyticsDataset) -> list[tuple[str, str]]:
    opened_at = trade.open_time or trade.close_time
    event_time = _trade_time(trade)
    if group_by == "symbol":
        return [(trade.symbol or "unknown", trade.symbol or "Unknown")]
    if group_by == "setup":
        return [(trade.setup_name, trade.setup_name)] if trade.setup_name else []
    if group_by == "direction":
        direction = _trade_direction(trade)
        return [(direction.lower(), direction.title())]
    if group_by == "weekday":
        if event_time is None:
            return [("unknown", "Unknown")]
        return [(event_time.strftime("%A").lower(), event_time.strftime("%A"))]
    if group_by == "hour":
        if opened_at is None:
            return [("unknown", "Unknown")]
        label = f"{opened_at.hour:02d}:00 UTC"
        return [(label, label)]
    if group_by == "session":
        label = _session_label(opened_at)
        return [(label, label)]
    if group_by == "emotion":
        return [(trade.emotion, trade.emotion)] if trade.emotion else []
    if group_by == "mistake":
        return [(tag, tag) for tag in (trade.mistake_tags or []) if tag]
    if group_by == "rule_violation":
        return [(code, code) for code in _rule_codes_for_trade(trade, dataset.checks, dataset.violations)]
    raise ValueError(f"Unsupported analytics group_by: {group_by}")


def build_breakdown(dataset: AnalyticsDataset, group_by: str) -> AnalyticsBreakdownOut:
    if group_by not in GROUP_BY_OPTIONS:
        raise ValueError(f"Unsupported analytics group_by: {group_by}")

    grouped: dict[str, dict[str, object]] = {}
    missing = 0
    for trade in dataset.trades:
        values = _group_values(group_by, trade, dataset)
        if not values:
            missing += 1
            continue
        for key, label in values:
            if key not in grouped:
                grouped[key] = {"label": label, "trades": []}
            grouped[key]["trades"].append(trade)

    rows = [
        BreakdownRowOut(
            group_by=group_by,
            key=key,
            label=str(value["label"]),
            metrics=calculate_metrics(value["trades"]),
        )
        for key, value in grouped.items()
    ]
    rows.sort(key=lambda row: (row.metrics.total_closed_trades, row.metrics.expectancy), reverse=True)
    return AnalyticsBreakdownOut(
        account_id=dataset.account_id,
        start_date=dataset.start_date,
        end_date=dataset.end_date,
        group_by=group_by,
        rows=rows,
        missing_journal_count=missing,
    )


def _row_by_expectancy(rows: list[BreakdownRowOut], reverse: bool) -> BreakdownRowOut | None:
    eligible = [row for row in rows if row.metrics.total_closed_trades >= MIN_EARLY_SIGNAL_TRADES]
    if not eligible:
        return None
    return sorted(eligible, key=lambda row: row.metrics.expectancy, reverse=reverse)[0]


def _insight_from_row(tone: str, title: str, template: str, row: BreakdownRowOut, metric_name: str = "expectancy") -> AnalyticsInsightOut:
    metric_value = getattr(row.metrics, metric_name)
    return AnalyticsInsightOut(
        tone=tone,
        title=title,
        observation=template.format(label=row.label, sample=row.metrics.total_closed_trades, confidence=row.metrics.confidence.label, value=metric_value),
        group_by=row.group_by,
        key=row.key,
        sample_size=row.metrics.total_closed_trades,
        confidence=row.metrics.confidence,
        metric_name=metric_name,
        metric_value=metric_value,
        supported=True,
    )


def _unsupported(title: str, group_by: str) -> AnalyticsInsightOut:
    return AnalyticsInsightOut(
        tone="info",
        title=title,
        observation=f"No observation yet for {group_by}. At least {MIN_EARLY_SIGNAL_TRADES} closed trades in a group are needed before showing this pattern.",
        group_by=group_by,
        supported=False,
    )


def _negative_row(rows: list[BreakdownRowOut], predicate: Callable[[BreakdownRowOut], bool] | None = None) -> BreakdownRowOut | None:
    eligible = [
        row
        for row in rows
        if row.metrics.total_closed_trades >= MIN_EARLY_SIGNAL_TRADES and row.metrics.expectancy < 0 and (predicate(row) if predicate else True)
    ]
    if not eligible:
        return None
    return sorted(eligible, key=lambda row: row.metrics.expectancy)[0]


def build_insights(dataset: AnalyticsDataset) -> AnalyticsInsightsOut:
    insights: list[AnalyticsInsightOut] = []
    overview = calculate_metrics(dataset.trades)
    if overview.total_closed_trades < MIN_EARLY_SIGNAL_TRADES:
        return AnalyticsInsightsOut(
            account_id=dataset.account_id,
            start_date=dataset.start_date,
            end_date=dataset.end_date,
            insights=[
                AnalyticsInsightOut(
                    tone="info",
                    title="More closed trades needed",
                    observation=f"Only {overview.total_closed_trades} closed trade(s) are in this range. Analytics will show observations after at least {MIN_EARLY_SIGNAL_TRADES} trades in a group.",
                    sample_size=overview.total_closed_trades,
                    confidence=overview.confidence,
                    supported=False,
                )
            ],
        )

    breakdowns = {name: build_breakdown(dataset, name).rows for name in ("setup", "symbol", "session", "emotion", "mistake", "rule_violation")}

    strongest_setup = _row_by_expectancy(breakdowns["setup"], reverse=True)
    weakest_setup = _row_by_expectancy(breakdowns["setup"], reverse=False)
    insights.append(
        _insight_from_row("edge", "Strongest setup observation", "{label} has the highest expectancy in this range: {value} per trade across {sample} trades ({confidence}).", strongest_setup)
        if strongest_setup
        else _unsupported("Strongest setup observation", "setup")
    )
    insights.append(
        _insight_from_row("leak", "Weakest setup observation", "{label} has the lowest expectancy in this range: {value} per trade across {sample} trades ({confidence}).", weakest_setup)
        if weakest_setup
        else _unsupported("Weakest setup observation", "setup")
    )

    best_symbol = _row_by_expectancy(breakdowns["symbol"], reverse=True)
    worst_symbol = _row_by_expectancy(breakdowns["symbol"], reverse=False)
    if best_symbol:
        insights.append(_insight_from_row("edge", "Best symbol observation", "{label} has the highest symbol expectancy: {value} per trade across {sample} trades ({confidence}).", best_symbol))
    if worst_symbol:
        insights.append(_insight_from_row("leak", "Worst symbol observation", "{label} has the lowest symbol expectancy: {value} per trade across {sample} trades ({confidence}).", worst_symbol))

    weak_session = _negative_row(breakdowns["session"])
    insights.append(
        _insight_from_row("leak", "Losses concentrate by session", "{label} shows a negative average outcome of {value} per trade across {sample} trades ({confidence}).", weak_session)
        if weak_session
        else _unsupported("Losses concentrate by session", "session")
    )

    mistake = _negative_row(breakdowns["mistake"])
    insights.append(
        _insight_from_row("leak", "Recurring mistake observation", "{label} appears with a negative average outcome of {value} per trade across {sample} tagged trades ({confidence}).", mistake)
        if mistake
        else _unsupported("Recurring mistake observation", "mistake")
    )

    emotion = _negative_row(breakdowns["emotion"])
    insights.append(
        _insight_from_row("leak", "Emotion outcome observation", "{label} is associated with a negative average outcome of {value} per trade across {sample} trades ({confidence}).", emotion)
        if emotion
        else _unsupported("Emotion outcome observation", "emotion")
    )

    rule_violation = _negative_row(breakdowns["rule_violation"])
    insights.append(
        _insight_from_row("leak", "Rule-code before trade observation", "{label} appeared before trades with a negative average outcome of {value} per trade across {sample} trades ({confidence}).", rule_violation)
        if rule_violation
        else _unsupported("Rule-code before trade observation", "rule_violation")
    )

    return AnalyticsInsightsOut(account_id=dataset.account_id, start_date=dataset.start_date, end_date=dataset.end_date, insights=insights)
