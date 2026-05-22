# 12 ADR + 1 AMD Batch Sign-off Highlight Sheet

**日期**：2026-05-21
**用途**：operator D+5 batch sign 用（目標 30 min 完）
**作者**：TW
**範圍**：ADR-0030 ~ ADR-0041 + AMD-2026-05-21-01

---

## Summary Table

| ID | 標題短 | 建議 | 重點看 |
|---|---|---|---|
| ADR-0030 | Copy Trading Y1 末 4-Gate evidence evaluation | APPROVE | no |
| ADR-0031 | Earn + Macro + On-chain 三 framework expansion | APPROVE | no |
| ADR-0032 | Bybit Earn Asset Movement 5-Gate Guardian + Decision Lease retrofit | APPROVE | no |
| ADR-0033 | ADR-0006 amendment：Binance market-data Y1 + Y2 trade defer + DEX/Hyperliquid NOT approved + D12 80% cap | APPROVE | **YES** |
| ADR-0034 | M1 Decision Lease Layered Approval (LAL) 0-4 — 改名避 Stage 字面碰撞 + 6 條 auto-approve hard gate | APPROVE | **YES** |
| ADR-0035 | M5 Online Learning interface reserved — trait stub + V114 placeholder + Y3+ activation 6 條件 | APPROVE | no |
| ADR-0036 | M8 Anomaly + M10 Tier D — HMM/Markov-switching/GARCH 永久黑名單 + ATR-vol × Funding-state 9 cell 替代 | APPROVE | no |
| ADR-0037 | M9 A/B Framework — 4 variant cluster + mSPRT + Always-Valid Inference + Bonferroni 校正 | APPROVE | no |
| ADR-0038 | M11 Continuous Counterfactual Replay — Self-hosted PG `market.liquidations` 唯一 historical source | APPROVE | no |
| ADR-0039 | M12 OrderRouter trait — 加 `maker_fill_rate_30d` 第 6 method + V115 audit log schema | APPROVE | no |
| ADR-0040 | M13 Multi-Venue Gate — Binance trade enable Y2 → Y3+ at earliest（ADR-0033 §Decision 2 timing amendment） | APPROVE | **YES** |
| ADR-0041 | ContextDistiller v4 — 800 token hard cap + DOC-08 §4 Y1 $60 / Y2 opt-in $150-200 cap amendment | APPROVE | no |
| AMD-2026-05-21-01 | Autonomy vs Human Final Review — protected scope 6 條（永不可 auto）+ opt-in scope 8 條 | APPROVE | **YES** |

**總計**：12 ADR + 1 AMD = 13 件
**建議分布**：APPROVE 13 / VETO 0 / DEFER 0
**重點看**：4 件（ADR-0033 / ADR-0034 / ADR-0040 / AMD-2026-05-21-01）

---

## ADR-0030：Copy Trading Activation — Y1 末 4-Gate Evidence Evaluation, Y2 Enablement Conditional

**Key decision**:
- Y1 嚴禁任何 Copy Trading 對外行為（不註冊 master / 不招募 follower / 不收 take fee / 不 build infra）
- Sprint 10 W36-39 走 4-Gate evaluation（Alpha / Governance / Infrastructure / Regulatory），任一 fail → defer 90d 重評
- 4 Gate 全 PASS → Y2 Copy Trading infra build phase enable；Y2+ 細節留待 PASS 後新 ADR

**衝突 / cross-dep**:
- Sprint 10 evaluation window 與 ADR-0031 Macro / On-chain Y1 末 evaluation 共用（運維集中），與 ADR-0040 Binance trade Y3+ at earliest 不衝突
- 對齊 ADR-0006 Bybit-only baseline + ADR-0033 DEX/Hyperliquid NOT approved（Copy Trading 只在 Bybit 平台內）

**反向 attack**:
- 「4 gate 設計嚴格永遠 enable 不了」風險 → mitigation：連續 2 cycle FAIL 觸發 ADR-0030 amendment 重審 threshold（非繼續執行）
- Sprint 10 W36-39 evaluation 工作量 30-50 hr 三方 review → mitigation：Sprint 9 100-140 hr 預備 evidence pipeline + dashboard

**建議**：APPROVE — 4 Gate 正交設計 + Y1 strict prohibition + 延後機制 + 與 v5.7 §1 honest Y1 income（不算 Copy Trading）對齊；evidence-gated 紀律無漏洞

---

## ADR-0031：Framework Expansion — Earn Governance + Macro Counterfactual + On-Chain Counterfactual

