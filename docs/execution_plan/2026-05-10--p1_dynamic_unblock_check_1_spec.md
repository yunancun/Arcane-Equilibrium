# P1-DYNAMIC-UNBLOCK-CHECK-1 — 30d Cycle Unblock Logic for Frozen Cells Spec

**Status**: PA SPEC DRAFT 2026-05-10 ｜ Owner: PA design / E1 IMPL / E2+E4 review
**對應 dispatch**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` §3.5 W5 P1 list
**對應 issue**: QC v3 NEW-ISSUE-V3-4（17 frozen cells 多數 0 fills 0 rejected_outcomes 無 counterfactual power）
**對應 freeze SOP**: `srv/docs/governance_dev/strategy_blocked_symbols_freeze.json` (P2-AUDIT-VERIFY-5-2026-05-09)
**對應 既有 audit**: `srv/helper_scripts/db/audit/blocked_symbols_7d_counterfactual.py`
**對應 ADR**: ADR-0018 funding_arb retire + DOC-08 §12 5（Reconciler diff → paper degrade）

---

## 1. Background + Trigger

QC v3 NEW-ISSUE-V3-4 揭露 **freeze 是 one-way street**：

- 當前 17 frozen cells（13 grid + 4 ma_crossover, per `strategy_blocked_symbols_freeze.json`）
- `blocked_symbols_7d_counterfactual.py` 7d 跑出**多數 cell 0 fills + 0 rejected_outcomes** → `evidence_power='no_7d_sample'`
- 缺 counterfactual evidence 即無從證明 cell 「永遠該 freeze」 vs 「過去 negative 是某 regime artifact，現可解封」
- selection-bias 累積：策略 fail → freeze symbol → freeze 後 0 fills（被 block）→ 0 evidence → 「permanent freeze」事實成立 → 17 → 18 → N
- TONUSDT 30d evidence 收集（P1-TONUSDT-CONDITIONAL-WATCH）+ 此 ticket 是同窗 — 都針對「freeze 必有 evidence-driven exit path」

**核心風險**：缺 dynamic unblock 機制 → 系統無法區分「結構性負 alpha cell」與「過去 sample 不代表現在」 → blocked_symbols list 單調增長 → universe 越縮越小 → strategy 可選 symbol 持續減少 → 5 active strategies edge collapse 加速。

**設計目標**：reuse 既有 `blocked_symbols_7d_counterfactual.py` 改 30d 版 + 加自動 unblock criteria + manual override SOP，確保 freeze 是「reversible」的治理動作而非永久 graveyard。

---

## 2. 30d Cycle Audit Logic

### 2.1 新檔 `blocked_symbols_30d_unblock_check.py`

**位置**：`srv/helper_scripts/db/audit/blocked_symbols_30d_unblock_check.py`

**設計**：fork 既有 `blocked_symbols_7d_counterfactual.py` 改：

- `--days 30` 預設（從 `--days 7` 改）
- 加 unblock candidate 判定 logic（§3）
- 加 GHOST cell 判定（連續 30d 0 fills + 0 rejected_outcomes → 標 `dormant_no_evidence`）
- 加 reverse 記錄機制（§6）
- 輸出加 `proposed_action` 列：`'unblock_candidate'` / `'continue_freeze'` / `'dormant_no_evidence'` / `'manual_review_required'`

### 2.2 SQL 擴充

reuse `blocked_symbols_7d_counterfactual.py` 既有 `fetch_audit_rows()`，但加新 query 收集 **paper engine 7d shadow edge**（cell 在 freeze 期 paper engine 是否仍在跑 → paper edge 可作為 unblock candidate evidence）：

```sql
WITH cells(strategy_name, symbol) AS (VALUES {values_sql})
SELECT c.strategy_name,
       c.symbol,
       COUNT(f.fill_id) FILTER (WHERE f.engine_mode='paper')::int AS paper_fills_30d,
       COALESCE(AVG(
           CASE WHEN f.engine_mode='paper'
                THEN (COALESCE(f.realized_pnl, 0) - ABS(COALESCE(f.fee, 0))) / NULLIF(f.notional_usdt, 0) * 10000
                ELSE NULL
           END
       ), NULL)::float8 AS paper_net_edge_bps_30d
FROM cells c
LEFT JOIN trading.fills f
  ON f.strategy_name = c.strategy_name
 AND f.symbol = c.symbol
 AND f.ts > now() - (%s * interval '1 day')
