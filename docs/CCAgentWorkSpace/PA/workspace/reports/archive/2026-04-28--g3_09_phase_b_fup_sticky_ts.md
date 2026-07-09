# PA Report — G3-09-PHASE-B-FUP-STICKY-TS (sticky `triggered_at_ms`)

**日期**：2026-04-28
**Ticket**：G3-09-PHASE-B-FUP-STICKY-TS（P2 prep-gate for Phase B impl）
**Worktree base HEAD**：`82347a5`（origin/main）
**Worktree branch**：`worktree-agent-aeb618f0d004b3366`
**Status**：完成（待主會話 commit + push + Linux deploy）

---

## §1 任務背景

E2 Phase A daemon test review report `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-27--g3_09_daemon_test_review.md` 揪出 INFO 級 doc/code drift：

- `rust/openclaw_engine/src/cost_edge_advisor/advisor.rs:114-120` 註解聲稱 daemon 會於 follow-up `store_state` cycle 覆寫 `triggered_at_ms`，暗示 Trigger→Trigger sticky 行為已實作
- **實際** `rust/openclaw_engine/src/cost_edge_advisor/mod.rs` daemon body 0 此邏輯：每個 evaluate cycle 呼叫 `evaluate()` → `evaluate()` 對任何 Trigger 狀態永遠回 `triggered_at_ms = now_ms` → daemon 直接 `store_state(new_state)` → 連續 Trigger run 期間時戳每 cycle 被 100ms-10s 推進，「進入時間」資訊永久遺失
- Phase A 純 advisory 路徑 0 trade impact，所以這個 drift 不會影響當前 production
- **但** Phase B Shadow（PA RFC `2026-04-27--g3_09_phase_b_shadow_dryrun_design.md`）規劃 `last_trigger_ms` rolling counter 與 dedup 觀察，若沿用現行非 sticky 行為將出 bug — 屬 Phase B Wave 1（V026 + INSERT path）派發前必修的 prep-gate

操作者授權 PA 三角合一執行（PA design + 直接寫 ≤80 LOC Rust + 自寫 ≥2 unit test），不擴 scope 至 Phase B impl。

---

## §2 設計決策：選 A（daemon enforce sticky）

### 候選

| 選項 | 描述 | 落地工時 | 對 Phase B 影響 |
|---|---|---|---|
| **A** | daemon body 加 sticky 保留邏輯：non-Trigger → Trigger 抓 `now_ms`、Trigger → Trigger 保留前次值、Trigger → 非 Trigger 清零 | ~30 LOC + 2 test | Phase B `last_trigger_ms` 與 dedup 邏輯可直接讀 `triggered_at_ms` 不需另存 |
| B | 保現行行為 + 改 advisor.rs 註解去除 sticky 聲稱 | ~5 LOC docstring | Phase B Wave 1 必須**自己**維護 sticky timestamp 在 daemon 內，重複工作；user-visible「Trigger 第一次發生時間」資訊永久遺失 |

### 選 A 理由

1. **避免 Phase B 二次踩雷**：Phase B RFC §3.1 line 247 schema 已預留 `triggered_at_ms` 欄位給 dedup analytics 用，若 Phase B 才補 sticky 會牽動 Phase B 範圍
2. **語意正確性 > LOC 預算**：`triggered_at_ms` 命名語意是「進入時間」，現行行為（每 cycle 推進）違反命名
3. **30 LOC ≪ 80 LOC 上限**：操作者 prompt 設 80 LOC 上限，A 案 daemon 改動約 30 LOC + 各檔 docstring 約 25 LOC，仍餘裕
4. **單純 daemon-local state**：sticky 用 `let mut sticky_triggered_at_ms: i64 = 0;` 在 daemon task scope 內維護，**0 共享 state**，0 race condition，0 額外 lock
5. **`evaluate()` 純 fn 性質保留**：sticky 由 daemon 對 `new_state.triggered_at_ms` 後處理，pure fn 簽名 / 行為 / 測試全不動 — `src/cost_edge_advisor/tests.rs` 32 既存 case 全綠

