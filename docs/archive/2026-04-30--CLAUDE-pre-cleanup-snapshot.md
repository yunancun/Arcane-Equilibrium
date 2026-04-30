# OpenClaw / Bybit AI Agent 交易系統
# CLAUDE.md — 項目指令文件（核心規則 + 下一步指針）

---

## 一、項目定位

長期進化型 AI Agent 自動交易系統。OpenClaw 為中樞、**Bybit 為唯一交易所**（專攻）。

> Agent 自主完成交易決策與執行，對成本與收益有清晰感知，能感知自身狀態，能持續學習，在嚴格風控框架下逐步贏得更高自主權。

人類 Operator 角色：不定時檢查、審閱、矯正、批准關鍵步驟、推動策略演進。

**交易所決策（2026-04-03）：** 早期規劃含 Binance 雙平台，現已明確專攻 Bybit。Binance 僅作為超長期可能方向保留，當前開發、設計、架構決策均不需考慮 Binance 兼容性。

**系統管線：** 市場數據 → H0 本地判斷 → H1-H5 AI 治理 → I Decision Lease → 執行適配層 → 學習/歸因

---

## 二、16 條根原則（DOC-01 項目憲法 §5.1–§5.16，不可違背）

1. **單一寫入口** — 所有訂單/執行動作通過唯一受控入口
2. **讀寫分離** — 研究/GUI/學習：只讀。寫入權限極度受限、可審計、可鎖定
3. **AI 輸出 ≠ 即時命令** — AI → Decision Lease（帶時效、可撤銷）→ 本地復核 → 執行
4. **策略不能繞過風控** — 所有交易意圖必須經 Guardian 審批
5. **生存 > 利潤** — 先判斷「不會螺旋崩潰」，再判斷「能否盈利」
6. **失敗默認收縮** — 不確定時默認保守：不開新倉、降頻率、降風險
7. **學習 ≠ 改寫 Live** — 學習平面與 Live 平面隔離
8. **交易可解釋** — 每筆交易必須可重建：為什麼、何時、風控審批、授權、執行、結果
9. **交易所災難保護** — 本地止損 + 交易所條件單雙重防線
10. **認知誠實** — 所有結論區分事實 / 推斷 / 假設
11. **Agent 最大自主權** — P0/P1 硬邊界內，Agent 完全自主決定：幣種、策略、參數、時機
12. **持續進化** — 系統必須從交易行為中自動學習（當前 demo 階段：Paper 驗證→參數進化，live 自動部署待 Phase 3 放權框架）
13. **AI 資源成本感知** — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉
14. **零外部成本可運行** — 基礎運營僅需 L0+L1（Ollama + 免費搜索）
15. **多 Agent 協作** — 5 Agent（Scout/Strategist/Guardian/Analyst/Executor）+ Conductor 編排，正式對象通信
16. **組合級風險意識** — 監控關聯曝險、策略重疊持倉、資金分配合理性

**優先級序：** 帳戶生存 > 風控治理 > 系統健康 > 審計可追溯 > 人類終審 > 真實 Net PnL > 自主能力進化

**實施準則（從根原則衍生，非憲法級但強制遵守）：**
- **認知調製 ≠ 能力限制** — Agent 壓力下更審慎的方式是提高決策門檻，不是關閉能力。虛擬稀缺性（能量/積分/內部貨幣）被明確否決。（衍生自原則 #11，見 `docs/references/2026-04-03--agent_cognitive_adaptation_spec_v1_draft.md`）

---

## 三、當前系統狀態摘要

**62-finding remediation 狀態（2026-04-29 CEST）**：Batch A-F 全 62 findings 已修復、簽核、tracking 更新並部署。主修復 `bc3fa70`，文檔同步 `6539e4e`，restart ownership hotfix `5db4e29`；Mac ahead doc commits 已推送並在 Linux fast-forward。Post-deploy RCA fix `bdd3177` 已部署：`[22] trading_pipeline_silent_gap` root cause = demo/LiveDemo fee-rate endpoint unsupported response 只在 startup seed conservative defaults，週期 refresh 失敗後未 re-seed，2h staleness window 後 cost_gate fail-closed。修復後 periodic refresh 在 demo unsupported response 時重新注入保守 fee defaults，mainnet/testnet 與非 demo error 不放寬。2026-04-29 follow-up `030ef2d` + `0e9e257` + `f0d21b9` + `af9d552` 已部署：新增 `[33] maker_fill_rate`（G2-01 fee-drop 監控）+ cron F7 `[22]`-`[29]` self-check；`[32] maker_entry_intent_drift` restart-aware 後 PASS。最新 healthcheck WARN：`[12] bb_breakout_post_deadlock_fix`（7d entries=1，低量）+ `[33] maker_fill_rate`（7d fee_drop 1.8% vs target ≥60%）+ `[11] counterfactual_clean_window_growth`。Live pipeline 拒絕啟動仍是預期 gate（authorization schema v1 vs expected v2），需 Operator 經 `/api/v1/live/auth/renew` 或 renew-review 重新簽署。Batch F sign-off `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_f_ml_agent_autonomy_signoff.md`；fee RCA report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--fee_refresh_periodic_reseed_rca_deploy.md`。

**Runtime**（2026-04-29 12:38 CEST · ssh verify · G6-04 §三 drift 規則）：runtime code commit `af9d552` deployed；engine PID **447123**（`rust/target/release/openclaw-engine`）+ API uvicorn PID **447192** + 4 workers + engine_watchdog PID **3450754**（自 2026-04-20 起）+ openclaw-gateway PID **3973441**（自 2026-04-28 起）全部 alive；watchdog `engine_alive=true`，demo/live snapshots fresh。Engine log 確認 Demo + LiveDemo startup conservative fee defaults seeded。`passive_wait_healthcheck.py` SUMMARY WARN：WARN `[12]` + `[33]` + `[11]`；`[22]`/`[27]` cleared，`[32]` post-restart limit-only PASS，`[33]` 暴露 G2-01 目前 fee_drop **1.8%** / maker_like **29/1402=2.1%** / limit_order_rows **15.5%**。Cron wrapper 手動驗證 exit=0 且 log 末尾 `[OK] F7 cron self-check saw [22]-[29] in current run`。direct unauth `/openclaw/health` + `/api/v1/system/health` 回 401（auth enforced），GUI-origin API logs 200 OK。**真實 live 門控**（Rust 可驗證 4 項 / 全部 5 項，詳 §四）：(1) Python `live_reserved` global mode (2) Python Operator 角色 auth (3) `OPENCLAW_ALLOW_MAINNET=1` env（僅 Mainnet）(4) secret slot 有 api_key + api_secret (5) `authorization.json` HMAC 簽名+未過期+env_allowed 匹配。`execution_authority` 在 Rust 僅為 P0/P1 denylist 字串常量（`claude_teacher/applier.rs:226`），非真實授權邏輯。Live 縮倉監控 5min 輪詢（代碼已寫、e2e 測試綠，**從未真實觸發**）。舊 runtime 詳述（2026-04-22~24 INFRA-PREBUILD Part A/B / WS-RETIRE-1 / P0-13 ATR / P0-14 A/B / Priority 6 物理層）已歸檔至 [`docs/archive/2026-04-29--claude_md_section3_pre_04_27_detail.md`](docs/archive/2026-04-29--claude_md_section3_pre_04_27_detail.md)。

**Strategy Edge Repair packet（2026-04-29 17:36 CEST · implementation checkpoint）**：策略虧損判讀以扣費後 `net_bps_after_fee` 為主，PNL / winrate 僅作參考；修後樣本起點用 **2026-04-29 12:27:53 CEST**（live TOML maker-entry reload）切分，避免混入舊 Market/taker fill。本輪按務實路線落地：1) demo/live_demo strategy-open intent 現在先寫 `trading.signals` attribution anchor，再把同一 `signal_id` / `context_id` 寫入 `trading.intents`；2) scanner 每輪寫 `trading.scanner_snapshots`，intent details 附 `scan_id` / edge 狀態 / route mode，方便查上游是否誤導；3) fee refresh 從單一 shared AccountManager 改為 demo/live 每個 exchange binding 自己 refresh/re-seed，避免 Live 搶 priority 後 Demo/LiveDemo fee cache 長期 stale；4) maker 入場改為 BBO/tick_size 不足就 skip，不再退回 last_price/taker fallback；5) scanner 新增可調 `edge_routing`，低樣本探索保留，成熟負 edge cell 降到 exploration-only / score cap；6) grid robust-negative symbols 可配置 `blocked_symbols`，bb_breakout demo threshold 使用最新 sweep 結果調到 volume 1.2。新增 healthcheck `[34] intent_signal_attribution` 監控 attribution chain；後續仍追 `[33] maker_fill_rate` 和 G2-01 settlement，不因短期虧損再疊風控層。

**Strategy Edge Models batch（2026-04-30 15:25 CEST · local verified · Linux deploy next）**：本輪把 execution-aware / regime-aware selector 變成可部署路徑，而不是新增裸價格預測策略。核心落地：修 TOML→runtime wiring 漏洞，MA/BB/grid 的 maker buffer 與 grid `blocked_symbols` / reject cooldown 真正進 factory；grid OU spacing 新增成本地板（`min_grid_step_bps=22.0`、`cost_floor_multiplier=2.0`）；scanner `edge_routing` 加 posterior LCB gate（1σ、min std 20bps，成熟不確定/負 LCB cell 轉 `exploration_only`）；MA 新增 ATR-normalized `min_trend_snr=0.75` 入場門。三環境 strategy TOML 已對齊 edge-protection baseline；live 自動交易 / live 參數自動放權邊界不變。驗證：`cargo test -p openclaw_engine --lib` 2377/0，`cargo check --workspace` PASS。工程日誌：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-30--strategy_edge_models_engineering_log.md`。部署後以 `[33]` / `[38]` / `[40]` 觀察 24h，立即 rolling-window 紅燈需按 post-deploy cutoff 分析。

**ML/Dream Edge Unblock implementation（2026-04-29 18:45 CEST · demo autonomous / live governed）**：正 edge 仍是 **promotion gate**，不是 training gate。已把 demo-first / live-governed 路線落地：V031 新增 `learning.mlde_edge_training_rows`（valid attribution + post-fee `net_bps_after_fee` reward）與 `learning.mlde_shadow_recommendations`（advisory source，live/live_demo applied row 必須有 `decision_lease_id`）；LinUCB trainer 改讀 V031 view，scheduler 每輪以 `demo_live_demo` 合併訓練一次避免 shared `learning.linucb_state` 被 per-mode 覆蓋；ML shadow advisor 產 `rank`/`veto`；DreamEngine / OpportunityTracker producers 接入 CognitiveModulator。V032 新增 `learning.mlde_param_applications`，`mlde_demo_applier` 在 scheduler 內只對 `engine_mode=demo` 做 bounded autonomous apply：strategy params 走 Rust `get_strategy_params` + `get_param_ranges` + `update_strategy_params`，risk/leverage 走 `get_risk_config` + `patch_risk_config(engine=demo, source=agent)`；所有 delta / confidence / sample / promotion 閾值均為 env-tunable defaults。strong demo evidence 只產生 live `experiment_plan` candidate，仍 `requires_governance=true`。Healthcheck `[35]` learning data contract（recent-window attribution regression）、`[36]` recommendation/live lease boundary、`[37]` demo applier audit/live lease boundary。Completion report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--ml_dream_edge_unblock_completion.md`；demo autonomy report：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--mlde_demo_autonomous_applier.md`。Live 自動交易或 live 參數自動放權仍必須經 **GovernanceHub + Decision Lease + 既有 5 live gates** 批准；Rust active LinUCB arm-space 仍是 `v1_15`，rich `mlde_arm_id` 先用於 shadow/advisory，future active arm-space migration 另做。

**權威原則**：Rust `openclaw_engine` = paper/demo/live 三引擎並行唯一引擎（ARCH-RC1 1C-4 + 3E-ARCH）。Rust ConfigStore 為所有交易/風控/學習/預算參數權威，4 IPC 寫入面 → tick-level hot-reload。**禁止 restart-to-apply**。Guardian = RiskConfig 純派生視圖。Python 無交易邏輯（DEAD-PY-2 清除 ~4500 行後）。**2026-04-23 `main_legacy.py` 拆分閉環確認**：Tier B 實質閉環（54 routes / 5 sibling / `main_legacy.py` 瘦至 468 行 = 原 ~5265 行 91.1% 瘦身），詳 [archive](docs/archive/2026-04-29--claude_md_section3_pre_04_27_detail.md)；先前 2026-04-16 audit「共 1630 行 · 此層拆分未完成」敘述過期。

