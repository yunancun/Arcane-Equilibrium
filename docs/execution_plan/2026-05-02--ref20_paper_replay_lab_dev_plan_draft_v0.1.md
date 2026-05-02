# REF-20 Paper Replay Lab + Learning Surface 開發方案草稿 v0.1

**日期：** 2026-05-02
**狀態：** 🟡 DRAFT v0.1 — 7-agent 冷酷審查回收後初稿，**未通過任何 sign-off**，等待後續反覆審核
**Owner：** PM
**上游契約：** REF-19（治理）/ REF-20（產品面設計）
**審查來源：** CC + PA + FA + QC + MIT + A3 + E3 並行冷酷審查（2026-05-02）
**重要前置認知：** 本草稿認為 REF-20 v0.1 設計**不能直接開工**，必須先完成 REF-20 → v2 修訂 + REF-19 → v2 修訂 + 多項硬前置補完。

---

## 0. TL;DR — 如果只看一段

REF-20 想解決的痛點（改完策略後等 paper/demo 數據累積太久）真實且重要，但 v0.1 設計層面有 **3 個致命方法論缺陷（QC）+ 3 個資料平面中毒風險（MIT）+ 3 個 CRITICAL 安全漏洞（E3）+ 多個合規模糊點與 UX IA 黑洞**。直接派發實作 = 重複 V023 silent-noop / bb_breakout F3 measurement-bias / decision_outcomes timeframe drift 三類 known regression 並引入新的「replay → MLDE shadow → demo applier」橫向提權鏈。

**正確路徑**：先做 REF-20 v2 + REF-19 v2 spec amendment（PM + QC + MIT + E3 + CC 五方共簽）→ 補硬前置（lease retrofit / FUP-2 attribution / leak-free indicator audit / row-level source_tier schema / manifest HMAC）→ 才開 P1 IA 重組 → 才開 P2 read-only S3 smoke MVP。其餘 P3-P6 全部 hard-block 直到前置綠燈。

---

## 1. 7-Agent 審查總表

| Agent | 評級 | 致命 | 高風險 | 待釐清 | 判定 |
|---|---|---|---|---|---|
| **CC** 合規 | B-（Conditional Approve） | 3 違規 | — | 4 模糊 | 違規 1/2/3 必修 |
| **PA** 架構 | 🔴 阻塞 | 3 阻塞級 | 5 高風險 | 5 細節 | P2 必須降為 S3 smoke；P5 押後 LG-4 後 |
| **FA** 規格 | Conditional Approve | 6 業務邏輯 gap | — | 6 不可測 acceptance | P0 前必補 |
| **QC** 量化 | 🔴 **REJECT** | 3 致命 | 3 顯著風險 | 3 細節 | F1-F3 + O1-O2 必修才放行 |
| **MIT** 資料/schema | 🔴 阻塞 | 3 致命 | 4 leakage | 5 細節 | 7 項硬條件全綠才放行 P2 |
| **A3** UX | C（5.5/10） | 5 嚴重 | 4 認知/術語 | — | 必先補 REF-20-UX 子文件 |
| **E3** 安全 | 🔴 CRIT × 3 | 3 CRITICAL | 4 HIGH | 4 MEDIUM | applier source filter / manifest HMAC / 8 routes auth 必修 |

**整合判定：REF-20 v0.1 REJECT，要求 v2 修訂後重審。**

---

## 2. 7-Agent 主要發現索引（去重後）

### 2.1 致命 — 必須在 v2 修訂中先解決

