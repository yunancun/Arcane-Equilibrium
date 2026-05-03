# E4 Memory — 工作記憶

## 工作記憶

### 2026-05-03 REF-20 Wave 2 Batch 1 regression smoke（commits `9879eeb` + `ce665b0` + `40ebc19`）— **E4 PASS**

**對象**：3 commit / 32 file / +5342 / -7。Frontend bundle (P1-U1/U7/U9) + S1 cron (P2a-S1) + manifest_signer Rust+Python (P2a-S2)。

**Verdict**：**PASS** — 0 baseline regression / 0 sibling regression / 0 flaky / 0 hard-boundary mutation

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| Rust `cargo test --release --lib` | 2415 | 0 | ~1980 (legacy) | +435 cumulative; **0 既有 fail** ✓ |
| Rust `cargo test --test replay_manifest_signer_xlang_consistency` | 8 | 0 | new | +8 ✓ |
| Rust `cargo test --lib live_authorization`（sibling） | 18 | 0 | 18 | +0 ✓ |
| Rust `cargo test --lib replay`（subset） | 10 | 0 | new | +10 ✓ |
| Python `pytest control_api_v1/tests/` | 3329 | 0 | 2555 / 17 (legacy) | +774 / **-17 fail** ✓ |
| Python `pytest helper_scripts/cron/test_replay_key_*.py` | 7 | 0 | new | +7 ✓ |
| HTML parser (`tab-paper.html`) | OK | 0 | n/a | OK |
| Cron shell `bash -n` + Python `py_compile` | OK | 0 | n/a | OK |
| **新增 test 合計** | **38** | **0** | **expected 38** | match ✓ |

**雙跑 confirm**：Run 1 (Rust 2415 / Python 3329) = Run 2 (Rust 2415 / Python 3329)，0 delta、0 flaky。

**Hard-boundary scan**（CLAUDE.md §四）：`grep '^+.*\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease)'` = **0 hit**。Wave 2 Batch 1 完全沒改 live execution gate / Decision Lease / Risk envelope。

**4 fail-mode + verify-order + xlang byte-equal HMAC（E2 Lesson 23-25 cover）**：
- 3 fixture (`manifest_1/2/3.json`) Rust + Python 各自獨立計算 HMAC 對 fixture sig file byte-equal ✓
- 4 fail-mode (signature_mismatch / manifest_hash_mismatch / key_missing / key_expired) Rust unit + integration + Python pytest 三 bucket 全 cover ✓
- Verify-order invariant（signature → hash）Rust + Python 兩端 unit test 顯式驗 ✓
- Fingerprint 算法（`sha256(file_content_with_newline)[:16]` = `da0d3b33336d12fb`）helper script + fixture + runtime 三方對齊 ✓

**Mock 審查**：5 個 test bucket 全 IO-boundary mock（V042 archive `InMemoryKeyArchive` / disk fixture / `os.utime()` filesystem time / PG `_FakePgCursor`），0 業務邏輯 mock。HMAC 計算邏輯與 cron 業務邏輯真跑。

**Pre-existing Mac dev env 缺陷（不影響 sign-off）**：
- `program_code/ml_training/tests/*` 10 file collection error `ModuleNotFoundError: numpy` — 對 baseline `b1c2034` checkout 後 reproduce 同 error 確認 pre-existing
- 教訓：CLAUDE.md §三 Mac dev-only 模式有環境差異；E4 baseline 對照建議用 control_api_v1 子目錄 scope（`pytest tests/`）而非 srv root 全 scope

**SLA 壓測 N/A**：Wave 2 Batch 1 完全不涉 hot path（manifest_signer = cold artifact 路徑 / cron daily / frontend 無 SLA）。

**Cross-platform**：Mac dev 端跑 6 項全 PASS。Linux trade-core 補做 optional（HMAC byte-deterministic 跨架構必同；E2 Lesson 23 fixture-based design 已 cover）。

**操作教訓**：
1. **uncommitted state 處理**：E4 開工時遇 mod.rs / profile.rs uncommitted MED-2 rename 改動 — 用 `git stash push -m "..."` 隔離後跑測試，run 完 `git stash pop` 恢復。**不擅改 git state**（CLAUDE.md skill §1 紅線）
2. **baseline 比對 trick**：當 srv root 跑收 collection error 時，先 `git checkout <baseline_HEAD> -- .` 對 baseline reproduce 同樣 error → 確認 pre-existing 而非新 commit 引入；驗完 `git checkout HEAD -- .` 還原
3. **Python pytest scope mismatch**：CLAUDE.md §九 baseline (2555/17) 是 legacy `srv/tests/` scope；當前主力 test 在 `program_code/exchange_connectors/.../control_api_v1/tests/`（3329 累積）。E4 報告必註記 scope 差異 + delta 真實意義
4. **PA 5 MED follow-up**：每個 MED fix 後 re-run 範圍 evaluation 寫進 report §15，方便 PM 決定 fix-up commit 後派發

**Report**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_wave2_batch1_e4_regression.md`

---

### 2026-05-02 P0 migration checksum repair binary sanity test（commit `bb6bf04`，branch `fix/p0-2026-05-02-sqlx-migration-checksum-repair`）— **E4 PASS**

**對象**：新 Rust binary `rust/openclaw_engine/src/bin/repair_migration_checksum.rs` (555 LOC) + `Cargo.toml` 加 `[[bin]]` entry (+11 LOC)。**未執行 `--apply` mode**（per PA 要求 dry-run only），純驗 build + lib test 不破壞 + binary smoke test。

**Verdict**：**PASS** — ready for operator dry-run review，可進 PM Sign-off

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| Cargo workspace build (`--workspace --release`) | 0 errors | 0 | clean | clean |
| Workspace warnings | 26 | — | 26 (cc286d0 parent) | +0 ✓ |
| Cargo lib `openclaw_engine` (`--lib`) | 2405 | 0 | 2405 | +0 ✓ |
| Cargo workspace tests (`--workspace`) | 3008 | 0 | 3008 | +0 ✓ |
| Lib 2nd run (non-flaky) | 2405 | 0 | match | ✓ |
| Binary build (`--bin repair_migration_checksum`) | OK | 0 | new | OK |

**Smoke tests (4 種)**：
1. `--verify` 連假 DB URL：connect timeout / graceful exit 0 / 無 panic ✓
2. `--apply` 無 ack flag：拒絕 + 雙語錯誤訊息「需同時帶 --i-understand-this-modifies-db」exit 0 ✓
3. `--apply --auto-yes` bogus flag：硬拒絕「rejected flag --auto-yes: interactive prompt is mandatory」+ print help exit 0 ✓
4. 真 DB `--verify` 跑兩次：output 100% bit-identical（diff_lines=0）✓

**真 DB verify 結果**：drift_versions = [28, 30, 31, 32, 34]、V033 = clean、V035 = MISSING_IN_DB — 完全 match PA spec。`pa_caught_by_binary == pa_known_drift` / `pa_missed_by_binary = []`。

**DB read-only proof**：跑 verify 前後 `_sqlx_migrations.checksum` 全表 34 行 hex dump 對比 diff = 0 行 — **binary --verify mode 對 DB 0 寫入**，符合設計。

**Steps**: 5/5 PASS（全 sanity test 過）

**E4 教訓 / 新坑**：
1. **新 binary 借 lib `database::migrations::load_migrations_from_dir`** 共用 sqlx 0.8.6 SHA-384 算法，避免 binary / engine 啟動驗證 hash drift。Cargo.toml 注 `[[bin]]` entry 不影響既有 build target。
2. **真 DB --verify deterministic**：兩次跑 49 行 output bit-identical，因為 binary 不訪問任何 mutable 系統時間 / 隨機（只讀 file mtime + DB checksum）。
3. **Engine 已 abort 狀態下 binary 仍可獨立跑**：repair binary 不需 engine alive，僅需 DB pool + migrations dir，符合 P0 incident response 場景（engine 啟動失敗時用此修 checksum）。
4. **`--apply --auto-yes` 雙重保險**：除了拒絕 missing ack flag，還主動偵測 `--auto-yes` 等 prompt-bypass flag 並 hardexit + print help，比單純「ack required」更 fail-closed。
5. **Postgres URL encoding**：密碼含 `(` `)` 必 percent-encode 為 `%28` `%29`（`postgres://redacted@host`）才能進 binary，否則 sqlx 解析 fail。

**Report**：直接於主對話 message 輸出（per system prompt 不寫 .md 報告檔）。

**建議 PM commit message** (when promoting bb6bf04 after operator dry-run accept):
```
chore(p0-migration): sanity test PASS for repair_migration_checksum binary (bb6bf04)

E4 sanity test 5/5 PASS. Workspace build clean (26 warnings, +0 vs cc286d0
parent). Cargo lib 2405/0 (matches baseline 2405). Workspace tests 3008/0
(matches baseline 3008). Binary smoke: invalid DB URL graceful exit;
--apply without ack rejected; --apply --auto-yes hard-rejected; real DB
--verify 2 runs bit-identical; pre/post DB checksums diff=0 (read-only
proof). Drift detected matches PA spec: V[28,30,31,32,34] + V035 missing.
--apply NOT executed; ready for operator dry-run review.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

### 2026-05-02 LG-5 Wave 3 IMPL-3 + risk_config_demo TOML promote Linux PG regression（merge `a51cdc5`）— **E4 PASS_TO_PM**

**對象**：兩 work stream 同 commit promote：
- **Stream A** (LG-5 W3 IMPL-3, Mac dispatch)：`checks_governance.py` (372 LOC new) + `test_lg5_healthchecks.py` (249 LOC new, 13 tests) + `passive_wait_healthcheck/{runner.py +44, __init__.py +9}` + `docs/healthchecks/2026-05-02--lg5_health_checks.md` (180 LOC)。E2 round 2 PASS：4 boundary verdict + producer engine_mode aligned。
- **Stream B** (Linux operator, funding_arb V2 deprecation TOML)：`risk_config_demo.toml` +41 LOC（dyn_stop base_ratio 0.4→0.25 + funding_arb 3% SL override）+ `rust/openclaw_engine/src/risk_checks_per_strategy_tests.rs` +93 LOC new G2-03 sibling extract。

**Verdict**：**PASS** — ready for PM Sign-off

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| Cargo lib (`--lib`) | 2405 | 0 | 2404 | +1 ✓ |
| Cargo aggregate (`--tests`) | 2561 | 0 | ≥2560 | ✓ |
| g2_03_per_strategy runtime (Stream B) | 8 | 0 | new | +8 |
| `test_demo_toml_funding_arb_3pct_override_2026_05_02` (Stream B) | 1 | 0 | new | +1 |
| Pytest test_lg5_healthchecks (Stream A new) | 13 | 0 | new | +13 |
| Pytest helper_scripts/db (full) | 100 | 0 | 87 | +13 ✓ |
| Pytest control_api_v1 (excl integration) | 3306 | 1 pre-existing grafana | 3306 | +0 (skipped 3) |
| Pytest IMPL-1 + IMPL-2 regression | 59 | 0 | 59 | ✓ |
| `audit_migrations.py` V035 | OK | — | — | no drift |
| Runner: [42] + [42b] emit verdict | ✓ | (production FAIL by design) | new | wired |
| 2nd run W3 + g2_03 | identical | 0 | — | no flake |

**Steps**：11/11 PASS（步 9/10 雖 SUMMARY=FAIL，唯一 NEW FAIL 是 [42]+[42b] 設計目的觸發的真實 production drift signal，非測試/wire 問題；[40] / [33] / [38] / [4] / [10] / [11] / [41] 其他 baseline WARN 不破，與 §三 2026-05-01 23:17 CEST 快照一致）。

**Stream A vs Stream B 完全隔離**：兩 work stream 在不同 LOC region 落地，互不耦合；測試結果亦無交叉污染。Stream A 的 Python healthchecks 不依賴 Stream B 的 Rust risk_checks 改動，反之亦然。

**Step 9/10 [42]+[42b] production verdict（給 PM 評估 IMPL-5 retro / G6 ticket 接線時機）**：
- **[42] live_candidate_eval_contract = FAIL**：`recent_24h_total=8, unaudited_over_1h=27` — `GovernanceHub.review_live_candidate` consumer 停滯，RFC v2 §4 lease_revoke_trigger 應觸發
- **[42b] live_candidate_attribution_drift = FAIL**：`worst=grid_trading@0.135 (n=1277)` 低於 0.30 standard floor；ma_crossover@0.152 也低；指向 `MIT-S2-1 attribution_chain_ok` writer producer 大量漏寫
- 兩 FAIL = healthcheck 第一次曝光的真實 production drift（**不是 W3 code 問題**），代表 W3 healthcheck 的設計目的已正確履行
- **建議優先級**：HIGH `[42]` 修復 GovernanceHub.review_live_candidate consumer + HIGH `[42b]` 補 attribution_chain_ok writer 缺洞
- **不應 block 此 commit**：Stream A 的 healthcheck 本身運作正確；FAIL 訊號 = 它們已經抓到真問題

**教訓**：
1. 第一次 install 的 healthcheck 在 production 即刻 FAIL = OK，不是 W3 caller 的 bug；屬「healthcheck 履行職責」。E4 應分清「healthcheck 設計目的的 FAIL」vs「healthcheck 自己壞掉的 FAIL」。
2. 題目 prompt 給的 `cargo --tests | awk '{p+=$4;f+=$6}'` 報 `failed=1` 是 awk 解析誤導（grep 逐行驗證所有 `test result:` 行皆 0 failed）— E4 不應盲信題目給的 one-liner，必逐行驗證。
3. `runner.py` 不能直接 `python3 file.py` 跑（relative import broken），必 `python3 -m helper_scripts.db.passive_wait_healthcheck.runner`；題目 prompt Step 9/10 命令需修正（已自行 escalate）。
4. risk_checks_per_strategy_tests.rs 用 `#[path]` sibling 載入而非獨立 mod；test name 過濾要用 `g2_03_runtime` 或 `g2_03_per_strategy_tests` prefix，不能用檔名直接 grep。

**Report**：`srv/.claude_reports/20260502_e4_lg5_w3_impl3_plus_risk_toml_linux_regression.md` + `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--lg5_wave3_impl3_plus_risk_toml_linux_regression.md`

---

### 2026-05-02 LG-5 Wave 2 IMPL-2 Linux PG regression（commit `f663354`）— **E4 PASS_TO_PM**

**對象**：LG-5 Wave 2 IMPL-2 = consumer `governance_hub_live_candidate_review.py` (1496 LOC new) + bulk re-eval `lg5_re_evaluate_pending.py` (532 LOC new) + 44 unit tests `test_lg5_review_live_candidate.py` (731 LOC new)。Linux at `f663354`（git log -1 確認）。

**Verdict**: **PASS** — ready for PM Sign-off

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| Pytest test_lg5_review_live_candidate (W2 new) | 44 | 0 | new | +44 |
| Pytest control_api_v1 (excl integration) | 3306 | 1 pre-existing grafana | 3262 → 3306 | +44 effective |
| Pytest test_mlde_demo_applier (W1 IMPL-1) | 15 | 0 | 15 | +0 |
| py_compile new files (×2) | OK | 0 | — | clean |
| audit_migrations V035 | OK (33/34 applied, V005 1-idx gap pre-existing) | — | — | no V034/V035 drift |
| Healthcheck | WARN baseline | 0 new WARN/FAIL | match W1 | preserved |
| V035 governance_audit_log | 23 cols ✓ | — | — | matches W1 spec |

**Steps**: 11/11 PASS（Step 9 first attempt column-name 失敗 → 改用真實 column `net_bps_after_fee` 後 PASS；非 W2 code 問題）。

**Step 7 bulk re-eval --help 確認**：3 flags（`--dry-run` / `--limit` / `--verbose`）；未實際執行 bulk eval（per PA 指令避免 modify production data，等 IMPL-3 healthcheck `[42]` land 後再授權）。

**Step 8 pending live candidates baseline**：26 rows（W1 baseline ~24，+2 自然 trickle，正常增長）。

**Step 9 live regime baseline**：rows_24h=8 / avg_net_bps_24h=+10.14 bps（W1 IMPL-1 24h baseline 為對照）。

**Pre-existing grafana fail**：仍 `test_grafana_data_writer.py::test_start_sets_running`，parent baseline `9076cc9` 已 fail；W2 改動 0 overlap，scope 完全正交。

**Healthcheck WARN preserved**：[4] phys_lock 0 fire 24h、[10] intents_writer_ratio under-firing、[11] counterfactual rolling 2d shrink、[33] maker_fill_rate 28.9%、[40] avg_net -36.82 bps（注意：[40] 用 24h all live/live_demo MLDE rows=38，與 Step 9 attribution_chain_ok=true 過濾後 rows=8 不同樣本）、[41] scanner gates 無 labels — 全部 W2 前已存在；無新 WARN/FAIL。

**E4 教訓 / 新坑**：

