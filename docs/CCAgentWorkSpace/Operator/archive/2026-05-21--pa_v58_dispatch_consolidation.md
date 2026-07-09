# v5.7+v5.8 真實開發路線整合 — PA 視角
**日期**：2026-05-21
**Verdict**：**DISPATCH-NEEDS-FIX**（13 prerequisite 完成 D+5~D+10 內可派 Sprint 1A-β；v5.7 Sprint 1A-α 已 PM-signed 不受影響）
**One-line summary**：v5.8 13-module thesis 14 audit 全 0 NO-GO（8 GO / 3 HOLD / 0 NO-GO），HOLD 三家（E2/R4/TW）阻塞點皆為文檔/工時/治理層面非邏輯/設計層；must-fix 去重後 16 條共識 CRITICAL + 24 條 HIGH；真實 Sprint 1A 670-1,015 hr / 7-9w（v5.8 543-797 hr 系統性偏低 20-43%）；Y1 真實 3,500-5,600 hr / 44-55w（v5.8 2,780-3,930 hr 漏 GUI 261-374 hr + TW 450-640 hr + MIT spec 120-140 hr + AI cost $1.3-2.6k）；派發 v5.7 leftover 4 follow-up + v5.8 13 prerequisite 必 land。

---

## 0. 14 audit verdict 聚合 + 跨 agent 共識 pattern

### 0.1 Verdict 分布

| Verdict | 數 | Agents |
|---|---|---|
| GO-WITH-CONDITIONS | 11 | A3 / AI-E / BB / CC / E3 / E4 / E5 / FA / MIT / QA / QC |
| HOLD（conditional） | 3 | E2 / R4 / TW |
| NO-GO | 0 | — |

### 0.2 3 HOLD 阻塞分析

**E2 HOLD**：對抗式 audit 找盲點性質；非設計缺陷而是工時/依賴/治理缺口
- 7 條矛盾（§3/§4/§14 工時三處不一致 / V103 EXTEND 規格不明 / V### 編號散落 / §10 漏 P0 precondition / §11 反向 attack 6 條未識別 / 13 module 依賴圖未畫 / Sprint 7-8 IMPL race / 24h undo 已 fill 不可逆）
- 阻塞層級 = 派發前 5-7 hr PA + PM hands-on 補完即解
- 不阻 1A-α；阻 1A-β 派發

**R4 HOLD**：文檔層面 ~46 新文件 + ~40 條 index 漂移
- 7 ADR draft / 9 V### spec doc / 13 module spec / 8 runbook / docs/README index 缺
- 阻塞層級 = TW + PA + MIT 並行 ~150-200 hr 補完
- 不阻 1A-α；1A-β 派發前先 reserve placeholder file path（含 frontmatter）即可

**TW HOLD-WITH-CONDITIONS**：TW 工時 450-640 hr 完全沒列 + 並行 dispatch 缺位
- §3 / §4 / §8 / §9 全表 0 TW 行
- 阻塞層級 = §3/§4 表格 + §12 decision point 補 = 1-2 hr 修檔 + PM 仲裁
- 不阻 1A-α；阻 1A-β 並行 dispatch 規劃

**結論**：3 HOLD 全部屬 conditional + 文檔/治理/工時補位類別，**邏輯設計通過 11/14 GO**。13 prerequisite 完成後 → 全 HOLD 升 GO。

### 0.3 共識 pattern（≥3 agent 重合）

| Pattern | 重合 agent | 次數 |
|---|---|---|
| Sprint 1A 工時系統性偏低 20-90% | E2/E4/E5/MIT/QA/QC/R4/TW/AI-E | **9** |
| V105-V113 schema spec 全 placeholder（V055 5-round loop 9x 放大） | MIT/E4/E2/R4/QA/CC | **6** |
| 13 module 依賴圖未畫 / IMPL wave 必撞 race | E2/E4/E5/QA | **4** |
| M4 leakage 防範（feedback_indicator_lookahead_bias 教訓延伸） | MIT/E4/QC | **3** |
| M10 Tier D HMM 黑名單 + M8 GARCH 觸 math-model audit | MIT/QC | **2**（但 CRITICAL）|
| 5-gate auto path inheritance 未明文 | E3/CC/QA | **3** |
| GUI 工時 ~261-374 hr 完全缺席 | A3 / E2 / FA | **3** |
| TW 工時 ~450-640 hr 完全缺席 | TW | **1**（但 14% 系統性缺口）|
| ContextDistiller token budget 從 700 → 1,200-1,500 撞 L1 SLA | AI-E | **1**（CRITICAL）|
| M11 + M7 信號重疊（dedup 機制缺）| QC / FA | **2** |
| M13 Y2 Binance trade enable 與 Product Boundary 衝突 | BB / CC | **2**（CRITICAL）|
| Console tab 歸屬 + A3 sign-off gate 未列 §12 | A3 | **1**（但 8 surface Lv 3-4 高危）|
| operator forgetfulness mitigation vs priority 5 衝突 | CC / E3 / FA | **3** |
| M9 mSPRT i.i.d. 假設違反 + power 損失 | QC / E4 | **2** |
| M1 Lease Tier 命名 vs AMD-01 Stage 0-4 衝突 | QA / CC | **2** |

---

## 1. 跨 agent 共識 must-fix 合併清單（按優先級 — 去重後 16 CRITICAL + 24 HIGH）

### CRITICAL（缺一不派 Sprint 1A-β；16 條）

