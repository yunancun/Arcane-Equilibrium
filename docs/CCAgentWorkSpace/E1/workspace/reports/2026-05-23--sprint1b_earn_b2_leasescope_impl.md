# E1 Sprint 1B Earn Wave B B2 — LeaseScope variant extension IMPL DONE

- Date: 2026-05-23
- Role: E1 Backend Developer
- Sprint: Sprint 1B Pending 3.2 Earn first stake Wave B
- Task slot: B2 LeaseScope variant extension (single-thread 2-3 hr)
- Dispatch packet SSOT: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md` §3 + §4 PA4 Wave A
- Branch: feature work tree (working dir state); 不 commit (待 E2 review → E4 regression → PM 統一 commit)

## §1 任務摘要

per dispatch packet §3.2 + §3.3 + §3.4：

1. `rust/openclaw_core/src/lease_scope.rs` 既有 4 variant LeaseScope enum 擴 2 new variant: `EarnStake` / `EarnRedeem`
2. 3 method exhaustive match 強制更新：`as_audit_str()` / `requires_operator_authority()` / `default_ttl_ms()`
3. Linux PG empirical 驗 `governance.lease_transitions` + `governance.canary_stage_log` CHECK constraint 是否限既有 4 scope 字串 → 結論：0 conflict，**不需 V108 ALTER**
4. 既有 4 variant 不破；exhaustive match 編譯期自動 catch 漏更新的 match
5. 補 2 new unit test 覆蓋新 variant（earn_scope_requires_operator_authority + earn_scope_default_ttl_60s）+ 既有 lease_scope_audit_str_roundtrip 擴 2 entry

## §2 修改清單

| 檔 | 行範圍 | 類型 | 內容 |
|---|---|---|---|
| `srv/rust/openclaw_core/src/lease_scope.rs` | enum body (line 35-77) | NEW variant | + `EarnStake` + `EarnRedeem` 兩個 variant + 中文 doc-comment（為什麼 + 對齊 + 不變量） |
| `srv/rust/openclaw_core/src/lease_scope.rs` | `as_audit_str()` (line 85-100) | match 擴展 | + `Self::EarnStake => "EARN_STAKE"` / `Self::EarnRedeem => "EARN_REDEEM"`（SCREAMING_SNAKE_CASE 對齊 W-AUDIT-9 audit pattern） |
| `srv/rust/openclaw_core/src/lease_scope.rs` | `requires_operator_authority()` (line 108-116) | match 擴展 | EarnStake / EarnRedeem 加入 operator-only set（matches! 三聯）|
| `srv/rust/openclaw_core/src/lease_scope.rs` | `default_ttl_ms()` (line 123-131) | match 擴展 | EarnStake / EarnRedeem 60s（與 CanaryStagePromotion 同 arm；對齊 earn_governance §2.3 line 102「TTL = 60s 與 trading lease 一致」） |
| `srv/rust/openclaw_core/src/lease_scope.rs` | tests `lease_scope_audit_str_roundtrip` | test 擴展 | all 陣列 +2 entry: (EarnStake, "EARN_STAKE") / (EarnRedeem, "EARN_REDEEM") |
| `srv/rust/openclaw_core/src/lease_scope.rs` | tests NEW `earn_scope_requires_operator_authority` | NEW test | 2 assertion: EarnStake.requires_operator_authority() == true / EarnRedeem 同 |
| `srv/rust/openclaw_core/src/lease_scope.rs` | tests NEW `earn_scope_default_ttl_60s` | NEW test | 2 assertion: EarnStake.default_ttl_ms() == 60_000 / EarnRedeem 同 |

**LOC delta**：lease_scope.rs +52 行（含中文 doc-comment 與 2 new test）/ -0 行；其他檔案未動。

**新檔**：0；既有檔修改 1。

## §3 關鍵 diff（要點）

### 3.1 enum body 新 variant

```rust
pub enum LeaseScope {
    TradeEntry,
    TradeExit,
    PositionAdjust,
    CanaryStagePromotion,
    /// Sprint 1B Earn first stake NEW — Bybit Earn stake（flexible / fixed）操作。
    /// ... (中文 doc-comment 解釋為什麼 / 對齊 / 不變量)
    EarnStake,
    /// Sprint 1B Earn first stake NEW — Bybit Earn redeem（flexible / fixed）操作。
    /// ...
    EarnRedeem,
}
```

### 3.2 三 method exhaustive match

```rust
impl LeaseScope {
    pub fn as_audit_str(self) -> &'static str {
        match self {
            // ... 既有 4 arm 不動
            Self::EarnStake => "EARN_STAKE",
            Self::EarnRedeem => "EARN_REDEEM",
        }
    }

    pub fn requires_operator_authority(self) -> bool {
        matches!(
            self,
            Self::CanaryStagePromotion | Self::EarnStake | Self::EarnRedeem
        )
    }

    pub fn default_ttl_ms(self) -> u32 {
        match self {
            Self::CanaryStagePromotion | Self::EarnStake | Self::EarnRedeem => 60_000,
            Self::TradeEntry | Self::TradeExit | Self::PositionAdjust => 30_000,
        }
    }
}
```

## §4 exhaustive match caller 更新清單

按 dispatch packet §3.4 要求 grep 所有 LeaseScope 使用點，確認 exhaustive match caller。

```bash
grep -rn "LeaseScope::" srv/rust/ --include="*.rs" | grep -v "lease_scope.rs"
```

結果：

| 檔 | 行 | 用法 | 是否需更新 |
|---|---|---|---|
| `rust/openclaw_engine/src/config/risk_config_advanced.rs` | 458 | doc-comment 提到 `LeaseScope::CanaryStagePromotion` | **不需**（doc-comment 不影響 exhaustive match） |
| `rust/openclaw_core/src/governance_core.rs` | 524 | doc-comment | **不需** |
| `rust/openclaw_core/src/governance_core.rs` | 564 | `let scope = LeaseScope::CanaryStagePromotion;` 單 variant assign | **不需**（不是 match 全 variant） |
| `rust/openclaw_core/src/governance_core.rs` | 571 | comment | **不需** |
| `rust/openclaw_core/src/governance_core.rs` | 1637 | comment | **不需** |
| `rust/openclaw_core/src/lib.rs` | 38-39 | mod-level doc-comment | **不需** |

**結論**：所有非 `lease_scope.rs` 的 LeaseScope 用法都是「單 variant 直接 reference」或 doc-comment，**沒有任何 `match scope { ... }` 全 variant 結構**。新增 EarnStake / EarnRedeem **不會破壞任何 caller**；exhaustive match 強制只發生於 lease_scope.rs 本身 3 method（已在本 IMPL 同步補上）。

進階驗證 — 在 build 階段若 caller 端有 hidden `match LeaseScope`，rustc 會 fail：

```text
cargo build --release → 0 error；僅 2 既有 dead_code warning（與本 IMPL 無關）
```

## §5 Linux PG empirical CHECK constraint 結果（dispatch packet §3.3 + §4 PA4 Wave A）

### 5.1 直接驗證既有 4 scope 字串是否被 PG CHECK 限制

```bash
ssh trade-core "docker exec -i trading_postgres psql -U trading_admin -d trading_ai -c \
  \"SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint \
    WHERE contype='c' AND \
    pg_get_constraintdef(oid) ~ '(TRADE_ENTRY|TRADE_EXIT|POSITION_ADJUST|CANARY_STAGE_PROMOTION)' \
    ORDER BY conrelid::regclass::text;\""
