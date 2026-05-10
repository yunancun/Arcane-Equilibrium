# PA W5 三 P1 Ticket Spec 預寫報告 — Sprint N+1 W5 IMPL Phase 直接收

**Date**: 2026-05-10
**Owner**: PA
**Authority**: PM 派 PA 預寫 W5 三 P1 spec → W5 sub-agent E1 IMPL phase 直接收
**Trigger**: dispatch v3.5 §3.5 W5 P1 list 9 active 中三高 priority 預寫，省 PA D+1-3 spec phase
**Predecessor**: Sprint N+0 closure HEAD `b6ed4975`；dispatch v3.5 land

---

## 1. Spec 預寫範圍

| Ticket | Source | Spec Path | LOC 估 | E1 IMPL phase 阻塞 |
|---|---|---|---|---|
| P1-CANARY-STAGE-CRITERIA-1 | QC HIGH push back 2 | `srv/docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md` | Rust ~120 + Py ~80 + SQL ~60 + test ~80 = **~340 LOC** | W3 必先 close（W3 Stage 1 cohort 進入需 spec SoT）|
| P1-CANARY-COHORT-FREQ-23 | CC 22 invariant gap | `srv/docs/execution_plan/2026-05-10--p1_canary_cohort_freq_23_spec.md` | Rust ~50 + Py ~140 + SQL ~50 + GUI ~60 + test ~60 = **~360 LOC** | W3 必先 close（同上） |
| P1-DYNAMIC-UNBLOCK-CHECK-1 | QC v3 NEW-ISSUE-V3-4 | `srv/docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md` | Py ~330 + healthcheck ~80 + API ~60 + SQL ~50 + cron ~40 + GUI ~80 + test ~120 = **~760 LOC** | 與 P1-TONUSDT-CONDITIONAL-WATCH 同窗 |

**三 spec 總 LOC 估**：**~1460 LOC**（含 test + optional GUI）；不含 GUI 為 **~1280 LOC**。

---

## 2. 設計 alignment

三 spec 都對齊以下 governance baseline：

- **AMD-2026-05-09-03 graduated canary default**（§2.2 5-stage 表 / §2.4 cohort 切換 / §4.2 PG persistence / §4.5 LeaseScope::CanaryStagePromotion）
- **§二 16 根原則**（特別 #4 策略不繞風控 / #6 失敗默認收縮 / #8 交易可解釋 / #16 組合級風險）
- **DOC-08 §12 9 不變式**（特別 8 Reconciler diff → paper degrade 對齊 unblock 反向）
- **CLAUDE.md §四 硬邊界**（5 項 0 觸碰；無新增 live_execution_allowed / max_retries / system_mode 改動）
- **CLAUDE.md §七 SQL migration 規範**（Guard A/B/C 強制 + Linux PG dry-run mandatory）

**新增 governance artifact**：
- AMD-2026-05-10-05 — Graduated Canary Promotion Criteria Spec（W5 IMPL phase E1 land）
- AMD-2026-05-10-06 — Cohort Frequency Cap Invariant 23（同上）
- DOC-01 §5.4 補件 invariant 23 wording
- 新 healthcheck `[58]` enrich + `[63]` cohort_freq_cap + `[64]` unblock_candidates_drift
- 新 PG table `governance.cohort_freq_cap_attempts` (V086) + `governance.unblock_candidates` (V0XX)

---

## 3. 副作用識別

### 3.1 與既有 Wave 互動

- **W3（W-AUDIT-9 Stage 1 cohort observation）**：強依賴 P1-CANARY-STAGE-CRITERIA-1 + P1-CANARY-COHORT-FREQ-23；W3 IMPL 必等兩 spec 的 healthcheck `[58]` enrich + `[63]` land 才能進 atomic patch
- **W7（systemic position sync）**：W7-4 audit 已揭露 ma_crossover hot loop；P1-DYNAMIC-UNBLOCK-CHECK-1 §5.3 yo-yo detection 對 hot-loop unfreeze 行為可作 second line of defense
- **W6（reject reason metadata）**：V086 編號被 P1-CANARY-COHORT-FREQ-23 的 `cohort_freq_cap_attempts` table 用；W6 自己的 V086 reject_reason_code metadata 需與此 spec 的 V086 編號協調 — **PA flag 給 PM**：建議 V086 = W6 reject_reason_code（governance writer 改，先級高），V087 = cohort_freq_cap，V088 = unblock_candidates，並重排 W1 V085 / W1 V087 / W2 V088 編號

