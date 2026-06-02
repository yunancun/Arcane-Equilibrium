"""
Tests for governance_lease_bridge / lease_ipc_schema (Sprint 3 H E-3).
Decision Lease IPC bridge 測試（Sprint 3 H E-3）。

MODULE_NOTE (EN):
    Covers / 測試覆蓋:
      1. lease_ipc_schema canonical key spellings (drift sentinel)
      2. shadow_short_circuit_acquire correctness (provider variants)
      3. acquire_lease_via_ipc happy path + IPC failure + timeout + malformed
      4. release_lease_via_ipc happy path + SHADOW_BYPASS short-circuit
      5. dual-write mirror invariants (acquire/release, snapshot integrity)
      6. backward-compat: GovernanceHub.acquire_lease() still returns
         Optional[str], the lambda True shadow path returns SHADOW_BYPASS,
         and the legacy executor_agent.py:454 fail-closed branch behaves
         identically when env flag is OFF.

MODULE_NOTE (中):
    覆蓋 6 大層次：schema canonical 鍵 / shadow 短路 / IPC 成功失敗超時畸形 /
    release IPC + shadow 短路 / mirror 不變量 / governance_hub backward-compat。

Mac dev / Linux runtime 跑（從 OPENCLAW_BASE_DIR 切換）：
    cd "$OPENCLAW_BASE_DIR" && \\
    ./venvs/mac_dev/bin/python -m pytest \\
        program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_governance_lease_bridge.py -v
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Mapping
from unittest.mock import patch

import pytest

# E-3 module under test / 受測模組
from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (
    governance_divergence as divergence,  # P5 step-(i): Rust-IPC vs Python-shadow 比對器
    governance_lease_bridge as bridge,
    lease_ipc_schema as schema,
)
from program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_hub import (
    GovernanceHub,
)


# ═══════════════════════════════════════════════════════════════════════════════
# lease_ipc_schema canonical contract tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeaseIpcSchema:
    """Schema constants must not drift; contract anchors for Rust mirror."""

    def test_method_names_canonical(self):
        """Method names lock-in (drift sentinel for Rust dispatch.rs).
        方法名鎖定（給 Rust dispatch.rs 的漂移哨兵）。"""
        assert schema.METHOD_ACQUIRE_LEASE == "governance.acquire_lease"
        assert schema.METHOD_RELEASE_LEASE == "governance.release_lease"
        assert schema.METHOD_GET_LEASE == "governance.get_lease"

    def test_acquire_param_keys_canonical(self):
        """Acquire request keys lock-in.
        Acquire 請求鍵鎖定。"""
        assert schema.ACQUIRE_KEY_INTENT_ID == "intent_id"
        assert schema.ACQUIRE_KEY_SCOPE == "scope"
        assert schema.ACQUIRE_KEY_TTL_MS == "ttl_ms"
        assert schema.ACQUIRE_KEY_PROFILE == "profile"
        assert schema.ACQUIRE_KEY_SOURCE_STAGE == "source_stage"

    def test_outcome_constants_canonical(self):
        """Outcome enum strings lock-in.
        Outcome enum 字串鎖定。"""
        assert schema.OUTCOME_ACTIVE == "Active"
        assert schema.OUTCOME_BYPASS == "Bypass"
        assert schema.OUTCOME_CONSUMED == "Consumed"
        assert schema.OUTCOME_FAILED == "Failed"
        assert schema.OUTCOME_CANCELLED == "Cancelled"

    def test_profile_constants_canonical(self):
        """Profile enum strings lock-in.
        Profile enum 字串鎖定。"""
        assert schema.PROFILE_PRODUCTION == "Production"
        assert schema.PROFILE_VALIDATION == "Validation"
        assert schema.PROFILE_EXPLORATION == "Exploration"

    def test_build_acquire_request_params_happy_path(self):
        """Builder produces canonical params dict.
        建構器產生 canonical params dict。"""
        params = schema.build_acquire_request_params(
            intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0,
        )
        assert params == {
            "intent_id": "i-1",
            "scope": "TRADE_ENTRY",
            "ttl_ms": 30_000,
            "profile": "Production",
            "source_stage": "executor_agent_python",
        }

    def test_build_acquire_request_params_ttl_seconds_to_ttl_ms_conversion(self):
        """ttl_seconds float → ttl_ms int conversion is correct.
        ttl_seconds float → ttl_ms int 轉換正確。"""
        params = schema.build_acquire_request_params(
            intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=0.5,
        )
        assert params["ttl_ms"] == 500

    def test_build_acquire_request_params_rejects_bad_args(self):
        """Builder rejects empty / wrong-type args.
        建構器拒絕空 / 錯型別參數。"""
        with pytest.raises(TypeError):
            schema.build_acquire_request_params(intent_id="", scope="TRADE_ENTRY", ttl_seconds=30.0)
        with pytest.raises(TypeError):
            schema.build_acquire_request_params(intent_id="i-1", scope="", ttl_seconds=30.0)
        with pytest.raises(TypeError):
            schema.build_acquire_request_params(intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=-1)
        with pytest.raises(TypeError):
            schema.build_acquire_request_params(
                intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0, profile="Banana",
            )

    def test_build_release_rejects_shadow_bypass_sentinel(self):
        """Release builder rejects SHADOW_BYPASS sentinel (caller bug).
        Release 建構器拒絕 SHADOW_BYPASS sentinel（caller bug）。"""
        sentinel = schema.make_shadow_bypass_lease_id("intent-x")
        with pytest.raises(ValueError):
            schema.build_release_request_params(lease_id=sentinel, outcome="Consumed")

    def test_parse_acquire_response_flat_shape(self):
        """Parser handles flat {"lease_id": ..., "outcome": ...} response.
        解析器處理平攤 dict 回應。"""
        result = {"lease_id": "lease:abc", "outcome": "Active"}
        assert schema.parse_acquire_response(result) == ("lease:abc", "Active")

    def test_parse_acquire_response_wrapped_in_result(self):
        """Parser handles {"result": {...}} wrapping (one_shot_ipc_call shape).
        解析器處理 {"result": {...}} 包裝形狀。"""
        result = {"result": {"lease_id": "lease:abc", "outcome": "Bypass"}}
        assert schema.parse_acquire_response(result) == ("lease:abc", "Bypass")

    def test_parse_acquire_response_malformed_returns_none_lease(self):
        """Malformed payload → (None, "")."""
        assert schema.parse_acquire_response({}) == (None, "")
        assert schema.parse_acquire_response({"foo": "bar"}) == (None, "")
        assert schema.parse_acquire_response({"lease_id": 42, "outcome": "Active"}) == (None, "")

    def test_parse_release_response_ok_true(self):
        """Parser returns True only when ok=True."""
        assert schema.parse_release_response({"ok": True}) is True
        assert schema.parse_release_response({"result": {"ok": True}}) is True
        assert schema.parse_release_response({"ok": False}) is False
        assert schema.parse_release_response({}) is False
        assert schema.parse_release_response({"ok": "true"}) is False  # strict bool

    def test_shadow_bypass_sentinel_round_trip(self):
        """make_shadow_bypass / is_shadow_bypass round-trip.
        sentinel 雙向匹配。"""
        sentinel = schema.make_shadow_bypass_lease_id("intent-x")
        assert sentinel == "SHADOW_BYPASS:intent-x"
        assert schema.is_shadow_bypass_lease_id(sentinel) is True
        assert schema.is_shadow_bypass_lease_id("lease:abc") is False
        assert schema.is_shadow_bypass_lease_id("") is False


# ═══════════════════════════════════════════════════════════════════════════════
# shadow_short_circuit_acquire tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestShadowShortCircuit:
    """Caller-side shadow short-circuit (PA push back #2 HIGH)."""

    def test_provider_none_returns_none(self):
        """No provider → no short-circuit / None.
        無 provider → 不短路 / None。"""
        assert bridge.shadow_short_circuit_acquire(
            intent_id="i-1", shadow_mode_provider=None,
        ) is None

    def test_provider_returns_true_emits_sentinel(self):
        """Provider True → emit SHADOW_BYPASS sentinel."""
        result = bridge.shadow_short_circuit_acquire(
            intent_id="intent-7", shadow_mode_provider=lambda: True,
        )
        assert result == "SHADOW_BYPASS:intent-7"

    def test_provider_returns_false_does_not_short_circuit(self):
        """Provider False → return None (caller proceeds)."""
        assert bridge.shadow_short_circuit_acquire(
            intent_id="i-1", shadow_mode_provider=lambda: False,
        ) is None

    def test_provider_raising_exception_is_treated_as_non_shadow(self):
        """Misbehaving provider must NOT silently route into shadow path
        (would hide real lease failures). Treat as non-shadow.
        異常 provider 不可靜默路由進 shadow 路徑（會掩蓋真實 lease 失敗）。
        視為 non-shadow。"""
        def bad_provider():
            raise RuntimeError("boom")

        assert bridge.shadow_short_circuit_acquire(
            intent_id="i-1", shadow_mode_provider=bad_provider,
        ) is None


# ═══════════════════════════════════════════════════════════════════════════════
# acquire_lease_via_ipc / release_lease_via_ipc tests with fake dispatcher
# ═══════════════════════════════════════════════════════════════════════════════

def _make_async_dispatcher(*, return_value=None, raise_exc=None, sleep=None):
    """Build a fake IPC dispatcher for tests.
    為測試構造假 IPC 派發器。"""
    async def _dispatch(method: str, params: Mapping[str, Any], timeout: float):
        if sleep is not None:
            await asyncio.sleep(sleep)
        if raise_exc is not None:
            raise raise_exc
        return return_value
    return _dispatch


class TestAcquireLeaseViaIpc:
    """acquire_lease_via_ipc unit tests with injected dispatcher."""

    def setup_method(self):
        bridge.reset_dual_write_mirror()

    def test_happy_path_active_outcome(self):
        """Rust returns Active → bridge returns lease_id + records mirror.
        Rust 回 Active → bridge 回 lease_id 並寫入 mirror。"""
        fake = _make_async_dispatcher(return_value={"lease_id": "lease:abc", "outcome": "Active"})
        lease_id = bridge.acquire_lease_via_ipc(
            intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0,
            dispatcher=fake,
        )
        assert lease_id == "lease:abc"
        snapshot = bridge.get_dual_write_mirror_snapshot()
        assert "lease:abc" in snapshot
        assert snapshot["lease:abc"]["intent_id"] == "i-1"
        assert snapshot["lease:abc"]["scope"] == "TRADE_ENTRY"

    def test_bypass_outcome_returned_as_lease_id(self):
        """Validation/Exploration profile → Rust returns Bypass; bridge
        returns the literal "bypass" string (Rust E-1 emits "bypass" lease_id).
        Validation/Exploration profile → Rust 回 Bypass；bridge 回字串 "bypass"。"""
        fake = _make_async_dispatcher(return_value={"lease_id": "bypass", "outcome": "Bypass"})
        lease_id = bridge.acquire_lease_via_ipc(
            intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0,
            profile="Validation", dispatcher=fake,
        )
        assert lease_id == "bypass"

    def test_ipc_outage_returns_none(self):
        """Dispatcher raising → fail-closed None.
        派發器拋例外 → fail-closed None。"""
        fake = _make_async_dispatcher(raise_exc=ConnectionError("rust engine down"))
        lease_id = bridge.acquire_lease_via_ipc(
            intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0,
            dispatcher=fake,
        )
        assert lease_id is None

    def test_ipc_timeout_returns_none(self):
        """Dispatcher slower than timeout → fail-closed None.
        派發器超時 → fail-closed None。"""
        fake = _make_async_dispatcher(sleep=0.5)
        lease_id = bridge.acquire_lease_via_ipc(
            intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0,
            timeout_seconds=0.1, dispatcher=fake,
        )
        assert lease_id is None

    def test_malformed_payload_returns_none(self):
        """Rust returns junk → fail-closed None.
        Rust 回垃圾 → fail-closed None。"""
        fake = _make_async_dispatcher(return_value={"foo": "bar"})
        lease_id = bridge.acquire_lease_via_ipc(
            intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0,
            dispatcher=fake,
        )
        assert lease_id is None

    def test_unknown_outcome_returns_none(self):
        """Unknown outcome string → defensive fail-closed.
        未知 outcome → 防禦性 fail-closed。"""
        fake = _make_async_dispatcher(return_value={"lease_id": "lease:abc", "outcome": "WhoKnows"})
        assert bridge.acquire_lease_via_ipc(
            intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0,
            dispatcher=fake,
        ) is None


class TestReleaseLeaseViaIpc:
    """release_lease_via_ipc unit tests with injected dispatcher."""

    def setup_method(self):
        bridge.reset_dual_write_mirror()

    def test_happy_path_consumed(self):
        """ok=true response → return True + mirror updated.
        ok=true 回應 → 回 True 並更新 mirror。"""
        bridge.record_dual_write_acquire(
            lease_id="lease:abc", intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0,
        )
        fake = _make_async_dispatcher(return_value={"ok": True})
        ok = bridge.release_lease_via_ipc(
            lease_id="lease:abc", consumed=True, dispatcher=fake,
        )
        assert ok is True
        snapshot = bridge.get_dual_write_mirror_snapshot()
        assert snapshot["lease:abc"]["release_outcome"] == "Consumed"

    def test_shadow_bypass_short_circuits_to_true(self):
        """SHADOW_BYPASS sentinel → True without IPC engagement.
        SHADOW_BYPASS sentinel → 不啟動 IPC 直接 True。"""
        called = []

        async def watcher(method, params, timeout):
            called.append(method)
            return {"ok": True}

        ok = bridge.release_lease_via_ipc(
            lease_id="SHADOW_BYPASS:intent-x", consumed=True, dispatcher=watcher,
        )
        assert ok is True
        assert called == []  # IPC not engaged

    def test_ipc_failure_returns_false(self):
        """Dispatcher raising → False (fail-soft).
        派發器拋例外 → False（fail-soft）。"""
        fake = _make_async_dispatcher(raise_exc=ConnectionError("rust engine down"))
        ok = bridge.release_lease_via_ipc(
            lease_id="lease:abc", consumed=True, dispatcher=fake,
        )
        assert ok is False

    def test_failed_outcome_when_consumed_false(self):
        """consumed=False → outcome=Failed (release builder enforces this).
        consumed=False → outcome=Failed（release builder 強制）。"""
        params_seen = {}

        async def capture(method, params, timeout):
            params_seen.update(params)
            return {"ok": True}

        bridge.release_lease_via_ipc(
            lease_id="lease:abc", consumed=False, dispatcher=capture,
        )
        assert params_seen.get("outcome") == "Failed"


# ═══════════════════════════════════════════════════════════════════════════════
# Dual-write mirror invariant tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDualWriteMirror:
    """Mirror invariants under acquire/release sequences."""

    def setup_method(self):
        bridge.reset_dual_write_mirror()

    def test_acquire_then_release_records_both_phases(self):
        """Mirror records acquired_at + released_at correctly.
        Mirror 正確記錄 acquired_at + released_at。"""
        bridge.record_dual_write_acquire(
            lease_id="lease:abc", intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0,
        )
        snapshot_before = bridge.get_dual_write_mirror_snapshot()
        assert snapshot_before["lease:abc"]["released_at"] is None

        bridge.record_dual_write_release(lease_id="lease:abc", outcome="Consumed")
        snapshot_after = bridge.get_dual_write_mirror_snapshot()
        assert snapshot_after["lease:abc"]["released_at"] is not None
        assert snapshot_after["lease:abc"]["release_outcome"] == "Consumed"

    def test_shadow_bypass_sentinel_not_recorded(self):
        """Shadow sentinel acquire/release does NOT pollute mirror.
        Shadow sentinel 的 acquire/release 不污染 mirror。"""
        bridge.record_dual_write_acquire(
            lease_id="SHADOW_BYPASS:intent-x",
            intent_id="intent-x",
            scope="TRADE_ENTRY",
            ttl_seconds=30.0,
        )
        bridge.record_dual_write_release(
            lease_id="SHADOW_BYPASS:intent-x", outcome="Consumed",
        )
        assert bridge.get_dual_write_mirror_snapshot() == {}

    def test_release_unknown_lease_id_does_not_crash(self):
        """Releasing a never-acquired id is debug-logged, not raised.
        釋放從未 acquire 的 id 僅 debug log，不拋例外。"""
        # Should not raise
        bridge.record_dual_write_release(lease_id="lease:never_acquired", outcome="Consumed")
        assert bridge.get_dual_write_mirror_snapshot() == {}

    def test_snapshot_is_defensive_copy(self):
        """Mutating snapshot does not mutate the live mirror.
        修改 snapshot 不影響 live mirror。"""
        bridge.record_dual_write_acquire(
            lease_id="lease:x", intent_id="i", scope="s", ttl_seconds=1.0,
        )
        snapshot = bridge.get_dual_write_mirror_snapshot()
        snapshot["lease:x"]["intent_id"] = "tampered"
        live = bridge.get_dual_write_mirror_snapshot()
        assert live["lease:x"]["intent_id"] == "i"


# ═══════════════════════════════════════════════════════════════════════════════
# is_lease_ipc_enabled env-gate tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnvFlag:
    """Strict-equality "1" gate, mirroring h_state_invalidator pattern."""

    def test_env_unset_disabled(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(bridge.LEASE_IPC_ENABLED_ENV, None)
            assert bridge.is_lease_ipc_enabled() is False

    def test_env_one_enabled(self):
        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "1"}):
            assert bridge.is_lease_ipc_enabled() is True

    def test_env_zero_disabled(self):
        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "0"}):
            assert bridge.is_lease_ipc_enabled() is False

    def test_env_true_string_disabled_strict_equality(self):
        """Strict "1" — 'true' / 'yes' do NOT enable.
        嚴格 "1" — 'true' / 'yes' 不啟用。"""
        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "true"}):
            assert bridge.is_lease_ipc_enabled() is False
        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "yes"}):
            assert bridge.is_lease_ipc_enabled() is False
        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: ""}):
            assert bridge.is_lease_ipc_enabled() is False


