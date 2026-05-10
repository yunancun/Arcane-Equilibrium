# Amendment AMD-2026-05-10-05 — Graduated Canary Stage Criteria 寫死

**對應 spec**: AMD-2026-05-09-03 §2.2（5-stage promote/rollback 表）· §4.1 healthcheck `[58]` · §4.5 manual_promote Decision Lease
**Refines**: AMD-2026-05-09-03 §2.2 表的 promote / rollback 條件文字描述，補上 IMPL 落地時的精確語義（AND/OR 關係 / sample size floor / wall-clock floor / 字段檢查）
**Cross-references**:
- AMD-2026-05-09-03 (graduated canary default)
- AMD-2026-05-02-01 (SM-02 R-04 Decision Lease retrofit Path A)
- AMD-2026-05-10-04 (TOML drift fix SOP)
- ADR-0022 (Strategist wide adjustment)
- DOC-08 §12 (9 條安全不變量 — 不適用 graduated canary 範圍)
- CLAUDE.md §二 (16 根原則) / §四 (硬邊界)
- Spec source: `docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md`

**日期**: 2026-05-10
**作者**: PA（W5-E1-A spec land 同次提案）+ E1（IMPL 階段反向 verify 起草）
**狀態**: Drafted — 待 PA + QC + PM sign-off (Sprint N+1 D+0 派發後階段)
**索引**: `docs/README.md` Amendments index
**TODO 連結**: W5-E1-A IMPL / W3 cohort SQL pipeline / W-AUDIT-9 acceptance

---

## 1. Background

### 1.1 QC HIGH push back 2 觸發

QC 在 Sprint N+1 dispatch v3 review 提了 **HIGH push back 2**（per
`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md`）—
AMD-2026-05-09-03 §2.2 5-stage 表雖列出 promotion / rollback 條件文字，但 IMPL
落地時面臨歧義：

- §2.2 Stage 1 → Stage 2 寫「`entry_fills ≥ 10` AND `boundary_violation_count == 0`」
  + 觀察期 7d wall-clock — 但兩個條件**沒明文 AND/OR 關係**：是「7d **AND**
  entry_fills≥10」（whichever later）還是「7d **OR** entry_fills≥10」
  （whichever earlier）？
- 「sample size n ≥ 200 OR wall-clock ≥ 72h whichever later」推薦字句出現在
  dispatch §3.3 但 AMD 文未寫死，N+0 W-AUDIT-9 IMPL E1 無法解析
- §0.2.B post-V082 W6 baseline 揭露**真實 close fill 只有 9 條**，若 promote
  criteria 用 `entry_fills` 可能永遠不達 → 必須加 wall-clock floor（避免無限
  dwell）+ 加 sample 上限 cap（避免 reject 樣本污染 entry 計數）

### 1.2 spec land 同次補件

W5-E1-A spec
（`docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md`）已把
§2-§5 promote / rollback 條件落到可執行 SQL + Rust pure-logic 精度。本 amendment
是 spec 對 AMD-2026-05-09-03 §2.2 的**精確化補件**，不變更 5-stage 哲學或姿態，
只把語義收緊到 IMPL 可消化粒度。

---

## 2. 修訂內容（核心）

### 2.1 §2.2 5-stage 表 SoT 重定義

§2.2 5-stage 表的 promotion / rollback 條件以 **W5-E1-A spec §2-§5 為 SoT**。
§4.1 healthcheck `[58]` SQL 與 spec §2-§5 公式 1:1 對應（V089 seed
governance.canary_stage_metric_registry 為持久化 SoT）。§4.5 manual_promote
Decision Lease 必伴隨 cohort 字段檢查（驗 cohort 與 stage entry cohort 一致）。

### 2.2 Stage 1 → Stage 2 promote 條件（精確化）