| # | Item | 來源 agent | 估時 | Owner |
|---|---|---|---|---|
| **CR-1** | **v5.7 4 follow-up 收口**（V103 audit field +4-5 / V### re-number search/replace / PG conn 範例 CLAUDE.md / Earn 五角色 cross-ref） | TODO §0.5 | **8-12 hr** | PA + MIT + TW + FA + E3 + QA |
| **CR-2** | **M1 Lease Tier governance spec** + ADR-0034 5 細節（per-decision lease emit / lease_id uniqueness / 80% yes-rate window / Console toggle auth / 24h undo scope）+ Tier → LAL 改名（避 AMD-01 Stage 0R-4 衝突）+ LAL n ↔ Stage n 對齊矩陣 | CC / QA / E3 | **12-18 hr** | PA + CC + QA |
| **CR-3** | **AMD-2026-05-21-01-autonomy-vs-human-final-review** AMD（priority order 第 5 條 vs §11 forgetfulness mitigation 邊界；protected scope vs opt-in scope） | CC | **4-8 hr** | PM + CC |
| **CR-4** | **ADR-0040 multi-venue gate spec**（M13 Y2 Binance trade enable 措辭修正 → Y3+ at earliest + venue 維度 5-gate schema + per-venue secret slot + per-venue authorization） | BB / CC / E3 | **6-10 hr** | TW + BB + E3 |
| **CR-5** | **M10 Tier D 模型黑名單 hardening** + ADR-0036 GARCH 替換（ADR 明寫「no HMM / Markov-switching / GARCH」+ 替代 = ATR-vol regime + funding state 雙 axis 矩陣 / realized vol percentile + block bootstrap） | MIT / QC | **4-6 hr** | TW + MIT + QC |
| **CR-6** | **M4 minimum bar + leakage protocol**（DRAFT 必附 6 attribute：N ≥ 30 / Bonferroni p < 0.05/K / effect size ≥ 0.2 / 6mo sub-period stability / Harvey-Liu-Zhu graveyard flag / cluster K silhouette 5-fold CV）+ rolling stat 強制 shift(1) leak-free | MIT / QC / E4 | **5-8 hr** | MIT + PA |
| **CR-7** | **M11 threshold statistical derivation + M7 dedup**（M11 3 threshold noise floor 5d empirical + 2.5-3σ；M11 daily divergence event 是 M7 input 非 independent demote；M7 為 single decay authority）+ M7 STAGE_DEMOTED → DECAY_ENFORCED 改名 | QC / FA / QA | **4-6 hr** | MIT + QC |
| **CR-8** | **9 個 V### schema spec doc**（V105 overlay / V106 health / V107 replay div / V108 A/B / V109 anomaly / V110 reward / V111 discovery tier / V112 lease tier / V113 decay）— 仿 v103_v104 範式（column inventory + Guard A/B/C + engine_mode CHECK + hypertable 判斷 + Linux PG dry-run + idempotency）；V106 高頻表必 hypertable 7d chunk + 7d compression + 90d retention | MIT / E4 / E5 / R4 | **90-140 hr** | MIT + PA + E5 |
| **CR-9** | **PG dry-run mandatory + Guard A/B/C 規範條款**寫入 v5.8 §3 / §10；cross-V### dependency graph（V107 → V103/V109/V113 / V108 → V103 / V109 → V112 / V112 → V113 / V105 → V107）；Sprint 1A-β/γ 不能無條件並行（順序 dispatch + cross-ADR collision gate） | MIT / E4 / E2 / E5 / QA | **3-5 hr** | PA + E5 |
| **CR-10** | **§10 加 P0 precondition table**（P0-EDGE-1 + P0-LG-3 + P0-OPS-1..4 + 5-gate live）+ §12 加第 5 條 operator decision point「確認 Sprint 4 Live precondition ETA OR accept LiveDemo 自動降級」 | E2 / FA | **2-4 hr** | PM |
| **CR-11** | **GUI 工時 +261-374 hr 寫入 §3 / §4 / §14** + Console tab 歸屬 4 tab × 2-4 sub-section（不擴張 16 tab）+ §12 加 A3 sign-off invariants（48-53 hr Y1 / 8 surface Lv 3-4） | A3 | **3-5 hr** | PM + A3 |
| **CR-12** | **TW 工時 +450-640 hr 寫入 §3 / §4 / §8 / §9 / §12**（第 5 條 operator decision「Approve TW 並行 dispatch with PA-MIT-CC parallel tracks」） | TW | **2-3 hr** | PM + TW |
| **CR-13** | **v5.8 §3 Sprint 1A 工時上修 543-797 → 670-1,015 hr** + §4 Y1 total 上修 2,780-3,930 → 3,500-5,200 hr + Y1 calendar 37-44w → 44-55w；§3 五階段 + §4 Sprint 表三處時間數字統一 | E2 / E4 / E5 / MIT / R4 / TW / A3 | **1 hr** | PM |
| **CR-14** | **M12 OrderRouter trait 必含 maker_fill_rate_30d metric** + ADR-0039 routing audit log schema + 字典補 PostOnly fill rate SOP；M11 ADR-0038 明示 nightly replay 用 PG `market.liquidations` table (自家累積) 為 historical source（**不**依賴 Bybit historical liquidations API — 不存在） | BB / QC | **3-5 hr** | BB + TW |
| **CR-15** | **5-gate auto path inheritance 明文**（v5.8 §11 invariant：M1 Tier 1+2 / M2 auto-disable / M3 auto-degrade / M6 auto-weight / M7 auto-demote / M8 alert→action / M10 capital trigger 寫 live state 必經完整 5-gate fail-closed）+ M4 DRAFT writeback Decision Lease + HMAC signature + ml-training-pattern-miner role + rate limit | E3 / CC | **4-6 hr** | TW + E3 + CC |
| **CR-16** | **ADR-0041 ContextDistiller v4**（分層 snapshot + token 硬 cap ≤ 800/推理；超出降級 statistical-only path） + DOC-08 月 $60 cap 重估（Y2 預估 $112-213/月）；M4 Cowork review path 純規則 vs LLM 明示；M11 narrative daily L1 Ollama 9B + divergence threshold ≥ $X 才產 narrative | AI-E | **6-10 hr** | AI-E + TW + PM |

**CRITICAL 合計**：**157-246 hr** + 90-140 MIT spec(CR-8) + 450-640 TW(CR-12) + 261-374 GUI(CR-11) + 48-53 A3(CR-11) **核心壓在 13 prerequisite check list（CR-1..16）**

### HIGH（派發後可並行補；Sprint 1A-β-ε 期內 land；24 條）

