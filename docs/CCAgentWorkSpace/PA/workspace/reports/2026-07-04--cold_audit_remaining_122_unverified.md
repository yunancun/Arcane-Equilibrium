# 7.4 122 remain — 冷審計 R2 未複核殘餘清單(單證人,修前自核)

> 出處:2026-07-03~04 冷酷對抗審計 R2(`wf_6dc68c2f-4a0` + `wf_63ba9216-071`)168 條 finding 中,47 條已進對抗複核並由 PA plan(P0×3/P1×11/P2×15)收編;本檔為其餘 **122 條 MEDIUM/LOW/INFO 單證人條目**——未經質疑者投票,預期含一定 false positive。
>
> **修復規則(Codex/E1 必讀)**:①每條修前先自行核實 anchor 屬實;屬實→修,不屬實→在本檔該條後標 `NO-OP: <理由>`,不得為消條目改碼;②觸風險語義/gate/sizing/live 邊界的條目一律不在本檔授權範圍(那些已單列 PA plan P2 具名項與 D 決策);③文檔/索引類建議排在 P1-7(TODO/memory 瘦身)之後修,防錨點漂移白工;④live fail-closed 5 gates + 9 安全不變量不碰。
> 完成標記:逐條前綴 `[x]` 或 `NO-OP`;全檔清零後在 TODO 指針行標 DONE。

## CC(10 條)

- [ ] **[MEDIUM]** TODO §0 runtime 事實漂移：repo head/PID/sync 狀態全部 stale（G6-04）
  - anchor: `TODO.md §0 'Runtime sync/materialization state'` | dt: drift-source-runtime, doc-stale
- [ ] **[MEDIUM]** 2000 行硬上限 9 個生產檔超標且無 documented exception
  - anchor: `discovery_loop.py / runtime_runner.py / status.py / step_4_5_dispatch.rs / intent_processor/mod.rs` | dt: readability-debt
- [ ] **[LOW]** earn_router 審計 lineage 占位 sentinel governance_approval_id=0
  - anchor: `earn_router.rs::governance_approval_id` | dt: lineage-gap
- [ ] **[LOW]** AgentTool 訪問分類與代碼自述雙向漂移（DreamEngine/OpportunityTracker）
  - anchor: `dream_engine.py::persist_dream_insights` | dt: doc-stale, other
- [ ] **[LOW]** Demo API key 遮罩片段常態化寫入 TODO.md
  - anchor: `TODO.md §0 'Bounded Demo soak runtime state' row` | dt: secret-leak
- [ ] **[LOW]** standing auth 過期後內嵌 status 仍為 STANDING_DEMO_AUTHORIZATION_ACTIVE
  - anchor: `standing_demo_operator_authorization.json::status` | dt: fake-success, schema-issue
- [ ] **[INFO]** advisory 面 max_retries=1 為合規例外（指紋掃描假陽性候選）
  - anchor: `l2_advisory_orchestrator.py::max_retries` | dt: other
- [ ] **[INFO]** IMPL-A dispatch-edge containment 源碼已進 runtime checkout、running binary 未含
  - anchor: `demo_learning_lane_soak_gate.rs / OPENCLAW_BOUNDED_PROBE_SOAK flag` | dt: drift-source-runtime
- [ ] **[INFO]** Mac memory/ 髒樹懸掛：R4 巡檢 8 組 MERGE 未 commit（44 modified + 47 untracked）
  - anchor: `memory/ (uncommitted R4 merge output)` | dt: other
- [ ] **[INFO]** 硬邊界 + 9 安全不變量全面 PASS（正向確認）
  - anchor: `live_authorization.rs / OPENCLAW_ALLOW_MAINNET / max_retries` | dt: other

## FA(7 條)

- [ ] **[MEDIUM]** cost_gate_learning_lane 治理 helper 面積膨脹：86 檔 / 4.4MB，一次性 packet helper 邏輯重複
  - anchor: `helper_scripts/research/cost_gate_learning_lane/` | dt: readability-debt, duplicate-logic
- [ ] **[LOW]** SCRIPT_INDEX.md 未收錄 7/86 lane helpers（違 CLAUDE §七）
  - anchor: `helper_scripts/SCRIPT_INDEX.md` | dt: index-broken, doc-stale