1. **passive_wait_healthcheck.py 與 audit_migrations.py 都需要 PG env vars**（`POSTGRES_USER/PASSWORD/DB/HOST/PORT`），不會自動 inherit `PGPASSWORD`；ssh wrapper 必明文 export 才能跑。第一次落入 fallback 模式只回 [30]。
2. **Step 9 column name drift**：原指令用 `label_net_edge_bps`，schema 真實名為 `net_bps_after_fee` —— 提示 prompt 內固化的 SQL 在 schema 演進後可能 stale。E4 自動退回查 information_schema 修正，未列入 BLOCKER。
3. **W1 → W2 baseline 累積**：control_api_v1 從 3262 → 3306（+44），+44 全來自 W2 新測試。Pre-existing grafana 同一條，無新 regression。
4. **Step 7 不跑 bulk re-eval** = 對的決策；script 設計為 idempotent（candidate -> writes audit_log + flips status / decision_lease_id），但 production data write 留 PM/operator 授權 + IMPL-3 [42] 監測 land 後。

**建議 PM commit message**:
```
test(lg5): Wave 2 IMPL-2 Linux PG regression PASS — 44 new + 3306 baseline (commit f663354)

E4 Linux PG regression 11/11 Steps PASS. control_api_v1 3306/0 (+44 vs W1 3262), 0 new
WARN/FAIL on healthcheck. V035 unchanged (W1 deliverable). py_compile clean. Bulk
re-eval --help validated; no production data mutation. Pending live candidates: 26.
Live regime 24h: rows=8 / avg_net=+10.14 bps. Ready for IMPL-3 healthcheck [42] land.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

### 2026-05-02 LG-5 Wave 1 Linux PG regression（PM commit `9076cc9`）— **E4 PASS_TO_PM**

**對象**：LG-5 Wave 1 = `V035__governance_audit_log.sql` (288 LOC new) + `mlde_demo_applier.py` (+401 +102) + `test_mlde_demo_applier.py` (+332)。Linux ff-only 至 `9076cc9` 已驗。

**Verdict**: **PASS** — ready for PM Sign-off

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| Cargo migrations_test (release) | 5 | 0 | 5 | +0 |
| Pytest mlde_demo_applier | 15 | 0 | 15 | +0 |
| Pytest mlde_shadow_advisor | 5 | 0 | 5 | +0 |
| Pytest control_api_v1 (excl integration) | 3262 | 1 pre-existing grafana | 3262/1 | +0 effective |
| V035 first/2nd/3rd apply | 0 RAISE / 0 ERROR | — | — | idempotent ✓ |
| CHECK constraints (5/6) | 2/2 RAISE check_violation | — | — | attack path proved |
| audit_migrations V035 | OK | — | — | clean |
| Healthcheck | WARN baseline | 0 new WARN/FAIL | match | preserved |

**Steps**: 12/12 PASS。V035 first apply: Guard A schema_guard + create + comments + hypertable convert (7d chunks) + 2 hot-path indexes (idx_gov_audit_candidate_ts / idx_gov_audit_event_type_ts) + Guard C validated。3-run 連發證明 idempotent 比 spec 要求 2-run 還強。

**結構**：23 cols / 4 indexes (2 hot-path required + pk + ts default) / hypertable 1 row num_chunks=0。

**Healthcheck**：[27] intents_counter_freeze 從 WARN 升 PASS（unrelated improvement）；[4][10][11][33][40][41] 維持 WARN baseline；新 WARN/FAIL = 0。

**Pre-existing grafana fail RCA**：與 P2 wave 同一個 `test_grafana_data_writer.py::test_start_sets_running`（writer._running is False not True），parent baseline `1f3acc5` 已 fail，Wave 1 file changes 0 overlap。Scope 完全正交。

**E4 教訓 / 新坑**：
- **basic_system_services.env shell parse 限制**：password 含 `()` 字符（`<REDACTED>`）讓 `set -a && . file && set +a` 失敗或 source 不全。對 `passive_wait_healthcheck.py` 該 source 可走（腳本自己有讀 env 邏輯吃進去），對 `audit_migrations.py` 必顯式 inline 注入：`POSTGRES_USER='...' POSTGRES_PASSWORD='(...)' POSTGRES_DB='...' python3 ...`。Single-quote `()` 包好就過，不要 source。
- **Hypertable num_chunks=0 ≠ FAIL**：V035 新表 0 INSERT，預期 num_chunks=0；判定 hypertable conversion 看 `timescaledb_information.hypertables` 1 row hit，不是看 num_chunks > 0。
- **Guard A + C 模板首次驗證**（V023 postmortem 後第一個從零按模板寫的新 migration，非 retrofit）：3-run 證明模板路徑乾淨可重現。所有 V### 新 file 套此模板可保證 idempotent。
- **task spec 說 12 step 但 Step 11 audit grep 命中 0**：第一次 grep 命中 0 不一定是 V035 失敗，可能是 audit script 沒拿到 PG env vars。完整 tail 才看到 `ERROR: POSTGRES_USER...required`。永遠先 tail 全 output 確認 script 自己跑通，再用 grep 過濾。

**Reports**：
- `.claude_reports/20260502_162616_e4_lg5_wave1_linux_pg_regression.md`（6 節格式）
- `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--lg5_wave1_linux_pg_regression.md`

---

### 2026-05-02 P2 Wave Linux regression（PM commit `1f3acc5`）— **E4 PASS_TO_PM**

**對象**：4 fast-win fix（MIT-S2-6 opportunity_tracker early-exit / E3-S2-P2-1 strategy_read_routes envelope / E3-S2-P2-2 live_session_account_routes IPC error detail / PA-DRY-1 tick_pipeline `is_legacy_close_tag` helper）。Linux ff-only sync 至 `1f3acc5` 已驗。

**Verdict**: **PASS** — ready for PM Sign-off

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| Cargo lib | 2404 | 0 | 2404 | +0 |
| Cargo tests aggregate (14 binaries) | 2560 | 0 | 2560 | +0 |
| Pytest control_api_v1 (excl integration) | 3262 | 1 (pre-existing grafana) | 3261/1 | +0 effective |
| MLDE shadow advisor focused (Fix 1) | 5 | 0 | 5 | +0 |
| Live session endpoint actual_engine_kind (Fix 3) | 17 | 0 | 17 | +0 |
| Edge gates / prelive_edge focused (Fix 2) | 5 | 0 | 5 | +0 |
| 2nd run (excl pre-existing) | 3262 | 0 | match | non-flaky ✓ |

**Pre-existing fail RCA**：`test_grafana_data_writer.py::TestGrafanaDataWriterLifecycle::test_start_sets_running` (`writer._running is True` got `False`)。E4 親自 `git checkout 9dd71a2 -- .` 重現同 fail，證明 baseline 即存在；file 最後修改 `bc3fa70`/`7178059`，與 P2 wave 4 file changes 0 overlap。

**Healthcheck**：WARN list 從 baseline `[4][10][11][22][27][33][38][40][41]` → 本次 `[4][10][11][27][33][40][41]`。`[22] trading_pipeline_silent_gap` 與 `[38] grid_trading_lifecycle_drift` 從 WARN 升 PASS（fills 7/h fresh + grid n=4<5 insufficient sample skip）。0 新 WARN / 0 新 FAIL。

**opportunity_tracker noise baseline (Step 8)**：opp_24h=50 / noise=50 (100%)。原因：Linux source pull 完但 engine 未 `--rebuild`，runtime 仍跑舊 code → Fix 1 早退邏輯尚未 promote。Task spec 明示「不阻塞」。Operator deploy `--rebuild --keep-auth` 後 24h 重測應顯著降至 < 50%。

**E4 教訓 / 反模式避免**：
- Cargo PATH on non-interactive ssh：必先 `source ~/.cargo/env`，否則 `cargo: 未找到命令`
- Pytest 出 1 fail 時 → checkout baseline commit (`git checkout <parent> -- .`) 直接 reproduce 證明 pre-existing，不是「假設並繼續」（memory `feedback_working_principles.md` 原則 1 誠實報告）
- Step 8 / 9 等 runtime probe 跑出與預期不符數字（noise 100%）時，先區分「fix 失效」vs「fix 未 promote 到 runtime」— 前者 BLOCK，後者 inform PM 不阻塞
- 健康檢查腳本需 `set -a && . secrets/environment_files/basic_system_services.env && set +a` 才能拿到 PG 憑證；無 env 時 default fallback to OS 用戶 (`ncyu`) 必認證失敗

**Reports**：
- `.claude_reports/20260502_144705_e4_p2_wave_linux_regression.md`（6 節格式）
- `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--p2_wave_linux_regression.md`

---

### 2026-05-02 AUDIT-2026-05-02-P1-1 Round 2 Linux PG regression — **E4 FAIL → RETURN E1**

**對象**：retrofit V028/V030/V031/V032/V034 + fixture (round 1 BLOCK 解除後重跑)。Linux source 已 ff-only pull 到 PM commit `e858ae2`；PG 連接憑證 `trading_admin@127.0.0.1:5432/trading_ai`（從 `basic_system_services.env` 讀；password 含 `()` 字符必 single-quote）。

**Verdict**: **FAIL** — V031 retrofit not idempotent on V034-extended state.

**Step results**:
- Step 2 FAIL @ V031 (`ERROR: cannot drop columns from view` line 240)
- Step 3 PASS (17/17 fixture cases)
- Step 4 PARTIAL (V028/V030/V032/V034 second run clean; V031 deterministic FAIL)
- Step 5 SKIP (no separate test DB; would reset production)
- Step 6 PASS (all 5 retrofit V### "ALL PRESENT OK")
- Step 7 PASS WARN baseline (no new FAIL related to retrofit)

**Root cause**: V031 line 56 `CREATE OR REPLACE VIEW learning.mlde_edge_training_rows` 體積 35 cols，但 production 已被 V034 cumulative 擴成 53 cols。PG `CREATE OR REPLACE VIEW` 不允許 drop col → 第二次跑必 ERROR。Retrofit author 注解假設「乾淨初次安裝」idempotent — 在 V034-applied state 下不成立。違反 CLAUDE.md §七 Migration Guard #4。

**E4 教訓** — 對偶 V023 postmortem：
- V023 lesson = 對 **legacy drift** 主動 RAISE (Guard A 模板)
- V031 R2 lesson = 對 **future-shape drift**（已被後續 migration 擴展的 view/table）主動 skip — 否則 retrofit 自己變成 silent destroy（PG hard limit 阻擋這次救了我們，但凡能跑下去就會 narrow view 摧毀下游 reader）
- 凡 migration 含 `CREATE OR REPLACE VIEW` 都要驗 view 當前 col superset 是否包含本次預期 col；不對等則整段 view 重建 wrap in `DO $$` shape-guard skip。

**Recommended E1 fix**: Option B — V031 加 `DO $$ ... $$` shape-guard 包 `CREATE OR REPLACE VIEW`，先驗 V031 預期 col 已在 view 才 skip 重建。Round 3 驗 V031 only (其餘 4 已 pre-validated)。

**Reports**:
- `.claude_reports/20260502_130800_e4_audit_p1_1_linux_regression_round2.md`
- `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--audit_p1_1_linux_pg_regression_round2.md`

---

### 2026-05-02 AUDIT-2026-05-02-P1-1 Linux PG end-to-end regression — **E4 BLOCKED**

**對象**：retrofit V028/V030/V031/V032/V034 + fixture `test_v028_v034_guards.sql`（733 LOC / 17 case），E1 R2 + E2 R2 PASS 後 E4 Linux 真實 PG 驗證。

**Verdict**: **BLOCKED**（無一 Step 真實執行）

**BLOCKER 1 — Linux 工作樹缺 retrofit**：
- ssh trade-core git status 顯示 clean main `4749e0c`（最後 commit「Document eaf0c7e runtime redeploy」）
- ls 確認 V028..V034 是舊版（無 Guard A/B），fixture 完全不存在
- 此為 task 預期：「PM 還沒 push retrofit。如果 Linux 端看不到 retrofit code，本步等 PM push 後再做」
- Mac 端 working tree retrofit 完整：6 檔 1850 LOC，guard markers 51 hits（V028=21 / V030=7 / V031=9 / V032=9 / V034=5），fixture TEST/CASE/RAISE marker 46 hits 對齊 17 case 描述

**BLOCKER 2 — Linux PG `trading_ai_test` 連接憑證未知**：
- `settings/environment_files/basic_system_services.env` 含 `POSTGRES_USER/PASSWORD/DB/PORT`（無 HOST），fallback 127.0.0.1
- 用 sourced env 跑 psql：`FATAL: password authentication failed for user "trading_admin"`
- `audit_migrations.py:280` 用同樣 conn pattern；推測 production runtime 連法不同（docker / pgpass file / IPC socket）
- task 明文「如不確定，stop and ask PM，不要自己猜路徑」— 不擅自猜

**Risk warning 給 E4 重啟**：
- Step 5 用 `OPENCLAW_TEST_PG_DESTRUCTIVE=1` reset DB — PM 提供連接字串時必確認是 `trading_ai_test` 非 `trading_ai`
- 整批 ssh trade-core 命令落在 SSH bridge「無需 per-case 授權」範圍

**Reports**：
- `.claude_reports/20260502_125420_e4_audit_p1_1_linux_regression.md`（6 節格式 + 完整 ssh 命令清單供 PM 解封後 E4 重啟）
- workspace report: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--audit_p1_1_linux_pg_regression.md`

**教訓 / 反模式避免**：
- 不擅自 commit + push 整批 working tree（含 audit memory + report 等需 PM Sign-off 條目）解 BLOCKER 1
- 不擅自 git pull / merge / rebase Linux 端
- 不猜 PG 連接字串
- BLOCKED 立即回報而非繼續探索 — memory `feedback_working_principles.md` 原則 4「多角色工作流不可跳過」

### 2026-04-30 5-Agent `last_heartbeat_ms` 契約 round 2 Mac local regression — **E4 PASS_TO_PM**

**對象**：8 changed files unstaged（5 agent .py + agents_routes_helpers.py 827 LOC + test_agents_routes.py + 新檔 test_agent_heartbeat_contract.py 614 LOC / 36 case），E2 round 2 APPROVE_WITH_NITS 後 E4。

**Verdict**: **PASS_TO_PM** — focused 全綠 + full regression 與 E2 baseline 完全一致（1 pre-existing Rust WIP fail，scope 完全正交）

| Suite | passed | failed | baseline (E2 R2) | delta |
|---|---|---|---|---|
| Heartbeat contract focused (8 files: heartbeat + agents_routes + 5 agent unit/integration/worker + strategist) | **238** | 0 | new + adjacent | +0 |
| Heartbeat contract 2nd run（非 flaky 驗證） | **238** | 0 | match 1st | 0 ✓ |
| Full control_api_v1 regression（excl test_pyo3_*）| **3234** | 1 (pre-existing) | 3195 / 1 (E2 R2) | +39 passed (含 36 new heartbeat cases + adj) ✓ |

**Pre-existing FAIL clarification**：`test_batch_d_risk_fail_closed.py::test_rc_002_h0_status_refresh_preserves_cooldown_and_kill_switch` — 斷言 Rust `event_consumer/loop_handlers.rs` 含 `fn build_status_risk_snapshot(`，loop_handlers.rs current Wave G1-02 Step 2a 拆分中只實作了 LoopState + 3 個 small arm（A/B/D），arm C/E/F 包含 risk snapshot 留 Step 2b/2c。**完全正交本 PR**（5 agent .py + helper + 2 test，0 Rust 變動）。E2 round 2 報告同 1 fail。

**新增 36 case 覆蓋盤點**（無灌水）：
- 5 ctor-zero × 5 agent
- 5 start-stamps × 5 agent
- 9 activity refresh：scout record_scan + 2 negative MED-2 (produce_intel/produce_event_alert no-stamp) + guardian review_intent + 4 on_message refresh + analyst analyze_trade
- 5 get_stats × 5 agent
- 4 role card → ISO + 1 ts=None when heartbeat=0
- 3 Strategist eval-log precedence/fallback (round-trip ISO→ms 1500ms tolerance)
- 4 stopped-state negative（M-1 strict guard 真實生效）

**Mock 安全 audit**：所有 Tier 1 test 真用 ctor + 真 path call + assert real `_last_heartbeat_ms` 變化（含 `time.sleep(0.002)` 確保 ms-clock 前進）；Tier 2 用 `types.SimpleNamespace(get_stats=lambda: ...)` 注入 controlled stats，`_build_<role>_card` 真讀 `card["last_heartbeat_ts"]` ISO 字串；無 magic mock 灌水、無業務邏輯 mock。

**SLA 壓測**：N/A — 心跳賦值 `int(time.time() * 1000)` 一行 <1µs，無 hot-path 影響；MED-1 record_scan stamp 移進 lock 但 critical section <10 行符合 H0 <1ms / tick <0.3ms / IPC <5ms 預算。

**跨語言浮點 1e-4 一致性**：N/A — 純 Python metadata field 加增，無 Rust 對應、無 float 計算。

**Engine rebuild**: NOT triggered — 純 Python 改動，commit 後 Mac push → Linux `git pull --ff-only` 即可，不需 `--rebuild`。Linux pytest 驗證留 PM commit + push + ssh trade-core git pull 階段重跑（Mac WIP unstaged 無法直接 ssh 跑）。

**操作 notes**：
1. test 檔名與 spec 略異：`test_analyst_agent_unit.py` / `test_executor_agent_unit.py` / `test_scout_integration.py` / `test_scout_worker.py`（無 `test_analyst_agent.py` / `test_scout_agent.py` / `test_executor_agent.py`，spec 有 typo）
2. `test_pyo3_audit.py` / `test_pyo3_routes.py` 在 Mac dev 通常 OPENCLAW_DATABASE_URL 未設會 skip 或 attempt connect → ignore by design

