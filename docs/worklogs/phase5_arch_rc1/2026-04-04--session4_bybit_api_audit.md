# 2026-04-04 Session 4 — Bybit V5 API 基礎設施審計 + 字典手冊

## Summary

BB（Bybit 技術顧問）+ E5（優化工程師）+ PA（項目架構師）三角色聯合審計 Rust Bybit API 層，修復所有發現問題，撰寫完整 API 字典手冊。

---

## 完成項

### Phase 1: 全面盤點 + 覆蓋率分析
- 對照 Bybit V5 官方文檔 ~243 REST + ~20 WS topics
- 盤點 Rust 層 14 模組 57 端點 + Python Demo connector
- 產出覆蓋率矩陣：交易核心 ~85%，非核心（Loan/Broker/Earn）設計上不覆蓋

### Phase 2: Round 1 修復（commit b2584ce）
**路徑修復（8 處）：**
- `position_manager.rs`: `/v5/position/set-trading-stop` → `/v5/position/trading-stop`
- `account_manager.rs`: `/v5/account/quick-repayment` → `/v5/account/repay`（方法改名）
- `platform_client.rs`: `query-dcp-info` → `dcp-info`, `set-collateral-switch` → `set-collateral`
- `spot_margin_client.rs`: 3 端點遷移到 `/v5/spot-margin-uta/*`

**移除廢棄端點（3 個，0 callers）：**
- `switch_isolated`, `set_tpsl_mode`, `set_risk_limit` → 新增 `confirm_mmr`

**新增端點（P0）：**
- `get_adl_alert()`: stub → 實際調用 `/v5/market/adl-alert`
- `get_insurance()`: `/v5/market/insurance` + InsuranceRecord struct
- `get_coin_info()`: `/v5/asset/coin-info` + CoinInfoRecord + ChainInfo structs

**新增 WS topic 解析（5 個）：**
- orderbook, ticker, liquidation, price-limit, adl-notice
- 支持 array + object 兩種 Bybit 數據格式

**新增 Private WS（2 個）：**
- fast-execution（~50ms 低延遲成交）
- dcp（斷連取消保護通知）

**新增基礎設施：**
- `RateLimitGroup` enum（6 組 per-endpoint 限流追蹤）
- `BybitRetCode` enum（13 個常用錯誤碼 + is_retryable/is_noop）
- `multi_interval_ws.rs`: 3 個新 topic builder + extended_subscription_list

### Phase 3: Round 2 修復（commit 090fea1）
BB+E5 第二輪交叉驗證發現 3 個問題，全部修復：
- `confirm-pending-mmr` → `confirm-mmr`（路徑修正）
- spot cross-margin 舊路徑遷移到 UTA
- 段落註釋同步更新

### Phase 4: Round 3 — 三角色邏輯正確性審計（commit 090fea1）
BB+E5+PA 並行派 3 路 agent 審計所有修改的邏輯正確性：

**發現並修復：**
| 嚴重度 | 問題 | 修復 |
|--------|------|------|
| BLOCKING | WS subscribe 不分批，超過 10 topic 被靜默拒絕 | `chunks(SUBSCRIBE_BATCH_SIZE)` 分批發送 |
| HIGH | DCP 映射為 Disconnected 語義錯誤 | 新增 `DcpTriggered` variant + execution_listener 處理 |
| HIGH | `RateLimitGroup` 缺 `#[repr(usize)]` | 已加 |
| MED | Liquidation 讀 `qty` 但 Bybit 發送 `size` | 已改為 `size` |
| MED | fast-execution + execution 同時訂閱造成重複 fill | 只訂閱 fast-execution |
| MED | adl-notice/price-limit 不宜默認訂閱 | 移到 `extended_subscription_list()` |

### Phase 5: API 字典手冊（commit f4c39ec）
撰寫 `docs/references/2026-04-04--bybit_api_reference.md`（1032 行）：
- 64 REST 端點完整條目（服務描述 + 調用 + Input + Output + 關聯程式）
- 8 默認 + 2 擴展 Public WS topics
- 5 Private WS topics + PrivateWsEvent 結構
- 8 IPC methods
- 速查表：Rate Limit 6 組 + Error Code 13 個 + 已知陷阱 10 條
- grep 交叉驗證：所有端點計數與代碼完全一致

### Phase 6: 工作流程更新（commit 51c7a89）
- CLAUDE.md §8: 新增「Bybit API 相關開發強制規則」
- CLAUDE.md §10: 關鍵文件列表新增字典手冊 + 審計報告
- README.md: 狀態區新增 Bybit API 審計行
- TODO.md: 強制工作流程新增 Bybit API 必查段 + 測試基準線更新

---

## Commits

| Commit | 描述 |
|--------|------|
| `b2584ce` | fix: Bybit V5 API audit — path updates, WS full coverage, rate limit groups |
| `090fea1` | fix: BB+E5+PA audit round 3 — 1 BLOCKING + 2 HIGH + 3 MED fixes |
| `f4c39ec` | docs: Bybit V5 API reference — dictionary-style engineering manual |
| `51c7a89` | docs: register Bybit API reference in CLAUDE.md/README.md/TODO.md |

---

## 測試結果

```
Rust:   763 passed, 0 failed (+73 vs session start)
Python: 2146 passed, 1 flaky (pre-existing)
Total:  4640 tests
```

---

## 文件變更匯總

| 文件 | 變更 |
|------|------|
| `position_manager.rs` | 修路徑, 移除 3 廢棄端點, 新增 confirm_mmr |
| `account_manager.rs` | 修路徑, 改名 repay |
| `platform_client.rs` | 修路徑, 新增 coin-info + CoinInfoRecord + ChainInfo |
| `spot_margin_client.rs` | 5 路徑遷移 UTA |
| `market_data_client.rs` | ADL alert 實作, 新增 insurance + InsuranceRecord |
| `ws_client.rs` | 5 新 topic parser, subscribe 分批, object/array 兼容 |
| `multi_interval_ws.rs` | 3 topic builder, extended_subscription_list, TopicType 擴展 |
| `bybit_private_ws.rs` | fast-execution + dcp, DcpTriggered variant |
| `bybit_rest_client.rs` | RateLimitGroup + BybitRetCode + per-group tracking |
| `execution_listener.rs` | DcpTriggered 事件處理 |
| `docs/references/2026-04-04--bybit_api_reference.md` | 1032 行字典手冊 |
| `docs/audits/2026-04-04--bybit_api_infra_audit.md` | 審計報告 |
| `CLAUDE.md` | §8 Bybit 強制規則 + §10 關鍵文件 |
| `README.md` | Bybit API 狀態行 |
| `TODO.md` | Bybit 必查段 + 基準線 763 Rust |

---

## 下一步

- Phase 1（5/01 開始）：市場數據 pipeline + FeatureCollector + PSI 漂移
- 所有 Bybit 相關開發必先查閱字典手冊