| # | 來源 | 問題 | 修正方向 |
|---|---|---|---|
| **D-1** | QC F1 + MIT R3 + PA B2 | **Calibration ↔ Simulation feedback loop**：用 5 策略 negative gross edge 的 fills 訓 calibration model → 餵 replay 生 simulated fills → MLDE rank/veto → demo applier → 新 fills 又進 calibration（Goodhart 閉環 + replication crisis） | (1) calibration 必 OOS embargo（≥7d 與 candidate window 不重疊）；(2) per-strategy / per-side 分群；(3) hard-block on `attribution_chain_ok ≥ 70%`；(4) regime shift 後必 refit |
| **D-2** | QC F2 + MIT O4 | **q10/q50/q90 估計器 + shrink prior 未指定**：S0 ~1900 fills / (5 strat × 25 sym × 2 side) = ~7.6 fills/cell，多數 cell n<10，empirical quantile 信賴區間寬於 point estimate 本身；REF-19「shrink」是 ad-hoc | 強制 (a) block bootstrap（Politis-Romano 1000 iter）+ 95% CI；(b) hierarchical Bayesian / James-Stein shrinkage（method 寫死非 ad-hoc）；(c) cell n<30 自動 `insufficient_calibration` veto |
| **D-3** | QC F3 + MIT O2 | **demo_candidate gate 缺多重檢驗修正**：DreamEngine propose K candidates → MLDE rank → 選 q50>0 = best-of-K selection bias，0 個 DSR / Bonferroni / PBO / CSCV gate | (a) gate 改 DSR(K)>0.95，K = manifest 內 candidate 總數含已 reject；(b) total_candidates_explored 必入 manifest；(c) ≥10 candidates 強制 PBO<0.5 才 handoff |
| **D-4** | MIT R1 + PA H4 + FA #3 | **Phase 1 file-only sink = anti-pattern**：REF-19 §11 列 6 個 `replay.*` 表，REF-20 §8 卻退化成 file dir → advisory row 引用 file path 是 dangling FK；未來 schema migration 又是 V023 silent-noop 風險 | P2 開工前 land `replay.experiments` + `replay.report_artifacts` 兩表（含 V###  Guard A/B/C），其餘 4 表延後可接受；不接受 0 DB schema |
| **D-5** | MIT R2 + E3 CRIT-01 | **`learning.mlde_shadow_recommendations` 同表混 replay + real-outcome row 是中毒設計**：JSONB payload 內 source_tier 而非 row-level column + CHECK constraint，下游漏 filter 即把 simulated fill 當 real outcome；applier 完全不檢查 source = 橫向提權鏈成立 | (1) 新 column `source_tier VARCHAR(32) NOT NULL CHECK (source_tier IN (...))`；(2) `replay_experiment_id NOT NULL on replay rows`；(3) applier WHERE 加 `(source != 'replay') OR verified_against_replay_registry(manifest_hash)`；(4) 所有 consumer SQL 強制 `WHERE source_tier='real_outcome'`；(5) partial index 保熱路徑速度 |
| **D-6** | E3 CRIT-02 | **Manifest 缺 HMAC 簽名**：REF-19 §5 列 git_sha / engine_binary_sha / config sha256 但 manifest 本身沒簽 → 攻擊者 / 失控 agent 可上傳任意 hash 字串，replay 跑當前 binary 但 report 標歷史 sha = reproducibility 假象 | manifest schema 加 `manifest_signature: HMAC-SHA256($OPENCLAW_SECRETS_DIR/<env>/auth_signing_key, canonical_json)`；對齊既有 `authorization.json` 模式；server-side 簽，client 不允自帶 |
| **D-7** | E3 CRIT-03 | **8 routes 無 auth contract**：REF-20 §8 表格 0 字提 Operator role / scope / rate limit；對照 paper_trading_routes 強制 `require_scope_and_operator`、backtest_routes 強制 `_require_operator_role`，REF-20 不寫 = A01 Broken Access Control 必爆 | §8 表格加第 4 欄「Auth contract」明列 (a) current_actor required, (b) Operator role, (c) scope 字串, (d) rate limit；`POST /api/v1/replay/candidates` 必 Operator + scope=replay:handoff + idempotency_key |
| **D-8** | PA B1 | **Rust replay mode 是 dev-only smoke test，不是 production-grade canonical path**：(a) feed_replay_tick 翻轉 canary_mode 違反 reproducibility；(b) 無 IPC、無 paper auth、無 governance hub、無 stop_manager；(c) CanaryRecord ≠ Fill record（無 fee/lease/risk_envelope）；(d) 4 策略 hardcoded register，FundingArb V2 漏 | P2 必須降級為「S3 synthetic smoke test only，明文標 execution confidence=NONE」；canonical replay path 需新增 `pipeline_replay.rs` 與 live TickPipeline 共享 Orchestrator + IntentProcessor + StopManager（不 fork） |
| **D-9** | CC V2 + E3 MED-03 + PA H1 | **P2 same-path replay → IntentProcessor → 觸 Decision Lease 路徑**：Decision Lease retrofit (AMD-2026-05-02-01) 預估 ~05-15 派發、~05-30 deploy；P3-P6 advisory wiring 若早於 lease retrofit land = Rust 熱路徑 0 lease + replay-driven applier 無 lease 控制 | REF-20 §10 加明文 dependency `P3 blocked by AMD-2026-05-02-01 deploy + 7d 灰度`；P2 階段 replay 對 lease 必 mock-lease + 不寫 audit |

### 2.2 高風險 — v2 修訂 / P1 開工前須鎖