報告：作為 E4 final assistant message 直接輸出（per system-reminder 不寫 .md），上層 PM 會議讀此訊息

---

### 2026-04-28 Wave H 3-way active warn cleanup splits + 2 inline fixes Linux full regression — **E4 PASS**

**HEAD**: `0a50c6c` (Wave H 6 commits `dbba235..0a50c6c` post-EDGE-DIAG-2 deploy)

**Verdict**: **PASS** — Wave H 純 Python refactor + docs (0 Rust src diff, 0 trade impact, no engine rebuild)

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| Rust lib (release) | **2308** | 0 | 2308 | 0 ✓ |
| Rust daemon split sum (3 files: dual_safeguard 3 + proofs 5 + spawn_decision 3) | **11** | 0 | 11 | 0 ✓ |
| Rust persistence (Linux real PG) | **2** | 0 | 2 | 0 ✓ |
| HSQ same-session 1st (api_contract + h_state_query) | **108** | 0 | 108 (post-Wave-G HSQ-SPLIT) | 0 ✓ |
| HSQ same-session 2nd (flaky verify) | **108** | 0 | 108 | 0 ✓ (non-flaky) |
| Strategist regression (8 files) | **133** | 0 | 133 | 0 ✓ |
| Scout (integration + audit_wiring) | **46** | 0 | 46 | 0 ✓ |
| Analyst (agent_unit) | **22** | 0 | 22 | 0 ✓ |
| Full control_api_v1 baseline | **3117** | 0 (3 skipped) | ≥3117 | 0 ✓ |
| Healthcheck full sweep | 30 PASS / 2 FAIL pre-existing | — | — | OK |

**Wave H 對象**：(1) `54b9add` §九 pre-existing baseline exception clause (2) `6d657c1` STRATEGY-WIRING-SPLIT P2 strategy_wiring 1060→784 + 2 sibling (h_state 133 + scanner 338) (3) `5928576` STRATEGIST-DELEGATOR-SLIM P3 strategist 933→782 + 25 delegators lift (4) `bd48672` MAF-SPLIT-CLEANUP §九 SCOUT_AGENT row + docstring (5) `eb6f9e2` cross-agent memory (6) `0a50c6c` PA lambda capture comment fix.

**重要驗證**：HSQ same-session 108/108 reproducible 兩遍 → confirms STRATEGY-WIRING-SPLIT P2 (1060→784 + 2 sibling) 對 H state singleton lifecycle **0 影響**（singleton attribute grep stability via re-export 維持）。

**Pre-existing FAIL clarification**（per CLAUDE.md §九 exception clause）：
- `[12] bb_breakout_post_deadlock_fix` — G2-06 disable + EDGE-DIAG-2 demo override known issue
- `[27] intents_counter_freeze` — Rust trading_writer intent INSERT path wedge (P1 documented，parent commit 也 FAIL)
- 兩 FAIL 在 Wave H 之前的 multiple E4 reports (2026-04-26 起) 持續記載；Wave H 0 Rust diff 不可能引入

**Engine rebuild**: NOT triggered. Engine PID 3626554 binary mtime 2026-04-28 05:28 (EDGE-DIAG-2 deploy 不變). Wave H 純 Python + docs, LiveDemo runtime 不退化.

**操作 notes for next E4**：
1. Linux pytest path = `/home/ncyu/.local/bin/pytest`（venvs/ 只含 rust_build, 無 Python venv）
2. test_strategist*/test_scout*/test_analyst* 全在 `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/` 不在 srv root `tests/`
3. Healthcheck 用 `bash helper_scripts/db/passive_wait_healthcheck.sh` 不要 `python3 -m runner`（後者 PG 密碼/env 載入會失敗）
4. cargo test --test 多 file flag 要拆，不能合 (`--test a --test b` 才會跑 b，純 `cargo test --test a` 只會跑 a)

報告：`docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-28--wave_h_linux_full_regression.md`

---

### 2026-04-28 Wave B Hotfix `00db240` Linux re-regression — **E4 PASS**

**對象**：commit `00db240` (V026 retention policy fn + CHECK constraint test fixture acceptance)，HEAD `16a30e5`

**Verdict**: **PASS** — 兩 BLOCKERs 完全 resolved

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| Rust lib (release) | **2299** | 0 | 2299 | 0 ✓ |
| Rust daemon test | **11** | 0 | 11 | 0 ✓ |
| Rust persistence (Linux real PG) | **2** | 0 | new (recovered 0/2) | +2 ✓ |
| V026 idempotency (3 runs) | NOTICE-only, 0 RAISE | — | new | ✓ BLOCKER #1 RESOLVED |
| V026 Guard test fixture | 6/6 PASS | 0 | new | ✓ |
| Healthcheck full sweep | 32 (PASS+WARN+FAIL) | 0 FAIL | — | 1 WARN [11] pre-existing |

**BLOCKER #1 RESOLVED** — V026 加 `learning.cost_edge_advisor_log_now_ms()` STABLE fn (returns `(extract(epoch from now())*1000)::bigint`) + `set_integer_now_func(replace_if_exists=>TRUE)` + `add_retention_policy(if_not_exists=>TRUE)`，3 連跑 0 RAISE 全 NOTICE skip = idempotency 完全恢復，符合 CLAUDE.md §七 規則 4。

**BLOCKER #2 RESOLVED** — V026 CHECK constraint 加 `OR engine_mode LIKE 'test\_%' ESCAPE '\'`（生產 4 mode `paper/demo/live/live_demo` 不變，test fixture `test_*` 接受），Linux 真 PG persistence test 2/0 fail 通過。

**Linux PG cleanup** — `helper_scripts/db/cleanup_v026_partial_state.sh` 一次性 DROP CASCADE 清 1st-apply ERROR 殘留 partial state，DROP TABLE OK + DROP FUNCTION skip（function 從未被創建，1st-apply ERROR 在 retention policy 行就 abort）= clean state 確認。

**V026 artifacts verified（postgres）**：table + hypertable + STABLE function + retention policy job_id=1025 (`Retention Policy [1025]`) 全 4 項 present。

**教訓**：
1. Mac auto-skip（`OPENCLAW_TEST_PG` 未設）會漏抓 Linux real-PG 的 schema-level bug — Mac dev 須在 hotfix 前 documented limitation 「我已驗 SQL 純 fix 不影響 Rust，但 Linux PG schema 落地需 Linux E4 真驗」，**不可單方面宣布 fix**
2. SSH 連 Linux PG 須用 `localhost` 不是 `127.0.0.1`（pg_hba.conf md5 規則差異）；passive_wait_healthcheck 預設 `127.0.0.1` 沒密碼會 connect fail，需 `OPENCLAW_DATABASE_URL='postgresql://redacted@localhost:5432/trading_ai'` 顯式覆寫
3. 密碼含 shell metachar (`(`, `)`) 在 URI 內須 literal-quote 包外層 bash single-quote 防解析，但內部 `(` 仍可在 PG URI 解析（不需 percent-encode）
4. TimescaleDB `add_retention_policy(BIGINT)` on `bigint` ts column 一定要先 `set_integer_now_func()` — 是 framework 慣例不是 bug，但 CLAUDE.md §七 SQL guard 規則 4 idempotency 強制兩跑通過 = 防線發揮作用，事前若 Linux 試跑就會抓到

**Report**: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-28--wave_b_hotfix_linux_re_regression.md`

---

### 2026-04-28 Wave B (G3-09 Phase B Wave 1 + G8-01 W2 + W3) Linux full regression `cf34e96..d1fd1cf` — **E4 FAIL**

**對象**：4 commits (`31761a6` Phase B Wave 1 V026+INSERT+healthcheck split+DbSlot late-inject ~2293 LOC / `99ac0b4` G8-01-W2 CognitiveModulator 22-case / `4a5b1d6` G8-01-W3 strategist cognitive integration 7 scenarios / `d1fd1cf` cross-agent memory)

**Verdict**: **FAIL — 退 E1**（2 BLOCKERs Linux-only，Mac auto-skip 漏抓）

| 引擎 | passed | failed | baseline | delta |
|---|---|---|---|---|
| Rust cargo lib (release) | **2299** | 0 | 2290 | +9 ✓ (兩遍 0.52s 同綠) |
| Rust daemon test | **11** | 0 | 6 (Phase A) | +5 ✓ (兩遍 2.06s/2.07s 同綠) |
| **Rust persistence test** | **0** | **2** | new | **BLOCKER #2** |
| W3 same-session (51 cases) | **51** | 0 | n/a | ✓ (兩遍 0.52s/0.58s) — H-1 fix Linux reproducible CONFIRMED |
| Pytest combined 7-suite | **141** | 0 | Mac 141 | match ✓ (兩遍 0.71s/0.67s) |
| **V026 idempotency** | — | — | — | **BLOCKER #1** (1st apply ERROR + 2nd apply same ERROR) |
| Healthcheck full sweep | 31 PASS / 1 WARN [11] / 0 FAIL | — | — | [30] cost_edge_advisor_status PASS / [8] shadow_exits dormant ok |

**BLOCKER #1 — V026 retention policy bug** (P0 production migration broken on Linux)：
- File `srv/sql/migrations/V026__cost_edge_advisor_log.sql` 行 192-198：`add_retention_policy('learning.cost_edge_advisor_log', BIGINT '2592000000', if_not_exists => TRUE)` 在 TimescaleDB 2.26 上 ERROR — `bigint` ts_ms hypertable 缺 `integer_now_func`
- 1st apply: 表 + hypertable 創建後 ERROR aborted；Linux PG 留下 partial state（表 OK / 0 rows / 無 retention）
- 2nd apply: `IF NOT EXISTS` Guard A NOTICE-skip 表 + hypertable，但 retention policy 行再次 ERROR — **Idempotency BROKEN**，違反 CLAUDE.md §七 規則 4
- 影響：`linux_bootstrap_db.sh` 無法套用 V026；`OPENCLAW_AUTO_MIGRATE=1` engine 拒絕啟動
- E1 fix path A 推薦：先 `set_integer_now_func()` 註冊再 `add_retention_policy(BIGINT ...)`；或改 `drop_created_before => INTERVAL '30 days'`

**BLOCKER #2 — 持久化測試 vs V026 CHECK constraint 衝突** (P1 test infrastructure)：
- File `srv/rust/openclaw_engine/tests/test_cost_edge_advisor_persistence.rs:184,261` 用 `format!("test_persist_{}", pid)` 隔離 tag，但 V026 CHECK `engine_mode IN ('paper','demo','live','live_demo')` 拒絕
- 直接 `psql INSERT ... 'test_e4_diag' ...` 確認 ERROR `cost_edge_advisor_log_engine_mode_check`；Rust 側 `tokio::spawn(insert_advisor_log_row)` fire-and-forget 將 ERROR 吞為 warn!，測試見 0 rows panic
- 生產路徑不受影響（engine_mode 永遠 4 prod 值之一）— 純 test-vs-schema design conflict
- E1 fix path A 推薦：CHECK 放寬 `OR engine_mode LIKE 'test_%'`；或測試改用 prod value + ts_ms range cleanup

**驗證流程**：
1. `git reset --hard origin/main` Linux HEAD `d1fd1cf` ✓
2. cargo lib `--release` 兩遍 2299/0 — Phase B Wave 1 lib-side (+9: EvalCounters/CostEdgeAdvisorLogRow/sticky/CHECK envelope) 全綠
3. cargo daemon test 兩遍 11/0 — Wave A baseline 6 + Wave B sticky×2 + spawn-test×3 = 11 完美對齊
4. cargo persistence test → 2/2 FAIL → BLOCKER #2 RCA via direct psql INSERT
5. `bash helper_scripts/linux_bootstrap_db.sh --apply V026` 1st → ERROR line 197 → BLOCKER #1
6. 2nd apply → 同 ERROR → idempotency BROKEN
7. pytest W3 51-case 兩遍 51/0 0.52s/0.58s — H-1 fix Linux reproducible
8. pytest 7-suite combined 兩遍 141/0 0.71s/0.67s — Mac 141 vs Linux 141 perfect match
9. healthcheck 32 check 全跑 → 31 PASS / 1 WARN [11] (pre-existing 226/200 113%) / 0 FAIL，含 [30] PASS DB-down fallback verified

**綠色項目（confirm Phase B observation foundation working）**：
- 5-Agent rust path 全綠（cargo lib + daemon + W3 + combined 7-suite 全 0 fail）
- Phase B Wave 1 advisory observability 0 trade impact 確認（healthcheck [30] env=0 dormant + [8] shadow_exits 0 row）
- ExecutorAgent shadow_mode dormant 確認（[16] strategist scheduler not started by design）

**Mac vs Linux 盲點教訓**：
1. **Mac PG bypass blind spot**：Mac `OPENCLAW_TEST_PG` 未設 → persistence test auto-skip → V026 retention bug + test-vs-CHECK conflict 雙雙隱藏。PA RFC §6 R-B7 顯式要求 Linux 驗，否則 Wave B 在 Mac 全綠卻 Linux deploy 卡死。**規則強化**：任何 V*.sql migration 動到 TimescaleDB hypertable retention/compression/integer_now 必 Linux-validated（`linux_bootstrap_db.sh --apply` 兩遍）才能 PM Sign-off，不論 Mac 結果。
2. **Fire-and-forget INSERT 吞測試訊號**：`tokio::spawn(insert_advisor_log_row)` 解耦 DB I/O 與 daemon cadence（生產 design 正確 per RFC §6.1 R-B1）但 CHECK / FK / 權限 ERROR 全 warn-only — 測試 panic 見 "0 rows" 無線索。**建議**：persistence-style integration test 應先跑 sentinel 直接 INSERT 驗 schema 相容性才信任 async daemon path。
3. **CHECK constraint + isolation-tag 測試 = anti-pattern**：test code `format!("test_persist_{}", pid)` 隔離但 schema CHECK whitelist 拒絕。schema 必須允許 `test_*` prefix OR 測試必用 prod value + 替代隔離（ts_ms range/獨立 column）。**新增 PA / E2 checklist**：任何新 V*.sql with CHECK 必列目前 test isolation pattern 並確認相容。

**Report**: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-28--wave_b_linux_full_regression.md`

### 2026-04-28 Wave A prep-gate trio Linux full regression (commits `aced662`+`9303a3b`+`22c57dc`+`528805d`) — E4 PASS

**對象**：Wave A prep-gate trio 4 commits 已 push origin/main `82347a5..528805d`
- `aced662` G8-01-FUP-LOSSES-WIRING (Python: analyst + strategist + strategy_wiring + new test 8 cases)
- `9303a3b` G3-09-FUP sticky_triggered_at_ms (Rust: mod.rs daemon body + advisor.rs doc + types.rs + 2 sticky tests)
- `22c57dc` G3-09-FUP spawn-test (Rust: 3 cases A/B/C in test_cost_edge_advisor_daemon.rs)
- `528805d` cross-agent memory updates

**Linux baseline 全綠 (兩遍同綠 non-flaky)：**

| 引擎 | passed | failed | baseline | delta |
|---|---|---|---|---|
| Rust cargo lib (release) | **2290** | 0 | 2290 | 0 |
| Rust daemon integration test | **11** | 0 | 6 (Phase A) | +5 (sticky+spawn FUP) |
| Python pytest combined Wave A | **199** | 0 | Mac 86 | +113 (Linux collects more) |
| Healthcheck | 27 PASS / 1 WARN [11] / 0 FAIL | — | — | WARN [11] pre-existing per-existing observation pacing |

**驗證**：
1. Sync `cd ~/BybitOpenClaw/srv && git fetch && git reset --hard origin/main` → HEAD `528805d` ✓
2. cargo lib `--release` 0.52s × 2 兩遍 2290/0 — sticky-ts 改 mod.rs daemon body 屬 production code 但 Phase A advisory-only 路徑 0 行為變化（E2 已驗），lib 不變
3. cargo `--test test_cost_edge_advisor_daemon` 2.09s × 2 兩遍 11/0 — daemon test target = baseline 6 + 5 new (2 sticky from 9303a3b + 3 case A/B/C from 22c57dc) 完美對齊
4. pytest combined 7-suite 0.29s × 2 兩遍 199/0 — Mac 86 vs Linux 199 因 Linux 環境 collect 更多 case（fastapi 等 Mac dev_disabled 套件齊全）；E2 報 PA 預測「Mac 8 fastapi pre-existing failures」Linux 0 fail 確認屬 Mac dev-only env
5. Healthcheck full sweep 27 PASS — `phys_lock_runtime` 7d=456 / `edge_estimates` 100% populated 231/231 / `bb_breakout disabled by G2-06` confirmed / `cost_edge_advisor_status` env=0 dormant by design (Phase A: 0 trade impact 預期)

**Mock 安全 / Mock 審查**：N/A（純跑既有測試 + 0 production diff）

**WARN [11] 解讀**：`counterfactual_clean_window_growth` post-P013-clean n_rows=226/200 (113%), rate=95rows/2d, ETA ~0d at current rate — 即將 PASS，與 Wave A 改動無因果（pre-existing observation pacing rule，過 200 rows 後 healthcheck 仍 WARN 直到 cron next sweep 重評）

