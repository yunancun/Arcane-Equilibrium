# PM Memory — 工作記憶

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；新條目（含 agent 完成序列）一律倒序插入「近期記錄」標題後，**禁止檔尾第二累積區**（2026-07-04 P1-7 根修：雙累積區曾使 07-02 最新條目躲在 L4256+、超出 2000 行 Read 窗而不可見）。

## 長期教訓（2026-06-10 壓實蒸餾，源自 2026-03-31~2026-06-04 條目）

1. 部署驗證必查 `/proc/$pid/exe` 與 binary hash/strings 對齊：PID 存活可能跑著已刪除的舊 executable，source grep+watchdog 不能證明 runtime 已載入新碼。
2. Linux rebuild 經非登入 SSH 必帶 `PATH=$HOME/.cargo/bin:$PATH`；標準部署指令 `bash helper_scripts/restart_all.sh --rebuild --keep-auth`。
3. `--keep-auth` 只保留現存簽名 auth、不會恢復已缺失者（restart sentinel 可能已消耗 auth）；live auth 只能走簽名 renew 路徑，禁手寫 authorization.json。
4. Bind/health 用實際地址：`OPENCLAW_BIND_HOST=auto` 解析 Tailscale IPv4 否則 loopback，禁 0.0.0.0/::；健康探測打實際 bind 地址而非假設 127.0.0.1。
5. 派發前 PM 必做 ground-truth audit（fetch+查 remote branch+實測現狀），TODO banner 與 prompt hint 會 stale；sub-agent 應 read source 驗證 prompt 前提，偏離時 pivot 並記錄動機。
6. Sub-agent prompt 必明示：直接 commit+push 不留 staging dir；push 被 sandbox 擋時 inline 回報由 PM 補推、禁 dangerouslyDisableSandbox；鼓勵 push back 非盲從執行。
7. 多 session 並行安全模式：meta-doc 用 `git commit --only`、絕不動隔壁 WIP；branch chaos 下 `git push origin <hash>:main` 與 git plumbing pattern 安全（不含 checkout/merge/rebase）。
8. 大工程先派 PA design（含 ready-to-deploy E1 prompt template）再派實作；同檔 overlap 任務強制串行派發或 first-commit absorb pattern，避免 rebase conflict。
9. Cross-agent audit 前提可能部分錯（MIT/PA/QC 均有先例），push back+SSOT trace 驗證是責任；判級先分清「by-design 未實作」vs「真壞掉」，避免 P0/CRITICAL false elevation。
10. Source/test green ≠ runtime/product closure；conditional-pass review 不是 closure；contract/FND PASS 只開下一層 design scope 非 implementation clearance；舊 spec 的 stale ready-to-implement 標頭要打 gate override 註記。
11. Healthcheck 校準：FAIL 須區分真 wedge 與合法狀態（rejected-only、Working maker、rolling-window shrink → WARN）；分母選錯會長期 false-red（[55] 改 fully-filled plan invariant 先例）。
12. Replay-first 驗證默認：sign-off 前先判 replay/counterfactual 能否驗 claim，能且安全就跑；不能則明說並改用 runtime probe / DB inventory / WS probe / healthcheck / static guard。
13. Alpha promotion 治理：math-primary、bull-heavy 證據必標註；Stage 0R GATE-RED 不啟 Stage 1（Demo-only 證據鏈）；gate 必 machine-checkable fail-closed——producer 不檢查的 manifest/JSON 等於沒有 gate。
14. V### migration 必 Linux PG empirical dry-run + double-apply 驗 idempotency；V 槽位尊重已文檔化 reserved slots；整合/合併後的 SQL 要重跑 dry-run（曾抓 Timescale `time_interval` 整合 bug）。
15. Schema 註釋與「表存在」都不是事實：retention 以 migration+PG 反射為準，0-row 表 ≠ pipeline live；先 runtime/DB 查證再寫結論。
16. 審計報告合併必按根因去重（同一問題 E3/E4/PA 各報一遍）；估時保留 E2+E4 佔總工時 30-40% 的 buffer。
17. 新 healthcheck slot 派發前 grep `passive_wait_healthcheck/runner.py` 確認編號避免衝突；被動等待項必綁 healthcheck/復查日期；fresh-restart grace 內的 PASS 不算 post-grace 閉合。
18. 長 multi-agent run 後不 bulk-commit raw WIP：只 promote 單一 canonical closure report，stale/衝突 role notes 留待 reconcile；Operator mirror 要嘛 pointer/stub 要嘛 `cmp` byte-identical。

## 近期記錄

## 2026-07-07 AI/ML Downstream Closure Loop Design

- PM designed the post-WP1-WP5 downstream closure loop as `DESIGN_READY_SOURCE_FIRST_RUNTIME_GATED`: no need to wait for neighbor data to design or run source-safe WP2.1/WP3.1 work, but runtime learning remains gated by PM->E3->BB and bounded Demo outcome evidence.
- Loop order: `WP2.1` training PIT gate -> `WP3.1` registry contract emission -> `WP6` reward-ledger ProofPacket bridge -> `WP7` effect-review stop loop; each iteration must write effect review and state packet.
- Auto-stop codes include dirty overlap, source drift, boundary, loss-control, test, evidence, no-delta, wait-neighbor, source-closure-wait-runtime, wait-bounded-demo-outcomes, and loop-complete. Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_closure_loop_design.md`。

## 2026-07-07 AI/ML Roadmap WP1-WP5 Completion Assessment

- PM combined WP5 with prior WP1-WP4 audit and signed `PASS-SOURCE-CONTRACT-LAYER / FAIL-FULL-TRAINING-PROFIT-EVOLUTION-CLOSURE`: WP1-WP5 source contracts are complete enough, but the full AI/ML trading-learning loop is not complete.
- Verification passed: WP1-WP5/training/bandit/applier `245 passed, 1 skipped`, advisory/runner adjacency `61 passed`, compile gate PASS. Venv dry-run trained/exported ONNX but still failed at registry DB precheck and acceptance report lacked WP1-WP5/reward/effect binding fields.
- Remaining downstream work: `WP2.1` training PIT gate, `WP3.1` registry contract emission, `WP6` reward-ledger ProofPacket bridge, `WP7` effect-review stop loop, and standing Demo loss-control refresh before runtime learning. Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_roadmap_wp1_wp5_completion_assessment.md`。

## 2026-07-07 AI/ML Roadmap WP1-WP4 Training / Profit / Evolution Cold Audit

