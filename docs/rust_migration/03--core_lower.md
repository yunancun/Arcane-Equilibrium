# Phase R-03：core 下半——SM + 執行 + 回測（Week 5-6）

**週期**：Rust 主開發 Week 5-6
**工時**：~2 週
**前置**：`02--core_upper.md` Go
**下一階段**：`04--engine_full_path.md`

---

## 上下文導航

```
源文件：V3-FINAL §1.3（GovernanceCore 切分）+ §1.4（並發模型）
前置完成：core 上半全部通過 · Golden Dataset 穩態 PASS
本階段目標：4 SM 級聯 + 完整執行計算 + 回測引擎
```

**PA 提醒**：
- 級聯必須 all-or-nothing（clone+swap 事務）[V3-PA-3]
- SM 是 tick actor 的 sole-owned 狀態，不獨立持鎖 [V3-PA-1]

---

## 具體任務

### [ ] R03-1：core/sm_auth.rs — Authorization SM（724 行源碼）
### [ ] R03-2：core/sm_lease.rs — Decision Lease SM（740 行）
### [ ] R03-3：core/sm_risk_gov.rs — Risk Governor SM（858 行）
### [ ] R03-4：core/sm_oms.rs — OMS 11 態（693 行）
- 每個 SM：enum 狀態 + 轉換表 + proptest 窮舉測試
- transition_history 用 Vec\<TransitionRecord\> 替代 Python dict

### [ ] R03-5：GovernanceCore 級聯邏輯 [V3-PA-3]
- `execute_cascade()` all-or-nothing：clone SM states → 執行 → commit/rollback
- risk→auth→lease→mode 完整鏈
- CRITICAL alert on failure

### [ ] R03-6：core/guardian.rs — 4 項確定性檢查（580 行）
### [ ] R03-7：core/execution.rs — slippage + fill_price + fee（180 行邏輯）
### [ ] R03-8：core/order_match.rs — ENGINE.tick() 訂單匹配（300 行邏輯）
### [ ] R03-9：core/state_compute.rs — mutate() 計算驗證（350 行邏輯）
### [ ] R03-10：core/portfolio.rs — 相關性 + delta + 總暴露（557 行）
### [ ] R03-11：core/stop_manager.rs — hard/trailing/time stop（319 行）
### [ ] R03-12：core/message_bus.rs — Agent 消息路由（1,104 行部分）
### [ ] R03-13：core/attribution.rs — PnL 歸因（958 行）
### [ ] R03-14：core/backtest.rs — 完整回測引擎（1,352 行）

### [ ] R03-15：Golden Dataset 極端組對比
- 極端組 500 根（2024-08-05 日元事件 + 2025-03-12 BTC 閃崩）[V3-QC-4]
- + 邊界組 50 根（人工構造）

---

## Go/No-Go 門控

- [ ] 4 SM proptest 轉換窮舉：所有合法路徑 PASS + 所有非法轉換被拒
- [ ] 級聯 all-or-nothing：中間步驟失敗時 SM 狀態不變（測試覆蓋）
- [ ] Golden Dataset 極端組：FAIL=0
- [ ] `cargo test -p openclaw_core` 全部通過（累計 ~400 測試）

---

## 與現有工作交叉

| 交叉點 | 處理 |
|--------|------|
| Phase 2 策略 V2 | 策略接口已在 L1 凍結，此階段不受影響 |
| Phase 3 放權框架 | GovernanceHub 授權接口已在 L2 凍結 |

---

## 進度追蹤

| 任務 | 狀態 | 完成日期 | commit |
|------|------|---------|--------|
| R03-1~4 四個 SM | [ ] | | |
| R03-5 級聯邏輯 | [ ] | | |
| R03-6~14 其餘 core | [ ] | | |
| R03-15 極端組對比 | [ ] | | |

---

## 問題與變更

（空）
