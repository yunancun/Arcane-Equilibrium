# OpenClaw / Bybit 亏损根因 5 维拆解（供外部第三方交叉核验）

**Audit 时间**：2026-04-28
**Repo HEAD**：`85a4e2d`
**方法**：5 并行 sub-agent 独立审计（QC×2 / MIT / E5 / CC）逐项 file:line 比对
**适用对象**：外部第三方独立核验 / 内部 PA Wave 规划输入

---

## 0. 执行判决（一句话）

**当前亏损**主要由 **(A) 策略层 alpha 缺失（Edge 维度）** + **(B) Funding settlement 完全不入 PnL（Cost 维度 BROKEN）** 两条独立链路构成；Risk 维度合规无重大漏洞，ML pipeline 自身有 BLOCKER 但还没真正运行所以不主动加重亏损。

| 维度 | 综合评级 | 对当前亏损贡献 | 关键 BLOCKER |
|---|---|---|---|
| **1. 成本 Cost** | C2 BROKEN / 其余 OK-Suspect | **中-高** | 🛑 funding settlement 不入帐 |
| **2. 边界 Edge** | 18/50（5 项 0 alpha） | **高** | 🛑 5/5 策略无结构性 alpha + Donchian look-ahead 未修 |
| **3. 模型 Model/ML** | M2 BLOCKER / M3 A- | **中** | 🛑 train-serve skew (engine_mode filter) |
| **4. 执行 Execution** | X2 中-高 / 其余 OK | **中** | ⚠ partial fill 无 chase + hot path 无 benchmark |
| **5. 风控 Risk** | A-（22/25, 9/9 invariant） | **低** | 仅 P2/P3 建议，无 P0 |

---

## 1. 成本维度（Cost）

### 关键证据

| 子项 | 状态 | file:line |
|---|---|---|
| **C1 Fee 模型** | Suspect | `intent_processor/mod.rs:213-220`（DEFAULT_TAKER 5.5bps）/ `account_manager.rs:135-138`（**重复常量**）/ `account_manager.rs:254-303`（live REST refresh，linear-only） |
| **C2 Funding settlement** | 🛑 **BROKEN** | `bybit_private_ws.rs:163-165`（exec_type 字段已序列化）/ `execution_listener.rs:200-213`（**全 dispatch on_fill 不分流 exec_type**）/ `event_consumer/loop_handlers.rs:416-601`（Fill 分支无 `exec_type=="Funding"` 处理）/ `loop_handlers.rs:565-601`（funding row 走 F4-1 unattributed audit，**不调 paper_state、不更新 balance**） |
| **C3 Slippage** | Suspect | `config/risk_config_advanced.rs:472-501`（5-tier turnover-based const）/ `:583-594` lookup / `execution_listener.rs:200-281`（**fill 路径不算 realized slippage = 无回流校准**）/ `router.rs:263-266`（**PostOnly path double-count slippage**） |
| **C4 PostOnly/IOC/Market** | OK with caveat | `intent_processor/mod.rs:1100-1110` `fee_rate_for_tif`；`bybit_rest_client.rs:395+430-432` PostOnly reject backoff；GTC 全当 taker 计费保守 |
| **C5 Cost gate** | OK | `intent_processor/gates.rs:14-92` paper / `:108-174` moderate(demo) / `:181-225` live fail-closed；EDGE-DIAG-2 修对称性 |

### 因果链（C2 单独可解释 funding_arb）