- [ ] **[LOW]** 治理 .docx→.md 轉檔 SOP 腳本不存在（governance_docx_to_md.py 缺）
  - anchor: `.claude/skills/spec-compliance::governance_docx_to_md.py` | dt: doc-stale, other
- [ ] **[INFO]** alpha_tournament orchestrator 仍為 stub（進化環節主要缺口，register 標註誠實）
  - anchor: `tournament_orchestrator.py::ranking_logic` | dt: dead-code, evolution-blocker
- [ ] **[INFO]** Stage0R residual preflight dormant：flag 預設 0 且 cron 未安裝
  - anchor: `OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT` | dt: other
- [ ] **[INFO]** TODO.md v738 runtime facts 已被 overnight 進展超越（PID/writer/head 均變）
  - anchor: `TODO.md::Source/runtime pointer` | dt: doc-stale, drift-source-runtime
- [ ] **[INFO]** 硬邊界正向驗證：無違反（mainnet=0 / stock_etf GET-only / 無硬編碼路徑 / .claude 完整 / DEPRECATED 紀律良好）
  - anchor: `OPENCLAW_ALLOW_MAINNET` | dt: other

## E3(8 條)

- [ ] **[LOW]** POLICY-1 Gate-5 (signed authorization.json) exemption is triggered by a self-asserted client boolean with no server-side halt-state verification
  - anchor: `operator_override` | dt: auth-bypass, over-gate, missing-gate
- [ ] **[LOW]** _attach_live_token_if_live mints a live capability token unconditionally when engine=='live'; 5-gate safety depends on every caller being operator-gated (fragile invariant)
  - anchor: `_attach_live_token_if_live` | dt: auth-bypass, evolution-blocker, test-blindspot
- [ ] **[INFO]** IBKR stock_etf lane is dormant source fixtures — no live broker surface (confirmed clean per ADR-0048)
  - anchor: `ibkr_live_enabled` | dt: other
- [ ] **[INFO]** Bybit credential write path (POST /settings/api-key/{slot}) is well-hardened
  - anchor: `save_api_key` | dt: other
- [ ] **[INFO]** Strategy-write / promotion / layer2-cost write endpoints all operator-gated; baseline HIGH-1 remains closed
  - anchor: `_require_strategy_write` | dt: other
- [ ] **[INFO]** f-string SQL in ml_routes.py:238 and earn_routes.py:988 are parameterized (false-positive candidates)
  - anchor: `list_model_registry` | dt: other
- [ ] **[INFO]** shell=True in deploy helper runtime_source_reconcile_apply.py is shlex.quote-protected and operator-gated
  - anchor: `LocalShellClient.run_shell` | dt: readability-debt
- [ ] **[INFO]** Core security baselines intact since 976d420e — 5-gate SSOT, IPC socket 0600+HMAC, CORS/rate-limit, secret hygiene, production-unsafe-free
  - anchor: `verify_signed_authorization` | dt: other

## BB(9 條)

- [ ] **[MEDIUM]** 哨兵 heartbeat 無年齡監控消費者，停擺 6 天零告警
  - anchor: `cron_heartbeat/bybit_announcement_sentinel.last_fire` | dt: test-blindspot, missing-gate
- [ ] **[MEDIUM]** Rust client rate 註釋三處三值 + per-prefix 分組模型與官方 per-endpoint 配額結構不符（BB-2/BB-3 持續）
  - anchor: `RateLimitGroup / RateLimitState::default / group_backoff_threshold` | dt: doc-stale, readability-debt
- [ ] **[MEDIUM]** Python client live_demo 憑證解析仍允許 env-var fallback，與 Rust P1-08 live-slot 禁令 drift（latent provenance gap）
  - anchor: `_resolve_credentials（is_mainnet 判斷應為 is_live_slot）` | dt: drift-source-runtime, auth-bypass
- [ ] **[LOW]** 字典 funding 章 blanket「每 8 小時結算一次」殘留，與 per-symbol fundingInterval 正確段矛盾
  - anchor: `dict get_funding_history 服務描述（line 154）` | dt: doc-stale
