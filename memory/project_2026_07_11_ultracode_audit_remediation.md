---
name: project_2026_07_11_ultracode_audit_remediation
description: "ultracode 全盤審計弧:07-11 審計→修復→部署 + 07-24 run0 治理版全審(9C/1L/3D/1R,S1 P1 fix branch 未併=首要,adaptive 會漏 44%)"
metadata: 
  node_type: memory
  heat: 0
  type: project
  originSessionId: 76772c74-e189-4bd6-afb6-fa63d693bdfe
  modified: 2026-07-24T01:16:28.667Z
---

2026-07-11 operator 要求「跑 ultracode full audit」→ 後續「派 subagent 生成工程安排→另一 workflow 全鏈修掉→三端同步(含 runtime 部署)」。完整弧走完並經驗證。

## 審計(openclaw-full-audit,run wf_27620bc0-5a4,baseline bf557fbc)
- 4 CONFIRMED:①**HIGH** ML ship-gate validation leakage(quantile 單 tail-holdout 三用=early-stop+CQR calib+報告指標,無獨立 test 分區,coverage gate 近乎恆真)②MED FA 零產出 vs dormant-scaffold annuity(操作面 directive 非 patch)③MED PIT lineage source-only(model_registry 無法重建 model→data)④MED AMD-2026-07-09-01 漏登 register(DEFER-COLLISION,並行 session 佔 SPECIFICATION_REGISTER.md)
- 2 REFUTED(對抗驗證有效):CPCV「silently never written」(cron wrapper 有 export PG_*+trust-auth loopback→實際會寫,殘留 latent fragility);risk-config 單擊 save(server route `_require_live_gates_if_live`→`all_five_live_gates_ok` 全 5-gate,security 駁回,只剩 LOW UX)
- 8 seam re-probes(coverage debt,未驗證):fee 常數 SSOT 碎裂(5.5bps 多處硬編)、IBKR port 4001 跨層矛盾、CV-leakage→deprecated t-test false-GO 放大、dormancy 無 compile-guard、4-head 完整性、agent-session token 無 budget、cron 實際執行 head、composite live-write。教訓:verifier 投票隨機但淨裁決穩定;**verify 首跑漏 1 裁決者(StructuredOutput retry cap)→resumeFromRunId 補跑才完整**。

## 修復(PA 工程安排 14 TIER-A→fix workflow 12 項,worktree 隔離)
- **已上 origin/main 且引擎重部署**:9 項(1,2,3,4,5,8,11,12,13)= commit `6b7ad5ca8`(1 HIGH+8 MED/LOW,+2941 行,23 檔含 E4 tests)。Item 1 leakage 修法=**三向 disjoint 分區(val/calib/test)+ 小樣本 two-way shadow-capped fallback**(n∈[200,400) 不再 no-model,§6.5 shadow band 復原;downgrade-only hard cap 保證 should_ship 永不消費 shared-holdout 指標;MIT re-review SOUND)。**未來勿把 two-way fallback 當 bug「修掉」,勿回退成單 holdout。** Item 3 embargo verdict cap、Item 5 scorer CPCV cap+purge、Item 8 L2 fence-strip+stage 拆分、Item 11 deploy-drift 偵測(detection-only)、Item 12 portability、Item 13 IBKR port 4001 reject 皆含 test。
- 引擎:Linux HEAD=`c082bc569`(後續並行 session 續推),running build `72ed1f5fc`(含 fix 世代,2026-07-11T10:20Z 重啟);Stage B/C/D/E deploy 閉環,途中 catch+fix **PA-DRIFT-6**(V100 governance_approval_id FK→soft reference,composite PK 不可 FK)。OPS preflight 初判 NO-GO(cargo not-found=PATH 問題非真失敗、無 rollback 備份、target-SHA drift)→條件補齊後 restart。

