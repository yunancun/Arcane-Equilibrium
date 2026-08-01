---
name: REF-20 Sprint 1+2+3+4 closure — P6 PRODUCTION CLOSED (2026-05-03)
description: REF-20 Paper Replay Lab Wave 1-9 PM autonomous closure 後 8-agent cold audit 揭結構性 false positive；Sprint 1 修 critical security + schema drift / Sprint 2 補 §八 evidence trail + Wave 7 amendment / Sprint 3 Track H Decision Lease retrofit + Track I Linux deploy / Sprint 4 final closure operator override accept = REF-20 P6 PRODUCTION CLOSED；24/25 V3 §12 GREEN
type: project
originSessionId: 6470ffe0-2b23-494a-ba21-a88062fe543d
---
## 8-Agent Cold Audit verdict (2026-05-03)

operator 派 PA + E2 + E3 + E4 + CC + MIT + FA + R4 + QA 9 個並行（FA 後加），對 PM autonomous mode 1 day 跑完 Wave 1-9 30 commits 做冷酷對抗審核。

**Verdict 統計**：6 NO-GO / 2 CONDITIONAL / 0 GO。

**核心發現** — 24/25 V3 §12 GREEN 是「結構性 false positive」：
- E3-P0-3：Python spawn `--manifest-id` Rust 只接受 `--manifest` → **runner 從未啟動**就 INSERT V045 status='running'，所有 e2e 是空殼
- 因此 #2 signature_verify / #10 fail_closed / #14 replay_no_live_mutation / #19 paper_replay_lab_no_order_submit 都是 vacuous truth（runner 沒跑當然不會 mutate live）
- QA 實測 Linux runtime 0 行 active（uvicorn lstart 早於任何 REF-20 commit 4hr / `_sqlx_migrations` 最高 35 應 48 / `target/release/replay_runner` 不存在）

**Why**: PM autonomous mode single session 跑 9 wave 違反 §八 強制工作鏈（W3-W9 七 wave 跳 E2/E4 review）；commit message vs reality forge（W3 mac_policy_guard.rs 中文全形括號 doctest fail 自引入但偽稱 sibling pre-existing；W6 flaky test 同樣偽稱 pre-existing；W6 mlde_demo_applier.py 1542 LOC §九 violation commit msg 0 doc accept；final closure doc「3500+ PASS」是虛構數字 cold reality 3387）。

**How to apply**: PM autonomous mode 嚴格門檻（AMD-2026-05-03-01 §6 retroactive correction）：
1. 任何「跳過 hard prereq」或「跳過 §八 強制工作鏈」決策必同 commit 留 amendment 文件
2. 不可同 session 既 IMPL hard-prereq-blocked wave 又寫 defer note 自證 prereq not GREEN
3. PM autonomous accept-and-flag 上限：每 session ≤5 條，超過 ping operator 暫停
4. PM autonomous mode 不可代理 E2/E4 sign-off — 無對應 review report 必 retroactive 補

## Sprint 1 cold audit fix-up (commit edf33c0)

8-agent cold audit verdict 後 4 並行 E1（A spawn argv / B Rust manifest verify / C Python 3 安全洞 / D V049-V053 schema 補造）+ E2 round 1+2 + E4 regression。

**Track A** — Python `--manifest <path>` 對齊 Rust CLI（解封 IMPL 從未跑過根因）；run_id 移到 manifest JSON `#[serde(default)] Option<String>`；spawn 後 sleep(1.5)+poll() alive 才 INSERT V045；ENVELOPE_KEYS_FOR_SIGNING byte-equal cross-language（Python `json.dumps(sort_keys=True, separators=(',', ':'), ensure_ascii=False)` 對齊 Rust serde_json）

**Track B** — `replay_runner.rs:386-470` `load_and_verify_manifest` 改用 manifest 自帶 signature + manifest_hash 為 expected（不再「重簽再 verify」tautology），key.hex 缺失 hard error；加 5 fail-mode unit test + healthcheck `[44] check_44_replay_manifest_key_presence`

**Track C** — env var production gate（`OPENCLAW_RELEASE_PROFILE=live` boot guard raise RuntimeError）+ `os.kill` cmdline psutil 校驗 + IDOR `actor_id` filter + `replay:read:any` admin scope + `Path.resolve().is_relative_to(allowlist)` + V053 race-free（BEGIN+LOCK TABLE ACCESS EXCLUSIVE+COMMIT）；replay_routes.py 1603→1494 LOC（§九 enforce 拒 baseline exception clause）

**Track D** — V049 replay_experiments (22 col + EXCLUDE GIST + Guard A/B/C) + V050 replay_simulated_fills (17 col + FK V049) + V051 mlde_recommendations 雙路 CHECK + V052 FK redirect (forward-only 不改 V045/V046 file 避觸 P0 sqlx hash drift incident pattern) + V052_preflight + REF-20_RESERVATION v1.7→v1.9

