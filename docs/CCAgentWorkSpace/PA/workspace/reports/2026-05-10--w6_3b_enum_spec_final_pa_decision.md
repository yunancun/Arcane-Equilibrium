# PA — W6-3b enum spec final + 5 ambiguous mapping (A1-A5) 拍板
**日期**：2026-05-10
**性質**：D+1 W6-3b PA 拍板報告；read-only design；不寫 V086 SQL；不修 dispatch v3.3
**前置**：
- MIT W6-3a audit `2026-05-10--w6_3a_close_tag_distribution_audit.md` (HEAD `da6c1f80`)
- PA dispatch draft v3.3 `2026-05-10--sprint_n1_dispatch_draft.md` §3.0 W6-3b (preliminary 8+10 enum)
- PG live measure 2026-05-10 14:53 UTC: 9757 labeled rows, 12 enum/14 enum 完成 audit
- Code evidence: `rust/openclaw_engine/src/tick_pipeline/on_tick/helpers.rs:38` `build_risk_close_tag()` (RUST-DOUBLE-PREFIX-1, 2026-04-23 land)

---

## §1 5 Ambiguous mapping (A1-A5) PA 拍板

### A1. `strategy_close_legacy_bare_name` (615 row) 是否拆 5 sub-enum?
**MIT 推薦**：不拆，1 enum 收所有；trainer 看 `strategy_name` column 區分。
**PA 拍板**：**ACCEPT MIT — 不拆，1 enum**。
**理由**：(1) 5 策略區分已由 `decision_features.strategy` column SoT 承擔，再拆 sub-enum 是 schema duplication；(2) W6-3 scope 是 "reason taxonomy" 不是 "策略身份標籤"；(3) trainer 端 multi-task 的 per-strategy close-mode signal 可在 N+2 multi-task pipeline 改用 `(strategy, close_reason_code)` tuple 直接 group-by，**不需 enum 預埋**；(4) enum slot 一旦開出來不可逆（NOT VALID CHECK 鎖死），保留審慎。

### A2. `risk_close:risk_close:phys_lock_gate4_giveback` (16 row 雙前綴)
**MIT 推薦**：backfill 全標 `risk_close_phys_lock_gate4_giveback` 同 enum；同時開 P1 ticket 修 producer。
**PA 拍板**：**ACCEPT MIT — backfill SQL 內加 normalize；P1 producer ticket 不需要開（已 fix）**。
**理由（PA 額外驗證）**：
- code grep 確認 `helpers.rs:38` `build_risk_close_tag()` 是 idempotent helper，**RUST-DOUBLE-PREFIX-1 已於 2026-04-23 land**
- `step_6_risk_checks.rs:275` 已 migrate `super::build_risk_close_tag(&reason)`
- 唯一 emitter `risk_checks.rs:400` 用 `format!("risk_close:{}", reason)` 但傳入的 reason 是裸字串（`"phys_lock_gate4_giveback"`）→ 只生成單前綴
- 16 row 雙前綴是 **2026-04-23 fix 之前的歷史污染**，**非 active bug**
- V086 backfill SQL 必含 normalize step（`LIKE 'risk_close:risk_close:phys_lock_gate4_giveback%' THEN 'risk_close_phys_lock_gate4_giveback'`）以收歷史 16 row；無需開 P1 producer ticket。

### A3. `cost_gate_atr_unavailable` 0 row post-V082 — 保留 enum 還是合 `cost_gate_other`?
**MIT 推薦**：保留；ATR unavailable 是 SEC-11 fail-closed signal，與 `cost_gate_other` 不同 trader semantic。
**PA 拍板**：**ACCEPT MIT — 保留，empty-but-reserved**。
**理由**：(1) ATR unavailable 屬 infrastructure failure（指標管線 broken），不應與 legacy `cost_gate` 混；(2) ML trainer 未來看 `cost_gate_atr_unavailable` spike 可立即 alert 是 indicator engine 故障，不是 edge gate negative；(3) enum slot 的「reserved-but-empty」pattern 與 `direction_conflict` (post-V082 0 row 但歷史 2.77M) 同邏輯，方法論一致。

