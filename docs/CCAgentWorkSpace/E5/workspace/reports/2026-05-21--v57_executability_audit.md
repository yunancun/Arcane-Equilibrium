# v5.7 Dispatch-Safe Patch 執行性審核 — E5 視角

**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.7 邏輯修正（6/6）採納完整，但工時 estimate 仍按 v5.6 量級照搬而未套 operator 5-10x underestimate 規律，加上 Apple Silicon CI tuple 與 PG buffer 預算缺席，需 5 項 must-fix 才能 Sprint 1A dispatch。

---

## 0. 工時 5-10x 規律對照（Sprint by Sprint）

> 規律來源：CLAUDE.md memory `feedback_working_principles` + 過往 sprint closure 經驗，operator 自陳 dev 估時 5-10x underestimate 規律。本表以 **3x 保守 / 7x 中位**兩段 anchor 重估，因 v5.7 含「sub-agent 並行可消化」變量，純 5-10x 套用過度悲觀。

| Sprint | 週數 | v5.7 估時 | 3x 保守重估 | 7x 中位重估 | 風險評等 |
|---|---|---|---|---|---|
| 1A | 0-1.5 | 60-80 hr | 180-240 hr | 420-560 hr | **HIGH**（含 governance + V097/V098 + V103/V104 + 6 sensor + Earn recorder） |
| 1B | 1.5-3 | 50-70 hr | 150-210 hr | 350-490 hr | MEDIUM（C10 minimal viable + Earn governance policy） |
| 2 | 4-7 | 110-150 hr | 330-450 hr | 770-1050 hr | **HIGH**（Alpha Tournament + Microstructure + On-chain counterfactual 並行） |
| 3 | 8-11 | 130-160 hr | 390-480 hr | 910-1120 hr | **HIGH**（Top-1 build ~400 LOC Rust + Stage 0 shadow） |
| 4 | 12-15 | 160-210 hr | 480-630 hr | 1120-1470 hr | **CRITICAL**（peak engineering week — Top-1 live + Top-2 + C13 Phase 1 ~600 LOC Rust） |
| 5 | 16-19 | 150-200 hr | 450-600 hr | 1050-1400 hr | **HIGH**（Top-2 live + Top-3 + C13 Phase 2 ~600 LOC Rust） |
| 6 | 20-23 | 140-180 hr | 420-540 hr | 980-1260 hr | MEDIUM |
| 7 | 24-27 | 110-150 hr | 330-450 hr | 770-1050 hr | MEDIUM |
| 8 | 28-31 | 110-150 hr | 330-450 hr | 770-1050 hr | LOW |
| 9 | 32-35 | 100-140 hr | 300-420 hr | 700-980 hr | LOW |
| 10 | 36-39 | 70-100 hr | 210-300 hr | 490-700 hr | LOW |
| **Total** | 39 週 | **1,190-1,590 hr** | **3,570-4,770 hr** | **8,330-11,130 hr** | — |

**結論**：v5.7 估時整體量級可信度 LOW。即使按最樂觀的「sub-agent 並行消化 50% workload」假設，3x 重估後仍是 1785-2385 hr，超過 v5.7 上限 50%。Operator 39 週 calendar 不變的話，**single-thread 不可達**，必須 sub-agent 並行 dispatch 才有完成可能。

**Total adjusted**：保守 3x = 3,570-4,770 hr vs v5.7 1190-1590 hr（差 3 倍）。Operator 應預期實際工時落在 3x 重估區間，calendar 39 週要可達須假設 60%+ workload 用 sub-agent 並行。

---

## 1. Top 3 執行性風險（排序）

### Risk 1：Sprint 1A 60-80 hr / 1.5 週 含 10+ 子任務不可達