- PM 補跑冷酷對抗性 audit 後裁決：`FAIL-STRICT-AS-STATED / PASS-AS-PREREQUISITES`。WP1-WP4 是正確且必要的 proof/PIT/registry/advisory 前置，但尚未構成完整盈利追逐、自我訓練、自我進化閉環。
- 驗證：WP1-WP4/quantile/bandit focused suite `165 passed, 1 skipped`；project venv dry-run 可訓練並輸出 ONNX/acceptance report，但最終被 registry DB precheck 擋住，且 acceptance report 沒有 WP contract binding fields。
- 下一步應落 `WP2.1` training PIT gate、`WP3.1` registry contract emission、`WP5` mutation envelope、`WP6` reward-ledger ProofPacket bridge、`WP7` effect-review stop loop。Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_roadmap_wp1_wp4_training_profit_evolution_cold_audit.md`。

## 2026-07-06 AI/ML Roadmap Loop WP5 Demo Mutation Envelope Contract

- PM selected `WP5-DEMO-MUTATION-ENVELOPE-CONTRACT` after WP4 because controlled Demo bandit work needs a machine-checkable DemoMutationEnvelope boundary before any runtime/reward allocation path.
- Added `demo_mutation_envelope_v1` plus a pure `mlde_demo_applier` record mapping. `_record_application` now attaches `payload.demo_mutation_envelope` without changing SQL schema, status semantics, dedupe, patch calculation, IPC params, or live-candidate behavior.
- Countability is fail-closed: applied Demo status, non-empty patch, no dedupe/dry-run, concrete bounded delta, rollback, governance review allowance, post-change review pass, and valid proof linkage are all required. Empty/dedupe/dry-run/skipped/failed/non-demo/live/live_demo/missing-bound rows are audit-only or invalid.
- E2 initially found 2 high issues (missing concrete max-delta bound for countability and missed authority/scope aliases); E1-fix closed both. E2 rereview PASS, E4 PASS, QA ACCEPT.
- Verification passed: py_compile, envelope/mapping `49 passed`, mlde_demo_applier `31 passed`, adjacent ProofPacket/PIT/advisory contracts `93 passed`, forbidden scan, `git diff --check`.
- State is `STOPPED` with `STOP_LOSS_CONTROL`: next work is `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD` through PM->E3->BB, not bandit runtime.

## 2026-07-07 AI/ML Roadmap WP1-WP4 Fixes And Trading-Focused Audit

- PM fixed all findings from the strict WP1-WP4 audit: ProofPacket `sha256:` refs are strict, advisory packets carry self-hash plus no-provider/no-exchange/no-private/no-MCP contact guards, and registry serving q10/q50/q90 writes are one transaction.
- Verification passed: focused `116`, WP1-WP4 regression `155`, Control API adjacency `93`, thought-gate/cost `18`, proof/evidence/promotion `90`, py_compile, and diff-check.
- Second trading-focused adversarial probe passed 21/21 fail-closed payloads while preserving a valid candidate-matched after-cost proof happy path. Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_roadmap_wp1_wp4_fixes_and_trading_adversarial_audit.md`.

## 2026-07-07 AI/ML Roadmap WP1-WP4 Strict Adversarial Audit

- PM ran a strict source-only adversarial audit over completed WP1-WP4. Verdict: `CONDITIONAL`; boundary held and focused regressions passed, but WP1/WP4 need P1 hardening before downstream authority-grade use.
- Finding 1: ProofPacket accepts malformed `sha256:` references as proof-ready provenance. Finding 2: advisory review packets accept truthy provider/private/exchange/MCP contact aliases while still validating inactive.
- WP2 passed this audit; WP3 keeps its known non-transactional trio persistence concern. Reports: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_roadmap_wp1_wp4_strict_adversarial_audit.md`; operator mirror same basename under `docs/CCAgentWorkSpace/Operator/`.

## 2026-07-06 AI/ML Roadmap Loop WP4 Advisory DreamEngine Role Hardening

- PM selected `WP4-ADVISORY-DREAMENGINE-ROLE-HARDENING` after WP3 because L2/LLM/MLDE/DreamEngine/thought-gate outputs needed a reusable inactive no-authority packet before any controlled Demo bandit work.
- Added `advisory_review_packet_v1` with stable input hashes and validator-backed no-mutation fields; L2 now strips model-supplied packets and rebuilds local packets, including no-output error rows.
- MLDE shadow, DreamEngine parameter/replay proposals, thought-gate H1-E/H1-H/H1-I/handoff, and admitted `/ml-advisory/dispatch` responses now carry valid inactive packets where they produce advisory output.
- E2 initially found 2 high + 1 medium, then 1 medium route projection issue; all were fixed. E4 PASS: py_compile, ML/helper `53 passed`, L2 `84 passed`, thought-gate `18 passed`, `git diff --check`.
- State is `ADVANCED_WITH_CONCERNS`: source-only acceptance, upstream screen/admission rejects are non-proposal gate outcomes, and next safe work is `WP5-DEMO-MUTATION-ENVELOPE-CONTRACT` before any controlled Demo bandit runtime.

## 2026-07-06 AI/ML Roadmap Loop WP3 Registry Serving Parity

- PM selected `WP3-REGISTRY-SERVING-PARITY-SOURCE-CONTRACT` after WP2 because registry/advisory serving metadata was the next safe source-only dependency; runtime/order-capable work remains blocked by expired standing Demo authorization.
- Added `registry_serving_contract_v1` plus Python/Rust validation so advisory registry metadata is `not_authority=true`, `promotion_serving_ready=false`, PIT/feature/schema/policy/hash-bound, and q10/q50/q90 artifact-bound before attachment or validation.
- Rust and FastAPI capability surfaces now keep direct `reload_edge_predictor=false` until registry-authorized serving integration exists. Final E2 PASS, E4 PASS, QA ACCEPT_WITH_CONCERNS.
- Verification passed: py_compile; focused Python `58 passed`; expanded ML `106 passed, 13 skipped`; Rust registry `25 passed`; Rust reload `4 passed`; Rust capability `1 passed`; rustfmt; `git diff --check`.
- State is `ADVANCED_WITH_CONCERNS`: no promotion-serving readiness, no runtime reload authority, partial trio persistence is fail-loud not transactional rollback, and WP4 should harden advisory DreamEngine role boundaries next.

## 2026-07-06 AI/ML Roadmap Loop Continuous-State Correction

- PM updated the AI/ML roadmap loop spec after the WP1 dry-run exposed that `ADVANCED` had no durable state cursor. `roadmap_loop_state_packet_v1` is now mandatory after every iteration, not only on stop.
- Launcher rule: if latest effect review has no matching state packet, write an `ADVANCED_WITH_CONCERNS` recovery packet and continue from `next_work_id`; single-cycle runs require explicit `max_iterations=1`.
- Source feature work now requires the repo role chain by default; PM direct code is only docs/state/report scope or explicit single-agent exception, otherwise stop as `STOP_DISPATCH_BLOCKED`.

## 2026-07-06 AI/ML Roadmap Loop WP1 ProofPacket Contract

- PM ran the first autonomous engineering completion loop cycle and selected `WP1-PROOF-PACKET-V1` because runtime/order-capable WP0 remains blocked by expired standing Demo authorization; source-only work was allowed.
- Added `proof_packet_v1` validator/hash/extractor/tests under `program_code/ml_training/`, requiring candidate-matched order/fill/cost/control/provenance proof and treating `NO_MATCHED_FILLS` as blocker artifact, not a label or authority.
- Verification passed: focused ProofPacket `15`, adjacent ML evidence `60`, adjacent cost-gate proof/promotion `20`, py_compile, diff-check. Reports: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_loop_wp1_proof_packet_contract.md`; operator summary same basename under `docs/CCAgentWorkSpace/Operator/`.

