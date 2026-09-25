from pathlib import Path
import re


EA_SOURCE = Path(__file__).resolve().parents[2] / "mt5-ea" / "AITradingCoachConnector.mq5"


def _function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    opening_brace = source.index("{", start)
    depth = 0
    for index in range(opening_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[opening_brace + 1 : index]
    raise AssertionError(f"Unclosed function: {signature}")


def test_history_sync_keeps_the_history_select_deal_list_intact() -> None:
    source = EA_SOURCE.read_text(encoding="utf-8")
    sender = _function_body(source, "bool SendHistoryDealEvent(ulong deal_ticket)")
    sync = _function_body(source, "void SyncRecentTradeHistory()")
    sender_code = re.sub(r"//.*", "", sender)

    assert "HistoryDealSelect(" not in sender_code
    assert re.search(r"HistoryDealGetTicket\s*\(\s*index\s*\)", sync)
    assert "SendHistoryDealEvent(deal_ticket)" in sync
