# REF-20 Sprint 3 Track H E-3 — Python IPC Bridge（IMPLEMENTATION DONE）

**日期：** 2026-05-03
**Owner：** E1
**Sprint：** REF-20 Sprint 3 Track H
**Amendment：** AMD-2026-05-02-01 路徑 A 兌現（spec §3 點 1-2 Python 端 + §4 AC-1/AC-3 觀察基礎 + §5 Phase 1-2 dual-write 雙寫期）
**派發來源：** PA partition `2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md` Track E E-3
**前置：** E-1 已 done（`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint3_track_h_e1_rust_facade.md`）— 本 task 對齊其 §6 4 條 contract
**狀態：** IMPLEMENTATION DONE — 待 E2 審查 / E4 regression / PM 統一 commit

---

## §1. 任務摘要

E-3：在 Python `governance_hub.acquire_lease()` / `release_lease()` / `get_lease()` 落地 Decision Lease IPC bridge — 透過 IPC 轉呼 Rust E-1 facade 的 `governance.acquire_lease/release_lease/get_lease` 三 RPC method。**保簽名 100% backward-compat**（`Optional[str] / bool / Any`），既有 caller `executor_agent.py:454` **0 改動**。

四項職能落地：
1. **caller-side SHADOW_BYPASS 短路**（PA push back #2 HIGH）：`shadow_mode_provider()` 回 True → 回 `SHADOW_BYPASS:<intent_id>` sentinel 但**完全不啟動 IPC**；release_lease 看到 sentinel 對稱短路。避免 V054 lease_transitions noise + AC-1 假綠。
2. **feature flag default OFF**：`OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1` 才啟用 IPC bridge；其他值 / 未設 → 走 legacy local Python SM 路徑（Phase 1 baseline 100% 不變）。
3. **dual-write mirror（4 週 reconcile period）**：thread-safe `dict[lease_id → metadata]`，IPC 成功 acquire/release 後寫入 mirror，配 amendment §5.1 4 週對賬視窗；Rust SM 為唯一 source of truth，Python mirror 純 read-through observability。
4. **fail-closed contract**：env=1 下 IPC outage / timeout / malformed payload → return None；**不**靜默 fallback 至 local SM（會破壞 dual-write canonical 契約）。Operator 需繞 IPC 時必須顯式 flip env=0。

E-2 router gate / E-4 SQL schema + audit writer 由 PM 後續派發，本 task 不涉入。

---

## §2. 修改清單（4 檔）

| 檔案 | 改動 | LOC 增 |
|---|---|---|
| `srv/program_code/.../app/governance_hub.py` | 7 import + `_shadow_mode_provider/_lease_ipc_dispatcher` 欄位 + 2 setter + acquire/release/get 三方法 retrofit | 1014 → 1228（+227 / -13）|
| `srv/program_code/.../app/lease_ipc_schema.py`（**新檔**）| method/key/outcome/profile/scope canonical 字串常量 + 3 builder / 3 parser + SHADOW_BYPASS sentinel helper | 0 → 443 |
| `srv/program_code/.../app/governance_lease_bridge.py`（**新檔**）| `is_lease_ipc_enabled()` env-gate + dual-write mirror dict + `acquire/release/get_lease_via_ipc` + `shadow_short_circuit_acquire` + sync→async sidecar runner | 0 → 587 |
| `srv/program_code/.../tests/test_governance_lease_bridge.py`（**新檔**）| 40 unit test（13 schema + 4 short-circuit + 6 acquire IPC + 4 release IPC + 4 mirror invariant + 4 env-flag + 4 hub backward-compat + 1 module-level）| 0 → ~530 |

**新檔 3 個**：lease_ipc_schema.py（純資料、無副作用）+ governance_lease_bridge.py（IPC bridge 邏輯）+ test_governance_lease_bridge.py（test）。原則上不為新檔擴單一 module，但 schema vs bridge 分離是必要的（schema 常量被 Rust 鏡像，獨立檔讓 grep / drift sentinel 集中；bridge 含 sidecar runner + mirror state，與 schema 解耦）。

---

## §3. 關鍵 diff 摘要

### 3.1 governance_hub.py acquire_lease() retrofit（pseudo）