## 2026-07-06 AI/ML Roadmap Autonomous Completion Loop Design

- PM designed a source-first autonomous engineering completion loop for the AI/ML roadmap: gate-based backlog, work-item contract, effect-review packet, stop packet, and strict dependency order from ProofPacket/PIT to advisory/bandit/side lanes.
- The loop is explicitly not a trading loop: it may automate source/docs/tests/reports and role dispatch, but stops on runtime mutation, DB write, exchange/private read, MCP server/credential, order/probe, Cost Gate, live/mainnet, source drift, test failure, or repeated no-delta.
- First safe implementation tickets remain `proof_packet_v1`, PIT dataset manifest, or current-head standing envelope refresh under existing PM->E3->BB. Reports: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_autonomous_completion_loop_design.md`; operator mirror `docs/CCAgentWorkSpace/Operator/2026-07-06--ai_ml_roadmap_autonomous_completion_loop_design.md`.

## 2026-07-06 AI/ML Roadmap Adversarial Audit

- PM ran a source-only adversarial audit of the AI/ML roadmap and signed `PASS-WITH-CONDITIONS`: direction is effective if enforced as a gate-based dependency graph, not a calendar promise.
- Key constraints: define `proof_packet_v1` before treating ProofPacket as an interface; make PIT manifests mandatory; extend registry-authorized serving metadata; formalize/map `DemoMutationEnvelope`; pre-register new-listing/event screens; scope M12 as cost reduction only; keep MCP pinned source-only.
- Boundary held: no runtime action, DB write, exchange/API/private read, order/probe, MCP install/config, Cost Gate change, secret access, or live/mainnet.
- Reports: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_roadmap_adversarial_audit.md`; operator mirror `docs/CCAgentWorkSpace/Operator/2026-07-06--ai_ml_roadmap_adversarial_audit.md`.

## 2026-07-06 AI/ML Roadmap After Maker-First Challenge

- PM challenged the maker-first NO-GO without overturning its narrow conclusion: mature-perp passive spread capture at current Bybit fee tier remains blocked, but the result must not be overextended into "AI is useless" or "all engineering edge is dead."
- Signed roadmap: mainline is ProofPacket/candidate-matched outcome loop -> point-in-time dataset manifests -> supervised q10/q50/q90 advisory -> controlled Demo bandit learning; new-listing/event microstructure, M12 adaptive router, and MCP inventory are scoped side lanes with explicit kill gates.
- Boundary held: planning/report only. No runtime action, DB write, exchange/API/private read, order/probe, Cost Gate change, MCP install/config, secret access, or live/mainnet.
- Reports: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_trade_engineering_roadmap_after_maker_challenge.md`; operator mirror `docs/CCAgentWorkSpace/Operator/2026-07-06--ai_ml_trade_engineering_roadmap_after_maker_challenge.md`.

## 2026-07-06 Maker-First / Microstructure Feasibility — NO-GO

- PM ran a read-only $0 four-agent wave (QC/BB/MIT/PA) plus a two-window `fill_sim` run over ~34M rows of recorded `market.l1_events` to test whether a maker-first (passive liquidity-provision) paradigm could fix non-profitability / mechanical design. Verdict: **NO-GO as an engineering profit lever at Bybit VIP0**, triple-confirmed — BB (VIP0 maker is a +2.0 bps fee not a rebate; rebate is institution-gated MM-program only), QC (half-spread ≈ fee on liquid perps), `fill_sim` (**0/172 cells net-positive** across fast-3h + 72h windows; best cell ADAUSDT −3.2 bps; 0 signals survive walk-forward holdout; break-even needs maker fee ≤ ~0.4 bps/side).
- Structural reason is market-making-native, not directional-alpha: captured half-spread < adverse selection + maker fee; wide-spread symbols do NOT help (adverse selection scales with spread). The lower-fee tier that would flip it is an operator capital/BD lever, not engineering.
- Correction to the session's initial thesis (falsified by PA at code level): the hot path is NOT a hardcoded naive taker — maker/PostOnly entry is live (`use_maker_entry=true` demo+live), demo close-maker is attempted; the taker wall is on the exit leg and is a microstructure reality (passive exits don't reliably fill), not a code gap. Genuinely dormant = `order_router.rs` M12 adaptive router (0-caller `unimplemented!()`) — a cost-reduction capability, not alpha.
- Still open (not concluded, mandate-respecting): brand-new-listing wide-spread capture (offline-screenable $0); full CP-3 multi-regime accumulation (passive via recorder+cron, unlikely to overturn the regime-independent fee wall); infra-tier change. P0 read-only prep came back CLEAN (Rust RiskConfig sole cap authority; June live-write 5-gate-bypass P1 remediated at HEAD; no hidden 10-USDT path; context_id-keyed outcomes).
- Lesson: a detached long research job (`fill_sim`, reparented to init) survives its launching agent's idle-kill; its liveness = remote PID + output artifact, independent of the agent — diagnose before `TaskStop`. PM prematurely stopped a resuming QC here and recovered by reading the durable JSON in the main session (no data lost).
- Boundary held: read-only, offline, $0. No order, probe, private read, exchange contact, secret access, MCP, Cost Gate change, DB write, migration, runtime mutation, or live/mainnet. No implementation dispatched; awaiting operator fork (niche screen / infra decision / M12 cost-reduction). Report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--maker_first_microstructure_feasibility_verdict.md`.

## 2026-07-05 AI/ML Trading Maturity Engineering Plan

- PM integrated QC/MIT/AI-E/PA/E3/BB reviews plus local CC root-principle review into a five-phase AI/ML trading maturity plan: evidence loop, point-in-time training foundation, advisory model layer, controlled Demo learning, and optional RL/MCP research.
- Sign-off is conditional: proceed with Phase 1/2 engineering; no MCP runtime, no direct AI order authority, no RL policy work before candidate-matched after-cost evidence and sealed manifests exist.

## 2026-07-05 Official MCP Exchange Tool Review

