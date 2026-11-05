from app.bots.base import BotContext, BotResult, BrowserBot, RunOutcome
from app.bots.registry import BotRegistry


class DummyBot(BrowserBot):
    id = "dummy"
    name = "Dummy"
    description = "test"
    engine = "test"

    def run(self, context: BotContext) -> BotResult:
        return BotResult(outcome=RunOutcome.SUCCESS, message="ok")


def test_register_and_list():
    registry = BotRegistry()
    registry.register(DummyBot())
    assert registry.get("dummy") is not None
    assert len(registry.list()) == 1
    assert registry.require("dummy").name == "Dummy"


def test_duplicate_registration_rejected():
    registry = BotRegistry()
    registry.register(DummyBot())
    try:
        registry.register(DummyBot())
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "already registered" in str(exc)
