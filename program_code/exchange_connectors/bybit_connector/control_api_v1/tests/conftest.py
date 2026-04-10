"""
Shared test fixtures and utilities for all tests / 所有测试共享的夹具和工具
共享测试夹具

This module provides reusable fixtures across all test files to:
  - Reduce code duplication
  - Ensure consistent setup/teardown
  - Provide common mock objects and temporary resources
  - Support common testing patterns (state machines, temp files, callbacks)
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest


# ═══════════════════════════════════════════════════════════════════════════════
# PATH SETUP / 路径设置
# ═══════════════════════════════════════════════════════════════════════════════

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPORARY FILE & DIRECTORY FIXTURES / 临时文件和目录夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_state_file():
    """
    Create a temp file path for paper trading state storage.
    Ensures cleanup after test.
    纸上交易状态存储的临时文件路径，测试后清理。
    """
    fd, path = tempfile.mkstemp(suffix=".json", prefix="test_state_")
    os.close(fd)
    os.unlink(path)  # Let the service create it
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def tmp_audit_dir():
    """
    Create a temp directory for audit files.
    Automatically cleaned up after test.
    审计文件的临时目录，测试后自动清理。
    """
    with tempfile.TemporaryDirectory(prefix="audit_test_") as d:
        yield d


@pytest.fixture
def tmp_cost_file():
    """
    Create a temp file path for cost/fee data.
    Ensures cleanup after test.
    成本/费用数据的临时文件路径。
    """
    fd, path = tempfile.mkstemp(suffix=".json", prefix="test_cost_")
    os.close(fd)
    os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


# ARCH-RC1 1C-3-F: PAPER TRADING ENGINE FIXTURES retired together with
# paper_trading_engine.py. Rust engine owns paper-side execution; the few tests
# that needed these fixtures were deleted in the same patch.
# ARCH-RC1 1C-3-F：紙盤引擎 fixtures 隨 paper_trading_engine.py 一同退場。

# ═══════════════════════════════════════════════════════════════════════════════
# STATE MACHINE FIXTURES / 状态机夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def auth_state_machine():
    """
    Create a fresh AuthorizationStateMachine instance.
    全新授权状态机实例。
    """
    from app.authorization_state_machine import AuthorizationStateMachine  # TODO R-06: replace with IPC mock
    return AuthorizationStateMachine()


@pytest.fixture
def auth_sm_with_audit():
    """
    Create an AuthorizationStateMachine with audit callback tracking.
    带审计回调的授权状态机。
    Returns: (machine, records_list)
    """
    from app.authorization_state_machine import AuthorizationStateMachine  # TODO R-06: replace with IPC mock

    records = []
    machine = AuthorizationStateMachine(audit_callback=lambda r: records.append(r))
    return machine, records



@pytest.fixture
def decision_lease_state_machine():
    """
    Create a fresh DecisionLeaseStateMachine instance.
    全新决策租赁状态机实例。
    """
    from app.decision_lease_state_machine import DecisionLeaseStateMachine  # TODO R-06: replace with IPC mock
    return DecisionLeaseStateMachine()


@pytest.fixture
def decision_lease_sm_with_audit():
    """
    Create a DecisionLeaseStateMachine with audit callback tracking.
    带审计回调的决策租赁状态机。
    Returns: (machine, records_list)
    """
    from app.decision_lease_state_machine import DecisionLeaseStateMachine  # TODO R-06: replace with IPC mock

    records = []
    machine = DecisionLeaseStateMachine(audit_callback=lambda r: records.append(r))
    return machine, records


@pytest.fixture
def risk_governor_state_machine():
    """
    Create a fresh RiskGovernorStateMachine instance.
    全新风控治理状态机实例。
    """
    from app.risk_governor_state_machine import RiskGovernorStateMachine  # TODO R-06: replace with IPC mock
    return RiskGovernorStateMachine()


@pytest.fixture
def risk_governor_sm_with_audit():
    """
    Create a RiskGovernorStateMachine with audit callback tracking.
    带审计回调的风控治理状态机。
    Returns: (machine, records_list)
    """
    from app.risk_governor_state_machine import RiskGovernorStateMachine  # TODO R-06: replace with IPC mock

    records = []
    machine = RiskGovernorStateMachine(audit_callback=lambda r: records.append(r))
    return machine, records


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIT & LOGGING FIXTURES / 审计和日志夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def change_audit_log():
    """
    Create a fresh ChangeAuditLog instance.
    全新变更审计日志实例。
    """
    from app.change_audit_log import ChangeAuditLog
    return ChangeAuditLog()


@pytest.fixture
def change_audit_log_with_callback():
    """
    Create a ChangeAuditLog with callback tracking.
    带回调追踪的变更审计日志。
    Returns: (log, callbacks_list)
    """
    from app.change_audit_log import ChangeAuditLog

    callbacks = []
    log = ChangeAuditLog(audit_callback=lambda r: callbacks.append(r))
    return log, callbacks


@pytest.fixture
def audit_file_writer(tmp_audit_dir):
    """
    Create an AuditFileWriter instance for temp directory.
    临时目录的审计文件写入器。
    """
    from app.audit_persistence import AuditFileWriter, AuditPersistenceConfig

    config = AuditPersistenceConfig(
        base_dir=tmp_audit_dir,
        flush_after_write=True,
    )
    w = AuditFileWriter(config)
    yield w
    w.close()


@pytest.fixture
def audit_file_reader(tmp_audit_dir):
    """
    Create an AuditFileReader instance for temp directory.
    临时目录的审计文件读取器。
    """
    from app.audit_persistence import AuditFileReader
    return AuditFileReader(base_dir=tmp_audit_dir)


@pytest.fixture
def audit_pipeline(tmp_audit_dir):
    """
    Create an AuditPipeline instance for temp directory.
    临时目录的审计管道。
    """
    from app.audit_persistence import AuditPipeline, AuditPersistenceConfig

    config = AuditPersistenceConfig(base_dir=tmp_audit_dir, flush_after_write=True)
    p = AuditPipeline(config)
    yield p
    p.close()


# ARCH-RC1 1C-3-D: risk_manager / global_risk_config / category_risk_config
# fixtures removed — Python RiskManager now a thin shim over RiskViewClient,
# all risk logic owned by Rust ConfigStore + intent_processor.

# ═══════════════════════════════════════════════════════════════════════════════
# MARKET DATA FIXTURES / 行情数据夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def bybit_ws_listener():
    """
    Create a BybitPublicWsListener instance.
    Bybit 公共 WS 监听器实例。
    """
    from app.bybit_public_ws_listener import BybitPublicWsListener
    return BybitPublicWsListener()


@pytest.fixture
def sample_price_event():
    """
    Create a sample PriceEvent for testing.
    用于测试的示例价格事件。
    """
    from app.shared_types import PriceEvent
    return PriceEvent(
        symbol="BTCUSDT",
        last_price=87000.0,
        mark_price=86950.0,
        best_bid=86900.0,
        best_ask=87100.0,
        volume_24h=100000.0,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS / 实用函数
# ═══════════════════════════════════════════════════════════════════════════════

def _sample_audit_record(event: str = "test_event") -> dict:
    """
    Create a sample audit record for testing.
    用于测试的示例审计记录。
    """
    return {
        "transition_id": f"tx:{os.urandom(6).hex()}",
        "trigger_event": event,
        "previous_status": "STATE_A",
        "next_status": "STATE_B",
        "initiated_by": "TestSuite",
        "effective_at_ms": int(time.time() * 1000),
    }


def _create_draft_auth(sm, title: str = "Test Auth") -> Any:
    """
    Helper: create a DRAFT authorization.
    辅助函数：创建 DRAFT 授权。
    """
    from app.authorization_state_machine import AuthorizationStateMachine  # TODO R-06: replace with IPC mock

    if not isinstance(sm, AuthorizationStateMachine):
        raise TypeError("sm must be an AuthorizationStateMachine instance")

    return sm.create_draft(
        title=title,
        scope={"categories": ["linear"], "symbols": ["BTCUSDT"], "mode": "paper_only"},
        created_by="test_operator",
        description="Test authorization for unit tests",
        expires_at_ms=int(time.time() * 1000) + 3600_000,  # 1 hour from now
    )


def _activate_auth(sm, draft_auth) -> Any:
    """
    Helper: promote a DRAFT authorization to ACTIVE (draft → pending → active).
    辅助函数：将 DRAFT 授权提升为 ACTIVE。
    """
    from app.authorization_state_machine import AuthorizationStateMachine  # TODO R-06: replace with IPC mock

    if not isinstance(sm, AuthorizationStateMachine):
        raise TypeError("sm must be an AuthorizationStateMachine instance")

    sm.submit_for_approval(draft_auth.authorization_id)
    return sm.approve(
        draft_auth.authorization_id,
        approved_by="operator_1",
        reason="approved for testing"
    )


def _make_active(sm) -> Any:
    """
    Helper: create and activate an authorization in one call.
    辅助函数：一次调用创建并激活授权。
    """
    from app.authorization_state_machine import AuthorizationStateMachine  # TODO R-06: replace with IPC mock

    if not isinstance(sm, AuthorizationStateMachine):
        raise TypeError("sm must be an AuthorizationStateMachine instance")

    auth = sm.create_draft(
        title="Helper Auth",
        scope={"mode": "paper_only"},
        created_by="test",
    )
    sm.submit_for_approval(auth.authorization_id)
    sm.approve(auth.authorization_id, approved_by="operator_1")
    return sm.get(auth.authorization_id)


# _create_and_advance_oms_order removed 2026-04-10: Python OMS deprecated.
# Order lifecycle now tracked in Rust event_consumer → trading.orders + order_state_changes.


# ═══════════════════════════════════════════════════════════════════════════════
# IPC STATE READER FIXTURES / IPC 狀態讀取器夾具 (R06-D)
# ═══════════════════════════════════════════════════════════════════════════════

# Standard pipeline snapshot matching Rust PipelineSnapshot format
# 標準管線快照，匹配 Rust PipelineSnapshot 格式
SAMPLE_PIPELINE_SNAPSHOT = {
    "paper_state": {
        "balance": 9500.0,
        "peak_balance": 10000.0,
        "total_realized_pnl": -500.0,
        "total_fees": 12.5,
        "trade_count": 3,
        "positions": [
            {
                "symbol": "BTCUSDT",
                "is_long": True,
                "qty": 0.01,
                "entry_price": 65000.0,
                "best_price": 66000.0,
                "entry_fee": 3.25,
                "entry_ts_ms": 1700000000000,
                "unrealized_pnl": 10.0,
            }
        ],
    },
    "latest_prices": {"BTCUSDT": 66000.0, "ETHUSDT": 3200.0},
    "stats": {
        "total_ticks": 5000,
        "total_intents": 15,
        "total_fills": 3,
        "total_stops": 1,
        "last_tick_ms": 1700000050000,
    },
    "source": "rust_engine",
}


@pytest.fixture
def rust_snapshot_dir():
    """
    Create a temp dir with a valid pipeline_snapshot.json.
    創建帶有有效 pipeline_snapshot.json 的臨時目錄。
    """
    with tempfile.TemporaryDirectory(prefix="rust_snap_") as d:
        path = os.path.join(d, "pipeline_snapshot.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(SAMPLE_PIPELINE_SNAPSHOT, f)
        yield d


@pytest.fixture
def rust_reader_available(rust_snapshot_dir):
    """
    Provide a RustSnapshotReader pointing at a valid snapshot file.
    提供指向有效快照文件的 RustSnapshotReader。
    """
    from app.ipc_state_reader import RustSnapshotReader
    return RustSnapshotReader(data_dir=rust_snapshot_dir)


@pytest.fixture
def rust_reader_unavailable():
    """
    Provide a RustSnapshotReader with no snapshot (simulates Rust engine down).
    提供無快照的 RustSnapshotReader（模擬 Rust 引擎停止）。
    """
    with tempfile.TemporaryDirectory(prefix="rust_empty_") as d:
        from app.ipc_state_reader import RustSnapshotReader
        yield RustSnapshotReader(data_dir=d)


@pytest.fixture
def patch_rust_reader_available(rust_reader_available, monkeypatch):
    """
    Monkeypatch the ipc_state_reader singleton to a reader with valid data.
    Monkeypatch ipc_state_reader 單例為帶有效數據的讀取器。
    Use this in route-level tests to simulate Rust engine running.
    """
    import app.ipc_state_reader as mod
    monkeypatch.setattr(mod, "_READER", rust_reader_available)
    return rust_reader_available


@pytest.fixture
def patch_rust_reader_unavailable(rust_reader_unavailable, monkeypatch):
    """
    Monkeypatch the ipc_state_reader singleton to a reader with no data.
    Monkeypatch ipc_state_reader 單例為無數據的讀取器。
    Use this in route-level tests to simulate Rust engine NOT running (fallback path).
    """
    import app.ipc_state_reader as mod
    monkeypatch.setattr(mod, "_READER", rust_reader_unavailable)
    return rust_reader_unavailable


# ═══════════════════════════════════════════════════════════════════════════════
# MODULE-LEVEL EXPORTS / 模块级导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Fixtures
    "tmp_state_file",
    "tmp_audit_dir",
    "tmp_cost_file",
    "paper_state_store",
    "paper_engine",
    "active_paper_engine",
    "paper_engine_with_risk",
    "dispatcher_with_engine",
    "auth_state_machine",
    "auth_sm_with_audit",
"decision_lease_state_machine",
    "decision_lease_sm_with_audit",
    "risk_governor_state_machine",
    "risk_governor_sm_with_audit",
    "change_audit_log",
    "change_audit_log_with_callback",
    "audit_file_writer",
    "audit_file_reader",
    "audit_pipeline",
    "risk_manager",
    "global_risk_config",
    "category_risk_config",
    "bybit_ws_listener",
    "sample_price_event",
    # IPC fixtures (R06-D)
    "rust_snapshot_dir",
    "rust_reader_available",
    "rust_reader_unavailable",
    "patch_rust_reader_available",
    "patch_rust_reader_unavailable",
    # Helpers
    "_sample_audit_record",
    "_create_draft_auth",
    "_activate_auth",
    "_make_active",
    "_create_and_advance_oms_order",
]
