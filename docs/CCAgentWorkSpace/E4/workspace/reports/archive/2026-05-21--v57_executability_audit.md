# v5.7 Dispatch-Safe Patch 執行性審核 — E4 視角
**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：v5.7 修了 6 個邏輯漏洞但對「測試規劃 / regression baseline / SLA 壓測 / Stage gate 自動化」全部沉默；可派 PA 但 PA 包必須補強測試章節否則 Sprint 1A 會在 E4 階段卡死

---

## 0. 測試規劃缺口（per Sprint）

### Sprint 1A（W0-1.5, 60-80 hr, 8 個並行子任務）
- **V103/V104 migration 測試**：v5.7 §3 只說「PA dispatch finalizes」沒列 Guard A/B/C 測試 / idempotent 雙跑 / Linux PG empirical dry-run。按 CLAUDE.md Data/Migrations/Validation：「V### 必先 Linux PG empirical dry-run」這是 BLOCKER 級規則被忽略。
- **healthcheck existing liquidation writer**：v5.7 §6 只說「healthcheck/extend」沒定義 healthcheck 的具體測試 SOP — 怎麼算「健康」？rows/min 閾值？stale 容忍？panel_aggregator consumer lag 上限？
- **Bybit options chain recorder NEW**：完全沒提測試（IPC schema / serde round-trip / 5min poll 不影響 SLA）。
- **Tokenomist unlock calendar NEW**：完全沒測試規劃（外部 API failure 處理 / retry / fallback）。
- **Macro calendar feed NEW**：沒提失敗模式測試（FOMC 抓取失敗 strategy 該降級到什麼狀態）。
- **Binance market-data-only WebSocket NEW**：跨交易所 indicator 一致性（cross-language 1e-4 容差）沒提及。
- **Earn API APR recorder**：read-only 也需要測試 API 失效 / rate-limit 情境。
- **regression baseline**：v5.7 全文 0 處提到「2555 passed / 17 failed 不准降」，PA 包若不寫明 E4 沒鎖點。

### Sprint 1B（W1.5-3, 50-70 hr）
- **C10 minimal viable on 主帳 $2,000**：v5.7 沒提 C10 → IPC → Rust engine 跨語言 indicator 一致性（funding rate / basis 計算 Python vs Rust 1e-4）。
- **Earn governance policy + 首次 $200-400 manual stake**：§4 提了 Guardian + Decision Lease 但**完全沒提「stake intent → guardian → execute → audit log」的 e2e 整合測試**；這是 asset write operation 失敗 = 真實資金風險。
- **earn_movement_log table（NEW）**：daily reconciliation 與 Bybit account balance — 自動化校驗測試怎麼寫沒提。
- **Alpha Tournament dataset readiness check**：沒測試規劃（5 個策略樣本量驗證 / SSRN 文獻引用 vs 真實 24mo Bybit data 樣本是否足夠）。
- **pre-registration table seeded**：沒提 schema 鎖定後的 mutation 測試。

### Sprint 2-10（概略）
- **5 個策略跨語言 1e-4 一致性**：C10 / Unlock SHORT / Pairs / C13 defined-risk / Funding short-only — v5.7 0 處提及。Pairs trading 兩 leg + C13 put spread 兩 leg 各自都是高浮點風險。
- **SLA 壓測**：H0 <1ms / tick <0.3ms / IPC <5ms — v5.7 全文 0 提及 SLA 與新增 sensor 對 hot path 影響；Sprint 1A 加 4 個 sensor（Binance WS / options chain / funding aggregator / Macro feed）對 IPC <5ms 沒做 stress test 規劃。
- **Counterfactual logger（§5 macro/on-chain）A/B 邏輯測試**：「what would have happened」要可重放可驗證，沒測試規劃 = 評估 Y2 enable 時就沒有可信 evidence。
- **Stage 0R replay preflight + Stage 1 Demo micro canary 7d 自動化**：CLAUDE.md §四 hard boundary「Stage 1 alpha-bearing promotion 是 Demo-only after a green Stage 0R replay preflight」— v5.7 提了 stage gate 但**沒提自動化測試框架 / pass-fail 判定機制 / 漏判 false-positive 風險**。
- **Sprint 3+ Advisory Allocator**：「monthly proposals + operator approves」沒提 Console 寫入路徑的 GUI sign-off SOP（per memory：node --check 必跑）。

---

## 1. Top 3 執行性風險（排序）