- [ ] **[LOW]** live_authorization now_ms duration_since 失敗 fallback=0 理論 expiry fail-open（BB-5 持續 nit）
  - anchor: `live_authorization.rs::now_ms（unwrap_or(0)）` | dt: over-gate, other
- [ ] **[INFO]** BYBIT_ORDER_LINK_ID_MAX_LEN=36 比 Bybit linear 45 上限緊 9 字元（保守方向）
  - anchor: `BYBIT_ORDER_LINK_ID_MAX_LEN` | dt: over-gate
- [ ] **[INFO]** 公開資料 helper 多處硬編 mainnet base URL（public-only，無合規風險）
  - anchor: `_BYBIT_PUBLIC_BASE_URL / DEFAULT_BASE_URL` | dt: hardcoded-config, readability-debt
- [ ] **[INFO]** demo secret slot 存在未被讀取的 bybit_endpoint 檔（dead config）
  - anchor: `secret_files/bybit/demo/bybit_endpoint` | dt: dead-code
- [ ] **[INFO]** PASS 面彙總：核心交易路徑 0 ship-stop（HMAC 簽名/4-env 映射/LIVE-GUARD-1 三閘 runtime 實證/gate5 HMAC/retCode fail-closed/withdraw 0 引用/30d changelog 0 breaking/rate 30d 0 hit/25 pinned 0 delisting 中招）
  - anchor: `None` | dt: other

## QC(12 條)

- [ ] **[MEDIUM]** 學習面 best-of-K 選擇（43 side-cells × 多 horizon）無多重比較控制，headline 數字系統性上偏
  - anchor: `horizon_stability_scorecard` | dt: test-blindspot, math-error
- [ ] **[MEDIUM]** per_trade_risk_pct 為 fraction（0.1=10%）與同區塊 percent 欄位混雜；4 處 survival-floor 註解寫 2% 低估實際 5 倍
  - anchor: `per_trade_risk_pct` | dt: schema-issue, doc-stale, readability-debt
- [ ] **[MEDIUM]** dynamic_sizing band [0.01,0.05] 與 per_trade_risk_pct=0.1 無交叉驗證：暖機 10% → 50 筆平倉後靜默腰斬至 ≤5%；反向配置存在 fail-open 抬升結構
  - anchor: `dynamic_sizing.max_pct` | dt: missing-gate, schema-issue, drift-source-runtime
- [ ] **[MEDIUM]** ADPE explore keepalive 的 cost-viability 篩選 edge_evidence_slippage=0.0，違反保守成本硬約束
  - anchor: `edge_evidence_slippage` | dt: hardcoded-config, math-error
- [ ] **[LOW]** funding_harvest 年化寫死 8h×3×365，未讀 per-symbol fundingInterval
  - anchor: `annualized_funding` | dt: bybit-incompat, hardcoded-config
- [ ] **[LOW]** ewma_vol log-return 無 w[0]>0 guard（與同檔 hurst filter 不一致）——2026-04-24 LOW 延續 open
  - anchor: `ewma_vol` | dt: math-error, readability-debt
- [ ] **[LOW]** close-maker backoff/cascade 6 常數仍硬編碼（前輪 P3 延續 open）
  - anchor: `CLOSE_MAKER_BACKOFF_INITIAL_MS` | dt: hardcoded-config
- [ ] **[LOW]** git 內 settings/edge_estimates.json 為 2026-04-20 化石，與 runtime 同名檔（2026-07-03, 221 keys）分歧 2.5 個月
  - anchor: `settings/edge_estimates.json` | dt: drift-source-runtime, lineage-gap
- [ ] **[INFO]** _rank_score 混量綱加總（bps + pct/2 + log10(n)·5 + 1000/100/50/40 tier bonus），常數敏感性未文檔化
  - anchor: `_rank_score` | dt: readability-debt
- [ ] **[INFO]** runtime edge_estimates _meta.n_cells=45 vs 實際 221 keys（113 real+108 proxy），meta 語意未自述
  - anchor: `_meta.n_cells` | dt: schema-issue
- [ ] **[INFO]** 系統態勢確認（非缺陷）：113 real cells 0 過 WF+PSR/DSR 驗證、101/113 EV<0、median n=6——系統誠實自報無已驗證 edge；樣本饑餓仍第一約束
  - anchor: `validation_config` | dt: other
