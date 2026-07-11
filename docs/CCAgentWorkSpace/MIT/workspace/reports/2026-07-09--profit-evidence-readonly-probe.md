# MIT read-only 盈利證據取數（Probe 階段供數）— 2026-07-09

**Agent**: MIT（ML & Database Auditor）
**邊界**: 全程 read-only。Linux 證據僅 `ssh trade-core` read-only 命令 + `docker exec trading_postgres psql`（readonly 查詢）。無任何 fix / config / gate / deploy / restart / auth 變更。
**證據紀律**: 每條 FACT 附可重跑命令/SQL/file:line；無法取證者標 ASSUMPTION / INFERENCE；單 regime 結果標 regime-bet。
**Runtime 錨點**: trade-core 2026-07-09T20:52:08Z；`rust/target/release/openclaw-engine` PID 1561777（07-09 08:28 起）running（`ps aux | grep openclaw`）；trading_postgres Up 4 days；`ma_crossover` 最後 signal 20:18+02、`grid_trading` 22:54+02（engine 活著）。

---

## A. 近期成交 fills：gross edge 分布 + 成本分解（30d，demo + live_demo）

**Load-bearing 語義（FACT）**: `trading.fills.realized_pnl` = **GROSS 價格 PnL（不含費用）**；net = realized_pnl − 兩腿 fee。證據 `rust/openclaw_engine/src/tick_pipeline/pipeline_helpers.rs:507-529`（`gross_bps = (realized_pnl / entry_notional_portion) * 10_000`，entry/close fee 另計）。**任何把 fills.realized_pnl 直接當 net 的讀數都高估。**

### A.1 總量（FACT；SQL: `SELECT engine_mode, count(*), sum(fee), sum(realized_pnl) FROM trading.fills WHERE ts > now()-interval '30 days' GROUP BY engine_mode`）
| engine_mode | fills 30d | fee 合計 | gross rpnl 合計 |
|---|---|---|---|
| demo | 1,011 | 254.68 | −148.61 |
| live_demo | 44 | 0.71 | −2.11 |

**30d 全體：gross −150.72 / fees 255.39 / true net −406.11 USDT**。成本結構 = fee-dominated：費用是 gross 虧損的 ~1.7×。

### A.2 Per-strategy true net（FACT + INFERENCE 標註）
費用歸屬用「同窗全 fills fee 合計」近似兩腿配對（**INFERENCE：未做逐 round-trip 配對，窗口邊界的 entry/close 錯配會有小誤差**）。closing fills = `realized_pnl <> 0`。

| strategy | closes | gross rpnl | all fees | true net | gross bps | **net bps** |
|---|---|---|---|---|---|---|
| grid_trading | 252 | −102.82 | 129.17 | −231.99 | −5.45 | **−12.31** |
| flash_dip_buy | 92 | −5.42 | 17.14 | −22.56 | −2.48 | **−10.32** |
| ma_crossover | 87 | −32.70 | 38.72 | −71.42 | −5.51 | **−12.04** |
| funding_arb | 31 | −32.48 | 38.67 | −71.15 | −11.96 | **−26.20** |
| bb_reversion | 28 | +22.46 | 26.27 | −3.81 | **+9.06** | **−1.54** |
| bb_breakout | 1 | +0.17 | 0.28 | −0.10 | +1.75 | −1.05 |

**結論：30d 內全部策略 true net 為負。** 唯一 gross 正的 bb_reversion（19W/9L，橫跨 16 symbol 多日，非單一 episode——結構比 NEAR cell 可信）扣兩腿費後 −1.54bps。n=28 無統計顯著性（19/28 單邊 sign test p≈0.044 邊緣），**不是 promotion 證據；30d 窗單一 regime，標 regime-caveat**。

### A.3 Per-fill gross bps 分布（closing fills，n=493；FACT）
p10 −45.65 / p25 −16.06 / **p50 −1.17** / p75 +9.73 / p90 +29.66 / mean −2.86 bps。中位數即為負，尾部不對稱（左尾重）。

### A.4 成本分解 by liquidity role（30d；FACT）
| role | mode | n | avg fee_rate | avg slippage bps | avg maker markout bps |
|---|---|---|---|---|---|
| taker | demo | 440 | 5.76bps | −6.08 | — |
| maker | demo | 545 | 2.07bps | — | **−7.57**（adverse） |
| taker | live_demo | 22 | 5.50bps | −1.83 | — |
| maker | live_demo | 22 | 2.00bps | — | — |

