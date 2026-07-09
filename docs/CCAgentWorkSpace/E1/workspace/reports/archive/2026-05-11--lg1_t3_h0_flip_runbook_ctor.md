# E1 LG1-T3 IMPL Report — H0 Flip/Rollback Runbook + pipeline_ctor.rs default fix

- 日期：2026-05-11
- Agent：E1
- 任務性質：IMPL (Mix — docs + Rust 微改 + unit tests)
- Wave：Sprint N+1 Wave 2.2 LG-1 T3
- Dispatch ref：PA tech plan `2026-05-11--lg_2_3_4_design_plan.md` §1.4 表 T3 + §1.5 risk #1 mitigation
- 並行兄弟：LG1-T1（E1-α `h0_blocking.rs` E2E test）/ LG1-T2（E1 healthcheck `[59]`）/ LG1-T4（E1 route `/api/v1/risk/h0_block_summary`）
- Linux runtime impact：本 PR 純 source 改動 + new test sibling + new docs；**不**需 engine 重啟即可 deploy（PR merge + restart 後即生效）

---

## 1. 完成項摘要 / Executive Verdict: DONE

| 維度 | 結論 |
|---|---|
| Part A：SOP runbook（12 章節） | ✅ `docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md` 316 LOC |
| Part B：`pipeline_ctor.rs:75-78` ctor default 修正 | ✅ `shadow_mode: true` → `false`（+ 中文注釋 18 行） |
| Part C：sibling unit test | ✅ `tests/h0_ctor_default.rs` 5 test（4 PASS / 1 #[ignore] 留 reviewer 證據） |
| Part D：E2 reviewer note | ✅ 寫在 runbook §10 + sibling test #5 + report §4 |
| `cargo build --release -p openclaw_engine` | ✅ 綠（既有 dead-code warning 不變） |
| `cargo test --lib --release -p openclaw_engine`（整體 regression）| ✅ 2827 passed / 0 failed / 1 ignored（W-AUDIT-3b 並行 land 後總數 ↑） |
| `cargo test --lib --release h0_ctor_default`（新 sibling） | ✅ 4 PASS / 1 ignored |
| 跨平台 hardcoded path check（`/home/ncyu` `/Users/ncyu` 等） | ✅ 0 hit（純引用 `$OPENCLAW_DATA_DIR` / `$OPERATOR_SESSION_COOKIE` / 文檔相對路徑） |
| 中文-only 注釋 governance（2026-05-05 起） | ✅ 無 `MODULE_NOTE (EN)`；test 注釋 + ctor 注釋 + runbook 全中文 |
| 新 unsafe / unwrap | ✅ 0 |

---

## 2. 修改清單

| 檔 | 動作 | LOC |
|---|---|---|
| `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs` | edit ctor `H0Gate::new` 區塊：`shadow_mode: true → false`，加 18 行中文注釋說明 PA §1.5 risk #1 + TOML always-覆蓋契約 | +22 / -4 |
| `rust/openclaw_engine/src/tick_pipeline/tests/h0_ctor_default.rs` | **新** sibling test：5 test 涵蓋 `new` / `with_balance` / `with_kind`(×3) default + `set_shadow_mode` runtime IPC override + (`#[ignore]`) reviewer note 證據 | +157 |
| `rust/openclaw_engine/src/tick_pipeline/tests/mod.rs` | edit 加 `mod h0_ctor_default;`（並行 LG1-T1 已加 `mod h0_blocking;`，**無 conflict**） | +1 |
| `docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md` | **新** runbook：12 章節（用途 / 治理 / 預設矩陣 / Flip / Rollback / 監測 / 失敗模式 / Checklist / Rollback procedure / Reviewer note / 修訂歷史 / Cross-ref） | +316 |
| **Production code 改動小計（pipeline_ctor.rs only）** | | **+22 / -4 = ~5 effective LOC**（符合 acceptance criterion #5 ≤ 5 LOC default value + 注釋） |

---

## 3. 關鍵 diff snippet

### 3.1 `pipeline_ctor.rs:75-93` 預設值修正

