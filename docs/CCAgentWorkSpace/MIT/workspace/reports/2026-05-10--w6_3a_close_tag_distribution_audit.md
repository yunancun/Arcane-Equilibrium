# MIT W6-3a — close_tag distribution audit + reject_reason / close_reason enum spec
**日期**：2026-05-10
**性質**：D+1 W6-3b PA enum spec 入場前 baseline；read-only PG audit；不寫 V086 SQL；不修 dispatch v3.3
**前置依據**：
- MIT W6 RFC 自答 `2026-05-10--w6_rfc_mit_questions_self_answer.md` Q3（揭露 close_tag >100 unique values）
- MIT governance reject baseline `2026-05-10--governance_reject_baseline_w6_rfc.md`（risk_verdicts SoT 確認）
- PA dispatch v3.3 §3.0 W6-3b preliminary enum (8 reject + 10+ close)

**Source PG live measure** (2026-05-10 14:53 UTC, ssh trade-core):
- `learning.decision_features` labeled=9757 (rejected=7528 / closed=2229)；unlabeled=9.51M（pre-W-AUDIT-4b M3 era）
- `trading.risk_verdicts` 全期 18.5M row；post-V082 (2026-05-10 09:00+) Approved=48 / Rejected=7587

---

## §1 Schema discovery — close_tag 真實 distribution

### 1.1 完整 unique values（68 unique row → 15 category）

| Category | Count | % of labeled |
|---|---|---|
| `rejected_governance` | 7528 | 77.2% |
| `strategy_close_grid` (`strategy_close:grid_close_short/long`) | 689 | 7.1% |
| `fill_strategy_label`（5 bare strategy name）| 615 | 6.3% |
| `risk_close_phys_lock_gate4_giveback`（含 16 row 雙前綴 bug）| 511 | 5.2% |
| `strategy_close_ma` (`strategy_close:ma_reverse_cross`) | 315 | 3.2% |
| `strategy_close_funding_arb` (29 row, 含 sub-reason 字串拍平) | 29 | 0.3% |
| `risk_close_phys_lock_gate4_stale` (`stale_roc_neg`) | 20 | 0.2% |
| `risk_close_cost_edge` (`COST EDGE: ratio X.XX...`) | 14 | 0.14% |
| `risk_close_fast_track` (`fast_track_reduce_half/fast_track`) | 14 | 0.14% |
| `risk_close_trailing_stop` (`TRAILING STOP: peak X.XX...`) | 10 | 0.10% |
| `risk_close_dynamic_stop` (`DYNAMIC STOP: pnl X.XX...`) | 6 | 0.06% |
| `strategy_close_bb` (`bb_mean_revert`) | 4 | 0.04% |
| `ipc_close_all` | 1 | 0.01% |
| `strategy_close_regime_shift` | 1 | 0.01% |

### 1.2 producer bug 揭露
- **16 row** `label_close_tag = 'risk_close:risk_close:phys_lock_gate4_giveback'`（risk_close: 雙前綴）
  → Rust producer chain 對 source-string concat 時 prepend `risk_close:` 沒判斷既有 prefix；這 16 row backfill 必標 `risk_close_phys_lock_gate4_giveback` 同類，並開新 P1 ticket 修 producer
- **615 fill 用 bare strategy name** (`grid_trading`/`ma_crossover`/`bb_breakout`/`bb_reversion`/`funding_arb`)
  → producer 對 successful close-on-strategy-signal 直接寫 strategy_name 而非 `strategy_close:<strategy>_close_*`；這是 W-AUDIT-4b M2 chain 早期約定，**不是 bug**；backfill 時依 close 路徑映射到對應 `strategy_close_*` enum

### 1.3 funding_arb sub-reason 字串爆炸
- 29 unique `strategy_close:funding_arb_exit: rate=X.XXXXXX basis=X.XXX%` (各 1 row)
- ADR-0018 已退役；歷史資料但 backfill 全收 `strategy_close_funding_arb` 單一 enum

---

## §2 risk_verdicts.reason distribution（reject reason SoT）

### 2.1 全期 18.5M row reason_head 分布