taker fee ~5.5-5.8bps/腿 + slippage ~6bps；maker fee 2bps/腿但 markout −7.6bps（adverse selection 把 maker 省的費吃回去）——與 2026-07-06 maker-nogo 結論一致。

---

## B. 策略 active/dormant 清單

Config 權威 = Linux runtime TOML（`~/BybitOpenClaw/srv/settings/strategy_params_demo.toml` + `settings/risk_control_rules/risk_config_demo.toml`）；runtime 驗證 = `trading.signals` 7d。

| strategy | config | signals 7d | orders 7d(entry) | fills 7d | 狀態 |
|---|---|---|---|---|---|
| ma_crossover | active=true | 602,091 | ~0 | 5（皆平倉） | ACTIVE-signal / entry 幾乎全被 gate 擋 |
| grid_trading | active=true | 222,397 | 0 | 0 | ACTIVE-signal / entry 0（cold-start block + soak isolation） |
| bb_reversion | active=true | 17,620 | 15 | 30 | **ACTIVE-trading（唯一持續成交）** |
| flash_dip_buy | active=true（pilot 三鎖） | 164 | 43 | 56 | ACTIVE-trading（pilot） |
| bb_breakout | active=true | 2 | 2 | 0 | 近似 dormant |
| funding_arb | **active=false（三端硬鎖）** | 0（last 06-19） | 0 | 0 | DISABLED |
| funding_harvest / funding_short_v2 / liquidation_cascade_fade | active=false | 0 | 0 | 0 | DISABLED |
| macd_crossover / macd_exhaustion / rsi_exit / rsi_overbought_oversold / bollinger_reversion / rsi_divergence / regime_detector | （不在 demo TOML） | 0（last signal 2026-05-06） | 0 | 0 | DEAD（5月起無 signal） |

**live_demo lane：最後 live_demo fill = 2026-06-12 23:29（FACT）→ live_demo 執行面 dormant ~27 天**；demo lane 繼續成交。

---

## C. Gate 拒單統計 + 反事實（真負 vs 誤殺）

### C.1 拒絕率（FACT；`SELECT verdict, count(*) FROM trading.risk_verdicts WHERE ts > now()-interval '30 days' GROUP BY verdict`）
- 30d：**Rejected 2,308,158 vs Approved 1,622 → 拒絕率 99.93%**。
- All-time：Rejected 2,488,483 / Approved 1,643。

### C.2 拒因組成（30d top，FACT）
| 拒因類 | n | 佔比解讀 |
|---|---|---|
| `bounded_probe_soak_isolation:ordinary_demo_entry_blocked` | 415,651 | **自 2026-06-29 19:29 起 soak isolation 擋掉全部 ordinary demo entry**（min/max ts 實查），持續至 07-09。這是 grid/ma 零 entry 的直接原因之一，非 alpha 判斷 |
| `cost_gate(JS-demo): estimated=<0 blocked` 各檔 | 合計 >1.3M | James-Stein 負估計阻擋（主體） |
| `cost_gate(JS-demo): edge=3.61bps < threshold=8.80bps (fee=4.00bps, wr=0.59)` | 49,388 | **正 edge 但低於門檻**——這一類才是「誤殺候選」的正確母集 |
| `cost_gate(JS-demo): no edge estimate for grid_trading — cold-start blocked` | 35,689 | 冷啟動阻擋 |

### C.3 反事實 edge（blocked-signal counterfactual；FACT，來源 `blocked_outcome_review_latest.json` gen=2026-07-09T20:31:20Z）
- blocked_signal_outcome 總數 949,629（14d ledger 窗）：**net positive 僅 14.92%，avg net −75.13bps**（conservative_v1 成本模型）→ **被擋信號的絕大多數是真負（true negative），cost gate 整體無系統性誤殺**——與 2026-06-13 全真負結論一致。
- 76 side cells：keep_blocked=5、insufficient_sample=13、realized_contradiction=0、false_negative_candidate=**1**（見 E/F1）。
- **成本模型注意（INFO）**：conservative_v1 假設 cost=92.3bps（slippage 30bps/腿）；demo 實測 taker slippage 僅 ~6bps → conservative 對高流動性 symbol 高估成本 ~5×。誤殺判斷若改用 realistic 成本，「edge 正但 < threshold」類（49,388 筆）值得重跑反事實——此為唯一建議深挖的誤殺母集。

---

