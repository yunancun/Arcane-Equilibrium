# AMD-2026-05-11-W6-1 — MIT Verify (post-PA draft)

**Date**: 2026-05-11 02:30 UTC
**Verdict**: ✅ **APPROVE-CONDITIONAL** (3 push back / 0 BLOCKER, 全 surgical wording / metadata 修正)
**Reviewer**: MIT
**Draft under review**: `srv/docs/governance_dev/amendments/2026-05-11--AMD-2026-05-11-W6-1-rfc-final-verdict-absorb.md` (608 LOC)

> **註記 (PM)**：本 verdict 由 MIT sub-agent (a3b74bc3) 於 2026-05-11 02:30 UTC inline 完成，未直寫 .md。PM 從 task notification full content 落到 file 為 governance trail 保存。

---

## §1 5 MUST + 2 SHOULD absorption verify

| # | Item | AMD 章節 | Fidelity | 狀態 |
|---|---|---|---|---|
| MUST 1 | V086 SQL §2 wording fix (lossless / row count ≠ 0 / 不破不變式 三 phrase) | §2.1 (line 100-103) + §10 step 6 + §10 重點審查 1 | HIGH | ✅ 三 phrase 全列 + D+2 14:30 UTC timing 寫入 acceptance + 撤回方案 D fallback 明確 |
| MUST 2 | V091 schema-level mutex CHECK NOT VALID | §2.3 (line 277-294) + §0 predecessor + §6 + §10 step 7 + §10 step 13 | HIGH | ✅ V091 `50e75bff` skeleton commit ref + IN FLIGHT status + D+2 14:30 ALTER VALIDATE timing 列 critical path |
| MUST 3 | W6-5 acceptance 補 5 ML pipeline metrics + purge+embargo CV | §2.4 (line 299-316) + §3 Track A + §10 step 12 | HIGH | ✅ 全 5 metric + walk-forward rolling + purge label_end_ts < test_start + embargo=1d + 缺 ≥3 項→REJECT |
| MUST 4 | CLAUDE.md §七 idempotency wording 「lossless on repeated apply」 | §2.1 (line 152-159) + §10 step 9 | HIGH | ✅ wording template 完整 + Owner=Operator + D+1 evening / D+2 morning 兩 window |
| MUST 5 | memory chain integrity 100% 結論補註 + N+2 RCA | §2.3 (line 246-258) + §6 + §10 step 14 | HIGH | ✅ DONE per commits `332a2f9c` + `9159362c`；era-split 明文；NEW orphan 3570 RCA → N+2 dispatch |
| SHOULD 6 | Track B (b) 「核心 5 策略中 ≥3 策略」+ funding_arb 排除 | §2.2 (line 232-240) + §3 Track B + §5 line 407 | HIGH | ✅ 升級為 MUST per QC PB#2 同源整合；MIT SHOULD 6 wording 主 / QC PB#2 wording 補強；funding_arb 排除三處一致 |
| SHOULD 7 | HC `[65]` post-M3 enforcement | §2.3 (line 262-273) + §6 + §10 step 14 | HIGH | ✅ DONE per commit `db17e205`；with PB#A.2 below — 注意 file path 引用差異 |

**14/14 push back absorb fidelity HIGH。0 漏接、0 立場 drift。**

---

## §2 V091 + HC [65] IMPL fidelity (vs MIT spec)

### V091 IMPL fidelity (vs MIT MUST 2 spec)

| Spec 要求 | V091 IMPL 對應 | 狀態 |
|---|---|---|
| ADD CONSTRAINT NOT VALID | `chk_reason_code_mutually_exclusive ... NOT VALID` (line 140-143) | ✅ |
| CHECK 互斥不變式 | `NOT (reject_reason_code IS NOT NULL AND close_reason_code IS NOT NULL)` (De Morgan 等價 MIT verdict §3 line 84 範例) | ✅ MIT 認可語意等價 |
| Guard A (column 存在驗 V086 land) | line 79-106 array_agg check | ✅ |
| Idempotent (兩次 apply 必 PASS) | IF NOT EXISTS pg_constraint pre-check (line 130-153) 對齊 V083:173-189 pattern | ✅ |
| 0 existing row violation 預檢 | RAISE WARNING (非 EXCEPTION) line 163-184 | ✅ |
| 不執行 ALTER VALIDATE | 純 RAISE NOTICE 提及 D+2 後續 work，本 migration 不執行 | ✅ |