**進行中/阻塞**（已完成 ≤2 日的項目 + 仍活躍的 gap；2026-04-21 刷新）：
- **LEARNING-PIPELINE-DORMANT-1（P1，2026-04-16 audit · 2026-04-19 半解 · 2026-04-21 刷新）**：學習管線已部分解凍 — `edge_estimator_scheduler.py` daemon 隨 uvicorn 運作（2026-04-19 `23b14ef`），`settings/edge_estimates.json` 每小時自動刷新（mtime 2026-04-21 20:45 驗證）。**剩餘 gap**：bind cost_gate 門檻 grand_mean > −50 bps 且 ≥2 策略 shrunk_bps>0 尚未滿足（受 P1-10 結構性 fee-drag / R:R 不對稱壓制）；ONNX 訓練 pipeline 工具鏈綠但資料量不足（最大切片 `demo grid_trading BLURUSDT` 47/200 labels，ETA ~3-5d 自然累積過 200）；`experiment_ledger_snapshot.json` 結構異常；21 個 learning schema 表仍無 consumer。TODO §P1-7 / §P1-14。
- **EDGE-DIAG-1（2026-04-24 刷新）**：Phase 1+2+4 + FUP-IPC 完成（commits `5b0908b` + `1a53400` 於 02:06 CEST rebuild 後 live）。Phase 2 post-P013 clean window 74 rows / 37 fires / **+11.95 bps** 真實 signal（90% of 首跑 +223 bps 證為 vacuum + P0-13 pollution 污染，per FA H3 + PM P0-13 hypothesis 雙驗證）；Phase 3 strategy-scoped Gate 1 fallback 部署 **auto-gated by `passive_wait_healthcheck` check [11]** 當 clean n≥200 + per-strategy 樣本達標（ETA ~2026-05-01）；7 exit.* IPC 熱重載 live（`<60s` rollback 可行）；FUP-SHADOW-ENABLED-IPC P3。詳 TODO §EDGE-DIAG-1。
- **Phase 5 PAUSED**（2026-04-12 reframe）— PNL-FIX-1/2 清理後所有活躍策略 gross edge 為負；cost_gate/DL/JS 機械已接線但需真實正 edge。**下一步**：21d demo 穩定期過後（最早 2026-05-07）P0-3 重評，若仍負則轉 EDGE-P3-1 / EDGE-P2 接管。詳見 `memory/project_phase5_promotion_edge_crisis.md`。
- **P1-6 DEMO-BYBIT-SYNC-ORPHAN-1**：6 個 `bybit_sync` 倉位策略動不了；P1-8 FUP `retriage_synthetic_owner` tick-level 自主接管中，觀察一週（起算 2026-04-17）。TODO §P1-6。
- **P1-10 STRATEGY-ASYMMETRY-1**：grid 過度交易 + ma_crossover R:R 不對稱；2026-04-20 R1 驗收結論 = grid fee drag 主導（結構性，非 cadence）+ ma_crossover win rate 64% → 37.8% 崩；EDGE-P2-3 PostOnly runtime 已 2026-04-21 20:44 部署（demo/paper=true），預期 fee 降 5.5 bps → ~1 bps/side，待 ≥1w demo 資料驗正效果。TODO §P1-10。
- **P1-11 BB-BREAKOUT/REVERSION-DORMANT-1（2026-04-26 G2-06 disable + 2026-04-28 EDGE-DIAG-2 demo override）**：(2)+(3) DonchianMode + BbBreakoutProfile enum ✅（`0528d96`+`38a14ca`）。(1) G2-06 PA RFC 推 C 永久 disable + PM approve（2026-04-26）→ **2026-04-28 EDGE-DIAG-2 operator override：bb_breakout 與 funding_arb demo-only 重啟，live 仍 disable**（commit `341c093`）。理由：永久 disable = ML/agent 上線時學習盲區（違反原則 #11/#12）。1m bandwidth 結構性問題（squeeze_bw=0.03 noise floor / expansion_bw=0.04 永不達）未修，預期 7d 仍 0 fill；demo flip 是「保留可觀察性 + 等閾值/timeframe 修復」非「策略已修」。Live 重啟需新 PA RFC + 結構性修復。F2「signals≠edge」top edge 未達 95% / F3「Donchian breach 反向」RETRACT（含 current bar bias）。詳 PA RFC `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g2_06_bb_breakout_disposal_rfc.md` + EDGE-DIAG-2 報告 `.claude_reports/20260428_053101_edge_diag_2_demo_loosen_live_strict.md`。
- **EDGE-DIAG-2（2026-04-28 deploy + 2 post-deploy FUP）**：operator pushback「228/230 negative cells = 真負」結論落入採信污染資料的圈套。實證 4 污染點（median n=6 / 7d 含 04-21~22 dev-bug 期 / EDGE-DIAG-1 自證 +223→+11.95 bps / demo cost_gate 比 paper 嚴格但 demo 是唯一可信資料源 → 死循環）。落地（commits `341c093`+`8a5973f`+FUP `cdc2699`+`20baabe`，engine PID `3626554` mtime 05:28，demo 放寬/live 收緊政策）：(a) `cost_gate_moderate` 對稱低樣本探索 — `n_trades < cost_gate_min_n_trades_for_block`（預設 30）路由 exploration mode 而非 block；`cost_gate_live` 完全不動 (b) JS estimator `min_observation_ts` cutoff `2026-04-22T21:00Z`（post P0-13 ATR fix + V2 SWAP；env `OPENCLAW_EDGE_MIN_OBSERVATION_TS` 可覆寫）— `effective since = max(now-7d, cutoff)` (c) bb_breakout + funding_arb demo TOML active=true（live 仍 false） (d) 13 Rust + 17 Python 新測試。Post-deploy 驗：post-cutoff 58 cells（vs 70 pre-cutoff，~17% 排除符合預估 18%），n_trades 分佈 `<5: 21 / 5-9: 13 / 10-29: 19 / >=30: 5`，**5 個 robust 負 cells 全 grid_trading**（AAVE/GALA/ENA/DOGE/FARTCOIN，n=31~69，仍會 block）；engine 啟動 1s 內 `cost_gate(JS-demo): low sample — exploration mode` log 已 fire 確認新路徑活著。Follow-up 留尾：(i) ✅ `passive_wait_healthcheck` 新增 [31] `check_edge_diag_2_strategy_diversity`（demo 6h Approved distinct strategy count；engine restart <30 min 緩衝期 PASS-with-note） (ii) ✅ `passive_wait_healthcheck` 新增 [33] `maker_fill_rate`（2026-04-29 Linux WARN：fee_drop 1.8% / maker_like 2.1%，低於 G2-01 ≥60% 目標，後續進 G2-01 settlement/G2-04 decision） (iii) ✅ `feedback_demo_loose_live_strict_policy.md` memory 已寫並掛上 MEMORY.md 索引 (iv) demo bb_breakout 1m bandwidth 結構性問題未修，預期 7d 仍低量 (v) ✅ fee-postonly-2 column drift `cdc2699` 修 strategy-open Fill `fee_rate` 寫 TIF-aware（之前 100% 寫 taker 但 actual fee 已正確；JS estimator 用 fee_usd/notional 不受影響；已隨 `af9d552` rebuild 套用） (vi) ✅ `restart_all.sh --keep-auth` 旗標 `20baabe`（保 authorization.json 跨 planned deploy；crash/watchdog 路徑不變仍 force re-approve；§四 Gate #5 hot-rate verify 5 min re-check 不變）。
- **非阻塞留尾**：W1 event_consumer 拆分；D-02 PriceEvent metadata HashMap 移除；IP-DEDUP-1（等 P0-3 判決）。

**已完成里程碑索引**（完整敘述 + commit + 測試數保留於 `docs/archive/2026-04-15--claude_md_section3_snapshot.md`）：