## D. Feature/pipeline：真帶 edge vs 死表（freshness + decision impact）

| 表 | rows | freshness（+02） | 7d 增量 | Decision impact | 判定 |
|---|---|---|---|---|---|
| learning.decision_features | 15.65M(est) | 07-09 23:03 | 876,821 | cost_gate 反事實鏈輸入 | LIVE（但 99.99% 是 reject 行） |
| learning.decision_features_evaluations | 411M(est, pg_stat) | 07-09 23:03 | 883,489 | 評估鏈 | LIVE；**體積風險，retention 未驗** |
| learning.james_stein_estimates | 1,096 | 07-09 22:57 | 活躍 | **直接驅動 cost_gate 拒單（JS-demo）** | **PRODUCTION-impact（阻擋方向）** |
| learning.mlde_shadow_recommendations | 28,942 | 07-09 22:57 | 活躍 | → mlde_param_applications | LIVE-shadow |
| learning.mlde_param_applications | 12,652 | 07-09 22:57 | 316 | **最後 `applied`=2026-06-29；7d 內 176 skipped + 140 failed、0 applied** | **接線但 10 天零實效** |
| learning.model_registry | 93 | 07-09 03:19（daily cron） | 每日訓練 | **全部 canary_status=shadow / verdict=shadow_only；0 canary 0 production** | SHADOW |
| learning.cpcv_results | 307 | 07-09 03:19 | 活躍 | 訓練評估 | LIVE-support |
| learning.strategy_trial_ledger | 72,229 | 07-09 22:56 | 7,874（edge_estimator_cycle） | edge estimator | LIVE-support |
| learning.exit_features | 3,677 | 07-09 06:48 | 隨 fill | 訓練標的 | LIVE（量小） |
| learning.linucb_state | 15 | 07-09 22:57 | 活躍 | bandit 狀態 | LIVE（小） |
| learning.bayesian_posteriors | 296 | **07-05 停** | 0 | — | STALE 4d |
| learning.strategist_applied_params | 21,623 | **06-24 停** | 0 | — | STALE 15d |
| learning.decision_shadow_exits / decision_shadow_fills / edge_estimate_snapshots / hypotheses / experiment_ledger / anomaly_events / ml_parameter_suggestions / foundation_model_features / demo_residual_alpha_reports / hidden_oos_state_registry / l2_gate_seam_log | 0 | — | — | — | **DEAD/FOUNDATION（0 row）** |
| agent.lessons / agent.l2_calls / agent.ai_invocations | 0 | — | — | — | DEAD |
| learning.alr_* (5 表) | 65-131 | 07-09（alr_event_consumer PID 1925314 活） | 新增 | P2 ALR shadow | LIVE-new（evidence-only） |

**ML 訓練標籤斷糧（HIGH concern，FACT）**：7d 內 decision_features 標籤組成 = `rejected_governance` 743,465（label 0.0）+ `synthetic_reject` 133,294 vs **`realized_fill` 僅 14 行**（flash_dip_buy 12 mean −5.42bps、bb_reversion 2 mean −7.61bps）。今日訓練 sample size：ma_crossover 316 / grid_trading 836。**「真帶 edge」的 feature→label→train 供血近乎為零；模型全 shadow，無決策影響。目前唯一影響真實決策的 ML 組件 = James-Stein edge estimates（以「阻擋」方式）。**

---

## E. Profit-first loop runtime 狀態（strict）