**V### 編號重排建議**（PA 給 PM 拍板）：

```
V085 = W1 funding_curve（不變，per dispatch v3.5 §0.7）
V086 = W6 reject_reason_code metadata（不變，governance writer 高 priority）
V087 = W1 oi_delta_panel（從 dispatch v3.5 V087 不變）
V088 = W2 panel.btc_lead_lag_panel（從 dispatch v3.5 V088 不變）
V089 = W5 P1-CANARY-COHORT-FREQ-23 cohort_freq_cap_attempts (新)
V090 = W5 P1-DYNAMIC-UNBLOCK-CHECK-1 unblock_candidates (新)
```

→ 這樣三 spec 的 SQL migration 不撞 W1/W2/W6 編號。**PA 建議 PM 同步 dispatch v3.5 §3.5 V### 編號 update**。

### 3.2 與既有 PG schema 互動

- **`governance.canary_stage_log`**（已 in AMD-2026-05-09-03 §4.2 + N+0 W-AUDIT-9 land）— P1-CANARY-COHORT-FREQ-23 需擴 `transition_kind` CHECK constraint 加 `'manual_promote_override'` enum value
- **`trading.fills`**（既有）— 三 spec 都查 fills 但不 schema 改動
- **`trading.risk_verdicts`**（既有）— P1-DYNAMIC-UNBLOCK-CHECK-1 §3 verdict logic reuse rejected_outcome_n 計算
- **`governance.canary_stage_metric_registry`**（已 in AMD-2026-05-09-03 §4.2）— P1-CANARY-STAGE-CRITERIA-1 §7.3 seed 12+ row metric SQL

### 3.3 與既有 Healthcheck 互動

`[58]` 已存在（per AMD-2026-05-09-03 §4.1）→ P1-CANARY-STAGE-CRITERIA-1 是 `[58]` enrich（不新增 ID），加 5 項細粒度檢查。新 ID `[63]` `[64]` 續 N+0/N+1 numbering family。

---

## 4. 派發設計（W5 IMPL phase）

W5 sub-agent E1 拆分（PA 預先設計，PM 派發時直接用）：

| W5 sub-agent | Spec | 文件範圍 | 阻塞關係 |
|---|---|---|---|
| W5-E1-A | P1-CANARY-STAGE-CRITERIA-1 Rust + Python + SQL | `rust/.../canary_promotion.rs` + `program_code/.../checks_governance.py` `[58]` + `V0XX__canary_stage_metric_seed.sql` | 無 |
| W5-E1-B | P1-CANARY-COHORT-FREQ-23 全套 | `rust/.../canary_promotion.rs`（與 A 同檔，加 method）+ `program_code/.../checks_governance.py` `[63]` + `V089__governance_cohort_freq_cap.sql` + `risk_config_routes.py` patch + `canary_governance_routes.py` (新檔) | A 完（Rust 同檔） |
| W5-E1-C | P1-DYNAMIC-UNBLOCK-CHECK-1 全套 | `helper_scripts/db/audit/blocked_symbols_30d_unblock_check.py` (新檔) + `checks_governance.py` `[64]` + `V090__governance_unblock_candidates.sql` + `canary_governance_routes.py` 加 endpoint + cron | 無（與 A/B 並行） |

**並行度**：A + C 100% 並行（不同檔）；B 等 A 完（Rust 同檔 sequential）；3 sub-agent 在 W5 IMPL phase 預期 2-3 day 完成 IMPL（含 E2/E4 review）。

---

## 5. E2 重點審查 3 點（跨 spec）

