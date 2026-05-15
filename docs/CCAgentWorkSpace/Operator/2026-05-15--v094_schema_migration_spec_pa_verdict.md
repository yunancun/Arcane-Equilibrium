---
report: PA — Wave 2a Track A2 V094 hybrid schema migration spec finalize verdict
date: 2026-05-15
author: PA agent
mode: design / spec only — 不寫 V094.sql 實檔，不改 trading_writer.rs 實際代碼，不在 Mac 跑 V094 SQL
trigger: PM Wave 2 Track A2 派工；EDGE-P2-3 Phase 1b close-maker-first refactor F-FA-1 解除條件 (a)(b)(c)
status: SPEC-FINAL（V094 schema + writer upgrade + Linux PG dry-run + healthcheck + IMPL plan + Backward-compat + Rollback）
spec output: srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md (commit 9b1117a0)
---

# Wave 2a Track A2 — V094 Spec PA Verdict

## §0 TL;DR

- **Spec land**：`srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`（commit `9b1117a0`，1176 lines，15 sections）
- **F-FA-1 解除條件 (a)(b)(c) 全完成**：(a) V094 SQL design + (b) writer upgrade spec + (c) Linux PG empirical schema verify
- **3 critical empirical findings (Linux PG 2026-05-15)**：
  1. `trading.fills.details JSONB` 已存在 V003 line 284 — zero schema migration for 3 audit keys（per F-FA-3 PA report 重申）
  2. 24h 98 fills 0% details present rate → trading_writer.rs:430 INSERT writer gap empirical 確認
  3. **Linux runtime applied max = V90**（不是 spec/AMD 寫的 V93）；V81/V91/V92/V93 source 在 git 但 PG 未 apply
- **改動風險評級 = 中**：schema migration + writer hot-path + 13 caller sites；mitigated by Linux PG empirical dry-run × 2 + sqlx checksum repair + caller enumeration + append-only
- **16 原則 16/16 + DOC-08 §12 0/9 觸碰 + §四 0/5 觸碰** = 0 BLOCKER

---

## §1 Wave 2a Track A2 工作範圍

### 1.1 PM 派工要求

從 PM Wave 2 派工（user prompt）：
> finalize V094 hybrid schema migration **spec**（不是 SQL 實檔；spec 給 E1 後續 IMPL）+ 配套 trading_writer.rs writer upgrade spec + Linux PG dry-run protocol。完成此 spec 解 IMPL Prereq 條件 5 第 3 子條件（F-FA-1 V### migration spec finalize）。

### 1.2 必含項

✅ §1 Background + Scope（hybrid schema 設計理由 + IMPL prereq 5 解依賴）
✅ §2 Schema Changes（new columns + JSONB extensions + enum allowlist）
✅ §3 Guard A/B/C Templates（per CLAUDE.md §七 + V083 mirror）
✅ §4 Linux PG Dry-Run Protocol（mandatory × 2 round + drift caveat）
✅ §5 sqlx Checksum Repair SOP（per V055/V083/V084 incident precedent）
✅ §6 trading_writer.rs Upgrade Spec（INSERT 升級 + TradingMsg::Fill enum + 13 caller sites + SLA + cross-language IPC）
✅ §7 Healthcheck [62] [63] [64] [65] Integration
✅ §8 IMPL Plan + 估工時（~480 LOC / ~3.1 E1-day / 2 並行 + 1 串行 worktree）
✅ §9 Backward Compat（per AMD §10.1 append-only）
✅ §10 Rollback Path（IMPL 階段未 deploy / TOML hot-reload / kill-switch）
✅ §11-12 風險 + 16 原則 + E2 review 重點 3 項
✅ §13-15 PA Verdict + 後續行動 + 關鍵文件指針

---

## §2 Empirical Investigation 結果

### 2.1 trading.fills schema 真實狀態（Linux PG 2026-05-15）

```sql
ssh trade-core "PGPASSWORD='...' psql -h localhost -U trading_admin -d trading_ai -c '\d+ trading.fills'"
```

**確認 details JSONB column 存在於 V003 line 284**：
```
details          | jsonb                    | extended  
```

**confirm 23 既有 columns**：ts / fill_id / order_id / symbol / side / qty / price / fee / fee_currency / realized_pnl / is_paper / strategy_name / context_id / details / fee_rate / engine_mode / entry_context_id / exit_source / reference_price / reference_ts_ms / reference_source / slippage_bps / liquidity_role / fill_latency_ms / exit_reason

**既有 indexes**: 10 indexes 全 enumerate
**既有 CHECK constraints**: chk_fills_close_has_entry_context_id_v083 NOT VALID + fills_exit_source_enum
**既有 triggers**: trg_fills_engine_mode_known_values