```

結果：**0 rows**（zero CHECK constraint references existing 4 audit strings）。

### 5.2 lease/scope/transition_kind 命名 CHECK 全表

```bash
ssh trade-core "docker exec -i trading_postgres psql -U trading_admin -d trading_ai -c \
  \"SELECT conname, conrelid::regclass AS table_name, pg_get_constraintdef(oid) \
    FROM pg_constraint WHERE contype='c' AND \
    (conname ILIKE '%lease%' OR conname ILIKE '%scope%' OR conname ILIKE '%transition_kind%')\""
```

CHECK constraints 摘要（去 hypertable chunks 重複）：

| Table | constraint | 內容 |
|---|---|---|
| `learning.lease_transitions` | `chk_lease_transitions_engine_mode` | `engine_mode IN ('paper','demo','live_demo','live_mainnet','shadow')` |
| `learning.lease_transitions` | `chk_lease_transitions_profile` | `profile IN ('Production','Validation','Exploration')` |
| `learning.lease_transitions` | `chk_lease_transitions_to_state` | `to_state IN ('DRAFT','REGISTERED','ACTIVE','BRIDGED','FROZEN','REVOKED','EXPIRED','REJECTED','CONSUMED','BYPASS')` |
| `learning.lease_transitions` | `chk_lease_transitions_ts_ms_positive` | `ts_ms > 0` |
| `governance.canary_stage_log` | `canary_stage_log_transition_kind_chk` | `transition_kind IN ('manual_promote','auto_promote','auto_rollback','incident_rollback')` |
| `governance.canary_stage_log` | `canary_stage_log_manual_promote_lease_required_chk` | `transition_kind <> 'manual_promote' OR decision_lease_id IS NOT NULL` |

### 5.3 Schema 結構檢查

`learning.lease_transitions` 表 columns（`\d learning.lease_transitions`）：

```
transition_id text NOT NULL
lease_id text NOT NULL
from_state text
to_state text NOT NULL
event text NOT NULL
initiator text NOT NULL
reason_codes text[] NOT NULL DEFAULT ARRAY[]::text[]
requires_approval boolean NOT NULL DEFAULT false
approved_by text
profile text NOT NULL
engine_mode text NOT NULL
context_id text
ts_ms bigint NOT NULL
created_at timestamptz NOT NULL DEFAULT now()
```

**關鍵發現**：`learning.lease_transitions` **沒有 `scope` column**；既有 LeaseScope 的 `as_audit_str()` 並沒被寫進 lease_transitions 表（per `rust/openclaw_engine/src/database/lease_transition_writer.rs` line 268-289 INSERT 列出 13 columns，無 scope）。

`governance.canary_stage_log.transition_kind` 限 'manual_promote' / 'auto_promote' / 'auto_rollback' / 'incident_rollback' 四值；**這是 canary stage 操作的種類字串，不是 LeaseScope 字串映射**；Earn lease 不寫 canary_stage_log，所以 EarnStake/EarnRedeem 不會撞此 CHECK。

### 5.4 Verdict — 0 V### migration needed

| 預期風險（dispatch packet §3.3）| 實證 |
|---|---|
| `governance.lease_transitions.scope` CHECK 限 4 scope → 阻 EARN_STAKE/EARN_REDEEM | **不存在**：lease_transitions 在 `learning` schema，且沒有 `scope` column；現有 LeaseScope.as_audit_str() 並未寫入此表 |
| `governance.canary_stage_log.transition_kind` CHECK 限 4 scope → 阻 EARN_* | **不衝突**：transition_kind 4 值（manual_promote/auto_promote/auto_rollback/incident_rollback）與 LeaseScope 字串集是兩個獨立 namespace；Earn 不走 canary_stage_log |
| 其他 CHECK constraint 含 4 既有 scope 字面值 | **0 match**（§5.1 ssh 查詢 0 rows） |

**結論**：Sprint 1B Earn first stake Wave B B2 純 Rust IMPL 已收斂；**不需新 V108 / V### migration**。

### 5.5 報 PM 的 follow-up 觀察（不在本 IMPL 範圍）

**Observation 1 — LeaseScope.as_audit_str() 字串的去處**：當前 `learning.lease_transitions` writer 13 columns 沒有 scope，意味著 LeaseScope 的字串目前主要被使用在：(a) `Display` impl 用於日誌 / 錯誤訊息 / metric label；(b) `CanaryStageTransition.transition_kind`（hardcoded "manual_promote"，沒走 LeaseScope 字串）。Sprint 1B Earn 階段如需 audit trail，須在 `earn_movement_writer` / `learning.governance_audit_log` 另闢欄位（dispatch packet §5 已預留 EarnMovementWriter spec；本 IMPL 不涉及）。

**Observation 2 — lease_transitions.event 欄位**：`event TEXT NOT NULL` 沒 CHECK，可承載任意字串；如未來把 LeaseScope.as_audit_str() 寫進 `event` 欄位作為 audit 字串，0 schema 變更即可。建議 PA Sprint 1B 後續 wiring 階段（B3 EarnMovementWriter / B4 reconciliation cron）一併確認此資料流。

**這 2 observation 不阻 B2 IMPL DONE；列出供 PM / PA 決定是否進 Sprint 1B 後續 task 範圍。**

## §6 治理對照

| 治理項 | 對應內容 | 證據 |
|---|---|---|
| earn_governance §2.1 hard fail-closed operator authority | `requires_operator_authority()` EarnStake/EarnRedeem 返回 true | impl + test earn_scope_requires_operator_authority |
| earn_governance §2.3 line 102「TTL = 60s 與 trading lease 一致」 | `default_ttl_ms()` EarnStake/EarnRedeem 返回 60_000 | impl + test earn_scope_default_ttl_60s |
| ADR-0020 Layer 2 manual+supervisor only | EarnStake/EarnRedeem requires_operator_authority=true | 同上 |
| ADR-0030 5-gate Gate a | EarnStake/EarnRedeem 要 operator authority | 同上 |
| V100 earn_movement_log.direction 'stake'/'redeem' 命名對齊 | as_audit_str() 返回 SCREAMING_SNAKE_CASE "EARN_STAKE"/"EARN_REDEEM"；direction column 大小寫由 EarnMovementWriter 自行映射 | impl + comment |
| W-AUDIT-9 T6 範式對齊 | CanaryStagePromotion + EarnStake + EarnRedeem 同 60s arm 同 operator-only arm；exhaustive match 強制 | impl |
| 注釋默認中文（feedback_chinese_only_comments） | 新增的 doc-comment 與 test 注釋均中文；既有英文 doc-comment 不主動清 | diff 自驗 |
| 硬邊界：max_retries / live_execution_allowed / execution_authority / system_mode 不碰 | 0 涉及 | grep 無命中 |
| 不新增 SQL migration | 本 IMPL 0 SQL 變更（§5.4 verdict 已驗證不需要）| diff 自驗 |

## §7 驗證證據

### 7.1 cargo build

```bash
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine
source ~/.cargo/env
cargo build --release 2>&1 | tail -20
```

結果：

```
warning: function `spawn_position_reconciler` is never used
warning: `openclaw_engine` (bin "openclaw-engine") generated 1 warning
    Finished `release` profile [optimized] target(s) in 27.68s
