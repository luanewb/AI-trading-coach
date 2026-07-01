from app.core.config import get_settings
from app.services import ai_review


def _metrics():
    return {
        "total_trades": 1,
        "wins": 1,
        "losses": 0,
        "realized_pnl": "25.00",
        "win_rate": 100.0,
        "rule_violations": {"total": 0},
        "blocked_pre_trade_attempts": 0,
    }


def _findings():
    return {
        "facts": ["Có 1 lệnh đã đóng, gồm 1 lệnh thắng và 0 lệnh thua."],
        "risk_patterns": ["Không phát hiện mẫu rủi ro lớn từ dữ liệu đã lưu."],
        "positive_behaviors": ["Không ghi nhận lệnh bị chặn trước khi vào lệnh trong ngày này."],
        "tomorrows_plan": ["Kiểm tra SL và rủi ro trước mỗi lệnh."],
    }


class FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": (
                                    '{"facts":["Có 1 lệnh đã đóng, gồm 1 lệnh thắng và 0 lệnh thua."],'
                                    '"observations":["Quan sát này được dữ liệu hỗ trợ."],'
                                    '"positive_behaviors":["Không ghi nhận lệnh bị chặn trước khi vào lệnh trong ngày này."],'
                                    '"next_session_recommendations":["Kiểm tra SL và rủi ro trước mỗi lệnh."],'
                                    '"disclaimer":"Chỉ là huấn luyện hành vi giao dịch; không phải lời khuyên tài chính."}'
                                )
                            }
                        ]
                    }
                }
            ]
        }


def test_gemini_provider_generates_narrative(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return FakeResponse()

    monkeypatch.setenv("ENABLE_AI", "true")
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    get_settings.cache_clear()
    monkeypatch.setattr(ai_review.httpx, "post", fake_post)

    narrative, metadata = ai_review.maybe_generate_ai_narrative(_metrics(), 100, [], _findings())

    assert metadata["ai_enabled"] is True
    assert metadata["provider"] == "gemini"
    assert metadata["model"] == "gemini-test-model"
    assert "Quan sát này được dữ liệu hỗ trợ." in narrative
    assert "Sự thật từ dữ liệu:" in narrative
    assert calls[0][0] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-test-model:generateContent"
    assert calls[0][1]["headers"] == {"x-goog-api-key": "test-gemini-key"}
    assert calls[0][1]["json"]["generationConfig"]["responseMimeType"] == "application/json"
    prompt = calls[0][1]["json"]["contents"][0]["parts"][0]["text"]
    assert "Write all user-facing strings in Vietnamese." in prompt


def test_gemini_provider_missing_key_uses_fallback(monkeypatch):
    monkeypatch.setenv("ENABLE_AI", "true")
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    get_settings.cache_clear()

    narrative, metadata = ai_review.maybe_generate_ai_narrative(_metrics(), 100, [], _findings())

    assert metadata["ai_enabled"] is False
    assert metadata["provider"] == "gemini"
    assert metadata["fallback_reason"] == "GEMINI_API_KEY missing"
    assert "Sự thật từ dữ liệu:" in narrative
