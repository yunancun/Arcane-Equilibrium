# E2 Adversarial Review — Wave 2.2 LG-1 + LG-2 batch (8 task)

Date: 2026-05-11
Owner: E2
Wave: Sprint N+1 Wave 2.2 (LG-1 T1/T2/T3/T4 + LG-2 T1/T2/T3/T4)
Object: commit `a11a4df6 LG live gate checkpoint [skip ci]` (already on `main`)
Parallel: E5 perf, A3 UX/runbook, E4 regression
PA SoT: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` §1.4 + §2.4

---

## 1. Verdict

**APPROVE WITH 4 MEDIUM / 2 LOW / 3 P2 / 1 HIGH governance flag · PASS to E4**

- 0 BLOCKER（無 race / no SQL injection / no panic in hot path / no hard boundary bypass）
- 1 HIGH governance flag（**SCOPE CREEP not blocker but must be acknowledged**）
- 4 MEDIUM（PA spec drift 已 E1 push back，可接受；1 個未閉環）
- 2 LOW（注釋語意 / docstring）
- 3 P2 governance ticket（pre-existing file size warnings ≥800，每個未破 2000 hard cap）

可派 E4 regression。E5 perf + A3 UX 並行 audit。**PM 在 push 前須額外 sign-off SCOPE CREEP**（commit body 未 disclose `SCANNER-TRADEABLE-TIER-1` bb_reversion/ma_crossover 業務邏輯改動）。

---

## 2. 8 Task A-F 逐項結論

### LG1-T1 H0 Blocking E2E integration test (h0_blocking.rs, +374 LOC)

| 項目 | 結論 |
|---|---|
| A. Thread-safety + race | ✓ test 5 (`test_h0_shadow_to_hardblock_race_safe`) flip 後 stats 對齊 + lease store 兩階段恆 0；無 race |
| B. Hot path SLA (E5 主審) | ✓ p99 0us < 1ms 達標（micros 解析度限制是合法 fail-soft）|
| C. Governance | ✓ 374 LOC < 800 警告；注釋全中文 + invariant 雙語；0 hardcoded path；0 unsafe / unwrap / expect（production code 範圍） |
| D. 邊界 / 失敗模式 | ✓ trigger_kill_switch 只 cover risk_envelope（1/5 sub-check）— E1 §8.1 self-flag P2 補；不阻 |
| E. Mock 不掩 | ✓ 6 個 test 真送 PriceEvent → real on_tick → 真驗 H0 stats / lease lock / paper_state / canary record，無 mock |
| F. PA spec drift | LG1-T3 ctor flip 已 land；helper `debug_assert!` 防呆 |

### LG1-T2 `[59]` h0_block_acceptance healthcheck (checks_h0_block_acceptance.py +468 + test +532)

| 項目 | 結論 |
|---|---|
| A. Race | ✓ 純讀 filesystem snapshot + PG SELECT；無寫；無 lock |
| B. Hot path SLA | ✓ healthcheck cron 不在 tick path；Linux PG empirical 0.7-8.8ms <<1s |
| C. Governance | ✓ 468 LOC < 800；中文 default；0 hardcoded path（`$OPENCLAW_DATA_DIR` env）|
| D. 邊界 | ✓ 7 verdict path（PASS / WARN_NO_SNAPSHOT / WARN_LOW_SAMPLE / WARN_SHADOW_MODE / FAIL_BLOCK_LEAKAGE / WARN_PIPELINE_QUIET / FAIL_TABLE_MISSING）；fail-soft on transient PG error |
| E. Mock | ✓ 14 unit test 用真實 dict + cursor sequence；無 mock parser |
| F. PA spec drift | **MEDIUM-1**: PA §1.5 mitigation 「讀 canary_records」**不存在 PG**（CanaryRecord 是 Rust internal struct → JSONL）。E1 改讀 `pipeline_snapshot_{engine}.json` filesystem + PG `trading.fills` 對 join → **E2 accept**（PA spec drift 合理 mitigation，accept 精神不變：「不新增 PG 表」）|

### LG1-T3 ctor default + Flip Runbook (pipeline_ctor.rs +22/-4 + h0_ctor_default.rs +157 + runbook +316)

| 項目 | 結論 |
|---|---|
| A. Race | ✓ ctor flip from `true→false` = fail-closed；shadow→hard race-safe（LG1-T1 test 5 同證）|
| B. Hot path SLA | ✓ N/A（ctor change 是 startup-time 一次性 init）|
| C. Governance | ✓ pipeline_ctor.rs 575 LOC < 800；中文注釋；0 hardcoded path |
| D. 邊界 | ✓ debug_assert in LG1-T1 helper 防 ctor 未來 flip 回 |
| E. Mock | ✓ 4 test PASS（new/with_balance/with_kind/set_shadow_mode）+ 1 `#[ignore]` reviewer note evidence |
| F. PA spec drift / **MEDIUM-2** | **PA §1.5 risk #1 mitigation 假設「TOML 載入路徑 always 覆蓋 ctor default」實證不成立**（E1 sibling test `test_lg1_t3_known_gap_apply_risk_snapshot_does_not_wire_h0_shadow_mode` `#[ignore]` 證實）— `pipeline_config.rs:97-109` H0Gate RMW **沒**推 `snap.runtime.h0_shadow_mode`，且 line 98 stale comment 「shadow_mode fields don't live in RiskConfig」與 `risk_config_advanced.rs:366` 矛盾。**E2 verdict**：5 LOC fix 不在 T3 範圍是合理 push back；ctor flip 已治本 fail-closed；**accept 為 P1 follow-up ticket**（建議 next wave 5 LOC fix 同 LG-2 T4 risk.rs 一道 commit）|

