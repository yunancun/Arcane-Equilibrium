# DUAL-TRACK-EXIT-1 — 物理最優 + ML 持續優化雙軌退場設計

**日期**：2026-04-18
**作者**：主會話 PM+Conductor（對話式設計）
**狀態**：設計定稿，等 W23 可行性驗證 sprint 後進入實作
**關聯 TODO**：取代 P1-9 原案；與 P1-7 解阻塞 A+B+C 合併；與 P1-10 並行

---

## 一、背景與命題演進

### 起點：P1-9 原案（2026-04-18 早）
MICRO-PROFIT-FIX-1 語意重構 — operator 澄清設計意圖應為「有微利就套」，建議降 `min_profit_to_close_pct` 或改 `min_net_profit_bps`。

### 第一輪 QC 反駁（對話 Turn 1）
指出三個問題：
1. 現規則 494 觸發 99.39% 勝率是 **sampling bias 不是 edge** — 規則定義下只在 pnl_pct ≥ 0.30% 時觸發，自選正收益。
2. P1-10 audit 的 fee/R:R 不對稱才是 Phase 5 edge 負的主因（grid fee=74% of gross loss、ma_crossover 2.54× 不對稱）；降門檻會雙重惡化。
3. operator 原始「牛市 trailing / 熊市微利」的比喻在工程上行不通：市場趨勢難定義、有滯後、per-symbol 與 BTC 經常解耦。**正確軸是「倉位動能流失」**（per-position signal），不是全域趨勢。

初步建議用 `peak_pnl_pct` 衰減做 giveback gate。

### 第二輪 Operator push back
operator 反駁：< 0.30% 微利大概率被 fee 吃掉，P1-9「降門檻」方向**本身應否決**。真正命題是 **「放大單筆收益 + 用風控最大化套現」**。並追問：peak_pnl_pct 是最優解還是「省事的相對解」？

### 第二輪 QC 重審（對話 Turn 2）
承認 `peak_pnl_pct` 只是「現有變量 + 一階近似」，**不是最優**。列出五個結構性盲點：
1. 無時間維度（spike wick vs 真實峰值衰減混淆）
2. 無波動率歸一化（高/低 vol symbol 鬆緊不一）
3. 無速度/方向（「靜止震盪」與「明確下行」區分不出）
4. 無開倉年齡（noise-to-signal 早晚期差幾個量級）
5. 隱含線性對稱（獲利分佈右偏，非線性 giveback 未處理）

真正接近最優的信號集是 **7 個維度組合**（下詳）。

### 第三輪 Operator 定向
**期望：物理層最優 + ML 持續優化並行**。P1-7 是後續肯定要完成的，只是目前不知被哪個章節阻塞。

### 第三輪 QC 定位 P1-7 阻塞（對話 Turn 3）
**驚人結論：P1-7 沒有結構性阻塞，是「沒人接線」**。

```
A. Rust 接 trading.intents 持久化      (~0.5d, 純接線)
B. james_stein_estimator scheduler    (~0.5d, cron job)
C. run_training_pipeline 首跑 1 ONNX (~1-2d, 跑通 + 排程)
D. G-7 Teacher directive loop        (~1-2w, 需 R-02)
```

A/B/C 加起來 **< 1 週工程**。D 與退場優化**正交獨立**。
→ **Track L（ML 退場 policy）只依賴 A+B+C，1 週內解阻塞**。

---

## 二、最終設計：Track P + Track L 雙軌 + Combine Layer

### 架構圖

```
                    [Position Tick Data]
                           │
              ┌────────────┴────────────┐
              ▼                         ▼
       Track P (Physical)        Track L (ML)
       7 維度啟發式規則           ONNX inference
       零依賴可運行               per-strategy policy
              │                         │
              └────────────┬────────────┘
                           ▼
                    [Combine Layer]
                    決策融合 + 安全網
                           │
                           ▼
                  ExitSignal { Hold | Lock(source) }
                           │
                           ▼
                audit: exit_source column
                (Physical | ML | Hybrid | Disabled)
```

