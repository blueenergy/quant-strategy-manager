import sys
from pathlib import Path

from bson import ObjectId

sys.path.insert(0, str(Path(__file__).parent / "src"))

from strategy_manager.core.multi_strategy_orchestrator import (  # noqa: E402
    MultiStrategyOrchestrator,
    StrategyConfig,
)


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    def find(self, query=None):
        return [doc for doc in self.docs if self._matches(doc, query or {})]

    def find_one(self, query=None):
        rows = self.find(query or {})
        return rows[0] if rows else None

    def _matches(self, doc, query):
        for key, expected in query.items():
            if doc.get(key) != expected:
                return False
        return True


class _Log:
    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass


def _orchestrator_with_accounts(accounts):
    orchestrator = MultiStrategyOrchestrator.__new__(MultiStrategyOrchestrator)
    orchestrator.db = {"securities_accounts": _Collection(accounts)}
    orchestrator.log = _Log()
    return orchestrator


def test_strategy_config_reads_explicit_securities_account_id():
    config = StrategyConfig.from_db_doc(
        {
            "symbol": "000001.SZ",
            "strategy_key": "demo",
            "user_id": "user-1",
            "params": {"securities_account_id": "acct-1"},
        }
    )

    assert config.securities_account_id == "acct-1"


def test_resolve_account_params_uses_selected_account():
    account_a = ObjectId()
    account_b = ObjectId()
    orchestrator = _orchestrator_with_accounts(
        [
            {"_id": account_a, "user_id": "user-1", "broker": "BrokerA", "account_id": "A"},
            {"_id": account_b, "user_id": "user-1", "broker": "BrokerB", "account_id": "B"},
        ]
    )

    params = orchestrator._resolve_account_params("user-1", str(account_b))

    assert params == {
        "securities_account_id": str(account_b),
        "broker": "BrokerB",
        "account_id": "B",
    }


def test_resolve_account_params_without_account_does_not_fallback():
    orchestrator = _orchestrator_with_accounts(
        [
            {"_id": ObjectId(), "user_id": "user-1", "broker": "BrokerA", "account_id": "A"},
        ]
    )

    assert orchestrator._resolve_account_params("user-1", None) == {}


def test_load_configurations_keys_include_account_id():
    orchestrator = MultiStrategyOrchestrator.__new__(MultiStrategyOrchestrator)
    orchestrator.log = _Log()
    orchestrator.user_id = None
    orchestrator.worker_factories = {"backtrader": object()}
    orchestrator.config_coll = _Collection(
        [
            {
                "symbol": "000001.SZ",
                "strategy_key": "demo",
                "user_id": "user-1",
                "securities_account_id": "acct-a",
                "enabled": True,
            },
            {
                "symbol": "000001.SZ",
                "strategy_key": "demo",
                "user_id": "user-1",
                "securities_account_id": "acct-b",
                "enabled": True,
            },
        ]
    )

    configs = orchestrator.load_configurations()

    assert set(configs) == {
        "user-1_acct-a_000001.SZ_demo",
        "user-1_acct-b_000001.SZ_demo",
    }