| # | 來源 | 問題 | 修正方向 |
|---|---|---|---|
| H-1 | QC O1 + MIT O1 | calibration features 含 `recent reject / timeout state` / `time of day` / `regime` 全部 look-ahead / cross-section / time-zone leakage 高風險 | 補一份「calibration feature spec doc」逐 feature 列 lookback / closed-bar / timezone / cyclic encoding 屬性；E2 必審 |
| H-2 | QC O2 | 5 策略 indicator computation 是否全部 leak-free shift(1) 未驗證；bb_breakout F3 RETRACT 教訓在案 | P0 前置 audit：`grep -nE 'rolling\(.*\)\.(max\|min\|mean)' rust/openclaw_engine/src/strategies/`，無 shift(1) 等價的全 RETRACT |
| H-3 | E3 HIGH-02 | replay engine 共享 production engine PID/IPC socket = DoS 攻擊面，operator 多 tab 同跑會直接拉低 [33] maker fill rate | replay engine 獨立 binary 或獨立 process；max concurrent=1；wall-clock budget 5min hard kill；獨立 `replay_pool` DB connection |
| H-4 | PA H3 | manifest reproducibility 在 Mac/Linux drift 下不可達成（Mac engine binary 永遠落後 deployed binary） | manifest 強制 `engine_binary_sha == deployed_binary_sha` validation；Mac 端 replay 必透過 ssh trade-core 觸發；schema 加 `runtime_environment: linux_trade_core \| mac_dev_smoke_test_only` |
| H-5 | PA H2 | 8 個 `/api/v1/replay/*` route 加進 control_api_v1 觸 1500 LOC 硬上限（paper_trading_routes.py 已 1188 LOC） | 新建 `replay_routes.py`（≤800 LOC ceiling），manifest builder + report renderer 拆 `replay_manifests.py` / `replay_reports.py`，schemas 拆 `replay_models.py` |
| H-6 | PA B3 | P5 5-Agent 抽出與 LG-2/3/4 IMPL 撞 frontend 檔（tab-learning.html / app-learning.js / agent-tracker.js 三檔 4-way merge） | REF-20 §10 序列重排：P0→P1→P2→P3→P4→**LG-2/3/4 IMPL deploy**→P5→P6 |
| H-7 | E3 HIGH-03 + CC V3 | manifest `candidate_params` inline patch 可繞 demo applier bounded delta | manifest validation 強制 patch 必 fall within demo applier 既有 `_validate_param_bounds`；超 bound → 400 patch_out_of_demo_bounds，不到 run；demo 執行仍 100% 走 Guardian / RiskConfig |
| H-8 | E3 HIGH-01 | `report_uri` 字串無 schema 契約 → SSRF / stored XSS（GUI 既知 MEDIUM-C innerHTML 警告） | scheme 白名單 `replay://` + `file://` 限 `$OPENCLAW_DATA_DIR/replay/` prefix；GUI textContent + `<a rel="noopener noreferrer">` |
| H-9 | E3 HIGH-04 | manifest creation 無 rate limit / TTL → storage exhaustion DoS | per-actor max active manifest=10 + TTL 24h auto-prune + runtime directory 配額 monitoring |
| H-10 | A3 #1 | §5 四工作區「結構未指定」黑洞（sub-tab / accordion / route 自由發揮） | 明文要求二級 sub-tab：Session \| Replay \| Compare \| Handoff；右上 mode badge 不變 |
| H-11 | A3 #2 + CC V3 | Candidate Handoff 漏 confirm 規格（1-click 推 demo applier 改 demo 參數 = 防誤觸 Lv2-3） | modal + 顯示 baseline_delta + manifest_hash + data_tier + 打字 symbol/strategy 確認；handoff 後 toast 帶 trace_id；footer 列最近 5 次 handoff |
| H-12 | A3 #4 + FA #2 | 5-Agent 抽出 IA 完全空白（11→12-Tab？sidebar？top-level menu 排序？） | 12-Tab（Agents 插在 Learning 與 Governance 之間）；Learning 原位置留 90 天 redirect notice；新 Tab icon 與既有 11-Tab 同套 icon set |
| H-13 | A3 #5 + FA #4 | P1 placeholder 戰略 = 認知欺詐風險（介面看似齊全實際 50% disabled） | placeholder 必為「Coming in P2 (~YYYY-MM-DD)」明文 banner + grey-out card with explanation，禁灰按鈕 |

### 2.3 待釐清 — 設計細節，可在 PR 階段鎖

詳見各 agent 原始發現（CC 模糊 4-7 / FA 不可測 6 項 / PA 設計細節 M1-M5 / QC Y1-Y3 / MIT Y1-Y5 / A3 認知負荷 6-9 / E3 MED-01-04）。本草稿不重列，交由 v2 修訂統一處理。

