from decimal import Decimal


def decimal_or_none(value: object) -> Decimal | None:
    if value is None:
        return None
    amount = Decimal(str(value))
    return amount if amount > 0 else None


def direction_from_prices(entry_price: object, sl: object, tp: object) -> str | None:
    entry = decimal_or_none(entry_price)
    stop_loss = decimal_or_none(sl)
    take_profit = decimal_or_none(tp)
    if entry is None:
        return None

    sell_votes = 0
    buy_votes = 0
    if stop_loss is not None:
        if stop_loss > entry:
            sell_votes += 1
        elif stop_loss < entry:
            buy_votes += 1
    if take_profit is not None:
        if take_profit < entry:
            sell_votes += 1
        elif take_profit > entry:
            buy_votes += 1

    if sell_votes > buy_votes:
        return "SELL"
    if buy_votes > sell_votes:
        return "BUY"
    return None


def normalize_order_type(order_type: object, entry_price: object = None, sl: object = None, tp: object = None) -> str:
    inferred = direction_from_prices(entry_price, sl, tp)
    if inferred:
        return inferred

    normalized = str(order_type or "").upper()
    if normalized in {"ORDER_TYPE_SELL", "SELL", "SHORT", "POSITION_TYPE_SELL"}:
        return "SELL"
    if normalized in {"ORDER_TYPE_BUY", "BUY", "LONG", "POSITION_TYPE_BUY"}:
        return "BUY"
    return str(order_type or "")


def is_sell_order(order_type: object, entry_price: object = None, sl: object = None, tp: object = None) -> bool:
    return normalize_order_type(order_type, entry_price, sl, tp) == "SELL"
