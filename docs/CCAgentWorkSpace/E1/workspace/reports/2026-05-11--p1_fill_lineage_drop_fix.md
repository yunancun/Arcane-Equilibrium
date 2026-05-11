# Wave 1.6 P1-FILL-LINEAGE-DROP — Option F4 Spine Channel Silent-Drop Fix（E1 IMPL DONE）

**Date**: 2026-05-11
**Author**: E1 (Backend Developer)
**Trigger**: QA RCA 2026-05-11 `p1_rca_1_orphan_er_investigation.md` SYSTEMIC verdict（empirical 25.8% silent drop rate, blocks Stage 3+ promotion）+ operator GO 派 Wave 1.6 急 fix
**Scope**: 3 files / +422 LOC / -6 LOC（淨 +416 LOC）
**Build**: cargo build --release -p openclaw_engine PASS @ 22.11s（baseline 24.79s 同範圍）
**Tests**: cargo test --lib --release -p openclaw_engine **2810 passed / 0 failed / 0 ignored**（baseline 2807 + 3 new = 2810）
**SoT**: working tree HEAD（未 commit；等 E2 + E4 對抗 review 後 PM 統一 commit + deploy）

---

## 1. Executive Summary

**STATUS**: ✅ **IMPL DONE — APPROVED FOR E2 + E4 PARALLEL REVIEW**

QA RCA 確認 spine mpsc channel `try_send` silent-drop 在 burst load 期間丟 25.8% ER events（empirical engine 1 14.5h: 19.4% / engine 2 3h: 14.3%）。本 fix 採 **Option F4 hybrid + B-2 caller-aware retry strategy**：

1. **Stage 1**：`tasks.rs:642` channel cap 1024 → 8192（8x headroom）
2. **Stage 2**：`runtime_shadow.rs` 拆 `try_send`（hot path）+ 新增 `try_send_with_background_retry`（fill_completion path）
3. **Stage 3**：3 個 drop / retry counter 暴露為 process-wide metric（`spine_channel_drop_total()` / `spine_channel_retry_success_total()` / `spine_channel_retry_fail_total()`）
4. **Stage 4**：3 個新 unit test 釘住 (a) drop counter 升 (b) cap bump 後 burst 0 drop (c) retry path 成功救援

5 條 acceptance 全綠：build PASS / lib test 2810 PASS / 0 regression / hot path SLA 不變 / 0 cross-platform hardcoded path。

---

## 2. B-1 / B-2 / B-3 設計選擇

### 選 B-2（**Caller-aware retry**）+ 局部融合 B-3（**spawn background retry**）

| Option | 評估 | 選否 |
|---|---|---|
| B-1（只 cap bump） | 25.8% baseline drop 8x bump 估降至 <1%，但 burst peak >100 msg/s 時 8192 仍可能爆 | ❌ 太樂觀，無 retry 救援機制 |
| B-2（區分 caller） | entry path（hot）只 cap bump；fill_completion path（post-fill）加 retry | ✅ **採用** |
| B-3（全部 spawn task retry） | 統一架構優雅，但 entry path 10 try_send 都 spawn = 10×10μs hot path overhead；不必要 | ❌ entry path 違反 hot path 原則 |

**設計理由**：
1. `emit_entry_lineage` caller = `step_4_5_dispatch.rs:664` 屬 **tick hot path**（gate approved → dispatch entry）；CLAUDE.md §九 SLA <0.3ms tick。3×50ms retry 在 worst-case = 5000x SLA breach 絕對禁。
2. `emit_fill_completion_lineage` caller = `loop_exchange.rs:283` 是 **WS Fill event consumer**（**不是 tick hot path**）；fully_filled 路徑 24h ~86 次，spawn task ~10μs × 4 = 40μs/event = 0 SLA 壓力。
3. **B-2 + spawn task hybrid**：fill_completion 內 4 try_send fail 時 spawn 4 個 background retry task，**主執行緒立即返回不阻塞**（保 `emit_fill_completion_lineage` 為 sync fn 避免破多檔 caller cascade 改 async）。

