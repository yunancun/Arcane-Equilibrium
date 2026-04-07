# Session ARCH-RC1 1C-2 Complete + 1C-3 Scoped — Pre-Compact Worklog (2026-04-07 PM)

> 接續 `2026-04-07--session_arch_rc1_1c1_1c2.md`。本 session 把 1C-2 phase 完整收尾並寫好 1C-3 接手規格。下個 session 從 1C-3-A 開始。

---

## 1. Session 目標與實際完成

**開場**：繼續 1C-2-C IPC 寫端點。
**完成**：
1. **1C-2-C** 6 個 unified Config IPC 寫端點 (`get/patch_{risk,learning,budget}_config`)
2. **1C-2-E** V014 `observability.engine_events` audit 表（schema apply + 寫入 hook）
3. **1C-2-D** 舊 `operator_risk_config.json` → TOML 一次性遷移
4. **1C-2-E audit wiring** patch 成功時 fire-and-forget 寫一行 V014
5. **1C-3 scoping doc** `docs/references/2026-04-07--arch_rc1_1c3_scope.md`（不含程式碼）
6. **文檔大清理**：CLAUDE.md / TODO.md / MEMORY.md 過時條目歸檔

---

## 2. Commits（5 個 + docs/cleanup commits）

```
5f87bca  feat(ipc): ARCH-RC1 1C-2-C — 6 unified Config IPC endpoints
de75191  feat(db): V014 engine_events audit table (1C-2-E schema)
950f547  feat(config): ARCH-RC1 1C-2-D — one-shot legacy JSON → TOML migration
b0fa2c6  feat(ipc): ARCH-RC1 1C-2-E audit wiring — V014 rows on patch success
(pending) docs: ARCH-RC1 1C-2 wrap + 1C-3 scope + memory cleanup
```

**Stats**：engine lib 714 → **725** (+11 tests · 0 regression) · core/types 不變 · all green。

---

## 3. 1C-2-C 設計決策

### IPC 端點 6 個
- `get_risk_config` / `get_learning_config` / `get_budget_config` — 回傳 `{config: <full snapshot>, version}`
- `patch_risk_config` / `patch_learning_config` / `patch_budget_config` — 接 `{patch: <object>, source?: "operator"|"agent"|"migration"}`

### Patch flow
1. `params.patch` 必為 object 否則 -32600
2. `source` 預設 `operator`，invalid → -32600
3. `store.load()` → `serde_json::to_value()` → `json_merge(current, patch)` 深合併
4. `serde_json::from_value::<T>()` 反序列化（型別錯誤即 -32600）
5. `validate(&next)` 跨欄位不變量
6. `store.replace(next, source)` 原子替換 + version++
7. 成功 → tracing::info! + spawn V014 audit insert

### Generic helpers
```rust
fn json_merge(base: &mut Value, patch: &Value)
fn handle_get_config<T: Serialize>(...)
fn handle_patch_config<T, V>(... validate: V, ... audit_pool: &Option<PgPool>)
```
所有 3 種 Config 走同一條 generic path，零重複代碼。

### 與 legacy `update_risk_config` 的關係
舊 `update_risk_config`（channel-based, 20+ flat field params）**保留不動**，但它 bypass ConfigStore，所以**不會觸發 hot-reload**。1C-3 階段 Python 改用新端點後可移除。

---

## 4. 1C-2-E V014 設計

### Schema (`sql/migrations/V014__engine_events.sql`)
```sql
CREATE TABLE observability.engine_events (
    id BIGSERIAL PRIMARY KEY,
    ts_ms BIGINT NOT NULL,
    event_type TEXT NOT NULL,  -- startup|shutdown|config_patch|config_reject|reconcile|crash
    source TEXT,               -- operator|agent|migration|startup|system
    config_name TEXT,          -- risk|learning|budget|NULL
    old_version BIGINT,
    new_version BIGINT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```
3 indexes: `ts DESC`, `(event_type, ts DESC)`, partial `(config_name, new_version DESC)`.
Live PG 已 apply。

### Audit wiring 設計
- `IpcServer` 加 `audit_pool: AuditPoolSlot = Arc<RwLock<Option<PgPool>>>`
- `main.rs` 在 `db_pool.connect()` 成功後 `audit_pool_slot.write().replace(pg.clone())`
- 連線 accept 時 snapshot read 取出 pool（小成本，1 await per connection）
- `handle_patch_config` 成功分支：`tokio::spawn` INSERT，失敗只 WARN log，不影響 patch 結果
- Payload 內 `{fields_changed: [top-level patch keys]}`