| 日期 | 里程碑 |
|---|---|
| 2026-04-08 | ARCH-RC1 1C-4 WRAP ✅ |
| 2026-04-09 | StrategyAction Enum ✅ · Rust 市場掃描器 Phase A-D + QC/FA + P2 ✅ |
| 2026-04-10 | DEAD-PY-1/2 · A2 NewsPipeline · LIVE-P0/P1/P2 · Live GUI Phase 4/5/6 + 平倉按鈕 · SEC-05 XSS · SM-1 治理統一 · Signal Diamond Fix · Phase 6 Reconciler 自動降級 · W20 ✅ |
| 2026-04-11 | 3E-ARCH 三引擎並行 · Multi-Symbol Position Tracking · W21 6-04~08 ✅ |
| 2026-04-12 | E5 Performance Optimization（23 項） ✅ |
| 2026-04-13 | G-SR-1 Signal Tightening · OC-5 FundingArb · Edge 數據 engine_mode 隔離 ✅ |
| 2026-04-14 | ORPHAN-ADOPT-1 Phase 1 · QoL-1/3 · ENGINE-HEAL 4 Fix · WP-F/UX-07~10 術語統一 ✅ |
| 2026-04-15 | EDGE-P3-1 ML-MIT #26 Lane A · FA-PHANTOM-2 spec · ORPHAN-ADOPT-1 Phase 2A · engine_watchdog systemd unit ✅ |
| 2026-04-16 | P0-4 R1 STRATEGY-CLOSE-TAG-FIX · P0-0 RECONCILER-BURST-FIX · P0-5 PHANTOM-2-FUP · PAPER-DISABLE-1 · DEDUP-PY-RUST Tier A · EDGE-P3-1 Phase B #3 + Step 7b/7c · G-2 daemon option D ✅ |
| 2026-04-17 | P0-10 SCANNER-GATE · P0-5 PHANTOM-2-FUP · P1-8 DUST-EVICTION-GAP-1 E1/E4 · MICRO-PROFIT-FIX-1 ✅（詳 `docs/archive/2026-04-20--claude_md_section3_snapshot.md`） |
| 2026-04-18 | LIVE-GATE-BINDING-1 · E5-P0 Refactor Wave · P1-16 HALT-SESSION CROSS-SYMBOL PRICE CORRUPTION ✅（詳 `docs/archive/2026-04-20--claude_md_section3_snapshot.md`） |
| 2026-04-19 | PIPELINE-SLOT-1 Phase 1-4 · E5-P1 Refactor Wave 1 · E5-P2 Refactor Wave 2 · FILL-CONTEXT-LINKAGE-1 · EXIT-FEATURES-TABLE-1 Phase 1b FUP · E5-FN Functional Defects Wave ✅（詳 `docs/archive/2026-04-21--claude_md_section3_snapshot.md`） |
| 2026-04-20 | **EDGE-P2-2 Phase A** ✅ `381c542`（OI confluence signal for `bb_breakout` — 3 新參數 `enable_oi_signal`/`oi_buffer_window_ms`/`oi_confluence_bonus`/`oi_min_delta_pct` + 3 env TOML；E2 對抗性審查 7 findings 全修（#1 buffer dedup / #2 on_rejection preserve / #3 noise floor / #4 validate_oi factory mirror / #5 hot-reload smoke / #6 ts regression guard / #7 unit coverage）；engine lib 1770→**1791** passed；Phase B Liquidation signal 待做） · **LLM-ABC-MIGRATION-1** ✅（5 call-site 切 `local_llm_factory.get_local_llm_client()` — `ai_service.py` / `strategy_wiring.py` / `layer2_engine.py` / `layer2_routes.py` / `layer2_tools.py`；新 `app/local_llm_factory.py` + `LMStudioShimClient` 暴露 OllamaClient-shape 介面回 `OllamaResponse`，call-site parsing 零變動；`LOCAL_LLM_PROVIDER` env 切 `ollama`(default)/`lm_studio`，未知值 fallback Ollama；17 pytest 新測 + 11 既有 patch-target 更新 + 1 訊息文案對齊；business code 0 `import OllamaClient`；**Mac operator 設 `LOCAL_LLM_PROVIDER=lm_studio`+`LM_STUDIO_BASE_URL` 即可不裝 Ollama 跑 Layer 2**；閉合 CLAUDE.md §七「LocalLLMClient 抽象乾淨」既有技術債） |
| 2026-04-21 | **主軸** `TRACK-P-T4-WIRING-1` ✅ `e95c779`（Priority 6 T4 closure 接線 + `build_exit_features_for_tick` pure fn；engine lib 1827→1839；20:44 CEST `--rebuild` runtime 部署）· **DUAL-TRACK-EXIT-1 Phase 1b Track P v2 pure fn** ✅ `aee96b9` · **GATE1-REVERSAL-1 hotfix A** ✅ `d0f0c21` · **EDGE-P2-3 Phase 2+ (b) bb + ma PostOnly entry** ✅ merges `f5f4dc2`+`8280132`（demo/paper=true, live=false）· **outcome_backfiller wiring fix** ✅ `5e2981d`（timeframe `'1'→'1m'` + engine_mode INSERT；歷史回填 ~267k rows）· refactor split 系列 `3a9b988` / `580304a` / `bfedb56` / `d454c17` / `c164cb6` — 全 14 項詳見 `docs/archive/2026-04-21--completed_todo_batch.md` |
| 2026-04-22 | **TICK-PIPELINE-MOD-SPLIT-1** ✅ `3d67a99`（`tick_pipeline/mod.rs` 2274→**1012** 行進 §七 1200 硬上限；impl 拆 3 sibling `pipeline_ctor/pipeline_config/pipeline_helpers`；engine lib 1835 / 0 failed 零變）· **TRACK-P-V2-SWAP-1** ✅ `306993e`（Priority 6 v1 linear → v2 non-linear；`RiskConfig.phys_lock`→`RiskConfig.exit` + `ExitConfig` 熱重載；v1 pure fn + 8 v1 直測整塊退役；20:55 CEST `--rebuild` 部署 engine PID 158918）· Step 0 衍生新 TODO 章節 5/5 ✅ 歸檔 `docs/archive/2026-04-22--step_0_derived_todo_batch.md` |
| 2026-04-24 | **TODO 10-Agent Audit 重構** ✅ — Operator 指令下派 PM/FA/PA/CC/QC/QA/AI-E/MIT/E5/BB **10 個獨立 agent** 各自 audit，每個寫 `docs/CCAgentWorkSpace/<agent>/workspace/reports/2026-04-24--4.24TodoAudit.md`；PA 整合出 FIX-PLAN（45 findings / 6 工作組 G1-G6 / 4 wave / 7-layer TODO 骨架，27 KB `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan.md`）；PM Sign-off Approved with 6 minor adjustments（`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-24--FixPlan_PMApproval.md`）；舊 TODO 700 行歸檔 `docs/archive/2026-04-24--todo_snapshot_pre_refactor.md`；新 TODO 328 行（精煉 53%，每條帶 audit + FIX-PLAN 指針）；audit 索引 `docs/audits/2026-04-24--todo_refactor_audit.md`。**3 大 Verified 發現**：(1) `settings/edge_estimates.json` 實測僅 **1 cell**（grid_trading::ORDIUSDT, n=3, grand_mean=-45.73）mtime 2026-04-20 4d 停滯（vs CLAUDE.md 宣稱 162 cells 嚴重過期） → edge_estimator_scheduler daemon 4d 未運行是 edge dormancy root cause (2) PostOnly 配置 demo=false/live=true **反向**（讀 `strategy_params_{demo,live}.toml`）違反原則 #6（失敗默認收縮） (3) ExecutorAgent `_shadow_mode=True` hardcoded（已修：G3-03 Phase B `shadow_mode_provider` 已 production at `program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:145-186`） — 違反原則 #3（AI 輸出 ≠ 即時命令），5-Agent→Rust IPC 物理斷路 ✅。**主路徑**改 Wave 1-4 結構：W1 G1 scheduler+fn 拆+G6 healthcheck → W2 G3 AI 接線+G5 refactor+G4 ML → W3 EDGE-DIAG Phase 3+Phase 1b → W4 LG-2/3/4/5+P0-3 決策 → Live（最早 ~2026-05-23）。純 doc 重構無代碼邏輯變更，engine lib baseline 1980 不變 |
| 2026-04-24 | **P1-11 BB-BREAKOUT/REVERSION-DORMANT-1 全工** ✅（多輪 audit 收尾）— (2) `DonchianMode::{Hard,Score,Off}` + (3) `BbBreakoutProfile::{Conservative,Balanced,Aggressive}` enum + helper（`0528d96`+`38a14ca`，Hard/Balanced bit-identical 保留 + 14 tests）· (1) Phase 1 Python 信號級 sweep `helper_scripts/research/bb_breakout_threshold_sweep.py`（`148bd96`）+ 多輪 self-audit + QC/MIT/PM/PA/FA multi-role parallel audit（3 sub-agent 揭 5 FAIL + 6 WARN 全修：mod.rs:492 saturating_add 對稱 / Python ddof=1 + df-aware t_crit + Bonferroni / cluster-SE / leak-free Donchian shift(1) / +4 boundary tests / [12] healthcheck `bb_breakout_post_deadlock_fix`）· **F4 Rust bug FIX-26-DEADLOCK-1 發現並修**（`bcc5401`+`63957ad`）— `squeeze_detected_ms` 過期後無清除路徑，首次 squeeze 窗口無入場 → symbol 永久 dormant；修：is_none() guard 前加 expiry auto-clear + 7 regression tests · F1 1m scale mismatch CONFIRMED（squeeze_bw=0.03 100% 觸發，expansion_bw=0.04 永不達）· F2 signals≠edge 方向觀察成立但 top edge 未達 95% · F3 RETRACT — Donchian 含 current bar 是 measurement bias，leak-free 下消失 · engine lib 1939 → **1980 passed / 0 failed** · 待 `--rebuild` 部署 FIX-26-DEADLOCK-1；healthcheck [12] cron 6h 報 fill 復活；報告 `.claude_reports/20260424_024807_p1_11_qcmitpmpafa_audit_closeout.md` |
| 2026-04-28 | **EDGE-DIAG-2 demo 放寬 / live 收緊** ✅ commits `341c093`+`8a5973f`（engine PID `3626554` mtime 05:28 已 deploy）— Operator pushback：「228/230 negative cells = 真負」結論落入採信污染資料的圈套。實證 4 污染點（median n=6 / 7d 含 04-21~22 dev-bug 期 / EDGE-DIAG-1 自證 +223→+11.95 bps / demo cost_gate 比 paper 嚴格但 demo 是唯一可信資料源 = 死循環）。落地 4 項：(a) `cost_gate_moderate` 對稱低樣本探索（`SlippageConfig.cost_gate_min_n_trades_for_block` 預設 30，`n<30` 路由 exploration mode 而非 block；`cost_gate_live` 完全不動 + 新增 unit test 釘 live n=3 仍 fail-closed） (b) JS estimator `min_observation_ts` cutoff `2026-04-22T21:00Z`（post P0-13 ATR fix + V2 SWAP；env `OPENCLAW_EDGE_MIN_OBSERVATION_TS` 可覆寫；effective `since = max(now-7d, cutoff)`） (c) `[bb_breakout].active=true` + `[funding_arb].active=true` 僅 `strategy_params_demo.toml`（live 仍 false；G2-06 + G-2 verdict demo-only override，理由：永久 disable = ML/agent 上線時學習盲區） (d) 13 Rust + 17 Python 新測試（cargo lib **2308 / 0 failed**；pytest 17/17 PASS）。Post-deploy 驗：post-cutoff 58 cells（vs 70 pre-cutoff，~17% 排除符合預估 18%），n_trades 分佈 `<5: 21 / 5-9: 13 / 10-29: 19 / >=30: 5`；**5 個 robust 負 cells 全 grid_trading**（AAVE/GALA/ENA/DOGE/FARTCOIN，n=31~69，仍會 block）；engine 啟動 1s 內 `cost_gate(JS-demo): low sample — exploration mode` log 已 fire。Live 硬邊界完全保 — `strategy_params_live.toml` 未動、`cost_gate_live` 未動、`missing_edge_fallback_bps` 維持 -10。**2 個 post-deploy FUP**（同 2026-04-28 但 ~12:20 CEST，未進 runtime engine PID 3626554）：(α) `cdc2699` fee-postonly-2 — Rust `step_4_5_dispatch.rs:617` strategy-open Fill 改用 `fee_rate_for_intent(symbol, intent)`（TIF-aware）取代 `fee_rate(symbol)`（hardcoded taker）。先前 SQL 驗 `fee_rate` 100% 寫 0.00055 taker（即便 ma_crossover 實際 ~50% maker fill）；actual `fee` 欄位已對 → JS estimator 不受影響、5 robust 負 cells 仍真實負；本修純清 DB column 失真供 operator audit / future ML feature。其他 fee_rate(symbol) call sites 驗安全（commands.rs 5 site 平倉路徑 by design Market；step_6_risk_checks.rs:128 PositionRow 已成交 taker 為保守估計；pipeline_helpers.rs:134 close-path）。next `--rebuild --keep-auth` 套用。 (β) `20baabe` `restart_all.sh --keep-auth` 旗標 — default 行為不變（write `last_shutdown_kind=manual` sentinel = operator-initiated restart 視 security event force re-approve）；新 `--keep-auth` 主動 `rm -f` stale sentinel 並 skip write，使 engine 下次 boot 沿用 authorization.json。crash/watchdog/systemd 自動 restart 路徑不跑此 shell，永遠保 auth；§四 Gate #5 HMAC sign + 未過期 + env_allowed match 5 min re-verify 不變，過期 auth 仍 fail-closed。Operator workflow：一次 GUI approve → 後續 `--rebuild --keep-auth` 不需重 approve。Skipped formal RFC per operator decision。報告 `.claude_reports/20260428_053101_edge_diag_2_demo_loosen_live_strict.md` |
| 2026-04-26 | **Wave 3 第二/三波派發 + G2-06 bb_breakout 永久 disable** ✅ — (a) PA G2-06 RFC `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g2_06_bb_breakout_disposal_rfc.md` 推 C 永久 disable + PM approve（vs B 升 5m：dominated strategy 分析、ROI 不利、F2 未驗證、Wave 3 主軸擠壓）(b) E1 落地 4 子任務：[bb_breakout].active=true→false 三環境 TOML（demo/paper/live）+ 雙語 disable comment / healthcheck [12] active=false → PASS skip / 新增 [18] disabled_strategy_inventory（CLAUDE.md §三 G6-04 drift 防線）/ BbBreakoutProfile + sweep tool 保留為 future investment（per §6 重啟條件 6 個月）(c) E1 G2-02 ma_crossover counterfactual replay tool（PM 派發 QC (c) 並行：寫碼 + passive 等 G7-09 1w demo data ~05-03 雙軌驗證）(d) E1 G8-02 Python↔Rust ExecutorAgent decision parity 70-case ≥95%（shadow_mode 主導；cap/pct 在 RiskConfig.executor schema 但 runtime 未 wire 屬 G3-08 future） · 重啟需新 PA RFC + 5m timeframe 升級 |
| 2026-04-23 | **DEDUP-PY-RUST 全鏈閉環 A+B+C+D** + **INFRA-PREBUILD-1 Part A（Combine Layer shadow 骨架）** + **INFRA-PREBUILD-1 Part B（Model Registry + Canary 骨架）** + **WS-RETIRE-1（Python `bybit_private_ws_listener.py` 退役）** ✅ — engine lib **1910 passed**；淨減行數 Rust +685 / Python+shell -12.8k（98 shells + 3 retire + 7 governance）；詳 [`docs/archive/2026-04-29--claude_md_section3_pre_04_27_detail.md`](docs/archive/2026-04-29--claude_md_section3_pre_04_27_detail.md) |

**歷史細節指針**（不要重複載入）：
- §三 2026-04-16 STABILITY-1/LIVE-GUARD-1 + 2026-04-19 完整敘述 → `docs/archive/2026-04-21--claude_md_section3_snapshot.md`
- §三 2026-04-17/18 完整敘述 → `docs/archive/2026-04-20--claude_md_section3_snapshot.md`
- §三 2026-04-15 之前完整敘述 → `docs/archive/2026-04-15--claude_md_section3_snapshot.md`
- 1A→1C-4 commit 敘事 → `docs/archive/2026-04-08--arch_rc1_1c_history_archive.md`
- Phase 0-4 Sprint/Wave → `docs/archive/2026-04-07--claude_md_section3_history_phase0_4.md`
- 逐 commit 行數 → `docs/CLAUDE_CHANGELOG.md`
- 1C-3/1C-4 narrative → `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`