### LG1-T4 H0 Block Summary Route (risk_routes.py +410 LOC, NEW route)

| 項目 | 結論 |
|---|---|
| A. Race | ✓ 純 SELECT；無寫；`_count_fills_in_window` single SELECT per engine batch |
| B. Hot path SLA | ✓ Linux PG empirical 0.461ms execute / 10ms plan；mock pytest 21/21 in 0.40s |
| C. Governance | **P2-1**: risk_routes.py 708 → 1118 = +410 LOC；**>800 警告線**但 < 2000 hard cap；**§九 「pre-existing baseline exception clause」僅適用 baseline > 2000** — 不適用，屬「新 wave 推 ≤2000 到 ≤2000」常規 path。Open split ticket（建議拆 `h0_block_summary_routes.py` sibling）|
| C 額外 | ✓ `actor: Depends(base.current_actor)` 對 read-only 合規（非寫操作不需 _require_operator_role / _require_risk_write）；0 hardcoded path；中文 docstring|
| D. 邊界 | ✓ engine_mode whitelist 防 SQL injection；window_hours [1, 720] 邊界；PG 不可用 fail-safe → fills=0 + 200 不 5xx；snapshot 不可達 → engine_available=false WARN |
| E. Mock | ✓ 21 test 含 4 auth path (401 / 400 invalid / 400 window / response schema)；mock 真實 IPC snapshot dict + cursor |
| F. PA spec drift | 4 條 push back（E1 §4.1-4.4）：`by_strategy → by_reason`（H0 是 pre-strategy gate）/ `fills_during_block` 改語意（by-design 恆 0）/ `last_block_event_at_utc` snapshot.written_at_ms 近似 / 路徑 prefix `/api/v1/paper/risk/` 而非 `/api/v1/risk/`。**E2 verdict**：4 條全合理 accept（H0 真實是 pre-strategy gate；GateStats 真實無 per-event ts；router prefix 對齊既有 pattern）|

### LG2-T1 Pricing Binding Contract Tests (account_manager.rs inline +275 + lg3_contract.rs +521)

| 項目 | 結論 |
|---|---|
| A. Race | ✓ 純 unit + integration test；無 production 改動 |
| B. Hot path SLA | ✓ test 跑時間：inline 0.26s / integration 0.00s |
| C. Governance | **P2-2**: account_manager.rs 1404 LOC > 800 警告；E1 自報；**§九 exception clause 不適用**（baseline 1404 < 2000）。建議拆 account_manager_lg2_t1_tests.rs sibling，但不阻 deploy |
| C 額外 | ✓ lg3_contract.rs 521 < 800；中文 default；srv_root() helper 跨平台 dynamic |
| D. 邊界 | ✓ Cold default / Demo seed_default / Mainnet refused / LiveDemo accept 4 維 coverage；invariant 跨 3 環境 TOML 驗 (warn<fail / cold modes 不含 "live") |
| E. Mock | ✓ Bybit V5 response shape 真實 JSON 對齊 `docs/references/2026-04-04--bybit_api_reference.md:655-665` |
| F. PA spec drift | 3 條 push back（E1 §2）：`account_manager_tests.rs` 實為 inline `mod tests` / (e) hourly refresh task 在 binary `tasks.rs` integration 無法直驗 / LG-2 T3 sibling 並行整合 cross-ref。**E2 verdict**：全合理 accept；(e) 用「等價語意」(`tokio::time::interval` 50ms + `CancellationToken`) 是 acceptable trade-off（PA 沒指明 must hit binary crate；binary tasks.rs 已有自身 inline test）|

### LG2-T2 Startup Pricing Binding Assertion (live_spawn_assert.rs NEW 578 + integration ~190 LOC)