```

→ **build PASS**；0 error；僅 2 既有 dead_code warning（與本 IMPL 無關，是 ma_crossover::make_intent + tasks::spawn_position_reconciler 既有 dead code）。

### 7.2 cargo test workspace

```bash
cargo test --release --workspace --no-fail-fast 2>&1 | grep "^test result:" | awk '{p+=$4; f+=$6; i+=$8} END {print "PASS:",p,"FAIL:",f,"IGNORED:",i}'
```

結果：

```
PASS: 4081 FAIL: 0 IGNORED: 5
```

→ baseline 4079 + 2 new test (earn_scope_requires_operator_authority + earn_scope_default_ttl_60s) = 4081 PASS；**0 regression**。

### 7.3 lease_scope 局部 7 test 全綠

```bash
cargo test --release -p openclaw_core lease_scope::tests::
```

結果：

```
test lease_scope::tests::canary_stage_promotion_default_ttl_60s ... ok
test lease_scope::tests::canary_stage_promotion_requires_operator_authority ... ok
test lease_scope::tests::canary_stage_transition_manual_promote_carries_lease_id ... ok
test lease_scope::tests::earn_scope_default_ttl_60s ... ok
test lease_scope::tests::canary_stage_transition_manual_promote_serializes ... ok
test lease_scope::tests::earn_scope_requires_operator_authority ... ok
test lease_scope::tests::lease_scope_audit_str_roundtrip ... ok
test result: ok. 7 passed; 0 failed; 0 ignored; 0 measured; 363 filtered out; finished in 0.00s
```

→ lease_scope tests 7 全 PASS（包括 5 既有 + 2 新增）。

### 7.4 Linux PG empirical 證據

§5.1 / §5.2 / §5.3 已附 SQL query 與輸出；結論 0 V### needed。

## §8 不確定之處 / 限制

1. **單一 file 改動的小範圍**：B2 task 是 5-wave parallel IMPL 中的 ② variant 擴 enum；下游 wave (B1 IntentType to_lease_scope mapping / B3 EarnMovementWriter / B4 reconciliation cron) 是否會用到本 IMPL 加的 variant 與字串映射，待 E2 跨 wave review 確認。本 IMPL 僅保證 enum 本身 + 3 method exhaustive 一致。
2. **observation §5.5**：LeaseScope.as_audit_str() 在 lease_transitions 表沒 scope column → 字串目前去處主要是 log / metric / Display impl；如後續 EarnMovementWriter 想寫進 lease_transitions.event 欄位，需 PA 在 Sprint 1B 後續 task 明確接線位置。本 IMPL 不擴大決定。
3. **PG CHECK constraint 全表 grep 的覆蓋度**：用 conname pattern + audit string regex 兩條 query；但 PG 上仍可能有 trigger-based constraint 或 function 內 hardcoded validation 未被靜態 grep 抓到。如 E2 review 想要更深 grep，建議補 `pg_get_functiondef` 全函數內容檢查（本 IMPL 未做，因 dispatch packet §3.3 預期路徑只查 CHECK constraint）。
4. **2 既有 dead_code warning**：`ma_crossover::helpers::make_intent` + `tasks::spawn_position_reconciler` 已 dead code（先於本 IMPL 存在）；不在本 IMPL 修復範圍。

## §9 Operator / PM 下一步建議

1. **派 E2 review B2 patch**（單檔 lease_scope.rs +52 LOC；high signal review focal area = §6 治理對照表 + §5.4 V### verdict + tests 覆蓋）
2. **派 E4 regression**（workspace 4081 PASS / 0 FAIL 已收）
3. 等 Wave B 其他 4 task（B1/B3/B4/B5）IMPL DONE 後一併 PM 統一 commit；本 patch 不單獨 commit
4. PA 後續 Wave 設計時參考 §5.5 observation 2 — 如 Earn lease 要寫 audit trail，建議接線到 `learning.lease_transitions.event`（無 CHECK constraint，0 schema 改動）或 `learning.governance_audit_log`

## §10 完成回報 4 條（per dispatch 要求）

1. **LeaseScope 2 new variant + 3 method**：EarnStake + EarnRedeem 加入；as_audit_str / requires_operator_authority / default_ttl_ms 三 method 同步擴展 match arm；exhaustive match 編譯期強制
2. **exhaustive match caller 更新清單**：所有非 lease_scope.rs 的 6 處 LeaseScope 引用都是 doc-comment / 單 variant 直接 reference，**0 caller 需更新**；cargo build --release 0 error 驗證
3. **Linux PG empirical lease_transitions.scope CHECK constraint 結果**：`learning.lease_transitions` 表**沒有 scope column**且既存 4 個 CHECK constraint（engine_mode/profile/to_state/ts_ms）均不限 scope 字串；`governance.canary_stage_log.transition_kind` 4 值 namespace 與 LeaseScope 字串集獨立；**0 conflict，不需 V108 ALTER**
4. **cargo build + workspace test 結果**：build PASS（27.68s release，0 error，2 既有 dead_code warning）；workspace test 4081 PASS / 0 FAIL / 5 IGNORED；baseline 4079 → 4081（+2 new test 涵蓋 2 新 variant）；0 regression

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint1b_earn_b2_leasescope_impl.md`）