```
Stage 1 → Stage 2 PROMOTE 觸發 ⇔
    (wall_clock_elapsed_ms ≥ 7 * 86_400_000)         # 7d wall-clock floor
    AND (entry_fills_count ≥ 10)                      # 質量門檻
    AND (boundary_violation_count == 0)               # 0 boundary trip
    AND (sample_size_floor_ms ≥ 72 * 3_600_000)       # 72h sample floor (whichever later)
```

- 「whichever later」精確語義：wall_clock 與 sample_size_floor 都必達（兩者
  AND）；entry_fills 是質量 gate，必獨立達 10
- `entry_fills_count` SQL 排除 `rejected_governance` reject（per spec §2.2）—
  避免 reject sample 污染 entry 計數
- `wall_clock_elapsed_ms = current_ts_ms - stage_entered_at_ms`，**不**接受
  IPC `patch_risk_config` 重啟 reset（per AMD-2026-05-09-03 §2.4 cohort 切換才
  reset）
- `sample_size_floor_ms = 72h` 是 QC HIGH push back 2 推薦下界 — 即使 wall_clock
  7d 達且 entry_fills≥10，若 stage entered <72h 仍 PENDING（防意外 cohort
  切換 race）

**Fail conditions**：`entry_fills_count` 在 14d wall-clock 仍 < 10 → escalate
WARN 到 GUI surface「stage_1_starvation」（不 auto-demote，operator 拍板是否
切 cohort 或 archive）。

### 2.3 Stage 2 → Stage 3 promote 條件

```
Stage 2 → Stage 3 PROMOTE 觸發 ⇔
    (wall_clock_elapsed_ms ≥ 14 * 86_400_000)        # 14d wall-clock
    AND (entry_fills_count ≥ 30)
    AND (gross_pnl_usdt > -5.0)                       # strict floor
    AND (DSR > 0.5)                                   # by W-AUDIT-6 acceptance pipeline
    AND (boundary_violation_count == 0)
    AND (sample_size_floor_ms ≥ 168h)                 # 7d hard floor for demo
```

- DSR 計算 reuse W-AUDIT-6 SDR/PBO writer（per AMD-2026-05-02-01 + DOC-08 §6
  acceptance）— cohort scope `(strategy, symbol, environment, stage_entered_at_ms..now)`
- DSR=NULL → PROMOTE PENDING（不 fail，等下次 cycle）
- Fail：28d wall-clock 仍未滿足任一條件 → escalate WARN + operator 拍板（Stage
  2 dwell extension 或 demote 至 Stage 1 重觀察）

### 2.4 Stage 3 → Stage 4 promote 條件

```
Stage 3 → Stage 4 PROMOTE 觸發 ⇔
    (wall_clock_elapsed_ms ≥ 21 * 86_400_000)        # 21d wall-clock
    AND (gross_pnl_usdt > 0)                          # strict positive
    AND (DSR PASS by W-AUDIT-6 acceptance)
    AND (PBO ≤ 0.5)
    AND (attribution_chain_ok ratio ≥ 0.7)            # [55] healthcheck 同源
    AND (boundary_violation_count == 0)
```

Stage 4 **不 auto-promote**（per AMD-2026-05-09-03 §2.2 表）— `[58]` healthcheck
PASS 後寫 GUI surface「ready_for_stage_4_review」，operator 拍板 + signed
authorization + Decision Lease + 5-gate live boundary 全鏈滿足才升 4。

### 2.5 Demote 條件（任一 trip → fall back 1 stage）

| 來源 stage | Demote → | trip 條件（OR）|
|---|---|---|
| Stage 1 | Stage 0 | `boundary_violation_count > 0` OR `lease IPC 失敗率 1h > 1%` OR SM-04 ≥ L3 |
| Stage 2 | Stage 1 | `gross_pnl_usdt < -10.0` OR `DSR < 0` OR Stage 1 任一 rollback 條件持續 ≥ 6h |
| Stage 3 | Stage 2 | `gross_pnl_usdt < -20.0` OR `DSR < 0` OR `attribution_chain_ok ratio < 0.3` OR Stage 2 任一條件持續 ≥ 12h |
| Stage 4 | Stage 0（不是 Stage 3）| 任一 boundary 失敗 → cancel_token shutdown，per §2.2 表 |