| # | Item | 來源 agent |
|---|---|---|
| H-1 | M2 overlay state machine 對齊 AMD-2026-05-15-01 Stage gate（PRODUCTION_TRIGGER 必過 Stage 0R replay preflight） | CC / QA |
| H-2 | M6 Bayesian opt 算法 spec（GP kernel + acquisition function + iter budget + convergence）+ 30% rollback 累積 cap | MIT / QC / E3 |
| H-3 | M7 per-strategy baseline calibration（expanding mean + std + shift(1)）+ DECAY_ENFORCED 路徑明示（demo fall-back 還是 live 50% 14d review） | MIT / QC / QA |
| H-4 | M8 autoencoder Y2 spec（training data window exclude anomaly period / retraining cadence / reconstruction error threshold per-symbol） | MIT / E3 |
| H-5 | M9 variant 4 類型 Stage 路徑分類（parameter / sizing / trigger / overlay）+ A/B test only OpenClaw self-trade（Copy Trading follower 永遠 control variant）| QA / QC / BB |
| H-6 | M10 AUM trigger 數據源（realized vs unrealized PnL；trading.fills vs wallet balance API）+ 與 AMD-2026-05-15-01「新策略需 operator approve」相容性 | E3 / FA |
| H-7 | M5/M12/M13 trait method slot 列表（M5: get_predict/streaming/drift_callback/rollback/throttle/health；M12: route_order/venue_health/cross_venue_position/forecast_slippage/reverse_snipe；M13: Venue enum hardcode DEX/Hyperliquid 拒絕） | E3 / E4 |
| H-8 | M3 / M8 / M11 風控三 module trigger mutual exclusion contract | FA |
| H-9 | M3 hot-swap (PM verdict M3) / M6 capacity-aware sizing (PM M6) / M7 cross-strategy correlation re-sizing (PM M7) 三 missing module — 處置（defer v5.9 + ETA 或新增 M14-M16） | FA |
| H-10 | M1 / M3 / M11 量化 threshold（Tier 2 sharpe/sample/max_dd 具體值 / 5 health domain threshold / M11 divergence bps） | FA |
| H-11 | §11 operator forgetfulness mitigation 反向 attack 6 條補對應 mitigation（M1 24h undo 已 fill 不可逆 / M2 false anomaly trigger / M3 healthy market burst FP / M7 14d × 50% 持續虧 / M8 alpha source vs halt 混淆 / M11 passive Slack 報告 5d 不被 ack 自動升 M3 HEALTH_WARN） | E2 |
| H-12 | §0.5 灰度事件嚴重度對照表（M1 auto-approve INFO / M2 auto-disable WARNING / M2 auto-enable CRITICAL-eligible 重置 7d / M3 HEALTH_DEGRADED WARNING / M3 HEALTH_CRITICAL CRITICAL / M7 auto-demote WARNING / M9 variant >25% 觸發新 7d / M13 新 venue 首交易 21d full Stage 3 等價） | QA |
| H-13 | M1/M3/M7/M9/M12/M13 涉及 Rust-side IPC message type 增量清單（Sprint 1A-β/γ DESIGN 必補） | QA / E4 |
| H-14 | 4 state machine（M1/M2/M3/M7）完整性測試 § STATE-MACHINE-TEST（每 SM 必有 proptest 窮舉 + invalid → rejected + dead-state scan + is_none() reset auto-clear 反模式 scan） | E4 |
| H-15 | §V-MIGRATION-DRY-RUN（10 個 active V### 各 Linux PG empirical dry-run + Guard A/B/C 對應 + idempotent 雙跑 + rollback + engine restart 實測 per a19797d 教訓） | E4 |
| H-16 | §SLA-STRESS（5+ hot path module M1/M3/M9/M11/M12 各 cargo bench harness + p50/p95/p99 + IPC <5ms / Tick <0.3ms / H0 <1ms 不破鎖點）+ M8 hot path budget ≤ 5μs / fill hard gate（ADR-0036） | E4 / E5 |
| H-17 | §M9-FRAMEWORK-VALIDATION + §M4-LEAKAGE-SCAN（M9 mSPRT known distribution 1000+ simulation 驗 Type I + Power；M4 每 feature 並列 leak-free shift(1) 對比 + anti-mock leakage scan） | E4 |
| H-18 | Cross-language 1e-4 容差 fixture harness 一次建多次用（M11 replay vs production / M3 latency / M6 Bayesian / M8 z-score 共用） | E4 |
| H-19 | 13 module 預先拆 sibling file structure（M3 healthcheck / M4 pattern miner / M8 anomaly / M9 A/B / M11 replay / M12 routing）；避 G5-09 tick_pipeline 3524 LOC 重蹈 | E5 |
| H-20 | Apple Silicon CI tuple 全 13 module（M4 ndarray-stats / linfa-clustering / M8 tch-rs / burn / M11 inotify-epoll 等 Linux-only crate 篩選） | E5 |
| H-21 | external secret slot policy（M2 macro feed / M12 Binance trade key / M13 multi-venue API key）— `$OPENCLAW_SECRETS_DIR/external/<vendor>/api_key` + TTL + 域名白名單 | E3 |
| H-22 | docs/README.md 補 v5.7 + v5.8 主檔 + Sprint 1A dispatch packet + V103/V104 spec + Earn governance spec + 14 audit reports（~11 條）+ Sprint 1A-β/γ/δ/ε 每階段補 ~8-10 條 | R4 / TW |
| H-23 | TODO §0.5 refactor（v5.7 12 prefix DONE 歸檔 §F；v5.8 13 module staging） | R4 / TW |
| H-24 | M4 Tokenomist trial expiry Sprint 6-7 decision deadline（paid subscription vs fallback vendor） | BB |

### MEDIUM/LOW（Sprint 1B-3 should-fix；摘要）

- Cowork review path 純規則 vs LLM 比例（AI-E）；M11 nightly resource budget（24h replay < 4h）（E4）；M9 trial_id hash → server-side seeded random（E3）；M8 → M3 amplification loop cap 1-anomaly = 1-state-change/24h（E3）；M11 replay_divergence_log + M4 hypothesis_drafts GUI viewer reject + Copy Trading export 禁 join（E3）；V105-V116 learning.* table production trading role 禁寫（E3）；C10 Pairs Funding short-only acceptance criteria 5 條（FA）；Earn governance runbook（TW）；GUI Vanilla JS sign-off node --check（W-AUDIT-7c 教訓）；CHANGELOG.md v5.7→v5.8 entry（TW）；CONTEXT.md 12 詞條（TW）

