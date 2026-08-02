# PR#164 追認審計正本（2026-08-02）

- **對象**:PR #164 `governance: bound GPT-5.6 multi-agent execution`,merge commit `245869d25`(2026-08-01T20:51:23Z,mergedBy=yunancun),range `f115a40e6..245869d25`,143 檔 +33,414/−8,064。
- **背景**:該分支原經 operator 批准裁 `SUPERSEDED-KILL`(governance doc §13 先例);2026-08-01 22:51 operator 改判並親自 merge;改判條件=「仔細審核」,即本審計。
- **編排**:workflow run `wf_b7aae581-484`(本 repo 開發用 Claude 主會話派發;transcript 於開發機 session 目錄),5 個 read-only 審計 lane(policy/safety/workflows/machine/claims)+每 lane critical/high findings 對抗覆核。
- **總裁決**:實質面過關,支持追認;4 條 CONFIRMED high 帳面問題由追認整合 PR(#175)收口。
- **可復現錨**:本檔所有量化主張標明復算方式;關鍵數字=治理測試 in-glob 76,939→86,203(+9,264)、glob 外 +1,764(四 glob 合計 87,967 @245869d25)、本地 782 tests passed/0 failed/9 skipped、role memory 熱記憶 1,547,913→41,904B(−97.3%,18 archive digest 逐一對上原 bytes)。


## Lane policy

### Summary
PR#164 vs #165-169 政策語義衝突審計(policy 維度,read-only,range f115a40e6..245869d25):六項對照結論——①§11 輪詢禁令 COMPATIBLE(四 workflow 無任何 sleep/watch/輪詢;while 迴圈全為 DAG 拓撲/fixpoint 迴圈且無進展即 throw;新增 max_wait_cycles/max_no_delta_wakeups/max_wall_clock_ms 等有界執行 cap 與「one watcher per wave、no-delta 終態不得 respawn」,實質強化 §11);②§12 終態凍結 COMPATIBLE(未新增任何對 BLOCKED 弧再開 readiness 層的機制,8 項 MAE 全為 typed EXTERNAL_LIMIT 且 ADR-0052 明文未來 phase 需另行 admission;但帳面矛盾見 finding 1);③§13 meta-work COMPATIBLE-WITH-GAP(無自動生成測試機制——codegen 只從 Registry 重投影 workflow JS,compaction 冪等且證 byte-identical recovery;但新治理測試/腳本落在 §13 凍結與 30% 計量 glob 之外,CI 被迫顯式列名即為證據,構成未來擴張的被動繞道);④三級 tier 下限 SUPERSEDES(正向落地 #166 的 follow-up:22 toml 逐一驗證 T1=sol/high×10、T2=sol/low×9、T3=terra/medium×3 全符;Claude 側 22 agent frontmatter 全符 opus/sonnet 三級;三 workflow 均以 admittedSavedWorkflowTierV1 強制 caller 覆蓋即 throw、allow_inheritance:false;MAE-004=DONE);⑤per-role workspace COMPATIBLE(36 檔=18 角色 memory.md 壓實成 32-34 行 hot index+append-only archive,係清理非寫入;history_on_demand 撤 role-memory glob 改 task-bound history_refs;promotion 需 trusted-host attestation,單方 promotion=zero-mutation;唯 .codex/config.toml 開啟 generate_memories=true+Luna 新自動記憶通道,方向與「automatic growth retired」相反,需 operator 顯式認可);⑥review 批次收口 COMPATIBLE(findings 不得產生 in-workflow 逐 finding verify/fix/review call,一律批次成 coverage_debt 進單一 fresh MAE-005 host phase;fix/verification 預算參數已整組移除;禁 automatic split/retry loop;其開發史上 9 輪 review reopen 為 §11 生效前歷史)。量化復算全符:143 檔 +33,414/−8,064;治理測試家族 glob 內 76,939→86,203(+9,264)+glob 外 1,764≈+11k;本機重跑 6 個治理測試檔 218 passed。追認帳面待修:governance doc §13 先例行仍記 SUPERSEDED-KILL/不 merge/禁 recovery 遞迴,與 TODO v865 EXACT_HEAD_MERGE_AUTHORIZED 及已 merge 事實矛盾。

### Stats
```json
{
 "range": "f115a40e6..245869d25",
 "merge_time": "2026-08-01T22:51:22+02:00",
 "diffstat_recomputed": "143 files, +33414/-8064 (matches claim)",
 "dimension_verdicts": {
  "D1_s11_polling": "COMPATIBLE",
  "D2_s12_terminal_freeze": "COMPATIBLE (ledger contradiction filed separately)",
  "D3_s13_metawork": "COMPATIBLE-WITH-GAP (glob coverage escape, no active backdoor)",
  "D4_tier_floor": "SUPERSEDES (implements #166 follow-up, fail-closed)",
  "D5_role_workspace": "COMPATIBLE (compaction/cleanup; codex memories channel flagged)",
  "D6_review_batch": "COMPATIBLE"
 },
 "tier_verification": {
  "codex_tomls_checked": 22,
  "t1_sol_high": 10,
  "t2_sol_low": 9,
  "t3_terra_medium": 3,
  "claude_agents_checked": 22,
  "violations": 0
 },
 "governance_test_lines": {
  "frozen_glob_before": 76939,
  "frozen_glob_after": 86203,
  "net_in_glob": 9264,
  "outside_glob_new": 1764
 },
 "local_test_reruns": {
  "files": 6,
  "passed": 218,
  "failed": 0
 },
 "role_memory_compaction_check": "PASS (18 roles, manifest sha256:894c1401ca22f2c1...)",
 "workspace_files": "36 = 18 roles x (memory.md 32-34 lines + memory-archive.md append-only)",
 "scratchpad_evidence": "/private/tmp/claude-501/-Users-ncyu-Projects-TradeBot/1fb34c5e-f3ca-48e9-99a1-108451d4ebcc/scratchpad/pr164-policy/evidence-log.md"
}
```

### Findings

#### [high][CONFIRMED] §13 先例帳面與 merge 事實矛盾:governance doc 仍記 SUPERSEDED-KILL/不 merge/禁 recovery 遞迴,但 TODO v865 已改 EXACT_HEAD_MERGE_AUTHORIZED 且 main 已含 #164
- evidence: docs/agents/development-agent-governance.md §13 末段(约 1003-1008 行):「`origin/agent/gpt56-multiagent-remediation-20260730`…裁 `SUPERSEDED-KILL` — 不 merge、分支保留存史、禁 recovery 遞迴」;TODO.md §2(#164 自改,v865):「GPT56-MULTIAGENT-EFFICIENCY-REMEDIATION-20260730 / PR #164 | SOURCE_COMPLETE_WITH_8_TYPED_EXTERNAL_LIMITS / EXACT_HEAD_MERGE_AUTHORIZED | Operator 已明確授權 PR #164 exact-head publication/merge」;實際 merge 245869d25(2026-08-01 22:51:22 +0200)且經 commit b0d1faeb1 所示 `agent/gpt56-multiagent-remediation-recovery-20260801` recovery 分支——正是原裁決明文禁止的形狀。兩本權威帳(policy 正本 vs 派發正本)現互相矛盾,且 policy 正本的「不 merge」宣稱已與 repo 現實不符。
- recommendation: 以 operator 追認為據對 development-agent-governance.md §13 先例行追加演變注記(原裁決文字保留存史,附註 2026-08-01 operator 改判追認 merge、條件=本次審計、PR#164/245869d25),同步 memory 框架健檢 topic 檔演變軌跡;不原地改寫原裁決。

- 覆核 reason: 全部事實復核成立(僅行號更正:實際在 docs/agents/development-agent-governance.md:977-979,檔案共 979 行,非 ~1003-1008)。§13 末段逐字保留「SUPERSEDED-KILL — 不 merge、分支保留存史、禁 recovery 遞迴」且無任何追認注記(檔案在該行結束);TODO.md:344(v865)逐字含 EXACT_HEAD_MERGE_AUTHORIZED/Operator 已明確授權 merge,git blame 定位到 dc5abae91(#164 branch 內 commit,「自改」成立);245869d25(2026-08-01 22:51:22 +0200)merge 的正是裁決點名的 agent/gpt56-multiagent-remediation-20260730 分支;b0d1faeb1(「Merge origin/main into agent/gpt56-multiagent-remediation-recovery-20260801」)經 git merge-base --is-ancestor 確認在 merged head 祖先鏈中——正是原裁決明文禁止的 recovery 分支形狀。normative_policy 正本與 active_work_state 正本現互相矛盾,且 policy 正本「不 merge」宣稱與 repo 現實不符。

#### [high][CONFIRMED] §13 凍結/計量 glob 覆蓋缺口:#164 新增治理測試與治理腳本落在既定 glob 之外,構成未來 meta-work 擴張的被動繞道
- evidence: §13 凍結家族=「tests/structure 的 `test_agent_governance*` 與 `test_development_agent_governance*`」,30% 計量=「觸及 `helper_scripts/maintenance_scripts/agent_governance*`…的 commit」。#164 新增 tests/structure/test_codex_memory_policy.py(138 行)與 tests/structure/test_role_memory_compaction.py(1,626 行)均不匹配凍結 glob——.github/workflows/ci.yml:162-166 被迫顯式逐檔列名(glob 抓不到即為機器證據);helper_scripts/maintenance_scripts/role_memory_compaction.py(2,271 行)與 codex_memory_policy_probe.py(189 行)不匹配 `agent_governance*` 計量前綴。復算:glob 內家族 76,939→86,203(+9,264 行),glob 外另 +1,764 行測試,合計≈+11k。未查獲主動自動生成測試機制(codegen 僅重投影 workflow JS;compaction 冪等且 --check PASS),缺口屬命名範疇性而非機制性。
- recommendation: 追認落帳時同步修 §13 兩處 glob 定義:凍結家族納入 test_codex_memory_policy*/test_role_memory_compaction*(或改為「tests/structure 內以治理機為對象的測試」語義定義+顯式清單),計量前綴納入 role_memory_compaction.py 與 codex_memory_policy_probe.py;並記錄追認後新基線(in-glob 86,203 行@245869d25)。

- 覆核 reason: 全部量化主張精確復算成立:四檔均為 #164 新增(f115a40e6 不存在),行數 138/1,626/2,271/189 逐一相符;in-glob 家族 76,939(f115a40e6)→86,203(245869d25)=+9,264;glob 外測試 138+1,626=1,764;合計 11,028≈+11k。機器證據成立:ci.yml:165-166 顯式列名兩個新測試檔,159-161 行 NOTE 注釋自承 glob 抓不到部分 suites。凍結 glob(doc 963-965 行)與計量前綴(966-972 行)定義如引;grep 未發現任何機器化凍結/計量 enforcement,故 doc glob 即操作性定義,缺口為真。兩腳本按自身 docstring 均為治理機工作(development-role memory compaction/Codex memory policy probe),governance doc 僅在 §9 CLI(865-866 行)引用、§13 計量未納入,不屬 product-work 豁免。軟化性主張亦復現:role_memory_compaction.py --check 回 PASS/0 errors/exit 0,缺口屬命名範疇性而非機制性。注意 §13 生效時點條款使 #164 本批次 in-glob +9,264 不追溯計入凍結——但 finding 主張的是前瞻性覆蓋缺口而非 #164 違反凍結,該條款不構成反駁。

#### [medium] Codex 平台級自動記憶生成被 #164 開啟(generate_memories=true+Luna),方向與「Per-role automatic report/memory growth is retired」相反,需 operator 顯式認可
- evidence: .codex/config.toml:19-24 `[memories] generate_memories=true / use_memories=true / disable_on_external_context=true / extract_model="gpt-5.6-luna" / consolidation_model="gpt-5.6-luna"`。CLAUDE.md:293-294 政策明文 per-role automatic report/memory growth 已退役。緩解確實存在:external-context 線程排除、role memory 側 promotion 需 PM closure+PLATFORM_OR_EXTERNAL_ATTESTED host verifier(單方 promotion=zero-mutation EXTERNAL_LIMIT,role_memory_compaction manifest v3 拒直改 hot bytes)、probe+test_codex_memory_policy.py 鎖定五鍵配置;MAE-018 記為 DONE。但這是新的自動記憶生成通道,且 gpt-5.6-luna 不在 operator 三級 tier 表內(tier 表只治理 20 role),模型指派屬 #164 單方決定。
- recommendation: 追認清單列一項 operator 顯式裁決:是否保留 generate_memories=true 與 Luna 指派;若保留,在 model_effort_tiering memory/governance doc 補一行「memory extraction lane=luna,非 role tier 治理範圍」使帳面完整;若不保留,單行 PR 關閉 [memories] 生成側。

#### [medium] TODO wave2 backlog 兩項已被 #164 完成但仍列 QUEUED(agent-wave tier 綁定、Codex toml model pin),帳面過期
- evidence: TODO.md `P2-FW-WAVE2-FRAMEWORK-OPT-BACKLOG` 仍列「agent-wave saved-workflow tier 綁定(禁向下覆蓋 Registry-`opus`)」與「Codex toml model pin」;實際 #164 已落地:.codex/agent_registry_v1.json 新增 model_routing_v1+saved_workflow_model_policy_v1(allow_inheritance:false),三 workflow admittedSavedWorkflowTierV1 caller 覆蓋即 throw(agent-wave.js:198/openclaw-full-audit.js:209/profit-diagnosis.js:206),22 toml model+effort 雙欄逐一驗證全符三級;ADR-0050 修正案已改寫為「executable binding 均已逐角色落地並由 validator 強制」。backlog 行與 ADR 現述矛盾。
- recommendation: 追認落帳時把該 row 兩項標記 DONE_BY_PR164(引 245869d25),避免重複派工;其餘項(WP-D delta 化、TODO L10 瘦身等)保留。

#### [low] cheapTier 死代碼空殼殘留於兩個 saved workflow(誤導性命名,行為 no-op),修復已在未併分支
- evidence: 245869d25 現檔 openclaw-full-audit.js:1426 與 profit-diagnosis.js:1212 各存 `const cheapTier = () => ({})` 及三處 `...cheapTier()` 展開點,均為 no-op(tier 已由 admittedSavedWorkflowTierV1 強制),但名稱暗示存在降級 tier 通道。刪除 commit cb1855240(2026-08-01 23:30)在分支 agent/fw2-wave-tier-binding-20260801 上,未併入 main。
- recommendation: merge 該分支(或 cherry-pick cb1855240)收口;衛生級,不阻追認。

#### [low] #164 開發過程含 9 輪連續 review reopen(§11 生效前歷史),其 shipped 機制本身符合批次收口——僅入帳存史,無需行動
- evidence: docs/agents/2026-07-30--gpt56-multi-agent-efficiency-remediation.md 記錄 Independent review reopen round 2..9(07-30~31,先於 §11 08-01 生效);對照 §11「同一 scope 連續 2 輪 FAIL 後升 PM 裁決」。但其交付機制無逐 finding 一刀:Full Audit findings 一律批次成 typed coverage_debt 進單一 fresh MAE-005 host phase(SKILL.md 已移除 estimated_fix_tokens/max_fixes/max_verification_calls 整組參數),dispatch protocol 明文「must not enter an automatic split/retry loop」,efficiency policy max_reopen_count_increase=0。
- recommendation: 追認記錄註明:9 輪歷史為 §11 政策動機的又一實證,#164 機制面 COMPATIBLE;無需修復動作。


## Lane safety

### Summary
PR#164 交易安全與邊界維度審計:無 critical。143 檔全數落在治理面(.codex/.claude/docs/helper_scripts/tests),零觸 rust/、app/、settings/risk_control_rules、sql/、program_code;live 5-gate/authority 邊界/fail-closed 條款零削弱(所有含安全 token 的刪除行皆為 role-memory compaction 搬遷,抽查守恆成立,archive record 有 sha256+byte 釘扎);ci.yml 僅在既有 pytest step 增列兩個測試檔(收緊),無新 job/required check/merge gate 變動;4 個 schema 全為收緊或零授權面(closure_packet 新增 9 個 bounded-execution 必填 cap 反無界迴圈、scheduler 鎖 const full、adaptive recall 鎖死 false;platform enum 擴為三值但 execution_policy 強制 generic_host advisory-only;liveness schema 鎖 automatic_stop=false;efficiency 兩 schema 零 effect/authority 欄位);fixture 誠實標注 synthetic 且明言不可支撐 adoption 主張。三級模型分級(#165-168 operator 裁決)在 registry/agent-wave/.codex TOML 三面逐角色吻合且由 validator 強制(ADR-0050「validator 強制」宣稱複核為真);agent-wave authorityProfiles 與 registry budget_envelopes 複算零偏差;全 PR 零測試斷言刪除;被移除的 js throw 全部搬遷且加強。實測:agent_governance validate+render --check PASS(20 roles);CI governance gate 本地跑 4115 passed/15 skipped/83 errors,83 errors 全在 11 個 *_disposable.py PG-cluster 套件(initdb fixture 在 Mac 沙箱失敗),該 11 檔零一在 #164 觸碰面=環境性非回歸。真問題在帳面:governance 政策正本 §13 仍記載 #164 分支「SUPERSEDED-KILL 不 merge、禁 recovery 遞迴」與現實(已 merge、經 recovery 分支)相反,且 §13 治理測試家族淨行數凍結被 #164 淨增 +9,264 行,追認帳面必須同步修正政策正本;另 adaptive_shadow 儀器被 full-only 取代(方向保守但記憶正本三處已 stale)。

### Stats
```json
{
 "files_in_pr": 143,
 "files_touching_trading_runtime": 0,
 "forbidden_dirs_touched": "rust/=0, app/=0, settings/=0, sql/=0, program_code/=0",
 "ci_yml_changes": "2 test files added to existing pytest step; 0 new jobs, 0 required-check/merge-gate changes",
 "new_schemas_reviewed": 4,
 "schema_authority_expansion": "platform enum widened to 3 values but generic_host forced advisory-only by execution_policy; net direction fail-closed",
 "test_asserts_deleted_in_pr": 0,
 "frozen_governance_test_family_net_lines": "+9264 (+9810/-546)",
 "model_tiering_vs_operator_decision": "exact match across registry/agent-wave/.codex TOMLs; validator-enforced (verified)",
 "agent_wave_authority_profiles_vs_registry": "0 mismatches (recomputed all 5 envelopes)",
 "local_verification": "agent_governance validate+render --check PASS (20 roles); pytest CI gate 4115 passed / 15 skipped / 83 errors in 20m36s",
 "error_adjudication": "83 errors all in 11 *_disposable.py PG-cluster suites failing at initdb fixture on Mac sandbox; 0 of those files touched by PR#164 (environmental, Linux-required)",
 "new_structure_test_files_run": "183 passed (efficiency/execution_policy/liveness/codex_memory_policy/role_memory_compaction)",
 "memory_compaction_conservation": "spot-checked TW+BB archived entries present in memory-archive.md; archive records sha256+byte pinned; .gitattributes -whitespace protects archive bytes",
 "critical_findings": 0,
 "high_findings": 1,
 "medium_findings": 1,
 "low_findings": 2
}
```

### Findings

#### [high][CONFIRMED] governance 政策正本 §13 與 merge 現實相反:SUPERSEDED-KILL 先例條款未隨 operator 改判修正,且淨行數凍結被本 PR 淨增 +9,264 行
- evidence: /Users/ncyu/Projects/TradeBot/srv/docs/agents/development-agent-governance.md §13「Meta-work 邊界」lines 977-979(merge 後現檔)仍記載:「2026-08-01 裁決先例:origin/agent/gpt56-multiagent-remediation-20260730(+27,988 行治理機測試)依本節裁 SUPERSEDED-KILL — 不 merge、分支保留存史、禁 recovery 遞迴」。現實:該分支已以 PR#164 merge(245869d25),且經由被明文禁止的 recovery 分支(commit b0d1faeb1 merge 訊息含 agent/gpt56-multiagent-remediation-recovery-20260801)。TODO.md §2 row 已改為 EXACT_HEAD_MERGE_AUTHORIZED(operator 授權),但其舊 row 引用的「政策正本=development-agent-governance.md Meta-work 邊界節」未修——normative_policy 與 active_work_state 兩類 authority 現互相矛盾。另 §13 lines 963-965 凍結條款(治理測試家族 test_agent_governance*+test_development_agent_governance* 淨行數不得再增,新增 gate 需同 change 內淨行數 ≤0)自 #169(f115a40e6,早於 #164 merge)後生效;git diff --numstat f115a40e6..245869d25 對凍結家族複算=+9,810/−546=淨 +9,264 行。lines 960-962 豁免條款(「該次 operator 批准的 remediation 批次含並行 lane 不追溯計入」)是否涵蓋 #164 語義不明,而先例 bullet 明文將其排除。
- recommendation: 追認帳面必列一筆 doc amendment:改寫 §13 先例 bullet 記錄 08-01 KILL→operator 改判追認 merge(含「仔細審核」條件與本審計結論指針),並顯式裁決凍結基線——建議 pin 至 245869d25 並明文 #164 豁免;否則凍結條款自 merge 日起即為 -9,264 行赤字的死條文,未來任何治理測試改動都機械性違規。

- 覆核 reason: 全部證據獨立復核成立。①docs/agents/development-agent-governance.md lines 977-979(merge 後現檔)仍逐字記載 gpt56 分支裁 SUPERSEDED-KILL/不 merge/禁 recovery 遞迴;該條款在 f115a40e6(#169)已存在(當時 lines 779-780),#164 雖改動同一檔 304 行卻未修此節。②commit b0d1faeb1 merge 訊息確含 agent/gpt56-multiagent-remediation-recovery-20260801,且 merge-base --is-ancestor 證實其在 245869d25 祖先鏈內、不在 f115a40e6 內——被禁的 recovery 分支確實隨 #164 入史。③TODO.md 現檔 line 344 = EXACT_HEAD_MERGE_AUTHORIZED,而 merge 前 line 343 舊 row 明指政策正本=governance doc Meta-work 邊界節,兩 authority 現互相矛盾。④量化復算精確吻合:git diff --numstat f115a40e6..245869d25 對凍結家族(test_agent_governance*+test_development_agent_governance*)=21 檔 +9,810/−546=淨 +9,264;凍結自 #169 merge(22:38)生效,#164 merge 於 22:51 在其後;豁免條款(lines 960-962)限於「該次」框架健檢批次,且同節先例 bullet 明文排除 gpt56 分支,故 −9,264 赤字定性成立。severity=high 恰當:屬政策正本與現實矛盾,非直接削弱交易 gate。

#### [medium] adaptive_shadow 量測儀器被 full-only 取代:方向保守但與 07-24 run0 裁決敘事及記憶正本三處相左
- evidence: schema:/Users/ncyu/Projects/TradeBot/srv/.codex/schemas/closure_packet_v1.schema.json $defs/fullAuditControl.scheduler 由 enum [full, adaptive_shadow, adaptive] 收成 const "full",adaptive_recall_approved const false、authority digest 鎖 null;runner:/Users/ncyu/Projects/TradeBot/srv/.claude/workflows/openclaw-full-audit.js lines 1367-1371 在首次 model call 前 throw EXTERNAL_LIMIT_RECALL_AUTHORITY;SKILL.md 改寫為「full 是唯一可執行 scheduler」。python 側 agent_governance_full_audit.py lines 447-495 保留三值分支但 482-495 一律拒絕 adaptive 授權=拒絕型冗餘,三層同向 fail-closed,執行覆蓋未縮(full ⊇ adaptive_shadow 的執行面)。但 07-24 run0 裁決(memory project_2026_07_11_ultracode_audit_remediation.md:「adaptive-only recall 不及格,adaptive_shadow 默認必須維持」「仍活:adaptive_shadow 默認不可退」;reference_ultracode_full_audit.md:「默認 report-only」)描述的 shadow 量測模式現已 schema-invalid——recall 量測儀器被退役,無替代基準路徑直至未來 PLATFORM_OR_EXTERNAL_ATTESTED recall adapter 存在。
- recommendation: 帳面記錄:非安全削弱(adaptive 縮減的解鎖門檻從 config 布林升為平台級 attestation,更難繞過),但屬對 07-24 裁決敘事的單方面再詮釋。同步更新 memory 兩個 topic 檔與 reference 配方行,標注「adaptive_shadow 已由 #164 退役、full-only、recall 量測 debt 掛 EXTERNAL_LIMIT adapter」,避免未來 session 按 stale 記憶配置 adaptive_shadow 而在首 call 前炸 EXTERNAL_LIMIT_RECALL_AUTHORITY。

#### [low] .codex/config.toml 平台級遞迴上限 max_depth=1 移除,深度防護改依 governed ledger(僅覆蓋受治理執行)
- evidence: /Users/ncyu/Projects/TradeBot/srv/.codex/config.toml diff:舊 [agents] max_threads=4/max_depth=1 → 新 enabled/max_concurrent_threads_per_session=3/default model 等,無 depth key。remediation 文檔 MAE-006(docs/agents/2026-07-30--gpt56-multi-agent-efficiency-remediation.md line 57)自述 max_depth 為「undocumented config folklore」,以 receipt-validated spawn-depth 取代;替代 enforcement 在 agent_governance_execution_policy.py lines 600-676(spawn_depth 逐 event 校驗)+ registry 全 envelope max_spawn_depth_from_root=1——但只綁 governed workflow 執行,原生未治理 Codex thread 僅餘並發上限 3 與 README prose(.codex/README.md line 13)。test_development_agent_governance.py lines 353-359 釘死新 config 形狀。
- recommendation: 在 runtime 主機驗證現裝 Codex 版本是否仍支援任何 depth 限制 key;若支援則恢復顯式平台級 cap 作為 governed-ledger 之外的第二道防線。若確認 key 已不存在則現狀可接受(folklore key 本無效力)。

#### [low] .codex 平台級 memory 抽取由關轉開(generate_memories=true):新的常設持久化面,有 policy probe 看守但屬 standing-config 行為變更
- evidence: /Users/ncyu/Projects/TradeBot/srv/.codex/config.toml 新增 [features] memories=true 與 [memories] generate_memories=true/use_memories=true/extract_model=consolidation_model=gpt-5.6-luna/disable_on_external_context=true(阻止 web/MCP/tool-search transcript 靜默成為持久記憶=反注入方向);inline 註釋聲明 PM 擁有 lesson eligibility、promotion 需 trusted-host attestation。看守:helper_scripts/maintenance_scripts/codex_memory_policy_probe.py(CONFIG_VALUES 逐鍵釘扎)+ tests/structure/test_codex_memory_policy.py(本地實跑 PASS,且已加入 ci.yml gate)。與既定「Per-role automatic report/memory growth is retired」政策的張力由 role-memory-compaction 標準(sha256+byte 守恆、48KB hot cap)承接。
- recommendation: 追認帳面明列此 standing-config 開關供 operator 知情;無需回滾,但建議在下次框架巡檢確認 Luna 抽取的實際記憶產物未繞過 PM promotion 關卡(現階段僅有 config 層與測試層保證,無 runtime 產物抽查)。


## Lane workflows

### Summary
PR#164 四個 .claude/workflows 檔改寫整體品質高、方向一致 fail-closed,查無 critical/high 問題。①四檔 node --check 全過,且 codegen 測試以 AsyncFunction 載入器實 parse 全過。②agent-wave.js 有界性完整存活:maxCallAttempts=maxUniqueNodes+retryBudget 前置強制仍在(L1001,另有 L1533 前置 reserve 檢查與 L1553 逐 call 檢查),五個 envelope profile 全部滿足該不變量(5=4+1/9=8+1/14=12+2/46=44+2/22=20+2),新 max_total_model_turns 亦符合 attempts+1(root)+max_followup_attempts 公式全五組吻合;新增 boundedParallelV1 依 max_concurrent_calls 有界併發(semaphore baton-passing 正確);caller model/effort 由 passthrough 改為 Registry saved_workflow_model_policy 強制(不符即 throw),逐 role 比對與 #166 operator 三級分級完全一致(T1 opus/high、T2 opus/low、T3 sonnet/medium),registry model_routing(gpt-5.6-*)屬 codex surface、與 claude surface 分治無衝突;pinned registryDigest sha256:22ac6a33… 與現行 load_registry()+registry_digest() 實算完全相等(merge 76432b8f8 已 reconcile),authorityProfiles 與 registry budget_envelopes、Python compile_execution_budget_policy() 逐欄位相等,三個 surface profile digest 與 Python surface_profile_binding() 相等。③openclaw-full-audit.js:adaptive_shadow 實質政策(run0「adaptive-only recall 不及格→full backstop 不可退」)完整保留且更強——full 為唯一可執行 scheduler,adaptive/adaptive_shadow/axes 子集一律 EXTERNAL_LIMIT_RECALL_AUTHORITY 先於首個 model call;shadow 量測(adaptive_selected_axes)仍計算、log、回傳(含 shadow_selected_axes 舊名);in-run verify/第三票/fix/review 全移為 MAE-005 host-phase 典型債,終態 null 軸改硬 abort;cheapTier 退役為 {}(Registry role tier 接管,cheap_model/judgment_model 等傳入即 throw,claim-0009 退役 pin 漂移根除);envelope 引用(full_audit/profit_diagnosis)與 registry 硬綁;ultracode-full-audit SKILL.md 已在 #164 merge 鏈內同步改寫(7957df240 absorb #169 修正),context_artifact 嵌入、admission_now_ms、surfaces 排除清單(runtime/pg/service/cron/deploy/bybit/ibkr)、新必填 route_required_roles、44/46/96000/4416000/2/3 數字全與 JS 及 registry 一致,配方未失真。④context-admission-v1.fragment.js 為 codegen 模板,render_context_admission_block() 產物與三個 runner 內嵌塊 exact 相等(測試強制);admission 全 fail-closed、所有迴圈有界、無新合法迴圈;operator_loop 需 /loop 前綴+digest 綁定且 specialized workflow 拒收。健檢 L4 context artifact 全量重發:#164 未解決亦未實質加劇——promptFor/contextPrefixV1 每 role call 仍重發完整 shared canonical,WP-D delta 化仍是 wave2 待辦;其 efficiency 敘事實指 finite budgets/history mode none+ephemeral fork(claude surface 標 enforced)/bounded scheduling/host 端 turns-waits-no-delta caps(對應健檢 loop 1/2/5,Python admit_execution_event 有實 enforcement),無 L4 虛稱,但追認記錄應注明 WP-D 仍欠。測試:codegen 5 passed、wave receipts+execution policy 75 passed、full-audit adversarial+profit control+trust bindings 74 passed、全 structure suite -x 241 passed(唯一 error=test_agent_governance_alr_quiesce_fence_disposable.py 需本機 PG initdb,Mac 環境限制非 #164 缺陷)。

### Stats
```json
{
 "files_audited": 4,
 "diff_lines_reviewed": 4711,
 "node_check_pass": 4,
 "registry_digest_match": true,
 "authority_profiles_match_registry": true,
 "model_policy_matches_operator_tiering": true,
 "bounded_retry_invariant_intact": true,
 "structure_tests_passed": 395,
 "structure_test_env_errors": 12,
 "critical_findings": 0,
 "high_findings": 0,
 "medium_findings": 3,
 "low_findings": 3
}
```

### Findings

#### [medium] scheduler='adaptive_shadow' 由默認值改為硬拒(舊配方呼叫將直接 throw)
- evidence: .claude/workflows/openclaw-full-audit.js L1342-1343 默認由 'adaptive_shadow' 改 'full';L1367-1371 scheduler!=='full' 或 axes 子集 → throw EXTERNAL_LIMIT_RECALL_AUTHORITY。實質政策(run0 裁決「full backstop 不可退」)保留且更強:full 全執行、adaptive-only 不可達、shadow 量測仍計算並回傳(L1650/L2096-2097 adaptive_selected_axes+shadow_selected_axes)。但任何沿用舊配方傳 scheduler:'adaptive_shadow' 的 dispatch 會在首個 model call 前硬失敗;memory(project_2026_07_11_ultracode_audit_remediation.md L37/L46「adaptive_shadow 默認必須維持」)字面已過時。SKILL.md L43-50 已同步記載新契約。
- recommendation: 追認記錄注明:政策實質(full backstop+shadow 量測)保留、僅 scheduler 命名語義收緊;更新 memory 兩處字面(adaptive_shadow 默認→full 唯一可執行、量測欄位改名 adaptive_selected_axes);PM 派發側檢查無殘留傳 'adaptive_shadow' 的腳本。

#### [medium] L4 context artifact 全量重發未解決(WP-D 仍欠),#164 efficiency 敘事不含此項
- evidence: agent-wave.js L1502-1504 promptFor 仍為 contextPrefixV1(=完整 shared_task_context_canonical+role delta)逐 role call 重發,full-audit/profit-diagnosis 的 boundPrompt 同構,與 pre-#164 相同;validateSemanticContextV1 仍要求每 role artifact 內嵌逐字 shared canonical。#164 微增每 artifact 位元組(shared canonical +registry_digest ~100B;plan +execution_dag_binding,14 節點約 2KB,admission 側非 model input)。commit 敘事(7e465ad12 等)宣稱 finite budgets/bounded scheduling/attested efficiency evaluation,未宣稱 L4 delta 化,無虛稱;真實效率貢獻在 history mode='none'+ephemeral fork(surface 標 enforced)與 host 端 caps。
- recommendation: 追認記錄明載:#164 與健檢 L4(90,639 tokens/role 重發)正交,WP-D context artifact delta 化(共享段 content-addressed 單發)仍是 wave2 待辦,不得因 #164 的 'efficiency' 字樣視為已修。

#### [medium] admitted_caps 新列時間類 caps 在 saved-workflow surface 無執行點(僅記錄)
- evidence: authorityProfiles 新增 max_wall_clock_ms/max_call_duration_ms/max_wave_duration_ms 等並經 executionCapsV1 全數寫入每個 wave record 的 budget_authority.admitted_caps(agent-wave.js L1817 附近、兩個 runner 同構),但三個 JS runner 無任何時間量測/中斷程式碼;surface profile 誠實標 call_deadline/wave_deadline='unavailable'。turns/waits/no-delta 類 caps 在 Python host 端有實 enforcement(agent_governance_execution_policy.py L802-825、L1202-1232 admit_execution_event),時間類 caps 於此 surface 為宣示性。
- recommendation: 視為已知邊界而非缺陷:admitted_caps 讀者(閉環審計/追認文書)應理解時間類欄位在 claude_saved_workflow surface 是政策記錄非執行保證;如需執行,屬未來 host adapter 工作。

#### [low] 新 fail-closed throw 之後遺留兩處不可達死碼
- evidence: agent-wave.js L1646-1652 blockedDependencyIndexes 非空即 throw,但 L1707-1711 仍將 blockedDependencyIndexes concat 進 retryCoverageDebt(不可達);profit-diagnosis.js L1441-1447 incompleteMandatoryEvidenceNodes 非空即 throw,但 L1450 addCoverageDebt('mandatory_evidence', …, 'missing after bounded infrastructure retry', …) 的 !evidenceResults[index] 分支不可達(L1451 status!==DONE 分支仍可達)。行為方向正確(拒發 wave record 比記債更保守),僅衛生問題。
- recommendation: 下次觸碰這兩檔時順手移除不可達分支並留一行中文注釋說明由 throw 取代;不值得單獨開 PR。

#### [low] cheapTier 降檔退役:evidence/seam 呼叫改按 Registry role tier,個別 call 成本方向上升
- evidence: pre-#164 cheapTier 默認 claude-sonnet-5/medium(openclaw-full-audit.js 舊 L795-798、profit-diagnosis.js 舊 L515-517);現兩檔 cheapTier=()=>({}) 且 cheap_model/cheap_effort/judgment_model/judgment_effort 傳入即 throw,invoke 內 admittedSavedWorkflowTierV1 強制 Registry tier。淨效果:profit-diagnosis evidence 段 MIT 由 sonnet/medium→opus/high、OPS/AI-E→opus/low,full-audit seam critic(CC)→opus/high。與 #166 operator 三級分級完全一致且根除 claim-0009 退役 pin 漂移,但屬成本上升方向的合規變化。
- recommendation: 無需修改(政策正本=feedback_model_effort_tiering,registry 為唯一權威);AI-E 月度成本回顧時將此列為 #164 已知成本方向變化即可。

#### [low] 結構測試環境殘項:ALR quiesce fence 測試檔在 Mac 無法執行
- evidence: tests/structure/test_agent_governance_alr_quiesce_fence_disposable.py 12 errors,全部為 /opt/homebrew/bin/initdb rc=1(需本機 PG),與 #164 workflows 改動無關;其餘針對性套件全綠:workflow_codegen 5 passed、wave_receipts+execution_policy 75 passed、full_audit_adversarial+profit_control+trust_bindings 74 passed、全 suite -x 241 passed。
- recommendation: 依既有規範以 Linux trade-core 跑 governed pytest 作最終回歸;本審計的 Mac 綠燈已覆蓋 #164 workflows 全部改動面。


## Lane machine

### Summary
machine 維度審計完成(絕對 read-only;中間物在 scratchpad/pr164-machine/)。①Mac plain pytest 實跑 #164 全部 23 個 tests/structure 測試檔:782 passed / 0 failed / 9 skipped / 0 error(192.8s);9 skips 全部來自 test_agent_governance_s2_host_kernel.py:1353 單一刻意 parametrized skip(exec-family-only 規則),非環境性跳過。②role memory compaction 是真的新子系統:對 18 個 docs/CCAgentWorkSpace/<ROLE>/memory.md 做可逆熱/冷壓縮(hot ≤300 行/48KiB、固定四 H2、禁日期/任務帳本;append-only archive+manifest v3)。實測 18 個 archive payload digest 與 f115a40e6 的 memory.md bytes 逐一相符 — 無損、且未吃掉任何 #165-169 期間的 memory 內容;熱記憶 1,547,913→41,904 B(−97.3%,ADR-0052 宣稱精確覆算 CONFIRMED)。方向與「per-role 自動 memory 增長已退役」政策同向(它就是該政策的執行機制),與 ~/.claude MEMORY.md R4 治理無 namespace 交集、無衝突。但 promotion 機制被自身 fail-closed 設計鎖死(見 finding 1)。test_codex_memory_policy 則把 .codex/config.toml 釘在 Codex host 自動 memory 生成 ON(gpt-5.6-luna、排除 external-context)— 與退役政策存在方向不對稱(finding 3)。③context 5 檔改寫與 WP-D delta 化同向:todo_active_rows 把 active_state 從整段 TODO(38,090 B/節點,TODO.md 全檔 108,691 B)投影成唯一 ACTIVE row+直接依賴(1,282 B,−96.6%);history_refs 把角色記憶/報告歷史從全目錄 inventory 改為 opt-in digest-bound 段(≤4 refs/32KiB)。同一 s2e 型 task facts、同一 7 節點 DAG(PM/PA/E1/E2/E4/TW/R4)雙樹實測:舊樹重複率 85.3% 重現 07-30 的 86% 基線(方法有效);新樹跨節點重複 shared bytes 501,492→279,852(−44.2%),shared block/節點 83,582→46,642 B,semantic_input_tokens/節點 20,957→11,722(−44.1%)。注意:重複「率」幾乎不變(85.0%),因 shared/delta 可快取分割在 #164 之前已存在 — #164 縮小重複面的體積,不改變複製結構。④agent_governance.py validate=PASS(20 roles,exit 0);render --check=PASS updated=[](exit 0);role_memory_compaction --check=PASS(18 roles)。無 critical:改動全域限於 development-agent 治理面,未觸交易安全 gate,新模組無 while-True/sleep 輪詢,fail-closed/EXTERNAL_LIMIT 紀律與 #165-169 精神一致。

### Stats
```json
{
 "pytest_quad": {
  "passed": 782,
  "failed": 0,
  "skipped": 9,
  "error": 0,
  "files": 23,
  "seconds": 192.76,
  "skip_source": "test_agent_governance_s2_host_kernel.py:1353 單一刻意 skip ×9 參數化"
 },
 "cli_checks": {
  "validate": "PASS roles=20 exit=0",
  "render_check": "PASS updated=[] exit=0",
  "role_memory_compaction_check": "PASS roles=18 exit=0"
 },
 "role_memory": {
  "roles": 18,
  "hot_bytes_before": 1547913,
  "hot_bytes_after": 41904,
  "reduction_pct": 97.3,
  "archive_vs_f115a40e6_mismatches": 0,
  "manifest_generation": 1,
  "promotions": 0
 },
 "context_dedup_s2e_7node_dag": {
  "roles": [
   "PM",
   "PA",
   "E1",
   "E2",
   "E4",
   "TW",
   "R4"
  ],
  "shared_bytes_per_node": {
   "old": 83582,
   "new": 46642
  },
  "todo_active_state_source_bytes": {
   "old": 38090,
   "new": 1282,
   "todo_file_bytes": 108691
  },
  "total_delivered_bytes": {
   "old": 587909,
   "new": 329329
  },
  "duplicated_shared_bytes": {
   "old": 501492,
   "new": 279852,
   "reduction_pct": 44.2
  },
  "duplication_ratio": {
   "old_reproduces_0730_baseline": 0.853,
   "new": 0.8498,
   "note": "shared/delta 可快取分割先於 #164;#164 縮體積不改結構"
  },
  "semantic_input_tokens_per_node": {
   "old": 20957,
   "new": 11722
  }
 },
 "adr0052_claims": {
  "role_memory_bytes": "CONFIRMED exact",
  "prompt_bytes": "delta/% CONFIRMED, baseline offset +40B 口徑差"
 },
 "scratchpad": "/private/tmp/claude-501/-Users-ncyu-Projects-TradeBot/1fb34c5e-f3ca-48e9-99a1-108451d4ebcc/scratchpad/pr164-machine/ (measure_context.py, old_result.json, new_result.json, comparison.json, pytest_tail.txt, old-srv clone)"
}
```

### Findings

#### [high][CONFIRMED] Role memory 被 CI 位元組凍結,promotion 唯一寫入路徑依賴不存在的 trusted-host verifier(死鎖)
- evidence: helper_scripts/maintenance_scripts/role_memory_compaction.py:1588 verify_manifest 以 active_sha256 釘死現行 memory.md bytes,並由 tests/structure/test_role_memory_compaction.py:1219-1230(CI 綁定於 .github/workflows/ci.yml:166)強制;1867-1875 對任何直接編輯 raise 'active memory drift after compaction';durable lessons 內容以常量寫死在工具內(1917-1921 ROLE_LESSONS);promotion 需 PROMOTION_TRUST_TIER='PLATFORM_OR_EXTERNAL_ATTESTED'(role_memory_compaction.py:25),standalone promote CLI 恆回 EXTERNAL_LIMIT(test:668);ADR-0052:298 自認 'future durable promotion remains blocked until a trusted host supplies its external-attestation verifier';manifest generation=1、promotions=0。effect:PM/operator 現在無法對任何角色新增一條 durable lesson,除非改工具+測試本身 — 超越了「退役『自動』增長」的政策範圍(策展式增長也被封死)
- recommendation: 追認帳面記明:role memory 目前為唯讀凍結態。修復清單加一項:建最小 trusted-host promotion verifier(或 operator-SSHSIG 級 attested override lane),否則第一次需要更新角色教訓時只能動 2,271 行工具原始碼

- 覆核 reason: 全部核心主張復現:(1) active_sha256 位元組釘死於 role_memory_compaction.py:1588-1589,read-only 實測對 PM/memory.md 模擬加一行即回報 'active compact memory digest mismatch' + 'render drift' 共 4 錯;(2) CI 綁定屬實——test_role_memory_compaction.py:1219-1230 對真 repo 斷言 verify_manifest==[],ci.yml ~162-166 執行該檔,且 tests/ci/test_github_ci_workflow_static.py:115 再鎖一層(CI 移除該測試本身會紅);兩關鍵測試在 HEAD 實跑 2 passed;(3) 1869-1875 'active memory drift after compaction' 兩分支確在;(4) durable lessons 確以 ROLE_LESSONS 常量寫死(定義在 170 行,非 finding 引的 1917-1921——該處僅 roster 檢查,引用行號小誤但實質成立);(5) CLI --promote 恆回 EXTERNAL_LIMIT/exit 2/零寫入(2201-2222,test:668-711 實跑通過),PROMOTION_TRUST_TIER=PLATFORM_OR_EXTERNAL_ATTESTED 在 25 行,全 repo grep 無任何 verifier 提供者;(6) ADR-0052 ~297-298 原句在;(7) manifest generation=1/promotions=0 實查相符;(8) 三檔皆不存在於 f115a40e6,確為 #164 range 引入。一項精度保留:「除非改工具+測試本身」略過強——測試未釘 lesson 內容毋須改,且 promote_durable_lesson 可被 import 並自供 verifier 機械繞過(測試套件自身即此模式且離線 verify 綠),但該路徑要求偽造 producer.kind∈{platform,external} 的 attestation 記錄,違反 repo 自身 'Do not fake lineage/evidence' 硬邊界,故所有『受認可』寫入路徑確實死鎖,與 ADR-0052 自認一致。修復建議(建最小 trusted-host/operator-attested verifier lane)正確且成本低於 finding 暗示——是薄 verifier,非重寫 2,271 行工具。severity=high 合理:凍結超出『退役自動增長』政策範圍,策展式增長一併封死,屬宣稱範圍與實作不符。

#### [medium] 7 個新 script 有 5 個未登記 SCRIPT_INDEX.md,違反 CLAUDE.md 明文規則
- evidence: grep -cF 實測 helper_scripts/SCRIPT_INDEX.md:role_memory_compaction.py=0、codex_memory_policy_probe.py=0、agent_governance_context_refs.py=0、agent_governance_liveness.py=0、agent_governance_efficiency_evaluation.py=0(僅 agent_governance_execution_dag.py 與 agent_governance_execution_policy.py 有登)。CLAUDE.md §七:'New scripts must update helper_scripts/SCRIPT_INDEX.md'
- recommendation: 修復清單:補 5 條 index 行(其中 role_memory_compaction.py 2,271 行、efficiency_evaluation 1,190 行是實質子系統,漏登會直接傷 R4 doc-cross-reference 巡檢)

#### [medium] test_codex_memory_policy 把 Codex host 自動 memory 生成釘死為 ON — 與「per-role 自動 memory 增長已退役」政策方向不對稱
- evidence: tests/structure/test_codex_memory_policy.py:24-35 assert .codex/config.toml features.memories=true 且 memories={generate_memories:true, use_memories:true, disable_on_external_context:true, extract/consolidation_model:'gpt-5.6-luna'}(#164 於 config.toml 新增該區塊,diff 已核)。這是 Codex host 層的自動記憶萃取通道,積累在 host state、不經 PM_CLOSURE promotion gate;若 operator 想關閉,structure test 會轉紅。緩解:disable_on_external_context=true 擋 web/MCP 注入,且不寫 repo 檔案、不觸 ~/.claude MEMORY.md namespace
- recommendation: 追認時 operator 明確表態:接受 Codex host 自動記憶(現狀)或要求改 test 讓 memories 可關。二擇一入帳,避免日後被當成默認政策

#### [medium] #164 全部新 Python 模組英文註釋,違反「新注釋只中文」現行規則
- evidence: 實測 6 個新模組(role_memory_compaction/codex_memory_policy_probe/efficiency_evaluation/execution_policy/liveness/context_refs)共 13 行 # 註釋、0 行中文;全部 docstring 英文。CLAUDE.md §七:'New or modified comments default to Chinese';對照同 repo 既有治理模組(如 agent_governance_routing.py SIDE_EFFECT_CLASSES 區塊)均為中文註釋
- recommendation: 不建議為此回頭改 8,000 行(churn>收益);入帳為已知一致性債,後續觸碰這些檔案時按規則逐步轉中文

#### [low] ADR-0052 prompt-bytes 宣稱基線與復算差固定 40 bytes(delta 與百分比正確)
- evidence: docs/adr/0052-gpt56-bounded-multi-agent-execution.md:294 宣稱 47,047→38,477(18.22%);對 .codex/agents/*.toml developer_instructions 欄位復算=47,007→38,437 — 兩端同差 40 bytes,削減量 8,570 bytes 與 18.22% 完全一致(量測邊界定義差,非虛報)。同檔 :296 role-memory 宣稱 1,547,913→41,904(97.29%)復算精確相符
- recommendation: 無需行動;帳面記為量測口徑footnote即可


## Lane claims

### Summary
PR#164 追認審計(read-only, main=245869d25):實質內容大體如宣稱——scope 乾淨(143 檔全為 governance/docs/tests/workflows,無 runtime/app/Rust/migration 觸碰;ci.yml 僅 +2 測試路徑)、8 項 MAE EXTERNAL_LIMIT 機制逐一驗真為 fail-closed 非變相放行(promotion 零突變 exit 2、wait/no-delta caps 終態化、liveness 一律 UNKNOWN+EXTERNAL_LIMIT、platform_token_cap 機器可檢、full-audit reduced mode 先拒後呼)、模型三級分級與 #165-169 operator 裁決逐角色完全一致且三個 saved workflows 已嵌 allow_inheritance:false 的 executable 綁定(反而提前交付了 wave2 兩項 QUEUED 待辦)、量化主張可復算者全中(baseline 恰 7 個 memory >300 行;round-9「65 passed」在 merge 後現檔精確重現;本地共 400+ 項 #164 範疇測試全綠;hosted CI 於 exact-head 7957df240 與 merge commit 245869d25 均綠;本地全套 5,364 收集、83 個 error 全數侷限於 *_disposable.py host/PG 家族=doc 自明排除的環境依賴)、抽查 5 個 commit 敘事與 diff 一致、efficiency 未宣稱任何未平台佐證的改善數字(動機表 telemetry 標 UNVERIFIABLE,A/B runner 拒 self-attestation)。但「宣稱 vs 現實」有兩處 high 級落差:①TODO 行「經 exact-head tests/review」不成立——最後 5 個 commit(含改 source 的 9822d9a2e)無任何 hosted review,merge(20:51:23Z)早於 exact-head governance CI 完成(21:12:26Z)21 分鐘,且 merge 前 2 小時 Codex 最後一條 P2(agent-wave.js BLOCKED predecessor 仍派發 successor)至今未修、未在 remediation doc 任何 round 中披露;②merge 後主幹留下互相矛盾的政策文本——development-agent-governance.md §13 仍載 gpt56 分支 SUPERSEDED-KILL/不 merge/禁 recovery 遞迴先例,而本 PR 正是經 recovery 分支完成並對凍結家族淨增 +9,264 行,§13 的豁免條款文字上不涵蓋 #164,凍結基線因此語義懸空(CLAUDE_CHANGELOG v865 已記錄改判但 §13 未 reconcile)。另 5 個新腳本漏登 SCRIPT_INDEX.md(違 CLAUDE.md 明文規則)。無 critical:未發現交易安全 gate 削弱、無界迴圈或政策執行機制破壞。追認帳面建議:記錄兩處 high 落差為 merge 條件缺口,修復清單=①§13 先例段補 supersession 注記+凍結基線顯式重錨;②agent-wave.js:1612 predicate 改為要求 predecessor work_status∈{DONE,DONE_WITH_CONCERNS};③SCRIPT_INDEX 補 5 條;④TODO wave2 backlog 清除已交付項。

### Stats
```json
{
 "pr_range": "f115a40e6..245869d25",
 "merge_commit": "245869d2530e941abdf3e7b1a03fe21348dbdf9a",
 "exact_head": "7957df2407f1aab66cbc45f27db59767c7bd0d5e",
 "files_changed": 143,
 "insertions": 33414,
 "deletions": 8064,
 "tests_dir_net_lines": 11136,
 "governance_test_family_net_lines": 9264,
 "mae_rows": {
  "total": 18,
  "done": 10,
  "external_limit": 8
 },
 "review_threads": {
  "total": 20,
  "resolved": 20,
  "human_reviews": 0,
  "codex_bot_reviews": 6,
  "review_body_findings": {
   "fixed_p1": 2,
   "unfixed_p2": 1
  }
 },
 "ci": {
  "head_checks_all_success": true,
  "merge_commit_main_ci_success": true,
  "merged_at": "2026-08-01T20:51:23Z",
  "governance_gate_completed_at": "2026-08-01T21:12:26Z",
  "merged_before_gate_completion": true
 },
 "local_test_runs_on_merged_head": {
  "execution_policy+liveness+trust": "92 passed",
  "context+full_audit+profit+codegen+wave": "134 passed",
  "memory_compaction+codex_policy+efficiency+dev_governance+ops_routing": "142 passed",
  "round9_two_files_claimed_65": "65 passed (exact)",
  "full_audit_adversarial": "33 passed (round-5 claimed 28, later rounds added)",
  "profit_control": "29 passed (exact vs round-4)",
  "collected_total_structure": 5364,
  "local_full_run_errors_at_37pct": "83, all in *_disposable.py host/PG family (environment-dependent, excluded by doc's non-disposable claim)"
 },
 "quantitative_claims_recomputed": {
  "seven_memories_over_300_lines_at_baseline": "7 exact (E1 892, E4 1055, E2 595, MIT 475, PM 443, PA 421, E3 335)",
  "session_token_motivation_table": "UNVERIFIABLE (platform telemetry)",
  "route_parity_129_46_fuzz_2707": "UNVERIFIABLE point-in-time; corpus-backed codegen parity test exists and passes",
  "efficiency_improvement_claims": "none made; A/B runner returns EXTERNAL_LIMIT_PLATFORM_ATTESTATION_UNVERIFIED without platform attestation"
 },
 "commit_narrative_samples_consistent": 5,
 "tier_mapping_vs_165_169": "exact match (registry 20 roles, 22 native profiles, 3 saved workflows)"
}
```

### Findings

#### [high][CONFIRMED] TODO 追認行「已完成並經 exact-head tests/review」與現實不符
- evidence: TODO.md:344 宣稱「經 exact-head tests/review」。現實:(a) GitHub PR#164 最後一次 hosted review(chatgpt-codex-connector)落在 commit b0d1faeb1(2026-08-01 18:36:46Z),其後 5 個 commit(1450702a3/76432b8f8/dc5abae91/9822d9a2e/7957df240,含改動 agent_governance_execution_policy.py 85 行的 9822d9a2e)無任何 review;(b) 該 18:36Z review 的 P2 finding「Stop successors when a predecessor is blocked」(agent-wave.js#L1611)在 merged head 未修(見另一 finding),且 remediation doc 九輪 review 記錄無一字披露;(c) merge 時刻 2026-08-01 20:51:23Z 早於 exact-head「development-agent governance (cheap static gate)」CI 完成時刻 21:12:26Z——merge 決策做在證據存在之前(事後全綠:head 7957df240 與 merge 245869d25 的 CI rollup 均 SUCCESS);doc 自身 L399 亦要求「hosted exact-head suite must rerun on the new commit before merge」。20 條 inline review threads 確全數 resolved,reviewDecision 為空(無人類 review)。
- recommendation: 追認帳面將 TODO row 措辭改為「exact-head CI 事後綠;final 5 commits 無 hosted review;1 條未處置 P2」;將該 P2 與 review 缺口列入修復清單而非默認閉合。

- 覆核 reason: 全部子主張經 GitHub API/git 復核成立:(a) 最後 hosted review=chatgpt-codex-connector 2026-08-01T18:36:46Z on b0d1faeb1,其後 5 commits(1450702a3/76432b8f8/dc5abae91/9822d9a2e/7957df240)零 review,9822d9a2e 確改 agent_governance_execution_policy.py 85 行(33+/52−);(b) 該 review P2「Stop successors when a predecessor is blocked」(agent-wave.js#L1611)在 merged head 未修——現檔 .claude/workflows/agent-wave.js:1612 仍僅檢 judgments!==null,BLOCKED/NEEDS_CONTEXT 判定照樣放行 successors,remediation doc 九輪記錄無一字提及;(c) mergedAt=20:51:23Z 早於 exact-head「development-agent governance (cheap static gate)」完成 21:12:26Z 約 21 分鐘(事後 head 7957df240 與 merge 245869d25 rollup 均全綠),doc 自身 :398 明文要求 exact-head suite 須在 merge 前重跑;(d) reviewDecision=空(無人類 review),20 inline threads 全 resolved 亦核實。TODO.md:344 措辭與上述事實不符。

#### [high][CONFIRMED] 主幹同時存有「SUPERSEDED-KILL/禁 recovery 遞迴」與「merge 已授權」兩套矛盾政策文本,治理測試凍結基線懸空
- evidence: docs/agents/development-agent-governance.md:975-977(§13 Meta-work 邊界)仍載:「2026-08-01 裁決先例:origin/agent/gpt56-multiagent-remediation-20260730(+27,988 行治理機測試)依本節裁 SUPERSEDED-KILL — 不 merge、分支保留存史、禁 recovery 遞迴」。而同一 merge 的 TODO.md:344 與 docs/CLAUDE_CHANGELOG.md(v865 增量,明文「取代 v864 的 SUPERSEDED-KILL/不 merge 裁決」)記錄 operator 改判;且本 PR 實際經 recovery 分支 agent/gpt56-multiagent-remediation-recovery-20260801 完成(b0d1faeb1 merge message),對 §13 凍結的 governance 測試家族淨增 +9,264 行(git diff --numstat 實測 +9810/−546)。§13:960-962 的生效豁免僅涵蓋「2026-08-01 框架健檢 remediation 批次」(#165-169),文字上不含 #164;§13 未加任何 supersession 注記。依 CLAUDE.md Typed Authority Matrix,normative_policy 類內衝突須顯式 reconcile,目前缺席。
- recommendation: 修復清單:①§13 先例段追加改判注記(日期+authority=operator 決策+指向 CLAUDE_CHANGELOG v865);②顯式重錨治理測試家族凍結基線(以 245869d25 為新零點或明文豁免 #164),否則下一個 governance-test PR 的合規判定無所依。

- 覆核 reason: 矛盾文本並存核實:docs/agents/development-agent-governance.md:977-979(finding 引 975-977,偏 2 行,內容同)仍載 SUPERSEDED-KILL 先例含「禁 recovery 遞迴」且全檔無任何改判/supersession 注記;docs/CLAUDE_CHANGELOG.md:8-11(v865)明文「取代 v864 的 SUPERSEDED-KILL/不 merge 裁決」;TODO.md:344=EXACT_HEAD_MERGE_AUTHORIZED;recovery 分支 agent/gpt56-multiagent-remediation-recovery-20260801 見 b0d1faeb1 merge message。量化復算:git diff f115a40e6..245869d25 --numstat 治理測試家族=+9,810/−546=淨 +9,264,與 finding 數字完全一致。§13:960-962 生效豁免文字僅及「2026-08-01 框架健檢 remediation 批次」,#164(GPT-5.6 remediation)不在其列;CLAUDE.md:79-86 Typed Authority Matrix+rule 7(:212-215)要求同 authority class 內衝突須 surface 並標 cleanup debt,現況缺席。凍結基線在 #164 淨增後確實無所依。

#### [medium] agent-wave.js BLOCKED/NEEDS_CONTEXT predecessor 仍派發 successor(merge 前 2 小時的 Codex P2,未修)
- evidence: .claude/workflows/agent-wave.js:1612 `const runnable = indexes.filter(index => tasks[index].requires.every(node => judgments[nodeIds.indexOf(node)] !== null))`——只驗 judgment 非 null;predecessor 返回合法 work_status='BLOCKED'/'NEEDS_CONTEXT' 時 successor 照樣 dequeue(E1 backend BLOCKED 後 E1a frontend writer 照跑,浪費 bounded budget 且 writer 可能產生部分編輯)。下游僅在 judgment 為 null 時擋(L1646 throw)與事後標 attention(L1695-1698)。predicate 在 f115a40e6:852 已存在(非 #164 引入),但 #164 重寫此檔 +866 行且 review 於本 PR 指出;損害被 budget caps 與 closure 失敗兜底,故非 critical。
- recommendation: 獨立小修:dequeue 條件改為 predecessor work_status ∈ {DONE, DONE_WITH_CONCERNS},BLOCKED/NEEDS_CONTEXT 的 successor 走 blockedDependencyIndexes 既有 coverage-debt 路徑;補一條 adversarial 測試。

#### [medium] 5 個新腳本未登記 helper_scripts/SCRIPT_INDEX.md,違反 CLAUDE.md 明文規則
- evidence: grep 實測 SCRIPT_INDEX.md 零命中:role_memory_compaction.py(2,271 行)、codex_memory_policy_probe.py(189 行)、agent_governance_efficiency_evaluation.py(1,190 行)、agent_governance_liveness.py(237 行)、agent_governance_context_refs.py(249 行)。同 PR 新增的 agent_governance_execution_dag.py 與 execution_policy.py 有登記,證明作者知悉規則但漏了五條。CLAUDE.md §七:「New scripts must update helper_scripts/SCRIPT_INDEX.md」。
- recommendation: 補 5 條 index 行(一行式功能描述,依現有格式);可併入 §13 reconcile 同一 doc-only PR。

#### [low] 8 項 EXTERNAL_LIMIT 中 6 項的 typed 名稱僅存在於 doc ledger,代碼側為泛型 EXTERNAL_LIMIT+能力記錄
- evidence: 全 repo grep:EXTERNAL_LIMIT_HOST_DURATION_TOKEN/CODEX_HISTORY_ATTESTATION/HOST_WAIT_CANCEL/MEMORY_PROMOTION_ATTESTATION/HOST_DEADLINE_CANCEL/HOST_ACTIVITY_ADAPTER 六個識別子在 helper_scripts/tests/.claude/.codex 零命中;僅 EXTERNAL_LIMIT_RECALL_AUTHORITY(registry py/JS/tests/skill)與 EXTERNAL_LIMIT_PLATFORM_ATTESTATION_UNVERIFIED(efficiency_evaluation.py:1098)為真代碼 token。機制本身逐項驗真為 fail-closed:execution_policy.py:331-335 platform_token_cap 須精確等於 {status:EXTERNAL_LIMIT,...} 否則 registry 驗證失敗;role_memory_compaction.py:2202-2221 --promote 恆返 mutation_applied:False+exit 2;liveness.py:217 恆 EXTERNAL_LIMIT;wait/no-delta 超 cap 返 *_BUDGET_EXHAUSTED 終態(execution_policy.py:1226-1247)。故為命名層 doc-code drift,非變相放行。
- recommendation: 無需改碼;追認帳面注明「typed」指 doc-ledger 狀態標籤+機器可檢能力記錄,避免後續審計誤判為缺陷或誤信 6 個 token 可 grep 追蹤。

#### [low] TODO wave2 backlog 仍將 #164 已交付項列為 QUEUED(重複派發風險)
- evidence: TODO.md P2-FW-WAVE2-FRAMEWORK-OPT-BACKLOG 行仍列「agent-wave saved-workflow tier 綁定(禁向下覆蓋 Registry-opus)」與「Codex toml model pin」為待辦;實際 #164 已交付:三個 saved workflows 均嵌 saved_workflow_model_policy_v1(allow_inheritance:false+逐角色 model/effort map,agent-wave.js:147/185-200、profit-diagnosis.js:155、openclaw-full-audit.js:158)且 .codex/agents/*.toml 已釘 model(PM=gpt-5.6-sol/high、TW=gpt-5.6-terra/medium),SUBAGENT_EXECUTION_RULES.md 與 ADR-0050 修訂亦確認「均已逐角色落地並由 validator 強制」。
- recommendation: 從 backlog row 劃掉這兩項(標注 delivered-by-PR#164),防止重複 carve 派工。