**Key decision**:
- 三 framework 同時鎖入「數據接入 ≠ production trigger」紀律：Earn API APR query / Macro counterfactual / On-chain counterfactual
- Y1 income 邊界：Earn $26（real income）/ Macro $0（counterfactual only）/ On-chain $0（counterfactual only）
- Sprint 10 W36-39 三 framework + Copy Trading 共用 evaluation window；任一 marginal/null → retire layer

**衝突 / cross-dep**:
- Earn asset movement Guardian 細節拆到 ADR-0032（執行複雜需獨立 ADR）
- Macro / On-chain counterfactual A/B framework 共享 15-20 hr（避免重複開發）
- Sprint 1A Earn API 工時 45 hr 占 Sprint 1A/1B 主要工程，可能阻塞其他 sensor

**反向 attack**:
- Macro 事件 Y1 樣本量可能太小（FOMC 8 次 + CPI 12 次）無法判定 alpha → mitigation：evaluation 加 MARGINAL verdict option
- Sprint 10 evaluation window 集中 4 個 framework decision 工作量大 → mitigation：Sprint 9 預備

**建議**：APPROVE — 三 framework 統一治理紀律 + 「數據接入 ≠ trigger」紀律避免漂移 + 失敗默認 retire 避免 sunk cost

---

## ADR-0032：Bybit Earn Asset Movement Guardian — 5-Gate Adapter + Decision Lease Retrofit + Audit Log

**Key decision**:
- Earn stake/redeem 走 5-gate adapter（Authorization / Risk envelope / Decision Lease / Execute / Audit），對齊既有 Five-Gate baseline
- Decision Lease retrofit 加 `unstake_pending` state；lease ID format `lease_earn_<product>_<direction>_<ts>`；TTL min-hr 級
- Manual first 3 months（Sprint 1B-4）強制 manual；Sprint 4 結束 evaluation 5 sub-criterion PASS → Sprint 5 開 auto-redeem (margin < 30% trigger)

**衝突 / cross-dep**:
- ADR-0031 Framework 1 §1.2 細節拆分點；父框架對齊
- ADR-0008 Decision Lease retrofit ~8-10 hr，可能引入 existing trading lease regression → mitigation：E2 review + E4 regression test 強制
- 與 ADR-0033 D12 cap 80% 互補（兩個獨立 threshold 運作）

**反向 attack**:
- Sprint 4 結束 evaluation threshold 接近邊界時主觀 → mitigation：MARGINAL verdict 自動延後 Sprint 6-7 重評
- Auto-redeem 24h cooldown 3 次可能不夠 → mitigation：cooldown 後仍 margin 不足 → Operator manual escalation

**建議**：APPROVE — Earn 接入完整 Guardian 防線 + manual first 3 months 紀律驗證 + 5-gate adapter 可重用於未來 asset-write framework

---

## ADR-0033：ADR-0006 Amendment — Binance Market-Data + Trading Defer Y2 + DEX/Hyperliquid NOT Approved + D12 + ToS Posture

**重點看 YES**：這是 ADR-0006 唯一 amendment，且 Decision 2 時點被 ADR-0040 進一步 amend 為 Y3+ at earliest；理解此 ADR + ADR-0040 串聯邏輯是 venue gate 治理核心。

**Key decision**:
- Decision 1：Binance market-data only approved Y1（cross-venue analytics + counterfactual）；trading endpoint 全禁
- Decision 2（被 ADR-0040 amend）：Y2 Binance trading defer pending evaluation；4 條件 (a)(b)(c)(d) 全 PASS 才 enable
- Decision 3：DEX / Hyperliquid Y1+Y2 baseline **NOT approved**（proactive lock-down 避免「不提到 ≠ 不允許」漂移）
- Decision 4：D12 cap = Bybit total exposure（trading + Earn）≤ 80%；剩 20% 保 Revolut/Wise off-exchange emergency liquidity

**衝突 / cross-dep**:
- ADR-0006 thesis 不變（baseline 仍 Bybit-only）；本 ADR 為 amendment standalone
- ADR-0040 進一步 amend §Decision 2 timing（Y2 → Y3+ at earliest）；§Decision 1/3/4 保留
- 與 ADR-0032 D12 cap 互補（Earn stake + trading exposure 跨計）

