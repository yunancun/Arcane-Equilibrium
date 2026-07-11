# Portfolio Construction — 治理映射與 Live 歸因細節（governance extract）

> 本檔為 `portfolio-construction-protocol` SKILL.md 的外移節（原 §5 / §6），需要時讀。
> Authority 使用 `.codex/agent_registry_v1.json` typed matrix；只在同類內比較，跨類不一致標 DRIFT/CONFLICT，runtime 不得合法化 policy denial。

## 5. Drawdown Control（對齊 SM-04 + RiskConfig）

**SM-04 是治理 SSOT**（`srv/docs/decisions/SM-04_..._V1.md`）：6 named states + event-driven + observation window；具體 % threshold 讀 RiskConfig `[cascade]`。

### 5.1 SM-04 狀態與 RiskConfig 觸發 mapping

| SM-04 state | 行為約束（見 SM-04 §9） | RiskConfig threshold key |
|---|---|---|
| **NORMAL** | 正常裁決 | drawdown < `drawdown_cautious_pct` |
| **CAUTIOUS** | 提高入場門檻 + 下調倉位 + 提高 manual review | drawdown ≥ `drawdown_cautious_pct` |
| **REDUCED** | 大比例 downsize + 局部凍結 + 限制訂單類型 | drawdown ≥ `drawdown_reduced_pct` |
| **DEFENSIVE** | reduce-only + protective only + 禁新風險 | drawdown ≥ `drawdown_defensive_pct` |
| **CIRCUIT_BREAKER** | 停止非保護性推進 + 凍結 live 扩张 | drawdown ≥ `drawdown_circuit_pct` |
| **MANUAL_REVIEW** | 人工審批指定範圍 | operator emergency / multi-layer conflict |

各 key 的具體值（base / demo / live 各環境不同）以 `settings/risk_control_rules/risk_config_<env>.toml` `[cascade]` 為 SSOT，本檔不寫死數字；每次 audit 必 grep TOML 重驗。

### 5.2 跨級恢復禁止（SM-04 §7.1）

明禁：
- CIRCUIT_BREAKER → NORMAL
- DEFENSIVE → NORMAL
- REDUCED → NORMAL

恢復必須**渐进**：CIRCUIT_BREAKER → DEFENSIVE → REDUCED → CAUTIOUS → NORMAL，且每步須觀察窗口完成。

### 5.3 觀察窗口要求（SM-04 §11）

進入更宽松前必有 observation_window：
- 禁進一步放寬超過當前批准級別
- 提高審計密度
- 提高 incident / near-miss 檢查頻率

結束條件（SM-04 §11.3）：
- 無新增同類異常
- 觸發恢復的根因已不再出現
- 審計鏈、對賬鏈、健康鏈穩定
- Operator 未提出回退

### 5.4 OpenClaw 對應實現

- CognitiveModulator.confidence_floor 動態調整（CLAUDE.md memory `feedback_agent_autonomy`）
- P0/P1 硬邊界（DOC-01 §5.11；P2 範圍 Agent 自主）
- Performance Attribution 拆解（見 §6 Live 階段績效歸因）

## 6. Live 階段績效歸因（a3 整合）

### 6.1 Performance Attribution 拆解
```
Total PnL = Σ_strategy PnL_strat + interaction
PnL_strat = Σ_symbol PnL_sym
PnL_sym = (entry_alpha + exit_alpha + holding_alpha) − (fee + slippage + funding)
```

### 6.2 Realized vs Expected Edge Gap
每 24h 對每 (strategy, symbol) 比對：
- Backtest expected edge per trade
- Live realized edge per trade
- Gap > 50% 的 cell → 警報（**建議起點，非硬規範**；具體 gap threshold 依 strategy 半衰期 + sample size 動態調整）

OpenClaw 教訓：edge_estimator JSON 結構 + engine_mode 隔離（live vs live_demo 必含）。

### 6.3 Slippage Monitoring
- Expected fill price（mid）vs actual fill price
- Per (symbol, hour, order_type) 分群統計
- 異常時段 / symbol 列為高 slippage cell

### 6.4 Position-level P&L Decomposition
- Entry alpha（從 entry 到第一個 favourable move）
- Exit alpha（exit 是 take profit / stop loss / phys lock）
- Holding alpha（中間部分）
- 對應 OpenClaw `learning.exit_features` table

### 6.5 Rolling Sharpe / Drawdown Duration 動態追蹤
- 30d rolling Sharpe 圖
- Underwater curve（drawdown 持續多久）
- 若 60d Sharpe < 0 → 全策略 review
