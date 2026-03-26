"""
Tests for Observer → Runtime Snapshot Auto-Bridge
测试：Observer → Runtime Snapshot 自动桥接

覆盖范围 / Coverage:
  - Connection state extraction from observer data / 从 observer 数据提取连接状态
  - Freshness state determination / 数据新鲜度判断
  - Product family facts derivation / 产品族事实推导
  - Health telemetry computation / 健康遥测计算
  - Complete snapshot generation / 完整快照生成
  - Contract validation of generated output / 生成输出的合同验证
  - File I/O (write + permissions) / 文件读写与权限
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Add scripts directory to path for imports
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from scripts.auto_bridge_observer_to_runtime_snapshot import (
    STALENESS_THRESHOLD_MS,
    build_runtime_snapshot_from_observer,
    extract_completeness,
    extract_connection_states,
    extract_freshness_state,
    extract_health_telemetry,
    extract_product_family_facts,
    write_snapshot,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Test Data Fixtures / 测试数据
# ═══════════════════════════════════════════════════════════════════════════════

def _make_system_snapshot(*, all_ok: bool = True, account_type: str = "UNIFIED") -> dict:
    """Build a minimal system snapshot for testing / 构建最小化系统快照"""
    return {
        "snapshot_type": "bybit_system_snapshot",
        "ts_ms": int(time.time() * 1000),
        "sources": {
            "account": {"ok": all_ok, "payload_ts_ms": int(time.time() * 1000)},
            "positions": {"ok": all_ok, "payload_ts_ms": int(time.time() * 1000)},
            "order_history": {"ok": all_ok, "payload_ts_ms": int(time.time() * 1000)},
            "execution_history": {"ok": all_ok, "payload_ts_ms": int(time.time() * 1000)},
        },
        "payload": {
            "account": {
                "latency_ms": 200,
                "response": {
                    "result": {
                        "list": [{"accountType": account_type, "totalEquity": "610.01"}]
                    }
                },
            },
            "positions": {"latency_ms": 180},
            "order_history": {"latency_ms": 210},
        },
    }


def _make_ws_facts(*, connected: bool = True) -> dict:
    return {
        "facts_type": "bybit_ws_runtime_facts",
        "ts_ms": int(time.time() * 1000),
        "connection_state": "connected" if connected else "disconnected",
        "listener_health": "idle_but_connected" if connected else "disconnected",
        "running": connected,
    }


def _make_verdict(*, fresh: bool = True) -> dict:
    now = int(time.time() * 1000)
    ts = now if fresh else now - STALENESS_THRESHOLD_MS - 10_000
    return {
        "verdict_type": "bybit_observer_verdict",
        "verdict_generated_ts_ms": ts,
        "verdict_code": "OBSERVE_ONLY",
        "execution_allowed": False,
        "freshness": {
            "snapshot_age_ms": 100 if fresh else 200_000,
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Connection State Extraction / 测试：连接状态提取
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectionStates:
    def test_all_healthy(self):
        """All sources OK + WS connected → ready/ready / 全部健康"""
        states = extract_connection_states(
            _make_system_snapshot(all_ok=True),
            _make_ws_facts(connected=True),
        )
        assert states["rest_private_connection_state"] == "ready"
        assert states["ws_private_connection_state"] == "ready"

    def test_rest_degraded(self):
        """Some REST sources failed → degraded / REST 部分源失败"""
        states = extract_connection_states(
            _make_system_snapshot(all_ok=False),
            _make_ws_facts(connected=True),
        )
        assert states["rest_private_connection_state"] == "degraded"

    def test_ws_disconnected(self):
        """WS disconnected → degraded / WS 断开"""
        states = extract_connection_states(
            _make_system_snapshot(all_ok=True),
            _make_ws_facts(connected=False),
        )
        assert states["ws_private_connection_state"] == "degraded"

    def test_no_sources(self):
        """No observer data → unknown / 无 observer 数据"""
        states = extract_connection_states(None, None)
        assert states["rest_private_connection_state"] == "unknown"
        assert states["ws_private_connection_state"] == "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Freshness State / 测试：数据新鲜度
# ═══════════════════════════════════════════════════════════════════════════════

class TestFreshnessState:
    def test_fresh_verdict(self):
        """Recent verdict → fresh / 最近的判决 → fresh"""
        assert extract_freshness_state(_make_verdict(fresh=True), int(time.time() * 1000)) == "fresh"

    def test_stale_verdict(self):
        """Old verdict → stale / 过期的判决 → stale"""
        assert extract_freshness_state(_make_verdict(fresh=False), int(time.time() * 1000)) == "stale"

    def test_no_verdict(self):
        """No verdict → unknown / 无判决 → unknown"""
        assert extract_freshness_state(None, int(time.time() * 1000)) == "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Completeness / 测试：完整性
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompleteness:
    def test_complete(self):
        result = extract_completeness(_make_system_snapshot(all_ok=True))
        assert result["account_fact_completeness_state"] == "complete"
        assert result["source_snapshot_completeness_state"] == "complete"

    def test_partial_account(self):
        snap = _make_system_snapshot(all_ok=True)
        snap["sources"]["account"]["ok"] = False
        result = extract_completeness(snap)
        assert result["account_fact_completeness_state"] == "partial"

    def test_no_snapshot(self):
        result = extract_completeness(None)
        assert result["account_fact_completeness_state"] == "missing"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Product Family Facts / 测试：产品族事实
# ═══════════════════════════════════════════════════════════════════════════════

class TestProductFamilyFacts:
    def test_unified_account(self):
        """UNIFIED account → spot/margin/perp visible, options unavailable"""
        facts = extract_product_family_facts(_make_system_snapshot())
        assert facts["spot"]["exchange_permission_fact"] == "readonly_visible"
        assert facts["perp_linear"]["exchange_permission_fact"] == "readonly_visible"
        assert facts["options"]["exchange_permission_fact"] == "unavailable"
        assert facts["other_derivatives_reserved"]["exchange_permission_fact"] == "unavailable"

    def test_no_snapshot(self):
        """No snapshot → all unavailable / 无快照 → 全部不可用"""
        facts = extract_product_family_facts(None)
        for fam in ("spot", "margin", "perp_linear", "perp_inverse", "options", "other_derivatives_reserved"):
            assert facts[fam]["exchange_permission_fact"] == "unavailable"

    def test_all_six_families_present(self):
        """All 6 product families are present / 所有 6 个产品族都存在"""
        facts = extract_product_family_facts(_make_system_snapshot())
        expected = {"spot", "margin", "perp_linear", "perp_inverse", "options", "other_derivatives_reserved"}
        assert set(facts.keys()) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Health Telemetry / 测试：健康遥测
# ═══════════════════════════════════════════════════════════════════════════════

class TestHealthTelemetry:
    def test_healthy_system(self):
        now = int(time.time() * 1000)
        health = extract_health_telemetry(
            _make_system_snapshot(), _make_ws_facts(), _make_verdict(fresh=True), now,
        )
        assert health["scores"]["overall_health_score"] == 100
        assert health["gates"]["health_gates_overall_state"] == "passed"

    def test_ws_disconnect_degrades(self):
        now = int(time.time() * 1000)
        health = extract_health_telemetry(
            _make_system_snapshot(), _make_ws_facts(connected=False), _make_verdict(fresh=True), now,
        )
        assert health["scores"]["infra_health_score"] < 100
        assert health["gates"]["ws_disconnect_gate_state"] == "failed"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Complete Snapshot Generation / 测试：完整快照生成
# ═══════════════════════════════════════════════════════════════════════════════

class TestSnapshotGeneration:
    def test_full_snapshot_has_required_fields(self):
        """Generated snapshot has all required contract fields / 包含所有合同必需字段"""
        snapshot = build_runtime_snapshot_from_observer(
            _make_system_snapshot(), _make_ws_facts(), _make_verdict(),
        )
        # Top-level required fields
        assert "runtime_snapshot_id" in snapshot
        assert "runtime_snapshot_ts_ms" in snapshot
        assert "rest_private_connection_state" in snapshot
        assert "ws_private_connection_state" in snapshot
        assert "runtime_connection_state" in snapshot
        assert "account_fact_completeness_state" in snapshot
        assert "source_snapshot_completeness_state" in snapshot
        assert "global_runtime_facts" in snapshot
        assert "product_family_facts" in snapshot
        # Global runtime facts
        grf = snapshot["global_runtime_facts"]
        assert "system_mode_fact" in grf
        assert "execution_state_fact" in grf
        assert "runtime_last_refresh_ts_ms" in grf
        assert "runtime_data_freshness_state" in grf

    def test_safety_invariants(self):
        """System mode and execution state are always safe / 系统模式和执行状态始终安全"""
        snapshot = build_runtime_snapshot_from_observer(
            _make_system_snapshot(), _make_ws_facts(), _make_verdict(),
        )
        assert snapshot["global_runtime_facts"]["system_mode_fact"] == "shadow_only"
        assert snapshot["global_runtime_facts"]["execution_state_fact"] == "execution_disabled"
        assert snapshot["execution_connector_name"] is None

    def test_contract_validation_passes(self):
        """Generated snapshot passes contract validation / 通过合同验证"""
        snapshot = build_runtime_snapshot_from_observer(
            _make_system_snapshot(), _make_ws_facts(), _make_verdict(),
        )
        from scripts.runtime_snapshot_contract import validate_runtime_snapshot_payload
        validate_runtime_snapshot_payload(snapshot)  # Should not raise

    def test_healthy_connection(self):
        """All healthy → runtime_connection_state=healthy"""
        snapshot = build_runtime_snapshot_from_observer(
            _make_system_snapshot(), _make_ws_facts(), _make_verdict(),
        )
        assert snapshot["runtime_connection_state"] == "healthy"

    def test_partial_sources_still_works(self):
        """Only verdict available → snapshot still generates / 仅有判决也能生成快照"""
        snapshot = build_runtime_snapshot_from_observer(None, None, _make_verdict())
        assert snapshot["runtime_connection_state"] in ("unknown", "down")
        assert snapshot["global_runtime_facts"]["runtime_data_freshness_state"] == "fresh"

    def test_no_sources_still_works(self):
        """All None → generates degraded snapshot / 全部为空也能生成降级快照"""
        snapshot = build_runtime_snapshot_from_observer(None, None, None)
        assert snapshot["runtime_connection_state"] in ("unknown", "down")
        assert snapshot["global_runtime_facts"]["runtime_data_freshness_state"] == "unknown"

    def test_bridge_meta_included(self):
        """Bridge metadata is included / 桥接元数据存在"""
        snapshot = build_runtime_snapshot_from_observer(
            _make_system_snapshot(), _make_ws_facts(), _make_verdict(),
        )
        assert "_bridge_meta" in snapshot
        assert snapshot["_bridge_meta"]["bridge_version"] == "v1"
        assert snapshot["_bridge_meta"]["source_verdict_code"] == "OBSERVE_ONLY"


# ═══════════════════════════════════════════════════════════════════════════════
# Test: File I/O / 测试：文件读写
# ═══════════════════════════════════════════════════════════════════════════════

class TestFileIO:
    def test_write_snapshot_creates_file(self):
        """Write snapshot creates file with correct content / 写入快照并验证内容"""
        snapshot = build_runtime_snapshot_from_observer(
            _make_system_snapshot(), _make_ws_facts(), _make_verdict(),
        )
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            write_snapshot(Path(path), snapshot)
            loaded = json.loads(Path(path).read_text())
            assert loaded["runtime_snapshot_id"] == snapshot["runtime_snapshot_id"]
        finally:
            os.unlink(path)

    def test_write_snapshot_permissions(self):
        """Written file has 0o600 permissions / 文件权限为 0o600"""
        snapshot = build_runtime_snapshot_from_observer(
            _make_system_snapshot(), _make_ws_facts(), _make_verdict(),
        )
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            write_snapshot(Path(path), snapshot)
            mode = os.stat(path).st_mode & 0o777
            assert mode == 0o600
        finally:
            os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════════════
# Test: Real Observer Data / 测试：真实 Observer 数据
# ═══════════════════════════════════════════════════════════════════════════════

class TestRealObserverData:
    """Test with actual observer output files if they exist / 使用真实 observer 文件测试"""

    SYSTEM_SNAPSHOT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json")
    WS_FACTS_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_ws_runtime_facts_latest.json")
    VERDICT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/verdicts/bybit/bybit_observer_verdict_latest.json")

    @pytest.fixture
    def real_data(self):
        """Load real observer data if available / 加载真实数据"""
        if not self.SYSTEM_SNAPSHOT_PATH.exists():
            pytest.skip("Real observer data not available")
        return {
            "system_snapshot": json.loads(self.SYSTEM_SNAPSHOT_PATH.read_text()),
            "ws_facts": json.loads(self.WS_FACTS_PATH.read_text()) if self.WS_FACTS_PATH.exists() else None,
            "verdict": json.loads(self.VERDICT_PATH.read_text()) if self.VERDICT_PATH.exists() else None,
        }

    def test_real_data_produces_valid_snapshot(self, real_data):
        """Real observer data produces valid contract-passing snapshot / 真实数据生成合规快照"""
        snapshot = build_runtime_snapshot_from_observer(
            real_data["system_snapshot"],
            real_data["ws_facts"],
            real_data["verdict"],
        )
        from scripts.runtime_snapshot_contract import validate_runtime_snapshot_payload
        validate_runtime_snapshot_payload(snapshot)

    def test_real_data_rest_ready(self, real_data):
        """Real data shows REST as ready / 真实数据显示 REST 就绪"""
        snapshot = build_runtime_snapshot_from_observer(
            real_data["system_snapshot"],
            real_data["ws_facts"],
            real_data["verdict"],
        )
        assert snapshot["rest_private_connection_state"] == "ready"