- PM reviewed IBKR's official AI/MCP connector and Bybit's official `trading-mcp` as source-only architecture inputs. Verdict: do not replace Rust-owned execution or ADR-0048 IBKR baseline; use official tools only as reference/offline inventory unless a future E3/BB-reviewed gate authorizes narrower use.
- Borrowable patterns: IBKR human-in-the-middle instruction flow, Bybit capability taxonomy, credential-minimization language, and deny-by-default MCP tool matrix. No MCP install/config, no credentials, no exchange contact, no runtime mutation.

## 2026-07-05 Legacy TODO Remaining Work Audit

- PM re-audited the two residual legacy TODOs after the MAG-083/MAG-084 and Phase 5 cleanup: `AgentTodo.md` and `2026-04-10--signal_diamond_db_todo.md` now have no clean directly-dispatchable remaining work.
- AgentTodo MAG-002/MAG-003 are historically closed by MAG-015 contract addendum; open questions / DoD were reclassified as historical context and not runtime authorization.
- Signal Diamond's old `mode_states` / `active_modes` / per-mode strategy-instance limitation is superseded by 3E-4 per-pipeline `PipelineKind` architecture; future shared-compute fan-out would need a fresh root TODO/ADR, not this legacy ledger.

## 2026-07-05 Legacy TODO MAG/Phase5 Resolution

- PM cleaned the desktop main worktree by preserving the pre-sync dirty state on branch `preserve/dirty-worktree-20260705-before-main-sync` at `0296d7ba7`, then aligned Mac/Linux/main to `54d5fbf99`.
- MAG-083/MAG-084 in legacy AgentTodo were stale blockers; 2026-05-11 W-D sign-off already records MAG-083 PASS and MAG-084 SIGNED, with live/Stage3/Executor boundaries still closed.
- Signal Diamond Phase 5 strategy params are code-complete through per-engine TOML files plus Rust `load_strategy_params(PipelineKind)`; per-mode strategy instance fan-out remains separate future work.

## 2026-07-02 Stock/ETF Phase0 Route Exact Contract Manifest Guard

- PM tightened test-only exact-manifest coverage for the FastAPI Phase0 status route: accepted `contracts` now must match the complete ordered 36-item Phase0 contract list.
- The Phase0 route source guard now rejects loose `set(...)`, membership, and subset assertions for both `contract_violations` and `contracts`.
- Verification passed: Phase0 route `5 passed`; full Stock/ETF Python route/static `144 passed`; changed-file `py_compile` PASS; no-loose contract/contracts scan PASS; changed-file diff check PASS.
- Boundary unchanged: no FastAPI route behavior change, Rust IPC handler behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, DB/evidence writer, scorecard writer, evidence clock, release launch, paper-shadow launch, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 Stock/ETF Rust IPC Fixture Split Guard

- PM split oversized Rust IPC Stock/ETF fixture tests into clearer modules: parent `stock_etf.rs` now holds only the module shell/shared guard/helper plus untrusted params test, core status fixtures live in `core_status_fixtures.rs`, and Phase5 status fixtures live in `phase5_status_fixtures.rs`.
- The exact assertion source guard now covers the new modules so loose blocker membership assertions cannot return after the split.
- Verification passed: Stock/ETF Rust IPC fixture line counts all below 800; fixture `rustfmt --edition 2021 --check` PASS; `cargo test -p openclaw_engine stock_etf -- --test-threads=1` PASS with Stock/ETF IPC/lib `32 passed`; no-loose blocker scan PASS.
- Boundary unchanged: no Rust IPC handler behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, DB/evidence writer, scorecard writer, evidence clock, release launch, paper-shadow launch, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 Stock/ETF Readiness Denied Operations Exact Guard

- PM tightened FastAPI readiness route tests so `denied_operations` must match the complete ordered Stock/ETF denied operation vector on both fail-closed and readonly fixture paths.
- The readiness route source guard now rejects loose `set(...)`, membership, and subset assertions for `denied_operations`.
- Verification passed: readiness route `7 passed`; full Stock/ETF Python route/static `144 passed`; changed-file `py_compile` PASS; no-loose denied-operations scan PASS; diff check PASS.
- Boundary unchanged: no FastAPI route behavior change, Rust IPC handler behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, DB/evidence writer, scorecard writer, evidence clock, release launch, paper-shadow launch, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 Stock/ETF Lane-Scoped IPC IO Matrix Exact Guard

- PM added a split test-only Rust acceptance guard for the lane-scoped IPC command IO matrix so all 20 accepted commands must keep complete ordered `required_gates` and `required_request_fields` vectors.
- The legacy lane-scoped IPC acceptance file no longer uses positive gate/field membership assertions for submit/preview/shadow/readonly-probe; a source guard blocks `.required_gates.contains(...)`, `assert_fields(...)`, and positive request-field contains checks from returning.
- Verification passed: lane-scoped IPC focused Rust acceptance `12 + 2 passed`; full `cargo test -p openclaw_types` PASS; package fmt PASS; lane-scoped IPC source static `7 passed`; no-loose IO scan PASS; diff check PASS.
- Boundary unchanged: no Rust production code change, Rust IPC handler behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, DB/evidence writer, scorecard writer, evidence clock, release launch, paper-shadow launch, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 Stock/ETF Broker Capability Gate Matrix Exact Guard

- PM added a split test-only Rust acceptance guard for the broker capability registry gate matrix so all 15 accepted broker operations must keep complete ordered `required_gates` vectors plus pinned authority scope, denial reason, Rust ownership, and audit/source-hash flags.
- The legacy broker capability registry acceptance file no longer uses positive `required_gates.contains(...)` membership assertions for accepted rows or paper-fill-import; a source guard blocks those loose gate checks from returning.
- Verification passed: broker capability focused Rust acceptance `14 + 2 passed`; full `cargo test -p openclaw_types` PASS; package fmt PASS; broker capability source static `9 passed`; no-loose gate scan PASS; diff check PASS.
- Boundary unchanged: no Rust production code change, broker capability validator semantics change, Rust IPC handler behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, DB/evidence writer, scorecard writer, evidence clock, release launch, paper-shadow launch, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 Stock/ETF DB Evidence DDL Required Surface Exact Guard

- PM tightened test-only DB evidence DDL accepted fixture coverage so `required_schemas`, `required_tables`, and `required_natural_keys` must match complete ordered vectors.
- The DB evidence DDL acceptance file no longer uses positive schema/table membership assertions for accepted required surface checks; a source guard blocks `.required_schemas.contains(...)`, `.required_tables.contains(...)`, and `.required_natural_keys.contains(...)` from returning before the guard.
- Verification passed: DB evidence DDL focused Rust acceptance `11 passed`; full `cargo test -p openclaw_types` PASS; package fmt PASS; DB evidence DDL source static `7 passed`; no-loose required-surface scan PASS; diff check PASS.
- Boundary unchanged: no Rust production code change, DB evidence validator semantics change, migration/DDL production behavior change, DB apply, PG/runtime contact, Rust IPC handler behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, DB/evidence writer, scorecard writer, evidence clock, release launch, paper-shadow launch, destructive DB cleanup, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 Stock/ETF Risk Policy Instrument Kind Exact Guard