| reason_head | count | % | 對應 reject_code |
|---|---|---|---|
| `cost_gate(JS-demo)` | 6.19M | 33.4% | `cost_gate_js_demo_negative_edge` (+ atr_unavailable sub-class) |
| (Approved 空 reason) | 5.24M | 28.3% | N/A (verdict='Approved') |
| `direction_conflict` | 2.77M | 14.9% | `direction_conflict` |
| `duplicate_position` | 1.94M | 10.5% | `duplicate_position` |
| `cost_gate` (legacy non-JS) | 987k | 5.3% | `cost_gate_other` |
| `position_count` | 732k | 3.9% | `position_count_limit` |
| `scanner_market_gate` | 401k | 2.2% | `scanner_market_gate` |
| `scanner_opportunity_canary` | 138k | 0.7% | `scanner_opportunity_canary` |
| `drawdown_breach` | 91k | 0.5% | `drawdown_breach` |
| `<SYMBOL> blocked by per_strategy.<strategy>.blocked_symbols` | 35.5k | 0.2% | `symbol_blocklist` |
| `risk_gate` | 7998 | 0.04% | `risk_gate_other` |

### 2.2 post-V082 (3.5h) reject 集中度
僅 3 reject_code: `cost_gate_js_demo_negative_edge` (5239) / `duplicate_position` (2333) / `cost_gate_other` (15)
→ **W6-3b enum 8 類覆蓋當前 producer chain 充足**；剩下 5 類（direction_conflict / position_count / scanner_market_gate / scanner_opportunity_canary / drawdown_breach / symbol_blocklist / risk_gate）走歷史 risk_verdicts → 仍需 enum 容納

### 2.3 `checks_failed` array 全空 (0 rows)
producer 從未 populate；reason 字串是唯一 SoT；`details jsonb` 也未驗（V086 不必依賴）

---

## §3 reject_reason_code refined enum spec（10 enum，extend from PA preliminary 8）

| reject_reason_code | source pattern | 全期 count | post-V082 count | mapping deterministic? |
|---|---|---|---|---|
| `cost_gate_js_demo_negative_edge` | `cost_gate(JS-demo) estimated=...` | ~6.19M | 5239 | ✅ regex `^cost_gate\(JS-demo\) estimated=` |
| `cost_gate_atr_unavailable` | `cost_gate(JS-demo) ATR unavailable...` / `cost_gate ATR unavailable...` | ~13 (歷史) | 0 | ✅ regex `ATR unavailable` |
| `cost_gate_other` | `cost_gate ` (legacy non-JS) | 987k | 15 | ✅ `^cost_gate ` and not JS-demo |
| `duplicate_position` | `duplicate_position <SYMBOL> already <SIDE>...` | 1.94M | 2333 | ✅ regex `^duplicate_position` |
| `direction_conflict` | `direction_conflict` | 2.77M | 0 | ✅ regex `^direction_conflict` |
| `position_count_limit` | `position_count` | 732k | 0 | ✅ regex `^position_count` |
| `scanner_market_gate` | `scanner_market_gate ...` | 401k | 0 | ✅ regex `^scanner_market_gate` |
| `scanner_opportunity_canary` | `scanner_opportunity_canary ...` | 138k | 0 | ✅ regex `^scanner_opportunity_canary` |
| `drawdown_breach` | `drawdown_breach ...` | 91k | 0 | ✅ regex `^drawdown_breach` |
| `symbol_blocklist` | `<SYMBOL> blocked by per_strategy.<strategy>.blocked_symbols` | 35.5k | 0 | ✅ regex `blocked by per_strategy\.\w+\.blocked_symbols` |
| `risk_gate_other` | `risk_gate ...` | 7998 | 0 | ✅ regex `^risk_gate` |
| `other_reject` | catch-all | <100 | 0 | ⚠️ residual after 11 rules |

**改動 vs PA preliminary 8**：
- ❌ remove: `volatility` / `dsr` / `position_size` / `margin_util` / `scanner_advisory`（歷史 0 row 未觸發；不浪費 enum slot；future runtime add 走 `other_reject` + 升 enum migration）
- ➕ add: `cost_gate_js_demo_negative_edge` 拆 `cost_gate_other` / `cost_gate_atr_unavailable`（最大宗 reject，必須拆）/ `direction_conflict` / `scanner_market_gate` / `scanner_opportunity_canary` / `drawdown_breach` / `symbol_blocklist` / `risk_gate_other` / `other_reject`
- ✅ keep: `duplicate_position` / `position_count_limit` (rename `position_size`)

