"""governance_ipc_canary 單元測試（P5-SM-OPTION2 step-(i) soak 第二輪，E1-C）。

MODULE_NOTE:
    覆蓋 PM 五條引擎 fire 機率硬防護（`2026-06-10--p5sm_soak_cadence_decision.md`），
    **每條各帶負向測試**：
      1. single-flight + 2s timeout + 失敗不立即重試（in_flight 守衛跳過不計數 /
         單拍 dispatcher 恰被呼叫 2 次 / timeout 計 fail）。
      2. jitter ±10%（樣本全落 [0.9, 1.1]×interval 且非常數）。
      3. fail-backoff 連敗 ≥10 → max(配置, 300s)、只降頻不加頻、恢復即退出；
         9 連敗**不**觸發（負向）。
      4. kill-switch 默認 OFF（env 未設不 probe）、嚴格 "1"、循環中翻 OFF 即退出。
      5. O(1) 唯讀（0 mutation：tokenize 剝註解/字串後 0 acquire/release 引用）+
         leader 複用 flusher 同一把 flock（同進程不變量）+ 正常拍只 log DEBUG。
    另覆蓋：結構驗證軸（probe-1 strict bool / probe-2 必備鍵+型別+bool-是-int
    陷阱 + 真實 serde PascalCase payload）、15min 失敗連段 breach（時間語義 +
    每連段至多一次 + 成功重置）、attempts==ok+fail 不變量、cadence env 解析
    （含 E4 1s 注入鉤子）、loop 端到端（0.01s 注入 + cancellation）。

    無 pytest-asyncio 依賴：async 入口以 asyncio.run 直驅（對齊既有 route
    auth-matrix 測法）。無真 IPC / PG / engine（dispatcher 全注入）。
"""
from __future__ import annotations

import asyncio
import io
import logging
import tokenize
from typing import Any, Mapping

import pytest

from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (
    governance_divergence_flush as flush_mod,
    governance_ipc_canary as canary,
    lease_ipc_schema as schema,
)


@pytest.fixture(autouse=True)
def _reset_canary() -> Any:
    """每個 test 前後清空 canary 計數器/狀態（測試隔離）。"""
    canary.reset_canary_state_for_tests()
    yield
    canary.reset_canary_state_for_tests()


# ─────────────────────────────────────────────────────────────────────────────
# 測試用 dispatcher / payload helpers
# ─────────────────────────────────────────────────────────────────────────────

# 真實 serde wire 形狀（E1 親證：GovernanceStatus derive 無 rename_all →
# PascalCase 變體名；auth_pending_approval 由 handle_get_gov_status 注入）。
_REAL_STATUS_PAYLOAD: dict[str, Any] = {
    "enabled": True,
    "mode": "Normal",
    "risk_level": "Normal",
    "auth_effective_count": 1,
    "auth_pending_approval": 0,
    "lease_live_count": 0,
    "oms_active_count": 0,
}


class _FakeDispatcher:
    """可程式化假 dispatcher：按 method 回 payload / 拋例外 / 睡眠，並記呼叫。"""

    def __init__(
        self,
        *,
        is_authorized: Any = None,
        get_status: Any = None,
        raise_exc: Exception | None = None,
        sleep_s: float = 0.0,
    ) -> None:
        self.is_authorized = (
            {"authorized": True} if is_authorized is None else is_authorized
        )
        self.get_status = (
            dict(_REAL_STATUS_PAYLOAD) if get_status is None else get_status
        )
        self.raise_exc = raise_exc
        self.sleep_s = sleep_s
        self.calls: list[str] = []

    async def __call__(
        self, method: str, params: Mapping[str, Any], timeout: float
    ) -> Mapping[str, Any]:
        self.calls.append(method)
        if self.sleep_s:
            await asyncio.sleep(self.sleep_s)
        if self.raise_exc is not None:
            raise self.raise_exc
        if method == schema.METHOD_IS_AUTHORIZED:
            return self.is_authorized
        if method == schema.METHOD_GET_STATUS:
            return self.get_status
        raise AssertionError(f"unexpected method: {method}")