---

## 四、硬邊界（永遠不能違背）

```python
# ── Live_Ready 真實狀態 ──
# LIVE-P0/P1/P2 代碼完整（SM-01/02/04 + Reconciler + 3E-ARCH），0 真實 live 流量
# （歷史 43k 條 engine_mode="live" 實為 LiveDemo）。

# 真實 live 門控（Rust 端可驗證 = 4 項 / 全部 = 5 項）：
#   1. Python `live_reserved` global mode           （Python 側，重啟會丟）
#   2. Python Operator 角色 auth                    （Python 側）
#   3. OPENCLAW_ALLOW_MAINNET=1 env var             （Rust 側，僅 Mainnet）
#   4. secret slot 有 api_key + api_secret          （Rust 側，憑證空 → Err；
#        Mainnet env-var fallback 封閉，來源優先級見 bybit_rest_client.rs:386-497）
#   5. authorization.json 簽名+未過期+env_allowed 匹配  （Rust 側，HMAC-SHA256）
#        路徑：$OPENCLAW_SECRETS_DIR/live/authorization.json
#        檢查點：build_exchange_pipeline 啟動 + main.rs 每 5 min re-verify
#        失效 → engine 優雅 shutdown（cancel_token）
#        涵蓋 LiveDemo + Mainnet（LiveDemo 不因 api-demo endpoint 降級）
#        **必經** Python renew/approve 路由 `_write_signed_live_authorization()`，不可手動寫

# execution_authority：Rust 僅為 P0/P1 denylist 字串常量
# （claude_teacher/applier.rs:226），非真實授權邏輯；「auto_granted_on_start」屬 Python 概念。
decision_lease_emitted  = False
max_retries             = 0

# 永不允許的硬錯誤：
# - 繞過 Operator 角色認證或 live_reserved 直接啟動 live session
# - 自動修改 engine trading_mode 為 live（需 operator 顯式配置）
# - ML / DreamEngine / ExecutorAgent / StrategistAgent 直接 live 下單或修改 live 參數而未經 GovernanceHub + Decision Lease 批准
# - Bybit API timeout / retCode != 0 → fail-closed，不重試
# - should_call_ai=true 但 invocation 沒發生；偽造 AI 調用或交易活動
# - Mainnet 下無 OPENCLAW_ALLOW_MAINNET=1，或用 env var 當唯一憑證來源
# - Live（含 LiveDemo）下無有效 authorization.json 即 spawn pipeline
```

---

## 五、架構總覽

```
[數據與觀察層]           Bybit REST + WS → Postgres + Observer
[H0 本地判斷內核]        freshness / health / eligibility / risk envelope（<1ms SLA）
[GovernanceHub]          SM-01 授權 + SM-04 風控 + SM-02 租約 + EX-04 對賬
[H1-H5 AI 治理層]       thought_gate / budget / model_router / governor / cost_logging
[I Decision Lease]       GovernanceHub.acquire_lease() / release_lease()
[Control API v1]         FastAPI 209 /api/v1 + 11 non-api 路由（2026-04-16 audit 實測）
[GUI + Learning]         11-Tab 控制台 + Learning Cockpit + Paper Trading Dashboard
[Rust openclaw_engine]   paper / demo / live 三模式唯一引擎（1C-3-F 後）
                         tick pipeline + IntentProcessor + paper_state + governance + stop_manager
[Layer 2 AI 推理]        L0 確定性 → L1 Ollama → L2 Claude
[風控框架]               P0/P1/P2 三層 + 對抗性止損 + AI 注意力稅
[策略工具包]             KlineManager → IndicatorEngine → SignalEngine → 5 策略 → Orchestrator
[管線橋接]               PipelineBridge: Tick Fan-Out + Intent→Order + 治理 gate
[止損管理器]             StopManager: Hard/Trailing/Time Stop + ATR 動態倉位
```

---

## 六、路徑與啟動

```
GitHub repo:    yunancun/BybitOpenClaw
本地主工作樹:   由 $OPENCLAW_BASE_DIR 決定（repo 任意絕對路徑皆可）
                Linux 預設: $HOME/BybitOpenClaw/srv（/home/ncyu/srv ← symlink, legacy）
                Mac   範例: /Users/ncyu/Documents/Projects/TradeBot（或 $HOME/BybitOpenClaw/srv）
本地-only：     settings/（secrets）  trading_services/（runtime）
```

### 跨平台 Runtime 路徑（Mac/Linux 共用）
**Mac dev 必設**（Linux 上可選，默認 `/tmp/openclaw` + `$HOME/BybitOpenClaw/`）：
```bash
# Repo 位置（任意路徑皆可，例如 /Users/ncyu/Documents/Projects/TradeBot）
export OPENCLAW_BASE_DIR="/Users/ncyu/Documents/Projects/TradeBot"

# Runtime / socket / log 目錄（Mac /tmp 是 /private/tmp symlink，必須顯式設）
export OPENCLAW_DATA_DIR="$HOME/.openclaw_runtime"

# Secrets 根目錄（含 environment_files/ + secret_files/）
export OPENCLAW_SECRETS_ROOT="$HOME/.openclaw_secrets"

# Bybit slot base（Rust/Python 專用，= $SECRETS_ROOT/secret_files/bybit）
export OPENCLAW_SECRETS_DIR="$HOME/.openclaw_secrets/secret_files/bybit"

# 歸檔目錄（clean_restart / fresh_start 寫入）
export OPENCLAW_ARCHIVE_DIR="$HOME/.openclaw_archive"

mkdir -p "$OPENCLAW_DATA_DIR" "$OPENCLAW_SECRETS_ROOT/environment_files" \
         "$OPENCLAW_SECRETS_ROOT/secret_files/bybit" "$OPENCLAW_ARCHIVE_DIR"
```
原因：Mac `/tmp` 是 `/private/tmp` symlink 且 LaunchAgents 看到不同路徑；Mac 上跑 pytest、`restart_all.sh`、IPC socket 都必須走 `$OPENCLAW_DATA_DIR`。Linux 上不設時 fallback 到 `/tmp/openclaw` + `$HOME/BybitOpenClaw/{secrets,archive}`，行為不變。

**env var 語義速查**：
| env var | 指向 | 誰在讀 |
|---|---|---|
| `OPENCLAW_BASE_DIR` | repo 根（srv） | Rust `startup.rs` / `strategies` · Python 多處 · `start_paper_trading.sh` |
| `OPENCLAW_DATA_DIR` | runtime（sockets / logs / flags / snapshot） | Rust engine · API · scripts |
| `OPENCLAW_SECRETS_ROOT` | secrets/ 根（含 env_files + secret_files） | shell scripts（restart/clean/fresh） |
| `OPENCLAW_SECRETS_DIR` | secrets/secret_files/bybit（slot base） | Rust `bybit_rest_client` · Python `bybit_rest_client.py` · live_auth |
| `OPENCLAW_ARCHIVE_DIR` | archive（damaged_/fresh_start_ dumps） | clean_restart / fresh_start |
| `OPENCLAW_SRV_ROOT` | ⚠️ legacy alias，同 `OPENCLAW_BASE_DIR` | `bybit_path_policy.py` + 115 歷史 maintenance scripts — **新代碼請用 `OPENCLAW_BASE_DIR`**，兩者互不 fallback，Mac 部署時建議 `export` 同值 |

**Mac 差異注意**：`$HOME/.openclaw_runtime` **不會**在開機時被清（Linux `/tmp` 每次重啟清空），因此：
- `engine_maintenance.flag` 若上次異常留下會阻塞 watchdog → 開工前先 `rm -f "$OPENCLAW_DATA_DIR/engine_maintenance.flag"`
- 舊 socket 檔（`engine.sock` / `ai_service.sock`）殘留會讓新 process 拒綁 → 啟動前清或讓腳本 unlink 舊 socket
- 建議 Mac `.zshrc` 加 `alias oc-clean-runtime='rm -f "$OPENCLAW_DATA_DIR"/{*.sock,engine_maintenance.flag}'`

### 啟動檢查（每次 session 起點）

**Linux 端（trade-core 本地 session）**：
```bash
git status && git log --oneline -5
python3 helper_scripts/canary/engine_watchdog.py --data-dir "$OPENCLAW_DATA_DIR" --stale-threshold 45 --grace-period 120 --status
```

**Mac 端（SSH bridge workflow，2026-04-21 起）**：
```bash
git status && git log --oneline -5                                    # Mac 本地 repo 狀態
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -5"       # Linux repo 狀態（可能領先）
ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status"  # engine 真實狀態
```
Mac 本地跑 watchdog 永遠回 `engine_alive: false`（engine 只跑 Linux，見 `memory/project_dev_runtime_split.md`）；必須透過 ssh 查。Mac 接手三連 = git status + ssh Linux git log + ssh Linux watchdog。

R-07 Go/No-Go 已 PASS（見 `memory/archive/project_rust_migration_status.md`）。watchdog 回 `engine_alive: false` 代表引擎沒在跑，按 TODO.md 重啟指引處理（Mac 端：`ssh trade-core "bash helper_scripts/restart_all.sh --rebuild"`）。

### TODO.md 強制規則（每次接手必須遵守）

**接手時：** 必須讀 `TODO.md` 確認當前工作狀態，找第一個 `[ ]` 未完成項作為起點。用戶有明確指令時以用戶為準。

**發現新問題時：** 立即追加到 TODO.md，不等會話結束。

**修復完成後：** `[ ]` → `[x]`，追加完成 commit 號，更新測試基準線。

---

## 七、代碼與文檔規範

### ★★ 跨平台兼容性（強制，所有開發必須遵守）

**大前提：項目必須隨時可以部署在 macOS 上運行。**

1. **路徑不硬編碼** — 所有路徑使用環境變量或 config，禁止任何 user-home 絕對路徑字面值（`/home/ncyu/`、`/Users/ncyu/`、`/Users/<name>/…/TradeBot` 等）。
   用 `os.environ.get("OPENCLAW_BASE_DIR", ...)`、docker-compose 相對路徑（`../../settings/...`），或 `Path(__file__).parent` 相對路徑。
   E2 必查：`grep -E '(/home/ncyu|/Users/[^/]+)' <diff>` 新代碼命中 → 打回（歷史 worklog / dated snapshot / 政策反例引用不在此限）。

2. **LocalLLMClient 抽象乾淨** — 不洩漏 Ollama-specific 細節。
   所有 LLM 調用通過 `LocalLLMClient` ABC 接口（Phase 1 任務 1.8）。
   禁止在業務邏輯中直接調用 Ollama HTTP endpoint。

3. **服務部署可遷移** — systemd → launchd 遷移路徑清晰。
   服務配置邏輯寫成文檔或腳本（`helper_scripts/deploy/`）。
   不依賴 systemd-specific 特性（如 `sd_notify`）。

4. **依賴管理乾淨** — `requirements.txt` 保持更新，禁止隱式依賴。
   新增 `import` 時同步更新 requirements。E2 必查。
   避免 Linux-only 依賴（如 `psutil` 的 Linux 特定 API），需要時加平台守衛。

### 雙語注釋（強制）
每個新建/修改的函數、類、模塊必須中英對照注釋（MODULE_NOTE / docstring / inline / fail-closed 路徑 / 安全代碼）。E2 必查。

### 新 SQL migration 規範（強制，2026-04-24 V023 postmortem 新增）

**背景**：2026-04-23 `V023__model_registry.sql` 入 repo 但在 Linux 上**靜默 no-op** —— V004 早已預建了缺 `canary_status/verdict` 的 legacy `learning.model_registry` stub；`CREATE TABLE IF NOT EXISTS` 看到表存在就跳過，下游 Rust 讀 `canary_status` 全空。`helper_scripts/db/audit_migrations.py` 事後才能抓到。**更好的防線是 migration 內的 DO block guard，對 legacy drift 主動 RAISE**。