---

## 3. REF-20 → v2 修訂建議（spec amendment 清單）

REF-20 v2 必須包含以下硬條款。建議由 PM + QC + MIT + E3 + CC 五方共簽。

### 3.1 §3 系統角色邊界（新增）

- 列入第 11 個 Component：「**Replay Engine Process Isolation**」職責 = 獨立 process / IPC socket / DB pool 隔離，禁止 starve production engine 資源（修 D-8 / H-3）。
- 列入第 12 個 Component：「**Manifest Signature Authority**」職責 = HMAC-SHA256 sign + verify，對齊 authorization.json（修 D-6）。

### 3.2 §5 Manifest Schema（修訂）

```yaml
schema_version: replay_manifest_v2     # bump
manifest_signature:                     # 新增（D-6）
  algo: HMAC-SHA256
  signing_key_ref: $OPENCLAW_SECRETS_DIR/<env>/auth_signing_key
  signed_at: <UTC>
  signature: <base64>
runtime_environment: linux_trade_core | mac_dev_smoke_test_only  # 新增（H-4）
config_bundle:                          # 改 §5 兩個 sha 為 bundle（MIT Y1）
  strategy_sha256: <hash>
  risk_sha256: <hash>
  engine_sha256: <hash>
  env_mode_label: demo | live_demo | synthetic    # 禁 live
calibration_oos_label_window:           # 新增（D-1）
  start_ts: <UTC>
  end_ts: <UTC>
  embargo_days: 7
  candidate_window_overlap: false       # 自動 reject 重疊
total_candidates_explored: <int>        # 新增（D-3）
market_data:
  ...
  timeframe: 1m | 5m | 15m | 1h | 4h | 1d | tick   # enum 強制（MIT Y2）
calibration_validity_regime: <regime_id>  # 新增（QC O3）
```

### 3.3 §6 Source Tagging Contract（升級為 row-level column + DDL CHECK）

修訂 §6（D-5）：

- 所有 advisory / calibration / fill 表必含 `source_tier VARCHAR(32) NOT NULL CHECK (source_tier IN ('real_outcome','calibrated_replay','synthetic_replay','counterfactual_replay','dream_proposal','ml_shadow_rank','ml_shadow_veto'))`
- `learning.mlde_shadow_recommendations` 加 `replay_experiment_id VARCHAR(64) NULL`，且 CHECK：`(source_tier = 'real_outcome' AND replay_experiment_id IS NULL) OR (source_tier != 'real_outcome' AND replay_experiment_id IS NOT NULL)`
- 所有現有 consumer SQL 強制 `WHERE source_tier = 'real_outcome'`（E4 必 grep 全 consumer + 加 retrofit migration）
- 全表 partial index `WHERE source_tier='real_outcome'`

### 3.4 §7 Execution Calibration Contract（補方法論）

新增 §7 強制條款（D-1 / D-2 / H-1 / H-2）：

1. **OOS embargo**：calibration window 與任何 candidate replay window 必有 ≥7d 不重疊；manifest 自動 reject 重疊。
2. **Per-strategy 分群**：禁全策略共用 fill model；每 strategy + side 獨立 model。
3. **Pre-condition gate**：`attribution_chain_ok rate ≥ 0.7` 才允許 P3 開工；當前 15.4% → P3 hard-block。
4. **Quantile estimator 寫死**：q10/q50/q90 必用 block bootstrap（Politis-Romano，1000 iter）+ 95% CI；禁 normal parametric。
5. **Shrinkage method 寫死**：`shrinkage_method IN ('hierarchical_bayes', 'empirical_bayes', 'james_stein')` 必選一；禁 ad-hoc。
6. **Insufficient veto**：cell n<30 自動標 `insufficient_calibration` 並 block actionable handoff。
7. **Feature spec doc**：每 feature 列 lookback / closed-bar / timezone / cyclic encoding 屬性；E2 必審。

### 3.5 §8 API 與 Storage（新增 Auth contract 表 + DB schema 提前）

修訂 §8 表格加第 4 欄（D-7）：