**11 enum + 1 catch-all = 12 enum total（vs PA 8）**

---

## §4 close_reason_code refined enum spec（13 enum，extend from PA preliminary 10+）

| close_reason_code | source pattern (label_close_tag) | count | mapping deterministic? |
|---|---|---|---|
| `strategy_close_grid` | `strategy_close:grid_close_short/long` | 689 | ✅ regex `^strategy_close:grid_close` |
| `strategy_close_ma` | `strategy_close:ma_reverse_cross` | 315 | ✅ regex `^strategy_close:ma_` |
| `strategy_close_bb` | `strategy_close:bb_mean_revert/bb_*` | 4 | ✅ regex `^strategy_close:bb_` |
| `strategy_close_funding_arb` | `strategy_close:funding_arb_exit: ...` | 29 | ✅ regex `^strategy_close:funding_arb_exit` |
| `strategy_close_regime_shift` | `strategy_close:regime_shift` | 1 | ✅ exact match |
| `risk_close_phys_lock_gate4_giveback` | `risk_close:phys_lock_gate4_giveback` (+ 16 雙前綴) | 511 | ✅ regex `^(risk_close:)?risk_close:phys_lock_gate4_giveback` |
| `risk_close_phys_lock_gate4_stale` | `risk_close:phys_lock_gate4_stale_roc_neg` | 20 | ✅ regex `^risk_close:phys_lock_gate4_stale` |
| `risk_close_cost_edge` | `risk_close:COST EDGE: ratio X.XX, pnl Y.YY% ...` | 14 | ✅ regex `^risk_close:COST EDGE` |
| `risk_close_fast_track` | `risk_close:fast_track_reduce_half/fast_track` | 14 | ✅ regex `^risk_close:fast_track` |
| `risk_close_trailing_stop` | `risk_close:TRAILING STOP: peak X.XX...` | 10 | ✅ regex `^risk_close:TRAILING STOP` |
| `risk_close_dynamic_stop` | `risk_close:DYNAMIC STOP: pnl X.XX...` | 6 | ✅ regex `^risk_close:DYNAMIC STOP` |
| `ipc_close_all` | `ipc_close_all` | 1 | ✅ exact match |
| `strategy_close_legacy_bare_name` | `grid_trading/ma_crossover/bb_breakout/bb_reversion/funding_arb` (615 W-AUDIT-4b M2 早期約定 bare strategy) | 615 | ✅ exact match against 5 known names |
| `other_close` | catch-all | <100 | ⚠️ residual |

**改動 vs PA preliminary 10+**：
- ❌ remove: `risk_close_phys_lock` 統一字段 → 拆 `gate4_giveback` / `gate4_stale`（最大宗 + 第二大宗 risk_close）；其餘 phys_lock_gate1-3 歷史 0 row 不開 enum
- ➕ add: `strategy_close_legacy_bare_name`（615 row 是 producer 早期約定不是 bug；backfill 收這 enum，trainer 視為「strategy 自然 close + 沒 sub-reason」）/ `strategy_close_regime_shift` (1 row, 但 future 可能成長因 regime detection 升級)
- ✅ keep: 其他 11 close_reason

**13 enum + 1 catch-all = 14 enum total（vs PA 10+）**

---

## §5 Ambiguous mapping（需 D+1 PA 拍板）

### A1. `strategy_close_legacy_bare_name` (615 row) 是否拆 5 sub-enum？
- **MIT 推薦**：**不拆**，1 enum 收所有；trainer 看 `strategy_name` column 即可區分 5 策略
- **PA 拍板需要**：trainer 端 multi-task learning 是否需要 「per-strategy close-mode」signal？若需要 → 拆 `strategy_close_grid_natural` / `strategy_close_ma_natural` 等 5 sub-enum