# ═══════════════════════════════════════════════════════════════════════════════
# GovernanceHub end-to-end backward-compat tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestGovernanceHubBackwardCompat:
    """GovernanceHub.acquire_lease/release_lease/get_lease retrofit must
    preserve the existing executor_agent.py:454 caller contract.
    GovernanceHub.acquire_lease 改造須保留 executor_agent.py:454 caller 契約。"""

    def setup_method(self):
        bridge.reset_dual_write_mirror()

    def test_legacy_local_sm_path_unchanged_when_env_off(self, tmp_audit_dir):
        """Env flag OFF → legacy local SM path unchanged.
        Env flag OFF → legacy local SM 路徑不變。"""
        # Make sure env flag is OFF for this test even if test runner has it set.
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(bridge.LEASE_IPC_ENABLED_ENV, None)
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()

            auth_obj = hub._authorization_sm.create_draft(
                title="Test Auth",
                scope={"lease_scopes": ["TRADE_ENTRY"]},
                created_by="test",
                expires_at_ms=int(time.time() * 1000) + 3600_000,
            )
            hub._authorization_sm.submit_for_approval(auth_obj.authorization_id)
            hub._authorization_sm.approve(auth_obj.authorization_id, approved_by="operator")

            lease_id = hub.acquire_lease(intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0)
            assert isinstance(lease_id, str)
            assert lease_id  # non-empty
            assert not lease_id.startswith("SHADOW_BYPASS:")

            # release path
            ok = hub.release_lease(lease_id=lease_id, consumed=False)
            assert ok is True

    def test_shadow_short_circuit_returns_sentinel_when_provider_true(self, tmp_audit_dir):
        """ExecutorAgent shadow=True path → SHADOW_BYPASS sentinel; no SM transition.
        ExecutorAgent shadow=True 路徑 → SHADOW_BYPASS sentinel；無 SM transition。"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(bridge.LEASE_IPC_ENABLED_ENV, None)
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub.set_shadow_mode_provider(lambda: True)

            lease_id = hub.acquire_lease(intent_id="intent-7", scope="TRADE_ENTRY")
            assert lease_id == "SHADOW_BYPASS:intent-7"

            # release of sentinel returns True without touching SM
            assert hub.release_lease(lease_id=lease_id, consumed=True) is True

            # get_lease of sentinel returns None
            assert hub.get_lease(lease_id) is None

    def test_ipc_path_engaged_when_env_on_with_injected_dispatcher(self, tmp_audit_dir):
        """Env flag ON + dispatcher injected → IPC path executes (no fallback).
        Env flag ON + 注入 dispatcher → 走 IPC 路徑（不 fallback）。"""
        async def dispatcher(method, params, timeout):
            assert method == "governance.acquire_lease"
            assert params["intent_id"] == "i-99"
            return {"lease_id": "lease:rs-xyz", "outcome": "Active"}

        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "1"}):
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            # auth required by Step 2 gate
            auth_obj = hub._authorization_sm.create_draft(
                title="Test Auth",
                scope={"lease_scopes": ["TRADE_ENTRY"]},
                created_by="test",
                expires_at_ms=int(time.time() * 1000) + 3600_000,
            )
            hub._authorization_sm.submit_for_approval(auth_obj.authorization_id)
            hub._authorization_sm.approve(auth_obj.authorization_id, approved_by="operator")

            hub.set_lease_ipc_dispatcher(dispatcher)
            lease_id = hub.acquire_lease(intent_id="i-99", scope="TRADE_ENTRY", ttl_seconds=30.0)
            assert lease_id == "lease:rs-xyz"

    def test_ipc_outage_when_env_on_returns_none_no_silent_fallback(self, tmp_audit_dir):
        """IPC failure under env=1 → None (NO silent fallback to local SM,
        which would break dual-write canonical contract).
        env=1 下 IPC 失敗 → None（不靜默 fallback 至 local SM，否則破壞
        dual-write canonical 契約）。"""
        async def dead_dispatcher(method, params, timeout):
            raise ConnectionError("rust engine offline")

        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "1"}):
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            auth_obj = hub._authorization_sm.create_draft(
                title="Test Auth",
                scope={"lease_scopes": ["TRADE_ENTRY"]},
                created_by="test",
                expires_at_ms=int(time.time() * 1000) + 3600_000,
            )
            hub._authorization_sm.submit_for_approval(auth_obj.authorization_id)
            hub._authorization_sm.approve(auth_obj.authorization_id, approved_by="operator")
            hub.set_lease_ipc_dispatcher(dead_dispatcher)

            lease_id = hub.acquire_lease(intent_id="i-x", scope="TRADE_ENTRY", ttl_seconds=30.0)
            assert lease_id is None


# ═══════════════════════════════════════════════════════════════════════════════
# Module-level invariants
# ═══════════════════════════════════════════════════════════════════════════════

def test_module_imports_have_no_side_effects():
    """Importing lease_ipc_schema / governance_lease_bridge does not engage IPC.
    匯入兩個模組沒有 IPC 副作用。"""
    # If any side effect (e.g., socket connect) had happened, the test runner
    # would have errored on import. This test is documentary.
    # 若有副作用（如 socket connect），import 階段就會 error。本測試為文檔型。
    assert hasattr(schema, "METHOD_ACQUIRE_LEASE")
    assert hasattr(bridge, "acquire_lease_via_ipc")


# ═══════════════════════════════════════════════════════════════════════════════
# E2 round 1 LOW-2 retrofit (2026-05-03):
#   ipc_client.py json.dumps must use ensure_ascii=False so any unicode in the
#   IPC payload (intent_id / strategy_name / future fields) keeps raw UTF-8 on
#   the wire — byte-equal to Rust serde_json::to_vec. Sprint 1 Track A F1 lock
#   established this contract for manifest signing; LOW-2 extends it to the
#   lease IPC bridge so a future cross-language byte-equal verification (HMAC,
#   manifest, or audit signature) won't fail-closed on non-ASCII payloads.
#
# E2 round 1 LOW-2 retrofit（2026-05-03）：
#   ipc_client.py 的 json.dumps 必用 ensure_ascii=False，使 IPC payload 含 unicode
#   時（intent_id / strategy_name / 未來欄位）wire 上保留 raw UTF-8 — 與 Rust
#   serde_json::to_vec byte-equal。Sprint 1 Track A F1 鎖建立此契約於 manifest
#   signing；LOW-2 將其延伸至 lease IPC bridge，避免未來跨語言 byte-equal 驗證
#   （HMAC、manifest、audit signature）在非 ASCII payload 下 fail-closed。
# ═══════════════════════════════════════════════════════════════════════════════

import hashlib  # noqa: E402  (test-only; safe to keep colocated with class)
import json  # noqa: E402


class TestLeaseIpcUnicodeByteEqualContract:
    """Lease IPC payload byte-equal under unicode (LOW-2 retrofit).
    Lease IPC payload 在 unicode 下的 byte-equal 契約（LOW-2 retrofit）。"""

    def test_acquire_request_params_unicode_intent_id_byte_equal_canonical(self):
        """build_acquire_request_params output JSON-serialises byte-equal to a
        manually canonicalised dict when intent_id contains unicode.
        含 unicode 的 intent_id 經 build_acquire_request_params 後序列化結果與
        手動 canonical 化的 dict byte-equal。

        F1 contract / F1 契約:
            ``json.dumps(d, separators=(',', ':'), ensure_ascii=False)`` is the
            canonical form Rust ``serde_json::to_vec`` mirrors. The kwarg
            ``ensure_ascii=False`` is the critical bit — Python default True
            would emit ``\\u6d4b\\u8bd5`` while Rust emits raw ``测试`` UTF-8.
            Mismatch = future cross-language byte-equal HMAC/audit signature
            verification永遠 fail-closed.
            ensure_ascii=False 為關鍵 kwarg — Python 預設 True 會 escape 為
            \\uXXXX，Rust 直接 emit raw UTF-8；不對齊 = 未來跨語言 byte-equal
            HMAC / audit signature 驗證恆 fail-closed。
        """
        # intent_id 含 U+6D4B U+8BD5 (测试) + 全形分號 (U+FF1B) — non-ASCII
        # 拉滿，PA prompt LOW-2 §加 1 unit test 範例完全對齊。
        # intent_id 含「测试_intent_001」+ 全形分號，對齊 PA prompt LOW-2 範例。
        intent_id = "测试_intent_001；分號"
        params = schema.build_acquire_request_params(
            intent_id=intent_id,
            scope="TRADE_ENTRY",
            ttl_seconds=30.0,
            profile=schema.PROFILE_PRODUCTION,
            source_stage="executor_agent_python",
        )

        # Mirror of what ipc_client.py:218 will serialise (with our LOW-2 kwarg).
        # 鏡像 ipc_client.py:218 的 LOW-2 kwarg 序列化結果。
        canonical_bytes = json.dumps(
            params, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

        # Anti-`\uXXXX` guard — if ensure_ascii were True, raw `测试` would
        # become `测试` and this assertion would fail.
        # 反 `\uXXXX` 守護 — ensure_ascii=True 會 escape 成 测试 → 失敗。
        decoded = canonical_bytes.decode("utf-8")
        assert "\\u" not in decoded, (
            f"canonical bytes must not contain \\u escape (LOW-2 contract); "
            f"got: {decoded!r}"
        )

        # Direct UTF-8 substring — raw 测试 must be present in the bytes.
        # 直接 UTF-8 substring — raw 测试 必在 bytes 內。
        assert "测试".encode("utf-8") in canonical_bytes, (
            "raw UTF-8 测试 must appear in canonical bytes"
        )
        assert "；".encode("utf-8") in canonical_bytes, (
            "raw UTF-8 fullwidth semicolon must appear in canonical bytes"
        )

        # SHA-256 byte-equal anchor — pin the canonical bytes hash so any
        # accidental drift in builder field order / spelling fails this test.
        # SHA-256 byte-equal 錨 — 釘 canonical bytes 雜湊，builder 任何鍵順序 /
        # 拼寫漂移立即 fail。
        sha = hashlib.sha256(canonical_bytes).hexdigest()
        # Re-compute expected from the params dict via the same kwarg set;
        # this is the byte-equal contract anchor — Rust serde_json::to_vec
        # over the equivalent struct must produce these same bytes.
        # 由 params dict 用同 kwarg 重算為 expected — Rust serde_json::to_vec
        # 對等 struct 必產出相同 bytes（byte-equal contract anchor）。
        expected_bytes = json.dumps(
            {
                schema.ACQUIRE_KEY_INTENT_ID: intent_id,
                schema.ACQUIRE_KEY_SCOPE: "TRADE_ENTRY",
                schema.ACQUIRE_KEY_TTL_MS: 30000,
                schema.ACQUIRE_KEY_PROFILE: schema.PROFILE_PRODUCTION,
                schema.ACQUIRE_KEY_SOURCE_STAGE: "executor_agent_python",
            },
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        expected_sha = hashlib.sha256(expected_bytes).hexdigest()
        assert sha == expected_sha, (
            "builder output bytes must equal manually-canonicalised dict bytes"
        )

    def test_release_request_params_unicode_lease_id_byte_equal_canonical(self):
        """release request params byte-equal under unicode lease_id (defense
        in depth — current acquire produces opaque hex lease_id, but contract
        must hold for any future lease id format that includes non-ASCII).
        release request params 在 unicode lease_id 下 byte-equal（防禦深度 —
        當前 acquire 產生不透明 hex lease_id，但契約必對任何未來含非 ASCII 的
        lease id 格式成立）。"""
        # Hypothetical future lease_id with non-ASCII (defensive) / 假設未來
        # 含非 ASCII 的 lease_id（防禦）。
        lease_id = "lease:测试_abc123"
        params = schema.build_release_request_params(
            lease_id=lease_id,
            outcome=schema.OUTCOME_CONSUMED,
        )
        canonical_bytes = json.dumps(
            params, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

        # No \u escape sequence in the canonical bytes.
        # canonical bytes 內無 \u escape。
        decoded = canonical_bytes.decode("utf-8")
        assert "\\u" not in decoded
        assert "测试".encode("utf-8") in canonical_bytes

    def test_ipc_client_json_dumps_uses_ensure_ascii_false(self):
        """Source-grep test: ipc_client.py call() + auth() json.dumps both pass
        ensure_ascii=False. Drift sentinel — any future commit reverting LOW-2
        triggers this regression marker.
        源碼 grep 測試：ipc_client.py 兩處 json.dumps 必皆帶 ensure_ascii=False。
        漂移哨兵 — 未來任何 commit revert LOW-2 立即觸發此 regression marker。"""
        ipc_client_path = (
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            + "/app/ipc_client.py"
        )
        with open(ipc_client_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Must contain at least 2 ensure_ascii=False (call + auth handshake).
        # 至少 2 處 ensure_ascii=False（call + auth handshake）。
        ensure_ascii_count = content.count("ensure_ascii=False")
        assert ensure_ascii_count >= 2, (
            f"ipc_client.py must have ensure_ascii=False at both json.dumps "
            f"call sites (LOW-2 contract); found {ensure_ascii_count}"
        )

        # No json.dumps without ensure_ascii in the source (regression guard).
        # Counts json.dumps tokens vs ensure_ascii kwargs near them.
        # 源碼內無漏 ensure_ascii 的 json.dumps（regression 守護）。
        json_dumps_count = content.count("json.dumps(")
        # Allow some json.dumps outside dispatch path (logging fixtures etc.),
        # but contract is: every dispatch-layer json.dumps must mirror the
        # canonical form. We pin >= 2 hits and matching ensure_ascii count.
        # 允許部分 json.dumps 在非 dispatch 路徑（如 logging fixture），但契約
        # 是：每個 dispatch-layer json.dumps 必鏡像 canonical form。我們釘
        # >= 2 hit 且 ensure_ascii 計數一致。
        assert json_dumps_count >= 2
        assert ensure_ascii_count >= json_dumps_count, (
            f"every json.dumps in ipc_client.py must carry ensure_ascii=False; "
            f"found {json_dumps_count} json.dumps but only "
            f"{ensure_ascii_count} ensure_ascii=False"
        )

    def test_no_unicode_escape_in_request_payload_round_trip(self):
        """End-to-end: build acquire params with unicode + emulate the wire
        serialisation that ipc_client.py:218 will perform → assert resulting
        bytes contain raw UTF-8 (not \\uXXXX). Locks the production wire shape.
        端到端：build acquire params 含 unicode + 模擬 ipc_client.py:218 wire
        序列化 → 結果 bytes 含 raw UTF-8（不是 \\uXXXX）。鎖定生產 wire 形狀。"""
        params = schema.build_acquire_request_params(
            intent_id="测试_e2e_001",
            scope="TRADE_ENTRY",
            ttl_seconds=30.0,
        )
        # Mirror ipc_client.py:210-218 envelope shape.
        # 鏡像 ipc_client.py:210-218 envelope 形狀。
        request_envelope = {
            "jsonrpc": "2.0",
            "method": schema.METHOD_ACQUIRE_LEASE,
            "id": 42,
            "params": params,
        }
        wire_bytes = (
            json.dumps(
                request_envelope, separators=(",", ":"), ensure_ascii=False
            )
            + "\n"
        ).encode("utf-8")

        # No \uXXXX escape in the entire envelope.
        # 整個 envelope 內無 \uXXXX escape。
        decoded = wire_bytes.decode("utf-8")
        assert "\\u" not in decoded, (
            f"wire bytes must not contain \\u escape; got: {decoded!r}"
        )
        # Raw UTF-8 测试 present in payload bytes.
        # raw UTF-8 测试 在 payload bytes 內。
        assert "测试".encode("utf-8") in wire_bytes


# ═══════════════════════════════════════════════════════════════════════════════
# P5 step-(i): governance_divergence comparator unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDivergenceComparatorUnit:
    """Direct unit tests for the divergence comparator sink (no hub).
    比對器 sink 的直接單元測試（不經 hub）。"""

    def setup_method(self):
        divergence.reset_divergence_state()

    def test_match_recorded_no_divergence(self):
        """rust == python → match True, counter divergences stays 0, total +1.
        rust == python → match=True，divergences 維持 0，total +1。"""
        m = divergence.record_divergence(
            op=divergence.OP_ACQUIRE,
            rust_outcome=divergence.OUTCOME_GRANTED,
            python_outcome=divergence.OUTCOME_GRANTED,
            intent_id="i-1", scope="TRADE_ENTRY",
        )
        assert m is True
        c = divergence.get_divergence_counters()
        assert c == {"total": 1, "matches": 1, "divergences": 0}

    def test_mismatch_recorded_as_divergence_with_bite(self):
        """rust != python → match False, divergences +1, differing_fields filled,
        mismatch snapshot surfaces the entry. 比對器有 bite。
        rust != python → match=False，divergences +1，differing_fields 已填，
        mismatch snapshot 取得該筆。"""
        m = divergence.record_divergence(
            op=divergence.OP_ACQUIRE,
            rust_outcome=divergence.OUTCOME_GRANTED,
            python_outcome=divergence.OUTCOME_DENIED,
            intent_id="i-2", scope="TRADE_ENTRY",
        )
        assert m is False
        c = divergence.get_divergence_counters()
        assert c["divergences"] == 1
        assert c["total"] == 1
        mismatches = divergence.get_mismatch_snapshot()
        assert len(mismatches) == 1
        assert mismatches[0]["rust_outcome"] == divergence.OUTCOME_GRANTED
        assert mismatches[0]["python_outcome"] == divergence.OUTCOME_DENIED
        assert mismatches[0]["differing_fields"] == ["outcome"]
        assert mismatches[0]["intent_id"] == "i-2"

    def test_snapshot_is_defensive_copy(self):
        """Mutating a snapshot row does not corrupt the live ring.
        修改 snapshot row 不污染 live ring。"""
        divergence.record_divergence(
            op=divergence.OP_ACQUIRE,
            rust_outcome=divergence.OUTCOME_GRANTED,
            python_outcome=divergence.OUTCOME_GRANTED,
            intent_id="i-3",
        )
        snap = divergence.get_divergence_snapshot()
        snap[0]["intent_id"] = "tampered"
        live = divergence.get_divergence_snapshot()
        assert live[0]["intent_id"] == "i-3"

    def test_reset_clears_ring_and_counters(self):
        """reset zeroes both ring + counters (test isolation contract).
        reset 同時清空 ring + counters。"""
        divergence.record_divergence(
            op=divergence.OP_RELEASE,
            rust_outcome=divergence.OUTCOME_GRANTED,
            python_outcome=divergence.OUTCOME_DENIED,
        )
        assert divergence.get_divergence_counters()["total"] == 1
        divergence.reset_divergence_state()
        assert divergence.get_divergence_counters() == {"total": 0, "matches": 0, "divergences": 0}
        assert divergence.get_divergence_snapshot() == []

    def test_record_never_raises_on_bad_input(self):
        """Comparator best-effort: an internal error must not raise into caller
        (returns True = not counted as divergence). 比對器 best-effort：內部錯誤
        不可向 caller 拋（回 True，不計為 divergence）。"""
        # differing_fields 給非 list 的怪型別也不可炸（防禦）。
        m = divergence.record_divergence(
            op=divergence.OP_GET,
            rust_outcome=divergence.OUTCOME_GRANTED,
            python_outcome=divergence.OUTCOME_GRANTED,
            differing_fields="not-a-list",  # type: ignore[arg-type]
        )
        assert m is True  # match path; no raise


# ═══════════════════════════════════════════════════════════════════════════════
# P5 step-(i): GovernanceHub authoritative routing + shadow-compute divergence
# ═══════════════════════════════════════════════════════════════════════════════

def _authorize_hub(hub: GovernanceHub) -> None:
    """Drive the hub's auth SM to ACTIVE so the acquire auth-gate passes.
    把 hub 的 auth SM 驅到 ACTIVE，使 acquire 的 auth-gate 通過。"""
    auth_obj = hub._authorization_sm.create_draft(
        title="Test Auth",
        scope={"lease_scopes": ["TRADE_ENTRY"]},
        created_by="test",
        expires_at_ms=int(time.time() * 1000) + 3600_000,
    )
    hub._authorization_sm.submit_for_approval(auth_obj.authorization_id)
    hub._authorization_sm.approve(auth_obj.authorization_id, approved_by="operator")


class TestHubAuthoritativeRoutingAndDivergence:
    """Flag ON → Rust IPC authoritative + local Python SM shadow-compute compared;
    flag OFF → byte-unchanged + comparator silent. fail-closed on IPC error.
    Flag ON → Rust IPC 權威 + 本地 Python SM 影子比對；flag OFF → 行為不變且
    比對器靜默。IPC 錯誤 fail-closed。"""

    def setup_method(self):
        bridge.reset_dual_write_mirror()
        divergence.reset_divergence_state()

    def test_flag_off_comparator_silent_and_behavior_unchanged(self, tmp_audit_dir):
        """Flag OFF → legacy local SM path; comparator records NOTHING (total=0).
        Flag OFF → legacy local SM 路徑；比對器零記錄（total=0）。"""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(bridge.LEASE_IPC_ENABLED_ENV, None)
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            _authorize_hub(hub)

            lease_id = hub.acquire_lease(intent_id="i-1", scope="TRADE_ENTRY", ttl_seconds=30.0)
            assert isinstance(lease_id, str) and lease_id
            assert not lease_id.startswith("SHADOW_BYPASS:")
            assert hub.release_lease(lease_id=lease_id, consumed=False) is True

            # Comparator must be untouched on the flag-OFF path.
            # flag-OFF 路徑比對器必完全未動。
            assert divergence.get_divergence_counters()["total"] == 0

    def test_flag_on_agreement_records_match_no_divergence(self, tmp_audit_dir):
        """Flag ON + Rust grants + local auth ACTIVE → both the auth-axis compare
        and the acquire-axis compare agree → 2 match rows, 0 divergence.
        Flag ON + Rust 放行 + 本地 auth ACTIVE → auth 軸與 acquire 軸皆一致 →
        2 筆 match，0 divergence。"""
        async def dispatcher(method, params, timeout):
            # Step-1.5 auth-axis compare reads is_authorized first; then acquire.
            # Step-1.5 auth-axis 先讀 is_authorized；隨後才 acquire。
            if method == "governance.is_authorized":
                return {"authorized": True}
            assert method == "governance.acquire_lease"
            return {"lease_id": "lease:rs-1", "outcome": "Active"}

        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "1"}):
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            _authorize_hub(hub)
            hub.set_lease_ipc_dispatcher(dispatcher)

            lease_id = hub.acquire_lease(intent_id="i-agree", scope="TRADE_ENTRY", ttl_seconds=30.0)
            assert lease_id == "lease:rs-1"  # Rust result is authoritative

            c = divergence.get_divergence_counters()
            assert c["total"] == 2  # auth-axis (match) + acquire-axis (match)
            assert c["divergences"] == 0
            assert c["matches"] == 2

    def test_flag_on_forced_divergence_bite_rust_grants_python_denies(self, tmp_audit_dir):
        """FORCED-DIVERGENCE BITE: Rust grants acquire but the local Python SM
        auth-gate DENIES (no ACTIVE auth) → comparator records exactly 1
        divergence. Proves the shadow-compare is not a no-op.

        強制分歧 bite：Rust 放行 acquire，但本地 Python SM auth-gate 拒絕
        （無 ACTIVE auth）→ 比對器恰記 1 筆 divergence。證明影子比對非空轉。

        NOTE: the hub's own Step-2 auth-gate (is_authorized) would normally block
        before IPC; we inject an is_authorized override so the IPC path is reached
        while the local *lease auth-permits-scope* shadow still denies (no
        effective auth) — isolating the comparator's bite from the Step-2 gate.
        注意：hub 自身 Step-2 auth-gate 通常會在 IPC 前擋下；此處覆寫
        is_authorized 讓 IPC 路徑可達，而本地 lease auth 影子仍拒絕（無 effective
        auth），以隔離比對器 bite 與 Step-2 gate。"""
        async def dispatcher(method, params, timeout):
            return {"lease_id": "lease:rs-2", "outcome": "Active"}

        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "1"}):
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            # NO _authorize_hub() → local auth-gate has no effective auth → shadow DENIES.
            # 不呼叫 _authorize_hub() → 本地無 effective auth → 影子判 DENIED。
            hub.set_lease_ipc_dispatcher(dispatcher)
            # Bypass only the Step-2 hot-path gate so we reach the IPC + shadow.
            # 僅繞過 Step-2 hot-path gate，使流程到達 IPC + 影子。
            hub.is_authorized = lambda: True  # type: ignore[method-assign]

            lease_id = hub.acquire_lease(intent_id="i-diverge", scope="TRADE_ENTRY", ttl_seconds=30.0)
            assert lease_id == "lease:rs-2"  # authoritative Rust result still returned

            c = divergence.get_divergence_counters()
            assert c["total"] == 1
            assert c["divergences"] == 1, "forced divergence must be detected (comparator bite)"
            mismatches = divergence.get_mismatch_snapshot()
            assert len(mismatches) == 1
            assert mismatches[0]["op"] == "acquire"
            assert mismatches[0]["rust_outcome"] == divergence.OUTCOME_GRANTED
            assert mismatches[0]["python_outcome"] == divergence.OUTCOME_DENIED
            assert mismatches[0]["intent_id"] == "i-diverge"

    def test_flag_on_ipc_error_fail_closed_records_deny_outcome(self, tmp_audit_dir):
        """IPC error under flag ON → acquire returns None (fail-closed, §3b); the
        comparator still records the op with rust_outcome=denied (and since local
        auth is ACTIVE → python granted → this is itself a divergence the soak
        would surface: Rust-down vs Python-would-grant).
        flag ON 下 IPC 錯誤 → acquire 回 None（fail-closed §3b）；比對器仍記該操作
        （rust=denied）。"""
        async def dead_dispatcher(method, params, timeout):
            raise ConnectionError("rust engine offline")

        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "1"}):
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            _authorize_hub(hub)
            hub.set_lease_ipc_dispatcher(dead_dispatcher)

            lease_id = hub.acquire_lease(intent_id="i-down", scope="TRADE_ENTRY", ttl_seconds=30.0)
            assert lease_id is None  # fail-closed: no silent fallback to local SM

            c = divergence.get_divergence_counters()
            assert c["total"] == 1  # op was compared
            # rust denied (IPC down) vs python granted (auth ACTIVE) → divergence.
            mismatches = divergence.get_mismatch_snapshot()
            assert len(mismatches) == 1
            assert mismatches[0]["rust_outcome"] == divergence.OUTCOME_DENIED
            assert mismatches[0]["python_outcome"] == divergence.OUTCOME_GRANTED

    def test_flag_on_bypass_outcome_not_counted_as_divergence(self, tmp_audit_dir):
        """Rust Bypass (Validation/Exploration profile short-circuit) → NOT
        compared (local auth-gate has no Bypass concept). total stays 0.
        Rust Bypass（profile short-circuit）→ 不比對（本地 auth-gate 無 Bypass
        概念）；total 維持 0。"""
        async def dispatcher(method, params, timeout):
            return {"lease_id": "bypass", "outcome": "Bypass"}

        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "1"}):
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            _authorize_hub(hub)
            hub.set_lease_ipc_dispatcher(dispatcher)

            lease_id = hub.acquire_lease(intent_id="i-bypass", scope="TRADE_ENTRY", ttl_seconds=30.0)
            assert lease_id == "bypass"
            # Bypass is a legitimate Rust short-circuit → excluded from divergence.
            assert divergence.get_divergence_counters()["total"] == 0

    def test_flag_on_release_records_comparison(self, tmp_audit_dir):
        """release under flag ON records a comparison; the local SM has NO opinion
        on a Rust-held lease → OUTCOME_UNKNOWN (no-opinion, A3) → counted in total
        but NOT a divergence (over-fire fix). release/get is a weak presence-echo
        channel; primary detection is the acquire-head auth-axis compare.
        flag ON 下 release 記一筆比對；本地 SM 對 Rust lease 無意見 → UNKNOWN
        （no-opinion，A3）→ 計入 total 但*不*算分歧（over-fire 修正）。release/get
        是弱通道；主分歧偵測靠 acquire 開頭的 auth-axis 比對。"""
        async def dispatcher(method, params, timeout):
            if method == "governance.release_lease":
                return {"ok": True}
            return {"lease_id": "lease:rs-3", "outcome": "Active"}

        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "1"}):
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            _authorize_hub(hub)
            hub.set_lease_ipc_dispatcher(dispatcher)

            ok = hub.release_lease(lease_id="lease:rs-held-by-rust", consumed=True)
            assert ok is True
            c = divergence.get_divergence_counters()
            assert c["total"] == 1
            # local SM has no opinion on this Rust lease → UNKNOWN no-opinion →
            # NOT a divergence (this is the A3 over-fire fix the bug exposed).
            # 本地對 Rust lease 無意見 → UNKNOWN no-opinion → 非分歧（A3 修正）。
            assert c["divergences"] == 0
            # The recorded row must be flagged no_opinion (not a true match).
            # 該筆須標記 no_opinion（非真 match），供 soak 區分。
            rows = divergence.get_divergence_snapshot()
            assert len(rows) == 1
            assert rows[0]["op"] == "release"
            assert rows[0]["python_outcome"] == divergence.OUTCOME_UNKNOWN
            assert rows[0]["no_opinion"] is True
            assert rows[0]["match"] is True  # no-opinion counts as match (not divergence)


# ═══════════════════════════════════════════════════════════════════════════════
# P5 step-(i) E2 HIGH #5 fix: acquire-head auth-axis comparator (production path)
# ═══════════════════════════════════════════════════════════════════════════════

class TestAcquireAuthAxisComparator:
    """A1: the auth-axis comparator runs at acquire-head (flag-ON, BEFORE Step-2),
    independently of the Step-2 gate, so the "Rust grants but Python auth would
    deny" divergence is OBSERVED instead of pre-filtered. These tests do NOT
    monkeypatch is_authorized — they exercise the real production path.

    A1：auth-axis 比對器在 acquire 開頭（flag-ON、Step-2 *之前*）獨立於 Step-2 跑，
    讓「Rust 授予但 Python auth 會拒」的分歧被*觀測*而非預先過濾。本組測試*不*
    monkeypatch is_authorized — 走真實 production path。"""

    def setup_method(self):
        bridge.reset_dual_write_mirror()
        divergence.reset_divergence_state()

    def test_auth_axis_rust_grants_python_denies_records_divergence_production_path(
        self, tmp_audit_dir,
    ):
        """CORE A4: Rust ``is_authorized``=True (IPC) while Python ``is_authorized()``
        =False (no ACTIVE auth) → the acquire-head auth-axis comparator records
        exactly 1 ``is_authorized`` divergence. NO monkeypatch of is_authorized:
        the divergence is captured BEFORE Step-2 (which then legitimately denies
        the acquire). This proves the comparator is no longer near-blind.

        核心 A4：Rust is_authorized=True（IPC）而 Python is_authorized()=False
        （無 ACTIVE auth）→ acquire 開頭的 auth-axis 比對器恰記 1 筆 is_authorized
        分歧。*不* monkeypatch is_authorized：分歧在 Step-2（隨後合法拒絕 acquire）
        *之前*被捕捉。證明 comparator 不再近盲。"""
        async def dispatcher(method, params, timeout):
            if method == "governance.is_authorized":
                # Rust 端授予；Python 端因無 ACTIVE auth 會拒 → 真分歧。
                return {"authorized": True}
            # acquire 不該被呼叫到（Step-2 會先 deny），給個保險回應。
            return {"lease_id": "lease:rs-x", "outcome": "Active"}

        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "1"}):
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            # NO _authorize_hub() → Python is_authorized() is naturally False.
            # 不呼叫 _authorize_hub() → Python is_authorized() 自然為 False。
            # NO is_authorized monkeypatch — real production path.
            hub.set_lease_ipc_dispatcher(dispatcher)

            # Sanity: Python really denies (so the divergence is genuine, not staged).
            assert hub.is_authorized() is False

            lease_id = hub.acquire_lease(intent_id="i-auth-div", scope="TRADE_ENTRY")
            # Step-2 legitimately denies (Python not authorized) → live behavior
            # unchanged (returns None). 但 auth-axis 分歧已在 Step-2 前被記錄。
            assert lease_id is None

            c = divergence.get_divergence_counters()
            assert c["divergences"] == 1, (
                "auth-axis comparator must capture Rust-grant/Python-deny on the "
                "production path (BEFORE Step-2), proving it is not near-blind"
            )
            mismatches = divergence.get_mismatch_snapshot()
            assert len(mismatches) == 1
            assert mismatches[0]["op"] == "is_authorized"
            assert mismatches[0]["rust_outcome"] == divergence.OUTCOME_GRANTED
            assert mismatches[0]["python_outcome"] == divergence.OUTCOME_DENIED
            assert mismatches[0]["intent_id"] == "i-auth-div"

    def test_auth_axis_agreement_no_divergence(self, tmp_audit_dir):
        """Rust is_authorized=True AND Python is_authorized()=True (ACTIVE auth) →
        auth-axis agrees → no divergence on that axis. (acquire then proceeds to
        IPC; the acquire-axis with matching outcomes also yields 0 divergence.)
        Rust=True 且 Python=True（ACTIVE auth）→ auth-axis 一致 → 該軸無分歧。"""
        async def dispatcher(method, params, timeout):
            if method == "governance.is_authorized":
                return {"authorized": True}
            return {"lease_id": "lease:rs-ok", "outcome": "Active"}

        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "1"}):
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            _authorize_hub(hub)  # Python is_authorized() → True
            hub.set_lease_ipc_dispatcher(dispatcher)

            lease_id = hub.acquire_lease(intent_id="i-agree2", scope="TRADE_ENTRY")
            assert lease_id == "lease:rs-ok"
            c = divergence.get_divergence_counters()
            # auth-axis match (1) + acquire-axis match (1) = 2 rows, 0 divergence.
            assert c["divergences"] == 0
            assert c["total"] == 2  # is_authorized compare + acquire compare

    def test_auth_axis_rust_ipc_down_skips_compare_fail_closed(self, tmp_audit_dir):
        """Rust ``is_authorized`` IPC error → is_authorized_via_ipc returns None →
        auth-axis compare SKIPS (None is "undecidable", NEVER read as granted).
        No is_authorized divergence is recorded from a dead IPC. fail-closed
        observation semantics. (The acquire IPC also fails → None, fail-closed.)
        Rust is_authorized IPC 錯誤 → 回 None → auth-axis 比對*跳過*（None=無法
        判定，絕不當授予）。死 IPC 不產生 is_authorized 分歧。"""
        async def dead_dispatcher(method, params, timeout):
            raise ConnectionError("rust engine offline")

        with patch.dict(os.environ, {bridge.LEASE_IPC_ENABLED_ENV: "1"}):
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            _authorize_hub(hub)  # Python is_authorized() → True
            hub.set_lease_ipc_dispatcher(dead_dispatcher)

            lease_id = hub.acquire_lease(intent_id="i-ipc-down", scope="TRADE_ENTRY")
            assert lease_id is None  # acquire IPC down → fail-closed

            # No is_authorized-op divergence (compare skipped on Rust None).
            # 無 is_authorized 軸分歧（Rust None → 比對跳過）。
            is_auth_rows = [
                r for r in divergence.get_divergence_snapshot()
                if r["op"] == "is_authorized"
            ]
            assert is_auth_rows == []

    def test_auth_axis_not_run_when_flag_off(self, tmp_audit_dir):
        """Flag OFF → auth-axis comparator does NOT run (byte-unchanged path);
        comparator stays silent (total=0). The dispatcher must never be hit.
        Flag OFF → auth-axis 比對器不跑（byte-unchanged）；比對器靜默（total=0）。"""
        called = []

        async def dispatcher(method, params, timeout):
            called.append(method)
            return {"authorized": True}

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(bridge.LEASE_IPC_ENABLED_ENV, None)
            hub = GovernanceHub(audit_dir=tmp_audit_dir, enabled=True)
            hub._ensure_initialized()
            _authorize_hub(hub)
            hub.set_lease_ipc_dispatcher(dispatcher)

            lease_id = hub.acquire_lease(intent_id="i-off", scope="TRADE_ENTRY")
            assert isinstance(lease_id, str) and not lease_id.startswith("SHADOW_BYPASS:")
            # Flag OFF → no IPC of any kind, comparator untouched.
            assert called == []
            assert divergence.get_divergence_counters()["total"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# P5 step-(i): is_authorized_via_ipc bridge client + schema parser unit tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestIsAuthorizedViaIpc:
    """Bridge-level unit tests for the auth-axis read client (fail-closed).
    auth-axis 唯讀 client 的 bridge 層單元測試（fail-closed）。"""

    def test_method_name_canonical(self):
        """Method constant locks the Rust dispatch arm name (drift sentinel)."""
        assert schema.METHOD_IS_AUTHORIZED == "governance.is_authorized"

    def test_happy_path_true(self):
        """Rust {"authorized": true} → True."""
        fake = _make_async_dispatcher(return_value={"authorized": True})
        assert bridge.is_authorized_via_ipc(dispatcher=fake) is True

    def test_happy_path_false(self):
        """Rust {"authorized": false} → False (a real deny, distinct from None)."""
        fake = _make_async_dispatcher(return_value={"authorized": False})
        assert bridge.is_authorized_via_ipc(dispatcher=fake) is False

    def test_wrapped_in_result(self):
        """one_shot {"result": {"authorized": true}} wrapping → True."""
        fake = _make_async_dispatcher(return_value={"result": {"authorized": True}})
        assert bridge.is_authorized_via_ipc(dispatcher=fake) is True

    def test_ipc_outage_returns_none(self):
        """Dispatcher raising → None (undecidable; NEVER True). fail-closed.
        派發器拋例外 → None（無法判定；絕不 True）。"""
        fake = _make_async_dispatcher(raise_exc=ConnectionError("down"))
        assert bridge.is_authorized_via_ipc(dispatcher=fake) is None

    def test_ipc_timeout_returns_none(self):
        """Dispatcher slower than timeout → None."""
        fake = _make_async_dispatcher(sleep=0.5)
        assert bridge.is_authorized_via_ipc(timeout_seconds=0.1, dispatcher=fake) is None

    def test_malformed_payload_returns_none(self):
        """Junk / missing key → None (undecidable)."""
        assert bridge.is_authorized_via_ipc(
            dispatcher=_make_async_dispatcher(return_value={"foo": "bar"})
        ) is None
        assert bridge.is_authorized_via_ipc(
            dispatcher=_make_async_dispatcher(return_value={})
        ) is None

    def test_non_bool_authorized_returns_none_strict(self):
        """Strict bool: "true" / 1 are NOT accepted → None (never coerced True).
        嚴格 bool："true" / 1 不接受 → None（絕不強轉 True）。"""
        assert bridge.is_authorized_via_ipc(
            dispatcher=_make_async_dispatcher(return_value={"authorized": "true"})
        ) is None
        assert bridge.is_authorized_via_ipc(
            dispatcher=_make_async_dispatcher(return_value={"authorized": 1})
        ) is None

    def test_parse_is_authorized_response_direct(self):
        """parse_is_authorized_response strict-bool contract (schema unit)."""
        assert schema.parse_is_authorized_response({"authorized": True}) is True
        assert schema.parse_is_authorized_response({"authorized": False}) is False
        assert schema.parse_is_authorized_response({"result": {"authorized": True}}) is True
        assert schema.parse_is_authorized_response({}) is None
        assert schema.parse_is_authorized_response({"authorized": "true"}) is None
        assert schema.parse_is_authorized_response({"authorized": 1}) is None