### 核心原則
1. **Track L 修飾 Track P，不替代** — ML 失效時系統不退化
2. **兩軌共用同一特徵向量** — Track P 用於規則、Track L 用於推理，Track P 永遠是 Track L 的可解釋下界
3. **Combine Layer 雙閾值不對稱** — ML override 比 ML veto 需要更高信心
4. **每決策標源** — `exit_source` 寫入 `trading.fills`，可對比分組 edge

---

## 三、Track P：物理層 7 維度規則

### 特徵集

| # | 維度 | 用途 | 現狀 |
|---|---|---|---|
| 1 | `est_net_bps = pnl_pct - 2 × fee_rate × 100` | 淨利底線（fee 已 clear） | 可算 |
| 2 | `peak_pnl_pct` | 峰值高度 | 已 derive from `p.best_price` |
| 3 | `atr_pct` | 波動率（normalize 基準） | 已 plumbed 到 `evaluate_position` |
| 4 | `giveback_atr_norm = (peak - current) / atr_pct` | ATR-歸一化峰值衰減 | 組合已存變量 |
| 5 | `time_since_peak_ms` | 峰值年齡（排除 spike wick） | **需加欄位** |
| 6 | `price_roc_short` | 短窗價格速度 + 方向 | **需 PriceTracker 加 method** |
| 7 | `entry_age_secs` | 開倉年齡（早期寬容） | `entry_ts_ms` 已存 |

### 候選規則（Tier A 物理最優啟發式）

```rust
// 粗略草稿，具體閾值由 W23 counterfactual replay 校準
fn physical_micro_profit_lock(f: &ExitFeatures, cfg: &ExitConfig) -> PhysicalDecision {
    // Gate 1 — 淨利底線（必要，非充分）
    if f.est_net_bps <= cfg.min_net_floor_bps {
        return PhysicalDecision::Hold;
    }

    // Gate 2 — 開倉太早寬容（信號發展期）
    if f.entry_age_secs < cfg.min_hold_secs {
        return PhysicalDecision::Hold;
    }

    // Gate 3 — 峰值高度感知（非線性閾值）
    let peak_atr_norm = f.peak_pnl_pct / f.atr_pct;
    if peak_atr_norm < cfg.min_peak_atr_norm {
        return PhysicalDecision::Hold;
    }

    // Gate 4 — 核心：giveback (ATR-歸一化) 或 (峰值陳舊 + 速度向下)
    let giveback_threshold = non_linear_giveback_fn(peak_atr_norm, cfg);
    let giveback_triggered = f.giveback_atr_norm >= giveback_threshold;

    let stale_and_decaying =
        f.time_since_peak_ms >= cfg.stale_peak_ms && f.price_roc_short < 0.0;

    if giveback_triggered || stale_and_decaying {
        PhysicalDecision::Lock(format!(
            "PHYS-LOCK: net={:.1}bps peak={:.2}% giveback_atr={:.2} age_s={} roc={:.4}",
            f.est_net_bps, f.peak_pnl_pct, f.giveback_atr_norm,
            f.entry_age_secs, f.price_roc_short
        ))
    } else {
        PhysicalDecision::Hold
    }
}
```

`non_linear_giveback_fn(peak_atr_norm)` 高峰值 → 小相對 giveback 就鎖；低峰值 → 大相對 giveback 才鎖。具體形式（線性 / sigmoid / 階梯）由 W23 replay 決定。

### 與既有 trailing stop 的關係
現 trailing：`activation=0.8% / distance=3.5% / min_locked ≈ 0.9%`。
Tier A 覆蓋的區段是 **[min_net_floor, trailing_activation]**（即 trailing 還沒啟動前的微利段），與 trailing 形成**連續譜**，不重疊。W23 需驗證兩者在邊界不打架。

---

## 四、Track L：ML 層 (per-strategy exit policy)

### 任務定義
給定當前 feature vector，預測 `P[future_max_pnl_pct > current_pnl_pct | features]`
- 高 → 繼續持（hold more value）
- 低 → 立即鎖（動能耗盡）