| 項目 | 結論 |
|---|---|
| A. Race | ✓ `wait_for_first_refresh_or_timeout` 純讀 AtomicU64 `last_fee_refresh_ms`；poll 200ms in 30s window；start: instant-baseline 走 spawn 路徑 cancel token 上層控制 |
| A 額外 | ✓ `assert_pricing_binding` 純同步 (no tokio::spawn)；SYMBOLS 5 const &'static str → 5 次 read lock；無 hot path（startup 一次性）|
| B. Hot path SLA | ✓ startup-time 非 tick hot path；fee_source() grep tick_pipeline/ + strategies/ = **0 hit**（無人在 tick path 用） |
| C. Governance | ✓ 578 LOC < 800；中文 default；0 hardcoded path；0 unsafe / unwrap / expect (production code) |
| D. 邊界 / **MEDIUM-3** | **30s wait 期間 cancel token 上層控制**：`tokio::time::sleep` 在 `cancel.cancelled()` race 下，若 build_exchange_pipeline 上層 cancel 觸發，wait_for_first_refresh_or_timeout 不會 cooperatively yield（無 `tokio::select!` 包 cancel.cancelled()）— 30s polling 內等 timeout / refresh ts 第一個非 0 才退出。**E2 verdict**：trade-off 接受（startup 一次性、30s 短窗、tokio::sleep 本身 cancel-aware，但 last_fee_refresh_ms() AtomicU64 poll 不 yield 給其他 task）；建議 P3 加 `tokio::select! { sleep(poll) => {} cancel.cancelled() => return Err }` 對齊 production cancel discipline |
| D 額外 | ✓ Live 6th gate ordering（HMAC → BybitRestClient::new → DCP → positions → fee refresh → **T2 pre-check** → balance fetch → WS spawn）合理；fee refresh 必先（seed_default fallback 保證 last_fee_refresh_ms > 0 OR Mainnet 必真 API） |
| D 額外 / **MEDIUM-4** | **audit log 走 tracing 非 PG row** — startup 在 db_pool 連線前，PA spec 未明指 storage；E1 採 systemd journalctl + engine.log 留證。**E2 verdict**：accept（db_pool 連線前無法寫 PG；tracing 有 journalctl 持久化 / grep-able target `openclaw_engine::live_spawn_audit`）；但**追加 P2 ticket** retrofit insert（engine 啟動 db_pool 後從 engine.log parse 補寫 PG row）以對齊未來 LG-3 supervised_live_audit table |
| E. Mock | ✓ 11 unit test 覆蓋 4 失敗路徑（NoRefresh / Insufficient / MainnetNonApi / LiveDemoNonApiStrict）+ 2 happy path（LiveDemo accept demo_conservative_default / accept cold_default in modes）+ Display + reason_code |
| F. PA spec drift | 4 條 push back（E1 §2）：`build_exchange_pipeline` 真實位置 `startup/mod.rs:496` 非 `bybit_rest_client.rs` / 新 module 放 lib crate / audit log tracing 非 PG / LiveDemo + ColdDefault 邏輯統一「mode_label in acceptable_modes → accept」。**E2 verdict**：全合理；E1 統一邏輯比 PA spec 寫死「ColdDefault → reject」更具表達力，且 risk_config_live.toml 的 cold_default_acceptable_modes=`["demo", "live_demo"]` 確實 contains "live_demo"（一致驗證 LiveDemo accept ColdDefault）|

### LG2-T3 FeeSource enum + IPC + Healthcheck dual-source (account_manager.rs +501 + handlers/fee_source.rs NEW 203 + checks_pricing_binding.py +184)