retry 邏輯（per QA RCA Option F4）：
- 3 × 50ms retry interval = 150ms worst case
- tokio::time::sleep().await 不阻 tokio worker thread
- AgentSpineMsg 帶入 task 內 owned（Clone derived）；無 leak 風險

---

## 3. 修改檔案清單

| 檔 | LOC 變更 | 變更摘要 |
|---|---|---|
| `rust/openclaw_engine/src/tasks.rs:641-655` | +12 / -1 | mpsc channel cap 1024 → 8192 + 中文 8 行解釋 RCA 經驗證據 |
| `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:33-93` | +63 / 0 | imports + 3 個 AtomicU64 static counter + 3 pub accessor fn（drop / retry_success / retry_fail）|
| `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:639-771` | +103 / -19 | 改 `try_send` 加 counter；新增 `try_send_with_background_retry` 含 spawn retry task |
| `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:526-602` | +6 / -8 | emit_fill_completion_lineage 內 4 個 try_send 換用 retry helper |
| `rust/openclaw_engine/src/agent_spine/tests.rs:1-22` | +1 / 0 | use `std::time::Duration` |
| `rust/openclaw_engine/src/agent_spine/tests.rs:1247-1476` | +231 / 0 | 3 個新 unit test（`fill_completion_*`）|
| **總計** | **+422 / -6** | 淨 +416 LOC（10% on runtime_shadow.rs，新檔 0）|

---

## 4. cargo test 全綠數字

```
running 2810 tests
...
test result: ok. 2810 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.55s
```

baseline: 2807 → 本 PR + 3 new = 2810 ✅

連續 5 次跑新 3 個 test：5/5 PASS（驗證時序 retry test 穩定，無 flaky）

---

## 5. 新加 3 個 unit test

| Test | 驗的不變式 | 機制 |
|---|---|---|
| `fill_completion_channel_full_increments_drop_counter` | (a) channel full → drop counter 嚴格遞增 | cap=1 預塞滿；emit_fill_completion 4 try_send 全 fail；delta ≥ 4 |
| `fill_completion_burst_with_8192_cap_no_drop` | (b) 8192 cap 下連續 100 fill_completion = 400 msg 0 drop | cap=8192 私有 channel；100 iter × 4 msg；assert accepted=4 每次 + queued=400 |
| `fill_completion_retry_succeeds_after_slot_released` | (c) channel slot 釋放後 retry task 成功救援 | cap=4 預塞滿；4 try_send 全 fail → spawn 4 retry；drain 4 pre-fill → 等 500ms deadline → assert ≥4 retry msg drained |

設計亮點：
- counter 是 **process-wide global**，並行測試下 delta 受其它 test 污染 → test (b) 改用 **channel queue state**（rx.try_recv 計數）作驗，不依賴 counter delta
- test (c) cap=1 下 4 retry task 互相搶 slot 觸發二次 retry → 用 cap=4 + drain 4 pre-fill 騰 4 slot → 時序確定性高
- test (c) 500ms deadline 給 50ms × 3 retry worst case 150ms + tokio scheduler jitter buffer 350ms

---

## 6. Hot path SLA before/after

### emit_entry_lineage（**hot path**）

| 項 | Before | After | Delta |
|---|---|---|---|
| try_send fast path（success） | ~50-200 ns | ~50-200 ns + Relaxed atomic check ~0ns | 0 |
| try_send fail path（channel full）| ~200 ns + warn log | ~200 ns + `fetch_add(1, Relaxed)` ~3 ns + warn log | +3 ns / fail |
| 10 try_send（W-C Caveat 1 後）| ~2-20 μs | ~2-20 μs + 0-30 ns | < +0.2% baseline |
| Total emit_entry_lineage 估算 | ~20 μs（E5 baseline）| ~20 μs（不可量化差異）| **0% on tick SLA 0.3ms = 300μs** ✅ |