| 項 | 狀態 | 證據 |
|---|---|---|
| `_latest` Cost Gate 候選 | `ma_crossover\|NEARUSDT\|Buy`，review rank 1，avg_net 64.98bps、outcome_count 5058、wrongful_block_score 129.97、bh_fdr_pass=true | `blocked_outcome_review_latest.json` gen 2026-07-09T20:31Z |
| **候選證據有效性** | **無效（見 F1）：5058 outcomes 只含 2 個 distinct entry（2026-07-07 16:19 與 16:20 UTC），單日單 episode** | ledger 實測（下） |
| Standing 授權 envelope | **已過期**：`expires_at_utc=2026-07-09T00:12:30.886090Z`（現在 20:52Z，過期 ~20.7h）；檔內 status 字串仍為 `STANDING_DEMO_AUTHORIZATION_ACTIVE`（**string≠有效性**）；sha `05fe07f5ad4f...` 與 TODO 一致；max_probe_orders=2、demo_only=true | `jq .expires_at_utc ~/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/standing_demo_operator_authorization.json` |
| False-negative operator review | gen 2026-07-09T20:33Z：`decision=defer`、status=`STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT_REVIEW`（loop 自己偵測到授權失效並 fail-closed defer——**行為正確**） | `false_negative_operator_review_latest.json` |
| Candidate-matched order/fill proof | **無**：strict scan sha `ca4bf9cb4188...`（與 TODO 一致）`candidate_matched_actual_order_fill_evidence_present=false`、candidate_rows=0；**獨立 DB 交叉驗證**：`ma_crossover`+`NEARUSDT` 最後 order=2026-06-18 08:43、最後 fill=2026-06-18 14:17，候選選定後零下單 | `/tmp/openclaw_near_order_capable_after_plan_materialization_20260708T2250Z_c66338e8/outputs/current_candidate_order_fill_evidence_scan_strict.json` + SQL |
| 下一步阻塞 | TODO 記 order-capable packet sha `305774b2` 唯一 blocker=`renewed_active_bbo_manifest_stale_for_review_packet`（stale manifest `17a3a426` 綁舊 checkpoint `08f7e957`）——**本審計未直讀該 packet 檔，標 INFERENCE（source: TODO.md）**；疊加本審計 F3（auth 過期）後，實際 blocker 至少兩個 | TODO.md P0 行 |
| Lane cron | 活著：`_latest` 系列 artifacts mtime 22:29-22:37+02（今日每小時刷新） | `ls -la` lane dir |

---

## F. Findings（全量，含 LOW/INFO；severity × confidence）

**F1（CRITICAL / HIGH confidence / FACT）— 動態候選的 5058 outcomes 是 2 個真實觀測的偽複製（pseudo-replication ×2529）。**
全 5058 行 `blocked_signal_outcome`（`ma_crossover|NEARUSDT|Buy`）僅 2 個 distinct `entry_ts_ms`：
- `1783436340000`（2026-07-07 16:19:00Z）× **2,614 份完全相同副本**：net +70.2776bps，entry 2.0298 → exit 2.0628
- `1783436400000`（16:20:00Z）× **2,444 份**：net +59.3201bps
兩窗 60min markout 重疊 59/60 → **有效樣本 n_eff ≈ 1-2**，全部來自 NEAR 單日 +1.6% 一小時 pop。review 的 `one_sided_t_p=0.0`、`bh_fdr_pass=true`、`min_outcomes_per_side_cell=3` 全部把 5058 當獨立樣本計 → 統計上無效。**「avg net 64.98bps/5058」實為單一 regime-bet episode，不是 edge 證據。**
成因：ma_crossover 每秒級重發 signal，每次被擋都生成一行 outcome（同 entry bar 同 exit bar），`outcome_review.py` 無 per-(cell, entry_ts) 去重。
可重跑證據：`grep -h "ma_crossover|NEARUSDT|Buy" ~/BybitOpenClaw/var/openclaw/cost_gate_learning_lane/probe_ledger.20260707T163027Z.jsonl probe_ledger.20260707T213755Z.jsonl | grep blocked_signal_outcome | jq -r '[.entry_ts_ms,.realized_net_bps]|@tsv' | sort | uniq -c` → 兩行。
**含義**：目前 loop 的唯一 false-negative 候選（及其 READY_FOR_PM_E3_DISPATCH 下游鏈）建立在無效統計上。修復歸屬 E1/QC（review 需按 distinct entry window 去重 + effective-n 檢定），MIT 不改碼。

**F2（HIGH / HIGH / FACT）— 30d 全策略 true net 為負；系統當前不賺錢，費用主導。** 見 §A：gross −150.72、fees 255.39、net −406.11 USDT/30d。唯一 gross 正 cell（bb_reversion +9.06bps）扣費後 −1.54bps。

**F3（HIGH / HIGH / FACT）— standing Demo 授權已過期 ~20.7h，loop 正確 fail-closed（defer），但 TODO 的 READY_FOR_PM_E3_DISPATCH 前置又多一項失效。** 見 §E。

**F4（HIGH / HIGH / FACT）— 候選零 order/fill proof。** strict scan 與獨立 DB 查詢雙證：候選自選定以來 0 order 0 fill；最近 NEAR×ma_crossover 交易停在 2026-06-18。

**F5（MEDIUM / HIGH / FACT）— soak isolation 自 06-29 起擋掉全部 ordinary demo entry（415,651 次 / 10 天）**。當前 demo 成交只剩 flash_dip_buy pilot + bb_reversion 等旁路。解讀「策略 dormant」時需先扣掉這個結構性閘（它不是 alpha 判斷）。學習面後果：realized_fill 標籤斷糧（7d 僅 14 行）。