### A2. `risk_close:risk_close:phys_lock_gate4_giveback` (16 row 雙前綴)
- **MIT 推薦**：backfill 全標 `risk_close_phys_lock_gate4_giveback` 同單一 enum；同時開 P1 ticket 修 Rust producer string concat
- **PA 拍板需要**：是否在 V086 的 backfill SQL 內加 normalize step (regex `s/^risk_close:risk_close:/risk_close:/`)，避免 producer fix 落地前持續寫雙前綴

### A3. `cost_gate_atr_unavailable` 0 row post-V082 — 保留 enum 還是合 `cost_gate_other`?
- **MIT 推薦**：**保留**；ATR unavailable 是 SEC-11 fail-closed signal，與 `cost_gate_other` (legacy non-JS) 不同 trader semantic；future runtime 任何 ATR 路徑 broken 會 spike 此 enum
- **PA 拍板需要**：是否同意 enum slot reserved-but-empty pattern

### A4. funding_arb 29 unique sub-reason 全合 1 enum?
- **MIT 推薦**：**合**；ADR-0018 退役後 future 0 增量；distinguishing rate=-0.001147 vs rate=-0.001238 對 ML 無用
- **PA 拍板**：confirm

### A5. `strategy_close_regime_shift` 1 row enum 是否值得?
- **MIT 推薦**：**保留**；future R-3 hypothesis pipeline 落地 + regime detection 成熟後可能爆量；現 1 row 是 pilot signal
- **PA 拍板**：confirm

---

## §6 Backfill cron 設計

### 6.1 Scope
- 9757 labeled rows（rejected 7528 + closed 2229）
- 12 reject_reason_code + 14 close_reason_code = 26 enum total
- 全 mapping rules deterministic（regex / exact match），**0 manual review**
- 雙前綴 16 row 走 normalize step；其餘 99.84% straight regex

### 6.2 Backfill SQL 結構（D+1 W6-3c E1 寫實 SQL，本 spec 只描述）
```
UPDATE learning.decision_features
SET reject_reason_code = CASE
    WHEN label_close_tag != 'rejected_governance' THEN NULL
    -- match risk_verdicts.reason via context_id JOIN
    WHEN rv.reason LIKE 'cost_gate(JS-demo) ATR unavailable%' THEN 'cost_gate_atr_unavailable'
    WHEN rv.reason LIKE 'cost_gate(JS-demo)%' THEN 'cost_gate_js_demo_negative_edge'
    WHEN rv.reason LIKE 'cost_gate ATR unavailable%' THEN 'cost_gate_atr_unavailable'
    WHEN rv.reason LIKE 'cost_gate%' THEN 'cost_gate_other'
    WHEN rv.reason LIKE 'duplicate_position%' THEN 'duplicate_position'
    WHEN rv.reason LIKE 'direction_conflict%' THEN 'direction_conflict'
    WHEN rv.reason LIKE 'position_count%' THEN 'position_count_limit'
    WHEN rv.reason LIKE 'scanner_market_gate%' THEN 'scanner_market_gate'
    WHEN rv.reason LIKE 'scanner_opportunity_canary%' THEN 'scanner_opportunity_canary'
    WHEN rv.reason LIKE 'drawdown_breach%' THEN 'drawdown_breach'
    WHEN rv.reason ~ 'blocked by per_strategy\.\w+\.blocked_symbols' THEN 'symbol_blocklist'
    WHEN rv.reason LIKE 'risk_gate%' THEN 'risk_gate_other'
    ELSE 'other_reject'
END,
close_reason_code = CASE
    WHEN label_close_tag = 'rejected_governance' THEN NULL
    WHEN label_close_tag IN ('grid_trading','ma_crossover','bb_breakout','bb_reversion','funding_arb') THEN 'strategy_close_legacy_bare_name'
    WHEN label_close_tag LIKE 'strategy_close:grid_close%' THEN 'strategy_close_grid'
    WHEN label_close_tag LIKE 'strategy_close:ma_%' THEN 'strategy_close_ma'
    WHEN label_close_tag LIKE 'strategy_close:bb_%' THEN 'strategy_close_bb'
    WHEN label_close_tag LIKE 'strategy_close:funding_arb_exit%' THEN 'strategy_close_funding_arb'
    WHEN label_close_tag = 'strategy_close:regime_shift' THEN 'strategy_close_regime_shift'
    WHEN label_close_tag LIKE 'risk_close:risk_close:phys_lock_gate4_giveback%' THEN 'risk_close_phys_lock_gate4_giveback'  -- 雙前綴 normalize
    WHEN label_close_tag LIKE 'risk_close:phys_lock_gate4_giveback%' THEN 'risk_close_phys_lock_gate4_giveback'
    WHEN label_close_tag LIKE 'risk_close:phys_lock_gate4_stale%' THEN 'risk_close_phys_lock_gate4_stale'
    WHEN label_close_tag LIKE 'risk_close:COST EDGE%' THEN 'risk_close_cost_edge'
    WHEN label_close_tag LIKE 'risk_close:fast_track%' THEN 'risk_close_fast_track'
    WHEN label_close_tag LIKE 'risk_close:TRAILING STOP%' THEN 'risk_close_trailing_stop'
    WHEN label_close_tag LIKE 'risk_close:DYNAMIC STOP%' THEN 'risk_close_dynamic_stop'
    WHEN label_close_tag = 'ipc_close_all' THEN 'ipc_close_all'
    ELSE 'other_close'
END
FROM trading.risk_verdicts rv
WHERE learning.decision_features.context_id = rv.context_id
  AND learning.decision_features.label_close_tag IS NOT NULL;
```