### Model
- **初版**：LightGBM binary classifier（per strategy）
- **Input**：Track P 的 7 維度 + `strategy_id` + `regime` + `symbol_embedding`（若 P1-7 Autoencoder 就緒）
- **Label**：從歷史 positions 反算「exit 時刻的 pnl_pct 是否為該 position 峰值的 ≥90%」
- **Training data**：`learning.decision_features` + `trading.fills` JOIN（per position trajectory）
- **Validation**：CPCV（Combinatorial Purged Cross-Validation，時序安全）

### 部署通道
- Training：`program_code/ml_training/run_training_pipeline.py` + cron scheduler
- Inference：Rust `ort 2.0` onnx loader（EDGE-P3-1 Phase B #3 已就緒）
- Artifact：`models/<engine>/<strategy>_exit_policy_vYYYYMMDD.onnx` + symlink latest
- Hot reload：現有 `ReloadEdgePredictor` IPC 可複用或新增 `ReloadExitPolicy` IPC

### 樣本平衡性預警
- grid_trading ~800k ✅
- ma_crossover ~100k（估計）
- bb_reversion ~5k（24h 66 筆 × 歷史 = 少）
- bb_breakout **0 筆** → 不訓練、永遠 Track P-only

---

## 五、Combine Layer：決策融合

### 偽代碼

```rust
enum ExitSource {
    Physical,
    ML { model_id: String, score: f32 },
    Hybrid { physical_reason: String, ml_score: f32 },
    Disabled { reason: String },
}

fn combine_exit_decision(
    physical: PhysicalDecision,
    ml_opt: Option<MLInference>,
    cfg: &CombineConfig,
) -> (ExitSignal, ExitSource) {
    // 安全網 1：ML model 過期 / 推理失敗 → 完全退回 Physical
    let ml = match ml_opt {
        Some(m) if m.age_secs < cfg.max_model_age_secs && m.confidence.is_finite() => Some(m),
        _ => None,
    };

    match (physical, ml) {
        // Physical 要鎖 + ML 高信心確認 → Hybrid（最高信心）
        (PhysicalDecision::Lock(r), Some(m)) if m.score >= cfg.ml_confirm_threshold =>
            (ExitSignal::Lock, ExitSource::Hybrid { physical_reason: r, ml_score: m.score }),

        // Physical 要 Hold + ML 高信心 override → ML 主動鎖
        (PhysicalDecision::Hold, Some(m)) if m.score >= cfg.ml_override_high =>
            (ExitSignal::Lock, ExitSource::ML { model_id: m.id, score: m.score }),

        // Physical 要鎖 + ML 強烈反對 → ML veto，繼續持
        (PhysicalDecision::Lock(_r), Some(m)) if m.score < cfg.ml_veto_low =>
            (ExitSignal::Hold, ExitSource::Disabled { reason: format!("ML veto score={:.2}", m.score) }),

        // Physical 要鎖 + ML 中性 → Physical 主導
        (PhysicalDecision::Lock(r), _) =>
            (ExitSignal::Lock, ExitSource::Physical),

        // 其他情況
        _ => (ExitSignal::Hold, ExitSource::Physical),
    }
}
```

### 閾值初始值（保守）
- `ml_confirm_threshold = 0.70`（ML 同意鎖的信心）
- `ml_override_high = 0.95`（ML 主動鎖的信心，極高）
- `ml_veto_low = 0.10`（ML 否決物理鎖的信心，極低）
- `max_model_age_secs = 7 × 86400`（model 7 天內有效）

### 灰度路徑
W23 全 Physical → W24 shadow ML → W25 ML override @0.95 → W26 @0.85 → W27+ @0.75。每階段觀察 1-2 週 per-strategy net edge 差。

---

## 六、W23 可行性驗證 sprint（Day 1-3）

**先解決以下四個不確定，否則所有後續設計都是猜測。**

### 不確定 1：`james_stein_estimator.py` 真的能跑通嗎？
- 行動：E1 實測 `python -m program_code.ml_training.james_stein_estimator` + 寫入 `settings/edge_estimates.json`
- 可能問題：schema migration 缺、配置缺、依賴缺、DB 權限缺
- 成功標準：產出 non-empty JSON 且 `ml_training/tests/test_james_stein.py` 綠
- 失敗回退：先修 Python 端（小工程），或降級為手工 backfill + TODO 記債

