# R4 Pass B — Workflow F Cross-Ref Audit Verification

**Auditor**: R4 (read-only)
**Date**: 2026-05-27 (UTC)
**Phase**: Workflow F Phase 2 R4 Pass B（post TW cascade land）
**Baseline**: HEAD `e913adbf`（AMD-2026-05-26-01 + TW cascade in tree）
**Pass A reference**: `srv/docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-26--workflow-f-cross-ref-audit.md`
**Verdict**: **APPROVE** — Workflow F Phase 2 R4 CLOSE

---

## A. AMD-26-01 Cascade 命中率

### A.1 Primary 5/5 = 100% PASS

| Layer | Target | 命中 | 備註 |
|---|---|:-:|---|
| Primary 1 | `docs/README.md` line 228 (amendments table) + line 783 (ADR-0018 entry "Retired closed") | ✅ | 行內 cross-ref + Retired closed wording 全 land |
| Primary 2 | `docs/governance_dev/SPECIFICATION_REGISTER.md` line 25 AMD row | ✅ | Last Updated 2026-05-26；AMD row 完整含 ADR-0018 Status 升格描述 |
| Primary 3 | `docs/adr/0018-funding-arb-v2-deprecation-watch.md` lines 1-51 | ✅ | Status: **Retired closed**；升格 wording 完整；§Consequences W-AUDIT-6 cleanup completion + AMD-26-01 §References |
| Primary 4 | `docs/KNOWN_ISSUES.md` line 476-480 | ✅ | "P0-EDGE-1：4 textbook 策略 negative realized edge" + 行內 funding_arb retired note |
| Primary 5 | `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` line 842 + 763 + 992-993 | ✅ | P0-EDGE-1 cohort 4 textbook reframe + Amendments roster 新增 AMD-26-01 |

### A.2 Secondary 19/19 = 100% PASS

| Secondary scope | Target count | 命中 | 結果 |
|---|---:|---:|---|
| 3 TOML `[funding_arb]` 註釋 (paper/demo/live) | 3 | 3 | ✅ 全 AMD-26-01 cross-ref land |
| 4 ADR cross-ref (0021 / 0025 / 0038 / 0039) | 4 | 4 | ✅ 全 inline "retired per AMD-26-01" + ADR-0046 future redesign slot ref |
| 3 dispatch packet (sprint_1a / sprint_2_business / alpha_candidate_1_funding_short_v2_spec) | 3 | 3 | ✅ 全 inline cross-ref |
| 6 SQL migration header (V031/V034/V084/V086/V090/V101) | 6 | 6 | ✅ 全 "historical-only post AMD-2026-05-26-01" header；不改 enum |
| TODO §1 §6 §15 | 3 | 3 | ✅ 全對齊 |

---

## B. 0 Dangling Reference Verify — PASS

`rg AMD-2026-05-26-01` = **25 file hit**，全屬下列 4 類：
1. AMD self + PA spec self（2 file）
2. Primary 5 cascade target（5 file）
3. Secondary cascade（16 file）
4. R4 Pass A report（1 file，retain）

`funding_arb` 全 docs 300+ file 提及，其中 cascade scope 內所有 ACTIVE 引用點均已對應 AMD-26-01 / ADR-0018 Retired closed lineage（archive + CCAgentWorkSpace 歷史 per PA spec §4.3 不更新）。

---

## C. TW Discoveries 評估

### C.1 EA-3 hotfix spec (`2026-05-25--ea3_funding_arb_sl_gate_p1_hotfix_spec.md`)

- 內文已 self-document 為 PA reject hot-fix → P3 carry-over verdict
- 性質非 IMPL spec 而是 verdict report
- 無 explicit `Status: Superseded` header
- **R4 評估**：LOW / OPTIONAL；不阻 Workflow F closure；下次 R4 cycle 或 D+7 E1 IMPL piggyback

### C.2 8 個 helper_scripts/db/audit/ 校正

**事實校正**：TW report 提「8 個」與實際 grep 不符。
- `helper_scripts/db/audit/` 含 funding_arb 實際 = **4 file**：
  - `2026-05-09_3c_7d_audit.py`（historical 3C re-enable audit）
  - `2026-05-16_funding_arb_14d_audit.py`（n=18 dormant audit source）
  - `2026-05-16_funding_arb_14d_audit.sh`
  - `test_funding_arb_14d_audit.py`
