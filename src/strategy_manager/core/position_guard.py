"""Position guard helpers for the strategy-manager API.

The live shell owns execution; this module only mirrors its rules so callers
can answer "how many shares does this strategy manage right now?" without
starting a worker.

Keep :func:`compute_sleeve` and :func:`resolve_managed_position` in lockstep
with ``vnpy-live-trading/scripts/single_stream_base_engine.py``::

    if not single_position and not scoped and not sync_pos:
        return                      # core owns its own state file
    if sync_pos:
        core.sync_position(qty)     # whole broker position
    if core_shares > 0:
        managed = max(0, qty - core_shares)
        if cap > 0: managed = min(managed, cap)
    elif scoped:
        managed = min(qty, cap)
    else:
        managed = qty
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from strategy_cores.registry import get_core_class


CN_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_STATE_DIR = Path("/app/vnpy-live-trading/scripts/state")
DEFAULT_STATE_PREFIX = "single_stream"

ACTIVE_SIGNAL_STATUSES = (
    "pending",
    "retry_pending",
    "submitted",
    "partial_filled",
    "cancel_requested",
)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def compute_sleeve(qty: int, managed_shares: int, core_shares: int) -> Tuple[int, int]:
    """Split an account position into ``(managed, core)`` exactly as the shell."""
    qty = max(0, _int(qty))
    cap = max(0, _int(managed_shares))
    core_floor = max(0, _int(core_shares))

    if core_floor > 0:
        managed = max(0, qty - core_floor)
        if cap > 0:
            managed = min(managed, cap)
        return managed, qty - managed

    if cap > 0:
        managed = min(qty, cap)
        return managed, qty - managed

    return qty, 0


def strategy_capabilities(strategy_key: str) -> Dict[str, Any]:
    """Return the core capability flags the shell uses to locate a position."""
    try:
        core_cls = get_core_class(strategy_key)
    except KeyError:
        return {
            "known": False,
            "name": strategy_key,
            "single_position": False,
            "sync_position": False,
        }

    meta = getattr(core_cls, "meta", None)
    return {
        "known": True,
        "name": getattr(meta, "name", strategy_key) or strategy_key,
        "single_position": bool(getattr(meta, "single_position", False)),
        "sync_position": hasattr(core_cls, "sync_position"),
    }


def resolve_managed_position(
    *,
    capabilities: Dict[str, Any],
    broker_qty: int,
    managed_shares: int,
    core_shares: int,
    state_pos: Optional[int],
) -> Dict[str, Any]:
    """Locate the shares this strategy manages.

    ``state_file_missing`` is deliberately treated as zero managed shares:
    a non-single-position core that has no state does not adopt the broker
    position, so stopping it cannot orphan shares it never claimed.
    """
    if not capabilities.get("known"):
        return {"source": "unknown", "managed_qty": None, "core_qty": None}

    if capabilities.get("sync_position"):
        return {
            "source": "broker_sync_position",
            "managed_qty": max(0, _int(broker_qty)),
            "core_qty": 0,
        }

    if _int(managed_shares) > 0 or _int(core_shares) > 0:
        managed, core = compute_sleeve(broker_qty, managed_shares, core_shares)
        return {"source": "broker_sleeve", "managed_qty": managed, "core_qty": core}

    if capabilities.get("single_position"):
        return {
            "source": "broker_position",
            "managed_qty": max(0, _int(broker_qty)),
            "core_qty": 0,
        }

    if state_pos is not None:
        return {
            "source": "state_file",
            "managed_qty": max(0, _int(state_pos)),
            "core_qty": None,
        }

    return {"source": "state_file_missing", "managed_qty": 0, "core_qty": None}


def read_state(
    state_dir: Path,
    symbol: str,
    state_prefix: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Read the live shell's state JSON for ``symbol`` (None when absent)."""
    safe_symbol = str(symbol or "").replace(".", "_")
    safe_prefix = str(state_prefix or DEFAULT_STATE_PREFIX).replace(" ", "_")
    path = Path(state_dir) / f"{safe_prefix}_state_{safe_symbol}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def read_state_pos(state_dir: Path, symbol: str, state_prefix: Optional[str]) -> Optional[int]:
    data = read_state(state_dir, symbol, state_prefix)
    if data is None:
        return None
    try:
        return int(data.get("pos") or 0)
    except (TypeError, ValueError):
        return None