### 不確定 2：`decision_features` schema 與 training ETL 對齊 Track P 7 維度嗎？
- 行動：E1 讀 `program_code/ml_training/parquet_etl.py` + `decision_features` schema，對照 Track P 7 維度
- 特別：`time_since_peak_ms` 和 `price_roc_short` 是否在歷史資料中可重建？若不行，需先加 feature logging（backward-incompatible，慎重）
- 成功標準：7 維度中至少 5 個可從現有 schema 直接 derive；剩下 2 個有明確 backfill/前向補齊計劃
- 失敗回退：Track P 暫時不用缺失維度、Track L 訓練數據只用可得特徵

### 不確定 3：per-strategy 樣本平衡度真實分佈？
- 行動：`SELECT strategy, COUNT(*) FROM learning.decision_features WHERE engine_mode IN ('demo','live_demo') GROUP BY strategy`
- 成功標準：至少 2 個策略 ≥10k rows 可支持 ML 訓練；其餘走 Track P-only
- 失敗回退：若只有 grid_trading 樣本足，先做 grid 單策略 PoC，其他等樣本累積

### 不確定 4：Counterfactual replay 可行嗎？
- 行動：查 tick-level price history 保留時長 + 粒度。代碼路徑：`price_tracker.rs` snapshots、`/tmp/openclaw/` tick dumps、`trading.risk_verdicts` 時序資料
- 成功標準：至少能重放 7d demo 倉位 tick-level PnL 軌跡
- 失敗回退：改用「事後歸因」audit — 對已關倉 positions 分析 peak-to-exit 軌跡形態，不做逐 tick replay

### Sprint 產出
- `docs/worklogs/2026-04-18-N--dual_track_exit_feasibility.md`（N=1/2/3 Day 產出）
- 若 4 項全綠 → W23 Day 4+ 進入 Phase 1 實作
- 若任一紅 → 調整設計或再拖一週解紅

---

## 七、實施排程（Phases）

### Phase 1（W23 Day 4-7）
**並行 1 — Track P 實作**：
- E1: 加 `peak_reached_ts_ms` 到 `PaperPosition`（+ migration）
- E1: `price_tracker` 加 `compute_roc(symbol, lookback_ms)`
- E1: 7 維度規則 in `risk_checks.rs` + ConfigStore 綁定
- E2 + E4: counterfactual replay audit（demo 7d）+ 18 單測
- 估工程量：~400 LOC + 18 單測 + 1 audit script + 1 worklog

**並行 2 — P1-7 解阻塞 A+B+C**：
- A: 定位 DEDUP-PY-RUST Tier A stub 點，Rust 端補 `trading.intents` 寫入
- B: JS estimator scheduler — 每小時 cron + IPC hot-trigger
- C: `run_training_pipeline.py` 首跑 grid_trading ONNX + 排程

→ **W23 末產出**：Track P 灰度部署 + 第一個 ONNX artifact

### Phase 2（W24）— Track L shadow mode
- Combine Layer 實作，`ml_override_high = 2.0`（不可達，Shadow only）
- Track L 推理但 log only；寫 `learning.decision_shadow_fills`
- 每日對比「Track P 決策 vs Track L 推理」一致性 → 校準閾值
- **並行**：P1-10 grid 過度交易 + ma_crossover R:R 不對稱修復（比 ML 重要）

### Phase 3（W25-W26）— Track L 灰度
- `ml_override_high` 從 0.95 → 0.85（每階段 1-2 週）
- 每週對比 P-only vs Hybrid per-strategy net edge
- 證明 Hybrid 顯著正才下調

### Phase 4（W27+）— 持續優化常態
- 每週 retraining cron（用最新 7-14d 數據）
- model registry 自動版本化 + canary deployment
- 每月 CPCV 驗證 + drift 檢測 + auto-rollback
- 整合 G-7 Teacher directive（Phase 2B）

---

## 八、QA 守衛（避免 ML 變賭博）