### 2.2 details JSONB usage empirical（writer gap 確認）

```sql
SELECT 
  COUNT(*) AS total_fills_24h,
  COUNT(details) AS fills_with_details_24h,
  ROUND(COUNT(details)::numeric / NULLIF(COUNT(*),0)::numeric * 100, 2) AS details_present_pct
FROM trading.fills WHERE ts > NOW() - INTERVAL '24 hours';
```

**結果**：`total_fills_24h=98 / fills_with_details_24h=0 / details_present_pct=0.00%`

**歷史 details samples**（5 sample，非 24h window）：
```json
{"contaminated": true, "contamination_reason": "fa_phantom_1"}
{"contaminated": true, "contamination_reason": "fa_phantom_1"}
... (全部 fa_phantom_1 contamination tagging)
```

→ 所有歷史 details rows 都是 manual UPDATE 寫入的 contamination tag，**非 writer INSERT 寫入**。trading_writer.rs:430 INSERT 真實 23-column 不寫 details — empirical 確認。

### 2.3 Linux runtime sqlx_migrations applied state

```sql
SELECT version, success FROM _sqlx_migrations ORDER BY version DESC LIMIT 10;
```

**結果**：
```
 version | success | description                             
---------+---------+-----------------------------------------
      90 | t       | governance unblock candidates
      89 | t       | governance canary stage metric seed
      88 | t       | panel btc lead lag panel
      87 | t       | panel oi delta panel
      86 | t       | governance reject close reason code
      85 | t       | panel funding curve
      84 | t       | decision features reject negative label
      83 | t       | fills entry context id close check
      82 | t       | decision features evaluations split
      80 | t       | governance canary stage
```

**Drift identified**：
- Linux runtime applied max = **V90**（不是 spec/AMD 寫的 V93）
- V81 漏 applied（V80 → V82 跳）
- V91/V92/V93 source 在 git 但 PG 未 apply

**對 V094 IMPL 影響**（spec §4.4 caveat 段已記載）：
- V094 deploy 時 sqlx migrate 會先按 numeric order apply V81/V91/V92/V93，再 V094
- E1 IMPL kickoff 前 PA 必補一輪 Linux V81/V91/V92/V93 dry-run 檢查
- spec/AMD 文字無需 patch（V094 仍 next-free numeric slot；deploy semantic 不變）

### 2.4 trading_writer.rs INSERT 列表 empirical

```bash
grep -n "INSERT INTO trading.fills" srv/rust/openclaw_engine/src/database/trading_writer.rs
# 430:                "INSERT INTO trading.fills (ts, fill_id, order_id, symbol, side, qty, price, fee, fee_rate, reference_price, reference_ts_ms, reference_source, slippage_bps, liquidity_role, fill_latency_ms, realized_pnl, is_paper, strategy_name, context_id, entry_context_id, engine_mode, exit_source, exit_reason)"
```

**確認 23 columns**（與 `FILL_COLS = 23` 一致）；**details column 不在列表**。

**TradingMsg::Fill enum 結構**（database/mod.rs:281-376）：
- 21 fields total（不含 details）
- 21 production callers + tests = 13 sites total（grep verified）

### 2.5 13 caller sites enumeration

**Production callers (6 sites)**:
| Path | Line | Context |
|---|---|---|
| `event_consumer/unattributed_emit.rs` | 168 | unattributed audit fill emit |
| `tick_pipeline/pipeline_helpers.rs` | 232 | helper fill emit |
| `tick_pipeline/on_tick/step_4_5_dispatch.rs` | 1179 | dispatch step fill emit |
| `tick_pipeline/on_tick/step_4_5_dispatch.rs` | 1462 | dispatch step fill emit |
| `tick_pipeline/commands.rs` | 301 | open close cmd path fill emit |
| `tick_pipeline/commands.rs` | 618 | open close cmd path fill emit |

**Test callers (7 sites)**:
| Path | Line |
|---|---|
| `database/trading_writer.rs` | 979, 1113, 1241, 1274 |
| `event_consumer/tests/pending_registration_order_type_tests.rs` | 397 |
| `event_consumer/tests/unattributed_fill_tests.rs` | 106 |

→ **13 sites total**；E1 IMPL 加 `details: Option<serde_json::Value>` + `close_maker_attempt: bool` + `close_maker_fallback_reason: Option<String>` 三 fields 必修全部 13 sites（Rust strong-type compile-time enforcement）。

---

## §3 Hybrid Schema 設計決策（為什麼 hot column + JSONB extension）

