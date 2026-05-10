from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


_TEST_DIR = Path(__file__).resolve().parent
_CONTROL_API_DIR = _TEST_DIR.parent
if str(_CONTROL_API_DIR) not in sys.path:
    sys.path.insert(0, str(_CONTROL_API_DIR))

from app.replay_prepare_policy import ReplayPreparePolicy  # noqa: E402


def _getenv(values: dict[str, str]):
    def _inner(key: str, default: Optional[str] = None) -> Optional[str]:
        return values.get(key, default)

    return _inner


def test_prepare_policy_clamps_env_limits() -> None:
    policy = ReplayPreparePolicy.from_env(
        _getenv({
            "OPENCLAW_REPLAY_QUICK_MAX_BARS": "999999",
            "OPENCLAW_REPLAY_FULL_CHAIN_MAX_EVENTS": "not-an-int",
            "OPENCLAW_REPLAY_FULL_CHAIN_MAX_BARS_PER_SYMBOL": "10",
            "OPENCLAW_REPLAY_FULL_CHAIN_FETCH_CONCURRENCY": "99",
        })
    )

    assert policy.quick_max_bars == 20_000
    assert policy.full_chain_max_events == 100_000
    assert policy.full_chain_max_bars_per_symbol == 200
    assert policy.full_chain_fetch_concurrency == 5


def test_prepare_policy_blocks_live_profile_bulk_public_fetch_by_default() -> None:
    policy = ReplayPreparePolicy.from_env(
        _getenv({
            "OPENCLAW_REPLAY_PREPARE_ENABLED": "1",
            "OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP": "0",
        })
    )

    rejection = policy.validate_full_chain_bulk_prod_ip(is_live_release_profile=True)

    assert rejection is not None
    assert rejection.status_code == 403
    assert rejection.reason_code == "replay_full_chain_prod_ip_blocked"


def test_prepare_policy_accepts_bulk_public_fetch_when_override_is_explicit() -> None:
    policy = ReplayPreparePolicy.from_env(
        _getenv({
            "OPENCLAW_REPLAY_PREPARE_ENABLED": "1",
            "OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP": "1",
        })
    )

    assert policy.validate_full_chain_bulk_prod_ip(is_live_release_profile=True) is None


def test_prepare_policy_returns_stable_window_rejections() -> None:
    policy = ReplayPreparePolicy(
        quick_max_bars=10,
        full_chain_max_events=20,
        full_chain_prepare_enabled=False,
        full_chain_bulk_prod_ip_allowed=False,
        full_chain_max_bars_per_symbol=5,
        full_chain_fetch_concurrency=1,
    )

    quick = policy.validate_quick_window(estimated_bars=11)
    enabled = policy.validate_full_chain_prepare_enabled()
    per_symbol = policy.validate_full_chain_bars_per_symbol(
        estimated_bars_per_symbol=6,
    )
    events = policy.validate_full_chain_event_window(
        estimated_events=21,
        symbol_count=2,
    )

    assert quick is not None
    assert quick.reason_code == "replay_quick_window_too_large"
    assert enabled is not None
    assert enabled.reason_code == "replay_full_chain_prepare_disabled"
    assert per_symbol is not None
    assert per_symbol.reason_code == "replay_full_chain_window_too_large_per_symbol"
    assert events is not None
    assert events.reason_code == "replay_full_chain_window_too_large"