**結論**：V091 IMPL fidelity HIGH，符合 MIT MUST 2 spec 全部要求。

### HC [65] IMPL fidelity (vs MIT SHOULD 7 spec)

| Spec 要求 | HC [65] IMPL 對應 | 狀態 |
|---|---|---|
| 入 W-AUDIT-4b 24h passive observation | runner.py 註冊 `[65]` invocation + cron schedule | ✅ |
| era filter `ts > '2026-05-09 09:22 UTC'` | `W_AUDIT_4B_M3_PRODUCER_DEPLOY_TS_UTC = "2026-05-09 09:22:00"` constant + `%s::timestamptz` parametrize (SQL injection-safe) | ✅ |
| post-M3 100% / pre-M3 接受 orphan | 4 verdict bands: PASS ≥95% / WARN 80-95% / FAIL <80% / WARN_LOW_SAMPLE n<30 | ✅ |
| per-strategy drill-down | sub-query 2 best-effort downgrade ladder (annotation only, 不破 global verdict) | ✅ |
| MIN_SAMPLE 防 noise | `CHAIN_INTEGRITY_MIN_SAMPLE = 30` | ✅ |
| 18 unit tests + 307/307 regression PASS | pytest 318/318 PASS in 0.27s | ✅ |

**結論**：HC [65] IMPL fidelity HIGH。MIT 認可 4 verdict band + per-strategy drill-down 設計。

---

## §3 chain integrity memory era-split fidelity (vs MIT MUST 5 spec)

| Spec 要求 | PM memory 對應 | 狀態 |
|---|---|---|
| 100% 結論補註「窄窗 n=331」 | line 84「post-M3 92/92 = 100%」+ line 76 標題明文 | ✅ |
| 樣本擴大 ratio 40% RCA | line 80-92 era-split table + line 90 結論 | ✅ |
| pre-M3 backfill defer N+2 W-AUDIT-4b followup | line 101 決策明文 | ✅ |
| AMD §6 cross-ref evidence chain | AMD §6 line 453 cite memory commits | ✅ |

**結論**：PM memory era-split fidelity HIGH，per AMD §2.3 line 251-258 ✅ DONE 標記正確。

---

## §4 W6-5 5 ML pipeline metrics + purge+embargo CV completeness (vs MIT MUST 3 spec)

| Metric | AMD 描述 | Fidelity | 狀態 |
|---|---|---|---|
| 1. Per-fold RMSE + 95% CI | "5 fold walk-forward rolling, train_window=10d, test_window=2d, embargo=1d, purge label_end_ts < test_start" (line 305) | HIGH | ✅ 同 MIT verdict §8 line 56 wording |
| 2. IS vs OOS gap | "gap > 50% → 撤回試行 baseline" (line 306) | HIGH | ✅ |
| 3. Cross-fold consistency | "std/mean > 0.5 → 不上線 even shadow" (line 307) | HIGH | ✅ |
| 4. PSI + KS p-value | "per-fold prediction distribution drift；走 `data-drift-detection` skill" (line 308) | HIGH | ✅ skill cross-ref 正確 |
| 5. cost_gate decision distribution shift | "per ratio: # cells PASS 變化 + JS shrinkage B factor 變化" (line 309) + line 311 explicit 二階因果鏈解釋 | HIGH | ✅ 二階因果鏈完整 (scorer → LinUCB reward → routing → fill 樣本 → JS estimator → cost_gate decision) |

**Purge + Embargo 完整性**:
- `time-series-cv-protocol` skill § Lopez de Prado AFML Ch.7 全套用 ✅
- `walk-forward rolling` ✅
- `purge label_end_ts < test_start` ✅
- `embargo=1d` ✅

**結論**：MUST 3 fidelity HIGH。5 metric + purge + embargo CV 完整，缺 ≥3 項 → REJECT 條款明確 (line 313)。

