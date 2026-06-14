# 全盤冷酷審計 — Stage 3 PA Validated Fix Plan

**AUDIT_DATE**: 2026-06-14 ｜ **凍結 SHA**: `976d420e`（三端同步 main，0/0）
**輸入**: Stage 2（10 軸 openclaw-full-audit，`wf_3822153a`）+ Stage 2.5 補完（E4/TW + 8 dirty 檔 + 7 seam re-probe，`wf_2d7c6513`）
**模式**: report-only（fix=false）— **未經 operator 批准前嚴禁動手**
**對抗強度**: 雙向（假陽性 refute + negative-space 盲區 + seam critic）；高危類加可達性第三視角；verify/fix 按原始 finding 粒度不壓縮

> Stage 0 baseline: [2026-06-14--cold_audit_baseline.md](../../PM/workspace/reports/2026-06-14--cold_audit_baseline.md)
> 各軸全文證據: 見 §6 report_paths

---

## 0. 執行摘要（裁決骨架）

- **總量**: 兩輪共 103 finding（80 + 23）；對抗複核後 **confirmed 10、latent 5、seam 升格 5（4 LOW + 1 HIGH 已併入 confirmed）、disputed/refuted 多項**。
- **無 P0/CRITICAL 可達缺陷**。Live 執行邊界（5-gate + 雙 boot panic）經 CC/BB 實證 fail-closed（正面確認）。
- **最重要單點 = P1-AUTH-1**：live RiskConfig 可在「弱於 live 執行」的閘下被改（operator+scope 即可，無需 5-gate / 簽署授權 / OPENCLAW_ALLOW_MAINNET）。**需 operator 先裁 intent，再修。**
- **盈利線交集**：QC cost_gate 雙重扣成本（confirmed, reachable）獨立佐證 2026-06-13 profit-diagnosis「cost_gate 拒 99.97%」——異質 corroboration 成立。
- **dirty 8 檔（closed_pnl 分頁 + m4 fills）**：讀模型 CLEAN（cursor fail-closed / bound params / 無注入 / 無 fake-success / engine_mode 不變量守住）、測試真咬非空轉、0 回歸（4738/66 ×3）；但有 **3 個 fix-before-commit 缺口**（fail-closed 分支無測 / m4 fee JOIN fan-out / docstring 中文化）。

---

## 1. 異質 corroboration 與去重判定（PA 機械聚簇能力邊界外的語義收口）

機械聚簇結果：first-run 7 簇全單軸（multi_axis=0），ungrouped=0。**跨檔/跨輪同源**由 PA 在此收口：

| 簇 | 成員（保留原始粒度） | corroboration 性質 |
|---|---|---|
| **cost-edge 治理** | QC cost_gate 雙重扣成本(HIGH) + FA Root#13 `cost_edge_max_ratio=100.0` 關閘(LOW) + AI-E `cost_edge_ratio` 三處三義(MED) + AI-E cost_edge_advisor 永久 B_shadow(MED) | **異質**（QC 數學/FA 治理/AI-E 實作三路獨立）→ 同一「成本-edge 閘語義未統一且實質失效」家族。fix 須協調，勿單點改 |
| **funding 策略治理漂移** | QC funding dead-knob(HIGH) + CC funding_arb `#[deprecated]`/fail-closed guard 不存在(MED) + FA funding_arb AMD guard 不存在(MED) | **異質**（QC edge 數學 / CC+FA doc-vs-code）→ funding 策略「文檔宣稱 vs 代碼實態」漂移家族 |
| **m4 fills fee JOIN** | E4 fan-out(latent HIGH) + DIRTY fan-out PG-empirical(MED) + E4 fee 符號/方向無數值測(MED) + DIRTY schema test 僅 string-match(LOW) + DIRTY docstring 自相矛盾(LOW) | **同源異 facet**（同一 `FILLS_QUERY_SQL`）→ 單一 fix 包 |
| **profit-diagnosis 交集** | QC cost_gate(本輪) + 2026-06-13 profit-diagnosis「cost_gate 拒 99.97% 全真負 0 誤殺」 | **跨輪異質 corroboration**：本輪純 source 數學讀出雙重扣成本，前輪 runtime 統計拒單率——兩路獨立指向同一閘 |

> 去重鐵律遵守：以上僅呈現層歸併供 fix 排程；**verify/fix 仍按原始 finding 粒度**，未縮減任一對抗暴露面、未掩蓋同位置第二缺陷。

---

## 2. CONFIRMED — 分級修復隊列（P0-P3）

