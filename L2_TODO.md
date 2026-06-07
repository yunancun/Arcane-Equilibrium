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

**operator 拍板啟 E1。** 啟動後走 `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`，依 §3 phase 序，每
phase 綠燈才下一步。尚未動任何碼／migration／DB／部署；singleton 註冊、V134/V13x 皆未落地。三端同步
為 PM 動作。

## §3 Phase checklist（建置序 = 設計 §J；每 phase green-gated）

| Phase | 內容 | 狀態 | Gate to next |
|---|---|---|---|
| P1 | D3 foundation：`agent.l2_calls`（V134 append-only）+ 全鏈 provenance + gate-seam + **E2 sanitize-before-persist** | ⬜ 未啟 | D3 綠 + sanitize 在 write path；其餘一律不 ship |
| P2 | Orchestrator + registry（無 `autonomy_level`，derived）+ PromptContract/schema + out-of-bound guard + admission(§F.1) + adjudication(§F.2)；**`LANE_DIRECTION` 落地** | ⬜ 未啟 | **CC** APPROVE no-auto-path-to-live + carbon-layer fence；fail-safe 不阻塞；write 端 operator-scope |
| P2p | `incident_sentinel`（本地哨兵，alert-only，never remediate）—平行廉價 | ⬜ 未啟 | 獨立可隨任何 phase ship |
| P3 | `ml_advisory.v1`（首個 L2 能力）接現有 ML 管線；cascade Ollama→math/leak→cloud | ⬜ 未啟 | cascade + 確定性 math gate 綠（promotion-relevant verdict 須 **B1 QC sign-off**） |
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