### A4. funding_arb 29 unique sub-reason 全合 1 enum?
**MIT 推薦**：合，ADR-0018 退役後 future 0 增量。
**PA 拍板**：**ACCEPT MIT — 合 1 enum (`strategy_close_funding_arb`)**。
**理由**：(1) ADR-0018 funding_arb 已退役（AMD-2026-05-09-02），future incremental 為 0；(2) 29 unique sub-reason 是 string-formatted floating-point (`rate=-0.001147` etc.)，對 ML feature 無 cardinality value；(3) 歷史保留 strategy_name 即可區分。

### A5. `strategy_close_regime_shift` 1 row enum 是否值得?
**MIT 推薦**：保留；future R-3 hypothesis pipeline + regime detection 落地後可能爆量。
**PA 拍板**：**ACCEPT MIT — 保留 (pilot enum)**。
**理由**：(1) W-AUDIT-8a Phase R-3 (Hypothesis Pipeline) + R-2 (Strategist scope reframe) 落地後 regime-aware close 是 first-class signal；(2) 現 1 row 是 producer pilot signal，刪掉等於 W-AUDIT-8e/f/g 落地時要重新 V08X migration；(3) enum slot 成本極低（CHECK constraint 12+1 vs 13+1 無實質差別）。

---

## §2 reject_reason_code Final Spec (12 enum, 11 + 1 catch-all)

| # | reject_reason_code | producer source pattern | 全期 count | post-V082 |
|---|---|---|---|---|
| 1 | `cost_gate_js_demo_negative_edge` | `^cost_gate\(JS-demo\) estimated=` | ~6.19M | 5239 |
| 2 | `cost_gate_atr_unavailable` | `ATR unavailable` (within cost_gate*) | ~13 | 0 |
| 3 | `cost_gate_other` | `^cost_gate ` (legacy non-JS, exclude JS-demo, exclude ATR unavailable) | 987k | 15 |
| 4 | `duplicate_position` | `^duplicate_position` | 1.94M | 2333 |
| 5 | `direction_conflict` | `^direction_conflict` | 2.77M | 0 |
| 6 | `position_count_limit` | `^position_count` | 732k | 0 |
| 7 | `scanner_market_gate` | `^scanner_market_gate` | 401k | 0 |
| 8 | `scanner_opportunity_canary` | `^scanner_opportunity_canary` | 138k | 0 |
| 9 | `drawdown_breach` | `^drawdown_breach` | 91k | 0 |
| 10 | `symbol_blocklist` | regex `blocked by per_strategy\.\w+\.blocked_symbols` | 35.5k | 0 |
| 11 | `risk_gate_other` | `^risk_gate` | 7998 | 0 |
| 12 | `reject_other` | residual catch-all (renamed from `other_reject`) | <100 | 0 |

**命名規範對齊**：catch-all rename `other_reject` → **`reject_other`** 對齊「prefix 一致性」（與 `close_other` 對稱）。
**Producer mapping rule**：
- evaluation order: 嚴格 top-down（cost_gate ATR unavailable 必 case 先於 cost_gate_other / cost_gate_js_demo）；catch-all 收殘餘
- source SoT: `trading.risk_verdicts.reason` (W-AUDIT-1 確認)；**禁** parse `trading.risk_verdicts.checks_failed[]`（全空）

---

## §3 close_reason_code Final Spec (14 enum, 13 + 1 catch-all)