- **嚴重度**：CRITICAL
- **位置**：v5.7 §8 Sprint 1A bullet list
- **描述**：v5.7 §8 將 Sprint 1A 列出至少 10 個獨立工作項：
  1. ADR-0006 amend
  2. V097/V098 Linux DB catch-up
  3. V103/V104 schema（hypotheses + preregistration + trading.fills.track）
  4. 既有 market.liquidations writer healthcheck
  5. Bybit options chain recorder（NEW）
  6. Tokenomist unlock calendar（NEW）
  7. Macro calendar feed（NEW）
  8. Binance market-data-only WebSocket（NEW）
  9. Bybit Earn API APR recorder（read-only）
  10. （隱含）ADR-0030 Earn Guardian 政策草案

  60-80 hr / 1.5 週 = 40-53 hr/週。每項平均 6-8 hr。但 V097/V098 catch-up + V103/V104 schema 在 PG empirical dry-run mandatory 規律下（CLAUDE.md `feedback_v_migration_pg_dry_run`）單獨即需 15-25 hr。剩餘 8 項 sensor + recorder 平均 5-7 hr 不切實際 — 每個 sensor 含 Rust schema + tokio task + writer + healthcheck endpoint + 測試。

- **為何屬「執行性」（非邏輯）**：v5.7 §8 邏輯結構 reviewer 已 audit converge，10 項都需要做。問題在工時分配與 calendar：1.5 週塞 10 項在執行層面不可達，但邏輯無誤。

- **Must-fix 建議**：
  1. Sprint 1A 內部進一步拆分為 1A.1（governance + migration）+ 1A.2（sensors）+ 1A.3（Earn recorder），每塊各 1 週
  2. 或保持 1.5 週 calendar 但顯式承認需 3-4 並行 sub-agent dispatch（PA 派 E1×3 / E2×3）
  3. 工時 estimate 改 120-180 hr（按 2x 重估）

---

### Risk 2：Apple Silicon CI tuple 全文缺席

- **嚴重度**：HIGH
- **位置**：v5.7 全文（§3 / §4 / §6 / §8）
- **描述**：v5.7 不提及 `aarch64-apple-darwin` 一次。新增程式包括：
  - Sprint 1A：Binance WebSocket / Bybit options recorder / Tokenomist calendar / macro feed / Earn API recorder（5 個 Rust + Python sensor）
  - Sprint 2：On-chain signals layer（Glassnode/Etherscan/DeFiLlama 整合）
  - Sprint 3-4：C10 strategy module + Top-1 strategy（~400 LOC Rust）
  - Sprint 4-5：C13 Options Stack Phase 1+2（~1200 LOC Rust）
  - Sprint 7：Advisory Allocator
  - Sprint 8-9：Auto-Allocator + Copy Infra

  CLAUDE.md memory `project_mac_deployment_target` 明示「CI tuple aarch64-apple-darwin 必含」。v5.7 未承諾任一新模組要過 Mac cross-compile gate。

- **為何屬「執行性」（非邏輯）**：v5.7 §0-7 邏輯修正無誤，但工程實作會在 Sprint 1A 第一筆 Rust commit 即觸發 Mac CI red — 因現有 CI workflow 含 Mac cross-compile target，若新 sensor 用 Linux-only crate（如 `inotify`、`epoll-rs` 直呼）會 break build。

- **Must-fix 建議**：
  1. v5.7 §8 Sprint 1A acceptance criteria 加：「所有新 Rust crate 必過 `cargo check --target aarch64-apple-darwin`」
  2. PA dispatch sub-agent 時，sub-agent prompt 顯式注入「Mac cross-compile 必過」
  3. E3 review checklist 加 Apple Silicon tuple verify step

---

### Risk 3：5 個策略並行 + 4 個新 sensor 對 hot path SLA 衝擊未評估

- **嚴重度**：HIGH
- **位置**：v5.7 §0（Tier 0 Sensors）+ §6（Sprint 1A sensor list）+ §9（Sprint 4-7 5 strategies 同時運行）
- **描述**：v5.7 規劃 Y1 末 5 策略並行 live + 4 新 sensor（Binance WS / options chain / funding aggregator / macro feed）+ on-chain signals layer。但全文未提：
  - H0 Gate <1ms / tick <0.3ms / IPC <5ms SLA 衝擊評估
  - 每個 sensor tokio task 數量與 runtime 線程預算
  - 5 strategies 並行的 Arc/Mutex 競爭路徑（CLAUDE.md memory 提及 Python ~45 threading.Lock）
  - panel_aggregator 既有負載（已 push to 0 req/s WS-first per W1 v1.1）

  Sprint 4 是 peak engineering week — C13 Options Stack Phase 1 引入 600 LOC Rust（margin calculator + Greek aggregation + IV recording 都是 CPU-bound），同時 Top-1 + Top-2 即將 live，hot path SLA 風險最高。