- [ ] **[INFO]** 正向確認：前兩輪 QC audit 全部 P0/P1 已修復（donchian_prior / OU 殘差 σ / Kelly Wilson-LB+config / fast_track+slippage+cost_gate TOML 化 / confluence load guard / 年化×365 測試固化 / 黑名單 0 違規）
  - anchor: `donchian_prior` | dt: other

## MIT(13 條)

- [ ] **[MEDIUM]** quantile trainer embargo fail-open：<50 樣本時靜默跳過且不入 acceptance report
  - anchor: `train_quantile_trio` | dt: leakage, test-blindspot
- [ ] **[MEDIUM]** V141 kline truth-drift guardrail 從未啟動：0 row/16 天，cron 未裝且哨兵 check_91 又因 F-3 停擺（雙盲）
  - anchor: `kline_calibration_cron.sh` | dt: missing-gate, drift-source-runtime
- [ ] **[MEDIUM]** regime 軸雙缺陷未修且惡化：aeg_regime_labels stale 32 天 + bayesian_posteriors.regime 實值=engine_mode
  - anchor: `bayesian_posteriors.regime` | dt: schema-issue, drift-source-runtime, doc-stale
- [ ] **[MEDIUM]** mlde_shadow_advisor 每日 run 全 error（QueryCanceled 5s statement timeout）— MLDE advisory lane 死
  - anchor: `_AGGREGATE_BASE_SQL` | dt: perf-hotpath, drift-source-runtime
- [ ] **[MEDIUM]** linucb_trainer 以 arms=0/total_pulls=0 回報 ok — 空訓練標成功
  - anchor: `linucb_trainer` | dt: fake-success, test-blindspot
- [ ] **[MEDIUM]** V142/V143/V144 header 聲稱 Guard A 但 body 無 Guard DO-block（V023 silent-noop 防線缺口 + 注釋不誠實）
  - anchor: `V142/V143/V144 CREATE TABLE IF NOT EXISTS` | dt: missing-gate, doc-stale, untruthful-ai
- [ ] **[LOW]** scorer label winsorization 用全窗口分位數（含未來 fold）— 輕度 cross-fold statistic leak
  - anchor: `generate_labels` | dt: leakage
- [ ] **[LOW]** 訓練 engine_mode 默認 demo，與穩定規則 IN('live','live_demo') 文檔漂移
  - anchor: `OPENCLAW_ML_CRON_TRAINING_ENGINE_MODES` | dt: doc-stale, hardcoded-config
- [ ] **[LOW]** V142/V143 compression/retention policy 無 timescaledb extension guard（V006 已知缺陷複製）
  - anchor: `add_compression_policy` | dt: schema-issue, duplicate-logic
- [ ] **[INFO]** V146 未 apply（prod sqlx head=145）— V145 誤導性 markout COMMENT 仍活在 prod
  - anchor: `trading.fills.maker_markout_bps COMMENT` | dt: doc-stale
- [ ] **[INFO]** market.l1_events 28GB 超 PA realistic 儲存預估 4-9x（硬上界 ~26GB 亦已破）且 recorder 監測 lane 已死
  - anchor: `OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL` | dt: perf-hotpath, doc-stale
- [ ] **[INFO]** decision_features 14.8M rows（99.9% reject）以 ~55k/day 膨脹 — 下游查詢成本共同根源
  - anchor: `learning.decision_features` | dt: perf-hotpath, schema-issue
- [ ] **[INFO]** ML 決策層斷線三件套維持原狀：resolver 0 caller / combine layer mock / select_next_arm 0 consumer（06-14 結論重驗不變）
  - anchor: `resolve_latest_production_artifact` | dt: dead-code, evolution-blocker

## AI-E(8 條)

- [ ] **[MEDIUM]** Layer2CostTracker 跨進程預算競態：4 uvicorn workers 共寫 JSON 無 file lock（新發現，dormant）
  - anchor: `layer2_cost_state.json / _lock` | dt: missing-gate, duplicate-logic