- PM tightened test-only risk policy accepted fixture coverage so `instrument_kinds_allowed` and `instrument_kinds_denied` must match complete ordered vectors.
- The risk policy acceptance file no longer uses positive instrument-kind membership assertions for accepted fixture checks; a source guard blocks `.instrument_kinds_allowed.contains(...)` and `.instrument_kinds_denied.contains(...)` from returning before the guard.
- Verification passed: risk policy focused Rust acceptance `10 passed`; full `cargo test -p openclaw_types` PASS; package fmt PASS; risk policy source static `7 passed`; no-loose instrument-kind scan PASS; diff check PASS.
- Boundary unchanged: no Rust production code change, risk policy validator semantics change, source/runtime config change, Rust IPC handler behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, DB/evidence writer, scorecard writer, evidence clock, release launch, paper-shadow launch, destructive DB cleanup, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 Stock/ETF Lane Readiness Denial Reasons Exact Guard

- PM tightened test-only lane readiness default fail-closed coverage so `readiness.denial_reasons` must match the complete ordered vector `LaneDisabled`, `BrokerDisabled`, `ShadowOnly`.
- The lane acceptance file no longer uses a positive readiness denial-reason membership assertion for the default fixture; a source guard blocks `.denial_reasons.contains(...)` from returning before the guard.
- Verification passed: lane focused Rust acceptance `15 passed`; full `cargo test -p openclaw_types` PASS; package fmt PASS; lane source static `8 passed`; no-loose readiness denial scan PASS; diff check PASS.
- Boundary unchanged: no Rust production code change, lane/readiness validator semantics change, source/runtime config change, Rust IPC handler behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, DB/evidence writer, scorecard writer, evidence clock, release launch, paper-shadow launch, destructive DB cleanup, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 IBKR Non-Bybit API Allowlist Bucket Exact Guard

- PM tightened test-only Phase2 gate embedded allowlist coverage so `NonBybitApiAllowlistV1::accepted_fixture()` must keep complete ordered `read_actions`, `paper_write_actions`, and `denied_actions` vectors.
- The Phase2 gate acceptance file no longer relies on aggregate action-bucket length coverage for the accepted fixture; a source guard blocks `allowlist.*_actions.len()` and `required_non_bybit_api_actions().len()` aggregate assertions from returning before the guard.
- Verification passed: IBKR Phase2 gate focused Rust acceptance `14 passed`; full `cargo test -p openclaw_types` PASS; package fmt PASS; Phase2 gate source static `8 passed`; no-loose bucket scan PASS; diff check PASS.
- Boundary unchanged: no Rust production code change, non-Bybit API allowlist validator semantics change, external-surface/session gate semantics change, Rust IPC handler behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, DB/evidence writer, scorecard writer, evidence clock, release launch, paper-shadow launch, destructive DB cleanup, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 Stock/ETF IPC Phase5 Status List Exact Guard

- PM tightened test-only Rust IPC Phase5 status fixture coverage so release-packet `blockers` and `manifest_hashes`, disable-cleanup `blockers`, `env_flags`, and `proofs`, plus universe `sample_constituents`, must match exact ordered arrays instead of length-only checks.
- The shared Rust IPC status fixture source guard now blocks `.as_array().unwrap().len()` length-only list assertions from returning across Stock/ETF IPC fixture modules.
- Verification passed: changed-file rustfmt PASS; `cargo test -p openclaw_engine stock_etf -- --test-threads=1` PASS with Stock/ETF IPC/lib `32 passed`; no-loose list scan PASS; diff check PASS. Full `cargo fmt -p openclaw_engine -- --check` remains blocked by pre-existing unrelated crate-wide rustfmt drift, so PM did not format unrelated files.
- Boundary unchanged: no Rust IPC handler behavior change, Rust production behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, release launch, disable/cleanup action, DB/evidence writer, scorecard writer, evidence clock, paper-shadow launch, destructive DB cleanup, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 Stock/ETF Phase3 Evidence Acceptance Split Guard

- PM split the oversized Phase3 evidence Rust acceptance file by contract boundary: collector/evidence-clock/template coverage remains in `stock_etf_phase3_evidence_acceptance.rs`, market-data/frozen-input coverage moved to `stock_etf_phase3_market_data_acceptance.rs`, and DQ manifest coverage moved to `stock_etf_phase3_dq_acceptance.rs`.
- Line-count hygiene now holds for the split files: 640 / 265 / 173 lines, all below 800, while preserving the same 24 Phase3 evidence-related tests.
- Verification passed: changed-file rustfmt PASS; Phase3 focused Rust acceptance DQ `5 passed`, evidence `11 passed`, market-data `8 passed`; full `cargo test -p openclaw_types` PASS; test-count/line-count scans PASS. Desktop shell `~/.cargo/bin` proxies point at a stale rustup-init symlink, so PM ran verification through Homebrew rustup + stable toolchain bin without changing repo or global env.
- Boundary unchanged: no Rust production code change, Phase3 validator semantics change, source/runtime config change, Rust IPC handler behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, DB/evidence writer, scorecard writer, evidence clock, paper-shadow launch, destructive DB cleanup, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-06 AI/ML Roadmap Loop WP2 PIT Dataset Manifest

- PM ran `WP2-PIT-DATASET-MANIFEST` through the required `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM` source-feature chain.
- Added source-only `pit_dataset_manifest_v1` validator and builder with deterministic row-id/dataset hashes, rebuild evidence, pinned query/as-of requirements, feature/label/split/leakage lineage, matched-control evidence, row-backed fill source, and fail-closed secret/authority/cleanup checks.
- Updated ProofPacket `PROOF_READY` to require valid `provenance.pit_dataset_manifest`; after E2/QA findings, added candidate_scope cross-binding and broader authority alias blocking for keys such as `order_allowed` and `promotion_allowed`.
- Verification passed: focused PIT/ProofPacket `36`, adjacent ML evidence `81` with `1 skipped`, adjacent cost-gate proof/promotion `20`, py_compile, static no-I/O scan, and `git diff --check`.
- Loop state is `ADVANCED`; next source-only item is `WP3-REGISTRY-SERVING-PARITY`. Boundary unchanged: no runtime mutation, DB read/write, exchange/private read, MCP server, secret access, order/probe, Cost Gate change, deploy, live, or mainnet.

## 2026-07-06 AI/ML Roadmap Loop WP1 Chain Closure

