"""
learning_engine package — REF-20 Paper Replay Lab math/calibration modules.
learning_engine 套件 — REF-20 Paper Replay Lab 數學/校準模組。

MODULE_NOTE (EN): Hosts Wave 5+ pure-math IMPL for Paper Replay Lab calibration
  (P3a/P3b global + cell-level execution calibration). 0 IPC / 0 DB writer / 0
  exchange dispatch — strictly offline math + DataFrame ingestion. Acceptance
  reports per V3 §11 P3a KPI consumed by replay_routes.generate_handoff_verdict
  in later waves.
MODULE_NOTE (中): 承載 Wave 5+ Paper Replay Lab 純數學 IMPL（P3a/P3b 全域 + cell
  級執行校準）。0 IPC / 0 DB writer / 0 exchange dispatch — 嚴格離線數學 +
  DataFrame 攝入。後續 Wave 由 replay_routes.generate_handoff_verdict 消費 V3
  §11 P3a KPI 結果。

V3 §11 / §12 acceptance binding:
- #15 execution_calibration_freshness (model age <= 72h)
- #16 execution_calibration_power (n>=200 strategy / n>=30 cell)
- #17 replay_cv_protocol (DSR(K)>0.95 + PBO<0.5)
- #23 replay_baseline_snapshot_provenance (engine_binary_sha + baseline_source)

Hard prerequisites for production acceptance (NOT IMPL):
- FUP-2 attribution writer deploy
- decision_outcomes timeframe '1' vs '1m' fix
- 21d demo unlock 2026-05-07
"""
