# 2026-04-12 Daily Summary

## 完成項目 / Completed

### PNL-FIX-1/2（commits `2a422fa` / `cbb4e45`）
- PNL-FIX-1：`on_tick.rs` 5 條 close 路徑誤用 `event.last_price` 跨 symbol 平倉 → 修正為 per-symbol latest_price
- PNL-FIX-2：`emit_close_fill` 寫 `fee: 0.0` → 加入真實手續費計算
- Phase 5 暫停：所有策略 gross edge 為負（非僅扣費後負）

### Earned-Trust TTL Ladder（commit `5d99875`）
- T0→T5 信任階梯持久化 + Audit Trail 時間戳修復
- Python 2792 → 2852 passed（+53 新測試）

### 全程序鏈審計 12 報告 · 58 發現 · 8 P0
- **P0（8/8）全修**（commit `283ae33`）：IPC HMAC Live 強制、FastTrack 半倉/暫停、price_drop 真實值、execFee 估算、edge_estimates +14 tests、REST fail-closed +7 tests、三管線並發 +1 e2e、ocEsc 單引號
- **P1（18/18）全修**（commit `09f64c1`）：correlated_exposure 實現、GridTrading grid_count、OU theta fallback、Cookie secure、startup tests、hot-reload 並發、Price=0 防護、pre_check_order 移除、MlSwitches 清理、on_tick 拆分、risk_config 借用、Danger Zone modal、CLAUDE_REFERENCE/KNOWN_ISSUES/SCRIPT_INDEX 更新
- **P2 S3（7 項）**（commit `84f00eb`）：RSI 閾值、fee_rate、squeeze 過期、Kelly 負 edge、account_leverage、PriceEventKind enum、O(1) dedup
- **P2 S3.1（10 項）**（commit `421277a`）：孤立模組、Singleton、死碼、加載失敗 UI、刷新頻率、文件歸檔、文檔索引、CHANGELOG、定價日期
- **P2 S3.2（5 項）**（commit `0de58bb`）：文件拆分、FundingArb 註冊、outcome backfiller、DDL 狀態、AI 預算同步

### 其他修復
- GUI metrics DB fallback（commit `7193705`）
- IPC cross-engine routing 修復（commit `35272d3`）
- Paper/Demo session 獨立控制（commit `986d724`）
- Circuit-breaker 防誤觸發（commit `6ae6e1b`）

## 測試基準線 / Test Baseline
- Rust engine lib: 965 + bin 5 + core 366 + e2e 29 + promotion 32 = 1397
- Python: 2852 passed, 0 fail

## 決策 / Decisions
- Phase 5 暫停等策略重做（策略 gross 負 edge，非費用問題）
- 全審計 P0+P1+P2 = 48 項全修，P2 22/22 清零