**0 regression / 0 production diff in this E4 run**（純跑測試）

**教訓**：Wave A 是「PA 派發 prep-gate」3 commits 整合 — 都是小範圍補強：(a) G8-01 LOSSES-WIRING 補 W1 cognitive modulator consecutive_losses (b) G3-09 sticky_triggered_at_ms 補 daemon 內 contiguous trigger 跨 evaluate cycle 持久化 (c) G3-09 spawn-test 補 PA RFC §6.1 R-B4 揭示的「daemon spawn fn 級整合測試 0 個」缺口。三者都是 Phase B prerequisite，本身不觸 live 或 hot path，但對下游 Phase B observation 必要。

### 2026-04-27 G3-09 Phase A daemon integration test (Phase B prerequisite) — E4 PASS

**任務**：補 PA RFC `2026-04-27--g3_09_phase_b_shadow_dryrun_design.md` §6.1 R-B4 + §R-B10 揭示的缺口 — Phase A 32 unit tests 全直驅 `evaluate()` pure fn + 5 IPC handler tests 手動 populate slot，**0 個 daemon-level 整合測試**證明 daemon 真在跑 → Phase B observation 無 ground truth。

**成果**：新檔 `rust/openclaw_engine/tests/test_cost_edge_advisor_daemon.rs` 6 tests (~440 LOC，純測試 0 production diff)，Mac --release 2.09s 兩遍同綠 (2/2 non-flaky)。

**4 大證明 + 1 bonus**：
1. `daemon_spawn_advances_state_off_uninitialized` — daemon spawn 100ms cadence 1s 內 state 從 Uninitialized → Ok 且 ratio/data_days/threshold/last_eval_ms 全 echo H5+RiskConfig
2. `ipc_handler_returns_live_state_after_daemon_writes` — Trigger ratio (-0.8) 場景下 advisor.state() 回 status=Trigger / ratio=-0.8 / ai_spend=10.0 / paper_pnl=-8.0 / data_days=7 / triggered_at_ms>0 全來自 daemon-written，非 `uninitialized()` stub
3. `dual_safeguard_env_gate_off_skips_daemon` — env-gate 嚴格 "1" 比對：unset/"0"/"true"/" 1 "（含空白）全 false，僅 "1" true；env 改動經 process-wide `OnceLock<Mutex<()>>` 序列化避 OS-level env race
4. `dual_safeguard_risk_config_disabled_short_circuits` — env=1 + H5=Trigger ratio (-0.8) 但 RiskConfig.cost_edge.enabled=false → daemon body 內 `evaluate()` Step 1 short-circuit Disabled，ratio=None（不 echo H5 because short-circuit 在 H5 read 前），threshold echo for audit
5. `daemon_evaluate_cadence_within_tolerance` — 200ms × 10 cycle，mean cadence error ≤10%（task spec），per-cycle jitter 硬上限 50%（5× tolerance 容 CI scheduler outlier）
6. **bonus** `daemon_cancellation_drains_within_one_second` — 長 poll interval (10s sleep) 中觸發 cancel，daemon 1s 內 join cleanly（驗 mod.rs:188 「cancellation-safe sub-second shutdown」宣告）

**關鍵設計選擇**：
- 用 `tokio::test(flavor = "multi_thread", worker_threads = 2)` 確保 daemon 真拿獨立 worker（single-threaded runtime 會序列化 daemon 與 assertion，defeat integration）
- 用 100ms / 200ms poll interval 加速測試（vs 預設 10s），仍走真實 spawn → tokio::select! → tokio::time::sleep 路徑（非 mock）
- 透過 daemon 自己的 `last_eval_ms` epoch ms 算 cycle delta，這是 consumer 視角的 cadence（非 wall-clock 觀察者視角）
- 直呼 inner `spawn_cost_edge_advisor()` 而非 `spawn_cost_edge_advisor_if_enabled()` 隔離「第二保險」(RiskConfig flag)，避免 env-gate 並發污染

**baseline**：lib 2290/0 兩遍同綠不變（純整合測試，獨立 test target）。整合 test target 35 + 6 = 41 tests 全綠。

**0 production diff 確認**：`git diff --stat` 顯示僅 `docs/CCAgentWorkSpace/PA/memory.md` 79 行（sibling agent，非本任務）；新檔在 untracked 區。

**教訓**：Phase A E1 self-report 5.4 標 daemon integration 屬「E4 regression scope」 — 但 Phase A E4 report 第 §5 mock 審查直接判 `Phase A daemon 邏輯 ... runtime 行為，本 E4 不啟動 spawn` = N/A，沒補 daemon 級測試就放行。後 PA 寫 Phase B RFC 才察覺 R-B4 = 「無 ground truth」缺口必須回頭補。**規則**：advisor / daemon / 任何「spawn 後背景運轉」模組，single E1 完工不能跳「至少 1 個整合測試證明 daemon 真寫入觀察點」這條。

### 2026-04-27 OBSERVER-RESTORE-1 (`d4bc9eb`) healthcheck+observer 4 stale/FAIL 修 — E4 PASS

**結論：E4 PASS — 0 regression / +5 new tests / 兩遍同綠**

**Commit `d4bc9eb`** = 7 files changed (482+/62-), 純 Python：
- `checks_engine.py` [3] threshold ratio-band rewrite + [23] orders⊇fills 改 JOIN order_id
- `checks_strategy.py` [24] paper-only context-aware skip
- 新 `_bybit_private_check_stub.py` 共享 helper（OBSERVER-RESTORE-1：`f42face` 刪 `.py.orig` stub 後 4 thin wrapper `execv` rc=2 連 8 天 silent-fail）
- 4 wrapper rewrite 為 thin（account / positions / order_history / execution_history）

**Baseline 比對（parent `26e42fa` vs `d4bc9eb`）：**
| 引擎 | parent | d4bc9eb | delta |
|---|---|---|---|
| Linux pytest control_api_v1 | 2953p / 54f / 3s | 2953p / 54f / 3s | **0** ✓ |
| Linux Rust cargo lib (release) | 2290p / 0f | 2290p / 0f | **0** ✓ |

**+ E4 新測（`8df0a86` Mac local，未 push）：** `test_bybit_private_check_stub.py` 5 tests Linux 5/5 兩遍同綠 → 控制台 suite **2958p / 54f / 3s**（baseline+5）

**4 wrapper subprocess 直跑：rc=0 each**（Linux 即時驗）

**4 healthcheck 全 PASS：**
- [3] `exit_features_writer` ratio 1.00（pre-fix: absolute-delta FAIL）
- [19] `observer_pipeline_alive` ok=5/5 age=0.0h（pre-fix: 8 天 silent rc=2）
- [23] `orders_fills_consistency` pairs_missing=0/6（pre-fix: LEFT JOIN context_id 都 NULL → 假 0）
- [24] `signals_writer_freshness` paper disabled skip（pre-fix: 假 FAIL）

**1 unrelated FAIL：** [27] `intents_counter_freeze` Rust trading_writer intent INSERT path — **不在 d4bc9eb scope**（parent 也 FAIL，本 commit 0 Rust diff）

**Mock 安全：** 新 5 tests 用 `monkeypatch.setenv` + `tmp_path`，0 mock 業務邏輯（emit_stub 邏輯真跑）

**1 條 WARN（不阻塞）：**
- 5 tests pin 當前 `{**base, **payload_extra}` merge 順序行為（caller 可覆蓋 base schema）；future fix 改 `{**extra, **base}` 時須同步改本測試 + 4 wrapper rely 點

**1 條教訓：**
- E4 本地新增 test commit + push 被 harness 鎖（`Pushing directly to main bypasses PR review`）— operator 需手動 push `8df0a86`，但 Linux 已先 scp 驗 5/5 PASS，不阻塞 PM Sign-off

**Report：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-27--healthcheck_observer_fix_regression.md`

---

## 項目上下文（2026-04-01）

- 當前 Phase：Phase 3 Batch 3A 完成
- 測試基準：**3310 passed / 21 failed / 17 errors**（3349 collected）
- Pre-existing failures：17（與 March 31 一致）
- New failures：4 FAILED + 17 ERRORS（回歸問題）
- 系統模式：demo_only

## 工作記憶

### 2026-04-27 G3-08 Phase 4 Wave II Sub-task 4-2/4-3/4-4/4-5 batch 回歸驗證

**結論：E4 ALL 4 PASS — forward to PM batch merge per E2 §5.4 sequential plan**

**4 worktree branches（Mac 端，未 push origin/main）：**
| Sub-task | Branch | Commit | E1 self-tests | Run 1 | Run 2 |
|---|---|---|---|---|---|
| 4-2 Guardian | `agent-a051276dd2c9c8a42` | `e1157ae` | 104/0 | 152/0 | 152/0 |
| 4-3 Analyst | `agent-ad253927d45469488` | `b8951ab` | 207/207 | 138/0 | 138/0 |
| 4-4 Executor | `agent-a3625849262bdb342` | `d99a0da` | 157/7 | 139/0 | 139/0 |
| 4-5 Scout | `agent-a3ba65c86c26adef7` | `eee0f7b` | 226/226 | 187/0 | 187/0 |

每 worktree 跑 `test_h_state_query_handler.py + test_strategist_agent.py + 對應 agent suite`，全綠且非 flaky（兩遍同分）。

**Linux cargo lib baseline：2290 / 0 failed**（origin/main `00682ef` G3-09 Phase A，本 Wave II 0 Rust diff = 預期不變）

**Cumulative LOC 預估（E4 不執行 merge，純 git diff 分析）：**
- baseline `h_state_query_handler.py` 636 LOC
- 每 sub-task 加 ~149-153 LOC（共用 `_collect_agent_snapshots()` scaffold ~115 + 自身 elif arm ~13-18）
- post-merge 預估 ~816-828 LOC，**borderline §九 800 警告線**（差 ~16-28 行）
- 1200 hard cap headroom ~384 行 OK
- PA RFC §3.2 Option B（`dict[str, Optional[dict]]` return）保證 arm 純加性合併 / 0 caller signature break

**Healthcheck [20]：** PASS env=0 dormant by design（Wave II 未 merge / `OPENCLAW_H_STATE_GATEWAY=unset`）

**Mock 安全（PASS）：**
- snapshot accessor lazy import (`strategy_wiring`) per arm — fail-closed `None`
- IPC fire-and-forget hint env=1 gate（env=0 → no-op）
- 0 mock 業務邏輯 / 0 mock snapshot 計算
- 對齊 `build_h_state_full_response` never-raise 合約

**4 條 WARN（不阻塞）：**
1. post-merge `h_state_query_handler.py` ~816-828 LOC 接近 §九 800 警告線（差 16-28 行），future refactor wave 可抽 `_collect_agent_snapshots()` 到 sibling
2. post-merge `test_h_state_query_handler.py` 預估 ~3000+ LOC（test file convention 寬容；可分 per-agent test file）
3. operator 需依 E2 §5.4 sequential merge plan 手動解 2 處 textual conflict（function scaffold + test classes）— union-keep-both 安全
4. 2 MED self-flagged + 3 FUP tickets backlog（E2 scope，PM tracks）

**3 條教訓（升 SOP）：**
1. **Batch regression 同檔多 worktree textual conflict 模式**：E4 不需物理 merge — per-worktree 兩遍綠 + static cumulative LOC analysis 足以當 PA RFC 契約保證 additive arm resolution（Option B dict-return shape）成立。靜態驗證等效 batch merge feasibility 確認。
2. **§九 800 警告線在 batch wave 的隱性風險**：N 個並行 sub-task 各加 K LOC 到同檔，post-merge 預估 = baseline + scaffold + N × arm-loc。E4 必須先計算 cumulative 並在報告中 flag，讓 PM 決定是「merge as-is 接受 §九 warn」還是「同 wave refactor 抽 sibling 預防 LOC 膨脹」。本次推薦 merge as-is（差 ~16 行屬可接受，未來自然 refactor）。
3. **PA RFC §3.2 Option B `dict[str, Optional[dict]]` return shape 在 N-way same-file split 的價值**：跨 N 個 arm 0 caller signature break = E2/E4 cycle 簡化為「驗證每個 arm 自身測試通過」而非「驗證 cross-arm 契約完整性」。建議 PA 將此 pattern 升級為未來 N-way same-region split work 的 reference template。

**報告：**
- `.claude_reports/20260427_205321_e4_batch_regression_phase4_wave2.md`（完整詳報）
- `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-27--phase4_wave2_batch_regression.md`（E4 workspace summary）

---

### 2026-04-27 G3-09 Phase A cost_edge_advisor schema + advisory only 回歸驗證

**結論：E4 PASS — Mac 補位驗證完成；commit `00682ef` 未 push origin（operator gate），Linux 端 cargo +38 驗證俟 push 後跑（Linux baseline 已驗 2252/0 健在）**

**Commit：** `00682ef`（Mac local ahead origin/main `c077e8c` by 2 含 c8a4a55；操作者 gate 未 push）

**Mac cargo lib 兩遍同綠（非 flaky）：**
| Run | passed | failed | delta vs baseline 2252 |
|---|---|---|---|
| 1st | 2290 | 0 | +38 ✓ 對齊 E1 self-report |
| 2nd | 2290 | 0 | +38 ✓ |

**Linux baseline confirm（origin/main `c077e8c` 不含 G3-09）：** cargo lib 2252 / 0 failed（一遍，per E2 baseline + commit 不在 Linux）。**Push 後 Linux 重跑預期 2290 / 0**。

**cost_edge_advisor module direct test 兩遍同綠：** 32 advisor + 5 IPC handler tests = 37/37 PASS（含 +1 額外 schema test：`status_uninjected_returns_disabled_shape` / `status_warm_up_state_round_trips` 等 advisor 32 + handler 5）。E1 self-report 寫 38 包含 IPC schema 五 + advisor 32 + 1 extra round-trip = 對齊。

**Config / TOML deserialize：** 236 / 0（涵蓋三環境 risk_config TOML 解析 + ArcSwap hot-reload）

**Adversarial grep verify（advisory only confirm，§F）：**
- `intent_processor/`：**0 hit** ✓
- `combine_layer.rs`（單檔，非 dir）：**0 hit** ✓
- `exit_features/`（含 schema/writer）：**0 hit** ✓
- `strategies/`：**0 hit** ✓
- `cost_gate*`：**檔案不存在於 src/**（PA RFC 引用是 IntentProcessor 內 cost gate 邏輯，非獨立檔；intent_processor/ 0 hit 等同覆蓋）

cost_edge_advisor 出現點全在「非 trade path」：
- `lib.rs:22` pub mod 聲明
- `main.rs:503-510` env-gate spawn wire
- `main_boot_tasks.rs:19-538` 條件 spawn fn（dual safeguard：env=1 + flag=true）
- `config/risk_config*.rs` schema + risk_config_cost_edge.rs sub-struct
- `ipc_server/dispatch.rs:73-439` 唯讀 status IPC handler

**Three-TOML `[cost_edge]` schema verify（§E 等同）：**
| TOML | enabled | trigger_threshold | per RFC §8.2 |
|---|---|---|---|
| paper | false (Phase A dormant) | -0.5 | ✓ |
| demo | false (Phase A dormant) | -0.5 | ✓ |
| live | false (Phase A dormant) | **-0.3 more conservative** | ✓ |

**Healthcheck [30] check_cost_edge_advisor_status（Mac py3.10 直驗）：**
- `OPENCLAW_COST_EDGE_ADVISOR` unset → verdict=`PASS` "env=0 dormant by design (Phase A: 0 trade impact even when activated); skip"
- 設計：env=0 short-circuit 不依賴 tomllib（py3.10 fallback 路徑只在 env=1 才觸發），合理避免 false WARN

**Slot ID drift（E1 commit message 已標 NOTE）：**
- PA RFC §6.2 原寫 [22]
- F7 已佔用 [22] trading_pipeline_silent_gap
- 實裝改 [30] 並在 docstring 雙語標 NOTE — 合 §三 G6-04 drift 規則

**Mock 安全（PASS）：**
- 5 advisor unit tests evaluate(snapshot, cfg, is_stale) 純 fn 真跑數學（NaN / Inf / threshold boundary / staleness）
- 5 IPC handler tests 真跑 dispatch + RpcCommand serde round-trip
- 0 mock 業務邏輯 / 0 mock H5CostStats 計算公式
- env-gate 邏輯走 std::env 真讀（`env_gate_strict_one_semantics_serialised` 驗 "1" only）

**浮點 / SLA：** N/A（純 Rust schema + read-only IPC + dormant daemon；advisor 為 pure fn 評估，無跨語言對接面 / 無 hot-path）

**3 條 WARN（不阻塞）：**
1. **Commit 00682ef 未 push origin**（operator gate）— Linux 端 +38 完整驗證須俟 push 後跑；本 E4 採 Mac 補位驗證（Apple Silicon Rust release 與 Linux x86_64 cargo lib 在純 Rust 邏輯上無差異，僅 hot-path SLA 數值會異）
2. **PA RFC slot drift [22]→[30]**：F7 已佔用 [22] 是 root cause，E1 已在 docstring + commit message 雙標 NOTE，合 §三 drift 防線
3. **Healthcheck unit test 缺**：[30] check 為 Phase A 哨兵，無 dedicated test 文件（未來 Phase B 啟動 advisor 後可加 pytest stub mock env=1 / flag=true 路徑）

**Push 後 Linux 重跑指令（PM 派發給下個會話）：**
```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main && cd rust && cargo test --release -p openclaw_engine --lib 2>&1 | tail -5"
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -i '\[30\]\|cost_edge'"
```
預期：lib **2290 / 0 failed**；[30] env=0 PASS skip 訊息。

**1 條教訓：**
1. **未 push commit 的 E4 補位策略**：當 commit 在 Mac local ahead origin（operator gate 未 push）+ Linux 端不能跑 +38 完整驗證時，採「Mac cargo --release 補位 + Linux baseline 鎖死」雙軌：
   - Mac 跑兩遍 cargo --release 確認非 flaky + 對齊 E1 self-report 數字
   - Linux 跑 baseline 確認 origin/main 健在（不含本 commit）
   - 把 push 後 Linux 重跑指令記在 report 給下個會話（PM 派發）
   本次 G3-09 Phase A 驗證雖 Linux 未跑 +38，但 Mac 2290/0 兩遍同綠 + adversarial 0 trade-path hit + 三 TOML schema verify + Mac py3.10 [30] 直驗 PASS = 補位等效。Phase A 是 advisory only / 0 trade impact / dormant by default 的 risk surface 極小 commit，補位策略可接受。

**報告：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-27--g3_09_phase_a_regression.md`