---

## 2. 真實 Sprint 1A 工作內容（α / β / γ / δ / ε 五階段）

### Sprint 1A-α（W0-1.5）— v5.7 12 prefix DONE + 4 follow-up 收口

**狀態**：DONE 2026-05-21 PM signoff（TODO §0.5）；剩 v5.7 4 follow-up
**Workload**：8-12 hr / 4-5 並行 sub-agent / 2026-05-22 內 land
**Deliverable**：
- v57-C3 V103 schema 補 4-5 audit field（lease_id / approval_id / actor_id / bybit_request_payload / rationale）— PA + MIT 5-8 hr
- V### re-number search/replace（V097/V098 catch-up → V099/V100=Track v3 → V101/V102=Earn schema → V103/V104=hypotheses 不動）— PA 30-60 min
- PG connection 範例補 CLAUDE.md + docs/agents/context-loading.md — TW 30 min
- Earn governance 五角色 cross-ref（FA + E3 + QA + MIT 並行；各 1-2 hr）

### Sprint 1A-β（W1.5-3.5）— v5.8 CRITICAL module DESIGN

**Workload**：220-320 hr（v5.8 §3 基數）+ 90-140 hr MIT spec(CR-8 部分)+ TW 35-45 hr + GUI 9-11 hr A3 + 60-90 hr v5.8 ADR draft buffer = **310-460 hr / 5-7 並行 sub-agent / 2 wall-clock weeks**
**Deliverable**：
- M1 Lease Tier (rename → LAL) schema + ADR-0034 + V112 spec doc
- M3 Health domain schema + ADR (R4 建議補) + V106 spec doc（含 hypertable + retention）
- M6 Reward weight schema + ADR (R4 建議補) + V110 spec doc
- M7 Decay (rename → DECAY_ENFORCED) schema + ADR (R4 建議補) + V113 spec doc
- M11 Replay divergence schema + ADR-0038 + V107 spec doc
- ADR-0041 ContextDistiller v4（AI-E + PM）
- AMD-2026-05-21-01 autonomy-vs-human-final-review（CC + PM）
- 5 spec doc (M1/M3/M6/M7/M11)
- 6 runbook draft (M1/M3/M7 + Earn 延續 + Counterfactual 延續 + M11 quality report)
- Cross-ADR collision audit gate（PA + TW 4-6 hr）

### Sprint 1A-γ（W3.5-5.5）— ADD-per-operator module DESIGN