## 6/7/Q4 已併入 main(decouple 方式,2026-07-11)
- operator「1併入」→ 我 push-back 不 force-deploy 並行 session 的 ALR 鏈,改 **decouple 併入**:Item 6(CPCV DSN threading+distinct persist_status+loud WARN)+Q4(two-way in-sample gate provenance+canary_promoter HOLD guard,補先前 shadow_only 仍可自動晉升的漏洞)**已 live 於 main**;Item 7 code+**V157 migration** 亦併入但 register **改 tolerant**(schema probe→缺欄位走 legacy 14-param SQL,不寫 lineage),**故先於 V157 apply 併 main 不會讓 cron register 失敗**。合入序:branch `9109ae10`→tolerance `4e9c114`→rebase+push HEAD:main=**`1b16115bc`**;三端同步(Linux ff-pull)。E2 APPROVE(item7 nits)+Linux PG dry-run double-apply PASS+ml_training 1508 passed。
- **V157 仍 pending**:prod PG 在 V150,V151-V156=並行 session ALR 鏈未 apply。**Item 7 lineage 要等 V151-V157 協調 migration 部署(OPS preflight+operator)才生效**,欄位 apply 後 register 自動走完整路徑。sqlx 按序 apply→不能單 apply V157。TODO v788 `P2-AUDIT-REMEDIATION-6-7-Q4-V157-DEPLOY` 追蹤。E2 nit:合成時間戳 fallback 記 ~1970 window;PG_PASS rename(optuna_optimizer.py:442)待 E3 全盤 enumerate。

## 未完(TODO v788 追蹤)
- **GUI 9/10 遺失需重做**:defense-in-depth UX(live risk save typed-confirm + Danger-Zone [PAPER] 標註),未 commit 就隨 scratch worktree 清掉;main risk-tab.js 舊單擊結構仍在(可重做),但並行 session 正做 P0.4 GUI 改版動同檔→**待 P0.4 落地後重做以免 collision**;security 已 refuted 非急。
- **Item 14 BLOCKED**:AE_INVENTORY_CONSOLIDATED.md 仍在 root,E1 grep 到 live references 正確拒移;需先解 reference 歸屬(LOW)。

相關:[[project_2026_07_07_ai_ml_maturity_roadmap]](PIT/registry=WP2)、[[project_2026_06_14_cold_audit]](前次全審)、[[feedback_v_migration_pg_dry_run]]、[[project_ssh_bridge_workflow]]、[[project_multi_session_memory_race]](本弧全程有並行 session 活躍推 main,worktree 隔離+cherry-pick/rebase 同步)。

## 2026-07-24 run 0:治理版 full audit(S1 formal-closure 後首輪)

run `wf_749b4f8c-2ea`,baseline main=runtime=`7d78765a2`(PR#114 merge),`adaptive_shadow` report-only。13 軸 backstop 全完成(45 calls,E3/IB 首攻 API error 由 retry budget 恰好吸收,`final_null_node_count=0`);130 findings→16 claims→**9 CONFIRMED/1 LATENT-HIGH/3 DISPUTED/1 REFUTED**+5 seam+92 assumption;5.06M subagent tokens。正本=`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-24--full_system_ultracode_audit_run0.md`(+decision_view.json 含全 digest)。

- **首要**:claim-0002/0005(HIGH)=main 帶已知 S1 效果縫 P1 缺陷,fix 只在 `agent/aiml-s1-closure-p1p2-fixes` 未併;**併入前不得做任何 S1 SSHSIG 簽署**。claim-0015(HIGH)=TODO.md 落後 3 個已 merge PR。
- **治理硬數據**:9 confirmed 有 4 條(BB/OPS/QC×2)來自 adaptive shadow 子集之外 → **adaptive-only recall 不及格,`adaptive_shadow` 默認必須維持**。
- QC 重確認 PROFIT-1 現況(gates.rs 雙扣仍在,提交 operator 再裁決非默改);新 QC 發現 DSR gate 缺 √Var(SR_k) 縮放=K≥2 幾乎必 block(over-gate 壓 promotion);BB:110003/110049 零消費者(INSTR-ENSURE-FORCE-1 自 04-23 懸置);AI-E×3=workflow 自身缺陷(retired model pin `claude-opus-4-6`/第三票 reserve=1/regression 死碼)+closure-quality ledger 零實例。
- seam:S1 attestation 三軸同源、成本模型雙缺陷(fill-sim fee 半價×PROFIT-1)須同輪裁決、promotion 統計功效 QC+MIT 聯查、DSN split-string 繞掃描器(E3 追蹤)、active-state 家族 stale。
- **教訓(派發側)**:①現行 desktop Workflow 沙箱無 crypto.subtle/TextEncoder 且 Date.now 拋錯→saved 治理 workflow 原樣必死;解=派發側 shim runner(純 JS SHA-256/UTF-8 注入 globalThis+`admission_now_ms` 走 args),驗證邏輯 0 改動、digest 全過;修法應上游化。②bybit/ibkr surface 不能入 full-audit task contract(external_policy_snapshot 本地必 blocking/debt 而 admission 要求 debt 全空)→摘除後 BB/IB 軸照樣在 backstop 跑。③context artifact 220KB 不可能手打入 args→byte-exact 嵌入 runner(`scriptPath`)。