**反向 attack**:
- Binance WS 即使 market-data only 仍引入新 surface（API key / ws reconnect / rate limit）→ mitigation：Sprint 1A E1 對齊既有 Bybit WS pattern + Binance-specific 走獨立 module 不污染 `bybit_*`
- D12 80% cap 對 trading allocation 形成上限，Earn + trading 接近 80% 時 auto-redeem 頻繁 → mitigation：與 ADR-0032 auto-redeem trigger（margin < 30%）是兩獨立 threshold，互補不衝突
- 「Binance trading defer Y2 但 Y1 market data 已接入」frustration → 設計上是 evidence accumulation 一部分

**建議**：APPROVE — Bybit-only thesis 不變 + 明示 DEX/Hyperliquid not approved + D12 single-venue freeze risk 保護 + 與 v5.7 §1 honest income 對齊；amendment pattern 對齊 ADR governance（不取代 ADR-0006）

---

## ADR-0034：M1 Decision Lease Layered Approval (LAL) — Autonomous Proposal-to-Execution Loop

**重點看 YES**：此 ADR 是 v5.8 §2 M1 module ADR 級落地核心 + 命名重大決策（避字面碰撞 Stage 0R-4），影響 Sprint 1A-β 6 子 ADR / 多個 V### schema dispatch；6 條 auto-approve hard gate + LAL ↔ Stage 對齊矩陣 + 24h undo + default-OFF + 2FA + per-decision lease emit + Decision 6 M7 RETIRED blocker 等多項硬約束 land 為 single source。

**Key decision**:
- **改名**：Lease Tier 0-4 → **Layered Approval Lease (LAL) 0-4**（避 AMD-2026-05-15-01 Stage 0R-4 字面碰撞）
- 6 條 Auto-approve hard gate：≥30 prior approvals + 80% rolling 30d yes-rate + 90d incident-free + risk envelope check + Console opt-in default-OFF + 24h undo
- Decision 1：LAL 1+2 auto-approve **仍 emit per-decision lease**（反模式禁止：aggregate counter only）
- Decision 5：24h undo scope = **config + risk envelope only**；fills 已成交不可逆
- Decision 6（R4 NEW-M-3 patch）：M7 RETIRED → LAL Tier 0 fill **MUST fail-closed**（即使 LAL 4 operator override 也禁用，僅 Stage 0R re-promotion 路徑可恢復）

**衝突 / cross-dep**:
- ADR-0008 baseline 不變（emit / sign / settle / replay / Guardian gate 全保留），本 ADR 是擴展
- 與 ADR-0037 M9 variant promotion 走 LAL 3 / ADR-0035 M5 Y3+ activation 走 LAL 4 / ADR-0044 M7 single decay authority 等多 ADR 對齊
- V112 schema spec（CR-8 pending）必 cite 本 ADR；schema 必含 `lal_level` + `lal_pre_proposal_config_snapshot` + `lal_toggle_audit`
- 搜尋取代 cost 30-60 min（v5.8 §2 / §3 / §7 / §9 / §11 / §12 內所有「Tier」需改「LAL」）

**反向 attack**:
- LAL 1 Sprint 4 IMPL 在 Stage 4 stable 紀律未明示前可能誤觸發 → mitigation：Sprint 4 dispatch 要求 E1 cite Decision 5 gate criteria；Stage 4 stable 定義「30d window 內無 5-gate kill / Guardian block」
- rolling 30d window 對新策略不公（min N=30 Y1 早期可能 60-90d 才達標）→ by design，autonomy 升級必須有足夠樣本不為「快」放寬
- 24h undo 邊界（fills 不可逆）需 Operator 認知到位 → mitigation：Console undo button hover tooltip + Slack notification 明示「fills already executed cannot be undone」

**建議**：APPROVE — 命名零字面碰撞 + 6 條 hard gate 五層保護（hard gate + opt-in + undo + lease emit + audit）+ ADR-0008 baseline 不變 + Decision 6 對齊 ADR-0044 M7 single authority

---

## ADR-0035：M5 Online Learning Interface Reserved — Trait Stub + V114 Placeholder, IMPL Deferred Y3+

**Key decision**:
- Sprint 1A-δ 只交 `ModelClient` trait stub（6 method default panic）+ V114 reserved placeholder（不寫 DDL）+ `streaming_enabled` BOOL DEFAULT FALSE column
- IMPL Y3+ 6 條件 AND gate：(a) daily-batch 不足 + (b) AUM > $50k + (c) operator opt-in + (d) M9 GA + (e) Live PnL 3 month > 0 + (f) baseline Sharpe > X
- Retirement criteria：R1 Y3 末未觸發 → dead-code removal + Supersede ADR；R2-R4 替代條件

