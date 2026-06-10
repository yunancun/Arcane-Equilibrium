# L2 Advisory Mesh — TODO

**版本** v1 ｜ **日期** 2026-06-05 ｜ 設計 = v4-final（0 CRITICAL · 2 BLOCKER 已閉）｜ gating = **B1/M1/M2 ENDORSED**

**狀態**：設計 **E1-READY**，等 operator 拍板啟 E1。本檔僅為精簡派工存根，不貼長架構。
**SSOT 連結**：
- 設計（v4-final）`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-05--l2-advisory-mesh-design-draft.md`
- 執行方案 `docs/execution_plan/2026-06-05--l2-advisory-mesh-execution-plan.md`
- 整合背景 `docs/execution_plan/2026-06-05--l2-copilot-design-session-consolidated.md`
- 本地哨兵基礎（sibling）`docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-05--watchdog_alert_wiring_design.md`

---

## §1 Active blockers

**無。** 四審（CC/MIT/QC/E3）0 CRITICAL；2 BLOCKER（B1 beta-neutral / B2 forward-OOS）已折進設計
body 並閉合；3 re-confirm（QC B1 / MIT M1 / MIT M2）= **ENDORSE**。

## §2 Next action

**P1+P2+P3a+P3b 皆過 pre-deploy green gate 並 scoped-commit（2026-06-09~10）。**
- **P1 `f1c3c1ca`**（D3 ledger+redactor v4）/ **P2 `6a9dd0f1`**（Orchestrator+LANE_DIRECTION+fail-safe）/ **P3a `aeae4da4`**（ml_advisory diagnose/interpret，agent.lessons inert sink）/ **P3b（本 checkpoint）**（hypothesize alpha-gate）。
- **P3b**：beta_neutral_check(B1 雙因子 BTC+altcap、三軸|β|<0.15+β_upper<0.20、down-leg≥180d、SE+HAC) + altcap producer(equal-weight ex-BTC CORE25 PIT walk-forward on-the-fly 無 V137) + shift1/is_oos leak producers + hypothesize 模式(L3+can_generate_hypotheses+enabled=false **雙閘**；cascade Ollama-generate→**math gate Q1→DSR→PBO→B1→leak strictest-wins=唯一 alpha validator**→cloud survivors；sink=agent.lessons inert)。E2(碼綠)/QC(**B1 final APPROVE**)/MIT(**M3+M4 APPROVE**)/E4(Linux parity + **altcap real-smoke 真資料 sane**)/QA 全綠。E1 自抓修 `residual_alpha_gate` 字串排序 bug(`_chrono_key`) + **fail-loud temporal-key 契約**（int-bar-index）。
- 他 session WIP（aeg leftover 3 檔）全程隔離未動。

**next**：① **✅ deploy bundle DONE（2026-06-10）**：main `7b8fae45` = cherry-pick 重放（`8ffa31f2` 設計文件/`a38d9bed` P1/`ce639e25` P2/`7296747e` P3a/`c790d1e4` P3b，零衝突，5 共享檔 byte-identical 於 `24d049fc` 樹）+ `bf32074d` 測試適配補遺（P3b 漏 commit 3 test 檔=乾淨樹必 FAIL 盲點，已閉）+ `7b8fae45` meta-doc。re-test：Linux layer2 家族 **450 passed/4 xfailed/0 failed** + full suite **4661 passed/8 pre-existing fail（集合==E4 基線，0 新增）** + Mac 子集 74+208 綠。E3 deploy 審 **PASS-with-NOTE**（修正 runbook：`OPENCLAW_AUTO_MIGRATE` consumer=**engine** 非 control_api，故走 env-file + `restart_all.sh --keep-auth` 全 scope）。Linux applied：sqlx **133→136**（engine `auto_migrate applied=3`，V134/135 hypertable ready + V136 Guard A PASS NOTICE 鏈全綠），`agent.l2_calls`/`agent.l2_consequential_marks`/`learning.l2_gate_seam_log` 建成**全 0 rows=dormant**，V136 provenance 欄 3 表落地，api 0 panic/console 303/demo engine tick 正常，AUTO_MIGRATE 已復原 0。**deploy-NOTE**：(a) prod 無 `trading_ai` role → migration 走 role-absent 分支（REVOKE PUBLIC；`trading_admin`=owner 隱含全權，與 agent.lessons V133 同構=sign-off 前提一致，append-only 靠 PUBLIC-REVOKE+code 層 INSERT-only）；(b) api worker 啟動有 `_sha256_text` import fallback log（設計內 fail-soft，本地等價 sha256）。**`feature/l2-critic-lessons-tools` = SUPERSEDED `1f34653c`，勿 merge/rebase/取檔**。**owed-post-deploy**：deployed-E2E（真觸發→真 ledger row；operator-scope `/trigger`）。② **★P3b owed-before-hypothesize-enable**（設 `enabled=true` 前**必補**否則 universal DEFER）：int-bar-index re-index(producer/conductor wiring) + agent.lessons seed 5-10 dead-modes(M4 bad-set+novelty) + producer→math_gate_inputs conductor wiring(AEG-S3 候選接口) + V127 population + 6 ex-BTC symbol(ATOM/ETC/FIL/ICP/INJ/UNI) klines 1d 覆蓋 ③ **P4**(online-FDR loop，tier-gated L3+) 或 P2p(incident_sentinel)。

