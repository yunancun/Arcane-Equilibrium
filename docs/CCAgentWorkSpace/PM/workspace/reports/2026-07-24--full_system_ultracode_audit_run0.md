# 2026-07-24 全系統 ultracode 對抗審計(run 0)

**Workflow**:`openclaw-full-audit`(run `wf_749b4f8c-2ea`,`adaptive_shadow`,report-only `fix=false`)
**凍結身份**:source=main `7d78765a251dc19997dae48b5591b3f1a591d3aa`(= origin/main,PR#114 merge)|dirty=`memory/reference_pr_merge_gates.md` 1 檔(`sha256:6c65171f…ae3c952`)|untracked=空(`sha256:4f53cda1…202b945`)|runtime=trade-core 同 head,觀測 `2026-07-24T00:24:34Z`(api service active、engine running)
**Context artifact**:`sha256:9941ee33…f62e838`|task contract `sha256:774eef20…fd55760`|budget authority `sha256:07d2d436…3575370`(full_audit:44 nodes/46 attempts/retry 2)
**同目錄佐證**:`2026-07-24--full_system_ultracode_audit_run0.decision_view.json`(全 claims/seams/92 條 coverage debt/manifest+wave digests)

## 0. 執行摘要

13 軸 backstop 全數完成(45 calls=43 首攻+2 重試,`final_null_node_count=0`;audit:E3 與 audit:IB 首攻死於 API server error,retry budget 恰好吸收)。130 raw findings → 16 decision claims → 14 admitted(2 deferred)→ **9 CONFIRMED / 1 LATENT-HIGH / 3 DISPUTED / 1 REFUTED**;5 條跨軸 seam;92 條 assumption 全數入帳;`pass_eligible=false`(顯式 debt,按設計誠實)。平台側觀測消耗 5.06M subagent tokens / 1110 tool calls / 37.6 分鐘。

**兩個最高優先信號**:
1. **S1 formal-closure 效果縫的已知 P1 修復仍未併 main**(claim-0002 LATENT-HIGH + claim-0005 DISPUTED-HIGH):fix 只活在 `agent/aiml-s1-closure-p1p2-fixes`。在該支併入前,main 上的 S1 closure 證據鏈不應被 operator SSHSIG 簽署。這直接壓在 TODO 既定的「S1 三端同步」下一步上——順序必須是 fixes 併入 → 再簽。
2. **Adaptive 子集這輪會漏 44% confirmed**:claim-0004(BB)、0006(OPS)、0007/0008(QC)全部來自 shadow 子集(CC/FA/E2/E3/MIT/AI-E/A3/R4)之外的軸。`adaptive` 模式的 recall benchmark 以此輪計 **不及格**,`adaptive_shadow` 默認必須維持。

## 1. CONFIRMED(9;按嚴重度)

| # | 軸 | 嚴重度 | 錨 | 一句話 | fix 方向 |
|---|---|---|---|---|---|
| claim-0009 | AI-E | HIGH | `.claude/workflows/openclaw-full-audit.js` `strongJudgmentTier()` | 強裁決層 pin 已退役模型 `claude-opus-4-6`,與 repo pricing 權威矛盾(本輪部分 verify 呼叫實際跑在該 pin 上) | tier 默認改由 `settings/ai_pricing.yaml` active 條目/Registry model map 派生 |
| claim-0015 | R4 | HIGH | `TODO.md` L4-5/12/51-56/129/215 | active-state 權威落後 3 個已 merge PR:仍命令「push→PR→merge」已併入的 S1 branch | 單一 writer task 刷新 banner/看板/P0-AIML row/自檢至 post-PR#114 真相 |
| claim-0004 | BB | MEDIUM | `rust/…/event_consumer/dispatch_retcode.rs`+`bybit_rest_client.rs:984` | retCode 110003/110049 有分類器但零消費者,無 force-refresh 恢復;INSTR-ENSURE-FORCE-1 自 2026-04-23 懸置,cache 只 4h 刷新 | OrderManager submit wrapper 接 `ensure_symbol_force` → re-round → 單次重試 |
| claim-0006 | OPS | MEDIUM | `docs/execution_plan/ai_ml_landing/receipts/S1-…run-record.md` | 宣稱的 trade-core 效果證物在 head 只有 digest,bytes 不在 repo(不可本地重驗) | 落地 artifact JSON(fix branch 已做)再綁 operator SSHSIG |
| claim-0007 | QC | MEDIUM | `rust/…/intent_processor/gates.rs:145/448` | PROFIT-1 現況重確認:net-of-fee edge 對 fee 門檻牆,demo+live 雙路徑仍雙重扣成本 | 提交 operator 顯式再裁決(gross vs 牆、或 net vs 殘差 margin),不做默改 |
| claim-0008 | QC | MEDIUM | `program_code/learning_engine/dsr_gate.py:227-254` | DSR 偏離 Bailey-LdP Eq.8:E[max SR_k] 缺 √Var(SR_k) 縮放,per-trade Sharpe 輸入下 K≥2 幾乎必 block(over-gate,壓死 promotion) | 按 Eq.8 以 cross-trial SR 標準差縮放,並正規化輸入時間尺度 |
| claim-0010 | AI-E | MEDIUM | workflow `thirdVoteReserve`(L927/964-968) | 全局唯一第三票 reserve:每輪至多 1 條 high-risk claim 能拿到第三裁決 | 第三票按 claim 風險條件化,於剩餘容量內動態分配 |
| claim-0011 | AI-E | MEDIUM | workflow L1184 | Regression phase 不可達死碼(`integration_status` 恆為 `NOT_INTEGRATED`),其 reserve 在 fix-run 擠占一條可驗證 claim | 移除 in-run regression reserve 或以真實 integration 狀態 gate 它 |
| claim-0012 | AI-E | MEDIUM | `agent_governance_closure_quality.py` | `closure_quality_followup_v1` 全 repo 零實例:cost-per-durable-closure 沒有分母,無 producer/cron/CI 任何一處生成 | PM closure/Report Sink 每 durable closure 排一筆 follow-up 入 canonical ledger |

## 2. LATENT / DISPUTED / REFUTED

- **claim-0002(LATENT,HIGH,E3/E2 系)**:main 帶著 PR#114/PR#115 review 已確認的 S1 效果縫 P1 缺陷(`agent_governance_target_host_apply.py` 家族:父進程 `os.environ["AIML_TARGET_HOST_PROBE"]="1"` 直寫等);修復只在 `agent/aiml-s1-closure-p1p2-fixes`。E3 第三裁決判 reachable=**latent**(非即時可達,但簽署前必須收口)。**行動=先併 fix branch 再談任何 S1 簽署。**
- **claim-0005(DISPUTED,HIGH)**:同一事實面,verifier 對「是否構成 head 級 HIGH」存異議(與 0002 之差在 impact 框架)。異議按治理保留,不降級不合併。
- **claim-0003(DISPUTED,MEDIUM)**:S1 exit「current, verifiable receipt」在 main 無 repo-resident 證據可驗;異議點=receipt 刻意 disposable 是否即為缺陷。與 claim-0006 同族,行動同上(落 JSON+digest pin)。
- **claim-0013(DISPUTED,MEDIUM)**:`agent_governance_component_effects.py` 1941 行距 2000 硬閘 59 行;事實全確認,異議在「距離閘 59 行」是否構成當下 defect。S2 writer 動它之前先分割即可。
- **claim-0001(REFUTED,MEDIUM)**:run record 的 `PLATFORM_OR_EXTERNAL_ATTESTED` 標籤——事實引用全部核實,但兩位 verifier 一致認定文件自身已明示 SSHSIG pending,「下游會誤讀」的 impact 不成立。按治理記 refuted,原始 claim 與 dissent 均保留於 decision view。

## 3. 跨軸 seam(5)

1. **S1 attestation 縫三軸同源**:CC(SSHSIG pending)×E2(non-replayable structural_reference_only)×OPS(Linux attestation OWED 不被 pytest-only CI 抵扣)→ 同一根因=效果證據鏈在 operator 簽署前全是 ORCHESTRATOR_BOUND。收口點只有一個:fix branch 併入+SSHSIG。
2. **成本模型雙缺陷同一血管**:BB D2(fill-sim taker fee 只建到真實 5.5bps/leg 表的一半)× QC PROFIT-1(gate 雙扣)→ 兩者都汙染 promotion/edge-viability 判斷,一個偏鬆一個偏緊;必須同一輪 operator 裁決,不可各修各的。
3. **Promotion 統計功效**:QC(DSR Eq.8 缺縮放、CPCV 非真 combinatorial、ad-hoc power 公式)× MIT(ship-gate 在 n_test≈26 下功效極低)→ gate 鏈的統計學需要一次 QC+MIT 聯合重推導。
4. **DSN split-string 規避掃描器**:MIT 與 OPS 各自獨立發現 ML persistence fallback 與 `restart_all.sh` 記錄的同構手法(拆字串繞 credential scanner)→ E3 family 追蹤:確認是防呆繞行還是真實洩漏面。
5. **Active-state 家族性 stale**:CC/FA/E2/OPS/MIT/E5/R4 七軸各自撞見 TODO/PROGRESS/initiative_index 落後 merge 事實,但無一軸查了 E5 單獨提出的「Registry active_state pack 只 pin 看板 selector」——修 TODO 時一併驗 pack selector 仍解析。

## 4. Coverage debt(92 條入帳;重點 8 條)

- runtime 家族(engine/watchdog/PG/cron 實態)與 Bybit/IBKR 官方政策新鮮度:**契約排除**(本地無法 attest),只有 head 身份 pin 被承認;深訪=永久 debt 直到 governed Linux capture。
- PROFIT-1 已由本輪 QC 用代碼重確認(claim-0007),但 SCHEMA-1(column contract test 缺無)未重查。
- Rust 五閘 live 授權只做指紋級存在證明,未做逐 spawn path 全量重推導(歷史 06-14 runtime 實證 + 07-06 AUTH-1 修復作 claim_inputs 級承接)。
- GUI 93 寫入面只抽樣 2 個風險代表端點。
- S1 各 session role-chain PASS 建立在 disposable receipt 上,本 head 不可重驗(=claim-0006 同源)。
- PR#112-114 的 Linux CI 綠與 GitHub check runs 為外部平台事實,本輪無 GitHub 工具admission,不推斷為綠。
- repo 父目錄(`/Users/ncyu/Projects/TradeBot/`)散落的 p0_*.json 任務工件與 `GITHUB_SUPPORT_SECRET_PURGE_REQUEST.md` 未做秘密掃描(在 scope root 之外)——值得一次 E3 順手清掃。
- E3 深訪與 IB 深訪各經 1 次 API 重試完成,無殘缺;但兩軸重試消耗了全部 retry budget,後續任何軸再失敗即斷,屬本輪運氣邊界。

## 5. 派發側工程事實(PM 披露)

1. **Canonical workflow 在現行 desktop Workflow 沙箱不可執行**:沙箱無 `crypto.subtle`、無 `TextEncoder`、`Date.now()/new Date()` runtime 拋錯(探針實證)。`openclaw-full-audit.js` 與 `agent-wave.js` 的 admission 硬依賴三者——**即所有 saved 治理 workflow 目前原樣必死**。本輪以派發側 shim runner 執行:純 JS UTF-8+SHA-256(FIPS 180-4,test vectors 含中文/emoji/raw-bytes 全過)注入 `globalThis`,admission 時鐘按 harness 官方建議改由 `args.admission_now_ms` 傳入,call record 的 started/ended 戳以 admission 戳確定性替代;**驗證邏輯 0 改動,全部 digest 檢查原樣執行且全過**。shim runner 與 probe 留存於 session scratchpad;修法應上游化(workflow 檔內建 fallback shim),與 claim-0009/0010/0011 併一個 workflow 維護包。
2. **bybit/ibkr surface 自 task contract 摘除**:broker pack 的 external_policy_snapshot 本地只能到 `available_unattested_evidence`(→blocking)或 `resolve_on_demand`(→evidence_debt),而 admission 要求 debt 全空,結構上不可能帶著這兩個 surface 過閘。BB/IB 軸仍在 backstop 全量執行(自帶 WebSearch 查官方政策)。此為 registry 設計與 workflow admission 的縫,已按 debt 入帳。
3. closure_packet_v1 之 PM 彙編:workflow 已產 hash-bound 之 `full_audit_control_v1`/fragments/admissions/wave record,全部原樣持久化於 decision view+session 存檔;獨立 packet 彙編與 CLI 結構驗證列為 **owed**(標準 CLI 本就不能 authenticate PASS,且本輪 `pass_eligible=false` 無 PASS 可宣)。

## 6. 建議行動佇列

| 優先 | 行動 | 承接 |
|---|---|---|
| P0 | `agent/aiml-s1-closure-p1p2-fixes` 完成自身 review 後 exact-head 併入 main;**在此之前不做任何 S1 SSHSIG 簽署**;隨後補 Linux CI attestation | claim-0002/0005/0006/0003+seam-1 |
| P0 | TODO.md banner 單 writer 刷新至 post-PR#114 真相(含 Registry active_state pack selector 驗證) | claim-0015+seam-5 |
| P1 | Workflow 維護包:model pin 改 pricing 派生+第三票風險條件化+regression 死碼裁決+沙箱相容 shim 上游化 | claim-0009/0010/0011+§5.1 |
| P1 | 成本模型聯裁:PROFIT-1(雙扣)與 fill-sim fee(半價)一次提交 operator 裁決 | claim-0007+seam-2 |
| P1 | DSR gate 按 Eq.8 補 √Var(SR_k) 縮放+QC/MIT 聯合重推導 promotion 統計鏈 | claim-0008+seam-3 |
| P2 | Bybit 110003/110049 force-refresh 接線(INSTR-ENSURE-FORCE-1 收口) | claim-0004 |
| P2 | closure-quality ledger 接 producer(給 cost-per-durable-closure 一個分母) | claim-0012 |
| P2 | DSN split-string 手法 E3 追蹤;repo 父目錄散件秘密掃描 | seam-4+debt |
| P2 | `component_effects.py` 分割(S2 動它之前) | claim-0013 |

## 7. 證據錨

- run:`wf_749b4f8c-2ea`|workflow_contract_digest、call_manifest_digest、wave record digest 見 decision view
- 平台側觀測:45 agents/5,062,344 subagent tokens/1,110 tool calls/2,258s;in-script 記帳為 planned lower bound(consumption=partial,per 治理不偽造 actual)
- 全量 1.5MB `full_audit_result_v3` 與各軸 fragment 原文:session 存檔(`subagents/workflows/wf_749b4f8c-2ea/journal.jsonl`);decision view 為其無損裁決投影