def _run_tick(dispatcher: Any) -> Any:
    return asyncio.run(canary.run_canary_tick(dispatcher))


# ─────────────────────────────────────────────────────────────────────────────
# 防護 1：single-flight + 2s timeout + 失敗不立即重試
# ─────────────────────────────────────────────────────────────────────────────


def test_single_flight_guard_skips_overlapping_tick_without_counting() -> None:
    """in-flight 期間重入 tick → 回 None 且**不計數**（雙排程不可放大 IPC 負載）。"""
    with canary._CANARY_LOCK:
        canary._CANARY_STATE["in_flight"] = True
    result = _run_tick(_FakeDispatcher())
    assert result is None
    assert canary.get_canary_counters()["attempts"] == 0  # 跳過拍不污染統計


def test_single_flight_negative_normal_tick_counts() -> None:
    """負向對照：無 in-flight 時正常拍計數（守衛不誤殺正常路徑）。"""
    assert _run_tick(_FakeDispatcher()) is True
    assert canary.get_canary_counters()["attempts"] == 1


def test_in_flight_flag_cleared_even_on_dispatcher_exception() -> None:
    """dispatcher 拋例外後 in_flight 必清（finally）——否則 canary 永久自鎖死。"""
    _run_tick(_FakeDispatcher(raise_exc=RuntimeError("ipc boom")))
    assert canary.get_canary_runtime_state()["in_flight"] is False


def test_probes_sequential_one_dispatcher_call_per_probe_no_retry() -> None:
    """單拍恰好 2 次 dispatch（probe-1 + probe-2），失敗**不在拍內重試**（防護 1）。"""
    d = _FakeDispatcher(raise_exc=RuntimeError("ipc down"))
    result = _run_tick(d)
    assert result is False
    # 兩個 probe 各一次；若有立即重試會 >2（retry storm 是唯一真實風險源）。
    assert d.calls == [schema.METHOD_IS_AUTHORIZED, schema.METHOD_GET_STATUS]


def test_probe_timeout_counts_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """probe 超時 → 該拍計 fail（fail-closed），不上拋、不重試。"""
    monkeypatch.setattr(canary, "PROBE_TIMEOUT_SECONDS", 0.05)
    d = _FakeDispatcher(sleep_s=0.5)  # 比 timeout 慢 → wait_for 觸發
    result = _run_tick(d)
    assert result is False
    counters = canary.get_canary_counters()
    assert counters["fail"] == 1
    assert counters["attempts"] == 1
    assert d.calls == [schema.METHOD_IS_AUTHORIZED, schema.METHOD_GET_STATUS]


# ─────────────────────────────────────────────────────────────────────────────
# 防護 2：jitter ±10%
# ─────────────────────────────────────────────────────────────────────────────


def test_jitter_bounded_within_10pct_and_varies() -> None:
    """jitter 樣本全落 [0.9, 1.1]×interval 且非常數（防鎖相）。"""
    samples = [canary._jittered(120.0) for _ in range(200)]
    assert all(108.0 <= s <= 132.0 for s in samples)
    assert len({round(s, 6) for s in samples}) > 1  # 非常數


# ─────────────────────────────────────────────────────────────────────────────
# 防護 3：fail-backoff（連敗 ≥10 → max(配置, 300s)；只降頻不加頻）
# ─────────────────────────────────────────────────────────────────────────────


def _drive_failures(n: int) -> None:
    d = _FakeDispatcher(raise_exc=RuntimeError("down"))
    for _ in range(n):
        _run_tick(d)


def test_backoff_engages_at_10_consecutive_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(canary.CANARY_INTERVAL_ENV, "120")
    _drive_failures(10)
    assert canary.get_canary_runtime_state()["in_backoff"] is True
    assert canary._effective_interval_seconds() == 300.0


def test_backoff_negative_9_failures_not_engaged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """負向：9 連敗不退頻（閾值是 ≥10）。"""
    monkeypatch.setenv(canary.CANARY_INTERVAL_ENV, "120")
    _drive_failures(9)
    assert canary.get_canary_runtime_state()["in_backoff"] is False
    assert canary._effective_interval_seconds() == 120.0