**owed（operator-gated）**：deployed-E2E（真觸發→真 ledger row；operator-scope `/trigger`）。（branch divergence 與 full Linux regression 已於 2026-06-10 deploy 收口：bundle worktree 全量 4661 passed/0 新 fail）

## §3 Phase checklist（建置序 = 設計 §J；每 phase green-gated）

| Phase | 內容 | 狀態 | Gate to next |
|---|---|---|---|
| P1 | D3 foundation：V134 `agent.l2_calls`+marks / V135 gate-seam / V136 上游 provenance / L2CallLedgerWriter / redactor v4 / cost_tracker 消毒 / 接線 | ✅ **green(pre-deploy) 2026-06-08** PA→E1→E2/E3/E4-LinuxPG/QA 全 PASS | owed-post-deploy: deployed-E2E + full Linux regression + sqlx apply（operator-gated）；殘留 naked+cap-straddle→P3 source-side |
| P2 | Orchestrator + registry + LANE_DIRECTION + PromptContract + guard + admission + adjudication + fail-safe（TOML-only，**0 migration**） | ✅ **green+committed `6a9dd0f1` 2026-06-09** CC-A級/E2(2輪)/E3(2輪)/E4-parity/QA 全 PASS | owed-post-deploy: deployed-E2E + full Linux regression |
| P2p | `incident_sentinel`（本地哨兵，alert-only，never remediate）—平行廉價 | ⬜ 未啟 | 獨立可隨任何 phase ship |
| P3a | `ml_advisory.v1` diagnose_leak+interpret_result（無 alpha；cascade Ollama→leak/diag gate M3→cloud；**sink=agent.lessons inert**）| ✅ **green(pre-deploy) 2026-06-09** E2(3輪)/E3/MIT(M3+M4)/E4-parity+agent.lessons-grant/QA 全 PASS | owed-post-deploy: deployed-E2E（需 V134 deploy + conductor trigger）+ full Linux regression |
| P3b | hypothesize→promotion alpha-gate：beta_neutral_check(B1) + altcap producer(equal-weight PIT) + shift1/is_oos leak producers + hypothesize 模式(L3 雙閘) | ✅ **green(pre-deploy) 2026-06-10** E2(碼綠)/QC(B1 final APPROVE)/MIT(M3+M4)/E4(Linux+altcap smoke)/QA 全 PASS | owed-before-enable: int-bar-index re-index + agent.lessons seed + conductor wiring + V127 pop + 6 symbol klines；deployed-E2E |
| P4 | online-FDR research loop（α-wealth + V132 sealer + novelty + N_eff + Q3 cascade），tier-gated L3+ | ⬜ 未啟 | **MIT** APPROVE M1 + M2；sealed-holdout 證實 |
| P5 | feedback→rule pipeline(§M) + quality/ROI metric(§O) + GUI panel（vanilla JS） | ⬜ 未啟 | **CC** APPROVE no-auto-expansion linchpin + read-only promote inbox；math-primary live packet |

## §4 E1 驗收項（每 phase 對應，詳見執行方案 §2）