### P0 / CRITICAL — 無
Live 執行 5-gate + 雙 boot panic 經實證 fail-closed（CC INFO 正面確認，記為現役防線）。

### P1 / HIGH

#### P1-AUTH-1 — live RiskConfig 可繞 5-gate 被改（authority 不對稱）🔴 最高優先
- **anchor**: `handle_patch_config` (rust/openclaw_engine/src/ipc_server/handlers_config.rs:77-199); dispatch arm `patch_risk_config` (ipc_server/dispatch.rs:420-436); Python `update_per_engine_global_config` (risk_routes.py:688-733) vs live 5-gate `post_live_session_start` (live_session_endpoints.py:163-188)
- **classification**: FACT（CC seam #5，verdict=partial，**reachable**，雙質疑者 0 refute）
- **缺陷**: `patch_risk_config engine=live` 只需 operator role + `risk:write` scope，**無** `all_five_live_gates_ok` / `live_reserved` / `OPENCLAW_ALLOW_MAINNET` / 簽署 authorization.json。對比：live **訂單**路徑強制全 5 gate。→ 持 `OPENCLAW_IPC_SECRET` 且具 operator 角色者可在 live 下單前放寬 live 風控（拉高 max_leverage、放寬 exposure cap、降 stop_loss/daily-loss、翻 take_profit_enforced）。
- **緩解事實（為何非 CRITICAL）**: 需 operator role + scope；寫 V014 audit row（守 #8）；AI/Teacher sink 硬釘 `target_engine="demo"`（AI 不能自走 live，守 #3/#7）；live pipeline 仍須另經 5-gate 才真正依放寬後的限額行動。
- **違反**: Root #4（mutation 不可繞風控授權）、#5（survival>profit）、Hard Boundary「LiveDemo/Live 不弱化授權/TTL/風險/審計」。
- **fix（待 operator 裁 intent 後）**: `update_per_engine_global_config` 當 `engine=="live"` 時加 `all_five_live_gates_ok(actor, require_authz=True)`（與 `post_live_session_start` 對齊）；defense-in-depth 在 `handle_patch_config` 對 `config_name` 以 `risk/live` 開頭者加閘。**若 pre-auth 放寬 live config 是刻意設計 → 須在 Hard Boundary 明文記為例外。**
- **owner**: PM 裁 intent → E1(Rust+Python) → E2 → E3 複審 → E4。**operator decision 前置。**

#### P1-PROFIT-1 — cost_gate 雙重扣成本（壓制邊際正 cell）
- **anchor**: `cost_gate_safety_multiplier / threshold_bps / shrunk_bps` (rust/openclaw_engine/src/intent_processor/gates.rs:33-46,134-203,266-297)
- **classification**: INFERENCE→FACT（QC，**reachable**，0 refute；跨輪 corroboration profit-diagnosis）
- **缺陷**: 已是 net-of-fee 的 edge 又與 fee-derived threshold 比較 → 成本被算兩次，壓制 0<net<(fee/wr×1.3) 帶的邊際正 cell。
- **影響**: 直接壓盈利面（與「6 週無 edge」「cost_gate 拒 99.97%」線索同源）。
- **fix 前置（不可直接翻）**: **須 QC/MIT 先跑 replay** 對比 current gate vs `net>0` gate，統計落在誤拒帶的 cell 數與其真實 forward PnL（避免一翻就放閘進負期望單）。→ 量化後 PM 裁修法。
- **owner**: QC/MIT replay（read-only Linux edge_estimates）→ PA 定 fix → E1 → E2 → E4。

#### P1-SCHEMA-1 — sqlx 全 runtime-checked，無 schema-consumer contract test（column drift 隱形）
- **anchor**: 93 個 `sqlx::query()/query_as/query_scalar` runtime call sites（0 compile-time 巨集、無 .sqlx offline cache）；`tests/migrations_test.rs` 只查 `information_schema.tables` 從不查 `.columns`；CI = cargo check only（PG-dependent test 全 SKIP）
- **classification**: FACT（MIT seam #1，verdict=confirmed，**reachable**，0 refute）
- **缺陷**: 任一 V### rename/drop column 對 Rust 編譯期 + Python import 皆隱形，僅 runtime first-touch 才破；16 個 writer 吞 query error（warn/error only）→ column-drift INSERT 靜默不寫 row（重演 V023 silent-noop）。**M4 已實證 drift 發生**（E2 cold review 抓到 5 個 schema-incorrect column 滑過 compile+標準測試）。
- **fix**: (1) `helper_scripts/db/audit_migrations.py` 進 CI（ephemeral PG）+/或 cron healthcheck，並補 consumer-query→DB 反向檢；(2) 高價值寫路徑改 `sqlx::query!` 宏 + `cargo sqlx prepare` 產 .sqlx cache + CI `cargo sqlx prepare --check`；(3) 擴 M4 reverse grep-contract 到全熱表或加「跑真 migration 後執行代表性 consumer query」整合測試。
- **owner**: MIT 設計 → E1 → E2 → E4（CI 改動需 GitHub Actions cost policy 對齊：feedback_github_actions_cost）。