- PM recovered the missing WP1 state packet, dispatched E2/E4/QA against commit `b9867ac9e`, and closed the original shortened-chain concern.
- E4 and QA passed: ProofPacket focused `15`, adjacent ML evidence `60`, adjacent cost-gate proof/promotion `20`, plus `git diff --check`.
- E2 found one medium proof-quality concern: ProofPacket provenance is still too generic until WP2 adds named PIT dataset manifest, rebuild evidence, feature/schema lineage, matched-control artifact hash, and row-backed fill source artifact hash.
- Loop state is `ADVANCED_WITH_CONCERNS`; next safe work is `WP2-PIT-DATASET-MANIFEST` through `PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM`.
- Boundary unchanged: no runtime mutation, DB read/write, exchange/private read, MCP server, secret access, order/probe, Cost Gate change, deploy, live, or mainnet.

## 2026-07-02 Stock/ETF Paper Order Request Acceptance Split Guard

- PM split the oversized paper-order request Rust acceptance file by contract boundary: default/accepted fixture, aggregate cross-wire, method-specific shape, boundary regression, and template coverage remain in `stock_etf_paper_order_request_acceptance.rs`; independent gap matrix coverage moved to `stock_etf_paper_order_request_gap_acceptance.rs`.
- Line-count hygiene now holds for the split files: 378 / 506 lines, both below 800, while preserving the same 17 paper-order request tests.
- Verification passed: changed-file rustfmt PASS; paper-order focused Rust acceptance original `11 passed`, gap `6 passed`; full `cargo test -p openclaw_types` PASS; test-count/line-count scans PASS.
- Boundary unchanged: no Rust production code change, paper-order request validator semantics change, source/runtime config change, Rust IPC handler behavior change, FastAPI route behavior change, GUI behavior change, connector production code change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, DB/evidence writer, scorecard writer, evidence clock, paper-shadow launch, destructive DB cleanup, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 Stock/ETF IBKR Connector Action Matrix Preview Guard

- PM added inert `IbkrApiActionMatrixPreview` to the Python IBKR connector skeleton, mirroring the Rust `non_bybit_api_allowlist_v1` ordered buckets: 10 read actions, 3 paper-write actions, and 10 denied actions.
- `IbkrReadOnlyClient.api_action_matrix_preview()` and `blocked_api_action_matrix_fixture()` return blocked dict/list/count payloads only; public exports, README source boundary, fixture export, public-surface freeze, payload shape, side-effect false fields, and risky-config blocker coverage were updated.
- Verification passed: changed Python files `py_compile` PASS; connector skeleton + no-write focused pytest `18 passed`; full Stock/ETF Python route/static pytest `144 passed`; `git diff --check` PASS; skeleton test remains 791 lines.
- Boundary unchanged: no FastAPI wiring, Rust/GUI/IPC behavior change, IBKR contact, connector runtime, socket/client construction, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, DB/evidence writer, scorecard writer, evidence clock, paper-shadow launch, destructive DB cleanup, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-02 Stock/ETF IBKR Connector Action Matrix Test Split Guard

- PM split action-matrix exact coverage out of `test_stock_etf_ibkr_connector_skeleton.py` into focused `test_stock_etf_ibkr_connector_action_matrix.py`.
- The new test owns `non_bybit_api_allowlist_v1` contract/source, exact ordered read/paper-write/denied buckets, fixture parity, risky-config blocker expansion, and dataclass inert posture. The skeleton test retains package export, README boundary, Bybit import separation, public surface, and non-action preview payload coverage.
- Verification passed: changed test `py_compile` PASS; connector skeleton/action-matrix/no-write focused pytest `22 passed`; full Stock/ETF Python route/static pytest `148 passed`; `git diff --check` PASS. Line-count hygiene: skeleton 701 lines, action-matrix 168 lines.
- Boundary unchanged: no connector production code change, FastAPI route behavior change, Rust/GUI/IPC behavior change, IBKR contact, connector runtime, secret access, broker session, read-only probe execution, paper order routing/cancel/replace execution, fill import execution, DB/evidence writer, scorecard writer, evidence clock, paper-shadow launch, destructive DB cleanup, tiny-live/live authorization, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 Standing Envelope Source Impact Guard Done

- PM closed `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-SOURCE-STABILITY-CURRENT-HEAD` as source/test/docs `DONE_WITH_CONCERNS` by adding `standing_envelope_source_impact_guard_v1`.
- The guard compares an approved base ref to current `HEAD`, requires clean source plus `HEAD == origin/main`, and fails closed for protected standing-refresh/runtime/security/config surfaces, unknown changes, binary/submodule ambiguity, missing refs, non-ancestor base, and git errors.
- READY grants only E3/BB review input for the standing-envelope refresh surface; it grants no stale approval consumption, runtime action, Control API GET, Bybit call, Decision Lease, order, PG, risk/Cost Gate, live/mainnet, fill/PnL, or proof.
- Verification passed focused/adjacent tests `38`, py_compile, diff-check, E2, and E4. Runtime standing auth remains expired; next blocker is `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD` with a fresh exact-source or source-impact-guarded E3/BB cycle.

## 2026-07-01 Stock/ETF IBKR Connector Preview Exact Blocker Guard

- PM tightened the inert Python IBKR connector skeleton preview tests from blocker membership/subset checks to exact ordered blocker vectors across default readiness, connection/account/market-data/contract previews, session/paper attestation, result-import preview, paper lifecycle, fill import, fixtures, and risky config expansion.
- Added a local source guard so this connector skeleton test cannot regress to loose payload blocker membership for preview blockers.
- Verification passed: connector skeleton focused `11`, related no-write/surface/readiness `16`, full Stock/ETF Python route/static `127`, py_compile, no-loose connector scan, and diff-check. Boundary unchanged: no connector code or route/runtime behavior change, no IBKR contact, SDK import, secret access/serialization, connector runtime, paper order, fill import, DB/evidence/scorecard writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Standing Envelope Runtime Refresh Blocked By Source Drift

- PM attempted the constrained standing Demo loss-control envelope runtime refresh across clean heads `477b248...`, `67c12f...`, and `19dae039...`; E3/BB approvals were exact-source-bound and became stale before action.
- Runtime precheck still showed expired standing auth sha `8c891b4e...` for `grid_trading|ETHUSDT|Buy`, cap `954.18759458`, max probe orders `2`, canonical soak plan sha `30056993...`, and Demo-only/mainnet-disabled service posture.
- PM stopped before any Control API GET or envelope materialization when final source check advanced to `ed2b7514...`; state transition `BLOCKED_BY_RUNTIME`. Next blocker is current-head source stability or a reviewed source-impact guard before retrying the runtime refresh.

## 2026-07-01 Stock/ETF GUI Lane Endpoint Exact Blocker Guard

