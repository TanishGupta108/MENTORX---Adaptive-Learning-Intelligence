"""The OpenRouter client: key clean-up, rejected keys, fallbacks, the time budget and the
reasoning retry. Everything runs against httpx.MockTransport and a fake clock, never the
real API."""

from __future__ import annotations

import json

import httpx
import pytest

from app.core.config import Settings, get_settings
from app.tutor import llm
from tests.conftest import auth, register

MSG = [{"role": "user", "content": "hi"}]


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def fake(monkeypatch):
    """Install a mock transport. `fake.replies` is a list of (status, body) or callables."""
    clock = FakeClock()
    calls: list[dict] = []

    class Fake:
        replies: list = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append({"body": body, "timeout": request.extensions.get("timeout", {})})
        reply = Fake.replies.pop(0) if Fake.replies else (429, {"error": "busy"})
        if callable(reply):
            reply = reply(body)
        status, payload = reply
        return httpx.Response(status, json=payload)

    monkeypatch.setattr(llm, "_clock", clock)
    monkeypatch.setattr(llm, "_transport", httpx.MockTransport(handler))
    llm.reset_state()
    Fake.calls, Fake.clock = calls, clock
    yield Fake
    llm.reset_state()


def ok(text="Think about sharing equally between the groups."):
    return (200, {"choices": [{"message": {"content": text}}]})


@pytest.mark.parametrize(
    "raw",
    ['"sk-or-abc"', "'sk-or-abc'", "  sk-or-abc  ", "Bearer sk-or-abc", '" Bearer sk-or-abc "'],
)
def test_api_key_is_cleaned(raw):
    assert Settings(openrouter_api_key=raw).openrouter_api_key == "sk-or-abc"


def test_default_chain_starts_with_nemotron():
    models = Settings(ai_model=Settings.model_fields["ai_model"].default).ai_models
    assert models[0] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert models[-1] == "openrouter/free" and not any("ernie" in m for m in models)


def test_rejected_key_stops_at_once_and_is_remembered(fake):
    fake.replies = [(401, {"error": {"message": "User not found."}})]
    with pytest.raises(llm.AIKeyRejected):
        llm.complete(MSG)
    assert len(fake.calls) == 1  # no other model tried
    assert llm.key_ok() is False
    with pytest.raises(llm.AIKeyRejected):  # still rejected: no new call
        llm.complete(MSG)
    assert len(fake.calls) == 1
    fake.clock.t += llm.KEY_REJECT_SECONDS + 1  # the flag clears after 10 minutes
    assert llm.key_ok() is None


def test_busy_model_falls_back_and_the_good_one_is_tried_first(fake):
    models = get_settings().ai_models
    fake.replies = [(429, {"error": "rate limited"}), ok()]
    text, _, model = llm.complete(MSG)
    assert model == models[1] and "sharing" in text and llm.key_ok() is True
    assert [c["body"]["model"] for c in fake.calls] == models[:2]
    fake.replies = [ok()]
    llm.complete(MSG)
    assert fake.calls[-1]["body"]["model"] == models[1]  # cached last good model


def test_other_4xx_also_falls_back(fake):
    fake.replies = [(400, {"error": "bad model"}), ok()]
    assert llm.complete(MSG)[2] == get_settings().ai_models[1]


def test_reasoning_is_low_and_retried_without_when_rejected(fake):
    fake.replies = [
        lambda body: (
            (400, {"error": "reasoning is not supported"}) if "reasoning" in body else ok()
        ),
        ok(),
    ]
    llm.complete(MSG, 600)
    first, second = fake.calls
    assert first["body"]["reasoning"] == {"effort": "low", "exclude": True}
    assert first["body"]["max_tokens"] == 600
    assert "reasoning" not in second["body"] and second["body"]["model"] == first["body"]["model"]


def test_total_deadline_is_respected(fake):
    def slow(body):
        fake.clock.t += 30  # every attempt takes 30 s and fails
        return (429, {"error": "busy"})

    fake.replies = [slow] * 10
    start = fake.clock.t
    with pytest.raises(llm.AIUnavailable, match="busy"):
        llm.complete(MSG)
    assert len(fake.calls) == 2  # 0-30 s, 30-60 s; no third start with < 5 s left
    assert all(c["timeout"]["read"] <= llm.MAX_READ_SECONDS for c in fake.calls)
    assert fake.calls[1]["timeout"]["read"] <= get_settings().ai_total_seconds - 30
    assert fake.clock.t - start <= 60


def test_too_short_answers_move_on(fake):
    fake.replies = [ok("OK"), ok()]
    assert llm.complete(MSG)[2] == get_settings().ai_models[1]


def test_status_and_admin_test_endpoint(client, fake, db):
    from app.db.models import User

    fake.replies = [(401, {"error": "No auth credentials found"})]
    h = auth(register(client))
    r = client.post("/api/v2/admin/ai/test", headers=h)
    assert r.status_code == 403
    db.query(User).update({"role": "admin"})
    db.commit()
    r = client.post("/api/v2/admin/ai/test", headers=h).json()
    assert not r["ok"] and r["error_code"] == "ai_key_rejected" and "test-key" not in str(r)
    st = client.get("/api/v2/ai/status", headers=h).json()
    assert st["key_ok"] is False and st["enabled"] is False
    fake.replies = [ok("OK")]
    r = client.post("/api/v2/admin/ai/test", headers=h).json()
    assert r["ok"] and r["model"] and r["latency_ms"] is not None
    st = client.get("/api/v2/ai/status", headers=h).json()
    assert st["key_ok"] is True and st["enabled"] is True