**規則**（4 條，E2 必查）：
1. **Guard A 強制**：任何 `CREATE TABLE IF NOT EXISTS schema.table (...)` **前必加**一個 DO block，驗表若已存在則必要欄位俱在；缺 ≥1 即 `RAISE EXCEPTION`。模板見 `sql/migrations/templates/schema_guard_template.sql § Guard A`。
2. **Guard B 強制（型別 matters 時）**：`ALTER TABLE ... ADD COLUMN IF NOT EXISTS col TYPE` 前，若該 column 類型錯會讓下游 writer 失敗，**必加** Guard B 驗 `information_schema.columns.data_type`；型別不符即 RAISE。模板同檔 § Guard B。
3. **Guard C（hot-path 索引選用）**：`CREATE INDEX IF NOT EXISTS` 若索引欄位組合關鍵（production 熱查詢依賴），加 Guard C 比對 `pg_get_indexdef()`；純 audit / 低頻索引可略。
4. **Idempotency 驗證**：每個新 migration 本地跑兩次 `psql -f V<NNN>__<desc>.sql`，第二次必須**不 RAISE**（shape 已正確時 guard no-op）。違反 = E2 打回。
5. **範例** retrofit：`sql/migrations/V023__model_registry.sql`（Guard A `learning.model_registry`）+ `sql/migrations/V021__fills_exit_source.sql`（Guard A `learning.decision_shadow_exits` + Guard B `trading.fills.exit_source` + Guard B `learning.decision_shadow_exits.ts`）。新 migration 以此兩檔為 reference。

**測試**：`sql/migrations/tests/test_schema_guards.sql` 提供 9 個單測（3 guard × {pass / fail / no-op}），無 pgTAP infra 下直接 `psql -d <test_db> -f` 跑；grep NOTICE 無 `FAIL` 即綠。

### Engine 自動遷移（opt-in，2026-04-24 Phase 2 新增）

**背景**：V023/V019/V021 silent-noop postmortem 顯示 100% 手動 `psql < V*.sql` 會漏套用。Phase 2 在 `openclaw_engine` 啟動時加一條 opt-in 自動遷移管線，**預設關**，operator 逐步驗證後再開。

**兩條套用路徑並存**：
- **手動（預設）**：`bash helper_scripts/linux_bootstrap_db.sh --apply` — 既有流程不動，此 Phase 不移除。
- **自動（opt-in）**：環境變數 `OPENCLAW_AUTO_MIGRATE=1` 時，engine 啟動在 DbPool 連線後、writer 啟動前呼叫 `openclaw_engine::database::migrations::MigrationRunner::run_if_enabled()`：
  1. 自刻 parser 讀 `sql/migrations/V###__*.sql`（sqlx 內建 parser 不吃 Flyway 格式）；`V017_rollback.sql` / `V999__*.sql` 依檔名過濾。
  2. 若 `_sqlx_migrations` 空且 `learning.model_registry` 存在（V023 canary），seed V001-V023 為「已套用」狀態 — 符合 2026-04-24 postmortem 後的 live DB 狀態。
  3. 跑 `Migrator::run_direct` 套用 pending（目前無，V024+ 時才會有）；checksum 比對失敗 / 曖昧狀態 / canary 不成立 → 中止啟動（`exit 1`），**不靜默吞**。
- **安全準則**：ambiguous state（有 app schema 但無 V023 canary）= 硬性 RAISE，不自動猜測；operator 跑 `helper_scripts/db/audit_migrations.py` 後人工介入。

**Rollback path（engine refuse to start）**：若 `OPENCLAW_AUTO_MIGRATE=1` 打開後 engine 不肯啟動，operator 立即：
1. Stop engine（`restart_all.sh --stop`）。
2. 關 env：`unset OPENCLAW_AUTO_MIGRATE` 或 env file 改回空。
3. 回到手動流程 `bash helper_scripts/linux_bootstrap_db.sh --apply` 補任何 pending migration。
4. 重啟 engine（`--rebuild` 非必要，除非改了 Rust 碼）。

**測試**：`rust/openclaw_engine/src/database/migrations.rs` 15 個 unit tests（純解析 / 無 DB）+ `rust/openclaw_engine/tests/migrations_test.rs` 5 個整合測試（需 `OPENCLAW_TEST_PG` 連線字串；無則自動跳過；`fresh_db_applies_all_migrations_end_to_end` 另需 `OPENCLAW_TEST_PG_DESTRUCTIVE=1` ack）。

### 被動等待 TODO 必附 healthcheck（強制，2026-04-23 新增）

**背景**：2026-04-22 P0-13 ATR scale + P0-14 edge miss 雙 bug 經「被動等待 24h observation」流程放行；後續 review 才發現 7d `phys_lock` 0 fire 其實是 silent-dead，observation window 本身無法偵測。結論：**任何「被動等待 Nd / Nw」的 TODO 必須同步附一條可執行 healthcheck**，由 cron 或 operator 手動間隔跑，確認被動等待的前提（pipeline 活著 / 信號流通 / fires 發生中）仍成立。缺此項 = 無法區分「沒事所以沒動」vs「壞了所以沒動」。

**規則**（4 條，E2 必查）：
1. **登記門檻**：TODO 新增「被動等待 Nd / Nw」類條目時，必須同時：(a) 在 `helper_scripts/db/passive_wait_healthcheck.py` 加一個 `check_*()` function（通常 1 SQL or 1 oneliner）;(b) TODO 文本引用該 check id。
2. **檢查語意**：check 回 `"PASS" / "WARN" / "FAIL"`，**Exit 1 = silent-dead 自動偵測** — 不是「沒資料」就 PASS。若被動等待假設「每 N 小時該有 ≥1 次 fire」，check 就要驗 fire count ≥ 1 and ts > now() - N hours。
3. **節奏建議**：operator 每 6h cron 跑 `passive_wait_healthcheck.py`，任一 FAIL 即檢查該 TODO 的前提是否仍成立。本檔已有 7 個 check（close_fills / label_backfill / exit_features_writer / phys_lock / micro_profit / trailing_stop / edge_estimates freshness），新增按此樣式追加即可。
4. **違規處理**：新增被動等待 TODO 未附 healthcheck = E2 審查打回；已有被動等待 TODO 若對應 pipeline 沒 healthcheck 覆蓋 = 下一輪維護週期必補。

**觸發情境例**：
- 「等 21d demo 穩定」→ check：demo engine_alive last 24h + 0 engine_crash 次數
- 「等 7d counterfactual replay」→ check：replay 結果檔存在且 mtime > script last run
- 「等 1w PostOnly fee 驗證」→ check：maker fill rate > X% 且 demo fee 降幅達標