- 廣義 `helper_scripts/` 含 funding_arb = **16 file**（cron/passive_wait/canary/counterfactual/SCRIPT_INDEX），多數屬 enum allowlist 不需動

**MIT D+7 retire scope（per PA spec §6.2 + AMD-26-01 §6.2）**：
- ✅ 3 file (`2026-05-16_funding_arb_14d_audit.py/sh` + `test_*`) MIT D+7 retire 對應充分
- ⚠ `2026-05-09_3c_7d_audit.py` 是 historical；可保留 lineage
- 廣義 16 file 其餘 12 file 屬 enum hardcode，per PA §1.3 不需動

---

## D. Drift Carry-over（PA spec §4.1 underspecified 殘留）

| # | Item | Status | R4 建議 |
|---|---|---|---|
| 1 | Rust src 60 file (PA 列 5-8 file) | DEFERRED to D+7 E1 IMPL | E1 dispatch 前 grep 全表確認 `#[deprecated]` warning storm scope；IMPL phase 範疇 |
| 2 | SQL V033 (`fills_exit_reason.sql`) 含 enum `strategy_close_funding_arb` | CARRY-OVER | 屬 historical enum 同 V086 line 287 模式；建議下次 R4 cycle 或 D+7 piggyback |
| 3 | helper_scripts 16 file vs PA 列 3 file | DEFERRED to D+7 MIT | per C.2 MIT D+7 已對齊；廣義 16 file 多 enum allowlist 不需動 |
| 4 | EA-3 hotfix spec optional SUPERSEDED header | LOW / OPTIONAL | per C.1；不阻 closure |
| 5 | W-AUDIT-8B funding_skew_directional spec | NOT FIXED (intentional) | funding_skew ≠ funding_arb concept；R4 評估 **無需** AMD-26-01 cross-ref |
| 6 | `docs/README.md` specs/ 目錄索引漏 PA spec `2026-05-26--funding-arb-deprecation-cascade.md` | **NEW drift Pass B** | LOW；line 226 列 5-22 v099 但漏 5-26 PA spec；建議下次 cascade 補 |

---

## E. TODO Drift

| 項 | 觀察 | 狀態 |
|---|---|---|
| §1 第四列 P0-FUNDING-ARB-DECISION-FORCE | ✅ CLOSED 2026-05-26 (D)；cascade Workflow F NEW | OK |
| §6 P1-FUNDING-ARB-DEPRECATION-CASCADE | IMPL DONE markers | OK |
| §6 P1-EDGE-2 (funding_arb) | line 169 ARCHIVE-READY post AMD-26-01；D+7 E1 IMPL DONE 後可移 §-1 archive | OK |
| §9 Workflow F | line 90 NEW row "T2: PA→TW→R4" 4-6 hr | OK |
| §15 #1 | line 204 ~~D+3 升等拍板~~ CLOSED reframed | OK |
| §15 #5 | OBSOLETED 2026-05-26 V117 framed for ADR-0046 future redesign | OK |

---

## F. Final Verdict

**APPROVE — Workflow F Phase 2 R4 CLOSE**

**Closed**：
- AMD-2026-05-26-01 + Primary 5/5 + Secondary 19/19 全 land
- 0 dangling reference confirmed
- TODO §1/§6/§9/§15 全對齊
- ADR-0018 Status 升 Retired closed wording 完整

**Non-blocking carry-over (3 LOW)**（D+7 piggyback）：
1. EA-3 hotfix spec optional SUPERSEDED header
2. SQL V033 enum header (strategy_close_funding_arb)
3. `docs/README.md` specs/ 目錄漏 PA spec entry

**下次 R4 trigger** = D+7 (~2026-06-02) E1 `#[deprecated]` IMPL land 後 piggyback Rust /// doc comment 同步 + 3 carry-over fix。

---

**R4 DOC AUDIT DONE**: APPROVE；5/5 primary + 19/19 secondary + 0 dangling；3 LOW carry-over deferred D+7。