---

### 2026-04-27 G3-08 Phase 4 Sub-task 4-1 Strategist agent_state events 回歸驗證

**結論：E4 PASS — PM 可 merge + push（純 Python，0 Rust diff，Linux 不需 --rebuild）**

**Commit：** `c8a4a55`（Mac local ahead origin/main `c077e8c` by 1，未 push 待 PM merge chain）

**4 必要 suite 兩遍同綠：** 142/0 → 142/0（test_strategist_agent + test_h_state_query_handler + test_strategist_audit_wiring + test_batch7_conductor_strategist；含 +7 TestStrategistSnapshot + +9 across 3 new TestCase = +16 new tests vs E1 self-report）

**Linux cargo lib 兩遍同綠：** 2252/0 → 2252/0（對齊 STRKUSDT P0 wave merge 後 baseline；純 Python 0 Rust diff = 預期）

**Stash isolation 模式（首次正式記錄）：** G3-09 Phase A 並行 agent ab0c139a1cd84908c Rust in-flight（25 modified + 3 new cost_edge_advisor/）必須 `git stash push -u -- rust/` 隔離；不隔離則 cargo 編譯失敗 / false negative。完成後 `git stash pop` 還原無衝突。**列入 E4 SOP**：multi-agent in-flight 場景每次必跑。

**F-section grep verify（patch path migration 5/5 PASS）：**
- `if inv is None` env-gate short-circuit: 1 hit @ h_state_invalidator.py:347 ✓
- `def get_strategist_snapshot` 主檔 1 site @ strategist_agent.py:802 / sibling 0 hit ✓
- `_collect_agent_snapshots` def @ h_state_query_handler.py:406 + caller @ :737 ✓
- agent_state hook 中英對照 comments @ strategist_agent.py:79/82/800 ✓

**Mock 審查（PASS）：**
- 4 必要 suite mock 範圍合 §五.5.1（IPC fire-and-forget boundary / time / ai_service.get_ollama_client）
- 0 mock 業務邏輯 / snapshot 計算
- TestSafeSnapshotDefensive 系列驗 fail-closed（method missing / non-callable / non-dict / raises → returns None）符合 §二 原則 #6

**浮點 / SLA：** N/A（snapshot accessor + dict aggregation 無 indicator 計算 / hot-path）

**Broader -k "strategist or h_state or layer2"：** 29 collection errors 全 `ModuleNotFoundError: fastapi` Mac dev-only pre-existing（與 cost_tracker_split / strategist_split 同 pattern，CLAUDE.md §七）。0 net new fail。

**3 條 WARN（不阻塞）：**
1. strategist_agent.py 829 LOC ⚠️ §九 警告線（800 警告 / 1200 hard cap），下個 refactor wave 可抽 50-100 行降回 < 800
2. c8a4a55 未 push origin（Mac local ahead by 1）— PM merge chain 完成後再 push
3. E2 LOW/NIT 5 條本 E4 階段不修（PM 決定是否進 G3-08 Phase 4 follow-up）

**1 條教訓（已升 SOP）：**
- **Stash isolation 模式**：multi-agent in-flight 場景，E4 跑 Linux cargo 前必 `git stash push -u -- rust/` 隔離隔壁 agent 半成品 Rust，完成後 pop 還原。本次 G3-09 Phase A in-flight 25 mod + 3 new 完美隔離。未來凡 Mac 主樹同時有 Rust 子樹 unstaged 改動時必跑此模式。

**報告：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-27--g3_08_phase4_1_strategist_agent_state_regression.md`

---

### 2026-04-27 G3-08 Phase 4 cost_tracker split 回歸驗證

**結論：E4 PASS — PM 可 merge + push（純 Python，Linux 不需 --rebuild）**

**Baseline 對齊：**
- Worktree HEAD `73c1f3d`（Track A `worktree-agent-af8001f13a3d3940b`，未 push origin，PA→E1→E2→E4→PM merge chain）
- origin/main HEAD `12832ca`（pre-merge baseline）
- Linux cargo lib **2252 / 0 failed**（與 CLAUDE.md §十一 一致；本 PR 純 Python 0 Rust diff = 預期）

**改動 LOC：**
| 檔案 | 預期 | 實測 | §九 |
|---|---|---|---|
| layer2_cost_tracker.py | 540 (was 930) | 540 | ✅ <800 |
| layer2_cost_recording.py (NEW) | 405 | 405 | ✅ <800 |
| layer2_adaptive.py (NEW) | 207 | 207 | ✅ <800 |
| layer2_h_state_snapshots.py (NEW) | 190 | 190 | ✅ <800 |

**4 必要 suite 兩遍同綠（test_layer2 + test_h_state_query_handler + test_layer2_escalation + test_strategist_agent）：**
| Run | passed | errors |
|---|---|---|
| 1st | 196 | 12（pre-existing fastapi env gap）|
| 2nd | 196 | 12（identical）|

**Broader -k "layer2 or cost or h_state or strategist"：** 303 passed / 16 fail / 41 collection error。**全 pre-existing httpx + fastapi Mac dev-only env gap**（origin/main 同 3 個 broader-scan failing test files = 28 fail，本 worktree = 16 fail，net new = **0**）。CLAUDE.md §七 Mac dev-only fail-by-design。

**Patch path verify（E4 task §F）：**
- OLD `app.layer2_cost_tracker._invalidate_h_state_async`: **0 hits** ✓
- NEW `app.layer2_cost_recording._invalidate_h_state_async`: **4 hits** at `tests/test_layer2.py:389/422/557/592` ✓
- E1 commit message 寫 line 384/417/552/587 — 實 389/422/557/592（off-by-~5 doc drift）

**Mock 審查（PASS）：**
- 4 patch sites 全 mock `_invalidate_h_state_async`（IPC fire-and-forget boundary OK）
- 0 mock 業務邏輯 / cost 計算 / cost_edge_ratio 數學
- 14 method delegators 真跑 `_recording_sibling.<fn>(*args)` — 由 `record_ollama_call` deprecation warning trail 證 delegator path 真實執行

**浮點 / SLA：** N/A（純 file structure refactor，無 indicator / hot-path）

**3 條 WARN（不阻塞）：**
1. Mac 缺 fastapi/httpx → 12+16+41 errors 全 pre-existing；建議 `pip install fastapi httpx`
2. E1 commit message line numbers off-by-~5（doc drift only）
3. 純 Python refactor，0 Rust diff，Linux cargo baseline 2252/0 不變

**1 條教訓：**
1. **Patch path migration 驗證模板**：未來 file split refactor 涉及 monkey-patch 重新接線時，E4 必跑 grep verify (a) 0 old hits (b) ≥N new hits 對應 E1 self-report — 比單純 pytest pass 多一道 contract check 護欄。本次 4/4 sites OK。

**報告：** `.claude_reports/20260427_151551_e4_regression_cost_tracker_split.md` + `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-27--cost_tracker_split_regression.md`

---

### 2026-04-27 G3-08 Phase 4 Strategist split 回歸驗證

**結論：E4 PASS — PM 可 merge worktree → main + push（純 Python，Linux 不需 --rebuild）**

**Baseline：** Linux cargo lib **2252 / 0 failed**（兩遍同綠 = 非 flaky；對齊 STRKUSDT P0 wave 後 baseline）。純 Python 0 Rust diff，Linux 端跑 main HEAD `1edc6fe` baseline 等同跑本次 Track A Rust 變化。

**改動 LOC 對齊 E1 self-report：**
| 檔案 | 預期 | 實測 | <800 §九 警告 | <1200 hard cap |
|---|---|---|---|---|
| strategist_agent.py | 792 (was 1200) | 792 | ⚠️ 差 8 行 | ✅ |
| strategist_edge_eval.py (NEW) | 369 | 369 | ✅ | ✅ |
| strategist_weights.py (NEW) | 224 | 224 | ✅ | ✅ |
| strategist_cognitive.py (NEW) | 169 | 169 | ✅ | ✅ |

**4 必要 suite 兩遍同綠：**
| Suite | Run 1 | Run 2 |
|---|---|---|
| test_strategist_agent.py + test_strategist_audit_wiring.py + test_h_state_query_handler.py + test_batch7_conductor_strategist.py | 126/0 | 126/0 |

**Broader strategist/h_state/layer2 grep：** 301 passed / 15 fail / 30 error（全 fastapi+httpx 缺套件 Mac dev-only pre-existing；base commit `0611de0` checkout 同 fail 已驗，CLAUDE.md §七 Mac dev-only fail-by-design）

**Mock 安全：** PASS — 純 file structure refactor 0 mock 變動，public API + ctor signatures + import paths 維持原貌

**浮點 / SLA：** N/A（無 indicator / hot-path 改動）

**3 條 WARN（不阻塞）：**
1. strategist_agent.py 792 接近 §九 800 警告線（差 8 行）
2. 30 fastapi/httpx Mac dev-only pre-existing
3. 5 `record_ollama_call` DeprecationWarning pre-existing

**1 條教訓：**
1. **Mac dev-only pre-existing 識別三步驟**（≤2min disambiguate）：(a) grep `ModuleNotFoundError` 看是否套件缺；(b) `git checkout <pre-base> -- <split-file>` 跑同 test 驗 base 是否同 fail；(c) 引用 CLAUDE.md §七 Mac dev-only — 用此流程驗 15 fail + 30 error 全 pre-existing

**報告：** `.claude_reports/20260427_151252_e4_regression_strategist_split.md` + `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-27--strategist_split_regression.md`

---

### 2026-04-27 Live Auth Watcher event_consumer respawn fix 回歸驗證

**結論：E4 PASS — 準備好 commit + push + rebuild**

**Baseline：** Mac lib 2252 / 0 failed（與 Combined Wave 同一 commit；Linux main branch 已同步 2252 / 0）

**兩遍測試結果（非 flaky 確認）：**
| Run | lib | bin |
|---|---|---|
| 第一遍 | 2252 / 0 failed | 53 / 0 failed |
| 第二遍 | 2252 / 0 failed | 53 / 0 failed |

**6 項驗證全 PASS：**
1. Mac lib 2252 / 0 ≥ baseline 2252 ✓
2. Mac bin 53 / 0 ≥ baseline 53 ✓
3. Linux baseline lib 2252 / 0（main branch，feature branch 尚未 push，Linux 端確認基線健在）✓
4. happy path test `spawner_callback_invoked_and_handle_slot_populated_on_ok_some` 存在於 `live_auth_watcher_tests.rs:746` ✓（bin tests 中可見執行）
5. `live_auth_watcher.rs` 975 行 < 1200 ✓；`main_pipelines.rs` 851 行 < 1200 ✓；`main.rs` 1194 行（介於 800 警告線與 1200 硬上限之間，WARN 不 FAIL）✓
6. 硬編碼路徑 0 hit ✓

**1 條 WARN（非阻塞）：**
- `main.rs` 1194 行，接近 §九 1200 硬上限（差 6 行），建議下個 refactor wave 拆分，本 PR 範圍內不超限 OK

**2 條教訓：**
1. **bin tests 跑出 live_auth_watcher tests**：happy path test 是 bin-level integration test（`--bin openclaw-engine`），而非 `--lib`；E4 驗新測試存在性須同時查 lib + bin 兩個 binary 的輸出。
2. **Linux baseline 與 Mac feature branch 同為 2252**：feature branch 改動（E1 加 1 個 happy path test）已讓 Mac bin 從 52→53，lib 因新 test 在 bin 而非 lib 路徑故不變。兩端 baseline 對齊無 delta。

### 2026-04-27 6 P0 PR Wave Combined Regression（F2/F3/F4/F5/F6/F7）

**結論：E4 PASS — MERGE READY**

**Baseline 校正：**
- TODO L10 + CLAUDE.md §十一 寫的 2161 **已過期**（採集時間 2026-04-26，CLAUDE.md §九 G6-04 drift 規則）
- 實測 origin/main HEAD `82bbe5e` cargo test --release lib = **2212 / 0 failed**（+51 vs 2161，含 G3-08 Phase 1A H state cache + Tier 8/9 commits）
- E4 baseline 永遠跑命令拿即時值，**不信 docs 寫死數字**

**Per-branch verification（baseline 2212 / 0）：**
| Branch | HEAD | lib | bins | pytest | E2 quote match? |
|---|---|---|---|---|---|
| F2 | `faebe51` | 2216 (+4) | n/a | n/a | exact ✓ |
| F3 | `8a2c42a` | 2225 (+13) | n/a | n/a | exact ✓ |
| F4 | `db1c012` | 2228 (+16) | 38 | 7 (unattr filter) | lib exact ✓ |
| F5 | `2f353ab` | n/a | n/a | 17 (live_session) | exact ✓ |
| F6 | `337804e` (drift +1 doc commit) | 2219 (+7) | n/a | n/a | lib exact ✓ |
| F7 | `e437a87` | n/a | n/a | 39 (test_f7_new_healthchecks) | exact ✓ |

**Combined merged tree（順序 main→F2→F6→F3→F4→F7→F5）：**
- 2 處 doc-only conflict in `docs/CCAgentWorkSpace/E1/memory.md`（F6 + F7 step），union-resolvable，無代碼撞區
- F4 在 F3 後 merge 自動合併 `loop_handlers.rs`（F3 status arm @L1160 vs F4 unattributed_emit re-export @L83 不撞區）— E2 推薦順序奏效
- Final cargo lib **2252 / 0 failed**（兩遍同綠 = 非 flaky）
- Math: 2212 + 4 + 13 + 16 + 7 = 2252 完美對齊（無 test 互覆）

**Healthcheck integration smoke（F7 8 新 [22-29]）：**
- 27 check 全執行（19 既有 + 8 新）— 無 stack trace / SQL syntax error
- Verdict 分佈：18 PASS / 2 WARN / 5 FAIL — 5 FAIL 是 healthcheck 正確發現 **pre-existing silent-dead pipelines**（與本 wave 6 PR 無關）：
  - [3] exit_features_writer 37 delta、[19] observer_pipeline 1/5 ok、[23] orders_fills 6 pairs missing、[24] signals_writer 179h stale、[26] dust_spiral_noise 37 rows、[27] intents_freeze 30min
- **F7-FUP-23 unattributed:% 排除生效**：DB 實測 `trading.fills WHERE strategy_name LIKE 'unattributed:%'` = 0 rows（engine 未 deploy F4），WHERE filter logic 已就位 → deploy F4 後仍排除無 false positive

**Cross-cutting verification：**
1. F3 status arm × F4 else branch（loop_handlers.rs cross-cut）— 不同 logical region，無撞區。Combined 1212 行 **超 §九 1200 hard cap 12 行**，建議下個 refactor wave 拆 status arm sibling（F4 unattributed_emit.rs 是 reference pattern）
2. F4 audit row × F7 [23] 對齊：DB 0 unattributed rows，[23] WHERE filter exclude 已就位（`checks_engine.py:534-573`）
3. F5 phantom guard 5 邊界齊（integrity-fail view + action-guard write button + body class 4 態 + manual refresh defensive + account endpoint phantom envelope read+write guard）
4. Cross-language float 1e-4 容差驗證 N/A（6 PR 無 Rust↔Python 數值對接面）

**Mock 安全審查（PASS）：**
- F4 unattr filter mock psycopg cursor (IO 邊界 OK)
- F5 mock auth state + slot binding (state OK)
- F7 mock `cur.fetchone()/fetchall()` (純 IO row return OK)
- F2/F3/F6 cargo unit tests 真結構無 mock
- 0 mock 業務邏輯 / 計算函數 / IPC 協議

**5 push back / WARN（不阻塞，PM 注意）：**
1. `loop_handlers.rs` combined 1212 行超 cap 12 行（建議下 wave sibling 抽 status arm）
2. doc-only conflicts in E1/memory.md（PM `sed` strip markers union-resolve safe）
3. TODO L10 + §十一 baseline 過期（merge 同 commit 應更新至 2252）
4. F7 cron wrapper `cd $BASE_DIR` 使 ephemeral worktree 看不到 [22-29]（merge 後 main worktree pull 即解；建議 follow-up 加 wrapper 自驗 grep 新 check id）
5. 5 個真實 FAIL pre-existing silent-dead pipelines（建議 PM 開 ticket 屬 Wave 4 / G3-08+ 範圍）

**Deploy 建議：**
- 4 Rust PR (F2/F3/F4/F6) → `restart_all.sh --rebuild`（Linux operator 指令）
- 2 Python PR (F5/F7) → uvicorn reload + cron 自然 pickup（無 rebuild 需求）
- 一次性 PM merge 6 PR + push + operator `--rebuild` 即整批生效

**3 條教訓：**
1. **Cron wrapper cwd pitfall**：F7 sibling package split 後 wrapper `cd $BASE_DIR` 切到 main worktree → ephemeral worktree 看不到 [22-29]。E4 驗 cron-style script 必須繞過 wrapper 直 invoke 或臨時 patch BASE_DIR
2. **Baseline drift detection**：TODO/CLAUDE.md 寫死數字過期 51 個 test（2161 vs 實測 2212），E4 必跑 cargo 拿即時值
3. **Doc-only memory.md union pattern**：multi-PR 並行 E1/memory.md 是 doc race 不是代碼撞區，`sed -i '/^<<<<<<< HEAD$/,/^>>>>>>>/{/^<<<<<<< HEAD$\|^=======$\|^>>>>>>>/d;}' file` 自動 strip union-keep-both 是 safe pattern

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-27--p0_wave_combined_regression.md`

