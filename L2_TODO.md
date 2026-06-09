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

**P1 D3 + P2 Orchestrator + P3a ml_advisory 皆過 pre-deploy green gate 並 scoped-commit（2026-06-09）。**
- **P1 = `f1c3c1ca`**：V134-136 ledger+marks/gate-seam/上游 provenance + redactor v4 + 接線。
- **P2 = `6a9dd0f1`**：Orchestrator+registry+LANE_DIRECTION+admission+F.2+fail-safe（TOML-only，0 migration）。
- **P3a**（本 checkpoint）：ml_advisory diagnose_leak+interpret_result（無 alpha；cascade Ollama screen M4→leak/diag gate M3→cloud-L2 interpret survivors；**sink=agent.lessons inert**——閉了原 mlde_shadow_recommendations 被 active `mlde_demo_applier` 掃描去 mutate demo 配置的 S-2 安全洞）；E2(3輪)/E3(完整)/MIT(M3+M4 GRANTED)/E4(Linux parity + agent.lessons INSERT 權 confirmed)/QA 全綠。
- 他 session WIP 全程 scoped 隔離未動。

**next = P3b track ACTIVE（2026-06-09 operator 開）**：`hypothesize→promotion`（alpha-bearing）blocked on——**QC**：B1 four final numbers + **altcap cap-weighted basket 構造規範（data 不存在=最大 gap）** + Q1 threshold；**MIT**：shift1_compliance/is_oos_gap producer + M4 benchmark artifact + down-market regime(V127) population。QC+MIT 出 spec → PA 設計 → E1 build beta_neutral_check + altcap producer + hypothesize 模式。

**owed（operator-gated/timed）**：① branch divergent，merge 前需 rebase（operator 處置）② **deploy 活化整個 P1+P2+P3a bundle**：push → control_api restart + V134/135/136 經 auto-migrate apply（prod 現 `_sqlx_migrations`=133，V134-136 未 apply）③ deployed-E2E（需 V134 deploy + conductor trigger）④ full Linux regression post-push ⑤ minor: parents[5] eager-default nit / cap-mode 一致性斷言（conductor wiring 時加）。

## §3 Phase checklist（建置序 = 設計 §J；每 phase green-gated）

| Phase | 內容 | 狀態 | Gate to next |
|---|---|---|---|
| P1 | D3 foundation：V134 `agent.l2_calls`+marks / V135 gate-seam / V136 上游 provenance / L2CallLedgerWriter / redactor v4 / cost_tracker 消毒 / 接線 | ✅ **green(pre-deploy) 2026-06-08** PA→E1→E2/E3/E4-LinuxPG/QA 全 PASS | owed-post-deploy: deployed-E2E + full Linux regression + sqlx apply（operator-gated）；殘留 naked+cap-straddle→P3 source-side |
| P2 | Orchestrator + registry + LANE_DIRECTION + PromptContract + guard + admission + adjudication + fail-safe（TOML-only，**0 migration**） | ✅ **green+committed `6a9dd0f1` 2026-06-09** CC-A級/E2(2輪)/E3(2輪)/E4-parity/QA 全 PASS | owed-post-deploy: deployed-E2E + full Linux regression |
| P2p | `incident_sentinel`（本地哨兵，alert-only，never remediate）—平行廉價 | ⬜ 未啟 | 獨立可隨任何 phase ship |
| P3a | `ml_advisory.v1` diagnose_leak+interpret_result（無 alpha；cascade Ollama→leak/diag gate M3→cloud；**sink=agent.lessons inert**）| ✅ **green(pre-deploy) 2026-06-09** E2(3輪)/E3/MIT(M3+M4)/E4-parity+agent.lessons-grant/QA 全 PASS | owed-post-deploy: deployed-E2E（需 V134 deploy + conductor trigger）+ full Linux regression |
| P3b | `hypothesize→promotion`（alpha-bearing）+ beta_neutral_check（B1）| 🔬 **track ACTIVE 2026-06-09**（QC B1/altcap + MIT shift1/is_oos/M4 benchmark）| blocked: altcap basket 構造（data 不存在）+ QC B1 final + shift1/is_oos producer + L3 tier |
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