| 項目 | 結論 |
|---|---|
| A. Race | ✓ AccountManagerSlot 純 `Arc<RwLock<Option<Arc<AccountManager>>>>` late-inject；IPC handler `read().await` 非阻塞讀；slot=None → fail-soft uninitialized payload 不爆 error |
| A 額外 | ✓ slot 注入時序（main.rs L529 取 handle / L573 main_instruments 後 `replace(am)`）— IPC request 在注入前進來必走 None branch 回 `status=uninitialized`，fail-closed |
| B. Hot path SLA | ✓ IPC handler 純讀 `RwLock + HashMap.read()`，非 tick hot path（grep 證實 fee_source() / fee_rate_count() 在 tick_pipeline/strategies 0 hit） |
| C. Governance | **P2-2**: account_manager.rs 1404 > 800 警告（同 LG2-T1 P2，不重複算）；fee_source.rs 203 < 800；中文 default；0 hardcoded path；0 unsafe / production unwrap / expect |
| C 額外 / §九 Singleton 表 | **MEDIUM-5**: `AccountManagerSlot` 新增是 late-inject Arc，與既有 `CostEdgeAdvisorDbSlot` / `HStateCacheSlot` 同類；E1 §7.3 自報「§九 表已含『Rust 端 late-injected slot』一類，新 slot 不需新增獨立條目」— **E2 verify**：grep CLAUDE.md §九 表中**確實列了** HStateCacheSlot + CostEdgeAdvisorDbSlot 個別條目，未列 AccountManagerSlot。建議 **P2 ticket** PM 在 next meta-doc commit 加 row（與既有 pattern 對齊）|
| D. 邊界 | ✓ 4 rule (last_refresh==0 / cache miss / both default match / else) 邏輯封閉；浮點精確比對在 seed_default_fee_rates 直接賦常量場景安全（無中間運算）|
| D 額外 / **MEDIUM-6 (unresolved)** | **PA risk #4 「2 週觀察期後升 FAIL」schedule 無代碼層 enforcement**：`grep '2 週\|two weeks\|two-week'` healthcheck code = 只 4 hit 全在 comment / docstring（narrative only）。`OPENCLAW_LG2_T3_DUAL_SOURCE` env 預設關，operator 必手動 flip；沒 timer / calendar / TODO ticket grep hit。**E2 verdict**：建議 **必加 P2 ticket** 跟 deploy 後 2 週 calendar reminder（per memory `passive_wait_healthcheck` pattern：被動等待 TODO 必附 healthcheck check_X），否則 silent-dead 風險（operator 忘了升 FAIL）|
| E. Mock | ✓ 4 IPC tokio test（uninjected / missing symbol / cold_default / seed default）+ 9 Python test（compat 字典 5 + WARN-promotion 1 + IPC compat-no-change 1 + ipc-unavailable fail-soft 1 + env-disabled 1）|
| F. PA spec drift | 1 條 push back：46 個 ipc_server/tests/*.rs 加 slot arg + 6 file import 用 Python regex 批量處理。**E2 verdict**：accept（test plumbing 批量更新合理；ipc_server/tests/mod.rs 加 `empty_account_manager_slot()` helper 對齊 sibling cost_edge_advisor pattern）|

### LG2-T4 RiskConfig [pricing] section + 3 TOML (risk.rs +211/-10 + risk_config.rs +27 + risk_config_tests.rs +218 + 3 TOML +59)

| 項目 | 結論 |
|---|---|
| A. Race | ✓ `Option<PricingConfig>` 純 read-only field；ArcSwap snapshot 路徑既有；無新 mutable state；E1 §6 self-verify 「不需動 pipeline_config.rs RMW」(下游無 owned consumer)，2828 既有 test PASS 證 hot-reload 不破 |
| B. Hot path SLA | ✓ PricingConfig 非 tick hot path；validate() 在 RiskConfig.validate() 內，~3 boolean check + 1 contains "live" check，cost negligible |
| C. Governance | ✓ risk.rs 367 < 800；risk_config.rs 1216 < 2000；risk_config_tests.rs 1796 接近 2000 但 < 2000；中文 default；srv_root() 跨平台 |
| D. 邊界 | ✓ validate() 4 invariant（fail>0 / warn<fail / modes 非空 / 不含 "live"）；3 TOML 三環境 default 不一致（feedback_env_config_independence 對齊：paper 1440/10080/3 modes / demo 60/1440/3 modes / live 30/720/2 modes）|
| D 額外 | ✓ Mainnet hard-block 雙保險：PricingConfig::validate() 禁 "live" 在 modes + BybitEnvironment::Mainnet endpoint URL distinct + assert_pricing_binding `is_mainnet=true` 硬規則 reject 任何非 BybitApi（per `live_spawn_assert.rs:218-223`）|
| E. Mock | ✓ 8 types-layer test + 7 engine-layer test + 1 real TOML smoke（3 個真 disk read + validate）|
| F. PA spec drift | 2 條 push back（E1 §2）：PA 寫「4 個 TOML」實為 3 個 active + 1 legacy fallback (`risk_config.toml` 不加)，per `startup/mod.rs:196-203` 真實狀態；PricingConfig 放 openclaw_types（PA 同意採納）。**E2 verdict**：3 TOML 是 production 真實 wiring；legacy fallback `risk_config.toml` 走 Option None fallback 合理；小範圍 push back 全 accept |

---

## 3. 8 PA spec push back 逐條 E2 裁定

| Push back | 來源 | E2 verdict | 理由 |
|---|---|---|---|
| 1. PA §1.5 mitigation 「讀 canary_records」不存在 PG | LG1-T2 | **ACCEPT** | CanaryRecord 是 Rust internal struct → JSONL；E1 改 filesystem snapshot + PG join 等價符合「不新增 PG 表」精神 |
| 2. PA §1.5 risk #1 mitigation 「TOML always 覆蓋 ctor default」實證不成立 | LG1-T3 | **ACCEPT + P1 follow-up ticket** | `pipeline_config.rs:97-109` 漏推 `h0_shadow_mode`；E1 sibling `#[ignore]` test 證實 + stale comment line 98；ctor flip 已治本 fail-closed；5 LOC fix 不在 T3 範圍合理；建議 LG-2 T4 risk.rs 同 commit 修 |
| 3. PA §1.4 表 T1 「擴展 account_manager_tests.rs」實為 inline `mod tests` | LG2-T1 | **ACCEPT** | grep 確認無獨立檔；inline 是真實 baseline；E1 進此檔內擴展合理 |
| 4. PA §1.4 (e) hourly refresh task 在 binary `tasks.rs` 無法 integration 直驗 | LG2-T1 | **ACCEPT** | binary crate 不暴露 pub API；E1 用「等價語意」(`tokio::time::interval` 50ms + cancel) cover；binary tasks.rs 自身 inline test 已 cover 真實 task |
| 5. PA §1.4 「build_exchange_pipeline in bybit_rest_client.rs」實為 `startup/mod.rs:496` | LG2-T2 | **ACCEPT** | grep 確認真實位置；E1 採 startup/mod.rs 進入點正確 |
| 6. PA §2.4 「audit write」未指明 storage；E1 採 tracing 非 PG | LG2-T2 | **ACCEPT + P2 retrofit ticket** | startup 在 db_pool 連線前無法寫 PG；tracing 有 journalctl 持久化；建議 P2 ticket 待 db_pool ready 後 retrofit log→PG row mirror（對齊未來 LG-3 supervised_live_audit）|
| 7. PA §2.4 「LiveDemo + ColdDefault → reject」邏輯被 E1 統一為「mode_label in acceptable_modes → accept」 | LG2-T2 | **ACCEPT** | risk_config_live.toml `cold_default_acceptable_modes=["demo", "live_demo"]` 確實 contains "live_demo"；統一邏輯比 hard rule 更表達力 + 一致；雙重 test cover「modes 含 → accept」+「modes 不含 → reject」|
| 8. PA §2.4 「4 個 TOML」實為 3 個 active + 1 legacy fallback | LG2-T4 | **ACCEPT** | grep 確認 `risk_config_live_demo.toml` 不存在；LiveDemo 走 live TOML by env var；3 TOML active + 1 legacy fallback (走 Option None) 是真實 wiring |

**8/8 push back 全 ACCEPT**，3 個附 P2 follow-up ticket（pipeline_config.rs RMW fix / audit log retrofit / 2-week dual-source FAIL schedule）。

---

## 4. Governance compliance

### §九 文件大小

| 檔 | 行 | Cap | 狀態 |
|---|---|---|---|
| account_manager.rs | 1404 | 2000 hard / 800 warn | ⚠️ pre-existing > 800（baseline 903 + LG2-T1 6 inline test ~280 + LG2-T3 FeeSource ~221）|
| risk_routes.py | 1118 | 2000 / 800 | ⚠️ baseline 708 + LG1-T4 +410 = 1118 > 800 |
| risk_config_tests.rs | 1796 | 2000 / 800 | ⚠️ 接近 hard cap，後續 task 加 test 必拆 |
| live_spawn_assert.rs | 578 | 2000 / 800 | ✓ |
| live_auth_watcher.rs | 995 | 2000 / 800 | ⚠️ pre-existing > 800（baseline 既 970 + LG2-T2 +25）|
| pipeline_slot.rs | 908 | 2000 / 800 | ⚠️ pre-existing > 800（baseline 既 899 + LG2-T2 +9）|
| startup/mod.rs | 1243 | 2000 / 800 | ⚠️ pre-existing > 800（baseline 既 1161 + LG2-T2 +82）|
| main.rs | 1434 | 2000 / 800 | ⚠️ pre-existing > 800（baseline 既 1395 + LG2-T2 +39）|
| risk_config.rs | 1216 | 2000 / 800 | ⚠️ pre-existing > 800（baseline 1190 + LG2-T4 +26）|

**§九 「pre-existing baseline exception clause」適用範圍嚴格**：原文「僅適用 baseline > 2000」；本 wave 所有檔 baseline 均 < 2000，**不適用 exception clause**；屬「新 wave 推 ≤2000 到 ≤2000」常規 path（警告線 watch + 開 P2 split ticket，但不禁 merge，per E2 memory 2026-05-11 W2 IMPL chain lesson #1）。

**結論**：**3 P2 split ticket**（account_manager.rs / risk_routes.py / risk_config_tests.rs 3 個高優先；其他 4 檔（live_auth_watcher / pipeline_slot / startup/mod / main.rs）這 wave 僅微增量是低優先 P3）。

### §九 Singleton 表

`AccountManagerSlot` 是新加 late-inject Arc — `slots.rs:180`。E1 §7.3 自報「§九 表已含『Rust 端 late-injected slot』一類，新 slot 不需新增獨立條目」。

**E2 verify**：CLAUDE.md §九 表確實**個別列**了 `HStateCacheSlot` + `CostEdgeAdvisorDbSlot`，未列 AccountManagerSlot。**MEDIUM-5**：建議 **P2 ticket** PM 在 next meta-doc commit 加 row 與既有 pattern 對齊（不阻 deploy）。

### §七 中文注釋

8 個 task 新檔注釋全中文 + 重要 invariant 雙語對照（`grep MODULE_NOTE (EN)` = 0 hit 在新檔；live_auth_watcher.rs 既有雙語 MODULE_NOTE 動到的 block 端 E1 未清，per 2026-05-05 governance change「修改既有中英對照塊時移除英文只保留中文」屬未踐行但**未動到的 block** — 不算 violation）。

**結論**：✓ 8 task 全 §七 中文 default 合規。

### §四 Hard boundary 不變式

| 不變式 | 結論 |
|---|---|
| max_retries=0 | ✓ 不動 |
| live_execution_allowed | ✓ 不動 |
| execution_authority | ✓ 不動 |
| system_mode | ✓ 不動 |
| 5 Live gate（HMAC + freshness + env_allowed + secret + ALLOW_MAINNET） | ✓ LG2-T2 是第 6 gate 並列；既有 5 gate **全保留 unmodified**；E2 grep verify `startup/mod.rs:517-553`（Gate 1+2+3）保留；fee refresh + balance fetch + WS spawn 順序 unchanged |
| Decision Lease + Guardian + GovernanceHub | ✓ 不動 |
| authorization.json HMAC | ✓ 不動 |

### §七 跨平台 grep

```bash
grep -E '/home/ncyu|/Users/[a-zA-Z]*ncyu' [11 new/changed file] → 0 hit
```

✓ 全 8 task 0 hardcoded path violation。

### §四 unsafe / unwrap / expect 新增

| 檔 | unsafe | production unwrap | production expect |
|---|---|---|---|
| live_spawn_assert.rs | 0 | 0 | 0 |
| ipc_server/handlers/fee_source.rs | 0 | 0 (test only) | 0 (test only) |
| account_manager.rs | 0 | 0 (test only) | 0 (test only) |
| risk_routes.py | N/A | 0 | 0 |
| 其他 | 0 | 0 | 0 |

✓ 全部 unwrap / expect 在 `#[cfg(test)] mod tests` 內合規（test 預期 panic 是合理 pattern）。

### §五 SLA / hot path

- E5 主審 perf；E2 cross-check：fee_source() / fee_rate_count() / assert_pricing_binding **grep tick_pipeline/ + strategies/ = 0 hit**（無人在 tick hot path 用），純 startup-time + healthcheck IPC + LG-2 T2 spawn-time ✓
- LG-1 T1 p99 = 0us release build，達標 `< 1ms` SLA（micros 解析度 floor，per E1 §4 caveat）
- Live spawn pre-check 30s poll 在 startup 一次性，無 hot path 影響

---

## 5. SCOPE CREEP — **HIGH governance flag**

### 5.1 commit `a11a4df6 LG live gate checkpoint` 內含的 SCANNER-TRADEABLE-TIER-1 業務邏輯

E2 git show 揭露 commit `a11a4df6` 含 **8 task scope 外的業務邏輯改動**：

| File | 改動 | 性質 |
|---|---|---|
| `rust/openclaw_engine/src/strategies/bb_reversion/mod.rs` | +13 LOC `is_pinned` entry guard + tracing debug | **業務邏輯** |
| `rust/openclaw_engine/src/strategies/bb_reversion/tests.rs` | +90 LOC 2 new test (`test_non_pinned_symbol_skips_entry` + `test_non_pinned_self_owned_position_can_exit`) | test |
| `rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` | +13 LOC `is_pinned` entry guard + tracing debug | **業務邏輯** |
| `rust/openclaw_engine/src/strategies/ma_crossover/tests.rs` | +88 LOC 2 new test | test |

### 5.2 為何 HIGH governance flag

1. **不在 PA spec §1.4 LG-1 / §2.4 LG-2 任何 8 task scope**
2. **PA spec 沒 dispatch SCANNER-TRADEABLE-TIER-1 給 bb_reversion / ma_crossover**（只 `070ff0a3 P0 Option 2: SCANNER-PINNED-GATE-1` 已 dispatch grid_trading）
3. **commit message body 未 disclose** — 只寫「H0 block summary / healthcheck [59] / FeeSource / PricingConfig / Live spawn assertion」，無提 strategy entry gate
4. **業務邏輯改動未經 PA spec 派發**，違反 §八 強制工作鏈 PA→E1→E2→E4

### 5.3 E2 verdict on SCOPE CREEP

**不阻 LG-1 + LG-2 8 task review 結論**（PASS to E4），但**升 HIGH governance flag**：
- PM 在 push 前必額外 sign-off：是否認領此 SCANNER-TRADEABLE-TIER-1 為「checkpoint 同次 land 的 follow-up」（per `070ff0a3` 後續），OR 拆獨立 commit + 補 PA spec sign-off
- 若認領，本 review 對 4 strategy 檔案改動 **未做對抗 audit**（不在 scope）— PM 須評估是否 dispatch separate E2 review
- bb_reversion `is_pinned` entry guard 對 backtest / paper / demo 有真實行為改動（new entry refused on non-pinned symbol），可能影響 [40] realized edge 觀察期

**建議處置**：
1. PM 補對 SCANNER-TRADEABLE-TIER-1 bb_reversion + ma_crossover 改動的 PA spec entry（或標為 `070ff0a3` follow-up）
2. 此 wave 不阻 deploy，但 commit message body 應 amend 補 disclosure（git rebase 或 follow-up commit）
3. 此 commit 已 `[skip ci]`，CI 沒跑；E4 必須 cover bb_reversion + ma_crossover entry guard 真實行為（非 LG-1/2 scope，是 sibling concern）

---

## 6. Pre-existing flaky / fail 處理

### 6.1 stress_bb_reversion_extreme_oversold_bounce fail (pre-existing)

- E1 LG-2 T2 報告 §10.5 明確指認：**100% pre-existing W7-2 P0 Option A-Lite paper_state SSoT refactor 後 fixture 未同步更新**
- E2 grep `git log --oneline -3 rust/openclaw_engine/src/strategies/bb_reversion/` 看到 `6cdfe0dc P0 Option A-Lite E1-B` / `77a52796 P0 Phase 0 hot-fix` / `df0e2269 P1-1 bb_reversion W7-3` — 確認 W7-2/W7-3 wave 累積，LG-2 T2 無關
- **E2 verdict**：accept E1 self-flag；不阻本 wave 8 task review；W7 owner 修；屬 sibling concern
- **重要 cross-check**：**5.3 SCOPE CREEP** 已揭示 `a11a4df6` 同時 land bb_reversion/ma_crossover SCANNER-TRADEABLE-TIER-1 entry guard — E4 regression 必驗此 entry guard 是否 fix了 stress_bb_reversion_extreme_oversold_bounce OR 仍 fail（可能 fixture 同 wave 已修）

### 6.2 8 task baseline cargo test 數字

E1 reports 自報：
- LG-1 T1 baseline 2815 + 6 LG1-T1 test → 2827 PASS / 0 failed / 1 ignored
- LG-1 T3 +5 sibling test → 2827 + 5 = 2832 (但 LG-2 T3 sibling parallel land 後 baseline 漂)
- LG-2 T1 final 2849 PASS / 0 failed / 1 ignored
- LG-2 T2 final 2860 PASS / 0 failed / 1 ignored + binary 58/0
- LG-2 T3 final 2849 PASS（IPC slot 整合）
- LG-2 T4 final 2828 PASS（types layer 35 + engine layer 2828）

**E2 verdict**：baseline 漂是 parallel 並行 wave 自然現象；最終 commit `a11a4df6` 統一後 E4 regression 跑 full suite 重 verify（建議 E4 跑 2860+ baseline）

---

## 7. Direct fix (E2 直接修)

**0 個**。E2 不寫業務代碼，原則只接受 typo / lint / dead import 微修。本 wave 8 task 改動已 commit 入 main，無 working tree 改動可微修。

---

## 8. Issues returned to E1 (本 review 不 return；全 P2 follow-up ticket)

E2 對 8 task 內容 **無 BLOCKER / HIGH issue 需 E1 修**。所有 finding 是 P2/P3 follow-up ticket 或 governance flag（SCOPE CREEP 屬 PM 決策）。

### P1/P2 follow-up ticket（建議 PM 開）

| Ticket | 內容 | 嚴重性 |
|---|---|---|
| P1-LG1T3-RMW-WIRE | `pipeline_config.rs:97-109` H0Gate RMW 加 `h0.shadow_mode = snap.runtime.h0_shadow_mode;` + 刪 line 98 stale comment + 移除 sibling test #5 `#[ignore]`（5 LOC） | P1（不阻當前 deploy，但是 PA spec mitigation 假設不成立修復）|
| P2-LG1T4-SPLIT | risk_routes.py 1118 LOC > 800 → 拆 `h0_block_summary_routes.py` sibling | P2 |
| P2-LG2T1T3-SPLIT | account_manager.rs 1404 > 800 → 拆 `account_manager_lg2_t1_tests.rs` OR LG2_T3 FeeSource 獨立檔 | P2 |
| P2-LG2T4-TEST-SPLIT | risk_config_tests.rs 1796 接近 2000，後續 task 加 test 必拆 | P2 |
| P2-LG2T2-AUDIT-RETROFIT | live spawn audit log tracing → 待 db_pool ready 後 retrofit PG insert（對齊未來 LG-3 supervised_live_audit table） | P2 |
| P2-LG2T3-2WEEK-FAIL-SCHEDULE | dual-source disagree 升 FAIL 的 2-week schedule 無代碼 enforcement → 加 calendar reminder OR healthcheck check_X 跟 deploy 後 14d 自動評估 | P2 |
| P2-LG2T3-SINGLETON-TABLE | CLAUDE.md §九 Singleton 表加 AccountManagerSlot row | P2 |
| P3-LG2T2-CANCEL-DISCIPLINE | wait_for_first_refresh_or_timeout 加 `tokio::select! { sleep => {} cancel.cancelled() => return Err }` 對齊 production cancel discipline | P3 |
| P3-LG1T1-PERF-NANO | H0 latency assertion 從 micros → nanos 解析度（per E1 §10 caveat）| P3 |

### HIGH governance flag → PM action

1. **SCOPE CREEP audit** — `a11a4df6` 含 bb_reversion + ma_crossover SCANNER-TRADEABLE-TIER-1 業務邏輯改動未 PA dispatch；PM 決定：
   - (a) 認領為 `070ff0a3` 後續 + 補 amend commit message disclosure，OR
   - (b) 拆獨立 commit + 補 PA spec entry + 派 sibling E2 review

---

## 9. E2 對抗反問結果

| Q | A from E1 reports | E2 評估 |
|---|---|---|
| LG2-T2 wait_for_first_refresh_or_timeout(30s) timeout 期間 engine block startup？ | E1 §4.2：30s 內 last_fee_refresh_ms 仍 0 → reject spawn return None | ✓ 設計合理；poll 200ms × 150 次；無 hot path 影響；不 block engine（startup 一次性） |
| LG2-T2 LiveAuthWatcher respawn 取 pricing 路徑正確？ | E1 §6 + §8.3：watcher run loop 取 `risk_live_store.load().pricing` 每次 respawn fresh ArcSwap | ✓ E2 grep verify `live_auth_watcher.rs:734-738` — `Option::and_then(...).unwrap_or_default()` 雙層 fallback safe |
| LG2-T3 IPC slot 注入前 race 怎處理？ | E1 §3.4 + handler line 68-75：`guard.as_ref()` None → uninitialized payload | ✓ fail-soft；Python 端視 silent-dead branch 處理 |
| LG-1 T4 SQL injection? | engine_mode whitelist + `%s` ANY(%s) 參數化 | ✓ 雙保險 |
| LG2-T4 PricingConfig hot-reload 真生效？ | E1 §6：ConfigStore::swap → sync_risk_config_if_changed → apply_risk_snapshot（既有 ArcSwap 路徑） | ✓ E2 grep `pipeline_config.rs:97-109` H0Gate RMW 不 reset PricingConfig（不是 RMW 對象，是 ArcSwap snapshot pass-through）|
| LG2-T2 audit log 持久化？ | E1 §12：tracing target=`openclaw_engine::live_spawn_audit` → systemd journalctl | ✓ accept；待 P2 retrofit |
| LG-1 T2 healthcheck 全 fail-soft 路徑都驗了？ | E1 §6：14 test 覆 7 verdict path + 3 helper sanity | ✓ + E2 額外驗 `(OSError, json.JSONDecodeError)` exception 順序對 |
| LG2-T1 mainnet hard-block 雙保險真破不了？ | PricingConfig::validate() + BybitEnvironment endpoint + assert_pricing_binding is_mainnet 硬規則 | ✓ E2 cross-verify 三層 defense；不變式不可違 |

**8 對抗反問全通過**。

---

## 10. Files reviewed

### Rust 新檔 / 大改
- `rust/openclaw_engine/src/live_spawn_assert.rs` (NEW 578)
- `rust/openclaw_engine/src/ipc_server/handlers/fee_source.rs` (NEW 203)
- `rust/openclaw_engine/src/tick_pipeline/tests/h0_blocking.rs` (NEW 374)
- `rust/openclaw_engine/src/tick_pipeline/tests/h0_ctor_default.rs` (NEW 157)
- `rust/openclaw_engine/tests/lg3_contract.rs` (NEW 521)
- `rust/openclaw_engine/src/config/risk_config_tests.rs` (+234)
- `rust/openclaw_types/src/risk.rs` (+236)
- `rust/openclaw_engine/src/account_manager.rs` (+501，含 FeeSource enum + getter + 6 LG2-T1 test + 7 LG2-T3 test)
- `rust/openclaw_engine/src/startup/mod.rs` (+82 LG-2 T2 integration)
- `rust/openclaw_engine/src/live_auth_watcher.rs` (+27 LG-2 T2 risk_live_store wire)
- `rust/openclaw_engine/src/pipeline_slot.rs` (+9 pricing_config pass-through)
- `rust/openclaw_engine/src/main.rs` (+39 LG-2 T2 SpawnConfig + LG-2 T3 slot inject)
- `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs` (LG-1 T3 ctor flip + 注釋)
- `rust/openclaw_engine/src/ipc_server/{server, connection, dispatch, slots}.rs` (+73 LG-2 T3 IPC wiring + 6 test file plumbing)

### Python 新檔 / 大改
- `helper_scripts/db/passive_wait_healthcheck/checks_h0_block_acceptance.py` (NEW 468)
- `helper_scripts/db/test_h0_block_acceptance.py` (NEW 532)
- `helper_scripts/db/passive_wait_healthcheck/checks_pricing_binding.py` (+184 LG-2 T3 dual-source)
- `helper_scripts/db/test_pricing_binding_healthcheck.py` (+195)
- `helper_scripts/db/passive_wait_healthcheck/runner.py` (+46 LG-1 T2 register check_59)
- `program_code/.../app/risk_routes.py` (+410 LG-1 T4 H0BlockSummary route)
- `program_code/.../tests/test_h0_block_summary_route.py` (NEW 468)

### Config
- `settings/risk_control_rules/risk_config_paper.toml` (+18 [pricing])
- `settings/risk_control_rules/risk_config_demo.toml` (+19 [pricing])
- `settings/risk_control_rules/risk_config_live.toml` (+22 [pricing])
- `settings/risk_control_rules/scanner_config.toml` (+8) — SCOPE CREEP 部分？需 PM confirm

### SCOPE CREEP scope（**未深入 audit**，僅 grep）
- `rust/openclaw_engine/src/strategies/bb_reversion/mod.rs` (+19)
- `rust/openclaw_engine/src/strategies/bb_reversion/tests.rs` (+248)
- `rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` (+20)
- `rust/openclaw_engine/src/strategies/ma_crossover/tests.rs` (+119)

### PA spec
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_2_3_4_design_plan.md` (full read)

---

## 11. Decision summary

- **APPROVE WITH 4 MEDIUM / 2 LOW / 3 P2 / 1 HIGH governance flag**
- **PASS to E4 regression**
- **E5 perf audit parallel** can proceed
- **A3 UX/runbook audit parallel** can proceed
- **PM 在 push 前 must sign-off SCOPE CREEP** decision（authorize SCANNER-TRADEABLE-TIER-1 bb_reversion/ma_crossover OR split commit）
- **3 P1/P2 follow-up ticket 必開**（pipeline_config RMW + audit log retrofit + 2-week FAIL schedule）

---

E2 REVIEW DONE: APPROVE WITH MINOR · PASS to E4 · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-11--wave2_2_lg1_lg2_e2_review.md`