GROUP BY c.strategy_name, c.symbol;
```

paper engine fill (`engine_mode='paper'`) 不被 freeze 影響（freeze 只影響 demo + live blocked_symbols runtime gate）→ 30d paper edge 是 freeze 期間能拿的「實時 edge proxy」。

### 2.3 Cycle 觸發

**Cron**：`0 4 * * 0`（UTC 週日 04:00，per `feedback_github_actions_cost.md` cost-aware schedule）— 每週跑一次 30d window audit

**alternative trigger**：cell 連續 7d paper engine `paper_net_edge_bps_30d ≥ +5 bps` → 立即觸發單 cell unblock candidate eval（不等週日 cron）

---

## 3. Unblock Criteria（自動 unblock 條件）

cell C 從 frozen → unblock candidate 自動觸發 ⇔ **全部 AND**：

```
(C 在 frozen list ≥ 30d wall-clock)
AND (paper_fills_30d ≥ 30)                                  -- 統計 power 下界
AND (paper_net_edge_bps_30d ≥ +X bps)                       -- X 預設 +5 bps（保守）
AND (DSR(paper_30d) ≥ 0.5)                                  -- W-AUDIT-6 acceptance
AND (PBO ≤ 0.5)                                             -- selection-bias 防護
AND (no SM-04 escalate ≥ L3 in last 7d for cell)
AND (rejected_outcome_n ≥ 5 in last 30d if rejected_n > 0)  -- 若有 reject，必有 outcome label
```

**+X bps gate 校準**：`X=+5` 對齊 dispatch §0.7.A QC W2 review 的 demo cost 15-20 bps round-trip 邏輯 — paper edge +5 bps 是「demo 可生存」最低門檻；若 cell 連 paper +5 bps 都拿不到，demo 解封必虧。

**Verdict**：
- 全 AND PASS → `proposed_action='unblock_candidate'`
- AND 任缺 + paper_fills_30d ≥ 30 → `proposed_action='continue_freeze'`（已有 evidence 但不 promote）
- paper_fills_30d < 30 → `proposed_action='dormant_no_evidence'`（freeze 期 paper 也未跑 → 可能是 strategy 邏輯 + freeze 雙重抑制）
- DSR/PBO 計算 NULL → `proposed_action='manual_review_required'`

---

## 4. Auto-Unblock Action

cell verdict = `'unblock_candidate'` **不**自動修改 `risk_config*.toml`（per freeze SOP `runtime_effect: No runtime mutation`）— 而是：

1. **寫一筆 governance event** 到 `governance.unblock_candidates` (新 table, §6.1)：
   ```
   INSERT (cell_strategy, cell_symbol, candidate_at_ms, paper_evidence_jsonb, verdict='unblock_candidate', requires_pa_qc_signoff=true)
   ```
2. **emit GUI alert** 到 Settings tab "Frozen Cells Unblock Candidates" 區塊 — 顯示 cell + paper_30d evidence + 建議 next step（PA RFC + QC review）
3. **不**自動推 `risk_config*.toml` mutation — operator 手動觸發 §5 SOP

**Rationale**：freeze SOP `new_block_requirements` 列出「PA RFC + 7d evidence + DSR/PBO」三條件 → 反向 unblock 同樣需 governance evidence + 雙人 sign-off，不可 auto deploy。

---

## 5. Manual Override SOP

### 5.1 Operator 強制解封

operator 不等 30d cycle，可立即觸發單 cell unblock review：

1. operator 在 Settings tab 點 "Force Unblock Eval" → IPC `POST /api/v1/canary/unblock/force_eval` 帶 `cell_strategy` + `cell_symbol` + `force_reason` (≥ 50 char)
2. system 立即跑 §3 unblock criteria + §2 paper engine evidence query
3. 結果寫 `governance.unblock_candidates` + emit GUI

**注意**：force_eval **不** override §3 criteria — 仍按 verdict 判 `unblock_candidate` / `continue_freeze` / `dormant_no_evidence`。force_eval 只是「插隊跑 audit」。

### 5.2 PA + QC Sign-off → 修改 TOML

`unblock_candidate` 後：

1. **PA review** 在 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/YYYY-MM-DD--unblock_<cell>.md` 寫評估（含 paper evidence + risk acceptance）
2. **QC review** 在 `srv/docs/CCAgentWorkSpace/QC/workspace/reports/YYYY-MM-DD--unblock_<cell>.md` 從 selection-bias 視角 review
3. **PA + QC 都 APPROVE** → operator 動 `settings/strategy_params_{paper,demo,live}.toml` 從 `blocked_symbols` array 移除該 symbol（**手動**，per CLAUDE.md §四 trading_mode 同等手動準則）
4. **同 commit 動** `srv/docs/governance_dev/strategy_blocked_symbols_freeze.json` 從 `frozen_cells.<strategy>.symbols` 移除 + 加 `unfrozen_cells_history.<strategy>.symbols` array record
5. **`governance.unblock_candidates` row update** `outcome='unfrozen'` + `unfrozen_at_ms` + `pa_report_path` + `qc_report_path` + `commit_sha`

