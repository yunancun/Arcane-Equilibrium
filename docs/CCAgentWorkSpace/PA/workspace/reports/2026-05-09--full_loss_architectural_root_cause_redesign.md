# 玄衡 · Arcane Equilibrium — 系統性虧損的架構級根因 + 真升級藍圖

**作者**：PA（Project Architect）
**日期**：2026-05-09
**基準**：CLAUDE.md head（W-AUDIT-1 sync, `b91487f2`）+ v2 verification land 後
**讀者**：Operator（首讀）、PM、QC/MIT/FA（協同）
**輸入**：CLAUDE.md §一/§二/§五 / `2026-05-08--full_audit_fix_plan.md`（88 finding）/ `2026-05-09--audit_fix_verification_v2_summary.md`（v2 verdict）/ EX-06 V1 / 14 ADR / Rust strategies/* + tick_pipeline + 5-Agent Python code
**獨立性**：QC 從 alpha 視角、MIT 從 ML/data 視角、本份從 system architect 視角，三角觸碰前不互相校核。

---

## Executive Summary（給 PM，200 字）

5 策略 7d demo gross **-26.44 USDT** 不是策略 bug 或調參失敗，是**架構在系統性生產 alpha-deficient 策略**的必然輸出。問題核心：**Strategy 接口契約只暴露 OHLCV + classic indicators**，本質上只能孵化 textbook TA；**Strategist Agent 的 scope 被縮在「調 5 策略參數」**，不負責新策略發現；**Analyst L2-L5 進化階梯 100% dormant**，無 alpha-discovery loop；**ML 學習平面 attribution_chain 0.5%** = 系統不會從交易學習。架構 north star：**從「TA 策略執行容器」升級為「alpha source 孵化平台」**。第一刀切 Strategy Interface — 從 `(KlineManager, IndicatorSnapshot, Signal[])` 升級為含 `funding_rate / basis / open_interest / orderflow / cross_asset` 的 Alpha Surface Bundle，並把 Strategist 重定義為 alpha-source orchestrator 而非參數調校器。88 finding 中 ~80% 是這 5 個結構性根因的下游症狀，逐 finding 修永遠追不上。

---

## Layer 1 — 為什麼這個架構必然產出虧損策略

### 1.1 Strategy Interface 結構性偏差（**最核心**）

代碼證據：

- `rust/openclaw_engine/src/strategies/mod.rs:72-159` — `Strategy` trait 的 `on_tick(ctx: &TickContext<'_>)` 是唯一對策略可見的世界
- `rust/openclaw_engine/src/tick_pipeline/mod.rs:665-708` — `TickContext` 字段：`symbol / price / timestamp_ms / indicators (1m/5m IndicatorSnapshot) / signals[] / h0_allowed / funding_rate / index_price / open_interest / best_bid / best_ask / tick_size`
- 5 策略代碼：`bb_breakout / bb_reversion / ma_crossover / grid_trading / funding_arb`

**架構觀察**：
TickContext 形式上**已暴露** funding_rate / index_price / open_interest / orderbook L1 — 這是好消息。但**實際被消費的只有**：
- `funding_arb.rs` 用 funding_rate + index_price（已 RETIRE per ADR-0018）
- `grid_trading` 用 best_bid/ask 為 PostOnly maker entry
- 其餘 4 策略全部以 `IndicatorSnapshot`（典型 EMA / Bollinger / ATR）為核心輸入

**結構性問題**：Strategy interface 把「indicators-driven on_tick reactive」當作預設模式。寫一個 funding skew + basis arb 策略需要的 cross-section snapshot（同時看 25 symbols 的 funding curve）、做 orderflow imbalance 需要的 microprice + queue depth、做 liquidation cascade 偵測需要的 large-trade tape — **這些在 TickContext 結構下是「strategy 自己 buffer」而非 first-class field**。EDGE-P2-2 line 686-688 註明：「Raw value — consumer strategies buffer + compute delta on their own window」。

→ **每個非 TA 類 alpha 都要自己重造輪子**，有摩擦但不 fatal；致命的是 IndicatorEngine + SignalEngine 的中央化使「TA 路徑」是高速公路、其他路徑是泥路。E1 / Strategist 自然偏向走高速公路。

**根因 1**：**Strategy interface 結構性激勵 1m kline + classic indicator 路徑，使任何系統孵化的策略都會 regress 到 textbook TA**。當市場已對 textbook TA pattern 做了 30 年 efficient pricing，gross-negative 是統計必然。

**Push-back 給 operator**：CLAUDE.md §五的「KlineManager → IndicatorEngine → SignalEngine → 5 策略」流水線的措辭本身就在強化這個 mental model。建議 §五改寫為「市場數據 → AlphaSurface (kline + funding + basis + orderflow + xasset) → Strategy → Orchestrator」，從文檔層面就 reframe。

### 1.2 Strategist Agent scope 是「調參器」非「策略發現器」

代碼證據：
- `strategist_agent.py:128-134` — `_REGIME_STRATEGY_PREFERENCES`：4 個 regime（trending_up/down, ranging, volatile）對 5 個策略的 weight multiplier
- `EX-06.md:155-165` — Strategist 職責：「币种选择 / 策略匹配 / 参数优化 / 组合分配 / 时段意识」
- v2 verification §5：F-strategist-cap `max_param_delta_pct` 30→50 一次調整

**架構觀察**：
EX-06 V1 的 Strategist 描述包含「策略匹配（從 5 策略選最優 + 自主孵化策略）」字面，但**「自主孵化策略」這條線在代碼層面 100% 不存在**。Strategist 的所有 IMPL bandwidth 用在：
- H1 ThoughtGate 預算/複雜度 gate
- H3 ModelRouter Ollama vs L2 Claude 路由
- 對 5 個既存策略的 regime preference weight 1.2 / 0.8 微調
- `max_param_delta_pct` 一次最多改 50% 參數

**沒有任何代碼路徑做**：
- 「我注意到當前 ranging regime 下 25 symbols 的 funding 散度方差 1.8σ，我提議孵化一個 funding-skew-spread 策略」
- 「跨 strategy_X 在 BTC 上 winrate 60% 但 strategy_Y 在 SOL 上 winrate 30% 的差異提示 microstructure factor 不同」
- 「請 Analyst L3 設計 hypothesis test」

→ **Strategist 在當前架構就是 `dict[str, float]` 微調器**，不是 cognitive entity。

**根因 2**：**Strategist scope 被縮在「5 策略參數 + regime weight」，沒有 alpha-discovery 職責**。即使 Layer 2（cloud LLM）翻 ON，它能做的也只是「換個方式微調這 5 策略」。

**Push-back**：Operator 在 CLAUDE.md §一寫「Agent 自主完成交易決策」+ 原則 11「Agent 最大自主權」。這個敘事與代碼 scope 強烈不一致 — 當前 Agent 實際自主的範圍只是 [P2 參數 ± 50%]。**架構不在生產 Agent 自主，而在生產 Agent 微調權**。

### 1.3 Analyst L2-L5 進化階梯 100% dormant 是 alpha discovery loop 死的真實位置

代碼證據：
- `EX-06.md:233-239` — Analyst 五層 L1-L5
- `analyst_agent.py:64-80` — code 註明「L1: Statistical analysis (always running) / L2: AI pattern discovery (triggered after sufficient observations)」
- v2 §6 §10：MLDE attribution_chain_ok 24h 0.5041%（denominator artifact，ok_n only +47%）；feature_baselines row=0 持平；DSR/PBO 已 wired 但 5 策略 None evidence 永卡 promotion gate
- AMD-2026-05-09-02 §4 + ADR-0020：**Layer 2 manual + supervisor-only by design**

**架構觀察**：
EX-06 設計 Analyst 是進化引擎（L1 復盤→L2 模式→L3 假設→L4 策略進化→L5 元學習）。實際情況：
- L1 跑（基本統計）
- L2-L5 全 dormant，且 ADR-0020 把 Layer 2 永久標 manual + supervisor-only **by design**

→ Analyst 在當前架構 = post-trade summarizer，**沒有任何 hypothesis-experiment loop**。「進化」是宣傳詞，不是 runtime 行為。

attribution_chain_ok 0.5041% 不是 ML pipeline bug，是**沒有 hypothesis-experiment-verdict loop 的必然結果**：沒有 hypothesis 哪來的歸因 chain。

**根因 3**：**alpha discovery loop 是 EX-06 spec 但 IMPL 0%**，且 ADR-0020 把它的解封路徑進一步推遲（manual + supervisor-only）。系統從交易學到的東西不會回流影響策略，永遠是 5 個 fixed-graph 策略 + 微調。

### 1.4 風控側鐵血 vs alpha 側放羊的架構張力

代碼證據：
- DOC-01 §5.1-5.16 16 條根原則：原則 1/2/3/4/5/6/7/8/9/13 都是 risk-side
- 原則 11/12/15 是 capability-side，但措辭抽象（「最大自主」/「持續進化」）
- 4 個 risk_config*.toml + Rust risk_envelope + Guardian Agent + SM-04 5-step 降級階梯 + Cost Gate + AI 注意力稅 + StopManager + 對抗性止損
- 對應 alpha 側：1 個 strategy_params*.toml + Strategist `_REGIME_STRATEGY_PREFERENCES` 4×5 hardcoded 字典

**架構觀察**：
風控有 5 層 state machine + 4 條 TOML + 數字精準 cap；alpha 有 1 條 TOML 拍 5 個策略參數 + 4 個 hardcoded regime label × 5 策略 weight。

兩邊不對稱不是 risk vs return 的優先級正確（生存 > 利潤本身合理），而是**風控側有 specification + 治理 + 機械強制機制；alpha 側只有「Strategist 自由發揮」這一句話 + 一個 Ollama 提示詞**。

→ Operator 寫 ARCH-RC1 統一 Config 契約 + 4 risk_config 獨立 + Rust ArcSwap hot-reload 是因為「風控很重要要架構強制」。**alpha 側沒有等同的架構 forcing function**：沒有 alpha source registry、沒有 factor library、沒有 hypothesis pipeline、沒有 cross-strategy 對沖檢查、沒有 portfolio-level alpha aggregation contract。

**根因 4**：**架構在風控側建立了 forcing function（state machine + 4 config + Guardian veto），但在 alpha side 把所有責任丟給「Strategist 自主」這個抽象期待**。alpha 側沒有 architectural forcing function = alpha 永遠是個鬆散願景。

### 1.5 Conductor + 5-Agent 拆分是否 over-engineered

代碼證據：
- `analyst_agent.py:88-238` + `strategist_agent.py:91-238` 都繼承 BaseAgent，含 H1-H4 gate / cognitive_modulator / consecutive_losses / l2_cache / regime_preferences
- v2 §1 FA verdict：5-Agent 業務鏈 58→62%，仍未到 production
- AMD-2026-05-09-02 §4 + ADR-0020：Layer 2 永久 manual + supervisor only

**架構觀察**：
EX-06 5-Agent（Scout/Strategist/Guardian/Analyst/Executor）拆分解決的是**信息流職責邊界**問題：誰看新聞 / 誰決策 / 誰收緊風控 / 誰歸因 / 誰下單。這個拆分在治理層**正確且有清楚對象通信協議**。

但**運行時實際情況**：
- Scout: 跑著但 IntelObject 主要被 logging，Strategist 不真依賴 Scout 的 sentiment（Strategist 的決策路徑是 H1 gate → IndicatorSnapshot）
- Strategist: 跑著但等同於 5 策略的參數放大鏡
- Guardian: 跑著但 P2 風控的 veto 和 Cost Gate 重疊
- Analyst: L1 統計 + L2-L5 dormant
- Executor: shadow_mode_provider true（fail-closed），lambda:True 已移除（v2 closed）

**拆分引入的摩擦**：
- 5 個 BaseAgent 各自 cognitive_modulator + audit_callback + event_store + budget_tracker
- 跨 Agent 通信走 MessageBus（v2 §1 仍稱 free-text MessageBus 為 legacy/advisory）+ Agent Decision Spine（typed lineage，REF-20 新建）
- 兩套 lineage 並存（MessageBus + Agent Decision Spine）= 維護負擔 + 治理對象不清晰

**判定**：**5-Agent 拆分本身正確**（職責邊界 clear），**但運行時 4 個是空殼**（Scout / Analyst L2-L5 / Strategist alpha-discovery / Layer 2）。這不是 over-engineered，是 **under-implemented 的 over-spec**。當前架構讓「治理框架完備」幻覺存在，掩蓋了「實質無 alpha 源」的事實。

**根因 5**：**5-Agent 是合法骨架，但靈魂（Analyst L2-L5 + Strategist alpha-discovery + Layer 2 cloud reasoning）沒裝**。修架構時不要砍掉骨架（會破 Decision Lease + Guardian veto + Authorization 治理），要裝靈魂。

---

## Layer 2 — 88 finding 的 5-7 個結構性公因式

把 88 個 finding 從 severity 視角抽到 root-cause 視角，得到：

### Cluster A — Strategy interface alpha-poverty（佔約 25-30 findings）

**公因式**：策略 interface 不暴露 alpha-rich primitives + 5 策略全部 OHLCV-driven。

涵蓋 finding：F-05（5 策略 gross negative）、F-13（DSR/PBO 卡）、F-bb-rfc-5m、F-ma-rewrite、F-VaR-CVaR、F-Kelly-config、F-funding-clean、QC v2 NEW-4（Donchian leak-bias）、QC v2 NEW-5（min_observations=200 卡 promotion）、5 策略 verdict、AMD §3 Option ii、bb_reversion 配 ma 等。

**架構 anti-pattern**：「TA-Strategy as Default」— 預設策略 = TA 策略，alpha discovery 在 architectural sense 是 second-class citizen。

**真正的「一勞永逸」**：升級 Strategy interface 成 Alpha Surface Bundle，加 Alpha Source Registry 與 Strategy Incubation Pipeline，並把 Strategist scope 重定義。**88 finding 修不到根**，因為它們都在「修當前 5 個 OHLCV 策略」邊界內。

### Cluster B — Learning loop dormant（佔約 15-20 findings）

**公因式**：Analyst L2-L5 + Layer 2 + ML training + attribution_chain 全部不工作。

涵蓋 finding：F-08（5 ML 腳本 unscheduled）、F-10（attribution_chain 0.5%）、F-16（feature_baselines 0 row）、F-edge-cycle、F-outcome-bf、F-V076、F-29、F-09 sibling FUP-2、Layer 2 0 流量、F-07 ANTHROPIC_API_KEY 未設、F-28 ContextDistiller 不存在、F-strategist-cap 30→50 等。

**架構 anti-pattern**：「Learning Plane Specified But Not Wired」— 仍有人在 spec / spec修訂，IMPL 進度不交付學習信號。

**真正的「一勞永逸」**：建立 Hypothesis Pipeline as First-Class Architectural Object（不只是 Analyst 內部欄位），讓 Analyst L3 hypothesis 是 Decision Lease 同等級的 governance 對象，跨 sprint 持續、可審計、有 verdict gate。

### Cluster C — Authority/Lineage drift（佔約 12-15 findings）

**公因式**：spec 與 runtime 之間漂移，人工 verification 才知。

涵蓋 finding：F-01 shadow_mode TOML × 3 + lambda（v2 closed）、F-02 §三 lease flag stale（v2 closed）、F-03 lease audit channel（v2 closed）、F-15 lease writer e2e、F-17 tab-settings hard-coded、F-19 AMD §5.4 7d 提前 flip、F-spec-SM05 polling 設計、F-25 scout require_operator、F-24 phase4 0 actor、原則 #11 違反、原則 #16 等。

**架構 anti-pattern**：「Spec / Runtime / Doc 三套 SoT 漂移」— v2 §3 P0-DECISION-AUDIT 5/5 拍板過程顯示 operator 必須親自介入解 spec 衝突，因為架構沒有自動對齊機制。

**真正的「一勞永逸」**：Spec-as-Code（CLAUDE.md §三 stale 防線 + healthcheck id 引用是好開始，但沒走完），所有 spec 必須有 runtime check，runtime 必須有 spec 引用，CI 失敗即 spec drift。

### Cluster D — Schema dead weight + dead code（佔約 10-15 findings）

**公因式**：spec 寫了表 / 模組 / 函數，但 0 production caller / 0 INSERT。

涵蓋 finding：F-04 H0_GATE Python 0 caller、F-11 24 表 0 row（learning 14 + observability 4 + replay 5 + agent 1）、F-20 909MB damaged dump、F-22 risk_verdicts 18.47M no retention、AMD §4 openclaw_core 9 模組 sunset、F-12 runner.rs 2467（v2 closed 1167）等。

**架構 anti-pattern**：「Spec-First Without Sunset Clauses」— 寫進來的東西沒有 retire 機制，dead schema / dead code 累積成戰略迷霧。

**真正的「一勞永逸」**：Module Lifecycle State Machine（active / observing / deprecated / sunset），所有 module + table 必標 lifecycle stage + sunset trigger condition。

### Cluster E — Documentation churn debt（佔約 10-15 findings）

**公因式**：Sprint 完成 → CLAUDE.md / TODO.md / docs/README / SCRIPT_INDEX / SPEC_REGISTER / CONTEXT.md / ADR / memory 多套文檔半同步。

涵蓋 finding：F-14（docs/README 50+ 缺漏）、F-spec-reg、F-script-idx、F-tw-misc、TW worklogs 12 天斷層、SPECIFICATION_REGISTER 缺、ADR 0015-0019 缺、CCAgentWorkSpace MIT/BB 漏列、MODULE_NOTE 規範違反、R4 v2-N1 殭屍引用等。

**架構 anti-pattern**：「Doc Plane is Manual」— 策略 / 治理對象 / agent / wave 結構在代碼變化，但 docs 必須人手追，必然 drift。

**真正的「一勞永逸」**：Doc Plane 自動化（從代碼註解抽 spec、從 healthcheck 抽 §三、從 PG schema 抽 SCRIPT_INDEX），讓 doc 是 derived 而非 first-class write surface。

### Cluster F — Performance / Platform readiness（佔約 8-10 findings）

涵蓋 finding：F-12 runner.rs 拆（v2 closed）、F-21 strip、F-26 CI Mac matrix、F-deepcopy、F-orjson、F-ai-budget RwLock、F-event-consumer 拆等。

**架構 anti-pattern**：「Cross-Platform / Performance is Aspirational」— 跨平台政策有 §七 ★★ 強條款但無 CI gate；performance budget 散在多 sprint。

### Cluster G — Security/Governance Edge cases（佔約 5-8 findings）

涵蓋 finding：F-23 0.0.0.0、F-24 phase4 0 actor（v2 closed）、F-25 scout 0 require_operator、F-30 prompt() × 6 + a11y、launchd plist HIGH（v2 closed）、cookie secure default、A3 v2 NEW-7/8 等。

**判定**：屬於常規 hardening，不是結構性 root cause。

---

### 關鍵結論：88 finding 真正的 leverage point 是 A + B + C 三個 cluster

| Cluster | finding 數 | 真正修復路徑 | 88-finding patch 是否能解 |
|---|---|---|---|
| A 策略 alpha 貧乏 | ~25-30 | 升 Strategy Interface + Strategist scope | ❌ 患「修 5 個 TA 策略」近視 |
| B 學習 loop 死 | ~15-20 | Hypothesis Pipeline 一等對象 | ⚠️ 部分修能解，但無頂層架構支撐 |
| C 治理 drift | ~12-15 | Spec-as-Code | ⚠️ v2 已修一部分，仍需 forcing function |
| D dead weight | ~10-15 | Module Lifecycle SM | ⚠️ 可逐個拔，但長期會回流 |
| E doc churn | ~10-15 | Doc Plane 自動化 | ⚠️ 緩衝，但長期不解 |
| F 性能 / 平台 | ~8-10 | CI gate + budget 政策 | ✅ 88 patch 已解部分 |
| G security edge | ~5-8 | Hardening backlog | ✅ 88 patch 適用 |

**直白：A 是 source of all evil，B 是 source of all darkness，C 是 source of all surprise**。先解 A，否則 B/D/E 都白做。

---

## Layer 3 — Architectural Redesign Sketch

### 3.1 升級 Strategy Interface 為 Alpha Surface Bundle（Tier-1 改造）

**現況**：`Strategy::on_tick(&TickContext)` 字段以 indicators 為核心。

**新接口（建議）**：

```rust
pub trait Strategy: Send {
    fn name(&self) -> &str;
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag];  // ← 新：聲明依賴
    fn on_tick(&mut self, ctx: &TickContext, surface: &AlphaSurface) -> Vec<StrategyAction>;
    // ...
}

pub struct AlphaSurface<'a> {
    // Tier 1 — TA / OHLCV（向後相容）
    pub indicators: Option<&'a IndicatorSnapshot>,
    pub indicators_5m: Option<&'a IndicatorSnapshot>,

    // Tier 2 — 跨資產 / 截面（新一等對象）
    pub funding_curve: Option<&'a FundingCurveSnapshot>,    // 25 symbols funding
    pub basis_curve: Option<&'a BasisCurveSnapshot>,
    pub oi_delta_panel: Option<&'a OIDeltaPanel>,           // cross-symbol OI 動量

    // Tier 3 — Microstructure（新一等對象）
    pub orderflow: Option<&'a OrderflowFeatures>,           // microprice, queue imbalance from L50 (or L200), large-trade tape
    pub liquidation_pulse: Option<&'a LiquidationPulse>,    // requires_revival flag — handler 已 4 weeks ago deleted（見 BB v3 NEW-6）

    // Tier 4 — 信息流（從 Scout 真實接入）
    pub event_alerts: &'a [EventAlert],
    pub regime: RegimeTag,
    pub sentiment_panel: Option<&'a SentimentPanel>,
}

pub enum AlphaSourceTag {
    TA1m, TA5m, FundingSkew, Basis, OIDeltaPanel, OrderflowImbalance,
    LiquidationCascade, EventDriven, CrossAsset, ...
}
```

**Bybit V5 真實 levels 對齊**（BB v3 NEW-5）：Bybit V5 WS linear orderbook 真實 depth levels = `1 / 50 / 200 / 1000`，**沒有 L25**。`OrderflowFeatures` 的 microprice / queue imbalance / orderbook imbalance 必須從 `orderbook.50.{symbol}`（已預設訂閱）抽取；如需 deeper book context（large order resting、queue depth tail）改 `orderbook.200.{symbol}`，禁止任何「L25」字眼進 spec / IMPL / migration / healthcheck。

**`liquidation_pulse` 復活前置條件**（BB v3 NEW-6）：OpenClaw 於 2026-04-06 已刪除 `allLiquidation` WS handler（字典手冊 line 990 證明）。`market.liquidations` 表雖 reserved 保留，但 R-1 IMPL 必須**先付 +1 sprint 重接 WS handler + 重啟 writer**，期間此 alpha source 必須以 `requires_revival: true` flag 標記為 dormant；策略 ctor 階段 declare `LiquidationCascade` 的，在 handler 復活前 surface 永遠 `None`，而不是 stub mock 數據。

**`Basis` execution 邊界**（BB v3 NEW-8）：`basis_curve` (perp - spot) 在 Bybit demo 環境**僅支援 observation**（demo 無 spot lending execution capability，與 funding_arb v2 retire 同因 ADR-0018）。R-1 spec 必須明文「`basis = observation-only signal until mainnet`」，並對 `Basis` tag 的策略加 `requires_spot_capability: true` flag — 在 demo 環境下任何吃 `Basis` tag 的策略產生的 `StrategyAction` **必須 fail-closed**，不可進 IntentProcessor；只有 mainnet + 真實 spot account 接通後才解封 execution path。否則跟 funding_arb v2 同陷阱（demo edge sample 全是 paper-grade，graduate live 時必死）。

**強制機制**：
- 每個 Strategy 必須在 ctor 聲明 `declared_alpha_sources()`
- Orchestrator 用此做 dispatch tracking（哪些 alpha source 被消費 / 棄用）
- Strategy Registry 拒絕全部依賴 `[TA1m]` 的新提案，除非附 QC explicit waiver

**為什麼這是 leverage point**：寫一個 funding skew spread 策略現在需要自己 buffer 25 symbols。新介面下 `surface.funding_curve` 是一等對象 — 摩擦從「寫 200 LOC 自己維護 panel」降到「import + 50 LOC 策略邏輯」。**架構在主動激勵非 TA alpha**。

**Token of doubt**：可能會被指控 over-engineering。但證據：v2 §6 P1 第 6 條「DSR/PBO evidence 自動化 push 鏈 — 5 策略 None evidence → demo graduation 永遠卡」 — **5 策略本身結構性無法 graduate，因為它們都吃同一個 alpha source（TA），互相 redundant**。換 alpha source = 拓寬可孵化空間。

### 3.2 Strategist 重定義為 Alpha Source Orchestrator

**現況**：Strategist = 5 策略 weight 微調器 + 參數 ± 50%

**新責任**：
1. **Alpha Inventory Tracking**：維護 `AlphaSourceRegistry`（已實裝 source / 已 retired / 正 incubating / 正 sunset）
2. **Hypothesis Sourcing**：基於 `surface.regime` + Analyst L2 模式 + Scout 事件，提出新 alpha source 假設（不是新參數）
3. **Strategy Incubation Dispatcher**：把假設派給 Analyst L3 進實驗 pipeline
4. **Portfolio-Level Allocation**：對 active alpha sources 做 risk-budget 分配（不是 hardcoded 1.2 / 0.8）

**淘汰路徑**：`_REGIME_STRATEGY_PREFERENCES` hardcoded 4×5 字典移除，由 `AlphaSourceRegistry` + 動態 Sharpe-by-regime 計算取代。

**對 LG 的影響**：當前 LG-2/3/4/5 都 frame 為「整 system 放權」。但若有 alpha-source 級別 risk budget，可改成 **per-alpha-source promotion**（funding skew 跟 TA 完全獨立 promotion path），這是 Layer 3 §3.3 的 supervised live 設計。

### 3.3 Live Promotion Gate 改 risk-budgeted per-alpha-source

**現況**：LG-2 / LG-3 / LG-4 / LG-5 線性串列必全完才放權，且全 system 一刀。

**新設計（建議 ADR）**：

```
LiveBudget = { capital_cap_usd, max_concurrent_positions, max_drawdown_pct }
AllocateBudget(alpha_source_id, budget_slice):
    1. evidence_window_PASS for THIS alpha_source（DSR / PBO / 7d gross > 0 demo）
    2. Guardian per-alpha-source veto check
    3. Decision Lease 仍然 per-intent
    4. Outcome → MLDE feedback → adjust budget_slice 動態
```

**好處**：
- funding-skew 樣本量足、TA 樣本量不足 → funding-skew 先 graduate live with 5% budget，TA 留 demo
- 不需「整 system 放權」blocking on 5 個 TA 策略
- 每個 alpha source 有自己的 promotion clock，併發推進

**對 LG-X 的關係**：LG-X 1-5 仍是 baseline foundation（H0 production caller / pricing binding / supervised state machine 仍必要），但放權單位從 `live_reserved (yes/no)` 變成 `live_budget(alpha_source_id, slice)`。

### 3.4 Hypothesis Pipeline as First-Class Governance Object

**現況**：Analyst L3 spec 在 EX-06，但代碼層無 Hypothesis 對象。

**新對象**（與 Decision Lease 同治理層級）：

```python
@dataclass
class Hypothesis:
    id: HypothesisId
    state: Literal['DRAFT', 'REGISTERED', 'EXPERIMENTING', 'EVIDENCE_GATE', 'PROMOTED', 'REJECTED', 'EXPIRED']
    proposer: AgentRole              # Strategist / Analyst / Operator
    statement: str                   # 「ranging regime + funding > 0.05% → spread alpha」
    null_hypothesis: str             # 「funding > 0.05% 對 ranging 無 effect」
    evidence_required: EvidenceContract  # n_samples, DSR_min, PBO_max
    experiment_target: ExperimentSpec     # 哪 cohort / 哪 alpha source / 哪 paper engine
    verdict: Optional[Verdict]
    audit_chain: List[AuditEvent]
```

**強制機制**：
- 每個新策略 / 新參數 / 新 risk budget 必須有 originating Hypothesis
- Hypothesis 狀態機強制 EVIDENCE_GATE 才能 PROMOTED
- Verdict 持久化 → MLDE 訓練資料 + Analyst L5 元學習

**對 attribution_chain 0.5% 的影響**：當前歸因失敗的根因不是 SQL bug，是**沒有 hypothesis 來歸因**。每筆交易若有 originating hypothesis_id，attribution 是 trivial：「fill outcome → hypothesis_id → win/loss → update DSR」。

### 3.5 Multi-Timeframe + Portfolio-Level Aggregation

**現況**：5 策略獨立計分；TickContext 1m/5m 兩 timeframe；無 portfolio-level alpha aggregation。

**設計**（合併入 §3.1 AlphaSurface）：
- 每個 alpha source 註冊 `(timeframe, freshness_ladder, decay_function)`
- Orchestrator 在 portfolio level 做：
  - 高度相關 alpha sources → enforce single budget slice（避免雙重曝險）
  - 反向 alpha sources → 自動 hedge eligibility check
  - VaR/CVaR/EVT（W-AUDIT-6c 已 IMPL）作 portfolio-level gate，不只 per-symbol

### 3.6 觀察 / 學習 / 執行 hard separation 是否真成立

**Operator 在原則 #7 強調學習 ≠ Live**。當前 attribution 0.5% 部分是因為這個 separation 太硬，Live → Learning 寫路徑只有 fills 表 + outcome backfill 的稀疏 INSERT。

**但** separation 本身正確（避免 ML 直接改 live 參數的災難）。問題在**接口太窄**：
- 當前 Live → Learning：只有 trading.fills 落地
- 應該：每筆 fill 帶 originating_hypothesis_id + alpha_source_id + decision_lease_id + risk_budget_id 的 typed lineage（Agent Decision Spine 已部分做到，但 hypothesis 還未 first-class）

**結論**：separation 不需放鬆，需把**通過 separation 的接口加寬**，讓學習平面拿到結構化 attribution，而非自己從 fills 拼湊。

---

## Layer 4 — 排序 + Sprint 規劃（架構升級的 highest-leverage 動作）

### 動作 R-1（Tier-1，3-4 sprint）：Alpha Surface Bundle + Strategy Interface 升級

**範圍**：
- 新增 Rust struct `AlphaSurface` + `AlphaSourceTag`
- Strategy trait 加 `declared_alpha_sources()`
- TickContext 升級加 funding_curve / basis_curve / oi_delta_panel / orderflow（暫先 stub 結構，不全部 wire）
- 5 既存策略 declare alpha_sources（多數是 TA1m）作 backward compat
- Orchestrator 加 dispatch tracking

**Dependency**：低 — TickContext 已部分準備（funding_rate/index_price 字段已在）
**Sprint estimate**：3 sprint（spec + IMPL + 5 策略 migration + 測試）
**失敗 fallback**：可漸進，先 stub 結構不破現有 5 策略
**與 W-AUDIT-1..7 關係**：**全新 wave，建議 W-AUDIT-8a "Alpha Surface Foundation"**，不替代 W-AUDIT-6（W-AUDIT-6 重點是 5 既存策略 verdict + Kelly + DSR/PBO，那層仍要做 — 但長線價值低）

### 動作 R-2（Tier-1，2-3 sprint）：Strategist scope reframe + AlphaSourceRegistry

**範圍**：
- 新增 `AlphaSourceRegistry` Python class（active / observing / deprecated / sunset 4 stage）
- Strategist 增 `propose_alpha_source()` 方法（產出 Hypothesis 而非 TradeIntent）
- 移除 `_REGIME_STRATEGY_PREFERENCES` 4×5 hardcoded → 動態 Sharpe-by-regime
- Strategist Layer 2 解封路徑：alpha-source proposal 是合適的 Layer 2 cloud reasoning 場景（vs 高頻 trade signal — ADR-0020 對的）

**Dependency**：R-1 進度 ≥ 50%（AlphaSurface 結構存在才能 propose）
**Sprint estimate**：2 sprint
**失敗 fallback**：保持 hardcoded 字典，只先做 AlphaSourceRegistry observation
**與 W-AUDIT-7 關係**：W-AUDIT-7 第 8 條「Layer 2 autonomous loop」可以 reframe 為「Layer 2 alpha-source proposal loop」，更聚焦

### 動作 R-3（Tier-1，2-3 sprint）：Hypothesis Pipeline first-class object

**範圍**：
- V### migration 加 `learning.hypotheses` table + state machine
- Analyst L3 重 IMPL 為 Hypothesis CRUD + experiment dispatch
- Decision Lease 加 `originating_hypothesis_id` 欄位
- ExecutionPlan / fills 落地 propagate hypothesis_id
- attribution chain 改寫 base on hypothesis_id

**Dependency**：R-1 + R-2 至少 spec 完成（hypothesis 要 reference alpha_source_id）
**Sprint estimate**：3 sprint（schema + state machine + 接線 + ML 餵）
**失敗 fallback**：階段 1 只做 hypothesis CRUD + manual approval；階段 2 才接 Analyst L3 自動
**與 W-AUDIT-4 關係**：W-AUDIT-4 ML 基座 (feature_baselines / outcome backfill) 應**併入** Hypothesis Pipeline IMPL，不要分兩條線。當前 W-AUDIT-4 修 feature_baselines 然後仍無 hypothesis 來解釋特徵 → 只是讓 dead schema 變 alive schema 但仍無含義

### 動作 R-4（Tier-2，2 sprint）：Per-alpha-source Live Promotion Gate

**範圍**：
- 新 ADR：替換 LG-2/3/4/5 「整 system 放權」 為 risk-budgeted per-alpha-source
- LiveBudget 對象 + GovernanceHub 加 `acquire_alpha_source_budget()` API
- Guardian 加 per-alpha-source veto path

**Dependency**：R-1 + R-2 完成；LG-X 1-5 baseline 仍須完成（H0 production caller / pricing binding）
**Sprint estimate**：2 sprint
**失敗 fallback**：保留 binary live_reserved，但加上 alpha-source-aware risk budget within Live
**與 W-AUDIT-3 關係**：W-AUDIT-3 fake-live + Decision Lease 仍是 baseline，本動作疊加之上

### 動作 R-5（Tier-2，1-2 sprint）：Spec-as-Code + Module Lifecycle SM

**範圍**：
- CI gate：CLAUDE.md §三 stale > 7d auto-fail
- 每個 module / table 新增 `# LIFECYCLE: active|observing|deprecated|sunset` header
- helper_scripts/ci/spec_runtime_drift_check.py（與現有 healthcheck 整合）
- 自動從代碼抽 SCRIPT_INDEX / SPEC_REGISTER

**Dependency**：低
**Sprint estimate**：1-2 sprint
**與 W-AUDIT-1 關係**：**併入 W-AUDIT-1**（已是 doc sync wave），加自動化 dimension

---

### W-AUDIT-1..7 vs R-1..R-5 對照矩陣

| | 性質 | 對應 W-AUDIT |
|---|---|---|
| W-AUDIT-1 docs sync | maintenance + spec-as-code 升級 | 部分被 R-5 取代 / 增強 |
| W-AUDIT-2 security IMPL | hardening | orthogonal — 必須做 |
| W-AUDIT-3 fake-live | runtime baseline | orthogonal — R-4 build on top |
| W-AUDIT-4 ML 基座 | dead schema 修 / 學習平面 | **建議併入 R-3 Hypothesis Pipeline**，不要單獨做 |
| W-AUDIT-5 性能 | LOC + binary + CI | orthogonal — 必須做 |
| W-AUDIT-6 策略 | 5 既存 TA 策略修 | 短期必做但長期 ROI 低 — **這是「修 5 個必死策略」陷阱** |
| W-AUDIT-7 GUI/AI | UX + Layer2 | Layer 2 部分被 R-2 reframe |

**判定**：
- W-AUDIT-2 / -5 純粹增量必做（不關架構升級）
- W-AUDIT-3 是 R-4 baseline 必做
- **W-AUDIT-4 + W-AUDIT-7 應 reframe**：4 併入 R-3，7 的 Layer 2 部分換成 R-2
- **W-AUDIT-6 戰略 ROI 低**：5 既存 TA 策略修完仍會 gross negative 高機率（QC FA MIT 共識），建議只做 minimum（funding_arb 退役 + DSR/PBO + Kelly config 化），不重寫 ma / bb，把帶寬留給 R-1 R-2 R-3
- **W-AUDIT-1 升級 R-5 是「自動化 doc 同步」**

### 推薦 Sprint 順序

| Sprint | Wave |
|---|---|
| Sprint N (current+1) | W-AUDIT-2 + W-AUDIT-5（純維護）+ R-1 spec phase |
| Sprint N+1 | R-1 IMPL + R-3 schema phase + W-AUDIT-3 baseline |
| Sprint N+2 | R-1 5 策略 migration + R-2 spec phase + R-3 state machine |
| Sprint N+3 | R-2 IMPL + R-3 接線 + R-5（W-AUDIT-1 升級） |
| Sprint N+4 | R-4 + 真 alpha source 孵化（funding skew spread / OI delta panel） |
| Sprint N+5 | First per-alpha-source supervised live promotion |

**最早 supervised live 重定義**：不是「整 system live_reserved」，而是「first alpha source 拿到 budget slice」。預計 6-8 sprint，與 88 finding patch 估的 6-8 sprint 同數量級，**但長期收斂可能性提升**（不是修一條已知必虧路徑）。

---

## 結語：對 operator 的直白話

當前 88 finding 都是真的問題、必須修。但**只修 88 finding 不會盈利**，因為：
- 5 策略全是 TA → 即使 Donchian shift(1) 修了 / Kelly tier config 化了 / DSR/PBO wired，**仍是 5 個結構同質 TA 策略**互相 cannibalize
- 每個 alpha source 自身有 carrying capacity，5 個 TA 策略其實是**1 個 TA alpha 上的 5 種包裝**

architectural verdict：當前 5 策略不是「需要更好參數」，是**站在已無 alpha 的 territory**。架構必須讓系統能站到別的 territory（funding skew / orderflow imbalance / liquidation cascade / cross-asset basis），這需要 R-1 R-2 R-3 三個 architectural amendment，不是 88 finding patch list。

「先修完 88 再說架構」**是錯的順序** — 它讓系統繼續精煉一條結構性無回報路徑，每 sprint 燒治理工時但 gross PnL 不會轉正。**正確順序：W-AUDIT-2/-5 維護同時並行 R-1 spec → R-1 IMPL 後其他 wave priority 自然 reorder**。

`funding_arb V2 退役`（ADR-0018）是好決策，因為證明了「策略無 alpha 就退役」的治理機制存在 — 但**機制存在 ≠ 結構性會孵化新 alpha**。下一步：建立 alpha 生產的 architectural forcing function，否則 funding_arb 退役後空缺位永遠不會被有 edge 的東西填上。

---

**報告路徑**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md`

**結論性報告同步至**：`srv/docs/CCAgentWorkSpace/Operator/`（PM 收到後處理）

**PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md**