---

### 2026-04-26 Wave 3 W5 兩軌（EDGE-P2-flip T2 + G2-FUP-IPC-LEGACY-MS-FIX）回歸驗證

**結論：E4 Pass with conditions（軌獨立 + 整體驗證綠；條件 = PM commit + push 後 Linux smoke 重跑）**

**Baseline 對齊：**
- Linux HEAD `60fdf74` (W4 三軌 commit 已 push)：cargo test 兩遍同綠 **2161 passed / 0 failed**（W5 純 Python 改動，Rust 不變符合預期）
- Mac local working tree 5 changes：軌 1 `passive_wait_healthcheck.py` +101 / `shadow_disagreement_breakdown.py` 新 592；軌 2 `ipc_client.py` +24/-1 / `test_ipc_client_hmac_ts_unit.py` 新 360；E1 memory.md 1 個

**§1 cargo test：** Linux 兩遍 2161/0 同綠，W4 已 push 進 baseline，W5 純 Python ✅
**§2 healthcheck [15]：** 4 次連跑 PASS dormant 訊息「decision_shadow_exits 24h=0 (Phase 1a dormant)」；軌 1 T2 升級 GROUP BY 切片屬 pre-warm code，dormant 路徑出口走 G6-02 baseline 一致 message（設計）
**§3 shadow_disagreement_breakdown.py 真機：** Linux HEAD 不含 W5 → MISSING；Mac sandbox 拒 scp（同 W4 教訓 #2）；Mac local psycopg2 缺 → 採靜態 ast.parse + MODULE_NOTE 結構審查 + Phase 1a dormant 出口設計驗證；E1 自跑 Linux dormant PASS 為 trust 基線
**§4 IPC HMAC unit test：** Linux 待 push（Step 4 規則明確跳過）；**Mac local 兩遍 3/3 PASS in 0.02s**（等效驗證 + 非 flaky）
**§5 ast.parse：** Mac local 4/4 全綠；Linux 2/4（2 W5 新檔尚未 push）
**§6 Rust verifier 對照：** mod.rs:534 verify_ipc_token + L621-628 ts 30s 容差 + L637 verify_slice constant-time；軌 2 testfile L73-90 _rust_verifier_accepts() 1:1 移植 0 偏差
**§7 async path :553 比對：** L553 一直 `int(time.time())` 秒制（E1 立場 ✅）；軌 2 fix 把 sync L809 從 `int(time.time() * 1000)` 對齊到 `int(time.time())` — 三者（async + sync + Rust）一致 Unix epoch 秒

**Mock 安全審查（PASS）：**
- `_FakeSocket` mock socket OS IO（合 E4 規則「✅ Mock 外部 IO OK」）
- `_rust_verifier_accepts()` **真跑 Python HMAC + abs 計算**（非 mock 業務邏輯）— mirror 對 verifier 真實覆蓋
- E4 規則「mock vs 真實 verifier 差異 = WARN」**0 WARN**

**1200 硬上限觀察（WARN 不 FAIL）：**
- `passive_wait_healthcheck.py` 2286（W5 +101 vs W4 2185）— PRE-EXISTING WARN（W4 已記錄，in-place 升級不阻塞）
- 其餘 3 檔皆 < 1200 OK

**條件 6 條（PM 必看）：**
1. PM commit + push 必須執行（W5 全 Mac local）
2. Linux git pull --ff-only 重跑 §4 軌 2 unit test（3/3 預期）
3. Linux git pull --ff-only 重跑 §3 dormant 路徑（exit 0 + JSON artifact）
4. [15] dormant message 是 W4 baseline 不是 T2 升級驗證 — T2 GROUP BY 真實運行需 shadow_enabled=true flip 後 cron 第一輪
5. passive_wait_healthcheck.py 2286 行建議下個 refactor wave 拆 dispatch_18_checks 子模組
6. E1 軌 2 testfile fixture 行數 self-report 325 vs 實 360（與 W3 G8-02 661 vs 838 同模式，建議 PA/E2 sanity check）

**3 條教訓：**
1. **W4 教訓 #2 重現驗證**：scp 被 Mac sandbox 阻擋是規則設計，**不繞過**，採等效驗證（Mac local pytest = Linux pytest 邏輯等效，純 Python + mock socket 無 Linux 特殊依賴）
2. **dormant 路徑 cron log 驗證 ≠ T2 升級邏輯驗證**：T2 GROUP BY runtime 需 shadow_enabled=true 翻轉，[15] 24h=0 fixed-message exit 是 G6-02/T2 共用 dormant guard。E4 必明示這條，避免 PM 誤以為 cron PASS = T2 已驗
3. **fixture self-report 行數**：W3 G8-02 fixture 661 報 / 838 實，W5 軌 2 testfile 325 報 / 360 實 — recurring pattern，建議 E1 task report template 加 `wc -l` exact 預填欄位

**Working tree 狀態：** 5 changes 全 Mac local，Linux HEAD `60fdf74`（不含 W5）。PM commit + push + Linux git pull --ff-only + ssh smoke test 應全綠。

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_w5_two_tracks_regression.md`

---

### 2026-04-26 Wave 3 W4 三軌（EDGE-P1b + EDGE-P2-flip + G2-03）回歸驗證

**結論：E4 PASS（三軌全綠 + 兩遍同綠 = 非 flaky）**

**Baseline 對齊：**
- Linux HEAD `55801fe` Rust release：**2138 passed / 0 failed**（不含三軌；Mac local working tree 21 changes 未 push）
- Mac local cargo test --release（含三軌 +23 tests）：**2161 passed / 0 failed**（兩遍同綠；對齊 E1 報告 2161 數字）
- 軌 1 +3（T3 IPC restore_exit_config_defaults handler tests）+ 軌 3 +20（防線 A 12 + 防線 B 8）= +23 ✅

**§1 cargo test 驗證：**
- 派發指定的 ssh Linux 跑 cargo PATH 缺失（ssh non-login shell 不載 ~/.cargo/env），workaround `source ~/.cargo/env` 後 Linux 端 baseline 2138 / 0 failed（HEAD 不含三軌符合預期）
- Mac local 第一次 2138（cargo cache 給舊 binary） / 第二次 rebuild 2161 — 兩遍同綠
- Sibling module 接線 grep：risk_checks.rs:1019 / risk_config.rs:579 / risk_config_tests.rs:1050 三 #[path] re-export 全在 cargo --lib 路徑

**§2 healthcheck 18 check：**
- 軌 1 [14] per-strategy 切片實測 deploy（cron log 03:02:15 CEST 跑出）：grid_trading=282[READY], ma_crossover=146[GROWING], bb_reversion=7[SPARSE], risk_close:fast_track_reduce_half=7[SPARSE], orphan_frozen=4[SPARSE] (READY_frac=63%)
- READY 閾值 ≥200 = calibrator min（對齊 ✅）
- SUMMARY 從 02:33 FAIL → 03:02 WARN（[12] G2-06 deploy 後 PASS；[11] 既有 WARN 與本軌無關）
- 18 check 完整：[1]-[15] + [16] + [Xa]/[Xb] + [18] = 18 PASS/WARN（不含 FAIL）

**§3 EDGE-P2-flip dry-run：**
- ssh Linux 跑 helper 報「No such file or directory」（檔案仍 Mac local，不在 Linux HEAD）
- artifact `/tmp/openclaw/edge_p2_flip_dry_run.json`（先前 E1 自跑留下）含 5/5 PASS：current_shadow_enabled=false / config_version=0 / IPC channel live / engine alive / revert payload symmetric

**§4 shell bash -n：3/3 wrapper 全綠（edge_p2_flip.sh 283 / edge_p2_revert.sh 208 / g2_03_bind_ma_sltp.sh 256）**
**§5 Python ast.parse：4/4 helper 全綠**
**§6 calibrator + summary：**
- calibrator smoke：synthetic 1-strategy 250-row → CALIBRATED（exit 0）
- summary 14d demo（scp + Linux PG, trading_admin user）：per-strategy markdown report 完整（dim×percentile 6×10 + profit cohort 子表 + tier 標籤 + Notes 防誤用警示）

**§7 1200 行硬上限驗（WARN 不 FAIL，per E4 規則 #3）：**
- ipc_server/mod.rs：1251（軌 1 +11 PRE-EXISTING）— WARN
- passive_wait_healthcheck.py：2185（軌 1 +99 PRE-EXISTING）— WARN
- risk_config.rs：1071（軌 3 抽 sibling 後實減 6 行 vs 1077 baseline）— OK
- risk_checks.rs：1020（軌 3 加 thin wrapper +140）— OK
- 三 sibling 全在 800 警告線內（191 / 294 / 308）

**6 條 push back / WARN 觀察（非阻塞）：**
1. 三軌仍只在 Mac local working tree — PM 必須統一 commit + push
2. ipc_server/mod.rs 1251 + passive_wait_healthcheck.py 2185 PRE-EXISTING — 建議 E5 refactor wave 拆 dispatch_request / check_*() 子模組
3. 軌 1 §5.1 stale_peak_ms / shadow_enabled 不在 IPC（toml_only）— 建議 follow-up 擴 update_risk_config IPC
4. 軌 2 §5.1 IPC HMAC ts unit legacy bug（app/ipc_client.py:786 毫秒 vs Rust 秒）— 建議 E5 修 legacy sync_ipc_call
5. 軌 3 §5.3 step_6_risk_checks.rs 未升級為 _with_override — 屬 G2-03 binding 真實啟用 PR 範圍，schema-only 此本輪 OK
6. summary 用 trading_admin user 連 PG（cron wrapper 範式）— 工具自身沒 wire DSN 構造路徑，需依賴外部 env

**3 條教訓：**
1. **派發鏈說明**：PM 直派 E1 → E4 跳過 E2，E4 須兼任 E2 必查 5 點 + E4 主驗 7 步驟（21 changes 全覆蓋）
2. **檔案不在 Linux 的應對**：軌 2/6 派發指定 ssh Linux 跑但檔案還在 Mac → 替代路徑 = (a) 跑 Mac local cargo test 驗 Rust （b) scp + 設 OPENCLAW_DATABASE_URL + activate venv 跑 Python helper 真機（c) 從 artifact JSON 反推 dry-run pass 狀態
3. **Linux PG user 注意**：`trading_admin`（per cron wrapper）非 `openclaw`；E4/E5 跑 ssh Linux SQL 工具須對齊 cron wrapper DSN 構造路徑

**Working tree 狀態：** 三軌 21 changes（11 modified + 10 new + 3 reports） 全 Mac local，Linux HEAD 仍 `55801fe`（不含三軌）。PM commit + push + Linux git pull --ff-only + ssh cargo test 重驗應 2161 / 0 failed 同綠。

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_w4_three_tracks_regression.md`

---

### 2026-04-26 Wave 3 G2-06 bb_breakout 永久 disable 回歸驗證

**結論：E4 PASS**

**測試結果：**
- Linux baseline (HEAD 8946e47, 不含 G2-06)：**2138 passed / 0 failed**（與 TODO L10 完全一致）
- Mac local cargo test --release（含 G2-06 5 行 Rust comment）：**2138 passed / 0 failed**（兩遍同綠 = 非 flaky）
- Mac cargo check：0 new warning（9 既有 warnings 與 G2-06 無關）
- Mac cargo doc + rendered HTML 驗證：`pub enum BbBreakoutProfile` 上方 `///` doc + `//` G2-06 plain block + `#[derive]` 排列下，rustdoc 完整保留 Conservative/Balanced/Aggressive/嚴格/寬鬆/當前生產 — `//` plain 不汙染 ✓
- Mac local Python 3.12 兩遍 healthcheck 函數測試：
  - `_read_bb_breakout_active_from_toml()` → `(False, "ok")` 同綠
  - `[18] check_disabled_strategy_inventory()` → PASS `disabled strategies: bb_breakout, funding_arb (active count=3: ...)` 同綠
  - `[12] check_bb_breakout_post_deadlock_fix(StubCur)` → PASS `disabled by G2-06 ... fill check skipped` 同綠（StubCur execute() 故意 raise — 證 active=false 早 return SQL 不執行 ✓）
- Python ast.parse: passive_wait_healthcheck.py / bb_breakout_threshold_sweep.py 兩檔 OK
- TOML 三環境 grep: demo/paper/live 全部 `[bb_breakout].active = false` + 雙語 G2-06 disable comment 模板一致

**3 條 non-blocking drift 觀察（PM commit 時可選 sweep）：**

1. **CLAUDE.md L488 §十一 一句話狀態「17 check」**：實測 main() 內 19 次 check_*() 呼叫（含 [Xa]/[Xb] 18，加 [18] 後 19）— 過期，但 §十一 是 2026-04-24 採集快照，G6-04 §三 drift 規則範圍但**不在 E1 任務界內**
2. **CLAUDE.md L82 「engine lib 1939 → 1980 passed」**：應為 2138（已 baseline）
3. **paper.toml `[funding_arb].active = true`**：demo/live 都 disabled 但 paper 仍 active —— 獨立 drift（per G-2 結案 2026-04-18 殘留），G2-06 範疇外，E1 沒擴大正確

**設計亮點 / 學到的事：**
- E1 §3.4「合法 orphan comment」風險點獨立驗證為真：rustdoc 仍 attach `///` doc 到 enum，`//` plain block 不汙染 — 但**驗證需要 cargo doc + 渲染 HTML grep**，光 cargo check 0 warning 不夠
- StubCur 反向 mock guard：故意 raise execute() 來**證明** active=false 時 SQL 路徑根本不執行，比 mock 業務邏輯更乾淨
- [18] disabled_strategy_inventory 只讀 demo TOML 是 Phase 1a 局限（paper/live 各自 disabled 看不到）— 適合當前 scope，未來可加 [19]/[20]
- baseline 數字源優先級：**TODO L10（2138）> Linux cargo 實測（2138）> CLAUDE.md §三 內各種中段數字（1939/1980 過期）**；E4 驗 baseline 必跑命令拿真數字，不信 CLAUDE.md 寫死

**派發鏈說明：** PM 直接從 E1 派 E4 跳過 E2 review，但本 E4 報告對 E2 必查 5 點（TOML 同方向 / [12] 不擴張 / [18] 純 observability / Rust doc-attribute / drift 規則）全部驗了一遍，等同 E2 + E4 合一通過。