**F6（MEDIUM / MEDIUM / FACT+INFERENCE）— ML 管線零決策影響**：model_registry 93/93 shadow_only、0 canary 0 production；MLDE param applier 最後 applied 06-29，7d 全 skipped/failed；strategist_applied_params 06-24 停、bayesian_posteriors 07-05 停。唯一 production-impact ML 組件 = James-Stein estimates（透過 cost_gate 阻擋）。

**F7（MEDIUM / MEDIUM / FACT）— 被擋信號反事實整體為真負**（avg −75.13bps、正率 14.9%）→ cost gate 系統性誤殺假說再次不成立；唯一值得深挖的誤殺母集 = 「edge 正但 < threshold」類 49,388 筆（建議用 realistic 成本重跑，因 conservative_v1 slippage 30bps vs 實測 ~6bps 高估 ~5×）。

**F8（LOW / HIGH / FACT）— `fills.realized_pnl` 是 gross**（pipeline_helpers.rs:507-529）。任何下游把它當 net 的報表都高估 PnL；本報告 §A 已按 gross/net 分列。

**F9（LOW / MEDIUM）— 資料衛生**：pg_stat n_live_tup 嚴重失真（fills 顯示 1 實為 16,076；exit_features 顯示 1 實為 3,677）——row count 主張必 count(*)（舊教訓再驗證）。decision_features_evaluations est 411M 行、僅 5 index，retention/壓縮策略未驗——體積風險標 operator。

**F10（INFO）— bb_reversion 是當前唯一結構上值得看的 cell**：19W/9L、16 symbols 多日分散、gross +9.06bps，但 net 仍負且 n=28 不顯著。若 maker 化或降費（費 ~10.6bps 往返 vs gross 9bps）在數學上恰好差一個費率檔——與 maker-nogo 的 infra-tier 結論一致，非新發現。

**假陽性候選申報**：F1 的判定依據是 ledger 內 `entry_ts_ms` 完全相同；若 review 鏈在別處（本審計未見的檔）已做 entry-window 去重再算 t/FDR，則 F1 降級——但 `outcome_review.py` grep 無 dedup 邏輯、review JSON 的 `outcome_count=5058` 與 ledger 行數一致，支持原判。

---

## Gaps（取不到/未做）
1. `learning.decision_features_evaluations` 精確 count(*) 未跑（411M est，全掃會超時/壓 DB）；其 `evaluation_outcome` 語義與消費端未逐一追蹤。
2. Approved verdicts 的 per-strategy 歸屬取不到（`details->>'strategy'` 為 null），只能以 orders 近似。
3. Per-strategy true net 的兩腿費用配對是窗口近似（未做逐 round-trip pairing）。
4. Order-capable packet sha `305774b2...` 檔案未直讀（位置未定位；blocker 描述轉自 TODO.md，標 INFERENCE）。
5. model_registry `training_sample_size`（316/836）的樣本構造 query 未溯源（是否只用 realized_fill 標籤未驗證）。
6. live 帳戶（真金）無任何 30d fills 證據需求——本期全部 demo/live_demo，無 live 交易存在（`engine_mode='live'` 30d fills=0，包含於 A1 分組缺席）。

## 建議行動（供 PM/operator 裁決，MIT 不執行）
1. **E1/QC**：`outcome_review.py` 對 (side_cell, entry_ts) 去重 + effective-n / HAC 檢定後重算 false-negative 榜（F1）。在此之前，`ma_crossover|NEARUSDT|Buy` 的 bounded probe dispatch 缺乏統計依據。
2. **PM**：READY_FOR_PM_E3_DISPATCH 鏈在（a）auth 過期（b）BBO manifest stale（c）F1 證據無效 三重失效下，建議先修 F1 再續 chain（避免對無效候選消耗 E3/BB window）。
3. **QC/E1**：用 realistic 成本（實測 slippage 分位數，`slippage_quantile_artifact.py` 已存在）對「edge 正但 < threshold」49,388 筆重跑反事實——這是唯一數學上可能藏誤殺的母集。
4. **operator**：soak isolation 的存續決策（已 10 天）需權衡「隔離保護 probe」vs「realized_fill 標籤斷糧餓死學習迴路」。

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-07-09--profit-evidence-readonly-probe.md