**衝突 / cross-dep**:
- 同 Sprint 1A-δ deliverable 與 ADR-0039 M12 / ADR-0040 M13（同 interface-reservation pattern）
- 不取代既有 LightGBM / Optuna / 3DL daily-batch（M5 是「baseline 之上加層」）
- (d) 條件依賴 ADR-0037 M9 GA；無循環依賴

**反向 attack**:
- trait 死碼 Y1~Y3 約 6 method panic → mitigation：sibling panic test 5 case + retirement audit cadence Sprint 10 / Y2 Q4 / Y3 Q2 三輪
- V114 reserved number 佔位 Y1~Y3 不用 → schema number planning 紀律（避免 Y3+ 才分配撞既有 V### number）

**建議**：APPROVE — 8-12 hr stub cost vs 避免後續 schema breaking change；6 條件 AND gate 對齊 §二 原則 6 失敗默認收縮；Decision 4 retirement audit cadence 防永久債

---

## ADR-0036：M8 Anomaly + M10 Tier D — HMM/Markov-switching/GARCH 永久黑名單 + ATR-vol × Funding-state 9 cell 替代

**Key decision**:
- Decision 1（核心）：**HMM (含 HSMM/HHMM/Factorial HMM) / Markov-switching regression / GARCH (含 EGARCH/TGARCH/IGARCH/FIGARCH/Multivariate GARCH) 任何 module 永久禁用**（math-model-audit skill 黑名單 promote 為 ADR 級強制 grep gate）
- M8 Vol regime shift 用 **Rolling realized vol percentile (RV pct)** 替代「GARCH break」字眼
- M10 Tier D regime auto-classify = **ATR-vol × Funding-state 雙 axis 3×3 = 9 cell 矩陣**（3 級 LOW/MID/HIGH × CONTANGO/NEUTRAL/BACKWARDATION）
- Decision 4：threshold 不寫死 magic number → block bootstrap 估計 + ArcSwap 熱更新
- Y3+ ADR-debt：PELT change-point detection evaluation（OOS 21d 累積 +1% alpha 才觸發 amendment）

**衝突 / cross-dep**:
- math-model-audit skill 為 source of truth，本 ADR 為 governance promotion；任何未來新增黑名單方法 先 amend skill → 再 amend 本 ADR
- 對齊 walk-forward-validation-protocol skill（block bootstrap + OOS 驗證 SOP）
- V109 anomaly_events table + V111 discovery_tier_config table 必 cite 本 ADR

**反向 attack**:
- ATR-vol + funding 雙 axis 數學上不如 HMM elegance（無 state transition probability matrix）→ mitigation：M11 nightly replay 驗 actual edge（真實 test 是 PnL 不是數學優雅）+ Y3+ PELT evaluation 是 amendment hedge
- 3×3 = 9 cell 在 Y1 樣本量下 cell sample 可能不均勻（MID-NEUTRAL > 50%）→ mitigation：Decision 3.1 cell stability metric 7d 統計 warning + cell sample < 30 觸發 fallback strategy allocation
- Decision 1「無例外」可能與未來 corner-case 衝突 → mitigation：amendment 路徑明確 + 例外段允許 read-only counterfactual

**建議**：APPROVE — math-model-audit skill 黑名單在 ADR 級永久強化 + ATR-vol+funding 是 crypto perp 微結構天然 feature + 9 cell 每 cell 人類可解讀 + Harvey-Liu-Zhu replication crisis 警覺降低

---

## ADR-0037：M9 A/B Framework + Statistical Methodology — 4 Variant Cluster + mSPRT i.i.d. 修正

**Key decision**:
- 4 variant cluster 重整（治理 taxonomy 而非 test type）：Cluster 1 parameter sweep (LAL 1) / Cluster 2 signal source swap (LAL 2) / Cluster 3 risk profile (LAL 2) / Cluster 4 exit logic (LAL 1)
- Decision 2：variant 與 control **共享 5-gate Stage 0R→4 graduated canary**（不繞 promotion 紀律）；variant promotion to Stage 4 走 LAL 3 operator approval
- Decision 4：**mSPRT + Always-Valid Inference (AVI, Howard et al 2021) + Bonferroni 校正**（修正 mSPRT i.i.d. 假設違反 + 多重比較 Type I inflation）
- Decision 5：Fair execution clause — 同 lease bucket / 同 LAL Tier / 同 budget cap / 同 Guardian gate（variant 不能偷跑）