### Risk 1：V103/V104 migration 缺 Linux PG empirical dry-run 規劃
- **嚴重度**：CRITICAL
- **位置**：v5.7 §3 + Sprint 1A
- **描述**：v5.7 §3 只說 "PA dispatch confirms final numbers based on Linux DB head"，沒提：(a) Linux PG dry-run 是 V### 強制 SOP（per CLAUDE.md Data/Migrations/Validation 與 feedback_v_migration_pg_dry_run）；(b) Guard A（CREATE TABLE IF NOT EXISTS for hypotheses + hypothesis_preregistration）/ Guard B（trading.fills.track ADD COLUMN type-sensitive）必須各自實裝；(c) idempotent 雙跑驗證；(d) V055 5-round loop 教訓 — Mac mock pytest cannot catch PG runtime semantic。
- **為何屬「執行性」（非邏輯）**：邏輯設計（hypotheses + preregistration + track 欄位）reviewer 已驗；缺的是 V### migration 落地時的 PG runtime 行為驗證 SOP — 純執行性。
- **Must-fix 建議**：PA 包必須加 §V-MIGRATION-TEST：
  1. Linux PG empirical dry-run（V055 教訓 SOP）
  2. Guard A/B/C 對應位置標出
  3. 雙跑 idempotent test case
  4. rollback 路徑（若 PA 確定 V103/V104 後續 in-flight migration 衝突）

### Risk 2：Sprint 1A 4 個新 sensor + 對 SLA hot path 0 壓測規劃
- **嚴重度**：HIGH
- **位置**：v5.7 §6 + §8 Sprint 1A
- **描述**：Sprint 1A 加 4 個 sensor（Binance WS / Bybit options chain 5min poll / Macro feed / Tokenomist），加上 healthcheck 既有 liquidation writer + funding aggregator extend。E4 regression-testing-protocol 規定 H0 Gate <1ms / Tick path <0.3ms / IPC round-trip <5ms — 新增 sensor 並行 publish 對 hot path 的影響沒做 p50/p95/p99 壓測規劃。Bybit options chain recorder 5min poll 一次性 dump 可能撐爆 IPC queue。
- **為何屬「執行性」（非邏輯）**：邏輯（要記 options chain）OK；缺的是「在 baseline pytest passed 不退 + SLA 不破」的 stress test → 執行性。
- **Must-fix 建議**：PA 包加 §SLA-STRESS：
  1. Sprint 1A 結束前 N=10000 IPC roundtrip p99 < 5ms 必驗
  2. Tick path p99 不退；證據 = grafana metric snapshot 或 cargo bench
  3. Bybit options chain 5min poll burst size 限制 / chunk 策略

### Risk 3：Stage 0R replay preflight + Stage 1 Demo micro canary 自動化規劃缺位
- **嚴重度**：HIGH
- **位置**：v5.7 §8 Sprint 1B + v5.6 §12 Stage Gate Language
- **描述**：v5.6 §12 寫了 Stage 0R → Stage 1 Demo 7d → Stage 2 14d → ... → Live 的 lifecycle 但 v5.7 對「**自動化**」沉默 — 7d Demo micro canary 「pass-fail 怎麼判」、「false-positive 漏判風險」、「人工 review 觸發條件」全沒。CLAUDE.md §四 是 hard boundary：Stage 1 alpha-bearing 必走 Stage 0R green replay preflight。Sprint 1A 不需要這部分但 Sprint 1B 的 C10 minimal viable + Sprint 4 Top-1 live 都會撞上。
- **為何屬「執行性」（非邏輯）**：lifecycle 邏輯（v5.6 §12 已定）reviewer 過；缺的是 Stage gate 自動化測試框架（pre-registration 比對 + actual outcome 比對 + 過 / 退判定 + alert）→ 純執行性。
- **Must-fix 建議**：PA 包加 §STAGE-GATE-AUTO 給 Sprint 1B/2/3 各個階段：
  1. Stage 0R replay 自動化 harness（replay 引擎 + outcome diff + tolerance）
  2. Stage 1 Demo 7d canary 結束時的 auto-eval 條件
  3. false-positive 漏判保護（強制 operator manual review 觸發條件）

---

## 2. Hours sanity check（測試工時是否被 estimate 漏算）