| Route | Method | Auth contract | 用途 |
|---|---|---|---|
| `/api/v1/replay/health` | GET | actor required, scope=`replay:read`, 60/min | ... |
| `/api/v1/replay/manifests` | POST | Operator required, scope=`replay:write`, 10/min, idempotency_key | ... |
| `/api/v1/replay/runs` | POST | Operator required, scope=`replay:run`, 5/min, max concurrent=1 | ... |
| `/api/v1/replay/runs/{id}` | GET | actor required, scope=`replay:read`, 60/min | ... |
| `/api/v1/replay/runs/{id}/cancel` | POST | Operator required, scope=`replay:run`, 10/min | ... |
| `/api/v1/replay/reports/{id}` | GET | actor required, scope=`replay:read`, 60/min | ... |
| `/api/v1/replay/compare` | POST | actor required, scope=`replay:read`, 30/min | ... |
| `/api/v1/replay/candidates` | POST | **Operator required**, scope=`replay:handoff`, 5/min, idempotency_key, **manifest_signature 驗簽** | ... |

修訂 §11 storage posture（D-4）：

- P2 開工前 land `replay.experiments` + `replay.report_artifacts` 兩表（含 V### Guard A/B/C + idempotency 雙跑驗證 + audit_migrations.py PASS + healthcheck `replay_manifest_contract` GREEN）
- 其餘 4 表（`market_data_manifests` / `execution_model_versions` / `simulated_fills` / `candidate_results`）可延後 P3 / P4
- 禁「先寫 file 再遷 DB」歷史遷移債

### 3.6 §10 Phase 路徑（重排 + 加 dependency gates）

| Phase | 修訂後內容 | 進入條件 | 離開條件 | Block dependency |
|---|---|---|---|---|
| **P0 Spec v2** | 本草稿走 PM/QC/MIT/E3/CC 五簽 → REF-20 v2 + REF-19 v2 落檔 | 7-agent 審查 close | 五簽完成 + 進 specification register | — |
| **P1 IA 重組（純 frontend）** | 二級 sub-tab + 12-Tab Agents 抽出 + Learning redirect notice + UX wireframe | P0 五簽 + REF-20-UX 子文件 land + 5 策略 leak-free indicator audit PASS | 既有 Paper / Learning / Agents UI 行為不變、無新後端 | — |
| **P2 Read-Only Replay MVP（S3 only）** | Rust replay mode 拉成獨立 binary / process / DB pool；只跑 S3 synthetic；明文 execution confidence=NONE；落 `replay.experiments` + `replay.report_artifacts` 兩表 | P1 deploy + AMD-2026-05-02-01 lease retrofit deploy + 7d 灰度 | manifest signature + 8 routes auth + replay isolation + storage 兩表 GREEN | AMD-2026-05-02-01 |
| **P3a Global Calibration** | 全策略單一 fill model；per-strategy分群留 P3b | FUP-2 attribution writer deploy + `attribution_chain_ok ≥ 0.7` 持續 7d + decision_outcomes timeframe normalize 修 + FA-H6 est_net_bps writer 修 | OOS embargo / quantile estimator / shrinkage method 全寫死 + healthcheck `execution_calibration_freshness/power` GREEN | FUP-2 / FA-H6 / decision_outcomes |
| **P3b Cell-level Calibration** | per-(strategy, symbol, side) cell-level model | S0 累積 ≥30d + S1 recorder 上線（另立 spec） | hierarchical Bayesian shrinkage 跑通 + per-cell n≥30 比例 ≥50% | S1 recorder spec + 30d 累積 |
| **P4 MLDE / Dream Advisory** | DreamEngine propose + MLDE rank/veto，全部 advisory + source-tagged | P3a deploy + DSR(K) gate + PBO/CSCV gate + manifest `total_candidates_explored` | 5-finger handoff 鏈 dry-run + audit row 累積 | P3a |
| **LG-2/3/4 IMPL deploy** | 不屬 REF-20 但必須在 P5 前 | （另 wave）| （另 wave） | — |
| **P5 Agents Monitor 抽出** | 12-Tab IA + 90 天 redirect notice + tab-learning.html / app-learning.js / agent-tracker.js 收尾 | LG-2/3/4 IMPL deploy 完成 + 7d frontend 穩定 | 既有 5-Agent 行為 100% 保留 + redirect notice 上線 | LG-2/3/4 IMPL |
| **P6 Bounded Demo A/B Handoff** | demo_candidate 走 MLDE demo applier，強制 baseline + calibration + source mix + manifest_signature + bound check | P4 deploy + applier source filter schema land + Guardian gate dry-run | demo applier WHERE source filter + replay registry verify + 灰度 14d 0 incident | P4 + applier guard schema |

### 3.7 §11 Acceptance Checks（10 → 13 條，全部可測）

新增 / 修訂以下 healthcheck（FA #6-12 + A3 ✅ 補項 + E3 補項）：