**Workload**：190-290 hr（v5.8 §3 基數）+ TW 35-45 hr + GUI 7-9 hr A3 + V### spec 補 = **240-360 hr / 5-7 並行 sub-agent / 2 wall-clock weeks**
**Deliverable**：
- M2 Overlay state machine schema + ADR (R4 建議補) + V105 spec doc
- M4 Hypothesis discovery schema + V103 EXTEND + ADR (R4 建議補) + M4 leakage protocol + Cowork review path 明示
- M8 Anomaly schema + ADR-0036（GARCH 替換 / 算法明示）+ V109 spec doc
- M9 A/B framework schema + ADR-0037（variant Stage 路徑 + fair execution clause）+ V108 spec doc
- M10 Discovery tier schema + ADR (R4 建議補；Tier D 黑名單 hardening）+ V111 spec doc
- 5 spec doc (M2/M4/M8/M9/M10)
- 2 runbook（M2 / M9）
- Cross-ADR collision audit gate

### Sprint 1A-δ（W5.5-6.5）— interface stubs

**Workload**：58-82 hr（v5.8 §3 基數）+ TW 15-25 hr + GUI 2 hr A3 = **75-110 hr / 3-4 並行 sub-agent / 1 wall-clock week**
**Deliverable**：
- M5 ModelClient trait stub（6 method slots default panic）+ ADR-0035（Y3+ retirement criteria）+ V114 reserved
- M12 OrderRouter trait stub（5 method slots default panic + maker_fill_rate_30d metric）+ ADR-0039 + V115 reserved
- M13 AssetClass + Venue enum（DEX/Hyperliquid hardcode 拒絕）+ ADR-0040（multi-venue gate spec + Y3+ Binance trade enable）+ V116 reserved
- 3 spec doc partial

### Sprint 1A-ε（W6.5-7.5）— integration verify + cross-ADR consistency

**Workload**：60-90 hr（v5.8 §3 40-60 上修）+ TW 20-30 hr + GUI 6 hr A3 = **86-126 hr / single-thread / 1.5-2 wall-clock weeks**
**Deliverable**：
- Cross-ADR consistency audit（11 ADR 跨引用 / AMD-2026-05-21-01 / ADR-0024-lite amend）
- Schema migration ordering audit（V099-V116 sequencing + dependency graph land）
- Mac CI 全 13 module cross-compile verify
- 12 V### dry-run SOP land（per-V twice idempotency + engine restart 實測）
- docs/README.md index 補 46 新文件 + 14 新腳本進 SCRIPT_INDEX.md
- Monthly Operator Review Wizard + Traffic-light + 摺疊規則（A3 16-24 hr）
- Lv 3-4 modal helper 統一（A3 8-12 hr）
- CHANGELOG.md v5.7→v5.8 entry land
- CONTEXT.md 12 詞條補錄

**Sprint 1A 總工時**：670-1,015 + 90-140(MIT spec)+ 450-640(TW)/7 = **~720-1,090 hr 真實**

### Sprint 1A 真實 wall-clock 預測

```
Sprint 1A-α  : W0-1.5  (DONE + 4 follow-up D+1 land)
Sprint 1A-β  : W1.5-3.5 (2 wall-clock weeks; 5-7 sub-agent 並行)
Sprint 1A-γ  : W3.5-5.5 (2 wall-clock weeks; 5-7 sub-agent 並行)
Sprint 1A-δ  : W5.5-6.5 (1 wall-clock week; 3-4 sub-agent 並行)
Sprint 1A-ε  : W6.5-8.5 (1.5-2 wall-clock weeks; single-thread cross-ADR + 全 module verify)
Sprint 1A    : ~8.5w 真實 (v5.8 §3 7w + 1.5w cross-ADR collision risk slip)
```

---

## 3. v5.8 Y1 工時 + 排期上修

### 3.1 工時對照表（v5.8 文本 vs PA 整合後）

| 維度 | v5.8 文本 | PA 整合後 | gap |
|---|---|---|---|
| Sprint 1A engineering | 543-797 hr / 7w | **670-1,015 hr / 8.5w**（含 GUI/TW/MIT buffer）| +127-218 hr |
| Y1 total engineering | 2,780-3,930 hr / 37-44w | **3,500-5,200 hr / 44-55w** | +720-1,270 hr |
| GUI 工時（v5.8 = 0） | 0 | **+261-374 hr Y1** | +261-374 |
| TW 工時（v5.8 = 0） | 0 | **+450-640 hr Y1** | +450-640 |
| MIT spec land 工時 | 0 | **+120-140 hr**（9 V### spec doc） | +120-140 |
| Governance amend buffer | 0 | **+60-90 hr**（4 R4 建議 ADR + 0034/0036/0037/0038/0040 細節）| +60-90 |
| AI LLM cost Y1 | 0 | **$505-865** | +$505-865 |
| AI LLM cost Y2 | 0 | **$1,344-2,556**（DOC-08 月 $60 cap 超 1.9-3.5x）| +$1,344-2,556 |
| A3 sign-off 工時 Y1 | 0 | **+48-53 hr** | +48-53 |

### 3.2 Sprint 1A-10 Y1 真實 sprint 排期

| Sprint | v5.8 文本 wks | PA 整合 wks | 主任務 | hr 真實 |
|---|---|---|---|---|
| 1A (α-ε) | 0-7 | **0-8.5** | v5.7 baseline + 13-module DESIGN + GUI + TW | 720-1,090 |
| 1B | 7-10 | **8.5-11.5** | v5.7 1B + M3/M11 early IMPL + ContextDistiller v4 | 150-200 |
| 2 | 10-13 | **11.5-14.5** | Alpha Tournament + M4 pattern miner stage 1 + M10 Tier A productionize | 240-330 |
| 3 | 13-16 | **14.5-17.5** | Top-1 build + Stage 0 shadow + M11 nightly replay + M3 statistical detectors + M8 read-only | 250-340 |
| 4 | 16-19 | **17.5-20.5** | Top-1 live + Top-2 + Options Stack 1 + M1 LAL 1 IMPL + M9 read-only | 300-410 |
| 5 | 19-22 | **20.5-23.5** | Top-2 live + Top-3 + Options Stack 2 + M3 auto-degradation + M11 hookups | 260-370 |
| 6 | 22-25 | **23.5-26.5** | Top-4 + C13-VRP + Funding short + M12 maker-vs-taker | 260-370 |
| 7 | 25-28 | **26.5-29.5** | Top-5 + Advisory Allocator + M1 LAL 2 + M6 Advisory reward weights | 250-350 |
| 8 | 28-31 | **29.5-32.5** | Decay (M7) IMPL + M4 pattern miner stage 2 + M9 manual A/B + M3 recovery + M8 alerting | 310-410 |
| 9 | 31-34 | **32.5-35.5** | Continue Advisory + Copy Infra build + M12 slicing | 220-310 |
| 10 | 34-37 | **35.5-38.5** | Y1 Review + Copy Trading Evidence Gate + Overlay verdict + M2/M8/M9 Y2 prep + M13 spec | 170-220 |
| **Y1 buffer** | — | **38.5-44 (5.5w buffer)** | cross-Sprint collision + cross-ADR re-amendment + 13 prerequisite emergent | 80-120 |
| **Y1 total** | **37-44w / 2,780-3,930 hr** | **44-55w / 3,500-5,200 hr** | +720-1,270 hr |

---

## 4. 工作流（dispatch chain per module）

### 4.1 DESIGN phase chain

```
PA + (MIT/QC/E5) spec draft
  ↓
TW ADR draft (frontmatter reserve)
  ↓
A3 GUI mockup (Lv 3-4 surface 配 防誤等級 modal)
  ↓
PA + TW cross-ADR collision audit (per stage 4-6 hr)
  ↓
PM signoff DESIGN deliverable
```

### 4.2 IMPL phase chain

```
PA dispatch packet (with §STATE-MACHINE-TEST + §V-MIGRATION-DRY-RUN + §SLA-STRESS + §M9/M4 sub-章節)
  ↓
E1 (Rust + Python) IMPL — 中文注釋 mandate + MODULE_NOTE 4 字段
  ↓
E1a GUI IMPL (Console toggle / dashboard / Monthly Review Wizard)
  ↓
A3 GUI audit (per Lv 3-4 surface; 防誤觸 modal + cooldown + 雙 actor)
  ↓
E2 對抗式 review (per CR-3 / A3+E2 IMPL DONE 強制核驗 per CLAUDE.md §八)
  ↓
E4 regression (pytest + cargo test --workspace tail -5 + cross-language 1e-4 fixture)
  ↓
QA acceptance (Stage gate 對齊 + 灰度事件嚴重度 + Stage 0R replay preflight if applicable)
  ↓
PM signoff IMPL deliverable
```

### 4.3 Y2 activation phase chain

```
M1/M2/M6/M7/M8/M9/M10 5-gate review (per CR-15 auto path inheritance)
  ↓
CC/E3 cross-check (priority 5 vs §11 mitigation boundary per CR-3 AMD-01)
  ↓
PM ADR amendment (per Sprint 10 Y1 review + Copy Trading gate evidence)
```

---

## 5. 並行性 + 跨 module 依賴圖

### 5.1 Sprint 1A-β/γ/δ 並行 sub-agent

| 階段 | 並行 sub-agent | wall-clock |
|---|---|---|
| 1A-α | 4-5 並行 sub-agent + PM hands-on | D+1 collapse |
| 1A-β | **5-7 並行**（PA + MIT + TW + CC + AI-E + E5 + A3 各自 module/spec/ADR）| 2 wall-clock weeks |
| 1A-γ | **5-7 並行**（同上配對 M2/M4/M8/M9/M10）| 2 wall-clock weeks |
| 1A-δ | **3-4 並行**（M5/M12/M13 trait stub 各 1 sub-agent + Mac CI sweep）| 1 wall-clock week |
| 1A-ε | **single-thread cross-ADR + 並行 docs/index/CONTEXT batch** | 1.5-2 wall-clock weeks |

**sub-agent 並行 ceiling**：v5.7 12 prefix DONE 證實 7 並行 + PM hands-on coordination 是 hard ceiling；超 7 並行 → cross-session memory race（per memory `project_multi_session_memory_race`）

### 5.2 13 module 依賴圖（v5.8 §3 沒明畫；PA 補）

```
                  [M11 nightly replay (Sprint 3)]
                  /        |          \
            (input)    (input)      (input)
                 |        |           |
          [M7 decay] [M8 anomaly]  [M1 LAL gate]
          (Sprint 8) (S3 read-only)(Sprint 4/7/Y2)
                |        |           |
            (gate)   (alert)     (auto-approve)
                |        |           |
          [M1 LAL 1] [M3 health]  [M6 weight auto Y2]
          (Sprint 4) (S2/S5/S7)
                            |
                  [M2 overlay state machine (S1A-γ)]
                       |          |
                  (auto-disable Y1)(auto-enable Y2 require M11 + counterfactual)
                       |          |
                  [M8 alert (Y2)] [M9 A/B significance (S4 read-only / S7-8 manual / Y2 auto)]

[M4 hypothesis miner] (S2-3 stage 1, S8 stage 2)
    ⟶ DRAFT (V103 EXTEND)
       ⟶ Cowork+operator review (pure rule + LLM hybrid)
          ⟶ Alpha Tournament (S2)
             ⟶ [M10 Tier B trigger (S8+)]

[M10 Tier A] (Sprint 2 cron productionize) — always on
[M10 Tier B] ← M4 active hook (Sprint 8)
[M10 Tier C] ← AUM > $25k (Y2 Q1-Q2) ← live PnL aggregator (P0-EDGE-1 closed gate)
[M10 Tier D] ← AUM > $50k (Y2-Y3) ← regime auto-classify (NO HMM/GARCH per CR-5)
[M10 Tier E] ← AUM > $100k (Y3+)

[M5 online learning] ← Y3+ AUM trigger + operator opt-in
[M12 routing adaptive] ← Sprint 6 maker-vs-taker / Sprint 7-8 slicing / Y2 cross-venue
[M13 multi-venue] ← Binance trade enable Y3+ at earliest (per CR-4 ADR-0040)
```

### 5.3 Cross-V### 依賴

```
V099/V100 (Track v3) — v5.7 4 follow-up
V101/V102 (Earn schema) — v5.7 4 follow-up
V103/V104 (hypotheses + preregistration) — DONE 2026-05-21 + EXTEND for M4 Sprint 1A-γ
  ↓
V105 (M2 overlay) ─ S1A-γ ← V107 (M11)
V106 (M3 health) ─ S1A-β
V107 (M11 replay div) ─ S1A-β ← V103/V109/V113
V108 (M9 A/B) ─ S1A-γ ← V103
V109 (M8 anomaly) ─ S1A-γ → V112 (M1 LAL)
V110 (M6 reward) ─ S1A-β
V111 (M10 discovery) ─ S1A-γ
V112 (M1 LAL) ─ S1A-β → V113 (M7 decay)
V113 (M7 decay) ─ S1A-β
V114/V115/V116 (M5/M12/M13 reserved) ─ S1A-δ
```

**順序限制**：Sprint 1A-β 必先 land V106/V107/V110/V112/V113，1A-γ 才能 land V105/V108/V109/V111；β → γ 不可重疊（per E5 + MIT 共識）

---

## 6. 跨 audit 衝突解決

| 衝突 | 雙方 verdict | reconcile |
|---|---|---|
| **R4 HOLD vs CC GO** | R4 = 46 新文件 + index 漂移；CC = 16 原則 PASS 10/16 | reconcile = R4 是文檔層 / CC 是治理層；都不阻 thesis；但派發前必補 docs/README + 7 ADR placeholder + AMD-01 |
| **E2 HOLD vs E5 GO** | E2 = 找盲點 ceiling estimate 670-1,490 hr；E5 = 性能/工時 floor estimate 565-1,007 hr | reconcile = E2 是 ceiling；E5 是 floor；PA 整合取中段 670-1,015 hr |
| **TW HOLD vs PA GO** | TW = 工時欄 0；PA = 5-7 並行 sub-agent 可行 | reconcile = TW 是 doc workload；PA 是 engineering；併行 dispatch + TW 工時欄補 §3/§4 |
| **MIT QUESTIONABLE M10 Tier D vs E2 GO** | MIT = HMM 黑名單；E2 = thesis 設計 OK | reconcile = M10 Tier D 算法選擇 ≠ thesis；ADR-0036 + ADR (R4 建議) M10 必明寫「no HMM/GARCH/Markov-switching」 |
| **QC QUESTIONABLE M4 vs FA MATCHED** | QC = false discovery 40-60% / FDR 未控；FA = DRAFT writeback workflow 完整 | reconcile = FA 看 governance 邊界 OK；QC 看 statistical rigor 缺；ADR M4 + spec doc 必補 minimum bar |
| **A3 7.0/10 vs CC GO** | A3 = GUI 工時 261-374 hr 缺；CC = 16 原則 OK | reconcile = GUI 工時補 §3/§4；A3 sign-off gate 列 §12 |
| **AI-E CRITICAL vs E5 GO** | AI-E = ContextDistiller 1,200-1,500 token 撞 L1 SLA；E5 = hot path SLA 13 module 只 M8 邊際 | reconcile = AI-E 是 LLM / E5 是 Rust hot path；ADR-0041 ContextDistiller v4 必立 + token cap ≤ 800 |
| **BB CRITICAL M13 Y2 vs E2 §10 缺 P0** | BB = Binance Y2 trade enable 與 Product Boundary 衝突；E2 = §10 漏 P0-EDGE-1 | reconcile = 二者均 §10 cluster 缺漏；CR-4 + CR-10 必補；M13 Y2 → Y3+ at earliest |
| **QA missing M9 variant Stage 路徑 vs QC M9 mSPRT i.i.d.** | QA = variant promote Stage 不明；QC = i.i.d. 假設違反 | reconcile = 是同 ADR-0037 兩個 cluster；4 variant 類型 × i.i.d. 修正 = 同 spec land |
| **FA missing 3 module (hot-swap/capacity/correlation) vs E2 13 module 依賴撞點** | FA = PM verdict 漏 M3/M6/M7 cross-strategy；E2 = Sprint 7-8 IMPL race | reconcile = FA 是業務 missing；E2 是 engineering race；H-9 處置（defer v5.9 或新增 M14-M16） |

---

## 7. v5.7 → v5.8 銜接（Sprint 1A-α 4 follow-up）

**4 條 v5.7 leftover 併入 v5.8 Sprint 1A-α 末**：

1. V103 schema 補 4-5 audit field（lease_id/approval_id/actor_id/bybit_request_payload/rationale）— PA + MIT 5-8 hr
2. V### re-number search/replace（V097/V098 catch-up → V099/V100=Track v3 → V101/V102=Earn schema → V103/V104=hypotheses）— PA 30-60 min
3. PG connection 範例補 CLAUDE.md + docs/agents/context-loading.md — TW 30 min
4. Earn governance 五角色 cross-ref（FA + E3 + QA + MIT 並行；各 1-2 hr）

**操作 follow-up（v5.7 12 prefix DONE 已決議但不阻 1A-α）**：
- G4 OpenClaw key 發行日（5 min query；Sprint 1B 派發前必驗）— operator
- H2 Console tab 歸屬決策（v5.8 4 tab × 2-4 sub-section per A3 §0.6 規劃）— A3 + PA + operator

---

## 8. PM 仲裁建議

| # | 仲裁項 | 選項 | PA 推薦 |
|---|---|---|---|
| 1 | **M1 Lease Tier 命名**（QA 提 Tier 0-4 vs AMD-01 Stage 0R-4 衝突；QA 建議 LAL；CC 建議 Tier）| (a) 改 LAL（避衝突）/ (b) 保 Tier + 補 LAL ↔ Stage 對齊矩陣 | **(a) LAL** — 避字面衝突 → 派 sub-agent IMPL 時零混淆；3-5 hr search/replace |
| 2 | **R4 6 建議 ADR**（M2/M3/M4/M6/M7/M10 是否補 ADR）| (a) 全補（+48-72 hr TW）/ (b) M2/M3/M7 補（stateful machine 必要）/ (c) M4/M6/M10 合入 0034 / (d) 全 defer | **(b) M2/M3/M7 補 + M4/M6/M10 合入 0034 / 0036**（混合方案）— stateful machine 必有 ADR；其他合 0034 covers |
| 3 | **AMD-2026-05-21-01 autonomy-vs-human-final-review**（CC 提）| (a) 立 AMD / (b) ADR-0024-lite amend / (c) ADR-0034 covers | **(a) 立 AMD** — 因涉跨多 ADR（0034/0040 + ADR-0024-lite）; AMD 更符合 priority order 級別 |
| 4 | **M13 Y2 vs Y3 Binance trade enable**（BB push back Y2 → Y3+ at earliest；衝突 Product Boundary）| (a) Y2 keep（override Product Boundary + 補 ADR-0041 + 5-gate 重審）/ (b) Y3+ at earliest（保 Product Boundary）| **(b) Y3+ at earliest** — Product Boundary 是 CLAUDE.md §一 hard；override 風險高；BB advisory verdict 直接適用 |
| 5 | **M10 Tier D regime auto-classify 模型**（QC 黑名單 HMM/GARCH/Markov-switching；MIT 推薦 change-point detection / Markov-switching regression 不含 HMM）| (a) ATR-vol + funding state 雙 axis（QC 推薦）/ (b) PELT change-point（MIT 推薦）/ (c) 二者 ensemble | **(a) ATR-vol + funding state**（Y1-Y2 簡單可行）+ Y3+ 再 evaluate PELT — 兩者列 ADR-0036 + ADR (M10 R4 建議)；Tier D 真 active 已 Y2-Y3 |
| 6 | **GUI 工時 +261-374 hr** 是否補位 §4 + §12 | (a) 補 §4 / (b) §4 不動 / 註明 GUI 工時 outside engineering hours | **(a) 補 §4** — A3 sign-off + Console tab 歸屬 都依賴 §4 hours visibility |
| 7 | **TW 工時 +450-640 hr** 並行 dispatch（§12 第 5 條 operator decision）| (a) 並行 dispatch 加入 §12 / (b) TW 寫在 §4 註腳 / (c) TW 在 Sprint 1A-ε 集中 | **(a) 並行 dispatch + §12 第 5 條** — TW workload 14-17% 系統性，集中無法消化 |
| 8 | **AI cost $1,344-2,556 yr Y2** vs DOC-08 $60 cap | (a) cap 升 $200-300/月（接受超 cap）/ (b) M4/M11 narrative 砍頻率（L1 only / weekly digest）/ (c) Y2 Q1 重評 | **(b) 砍頻率 + Y2 Q1 重評** — 短期降 cost 5-10x；Y2 evidence 後 operator 自決定 |
| 9 | **Sprint 1A wall-clock 7w vs 8.5w** | (a) 8.5w（cross-ADR collision risk 1.5w slip 接受）/ (b) 7w（操作 60-70% parallel hard mandate） | **(a) 8.5w** — 7 並行 sub-agent ceiling + cross-ADR audit single-thread |
| 10 | **3 PM verdict missing module** (M3 hot-swap / M6 capacity / M7 correlation) | (a) defer v5.9 + ETA / (b) 新增 M14-M16 immediate / (c) M1+M6 擴 scope | **(a) defer v5.9 + ETA** — v5.8 已含 13 module；M14-M16 變動範圍太大；Sprint 10 Y1 Review 時 evaluate |

---

## 9. 真實 Sprint 1A-β 派發 readiness verdict

### 9.1 派發前 prerequisite check list（13 項；2026-05-22~5-26 內 land）

| # | Item | 工時 | Owner | Deadline |
|---|---|---|---|---|
| 1 | **v5.7 4 follow-up 完成** | 8-12 hr | PA + MIT + TW + FA + E3 + QA | D+1 (2026-05-22) |
| 2 | **CR-2 M1 Lease Tier → LAL 改名 + ADR-0034 spec** | 12-18 hr | PA + CC + QA | D+2 |
| 3 | **CR-3 AMD-2026-05-21-01 land** | 4-8 hr | PM + CC | D+2 |
| 4 | **CR-4 ADR-0040 multi-venue gate spec**（含 M13 Y2 → Y3+ 措辭） | 6-10 hr | TW + BB + E3 | D+3 |
| 5 | **CR-5 M10 Tier D 黑名單 hardening + ADR-0036 GARCH 替換** | 4-6 hr | TW + MIT + QC | D+3 |
| 6 | **CR-6 M4 minimum bar + leakage protocol** | 5-8 hr | MIT + PA | D+3 |
| 7 | **CR-7 M11 threshold derivation + M7 dedup + DECAY_ENFORCED 改名** | 4-6 hr | MIT + QC | D+3 |
| 8 | **9 V### spec doc reserve placeholder + dispatch 規劃**（V105-V113 spec land 在 1A-β/γ 各週逐個推進；先 reserve frontmatter） | 3-5 hr placeholder + 90-140 hr full spec across 1A-β/γ | MIT + PA + E5 | D+3 reserve / 1A-β/γ full |
| 9 | **CR-10 §10 加 P0 precondition table + §12 第 5 條** | 2-4 hr | PM | D+3 |
| 10 | **CR-11 GUI 工時 + Console tab 歸屬 + A3 sign-off invariants 寫入 §3/§4/§12** | 3-5 hr | PM + A3 | D+3 |
| 11 | **CR-12 TW 工時寫入 §3/§4/§8/§9/§12（第 5 條 operator decision）** | 2-3 hr | PM + TW | D+3 |
| 12 | **CR-13 Sprint 1A 工時 + Y1 total 上修；§3/§4/§14 三處時間統一** | 1 hr | PM | D+3 |
| 13 | **CR-16 ADR-0041 ContextDistiller v4 + DOC-08 cap 重估** | 6-10 hr | AI-E + TW + PM | D+4 |

**Prerequisite 合計**：~60-105 hr / 4-5 wall-clock days / 5-7 並行 sub-agent

### 9.2 派發後並行補（H 級；24 條；Sprint 1A-β-ε 期內 land）

詳見 §1 HIGH list。重點：
- §STATE-MACHINE-TEST + §V-MIGRATION-DRY-RUN + §SLA-STRESS + §M9/M4 sub-章節（E4）
- 13 module sibling file 預先拆（E5）
- Apple Silicon CI 全 13 module（E5）
- docs/README + SCRIPT_INDEX + CONTEXT.md（R4 + TW）
- IPC schema 增量清單（QA + E4）
- Cross-language 1e-4 fixture harness（E4）

### 9.3 Sprint 1A-β 派發前 final go/no-go

**GO 條件**：13 prerequisite 全 land + PM 仲裁 10 條全簽 + operator decision 5 條全簽（v5.8 §12 第 1-5）

**No-go 條件**：13 prerequisite 任一未 land / PM 仲裁 #1-#5 未決定 / operator decision 任一未簽

---

## 10. PA 結論

**Verdict**：**DISPATCH-NEEDS-FIX**

**核心結論**：
1. v5.8 13-module thesis 14 audit 全 0 NO-GO（8 GO / 3 conditional HOLD），thesis 邏輯設計通過
2. 3 HOLD 全部屬文檔/治理/工時補位類別（非設計缺陷），D+5~D+10 內可清
3. 共識 must-fix 去重 16 CRITICAL + 24 HIGH；CRITICAL 工時集中 13 prerequisite check list（~60-105 hr）
4. v5.8 系統性偏低 工時 20-43%（Sprint 1A 543-797 → 670-1,015 / Y1 2,780-3,930 → 3,500-5,200 hr）+ 漏 GUI/TW/MIT spec/A3/AI cost
5. v5.7 12 prefix DONE + v5.8 銜接通過 1A-α 4 follow-up 自然合併
6. 5 並行 track 升級為 1A-β/γ/δ 5-7 並行 sub-agent + 1A-ε single-thread cross-ADR + 8.5w wall-clock
7. v5.8 §3 沒畫的 13 module 依賴圖 + cross-V### sequencing + IMPL wave race 已補
8. AI cost Y2 預估 $1,344-2,556 超 DOC-08 月 $60 cap 1.9-3.5x；ContextDistiller v4 ADR-0041 必立
9. M13 Y2 → Y3+ at earliest（CR-4 / 仲裁 #4 採 BB push back）+ M10 Tier D HMM 黑名單（CR-5 / 仲裁 #5 採 ATR-vol + funding state）
10. 13 prerequisite 完成 D+5~D+10 內 → Sprint 1A-β 派 PA dispatch；首次 Live 落 Sprint 4（W17.5-20.5）受 P0-EDGE-1 + P0-LG-3 + P0-OPS-1..4 4 條 active P0 阻塞（必先解或 LiveDemo 降級 per CR-10）

**派發 readiness verdict**：DISPATCH-NEEDS-FIX；13 prerequisite + PM 仲裁 10 條 + operator decision 5 條 完成後 D+5~D+10 內可派 Sprint 1A-β。

---

**END v5.8 PA dispatch consolidation**

**PA DESIGN DONE**: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md
