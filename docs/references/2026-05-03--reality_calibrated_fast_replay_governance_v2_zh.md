# REF-19 v2 — Reality-Calibrated Fast Replay 治理契約（中文版）

**狀態：** REF-19 v2 治理契約 — **supersedes v1（2026-05-02）**
**Owner：** PM（PA 共同撰寫 §3 / §6 / §11 / §12 amendment）
**日期：** 2026-05-03
**Supersedes：** `docs/references/2026-05-02--reality_calibrated_fast_replay_governance_zh.md`（v1，保留為 historical baseline）
**上游契約：** `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`（V3 baseline）
**UX SoT：** `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md`（V1）
**Indicator sweep verdict：** `docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md`（5/5 PASS, 2026-05-03）
**英文版：** `docs/references/2026-05-03--reality_calibrated_fast_replay_governance_v2.md`
**關聯：** DOC-01 §5.1–§5.16、REF-03、REF-04、REF-05、V031、V032、V034
**Audit history：** v0.1 → V1 → Round 2 → V2 → Round 3 → V2.1 → V3 P0-baseline → v2（本文件，整合 V3 + UX subdoc V1 + indicator sweep verdict）

---

## 0. v2 與 v1 的差異（讀者導讀）

v1（2026-05-02）為 governance draft，內容著重 boundary / manifest schema / verdict rules。**為什麼**需要 v2：v1 land 後到 V3 baseline 確立的這段時間，工程坑被 7-agent 三輪 audit 收斂；UX subdoc V1 land；indicator sweep PASS。**這些是工程細節而不是 governance 邊界改變**，所以 v2 不重做 v1 §1–§16，僅補三項整合：

| 整合來源 | v1 缺口 | v2 章節 | 性質 |
|---|---|---|---|
| V3 baseline §3 G2/G3/G5/G7/G8/G9 | v1 Section 5/6/11 措辭未硬化 | §5 v2 補丁 + §11 v2 補丁 + §12 v2 補丁 | **整合，不發明新規則** |
| V3 baseline §6 + §10 + §11 | v1 Section 13 phased delivery 缺 KPI / fail-mode | §13 v2 補丁 | **整合** |
| UX subdoc V1（2026-05-02） | v1 沒有 UX SoT 引用 | §17 UX binding | **新增 SoT 引用** |
| Indicator sweep verdict（2026-05-03） | v1 §13 R1 entry 未明文 G6 satisfied | §18 G6 解封紀錄 | **新增證據紀錄** |
| v1 §11 Storage and Table Separation | v1 §11 整節在 v2 中題目替換為 Resource/Quota/Retention | REF-20 v2 §15（治理 sink 邊界由 REF-20 v2 接管）+ 部分固化進 V3 §4.2 / §6.2 | **trace path 披露** |
| v1 §12 Healthcheck Requirements | v1 §12 內容從 §12 重編號 | v2 §19（Healthcheck 補完 8 項） | **章節重編號 trace** |

v1 的 §1–§16 條文以本文件 §1–§16 重述（措辭微調為與 V3 一致），不改變 v1 邊界承諾。新增章節 §17 / §18 為 v2 獨有的整合層。**例外**：v1 §11 Storage and Table Separation 內容已搬至 REF-20 v2 §15；v1 §12 Healthcheck 重編號至本 v2 §19（同類保留，不削弱）。

---

## 1. 目的（v1 §1 沿用）

Reality-Calibrated Fast Replay 是 OpenClaw 新增的「研究與開發平面（research and development plane）」。它的職責是把歷史行情實驗壓縮到分鐘級，**同時誠實標出**「歷史回放」與「真實交易所執行」之間的差距。

Reality-Calibrated Fast Replay 不替代 demo / LiveDemo / GovernanceHub / Decision Lease / live gates。它是一個實驗環境，幫 operator 與 agents 快速淘汰壞參數，挑出少量值得進入 bounded demo 驗證的候選。

Reality-Calibrated Fast Replay 可以調用 MLDE / DreamEngine / OpportunityTracker / LinUCB / ML shadow components，**但不得**把這些 component 重新定義為 replay-only 工具。它們的主要使命仍然是：Agent 自我學習 / 策略修復 / 受邊界約束的策略與風控參數演進。

**為什麼要 v2 而不是直接跳 V3**：governance 文件（REF-19 / REF-20）與 implementation plan（V3）是兩個層級。V3 描述「怎麼做」；REF-19 描述「邊界承諾」。v2 把 V3 確立的工程坑（HMAC 簽名 / `evidence_source_tier` retrofit / DB role 3-PR / replay_runner crate 邊界）反映進 governance 邊界，使邊界承諾與 implementation 對齊。