### 6.3 Cron timing 估算
- 9757 row UPDATE + JOIN 18.5M row risk_verdicts (indexed on context_id) → 估 ~30-90 sec single-pass
- **不需 cron**：D+1 W6-3c IMPL 後 V086 schema migration 內直接 backfill (one-shot)；不開 cron 持續 backfill
- producer dual-write 從 V086 land 之刻 enable，0 NULL drift on new rows
- V086 NOT VALID CHECK + 24h dual-write drift healthcheck PASS → ALTER VALIDATE CONSTRAINT (D+2 14:00 UTC 估算 lock <30sec for 9757+ row ALTER)

---

## §7 V086 schema migration spec preview

### 7.1 Schema 動作（D+1 W6-3c E1 寫實 SQL，本 preview 描述）

```
-- Guard A: table exists & schema matches expected baseline
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_schema='learning' AND table_name='decision_features' 
                   AND column_name='label_close_tag') THEN
        RAISE EXCEPTION 'V086 silent-noop: learning.decision_features missing label_close_tag column';
    END IF;
END $$;

-- Guard B: new columns not yet exist
DO $$
DECLARE
    col_type text;
BEGIN
    SELECT data_type INTO col_type
    FROM information_schema.columns
    WHERE table_schema='learning' AND table_name='decision_features' AND column_name='reject_reason_code';
    IF col_type IS NOT NULL AND col_type != 'text' THEN
        RAISE EXCEPTION 'V086 type drift: reject_reason_code is % (expected text)', col_type;
    END IF;
END $$;

-- Add columns (additive, NULL allowed pre-backfill)
ALTER TABLE learning.decision_features 
    ADD COLUMN IF NOT EXISTS reject_reason_code TEXT,
    ADD COLUMN IF NOT EXISTS close_reason_code TEXT;

-- Backfill (one-shot, 9757 row, ~30-90 sec)
UPDATE learning.decision_features ... (見 §6.2)

-- NOT VALID CHECK constraint (forward-only, allow legacy 9.5M unlabeled rows untouched)
ALTER TABLE learning.decision_features 
    ADD CONSTRAINT chk_reject_reason_code_enum CHECK (
        reject_reason_code IS NULL OR reject_reason_code IN (
            'cost_gate_js_demo_negative_edge', 'cost_gate_atr_unavailable', 'cost_gate_other',
            'duplicate_position', 'direction_conflict', 'position_count_limit',
            'scanner_market_gate', 'scanner_opportunity_canary', 'drawdown_breach',
            'symbol_blocklist', 'risk_gate_other', 'other_reject'
        )
    ) NOT VALID,
    ADD CONSTRAINT chk_close_reason_code_enum CHECK (
        close_reason_code IS NULL OR close_reason_code IN (
            'strategy_close_grid', 'strategy_close_ma', 'strategy_close_bb',
            'strategy_close_funding_arb', 'strategy_close_regime_shift', 'strategy_close_legacy_bare_name',
            'risk_close_phys_lock_gate4_giveback', 'risk_close_phys_lock_gate4_stale',
            'risk_close_cost_edge', 'risk_close_fast_track',
            'risk_close_trailing_stop', 'risk_close_dynamic_stop',
            'ipc_close_all', 'other_close'
        )
    ) NOT VALID;

-- Guard C: hot-path index for ML training query
DO $$
DECLARE
    idx_def text;
BEGIN
    SELECT pg_get_indexdef(c.oid) INTO idx_def
    FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='learning' AND c.relname='idx_decision_features_reason_codes';
    IF idx_def IS NOT NULL AND idx_def NOT LIKE '%(reject_reason_code, close_reason_code)%' THEN
        RAISE EXCEPTION 'V086 index drift: idx_decision_features_reason_codes wrong column order';
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_decision_features_reason_codes 
    ON learning.decision_features (reject_reason_code, close_reason_code) 
    WHERE reject_reason_code IS NOT NULL OR close_reason_code IS NOT NULL;
```