### 5.3 Reverse 記錄

unfrozen cell **若再次** trigger freeze condition（e.g. 7d demo `[40]` realized_edge_acceptance hard FAIL for cell）→ 走 freeze SOP 重新 freeze → `governance.unblock_candidates` row update `outcome='re_frozen'` + `re_frozen_at_ms` + `re_freeze_reason`。

**Selection-bias 防護**：同 cell 30d 內被 unfrozen + re-frozen ≥ 1 cycle → next cycle 進 `'manual_review_required'`（不允許自動 unblock candidate）；防 yo-yo unblock/refreeze。

---

## 6. Tracking Mechanism

### 6.1 PG persistence

新建 V0XX migration（與 P1-CANARY-COHORT-FREQ-23 V086 different number）：

```sql
CREATE TABLE IF NOT EXISTS governance.unblock_candidates (
    id BIGSERIAL PRIMARY KEY,
    cell_strategy TEXT NOT NULL,
    cell_symbol TEXT NOT NULL,
    candidate_at_ms BIGINT NOT NULL,
    paper_evidence_jsonb JSONB NOT NULL,                    -- §3 全 metric snapshot
    verdict TEXT NOT NULL,                                   -- 'unblock_candidate' | 'continue_freeze' | 'dormant_no_evidence' | 'manual_review_required'
    requires_pa_qc_signoff BOOLEAN NOT NULL DEFAULT TRUE,
    pa_report_path TEXT,                                     -- nullable; sign-off 後填
    qc_report_path TEXT,                                     -- nullable; sign-off 後填
    outcome TEXT,                                            -- nullable; 'unfrozen' | 're_frozen' | 'kept_frozen'
    unfrozen_at_ms BIGINT,
    re_frozen_at_ms BIGINT,
    commit_sha TEXT,                                         -- toml mutation commit
    re_freeze_reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_unblock_candidates_cell_time
    ON governance.unblock_candidates (cell_strategy, cell_symbol, candidate_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_unblock_candidates_outcome
    ON governance.unblock_candidates (outcome) WHERE outcome IS NOT NULL;
```

Guard A/B/C + Linux PG dry-run 強制（per CLAUDE.md §七）。

### 6.2 Healthcheck `[64] check_unblock_candidates_drift`

**Cron**：`0 5 * * 0`（週日 05:00 UTC，跟 §2.3 cycle 同窗 + 1h delay）

**語義**：
1. **Stale candidate**：`outcome=NULL` AND `candidate_at_ms < now - 14d` → **WARN**（candidate 14d 無 sign-off → operator inattention signal）
2. **Yo-yo detection**：同 cell 30d 內 unfrozen + re_frozen ≥ 1 cycle 但 next 30d 仍出現新 candidate → **FAIL**
3. **Sign-off completeness**：`outcome='unfrozen'` row 必有 `pa_report_path` + `qc_report_path` + `commit_sha` non-NULL → 任缺 = **FAIL**
4. **Audit consistency**：`unfrozen` cell 在 `strategy_blocked_symbols_freeze.json` `unfrozen_cells_history` 對應 entry → 不對應 = **WARN**（json 同步缺）

Exit code：FAIL → exit 1；WARN → exit 0 + log。

### 6.3 Reverse audit chain

- Unblock 後 cell → 7d shadow paper engine 持續觀察（既有 paper engine pipeline 已 cover）
- 若 cell post-unblock 7d demo edge `[40]` < -10 bps → trigger `re_freeze` SOP（per freeze 既有 mechanism）→ update `governance.unblock_candidates.outcome='re_frozen'`

---

## 7. IMPL Scope

### 7.1 Python script（E1-A）

- **新檔**：`srv/helper_scripts/db/audit/blocked_symbols_30d_unblock_check.py` (~300 LOC, 含 §2.2 SQL 擴充 + §3 verdict logic + §4 governance event 寫入)
- **配套 shell**：`srv/helper_scripts/db/audit/blocked_symbols_30d_unblock_check.sh` (~30 LOC)
- 既有 `blocked_symbols_7d_counterfactual.py` 不動（保留為短期 audit；新檔走 30d unblock 路徑）

### 7.2 Healthcheck（E1-B）

- `program_code/.../healthcheck/checks_governance.py` — `[64] check_unblock_candidates_drift` 加 §6.2 4 項

### 7.3 API（E1-C）