- PM tightened `StockEtfGuiLaneContractV1` read-only endpoint aggregate acceptance to an exact ordered blocker vector for all Stock/ETF GUI status endpoints and GET-only flags.
- Existing source-static guard already pins GUI lane validator blocker emit order; this checkpoint removes the last broad `blockers.contains` membership coverage from Stock/ETF acceptance/static blocker scans.
- Verification passed: global loose blocker scan, GUI lane source static `7`, Rust acceptance `9`, full `cargo test -p openclaw_types`, cargo fmt, docs trace, and diff-check. Boundary unchanged: no GUI runtime/API/IPC behavior change, IBKR contact, connector/runtime, secret access/serialization, paper order route, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF DB Evidence DDL Exact Blocker Guard

- PM tightened `StockEtfDbEvidenceDdl` source SQL auditor mutation acceptance to exact single-blocker vectors for required column, foreign key, synthetic-shadow check, destructive statement, migration dry-run, guard B/C, and retention-plan drift.
- Existing source-static guard continues to pin DB evidence DDL contract and source-auditor blocker emit order; no Rust production validator or SQL draft behavior changed.
- Verification passed: DB evidence DDL source static `7`, Rust acceptance `10`, full `cargo test -p openclaw_types`, cargo fmt, docs trace, and diff-check. Boundary unchanged: no migration apply, Postgres open/write, sqlx registration, IBKR contact, connector/runtime, secret access/serialization, paper order route, evidence/scorecard writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Risk Policy Exact Blocker Guard

- PM tightened `StockEtfRiskPolicyV1` aggregate acceptance coverage to exact ordered blocker vectors for default fail-closed posture, contract/source mismatch, runtime/cap/cash-only regressions, universe/cost/paper-order gate gaps, and Bybit/IBKR/connector/secret boundary flags.
- Source-static guard now pins risk policy validator blocker emit order across top-level checks, caps, cash-only controls, universe controls, cost model controls, paper-order controls, and authority boundary flags.
- Verification passed: risk policy source static `7`, Rust acceptance `9`, full `cargo test -p openclaw_types`, cargo fmt, docs trace, and diff-check. Boundary unchanged: no Rust production code change, IBKR contact, connector/runtime, secret access/serialization, paper order route, scorecard/DB writer, tiny-live/live, or Bybit behavior change.

## 2026-07-07 Standing Demo Loss-Control Refresh Blocked By Engine Env

- PM completed the requested PM->E3->BB authorization path for `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`: request sha `62f2a9cc...` at source `798843f2`, E3 `APPROVE_FOR_BB_REVIEW`, BB `APPROVE_RUNTIME_LOSS_CONTROL_REFRESH`.
- Final source check passed and exactly one runtime-local Control API fast-balance GET produced READY artifact sha `0b1fd2ab...`, equity `9545.91584234`, `rust_snapshot_fast`/`rust_engine`/connected, no authority contamination.
- PM stopped before guardrail/materialization because corrected readiness sha `a81ae387...` was `BOUNDED_DEMO_RUNTIME_BLOCKED_BY_ENGINE_ENV`: `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0` plus expired auth. Next step is separate PM->E3 runtime/env decision; no standing envelope was materialized.

## 2026-07-01 Stock/ETF Data Foundation Exact Blocker Guard

- PM tightened source-only data foundation acceptance coverage to exact ordered blocker vectors for `StockEtfInstrumentIdentityV1`, `StockEtfPitUniverseV1`, and `StockEtfReferenceDataSourcesV1` aggregate failure cases.
- Source-static guards now pin validator blocker emit order across identity validation/cash venue rules, PIT universe top-level/constituent/hash validators, and reference-data corporate-action/FX/fee-tax validators.
- Verification passed: data foundation source static `28`, Rust acceptance `24`, full `cargo test -p openclaw_types`, cargo fmt, docs trace, and diff-check. Boundary unchanged: no Rust production code change, IBKR contact, connector/runtime, secret access/serialization, data ingestion, paper order route, evidence/scorecard/DB writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Standing Auth Readiness Cycle Source Fix

- PM fixed the standing Demo authorization refresh guardrail cycle: default still requires bounded readiness READY, while explicit `--allow-expired-standing-auth-readiness-only` accepts only the single combined blocker `standing_authorization:standing_auth_expired`.
- E2 found a nested/top-level blocker disagreement fail-open; PM fixed by unioning top-level and nested readiness blockers, then E2 replayed the prior inconsistent packet as NOT_READY with no preview.
- Verification passed: focused guardrail `10`, adjacent auth/equity/readiness/no-order `66`, py_compile, diff-check, E2, and E4. Runtime standing auth remains expired; next step is E3-reviewed runtime refresh/materialization, not no-order E3/BB.

## 2026-07-01 Stock/ETF Phase3 Evidence Exact Blocker Guard

- PM tightened `StockEtfPhase3` evidence acceptance coverage to exact ordered blocker vectors for market-data provenance drift/boundaries, frozen-input lineage, collector lineage/runtime side effects, evidence-clock gate/status regressions, and DQ manifest runtime side effects.
- Source-static guard now pins validator blocker emit order across market-data provenance, frozen inputs, collector run, DQ manifest, and evidence-clock validators including side-effect and status blockers.
- Verification passed: Phase3 evidence source static `16`, Rust acceptance `24`, full `cargo test -p openclaw_types`, cargo fmt, docs trace, and diff-check. Boundary unchanged: no market-data ingestion, evidence clock runtime, IBKR contact, connector/runtime, secret access/serialization, scorecard/DB writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Broker Capability Registry Exact Blocker Guard

- PM tightened `StockEtfBrokerCapabilityRegistryV1` aggregate acceptance coverage to exact ordered blocker vectors for default registry posture, read-row gate gaps, registry identity/source mismatch, operation coverage, paper write/fill-import shape gaps, denied-row regressions, and boundary flags.
- Source-static guard now pins validator blocker emit order across registry top-level checks, operation coverage checks, and operation row validation checks.
- Verification passed: broker capability registry source static `9`, Rust acceptance `14`, full `cargo test -p openclaw_types`, cargo fmt, docs trace, and diff-check. Boundary unchanged: no Rust production code change, IBKR contact, connector/runtime, secret access/serialization, paper order route, fill import, evidence/scorecard/DB writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 No-Order Refresh Blocked By Loss-Control 6b0e

- PM rotated from stale `bef289ef...` request to clean `6b0e6b03...`; 6b0e source-stability READY sha `8b89bd88...` was produced but not consumed.
- Runtime SSH freshness check found standing auth sha `8c891b4e...` had only `80.377923s` remaining at `2026-07-01T17:14:45Z` and expired at `2026-07-01T17:16:05.473618+00:00`; final docs-sync fetch found `origin/main == c1d2ef4c...`.
- State transition `BLOCKED_BY_LOSS_CONTROL`; next blocker is `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`. No E3/BB dispatch, API GET, public quote, lease, order/private endpoint, runtime mutation, Cost Gate change, live/mainnet, fill/PnL, or proof.