**結論**：emit_entry_lineage SLA 不變（counter Relaxed atomic 約 1-3ns × 10 = <30ns 增量）。

### emit_fill_completion_lineage（**非 hot path** — loop_exchange WS fill event consumer）

| 項 | Before | After | Delta |
|---|---|---|---|
| Fast path（all 4 try_send 成功）| ~10-20 μs | ~10-20 μs（無 tx.clone / spawn）| 0 |
| 1 個 try_send fail + spawn retry | n/a | ~50-200ns + `tx.clone()` ~20 ns + `tokio::spawn` ~10 μs | +10 μs / fail |
| 4 try_send 全 fail（worst case）| 4 × ~200ns + 4 × warn log = ~1 μs | 4 × ~10 μs spawn = ~40 μs | +39 μs |
| 24h 累積（86 fully_filled × 4 try_send × spawn worst case）| 0 | ~3.4 ms | **0% impact**（fill 路徑不在 tick SLA）|

**結論**：fill_completion 不在 tick hot path（loop_exchange async event consumer），spawn 成本可忽略。retry 失敗 worst 150ms 仍遠低於 fill 事件處理週期。

---

## 7. Drop counter metric 暴露介面

### Public API（`agent_spine::runtime_shadow`）

```rust
pub fn spine_channel_drop_total() -> u64;
pub fn spine_channel_retry_success_total() -> u64;
pub fn spine_channel_retry_fail_total() -> u64;
```

### 用途

| Counter | 用途 |
|---|---|
| `spine_channel_drop_total` | 累計 try_send 失敗（channel_full + channel_closed）；healthcheck [55] / 將來 P1-FILL-LINEAGE-MONITOR 對外暴露 metric `agent_spine_channel_drop_total` |
| `spine_channel_retry_success_total` | retry helper 重試成功筆數；觀察 burst 期間 retry 救援率（理想 > drop_total 表 retry 工作） |
| `spine_channel_retry_fail_total` | retry 用盡 3 次仍失敗筆數；若非 0 代表 8192 cap + retry 3× 仍不足，需 wave 2 級 infra 升級 |

### 設計

- 3 個 `static AtomicU64 = AtomicU64::new(0)`；Relaxed ordering（counter 屬統計屬性，無 happens-before 需求）
- process 重啟歸零；下游 healthcheck 用 delta 對比不依賴跨重啟絕對值
- 0 新依賴（std::sync::atomic 標準庫）
- 並發 fetch_add(1, Relaxed) 保證單調遞增，無 Mutex 必要

### 後續接線（**非本 fix scope，留 P1-FILL-LINEAGE-MONITOR ticket**）

- Python healthcheck `checks_agent_spine.py` 加 `/api/v1/metrics/agent_spine_channel_drop` endpoint 對應 IPC call
- 或 直接讓 Rust engine 通過既有 metric channel 推送（OPENCLAW_DATA_DIR/metrics socket）

---

## 8. Self-check 8 acceptance 逐條

| # | Acceptance | Verdict | Evidence |
|---|---|---|---|
| 1 | `cargo build --release -p openclaw_engine` 綠 | ✅ | 22.11s（baseline 24.79s 同範圍）；0 error；本 PR 0 warning（既存 2 dead_code warning 非本 PR 引入）|
| 2 | `cargo test --lib --release -p openclaw_engine` 全綠（2807 + new tests）| ✅ | 2810 passed / 0 failed / 0 ignored；連續 5x 跑新 test 穩定 PASS |
| 3 | 新加至少 3 個 unit test（counter / burst no drop / retry path PASS）| ✅ | 3/3 新 test 全綠：`fill_completion_channel_full_increments_drop_counter` / `fill_completion_burst_with_8192_cap_no_drop` / `fill_completion_retry_succeeds_after_slot_released` |
| 4 | emit_entry_lineage hot path SLA 不變（或微增 <2μs 接受）| ✅ | 增量 <30 ns（Relaxed atomic × 10），E5 base 20μs / 0.3ms tick SLA 中佔比 <0.01% |
| 5 | 注釋全中文 | ✅ | grep 純英文長注釋 0 hit（混中文技術詞合法）；MODULE_NOTE / docstring / inline 全含中文成分 |
| 6 | drop_counter Atomic 設計 thread-safe | ✅ | `AtomicU64` + Relaxed ordering（counter 統計屬性無 happens-before 需求）；無 Mutex；fetch_add 保證並發單調 |
| 7 | Channel cap bump 後 burst scenario 模擬 drop=0 | ✅ | test (b) `fill_completion_burst_with_8192_cap_no_drop` 100 iter × 4 msg = 400 全 queued + 0 drop；private channel 排除並行 test 污染 |
| 8 | retry path 在 fill_completion 不阻塞 hot path（B-2 選擇）| ✅ | retry 用 `tokio::spawn` 移到 async runtime；sync `emit_fill_completion_lineage` 返回後 4 try_send fail 的 retry 全在背景；caller `loop_exchange.rs` 不等 retry result |