---

## 2. 不可談判邊界（v1 §2 沿用 + v2 §6.4 baseline 補強）

1. Replay 是研究平面，**永遠不得**提交 live 訂單。
2. Replay 輸出默認是 advisory，除非經現有治理流程明確提升。
3. ML / Dream 輸出**不是**執行命令。
4. synthetic 或 calibrated replay rows **不得**在缺少明確 source tag 的情況下混入 real fill labels。
5. `learning.mlde_edge_training_rows` 保持 real-outcome training view，除非未來 migration 新增明確分離的 replay-labeled view。
6. 由 replay-derived recommendation 觸發的 demo 參數變更，必須經現有 MLDE demo applier contract 保持 bounded、audited、reversible。
7. live / live_demo 參數變更必須經 GovernanceHub review、Decision Lease 與現有 live authorization gates。
8. Replay 不得削弱 H0 / Guardian / risk config / exchange disaster protection / account survival rules。
9. Replay 必須報告不確定性；單一點估計不足以作為決策依據。
10. 每一次 replay 結果都必須可由 manifest 重建。
11. **(v2 新增承襲 V3)** Replay routes 鏡像 `agents_routes.py` PG-degraded-safe pattern；Replay subsystem outage **不得** return 5xx，必須降級為 200 + status payload。
12. **(v2 新增承襲 V3)** Mac smoke 由 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` default fail-closed；任何 Mac 結果 `engine_binary_sha=NULL`，**永遠** non-actionable。

**為什麼新增 #11 / #12**：v1 假設 Replay 子系統 PG outage 只是 internal failure；後來 V3 §3 G14 確立 Replay 子系統若回 5xx 會被 healthcheck 看成系統級故障，污染整體 SLO。所以加 11。Mac 環境 #12 是因為 v1 沒有跨平台條款，V3 §6.3 加入後在 v2 補上邊界承諾。

---

## 3. 系統角色邊界（v1 §3 沿用 + v2 §6.1 runner 強化）

| Component | 職責 | 禁止事項 |
|---|---|---|
| Reality-Calibrated Replay Orchestrator | 建立 experiment manifest、載入歷史市場資料、運行 Rust 同源 replay、調用 execution calibration 與 advisory producers、寫報告 | 直接修改 live / demo 參數；變成策略權威 |
| Rust `TickPipeline` | 從歷史事件重新計算 indicators / signals / scanner context / intents / risk / verdict 行為 | 未經版本化加入 replay-only 策略特殊行為 |
| **`replay_runner` Rust binary**（v2 §6.1 補丁） | 專屬 P3+ canonical replay process；可共享 strategy / risk modules，**但不得**共享 live process bootstrap / IPC / exchange dispatch / DB writer channels / Decision Lease acquisition wiring | 與 live process co-locate；重用 live IPC server；acquire Decision Lease；mutate 任何 `trading.*` / `learning.*` table |
| Execution Simulator | 估計 maker fills / taker slippage / fees / latency / timeout / reject probability | 宣稱 simulated fills 是 real fills |
| MLDE / ML Shadow | 對候選做 rank / veto，估計 expected post-fee edge 與不確定性 | 變成 replay-only；繞過 advisory / governance tables |
| DreamEngine | 在 replay windows 上探索參數假設並產生 parameter proposals | 直接套用參數；變成一般 backtest engine |
| OpportunityTracker | 從 skipped / rejected opportunities 估計 regret / dodged-loss | 沒有 outcome evidence 時把 gate rejection count 當 regret |
| Demo Applier | 透過 Rust IPC 套用 bounded demo-only changes，並寫 audit rows | 套用 live / live_demo changes |
| GovernanceHub | Review live candidates，執行 lease / governance 邊界 | 把 replay metrics 視為足夠 live approval |
| Operator | 接受治理變更並批准 live-boundary changes | 只用 replay report 作為 live release evidence |

**為什麼把 `replay_runner` 列為獨立角色**：v1 §3 把 replay 當 Orchestrator 內部實作細節；V3 §6.1 確立它是專屬 Rust binary，必須與 live process **碼級** 隔離（不只是 logical isolation）。所以在 v2 §3 中明列為角色，把禁止事項寫死。

---

## 4. 資料來源分層（v1 §4 沿用）

Replay 的可信度取決於市場資料等級。每份報告都必須標明使用了哪個 tier。

| Tier | Source | 預期用途 | 可信度 |
|---|---|---|---|
| S0 | 真實 demo / live_demo fills、orders、verdicts、snapshots | Calibration 與 validation labels | 對已觀察行為最高 |
| S1 | 本地錄製 L1 / L50 orderbook + trades + ticker / funding / OI | 未來高擬真 maker simulation | recorder 穩定後高 |
| S2 | Bybit public klines、trades、funding、OI | 低成本歷史 replay 與 signal sweeps | 中 |
| S3 | OHLC-derived synthetic ticks | 僅策略 signal smoke tests | 對 execution 低 |
| S4 | 經批准的付費 historical L2 data | 深度 maker queue / backfill calibration | 高，但受成本 gate 約束 |

默認成本策略：先用 S0 + S2，立刻開始累積 S1；S4 需要 operator 批准具體 paid-data scope 後才可使用。

---

## 5. 必需 Experiment Manifest（v1 §5 沿用 + v2 §5.1 v2 簽名硬化）

每一次 replay run 都必須有 manifest。Manifest 是可重建性契約。

必需欄位（v1 yaml schema 沿用）：

```yaml
schema_version: replay_manifest_v1
experiment_id: <stable id>
created_at: <UTC timestamp>
operator_or_agent: <actor>
git_sha: <repo sha>
engine_binary_sha: <if available; NULL for mac_dev_smoke_test_only>
strategy_config_sha256: <hash>
risk_config_sha256: <hash>
market_data:
  tier: S0|S1|S2|S3|S4
  source: bybit_public|local_recorded|paid_l2|synthetic
  symbols: [...]
  start_ts: <UTC>
  end_ts: <UTC>
  timeframe_or_tick: <details>
