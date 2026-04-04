# 2026-04-04 Session Progress — QA 審計 + Rust 策略補齊 + 工程路線決策

## 一、QA 嚴格審計結果：Python V2 真實狀態 62/100

### 策略可用性
| 策略 | 判定 | V2 啟用率 |
|------|------|----------|
| MA Crossover | ✅ PRODUCTION | 3/3 |
| BB Reversion | ✅ PRODUCTION | 2/3（limit order FAKE）|
| Grid Trading | ✅ PRODUCTION | 1/1（唯一有 paper 成交）|
| BB Breakout | ⚠️ CONDITIONAL | 2/3（volume/Donchian 數據斷裂）|
| Funding Arb | ⚠️ CONDITIONAL | 1/1（費用模型正確阻止交易）|

### 6 大謊言/幻覺
1. **BB Reversion limit orders** — FAKE：參數存在但代碼無分支
2. **Kelly Position Sizing** — UNREACHABLE：需 ≥50 筆歷史，僅 15 筆
3. **FundingArb handle_leg_failure()** — DEAD CODE：管線無調用者
4. **BB Breakout volume/Donchian** — UNREACHABLE：SignalRule 不注入字段
5. **Shadow Decision Tracking** — DEAD CODE：主管線未實例化
6. **Dream Engine** — ISOLATED：文檔承認「暫不接入」

### 分項評分
- 策略代碼質量：85 | 管線整合度：80 | V2 特性��用率：55
- 實際交易驗證：40 | 高級特性落地：35

## 二、Rust 引擎完整度：99.9% 獨立

完整管線覆蓋：WS → Kline → 16 指標 → 8 信號 → 4 策略 → Guardian → Governance → Paper
零 Python 依賴。唯一缺口：FundingArb 需外部資金費率數據。

## 三、Operator 決策：放棄修 Python，全力 Rust

### 現在做（4/4-4/10）
| 任務 | 說明 |
|------|------|
| MA Crossover regime filter | Rust 缺，Python V2 有且工作 |
| MA Crossover multi-TF confirm | 同上 |
| BB Breakout volume/Donchian 直讀 IndicatorSnapshot | 避免 Python metadata 斷裂問題 |
| 所有策略 intent rejection rollback | Python V2 有，Rust 全缺 |
| 所有策略 on_fill() sync | 同上 |
| Grid Trading geometric + health check | Python 有，Rust 缺 |
| BB Reversion limit order（真實實現）| Python 是 FAKE，Rust 做真的 |
| FundingArb REST 資金費率 + 基礎入場 | 唯一缺口 |
| StrategyParams trait 定義 | 為 DB/Agent/Optuna 預留接口 |

### 延後到融合方案（依賴 DB）
| 任務 | 延後原因 | 接入時機 |
|------|---------|---------|
| Kelly Position Sizing | 需 trading.fills + Scorer calibrated_prob | Phase 2 (W6-9) |
| FundingArb 雙腿回滾 | 需完整執行狀態機 + trading.orders 持久化 | Phase 1 (W4-5) |
| Agent 自主調參 | 需 update_params() (AGT-1) | Phase 3a (W9-10) |
| Shadow Decision Tracking | Phase 2 規劃項 | Phase 2 |
| Dream Engine 接入 | Phase 2 規劃項 | Phase 2 |

### StrategyParams trait 設計（現在定義，實現留空）
```rust
pub trait StrategyParams: Serialize + DeserializeOwned {
    fn param_ranges() -> Vec<ParamRange>;  // Phase 3b Optuna
    fn from_db(conn: &PgPool) -> Self;     // Phase 0a 後啟用
    fn validate(&self) -> Result<()>;
}
pub struct ParamRange {
    pub name: String,
    pub min: f64, pub max: f64,
    pub step: Option<f64>,
    pub agent_adjustable: bool,
    pub db_persisted: bool,
}
```

### 不應寫死的參數（Agent 未來自主調整）
- BB Reversion: limit_offset_bps, use_limit (market/limit 選���)
- FundingArb: min_rate_threshold, fee_model_bps, expected_periods
- Kelly: kelly_fraction, lookback_window, min_trades
- 所有策���: confidence_threshold, cooldown_ticks

## 四、今日完成的代碼改動

### Commit f6ab650 — Cold-Start Fix + Phase 0a DDL
- Watchdog 45s + grace-period 120s + Rust force_write
- 6 檔 DDL 草稿 V001-V005（43 表 / 8 Schema / 29 hypertable）

### Commit 2a253d9 — tick_duration_us + Replay Mode B
- CanaryRecord 添加 tick_duration_us
- TickPipeline.feed_replay_tick() 100% 複用 on_tick()
- replay_runner.py 真實 subprocess 調用

### Commit 69b03aa — ADX Bug + Comparator Fixes
- Python ADX DX→ADX Wilder 平滑修復
- Comparator key 映射（31+35 keys）
- Bar-close filter + paper_state skip
- replay_runner StrategyOrchestrator 接線

### Commit 5ed077b — Comprehensive Indicator+Strategy Alignment
- Rust: Hurst 安全修復 + KAMA SMA seed + IndicatorSnapshot 擴展(+3)
- Rust: BB Breakout ATR trailing stop + regime exit
- Python: KAMA per-step SC + Stochastic Slow %K
- Comparator: 容差放寬 + MISSING severity

## 五、Go/No-Go 清單 (4/10)
| 條件 | 狀態 |
|------|------|
| Watchdog 3-STRIKE 驗證 | ✅ PASS |
| 記憶體 < 100MB | ✅ PASS (10.9MB) |
| IPC 零丟失 | ✅ PASS |
| tick P50 < 50μs | ✅ PASS (30.1μs + live 計時就位) |
| 回滾演練 < 10min | ✅ PASS (0.091s) |
| 歷史回放 0 CRITICAL | 🔄 Replay 基礎設施完備，需重跑驗證 |
| 即時 7 天穩態 0 崩潰 | 🔄 引擎持續運行中 |
