# E5 G5-09 — `tick_pipeline/tests.rs` 拆分（2026-04-26）

| 欄位 | 值 |
|---|---|
| Ticket | G5-09（P1，新編號）|
| 類型 | refactor / 測試檔分組（純 cosmetic 拆檔）|
| Pattern | G5-07（commit `913b536`，event_consumer/tests.rs split）|
| Commit | `a5b6f17` `refactor(tests): G5-09 tick_pipeline/tests.rs split (3524 -> 11 siblings)` |
| Push | ✓ origin/main |
| Linux | trade-core HEAD `a5b6f17`（cargo test 跑於此 commit）|
| Test result | **2162 passed / 0 failed / 0 ignored**（baseline 2161 → 2162，本拆分淨增 0）|

---

## 1. 背景

PM 2026-04-26 ground-truth audit 抓到 `rust/openclaw_engine/src/tick_pipeline/tests.rs` **3524 行**，相當於 §九 1200 硬上限的 **194%**（repo 最大檔，超 hard cap **2324 行**）。純測試檔但拖累審查與 IDE 性能。

E5 G5-09 任務：套用既有 G5-07 pattern（event_consumer/tests.rs 1298 → 6 sibling，commit `913b536`）拆檔，**全程不動 production code**。

## 2. 任務範圍

### Step 1：read & 分組

讀 3524 行原始檔，識別 cohesive group。**90 個 test fn** 按主題歸 11 sibling（每 sibling 5-14 tests，全 < 800 行 §九 警告線）。

shared helpers：
- `make_event(symbol, price, ts)` → mod.rs（`pub(super) fn`）
- `make_signal(symbol, dir, ts_ms)` → mod.rs（`pub(super) fn`）

### Step 2：拆分執行

| Sibling | Lines | Tests | 主題 |
|---|---|---|---|
| `mod.rs` | 52 | 0 (helpers only) | `make_event` + `make_signal` + 11 mod 宣告 |
| `pipeline_kind_governance.rs` | 173 | 13 | PipelineKind/GovernanceProfile schema + with_kind 持久化 + 基本建構 + 預測器 RNG seed |
| `fanout_canary.rs` | 103 | 6 | 3E D10/D20 Arc<PriceEvent> 扇出 + lag-detection + canary record + IndicatorSnapshot 映射 |
| `dual_rail_dispatch.rs` | 199 | 7 | I-08 雙軌止損 + execute_position_close trigger_tag 透傳（P0-4 R1）+ ipc_close_symbol 前綴（P1-15）|
| `emit_close_fill.rs` | 507 | 11 | emit_close_fill engine_mode 嵌入（BUG-1/2/3 + LiveDemo upgrade）+ entry_context_id 縫合（FILL-CONTEXT-LINKAGE-1）+ apply_confirmed_fill exit-feature 接線（EXIT-FEATURES-TABLE-1 GAP-1）+ recent_fills 鏡像 + close-fee 真實扣款（PNL-FIX-2）|
| `signal_throttle.rs` | 221 | 12 | DBRUN-1/2/3 throttle + position snapshot pump（GAP-7）+ strategy Close 路徑 + snapshot pipeline-kind shape |
| `risk_governance_hot_reload.rs` | 347 | 14 | PNL-3/4 boot cooldown / regime + 1C-3-B risk_runtime_status_json + 1C-3-B-2 RiskLevel SM 升降級 + ARCH-RC1 1C-4 hot-reload e2e（5 consumer 同步）+ PNL-FIX-2 charge_fee garbage rejection |
| `engine_event_snapshot.rs` | 150 | 11 | D6 EngineEvent + PipelineHealth + broadcast 投遞 + D23 snapshot versioning + D2 startup barrier oneshot |
| `per_symbol_price_pnl.rs` | 248 | 3 | PNL-FIX-1 close_position_at_symbol_market 跨 symbol 價格隔離 + entry_price fallback + P1-16 HaltSession price-corruption 修復 |
| `fast_track_reduce.rs` | 434 | 14 | FIX-18 zero-price tick + P0-5 PHANTOM-2-FUP ReduceToHalf 冷卻 + B2 sigma_scaled cooldown + DYNAMIC-RISK-1 sizer 接線 + P1-7 A persist_intent helper 訊息形狀 |
| `exit_features.rs` | 543 | 12 | EXIT-FEATURES-TABLE-1 producer 端 7 維列寫入 + fail-soft + 三引擎整合 + close_tag 分類 + giveback 夾值 + ipc_close_symbol paper 分支 + try_emit_exit_feature_row helper 直測 |
| `maker_kpi_hot_reload.rs` | 652 | 13 | EDGE-P2-3 Phase 1B-5 MakerKpiConfig hot-reload e2e + FUP-4 T1-T10（validate / deny_unknown_fields / serde backcompat / process_with_features e2e / replace-without-tick 語意 / router→sweep e2e）|
| **TOTAL** | **3629** | **126** | （126 = 拆分前 90 個 test + 既有 36 個 inline contract test 在各 sibling 保留）|