- **P1**：V134 Guard A/B + append-only（無 UPDATE/DELETE grant）+ **Linux PG dry-run + 雙 apply 冪等**；FULL prompt/input/response + 版本 + tags；**E2 sanitize 在 write path**（注入 secret → `[REDACTED:*]`，`str(e)` 不入庫）；provenance 加欄不衝突（live 欄 audit-only）。
- **P2**：loader 型別強制 `expand`→MANUAL（無 `lane: live`）；拒 `autonomy_level` 欄；**C1** grep 0 個 `promote_tier`；**C2** 不讀 `can_auto_deploy_to_paper` 判 auto/manual；**F.2** 無 model-adjudication；**E3 E1** write 端 operator-scope；storm 不破 $2/day；fail-safe 無路通 live／無路阻塞 baseline。
- **P3**：**B1** 確定性 `beta_neutral_check`（**雙因子 BTC+altcap 強制**、daily/4h OLS、`|β|<0.15` + 下行 `|β_down|<0.15`、down 定義 30d 回撤>8% OR 7d<-5% lagged-PIT ≥30bars 否則 DEFER、`β+1.96·SE<0.20`）；**Q1** `N_trades_oos≥50` 否則 DEFER；**M3** leak `source_class` typing（`name_pattern_check` 非 leak-free）；**M4** Ollama recall ≥0.85；bull-only 標 `regime-bet/learning-only`。
- **P4**：**M1** φ=1.0 proportional refund、`W_0=0.10·α_target`、demo-confirm bar `n_trades≥30`+green 0R+net≥0+≥21 forward-OOS、`debit_state` 在 **PG `research.alpha_wealth_ledger`**、`α_i ≤ α_target/min_batch_size`；**M2** average-linkage corr>0.5、`K_for_dsr=N_eff` 單 debit、`max(1,N_eff)` guard、`max_variants_per_cluster`；**B2** applier 強制 `forward_oos_days≥21`；V132 sealer 真寫 `state='sealed'`；pre-registration immutable。
- **P5**：**C1** promote-candidate = read-only inbox row（只 operator route 晉升）；**R2-1** 無任何自動 autonomy 擴張；**R2-2** promote 訊號排除 adoption；**R2-3** 低樣本只收縮；**§M** demote-only；**Q2** packet 顯示 cost 分解 + beta_neutral_check；**R2-4** block5 無 verdict、`math_ack_required`；**Q3** blind-window badge + proxy correctness；**E3 E1** human-confirm/`/cost/*` operator-scope；GUI vanilla JS + `node --check`。

## §5 Gating 簽核狀態

| Gate | Owner | 狀態 | 綁定 phase |
|---|---|---|---|
| **B1** beta_neutral_check | QC | ✅ **ENDORSED**（FIX/NOTE 折入 P3/P4 驗收） | P3（promotion verdict）/P4 |
| **M1** FDR refund accounting | MIT | ✅ **ENDORSED**（φ=1.0 + PG ledger NOTE） | P4 |
| **M2** N_eff single-debit | MIT | ✅ **ENDORSED**（avg-linkage corr>0.5 + guards NOTE） | P4 |
| B2 / C1 / C2 / Q1 / Q2 / Q3 / M3 / M4 / E3-E1 / E3-E2 | CC/QC/MIT/E3 | folded（設計 body 已閉） | 見執行方案 §1 |

> 規則：promotion-relevant verdict 不過 **B1（QC sign-off）** 不 ship（diagnose/interpret 模式可先行）；
> FDR loop 不過 **M1 + M2（MIT sign-off）** 不 ship；其餘 design-decided。

## §6 安全不變量（CC 每 phase 三引擎覆驗）

L2 不觸 `live_execution_allowed` / `max_retries` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` /
`execution_authority` / `system_mode` / lease trading authority；`can_modify_live_config=False` 全層
（已硬編碼）；live = 不變的 5 閘 + Decision Lease，人工專屬，auto-loop 結構無法觸及；autonomy 唯一自動
方向 = 向內收縮（auto-contract / human-expand）；worst case = NO_ADVICE = 今日確定性 baseline。

## §7 Open questions（不阻 E1 啟動；對應 phase 前解）

D3 retention 經濟性（P1/P4）｜auto-trigger cadence vs $2/day 超額規則（P2）｜§O promote 權重/sample floor/門檻（P5）｜§M-① review SLA（P5）｜§F.1 debounce 預設（P2/P4）｜Ollama 生成品質（M4 為守，P3/P4）。