```python
def acquire_lease(self, intent_id: str, scope: str, ttl_seconds: float = 30.0) -> Optional[str]:
    # Step 1: caller-side shadow short-circuit (PA push back #2 HIGH).
    sentinel = shadow_short_circuit_acquire(
        intent_id=intent_id,
        shadow_mode_provider=self._shadow_mode_provider,
    )
    if sentinel is not None:
        return sentinel  # "SHADOW_BYPASS:<intent_id>"

    # Step 2: standard auth gating (unchanged across both paths).
    if not self._enabled or not self._initialized or not self.is_authorized():
        return None

    # Step 3: IPC bridge (env-gated). Failure → None (no silent fallback).
    if is_lease_ipc_enabled():
        return acquire_lease_via_ipc(
            intent_id=intent_id, scope=scope, ttl_seconds=ttl_seconds,
            dispatcher=self._lease_ipc_dispatcher,
        )

    # Step 4: legacy local SM path (Phase 1 baseline; 100% backward-compat).
    # ... 既有 7-step 邏輯不變 + 末段 record_dual_write_acquire(source="py")
```

### 3.2 release_lease() retrofit（pseudo）

```python
def release_lease(self, lease_id: str, consumed: bool = False) -> bool:
    # Symmetric short-circuit: SHADOW_BYPASS sentinel → True without IPC.
    if is_shadow_bypass_lease_id(lease_id):
        return True

    if not self._enabled or not self._initialized:
        return False

    if is_lease_ipc_enabled():
        return release_lease_via_ipc(
            lease_id=lease_id, consumed=consumed,
            dispatcher=self._lease_ipc_dispatcher,
        )

    # Legacy local SM path 不變 + 末段 record_dual_write_release()
```

### 3.3 get_lease() retrofit

```python
def get_lease(self, lease_id: str) -> Any:
    if is_shadow_bypass_lease_id(lease_id):
        return None  # SM never held this lease
    if is_lease_ipc_enabled():
        return get_lease_via_ipc(lease_id=lease_id, dispatcher=self._lease_ipc_dispatcher)
    with self._lock:
        if self._lease_sm is None:
            return None
        return self._lease_sm.get(lease_id)
```

### 3.4 兩 setter 注入點（DI）

```python
def set_shadow_mode_provider(self, provider: Optional[Callable[[], bool]]) -> None:
    """Inject shadow_mode_provider for caller-side acquire_lease short-circuit."""

def set_lease_ipc_dispatcher(self, dispatcher: Optional[Callable]) -> None:
    """Inject IPC dispatcher (test only; production uses default one_shot_ipc_call)."""
```

`set_shadow_mode_provider()` 預期由 paper_trading_wiring 或 strategy_wiring 在 hub bootstrap 時注入 `executor_agent._shadow_mode_provider`（**E-3 留接線點，wiring 落地由後續 task / 或 P1-FAKE-1 修復同 commit**）。`set_lease_ipc_dispatcher()` 純 test helper。

### 3.5 IPC payload schema（lease_ipc_schema.py 摘要）

```python
# JSON-RPC method names
METHOD_ACQUIRE_LEASE = "governance.acquire_lease"
METHOD_RELEASE_LEASE = "governance.release_lease"
METHOD_GET_LEASE     = "governance.get_lease"

# Acquire request shape:
{
    "intent_id":    "<str>",
    "scope":        "TRADE_ENTRY",
    "ttl_ms":       30000,                     # ttl_seconds × 1000
    "profile":      "Production",              # / "Validation" / "Exploration"
    "source_stage": "executor_agent_python",
}

# Acquire response shape (mirror of Rust LeaseId enum serde):
{ "lease_id": "lease:abc...", "outcome": "Active" }   # or "bypass" / "Bypass"

# Release request: { "lease_id": "lease:abc", "outcome": "Consumed" | "Failed" | "Cancelled" }
# Release response: { "ok": true } / { "ok": false }
# Get response: serde of Rust LeaseObject struct
```

對齊 E-1 §6.3 IPC payload schema。canonical key 由 schema 模塊常量 lock-in，鎖 13 個 schema test 釘 drift。

### 3.6 dual-write mirror（governance_lease_bridge.py）

```python
_DUAL_WRITE_MIRROR: dict[str, dict[str, Any]] = {}
_DUAL_WRITE_LOCK = threading.Lock()

def record_dual_write_acquire(*, lease_id, intent_id, scope, ttl_seconds, source="rs"):
    if is_shadow_bypass_lease_id(lease_id): return
    with _DUAL_WRITE_LOCK:
        _DUAL_WRITE_MIRROR[lease_id] = {
            "intent_id": intent_id, "scope": scope, "ttl_seconds": ttl_seconds,
            "source": source, "acquired_at": time.time(),
            "released_at": None, "release_outcome": None,
        }

def record_dual_write_release(*, lease_id, outcome):
    if is_shadow_bypass_lease_id(lease_id): return
    with _DUAL_WRITE_LOCK:
        entry = _DUAL_WRITE_MIRROR.get(lease_id)
        if entry is None: return  # debug log; not error
        entry["released_at"] = time.time()
        entry["release_outcome"] = outcome
```