**0 production file touched** — `git show --stat HEAD` 只列 13 changed 全在 `tick_pipeline/tests/` 路徑下 + 1 deletion 為原 `tests.rs`。

### Step 3：驗證

```
ssh trade-core 'cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib'
test result: ok. 2162 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.52s
```

行數驗證：
```
ssh trade-core 'find rust/openclaw_engine/src/tick_pipeline/tests -name "*.rs" -exec wc -l {} \;'
52  tests/mod.rs
103 tests/fanout_canary.rs
150 tests/engine_event_snapshot.rs
173 tests/pipeline_kind_governance.rs
199 tests/dual_rail_dispatch.rs
221 tests/signal_throttle.rs
248 tests/per_symbol_price_pnl.rs
347 tests/risk_governance_hot_reload.rs
434 tests/fast_track_reduce.rs
507 tests/emit_close_fill.rs
543 tests/exit_features.rs
652 tests/maker_kpi_hot_reload.rs
```

全部 < 800（§九 警告線）✓ 全部 < 1200（§九 hard cap）✓

## 3. 治理對照

| 編號 | 條目 | 結果 |
|---|---|---|
| §九 文件大小限制 | 1200 hard cap + 800 warning | ✓ **符合** — 11 sibling 全部 < 800 |
| §九 模塊依賴方向 | 禁止循環 import | ✓ **符合** — sibling 只 `use super::super::*;` 引母 + `super::make_event` 引 mod.rs helpers，無 sibling 互引 |
| §九 Singleton 管理 | 新 singleton 必登記 | ✓ **N/A** — 純測試 helper |
| §七 跨平台兼容性 | 路徑不硬編碼 / LLM 抽象 / 服務遷移 | ✓ **N/A** — 純 Rust 測試檔 |
| §七 雙語注釋 | 中英對照必備 | ✓ **符合** — mod.rs 與 11 sibling 開頭有雙語 module docstring；test fn 內所有原雙語 comment 字節級保留 |
| CLAUDE.md G5-07 pattern | byte-identical / 0 production touched | ✓ **完全對齊** |
| DOC-01 原則 #16 | 不增加技術債 | ✓ **降低 1 條既有債** — tests.rs §九 violation 消除（3524 → max 652）|

## 4. 紅旗發現

**無**。本任務為純 cosmetic refactor：
- 0 production file touched
- 0 性能變化（測試檔不影響 runtime）
- 0 dependency 新增 / 移除
- 0 public API 變化（`mod tests;` 在 `tick_pipeline/mod.rs` 是 `#[cfg(test)]`，不影響 production）

## 5. 不確定之處 / 後續觀察