#### P1-PERF-1/2/3 — Rust/Python 熱路徑三項（clean perf wins）
- **P1-PERF-1** 1m+5m 全指標每 tick 無條件重算（`compute_indicators_for_timeframe`, tick_pipeline/on_tick/step_4_5_dispatch.rs:222）— E5 HIGH。fix=僅在 bar-close 重算（gate on closed-bar），**前置假設**=指標不依賴 intra-bar last_price（E5 自標需逐 16 指標確認 + replay bit-identical 對比 cache-on/off）。
- **P1-PERF-2** release profile 缺 LTO/codegen-units（rust/Cargo.toml:61）— E5 HIGH，最高 ROI 純 build flag。**前置**=E1 跑 `cargo bench --save-baseline` 量化（文獻 5-15%，本 repo 未實測），且 build time trade-off。
- **P1-PERF-3** async route 內同步阻塞 `urlopen` 凍 event loop（`get_ollama_status`, layer2_routes.py:531）— E5 HIGH。fix=改 async client 或 thread pool offload。
- **owner**: PA 批 scope → E1 → E2 → E4（PERF-1/2 須 bench 證量級，不憑文獻值 sign-off）。

### P2 / MEDIUM

| ID | finding | anchor | 備註 |
|---|---|---|---|
| P2-DIRTY-1 | closed_pnl fail-closed `learning_pnl` 分支無測試（mutation-bite 親證盲區） | closed_pnl_pagination.py `_fetch_pg_closed_pnl_fallback` | **dirty 工作 fix-before-commit**；E4 reachable |
| P2-DIRTY-2 | m4 fills fee 自連 LEFT JOIN row fan-out + silent gross-leakage（PG-empirical：30 close row 命中 29 dup group） | helper_scripts/m4/sources/fills_loader.py `FILLS_QUERY_SQL` | latent（fills 尚未餵 generate_stage1_candidates）但 **M4 接 live 前必修**；正確 net 聚合定義需 QC/MIT 裁 |
| P2-DIRTY-3 | closed_pnl 測試無 Bybit retCode 非零顯式覆蓋 + m4 fee 符號/方向僅 string 驗證 | test_bybit_closed_pnl_route.py / fills_loader.py | 測試盲區矩陣 |
| P2-FUND-1 | funding_short_v2+funding_harvest「annualized funding threshold」是 dead knob（binding gate=edge>0 ~135-160% APR） | funding_short_v2/mod.rs:165-181; funding_harvest/mod.rs:154-167; strategy_params_demo.toml:217 | + 併 funding_arb doc-vs-code 漂移（CC/FA MED） |
| P2-COST-1 | cost-edge 治理家族：`cost_edge_max_ratio=100.0` 關 Root#13 閘（stale TODO 無 review date）+ `cost_edge_ratio` 三處三義 + cost_edge_advisor 永久 B_shadow（41500 row 全 Disabled，CLAUDE 關倉鐵則永不觸發） | budget_config.toml:5-15; cost_edge_advisor.py/advisor.rs/tracker.rs; DOC-08 §5.2 | **異質 corroboration**，須統一語義後再決定是否復閘 |
| P2-AIE-1 | ai_pricing.yaml 雙副本不一致 + 漏現行型號（opus-4-8/sonnet-4-6）→ 真名呼叫被預算層 fail-closed 拒 | settings/ai_pricing.yaml; layer2_types.py:474-492; pricing.rs:75 | **可能擋 L2 真調用**，運維相關 |
| P2-AIE-2 | crontab `daily_cost_snapshot.sh` 指向不存在腳本，每日成本快照採集腿斷裂 | helper_scripts/maintenance_scripts/ (缺) | broken cron，需 operator 確認 crontab |
| P2-QC-1 | dynamic_risk_sizer 用 small-sample un-annualized「Sharpe」配 annualized 閾值且無顯著性 gate；Kelly point-estimate 無 shrinkage（min_trades=50 win_rate SE 大） | dynamic_risk_sizer.rs:236-309; kelly_sizer.rs:213-247 | sizing 嚴謹性 |
| P2-MIT-1 | model_registry freshness healthcheck 盲區：shadow-only 永遠回 PASS「expected」，stale shadow model 不可見 | checks_ipc_edge.py:437-508 | 監測誠實性 |
| P2-MIT-2 | alpha 主路全 0 row（listing/hypotheses/residual/FDR/LSR 軸全 inert） | research.* / learning.* runtime | 與 P0-EDGE-1 主線狀態一致，記錄 |
| P2-A3-1 | Legacy /gui Paper「提交」按鈕靜默 NO-OP 死按鈕（fake-success） | app-paper.js:60-79; index.html:227 | 雖 legacy，仍誤導 |
| P2-A3-2 | engine_alive 未在 System 第一屏顯示（藏折疊 Agents tab 且英文標籤）+ Earn tab 暴露未解釋工程術語 | tab-system.html; tab-earn.html:308-324 | operator 可用性 |
| P2-BB-1 | Bybit rate-limit 字典 §4.1 與官方 V5 doc 全面矛盾 + code 內部三方不一致（docstring 20/s vs default 10 vs 註解 10/s） | bybit_api_reference.md:1315-1333; bybit_rest_client.rs:229-299 | runtime 行為 header-authoritative 實際安全（BB 背書），屬 doc/常數債 |
| P2-R4-1 | README Control Console tab 表缺 earn 分頁 + 測試/端點數硬編碼大幅漂移且自相矛盾（3,700 vs 6,500） | README.md:24-42,77,130,137 | doc-runtime drift |
| P2-TW-1 | M4 helper 族 ≥13 檔缺 SCRIPT_INDEX 條目 + profit-diagnosis FINAL cross-ref 指向不存在 QC 報告 + closed_pnl 新模組 docstring 英文-only | SCRIPT_INDEX.md; 2026-06-13 FINAL; closed_pnl_pagination.py `_safe_float` | dirty 工作 docstring 中文化屬 fix-before-commit |