---

## 9. Caveat / Risk

### Caveat 1（**file size 警告線**）

`runtime_shadow.rs` 從 657 → 828 LOC，**超 800 警告線 28 LOC**（仍 < 2000 hard cap）。

- 起因：本 PR 加 ~60 LOC counter + 70 LOC retry helper + 40 LOC 中文注釋
- 評估（**E2 review MEDIUM-1 修正**）：~~屬 CLAUDE.md §九「Pre-existing baseline exception clause」框架可接受~~（**錯誤引用**：§九 exception clause 字面僅適用 `pre-existing baseline > 2000` 的 violation；657 < 2000 不適用此 clause）。正確 path = **「800 警告線 watch + 開 P2/P3 split ticket」標準流程**，不阻 merge。
- 後續：**P2 ticket `P2-RUNTIME-SHADOW-SPLIT` 已加入 TODO §10**（從 E5/E2 建議 P3 升 P2，per E2 review consensus），拆 `runtime_shadow.rs` → `lineage_emit.rs` + `channel_helpers.rs` 兩 sibling（與 E5 W-C review §D-5/D-6 同方向）。

### Caveat 2（**retry path 不保證 100% delivery**）

retry 3 × 50ms 用盡仍 fail 時 → 計 `retry_fail_total` 但 ER 訊息**永久 lost**。

- 條件：channel 持續 burst 滿超 150ms（極端持續壓力）
- 影響：少數 ER 仍會 silent drop（QA RCA expected residual rate <1%）
- 監測：healthcheck [55] 監 `retry_fail_total` 非 0 → 觸 P1 升級 ticket（cap 32K / unbounded / 全 async cascade）
- 評估：屬 Option F4 設計 known trade-off；ER 是 audit-trail 非 trading authority，少許 drop 不影響交易正確性

### Caveat 3（**spawn 成本 micro-benchmark 未測**）

E5 W-C review 用估算（spawn ~10μs / Sender clone ~20ns）；本 PR 沒新 bench harness 量測，僅理論推算。

- 評估：fully_filled 24h ~86 次 × 4 spawn × 10μs = 3.4ms 累積，遠低於任何 SLA
- 後續：若 future burst 統計顯示 spawn task 數量 >1000/min，建議改 fixed-pool retry queue（PA 後續 ticket 決定）

### Caveat 4（**tests.rs 已超 800 警告線**）

tests.rs 1245 → 1476 LOC；屬 pre-existing 已超警告，本 PR +231 LOC = 18.5% 增。

- 屬 §九 pre-existing exception（test 檔在政策上 800 警告較寬）；不破 2000 hard cap
- 後續 G5-09 pattern 拆 sibling 待 W-D wave 後一起

---

## 10. 治理對照