- [ ] **[MEDIUM]** AI-E 報告 lineage gap：memory 索引的 06-13/06-14 兩份報告在 Mac/Linux/git 全史皆不存在
  - anchor: `AI-E/memory.md 報告索引` | dt: lineage-gap, doc-stale
- [ ] **[LOW]** 每日成本快照採集腿不存在（06-14 F5 以刪 cron 而非補實現收場）
  - anchor: `daily_cost_snapshot.sh（absent）` | dt: missing-gate
- [ ] **[LOW]** DOC-08 內文 stale：L1 寫 Ollama 7B（實際 9B/27B）、L2 per-call 估價基於退役定價
  - anchor: `DOC-08 §1 模型表` | dt: doc-stale
- [ ] **[LOW]** cost_edge_ratio 三同名三義未收斂（06-14 F3 殘留命名債）
  - anchor: `cost_edge_ratio / trigger_threshold` | dt: readability-debt, math-error
- [ ] **[INFO]** GUI AI tab ROI tiles 永久 '--'（誠實空顯示非 fake-success）；adaptive_base_daily_usd=8 無風險（min 束於 2.0）
  - anchor: `roi-ratio / adaptive_base_daily_usd` | dt: dead-code
- [ ] **[INFO]** PASS 面：定價三軸對齊且 07-03 官方複驗仍準；上輪 4 修復閉環確認；新模型 Sonnet 5 intro $2/$10 省 33% 機會窗至 08-31
  - anchor: `OPENCLAW_CLAUDE_TEACHER_MODEL / ai_pricing.yaml` | dt: other
- [ ] **[INFO]** 零成本承諾複驗：DreamEngine 0 LLM import、CognitiveModulator 300-3600s 界內；advisor 心跳 ~1.4k row/day 純噪音寫入
  - anchor: `cost_edge_advisor_log heartbeat` | dt: perf-hotpath, other

## E5(10 條)

- [ ] **[MEDIUM]** tick 熱路徑每 tick 深拷貝 4 個 panel snapshot（panel 60s 才更新）
  - anchor: `try_clone_panel_snapshot` | dt: perf-hotpath
- [ ] **[MEDIUM]** _percentile 同名異契約 ×6（q∈[0,1] vs p∈[0,100] + NaN 過濾不一致）
  - anchor: `_percentile` | dt: duplicate-logic, math-error
- [ ] **[MEDIUM]** layer2_tools 3/4 SearchProvider 在 async def 內同步阻塞（latent，0 prod caller）
  - anchor: `LocalLLMWebSearchProvider.search / LocalLLMSearchProvider.search / WebPilotSearchProvider.search` | dt: perf-hotpath, dead-code
- [ ] **[MEDIUM]** helper_scripts/research 356 檔 / 184.8k LOC 一次性 evidence 腳本無 active/stale 歸檔機制
  - anchor: `SCRIPT_INDEX.md（1588 行無 active/historical 分節）` | dt: readability-debt, doc-stale
- [ ] **[LOW]** cost_gate_learning_lane_cron.sh 1980 行 bash 僅 6 函數，距硬限 <1%
  - anchor: `cost_gate_learning_lane_cron.sh` | dt: readability-debt
- [ ] **[LOW]** ipc_client 單連線 + asyncio.Lock 串行全部 engine IPC（吞吐 ceiling 記錄）
  - anchor: `EngineIPCClient._lock` | dt: perf-hotpath, other
- [ ] **[LOW]** pg_stat_statements 未安裝——PG 調參與 seq scan 歸因無法證據驅動
  - anchor: `shared_preload_libraries` | dt: index-broken, other
- [ ] **[INFO]** 根目錄歷史大 md（AE_INVENTORY 422KB / CLAUDE_CHANGELOG 1.4MB）
  - anchor: `AE_INVENTORY_CONSOLIDATED.md` | dt: doc-stale
- [ ] **[INFO]** （正面）前輪 F2 LTO/F3 urlopen/PERF-1 5m gate 已修；drift-gate 死循環 source 側已解待 v739 實走
  - anchor: `lto / codegen-units / standing_envelope_post_approval_drift_gate` | dt: over-gate, evolution-blocker
- [ ] **[INFO]** （基線）Linux engine 運行時資源快照
  - anchor: `openclaw-engine release binary` | dt: other