**Fail-soft 鏈**：db_pool 不可用 → audit_pool 永遠 None → patch 仍成功，只少一行審計記錄。

---

## 5. 1C-2-D legacy migration 設計

### 新模組 `config/legacy_migration.rs`（~280 行 / 5 tests）
- `migrate_legacy_risk_json_if_needed(dir: &Path) -> Result<MigrationOutcome, String>`
- 三種結果：`TomlExists` / `NoLegacyJson` / `Migrated(PathBuf)`
- 從 `RiskConfig::default()` 起手，套用 ~15 個 `global_config.*` 已知欄位（stop_loss / take_profit / leverage / drawdown / categories / margin_mode / position_mode / consec_loss / holding_hours / 等）
- 跨 Config field `max_cost_edge_ratio` → log WARN（屬 BudgetConfig.attention_tax，operator 自行 patch_budget_config 套用）
- 驗證後 `save_toml()` → rename 舊 JSON 為 `.legacy`
- 失敗非致命：log WARN + 引擎用 `RiskConfig::default()` 啟動

### 呼叫點
`main.rs::load_unified_configs` 開頭，在 `load_toml_or_default` 之前。下次重啟自動執行。

---

## 6. 1C-3 接手清單（NEXT SESSION 起點）

**一定先讀：**
1. **`docs/references/2026-04-07--arch_rc1_1c3_scope.md`**（本 session 新寫，5 sub-batch + DoD）
2. 本 worklog
3. `memory/project_arch_rc1_unified_config.md`

**1C-3-A 第一動作**（fresh session 開頭）：
```bash
# Re-verify live surface
grep -hrn "risk_manager\.\w\+\|RISK_MANAGER\." program_code/exchange_connectors/bybit_connector/control_api_v1/app/ --include="*.py" | grep -v test_
```

**1C-3 5 個 sub-batch**：
- A: gap analysis + IPC surface design (~3h, no code)
- B: build `RiskViewClient` + `atr_tracker.py` (~4h)
- C: migrate `risk_routes.py` (~3h)
- D: migrate 14 importers + delete dead code (~5-6h)
- E: final cleanup + docs (~2h)

**Total**: 17-20h ≈ 3 sessions across 2-3 days.

---

## 7. 文檔清理 (本 session 後段)

### CLAUDE.md (40K → 目標 ≤ 25K)
- §三 詳細歷史 commit 區塊 (Phase 0/1/2/3 細節) → 歸檔到 `docs/archive/2026-04-07--claude_md_history_phase0_3.md`
- 保留：§一/§二/§四/§五/§六/§七/§八/§九/§十一 + §三 最近 3 條 (1C-2/4.1/4)
- §十一 one-liner 更新到 1C-2 完整收尾

### MEMORY.md 索引清理
- 歸檔 6 條過時/已完成的 project_*：
  - `project_batch9_decisions.md` (Phase 1-era)
  - `project_rust_cutover_decision.md` (已完成)
  - `project_rust_migration_status.md` (已完成)
  - `project_openclaw_deep_analysis.md` (純研究)
  - `project_local_strategy_plan.md` (早期計劃)
  - `project_gui_upgrade_plan.md` (大部分已實現)
- 移到 `memory/archive/` 子目錄
- MEMORY.md 索引相應移除這 6 行
- 保留所有 feedback_*（行為準則）+ 核心 project_*

### TODO.md 清理
- 標記所有完成的 1C-2-A..E
- 刪除 Phase 0a-2b infra 重複描述（已散落多區塊）
- 加入 1C-3-A..E 子任務清單

---

## 8. 此 session 沒做的事

- ❌ 1C-3 任何代碼改動（按計劃 defer 到下個 session）
- ❌ ATR Rust IPC endpoint（1C-3-A 才決定要不要做）
- ❌ Position Reconciler / NewsPipeline spawn（1C-4）
- ❌ E2/E4/QA full audit（1C-4 末尾統一做）
- ❌ Restart engine 載入新 binary（live 仍跑舊版）

---

## 9. Compact 後三步

1. 讀 `docs/references/2026-04-07--arch_rc1_1c3_scope.md`
2. 讀本 worklog
3. 從 1C-3-A grep audit 開始