**Demote 機制**：自動觸發 → write `governance.canary_stage_log` row
`transition_kind='auto_rollback'` + `from_stage`/`to_stage` + `reason` 詳述 +
`metric_snapshot`；觀察期 timer 重置為新 stage。

### 2.6 SM-04 cross-stage hard demote

per AMD-2026-05-09-03 §3.2 + spec §2.4 第 3 條：SM-04 escalate level ≥ L3 跨
stage 強制 demote 至 Stage 0（不論 source stage）。本條為**全 stage 共同硬不變式**，
與 §2.5 表的 OR-trigger 並行（先 evaluate SM-04 hard demote，再評估 stage 自家
trigger）。

---

## 3. 不適用範圍（仍維持 fail-closed）

本 amendment **不適用**下列場景，仍**強制** binary fail-closed（per
AMD-2026-05-09-03 §3）：

### 3.1 DOC-08 §12 9 條安全不變量
（pre-trade audit replay / lease acquired before submit / fills writer / SM-04
auto bleed / authorization expired → cancel_token / Mainnet OPENCLAW_ALLOW_MAINNET
/ Bybit retCode != 0 / Reconciler diff → paper degrade / Operator 角色 +
live_reserved 缺一即拒）— 任何 stage 違反任一條 = 立即 auto-rollback 至 Stage 0
+ 觸發 incident。

### 3.2 SM-04 CIRCUIT_BREAKER 5 ladder
本 amendment 第 §2.6 已固化 SM-04 ≥ L3 跨 stage hard demote 至 Stage 0。

### 3.3 Live boundary 5-gate
（CLAUDE.md §四 line 125-136）— Stage 4 enter 必須**全部**滿足。Stage 1-3
不可作為 live gate 替代。

### 3.4 §二 16 根原則的硬不變式
所有 stage 都通過唯一 IntentProcessor / Guardian veto / StopManager 等。
graduated canary 不放鬆任一條。

---

## 4. 配套機制

### 4.1 Healthcheck `[58a]` enrich

新增 `[58a] stage_criteria_eval`（package
`helper_scripts/db/passive_wait_healthcheck/checks_canary_stage_criteria.py`，
與 `[58]` 同 family）— evidence collection 報告：
1. V089 seed 每 stage promote / rollback metric row count
2. 對 active cohort latest stage，列出對應 metric 列表 + threshold + observation_window
3. drift detection — 與 spec EXPECTED_METRIC_COUNT_PER_STAGE 對齊；缺即 WARN

**Verdict 哲學**：verdict-preserving WARN-on-drift / PASS-on-full-seed（不 hard
FAIL，避免阻塞 silent-dead 偵測）。實際 cohort metric 值計算延後到 W3 cohort
SQL pipeline land 後 enrich。

**Cron**：與 `[58]` 同期 `0 */6 * * *`。

### 4.2 PG 持久化（V089 migration）

新建 `sql/migrations/V089__governance_canary_stage_metric_seed.sql` —
INSERT 18 row 進 V080 `governance.canary_stage_metric_registry`：
- Stage 1: 4 promote (wall_clock / entry_fills / boundary / sample_floor) + 1 rollback (boundary)
- Stage 2: 5 promote (wall_clock / entry_fills / gross_pnl / DSR / sample_floor) + 2 rollback (gross_pnl / DSR)
- Stage 3: 5 promote (wall_clock / gross_pnl / DSR / PBO / attribution) + 2 rollback (gross_pnl / attribution)
- Stage 4: 0 promote (operator-pinned) + 1 rollback (boundary → 0)