### P3 / LOW + INFO + seam 降級
- **seam 降級（已 verify，非 P0/P1）**：FA update_strategy_params provenance 碎片化（LOW，非硬 #8 違反，audit 落 learning.mlde_param_applications + strategist_applied_params 兩表，建議統一 feed）；CC IPC method registry vestigial（LOW，修 docstring 移除「can grow」成長暗示或補覆蓋測試）；BB shadow_decision_builder qty pre-round（LOW，paper-only，建議移除 client 預 round + 補 log）；E3 submit_paper_order（**refuted 無洞**，建議防呆 `engine!="live"` assertion 鎖死 latent）；QC strategy_name（**refuted 無洞**，find_strategy_mut fail-closed 已測，optional comment）。
- **doc/hygiene LOW**：MEMORY.md Project context 超配額（61 vs ≤40，R4 HIGH 但歸治理 hygiene）；SCRIPT_INDEX changelog 長行惡化；README rust module 計數 stale；MEMORY skill 計數 24→25；tab 時間僅本地時區無 UTC 雙標；Settings/Agents tab 殘留英文 placeholder / config-key 術語；audit_migrations.py:218 寫死 Mac 路徑（跨平台 regression carry-forward 2026-04-24）；spec-compliance skill 指向 archived stub COMPREHENSIVE_SPEC_REQUIREMENTS.md。
- **latent debt（記錄不修）**：AI-E DOC-08 $2/天硬上限 Rust tracker 無 daily 腿（只 monthly $100/$150）；MIT ML 決策層 quantile model 永不載入 live + model_registry frozen 7+ 週永停 shadow（**by-design shadow**，disputed→latent，非缺陷但成熟度誠實性需在 doc 標明）；FA regime_snapshots/transitions dead persistence（writer 在 0 producer）；FA Layer2 autonomous loop 無 production trigger（dormant-in-practice）；AI-E ai_invocations 不覆蓋 L1 Ollama IPC 流量；Rust ClaudeTeacher 硬編 stale model 名 `claude-sonnet-4-5`。

---