### 強制同步規則
- **Sprint/Wave 完成**：更新 §三 + §十一 + `docs/CLAUDE_CHANGELOG.md` + README，與生產代碼同 commit
- **§三 衛生規則（強制）**：§三 只記載「現況/活躍狀態」+「過去 ≤2 天的完成里程碑」。**任何完成里程碑當天 +2 日（以 `currentDate` 為準）必須在 commit 同次操作中歸檔到 `docs/archive/YYYY-MM-DD--claude_md_section3_*.md`** 並從 §三 刪除，僅在「已完成里程碑索引」表保留 1 行條目。違反 = §三 膨脹回 ~10K tokens、context 提早撞 compact。
- **§三 敘述 vs runtime drift 防線（強制，2026-04-24 G6-04 V023 postmortem 衍生）**：§三 任何「runtime 數值 + 狀態」（cell count / row count / fill rate / binary mtime / commit progress / fire 次數）必註明採集時間 + 對應 healthcheck id；滿 7 日未經自動化重驗即必須更新或從 §三 刪除；CC 收到 §三 數字當決策輸入時必先實測 source-of-truth 才採納，發現 drift 同 commit 修。詳 `docs/lessons.md` 條目「2026-04-24 · CLAUDE.md §三 敘述 vs runtime drift」。E2 必查。
- **Commit 時**：摘要追加到 `docs/CLAUDE_CHANGELOG.md` 頂部，格式 `### 標題（YYYY-MM-DD · commit XXXXXXX）`
- **Context ≥90%**：立即寫 `docs/worklogs/YYYY-MM-DD--session_progress_N.md`（已完成/進行中/未完成/決策/下一步）
- **每日整合**：當天 worklog 碎片合併為 `YYYY-MM-DD--daily_summary.md`，刪碎片
- **新腳本**：MODULE_NOTE 雙語 + latest+dated 輸出 + contract check + 更新 SCRIPT_INDEX.md
- **docs/**：分類目錄 + `YYYY-MM-DD--描述.md` + 更新 `docs/README.md` 索引

### 本地 LLM 審核協作（Mac 環境，強制）

Operator 在 Mac 並行跑 Qwen3.6-35B（LM Studio）做代碼審核。CC 每完成一個任務，必寫結構化報告至：

    .claude_reports/YYYYMMDD_HHMMSS_<短描述>.md

（`.claude_reports/` 在 `.gitignore`，僅本機留存；供本地 LLM 審核 + 開發編年史 — 與 `docs/worklogs/` 職能互補：worklog 是會話時序流水，claude_report 是單任務審核單位）

**6 節必備**（中文，繁簡皆可）：
1. **任務摘要** — operator 意圖白話重述 + 完成狀態
2. **修改清單** — 逐檔 `path | 新增/修改/刪除 | 行數 | 一句話說明`
3. **關鍵 diff** — 最能說明變更的片段（非全量）
4. **治理對照** — 涉及的 DOC/SM/EX/P0 編號 + 符合 / 違反 / 未規範 / 建議修改文件
5. **不確定之處** — 未確認假設 / 跨平台風險（對照 §七.★★）/ 測試覆蓋判斷
6. **Operator 下一步** — 審查重點 / Mac CC 透過 SSH bridge 已做的驗證（cargo test / psql / engine log）/ 若需 operator 親自動手的步驟（high-risk per-case 授權項 / Linux 端 interactive 操作）

**Git 自動化（強制，2026-04-21 operator 加嚴：所有 commit 必 push）**：
- CC 每完成一個**合理可交付單位**（任務完成 + 本節 report 已寫 + 無跑不過的測試）→ 自動 `git add` + `git commit` + **`git push origin main`**（三者同 Bash 鏈內完成，不允許 commit 後留著沒 push 就結束回合）
- **無例外**：Mac CC / Linux CC 都遵守「commit 即 push」；維持 Mac / Linux / origin 三處 state 一致性
- **Session 接手三連 sync**（所有 CC 起手必做）：`git fetch --prune origin` + 若 local 落後 `git pull --ff-only` + 若 local 超前（前 session 漏 push）`git push origin main` —— 例行自動做，不待 operator 提醒
- **Mac CC 觸發 Linux 驗證前**：push 完接 `ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"` 同步 Linux 工作樹
- **ff-only pull 失敗（divergent branches）**：報告 operator，不擅自 merge/rebase（CC 本地規則仍禁這 3 op）
- 詳 memory `project_ssh_bridge_workflow.md`「硬規則：commit 完必 push」章節
- **CC 絕不執行**：`pull` / `merge` / `checkout` / `reset` / `rebase`（狀態變更操作留給 operator）

### Mac dev-only 模式（環境檢測 + 操作細節）

**環境檢測**：CC 從 system prompt `Platform:` 讀取，**不分大小寫**做子串比對：含 `darwin` → Mac dev-only · 含 `linux` → trade-core 生產（Linux session 實測回 `Linux`，Mac 回 `darwin`）。下面 4 條僅在 Mac 端生效，**不必詢問 operator**。

1. **pytest 必從 srv root 跑** — 部分測試用絕對 import `from program_code.…`，從 `control_api_v1/` 內跑會 `ImportError: No module named 'program_code'`（例：`test_earned_trust_engine.py`）。
2. **整合測試打真實 Bybit 會 fail —— by design** — 3 個 secret slot 已 rename 為 `*.dev_disabled_*`（避免與 Linux trade-core 撞單；還原見 README § Mac dev-only 模式）。任何 connect 真實 Bybit 的 test 拿不到 credentials → fail-closed。Mock-based unit test 不受影響。**Reproduce release 基準**（engine lib 1827 / 0 failed 等）現可 `ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"` 直驗，不需要離開 Mac session。
3. **Sub-agent (E1) 寫碼若 refuse** — Linux 端 2026-04-19「第 3 次驗證解除」refuse pattern，但跨平台/跨 session 仍偶發。Workaround：主 session 直接寫。
4. **Mac↔Linux SSH bridge workflow（2026-04-21 採納，取代原「同步單向」）** — 詳 memory `project_ssh_bridge_workflow.md`。核心：Mac CC 為 SSOT，透過 `ssh trade-core`（Tailscale + key auth，免密碼）遠端觸發 Linux runtime 任務（cargo test / psql / restart_all / git 操作 / engine log）。
   - ✅ **Mac 本地 git 放寬**：允許 `git fetch` + `git pull --ff-only`（純 fast-forward，衝突時 abort 不破壞 state）；**仍禁** `git merge <branch>` / `rebase` / `reset --hard` / `checkout <branch>`
   - ✅ **SSH 允許**：ssh trade-core 跑 cargo/psql/git pull&push/restart_all/tail log/watchdog/rm tmp sentinel
   - 🚫 **SSH 需 operator per-case 授權**：觸及 live API/authorization.json/secrets、刪 remote branch（本 session 已試 trigger guardrail 成功擋住）、刪 worktree、DROP/TRUNCATE table 資料、改 risk_config TOML
   - **工作流**：Mac 寫碼 → `git add/commit/push` → `ssh trade-core "git pull --ff-only && cargo test --release"` → 看結果 → 綠就完成，紅就回頭 fix。**不再派 Linux CC 做寫 prompt 的 round-trip**（除非需要 interactive rebase/amend 等 Mac CC 禁做的動作）。
   - **Linux CC 剩餘職能**：24h 守夜監控、interactive git 操作、operator 急令 hotfix、Mac CC 離線時兜底。

---

## 八、工作流編排、16 Agent 角色與自我改進循環

### ★ 工作流編排 6 條 + 3 底線（2026-04-22 operator 指令融合）

1. **規劃優先 Plan-First**：非平凡任務（≥3 步 / 涉架構決策）先進規劃模式再動手；前期寫詳細 spec 減歧義；過程遇阻即停重規劃，**禁強推**；驗證階段同樣套規劃節點。Auto mode 下放寬「開工前 operator confirm」，但規劃思考仍要做。
2. **Sub-agent 卸載**：研究/探索/並行分析一律派 sub-agent 保主上下文整潔；一 agent 一任務精準執行；複雜問題投更多算力。詳 memory `feedback_subagent_first.md`。
3. **自我改進循環**：operator 任何糾正 → 抽模式寫 `docs/lessons.md`（場景 / 錯誤模式 / 預防規則 / 相關檔案）；會話起手掃近期相關條目；對錯誤率無情迭代。lessons.md = 可 grep 技術/流程錯誤庫，與 auto-memory `feedback_*.md`（跨 session 偏好）互補不重複。
4. **完成前驗證 Verify-Before-Done**：永不先標 done；跑測試 / 查 log / 對比 main 分支行為差 / 自問「senior engineer + FA 會 approve 嗎？」。強化既有 E2/E4 + memory `feedback_working_principles.md` 原則 3 對抗性驗證。
5. **追求優雅（平衡）**：非平凡修改前停問「有更優雅方式嗎？」；修復像 patch 就重做「基於現在所知一切實作優雅解」；**簡單/明顯修復跳過本條禁過度設計**。
6. **自主 bug 修復**：收到 bug 直接修；指 log/錯誤/失敗測試再解；CI 紅直接修不等手把手；operator 零上下文切換。詳 memory `feedback_minimal_confirmation.md`。

**3 條核心底線**：**簡單優先**（只動必要代碼，禁無關重構） · **不偷懶**（找 root cause，禁臨時 patch，senior/FA 標準） · **最小影響**（變更只觸必要部分，禁引 bug）。

**會話任務管理 6 步**（與 §六 TODO.md 強制規則同體，流程化版）：1) TODO.md 先寫 checkbox 計畫 → 2) 開工前 operator confirm（auto mode 跳過）→ 3) 逐步勾選進度 → 4) 每步高階摘要 → 5) TODO.md 結尾補 Review 章節 → 6) 任何糾正後寫入 `docs/lessons.md`。

### 18 Agent 角色體系與強制工作鏈（2026-04-25 真實接線）

**真實接線**：18 個 subagent definition 在 `.claude/agents/<NAME>.md`（git tracked，雙端 git 同步）。每個 agent 含 Anthropic 官方 frontmatter（`tools` / `disallowedTools` / `skills` 預載 / `color` / `model: inherit`）+ 啟動序列（讀 `docs/CCAgentWorkSpace/<NAME>/{profile,memory}.md` + 最新 report）+ 完成序列（追加 memory + 存 `workspace/reports/`）。CCAgentWorkSpace 仍是 SSOT，`.claude/agents/<NAME>.md` 是路由器；完整角色定義見各 `profile.md`，激活矩陣見 `docs/CLAUDE_REFERENCE.md`。

**主會話 = PM + Conductor**（合一，**非** subagent）。Anthropic 限制：subagent 不能 spawn 另一 subagent — 派發鏈必須由主會話編排。

**18 Agent 速查**（typeahead `@<NAME>` 直呼）：

| Tier | Agents |
|---|---|
| 管理層 | `@PM` `@FA` `@PA` |
| 質量保證層 | `@CC` `@E2` `@E3` `@E4` `@E5` |
| 執行層 | `@E1` `@E1a` |
| 專項審查層 | `@A3` `@R4` `@TW` |
| 分析顧問層 | `@AI-E` `@QA` `@QC` `@BB` `@MIT` |

**Invocation 三種 pattern**（Anthropic 官方）：
1. **Natural language 自動 delegate**：「讓 QC 看一下這個策略」→ Claude 主動 delegate（基於 description "Use proactively for..." 匹配）
2. **`@-mention` 強制**：`@QC` → 100% trigger 該 agent，不交 Claude 判斷
3. **Session-wide**：`claude --agent QC` → 整個 session 走該 agent system prompt + tool 限制

**何時用哪個**：
- **強制工作鏈**（不可跳過）→ **@-mention**：`@E1` 完 → `@E2` → `@E4` → `@QA` → PM Sign-off
- **多角色 adversarial review**（重大決策） → **@-mention 並行**：`@QC` + `@FA` + `@CC` + `@PM`（memory `feedback_multi_role_strategic_review`）
- **Routine 探索 / 分析** → **natural language**：「研究 ML pipeline 狀態」→ Claude 自動派 `@MIT`
- **長時間單角色任務** → **`--agent`**：例如整個 session 跑 QC audit

**標準工作鏈**（強制，memory `feedback_workflow_audit_chain`）：
`PM` + `@FA` 規格 → `@PA` 派發 → `@E1` / `@E1a` 並行 → **`@E2` 代碼審查 → `@E4` 測試回歸**（兩者絕不可跳）→ `@E5` 優化（每 Phase / Wave / ≥3 E1 任務強制）→ `@QA` → PM 確認。`@E3` / `@CC` / `@A3` / `@R4` / `@TW` / `@BB` 按需插入。`@AI-E` 季度跑。`@QC` 新策略提案 / 數學審計必活。`@MIT` ML pipeline / DB schema 審計必活。
**P0 快速通道**：`@PA` → `@E1`（≤5 並行）→ `@E2` → `@E4` → PM。可省 FA / E5 / E3 / CC，但 E2 + E4 永不跳。

**動態 isolation 派工準則**（PM 編排時 per-invocation 決定，避免 branch 過多）：
- 單實例 sub-agent 操作單檔 → **NOT** isolation（主 work tree）
- 並行 ≥2 sub-agent 操作不重疊檔 → **NOT** isolation
- 並行 ≥2 sub-agent 操作可能重疊檔 → 對重疊組加 `isolation: worktree` per-invocation
- destructive 動作（git reset / 大量 rm / 跨檔重構）→ 加 isolation（即使單實例）
- 純審查類（CC/QC/A3/R4/TW/E2 讀/E3/AI-E/PM/FA/PA/BB/MIT）→ **永不需要** isolation

**Skill 預載 vs 按需 Read**：
- **OpenClaw 24 個 custom skill** 在 `.claude/skills/<name>/SKILL.md`（git tracked）— agent frontmatter `skills:` 預載相關子集（自動注入 system prompt）
- **K-Dense-AI 134 個 scientific skill** 在 `~/.claude/skills/k-dense-ai/scientific-skills/<name>/`（user-level，Mac + Linux 各自 clone 一次）— agent body 寫路徑供按需 Read（**非** always-on，避免 trigger 噪音）

**雙端部署**（memory `project_18_agent_runtime_wired`）：
- Master：`srv/.claude/{skills,agents}/`（git tracked，`.gitignore` 對 `.claude/*` ignore 但 `!.claude/skills/`、`!.claude/agents/` 例外；`settings.local.json` + `worktrees/` 仍 ignore）
- Mac CC cwd `/Users/ncyu/Projects/TradeBot`：symlink `.claude/{skills,agents}` → `../srv/.claude/...`
- Linux CC cwd `~/BybitOpenClaw/srv/`：直讀 srv/.claude/
- 同步：Mac edit → `cd srv && git add + commit + push` → Linux `git pull --ff-only`
- 新 session 起手 / 修改 agent definition 後：`/agents` 重 load 或 restart CC

**Bybit API 強制**：所有 Bybit 相關開發（REST/WS/IPC）先查字典手冊 `docs/references/2026-04-04--bybit_api_reference.md`，新增端點同步更新手冊，`@E2` 必查；`@BB` 從 Bybit 立場 push back 違規設計。審計：`docs/audits/2026-04-04--bybit_api_infra_audit.md`。

---

## 九、代碼結構約定

### 文件大小限制
- **800 行** ⚠️ 警告線（E2 必須標記）
- **1200 行** 🛑 硬上限（不允許 merge）

**Pre-existing baseline exception clause（2026-04-28 governance addition per Wave E E2 retroactive review MED-1）**：當檔案在某個 wave 開工前的 baseline 已超過 1200 行（pre-existing violation 來自更早歷史），允許下列例外處理：
- **(1) 接受 wave 後 LOC ≤ pre-existing baseline + 5 LOC**（wave 不擴大違規幅度，且純 cleanup wave 應顯著減少 LOC）
- **(2) 同時開新 P2 ticket** 處理 pre-existing violation（如 `<FILE>-PRE-EXISTING-CLEANUP P2`），標明「ETA next maintenance wave」
- **(3) PM Sign-off 必明文記錄** governance exception accept 理由（避免 silent drift）

此例外 **僅適用 pre-existing 1200 + violation**，不適用「新 wave 把 ≤1200 推到 >1200」的場景（後者必拒）。E2 retroactive review 時引此條款判斷 governance accept vs RETURN to E1。範例：Wave E `2f88c40` main.rs 1208(pre-existing) → 1230(Wave 1 deepens) → 1210(Wave E split shrinks Wave 1 contribution +22→+2)，PM accept 1210 短期 + 開 MAIN-RS-PRE-EXISTING-CLEANUP P2 → Wave G `54e468a` 完成清零至 1158（解 baseline + 留 +42 headroom）。

### 模塊依賴方向（禁止循環 import）
```
state_models ← state_compiler ← state_store ← main_legacy ← main.py
其他 route 文件 ← main_legacy（通過 from . import main_legacy as base）
```

### Monkey-patch 安全
被 main.py patch 的函數（compile_state / STORE / envelope_response 等），新模塊必須通過 `main_legacy` 命名空間間接引用，不可直接 import 原始版本。

### Singleton 管理
| Singleton | 創建位置 | 導入方式 |
|-----------|---------|---------|
| `settings` | main_legacy.py | `base.settings` |
| `STORE` | main_legacy.py（main.py 重建） | `base.STORE` |
| `app` | main_legacy.py | `base.app` |
| `limiter` | main_legacy.py | `base.limiter` |
| `_pool` | db_pool.py | `from .db_pool import get_conn` |
| `DEFAULT_LEASE_TTL_CONFIG` | lease_ttl_config.py | `from .lease_ttl_config import DEFAULT_LEASE_TTL_CONFIG` |
| `_backtest_engine` | backtest_routes.py | 內部懶加載 `_get_backtest_engine()` |
| `_scheduler` | evolution_auto_scheduler.py | 內部懶加載 `start_scheduler()` |
| `_evolution_engine` | evolution_routes.py | 內部懶加載 `get_evolution_engine()` |
| `_ledger` | experiment_routes.py | 內部懶加載 `get_experiment_ledger()` |
| `LeaseTTLConfigManager._instance` | lease_ttl_config.py | `LeaseTTLConfigManager.get_instance()` |
| `_BYBIT_CLIENT` / `_BYBIT_CLIENT_AVAILABLE` | strategy_ai_routes.py | 內部懶加載 `_get_rust_client()`（PYO3-ELIMINATE-1 Phase 2 後指向 `app.bybit_rest_client.BybitClient` 純 httpx；函數名為 grep-stability 保留） |
| `KLINE_MANAGER` / `INDICATOR_ENGINE` / `SIGNAL_ENGINE` / `ORCHESTRATOR` 等 12+ | strategy_wiring.py | 模組級全局，import 時初始化 |
| `SCOUT_AGENT` | strategy_wiring.py:143（建構＋start）；scout_routes.py:61（mutable handle，由 `set_scout_agent()` 寫入） | 模組級全局，import 時初始化；外部直接 `from .strategy_wiring import SCOUT_AGENT` 或經 scout_routes 模組屬性。G3-08-FUP-MAF-SPLIT-CLEANUP P3 補登（pre-existing gap，2026-04-28；class 定義於 `scout_agent.py`，maf 經 PEP 562 `__getattr__` lazy re-export 維持向後相容） |
| `_SHARED_IPC_SLOTS` / `_SHARED_SLOT_LOCK` | ipc_dispatch.py | 內部懶加載 `get_or_connect_shared_client(slot_key)`（E5-P1-5） |
| `_<AGENT>_AUDIT_CB` / `_GOV_HUB_FOR_<AGENT>` × 5（Scout/Strategist/Guardian/Analyst/Executor） | strategy_wiring.py | 模組級，由 `agent_audit_bridge.make_agent_audit_callback(...)` 構造；各 agent ctor 注入 `audit_callback`（E5-FN-3 Analyst pilot + FN-3-FUP-a~d 4 agents 補接線）。ImportError 時 GOV_HUB=None → bridge fail-open 靜默丟事件。`agent_audit_bridge` 本身無狀態工廠（不持 singleton） |
| `_scheduler` / `_scheduler_lock` | edge_estimator_scheduler.py | 內部懶加載 `start_scheduler()`（P1-7 B JS estimator，每小時 cycle）。QC-3 audit FUP 補登（2026-04-23） |
| `_LEADER_LOCK_FD` / `_LEADER_LOCK_PATH` | edge_estimator_scheduler.py | 模組級全局；`_acquire_leader_lock()` 取得 flock fd 後寫入，OS 進程退出自動釋放（含 SIGKILL）。uvicorn --workers 4 leader election sentinel。測試用 `_reset_for_tests()` 釋放。EDGE-SCHEDULER-LEADER-1（2026-04-23 `f32629c`）|
| `_CACHE_INSTANCE` / `_CACHE_LOCK` | executor_config_cache.py | 內部懶加載 `get_executor_config_cache()`；G3-03 Phase B（2026-04-25）。process-global ``ExecutorConfigCache`` 持 Rust ``RiskConfig.executor`` 子切片快照（背景 daemon thread 每 N 秒 IPC poll，預設 10s 由 `OPENCLAW_EXECUTOR_CACHE_POLL_SEC` 覆寫）；首次 IPC 成功前 fail-closed 預設 `shadow_mode=True`，IPC 暫時失敗保留前一個好 snapshot。`shadow_mode_provider()` lambda 注入 ``ExecutorAgent`` ctor 取代原 `_shadow_mode = True` 硬編碼（CLAUDE.md §二 原則 #3 fix）。`strategy_wiring.py:467` 區段 init + `start_polling()`。測試用 `_reset_for_tests()` 釋放 |
| `_H_STATE_INVALIDATOR` / `_LOCK` | h_state_invalidator.py | 內部懶加載 `init_h_state_invalidator()`；G3-08 Phase 1C（2026-04-26）條件 spawn — 嚴格 `OPENCLAW_H_STATE_GATEWAY=="1"` 才建構 singleton，否則 `invalidate_async()` no-op 零負擔。Process-global ``HStateInvalidator`` 是 Python→Rust 失效提示通道（資料流與 G3-03 ExecutorConfigCache 相反）：每次 H1-H5 / 5-Agent 狀態變化由 fire-and-forget daemon thread + 私有 ``EngineIPCClient`` + ``asyncio.new_event_loop()`` 推送 ``invalidate_h_state`` JSON-RPC notification，提早 Rust ``h_state_cache`` poller 的 ad-hoc poll；Rust 端 10s 排程 poll 永遠仍會發生，漏一次提示最多多 ≤10s 過時、不破壞正確性。所有 IPC 例外於內部三層 try/except 吞掉（CLAUDE.md §二 原則 #6 fail-closed）。Wire site：`strategy_wiring_h_state.py`（STRATEGY-WIRING-SPLIT P2，2026-04-28；前為 `strategy_wiring.py:535`），`strategy_wiring.py` re-import 保 `app.strategy_wiring._H_STATE_INVALIDATOR` 屬性 grep 穩定。測試用 `_reset_for_tests()` 釋放 |
| `MARKET_SCANNER` / `AUTO_DEPLOYER` / `_SCOUT_WORKER` | strategy_wiring_scanner.py | `wire_market_scanner_and_workers(...)` 函數呼叫返回 `ScannerWiringResult`；`strategy_wiring.py` 在原 init 順序位置呼叫並 bind 回 module attribute（保 `app.strategy_wiring.MARKET_SCANNER` / `AUTO_DEPLOYER` 屬性 — 下游 `strategy_read_routes` / `strategy_write_routes` `from .strategy_wiring import MARKET_SCANNER, AUTO_DEPLOYER` 不破，`h_state_collectors` `getattr(_sw, ...)` 不破）。MarketScanner = 5-min linear+spot 機會掃描；StrategyAutoDeployer = max_symbols=30 / risk 3% / pinned BTCUSDT,ETHUSDT / spot reserved 5；ScoutWorker = 30-min 情報注入 ScoutAgent → MessageBus → Strategist。3 子塊 fail-open（任何一個 except → 該 singleton=None，主管線繼續）。STRATEGY-WIRING-SPLIT P2（2026-04-28）抽出 |
| `HStateCacheSlot` | rust/openclaw_engine/src/ipc_server/slots.rs | Rust 端 `Arc<RwLock<Option<Arc<HStateCache>>>>` late-injected slot pattern（G3-08 Phase 1A，commit `aa287c4`）。env=0 時 `main_boot_tasks::spawn_h_state_poller_if_enabled()` 跳過 spawn → slot 維持 `None` → `query_h_state` hot-path lookup 回 `None`、`get_h_state_status` 回 uninitialized；env=1 時建構 `Arc<HStateCache>` + spawn tokio daemon 每 10s pull `query_h_state_full` Python IPC + 收 `invalidate_h_state` 提示觸發 ad-hoc poll，DashMap shard lookup ≤1ms p99 達 hot-path SLA。Python crash → Rust 沿用 last good snapshot 並在 `staleness_ms > 30s` 時標 stale flag（fail-soft，CLAUDE.md §二 原則 #5/#9）。Schema 演化 forward-compat：`AgentState.stats: HashMap<String, i64>` + `#[serde(default)]` 吸收新欄位免 lock-step deploy |
| `CostEdgeAdvisorDbSlot` | rust/openclaw_engine/src/cost_edge_advisor_boot.rs | Rust 端 `Arc<tokio::sync::RwLock<Option<Arc<DbPool>>>>` late-injected slot pattern（G3-09 Phase B，2026-04-28；2026-04-28 Wave E split 從 main_boot_tasks.rs 移出至 cost_edge_advisor_boot.rs sibling per E2 PB1 LOC review）。鏡 `HStateCacheSlot` 設計：DB pool 啟動時延後注入 cost_edge_advisor daemon，30s populate-timeout；slot=None 時 daemon fallback 到 in-memory counter（不寫 `learning.cost_edge_advisor_log`），slot 注入後改走 DB INSERT 路徑。Engine restart 自動清空（`Arc` 隨 process 結束 drop）。Phase A advisor.evaluate() 不依賴此 slot — 純為 Phase B INSERT path 加 forward-compat（Phase A 評估邏輯仍跑於 in-memory，slot 注入後純加 persist 副作用）。HMAC secret 與 main loop 解耦，符合 CLAUDE.md §二 原則 #6（失敗默認收縮）+ 原則 #8（可審計） |

新增 singleton 必須在此表登記。禁止子模塊創建未登記的全局可變狀態。

### 其他
- Route Handler 只做 parse → call → format，不含業務邏輯
- 新 Pydantic model 放 `*_models.py` 或所屬模塊，不加入 main_legacy.py

---

## 十、下一步工作指針

**當前焦點**：活躍任務與週次排期以 `TODO.md` 為準（P0/P1/P2/P3/P4 分層）。CLAUDE.md 不重複列週。

**關鍵路徑（2026-04-24 · 10-Agent audit 重構後）**：
`Wave 1 G1 scheduler 恢復 + event_consumer fn 拆 + G6 healthcheck → Wave 2 G3 AI 接線 + G5 refactor + G4 ML pipeline → Wave 3 EDGE-DIAG Phase 3 + Phase 1b exit_features + Phase 2 shadow → Wave 4 LG-2/3/4/5 + P0-3 Phase 5 edge 重評 → Live`
- **最早 Live 日期**（事件驅動，非 hard date）：樂觀 ~2026-05-23 / 中位 ~2026-05-30 / 悲觀 ~2026-06-15
- **3 大 Verified 發現觸發點**：(1) edge_estimator_scheduler 4 天停滯 → G1-01 立即恢復 (2) PostOnly 配置反向 → G1-05 立即修 (3) ExecutorAgent hardcoded shadow → G3-02 Wave 2 重構
- 詳見 `TODO.md` Wave 1-4 + `docs/audits/2026-04-24--todo_refactor_audit.md`

**路線圖**：Phase 0-5 ✅ · Live GUI ✅ · Phase 6 ✅ · **AI 治理層 (W22-W23) 🟡 部分 live**（**2026-04-23 audit 更正**：H1-H5 AI middleware 與 5-Agent 代碼**並非 stub** — `h1_thought_gate.py` 185 行 / `model_router.py` 292 行 / `h4_validator.py` 103 行 / `layer2_{engine,routes,tools,cost_tracker,types}.py` 全實作。5-Agent 總計 ~4552 行（strategist 1170 / guardian 587 / analyst 834 / executor 630 / scout 194 / multi_agent_framework 1137）+ 完整 batch7/8/9/11 + audit_wiring 測試套件。runtime 狀態：StrategistAgent `shadow=False`（Sprint 5a live，`strategy_wiring.py:243`）、GuardianAgent / AnalystAgent 已 subscribe MessageBus、**ExecutorAgent `_shadow_mode=True` 默認未覆蓋**（`executor_agent.py:482` + `strategy_wiring.py:467` `ExecutorConfig()`）→ 產出 shadow intent log 不發 SubmitOrder IPC 到 Rust（設計上避免 Path A/B 倉位衝突，`executor_agent.py:382` 註解）。Linux uvicorn PID 720867（4 workers，2026-04-23 19:36 start）+ `/api/v1/paper/shadow/decisions` 持續被 GUI 查詢。**真正 gap**（待 G-1 展開）：(a) ExecutorAgent shadow→live 切換流程 + Rust IPC `SubmitOrder` 接收 Python intent 的整合契約 (b) Layer 2 自主推理循環（新聞搜索 / 宏觀判斷 / 工具箱 / 推理鏈記錄，見 `memory/project_layer2_agent_design.md`）。先前敘述「H1-H5 AI agent 目前全 stub」過期）。

**Live 前置**：~~G-3 / G-5 / Phase 6~~ ✅ · ~~LIVE-GUARD-1 Rust fail-safe 補回~~ ✅（2026-04-16 深夜，三重 Mainnet 硬鎖，見 §三/§四） · ~~LIVE-GATE-BINDING-1 Python↔Rust 簽名授權綁定~~ ✅（2026-04-18，HMAC `authorization.json` + 5 min re-verify，見 §四 Gate #5） · ~~P0-9 STABILITY-1~~ ✅（停電基礎設施事件 RCA 完成，非 code bug，不重置 21d 時鐘） · demo ≥21d 穩定（P0-2，時鐘從 **2026-04-16 22:16 local** 起算 = P0-9 STABILITY-1 RCA 穩定點；PID 已多次輪替，當前 engine PID `3954769` 於 **2026-04-21 20:44 CEST** `restart_all.sh --rebuild` restart 起（commit `f128af5` baseline，累積 TRACK-P-T4-WIRING-1 + EDGE-P2-3 PostOnly + DECISION-OUTCOMES fix + 所有 split 系列 refactor 首次進 runtime），計劃性 rebuild/deploy 不重置時鐘，僅 crash/hang 才重置）· provider pricing 綁定（LG-3）· API key 填入 ≠ 即可上線（Rust 側 4 項可驗證硬鎖 + Python 側 2 項門控共 5 項，全綠才真實 live）。

**關鍵文件指針**（按需 Read，不要全載入）：
- Bybit API 字典/審計：`docs/references/2026-04-04--bybit_api_reference.md` · `docs/audits/2026-04-04--bybit_api_infra_audit.md`
- 完整參考索引：`docs/CLAUDE_REFERENCE.md`

---

## 十一、一句話狀態

> 截至 2026-04-29 18:16 CEST：**ML/Dream edge-unblock local implementation complete** — V031 data contract + advisory table、LinUCB post-fee reward loop、ML shadow advisor、DreamEngine/OpportunityTracker read-only producers、scheduler 接線與 healthcheck `[35]`/`[36]` 已落地。Demo 可先用 ML/LinUCB/DreamEngine/OpportunityTracker 做 read-only/shadow/counterfactual/demo A-B 來修 edge；正 edge 是 promotion gate 而非 training gate；Live 自動交易與 live 參數自動放權仍必須經 GovernanceHub + Decision Lease + 既有 5 live gates。Completion 見 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--ml_dream_edge_unblock_completion.md`。

> 截至 2026-04-29 17:36 CEST：**Strategy Edge Repair implementation 完成，Linux deploy pending** — 已修 demo/live_demo/live intent `signal_id` attribution chain、per-binding fee refresh 長期 stale root、scanner snapshot + edge route metadata、可調 `edge_routing`、maker unsafe fallback skip、grid robust-negative `blocked_symbols`、bb_breakout demo threshold 1.2；新增 healthcheck `[34] intent_signal_attribution`。驗證：Rust lib 2361/0、scanner 61/0、DB writer 3/0、fast_track_reduce 16/0、maker_price 10/0、`cargo check --bins`、`cargo check openclaw_core`、Python maker/attribution pytest 9/0、`git diff --check`。

> 截至 2026-04-29 12:38 CEST：**62-finding remediation Batch A-F 全部完成、push/sync、Linux rebuild/redeploy 已完成；fee-refresh RCA + maker-fill healthcheck follow-up 已部署，healthcheck WARN** — 主修復 `bc3fa70` + 文檔同步 `6539e4e` + restart ownership hotfix `5db4e29` + fee periodic re-seed `bdd3177` + maker/cron follow-up `030ef2d`/`0e9e257`/`f0d21b9`/`af9d552` 已進 Linux；engine PID **447123**，API PID **447192**；tracking ledger `docs/audit/remediation_tracking.md` 62/62 fixed；PM/operator sign-off 報告已落在 `docs/CCAgentWorkSpace/PM/workspace/reports/` 和 `docs/CCAgentWorkSpace/Operator/`。當前 gate：watchdog `engine_alive=true` + demo/live snapshots fresh，API 可用且 auth enforced；passive healthcheck WARN `[12]` + `[33]` + `[11]`，`[22]`/`[27]` cleared，`[32]` PASS；`[33]` G2-01 fee_drop 1.8% vs target ≥60%；cron self-check `[22]`-`[29]` PASS；live pipeline 因 authorization schema v1→v2 拒絕啟動，需 Operator renew。

> 截至 2026-04-28 12:30 CEST（採集時間，G6-04 §三 drift 規則）：**EDGE-DIAG-2 deploy + Wave H + 2 post-Wave-H operator hotfixes**（HEAD `85a4e2d` origin synced — 含 `cdc2699` fee-postonly-2 Rust fix + `20baabe` restart-all `--keep-auth` shell flag + `85a4e2d` CLAUDE.md drift fix）· engine PID **3626554**（binary mtime **2026-04-28 05:28**，**未含 `cdc2699` Rust fix**：strategy-open Fill `fee_rate` 仍寫 taker 0.00055 — DB column drift，下次 `--rebuild` 套用即可，actual `fee` 已正確；JS estimator 用 `fee_usd/notional` 不受影響，5 robust 負 cells 仍真實負）· uvicorn PID **3626645**（4 workers，05:28 reload）·，含 EDGE-DIAG-2 4 項落地 + 5 strategies 全 active 在引擎中：ma_crossover/bb_reversion/bb_breakout/grid_trading/funding_arb）· uvicorn PID **3626645**（4 workers，05:28 reload）· **Live_Ready ⚠️**（5 門控，Rust 可驗證 4，本 wave 0 觸碰 live 硬邊界 — `strategy_params_live.toml` / `cost_gate_live` / `missing_edge_fallback_bps` 全保）· **EDGE-DIAG-2 落地 4 項**：(a) `cost_gate_moderate` 對稱低樣本探索（n<30 → exploration mode；live 不動 + new test pinning live n=3 fail-closed） (b) JS estimator `min_observation_ts` cutoff `2026-04-22T21:00Z` post P0-13 ATR fix + V2 SWAP（env override `OPENCLAW_EDGE_MIN_OBSERVATION_TS`） (c) bb_breakout + funding_arb demo TOML active=true（live 仍 false） (d) 13 Rust + 17 Python 新測試（cargo lib **2308 / 0 failed**；pytest 17/17 PASS）。**Post-deploy 實測**：post-cutoff 58 cells (vs 70 pre-cutoff，~17% 排除符合預估 18%)，n_trades 分佈 `<5: 21 / 5-9: 13 / 10-29: 19 / >=30: 5`，**5 個 robust 負 cells 全 grid_trading**（AAVE/GALA/ENA/DOGE/FARTCOIN n=31~69，仍 block）；engine 啟動 1s 內 `cost_gate(JS-demo): low sample — exploration mode` log 已 fire 確認新路徑活著。**主路徑**（Wave 1 → Wave 4）：W1+W2+W3 派發層面全完 / EDGE-DIAG-2 deploy 完 / Wave H 收尾完 / next `--rebuild --keep-auth` 套用 fee-postonly-2 fix / EDGE-DIAG Phase 3 被動 ~04-30 / G2-02 counterfactual ~05-03 / G2-01 PostOnly ~05-07 / EDGE-P1b bind ~05-10 / P0-3 決策 ~05-15 / Live（最早 ~2026-05-23，中位 ~2026-05-30）。Follow-up 留尾：(i) ✅ `passive_wait_healthcheck` [31] `check_edge_diag_2_strategy_diversity` 已 wire（cron 改跑 31 check） (ii) PostOnly maker fill rate 還沒驗 (iii) ✅ `feedback_demo_loose_live_strict_policy.md` memory 已寫 (iv) ✅ fee-postonly-2 column drift 已修（`cdc2699`），下次 `--rebuild --keep-auth` 套用。詳 EDGE-DIAG-2 報告 `.claude_reports/20260428_053101_edge_diag_2_demo_loosen_live_strict.md` + `TODO.md` Wave 1-4。

> 前次狀態（pre-EDGE-DIAG-2 deploy）：截至 2026-04-27 01:30 CEST：**STRKUSDT P0 Wave merge 完成**（HEAD `1edc6fe`） · engine PID 2033577（pre-merge binary 2026-04-26 04:29，**待 2nd deploy 套用 6 PR 改動**）· uvicorn PID 2033662 · STRKUSDT P0 Wave 7 fix（F1 deploy `af48ee1` + F2-F7 6 PR）merge 順序 F2 → F6 → F3 → F4 → F7 → F5；6 merge commits `1dff948`/`5ac7a80`/`310ae29`/`31c8206`/`1341c01`/`1edc6fe`；E4 combined regression 2252 / 0 failed；cron 6h 27 check（[1-15]+[Xa]+[Xb]+[16]+[18]+[22-29]）；STRKUSDT dust spiral RCA 三層 root entry_notional=0 fail-open + Gate 2 cross-symbol price contamination + 41 phantom fill。詳 STRKUSDT P0 wave Sign-off `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-27--strkusdt_p0_wave_signoff.md`。

---

## 十二、外部整合工具映射（**Linear-only active** posture）

**核心原則**：**git `srv/` 是唯一 source of truth**。外部工具僅為 *view layer*、*artifact store*，永不擁有交易參數 / 代碼 / 政策的權威。任何衝突一律以 git 為準。

**Posture（2026-04-29 operator 簡化決定）**：**Linear 是唯一 active workflow tool**。其他工具不融入工作流（不寫 SOP gate、不要求每 Wave 更新）。

### 工具狀態表（2026-04-29 終版）

| 工具 | 狀態 | 用途 | 維護要求 |
|---|---|---|---|
| `srv/` git | **Source of truth** | 代碼 / CLAUDE.md / TODO.md / memory / docs | 每 commit 強制 |
| **Linear** | **🟢 ACTIVE** | 62-finding remediation tracker | Wave/Batch Sign-off 後主會話更新對應父 issue |
| **Notion** | **❄️ FROZEN**（保留但不維護） | 2026-04-29 bootstrap 快照（5 pages） | **不要更新** — operator 決定不融入工作流 |
| **Google Drive** | **🟡 PASSIVE** | 按需 binary artifact（PDF / screenshot） | 0 SOP；只在 operator 明確要求才用 |
| **Coupler.io** | **❌ DECLINED** | — | 不啟用 dataflow；連接器 slot 留著零成本 |
| **MotherDuck** | **❌ DECLINED** | — | 同上（已移除 connector） |
| **Slack** | **❌ DECLINED**（may revisit pre-live ~2026-05-15） | — | 不 authenticate；live 前 2 週評估純 alert channel |

### Bootstrap 入口

- **Linear**：team `NCYu` · project [`OpenClaw 62-Finding Remediation`](https://linear.app/ncyu/project/openclaw-62-finding-remediation-de1bc8f68e42) · 6 milestones (Batch A-F) · 7 labels (P1/P2/P3/live-release-blocker/backlog/time-driven/edge-diag) · 12 issues (`NCY-5..16`)
- **Notion (frozen)**：[OpenClaw — Operator Hub](https://www.notion.so/350dcd3b1eff81038de2d10874ae0fe4) — 5 pages 為 2026-04-29 快照，內容保留但**不再同步**；任何看到的條目需以 git 為準

### SOP（簡化版）

#### PM（主會話 / Conductor）
1. Wave / Batch Sign-off git commit landed 之後：
   - 更新對應 Linear 父 issue（description checklist + status flip）
   - **Notion 不更新**（凍結快照）
2. 新 finding：判斷是否屬 mainline（62-finding / time-driven / 重要 backlog），是則建 Linear issue；否則只進 TODO.md
3. **不要**把 TODO.md 全鏡像 Linear；只篩 mainline / time-driven cutoff items

#### PA / 審計 agents
1. RFC / audit 寫入 `docs/CCAgentWorkSpace/.../reports/` 或 `docs/audits/` / `.claude_reports/`
2. **不要**寫 Notion（凍結）；**不要**直接寫 Linear（PM 提案）
3. 若產生新 finding 上 mainline，向 PM 提案 Linear issue

### 嚴禁事項

- **Don't** 把 Linear / Notion 當有否決權；它們鏡像，git 決策
- **Don't** 自動同步 TODO.md → Linear；策展鏡像 only
- **Don't** 在任何外部工具發布 secrets / API keys / authorization tokens
- **Don't** 啟用 Coupler.io dataflow（已 declined；本機 DuckDB / psql 替代）
- **Don't** authenticate Slack（已 declined to live -2w）
- **Don't** 未經 operator 授權發布 runtime engine state（PID / snapshot freshness / fill rates）到任何外部工具

### 與 §六.六 SSH bridge 工作流關係

Mac CC = SSOT，可寫 Linear / git；Linux runtime 透過 `ssh trade-core` 觸發；Linear 寫入從 Mac 主會話發起。**Multi-session race 守則**（`feedback_git_commit_only_for_metadoc.md`）對 CLAUDE.md / TODO.md / memory 仍適用：用 `git commit --only <file>`。

### 重新評估觸發點

只有以下情況才考慮重啟已 declined 的工具，不要主動評估：
- **Coupler.io**：本機 DuckDB / psql 真的不可行
- **Slack**：approaching live trading（~2026-05-15）需 mobile alert channel
- **MotherDuck**：見 `memory/reference_external_tools.md` §Declined
- **Notion**：operator 主動要求重新融入（單方面解凍）