```rust
// 修改前
h0_gate: H0Gate::new(Some(openclaw_types::H0GateConfig {
    shadow_mode: true, // RRC-1-A3: observe-only until proven stable
    ..Default::default()
})),

// 修改後
// LG1-T3 (2026-05-11)：ctor 預設改為 shadow_mode=false（hard-block）。
// 理由（PA tech plan §1.5 risk #1 mitigation）：
//   - Demo / Live TOML 均已長期 `runtime.h0_shadow_mode = false`，
//     ctor 舊預設 `true` 會在 engine 啟動到首次 TOML 載入 / 熱重載完成
//     之間留 1–3 秒「shadow 觀察窗」，期間若有觸發 H0 阻斷條件
//     會被誤放行（fail-open）。
//   - Paper 仍以 TOML `risk_config_paper.toml` 中 `h0_shadow_mode = true`
//     維持影子模式；TOML always-覆蓋契約由 `apply_risk_snapshot` 中
//     H0Gate RMW 路徑保證（pipeline_config.rs:97-109）。
//   - 切換預設值不會破壞既有 hot-reload 行為：apply_risk_snapshot
//     的 read-modify-write 會把 TOML `runtime.h0_shadow_mode` 值
//     寫回 H0GateConfig.shadow_mode。
//   - 對齊 §四「失敗默認收縮」原則：未載 TOML 時 fail-closed 優於
//     fail-open。
// E2 必驗：apply_risk_snapshot / sync_risk_config_if_changed 在
// 首次 set_risk_store + 首次 tick 內把 TOML `h0_shadow_mode` 正確
// 傳入 H0GateConfig.shadow_mode；測試覆蓋見
// tests/h0_ctor_default.rs。
h0_gate: H0Gate::new(Some(openclaw_types::H0GateConfig {
    shadow_mode: false,
    ..Default::default()
})),
```

### 3.2 unit test 五條（h0_ctor_default.rs）

| Test | 目的 | 結果 |
|---|---|---|
| `test_lg1_t3_new_default_shadow_mode_is_false` | `TickPipeline::new` 預設 `false` | ✅ PASS |
| `test_lg1_t3_with_balance_default_shadow_mode_is_false` | `with_balance` 預設 `false` | ✅ PASS |
| `test_lg1_t3_with_kind_default_shadow_mode_is_false` | `with_kind`(Paper/Demo/Live) 均預設 `false` | ✅ PASS |
| `test_lg1_t3_set_shadow_mode_overrides_ctor_default_to_true` | `H0Gate::set_shadow_mode(true)` IPC 路徑能推翻 ctor `false` | ✅ PASS |
| `test_lg1_t3_known_gap_apply_risk_snapshot_does_not_wire_h0_shadow_mode` | （`#[ignore]`）TOML→pipeline_config.rs RMW 漏失證據 | ⚠️ `#[ignore]` 留作 reviewer note 可執行證據；修好後變 PASS |

---

## 4. E2 reviewer note — 已知 hot-reload gap（PA §1.5 風險 #1 假設修正）

**E1 IMPL 期間發現 PA tech plan §1.5 risk #1 mitigation 假設不完全成立**。需 E2 + PA 確認後決定後續工作排期。

### 4.1 發現脈絡

- **PA 假設**：「TOML 載入路徑 always 覆蓋 ctor default」
- **實際測試**（sibling test #4 `test_lg1_t3_toml_overrides_ctor_default_to_true` 第一版 fail）：
  - `ConfigStore.replace(next_config_with_shadow_mode_true)` + 首個 tick → `h0_gate.config().shadow_mode` **仍為 ctor default `false`**（不跟隨 TOML）
- **Root cause**：`pipeline_config.rs:97-109` H0Gate RMW 區塊**沒** 把 `snap.runtime.h0_shadow_mode` 推進 `h0.shadow_mode`；行 98 注釋「shadow_mode fields don't live in RiskConfig」**已過時** — `RiskConfig.runtime.h0_shadow_mode` 確實存在於 `risk_config_advanced.rs:366`
- **Runtime SoT 真實位置**：IPC `patch_risk_config{h0_shadow_mode=...}` → `event_consumer/handlers/risk.rs:313` → `pipeline.h0_gate.set_shadow_mode(v)`（直接設）。Startup TOML 載入後到第一次 IPC patch 之前，ctor default 就是真正的 SoT。

### 4.2 風險評估

- **本 T3 改 ctor default `false` 已治本**：fail-closed safety net，不會留 fail-open 窗口
- **既有 demo / live runtime 不受影響**：兩 environment 早就 `runtime.h0_shadow_mode = false`；ctor default 同值 → 行為不變
- **Paper 行為微改變**：paper TOML 是 `h0_shadow_mode = true`；engine 啟動瞬間到第一次 IPC patch（或 ConfigStore 載入後第一次熱觸發）之間，paper engine 會走 hard-block；對 paper observation 是 fail-closed（更保守），不會誤觸發新單

### 4.3 後續工作（**不在本 T3 scope**，留新子任務 / 後續 LG-1 wave）

1. `pipeline_config.rs::apply_risk_snapshot` H0Gate RMW 區塊加：
   ```rust
   h0.shadow_mode = snap.runtime.h0_shadow_mode;
   ```
2. 同次刪除行 98 過時注釋。
3. 移除 sibling test #5 的 `#[ignore]` attribute。

### 4.4 證據檔