1. **`boundary_violation_count` source alignment**：P1-CANARY-STAGE-CRITERIA-1 §2.4 list 7 source（lease IPC / authorization / SM-04 / `[40]` / `[55]` / `[42b]` / 任一 healthcheck FAIL）必與 §4.1 healthcheck 對齊；任一 source drift = `[58]` invariant break；E2 grep 驗 7 source 全 wired
2. **Cohort identity 三元組一致**：P1-CANARY-COHORT-FREQ-23 「cohort identity = (strategy, symbol, environment)」在 Rust `CanaryCohort` struct + Python `_evaluate_promote_criteria()` + SQL `WHERE cohort_strategy=$1 AND cohort_symbol=$2 AND environment=$3` 三處 case-sensitive 一致；E2 grep 驗 cohort_strategy literal 對齊
3. **`force_eval` 不放寬 criteria**：P1-DYNAMIC-UNBLOCK-CHECK-1 §5.1 `POST /api/v1/canary/unblock/force_eval` 不可 override §3 criteria（force_eval 只插隊跑 audit，不放寬 paper_fills_30d ≥ 30 / paper_net_edge_bps_30d ≥ +5 / DSR ≥ 0.5 / PBO ≤ 0.5 條件）；E2 review API impl 確認

---

## 6. 16 原則 / DOC-08 §12 / 硬邊界 0 觸碰確認

逐 spec 確認：

| Spec | 16 原則 | DOC-08 §12 | 硬邊界 5 項 |
|---|---|---|---|
| P1-CANARY-STAGE-CRITERIA-1 | ✅（特別 #4/#6/#8/#16）| ✅（不變式 5 authorization expired → cancel_token 對齊 demote at boundary fail） | ✅（無 live_reserved / max_retries / system_mode 改動） |
| P1-CANARY-COHORT-FREQ-23 | ✅（特別 #4/#6/#8/#16）| ✅（不變式 2 lease before submit 對齊 override lease） | ✅ |
| P1-DYNAMIC-UNBLOCK-CHECK-1 | ✅（特別 #4/#6/#7/#8/#16）| ✅（不變式 8 Reconciler diff → paper degrade 對齊 unblock 反向 re-freeze） | ✅ |

**外部依賴 0**：三 spec 全用 L0 + DB + GUI，不依賴 L2 cloud LLM（per 原則 14）。

---

## 7. 後續動作

1. **PM 派 W5 IMPL phase**：dispatch §3.5 W5 P1 三 ticket assign W5-E1-A/B/C；spec 直接收（省 PA D+1-3 spec phase）
2. **V### 編號協調**：PM 拍板 V086 = W6 reject_reason_code 不變；V089/V090 = W5 spec 兩 table（dispatch §3.5 V### 編號 update）
3. **AMD 起草接力**：AMD-2026-05-10-05/06 由 W5-E1 spec IMPL 完成後 PA review + 起草 + sign-off（W5 內 land）
4. **DOC-01 §5.4 補件**：invariant 23 wording land DOC-01 V2 §5.4（W5 內）
5. **healthcheck IMPL**：`[58]` enrich + `[63]` + `[64]` IMPL（W5 W5-E1 sub-agent IMPL phase）
6. **acceptance**：dispatch §6 #14 「22 invariant + 新 invariant 23 全 PASS」確認 — 已寫入 dispatch v3.5

---

## 8. 派生教訓

- **Spec 預寫 pattern**：PA 在 dispatch sign-off 後立即預寫高 priority P1 spec → W5 sub-agent E1 IMPL 直接收 → 省 PA D+1-3 spec phase 約 2-3 day 並行壓縮
- **AMD wording 起草必 cross-ref 既有 AMD**（如 AMD-2026-05-09-03 §2.2/§2.4/§4.2/§4.5）— 避免 spec drift
- **V### 編號預留**：當 wave 內多 ticket 都需 migration 時，PA 必早提 V### 編號重排建議（避 IMPL phase 撞）
- **Frozen cells unblock 是治理空白**：當前 17 cells 無自動 reverse 機制 → selection-bias 累積；P1-DYNAMIC-UNBLOCK-CHECK-1 是 first formal unblock 治理框架

---

PA W5 三 P1 SPEC PREDRAFT DONE
- Spec 1: `srv/docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md`
- Spec 2: `srv/docs/execution_plan/2026-05-10--p1_canary_cohort_freq_23_spec.md`
- Spec 3: `srv/docs/execution_plan/2026-05-10--p1_dynamic_unblock_check_1_spec.md`
- 預估 W5 IMPL phase E1 LOC：**~1460 LOC**（含 test + optional GUI）