execution_model:
  version: <model version>
  calibrated_from_start_ts: <UTC>
  calibrated_from_end_ts: <UTC>
  source_modes: [demo, live_demo]
candidate_params:
  strategy_params: <hash or inline patch>
  risk_params: <hash or inline patch>
output_policy:
  write_shadow_recommendations: true|false
  allow_demo_candidate: true|false
  allow_live_candidate: false
```

### 5.1 v2 簽名硬化（承襲 V3 §3 G2 + §5）

| Field | Requirement |
|---|---|
| algorithm | HMAC-SHA256 |
| key path | `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` |
| key separation | 不得與 live `auth_signing_key` 共用 |
| rotation | 90 天目標 |
| 舊 key retention | 歸檔 manifests verify 至多 180 天 |
| signer | 純 server-side |
| client-supplied signature | rejected |
| verification order | 先驗 signature，後驗 manifest hash |
| failure mode | fail-closed；run / handoff rejected |
| audit | 區分 `signature_mismatch` / `manifest_hash_mismatch` / `key_missing` / `key_expired` |
| key archive | 每個 key version 必記錄；`signing_key_ref` 必 trace 到 archive，不可只記 alias |

**為什麼要 4 fail-mode 區分**：v1 只說「fail-closed」；V3 §3 G2 進一步要求區分原因，因為 `signature_mismatch`（密鑰錯）vs `manifest_hash_mismatch`（內容被改）vs `key_missing`（部署失誤）vs `key_expired`（rotation 漏修）對應的 incident response SOP 完全不同。Audit row 必須能直接告訴 operator「該找誰處理」。

**規則**：沒有 manifest 或簽名驗證失敗的 replay 結果**不得**用於 MLDE recommendation / demo patching / governance review。任一 fail-mode → run status=failed，audit row 記入 `learning.governance_audit_log`。

---

## 6. Source Tagging Contract（v1 §6 沿用）

Replay 產生的所有 rows 與 reports 都必須帶 source tags。

| Tag | 含義 |
|---|---|
| `real_fill` | 來自交易所或 runtime DB 的真實 demo / live_demo / live fill |
| `calibrated_replay` | 由「從 real fills 校準過的 execution model」產生的 simulated fill |
| `synthetic_replay` | 從 OHLC 或其他 synthetic reconstruction 產生的 simulated fill / tick |
| `counterfactual_replay` | 以真實觀測 trade 為 anchor 重新計算的 outcome |
| `dream_parameter_proposal` | DreamEngine advisory parameter hypothesis |
| `ml_shadow_rank` | MLDE rank recommendation |
| `ml_shadow_veto` | MLDE veto recommendation |

Reports 必須包含 source mix table；任何混合不同 source 的 aggregate 必須顯式暴露混合比例。

---

## 7. Execution Calibration Contract（v1 §7 沿用 + v2 §11 補強）

Execution model 與 strategy replay 是分離的。Execution model 估計交易所現實，**不**假設 paper 立即成交。

最少模型輸出（v1 沿用）：`maker_fill_probability` / `maker_timeout_probability` / `maker_expected_latency_ms` / `maker_adverse_selection_bps` / `taker_slippage_q10/q50/q90_bps` / `reject_probability` / `fee_rate_maker` / `fee_rate_taker`。

Calibration features（v1 沿用）：symbol / strategy / side / order type / liquidity role / maker offset bps / maker timeout ms / spread bps / turnover (volume) / volatility (ATR) / funding rate / open interest / scanner regime / time of day / recent reject-timeout state。

Calibration acceptance：模型必須發布 sample count 與 calibration window；low-sample cells 必須 shrink 或標記 insufficient；reports 必須顯示 calibrated / pessimistic / optimistic outcomes；calibration stale 時 replay 可跑但**不得**產生 actionable recommendations。

---

## 8. MLDE 與 DreamEngine 使用邊界（v1 §8 沿用 + v2 §4.2 evidence_source_tier 補強）

### 8.1 ML Execution Calibration（v1 沿用）

ML 從 S0 real fills / orders 訓練或更新 execution-reality estimators；估計用於 replay simulation 與 uncertainty report。**不改 MLDE 主要角色**；calibration outputs 同樣可服務 live agent self-awareness / cost-edge analysis / 未來策略調參。

### 8.2 Dream Parameter Exploration（v1 沿用）

DreamEngine 在 replay windows 上做 parameter exploration；產生 parameter proposals，**不是** approvals。

DreamEngine outputs 與 general advisory contract 相容：

- `source = dream_engine`
- `recommendation_type = parameter_proposal`
- `expected_net_bps`
- `confidence`
- `sample_count`
- `payload.policy = read_only_parameter_proposal`
- `payload.replay_experiment_id` 當來源是 replay

DreamEngine 必須保持 Agent general self-learning component 的身份。Replay 只是其中一種 experiment environment，**不是**它的唯一用途。

### 8.3 MLDE Rank / Veto（v1 沿用）

MLDE 對 replay-generated candidates 做 rank / veto；必須包含 expected post-fee edge / q10 (pessimistic downside) / confidence / sample count / data source tier / attribution quality / calibration freshness。

MLDE recommendations 仍為 advisory，除非被現有 demo applier 或 GovernanceHub review flow 消費。

### 8.4 v2 evidence_source_tier 補強（承襲 V3 §3 G3 + §4.2）

任何 replay-derived advisory row（`learning.mlde_shadow_recommendations`）必須帶：

| Column | Requirement |
|---|---|
| `evidence_source_tier` | NOT NULL, default `real_outcome`, CHECK in `(real_outcome, calibrated_replay, synthetic_replay, counterfactual_replay)` |
| `replay_experiment_id` | NULL for `real_outcome`; NOT NULL for replay-derived |
| `manifest_hash` | NULL for `real_outcome`; NOT NULL for replay-derived |

**Insert 路徑硬化**：禁直接 `INSERT INTO learning.mlde_shadow_recommendations`；必經 `verify_replay_evidence_and_insert()` PL/pgSQL function（**SECURITY INVOKER**），驗 replay registry FK + manifest hash + source tier + output policy 後才寫。`REVOKE INSERT FROM PUBLIC` + role-based `GRANT EXECUTE` 為 target posture。

**為什麼選 SECURITY INVOKER 而不是 DEFINER**：DEFINER 會 bypass 既有 producer 的 role grant；既有 `dream_engine` / `ml_shadow` / `opportunity_tracker` 寫 `real_outcome` 是合法路徑，不能因為加了 verified function 就被擋掉。INVOKER 保留既有 grant，只在「replay-derived rows」這條新路徑加 verified function。

---

## 9. Report Acceptance Metrics（v1 §9 沿用）

Replay report 至少必須包含：gross PnL / net bps after fee / q10·q50·q90 net bps / max drawdown / maker fill rate (maker strategies) / maker timeout rate (maker strategies) / taker slippage distribution (market close paths) / reject rate / trade count / source mix / calibration model version / calibration freshness / attribution-chain quality / regime breakdown / symbol breakdown / pass-defer-reject verdict。

Promotion-oriented reports 必須列出每個 verdict 的理由。

---

## 10. Candidate Verdict Rules（v1 §10 沿用 + v2 §11 demo_candidate gate 補強）

Replay 只能產生：

| Verdict | 含義 |
|---|---|
| `reject` | candidate 比 baseline 差 / 未通過 safety / data gates |
| `defer_data` | sample 不足 / calibration stale / attribution 弱 |
| `defer_reality` | signal 看起來可以，但 execution model uncertainty 太高 |
| `defer_calibration`（v2） | calibration model age > 72h / regime frozen |
| `research_only`（v2） | 過了 methodology gates 但未到 demo handoff bar |
| `demo_candidate` | candidate 可進 bounded demo A/B（gate 增強，見下） |
| `live_candidate_research_only` | candidate 寫入 GovernanceHub review，不可 auto-apply |

Replay **永遠不得**產生 `live_approved`。

最小 `demo_candidate` gates（v1 沿用 + v2 §11 補強）：

1. calibrated q50 net bps after fee > 0
2. pessimistic q10 未突破 downside threshold
3. maker timeout / reject rates 未超閾值惡化
4. source tier 是 S0 / S1 / S2，**不是** S3-only
5. calibration 足夠新鮮（model age <= 72h）
6. attribution-chain quality 高於配置下限（**v2 補：** `attribution_chain_ok_ratio >= 0.70`）
7. parameter delta 在 demo applier bounds 內
8. **(v2 新增)** strategy-window sample `n >= 200`
9. **(v2 新增)** OOS embargo `max(7d, 2 * signal_half_life)` 滿足
10. **(v2 新增)** DSR(K) > 0.95
11. **(v2 新增)** PBO < 0.5 when K >= 10 and total trades >= 320
12. **(v2 新增)** `cost_edge_ratio >= 0.8` for LLM/ML assisted candidate loops

P2 phase 只能輸出 `reject` / `defer_data`；`defer_calibration` / `research_only` 需 P3+；`demo_candidate` 需 P6 + typed confirm。

**為什麼要這麼多新 gate**：v1 寫的是 governance 邊界，沒有量化方法論；V3 §8.3 補完 selection bias / power gate 後，v2 把這些量化條件硬綁進 `demo_candidate` 的最小 gate，避免 P3+ 階段 dev 把 governance 與 methodology 切分成兩套規則。

---

## 11. v2 補丁：Resource / Quota / Retention（承襲 V3 §3 G9 + §5）

v1 §5 manifest 未硬化資源限制；v2 補：

| Limit | Value |
|---|---|
| manifest TTL | 30 天默認 |
| per-actor active manifests | 20 |
| per-actor active runs | 1 |
| global active runs | 1（P2 / P3 phase） |
| artifact storage cap | implementation 在 P2a merge 前定義 env-specific cap |
| prune job | 持續 P2 使用前 required |
| signing key rotation | 90 天目標 |
| signing key retention | 歸檔 keys verify manifests 至多 180 天 |

Canonical manifest 必含：git sha / engine binary sha（NULL for Mac）/ strategy & risk config hashes / runtime environment / symbol list / timeframe / data tier / source mix expectation / calibration train window / OOS label window / candidate window / `total_candidates_K` / selection-bias correction metadata / fee model / execution confidence / output policy / expiry。

**為什麼要 global active runs = 1**：v1 沒指定 concurrent run 限制；V3 §5 確立資源隔離邊界。Single-tenant production runtime 上，並行 Replay 競爭 PG / disk / CPU 會干擾 demo / live_demo SLO。Cap = 1 是 P2/P3 階段保守選擇；P4+ 看數據再放寬。

---

## 12. v2 補丁：DB Role Guard 三 PR Sequence（承襲 V3 §3 G5 + §4.2）

v1 §11 storage 條文未指定 DB role grant sequence；v2 補：

`evidence_source_tier` retrofit + `verify_replay_evidence_and_insert()` PL/pgSQL function 部署必拆 **3 個 PR**：

1. **PR-1**：建立 `verified_insert_function` + `GRANT EXECUTE` to read role；既有直接 INSERT 路徑保留。
2. **PR-2**：把所有現有 producer (allowlist: `dream_engine`, `ml_shadow`, `opportunity_tracker`) 的 INSERT 路徑切到 verified function；`learning.mlde_shadow_recommendations.source` distinct sweep 在這步完成 ambiguous classification。
3. **PR-3**：`REVOKE INSERT FROM PUBLIC`；ad-hoc INSERT 路徑全部封閉；`replay_shadow_sink_boundary` healthcheck 啟用。

**禁止**：單 PR 直接 REVOKE — 會 break live demo 寫入路徑。

**為什麼要拆 3 PR**：單 PR 直接 `REVOKE INSERT FROM PUBLIC` 會在 deploy 那一刻立即斷掉所有 producer，包括 `dream_engine` / `ml_shadow` 的合法 `real_outcome` 寫入。3-PR sequence 確保 (1) 新 verified function 先到位 (2) 既有 producer 能逐一切換、能驗證 (3) 最後才 REVOKE。每個 PR 之間有 deploy + 觀察期，不是同一 commit 裡完成。

---

## 13. Implementation Sequence（v1 §13 沿用 + v2 §11 phase exit KPI 整合）

### Phase R0 — Governance First

- Land 本文件（v2）+ REF-20 v2 amendment + V3 baseline + UX subdoc V1。
- 0 runtime change；0 DB migration。
- **Phase exit KPI**：docs-only land within 1 sprint；0 runtime regressions。

### Phase R1 — Read-Only Replay MVP

- 新增 standalone `replay_runner` binary（V3 §6.1）。
- 載入 Bybit historical data → `PriceEvent` stream。
- 用 `ReplayProfile::Isolated` 跑 Rust `TickPipeline` replay mode。
- 輸出 manifest + report；**不**寫 recommendations。
- **Phase exit KPI**：`paper_replay_lab_no_order_submit` PASS；0 Decision Lease acquire；`execution_confidence='none'` 一致顯示。

### Phase R2 — Execution Calibration

- 從真實 demo / live_demo data 訓練/校準 maker fill / slippage / reject / timeout models。
- 加 calibrated / pessimistic / optimistic result bands。
- 補 healthchecks（V3 §3 G2/G3/G5/G7/G8/G9 全 PASS）。
- **Phase exit KPI**：calibration coverage ≥3 strategies × ≥10 symbols；CI tightness 顯著（Welch p<0.05）。

### Phase R3 — MLDE / Dream Advisory Integration

- 允許 replay 調用 DreamEngine 產生 parameter proposals。
- 允許 MLDE 對 replay candidates 做 rank / veto。
- 寫帶明確 replay source tags 的 advisory rows，**經** `verify_replay_evidence_and_insert()`。
- **Phase exit KPI**：advisory rows ≥10 / week；0 unverified rows reach applier。

### Phase R4 — Bounded Demo A/B Candidate Flow

- 允許 `demo_candidate` output 被 MLDE demo applier 消費。
- 強制 existing bounded delta / dedupe / rollback / audit rules。
- **Phase exit KPI**：≥1 demo handoff / week with typed confirm；0 live mutation events。

### Phase R5 — GovernanceHub Live Candidate Review

- 允許高信心、demo 驗證後的 candidates 變成 live research candidates。
- GovernanceHub review + Decision Lease + live gates 仍為 mandatory。
- **Phase exit KPI**：14d gradient observation `replay_no_live_mutation` continuous；0 incident。

---

## 14. Cost Policy（v1 §14 沿用）

默認路線：

1. 使用現有 runtime DB + 真實 demo / live_demo fills。
2. 使用 Bybit public historical data。
3. 開始累積 local orderbook data 供未來 replay。
4. 在免費路徑證明瓶頸確實是缺失 L2 history 前，**不**使用付費資料。

付費 historical L2 data 需 operator decision：vendor / symbol list / time range / expected cost / acceptance question / dataset 使用期限。

---

## 15. Review Chain（v1 §15 沿用）

實作工作為 feature / quant / data hybrid，必須使用：

PM triage → PA design check → QC strategy/math review → MIT data/schema review → E1 implementation → E2 adversarial code review → E4 regression → QA acceptance（若有 GUI/operator workflow）→ PM sign-off。

可以跳過角色，但 PM 必須明確寫出理由；**E2 與 E4 不可跳過**。

---

## 16. Operator-Facing Summary（v1 §16 沿用）

Reality-Calibrated Fast Replay 是高速度實驗環境。它調用 MLDE / DreamEngine 但不重新定義它們。MLDE 與 DreamEngine 仍是 general agent-learning components，服務策略修復 / 風控調整 / 自我改進。

Replay 可以說：

- 這組參數不值得浪費 demo 時間
- 這組參數值得 bounded demo A/B
- 這個 candidate 應該寫入 future governance review

Replay **不能**說：

- 這已經 live-approved
- synthetic PnL 是 real PnL
- ML / Dream output 是 order
- paper fill assumptions 是 exchange truth

---

## 17. v2 新增：UX SoT Binding（承襲 V3 §9 + UX subdoc V1）

v1 governance contract 未指定 UX 表面；v2 引入硬綁定：

| 概念 | 唯一 SoT | v2 引用方式 |
|---|---|---|
| Sub-tab IA | UX subdoc V1 §2 | 凍結；任何 UI 改動先改 UX subdoc，再改 frontend |
| Mode badges（4 維） | UX subdoc V1 §7 | 4 badge: run mode / data tier / execution confidence / runtime environment |
| Disabled state contract | UX subdoc V1 §8 | 必明示 missing gate（`P2 backend pending` 等），禁止 fake active CTA |
| Terminology（中英對照） | UX subdoc V1 §9 | 9 對照表凍結，TW i18n 由此擴展 |
| Verdict label 5 種 | UX subdoc V1 §5 | `reject` / `defer_data` / `defer_calibration` / `research_only` / `demo_candidate` |
| Accessibility | UX subdoc V1 §10 | 8 條規則 + axe-core CI |

**Cognitive overload 緩解**：4 mode badge + 5 verdict label 同屏 ≥10 chip 易視覺擁擠。緩解 = inline pill 化 + grey-tone disabled state + `execution_confidence='none'` 用警告色 + 灰底 + ⚠️ icon + tooltip + 卡片右上紅邊。

**為什麼 `execution_confidence='none'` 要這麼強烈的視覺處理**：A3 audit 指出純文字「無」極易忽略 — 用戶會把 P2 smoke 結果當 P3+ calibrated 結果來看，導致誤判。所以 v2 引用 UX subdoc 強制要求灰底 + ⚠️ icon + tooltip + 紅邊四重視覺保險。

**P5 Agent Monitor 抽出**：v2 重申「Agents Monitor 在 LG-2/3/4 frontend merged + 7d frontend stable 之前**不啟動**抽出」。Learning Tab 為 LG-2/3/4 主戰場；P5 必 worktree isolation。

---

## 18. v2 新增：G6 Indicator Sweep 解封紀錄

V3 §3 G6 / §7 P2 precondition 要求 5-strategy indicator leak-free audit 在 P2 runner 開工前完成。

### 18.1 解封證據

**Verdict 文件**：`docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md`（5/5 PASS, 2026-05-03）

| # | 策略 | QC | E3 | PM compute_indicators body | Final |
|---|---|---|---|---|---|
| 1 | grid_trading | Conditional → PASS | PASS | closed-bar only | ✅ PASS |
| 2 | ma_crossover | Conditional → PASS | PASS | closed-bar only | ✅ PASS |
| 3 | bb_breakout | Conditional → PASS（Donchian shift(1) 已修） | PASS | closed-bar only | ✅ PASS |
| 4 | bb_reversion | Conditional → PASS | PASS | closed-bar only | ✅ PASS |
| 5 | funding_arb | PASS（架構級無 indicator） | PASS | N/A | ✅ PASS |

### 18.2 關鍵盲點補位

**為什麼這個盲點重要**：QC 主審指出 `compute_indicators(sym)` body 是最大盲點 — 該 method 決定餵入 IndicatorEngine 的 close[] 是否含 currently-forming bar。如果含當下 bar，所有 rolling-window breach 邏輯（最大值 / 最小值 / σ-out-of-band）會 look-ahead，使 sweep 結論作廢。

PM 補位驗證：

```
TickPipeline::compute_indicators(sym) @ on_tick_helpers.rs:453
  → KlineManager::get_ohlcv(sym, "1m", Some(100)) @ klines.rs:552
    → aggregator.buffer().ohlcv_arrays(n) @ klines.rs:562
      → KlineBuffer::ohlcv_arrays(n) @ klines.rs:200
        → self.bars[start..len]   ← bars 是 closed-only buffer
  → KlineBuffer::append(bar) @ klines.rs:128
    "Append a CLOSED bar"   ← only closed