| Sprint | v5.7 estimate | E4 推測測試工時缺口 | 真實 estimate 應為 |
|---|---|---|---|
| 1A | 60-80 hr | +15-20 hr（V### dry-run / sensor SLA stress / cross-language indicator） | 75-100 hr |
| 1B | 50-70 hr | +10-15 hr（C10 1e-4 容差 / Earn governance e2e / earn_movement_log reconciliation） | 60-85 hr |
| 2 | 110-150 hr | +20-30 hr（Alpha Tournament 樣本量 walk-forward / DSR / PSR 框架 / on-chain counterfactual logger A/B） | 130-180 hr |
| 3 | 130-160 hr | +15-20 hr（Top-1 Stage 0R replay 自動化 + macro overlay 自動化 toggle test） | 145-180 hr |
| 4 | 160-210 hr | +25-35 hr（options stack property-based test + defined-risk margin calc cross-language） | 185-245 hr |
| 5 | 150-200 hr | +20-30 hr（C13 stack Phase 2 portfolio margin + Greek aggregation 跨語言） | 170-230 hr |
| **Total** | **1,190-1,590 hr** | **+105-150 hr** | **1,295-1,740 hr** |

v5.7 §9 與 v5.6 比「roughly same total」但**測試工時被無形吞下**約 100-150 hr。這是執行性 estimate gap，不是 thesis 問題。

---

## 3. 未識別的依賴 / 阻塞（測試基礎設施）

1. **Mac dev_disabled secret slots**：Bybit demo 真實 API 整合測試在 Mac 端 fail-closed by design。Sprint 1A Earn API APR recorder + options chain recorder 的整合測試必須在 Linux trade-core 跑（per memory：Mac=開發 / Linux=Runtime）。PA 包沒提這條約束。
2. **pytest 從 srv root 跑**：絕對 import 規則。新增 5 個策略測試在哪個 tests/ 子路徑？PA 沒指定 → 子任務並行時容易衝突。
3. **cross-language fixture data**：1e-4 容差驗證需要對齊的 Python ↔ Rust 輸入 fixture（如 BTCUSDT 24h ohlcv），Sprint 2 Alpha Tournament 那 24mo SSRN unlock event 數據對齊機制沒提。
4. **regression-testing-protocol skill 規則「跑兩遍」**：第一次過 ≠ 真綠（race / flaky）。v5.7 §8 Sprint 1A 8 個並行子任務間若共用 fixture 會有 flaky 風險，PA 包沒提隔離 SOP。
5. **PG 對 V103/V104 並行**：v5.7 §3 提了「PA dispatch finalizes based on in-flight migration work」— 但若 Sprint 1A 同時派多個 sub-agent 寫 V103/V104，順序鎖（race-aware sequencing）沒明寫。
6. **Counterfactual logger 落地表 schema**：§5 macro/on-chain 提了 logging 但沒提 schema（要哪個 V### / 那個 hypertable / 多少欄位）— A/B evaluation framework 沒目標表就沒 readable evidence。

---

## 4. 對 PA+FA 匯總的必收 top 3

1. **PA 包 §測試規劃**強制章節 — 每個子任務必列：unit/integration/property/concurrency/SLA/cross-language 哪幾類測試 + baseline 鎖點（2555 passed / 17 failed 不退）+ 哪個工程師（E1/E1a）寫測試。沒有測試規劃的子任務 E2/E4 直接退回。
2. **Linux PG empirical dry-run SOP** — V103/V104 落地前 PA 必跑 Linux PG dry-run（per V055 教訓 / feedback_v_migration_pg_dry_run）；證據 = 在 PA report 附 Linux PG psql 輸出 + reflection function output。
3. **Stage gate 自動化 framework** 在 Sprint 1B 末（C10 minimal viable 上 Stage 0R 之前）必須就位 — PA 排 Sprint 1B 內 ≥ 10 hr 給 stage_gate_auto_eval.py 之類 harness + Stage 0R replay tolerance config。

---

## 5. Sprint 1A 派發前 must-fix（測試規劃）