**衝突 / cross-dep**:
- V108 三表（ab_tests + ab_assignments + ab_results）spec 必 cite 本 ADR
- Cluster 2 signal source swap 依賴 M4 land（Sprint 7-8 IMPL）
- 對齊 quant-strategy-design + time-series-cv-protocol skills；Decision 4 反模式 (e) 引用 ADR-0036 黑名單適用 M9 variance structure 估計
- Decision 6：Sprint 4 first Live A/B 啟用必先通過 v5.8 §10.5 P0 precondition（4+1 條）

**反向 attack**:
- cohort 切片成本 /2 ~ /4 對 single-strategy Sharpe noise 上升 → mitigation：min_sample_size_per_arm 從 power analysis derive 不從 magic number 設
- Bonferroni 100+ test α=0.0005 可能 power < 0.5 → mitigation：FDR (Benjamini-Hochberg) 替代為 amendment 選項 + 限制並行 test 數
- mSPRT validation harness 1000+ simulation Sprint 1A-γ 50-70 hr budget 緊 → mitigation：harness 推 Sprint 1A-γ 末 + Sprint 3 一起 land

**建議**：APPROVE — QA + QC 5.21 兩 push back（variant Stage 路徑 + mSPRT i.i.d.）一次性 reconcile + 4 cluster 分類紀律 + statistical methodology 對齊 crypto perp 微結構 + fair execution clause 對齊 §二 原則 4

---

## ADR-0038：M11 Continuous Counterfactual Replay — Self-Hosted PG `market.liquidations` As Historical Source

**Key decision**:
- Decision 1：M11 nightly replay 任何 historical `market.*` query **限制 self-hosted PG**（禁依賴 vendor API / 第三方 SaaS / cross-exchange historical）；對齊 §二 原則 14 零外部成本 baseline
- Decision 2：默認 replay window 24h；> 24h 必經 LAL 2 approval（per ADR-0034）
- Decision 3：3 級 statistical threshold（5d empirical mean + 0.5σ NOISE / +2.5σ WARN / +3σ CRITICAL）；CRITICAL → emit M7 input（**不 auto-demote** per CR-7 dedup contract M7 為 single decay authority）
- Decision 5：4h wall-clock budget；Mac 不跑 full replay；連續 7d 超 budget → operator 仲裁 decision matrix

**衝突 / cross-dep**:
- BB 5.21 audit push back 「Bybit historical liquidations REST API 不存在」落地
- 對齊 ADR-0029 trade tape policy（fidelity uplift）+ ADR-0017 scanner-is-evidence-not-authority（sourcing posture）
- V107 `learning.replay_divergence_log` schema 候選；待 CR-7 finalize
- 與 V109 anomaly schema dedup（OQ-4）

**反向 attack**:
- Cold start 期 baseline < 5d → mitigation：OQ-1 cohort-level baseline fallback + degraded warn flag
- `market.liquidations` WS subscription 未 production enabled（W-AUDIT-8a C1 PASS 後啟動）→ mitigation：M11 first nightly run 在 C1 PASS 後啟動，本 ADR 不阻塞 C1 timeline
- 4h budget 在 Y2 strategy cohort 擴張下可能超 → mitigation：§Decision 5 升級條件

**建議**：APPROVE — M11 不押 vendor optionality + self-hosted PG 數據累積路徑明確（BB C6 PROOF PASS 31,473 rows 已驗）+ CR-7 dedup紀律落地（M11 sensor / M7 actuator）+ Statistical 3σ threshold derivation 非 ad-hoc

---

## ADR-0039：M12 OrderRouter Trait — Maker-Fill-Rate Metric + Adaptive Routing Audit Schema

**Key decision**:
- OrderRouter trait 6 method（v5.8 initial 5 + **NEW `maker_fill_rate_30d`**）：route_order / venue_health / cross_venue_position / forecast_slippage / reverse_snipe / maker_fill_rate_30d
- Decision 2：`maker_fill_rate_30d` rolling 30d × per-venue × per-asset-class；分子 = maker fill notional / 分母 = total fill notional；對齊 Bybit rebate tier table（T1 ≥ 80% / T2 ≥ 70% / Default ≥ 50%）
- Decision 3：V115 三表（order_routing_decisions + maker_fill_rate_30d_snapshots + routing_tier_transitions）
- Decision 4：reverse-snipe defense — 預設 PostOnly maker；切 taker 觸發條件 signal confidence ≥ 0.7 + market direction confirmed within 200ms
- Decision 5：bounds + LAL 3 protection — 越單 order $500 cap 或 slippage tolerance → require operator confirm + LAL 3（per ADR-0034）