ON CONFLICT (stage, metric_name) WHERE active=true DO NOTHING — 走 V080
partial unique index `uq_canary_stage_metric_registry_active`，idempotent re-run。

**Guard A/B/C** 強制 + Linux PG dry-run mandatory（per ADR-0011 +
`feedback_v_migration_pg_dry_run.md`）。

### 4.3 Rust pure-logic（canary_promotion.rs）

新建 `rust/openclaw_engine/src/config/canary_promotion.rs`（~620 LOC，含 24
unit test）— `is_promote_eligible` / `is_rollback_tripped` 兩 API 對應 spec
§2-§5 公式 100%。預期由 ExecutorAgent stage-aware shadow_mode_provider 跨 IPC
呼叫；shadow eval 可在 Rust 側做本地預判（per spec §7.1）。

### 4.4 Python evaluator helper

新建
`program_code/exchange_connectors/bybit_connector/control_api_v1/app/canary_promotion_eval.py`
（~370 LOC）— Rust mirror Python evaluator。`evaluate_promote_criteria()` /
`evaluate_rollback_criteria()` 兩 API，threshold 與 Rust 端 byte-identical。

跨語言一致性測試（per spec §8 acceptance #4）：cohort `grid_trading × BTCUSDT
× demo` Python helper 跑出 PromoteVerdict 必與 V089 seed + `[58a]` SQL 結果
一致。Sign-off 待 W3 cohort SQL pipeline land 後做 cross-language verification。

### 4.5 Decision Lease 接線（manual_promote）

per AMD-2026-05-09-03 §4.5 — manual stage promotion 必伴隨
`LeaseScope::CanaryStagePromotion` lease（TTL 60s strict）。本 amendment 補加：
manual_promote IPC payload 必含 `cohort_strategy` / `cohort_symbol` /
`cohort_environment` 三字段檢查 — 與 stage entry cohort 不一致即 reject
（防 cohort drift race）。

---

## 5. IMPL Wave

per spec §7 Implementation scope：
- W5-E1-A Rust + Python + SQL（本 amendment 起草階段已 IMPL，待 PA + QC + PM sign-off）
- W3 cohort SQL pipeline land 後啟用 `[58a]` 真實 cohort metric eval
- W-AUDIT-9 T7 E4 regression 加 5×5 stage transition matrix（25 case）

---

## 6. Decision rationale & risk acceptance

### 6.1 為何接受此 amendment

1. **AMD §2.2 字面表達不足以 IMPL**：QC HIGH push back 2 揭露兩條件 AND/OR 歧義；
   不收緊到 IMPL 粒度將造成 W3 / W5 並行 IMPL 衝突
2. **W3 阻塞依賴關係**：W5 spec 必先 close（spec land + AMD sign-off），W3 才能
   進 Stage 1 atomic patch；違反 = W3 IMPL 撞無 SoT
3. **Backward compat 嚴化**：legacy `entry_fills ≥ 10` 字面條件被 §2.2 嚴化
   為「AND wall_clock ≥ 7d AND boundary=0 AND sample_floor ≥ 72h」— 現有 mock
   test 若 fake `entry_fills=15` 但 `wall_clock=1h` 將 Pending（pre-spec 為
   Promote），E2 必 update（spec §9 已標）
4. **與 §二 16 原則合規**：本 amendment 不放寬 fail-closed 哲學；rollback
   仍是 stricter（回更低 stage），完全滿足「不確定時保守」精神

### 6.2 §二 16 原則合規確認

- 原則 1（單一寫入口）：所有 stage 仍通過 IntentProcessor — ✅
- 原則 2（讀寫分離）：`[58a]` healthcheck 純 SELECT；GUI 顯示 read-only — ✅
- 原則 3（AI ≠ 命令）：promote 必 lease + audit — ✅
- 原則 4（策略不繞風控）：Guardian veto / SM-04 ladder 在所有 stage active — ✅
- 原則 5（生存 > 利潤）：StopManager + 對抗性止損所有 stage active — ✅
- 原則 6（失敗默認收縮）：rollback 永遠回更低 stage，不向 Stage 4 漂移 — ✅
- 原則 7（學習 ≠ Live）：學習平面與 live 平面隔離不變 — ✅
- 原則 8（交易可解釋）：每 transition 落 `canary_stage_log` + metric_snapshot — ✅
- 原則 9（雙重防線）：本地 stop + 交易所條件單在 Stage ≥ 1 都 active — ✅
- 原則 10（認知誠實）：metric_snapshot 區分 PASS / threshold / margin — ✅
- 原則 11（Agent 最大自主）：cohort 內 Agent 自主不變，cohort 邊界由 operator 拍板 — ✅
- 其他原則對齊 AMD-2026-05-09-03 §6.3 — ✅

### 6.3 與既有 amendment / ADR 的關係

- **AMD-2026-05-09-03 §2.2**：本 amendment refines 為 SoT，不替代
- **AMD-2026-05-02-01 SM-02 R-04**：Decision Lease per-intent 不變；本 amendment
  §4.5 補加 manual_promote cohort 字段檢查
- **AMD-2026-05-10-04 TOML drift fix SOP**：與本 amendment 並行；TOML drift fix
  針對 demo TOML，本 amendment 針對 spec criteria
- **ADR-0017 Scanner is evidence not authority**：scanner 在所有 stage 都是
  evidence — 本 amendment 不變更 — ✅
- **ADR-0018 funding_arb retire**：funding_arb 不在 active strategy set，本
  amendment 不可選為 cohort — ✅
- **ADR-0020 Layer2 manual + supervisor only**：Layer2 不參與 stage transition
  automation — ✅

---

## 7. 後續動作（D+1 必跟進）

| # | 動作 | Owner | 時點 |
|---|---|---|---|
| 1 | V089 Linux PG dry-run + apply（per ADR-0011） | E1-B | D+1 W5 dispatch |
| 2 | E2 review canary_promotion.rs + canary_promotion_eval.py + V089 + `[58a]` | E2 | D+1 |
| 3 | E4 regression: 5×5 stage transition matrix + boundary case | E4 | D+1+ |
| 4 | W3 cohort SQL pipeline land 後啟用 `[58a]` 真實 metric eval enrich | E1 | post-W3 |
| 5 | CLAUDE.md §三 active gates 加 `[58a]` 描述 + 引用本 amendment | TW + PA | post-PM sign-off |

**E2 重點審查 3 點**：
1. `boundary_violation_count` 計算與 spec §2.4 list 7 source 全對齊
   （lease IPC 失敗率 / authorization revoke / SM-04 escalate / Decision Lease deny
   / Guardian veto / `_read_shadow_mode()` exception / OR 等）
2. V089 seed threshold 與 spec §2-§5 公式 byte-identical（reviewer 必逐項對齊）
3. Python evaluator 與 Rust pure-logic 跨語言一致性 — 同 cohort 同 metrics 必
   give 同 verdict

---

## 8. Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| PA | spec author + 本 amendment 起草指示 | 2026-05-10 | 🟡 Pending（W5-E1-A IMPL DONE 後 review）|
| E1 | 本 amendment IMPL 階段反向 verify 起草 | 2026-05-10 | ✅ Drafted |
| QC | HIGH push back 2 觸發 spec | 2026-05-10 | 🟡 Pending |
| E2 | code review canary_promotion.rs + canary_promotion_eval.py + V089 + `[58a]` | TBD | 🟡 Pending |
| E4 | regression 5×5 transition matrix | TBD | 🟡 Pending |
| PM | TBD（W5-E1-A IMPL DONE → E2/E4/QC sign-off → PM commit） | TBD | 🟡 Pending |

---

*OpenClaw / Arcane Equilibrium Governance Amendment — AMD-2026-05-10-05*
