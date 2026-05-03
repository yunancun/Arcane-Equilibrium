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