**衝突 / cross-dep**:
- BB 5.21 audit push back「maker_fill_rate_30d metric 缺失 → silent rebate tier degradation」落地
- 計算數據源依賴 ADR-0029 trade tape + V094 既有 `close_maker_attempt` column
- 對齊 crypto-microstructure-knowledge skill rebate tier 對照表 + PostOnly fee 計算
- 與 V107（M11）dedup（OQ-4）

**反向 attack**:
- 新 venue 接入後 30d 期內 tier 不可用 → mitigation：OQ-3 cold start fallback enum (Unknown / Provisional / full classification)
- In-memory ring buffer 與 PG snapshot 一致性（actor restart 後 rebuild） → mitigation：OrderRouter actor lifecycle 包含 ring buffer rebuild step
- Bybit fee schedule revision → mitigation：OQ-1 BB Sprint 6 IMPL 期 confirm + revision 走 ADR-0033 amendment

**建議**：APPROVE — Bybit ToS rebate eligibility 持續監控 first-class metric + cost edge 結構性保護（避免 silent loss）+ Sprint 1A interface stub 避免下游 drift + 與 ADR-0033 §4.2 ToS posture trait-level 對應

---

## ADR-0040：Multi-Venue Gate Spec — M13 Binance Trade Enable Defer Y3+ At Earliest

**重點看 YES**：此 ADR amend ADR-0033 §Decision 2 timing（Y2 → Y3+ at earliest）；與 ADR-0033 共同構成 venue gate 完整治理鏈；新增 per-venue 5-gate schema + 6 條 evaluation gate criteria + venue enum hardcode 拒絕 DEX/Hyperliquid + per-venue authorization 三元組綁定。

**Key decision**:
- Decision 1：Binance trade enable 時點 **amend Y2 → Y3+ at earliest**（最早 Y3 Q1 evaluation；Y2 期間 Binance 仍 market-data only per ADR-0033 §Decision 1 不變）
- Decision 2：Per-venue 5-gate schema — Gate 4 secret slot per-venue path（Bybit 走原 / Binance 走 `external/binance/api_key`）；Gate 5 authorization.json 新加 `venue` field（默認 `'bybit'`）
- Decision 3：Y3+ enable gate **6 條 AND**（ADR-0033 4 條 + 新加 (e) Y2 末 Copy Trading evidence land + (f) AUM ≥ $50k sustained 30d）
- Decision 4：Rust `Venue` enum hardcode 拒絕 DEX/Hyperliquid（不留 enum slot 從根源編譯期 fail-closed）
- Decision 5：Per-venue authorization 三元組綁定（venue + environment + secret slot）+ venue change 永遠走 LAL 4

**衝突 / cross-dep**:
- ADR-0033 §Decision 1（Binance market-data Y1 approved）/ §Decision 3（DEX/Hyperliquid not approved）/ §Decision 4（D12 + ToS posture）**全部保留**；只 amend §Decision 2 timing
- 對齊 ADR-0034 LAL 4 venue change always operator approve + AMD-2026-05-21-01 protected scope (a)
- (e) 條件依賴 ADR-0030 Copy Trading evidence land；(f) 依賴 v5.8 §5 capital-tier ladder Y3 Q2 estimate

**反向 attack**:
- v5.8 §2 M13 文本 + §5 capital-tier ladder + §6 autonomy estimate 需同步更新 → mitigation：主會話 v5.8 主檔 update 時 cite 本 ADR
- (a) 12-18 months sustained alpha 可能 evidence base 仍不足（Y1 Live W17.5 起始實際 sustained window ≈ 18-20 months）→ mitigation：若 (a) inconclusive 繼續 defer 至 Y3 末或 Y4
- (f) AUM ≥ $50k 門檻可能延遲 Binance trade enable 至 Y3 Q3-Q4 → by design (evidence-gated 延遲是設計意圖)

**建議**：APPROVE — ADR-0033 4 條件不夠 robust 風險化解 + Y3+ at earliest 給 Y1+Y2 累積足夠 evidence + per-venue 5-gate schema 對齊 H-21 external secret slot policy + venue enum hardcode 編譯期 fail-closed + 與 ADR-0034 LAL 4 對齊

---

## ADR-0041：ContextDistiller v4 — Layered Snapshot + Token Hard Cap + DOC-08 §4 AI Cost Cap Amendment