## A3(14 條)

- [ ] **[MEDIUM]** Stock/ETF IBKR tab：18 個第一屏 metric 卡全英文工程術語、零中文、零解說 — 全 console 唯一無雙語的 tab，且認知密度超標
  - anchor: `se-metric` | dt: readability-debt, other
- [ ] **[MEDIUM]** Rust 引擎宕機無全域跨 tab 告警：engine_alive 只在 system tab 一張 metric 卡 + agents tab chip，console 側欄/header 無引擎狀態燈
  - anchor: `loadEngineAlive` | dt: missing-gate, other
- [ ] **[MEDIUM]** 源碼-runtime 漂移：本輪全部『已修復』判定僅對 Mac 源碼 head 成立，trade-core runtime 落後 origin/main 164 commits，線上 console 是否含這些修復未驗證
  - anchor: `BUILD_TS` | dt: drift-source-runtime
- [ ] **[LOW]** 側欄footer『Auto-refresh 15s』與實際 SIDEBAR_REFRESH_MS=30000 不符
  - anchor: `SIDEBAR_REFRESH_MS` | dt: doc-stale, hardcoded-config
- [ ] **[LOW]** 破壞性操作 modal 缺『具體影響』數據：Demo/Live close-all 確認框無持倉數量與預估 UPL
  - anchor: `doDemoCloseAll` | dt: other
- [ ] **[LOW]** 審計感知 UX（ux-checklist §5）系統性缺席：寫操作 toast 無 trace_id、無『最近 5 次 actor+ts+結果』、多數 dashboard 無採集時間 footer
  - anchor: `ocToast` | dt: lineage-gap, other
- [ ] **[LOW]** 簡繁中文混排遍佈治理/風控視圖，同一畫面同一概念兩種字形
  - anchor: `gov-sm-note` | dt: readability-debt
- [ ] **[LOW]** 首次進入 console 僅見 core group 3 tabs（含最生僻的 Stock/ETF），交易/治理 group 默認折疊；Global Mode Control 卡藏於 dev-support 開關後
  - anchor: `TAB_GROUP_DEFAULT_OPEN` | dt: duplicate-logic, over-gate, other
- [ ] **[LOW]** UTC+local 雙時區標註基本缺席：console 時鐘僅 zh-CN 本地時間，全 GUI 僅 4 處 UTC 字樣
  - anchor: `clock` | dt: other
- [ ] **[LOW]** 設置/風控殘留英文-only placeholder 與 toast
  - anchor: `cost-note` | dt: readability-debt
- [ ] **[INFO]** A3 總評 7.5/10（術語友好 7 / 操作流完整 7 / 學習曲線 7.5 / 錯誤提示 8）— 較 2026-05-30 的 8.0 下調
  - anchor: `a3_score_v20260703` | dt: other
- [ ] **[INFO]** Legacy GUI /gui（index.html）仍註冊路由並保留 disabled paper 下單表單
  - anchor: `gui_index` | dt: dead-code
- [ ] **[INFO]** tab-governance.html:1159-1160 stale 註釋仍引用不存在的 loadGovernance()（2026-05-30 advisory 未清）
  - anchor: `loadGovernance` | dt: doc-stale
- [ ] **[INFO]** 正向確認：既往 A3 findings 全數修復且守住 — A3-GUI-009/010/011 已修（源碼含 A3 編號註釋）、native confirm()/prompt() 全滅、SM 術語加解說、學習 Tab 雙語、engine_alive 上第一屏、Demo close-all modal 補齊
  - anchor: `classifyLiveMutation` | dt: other

## R4(13 條)

- [ ] **[MEDIUM]** README Control Console tab 表 ⇄ GUI nav 漂移：缺 `stock-etf`、`charts`，仍列已下架的 `phase4`
  - anchor: `README.md::Control Console tab 表` | dt: doc-stale, drift-source-runtime
- [ ] **[MEDIUM]** .claude/agents/R4.md 與 R4 profile.md 仍以『docs/README.md 底部索引』為審計目標，該索引已遷出至 _indexes/document_index.md
  - anchor: `.claude/agents/R4.md::核心審計領域/核查清單` | dt: hardcoded-config, doc-stale