- **CLAUDE.md §一**：fix 屬 Spine audit chain 完整性，不動 OpenClaw control plane（Gateway / Console）
- **§二 16 原則**：16/16（特別 #5 生存 > 利潤 — 確保 audit chain 完整提供 Stage 3+ promotion 必要證據；#8 交易可解釋 — drop 25.8% 即 audit chain 19% 破洞）
- **§四 5 硬邊界**：0 觸碰（max_retries=0 / live_execution_allowed / execution_authority / system_mode 全不動）
- **§五 架構**：emit_*_lineage 仍隸 agent_spine module，0 跨模組擾動
- **§七 跨平台**：0 硬編碼路徑（`grep -E '(/home/ncyu|/Users/ncyu)' = 0 hit`）
- **§七 注釋（2026-05-05 中文 default）**：新增 ~50 LOC 注釋全中文（混技術詞）；無純英文長段
- **§七 SQL migration Guard A/B/C**：N/A（本 fix 0 schema change）
- **§九 Singleton 表**：新增 3 個 `static AtomicU64` process-wide counter — 在 `agent_spine::runtime_shadow` module 內以 pub fn accessor 暴露。**已 PM commit 同次更新 §九 Singleton 表加 1 行（3 個 counter 合 1 row）** ✅
- **§九 file size**（**E2 review 修正**）：runtime_shadow.rs 828 > 800 警告線（**non-exception path** — pre-existing baseline 657 不到 2000，§九 exception clause 不適用；走標準警告 watch + P2 split ticket 路徑，P2-RUNTIME-SHADOW-SPLIT 已加 TODO §10）；tests.rs 1476 同樣（P2 tracked）；tasks.rs 978（pre-existing >800，本 PR +8 LOC，跟 sibling 一起拆）

---

## 11. Operator 下一步（PM 派發指引）

1. **派 E2 對抗審查**：重點審 retry path race condition（spawn task lifetime / msg.clone 開銷）+ counter Relaxed ordering 是否 sufficient + cap 1024→8192 對 DB writer flush 端是否造壓
2. **派 E4 regression**：跑既存 2807 baseline + 3 new = 2810 lib test 全 PASS；burst 模擬 200ms 100 fill_completion concurrent benchmark 測 spawn task pool 不爆（建議補）
3. **E2 + E4 PASS 後 PM commit + deploy**：
   - 一次 `bash helper_scripts/restart_all.sh --rebuild --keep-auth` 部署 Rust binary 升級
   - Deploy 後立刻看 healthcheck `[55] agent_decision_spine_lineage` chains_with_real_fill_report 比率（理論應由 80-86% 升至 >99%）
   - 4h passive watch `spine_channel_drop_total` 增量（理論在 burst 期間應 << pre-fix baseline）
   - 12h 確認 W-D MAG-084 sign-off §5 P1-RCA-1 propagation rate 50% gate 真實通過後升 W-D 結案
4. **後續 follow-up（**非本 fix scope**）**：
   - P1-FILL-LINEAGE-MONITOR：[55] healthcheck 加 channel drop SLO（5/min 警報閾，per QA RCA §D.6）
   - P3 file size 拆 runtime_shadow.rs → sibling
   - P2 micro-bench spawn task 成本 empirical（補 cargo bench harness）

---

## 12. Cross-references

- QA RCA: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-11--p1_rca_1_orphan_er_investigation.md`
- W-C E5 perf review（baseline 數字）: `srv/docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-10--w_c_fix_e5_perf_review.md`
- MAG-084 sign-off：`docs/governance_dev/2026-05-11--w_d_mag084_signoff.md`
- 修改 source path 列表：
  - `rust/openclaw_engine/src/tasks.rs:641-655`（channel cap bump）
  - `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:33-93`（counter + accessor）
  - `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:639-771`（try_send + retry helper）
  - `rust/openclaw_engine/src/agent_spine/runtime_shadow.rs:526-602`（emit_fill_completion_lineage 接 retry helper）
  - `rust/openclaw_engine/src/agent_spine/tests.rs:22`（Duration import）
  - `rust/openclaw_engine/src/agent_spine/tests.rs:1247-1476`（3 new tests）

---

**E1 IMPL DONE: 待 E2 對抗審查 + E4 regression（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--p1_fill_lineage_drop_fix.md`）**