## 3. 正面確認（回歸守恆 — 記錄為現役防線，勿誤刪）
- **CC**: live_authorization.rs 5-gate + 雙 boot panic 全 fail-closed；前次 CC P1（ADR-0046 phantom revive-gate）+ G-01（$15 daily cap）VERIFIED FIXED。
- **BB**: HMAC（REST+WS）+ env/secret-slot 切換 + retCode fail-closed + WS demo topic 排除 + positionIdx one-way + withdraw permission 架構級零引用。
- **E4**: BASELINE 4738/66 deterministic ×3，0 回歸；dirty closed_pnl 測試真咬業務邏輯（temp-overlay + 雙向 mutation-bite 親證，非 mock 空轉）。
- **DIRTY**: closed_pnl 分頁讀模型 CLEAN（cursor fail-closed / bound params / 無注入 / 無 fake-success）；engine_mode 不變量守住（demo/live/m4 全 hardcode IN-list，無 caller-tunable paper 洩漏）；GUI drift label 純文字 XSS-safe。
- **A3**: prior A3-GUI-001~011 + 2026-04-24 Top-3 全修並守住；全 static 無 native confirm()/prompt()。
- **FA**: hard-boundary fingerprint scan + 跨平台硬編碼路徑掃 production = CLEAN（no BLOCKER）。

---

## 4. 待證假設 / re-probe（不入 TODO，留附錄供後續輪）
70 條 assumptions（55 first-run + 15 supp）核心未展開項：① 多軸無 Linux runtime 親探（CC/QC/E5 read-only 限制；engine PID/flag 實值/IPC secret present/edge_estimates 分布/pg_stat 慢查詢/tick burst tail 未取當日值）；② ~93-107 GUI write endpoint 未逐一打對抗 actor 矩陣（baseline 累積覆蓋，非全集重打）；③ Rust 全模塊 panic/unwrap fail-closed 未系統枚舉（DoS-via-panic 面需專輪 fuzz）；④ 9 安全不變量未逐條 1-by-1 重 grep（前次 2026-05-30 已驗 load-bearing，本輪無相關 diff）；⑤ DOC-01..08 逐 clause conformance 矩陣未產（僅 DOC-03/06 targeted）；⑥ tests/migrations vs sql/migrations 雙目錄是否 schema 分歧未逐檔 diff；⑦ model_registry 3 shadow 模型 feature leakage 6 維未逐項（模型既 frozen 不 live，零風險優先級低）；⑧ bybit_thought_gate 56 檔 9658 LOC 子系統僅查 wiring 未審內部 cost-governance 正確性（可單獨派一輪）。

---

## 5. owed — 需 operator 決策 / Linux read-only 證據
1. **P1-AUTH-1 intent 裁決**：live config pre-auth 放寬是否刻意？（決定「修閘」vs「Hard Boundary 明文例外」）
2. **P1-PROFIT-1 replay 量化**：批准 QC/MIT 跑 read-only replay 統計 cost_gate 誤拒帶（修前置）。
3. **P1-SCHEMA-1 CI 改動**：ephemeral PG service 進 CI（涉 GitHub Actions 分鐘成本，feedback_github_actions_cost）。
4. **P2-AIE-2 crontab 核對**：Linux `crontab -l` 確認 daily_cost_snapshot.sh 斷裂腿（read-only）。
5. **dirty 8 檔走完整鏈**：closed_pnl + m4 工作（含 fix-before-commit P2-DIRTY-1/2/3 + docstring 中文化）走 E1→E2→E4 後再 commit；目前未提交於 976d420e。
6. **runtime 親探補證**：多軸 latent/assumption 依賴的 Linux runtime 值（engine env flag / IPC secret present / edge_estimates 分布 / m4 fan-out 完整 before-after row 數）。

---

## 6. report_paths（各軸全文證據）
- CC: docs/CCAgentWorkSpace/CC/workspace/reports/2026-06-14--root_principle_compliance_audit.md
- E3: docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-14--E3--full_repo_cold_audit.md
- BB: docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-14--bybit_api_compat_audit.md
- QC: docs/CCAgentWorkSpace/QC/workspace/reports/2026-06-14--srv_quant_math_full_audit.md
- MIT: docs/CCAgentWorkSpace/MIT/memory.md（inline）
- AI-E: docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-06-14--AI-E--full_repo_cost_audit.md
- E5: docs/CCAgentWorkSpace/E5/workspace/reports/2026-06-14--full_repo_optimization_audit.md
- A3: docs/CCAgentWorkSpace/A3/workspace/reports/2026-06-14--gui_ux_full_audit.md
- R4: docs/CCAgentWorkSpace/R4/workspace/reports/2026-06-14--cross_ref_audit.md
- TW: docs/CCAgentWorkSpace/TW/workspace/reports/2026-06-14--tw_full_audit_dirty_files_doc_dedup.md
- DIRTY(E3 lens): docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-14--E3--closed_pnl_pagination_m4_fills_targeted_audit.md
- FA: inline（harness override，全文在 workflow finding return）