| ID | Check | SQL / probe | PASS 閾 |
|---|---|---|---|
| 既有 1 | `replay_manifest_contract` | `SELECT COUNT(*) FROM replay.experiments WHERE manifest_signature IS NULL` | =0 |
| 既有 2 | `replay_source_mix` | `SELECT COUNT(*) FROM replay.report_artifacts WHERE source_mix IS NULL` | =0 |
| 既有 3（修訂） | `execution_calibration_freshness` | `model_age_days ≤ 14` | PASS |
| 既有 4（修訂） | `execution_calibration_power` | `cells WHERE sample_count ≥ 30 / total cells` | ≥0.5 P3b 後 |
| 既有 5（修訂） | `replay_no_live_mutation` | `SELECT COUNT(*) FROM trading.fills WHERE source_tier != 'real_outcome'` + `SELECT COUNT(*) FROM learning.mlde_edge_training_rows WHERE source_tier != 'real_outcome'` | =0 |
| 既有 6（修訂） | `replay_shadow_sink_boundary` | `SELECT COUNT(*) FROM learning.mlde_shadow_recommendations WHERE source_tier != 'real_outcome' AND replay_experiment_id IS NULL` | =0 |
| 既有 7 | `replay_report_reproducibility` | manifest signature verify + git_sha + engine_binary_sha 一致性 | PASS |
| 既有 8 | `paper_replay_lab_no_trading_submit` | grep `/api/v1/replay/.*POST.*order` + UI submit button 掃描 | =0 |
| 既有 9 | `learning_producer_monitor_read_only` | FastAPI route methods 無 PUT/DELETE | PASS |
| 既有 10 | `agents_monitor_read_only` | 同上 agents_routes.py | PASS |
| **新 11** | `replay_handoff_typed_confirm` | UI E2E test：handoff 必經打字確認 | PASS（A3 ✅） |
| **新 12** | `paper_session_no_mutation_ui` | Session 工作區 0 mutation button（含既有 submitOrder/cancelOrder 移除） | PASS（A3 #3） |
| **新 13** | `replay_resource_isolation` | replay process PID ≠ engine PID + IPC socket ≠ + DB pool 名 ≠ | PASS（E3 HIGH-02） |
| **新 14** | `replay_cv_protocol` | candidate set ≥5 必跑 PBO；PBO<0.5 才放 demo | PASS（QC F3） |
| **新 15** | `attribution_chain_ok_precondition` | `learning.mlde_edge_training_rows attribution_chain_ok rate` | ≥0.7（P3 前置） |

---

## 4. 硬前置（Hard Prerequisites）

REF-20 v2 簽完後，以下前置必須 GREEN 才能依序推進：

| # | 前置 | 阻塞哪些 phase | 目前狀態 | ETA |
|---|---|---|---|---|
| **P-1** | AMD-2026-05-02-01 Decision Lease retrofit deploy + 7d 灰度 | P2+ | ~05-15 派發 | ~05-30 deploy + ~06-06 灰度完 |
| **P-2** | LG5-W3-FUP-2 attribution writer deploy + `attribution_chain_ok ≥ 0.7` 持續 7d | P3 | sibling CC in flight | ~05-20 樂觀 |
| **P-3** | FA-H6 `learning.exit_features.est_net_bps` writer 修（100% NULL） | P3 | edge_estimator P1-7 C labels 累積 | ~05-25 |
| **P-4** | decision_outcomes timeframe normalize 修（'1' vs '1m'） | P3（manifest enum 強制） | 待派 | ~1 sprint |
| **P-5** | 5 策略 indicator computation leak-free shift(1) audit PASS | P1 | 未派 | 0.5 sprint，可立刻派 |
| **P-6** | REF-20-UX 子文件 land（wireframe + confirm flow + sub-tab 結構） | P1 | 未開 | 0.5-1 sprint |
| **P-7** | LG-2/3/4 IMPL deploy + 7d 穩定 | P5 | RFC `5ce777b` / `ec8f0f4` 0 行 IMPL | 中位 ~06-15 |
| **P-8** | S1 orderbook recorder spec land（另立 REF-21 草） | P3b | 未開 | 1-2 sprint，REF-20 之外 |

---

## 5. 修訂後分階段路線（建議 PM 採納為基線）