- `program_code/.../api/v1/canary_governance_routes.py`（與 P1-CANARY-COHORT-FREQ-23 同檔）— 加 `POST /api/v1/canary/unblock/force_eval`（§5.1）+ `GET /api/v1/canary/unblock/candidates`（GUI read）

### 7.4 PG（E1-D）

- 新 migration `V0XX__governance_unblock_candidates.sql`（編號等 P1-CANARY-COHORT-FREQ-23 V086 確定後 +1）+ Guard A/B/C + Linux PG dry-run

### 7.5 Cron（E1-E）

- `srv/helper_scripts/cron/dispatch_30d_unblock_cycle.cron` (~20 LOC) — 加入 cron schedule `0 4 * * 0`
- `srv/helper_scripts/cron/check_64_drift.cron` (~20 LOC) — `0 5 * * 0`

### 7.6 GUI（E1-F, optional W5 內 land OR 留 N+2）

- Settings tab 加 "Frozen Cells Unblock Candidates" 區塊 — read `governance.unblock_candidates` 顯示 candidate + paper_30d evidence + force_eval 按鈕 + sign-off 完成連結
- 不阻塞 IMPL 主路徑

**LOC 估**：Python ~330 + healthcheck ~80 + API ~60 + SQL ~50 + cron ~40 + GUI ~80 (optional) = **~560-640 LOC + ~120 LOC test**。

---

## 8. Acceptance Criteria

1. `blocked_symbols_30d_unblock_check.py` 對 17 frozen cells 跑 30d audit + 輸出 `proposed_action` 全 4 verdict（含至少 1 `dormant_no_evidence` 預期）
2. `[64] check_unblock_candidates_drift` 4 項 healthcheck 全 unit test PASS
3. `governance.unblock_candidates` table sqlx success + Guard A/B/C 全綠
4. `POST /api/v1/canary/unblock/force_eval` 對 mock cell 跑 + 寫一筆 row + 返回 verdict
5. cron `0 4 * * 0` schedule 加入 + Linux runtime test 跑出 1 次完整 cycle 寫入 row
6. PA evaluate 後第一個 `proposed_action='unblock_candidate'` cell 驗 paper_30d evidence 與 SQL output 一致
7. Reverse audit chain（unfrozen → re_frozen）流程驗（mock cell + manual write `re_freeze` event）→ `outcome='re_frozen'` 正確 update
8. E2 review confirm `force_eval` API 不允許 override §3 criteria（force_eval 只插隊，不放寬條件）
9. E4 regression 驗 cell 從 frozen → candidate → unfrozen → re_frozen 完整 lifecycle
10. dispatch §3.5 W5 P1 list `P1-DYNAMIC-UNBLOCK-CHECK-1` close + sign-off
11. CLAUDE.md §三 active gates 加 `[64]` 描述
12. 16 原則 / DOC-08 §12 / 硬邊界 5 項 0 觸碰

---

## 9. Risk + Side Effect

- **與 P1-TONUSDT-CONDITIONAL-WATCH 同窗**：TONUSDT 30d evidence 收集是此 spec 的 first real customer；TONUSDT 若驗到 `proposed_action='unblock_candidate'` 即驗證機制 end-to-end
- **Selection-bias 防護**：§5.3 yo-yo detection 是核心防線；E2 必驗「30d 內 unfrozen + re_frozen 後 next candidate 必 'manual_review_required'」
- **與 freeze SOP 互動**：unfreeze 動作 = freeze 反向操作 → 需符合 freeze SOP 的「source freeze + runtime deploy + observation follow-up」三段式（per `strategy_blocked_symbols_freeze.json:policy.new_block_requirements`）反向；具體 PA + QC report 結構對齊
- **Backward compat**：既有 `blocked_symbols_7d_counterfactual.py` 不動（短期 P2-AUDIT-VERIFY-5 audit 仍走舊腳本）；新腳本是擴充非取代
- **Race condition**：若 cron 跑 §2.3 cycle 同時 operator 手動 force_eval → 兩者各寫一筆 `governance.unblock_candidates` row（candidate_at_ms 不同），無 race；`[64]` stale candidate 邏輯按時間先後 evaluate
- **Paper engine availability**：paper engine `OPENCLAW_ENABLE_PAPER!=1` 預設關閉（per `feedback`）→ paper_fills_30d 可能持續 0 → `dormant_no_evidence` 將是常態 verdict；此非 spec 缺陷而是 paper engine policy 結果；operator 拍板「需 paper edge evidence 解封」前提是「啟動 paper engine」決策

---

*PA spec for P1-DYNAMIC-UNBLOCK-CHECK-1, Sprint N+1 W5*