---

## §3 實作 diff stat

| 檔 | +/- LOC | 性質 |
|---|---|---|
| `rust/openclaw_engine/src/cost_edge_advisor/mod.rs` | +51 / -2 | daemon body 加 sticky enforce match arm + 雙語 docstring + warn! log 加 `triggered_at_ms` field |
| `rust/openclaw_engine/src/cost_edge_advisor/advisor.rs` | +24 / -16 | 模組 doc + Trigger constructor inline 註解對齊實作 |
| `rust/openclaw_engine/src/cost_edge_advisor/types.rs` | +9 / -4 | `triggered_at_ms` field doc 對齊實作 |
| `rust/openclaw_engine/tests/test_cost_edge_advisor_daemon.rs` | +175 / -1 | 新建 `h_state_cache_with_persistent_trigger()` builder + 2 sticky test + 區段 docstring |

**總 production code（mod.rs + advisor.rs + types.rs）**：+84 / -22 = **net +62 LOC**（含 ~25 LOC docstring，純邏輯約 +37）
**總 test code**：+175 / -1 = +174 LOC（2 test + 1 builder + 區段 doc）
**結果**：在 80 LOC 上限內（A 案不需要降為 B）

---

## §4 sticky 邏輯核心

`mod.rs` daemon spawn body 內，於 `evaluate()` 後、`store_state()` 前加 4-arm match：

```rust
match (&prev_status, &new_state.status) {
    // 持續 Trigger 區段 — 保留原進入時戳
    (CostEdgeAdvisorStatus::Trigger, CostEdgeAdvisorStatus::Trigger) => {
        new_state.triggered_at_ms = sticky_triggered_at_ms;
    }
    // 從其他狀態進入 Trigger — 記錄進入時戳
    (_, CostEdgeAdvisorStatus::Trigger) => {
        sticky_triggered_at_ms = new_state.triggered_at_ms;
    }
    // 離開 Trigger — 清零（state factory 對 non-Trigger 已預設 0）
    (CostEdgeAdvisorStatus::Trigger, _) => {
        sticky_triggered_at_ms = 0;
    }
    // 非 Trigger → 非 Trigger — sticky 不動
    _ => {}
}
```

**狀態跟蹤變數**：`let mut sticky_triggered_at_ms: i64 = 0;`（與 `let mut prev_status` 同 scope，daemon task 啟動時初始化，task 結束自然 drop，0 共享，0 race）

---

## §5 驗收

### 5.1 cargo build clean

```
cargo build --release -p openclaw_engine --tests
→ Finished `release` profile [optimized] target(s) in 50.81s
→ 0 errors, 既有 warnings 不變（no new warnings）
```

### 5.2 daemon integration test：6/0 → **8/0**

```
cargo test --release -p openclaw_engine --test test_cost_edge_advisor_daemon
→ test result: ok. 8 passed; 0 failed; 0 ignored
```

新增兩 test：
1. **`sticky_triggered_at_ms_records_first_entry_into_trigger`** — 證明首次進 Trigger 時 `triggered_at_ms` 落在 `[before_spawn_ms, after_first_ms]` 真實 epoch 視窗內（non-zero、合理、來自 daemon `now_ms()`）
2. **`sticky_triggered_at_ms_preserved_across_contiguous_trigger_cycles`** — 證明連續 ≥3 個 Trigger cycle（用 100ms cadence + 推進的 `last_eval_ms` 抓 distinct cycle）期間，`triggered_at_ms` 跨所有 cycle bit-equal 不變；同步 assert `last_eval_ms` 嚴格遞增證明真觀察到多輪 cycle 而非同 snapshot 採樣 3 次

### 5.3 lib test 維持 2290 / 0

```
cargo test --release -p openclaw_engine --lib
→ test result: ok. 2290 passed; 0 failed; 0 ignored
```