```
2026-05-02 [今日] 7-agent 審查 close → 草稿 v0.1 land
                            ↓
2026-05-?? P0 Spec v2 launch（PM + QC + MIT + E3 + CC 五簽 spec amendment）
                            ↓
              REF-20 v2 + REF-19 v2 + REF-20-UX 子文件 land + spec register
                            ↓
2026-05-?? P-5 leak-free indicator audit + REF-20-UX 子文件
                            ↓
2026-05-?? P1 IA 重組（純 frontend，sub-tab + 12-Tab + redirect notice）
                            ↓
2026-05-30 ← AMD-2026-05-02-01 lease retrofit deploy（P2 unblocker）
                            ↓
2026-06-06 P2 read-only S3 synthetic smoke MVP（獨立 process / DB pool / 兩表 land）
                            ↓
2026-05-20 ← FUP-2 attribution writer + FA-H6 + decision_outcomes 三修 GREEN
                            ↓
2026-06-?? P3a global calibration（OOS embargo / bootstrap CI / shrinkage 寫死）
                            ↓
2026-06-?? P4 MLDE / Dream advisory（DSR/PBO/CSCV gate / manifest signature 必驗）
                            ↓
2026-06-15 ← LG-2/3/4 IMPL deploy + 7d 穩定（P5 unblocker）
                            ↓
2026-07-?? P5 5-Agent → 12-Tab Agents Monitor（redirect notice 90d）
                            ↓
2026-07-?? P3b cell-level calibration（30d S0 + S1 recorder + hierarchical Bayesian）
                            ↓
2026-08-?? P6 bounded demo A/B handoff（applier source filter + bound check + 灰度 14d）
```

---

## 6. 與既有 wave 衝突 / 互鎖矩陣

| 既有 wave / 任務 | REF-20 互動 | 處置 |
|---|---|---|
| **AMD-2026-05-02-01 Decision Lease retrofit** | P2 same-path replay 必走 IntentProcessor → 觸 lease；P3-P6 advisory wiring 必經 lease 控制 | P2/P3+ block 直到 retrofit deploy + 7d 灰度（不退讓） |
| **LG5-W3 reviewer activation（sibling CC FUP-1 已 land）** | REF-20 §6.2 producer monitor 列 LG-5 reviewer | wait deploy + 啟動，monitor 才有資料 |
| **LG5-W3-FUP-2 attribution writer** | P3 calibration training source 必依賴 attribution clean | P3 hard-block on `attribution_chain_ok ≥ 0.7` |
| **LG-2/3/4 IMPL（H0 blocking / pricing binding / supervised live）** | P5 5-Agent 抽出與 LG-2/3/4 frontend 撞檔 | P5 押後 LG-4 deploy + 7d 穩定 |
| **P0-3 edge decision (~05-15)** | 5 策略全 net negative；REF-20 P3 calibration 在 negative edge fills 上訓 = bias | P0-3 完成後重評 calibration validity regime |
| **EDGE-DIAG-2 funding_arb V2 demo 樣本累積（至 ~05-16）** | 棄策略路徑；calibration source 應排除 V2 fills | per-strategy 分群天然解決，但 manifest schema 必加 `excluded_strategies` 欄位 |
| **18 Live Blocker #6（agent.messages / state_changes / ai_invocations all-time 0 rows）** | REF-20 §6.2 ML/Dream producer monitor 預期會 mask 此 blocker | §6.2 顯式註明「monitor degraded 不能被當 blocker 解除」 |
| **engine binary 落後 deployed binary 4-6 commit** | manifest reproducibility 在 Mac/Linux drift 下不可達成 | manifest 強制 `engine_binary_sha == deployed_binary_sha`；Mac 端 replay 必 ssh trade-core |
| **commands.rs 1343 / scanner/scorer.rs 1437 接近 1500 上限** | replay subsystem 加進 paper_trading_routes.py 模板會破上限 | 新建 `replay_routes.py` ≤800 LOC ceiling，拆 manifests/reports/models 三檔 |

---

## 7. 開放問題（v2 修訂前 PM 必須答）

1. **REF-20 v2 五簽 owner？** PM 主簽，QC/MIT/E3/CC 共簽 — 是否同步派 PA + FA + A3 副簽？
2. **REF-20-UX 子文件由誰寫？** A3 寫 wireframe + UX spec 或派 E1a 補？建議 A3 主寫，E1a 補 wireframe 細節。
3. **Manifest signing key 從哪取？** 與既有 `authorization.json` 共用 `auth_signing_key` 還是獨立 `replay_signing_key`？
4. **Replay engine 獨立 binary 還是獨立 process？** 獨立 binary = `cargo build --bin replay_engine` 重新切 main；獨立 process = production engine 再 fork 一個帶 `--replay-mode --isolated`。前者乾淨後者快。
5. **P3 hard-block on `attribution_chain_ok ≥ 0.7`** vs **P3a 用 0.5 + warning 啟動**？前者守邊界後者實用。建議前者。
6. **5 策略 leak-free indicator audit 派 QC 還是 E3？** QC 量化視角 / E3 對抗視角，建議 QC 主審 E3 副審。
7. **REF-21（S1 orderbook recorder）何時開？** REF-20 P3b 依賴；是 REF-20 子工程還是獨立 wave？建議獨立 REF-21 v0.1，REF-20 範圍只到 S2 + S0。