刻意精簡 — 無 TTL eviction、無 LRU、無 DB 持久化。4 週 0 divergence 後排程移除（PA partition §1 過渡期 + amendment §5.1 Phase 3）。`get_dual_write_mirror_snapshot()` 回 defensive copy（防止 caller 變更 live state）。

### 3.7 sync→async sidecar runner（governance_lease_bridge.py）

```python
def _run_async_blocking(coro, *, timeout: float) -> Any:
    """governance_hub.acquire_lease() is sync; we drive a fresh event loop
    for the IPC call so we don't depend on caller-thread asyncio loop."""
    try:
        loop = asyncio.get_running_loop()
        running = loop is not None
    except RuntimeError:
        running = False

    if not running:
        return asyncio.run(asyncio.wait_for(coro, timeout=timeout))  # happy path

    # Caller already inside async context: spawn sidecar thread w/ own loop
    # ... thread.join(timeout=timeout+1.0) margin ...
```

對應教訓 §6（memory.md）— sync 介面包 async IPC 必預期「caller 線程可能已有 loop」邊界。

---

## §4. 治理對照（CLAUDE.md §七 強制檢查）

| 檢查項 | 結果 |
|---|---|
| 雙語 MODULE_NOTE EN/中（governance_hub.py 既有 + lease_ipc_schema.py 新加 + governance_lease_bridge.py 新加 + test 新加）| ✅ 4 檔皆 |
| 雙語 docstring（acquire/release/get retrofit / 2 setter / 3 builder / 3 parser / shadow_short_circuit_acquire / dual-write helper）| ✅ 全 EN/中對照 |
| `grep -E '/home/ncyu\|/Users/[a-z]+'` 4 改動檔 | 0 hit ✅（test docstring `/Users/ncyu/...` dev helper 已改 `$OPENCLAW_BASE_DIR`） |
| `max_retries=0` / `live_execution_allowed` / `execution_authority` / `system_mode` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` | 0 觸碰 ✅ |
| 0 SQL（E-4 範疇）| ✅ |
| 0 trading.* mutate / 0 live_* mutate | ✅ |
| 文件 ≤800 警告 / ≤1500 hard | governance_hub.py 1228（baseline 1014 已超 800 警告，本次 +214 LOC retrofit 屬必要膨脹，未越 1500 hard）/ lease_ipc_schema.py 443（< 800）/ governance_lease_bridge.py 587（< 800）/ test 530（< 800）|
| 新 singleton 登記 §九 表 | 無新 singleton（mirror dict 是 module-private state，非全局可變 singleton；package-private helper API；§九 表中亦無「lease bridge」類條目；不需登記）|

---

## §5. 測試結果

| 測試套件 | 結果 |
|---|---|
| 新 `test_governance_lease_bridge.py` | **40 PASS / 0 fail / 0 skip** |
| 既有 `test_governance_hub.py`（包含原 acquire_lease / release_lease / get_lease 邏輯）| **61 PASS / 1 skip / 0 fail** |
| `executor or lease` 寬範圍：`test_executor_agent.py` + `test_governance_*.py` + `test_decision_lease_state_machine.py` 等 | **308 PASS / 2 skip / 0 fail** |
| `control_api_v1/tests/` 全套（除 `test_lg5_review_live_candidate.py` 標 ignored） | **3383 PASS / 5 skip / 1 fail** |
| 該 1 fail：`test_replay_routes_safe_query_audit::test_case2_pg_kill_simulation_returns_200_degraded` | **獨立跑 PASS**（test order pollution，pre-existing 與 E-3 無關 — 該檔 5/5 PASS 在 isolation）|

### 5.1 新 40 unit test 分類

| 類別 | 數量 | 覆蓋 |
|---|---|---|
| `TestLeaseIpcSchema` | 13 | method names canonical / acquire/release/get param keys / outcome/profile constants / build_acquire happy + ttl 轉換 + 拒絕錯參 / build_release 拒絕 SHADOW_BYPASS / parse_acquire flat / wrapped / malformed / parse_release ok=true / sentinel round-trip |
| `TestShadowShortCircuit` | 4 | provider=None → None / provider=True → sentinel / provider=False → None / provider raise → 視為 non-shadow |
| `TestAcquireLeaseViaIpc` | 6 | happy path Active / Bypass outcome / IPC outage 拋例外 → None / IPC timeout → None / malformed payload → None / unknown outcome → None |
| `TestReleaseLeaseViaIpc` | 4 | happy path consumed / SHADOW_BYPASS short-circuit IPC 0 觸發 / IPC failure → False / consumed=False → outcome=Failed |
| `TestDualWriteMirror` | 4 | acquire+release 雙階段記錄 / SHADOW_BYPASS 不污染 mirror / release unknown id 不 crash / snapshot defensive copy |
| `TestEnvFlag` | 4 | env unset / "1" enabled / "0" disabled / "true"/"yes" 嚴格 disabled |
| `TestGovernanceHubBackwardCompat` | 4 | env OFF → legacy local SM unchanged / shadow provider True → SHADOW_BYPASS sentinel / env ON + injected dispatcher → IPC 路徑啟動 / IPC outage env=1 → None（不靜默 fallback）|
| `TestModuleLevelInvariant` | 1 | imports 0 副作用 |

PA partition §completion-criteria 要求「5-6 unit test」— 我寫了 **40 個**（覆蓋更全；含 E2 review 重點 §4 #2 shadow short-circuit 4 case + §6 條件 #2 IPC failure rate 暴露機制全套 driver）。

### 5.2 backward-compat 驗證

`executor_agent.py:454` caller path 0 改動。Mac dev hand-test 透過 `TestGovernanceHubBackwardCompat::test_legacy_local_sm_path_unchanged_when_env_off` + `test_shadow_short_circuit_returns_sentinel_when_provider_true` 驗證：

- env 0 + 無 shadow provider → legacy local SM 路徑跑（原 100+ test 全綠）
- env 0 + shadow provider True → SHADOW_BYPASS sentinel（caller fail-closed branch L459 不觸發，保持 shadow path 既有行為）
- env 1 + injected dispatcher → IPC 路徑跑（dispatcher 收到 canonical params + 回 lease_id）
- env 1 + IPC outage → None（caller fail-closed branch L459 觸發 → reject execution，符合 fail-closed contract）

---

## §6. Interface Contract（為 E-2/E-4 / wiring 準備）

### 6.1 給 wiring（paper_trading_wiring / strategy_wiring）— shadow_mode_provider 注入

```python
# 預期接線位置（E-3 留接口，wiring 任務或 P1-FAKE-1 修同 commit 落地）：
gov_hub.set_shadow_mode_provider(executor_agent._shadow_mode_provider)
```

`executor_agent.py:185` `_shadow_mode_provider: Callable[[], bool]` 是 G3-03 Phase B 的 zero-arg callable（從 Rust IPC `executor_config_cache.py` 拉取）。直接傳遞引用即可。

### 6.2 給 E-4 audit writer — dual-write mirror snapshot 觀察點

```python
from program_code.exchange_connectors.bybit_connector.control_api_v1.app.governance_lease_bridge import (
    get_dual_write_mirror_snapshot,
)