def test_backoff_never_speeds_up_when_configured_slower(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """配置 600s 時退頻取 max(600, 300)=600 —— 失敗路徑**只降頻不加頻**。"""
    monkeypatch.setenv(canary.CANARY_INTERVAL_ENV, "600")
    _drive_failures(10)
    assert canary._effective_interval_seconds() == 600.0


def test_backoff_recovery_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """退頻後一次成功拍 → 退出 backoff、回配置頻率。"""
    monkeypatch.setenv(canary.CANARY_INTERVAL_ENV, "120")
    _drive_failures(10)
    assert canary.get_canary_runtime_state()["in_backoff"] is True
    _run_tick(_FakeDispatcher())  # 成功拍
    assert canary.get_canary_runtime_state()["in_backoff"] is False
    assert canary._effective_interval_seconds() == 120.0
    assert canary.get_canary_runtime_state()["consecutive_failures"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 防護 4：kill-switch（默認 OFF；嚴格 "1"；循環中翻 OFF 即退出）
# ─────────────────────────────────────────────────────────────────────────────


def test_kill_switch_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(canary.CANARY_ENABLED_ENV, raising=False)
    assert canary.is_canary_enabled() is False


@pytest.mark.parametrize("val", ["true", "yes", "ON", "0", "", " 1"])
def test_kill_switch_strict_equality(
    monkeypatch: pytest.MonkeyPatch, val: str
) -> None:
    """嚴格 "1"：其他值一律 OFF（負向；對齊 lease flag 嚴格等值慣例）。"""
    monkeypatch.setenv(canary.CANARY_ENABLED_ENV, val)
    assert canary.is_canary_enabled() is False


def test_loop_disabled_does_not_probe_or_elect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """kill-switch OFF → loop 立即返回：0 leadership、0 probe（默認休眠）。"""
    monkeypatch.delenv(canary.CANARY_ENABLED_ENV, raising=False)
    elected = {"called": False}

    def _fake_leader() -> bool:
        elected["called"] = True
        return True

    monkeypatch.setattr(canary, "_acquire_canary_leadership", _fake_leader)
    asyncio.run(canary.governance_ipc_canary_loop(_FakeDispatcher()))
    assert elected["called"] is False
    assert canary.get_canary_counters()["attempts"] == 0


def test_loop_kill_switch_flip_off_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    """循環中 env 翻 OFF → loop 自行退出（kill-switch 語義 = 立即可殺）。"""
    monkeypatch.setenv(canary.CANARY_ENABLED_ENV, "1")
    monkeypatch.setenv(canary.CANARY_INTERVAL_ENV, "0.01")
    monkeypatch.setattr(canary, "_acquire_canary_leadership", lambda: True)
    d = _FakeDispatcher()

    async def _main() -> None:
        task = asyncio.create_task(canary.governance_ipc_canary_loop(d))
        # 等至少跑出 1 拍後翻 OFF。
        for _ in range(200):
            await asyncio.sleep(0.01)
            if canary.get_canary_counters()["attempts"] >= 1:
                break
        monkeypatch.setenv(canary.CANARY_ENABLED_ENV, "0")
        await asyncio.wait_for(task, timeout=5.0)  # 自行退出（非 cancel）

    asyncio.run(_main())
    assert canary.get_canary_counters()["attempts"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# 防護 5：O(1) 唯讀（0 mutation）+ leader 同鎖 + DEBUG 級 log
# ─────────────────────────────────────────────────────────────────────────────


def _code_only_tokens(source: str) -> str:
    """剝 COMMENT + STRING token 只留真碼（grep 鐵則：docstring 合法提及禁字
    不可誤紅；同 L2 P2 carbon-layer 測法）。"""
    out: list[str] = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        out.append(tok.string)
    return " ".join(out)


def test_zero_mutation_no_acquire_release_in_code() -> None:
    """鐵則：canary 真碼 0 個 acquire/release 引用（剝註解/字串後驗證）。

    raw grep 會被 MODULE_NOTE 的「0 個 acquire_lease ... 引用」合法散文誤紅，
    故剝 token；wire 字面（governance.acquire_lease）在 STRING token 內，剝後
    若還出現代表有人把方法名寫成裸識別字 = 真碼引用 → 紅。
    """
    import inspect

    src = inspect.getsource(canary)
    code = _code_only_tokens(src)
    assert "METHOD_ACQUIRE_LEASE" not in code
    assert "METHOD_RELEASE_LEASE" not in code
    assert "acquire_lease_via_ipc" not in code
    assert "release_lease_via_ipc" not in code
    # 正向自證（mutation bite 防自欺）：唯讀方法常數在真碼中存在。
    assert "METHOD_IS_AUTHORIZED" in code
    assert "METHOD_GET_STATUS" in code


def test_zero_mutation_no_wire_literals_in_strings() -> None:
    """補強：全 source（含字串）也不得出現 mutating wire 字面。

    canary 不該以任何形式（哪怕字串拼接）構造 mutating 方法名；本模組的散文
    僅以底線識別字形式提及 acquire_lease（無 governance. 前綴），故此 raw 檢查
    不會誤紅。
    """
    import inspect

    src = inspect.getsource(canary)
    assert "governance.acquire_lease" not in src
    assert "governance.release_lease" not in src


def test_leadership_reuses_flusher_flock(monkeypatch: pytest.MonkeyPatch) -> None:
    """leader 複用 flusher 的同一把 flock（load-bearing：同進程才能被 flush）。"""
    calls = {"n": 0}

    def _fake_lock() -> bool:
        calls["n"] += 1
        return True

    monkeypatch.setattr(flush_mod, "_acquire_flusher_leader_lock", _fake_lock)
    assert canary._acquire_canary_leadership() is True
    assert calls["n"] == 1

    monkeypatch.setattr(flush_mod, "_acquire_flusher_leader_lock", lambda: False)
    assert canary._acquire_canary_leadership() is False


def test_loop_non_leader_does_not_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """非 leader worker：不 probe（負向；單 prober 防護）。"""
    monkeypatch.setenv(canary.CANARY_ENABLED_ENV, "1")
    monkeypatch.setattr(canary, "_acquire_canary_leadership", lambda: False)
    asyncio.run(canary.governance_ipc_canary_loop(_FakeDispatcher()))
    assert canary.get_canary_counters()["attempts"] == 0


def test_normal_tick_logs_debug_only(caplog: pytest.LogCaptureFixture) -> None:
    """正常拍只 log DEBUG（防護 5：不洗 log）；WARN 僅限連段/退頻事件。"""
    with caplog.at_level(logging.DEBUG, logger=canary.logger.name):
        _run_tick(_FakeDispatcher())
    records = [r for r in caplog.records if r.name == canary.logger.name]
    assert records, "正常拍應有 DEBUG 紀錄"
    assert all(r.levelno <= logging.DEBUG for r in records)


# ─────────────────────────────────────────────────────────────────────────────
# 結構驗證軸（probe-1 strict bool / probe-2 必備鍵+型別）
# ─────────────────────────────────────────────────────────────────────────────


def test_probe1_strict_bool_false_is_still_structurally_ok() -> None:
    """authorized=False 是**結構健康**（授權與否不是 canary 判定軸）。"""
    assert _run_tick(_FakeDispatcher(is_authorized={"authorized": False})) is True


@pytest.mark.parametrize(
    "payload",
    [
        {"authorized": "true"},   # 字串非 strict bool
        {"authorized": 1},        # int 非 strict bool
        {},                       # 缺鍵
        "pong",                   # 非 Mapping
    ],
)
def test_probe1_malformed_counts_fail(payload: Any) -> None:
    assert _run_tick(_FakeDispatcher(is_authorized=payload)) is False
    assert canary.get_canary_counters()["fail"] == 1


def test_probe2_real_serde_shape_passes() -> None:
    """真實 serde PascalCase payload（"Normal"）通過——不釘 UPPERCASE。"""
    assert _run_tick(_FakeDispatcher(get_status=dict(_REAL_STATUS_PAYLOAD))) is True


def test_probe2_wrapped_result_shell_accepted() -> None:
    """one_shot 對非 dict 的 {"result": ...} 包裝形狀也接受（與既有 parser 慣例同）。"""
    wrapped = {"result": dict(_REAL_STATUS_PAYLOAD)}
    assert _run_tick(_FakeDispatcher(get_status=wrapped)) is True


@pytest.mark.parametrize(
    "mutator",
    [
        lambda p: p.pop("mode"),                                  # 缺鍵
        lambda p: p.__setitem__("mode", ""),                      # 空字串
        lambda p: p.__setitem__("enabled", "true"),               # 非 strict bool
        lambda p: p.__setitem__("lease_live_count", True),        # bool-是-int 陷阱
        lambda p: p.__setitem__("auth_effective_count", -1),      # 負數
        lambda p: p.__setitem__("oms_active_count", "5"),         # 字串計數
        lambda p: p.pop("auth_pending_approval"),                 # 注入欄缺失
    ],
)
def test_probe2_structural_violations_count_fail(mutator: Any) -> None:
    payload = dict(_REAL_STATUS_PAYLOAD)
    mutator(payload)
    assert _run_tick(_FakeDispatcher(get_status=payload)) is False


def test_parse_get_status_response_direct() -> None:
    """parser 直驅：合法回正規化 dict；畸形回 None。"""
    out = schema.parse_get_status_response(_REAL_STATUS_PAYLOAD)
    assert out is not None
    assert out["mode"] == "Normal"
    assert schema.parse_get_status_response({"enabled": True}) is None
    assert schema.parse_get_status_response("nope") is None  # type: ignore[arg-type]


# ─────────────────────────────────────────────────────────────────────────────
# 失敗連段（S3：≥15min 牆鐘語義）
# ─────────────────────────────────────────────────────────────────────────────


class _MonoClock:
    """可推進的假 monotonic 時鐘。"""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_fail_streak_breach_at_15min(monkeypatch: pytest.MonkeyPatch) -> None:
    """失敗連段跨 15min → breaches +1 + WARN SM_IPC_CANARY_DOWN（一次）。"""
    clock = _MonoClock()
    monkeypatch.setattr(canary, "_monotonic", clock)
    d = _FakeDispatcher(raise_exc=RuntimeError("down"))

    _run_tick(d)            # t=1000 連段起點
    clock.now += 901.0      # 跨 15min
    _run_tick(d)
    assert canary.get_canary_counters()["fail_streak_breaches"] == 1


def test_fail_streak_negative_under_15min_no_breach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """負向：連段 <15min 不 breach（散發失敗不算連段）。"""
    clock = _MonoClock()
    monkeypatch.setattr(canary, "_monotonic", clock)
    d = _FakeDispatcher(raise_exc=RuntimeError("down"))
    _run_tick(d)
    clock.now += 600.0  # 10min < 15min
    _run_tick(d)
    assert canary.get_canary_counters()["fail_streak_breaches"] == 0


def test_fail_streak_breach_once_per_streak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同一連段持續惡化也只 breach 一次（防 WARN 洗版 + [82] 重複計段）。"""
    clock = _MonoClock()
    monkeypatch.setattr(canary, "_monotonic", clock)
    d = _FakeDispatcher(raise_exc=RuntimeError("down"))
    _run_tick(d)
    clock.now += 901.0
    _run_tick(d)
    clock.now += 901.0
    _run_tick(d)  # 同連段更深
    assert canary.get_canary_counters()["fail_streak_breaches"] == 1


def test_fail_streak_resets_on_success_then_new_streak_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """成功拍重置連段；新連段再跨 15min 可再 breach（每段獨立計）。"""
    clock = _MonoClock()
    monkeypatch.setattr(canary, "_monotonic", clock)
    bad = _FakeDispatcher(raise_exc=RuntimeError("down"))

    _run_tick(bad)
    clock.now += 901.0
    _run_tick(bad)               # 第一段 breach
    _run_tick(_FakeDispatcher())  # 成功 → 重置
    _run_tick(bad)               # 第二段起點
    clock.now += 901.0
    _run_tick(bad)               # 第二段 breach
    assert canary.get_canary_counters()["fail_streak_breaches"] == 2


def test_streak_warn_emitted(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """breach 時發 WARN ``SM_IPC_CANARY_DOWN``（soak 收口可 grep）。"""
    clock = _MonoClock()
    monkeypatch.setattr(canary, "_monotonic", clock)
    d = _FakeDispatcher(raise_exc=RuntimeError("down"))
    with caplog.at_level(logging.WARNING, logger=canary.logger.name):
        _run_tick(d)
        clock.now += 901.0
        _run_tick(d)
    assert any("SM_IPC_CANARY_DOWN" in r.getMessage() for r in caplog.records)


# ─────────────────────────────────────────────────────────────────────────────
# 計數器不變量 + getter 契約
# ─────────────────────────────────────────────────────────────────────────────


def test_counters_invariant_attempts_eq_ok_plus_fail() -> None:
    """attempts == ok + fail 恆成立（V129 CHECK total>=matches+divergences 天然滿足）。"""
    good = _FakeDispatcher()
    bad = _FakeDispatcher(raise_exc=RuntimeError("down"))
    for d in (good, bad, good, bad, bad, good):
        _run_tick(d)
    c = canary.get_canary_counters()
    assert c["attempts"] == 6
    assert c["ok"] == 3
    assert c["fail"] == 3
    assert c["attempts"] == c["ok"] + c["fail"]


def test_get_canary_counters_returns_defensive_copy() -> None:
    """getter 回防禦性副本（PA 鎖定契約 dict[str,int]；caller 改不動內部）。"""
    _run_tick(_FakeDispatcher())
    snap = canary.get_canary_counters()
    assert all(isinstance(v, int) for v in snap.values())
    snap["attempts"] = 9999
    assert canary.get_canary_counters()["attempts"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# cadence env 解析（含 E4 1s 注入鉤子）
# ─────────────────────────────────────────────────────────────────────────────


def test_interval_default_120(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(canary.CANARY_INTERVAL_ENV, raising=False)
    assert canary._canary_interval_seconds() == 120.0


def test_interval_e4_1s_injection_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    """E4 對抗壓測鉤子：env=1 → 1s 極端頻率可注入（120× 設計頻率）。"""
    monkeypatch.setenv(canary.CANARY_INTERVAL_ENV, "1")
    assert canary._canary_interval_seconds() == 1.0


@pytest.mark.parametrize("raw", ["abc", "-5", "0", ""])
def test_interval_invalid_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """無效 cadence → fail-safe 回默認 120s（配置錯不可讓觀測靜默消失）。"""
    monkeypatch.setenv(canary.CANARY_INTERVAL_ENV, raw)
    assert canary._canary_interval_seconds() == 120.0


# ─────────────────────────────────────────────────────────────────────────────
# loop 端到端（1s 級注入 + cancellation）
# ─────────────────────────────────────────────────────────────────────────────


def test_loop_end_to_end_probes_and_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """enabled + leader + 0.01s 注入 → 累積 ≥2 拍；cancel 乾淨退出。"""
    monkeypatch.setenv(canary.CANARY_ENABLED_ENV, "1")
    monkeypatch.setenv(canary.CANARY_INTERVAL_ENV, "0.01")
    monkeypatch.setattr(canary, "_acquire_canary_leadership", lambda: True)
    d = _FakeDispatcher()

    async def _main() -> None:
        task = asyncio.create_task(canary.governance_ipc_canary_loop(d))
        for _ in range(500):
            await asyncio.sleep(0.01)
            if canary.get_canary_counters()["attempts"] >= 2:
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(_main())
    c = canary.get_canary_counters()
    assert c["attempts"] >= 2
    assert c["ok"] == c["attempts"]