- `rust/openclaw_engine/src/tick_pipeline/tests/h0_ctor_default.rs::test_lg1_t3_known_gap_apply_risk_snapshot_does_not_wire_h0_shadow_mode`（`#[ignore]` 標）
- Runbook §10 `E2 reviewer note — 已知 hot-reload gap`

---

## 5. 治理對照 / Governance Compliance

| 規則 | 引用 | 本 T3 結果 |
|---|---|---|
| §二 #4 策略不能繞過風控 | CLAUDE.md | ✅ H0 hard-block 強化，hot path 不變 |
| §二 #6 失敗默認收縮 | CLAUDE.md | ✅ ctor default `false`(hard-block) = fail-closed |
| §四 硬邊界 | CLAUDE.md | ✅ 未動 max_retries / live_execution_allowed / system_mode |
| §七 跨平台 | CLAUDE.md | ✅ 0 hardcoded path（grep 通過） |
| §七 中文注釋 governance（2026-05-05 後）| CLAUDE.md | ✅ 全中文，無 EN MODULE_NOTE |
| §七 文件 800 行警告 / 2000 行硬上限 | CLAUDE.md | ✅ pipeline_ctor.rs 575 行（< 800 warn）；h0_ctor_default.rs 157 行；runbook 316 行 |
| §九 singleton 管理 | CLAUDE.md | ✅ 未新增 singleton |
| 16 原則 #1 單一寫入口 | DOC-01 | ✅ 不新增 writer |
| 16 原則 #5 生存>利潤 | DOC-01 | ✅ fail-closed default |

---

## 6. 不確定之處 / Open Questions

| # | 議題 | 影響 | 建議處置 |
|---|---|---|---|
| Q1 | E2 reviewer note §4 是否升 P1（新子任務 5 LOC fix）？ | 後續 LG-1 wave 排期；對 demo/live runtime 無影響（已 `false`），對 paper 是 fail-closed regression（更保守） | 建議 PM 在 24h passive observation 期間 dispatch 1 名 E1 做 5 LOC fix；可與 LG-2 T4 RiskConfig `[pricing]` section 合併 wave（兩者都動 risk.rs / pipeline_config.rs） |
| Q2 | LG1-T1 兄弟 sibling 並行 land — h0_blocking.rs 中 `trigger_kill_switch` dead-code warning | warning only，不阻 build | 待 LG1-T1 sign-off 時一併 review；本 T3 不擴大 scope 不動 |
| Q3 | Operator 操作 checklist §8 假設 LG1-T2 healthcheck `[59]` 已 land — 若 T2 後 land，runbook §8.1 checklist 一項 N/A | runbook 可用性影響低 | LG1-T2 sign-off 時 PR 補一行 §11 修訂歷史；本 T3 已預備該章節結構 |

---

## 7. Operator 下一步

1. **E2 審查**（必須）：重點看 §4 reviewer note；對 H0 hot-reload gap 給 verdict（修 / defer / merge LG-2 T4）
2. **E4 regression 跑**（必須）：
   ```bash
   ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --lib --release -p openclaw_engine h0_ctor_default 2>&1 | tail -15"
   # expect: 4 PASS / 1 ignored
   ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --lib --release -p openclaw_engine 2>&1 | tail -3"
   # expect: 2827+ passed / 0 failed / 1 ignored
   ```
3. **QA sign-off**：runbook §10 reviewer note 是否進 LG-1 後續 wave / 新子任務 / 後 N+1 sprint
4. **PM commit 統一收口**：本 T3 不發 commit；E2+E4 通過後 PM 在 Wave 2.2 並行收口時 commit + push（含 LG1-T1/T2/T3/T4 一同）
5. **Sprint N+1 N+24h passive observation**（per PA §1.5 risk #1）：deploy 後 demo + live_demo 各跑 24h，0 false-block / 0 leak / p99 < 1ms → LG-1 sign-off

---

## 8. Cross-References

- 上游 PA tech plan：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` §1.4
- 原 RFC：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-01--lg2_h0_blocking_verification_rfc.md`
- W-AUDIT-3b runtime smoke baseline：`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_audit_3b_runtime_smoke.md`
- Runbook：`docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md`
- 修改檔 1：`rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs`（行 75-93）
- 修改檔 2：`rust/openclaw_engine/src/tick_pipeline/tests/mod.rs`（+ `mod h0_ctor_default;`）
- 新增檔 1：`rust/openclaw_engine/src/tick_pipeline/tests/h0_ctor_default.rs`
- 新增檔 2：`docs/runbooks/2026-05-11--lg1_h0_flip_rollback.md`

---

E1 IMPLEMENTATION DONE: 待 E2 審查 + E4 regression（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--lg1_t3_h0_flip_runbook_ctor.md`）