`src/cost_edge_advisor/tests.rs` 32 case 全綠不變（pure `evaluate()` 行為未動）。

### 5.4 Phase A advisory-only 路徑 0 production behavior change

- `evaluate()` pure fn 行為未動 → `src/cost_edge_advisor/tests.rs` 全綠
- IPC handler `state()` 讀 `Arc<RwLock<CostEdgeAdvisorState>>` 的方式未動
- E2 + E4 已在 commit `af66ac1` 驗 Phase A clean window — sticky enforce 不改 status / ratio / threshold 任一觀察值，僅影響 `triggered_at_ms` 一欄，且 Phase A 的 IPC consumer (healthcheck `[30]`) 對該欄無語意依賴（schema 哨兵）

### 5.5 16 根原則 / 9 安全不變量

無觸碰：
- 原則 #4（策略不繞風控）— 0 trade path 改動
- 原則 #5（生存>利潤）— sticky 不改任何止損或風險邊界
- 原則 #13（AI 成本感知）— 本身就是強化 #13 的觀測精度
- DOC-08 §12 9 不變量 — daemon shutdown / cancel_token 行為未動，整合 test `daemon_cancellation_drains_within_one_second` 仍綠

---

## §6 跨平台兼容性（CLAUDE.md §七 ★★）

- 0 hardcoded path（純 Rust in-memory state）
- 0 LLM / Bybit API 調用
- 0 systemd / launchd 依賴
- 0 新依賴（`requirements.txt` 不變）

---

## §7 雙語注釋（CLAUDE.md §七 強制）

3 production file 改動全配 EN + 中文 docstring，inline 雙語標記 sticky semantic：
- `mod.rs` daemon body：`// Sticky `triggered_at_ms` enforcement (G3-09-PHASE-B-FUP 2026-04-28)` + 雙語 paragraph
- `advisor.rs` Trigger constructor inline + 模組 doc 段
- `types.rs` `triggered_at_ms` field doc

---

## §8 對 Phase B impl 的影響

**正面**：Phase B Wave 1 RFC §3.1 schema 設計可直接讀 `triggered_at_ms` 取「Trigger episode 進入時間」語意，**不需** Phase B 自己再維護 sticky state — Wave 1 工時估約 1d 不變（純加 V026 + INSERT path + counter rolling，sticky 已 baked in）。

**RFC §3.1 一致化**：Phase B 加的 `last_trigger_ms` field 與本次 sticky `triggered_at_ms` 語意上重疊但**不衝突**：
- `triggered_at_ms` = 當前 contiguous Trigger run 進入時戳（非 Trigger 為 0）
- `last_trigger_ms` = 24h rolling 內最後一次 Trigger transition 時戳（無論當前 status；Trigger 結束後仍保留供 historical analytics）

兩者語意正交。建議 Phase B Wave 1 接收本次 PR 後，在 RFC §3.1 加 1 行 note 確認語意分工。

---

## §9 主會話交接

1. **Commit 順序**（worktree pattern）：主會話統一 commit + push（不在本 PA worktree commit）
2. **Mac 驗證已完成**（本 PA 已跑）：
   - cargo build release tests = clean
   - cargo test daemon integration = 8 passed
   - cargo test lib = 2290 passed
3. **Linux deploy**：sticky 邏輯改變僅影響 `triggered_at_ms` 一欄，當前 Phase A advisory-only 路徑無 consumer 依賴此欄 → 不需 priority deploy；Phase B Wave 1 派發時 `--rebuild` 一併套入即可
4. **無 healthcheck 改動**：`[30] cost_edge_advisor_schema_sentinel` 仍是 schema 哨兵，未升級為 sticky 行為驗證（屬 Phase B Wave 1 範圍）
5. **無新 TODO**：本 PR 自閉環，已闡述 Phase B 對接點

---

## §10 報告路徑

`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--g3_09_phase_b_fup_sticky_ts.md`（本檔）