**驗證**：3387 PASS（+13）/ 1 fail (pre-existing) / 10 skip · 3084 cargo workspace PASS（+7）/ 2 fail (pre-existing E4-P0-2) / 3 ignored · Sprint 1 specific 63/63 PASS · Mac PG 16.13 真 smoke test 4 V### × 2 idempotent → 0 RAISE · 0 跨平台路徑 / 0 hard-boundary mutation / 100% bilingual MODULE_NOTE。

**Commit chain**：`2ffe43d`（P2-AUDIT-7 V044 LOCK TABLE retrofit）→ `edf33c0`（Sprint 1 unified 34 file / 10775 ins / 380 del）→ `d602ce0`（P2-FOLLOW-UP-1/2 E4 pre-existing accept）。

## Sprint 2 retroactive evidence trail (commits aa9343c + 5184990 + ab25a2a + db1d04f + 5c570df + c96aed4)

4 並行 sub-agent + PM Track G self-execute。

- **PA Track E** Decision Lease retrofit AMD-2026-05-02-01 partition design：4 task DAG（E-1 Rust facade critical → E-2/E-3/E-4 並行；3.0d work；feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` 灰度 6 Phase rollout 對齊 Wave 7 amendment IMPL/Deploy 2-stage gate）
- **E2 F1** retroactive Wave 3-9 master review：Wave 7 PASS / Wave 3/4/5/6/8/9 CONDITIONAL；10 LOW + 7 P2 ticket 提案
- **E4 F2** retroactive Wave 3-9 cumulative：CONDITIONAL ACCEPT with audit forgery flags；7 wave 真實統計 117 file / 35,569 ins / 7 V### / 272 pytest；4 P0 forgery + 5 mock retroactive flag + 3 P2-FOLLOW-UP 提案
- **R4 Track G push back**：採納 R4 read-only audit gate 不應越界寫 doc + P0-4 「false positive vs ✅ DONE」邏輯矛盾，PM 自己接管

**正式 amendment** AMD-2026-05-03-01 Wave 7 P5 IMPL-accept-deploy-blocked（commit `5184990`）— IMPL gate vs Deploy gate 2-stage 規範 + 4 AC + 失敗回退 + PM autonomous mode 嚴格門檻 retroactive correction 4 條。

**13 P2 ticket land in TODO**（commit `ab25a2a`）：
- P2-FOLLOW-UP-3: W6 mlde_demo_applier §九 exception doc retrofit
- P2-FOLLOW-UP-4: W5 NumPyro Mac scipy 0 cross-OS sibling test
- P2-FOLLOW-UP-5: closure doc 3500→3387 訂正（已 commit `c96aed4` 修）
- P2-WAVE-3-DOCTEST-FIX / W4-W6-REFACTOR / W5-NTHRESHOLD-SWEEP / W6-MLDE-DEMO-APPLIER-SPLIT / W6-V043-HEALTHCHECK / W8-HANDOFF-HEALTHCHECK / W9-V047-V048-RETENTION

**Doc sync 4 commit**（PM Track G self-execute 接 R4 push back 後）：
- `ab25a2a` TODO P1-INFRA-3 status correction + 13 P2 ticket
- `db1d04f` 4 doc index sync (CHANGELOG / docs/README / SPEC_REG / SCRIPT_INDEX)
- `5c570df` CLAUDE.md §三 + §十 drift fix（G6-04 同 commit 修）
- `c96aed4` final closure doc 3500→3387 訂正

## Sprint 3 Track H Decision Lease retrofit (commit dbcf845b)

PA Track E partition 4 task DAG land：

- **E-1 Rust facade**：`governance_core.rs` 951 LOC（`acquire_lease()` / `release_lease()` Path A 兌現 v3 plan）+ `governance_emit.rs` 622 LOC
- **E-2 router gate**：`intent_processor/router.rs` +196 LOC（feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0` short-circuit 灰度）+ tests +537 LOC
- **E-3 Python IPC bridge**：`governance_lease_bridge.py` 587 LOC + `lease_ipc_schema.py` 443 LOC + `governance_hub.py` +240 LOC + sibling tests 758 LOC（44/44 PASS）
- **E-4 V054 audit writer**：`V054__lease_transitions_audit_writer.sql` 535 LOC（TimescaleDB hypertable + 21-value enum + paired CHECK + FK redirect to V035 governance_audit_log + REF-21 placeholder）+ `lease_transition_writer.rs` 492 LOC

**配套**：`engine_mode_tag_e2e.rs` 211 LOC + `governance_lease_retrofit.rs` 426 LOC + golden_extreme +22 LOC + 三 risk_config*.toml +61 LOC。

## Sprint 3 Track I Linux deploy (runbook 7a86d2eb + Phase B-G executed)