def build_reset_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Zero the position fields of a state file, preserving replay guards.

    ``last_daily_signal_date`` / ``last_daily_date`` must survive: hidden_dragon
    replays its latest daily entry when the state has no record of having
    processed it. Turtle-specific unit bookkeeping is cleared so a fresh entry
    cannot inherit stale add counts.
    """
    data = dict(state)
    data["pos"] = 0
    data["entry_price"] = 0.0
    data["entry_date"] = None
    data["highest_since_entry"] = 0.0
    data["lowest_since_entry"] = 0.0
    for key in ("unit_size", "units_added"):
        if key in data:
            data[key] = 0
    for key in ("initial_entry_price", "last_add_price", "stop_price", "trailing_stop"):
        if key in data:
            data[key] = None
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    return data


def write_state(
    state_dir: Path,
    symbol: str,
    state_prefix: Optional[str],
    data: Dict[str, Any],
) -> Path:
    """Atomically write the live shell's state JSON."""
    safe_symbol = str(symbol or "").replace(".", "_")
    safe_prefix = str(state_prefix or DEFAULT_STATE_PREFIX).replace(" ", "_")
    path = Path(state_dir) / f"{safe_prefix}_state_{safe_symbol}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def resolve_account(
    db: Any,
    user_id: str,
    config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Resolve the config's securities account, mirroring the orchestrator.

    Explicit binding wins. A config without one falls back to the user's only
    account; zero or several accounts leave it unbound (signal-only worker).
    """
    params = config.get("params") or {}
    explicit = config.get("securities_account_id") or params.get("securities_account_id")
    if explicit:
        candidates: list[Any] = [str(explicit)]
        try:
            from bson import ObjectId

            candidates.insert(0, ObjectId(str(explicit)))
        except Exception:  # noqa: BLE001 - str form is still tried
            pass
        for query_id in candidates:
            doc = db["securities_accounts"].find_one({"_id": query_id, "user_id": user_id})
            if doc:
                return doc
        return None

    accounts = list(db["securities_accounts"].find({"user_id": user_id}))
    if len(accounts) == 1:
        return accounts[0]
    return None


def summarize_pending_signals(
    db: Any,
    user_id: str,
    account_id: Optional[str],
    symbol: str,
) -> Dict[str, Dict[str, Any]]:
    """Count live BUY/SELL signals still able to reach the broker."""
    query: Dict[str, Any] = {
        "user_id": user_id,
        "symbol": symbol,
        "mode": "live",
        "status": {"$in": list(ACTIVE_SIGNAL_STATUSES)},
        "action": {"$in": ["buy", "BUY", "sell", "SELL"]},
    }
    if account_id:
        query["securities_account_id"] = account_id

    result: Dict[str, Dict[str, Any]] = {
        "buy": {"count": 0, "qty": 0, "order_ids": []},
        "sell": {"count": 0, "qty": 0, "order_ids": []},
    }
    for row in db["trade_signals"].find(query):
        action = str(row.get("action") or "").lower()
        if action not in result:
            continue
        size = max(0, _int(row.get("size")))
        result[action]["count"] += 1
        result[action]["qty"] += size
        order_id = row.get("order_id")
        if order_id:
            result[action]["order_ids"].append(str(order_id))
    return result


def _next_open(local: datetime) -> datetime:
    """Next CN_A session open. Weekends only; no holiday calendar here."""
    if local.weekday() < 5 and local.time() < time(9, 25):
        return datetime.combine(local.date(), time(9, 25), tzinfo=CN_TZ)
    if local.weekday() < 5 and time(11, 30) < local.time() < time(13, 0):
        return datetime.combine(local.date(), time(13, 0), tzinfo=CN_TZ)

    day: date = local.date()
    while True:
        day = day + timedelta(days=1)
        if day.weekday() < 5:
            break
    return datetime.combine(day, time(9, 25), tzinfo=CN_TZ)


def market_session(now: Optional[datetime] = None) -> Dict[str, Any]:
    """CN_A session snapshot for the disable dialog."""
    local = (now or datetime.now(timezone.utc)).astimezone(CN_TZ)
    windows = ((time(9, 25), time(11, 30)), (time(13, 0), time(15, 0)))
    is_open = local.weekday() < 5 and any(start <= local.time() <= end for start, end in windows)
    return {
        "is_open": is_open,
        "now": local.isoformat(),
        "next_open_at": None if is_open else _next_open(local).isoformat(),
    }
