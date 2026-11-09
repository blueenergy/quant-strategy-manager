"""Tests for the position-guard helpers used by the disable flow.

Run with ``pytest test_*.py`` (strategy-cores must be importable, as in CI).
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from strategy_manager.core.position_guard import (  # noqa: E402
    build_reset_state,
    compute_sleeve,
    market_session,
    read_state,
    read_state_pos,
    resolve_account,
    resolve_managed_position,
    strategy_capabilities,
    summarize_pending_signals,
    write_state,
)


def test_compute_sleeve_whole_account():
    assert compute_sleeve(1000, 0, 0) == (1000, 0)


def test_compute_sleeve_core_floor_and_cap():
    # 600002: 10,000 shares, strategy manages 2,000, personal core 8,000.
    assert compute_sleeve(10000, 2000, 8000) == (2000, 8000)


def test_compute_sleeve_below_core_floor():
    assert compute_sleeve(3000, 2000, 8000) == (0, 3000)


def test_compute_sleeve_cap_only():
    assert compute_sleeve(15000, 2000, 0) == (2000, 13000)


def test_compute_sleeve_zero_position():
    assert compute_sleeve(0, 2000, 8000) == (0, 0)


def test_capabilities_hidden_dragon_owns_state_file():
    caps = strategy_capabilities("hidden_dragon")
    assert caps["known"] is True
    assert caps["single_position"] is False
    assert caps["sync_position"] is False


def test_capabilities_daily_sma_cross_is_single_position():
    caps = strategy_capabilities("daily_sma_cross")
    assert caps["single_position"] is True


def test_capabilities_grid_syncs_broker_position():
    caps = strategy_capabilities("grid")
    assert caps["sync_position"] is True


def test_capabilities_unknown_key():
    caps = strategy_capabilities("does_not_exist")
    assert caps["known"] is False


def test_resolve_managed_position_uses_state_file():
    caps = strategy_capabilities("hidden_dragon")
    result = resolve_managed_position(
        capabilities=caps,
        broker_qty=1000,
        managed_shares=0,
        core_shares=0,
        state_pos=1000,
    )
    assert result == {"source": "state_file", "managed_qty": 1000, "core_qty": None}


def test_resolve_managed_position_state_file_missing_is_zero():
    caps = strategy_capabilities("hidden_dragon")
    result = resolve_managed_position(
        capabilities=caps,
        broker_qty=1000,
        managed_shares=0,
        core_shares=0,
        state_pos=None,
    )
    assert result == {"source": "state_file_missing", "managed_qty": 0, "core_qty": None}


def test_resolve_managed_position_sleeve():
    caps = strategy_capabilities("daily_sma_cross")
    result = resolve_managed_position(
        capabilities=caps,
        broker_qty=10000,
        managed_shares=2000,
        core_shares=8000,
        state_pos=2000,
    )
    assert result == {"source": "broker_sleeve", "managed_qty": 2000, "core_qty": 8000}


def test_resolve_managed_position_sync_position_uses_whole_account():
    caps = strategy_capabilities("grid")
    result = resolve_managed_position(
        capabilities=caps,
        broker_qty=10000,
        managed_shares=0,
        core_shares=0,
        state_pos=0,
    )
    assert result == {"source": "broker_sync_position", "managed_qty": 10000, "core_qty": 0}


def test_resolve_managed_position_unknown_key():
    caps = strategy_capabilities("does_not_exist")
    result = resolve_managed_position(
        capabilities=caps,
        broker_qty=100,
        managed_shares=0,
        core_shares=0,
        state_pos=None,
    )
    assert result == {"source": "unknown", "managed_qty": None, "core_qty": None}


def test_read_state_and_pos(tmp_path):
    path = tmp_path / "single_stream_state_600000_SH.json"
    path.write_text(
        json.dumps({"symbol": "600000.SH", "pos": 1000, "entry_price": 9.5}),
        encoding="utf-8",
    )
    data = read_state(tmp_path, "600000.SH", "single_stream")
    assert data["pos"] == 1000
    assert read_state_pos(tmp_path, "600000.SH", "single_stream") == 1000
    assert read_state_pos(tmp_path, "600000.SH", "daily_single_stream") is None


def test_build_reset_state_preserves_hidden_dragon_replay_guard():
    state = {
        "symbol": "600000.SH",
        "pos": 1000,
        "entry_price": 9.5,
        "entry_date": "20260101",
        "highest_since_entry": 10.5,
        "lowest_since_entry": 9.0,
        "last_daily_signal_date": "20260101",
        "updated_at": "2026-11-06T00:00:00",
    }
    reset = build_reset_state(state)
    assert reset["pos"] == 0
    assert reset["entry_price"] == 0.0
    assert reset["entry_date"] is None
    assert reset["highest_since_entry"] == 0.0
    assert reset["lowest_since_entry"] == 0.0
    # Must survive, or the core replays the 20260101 entry on the next start.
    assert reset["last_daily_signal_date"] == "20260101"


def test_build_reset_state_clears_turtle_units_but_keeps_cash():
    state = {
        "symbol": "600003.SH",
        "pos": 300,
        "entry_price": 20.0,
        "entry_date": "20260101",
        "unit_size": 300,
        "units_added": 1,
        "initial_entry_price": 20.0,
        "last_add_price": 20.0,
        "stop_price": 19.5,
        "trailing_stop": 19.5,
        "cash": 100000.0,
        "atr_value": 1.2,
        "prev_close": 20.0,
        "last_daily_date": "20260101",
    }
    reset = build_reset_state(state)
    assert reset["pos"] == 0
    assert reset["unit_size"] == 0
    assert reset["units_added"] == 0
    assert reset["stop_price"] is None
    assert reset["trailing_stop"] is None
    assert reset["cash"] == 100000.0
    assert reset["last_daily_date"] == "20260101"


def test_write_state_roundtrip(tmp_path):
    data = {"symbol": "600000.SH", "pos": 0, "entry_price": 0.0, "entry_date": None}
    path = write_state(tmp_path, "600000.SH", "single_stream", data)
    assert path.exists()
    assert read_state(tmp_path, "600000.SH", "single_stream") == data


class _Collection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    @staticmethod
    def _matches(doc, query):
        for key, expected in query.items():
            if isinstance(expected, dict):
                if "$in" in expected and doc.get(key) not in expected["$in"]:
                    return False
                if "$ne" in expected and doc.get(key) == expected["$ne"]:
                    return False
                continue
            if doc.get(key) != expected:
                return False
        return True

    def find(self, query):
        return [doc for doc in self.docs if self._matches(doc, query)]

    def find_one(self, query, sort=None):
        rows = self.find(query)
        return rows[0] if rows else None


def _db(accounts=None, positions=None, signals=None):
    return {
        "securities_accounts": _Collection(accounts or []),
        "trader_positions": _Collection(positions or []),
        "trade_signals": _Collection(signals or []),
    }


def test_resolve_account_explicit_binding():
    db = _db([
        {"_id": "acct-a", "user_id": "u1", "account_id": "A", "broker": "BrokerA"},
        {"_id": "acct-b", "user_id": "u1", "account_id": "B", "broker": "BrokerB"},
    ])
    config = {"securities_account_id": "acct-b", "params": {}}
    assert resolve_account(db, "u1", config)["account_id"] == "B"


def test_resolve_account_single_account_autobinds():
    db = _db([{"_id": "acct-a", "user_id": "u1", "account_id": "A", "broker": "BrokerA"}])
    assert resolve_account(db, "u1", {"params": {}})["account_id"] == "A"


def test_resolve_account_multiple_accounts_stays_unbound():
    db = _db([
        {"_id": "acct-a", "user_id": "u1", "account_id": "A"},
        {"_id": "acct-b", "user_id": "u1", "account_id": "B"},
    ])
    assert resolve_account(db, "u1", {"params": {}}) is None


def test_summarize_pending_signals_counts_both_action_cases():
    signals = [
        {"user_id": "u1", "symbol": "600000.SH", "mode": "live", "action": "BUY",
         "status": "pending", "size": 100, "order_id": "b1", "securities_account_id": "acct-a"},
        {"user_id": "u1", "symbol": "600000.SH", "mode": "live", "action": "sell",
         "status": "submitted", "size": 50, "order_id": "s1", "securities_account_id": "acct-a"},
        {"user_id": "u1", "symbol": "600000.SH", "mode": "live", "action": "sell",
         "status": "filled", "size": 50, "order_id": "s2", "securities_account_id": "acct-a"},
        {"user_id": "u1", "symbol": "000001.SZ", "mode": "live", "action": "buy",
         "status": "pending", "size": 10, "order_id": "b2", "securities_account_id": "acct-a"},
    ]
    result = summarize_pending_signals(_db(signals=signals), "u1", "acct-a", "600000.SH")
    assert result["buy"] == {"count": 1, "qty": 100, "order_ids": ["b1"]}
    assert result["sell"] == {"count": 1, "qty": 50, "order_ids": ["s1"]}


def _utc(hour, minute, day=9):
    return datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc)


def test_market_session_open_during_morning():
    # 2026-11-09 10:00 CST
    result = market_session(_utc(2, 0))
    assert result["is_open"] is True
    assert result["next_open_at"] is None


def test_market_session_after_close_waits_for_next_weekday():
    # 2026-11-09 15:12 CST -> 2026-11-10 09:25 CST
    result = market_session(_utc(7, 12))
    assert result["is_open"] is False
    assert result["next_open_at"] == "2026-11-10T09:25:00+08:00"


def test_market_session_friday_after_close_skips_weekend():
    # 2026-11-13 16:00 CST -> 2026-11-16 09:25 CST
    result = market_session(datetime(2026, 11, 13, 8, 0, tzinfo=timezone.utc))
    assert result["is_open"] is False
    assert result["next_open_at"] == "2026-11-16T09:25:00+08:00"


def test_market_session_saturday_waits_for_monday():
    result = market_session(datetime(2026, 11, 14, 2, 0, tzinfo=timezone.utc))
    assert result["is_open"] is False
    assert result["next_open_at"] == "2026-11-16T09:25:00+08:00"