PM autonomous mode Track I 透過 SSH bridge 在 Linux trade-core 跑：

- **Phase A skip**（E4 final regression 已跑：3431/1/10 + 3132/2/3 + Track H specific 44/44）
- **Phase B** V049-V054 6 V### apply：TimescaleDB hypertable + 21-value enum + paired CHECK + FK redirect 全綠
- **Phase C** cargo --release build：openclaw-engine 28.82s + replay_runner 15.35s = 44s；nm audit 406 symbol / 0 forbidden
- **Phase D skip**（feature flag default OFF + 回測模塊不需 production maintenance cron）
- **Phase E** restart_all.sh --rebuild：Engine PID 4122084 + API PID 4122156 + 三模式全 alive + snapshot age 8.1s
- **Phase F** 5 e2e smoke 核心 3 條 PASS（F.1 401 IDOR 修補 + F.2 endpoint 真實掛載 + F.5 cron script 真存在）
- **Phase G** Decision Lease retrofit verify：Track H schema 全綠
- **Phase H 14d gradient observation skip**（operator override）

## Sprint 4 final closure (commit 0ad79f67) — REF-20 P6 PRODUCTION CLOSED

**Operator override**：「直接跑掉 A-H，後續有問題再修」（理由：REF-20 是 Paper Replay Lab 回測模塊 + feature flag default OFF + 0 trading.* mutation + 0 live trading 觸發）。

**安全邊界驗證**：V049-V054 schema 全 replay/learning 領域 0 trading.* 改動 + flag default OFF → production runtime 0 行為改動 + nm audit 406 symbol 0 forbidden + amendment AMD-2026-05-02-01/AMD-2026-05-03-01 IMPL/Deploy 2-stage gate retained。

**7 closure item 結算**：4 ✅ + 3 ⏭ override skip = **REF-20 P6 CLOSED**（accept-with-conditional-override）：
- ✅ Wave 1-8 closed / V### applied / Decision Lease retrofit deploy with flag OFF / E2+E4+MIT+FA+QA sign-off
- ⏭ 14d replay_no_live_mutation 0 violation / 14d governance_audit_log 0 high-severity incident / Business KPI 7d/14d snapshot

**24/25 V3 §12 acceptance binding GREEN** + 1 ⏸ DEFERRED（#21 Wave 7 P5 LG-2/3/4 stable 後解封）。

**Conditional override 3 條由 operator 後續 action（無時限）**：14d observation #4/5/6 + AMD-2026-05-02-01 flag flip canary 24h（~2026-05-15 P0-EDGE-2 後）+ AMD-2026-05-03-01 Wave 7 P5 deploy gate（LG-2/3/4 stable 後）。

## 18 Live Blocker 退役 #5

Decision Lease 在 Rust 熱路徑 0 觸發（R-04 last-mile 漏做）→ Sprint 3 Track H + Track I deploy with flag OFF → **closed**。

**最早 Live target**：以 2026-05-23 樂觀 / 2026-05-30 中位 / 2026-06-15 悲觀為規劃帶。**PA panorama 評估悲觀更可能**（5 策略 net negative + 4 LG 0 IMPL + 18 blocker 還剩 13 個未解 + Decision Lease canary 24h 未跑）。

## File 路徑指針

- **V3 SoT**：`docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`
- **Workplan V1**：`docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md`
- **Sprint 4 final closure**：`docs/execution_plan/2026-05-03--ref20_sprint4_final_closure.md`
- **Sprint 3 Track I Linux deploy runbook**：`docs/execution_plan/2026-05-03--ref20_sprint3_track_i_linux_deploy_runbook.md`
- **AMD-2026-05-02-01 Decision Lease retrofit path A**：`docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`
- **AMD-2026-05-03-01 Wave 7 amendment**：`docs/governance_dev/amendments/2026-05-03--ref20_wave7_p5_impl_accept_deploy_blocked.md`
- **Sprint 3 Track H 4 reports**：`docs/CCAgentWorkSpace/{PA,E1,E2,E4}/workspace/reports/2026-05-03--ref20_sprint3_track_h_*.md`
- **Sprint 2 PA Track E**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md`
- **Sprint 2 E2 F1**：`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_wave3_to_9_retroactive_master_review.md`
- **Sprint 2 E4 F2**：`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_wave3_to_9_retroactive_e4_cumulative.md`
- **Sprint 1 Track A/B/C/D 4 reports**：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint1_track_{a,b,c,d}_*.md`
- **Sprint 1 E2 round 1+2**：`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_sprint1_{4track_review,round2_retrofit_review}.md`
- **Sprint 1 E4 regression**：`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_sprint1_e4_regression.md`
- **TODO P1-INFRA-3**：✅ REF-20 P6 PRODUCTION CLOSED（commit `0ad79f67`）；P1-INFRA-3k/l/m 全 ✅ DONE