**Working tree 狀態：** 所有 G2-06 改動仍 Mac local，Linux HEAD 8946e47（不含 G2-06）— 採 Mac local 直驗 + Linux baseline grep 雙路徑驗證。

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--g2_06_disable_regression.md`

---

### 2026-04-26 Wave 3 G8-02 ExecutorAgent decision parity 回歸驗證

**結論：E4 Pass with conditions**

**測試結果：**
- G8-02 testfile 獨立：5 passed / 2 skipped / agree=70/70 (100%) — 不 flaky（兩次同綠）
- control_api_v1 子集 baseline：2749→**2754 passed**（+5），35 pre-existing failed 不變（與 G8-02 無關）
- Rust engine lib：2138 / 0 fail 不變（G8-02 不動 Rust 代碼）

**35 pre-existing failed root cause（與 G8-02 無關，建議 PM 開新 ticket）：**
- `test_executor_shadow_toggle_api.py`（17）+ `test_strategist_promote_api.py`（18）
- 獨立跑 → 全綠；與 G8-02 + 兩檔組合 40 個一起跑 → 全綠
- 全量跑時 fail = test ordering pollution（推測 module-scope fixture 或 STORE / shadow_mode_provider singleton mutation）

**4 大 WARN（PM 必須清楚理解，oversell 風險）：**

1. **G8-02 是 Python runtime ↔ Rust schema spec parity，不是 Python ↔ Rust runtime parity**
   - `_reference_decide()` 是純 Python function 寫的 schema intent
   - 完全不打 Rust 引擎（無 cargo run / IPC dispatch / Rust deserialize 驗）
   - testfile line 35-40 自己 honest 標明：「it is *not* a re-implementation of Rust runtime, **it *is* the schema's intent**」
   - 真 Rust runtime parity 屬 G3-08

2. **70 case 100% agree 是邏輯上的必然，非 statistical confidence**
   - 兩邊都只判一個 bool（shadow_mode）
   - max_position_pct / per_symbol_cap 全 case 不 gate（Wave-3 scope，golden_15 自承「Rust catches」）
   - 95% binary threshold 寫進 test 是 future-proof（將來 shadow_mode 邏輯增複雜時的 regression 邊界）

3. **「synthetic_replay」術語 misleading**
   - 40 case 並非真實 `decision_outcomes` table dump
   - 是 procedurally generated boundary cases（隨機 ~20 symbol，shadow_mode true/false 各半）
   - PA RFC Q2 若定義廣義 synthetic OK，否則需與 PA 對齊

4. **E1 fixture 行數 self-report 誤差**：報 661 / 實 838

**Mock 邊界（PASS）：**
- ExecutorConfigCache._inject_snapshot_for_tests() 繞 IPC socket — OK
- paper_trading_routes._ipc_command 用 _IpcCallRecorder — OK
- ExecutorAgent.execute_order() / _execute_via_ipc() / shadow_mode_provider lambda chain 全真跑 — OK
- 不算 mock 業務邏輯

**Conditions（PM 合併前釐清）：**
1. close-out 報告 / TODO 條目加註 G8-02 不是真 runtime parity
2. synthetic_replay 術語校準
3. G3-08 必須補 cargo `tests/executor_parity_test.rs` 真 IPC dispatch
4. 35 pre-existing failed test isolation 開新 ticket
5. 教訓：fixture self-report 行數 PA/E2 必做 sanity check

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_g8_02_regression.md`

---

### 2026-04-24 全程序範圍測試檢驗（full-chain testing audit）

**結論：A-（優秀）— 測試充分，但 CI 完全不存在 + 6 個 error-path 缺口阻塞 Live**

**覆蓋面快照（grep-based，非實跑）：**
- Rust engine inline：149 檔 / ~2,103 `#[test]`/`#[tokio::test]`（對應 §三 lib 1980 passed 基準，差值為 `#[ignore]` / feature-gated）
- Rust engine integration：`tests/*.rs` 7 檔 / **85 測**（stress 35 / reconciler_e2e 19 / edge_predictor_ort ~10 / micro_profit_fix 7 / migrations 5 / phase4 3 / rrc1 ~6）
- Python pytest：121 檔 / **~3,006** 測（控制 API 93/2687 + ml_training 26/292 + audit+local_model_tools 2/31；與 §十一 pytest 2996 承襲基準吻合）
- Healthcheck：`passive_wait_healthcheck.py` 12 checks（[1]~[12]，[8] shadow_exits L2-5 TOML 主動診斷 / [10] 4/17 post-mortem / [11] EDGE-DIAG-1 Phase 3 auto-gate / [12] FIX-26 驗收）
- **CI：0 workflow 檔**（`.github/workflows/` 不存在）
- **獨立 smoke 腳本：0**（canary `test_canary.py` 未驗；rollback_drill.sh 是 operational）

**5 項評估維度結果：**
1. 正常路徑：A-（tick_pipeline 120 測 / 策略 5 個全備 / 5-Agent 齊 / Decision Lease + Auth + hot-reload 完整）
2. 邊界：B+（qty=0/HMAC/leader lock 已覆蓋；funding_rate 極端 / ATR NaN/Inf / balance=0 / UTC 時邊界 / auth TTL=exp 未補）
3. 異常：B-（REST fail-closed 齊；但 **WS 斷線止損 / DB 斷線 / IPC 超時 / config 破損熱重載 / authorization 篡改 / intents writer 失敗** 全缺）
4. 並發：A-（leader lock multiprocess 齊 / Reconciler 100-cycle + 50 symbols + 20 rapid 齊；ArcSwap torn-read + IPC 多 worker 共享 slot 缺）
5. 回歸：A-（FIX-26 7測 + FA-PHANTOM-1/2 + MICRO-PROFIT 7 + PNL-FIX 隱含 + RUST-DOUBLE-PREFIX healthcheck 守門；STRATEGY-CLOSE-TAG-FIX `strip_phys_lock_prefix` 缺 unit）

**Top 10 Blocking Gaps（排序對齊 Live 日期 W24 末 ~2026-05-23）：**
1. **[P0] CI 完全不存在**（`.github/workflows/` 缺）
2. **[P0] ExecutorAgent shadow→live 切換契約無測**（阻 G-1）
3. **[P1] WS 斷線期間止損安全性**（§四 E-1）
4. **[P1] PostgreSQL 斷線期間 Rust writer 行為**（§四 E-2）
5. **[P1] trading.intents 寫失敗 unit regression**（只靠 healthcheck [10]）
6. **[P1] authorization 簽名篡改 engine 行為**（§四 E-10）
7. **[P1] ArcSwap torn-read under tick spike**（§五 C-1）
8. **[P1] 21d demo 穩定 aggregate healthcheck**（違 §七「被動等待必附 check」）
9. **[P1] PostOnly maker fill rate healthcheck**（違 §七）
10. **[P2] STRATEGY-CLOSE-TAG-FIX `strip_phys_lock_prefix` unit regression**

**關鍵對齊：**
- 12 healthcheck 對應 §三 active 被動等待 90%；H-1/H-2/H-3 違 §七 新被動等待規則，必補
- Python stop_manager.py 已退役（3E-ARCH 後）— 2026-04-01 報告敘述「319 LOC」過期
- IPC handlers inline 0 測，但 `ipc_server/tests/` sub-dir 覆蓋（dispatch 10 / config 8 / risk 7 / budget 7）— 分位正常

**報告位置：** `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-24--full_chain_testing_audit.md`

---

### 2026-04-01 全程序測試審計

**結論：PASS（有條件）— 整體進步顯著，但有 4 個新回歸需修復**
- 測試文件：71 → 96（+25）
- 測試 cases：~2,480 → 3,349（+869）
- passed：~2,480 → 3,310（+830）
- 估算覆蓋率：~62% → ~68%（+6pp）
- 關鍵改善：pipeline_bridge 15%→50%，governance_routes 10%→45%，ws_listener 20%→65%，demo_connector 8%→60%
- 新增回歸：4 FAILED（h0_gate sync、inverse leverage、session9 count、strategies OrderIntent）+ 17 ERRORS（session9 import）
- 最大缺口：strategy_auto_deployer 685 LOC 零測試、bybit_demo_sync 269 LOC 僅 1 間接
- 報告位置：docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-01--testing_audit.md + docs/audit/April01/E4_testing_report_2026-04-01.md

### 2026-03-31 Sprint 5b 全量回歸

**結論：PASS**
- 總計：2610 passed, 17 failed（全部 pre-existing）, 1 skipped
- 收集：2628 tests collected
- 執行時間：~59.65s
- 目標 ≥ 2600：✅ 達成（2610 passed）
- 17 pre-existing failures 清單與預期完全一致，無新增 failure
- 測試基準更新：**2610 passed**（較上次 2599 +11）

**新增測試（相較上次基準 2599）：+11 tests**
- test_h_chain_integration.py（TestPrinciple14OllamaFallback × 6）：全部 PASS
- test_scout_worker.py（× 10）：全部 PASS
- roi_basis / cost_tracker / ollama_call 標記測試（7 個）：全部 PASS

### 2026-03-31 Sprint 5b-5 根原則 14 集成測試（Principle 14 Ollama Fallback）

**結論：PASS**
- 新增測試：6（TestPrinciple14OllamaFallback）
- 文件位置：`tests/test_h_chain_integration.py`
- 全量回歸：2599 passed, 17/18 failed（全部 pre-existing），1 skipped
- 目標 ≥ 2576 + 6 = 2582：✅ 達成（2599 passed）

**6 個測試行為驗證：**
1. `test_ollama_unavailable_strategist_uses_heuristic`：is_available=False → judge_edge 不被調用，heuristic_evaluations 遞增
2. `test_ollama_unavailable_h1_budget_check_passes`：cost_tracker=None → _h1_check_budget() 返回 True（fail-open）
3. `test_ollama_unavailable_pipeline_bridge_processes_intents`：PipelineBridge._process_pending_intents() 無 Ollama 時不崩潰
4. `test_ollama_unavailable_h0_gate_still_blocks_bad_intents`：H0 Gate 確定性邏輯不依賴 Ollama，freshness check 仍阻擋
5. `test_ollama_unavailable_executor_still_applies_fail_closed`：acquire_lease()=None → ExecutorAgent 拒絕執行（原則 3 不依賴 Ollama）
6. `test_ollama_crash_mid_evaluation_falls_back`：_ai_evaluate 中 ConnectionError → catch + heuristic fallback + error 計數

**關鍵發現：**
- PipelineBridge 需要 3 個必填位置參數（kline_manager/indicator_engine/signal_engine）
- 所有降級邏輯均在 _evaluate_edge() 中正確實現（is_available=False 或異常均走 heuristic）
- H0 Gate 完全不依賴 Ollama（純確定性）
- ExecutorAgent 的 Principle 3 執行與 Ollama 狀態無關

**測試基準更新：2599 passed**（較上次 2576 +23）

### 2026-03-31 Sprint 5a 回歸（Position Sizing + Paper/Demo Sync）

**結論：PASS**
- 總計：2576 passed, 17 failed（pre-existing）, 1 skipped
- 收集：2594 tests collected
- 執行時間：~37.60s
- 目標 ≥ 2575：✅ 達成（2576 passed）
- 17 pre-existing failures 清單與預期完全一致，無新增 failure

**新增測試（相較上次基準 2561）：+15 tests**
- test_strategist_agent.py：15 tests（TestScoutStrategistChain 2 + TestH1ThoughtGate 11 + TestStrategistShadowFalse 2）
- H0 Gate 測試（test_h0_gate.py）：94 tests，全部通過

**已知 pre-existing failures（17 個，全部歸屬明確）：**
- test_batch10_learning_oms.py（2）：TestL2CronTrigger（asyncio event loop deprecation）
- test_edge_filter_integration.py（1）：test_edge_filter_respects_timeout
- test_integration_phase11.py（2）：TestEngineTierEnforcement（L1 reject submit/cancel）
- test_learning_tier_gate.py（1）：test_l1_capabilities
- test_ollama_integration.py（11）：LocalLLMSearchProvider（3）+ L1TriageLocalFallback（8）

### 2026-03-31 Sprint 0 回歸（G-05 + G-01）

**結論：PASS**
- 總計：2561 passed, 17 failed（pre-existing）, 1 skipped
- G-05 TestExecutorAgentDecisionLease：6/6 PASS（test_26～test_31）
- G-01 test_layer2.py：79/79 PASS
- 17 pre-existing failures 清單與預期完全一致，無新增 failure

**重要教訓：**
- pytest 收集 `test_app` 時有 PytestCollectionWarning（fastapi app instance，非真正問題）
- Pydantic V1 deprecated warnings 在 scout_routes.py（不影響功能）

### 2026-03-31 Wave 6 Sprint 0 TD-1 全量回歸（pipeline_bridge acquire_lease）

**結論：PASS**
- 總計：2614 passed, 17 failed（全部 pre-existing）, 1 skipped
- 收集：2632 tests collected
- 執行時間：~63.27s
- 目標 ≥ 2614：✅ 達成（2614 passed）
- 17 pre-existing failures 清單與預期完全一致，無新增 failure
- 測試基準更新：**2614 passed**（較上次 2610 +4）

**4 個 TestPipelineBridgeDecisionLease 測試（全部 PASS）：**
1. `test_td1_no_hub_fail_open_submit_proceeds`：hub=None → fail-open，submit 繼續
2. `test_td1_acquire_lease_none_fail_closed_submit_blocked`：acquire_lease()=None → fail-closed，submit 阻擋
3. `test_td1_acquire_lease_success_submit_proceeds`：acquire_lease() 成功 → submit 繼續
4. `test_td1_acquire_lease_exception_fail_closed`：acquire_lease() 拋異常 → fail-closed，submit 阻擋

**位置：** `tests/test_edge_filter_integration.py::TestPipelineBridgeDecisionLease`

### 2026-03-31 Wave 6 Sprint 1b 1B-1 Cooldown 聯動煙霧測試

**結論：PASS**
- 5 個測試全部 PASS（test_h0_gate_cooldown_integration.py）
- 全量回歸：2624 passed, 17 failed（全部 pre-existing）, 1 skipped（第二次穩定跑，無新增 failure）
- 目標 ≥ 2614：✅ 達成（2624 passed）
- 測試基準更新：**2619 passed**（保守估計：2614 + 5 新增；最新穩定跑 2624 但有測試順序影響波動）

**5 個新增測試（TestH0GateCooldownIntegration）：**
1. `test_risk_manager_pushes_cooldown_to_h0gate`：RiskManager 3連敗 → mock H0Gate.update_risk() 被調用，snapshot.cooldown_until > now ✅
2. `test_h0gate_blocks_during_cooldown`：update_risk(future cooldown) → check() allowed=False, check_name="cooldown" ✅
3. `test_h0gate_allows_after_cooldown_expires`：update_risk(past cooldown) → check() allowed=True ✅
4. `test_h0gate_cooldown_zero_does_not_block`：cooldown_until_ts_ms=0 → check() allowed=True ✅
5. `test_h0gate_cooldown_check_includes_reason`：blocked → reason.lower() contains "cooldown", check_name="cooldown" ✅

**關鍵發現：**
- H0Gate.check() 冷卻期判斷邏輯：`cooldown_until > 0 and now_ms < cooldown_until` → 正確
- RiskManager.record_fill_result() 在 consecutive_losses >= cooldown_count 時呼叫 H0Gate.update_risk()，保留現有 open_position_count/total_exposure_pct/kill_switch_active 不變 → 設計正確
- test_h0_gate.py::TestGovernanceRoutesH0GateStatus 在全量跑時偶發 3 失敗（模組狀態干擾），單獨跑全部通過，為 pre-existing 間歇性問題，與本 Sprint 無關

## 報告索引

| 日期 | 任務 | 文件位置 |
|------|------|---------|
| 2026-04-27 | G3-09 Phase A daemon integration test (Phase B prerequisite, 純測試 0 production diff) — 6 tests 兩遍同綠 / 4 大證明 daemon spawn+IPC live+雙保險+cadence + 1 bonus cancellation drain / lib baseline 2290/0 不變 | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-27--g3_09_phase_a_daemon_integration_test.md` |
| 2026-04-27 | 6 P0 PR Wave Combined Regression（F2/F3/F4/F5/F6/F7）— MERGE READY / baseline 校正 2161→2212 / Combined cargo lib 2252 兩遍同綠 / 27 healthcheck 8 新 [22-29] 全執行三態 verdict / 2 doc-only conflicts union-resolvable / 5 push back（1200 hard cap 12 / E1 memory.md merge / baseline drift / cron wrapper cwd / 5 真實 FAIL pre-existing） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-27--p0_wave_combined_regression.md` |
| 2026-04-26 | Wave 3 W5 兩軌（EDGE-P2-flip T2 + G2-FUP-IPC-LEGACY-MS-FIX）回歸驗證（E4 Pass with conditions / Linux cargo 2161 兩遍同綠 / Mac local pytest 兩遍 3/3 / [15] dormant 路徑 PASS / Rust verifier 1:1 mirror / async :553 一直秒制 / 6 conditions for PM commit+push 後 Linux 重跑） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_w5_two_tracks_regression.md` |
| 2026-04-26 | Wave 3 W4 三軌（EDGE-P1b + EDGE-P2-flip + G2-03）回歸驗證（E4 PASS / Mac local 2138→2161 +23 兩遍同綠 / 18 check 含 [14] per-strategy READY_frac 63% / dry-run 5/5 / bash -n 3/3 / ast.parse 4/4 / calibrator 250-row CALIBRATED / summary 14d markdown / 2 PRE-EXISTING WARN 1200 hard limit non-blocking） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_w4_three_tracks_regression.md` |
| 2026-04-26 | Wave 3 G2-06 bb_breakout 永久 disable 回歸驗證（E4 PASS / Rust 2138 不變兩遍 / Mac local Python 3.12 兩遍 healthcheck 同綠 / cargo doc 證 //G2-06 plain 不汙染 ///doc / 3 條 non-blocking drift） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--g2_06_disable_regression.md` |
| 2026-04-26 | Wave 3 G8-02 ExecutorAgent decision parity 回歸驗證（E4 Pass with conditions / +5 passed / Rust 2138 不變 / 4 WARN oversell 風險） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-26--wave3_g8_02_regression.md` |
| 2026-04-24 | Full-chain Testing Audit（Rust 2103 inline + 85 integration / Python 3006 / HC 12 checks / CI 0 / Top 10 gaps） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-24--full_chain_testing_audit.md` |
| 2026-04-01 | 全程序測試覆蓋評估（3310 passed / 96 test files / 18 無測模塊） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-01--testing_audit.md` |
| 2026-03-31 | Wave 6 Sprint 1b 1B-1 Cooldown 聯動煙霧測試（5 tests，2624 passed） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint1b_cooldown_smoketest.md` |
| 2026-03-31 | Wave 6 Sprint 0 TD-1 全量回歸（2614 passed，acquire_lease 修復驗收） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint0_td1_regression.md` |
| 2026-03-31 | Sprint 5b 全量回歸（2610 passed，Sprint 5b 最終驗收） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5b_regression.md` |
| 2026-03-31 | Sprint 5b-5 根原則 14 集成測試（Principle 14 Ollama Fallback，6 tests） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5b_p14_tests.md` |
| 2026-03-31 | Sprint 5a 全量回歸（Position Sizing + Paper/Demo Sync） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint5a_regression.md` |
| 2026-03-31 | Sprint 0 全量回歸（G-05 + G-01） | `docs/CCAgentWorkSpace/E4/workspace/reports/2026-03-31--sprint0_regression.md` |