snapshot = get_dual_write_mirror_snapshot()
# {lease_id: {intent_id, scope, ttl_seconds, source, acquired_at, released_at, release_outcome}}
# E-4 healthcheck 可比對 Rust learning.lease_transitions table 與此 snapshot 的
# divergence count（amendment §6 條件 #1 4 週對賬期）。
```

### 6.3 給 E-2 Rust router gate — IPC method handler 註冊預期

E-2 task 在 Rust `dispatch.rs` 註冊 3 個 governance handler，method 名與 schema 模塊嚴格對齊：

```rust
// Rust dispatch.rs governance handler 預期 method names：
"governance.acquire_lease" => acquire_lease_handler(params).await,
"governance.release_lease" => release_lease_handler(params).await,
"governance.get_lease"     => get_lease_handler(params).await,
```

handler params serde struct 的鍵需與 lease_ipc_schema.py 的 `ACQUIRE_KEY_*` / `RELEASE_KEY_*` / `GET_KEY_*` 字串對齊（測試 `test_method_names_canonical` + `test_acquire_param_keys_canonical` 釘 drift）。

### 6.4 給 PM/Phase 5 — feature flag flip checklist

```bash
# Phase 1 baseline（current）：
unset OPENCLAW_LEASE_PYTHON_IPC_ENABLED  # 等於 OFF；走 legacy local SM
# Phase 2+（E-1/E-2/E-4 都 land + dispatch.rs handler ready 後）：
export OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1  # 嚴格 == "1" 才啟用
# 24h 觀察 amendment §6 條件 #2 IPC failure rate < 0.5%/day
# AC-1 24h 5 distinct state PASS → 進 Phase 3 dual-write 4 週對賬
# AC-1 FAIL → flip back: unset OPENCLAW_LEASE_PYTHON_IPC_ENABLED
```

`is_lease_ipc_enabled()` 嚴格 == "1"，"true"/"yes"/"ENABLED" 不啟用（mirror h_state_invalidator + executor_config_cache 慣例）。

---

## §7. 不確定之處 / Open issues

### 7.1 PA push back #1 — Rust `acquire_lease/release_lease` 自動 emit `LeaseTransitionMsg`（E-4 範疇）

dispatch §"Push back 通道" 提到 「E-1 push back §7.3 acquire/release 不自動 emit LeaseTransitionMsg → E-3 IPC payload 怎麼帶 audit event flush？」

**答**：E-3 不負責 emit。Rust E-1 facade 在 acquire_lease 內 0 emit（E-1 報告 §7.3）；E-4 task 預計 wrap facade 加 transition emit hook（E-1 §6.5 Option A/B/C 三選一）。E-3 IPC payload **不**帶 audit event flush instruction — 這由 Rust dispatch.rs handler 內部觸發，與 IPC bridge 解耦。E-3 IPC contract 純粹是 lease 生命週期操作（acquire / release / get）；audit emit 是 Rust 端 side-effect。

如 E-2 / E-4 task 設計時認為 Python 端應 push event flush，需在 dispatch.rs handler 內 wrap acquire_lease + emit；E-3 IPC schema 不需擴。

### 7.2 PA push back #2 — shadow caller short-circuit logic 在 lambda True 既有 ExecutorAgent context 撞 race

dispatch §"Push back 通道"：「shadow caller short-circuit logic 在 `lambda: True` 既有 ExecutorAgent context 撞 unexpected race」

**E-3 解法**：`set_shadow_mode_provider()` 接受任意 zero-arg callable（不限於 `executor_agent._shadow_mode_provider`）。`shadow_short_circuit_acquire()` 內部加例外保護：provider 拋例外 → 視為 non-shadow（caller 走完整 IPC）。這避免：
- provider 內部死鎖（如 ExecutorConfigCache 內 lock 與 governance_hub._lock 互鎖）→ 例外路徑
- provider 內部 IPC 失敗（cache 不可達）→ 例外路徑
- provider 線程異步狀態（caller thread 中讀取 race）→ python GIL + thread-safe bool read 不會 race

**真正的 race 風險**（E2 review 必查）：
- `_shadow_mode_provider` 與 `acquire_lease()` 之間若 provider 先回 False，但呼叫 `acquire_lease_via_ipc()` 期間 shadow flag flip 為 True → 會走完整 IPC 路徑 + Rust SM 真實 transition。**這是 race**，但**不會破壞契約**（IPC 已啟動 + Rust SM 真實 transition + caller 收到真實 lease_id）。Phase 5 IPC 啟用後，shadow flag flip 應透過 Rust IPC `update_risk_config` 觸發 cache 同步，期間若 race 觸發 1-2 個假 IPC lease 並非系統性問題（< 0.5% IPC failure 條件可吸收）。

如 E2 認為 race window 必須消除，建議方案：在 `acquire_lease()` 內把 shadow check 與 IPC dispatch 包進 `with self._lock`（**不推薦** — provider 讀外加 lock 反而增加死鎖風險）。push back：當前設計可接受，race 機率極低且 IPC failure rate 觀察可吸收。

### 7.3 PA push back #3 — IPC payload byte-equal cross-language schema 不一致（如 既有 IPC 用 msgpack 而 lease 用 json）

dispatch §"Push back 通道"：「IPC payload byte-equal cross-language 撞既有 IPC schema 不一致（如 既有 IPC 用 msgpack 而 lease 用 json）」

**確認**：既有 IPC dispatch 走 JSON-RPC 2.0 over Unix domain socket（`ipc_client.py:1` MODULE_NOTE 明寫 "JSON-RPC 2.0 protocol, newline-delimited messages"）。**lease IPC 用同一個 transport** = JSON over UDS。0 msgpack 衝突。`one_shot_ipc_call()` (`ipc_dispatch.py:84`) 是純 JSON-RPC 派發；E-3 直接重用，無新 transport。

byte-equal 釘子在 schema 模塊 13 個 canonical 鍵 test，與 W8 P6 envelope-signing pattern 同模式（spec 釘 spelling，drift fail fast）。

### 7.4 PA push back #4 — dual-write 4 週 mirror cache invalidation 邏輯複雜

dispatch §"Push back 通道"：「dual-write 4 週 mirror cache invalidation 邏輯複雜（PA push back §1 過渡期）」

**E-3 解法**：mirror 刻意精簡 — **無 TTL eviction、無 LRU、無 DB persistence**。每筆 acquire 寫入 dict[lease_id]，每筆 release 更新 `released_at + release_outcome`。**永不主動清除**（4 週後整個模塊 + dict 一起刪）。

**容量風險評估**：
- demo throughput 估計：500-1500 lease/day（5 strategy × 25 symbol × 平均 4-12 fills/symbol/day）
- 4 週 max：1500 × 28 = 42K entries × ~200 bytes = 8.4 MB
- Python process memory：可吸收（governance_hub 既有 `_governance_events` 1000-row buffer 已是 ~MB 級）

**真實 invalidation 邏輯複雜度**：0（永不清除）。對賬腳本由 P1-INFRA-3a-l-NEW（E-4 task 設計）批 query mirror snapshot vs Rust learning.lease_transitions table，跑日 cron。Phase 6 移除 mirror 時純粹 `git rm` lease_dual_write_mirror.py 模塊。

如 4 週後 P0-EDGE-2 結論延期 → mirror 可繼續存活，唯一成本是 Python heap ~8MB / 月（可接受）。

### 7.5 wiring 接線位置未落地

`set_shadow_mode_provider()` 在 GovernanceHub 已加，但**未在 paper_trading_wiring / strategy_wiring bootstrap 處呼叫**。E-3 留接口，預期：

- **Option A**：與 P1-FAKE-1（CLAUDE.md §三 18 blocker #8 ExecutorAgent shadow_mode hardcoded `lambda: True` fail-close）修復同 commit；P1-FAKE-1 改為 ConfigStore 真實 source 後，wiring 同時把該 provider 注入 governance_hub。
- **Option B**：另起小 task `wiring-shadow-provider-injection` 純註冊。

**E-3 push back**：option A 更乾淨（同個 sprint 同一 wiring 改動）；option B 是 standalone 後續 chore。請 PM 決定。在此之前：env=0（Phase 1 baseline）下 shadow_mode_provider 不啟用，acquire_lease 走 legacy local SM 路徑（既有行為），不破壞任何 contract。

### 7.6 governance_hub.py LOC 1228（接近 hard 1500 但未越）

baseline 1014（已超 800 警告）+ 214 LOC retrofit = 1228。距 hard 1500 還有 272 LOC 緩衝，但 §七 §九 警告線在 800。

**E-3 立場**：retrofit 必要膨脹（4 import + 2 欄位 + 2 setter + 3 method body 重寫），無法用 sibling module extract — acquire/release/get 三方法 body 必須在 GovernanceHub 內訪問 self._lock / self._lease_sm / self._authorization_sm。**§九 pre-existing baseline exception clause 適用** — baseline 已超 800 警告，本次新增不破 hard 1500，也未推到全新閾值。

如 E2 認為必須 extract，建議路徑：抽 `governance_hub_lease_mixin.py`（GovernanceHubLeaseMixin），把 acquire/release/get + 2 setter + 2 欄位移過去。**這是 retrofit 後的 P2 重構**（與 governance_hub_cascades.py / governance_hub_event_handlers.py 同模式），不在 E-3 範圍。push back：本 task 範圍應只做 retrofit + 測試，不做 mixin 抽取。

---

## §8. Operator 下一步

1. **E2 代碼審查 `srv/docs/CCAgentWorkSpace/E2/...`**：
   - 重點 §3.6 dual-write mirror 不變量（acquire/release/snapshot defensive copy）
   - 重點 §6 4 條 contract（wiring / E-4 / E-2 / Phase 5 flip）
   - 重點 §7.5 wiring 接線位置 push back（option A vs B）
   - 重點 §7.6 governance_hub.py LOC 1228 governance exception 簽核（若不簽則需先做 mixin 抽取）
   - 8 unit test category 是否覆蓋 spec §3 點 1-2 + push back #2 全部 contract
   - SHADOW_BYPASS sentinel 真的不污染 IPC 路徑（test `test_shadow_bypass_short_circuits_to_true` 確認 IPC dispatcher 0 呼叫）

2. **E4 regression**：跑 `pytest control_api_v1/tests/` 全套 + `pytest -k "executor or lease"` 確認 0 regression；驗證 `test_replay_routes_safe_query_audit::test_case2` fail 是 pre-existing test order pollution（獨立跑 PASS）

3. **PM 後續派發排程**（依 PA design §6.2）：
   - **Day 1 PM** E-1 + E-3 facade green → 派 E-4（V054 SQL + audit writer）
   - **Day 2** E-1 + E-3 + E-4 land → 派 E-2（Rust router gate + dispatch.rs handler）
   - **Day 3** 全部 land → E2 review + E4 regression + AC-1~5 driver E2E
   - 並行 P1-FAKE-1 修復 + wiring `set_shadow_mode_provider()` 注入接線

4. **不要 commit / push** — 等 E2/E4 + E-2/E-4 全 done 後 PM 統一 commit Track H 完整 patch

5. **不要 ssh trade-core deploy** — Linux deploy 在 Sprint 4 P0-EDGE-2 結論後（~2026-05-15）+ feature flag flip 前

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint3_track_h_e3_python_ipc_bridge.md）

---

## §9. E2 round 1 LOW-2 retrofit（2026-05-03）

### 9.1 LOW-2 修補摘要

E2 round 1 verdict 給 E-3 PASS（LOW-2 informational）— PA prompt 寫「`governance_lease_bridge.py` JSON serialise 缺 `ensure_ascii=False`」。

### 9.2 PA prompt scope 修正（push back 通道 #2 兌現）

PA prompt §LOW-2 §修法寫「在 `governance_lease_bridge.py` 的所有 `json.dumps` 加 `ensure_ascii=False`」。**實情：governance_lease_bridge.py 完全沒有 `json.dumps` 直接呼叫**（純 dict pass-through 給 `one_shot_ipc_call()` → `EngineIPCClient.call()`）。同樣 `lease_ipc_schema.py` 0 hit `json.dumps`。所有 IPC payload serialise 集中在 `ipc_client.py:218`（method dispatch）+ `ipc_client.py:583`（`__auth` handshake）。

PA prompt push back §2 預留：「既有 `governance_lease_bridge.py` 已用 `ensure_ascii=False`（如已對齊則 NO-OP，標 already-correct）」— 我兌現此 push back：lease bridge **沒有** json.dumps 故無需改；真正修補點是 `ipc_client.py`。

### 9.3 修改清單（2 檔，~190 LOC）

| 檔案 | 改動 | LOC 變化 |
|---|---|---|
| `srv/program_code/.../app/ipc_client.py` | 兩處 `json.dumps(..., separators=(",", ":"))` 加 `ensure_ascii=False` + 雙語 SAFETY 註釋（call 路徑 + auth handshake 路徑）| 624 → 780（+156；其中 ~150 LOC 雙語註釋 / lock 字典 + 6 LOC kwarg 行） |
| `srv/program_code/.../tests/test_governance_lease_bridge.py` | 新 `class TestLeaseIpcUnicodeByteEqualContract` 4 unit test（unicode intent_id byte-equal + unicode lease_id byte-equal + ipc_client.py source-grep drift sentinel + e2e wire round-trip）| 555 → 758（+203） |

**新檔：0**。修改範疇小於 PA prompt 推測（4 檔），因 lease bridge / schema 純 dict pass-through。

### 9.4 關鍵 diff（ipc_client.py:218 + 583）

```python
# Before (call() L218):
payload = json.dumps(request, separators=(",", ":")) + "\n"