## 2026-07-01 Stock/ETF Lane-Scoped IPC Exact Blocker Guard

- PM tightened `StockEtfLaneScopedIpcContractV1` aggregate acceptance coverage to exact ordered blocker vectors for default contract posture, top-level boundary regressions, command coverage/denied-method aggregates, command shape failures, and paper-order request-shape cross-wire cases.
- Source-static guard now pins validator blocker emit order across top-level IPC contract flags and command validation shape checks.
- Verification passed: lane-scoped IPC source static `7`, Rust acceptance `12`, full `cargo test -p openclaw_types`, cargo fmt, docs trace, and diff-check. Boundary unchanged: no IPC runtime/server, IBKR contact, connector/runtime, secret access/serialization, paper order route, result/fill import, evidence/scorecard/DB writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Readonly Probe Result Import Exact Blocker Guard

- PM tightened `StockEtfIbkrReadonlyProbeResultImportRequestV1` aggregate acceptance coverage to exact ordered blocker vectors for default, read-action/operation cross-wire, common/kind-specific lineage gaps, timestamp/replay, and no-side-effect boundary regressions.
- Source-static guard now pins validator blocker emit order across top-level identity, required lineage fields, kind-specific lineage, and boundary flags.
- Verification passed: readonly probe result-import source static `12`, Rust acceptance `11`, full `cargo test -p openclaw_types`, cargo fmt, docs trace, and diff-check. Boundary unchanged: no IBKR contact, connector/runtime, read-only probe execution, result import execution, secret access/serialization, paper order, evidence/scorecard/DB writer, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Readonly Probe Request Exact Blocker Guard

- PM tightened `StockEtfIbkrReadonlyProbeRequestV1` aggregate acceptance coverage to exact ordered blocker vectors for default, read-action/operation/authority cross-wire, pre-contact lineage/hash gaps, and no-side-effect boundary regressions.
- Source-static guard now pins validator blocker emit order across top-level identity, required pre-contact lineage fields, and boundary flags.
- Verification passed: readonly probe request source static `10`, Rust acceptance `10`, full `cargo test -p openclaw_types`, cargo fmt, docs trace, and diff-check. Boundary unchanged: no IBKR contact, connector/runtime, read-only probe execution, secret access/serialization, paper order, DB/evidence writer, evidence clock, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Shadow Signal Request Exact Blocker Guard

- PM tightened `StockEtfShadowSignalRequestV1` aggregate acceptance coverage to exact ordered blocker vectors for default, method/operation/scope cross-wire, lineage/hash gaps, and no-side-effect boundary regressions.
- Source-static guard now pins validator blocker emit order across top-level identity, required fields, and boundary flags.
- Verification passed: shadow signal source static `9`, Rust acceptance `9`, full `cargo test -p openclaw_types`, cargo fmt, docs trace, and diff-check. Boundary unchanged: no IBKR contact, connector/runtime, shadow signal emission, shadow fill generation, scorecard/DB/evidence writer, paper order, tiny-live/live, or Bybit behavior change.

## 2026-07-01 Stock/ETF Paper Shadow Reconciliation Exact Blocker Guard

- PM tightened `StockEtfPaperShadowReconciliationV1` aggregate acceptance coverage to exact ordered blocker vectors for default, scope/authority/effect cross-wire, lineage/hash gaps, reconciliation-evidence failures, and no-side-effect boundary regressions.
- Source-static guard now pins validator blocker emit order across top-level identity, required fields, reconciliation evidence, and boundary flags.
- Verification passed: reconciliation source static `10`, Rust acceptance `10`, full `cargo test -p openclaw_types`, cargo fmt, docs trace, and diff-check. Boundary unchanged: no IBKR contact, connector/runtime, fill import, shadow fill generation, reconciliation/scorecard writer, DB/evidence writer, tiny-live/live, or Bybit behavior change.

## 2026-07-07 IBKR Demo Ready Loop L0-L1 Stop

- PM ran the sentinel-triggered IBKR Demo Ready source audit through L0 and into L1; L0 baseline artifact advanced, L1 stopped because no immutable `phase2_ibkr_external_surface_gate_v1` PASS artifact, operator session/credential approval, secret-slot evidence, topology evidence, or session attestation exists.
- Verification passed Python Stock/ETF IBKR guard subset `26`; Rust focused gate tests were not runnable because local `~/.cargo/bin/rustup` is a broken symlink to `/opt/homebrew/bin/rustup-init`.
- Boundary unchanged: no IBKR contact, connector/runtime, secret read/serialization, paper order, fill import, DB/evidence writer, MCP runtime, live/tiny-live path, or Bybit order path reuse.

## 2026-07-07 IBKR Demo Ready API-Absent Engineering Loop

- New attached prompt changed the loop semantics: missing IBKR credential/session/operator approval/real Phase2 PASS artifact is `external_verification_pending`, not STOP. PM added `ibkr_demo_ready_api_absent_engineering_packet_v1` under the inert IBKR connector package and terminal report `2026-07-07--ibkr_demo_ready_api_absent_terminal_packet.md`.
- Verification passed focused Python IBKR/API-absent/static guard subset `29` and `py_compile`; broader Stock/ETF Python suite was `183 passed, 1 failed` due unrelated dirty `console.html`; Rust tests remain unrunnable because local rustup symlink is broken and no Rust source was changed.
- Terminal state for this prompt variant: `DEMO_READY_API_ABSENT`. Boundary unchanged: no IBKR contact, connector runtime, secret read/serialization, broker order route, fill import, DB/evidence writer, runtime MCP, live/tiny-live path, or Bybit order path reuse.

## 2026-07-07 IBKR Demo Ready Autonomous L8 Dispatch

- PM continued past `API_ABSENT_READY` into L8 as required. P0 broadened Stock/ETF suite is now green (`184 passed`); P1/P3 Rust no-contact parity was smoke-verified from existing local acceptance binaries (`126 passed` total across selected binaries) because local cargo/rustup remains broken.
- PM added exact `external_verification_readiness_fixture` to `ibkr_demo_ready_api_absent_engineering_packet_v1`, covering operator checklist, Gateway/TWS topology checklist, secret fingerprint checklist, and Phase2 real-contact runbook.
- Terminal state for this autonomous prompt: `ENGINEERING_BACKLOG_EXHAUSTED_EXTERNAL_ONLY_PENDING`. Boundary unchanged: no IBKR contact, secret read/serialization, connector runtime, broker route, fill import, DB/evidence writer, runtime MCP, live/tiny-live path, or Bybit order path reuse.