**Key decision**:
- Decision 1：三層 layered snapshot — L0 always-inject ≤ 400 token / L1 task-conditional ≤ 200 token / L2 per-request dynamic ≤ 200 token；**累計 hard cap ≤ 800 token / 推理**
- Decision 2：800 token hard cap enforcement（9B P50 ~2.5s 安全 / P95 ~4.5s 邊際；不靜默截斷 prompt）
- Decision 3：Statistical-only fallback path — 4 觸發條件（token cap / LLM 5xx / SLA breach 5 次 / 月度 cost > 80%）
- Decision 4：DOC-08 §4 amendment — **Y1 cap $60 / 月**（default）/ **Y2 conditional opt-in $150-200 / 月**（走 LAL 4 operator approval + 5 項 evidence packet）
- Decision 5：M4 Cowork review 純規則 + LLM hybrid 明示（pattern miner stage 1/2 純規則 / LLM 只 narrative summary 不 ranking / Y2 active ≤ 20-30 DRAFT 月）
- Decision 6：M11 narrative L1-first cadence（daily L1 = $0 / per-divergence L2 只在 CRITICAL/HALT；INFO/WARN 走 L1 template）

**衝突 / cross-dep**:
- AI-E 5.21 v5.8 audit must-fix 第 1 條 + PA 仲裁 #8 (b)「砍頻率 + Y2 Q1 重評」核心執行落地
- ADR-0027 (AI Plan Mode time-budget) operator hours discipline 不變；本 ADR 為其 v4 級 token-level + month-cost level 補充
- DOC-08 §4（不是 §12 — 文本誤標已更正）AI 預算 baseline $2.00/day = ~$60/月 informal cap 保留為 Y1 default
- token-cost-analysis skill 為 AI-E 工作 SOP；本 ADR 為治理 contract 對應

**反向 attack**:
- 800 token cap 對 v5.9+ 新 module state 注入造成壓力 → mitigation：新 module state 加入 ContextDistiller v4 必走 ADR-0041 amendment（不可默默膨脹）
- L1 P95 邊際撞 3s SLA（800 token P95 ~4.5s）→ 接受妥協；mitigation：M3 self-monitoring + M8 anomaly 雙層觀察；若連續 30d 破 5s → 觸發新 ADR
- Statistical-only fallback informativeness 損失（純規則 narrative 比 LLM 弱）→ mitigation：fallback 是 conservative degrade 不是 normal path；M3 health 確保 fallback 不長期 active（> 30% inference → HEALTH_CRITICAL）
- DOC-08 §4 cap amendment cross-doc reference 協調成本（token-cost-analysis skill + 其他 ADR 引用 §12 為 AI cost cap 需批量更正為 §4）→ TW + PA 在 Sprint 1A-β-γ 集中修正

**建議**：APPROVE — L1 Ollama < 3s SLA P50 安全 + Y2 LLM cost 控 $72-126/月 + M4/M11 narrative cost 縮 5-20x + Y2 opt-in evidence-gated 路徑明示 + statistical-only fallback 保底 + DOC-08 §4 baseline 不取代

---

## AMD-2026-05-21-01：Autonomy vs Human Final Review 邊界定義

**重點看 YES**：此 AMD 是 v5.8 13-module thesis 的核心 governance amendment，CLAUDE.md §二 priority order 第 5「human final review」拆 protected scope 6 條 + opt-in scope 8 條；7 條 v5.8 §11 operator forgetfulness mitigation auto-action 全部落到具體 scope 列；5 條 mitigation 機制 + 6 條反向 attack counter-mitigation；影響 LAL / M2 / M3 / M6 / M7 / M8 / M10 / 5-gate / Copy Trading / Auto-Allocator 全部 v5.8 module。

**Key decision**:
- Protected scope 6 條（永不可 auto）：(a) Stage transition LAL 3-4 / (b) 5-gate live boundary / (c) Copy Trading enable / (d) Auto-Allocator 首次 activation / (e) Operator kill criteria breach response / (f) ADR-debt 創建
- Opt-in scope 8 條（operator 一次 opt-in 後可 auto）：(g) LAL 1 / (h) LAL 2 Y2 / (i) M2 overlay auto-disable always-on / (j) M3 auto-degradation T1+T2 always-on / (k) M6 reward weight ≤ 30% / (l) M7 demote 50% size always-on / (m) M8 alert→action Y2 / (n) M10 capital tier eval
- 5 條 mitigation：default-OFF / 5-gate fail-closed / 24h undo for LAL 1+2 / 每筆 emit lease + 多通道通知 / operator inactivity > 60d auto-rollback Advisory
- 6 條反向 attack counter-mitigation（v5.8 §11 each mitigation 對應 counter）
- 安全反模式禁止：inactivity = ∞ + toggle 永久 ON + undo window = 0 三項組合 Console UI hard-block