| # | close_reason_code | producer source pattern (label_close_tag) | 全期 count |
|---|---|---|---|
| 1 | `strategy_close_grid` | `^strategy_close:grid_close` | 689 |
| 2 | `strategy_close_ma` | `^strategy_close:ma_` | 315 |
| 3 | `strategy_close_bb` | `^strategy_close:bb_` | 4 |
| 4 | `strategy_close_funding_arb` | `^strategy_close:funding_arb_exit` | 29 |
| 5 | `strategy_close_regime_shift` | exact `strategy_close:regime_shift` | 1 |
| 6 | `strategy_close_legacy_bare_name` | exact match: `grid_trading` / `ma_crossover` / `bb_breakout` / `bb_reversion` / `funding_arb` (W-AUDIT-4b M2 早期 bare strategy name 約定) | 615 |
| 7 | `risk_close_phys_lock_gate4_giveback` | `^(risk_close:)?risk_close:phys_lock_gate4_giveback` (含雙前綴 normalize) | 511 |
| 8 | `risk_close_phys_lock_gate4_stale` | `^risk_close:phys_lock_gate4_stale` | 20 |
| 9 | `risk_close_cost_edge` | `^risk_close:COST EDGE` | 14 |
| 10 | `risk_close_fast_track` | `^risk_close:fast_track` | 14 |
| 11 | `risk_close_trailing_stop` | `^risk_close:TRAILING STOP` | 10 |
| 12 | `risk_close_dynamic_stop` | `^risk_close:DYNAMIC STOP` | 6 |
| 13 | `ipc_close_all` | exact `ipc_close_all` | 1 |
| 14 | `close_other` | residual catch-all (renamed from `other_close`) | <100 |

**Producer mapping rule**：
- evaluation order: bare-name exact match 必先於 prefix regex；雙前綴 normalize case 先於單前綴
- catch-all `close_other` 必 ELSE 兜底；任何新 close_tag pattern → 先進 catch-all → producer dual-write enable 前 schema migration ALTER 加新 enum

---

## §4 V086 Schema Migration Final Spec

### 4.1 Column DDL
```sql
ALTER TABLE learning.decision_features
    ADD COLUMN IF NOT EXISTS reject_reason_code TEXT,
    ADD COLUMN IF NOT EXISTS close_reason_code TEXT;
```
**兩 column 不是 jsonb**（per MIT Q3）；query-friendly indexed 直接走 text PK comparison；ML pipeline 直接 `WHERE reject_reason_code = 'cost_gate_js_demo_negative_edge'`，不需 jsonb operator。

### 4.2 Guard A/B/C 強制（per memory `feedback_v_migration_pg_dry_run`）
- **Guard A**：column existence check on `learning.decision_features.label_close_tag`（前置 SoT 必存在；缺 → RAISE silent-noop）
- **Guard B**：type check on `reject_reason_code` / `close_reason_code` (允許 not-yet-exist 或 text；非 text → RAISE drift)
- **Guard C**：`pg_get_indexdef()` 比對 `idx_decision_features_reason_codes` (column order `(reject_reason_code, close_reason_code)` partial index `WHERE reject_reason_code IS NOT NULL OR close_reason_code IS NOT NULL`)

### 4.3 NOT VALID CHECK constraint
```sql
ALTER TABLE learning.decision_features
    ADD CONSTRAINT chk_reject_reason_code_enum CHECK (
        reject_reason_code IS NULL OR reject_reason_code IN (
            'cost_gate_js_demo_negative_edge', 'cost_gate_atr_unavailable', 'cost_gate_other',
            'duplicate_position', 'direction_conflict', 'position_count_limit',
            'scanner_market_gate', 'scanner_opportunity_canary', 'drawdown_breach',
            'symbol_blocklist', 'risk_gate_other', 'reject_other'
        )
    ) NOT VALID,
    ADD CONSTRAINT chk_close_reason_code_enum CHECK (
        close_reason_code IS NULL OR close_reason_code IN (
            'strategy_close_grid', 'strategy_close_ma', 'strategy_close_bb',
            'strategy_close_funding_arb', 'strategy_close_regime_shift', 'strategy_close_legacy_bare_name',
            'risk_close_phys_lock_gate4_giveback', 'risk_close_phys_lock_gate4_stale',
            'risk_close_cost_edge', 'risk_close_fast_track',
            'risk_close_trailing_stop', 'risk_close_dynamic_stop',
            'ipc_close_all', 'close_other'
        )
    ) NOT VALID;
```
**NOT VALID 強制**：對齊 V083 既有 pattern；new rows 即時驗，legacy 9.5M unlabeled rows 不掃描。