---

## 8. 風險矩陣

| 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|
| REF-20 v2 修訂卡 PM 五簽 ≥2 sprint | 中 | 高（整個 wave 延遲） | 五簽用 async 28h SLA；不一致用 PM 仲裁 |
| FUP-2 attribution writer 7d 累積不到 0.7 | 中 | 高（P3 hard-block 無法解） | P3a 接受 0.5 + warning 啟動 fallback；持續觀察 |
| Rust replay 獨立 binary 工作量爆 | 中 | 中 | 先做獨立 process 路徑，長期再 build 獨立 binary |
| LG-2/3/4 IMPL ETA 滑到 06-30+ | 高 | 中（P5 延遲，但不影響 P2-P4） | P5 不是關鍵路徑 |
| `learning.mlde_shadow_recommendations` schema 改動破壞既有 consumer | 高 | 高 | retrofit migration 必含全 consumer SQL grep + E2 必審 |
| Calibration model 在 5 策略 negative edge 上訓出 false negative，殺好 candidate | 中 | 高 | per-strategy 分群 + counterfactual augmentation；regime shift 強制 refit |
| Mac/Linux engine binary drift 導致 manifest reproducibility 假綠 | 高 | 中 | manifest 強制 deployed_binary_sha；Mac ssh trade-core 路徑 |
| operator 多 tab 同跑 replay → maker fill rate 進一步降 | 中 | 高 | replay isolation + max concurrent=1 + healthcheck `replay_resource_isolation` |

---

## 9. 不確定性 / 待驗證假設

- 草稿假設「PM 接受七方審查並非 blocker」；若 PM 拒絕修訂改採 v0.1 直推，本草稿失效。
- 草稿假設 AMD-2026-05-02-01 lease retrofit 路徑 A 不變；若 retrofit 改路徑 B/C，P2 dependency 重算。
- 草稿假設 5 策略 7d gross net negative 是 P0-3 後可改善的；若 P0-3 結論為「全策略重做」，REF-20 calibration source 全部失效。
- 草稿假設 `replay.experiments` + `replay.report_artifacts` 兩表的 V### 編號可在 V044 之前；實際 ETA 看 LG-5 W3 V036 + lease retrofit V037-V038 + decision_outcomes V0?? 排序。
- A3 / E3 / CC 的部分 finding 在 ≤500-700 字限制下未完全展開，v2 修訂時可能再展開新項。

---

## 10. 下一步建議（不存進 TODO，等待 operator 決策）

1. **operator review 本草稿** → 標記接受 / 拒絕 / 修訂的 finding。
2. PM 派出 REF-20 v2 起草任務（draft owner 建議 PM 主筆 + 7 agent 各自審 v2 條文）。
3. 同步派 P-5（5 策略 indicator leak-free audit）+ P-6（REF-20-UX 子文件） 兩個前置 — 與 v2 修訂並行不衝突。
4. v2 落檔 + 五簽完成後，再進 P0 → P1。
5. 草稿後續迭代 v0.2 / v0.3 ... 在同檔追加修訂歷史，不另開新檔，直到 operator 接受版次。

---

## 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| v0.1 | 2026-05-02 | PM（主會話） | 7-agent 並行冷酷審查回收後初稿；REF-20 v0.1 REJECT，提 v2 修訂建議 + 修訂後分階段路線 |

---

## 附錄 A — 7-Agent 原始發現指針

完整原始發現（含每個 finding 的具體段落引用、修法、SQL probe 等）保留在主會話 transcript。本草稿章節 2 / 3 已綜合去重。若 v2 修訂需更細粒度，可重派同 7 agent 再做一輪。

## 附錄 B — 引用上游文件

- REF-20：`docs/references/2026-05-02--paper_replay_learning_surface_design_zh.md`
- REF-19：`docs/references/2026-05-02--reality_calibrated_fast_replay_governance_zh.md`
- DOC-01 §5.1-§5.16：CLAUDE.md §二 16 條根原則
- AMD-2026-05-02-01：`docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`
- 18 Live Blocker：CLAUDE.md §三
- Decision Lease retrofit memory：`memory/project_2026_05_02_p0_sqlx_hash_drift.md`