1. **每策略樣本下限** — < 1000 rows 不訓練、永遠 Track P-only
2. **CPCV 時序驗證** — 不能 random split
3. **Hold-out control group** — 永遠保留 5-10% 倉位完全跑 Track P-only，作 ML 偏差檢測對照
4. **Calibration 監控** — 每日 predicted vs realized Brier score，超閾值自動降級
5. **Feature drift 警報** — 7 個 feature 分佈每日對 baseline，shift > 2σ 報警
6. **Rollback 機制** — IPC 一條命令把 `ml_override_high = 2.0` → 等同卸載 Track L
7. **ML feedback loop 隔離** — hold-out positions 永不受 ML 影響，作 control group 防 feedback bias

---

## 九、與其他 TODO 的關係

| TODO | 關係 | 行動 |
|---|---|---|
| **P1-9 原案** | 完全取代 | TODO 中保留 1 行 stub → 指向 DUAL-TRACK-EXIT-1 |
| **P1-7 LEARNING-PIPELINE-DORMANT-1** | A+B+C 併入 Phase 1 | P1-7 保留 Teacher / LinUCB / Bayesian 等大項；A+B+C 在本章節追蹤 |
| **P1-4 首個 ONNX export** | 就是 Phase 1 Track L Prereq C | P1-4 標為 subsumed，指向 DUAL-TRACK-EXIT-1 |
| **P1-10 STRATEGY-ASYMMETRY-1** | 並行，比 ML 重要 | P1-10 保留，W24 同步；P1-10 原「聯合 P1-9 重構」改指 DUAL-TRACK-EXIT-1 |
| **P0-3 Phase 5 edge 2w 重評** | 推遲到 P1-10 + Track P 都上線後 | P0-3 描述更新，參考本設計 |
| **G-7 Teacher** | Track L Phase 4 整合 | G-7 正常排 W23，不阻 Track P/L 前三 Phase |
| **G-6 ML edge 噪音** | P1-7 B 解阻塞後自然解 | 無額外動作 |

---

## 十、風險與退路

1. **Phase 1 Track P replay 證明 net edge < 0** → 不上線，改走 Tier B（per-strategy native TP）
2. **Phase 2 shadow ML 與 Physical 一致性 < 60%** → 特徵集不夠，補特徵或降模型複雜度
3. **Phase 3 灰度後 Hybrid edge < P-only edge** → rollback 閾值到 2.0，Track L 回 shadow
4. **Per-strategy ML 過擬合 grid_trading** → 每策略獨立訓練 + 小樣本策略 Track P-only
5. **Counterfactual replay 失敗** → W23 可行性 sprint 轉向「事後歸因 audit」，設計風險上升

---

## 十一、一句話總結

> Track P 是物理最優的可解釋下界，Track L 是同一特徵集的監督學習上界，Combine Layer 保證系統永遠 ≥ Track P。P1-7 A+B+C 併入 Phase 1，一週內解阻塞。W23 Day 1-3 可行性驗證 sprint 先解掉 4 個不確定，再進實質工作。

---

## 附錄 A：對話記錄索引

- Turn 1（QC 初審 P1-9）：指出 sampling bias、P1-10 才是主因、全域趨勢軸錯、peak_pnl_pct 作初步建議
- Turn 2（QC 重審 peak_pnl_pct）：承認非最優、列 5 盲點、給出 7 維度 Tier A + ML Tier S 分層
- Turn 3（設計定稿）：P1-7 阻塞鏈診斷 + Track P/L 雙軌架構 + W23 可行性 sprint

## 附錄 B：文件索引

- 現 MICRO-PROFIT-FIX-1 邏輯：`rust/openclaw_engine/src/risk_checks.rs:140-258`（Priority 6）
- ATR 可用性：`rust/openclaw_engine/src/tick_pipeline/on_tick.rs:1352`（`compute_atr_pct`）
- peak_price 存在處：`rust/openclaw_engine/src/paper_state.rs:19`（`PaperPosition.best_price`）
- ONNX loader：EDGE-P3-1 Phase B #3（ort 2.0，2026-04-16 部署）
- learning schema 21 表：`learning.decision_features` 1.65M rows、其餘多數空
- 訓練 pipeline：`program_code/ml_training/{james_stein_estimator,run_training_pipeline,onnx_exporter,scorer_trainer}.py`
- P1-7 阻塞 RCA：`memory/project_p06_rca_and_fix_plan.md` + TODO §P1-7