- [ ] **[MEDIUM]** _indexes/document_index.md 與 initiative_index.md 零 2026-07 條目；operator 已批准之設計 spec 與 E4 回歸報告未登記
  - anchor: `docs/_indexes/document_index.md` | dt: index-broken, doc-stale
- [ ] **[LOW]** SPECIFICATION_REGISTER ADR 節標題停在 0047、表已含 0048；docs/README.md 寫『ADR 0001-0047』實有 0048
  - anchor: `SPECIFICATION_REGISTER.md::ADR 節標題` | dt: doc-stale, hardcoded-config
- [ ] **[LOW]** register Cross-Reference Summary『Active REF specifications = 19』與 REF 表狀態不吻合
  - anchor: `SPECIFICATION_REGISTER.md::Cross-Reference Summary` | dt: doc-stale, math-error
- [ ] **[LOW]** SCRIPT_INDEX.md『最新補充』段延續巨型敘事模式（前輪 R4-2026-IDX-04 持續）；標頭日期與 changelog 相差一天
  - anchor: `helper_scripts/SCRIPT_INDEX.md::最新補充` | dt: readability-debt, doc-stale
- [ ] **[LOW]** CLAUDE_REFERENCE.md 停更 82 天（2026-04-12）且無 STALE 快照 banner，仍自稱含『Authoritative checkers』
  - anchor: `docs/CLAUDE_REFERENCE.md::header` | dt: doc-stale
- [ ] **[LOW]** docs/README.md 路由表覆蓋缺口：docs/agents/ 表僅列 3/9 檔；docs 根層 KNOWN_ISSUES.md / lessons.md / CLAUDE_REFERENCE.md 不在目錄樹
  - anchor: `docs/README.md::稳定入口索引` | dt: index-broken, doc-stale
- [ ] **[LOW]** R4 自身 memory.md 報告索引停更：僅列 2/16 份報告；『項目上下文』段殘留 2026-04-24 runtime 數字未標 stale
  - anchor: `docs/CCAgentWorkSpace/R4/memory.md::報告索引` | dt: doc-stale, index-broken
- [ ] **[LOW]** TODO §4 handoff 命令引用已 superseded 的 v693 /tmp artifacts，且 `sed 1,180p` 截不到 §3/§4 自身
  - anchor: `TODO.md::§4 Handoff Commands` | dt: doc-stale, drift-source-runtime
- [ ] **[LOW]** README 內部測試計數三口徑並存（crate 註記 ~400/~2400 vs register ~3,600+ Rust vs README ~6,500+ 總）
  - anchor: `README.md::项目结构 rust/ 註記` | dt: doc-stale, hardcoded-config
- [ ] **[INFO]** A3.md 配置內嵌 GUI 現狀觀察未標採集日（『學習系統 Tab 6 個核心指標全英文』等）
  - anchor: `.claude/agents/A3.md::已知問題示例` | dt: hardcoded-config, doc-stale
- [ ] **[INFO]** （正向核驗，無缺陷）前輪 P1/P3 修復保持 + 各 SSOT 對齊抽查通過
  - anchor: `None` | dt: other

## E4(10 條)

- [ ] **[MEDIUM]** (補審) F4 ledger all-or-nothing 解析+跨語言型別/時間格式容忍不對稱,單一壞行=Rust learning lane 靜默死亡;無毒行/torn-line 測試
  - anchor: `LedgerRecord::from_jsonl_str` | dt: test-blindspot, schema-issue, other
- [ ] **[MEDIUM]** (補審) F9 v739 前置:runtime engine binary=06-29 build,IMPL-A/IMPL-B 已測代碼未上線;凍結事實『無獨立 engine 進程』已過期
  - anchor: `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED` | dt: drift-source-runtime, other
- [ ] **[MEDIUM]** (補審) F5 cutover 閘鍵 BYBIT_MODE/BYBIT_CONNECTOR_WRITE_ENABLED 零 runtime 強制消費者——治理語義純表示層
  - anchor: `BYBIT_CONNECTOR_WRITE_ENABLED` | dt: doc-stale, missing-gate