**唯一補強建議** (push back PB#A.3 below)：metric #5 cost_gate distribution shift 是 second-order observable，AMD §12 line 603 已 acknowledge MIT IMPL 階段如發現無法可觀測需撤回此 metric 並走 N+2 重 spec — 此 risk acceptance 寫入 OK，但建議 W6-5 IMPL 啟動前先 dry-run probe 確認可觀測性 (而非 IMPL 中發現)。

---

## §5 D+2 14:30 UTC ALTER VALIDATE critical path verify

### 三條 dependency 全列入 critical path

| Dependency | AMD 引用 | 狀態 |
|---|---|---|
| V086 SQL §2 註解 wording fix (per MIT MUST 1) | line 130 acceptance + line 388 D+2 step + line 602 open items | ✅ |
| V091 schema-level CHECK NOT VALID (per MIT MUST 2) | line 292 acceptance + line 388 D+2 step + line 561 D+2 step 13 | ✅ |
| 24h dual-write drift PASS 驗證 | line 387 D+2 14:00 UTC step | ✅ |

### Critical path 連鎖完整性

D+1 evening 20:00 engine restart → 21:00 PM sign-off → D+2 14:00 24h drift verify → D+2 14:30 ALTER VALIDATE — 三步 sequence 在 §4 (line 376-388) 列出，timing window 明確。

**唯一 issue**: AMD §4 line 388 + §10 step 13 line 561 寫的 ALTER VALIDATE 對象是 `learning.decision_features_evaluations VALIDATE CONSTRAINT decision_features_evaluations_reject_close_mutex_chk`，**但 V091 IMPL 實際目標是 `learning.decision_features` + 實際 constraint name 是 `chk_reason_code_mutually_exclusive`**（per E1 IMPL report §5.1 task spec drift catch + V091 SQL line 140-143）。詳 PB#A.1。

---

## §6 Push back items

### PB#A.1 (中 severity, MUST FIX before D+2 14:30 UTC)

**Issue**: AMD §4 line 388 + §10 step 13 line 561 中 D+2 14:30 UTC ALTER VALIDATE CONSTRAINT 的 SQL 對象寫成 `learning.decision_features_evaluations` (constraint name `decision_features_evaluations_reject_close_mutex_chk`) — 與實際 V091 IMPL (`learning.decision_features` + constraint `chk_reason_code_mutually_exclusive`) 不一致。E1 sub-agent IMPL §5.1 已 catch task spec drift 並 push back 給 PM。

**Risk**: 如 operator 直接照 AMD §4 + §10 step 13 wording 跑，PG 會 RAISE «relation "learning.decision_features_evaluations" does not have constraint "decision_features_evaluations_reject_close_mutex_chk"» — D+2 14:30 UTC 卡單。

**Action**: PA / PM commit 修正 AMD §4 line 388 + §10 step 13 line 561 為:
```
ALTER TABLE learning.decision_features
  VALIDATE CONSTRAINT chk_reason_code_mutually_exclusive;
```

**Owner**: PA (AMD edit) + PM (commit)
**Acceptance**: D+1 evening 同 commit / D+2 morning 修；本 PB 不阻 W6-1 sign-off
**Severity**: 中 (operator-facing wording correctness, 非治理立場 drift)

### PB#A.2 (低 severity, informational)

**Issue**: AMD §2.3 line 267 cite HC [65] file path 為 `helper_scripts/db/passive_wait_healthcheck/checks_chain_integrity_post_m3.py`，但實際 IMPL (per E1 report §2 file placement decision) 放在 `checks_derived_ml_hygiene.py` 內 (108→363 LOC)。

**Risk**: 低（不影響 runtime；可能 mislead 後續找 source code）。

**Action**: AMD §2.3 line 267 修為 "function in `checks_derived_ml_hygiene.py`" 或註明 sibling [26] family placement。

**Owner**: PA (AMD edit) + PM (commit)
**Acceptance**: D+1 evening 同 commit / D+2 morning 修
**Severity**: 低（informational only）

### PB#A.3 (低 severity, MUST 3 acceptance gate strengthen)

**Issue**: AMD §12 line 603 acknowledge MIT MUST 3 metric #5 (cost_gate decision distribution shift) 是 second-order observable，IMPL 階段如發現無法可觀測需撤回此 metric 並走 N+2 重 spec。但 AMD §10 step 12 (W6-5 IMPL D+3~D+4) 沒 explicit pre-IMPL dry-run probe 條款。

**Risk**: MIT IMPL 發現 metric 不可觀測 → W6-5 acceptance 重 spec → N+1 acceptance window 順延。

**Action**: AMD §10 step 12 補 sub-step「W6-5 IMPL D+3 morning pre-IMPL dry-run probe metric #5 可觀測性 (cost_gate decision distribution shift trace 是否真能 capture)；如 D+3 12:00 UTC 證明不可觀測，提撤回此 metric 並走 N+2 重 spec，acceptance 改 4 metrics + 緊縮 OOS gap 從 50% → 40%」。

**Owner**: MIT (W6-5 IMPL pre-probe) + PA (AMD edit)
**Acceptance**: AMD §10 step 12 加 sub-step；D+3 morning probe 結果決定 metric #5 retain or drop
**Severity**: 低（preventive risk mitigation；本 AMD §12 line 603 已 acknowledge risk）

---

## §7 Confidence + Sources

### Confidence: HIGH

**理由**：
1. 5 MUST + 2 SHOULD absorb fidelity 全 HIGH — 0 立場 drift / 0 漏接 / 0 wording 模糊
2. V091 + HC [65] IMPL fidelity 全 HIGH
3. PM memory era-split fidelity HIGH — post-M3 100% / pre-M3 39% 結論 + N+2 defer decision 全列入
4. W6-5 5 ML pipeline metrics + purge+embargo CV 完整 — 同 `time-series-cv-protocol` skill § Lopez de Prado AFML Ch.7 spec
5. D+2 14:30 UTC critical path 三 dependency 全列；唯一 issue 是 PB#A.1 wording drift（中 severity，非立場 drift）
6. 三 push back 全 surgical wording / metadata / acceptance gate strengthen 性質，0 BLOCKER；本 AMD 升 ✅ Accepted 後 N+1 W6 wave 無 reblock

### 唯一不確定 (不阻 sign-off)

1. **PB#A.1**: D+2 14:30 UTC ALTER VALIDATE 對象 wording drift 是否屬「PA absorb 過程的 typo」vs「task spec drift 未修正」— PA 應 cross-ref E1 IMPL §5.1 push back 並修
2. **PB#A.2**: HC [65] file path 引用差異是 PA 寫作時 mock path vs 實際 IMPL 放置決策；不影響 governance fidelity
3. **PB#A.3**: cost_gate distribution shift metric 可觀測性風險未在 IMPL 啟動前 probe — AMD §12 line 603 已 acknowledge，PB#A.3 是 strengthen 不是反對

### Sources

1. AMD draft: `srv/docs/governance_dev/amendments/2026-05-11--AMD-2026-05-11-W6-1-rfc-final-verdict-absorb.md` (608 LOC)
2. PA sign-off report: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--amd_w6_1_draft_pa_signoff.md` (264 LOC)
3. MIT 原 verdict: `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_1_rfc_mit_signoff_verdict.md` (307 LOC)
4. V091 IMPL report: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--v091_decision_features_mutex_check_impl.md` (374 LOC) + V091 SQL `srv/sql/migrations/V091__decision_features_reject_close_mutex_check.sql` (215 LOC)
5. HC [65] IMPL report: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--check_65_chain_integrity_post_m3_impl.md` (203 LOC)
6. PM memory era-split: `srv/memory/project_2026_05_10_sprint_n0_closure.md` (line 76-101 era-split section)
7. MIT skill `time-series-cv-protocol` (purge + embargo + walk-forward)
8. MIT skill `data-drift-detection` (PSI + KS metric #4 cross-ref)
9. MIT skill `db-schema-design-financial-time-series` (Guard A/B/C + NOT VALID CHECK pattern)
10. CLAUDE.md §七 SQL migration 規範 + idempotency wording (MUST 4 target)
11. ADR-0018 funding_arb retire (SHOULD 6 cross-ref)
12. AFML Ch.7 (Lopez de Prado purge + embargo)

---

## §8 Sign-off

**MIT verdict**: ✅ **APPROVE-CONDITIONAL** (3 push back / 0 BLOCKER)

**3 push back 全屬 wording / metadata / acceptance gate strengthen 性質**：
- PB#A.1 (中) — D+2 14:30 ALTER VALIDATE 對象 wording 修正
- PB#A.2 (低) — HC [65] file path 引用更新
- PB#A.3 (低) — MUST 3 metric #5 pre-IMPL dry-run probe 條款補入 §10 step 12

**3 push back 全可在 D+1 evening 同 commit / D+2 morning 修，不阻 W6-1 sign-off**。本 AMD 升 ✅ Accepted 後 N+1 W6 wave 無 reblock。

**14/14 push back absorb fidelity HIGH**。MIT confidence HIGH。

**MIT AUDIT DONE**