`forecast_funding 入 EV` → `开仓收 round-trip taker fee 11 bps + slippage 3 bps` → `持仓跨 settlement` → **`exec_type="Funding"` row 推 WS → 走 unattributed audit → balance 不变`** → `平仓再 11 bps` → 净 -14 bps + mark-to-market noise。
**G-2 v2 13 trades / -36.76 bps / 0 win-rate 完全可由此独立解释**（数量级对齐）。

---

## 2. Edge 维度

### 5 策略 alpha 盘点

| 策略 | 声称 alpha | 8 来源类别 | 实证 PnL | 主因 |
|---|---|---|---|---|
| grid_trading | ranging mean-reversion | #6（条件性） | fee drag 74% | 数学成立但 fee 吞 |
| ma_crossover | KAMA cross + ADX | #1（dead anomaly graveyard） | avg_win=1.2 vs avg_loss=4.7 bps | R:R 不对称 |
| bb_breakout | squeeze→expansion | **含 Donchian 含 current bar bias** | demo 7d 0 fill | 1m 结构性 noise + bias |
| bb_reversion | BB+RSI 启发式 | 无半衰期/无 OU 校准 | dormant | 无 alpha 数学 |
| funding_arb | 短 perp 收 funding | #2（伪套利：Bybit demo 不能 hedge spot leg） | -36.76 bps / 0% | C2 + 名实不符 |

### Look-ahead bias 扫描（B1 是最严重）

| # | 位置 | 类型 | 严重度 |
|---|---|---|---|
| **B1** | `openclaw_core/src/indicators/trend.rs::donchian` 视窗 `&high[n-period..n]` | rolling-max **含当前 bar** → breach 必伴 mean-revert | **HIGH 未修** |
| B2 | timeframe `'1' vs '1m'` join | Target leakage（已修 `5e2981d`） | HIGH（残）|
| B3 | grid OU σ 估计 `sqrt(Σ Δx²/n)` raw 2nd moment | σ 估计偏误 | MED |
| B4 | bb_breakout `squeeze_detected_ms` no auto-clear | First-detection deadlock 致样本选择偏误（已修） | MED（残）|
| B5 | engine_mode 标 'live' 实为 'live_demo' | ML filter 漏标签（已修 IN clause） | MED（残）|

### Edge estimator

`settings/edge_estimates.json`：n_cells=1，唯一 cell `grid_trading::ORDIUSDT n=3 win_rate=0`，`grand_mean = raw_value`（**JS shrinkage 在 p<3 不可信**），无 Deflated Sharpe / PSR / Bonferroni / walk-forward → **edge 衰减监控基本不存在**。

### 相关性

未量化；结构上 5 策略 = 2 regime bucket（ranging vs trending）→ effective N≈2，**不是 5**。

---

## 3. 模型 / ML 维度

### M1 Feature pipeline（双管线）

- 通用 34 维：`feature_collector.rs:24-59` FEATURE_NAMES → `features.online_latest`
- Edge predictor 17 维：`parquet_etl.py:39-57` + `edge_predictor/feature_builder.rs:31-145` → `learning.decision_features`
- Exit 4-Gate：`exit_features/builder.rs:78-145` → `learning.exit_features`

### M2 BLOCKER（train-serve skew）

```
parquet_etl.py:386-401 _LOAD_TRAINING_DATA_SQL   line 396  engine_mode = %(engine_mode)s
edge_label_backfill.py:129/246                    同 bug 单值匹配
```

Runtime 写入：`mode_state.rs:38-52` Live+LiveDemo → tag `"live_demo"`。
**单值 filter 让 demo 训练漏拿 LiveDemo 流量**，必须改 `engine_mode IN ('live','live_demo')` 才能取齐。**P1-7 C 47/200 labels 累积慢**直接受此 bug 拖累。

### M3 CV（A- 严谨）

`cpcv_validator.py:48-65` CPCV + Purge + Embargo 完整；策略特定 embargo（grid 72h / arb 8h / trending 24h / reversion 4h）正确；缺 PBO + walk-forward。

### M4 Outcome 回流闭环

`outcome_backfiller.rs:37-113` BACKFILL_SQL **已修两 bug**（commit `5e2981d`，含 timeframe '1m' 修正 + engine_mode INSERT 接线 + regression test `:182-226`）。
LinUCB（`linucb_trainer.py:208`）依赖 outcome_*，**NULL 期间完全没在学**。

### M5 Drift / canary

`drift_detector.rs:21-256` PSI + ADWIN ✅；缺 KS / Wasserstein / KL / per-segment / prediction drift。Model registry 0 row dormant。`canary_writer.rs:32-42` 是 JSONL audit writer 不是 model canary 灰度。

---

## 4. 执行维度

### 路径完整链

```
WS → main_fanout.rs:140-187 → TickPipeline (3 engines)
   → tick_pipeline/on_tick/step_4_5_dispatch.rs (1024 行)  ← §九警告线
   → intent_processor/router.rs (Gate 1.5/1.6/2/2.5/2.6/3)
   → order_manager.rs:354-380 REST → Bybit
   → bybit_private_ws → execution_listener.rs:200-213
   → event_consumer/loop_handlers.rs (1212 行)  ← 超§九硬上限