- **為何屬「執行性」（非邏輯）**：策略選擇與 sensor 設計邏輯 reviewer 已 audit converge。問題是 v5.7 沒有 performance budget 預先評估，等 Sprint 4 才發現 SLA 超標將觸發 expensive rework。

- **Must-fix 建議**：
  1. Sprint 1A 前置加 baseline profiling task（E5 派遣）：當前 H0/tick/IPC P50/P95/P99 + RAM/CPU peak
  2. 每個新 sensor 引入時跑 differential benchmark（before/after）
  3. Sprint 4 入口加 hot path budget check gate（peak week 前 fail-fast）
  4. 5 strategies 並行 RAM headroom 預算明寫（OpenClaw engine ≤60GB headroom per 128GB unified memory constraint）

---

## 2. Hours sanity check（與 §0 對照）

| 對照維度 | v5.7 estimate | E5 重估 | 差距 |
|---|---|---|---|
| Sprint 1A | 60-80 hr | 120-180 hr | 2-2.25x |
| Sprint 4（peak） | 160-210 hr | 480-630 hr | 3x |
| Total Y1 | 1190-1590 hr | 3570-4770 hr | 3x |
| 7x 中位（operator 規律） | — | 8330-11130 hr | 5-7x v5.7 |

**結論**：v5.7 工時 estimate 整體系統性偏低。即使按 sub-agent 並行 50% 消化的最樂觀假設，3x 重估後仍超 v5.7 上限。Operator 應預期：
- 若堅持 39 週 calendar → 必須 50-60% workload 走 sub-agent 並行 dispatch
- 若允許 calendar 滑 → 50-60 週實質完成
- v5.6 §7 末段「dev speed faster than estimate; realistic compression to 32-36 weeks」**直接刪除** — 這在 5-10x 規律下是反向預測

---

## 3. 未識別的依賴 / 阻塞（性能 / 兼容性）

### 3.1 PG 4-8GB buffer 預算衝擊
v5.7 §3 新增 4 個 table（hypotheses + hypothesis_preregistration + trading.fills.track column + 隱含 earn_movement_log），加上 V101/V102 已 reserved 12 table = 16 新 table。CLAUDE.md memory `project_hardware_constraints` 明示 PG shared_buffers + work_mem 上限 4-8GB。但 v5.7 未評估：
- 新 hypertable chunk 策略（counterfactual_log + earn_movement_log 是時序資料）
- index 命中率對既有 hot query 衝擊
- 4-8GB 預算在 30+ table 下能否撐住 P95 query latency

**Must-fix**：Sprint 1A V103/V104 dry-run 加 PG buffer footprint 評估（`pg_total_relation_size` baseline）。

### 3.2 Bybit API rate limit + 新 sensor 競爭
v5.7 §6 Sprint 1A 同時新增：
- Bybit options chain recorder（5min poll Bybit BTC + ETH）
- Bybit Earn API APR recorder
- 既有 funding rate aggregator + market.liquidations writer
- 既有 5 策略的 order placement / position query

但 v5.7 未提 Bybit API weight budget 規劃（CLAUDE.md `docs/references/2026-04-04--bybit_api_reference.md` 已有先例顯示 BB review push back 經驗）。Sprint 1A 一次加 2 個 REST poll + Sprint 2 加 Glassnode/Etherscan/DeFiLlama 3 個外部 free tier API（rate limit 嚴格），需 BB 預先審。

**Must-fix**：Sprint 1A dispatch 前 BB review API weight budget + free tier rate limit 預算。

### 3.3 Tokio runtime task 預算（hot path 線程競爭）
v5.7 §6 Sprint 1A 新增 5 個 tokio task（Binance WS / options recorder / unlock calendar / macro feed / Earn recorder）+ 既有 panel_aggregator + market writers + WS dispatchers。但 v5.7 未提 tokio runtime 線程數量規劃。

