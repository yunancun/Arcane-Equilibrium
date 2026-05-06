# 融合方案執行計劃 V1 — 索引
# Agent 接手入口：讀此文件��定要做哪個 Phase，然後只讀對應的 Phase 文件

## 排期總覽（20 週 · 起算 4/11）

```
Phase 0a  (W1,    4/11-4/17):  PG Schema 基礎
Phase 0b  (W2-3,  4/18-4/30):  TimescaleDB 啟用 + 依賴
Phase 1   (W4-5,  5/01-5/14):  市場數據 + FeatureCollector + PSI
Phase 2   (W6-9,  5/15-6/11):  交易鏈 + Scorer + ONNX [+buffer]
Phase 3a  (W9-10, 6/05-6/18):  update_params() = AGT-1
Phase 3b  (W11-12,6/19-7/02):  Optuna + TS + CPCV + 黑天鵝
Phase 4   (W13-15,7/03-7/23):  Claude Teacher + News + DL-3
Phase 5   (W16-18,7/24-8/13):  James-Stein + DL-1 + DL-2
Phase 6   (W19-20,8/14-8/27):  驗收
```

## 文件索引

| 文件 | 內容 | Agent 何時讀 |
|------|------|-------------|
| [phase_0a.md](phase_0a.md) | PG Schema DDL + Grafana VIEW（19 任務） | 開始 Phase 0a 時 |
| [phase_0b.md](phase_0b.md) | TimescaleDB + 壓縮 + ML 依賴（19 任務） | 開始 Phase 0b 時 |
| [phase_1.md](phase_1.md) | 市場數據 + FeatureCollector + PSI（20 任務） | 開始 Phase 1 時 |
| [phase_2.md](phase_2.md) | 交易鏈 + Scorer + ONNX（28 任務，最大 Phase） | 開始 Phase 2 時 |
| [phase_3a.md](phase_3a.md) | update_params() Python+Rust 10 策略（17 任務） | 開始 Phase 3a 時 |
| [phase_3b.md](phase_3b.md) | Optuna + TS + CPCV + 黑天鵝（17 任務） | 開始 Phase 3b 時 |
| [phase_4.md](phase_4.md) | Claude Teacher + LinUCB + News + DL-3（20 任務） | 開始 Phase 4 時 |
| [phase_5.md](phase_5.md) | James-Stein + DL-1 + DL-2（13 任務） | 開始 Phase 5 時 |
| [phase_6.md](phase_6.md) | 漸進放權 + 驗收（13 任務） | 開始 Phase 6 時 |
| [critical_path.md](critical_path.md) | 關鍵路徑 + Contingency + 量化指標 | 排期變更時 |
| [2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md](2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md) | REF-20 Paper Replay Lab 開發方案 v0.1：早期審查材料，未 sign-off | 追溯早期風險來源時 |
| [2026-05-02--ref20_paper_replay_lab_dev_plan_v1.md](2026-05-02--ref20_paper_replay_lab_dev_plan_v1.md) | REF-20 Paper Replay Lab 開發方案 V1：第一版開發基線，已被 Round2 audit 推進為 V2 | 追溯 V2 變更來源時 |
| [2026-05-02--ref20_v1_round2_audit.md](2026-05-02--ref20_v1_round2_audit.md) | REF-20 V1 第二輪 audit：對 V1 的安全 / 資料 / 量化 / UX / API 審查意見 | 追溯 V2 採納與反對理由時 |
| [2026-05-02--ref20_paper_replay_lab_dev_plan_v2.md](2026-05-02--ref20_paper_replay_lab_dev_plan_v2.md) | REF-20 Paper Replay Lab 開發方案 V2：整合 Round2，已被 Round3/V2.1 收斂為更嚴格實作基線 | 追溯 Round3/V2.1 變更來源時 |
| [2026-05-02--ref20_v2_round3_audit.md](2026-05-02--ref20_v2_round3_audit.md) | REF-20 V2 第三輪 audit：指出 V2 仍需補 schema 物理欄位、DB role guard、migration governance、P2 isolation、UX subdoc、Mac non-actionable policy 等 P0 gates | 追溯 V2.1 採納與改寫理由時 |
| [2026-05-02--ref20_paper_replay_lab_dev_plan_v2_1_round3.md](2026-05-02--ref20_paper_replay_lab_dev_plan_v2_1_round3.md) | REF-20 Paper Replay Lab 開發方案 V2.1 Round3：當前實作前基線，接受 Round3 真實問題並保留 P2 使用 TickPipeline/IntentProcessor 的 isolated no-write 方向 | 啟動 REF-20 / Reality-Calibrated Replay 實作前 |
| [2026-05-02--ref20_ux_subdoc_v1.md](2026-05-02--ref20_ux_subdoc_v1.md) | REF-20 Paper Replay Lab UX Subdoc V1：P1 前必讀 UX contract，定義 Session/Replay/Compare/Handoff、mode badges、disabled states、no submit/cancel 邊界 | 啟動 Paper Replay Lab P1 frontend 前 |
| [2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_2.md](2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_2.md) | REF-21 Full-Chain Replay Engine V1.2：active plan；default-OFF provisional endpoint gate + subprocess env/auth 禁繼承 + V057/V058/V059 migration + promotion thresholds + maker defaults + timeout criteria + applier prerequisite + ScannerCore + LOC gate | 啟動 R1 hardening、R2/R3 或 Agent replay exploration 前 |
| [2026-05-06--ref21_gui_ux_spec_v1.md](2026-05-06--ref21_gui_ux_spec_v1.md) | REF-21 Replay GUI/UX Spec V1：default 一鍵 replay、simulation-only copy、progress/cancel/error states、Advanced manifest controls、agent quota UI、feature-flag behavior | 開始 R4 GUI 前 |
| [2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_1.md](2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1_1.md) | REF-21 Full-Chain Replay Engine V1.1：已被 V1.2 supersede，保留作第二輪 audit 追溯 | 追溯 V1.1 audit 時 |
| [2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1.md](2026-05-06--ref21_full_chain_replay_engine_dev_plan_v1.md) | REF-21 Full-Chain Replay Engine V1：已被 V1.1 supersede，保留作方向性 baseline 與 audit 追溯 | 追溯 V1 原始方向時 |
| [2026-05-XX--ref21_s1_recorder_spec_placeholder.md](2026-05-XX--ref21_s1_recorder_spec_placeholder.md) | REF-21 S1 recorder placeholder：已被 2026-05-06 REF-21 Full-Chain Replay plan 接管，僅保留 REF-20 Wave 5 歷史 trace | 追溯 REF-20 P3b placeholder 來源時 |

## 設計文件（按需讀��不需每次都讀）

| 文件 | 用途 |
|------|------|
| `docs/references/2026-04-04--unified_db_ml_news_workplan_draft_v0.1.md` | 融合方案 v0.5 完整設計（889 行） |
| `docs/references/2026-04-03--ml_dl_learning_architecture_v0.4.md` | ML/DL 架構設計 |
| `docs/references/2026-04-03--data_storage_architecture_optimal_draft_v0.1.md` | DB 原始設計 |
| `docs/references/2026-04-04--execution_plan_v1.md` | 完整執行計劃（本目錄的合併版） |