```

### 关键发现

| ID | 等级 | 位置 |
|---|---|---|
| X1-1 | MED | CLAUDE.md「PostOnly 反向 bug」**描述过期**：实测 demo=true / live=false（`strategy_params_demo.toml:17/69/91` vs `strategy_params_live.toml:20/53/73`）— 符合根原则 #6 保守 |
| X1-2 | MED | `router.rs:344-347` MakerKpi degraded 静默 fallback Market 无 alert |
| **X2-1** | **HIGH** | `loop_handlers.rs:520-562` partial fill **无 chase / replace**；只能等 maker_timeout (45s) sweep cancel 整单 — 剩余量未成交期间市场移动 = pure cost |
| X2-2 | HIGH | `pending_sweep.rs:67-100` cancel 后 race：tracker 先移除，若交易所在 cancel ack 前 fill → unmatched WS fill |
| X3-1/2 | HIGH | `step_4_5_dispatch.rs` 1024 行单 method + `loop_handlers.rs` **1212 行超 §九 1200 硬上限** + 0 benchmark baseline → hot path profile 黑盒 |
| X4 | OK | v2 swap 完整接线（`exit_features/v2.rs:65-103` ExitConfig 8 维），无断点；drawdown_revoke 健康 |
| X5 | OK | LIVE-AUTH-WATCHER（2026-04-27）+ BLOCKER-2 stale-cmd-tx **已修**（`live_auth_watcher.rs:55-115`/`:725-760`/`:911-927`），memory「P1 待修」描述过期 |

---

## 5. 风控维度

### 5 子项全 PASS

| 子项 | 评级 | 关键证据 |
|---|---|---|
| R1 Position sizing | B+ | `kelly_sizer.rs:198-204` fractional 4 层 + `:107` max=0.25 cap；FIX-27 `:182-191` 负 Kelly 返 0；FA-PHANTOM-1 已修 `fast_track.rs:33-66`；**default 2% vs operator 偏好 3% drift**；Risk Parity 未实装 |
| R2 SL/TP | A- | `risk_checks.rs:202-244` priority ladder（hard/dyn/TP/trail/time/PHYS-LOCK/dd/consec/daily）；`:50-60` G2-03 三道防线（validate+runtime clamp+calibrator） |
| R3 Drawdown kill | A- | `drawdown_revoke.rs:151-161` 仅 Live；删 authorization.json → live_auth_watcher 5s teardown；缺周/月级阈值 |
| R4 Config 隔离 | A- | `config/io.rs:25-47` + `main_pipelines.rs:64` PerEngineRiskStores 物理隔离；demo/live TOML 政策正确 |
| R5 Margin/总曝险 | B+ | `risk_checks.rs:113-170` 5 层 admission cap：daily 5%, leverage 20x, position 20%, total 100%, correlated 60% |

### 16 root principles + 9 safety invariants

- 16 原则：13/16 完全合规 / 3 部分（#11 Agent 自主 / #12 持续进化 / #13 AI 成本感知，均挂 TODO Wave 2/3）/ 0 违反
- 9 不变量：**9/9 全合规**
- 5 硬边界：**0 违规**

---

## 6. 因果归因（按贡献度排序）

### 主链 A — 策略 alpha 缺失（高贡献）
**4/5 策略数学上必亏**。即使 cost=0、bias=0：grid 在 trending 必输、ma_crossover 是 dead anomaly、bb_breakout 含 leak、bb_reversion 无 OU 校准。PNL-FIX-1/2「全负 gross edge」是设计层 alpha 缺失的下游表现，**不是计算 bug**。

### 主链 B — Funding settlement 不入帐（独立解释 funding_arb）
`exec_type="Funding"` row 没有专门 handler → `apply_funding_settlement` 路径不存在 → forecast 收益从未到帐 → 必亏。

### 加重 — Donchian look-ahead bias 未修
`openclaw_core/src/indicators/trend.rs::donchian` 视窗仍含当前 bar；EDGE-DIAG-2 demo override 重启 bb_breakout 后会**结构性产生 mean-revert 反信号**。

### 盲区 — Edge estimator 失能 + ML train-serve skew
n=3 不可信 + 无 DSR + 无 walk-forward → 即使有真 edge 也偵测不到；M2 单值 engine_mode filter 让训练资料系统性缺失 LiveDemo → 自学习闭环空转。

### 次要 — Partial fill 无 chase + hot path 0 benchmark
X2-1 与 grid R:R 不对称叠加放大 fee drag；X3 1212 行 + 1024 行单 method 是 profile 黑盒，live 前必跑 flamegraph。

### 排除项 — 风控、Live auth、IPC 路径、SL/TP 设计、cost gate 形式
全部 PASS，不是当前亏损贡献者。

---

## 7. 第三方交叉核验命令清单

第三方拿到此报告后逐条跑下面命令独立验证（Linux PG 端）：

```bash
# C2 funding settlement 不入帐验证
grep -n "exec_type" srv/rust/openclaw_engine/src/event_consumer/loop_handlers.rs | head
grep -rn "Funding" srv/rust/openclaw_engine/src/paper_state/

# C1 fee 常量 drift
diff <(sed -n '213,220p' srv/rust/openclaw_engine/src/intent_processor/mod.rs) \
     <(sed -n '135,138p' srv/rust/openclaw_engine/src/account_manager.rs)