```

`compute_indicators` body 100% 從 closed-bar buffer 拿 OHLCV，**絕不**含 currently-forming bar。所有 4 個 active 策略的 Bollinger / ATR / RSI / EMA / Hurst / ADX / Volume Ratio / KAMA 都基於 closed bars 計算。

### 18.3 阻塞解除

- **V3 §3 G6 「5-strategy indicator leak-free audit before P2 runner」**：✅ 解除
- **V3 §7 P2 Precondition: Indicator Leak-Free Sweep**：✅ 解除（5/5 verdict=pass，無策略 retract / fix-required）
- **V3 §12 #13 `strategy_indicator_leak_free` healthcheck**：可寫 SQL probe（fixture 驗證模式，P2b 開工時補完）

### 18.4 Follow-up（非 P0 阻塞）

- **L-01（升 P2）**：`bb_breakout/tests.rs:33` 用 `Box::leak(IndicatorSnapshot)` 跳過 KlineManager streaming → streaming 整合無 coverage。建議綁 REF-20 P2b deliverable，每策略補 1 deterministic replay window fixture。
- **L-02（升 P2）**：`pipeline_ctor.rs:67` `feature_version: "v1.0".into()` 硬編碼 → MLDE training data 隱性混版本。建議綁 `env!("CARGO_PKG_VERSION")` 或 git-sha-derived。獨立 P2 task。
- **Mac/Linux byte-equality（E3 補審 #4）**：預期 byte-equal 但未實測；綁 REF-20 P2a baseline reproducibility test，不獨立 task。

---

## 19. Healthcheck Requirements（v1 §12 沿用 + v2 補完 8 項）

v1 §12 列 7 條 healthcheck；v2 整合 V3 §3 G2/G3/G5/G7/G8/G9 後共 15 條：

1. `replay_manifest_contract`（v1）— 每次 run 都有有效 manifest
2. `replay_source_mix`（v1）— report 暴露 real / calibrated / synthetic 比例
3. `execution_calibration_freshness`（v1）— calibration window / samples 足夠新鮮
4. `execution_calibration_power`（v1）— low-sample cells 不被當高信心
5. `replay_no_live_mutation`（v1）— replay path 不能寫 live / live_demo params
6. `replay_shadow_sink_boundary`（v1）— replay-derived MLDE rows 是 advisory + tagged
7. `replay_report_reproducibility`（v1）— report 引用 git SHA / config hashes / model version
8. **`replay_signature_verify`（v2）** — signature 先驗 / hash 後驗 / fail-closed / 4 fail-mode 區分
9. **`check_evidence_source_tier_completeness`（v2）** — `learning.mlde_shadow_recommendations` 0 NULL / invalid `evidence_source_tier`
10. **`mlde_replay_source_guard`（v2）** — replay-derived advisory rows 必經 `verify_replay_evidence_and_insert()`
11. **`replay_registry_fk_contract`（v2）** — report artifacts + simulated fills FK reference experiments
12. **`replay_resource_isolation`（v2）** — runner 0 IPC / WS / exchange dispatch / DB writer channel
13. **`replay_no_decision_lease_acquire`（v2）** — runner 0 `acquire_lease` call
14. **`replay_forbidden_wiring_fail_closed`（v2）** — forbidden path → run abort，**不只** log
15. **`replay_routes_use_safe_query_pattern`（v2）** — replay routes 鏡像 `agents_routes.py` PG-degraded posture

任一 healthcheck FAIL 阻塞 promotion to demo candidate。

---

## 20. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| v1 | 2026-05-02 | PM | REF-19 初版 governance contract；§1–§16 完整邊界；R0–R5 phased delivery |
| **v2** | **2026-05-03** | **PA + PM** | **整合 V3 contract baseline（§3 G2/G3/G5/G7/G8/G9）+ UX subdoc V1（§17 binding）+ INDICATOR SWEEP verdict（§18 G6 解封）；§5/§6/§10/§13/§19 補丁；不改 v1 §1–§16 邊界承諾。註：v1 §11 storage/table separation 內容已搬至 REF-20 v2 §15（治理 sink 邊界由 REF-20 v2 接管）；v1 §12 Healthcheck 重編號至本 v2 §19** |
| v2.0.1 | 2026-05-03 | PA + E2 fix | cross-ref label 修字（M1/M2/M3）— §0 mapping table 補 v1 §11 storage 與 v1 §12 healthcheck trace path；§20 修訂歷史補 §11/§12 trace 註記；0 boundary / 0 spec 改動 |

---

## 附錄 A — 配套文件

| 角色 | 文件路徑 |
|---|---|
| v1 historical baseline（英文） | `docs/references/2026-05-02--reality_calibrated_fast_replay_governance.md` |
| v1 historical baseline（中文） | `docs/references/2026-05-02--reality_calibrated_fast_replay_governance_zh.md` |
| v2 英文版 | `docs/references/2026-05-03--reality_calibrated_fast_replay_governance_v2.md` |
| V3 contract baseline | `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` |
| UX subdoc V1 | `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md` |
| Implementation workplan V1 | `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` |
| Indicator sweep verdict | `docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md` |
| REF-20 v1 (產品設計上游，中文) | `docs/references/2026-05-02--paper_replay_learning_surface_design_zh.md` |
| REF-20 v2 amendment（中文） | `docs/references/2026-05-03--ref20_paper_replay_lab_governance_v2_zh.md` |
| DOC-01 16 根原則 | `srv/CLAUDE.md` §二 |
| AMD-2026-05-02-01（Decision Lease 路徑 A） | `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md` |

## 附錄 B — Audit 軌跡

| 輪次 | 文件 | 主要結論 |
|---|---|---|
| Round 1 | `docs/execution_plan/2026-05-02--ref20_paper_replay_lab_dev_plan_draft_v0.1.md` | 全 REJECT |
| Round 2 | `docs/execution_plan/2026-05-02--ref20_v1_round2_audit.md` | 5/7 Conditional；2/7 阻塞 |
| Round 3 | `docs/execution_plan/2026-05-02--ref20_v2_round3_audit.md` | 5/7 Conditional Approve；12 條必補 |
| V3 baseline | `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` | P0 commit-ready；25 條 acceptance；15 條 hard gate |
| Indicator sweep | `docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md` | 5/5 PASS；G6 解除 |
| **v2 整合** | **本文件** | **PA + PM 整合 V3 + UX subdoc + sweep verdict 為 v2 governance baseline** |