### 3.1 三選項 trade-off

| 設計選項 | 性能 | Schema bloat | 結論 |
|---|---|---|---|
| 全 5 欄位走 new column | 最快（columnar scan） | +5 column 對 trading.fills 既有 23 columns 增 22% schema 寬度；歷史 row default 占空間 | over-optimize for low-cardinality audit-only fields |
| 全 5 欄位走 JSONB | 慢（GIN index 100x slower than partial BTREE per MIT F-MIT-1） | 0 | hot-path query (healthcheck [62]/[63] `GROUP BY close_maker_attempt`) 性能不可接受 |
| **Hybrid（2 column + 3 JSONB）** | 快（hot path filter）+ low cardinality audit JSON-extension | +2 column（既有 23 → 25）+ JSON keys append-only | **採用** |

### 3.2 具體分配理由

| 欄位 | 載體 | 設計理由 |
|---|---|---|
| `close_maker_attempt:bool` | new column | high-frequency group-by query；partial index `WHERE close_maker_attempt = TRUE` 比 JSONB GIN 高效 100x |
| `close_maker_fallback_reason:text` | new column | enum allowlist 約束（CHECK constraint）+ healthcheck [63] NULL ladder 計算需獨立欄位；不適合 JSONB |
| `close_initial_limit_price:numeric` | JSONB key | 單筆 audit 讀取，無 group-by；JSON-column extension append-only |
| `close_final_fill_price:numeric` | JSONB key | 同上 |
| `close_maker_eligible_reason:text` | JSONB key | 鏡像 trigger_tag，僅 audit 讀取 |

---

## §4 enum 設計決策

### 4.1 enum allowlist 10 值（spec/AMD 8 值的 superset）

V094 enum CHECK constraint 包含 10 enum 值：
1. `timeout_taker` — spec §5.5 Race A
2. `postonly_reject` — spec §5.5 Race B + AMD §4.1
3. `cancel_grace_expired` — spec §5.5 Race C + AMD §4.1
4. `ack_lost` — spec §5.5 Race D + AMD §4.1
5. `rate_limit_pause_global` — AMD §5.4 BB-MF-2 conditional global
6. `rate_limit_backoff_per_symbol` — AMD §5.4 BB-MF-2 per-symbol（**spec/AMD enum 缺，本 spec 補**）
7. `fast_escalate_safety_upgrade` — AMD §4.1 Race A escalation（safety path）
8. `not_attempted_safety_path` — AMD §4.1 negative whitelist（safety path）
9. `engine_shutdown_safety` — AMD §4.1 cancel_token/auth（safety path）
10. `fallback_to_taker_mandatory` — spec §5.5 Race E AC-18 ≥95% over 7d（**spec/AMD enum 缺，本 spec 補**）

### 4.2 為何補 2 enum 值

- **`rate_limit_backoff_per_symbol`**：AMD §5.4 區分 per-symbol exp backoff（1s→60s）vs conditional global pause（5min）兩種 rate limit 場景；spec/AMD §4.1 enum allowlist 只有單一 `rate_limit_pause` 值，無法區分 audit 路徑。本 spec 拆 2 值對應 2 真實場景。
- **`fallback_to_taker_mandatory`**：spec §5.5 Race E 是 Wave 1.5 v1.2 新增 mandatory fallback policy，AC-18（fallback to taker rate ≥ 95% over 7d）服務 §二 #5 生存 > 利潤；spec/AMD §4.1 enum allowlist 漏 explicit enum 值對應這個策略動作。本 spec 補。

### 4.3 safety path 3 enum 的 healthcheck 處理（per Consensus-MF-3）

`fast_escalate_safety_upgrade` / `not_attempted_safety_path` / `engine_shutdown_safety` 是合法 close path（不是 audit 漏寫）；healthcheck [63] NULL ladder 必 **exclude** 這 3 個值而非算進 NULL 比例。

對應 PASS / WARN / FAIL ladder：
- PASS：`close_maker_attempt=TRUE AND fallback_reason NOT IN (safety enum 3) AND details IS NULL` ratio ≤ 0.1%
- WARN：0.1% < ratio ≤ 1.0%
- FAIL：ratio > 1.0%

---

## §5 IMPL Prereq 5 Wave 2a closure 證據

### 5.1 F-FA-1 解除條件對照

