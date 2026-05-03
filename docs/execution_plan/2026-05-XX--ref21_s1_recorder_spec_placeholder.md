# REF-21 S1 Recorder Spec — Placeholder Stub

**狀態：** Placeholder / Wave 5 R20-P3b-Q3 dispatch；REF-21 真實 spec 待後續 wave land
**契約上游：** [`docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`](2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md) §4 + §6 (replay schema 核心表 P2b binary 部署 SQL fixture，不佔 migration 編號)
**Workplan SoT：** [`docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md`](2026-05-03--ref20_implementation_workplan_v1.md) §4 Wave 5 R20-P3b-Q3 row
**Owner：** PM (REF-21 spec land 後 transfer to PA)
**Created:** 2026-05-03 (Wave 5 batch 5B PM solo)

---

## 1. 用途 / Why this placeholder exists

REF-20 Wave 5 R20-P3b-Q3 task spec：「S1 recorder dependency stub (REF-21 spec pointer)」。本 placeholder 是 Wave 5 acceptance 的最小依賴，記錄 REF-21 將替換的 contract surface，避免 P3b cell-level Bayesian (Q2) IMPL 沒 caller 方向。

REF-21 (S1 = Stage 1 trade recorder) 是 ML pipeline 的 ground truth source — 對每個 fill / order outcome 寫入結構化 metadata，供 P3b cell calibration + P3a half-life estimation 拉取。當前 (2026-05-03) 由 既有 `mlde_demo_applier` + `dream_engine` 部分提供 fills metadata，但 column shape 不對齊 P3b 需要的 cell-key + outcome distribution 欄位。

REF-21 land 後本 placeholder 將 supersede 為 RFC-grade spec doc。

---

## 2. P3b 對 S1 recorder 的最小依賴契約

P3b cell calibration 需要從 S1 拉以下資料 (per V3 §8.2 + workplan §4 R20-P3b-Q1/Q2):

| 字段 / Field | 類型 / Type | 用途 / Purpose |
|---|---|---|
| `cell_key` | TEXT | strategy-symbol-window-tier 5-tuple 唯一識別 (P3b-Q1 cell aggregation) |
| `fill_id` | UUID | 對齊 trading.fills 主鍵 |
| `net_outcome_bps` | DOUBLE | 扣費後實際結算 bps (P3a-Q1 half-life decay input) |
| `intended_outcome_bps` | DOUBLE | 策略 ex-ante 預期 bps (P3b-Q2 prior shrinkage target) |
| `execution_ts` | TIMESTAMPTZ | fill 完成時刻 (P3a-Q6 freshness gate) |
| `regime_label` | TEXT | low_vol / high_vol / trending / chop (RGM-Q2 CUSUM input) |
| `data_tier` | TEXT | real_outcome / shadow_live_demo / mlde_advisor (V3 §4.2 allowlist 對齊) |
| `signature_hash` | TEXT | manifest 簽名（Wave 4 R20-P2b-T1 signer ref） |

P3b-Q1 (cell calibration n≥30 gate) → SELECT outcome distribution per cell_key；need ≥30 fills per cell。
P3b-Q2 (NumPyro hierarchical Bayes) → SELECT (intended, net_outcome) pairs per cell；fit shrinkage prior。

---

## 3. REF-21 spec 預期內容（forward-looking）

REF-21 Stage 1 Trade Recorder spec 預期含:
- (a) 完整 schema definition (擴展 trading.fills 或新 `s1.trade_outcomes` table)
- (b) Writer architecture (Rust openclaw_engine fill writer → PG OR Python sibling)
- (c) Idempotency + retry semantics (防 dual-write)
- (d) S1 archive retention policy (180d-1y 視 phase)
- (e) Verifier: nightly check S1 row count vs trading.fills row count (fail-closed if drift)
- (f) Cross-language schema canonicalisation (Rust + Python 1:1 byte-equal)

---

## 4. P3b IMPL 對接策略 (本 Wave 5 階段)

**今期 (Wave 5 P3b IMPL)**：P3b-Q1 + Q2 mock fixture from既有 trading.fills + 部分 mlde_demo_applier audit row mapping，column 不夠的 placeholder 為 NULL。Pytest 用 mock dataframe，不依賴 real S1 deploy。

**REF-21 land 後**：P3b 模組改 import S1 reader API + drop fixture mock。Migration 路徑由 REF-21 spec 規定（V###/V### reserved 從 buffer V047-V050）。

---

## 5. 修訂歷史 / Revision History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **placeholder-v0** | 2026-05-03 | PM (Wave 5 R20-P3b-Q3) | Stub created — minimum dependency contract surface for P3b cell calibration; REF-21 spec land 後 supersede |

---

## 6. Cross-References

- 上游契約：[V3 baseline](2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md) §4.2 + §6 + §8 + §11 P3b KPI
- Workplan：[Implementation Workplan V1](2026-05-03--ref20_implementation_workplan_v1.md) §4 Wave 5 R20-P3b-Q1/Q2/Q3
- Sibling Wave 5 IMPL: P3b-Q1 cell_calibrator (commit pending) + P3b-Q2 hierarchical_bayes (commit pending)
- REF-21 真實 spec land tracker: 開單 GitHub issue / TODO P1-INFRA-21 (Wave 5 closure 時補)
