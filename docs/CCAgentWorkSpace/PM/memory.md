# PM Memory — 工作記憶

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；agent 完成序列照常追加於檔尾。

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

## 2026-07-01 IBKR Connector Risky Config Blocker Guard

- PM added a source-only regression that forces risky IBKR connector endpoint config values to appear only as blockers across every inert preview payload.
- Verification passed: connector skeleton focused `9`, Python no-write/static/GUI guard focused `30`, and Stock/ETF Python route/static `121`.
- Boundary unchanged: no IBKR contact, SDK, secret, connector runtime, paper order, fill import, DB apply, evidence clock, tiny-live/live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Reconciliation GUI Contract Display

- PM split Stock/ETF reconciliation rendering into `tab-stock-etf-reconciliation.js`; main `tab-stock-etf.js` is now 1847 lines, below the 2000-line cap.
- The GUI now displays `stock_etf_paper_shadow_reconciliation_v1` contract id/acceptance/blockers, paper-shadow link hash, imported/synthetic markers, and reconciliation side-effect flags; the new JS is covered by route/static and no-write guards.
- Verification passed: Node syntax, GUI line counts, focused route/static/no-write `13`, and full Stock/ETF Python route/static `90`. This grants no IBKR contact, connector runtime, fill import, shadow fill generation, reconciliation/scorecard writer, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper-Shadow Reconciliation Contract

- PM added source-only `stock_etf_paper_shadow_reconciliation_v1` for paper lifecycle/fill facts, synthetic shadow fill linkage, frozen divergence thresholds, and unmatched-fill reconciliation checks.
- Phase0 manifest/count is now 32; Rust/FastAPI reconciliation status surfaces expose the contract id, accepted/blockers, paper-shadow link hash, imported/synthetic markers, and side-effect flags while staying default blocked.
- Verification passed: reconciliation acceptance `5`, Phase0 manifest `6`, FastAPI Phase0/reconciliation `9`, engine reconciliation focused `1`, engine Stock/ETF `27`, workspace cargo check PASS. This grants no IBKR contact, connector runtime, fill import, shadow fill generation, reconciliation/scorecard writer, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Authorization Status

- PM added source-only `stock_etf.get_authorization_status`, FastAPI `GET /api/v1/stock-etf/authorization-status`, and GUI `Authorization Status` / `Authorization Gate` display.
- Verification passed: Stock/ETF FastAPI/static `77`, engine Stock/ETF `18`, GUI/lane IPC `17`, openclaw_types `35 + 206 + 0 doc-tests`, workspace cargo check PASS.
- Boundary unchanged: no IBKR contact, secret access, connector runtime, paper order, DB apply, evidence clock, Linux runtime sync/restart, tiny-live/live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Split Hygiene

- PM split accumulated Stock/ETF tab inline JS from `tab-stock-etf.html` into `tab-stock-etf.js`; line counts are now 341 and 1883, both below the 2000-line hard cap.
- Static no-write guards now scan the HTML+JS bundle; verification passed with JS syntax check, inline parser, Stock/ETF FastAPI/static `77`, and diff-check.
- Boundary unchanged: no new endpoint, IBKR contact, secret, connector runtime, paper order, DB apply, Linux runtime sync/restart, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Disable Cleanup Status

- PM added source-only `stock_etf.get_disable_cleanup_status`, FastAPI `GET /api/v1/stock-etf/disable-cleanup-status`, and GUI `Disable / Cleanup Status` / `Disable Cleanup` display.
- The surface shows only the `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` source-ready shape while runtime cleanup/launch fields remain blocked false; `tab-stock-etf-disable-cleanup.js` keeps the main Stock/ETF JS below the 2000-line cap.
- Verification passed: Stock/ETF FastAPI/static `81`, engine Stock/ETF `19`, openclaw_types `stock_etf` filter PASS, Node checks, inline parser, and line caps 359/1895/132.
- Boundary unchanged: no IBKR contact, secret access/creation, connector runtime, collector stop, GUI hide, archive, DB cleanup/apply, paper order, fill import, evidence clock, scorecard writer, Linux runtime sync/restart, paper-shadow launch, tiny-live/live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Release Packet Status

- PM added source-only `stock_etf.get_release_packet_status`, FastAPI `GET /api/v1/stock-etf/release-packet-status`, and GUI `Release Packet Status` / `Release Packet` display.
- The surface shows only the `stock_etf_release_packet_v1` source fixture plus disable-cleanup proof summary while runtime launch, writer, DB, evidence-clock, order, secret, contact, and Bybit-reuse fields remain blocked false; `tab-stock-etf-release-packet.js` keeps the main Stock/ETF JS below the 2000-line cap.
- Verification passed: Stock/ETF FastAPI/static `85`, engine Stock/ETF `20`, full openclaw_types PASS, workspace cargo check PASS, Node checks, and inline parser.
- Boundary unchanged: no IBKR contact, secret access/creation, connector runtime, release packet materialization, paper-shadow launch, paper order, fill import, evidence clock, scorecard writer, Linux runtime sync/restart, Phase 2/3/5 start, tiny-live/live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Market-Data Provenance Contract

- PM hardened `stock_market_data_provenance_v1` inside the Phase 3 evidence contract surface for lane/broker/environment, vendor/entitlement, payload/source hashes, timestamps, adjustment marker, instrument identity, and calendar session provenance.
- The validator rejects Bybit-live regression, IBKR contact, connector runtime, serialized secrets, and tiny-live/live authority; broker capability gates now require it for market-data read, shadow-fill reconstruction, and scorecard derivation.
- Verification passed: focused linked openclaw_types tests `25 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `171` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, collector, market-data ingestion, evidence clock, scorecard writer, DB apply, GUI lane authority, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Python No-Write Static Guard

- PM added `test_stock_etf_python_no_write_static_guard.py` as an AST/static guard for Stock/ETF/IBKR Python surfaces and future `program_code/broker_connectors/ibkr_connector/` files.
- The guard rejects direct broker write functions/calls, forbidden paper-order IPC method strings, direct `ibapi` / `ib_insync` imports, and non-GET Stock/ETF/IBKR routes while intentionally excluding existing Bybit modules.
- This grants no IBKR contact, connector runtime, paper order, DB apply, evidence clock, GUI lane authority, release approval, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Reference Data Sources Contract

- PM added `stock_etf_reference_data_sources_v1` as a Rust source-only validator for corporate-action, FX, fee, tax/FTT, and withholding-treatment source-as-of records.
- The contract is wired into the Phase 0 manifest, Phase 3 frozen inputs, and broker capability shadow-fill / scorecard gates; blocked template and acceptance tests are included.
- Verification passed: focused linked openclaw_types tests `28 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `168` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, collector, scorecard writer, DB apply, GUI lane authority, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Phase 0 Manifest Contract

- PM added `stock_etf_phase0_contract_packet_manifest_v1` as a Rust source-only validator for the Phase 0 machine-readable manifest.
- The contract pins schema/status/scope, ADR/AMD/packet paths, loopback paper API baseline, all global denials, exact named contract list, and fail-closed phase unlocks.
- This grants no IBKR contact, connector runtime, paper order, DB apply, evidence clock, GUI lane authority, release approval, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Disable-Cleanup Runbook Contract

- PM added `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` as a Rust source-only validator for exact kill flags, collector stop, GUI disabled/hidden posture, live-secret absence, forward-only archive/DB retention, append-only audit, and Bybit live unchanged proof.
- The contract rejects IBKR contact, connector runtime, paper order routing, secret-slot creation, secret serialization, destructive DB cleanup, DB delete/truncate permission, release authority, tiny-live, and live authority.
- This grants no IBKR contact, connector runtime, paper order, DB apply, evidence clock, GUI lane authority, release approval, tiny-live, or live.

## 2026-06-30 Bounded Demo Connector Mode Cutover

- PM confirmed `BYBIT_MODE=read_only` was a local runtime connector gate, not a Bybit dashboard/API-key permission. Operator-confirmed Demo key remains `FWkGZX...g53T`; mainnet stayed disabled with `OPENCLAW_ALLOW_MAINNET=0`.
- Approved settings API cutover persisted `BYBIT_MODE=demo` and `BYBIT_CONNECTOR_WRITE_ENABLED=true`; readiness sha `e4cad133...` is now `BOUNDED_DEMO_RUNTIME_READY_FOR_FINAL_WINDOW_GATES`.
- Runtime hygiene lesson: `restart_all.sh` manual API launch can fight `openclaw-trading-api.service`; PM reclaimed API under systemd MainPID `1038429`, added restart_all API env pass-through, and verified settings `restart_required=false`. This is not promotion proof; final-window gates and candidate-matched fills still remain.

## 2026-06-30 IBKR Stock/ETF Broker Capability Registry Contract

- PM added `broker_capability_registry_v1` as a Rust source-only validator for the full IBKR Stock/ETF read/paper/shadow/scorecard/denied operation matrix.
- The contract requires Bybit live unchanged, Python broker write authority denied, Rust-owned paper writes, required gates/audit/source hashes, and exact typed denials for live/margin/short/options/CFD/transfer/account writes.
- This grants no IBKR contact, connector runtime, paper order, GUI authority, tiny-live, live, or secret access.

## 2026-06-30 IBKR Stock/ETF DB Evidence DDL Contract

- PM added `stock_etf_db_evidence_ddl_v1` as a Rust source-only validator for broker/research/audit schemas, evidence tables, natural keys, lane/broker/live-denial constraints, paper/shadow separation, Guard A/B/C, and future PG dry-run/double-apply requirements.
- The blocked template and tests reject migration path promotion, DB apply, PG write, sqlx registration, PM/Operator apply authorization claims, and secret serialization.
- This does not authorize migration apply, IBKR contact, connector runtime, paper orders, audit writer, evidence clock, GUI lane authority, tiny-live, or live.

## 2026-06-30 Bounded Demo Key Expected Prefix False Positive

- PM accepted operator correction: masked `FWkGZX...g53T` is the correct Bybit Demo Read-Write key with OpenAPI whitelist `79.117.10.224`; the old `BHw4...` mismatch was a stale expected-prefix hint, not a live/mainnet key issue.
- `bounded_demo_runtime_readiness.py` now treats expected Demo key sha/prefix mismatch as advisory unless `--require-expected-demo-api-key-match` is explicit. Runtime still blocks on connector mode (`BYBIT_MODE=read_only`, write disabled), serving/proof repair, and missing candidate-matched fills.
- PM read: next path is fresh readiness without stale expected pin, reviewed Demo-only connector cutover if green, then final-window gates; do not rewrite secrets or infer promotion proof from the key correction.

## 2026-06-29 IBKR Stock/ETF Plan Round 3 Launch Certification

- PM integrated CC/FA/PA/E3/E5/QC/MIT/QA third-round launch-certification: all eight roles returned `CERTIFIABLE_IF_GATES_PASS`, `SCOPE=paper_shadow_only`, `FINDINGS=0`.
- Conditional sign-off wording is `PAPER_SHADOW_LAUNCH_CERTIFIABLE_IF_ALL_GATES_PASS`: only after Phase 0 named contract packet is accepted and Phase 1-5 gates all pass can paper/shadow lane be signed off as complete.
- Current state remains not launch-ready; live/tiny-live, profitability claims, durable alpha proof, and any promotion beyond paper/shadow stay excluded.

## 2026-06-29 IBKR Stock/ETF Plan Round 2 Review

- PM integrated CC/FA/PA/E3/E5/QC/MIT/QA second-round adversarial review: every role returned `APPROVE_PHASE0_ONLY`; no role certified no-omission or scheduled full-online readiness.
- Main plan now treats Phase 0 as ADR/AMD plus named contract packet: broker capability registry, external-surface gate, lane IPC, paper lifecycle, DDL/evidence, GUI contract, evidence clock, release packet, storage/capacity, and disable cleanup runbook.
- Still blocked: Phase 1+ code, IBKR healthcheck/API/secret/fill import/paper order, GUI runtime, evidence clock, tiny-live/live; correct next step is Phase 0 contract packet only.

## 2026-06-29 IBKR Stock/ETF Plan Adversarial Review

- PM integrated CC/FA/PA/E3/QC/MIT review of the IBKR `stock_etf_cash` paper/shadow plan: direction valid, but Phase 0 ADR/spec only; Phase 1+, IBKR API, secret slots, paper orders, GUI runtime enablement, and evidence clock remain blocked.
- Main blockers added back to the plan: IBKR API/session baseline, broker-paper attestation, Rust lane-scoped IPC/order lifecycle, Python no-write connector boundary, DB evidence contract, flag/secret invariants, GUI display-only lane selector, and pre-registered QC/MIT evidence gates.

## 2026-06-29 External Repo Integration Review

- PM closed six-subagent evaluation of `xbtlin/ai-berkshire` and `AgriciDaniel/claude-obsidian` as conditional read-only only: both are useful as research/retrieval/report-QA inspiration, not runtime/trading/alpha proof.
- Approved next step is scratch smoke only (`/tmp/openclaw/...`): BM25-only docs retrieval + report-audit style AEG/PM checks, with zero repo/runtime/DB/network/LLM/order/config mutation.
- Blocked: direct skill install, Obsidian hooks/MCP/vault SoT, shell `flock` workflows, ContextDistiller prompt injection before ADR-0041 token ledger, and any external narrative/performance claim as alpha evidence.

## 2026-06-27 Bounded Demo Probe Soak Enabled

- PM closed this loop as `DONE_WITH_CONCERNS`: runtime source is clean at `bb15288b`, engine PID `4136267` runs Demo-only with writer/adapter enabled, and `/proc` binary sha matches disk `d7c80e...`.
- Soak plan `/tmp/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json` sha `91812ebc...` came from plan-inclusion sha `9527fb8e...`; adapter-off dry-run stayed `ADAPTER_DISABLED`, adapter-on hypothetical was `ADMIT_DEMO_LEARNING_PROBE`.
- Post-restart verification sha `624caaec...` has ticks but `total_intents=0`, `total_fills=0`, and unchanged ledger; no order/fill/fee/slippage/after-cost proof exists yet. Heartbeat monitor `openclaw-bounded-demo-probe-soak-monitor` should refresh auth/plan before expiry or collect fill evidence.

## 2026-06-27 Same-Lineage Downstream Refresh

- PM closed the v654 GUI cap mismatch as `DONE_WITH_CONCERNS`: preflight/touchability/placement/auth/admission were rebuilt from standing auth cap `954.93892693 USDT`; local `10 USDT` authority remains false.
- Bounded auth sha `c66dd527...` is valid for the current candidate, and admission sha `69e905ad...` now blocks only on `decision_lease_valid` and `fresh_bbo_refresh_at_actual_admission`.
- Next is same-window active Demo Decision Lease plus actual-admission BBO/gate evidence without order submission; do not promote the timestamped auth object by itself.

## 2026-06-27 Current Candidate Admission With Rust Authority Evidence

- PM advanced the no-order admission review as `BLOCKED_BY_LOSS_CONTROL`: runtime Rust authority readiness sha `d0459cc...` clears `rust_authority_path_valid` for `grid_trading|AVAXUSDT|Sell`.
- Review sha `5a5b28c...` keeps GUI cap `955.24342626 USDT` and active runtime probe/order authority false; remaining blockers are Decision Lease, Guardian risk gate, and fresh actual-admission BBO.
- Next is no-order machine-checkable Decision Lease / Guardian evidence; do not execute or refresh actual-admission BBO outside reviewed runtime-admission scope.

## 2026-06-27 GUI Risk Cap Runtime Source Sync

- PM closed the runtime helper prerequisite as `DONE_WITH_CONCERNS`: `trade-core` fast-forwarded `9fecf84f -> 665b2eef`, and 11 crontab expected-head pins now point to `665b2eef`.
- Runtime focused cap/equity/quote helper verification passed `66`; API/watchdog PIDs stayed `2218842`/`1538268`; no service restart, cron run, Bybit, PG, order path, Cost Gate lowering, risk expansion, or authority/proof happened.
- Current AVAX control identity and construction preview latest artifacts remain missing; next is reviewed PM -> E3 -> BB no-order public quote/current-construction refresh, not another sync or equity capture.

## 2026-06-27 GUI Cap Touchability Placement Refresh

- PM closed the no-order GUI-cap placement refresh as `DONE_WITH_CONCERNS`: timestamped placement now carries `955.24342626 USDT` from GUI/Rust RiskConfig instead of stale `10.0`.
- Bounded auth is `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, `decision=defer`, `blocking_gates=[]`, but emits no auth object and grants no active probe/order authority.
- Next is a separate bounded auth object review from the valid standing Demo authorization; execution remains blocked by Decision Lease, Guardian/Rust admission, fresh BBO, auditability, and reconstructability.

## 2026-06-27 GUI Risk Cap Runtime Cache Reconcile

- PM closed timestamped runtime cache-only reconcile as `DONE_WITH_CONCERNS`: fast-balance GET on `trade-core` returned `rust_snapshot_fast/connected` equity `9552.43426257`; accepted artifact sha `afea4d...`.
- Worksheet accepted the equity artifact and resolved GUI 10% cap to `955.24342626 USDT`, proving the GUI setting is percent-based, while fail-closing order admission as `CONTROL_IDENTITY_CONTRACT_INPUT_NOT_READY`.
- Current AVAX construction inputs remain missing/stale; do not reuse 2026-06-24 construction or 2026-06-25 cap-feasible selection as current evidence. Runtime source sync is now superseded by the 2026-06-27 source-sync entry above; next is reviewed no-order public quote/current-construction refresh.

## 2026-06-27 Demo Fast-Balance Equity Artifact Source

- PM closed the source producer sub-checkpoint as `DONE_WITH_CONCERNS`: `demo_fast_balance_equity_artifact.py` now emits `demo_account_equity_artifact_v1` from supplied/captured `/api/v1/strategy/demo/balance?fast=1` `rust_snapshot_fast` payloads.
- The worksheet now requires artifact status `DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY`; schema shape alone no longer resolves GUI risk cap. Unit integration confirms GUI 10% over equity `200` resolves `20.0 USDT`, while construction `cap_usdt=10` remains diagnostic-only.
- No runtime/control API capture, Bybit call, PG, order path, Cost Gate lowering, risk expansion, or authority/proof happened. Next remains PM -> E3 -> BB reviewed cache-only capture plus current-candidate no-order construction refresh/reconcile.

## 2026-06-27 GUI Risk Cap Equity Artifact Gate Rotated No-Order

- PM advanced the cap resolver blocker as `ROTATED`: runtime `_latest` artifacts observed at `2026-06-27T00:45Z` rotated to `grid_trading|AVAXUSDT|Sell`, so ETH-specific construction refresh is no longer current.
- `current_cap_staircase_risk_worksheet.py` now requires accepted `demo_account_equity_artifact_v1` from `/api/v1/strategy/demo/balance?fast=1` `rust_snapshot_fast`; naked `account_equity_usdt` fails closed and cannot resolve cap.
- Next blocker is current-candidate drift reconcile plus audited Demo fast-balance equity artifact capture/review; no runtime sync, Bybit call, PG, order path, Cost Gate lowering, or authority/proof happened.

## 2026-06-27 GUI Risk Cap Source Correction

- PM closed source/test/docs correction as `DONE_WITH_CONCERNS`: GUI/Rust RiskConfig is risk source of truth; GUI `P1 Risk/Trade=10.0%` maps to TOML `per_trade_risk_pct=0.1`, not `10 USDT`.
- Rust bounded-probe active order `DEFAULT_MAX_DEMO_NOTIONAL_USDT_PER_ORDER=10.0` is a separate local envelope, not global risk authority. Do not use it as the single-order exposure cap.
- `current_cap_staircase_risk_worksheet.py` now derives `resolved_cap_usdt` from GUI-backed RiskConfig plus auditable equity; quote/atomic runner no longer default-injects `10.0`; next blocker is GUI-risk cap resolver before any ETH construction refresh/admission.

## 2026-06-27 Aligned ETH Runtime Admission Review Blocked By Loss Control

- PM/E3/BB closed `P0-ALIGNED-ETH-RUNTIME-ADMISSION-EXECUTION-ENVELOPE-REVIEW` as `BLOCKED_BY_LOSS_CONTROL`.
- Timestamped noncanonical plan-inclusion diagnostic `/tmp/openclaw/aligned_eth_runtime_admission_review_20260627T000135Z/bounded_probe_plan_inclusion_review.json` is `CONSTRUCTION_PREVIEW_NOT_READY`; manifest problems `[]`; no latest overwrite, adapter enablement, ledger append, Bybit/PG/order path, Cost Gate lowering, or proof claim.
- ETH Buy is not constructible under the standing 10 USDT cap (`min_positive_qty_notional_usdt=15.7105`), so next blocker is cap-feasible candidate rotation or fresh ETH no-order construction refresh review without cap/risk expansion.

## 2026-06-27 Aligned ETH Bounded Authorization Review

- PM/E3/BB closed `P0-ALIGNED-ETH-BOUNDED-AUTHORIZATION-REVIEW` as `DONE_WITH_CONCERNS`.
- Timestamped noncanonical artifact `/tmp/openclaw/aligned_eth_bounded_authorization_review_20260626T234532Z/bounded_probe_operator_authorization_authorize_review.json` emitted a scoped ETHUSDT/Buy auth object with cap `2`, but canonical `_latest` stayed `defer` with no auth object and no active runtime probe/order authority.
- Next blocker at that time was `P0-ALIGNED-ETH-RUNTIME-ADMISSION-EXECUTION-ENVELOPE-REVIEW`; that checkpoint is now closed as blocked by loss control, so do not promote `_latest`, include in a plan, enable adapter/writer, or execute this ETH path unless a fresh cap-feasible review replaces it.

## 2026-06-27 Standing Demo Current-Candidate Downstream Alignment Apply

- PM/E3 closed `P0-STANDING-DEMO-CURRENT-CANDIDATE-DOWNSTREAM-ALIGNMENT-REVIEW` as runtime `DONE_WITH_CONCERNS`.
- Canonical downstream artifacts now align to `grid_trading|ETHUSDT|Buy`; bounded auth latest is `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, `decision=defer`, no auth object, no active probe/order authority.
- Next blocker at that time was a separate `PM -> E3 -> BB -> PM` bounded authorization review for the aligned ETH candidate; this is now superseded by the 2026-06-27 bounded authorization review entry above.

## 2026-06-27 Standing Demo Loss-Control Envelope Runtime Materialization Apply

- PM/E3 closed `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-RUNTIME-MATERIALIZATION-E3-REVIEW` as `DONE_WITH_CONCERNS`.
- Runtime source/crontab pins are aligned at `9fecf84f...`; a `0600` standing Demo envelope is materialized for current `grid_trading|ETHUSDT|Buy` with cap `2` and no live/mainnet/Cost Gate/order authority.
- Targeted verification makes false-negative review/preflight ready, but bounded auth remains `defer`/no-object because canonical downstream placement artifacts are still AVAX; next blocker is current-candidate downstream alignment.

## 2026-06-27 Standing Demo False-Negative Preflight Runtime Sync Apply

- PM/E3 closed `P1-RUNTIME-HEALTH-HYGIENE-STANDING-DEMO-FALSE-NEGATIVE-PREFLIGHT-SYNC-REVIEW` as `DONE_WITH_CONCERNS`.
- Runtime source and crontab expected-head pins are aligned at `e29c96cc...`; sync changed no service, order, PG, Cost Gate, adapter, standing-env, explicit-authorize, or authority state.
- Natural artifacts still fail closed because no runtime standing envelope is configured; next blocker is `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-RUNTIME-MATERIALIZATION-REVIEW`.

## 2026-06-27 Standing Demo False-Negative Preflight Source Plumbing

- PM closed `P0-STANDING-DEMO-FALSE-NEGATIVE-PREFLIGHT-PLUMBING` as source/test/docs `DONE_WITH_CONCERNS`.
- False-negative review/preflight can now consume a fresh, scoped `standing_demo_operator_authorization_v1` and fail closed for absent/invalid/stale/live/scope-mismatched envelopes; scheduled cron no longer auto-switches bounded auth to `authorize` just because standing JSON exists.
- Runtime remains unsynced at `69f6c4b2...`; next blocker is E3-reviewed runtime source/expected-head sync, not execution or profit proof.

## 2026-06-26 Standing Demo Auth Plumbing Runtime Sync Apply

- PM closed `P1-RUNTIME-HEALTH-HYGIENE-STANDING-DEMO-AUTH-PLUMBING-SYNC-REVIEW` as `DONE_WITH_CONCERNS`.
- Runtime source and crontab expected-head pins are aligned at `69f6c4b2...`; sync changed no service, order, PG, Cost Gate, adapter, or authority state.
- Natural artifacts still fail closed at false-negative review/preflight, so the next source-progress blocker is `P0-STANDING-DEMO-FALSE-NEGATIVE-PREFLIGHT-PLUMBING`.

## 2026-06-26 Standing Demo Authorization Plumbing Source Fix

- PM closed `P0-STANDING-DEMO-AUTHORIZATION-PLUMBING` as source/test/docs `DONE_WITH_CONCERNS`.
- Standing Demo JSON can now derive candidate-scoped auth id/budget/expiry, and cost-gate/alpha cron wrappers consume it only via explicit env path while defaulting to `defer`.
- Runtime remains unsynced at `b224c759...`; next blocker is E3-reviewed runtime source/expected-head sync, not bounded execution.

## 2026-06-26 Auth Typed-Confirm Guard Runtime Sync Apply

- PM closed `P1-RUNTIME-HEALTH-HYGIENE-AUTH-TYPED-CONFIRM-GUARD-RUNTIME-SYNC-APPLY` as `DONE_WITH_CONCERNS`.
- Runtime source fast-forwarded `dd22810e -> b224c759`; crontab expected-head old/target `11/0 -> 0/11`; line count stayed `70`; API MainPID `2218842` and watchdog MainPID `1538268` stayed active/running.
- Natural auth sha `fb2d05e...` now suppresses exact `typed_confirm_expected` and emits template + `PREFLIGHT_NOT_READY`, but still has no authorization id or probe/order authority. P0 auth remains blocked by missing machine-checkable scoped authorization.

## 2026-06-26 Auth Typed-Confirm Guard Runtime Sync Review No-Apply

- PM/E3 closed `P1-RUNTIME-HEALTH-HYGIENE-AUTH-TYPED-CONFIRM-GUARD-RUNTIME-SYNC-REVIEW` as read-only `DONE_WITH_CONCERNS_NO_APPLY` because the operator requested pause after TODO normalization.
- New runtime delta: source/origin is `b224c759`, runtime remains `dd22810e`, crontab pins old/new `11/0`, and natural auth sha `351bd18b...` still emits stale `authorize_bounded_demo_probe:grid_trading|AVAXUSDT|Sell:0:` with no authorization id or authority.
- E3 says future apply is justified only as atomic runtime source sync plus all 11 expected-head pin replacements; no restart, cron run, PG, Bybit/order, Cost Gate, writer/adapter, or authority change.

## 2026-06-26 Auth Typed-Confirm Guard Source Fix

- PM closed `P0-BOUNDED-PROBE-AUTHORIZATION-TYPED-CONFIRM-GUARD` as source/test/docs `DONE_WITH_CONCERNS`.
- Auth packets now suppress exact `typed_confirm_expected` until preflight is ready and positive budget plus authorization id are present; stale/impossible `authorize_bounded_demo_probe:...:0:` strings should not be copied.
- PM read: latest runtime auth `af337e48...` is still AVAX defer/no authority. The fix improves review safety only; it does not authorize a probe.

## 2026-06-26 Runtime Source Sync Apply Go/No-Go No-Apply

- PM/E3 closed `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-APPLY-REVIEW` as read-only `DONE_WITH_CONCERNS_NO_APPLY`.
- `dd22810e..370a3d82` drift is docs/reports/TODO/worklog/changelog/SCRIPT_INDEX plus source-only cost-gate research helpers/tests; no Rust/FastAPI/cron/canary/deploy/service/migration/Cargo/crontab paths, and runtime pins remain internally consistent at `dd22810e`.
- PM read: do not reopen apply review for docs/source-only research drift alone. P0 auth still needs real scoped auth; shadow placement sample mismatch is not proof or authority.

## 2026-06-26 API Process Ownership Read-Only

- PM closed `P1-RUNTIME-HEALTH-HYGIENE-API-PROCESS-OWNERSHIP` as read-only `DONE_WITH_CONCERNS`.
- Runtime API/watchdog ownership is established under `systemctl --user`: API MainPID `2218842`, watchdog MainPID `1538268`, and API cgroup `app.slice/openclaw-trading-api.service`.
- PM read: do not repeat manual-vs-service ownership audit without unit/PID/cgroup change. P0 auth remains blocked because latest auth sha `e7420e21...` is still AVAX defer/no authority.

## 2026-06-26 Runtime Source Sync Review No-Apply

- PM/E3 closed `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-REVIEW-NO-APPLY` as `DONE_WITH_CONCERNS`.
- Runtime is clean and internally consistent at `dd22810e`; 11 cron expected-head pins also point to `dd22810e`; source/origin is `beeef498`.
- E3 found no security blocker to a future sync, but no apply is needed now. Future apply, if opened, must fast-forward runtime source and update all 11 expected-head pins in one checkpoint; do not change pins alone.
- Latest auth sha `167af613...` remains AVAX defer/no auth object/no active authority. PM read: P0 auth remains blocked; any public quote runner still needs separate PM->E3->BB review.

## 2026-06-26 Anti-Repeat TODO + Runtime Hygiene Reconcile

- PM closed `P1-RUNTIME-HEALTH-HYGIENE-ANTI-REPEAT-TODO-RECONCILIATION-NO-APPLY` as docs/state `DONE_WITH_CONCERNS`.
- TODO v575 now marks `P1-LEARNING-LOOP-CLOSURE` and `P1-AUTONOMOUS-PARAMETER-PROPOSAL` as DONE/no-repeat using the 2026-06-24 reports; do not rerun them.
- Runtime auth latest sha `c956288b...` remains AVAX defer/no auth object/no active authority; runtime head and cron expected-head pins remain `dd22810e` while source/origin is `26a203b`.
- PM read: no runtime apply happened. If continuing without auth delta, next safe item is `P1-RUNTIME-HEALTH-HYGIENE-SOURCE-SYNC-REVIEW-NO-APPLY`, not crontab/source sync.

## 2026-06-26 Candidate Source Freshness Alignment + Atomic Preview Runner

- PM closed `P1-AGGRESSIVE-ALPHA-CANDIDATE-SOURCE-FRESHNESS-ALIGNMENT-NO-CAPTURE` as `DONE_WITH_CONCERNS`.
- Source fix maps `cap_usdt` into `current_cap_usdt` for ready lower-price reroute packets while preserving explicit zero; fresh AVAX reroute sha `bc300277...` is ready with `current_cap_usdt=10.0`.
- Added `atomic_quote_adapter_preview_runner.py`; one E3/BB-reviewed run produced summary sha `98c7d75...` and construction preview sha `f721bc3...`, ready no-order under `1000ms` freshness. QA found no blocker; all grant/order/proof flags remain false.
- PM read: pause now. Next is still `P0-BOUNDED-PROBE-AUTHORIZATION`, blocked until a candidate-scoped auth object or exact typed confirm passes repo gates; do not repeat quote/runner work without new evidence and E3/BB review.

## 2026-06-26 Atomic Quote Adapter Preview Runtime Review No-Capture

- PM closed `P1-AGGRESSIVE-ALPHA-ATOMIC-QUOTE-ADAPTER-PREVIEW-RUNTIME-REVIEW` as `DONE_WITH_CONCERNS` without capture.
- BB found no Bybit-side blocker for the public market-data envelope, but E3 blocked the exact run because `_latest` reroute sha `fcd7f925...` is stale for construction preview's `24h` max artifact age; fresh timestamped reroute sha `97021201...` is `LOWER_PRICE_REROUTE_ALIGNMENT_BLOCKED`.
- PM read: do not rerun the exact capture envelope. Next if no real auth delta is source/artifact-only candidate-source freshness/alignment; no public quote capture until source alignment is fixed or scope is re-reviewed.

## 2026-06-26 Atomic Quote Adapter Preview Design No-Capture

- PM closed `P1-AGGRESSIVE-ALPHA-ATOMIC-QUOTE-ADAPTER-PREVIEW-DESIGN-NO-CAPTURE` as source/test/docs `DONE_WITH_CONCERNS`.
- Added `atomic_quote_adapter_preview_design.py`; smoke is `ATOMIC_QUOTE_ADAPTER_PREVIEW_DESIGN_READY_NO_CAPTURE_NO_AUTHORITY`, requiring future capture->adapter->no-order-preview to run as one reviewed atomic flow with `1000ms` freshness, adapter provenance, no generated_at override, no raw quote construction, and no order authority.
- E2 follow-up closed after PM added structured stale-adapter CLI evidence, broader positive authority text detection, and path-resolved runtime output rejection; final E4 verification passed focused `10` and adjacent `73`.
- PM read: this is still no-capture/no-runtime. Next if continuing is PM->E3->BB runtime review for exactly one atomic public quote capture + immediate local adapter/preview flow.

## 2026-06-26 Quote-To-Adapter Freshness Review No-Order

- PM closed `P1-AGGRESSIVE-ALPHA-QUOTE-TO-ADAPTER-FRESHNESS-REVIEW-NO-ORDER` as `DONE_WITH_CONCERNS`.
- Existing `public_quote_market_snapshot_adapter.py` refused v570 quote sha `4d46d88a...` with `public_quote_stale_at_adapter_generation`; no market snapshot or construction preview was emitted.
- PM read: do not rerun capture or forge adapter time. Next useful source-only blocker is an atomic quote->adapter->preview no-capture design; future actual capture still requires PM->E3->BB.

## 2026-06-26 Public Quote Capture Runtime Review

- PM closed `P1-AGGRESSIVE-ALPHA-PUBLIC-QUOTE-CAPTURE-RUNTIME-REVIEW` as `DONE_WITH_CONCERNS` after E3 and BB both cleared exactly one PM-run public/read-only AVAX quote capture.
- Capture artifact `/tmp/openclaw/public_quote_capture_runtime_review_20260626T092300Z/public_quote.json` is `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER`: bid/ask `6.212/6.213`, spread `1.609658bps`, effective BBO age `529.314ms`, instrument `Trading`, tick `0.001`, qty step `0.1`, min notional `5.0`.
- PM read: this is quote evidence only, not profit proof, order admission, or authority. Do not repeat capture without a new review. Operator asked to pause after this round; next after resume is no-order quote-to-adapter freshness review unless a real AVAX auth delta appears.

## 2026-06-26 Reviewed Public Quote Capture Packet No-Capture

- PM closed `P1-AGGRESSIVE-ALPHA-REVIEWED-PUBLIC-QUOTE-CAPTURE-PACKET-NO-CAPTURE` as source/test/docs `DONE_WITH_CONCERNS`.
- Added no-authority helper `reviewed_public_quote_capture_packet.py`; smoke defines exact future public GET-only AVAX quote capture envelope, response hash/timestamp/freshness requirements, adapter handoff, maker-policy spread/cost guard, and PM->E3->BB checklist.
- PM read: this still does not call Bybit or permit runtime quote capture. Next checkpoint is an exchange-facing public quote capture runtime review; do not run capture without the PM->E3->BB chain and no private/order/auth path checks.

## 2026-06-26 Maker-First Micro-Tier Placement Policy

- PM closed `P1-AGGRESSIVE-ALPHA-MAKER-FIRST-MICRO-TIER-PLACEMENT-POLICY-NO-ORDER` as source/test/docs `DONE_WITH_CONCERNS`.
- Added no-authority helper `maker_first_micro_tier_policy.py`; smoke selects the smallest current-cap AVAX tier as primary review tier (`0.9 AVAX / 5.4576 USDT`) and fixes post-only maker-first limit-or-skip, spread/cost skip, and taker-fallback fail-closed rules.
- PM read: this still does not capture quotes, call Bybit, admit orders, or grant authority. Operator asked to pause after this round; on resume, real P0 auth delta takes precedence, otherwise next source-only work is reviewed public quote capture packet design with no capture.

## 2026-06-26 Fresh BBO Read-Only Readiness Path

- PM closed `P1-AGGRESSIVE-ALPHA-FRESH-BBO-READONLY-READINESS-PATH-NO-ORDER` as source/test/docs `DONE_WITH_CONCERNS`.
- Added no-authority helper `fresh_bbo_readonly_readiness_path.py`; smoke defines future public quote capture requirements for exact AVAX identity, public GET-only allowlist, no auth/private/order paths, `max_fresh_bbo_age_ms=1000`, BBO/instrument sanity, and adapter-backed handoff before construction preview.
- PM read: this still does not perform quote capture or grant order admission. If no real auth delta appears, next source-only work is maker-first micro-tier placement policy.

## 2026-06-26 Fee/Slippage/Maker-Taker Schema Contract

- PM closed `P1-AGGRESSIVE-ALPHA-FEE-SLIPPAGE-MAKER-TAKER-SCHEMA-NO-ORDER` as source/test/docs `DONE_WITH_CONCERNS`.
- Added no-authority helper `fee_slippage_maker_taker_schema_contract.py`; smoke requires future AVAX proof/control rows to carry actual fee, actual slippage, maker/taker/post-only labels, order/fill lineage, and reconstructable net PnL after fees/slippage.
- PM read: this is not proof and not order admission. Operator requested pause after this round; on resume, real P0 auth delta takes precedence, otherwise next source-only work is fresh BBO read-only readiness path.

## 2026-06-26 Current-Cap Staircase Risk Worksheet

- PM closed `P1-AGGRESSIVE-ALPHA-CURRENT-CAP-STAIRCASE-RISK-WORKSHEET-NO-ORDER` as source/test/docs `DONE_WITH_CONCERNS`.
- Added no-authority helper `current_cap_staircase_risk_worksheet.py`; smoke shows AVAX Sell constructible under existing `10 USDT` cap with 8 tiers, min `0.9 AVAX / 5.4576 USDT`, max `1.6 AVAX / 9.7024 USDT`, 3-order review reserve `30 USDT`, cap/risk mutation false.
- PM read: order admission remains false because BBO is stale and there is no bounded auth. If no real auth delta, next source-only work is fee/slippage/maker-taker schema.

## 2026-06-26 Source-Only Control Identity Contract

- PM closed `P1-AGGRESSIVE-ALPHA-SOURCE-ONLY-CONTROL-IDENTITY-CONTRACT-NO-ORDER` as source/test/docs `DONE_WITH_CONCERNS`.
- Added no-authority helper `source_only_control_identity_contract.py`; smoke requires AVAX future proof rows to exact-match side-cell/strategy/symbol/side/horizon, requires same-side-cell blocked controls, and marks cross-symbol controls research-only/not proof.
- Runtime auth latest refreshed at `2026-06-26T08:00:05Z` but remains AVAX defer/no-authority. PM read: do not rerun P0 auth on that artifact; if no real auth delta, next source-only work is current-cap staircase/risk worksheet.

## 2026-06-26 Evidence-Floor Gap-Closure Design

- PM closed `P1-AGGRESSIVE-ALPHA-EVIDENCE-FLOOR-GAP-CLOSURE-DESIGN-NO-ORDER` as source/test/docs `DONE_WITH_CONCERNS`.
- Added no-authority helper `false_negative_evidence_floor_gap_closure.py`; smoke on the ranking packet outputs AVAX Sell gap design with `gap_count=9`, lane-separated source-only/read-only-runtime/future-authorization evidence, and probe/order/promotion/proof false.
- PM read: operator requested pause after this round. On resume, use real P0 auth delta if it exists; otherwise next useful source-only work is `P1-AGGRESSIVE-ALPHA-SOURCE-ONLY-CONTROL-IDENTITY-CONTRACT-NO-ORDER`, not another ranking/gap audit.

## 2026-06-26 Low-Price False-Negative Evidence-Floor Ranking

- PM closed `P1-AGGRESSIVE-ALPHA-LOW-PRICE-FALSE-NEGATIVE-EVIDENCE-FLOOR-RANKING-NO-ORDER` as source/test/docs `DONE_WITH_CONCERNS`.
- Added no-authority helper `false_negative_evidence_floor_ranking.py`; smoke on latest runtime artifacts ranks AVAX Sell first as `REVIEW_ONLY_LEADER_NOT_PROOF`, with `floor_satisfied_count=0` and probe/order authority false.
- PM read: do not rerun ranking on the same artifacts. If no real P0 auth delta appears, next source-only work is evidence-floor gap-closure design.

## 2026-06-26 TODO Maintenance Compliance Compaction

- PM closed operator-requested `P1-TODO-MAINTENANCE-COMPLIANCE-COMPACTION` as source/doc-only `DONE_WITH_CONCERNS`; `TODO.md` v561 is back to compact active-queue shape.
- Fresh natural artifacts show autonomous proposal has `cost_gate_cap_envelope_evidence_floor_v1`, but bounded auth is still AVAX-scoped defer/no authority.
- PM read: pause now per operator. On resume, do source-only low-price false-negative evidence-floor ranking unless a real P0 auth delta appears first.

## 2026-06-26 Cap Envelope Proposal Runtime Sync

- PM/E3 closed `P1-RUNTIME-HEALTH-HYGIENE-CAP-ENVELOPE-PROPOSAL-SYNC-REVIEW` as `DONE_WITH_CONCERNS`.
- Linux runtime source fast-forwarded `99d3b8f7 -> dd22810e`; crontab expected-head old/new changed `11/0 -> 0/11`; line count stayed `70`; API MainPID stayed `2218842`; runtime focused tests passed `10`.
- PM read: this did not run cron or overwrite `_latest`. Natural auth latest is still defer/no typed-confirm/no authority, so P0 authorization remains no-repeat blocked.

## 2026-06-26 Cap Envelope Evidence Floor Source Patch

- PM closed `P1-AGGRESSIVE-ALPHA-CAP-ENVELOPE-EVIDENCE-FLOOR-SOURCE-ONLY` as source/test/docs `DONE_WITH_CONCERNS`.
- `autonomous_parameter_proposal.py` now emits `cost_gate_cap_envelope_evidence_floor_v1`, inactive cap-envelope proposal row, and `cap_envelope_mutation_allowed=false`; tests passed `10`.
- PM read: P0 auth still has no delta. Next useful blocker is a separate runtime sync review if scheduled artifacts should emit the new floor; otherwise stop at P0 auth until real candidate-scoped authorization appears.

## 2026-06-26 ETH Cap Envelope Sensitivity No-Order

- PM closed `P1-AGGRESSIVE-ALPHA-ETH-CAP-ENVELOPE-SENSITIVITY-NO-ORDER` as source-only `DONE_WITH_CONCERNS` and normalized TODO v558 to active-queue shape with an explicit operator-requested pause.
- Fresh read-only runtime artifact check corrected the active cost-gate artifact path to `/tmp/openclaw/cost_gate_learning_lane/`; latest bounded auth artifact now reports `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED` for AVAX but remains defer/no typed confirm/no authority.
- ETH Buy remains research-only: current `10 USDT` cap cannot construct it; executable tiers are `15.7105`, `31.4210`, `47.1315 USDT` for `0.01`, `0.02`, `0.03 ETH`. Do not raise cap or open ETH order/probe path without separate operator/QC/E3/BB review.

## 2026-06-26 Authorization Gate Status Clarity Runtime Sync

- PM/E3 closed `P1-RUNTIME-HEALTH-HYGIENE-AUTH-STATUS-CLARITY-SYNC-REVIEW` as `DONE_WITH_CONCERNS`.
- Linux runtime source fast-forwarded `785a4346 -> 99d3b8f7`; crontab expected-head literals changed old/new `11/0 -> 0/11`; line count stayed `70`; API MainPID stayed `2218842`; runtime focused tests passed `19+18+6`.
- PM read: this did not run cron or refresh `_latest` artifacts. Next blocker is still `P0-BOUNDED-PROBE-AUTHORIZATION`, but do not rerun read-only auth audit without a real candidate-scoped auth delta.

## 2026-06-26 Authorization Gate Status Clarity Source Fix

- PM closed `P1-AUTHORIZATION-GATE-STATUS-CLARITY-SOURCE-FIX` as source-only `DONE_WITH_CONCERNS`.
- False-negative bounded preflight blockers now emit `false_negative_preflight_ready` and `FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED` / `FALSE_NEGATIVE_PREFLIGHT_NOT_READY` instead of misleading sealed-horizon wording; scorecard/discovery classify the new statuses without granting authority.
- PM read: v556 is not runtime-synced. After the operator-requested pause, resume at `P1-RUNTIME-HEALTH-HYGIENE-AUTH-STATUS-CLARITY-SYNC-REVIEW`, not another P0 authorization audit.

## 2026-06-26 Post-Guard AVAX Latest-Chain Review No Authority

- PM closed `P0-BOUNDED-PROBE-AUTHORIZATION-AVAX-LATEST-CHAIN-REFRESH-REVIEW` as `DONE_WITH_CONCERNS`.
- Runtime guard worked: the fresh latest chain is AVAX-scoped, but false-negative operator review is `defer`, bounded preflight is `OPERATOR_REVIEW_REQUIRED`, and bounded auth is `SEALED_HORIZON_PREFLIGHT_NOT_READY`.
- Actual bounded authorization remains blocked by candidate-scoped typed-confirm/standing-auth gates. Do not rerun read-only P0 audit without new authorization evidence.

## 2026-06-26 Alpha Bounded-Chain Guard Runtime Sync

- PM/E3 closed `P1-RUNTIME-HEALTH-HYGIENE-ALPHA-BOUNDED-CHAIN-STALENESS-GUARD-SYNC-REVIEW` as `DONE_WITH_CONCERNS`.
- Linux runtime source fast-forwarded `b9836224 -> 785a4346`; crontab expected-head pins replaced exactly `11` times; API MainPID stayed `2218842`; runtime cron tests passed `24`.
- No manual cron or artifact refresh was run. Next useful checkpoint is fresh post-guard AVAX latest-chain review after the scheduled cron window.

## 2026-06-26 Alpha Bounded-Chain Stale Side-Cell Guard Source Fix

- PM closed `P1-RUNTIME-HEALTH-HYGIENE-ALPHA-BOUNDED-CHAIN-STALENESS-GUARD-SOURCE-FIX` as `DONE_WITH_CONCERNS`.
- Runtime read-only evidence showed `08:00:05 CEST` alpha bounded auth latest still ETH-scoped while the only cap-feasible selection is AVAX Sell.
- Source fix: alpha cron now fails closed on selected-side-cell mismatch, skipping bounded review chain refresh and bounded scorecard inputs. Next checkpoint is runtime sync review; do not rerun P0 authorization until fresh AVAX-scoped artifacts exist.

## 2026-06-26 Cap-Feasible Selector Runtime Sync

- PM/E3 closed `P1-RUNTIME-HEALTH-HYGIENE-CAP-FEASIBLE-SELECTOR-SYNC-REVIEW` as `DONE_WITH_CONCERNS`.
- Linux runtime source fast-forwarded cleanly `0246b263 -> b9836224`; crontab expected-head literals replaced exactly `5` times; API MainPID stayed `2218842`.
- No manual cron/artifact refresh was run. Latest auth artifact still predates sync and remains ETH Buy defer/no-authority, so next review needs a post-sync artifact delta.

## 2026-06-26 Candidate Selection Delta Cap-Feasible Selector Source Fix

- PM closed `P0-PROFIT-CANDIDATE-SELECTION-DELTA-REFRESH-NO-ORDER` as `DONE_WITH_CONCERNS`.
- Runtime read-only delta: latest scorecard/auth chain again targeted `grid_trading|ETHUSDT|Buy`, but ETH remains infeasible under current `10 USDT` cap; AVAX remains the top current-cap-feasible candidate.
- Source fix: cron false-negative operator review now prefers explicit/cap-feasible selected side-cell before falling back to top ranked false-negative. This is source/test/docs only; runtime sync remains a separate E3-reviewed blocker.

## 2026-06-26 AVAX/SUI/FIL Matched-Control Design No-Order

- PM closed `P1-AGGRESSIVE-ALPHA-AVAX-SUI-FIL-MATCHED-CONTROL-DESIGN-NO-ORDER` as `DONE_WITH_CONCERNS`.
- Design decision: future AVAX proof must use candidate-matched AVAX outcomes plus same-side-cell blocked controls and proof-exclusion/result-review/execution-realism contracts. SUI/FIL are research-only cross-symbol controls, not AVAX proof/promotion/Cost Gate evidence.
- TODO maintenance: v549 separates operational queue `Status` (`DONE/BLOCKED/WAITING/DEFERRED`) from loop/state-machine outcomes in `Loop decision`.
- PM read: all currently selected source-only aggressive blockers are closed. Next queue entry is `P0-BOUNDED-PROBE-AUTHORIZATION`, still `BLOCKED_BY_RUNTIME_AUTHORIZATION` until valid AVAX-scoped auth or exact typed confirm plus E3/BB review.

## 2026-06-26 Cap-Feasible Low-Price Filter No-Order

- PM closed `P1-AGGRESSIVE-ALPHA-CAP-FEASIBLE-LOW-PRICE-REGIME-FILTER-NO-ORDER` as `DONE_WITH_CONCERNS` with a source-only filter proposal.
- Clean-BBO/high-cushion/current-cap filter keeps `grid_trading|AVAXUSDT|Sell` as champion/current P0 candidate; SUI/FIL are source-only controls only. ETC/APT fail incomplete BBO; UNI/XRP/OP fail thin cushion/hit-rate/sample/spread.
- PM read: current artifacts do not contain regime labels or markout buckets, so do not claim regime proof. Next source-only blocker is `P1-AGGRESSIVE-ALPHA-AVAX-SUI-FIL-MATCHED-CONTROL-DESIGN-NO-ORDER`.

## 2026-06-26 ETH Buy Cap Feasibility No-Order

- PM/QC/MIT closed `P1-AGGRESSIVE-ALPHA-ETH-BUY-CAP-FEASIBILITY-PROPOSAL-NO-ORDER` as `DONE_WITH_CONCERNS`.
- Decision: do not raise cap or open ETH order/probe path now. ETH Buy remains research-only because current `10 USDT` cap cannot construct it (`15.7105 USDT` min executable notional, rounded qty `0`), evidence is only `7` modeled outcomes, and candidate-matched fills/fees/slippage/controls are absent.
- PM read: AVAX Sell remains the only current-cap-feasible bounded Demo candidate, still blocked by valid scoped authorization. After operator-requested pause, resume at source-only `P1-AGGRESSIVE-ALPHA-CAP-FEASIBLE-LOW-PRICE-REGIME-FILTER-NO-ORDER`; do not rerun ETH cap feasibility without fresh scorecard/cap/construction or cap-envelope evidence.

## 2026-06-26 False-Negative Subset Mining ETH Cap-Bound

- PM closed `P1-AGGRESSIVE-ALPHA-FALSE-NEGATIVE-SUBSET-MINING-NO-ORDER` as `DONE_WITH_CONCERNS` with a source-only review packet.
- Latest scorecard ranks `grid_trading|ETHUSDT|Buy` highest (`258.3905bps`, 7/7 positive, friction rank 1), but current 10 USDT cap makes it non-constructible because min executable notional is about `15.7318 USDT`.
- PM read: AVAX Sell remains the current cap-feasible bounded Demo candidate. Next source-only blocker is ETH Buy cap/risk feasibility; no cap mutation, order/probe authority, or Cost Gate change.

## 2026-06-26 Bounded Probe Authorization Anti-Repeat TODO Hygiene

- PM closed the current `P0-BOUNDED-PROBE-AUTHORIZATION` round as `BLOCKED_BY_RUNTIME_AUTHORIZATION`; repeated no-authority audit is `NO-OP_NO_EVIDENCE_DELTA`.
- Runtime latest authorization artifact remains defer-only and candidate-mismatched (`grid_trading|ETHUSDT|Buy`), with no standing auth, emitted object, runtime probe/order authority, or Cost Gate change for selected `grid_trading|AVAXUSDT|Sell`.
- PM read: do not rerun this authorization blocker without a valid AVAX-scoped auth delta. After operator-requested pause, resume at source-only `P1-AGGRESSIVE-ALPHA-FALSE-NEGATIVE-SUBSET-MINING-NO-ORDER`; no orders/authority.

## 2026-06-26 Runtime Hygiene Post-Alignment Snapshot

- PM/E3 closed `P1-RUNTIME-HEALTH-HYGIENE-CRON-POST-ALIGNMENT-HYGIENE-SNAPSHOT` as `DONE_WITH_CONCERNS`.
- Hygiene packet `/tmp/openclaw/runtime_health_hygiene_post_alignment_20260626T042802Z/runtime_health_hygiene_post_alignment.json` is `RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY`: source/crontab/API/artifact compatibility clean, no authority/mutation/proof signals.
- PM read: target runtime head is `0246b263`, not docs head `65fe28ef`. Natural MM current-fee artifact now says `NO_CURRENT_FEE_POSITIVE_MM_CELL`; false-negative AVAX path remains the main review-only candidate. Next blocker is still machine-checkable bounded Demo authorization.

## 2026-06-26 Cron Expected-Head Drift Alignment

- PM/E3 closed `P1-RUNTIME-HEALTH-HYGIENE-CRON-EXPECTED-HEAD-DRIFT-REVIEW` as `DONE_WITH_CONCERNS`.
- Runtime crontab expected-head pins now align to `0246b263`: old `d2cd70d0` count `0`, new count `11`, lines `57,67,68,69,70`, line count `70`.
- PM read: use `systemctl --user` for canonical API/watchdog checks. `openclaw-trading-api.service` is active/enabled with MainPID `2218842`, and `openclaw-watchdog.service` is active/running/enabled; system-level `openclaw-api`/`openclaw-watchdog` inactive is wrong-scope evidence.
- TODO v543 is normalized to active queue only. Next blocker is `P1-RUNTIME-HEALTH-HYGIENE-CRON-POST-ALIGNMENT-HYGIENE-SNAPSHOT`, but the operator requested pause after this round.

## 2026-06-26 Health [68] Runtime Source Sync Review

- PM/E3 closed `P1-RUNTIME-HEALTH-HYGIENE-68-RUNTIME-SYNC-REVIEW` as `DONE_WITH_CONCERNS`; Linux `trade-core` source-only fast-forwarded clean to `0246b263`.
- Direct [68] read-only PG verification now returns `PASS` with demo `resting=0`, `working_n=0`, while preserving visible `local_lineage_residual_n=2/notional=398`.
- PM read: do not rerun [68] source sync. Remaining runtime hygiene is crontab expected-head drift: 5 pins still point to `d2cd70d0`, requiring separate E3 review before any crontab edit.

## 2026-06-26 Health [68] Local Lineage Residual Source Patch

- PM/E2/E4 closed `P1-RUNTIME-HEALTH-HYGIENE-LOCAL-LINEAGE-68-STALE-WORKING` as source-only `DONE_WITH_CONCERNS`.
- Anti-repeat: `P1-LEARNING-LOOP-CLOSURE` and `P1-AUTONOMOUS-PARAMETER-PROPOSAL` are already done via 2026-06-24 reports; do not rerun them without new source/runtime/PG/artifact evidence.
- PM read: [68] now distinguishes exchange-clean local close/risk stale `Working` lineage residuals from real entry resting exposure. This reduces a false blocker but is not synced to Linux runtime and is not profit proof.

## 2026-06-26 AVAX Authorization Review Ready No-Authority

- PM/E3/BB advanced `P0-BOUNDED-PROBE-AUTHORIZATION` only to a no-authority review checkpoint for `grid_trading|AVAXUSDT|Sell`.
- Anti-repeat: do not redo `P0-BOUNDED-PROBE-FIRST-ATTEMPT-TOUCHABILITY-BOOTSTRAP-SOURCE-ONLY`; prior source patch/report already covers the bootstrap and placement plan is review-ready.
- Fresh packet is defer-only: `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, no auth object, no active runtime probe/order authority, no Cost Gate change. Actual grant still requires valid structured standing Demo authorization or exact typed confirm, then fresh E3/BB order-envelope/runtime/reconciliation review.

## 2026-06-26 Profit Candidate Selection AVAX Review Packet

- PM/QC/MIT/BB closed `P0-PROFIT-CANDIDATE-SELECTION` as `DONE_WITH_CONCERNS` and selected exactly one review-only candidate: `grid_trading|AVAXUSDT|Sell`, 60m, false-negative after current cost.
- Evidence is strong enough for review-only selection: avg net `73.5511bps`, `48/48` net-positive, cap `10 USDT`, min notional `5 USDT`, Cost Gate lowering false, probe/order authority false.
- PM read: do not overclaim. Candidate-matched touchability is still missing (`candidate_reviewed_orders=0`, `candidate_fill_rows=0`), so the next safe action is source/read-only first-attempt touchability bootstrap, not order/probe authority.

## 2026-06-26 Demo Residual Cleanup Auth Block

- CSRF-safe helper worked through gating, but the one reviewed `/api/v1/strategy/demo/session/stop` POST failed before route execution with HTTP 401 `unauthenticated`; no exchange mutation occurred and no retry was allowed.
- Fresh pre-inventory immediately before action showed demo exposure still drifting (`6` open orders, `5` positions), so candidate selection remains blocked.
- PM read: next useful checkpoint is runtime-local/authenticated control API token-source path review; do not repeat cleanup POST until new E3/BB envelope and fresh inventory exist.

## 2026-06-26 Demo Residual Cleanup Refresh Clean Exchange

- E3/BB approved a one-time inline runtime-local GET-only full-scan inventory because runtime lacked the repo helper; pre-inventory found 5 reduce-only conditionals and 5 positions inside caps.
- PM executed exactly one runtime-local CSRF/Bearer `/api/v1/strategy/demo/session/stop`; response was HTTP 200, `closed_all=true`, `partial_failure=false`, and post-action full-scan inventory is exchange-clean.
- PM read: next is candidate selection, but cleanup/risk-close/unattributed/local-stale [68] rows are proof-excluded; [68] remains a local lineage hygiene residual, not exchange exposure.

## 2026-06-25 AVAX Candidate-Scoped Chain Smoke

- Local timestamped smoke `/tmp/openclaw/local_chain_smoke_20260625T232303Z` proved AVAX can reach reviewable proposal and bounded preflight READY via explicit `grid_trading|AVAXUSDT|Sell`.
- The first hard blocker is now exact: touchability/placement returned `CANDIDATE_TOUCHABILITY_DATA_REQUIRED` because fill flow exists only for non-candidate AVAX rows; authorization/readiness/reroute remained fail-closed with no authority object.
- PM read: next safe work is source-only zero-candidate touchability bootstrap design, or stop before any runtime/order/probe authority.

## 2026-06-25 AVAX Candidate-Scoped Reroute Source Patch

- `bounded_probe_lower_price_reroute_review.py` now accepts fresh cap-feasible selection wrappers as an alternate candidate source, so AVAX is not forced through a stale order-construction repair packet.
- E2 found and E1 fixed a stale-selection freshness bug; PA-requested PG evidence scoping was tightened to `cap_feasible_selection.answers.pg_query_performed` only. Verification: focused `18 passed`, adjacent `179 passed`, py_compile/diff-check PASS.
- PM read: this is source readiness only. Next proof is timestamped no-authority candidate-scoped chain smoke; no quote, runtime write, or authority follows from this patch.

## 2026-06-25 Bounded Probe Cron Expected-Head Sync

- E3 selected option A: align Linux checkout and crontab expected-head pins to the same source head. PM fast-forwarded `/home/ncyu/BybitOpenClaw/srv` from `b180546c` to docs head `d2971aa5`, then replaced exactly 11 crontab expected-head occurrences `bdc1e156 -> d2971aa5`.
- Post-check: Linux `HEAD=origin/main=d2971aa5`, clean worktree, crontab still 70 lines, `RECORD_PROBE_OUTCOMES=0` count 1, `=1` count 0, no `OPENCLAW_ALLOW_MAINNET=1`, no `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED`; running engine env remains `OPENCLAW_ALLOW_MAINNET=0`.
- Boundary remains no-order/no-authority: no rebuild/restart, no PG write, no Bybit/API/order/cancel/modify, no adapter/writer enablement, no Cost Gate change, no probe/order/live authority, no promotion proof. Latest authority artifact still needs a separate no-order refresh/review.

## 2026-06-25 Bounded Probe Runtime Source Sync Reconciliation E3 Review

- E3 approved only a no-order Linux source checkout sync. PM fast-forwarded `/home/ncyu/BybitOpenClaw/srv` from `f9e4456c` to `b180546c`; post-check showed `HEAD=origin/main=b180546c`, clean worktree, and v513 gate source present.
- Running engine was not rebuilt/restarted; env still has `OPENCLAW_ALLOW_MAINNET=0` and no `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED`. Crontab expected-head pins still point to `bdc1e156`, and latest natural authority artifact remains `PLACEMENT_REPAIR_PLAN_NOT_READY`.
- Read-only PG found no 7d active bounded-probe rows, but broad 2d demo `Working` orders remain `117`; post-restart active bounded-probe reconciliation remains unproven. Boundary: no crontab/env/service mutation, no PG write, no Bybit/order/cancel/modify, no adapter/writer enablement, no Cost Gate change, no probe/order/live authority, no promotion proof.

## 2026-06-25 Bounded Probe Production Active Caller Runtime Adapter Gate

- `demo_learning_lane_writer.rs` now has source-ready optional active bounded-probe request admission plumbing and a strict `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED` gate, but the real writer loop still passes `None`; no order sender is reached.
- Readiness scanning now requires explicit `1`/`true` parsing plus `active_order_request.is_some()` and rejects env-presence or missing-guard shapes. Current repo can become E3/BB-review-ready while actual runtime/order authority remains false.
- Verification passed focused readiness `35`, adjacent active/proof/result/execution `35`, Rust writer `10`, Rust active-order `13`, rustfmt check, py_compile, and diff-check. Boundary remains source/test/docs only; no runtime sync, PG/Bybit/order/cancel/modify, Cost Gate lowering, active probe/order/live authority, Rust writer enablement, or promotion proof.

## 2026-06-25 Bounded Probe Runtime/Admission Propagation Review

- `bounded_probe_authority_patch_readiness.py` now exposes `runtime_admission_propagation_review` plus top-level no-authority answers, including `actual_runtime_admission_enablement_ready=false`, `allowed_to_submit_order=false`, `adapter_enabled_by_this_packet=false`, and Bybit/order/PG/runtime/writer/live/probe authority false.
- Current repo remains source-blocked for active runtime enablement: production active caller, reviewed runtime adapter gate, runtime source sync, adapter enablement, and post-restart reconciliation are not proven.
- Verification passed focused readiness `33`, adjacent active/proof/result/execution `35`, py_compile, and diff-check. Boundary remains source/test/docs only; no runtime sync, PG/Bybit/order/cancel/modify, Cost Gate lowering, active probe/order/live authority, Rust writer enablement, or promotion proof.

## 2026-06-25 Bounded Probe Active Effective Cap Guard

- Active bounded Demo drafts now share a fail-closed effective-notional cap helper, and the dormant active dispatch seam rechecks cap immediately before `OrderDispatchRequest` send.
- PA/E2/E4 passed; focused verification was Rust active-order 12, active submission 2, no-send cap dispatch 1, writer helper 1, Python scanner suite 40, and diff-check.
- Boundary remains source/test/docs only: no runtime sync, no PG/Bybit/order/cancel/modify, no Cost Gate lowering, no active probe/order/live authority, and no promotion proof.

## 2026-06-25 Bounded Probe Active Candidate-Bound OrderLinkId

- Active bounded Demo draft validation now requires candidate-bound deterministic `orderLinkId` over engine mode, event ts, canonical base36 seq, side-cell, context id, and signal id; generic orderLinkId helper remains unchanged.
- PA/E2 concerns were fixed: side-cell is included in the lineage hash, non-canonical leading-zero seq is rejected, and dormant writer helper fixtures use the new helper.
- Boundary remains source/test/docs only: no runtime sync, no PG/Bybit/order/cancel/modify, no Cost Gate lowering, no active probe/order/live authority, and no promotion proof.

## 2026-06-24 Bounded Probe Authorization Candidate-Scoped Refresh

- E3 approved timestamped-only artifact generation for `grid_trading|AVAXUSDT|Sell`; PM generated standing auth sha `a303f80e` and bounded authorization packet sha `391dbca5`.
- Packet status is `BOUNDED_DEMO_PROBE_AUTHORIZED`, max orders `1`, expires `2026-06-25T00:04:43Z`, but packet answers keep active runtime probe/order authority false.
- PM read: this is plan/admission review input only. `bounded_probe_operator_authorization_latest.json` was not overwritten and currently points to non-ready ETHUSDT Buy, so AVAX admission must use a separate reviewed propagation path.

## 2026-06-24 Public Quote Adapter Runtime Ready Preview

- E3/BB approved a bounded runtime route; trade-core fast-forwarded cleanly to `22f5915b`, focused public quote/adapter/construction tests passed `39`, and PM consumed exactly one public quote helper invocation.
- Runtime artifacts at `2026-06-24T20:50:15Z` reached `PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER` and `CANDIDATE_CONSTRUCTION_PREVIEW_READY_NO_ORDER` for `grid_trading|AVAXUSDT|Sell`: limit `6.359`, qty `1.5`, notional `9.5385 USDT`, effective BBO age `356.104ms`, all authority/proof flags false.
- PM read: this is the first fresh no-order construction-ready AVAX checkpoint, not order authority. Bounded authorization latest remains `defer`, and the old standing demo authorization expired at `2026-06-24T20:09:30Z`.

## 2026-06-24 BBO Freshness Runtime Co-Located Runner Review

- E3 approved a bounded PM-only runtime path; trade-core fast-forwarded cleanly `bdc1e156 -> 8e7bc890`, focused runner+preview tests passed, and `bbo_freshness_colocated_runner.py` ran in explicit `--pg-readonly` mode.
- Runtime artifact `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_colocated_runner_avax_sell_pg_readonly_20260624T185436Z.json` is `COLOCATED_RUNNER_BBO_STALE_NO_ORDER`: effective BBO age `2476.128ms` still exceeds the 1000ms gate, so no order admission follows.
- PM read: next useful blocker is public-quote capture E3/BB review; do not rerun PG co-located runner as proof without a new market-data freshness delta, and do not treat READY as order authority even if future quote freshness passes.

## 2026-06-24 Candidate-Scoped Standing Demo Authorization Artifact

- Runtime timestamped artifact `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_standing_demo_20260624T160930Z.json` authorizes exactly `grid_trading|AVAXUSDT|Sell` 60m with cap 1 and 4h TTL via `standing_demo_authorization`.
- E3 approved only timestamped artifact generation; PM did not overwrite `bounded_probe_operator_authorization_latest.json`, did not refresh alpha, did not run runtime_adapter, and did not include the object in a plan.
- PM read: next blocker is propagation/admission review. The generated object is useful proof-chain input, but it is not active runtime order/probe authority, not Cost Gate lowering, not live permission, and not promotion proof.

## 2026-06-24 Standing Demo Authorization Contract

- Source/runtime commit `bdc1e156` lets bounded Demo operator authorization consume a structured `standing_demo_operator_authorization_v1` as an alternative confirmation source, but only to emit a fresh candidate-scoped authorization object.
- Standing auth must be top-level explicit demo/live_demo, bounded-probe scoped, candidate-scoped, capped, short-TTL, operator-aligned, and recursively free of live/runtime/order/probe/PG/Bybit/service/writer/Cost Gate/promotion contamination; truthy strings and `answers` overrides fail closed.
- PM read: the operator's standing Demo permission no longer needs repeated broad authorization questions, but it still does not grant live/mainnet, active runtime authority, order submission, Cost Gate change, or promotion proof. Demo experience remains live-applicable only through candidate-matched, fee/slippage/lineage-auditable evidence.

## 2026-06-24 MM Motif Distinct-Date Worklist Surface

- Source commit `52b572ed` makes the learning worklist emit a separate no-authority `mm_motif_distinct_date_accumulation` task for the low-friction MM motif when motif amplification still needs distinct-date history.
- Runtime is clean at `52b572ed`; crontab expected-head pins are synced; alpha refresh at `2026-06-24T15:12:51Z` reports both `mm_current_fee_confirmation=1` and `mm_motif_distinct_date_accumulation=1`, with both tasks operator/runtime false.
- PM read: this closes a source-only autonomy visibility gap, not an edge proof. The MM path still needs independent distinct dates, repeat windows, OOS/walk-forward evidence, and maker-realism before any bounded Demo review; no probe/order/live authority or promotion proof exists.

## 2026-06-24 Killboard Probe Authority Semantics Runtime Sync

- Source commit `7d118e81` makes alpha killboard/history separate operator probe-review readiness from actual runtime probe/order authority; legacy `ready_for_probe/actionable_probe_found` remains compatibility-only.
- Runtime is clean at `7d118e81`; crontab expected-head pins are synced to that head; direct `runtime_runner` refresh reports `actionable_probe_semantics=OPERATOR_REVIEW_READY_NO_RUNTIME_AUTHORITY`, `runtime_probe_authority_found=false`, `runtime_order_authority_found=false`, promotion/Cost Gate mutation false.
- PM read: future autonomous consumers must use the `runtime_*_authority_found` and `actionable_probe_semantics` fields for authority decisions; `ready_for_probe=1` means operator review readiness only unless runtime authority fields prove otherwise.

## 2026-06-24 Bounded Probe Authorization Broad Demo Fail-Closed

- Fresh runtime artifacts are aligned and ready for `grid_trading|AVAXUSDT|Sell`, but the broad Demo/API authorization was not converted into bounded probe/order authority.
- Structured attempt `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_operator_authorization_structured_attempt_broad_demo_session_20260624T1145Z.json` returned `TYPED_CONFIRM_REQUIRED`, only blocker `typed_confirm_matches`, and no emitted authorization object.
- PM read: do not repeat this P0 authorization audit unless exact typed-confirm is new evidence; continue with source-only/runtime-hygiene blockers meanwhile.

## 2026-06-24 API Service Runtime Cutover PM Apply

- E3 approved and PM executed a guarded Demo/API service ownership handoff from manual uvicorn PID `1859622` to `openclaw-trading-api.service`; post-cutover service is active/running with MainPID `2218842`, bound only to `100.91.109.86:8000`.
- Post-cutover parity packet `/tmp/api_service_env_parity_packet_post_cutover.json` is `API_SERVICE_ENV_PARITY_CLEAN_SOURCE_ONLY` with no findings, evidence gaps, or plan blockers; demo engine remains alive and runtime source remains clean at `dc1416e5`.
- `systemctl --user enable` was not run; unit remains disabled and boot-autostart enablement is a separate PM/E3 checkpoint. No Bybit/PG/Cost Gate/probe/order/live/Rust-writer authority changed.

## 2026-06-24 API Service Exact Unit Diff Packet

- Source-only `api_service_env_parity.py` now emits exact redacted current/proposed systemd unit content, unified diff, current/proposed SHA256, source fragment inventory, drop-in detection, and `pre_apply_revalidation_contract.contract_sha256`.
- Fresh packet `/tmp/api_service_env_parity_exact_unit_diff_20260624T1148Z.json` is `API_SERVICE_ENV_PARITY_DRIFT` with `plan_blockers=[]`, single base fragment, no drop-ins/redactions, and `apply/restart/enable=false`.
- Do not treat this as runtime apply authority. Before any future systemd write/restart, take a fresh snapshot and require the manual pid/cmdline/cwd/env/listener plus current unit SHA/source-fragment fields to match the reviewed contract.

## 2026-06-24 Runtime Cron Expected-Head Patch

- Runtime `trade-core` remains clean at operational source head `dc1416e5`; four demo-learning cron entries now pin that head, with schedules/wrappers/log paths and Cost Gate flags preserved.
- Post-check hygiene cleared cron/source/artifact drift and kept all authority/proof flags false; remaining runtime hygiene drift is API process/service ownership only.
- Do not restart or enable `openclaw-trading-api.service` without an env-parity/runbook blocker: current manual uvicorn has workers/runtime env that the inactive unit does not reproduce.

## 2026-06-24 False-Negative Runtime Preflight Approval

- Runtime `trade-core` is now synced clean to `6702ac0a`; the selected false-negative candidate `grid_trading|AVAXUSDT|Sell` has an approved no-authority false-negative review and a ready false-negative bounded preflight.
- Bounded operator authorization remains fail-closed at `PLACEMENT_REPAIR_PLAN_NOT_READY` with gates `placement_repair_plan_ready` and `authority_path_patch_readiness_ready`; no authorization object, active order/probe authority, Cost Gate lowering, Bybit call, or promotion proof was emitted.
- PM read: do not repeat the source-sync/preflight approval audit. Next useful work is source/runtime gate semantics around fill-flow touchability -> placement/readiness, or outcome review only after a real bounded authorization object and candidate-matched outcomes exist.

## 2026-06-24 Profit Evidence Quality Operator Checkpoint

- Read-only PM checkpoint found a stronger overhang delta than the prior audit: paged Bybit demo inventory has 35 exchange open orders, including 34 deep PostOnly buys totaling about 8.37k USDT notional and 9 stale >24h orders, plus one SOLUSDT open position while local demo_state is flat.
- SOL/ETH unattributed fills are OpenClaw-dispatched orders that failed clean fill matching; they are audit evidence only and must never count toward Cost Gate, bounded-probe, promotion, or risk-adjusted net PnL proof.
- `P0-PROFIT-EVIDENCE-QUALITY` is blocked by operator action: any cancel/modify/close, PG reconciliation/backfill, cron edit, service restart, or runtime mutation needs explicit authorization before candidate selection.

## 2026-06-23 Cost Gate False-Negative Candidate Packet

- `cost_gate_false_negative_candidate_packet_v1` now turns blocked-outcome diagnosis into a ranked Cost Gate escape packet: false-negative-after-cost candidates for operator review, edge-amplification-required rows for engineering search, sample accumulation, and keep-blocked rows.
- Linux artifact-only smoke at `2026-06-23T19:12:22Z` on source `b713c672` reports `COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW`, 16 ranked false-negative candidates, top `grid_trading|AVAXUSDT|Sell`, wrongful-block score `146.9126`, and net cost cushion `73.4563bps`.
- PM read: this is the right profit-learning path for the Cost Gate problem. Do not globally lower the gate; review ranked false negatives, require bounded demo-probe authority before any probe, and require candidate-matched touchability/fill/fee/slippage lineage before any Cost Gate change. No global Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof was granted.

## 2026-06-24 Demo-Learning Autonomy Audit

- Runtime is no longer demo-silent: `trade-core` is clean at `c88deea7`, demo engine is alive, and PG shows fresh `flash_dip_buy` demo intents/orders/fills.
- Current maturity is evidence-active and safety-gated, not autonomous-profit complete: Cost Gate learning artifacts and JSONL rows accumulate, but Rust hot-path writer/PG-backed decision impact, bounded probe outcomes, promotion proof, and material AI/ML parameter evolution remain absent.
- Next PM posture: clear working-order overhang, fill lineage, and stale cron expected-head health drift before any exact bounded-probe operator review; no global Cost Gate lowering or promotion.

## 2026-06-23 Cost Gate Blocked-Outcome Diagnosis

- `cost_gate_demo_learning_lane_blocked_outcome_review_v2` now emits explicit `learning_diagnosis` and `cost_gate_escape_recommendation` fields for blocked-signal outcomes.
- Source checkpoint `51a1c4ad` routes gross-positive but after-cost-insufficient blocked outcomes to `cost_gate_blocked_signal_edge_amplification_required` / `amplify_edge_or_reduce_friction_for_same_side_cell` instead of `rejected_no_edge`.
- PM read: this is a learning-loop depth improvement, not authority. It grants no global Cost Gate lowering, no probe/order authority, no runtime mutation, and no promotion proof.

## 2026-06-23 MM Current-Fee Confirmation Packet

- `mm_current_fee_confirmation_packet_v1` now turns the SOXLUSDT current-fee-positive MM cell into a standalone repeat/OOS/maker-realism confirmation artifact.
- Linux canonical refresh at `2026-06-23T18:30:31Z` on source `SYNCED_CLEAN 6221b8f9` reports `MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW`, candidate `edge_scorecard|per_symbol_primary_queue|SOXLUSDT|back|informed_skip|fill_only`, net `0.715bps`, current-fee candidate count `2`, history positive windows `1`, repeated keys `0`, repeated windows `0`, repeat/OOS false, maker status `NOT_REACHED_REPEAT_WINDOW_REQUIRED`.
- PM read: this is a Cost Gate crossing lead, not profit proof. The next autonomous MM task is independent-window accumulation/replay for the same cell, then OOS/walk-forward, then maker execution realism; no global Cost Gate lowering, order/probe authority, runtime mutation, or promotion proof was granted.

## 2026-06-23 MM Current-Fee Confirmation Worklist Task

- `alpha_learning_worklist_v6` now emits `mm_current_fee_confirmation` for sample-gated MM cells that already clear current fees, instead of burying them under generic `mm_signal_search`.
- Linux artifact refresh at `2026-06-23T18:11:28Z` on runtime source `SYNCED_CLEAN 54183830` reports top engineering task `mm_current_fee_confirmation` for SOXLUSDT: gross `4.715bps`, net `0.715bps`, current-fee-positive count `2`, break-even maker fee `2.3575bp/side`, rank `3`.
- PM read: this is the right autonomous-learning next task for the MM path: independent-window repeat + OOS/walk-forward + maker execution realism. It still grants no Cost Gate lowering, no probe/order authority, no runtime mutation, and no promotion proof.

## 2026-06-23 MM Current-Fee Confirmation Path

- `alpha_profitability_path_scorecard_v1` now surfaces sample-gated current-fee-positive MM cells as `mm_current_fee_cell_confirmation` instead of hiding them under fee/scale or low-friction below-fee search.
- Linux artifact refresh at `2026-06-23T17:58:25Z` on runtime source `SYNCED_CLEAN b0b803ea` ranks the SOXLUSDT informed-skip maker cell #3: gross `4.715bps`, current fee `4.0bps`, net cushion `0.715bps`, sample `43`, break-even maker fee `2.357bp/side`.
- PM read: this is a concrete Cost Gate crossing lead, but only one current-fee-positive history window with 0 repeated positive keys. Next proof is independent-window repeat + OOS/walk-forward + inventory-risk + maker execution-realism, not Cost Gate lowering, probe/order authority, or promotion proof.

## 2026-06-23 MM 60s Low-Friction Lookback Search

- `fill_sim_low_friction_signal_scorecard()` now derives low-friction recent-flow/L1-churn features, combos, and interactions from `LOW_FRICTION_LOOKBACKS_S=(10,30,60)`, adding 60s PIT context without changing Cost Gate, sample gates, or authority.
- Linux artifact refresh at `2026-06-23T17:39:03Z` reports runtime source `SYNCED_CLEAN d4306ea1`; forced fill_sim processed `1,546,849` post-filter L1 rows / `36` symbols and evaluated `1,114` low-friction candidates.
- PM read: the best latest train-confirmed 60s interaction has train gross `0.778bps`, holdout gross `0.556bps`, min gross `0.556bps`, and still sits `3.444bps` below the current 4bp round-trip fee. This is useful search coverage / negative evidence, not Cost Gate lowering, probe/order authority, or promotion proof.

## 2026-06-23 MM Motif Frontier Amplification

- `fill_sim_history.py` now emits same-motif low-friction candidate frontiers; `mm_motif_amplification_packet_v1` uses frontier-best min train/holdout gross as the primary uplift baseline while preserving the old best-cell value for provenance.
- Linux artifact-only refresh at `2026-06-23T17:21:19Z` reports top motif `low_friction_motif|spread_combo|recent_trade_imbalance`, best-cell min gross `1.032bps`, frontier-best min gross `1.392bps`, remaining gap `2.608bps`, required uplift `2.8736x`, and frontier focus `lift_train_gross_edge_without_destroying_holdout_sample_gate`.
- PM read: this turns the MM path into a concrete same-motif train-leg amplification task, but still grants no Cost Gate lowering, no probe/order authority, no runtime mutation, and no promotion proof.

## 2026-06-23 Profitability Scorecard Operator-Authorization Gate

- `alpha_profitability_path_scorecard_v1` now consumes `bounded_probe_operator_authorization_latest.json`, so the main profitability closure names the concrete Cost Gate escape authority gates instead of stopping at a generic sealed-preflight blocker.
- Canonical Linux alpha smoke reports closure `BOUNDED_DEMO_PROBE_OPERATOR_AUTHORIZATION_GATES_NOT_READY` for `ma_crossover|BTCUSDT|Sell`, with gates `sealed_horizon_preflight_ready`, `placement_repair_plan_ready`, and `authority_path_patch_readiness_ready`.
- PM read: the profit path is side-cell/horizon edge amplification plus bounded Demo authorization and execution-realism proof, not global Cost Gate lowering; no authorization object, active order/probe authority, or promotion proof was granted.

## 2026-06-22 Bounded Probe Authority Patch Readiness

- `bounded_demo_probe_authority_patch_readiness_v1` now consumes the placement repair plan and scans Rust authority-path source for the exact near-touch bounded Demo Implementation seams.
- Linux canonical smoke reports `RUST_PATCH_REQUIRED_NEAR_TOUCH_PLACEMENT_ADAPTER_MISSING`: existing Cost Gate learning seams are present, but the deeper Adapter for `post_only_near_touch_or_skip`, fresh-BBO guard, initial-gap guard, skip record, and candidate-matched attempt lineage is still missing.
- PM read: the profit path is to increase Depth at the Rust authority path so selected blocked side-cell/horizon alpha becomes touchable, maker, candidate-matched Demo learning evidence; no global Cost Gate lowering, probe/order authority, or promotion proof was granted.

## 2026-06-22 Bounded Probe Shadow Placement Impact

- `bounded_demo_probe_shadow_placement_impact_v1` now shadow-applies the no-authority near-touch repair plan to already-observed Demo order-touchability rows.
- Linux smoke reports `SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH`: current no-fill sample would become 6/6 shadow-submit with max initial touch gap `58.2092bp` versus original max `1530.6074bp`, but candidate-matched order count is 0.
- PM read: the near-touch repair is mechanically worthwhile, but not alpha proof; next step still needs operator-authorized Rust bounded Demo patch plus candidate-matched fill-backed evidence before any Cost Gate change.

## 2026-06-22 Bounded Probe Placement Repair Plan

- `bounded_demo_probe_placement_repair_plan_v1` now turns the touchability failure into a no-authority near-touch-or-skip plan before any bounded Demo probe result review.
- Linux smoke reports `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW` for `ma_crossover|BTCUSDT|Sell`: the baseline remains 6/6 deep passive no-touch, max best-touch gap `1530.6074bp`, required initial passive gap `75bp`, order mode `post_only_near_touch_or_skip`, active=false.
- PM read: the next profitability move is a bounded Demo-only existing Rust authority-path repair with fresh BBO, maker-side near-touch price, skip-and-record if too wide, and immediate order-to-fill/fill-fee-slippage lineage; no global Cost Gate lowering or probe/order authority was granted.

## 2026-06-22 Bounded Probe Touchability Preflight

- `bounded_demo_probe_touchability_preflight_v1` now gates bounded Demo probe design against the latest order-to-fill touchability audit before any probe review.
- Linux smoke reports `TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`: the sealed BTCUSDT Sell design is reviewable, but current Demo orders are 6/6 deep passive no-touch with max best-touch gap `1530.6074bp` versus a required initial passive gap of `75bp`.
- PM read: next profit work is near-touch-or-skip placement repair plus fill/fee/slippage lineage, not global Cost Gate lowering; missing order-touchability input fails closed as `ORDER_TOUCHABILITY_AUDIT_REQUIRED`, not silent loss.

## 2026-06-22 Demo Order-To-Fill Touchability Audit

- `demo_order_to_fill_gap_audit_v1` now explains `DEMO_ORDER_FLOW_PRESENT_NO_FILLS` by joining Demo orders, intents, state changes, fills, and BBO touchability.
- Linux 48h artifact-only smoke reviewed 6 Demo PostOnly buy orders, 0 fills, 6 inferred effective limits from `intents.details.limit_price`, and 6/6 deep passive no-touch orders with best-touch gaps about 1156-1531bp.
- PM read: the current blocker is order touchability / execution realism, not silent Cost Gate signal loss or a proven fill-recorder break; next profit path is touchability-aware bounded Demo probe design before any Cost Gate change.

## 2026-06-22 Demo-Learning Stack Activation Packet

- `demo_learning_stack_activation_packet_v1` now turns stack health + Cost Gate activation preflight into one no-authority operator review artifact.
- It reports missing four-cron stack entries, operator dry-run/apply/rollback/verify commands, and the intended Cost Gate escape thesis: rejected-signal accumulation -> matched-control blocked outcomes -> bounded demo probe review -> execution-realism repair.
- This improves the path to profitability by making the data-learning activation step reviewable without installing cron, lowering Cost Gate, enabling writers, granting probe/order authority, or claiming promotion proof.

## 2026-06-22 Bounded Probe Edge-Capture Execution Gap

- `bounded_demo_probe_evidence_quality_v1` now measures whether positive probe outcomes actually capture matched blocked-signal control edge via `probe_edge_capture_ratio` and `probe_execution_gap_bps`.
- Positive probes that underperform matched controls are routed to `BOUNDED_DEMO_PROBE_EXECUTION_REALISM_GAP` / `bounded_probe_execution_realism`, forcing slippage/timing/fill-quality/horizon-retiming investigation before Cost Gate/operator review.
- This strengthens the profitability path by separating alpha/control discovery from realized PnL capture; no Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof was granted.

## 2026-06-22 Bounded Probe Matched-Control Evidence Quality

- `bounded_demo_probe_result_review_v1` now emits `bounded_demo_probe_evidence_quality_v1`, comparing probe outcomes with matched same side-cell/horizon `blocked_signal_outcome` controls.
- Positive probe outcomes without matched controls are marked `anecdote_risk` and routed back to data coverage in profitability scorecard / runtime killboard / discovery loop / learning worklist.
- This strengthens the Cost Gate escape path toward controlled Demo mode learning evidence, but still grants no Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof.

## 2026-06-22 Bounded Probe Result Review Alpha Ingestion

- Profitability scorecard, runtime killboard, blocker taxonomy, and learning worklist now consume `bounded_demo_probe_result_review_v1`; post-probe outcomes can stop, continue, or require operator review in the main loop.
- Empty result-review artifacts remain evidence only and do not advance preflight closure; failed realized edge keeps the Cost Gate blocked, while learning-review candidates still require operator review and grant no promotion proof.
- Linux v399 smoke showed current result review has `NO_PROBE_OUTCOMES_RECORDED` / completed outcomes `0`, so the sealed path remains blocked by operator review with no Cost Gate lowering or probe/order authority.

## 2026-06-22 Bounded Demo-Probe Result Review

- Added no-authority `bounded_demo_probe_result_review_v1` so future probe outcomes can be classified into collect-more, first-review, stop, or learning-review states against the v397 design packet.
- The result review consumes only preflight JSON + JSONL ledger rows and preserves no Cost Gate lowering, no probe/order authority, no runtime mutation, and no promotion proof.
- Current path still lacks operator approval and real probe outcomes; this closes the post-probe stop/review artifact gap before any authority is granted.

## 2026-06-22 Sealed Horizon Bounded Probe Design

- `sealed_horizon_bounded_demo_probe_preflight_v1` now embeds inactive `bounded_demo_probe_design_v1` with candidate side-cell/horizon, edge snapshot, initial demo caps, success criteria, stop conditions, and required review artifacts.
- Profitability scorecard mirrors the bounded-probe design status/limits in top path evidence, making the operator-review step concrete without granting Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof.
- Current remaining gate is still actual operator review/authorization; the design packet is review input only.

## 2026-06-22 Cost Gate Learning-Lane Accumulation Gate

- A controlled artifact-only 168h learning-lane refresh produced 40,000 ledger rows, 20,000 blocked-signal outcomes, and a review candidate `ma_crossover|ETHUSDT|Sell`, proving the production learning lane can accumulate evidence from recorded rejects without lowering Cost Gate or submitting orders.
- `cost_gate_learning_lane.status --json-output` now writes canonical activation preflight artifacts; sealed preflight now reads that evidence and is reduced to `OPERATOR_REVIEW_REQUIRED` with production lane accumulating.
- Current remaining sealed-path blocker is actual operator review approval; no cron install, writer/env enablement, Cost Gate lowering, probe/order authority, or promotion proof has been granted.

## 2026-06-22 Sealed Horizon Preflight Refresh Wrapper

- Added an artifact-only `sealed_horizon_probe_preflight_cron.sh` wrapper so canonical sealed preflight latest/status/heartbeat can be refreshed without manual one-off commands.
- Linux smoke selected the v389 aligned sealed decision packet despite an explicit stale/generic latest, refreshing `/tmp/openclaw/cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json` sha256 `5cae49e9837285aced6835ff8199e3b2183c669846b5fd8a59cd0c11a47b157d`.
- Remaining blockers are unchanged: actual operator approval review and production learning-lane ledger/outcome accumulation; no cron install, Cost Gate lowering, probe/order authority, or promotion proof.

## 2026-06-22 Sealed Horizon Preflight Decision Resolver

- `sealed_horizon_probe_preflight.py` can now use `--decision-packet-search-root` to supersede a stale/generic explicit decision packet with a fresh aligned sealed decision packet.
- Linux smoke intentionally passed the old generic latest and verified the resolver selected the v389 sealed packet, preserving `decision_packet_aligned=true`.
- This closes source/artifact routing drift only; operator approval and production learning-lane accumulation remain the live blockers, with no Cost Gate lowering or probe/order authority.

## 2026-06-22 Sealed Horizon Operator Review Artifact

- Added a no-authority `sealed_horizon_operator_review_v1` builder for bounded demo-probe preflight review.
- Exact approval for the current leading path requires `approve_sealed_horizon_preflight:ma_crossover|BTCUSDT|Sell:240`, a fresh aligned preflight, and a non-empty operator id.
- Codex smoke generated only `PENDING_OPERATOR_REVIEW`; the remaining gates are actual operator approval plus production learning-lane accumulation, with no Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof.

## 2026-06-22 Profitability Engineering Closure

- Profitability path scorecard now consumes the sealed horizon probe preflight and emits `profitability_engineering_closure_v1`.
- Current leading path is still `ma_crossover|BTCUSDT|Sell@240m`, but it is now classified precisely as blocked by operator review plus production learning-lane accumulation.
- The closure keeps the strategy thesis explicit: cross Cost Gate with side-cell/horizon specialization, bounded demo learning, execution-realism proof, and stronger alpha search, not global Cost Gate lowering or Python-side authority.

## 2026-06-22 Sealed Horizon Bounded Demo-Probe Preflight

- Added a no-authority `sealed_horizon_bounded_demo_probe_preflight_v1` that makes sealed evidence, decision-packet alignment, operator review, production learning-lane accumulation, and authority boundary explicit before any bounded demo probe.
- Alpha discovery and learning worklist now ingest the preflight when present, so a sealed candidate can move from packet-only review into machine-checkable operator/prod-lane gates.
- The current BTCUSDT Sell/240m path still needs operator review and production learning-lane accumulation; no Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof was granted.

## 2026-06-22 Sealed Horizon Alpha Worklist Bridge

- Alpha discovery now recognizes `OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE` as a Cost Gate `READY_FOR_PROBE` review blocker instead of leaving it stranded in the decision packet.
- Learning worklist carries sealed horizon side-cell/horizon/outcome evidence and emits `operator_review_sealed_horizon_learning_evidence_before_bounded_demo_probe`.
- This makes the profit path more autonomous and reviewable, but still grants no runtime mutation, Cost Gate lowering, probe/order authority, or promotion proof.

## 2026-06-22 Sealed Horizon Evidence Review Bridge

- Profitability path scorecard now consumes `sealed_horizon_learning_evidence_v1`; passing evidence promotes the horizon path to `SEALED_HORIZON_LEARNING_EVIDENCE_READY_FOR_OPERATOR_REVIEW`.
- Profit-learning decision packet now consumes the same evidence and can emit `OPERATOR_REVIEW_SEALED_HORIZON_DEMO_PROBE_CANDIDATE`, with explicit next actions for operator review and production learning-lane activation/repair before any probe.
- This stops the loop from asking for more replay after sealed blocked-outcome evidence exists; it still grants no Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof.

## 2026-06-22 Sealed Horizon Learning Evidence Builder

- Added a reusable artifact-only builder that converts one sealed horizon plan candidate into mature reject materialization, candidate-horizon blocked outcomes, blocked-outcome review, and compact evidence packet.
- Linux smoke for `ma_crossover|BTCUSDT|Sell` at 240m produced 16,515 scratch blocked outcomes with avg net +3.0511bp and net-positive 68.56%, enough for operator review of bounded demo probe authority.
- This remains review evidence only: production learning lane is still not accumulating via writer/cron/prod ledger, and no Cost Gate lowering, probe/order authority, or promotion proof was granted.

## 2026-06-22 Sealed Horizon Learning Plan Bridge

- Demo-learning policy now consumes passed sealed horizon replay artifacts and selects `ma_crossover|BTCUSDT|Sell` as a 240m learning candidate without granting order/probe authority or lowering Cost Gate.
- Runtime adapter ledger rows now carry selected candidate summaries, including outcome horizon and sealed replay evidence, so blocked-signal outcomes can be attributed to the intended horizon.
- Price observation and outcome writers use row-level candidate horizon before defaulting to 60m; the next blocker remains runtime writer/cron/ledger/outcome accumulation, not another offline replay.

## 2026-06-22 Sealed Replay Profitability Scorecard Bridge

- Profitability path scorecard now consumes a passed horizon-specific sealed replay artifact and advances the matching horizon path to learning/outcome accumulation instead of re-requesting sealed replay construction.
- The path carries sealed replay hashes, best/primary horizon metrics, and failed-gate state while preserving no Cost Gate lowering, no probe/order authority, and no promotion proof.
- Runtime status is source-synced but still not accumulating learning-lane ledger/outcome rows; next blocker remains writer/cron/ledger activation under operator-reviewed boundaries.

## 2026-06-22 Horizon-Specific Sealed Replay Packet

- Added an artifact-only sealed replay packet that binds a preselected horizon retiming candidate to hashed replay counterfactual inputs.
- The packet checks candidate/replay/sample/net/hit-rate/primary-block/metric-drift gates without searching for a better side-cell, reducing hindsight-selection risk before operator review.
- Verification passed with py_compile, focused sealed-replay tests, related alpha/profitability tests, and diff-check; no PG/Bybit/runtime/order/probe/promotion authority was granted.

## 2026-06-22 Horizon Edge Amplification Packet

- Added an artifact-only packet that turns multi-horizon Cost Gate counterfactuals into ranked retiming/stable side-cell candidates.
- The packet makes BTCUSDT Sell style horizon retiming reviewable as a sealed replay path before any bounded demo probe review, without lowering the global Cost Gate.
- Verification passed with py_compile, focused horizon packet tests, related alpha/profitability tests, and diff-check; no PG/Bybit/runtime/order/probe/promotion authority was granted.

## 2026-06-22 Profitability Path Scorecard

- Added an artifact-only profitability scorecard that ranks bounded Cost Gate demo-learning, horizon retiming / side-cell filtering, low-friction MM alpha search, fee/scale, Polymarket lead-lag, and Gate-B event-wait paths in one machine-readable output.
- The scorecard makes the profit thesis explicit: cross the Cost Gate through bounded learning and execution-realism proof for ranked side-cells, not global gate relaxation.
- Fixed the demo data-flow monitor blocker caused by unescaped literal `%` patterns in psycopg SQL. No Cost Gate lowering, order/probe authority, runtime mutation, or promotion proof was granted.

## 2026-06-22 Cost Gate Downstream Effective-Sample Guard

- Bounded learning policy and historical scorecard review now consume the v381 effective sample fields, preferring `sample_count_for_gate` / `distinct_ts` before raw rows for sample gates, scoring, ranking, and compact outputs.
- Decision packet markdown now shows `sample_n` versus raw rows, reducing operator ambiguity when duplicated feature rows exist.
- Regression proves `n=500` with `sample_count_for_gate=3` cannot enter bounded demo probe or historical review; no Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof was granted.

## 2026-06-22 Cost Gate Reject Counterfactual Sample Guard

- Runtime read-only counterfactual showed Cost Gate blocks contain learning candidates: BTCUSDT Buy is positive at 15m/60m after 4bp friction, while 240m flips to BTCUSDT Sell and confirms BTCUSDT Buy blocked.
- Added `distinct_ts`, `timespan_minutes`, `rows_per_distinct_ts`, and `sample_count_for_gate` to Cost Gate reject counterfactual outputs, using distinct timestamps as the sample gate to prevent duplicate-row inflation.
- Verification passed with py_compile, focused counterfactual pytest, related Cost Gate/alpha pytest, and diff-check; no Cost Gate lowering, order/probe authority, PG write, Bybit call, or runtime source sync was performed.

## 2026-06-22 Demo Data Flow Runtime Refresh

- Direct read-only PG refresh confirmed demo/live_demo data is still accumulating: latest 1h has 2355 decision/risk rows, all rejected, and latest 24h has 61093 risk verdicts with 61090 rejects.
- Rejects are recorded and dominated by Cost Gate, so the evidence does not support silent-drop at the risk-recording layer.
- Order/fill evidence remains insufficient: only 3 approved/intents/orders in 24h, all demo flash_dip_buy PostOnly Working, and 0 fills; next step remains source reconcile plus bounded learning-lane/counterfactual review, not global Cost Gate lowering.

## 2026-06-22 Runtime Source Reconcile Current Target Dry Run

- Refreshed the read-only remote probe and apply dry-run against current `origin/main=34066e5e`, superseding the prior dry-run target `eaed0cf2`.
- `trade-core` still reports runtime HEAD `917be4cc`, target object unavailable, dirty/untracked 56, review-required 13, and apply dry-run status `DRY_RUN_OPERATOR_APPROVAL_REQUIRED` with 0 blockers and 10 previewed commands.
- No runtime fetch/pull/reset/clean/source sync was executed; v375-v377 demo-learning monitors/packets remain blocked from running on Linux until operator-approved reconcile. The dry-run is valid for recorded target `34066e5e`; any later apply target must rerun probe/dry-run first.

## 2026-06-22 Profit-Learning Packet Alpha Ingestion

- Wired `profit_learning_decision_packet_latest.json` into `alpha_discovery_throughput.runtime_runner`, profitability blocker classification, and `learning_worklist` evidence.
- Fresh packet states now drive alpha/worklist blockers such as counterfactual refresh, bounded-plan refresh, learning-stack repair, and operator probe review while preserving no-order/no-Cost-Gate-lowering boundaries.
- Verification passed locally with py_compile, focused alpha/worklist/decision-packet tests, and diff-check; runtime source is still unsynced, so this ingestion has not run on Linux yet.

## 2026-06-22 Profit-Learning Decision Packet

- Added `helper_scripts/research/cost_gate_learning_lane/decision_packet.py`, an artifact-only closure packet that consumes demo data-flow, counterfactual, bounded-plan, activation/stack-health, and blocked-outcome-review JSON.
- Packet fails closed into explicit next actions such as running counterfactual, building a bounded plan, repairing activation, or operator-reviewing blocked-outcome candidates; main Cost Gate lowering and order authority remain false.
- Verification passed locally with py_compile, focused packet tests, related Cost Gate/data-flow tests, and diff-check; runtime source is still unsynced, so the packet has not run on Linux yet.

## 2026-06-22 Demo Data Flow Rolling Monitor

- Added `helper_scripts/db/audit/demo_data_flow_monitor.py`, a read-only multi-window wrapper around `demo_order_stall_audit` for 1h/4h/24h demo/live_demo data-flow accumulation.
- Classifier distinguishes recent empty windows from broader Cost Gate reject walls, prior order-flow-without-fills, no-data, and fill-present states; main Cost Gate lowering remains false.
- Verification passed locally with py_compile and focused pytest; runtime source is still unsynced, so this monitor has not run on Linux yet.

## 2026-06-22 Runtime Source Reconcile Apply Packet

- Added `helper_scripts/deploy/runtime_source_reconcile_apply.py`, a dry-run-first apply packet helper for the reviewed runtime source reconcile.
- True runtime dry-run against then-current target `eaed0cf2` produced `DRY_RUN_OPERATOR_APPROVAL_REQUIRED` with 56 dirty/untracked paths, 13 review-required paths, and no blockers when exact expected values plus review packet/target-wins confirmation are supplied; rerun with current `origin/main` before any real apply.
- No runtime apply was performed; actual source reconcile still requires `--apply` plus `OPENCLAW_RUNTIME_SOURCE_RECONCILE_APPLY=1` and operator authorization.

## 2026-06-22 Runtime Source Reconcile Review Packet

- Added PM/Operator review packet for the 13 runtime source review-required paths found by the read-only remote probe.
- Recommended target-wins for stale docs/source/test paths after checking line counts and top-level Python symbols; no remote-only source symbols were found.
- Preserved the runtime-only `vol-event-robust-ruling.md` report into repo as a cleaned-format doc; still no runtime source sync, cron install, writer enablement, Cost Gate lowering, or order/probe authority.

## 2026-06-22 Runtime Source Remote Reconcile Probe

- Added `helper_scripts/deploy/runtime_source_remote_reconcile_probe.py` so Mac can compare local approved target tree to `trade-core` remote worktree over read-only SSH even when runtime lacks the target object.
- True runtime read-only probe found target `6e29c06f` unavailable on runtime, remote HEAD `917be4cc`, 56 dirty/untracked paths, 43 content-equivalent, and 13 review-required paths.
- Demo-learning stack remains absent; PG read-only evidence showed 1h demo/live_demo flow all zero, 4h decisions/risk=2699 with 2696 Cost Gate blocks, 3 Working flash_dip orders, and 0 fills.

## 2026-06-22 Runtime Source Reconcile Planner

- Added `helper_scripts/deploy/runtime_source_reconcile_planner.py` to turn the v370 manual runtime dirty-tree manifest into a reusable read-only JSON preflight.
- Planner classifies tracked/untracked dirty paths against a local target ref into content-equivalent vs review-required buckets and fails closed when the target ref is unavailable.
- Verification passed: `py_compile` plus focused pytest `4 passed`; no runtime source sync, cron install, writer enablement, Cost Gate lowering, or order/probe authority was performed.

## 2026-06-22 Runtime Source Reconcile Blocker Manifest

- Read-only runtime classification found `trade-core` still at HEAD `917be4cc`, stale runtime `origin/main=1401848b`, while GitHub/local main is `e2b90306`.
- Dirty tree has 55 paths: 43 are content-equivalent to current main, but 7 tracked paths, 3 untracked current-main paths, and the untracked Cost Gate learning-lane directory still need operator-approved preserve/reconcile handling.
- Demo-learning stack crons and health artifacts remain absent; no runtime fetch/pull/reset/clean/source sync or cron install was performed.

## 2026-06-22 Demo Learning Stack Healthcheck Cron Wiring

- Added `demo_learning_stack_healthcheck_cron.sh` plus dry-run-gated `install_demo_learning_stack_healthcheck_cron.sh` so the stack health latest JSON can self-refresh after an operator-approved install.
- `install_demo_learning_stack_crons.sh` now manages three child crons as one stack: demo evidence heartbeat, Cost Gate learning lane, and stack healthcheck refresher.
- Boundary stayed source/test/docs plus local temp artifact smoke only; no runtime source sync, cron install, writer enablement, Cost Gate lowering, or order/probe authority was performed.

## 2026-06-22 Demo Learning Stack Health Evidence Ingestion

- `demo_learning_stack_healthcheck.py` can now write an explicit local JSON artifact via `--json-output` while still printing stdout.
- Runtime killboard schema is now `alpha_discovery_runtime_killboard_v7`; it ingests the healthcheck latest artifact into the Cost Gate learning arm.
- Alpha learning worklist schema is now `alpha_learning_worklist_v4`; Cost Gate learning activation carries stack-health evidence, is operator-authorized runtime mutation, and requires `demo_learning_stack_healthcheck_status == EVIDENCE_STACK_ACTIVE` before completion.
- Boundary remains source/test/docs plus optional local JSON artifact output only; no runtime sync/install/write/order/Cost Gate relaxation was performed.

## 2026-06-22 Demo Learning Stack Post-Install Healthcheck

- Added `demo_learning_stack_healthcheck.py` as the read-only acceptance gate after runtime source reconcile and stack install.
- It checks source HEAD/dirty state, crontab entries, heartbeats, status JSONL freshness, latest demo evidence JSON, Cost Gate blocked-outcome review JSON, ledger/outcome counts, and classifies the stack into actionable states.
- This proves whether the learning loop is actually accumulating evidence before any bounded demo-probe review; no runtime sync/install/write/order/COST gate relaxation was performed.

## 2026-06-22 Demo Learning Stack Cron Installer

- Added `install_demo_learning_stack_crons.sh` as the operator-facing stack installer for demo-learning evidence plus Cost Gate learning-lane crons.
- The stack defaults to dry-run and apply requires expected HEAD, clean matching runtime source, Cost Gate preinstall refresh, and activation preflight before child installer apply.
- This reduces half-install/repeat-work risk, but no runtime source sync, cron install, writer enablement, Cost Gate lowering, or order authority was performed.

## 2026-06-22 Runtime Demo Cost Gate Read-Only Audit

- `trade-core` demo engine is alive, but runtime source remains behind/dirty at `917be4cc`; latest alpha artifact is stale `alpha_discovery_runtime_killboard_v1` and false-reports actionable alpha/probe.
- Runtime PG shows 4h demo/live_demo decision/risk rows exist (2,496), all Cost Gate rejects, but 4h intents/orders/fills are 0; 24h has only 3 intents/orders and 0 fills, and latest 1h had 0 rows at audit time.
- Cost Gate/demo-learning evidence crons are not installed; learning lane has only an old plan artifact, no heartbeat/status/ledger/outcome/review loop. Next step is operator-approved runtime source reconcile + activation preflight/install, not more source-only visibility work.

## 2026-06-22 Runtime Killboard Learning Completion Evidence v6

- Runtime killboard schema is now `alpha_discovery_runtime_killboard_v6`.
- Killboard/history mirror top learning task completion gate/status, completion evidence count, compact evidence, evidence key count, and Cost Gate top blocked-review candidate fields.
- This is artifact visibility only; runtime source still requires operator-approved reconcile before current code can refresh runtime artifacts.

## 2026-06-22 Learning Worklist Cost Gate Review Evidence v3

- Alpha learning worklist schema is now `alpha_learning_worklist_v3`.
- Cost Gate outcome/probe review tasks carry the ranked blocked side-cell, wrongful-block score, net cost cushion, review schema/status, and latest review top fields in task evidence.
- Cost Gate operator-probe objective now points to reviewing the top blocked side-cell before any bounded demo probe; no probe/order/promotion authority is granted.

## 2026-06-22 Cost Gate Blocked Outcome Review v2

- Blocked-signal outcome review schema is now `cost_gate_demo_learning_lane_blocked_outcome_review_v2`.
- Review rows rank side-cells by wrongful-block score, net cost cushion, sample margin, gross/cost aggregates, and horizon counts.
- Activation preflight, learning-loop status, cron status JSON, and alpha-discovery rows mirror the top review opportunity; this is review visibility only and grants no probe/order/promotion authority.

## 2026-06-22 Alpha Learning Worklist Completion Gates

- Alpha learning worklist schema is now `alpha_learning_worklist_v2`.
- Every task carries completion gate, completion status, and required completion evidence.
- This turns alpha-learning recommendations into machine-checkable work items without granting probe/order/promotion authority.

## 2026-06-22 Runtime Killboard Learning Worklist v5

- Runtime killboard schema is now `alpha_discovery_runtime_killboard_v5`.
- Latest/history alpha artifacts mirror learning worklist status, task counts, operator/runtime-mutation counts, and top learning task fields.
- This is artifact visibility only; runtime source remains behind/dirty/stale until operator-approved reconcile/sync.

## 2026-06-22 Alpha Learning Worklist

- Alpha discovery now emits `alpha_learning_worklist_v1` beside the profitability blocker scorecard.
- Blocker rows become ranked learning tasks such as runtime source reconcile, cost-gate learning activation, MM signal search, Polymarket replay history, or promotion review.
- Worklist tasks explicitly mark operator authorization and runtime mutation requirements; no probe/order/promotion authority is granted.

## 2026-06-22 Cost Gate Source Reconcile Manifest

- Cost-gate activation preflight now emits source reconcile status/reasons/actions plus a capped dirty-path manifest.
- Dirty runtime source becomes `DIRTY_PATH_REVIEW_REQUIRED`; behind-only source becomes `SOURCE_SYNC_REQUIRED`; clean matching source reports no reconcile required.
- Runtime blocker still external: trade-core remains behind/dirty/old-schema with no learning-lane heartbeat/ledger/outcome artifacts or writer env.

## 2026-06-21 Runtime Demo Accumulation Read-Only Audit

- Runtime PG still records demo/live_demo Cost Gate rejects: 1h has 2496 decision features / cost-gate features / risk rejects, but 0 intents/orders/fills.
- Cost-gate learning lane is not accumulating: only old plan artifact exists; no heartbeat/status/ledger/materializer/outcome refresh/review; engine writer env is unset.
- Runtime source remains behind/dirty/stale and alpha latest is old killboard schema v1 with false actionable flags until operator-approved sync/rerun.

## 2026-06-21 Cost Gate Multi-Horizon Counterfactual Stability

- Cost Gate rejected-signal scorecard now compares configured outcome horizons instead of relying on one holding window.
- Policy/cron/status/alpha rows surface horizon-stability status, candidate horizons, and best horizon for bounded demo-learning review.
- Boundary remains source/test/docs only: no runtime sync, artifact refresh, order authority, main Cost Gate lowering, PG/Bybit call, deploy, or restart.

## 2026-06-21 Cost Gate Recommendation Runtime Preflight Gate

- Cost Gate adjustment recommendations now consume runtime/source/writer readiness from `cost_gate_learning_preflight`.
- Source not activation-ready, required writer disabled, or required running-process writer disabled now blocks bounded learning/probe recommendations before any Cost Gate change.
- Alpha-discovery cost-gate rows propagate runtime preflight/source/writer fields; order authority remains `NOT_GRANTED` and main/global Cost Gate lowering remains `NONE/false`.

## 2026-06-21 Cost Gate Adjustment Recommendation Scorecard

- Demo learning evidence now emits `cost_gate_adjustment_recommendation`, explicitly separating no global main Cost Gate lowering from bounded learning-lane activation and bounded demo-probe review readiness.
- Recommendation statuses include `BOUNDED_LEARNING_LANE_ACTIVATION_RECOMMENDED`, `BOUNDED_DEMO_PROBE_AUTHORITY_REVIEW_READY`, data-flow restore, and order-to-fill diagnosis states.
- Alpha-discovery cost-gate rows carry the recommendation status/reason/next action and learning gate adjustment; order authority remains `NOT_GRANTED`.

## 2026-06-21 Demo Order-Flow Starvation Blocker

- Demo learning evidence now has an order-flow evidence scorecard that distinguishes Cost Gate reject wall with zero orders/fills from orders-without-fills and fills-present states.
- Alpha-discovery cost-gate rows can now expose `demo_cost_gate_reject_wall_no_order_flow_evidence` with next trigger `activate_cost_gate_learning_lane_then_operator_review_bounded_demo_probe`.
- This remains evidence-only: no main Cost Gate lowering, order authority, runtime sync, PG write, or Bybit call.

## 2026-06-21 Demo Learning Data-Flow Freshness Blocker

- Demo order-stall audit now emits learning-data freshness with a 90-minute stale threshold.
- Demo learning evidence routes stale candidate/reject/order-flow data to `DEMO_LEARNING_DATA_FLOW_STALE` before claiming Cost Gate reject accumulation.
- Alpha-discovery cost-gate blocker rows now expose `demo_learning_data_flow_stale`; runtime remains unsynced, while latest read-only PG shows decision/risk rows resumed but no 1h/4h intents/orders/fills.

## 2026-06-21 Runtime Killboard Source-Trusted Actionability v4

- Runtime killboard schema is now `alpha_discovery_runtime_killboard_v4`.
- Raw promotion candidates remain visible via `promotion_ready_count`, but `actionable_alpha_found` now also requires `runtime_source_activation_ready=true`.
- `actionable_probe_found` is source-trusted too, preventing stale/dirty/behind source from producing top-level actionable flags.

## 2026-06-21 Runtime Killboard Source-Readiness Visibility v3

- Runtime killboard schema is now `alpha_discovery_runtime_killboard_v3`.
- Alpha artifacts now carry top-level `runtime_source` plus mirrored source readiness/status fields in `killboard` and history JSONL.
- This makes stale/dirty/behind/mismatched runtime source visible beside alpha/probe status, but does not sync runtime or refresh current artifacts.

## 2026-06-21 Runtime Killboard Actionable-Alpha Semantics v2

- Runtime killboard schema is now `alpha_discovery_runtime_killboard_v2`.
- `actionable_alpha_found` now means profitability-scorecard `promotion_ready_count>0`; raw `READY_FOR_AEG_CHAIN` remains visible as `ready_for_aeg_chain` / `aeg_candidate_artifact_found`.
- This prevents Polymarket candidate artifacts lacking replay-history/execution-realism proof from being reported as actionable alpha.

## 2026-06-21 Polymarket Promotion-Ready Replay-History Gate

- Polymarket `READY_FOR_AEG_CHAIN` IC artifacts no longer count as profitability-scorecard `promotion_ready` until candidate replay is built, replay history is AEG-recheck-ready, and replay-history execution realism is `PASS`.
- Missing history now routes to data coverage, insufficient dated history to sample gate, and unmeasured/failed execution realism to robustness wait.
- This preserves AEG candidate artifacts while preventing stale or under-verified Polymarket IC from appearing as alpha promotion readiness.

## 2026-06-21 Cost-Gate Killboard Source-Readiness Blocker

- Runtime alpha latest still showed `cost_gate_demo_learning_lane` as `probe_ready` even though runtime source was behind/dirty and no learning cron/ledger/materializer was active; this is a stale-runtime-code artifact, not true readiness.
- Alpha runtime runner now attaches cost-gate source activation readiness into the arm detail when repo root is available.
- Discovery loop blocks cost-gate probe readiness with `source_health` / `cost_gate_learning_lane_source_not_activation_ready` whenever the learning-lane source checkout is not activation-ready.

## 2026-06-21 Cost-Gate Learning Pre-Install Refresh Bridge

- Added `OPENCLAW_COST_GATE_LEARNING_PREINSTALL_REFRESH_ONLY=1` to the cost-gate learning cron wrapper.
- This mode refreshes scorecard -> plan -> status only, then skips historical review, reject materializer, outcome refresh, and blocked-outcome review.
- Activation runbook now uses it after runtime source reconcile and before installer activation preflight, avoiding the plan-ready deadlock without bypassing preflight or appending runtime ledger rows.

## 2026-06-21 Cost-Gate Learning Scorecard Refresh Chain

- Cost-gate learning cron now refreshes the read-only reject counterfactual scorecard before plan refresh, reject materialization, blocked-outcome refresh, and review.
- Status and alpha-discovery blocker rows now expose scorecard rc/status/probe-candidate count; scorecard refresh failures become learning-loop errors.
- This completes the source-side recurring learning chain, but runtime remains untouched until operator source sync/activation approval.

## 2026-06-21 Cost-Gate Learning Plan Refresh Preflight

- Cost-gate learning cron now refreshes `demo_learning_lane_plan_latest.json` before reject materialization and records plan rc/status/selected count in the learning-loop status log.
- Activation preflight now distinguishes a fresh artifact from a usable policy: only recent, schema-correct, `READY_FOR_DEMO_LEARNING_PROBE`, `OPERATOR_REVIEW`, non-empty plans are activation-ready.
- Local smoke proved no-scorecard runs emit a diagnostic `SOURCE_SCORECARD_UNAVAILABLE` plan/status rather than silent decay; runtime remains untouched until operator source sync/activation approval.

## 2026-06-21 Cost-Gate Cron Installer Apply Preflight

- `install_cost_gate_learning_lane_cron.sh` now defaults to a read-only activation preflight before any crontab write, requiring an expected source head and source/activation/plan readiness.
- The installer deliberately does not require existing ledger rows; installing the cron is the bounded step that starts materializing PG rejects and refreshing blocked outcomes.
- Boundary remains source/test/docs only in this checkpoint: no runtime sync, cron install, env edit, writer enablement, ledger append, PG write, Bybit call, order authority, or Cost Gate lowering.

## 2026-06-21 Cost-Gate Learning Activation Runbook

- Added an operator-gated runtime activation runbook for the cost-gate demo-learning lane, covering read-only audit, dirty source reconcile/sync, preflight, cron install, append enablement, optional writer restart, observation, and rollback.
- The runbook is intentionally non-authorizing; current runtime blockers from v341 remain until operator approves source sync and activation.
- This shifts the remaining work from source-wrapper building to a controlled runtime activation procedure.

## 2026-06-21 Cost-Gate Runtime Activation Blocker Audit

- Read-only `trade-core` audit confirmed PG Cost Gate rejects are abundant (27,071 in last 4h; 4,423,477 total), so data source accumulation exists.
- Runtime learning lane is not active: source checkout is behind/dirty and missing the new status/materializer/cron files; no learning-lane cron entry, no ledger/materializer/review artifacts, and running engine writer env is unset.
- Next hard step is operator-approved runtime reconcile/sync + cron/writer/append activation, not another source-only wrapper or blind Cost Gate lowering.

## 2026-06-21 Cost-Gate Materializer Status Visibility

- `cost_gate_learning_lane.status` now exposes reject materializer evidence from `reject_materializer_latest.json` and the learning-loop status log; activation preflight and alpha-discovery rows show ran/enabled/append/materialized/appended/decision counts.
- Runtime read-only smoke confirmed current PG rejects can traverse local in-memory materializer -> blocked-outcome refresh -> review; latest BTCUSDT sample is `KEEP_COST_GATE_BLOCKED`, so evidence supports continuous learning rather than blind Cost Gate lowering.
- Boundary remains source/test/docs plus read-only runtime PG/artifact smoke only: no runtime sync, cron install, ledger append, PG write, Bybit call, order authority, writer enablement, or Cost Gate lowering.

## 2026-06-21 Cost-Gate Materializer Cron Wiring

- `cost_gate_learning_lane_cron.sh` now runs reject materialization before outcome refresh/review, so an activated loop can turn PG rejects into ledger rows and then blocked-signal outcomes in one scheduled path.
- Installer preview now exposes materialize/append toggles, and activation preflight requires `reject_materializer.py` as source readiness.
- Boundary remains source/test/docs only in this checkpoint: no runtime install, source sync, ledger append, PG write, writer enablement, order authority, or Cost Gate lowering.

## 2026-06-21 Cost-Gate Reject Materializer

- Added `cost_gate_learning_lane.reject_materializer` to convert recorded `learning.decision_features` cost-gate rejects into the existing `probe_admission_decision` JSONL contract.
- It reuses the runtime admission adapter and keeps `adapter_enabled=false`, so output is fail-closed evidence rows, not order authority.
- Runtime PG read-only probe confirmed current demo cost-gate negative-edge rows match the extractor; no ledger append, writer enablement, PG write, source sync, deploy, restart, or gate lowering was performed.

## 2026-06-21 Derived Profit Ranking Policy

- `cost_gate_learning_lane.policy` now derives `cost_gate_profit_opportunity_ranking_v1` from legacy scorecard rows when embedded ranking is absent.
- Current runtime latest scorecard now produces source `derived_from_scorecard_rows` and ranked ETH/NEAR/LTC/ATOM Sell candidates without any runtime write or artifact refresh.
- Boundary remains unchanged: no writer enablement, order authority, ledger append, main Cost Gate lowering, PG write, Bybit call, source sync, deploy, rebuild, or restart.

## 2026-06-21 Profit Ranking Policy Selection

- `cost_gate_learning_lane.policy` now consumes `cost_gate_profit_opportunity_ranking_v1` as the preferred selection source when present.
- Ranked top-side-cells preserve `profit_priority_score/tier/components/next_action` in the plan, while sample gate and `NOT_GRANTED/NONE/false` authority boundaries remain mandatory.
- Current runtime latest artifact still lacks the ranking until refreshed, so production plan generation falls back to legacy; local read-only trial confirmed refreshed ranking will drive ETH/NEAR/LTC/ATOM order.

## 2026-06-21 Cost-Gate Profit Opportunity Ranking

- `cost_gate_reject_counterfactual.py` now emits `cost_gate_profit_opportunity_ranking_v1` inside the existing learning-lane scorecard.
- Ranking turns blocked side-cells into a direct next-action list: top current runtime artifact is `ma_crossover|ETHUSDT|Sell` with `priority_score=74.4954`, while NEAR/LTC/ATOM Sell are lower priority and FIL Buy remains sample-gated.
- This is the deliberate pivot away from more wrappers/preflights: rank profit-learning opportunities first; runtime activation remains operator-gated and still has no order authority or main Cost Gate lowering.

## 2026-06-21 Demo Learning Evidence Cron Installer

- Added `install_demo_learning_evidence_audit_cron.sh` as the reviewed Linux crontab installer for the demo-learning evidence heartbeat.
- It defaults to dry-run, requires `OPENCLAW_DEMO_LEARNING_EVIDENCE_CRON_APPLY=1` for install/remove, validates cron inputs, and preserves expected-head/runtime-env/process-writer preflight knobs.
- Boundary remains source/test/docs only: no runtime install, source sync, env edit, writer enablement, Cost Gate lowering, order authority, PG write, Bybit call, or restart.

## 2026-06-21 Demo Learning Evidence Killboard Ingestion

- Alpha-discovery now reads `demo_learning_evidence_audit_latest.json` into the cost-gate demo-learning arm.
- Fresh composite PG evidence outranks historical-only review when classifying missing learning-ledger blockers; observation-only telemetry no longer implies probe readiness.

## 2026-06-21 Demo Learning Evidence Artifact Wrapper

- Added `demo_learning_evidence_audit_cron.sh` so demo learning status has a recurring read-only evidence heartbeat instead of manual multi-command diagnosis.
- The wrapper records PG reject/context status plus cost-gate learning ledger/source/process readiness, but grants no order authority, writer activation, cron install, or Cost Gate lowering.

## 2026-06-21 Cost-Gate Historical Scorecard Review

- Added a separate `cost_gate_learning_lane.historical_review` artifact so old counterfactual scorecards can prioritize reject capture without being treated as runtime evidence.
- Alpha discovery now routes historical-scorecard-only candidates to `historical_cost_gate_candidates_not_runtime_verified`, not `READY_FOR_PROBE`.
- Boundary remains strict: historical review is not probe ledger/fill/execution evidence, has `order_authority=NOT_GRANTED`, and does not lower the main Cost Gate.

## 2026-06-21 Cost-Gate Learning Engine PID Auto-Detect Preflight

- `cost_gate_learning_lane.status` now auto-detects the engine PID when process-writer enablement is required and no PID/proc path is supplied.
- Detection scans `/proc/*/cmdline` and only accepts argv[0] basename `openclaw-engine`, avoiding shell/pgrep false positives.
- Preflight reports `engine_pid_detection_status`, detected PID, candidate count, and clearer `ENGINE_PROCESS_NOT_FOUND` / `ENGINE_PROCESS_DETECTION_UNAVAILABLE` statuses.

## 2026-06-21 Cost-Gate Learning Running-Process Preflight

- `cost_gate_learning_lane.status` can now inspect active engine process env via `--engine-pid` or `--runtime-proc-environ`.
- Preflight emits `writer_process.*` plus `answers.runtime_writer_process_enabled/status`, and can fail-closed with `running_engine_writer_not_enabled`.
- This separates env-file intent from the running engine actually loading `OPENCLAW_DEMO_LEARNING_LANE_WRITER`.

## 2026-06-21 Cost-Gate Learning Writer Config Preflight

- `cost_gate_learning_lane.status` now reports `writer_config.*` and can inspect `--runtime-env-file` plus fail-closed under `--require-writer-enabled`.
- `restart_all.sh` now forwards `OPENCLAW_DEMO_LEARNING_LANE_WRITER/PLAN/LEDGER` from operator env or `basic_system_services.env` into the Rust engine process.
- Rust writer treats blank plan/ledger overrides as unset, so restart-wrapper empty pass-through keeps default `$OPENCLAW_DATA_DIR/cost_gate_learning_lane/` paths.

## 2026-06-21 Cost-Gate Learning Capture-Error Diagnostics

- Extended Rust demo-learning writer with durable `probe_capture_error` rows for eligible rejects that cannot be admission-evaluated due plan/path/config failure.
- `cost_gate_learning_lane.status` now reports `CAPTURE_ERRORS_PRESENT`, `capture_error_count`, `captured_reject_count`, and `CAPTURE_ERRORS_NEED_OPERATOR_FIX`.
- Alpha discovery now routes capture-error-only ledgers to data-coverage work instead of treating them as normal evidence accumulation.

## 2026-06-21 Cost-Gate Learning Expected-Head Gate

- Extended `cost_gate_learning_lane.status` with optional `--expected-head` / `OPENCLAW_EXPECTED_SOURCE_HEAD`.
- Preflight now compares runtime `HEAD` directly with the PM-pushed commit and reports `expected_head_status`, `expected_head_matches`, and `expected_source_head_mismatch` blockers.
- This avoids relying only on runtime local upstream refs, which may be stale if `trade-core` has not fetched.

## 2026-06-21 Cost-Gate Learning Source-Sync Activation Gate

- Extended `cost_gate_learning_lane.status` with read-only local git checkout readiness: head, branch/upstream, ahead/behind, dirty/untracked counts, and dirty path sample.
- Preflight now emits `source_activation_status`, `source_activation_ready`, `runtime_source_ready_for_activation`, and aggregate `activation_blockers`.
- This directly captures the current runtime blocker: Linux `trade-core` is behind origin/main and dirty, so learning writer/cron activation must wait for operator-approved source sync/reconcile.

## 2026-06-21 Cost-Gate Learning Activation Preflight

- Added `cost_gate_learning_lane.status` as the public read-only status/preflight surface for the demo-learning lane.
- It now answers directly whether ledger rows have accumulated, whether evidence is currently accumulating, whether rejects are recorded, whether silent-drop risk remains, and whether blocked-signal review evidence is available.
- `alpha_discovery_throughput.runtime_runner` now imports the public status helpers, so killboard and operator preflight read the same artifact state. Runtime still needs operator-approved source sync/install/enable before trade-core can accumulate evidence.

## 2026-06-21 Cost-Gate Learning Loop Status Ingestion

- Added alpha-discovery ingestion for cost-gate learning-loop heartbeat, status log, latest refresh artifact, and latest blocked-outcome review artifact.
- Runtime blocker rows now expose `learning_loop_status` such as `NOT_SEEN` or `RUNNING_NO_LEDGER_ROWS`, plus latest rc/ledger/review fields, so lack of accumulation is machine-visible.
- Read-only Linux probe still found no heartbeat/status log/ledger/review artifact; source now reports that state, but runtime still needs operator-approved sync/install/enable before evidence can accumulate.

## 2026-06-21 Cost-Gate Learning Readiness Classification

- Fixed alpha-discovery semantics: a cost-gate learning plan with `OPERATOR_REVIEW` no longer counts as global `READY_FOR_PROBE` while the runtime ledger is missing/empty.
- Missing ledger / admission-only ledger / insufficient blocked outcomes now route to data-coverage or sample-gate work; only a positive blocked-outcome review candidate becomes operator-review actionable.
- This keeps `actionable_probe_found` aligned with actual demo-learning evidence accumulation, not just a plan artifact.

## 2026-06-21 Cost-Gate Learning Lane Cron Loop

- Read-only Linux probe found runtime `trade-core` behind origin by 5 commits and dirty; `/tmp/openclaw/cost_gate_learning_lane/` had no `probe_ledger.jsonl` and no `blocked_outcome_review_latest.json`, so demo cost-gate rejects are not yet accumulating enough outcome evidence on runtime.
- Added artifact-only `cost_gate_learning_lane_cron.sh` plus dry-run-gated installer to run blocked-outcome refresh and outcome-review hourly once operator syncs/enables it.
- Boundary remains strict: readonly PG plus local JSONL/JSON/log/heartbeat writes only; no order authority, main Cost Gate lowering, PG write, Bybit call, deploy, restart, or runtime mutation.

## 2026-06-21 Cost-Gate Blocked Outcome Review Scorecard

- Added artifact-only `cost_gate_learning_lane.outcome_review`, grouping `blocked_signal_outcome` ledger rows by side-cell and classifying them as collect-more, keep-blocked, or demo-probe-authority review candidates.
- Default thresholds are intentionally conservative (`n>=3`, avg net >= 0bp, net-positive pct >= 60%); output never grants order authority, lowers the main Cost Gate, or becomes promotion evidence.
- Alpha-discovery now surfaces `blocked_signal_outcome_review_status` and uses the scorecard's next trigger instead of a generic human-review string.

## 2026-06-21 Cost-Gate Outcome Refresh Loop

- Added artifact-only `cost_gate_learning_lane.outcome_refresh`, a one-command dry-run/append loop from `probe_ledger.jsonl` plus local/read-only-PG prices to missing `blocked_signal_outcome` / `probe_outcome` rows.
- The CLI requires explicit outcome targets and only appends when `--append-ledger` is set; `--source-pg` skips PG connection when no missing outcome windows exist.
- Alpha-discovery now routes admission-only cost-gate progress to `run_cost_gate_outcome_refresh_for_blocked_signal_outcomes`; still no order authority, main cost-gate lowering, PG write, Bybit call, or runtime mutation.

## 2026-06-21 Cost-Gate Read-Only Kline Observation Adapter

- Extended `cost_gate_learning_lane.price_observations` with `--source-pg`, a read-only SELECT-only Adapter over local `market.klines` for ledger-derived observation windows.
- The Adapter reuses `connect_report_pg`, rolls back setup state, and switches to `readonly=True, autocommit=True`; local file sourcing remains available through `--source-prices`.
- This moves blocked-signal outcome generation closer to autonomous evidence accumulation, but still adds no PG write, Bybit call, runtime mutation, order authority, or Cost Gate relaxation.

## 2026-06-21 Cost-Gate Price Observation Builder

- Added artifact-only `cost_gate_learning_lane.price_observations` to turn probe ledger admission rows into required local price observation windows.
- The builder normalizes local price/kline JSON/JSONL into rows that `runtime_adapter --price-observations` can consume, reducing manual data stitching before `--record-blocked-outcomes`.
- Alpha-discovery now points admission-only cost-gate ledger progress to `build_price_observations_then_record_blocked_signal_outcomes`; no order authority, main cost-gate lowering, PG/Bybit call, or runtime mutation was added.

## 2026-06-21 Cost-Gate Blocked-Signal Outcome Feedback

- Extended `runtime_adapter --record-blocked-outcomes` to append `blocked_signal_outcome` markout rows for recorded rejects that were not allowed to submit orders, including current `ORDER_AUTHORITY_NOT_GRANTED` rows.
- These rows are not `probe_outcome`, do not feed probe auto-disable or order authority, and remain `promotion_evidence=false`; they answer whether blocked signals later moved profitably.
- Alpha-discovery now summarizes the cost-gate probe ledger status/counts and changes next triggers based on actual progress: enable writer, record blocked outcomes, or review blocked outcomes before any probe authority.

## 2026-06-21 Cost-Gate Demo-Learning Lane Runtime Ledger Writer

- Added env-gated Rust `demo_learning_lane_writer`, wired from engine startup through all paper/demo/live pipeline deps into `TickPipeline`.
- Eligible demo/live_demo `cost_gate_js_demo_negative_edge` exchange-gate rejects now have a bounded non-blocking path to append `probe_admission_decision` JSONL rows when `OPENCLAW_DEMO_LEARNING_LANE_WRITER=1|true`.
- The writer dedupes by `attempt_id`, evaluates the existing Rust admission policy off hot path, flushes after successful writes, and hard-codes adapter enablement to false so enabling the writer cannot grant order authority. Current selected side-cells still record `ORDER_AUTHORITY_NOT_GRANTED`; no main cost-gate relaxation or order routing was added.

## 2026-06-21 Cost-Gate Demo-Learning Lane Hot-Path Adapter

- Added pure Rust `demo_learning_lane_hot_path` adapter plus tests to convert eligible demo/live_demo cost-gate negative-edge exchange rejects into `RejectEvent` learning shape.
- `step_4_5_dispatch` now recognizes those rejects and emits a `demo_learning_lane` debug trace, so the next runtime sink can append every eligible rejected signal instead of silently losing it.
- Boundary remains strict: no ledger append yet, no order authority, no main cost-gate lowering, no PG/Bybit/runtime mutation; selected side-cells still remain `ORDER_AUTHORITY_NOT_GRANTED`.

## 2026-06-21 Cost-Gate Demo-Learning Lane Outcome Writer

- Added artifact-only `outcome_writer.py` and shared `contract.py` for the cost-gate demo-learning lane.
- `runtime_adapter --record-outcomes` can append idempotent `probe_outcome` markout rows for admitted probes from local price observations, including gross/net bps and explicit cost.
- These outcomes feed the existing failed-outcome auto-disable path; current plan still has `order_authority=NOT_GRANTED`, so this is learning infrastructure, not order routing or main cost-gate relaxation.

## 2026-06-21 Cost-Gate Demo-Learning Lane Rust Policy Seam

- Added pure Rust `openclaw_engine::demo_learning_lane` policy + tests, mirroring the Python adapter inside the trading-authority codebase without hot-path wiring.
- Current selected side-cells still remain `ORDER_AUTHORITY_NOT_GRANTED`; admission requires explicit `DEMO_LEARNING_PROBE_GRANTED`, adapter enablement, normal risk state, budget/cooldown/outcome checks, and demo/live_demo mode.
- Python planner/runtime adapter and Rust policy now fail closed on future artifact timestamps. Next work remains operator-reviewed hot-path wiring plus durable probe outcome labels, not main cost-gate lowering.

## 2026-06-21 Cost-Gate Demo-Learning Lane Runtime Adapter

- Added `runtime_adapter.py` for the cost-gate demo-learning lane: plan + rejected demo event + JSONL ledger -> fail-closed admission decision.
- Matching selected side-cells still return `ORDER_AUTHORITY_NOT_GRANTED` under the current plan; future admission requires explicit `DEMO_LEARNING_PROBE_GRANTED` plus adapter enablement.
- The adapter tracks budget, cooldown, and failed `probe_outcome` rows for auto-disable, but it is artifact-only and does not submit orders. Actual demo-order routing must be Rust hot-path work after operator review.

## 2026-06-21 Cost-Gate Demo-Learning Lane Plan

- Added artifact-only `cost_gate_demo_learning_lane_plan_v1`: consumes the counterfactual scorecard, selects bounded demo-only side-cell probes, and keeps `main_cost_gate_adjustment=NONE` / `order_authority=NOT_GRANTED`.
- Latest Linux plan selected `ma_crossover ETH/NEAR Sell` and `grid_trading LTC/ATOM Sell`, 2 demo-only probe proposals each; confirmed blocks and data-coverage blockers stay separated.
- Alpha-discovery now reports `ACTIONABLE_PROBE_READY` from `cost_gate_demo_learning_lane`, with `actionable_alpha_found=false` and promotion-ready count 0. Next work is runtime adapter + durable probe outcome labels, not global gate lowering.

## 2026-06-21 Cost-Gate Learning-Lane Scorecard

- Upgraded the cost-gate reject counterfactual audit to v2 with JSON output and per-row learning-lane actions.
- Latest Linux read-only artifact has 4 probe candidates: `ma_crossover ETH/NEAR Sell` and `grid_trading LTC/ATOM Sell`; `atr_unavailable` rows are data-coverage blockers, not probe candidates.
- This is candidate-selection evidence for a future bounded demo-learning lane; it does not lower the main cost gate or grant trading authority.

## 2026-06-21 Cost-Gate Reject Counterfactual Learning Loop

- Demo no-order root cause is cost-gate rejection before order creation, not market-data failure; rejects persist to `risk_verdicts`/`decision_features` but not `trading.intents`, and recent outcome labels are effectively missing.
- Added read-only `cost_gate_reject_counterfactual.py`; 168h artifact shows BTC Buy rejects correctly blocked, while ETH/NEAR Sell rejects contain side-cell learning value.
- PM rule: do not globally lower the main cost gate; build a bounded demo-learning lane with small exploration budget, durable blocked/explored labels, and edge-estimate feedback.

## 2026-06-21 Polymarket Label Maturity / Price Catch-Up Routing

- Root diagnosis: Polymarket lead-lag had durable snapshots but zero joined IC rows; alpha only reported generic sample gate, hiding whether the next wait was label horizon maturity or PG 1m price catch-up.
- Added alpha runtime detail fields from `label_readiness`: `latest_feature_ts_utc`, `latest_price_ts_utc_by_symbol`, `oldest_unmatured_exit_target_utc`, and `newest_unmatured_exit_target_utc`.
- Added blocker split: `label_horizon_not_matured` before target maturity; `price_data_not_caught_up_to_label_target` when report time is past the oldest target but latest 1m price is still behind it.
- Runtime evidence after waiting past the first target: lead-lag sha256 `199fb15e150298ab076fb47e08513546e3e82c02153a5174da09edaa56b995c1`, `snapshot_rows=3555`, `feature_points=39`, `joined_rows=0`, `latest_feature_ts_utc=2026-06-20T22:07:01.434000+00:00`, all latest 1m prices at `2026-06-20T22:06:00+00:00`.
- Alpha sha256 `a77a709ec1f80bd5057a96d6874b297cbf5bdb7e821cdc796050d7f5129585f5` remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, but Polymarket next trigger is now precise: wait for price data to cover the oldest label target, then rerun lead-lag.
- Verification: Mac and Linux alpha+Polymarket suites `59 passed`; Mac cron static `9 passed`; Linux alpha suite `34 passed`; py_compile, diff-check, and artifact-only alpha runtime smoke passed.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifacts only; no PG write, Bybit private/signed/trading call, engine/API restart, strategy/auth/risk/order mutation, signal, execution proof, or promotion proof.

## 2026-06-20 Polymarket Durable Snapshot Mirror

- Root diagnosis: Polymarket lead-lag history had a runtime evidence-loop defect. Snapshot run dirs lived only under volatile `/tmp/openclaw/polymarket_axis_runs`, so `/tmp` cleanup could collapse a 30+ sample watch/history path back to zero.
- Added append-only collector mirroring: `polymarket_axis` copies completed run dirs to `$BASE/../archive/polymarket_axis_runs` through `--mirror-artifact-root`, preserving run IDs without overwriting existing evidence.
- Added lead-lag mirror loading: `polymarket_leadlag` v0.15 merges primary `/tmp` rows with mirror roots, lets primary rows win, skips duplicate mirror run IDs, and reports mirror metadata in `snapshot_meta`.
- Runtime smoke: latest lead-lag sha256 `e86ca7daf701da329b76ee51deddc552005a829480a3b0926c30b4b6f8dfb4f7` sees `2685` snapshot rows, `3` distinct timestamps, `3` distinct run dirs, and `1` duplicate mirror run skipped.
- Still not alpha: `joined_rows=0`, `max_overlap_adjusted_ic_points=0`, verdict `INSUFFICIENT_SAMPLE`; latest alpha sha256 `1619ca99dbfe10c22ee79d83cf44312aae434687c03fd4bfaa5ccfe94a4ff825` remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`.
- Verification: Mac and Linux research suites `110 passed, 1 skipped`; cron static suites `22 passed`; py_compile, bash syntax, diff-check, and Linux artifact-only runtime smokes passed.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifacts + sibling archive artifact mirror only; no PG write, Bybit private/signed/trading call, engine/API restart, strategy/auth/risk/order mutation, signal, execution proof, or promotion proof.

## 2026-06-20 MM Low-Friction Interaction Search

- Added bounded three-way MM low-friction interaction candidates: high quoted spread × quiet immediate tape/L1 context × favorable same-side touch/flow.
- Runtime result: the interaction search improves best train-confirmed min gross to `1.871bp`, but still leaves a `2.129bp` gap to the 4.0bp current-fee round trip.
- Fresh Linux fill_sim sha256 `d453ea298f1b2b427b6558d659fdcbeaf6f7db7e9fe40d52d2183a672b1e1518`: 224 low-friction candidates, 128 interaction candidates, 71 train-confirmed positive-gross candidates, 0 current-fee-confirmed candidates.
- Best train-confirmed interaction is `quoted_half_spread_bps_train_p90_and_recent_trade_count_30s_train_p25_and_side_recent_trade_imbalance_30s_train_p90`: train gross `1.871bp`, holdout gross `2.831bp`, min gross `1.871bp`.
- Best holdout gross near miss is still below current fee: `quoted_half_spread_bps_train_p90_and_side_touch_size_delta_frac_10s_train_p90`, holdout gross `3.813bp`, net `-0.187bp`, train gross `1.857bp`.
- Latest alpha sha256 `4902cbcbc6a0c8cbf19255553954a50a4b68ec176669c8df79cab85c4ccb1433` remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`; MM blocker stays cost-wall, not promotion-ready.
- Boundary: artifact-only source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact writes only; no PG write, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, signal, execution proof, or promotion proof.

## 2026-06-20 MM Train-Confirmed Low-Friction Gross Scorecard

- Added `train_confirmed_gross_scorecard` inside `fill_sim_low_friction_signal_scorecard()`, ranking every low-friction MM candidate by `min(train_edge_before_fees_bps, holdout_edge_before_fees_bps)`.
- Diagnosis: the apparent current-fee-positive low-friction cell is holdout-only, not a stable signal. Current best holdout-only cell has holdout gross `5.868bp` / net `1.868bp` but train gross `-0.336bp`.
- Fresh Linux fill_sim sha256 `a74353a05a99bd28a04acee932af86d5f7ab72ea3b40e5a497dd0303ec0ff408`: 96 low-friction candidates, 44 train-confirmed positive-gross candidates, 0 train-confirmed current-fee candidates.
- Best train-confirmed candidate is `quoted_half_spread_bps_train_p75_and_side_touch_size_delta_frac_10s_train_p90`: train gross `2.009bp`, holdout gross `1.402bp`, min gross `1.402bp`, gap `2.598bp` to the 4.0bp current-fee round trip.
- Latest alpha sha256 `18463765c3dd1ad94b36cdfbee9a04b723491ace0a88bfb958257838dd6721ed` remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`; MM blocker is now `low_friction_current_fee_holdout_not_train_confirmed`, next trigger `search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip`.
- Verification: Mac focused `53 passed`, Linux focused `53 passed`, py_compile, diff-check, selective Linux source sync, and read-only fill_sim/MM verdict/alpha runtime smokes passed.
- Boundary: artifact-only source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact writes only; read-only PG SELECT via wrappers; no PG write/schema migration, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, signal, execution proof, or promotion proof.

## 2026-06-20 Polymarket Replay History Accumulator

- Added `polymarket_leadlag.replay_history`, an artifact-only accumulator that scans dated lead-lag reports, dedupes explicit replay samples by candidate/sample id, merges PBO daily grids, and writes AEG-compatible history evidence.
- Existing `polymarket_leadlag_ic_cron.sh` now runs the accumulator fail-soft after each IC refresh and logs `candidate_replay_history_*` fields.
- Latest natural cron evidence: candidate `polymarket_leadlag_ic|price_target|SOLUSDT|15m`, report_count=4, matched=4, sample=33, n_days=1, net mean `0.12063233bp`, history status `REPLAY_HISTORY_DAYS_INSUFFICIENT`.
- AEG direct rows consume the history evidence, but candidate metrics remain `FAIL` with `n_days_below_30` and `missing_pbo`; PSR is only `0.50811419`, DSR `0.0`, execution realism `UNMEASURED`.
- Alpha scorecard remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, promotion_ready=0. This closes an automation gap, not the profitability gap.
- Boundary: artifact-only; no PG write, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, signal, execution proof, or promotion proof.

## 2026-06-20 Polymarket Lead-Lag Candidate Replay PnL

- Added deterministic paper replay for Polymarket IC candidates: `side = sign(IC) * sign(delta_prob_yes)`, explicit diagnostic round-trip cost default 4.0bp.
- Runtime candidate remains `polymarket_leadlag_ic|price_target|SOLUSDT|15m`; replay sample=32, gross mean `4.771bp`, net mean `0.771bp`, holdout net mean `6.829bp`.
- Important diagnosis: this is weak positive paper PnL, not executable alpha. Only `n_days=1`, `net_to_cost_ratio≈0.193`, `psr_0≈0.551`, PBO missing, price-feedback warning true, and execution realism is `UNMEASURED`.
- Direct candidate rows and candidate metrics now preserve the original `candidate_key`; replay candidate metrics remain `FAIL` with `n_days_below_30` and `missing_pbo`.
- Formal replay matrix stays `final_label_counts={"insufficient evidence":3}`, `coverage_gate_status=FAIL`, `execution_realism_mode=unverified_missing_missing`; alpha latest stays `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, promotion_ready=0.
- Next useful work: accumulate dated replay samples and build real execution/breadth evidence. Do not rerun AEG as if the current single-day replay solved profitability.
- Boundary: artifact-only research; read-only PG via existing lead-lag cron; no PG write, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, signal, execution proof, or promotion proof.

## 2026-06-20 FlashDip Execution-Realism Cron/Killboard Arm

- Added read-only `flash_dip_execution_realism_cron.sh` and alpha-discovery arm `flash_dip_execution_realism`.
- Diagnosis: K6 touchability alone is insufficient; we need durable evidence separating daily-exit failure from still-live short-exit research.
- Latest trade-core execution-realism sha256 `68c0c5ad486fbf2c71be95eea41c1861472bd7f03411e0da48d3d0e2cf375aa3`, generated `2026-06-20T17:49:51Z`.
- K6/N2/C3/nf0.005: 10bps daily-exit gate filled 68 events across 38 days but remains `EXECUTION_REALISM_BLOCKED`, gate annret `-2.56%`.
- Short-exit research signal remains: best 240m, 0bps buffer, n=72, 39 days, annret `1.73%`, maxDD `0.00033`.
- Alpha discovery latest sha256 `225de153dafec013270530b64883c0c6317082a56f66c118c1c55f042bc4bc2c` adds blocker `daily_exit_execution_realism_blocked_short_exit_needs_l1_replay`; global status remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, ready/probe=0.
- Linux user cron installed at `29 6 * * *`, before L1 replay at `31 6 * * *`; backup `/tmp/openclaw/cron_backups/crontab_before_flash_dip_execution_realism_20260620T175028Z.txt`.
- Boundary: source/test/docs + selective Linux source sync + user crontab + `/tmp/openclaw` artifact/status/log writes only; no PG write, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, retune authority, or promotion proof.

## 2026-06-20 FlashDip Touchability Action Scorecard

- Added diagnostic-only `touchability.action_scorecard` to alpha-discovery FlashDip runtime detail and blocker rows.
- Diagnosis: K15 no-touch is not enough as an endpoint; the K-ladder should tell us whether a shallower, testable research band exists before any retune discussion.
- Latest trade-core alpha-discovery artifact sha256 `8d5f58856ece9ff6e79839fbe055782a62a7517b41e1210b9fd6271a7160dd96`, `created_at_utc=2026-06-20T17:38:03.411654+00:00`.
- Runtime evidence: configured K15 has `0/18` touches; deepest shallower candidate with touches is K6 with `2/18` touches (`11.1111%`); `touchable_lower_k_count=7`.
- FlashDip blocker row now reports `touchability_action_status=SHALLOW_REPRICE_RESEARCH_BAND_PRESENT`, `research_candidate_k_pct=6.0`, and next trigger `run_shallow_k_execution_realism_then_l1_replay_before_any_retune`.
- Global alpha-discovery status remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, ready/probe=0; this only turns passive wait into a concrete read-only research trigger.
- Verification: Mac and Linux focused `test_alpha_discovery_throughput.py` `22 passed`; py_compile, targeted diff-check, and read-only runtime smoke passed.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG write, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, retune authority, or promotion proof.

## 2026-06-20 MM Sample-Gated Cost-Wall Diagnosis

- Added `sample_gated_cost_wall_summary` to `recorder_mm_verdict_cron.sh` and passed it through alpha-discovery runtime/blocker rows.
- Diagnosis: MM no-profit should not be anchored on the best live-markout symbol when that symbol has only one maker fill; use fill_sim sample-gated cells as the primary cost-wall evidence.
- Latest trade-core MM verdict status line sha256 `fe2ae9b675b11e4e43ebc8ba4bfbd704e30478db8d9cf18be1293cc310d8a5d5`, `ts_utc=2026-06-20T17:28:30Z`.
- Sample-gated fill_sim cost wall: status `SAMPLE_GATED_CURRENT_FEE_COST_WALL`, 74 sample-gated cells, best current-fee cell `LABUSDT` / back / informed_skip, `n=170`, net `-1.73bp`, fee shortfall `1.73bp RT`.
- Break-even maker fee remains `1.135bp/side`; fee reduction needed is `0.865bp/side`.
- Live-markout best remains `ARBUSDT` net `-0.0357bp`, but `best_n_maker_fills=1`, so it is diagnostic only and no longer the main MM cost-wall anchor.
- Latest alpha discovery sha256 `05301d674686b2763f122b915a47d7837a36ff5829c22c44abda81d9fc0727ad` remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, ready/probe=0; MM primary blocker is still `no_train_positive_walk_forward_feature_cell` with secondary sample-gated cost wall, live-markout diagnostic cost wall, and VIP5 scale/fee path.
- Verification: Mac and Linux focused suite `58 passed`; py_compile, bash syntax, diff-check, and read-only runtime wrapper smoke passed.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG write, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Pre-Gate Watchlist Persistence

- Upgraded `polymarket_leadlag` to report schema/runner v0.13.
- Added diagnostic-only `pre_gate_watchlist_persistence_scorecard`, passed through Polymarket cron status and alpha-discovery Polymarket blocker rows.
- Diagnosis: recurring pre-gate HAC cells are not enough; they must also have a non-trivial current overlap-adjusted sample floor before being treated as a stronger watch state.
- Current floor qualification threshold is `max(3, ceil(min_points*0.25))`; with `min_points=30`, threshold is 8.
- Latest trade-core Polymarket artifact sha256 `c64314139cac2349fdb1983de593a20c58fcac5813b0511d56c4ad4ae3ea65f5`, created `2026-06-20T17:17:02.986979+00:00`: `INSUFFICIENT_SAMPLE`, sample=19/30, remaining=11.
- Persistence status is `LOW_SAMPLE_RECURRING_PRE_GATE_WATCHLIST`: recurring=5, persistent=5, floor-qualified recurring=0, floor-qualified persistent=0.
- Top recurring cells are 240m with current sample floor 1 (`other|BTCUSDT|240`, `other|SOLUSDT|240`, `price_target|XRPUSDT|240`), so this is still a wait-for-sample state, not candidate/probe authority.
- Latest alpha-discovery artifact sha256 `76d8778a1964faaa93dcd81060ecc7afcbb3dcf08e52fbfeb269b9d166f319b8` preserves the same blocker and remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, ready/probe=0.
- Verification: Mac and Linux focused suite `78 passed`; py_compile, bash syntax, and diff-check passed.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG write, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Alpha Profitability Blocker Scorecard

- Added `profitability_blocker_scorecard` to alpha-discovery plans/runtime artifacts and mirrored it at top-level in `alpha_discovery_latest.json`.
- Purpose: make the no-profit state explicit across all arms instead of only counting `READY/RUN_CAPTURE/WAIT/BLOCK`.
- Taxonomy now separates ready states from blockers: `candidate_review_ready`, `probe_ready`, `feature_family_no_edge`, `cost_wall`, `fee_or_scale`, `sample_gate`, `data_coverage`, `event_wait`, `robustness_wait`, `rejected_no_edge`, `source_health`.
- `runtime_runner.py` now passes MM `fee_path_feasibility` into arm detail, so MM can show signal-family failure as primary and fee/capital path as secondary.
- Latest trade-core alpha-discovery artifact sha256 `64a04a70f674042a426c7f31f584a0f15345e773dfc6c9caab2ff515d781a869`, created `2026-06-20T17:02:16.424355+00:00`: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, ready/probe=0.
- Blocker counts: `feature_family_no_edge=1`, `sample_gate=1`, `data_coverage=1`, `event_wait=2`, `robustness_wait=1`, `rejected_no_edge=1`.
- Top blocker: MM `no_train_positive_walk_forward_feature_cell`, sample=16; secondary blockers include current fee shortfall `0.0357bp` and VIP5 scale-gated lower-fee path (`break_even_maker_fee=1.135bp/side`).
- Other active blockers: Polymarket 18/30 sample gate ETA `2026-06-20T19:52:03.067000+00:00`; FlashDip L1 `candidate_window_before_symbol_l1_range`; FlashDip buy no-touch; Gate-B `WATCH_ONLY`; AEG no durable rows; vol-event `NO_EDGE_SURVIVES`.
- Verification: Mac and Linux focused suite `49 passed`; py_compile and diff-check passed on both; manual Linux artifact-only cron refreshed latest JSON.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact write only; no PG write, Bybit private/signed/trading call, engine/API restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 MM Walk-Forward Failure Summary

- Added `walk_forward_feature_scorecard.failure_summary` and passed it through alpha-discovery MM detail as `walk_forward_failure_summary`.
- Diagnosis: determine whether current MM remains unprofitable because the existing PIT spread/queue/OFI/BTC-lead feature family hides a near-ready train/holdout filter.
- Latest trade-core forced fresh-L1 2h fill_sim report sha256 `b9bdeba681d6182de8eda32031e81320e6f628893aa65c5a645d334aa524a9ca`: `l1_rows_post_filter=1756794`, `trades_rows=1602324`, 33 symbols, L1 age `0.003h`.
- `walk_forward_feature_scorecard.status=NO_WALK_FORWARD_FEATURE_TRAIN_POSITIVE`; `failure_summary.status=NO_TRAIN_POSITIVE_CELL`; candidates=51, train sample-gated positives=0, holdout confirmations=0.
- Best train combo `quoted_half_spread_bps train_p75 AND side_book_imb train_p75` remains negative: train `-3.524bp`, holdout `-3.260bp`; best holdout candidate `symbol == ADAUSDT` remains `-1.998bp`.
- Same report remains current-fee negative across edge/horizon/conditional scorecards; fee sensitivity best break-even maker fee improved to `1.135bp/side` but is still below current `2.0bp/side`.
- MM verdict status line sha256 `d8c43bde35ff8f11e622734dcb5b939b82ef155c2e6e84dffe323f2a26f9da87` and alpha latest sha256 `3a834cad9e3ba3abbdc72014fab4b09dc2647046cfa232379a3d4f3172e787b3` preserve the summary; MM arm remains `CAPTURING`, ready/probe=0.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 MM FillSim Horizon Scorecard

- Added diagnostic-only `fill_sim_horizon_scorecard(report)` and passed it through `recorder_mm_verdict_cron.sh` plus alpha-discovery MM arm detail.
- Diagnosis: test whether the MM cost wall is only a 15s adverse-selection horizon artifact.
- Latest trade-core forced fresh-L1 2h fill_sim report sha256 `bbc92040206c2f50fe3d9fa6556d1aa6737b4c316cb45d6f935220fa06c36647`: `l1_rows_post_filter=1749143`, `trades_rows=1562327`, 33 symbols, L1 age `0.003h`.
- `horizon_scorecard.status=NO_HORIZON_POSITIVE_CELL`, horizons `[5,15,30]`, cells evaluated 222; best cell `ADAUSDT` / `informed_skip` / `back` / 5s has `n=926`, `net_bps=-2.444`.
- Best by horizon stays negative: 5s `-2.444bp`, 15s `-2.588bp`, 30s `-2.485bp`; sample-gated positives zero.
- Same report: current-fee `edge_scorecard` and conditional/walk-forward scorecards remain negative; fee sensitivity still says lower-fee/rebate path can become positive, with best break-even maker fee now `0.706bp/side`.
- MM verdict status sha256 `82fc3dd6cd55aa0065cea20f35848526a9f92e11a30eff93363438753355a4c7` and alpha discovery latest sha256 `f6915d61bbdf2a9067655b5134f35c46e59dc610d6936601d69c1481d402abee` both preserve the horizon scorecard; alpha MM arm remains `CAPTURING`, ready/probe=0.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Partial IC Control

- Upgraded `polymarket_leadlag` to report schema/runner v0.12.
- Diagnosis: v0.11 could flag odds deltas that correlate more with past return than forward return; v0.12 now measures remaining forward information after residualizing forward return against trailing return.
- IC rows now expose `partial_ic_controlling_trailing_return`, `partial_ic_t_stat`, `partial_ic_abs_margin_vs_raw`, `partial_ic_retained_abs_ratio`, `trailing_forward_return_ic_pearson`, and `price_feedback_partial_collapse_warning`; status/runtime detail expose `price_feedback_partial_collapse_count`.
- Linux v0.12 wrapper smoke latest sha256 `ab2620e8edc223583b63bcbc00de94c979fcfb45288dc4513845dd9331fd5322`: `snapshot_rows=14727`, `delta_rows=16453`, `feature_points=236`, `joined_rows=414`, `max_overlap_adjusted_ic_points=15`, `candidate_count=0`, still `INSUFFICIENT_SAMPLE`, ETA `2026-06-20T19:52:01.632Z`.
- Partial-control summary: `cells_with_control=46`, `partial_control_cells=29`, `raw_to_partial_collapse_count=4`, `max_abs_partial_ic_controlling_trailing_return=0.726`.
- Example: `price_target|XRPUSDT|15m` raw IC≈0.306 collapses to partial IC≈0.095 after trailing-return control, so raw Polymarket IC is not enough for candidate review.
- Alpha discovery latest sha256 `1a78a867e9912fe7a70ec51032f95e1cbd0f3d37dc288e0c98e82d838ee322e0` reports `polymarket_leadlag_ic.sample_count=15`, `price_feedback_partial_collapse_count=4`, action `RUN_READ_ONLY_CAPTURE`, ready/probe=0.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Price-Feedback IC Control

- Upgraded `polymarket_leadlag` to report schema/runner v0.11.
- Diagnosis: before treating any Polymarket lead-lag IC as actionable, we need to know whether odds deltas lead future perp returns or merely react to already-realized price moves.
- v0.11 keeps the existing leak-free forward label path and adds same-horizon trailing-return controls using price points at/before `t-h` and `t`; the control is diagnostic-only and does not relax candidate gates.
- IC rows now expose `past_return_control_n_points`, `past_return_ic_pearson`, `lead_lag_abs_ic_margin`, and `price_feedback_warning`; status/runtime detail expose `price_feedback_warning_count` and `price_feedback_summary`.
- Linux v0.11 wrapper smoke latest sha256 `bf22fe98f4d391616a0d86552828618efb486cf97e44193a21016286627b9483`: `snapshot_rows=13859`, `delta_rows=15418`, `feature_points=222`, `joined_rows=371`, `max_overlap_adjusted_ic_points=14`, `candidate_count=0`, still `INSUFFICIENT_SAMPLE`, ETA `2026-06-20T19:52:01.378Z`.
- Price-feedback summary: `cells_with_control=32`, `warning_count=22`, `max_abs_past_return_ic=1.0`; top warnings are `price_target` BTC/ETH/XRP 15m/60m cells where past-return IC dominates forward IC.
- Alpha discovery latest sha256 `41cdcad77a2897a28b57a73cba780c473f73306de784edbbcdac139699feaebe` reports `polymarket_leadlag_ic.sample_count=14`, `price_feedback_warning_count=22`, action `RUN_READ_ONLY_CAPTURE`, ready/probe=0.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Source-Split IC View

- Upgraded `polymarket_leadlag` to report schema/runner v0.10.
- Diagnosis: v0.9 correctly recovered macro/regulatory rows, but aggregate `event_reg` cells mixed direct asset events with generic macro/reg proxy rows, leaving two hypotheses collapsed into one IC cell.
- v0.10 preserves aggregate `event_reg` cells and adds `event_reg_direct` / `event_reg_macro` source-split cells, with `bucket_view`, `base_bucket`, `symbol_source`, and `symbol_source_breakdown` on feature rows.
- Report/status/runtime detail now expose `feature_bucket_counts`, `feature_bucket_view_counts`, and `feature_source_counts`; candidate gates remain unchanged.
- Linux v0.10 wrapper smoke latest sha256 `1f85dfb82789d3fd158272b8def4c0762755907e4ffbef7643243ba19e03b53f`: `snapshot_rows=13001`, `delta_rows=14393`, `feature_points=208`, `joined_rows=341`, `event_reg_direct=40`, `event_reg_macro=28`, `max_overlap_adjusted_ic_points=13`, `candidate_count=0`, still `INSUFFICIENT_SAMPLE`, ETA `2026-06-20T19:52:02.188Z`.
- Alpha discovery latest sha256 `d609117f2c4f44c91643e27cddaddbca37c219c44413fd04c3c1a9f08d6beaf8` reports `polymarket_leadlag_ic.sample_count=13`, split counts in detail, action `RUN_READ_ONLY_CAPTURE`, ready/probe=0.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Macro-Reg Proxy

- Upgraded `polymarket_leadlag` to report schema/runner v0.9.
- Diagnosis: a same-data alt-alias probe found `alias_clue_counts=[]`, so blind expansion to ADA/DOGE/BNB/LTC/etc. was rejected.
- The current unmapped pool before macro proxy had 5406 rows: `event_reg=3878`, `price_target=989`, `other=539`; top event/reg sources were CPI, inflation, Tether/USDT, Coinbase SEC, spot ETF, Fed/rate/regulation queries.
- v0.9 maps only unmapped `event_reg` rows to BTC/ETH `macro_event_reg` proxy series after direct BTC/ETH/SOL/XRP inference fails; direct asset rows still win, and `price_target`/`other` stay unmapped with diagnostics.
- Same-snapshot effect: delta rows `6184 -> 13380`, unmapped rows `5406 -> 1528`, mapped snapshot-source counts `asset_direct=6733`, `macro_event_reg=7756`; feature points / joined rows / adjusted sample floor stayed `130 / 210 / 12`.
- Linux v0.9 wrapper smoke latest sha256 `3c522bc98f73e9f20153d97dfa7a3f1db09e9fd23c585f3f405447545b7fad5d`: `snapshot_rows=12153`, `delta_rows=13380`, `joined_rows=210`, `max_overlap_adjusted_ic_points=12`, `candidate_count=0`, still `INSUFFICIENT_SAMPLE`, ETA `2026-06-20T19:52:03.743Z`.
- Alpha discovery latest sha256 `de0a74a9faf55bb8f66cbe9db3e978376494dc3effc09b63e077a130b25d905b` reports `polymarket_leadlag_ic.sample_count=12`, action `RUN_READ_ONLY_CAPTURE`, ready/probe=0.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Wide-Symbol Universe

- Upgraded `polymarket_leadlag` to report schema/runner v0.8 and widened defaults from BTC/ETH to BTC/ETH/SOL/XRP in the harness, cron wrapper, and installer env.
- Same-data isolated comparison separated the effect from sample maturation: BTC/ETH baseline sha256 `a042a4f8ac78cc6f9da7228801fc85e1e6e653170d9d266c1dd545b3b42092a0` had `snapshot_rows=11285`, `delta_rows=4643`, `joined_rows=114`; wide-symbol sha256 `7c9b2a7443af8d3f9f5dceceba83d4b18c49ff4218171f869b9aa2ed10647a55` had the same `snapshot_rows=11285` but `delta_rows=5715`, `joined_rows=190`.
- Linux v0.8 wrapper smoke latest sha256 `350a689a62ce688a1b1d3bd226f43165fbe9bddc2bc2a0a7f73cae124cd9b5a9`: symbols BTC/ETH/SOL/XRP, adjusted sample_count=11/30, gap=19, ETA `2026-06-20T19:52:01.390Z`, still `INSUFFICIENT_SAMPLE`.
- New best diagnostic-only pre-gate watch is `event_reg|XRPUSDT|60m`, floor 2 / gap 28, IC≈-0.616, HAC t≈-5.002, q≈1.02e-5; this is not candidate/probe/promotion authority.
- Alpha discovery latest sha256 `3ade420bc5c20aa671d0a7772d79875446ae937fc3c71c80f03c407804f4d3d3` preserves symbols/watchlist while keeping action `RUN_READ_ONLY_CAPTURE`, artifacts_ready=false, ready/probe=0.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Sample-Gate Clock

- Upgraded `polymarket_leadlag` to report schema/runner v0.7.
- Reports now include `counts.sample_gate_clock`; cron status and alpha discovery pass through `sample_gate_status`, `sample_gate_eta_utc`, and compact `sample_gate_clock`.
- Linux v0.7 smoke latest sha256 `0eb7c4bdea86f60810f4824d3a0c201b7cbcea67c5077be9ea36a9b8a86c21f2`: sample_count=10/30, gap=20, ETA `2026-06-20T19:52:03.862Z`, still `INSUFFICIENT_SAMPLE`.
- Key diagnosis: the v269 pre-gate watch did not persist after the 10th adjusted sample; watchlist_count=0 and `other|BTCUSDT|15m` decayed to IC≈0.1286 / HAC t≈0.401 / q≈0.765.
- Alpha discovery latest sha256 `682c1a278cc9384ccde3680d0ea1024e2b973185728d9befbf5546ec81bfcc4c` preserves the ETA while keeping action `RUN_READ_ONLY_CAPTURE`, artifacts_ready=false, ready/probe=0.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Pre-Gate HAC Watchlist

- Upgraded `polymarket_leadlag` to report schema/runner v0.6.
- Reports now include diagnostic-only `pre_gate_hac_watchlist` for HAC/BH-significant cells blocked by `sample_floor_below_min_points`; this is not candidate/probe/promotion authority.
- Cron status and alpha discovery raw detail pass through `pre_gate_hac_watchlist_count`, `best_pre_gate_hac_watch`, and `min_samples_remaining_to_gate`.
- Linux v0.6 smoke latest sha256 `864151680dc2787a79a387d7316faedb81568dc569ca2561ef1b38c723621213`: `max_overlap_adjusted_ic_points=9`, `min_samples_remaining_to_gate=21`, `pre_gate_hac_watchlist_count=5`, best watch `other|BTCUSDT|15m`, `candidate_count=0`, still `INSUFFICIENT_SAMPLE`.
- Alpha discovery latest sha256 `acaa77cab2660c65e57b092fe13a71966f0c8bd135d14c8ebf7e247603427e13` preserves the best watch while keeping action `RUN_READ_ONLY_CAPTURE`, artifacts_ready=false, ready/probe=0.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Jitter-Tolerant Sample Floor

- Upgraded `polymarket_leadlag` to report schema/runner v0.5.
- Overlap-adjusted sample counting and HAC lag now share a 5s schedule-jitter tolerance; IC rows expose `overlap_jitter_tolerance_ms`.
- This fixes evidence velocity under the installed 15m cron cadence without lowering `min_points` or candidate thresholds.
- Linux v0.5 smoke wrote latest sha256 `8756b1c5758634f283de79fc83014cd12b290c3fd0c79669c6bbef8f2b7d2136`; `max_ic_points=9`, `max_overlap_adjusted_ic_points=9`, `candidate_count=0`, still `INSUFFICIENT_SAMPLE`.
- Alpha discovery latest sha256 `0c3f6fbd893719888d6b29dd4ddc1ee59366855d4d9343dba90a8d78bbf60532` reports `polymarket_leadlag_ic.sample_count=9`, action `RUN_READ_ONLY_CAPTURE`, ready/probe=0.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket HAC IC Gate

- Upgraded `polymarket_leadlag` to report schema/runner v0.4 with Newey-West/HAC slope t-stat significance.
- Candidate review now requires overlap-adjusted sample floor, HAC t threshold, and BH q-value control; naive t-stat/p/q remain diagnostic only.
- Cron status and alpha discovery raw detail now expose `preliminary_hac_candidate_count`, `significance_t_stat=t_stat_hac`, and `max_abs_t_stat_hac`.
- Linux v0.4 smoke wrote latest sha256 `9e4941dc399f5f6c2c08076814d06f3ed78b6084d383689f66800083c80a5601`; `max_ic_points=2`, `max_overlap_adjusted_ic_points=2`, `preliminary_hac_candidate_count=0`, still `INSUFFICIENT_SAMPLE`.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Robust IC Gate

- Upgraded `polymarket_leadlag` to report schema/runner v0.3 with overlap-adjusted sampling and BH q-value controls.
- IC rows now expose `n_nonoverlap_timestamps`, `overlap_adjusted_sample_floor`, `overlap_warning`, approximate p-values, and `bh_q_value_approx`.
- `verdict.candidate_count` is now controlled-candidate count after raw IC/t thresholds plus `max_bh_q`; `preliminary_raw_candidate_count` preserves raw pass count.
- Alpha discovery now uses `counts.max_overlap_adjusted_ic_points` for `polymarket_leadlag_ic.sample_count`, with raw `max_ic_points` preserved in detail.
- Linux v0.3 smoke wrote `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T124843Z.json`; sha256 `5cd5dde22b7bfd6d31339aca739db3126982ac5b3130d23da3478b2ed56d6de5`; `max_ic_points=1`, `max_overlap_adjusted_ic_points=1`, still `INSUFFICIENT_SAMPLE`.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket 15m Evidence Cadence

- Manual lead-lag wrapper after first label maturity wrote `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T122433Z.json`; sha256 `cfc12bd3519a18eaa3dc03a7ea690f61d0e2cb695087a2c4f33cb4c110951111`.
- The lane is now producing joined labels: 397 deltas, 6 feature points, 6 joined rows, 6 joinable label pairs, max IC points per cell 1; still `INSUFFICIENT_SAMPLE`.
- Added default-preserving minute-list controls to the Polymarket collector and lead-lag installers, then installed Linux artifact-only cadence: collector `7,22,37,52 * * * *`, lead-lag IC `2,17,32,47 * * * *`.
- Natural 12:32 UTC lead-lag cron fire wrote `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T123201Z.json`; sha256 `4616b4dbe306035ce967b299b5c3afa6b37de4b0929885a1e2c5e6a57a0b401b`.
- Natural 12:37 UTC collector fire wrote `/tmp/openclaw/polymarket_axis_runs/hourly-topn-20260620T123716Z`: 884 snapshot rows, 107 events, 30 HTTP requests, `errors=[]`.
- Alpha discovery refresh `2026-06-20T12:24:46Z` shows `polymarket_leadlag_ic.sample_count=1`, action `RUN_READ_ONLY_CAPTURE`, ready/probe=0.
- Boundary: user crontab + `/tmp/openclaw` artifact/log/heartbeat writes only; no engine/API restart, PG table write, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, or promotion proof.

## 2026-06-20 Polymarket Label-Readiness Diagnostics

- Upgraded `polymarket_leadlag` report schema/runner to v0.2 with `counts.label_readiness`, so the IC loop distinguishes "forward label not mature yet" from collector/price-source failure.
- Cron status JSONL and alpha-discovery raw detail now expose `label_feature_horizon_pairs`, `label_joinable_pairs`, `label_status_counts`, and `oldest_unmatured_exit_target_utc`.
- Linux smoke after the 12:07 collector wrote `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T121515Z.json`; sha256 `43f189ca875ecdb3dddded925e936eda51b98fe5a5396b1e75d7b86452ee1b8a`; 397 deltas, 6 feature points, 0 joined rows.
- Read: all 18 feature×horizon pairs are `exit_target_after_latest_price`, with first target around `2026-06-20T12:22:01Z`. The Polymarket lane is producing real deltas; labels simply have not matured yet.
- Boundary: artifact/report/status only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Lead-Lag IC Cron + Killboard

- Added `helper_scripts/cron/polymarket_leadlag_ic_cron.sh` and installer, then installed Linux runtime cron at `17 * * * *`, after the active Polymarket v2 hourly collector at minute 7.
- Wrapper stays artifact-only and read-only: env-file PG creds, `PGOPTIONS=-c default_transaction_read_only=on`, dated/latest report writes, status JSONL, heartbeat, stale lock, fail-soft exit.
- Alpha discovery now includes arm `polymarket_leadlag_ic`; sample_count is max IC points per cell, not aggregate joined rows, so insufficient per-cell samples keep collecting.
- Linux smoke wrote `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T120018Z.json` plus latest; sha256 `15d68093c1e618ae9bfb234b072b6e4a5d3113c28b799e9d1af9913f46b3fab6`; verdict `INSUFFICIENT_SAMPLE` with 860 snapshot rows, 1 distinct v2 timestamp, 0 delta/joined rows, 64 price rows, min_points 30.
- Alpha discovery refresh `2026-06-20T12:00:33Z` shows Polymarket action `RUN_READ_ONLY_CAPTURE`, sample_count 0, ready/probe 0.
- Boundary: source/test/docs + selective Linux source sync + user crontab + `/tmp/openclaw` artifact/log/heartbeat writes only; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Lead-Lag IC Harness

- Added `helper_scripts/research/polymarket_leadlag/` as the fail-closed IC loop for active Polymarket v2 hourly data.
- Method: Polymarket PIT snapshot probability deltas -> research-side `price_target` / `event_reg` / `other` buckets -> Bybit perp forward returns from first 1m kline at/after snapshot and horizon.
- Local and Linux focused verification passed: `test_polymarket_leadlag.py` 4/4, py_compile, diff-check.
- Linux runtime smoke wrote `/tmp/openclaw/research/polymarket_leadlag/polymarket_leadlag_20260620T114427Z.json` plus latest; verdict `INSUFFICIENT_SAMPLE` with 860 snapshot rows, 1 distinct v2 timestamp, 0 delta/joined rows, 32 price rows.
- PM read: this is expected and useful. We now have the IC harness, but not enough hourly v2 points. Wait for >=20-30 hourly timestamps, rerun, then only treat candidates as review input after residual/regime/HAC/multiple-testing controls.
- Boundary: artifact/report only; PG path readonly SELECT `market.klines`; no PG writes, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Query-Set V2 Runtime Activation

- Added Polymarket query-set v2 for event/regulatory discovery while keeping v1 immutable and default-compatible.
- Runtime `trade-core` now has daily `41 4 * * *` and active hourly `7 * * * *` Polymarket cron entries carrying `OPENCLAW_POLYMARKET_QUERY_SET=v2`; backup before reinstall: `/tmp/openclaw/cron_backups/crontab_before_polymarket_query_set_v2_20260620T113342Z.txt`.
- Manual v2 smoke artifact `/tmp/openclaw/polymarket_axis_runs/hourly-topn-20260620T113312Z` produced 107 events, 860 snapshot rows, 30 HTTP requests, 24 keyword terms, `errors=[]`, `point_in_time=true`, `query_set_version=v2`.
- Tests passed locally and on Linux: Polymarket research + cron static suite `65 passed, 1 skipped`, plus py_compile for the four package modules and `bash -n` for both cron scripts.
- PM read: v2 changes discovery, not row filtering. Price-target markets remain in raw artifacts by design; lead-lag IC must bucket price-target vs event/reg markets research-side before any alpha ruling.
- Boundary: source/test/docs + selective Linux source sync + user crontab + `/tmp/openclaw` artifact/log/heartbeat writes only; no secrets, PG, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 Polymarket Hourly Top-N Activation

- Activated Linux `trade-core` Polymarket `hourly-topn` cron as artifact-only data collection: daily remains `41 4 * * *`; hourly top-50 is active at `7 * * * *`.
- Manual smoke artifact `/tmp/openclaw/polymarket_axis_runs/hourly-topn-20260620T111919Z` produced 50 events, 525 snapshot rows, 1 HTTP request, `errors=[]`, `point_in_time=true`, `query_set_version=v1`.
- Local tests passed 59/60 with 1 opt-in skip plus both cron scripts `bash -n`; crontab backup before activation is `/tmp/openclaw/cron_backups/crontab_before_polymarket_hourly_20260620T112015Z.txt`.
- PM read: this unblocks the time-series data requirement for Polymarket lead-lag IC, but Polymarket remains corroborating context only. Wait for 20-30 hourly points, then run leak-free forward IC with BTC/ETH residuals, regime slice, HAC, and multiple-testing correction before QC/MIT/AI-E ruling.
- Boundary: user crontab + `/tmp/openclaw` artifact/log/heartbeat writes + docs only; no secrets, PG, Bybit private/signed/trading call, engine restart, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 FlashDip L1 Timing Relation Diagnostics

- Added v0.2 timing diagnostics to `shallow_retune_l1_short_exit_replay.py`: missing event windows now record whether they are before, after, or inside the symbol's loaded L1 range, plus gap hours and symbol L1 first/last timestamps.
- `flash_dip_l1_short_exit_replay_cron.sh` and alpha-discovery `runtime_runner.py` now preserve `event_window_l1_relation_counts` and `dominant_missing_event_window_l1_relation`.
- Linux read-only replay latest sha256 `43992d40987e61a737b109721b4f079347bddb382fa71c69631cae3a19c75afd`: 6 candidate events / 2 days / 5 symbols, 173,749 L1 rows, 2,757,781 trades, 0/6 event windows covered, all 6 `candidate_window_before_symbol_l1_range`.
- Loaded L1 range for the replay is `2026-06-20T00:18:11.624Z`..`03:59:59.804Z`; the 2026-06-18 candidate windows ended ~24.3h before L1, and the 2026-06-19 windows ended ~18.2m before L1.
- PM read: FlashDip 240m short-exit remains data-timing gated after L1 recorder repair; not disproven by queue/fill realism and not promotion proof.

## 2026-06-20 MM FillSim Daily History Cadence

- Changed fill_sim refresh default `OPENCLAW_FILL_SIM_MAX_AGE_H` from 60h to 18h so the installed daily 06:05 UTC cron can accumulate cross-window history daily-ish instead of every ~2.5 days.
- This is evidence-velocity only, not promotion proof; v257 fresh-L1 report remains the latest production fill_sim artifact and MM still needs repeated current-fee or holdout-confirmed positives.
- Boundary: source/test/docs + selective Linux source sync only; no rebuild/restart, DB write, Bybit call, or auth/risk/order/strategy mutation.

## 2026-06-20 MM FillSim Wall-Clock Freshness Gate

- Fixed fill_sim/MM verdict false-freshness: both cron wrappers now recompute L1 data age from `l1_max_ts` against wall clock; missing/bad `l1_max_ts` fail-closes.
- Linux selective sync + checks passed; bounded forced 2h refresh replaced production fill_sim report with fresh L1 (`l1_rows_post_filter=1,022,579`, `l1_max_age_hours=0.002`, sha256 `7ff1f9cbccfb97f43a0bc1abc70ee7eb8c656ebed7ed7da95f278a00847727a8`) and history scorecard now has one valid window.
- Fresh evidence still does not promote MM: fill_sim maker net@15 is -4.086bp, edge scorecard has no current-fee positive, walk-forward has no train-positive feature, and live-markout ARBUSDT positive is n=1 below gate.
- Boundary: source/test/docs + selective runtime source sync + `/tmp/openclaw` artifact/log writes only; no rebuild/restart, DB write, Bybit call, or auth/risk/order/strategy mutation.

## 2026-06-20 MM FillSim History Runtime Sync

- Selectively synced v255 runtime files to Linux `trade-core` while leaving unrelated dirty docs untouched; full Linux git three-way sync is not claimed.
- Linux target code files now match `origin/main`: `fill_sim.py`, `fee_path.py`, `fill_sim_history.py`, fill_sim/MM cron wrappers, focused tests, and microstructure `__init__.py`.
- Linux canonical focused validation passed 34 tests plus py_compile and both cron `bash -n`.
- Initialized `/tmp/openclaw/research/fillsim/fillsim_history_scorecard.json` as `NO_HISTORY_REPORTS 0 0`; manual read-only MM verdict confirmed `fillsim.history_scorecard.present=true/status=NO_HISTORY_REPORTS`.
- Boundary: selective source rsync + `/tmp/openclaw` artifact/log writes + read-only PG verdict only; no rebuild/restart, DB table write, Bybit call, strategy/auth/risk/order mutation, or promotion proof.

## 2026-06-20 MM FillSim History Scorecard

- Added report-only `fill_sim_history.py` to aggregate multiple fill_sim JSON artifacts into longer-regime evidence: valid windows/dates, current-fee sample-gated positive repeats, walk-forward holdout confirmations, and best break-even fee.
- `fill_sim_refresh_cron.sh` now archives every valid candidate under `<DATA>/research/fillsim/history/` and refreshes `fillsim_history_scorecard.json`; `recorder_mm_verdict_cron.sh` preserves that under `fillsim.history_scorecard`.
- Verification: Mac focused tests 31 passed plus py_compile/bash syntax/diff-check/CLI smoke; Linux validation used `/tmp/openclaw_v255_validate` because canonical trade-core checkout was behind/dirty, and passed the same 31 focused tests plus py_compile/bash syntax/CLI smoke.
- Read: this does not create a promoted edge. It converts the v254 "need longer regime coverage" conclusion into durable evidence accumulation.
- Boundary: source/test/docs + Linux `/tmp` validation only; no canonical Linux checkout mutation, production report replacement, rebuild/restart, DB write, Bybit call, or trading/auth/risk mutation.

## 2026-06-20 MM FillSim Maker Fee Sensitivity

- Added `maker_fee_sensitivity_scorecard` to fill_sim and passthrough under `recorder_mm_verdict_cron.sh` status.
- Linux isolated read-only smoke `/tmp/openclaw/research/fillsim/fillsim_fee_sensitivity_smoke_20260620T093904Z.json` sha256 `33020cceaff59b47ae121dc270c7602c3a4540958eff497ac24975387ef9b5f2`: 15m fresh L1, 144,418 L1 rows, 88,555 trades, 34 symbols.
- Current 2.0bp/side maker fee still has `positive_sample_gate_count=0`; best current positive is BTWUSDT but n=18 below gate.
- At 1.0bp/side one sample-gated cell turns barely positive: `quoted_half_spread_p75 AND side_book_imb_p75`, n_fill_only=116, edge_before_fees=2.057bp, break-even maker fee=1.028bp/side, net@1bp=+0.057bp.
- Read: maker profitability is fee-sensitive but not promoted. Actual path needs fee <=~1.03bp/side plus cross-regime CP-3 evidence, or a stronger signal.
- Boundary: source/test/docs + selective sync + isolated read-only PG/artifact/status runs only; no production fill_sim replacement, rebuild/restart, DB write, Bybit private call, or auth/risk/order/trading mutation.

## 2026-06-20 MM FillSim PIT Conditional Feature Scorecard

- Added placement-time `conditional_feature_scorecard` to fill_sim and passthrough under `recorder_mm_verdict_cron.sh` status.
- Linux isolated read-only smoke `/tmp/openclaw/research/fillsim/fillsim_conditional_feature_smoke_20260620T092837Z.json` sha256 `3da43e8d295322727edcfe121716cd3e5520a1337fcea625e572696806208096`: 15m fresh L1, 139,675 L1 rows, 76,124 trades, 34 symbols.
- Result: `NO_CONDITIONAL_FEATURE_POSITIVE_CELL`; 30 PIT cells evaluated; best `quoted_half_spread_p75 AND side_book_imb_p75`, n_fill_only=116, net -3.184bp after 4bp maker RT fee.
- Isolated MM verdict wrapper smoke confirmed passthrough and live-markout cost wall still below gate: ARBUSDT best net -0.2197bp with `best_n_maker_fills=1`.
- Read: simple PIT spread/imbalance/OFI filters do not yet clear the maker cost wall. Next work needs wider-spread/regime/fee-rebate evidence or a materially new signal, not MM promotion.
- Boundary: source/test/docs + selective sync + isolated read-only PG/artifact/status runs only; no production fill_sim replacement, rebuild/restart, DB write, Bybit private call, or auth/risk/order/trading mutation.

## 2026-06-20 MM FillSim Skip-Quantile Sweep

- Ran isolated Linux read-only fill-sim scorecard sweep over `skip_quantile=0.00/0.10/0.20/0.30`; artifacts only under `/tmp/openclaw/research/fillsim/fillsim_scorecard_q*.json`.
- Results: q0.00 best BSBUSDT n=35 net -1.480bp; q0.10 best ADAUSDT n=125 net -1.276bp; q0.20 best ADAUSDT n=109 net -1.214bp.
- q0.30 produced BEATUSDT net +17.364bp but n=2, status `POSITIVE_FILL_ONLY_CELL_BELOW_SAMPLE_GATE`; all q values have `positive_sample_gate_count=0`.
- Read: existing informed-skip filter is not enough; aggressive skipping creates tiny-n positives only. No MM promotion or implementation authority.
- Boundary: isolated read-only PG/artifact run only; no source change, production fill_sim replacement, rebuild/restart, DB write, Bybit private call, or auth/risk/order/trading mutation.

## 2026-06-20 MM FillSim Edge Scorecard

- Added `edge_scorecard` to fill_sim: compact ranking over fill_only maker-edge cells across pooled/per-symbol, naive/informed-skip, and queue-dose views.
- `recorder_mm_verdict_cron.sh` now passes `fillsim.edge_scorecard` through status and includes `best_n_maker_fills` in `cost_wall_summary`.
- Isolated Linux read-only smoke artifact `/tmp/openclaw/research/fillsim/fillsim_scorecard_smoke_20260620T090830Z.json`: 15m fresh L1, 142,881 L1 rows, 86,471 trades, 34 symbols.
- Result: `NO_POSITIVE_FILL_ONLY_CELL`; best fill-sim cell is ADAUSDT back-of-queue informed-skip fill_only, n=121, net -1.082bp after 4bp maker RT fee.
- Isolated MM verdict smoke using that report: live-markout best ARBUSDT net +0.1213bp but `best_n_maker_fills=1`, below 30-fill gate.
- Boundary: source/test/docs + selective sync + isolated read-only PG/artifact/status runs only; no production fill_sim replacement, rebuild/restart, DB write, Bybit private call, or auth/risk/order/trading mutation.

## 2026-06-20 FlashDip L1 Event-Window Coverage

- Promoted the L1 replay status into independent alpha-discovery arm `flash_dip_l1_short_exit_replay`; conditional-pass with >=30 measured exits is required before `READY_FOR_AEG_CHAIN`, stale/blocked status becomes BLOCK.
- Added event-window L1 coverage diagnostics so broad symbol-level L1 rows no longer mask missing L1 inside each candidate maker window.
- Linux read-only smoke latest sha256 `417a4ee7b76191e1e8e2a3ac9a2285bc9fbd47558aabe8ae185115db0bf79c18`: 6 candidate events / 2 days / 5 symbols, 173,749 loaded L1 rows and 2,757,781 trades, but `events_with_l1_in_event_window=0` / `events_missing_l1_in_event_window=6`.
- Alpha discovery now shows action `RUN_READ_ONLY_CAPTURE`, rank 2, reason `sample_count_below_gate`; the short-exit thesis is still data-gated, not queue-realism disproven.
- Boundary: source/test/docs + selective helper/test sync + Linux read-only PG/artifact/status run only; no rebuild/restart, DB write, Bybit private call, or auth/risk/order/trading mutation.

## 2026-06-20 FlashDip L1 Short-Exit Replay Cron

- Added and Linux-installed read-only `flash_dip_l1_short_exit_replay_cron.sh` at `31 6 * * *`; it writes dated/latest replay artifacts plus `logs/flash_dip_l1_short_exit_replay.log`.
- Alpha discovery now exposes the latest L1 replay status under `flash_dip_buy_demo.detail.l1_short_exit_replay`, but does not use it as promotion readiness.
- Linux smoke latest sha256 `67670804402a58eee6f02e2dd1e3da590d7bfc806ebca5dbc71744688e3f48ee`; verdict remains data-gated: 0 L1 rows / 608,227 trade rows for the current APT/ATOM/AVAX candidate window.
- Boundary: source/test/docs + selective sync + read-only PG artifact + user-cron install only; no rebuild/restart, DB write, Bybit private call, or auth/risk/order/trading mutation.

## 2026-06-20 FlashDip L1 Short-Exit Replay

- Added read-only `shallow_retune_l1_short_exit_replay.py` for the v245 K6/N2/C3/nf0.5% 240m short-exit research signal, with queue-fill/adverse-through modeling against `market.l1_events` + `market.trades`.
- Linux artifact `shallow_retune_l1_short_exit_replay_20260620T023713Z.json` sha256 `231d3c57ae8f8945e114a77b8e5b0f8688149ffae738e72c5c31b2ac47631be2` returned `L1_SHORT_EXIT_INSUFFICIENT_SAMPLE`: 3 APT/ATOM/AVAX candidate events had 608,227 trade rows but 0 L1 rows in the candidate window.
- PM read: 2-day K6 retune remains blocked; 240m short-exit is not disproven, but is data-gated until future/instrumented K6 candidate windows have continuous L1 coverage.
- Boundary: source/test/docs + selective Linux helper/test sync + read-only PG artifact only; no rebuild/restart, DB write, Bybit private call, or auth/risk/order/trading mutation.

## 2026-06-20 FlashDip Touchability Monitor

- Added a read-only FlashDip touchability monitor that joins `trading.orders` to `trading.intents` and checks 1m lows from order_ts to maker timeout against `details.limit_price`.
- Linux isolated smoke showed `order_labeled_count=19`, `true_order_count=18`, `strategy_mismatch_count=1`, `touched_count=0`, `touch_rate_pct=0.0`, median closest miss `1595.84bp`.
- Selective Linux deploy installed hourly cron at minute 17 and manual production run wrote `/tmp/openclaw/logs/flash_dip_touchability.log`; alpha discovery manual refresh showed FlashDip `CAPTURING_NO_TOUCH`.
- K-ladder extension now reports runtime counterfactual touchability: production ladder has K15/K12/K10/K8 all 0/18 touched, K6 1/18, K4/K5 2/18, K2 4/18, K1 14/18; deepest candidate with any touch is K6.
- Boundary: source/test/docs + selective helper/docs deploy + user crontab + local `/tmp/openclaw` logs/artifacts only; no engine/API restart, no PG write/schema migration, no Bybit private/signed/trading call, no auth/risk/order mutation.

## 2026-06-20 Order Audit Projection Fix

- FlashDip order diagnosis found an audit projection gap: current `trading.orders` has 19 `flash_dip_buy` Working rows with NULL `price/context_id/details`, while `trading.intents` joined by `intent_id` contains the true `ctx-*` and `details.limit_price`.
- Source confirms `OrderDispatchRequest.limit_price` already feeds `CreateOrderRequest.price`; the missing fields were dropped between `PendingOrder`/`TradingMsg::Order` and `flush_orders`.
- Rust source now carries order price/context/details into existing `trading.orders` columns. Focused checks passed: pending-registration 23, trading_writer 14, `cargo check -p openclaw_engine --lib`, touched-file rustfmt, targeted diff-check.
- Boundary: source/test/docs + read-only PG only; no Linux deploy/rebuild/restart. New runtime projection requires a future safe rebuild/restart; current old rows remain NULL.

## 2026-06-20 FlashDip Death-Rate Freshness Gate

- Alpha discovery runtime now treats stale `flash_dip_death_rate.log` as `SOURCE_FAILURE/stale_artifact` instead of active FlashDip capture.
- This closes the same false-active class as the MM verdict stale guard, but for the current non-MM strategy path.
- Focused checks passed: `test_alpha_discovery_throughput.py` 11 and runtime runner py_compile.
- Linux selective deploy + artifact-only killboard smoke confirmed current status remains fresh (`age_seconds=71986.8 < 36h`), source_ok=true, sample_count=0.
- Boundary: source/test/docs only at checkpoint; no engine/API restart, no PG write, no Bybit private/signed/trading call, no runtime/auth/risk/order mutation.

## 2026-06-20 MM Verdict Cost-Wall Bridge

- `recorder_mm_verdict_cron.sh` now carries the break-even lens into daily live MM status: per-symbol edge-before-fees, break-even maker fee, fee shortfall, required spread capture, required maker rebate, and top-level `cost_wall_summary`.
- `runtime_runner.py` preserves this summary in alpha discovery `arms_raw` detail without changing the stable `discovery_plan` schema or positive-edge gates.
- Focused checks passed: MM cron bash/static tests 11, alpha discovery runtime tests 10, runtime runner py_compile.
- Linux selective deploy + manual read-only cron smoke confirmed `cost_wall_summary` in status: best `ARBUSDT` net `-0.1437bp`, fee shortfall `0.1437bp`, `n_maker_fills=1` below gate; BTC/ETH still require rebate.
- Boundary: source/test/docs only at checkpoint; no engine/API restart, no PG write, no Bybit private/signed/trading call, no runtime/auth/risk/order mutation.

## 2026-06-20 FillSim Cost-Wall Instrumentation

- `fill_sim.py` now reports break-even maker fee, fee shortfall, required half-spread, and required maker rebate per side for every horizon/net block.
- Focused test `program_code/research/tests/test_fill_sim_cost_wall.py` covers normal cost wall, negative break-even fee/rebate-needed, and empty-sample output.
- trade-core temp smoke on fresh L1 (`fillsim_cost_wall_smoke_20260620T003611Z.json`) showed the current MM failure is structural: back fill_only net@15 `-5.365bp` and front fill_only net@15 `-4.796bp`; both still require maker rebate to break even.
- Boundary: no production report overwrite, no engine/API restart, no PG write, no Bybit private/signed/trading call; this is a single-regime diagnostic, not CP-3 go/no-go or promotion proof.

## 2026-06-20 MM Verdict Stale Guard + Cron Restore

- Fixed alpha discovery killboard so stale `recorder_mm_verdict` status older than 36h becomes `SOURCE_FAILURE/stale_artifact` instead of active MM capture; focused alpha discovery tests are now 10 passed.
- Restored Linux daily `recorder_mm_verdict_cron.sh` at `41 6 * * *`; manual read-only run updated MM samples from 3 to 16, all current net-edge symbols remain negative and below sample gate.
- Caveat: fill_sim report was ~57h old; after 72h adverse_selection becomes unavailable unless a separate heavy refresh schedule is approved/designed.

## 2026-06-19 Alpha Discovery Runtime Killboard

- 1-6 alpha discovery throughput 從 source/test scaffold 接成 artifact-only runtime killboard：讀 Gate-B / FlashDip / vol-event / MM verdict / AEG matrix artifacts，寫 `<DATA>/alpha_discovery_throughput/alpha_discovery_latest.json`。
- 新 cron wrapper 可每 15 分鐘更新 killboard；`is_fast_discovery_active` 需至少 3 個真實 artifact source present，避免空跑假陽性。
- 邊界：不連 DB、不連 Bybit、不啟 probe、不下單、不改 auth/risk/runtime state；目前是 discovery-orchestration active，不是可晉升 alpha proof。

## 2026-06-19 TODO v227 Passive-Watch Refresh

- Refreshed passive watch surfaces without closing any active gate.
- Source sync: Mac/origin/Linux aligned at v226 checkpoint `880b82ba`; watchdog `engine_alive=true` with demo snapshot age `7.4s`.
- Gate-B latest `2026-06-19T01:42:01Z` remained `WATCH_ONLY` with 21 total candidates, 0 alertable/start/schedule, and 1 watch_only; no preflight/probe was run.
- flash_dip remained zero-sample; L2 cursor remained `2026-06-17` with B3 shadow rows=0; D2 `reconcile_ghost_converge` total/semantics rows remained 0.
- Passive health at `2026-06-19T01:45:02Z` still failed `[74]` (`attempts=201`, `postonly=26`, `max_pending=0`) and `[56]` (`authorization_json_missing`). Boundary: docs/TODO/report + read-only Linux file/PG/healthcheck only; no CI/cargo/Linux build/deploy/rebuild/restart/DB write/Bybit private call/credential/runtime/auth/risk/order/trading mutation/probe/archive/promotion.

## 2026-06-19 TODO v226 Source-Sync Correction

- Corrected source-sync metadata after v225 passive-watch refresh.
- Mac `HEAD=origin/main=e8ade59a` and Linux `trade-core` `HEAD=origin/main=e8ade59a` after ff-only sync.
- Linux watchdog read-only status: `engine_alive=true`, demo snapshot age `30.0s`.
- Boundary: docs/TODO metadata only; no CI/cargo/Linux build/deploy/rebuild/restart/DB write/Bybit private call/credential/runtime/auth/risk/order/trading mutation; no active gate closed.

## 2026-06-19 TODO v225 Passive-Watch Refresh

- Refreshed passive watch surfaces without closing any active gate.
- Source sync: Mac/origin/Linux aligned at v224 checkpoint `f622574a`; watchdog `engine_alive=true` with demo snapshot age `28.6s`.
- Gate-B latest `2026-06-19T01:12:01Z` remained `WATCH_ONLY` with 21 total candidates, 0 alertable/start/schedule, and 1 watch_only; top BPUSDT candidates were stale/old ContinuousTrading, so no preflight/probe was run.
- flash_dip entry remained `{}` and read-only PG found 0 flash_dip rows; L2 cursor remained `2026-06-17` with 2026-06-12..17 no-op material days and B3 shadow rows=0; D2 `reconcile_ghost_converge` total/semantics rows remained 0.
- Passive health at `2026-06-19T01:23:30Z` still failed `[74]` (`attempts=200`, `postonly=26`, `max_pending=0`) and `[56]` (`authorization_json_missing`). Boundary: docs/TODO/report + read-only Linux file/PG/healthcheck only; no CI/cargo/Linux build/deploy/rebuild/restart/DB write/Bybit private call/credential/runtime/auth/risk/order/trading mutation/probe/archive/promotion.

## 2026-06-19 TODO v224 Stage0R Current-Head Wrapper True-PG Rerun

- Refreshed `P1-A1A2-STAGE0R-RUNNER-IMPL` with current-head Linux true-PG read-only wrapper evidence, superseding the stale "no new true-PG rerun beyond v217 artifact" caveat without closing the row.
- Linux canonical `trade-core` was `HEAD=origin/main=e69d5fd3`; run dir `/tmp/openclaw/stage0r_current_head_verify_20260619T011508Z`; `PGOPTIONS="-c default_transaction_read_only=on"` with DB URL/password env deliberately unset.
- Evidence: 8b row_count=8034 / eligible=false / `no primary-horizon signals`; alpha_candidate `observe_more` / `stage0_ready=false` / A1 `draft_only` / A2 `observe_more`; standalone 8c `RED` / `review_ready=true` / total_rows=291 / total_bucket_count=2924 / long=164 / short=121 / missing-denominator scan=0.
- Boundary: no full CI/cargo/Linux build/deploy/rebuild/restart/DB write, no repo artifact write beyond docs, no Bybit private call, no credential mutation/auth/risk/order/trading mutation; trusted promotion packet, full E4 review, QC/MIT/QA sign-off, Stage0R promotion, P0-EDGE, and operator gates remain open.

## 2026-06-19 TODO v223 Source-Sync Correction

- Corrected source-sync metadata after v222 Earn first-stake routing review.
- Mac `HEAD=origin/main=712d3a03` and Linux `trade-core` `HEAD=origin/main=712d3a03`; Linux tracked checkout was clean except existing unrelated untracked `vol-event-robust-ruling.md` and `variance_risk_premium/`.
- Watchdog read-only status: `engine_alive=true`, demo snapshot age `9.6s`.
- Boundary: docs/TODO metadata only; no CI/cargo/Linux build/deploy/rebuild/restart/DB write/Bybit private call/credential mutation/auth/risk/order/trading mutation; no active gate closed.

## 2026-06-19 TODO v222 Earn First-Stake Capability Routing Focused Review

- Refreshed PM-local evidence for `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` without closing the runtime/first-stake row.
- Source review confirms bootstrap injects `BybitEarnClient` and `EarnMovementWriter` from existing runtime handles only, missing deps still fail closed as `earn_dispatch_unwired`, Rust IPC routes `process_earn_intent` into the event-consumer owner task, and Python `/api/v1/earn/stake` sends `engine="live"`.
- Focused checks passed: `process_earn_intent_command` 2, `process_earn_intent` 4, `earn_router_fail_closed_when_unwired` 1, Python Earn route suite 28 with one existing Pydantic warning, and `cargo clippy -p openclaw_engine --lib -- -D warnings`.
- Boundary: no full CI/Linux cargo/deploy/rebuild/restart, no real Bybit call, no credential/key/secret mutation, no runtime DB write, no auth/risk/order/trading mutation, and no first-stake evidence. OP-1/2/3 plus review/deploy/restart remain open.

## 2026-06-19 TODO v221 D2 Audit Semantics Focused Review

- Refreshed PM-local evidence for `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` without closing the row.
- Source review confirms D2 dispatch uses `PipelineCommand::ConvergeExchangeZero` rather than `CloseSymbol`, dispatch-site audit rows use `confirmed=false` / `dispatched-not-confirmed`, handler-confirmed wording is reserved for handler-side fact, and `converge_exchange_zero_close` removes local drift plus clears pending close without synthetic PnL/Kelly pollution.
- Focused checks from `srv/rust` passed: payload semantics tests 2, orphan_handler suite 19, loop-break regression 1, ghost suite 11, and `cargo clippy -p openclaw_engine --lib -- -D warnings`.
- Linux read-only DB count still showed `reconcile_ghost_converge` total=0 / semantics_rows=0, so production event proof remains open. Boundary: no full CI/Linux cargo/deploy/rebuild/restart/DB write/Bybit private call/auth/risk/order/trading mutation.

## 2026-06-19 TODO v220 Reconciler Pagination Focused Review

- Refreshed PM-local evidence for `P2-RECONCILER-GET-POSITIONS-PAGINATION` without closing the row.
- Source review confirms full-scan `get_positions(None)` uses `settleCoin=USDT` + `limit=200` pagination, normalizes empty/missing cursor to None, fails closed on same-cursor response, maps the client-side invariant as Structural / sync-untrusted, and keeps the ghost point-query gate load-bearing against pagination-truncated false ghosts.
- Focused checks from `srv/rust` passed: `position_manager::tests` 19, dispatch invariant mapping 1, exchange-stop invariant mapping 1, false-ghost regression 1, `position_reconciler::tests::ghost` 11, and `cargo clippy -p openclaw_engine --lib -- -D warnings`.
- Boundary: initial wrong-root cargo invocation failed before tests and was rerun correctly; no full CI/Linux cargo/deploy/rebuild/restart/DB write/Bybit private call/auth/risk/order/trading mutation. Formal BB/E2/E4/QA review and production event proof remain open.

## 2026-06-19 TODO v219 Stage0R 8c E4 Focused Regression

- Reduced the open `P1-A1A2-STAGE0R-RUNNER-IMPL` E4 denominator-fix review risk with a focused local regression report, without closing promotion/trusted-runner authority.
- Evidence: py_compile PASS; 8c smoke_cli 11/11 twice; 8c metrics smoke twice; alpha_candidate smoke twice; 8b funding_skew smoke twice; `helper_scripts/lib/tests/test_stats_common.py` 33 passed.
- Source inspection confirms the 8c wrapper now passes raw 5m `total_bucket_count` to single/sweep metrics, metrics still fail-close when omitted, and smoke coverage checks both paths.
- Boundary: no full CI, no Linux full E4 suite, no new true-PG rerun beyond v217 PM artifact, no deploy/rebuild/restart/model call/DB write/auth/risk/order/trading mutation.

## 2026-06-19 TODO v218 Source-Sync Passive Watch Refresh

- Corrected TODO source HEAD from stale v216 `61e1a6d2` to v217 `737356a5`; Mac/origin/Linux are aligned at `737356a5`.
- Read-only passive recheck found no actionable event: Gate-B remains `WATCH_ONLY`, flash_dip entry is still `{}` with no death-rate success file, L2 cursor remains `2026-06-17` with zero material/stored days, and passive health still fails `[74]`/`[56]`.
- Boundary: docs/TODO + read-only Linux file/healthcheck only; no CI/deploy/rebuild/restart, no model call, no DB write, no auth/risk/order/trading mutation.

## 2026-06-18 Earn First-Stake Capability Routing

- Reduced `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` source blocker without closing the runtime row.
- Rust event-consumer bootstrap now injects `BybitEarnClient` from `shared_client` and `EarnMovementWriter` from `audit_pool`; construction is handle-only and does not call Bybit/PG.
- Python `/api/v1/earn/stake` now sends `engine="live"` to `process_earn_intent`, so the operator/live_reserved asset-movement lane does not rely on primary fallback.
- Focused checks passed: Rust owner-task unwired/wired-gate regression, Rust IPC `process_earn_intent` selector, Earn router unwired selector, Python Earn route suite, rustfmt check, and `git diff --check`.
- Boundary: no real Bybit call, no key/secret mutation, no deploy/rebuild/restart, no runtime DB/auth/risk/order/trading mutation. Remaining: OP-1/2/3, review/deploy/restart, first real stake evidence.

## 2026-05-15 A4-C PM/PA/FA Unblock Engineering Card

- Operator asked PM/PA/FA to formalize the A4-C unblock path and start in
  order.
- PA proposed a bounded diagnostic revive path: read-only Stage 0R RCA,
  preregistered revision only if evidence supports it, then Stage 0R rerun.
- FA pushed back: A4-C does not currently justify 7d Demo micro-canary budget;
  it remains archived from active promotion because Step 5b has weak edge,
  failed PSR/DSR, CI lower < 0, and near-zero R2.
- PM decision: add `P1-A4C-RCA-1` as the single allowed read-only RCA path.
  No paper promotion, no demo launch, no gate relaxation, no runtime/auth/risk
  mutation. If RCA finds no new preregistered hypothesis, move alpha effort to
  W-AUDIT-8b / W-AUDIT-8a C1.
- RCA start result: current 7d dry-run fetched 6,713 rows and remained worse
  than Step 5b (`avg_net_bps=-1.0013`, `PSR(0)=0.1904`, `DSR=0`,
  R2(120)=0). Finite threshold probe X=5/Y=0.20 improved sample size and
  weakly positive average (`+1.4739 bps`) but remains far below +15 and below
  per-symbol +5 defer band. This strengthens the archive/default-switch read.

## 2026-05-15 TODO v30 Three-Side Source Sync

- Operator asked to update TODO and perform three-side sync.
- PM verified Mac `HEAD`, local `origin/main`, and Linux `trade-core` were
  clean/aligned at pre-v30 base `9a72d054` before the v30 docs update.
- Active docs still had stale sync wording: `CLAUDE.md` referenced
  `TODO.md v28`, while `CLAUDE.md` / `active-plan.md` referenced source sync
  `81bc0862`.
- Updated TODO to v30 and aligned `CLAUDE.md`, `active-plan.md`,
  `.codex/MEMORY.md`, `.codex/WORKLOG.md`, PM report index, and docs index.
- Boundary: source/docs sync only. No runtime rebuild/restart, DB write, auth
  renewal, production WS topic revival, paper enablement, demo canary, risk /
  sizing / config mutation, or live action.

## 2026-05-15 A4-C RCA Final + C1 Proof Start

- QC(default) and MIT(default) both rejected opening `P1-A4C-REV-1`.
- Final `P1-A4C-RCA-1` result: current A4-C feature shape stays archived from
  promotion. The 7d RCA was negative/weak (`avg_net_bps=-1.0013`,
  `PSR(0)=0.1904`, `DSR=0`, R2(120)=0), and the best finite X=5/Y=0.20
  probe was only `+1.4739 bps`, below revive/promotion bands.
- PM closed `P1-A4C-RCA-1` as no revive hypothesis found; do not run same-shape
  A4-C Stage 0R again unless a materially new predictive variable is
  preregistered in the future.
- C1 isolated smoke returned `SMOKE_PASS_NOT_C1_PROOF`. PM started the 24h
  standalone `allLiquidation.BTCUSDT` proof on `trade-core` at
  `2026-05-15T19:53:09Z`, PID `4100789`, log
  `/tmp/openclaw/audit/liquidation_topic_probe/nohup_20260515T195309Z.log`.
- C1 remains blocked until the 24h report passes and BB/MIT sign off; no
  production subscription, parser/writer revival, DB write, rebuild/restart,
  auth renewal, paper/demo launch, risk/sizing/config mutation, or live action.

## 2026-05-15 W-AUDIT-8b Review + Stage 0R Design

- QC(default), MIT(default), and BB(default) reviewed Funding Skew v0.1 and
  conditionally approved Stage 0R replay design only.
- No strategy implementation, demo launch, runtime config change, risk/sizing
  edit, production mutation, or funding-payment edge credit is authorized.
- Spec v0.2 locks: 30m primary horizon, 15m/60m sensitivity counted in K,
  crowded-long fade and crowded-short squeeze as separate branches,
  `K_total >= K_prior+4050`, `DSR>=0.95`, PBO fail-closed, raw
  `panel.funding_rates_panel` / `panel.oi_delta_panel` as-of joins,
  funding attribution `excluded`, and Bybit funding interval/source-mode fields.
- Runtime panel freshness probe at 2026-05-15 22:13 CEST passed:
  `funding=PASS(20929ms)`, `oi=PASS(20969ms)`.
- Next work is PA/E1 packet for a read-only `funding_skew_directional.v0_2`
  Stage 0R query/report only.

## 2026-05-15 close-maker-first Refactor PM Verdict

- 對主會話 3 輪對抗審 + DB/代碼核驗 + 5 gap 清單做 PM 治理驗證。
- Verdict: APPROVED-CONDITIONAL（純 spec/設計授權；IMPL 排 Sprint N+2，不 scope-in W3）。
- W3 scope-in 拒絕：W3-1/W3-2 ncyu-blocked、Stage 0R GATE-RED 雙鎖死、alpha-bearing pathway
  必走 AMD-2026-05-09-03 5-stage canary，當前在 Stage 0R 失敗下啟 IMPL 違反 §二 原則 #6。
- 例外授權：MA KAMA fallback warn! + skip entry（30 分鐘獨立修復）scope-in W3-6 by-the-way。
- Phase 命名 = EDGE-P2-3 Phase 1b（entry 1a 自然延伸到 close path 同 alpha 軸；
  Phase 1c 留給 resting orders microstructure 軸；EDGE-P2-4 留給 alpha source promotion gate）。
- AMD 要求：是。跨 §二 原則 #6 但不違反（whitelist 8 策略降 fee + 2 Market keep 保真風控）。
  AMD 必含 close path 為 alpha-bearing pathway 明文 + whitelist/keep 邊界 + phys_lock live

  決策分軌 + Stage 0R 先 replay preflight + compute_close_limit_price spec。
- 優先序: P1（非 P0）。理由：fee/cost 優化救不了 -110.43 USDT structural alpha deficit；
  排 Sprint N+2 backlog 在 N2-AUDIT-7c/8c/PhaseC/PhaseD 之後、P0 全 closed 前不啟 IMPL。
- phys_lock live 啟用決策歸 operator（PM 提案 + FA 規格 + QC 數學佐證），建議先 demo
  Stage 1 micro-canary 7d 證 Gate 4 phys_lock 真實 PnL 改善才提 live AMD。
- 補 governance gates: §二 原則 #4 Guardian veto 必過、DOC-08 §12.4 hard_stop 觸發
  cancel+Market re-submit replay 必驗、maker fill rate empirical baseline 必先採、
  compute_close_limit_price() spec PA 必出。
- 條件 4 條：PA spec 先出、AMD 經 QC+FA+BB+MIT 4-agent adversarial review、
  P0-EDGE-1+W-AUDIT-8b Stage 0R+W-AUDIT-8a C1 BB/MIT sign-off 三閘前不啟 IMPL、
  IMPL 走強制工作鏈不走 P0 快速通道。
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-15--close_maker_first_pm_verdict.md

## 2026-05-16 v35 Current Progress Sync + Rebuild Decision

- Operator asked to verify progress, update TODO/CLAUDE/Codex memory, perform three-side sync, and rebuild if required.
- PM verified Mac had uncommitted WP-13 leftover P1 Rust changes from the Round 4 E2 RETURN. The fix is now committed as `a7cb517f`.
- Verification for `a7cb517f`: `cargo check --release -p openclaw_engine` PASS; `tune_cmd_snapshot` 2/2 PASS; `edge_reload_tests` 16/16 PASS; full lib PASS 2908/0/1 after escalated rerun for sandbox socket tests; bin PASS 62/0.
- C1 standalone liquidation proof ended early with `FAIL_CONNECTION` at `2026-05-16T00:37:25Z` after `17055.2s/86400s`; it saw 15 `allLiquidation.BTCUSDT` candidate messages but is not proof-eligible. C1 remains blocked until a full-duration BB/MIT-signed proof.
- Before sync, Linux `trade-core` was clean but behind origin; runtime engine/API were alive and binary still reflected the prior `7b33ab2e` rebuild. Because v35 contains Rust runtime changes, rebuild was required after sync.
- Deployment completed: runtime/code-bearing v35 head `5f6f3edf` synced across Mac/origin/Linux before rebuild; post-rebuild docs-only sync may advance repository HEAD without another rebuild. `trade-core` ran `PATH=$HOME/.cargo/bin:$PATH bash helper_scripts/restart_all.sh --rebuild --keep-auth` successfully; post-rebuild engine PID `69581`, API PID `69674`, watchdog `engine_alive=true`, demo fresh.
- Runtime caveats after rebuild: signed live auth is absent and was not renewed by `--keep-auth`, so live remains inactive/blocked. `OPENCLAW_ENABLE_PAPER=0`; engine log says paper pipeline disabled and `paper_state.disabled=true`, so the fresh paper marker is disabled-state output, not active Paper trading.
- Report: `workspace/reports/2026-05-16--v35_three_side_sync_rebuild.md`.

## 2026-05-16 TODO v36 Completion Cleanup

- Active TODO was promoted to v36 after v35 rebuild. Completed v35 / 2026-05-15..16 detail was cross-checked against commits and PM/E2/E4/BB reports, then moved to `docs/archive/2026-05-16--todo_v36_completion_cleanup_archive.md`.
- Active TODO now keeps blockers, dependent gates, deferred work, and runnable backlog only. Runtime/code-bearing rebuild head remains `5f6f3edf`; this cleanup is documentation-only and does not require another rebuild.
- E2/BB `BB-MF-3` review found `arm_close_cooldown` plumbing and tests landed, but no production caller yet; keep `P1-BBMF3-WIRE-1` active for Phase 1b rather than archiving it as completed.
- Current blockers remain: W-AUDIT-8a C1 is not proof-eligible after `FAIL_CONNECTION`; true-live remains blocked by `P0-EDGE-1`, `P0-LG-1/2/3`, and `P0-OPS-1..4`.

## 12-Agent Full System Audit Sign-off (2026-05-16)

- PA consolidated 12 parallel audit agents (FA/AI-E/QC/E5/A3/E3/MIT/R4/BB/CC/E4/TW) into
  13 WPs across 4 waves. PM APPROVED-CONDITIONAL.
- 5 PM reprioritizations applied:
  1. WP-02 Donchian P0->P1: runtime already calls `donchian_prior()` since `75741eff`; the base
     `donchian()` retaining current-bar is hygiene, not live P0.
  2. WP-08 MIT-P0-2 "6/12 cron not installed" conflicts with TODO P0-V3-CRON-NOT-INSTALLED DONE;
     PA must reconcile before dispatch.
  3. AI-E-F-01 daily_usd_max $100->$2 requires operator decision, not auto-fix.
  4. R4 "CRITICAL" doc drift (14 ADR -> 22, 13 tab -> 16) downgraded to P2.
  5. WP-06 recommended split into WP-06a/b/c (Rust/Python/orjson) for parallel dispatch.
- True P0 items: WP-01 GUI Safety (A3-BLOCKER-1/2 emergency stop one-click) + P0-EDGE-1 (structural).
- Effort estimate: 12-15 sessions (optimistic 10 / pessimistic 18).
- Conflict guard: Wave 2 WP-03 (grid_helpers.rs) must land BEFORE EDGE-P2-3 Phase 1b IMPL;
  WP-06 performance must wait until Phase 1b stabilizes.
- Key lesson: 4 of 14 original P0/CRITICAL findings were false elevations (by-design pre-live state
  or deprecated strategies). PA's verification layer correctly caught all 4. Reinforces the principle
  that audit agents should distinguish "not yet implemented" from "broken/missing".
- TODO updated to v33 with new section 11.6 (13 WPs + wave assignments).
- Approved report: `srv/2026-05-16--full-system-audit-fix-plan.md` (PM sign-off appended).
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--12-agent-audit-pm-signoff.md

## 2026-05-16 Stage 1 Demo + A4-C Tombstone Cleanup

- Operator confirmed paper should not be promotion evidence; promotion must rely
  on Demo. PM cleaned active docs accordingly.
- Active docs now keep Stage 1 as Demo-only after future green Stage 0R. There
  is no active W3 paper cohort marker.
- A4-C is tombstoned in active docs: keep `panel.btc_lead_lag_panel` and `[57]`
  for diagnostics only; do not use A4-C as Stage 0R promotion candidate or
  Stage 1 Demo cohort source.
- Detailed A4-C Step 5b/RCA evidence remains archived; active TODO keeps only
  the guard to prevent accidental revival from old specs.
- No runtime, DB, auth, risk, strategy, paper, demo, LiveDemo, or live mutation.
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--stage1_demo_a4c_tombstone_cleanup.md

## 2026-05-16 Option A Phase 1b + W-AUDIT-8b IMPL Closure

- Operator selected Option A: dispatch Phase 1b Worktree B and W-AUDIT-8b Round 2 Phase A in parallel.
- W-AUDIT-8b v0.3 4-cell sweep tooling landed at `a6e17d5d` after E1 -> A3/E2 -> E4 PASS.
- Phase 1b close-maker-first source/test bundle landed at `ea4ceca6` after E1 rounds 1-3 -> A3/E2 -> E4 PASS.
- No deploy, production SQL migration, runtime restart, auth mutation, paper enablement, live/mainnet enablement, or production `allLiquidation` subscription.
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--option_a_phase1b_w_audit8b_impl_closure.md

## 2026-05-17 W-AUDIT-8c Correction Source/Test Closure

- C1 v2 proof passed technically, but production liquidation writer revival remained blocked by MIT's lossy `(symbol, ts, side)` idempotency condition.
- W-AUDIT-8c correction source/test is now done: V095 source migration uses `(symbol, ts, side, qty, price)`, parser/writer fail closed for invalid `allLiquidation` rows, and corrected Bybit side mapping is tested (`Buy` long liquidation / `Sell` short liquidation).
- BB approved the correction patch; E2 approved conditionally on excluding unrelated GUI dirty files; MIT still requires Linux PG dry-run x2, V095 apply authorization, and re-sign before production writer/topic revival.
- No deploy, Linux DB apply, runtime restart, auth mutation, paper/live/mainnet enablement, strategy/risk mutation, or production `allLiquidation*` subscription happened.
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--w_audit_8c_correction_source_test_closure.md

## 2026-06-04 Alpha-Edge P1 EvidenceManifest Gate

- EvidenceManifest 的 PM 原則：不能只落成 JSON / lineage 文檔；若 producer 不檢查、LG-5 不重驗，對 alpha promotion 幾乎等於沒有 gate。
- 本批完成 source/test/docs-only fail-closed 接入：MLDE live-candidate producer 與 LG-5 reviewer 都要求 canonical `candidate_evidence_manifest` + valid `demo_residual_alpha_report`，missing / alias / invalid / research_only / pending_schema 都不可 create/approve live candidate。
- 保留現實邊界：這不代表 hidden OOS registry 或真實 manifest producer 已完成；缺 manifest 的真實 upstream row 會被阻斷，而不是被自動修補。
- Report: docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-04--alpha_edge_p1_candidate_evidence_manifest_gate.md

## 2026-06-11 派工四態契約生效

- subagent 回報首行 STATUS 四態；處置表=DONE 驗收 / DONE_WITH_CONCERNS 讀 concerns 補驗 / NEEDS_CONTEXT 補 context 重派（可同模型）/ BLOCKED 換強模型、拆任務或升級 operator，禁無變更同模型裸重試；餵全文 + 共享 contextPath SOP 入 PM.md「派工四態契約與升級階梯」，agent-wave 自動 append 契約 footer 並回傳 statuses 索引。

## 2026-06-11 AEG-S3 + Claude Tooling 三端同步

- Operator 要求「三端同步」。本批同步範圍：Claude hooks/rtk/four-state contract/skill trigger rewrite + AEG-S3 candidate direct rows、listing_fade、oi_delta artifact-only evidence producers。
- AEG-S3 驗證：focused regression（listing fade + oi_delta + candidate rows + candidate metrics + robustness + Gate-B probe）= 70 passed；compileall OK；static forbidden-route search 新模組無 runtime/DB/Bybit route。
- Claude tooling 驗證：`bash -n` hooks、`node --check .claude/workflows/agent-wave.js`、`.claude/settings.json` JSON parse OK；secret-pattern 搜尋只命中文檔/技能中的安全詞與路徑說明。
- 邊界：docs/tooling/research artifact sync only；不重啟 runtime、不 rebuild、不改 DB/auth/risk/trading。P5-SM soak 繼續跑；AEG-S3 尚未產真候選 promotion proof，下一步仍是 Gate-B true transition artifact、V125 OI/price/regime export、candidate-grid PBO、funding_revive producer、E2/MIT/QC 審。

## 2026-06-12 AEG-S3 event breadth funding matrix

- `8fed7073` 新增 AEG-S3 event breadth adapter：funding/listing 單 symbol event evidence 可用 FND-2 PIT tiers 產真 `breadth_ladder`；`oi_delta` basket evidence 明確 fail-closed。
- Linux funding_revive event breadth `aeg_s3_funding_revive_event_breadth_v125_20260611T200033Z_oos20260301_pbo18` healthcheck PASS，full_survivorship breadth=829/delisted=255/n_independent=261；formal matrix 24 rows，coverage PASS、survivorship `pit_fnd2_delisted_proof`，但 DSR=0/PBO=0.54583333/execution unverified → 仍 non-promotable。

## 2026-06-12 P2 batch activation partial

- owed #3 Bybit 公告哨兵與 owed #4 Polymarket daily artifact cron 已在 `trade-core` 安裝並手動驗證；Bybit formal data-dir run 50 items/0 alerts，Polymarket `daily-20260612T090806Z` 6100 rows/0 errors。
- owed #2 V138/V139 與 owed #5/#6 L2 activation 未跑：checksum drift=0、prod head=137，但 P5-SM `[82]` soak 仍 accumulating（31.2h<48h，934 probes），migration 唯一路徑需 engine restart，故依 survival/system-health 邊界停在 A/B 前。

## 2026-06-12 AEG-S3 empirical execution realism + Gate-B watch

- `c35f8425` 新增 artifact-only AEG-S3 event execution realism adapter：`listing_fade` / `funding_revive` candidate evidence 可用 matched execution-observations JSONL 產 canonical `execution_realism.json`；`oi_delta` basket 明確 fail-closed。
- Gate-B 等待口徑改為事件觸發：現官方 new listing 最新批為 2026-06-09 已 open perpetual，live PreLaunch 只有老 `BPUSDT`（ContinuousTrading since 2026-03-16）；下一步盯 BPUSDT conversion 或下一個 fresh Pre-Market/PreLaunch 公告，再開 isolated 24h probe。

## 2026-06-12 AEG-S3 sidecar matrix wiring

- `66a9e511` 讓 `aeg_s3_matrix_inputs` 可直接引用既有 `breadth_ladder` / `execution_realism` sidecar artifact；缺 sidecar 時原 fail-closed placeholder 不變，candidate/parameter mismatch 直接 fail-closed。
- Mac/Linux focused regression 各 `24 passed`；Linux true funding_revive sidecar matrix smoke row_count=24、coverage PASS、survivorship `pit_fnd2_delisted_proof`、execution 仍 `unverified_missing_missing`，所以仍 non-promotable。

## 2026-06-12 AEG-S3 execution observations producer

- `9eaad929` 新增 artifact-only `aeg_s3_execution_observations`：把 `listing_fade` candidate evidence + Gate-B run 轉為 matched `execution_observations.jsonl`，供 `aeg_s3_event_execution_realism` 使用。
- 邊界：只支援 Gate-B listing_fade；funding_revive/oi_delta 不冒充；source 是 publicTrade prints only，不宣稱 orderbook-depth fill realism。
- Mac/Linux focused regression 各 `31 passed`；Linux old Gate-B smoke `listing_24h_20260602_1847` 只產 2 matched observations，execution realism 10 USDT FAIL=樣本不足+participation，1 USDT FAIL=樣本不足。producer 已接通；promotion 仍需 fresh Gate-B `>=30` matched samples 後重跑 formal matrix。

## 2026-06-12 AEG-S3 Gate-B evidence chain wrapper

- `75ed19c8` 新增 artifact-only `aeg_s3_gate_b_chain`：fresh Gate-B run 後一鍵編排 listing evidence、candidate rows、candidate metrics、execution observations、event execution realism；若提供 FND2+regime，再接 event breadth + formal matrix。
- Mac/Linux focused regression 各 `52 passed`；Linux true smoke `aeg_s3_gate_b_chain_listing_smoke_20260612` 用舊 run 產 2 listing samples / 2 execution observations，chain_status=`COMPLETE_EXECUTION_REALISM_FAIL`，reject=`sample_count_below_30`。
- 邊界：wrapper 只編排既有 artifact harness，不收集資料、不呼叫 Bybit、不寫 DB、不碰 runtime；wrapper 完成不是 promotion proof，fresh Gate-B 仍需 `>=30` matched samples + E2/MIT/QC 審。

## 2026-06-12 AEG-S3 listing_fade PBO grid wiring

- `3d03698c` 讓 `listing_fade` PBO candidate grid 變成明確 opt-in：`--include-default-pbo-grid` / `--pbo-grid-json`，默認不偽造 PBO，grid 不足 10 cells 時 fail-closed。
- Gate-B chain 已 pass-through PBO knobs 並輸出 `listing_pbo_status`；Linux old-run smoke 產 `produced_candidate_grid`，但仍因 sample_count=2 fail `sample_count_below_30`。
- Mac/Linux focused regression 各 `54 passed`；compileall/static scan OK；本批無 CI、無 deploy/rebuild/restart、無 DB/auth/risk/trading mutation。

## 2026-06-12 AEG-S3 Gate-B full matrix PBO readiness

- `235858f4` 固化 Gate-B chain full formal matrix 分支也必須攜帶 listing_fade PBO：test 斷言 `listing_pbo_status=produced_candidate_grid`、candidate rows `pbo_status=measured`。
- Linux final smoke 用 old Gate-B + 真 FND2/regime 跑完整 chain：formal matrix row_count=12、coverage PASS、survivorship `pit_fnd2_delisted_proof`、final labels 7 insufficient / 5 kill，chain_status non-promotable 只因舊 run sample_count=2。
- 結論：fresh Gate-B 到來後的 execution + event breadth + formal matrix + PBO 全鏈已可執行；promotion 仍需 fresh `>=30` matched observations + E2/MIT/QC。

## 2026-06-19 Vol-Event Robust Ruling Evidence

- Linux vol-event cron 自動產出 high-vol robust ruling：4 independent high_vol events（3 downside / 1 upside_squeeze），0/4 survives fee wall，robust ruling `NO_EDGE_SURVIVES`。
- PM 收錄為 dated repo report `docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-18--vol-event-robust-ruling.md` 並更新 TODO v216；這是 evidence trace，不是 QC final promotion verdict。
- 邊界：docs/report only；無 runtime/DB/auth/risk/order/trading mutation，P0-EDGE/Gate-B/flash/L2/operator gates 不因此關閉。

## 2026-06-19 Stage0R 8c Denominator + PM Runtime Verification

- PM runtime verification of Stage0R report wrappers found standalone 8c no-sweep emitted `missing_bucket_count_denominator`; alpha_candidate A2 adapter already passed the denominator.
- Source fix: `w_audit_8c/liquidation_cluster_stage0r_report.py` now queries raw 5m liquidation `total_bucket_count` and passes it into single/sweep metrics; smoke_cli pins the no-missing-denominator invariant.
- Linux `/tmp` temp clone true-PG post-fix run `stage0r_8c_denominator_fix_20260619T001027Z` produced `RED`/`review_ready=true`, total_rows=291, total_bucket_count=2931, long=164, short=121, missing_denominator=false.
- TODO advanced to v217. PM formal runtime verification is done; E4 review remains open before trusting Stage0R runner outputs. No deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-12 AEG-S3 Gate-B preflight locator

- `44a30afa`/`f4a58b3c` 新增 artifact-only `aeg_s3_gate_b_preflight`：定位 Gate-B/FND2/regime，preview listing sample/PBO，輸出 full-chain command；auto locator 要求 FND2/regime summary 語義驗證。
- Mac/Linux focused regression 各 `58 passed`；Linux explicit/auto smoke 均回 `READY_BUT_SAMPLE_BELOW_GATE`、sample_count=2、pbo_status=`produced_candidate_grid`、recommended command generated。
- fresh Gate-B 後先跑 preflight，再按 generated command 跑 full matrix；preflight ready 不等於 promotion proof。

## 2026-06-12 AEG-S3 Gate-B watch preflight bridge

- `2b880f5d` 讓 `aeg_s3_gate_b_preflight` 讀 local `gate_b_watch_latest.json`，輸出 `gate_watch.operator_action` 與 `probe_command_hints`；`WATCH_ONLY` wait-only，`ACTIONABLE_*` 才給 isolated probe hint，stale/malformed/source failure fail-closed。
- Mac/Linux focused regression 各 `62 passed`；Linux smoke 讀 live watch artifact 得 `WATCH_ONLY`、23 candidates、0 alertable/start/schedule、operator_action=`WAIT_FOR_ACTIONABLE_WATCH`、old Gate-B sample_count=2。

## 2026-06-12 AEG-S3 Gate-B preflight command guard

- `289fcbe8` 將 Gate-B preflight 升 v0.3：`recommended_command` 增加 operator guard，wait-only + sample<30 時輸出 `operator_recommended=false` / `HOLD_WAIT_FOR_ACTIONABLE_WATCH`，防止舊 full-chain shell 被誤當當前 action。
- Linux 同步後 focused preflight 8 passed；live smoke 仍 `WATCH_ONLY`、23 candidates、0 alertable、sample_count=2；P5-SM `[82]` 2026-06-12T21:00Z 為 `43.0h<48h`、probes=1290，約 2026-06-13 03:59:37+02 到期。

## 2026-06-12 P5-SM [81]/[82] selector fix

- `bf673cdc` 修好 `passive_wait_healthcheck.runner --check 81 --check 82` narrow routing；只改 CLI selector dispatch，不改 `[81]/[82]` 判定邏輯。
- Mac/Linux `test_lease_ipc_soak_healthcheck.py` 各 `47 passed, 1 skipped`；Linux true DB smoke 現正常輸出 `[81] PASS`、`[82] 38.7h<48h` accumulating。

## 2026-06-12 P2 incident-policy dispatch trigger source-state checkpoint

- TODO 原 row「PA 規格完成 / 待實作」已 stale。Source 已有 `notification_failsafe/incident_policy.rs` CORE ledger、auth invalid producer、Bybit fail-closed producer、C4 incident-policy E2E；本輪 PM 修正 TODO 狀態為 partial source-live。
- Focused Rust verification on Mac and Linux: incident_policy `15 passed`; C4 failsafe wire `4 passed`; ret_code_counter `6 passed`.
- Remaining honest gaps: `sm_halt_stuck`、`position_drift`、external `engine_dead` watchdog notify-only producer coverage still pending; BB/E2/E4/QA full review still needed before declaring fail-safe runtime-complete. No CI/deploy/rebuild/restart/DB/auth/risk/trading mutation.

## 2026-06-12 P2 incident-policy BB/E2 review checkpoint

- BB `APPROVE-WITH-CONDITIONS` + E2 `PASS-WITH-CONDITIONS` for existing CORE+auth+Bybit source-live path; 0 blocker/high/medium.
- Boundaries preserved: `incident_policy` does not add Bybit requests or direct risk/system/auth mutation; C4 owner handler remains the only `set_trading_stop` side-effect path; `bybit_fail_closed` wording must stay business-retCode fail-closed, not full exchange-outage coverage.
- TODO v141 marks the ticket as BB+E2 reviewed partial. Next recommended slice: remaining producer coverage, starting with `sm_halt_stuck` arm-class, then `position_drift` / `engine_dead` notify-only.

## 2026-06-12 P2 incident-policy sm_halt_stuck producer slice

- `sm_halt_stuck` is now source-live via `event_consumer/sm_halt_incident.rs`; producer reads `TickPipeline.halt_kind` + `halt_set_ts_ms` as runtime source-of-truth, not stale passive healthcheck `[69]`.
- Hook points: after each `pipeline.on_tick()` and after the 60s lease/auth sweep; active HaltSession feeds `IncidentClass::SmHaltStuck` at 5s cadence and clears with `report_resolved` once `halt_kind` clears. Operator IPC pause remains excluded because it has `halt_kind=None`.
- Mac focused Rust: `sm_halt_incident` 5 passed; incident_policy 15 passed; C4 wire 4 passed; halt_ttl 20 passed; ret_code_counter 6 passed.
- TODO v142 keeps ticket partial: prior BB/E2 review covers CORE+auth+Bybit only; the new `sm_halt` producer still needs BB/E2/E4/QA/full-chain review, and remaining producers are `position_drift` notify-only plus external `engine_dead` watchdog notify-only. No CI/deploy/rebuild/restart/DB/auth/risk/trading mutation.

## 2026-06-12 P2 incident-policy position_drift producer slice

- `position_drift` is now source-live via `position_reconciler/incident.rs`; producer observes post-classification/post-orphan-ghost unresolved drifts before baseline update.
- Semantics: actionable = MajorDrift/SideFlip/Orphan/Ghost, MinorDrift ignored; startup grace does not accumulate; persistent threshold is existing `PERSISTENT_DRIFT_CYCLES=3`; clear path calls class-scoped `report_resolved`.
- Boundary: `IncidentClass::PositionDrift` remains policy-level `NotifyOnly`, so no C4 AllFail feed or watcher timer arm; no `PipelineCommand`, RiskGovernor, auth, DB, order, or exchange write path changed.
- Mac+Linux focused Rust: `position_reconciler::incident` 6 passed; `position_reconciler` 94 passed; incident_policy 15 passed; touched-file rustfmt and `git diff --check` passed. TODO v143 remains partial: new `sm_halt` + `position_drift` slices need BB/E2/E4/QA/full-chain review; external `engine_dead` watchdog notify-only remains unwired.

## 2026-06-12 L2 root TODO tail triage

- Root `L2_TODO.md` is not completed-archive eligible: V138/V139 activation, E2E-1, P2p sentinel operator gates, and P5 remain open. PM mirrored the uncovered tails into TODO v149 `P1-L2-ADVISORY-MESH-TAILS`; no runtime mutation/model call/deploy occurred.

## 2026-06-13 A1 basis / P2 OPS / P3 forward recorder

- A1 basis formal gate matured: `panel.basis_panel` span=14.001d, Stage0R functional path verified with `infra_gap=false`, but A1 remains `draft_only` because `no_a1_signals_after_entry_gate` and `n_eff=0`; next A1 check is event-triggered, not a passive date wait.
- P2 OPS pg_dump/passive health tests closed; P3 ticker forward recorder source landed for nullable mark/index/funding/OI, deploy-gated and forward-only.

## 2026-06-12 Documentation governance first batch

- PM -> R4/CC/FA -> PA -> PM 审阅确认：Markdown 历史证据不做删除；第一批只做 active/history 边界降权、routing banner、initiative index、audit folder semantics 和未跟踪 `.DS_Store` 清理。
- 修正高风险 stale 指针：`L2_TODO.md` 不再是 active queue；funding_short 永久 DOA 与 Linear-only active 仅保留为历史，当前 authority 指向 TODO / `.codex/MEMORY.md` / `docs/agents/issue-tracker.md`。

## 2026-06-12 Documentation governance second batch

- 第二批确认策略：入口瘦身、目录 README、摘要库存和点名旧文档降权；继续不删除 Markdown、不批量移动 role reports。
- `docs/README.md` 只做 router，长索引归 `docs/_indexes/document_index.md`；`document_inventory.json` 只作规模/导航摘要，不作删除判据。
- 旧 Linear-only、L2 active stub、Paper promotion、3E-ARCH/v5.8 frozen module 语义必须在正文层明确 historical/reference，不能只依赖顶部 banner。

## 2026-06-13 P5-SM [82] clean closure

- `[82]` step-ii 48h soak gate 在 Linux 真 DB healthcheck 2026-06-13T02:05:59Z 關閉：window=48.1h、probes=1442、success_rate=1.0000、0 flag-OFF/regression/fail-streak；watchdog read-only `engine_alive=true`。
- Closure 只解除 `[82]` blocker；未 deploy/rebuild/restart、未套 V138/V139、未啟 L2 activation。step-iii cutover 與 P2 activation 仍需 operator-gated 低風險窗口。

## 2026-06-13 L2 activation preflight selector fix

- `[82]` 到時後 read-only preflight confirmed live DB head=V137, V138/V139 objects absent, activation flags off, Gate-B latest still WATCH_ONLY. Fixed passive healthcheck narrow selector gap so `[83]-[89]` can be run directly before V138/V139 activation.
- Post-sync Linux run of `--check 83..89` returned `SUMMARY: ALL PASS`: V138 checks PASS-skip, V132 sealed regression 0, L2 memory flags OFF PASS-skip.

## 2026-06-13 L2 V138/V139 activation-window packet

- V138/V139 activation is ready for an operator-approved window but not executed. Linux read-only baseline 2026-06-13T07:44Z: head=V137/all_success=true, checksum drift=0, V138/V139 objects absent, `OPENCLAW_AUTO_MIGRATE=0`, L2 memory/alpha wealth flags OFF, `[83]-[89]` true DB preflight `SUMMARY: ALL PASS`.
- Accepted path is engine auto-migrate only: temporarily persist `OPENCLAW_AUTO_MIGRATE=1`, run `restart_all.sh --engine-only --keep-auth`, restore flag to 0, then verify head=139/checksum/objects/healthcheck/watchdog. Raw `psql -f` for V138/V139 is forbidden because it bypasses `_sqlx_migrations`; V140/seed/pipeline/model/Gate-B remain separate approvals.

## 2026-06-13 L2 V138/V139 runtime activation

- Operator approved and PM executed V138/V139 engine-only auto-migrate: run `l2_v138_v139_activation_20260613T153352Z`, new engine PID 3607315, auto_migrate `Applied(2)`, `_sqlx_migrations` head=139/all_success=true/count=122, checksum drift=0, V138/V139 objects exist, new rows 0, `[83]-[89]` post-check `SUMMARY: ALL PASS`.
- Persistent `OPENCLAW_AUTO_MIGRATE=0` restored and maintenance flag absent. Current process env still has `OPENCLAW_AUTO_MIGRATE=1` because that process was started for the migration; no further migration runs until restart, and future restart reads persistent 0. Remaining L2 gates after seed: manual V140, memory pipeline/cron/embed flags, E2E model call, P2p/P5.

## 2026-06-13 L2 memory B1 seed dry-run

- Ran `seed_agent_memory.py --dry-run` on Linux after V139: B source parsed 93 `memory/MEMORY.md` candidate rows, skipped 6 by sensitive/allowlist rules, A source `agent.lessons dead_mode` deferred by dry-run contract; read-only SQL confirmed dead_mode count=6 and `agent.agent_memory` stayed 0 rows.
- Dry-run artifact `/tmp/openclaw/l2_memory_b1_seed_dry_run_20260613T161740Z.log` sha256 `f06a301a97f012dbe8a9a5030e266cc0652e35b61e55aaf3b134493667023950`; focused verification `test_seed_agent_memory.py` 39 passed. The separate `--apply` approval was later granted and closed by B2 below.

## 2026-06-13 L2 memory B2 seed apply

- Operator approved bounded DB write; PM ran `seed_agent_memory.py --apply` on Linux: run `l2_memory_b2_seed_apply_20260613T163835Z`, log `/tmp/openclaw/l2_memory_b2_seed_apply_20260613T163835Z.log`, sha256 `4b050252c803b193862d3758cf01d1ebb17fd907371369201e05f6764393a02c`.
- Result: A=6, B=93, inserted=99, already_present=0, recall verify en/zh hits=5/5. Post DB: `agent.agent_memory` total=99, duplicate_record_ids=0, active=99, embedding_pending=99; L2 memory pipeline/cron/embed/recall flags remained unset at B2 time; `[83]-[89]` PASS and engine PID 3607315 stayed alive. Manual V140 and FTS-only pipeline were later closed below; embed backfill/model-call/P2p/P5 remain separate gates.

## 2026-06-13 L2 V140 + FTS-only pipeline activation

- Operator instructed "V140 first, then L2"; PM applied manual V140 via `apply_manual_V140_agent_memory_vector.sh`: run `l2_manual_v140_apply_20260613T164628Z`, sha256 `3ccc6dc3ebcc69e0ee80027536a6d7d3325e6adc4a00d66279a45155bab07beb`; result `vector` extension 0.8.1 installed, `agent.agent_memory.embedding=vector(1024)`, HNSW index exists, sqlx head remains 139 by design.
- Activated L2 FTS-only daily cron: smoke run `l2_pipeline_ftsonly_smoke_20260613T164831Z` processed 2026-06-12 as no-op (`l2_calls=0`, DRAR=0, stored=0) and advanced cursor to 2026-06-12; cron install run `l2_memory_cron_install_20260613T164901Z` installed daily 05:23 UTC with `OPENCLAW_L2_MEMORY_PIPELINE=1`; active `[83]-[89]` PASS, `[88] rows=99 last_success=2026-06-12 lag_days=1`, `[89]` embed backfill OFF PASS-skip. `bge-m3` is absent in Ollama, so embedding backfill remains gated/off; engine PID 3607315 stayed alive.

## 2026-06-13 L2 embedding backfill activation

- Pulled `bge-m3` on Linux Ollama and ran bounded embedding backfill for seeded memory rows: `l2_embedding_backfill_20260613T170015Z`, sha256 `109aa15dcb540ce7428713b36628034ca9b53652c2caaf5ead88737c83aa8833`, result `embedded=99/status=ok`, probe dims=1024.
- Updated the existing L2 daily memory cron to include `OPENCLAW_L2_MEMORY_EMBED_BACKFILL=1`: `l2_memory_cron_embed_flag_20260613T170044Z`, sha256 `75de04eaf9e0434d984a99651b325e868ea3ece732f51246941708324303a33d`.
- Post DB: `agent.agent_memory` total=99, embedding_pending=0, embedding_not_null=99, dims=1024, meta=`ollama|bge-m3|1024`; Linux `[83]-[89]` PASS and focused source regression `94 passed`. No CI/deploy/rebuild/restart/B3/Gate-B/auth/risk/order/trading mutation; engine PID remained 3607315.

## 2026-06-13 L2 B3 recall source wiring

- Completed B3 recall source wiring for both mainline `layer2_engine` and guest-line `l2_ml_advisory_executor` via new `l2_memory_recall_context.py`. Flag contract is `OPENCLAW_L2_MEMORY_RECALL=0|shadow|1`: default `0` does no import/DB read, `shadow` computes bundle but only writes `memory_recall_shadow` metadata into existing D3 `input_context`, and `1` injects stable/recent blocks into prompt.
- Focused regression `92 passed` covering memory recall helper, `memory_distiller.recall`, D3 engine wiring, P3a ml_advisory, and P3b hypothesize. No CI/deploy/rebuild/restart/runtime flag enablement/DB/cron/Gate-B/auth/risk/order/trading mutation; engine PID remained 3607315 until a future deploy/restart.

## 2026-06-13 V5.8 pause readiness + alpha/edge handoff

- Added artifact-only `helper_scripts/research/v58_pause_readiness/` checker for V5.8 pause/resume: validates design/governance anchors, M1-M13 scaffold, freeze/unfreeze gate, V### numbering reality, LAL/M5/M12 fail-loud posture, and optional Gate-B watch context.
- True repo + Linux Gate-B latest run `v58_pause_local_20260613_r3` returned `PASS_PAUSE_READY` with 47 pass / 0 warn / 0 fail; Gate-B remained `WATCH_ONLY` with 0 alertable/start/schedule candidates and unfreeze gate `met=false`.
- Boundary: no CI/deploy/rebuild/restart/DB/auth/risk/order/trading mutation and no Gate-B probe. Future V5.8 active-IMPL remains frozen until AEG `stage0_ready`; rerun checker before pause/resume.

## 2026-06-18 TODO v164 hygiene

- TODO masthead restored to compact shape; v161-v163 long increment narrative moved to `docs/CLAUDE_CHANGELOG.md`, preserving active state in structured TODO sections.
- §5 stale cold-audit rows corrected: duplicate SCHEMA-1 removed, AUTH-1/PROFIT-1/DIRTY-FIX statuses aligned to deployed/healthcheck/true-table evidence. Boundary: docs-only, no runtime/code/DB/auth/risk/order mutation.

## 2026-06-18 AC19 expired cron cleanup

- Removed the expired `ac19_alt_bucket_daily_cron.sh` user-crontab line on Linux `trade-core` after read-only single-line match; backup saved at `/tmp/openclaw/backup/crontab_pre_ac19_cleanup_20260618T175129Z.txt`.
- Post-check confirmed 0 remaining crontab matches. Boundary: no code/deploy/rebuild/restart/DB/auth/risk/order/trading mutation.

## 2026-06-18 Phase2 verdict-casing reconcile

- Reconciled the §6 Phase2 promotion casing warning as stale: shared contract now canonicalizes `eligible` via `is_eligible()`, route uses that helper, Rust emits lowercase `verdict.tag()`, and the focused casing contract test passed.
- Full phase2 pytest under `/usr/local/bin/python3` was 21/23 with two `tomllib` false-reds from Python 3.10; local 3.12 has `tomllib` but no pytest. Boundary: read-only verification, no source/runtime mutation.

## 2026-06-18 runtime stale TODO reconcile

- Closed the stale `daily_cost_snapshot.sh` cron action: current Linux crontab has no `daily_cost_snapshot` line and repo/Linux still have no script, so there is no remaining cron deletion/rebuild action.
- Refreshed Gate-B watcher state: latest artifact generated `2026-06-18T17:42:01Z` is `WATCH_ONLY` with 21 total candidates, 0 alertable/start/schedule, and gate-watch-only preflight says `WAIT_FOR_ACTIONABLE_WATCH`. No probe/autostart/trading mutation.

## 2026-06-18 TODO closed-row archive pass

- Archived 8 no-action completed rows out of TODO §5: funding tilt NO-GO/no-reopen + 3LOW debt, orderLinkId #6/#6 follow-up, postmortem #7, OPS-2 D+14 soak observe, OPS-4 unit-test gap, and A1 basis wire.
- Kept rows that still have active deploy/operator/future-date/event-trigger gates. Boundary: docs hygiene only, no source/runtime mutation.

## 2026-06-18 TODO closed-row archive pass #2 + source sync

- TODO v169 archives five more no-action completed rows from §5: PERF-123, DIRTY-FIX, V5.8 pause readiness, P0-EDGE post-deploy QA A1/A2/B/A4, and CODE-SIMPLIFY-D no-reopen.
- Masthead/§0 now records prior docs checkpoint `e4e1b7a3` as Mac→GitHub→Linux `trade-core` fast-forward verified; no CI/deploy/rebuild/restart/source/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO operator archive pass

- TODO v170 compresses §6 operator actions by archiving six completed historical rows: V127 apply, AC19 cron cleanup, P5-SM step-i, P2 #6/#7, P2 #8 AST decision, and residual producer baseline done.
- Kept rows with real remaining gates: front levers, P2/L2 tails, Gate-B capture, OP-1/2/3, restore/systemd window, OPS-2 leftover auth/rotation, and residual PART4 activation decision. Boundary: docs hygiene only; no runtime mutation.

## 2026-06-18 TODO active queue archive pass #3

- TODO v171 archives `AUDIT-2026-06-14-MIGRATION-TREE-1` and `AEG-S2-EVIDENCE-AUTOMATION` from §5 because both are completed and their remaining relevance is carried by V###/PG discipline plus `AEG-S3-CANDIDATE-DIRECT-ROWS`.
- Kept DONE-ish rows that still carry policy, deploy, operator, future-date, event-trigger, or source-vs-runtime gates. Boundary: docs hygiene only; no runtime mutation.

## 2026-06-18 TODO OPS-2 cutover stale row reconcile

- TODO v172 removes stale §5 row `P1-OPS-2-PHASE-2-CUTOVER`: cutover commit `3018c7a3` is ancestor of runtime source HEAD `83b7632d` and current docs HEAD, Linux checkout contains it, and 2026-06-11 runtime note records operator-commanded `restart_all --rebuild` with OPS-2 cutover new binary active, 0 fallback string, and V137 applied.
- Remaining OPS-2 operator obligations are not closed: C-B manual `/auth/renew` evidence and 2026-09-08 rotation timing remain in TODO §6. Boundary: docs hygiene only; no CI/deploy/rebuild/restart/runtime mutation.

## 2026-06-18 TODO BB reversion regime observability SQL closure

- TODO v173 archives `P1-BB-REVERSION-REGIME-OBSERVABILITY` from §5 after post-deploy runtime evidence passed: source merge `6628b4cf` is ancestor of runtime source HEAD `83b7632d` and Linux checkout, production `trading.intents.details` is JSONB, and Linux read-only SQL for `bb_reversion` intents since `2026-06-11 02:00:00+00` returned n=10 with `hurst_label` 10/10 and `hurst_value` 10/10.
- This closes only the observability/key-presence acceptance. The 2026-06-27 bb_strategy sample-size/retire decision remains active under `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`; n<100 extension logic is unchanged. Boundary: read-only DB/source verification + docs hygiene only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO market_tickers forward-column SQL closure

- TODO v174 archives `P3-MARKET-TICKERS-INDEX-MARK-DEAD-PERSISTENCE` from §5 after post-engine-start SQL evidence passed. Current Linux engine PID 3134818 started `2026-06-18 14:11:50+02`; source checkpoint `5733eb06` is deployed through runtime source HEAD `83b7632d`; production `market.market_tickers` has nullable real `mark_price/index_price/open_interest/funding_rate`.
- Linux read-only SQL for `ts >= 2026-06-18 14:11:50+02` returned n=587319, mark_n=40912, index_n=84919, oi_n=5913, funding_n=719; mark/index/OI zero counts are 0, and funding_zero=8 is legitimate zero funding. This closes forward persistence/fake-zero evidence only; it does not backfill history or change 90d retention. Boundary: read-only DB/source verification + docs hygiene only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO funding/OI backfill completed-row archive

- TODO v175 archives `P0-EDGE-1-CAND-FUNDING-OI-BACKFILL` from §5. The completed state remains in TODO §2; active queue no longer needs a row whose only content was caveat/usage guidance.
- Linux read-only recheck confirmed `research.alpha_funding_rates_history` rows=46539 and `research.alpha_open_interest_history` rows=348153, single run_id `18b3c2f8-6125-42a8-a42c-cfcc8aec9406`, 0 NULL values. Caveat preserved: run-versioned schema is not idempotent on re-apply; future cron/refresh requires a new active row for clear-old-run/wrapper/rate-limit design. Boundary: docs hygiene + read-only SQL only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO 110017 convergence observability closure

- TODO v176 archives `P3-110017-CONVERGE-AUDIT-OBSERVABILITY` from §5 after Linux read-only DB evidence closed both deployment residual checks: 4 `trading.order_state_changes.reason LIKE 'exchange_zero_close_converge:%'` rows exist, and each had 0 follow-up orders for the same symbol+strategy within 63s and 5m after convergence.
- The row closed only D1 convergence observability/stop-timing. `P3-110017-D2-AUDIT-REMOVED-SEMANTICS` and `P3-110017-BB-DOC-FOLLOWUPS` remain active separately. Boundary: read-only DB/source verification + docs hygiene only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO incident-policy runtime deployment closure

- TODO v177 archives `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` from §5. Source chain was already closed at `26a72990`; this pass only closed the stale runtime activation gate by verifying `26a72990` is ancestor of runtime source marker `83b7632d`, running engine PID 3134818 contains the incident class/C4 dispatch strings, and watchdog PID 765009 started after current watchdog source mtime.
- Caveat preserved: no synthetic incident/drill, no real incident occurrence, and no alert-delivery proof is claimed. Future incident-class drills or alert-delivery checks need a new active row. Boundary: read-only runtime/source/DB/log introspection + docs hygiene only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 Reconciler runtime-status correction

- TODO v178 corrects stale `未部署` wording for `P2-RECONCILER-GET-POSITIONS-PAGINATION` / `P3-110017-D2-AUDIT-REMOVED-SEMANTICS`: `bb7e9efc`/`baf46a69` are in Mac/Linux HEAD and running engine PID 3134818 binary strings include `removed_position_semantics` / `dispatched-not-confirmed` / `reconcile_ghost_converge`.
- Rows stay active: PM 1-4 integration report still requires E2/E4/QA review, and production DB currently has 0 `observability.engine_events.event_type='reconcile_ghost_converge'` rows. Boundary: read-only source/runtime/DB verification + docs hygiene only; no CI/deploy/rebuild/restart/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 RetCode dictionary correction

- TODO v179 archives `P3-110017-BB-DOC-FOLLOWUPS`: Bybit reference now says 110017 D2 is source-land/runtime-loaded, not pending IMPL, and official Bybit V5 error table verifies 110009 as stop-orders-count limit rather than PositionNotFound.
- The remaining Rust drift is not hidden: `P2-110009-RETCODE-SEMANTICS-FIX` now tracks enum/test/comment rename plus removal/guarding of 110009 from the close-equivalent-success NoOp arm. Boundary: docs/TODO hygiene + official-doc verification only; no code/runtime mutation.

## 2026-06-18 TODO cold-audit completed-row archive

- TODO v180 archives `AUDIT-2026-06-14-AUTH-1` and `AUDIT-2026-06-14-PROFIT-1` from §5. AUTH-1 remains closed by cold-audit fix-wave/deploy; PROFIT-1 remains NO-FIX with passive_wait `[90]` sentinel.
- The future tails are preserved in §7, not hidden: Rust live-authz/direct-socket closure is a future operator architecture decision, and cost-gate double-deduct fix only reopens if explore-gate/Stage0R produces validated-positive cells or forward PnL proves released cells positive. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO schedule-only duplicate cleanup

- TODO v181 removes `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK` and `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` from §5 because both are passive scheduled reviews already carried by §7.
- §7 now contains the missing details: 2026-06-27 bb strategy baseline/retire/extend decision, and 2026-08-21 fallback dead-enum + halt root-cause review with `halt_audit.log` ready. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO SCHEMA-1 completed-row archive

- TODO v182 archives `AUDIT-2026-06-14-SCHEMA-1` from §5. The schema contract test and PR-only PG CI path remain in repo, while `audit_migrations.py` is explicitly informational-only.
- The derivative `MIGRATION-TREE-1` blocker is already closed/archived by v171 and future migration safety is carried by V### / Linux PG dry-run discipline. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO Stage0R replay preflight event-trigger relocation

- TODO v183 moves `P1-SPRINT2-STAGE0R-REPLAY-PREFLIGHT-DISPATCH` from §5 active queue to §7 passive schedule because the row has no current engineering action; it is now event-triggered.
- This is not a completion claim: 06-10 FA evidence still says 0 candidates satisfy AC-S2-A-3, A1/A2 demo are inactive with 0 fills, A1 basis wire is functional but candidate remains dormant (`n_eff=0` / `no_a1_signals_after_entry_gate`), and A2 remains NO-GO/observe_more.
- Reopen triggers preserved in §7: green Stage 0R preflight + operator demo-canary approval, first real AEG-S3 `candidate_regime_metrics` rows, residual Stage0R preflight flag-ON first run, or funding >30% APR + A1 entry-gate regime reappears; backstop remains 2026-06-27 with `P3-BB-STRATEGIES-30D-CATCH-UP-CLOCK`. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO SignalSpec conformance stale-defer relocation

- TODO v184 moves `P2-AST-SIGNALSPEC-CONFORMANCE` from §5 active queue to §7 conditional wait. The old defer reason was stale: `candidate_signal_spec_producer.py` and residual/hidden-OOS/manifest source now exist on main, and residual-producer baseline/operator history was archived in v170.
- This is not a checker completion claim and not a GO to implement. The remaining unblock condition is formal SignalSpec schema freeze plus PA/PM GO.
- Future thaw must preserve the corrected scope: build a `SignalSpec schema/lineage conformance checker`, not an expression-tree AST checker; true schema is a flat metadata manifest. Boundary: docs/status correction only; no source/runtime mutation.

## 2026-06-18 TODO tail deferred-debt relocation

- TODO v185 moves seven tail deferred/condition/cadence debt rows from §5 to §7: Packet C5 GUI ack, OPS-2 Sprint4 runbook bundle, LG-5 90d maturity review, LEASE-1 post-LG3 cleanup, Phase1B dynamic backoff, IntentType visibility refactor, and OPS-4 pg_dump/SOP cargo-test debt.
- This is not a DONE claim. §7 now carries the explicit wait conditions: Packet C4/failsafe role freeze, Sprint4 bandwidth/OPS-2 operator context, 90d reviewer maturity cadence, `P0-LG-3` closure, Phase 2a Demo PASS, PA builder-pattern spec, and SOP/on-demand bandwidth.
- §5 still keeps active/operator/action rows such as OP-1 dry-run, OPS-4 deploy, TOTP backend, A1/A2 runner, Earn Wave C/D, 110009 semantics, and other rows with current engineering/review gates. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO 110009 retCode semantics source fix

- TODO v186 archives `P2-110009-RETCODE-SEMANTICS-FIX` from §5 after source/test correction: `BybitRetCode::PositionNotFound` was renamed to `StopOrderLimitExceeded`, `from_code(110009)` maps to the new enum, and dispatch no longer classifies 110009 as close-equivalent NoOp.
- Official Bybit V5 meaning remains: 110009 = stop-order count exceeds maximum allowable limit. The fix makes 110009 Structural/fail-closed; 110001 stays NoOp and 110017 guarded convergence behavior is unchanged.
- Focused Rust tests passed: retCode tests (2), changed classifier/helper tests, and full `event_consumer::dispatch::tests` (56). Boundary: source/tests/reference/TODO/changelog/report only; no deploy/rebuild/restart, and running engine binary is not claimed to include the fix.

## 2026-06-18 TODO AC19 final-verdict active-row archive

- TODO v187 archives `P2-AC19-ALT-BUCKET-FINAL-VERDICT` from §5. The evidence/verdict work was already done: QA final verdict says alt FAIL (42 attempts, 23.8% fill, Wilson lower 13.5%, 28 timeout->taker), large_cap INCONCLUSIVE-LOW-N, and BB audit says demo public data mirrors mainnet while fills are pessimistic because demo orders have no queue position.
- Future α/β/C choice is now `P2-AC19-ALT-BUCKET-FINAL-VERDICT-FOLLOWUP` in §7: reopen only if PA/QC/operator chooses alt taker-direct, shortened timeout, or explicit keep-current-policy acceptance. Boundary: docs hygiene only; no code/runtime/DB/auth/risk/order/trading mutation.

## 2026-06-18 TODO P2/L2 activation owed operator-row archive

- TODO v188 removes the completed §6 operator row `P2 batch activation owed #2-#6`: V138/V139, B1/B2 seed, manual V140, L2 cron, bge-m3 embedding backfill, and B3 source wiring all have closure reports/evidence.
- This is not an L2 all-clear. Remaining L2 work stays visible in `P1-L2-ADVISORY-MESH-TAILS`, §8, and `L2_TODO.md`: first non-empty material day/E2E model-call evidence, B3 shadow runtime evidence, P2p sentinel operator gates, and P5 feedback/quality/GUI. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 TODO cold-audit P2/P3 batch active-row archive

- TODO v189 removes `AUDIT-2026-06-14-P2P3-BATCH` from §5. The Batch 4/5 fix-wave body is already completed/deployed by the cold-audit checkpoint, and its stale tails have since been split or closed: `daily_cost_snapshot.sh` v167, DIRTY-FIX v169, MIGRATION-TREE-1 v171, and 110009 semantics v186.
- Remaining policy/doc/perf tails are preserved in §7 as `P2-COLD-AUDIT-P2P3-BATCH-FOLLOWUP`: cost-edge re-gate decision, AI-PRICING option1 SSOT + `last_verified`, BB rate-limit dictionary doc hygiene, and PERF-1 1m minor follow-up. Boundary: docs hygiene only; no source/runtime mutation.

## 2026-06-18 Earn Wave D HMAC canonical-form checkpoint

- TODO v190 removes `P1-EARN-WAVE-D-RUST-HMAC-CANONICAL-FORM` from §5 after adding shared Rust/Python golden-vector coverage for Bybit REST V5 signing. The tests lock Earn GET sorted query bytes and Earn POST compact JSON body bytes to identical HMAC outputs in Rust `common::bybit_signer` and Python `BybitClient._sign`.
- Focused verification passed: Rust signer 2 tests and Python parity 2 tests. Remaining Wave D frontend -> backend -> Rust IPC integration test stays active as `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST`. Boundary: source/tests/docs only; no real Bybit call, credential mutation, deploy, runtime, DB, auth, risk, order, or trading mutation.

## 2026-06-18 TODO P5-SM completed-row relocation

- TODO v191 removes `P5-SM-OPTION2-CONVERGENCE` from §5. The active row was stale: `[82]` step-ii 48h soak had already passed on 2026-06-13T02:05:59Z, and later V138/V139, seed, V140, L2 cron, embedding backfill, and B3 source wiring superseded its old "not applied/not activated" caveats.
- This is not a P5-SM step-iii completion claim. Remaining `P5-SM step-iii CUTOVER sign-off` is preserved in §6 as an operator-gated action requiring operator sign-off plus CC/E2/BB/E4 review chain; docs hygiene only, no source/runtime mutation.

## 2026-06-18 Earn Wave D IPC contract checkpoint

- TODO v192 removes `P2-EARN-WAVE-D-CONTRACT-INTEGRATION-TEST` from §5 after source/test integration landed: Rust IPC dispatch registers `process_earn_intent`, sends `PipelineCommand::ProcessEarnIntent`, and the event-consumer owner task calls `IntentProcessor::process_earn_intent`; Python `/api/v1/earn/stake` now has a contract test locking method, timeout, and 8 params sent to Rust.
- Verification passed: `cargo test -p openclaw_engine process_earn_intent --lib` (3), `cargo test -p openclaw_engine earn_router_fail_closed_when_unwired --lib` (1), and full `test_earn_routes.py` (28, existing Pydantic warning only).
- Boundary preserved: no real Bybit call, no credential/secret mutation, no deploy/rebuild/restart, no runtime/DB/auth/risk/order/trading mutation. Current real Rust path intentionally returns `submitted=false` with `earn_dispatch_unwired...` until `BybitEarnClient` and `EarnMovementWriter` are injected; `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` stays active for OP-1/2/3 plus capability injection.

## 2026-06-18 P2 clippy cleanup gate

- TODO v194 closes `P2-CLIPPY-CLEANUP-1`: Apple Silicon `cargo clippy --target aarch64-apple-darwin -- -D warnings` now passes.
- Low-risk core/type lint errors were fixed directly; engine/bin historical lint debt is explicit at crate/bin boundaries so new unlisted lint classes still fail. Verification passed: clippy gate, core lib 412 passed, engine lib 4092 passed / 1 ignored.
- Boundary: source/tests/docs only; no CI full suite, deploy/rebuild/restart, runtime DB/auth/risk/order/trading mutation, credential mutation, or real Bybit call.

## 2026-06-18 H0Gate file split

- TODO v195 closes `P3-H0GATE-FILE-SPLIT`: `h0_gate.rs` moved its test module to `h0_gate/tests.rs`, reducing the production file from 1243 to 630 lines.
- Verification passed: H0 tests 33 passed, core lib 412 passed, Apple clippy gate, and engine `h0_latency_metrics` 5 passed.
- Boundary: source/tests/docs only; no CI full suite, deploy/rebuild/restart, runtime DB/auth/risk/order/trading mutation, credential mutation, or real Bybit call.

## 2026-06-18 Codex sub-agent hygiene dispatch rules

- TODO v196 closes `P3-SUB-AGENT-HYGIENE-SOP-CARGO-TEST-AFTER-ATOMIC`: Codex dispatch rules now require `docs/agents/sub-agent-hygiene-sop.md` for delegated Rust/Cargo/Linux-runtime/PG/deploy/runtime-verification work.
- Dispatch records must name `hygiene_sop`, `verification_surface`, and Linux write policy. E1/E2/E4 Rust tasks must report focused Mac cargo/source verification or an explicit skip reason; sub-agents remain barred from Linux cargo and unsupervised restart.
- Boundary: docs/governance only; no source code, CI, deploy/rebuild/restart, runtime DB/auth/risk/order/trading mutation, credential mutation, or real Bybit call.

## 2026-06-20 MLDE LinUCB / shadow timeout fix

- Production logs showed daily LinUCB and API scheduler MLDE reads timing out on the slow `learning.mlde_edge_training_rows` view path. LinUCB and shadow advisor now preserve the MLDE training-row contract while reading base tables directly, avoiding the `trading.signals` lateral bulk-decompress path.
- Routine LinUCB windows default to 30d with 5s timeout; remote read-only smoke of patched modules showed 30d all-arm LinUCB max arm 1.69s and shadow aggregate ~0.5s. Boundary: source/tests/docs only in this checkpoint; remote smoke was read-only and not an alpha promotion proof.

## 2026-06-20 fill_sim refresh guard + L1 stale diagnosis

- Added bounded `fill_sim_refresh_cron.sh` and installed Linux cron at 06:05 UTC. It writes candidate reports first and only replaces production fill_sim report when candidate has no abort, non-empty L1, non-empty symbols, and L1 data age <=72h. It prevents the failure observed this run: `HOURS=2` refresh produced empty L1 and initially overwrote production before the guard fix.
- `fill_sim.py` now records `l1_min_ts/l1_max_ts/l1_max_age_hours`; `recorder_mm_verdict_cron.sh` rejects empty/stale L1 data even when `generated_at` is fresh.
- Runtime recovery: explicit 90m post-fix window restored `/tmp/openclaw/research/fillsim/fillsim_report.json` with `l1_rows_post_filter=1,750,468`, fill_only `n=15,208`, adverse@15=1.477bp, net_maker@15=-4.701bp, `l1_max_age_hours=58.114`. Manual MM verdict then had `adverse_selection_usable=true`, sample=16, all symbol net edges still negative.
- Root blocker found: `market.l1_events` stopped at `2026-06-17 21:55:45+02` while trades/ob_top are fresh. `recorder_health_cron.sh` installed at 06:23 UTC and manual run appended `[RECORDER-HEALTH] recorder stalled` critical alert. Next PM target is L1 event recorder repair; without it, fill_sim data-age gate will disable adverse selection again around 72h from L1 max.

## 2026-06-20 L1 recorder persistence repair

- Root cause was restart env persistence: active engine had `OPENCLAW_RECORD_L1_EVENTS=` while `OPENCLAW_RECORD_TICKS=1`, so `market.trades` and `market.ob_top` stayed fresh but the L1 producer was OFF after restart.
- Fixed `helper_scripts/restart_all.sh` to read `OPENCLAW_RECORD_L1_EVENTS` and `OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL` from `basic_system_services.env` when parent env is absent; static regression covers the parent-only bug.
- Runtime repair on trade-core: set non-secret env-file keys `OPENCLAW_RECORD_L1_EVENTS=1`, `OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL=50`; engine-only `--keep-auth` restart, no rebuild/API restart/schema migration.
- Verification: new PID `4155643` env contains L1 flags; read-only PG showed `l1_max_ts=2026-06-20T02:19:20.531+02`, `l1_rows_5m=2635`, stale 0.027min. Formal `recorder_health_cron.sh` status: `l1_events.rows_24h=4566`, `stale_min=0.03`, crossed/locked 0.00.
- Boundary: source/test/docs + Linux non-secret env flag + engine-only restart and `/tmp/openclaw` logs/heartbeats only; no Bybit private/signed/trading call, no credential/auth/risk/order/trading mutation, no promotion proof.

## 2026-06-20 FlashDip shallow execution-realism checkpoint

- K6/N2/C3/nf0.5% remains a useful FlashDip research object, but its 2-day daily-exit demo-retune path is blocked by recent 1m execution-realism: 10bps buffer has 65 fills / 37 days but fixed-notional annret -2.49%, and all 0-50bps daily-exit buffers are negative.
- The same artifact shows the actionable next research seam: fee-adjusted short exits, especially 240m, are positive in the recent slice（0bps/240m annret 1.71%, 10bps/240m annret 1.29%）. Treat this as research-only; next gate is L1/orderbook replay plus QC/MIT/AI-E, not a parameter change.

## 2026-06-20 MM fee-path feasibility

- v253 adds `fee_path_feasibility` to `recorder_mm_verdict_cron.sh`: local 30d fills capacity proxy is now joined to the v252 maker fee sensitivity break-even. Linux isolated smoke showed `notional_usd=871,107.04`, `maker_notional_usd=496,419.84`, effective fee `3.6688bps`, and v252 break-even `1.028bp/side`.
- First standard Bybit derivatives VIP tier that clears that break-even is VIP5 (`1.0bp/side`), not VIP1-4; VIP5 is approximately `$250M/30d` derivatives volume or `$2M` asset balance, while current local volume proxy is only `0.348%` of that threshold and is not mainnet eligibility proof.
- PM read: fee reduction is a capital/scale/Bybit BD/MM-rebate path. Short-term engineering should keep searching for stronger signals/regime filters unless the operator explicitly pursues institutional/MM fee terms.

## 2026-06-20 MM walk-forward feature scorecard

- v254 adds `walk_forward_feature_scorecard` to fill_sim and MM verdict passthrough. Thresholds are selected on the first time half and replayed on the second half; only train+holdout sample-gated positive cells count as confirmed.
- Linux isolated 15m smoke `/tmp/openclaw/research/fillsim/fillsim_walk_forward_smoke_20260620T100549Z.json` sha256 `091eb93d6f653aa605941274134beff8d5a041c85b9577bc245636559c2364c2`: 139,391 L1 rows, 76,079 trades, 33 symbols, 51 candidates, status `NO_WALK_FORWARD_FEATURE_TRAIN_POSITIVE`. Best train cell `symbol=BCHUSDT` was still negative (train -2.061bp, holdout -1.429bp).
- PM read: simple PIT spread/imbalance/OFI/BTC-lead thresholding is not the missing short-term maker edge. Next work should be materially new signal/regime coverage or a non-MM path, not more in-window threshold overfitting.

## 2026-06-20 FlashDip L1 coverage action scorecard

- v286 adds `coverage_action_scorecard` to FlashDip L1 replay and alpha-discovery blocker rows. Current runtime evidence says the 6 missing candidate event windows ended before symbol L1 capture began, so this is a historical-before-capture wait state, not immediate recorder repair.
- Latest alpha remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`; FlashDip L1 next trigger is `wait_for_next_flash_dip_candidate_after_l1_capture_start_then_replay`. Treat this as research evidence routing only, not retune/promotion authority.

## 2026-06-20 FlashDip dependent L1 blocker propagation

- v287 propagates the L1 replay coverage-action scorecard into `flash_dip_execution_realism`. The parent execution-realism blocker now follows the child L1 wait state instead of claiming immediate engineering actionability.
- Latest alpha sha256 `05d0baa71008cc31024c0e58bbe86b5c98f50edae0919691ffaabd519f57a585` remains blocked, with `engineering_actionable_count=2`; FlashDip waits for a new candidate after L1 capture start, while Polymarket is near sample gate at 25/30.

## 2026-06-20 Polymarket sample-gate recheck scorecard

- v288 adds `sample_gate_recheck_scorecard` to alpha-discovery Polymarket blockers. Current runtime is no longer vague sample wait: 25/30 overlap-adjusted floor, `PERSISTENT_PRE_GATE_WATCHLIST`, floor-qualified persistent=2 / recurring=3.
- Latest alpha sha256 `c5832b2a371a6c0ea8564b2e321327bdb8d6ebedecf00c5ffab3a233617e89f0` says next trigger is `rerun_polymarket_leadlag_ic_after_sample_gate_eta_then_alpha_discovery` after `2026-06-20T19:52:02.074000+00:00`; not signal/candidate/promotion proof yet.

## 2026-06-20 AEG candidate artifact dependency scorecard

- v289 gates AEG robustness actionability on upstream `READY_FOR_AEG_CHAIN` / `READY_FOR_PROBE` / `artifacts_ready=true` artifacts. Empty candidate/probe pipeline now means AEG waits instead of consuming an engineering actionable slot.
- Latest alpha sha256 `f3aec25f6904681ce407e97f133dcfcb28629328115ebcbefbc616697d437c72` has `engineering_actionable_count=1`; AEG status `NO_CANDIDATE_ARTIFACTS_AVAILABLE_FOR_ROBUSTNESS`, candidate_artifact_count=0, next trigger `wait_for_candidate_or_probe_artifact_before_robustness_matrix`. Boundary: source/test/docs + read-only alpha artifact only; no trading/runtime mutation.

## 2026-06-20 MM current-fee cost-wall escape scorecard

- v290 adds `mm_cost_wall_escape_v1` to alpha-discovery MM blockers. Current fee round trip requires 4.0bp gross edge; best sample-gated gross edge is 2.27bp, gap 1.73bp, multiple 1.7621.
- Latest alpha sha256 `7a9f0e5005b4906ecbb6db3e4775d2cb2769654f5eac3310b4bdb8438bcff6bb` keeps `engineering_actionable_count=1`; lower-fee path remains scale/capital gated, so next trigger is `search_new_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip`.

## 2026-06-20 MM gross-edge near-miss ranking

- v291 adds `top_sample_gated_gross_cells` to MM gross-edge decomposition and alpha-discovery escape scorecard. Latest alpha sha256 `4dbbb4e964b1077f2b901a7d651b06c59d4cc3622c49b132e47b6b4f511c9583` lists top near misses: `LABUSDT` 2.27bp, `ADAUSDT` walk-forward holdout 2.002bp, quoted-half-spread train_p90 1.565bp.
- Current-fee threshold remains 4.0bp, so this is routing evidence for new low-friction signal search, not promotion proof or same-family retune authority.

## 2026-06-20 MM low-friction signal scorecard

- v292 adds recent-flow/L1-churn placement-time features and `low_friction_signal_scorecard` to fill_sim, then passes it through MM verdict and alpha-discovery. It also fixes oversized MM status JSON ingestion in `runtime_runner._latest_json_line`.
- Latest alpha sha256 `c87f9d538a1cf5dc7480d8d6f76e2048fe0278042812aa7dc725a9cea6890bba` reports best low-friction holdout `quoted_half_spread_bps train_p90 AND side_touch_size_delta_frac_30s train_p90`: gross 2.838bp, net -1.162bp, n=81. Current-fee threshold remains 4.0bp; not promotion proof.

## 2026-06-20 MM low-friction gross stability blocker

- v296 adds `low_friction_gross_stability_v1` inside alpha-discovery `mm_cost_wall_escape_v2`. It reads existing recorder gross decomposition and prevents a holdout-only low-friction near miss from being treated as train-confirmed MM signal.
- Latest alpha sha256 `d6e3a94c94919a564bc0d2667d3e8f229bc4a39e7c3c57cbc1efb6300990f5c2` remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`; best low-friction candidate train gross is `-0.225bp` / n=74 while holdout gross is `2.838bp` / n=81, so status is `LOW_FRICTION_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED`.
- Next trigger is now `search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip`. Boundary: source/test/docs + read-only alpha artifact only; no strategy, order, risk, runtime, engine, DB, or Bybit private mutation; not promotion proof.

## 2026-06-20 Polymarket AEG Candidate Review

- Polymarket lead-lag sample gate opened for `price_target|SOLUSDT|15m`: sample 30/30, HAC t `6.754`, BH q `3.378e-10`, partial IC `0.184`.
- Added fail-closed `polymarket_leadlag_ic` support to `aeg_candidate_metrics`; IC evidence carries candidate lineage/sample count only and does not become PnL/Sharpe/PSR/DSR evidence.
- Propagated `candidate_key=polymarket_leadlag_ic|price_target|SOLUSDT|15m` through candidate metrics, robustness matrix, and alpha runtime.
- Formal matrix result: `final_label_counts={"insufficient evidence":3}`, `coverage_gate_status=FAIL`, `execution_realism_mode=unverified_missing_missing`.
- Fixed alpha scorecard classification: once latest AEG matrix has reviewed the same candidate key with zero durable rows, Polymarket is downgraded from promotion-ready to `robustness_wait`.
- Latest alpha sha256 `0f31b41faa50ad144e4419ac0621d99caa93f695f6d40da3c3e20e0115caec9a`, `created_at_utc=2026-06-20T20:06:01.065368+00:00`, status `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, promotion-ready `0`.
- Next trigger: build candidate-specific PnL, breadth, and execution-realism evidence before any promotion discussion.
- Boundary: source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact writes only; read-only PG SELECT for regime artifact; no PG write/schema migration, Bybit private/signed/trading call, engine/API restart, credential/auth/risk/order/strategy mutation, or promotion proof.

## 2026-06-21 MM quiet-notional low-friction search

- v301 adds existing PIT `recent_trade_abs_qty_10s/30s` to the MM low-friction search, including high-spread x quiet-notional combos and `spread_quiet_abs_qty_interaction_v1` three-way candidates.
- Runtime result after Linux forced 2h fill_sim refresh: the new surface is searched but still below current fee. Best quiet-notional train-confirmed interaction min gross is `1.234bp`, gap `2.766bp`; global best train-confirmed min gross is `1.521bp`, gap `2.479bp`.
- Latest alpha sha256 `da105c37b2ba0c6565bfeebeb974a865df486685d4368d71ccedcac49c4030d4` remains `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`. Best sample-gated gross cell is `2.647bp` / n=33 / net `-1.353bp`, but train leg n=28 and gross `0.541bp`, so the blocker remains `LOW_FRICTION_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED`.
- Polymarket has moved past the previous price-catch-up blocker to `IC_READY_NO_SIGNIFICANT_EDGE`, candidate_count=0. Do not chase Polymarket unless new evidence or a new family appears.
- Boundary: artifact-only source/test/docs + selective Linux source sync + `/tmp/openclaw` artifact/status writes; read-only PG via existing wrappers; no engine/API restart, no Bybit private/signed/trading call, no strategy/risk/order/auth mutation, not promotion proof.

## 2026-06-22 Demo-Learning Activation Packet Alpha Ingestion

- v408 wires `demo_learning_stack_activation_packet_v1` into the alpha runtime and autonomous-learning worklist. The packet is no longer just a standalone operator artifact; `runtime_runner.py` emits `alpha_discovery_runtime_killboard_v8`, `discovery_loop.py` maps packet states into Cost Gate learning blockers, and `learning_worklist.py` emits `alpha_learning_worklist_v5` with packet evidence.
- The current intended blocker is specific: `demo_learning_stack_activation_packet_ready_for_operator_dry_run`, not generic `demo_learning_stack_not_installed`. This carries missing crons, dry-run/apply/rollback/verify commands, edge-amplification levers, and no-authority answers into the worklist.
- Verification: Mac py_compile and focused alpha/worklist pytest `62 passed`; source commit `277b00be` pushed `[skip ci]`; Linux fast-forwarded to `277b00be`; Linux py_compile and same pytest `62 passed`; Mac/Linux `git diff --check` clean.
- Boundary: source/test/docs + Linux source sync/read-only/static tests only; no CI, no cron install, no PG write/schema migration, no Bybit private/signed/trading call, no deploy/restart, no env/auth/risk/order/strategy/runtime mutation, no Cost Gate lowering, no probe/order authority, no promotion proof.

## 2026-06-22 Alpha Cron Activation Packet + Source Cleanliness

- v409 makes the v408 activation-packet ingestion durable in the natural alpha cron path: `alpha_discovery_throughput_cron.sh` refreshes canonical `demo_learning_stack_activation_packet_latest.json` before the alpha runner.
- v409 also moves the volatile vol-event robust-ruling latest report out of tracked docs by default and into `$OPENCLAW_DATA_DIR/order_flow_alpha/vol-event-robust-ruling.md`; `OPENCLAW_VOL_EVENT_RULING_REPORT_PATH` is now the explicit archival override.
- Runtime smoke on Linux after source sync produced packet `READY_FOR_OPERATOR_DRY_RUN`, alpha `alpha_discovery_runtime_killboard_v8`, source `SYNCED_CLEAN`, worklist `alpha_learning_worklist_v5`, top task `cost_gate_learning_activation`, and blocker `demo_learning_stack_activation_packet_ready_for_operator_dry_run`.
- Verification: Mac bash/py_compile passed; Mac cron tests `6 passed`; Mac research alpha/worklist/vol-event tests `64 passed`; source commit `2d4bad29` pushed `[skip ci]`; Linux fast-forwarded to `2d4bad29`; Linux same checks `6 + 64 passed`; Linux artifact-only cron smoke passed and source remained clean.
- Boundary: source/test/docs + Linux source sync + `/tmp/openclaw` artifact-only smoke only; no CI, no new cron install, no PG write/schema migration, no Bybit private/signed/trading call, no deploy/restart, no env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, no promotion proof.

## 2026-06-22 Demo-Learning Stack Dry-Run Review Alpha Ingestion

- v410 adds `demo_learning_stack_dry_run_review_v1`: a no-authority artifact that runs the stack installer only with `OPENCLAW_DEMO_LEARNING_STACK_CRON_APPLY=0`, captures rc/stdout/stderr tails, and proves the dry-run preview does not mutate crontab.
- `alpha_discovery_throughput_cron.sh` now refreshes activation packet, then dry-run review, then alpha runtime. `runtime_runner.py`, `discovery_loop.py`, and `learning_worklist.py` surface passed/failed dry-run preview state.
- Runtime smoke on Linux after source sync produced dry-run status `DRY_RUN_PREVIEW_PASSED_OPERATOR_APPLY_REVIEW_REQUIRED`, rc `0`, `forced_apply_gate=0`, `mutates_crontab=false`, alpha source `SYNCED_CLEAN`, worklist status `OPERATOR_GATED_LEARNING_READY`, and blocker `demo_learning_stack_dry_run_preview_passed_operator_apply_review_required`.
- Verification: Mac bash/py_compile passed; Mac cron tests `9 passed`; Mac research alpha/worklist tests `64 passed`; source commit `5eb46806` pushed `[skip ci]`; Linux fast-forwarded to `5eb46806`; Linux same checks `9 + 64 passed`; Linux artifact-only cron smoke passed and source remained clean.
- Boundary: source/test/docs + Linux source sync + `/tmp/openclaw` artifact-only smoke only; no CI, no cron install, no PG write/schema migration, no Bybit private/signed/trading call, no deploy/restart, no env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, no promotion proof.

## 2026-06-22 Learned Cost Gate Review Candidate Priority

- v411 changes alpha/worklist priority so real `DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT` blocked-outcome evidence supersedes the dry-run apply gate. The worklist now points to operator review of the learned side-cell, not infrastructure activation, when both are present.
- Linux artifact-only Cost Gate learning refresh produced `ledger_row_count=52419`, `blocked_signal_outcome_count=22419`, and top candidate `ma_crossover|ETHUSDT|Sell` with `wrongful_block_score=75.4927` and `net_cost_cushion_bps=37.7464`.
- Runtime alpha smoke after source sync produced top task `operator_probe_review`, objective `operator_review_top_blocked_signal_side_cell_before_bounded_demo_probe`, `requires_operator_authorization=true`, and `runtime_mutation_required=false`; no Cost Gate/order/probe authority was granted.
- Verification: Mac py_compile passed; Mac alpha/worklist tests `65 passed`; source commits `51e3e520` and `9768b3dd` pushed `[skip ci]`; Linux fast-forwarded to `9768b3dd`; Linux same checks `65 passed`; Linux artifact-only refresh/smoke passed and source remained clean.
- Boundary: source/test/docs + Linux source sync + `/tmp/openclaw` artifact-only refresh/smoke only; no CI, no cron install, no PG write/schema migration, no Bybit private/signed/trading call, no deploy/restart, no env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, no promotion proof.

## 2026-06-22 Multi-Horizon Cost Gate Learning Review Path

- v412 makes the Cost Gate learning cron default to multi-horizon scorecards (`15,30,60,120,240`) and carries horizon-stability evidence through the profit-learning decision packet into alpha/worklist.
- Runtime read-only counterfactual latest reports `MULTI_HORIZON_PROFIT_LEARNING_CANDIDATES_PRESENT`; top candidate `ma_crossover|ETHUSDT|Sell` is `CANDIDATE_MULTI_HORIZON_STABLE` across all five horizons, best horizon `120m`, best avg net `121.1121bp`, net-positive `100.0%`, sample `10074`.
- Alpha smoke after source sync reports top objective `operator_review_multi_horizon_blocked_signal_side_cell_before_bounded_demo_probe`, matched cell horizons `[15,30,60,120,240]`, `requires_operator_authorization=true`, `runtime_mutation_required=false`, and order/probe authority false.
- Remaining gate: decision packet still records `DATA_FLOW_MONITOR_REQUIRED`; this candidate is reviewable but not tradeable until data-flow, bounded demo probe authorization, matched-control result review, and execution-realism evidence are complete.
- Verification: Mac/Linux focused decision/alpha/worklist tests `71 passed`; cron static `13 passed`; source commits `65278ca9`, `aed33504`, `1f7180a1` pushed `[skip ci]`; Linux source clean at `1f7180a1`; read-only multi-horizon scorecard refresh, packet refresh, and alpha smoke passed.

## 2026-06-22 Cost Gate Data-Flow Packet Refresh Cron

- v413 wires demo data-flow monitor + profit-learning decision packet refresh into `cost_gate_learning_lane_cron.sh`, so the learning lane now auto-records whether rejects are present, whether silent-drop risk exists, and whether blocked side-cells are ready for operator review.
- Linux smoke initially failed on a missing optional sealed-evidence artifact; source now treats absent optional packet inputs as `MISSING` and still emits a fail-closed packet.
- Latest runtime evidence: data-flow `DEMO_ORDER_FLOW_PRESENT_NO_FILLS`, `broad_cost_gate_rejects=58968`, `broad_orders=3`, `broad_fills=0`, decision packet `OPERATOR_REVIEW_DEMO_PROBE_CANDIDATES`, `silent_drop_risk=false`, alpha top task `operator_probe_review`; no Cost Gate lowering, probe/order authority, runtime mutation, or promotion proof.

## 2026-06-22 Shadow Placement Impact Alpha Ingestion

- v418 wires `bounded_demo_probe_shadow_placement_impact_v1` into `alpha_discovery_runtime_killboard_v9`, `alpha_learning_worklist_v6`, and `profitability_engineering_closure_v1`.
- Evidence priority is now result-review/execution-realism first, then shadow placement, then older blocked-review candidate; current shadow sample still proves mechanical touchability only, not candidate alpha.
- Mac and Linux related suites both passed `107/107`; source commit `f0d422b2` was pushed `[skip ci]` and fast-forwarded on `trade-core` cleanly. No Cost Gate lowering, probe/order authority, deploy/restart, PG write, Bybit private call, or CI run.

## 2026-06-23 Bounded Probe Near-Touch Adapter Module

- v423 adds Rust `openclaw_engine::bounded_probe_near_touch`, a pure no-authority Adapter Module for future bounded Demo post-only near-touch-or-skip placement.
- Readiness now separates Adapter Module presence from tick-dispatch authority-path wiring; canonical Linux smoke returned `RUST_PATCH_REQUIRED_AUTHORITY_PATH_WIRING_MISSING` with Adapter present true and wiring present false.
- Verification passed Mac/Linux Python bounded suites `18/18`, Mac/Linux Rust focused Adapter tests `7/7`, and Linux `/tmp/openclaw` artifact smoke. No Cost Gate lowering, probe/order authority, deploy/restart, PG write, Bybit private call, or CI run.

## 2026-06-24 Profit Evidence Proof-Exclusion Guard

- Added centralized source-only proof exclusion for unattributed or lineage-incomplete fill-backed rows. Such rows now remain raw audit telemetry but cannot count toward bounded-probe proof, Cost Gate proof, promotion evidence, or risk-adjusted net PnL proof.
- Bounded result review, execution realism review, learning-lane status, runtime adapter state, artifact spine, scorecard/runtime/discovery/worklist propagation now split raw/proof-eligible/proof-excluded outcomes and fail closed when exclusion is present.
- Verification: py_compile passed for changed modules; bounded/status/runtime/scorecard tests `112 passed`; alpha discovery/worklist tests `90 passed`; `git diff --check` clean.
- Boundary: source/test/docs only. No Bybit private call, order cancel/modify/close, PG action, runtime/env/service/cron mutation, Cost Gate lowering, probe/order authority, live promotion, or Rust writer enablement.

## 2026-06-24 Source-Only Fill-Lineage Guard

- Commit `66f063cc` adds Rust event-consumer dispatch-response orderId mapping, stale-map unattributed fallback, and lifecycle cleanup for future fill attribution/reconstructability.
- Review chain PA/E2/E4/QA passed; focused Rust test `pending_registration_order_type_tests` passed 26/26 and `git diff --check` clean.
- Boundary: source-only guard, not deployed/runtime lineage closure, candidate selection, bounded-probe proof, Cost Gate proof, or promotion proof; P0 exchange cleanup/quarantine remains operator-gated.

## 2026-06-24 API Service Env-Parity Packet

- `api_service_env_parity.py` now makes manual uvicorn vs inactive systemd unit drift reviewable from supplied snapshots only; current runtime smoke is `API_SERVICE_ENV_PARITY_DRIFT`.
- E2/E3/E4 chain passed after PM fixed missing-env false-clean, env/service mutation contamination, and command-line secret/key redaction gaps.
- Boundary: source/test/docs + supplied `/tmp` snapshot smoke only; no service restart/process/env/crontab mutation, no PG/Bybit call, no Cost Gate change, no probe/order/live authority, and no promotion proof.

## 2026-06-24 API Service Runtime Cutover No-Apply Plan

- `api_service_env_parity.py` now embeds `api_service_runtime_cutover_plan_v1` with proposed ExecStart, safe env materialization, preflight/apply/rollback/verification templates, and hard `apply_allowed=false` / `restart_allowed=false`.
- E2 found and PM fixed direct `DATABASE_URL`/`DSN` leakage risk and `python -m uvicorn` wrapper reconstruction; E3 no-apply review and E4 regression passed.
- Boundary: source/test/docs + supplied `/tmp` snapshot smoke only; no systemd apply, daemon-reload, process signal, service restart, API/env/crontab mutation, PG/Bybit call, Cost Gate change, probe/order/live authority, or promotion proof.

## 2026-06-24 API Service Enablement Review

- Fresh read-only enablement review after cutover shows `openclaw-trading-api.service` active/running but disabled; parity is `API_SERVICE_ENV_PARITY_CLEAN_SOURCE_ONLY`, bind is Tailscale-only, health returns `401`, `Linger=yes`, and no default-target wants symlink exists.
- E3 returned `DONE_WITH_CONCERNS`: future `systemctl --user enable openclaw-trading-api.service` is acceptable only as a separate PM/E3 runtime mutation checkpoint using enable without `--now`; this packet grants no enable authority.
- Boundary: source/read-only evidence + docs only; no enable/disable/restart/daemon-reload/process signal, no API POST/Bybit/PG write, no Cost Gate change, no probe/order/live authority, no Rust writer, no promotion proof.

## 2026-06-24 Shadow Placement Authority-Readiness Next Action

- `P1-BOUNDED-PROBE-SHADOW-PLACEMENT-NEXT-ACTION-RECONCILE` closed as source-only `DONE_WITH_CONCERNS`.
- Fresh runtime evidence showed shadow placement still emitted `operator_review_mechanical_touchability_before_rust_patch` while authority readiness was already `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW` and `rust_patch_required=false`.
- `bounded_probe_shadow_placement_impact.py` now optionally consumes `bounded_demo_probe_authority_patch_readiness_v1` and only moves next actions to exact-authorization/candidate-matched evidence when readiness is fresh, ready, answer-self-consistent, Adapter/wiring present, and no authority/proof/mutation contamination exists.
- E2 found fail-open risks before commit; PM fixed them by expanding authority-key checks, scanning nested/list inputs, requiring readiness answers to match ready status, and splitting matched-sample next action into authorization-only first action.
- `cost_gate_learning_lane_cron.sh` now passes same-cycle readiness into shadow placement; runtime copied-artifact smoke produced `authority_path_ready_for_operator_review=true` and next actions `collect_candidate_matched_bounded_demo_probe_evidence_after_exact_authorization` / `rerun_shadow_placement_after_candidate_matched_flow`.
- Boundary: source/test/docs + copied-artifact smoke only; no Bybit call/order/cancel/modify, no PG write, no crontab/service mutation, no Cost Gate lowering, no probe/order/live authority, no Rust writer, no promotion proof.

## 2026-06-24 Alpha Cron Expected-Head Runtime Closure

- `P1-ALPHA-CRON-RUNTIME-RUNNER-EXPECTED-HEAD-PROPAGATION` closed as `DONE_WITH_CONCERNS`.
- Source commit `44a337e3` makes `alpha_discovery_throughput_cron.sh` pass expected-head into `runtime_runner` from `OPENCLAW_EXPECTED_SOURCE_HEAD`, `OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD`, or `OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD`.
- E2 caught the Bash 3.2 `set -u` empty-array regression; final source uses explicit `if/else` and a subprocess wrapper test with fake `PYBIN` for empty-env and demo-stack-env paths.
- Runtime fast-forwarded cleanly `7d118e81 -> 44a337e3`; demo-learning expected-head pins changed old SHA `10 -> 0` / new SHA `0 -> 10`.
- E3 separately approved alpha natural cron line 57 adding only `OPENCLAW_EXPECTED_SOURCE_HEAD=44a337e3...`; total crontab lines stayed `70`, new SHA count is `11`, old SHA `0`, and `OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0` remains with `=1` absent.
- Cron-shape alpha wrapper refresh at `2026-06-24T14:52:50Z` reports `expected_head_status=MATCH`, runtime source `SYNCED_CLEAN`, `runtime_probe_authority_found=false`, `runtime_order_authority_found=false`, `promotion_evidence_found=false`, `cost_gate_mutation_found=false`, and `actionable_probe_semantics=OPERATOR_REVIEW_READY_NO_RUNTIME_AUTHORITY`.
- Anti-repeat note: do not repeat expected-head propagation or killboard authority-semantics refresh without new source/runtime/artifact delta. Legacy `ready_for_probe=1` is review readiness, not authority.

## 2026-06-25 Bounded Probe Active Proof Reconstruction Contract

- `P0-BOUNDED-PROBE-ACTIVE-CALLER-RESTART-OUTCOME-PROOF-CONTRACT-DEMO-ONLY` closed as source-only `DONE_WITH_CONCERNS`. Active bounded Demo dispatch now has an active-specific reference source, pending-order registration preserves signal timestamp and Decision Lease id, and non-close active orders can emit a candidate-matched `active_bounded_probe_proof_key` into audit details.
- Result-review proof exclusion now rejects active-sourced rows without a valid active proof key. Validation is deliberately Rust-equivalent: exact demo/live_demo mode, positive signal timestamp, active reference source, stable side-cell/context/signal/Decision Lease/orderLinkId fields, candidate-bound orderLinkId hash/shape, and row side-cell/orderLinkId consistency. `details.reference_source` is checked even when top-level source is generic.
- Anti-repeat note: do not rerun the proof/reconstruction-contract slice without new source/runtime/artifact evidence. The next distinct source-only blocker is actual `adapter_enabled=true` active caller enablement review plus post-restart reconciliation; this checkpoint grants no runtime adapter enablement, order/probe authority, Cost Gate lowering, live promotion, or promotion proof.

## 2026-06-25 Bounded Probe Active Caller Enablement Readiness Split

- `P0-BOUNDED-PROBE-ACTIVE-CALLER-ENABLEMENT-REVIEW-DEMO-ONLY` closed as source-only `DONE_WITH_CONCERNS`. The readiness packet now distinguishes seam readiness from actual enablement: legacy `active_order_submission_ready` may be true, but current repo has `active_caller_source_ready_for_review=false`, `active_caller_enablement_ready=false`, and `active_caller_enablement_authority_granted=false`.
- Scanner fail-closed coverage now rejects cfg(test)/string-only/unused helper/unused dispatch calls, hardcoded adapter gates including typed bools, unrelated env reads, wrapped env reads, and env-read blocks that return hardcoded booleans. Actual enablement remains false until runtime source sync, reviewed adapter gate, E3/BB envelope, and post-restart pending-order reconciliation evidence exist.
- Anti-repeat note: do not repeat source/actual readiness split without a new source/runtime/artifact delta. Next distinct blocker is PM->E3/BB runtime-source/admission propagation review, not a Demo order, not adapter enablement, and not promotion proof.

## 2026-06-26 AVAX Runtime Admission E3/BB Review + TODO Hygiene

- `P0-BOUNDED-PROBE-AVAX-RUNTIME-ADMISSION-E3-BB-REVIEW-DEMO-ONLY` closed as read-only `DONE_WITH_CONCERNS`: E3/BB allow only opening the next separate runtime source-sync/post-restart reconciliation/adapter-enablement review checkpoint.
- TODO v527 now has one selected WAITING next blocker and a compact no-repeat AVAX ladder; `P0-PROFIT-DEMO-LEARNING-LOOP` is no longer an executable active row.
- Boundary unchanged: no runtime sync, no Bybit call/order/cancel/modify, no PG write, no `_latest` overwrite, no restart/crontab/env mutation, no adapter enablement, no Cost Gate lowering, no probe/order/live authority, no promotion proof.

## 2026-06-26 AVAX Runtime Source + Cron Expected-Head Sync

- Runtime source checkout is now clean at `d2cd70d0`; learning cron expected-head pins also point at `d2cd70d0` after exact 11-token SHA replacement.
- Engine PID `2432529` and API MainPID `2218842` did not change; no restart/rebuild, no PG/Bybit/order/cancel/modify, no adapter/writer enablement, no Cost Gate lowering, no proof/authority.
- Next PM read: adapter/restart/order path is blocked by health/reconciliation, especially demo resting exposure `working_n=6` and about `691 USDT`; start with `P0-PROFIT-EVIDENCE-QUALITY-DEMO-RESTING-EXPOSURE-RECONCILIATION-E3-BB-REVIEW`.

## 2026-06-27 Demo Fast-Balance Runtime Diagnostics

- `demo_fast_balance_equity_artifact.py` now has optional runtime diagnostics for snapshot metadata and Bybit Demo secret-slot metadata without reading secret contents; focused/adjacent GUI-cap tests passed.
- Fresh `trade-core` artifact `/tmp/openclaw/demo_fast_balance_runtime_diagnosis_20260627T091742Z/demo_account_equity_artifact_runtime_diagnosed.json` is READY (`rust_snapshot_fast`, connected, equity `9551.36942603`, no runtime blockers), superseding the stale disconnected artifact.
- GUI risk remains percentage-authority: `10.0%` resolves to `955.1369426 USDT` at this equity and max-single-position `25%` resolves to `2387.84235651 USDT`; runtime source drift still blocks actual-admission.

## 2026-06-29 External Repo Read-Only Fusion Implementation

- Implemented `docs_context_retrieval`, `aeg_report_audit`, and `external_repo_fusion_smoke` as read-only advisory helpers; retrieval score is relevance-only and audit statuses are advisory-only.
- Verification: py_compile PASS, focused tests `40 passed`, adjacent AEG `9 passed`, M4 leakage `52 passed`, smoke `EXTERNAL_REPO_FUSION_SMOKE_COMPLETE` with 2544 chunks and authority preserved.
- Boundary remains no Bybit/DB/network/runtime/order/risk/config/Decision Lease/writer/Cost Gate/promotion/sizing authority; use outputs only as PM/FA/QC/Operator redlines.
- Linux deploy: `trade-core` fast-forwarded to `523fcb48`, atomic engine rebuild/restart verified PID `877736` with binary SHA `c867c89cfbbde8f02a5ef6cf985a629aa8eeb544784dab6d7b883f4435854be0`, then API-only reload PID `878457`; live authorization was absent and preserved absent.

## 2026-06-29 Learning Engine Completion Engineering Plan

- PM integrated QC/MIT/AI-E/PA read-only review: DreamEngine is active advisory-only; general learning is partially alive but degraded/core-loop stalled due empty runtime crontab, stale health, ML maintenance error, stale registry, and missing fill-backed proof.
- Next engineering order is `P0-LEARN-HEALTH-SSOT`, then ledger event contract, proposal compiler, adjudicator, Demo mutation envelope, training/registry repair, serving snapshot, and proof/promotion gate; no runtime mutation or live authority granted.
- Triple adversarial audit hardened the plan: completion now requires contract versioning/tests, negative authority tests, operations runbook, budget/backpressure gates, and mandatory legacy retirement; learning-engine completion is plausible if these gates pass, but alpha profitability remains empirical proof-gate output.

## 2026-06-29 Learning Stack Health SSOT Source Checkpoint

- PM advanced `P0-LEARN-HEALTH-SSOT` source-only at commit `f2a827c2`: new `learning_stack_health_snapshot_v1` aggregates scheduler, demo-health, ML maintenance, registry/artifact, ledger/parity, and fill-backed proof inputs while keeping all mutation/order/live/Cost Gate authority false.
- Verification passed: py_compile, focused snapshot tests `7 passed`, adjacent demo-learning healthcheck + snapshot tests `19 passed`, and `git diff --check`.
- Next ML loop item is `P0-LEARN-LEDGER-EVENT-CONTRACT`; runtime install/cron repair/Demo mutation remains blocked until source contracts and gated reviews pass.

## 2026-06-29 LearningEvent Contract Source Checkpoint

- PM advanced `P0-LEARN-LEDGER-EVENT-CONTRACT` source-only at commit `6b93cf2a`: new `cost_gate_learning_event_contract_v1` wraps `probe_ledger.jsonl` and explicit artifact JSON into deterministic `cost_gate_learning_event_v1` packets with event ids, source refs/hashes, candidate identity, generated timestamp, proof tier, and quarantine.
- `blocked_signal_outcome` / `market_markout_proxy_for_blocked_signal` rows are explicitly labeled `blocked_markout_proxy`; authority-bearing input fails closed and emits no events.
- Verification passed: py_compile, focused LearningEvent tests `7 passed`, adjacent learning-lane tests `19 passed`, and `git diff --check`.
- Next ML loop item is `P0-LEARN-PROPOSAL-COMPILER`; PG cutover, runtime install, Demo mutation, training/registry repair, serving, and proof/promotion remain blocked until their separate source contracts and gated reviews pass.

## 2026-06-29 Learning Proposal Compiler Source Checkpoint

- PM advanced `P0-LEARN-PROPOSAL-COMPILER` source-only at commit `7cfec46e`: new `cost_gate_learning_proposal_compiler_v1` groups `cost_gate_learning_event_v1` events by candidate id and emits deterministic review-only proposal candidates.
- Candidate proposals carry evidence windows, event/proof-tier counts, source event ids/hashes, upstream quarantine propagation, and authority contamination fail-closed behavior.
- `blocked_markout_proxy` remains review/context evidence only: `blocked_markout_proxy_counts_as_fill_backed_proof=false`, fill-backed proof readiness false, promotion proof readiness false.
- Verification passed: py_compile, focused compiler tests `6 passed`, adjacent learning-lane tests `25 passed`, and `git diff --check`.
- Next ML loop item is `P0-LEARN-ADJUDICATOR`; PG cutover, runtime install, Demo mutation, training/registry repair, serving, and proof/promotion remain blocked until their separate source contracts and gated reviews pass.

## 2026-06-29 Learning Adjudicator Source Checkpoint

- PM advanced `P0-LEARN-ADJUDICATOR` source-only at commit `300ee0af`: new `cost_gate_learning_adjudicator_v1` consumes compiled proposal candidates and emits deterministic review-only decisions.
- Decision packets carry deterministic decision ids, rank, labels `REVIEW` / `DEFER` / `REJECT`, proof-tier eligibility gates, source event hashes, upstream quarantine propagation, and authority contamination fail-closed behavior.
- `blocked_markout_proxy` remains defer/context evidence only, not fill-backed proof; fill-backed proof readiness, Demo mutation readiness, and promotion proof readiness remain false.
- Verification passed: py_compile, focused adjudicator tests `6 passed`, adjacent learning-lane tests `31 passed`, post-external-change rerun `19 passed`, and `git diff --check`.
- Next ML loop item is `P0-LEARN-DEMO-MUTATION-ENVELOPE`; PG cutover, runtime install/mutation, training/registry repair, serving, and proof/promotion remain blocked until their separate source contracts and gated reviews pass.

## 2026-06-29 Learning Demo Mutation Envelope Source Checkpoint

- PM advanced `P0-LEARN-DEMO-MUTATION-ENVELOPE` source-only at commit `ed54bf93`: new `cost_gate_learning_demo_mutation_envelope_v1` consumes adjudicator decisions plus optional bounded Demo runtime readiness and emits deterministic inert operator-gated envelopes.
- Envelopes preserve operator/runtime gates, credential/mode blockers, standing-auth/final-window requirements, source event ids/hashes, quarantine propagation, and authority contamination fail-closed behavior.
- `blocked_markout_proxy` remains context/defer evidence only; Demo mutation authority, runtime mutation authority, order authority, Cost Gate change authority, and promotion proof remain false even when runtime readiness is green.
- Verification passed: py_compile, focused envelope tests `7 passed`, adjacent learning-lane/runtime-readiness tests `31 passed`, wider adjacent learning-lane tests `43 passed`, and `git diff --check`.
- Next ML loop item is `P0-LEARN-TRAINING-REGISTRY-REPAIR`; runtime mutation, PG cutover/write, serving, bounded Demo execution, and proof/promotion remain blocked until their separate source contracts and gated reviews pass.

## 2026-06-29 Learning Training/Registry Repair Source Checkpoint

- PM advanced `P0-LEARN-TRAINING-REGISTRY-REPAIR` source-only at commit `1a8cedb3`: new `cost_gate_learning_training_registry_repair_v1` consumes `learning_stack_health_snapshot_v1` and emits deterministic repair items for ML maintenance, model registry, ONNX/registry freshness, artifact/PG parity, and legacy artifact retirement.
- Repair items include source refs, budget/backpressure gates, operator runbook, rollback plan, and `allowed_actions` false for training, ONNX export, registry/PG write, artifact delete, runtime/env/service/cron mutation, serving, Cost Gate change, order/live authority, and promotion proof.
- Verification passed: py_compile, focused repair tests `5 passed`, health snapshot `7 passed`, registry freshness + repair `14 passed`, ML chain adjacent `48 passed`, and `git diff --check`; a wider wrapper static test still has an existing repo-venv/mock-PATH environment failure outside this helper.
- Next ML loop item is `P0-LEARN-SERVING-SNAPSHOT`; runtime mutation, PG/registry write, model serving/load, bounded Demo execution, and proof/promotion remain blocked until separate source contracts and gated reviews pass.

## 2026-06-29 Learning Serving Snapshot Source And Runtime Checkpoint

- PM advanced `P0-LEARN-SERVING-SNAPSHOT` at commit `f1d1a26c`: new `cost_gate_learning_serving_snapshot_v1` consumes training/registry repair, learning health, model registry summary, and optional runtime serving state artifacts.
- The packet emits immutable candidate/blocked review packets requiring no remaining repair items, registry/ONNX parity, q10/q50/q90 artifact hashes, feature schema hash, stale/legacy artifact exclusion, and runtime loaded-version agreement or explicit visible fallback with hidden ML inference rejected.
- Runtime `trade-core` is synced clean at `f1d1a26c19954a79d28014f75451c4a882f8d450` with learning cron expected-head pins repinned; engine PID `877736` stayed running with Demo-only bounded-probe env and no restart.
- Verification passed: local py_compile, focused serving tests `10 passed`, local adjacent learning/readiness suite `46 passed`, runtime py_compile, runtime adjacent suite `46 passed`, and `git diff --check`.
- Runtime serving snapshot `/tmp/openclaw/session_loop_state_20260629T_serving_snapshot/learning_serving_snapshot_after_f1d_sync.json` sha `83ac78520c9739b17378ddc1d88f3150237a36a1e96b87a236cf6eca7bbeb68d` is `LEARNING_SERVING_SNAPSHOT_BLOCKED_BY_TRAINING_REGISTRY_REPAIR_NO_AUTHORITY`; readiness sha `8f9da6b...` remains blocked by Demo key/mode.
- Next ML loop item is `P0-LEARN-PROOF-PROMOTION-GATE`; model load/serving, registry/PG write, bounded Demo execution, Cost Gate change, and proof/promotion remain blocked until separate gated reviews pass.

## 2026-06-29 IBKR Phase 0 Contract Packet

- PM materialized ADR-0048, AMD-2026-06-29-01, and `stock_etf_cash_phase0_named_contract_packet_v1` for IBKR read-only / paper / shadow research only.
- Stable boundary wording now preserves Bybit as the only active live execution venue while adding IBKR `stock_etf_cash` as an ADR-gated paper/shadow exception; IBKR live/tiny-live/margin/short/options/CFD/transfer remain denied.
- Next allowed work is Phase 1 source foundation only: closed type/config/schema/IPC reservations, default-OFF readiness parsing, source-only DDL, fixture lifecycle, and denial tests; no IBKR API/secret/connector/runtime/evidence clock.

## 2026-06-29 Learning Proof/Promotion Gate Source Checkpoint

- PM advanced `P0-LEARN-PROOF-PROMOTION-GATE` source-only at commits `ad43b638` and `ed8c3595`: new `cost_gate_learning_proof_promotion_gate_v1` consumes serving snapshot, learning adjudicator, candidate proof-evidence, and optional proof-exclusion artifacts.
- The gate emits deterministic blocked/ready operator-review verdicts requiring ready serving snapshot, matching adjudicator `REVIEW`, row-backed candidate-matched Demo fills, fee/slippage/spread/capacity/net evidence, execution realism, tail risk, OOS/repeat validation, matched controls/baseline outperformance, serving/model agreement, and proof-exclusion pass.
- Hardened coverage ensures summary counts alone cannot clear proof and cleanup/replay-only/unattributed/lineage-broken rows stay proof-excluded; outputs never grant promotion, Cost Gate, runtime, model load, serving, registry/PG, order, or live authority.
- Verification passed: py_compile, focused proof/promotion tests `11 passed`, ML source chain tests `52 passed`, health snapshot tests `7 passed`, and `git diff --check`.
- ML source contract chain is complete through proof/promotion gate; actual proof remains blocked by serving repair state, Demo credential/mode readiness, and missing row-backed candidate-matched Demo fills.

## 2026-06-30 IBKR Stock/ETF Instrument Identity Contract

- PM added `instrument_identity_contract_v1` as a Rust source-only validator for point-in-time Stock/ETF/Cash identity, closed venue/currency/tradability/PRIIPs states, calendar/contract-detail/corporate-action hashes, and Bybit-live-unchanged/live-denied proof.
- The contract rejects crypto/CFD, unknown venues, non-USD v1 currency, untradable instruments, prior IBKR contact, and secret serialization.
- This grants no IBKR contact, contract-details call, market-data subscription, connector runtime, paper order, DB apply, evidence clock, GUI lane authority, release, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF PIT Universe Contract

- PM added `stock_etf_pit_universe_contract_v1` as a Rust source-only validator for point-in-time universe id/version/hash/as-of/effective window, bounded constituents, per-constituent identity/tradability/PRIIPs/currency/venue checks, screen/policy hashes, survivorship controls, and evidence-clock freeze state.
- The contract rejects crypto/CFD/cash constituents, unknown or cash-ledger venues, non-USD v1 currency, untradable constituents, missing PIT/hash/survivorship/freeze evidence, prior IBKR contact, and secret serialization.
- This grants no IBKR contact, market-data collection, connector runtime, paper order, DB apply, scorecard write, evidence clock, GUI lane authority, release, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Strategy Hypothesis Contract

- PM added `stock_etf_strategy_hypothesis_contract_v1` as a Rust source-only validator for preregistered Stock/ETF paper/shadow hypotheses, allowed low/medium-turnover families, daily/weekly timeframe, PIT universe/benchmark/cost/rule/feature/statistical/preregistration hashes, bias controls, and benchmark-relative after-cost metrics.
- The contract rejects high-frequency/event-driven reserved families, intraday v1 timeframe, missing design controls, over-high turnover, premature profitability claims, live/tiny-live claims, prior IBKR contact, and secret serialization.
- This grants no IBKR contact, collector runtime, paper order, DB apply, scorecard write, evidence clock, profitability claim, GUI lane authority, release, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Lane-Scoped IPC Contract

- PM added `lane_scoped_ipc_v1` as a Rust source-only validator for the exact `stock_etf.*` IPC method matrix, required paper-effect gates, request fields, typed denials, and Rust ownership.
- The contract rejects unknown/Bybit paper IPC methods, direct Python broker write authority, existing Bybit paper path reuse, missing gates/fields/denials, prior IBKR contact, connector runtime, and secret serialization.
- This grants no IPC runtime, IBKR contact, connector runtime, paper order, DB apply, scorecard write, evidence clock, GUI lane authority, release, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Scorecard Input Contract Hardening

- PM hardened Phase 3 scorecard input source contracts so cash ledger, cost model, benchmark, shadow fill, and storage capacity require exact named `contract_id` values plus `source_version=1`.
- The derived-only bundle now requires market-data provenance, reference-data source, and risk-policy contract hashes, preserves Bybit-live unchanged proof, and rejects IBKR contact, connector runtime, broker fill import, scorecard writer, DB apply, evidence-clock start, serialized secrets, and tiny-live/live authority.
- Broker capability registry and lane-scoped IPC now use shared scorecard contract constants for relevant gates; the blocked template is expanded and remains secret-free.
- Verification passed: focused linked openclaw_types tests `30 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `173` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, fill import, scorecard writer, DB apply, evidence clock, GUI lane authority, paper order, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Evidence-Clock Contract Hardening

- PM hardened `stock_etf_evidence_clock_v1` day evidence so the checker requires exact contract id/source version, `stock_etf_cash` / IBKR lane binding, read-only/paper/shadow environment, source artifact hash, market-data provenance contract hash, and scorecard input bundle hash.
- The checker now preserves Bybit-live unchanged proof and rejects checker-side IBKR contact, connector runtime, runtime evidence-clock start, scorecard writer, DB apply, serialized secrets, and tiny-live/live authority. `WINDOW_COMPLETE` remains rejected by the source checker alone.
- Broker capability registry, lane-scoped IPC, Phase 0 manifest, exports, and the blocked Phase 3 template now use the shared evidence-clock contract constant.
- Verification passed: focused linked openclaw_types tests `33 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `174` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, evidence clock, collector, scorecard writer, DB apply, GUI lane authority, paper order, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF Release/Tiny-Live Contract Hardening

- PM hardened `stock_etf_release_packet_v1` and `tiny_live_adr_eligibility_v1` so release packets require exact `packet_id == stock_etf_release_packet_v1` plus `source_version=1`, and tiny-live ADR eligibility requires exact `contract_id == tiny_live_adr_eligibility_v1` plus `source_version=1`.
- The Phase 0 manifest validator now consumes shared release/tiny-live contract constants; blocked templates expose `source_version=0`; regression tests reject old `_fixture` ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `21 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `176` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, evidence clock, scorecard writer, DB apply, GUI lane authority, paper order, ADR start, tiny-live, or live.

## 2026-06-30 IBKR Stock/ETF GUI Lane Contract Hardening

- PM hardened `gui_lane_contract_v1` so GUI lane contract artifacts require exact `contract_id == gui_lane_contract_v1` plus `source_version=1`.
- The Phase 0 manifest validator now consumes the shared GUI lane contract constant; the blocked template exposes `source_version=0`; regression tests reject the old `_fixture` id and wrong source versions.
- Verification passed: focused linked openclaw_types tests `14 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `177` integration/acceptance + `0` doc-tests. This grants no GUI runtime authority, IBKR contact, connector runtime, DB apply, evidence clock, paper order, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Asset-Lane Audit Event Hardening

- PM hardened `audit.asset_lane_events_v1` so asset-lane event references require exact `schema_version == audit.asset_lane_events_v1` plus `source_version=1`.
- The Phase 0 manifest validator now consumes the shared audit event contract constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like schema ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `15 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `178` integration/acceptance + `0` doc-tests. This grants no audit writer, DB apply, IBKR contact, connector runtime, evidence clock, paper order, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Broker Capability Registry Hardening

- PM hardened `broker_capability_registry_v1` so registry artifacts require exact `registry_id == broker_capability_registry_v1` plus `source_version=1`.
- The Phase 0 manifest validator and `lane_scoped_ipc_v1` paper/preview gates now consume the shared broker registry contract constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like registry ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `22 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `179` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, paper order, evidence clock, scorecard writer, DB apply, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Lane-Scoped IPC Hardening

- PM hardened `lane_scoped_ipc_v1` so IPC contract artifacts require exact `contract_id == lane_scoped_ipc_v1` plus `source_version=1`.
- The Phase 0 manifest validator and IPC paper-effect self-gates now consume the shared lane-scoped IPC contract constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like IPC ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `14 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `180` integration/acceptance + `0` doc-tests. This grants no IPC runtime, IBKR contact, connector runtime, paper order, evidence clock, scorecard writer, DB apply, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Instrument Identity Hardening

- PM hardened `instrument_identity_contract_v1` so instrument identity artifacts require exact `contract_id == instrument_identity_contract_v1` plus `source_version=1`.
- The Phase 0 manifest validator, broker capability contract-details gate, and `lane_scoped_ipc_v1` paper/preview gates now consume the shared instrument identity constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like identity ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `31 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `181` integration/acceptance + `0` doc-tests. This grants no IBKR contract-details call, market-data subscription, connector runtime, IPC runtime, paper order, evidence clock, scorecard writer, DB apply, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF PIT Universe Hardening

- PM hardened `stock_etf_pit_universe_contract_v1` so PIT universe artifacts require exact `contract_id == stock_etf_pit_universe_contract_v1` plus `source_version=1`.
- The Phase 0 manifest validator, broker capability shadow/scorecard gates, and `lane_scoped_ipc_v1` preview/shadow gates now consume the shared PIT universe constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like PIT universe ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `30 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `182` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, market-data collection, IPC runtime, paper order, evidence clock, scorecard writer, DB apply, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Strategy Hypothesis Hardening

- PM hardened `stock_etf_strategy_hypothesis_contract_v1` so strategy hypothesis artifacts require exact `contract_id == stock_etf_strategy_hypothesis_contract_v1` plus `source_version=1`.
- The Phase 0 manifest validator, broker capability shadow/scorecard gates, and `lane_scoped_ipc_v1` shadow gates now consume the shared strategy hypothesis constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like strategy ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `30 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `183` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, market-data collection, IPC runtime, paper order, evidence clock, scorecard writer, DB apply, GUI authority, profitability claim, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Risk Policy Hardening

- PM hardened `stock_etf_risk_policy_v1` so risk-policy artifacts require exact `contract_id == stock_etf_risk_policy_v1` plus `source_version=1`; dormant source-config conversion emits source version 1 while preserving config version.
- The Phase 0 manifest validator now consumes the shared risk policy constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like risk-policy ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `31 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `184` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, IPC runtime, paper order, market-data collection, evidence clock, scorecard writer, DB apply, GUI authority, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF DB Evidence DDL Hardening

- PM hardened `stock_etf_db_evidence_ddl_v1` so DB evidence DDL artifacts require exact `contract_id == stock_etf_db_evidence_ddl_v1` plus `source_version=1`.
- The Phase 0 manifest validator now consumes the shared DB evidence DDL contract constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like DB DDL ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `14 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `185` integration/acceptance + `0` doc-tests. This grants no DB apply, PG write, sqlx migration registration, migration authorization, IBKR contact, connector runtime, evidence clock, scorecard writer, GUI authority, paper order, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Disable Cleanup Runbook Hardening

- PM hardened `stock_etf_kill_switch_and_disable_cleanup_runbook_v1` so disable/cleanup runbook artifacts require exact `runbook_id == stock_etf_kill_switch_and_disable_cleanup_runbook_v1` plus `source_version=1`.
- The Phase 0 manifest validator now consumes the shared disable/cleanup runbook constant; the blocked template exposes `source_version=0`; regression tests reject fixture-like runbook ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `13 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `186` integration/acceptance + `0` doc-tests. This grants no service stop, DB mutation, destructive cleanup, secret-slot creation, IBKR contact, connector runtime, paper order, evidence clock, GUI authority, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Reference Data Sources Hardening

- PM hardened `stock_etf_reference_data_sources_v1` so reference-data artifacts require exact `contract_id == stock_etf_reference_data_sources_v1` plus `source_version=1`; the blocker is now explicit `SourceVersionMismatch`.
- The Phase 0 manifest validator now consumes the shared reference-data contract constant; the blocked template exposes and tests `source_version=0`; regression tests reject fixture-like reference-data ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `12 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `187` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, reference-data ingestion, scorecard writer, DB apply, evidence clock, GUI authority, paper order, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Market Data Provenance Hardening

- PM hardened `stock_market_data_provenance_v1` so market-data provenance artifacts require exact `contract_id == stock_market_data_provenance_v1` plus `source_version=1`.
- The Phase 0 manifest validator now consumes the shared market-data provenance contract constant; the blocked template exposes and tests `source_version=0`; regression tests reject fixture-like provenance ids and wrong source versions.
- Verification passed: focused linked openclaw_types tests `19 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `188` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, collector start, market-data ingestion, scorecard writer, DB apply, evidence clock, GUI authority, paper order, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Phase2 Contract Constants Hardening

- PM converged remaining Phase 0 / Phase 2 named contract ids into shared Rust constants for asset-lane taxonomy, external surface gate, non-Bybit API allowlist, API session topology, session attestation, feature-flag/secret/auth matrix, paper lifecycle, lifecycle event log, paper attestation, and redaction policy.
- Phase 0 manifest, broker capability registry gates, lane-scoped IPC gates, and audit event fixtures now consume shared constants where this does not create reverse module coupling; validation semantics are unchanged.
- Verification passed: focused linked openclaw_types tests `63 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `188` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, collector start, market-data/reference-data ingestion, scorecard writer, DB apply, evidence clock, GUI authority, paper order, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Lifecycle Hardening

- PM hardened paper lifecycle evidence so `BrokerLifecycleEventLogV1` now requires exact `lifecycle_contract_id == ibkr_paper_order_lifecycle_v1`, exact `event_log_contract_id == broker_lifecycle_event_log_v1`, and `source_version=1`.
- The blocked lifecycle template exposes empty ids plus `source_version=0`; regression tests reject fixture-like lifecycle/event-log ids and wrong source versions while preserving state-transition and append-only evidence checks.
- Verification passed: focused linked openclaw_types tests `32 passed`; full `cargo test -p openclaw_types` `35` unit/golden + `189` integration/acceptance + `0` doc-tests. This grants no IBKR contact, connector runtime, IPC runtime, paper order, fill import, audit writer, DB apply, evidence clock, GUI authority, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Phase 2 Pre-Contact Identity Hardening

- PM hardened Phase 2 pre-contact contracts so external-surface gate, API session topology, session attestation, feature-flag/secret/auth matrix, and prerequisite policies require exact named contract ids plus `source_version=1`.
- Blocked external-surface/runtime/auth templates expose empty ids plus `source_version=0`; policy prerequisite templates carry exact policy ids/source versions but remain non-authorizing source prerequisites, not PASS artifacts.
- Verification passed: focused Phase 2 openclaw_types tests `32 passed`; linked tests `62 passed`; full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` `35` unit/golden + `191` integration/acceptance + `0` doc-tests; `cargo check --manifest-path rust/Cargo.toml --workspace` passed. This grants no IBKR contact, secret-slot creation, connector runtime, paper order, fill import, audit writer, DB apply, evidence clock, GUI authority, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Phase 2 Artifact + Secret Identity Hardening

- PM hardened the remaining pre-contact artifact chain: `IbkrPhase2GateArtifactV1` now requires exact `contract_id == phase2_ibkr_external_surface_gate_v1` plus `source_version=1`, and `IbkrSecretSlotContractV1` requires exact `contract_id == ibkr_secret_slot_contract_v1` plus `source_version=1`.
- The blocked gate artifact template now exposes empty ids/source-version 0 for artifact, embedded gate, secret-slot, and topology sections; the blocked runtime contract template also exposes empty secret-slot id/source-version 0.
- Verification passed: focused openclaw_types tests `23 passed`; linked tests `63 passed`; full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` `35` unit/golden + `192` integration/acceptance + `0` doc-tests; `cargo check --manifest-path rust/Cargo.toml --workspace` passed. This grants no IBKR contact, secret inspection, secret-slot creation, connector runtime, paper order, fill import, audit writer, DB apply, evidence clock, GUI authority, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Non-Bybit API Allowlist Hardening

- PM added `NonBybitApiAllowlistV1` in `ibkr_non_bybit_api_allowlist`: exact `contract_id == non_bybit_api_allowlist_v1`, `source_version=1`, and complete read / paper-write / denied coverage for all 23 IBKR non-Bybit API actions.
- The validator ties bucket membership to `classify_non_bybit_api_action`, rejects Client Portal/live/account-write/margin/short/options/CFD/entitlement/contact/secret/Bybit-regression drift, keeps the blocked template at empty id plus `source_version=0`, and splits allowlist code out of the Phase 2 gate module.
- Verification passed: focused gate `10 passed`; linked IBKR/Phase0 `65 passed`; full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` `35` unit/golden + `194` integration/acceptance + `0` doc-tests; `cargo check --manifest-path rust/Cargo.toml --workspace` passed. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, audit writer, DB apply, evidence clock, GUI authority, release, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF IPC Readiness Allowlist Trace

- PM wired Stock/ETF engine IPC readiness to expose `phase2.api_allowlist` with exact `non_bybit_api_allowlist_v1` id/version, accepted verdict, action counts, no-contact/no-secret flags, and Bybit-live protected proof.
- The external-surface gate remains blocked because there is still no immutable PASS artifact, no real secret/topology evidence, and no first-contact authorization; legacy `submit_paper_order` behavior remains on the existing channel path.
- Verification passed: engine IPC focused `4 passed`; engine `stock_etf` filtered `5 passed`; linked openclaw_types `18 passed`; `cargo check --manifest-path rust/Cargo.toml --workspace` passed. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Readiness Allowlist Gate

- PM made the Stock/ETF FastAPI readiness route normalize `phase2.api_allowlist` into top-level `api_allowlist` and fail closed on missing/mismatched `non_bybit_api_allowlist_v1` id, source version, action counts, contact/secret flags, or missing Bybit-live protection proof.
- IPC unavailable remains the existing degraded/fail-closed state rather than being reclassified as an IPC payload contract violation; integer contract fields reject boolean values.
- Verification passed: `python3 -m py_compile` for the route/test files and focused FastAPI/no-write pytest `12 passed`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Allowlist Readiness Trace

- PM made the display-only Stock/ETF GUI tab render the normalized `api_allowlist` readiness payload: accepted/blocked status, contract id/source version, action counts, no-contact/no-secret flags, Bybit-live protection proof, and allowlist blockers.
- Allowlist blockers are merged into the existing denied/blocker surface; static tests assert the tab consumes `api_allowlist` while preserving no POST, no paper order method, and no local/session storage authority.
- Verification passed: route test `py_compile`, focused FastAPI/no-write pytest `12 passed`, Node inline-script syntax check `2` scripts, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Static GUI No-Write Guard

- PM extended the Stock/ETF IBKR no-write guard to the static GUI tab, requiring `/api/v1/stock-etf/readiness` and rejecting POST/PUT/PATCH/DELETE snippets, `ocPost`, direct `fetch`, forms, browser storage lane authority, IBKR broker-write strings, and Stock/ETF write IPC strings.
- The guard is intentionally scoped to `tab-stock-etf.html` so existing Bybit paper/live GUI surfaces are not reclassified as IBKR violations.
- Verification passed: guard test `py_compile`, focused FastAPI/static no-write pytest `13 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Route Cache Auth Partition

- PM made Stock/ETF readiness and tab redirect responses emit no-store/private cache headers plus `Vary: Authorization`.
- Route tests prove query/header supplied lane, paper-ready, and first-contact claims are ignored: the API still calls only `stock_etf.get_readiness` with empty params and trusts the Rust IPC payload.
- Verification passed: route/test `py_compile`, focused FastAPI/static no-write pytest `14 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Route Method Partition

- PM added a source-only route-method negative-test checkpoint asserting the Stock/ETF OpenAPI surface exposes only `GET /api/v1/stock-etf/readiness`.
- Runtime negative tests assert `POST`, `PUT`, `PATCH`, and `DELETE` return `405` for both `/api/v1/stock-etf` and `/api/v1/stock-etf/readiness`; the existing static no-write guard remains in force.
- Verification passed: route test `py_compile`, focused FastAPI/static no-write pytest `16 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Lane Status Read-Only Surface

- PM added display-only `GET /api/v1/stock-etf/lane-status`, calling only Rust IPC `stock_etf.get_lane_status` with empty params and no-store/private cache headers.
- Lane-status normalization fail-closes to default `crypto_perp`, Stock/ETF/IBKR display identity, `display_only` GUI authority, no paper-order entry, no IBKR live, and no first-contact allowance; route tests prove query/header lane/paper/contact claims are ignored.
- Verification passed: route/test `py_compile`, focused FastAPI/static no-write pytest `21 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Lane Status Read-Only Render

- PM made `tab-stock-etf.html` consume display-only `GET /api/v1/stock-etf/lane-status` alongside readiness and render lane-status state plus feature flags in the Lane Boundary panel.
- Static guards now require both read-only endpoints while continuing to reject direct `fetch`, POST/PUT/PATCH/DELETE snippets, forms, browser storage lane authority, broker-write strings, and Stock/ETF write IPC strings.
- Verification passed: GUI guard `py_compile`, focused FastAPI/static no-write pytest `21 passed`, Node inline-script syntax check `2` scripts, and `git diff --check`. This grants no login-success lane selector, GUI/lane authority, IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust Lane Status IPC Regression

- PM added direct Rust IPC coverage for `stock_etf.get_lane_status`: phase2 precontact fixture identity, Stock/ETF/IBKR lane binding, mirrored default lane/flag state, typed feature-flag booleans, and safety fields false.
- The test asserts Phase 2 remains blocked, first IBKR contact false, connector disabled, API allowlist identity/version present, no IBKR contact performed, and no secret serialization.
- Verification passed: `rustfmt --edition 2021`, focused lane-status cargo test `1 passed`, filtered `openclaw_engine stock_etf` cargo test `6 passed`, focused FastAPI/static no-write pytest `21 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Redirect Auth Partition

- PM made `GET /api/v1/stock-etf` tab redirect require the same authenticated actor dependency as the Stock/ETF read APIs.
- Added a negative test proving unauthenticated redirect access returns `401`; existing method tests still prove Stock/ETF API routes are GET-only and reject POST/PUT/PATCH/DELETE.
- Verification passed: route/test `py_compile`, focused FastAPI/static no-write pytest `22 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF IPC Method Registry Boundary

- PM made Stock/ETF IPC fixture boundaries explicit in Rust method-registry tests: lane-status/readiness/preview/import/shadow methods remain read-only fixtures.
- Stock/ETF submit/cancel/replace paper methods stay visibly non-readonly, require no global IPC slot, do not enter the Bybit live-write token surface, and do not alias legacy paper method names.
- Verification passed: `rustfmt --edition 2021`, focused registry cargo test `1 passed`, filtered `openclaw_engine stock_etf` cargo test `7 passed`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, paper order, fill import, DB apply, GUI/lane selector authority, Phase 2 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Evidence Status Read-Only Surface

- PM added Rust IPC read-only fixture `stock_etf.get_evidence_status`, registry/dispatch coverage, and a blocked `phase3_evidence_status_source_fixture` from existing market-data provenance/evidence-clock contracts.
- FastAPI now exposes authenticated no-store `GET /api/v1/stock-etf/evidence-status`, calls only that IPC method with empty params, ignores client-supplied state, fail-closes on IPC errors, and converts Phase 3/contact/secret/order/scorecard/DB/Bybit IPC side-effect signals into contract violations while top-level authority fields remain false.
- `tab-stock-etf.html` renders the Evidence Status panel from the read-only endpoint; static guards require lane-status/readiness/evidence-status and still reject write methods, direct `fetch`, forms, browser storage lane authority, direct IBKR broker writes, and Stock/ETF write IPC strings.
- Verification passed: `rustfmt --edition 2021`, filtered `cargo test --manifest-path rust/Cargo.toml -p openclaw_engine stock_etf` `8 passed`, route/static `py_compile`, focused pytest `27 passed`, Node inline-script syntax `checked 2 inline scripts`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, evidence clock runtime, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2 start, Phase 3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Storage Capacity Guard

- PM hardened `stock_etf_storage_capacity_v1` so Phase 3 evidence cannot start from an unbounded storage plan: max `1,000` instruments, max `5,000,000` rows/day, max `8,192` MB index budget, max `5,000` ms query SLO, raw payload hash retention at least `365` days, compressed retention not shorter than raw-hash retention and not above `3,650` days, and archive paths restricted to relative `evidence/stock_etf_cash/...`.
- Acceptance tests now reject unbounded volume, slow query SLO, retention-order violations, and unsafe/cross-lane/archive traversal paths; the Phase 0 named contract packet documents the same guard.
- Verification passed: `rustfmt --edition 2021`, scorecard inputs `12 passed`, Phase0 manifest `6 passed`, Phase3 evidence `13 passed`, full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` `35` unit/golden + `181` integration/acceptance + `0` doc-tests, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, evidence clock runtime, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2 start, Phase 3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Contract Endpoint Hardening

- PM updated `gui_lane_contract_v1` to require three exact display-only GET surfaces: `/api/v1/stock-etf/readiness`, `/api/v1/stock-etf/lane-status`, and `/api/v1/stock-etf/evidence-status`.
- Added lane-status/evidence-status constants, GET-only fields, endpoint mismatch blockers, blocked template fields, and acceptance coverage; the Phase 0 named contract packet now documents the three-endpoint GUI surface.
- Verification passed: `rustfmt --edition 2021` on GUI contract source/test, GUI contract `9 passed`, Phase0 manifest `6 passed`, FastAPI/static guard pytest `27 passed`, full `cargo test --manifest-path rust/Cargo.toml -p openclaw_types` `35` unit/golden + `182` integration/acceptance + `0` doc-tests, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, evidence clock runtime, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2 start, Phase 3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Universe Status Read-Only Surface

- PM added display-only `GET /api/v1/stock-etf/universe-status` backed by Rust IPC fixture `stock_etf.get_universe_status`, exposing blocked PIT universe contract status from local source types only.
- GUI and `gui_lane_contract_v1` now require the universe-status GET-only surface alongside readiness/lane/evidence; static guards still reject write routes, direct broker writes, browser storage authority, and Stock/ETF paper-order IPC strings.
- Verification passed: openclaw_engine `stock_etf` `9 passed`, FastAPI/static pytest `32 passed`, Node inline scripts `2`, full `openclaw_types` `35` unit/golden + `198` integration/acceptance + `0` doc-tests, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, collector/evidence clock, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2/3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Shadow Status Read-Only Surface

- PM added display-only `GET /api/v1/stock-etf/shadow-status` backed by Rust IPC fixture `stock_etf.get_shadow_status`, exposing blocked shadow-fill-model and strategy-hypothesis contract status from local source types only.
- GUI and `gui_lane_contract_v1` now require the shadow-status GET-only surface alongside readiness/lane/evidence/universe; static guards still reject write routes, direct broker writes, browser storage authority, and Stock/ETF paper-order IPC strings.
- Verification passed: openclaw_engine `stock_etf` `10 passed`, FastAPI/static pytest `37 passed`, Node inline scripts `2`, full `openclaw_types` `35` unit/golden + `198` integration/acceptance + `0` doc-tests, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, shadow collector, shadow signal/fill generation, evidence clock, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2/3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Account Status Read-Only Surface

- PM added display-only `GET /api/v1/stock-etf/account-status` backed by Rust IPC fixture `stock_etf.get_account_status`, exposing blocked account cash-ledger, session-attestation, and paper-attestation policy status from local source types only.
- GUI and `gui_lane_contract_v1` now require the account-status GET-only surface alongside readiness/lane/evidence/universe/shadow/paper/reconciliation; static guards still reject write routes, direct broker writes, browser storage authority, and Stock/ETF paper-order IPC strings.
- Verification passed: route/normalizer/test `py_compile`, openclaw_engine `stock_etf` `13 passed`, FastAPI/static pytest `52 passed`, GUI/lane IPC focused `17 passed`, Node inline parser PASS, `rustfmt --check`, and `git diff --check`. This grants no IBKR contact, connector runtime, secret access, account snapshot, portfolio snapshot, cash ledger retrieval, broker paper attestation, paper order, fill import, lifecycle writer, scorecard writer, DB apply, GUI/lane selector authority, Phase 2/3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Scorecard Verdict Contract

- PM added `stock_etf_scorecard_verdict_v1`, a source-only Rust validator and blocked TOML template for the Phase 3 scorecard verdict artifact between scorecard inputs and the future tiny-live ADR discussion gate.
- Verdict labels cover positive and negative outcomes: `engineering_ready`, `research_promising`, `profitability_feasible`, `insufficient_evidence`, `execution_model_invalid`, and `kill`; negative verdicts can be sealed without positive profitability.
- Positive verdict validation requires formula/preregistration hashes, manifest/input hashes, sample/window thresholds, paper-vs-shadow divergence, PSR/DSR-style thresholds, after-cost LCBs where applicable, quality labels, and QC/MIT/QA review hashes; all verdicts reject IBKR contact, connector runtime, broker fill import, scorecard writer side effects, DB apply, evidence-clock start, secret serialization, tiny-live/live authority, and Bybit-live regression.
- Verification passed: new Rust source/test `rustfmt --check`, scorecard verdict `8 passed`, scorecard inputs `12 passed`, tiny-live eligibility `7 passed`, phase0 manifest `6 passed`, full `openclaw_types` `35` unit/golden + `206` integration/acceptance + `0` doc-tests, and `git diff --check`. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access, evidence clock, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2/3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Scorecard Status Read-Only Surface

- PM added display-only `GET /api/v1/stock-etf/scorecard-status` backed by Rust IPC fixture `stock_etf.get_scorecard_status`, exposing the blocked `stock_etf_scorecard_verdict_v1` posture from local source types only.
- GUI and `gui_lane_contract_v1` now require the scorecard-status GET-only surface alongside readiness/lane/evidence/universe/shadow/paper/reconciliation/account; static guards still reject write routes, direct broker writes, browser storage authority, and Stock/ETF paper-order IPC strings.
- Verification passed: route/normalizer/test `py_compile`; Rust format check on changed files, with `lib.rs` checked using `skip_children=true` to avoid unrelated module traversal; Node inline parser PASS; FastAPI/static pytest `57 passed`; openclaw_engine `stock_etf` `14 passed`; full `openclaw_types` `35` unit/golden + `206` integration/acceptance + `0` doc-tests; and `git diff --check`. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access, evidence clock, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2/3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Launch Status Read-Only Surface

- PM added display-only `GET /api/v1/stock-etf/launch-status` backed by Rust IPC fixture `stock_etf.get_launch_status`, exposing blocked release packet, disable-cleanup runbook, and tiny-live ADR eligibility posture from local source types only.
- GUI and `gui_lane_contract_v1` now require launch-status as a GET-only surface alongside readiness/lane/evidence/universe/shadow/paper/reconciliation/account/scorecard; static guards still reject write routes, direct broker writes, browser storage authority, and Stock/ETF paper-order IPC strings.
- Verification passed: route/normalizer/test `py_compile`; Rust format check on changed files, with `lib.rs` checked using `skip_children=true`; Node inline parser PASS (`7` scripts); FastAPI/static pytest `58 passed`; openclaw_engine `stock_etf` `15 passed`; GUI/lane IPC focused `17 passed`; full `openclaw_types` `35` unit/golden + `174` integration/acceptance + `0` doc-tests. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access, evidence clock, scorecard writer, DB apply, paper-shadow launch, paper order, fill import, GUI/lane selector authority, Phase 2/3/5 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Data Foundation Status Read-Only Surface

- PM added display-only `GET /api/v1/stock-etf/data-foundation-status` backed by Rust IPC fixture `stock_etf.get_data_foundation_status`, exposing blocked instrument identity and reference-data source posture from local source types only.
- GUI and `gui_lane_contract_v1` now require data-foundation-status as a GET-only surface alongside readiness/lane/evidence/universe/shadow/paper/reconciliation/account/scorecard/launch; `lane_scoped_ipc_v1` now includes `GetDataFoundationStatus` as display-only/non-effect-capable.
- Verification passed: route/normalizer/test `py_compile`; Rust format check on changed files, with `lib.rs` checked using `skip_children=true`; Node inline parser PASS (`7` scripts); focused FastAPI/static pytest `18 passed`; full Stock/ETF FastAPI/static pytest `67 passed`; openclaw_engine `stock_etf` `16 passed`; GUI/lane IPC focused `17 passed`; full `openclaw_types` `35` unit/golden + `206` integration/acceptance + `0` doc-tests; `git diff --check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access, contract-details request, reference-data collection/ingestion, market-data ingestion, evidence clock, scorecard writer, DB apply, paper order, fill import, GUI/lane selector authority, Phase 2/3 start, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Phase 0 Packet Status Read-Only Surface

- PM added display-only `GET /api/v1/stock-etf/phase0-status` backed by Rust IPC fixture `stock_etf.get_phase0_status`, exposing accepted `stock_etf_phase0_contract_packet_manifest_v1` source manifest status from local source types only.
- GUI and `gui_lane_contract_v1` now require phase0-status as a GET-only surface; `lane_scoped_ipc_v1` includes `GetPhase0Status` as display-only/non-effect-capable, and render logic lives in `/static/tab-stock-etf-phase0.js`.
- Verification passed: route/normalizer/test `py_compile`; full Stock/ETF FastAPI/static pytest `89 passed`; Node checks for Stock/ETF JS files; HTML inline parser PASS; Rust format checks PASS; openclaw_engine `stock_etf` `21 passed`; full openclaw_types `35` unit/golden + `206` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, connector runtime, secret access, Phase 1/2/3/4/5 runtime start, paper-shadow launch, paper order, fill import, evidence clock, scorecard writer, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF DB Evidence DDL Source Audit

- PM added `audit_stock_etf_db_evidence_source_sql`, a source-only Rust auditor for the accepted DB evidence DDL draft.
- The auditor validates the source-only/apply-denial posture plus schemas, Guard A, tables, key column declarations, natural keys, stock/IBKR/paper constraints, live denial, synthetic shadow fill separation, raw artifact hashes, audit event append-only posture, and hot-path indexes.
- Acceptance tests now execute the real source SQL and prove drift is blocked for missing column declarations, missing synthetic shadow checks, and destructive migration-promotion SQL.
- Verification passed: Rust format checks with `lib.rs` checked using `skip_children=true`; focused source SQL audit `2 passed`; DB evidence DDL acceptance `9 passed`; full openclaw_types `35` unit/golden + `207` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no DB migration/apply, PG dry-run, IBKR contact, connector runtime, secret access, Phase 1 runtime start, paper order, fill import, evidence clock, scorecard writer, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF DB Evidence DDL Source Contract Hardening

- PM strengthened the source-only DB evidence DDL with Guard B type checks, Guard C index drift checks, source FKs across instrument/order/fill/commission/shadow facts, and scorecard lineage hashes for cost model, market-data provenance, corporate actions, FX/cash ledger, and paper-vs-shadow reconciliation.
- The source draft now includes a TimescaleDB hypertable/retention promotion plan, but explicitly defers executable V### conversion until partition-safe primary/unique constraints are designed.
- The Rust auditor rejects missing Guard B/C, dry-run plan, FK lineage, scorecard lineage, and hypertable/retention plan drift.
- Verification passed: DB evidence DDL acceptance `10 passed`; full openclaw_types `35` unit/golden + `208` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no DB migration/apply, PG dry-run, sqlx registration, IBKR contact, connector runtime, secret access, Phase 1 runtime start, paper order, fill import, evidence clock, scorecard writer, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper IPC Request Shape Hardening

- PM hardened Phase 1D `lane_scoped_ipc_v1` so paper preview/submit/cancel/replace carry distinct request-shape contracts instead of one shared paper-effect field list.
- Submit pins full order intent fields (`symbol`, `instrument_kind`, `side`, `order_type`, `quantity`, `limit_price_policy`, `time_in_force`, `order_local_id`, idempotency, account/instrument hashes); cancel pins `order_local_id`, `broker_order_id`, `cancel_reason`, and idempotency; replace pins replacement idempotency/quantity/limit-price-policy/time-in-force plus `replace_reason`.
- Acceptance tests now reject submit/cancel/replace field-set cross-wiring, preserving the Rust-owned IBKR stock/ETF lane boundary and keeping legacy Bybit paper order routing separate.
- Verification passed: lane IPC `9 passed`; lane IPC + Phase0 manifest `15 passed`; full openclaw_types `35` unit/golden + `209` integration/acceptance + `0` doc-tests; openclaw_engine `stock_etf` `21 passed`; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, secret access, connector runtime, Phase 1 runtime start, paper order/cancel/replace, fill import, DB apply, evidence clock, scorecard writer, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Request Envelope Contract

- PM added `stock_etf_paper_order_request_v1`, a typed source-only request envelope contract between lane-scoped IPC and the IBKR paper lifecycle.
- The validator pins preview/submit/cancel/replace semantics: exact stock/ETF+IBKR+paper identity, IPC method/operation/scope/effect alignment, positive decimal quantities, explicit market/limit price policies, time-in-force rules, local/broker/idempotency ids, replacement fields, and audit/lifecycle/capability lineage.
- Phase0 manifest now includes 29 contracts; FastAPI Phase0 normalization/tests were updated to reject stale count drift.
- Verification passed: paper request `8 passed`; paper request + Phase0 manifest `14 passed`; lane IPC `9 passed`; FastAPI Phase0/StockETF route focused `14 passed`; openclaw_engine `stock_etf` `21 passed`; full openclaw_types `35` unit/golden + `217` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS; rustfmt/diff checks PASS. This grants no IBKR contact, secret access, connector runtime, Phase 1 runtime start, paper order/cancel/replace, fill import, DB apply, evidence clock, scorecard writer, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Lifecycle State Machine

- PM hardened `ibkr_paper_order_lifecycle_v1` / `broker_lifecycle_event_log_v1` so lifecycle events require append-only sequencing/hash chaining, request-envelope hash linkage to `stock_etf_paper_order_request_v1`, exact paper environment, and explicit stale-state policy.
- Operation-to-transition validation now separates submit/cancel/replace/fill-import state changes; denied events cannot advance active broker state, and `STATE_UNKNOWN` manual-review vs terminal reconciliation is machine-checked.
- Verification passed: lifecycle acceptance `12 passed`; linked acceptance `12 + 8 + 9 + 6 passed`; engine Stock/ETF `21 passed`; full openclaw_types `35` unit/golden + `221` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS. Linux runtime was not synced/restarted. This grants no IBKR contact, lifecycle writer, connector runtime, paper order/cancel/replace, fill import, DB apply, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Status Lifecycle Surface Hardening

- PM hardened the read-only paper-status surface after the lifecycle state-machine contract change. Rust `stock_etf.get_paper_status`, FastAPI normalization, fixtures/tests, and the Stock/ETF GUI now carry the lifecycle request-contract, event-sequence, genesis, hash-chain, request-envelope, and stale-state-policy fields.
- The FastAPI guard now blocks stale lifecycle payload shapes and any pre-gate event-chain/request-envelope/stale-policy readiness claim as `contract_violation_blocked`; fallback paths stay display-only and preserve `order_routed=false`.
- Verification passed: Python compile PASS; focused paper-status pytest `6 passed`; wider Stock/ETF FastAPI/static pytest `19 passed`; JS syntax PASS; Rust format check PASS; engine `stock_etf_paper_status` focused PASS; engine `stock_etf` filter `21 passed`; workspace `cargo check` PASS.
- PM boundary unchanged: no IBKR contact, no secret access/creation, no connector runtime, no lifecycle writer, no Phase 1/2/3/4/5 runtime start, no paper order/cancel/replace, no fill import, no DB apply, no evidence clock, no scorecard writer, no Linux runtime sync/restart, no tiny-live/live authority, and no Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper IPC Request Envelope Binding

- PM hardened the Phase 1D Rust IPC fixture so `stock_etf.preview_paper_order`, `stock_etf.submit_paper_order`, `stock_etf.cancel_paper_order`, and `stock_etf.replace_paper_order` parse their params as `stock_etf_paper_order_request_v1` when present and return a typed request-envelope verdict.
- The additive response surface reports parse status, expected/request method, IPC method binding, validator blockers, authority/effect posture, lineage field presence, and boundary flags; it keeps top-level IBKR/secret/routing/Bybit side-effect fields false.
- Tests now prove stale/minimal params fail envelope parsing without using the Bybit paper channel, valid preview envelope validation stays no-runtime, and a valid submit envelope cannot be accepted under the cancel IPC method.
- Verification passed: Rust format check PASS; openclaw_engine `stock_etf` filter `23 passed`; openclaw_types paper request acceptance `8 passed`; workspace `cargo check` PASS.
- PM boundary unchanged: no IBKR contact, no secret access/creation, no connector runtime, no lifecycle writer, no Phase 1/2/3/4/5 runtime start, no paper order/cancel/replace, no fill import, no DB apply, no evidence clock, no scorecard writer, no Linux runtime sync/restart, no tiny-live/live authority, and no Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Fill Import Request Contract

- PM added source-only `stock_etf_paper_fill_import_request_v1` for the future `stock_etf.import_paper_fills` path. It is a type/config/test checkpoint only, not a fill importer.
- The validator requires exact Stock/ETF/IBKR/paper identity, read-only `PaperOrderFillImport` semantics, session/lifecycle/event-log/redaction/source hashes, reconciliation run id, broker order/execution/commission ids, import idempotency, observed order state, stale-state policy, and raw/redacted artifact hashes.
- It rejects duplicate imports, stale unknown state without policy, IBKR contact, connector runtime, secret serialization, fill import side effects, DB apply, order routing, Bybit path reuse, live/tiny-live authority, margin/short/options/CFD requests, and Python direct broker writes.
- Phase0 manifest source, repository manifest JSON, FastAPI Phase0 count, route fixtures/tests, and Phase0 packet spec now include 30 contracts.
- Verification passed: new fill import acceptance `6 passed`; Phase0 manifest acceptance `6 passed`; FastAPI Phase0/StockETF focused `14 passed`; full openclaw_types `35` unit/golden + `227` integration/acceptance + `0` doc-tests; openclaw_engine `stock_etf` filter `23 passed`; workspace `cargo check` PASS.
- PM boundary unchanged: no IBKR contact, no secret access/creation, no connector runtime, no lifecycle writer, no Phase 1/2/3/4/5 runtime start, no fill import, no DB apply, no paper order/cancel/replace, no evidence clock, no scorecard writer, no Linux runtime sync/restart, no tiny-live/live authority, and no Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Paper Fill Import IPC Binding

- PM bound Rust IPC `stock_etf.import_paper_fills` to `StockEtfPaperFillImportRequestV1` parsing/validation and added an additive `fill_import_request` verdict to the handler response.
- Valid fill-import request params can validate as typed/read-only but remain no-runtime: `runtime_authority_denied=true`, no IBKR contact, no secret touch, no order routing, no Bybit path reuse, no fill import, and no DB apply.
- Minimal/stale import params now fail closed as `fill_import_request_parse_failed`, and top-level `allowed` also requires `fill_import_request_accepted_for_ipc`.
- Verification passed: Rust format check PASS; engine fill-import IPC focused `2 passed`; openclaw_types fill-import request acceptance `6 passed`; openclaw_engine `stock_etf` filter `25 passed`; workspace `cargo check` PASS; `git diff --check` PASS.
- PM boundary unchanged: no IBKR contact, no secret access/creation, no connector runtime, no lifecycle writer, no Phase 1/2/3/4/5 runtime start, no fill import, no DB apply, no paper order/cancel/replace, no evidence clock, no scorecard writer, no Linux runtime sync/restart, no tiny-live/live authority, and no Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Shadow Signal Request Contract + IPC Binding

- PM added source-only `stock_etf_shadow_signal_request_v1` for the future `stock_etf.evaluate_shadow_signal` path. It is a type/config/IPC gate checkpoint only, not a shadow collector or signal emitter.
- The validator requires exact Stock/ETF/IBKR/shadow identity, shadow-only `ShadowSignalEmit` semantics, request/evaluation/signal ids, evidence clock/PIT universe/strategy hypothesis/instrument identity/market-data provenance/cost model/asset-lane event/source hashes, and rejects IBKR contact, connector runtime, secret serialization, shadow signal emission, shadow fill generation, scorecard writer, DB apply, order routing, Bybit path reuse, live/tiny-live authority, margin/short/options/CFD requests, and Python direct broker writes.
- PM bound Rust IPC `stock_etf.evaluate_shadow_signal` to `StockEtfShadowSignalRequestV1` parsing/validation and added an additive `shadow_signal_request` verdict to the handler response; minimal/stale params now fail closed as `shadow_signal_request_parse_failed`.
- Phase0 manifest source, repository manifest JSON, FastAPI Phase0 count, route fixtures/tests, settings README, and Phase0 packet spec now include 31 contracts.
- Verification passed: shadow request acceptance `5 passed`; Phase0 manifest `6 passed`; FastAPI Phase0 route `4 passed`; FastAPI StockETF focused `14 passed`; engine shadow-signal IPC focused `2 passed`; openclaw_engine `stock_etf` filter `27 passed`; workspace `cargo check` PASS; scoped rustfmt check PASS; `git diff --check` PASS.
- PM boundary unchanged: no IBKR contact, no secret access/creation, no connector runtime, no shadow collector, no shadow signal emission, no shadow fill generation, no Phase 1/2/3/4/5 runtime start, no fill import, no DB apply, no paper order/cancel/replace, no evidence clock, no scorecard writer, no Linux runtime sync/restart, no tiny-live/live authority, and no Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Scorecard Reconciliation Lineage Gate

- PM added `paper_shadow_reconciliation_hash` to `stock_etf_scorecard_verdict_v1`, with a dedicated `PaperShadowReconciliationHashInvalid` blocker.
- Rust `stock_etf.get_scorecard_status`, FastAPI normalization, fixtures/tests, and the Stock/ETF GUI now expose `paper_shadow_reconciliation_hash_present=false`; pre-gate truthy claims are blocked as contract violations.
- Verification passed: scorecard verdict acceptance `8 passed`; focused FastAPI/static `15 passed`; full Stock/ETF FastAPI/static `90 passed`; engine `stock_etf` filter `27 passed`; full openclaw_types `35` unit/golden + `236` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS; rustfmt and Node syntax checks PASS. This grants no IBKR contact, connector runtime, secret access/creation, fill import, shadow fill generation, reconciliation writer, scorecard writer, DB apply, evidence clock, paper order/cancel/replace, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Scorecard Derivation Contract

- PM added source-only `stock_etf_scorecard_derivation_v1`, a derived artifact lineage contract between scorecard inputs/reconciliation and the scorecard verdict/writer boundary.
- Rust `stock_etf.get_scorecard_status`, FastAPI normalization, fixtures/tests, and the Stock/ETF GUI now expose a blocked `scorecard_derivation` block; pre-gate truthy derivation claims are blocked as contract violations.
- Verification passed: derivation acceptance `5 passed`; Python compile PASS; focused FastAPI/static `15 passed`; full Stock/ETF FastAPI/static `90 passed`; engine scorecard focused `1 passed`; engine `stock_etf` filter `27 passed`; full openclaw_types `35` unit/golden + `241` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS; rustfmt and Node syntax checks PASS. This grants no IBKR contact, connector runtime, secret access/creation, fill import, shadow fill generation, reconciliation writer, scorecard writer, DB apply, evidence clock, paper order/cancel/replace, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Tiny-Live Eligibility Lineage Gate

- PM hardened source-only `tiny_live_adr_eligibility_v1` so any future ADR tiny-live discussion requires scorecard derivation, scorecard verdict, scorecard manifest, paper-shadow reconciliation, DQ/statistical preregistration, and QC/MIT/QA review lineage.
- Rust `stock_etf.get_launch_status`, FastAPI normalization, fixtures/tests, and the Stock/ETF GUI now expose blocked lineage-present booleans; pre-gate truthy derivation/verdict/reconciliation/QA claims are blocked as contract violations.
- Verification passed: tiny-live eligibility `7 passed`; Python compile PASS; focused FastAPI/static `15 passed`; full Stock/ETF FastAPI/static `90 passed`; engine launch-status focused `1 passed`; engine `stock_etf` filter `27 passed`; full openclaw_types `35` unit/golden + `241` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS; rustfmt, Node syntax, and diff checks PASS. This grants no IBKR contact, connector runtime, secret access/creation, fill import, shadow fill generation, reconciliation writer, scorecard writer, DB apply, evidence clock, paper order/cancel/replace, ADR approval, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Read-Only Connector Skeleton Boundary

- PM added inert `program_code/broker_connectors/ibkr_connector/` outside the Bybit connector tree, with typed blocked readiness/previews and no IBKR SDK import, network contact, secret access, order methods, fill side effects, or DB writes.
- The existing Stock/ETF Python no-write static guard now scans the real connector skeleton, and dedicated skeleton tests assert the package stays blocked/source-only.
- Verification passed: Python compile PASS; connector skeleton + no-write static guard `7 passed`; full Stock/ETF FastAPI/static `94 passed`. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, scorecard writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF ADR/Register Lineage Catch-up

- PM updated `SPECIFICATION_REGISTER.md`, ADR-0048, and AMD-2026-06-29-01 so governance docs now record the scorecard derivation/verdict/reconciliation/tiny-live lineage gates and the inert IBKR connector skeleton boundary.
- Verification passed: register/ADR/AMD `rg` check PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, scorecard writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Connector Skeleton Readiness Gate

- PM exposed a fail-closed `connector_skeleton` block through the display-only Stock/ETF readiness normalizer and GUI, without importing the connector package or adding endpoints/actions.
- Pre-gate truthy claims for skeleton acceptance, non-blocked status, network contact, secret loading, paper/live channel exposure, write method presence, or Bybit path reuse now become readiness contract violations.
- Verification passed: Python compile PASS; focused readiness/no-write `9 passed`; full Stock/ETF FastAPI/static `94 passed`; Node syntax PASS; diff check PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, scorecard writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Source Posture Header Catch-up

- PM corrected high-level plan/report/operator status text: Phase 0 ADR/AMD/named contracts now exist in source, and Phase 1-5 source/status/display hardening is in progress; runtime launch remains blocked.
- Verification passed: `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, scorecard writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust Connector Skeleton Readiness Source

- PM made Rust IPC `stock_etf.get_readiness` emit the same fail-closed `connector_skeleton` block already normalized and displayed by FastAPI/GUI, so the IBKR connector skeleton boundary is source-owned by Rust readiness instead of only Python fallback.
- The block remains source/status-only: `ibkr_stock_etf_readonly_connector_skeleton_v1`, `accepted=false`, `status=blocked_source_only`, `phase2_gate_not_accepted`, and all contact/secret/paper/live/write/Bybit-reuse flags false.
- Verification passed: `rustfmt`, focused engine readiness `1 passed`, engine `stock_etf` filter `27 passed`, Python compile PASS, focused readiness/skeleton/no-write `13 passed`, full Stock/ETF FastAPI/static `94 passed`, Node syntax PASS, workspace `cargo check` PASS, and `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, scorecard writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Read-Only Probe Request Contract

- PM added source-only `stock_etf_ibkr_readonly_probe_request_v1`, a typed pre-contact request envelope for future IBKR health/account/contract-details/market-data read probes.
- The contract requires Stock/ETF IBKR readonly identity, allowlisted read action to broker-operation mapping, Phase 2 gate artifact, allowlist, secret-slot, topology, session-attestation, redaction, rate-limit, and audit-policy lineage hashes, while rejecting contact/runtime/secret/order/DB/evidence/Bybit/live/account-write/entitlement/client-portal/Python-write side effects.
- Phase0 manifest source, repository manifest JSON, FastAPI Phase0 count/fixtures/tests, settings template/README, ADR-0048, AMD-2026-06-29-01, specification register, and Phase0 packet spec now include 33 named contracts. Verification passed: readonly-probe acceptance `6 passed`; Phase0 manifest `6 passed`; Phase0 FastAPI route `4 passed`; full Stock/ETF FastAPI/static `94 passed`; full openclaw_types `35` unit/golden + `247` integration/acceptance + `0` doc-tests; engine `stock_etf` filter `27 passed`; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Read-Only Probe Readiness Gate

- PM made Rust IPC `stock_etf.get_readiness` expose a blocked `phase2.readonly_probe_request` block for `stock_etf_ibkr_readonly_probe_request_v1`, so the future first-contact read probe envelope is visible while still unavailable.
- FastAPI now normalizes readonly-probe readiness and fails closed if any pre-gate payload claims request artifact presence, validation, accepted-for-contact, IBKR contact, connector runtime, secret serialization, order/paper order, DB apply, evidence clock, Bybit reuse, or live/tiny-live.
- The Stock/ETF GUI renders readonly-probe request id/version/status/accepted flag and guard blockers; this is display/status only and adds no connector import, endpoint action, broker SDK path, runtime action, or write surface.
- Verification passed: engine `stock_etf` filter `27 passed`; full Stock/ETF FastAPI/static `94 passed`; Node syntax PASS; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Read-Only Probe IPC Binding

- PM added `stock_etf.preview_readonly_probe` as a Rust IPC validation-only fixture for `stock_etf_ibkr_readonly_probe_request_v1`; the response now carries a typed `readonly_probe_request` verdict and `readonly_probe_request_accepted_for_ipc`.
- `lane_scoped_ipc_v1`, method registry, and dispatch now include the method as readonly/slot-none with Phase 2 gate, API allowlist, secret-slot/topology/session, redaction, rate-limit, and audit-policy lineage requirements.
- A valid envelope can validate as typed/read-only, but top-level `allowed` remains false under current default flags/gates; empty/minimal params fail closed as `readonly_probe_request_parse_failed`.
- Verification passed: `rustfmt`; lane-scoped IPC acceptance `9 passed`; readonly-probe IPC focused `2 passed`; registry boundary focused `1 passed`; full openclaw_types `35` unit/golden + `247` integration/acceptance + `0` doc-tests; engine `stock_etf` filter `29 passed`; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Broker Read Capability Probe Gate

- PM hardened `broker_capability_registry_v1` so `health_read`, `account_snapshot_read`, `market_data_read`, and `contract_details_read` require `lane_scoped_ipc_v1` plus `stock_etf_ibkr_readonly_probe_request_v1` before a read capability row can validate.
- Missing typed IPC / readonly-probe request gates now produce `OperationRequiredGateMissing`; paper-write rows now use the shared lane-scoped IPC contract constant instead of a hard-coded id.
- Phase0 packet spec, broker settings README, and the blocked broker capability template now document the same prerequisite.
- Verification passed: `rustfmt`; broker capability acceptance `10 passed`; full openclaw_types `35` unit/golden + `248` integration/acceptance + `0` doc-tests; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Policy Status Read-Row Gate Display

- PM exposed the broker capability read-row probe gate state through Rust `stock_etf.get_policy_status`, FastAPI normalization/fallback, and the Stock/ETF policy GUI panel.
- `broker_capability_registry` status now includes the lane-scoped IPC contract id, readonly-probe request contract id, and two booleans showing whether read rows require both gates.
- Accepted broker capability registry payloads that omit/mismatch those gate claims now fail closed as `contract_violation_blocked` with explicit read-row gate violations.
- Verification passed: Python compile PASS; Node syntax PASS; focused policy/static `15 passed`; focused engine policy-status `1 passed`; full Stock/ETF FastAPI/static `94 passed`; engine `stock_etf` filter `29 passed`; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Read-Only Probe Request Operation Binding

- PM corrected `stock_etf.preview_readonly_probe` source semantics so accepted readonly-probe envelopes drive the top-level broker decision operation; market-data/account/contract-details probes no longer inherit the method fallback `health_read` decision operation.
- Invalid or parse-failed readonly-probe payloads are not trusted for operation selection and remain on the method-level fail-closed fixture boundary.
- Verification passed: `rustfmt`; readonly-probe IPC focused `3 passed`; engine `stock_etf` filter `30 passed`; workspace `cargo check` PASS; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Plan Timeline Checkpoint Guard

- PM normalized the main IBKR development arrangement so PM session checkpoints are now linear and unique from 14 through 74, aligned to the PM memory / Operator source timeline.
- Added a structure test that reads the main plan Markdown and fails if PM session checkpoint numbers become duplicated, skipped, or out of order.
- Verification passed: focused IBKR timeline structure test `1 passed`; section-body compare against `HEAD` PASS; `git diff --check` PASS. The full structure test file still has pre-existing docs README index drift failures unrelated to this guard. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF PM Memory Traceability Backfill

- PM backfilled main-plan and Operator trace titles for PM memory checkpoints: `Source Posture Header Catch-up`, `Rust Connector Skeleton Readiness Source`, `Read-Only Probe Request Contract`, and `Read-Only Probe Readiness Gate`.
- Added a structure guard that fails if those PM memory source/status titles are missing from the main development arrangement or Operator launch-certification summary.
- Verification passed: focused IBKR timeline + traceability structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Python Connector Network Static Guard

- PM hardened the Stock/ETF / IBKR Python no-write static guard so the source-only connector skeleton cannot import socket/HTTP/WebSocket client modules or dynamically import IBKR SDK / network modules.
- The guard now covers `socket`, `http.client`, `requests`, `httpx`, `urllib`, `urllib3`, `aiohttp`, `websocket`, and `websockets`, while keeping the scan scoped to Stock/ETF / IBKR Python surfaces rather than existing Bybit connector modules.
- Verification passed: Python no-write static guard `4 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Endpoint Template Consistency Guard

- PM added a FastAPI/GUI contract consistency guard requiring Stock/ETF OpenAPI GET endpoints to match `settings/broker/stock_etf_gui_lane_contract.template.toml` endpoint declarations, excluding the authenticated root redirect.
- The parser covers numeric endpoint keys such as `phase0_status_endpoint`; the guard prevents future route/template drift without adding endpoints or runtime authority.
- Verification passed: Stock/ETF route tests `11 passed`; full Stock/ETF FastAPI/static `96 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Static Endpoint Template Consistency Guard

- PM added a source-only static GUI guard requiring the Stock/ETF GUI bundle endpoint set to match `settings/broker/stock_etf_gui_lane_contract.template.toml` endpoint declarations exactly.
- The guard scans static `tab-stock-etf*` sources for `/api/v1/stock-etf...` strings, preventing future GUI/template drift or accidental extra Stock/ETF API surfaces.
- Verification passed: Python no-write static guard `5 passed`; full Stock/ETF FastAPI/static `97 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Route Auth Coverage Guard

- PM added a route-level auth coverage guard that derives every Stock/ETF GET path from OpenAPI, adds the authenticated root redirect, and verifies each route returns `401` without `current_actor`.
- This prevents future display-only Stock/ETF endpoints from being added without auth while preserving the existing GET-only, no-write route boundary.
- Verification passed: Stock/ETF route tests `12 passed`; full Stock/ETF FastAPI/static `98 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Route Cache Header Coverage Guard

- PM added a route-level cache/header guard that derives every Stock/ETF GET path from OpenAPI, adds the root redirect, and verifies `Cache-Control` is private/no-store with `Pragma: no-cache`, `Expires: 0`, and `Vary: Authorization`.
- This prevents future display-only Stock/ETF endpoints from bypassing auth/cache partitioning or leaking lane-specific status via stale shared caches.
- Verification passed: Stock/ETF route tests `13 passed`; full Stock/ETF FastAPI/static `99 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI IPC Empty Params Guard

- PM added an AST guard proving every `stock_etf_routes.py` IPC status read uses a literal `params={}`, so query/header/client lane claims cannot be forwarded into Rust IPC.
- The guard counts the Stock/ETF IPC calls and fails if any call omits `params` or passes non-empty/non-literal params.
- Verification passed: Python no-write static guard `6 passed`; full Stock/ETF FastAPI/static `100 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Handler Client-State Guard

- PM added an AST guard proving every `@stock_etf_router.get` handler accepts only `response` and/or authenticated `actor`, with `actor` wired through `Depends(base.current_actor)`.
- The guard blocks future route handlers from accepting Request/Header/Query/Body/Cookie/Form-style client state before Rust IPC/status normalization.
- Verification passed: Python no-write static guard `7 passed`; full Stock/ETF FastAPI/static `101 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI IPC Method Allowlist Guard

- PM added an AST guard proving `stock_etf_routes.py` IPC calls use named method constants whose resolved values are exactly the readonly Stock/ETF status/readiness method allowlist.
- The guard blocks future FastAPI GET/status surfaces from calling paper preview/submit/cancel/replace, fill import, shadow evaluation, readonly-probe preview, or any other non-status IPC method.
- Verification passed: Python no-write static guard `8 passed`; full Stock/ETF FastAPI/static `102 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Python Persistence Static Guard

- PM added a source-only AST guard proving Stock/ETF / IBKR Python surfaces do not import persistence, DB, object-store, or local evidence-writer modules.
- The guard also blocks dynamic persistence imports and explicit file-writer calls such as write_text/write_bytes/open-write/os.replace in the scoped Stock/ETF/IBKR Python surface.
- Verification passed: Python no-write static guard `9 passed`; full Stock/ETF FastAPI/static `103 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF OpenAPI Client Input Surface Guard

- PM added a route/OpenAPI guard proving Stock/ETF GET operations expose no request body and no client-state parameters beyond the optional `Authorization` header from existing auth.
- The guard blocks future query/path/header/cookie/body inputs from appearing in the public Stock/ETF OpenAPI contract.
- Verification passed: Stock/ETF route tests `14 passed`; full Stock/ETF FastAPI/static `104 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust Status IPC Untrusted Params Guard

- PM added a Rust IPC regression proving every Stock/ETF status/readiness method returns exactly the same result for `{}` params and malicious non-empty params claiming live, Bybit, paper submit, IBKR contact, secret touch, order routing, and Bybit IPC reuse.
- This extends the client-state-untrusted boundary below FastAPI so direct IPC callers cannot influence status/readiness fixture output through params.
- Verification passed: `rustfmt`; focused engine test `1 passed`; engine `stock_etf` filter `31 passed`; full Stock/ETF FastAPI/static `104 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust Dispatch Registry Routing Guard

- PM moved Rust dispatch for Stock/ETF fixture methods from a duplicated hand-written match arm list to registry-driven `is_stock_etf_fixture_method`.
- The registry helper requires a `stock_etf.` registered method with `slot=None`, keeping Stock/ETF IPC routing tied to the same source of truth that already records readonly/write-fixture metadata and live-token exclusion.
- Verification passed: `rustfmt`; engine `stock_etf` filter `31 passed`; full Stock/ETF FastAPI/static `104 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no IBKR contact, SDK import, socket/HTTP, connector runtime, secret access/creation, read probe execution, paper order/cancel/replace, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF GUI Data/Policy Fallback Split Guard

- PM split the large Data Foundation / Policy fallback payloads out of the main Stock/ETF GUI bundle into `tab-stock-etf-data-policy.js`, reducing `tab-stock-etf.js` from `1976` to `1805` lines and keeping every Stock/ETF GUI bundle file below the 2000-line governance cap.
- The static no-write guard now scans the new data/policy JS file and includes a line-cap regression for the Stock/ETF GUI bundle; the HTML loads the split before the main loader so existing display-only rendering semantics stay unchanged.
- Verification passed: Stock/ETF JS `node --check`; Python no-write/static guard `10 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust IPC Test Split Guard

- PM split the tail Stock/ETF Rust IPC status fixture tests into `rust/openclaw_engine/src/ipc_server/tests/stock_etf/status_fixtures.rs`, reducing the parent `stock_etf.rs` from `2532` lines to `1852` lines while keeping the child at `685` lines.
- Added a structure guard requiring the Stock/ETF Rust IPC parent and child fixture test files to stay below the 2000-line governance cap, with source-only checks for the moved status fixture methods and forbidden network/IBKR SDK tokens.
- Verification passed: `rustfmt`; engine `stock_etf` filter `31 passed`; Rust IPC split static guard `2 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust IPC Handler Split Guard

- PM split tail Stock/ETF Rust IPC status summary builders from `rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs` into `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/status_summaries.rs`, reducing the parent handler from `2217` lines to `1292` lines while keeping the child at `934` lines.
- Added a structure guard requiring the Stock/ETF Rust IPC handler parent and child files to stay below the 2000-line governance cap, with source-only checks for the moved status builder functions and forbidden IBKR SDK / network client tokens.
- Verification passed: `rustfmt`; engine `stock_etf` filter `31 passed`; Rust IPC handler/test split static guards `4 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Route Fixture Split Guard

- PM split the oversized Stock/ETF FastAPI route fixture helper into a same-name `stock_etf_route_fixtures/` package with `app.py`, `phase2_payloads.py`, `phase3_payloads.py`, and `phase5_payloads.py`, preserving the existing `from stock_etf_route_fixtures import ...` test import surface.
- The old 1525-line fixture file is replaced by package modules of `57`, `63`, `482`, `629`, and `364` lines, all below the 800-line review-attention threshold.
- Added a route fixture split structure guard requiring the legacy flat helper to stay removed, the package module/export set to remain stable, and payload fixture modules to avoid network/IBKR SDK/file-write tokens.
- Verification passed: route fixture `py_compile`; route fixture split static guard `3 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust IPC Request Contract Test Split Guard

- PM split Stock/ETF Rust IPC paper/fill/shadow/readonly-probe request contract tests from `rust/openclaw_engine/src/ipc_server/tests/stock_etf.rs` into `rust/openclaw_engine/src/ipc_server/tests/stock_etf/request_contracts.rs`.
- The Rust IPC test parent is reduced from `1852` to `1110` lines; `request_contracts.rs` is `745` lines and `status_fixtures.rs` remains `685` lines.
- The Rust IPC split structure guard now requires exactly `request_contracts.rs` and `status_fixtures.rs`, caps each parent/child test file at `1200` lines, and keeps both child modules free of network/IBKR SDK tokens.
- Verification passed: `rustfmt`; engine `stock_etf` filter `31 passed`; Rust IPC test split static guard `3 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF Rust IPC Handler Request Summary Split Guard

- PM split Stock/ETF Rust IPC request parsing and source-only paper/fill/shadow/readonly-probe summary helpers from `rust/openclaw_engine/src/ipc_server/handlers/stock_etf.rs` into `rust/openclaw_engine/src/ipc_server/handlers/stock_etf/request_summaries.rs`.
- The production handler parent is reduced from `1292` to `823` lines; `request_summaries.rs` is `477` lines and `status_summaries.rs` remains `934` lines.
- The handler split structure guard now requires exactly `request_summaries.rs` and `status_summaries.rs`, caps parent/child handler files at `1200` lines, and keeps both child modules free of network/IBKR SDK tokens.
- Verification passed: `rustfmt --check`; engine `stock_etf` filter `31 passed`; Rust IPC handler/test split static guards `6 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, dispatch route, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 IBKR Stock/ETF FastAPI Route IPC Query Helper Guard

- PM collapsed 16 duplicated `stock_etf_routes.py` IPC status query helpers into one central `_query_stock_etf_status(ipc, method)` helper while preserving every endpoint, method constant, normalizer, response envelope, and auth/no-store behavior.
- `stock_etf_routes.py` is reduced from `587` to `393` lines; the Python no-write static guard now proves there is exactly one `ipc.call(method, params={})` site and that all 16 route handlers invoke it only with allowlisted readonly Stock/ETF method constants.
- Verification passed: route/no-write focused tests `24 passed`; full Stock/ETF FastAPI/static `105 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Fallback Payload Split Guard

- PM split the remaining large display-only fallback payload builders out of `tab-stock-etf.js` into `tab-stock-etf-fallbacks.js`: authorization, account, evidence, universe, shadow, paper, scorecard, and launch.
- The main Stock/ETF GUI bundle is reduced from `1805` to `1244` lines; the new fallback module is `563` lines, loaded before the main loader, and all endpoint/rendering semantics remain display-only.
- The static no-write guard now scans the new fallback module and proves the large fallback builders stay out of the main bundle, with `tab-stock-etf.js <= 1400` and `tab-stock-etf-fallbacks.js <= 800`.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `25 passed`; full Stock/ETF FastAPI/static `106 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Data/Policy Renderer Split Guard

- PM moved the Data Foundation and Policy panel renderers from `tab-stock-etf.js` into the existing `tab-stock-etf-data-policy.js` display-only module, keeping the fallback payloads and renderers together.
- The main Stock/ETF GUI bundle is reduced from `1244` to `985` lines; `tab-stock-etf-data-policy.js` grows from `170` to `469` lines with local UI helpers consistent with the other split Stock/ETF modules.
- The static no-write guard now proves `renderDataFoundationStatus` and `renderPolicyStatus` stay out of the main bundle, with `tab-stock-etf.js <= 1100` and `tab-stock-etf-data-policy.js <= 700`.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `26 passed`; full Stock/ETF FastAPI/static `107 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Authorization/Account Renderer Split Guard

- PM moved the Authorization and Account panel renderers from `tab-stock-etf.js` into new display-only module `tab-stock-etf-auth-account.js`.
- The main Stock/ETF GUI bundle is reduced from `985` to `798` lines; `tab-stock-etf-auth-account.js` is `235` lines and exposes `window.renderAuthorizationStatus` / `window.renderAccountStatus` for the main loader.
- The static no-write guard now scans the auth/account module and proves `renderAuthorizationStatus` and `renderAccountStatus` stay out of the main bundle, with `tab-stock-etf.js <= 900` and `tab-stock-etf-auth-account.js <= 400`.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `27 passed`; full Stock/ETF FastAPI/static `108 passed`; focused IBKR timeline + trace-title structure tests `2 passed`; `git diff --check` PASS. This grants no new endpoint, IPC method, client input, IBKR contact, SDK import, socket/HTTP, connector runtime, secret access, read probe execution, paper order, fill import, evidence writer, DB apply, evidence clock, tiny-live, live, or Bybit behavior change.

## 2026-06-30 Standing Demo Authorization Refresh Guardrail

- PM added and ran a source-only standing Demo authorization refresh guardrail for current candidate `grid_trading|ETHUSDT|Buy`; source commit `04ec9c55d73226149c2221df51d7ab1881abf796`.
- Runtime materialized refreshed standing auth sha `a26666e71462b2fb6d11b1eedbdb9006e6b549393719e1e6933c4f348da3e4d3`, expiry `2026-07-01T09:02:17.250395+00:00`, cap `954.18759777 USDT`, max probe orders `2`, mode `0600`; validator sha `8dce62a676c3c5370579fd1e2687b0e9c0a64af7fa095e91fb6504cfc820c944` and readiness-after-refresh sha `ee46a2ae8f84acdb1ebcd7c50ca50de59f76c1a2ae1535d12907dda073a2e1ac` passed.
- Verification passed: source `py_compile`, focused guardrail tests `6 passed`, adjacent auth/equity/no-order suite `52 passed`, runtime post-refresh validator/readiness. Boundary: no Decision Lease, no order/cancel/modify, no Bybit private/order call, no env/service/crontab mutation, no Cost Gate change, no live/mainnet, no proof. Next blocker is downstream bounded auth/admission refresh because old plan/order-shape evidence is stale under the refreshed cap.

## 2026-06-30 Downstream Bounded Auth Final-Window No-Order Refresh

- PM established session loop state sha `056ed0927bea612ebf7f6d63d3305b8e57cd264f0deecf4552a03523c3feedcd`, then refreshed current ETH Buy downstream bounded auth/admission under standing auth sha `a26666e71462b2fb6d11b1eedbdb9006e6b549393719e1e6933c4f348da3e4d3`, cap `954.18759777 USDT`, max probe orders `2`.
- Runtime stayed divergent (`trade-core` local `00a78d92...`, runtime origin `e3655f93...`, `ahead 4, behind 128`), so PM used a timestamped source snapshot sha `4588dda9020b1509922d472393f1c4b37d0687a9` for no-order artifact construction instead of blind fast-forwarding runtime.
- Downstream manifest sha `c7f77c9f44889817d21de61afce43b09f9b88af68bd39e7b0a04d9cbf88cdcc8`; bounded auth sha `59fd54c49574ee063f7ec303b357f00a3d62490c3e1127aa3faf297d8e9b985e` is `BOUNDED_DEMO_PROBE_AUTHORIZED`; final-window manifest sha `7ba6047de6e52d4820aeb3ce78e6ab4f0ff5b08b755f6814e2d3374c38acd0d2` is `DONE_WITH_CONCERNS`; final admission sha `5d26cf035375846c91273ca9accf33d3ac4a47ccc1bbb92f37b6b732644489eb` is `READY_NO_ORDER`; post-run governance sha `19d926b9dfbcab10d801214f327100b7bc2e93733e5df396b99aea49610bf4d6` reports `lease_live_count=0`.
- Boundary: one short Demo Decision Lease acquire/release and public market-data GETs only; no order/cancel/modify, no Bybit private/order call, no writer/adapter enablement, no runtime/order admission, no Cost Gate change, no live/mainnet, no fill/PnL/proof. Next blocker is exact order-capable bounded Demo invocation review with a fresh active lease/BBO/order shape in the invocation window.

## 2026-07-01 Order-Capable Soak Plan Materialization

- PM established session loop state sha `cd9c99b4b73c8f63dc62e1f0b2a5a4e2b1012fd34de62145f19add992c946c71`; E3 and BB both returned `DONE_WITH_CONCERNS` for PM-supervised no-order canonical materialization.
- Canonical plan `/tmp/openclaw/cost_gate_learning_lane/bounded_demo_probe_soak_plan.json` moved from sha `80ba57285f0a7f9d20ea0f4621660d1c917245f8b1bc33f95b534568a74b86a6` to sha `30056993b5cae70a0fcad0503221e12bd74dae4e42a29d0d2c88423c64739823`; manifest sha `7971510fe89e3ef14eb7a46893e3368a588ae695b2409639720d94186c045f30`; post no-order verification sha `044b50a6738bc17b55e80dd0785104b8a77e28aeade4121148f852aefeae7706`; ledger sha unchanged `086f5eb30bb4213cdff9e348d47dd98cc93b7daafd82059cfa9adb0ae18045c1`.
- Boundary: no `_latest` overwrite, no ledger append, no service/env mutation, no exchange/private/order call, no Cost Gate change, no live/mainnet, no fill/PnL/proof. Next blocker is `P0-CURRENT-CANDIDATE-FRESH-INVOCATION-WINDOW-LEASE-BBO-ORDER-SHAPE-GATE`.

## 2026-07-01 IBKR Stock/ETF GUI Evidence/Paper Renderer Split Guard

- PM moved Evidence, Universe, Shadow, and Paper display renderers into `tab-stock-etf-evidence-paper.js`, reducing the Stock/ETF main GUI bundle from `798` to `583` lines.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `28 passed`; full Stock/ETF FastAPI/static `109 passed`; IBKR timeline + trace-title guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no endpoint/IPC/client-input change, no IBKR contact, no connector/runtime/secret/read-probe/paper-order/evidence/DB/tiny-live/live change, and no Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Scorecard/Launch Renderer Split Guard

- PM moved Scorecard and Launch display renderers into `tab-stock-etf-scorecard-launch.js`, reducing the Stock/ETF main GUI bundle from `583` to `350` lines.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `29 passed`; full Stock/ETF FastAPI/static `110 passed`; IBKR timeline + trace-title guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no endpoint/IPC/client-input change, no IBKR contact, no connector/runtime/secret/read-probe/paper-order/evidence/DB/tiny-live/live change, and no Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Readiness Renderer Split Guard

- PM moved the lane/readiness renderer and local UI helpers into `tab-stock-etf-readiness.js`, reducing the Stock/ETF main GUI bundle from `350` to `197` lines.
- Verification passed: Stock/ETF JS `node --check`; route/no-write focused tests `30 passed`; full Stock/ETF FastAPI/static `111 passed`; IBKR timeline + trace-title guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no endpoint/IPC/client-input change, no IBKR contact, no connector/runtime/secret/read-probe/paper-order/evidence/DB/tiny-live/live change, and no Bybit behavior change.

## 2026-07-01 Fresh Invocation-Window Source Preflight Blocked

- PM established session loop state sha `e6724c79a45b187e1c020065cf6c445950bafcf01daf923e9e73e94afbad7a2d` and ran only the corrected no-order dry-run with `PYTHONPATH=helper_scripts/research`.
- Dry-run sha `148deaecd3e7423d1ecf207c5d8f715e48f6773e95f676500e1e05299237e6b6` returned `CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_SOURCE_NOT_READY` because the current-candidate envelope is stale and the gate/sizing packet is not the required pre-active sizing-aware loss-control packet.
- E3 blocked the proposed `--run`; BB accepted public market-data GET scope in principle but also blocked `--run` until source inputs dry-run ready. No lease, public quote, Bybit call, order/cancel/modify, PG access, runtime mutation, service restart, Cost Gate change, live/mainnet, fill/PnL, or proof occurred.
- Next blocker: `P0-CURRENT-CANDIDATE-FRESH-INVOCATION-WINDOW-SOURCE-INPUT-REFRESH-GATE`.

## 2026-07-01 IBKR Stock/ETF Python Secret/Env Access Static Guard

- PM added a source-only AST guard proving Stock/ETF / IBKR Python surfaces do not import env/secret helper modules or read secret/environment material.
- The guard blocks `os` imports, `dotenv`/`getpass`/`keyring`, `os.environ`, `getenv`/`os.getenv`, `Path.home`, `expanduser`, `read_text`, `read_bytes`, and any `open()` call in the scoped surface while preserving display-only secret-slot schema normalization.
- Verification passed: Python no-write static guard `17 passed`; route/no-write focused tests `31 passed`; full Stock/ETF FastAPI/static `112 passed`; IBKR timeline + trace-title guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no endpoint/IPC/client-input change, no IBKR contact, no connector/runtime/secret/read-probe/paper-order/evidence/DB/tiny-live/live change, and no Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Rust IPC Secret/Env Material Static Guard

- PM added Rust split structure guards proving Stock/ETF IPC handler/test files do not introduce direct `std::env`/`env::var`, secret-file/material readers, network/socket clients, or direct IBKR SDK tokens.
- The handler guard explicitly preserves exactly one typed `StockEtfFeatureFlags::from_env()` path in the parent handler while forbidding bypass reads in `stock_etf.rs`, `request_summaries.rs`, and `status_summaries.rs`.
- Verification passed: Rust IPC split static guards `8 passed`; docs trace guard `2 passed`; full Stock/ETF FastAPI/static `112 passed`; `git diff --check` PASS.
- Boundary unchanged: no Rust runtime behavior change, endpoint/IPC method change, IBKR contact, connector/runtime/secret/read-probe/paper-order/evidence/DB/tiny-live/live change, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Rust Feature Flag Env Allowlist Guard

- PM added a Rust acceptance regression proving `StockEtfFeatureFlags::from_lookup` queries exactly five non-secret feature flag keys and falls back to default-off posture when all keys are absent.
- The allowed keys are lane enabled, IBKR readonly enabled, IBKR paper enabled, asset-lane default, and stock/ETF shadow-only; the test rejects secret/token/password/account/key-bearing names.
- Verification passed: file `rustfmt --check`; `stock_etf_lane_acceptance` `9 passed`; docs trace guard `2 passed`; full Stock/ETF FastAPI/static `112 passed`; `git diff --check` PASS.
- Boundary unchanged: no Rust runtime behavior change, endpoint/IPC method change, IBKR contact, connector/runtime/secret/read-probe/paper-order/evidence/DB/tiny-live/live change, or Bybit behavior change. Workspace-wide `cargo fmt --all -- --check` remains blocked by pre-existing unrelated Rust formatting drift outside this IBKR slice.

## 2026-07-01 IBKR Stock/ETF Connector Preview Payload Guard

- PM made `IbkrReadOnlyClient.connection_plan()` explicitly fail closed with `surface_id`, `accepted=false`, `status=blocked_source_only`, `phase2_gate_not_accepted`, and `connection_plan_blocked`.
- PM added an exact payload-shape regression for the inert IBKR connector skeleton covering connection plan, readiness, account snapshot, market data, contract details, paper lifecycle, fill import, and static fixture previews.
- The guard fixes all preview payloads to secret-free/no-network/no-paper-channel/no-live/no-write/no-Bybit-reuse posture while preserving the existing source-only connector boundary.
- Verification passed: connector skeleton tests `5 passed`; Python no-write static guard `17 passed`; full Stock/ETF FastAPI/static `113 passed`; docs trace guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no endpoint/IPC method change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Connector Bybit Import Separation Guard

- PM added an AST guard proving the inert IBKR connector skeleton does not import Bybit connector, control-api `app`, or `program_code.exchange_connectors.bybit_connector` modules.
- The guard scans direct imports and literal dynamic imports via `__import__` / `importlib.import_module` across `program_code/broker_connectors/ibkr_connector/*.py`.
- This keeps the IBKR skeleton isolated under `program_code/broker_connectors/ibkr_connector/` and prevents accidental reuse of Bybit runtime/control-api code while preserving the existing `bybit_path_reused=false` payload field.
- Verification passed: connector skeleton tests `6 passed`; Python no-write static guard `17 passed`; full Stock/ETF FastAPI/static `114 passed`; docs trace guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no endpoint/IPC method change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF FastAPI IBKR Connector Runtime Wiring Guard

- PM added a production-surface AST guard proving Stock/ETF/control-api Python files do not import the inert IBKR connector skeleton before runtime approval.
- The guard scans `control_api_v1/app` Stock/ETF/IBKR files only, while allowing dedicated skeleton tests to import the package.
- Literal dynamic imports are also checked through the shared dynamic import helper, including `importlib.import_module`.
- Verification passed: Python no-write static guard `18 passed`; connector skeleton tests `6 passed`; full Stock/ETF FastAPI/static `115 passed`; docs trace guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no endpoint/IPC method change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Rust IPC Bybit Runtime Separation Guard

- PM added Rust split structure guards proving Stock/ETF IPC handler/test source does not import or call Bybit REST/WS/Earn clients, order manager/router, paper state, bounded-probe active-order module, legacy paper submit handler, or direct order method call tokens.
- The handler guard scans `stock_etf.rs`, `request_summaries.rs`, and `status_summaries.rs`; the fixture guard scans parent `stock_etf.rs`, `request_contracts.rs`, and `status_fixtures.rs`.
- Contract-level negative posture fields such as `bybit_ipc_reused=false`, `bybit_path_reused=false`, and legacy Bybit channel regression text remain allowed; the guard blocks runtime code-path coupling.
- Verification passed: Rust IPC split static guards `10 passed`; full Stock/ETF FastAPI/static `115 passed`; docs trace guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no Rust runtime behavior change, endpoint/IPC method change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Connector Public API Freeze Guard

- PM added exact package/class public-surface guards for the inert IBKR connector skeleton.
- The package `__all__` is frozen to the source-only surface id, read-only client, paper boundary client, endpoint config, and surface status; the read-only client public surface is limited to config/readiness/preview methods; the paper boundary public surface is limited to lifecycle and fill-import readiness descriptors.
- This supplements the existing forbidden write-method guard by preventing future runtime-start, order-write, secret/network, or Bybit-reuse entrypoints from appearing under alternative public method names.
- Verification passed: connector skeleton tests `8 passed`; Python no-write static guard `18 passed`; full Stock/ETF FastAPI/static `117 passed`; docs trace guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no endpoint/IPC method change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Python Runtime Side-Effect Static Guard

- PM added an AST guard proving the scoped Stock/ETF / IBKR Python surface does not import clock/concurrency/subprocess modules or call timing/background-work primitives.
- The guard bans `time`, `datetime`, `asyncio`, `threading`, `multiprocessing`, `subprocess`, and `concurrent` imports plus `sleep`, `time`, `monotonic`, `perf_counter`, `now`, `utcnow`, `fromtimestamp`, `Thread`, `Process`, `Popen`, `run`, `create_task`, and `to_thread` calls in the scoped surface.
- Scope remains only Stock/ETF FastAPI routes/normalizers and the inert IBKR connector skeleton, preserving existing Bybit runtime modules.
- Verification passed: Python no-write static guard `19 passed`; connector skeleton tests `8 passed`; full Stock/ETF FastAPI/static `118 passed`; docs trace guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no endpoint/IPC method change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Rust IPC Runtime Side-Effect Static Guard

- PM added Rust split structure guards proving Stock/ETF IPC handler/test source does not import or call clock/thread/task/process side-effect primitives.
- The guard bans `std::time`, `SystemTime`, `Instant`, `chrono`, `Utc::now`, `Local::now`, `std::thread`, `thread::spawn`, `tokio::spawn`, `tokio::task`, `tokio::time`, `sleep(`, `std::process`, `process::Command`, `Command::new`, and `.spawn(` in scoped handler/test files.
- Scope remains only Stock/ETF IPC handler parent/children and Stock/ETF IPC fixture test parent/children.
- Verification passed: Rust IPC split static guards `12 passed`; full Stock/ETF FastAPI/static `118 passed`; docs trace guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no Rust runtime behavior change, endpoint/IPC method change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI Background Work Static Guard

- PM added a static GUI guard proving Stock/ETF display files do not introduce polling, push channels, workers, XHR/sendBeacon, or high-frequency timing primitives.
- The guard scans `tab-stock-etf*.js` and `tab-stock-etf.html`, blocking `setInterval`, `setTimeout`, animation/idle callbacks, WebSocket, EventSource, Worker/SharedWorker, BroadcastChannel, XMLHttpRequest, sendBeacon, `performance.now`, and `Date.now`.
- Existing one-shot authenticated GET loading remains allowed; `new Date().toLocaleTimeString()` remains display-only and does not start background work.
- Verification passed: Python no-write static guard `20 passed`; full Stock/ETF FastAPI/static `119 passed`; docs trace guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no endpoint/IPC method change, client input change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF GUI One-Shot Fanout Budget Guard

- PM added a static GUI guard proving `tab-stock-etf.js` keeps exactly one one-shot load path: one `Promise.all`, one `waitForServerUp(loadReadiness)`, and 16 `ocApi` calls.
- Every Stock/ETF GUI `ocApi` call must be GET-only with `timeoutMs: 5000` and `toastOnError: false`.
- This prevents future display-only GUI drift into extra API fanout, longer timeout budgets, or repeated loaders before runtime approval.
- Verification passed: Python no-write static guard `21 passed`; full Stock/ETF FastAPI/static `120 passed`; docs trace guard `2 passed`; `git diff --check` PASS.
- Boundary unchanged: no endpoint/IPC method change, client input change, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, paper order/cancel/replace, fill import, DB/evidence writer, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Collector Run Contract

- PM added source-only `stock_etf_collector_run_v1` and raised Phase0 named contracts to 34; the validator requires 5 green trading sessions plus PIT universe, market-data provenance, reference-data, storage-capacity, gap, DQ, replay, and source-artifact hashes.
- Existing evidence-status IPC/FastAPI/GUI surfaces now expose default-blocked `collector_run` without adding endpoints, IPC methods, GUI fanout, or runtime work.
- Verification passed: Python compile, JS syntax, scoped Rust format, full Stock/ETF FastAPI/static `120 passed`, full `openclaw_types` `287` tests, engine Stock/ETF focused `31 passed`, docs trace `2 passed`, and `git diff --check` PASS.
- Boundary unchanged: no IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, collector start, market-data ingestion, paper order/cancel/replace, fill import, DB/evidence/scorecard writer, evidence clock, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF DQ Manifest Contract

- PM added source-only `stock_etf_dq_manifest_v1` and raised Phase0 named contracts to 35; the validator requires exact contract identity, Stock/ETF IBKR paper/shadow binding, collector/provenance/source lineage hashes, DQ quality fields, Bybit-live unchanged proof, and no runtime side-effect claims.
- Existing evidence-status IPC/FastAPI/GUI surfaces now expose default-blocked `dq_manifest` without adding endpoints, IPC methods, GUI fanout, runtime work, or a DQ writer.
- Verification passed: Python compile, JS syntax, scoped Rust format, Phase3 evidence acceptance `19 passed`, Phase0 manifest acceptance `6 passed`, focused Phase0/Evidence/Route pytest `22 passed`, full Stock/ETF FastAPI/static `120 passed`, full `openclaw_types` PASS, engine Stock/ETF focused `31 passed`, docs trace `2 passed`, and `git diff --check` PASS.
- Boundary unchanged: no IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, collector start, market-data ingestion, DQ writer, paper order/cancel/replace, fill import, DB/evidence/scorecard writer, evidence clock, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Evidence Clock Lineage Guard

- PM hardened source-only `stock_etf_evidence_clock_v1` so evidence-clock day artifacts carry collector-run and DQ-manifest contract id/hash lineage.
- Existing evidence-status IPC/FastAPI/GUI surfaces now expose default-blocked evidence-clock collector/DQ/source/provenance/scorecard input hash presence without adding endpoints, IPC methods, GUI fanout, runtime work, or an evidence clock.
- Verification passed: Python compile, JS syntax, scoped Rust format, Phase3 evidence acceptance `19 passed`, Phase0 manifest acceptance `6 passed`, and focused evidence-status pytest `4 passed`.
- Boundary unchanged: no IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe execution, collector start, market-data ingestion, DQ writer, paper order/cancel/replace, fill import, DB/evidence/scorecard writer, evidence clock, tiny-live/live, Linux runtime sync/restart, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Phase3 Evidence Module Split Guard

- PM split Phase3 market-data provenance and frozen-input contracts into `stock_etf_phase3_evidence/market_data.rs` while preserving the parent module public re-export surface.
- `stock_etf_phase3_evidence.rs` dropped from 982 to 742 lines; the new child module is 254 lines.
- Verification passed: scoped Rust format, Phase3 evidence acceptance `19 passed`, Phase0 manifest acceptance `6 passed`, full Stock/ETF FastAPI/static `120 passed`, full `openclaw_types` PASS, engine Stock/ETF focused PASS, docs trace `2 passed`, and `git diff --check` PASS.
- Boundary unchanged: no contract behavior, endpoint, IPC, GUI payload, IBKR contact, runtime, order, DB/evidence writer, evidence clock, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Connector Attestation Preview Guard

- PM added inert Python connector skeleton session and paper attestation preview payloads plus blocked fixtures, preserving source-only/no-network/no-secret/no-Bybit posture.
- `IbkrReadOnlyClient.session_attestation_preview()` and `IbkrPaperClientBoundary.paper_attestation_preview()` now return typed blocked dicts for future Phase 2 gate wiring.
- Verification passed: Python compile, connector skeleton focused test `8 passed`, full Stock/ETF FastAPI/static `120 passed`, docs trace `2 passed`, and `git diff --check` PASS.
- Boundary unchanged: no endpoint, IPC, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, paper order, fill import, DB/evidence writer, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Session Attestation Data-Tier Lineage Guard

- PM hardened `ibkr_session_attestation_v1` with `IbkrSessionDataTier`, entitlements fingerprint, market-data entitlement purchase denial, and gateway startup timestamp lineage.
- Session validation now requires 64-hex account/secret-slot/entitlements/raw artifact hashes and rejects missing data tier, invalid entitlement lineage, entitlement purchase not denied, and gateway startup after attestation.
- Inert Python connector preview plus FastAPI account/authorization normalizers expose only fail-closed `unknown` / `False` / `0` fields and reject client/IPC claims before gate.
- Verification passed: Python compile, connector/account/authorization focused tests `18 passed`, Phase2 gate `11 passed`, feature-flag auth `8 passed`, full Stock/ETF FastAPI/static `120 passed`, full `openclaw_types` `291 passed`, docs trace `2 passed`, and `git diff --check` PASS.
- Boundary unchanged: no endpoint, IPC method, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, market-data ingestion, paper order, fill import, DB/evidence writer, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Phase0 Result-Import Display Lineage Guard

- PM propagated `stock_etf_ibkr_readonly_probe_result_import_request_v1` from Rust type/manifest authority into FastAPI Phase0 status, Rust IPC Phase0 assertions, policy status normalization, and GUI display rows.
- Phase0 control-plane fixtures now carry 36 contracts and fail closed if either readonly probe request or readonly probe result-import request is missing.
- Policy status now exposes `readonly_probe_result_import_request_contract_id` plus `scorecard_requires_readonly_probe_result_import_request`; an accepted registry missing that scorecard gate is a contract violation.
- Verification passed: Python compile, JS syntax, scoped Rust rustfmt, focused FastAPI Phase0/Policy/Route `23 passed`, full Stock/ETF FastAPI/static `120 passed`, focused engine Phase0/Policy IPC tests PASS, and engine Stock/ETF IPC regression `31 passed`.
- Boundary unchanged: no endpoint, IPC method, GUI fanout, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, result import, paper order, fill import, DB/evidence/scorecard writer, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Readiness Result-Import Request Guard

- PM propagated `stock_etf_ibkr_readonly_probe_result_import_request_v1` into the readiness pre-contact source/display surface.
- Rust IPC `stock_etf.get_readiness` now exposes a default-blocked `readonly_probe_result_import_request` with `accepted_for_import=false`, `result_import_performed=false`, writer flags false, DB/order flags false, and Bybit reuse false.
- FastAPI readiness normalizer fails closed when the block is missing and treats contract mismatch, ready status, or any result-import/writer/DB/order/Bybit side-effect claim as `contract_violation_blocked`.
- GUI readiness renderer and API-unavailable fallback display the result-import request contract/status/blockers/side-effect flags without adding endpoints, IPC methods, GUI fanout, client input, or connector public API.
- Verification passed: Python compile, JS syntax, scoped Rust rustfmt, focused FastAPI readiness/static `20 passed`, focused engine readiness IPC PASS, full Stock/ETF FastAPI/static `120 passed`, and engine Stock/ETF IPC regression `31 passed`.
- Boundary unchanged: no IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, result import, collector, market-data ingestion, DQ writer, paper order/cancel/replace, DB/evidence/scorecard writer, evidence clock, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Connector Result-Import Preview Guard

- PM added `IbkrReadOnlyProbeResultImportPreview` plus `IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID` to the inert Python IBKR connector skeleton.
- `IbkrReadOnlyClient.readonly_probe_result_import_request_preview()` and a matching fixture now return a blocked no-artifact result-import request preview with import/writer/DB/order/live/Bybit flags false.
- The connector package export freeze, read-only client public surface freeze, payload shape guard, no-Bybit-import guard, and Python no-write static guard now cover the new preview.
- Verification passed: Python compile, connector skeleton focused `8 passed`, Python no-write static guard `21 passed`, and full Stock/ETF FastAPI/static `120 passed`.
- Boundary unchanged: no endpoint, IPC method, FastAPI production import, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, result import, DB/evidence/scorecard writer, paper order/cancel/replace, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Scorecard Input Result-Import Lineage Guard

- PM hardened `StockEtfScorecardInputBundleV1` so future scorecard input bundles must carry `stock_etf_ibkr_readonly_probe_result_import_request_v1` contract id and a 64-hex result-import request hash.
- Rust IPC `stock_etf.get_scorecard_status` now exposes a default-blocked `scorecard_input_bundle` summary, including result-import lineage hash-present flags and side-effect flags.
- FastAPI scorecard status normalization and GUI scorecard rendering now fail closed around the input bundle, rejecting accepted/hash-present/runtime side-effect claims before any scorecard writer.
- Verification passed: Python compile, JS syntax, scoped Rust format, focused Rust scorecard input acceptance, focused engine scorecard IPC fixture, focused FastAPI scorecard/static pytest, full Stock/ETF FastAPI/static pytest, and docs trace guard.
- Boundary unchanged: no endpoint, IPC method, GUI fanout, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, result import, collector, market-data ingestion, DQ writer, paper order/cancel/replace, fill import, DB/evidence/scorecard writer, evidence clock, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Scorecard Fallback Input Lineage Guard

- PM added a default-degraded `scorecard_input_bundle` to browser-side `scorecardFallback()`.
- The fallback preserves `stock_etf_ibkr_readonly_probe_result_import_request_v1` lineage context while keeping result-import hash-present, market/reference/risk/atomic/source lineage flags, and all side-effect flags false.
- Static no-write/split guard now checks that fallback payloads keep the scorecard input bundle result-import lineage fields.
- Verification passed: Python compile, JS syntax, focused fallback/static/docs trace pytest, full Stock/ETF FastAPI/static pytest, and `git diff --check`.
- Boundary unchanged: no endpoint, IPC method, GUI fanout, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, result import, DB/evidence/scorecard writer, paper order/cancel/replace, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Scorecard Status Module Split Guard

- PM split Rust `scorecard_status_summary` from `status_summaries.rs` into `status_summaries/scorecard.rs`.
- The parent module keeps a thin wrapper, so `stock_etf.get_scorecard_status` behavior and payload shape remain unchanged.
- `status_summaries.rs` is now 785 lines and the scorecard child module is 228 lines.
- Verification passed: scoped Rust format, focused engine scorecard IPC fixture, engine Stock/ETF IPC regression `29 passed`, docs trace guard, and `git diff --check`.
- Boundary unchanged: no endpoint, IPC method, payload behavior, GUI fanout, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, result import, DB/evidence/scorecard writer, paper order/cancel/replace, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Python No-Write Static Guard Split Guard

- PM split the 1022-line Stock/ETF Python no-write static guard into a shared helper plus Python/route/GUI guard modules.
- The guard logic remains intact: Python/connector no-write, route/IPC readonly status, GUI display-only/no-background-work, fanout budget, and renderer/fallback split checks still run.
- Verification passed: Python compile, focused split guard `21 passed`, and full Stock/ETF FastAPI/static `120 passed`.
- Boundary unchanged: no endpoint, IPC method, GUI fanout, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, result import, DB/evidence/scorecard writer, paper order/cancel/replace, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Scorecard Input Module Split Guard

- PM split Rust `stock_etf_scorecard_inputs.rs` into a 128-line parent re-export, 520-line component validators module, and 181-line bundle validator module.
- Public `openclaw_types::stock_etf_scorecard_inputs::*` imports, contract ids, fixtures, and validator behavior remain unchanged.
- Verification passed: scoped Rust format, scorecard input acceptance `12 passed`, scorecard derivation/verdict acceptance `13 passed`, full `cargo test -p openclaw_types`, and engine Stock/ETF IPC `29 passed`.
- Boundary unchanged: no endpoint, IPC method, payload behavior, GUI fanout, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, result import, DB/evidence/scorecard writer, paper order/cancel/replace, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Rust IPC Parent Module Split Guard

- PM split handler Phase2 pre-contact summaries into `handlers/stock_etf/precontact.rs` and moved readiness/data-foundation/policy/authorization fixture tests into `precontact_fixtures.rs` / `foundation_status_fixtures.rs`.
- Handler parent dropped from 860 to 750 lines; IPC fixture test parent dropped from 1209 to 706 lines; new child modules are 118/158/353 lines.
- Rust IPC handler/test split static guards now cap files at 800 lines and require the new child-module allowlist plus moved helper/test ownership.
- Verification passed: scoped Rust format, focused split structure guards `14 passed`, engine Stock/ETF IPC `29 passed`, docs trace guard, and `git diff --check`.
- Boundary unchanged: no endpoint, IPC method, payload behavior, GUI fanout, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, result import, DB/evidence/scorecard writer, paper order/cancel/replace, tiny-live/live, Linux runtime, or Bybit behavior change.

## 2026-07-01 IBKR Stock/ETF Paper Order Request Module Split Guard

- PM split `stock_etf_paper_order_request.rs` into a 216-line parent type/default module, 114-line fixture module, and 498-line validation module.
- Public paper-order request types, accepted fixture methods, `validate()`, contract id, and import surface remain unchanged.
- Added `test_stock_etf_paper_order_request_split_static.py` to enforce module allowlist, moved ownership, 800-line cap, and no-runtime-token posture.
- Verification passed: scoped Rust format, paper-order split static guard `3 passed`, paper-order acceptance `8 passed`, full `cargo test -p openclaw_types`, and engine Stock/ETF IPC `29 passed`.
- Boundary unchanged: no endpoint, IPC method, payload behavior, GUI fanout, IBKR contact, SDK import, socket/HTTP, secret access, connector runtime, read probe, result import, DB/evidence/scorecard writer, paper order/cancel/replace, tiny-live/live, Linux runtime, or Bybit behavior change.