# After:
payload = json.dumps(
    request, separators=(",", ":"), ensure_ascii=False
) + "\n"

# Before (auth handshake L583):
payload = json.dumps(request, separators=(",", ":")) + "\n"

# After:
payload = json.dumps(
    request, separators=(",", ":"), ensure_ascii=False
) + "\n"
```

兩處改動的 contract：對齊 Sprint 1 Track A F1 `_python_canonical_body_for_signing` 模式 + REF-20 W6 V042 `manifest_signer.rs::canonical_body_for_signing`（serde_json 預設 raw UTF-8）— Python `ensure_ascii=False` 讓 wire 上 unicode 保持 raw UTF-8 bytes 而非 `测试` escape 形式；Rust serde_json::to_vec 也是 raw UTF-8，雙端 byte-equal。

### 9.5 LOW-2 4 unit test 覆蓋

| Test | 目的 | 結果 |
|---|---|---|
| `test_acquire_request_params_unicode_intent_id_byte_equal_canonical` | intent_id="测试_intent_001；分號" + scope/profile + ttl_seconds=30.0 → builder 輸出 → `json.dumps(ensure_ascii=False)` byte-equal 手動 canonical 化 dict + SHA-256 anchor + 反 `\u` escape 守護 + raw UTF-8 substring 檢查 | ✅ |
| `test_release_request_params_unicode_lease_id_byte_equal_canonical` | 防禦深度：未來假設含非 ASCII 的 lease_id（"lease:测试_abc123"）byte-equal 不變量 | ✅ |
| `test_ipc_client_json_dumps_uses_ensure_ascii_false` | 源碼 grep regression sentinel：`ipc_client.py` 至少 2 處 `ensure_ascii=False` + 計數 ≥ `json.dumps` 計數（防 future commit revert） | ✅ |
| `test_no_unicode_escape_in_request_payload_round_trip` | end-to-end：build params + 模擬 `ipc_client.py:218` envelope 序列化 → wire bytes 0 `\u` escape + raw UTF-8 测试 | ✅ |

PA prompt §LOW-2 §加 1 unit test 範例：「assert SHA-256 not contain `\u` escape pattern」+「payload 含 unicode（如 `intent_id="测试_intent_001"`）」+「assert serialise 結果 byte-equal expected canonical bytes」— 三條全部覆蓋於 test #1。我寫了 4 個（覆蓋更全 + drift sentinel + e2e round-trip）。

### 9.6 PA push back 通道回應

**PA prompt push back §2** 已對齊（見 §9.2）：lease_bridge.py 沒有 json.dumps → 修改點轉移到 ipc_client.py。

**PA prompt push back §3** 「既有 unit test 已覆蓋 unicode case（如 LOW-2 重複測）」：
- 既有 40 unit test 0 hit unicode 場景（pytest grep 確認）
- LOW-2 新 4 test 是首次釘 lease IPC unicode byte-equal 契約

### 9.7 測試結果（LOW-2 retrofit 後）

| 套件 | 結果 |
|---|---|
| `pytest test_governance_lease_bridge.py` | **44 PASS / 0 fail**（baseline 40 + LOW-2 新 4） |
| `pytest -k "ipc or engine_ipc"` | **157 PASS / 0 fail**（IPC 全套無 regression） |
| `pytest -k "governance or executor or lease"` | **529 PASS / 8 skipped / 0 fail**（governance 全套無 regression） |
| `pytest control_api_v1/tests/` 全套（除 lg5_review_live_candidate） | **3382 PASS / 10 skipped / 1 fail**（該 1 fail = `test_replay_routes_safe_query_audit::test_case2`，獨立跑 5/5 PASS — 既有 test order pollution，與 LOW-2 0 關，E-3 §5 已標 pre-existing） |

### 9.8 治理對照（CLAUDE.md §七）

| 檢查 | 結果 |
|---|---|
| 雙語注釋（兩處 SAFETY 註釋 + LOW-2 test class header + 4 test docstring）| ✅ EN/中對照 |
| `grep -E '/home/ncyu\|/Users/[^/]+'` 兩改動檔 | 0 hit ✅ |
| 0 hard-boundary mutation | ✅ |
| 0 SQL | ✅ |
| 文件 LOC（ipc_client.py 780 < 800 警告 / test 758 < 800 警告）| ✅ |
| 0 新 singleton | ✅ |

### 9.9 PA push back 通道 #1 對 LOW-2 真實 scope

PA prompt §「Push back 通道」第 2 點：「既有 `governance_lease_bridge.py` 已用 `ensure_ascii=False`（如已對齊則 NO-OP，標 already-correct）」

**回應**：lease_bridge.py 沒有 json.dumps（已 grep 確認），無 ensure_ascii 對齊問題。**真正缺口在 ipc_client.py（共用 IPC layer）**。改它影響全 IPC（含 33+ 既有 method）但：
- 全既有 method 用 ASCII payload → kwarg no-op
- Rust serde_json::to_vec 預設 raw UTF-8 → kwarg 讓 Python 端對齊
- 風險：0（ASCII payload byte-equal 不變；任何 future unicode payload 自動正確）

PA prompt §「Push back 通道」第 3 點：「既有 unit test 已覆蓋 unicode case」— 否：grep 確認 governance_lease_bridge / executor 既有 ~308 test 0 hit unicode；LOW-2 4 新 test 是首次。

### 9.10 PM 後續

- E2 round 2 review 確認 LOW-2 informational caveat 解除
- LOW-1 + LOW-2 retrofit 同 commit（PM 統一 commit Track H 完整 patch；不要 commit / push 由我做）
- 如 E2 認為 LOW-2 修法應限縮在 lease 路徑（避免改共用 ipc_client.py），可用替代方案：lease bridge 在 send 前自行 serialise + ipc_dispatch 接受 `pre_serialised: bytes`。**不推薦**（要改 dispatch 協議，scope 反而擴大）。