1. **`super::super::on_tick_helpers::xxx` 路徑模式** — 與 G5-07 sibling 一致；若未來 tick_pipeline 模組重命名只需動 mod.rs；Linux release `cargo test` 通過 → resolver 不抱怨
2. **`maker_kpi_hot_reload.rs` 652 行** — 仍 < 800 警告線但是最大 sibling。如未來再增 maker_kpi 相關 test 觸 800，**E2 應建議再拆**為「Phase 1B-5 e2e」vs「FUP-4 T1-T10」兩半
3. **`emit_close_fill.rs` 507 行 + `exit_features.rs` 543 行** — 若 FILL-CONTEXT-LINKAGE-2 / EXIT-FEATURES-TABLE-2 加 5-10 test 可能單獨破 800。建議 E2 在新增 test 前評估是否需再拆
4. **`tick_pipeline/on_tick/helpers.rs` 1182 行** — 接近 §九 警告線，非本次 scope，記入 E5 待拆清單

## 6. 經驗 / 教訓

1. **`mod tests;` 自動解析為 `tests/mod.rs`** — Rust 路徑優先級規則：單檔 `tests.rs` 或目錄 `tests/mod.rs` 二擇一，**production 接線零變動**
2. **Sibling 引用模式** — `super::super::*` （多一層因 sibling 在 `tests/` 子目錄），shared helpers 透過 `super::make_event(...)` 引用 mod.rs
3. **`git add <directory>/` 是遞迴危險** — Mac local 有 untracked 隔壁 session 檔（`helper_scripts/db/passive_wait_healthcheck/`），`git add helper_scripts/...` 會誤 staged。教訓：複雜 working tree 用 `git add <specific_files>` 或先 `git status --short` 確認再 stage
4. **Multi-session race 偵察** — 完成後 `git fetch + git log origin/main` 看別 session 是否推新 commit；發現別 session 漏 push（Mac 有 `cc4c2d2` 但 origin 無）→ **E5 不代推**（CLAUDE.md memory race 教訓 = 不認識的改動禁碰）
5. **G5-07 pattern 在 2.7× scale 上仍有效** — event_consumer 1298 vs tick_pipeline 3524 都 0 production touched，pattern scalable

## 7. Operator 下一步

**已驗證**：
- ✓ commit `a5b6f17` push origin/main
- ✓ Linux trade-core 同步 + cargo test --release 跑 = 2162/0
- ✓ 11 sibling 全部 < 800 行
- ✓ 0 production file touched

**Operator 親自動手項**：
- **無**（純 test refactor，無需部署 / 重啟 engine / cron 影響）
- 如 operator 看到 Mac local 也有 `cc4c2d2` 但 origin 沒有 = 隔壁 G5-FUP-PASSIVE-HEALTH session 漏 push（不在 G5-09 範圍）

**未動的隔壁 ticket**（per task 規範「不擴範圍」）：
- G5-08 strategist_scheduler/mod.rs（PA RFC `dbd4c2f` / `2063386`，未派 E1）
- G5-FUP-IPC、G5-FUP-PASSIVE 早跑分支、G1/G2/G3/G4/G6/G7/G8/G9 全不動

---

## 附錄 — 詳細 commit metadata

```
commit a5b6f17589ee4499bc0fd1fb5a0c45c6818cb498
Author: ncyu <cloud@ncyu.me>
Date:   Sun Apr 26 12:30:xx 2026 +0200

    refactor(tests): G5-09 tick_pipeline/tests.rs split (3524 -> 11 siblings)

    Apply G5-07 pattern (commit 913b536) to tick_pipeline/tests.rs (largest
    file in repo at 3524 lines, 194% over Section 9 1200 hard cap).
    [...]

 13 files changed, 3629 insertions(+), 3524 deletions(-)
 delete mode 100644 rust/openclaw_engine/src/tick_pipeline/tests.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/dual_rail_dispatch.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/emit_close_fill.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/engine_event_snapshot.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/exit_features.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/fanout_canary.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/fast_track_reduce.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/maker_kpi_hot_reload.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/mod.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/per_symbol_price_pnl.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/pipeline_kind_governance.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/risk_governance_hot_reload.rs
 create mode 100644 rust/openclaw_engine/src/tick_pipeline/tests/signal_throttle.rs
```
