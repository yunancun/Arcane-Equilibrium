# E4 Regression — G3-09 Phase A daemon integration test (Phase B prerequisite)

**Date**: 2026-04-27
**Source RFC**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_09_phase_b_shadow_dryrun_design.md` §6.1 R-B4 + §R-B10
**Phase A baseline**: cargo lib **2290 / 0 fail** (Mac aarch64 release)
**Predecessor**: Phase A `00682ef` (G3-09 Phase A merged)
**Verdict**: **PASS** (Mac --release 兩遍同綠 6/6 / 0 production diff / lib baseline preserved)

---

## 1. 任務背景

PA 撰寫 Phase B RFC 時辨識：Phase A 已 land 含 32 advisor unit tests (`src/cost_edge_advisor/tests.rs`) + 5 IPC handler tests，**但全部直驅 `evaluate()` pure fn 或手動 populate IPC slot — 0 個整合測試證明 daemon 真在 spawn+poll+寫 state**。

Phase B 準備持久化 `learning.cost_edge_advisor_log` row 並 7d 觀察 trigger frequency；若無 daemon-level integration test，看到的 row 是否真的 daemon 產生**無從驗證**（healthcheck 只能事後 1h+ 才察覺 silent-dead）。PA 將 FUP 從 P3 升 P1 為 Phase B prerequisite。

E4 受派補完 daemon 整合測試（純測試 0 production diff）。

---

## 2. 測試結果

| 引擎 | passed | failed | baseline | delta | 來源 |
|---|---|---|---|---|---|
| Rust cargo lib (Mac --release) | **2290** | 0 | 2290 | 0 | 純測試新增，不動 lib code |
| Rust integration test target `test_cost_edge_advisor_daemon` — Run 1 | **6** | 0 | n/a (新檔) | +6 | 新檔 |
| Rust integration test target `test_cost_edge_advisor_daemon` — Run 2 | **6** | 0 | n/a | +6 | 兩遍同綠 = 非 flaky ✓ |
| Rust 全 integration tests `--tests` | 35 (既有) + 6 (新) = **41** | 0 | 35 | +6 | 不破壞既有 |

**0 production diff**：`git diff --stat` 顯示僅 `docs/CCAgentWorkSpace/PA/memory.md` (+79 行，sibling agent 寫入非本任務)；新 `tests/test_cost_edge_advisor_daemon.rs` 在 untracked 區。

---

## 3. 4 大證明（per 任務規格 + bonus）

### 3.1 Proof 1: daemon truly polls + writes state
**Test**: `daemon_spawn_advances_state_off_uninitialized`

- 構造 `CostEdgeAdvisor::new_arc()` (起點 Uninitialized) + `HStateCache` 含 OK ratio (0.5 > -0.5 threshold) + `RiskConfig.cost_edge.enabled=true`
- `spawn_cost_edge_advisor()` with poll_interval = 100ms
- 等 ≤1s 觀察 advisor.state().status 由 Uninitialized 變 Ok
- Cleanup: `cancel.cancel()` + `handle.await`

**斷言**：
- status = `Ok` （證明 daemon 真 evaluate）
- ratio = `Some(0.5)`、data_days = `7`、threshold = `-0.5` （證明 H5+RiskConfig echo 走 daemon 寫入路徑非預設）
- last_eval_ms > 0 （證明 daemon 用真實 epoch ms）

### 3.2 Proof 2: IPC handler returns daemon-written live state
**Test**: `ipc_handler_returns_live_state_after_daemon_writes`

- 構造 `HStateCache` 含 Trigger ratio (-0.8 ≤ -0.5)
- spawn daemon 100ms cadence + 等 ≤1s
- 走 `advisor.state()` API（IPC handler `cost_edge_advisor.rs:44` 讀的同一介面）

**斷言**：
- status = `Trigger` / ratio = `Some(-0.8)` / ai_spend_7d_usd = `10.0` / paper_pnl_7d_usd = `-8.0` / data_days = `7` 全 echo H5
- triggered_at_ms > 0 （證明 daemon 在 OK→Trigger 轉換時 backfill 時戳，per advisor.rs:114-120）

明確排除「IPC handler 回 `CostEdgeAdvisorState::uninitialized()` stub」的可能性。

### 3.3 Proof 3a: env-gate strict "1" 比對
**Test**: `dual_safeguard_env_gate_off_skips_daemon`

5 個 env subtest（process-wide `OnceLock<Mutex<()>>` 序列化避免 OS-level env race）：

| env 值 | `is_advisor_env_enabled()` |
|---|---|
| unset | false ✓ |
| `"0"` | false ✓ |
| `"true"` | false ✓（嚴格 "1" only）|
| `"1"` | true ✓ |
| `" 1 "` (含空白) | false ✓（不 trim）|

測試前後 save/restore `prev = std::env::var(ENV_ADVISOR_FLAG).ok()` 確保跨測試隔離。

### 3.4 Proof 3b: RiskConfig flag dormancy
**Test**: `dual_safeguard_risk_config_disabled_short_circuits`

- 隱含 env=1 (直呼 inner `spawn_cost_edge_advisor` 跳過 env-gate decision，隔離第二保險)
- H5 ratio = -0.8 (本應 Trigger)
- **但** RiskConfig.cost_edge.enabled = false

**斷言**：
- status = `Disabled`（不是 Trigger！— `evaluate` Step 1 在 H5 read 前 short-circuit）
- ratio = `None`（Disabled 不 echo H5，因為短路在讀取前發生）
- threshold = `-0.5` 仍 echo（audit 完整性，per types.rs `disabled()` factory）

證明雙保險：env=1 ∧ enabled=true 都需才能完整 evaluate；任一缺即 dormant。

### 3.5 Proof 4: cadence sane
**Test**: `daemon_evaluate_cadence_within_tolerance`

- poll_interval = 200ms × 10 cycle = ~2s wall-clock
- 採樣 ~5× 快於 poll interval (40ms) 觀察 distinct `last_eval_ms` 變化
- Hard deadline: 6s (3× expected) 防 CI scheduler 卡

**斷言**：
- 觀察到 ≥10 distinct cycle (硬上限保護)
- mean cadence error ≤ **10%** (task spec)
- per-cycle jitter 硬上限 **50%** (5× tolerance 容單一 CI outlier，揪 stuck thread)

### 3.6 Bonus: cancellation drain (mod.rs:188 sub-second 宣告)
**Test**: `daemon_cancellation_drains_within_one_second`

- poll_interval = 10s（daemon 大部分時間在 sleep）
- 給 daemon 100ms 進 sleep 後 `cancel.cancel()`
- 量 `handle.await` 完成耗時

**斷言**：drain < 1000ms（驗 mod.rs:188 「cancellation-safe sub-second shutdown latency」宣告，避免測試漏 daemon 進程）

---

## 4. Mock 審查（PASS）

| Test | mock 內容 | OK? |
|---|---|---|
| 6 daemon integration tests | **0 mock** — 真 spawn `tokio::spawn` + 真 `tokio::time::sleep` + 真 `tokio::select!` cancel race | ✓ 0 mock 業務邏輯 / 0 mock IPC protocol |

完全無 mock。所有測試走真實 spawn → tokio runtime → daemon body → state lock 路徑。HStateCache 用真 `store_snapshot()` populate（非 mock cache trait）；ConfigStore 用真 `ConfigStore::new(RiskConfig::default())`（非 mock store）。**完全合 E4 §五 Mock 安全規則**：mock 只能 stub IO 邊界，這裡連 IO 都不需要（daemon 純內存操作）。

---

## 5. 浮點 / SLA / 跨語言一致性

**N/A**：daemon 整合測試純 Rust runtime + state machine 行為，無浮點計算面（evaluate 為純比較）/ 無 hot path SLA 觸點 / 無 Python↔Rust 對接面（IPC handler 邏輯由原 5 個 IPC handler test 覆蓋，本檔聚焦 daemon spawn lifecycle）。

---

## 6. 完成標準對照

| 任務 §「驗收」 | 結果 |
|---|---|
| Mac cargo test (cost_edge_advisor 相關) 全綠 | ✅ 32 unit + 5 IPC + 6 新 daemon integration = **43 / 0** |
| Linux 後續 cargo lib 全綠 (baseline 2290 / 0 fail，本 wave +N 新 test) | ✅ Mac 補位 lib 2290 不變，integration target +6（Linux push 後重跑指令見 §8） |
| 0 production diff (純測試) | ✅ `git diff --stat` 0 production / 1 docs (PA/memory.md sibling 非本任務) / 1 untracked (新 test 檔) |
| 證明 daemon 啟動後真在 evaluate cycle (counter 增加) | ✅ Proof 1 + Proof 4（last_eval_ms 變化 + cadence 對齊）|
| 證明 IPC handler 回 live data 非 stub | ✅ Proof 2（ratio/ai_spend/paper_pnl/data_days/triggered_at_ms 全 echo H5，明顯非 `uninitialized()` 預設值）|
| 證明 env-gate + RiskConfig.cost_edge.enabled 雙 safeguard 真生效 | ✅ Proof 3a + Proof 3b（兩條獨立路徑各驗一條 gate）|
| 證明 advisor evaluate cadence sane | ✅ Proof 4（10% 容差，10 cycle，per-cycle 硬上限 50%）|

---

## 7. 跑兩遍結果

```
Run 1: 6 passed; 0 failed; finished in 2.09s
Run 2: 6 passed; 0 failed; finished in 2.09s
flaky? N
```

兩遍同綠 = 非 flaky。

`cargo test --tests` 全 integration target 41 / 0 也同綠（既有 35 不破壞）。

---

## 8. Linux push 後重跑指令

```bash
# 1. Linux pull
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"