- [ ] **[MEDIUM]** (補審) F7 markout exit 價無 max-delay 上界(entry 有 5min 上界,exit 取任意遲到觀測),學習閾值輸入可被觀測缺口污染;無邊界測試
  - anchor: `_build_markout_outcome_records` | dt: math-error, leakage, test-blindspot
- [ ] **[LOW]** (補審) F10 engine_mode 正規化不對稱:Rust trim+to_ascii_lowercase vs Python exact dict-get
  - anchor: `_candidate_bound_active_order_link_id_is_valid` | dt: duplicate-logic, drift-source-runtime
- [ ] **[LOW]** (補審) F11 is_bybit_safe_order_link_id_for_engine_mode(4 段版)零生產 caller
  - anchor: `is_bybit_safe_order_link_id_for_engine_mode` | dt: dead-code
- [ ] **[LOW]** (補審) F12 4/5 cron pin stale OPENCLAW_EXPECTED_SOURCE_HEAD=00a78d92(runtime head 262596c6)+兩 cron log 0-byte,head-gated cron 實際行為未驗
  - anchor: `OPENCLAW_EXPECTED_SOURCE_HEAD` | dt: drift-source-runtime, other
- [ ] **[LOW]** (補審) F14 probe_outcome 以 admission 時價 markout 生成,未與真 fill 對賬(admitted-but-unfilled 同權計入學習證據)
  - anchor: `build_probe_outcome_records` | dt: leakage, test-blindspot
- [ ] **[INFO]** (補審) F13 學習 SSOT(plan+ledger 472MB)全在 /tmp/openclaw,reboot 即滅(corroboration,主審計他軸已有 data-dir 發現)
  - anchor: `OPENCLAW_DATA_DIR` | dt: lineage-gap
- [ ] **[INFO]** (補審) 覆蓋充分面(公平雙向聲明,非缺陷):retCode/timeout/fail-closed/auth-expiry 單語言層無新增盲區
  - anchor: `None` | dt: other

## TW(8 條)

- [ ] **[MEDIUM]** (補審) Operator/ 全文鏡像層於 07-03 主審計批次第三度再現（6/6 對全文複製）
  - anchor: `docs/CCAgentWorkSpace/Operator/2026-07-03--*.md` | dt: duplicate-logic, doc-stale
- [ ] **[MEDIUM]** (補審) Operator/ 目錄用途漂移：過程性 checkpoint/loop-state 記錄佔據 operator 決策通道
  - anchor: `docs/CCAgentWorkSpace/Operator/README.md::存放規則` | dt: doc-stale, other
- [ ] **[MEDIUM]** (補審) 同一敘事 3-4 處全文重述（SCRIPT_INDEX + CLAUDE_CHANGELOG + Operator brief + .codex/WORKLOG）
  - anchor: `SCRIPT_INDEX.md:6 ↔ CLAUDE_CHANGELOG.md:12` | dt: duplicate-logic, readability-debt
- [ ] **[LOW]** (補審) 檔名規範 rule-vs-practice 死字：hyphen-desc ≥64 檔違「下划线连接」+ role-infix 跨輪不一致（同批 4 種風格）
  - anchor: `docs/README.md::文件命名规范` | dt: doc-stale, other
- [ ] **[LOW]** (補審) worklogs/ lane 事實休眠（05 月 2 檔/06 月 1 檔/07 月 0）但 docs/README 仍標現役
  - anchor: `docs/README.md::worklogs 節` | dt: doc-stale
- [ ] **[LOW]** (補審) README.md Console tab 表殘留：仍列已退役 phase4、缺 charts（06-14 已 flag 未指派，carried 20 天）
  - anchor: `README.md:40::tab 表` | dt: doc-stale
- [ ] **[INFO]** (補審) cold-audit 報告族命名穩定無應併未併；pm_final 歸檔節奏不一致（05 輪已 archive、06-14/07-03 仍在 workspace）
  - anchor: `docs/archive/2026-05-*--cold_audit_pm_final.md` | dt: other
- [ ] **[INFO]** (補審) docs/README.md:174「ADR 0001-0047」stale（0048 已存在）— R4 索引軸重疊，掛帳不展開
  - anchor: `docs/README.md:174` | dt: index-broken, doc-stale
