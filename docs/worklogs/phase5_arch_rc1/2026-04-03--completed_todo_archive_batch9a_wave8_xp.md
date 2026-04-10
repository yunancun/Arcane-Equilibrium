# 已完成項歸檔：Batch 9A + Wave 8A-8D + XP-1~4
# Archive: Completed items from TODO.md (2026-04-03)

**歸檔日期**：2026-04-03
**歸檔原因**：全路線圖定稿（Phase 0-3+R），清理 TODO.md 只保留待做項

---

## Batch 9A — 確定性自適應風控（全部完成 · 2026-04-02 · commit d9b102f）

- [x] U-03：追蹤止損利潤約束（QC M1，P0）— risk_manager.py +24 行 · 12 測試
- [x] U-04：成本感知入場門檻（QC M2，P0）— cost_gate.py 185 行 · 22 測試
- [x] U-05：動態參數寫入 round-trip 記錄（QC M4，P0）— 16 測試
- [x] U-09：ATR 快/慢雙窗口（QC S1，P1）— indicator_engine.py +71 行 · 18 測試

## XP-1~4 — 跨平台兼容性審計（全部完成 · 2026-04-03 · commit e2baf6f）

- [x] XP-1：路徑硬編碼掃描與修復
- [x] XP-2：LocalLLMClient 抽象層預審
- [x] XP-3：服務部署遷移文檔
- [x] XP-4：requirements.txt 全量審計

## Wave 8A — 安全+正確性（全部完成 · 8 項）

- [x] A1：bybit_demo_sync.py 零測試覆蓋 · A2：grafana_data_writer.py 零測試覆蓋
- [x] A3：9 處 assert True 空斷言 · A4：CORS 安全加固 · A5：動態異常洩漏
- [x] A6：symbol 格式驗證 · A7：cost_tracker 方法名 · A8：MessageBus lock 內回調

## Wave 8B Sprint 1 — 核心重複消除（全部完成 · 7 項）

- [x] B1：now_ms() 統一 · B2：compile_state 重複 · B3：on_tick 拆分
- [x] B4：mutator 拆分 · B5：verify_operator_identity · B6：compile_state O(n)
- [x] B7：trading.html auth 統一

## Wave 8B Sprint 2 — 測試+前端統一（全部完成 · 8 項）

- [x] B8：CSS :root 統一 · B9：console.html getToken · B10：phase2 覆蓋率
- [x] B11：WS 斷線測試 · B12：innerHTML 審查 · B13：Evolution→Deploy
- [x] B14：_ollama_stats · B15：ollama_client async

## Wave 8C — 架構改進（9/10 完成 · C3 L5 deferred）

- [x] C1：strategist God-class 拆分 · C2：H3 ModelRouter · C4：Regime-aware
- [x] C5：EvolutionEngine frozen · C6：AnalystAgent 閾值 · C7：Backtest downsample
- [x] C8：並發壓測 · C9：market_data_dispatcher 測試 · C10：requirements.txt
- [ ] C3：L5 meta-learning（deferred → Phase 4 條件性）

## Wave 8D — 文檔清理（4/5 完成 · D2 minor deferred）

- [x] D1：重複 SPEC 刪除 · D3：報告路徑修正 · D4：.DS_Store · D5：decisions 索引
- [ ] D2：CLAUDE.md §3 歷史歸檔（minor，20min）

## 已知待辦（已修復歸檔）

- [x] Intent 被拒時策略內部狀態不回退（2026-04-01）
- [x] Grid 策略同一 tick 重複 intent（2026-04-01）