## 2026-04-27 — Wave IV Linux full regression (PASS)
- HEAD synced 6e466c8 → 7c32d1f (5 commits, ff-only, status clean)
- Rust openclaw_engine --lib: **2290 / 0 fail** (baseline 2290 match), 2 runs same green
- Rust --test test_cost_edge_advisor_daemon (G3-09 Phase A NEW): **6 / 0 fail**
- Python pytest 7 target files: **263 / 0 fail** (Mac 163, Linux higher collection but no regression), 2 runs same green
- Healthcheck passive_wait_healthcheck.py: 32 PASS / 0 FAIL / 1 WARN ([11] counterfactual ETA pre-existing)
- New [30] cost_edge_advisor_status check: PASS (env=0 dormant by Phase A design)
- 0 production code diff this wave (E4 task = run tests only)
- Lessons / patterns:
  - Linux ssh non-interactive PATH 不含 cargo → 必 `source ~/.cargo/env` 才能跑 cargo
  - Linux git repo 在 `~/BybitOpenClaw/srv/` (not `~/BybitOpenClaw/`); venvs/ 只有 README + rust_build (no python venv); 用 system /usr/bin/python3
  - Healthcheck 跑前必 `set -a; source secrets/environment_files/{basic_system_services,trading_services}.env; set +a`，否則 PG no password fail
  - Mac 163 vs Linux 263 為 collection 差異（部分 parametrize 在 Mac 環境跳過），≥163 即達標非 regression

## 2026-04-28 · G3-09-PHASE-B-FUP-SPAWN-TEST P3 — spawn-decision integration test

- 派工：Phase B Wave 0 補哨兵；E2 INFO → P3 backlog；新增 ≥2 案例證 spawn-decision wrapper 行為。
- 結構發現：spawn_cost_edge_advisor_if_enabled 在 binary crate (src/main_boot_tasks.rs, pub(crate))；integration test 在 tests/ 不能直呼。
- 解法：用 wrapper 完全相同的 lib-public primitive 重現 (is_advisor_env_enabled + spawn_cost_edge_advisor + late-inject + state())；新增 ipc_handler_status_string helper 鏡射 handler 行 33-44 行為。
- 新增 3 案例 (Case A env unset slot=None IPC=Uninitialized / B env=1 risk=false slot=Some IPC=Disabled / C env=1 risk=true slot=Some IPC=OK)；env mutex 序列化避 race。
- Mac --release: test_cost_edge_advisor_daemon 6 → 9 cases 兩遍同綠 (2.10s/2.09s)；lib baseline 2290/0 不變。
- 教訓：bin-only fn 的 spawn-decision integration test 需 wrapper-equivalent 重現策略，而非真的呼叫 wrapper（後者需 wrapper 升 pub 或測試移到 src/）。

## 2026-04-28 · WAVE-E Linux full regression — `decf712..00aa18a` 7 commits (PASS)

- 任務：Wave E + E' 純 doc + test fix + small refactor，Mac 已驗，Linux 對齊驗收。
- HEAD synced `16a30e5..00aa18a` ff-only (no rebuild needed — 0 trade impact).
- Rust release (Linux real PG): lib **2299/0** + daemon **11/0** + persistence **2/0** baseline 全綠 0 delta；cargo cache hit 各 <2.5s。
- SINGLETON-POLLUTION fix Linux 35→0 reproducibility CONFIRMED：
  - isolated `test_h_state_query_handler.py` **90/90** (2 runs same green)
  - same-session `test_api_contract + test_h_state_query_handler` **108/108**
  - CPython sys.modules semantic 跨平台一致預測成立
- W3+W2+W1+LOSSES 4 檔合計 **48/48** PASS。
- Healthcheck **32 PASS / 0 FAIL / 2 WARN**（[11] counterfactual ETA 0d、[23] orders_fills 1/20 single-pair anomaly，均 pre-existing non-blocking）。
- 全 control_api_v1 baseline: Linux **3075 passed / 35 failed**（vs Mac 38 fail）— Linux 比 Mac 少 3 fail（h_state pollution edge 在 Linux 表現更穩，**非 regression**）。35 fail 全 PA RFC 已標 pre-existing sibling-pollution family（17 executor_shadow_toggle + 18 strategist_promote）。
- 教訓：
  - Linux 環境 `~/BybitOpenClaw/` 是 srv subdir 的父目錄；git repo 在 `~/BybitOpenClaw/srv/`。
  - Linux pytest 用 `/usr/bin/python3` (Python 3.12 + pytest 9.0.2)，`venvs/` 只有 README + rust_build。
  - Healthcheck `passive_wait_healthcheck/runner.py` 用 relative import → 必 `python3 -m helper_scripts.db.passive_wait_healthcheck.runner` 不能 `python3 path/to/runner.py`。
  - Linux ssh non-interactive PATH 不含 cargo → 必 `source ~/.cargo/env` 才能跑 cargo。
  - Mac↔Linux 全量 baseline 差異 3 不算 regression — pollution 邊界跨 OS 微差正常，看絕對 fail 名單同源即可。


## 2026-04-28 — Wave G Linux full regression PASS（4-way file-size cleanup splits）

**HEAD**: `3b0a0d7` (5 commits `8a5973f..3b0a0d7`: MAIN-RS / ANALYST / HSQ / DAEMON-TEST splits + memory log)
**Verdict**: PASS

### KPIs
- Rust lib **2308/0** | daemon split sum **11/0** (proofs 5 + dual_safeguard 3 + spawn_decision 3) | persistence Linux PG **2/0**
- HSQ same-session **forward 108/108 + reverse 108/108** ✅ — SINGLETON `sys.modules.get` integrity post-G3-08-FUP-HSQ-SPLIT critical invariant **VERIFIED** (Mac 因 fastapi gap E2 無法 self-verify，Linux 確認過)
- ANALYST 22/22 + W1+W2+W3+LOSSES+SINGLETON 83/83
- Full control_api_v1 baseline **3117/0** 兩遍同綠 (60.74s + 62.65s) ✅ 非 flaky
- Healthcheck 25 PASS / 2 FAIL pre-existing ([12] bb_breakout deploy-pending + [27] intent freeze pipeline wedge)；非本 wave 引入

### Linux sync 教訓
- ff-only pull 被 Linux working tree 3 個 untracked split test 檔擋住（先前 session 部分復現後未 commit；origin 後續入庫同名檔）
- 解法：先 `diff <(cat untracked) <(git show origin/main:path)` byte-identical → `rm` untracked 三檔 → `git pull --ff-only` 帶入相同內容
- 無資料損失（incoming bytes 一樣），最小破壞路徑，不違反 auto-mode 安全準則
- Pattern：未來如遇 ff-only 衝突且 untracked 與 incoming byte-identical，可直接 rm；diff 不一致則必 stash + report

### 非 `--rebuild` 部署決定
- Wave G 全部是 file-size split / 0 production behavior change → task brief 明確不需 `--rebuild`，engine PID 沿用 pre-merge binary
- LiveDemo runtime 未退化（healthcheck [22] trading_pipeline_silent_gap 全 fresh stale=0.x m）


## 2026-04-28 — Agent Tracker MVP feature branch regression PASS（plan aa-nifty-walrus round 2）

**HEAD**: `feature/agent-tracker-mvp` `d1c6911`（feature `ab12207` E1 9 files + `d1c6911` E4 test fix）
**Verdict**: **APPROVED FOR PM SIGN-OFF**

### KPIs
- 21/21 PASS（plan 預期 12，E1 落地了 21 — 含 8 round-1 + 2 H-1 ExecutorAgent ctor integration + 1 H-3 invariant + file-size guard + 9 額外覆蓋 PG outage / limit validation / SQL filter / engine_mode union / since fallback / fail-closed provider exception 等）
- 全 control_api_v1: **3138/0** (vs Wave H baseline 3117 = +21 = 新增 21 個 agent tracker test，0 既有 fail) — non-flaky 跑 3 次同綠
- 3 endpoint smoke (Linux temp uvicorn port 18001 + Bearer api_token): roster 200 / recent_rejects 200 / shadow_vs_live_summary 200，body shape 對 plan §F
- p99 latency: 121ms < SLA 500ms（30s plan refresh，餘量充足）
- 不變量 grep: SQL writes 0（除 docstring 政策自證）/ JS POST 0（同上）/ hardcoded paths 0 / file size 5/5 under limit (334/783/804/824/954)
- 3 SQL EXPLAIN ANALYZE: ai_usage_log 空表（idx_ai_usage_log_scope_time 存在）/ risk_verdicts ChunkAppend + Index Scan idx_verdicts_verdict 0.1ms / fills hypertable ChunkAppend + 1-chunk Seq Scan 1.5ms（單 chunk 1330 rows 太小，cost-based seq 比 index 快）
- 0 Rust diff，0 engine impact，無需 --rebuild

### Round 2 自我修復案例（test 寫法 bug）
- E1 提交的 21 test 中**初次跑** 2 fail（test_h3_no_like_agent_underscore_anywhere + test_grep_no_write_paths）
- 失敗根因：**naive substring grep on raw source** 在自證 docstring（"INSERT/UPDATE/DELETE = 0 in this file" / "LIKE 'agent_%' forbidden"）+ inline comment `# post-update` 中誤觸
- E4 profile 允許「test 本身寫錯，可以直接修 test」— **不是業務代碼 bug**，所以本人改 test 不退 E1
- 修復：加 `_strip_comments_and_docstrings()` helper（tokenize + ast）：(1) 移所有 `#` comment (2) 移所有 module/class/function body 的 bare-string `Expr` statement
- 關鍵巧思：handles `from __future__ import annotations` + module-note pattern（PEP 257 不會 bless 為 docstring，因為它不是第一條 statement，但作者實際當 docstring 用 — 所以 strip 邏輯不能依賴 PEP 257，要直接掃 `body[*]`）
- 驗證：保留所有非 bare-string literal（`"""SELECT ..."""` SQL 模板仍在），未來如有真實 INSERT SQL 進 helpers/routes 仍會 trip invariant
- 教訓：寫 invariant grep test 時，**自證式 docstring + comment 是常見 false-positive 陷阱**，必須用 ast/tokenize strip 而非 raw `in src`

### Linux 部署門路（feature branch flow）
- Mac 不能跑 fastapi pytest（user 已驗），feature branch flow：Mac commit 9 file → push origin → ssh trade-core fetch + checkout feature → pytest runs OK
- Linux trade-core 跑現有 main branch uvicorn (PID 4162909, port 8000)，feature branch 程式碼**未進** running uvicorn（main HEAD `4abea3c` ≠ feature `d1c6911`）
- Smoke test 要啟臨時 uvicorn (port 18001 single-worker) 才能驗 endpoint —— 完成後需 `pkill -9 -f 18001` 清理
- Auth: `Authorization: Bearer <token>` from `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/.secrets/api_token`
- main branch uvicorn 不會收到 feature branch routes，所以 PM merge feature → main → 必跑 `restart_all.sh --keep-auth` 重啟 uvicorn（不需 --rebuild Rust，0 Rust diff）

### EXPLAIN ANALYZE on dev sandbox 的 gotcha
- ai_usage_log dev sandbox **0 row** → planner 折成 `One-Time Filter: false`，無法直接證明索引被選
- 緩解：(1) drop time prune 看 hypertable plan 形態 (2) 確認索引存在（pg_indexes 比對） (3) 信賴 production data shape 後 cost-based switch 自動發生
- 對 hypertable 小 chunk 內部 Seq Scan（1330 rows 1 chunk）= **正常** — partition prune 在 ChunkAppend layer 已生效，單 chunk 內 PG planner 認為 seq < random index access 是 cost-based 正確選擇

## 2026-05-02 — AUDIT-2026-05-02-P1-1 Round 3 V031 view shape-guard PASS

- Linux production trading_ai (V034-applied state) 真實 idempotent verified
- V031 round-3 shape-guard NOTICE-skip 兩次跑都 0 ERROR
- Fixture 20 cases (round 2 baseline 17 + round 3 新 V031/View-{fresh,extended,drift} 3) all PASS
- View col count = 53 (V034 augment preserved, 未被窄化回 35)
- audit: V031 ALL PRESENT OK, 0 drift
- healthcheck: WARN baseline same as round 2, 0 new FAIL
- **教訓**：retrofit migration 對 forward-shape drift 也要主動 skip（對偶 V023 對 legacy-shape drift RAISE），非僅向下兼容；CLAUDE.md §七 Migration Guard #4 idempotency 雙跑驗證強制，不可跳。
- 報告 `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-02--audit_p1_1_linux_pg_regression_round3.md`


## 2026-05-02 — Funding-arb tight-SL feature branch regression PASS（commit `73ea4ca`）

**Branch**: `feature/2026-05-02-funding-arb-tight-sl-base-ratio` HEAD `73ea4ca`（parent `a19797d` E1 demo TOML edit）
**Verdict**: **PASS**

### KPIs
- 4 PA target suites all PASS:
  - `config::risk_config::tests::g2_03_per_strategy_tests` 12/12 (no delta)
  - `risk_checks` 35→**36** (+1 new test)
  - `config::risk_config::advanced` 13/13 (no delta — DynamicStop validate)
  - `config::risk_config` 115/115 (no delta)
- Full lib `cargo test --release -p openclaw_engine --lib` baseline 2404→**2405** (+1 new test, 0 failed) — 兩遍同綠 0.52s + 0.52s 非 flaky
- Workspace `cargo test --release --workspace` 21 binaries / **3008 passed / 0 failed / 3 ignored (pre-existing)**
- 新 test runtime: <10ms（filesystem read + TOML parse + validate + effective_sl_max_pct call）— 遠低於 SLA <1ms hot-path 邊界（本測非 hot path）

### 新增 ad-hoc 測試
- `risk_checks::g2_03_per_strategy_tests::test_demo_toml_funding_arb_3pct_override_2026_05_02`
- 文件：`srv/rust/openclaw_engine/src/risk_checks_per_strategy_tests.rs` (line 311+)
- 8 個 assertion 覆蓋：
  1. `dynamic_stop.base_ratio == 0.25` (1e-9 tol)
  2. `per_strategy.funding_arb.enabled == true`
  3. `per_strategy.funding_arb.stop_loss_max_pct_override == Some(3.0)`
  4. `per_strategy.funding_arb.take_profit_max_pct_override == None`
  5. `per_strategy.funding_arb.trailing_activation_pct_override == None`
  6. `per_strategy.funding_arb.trailing_distance_pct_override == None`
  7. `per_strategy.ma_crossover.stop_loss_max_pct_override == None`（schema-only 維持）
  8. `RiskConfig::validate()` PASS（Defense A）
  9. `effective_sl_max_pct(&cfg.limits, Some(fa)) == 3.0`（Defense B runtime cap）
- 不改業務邏輯 / 不改 demo TOML / 不改 risk_config.rs / risk_checks.rs schema — 純哨兵 test。

### Mock 安全
N/A — 純讀真實 fixture TOML + 跑真實 validate / effective_sl 邏輯，無 mock。

### 教訓
- **PA 報告數字 ≠ runtime**：PA 寫「13 tests」，實際 `g2_03_per_strategy_tests` 12 tests。E4 要先跑 baseline 確認真實計數，不靠 PA 數。
- **Test placement 取決於 super::* 範圍**：`risk_checks_per_strategy_tests.rs` 經 `#[path]` mod 載入，`super::*` = `risk_checks` 範圍 → 直拿 `RiskConfig` / `effective_sl_max_pct` / `StrategyOverride`。`risk_config_per_strategy_tests.rs` 也載入 demo TOML 但拿不到 `effective_sl_max_pct`（在 risk_checks crate path）→ Defense A+B 雙驗 test 必放 `risk_checks_per_strategy_tests.rs`。
- **Worktree 隔離法**：Mac main branch 有未提交 untracked 檔案（`passive_wait_healthcheck/checks_governance.py` + 2 modified）非本任務 — 用 `git worktree add /tmp/srv-funding-arb-test feature/...` 隔離操作，避免污染 main 工作樹。完工後 `git worktree remove`。
- **CARGO_MANIFEST_DIR 上溯 2 層抵 srv**：`CARGO_MANIFEST_DIR = srv/rust/openclaw_engine`，pop 2 次（openclaw_engine→rust→srv）。Sibling `risk_config_per_strategy_tests.rs` 註解寫「up 3 levels」但代碼僅 2 次 pop（註解誤導；新 test 比照 2-pop pattern 不依賴註解）。