### 4.4 Backfill SQL (one-shot, 9757 row, ~30-90 sec)
```sql
UPDATE learning.decision_features df
SET reject_reason_code = CASE
    WHEN df.label_close_tag != 'rejected_governance' THEN NULL
    -- evaluation order critical: ATR unavailable 必先於 JS-demo / cost_gate_other
    WHEN rv.reason ~ 'cost_gate.*ATR unavailable' THEN 'cost_gate_atr_unavailable'
    WHEN rv.reason LIKE 'cost_gate(JS-demo)%' THEN 'cost_gate_js_demo_negative_edge'
    WHEN rv.reason LIKE 'cost_gate%' THEN 'cost_gate_other'
    WHEN rv.reason LIKE 'duplicate_position%' THEN 'duplicate_position'
    WHEN rv.reason LIKE 'direction_conflict%' THEN 'direction_conflict'
    WHEN rv.reason LIKE 'position_count%' THEN 'position_count_limit'
    WHEN rv.reason LIKE 'scanner_market_gate%' THEN 'scanner_market_gate'
    WHEN rv.reason LIKE 'scanner_opportunity_canary%' THEN 'scanner_opportunity_canary'
    WHEN rv.reason LIKE 'drawdown_breach%' THEN 'drawdown_breach'
    WHEN rv.reason ~ 'blocked by per_strategy\.\w+\.blocked_symbols' THEN 'symbol_blocklist'
    WHEN rv.reason LIKE 'risk_gate%' THEN 'risk_gate_other'
    ELSE 'reject_other'
END,
close_reason_code = CASE
    WHEN df.label_close_tag = 'rejected_governance' THEN NULL
    -- bare strategy name (W-AUDIT-4b M2 約定) 必先於 prefix regex
    WHEN df.label_close_tag IN ('grid_trading','ma_crossover','bb_breakout','bb_reversion','funding_arb')
        THEN 'strategy_close_legacy_bare_name'
    WHEN df.label_close_tag LIKE 'strategy_close:grid_close%' THEN 'strategy_close_grid'
    WHEN df.label_close_tag LIKE 'strategy_close:ma_%' THEN 'strategy_close_ma'
    WHEN df.label_close_tag LIKE 'strategy_close:bb_%' THEN 'strategy_close_bb'
    WHEN df.label_close_tag LIKE 'strategy_close:funding_arb_exit%' THEN 'strategy_close_funding_arb'
    WHEN df.label_close_tag = 'strategy_close:regime_shift' THEN 'strategy_close_regime_shift'
    -- 雙前綴 normalize (16 row 歷史污染, RUST-DOUBLE-PREFIX-1 已 2026-04-23 fix)
    WHEN df.label_close_tag LIKE 'risk_close:risk_close:phys_lock_gate4_giveback%'
        THEN 'risk_close_phys_lock_gate4_giveback'
    WHEN df.label_close_tag LIKE 'risk_close:phys_lock_gate4_giveback%' THEN 'risk_close_phys_lock_gate4_giveback'
    WHEN df.label_close_tag LIKE 'risk_close:phys_lock_gate4_stale%' THEN 'risk_close_phys_lock_gate4_stale'
    WHEN df.label_close_tag LIKE 'risk_close:COST EDGE%' THEN 'risk_close_cost_edge'
    WHEN df.label_close_tag LIKE 'risk_close:fast_track%' THEN 'risk_close_fast_track'
    WHEN df.label_close_tag LIKE 'risk_close:TRAILING STOP%' THEN 'risk_close_trailing_stop'
    WHEN df.label_close_tag LIKE 'risk_close:DYNAMIC STOP%' THEN 'risk_close_dynamic_stop'
    WHEN df.label_close_tag = 'ipc_close_all' THEN 'ipc_close_all'
    ELSE 'close_other'
END
FROM trading.risk_verdicts rv
WHERE df.context_id = rv.context_id
  AND df.label_close_tag IS NOT NULL;
```
**One-shot, no cron**：在 V086 schema migration 內直接 backfill；producer dual-write 從 V086 land 之刻 enable，0 NULL drift on new rows.