**衝突 / cross-dep**:
- CLAUDE.md §二 priority order 第 5 條（修訂對象，不取代）
- CLAUDE.md §四 hard boundaries（protected (b) 引用源）
- AMD-2026-05-15-01 Stage gate framework（protected (a) 引用源）
- 11 v5.8 ADR module-to-AMD scope mapping table（per R4 NEW-M-1 patch）— 對應 ADR-0030/0034/0036/0040/0042/0043/0044 等
- ADR-0024-lite Cowork operator-assistant 邊界對齊（不開「Cowork 可 promote」後門）

**反向 attack**:
- 「opt-in 後 AI 草擬 → operator 隔日 batch click confirm 100 條」helper UI 路徑 → mitigation：明示禁止 protected scope 走 batch path；每筆 audit log 落 `operator_click_evidence` per-decision
- operator vacation / 失憶 / 換手 silent failure → mitigation：default-OFF 退回 v5.7 Advisory safe degradation（非癱瘓）
- operator_ack_latency 健康域 probe 為新增（5d / 7d / 14d 階梯）具體閾值 + HEALTH state 升級曲線在 Sprint 1A-β CR-15 H-11 補完 — **partial defer 已明示**

**建議**：APPROVE — protected/opt-in 顯式 scope mapping 把灰區消除 + default-OFF safe degradation + always-on safety net (i)(j)(l) 收縮方向 + 24h undo for LAL 1+2 配套 ADR-0034 + operator inactivity 60d auto-rollback + 6 反向 attack 全 counter-mitigation；§二 16 根原則 #5 / #6 / #11 / #15 核心受益

---

## Cross-ADR 依賴拓撲圖

```
ADR-0006 (Bybit-only baseline 2026-04-03)
  └─ ADR-0033 (amendment standalone: Binance market-data Y1 + DEX/Hyperliquid NOT approved + D12)
     └─ ADR-0040 (timing amendment: Y2 → Y3+ at earliest, per-venue 5-gate + 6 條 gate + venue enum hardcode)

ADR-0008 Decision Lease state machine
  └─ ADR-0034 (M1 LAL 0-4 改名 + 6 條 auto hard gate + 24h undo)
     ├─ ADR-0030 (Copy Trading Y2 走 LAL 3/4)
     ├─ ADR-0032 (Earn lease retrofit unstake_pending state)
     ├─ ADR-0037 (M9 variant promotion 走 LAL 3)
     ├─ ADR-0038 (M11 replay window 擴展走 LAL 2)
     ├─ ADR-0039 (M12 bounds 越界走 LAL 3)
     └─ AMD-2026-05-21-01 (Y2 cap opt-in 走 LAL 4)

ADR-0017 Scanner is evidence not authority
  ├─ ADR-0030 (Copy Trading evidence-gated)
  ├─ ADR-0031 (Macro/On-chain counterfactual evidence)
  └─ ADR-0038 (M11 self-hosted PG only sourcing posture)

math-model-audit skill
  └─ ADR-0036 (HMM/Markov-switching/GARCH governance promotion)
     └─ ADR-0037 Decision 4 反模式 (e) 引用本 ADR 黑名單

ADR-0027 AI Plan Mode time-budget (operator hours discipline)
  └─ ADR-0041 (v4 級擴展: 800 token cap + DOC-08 §4 cap amendment Y1 $60 / Y2 opt-in)

CLAUDE.md §二 priority order 第 5「human final review」
  └─ AMD-2026-05-21-01 (拆 protected 6 條 + opt-in 8 條 + 5 mitigation + 6 反向 attack counter-mitigation)
     └─ 對應 ADR-0030/0034/0036/0040/0042/0043/0044 各 module
```

---

## TW Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| TW | 本文件起草（PA dispatch via operator D+5 batch sign-off 用） | 2026-05-21 | Drafted |
| Operator | 12 ADR + 1 AMD batch sign | 2026-05-21 | PENDING |

---

*OpenClaw / Arcane Equilibrium — TW 12 ADR + 1 AMD Batch Sign-off Highlight Sheet*
*Operator skim-time target: 30 min；重點 4 件（ADR-0033 / ADR-0034 / ADR-0040 / AMD-2026-05-21-01）*