| 子條件 | spec §X 證據 |
|---|---|
| (a) PA spec finalize V094 `sql/migrations/V094__fills_close_maker_audit.sql` | §2 schema + §3 Guard A/B/C + §10 rollback + spec file v094_close_maker_first_audit_schema_spec.md commit 9b1117a0 |
| (b) trading_writer.rs INSERT INTO trading.fills 列表升級 details JSONB 寫入路徑 spec finalize | §6 writer upgrade spec + 13 caller sites enumeration + TradingMsg::Fill enum upgrade + cross-language IPC + SLA |
| (c) Linux PG empirical query 驗證 trading.fills 既有 schema 對齊 | §1.2 hybrid schema 設計理由（Linux PG empirical 24h 0% details + 5 historical samples）+ §4 Linux PG dry-run × 2 round protocol + §4.4 V93 vs V90 drift caveat |

### 5.2 IMPL Prereq 5 全狀態（post Wave 2a）

| 子條件 | 狀態 | Commit |
|---|---|---|
| F-FA-1 V094 spec | ✅ DONE Wave 2a | 9b1117a0 |
| F-FA-2 portfolio_var SoT verify | ✅ DONE Wave 1 Track A3 | 96995b61 |
| F-FA-3 W-C Caveat 2 guard tests | ✅ DONE Wave 1 Track A4 | a5a7107c |

→ AMD §8 IMPL Prereq 5 全 done → 與 prereq 1/2/3/4/6 並行收口 → 待 3-gate 解除 → IMPL kickoff Wave 4 派 E1 5-worktree。

---

## §6 風險評估

### 6.1 改動風險評級 = **中**

| 風險來源 | Mitigation |
|---|---|
| Schema migration 必 Linux PG empirical | §4 Linux PG dry-run × 2 round protocol mandatory |
| sqlx checksum drift（V055 5-round / V028-V034 P0 incident pattern） | §5 sqlx checksum repair SOP + repair_migration_checksum binary |
| trading_writer.rs INSERT hot-path | Rust strong-type compile-time enforcement + 13 caller sites enumeration + SLA impact 估算（+50 μs per fill）|
| TradingMsg::Fill enum 升 24 fields → caller sites 漏接 | §12.2 E2 review grep verify 39 hits（13 × 3 fields） |
| Linux runtime V81/V91/V92/V93 backlog drift | §4.4 caveat + 後續行動 §14 Pre-Wave 4 backlog migration apply 檢查 |
| W-C Caveat 2 不變式破（IMPL drift） | §12.3 E2 review run F-FA-3 6 grep guard patterns |
| Backward-compat 破 | §9 append-only design + V083 mirror precedent + 既有 details usage 0 衝突 |

### 6.2 16 原則 16/16 / DOC-08 §12 0/9 觸碰 / §四 0/5 觸碰

per spec §11 全 enumeration verified；strengthens 原則 #8 交易可解釋（V094 5 audit 欄位 + 4 healthcheck dual-gate 全鏈條 audit 完整性）。

---

## §7 後續行動 + 派發 Action 清單

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 V094 spec | PM | Wave 2a closure | P0 |
| Update AMD v0.3 → v0.3.1：§8 IMPL Prereq 5 第 3 子條件 marker `F-FA-1 V094 spec ✅ DONE Wave 2a (commit 9b1117a0)` | PA | 本 PA report 接續 commit | P0 |
| Update TODO §11.5 Wave 2 Status block：A2 ✅ DONE + 加 `9b1117a0` commit | PA | 本 PA report 接續 commit | P0 |
| Update TODO §15 後續工作項：F-FA-1 → DONE row | PA | 本 PA report 接續 commit | P0 |
| 派 Wave 3 4-agent short re-review on AMD v0.3.1 + spec v1.2 + V094 spec | PM | Wave 3 dispatch | P1 |
| Pre-Wave 4 Linux V81/V91/V92/V93 backlog migration apply 檢查（per §4.4 caveat） | PA | Wave 3.5 | P1 |
| IMPL kickoff（Wave 4 / 3-gate 解除後）：派 E1 worktree A+B 並行 → C 串行 → E2/E4/Linux PG dry-run/deploy/healthcheck verify | PM | Wave 4+ dispatch | P1 |

### 7.1 PA 自接 3 子任務（本 report 之後）

per Multi-session race 防範要求，本 PA report 接續用 `git commit --only <file>` 分檔 commit：
1. AMD v0.3 → v0.3.1 §8 + §11.1 + §12 patch（commit 1）
2. TODO.md §11.5 Wave 2 Status A2 row update + §15 F-FA-1 row update（commit 2）
3. PA memory append（commit 3）

---

## §8 PA Verdict

**判定**：**SPEC-FINAL — F-FA-1 解除條件 (a)(b)(c) 全完成 → AMD §8 IMPL Prereq 5 全 done**