1. **§測試規劃** 章節寫入 v5.7（或 PA dispatch packet 必含），8 個子任務各列測試類型 + 工時 + owner。
2. **V103/V104 PG dry-run SOP** 寫進 §3 — Linux trade-core psql 驗證 reflection / Guard A/B/C 對應位置 / 雙跑 idempotent / rollback。
3. **regression baseline 鎖點** — Sprint 1A 任何 PR 進 main 之前 E4 必跑：`cd srv && python3 -m pytest tests/ -q --tb=short | tail -5` + `cd srv/rust && cargo test --release -p openclaw_engine --lib | tail -5`，passed 不退 + failed 不增；明寫進 PA 包。
4. **4 個新 sensor SLA 壓測** harness — IPC <5ms p99 / Tick <0.3ms p99 證據必收（cargo bench 或 grafana snapshot）。
5. **Bybit options chain recorder 5min poll burst** 策略 — 一次性 dump 拆 chunk / queue back-pressure。
6. **healthcheck existing liquidation writer** 具體 SOP — rows/min 閾值 / panel_aggregator consumer lag <30s / stale 容忍 / alert 觸發。

## 6. Sprint 1B-3 should-fix

1. **C10 minimal viable cross-language 1e-4 容差** — funding rate + basis Python ↔ Rust。
2. **Earn governance e2e 測試** — stake intent → guardian → execute → audit log 全鏈整合；Mock IO 但 governance 邏輯真跑。
3. **earn_movement_log daily reconciliation** 自動化 — 與 Bybit account balance diff > 0.01 USDT alert。
4. **Alpha Tournament walk-forward / DSR / PSR** — 5 個策略各自樣本量（SSRN 24mo unlock event 數量 vs Tokenomist trial 數據可用日期）必驗；樣本不足策略推遲 Sprint 3 build。
5. **Stage 0R replay 自動化 harness** — Sprint 1B 末 ready，Top-1 Sprint 3 build 入 Stage 0R 前必須過 harness。
6. **Counterfactual logger A/B schema** — Macro overlay + on-chain signals 落 PG hypertable schema 與 read query path 各列工時。
7. **Y1 末 counterfactual evidence evaluation 自動化** — Sprint 10 才用但 framework 在 Sprint 2 就要立（A/B 邏輯一致）。

## 7. 可優化 / 拆分 / 並行（測試自動化）

1. **Sprint 1A 8 個並行子任務**：可並派但**測試 fixture 隔離**必先寫；每個子任務專屬 fixture 路徑（tests/sprint1a/<sensor_name>/）避免 flaky。
2. **跨語言 1e-4 容差 harness**：寫一次 5 個策略全 reuse（per 5 strategies）— Sprint 2 Alpha Tournament 時就建好，Sprint 3-7 build 各 Top-N 直接套用 fixture。**這是 Sprint 2 ~10 hr 投入換 Sprint 3-7 各省 5-8 hr**。
3. **SLA 壓測 cargo bench** harness：寫一次（Tick path / IPC roundtrip / H0 Gate）後續每個 sensor + 每個策略 add 一行 bench config，避免每次重寫。
4. **Stage gate 自動化** harness：Sprint 1B 立、Sprint 3-7 各個 Top-N 直接套（per strategy plug-in pre-registration 比對）。
5. **regression baseline auto-check CI**：commit 前 git hook 跑 pytest tail -5 + cargo test tail -5，passed/failed 數寫入 commit message 自動 prepend；無需每次手敲。
6. **counterfactual logger** 與 regular learning.* schema 統一 — 一個 hypertable, type 欄位 dispatch（counterfactual vs production），避免 schema 雙軌。

---

## 結論

v5.7 完成「邏輯 reviewer 6/6 漏洞補丁」是 thesis 級進步，**但對 E4 視角的執行性（測試 / regression baseline / SLA / V### dry-run / Stage gate 自動化 / 1e-4 容差）全部沉默**。如果 PA 包按 v5.7 原文派發 Sprint 1A，E4 階段會在以下節點卡死：

1. V103/V104 PR 進來時無 Linux PG dry-run 證據 → E4 退回 E1
2. 4 個新 sensor 落地 IPC p99 退化 / pytest baseline 退 → E4 退回 E1
3. Sprint 1B C10 minimal viable 上 Stage 0R 時無自動化 harness → 全手工驗 = 時間成本爆

**Verdict GO-WITH-CONDITIONS**：可派 PA 但 PA dispatch packet 必加 §測試規劃 / §SLA 壓測 / §V### dry-run / §Stage gate 自動化 4 個強制章節，且 Sprint 1A 各子任務必逐項列測試類型 + 工時 + owner。預期 Sprint 1A hours 60-80 修正為 75-100，Sprint 1B 60-85，總 Y1 工時加 100-150 hr 至 1,295-1,740 hr。

**E4 REGRESSION DONE: PASS (audit-only, no code changes)**