**Must-fix**：Sprint 1A 加 tokio runtime config doc（worker threads / max blocking threads / per-task budget）。

---

## 4. 對 PA+FA 匯總的必收 top 3

1. **工時 estimate 全表 3x 重估**（v5.7 §9 1190-1590 hr → 3570-4770 hr 保守線；Sprint 4 peak 160-210 → 480-630 hr；Sprint 1A 60-80 → 120-180 hr）。若 calendar 39 週不變，**必須**承諾 50-60% workload 走並行 sub-agent dispatch。

2. **Apple Silicon CI tuple 強制條款**（v5.7 §8 acceptance criteria 加：所有新 Rust crate 必過 `cargo check --target aarch64-apple-darwin`；PA sub-agent prompt 注入；E3 checklist 加 step）。

3. **Sprint 1A 前置 baseline profiling task**（E5 派遣，先測當前 H0/tick/IPC P50/P95/P99 + RAM/CPU/PG buffer baseline；每筆新 sensor merge 跑 differential benchmark；Sprint 4 入口加 hot path budget check fail-fast gate）。

---

## 5. Sprint 1A 派發前 must-fix

### 5.1 Sprint 1A 內部拆分顯式化
v5.7 §8 列 10 項任務但未指 sub-task ownership / 並行性。Must-fix：
- 1A.1 governance + migration（V097/V098 + V103/V104）→ E1 dispatch / PG dry-run mandatory
- 1A.2 6 個 sensor 並行（Binance WS / Bybit options / Tokenomist / macro feed / Earn recorder / 既有 liquidation healthcheck）→ E1×3 並行 + E2 收尾
- 1A.3 ADR-0006/0029/0030 amend + AMD 草案 → CC + FA 並行
- 顯式承諾 1.5 週 calendar 需 3+ sub-agent 並行

### 5.2 工時 estimate 修正 60-80 → 120-180 hr
按 2x 重估（已 conservative）。

### 5.3 Apple Silicon CI tuple 條款入 acceptance criteria
顯式寫入 v5.7 §8 Sprint 1A acceptance：
- 所有新 Rust crate 過 `cargo check --target aarch64-apple-darwin`
- 所有新 Python 模組無 `psutil` Linux-only API 漏守衛
- 不硬編 `/home/ncyu` / `/Users/ncyu` 路徑

### 5.4 PG buffer footprint baseline
V103/V104 dry-run 加 `pg_total_relation_size` baseline + 預測 6 月後 size growth。

### 5.5 Bybit API + free tier rate limit budget
BB review push back gate：Sprint 1A dispatch 前確認 Bybit weight + Glassnode/Etherscan/DeFiLlama free tier rate 預算。

---

## 6. Sprint 1B-3 should-fix

### 6.1 Sprint 1B C10 minimal viable + Earn governance 並行性檢驗
v5.7 §8 Sprint 1B 50-70 hr / 1.5 週：
- C10 minimal viable on 主帳 $2,000（spot + perp delta-neutral）
- Earn governance policy + first small manual stake $200-400
- Alpha Tournament dataset readiness check
- Pre-registration table seeded

50-70 hr 看似輕，但 C10 minimal viable 包含真 live 部署 + Earn first stake（asset write 需 Guardian + Decision Lease per v5.7 §4）。FA + CC + BB 並行 review 必要。**Should-fix**：工時改 80-120 hr。

### 6.2 Sprint 2 On-chain counterfactual setup 工時偏低
v5.7 §9 Sprint 2 110-150 hr 含 Alpha Tournament + Microstructure + On-chain counterfactual setup。但 §5 §3 列 on-chain counterfactual logger 30-40 hr 單獨。Alpha Tournament 5 candidates × 24mo data analysis（含 Tokenomist trial）至少 50-80 hr。Microstructure 20-30 hr。**Should-fix**：工時改 200-280 hr。