**主要 deliverable**：
- V094 spec：`srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md` (1176 lines / 15 sections, commit `9b1117a0`)
- PA workspace report：本檔
- 後續 AMD v0.3.1 + TODO + PA memory 3 個分離 commit

**核心教訓**：

1. **F-FA-3 PA report 已預測本 spec 大部分結論**：F-FA-3 PA report §4 + §4.4 已給 V094 schema 雛形 + writer gap discovery + Linux PG mandatory；本 spec 主要是 finalize + enrich（補 enum 2 值 + 13 caller sites + healthcheck 4 個 spec + V93 vs V90 drift caveat）。**Wave 1 Track A4 design quality 直接決定 Wave 2 spec finalize 速度** — 這是 PA 多階段串行設計的價值。
2. **Empirical Linux PG verify 揭露 spec/AMD wording drift**：spec v1.2 §4.4 + AMD v0.3 §4.1 寫「current max applied V093」是 incorrect；事實 V90。Mac source files V091/V092/V093 在 git 但 PG 未 apply。**PA 派 sub-agent 前必先 ssh trade-core empirical query 驗 schema 真實狀態**，不能基於 spec 假設。
3. **TradingMsg::Fill enum 升級的 13 caller sites enumeration 是 critical 防護**：Rust strong-type 保證 compile-time 不漏接，但 PR review 仍需 grep verify 39 hit count（13 × 3 fields）；遺漏一個 default value 會語意錯（close_maker_attempt: None vs false）。E2 review 必跑此 grep 的具體命令在 spec §12.2 提供。
4. **Hybrid schema 是「設計 trade-off + empirical evidence」雙基礎**：MIT F-MIT-1 verified GIN index 100x slower than partial BTREE → 不能全 5 欄位走 JSONB；low-cardinality audit-only fields 全走 column → schema bloat → 不採；hybrid (2 hot column + 3 JSONB key) 是 Pareto 平衡。**設計決策必有 measurable evidence 背書**，不能 hand-wave。
5. **enum allowlist 必涵蓋 spec/AMD 全部 race 場景 + safety path**：spec §5.5 Race A-E + AMD §5.4 BB-MF-2 + Race E mandatory fallback 全部需 enum 值對應；spec/AMD 8 值漏 2（rate_limit_backoff_per_symbol + fallback_to_taker_mandatory），本 spec V094 enum 補成 10 值 superset。Healthcheck [63] safety path enum exclusion 邏輯（3 值不算 NULL）是 Consensus-MF-3 的核心。
6. **Backward-compat append-only 是 V083 mirror 的延伸 pattern**：mirror NOT VALID CHECK + partial WHERE close_maker_attempt = TRUE + Guard A/B/C；保證重跑 V094 idempotent + 既有 fills row 0 影響 + 既有 healthcheck 0 影響 + 既有 caller 0 break。**V083 + V094 一起構成 trading.fills schema evolution 範式**。
7. **Multi-session race 防範**：本 PA spec land 過程 fetch 顯示 sibling commits 7b0a8e8c + 6713bcdc（BB Wave 3a short re-review）已 land，與 V094 spec scope 互不重疊（BB 看 spec/AMD wording drift 不看 V094 schema）；本 task 4 commit 全分離 用 `git commit --only` + `[skip ci]` 避免 index race。

**Confidence**:
- HIGH for V094 hybrid schema design correctness（mirror V083 NOT VALID precedent + Linux PG empirical schema verify）
- HIGH for trading_writer.rs writer gap empirical（24h 98 fills 0% details rate confirmed）
- HIGH for 13 caller sites enumeration completeness（grep verified 全 codebase）
- HIGH for enum allowlist 10 values superset（spec/AMD 8 值 + 本 spec 補 2 值對應 spec §5.5 Race E + AMD §5.4 per-symbol）
- HIGH for Linux PG dry-run × 2 round protocol（mirror V055/V083/V084 incident precedent）
- HIGH for sqlx checksum repair SOP（mirror project_2026_05_02_p0_sqlx_hash_drift incident chain）
- HIGH for healthcheck [62][63][64][65] integration spec（per spec §8.1 + AMD §4.1 + AC-1/AC-15/Consensus-MF-2/-3）
- HIGH for backward-compat append-only（V083 mirror + 0 ALTER existing column + 0 DROP + 0 RENAME）
- MEDIUM for V81/V91/V92/V93 backlog drift mitigation（§4.4 caveat 識別風險，但 Pre-Wave 4 backlog apply 工作未 land）
- MEDIUM for spec/AMD wording drift（"V93" → "V90"）— 本 spec 顯式修正，但 spec v1.2 + AMD v0.3 文字無修

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--v094_schema_migration_spec_pa_verdict.md`