### 7.2 ALTER VALIDATE CONSTRAINT timing
- D+1 V086 land + producer dual-write enable
- D+2 14:00 UTC: 24h dual-write drift healthcheck PASS (期望 0 NULL on new rows)
- D+2 14:30 UTC: `ALTER TABLE ... VALIDATE CONSTRAINT chk_*` 強制驗 forward；lock window <30 sec on 9757+ row

### 7.3 Producer dual-write
- Rust intent_processor reject path: writer 直接寫 `reject_reason_code` (不依賴 risk_verdicts.reason post-hoc parse)
- Rust close path: writer 直接寫 `close_reason_code` (不依賴 label_close_tag post-hoc parse)
- 24h 內 healthcheck `check_reject_reason_code_dual_write_drift()` 必 PASS

### 7.4 Guard A/B/C compliance
- ✅ Guard A: column existence check
- ✅ Guard B: type check on new columns
- ✅ Guard C: hot-path index pg_get_indexdef compare
- ✅ Idempotency: re-run V086 → NOTICE skip (4 Guards 都 IF EXISTS-aware)

---

## §8 結論 + 對 dispatch v3.3 §3.0 W6-3b 影響

### 8.1 W6-3b enum spec 對 dispatch preliminary 的調整
| 維度 | dispatch v3.3 preliminary | MIT W6-3a refined | 差距 |
|---|---|---|---|
| reject_reason_code 數量 | 8 | 12 (含 catch-all) | +4 (cost_gate 拆 3 + 5 歷史 reject 補進) |
| close_reason_code 數量 | 10+ | 14 (含 catch-all) | +4 (phys_lock 拆 2 + legacy bare name + 雙前綴 normalize) |
| ambiguous mapping | 未列 | 5 項待 PA 拍板 | A1-A5 |
| backfill 機制 | "cron" 隱含 ongoing | one-shot UPDATE in V086 | 不需 cron |

### 8.2 D+1 PA 收 baseline 後的工作
- W6-3b enum spec：直接收 §3 + §4 兩 table；focus on §5 5 ambiguous mapping 拍板
- W6-3c V086 SQL：依 §7 spec 落地 (PM dispatch E1)
- W6-3d trainer pipeline read：對 reject_reason_code + close_reason_code 兩 column 升 schema (regression scorer 仍 ignore；future multi-task 接口準備)

### 8.3 額外發現 (P1 follow-up)
- **producer 雙前綴 bug** (16 row `risk_close:risk_close:`)：Rust string concat 漏 prefix-aware；建議開 P1 ticket fix producer + V086 backfill normalize
- **post-V082 reject 集中度高**（3 reject_code 占 100%）：當前 producer chain 遠少於歷史 12 reason_head；future 5 dormant reason 可能 surface (direction_conflict / position_count / etc.)；enum slot 預留正確
- **funding_arb 29 sub-reason** 已退役但歷史保留；不開 enum sub-class；ML training 看 strategy_name 區分

---

MIT AUDIT DONE: srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_3a_close_tag_distribution_audit.md
