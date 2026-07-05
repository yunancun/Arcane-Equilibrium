# 7.4 122 remain — 冷審計 R2 未複核殘餘清單(單證人,修前自核)

> 出處:2026-07-03~04 冷酷對抗審計 R2(`wf_6dc68c2f-4a0` + `wf_63ba9216-071`)168 條 finding 中,47 條已進對抗複核並由 PA plan(P0×3/P1×11/P2×15)收編;本檔為其餘 **122 條 MEDIUM/LOW/INFO 單證人條目**——未經質疑者投票,預期含一定 false positive。
>
> **修復規則(Codex/E1 必讀)**:①每條修前先自行核實 anchor 屬實;屬實→修,不屬實→在本檔該條後標 `NO-OP: <理由>`,不得為消條目改碼;②觸風險語義/gate/sizing/live 邊界的條目一律不在本檔授權範圍(那些已單列 PA plan P2 具名項與 D 決策);③文檔/索引類建議排在 P1-7(TODO/memory 瘦身)之後修,防錨點漂移白工;④live fail-closed 5 gates + 9 安全不變量不碰。
> 完成標記:逐條前綴 `[x]` 或 `NO-OP`;全檔清零後在 TODO 指針行標 DONE。

> **2026-07-05 全量處置完成(operator 裁 B①)**:12 組領域 agent 並行自核 → **41 FIXABLE / 70 NO_OP / 11 OUT_OF_SCOPE**。FIXABLE 由 5 批 writer(docs/gui/ml/rust/cron)+A/C 落地於 integration/remain-0705。**Phase-2 例外(FIXABLE 但未即修)**:E5-1 tick panel snapshot clone=microbench 證 epoch-cache 省不掉(退 PA 開 scoped ticket,優先 liquidation_pulse);SCRIPT_INDEX 229 段 run-on byte-move=需獨立 shell 守恆步驟(deferred);E5-4 helper active/historical curation=需 E5/QC domain 判斷(deferred);worklogs dormant(TW-5)=anchor 不成立(頂層實有 31 現役檔)已改判 NO-OP;QC-2 risk_config 單位混雜=與 C(band 擴)同檔,coordinate 後另處置。


## CC(10 條)

- [x] **NO-OP** **[MEDIUM]** TODO §0 runtime 事實漂移：repo head/PID/sync 狀態全部 stale（G6-04）
  - NO-OP(2026-07-05 自核): anchor 部分屬實但已被修復波 P1-7(TODO 瘦身)+P0-RUNTIME-EXECUTION-IDENTITY 解掉。實測 wt HEAD=e29adde76 的 TODO.md：Source pointer 已更新為 c0c49deeb 並標『已部署上線 2026-07-05』，healthz boot_sha=repo_head=c0c49d…
  - anchor: `TODO.md §0 'Runtime sync/materialization state'` | dt: drift-source-runtime, doc-stale