### 4.5 ALTER VALIDATE CONSTRAINT timing
- **D+1 evening (W6-3c E1 IMPL DONE)**：V086 land + producer dual-write enable
- **D+2 14:00 UTC**：24h dual-write drift healthcheck PASS（期望 0 NULL on new rows post-V086）
- **D+2 14:30 UTC**：`ALTER TABLE learning.decision_features VALIDATE CONSTRAINT chk_reject_reason_code_enum` + `chk_close_reason_code_enum`，lock window <30 sec on 9757+ rows

### 4.6 Producer dual-write spec (Rust IPC)
- **reject path**：`intent_processor` 寫 risk_verdicts.reason 同時寫 `decision_features.reject_reason_code`（producer 直接出 enum，不依賴 post-hoc parse）
- **close path**：`step_6_risk_checks.rs` / `helpers_close_tags.rs` close emit 路徑寫 `decision_features.close_reason_code`（producer 直接出 enum）
- W6-3c IMPL 必加 `helper_scripts/db/passive_wait_healthcheck/checks_reason_code_dual_write_drift.py` ([59] slot per dispatch v3.3)

---

## §5 W6-3 dispatch v3.3 Update 建議

### 5.1 Sub-task scope refinement
| dispatch v3.3 preliminary | PA W6-3b final | 變化 |
|---|---|---|
| W6-3b reject **8 enum** + close **10+ enum** | reject **12 enum** (11+catch-all) + close **14 enum** (13+catch-all) | +4 reject / +4 close (per MIT W6-3a evidence) |
| W6-3c V086 column add (1 day) | unchanged 1 day, spec 已 final（§4） | scope 收緊，less ambiguity |
| W6-3d trainer schema read update (1 day) | unchanged | 對 reject + close 兩 column 升 read schema；regression scorer 仍 ignore；future multi-task 接口 ready |
| backfill 機制 "cron" | one-shot 30-90 sec UPDATE in V086 | 不開 cron，**dispatch v3.3 §3.0 修文** |

### 5.2 額外 dispatch 修建議
- **W6-3a 已 DONE**（MIT report `2026-05-10--w6_3a_close_tag_distribution_audit.md`）→ dispatch §3.0 markdown checkbox flip
- **W6-3b 已 DONE**（本 PA report）→ dispatch §3.0 markdown checkbox flip
- **W6-3c E1 IMPL** 可立即 dispatch（spec final，無 ambiguity）
- **W6-3d** 改為 W6-3c sibling 並行（trainer read schema 不依賴 V086 deploy timing，只依賴 schema spec）

### 5.3 P1 follow-up (不阻 W6)
- **無 producer fix ticket**（A2 拍板：雙前綴是歷史污染，post-2026-04-23 fix 之 active code 已正確）
- 615 bare-name 走 `strategy_close_legacy_bare_name` enum，**不開** producer ticket（W-AUDIT-4b M2 約定，非 bug）

---

## §6 高風險警告（W6-3c E1 IMPL + E2 必查 3 點）

1. **Backfill SQL evaluation order**：CASE WHEN 順序錯誤會誤分類（ATR unavailable 必先於 JS-demo / cost_gate_other；雙前綴必先於單前綴；bare-name exact 必先於 prefix regex）。E2 必走 PG dry-run 9757 row distribution 比對 audit table。
2. **Guard A/B/C 完整性**：V086 必含 3 Guard，缺一 = E2 拒簽（per memory `feedback_v_migration_pg_dry_run`）。
3. **Producer dual-write race**：V086 land 與 producer dual-write code deploy 不能差 >5 min；否則 V086 → dual-write deploy 期間的 new rows reject_reason_code = NULL，過 24h healthcheck 後 ALTER VALIDATE 會失敗。E2 必驗 deployment runbook 含 atomic deploy step。

---

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_3b_enum_spec_final_pa_decision.md