### 6.3 Sprint 3 Top-1 build ~400 LOC Rust 文件大小監控
v5.6 §7 估 Top-1（Unlock SHORT）~400 LOC Rust + 200 LOC Python。**Should-fix**：E2 sign-off 加單檔 LOC < 800 警戒檢查；若 strategy 邏輯複雜超過 800 行考慮 module split。

### 6.4 Sprint 4 C13 Options Stack Phase 1 ~600 LOC Rust 拆分
v5.6 §7 估 600 LOC Rust 含 REST + WS client + Greeks/IV/OI/DTE 結構 + spread 邏輯。**Should-fix**：預先拆分為 4 module（rest_client / ws_client / data_structures / spread_logic），每塊 < 200 LOC 避免單檔 > 800 行。

### 6.5 Sprint 5 C13 Phase 2 ~600 LOC Rust 加 portfolio margin
Phase 2 含 margin calculator（portfolio margin）+ risk engine + Greek aggregation + stress test。**Should-fix**：margin calc 與 risk engine 分檔；Greek aggregation 走 SIMD vectorize 評估（M-series CPU）。

---

## 7. 可優化 / 拆分 / 並行（並行 dispatch 機會）

### 7.1 Sprint 1A 6 sensor 並行 dispatch
v5.7 §9 線性 Sprint 1-10，但 Sprint 1A 6 個 sensor 互相獨立，可派 6 sub-agent 並行：
- E1-A：Binance WebSocket
- E1-B：Bybit options chain recorder
- E1-C：Tokenomist unlock calendar
- E1-D：Macro calendar feed
- E1-E：Earn API APR recorder
- E1-F：既有 market.liquidations writer healthcheck

E2×2 並行收尾 review + E4 跑 regression。**估收益**：calendar 從 1.5 週壓到 1 週；總 hr 不變但 wall clock -33%。

### 7.2 Sprint 2 Alpha Tournament 5 candidates 並行
5 candidate（Unlock / Pairs / C13 / Funding short / C10 enhancements）event study 互相獨立：
- QC-A：Unlock SHORT 24mo event study
- QC-B：Pairs rolling cointegration
- QC-C：C13 options data analysis
- QC-D：Funding short-only high-threshold
- QC-E：C10 enhancements 評估

並行後 Sprint 2 calendar 4 週可壓到 2.5-3 週。

### 7.3 Sprint 3-7 多策略 build 部分並行
v5.7 §9 線性 Sprint 3-7 build top-1 → top-5。但實際 top-1 進 Stage 0 shadow 後，top-2 build 可同步開始（v5.7 已暗示但未強調）。**估收益**：Sprint 3-7 calendar 20 週可壓到 14-16 週。

### 7.4 Sub-agent 並行 vs single-thread 工時節省規律
基於過往 sprint closure（CLAUDE.md memory `project_2026_05_10_sprint_n0_closure`），sub-agent 並行 dispatch 對「拆分清晰、依賴弱」任務工時節省 30-50%；對「依賴鏈強、共用 state」任務節省 < 20%。Sprint 1A 6 sensor + Sprint 2 5 candidate 屬「拆分清晰」類別。

### 7.5 既有 helper 復用機會
- Sprint 1A Binance WS / options recorder：復用既有 `panel_aggregator` rate-limit pattern + WS dispatch 框架
- 既有 market.liquidations writer 已 30k+ rows runtime → healthcheck 用既有 metrics endpoint，零新建
- Earn API recorder：復用既有 Bybit REST client + auth pattern

**估收益**：Sprint 1A 工時可從 120-180 hr 壓回 90-130 hr（接近 v5.7 上限 80 hr × 1.5）。

---

**END E5 v5.7 Executability Audit**

Verdict 摘要：GO-WITH-CONDITIONS — v5.7 邏輯結構成熟（6/6 reviewer corrections 採納），但工時 estimate 系統性偏低（按 5-10x 規律應 3-7x 重估）、Apple Silicon CI tuple 全文缺席、PG buffer + tokio runtime + Bybit API rate budget 未顯式評估。Sprint 1A 派發前 must-fix 5 項（內部拆分顯式化 / 工時 2x 重估 / Mac CI 條款 / PG footprint baseline / Bybit + free tier rate budget）。完成 must-fix 後可 dispatch。