# C3 slippage 无 realized 回流
grep -rn "realized_slippage\|slippage_pnl\|expected_fill_price" srv/rust/openclaw_engine/src/

# E1 Donchian look-ahead bias
sed -n '1,50p' srv/rust/openclaw_engine/src/openclaw_core/src/indicators/trend.rs   # 找 donchian 视窗
grep -n "donchian" srv/rust/openclaw_engine/src/strategies/bb_breakout/mod.rs

# E3 edge estimator n=1 状态
cat srv/settings/edge_estimates.json | jq '._meta, .grand_mean_bps'

# M2 train-serve skew
grep -n "engine_mode" srv/program_code/ml_training/parquet_etl.py
grep -n "engine_mode" srv/program_code/ml_training/edge_label_backfill.py

# M4 outcome NULL ratio（PG 端 only）
psql -c "SELECT engine_mode, count(*) total, count(*) FILTER (WHERE outcome_1m IS NULL) null_1m,
         count(*) FILTER (WHERE outcome_24h IS NULL) null_24h FROM trading.decision_outcomes
         WHERE ts > now() - interval '7d' GROUP BY engine_mode;"

# X2 partial fill 无 chase
sed -n '518,565p' srv/rust/openclaw_engine/src/event_consumer/loop_handlers.rs

# X3 hot path 文件大小
wc -l srv/rust/openclaw_engine/src/event_consumer/loop_handlers.rs \
      srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs

# C4 maker fill 实际占比（PG 端）
psql -c "SELECT engine_mode, count(*) FILTER (WHERE fee_rate < 0.0003)::float / count(*) maker_pct
         FROM trading.fills WHERE ts > now() - interval '7d'
         AND engine_mode IN ('demo','live_demo') GROUP BY engine_mode;"

# X1-1 PostOnly 配置（验「反向 bug」描述是否仍有效）
grep -n "use_maker_entry" srv/settings/strategy_params_demo.toml \
                          srv/settings/strategy_params_live.toml \
                          srv/settings/strategy_params_paper.toml

# R5 五层 admission cap
sed -n '113,170p' srv/rust/openclaw_engine/src/intent_processor/risk_checks.rs
```

---

## 8. 修补优先序建议（不实作，仅给第三方参考）

| Priority | 项目 | 一句话 |
|---|---|---|
| **P0** | C2 funding settlement | `loop_handlers.rs` Fill 分支加 `if exec.exec_type == "Funding"` → `apply_funding_settlement`；funding_arb 重启前 hard gate |
| **P0** | E2-B1 Donchian leak-free | `donchian` 视窗改 `&high[n-period-1..n-1]`；bb_breakout demo 重启**应等此修**完成 |
| **P0** | M2 train-serve skew | `parquet_etl.py:396` + `edge_label_backfill.py:129/246` 改 `engine_mode IN %(set)s` |
| **P1** | X2 partial fill chase | `loop_handlers.rs:520-562` 加部分成交后剩余量决策（chase or cancel-replace） |
| **P1** | X3 hot path benchmark | cargo bench + flamegraph，建立 P50/P99 baseline |
| **P1** | E1 5 策略 alpha hypothesis 文档 | 每策略写 8 来源归类 + 半衰期 + IC，不能写=退役候选 |
| **P2** | C1 cold-boot fee staleness gate | `last_fee_refresh_ms > 2h → cost_gate fail-closed` |
| **P2** | E5 walk-forward + DSR/PSR | 给 edge_estimator 加 90/30 split + Bonferroni |
| **P2** | R1 default 2% → 3% 对齐 | 三 TOML 显式写 0.03 |
| **P3** | R3 周/月级 drawdown brake | session+daily 之上加独立周月阈值 |
| **P3** | R4 global_notional_cap default 0 | live TOML 显式锁数值 |

---

## 9. 报告 metadata

- **审计 agent**：QC（Cost+Edge）/ MIT（Model）/ E5（Execution）/ CC（Risk）共 5 并行
- **未直接验证项（Mac dev-only 限制）**：runtime PG 实时数据（outcome NULL ratio / maker fill rate / engine running 状态），需 Linux 端跑 §7 SQL
- **过期描述纠正**：(a) memory「PostOnly demo=false / live=true 反向」**与实际 TOML 相反，已是 demo=true / live=false 的保守配置**；(b) memory「P1 stale-cmd-tx 待修」**已与 LIVE-AUTH-WATCHER 同次 BLOCKER-2 修复**
- **核验签名**：本报告所有 file:line 在 HEAD `85a4e2d` 可重现；任何 file:line 找不到证据 = 报告失效，请直接 push back