- [x] **FIXED** **[MEDIUM]** 2000 行硬上限 9 個生產檔超標且無 documented exception
  - FIXED(2026-07-05 自核): anchor 屬實：實測 wt 內 >2000 行生產檔共 9 個(discovery_loop.py 5954/runtime_runner.py 4500/profitability_path_scorecard.py 3789/fill_sim.py 2796/engine_watchdog.py 2412/commands.rs 2266/statu…
  - anchor: `discovery_loop.py / runtime_runner.py / status.py / step_4_5_dispatch.rs / intent_processor/mod.rs` | dt: readability-debt
- [x] **OUT-OF-SCOPE** **[LOW]** earn_router 審計 lineage 占位 sentinel governance_approval_id=0
  - OUT-OF-SCOPE(2026-07-05 自核): anchor 屬實：earn_router.rs:376 `let governance_approval_id: i64 = 0` 是有意的 documented sentinel(PA-DRIFT-6，line 366-376 註釋明確標 Wave D/E carry-over、『本 IMPL 文檔化此 sentinel 行為避 silent drift…
  - anchor: `earn_router.rs::governance_approval_id` | dt: lineage-gap
- [x] **FIXED** **[LOW]** AgentTool 訪問分類與代碼自述雙向漂移（DreamEngine/OpportunityTracker）
  - FIXED(2026-07-05 自核): anchor 屬實：skill 16-root-principles-checklist/SKILL.md:84 列『只讀：CognitiveModulator / DreamEngine』，但 program_code/local_model_tools/dream_engine.py:436 persist_dream_insights 明確做 PG I…
  - anchor: `dream_engine.py::persist_dream_insights` | dt: doc-stale, other
- [x] **NO-OP** **[LOW]** Demo API key 遮罩片段常態化寫入 TODO.md
  - NO-OP(2026-07-05 自核): anchor 不成立(false positive)：實測 TODO.md 內出現的是 sha256 hash 前綴片段(standing auth sha `8c891b4e...`)與 Demo slot sha12 `317f982c009f`——後者是憑證檔的 sha256 內容指紋前12位(遮罩/lineage 用途)，非 API key 明文。s…
  - anchor: `TODO.md §0 'Bounded Demo soak runtime state' row` | dt: secret-leak
- [x] **NO-OP** **[LOW]** standing auth 過期後內嵌 status 仍為 STANDING_DEMO_AUTHORIZATION_ACTIVE
  - NO-OP(2026-07-05 自核): anchor 描述屬實但 fake-success/schema-issue 判定不成立(false positive)。實測 helper_scripts/research/cost_gate_learning_lane/standing_demo_authorization.py:120-123+167-180：consumption readiness…
  - anchor: `standing_demo_operator_authorization.json::status` | dt: fake-success, schema-issue
- [x] **NO-OP** **[INFO]** advisory 面 max_retries=1 為合規例外（指紋掃描假陽性候選）
  - NO-OP(2026-07-05 自核): 正向確認 PASS 類，anchor 屬實。實測 l2_advisory_orchestrator.py:221 max_retries=1 是 advisory 平面(非交易)，line 235-237 註釋明確『與交易 max_retries=0 不同，為 fail-safe RETRY 態的有界重試』，line 34 明確『無 live-config …
  - anchor: `l2_advisory_orchestrator.py::max_retries` | dt: other
- [x] **NO-OP** **[INFO]** IMPL-A dispatch-edge containment 源碼已進 runtime checkout、running binary 未含
  - NO-OP(2026-07-05 自核): anchor 屬實(demo_learning_lane_soak_gate.rs 源碼在 wt e29adde76)但已被修復波 P0-RUNTIME-EXECUTION-IDENTITY(D1 受控重啟)解掉。此為 R2 審計 07-03(重啟前)的 drift-source-runtime 快照；TODO.md P0-RUNTIME 行實證：2026-…
  - anchor: `demo_learning_lane_soak_gate.rs / OPENCLAW_BOUNDED_PROBE_SOAK flag` | dt: drift-source-runtime
- [x] **NO-OP** **[INFO]** Mac memory/ 髒樹懸掛：R4 巡檢 8 組 MERGE 未 commit（44 modified + 47 untracked）
  - NO-OP(2026-07-05 自核): anchor 屬 Mac 開發機工作樹的未提交狀態(working-tree dirty state)，非本 clean worktree(e29adde76 HEAD，memory/ 為已提交乾淨狀態)可表達或修的對象。R2 審計描述的『44 modified + 47 untracked』是 Mac runtime working-tree 快照，需在 …
  - anchor: `memory/ (uncommitted R4 merge output)` | dt: other
- [x] **NO-OP** **[INFO]** 硬邊界 + 9 安全不變量全面 PASS（正向確認）
  - NO-OP(2026-07-05 自核): 純正向確認 PASS，anchor 全數屬實。實測：live_authorization.rs:131-132/183-187 有 Expired fail-closed(過期即 operator 須 renew)；live_spawn_assert.rs:28/217 mainnet 任一 symbol 非 BybitApi 即 reject+fail-c…
  - anchor: `live_authorization.rs / OPENCLAW_ALLOW_MAINNET / max_retries` | dt: other

## FA(7 條)

- [x] **OUT-OF-SCOPE** **[MEDIUM]** cost_gate_learning_lane 治理 helper 面積膨脹：86 檔 / 4.4MB，一次性 packet helper 邏輯重複
  - OUT-OF-SCOPE(2026-07-05 自核): anchor 屬實(實測 94 個 .py / 2.7MB,報告記 86檔/4.4MB 為修復波前數字),但該目錄 94 檔中 32 個直接觸 bounded_probe / decision_lease / standing_demo_authorization / standing_envelope_post_approval_drift_gate / …
  - anchor: `helper_scripts/research/cost_gate_learning_lane/` | dt: readability-debt, duplicate-logic
- [x] **FIXED** **[LOW]** SCRIPT_INDEX.md 未收錄 7/86 lane helpers（違 CLAUDE §七）
  - FIXED(2026-07-05 自核): anchor 屬實但數字更新:實測 lane 目錄 94 個 .py 中有 10 個(非報告所稱 7/86)未被 SCRIPT_INDEX.md 收錄。純文檔索引補登,不改任何 helper 邏輯、不觸 gate/sizing/live 語義;且 SCRIPT_INDEX.md 本身在 post-approval drift gate 豁免集內(docs-e…
  - anchor: `helper_scripts/SCRIPT_INDEX.md` | dt: index-broken, doc-stale
- [x] **FIXED** **[LOW]** 治理 .docx→.md 轉檔 SOP 腳本不存在（governance_docx_to_md.py 缺）
  - FIXED(2026-07-05 自核): anchor 屬實:SKILL.md:33 引用 helper_scripts/maintenance_scripts/governance_docx_to_md.py,但 find 該檔不存在,且 helper_scripts/ 內無任何 python-docx/Document() 轉換邏輯的等價腳本。惟實務上 22 個 .docx 均已有對應 .md(…
  - anchor: `.claude/skills/spec-compliance::governance_docx_to_md.py` | dt: doc-stale, other
- [x] **NO-OP** **[INFO]** alpha_tournament orchestrator 仍為 stub（進化環節主要缺口，register 標註誠實）
  - NO-OP(2026-07-05 自核): anchor 屬實:helper_scripts/alpha_tournament/tournament_orchestrator.py 47 行,docstring 明寫「Sprint 2 placeholder for Sprint 3+ M11」「當前實作=stub return 0;不寫 PG/不寫 file」,ranking_logic 欄位值="…
  - anchor: `tournament_orchestrator.py::ranking_logic` | dt: dead-code, evolution-blocker
- [x] **NO-OP** **[INFO]** Stage0R residual preflight dormant：flag 預設 0 且 cron 未安裝
  - NO-OP(2026-07-05 自核): anchor 屬實:residual_stage0r_preflight.py:128 明確「NEW flag(預設 OFF):未明確設 =1 一律…」+ ml_training_maintenance.py:416 三重 OFF(行為中性),cron 腳本 residual_stage0r_preflight_cron.sh 存在但預設 flag=0。這是…
  - anchor: `OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT` | dt: other
- [x] **NO-OP** **[INFO]** TODO.md v738 runtime facts 已被 overnight 進展超越（PID/writer/head 均變）
  - NO-OP(2026-07-05 自核): anchor 屬實有漂移:worktree HEAD=e29adde76,而 TODO.md:4 Source/runtime pointer 記 origin main=c0c49deeb(兩者不等,pointer 落後)。但此類 runtime pointer 漂移是結構性的:TODO §0 每輪 dispatch 由 PM 重寫、且 pointer 永…
  - anchor: `TODO.md::Source/runtime pointer` | dt: doc-stale, drift-source-runtime
- [x] **NO-OP** **[INFO]** 硬邊界正向驗證：無違反（mainnet=0 / stock_etf GET-only / 無硬編碼路徑 / .claude 完整 / DEPRECATED 紀律良好）
  - NO-OP(2026-07-05 自核): anchor 屬實且為純正向確認 PASS 類:(1) OPENCLAW_ALLOW_MAINNET 有 fail-closed gate 測試(bybit_rest_client_tests.rs:908 門#1 未設→構造必須 Err);(2) stock_etf 僅 fixture GET-only 方法(method_registry.rs get_…
  - anchor: `OPENCLAW_ALLOW_MAINNET` | dt: other

## E3(8 條)

- [x] **OUT-OF-SCOPE** **[LOW]** POLICY-1 Gate-5 (signed authorization.json) exemption is triggered by a self-asserted client boolean with no server-side halt-state verification
  - OUT-OF-SCOPE(2026-07-05 自核): Anchor FACT-confirmed: operator_override is a client-supplied request-body bool; when True the override branch (risk_routes.py:756-778) runs only four_gates_minus_authz_ok (live_pr…
  - anchor: `operator_override` | dt: auth-bypass, over-gate, missing-gate
- [x] **OUT-OF-SCOPE** **[LOW]** _attach_live_token_if_live mints a live capability token unconditionally when engine=='live'; 5-gate safety depends on every caller being operator-gated (fragile invariant)
  - OUT-OF-SCOPE(2026-07-05 自核): Anchor FACT-confirmed: risk_view_client.py:43-56 mints a method-bound live capability token whenever params.engine=='live', performing NO authorization itself (Python authorizer ->…
  - anchor: `_attach_live_token_if_live` | dt: auth-bypass, evolution-blocker, test-blindspot
- [x] **NO-OP** **[INFO]** IBKR stock_etf lane is dormant source fixtures — no live broker surface (confirmed clean per ADR-0048)
  - NO-OP(2026-07-05 自核): Positive confirmation, VERIFIED accurate: ibkr_live_enabled is hardcoded False across all 15 stock_etf_*_normalizers.py plus stock_etf_status_common.py, with tests asserting is Fal…
  - anchor: `ibkr_live_enabled` | dt: other
- [x] **NO-OP** **[INFO]** Bybit credential write path (POST /settings/api-key/{slot}) is well-hardened
  - NO-OP(2026-07-05 自核): Positive confirmation, VERIFIED accurate: settings_routes.py:1390-1478 save_api_key requires _require_operator_auth, whitelists slot against ALLOWED_SLOTS, rejects injection chars …
  - anchor: `save_api_key` | dt: other
- [x] **NO-OP** **[INFO]** Strategy-write / promotion / layer2-cost write endpoints all operator-gated; baseline HIGH-1 remains closed
  - NO-OP(2026-07-05 自核): Positive confirmation, VERIFIED accurate: strategy_write_routes.py:40-44 _require_strategy_write delegates to base.require_scope_and_operator(actor,'strategy:write') (operator-role…
  - anchor: `_require_strategy_write` | dt: other
- [x] **NO-OP** **[INFO]** f-string SQL in ml_routes.py:238 and earn_routes.py:988 are parameterized (false-positive candidates)
  - NO-OP(2026-07-05 自核): False-positive candidate, VERIFIED as genuine false positive: ml_routes.py:217-247 f-string interpolates only a static server-side cols list and where-clause fragments with $N/%s p…
  - anchor: `list_model_registry` | dt: other
- [x] **NO-OP** **[INFO]** shell=True in deploy helper runtime_source_reconcile_apply.py is shlex.quote-protected and operator-gated
  - NO-OP(2026-07-05 自核): Positive confirmation, VERIFIED accurate: helper_scripts/deploy/runtime_source_reconcile_apply.py LocalShellClient.run_shell uses shell=True but every interpolated path/ref in _bui…
  - anchor: `LocalShellClient.run_shell` | dt: readability-debt
- [x] **NO-OP** **[INFO]** Core security baselines intact since 976d420e — 5-gate SSOT, IPC socket 0600+HMAC, CORS/rate-limit, secret hygiene, production-unsafe-free
  - NO-OP(2026-07-05 自核): Positive confirmation, spot-VERIFIED intact post-46-fixes: verify_signed_authorization SSOT present at live_preflight.py:62; IPC unix socket set to 0o600 (I-02) at ipc_server/serve…
  - anchor: `verify_signed_authorization` | dt: other

## BB(9 條)

- [x] **FIXED** **[MEDIUM]** 哨兵 heartbeat 無年齡監控消費者，停擺 6 天零告警
  - FIXED(2026-07-05 自核): Anchor 屬實。已核實：helper_scripts/cron/bybit_announcement_sentinel_cron.sh:48 `touch $HEARTBEAT_DIR/bybit_announcement_sentinel.last_fire` 確實寫 heartbeat sentinel，但 helper_scripts/db/pas…
  - anchor: `cron_heartbeat/bybit_announcement_sentinel.last_fire` | dt: test-blindspot, missing-gate
- [x] **NO-OP** **[MEDIUM]** Rust client rate 註釋三處三值 + per-prefix 分組模型與官方 per-endpoint 配額結構不符（BB-2/BB-3 持續）
  - NO-OP(2026-07-05 自核): Anchor 不再屬實（已被修復波解掉）。rust/openclaw_engine/src/bybit_rest_client.rs 已更新：(1) enum RateLimitGroup docstring（line 226-256）現正確標官方 per-endpoint 值——order create/amend/cancel/cancel-all 各 …
  - anchor: `RateLimitGroup / RateLimitState::default / group_backoff_threshold` | dt: doc-stale, readability-debt
- [x] **NO-OP** **[MEDIUM]** Python client live_demo 憑證解析仍允許 env-var fallback，與 Rust P1-08 live-slot 禁令 drift（latent provenance gap）
  - NO-OP(2026-07-05 自核): Anchor 不再屬實（已被 R2 修復波解掉）。program_code/exchange_connectors/bybit_connector/control_api_v1/app/bybit_rest_client.py:245 已為 `is_live_slot = (slot == "live")`，env-var fallback 於 line 2…
  - anchor: `_resolve_credentials（is_mainnet 判斷應為 is_live_slot）` | dt: drift-source-runtime, auth-bypass
- [x] **FIXED** **[LOW]** 字典 funding 章 blanket「每 8 小時結算一次」殘留，與 per-symbol fundingInterval 正確段矛盾
  - FIXED(2026-07-05 自核): Anchor 屬實。docs/references/2026-04-04--bybit_api_reference.md line 154 get_funding_history 服務描述含 blanket『資金費率是多空雙方定期互付的費用，每 8 小時結算一次』，與同檔 line 176『linear perp 預設每 8h 結算一次（fundingInt…
  - anchor: `dict get_funding_history 服務描述（line 154）` | dt: doc-stale
- [x] **OUT-OF-SCOPE** **[LOW]** live_authorization now_ms duration_since 失敗 fallback=0 理論 expiry fail-open（BB-5 持續 nit）
  - OUT-OF-SCOPE(2026-07-05 自核): Anchor 屬實但觸 live fail-closed gate 邊界，本批不授權。rust/openclaw_engine/src/live_authorization.rs:402-405 `now_ms = SystemTime::now().duration_since(UNIX_EPOCH).map(...).unwrap_or(0)`；line…
  - anchor: `live_authorization.rs::now_ms（unwrap_or(0)）` | dt: over-gate, other
- [x] **NO-OP** **[INFO]** BYBIT_ORDER_LINK_ID_MAX_LEN=36 比 Bybit linear 45 上限緊 9 字元（保守方向）
  - NO-OP(2026-07-05 自核): Anchor 屬實但為刻意保守設計，無需改。rust/openclaw_engine/src/bounded_probe_active_order.rs:26 `pub const BYBIT_ORDER_LINK_ID_MAX_LEN: usize = 36`，僅作用於 line 485 is_bybit_safe_order_link_id 驗證引擎自產…
  - anchor: `BYBIT_ORDER_LINK_ID_MAX_LEN` | dt: over-gate
- [x] **NO-OP** **[INFO]** 公開資料 helper 多處硬編 mainnet base URL（public-only，無合規風險）
  - NO-OP(2026-07-05 自核): Anchor 屬實但無合規風險（finding 自標 public-only）。bybit_public_connectivity_check.py:85-86 與 bybit_public_microstructure_builder.py:54/396 的 mainnet URL 是 OPENCLAW_BYBIT_PUBLIC_BASE_URL env …
  - anchor: `_BYBIT_PUBLIC_BASE_URL / DEFAULT_BASE_URL` | dt: hardcoded-config, readability-debt
- [x] **NO-OP** **[INFO]** demo secret slot 存在未被讀取的 bybit_endpoint 檔（dead config）
  - NO-OP(2026-07-05 自核): Anchor 屬實但為刻意 informational 設計（自文檔化）。settings_routes.py:1474 `_SLOT_ENDPOINT = {"demo":"demo","live_demo":"demo","live":"mainnet"}`，line 1478 對每 slot 對稱寫 bybit_endpoint；line 1470-1…
  - anchor: `secret_files/bybit/demo/bybit_endpoint` | dt: dead-code
- [x] **NO-OP** **[INFO]** PASS 面彙總：核心交易路徑 0 ship-stop（HMAC 簽名/4-env 映射/LIVE-GUARD-1 三閘 runtime 實證/gate5 HMAC/retCode fail-closed/withdraw 0 引用/30d changelog 0 breaking/rate 30d 0 hit/25 pinned 0 delisting 中招）
  - NO-OP(2026-07-05 自核): 純正向確認（PASS 類），無可修。已於 HEAD e29adde76 抽驗關鍵斷言：withdraw 端點調用點 grep（/v5/asset/withdraw 等）0 命中（0 引用屬實）；bybit_rest_client.rs 含 HMAC-SHA256 簽名（line 1/1180/1183 compute_signature per Bybit …
  - anchor: `None` | dt: other

## QC(12 條)

- [x] **FIXED** **[MEDIUM]** 學習面 best-of-K 選擇（43 side-cells × 多 horizon）無多重比較控制，headline 數字系統性上偏
  - FIXED(2026-07-05 自核): FACT 屬實。已核 helper_scripts/research/alpha_discovery_throughput/horizon_specific_sealed_replay.py:267-310 sealed gate 僅點估計 floor（sample_floor_met >=100 / avg_net_floor_met > floor / …
  - anchor: `horizon_stability_scorecard` | dt: test-blindspot, math-error
- [x] **FIXED** **[MEDIUM]** per_trade_risk_pct 為 fraction（0.1=10%）與同區塊 percent 欄位混雜；4 處 survival-floor 註解寫 2% 低估實際 5 倍
  - FIXED(2026-07-05 自核): FACT 部分屬實。runtime 值 settings/risk_control_rules/risk_config_demo.toml:34 per_trade_risk_pct = 0.1（fraction=10%）；但兩處註解把 survival floor 寫成 per_trade_risk_pct(2%)，低估真值 5×：risk_config_…
  - anchor: `per_trade_risk_pct` | dt: schema-issue, doc-stale, readability-debt
- [x] **OUT-OF-SCOPE** **[MEDIUM]** dynamic_sizing band [0.01,0.05] 與 per_trade_risk_pct=0.1 無交叉驗證：暖機 10% → 50 筆平倉後靜默腰斬至 ≤5%；反向配置存在 fail-open 抬升結構
  - OUT-OF-SCOPE(2026-07-05 自核): FACT 屬實。已核 risk_config_demo.toml:275 max_pct=0.05 / min_pct=0.01 vs per_trade_risk_pct=0.1；dynamic_risk_sizer.rs 註解確認輸出經 IntentProcessor::set_p1_risk_pct 覆寫 per_trade_risk_pct 並夾限 …
  - anchor: `dynamic_sizing.max_pct` | dt: missing-gate, schema-issue, drift-source-runtime
- [x] **OUT-OF-SCOPE** **[MEDIUM]** ADPE explore keepalive 的 cost-viability 篩選 edge_evidence_slippage=0.0，違反保守成本硬約束
  - OUT-OF-SCOPE(2026-07-05 自核): FACT 屬實。settings/adaptive_demo_profit.toml:58 edge_evidence_slippage=0.0（fee 0.00055 + safety 1.3 有，滑點歸零），runner.py:894 slippage=max(0.0,...)。零滑點使該 cost-viable side edge 判定鬆於 Rust …
  - anchor: `edge_evidence_slippage` | dt: hardcoded-config, math-error
- [x] **OUT-OF-SCOPE** **[LOW]** funding_harvest 年化寫死 8h×3×365，未讀 per-symbol fundingInterval
  - OUT-OF-SCOPE(2026-07-05 自核): FACT 屬實。rust/openclaw_engine/src/strategies/funding_harvest/mod.rs:138 annualized_funding = funding_rate_8h * 3.0 * 365.0，硬編 8h×3 cycles/day，假設普適 8h fundingInterval（Bybit V5 per-sy…
  - anchor: `annualized_funding` | dt: bybit-incompat, hardcoded-config
- [x] **FIXED** **[LOW]** ewma_vol log-return 無 w[0]>0 guard（與同檔 hurst filter 不一致）——2026-04-24 LOW 延續 open
  - FIXED(2026-07-05 自核): FACT 屬實。rust/openclaw_core/src/indicators/volatility.rs:278 ewma_vol 之 close.windows(2).map(|w|(w[1]/w[0]).ln()) 無 w[0]>0 守衛；同檔 hurst() line 154 有 .filter(|w| w[0]>0.0 && w[1]>0.0)…
  - anchor: `ewma_vol` | dt: math-error, readability-debt
- [x] **OUT-OF-SCOPE** **[LOW]** close-maker backoff/cascade 6 常數仍硬編碼（前輪 P3 延續 open）
  - OUT-OF-SCOPE(2026-07-05 自核): FACT 屬實。rust/openclaw_engine/src/strategies/maker_rejection.rs:39-51 六常數硬編碼：BACKOFF_INITIAL_MS=1000 / BACKOFF_MAX_MS=60000 / BACKOFF_RESET_AFTER_MS=300000 / GLOBAL_CASCADE_WINDOW_M…
  - anchor: `CLOSE_MAKER_BACKOFF_INITIAL_MS` | dt: hardcoded-config
- [x] **NO-OP** **[LOW]** git 內 settings/edge_estimates.json 為 2026-04-20 化石，與 runtime 同名檔（2026-07-03, 221 keys）分歧 2.5 個月
  - NO-OP(2026-07-05 自核): anchor 不屬實（false positive in clean HEAD）。已核 HEAD=e29adde76：git cat-file -e HEAD:settings/edge_estimates.json 回 'does not exist in HEAD'；git ls-files 無此檔；.gitignore:46 明列 settings/e…
  - anchor: `settings/edge_estimates.json` | dt: drift-source-runtime, lineage-gap
- [x] **FIXED** **[INFO]** _rank_score 混量綱加總（bps + pct/2 + log10(n)·5 + 1000/100/50/40 tier bonus），常數敏感性未文檔化
  - FIXED(2026-07-05 自核): FACT 屬實。helper_scripts/research/cost_gate_learning_lane/false_negative_evidence_floor_ranking.py:282-303 _rank_score 加總 net_cushion_bps(bps) + (net_positive_pct-50)/2 + log10(count…
  - anchor: `_rank_score` | dt: readability-debt
- [x] **FIXED** **[INFO]** runtime edge_estimates _meta.n_cells=45 vs 實際 221 keys（113 real+108 proxy），meta 語意未自述
  - FIXED(2026-07-05 自核): FACT 屬實且已定位機制。program_code/ml_training/james_stein_estimator.py:641 _meta.n_cells = len(results) 在 _inject_entry_side_cells（line 690）與 _inject_sync_label_proxy_cells 之前設定，故 n_cells…
  - anchor: `_meta.n_cells` | dt: schema-issue
- [x] **NO-OP** **[INFO]** 系統態勢確認（非缺陷）：113 real cells 0 過 WF+PSR/DSR 驗證、101/113 EV<0、median n=6——系統誠實自報無已驗證 edge；樣本饑餓仍第一約束
  - NO-OP(2026-07-05 自核): 純正向確認（INFO『PASS/態勢』類），finding 自身明標『非缺陷』。edge_estimates 為 gitignored runtime artifact（見 QC-8），HEAD 不在樹無法直讀當前計數，但 validation 機制（WF/PSR/DSR gate 欄位 validation_passed/psr/dsr/p_value_b…
  - anchor: `validation_config` | dt: other
- [x] **NO-OP** **[INFO]** 正向確認：前兩輪 QC audit 全部 P0/P1 已修復（donchian_prior / OU 殘差 σ / Kelly Wilson-LB+config / fast_track+slippage+cost_gate TOML 化 / confluence load guard / 年化×365 測試固化 / 黑名單 0 違規）
  - NO-OP(2026-07-05 自核): 純正向確認，已於 HEAD=e29adde76 逐項復驗全部屬實：(1) donchian_prior 排除 current bar + test_donchian_prior_excludes_current_bar（trend.rs:218,332）；(2) grid OU 殘差 σ = 先扣 OLS drift 再取標準差 dof n-2（grid_h…
  - anchor: `donchian_prior` | dt: other

## MIT(13 條)

- [x] **FIXED** **[MEDIUM]** quantile trainer embargo fail-open：<50 樣本時靜默跳過且不入 acceptance report
  - FIXED(2026-07-05 自核): Anchor 屬實。program_code/ml_training/quantile_trainer.py:598-604，當 embargo 後 train 樣本 <50 時只 logger.warning 並跳過 embargo（改用未 embargo 的 train set 繼續擬合），但 QuantileTrainingResult 只有 emba…
  - anchor: `train_quantile_trio` | dt: leakage, test-blindspot
- [x] **NO-OP** **[MEDIUM]** V141 kline truth-drift guardrail 從未啟動：0 row/16 天，cron 未裝且哨兵 check_91 又因 F-3 停擺（雙盲）
  - NO-OP(2026-07-05 自核): Anchor 檔案屬實但斷言為 runtime 事實。Code 側三件全就位:V141 migration 含 Guard A/B/C(親讀確認)、helper_scripts/cron/kline_calibration_cron.sh 存在且刻意狹窄(唯讀+dry-run 默認)、healthcheck check_91_kline_calibratio…
  - anchor: `kline_calibration_cron.sh` | dt: missing-gate, drift-source-runtime
- [x] **FIXED** **[MEDIUM]** regime 軸雙缺陷未修且惡化：aeg_regime_labels stale 32 天 + bayesian_posteriors.regime 實值=engine_mode
  - FIXED(2026-07-05 自核): 拆兩半。(a) regime==engine_mode 屬實且為真代碼缺陷:helper_scripts/cron/ml_training_maintenance.py:157-195 _fetch_recent_fill_returns 的 SELECT 第三欄 SELECT engine_mode(L174)被 unpack 進名為 regime 的變數…
  - anchor: `bayesian_posteriors.regime` | dt: schema-issue, drift-source-runtime, doc-stale
- [x] **NO-OP** **[MEDIUM]** mlde_shadow_advisor 每日 run 全 error（QueryCanceled 5s statement timeout）— MLDE advisory lane 死
  - NO-OP(2026-07-05 自核): 已被修復波 P1-3(label 污染 / rejected_governance 排除)解掉。program_code/ml_training/mlde_shadow_advisor.py:213-216 明載 P1-3(2026-07-04) 註釋:新增 `AND df.label_close_tag IS DISTINCT FROM 'rejected…
  - anchor: `_AGGREGATE_BASE_SQL` | dt: perf-hotpath, drift-source-runtime
- [x] **NO-OP** **[MEDIUM]** linucb_trainer 以 arms=0/total_pulls=0 回報 ok — 空訓練標成功
  - NO-OP(2026-07-05 自核): 已被修復波 P2-11 ③ 解掉。helper_scripts/cron/ml_training_maintenance.py:304-326 明載 P2-11 ③(2026-07-04) 註釋(並引 07-04 runtime 實證 arms=0/83.7s/'ok')，現改三態誠實回報:len(rows)==0→error('all_arms_faile…
  - anchor: `linucb_trainer` | dt: fake-success, test-blindspot
- [x] **NO-OP** **[MEDIUM]** V142/V143/V144 header 聲稱 Guard A 但 body 無 Guard DO-block（V023 silent-noop 防線缺口 + 注釋不誠實）
  - NO-OP(2026-07-05 自核): 已被修復波 P2-11 ①(V148 Guard A retrofit + header 誠實更正)解掉。sql/migrations/V148__recorder_promotions_guard_retrofit.sql 存在，§A-§D 為 market.trades(5欄)/market.ob_top(6欄)/market.l1_events(9欄)…
  - anchor: `V142/V143/V144 CREATE TABLE IF NOT EXISTS` | dt: missing-gate, doc-stale, untruthful-ai
- [x] **FIXED** **[LOW]** scorer label winsorization 用全窗口分位數（含未來 fold）— 輕度 cross-fold statistic leak
  - FIXED(2026-07-05 自核): Anchor 屬實但函數 dormant。program_code/ml_training/label_generator.py:84-86 generate_labels 用 np.percentile(raw_labels, ...) 對整個 raw_labels 陣列(含未來 fold)算 1/99 winsorize 門檻再 clip——確為 cro…
  - anchor: `generate_labels` | dt: leakage
- [x] **NO-OP** **[LOW]** 訓練 engine_mode 默認 demo，與穩定規則 IN('live','live_demo') 文檔漂移
  - NO-OP(2026-07-05 自核): Anchor 屬實(default=demo)但屬 phase-policy 決策非 clear-cut bug,需 operator/PA 裁。ml_training_maintenance_cron.sh:80 TRAINING_ENGINE_MODES 默認 demo；ml_training_maintenance.py:72 DEFAULT_TRAI…
  - anchor: `OPENCLAW_ML_CRON_TRAINING_ENGINE_MODES` | dt: doc-stale, hardcoded-config
- [x] **FIXED** **[LOW]** V142/V143 compression/retention policy 無 timescaledb extension guard（V006 已知缺陷複製）
  - FIXED(2026-07-05 自核): Anchor 屬實且未被修復波解(V148 只補欄位 Guard A,未動 compression/retention 的 extension guard)。V142:93-103(及 V143 同構)的 ALTER TABLE ... SET(timescaledb.compress...)、add_compression_policy()、add_ret…
  - anchor: `add_compression_policy` | dt: schema-issue, duplicate-logic
- [x] **NO-OP** **[INFO]** V146 未 apply（prod sqlx head=145）— V145 誤導性 markout COMMENT 仍活在 prod
  - NO-OP(2026-07-05 自核): Code 側已完成,唯待 Linux PG apply=deploy-lag 非代碼缺陷。sql/migrations/V146__fills_maker_markout_comment_fix.sql 已在 repo(含 Guard A,訂正 V145 'Positive=adverse' 誤導措辭為 spread-capture,COMMENT-only…
  - anchor: `trading.fills.maker_markout_bps COMMENT` | dt: doc-stale
- [x] **NO-OP** **[INFO]** market.l1_events 28GB 超 PA realistic 儲存預估 4-9x（硬上界 ~26GB 亦已破）且 recorder 監測 lane 已死
  - NO-OP(2026-07-05 自核): 純 runtime 儲存量觀測需 Linux PG 驗證(Mac 盲點)。V143 header 估 21d retention ~3-7.5GB realistic/<~26GB 上界;28GB 實測、超估 4-9x、recorder lane 死 全為 runtime 事實,無活 PG 無法核。Code 側控制已就位:l1_book_tracker.rs…
  - anchor: `OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL` | dt: perf-hotpath, doc-stale
- [x] **NO-OP** **[INFO]** decision_features 14.8M rows（99.9% reject）以 ~55k/day 膨脹 — 下游查詢成本共同根源
  - NO-OP(2026-07-05 自核): 純 runtime 表量+growth-rate 觀測需 Linux PG(Mac 盲點)。14.8M rows/99.9% reject/~55k/day 全為 runtime 度量,無活 PG 無法核。writer 存在(Rust database 層)。潛在修法(retention/pruning/reject-row 隔離)屬 schema+capa…
  - anchor: `learning.decision_features` | dt: perf-hotpath, schema-issue
- [x] **NO-OP** **[INFO]** ML 決策層斷線三件套維持原狀：resolver 0 caller / combine layer mock / select_next_arm 0 consumer（06-14 結論重驗不變）
  - NO-OP(2026-07-05 自核): INFO 狀態重驗,dormant-by-design,非缺陷。親驗屬實:resolve_latest_production_artifact 在 rust/openclaw_engine/src 無真 caller(僅 doc-comment + 定義 + Python ml_routes 引用);thompson_sampling.select_next…
  - anchor: `resolve_latest_production_artifact` | dt: dead-code, evolution-blocker

## AI-E(8 條)

- [x] **NO-OP** **[MEDIUM]** Layer2CostTracker 跨進程預算競態：4 uvicorn workers 共寫 JSON 無 file lock（新發現，dormant）
  - NO-OP(2026-07-05 自核): 已被 46 修復波 P2-13 解掉。乾淨 worktree (HEAD e29adde76) 的 layer2_cost_tracker.py:191-232 已實作 _state_lock 跨進程 context manager，用 fcntl.flock(fd, LOCK_EX) 對 sidecar .lock 檔加互斥鎖，並在 _save(:282)…
  - anchor: `layer2_cost_state.json / _lock` | dt: missing-gate, duplicate-logic
- [x] **NO-OP** **[MEDIUM]** AI-E 報告 lineage gap：memory 索引的 06-13/06-14 兩份報告在 Mac/Linux/git 全史皆不存在
  - NO-OP(2026-07-05 自核): FACT: reports/ 目錄無 2026-06-13/2026-06-14 AI-E 報告檔，git log --all 對兩檔 0 結果，anchor 屬實。但 lineage gap 已被自身更正處理:當前 memory.md:261 與 270 兩處已於 2026-07-04 R4 巡檢加刪除線 ~~報告 ...~~ 並標『【2026-07-04…
  - anchor: `AI-E/memory.md 報告索引` | dt: lineage-gap, doc-stale
- [x] **NO-OP** **[LOW]** 每日成本快照採集腿不存在（06-14 F5 以刪 cron 而非補實現收場）
  - NO-OP(2026-07-05 自核): FACT: 腳本在 repo/Linux/git 全史皆不存在（find 0、git log --all 0）。但已由 CLAUDE_CHANGELOG v167（2026-06-18 read-only Linux recheck）明確裁決:『current trade-core crontab 無 daily_cost_snapshot 行，repo/L…
  - anchor: `daily_cost_snapshot.sh（absent）` | dt: missing-gate
- [x] **FIXED** **[LOW]** DOC-08 內文 stale：L1 寫 Ollama 7B（實際 9B/27B）、L2 per-call 估價基於退役定價
  - FIXED(2026-07-05 自核): FACT: docs/decisions/DOC-08_..._V1.md §1 表 line 35 寫『本地 Ollama 7B』、line 64/92-94 寫『Qwen2.5 7B』，但 runtime 實為 Qwen3.5 9B/27B（memory 多處親證）;line 36-37 L2 per-call 估價（Haiku ~$0.001 / So…
  - anchor: `DOC-08 §1 模型表` | dt: doc-stale
- [x] **OUT-OF-SCOPE** **[LOW]** cost_edge_ratio 三同名三義未收斂（06-14 F3 殘留命名債）
  - OUT-OF-SCOPE(2026-07-05 自核): FACT 屬實:同名 cost_edge_ratio 在三處反義——(a) DOC-08 §5.2 / token-cost-analysis skill = cost/edge（高=壞，≥0.8 建議關倉）;(b) layer2_adaptive.py:168 get_cost_edge_ratio = paper_pnl_7d / ai_spend_7d…
  - anchor: `cost_edge_ratio / trigger_threshold` | dt: readability-debt, math-error
- [x] **NO-OP** **[INFO]** GUI AI tab ROI tiles 永久 '--'（誠實空顯示非 fake-success）；adaptive_base_daily_usd=8 無風險（min 束於 2.0）
  - NO-OP(2026-07-05 自核): 純正向確認。FACT: tab-ai.html:91 roi-ratio tile 默認 '--'，:1038-1040 在無 backend ROI sample 時顯示 'N/A'/'no backend ROI sample'，:1075-1077 在 dataDays<3 顯示 'waiting for 3 days'——皆為誠實空顯示（明示無數據）…
  - anchor: `roi-ratio / adaptive_base_daily_usd` | dt: dead-code
- [x] **NO-OP** **[INFO]** PASS 面：定價三軸對齊且 07-03 官方複驗仍準；上輪 4 修復閉環確認；新模型 Sonnet 5 intro $2/$10 省 33% 機會窗至 08-31
  - NO-OP(2026-07-05 自核): 純正向確認（PASS 面），非需修 finding。即時查證（WebSearch 官方多源，2026-07-05）確認 ai_pricing.yaml 定價三軸與官方對齊:Opus 4.8 $5/$25、Sonnet 4.6 $3/$15、Haiku 4.5 $1/$5 per MTok。口徑修正供 PA/PM 參考:Sonnet 5 intro $2/$1…
  - anchor: `OPENCLAW_CLAUDE_TEACHER_MODEL / ai_pricing.yaml` | dt: other
- [x] **NO-OP** **[INFO]** 零成本承諾複驗：DreamEngine 0 LLM import、CognitiveModulator 300-3600s 界內；advisor 心跳 ~1.4k row/day 純噪音寫入
  - NO-OP(2026-07-05 自核): 純正向確認（複驗 PASS）。FACT: dream_engine.py grep import (ollama|anthropic|openai|llm|requests|httpx|provider_client|llm_call) 全 0 匹配 → DreamEngine 零 API 成本（本地隨機數）確認;cognitive_modulator.py…
  - anchor: `cost_edge_advisor_log heartbeat` | dt: perf-hotpath, other

## E5(10 條)

- [x] **FIXED** **[MEDIUM]** tick 熱路徑每 tick 深拷貝 4 個 panel snapshot（panel 60s 才更新）
  - FIXED(2026-07-05 自核): anchor 屬實：step_4_5_dispatch.rs 每 tick per-symbol 呼叫 try_clone_panel_snapshot 對 funding_curve/oi_delta/btc_lead_lag/liquidation_pulse 4 個 slot 做 guard.clone()(行 453/455/475/487)，全在 …
  - anchor: `try_clone_panel_snapshot` | dt: perf-hotpath
- [x] **NO-OP** **[MEDIUM]** _percentile 同名異契約 ×6（q∈[0,1] vs p∈[0,100] + NaN 過濾不一致）
  - NO-OP(2026-07-05 自核): anchor 屬實：6 個同名 _percentile。兩個 prod 版契約不同——replay_execution_calibration.py:632 收 q in [0,1]、無 NaN 過濾、空回 None；calibration_label.py:368 收 p in [0,100]、過濾 NaN、clamp p、空回 NaN。但已 grep 確…
  - anchor: `_percentile` | dt: duplicate-logic, math-error
- [x] **NO-OP** **[MEDIUM]** layer2_tools 3/4 SearchProvider 在 async def 內同步阻塞（latent，0 prod caller）
  - NO-OP(2026-07-05 自核): anchor 不再屬實/已被修復波解掉：三個 SearchProvider.search 現皆用 await asyncio.to_thread(...) 卸載阻塞呼叫——LocalLLMWebSearchProvider(layer2_tools.py:610 subprocess.run)、LocalLLMSearchProvider(:674)、Web…
  - anchor: `LocalLLMWebSearchProvider.search / LocalLLMSearchProvider.search / WebPilotSearchProvider.search` | dt: perf-hotpath, dead-code
- [x] **FIXED** **[MEDIUM]** helper_scripts/research 356 檔 / 184.8k LOC 一次性 evidence 腳本無 active/stale 歸檔機制
  - FIXED(2026-07-05 自核): anchor 屬實(數字略更新)：helper_scripts/research 現 376 檔/190,351 LOC；SCRIPT_INDEX.md 1594 行，結構是逆時序『最新補充 / ## YYYY-MM-DD』append log，無頂層 active/historical/stale 分節，396 條 research/ 引用平鋪。這是真 t…
  - anchor: `SCRIPT_INDEX.md（1588 行無 active/historical 分節）` | dt: readability-debt, doc-stale
- [x] **FIXED** **[LOW]** cost_gate_learning_lane_cron.sh 1980 行 bash 僅 6 函數，距硬限 <1%
  - FIXED(2026-07-05 自核): anchor 屬實且已惡化：cost_gate_learning_lane_cron.sh 現 2031 行(finding 記 1980)，已『超過』2000 行硬上限，非『距硬限 <1%』。CLAUDE.md 九明訂 2000 為 hard cap『unless a documented pre-existing exception applies』，檔…
  - anchor: `cost_gate_learning_lane_cron.sh` | dt: readability-debt
- [x] **NO-OP** **[LOW]** ipc_client 單連線 + asyncio.Lock 串行全部 engine IPC（吞吐 ceiling 記錄）
  - NO-OP(2026-07-05 自核): anchor 屬實：EngineIPCClient(ipc_client.py) 單一 Unix-socket 連線 + 單 asyncio.Lock(self._lock 行 140)，call() 於行 264 async with self._lock: 跨整個 _send_and_receive round-trip 持鎖，序列化全部並發 IPC。這…
  - anchor: `EngineIPCClient._lock` | dt: perf-hotpath, other
- [x] **NO-OP** **[LOW]** pg_stat_statements 未安裝——PG 調參與 seq scan 歸因無法證據驅動
  - NO-OP(2026-07-05 自核): anchor 屬實(與 E5 自身 2026-07-03 report F12 重複，引不重審)：pg_stat_statements 未裝，shared_preload_libraries 未含。但這是 runtime PG 基礎設施狀態非代碼變更——安裝需改 shared_preload_libraries = PG 容器/服務重啟 = E3/opera…
  - anchor: `shared_preload_libraries` | dt: index-broken, other
- [x] **NO-OP** **[INFO]** 根目錄歷史大 md（AE_INVENTORY 422KB / CLAUDE_CHANGELOG 1.4MB）
  - NO-OP(2026-07-05 自核): anchor 部分屬實但為 by-design：AE_INVENTORY_CONSOLIDATED.md 3922 行/422KB 確在根目錄；CLAUDE_CHANGELOG.md 4213 行/1.4MB 實在 docs/ 非根(anchor『根目錄』不精確)。兩者皆 append-only 歷史檔且被 context-loading 協議明訂『on d…
  - anchor: `AE_INVENTORY_CONSOLIDATED.md` | dt: doc-stale
- [x] **NO-OP** **[INFO]** （正面）前輪 F2 LTO/F3 urlopen/PERF-1 5m gate 已修；drift-gate 死循環 source 側已解待 v739 實走
  - NO-OP(2026-07-05 自核): 純正向確認(PASS 類)，全部核實屬實：(1) F2——rust/Cargo.toml 行 69-70 現有 lto=thin + codegen-units=1(profile.release 已含 LTO)；(2) F3——layer2_routes.py:518 現用 is_available_async() + 行 530 httpx.AsyncC…
  - anchor: `lto / codegen-units / standing_envelope_post_approval_drift_gate` | dt: over-gate, evolution-blocker
- [x] **NO-OP** **[INFO]** （基線）Linux engine 運行時資源快照
  - NO-OP(2026-07-05 自核): 純基線/INFO 條目，非 finding 亦非可修項。內容為 Linux engine runtime 資源快照(CPU/RSS baseline)，作後續優化的對照基準。worktree 無 release binary(clean Mac dev checkout 預期，非缺陷)。此類基線記錄無 anchor bug 可修，不觸任何 gate/sizi…
  - anchor: `openclaw-engine release binary` | dt: other

## A3(14 條)

- [x] **FIXED** **[MEDIUM]** Stock/ETF IBKR tab：18 個第一屏 metric 卡全英文工程術語、零中文、零解說 — 全 console 唯一無雙語的 tab，且認知密度超標
  - FIXED(2026-07-05 自核): anchor 屬實。tab-stock-etf.html:69-158 共 18 張 .se-metric 卡，label 全英文（Default Lane/Phase 0 Packet/Policy Gate/Authorization Gate/Reconciliation/Scorecard/Launch Gate/...），僅刷新按鈕有中文（:63 …
  - anchor: `se-metric` | dt: readability-debt, other
- [x] **FIXED** **[MEDIUM]** Rust 引擎宕機無全域跨 tab 告警：engine_alive 只在 system tab 一張 metric 卡 + agents tab chip，console 側欄/header 無引擎狀態燈
  - FIXED(2026-07-05 自核): anchor 屬實。loadEngineAlive() 僅定義於 tab-system.html:911，渲染 m-engine-tip（該 tab 內一張卡）。console.html 側欄/header 只有 mode-tag（:188，接 system_mode），無 engine_alive 燈。ux-checklist 明列紅旗『沒有 engine…
  - anchor: `loadEngineAlive` | dt: missing-gate, other
- [x] **NO-OP** **[MEDIUM]** 源碼-runtime 漂移：本輪全部『已修復』判定僅對 Mac 源碼 head 成立，trade-core runtime 落後 origin/main 164 commits，線上 console 是否含這些修復未驗證
  - NO-OP(2026-07-05 自核): dt=drift-source-runtime。本條非源碼可修 finding，而是部署/驗證動作：需在 trade-core runtime 側重新部署並驗證 console 是否含修復。乾淨 worktree（HEAD=e29adde76）源碼側 BUILD_TS=20260629.stock-etf-readiness-v1 屬源碼真值，但 runti…
  - anchor: `BUILD_TS` | dt: drift-source-runtime
- [x] **FIXED** **[LOW]** 側欄footer『Auto-refresh 15s』與實際 SIDEBAR_REFRESH_MS=30000 不符
  - FIXED(2026-07-05 自核): anchor 屬實。console.html:273 顯示文字 `Auto-refresh 15s`，但 :803 `const SIDEBAR_REFRESH_MS = 30000`（:1034 setInterval 用之），實際 30 秒。文字誤導。純顯示層 doc-stale，不涉風險。
  - anchor: `SIDEBAR_REFRESH_MS` | dt: doc-stale, hardcoded-config
- [x] **FIXED** **[LOW]** 破壞性操作 modal 缺『具體影響』數據：Demo/Live close-all 確認框無持倉數量與預估 UPL
  - FIXED(2026-07-05 自核): anchor 屬實。tab-demo.html:1402-1414 close-all modal 僅靜態文字（『市價平掉所有 Demo 帳戶倉位』），openDemoCloseAllDialog()（:1326-1329）只 display=flex，不注入實時持倉數/預估 UPL。ux-checklist §1『二次確認：modal 顯示具體影響（這會關…
  - anchor: `doDemoCloseAll` | dt: other
- [x] **FIXED** **[LOW]** 審計感知 UX（ux-checklist §5）系統性缺席：寫操作 toast 無 trace_id、無『最近 5 次 actor+ts+結果』、多數 dashboard 無採集時間 footer
  - FIXED(2026-07-05 自核): anchor 部分屬實。common.js:535 `ocToast(msg,type)` 僅接純文字、不渲染 trace_id。handoff_helper.js 已有獨立 recent-5 + trace_id 機制（:428/:474），故『系統性缺席』略過度——部分能力已存在，但一般寫操作 toast（demo close-all/strategy …
  - anchor: `ocToast` | dt: lineage-gap, other
- [x] **FIXED** **[LOW]** 簡繁中文混排遍佈治理/風控視圖，同一畫面同一概念兩種字形
  - FIXED(2026-07-05 自核): anchor 屬實。tab-governance.html gov-sm-note 註釋內簡繁混排實證：:294『没有…链路』（簡『没/链』）與同段『範圍/時』（繁）並存；:353『转换…释放…状态机』（簡）；:401『訂單…建立…狀態機』但『校驗…狀態機』摻簡；:441『調整風險等级』（『级』簡）；:529『比较系統內部記錄与…漂移』（『较/与』簡）。純 …
  - anchor: `gov-sm-note` | dt: readability-debt
- [x] **NO-OP** **[LOW]** 首次進入 console 僅見 core group 3 tabs（含最生僻的 Stock/ETF），交易/治理 group 默認折疊；Global Mode Control 卡藏於 dev-support 開關後
  - NO-OP(2026-07-05 自核): anchor 部分屬實（TAB_GROUP_DEFAULT_OPEN 僅 core=true，其餘 trading/edge/governance/intelligence/ops 全 false，console.html:349-356），但這是刻意的資訊架構設計——代碼註釋顯示 group 歸屬經設計（:361 『交易環境：低風險到高風險』、group …
  - anchor: `TAB_GROUP_DEFAULT_OPEN` | dt: duplicate-logic, over-gate, other
- [x] **FIXED** **[LOW]** UTC+local 雙時區標註基本缺席：console 時鐘僅 zh-CN 本地時間，全 GUI 僅 4 處 UTC 字樣
  - FIXED(2026-07-05 自核): anchor 屬實。console.html:752-753 時鐘僅 `toLocaleDateString('zh-CN')+toLocaleTimeString('zh-CN',{hour12:false})`，無 UTC。ux-checklist §2『時間區雙標：UTC + local 同列』。純顯示層，不涉風險。
  - anchor: `clock` | dt: other
- [x] **FIXED** **[LOW]** 設置/風控殘留英文-only placeholder 與 toast
  - FIXED(2026-07-05 自核): anchor 屬實。tab-settings.html:131 `placeholder="Optional description"`（英文 only），:872 `ocToast('Cost recorded','success')`（英文 only）。純 UX 文案，不涉風險。
  - anchor: `cost-note` | dt: readability-debt
- [x] **NO-OP** **[INFO]** A3 總評 7.5/10（術語友好 7 / 操作流完整 7 / 學習曲線 7.5 / 錯誤提示 8）— 較 2026-05-30 的 8.0 下調
  - NO-OP(2026-07-05 自核): 純評分性 INFO，非可修 anchor。是 A3 前輪報告的評分快照記錄，無代碼可改。分數下調由前述 LOW/MEDIUM findings 累積所致，修掉那些即回升。無獨立 fix 對象。
  - anchor: `a3_score_v20260703` | dt: other
- [x] **FIXED** **[INFO]** Legacy GUI /gui（index.html）仍註冊路由並保留 disabled paper 下單表單
  - FIXED(2026-07-05 自核): anchor 屬實。gui_legacy_routes.py:107-113 `@app.get('/gui')`→FileResponse(index.html) 仍註冊；index.html:181-210 含 Paper Trading section（含下單/session 控制項）。dt=dead-code。移除路由屬後端行為變更且 legacy …
  - anchor: `gui_index` | dt: dead-code
- [x] **FIXED** **[INFO]** tab-governance.html:1159-1160 stale 註釋仍引用不存在的 loadGovernance()（2026-05-30 advisory 未清）
  - FIXED(2026-07-05 自核): anchor 屬實。全 static 目錄無 loadGovernance() 定義（grep 僅命中 tab-system.html:1020 的 loadGovernanceStatus()，屬不同函數）。tab-governance.html:1159-1160 註釋仍稱『Populated by loadGovernance() and loadSu…
  - anchor: `loadGovernance` | dt: doc-stale
- [x] **NO-OP** **[INFO]** 正向確認：既往 A3 findings 全數修復且守住 — A3-GUI-009/010/011 已修（源碼含 A3 編號註釋）、native confirm()/prompt() 全滅、SM 術語加解說、學習 Tab 雙語、engine_alive 上第一屏、Demo close-all modal 補齊
  - NO-OP(2026-07-05 自核): 純正向確認/PASS 類，無缺陷可修。核實：classifyLiveMutation 存在（common.js 等 7 檔）；tab-*.html 內 confirm()/prompt() 僅出現於註釋（tab-ai.html:871、tab-demo.html:1365 均說明已用 typed-confirm/openConfirmModal 取代 nat…
  - anchor: `classifyLiveMutation` | dt: other

## R4(13 條)

- [x] **NO-OP** **[MEDIUM]** README Control Console tab 表 ⇄ GUI nav 漂移：缺 `stock-etf`、`charts`，仍列已下架的 `phase4`
  - NO-OP(2026-07-05 自核): anchor 已不成立/已被 46 修復波解掉。base worktree README.md tab 表(line 24-45)已含 `stock-etf`(line 28)與 `charts`(line 34),不再有 `phase4`;line 45 明確標『2026-07-04 TW per R4 对齐:补 stock-etf/charts,移除已下…
  - anchor: `README.md::Control Console tab 表` | dt: doc-stale, drift-source-runtime
- [x] **NO-OP** **[MEDIUM]** .claude/agents/R4.md 與 R4 profile.md 仍以『docs/README.md 底部索引』為審計目標，該索引已遷出至 _indexes/document_index.md
  - NO-OP(2026-07-05 自核): anchor 已不成立。base worktree .claude/agents/R4.md 核心審計領域(line 29)、核查清單(line 48)、啟動序列(line 16)全部已改用 `docs/_indexes/document_index.md` / `initiative_index.md`,且顯式標『舊 docs/README.md 底部索引…
  - anchor: `.claude/agents/R4.md::核心審計領域/核查清單` | dt: hardcoded-config, doc-stale
- [x] **NO-OP** **[MEDIUM]** _indexes/document_index.md 與 initiative_index.md 零 2026-07 條目；operator 已批准之設計 spec 與 E4 回歸報告未登記
  - NO-OP(2026-07-05 自核): anchor 已不成立/已被修復波解掉。document_index.md line 9-25 新增『2026-07 冷審計 R2 + soak dispatch / drift-gate 設計批(2026-07-04 TW per R4 補登)』整節,收 operator 已批准之 `execution_plan/2026-07-02--soak_disp…
  - anchor: `docs/_indexes/document_index.md` | dt: index-broken, doc-stale
- [x] **FIXED** **[LOW]** SPECIFICATION_REGISTER ADR 節標題停在 0047、表已含 0048；docs/README.md 寫『ADR 0001-0047』實有 0048
  - FIXED(2026-07-05 自核): anchor 屬實,純 doc-stale,不觸 gate/risk/live 邊界。SPECIFICATION_REGISTER.md line 212 標題『Architecture Decision Records (ADR-0034 ~ ADR-0047)』與 line 214 導語末句『ADR-0047 追加...』落後於表身:表已含 ADR-00…
  - anchor: `SPECIFICATION_REGISTER.md::ADR 節標題` | dt: doc-stale, hardcoded-config
- [x] **FIXED** **[LOW]** register Cross-Reference Summary『Active REF specifications = 19』與 REF 表狀態不吻合
  - FIXED(2026-07-05 自核): anchor 屬實,doc 計數 drift,不觸 risk。REF 表 REF-01~REF-21 共 21 條(line 179-199):嚴格 ✅ Active=15(REF-01/02/04/05/06/07/08/09/10/11/12/13/15/16/17),另 REF-14=✅ Implemented Historical Reference…
  - anchor: `SPECIFICATION_REGISTER.md::Cross-Reference Summary` | dt: doc-stale, math-error
- [x] **FIXED** **[LOW]** SCRIPT_INDEX.md『最新補充』段延續巨型敘事模式（前輪 R4-2026-IDX-04 持續）；標頭日期與 changelog 相差一天
  - FIXED(2026-07-05 自核): anchor 主體屬實(readability-debt),不觸 gate/risk。SCRIPT_INDEX.md 頭部『最新補充』段(line 6 起約 30+ 段 run-on prose,每段動輒 400-800 字)仍在源檔;archive 檔 docs/archive/2026-07-04--script_index_changelog_pros…
  - anchor: `helper_scripts/SCRIPT_INDEX.md::最新補充` | dt: readability-debt, doc-stale
- [x] **FIXED** **[LOW]** CLAUDE_REFERENCE.md 停更 82 天（2026-04-12）且無 STALE 快照 banner，仍自稱含『Authoritative checkers』
  - FIXED(2026-07-05 自核): anchor 屬實,doc-stale,不觸 risk。docs/CLAUDE_REFERENCE.md line 4『最後更新:2026-04-12(FIX-47...)』距 2026-07-04 為 83 天;header(line 1-8)無 STALE banner;line 26 仍標『Authoritative checkers』並列 helpe…
  - anchor: `docs/CLAUDE_REFERENCE.md::header` | dt: doc-stale
- [x] **FIXED** **[LOW]** docs/README.md 路由表覆蓋缺口：docs/agents/ 表僅列 3/9 檔；docs 根層 KNOWN_ISSUES.md / lessons.md / CLAUDE_REFERENCE.md 不在目錄樹
  - FIXED(2026-07-05 自核): anchor 屬實,index-broken/doc-stale,不觸 risk。Glob docs/agents/*.md 實有 9 檔(domain/issue-tracker/triage-labels/role-profile-memory-standard/todo-maintenance/sub-agent-hygiene-sop/profit-…
  - anchor: `docs/README.md::稳定入口索引` | dt: index-broken, doc-stale
- [x] **FIXED** **[LOW]** R4 自身 memory.md 報告索引停更：僅列 2/16 份報告；『項目上下文』段殘留 2026-04-24 runtime 數字未標 stale
  - FIXED(2026-07-05 自核): anchor 屬實,doc-stale/index-broken,不觸 risk。Glob docs/CCAgentWorkSpace/R4/workspace/reports/*.md 實有 18 份,memory.md『報告索引』表(line 41-44)只列 2 份(2026-04-01、2026-04-24)。『項目上下文(2026-04-24 更新…
  - anchor: `docs/CCAgentWorkSpace/R4/memory.md::報告索引` | dt: doc-stale, index-broken
- [x] **FIXED** **[LOW]** TODO §4 handoff 命令引用已 superseded 的 v693 /tmp artifacts，且 `sed 1,180p` 截不到 §3/§4 自身
  - FIXED(2026-07-05 自核): anchor 部分屬實,已被修復波部分 flag 但命令未同步。TODO.md §4 Handoff Commands(line 96-109)命令仍寫 `/tmp/openclaw/...`(line 104-105);line 109 已加註『D3 落地(SSOT 遷移)後,上述 /tmp/openclaw 路徑統一改 ~/BybitOpenClaw/v…
  - anchor: `TODO.md::§4 Handoff Commands` | dt: doc-stale, drift-source-runtime
- [x] **FIXED** **[LOW]** README 內部測試計數三口徑並存（crate 註記 ~400/~2400 vs register ~3,600+ Rust vs README ~6,500+ 總）
  - FIXED(2026-07-05 自核): anchor 屬實但誤導性已被免責語緩解。README.md line 110 rust crate 註記 openclaw_core ~400 tests / openclaw_engine ~2400 tests;line 141 『约 6,500+ 测试通过(Py+Rs+sibling)』;SPECIFICATION_REGISTER.md line …
  - anchor: `README.md::项目结构 rust/ 註記` | dt: doc-stale, hardcoded-config
- [x] **FIXED** **[INFO]** A3.md 配置內嵌 GUI 現狀觀察未標採集日（『學習系統 Tab 6 個核心指標全英文』等）
  - FIXED(2026-07-05 自核): anchor 屬實,屬 R4 配置漂移巡檢範圍(.claude/agents/ 內硬編碼 GUI 現狀事實 vs canonical)。.claude/agents/A3.md『當前已知 GUI 問題』段(line 42-47)列具體 GUI 現狀(line 46『學習系統 Tab 6 個核心指標全英文』、line 47『設置 Tab 部分 placehol…
  - anchor: `.claude/agents/A3.md::已知問題示例` | dt: hardcoded-config, doc-stale
- [x] **NO-OP** **[INFO]** （正向核驗，無缺陷）前輪 P1/P3 修復保持 + 各 SSOT 對齊抽查通過
  - NO-OP(2026-07-05 自核): 純正向確認(PASS 類),無 anchor 可修(anchor=None)。本次自核亦印證:README tab 表(R4-01)、.claude/agents/R4.md 與 profile.md(R4-02)、_indexes 2026-07 補登(R4-03)三項先前 R4 指認缺口確已由 46 修復波閉合,符合『前輪修復保持』的正向敘述。無需動作。
  - anchor: `None` | dt: other

## E4(10 條)

- [x] **OUT-OF-SCOPE** **[MEDIUM]** (補審) F4 ledger all-or-nothing 解析+跨語言型別/時間格式容忍不對稱,單一壞行=Rust learning lane 靜默死亡;無毒行/torn-line 測試
  - OUT-OF-SCOPE(2026-07-05 自核): anchor 兩部分分別裁:(1) test-blindspot 部分【已被 46 修復波解掉】——fix/authz-contract-0704 已加 rust/openclaw_engine/tests/demo_lane_contract_xlang_consistency.rs 毒行三態測試(bad_json/non_dict/torn_eof, L…
  - anchor: `LedgerRecord::from_jsonl_str` | dt: test-blindspot, schema-issue, other
- [x] **NO-OP** **[MEDIUM]** (補審) F9 v739 前置:runtime engine binary=06-29 build,IMPL-A/IMPL-B 已測代碼未上線;凍結事實『無獨立 engine 進程』已過期
  - NO-OP(2026-07-05 自核): runtime-drift 觀察,非 source 缺陷,且已被 46 修復波 D1 rebuild 解掉。IMPL-A/B 源碼在 worktree 存在且由 OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED+engine_mode(demo/live_demo) gated(step_4_5_dispatch.rs:58-74…
  - anchor: `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED` | dt: drift-source-runtime, other
- [x] **NO-OP** **[MEDIUM]** (補審) F5 cutover 閘鍵 BYBIT_MODE/BYBIT_CONNECTOR_WRITE_ENABLED 零 runtime 強制消費者——治理語義純表示層
  - NO-OP(2026-07-05 自核): 已被 46 修復波解掉,anchor 不再成立。bybit_rest_client.py:144-165 有明署『F5(2026-07-04 冷審計 R2)』把兩 flag 接成真實 fail-closed 消費者:_connector_write_enabled() 缺失/false=拒(方向只准收緊),_post() (L497-514) 所有寫請求(o…
  - anchor: `BYBIT_CONNECTOR_WRITE_ENABLED` | dt: doc-stale, missing-gate
- [x] **NO-OP** **[MEDIUM]** (補審) F7 markout exit 價無 max-delay 上界(entry 有 5min 上界,exit 取任意遲到觀測),學習閾值輸入可被觀測缺口污染;無邊界測試
  - NO-OP(2026-07-05 自核): 已被修復波解掉,anchor 兩點皆不成立。(1) max-delay 上界已存在:outcome_writer.py:29-30 _max_exit_delay_ms(cap 30min/floor 5min),_build_markout_outcome_records(L332)於 L432-434 當 now_ms>exit_target_ts_ms…
  - anchor: `_build_markout_outcome_records` | dt: math-error, leakage, test-blindspot
- [x] **NO-OP** **[LOW]** (補審) F10 engine_mode 正規化不對稱:Rust trim+to_ascii_lowercase vs Python exact dict-get
  - NO-OP(2026-07-05 自核): 已被 p3-smalls 修復波(commit db07df83b, 在本 worktree HEAD e29adde76 已 landed)解掉。proof_exclusion.py:122 新增 _normalized_engine_mode(strip+lower),L198 mode_tag 查表前正規化、L248 proof key engine_…
  - anchor: `_candidate_bound_active_order_link_id_is_valid` | dt: duplicate-logic, drift-source-runtime
- [x] **NO-OP** **[LOW]** (補審) F11 is_bybit_safe_order_link_id_for_engine_mode(4 段版)零生產 caller
  - NO-OP(2026-07-05 自核): 已被 p3-smalls 修復波(commit 25353197e, 已 landed 於本 worktree)解掉。rust/openclaw_engine/src/bounded_probe_active_order.rs:494 現為中文墓碑注釋『F11(E4 2026-07-04 補審):四段版 is_bybit_safe_order_link_id…
  - anchor: `is_bybit_safe_order_link_id_for_engine_mode` | dt: dead-code
- [x] **NO-OP** **[LOW]** (補審) F12 4/5 cron pin stale OPENCLAW_EXPECTED_SOURCE_HEAD=00a78d92(runtime head 262596c6)+兩 cron log 0-byte,head-gated cron 實際行為未驗
  - NO-OP(2026-07-05 自核): runtime cron-state 觀察,非 worktree source 缺陷,且已被 46 修復波 D1/D2 部署窗口解掉。SHA 00a78d92/262596c6 全 source 無出現(純 runtime crontab 上的 pin)。TODO(本 worktree)P0-RUNTIME-EXECUTION-IDENTITY 行:『cro…
  - anchor: `OPENCLAW_EXPECTED_SOURCE_HEAD` | dt: drift-source-runtime, other
- [x] **NO-OP** **[LOW]** (補審) F14 probe_outcome 以 admission 時價 markout 生成,未與真 fill 對賬(admitted-but-unfilled 同權計入學習證據)
  - NO-OP(2026-07-05 自核): 已被 p3-smalls 修復波(commit 1791e433c, 已 landed)解掉。outcome_writer.py:49-58 新增 FILL_RECONCILIATION_FIELD(filled/admitted_only/indeterminate)誠實性標記,只認執行層識別碼(fill_id/exec_id/execution_id),…
  - anchor: `build_probe_outcome_records` | dt: leakage, test-blindspot
- [x] **NO-OP** **[INFO]** (補審) F13 學習 SSOT(plan+ledger 472MB)全在 /tmp/openclaw,reboot 即滅(corroboration,主審計他軸已有 data-dir 發現)
  - NO-OP(2026-07-05 自核): 自標為 corroboration(『主審計他軸已有 data-dir 發現』)=純重複確認;且已被 46 修復波 D3(SSOT 遷移)解掉。source 面 OPENCLAW_DATA_DIR 已為 SSOT——所有 cost_gate_learning_lane/*.py 讀 os.environ.get('OPENCLAW_DATA_DIR', ..…
  - anchor: `OPENCLAW_DATA_DIR` | dt: lineage-gap
- [x] **NO-OP** **[INFO]** (補審) 覆蓋充分面(公平雙向聲明,非缺陷):retCode/timeout/fail-closed/auth-expiry 單語言層無新增盲區
  - NO-OP(2026-07-05 自核): 純正向確認(INFO PASS 類),條目本身自標『公平雙向聲明,非缺陷』。anchor=None,無需修復面,亦無 gate/sizing/live 邊界觸及。屬 fairness/positive-coverage 聲明,NO_OP。
  - anchor: `None` | dt: other

## TW(8 條)

- [x] **NO-OP** **[MEDIUM]** (補審) Operator/ 全文鏡像層於 07-03 主審計批次第三度再現（6/6 對全文複製）
  - NO-OP(2026-07-05 自核): Anchor 不再成立於 e29adde76(HEAD)。乾淨核實:docs/CCAgentWorkSpace/Operator/ 目錄在此 worktree 只剩 README.md 一檔(Glob `2026-07-03--*.md`=No files found;`Operator/*.md`=No files found;`Operator/**/*…
  - anchor: `docs/CCAgentWorkSpace/Operator/2026-07-03--*.md` | dt: duplicate-logic, doc-stale
- [x] **NO-OP** **[MEDIUM]** (補審) Operator/ 目錄用途漂移：過程性 checkpoint/loop-state 記錄佔據 operator 決策通道
  - NO-OP(2026-07-05 自核): 核實 Operator/README.md::存放規則(:5-9)文本內容正確且完備:『不存放:各 Agent 的工作草稿、中間過程報告(那些存在各 Agent 自己的 workspace 下)』——規則本身已明確禁止過程性 checkpoint 進 operator 通道。finding 描述的『用途漂移』是實踐違規(過程檔實際被寫入),但那些違規證據檔在…
  - anchor: `docs/CCAgentWorkSpace/Operator/README.md::存放規則` | dt: doc-stale, other
- [x] **NO-OP** **[MEDIUM]** (補審) 同一敘事 3-4 處全文重述（SCRIPT_INDEX + CLAUDE_CHANGELOG + Operator brief + .codex/WORKLOG）
  - NO-OP(2026-07-05 自核): Anchor 行號指向的具體重述配對在 e29adde76 已不成立。乾淨核實:SCRIPT_INDEX.md:6=B2-1 學習證據方法學重設計(4 個 cost_gate_learning_lane 模組),CLAUDE_CHANGELOG.md:12=TODO v738 P1-7 瘦身敘事——兩行已非同一敘事的全文複製,錨點因 46 修復波(SCRIP…
  - anchor: `SCRIPT_INDEX.md:6 ↔ CLAUDE_CHANGELOG.md:12` | dt: duplicate-logic, readability-debt
- [x] **FIXED** **[LOW]** (補審) 檔名規範 rule-vs-practice 死字：hyphen-desc ≥64 檔違「下划线连接」+ role-infix 跨輪不一致（同批 4 種風格）
  - FIXED(2026-07-05 自核): Anchor 屬實。docs/README.md:242 命名規範寫『功能描述用下划线连接:避免空格,保持路径兼容性』,但實際檔名普遍用 hyphen 分隔描述詞(如 archive 索引 `2026-04-29--62finding-batch-A-to-F.md`、`strkusdt-p0-wave.md` 等,見 docs/README.md:101/…
  - anchor: `docs/README.md::文件命名规范` | dt: doc-stale, other
- [x] **FIXED** **[LOW]** (補審) worklogs/ lane 事實休眠（05 月 2 檔/06 月 1 檔/07 月 0）但 docs/README 仍標現役
  - FIXED(2026-07-05 自核): Anchor 屬實且比 finding 描述更嚴重。乾淨核實:docs/worklogs/ 目錄在 e29adde76 頂層完全無 .md 檔(Glob `docs/worklogs/*.md`、`docs/worklogs/**/*`、目錄名 `docs/worklogs` 三次皆 No files found——頂層已無現役檔,甚至可能整個目錄已空/移除…
  - anchor: `docs/README.md::worklogs 節` | dt: doc-stale
- [x] **NO-OP** **[LOW]** (補審) README.md Console tab 表殘留：仍列已退役 phase4、缺 charts（06-14 已 flag 未指派，carried 20 天）
  - NO-OP(2026-07-05 自核): 已被 46 修復波解掉。乾淨核實 README.md(根目錄)OpenClaw Control Console 核心 Tab 表:`charts` 已在(:34『charts | 圖表/交易视图』)、`stock-etf` 已在(:28)、無殘留 `phase4`(grep `phase4` 唯一命中在 :45 修復註記文本『移除已下架的 phase4』,非…
  - anchor: `README.md:40::tab 表` | dt: doc-stale
- [x] **NO-OP** **[INFO]** (補審) cold-audit 報告族命名穩定無應併未併；pm_final 歸檔節奏不一致（05 輪已 archive、06-14/07-03 仍在 workspace）
  - NO-OP(2026-07-05 自核): Anchor 屬實但為 INFO 級正向/中性觀察,不值得改。乾淨核實 cold_audit_pm_final 分布:`2026-05-17` 與 `2026-05-30` 已在 docs/archive/,`2026-06-14` 與 `2026-07-03` 仍在 docs/CCAgentWorkSpace/PM/workspace/reports/——…
  - anchor: `docs/archive/2026-05-*--cold_audit_pm_final.md` | dt: other
- [x] **FIXED** **[INFO]** (補審) docs/README.md:174「ADR 0001-0047」stale（0048 已存在）— R4 索引軸重疊，掛帳不展開
  - FIXED(2026-07-05 自核): Anchor 屬實。乾淨核實 docs/README.md:174『├── adr/ ← 架构决策记录(ADR 0001-0047)』,而 ADR-0048(IBKR stock_etf_cash)確已存在並被 CLAUDE.md/README 多處引用(如 CLAUDE.md §一、README:28/:53)。純目錄樹註記 stale,一字之差,不觸任何…
  - anchor: `docs/README.md:174` | dt: index-broken, doc-stale