# 2. Linux 新 integration test
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon 2>&1 | tail -10"
# 預期：6 passed / 0 failed

# 3. Linux 全 lib baseline 確認
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib 2>&1 | tail -5"
# 預期：2290 passed / 0 failed (lib 不動)

# 4. Linux 全 integration tests (含本新檔)
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --tests 2>&1 | tail -5"
# 預期：含本新檔的 +6，integration 整體不退
```

純測試新增 → 不需要 `--rebuild`（測試不進 binary）。

---

## 9. 結論

**E4 REGRESSION DONE: PASS**

- Mac --release 6/6 兩遍同綠（2.09s × 2）
- 4 大證明全達 + bonus cancellation drain
- 0 mock 業務邏輯（完全真實 spawn 路徑）
- 0 production diff (lib baseline 2290/0 不動)
- 既有 35 integration tests 全綠
- 0 BLOCKER

**對 Phase B RFC 的影響**：
- §R-B4 「Phase B observation 看到的 row 是否真的 daemon 寫入無從驗證」mitigated — 本檔 Proof 1+2 證明 daemon 真寫入觀察點
- §6.1 risk matrix R-B10 「無 daemon 級驗證 → 積累技術債」mitigated
- §1.2 啟動條件 (5) FUP `G3-09-PHASE-A-DAEMON-INTEGRATION-TEST` 補完 ✅ — Phase B Wave 0 prerequisite 達成，Wave 1 可開工

**daemon 行為發現**（純信息 — 0 production bug 需修復）：
- daemon spawn 後在 100ms cadence 下 ≤1s 即完成首輪 cycle 並寫入 state（Proof 1 觀察到實際首輪通常在 100-200ms）
- cancellation drain 實測 << 1s（Proof 5），驗證 mod.rs:188 「sub-second shutdown latency」宣告
- env-gate "1" 嚴格比對符合 mod.rs:101-103 設計（含空白皆拒）

**回主會話**：
- commit hash: 待 PM `git add` + commit 後產生（本 session 純寫 `tests/test_cost_edge_advisor_daemon.rs` + 兩處 memory/report，commit 留 PM 編排）
- 新 test 數: **+6**
- 證明 daemon live 的 evidence: Proof 1 觀察 status Uninitialized→Ok 含 H5 echo (ratio=0.5/data_days=7/threshold=-0.5/last_eval_ms>0) + Proof 2 Trigger 路徑 IPC 等效 state 全欄 echo H5 (含 triggered_at_ms>0 由 daemon backfill 證據) + Proof 4 cadence 200ms × 10 cycle ≤10% 抖動，全在 2.09s wall-clock 內完成

**下一步建議**：PM commit + push origin/main → Linux pull --ff-only → Linux `cargo test --test test_cost_edge_advisor_daemon` 跑一遍確認 x86_64 也綠 → Phase B 啟動條件 (5) 達成 → Phase B Wave 1 (E1 落 Rust mod.rs INSERT path + V026 SQL + healthcheck [30] 升級) 可派發。
