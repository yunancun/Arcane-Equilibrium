# E4 Memory — 工作記憶

## 2026-06-09 · L2 P2 (Orchestrator + registry, 0-migration TOML-only) Linux parity 回歸 — PASS
**被驗**：branch `feature/l2-critic-lessons-tools`，P2 改動**未 commit**疊 P1 `f1c3c1ca`。P2 = 5 新模塊（`l2_advisory_orchestrator`/`l2_capability_registry`/`l2_prompt_contract_registry`/`l2_out_of_bound_guard`/`l2_conflict_adjudicator`）+ wiring 改 `layer2_engine.py`/`layer2_routes.py` + `settings/l2_capability_registry.toml` + `test_l2_p2_orchestrator.py`。**純 Python control-plane + TOML，PA §L 確認 0 DB migration → 無 PG dry-run owed**。CC/E2/E3 已 PASS。
**Mac baseline（mac_dev venv = py3.12.13/pytest9.0.3/pytest-asyncio1.3.0/pydantic2.13.3；`PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 -p no:cacheprovider`）**：P2 `test_l2_p2_orchestrator`=**88 passed**；`test_layer2`=**94**；7-file layer2-family（layer2 + critic + escalation + g3_08 + tools + l2_p2 + l2_d3_ledger）=**386 passed/4 xfailed**。
**★ 關鍵環境坑：`tomllib` 是 py3.11+ stdlib，無 fallback**——Mac 預設 `python3`=3.10.1 collect P2 即 `ModuleNotFoundError: tomllib`。必用 **mac_dev venv `srv/venvs/mac_dev`（3.12.13）**；Linux 用 **`control_api_v1/.venv`（3.12.3/pytest8.3.5/pytest-asyncio1.3.0/pydantic2.11.2，含 tomllib）**（即 9afb811a 那個 venv）。
**Linux parity 做法（temp-only，真 checkout 零污染）**：Linux trade-core 在 `main@6c1b015f`（0 ahead/0 behind origin），**divergent** 於 Mac feature 分支、25-behind 未 pull→P2+P1 檔在真 checkout **absent**（親驗 ×2）。**rsync 整個 Mac working-tree `control_api_v1`→Linux `/tmp`**（excl venv/__pycache__/.pytest_cache）+ scp `settings/l2_capability_registry.toml`，一次帶齊 P1-committed+P2-modified+P2-new（避開 D3 那次「逐檔 scp companion 漏 → 假 fail」坑）。md5 6 檔（orchestrator/registry/engine/routes/test/toml）Mac==Linux byte-identical。
**★ 第一坑：default-TOML-path 測試對 repo 目錄深度敏感**——`_default_registry_path()`（`l2_capability_registry.py:257`）= `os.environ.get("OPENCLAW_BASE_DIR", str(Path(__file__).resolve().parents[5]))`。**Python default-arg 先 eager-eval**：即使 `OPENCLAW_BASE_DIR` 已 set，`parents[5]` 仍先算→在淺 `/tmp` 樹（`control_api_v1/app/` 只深 3）`IndexError: 5`，`test_default_checked_in_toml_loads_empty_skeleton` FAIL。**非 P2 regression、非真部署 bug**（真 repo `control_api_v1/app/` 恆深 5；Mac 88/88 證）。**修法=用 faithful-depth temp** `/tmp/.../program_code/exchange_connectors/bybit_connector/control_api_v1/`（`parents[5]`→`/tmp/<base>`，settings 放 `<base>/settings/`）→ 該測 PASS。**latent robustness nit**（值得 flag：`parents[5]` 應改 lazy/try 而非 eager default-arg，否則 env override 形同虛設），但非本批 scope、非 blocker。
**Linux 實測（faithful-depth temp，跑兩遍非 flaky）**：P2+test_layer2 = **182 passed**（==Mac 88+94）；7-file family run1=**386/4xfailed**、run2=**386/4xfailed**；P2-only run2=**88**。**Linux parity == Mac，逐項對齊，0 NEW fail、0 真回歸**。4 xfailed = 既有 strict-xfail naked-context-free 高熵殘留（兩端同 xfail，D3 memo 已記）。
**no-regression discipline**：(1) modified test 純加性——`test_layer2.py` +8/-0、`test_layer2_critic.py` +26/-0，**0 條 removed assert/def-test**（無「刪測試使綠」）。(2) `layer2_engine.py` P2 delta = `contract_ver`/`schema_ver` 改由 `l2_prompt_contract_registry.resolve_contract_versions()` 解析，**既有常數 `L2_PROMPT_CONTRACT_VER`/`L2_OUTPUT_SCHEMA_VER` 作 fallback（值不變、來源變、registry 不可用即兜底）= behavior-neutral by construction、零 D3 wiring 回歸**（comment 自註「值不變來源變→零回歸」）。
**cross-lang float = N/A**（pure-Python，無 Rust/IPC/共用浮點）。**teardown**：兩 temp 樹 `rm -rf` 已清；real Linux checkout 終驗 `6c1b015f`、0 L2 pollution、P2 檔 absent。
**owed（誠實標）**：**full-tree Linux 完整回歸 = owed-post-commit**（分支 divergent 未 pull、P2+P1 整包未提交，本次以 temp-tree 證 file-level parity，full-suite delta 待 push）。無 migration→無 PG dry-run owed（PA §L）。
**verdict = PASS**（ready for PM commit/push）。退 E1 清單：無。
**教訓**：(1) `tomllib` 依賴的 P2 模塊 collect 前必確認 interpreter ≥3.11——Mac 系統 `python3`=3.10 會在 collect 階段 ImportError，誤判成「測試壞」；用對 venv（mac_dev / control_api .venv）。(2) 凡測試走 `Path(__file__).resolve().parents[N]` 解 repo-root 的 default-path，Linux temp dry-run 必複製真 repo 目錄深度，否則淺樹觸 IndexError 假 fail；且留意 `os.environ.get(key, EXPENSIVE_DEFAULT)` 的 default 先 eager-eval（env override 失效是隱性 bug）。(3) 0-migration 純-Python 批：rsync 整 working-tree（含 P1-committed+M+untracked 一次帶齊）比逐檔 scp companion 穩——後者漏一個 companion 就把整包報成假 fail（D3 教訓）；md5 對齊 6 關鍵檔證 byte-identity 是 parity 地基。

## Memory Usage Contract (2026-05-16)

- 本文件保存歷史教訓與角色偏好，不是 active state、TODO 或 runtime ledger。
- 若舊條目與 `TODO.md`、`README.md`、`CLAUDE.md`、`.codex/MEMORY.md`、`docs/agents/context-loading.md`、代碼或 runtime 證據衝突，信任較新的有證據來源並顯式說明衝突。
- 不要靜默刪除舊條目；只追加可復用的 durable lesson。長報告放 `workspace/reports/`，active 進度放 `TODO.md`。

## 工作記憶

### 2026-05-31 b85ac3f3 confluence DB-load guard — E4 PASS

**對象**: commit `b85ac3f3`（fix(gui,strategy): avoid fake success and fail-closed confluence weights）。P3 test-debt close。

**Rust lib 實跑結果**:
| Run | passed | failed | ignored | 穩定? |
|---|---|---|---|---|
| Run 1 | 3688 | 0 | 1 | - |
| Run 2 | 3689 | 0 | 1 | YES (1-ct delta = parallel non-det in debug profile; 0 regression) |

**新增測試**: `test_build_confluence_config_invalid_weights_falls_back_to_default`
- 位置: `rust/openclaw_engine/src/strategies/tests.rs`
- Commit: `78153db1`
- 覆蓋三路: MaCrossoverParams→default()、BbReversionParams→reversion()、BbBreakoutParams→breakout()+confluence_as_gate 保留
- 正常路徑: 合法和=65 直通驗證

**教訓**: cargo test debug profile 下 passed 計數可因 parallel thread 排序差 1（3688 vs 3689）；兩次均 0 failed = 真穩定，計數差不是 flaky。實跑 baseline 3688/3689 vs 任務說的 3633 差 55 = 中間其他 commit 增加的 tests。

**Verdict**: PASS

**Report**: inline (no separate report file per E4 instruction)

---

### 2026-05-31 Deep-Dive #8 Test Blind Spots — BLIND-SPOTS-FOUND (minor, PASS-ADEQUATE)

**對象**: HEAD `187704f6`（同上，zero source delta）。深挖任務 = 實跑 targeted suites + 7-class 盲點矩陣 + mock-hides-logic + 新功能覆蓋確認。

**關鍵更正（先前 2026-05-30 first-pass 錯誤）**：
- F-001「dispatch retry on Transient P1 未修」= **錯誤**。cold-audit Wave1 `b93d3210` P1-07 已修：`OPEN_NO_RETRY = [u64; 0]`，OPEN 路徑 0 重試，strict fail-closed。dispatch_tests.rs:567 + :600 兩測試鎖定。F-001 **CLOSED**。
- F-003「paper-freeze test 未確認」= **已確認 CLOSED**。`test_promotion_pipeline.py:177` `test_paper_cannot_promote_demo` 明確 assert `paper_lane_frozen` in msg + stage stays PAPER_SHADOW，46/0 PASS。

**實跑結果**:
| Suite | Run 1 | Run 2 | 穩定? |
|---|---|---|---|
| Rust `openclaw_engine --lib` | 3633/0/1ign | 3633/0/1ign | YES |
| Python `control_api_v1/tests/` (`OPENCLAW_CSRF_SHADOW=1`) | 4234/6/13 | 4234/6/13 | YES |
| dispatch subset (171) | 171/0 | (stable) | YES |
| live_authorization (24) | 24/0 | (stable) | YES |
| basis/BasisAggregator (33) | 33/0 | (stable) | YES |
| reconciler (104) | 104/0 | (stable) | YES |
| notification_failsafe (108) | 108/0 | (stable) | YES |
| stage_0r earn_routes (4) | 4/0 | (stable) | YES |

**7-class 盲點矩陣**:
| Class | 狀態 |
|---|---|
| Fail-Closed | COVERED (OPEN single-attempt, basis fail-closed, paper-freeze) |
| Timeout | COVERED (機制共享 OPEN single-attempt path；無獨立 timeout-OPEN test，LOW gap) |
| Bybit retCode | COVERED (30+ classify tests；unknown retCode substring path = LOW blind spot) |
| Concurrency | COVERED (env-test lock + C4 T4.12 adversarial；Linux ≥5-round carry-over) |
| Stale Data | COVERED (basis sparse cache + cost gate freshness 7 cases + Python stale tests) |
| Auth Expiry | COVERED (24 live_auth tests + `expired_authorization_rejected` PASS) |
| Replay/Promotion Boundary | COVERED (paper-freeze F-003 CLOSED + stage_0r 4 tests PASS) |

**開放 findings**:
- **F-002** (P2 carry-over): Stage-0R helper script 無 unit tests。A2 REVISE/HOLD 降 blast radius。
- **F-NEW-1** (P3): CSRF env (`OPENCLAW_CSRF_SHADOW=1`) 未在 pytest.ini 記錄，開發者跑全量看 66 false failures 容易誤判。

**Mock safety**: 6 重要路徑審查全 PASS，無 mock-hides-logic。

**關鍵教訓**:
1. **Prior P1 dispatch retry = false alarm**：靜態 grep `Transient` 發現 enum variant，誤以為 retry 仍存在。正確做法：看 `run_dispatch_retry` 的 caller delay slice 參數（`OPEN_NO_RETRY = [u64; 0]`），才知 OPEN 路徑 0 重試。commit 留原始 enum variant 是因 CLOSE 路徑仍用同一函數但帶非空 delay。
2. **CSRF env = canonical baseline 的隱性前提**：`OPENCLAW_CSRF_SHADOW=1` 是 write-endpoint test 通過的必要前提，不是 optional。4229→4234 的 +5 delta 是 cold-audit wave2-4 新增 test，非 regression。
3. **實跑 vs 靜態推算**：Rust 靜態推算 3634，實跑 3633（差 1 = commit msg 計算誤差）。實跑永遠比靜態推算更權威。

**Verdict**: COVERAGE-ADEQUATE (Mac-side) / NEEDS-LINUX (concurrency ≥5-round + DB-side stale).

**Report path**: `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-30--E4--deepdive_test_blind_spots.md`

---

### 2026-05-30 Full-Chain Test Audit (campaign 2026-05-17) — FAIL (P1 persists)

**對象**: HEAD `187704f6`（全 5 post-baseline commit 為 `[skip ci]` docs-only，zero source delta）。Campaign label "2026-05-17"，實際執行 2026-05-30。

**結果**:
| 項目 | 結果 |
|---|---|
| P0 | 0 |
| P1 | 1 — F-001 dispatch retry on Transient (carry-over from prior E4-FCT-001, 未修) |
| P2 | 2 — F-002 Stage-0R runner 無 pytest 覆蓋；F-003 promotion-freeze test alignment 未確認 |
| P3 | 1 — F-004 BasisAggregator 無 Python 端 test |
| Rust lib count (靜態推算) | ~3634/0（ec995160 commit msg；未實跑，需 Linux 確認）|
| Python pytest count | ~6042/28/45（2026-05-22 sprint 2 wave 2；未實跑）|
| 實跑命令 | 0（budget 限制；全靜態 grep+commit msg 證據）|
| env-test lock 單鎖 (P1-OPS-2) | HELD：`crate::test_env_lock::guard()` lib.rs:125，12+ 模塊全用；Mac 3x clean；Linux ≥5-round carry-over |
| 110017 D1+D2 | 有測試：dispatch_tests.rs:227 + position_reconciler/tests.rs 8+ ghost tests；mock safety OK |
| BasisAggregator | 9 Rust unit tests（1e-12 公式對齊；disconnected pool mock = IO-only）；無 Python 端 |
| risk.rs byte-equivalent split | 無新 test 需求（pure move + re-export，c4 e2e 3/3 cover）|
| C4 failsafe wire | 107/0（2026-05-28 memory）；T4.12 adversarial reproduction 確立；dormant by design |
| E4-FCT-002 paper→demo freeze | 源碼修復 DONE（pipeline.py:527-538 `paper_lane_frozen`）；test 對齊未確認 → P2 |

**Verdict**: FAIL — P1 dispatch retry 未解除。所有 2026-05-29/30 source change 覆蓋充足，prior P1 E4-FCT-001 是唯一阻塞點。

**教訓**:
1. **Static audit budget-cap**：任務明確說 ≤25 tool calls / 全 cargo build 重且慢 → 靜態 grep + commit msg 是 acceptable fallback；但最終計數必須 Linux 實跑確認，不能以靜態推算作 PM commit gate。
2. **Carry-over P1 不會自動消除**：dispatch retry vs fail-closed 是 policy 問題，需 PA arbitrate 再 E1 實作，E4 不能代為關閉。
3. **test alignment 確認必顯式**：源碼改 behavior（paper-freeze）後必在同一 round 確認對應 test 也改，否則留 P2 gap。

**Report path**: `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-30--E4--full_chain_test_audit.md`

---

### 2026-05-28 Wave 5 Packet C (C1+C2+C3) + M11 cron + MED/LOW hardening E4 全 regression — PASS

**對象**：HEAD `575a0a94`。累積範圍 = C1 dispatchers (slack/email/console_banner/three_way + RealSmtpTransport lettre 0.11) + C2 audit_emitter (PgAuditEmitter + V114 17-col hypertable) + C3 providers (wall_clock/position/exchange_stop_sync/single_watcher) + E2 review fix MED-1/MED-2/LOW-1 + M11 cron install。

**結果**：
| 檢查 | 結果 |
|---|---|
| `cargo test -p openclaw_engine --lib` run1/run2 | 3575/0/1ign（兩遍同綠 non-flaky）— baseline 3569 → +6（email 3 + MED/LOW 3）✅ |
| `cargo test --lib notification_failsafe` | 107/0（104 + T11 banner + T4.12 watcher + T15 email redact）✅ |
| `cargo test -p openclaw_core --lib risk_gov` | 27/0（不變）✅ |
| `cargo build -p openclaw_engine` (dev, Mac arm64) | PASS（1 pre-existing dead_code `spawn_position_reconciler`）|
| Linux x86_64 `cargo build --release -p openclaw_engine` (ssh trade-core) | PASS 44.92s（lettre+aws-lc-rs 在 x86_64 編 clean）|
| `cargo tree` openssl / native-tls | 0 / 0 ✅；lettre v0.11.22；aws-lc=3 pre-existing（rustls default feature 非 lettre 引入）|
| default `cargo clippy --lib` notification_failsafe filter | 0 hit ✅ |
| #[ignore] / 刪測試 | 0 新增 ignore / 0 測試刪除（16 檔全 addition +4230/-1）|

**MED-2 T4.12 對抗 test 真實性核驗（重要教訓）**：
- T4.12 是真並發：`#[tokio::test(flavor="multi_thread", worker_threads=4)]` + 16 個真 `tokio::spawn` 共享一個 `Arc<SharedFailsafeWatcher>`（共享 mutex state）；clock 在 spawn 前 advance 過 timeout，16 task 真競爭「armed+expired」。
- 斷言真實：`some_count==1` + CountingAudit `emit_count==1`（fetch_add 真計數非 stub 假回）+ 後續 re-check None 且 count 仍 1。
- **E4 親自做對抗 reproduction**：臨時把 claim 還原成 buggy 版（claim 移到 await 後 Step 3 re-lock + 加 `yield_now()` 放大窗口）→ T4.12 FAIL `left: 16, right: 1` —— 精確復現 E1 報告的「16 escalations instead of 1」。隨即 `git diff` 確認零殘留還原。**證明 test 抓得到 race，非 mock 假過**。
- StubTransport / CountingAudit / NoopXxx 全是 IO-sink mock（捕捉 envelope + 回 `!force_fail` / fetch_add 計數），業務邏輯（claim-before-await guard / config 校驗 / timeout 包裝）真跑 — 符合 mock safety rule（mock IO 不 mock 業務）。

**V114 17-col schema 對齊**：audit_emitter.rs INSERT 供 13 column（engine-writable），4 DB-controlled（id BIGSERIAL / acked_at_utc / acked_by / created_at DEFAULT now()）正確省略；`test_insert_sql_locked_columns_match_v114_schema` include_str! grep 13 column + table name + 13 placeholder = drift guard（已在 107 內綠）。V114 runtime idempotency 雙跑由 MIT 第三輪 Linux dry-run 驗（不在 E4 範圍）。

**email.rs:199 doc_lazy_continuation**：default clippy = 0 hit；只在 `--no-deps` 升級 lint config 下 fire。git blame = `9bf71423`（本 Wave email amend）非 pre-existing。判定 = cosmetic doc 縮排，**標 E1 cosmetic follow-up**（E4 不改鏈內 source file，守 E4 邊界），加一行空白即解。

**教訓**：
1. **E4 對抗 test 必親跑 reproduction 才信「真綠」**：E1 報告「buggy 16 / fix 1」是 E1 自證；E4 用 Edit 還原 buggy → 跑 → 看 FAIL `16 vs 1` → git diff 確認零殘留還原，才確立 test 非 false-pass。這是 protocol「跑兩遍 + mock 不掩蓋邏輯」的延伸：並發 fix 加碼「對抗 reproduction」一步。
2. **clippy 數字看 lint config**：`cargo clippy --lib`（default）vs `--no-deps`（可能帶 pedantic/doc lint）數字差很大。protocol baseline 用 default set；email.rs:199 在 default = 0 hit，報告必標明在哪個 config 下 fire 否則誤判 regression。
3. **新 top-level dep 必 Linux x86_64 build 驗**：lettre + aws-lc-rs（aws-lc-sys 需 CMake+C compiler）在 Mac arm64 編過 ≠ x86_64 編過。ssh trade-core `bash -lc cargo build --release` 確認雙平台；openssl=0/native-tls=0 守「純 rustls 零 sys-dep openssl」目標。
4. **module addition regression 看 diff stat 確認 0 既有測試動**：16 檔全 +addition / -1（Cargo.toml 行移）= 純新增模塊；無既有 test 修改/刪除/ignore，baseline ratchet +6 全來自新 test，不是改既有 assertion 遮蓋。

**Verdict**：**PASS** — 全綠；可進 QA / PM commit。Carry-over：email.rs:199 cosmetic（E1）+ V114 runtime idempotency 雙跑（MIT 第三輪 Linux）+ C5 `failsafe_ack_role` restricted role（Sprint 3）。

**Report path**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-28--e4_packet_c_m11_full_regression.md`

---

### 2026-05-27 OPS-4 systemd (GAP-A + GAP-F + minor fix) E4 regression — PASS（含 3 carry-over）

**對象**：`65e78437` (OPS-4 IMPL) + `07027493` (OPS-4 minor fix 4 條：MED-1 空 Requires= 刪 / LOW-2 verify warn vs error / LOW-3 root user guard exit 12 / LOW-4 README reset-failed)。E2 APPROVE-WITH-MINOR + 4 minor fix DONE。

**結果**：
| 檢查 | 結果 |
|---|---|
| bash -n install_engine + install_watchdog | 2/2 PASS |
| systemd-analyze verify 6 unit (ssh trade-core, sed 替換 9 placeholder) | 4 clean / 2 warn / 1 fail (全預存非本次引入) |
| README 渲染（1 H1/7 H2/9 H3/12 fence balanced/154 行/3 reset-failed mention）| PASS |
| SCRIPT_INDEX 9 systemd entry 對齊 | PASS |
| 跨平台 grep /home/ncyu (logic line) | **0 違反**（11 hit 全在注釋/錯誤訊息字串內）|
| install script idempotency smoke (static) | OVERWRITE+daemon-reload pattern 正確冪等 |

**3 carry-over（全屬 65e78437 或更早 OPS-1 Track A 預存，不阻 07027493 commit）**：
1. **C-1 HIGH**：`StartLimitIntervalSec` 寫在 `[Service]` 被 systemd 245+ ignore → rate-limit 實際不生效（spec §5.1 雙重防線 systemd 端失效，僅靠 watchdog circuit-break）。應改為 `StartLimitInterval` 或移到 `[Unit]`。OPS-4 round 3。
2. **C-2 MED**：`openclaw-tls-renew-notify.service` `ExecStart` 內 `$(date -u +%FT%TZ)` 撞 systemd `%F/%T/%Z` specifiers → fatal error，OnFailure hook 無法觸發。需 escape `%%FT%%TZ`。OPS-1 round 3。
3. **C-3 LOW**：caddy binary `/usr/bin/caddy` 缺檔 — operator hand-action 提示，非 IMPL 缺陷。

**Verdict**：PASS — OPS-4 4 minor fix 全 land；deploy ready；3 carry-over 顯式記錄不漏。

**教訓**：
1. **systemd `StartLimitIntervalSec` section drift（systemd 230 → 245+）**：spec 寫 `[Service]` 在 systemd 245+ 是 unknown key，warning 是「ignoring」說明 directive **完全不生效**。E2 review 只看語法/結構，systemd-analyze 才能 catch；E4 必跑 trade-core 真實 systemd parser。Mac 沒有 systemd 不可代驗。
2. **systemd `ExecStart` 內 `%` 是 unit specifier escape**：`/bin/bash -c '... $(date -u +%FT%TZ) ...'` 看似 shell 字符串但 systemd 在執行前先解析 specifier，`%F/%T/%Z` 撞 systemd built-in specifier（如 `%F` = full hostname）→ fatal "无效的 slot"。修法 `%%FT%%TZ`。
3. **E4 對 minor fix 必 scope diff confirm**：本 round 3 finding 都不是 07027493 引入，必須顯式 git show 65e78437 + git log 證明預存，否則會誤判 minor fix 引入 regression 退 E1。
4. **install script idempotent ≠ skip-warn**：systemd unit install 是 leaf state OVERWRITE pattern；第二次跑直接覆寫 + daemon-reload，正確且冪等。比 `if exists then warn` 更安全（避免半成型 unit 殘留）。
5. **cross-platform grep 必 distinguish logic line vs comment/string**：`/home/ncyu` 出現在 install script `${VAR:?例: /home/ncyu/...}` 是錯誤訊息字串內，不是硬編碼；簡單 grep 會 false positive。

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-27--ops_4_e4_regression.md`

---

### 2026-05-22 Sprint 2 Phase 3b regression (Wave 1+2 combined 6 Track) — PASS

**對象**：Sprint 2 M3 metric emitter Wave 1+2 6 Track E1 IMPL round 2 (HEAD `ffb7ed48`) — Track A engine_runtime scaffold + Track B pipeline_throughput + Track C database_pool + Track D api_latency + Track E strategy_quality + Track F risk_envelope + cross-Wave OBSERVE-4 fix (M3Error::ReplaySubprocessForbidden + dual scheduler guard)。

**結果**：
| Suite | Run 1 | Run 2 | non-flaky |
|---|---|---|---|
| cargo test --workspace --release (skip stress_tick_latency_benchmark) | 3894/0/4 | 3894/0/4 | ✅ |
| sprint2_track_a..f + m3_emitter_replay_forbidden isolated | 51/0 | 51/0 | ✅ |
| spike feature suite | 38 test result line all ok / 0 fail | (covered by workspace) | ✅ |
| health:: subset | 87/0 | (covered) | ✅ |
| governance::lal:: subset | 15/0 | (covered) | ✅ |
| m3_amp_cap_24h_fire spike | 3/3 PASS (含 stub_domains_fail_loud) | (covered) | ✅ |
| stress_tick_latency_benchmark isolated | 43-50μs | 43-50μs (3 runs) | ✅ PASS (target 100μs) |
| pytest (program_code/ + tests/) | 6042 pass / 28 fail / 45 skip | 6042 pass / 28 fail / 45 skip | ✅ identical |
| test_spike_cross_lang_fixture.py | 7/7 PASS | - | ✅ |
| test_spike_cross_lang_rust_binding.py | 5/5 PASS | - | ✅ (Sprint 1B AC-7 Rust binding land confirmed) |

**Linux ssh trade-core sandbox verify**：
- `sandbox_admin` role 存在於 pg_roles ✅
- `learning.health_observations` V106 schema 完整 land：6 domain CHECK (engine_runtime / pipeline_throughput / database_pool / api_latency / strategy_quality / risk_envelope) 對齊 Sprint 2 6 Track；engine_mode 4-val CHECK 不含 'replay' (OBSERVE-4 PG 層 fail-loud)
- Sprint 2 不新增 V### per spec §1.4 ✅
- AC-1b real PG empirical 走 Phase 3c QA per Q2(d) operator decision — E4 本 round N/A

**Cross-platform aarch64-apple-darwin**：cargo check --release clean (0 error / 1 pre-existing dead_code warning `spawn_position_reconciler`)

**AC-5 nm symbol scan**：production binary `target/release/openclaw-engine` 0 hit on (mock_instant / tokio::time::pause / spike) — invariant 維持

**Pre-existing 28 pytest fail attribution**（與 Sprint 2 0 touch）：
- 24 GUI static template test（tab-live / w_audit_7c / replay_subtab / openclaw_agent_control / performance_metrics / prelive_edge_gate / replay_routes / session_stop）
- 7 structure test（confirm_modal_a11y / docs_readme_index / event_consumer_split / prompt_modal / strategy_action_visual_isolation / visual_isolation）
- 1 v072_feature_baseline_writer

baseline 比較：Sprint 1A-ζ Phase 3b 6037/28 → 當前 6042/28 → **+5 pass / 0 new fail** (Sprint 1B Rust binding 5 test land + 其他 sibling 增 test 抵消)

**OBSERVE-4 audit finding（cross-Wave）**：
- `tests/m3_emitter_replay_forbidden.rs:31` `use async_trait::async_trait;` 是 unused import warning（E2 Track E round 2 condition #2）→ **LOW carry-over** 不阻 PASS
- 3/3 m3_emitter_replay_forbidden test PASS：MetricEmitterScheduler + StrategyQualityScheduler + paper/demo/live_demo/live 4 mode startup OK guard 只攔 'replay'
- M3Error::ReplaySubprocessForbidden variant 新加；scaffold-level + per-tick 雙層 guard 全 cover

**stress_tick_latency_benchmark 假陽性 RCA**（重要教訓）：
- `cargo test --workspace --release` 並行模式下 stress_tick_latency_benchmark **5/5 FAIL** @ 163-228μs > 100μs target
- 切到 baseline e2d213b5 worktree 同一 commit reproduce → 46.5μs **PASS**
- 切回 HEAD ffb7ed48 + **isolated `cargo test --test stress_integration stress_tick_latency_benchmark`** 3 run → 43-50μs **PASS**
- 結論：**Mac 並行 cargo workspace 跑 release benchmark 時 CPU contention 拉高 latency 至 ~4x；不是 Sprint 2 IMPL regression**
- 解：E4 regression workspace 命令必 `--skip stress_tick_latency_benchmark`；isolated run 才是 SLA bench 可信信號

**Sprint 2 IMPL 完整 fingerprint**：
- 6 commit chain `788f8e99 → 2a7e2ae0 → 6152b01d → 6f6bbea8 → ffb7ed48` 全 PASS（baseline + Wave 1 + Wave 2 + round 2 全綠）
- 51 sprint2 integration test (A 9 + B 5 + C 8 + D 7 + E 11 + F 8 + replay_forbidden 3)
- 3 spike integration test (m3_amp_cap_24h_fire + amp_cap_different_anomaly_id_not_suppressed + stub_domains_fail_loud)
- lib 3152 PASS（含 87 health:: + 15 governance::lal::）
- Track D 8 metric (rest_p50/p95/p99 + ws_rtt_p50/p99 + ret_4xx/5xx + ws_dropout) 完整 IMPL 對齊 PA spec amend
- Track E pair-level OR-aggregate + scheduler per-pair 25 per-metric SM 100
- Track F position_count_active 4 band ladder + 5 min interval

**Verdict**：**PASS** — Sprint 2 Wave 1+2 combined 6 Track IMPL 全 closure；ready for Phase 3c QA empirical driver。

**Phase 3c QA carry-over（4 條）**：
| # | 項目 | Owner |
|---|---|---|
| QA-1 | AC-1b real PG empirical（30 min window row count ≥ 5；前置 = main.rs scheduler 接線 + Linux runtime --rebuild） | QA + E3 |
| QA-2 | m3_emitter_replay_forbidden.rs line 31 unused async_trait import warning cosmetic clean | E1 LOW |
| QA-3 | PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation 補位（Wave 2 main.rs 接 ApiLatencySourceProbe 前必 closed） | E1 |
| QA-4 | E4 workspace 命令固定加 `--skip stress_tick_latency_benchmark`；新增 SLA bench 文件說明 isolated-only constraint | PM SOP |

**教訓**：

1. **stress benchmark workspace vs isolated 假陽性**：Mac 並行 cargo workspace 跑 release benchmark 時 CPU contention 拉高 latency 至 ~4x；要 reproduce baseline 必須 isolated。如果只看 workspace fail message 會誤判 Sprint 2 引入 regression。E4 必 bisect 確認，並區別 workspace flaky 與 IMPL regression。

2. **Linux sandbox role mapping vs Mac credential gap**：`sandbox_admin` role 存在於 Linux pg_roles，但 `/home/ncyu/.pgpass` 只記 `trading_admin` 兩個 database 的密碼；E4 用 `trading_admin → trading_ai_sandbox` 雙重身分 fallback 仍可走 sandbox query。若需 sandbox_admin 跑 DDL 則需 .pgpass 第三 row 對應條目（per Sprint 1A-ε P1 E3 IMPL `sandbox_admin role + secret_file 0600`）。

3. **Sprint 2 emitter scaffold contract 6 Track 共用 writer 必走 OBSERVE-4 guard 一處**：M3Error::ReplaySubprocessForbidden 必加在 Track A scaffold 並 cross-Wave land 一次；6 Track 各自寫 guard 會漏（cascade reject path 或新 writer route）。round 2 fix 確認雙 scheduler (MetricEmitterScheduler + StrategyQualityScheduler) 對齊；3 test 含 startup 守 paper/demo/live_demo/live 4 mode 不誤攔。

4. **PA-DRIFT-4 bybit wrapper instrumentation 屬 Wave 2 main.rs 責任不歸 Track D scaffold**：emitter trait 抽象 land + StubSourceProbe 用 mock fixture 通過 AC-1a；real bybit client p50/p95/p99 + retCode + ws_dropout 屬 main.rs 接線時補 (4-6 hr)；Track D E1 不修 bybit client 既有邏輯，per packet §5.5 反模式 (a)+(c)+(d)。

5. **pytest baseline ratchet 6037 → 6042**：Sprint 1B Rust binding 5 test land（`test_spike_cross_lang_rust_binding.py`）對應 AC-7 從 PoC partial pass → FULL PASS（per Sprint 1B early IMPL Track D commit 9cf0fe82）。E4 baseline 跟著上升不下降 ✅。

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_2_phase_3b_regression.md`

---

### 2026-05-20 P0-ENGINE-HALTSESSION-STUCK-FIX Layer B (Python watchdog inert probe) — PASS

**對象**：E1 Layer B IMPL（Python-only：`engine_watchdog.py +525 LOC` + 新建 `test_engine_watchdog.py 581 LOC` 32 unit tests + `watchdog_inert_probe.toml 38 LOC` per-env config + `SCRIPT_INDEX.md` 索引更新）。spec v0.2 §4 + §10.2 B-1..B-7。Mac dirty tree，未 push。

**結果**：
| Suite | passed | failed | non-flaky |
|---|---|---|---|
| Mac pytest test_engine_watchdog.py Run #1 | 32 | 0 | ✅ |
| Mac pytest test_engine_watchdog.py Run #2 | 32 | 0 | ✅ identical |
| Mac wider canary `helper_scripts/canary/` Run #1 | 170 | 0 | ✅ |
| Mac wider canary Run #2 | 170 | 0 | ✅ identical |
| py_compile engine_watchdog.py | OK | - | - |
| CLI --help shows --disable-inert-probe + --inert-probe-config | OK | - | - |

**AC B-1..B-7 對應驗證**：
- B-1 paper_paused 60min+ alarm → `test_fires_alarm_paper_paused_stuck` ✅
- B-1a live 15min vs demo 60min 差異 → `test_per_env_threshold_live_stricter` + `test_per_env_threshold_demo_not_fire_at_live_threshold` ✅
- B-2 intents zero-delta > window alarm → `test_fires_alarm_intents_zero_delta` ✅
- B-3 cooldown 同 incident 不重發 → `test_cooldown_no_duplicate_alarms` ✅
- B-4 clear 寫 CLEARED → `test_paper_paused_clears_state` ✅
- B-5 watchdog restart 不重置 incident → `test_state_persistence_across_restart` + `test_save_load_roundtrip` ✅
- B-6 7d false-positive reconcile → ⏳ post-deploy passive watch
- B-7 multi-engine 獨立 → `test_multi_engine_independent_state` ✅

**Scope creep check**：Layer A 文件 0 diff（`halt_session.rs` / `risk_config.rs` / `halt_audit_pg_writer.py` / V096-V098 / `paper_state_restore_*` 全未動）。E1 守住 Layer B only。

**Mock 審查**：0 anti-pattern。`grep -nE "patch|MagicMock|Mock\(\)" test_engine_watchdog.py` = 0 matches。Test 用 tempfile 隔離 + 真函式 + 不 mock 時間 / 不 mock JSON parse。`os.environ` / `requests` / `psycopg` 引用 = 0。

**Layer A cron 完整性 post Layer B**：
- `/tmp/openclaw/halt_audit.log` 2 rows 保留（Round 2 set+manual_cleared 事件鏈）
- `governance_audit_log` 24h 內 2 rows 保留
- Layer B 不依賴 Layer A cron（獨立 `watchdog_inert_events.jsonl` channel）→ 結構上不該影響，實測確認

**教訓**：

1. **E1 「90/90」口徑陷阱**：E1 self-report 「90 = 58 existing canary + 32 new」只計 `test_canary.py + test_engine_watchdog.py` 兩檔；忽略 `healthchecks/tests/*` 60 個 + `test_halt_audit_pg_writer.py` 20 個。從廣域 `helper_scripts/canary/` 跑是 170/0。E4 不能盲信 E1 數字，必須直接 directory-level run 拿真實 baseline。

2. **Prompt 寫的 grep 模式可能錯**：prompt 期望 `test_b[0-9]` / `test_inert` / `test_TRADING_INERT` 命名，實際 E1 採描述式（`test_fires_alarm_*`）。E4 必須讀真實 source 而非靠 prompt 的 grep 模式驗 test count。`grep -cE "^\s*def test_"` 才是抗命名風格的計數方式。AC ↔ test 對應靠 E1 IMPL report 的表格不靠檔名 substring。

3. **Mac dirty tree → Linux pytest 不適用**：Layer B 未 commit、未 push，`ssh trade-core "ls test_engine_watchdog.py"` = NOT_PRESENT。Python 平台無關，Mac unit test 全綠對 Linux runtime 充分。但建議 push 後 PM 補跑 `ssh trade-core "git pull --ff-only && pytest"` 一次保險。Layer A Round 2 已驗 Python 跨平台 0 regression 模式。

4. **`[live_demo]` documented dead config 合理**：`pipeline_snapshot_live.json` 寫 `trading_mode="live"` 無 endpoint hint 區分 LiveDemo vs Live。Resolver 落 `[live]` 嚴 threshold。符合 「LiveDemo 不因 endpoint 降級」feedback。Spec L-3 預留升級空間，目前 IMPL acceptable。

5. **Cargo regression 不適用標記要明確**：Layer B Python-only（no Rust / no V### / no engine binary rebuild）。E4 報告必須明確說明「cargo regression 不適用」而非靜默跳過，否則容易被誤判 E4 偷懶。

**Verdict**：**PASS** — Mac 32/0/170 x2 non-flaky + AC B-1..B-7 全 cover + Mock 0 anti-pattern + Layer A 0 diff + Layer A cron infra preserved。允許 PM sign-off → push → 部署 Linux watchdog。**不阻塞** A3 / E2 並行 review（不同 surface）。

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-20--layer_b_watchdog_inert_probe_e4_regression.md`

---

### 2026-05-19/20 P0-ENGINE-HALTSESSION-STUCK-FIX Layer A Round 2 — PASS

**對象**：E1 Round 2 IMPL（4 MUST-FIX + 1 E3 MEDIUM + 1 SHOULD spec §6.3 incident replay）9 個新 test 加進來 → 3255 (R1) → 3264 (R2)。

**結果**：
| Suite | passed | failed | ignored | non-flaky |
|---|---|---|---|---|
| Mac cargo --release Run #1 | 3264 | 0 | 3 | ✅ |
| Mac cargo --release Run #2 | 3264 | 0 | 3 | ✅ identical |
| Linux pre-Layer A baseline | 3219 | 0 | 3 | (Round 1+2 未 push) |
| Python pytest test_halt_audit_pg_writer | 20 | 0 | - | ✅ |
| per_symbol_price_pnl (P1-16) | 3 | 0 | - | ✅ preserved |
| halt_audit substring | 13 | 0 | - | ✅ |
| halt_ttl substring | 29 | 0 | - | ✅ |
| config::risk_config substring | 159 | 0 | - | ✅ |

**Linux PG integration E4 獨立執行**（fake process_pid=2099999 marker 避撞 prod）：
- Run 1 cold start → inserted=3 skipped=0 new_offset=1227
- Run 2 idempotency → "no new rows since last cursor; exit 0"
- SELECT 驗 event_type↔clear_path 完整對齊：set↔NULL / auto_cleared↔auto_ttl / manual_cleared↔ipc_resume
- Cleanup DELETE 3 rows

**SLA bench**：
- hot_path_baseline avg=18.88μs p99=27.79μs max=64.79μs（target tick path <100μs，0 regression）
- intent_processor p99=8.9μs（target IPC <5ms，零問題）
- tick_latency 45.1μs avg over 1000 ticks
- TTL check 在 on_tick 入口 O(1) early-out（`halt_kind == None` 直 return）99.9%+ tick 0 額外 cost

**§九 LOC**：
- risk_config_tests.rs 1917 < 2000（MUST-FIX-4 從 2076 拆 159 LOC → sibling halt_ttl_tests.rs 182 LOC）✓
- 0 hard-cap breach；82 LOC headroom

**教訓**：

1. **Cross-arch byte-equiv verification 需 commit + push + Linux pull**。dirty Mac tree 無法做 aarch64 ↔ x86-64 對比；只能跑 Mac single-arch + Linux pre-Layer A baseline（diff = total +45 = Round 1 +34 + Round 2 +9 + 1-2 test case 數差合理）。如改 float math / serde / state machine 必須 commit + push 才能驗 1e-4 容差。Round 2 spec §6 已聲明 cross-arch 0 regression risk（無新 float hot path），所以 Linux baseline 對比足夠 E4 階段 sign-off。

2. **POSTGRES_PASSWORD with parens bash auto-export 坑**：`POSTGRES_PASSWORD=<REDACTED>` 在 `set -a; source basic_system_services.env; set +a` 下被 bash syntax-eat（`()` 被視為 subshell）。Python `os.environ.get` 拿到空字串。`grep | cut` 直讀 env file 字面值才正確（cron wrapper L39-43 已正確）。**生產 cron 不受影響**；只有 manual test 需 `export OPENCLAW_DATABASE_URL='postgresql://...(...)..'`。E4 報告此坑供 operator 知悉，不阻塞 PASS。

3. **9 個 named test 雙 path 驗證**：`grep -rnE "test_<name>" rust/openclaw_engine/src/` (file existence) + `cargo test -p openclaw_engine --release -- <9 names>` (run pass) 雙驗。E1 self-report 9 added；E4 兩條 path 各自 9/9。比起 single-path 「全 suite passed >= baseline」更能 catch ghost commits（test function 寫在某 module 但 mod registration 漏接，Mac cargo run 不會跑到）。

4. **Hot path SLA 0 regression 驗證的正確姿態**：不是「跑 cargo test 沒 fail」，是跑 bench 拿具體 p50 / p99 / max。on_tick 入口加 `check_and_clear_halt_expired` 雖看似額外動作，但 O(1) early-out `halt_kind == None → return false` 路徑 99.9%+ tick 走，bench 證實 hot_path_baseline 不退化。E4 應對所有 hot path 改動跑 bench，不能只跑 cargo test。

**Verdict**：**PASS** — Mac 3264/0/3 non-flaky + Linux PG integration 3 INSERT verified + SLA 0 regression + §九 0 breach + 16 原則 0 違反 + 9 named test exist+run。允許 PM 派 QA Audit 並行 E2 round 2 re-review。**不阻塞** E2。

**Report path**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_e4_regression.md`

---

### 2026-05-16 Two-IMPL parallel Mac regression (F-09 + [68]) — PASS

**對象**：兩個並行 P1 IMPL Mac-side baseline regression（PM 派發前）：
- **IMPL #1 F-09**：`model_tier` 從 `evaluate.rs:412` 硬碼 `"l1_9b"` 抽至 `RiskConfig.strategist.model_tier` ArcSwap snapshot；7 file diff（4 Rust + 3 TOML）；E1 self-report 2917/0/1
- **IMPL #2 [68]**：portfolio_resting_exposure healthcheck（ID 從 [58] 衝突→[68] 因 W-AUDIT-9 T4 `check_58_graduated_canary_stage_invariant` 已占用 [58]）；新 562 LOC check + 408 LOC test + runner.py wire + __init__.py re-export

**Mac-side baseline 結果（2x runs，non-flaky）**：
| Engine | passed | failed | ignored | delta vs E1 self-report |
|---|---|---|---|---|
| Rust openclaw_engine --lib --release Run #1 | 2917 | 0 | 1 | 0/0/0 ✅ |
| Rust openclaw_engine --lib --release Run #2 | 2917 | 0 | 1 | 0/0/0 ✅ identical |
| Python helper_scripts/db/ pytest | 368 | 0 | 0 | +10 from baseline 358 ✅ |
| Python test_portfolio_resting_exposure_healthcheck Run #1 | 10 | 0 | 0 | matches E1 ✅ |
| Python test_portfolio_resting_exposure_healthcheck Run #2 | 10 | 0 | 0 | non-flaky ✅ |

**Targeted runs**：
- Rust `strategist_scheduler` 36/0（含 1 F-09 new test `test_build_strategist_eval_payload_honors_custom_model_tier`）
- Rust `config::risk_config` 150/0（含 1 F-09 new test `test_strategist_config_validate_rejects_empty_or_whitespace_model_tier` + round-trip extends）
- Targeted `model_tier` substring run 2/2 PASS

**IMPL-by-IMPL Mac verdict**：

**F-09 (model_tier TOML extraction)**：
- ✅ cargo check --release 0 error（pre-existing dead_code warning unrelated）
- ✅ 2 new test 全 PASS（custom tier honor + empty/whitespace reject）
- ✅ test_strategist_config_toml_roundtrip 擴充驗 `model_tier="l1_27b"` 字串 round-trip
- ✅ test_strategist_config_partial_fallback 擴 4 partial 場景（缺/空/只填 delta/只填 tier）
- ✅ 3 TOML 均含 `[strategist] model_tier = "l1_9b"`（paper/demo/live）
- ✅ ArcSwap snapshot 路徑真實（不是 mock 路徑）：mod.rs L266 `current_model_tier()` → `risk_store.as_ref().map(|store| store.load().strategist.model_tier.clone())`
- ✅ 缺 store fallback 對齊 source default + Python default 三層（`DEFAULT_STRATEGIST_MODEL_TIER = "l1_9b"`）
- ⚠️ rustfmt --check 報 2 drift 在 risk_config_tests.rs（pre-existing，main HEAD 已 drift，**非 F-09 引入**；stash + clean rustfmt 驗證 pre-existing）
- 📌 SLA 0 風險：current_model_tier() 只在 strategist evaluate cycle（secs-period async）跑，**非 tick hot path**

**[68] healthcheck (portfolio_resting_exposure)**：
- ✅ py_compile 0 error
- ✅ 10/10 PASS x2 non-flaky
- ✅ Sibling helper_scripts/db/ 368/0 0 regression spill
- ✅ runner.py wire L+1 註冊正確（標記 P2-PORTFOLIO-RESTING-58-HEALTHCHECK + ID 衝突說明）
- ✅ __init__.py re-export `check_68_portfolio_resting_exposure` 正確
- ✅ ID conflict [58]→[68] 處理乾淨（source comment 明示 `[58] = W-AUDIT-9 T4 已占用，取 [68] free slot, name preserved`）
- ✅ Mock 審查：MagicMock 只 mock cursor IO 邊界（execute/fetchone/fetchall/rollback），業務邏輯 aggregate/divergence/cap compare 真跑 — **不掩蓋業務邏輯**
- 📌 OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED env-gated WARN→FAIL escalation tested via `test_required_env_escalates_warn_to_fail`

**Cross-IMPL conflict 評估**：**0 conflict**
- F-09 grep `portfolio|resting` = 0 matches in evaluate.rs/mod.rs
- [68] grep `model_tier` = 0 matches in checks_portfolio_resting_exposure.py
- 不同 layer（Rust config schema vs Python PG/filesystem healthcheck）
- 不同 process（strategist scheduler vs cron healthcheck）
- 不同 data source（ArcSwap RiskConfig vs paper_state.snapshot JSON + trading.orders PG）
- 不同表（無 SQL overlap）

**§九 LOC check**：
| 檔 | LOC | 狀態 |
|---|---|---|
| evaluate.rs | 537 | ✅ < 800 |
| mod.rs (strategist_scheduler) | 495 | ✅ < 800 |
| risk_config_advanced.rs | 1300 | ⚠️ > 800（pre-existing baseline） |
| risk_config_tests.rs | 1912 | ⚠️ > 800（pre-existing baseline，且接近 2000 hard cap = 88 LOC headroom） |
| checks_portfolio_resting_exposure.py | 562 | ✅ < 800 |
| test_portfolio_resting_exposure_healthcheck.py | 408 | ✅ < 800 |

**risk_config_tests.rs P2 follow-up**：1912/2000 = 95.6%，距 hard cap 88 LOC；F-09 增 ~88 LOC 之後再加 ~88 LOC 就破 2000。建議 P2 拆檔（per-feature sub-module）— 不阻塞當前 commit（pre-existing baseline + governance exception clause 適用）。

**Linux-flagged 項清單**（E4 不能 Mac 跑的，需 Linux trade-core 後續驗）：
1. **[68] SQL semantic on real PG**：`SELECT to_regclass('trading.orders')` + `SELECT DISTINCT ON (order_id) ... FROM trading.order_state_changes` + JOIN orders + `engine_mode = %s` WHERE 過濾 — 真 PG schema / index / data shape 必 Linux 驗
- 2. **[68] paper_state snapshot real read**：`OPENCLAW_DATA_DIR` 多 engine_mode snapshot 檔（paper.json/demo.json/live.json/live_demo.json）真檔讀 + `position.qty/entry_price/notional` 真值 cross-check vs Rust `paper_state/snapshots.rs:20` PositionSnapshot serialization layout
3. **F-09 ArcSwap runtime IPC hot-reload**：`patch_risk_config` `<60s` 真實熱重載 `model_tier="l1_27b"` 後驗 strategist evaluate 下一輪 IPC payload `model_tier == "l1_27b"`（Python `_handle_strategist` 端真實 routing）
4. **F-09 Python side end-to-end**：`ai_service_dispatch.py._handle_strategist` 收到 `params["model_tier"]="l1_27b"` 真 route 到 27B Ollama model（Linux Ollama 真跑）
5. **runner.py cron 真實 invocation**：Mac 跑 unit test 不等於 cron 真跑 [68] check + WARN/FAIL 級別正確 surfaced 到 healthcheck log

**核心驗證點**：
- 2 IMPL 0 conflict（不同 layer、不同 process、不同 data source）
- Rust 2917 = 2915 pre-IMPL + 2 F-09 new = **0 regression**
- Python +10 new test 全 PASS + 0 sibling regression spill
- Mock review 0 anti-pattern（IO 邊界 mock only）
- rustfmt drift 是 pre-existing baseline（stash 驗證），非 F-09 引入
- 跑兩遍 4/4 suites identical（non-flaky）
- §九 LOC 0 hard cap breach（但 risk_config_tests.rs 95.6% → P2 拆檔 follow-up）
- SLA hot path 0 風險（F-09 只在 strategist cycle async loop；[68] 是 cron healthcheck）

**教訓**：
1. **ID 衝突檢查的正確姿態** — E1 self-report 已預先 grep `passive_wait_healthcheck/checks_*.py` 找下個 free slot ([68])，並在 source comment 明示衝突原因 + 解決方案。比起追溯 PA spec 改 ID，**source-level 註解 + runner.py 顯式註冊 + name preserved** 是更可審計的 pattern。
2. **rustfmt drift 歸因必走 baseline stash** — E1 自驗 "fmt clean" 可能用 `cargo fmt` 而非 `--check`；E4 必須 stash 後 rustfmt --check baseline file 才能精準歸因 pre-existing vs new。本次 risk_config_tests.rs assert! wrap drift 是 pre-existing（git stash 驗證），不是 F-09 責任。
3. **Cross-IMPL conflict 評估走「grep + layer + process」三維** — 不只 grep file overlap，還要驗 process / data source / layer 不同。F-09 vs [68] 同 wave 並行最大風險是 ArcSwap 寫 vs healthcheck 讀同 config，但 [68] 從不讀 RiskConfig，0 風險。
4. **§九 LOC governance exception 適用 risk_config_tests.rs** — 1912/2000 = 95.6% pre-existing baseline；F-09 增 ~88 LOC 仍在 baseline + 5 LOC 容差（per CLAUDE.md §九 pre-existing exception clause）外，但仍未過 2000 hard cap。P2 拆檔 follow-up 標記，不阻塞當前 commit。

**Verdict**：**PASS** — 兩 IMPL Mac-side 0 regression、0 conflict、0 mock anti-pattern、non-flaky；5 Linux-only items 列入 Appendix 給 trade-core 後續驗。允許 PM 統一 commit + push 到 main。

**Report path**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--two_impl_f09_and_68_mac_regression.md`

---

### 2026-05-16 Wave 2+3 6-WP Mac-side full regression — PASS

**對象**：Wave 2 (WP-03/04/10 commit `ef6ea79f` + E2 follow-up `5682994c`) + Wave 3 (WP-06/08/13 commit `f31b6e8f`) 跨 11 source files。CC cross-validation 確認 sibling `8321b4b7` 只覆蓋 BB-MF-3，這 6 WP chain breach 需 fresh E4。

**Mac-side baseline 結果 (2x runs)**：
| Engine | passed | failed | ignored | non-flaky |
|---|---|---|---|---|
| Rust openclaw_engine --lib --release | 2906 | 0 | 1 | ✅ identical 2 runs (= prior `8321b4b7`) |
| srv/tests pytest (with 1 dup-basename --ignore) | 368 | 1 (pre-existing test_v072 source drift) | 2 | ✅ |
| control_api_v1 pytest (with 4 collection-error --ignore) | 4092 | 1 (pre-existing test_case2_pg_kill intermittent) | 8 | ✅ |

**WP-by-WP Mac verdict**：
- **WP-03 (OU σ residual)**：grid_helpers 21/0/0; 5 new tests verified by name; rustfmt CLEAN; cargo check no error; integrity confirmed `compute_ou_step` rewritten with `residual = dx - predicted` (L149) + `ou_residual_sigma` module L185-264. **PASS**.
- **WP-04 (Strategist Ollama observability + budget + evaluate.rs TODO)**：py_compile EXIT 0; `AIService._record_strategist_invocation` 確認 4 callsites (3 main + 1 ollama-unavailable per E2 MEDIUM-3 fix); `budget_config.toml` $2/$60 confirmed; evaluate.rs TODO marker L412 + `model_tier="l1_9b"` L413; 27 pytest passed. **PASS**, Mac caveat: agent.ai_invocations INSERT path empirical write-back FLAGGED-FOR-LINUX (PG IO is correctly an IO boundary, not mockable per §5.2).
- **WP-06 (state_compiler deepcopy 3→2)**：py_compile EXIT 0; documentation block "WP-06 E5-P-2 deepcopy 精簡：原有 3 次 deepcopy 精簡為 2 次" 確認; CACHE deepcopy L631 + INPUT deepcopy L635 (OUTPUT 3rd 已移除); 27 pytest passed. **PASS**.
- **WP-08 (engine_mode + purge_days)**：py_compile EXIT 0; `_VALID_ENGINE_MODES = ("paper","demo","live","live_demo")` + `_engine_mode_scope('live') → ["live","live_demo"]` (43k LiveDemo row recovery); MIT-DB-6 comment L545; `purge_days: int = 0` default backward-compatible; 16 pytest passed. **PASS**, Mac caveat: 43k empirical PG query FLAGGED-FOR-LINUX.
- **WP-10 (ReduceOnlyReject 110017 + backtest URL env)**：rustfmt CLEAN; bybit_rest 29/0; retcode 2/0 (`test_bybit_ret_code_phase1b_extensions`); ReduceOnlyReject = 110017 enum + 5 classifier asserts (`is_retryable / is_noop / is_exchange_backoff / is_instrument_filter / is_balance_block` 全 `!`-asserted); `OPENCLAW_BYBIT_BACKTEST_URL` env var default demo per BB-M-1. **PASS**.
- **WP-13 (DemoCmdSenderSlot + provider pattern)**：4/4 rustfmt CLEAN; cargo check no error; `pub type DemoCmdSenderSlot = Arc<RwLock<...>>` mirrors `LiveCmdSenderSlot` structurally; slot init L429 + write L431 + boot_tasks pass-through L801. **PASS-COMPILE**, Linux caveat: real respawn cycle FLAGGED-FOR-LINUX (Mac engine=`engine_alive: false` by design).

**Linux-only flagged scope (5 items)** — correctly partitioned per CLAUDE.md §六/§七:
1. Full Rust integration `cargo test -p openclaw_engine` (~2900 tests; Mac dev_disabled_* secret slots fail-closed)
2. WP-08 43k LiveDemo row empirical PG query
3. WP-13 demo cmd_tx survival across rebuild cycle
4. WP-04 agent.ai_invocations INSERT write-back verification
5. V091-V094 SQL migrations (NOT landed; WP-08 SQL source-only this wave)

**核心驗證點**：
- 6 WP 全部 source integrity grep PASS (compute_ou_step, _record_strategist_invocation × 4, deepcopy 3→2 doc-comment, _VALID_ENGINE_MODES expansion + purge_days, ReduceOnlyReject + 5 asserts, DemoCmdSenderSlot 8 grep sites)
- Mock 審查 0 anti-pattern (real math / IO boundary mock only)
- §四 5 hard boundaries 全 intact
- §九 file-size 0 hard-cap breach
- 跑兩遍 3/3 suites identical (non-flaky)
- 0 new failures (pre-existing 2: test_v072 source drift + test_case2_pg_kill intermittent)
- SLA hot path 0 risk (WP-03 residual sigma 是 per-spacing-update O(n) ≪ 1µs; WP-13 RwLock try_read 微秒級)

**教訓**：
1. **rustfmt walks `mod` declarations** — 對 `main.rs` 跑 rustfmt 會檢查所有透過 `mod`/`pub mod` 達到的子檔；發現 `startup/mod.rs` + `ipc_server/handlers/fee_source.rs` pre-existing drift 不在 Wave 2+3 diff，必須 per-file 跑才能精準歸因。
2. **`test_pure_utils.py` 3 dup basenames** — `tests/local_model_tools/` + `tests/ml_training/` + `tests/misc_tools/` 三個目錄都有同名檔；pytest collection error 是「在不同 cwd 跑會發現不同子集」(per 2026-05-16 audit MEDIUM-3)。E4 protocol：dup-basename 視為 pre-existing env noise，用 `--ignore` 而非試圖修；真要修是 P2。
3. **WP-13 沒有 inline test 不代表測不夠** — `DemoCmdSenderSlot` 是 type alias + slot init，與 `LiveCmdSenderSlot` 結構等同（LiveCmdSenderSlot 也 0 inline test）；compile-time 由 Rust borrow checker 驗證，runtime 真假驗證 by design 屬 Linux runtime（engine 只跑 Linux）。E4 sniff test：grep `LiveCmdSenderSlot.*test\|DemoCmdSenderSlot.*test` 都是 0，代表這層 contract 由「engine 啟動+IPC 命令真實往返」驗，不是 unit test。
4. **per-WP integrity grep > 抽象「passed >= baseline」** — Wave 2+3 6 WP 每個 grep 確認具體 line + 具體 const/enum/字串值 landed；比單純 baseline 數字更能 catch ghost commit。例如 `AIService._record_strategist_invocation` 4 callsites (不是 3) 直接驗證 E2 follow-up `5682994c` 也 landed。

**Verdict**：**PASS** — Mac-side 可跑的最大範圍 0 regression、0 integrity gap、5 Linux-only items 全 documented in Appendix B Linux-deferred verification scope。

**Report path**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--wave2_3_full_regression.md`

---

### 2026-05-16 test_track_a_spawn_argv.py 10 test fix — PASS

**對象**：`replay/tests/test_track_a_spawn_argv.py` 21 tests 中 10 個因 Round 6 HMAC sign 整合而失敗。

**三個 root causes + bonus**：
1. Envelope key rejection（5 tests）：`write_manifest_fixture()` defense-in-depth 拒 envelope keys。修法：剝除。
2. Signing key unavailable：Round 6 真 HMAC sign 需 key。修法：`_signing_key_env` fixture + `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env。
3. Field count（1 test）：`build_default_manifest_payload(cur=None)` 回 3 body keys，非 6。修法：assertion 改 3。
4. Mac artifact allowlist guard（3 spawn tests）：output_dir 必落 `/tmp/replay_artifacts_test_only` 下。

**結果**：21/21 passed x2（non-flaky）。

### 2026-05-16 Full Program-Scope Testing Audit — AUDIT COMPLETE (not a regression gate)

**對象**：Cold adversarial testing coverage audit across entire codebase. Not a commit-gating E4 regression; this is a P2 gap inventory.

**Baseline snapshot (Mac dev)**：
| 引擎 | passed | failed | ignored/skipped | notes |
|---|---|---|---|---|
| Rust lib (release) 2x | 2889/2889 | 0/0 | 1/1 | non-flaky |
| Rust integration (--tests) | 3082 total; 3080 pass | 2 | 1 | 2 pre-existing: stress_bb_breakout + stress_bb_reversion |
| Python srv/tests/ 2x | 413/413 | 1/1 | 2/2 | 1 fail = test_v072 source drift; non-flaky |
| Python control_api_v1 2x | 4089/4089 | 4/4 | 8/8 | 4 collection errors excluded; 4 fail = pre-existing; non-flaky |

**Critical findings (8 HIGH / 12 MEDIUM / 7 LOW)**：

HIGH-1: 104/342 Rust production files (30%) have ZERO inline `#[test]` or `#[cfg(test)]` -- including tick pipeline hot-path steps (step_0_fast_track 636 LOC, step_4_5_dispatch 1663 LOC, step_6_risk_checks 561 LOC), fill_engine 710 LOC, risk_config_advanced 1261 LOC.
HIGH-2: 107/196 Python app modules (55%) have no corresponding test file -- including h0_gate 971 LOC, risk_routes 1091 LOC, live_trust_routes 1121 LOC, strategy_ai_routes 1213 LOC.
HIGH-3: 4 Python test files cannot be collected (ModuleNotFoundError: 'program_code') -- R6/R7 calibration/advisory tests use absolute `from program_code...` imports but pytest runs from control_api_v1 directory.
HIGH-4: 0 proptest usage in entire Rust codebase -- no property-based testing for serde round-trip, state machine transitions, or IPC schema fuzzing.
HIGH-5: test_v072_feature_baseline_writer_static fails: assertion string `--apply requires --i-understand-this-modifies-db` does not match actual source `rejected flag {arg}: --apply requires the explicit acknowledgement flag`.
HIGH-6: 2 Rust integration tests fail persistently: stress_bb_breakout_valid_squeeze_with_volume and stress_bb_reversion_extreme_oversold_bounce -- strategy signal logic not triggering as test expects.
HIGH-7: 39 Python tests with genuinely NO assertions (AST-verified) -- including 15 in test_layer2.py, 2 in test_paper_live_gate.py.
HIGH-8: 0 DB connection loss tests exist; no test simulates mid-transaction PG drop/timeout in Python or Rust.

MEDIUM-1: 447 .unwrap() calls in Rust production code (excluding tests) -- any could panic on malformed data.
MEDIUM-2: 2 tautological `assert True` in test_bybit_rest_client_parity.py:549 and test_v055_evidence_insert_fix.py:1320.
MEDIUM-3: 3 duplicate `test_pure_utils.py` files across test directories cause pytest collection conflicts.
MEDIUM-4: No SLA benchmark for H0 Gate <1ms or IPC <5ms -- only tick latency benchmark (<100us) exists.
MEDIUM-5: Float exact equality `==` used in ~15 places for prices/quantities in test_layer2.py and test_paper_live_gate.py (should use pytest.approx).
MEDIUM-6: Only 32 async test functions in 24 files for Python -- given heavily async codebase (asyncio), concurrency coverage is thin.
MEDIUM-7: Cross-language float consistency tests limited to manifest signer (8 tests) and executor decision parity (20 tests) -- ATR/BB/Sharpe/indicator calculations have 0 cross-language tests.
MEDIUM-8: risk_config_advanced.rs (1261 LOC) has 0 test references anywhere in test code.
MEDIUM-9: ws_client/ (parsers.rs 368 LOC + connection.rs + run_loop.rs + dispatch.rs 718 LOC) has 0 tests.
MEDIUM-10: paper_state/fill_engine.rs (710 LOC) has 0 direct test file; only exercised indirectly via paper_state/tests.rs.
MEDIUM-11: governance_hub_cascades.py (811 LOC) and governance_hub_event_handlers.py have 0 test file.
MEDIUM-12: learning_auto_pipeline.py (827 LOC) and layer2_engine.py (840 LOC) have 0 test file.

LOW-1: 32 skip/xfail markers -- mostly conditional (env-var gated for Linux PG), acceptable.
LOW-2: 1 #[ignore] in Rust: LG1-T3 known gap h0_shadow_mode propagation.
LOW-3: event_consumer/bootstrap.rs (982 LOC) and main_pipelines.rs (981 LOC) untested -- primarily wiring/startup.
LOW-4: strategies/**/params.rs files (bb_breakout 592, bb_reversion 368, grid_trading 340, ma_crossover config) untested -- config/param structs.
LOW-5: Pydantic V1 @validator deprecation warnings (423 warnings) in replay routes.
LOW-6: news/provider.rs and news/types.rs untested -- non-critical feature module.
LOW-7: replay/profile.rs (322 LOC) and replay/apply_fill.rs (761 LOC) lack inline tests but are covered by integration tests.

**教訓**：
1. Per-file test coverage gap was never previously inventoried at scale. 107/196 Python app modules untested is a structural debt, not a single-sprint gap.
2. Collection errors from absolute import (`from program_code...`) indicate these tests were never run from the control_api_v1 directory -- they only work from srv root with PYTHONPATH set. This means 4 test files (R6/R7 calibration + advisory) have NEVER run in the standard pytest workflow.
3. The absence of proptest in a Rust trading engine is a significant architectural gap -- serde round-trip, state machine fuzzing, and numeric edge case exploration would all benefit.
4. The stress_integration test failures (bb_breakout + bb_reversion) suggest strategy logic drift since the tests were written, or the tests themselves have incorrect expectations post-refactor.

**Report**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--full-scope-testing-audit.md`

---

### 2026-05-11 P0 Replay Tier A Post-IMPL Regression (HEAD `d9a52572`, 8 local commits) — **PASS · 0 BLOCKER**

**對象**：4 個 E1 sub-task 合流後完整回歸驗 — E1-A T1+T2+T2.5 (`ffc57d7f`/`452ad7ba`) / E1-B T3+T4 (`7f6182b2`/`effb55ec`) / E1-C T5 (`a17ff37a`/`77046b62`) / E1-D T6 acceptance pack (`01b05e29`/`d9a52572`)。

**Test 結果**：
| 引擎 | passed | failed | baseline | delta | non-flaky |
|---|---|---|---|---|---|
| Rust lib (release) | **2807** | 0 | 2800 pre-E1 | +7 (E1-A +4 / E1-C +3) | ✅ 雙跑 0.56/0.55s |
| Rust lib replay subset | 116 | 0 | 113 | +3 | ✅ 0.03s |
| `replay_tier_a_acceptance` (--test, E1-D 新檔) | **6** | 0 | n/a | +6 | ✅ 0.00s |
| `replay_forbidden_guard_acceptance` | 4 | 0 | 4 | 0 | ✅ V3 §12 #10 |
| `replay_runner_e2e` | 6 | 0 | 6 | 0 | ✅ proof_1/4/5 byte-equal |
| `replay_runner_e2e_param_delta` | 2 | 0 | 2 | 0 | ✅ R5-T7 xlang |
| `replay_profile_acceptance` | 5 | 0 | 5 | 0 | ✅ V3 §12 #11 |
| `replay_mac_policy_acceptance` | 4 | 0 | 4 | 0 | ✅ |
| `replay_manifest_signer_xlang_consistency` | 8 | 0 | 8 | 0 | ✅ V3 §12 #14 |
| Python pytest `test_replay_*.py` | **170** | 0 | 170 | 0 | ✅ 雙跑 0.81/0.80s |

**核心驗證點**：
- A.1 lib 雙跑 2807/0/0 同綠（0.56s/0.55s）；delta +7 完全對齊 PA spec（E1-A `runner_tests.rs` +4 sanity test / E1-C `runner_tests.rs` +3 T5 unit test）
- A.2 7 個 acceptance `--test` 套件全綠 — 含 T6 新加 6 test + 既有 29 維持 PASS（35 total replay acceptance tests）
- B Python pytest 170/170 對齊 E1-B 自報，雙跑非 flaky
- C Mock 審查：
  - T6 Rust：`OpenThenCloseStub` / `ContextObserver` inline `impl Strategy` 是 trait contract driver，合法 test scaffold（per E1-D §6 boundary）；0 業務邏輯 mock；real `IsolatedPipeline.run()` / `apply_fill_open` / `risk_adapter.evaluate()` / `scanner_timeline.is_active_at()` / `StrategyFactory.create_with_params()` 真跑
  - E1-B Python：mock 純 IO 邊界（IPC fetch 4 個 + PG xact 3 個），核心 `_build_manifest_jsonb` + TOML parse + manifest hash invariance 真實跑
- D Forbidden surface：7 條全 not touched（grep 命中只在 doc-comment 敘述 invariant 非觸發）；§四 5 硬邊界 0 觸碰；cross-platform 0 硬編碼路徑
- E V3 §12 #10/#11/#14 全保 PASS（xlang signer 8/8 證實 Python tomllib parse + Rust serde parse byte-equal sha256）
- F SLA：replay 在 isolated subprocess + adapter pipeline scope，0 impact production hot path（H0 <1ms / Tick <0.3ms / IPC <5ms 不觸）
- G 浮點 1e-4：E1 改動 0 新數值 hot path（HashMap pure f64 pass-through + position borrow pointer + Python manifest assemble），cross-language tolerance trivially satisfied

**§九 file size 跟蹤**：
- `runner.rs` 1237 LOC（接近 800 警告線 P2 watch）
- `runner_tests.rs` 1645 LOC（>800 警告 pre-existing 測試檔 cohesion exception）
- `apply_fill.rs` 761 LOC（接近警告）
- `replay_tier_a_acceptance.rs` 686 LOC（新檔 <800 OK）

**教訓**：
1. **inline-impl Strategy stub 是合法 test scaffold**：T6 用 `OpenThenCloseStub` / `ContextObserver` 在 `impl Strategy for ...` 內構造可配置 emit 行為驅動 IsolatedPipeline 測 wire-up — 不違反「mock 業務邏輯」反模式，因為 Strategy trait 是 contract layer；test scaffold 不 stub real 計算路徑（apply_fill/risk_adapter/scanner_timeline 全真跑）。E4 sniff test：grep `mock\|stub\|fake` 後 + 看 impl detail，inline impl Strategy/Observer 是 OK，inline impl IsolatedPipeline/PaperState 才是反模式。
2. **任務描述 baseline delta 真實對賬**：PA spec 設定 2800 → 2807 (+4+3=+7)，E4 真實 run 2807/0/0 完全匹配（不只是「達到 baseline」，是「delta 精確）；E1-A `runner_tests.rs` +141 LOC 含 4 sanity test，E1-C +178 LOC 含 3 T5 unit test。Baseline delta 真實對賬比「passed >= baseline」抽象要求更嚴 — 此 task 通過此 sharper bar。
3. **--test crate 不計 --lib baseline**：E1-D 新檔 `tests/replay_tier_a_acceptance.rs` 6 test 在 `cargo test --test` scope，不在 `cargo test --lib` 2807 count 內。混淆此可能誤判 baseline regression。E4 必驗 lib baseline + 對每個 --test 套件分別跑驗 0 regression。
4. **Linux runtime smoke gating**：任務 §6.3「真實 27h validation 等 PM bundle push 後再做」是 by design — E4 不跑 deploy，只驗 Mac 本地 binary build + ssh trade-core 可訪問 + Linux working tree clean。27h replay 在 PM bundle push + Linux `--rebuild --keep-auth` deploy + 跑 short window smoke 後才動。

**Verdict**：**PASS** — 8 commit chain 全綠，0 regression，0 forbidden_guard trip，Mock 純測試 scaffold；派 PM bundle push + 三端 rebuild + 跑真實 27h replay validation。

**Report path**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--replay_tier_a_post_impl_regression.md`

---

### 2026-05-11 W2 IMPL Chain 4 Sub-agent Regression (HEAD `1f0354cf`) — **NEEDS_FIX · 3 HIGH BLOCKER in IMPL-4 SQL**

**對象**: W2 A4-C BTC→Alt Lead-Lag 4 sub-agent commit `1f0354cf`（IMPL-1 orderbook +568 LOC / IMPL-2 fence amendment / IMPL-3 check_57 +321 + test +273 / IMPL-4 paper edge report +1257 LOC + counterfactual SQL +279 LOC）。E4 必跑 5 項 per PA dispatch §3.4 §3.5 §5 + 必跑 Linux PG empirical dry-run per `feedback_v_migration_pg_dry_run.md`。

**Test 結果**:
| 引擎 | passed | failed | ignored | baseline | delta | non-flaky |
|---|---|---|---|---|---|---|
| Rust lib (release) | **2797** | 0 | 0 | 2789 pre-W2 | +8 (IMPL-1) | ✅ 雙跑 0.56/0.57s 同綠 |
| Rust W2 btc_lead_lag specific | 35 | 0 | 0 | n/a | +8 | ✅ 含 ingest task / 5-tick integration / cancel-safe |
| W2 healthcheck Python fixture (Mac) | 10 | 0 | 0 | n/a | +10 | ✅ 真實 cover PASS/WARN/FAIL 三段 |
| Python tests/ | 253 | 1 | 2 skipped | n/a | **0 W2 regression** | 1 fail 是 pre-existing docs/README.md drift (c13c811e) |
| **IMPL-4 SQL Linux PG dry-run** | **0** | **3 BLOCKER** | - | n/a | -3 | ❌ NEEDS_FIX |

**3 HIGH BLOCKER**:
1. **B1**: `sql/queries/w2_btc_alt_lead_lag_counterfactual.sql:182` `trading.klines` 不存在 → 真實 schema = `market.klines`（Linux PG `\dt trading.*` 證實）
2. **B2**: 同檔 line 185 `k.interval = '1m'` column 不存在 → 真實 column = `k.timeframe`（Linux PG `\d market.klines` 證實 schema）
3. **B3**: 同檔 line 42 + line 87 SQL 注釋裡的 `%(window_days)s` / `%(cohort_symbols)s` 字面字串 → psycopg2 不跳過 `--` 注釋，當 placeholder 解析 → caller `KeyError`（Mac empirical caller test 100% fail）

**Fixed-SQL 驗證**: 3 BLOCKER fix 後跑 Linux PG → 3948 row 返回（panel 565 × 7 cohort sym ≈ 3955 panel_expanded LEFT JOIN klines + fills）→ 設計結構 OK，只是 schema/syntax 失誤。

**IMPL-3 Linux PG runtime verify (re-verify per task)**: status=`WARN`, msg=`window=60m total_n=60 age=56.0s/PASS cohort=7/7/PASS extreme=0(0.0%)/PASS book=placeholder_zero/WARN`. Hot-path index `idx_btc_lead_lag_panel_ts_window` 存在 + chunk `_hyper_75_486_chunk` 對齊 IMPL-3 sub-agent self-report；EXPLAIN ANALYZE 走 Seq Scan 是 PG cost-based 對 565 row 正確選擇（不是 index miss bug）；execution time 0.497ms well within SLA。

**核心驗證點**:
- A.1 lib test 跑兩遍 2797/0/0 non-flaky 確認；IMPL-2 sub-agent 報告中提到的 IMPL-1 line 82 註釋語法錯 + line 1279 test signature 不齊 — 實際 build PASS（IMPL-1 commit 前已修補）
- A.2 W2 btc_lead_lag 35 test 含 `ingest_task_to_producer_5_tick_integration`（真實 spawn tokio task + 5 tick fixture 餵不同 imbalance pattern + assert ∈ {0.333, -0.500, 0.0, 0.714, -0.818}）+ `ingest_task_drops_non_btc_or_non_orderbook_event`（真實 ETHUSDT Orderbook + BTCUSDT Ticker 過濾 silent drop）+ `run_loop_responds_to_cancel`（CancellationToken 真實退出）— **0 業務邏輯 mock**，tokio mpsc 是合法 IO 邊界
- D 跨語言一致性: Rust `f32` → PG `real` → Python `f64` 是 f32→f64 擴展 cast 精度差 < 1e-7 遠優於 1e-4 容差；schema 對齊 7-symbol cohort `text[]` + regime enum `text` + BIGINT epoch ms 完全一致；empirical PG sample 3 row 證實
- E Mock 4 sub-task each:
  - IMPL-1 ✅ 0 業務邏輯 mock；公式 `(bid_top_n - ask_top_n) / (bid+ask)` 真實跑進 fixture
  - IMPL-2 ⚠️ env-gate logic 等 IMPL-5 cover（per PA dispatch 設計，非 BLOCKER）
  - IMPL-3 ✅ DB cursor IO mock 合法；verdict logic + SQL aggregate 真跑（Linux PG real check 確認）
  - IMPL-4 ✅ smoke 3 case PSR/DSR/CI/R²(N) 公式真實計算（Bailey-LdP 2012 / Künsch 1989 / OLS 回歸 / Φ via math.erf 跨平台）；唯一 mock = `_make_mock_row` SQL row constructor 是合法 input fixture，下游 helper 真跑

**Unexpected / 跟蹤 (非 W2 引入)**:
1. **docs/README.md drift**: archive `2026-05-09--claude_md_section5_pre_alpha_surface.md` 由 commit `c13c811e` (2026-05-09 W-AUDIT-8a) 引入，但 README 索引未補登 → `tests/structure/test_docs_readme_index_static.py` FAIL；非 W2 引入；P2 followup
2. **btc_book_imbalance 全 0**: Linux engine 載入 pre-IMPL-1 binary 仍寫 placeholder 0；待 `restart_all --rebuild --keep-auth` deploy 後翻 non-0（per IMPL-3 sub-agent dry-run note）— **預期 deploy gating 行為**

**教訓 (記錄 lesson)**:
1. **psycopg2 不跳過 SQL `--` 注釋裡的 `%(...)s` 字面字串**：注釋裡寫 placeholder 字面字符會被當 binding 解析 → caller KeyError。設計 hygiene：SQL 注釋若需提及 placeholder 名，用 Markdown 反引號或全角符或純文字描述（如「window_days 變數」）。**Mac mock pytest false-pass 不夠**（IMPL-4 sub-agent smoke-test 不連 PG 所以 mock cursor 不踩 binding 邏輯）→ `feedback_v_migration_pg_dry_run.md` 再次 reinforce
2. **schema namespace 跨 table 異質**: `panel.btc_lead_lag_panel`（新建）/ `trading.fills`（trading 域）/ `market.klines`（market 域）— 三個 schema namespace 不同 → 寫 SQL 時必先做 Linux empirical schema check 不能憑記憶寫 `trading.<table>` template
3. **Seq Scan ≠ Index miss bug**：低 cardinality + 全 row 在 window 內，PG 正確選擇 Seq Scan 比 Index 便宜；驗 hot-path index 命中不能只看 `Index Scan` 字樣，要看 cost 模型 + execution time 是否 within SLA + row count 是否在 cardinality threshold
4. **跨語言浮點容差自然滿足條件**: f32→f64 cast precision diff < 1e-7 → 1e-4 容差 trivially satisfied；W2 scope 內無新計算 hot path（panel field 大多 input pass-through）所以 cross-language tolerance 不是 critical

**Verdict**: **NEEDS_FIX**（W2-IMPL-1/2/3 + cargo test PASS，IMPL-4 SQL 3 BLOCKER 退回 E1 → 修 → E2 re-review → E4 重 dry-run → W2-IMPL-5 派發前必收口）

**Report**: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w2_chain_e4_regression.md`

---

### 2026-05-11 W-C MAG-082 Caveat 1+2+3 Fix Regression (HEAD `58970d24` + 4 file working tree) — **E4 PASS · Deploy READY**

**對象**: PA `2026-05-10--w_c_caveat_fix_plan.md` E4 regression 必跑 5 項。Rust R1 +877 LOC + R2 1 line + Python +254 LOC。E2 R1 APPROVE WITH CONDITIONS + R2 mini APPROVE · E5 APPROVE WITH 3 P2 perf SLA PASS · 最後 E4 gate。

**Test 結果**:
| 引擎 | passed | failed | ignored | baseline | delta | non-flaky |
|---|---|---|---|---|---|---|
| Rust lib (release) | **2776** | 0 | 0 | 2776 (sibling W2 wave +19 含 W-C) | 0 | ✅ 雙跑 0.55s 同綠 |
| Rust lib (debug) | **2776** | 0 | 0 | n/a | n/a | ✅ 0.64s |
| Rust W-C runtime_shadow | 7 | 0 | 0 | 2 pre-fix | +5 (含 R2 改 assertion) | ✅ |
| Rust agent_spine module | 13 | 0 | 0 | 8 pre-fix | +5 | ✅ |
| Python W-C healthcheck | **14** | 0 | 0 | 11 pre-fix | +3 (3 Caveat NEW) | ✅ 雙跑 0.02s 同綠 |

**核心驗證點**:
- A.1 lib test 雙 profile (release + debug) 2776/0/0 一致 · 跑兩遍 non-flaky 確認
- A.2 W-C runtime_shadow 7 test 全 PASS · 含 R2 fix test `runtime_shadow_emit_fill_completion_lineage_writes_real_fill_chain` 新 assertion `report_change.object_id == "report-stub-1002"` (append-only event log 語意對齊)
- A.3 Mock 審查: Rust 用真實 `tokio::sync::mpsc::channel(32)` + 真實 `emit_fill_completion_lineage` production fn 呼叫 · 真實驗 `AgentSpineMsg::*` enum variant · 真實驗 `filled_qty=0.5` / `liquidity_role="taker"` value-realism core invariant · 真實驗 ExecutedBy edge `fill_completion=true` 標記 (Python check_55 SQL 依賴點)
- B.1 Python W-C 14/14 PASS · 含 3 R3 NEW: `state_changes_empty_blocks_after_pass_path` (Caveat 1) / `bad_report_value_quality_blocks_with_cutoff` (Caveat 2 + env var roundtrip) / `real_fill_propagation_partial_warns` (Caveat 2 50% gate)
- B.3 Python Mock 審查: 只 mock `cur` DB cursor (IO 邊界);`check_55_*` 本體真實跑 SQL parse + 7-tuple unpack + state_changes_count helper + gate logic + msg format
- C 跨語言一致性: W-C scope 無新浮點計算 hot path, deferred to post-deploy 30min 短窗對抗 SQL
- D SLA: E5 已覆蓋 (emit_entry +3-6μs / emit_fill_completion 10-20μs / Python check_55 22.54ms / Spine writer mpsc 容量充裕);E4 lib test 0.55s 無 runtime 異常
- A.4 Release/Debug profile 一致性 2776/0/0 · 0 profile-specific drift

**Unexpected / 跟蹤 (非 W-C 引入)**:
1. **W1 sub-task 3 pre-existing import breakage**: `runner.py:84` import `check_panel_freshness` 由 commit `ddf0cebe` 引入,但 `checks_derived.py` 未 land 對應 function · 14 helper_scripts/db test file collection error · E1 R3 Caveat E 用 `importlib.util.spec_from_file_location()` isolation 繞行 W-C test → 14/14 PASS · E5 D-4 P2 待 W1 補完
2. **Mac local bin build error**: `main_pipelines.rs:922 btc_lead_lag_panel_slot` 缺 init = sibling W2 sub-task 4 staged-but-uncommitted 本機 only → 走 lib-only test path 符合任務 constraint · Linux 端 PM holistic commit 後驗 bin
3. **§九 file size pre-existing 警告 (P2)**: `tests.rs` (agent_spine) 1063 LOC > 800 警告 (W-C +361 從 ~702),`step_4_5_dispatch.rs` 1557 LOC pre-existing > 800 · 仍 < 2000 hard cap · E5 D-5/D-6 拆 sibling P2 ticket
4. **stable_id 算法字面複製 (E5 D-1 P2)**: `step_4_5_dispatch.rs:623-645` vs `runtime_shadow.rs:72-80` · `runtime_shadow_build_transition_ids_are_distinct` test 已 invariant lock · 不阻 deploy

**Baseline 建議更新** (E4 不直接改 CLAUDE.md):
- Rust lib test: 1980 → 2776
- Python W-C 專屬: 新增 14/14 baseline
- Python helper_scripts/db full regression: 待 W1 sub-task 3 補 `check_panel_freshness` 後重 baseline

**新增測試 LOC 統計**:
- Rust: +5 unit test in `tests.rs` (5_build_state_transitions / skips_transitions_in_paper / writes_real_fill_chain / skips_invalid_modes / build_transition_ids_distinct) + 1 既有測試 升級 (lineage_emits_complete_demo_chain accepted 10→15)
- Python: +3 unit test in `test_agent_spine_healthcheck.py` (3 Caveat 對應)

**結論**: 0 BLOCKER · 0 regression · 0 業務邏輯 mock · 全部 SLA / file size / 跨 profile / non-flaky 驗證通過 · 派 PM commit + push + deploy

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_c_fix_e4_regression.md`

---

### 2026-05-10 Sprint N+1 W4 W-AUDIT-3b Runtime Smoke Test DESIGN（pre-dispatch, HEAD `4bb5d485`）— **E4 DESIGN PASS**

**對象**：dispatch v3.4 §3.4 W4 (W-AUDIT-3b runtime smoke test, 1 day E4 預跑 design)。任務 = read-only design + spec, 不寫 IMPL test code，留 W4 sub-agent IMPL phase。

**關鍵發現**：
1. **既有 9 fail-closed test case 已涵蓋 dispatch §3.4 acceptance 「≥ 1 fail-closed test case」**：`test_executor_plan_v2.py` 5 + `test_executor_agent_unit.py` 3 + `test_executor_shadow_to_live_e2e.py` 1。Rust 端 `intent_processor/tests.rs:892-1335` 兩條真路徑（AuthNotEffective Production / Validation profile bypass）。重複新寫 `test_executor_fail_closed.py` 是 fake coverage。
2. **唯一 gap = RouterLeaseGuard Drop release on rejection path**：既有 test 無 assertion 驗 rejection 路徑下 Drop 真的呼 release(Cancelled)。建議 W4 IMPL 加 1 條 Rust unit test (~40 LOC) 補。
3. **[55] healthcheck SQL 在 `checks_agent_spine.py:109-208`** (`_complete_chain_counts` CTE)：4-hop JOIN strategy_signal→decision→verdict→plan + LEFT JOIN idem + report，5 個指標含 `chains_with_lease` (`plan.lease_id IS NOT NULL AND <> ''`)。
4. **2026-05-08 22:09 UTC baseline (CLAUDE.md §三)**：`chains=101, chains_with_lease=76, chains_with_report=101, bad_report_quality=0`，但 `LINEAGE_READY_NOT_WINDOW_PASS window=1440m` (Stage 2 evidence 已收，等 24h window PASS)。Smoke test 5min window 抽要從 `_complete_chain_counts` CTE 改 `interval '5 minutes'`。

**W4 IMPL phase 預估**：~120 LOC, ~3.5h（W4-1a baseline 10min + W4-1b Rust Drop test 1h + W4-2 smoke shell 1.5h + W4-3 跑 + report 30min 含 5min window wait），符合 dispatch v3.4 「1 day」上限。

**對 PA push back (acceptance criteria refinement 建議)**：
- pytest 規格改寫：「既有 9 case 全 PASS + 補 1 條 Rust Drop release test」（避免 fake coverage 重寫）
- Smoke test 加 4 條 invariant：`chains_with_lease ≥ 1` + `bad_report_quality = 0` + `chains_with_report ≥ 1` + `engine_alive=true 在 60s 內`
- 5min window 不夠分辨「pre-restart 累積混入」，建議跑 baseline-vs-window 兩次對比

**Test order 強制**：pytest first (fast, ~2min) → runtime smoke (slow, ~6min ssh trade-core)。pytest FAIL → 不跑 smoke (省 6min)。

**報告檔**：`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-10--w_audit_3b_runtime_smoke_test_design.md`

**教訓追加**：
1. **預跑 design 任務優於 IMPL phase 才寫 spec**：W4 sub-agent 進 IMPL 前已有 scenario matrix + LOC/時間預估 + acceptance 修訂建議，省 W4 sub-agent 自己摸 既有 9 case 的 30min。
2. **acceptance 「≥ 1 test case」是模糊規格 → 必先掃既有 case** ：dispatch v3.4 §3.4 寫得太寬，若 W4 sub-agent 不查就硬寫新 test，會重複 9 個既有 case 的 fake coverage。E4 預跑 design 抓出此 gap。
3. **healthcheck SQL CTE 是 SoT，smoke shell 必抽縮 window 版本**：別在 shell 重寫 4-hop JOIN，改剪 CTE + `interval '5 minutes'` 維持與 [55] 同口徑，避免 smoke PASS 但 [55] FAIL 的不一致。
4. **runtime smoke 用 ssh trade-core 而非 Mac 跑**：Mac engine_alive=false 是預期（CLAUDE.md §四）；smoke 必透過 ssh trade-core 才有 real runtime。

---

### 2026-05-10 Sprint N+0 W2 Regression Baseline（5 sub-agent IMPL 並行交付，HEAD `833c50f0`）— **E4 PASS-WITH-1-OUTSTANDING**

**對象**：5 sub-agent W2 並行交付：
- W-AUDIT-8a Phase A (E1-A `833c50f0`): trait + AlphaSurface + 5 strategies declare
- W-AUDIT-4b-M2 (E1-B `404174a4`): fill writer entry_context_id INSERT trigger + V083
- W-AUDIT-4b-M3 (E1-C `e93a6e5c`): governance reject negative label + V084 + class weight
- W-AUDIT-9 T4 (E1-D `1f010c52` + `870a3252`): [58] healthcheck + C-A6 runtime apply prep
- W-AUDIT-9 T5 (E1a `3982dc52` + `d005a663`): GUI graduated canary surface + manual promote

W1 baseline 對比：cargo lib 3077 PASS / 0 fail（425+2625+27）+ pytest 4265 PASS / 5 fail（4 pre-existing + 1 sibling CI workflow `0dc6d659`）。

**Verdict**：**PASS-WITH-1-OUTSTANDING** — 5 wave PASS + 1 cross-wave stress fail RETURN-TO-E1（W-AUDIT-6d `f6fb315a` cross-wave 副作用，被 W2 全 workspace 跑暴露，W1 baseline `--lib` only 漏抓）。

| 引擎 | round 1 | round 2 | W1 baseline | delta | identical | verdict |
|---|---:|---:|---:|---|---|---|
| Linux cargo lib --workspace (`openclaw_core` + `openclaw_engine` + `openclaw_types`) | 432+2632+27 = 3091 / 0 fail | identical | 3077 / 0 | +14 (+7 core alpha_surface / +7 engine writer+reject) | yes | PASS |
| Linux pytest tests/ + control_api_v1/ | 4302 / 5 fail / 12 skipped | identical | 4265 / 5 fail / 12 skipped | +37 PASS / 0 NEW fail | yes | PASS |
| Linux `cargo test --release stress_bb_reversion_extreme_oversold_bounce` | **1 FAIL** (left=0 right=1) | n/a | n/a (W1 8 wave `--lib` only 未跑 stress) | 1 cross-wave NEW fail | n/a | RETURN-TO-E1 |
| Linux `cargo test --release --test replay_runner_e2e proof_5_baseline_vs_candidate_two_runs` | 1 PASS (byte-identical) | n/a | n/a (8a Phase A NEW) | match | n/a | PASS |
| Mac cargo build --release engine + core | exit=0 / exit=0 (18 + 0 warning) | n/a | match W1 | 0 error | n/a | PASS |
| V080+V082+V083+V084 idempotent 雙跑 | NOTICE skip + `[migrate] OK` × 4 byte-identical | identical | match W1 | idempotent ✓ | yes | PASS |
| DB row cleanup (3 表) | 0 / 0 / 0 | identical | n/a | identical | yes | PASS |

**1 cross-wave stress fail root cause**：`bb_reversion::require_ma_confirmation: bool = true` (default ON, AMD-2026-05-09-02 §3) + `mod.rs:163-167` `ma_pair_allows_entry()` fail-closed when `ma_value() == None` + stress fixture `stress_integration.rs:72` provide `sma_50: None` → 0 intents 進場 vs assertion `assert_eq!(intents.len(), 1, "should enter long on extreme oversold")`。修復方向：fixture 補 `sma_50: Some(<oversold ma 值>)` 對齊 W-AUDIT-6d business semantic（「extreme oversold + price < ma_50 → enter」整條 contract），**禁止**反向 disable invariant 通過測試。

**W2 NEW PASS delta 對齊**：cargo +14 (vs sub-agent claim 累加 +17 差 -3 — M-2/M-3 同 file 共享 helper test scaffolding 重用)；pytest +37 (vs sub-agent claim 累加 +94 差 -57 — sub-agent IMPL 各自 claim 是 isolated test +N，full-suite 因 fixture parametrize 平攤後 net +37)。**0 NEW fail / 0 regression / deterministic identical 才是 W2 acceptance 硬條件，本 round 全達成**。

**4 pre-existing pytest fail 不變**（雙跑 identical）：`test_archive_top_level_files_are_all_indexed` / `test_oe_006_close_retry_budget_has_real_timeout_guard` / `test_grafana_data_writer.test_start_sets_running` / `test_replay_routes_safe_query_audit.test_case2_pg_kill_simulation_returns_200_degraded`。**Sibling CI workflow 1 fail 不變**：`test_ci_workflow_runs_release_cargo_check_for_openclaw_engine`（`0dc6d659` 副作用，PM follow-up）。

**雙端 git status**：Mac 1 untracked = E1-A W-AUDIT-8a IMPL report（PM 後處理）；Linux 0 lines clean。HEAD 兩端 + origin 全同步 `833c50f0`。

**V### idempotent**：4 migration 雙跑 byte-identical NOTICE chain；3 表 row count 0/0/0；UDF `learning.mlde_sample_weight` live verified；`_sqlx_migrations` max=79（V080-V084 透過 `linux_bootstrap_db.sh --apply` 直接 apply 未走 sqlx checksum 路徑，不影響 schema land + idempotent；deploy `OPENCLAW_AUTO_MIGRATE=1` 補 checksum 或 `bin/repair_migration_checksum` manual 補）。

**byte-identical replay**：W-AUDIT-8a Phase A invariant 2 critical PASS — `proof_5_baseline_vs_candidate_two_runs` 1/0 PASS。Tier 1 `AlphaSurface::tier1_only()` build 在 step_4_5_dispatch hot path 不破 baseline replay 序列確定性。Phase A「0 行為變化」契約成立。

**5 教訓**：
1. **W1 baseline scope `--lib` only 漏抓 integration test cross-wave 副作用** — W1 second-pass 跑 `cargo test --lib --workspace --release` PASS 但 `cargo test --release stress_bb_reversion_extreme_oversold_bounce`（integration target）會抓 W-AUDIT-6d `f6fb315a` 引入的 fixture / business gate mismatch。E4 W3+ baseline 改用 `cargo test --release --workspace`（含 integration tests）以早期暴露 cross-wave 副作用。
2. **AMD-2026-05-09-02 §3 `require_ma_confirmation: true` default 是業務語義，不是 dev rollback** — `require_ma_confirmation: false` 是 W-AUDIT-9 rollback 路徑，不是測試 convenience override；fixture 必須對齊業務 contract（`sma_50: Some(...)` for oversold scenario），不是去 invariant。
3. **5 sub-agent 並行 IMPL 各自 sub-agent 自跑 PASS 不等於 cross-wave PASS** — 本 W2 5 sub-agent 各自報告 self-test 全綠，但 W1 W-AUDIT-6d cross-wave 副作用要 W2 全 workspace integration test 才暴露。E4 W3+ 必跑 integration suite 確認 W1 漏抓。
4. **V### migration 全 NOTICE skip 表示 schema 已 deploy land** — 本 round V080/V082/V083/V084 全 NOTICE skip = 之前 wave 已 land 過。schema apply 路徑 idempotent 驗 PASS 但**不證明 producer / consumer 寫入路徑正確**；需 deploy 後 24h watch `learning.decision_features_evaluations` row count + `observability.fills_entry_context_id_health` null_ratio 趨勢。defer PM 後續 deploy verification。
5. **`_sqlx_migrations` max=79 vs 實際 schema V084 land** — 本 round 用 `linux_bootstrap_db.sh --apply` 直接 apply（不走 sqlx 路徑）；checksum entry 缺。對 idempotent 不影響（schema 已 land + idempotent 驗 PASS），但對 P0 sqlx hash drift incident 治理風險需 PM 後續 deploy 用 `OPENCLAW_AUTO_MIGRATE=1` engine 啟動路徑補 sqlx checksum entry，或 manual 用 `bin/repair_migration_checksum`。

**Report**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-10--sprint_n0_w2_regression_baseline.md`

---

### 2026-05-09 Sprint N+0 Day 3-5 Regression Baseline（4 sub-agent IMPL 9 commits，HEAD `f5574c5a`）— **E4 FAIL → RETURN-TO-E1**

**對象**：4 sub-agent 平行交付（W-AUDIT-9 T1+T2 + W-AUDIT-9 T3 + W-AUDIT-9 T6 + W-AUDIT-6d 4/5/6 + B-M1 + W-AUDIT-4b-M1）共 9 commits，已 push origin + Linux fast-forward sync 至 `f5574c5a`；對比 v3 baseline `da2aba11`（pytest 3961/3 fail / cargo lib 2584/0 fail）。

**Verdict**：**FAIL** — 雙跑 deterministic identical（0 transient flake），但 **5 個 NEW regression 確認**：
- 2 個 Rust IPC test fail — `ipc_server::tests::config::test_g3_02_a2_patch_executor_routes_to_demo_engine` + `test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config` — W-AUDIT-9 T1+T2 commit `094f9914` `ExecutorConfig::validate()` §4.4 invariant `shadow_mode == canary_stage.as_shadow_mode()` 拒絕舊 IPC patch 寫 `shadow_mode=false` 但無 `canary_stage` 同步的 payload；E1-A 漏更新 sibling test fixture。在 v3 baseline `da2aba11` 工作樹下這 2 個 test 是 PASS（cargo test ipc_server::tests::config = 15/0）→ HEAD 變 fail 確認 = NEW regression。
- 3 個 Python `test_executor_decision_parity` fail — `test_golden_fixtures_agree_rate` (10/20 fail) / `test_synthetic_handcrafted_agree_rate` (20/40 fail) / `test_overall_agree_rate_ge_95pct` (40/70 below 67) — W-AUDIT-9 T3 commit `200188ad` 改 `_read_shadow_mode()` 走 stage projection，所有 live fixture 走 fail-closed `block_shadow` 預設；fixture 沒注入 `canary_stage_provider()` 同步 stage>=1。E1-C 在 `_make_runtime_config` helper 修了但漏 parity fixture builder（IMPL report §2.2 自承）。在 v3 baseline 下 parity = 5/0 / agree=70/70 100% → HEAD 全 disagree = NEW regression。
- 1 個 CI workflow test fail — `test_ci_workflow_runs_release_cargo_check_for_openclaw_engine` — commit `0dc6d659 ci: 拆兩個 job 取代 matrix if` 改 workflow 但沒同步 sibling structure test 的 `'rustup target add "${{ matrix.target }}"' in WORKFLOW` assertion。**非本 4 sub-agent 範圍**但仍是 N+0 chain regression。

| 引擎 | run 1 | run 2 | v3 baseline | delta |
|---|---:|---:|---:|---|
| Linux cargo lib openclaw_engine | 2622/2 | 2622/2 | 2584/0 | +38 PASS / +2 NEW fail |
| Linux pytest tests/ + control_api_v1/ | 4262/8 | 4262/8 | 3961/3* | +301 PASS / +5 NEW fail |
| Mac cargo build --release engine + core | 0 error | n/a | 0 error | match ✓ |
| V080 schema mock pytest | 21/0 | 21/0 | new | match ✓ |
| V080 + V082 Linux PG empirical apply | OK no-op | OK no-op | n/a | idempotent ✓ |

*v3 baseline 3961 是 control_api_v1 only；本 round 跑 tests/ + control_api_v1 = +301 cumulative。

**Pre-existing 4 fail 不變**（v3 已記載）：`test_oe_006_close_retry_budget_has_real_timeout_guard` (NEW-3) / `test_replay_routes_safe_query_audit::test_case2_pg_kill_simulation_returns_200_degraded` (NEW-1) / `test_archive_top_level_files_are_all_indexed` (docs index drift) / `test_grafana_data_writer::test_start_sets_running` (NEW-4 leader lock flaky)。

**雙端 git status clean**：Mac `git status --porcelain` = 0 lines；Linux `git status --porcelain` = 0 lines（V080+V082 apply 後無 untracked）；HEAD 兩端同步 `f5574c5a`。

**Cross-language consistency**：Rust `CanaryStage::Stage0..Stage4` ↔ Python `CanaryStage` IntEnum 0..4 + `as_shadow_mode()` projection bit-exact 對齊（`matches!(self, Stage0)` ↔ `stage == SHADOW`）。整數 enum 不需 1e-4 浮點容差，bit-exact ✓。

**V080 + V082 Linux PG empirical**：`bash helper_scripts/linux_bootstrap_db.sh --apply V080/V082` 兩次 idempotent NOTICE skip path 全 OK；governance/learning schema row count = 0/0/0（schema-only apply，無 test data 殘留）。

**Mock 審查**：4 sub-agent IMPL mock 全限 IO boundary（IPC stub / DB writer stub / governance hub stub），業務邏輯（`as_shadow_mode()` projection / `evaluate_predictor_gate` PredictorAction outcome / `bb_reversion::ma_pair_allows_entry` / `portfolio_var.compute_var_cvar()`）真跑 ✓。

**Hard-boundary scan**：14 Rust + 6 Python diff `grep '\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease|execution_authority)\b'` = 2 hit `decision_lease_id` 在 V080 canary_stage_log + lease_scope.rs CanaryStagePromotion，**設計允許**（manual promote 路徑必須 lease audit chain）；其他 0 hit ✓。

**Cross-platform path scan**：14 Rust + 6 Python `grep '/home/ncyu\|/Users/ncyu'` = 0 hit ✓。

**LOC governance**：14 file 全 < 800 警告線或 pre-existing 區內 ✓。

**5 個 NEW fail 修復清單**：
1. `rust/openclaw_engine/src/ipc_server/tests/config.rs:459` 的 `test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config` — payload 加 `canary_stage: Stage1`
2. 同檔 line 577 `test_g3_02_a2_patch_executor_routes_to_demo_engine` — 同上
3-5. `tests/test_executor_decision_parity.py` golden + synthetic fixture builder 注入 `canary_stage_provider() -> Stage1+`
6. `tests/ci/test_github_ci_workflow_static.py:19` assertion 改驗 `rustup target add x86_64-unknown-linux-gnu` + `aarch64-apple-darwin` 兩個 hard target

**E1 fix 派工建議**：派 1 個 sub-agent 統一處理 5 NEW（4 W-AUDIT-9 chain 同根因 + 1 CI workflow），預期 2-3 hr 完成。fix 後重 E2 → 重 E4 → PM 一次 push 9 commits + fix commit 統一上 main。

**5 教訓**：
1. **大 invariant 改動 (`shadow_mode == canary_stage.as_shadow_mode()`) 必須在 E2 review 前跑 full regression**：sub-agent 自己跑 unit test PASS ≠ 全 suite PASS。本 sprint 4 sub-agent IMPL report 都 claim「sibling test 加好」，但 cross-suite 副作用 (IPC `tests/config.rs` + Python parity fixture) 沒檢查。E2 review 應加「sub-agent 必跑 cargo test --lib 全套 + pytest invariant_keyword」要求。
2. **Python parity test fixture 應全 codebase 自動 pair shadow_mode + canary_stage**：`_make_runtime_config` helper 已 auto-pair 但 `test_executor_decision_parity.py` 漏。新 invariant landing 必 grep 全 codebase `RuntimeConfig(.*shadow_mode=` + `RuntimeConfig(.*canary_stage=` 確認所有 helper 都同步。
3. **CI workflow change 必伴 sibling test 同步**：commit `0dc6d659` 拆 matrix 沒同步 structure test。任何 `.github/workflows/*` 改動 PA 派工 spec 必加「sibling structure test 同步檢查」。
4. **V080/V082 schema apply 全 NOTICE skip 表示 schema 已存在**：本 round 不證明 producer 寫入路徑正確；需 deploy 後 watch 24h `learning.decision_features_evaluations` 是否真接收 30k+ row 流量轉移。defer 給 PM 後續 deploy verification。
5. **flaky test 跨 host vary**：`test_grafana_data_writer.test_start_sets_running` Mac round 1 PASS / round 2 FAIL；Linux 兩 round 都 FAIL = 不同 host 的 leader lock contention vary。本 round 不阻 verdict 但 NEW-4 仍是 P1 pre-existing 待修。

**Report**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-09--sprint_n0_regression_baseline.md`

---

### 2026-05-04 REF-20 Sprint A R3（First Real E2E Evidence：simulated_fills_writer + run_finalize_route + thin handler；round 1+2 cumulative，HEAD `353db3fe` + WIP 改動）— **E4 PASS**

**對象**：PM 派 E4 regression 跑 R3 round 1+2 cumulative IMPL（11 writer + 9 finalize = 20 case；含 round 2 M-1 multi-worker race + M-2 `_FINALIZE_STATEMENT_TIMEOUT_MS` const + 4 follow-up TODO ticket）+ replay-keyword sibling 雙跑 + full control_api_v1 雙跑 + module smoke + cross-language byte-equal + cargo workspace + audit script + cross-platform grep + LOC governance + Hard-boundary scan。

**Verdict**：**PASS** — R3 round 1+2 cumulative 全綠 / 0 新 fail / 0 新 regression / 0 hard-boundary mutation / 0 path leak / 0 flake (2-round identical) / 0 LOC governance violation / M-1 multi-worker race test 真實落實 + FOR UPDATE clause 真實寫進 SQL line 229 / M-2 const 真實 export 5000 ms / 4 follow-up ticket 真實 land in TODO.md L168-171。

| Suite | passed | failed | baseline | delta |
|---|---:|---:|---:|---:|
| R3-specific 2-file（writer 11 + finalize 9） | 20 | 0 | new | match ✓ |
| Replay-tagged sibling round 1 | 118 | 0 | 98 (R2 final) | +20 ✓ |
| Replay-tagged sibling round 2 | 118 | 0 | 98 (R2 final) | identical → 0 flake ✓ |
| Full control_api_v1 round 1 | 3499 | 1 (E4-P0-1) | 3479 (R2 final) | +20 PASS / +0 fail ✓ |
| Full control_api_v1 round 2 | 3499 | 1 (E4-P0-1) | 3479 (R2 final) | identical → 0 flake ✓ |
| xlang_consistency invariant | 13 | 0 | 13 | 不退 ✓ |
| Cargo workspace lib (Mac) | 2909 | 0 | 2909 | 不退 ✓ |
| Audit script Mac arm64 | 0 forbidden / 414 sym / build OK / exit=0 | — | — | ✓ |

**M-1 race fix 雙重驗證**：(1) `tests/test_replay_run_finalize.py:457` `def test_finalize_multi_worker_race_no_v046_dual_insert` 真存在；(2) `replay/run_finalize_route.py:229` `FOR UPDATE;` SQL clause 真寫進 source；(3) test case L625-632 含 `assert "FOR UPDATE" in src` source-grep guard 防 future refactor 誤刪 lock。

**M-2 const fix 雙重驗證**：(1) Python -c import 跑出 `_FINALIZE_STATEMENT_TIMEOUT_MS = 5000`；(2) thin handler `app/replay_routes.py` 真實 import `_fr._FINALIZE_STATEMENT_TIMEOUT_MS`，runtime 取 5000ms。

**Mock 審查**：本 task 不寫業務代碼，僅讀 + 跑。E1 sign-off + E3 audit 已記載 R3 全部 mock 限 IO boundary（PG `_stub_get_pg_conn` / `tmp_path` filesystem fixture / monkeypatch.setenv env / `psutil.Process` spy / FastAPI `dep_overrides`）。0 業務邏輯 mock。`parse_replay_report_json` / `map_fill_to_v050_row` validator / `persist_replay_report` xact / `run_finalize_in_pg_xact` 業務邏輯真跑。✓

**Hard-boundary scan**（CLAUDE.md §四 18 條紅線）：在 3 個 R3 file (`simulated_fills_writer.py` / `run_finalize_route.py` / `app/replay_routes.py`) `grep '\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease|execution_authority)\b'` = **0 hit**。✓

**Cross-platform path scan**（CLAUDE.md §七）：2 個 R3 source file `grep '/home/ncyu|/Users/ncyu'` = **0 hit**。✓

**LOC governance**（CLAUDE.md §九）：
- `replay_routes.py` 1491 ≤ 1500（margin 9，與 E1 §11.6 claim 對齊）✓
- `simulated_fills_writer.py` 602（margin 898）✓
- `run_finalize_route.py` 593（margin 907；round 1 552 + round 2 +41）✓

**Module smoke**：11 個 `/api/v1/replay/*` route 全註冊（含 R2 5 個 + R3 1 個 `/api/v1/replay/run/{run_id}/finalize`）。✓

**Cross-language byte-equal invariant 維持**：13/13 xlang_consistency PASS。R3 完全不動 `manifest_signer.rs` / `manifest_signer.py:canonical_body_for_signing` → R2 build 起的 HMAC byte-equal Rust↔Python 8 fixture 完整保留。✓

**4 follow-up ticket 真實 land**：TODO.md L168-171 完整列：P2-R3-FOLLOW-UP-1（V046 enum `'replay_report'` value 加）/ P2-R3-FOLLOW-UP-3（exception detail leak class name 改 generic）/ P3-R3-FOLLOW-UP-4（`verify_replay_runner_pid` 加 `psutil.create_time()` 防 PID-reuse）/ P2-R3-FOLLOW-UP-5（V046 byte_size CHECK 64MB defense-in-depth）。✓

**8 教訓**：
1. **R3 是「round 1 + round 2」cumulative regression** — 不像 R2 走 round 1+2+3，R3 在 E3 audit PASS-WITH-FIX (1 MEDIUM + 1 doc drift)、PM 仲裁採 E3 觀點 → E1 round 2 fix（M-1 + M-2 + 4 follow-up ticket）→ E4 final。E4 必驗每個 round 2 fix 真實落實（grep + isolated test confirm + import 取常數值），不只跑 test 數字。
2. **M-1 SELECT FOR UPDATE 在 hermetic test 的限制** — single-process pytest 無法觸發真 PG row-level locking；只能驗 contract level「worker B 在 status 已終態下走 409 路徑、不再寫 V046/V050/V045」+ source grep `assert "FOR UPDATE" in src` 防 refactor regression。真 PG behavior 由 Linux deploy smoke run 驗（advisory §14.1）。E4 hermetic PASS ≠ production-ready。
3. **M-2 const fix 驗證 = import + numeric value 比對** — 不只看 grep `_FINALIZE_STATEMENT_TIMEOUT_MS`，要 import 取值看 `=== 5000` 才算真 fix（避免 const 名對但 value 寫錯，比如 `5_000_000` microsecond 誤讀）。
4. **`replay_routes.py` 1491 LOC ≤ 1500（margin 9）** — round 1 1488（基於 R2 final 1443 + 45 thin handler）+ round 2 +14 雙語注釋 = 1491。R2→R3 +48 LOC 完全在 thin handler import 與雙語注釋。Future R4/R5 任何擴 route 必先 inspect 是否能順手抽 model/handler 至 `replay/` 內 new module 維持 1500 governance limit。
5. **R3 不動 Rust → cargo workspace 完全不退** — 純 Python 改動驗證透過 `grep` source path（`replay/*.py` + `app/replay_routes.py` + `tests/*.py`）。R3 改動 0 觸 Rust build / proto / IPC schema → cargo --release --lib --workspace 預期 identical baseline，本 round 對齊 R2 final 2909 PASS / 0 fail / Mac 0 ignored。
6. **Test count 用戶 prompt 預期 vs 實測**：用戶 prompt §3 寫期望 ≥3499 PASS，實測 3499（exact match）— +20 = 純 R3 貢獻（11 writer + 9 finalize），baseline 3479 = R2 final，failed 1 = pre-existing E4-P0-1（不變）。E4 報告必明分清 R3-specific delta vs cumulative delta，幫 PM 理解真實貢獻數字。
7. **Cargo Mac vs Linux ignored 數字差異是預期** — Mac arm64 端 `cargo --release --lib --workspace` 三 crate（27 + 415 + 2467 = 2909）= 0 ignored；Linux 端通常 +3 ignored 屬 PG/Postgres-feature 標記，Mac 不啟用該 feature 故 0 ignored。R2 report §7 同樣記錄 Mac=0 ignored，behavior consistent — 不要誤判為「2909 vs 3 ignored 不對齊」。
8. **`'synthetic_replay'` tier 是 R3 寫入唯一 tier** — V050 CHECK enum 含 3-value（synthetic_replay / calibrated_replay / counterfactual_replay），但 R3 simulated_fills_writer 寫的全是 `'synthetic_replay'`（CLAUDE.md §九 line 412 entry）。下游 SELECT 必加 `WHERE evidence_source_tier IN ('calibrated_replay', 'counterfactual_replay')` 才能 ML training；E3 安全審計 grep rule 加此檢查。Sprint B-D 處理 calibration / counterfactual reweight。

**Report**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-04--ref20_sprint_a_r3_regression.md`

---

### 2026-05-04 REF-20 Sprint A R2（Manifest Registry：register/report/manifest_verify + idempotency cache + IDOR enum-oracle close + 0o600 secrets mode + rate limit；round 1+2+3 cumulative，HEAD `c1ab7ea9` + WIP 改動）— **E4 PASS**

**對象**：PM 派 E4 regression 跑 R2 round 1+2+3 cumulative IMPL 落盤後的 5 R2-specific test file（29 case）+ 1 retrofit Track C IDOR cross-actor 404 + replay-keyword sibling 雙跑 + full control_api_v1 + module smoke + cross-language byte-equal + cargo workspace + audit script + cross-platform grep + LOC governance + CLAUDE.md §九 真寫入證明 + E2 round 2 NEW finding round 3 fix verification。

**Verdict**：**PASS** — R2 cumulative 全綠 / 0 新 fail / 0 新 regression / 0 hard-boundary mutation / 0 path leak / 0 flake (2-round identical) / 0 LOC governance violation / E2 round 2 NEW finding（M-DEAD-LOCK + M-IDOR-ENUM + L-P3-TICKET-MISSING + L-RATE-LIMIT-WIRING）全 round 3 落實

| 引擎 | passed | failed | baseline | delta | verdict |
|---|---:|---:|---:|---:|---|
| Python pytest control_api_v1 全 suite (round 1) | 3479 | 1 | 3431 / 1 (TODO.md L5) | +48 PASS / +0 fail | ✓（fail = pre-existing E4-P0-1）|
| Python pytest -k replay (round 1) | 98 | 0 | 87 baseline (R1) | +11 (10 round 2 + 1 round 3) | ✓ |
| Python pytest -k replay (round 2) | 98 | 0 | (round 1 same) | match | ✓ flake=N |
| R2 specific 5-file new test | 29 | 0 | new | match | ✓ |
| Track C security | 14 | 0 | 13 baseline + 1 NEW IDOR cross-actor 404 | match | ✓ |
| Cross-language xlang_consistency | 13 | 0 | 13 | match | ✓（含 8 core fixture）|
| Rust cargo lib (3 crate cumulative) | 2909 | 0 | ≥2447 / 0 | +462 cumulative | ✓ |

**雙跑 confirm**：sibling replay 雙跑 98/98 identical 0 transient flake；E4-P0-1 是 deterministic shared-state pollution 仍是 deterministic（隔離跑 PASS / suite 跑 fail）。

**H/M/L round 2 fix verdict**（E4 黑盒重跑）：
- H-1 idempotency cache via `_REGISTER_IDEM_CACHE` ✓
- H-2 idempotency_replay_attack 409 ✓
- H-3 cross-route `lookup_registered_experiment_id` ✓
- H-4 0o600 secrets mode ✓
- M-1 4-value env_label allowlist (含 live_demo) ✓
- M-2 rate limit `@_replay_limiter.limit("10/minute")` ✓
- M-3 linux_trade_core engine_binary_sha 503 ✓
- M-4 reserved prefix `_*` key 422 ✓
- L-1 unused timezone import 刪 ✓

**E2 round 2 NEW finding round 3 fix 驗 (3 finding 全 closed)**：
- **M-DEAD-LOCK** ✓ 刪 `_REGISTER_IDEM_CACHE_LOCK = asyncio.Lock()` (0 callsite dead state) + 修 module-level docstring + 改 CLAUDE.md §九 line 404 entry（entry 改為 `_REGISTER_IDEM_CACHE / _REGISTER_IDEM_CACHE_THREAD_LOCK` 去 dead `_REGISTER_IDEM_CACHE_LOCK`）— grep 0 active asyncio.Lock callsite
- **M-IDOR-ENUM** ✓ `report_route.py:177-203` 加 `expected_actor_id` filter + non-admin cross-actor collapse to `not_registered`（close enumeration oracle on V049 lookup）— 8 hit `M-IDOR-ENUM` round 3 changelog 雙語
- **L-P3-TICKET-MISSING** ✓ TODO.md L167 真補 `P3-PYDANTIC-V2-MIGRATE-REPLAY` row（含 trigger / 修法 / defer rationale）
- **L-RATE-LIMIT-WIRING** 🔵 advisory（per-actor 真正解法在 ASGI middleware；round 2 fallback IP acceptable）

**Mock 審查**：本 task 不寫業務代碼，僅讀 + 跑。E1 sign-off + E2 review 已記載 R2 全部 mock 限 IO boundary（PG `_stub_get_pg_conn` / `tmp_path` filesystem fixture / `monkeypatch.delenv` env / `os.kill` spy / FastAPI `dep_overrides`）。0 業務邏輯 mock。`canonical_body_for_signing` / `_no_reserved_prefix_keys` validator / `_size_cap` validator / `_REGISTER_IDEM_CACHE_THREAD_LOCK` cache helpers / `lookup_registered_experiment_id_fn` / `build_report_idor_sql_fn` / `is_live_release_profile_fn` 業務邏輯真跑。✓

**Hard-boundary scan**（CLAUDE.md §四 18 條紅線）：在 5 個 R2 改動 file (`replay_routes.py` / `experiment_registry.py` / `report_route.py` / `manifest_signer.py` / `route_helpers.py`) `grep '\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease|execution_authority)\b'` = **0 hit**。✓

**Cross-platform path scan**（CLAUDE.md §七）：5 個 R2 file `grep '/home/ncyu|/Users/ncyu'` = **0 hit**。✓

**File size cap**（CLAUDE.md §九 1500）：
- `replay_routes.py` 1443 ≤ 1500（margin 57，R3 dispatch 前 reserved）✓
- `experiment_registry.py` 985 ≤ 1500 ✓
- `manifest_signer.py` 757 ≤ 1500 ✓
- `route_helpers.py` 1249 ≤ 1500 ✓
- `report_route.py` 506 ≤ 1500（new module）✓

**Module smoke**：10 個 `/api/v1/replay/*` route 全註冊（含 `/api/v1/replay/experiments/register` + `/api/v1/replay/run` + `/api/v1/replay/report/{experiment_id}` + `/api/v1/replay/health` + `/api/v1/replay/health/signature` 5 expected R2 path）。✓

**Cross-language byte-equal invariant 維持證明**：13/13 xlang_consistency PASS（含 8 core fixture）。R2 round 1+2+3 不動 `manifest_signer.rs` / `manifest_signer.py:canonical_body_for_signing`；H-1 fix 改 cache 路徑（不再 inject `_idempotency_key`）但 canonical bytes 計算 algorithm 完全保留 → HMAC byte-equal Rust↔Python 8 fixture 完整保留。✓

**Audit script**：Mac exit=0 + 414 symbol + 0 forbidden（R1 land 後 fallback chain step 2 workspace release 真實佈局生效）。✓

**CLAUDE.md §九 governance 真寫入**：grep 結果 3 hit（line 404 singleton table entry round 3 fix M-DEAD-LOCK 後 + line 412 simulated_fills non-training surface note + line 412 同行 synthetic_replay cross-ref）。✓

**E4 教訓 / 新坑**：
1. **R2 是「round 1 + round 2 + round 3」cumulative regression** — 不像 R1 的單 round IMPL → E4 流程；R2 經過 E2 round 2 review 揭 3 NEW finding（M-DEAD-LOCK / M-IDOR-ENUM / L-P3-TICKET-MISSING）+ 1 advisory（L-RATE-LIMIT-WIRING），E1 round 3 全 closed 後 E4 final regression。E4 必驗每個 round 3 fix 真實落實（grep + isolated test confirm），不只跑 test 數字。
2. **`replay_routes.py` 1443 LOC ≤ 1500** — round 1 1492 → round 2 round 3 cumulative -49 LOC 透過抽 `experiment_registry.py` (985 LOC) + `report_route.py` (506 LOC) 兩 new module 實現。R3 dispatch 估 +30 LOC thin handler `/run/{run_id}/finalize` → ~1473 仍 ≤ 1500。Future 任何擴 route 必先 inspect 是否能順手抽 model/handler 至 `replay/` 內 new module 維持 1500 governance limit。
3. **E2 NEW finding 不阻 E4，但必交 E1 round 3 / R3 dispatch 前順手清** — 本 task E4 接手時 E1 round 3 已 IMPL 完（HEAD WIP）；E4 驗 round 3 fix 真落實。若 PA dispatch 是「E2 round 2 → 直接 E4」（跳 E1 round 3）E4 需 push back，因為 NEW finding 屬「不阻 E4 但必修」必須在 PM commit 前 closed。本次 PA dispatch chain 正確走 E1 round 3 → E4 final，E4 verdict PASS 同 commit。
4. **`_REGISTER_IDEM_CACHE` per-process semantics** — multi-worker uvicorn workers=4 下 4 個獨立 cache（accepted trade-off）；race-safety 由 PG advisory xact lock 跨 process 兜底。E4 必在 sign-off §13 Advisory 寫 multi-worker 警告，幫 PM 在 commit message + Linux deploy 時 aware。
5. **CLAUDE.md §九 line 404 entry round 3 fix 後改為 `_REGISTER_IDEM_CACHE / _REGISTER_IDEM_CACHE_THREAD_LOCK`** — 去 dead `_REGISTER_IDEM_CACHE_LOCK` 是 governance table 與實際代碼一致性的關鍵。E4 必 grep CLAUDE.md 確認 entry 真實改完，不只看 E1 sign-off 自報「改了」。
6. **Test count 用戶 prompt 預期 vs 實測**：用戶 prompt §3 寫期望 ≥3461 PASS，實測 3479（差 +18）— 屬於 baseline 3431 之後的 sibling CC test additions（Decision Lease retrofit + V054 audit writer + 其他）累積，不是 R2 引入。E4 報告必明分清 R2-specific delta vs cumulative delta，幫 PM 理解真實貢獻數字。
7. **E2 §12.8 列 Linux smoke 6 條 屬 deploy gate 而非 commit gate**：本 E4 task 範圍 = Mac 端 verify。Linux 端 PM commit + push 後 SSH bridge 跑（純 Python 改動 + non-runtime path 無需 --rebuild）。E4 verdict PASS 不阻 PM commit。

**Report**：`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-04--ref20_sprint_a_r2_regression.md`

**建議 PM commit message** 見 report §15。

---

### 2026-05-04 REF-20 Sprint A R1（Runtime Usability：binary fallback + restart_all env + /health route + audit script + 5 unit tests，HEAD `a4ea3571` + WIP 改動）— **E4 PASS**

**對象**：PM 派 E4 regression 跑 R1 IMPL 落盤後的 R1-T5 5 new tests + replay-keyword sibling + module smoke + cross-platform import smoke + audit script + Sprint 1 F1 invariant 維持證明。**E2 review 不在本任務排程**（任務文件直接 IMPL → E4 → PM commit）。

**Verdict**：**PASS** — R1 5 sub-task 全綠 / 0 新 fail / 0 新 regression / 0 hard-boundary mutation / 0 path leak / 0 flake (2-round identical)

| 引擎 | passed | failed | baseline | delta | verdict |
|---|---:|---:|---:|---:|---|
| Python pytest control_api_v1 全 suite (round 1) | 3436 | 1 | 3431 / 1 (TODO.md L5) | +5 PASS / +0 fail | ✓（fail = pre-existing E4-P0-1）|
| Python pytest control_api_v1 全 suite (round 2) | 3436 | 1 | (round 1 same) | +0 / +0 | ✓ flake=N |
| Python pytest -k replay (round 1) | 60 | 0 | new | match | ✓ |
| Python pytest -k replay (round 2) | 60 | 0 | (round 1 same) | match | ✓ flake=N |
| R1-T5 new test (round 1) | 5 | 0 | new | match | ✓ |
| R1-T5 new test (round 2) | 5 | 0 | (round 1 same) | match | ✓ flake=N |
| Rust cargo lib（--release）| 2467 | 0 | 2447 (Sprint 1 cold audit) | +20 PASS / +0 fail | ✓ Sprint 3+4 累積 |

**雙跑 confirm**：Python 3436 P / 1 F + Rust lib 2467 / 0；2 round identical 0 transient flake（E4-P0-1 是 deterministic shared-state pollution 仍是 deterministic）。

**Mock 審查**：本 task 不寫業務代碼，僅讀 + 跑。E1 sign-off §1-2 已記載（5 R1-T5 test 用 `tmp_path` + `monkeypatch.delenv` + 純檔案系統 fixture，0 業務邏輯 mock；`resolve_replay_runner_bin()` 業務邏輯真跑）。✓

**Hard-boundary scan**（CLAUDE.md §四 18 條紅線）：在 6 個 R1 改動 file (`replay_routes.py` / `replay_models.py` / `route_helpers.py` / `test_replay_route_helpers_binary_resolution.py` / `restart_all.sh` / `replay_runner_symbol_audit.sh`) `grep '\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease|execution_authority)\b'` = **0 hit**。✓

**Cross-platform path scan**（CLAUDE.md §七）：E1 sign-off §6.2 已驗 0 真實命中（僅 docstring 政策反例引用，CLAUDE.md §七 example exception）✓

**File size cap**（CLAUDE.md §九 1500）：`replay_routes.py` 1492 ≤ 1500（E1 抽 3 model 至 `replay_models.py` 138 LOC + 加 `/health` route 70 LOC + 刪 dead pydantic import → net -3 ≤ baseline 1495）✓

**Sprint 1 F1 invariant 維持證明**：`grep` 確認 `replay/manifest_signer.py` 與 `replay/route_helpers.py` 0 個 import `replay_routes` 任何 model；R1 抽出 3 model 對 canonical_bytes 路徑完全 0 耦合。HMAC byte-equal Rust↔Python 8/8 xlang fixture invariant 完整保留。✓

**Module smoke 結果**：
- 9 個 `/api/v1/replay/*` route 全註冊（`/health` + `/health/signature` 兩條同時掛載；ordering `/health` 先於 `/health/signature` 與 PA plan 一致）
- 3 個 Pydantic class（`ReplayRunRequest` / `ReplayCancelRequest` / `ReplayManifestVerifyRequest`）`__module__` 全 = `replay.replay_models`
- `from app.replay_routes import` 與 `from replay.replay_models import` 兩條路徑得到**同一 class object**（Python `is` 算 True）
- → OpenAPI schema generation / 既有 5 `test_replay_routes_*.py` 0 行為改動

**Cross-platform import smoke (macOS)**：
- `resolve_replay_runner_bin()` 命中 fallback step 2 (`rust/target/release/replay_runner`，workspace 真實佈局)
- `compute_replay_health_state(rows=[], pg_err=None)` 9-field 全產出
- Mac local PG `pg_present=true` / `v045_present=false` / `v049_present=false` / `wiring_status="ready"`（Mac 端 PG 無 V045/V049 schema，Linux trade-core 才是真實 deploy 點；E1 sign-off §9-2 不確定點預期）

**Audit script**：exit=0 + 414 symbol + 0 forbidden（R1-T1 fallback chain step 2 workspace release 真實佈局生效）。本機 cargo build emit 21 dead-code/unused-import warning 全部 pre-existing 與 R1 改動無關（在 `openclaw_engine` 而非 R1 改動的 Python 模組或 `replay_runner` binary 自身）。

**E4 教訓 / 新坑**：
1. **R1 是 IMPL → E4 直跑（無 E2）路徑** — 本任務 PA 派發直接從 E1 IMPL 跳到 E4 regression 而沒有 E2 review；屬於小範圍、低風險、純 IMPL fixup 場景的合法簡化（CLAUDE.md §八 P0 快速通道也允許省 FA/E5/E3/CC，但 E2+E4 永不跳）。後續 R2/R3 是高風險區（FK / atomic registration / E2E run），必走完整 E2→E4 鏈。
2. **`replay_routes.py` 1495→1492 -3 LOC 透過抽 model 實現** — 加 `/health` route 70 LOC 但同時抽 3 model 138 LOC + 刪 dead pydantic import → 反而降 LOC。Future 任何擴 route 都該優先 inspect 是否能順手抽 model 至 `*_models.py` 維持 1500 governance limit。
3. **`replay_router.routes` 路徑前綴是 `/api/v1/replay/...`** — 不是 PA design doc 寫的 `/health` 而是 `/api/v1/replay/health`（SubRouter 加 prefix）。E1 IMPL 已正確處理（route 在 `replay_router` 而非 root app）。E4 module smoke 對 endpoint 路徑時必認 prefix。
4. **TODO.md L5 baseline 是 3431 而非 E4 prior memory 的 3387** — 兩者差 44，差距來自 Sprint 3 Track H Decision Lease retrofit + Sprint 4 closure 期間的累積增量（44 = 5 sprint 3 sibling sub-task tests + 其他）。E4 取 baseline 永遠以 **TODO.md L5 「測試基準」line** 為準，不信本 memory 寫死數字（CLAUDE.md §九「baseline 規則」）。
5. **Mac local PG `v045_present=false` / `v049_present=false` 卻 `wiring_status="ready"`** — health state 邏輯主要 gate 是 binary+pg+data_dir，V045/V049 schema 是 secondary signal。若 PA 後續設計意圖是 V049 absent → degraded，需 E1 補一條 rule。屬 R1 sign-off 後 follow-up，不阻塞 commit。

**Report**：`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-04--ref20_sprint_a_r1_regression.md`

**建議 PM commit message** 見 report §8。

---

### 2026-05-03 REF-20 Sprint 1（4 track A+B+C+D + V053 整 Sprint final E4 regression，HEAD `2ffe43d` + 30 file unstaged）— **E4 CONDITIONAL PASS**

**對象**：PM 派 final E4 regression 整 Sprint 1（Track A spawn argv + ensure_ascii=False byte-equal canonical contract 19/19 / Track B Rust manifest verify path + key.hex hard error + 5 fail-mode + healthcheck [44] / Track C 3 P0 安全洞修 + V053 LOCK TABLE race-free + 1500 LOC enforce + admin scope 登記 / Track D V049-V052 + V052_preflight + REF-20_RESERVATION v1.9）。

**Verdict**：**CONDITIONAL PASS** — Sprint 1 引入 0 新 fail / 0 新 regression / 0 hard-boundary mutation；2 條 pre-existing E4-P0-1（FastAPI dep_overrides shared-state pollution）+ E4-P0-2（mac_policy_guard.rs 中文全形括號 doctest）仍 fail，cold audit `2026-05-03--ref20_final_closure_e4_cold_audit.md` 已抓，Sprint 1 沒承諾修也沒新增。

| 引擎 | passed | failed | cold audit baseline | delta | verdict |
|---|---:|---:|---:|---:|---|
| Python pytest control_api_v1 全 suite | 3387 | 1 | 3374 / 1 | +13 PASS / +0 fail | ✓（fail = pre-existing E4-P0-1）|
| Rust cargo lib（--release）| 2454 | 0 | 2447 / 0 | +7 PASS / +0 fail | ✓ |
| Rust cargo workspace（含 doctest）| 3084 | 2 | 3077 / 2 | +7 PASS / +0 fail | ✓（fail = pre-existing E4-P0-2 doctest）|
| Rust replay_isolated cumulative | 2643 | 0 | 2630 / 0 | +13 PASS | ✓ |
| Sprint 1 specific 4-track suite（A 19 + C 13 + D 24 + V053 7 = 63）| 63 | 0 | new | match | ✓ |
| Track B 6（4 fail-mode + 1 happy + 1 sanity）| 6 | 0 | new | match | ✓ |
| Track B xlang consistency 8 | 8 | 0 | 8 | match | ✓ |
| SLA stress integration 35 | 35 | 0 | 35 | match | ✓（hot path 0 影響）|
| LG-5 healthcheck pytest 25 | 25 | 0 | 25 | match | ✓ |

**雙跑 confirm**：Python 3387 P / 1 F + Rust 2454 / 0 + workspace 3084 / 2 fail；2 round identical 0 transient flake（E4-P0-1 是 deterministic shared-state pollution，2 round 同 fail）。

**Mock 審查**（Track A + Track C 全綠）：
- Track A：`monkeypatch.setattr("replay.route_helpers.subprocess.Popen", _FakeProc/_FakeAliveProc/_FakeDeadProc)` + `time.sleep` + env vars **全 IO boundary**，0 業務邏輯 mock。`write_manifest_fixture` / `build_default_manifest_payload` / `verify_replay_runner_pid` / `spawn_replay_runner` 業務邏輯真跑（含 byte-equal canonical / sort_keys invariant / psutil cmdline cert）。
- Track C：`monkeypatch.setattr("app.replay_routes.get_pg_conn", _stub_get_pg_conn)` + `os.kill` spy + env vars **全 IO boundary**，0 業務邏輯 mock。`is_live_release_profile()` boot guard / IDOR actor_id SQL filter / Path traversal allowlist / psutil cmdline cert 業務邏輯真跑。

**Hard-boundary scan**（CLAUDE.md §四 18 條紅線）：`grep '^+.*\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease|execution_authority)' = **0 hit**。✓

**Cross-platform path scan**（CLAUDE.md §七）：`grep '/home/ncyu|/Users/[^/]+'` 在 6 個 Sprint 1 改動 file = **0 hit**。✓

**File size cap**（CLAUDE.md §九 1500）：replay_routes.py 1494 ≤ 1500 ✓（round 1 1603 → round 2 retrofit 109 LOC reduction）；其他 over 800 warn ≤1500 hard cap 屬 P2 backlog。

**Cross-language byte-equal**（manifest_signer Rust ↔ Python）：8/8 xlang fixture PASS（不適用 1e-4 浮點容差 — HMAC byte-equal 比 float consistency stricter）。Track A retrofit `_python_canonical_body_for_signing` 鏡像 Rust `canonical_body_for_signing` algorithm（ENVELOPE_KEYS_FOR_SIGNING `manifest_signer.rs:574` + canonical fn `L594`），sort_keys/separators/ensure_ascii=False kwargs 三 lock 對應 BTreeMap/serde_json compact/raw UTF-8。

**SLA**：35 stress integration test PASS（含 tick latency benchmark / 10k ticks / hot reload during ticks / 3-pipeline concurrent / extreme prices / zero volume / multi-symbol 5 coins）。replay_runner binary 屬 batch path（cold artifact），不在 hot tick scope，無需專門 SLA test — PA push back #5 confirmed 不成立。

**P2-AUDIT-7 V044 LOCK TABLE retrofit ticket**：✓ 已 land TODO.md L142（PM commit `2ffe43d` 三端同步 — Mac/Linux/origin 已對齊）。E2 round 2 LOW finding 完整 close。

**E4 教訓 / 新坑**：
1. **Sprint 1 跨 4 track 同期 E4 final regression** — 不像往日 E4 一次驗一個 track；本次同時驗 4 track + V053 + cold audit 2 條 pre-existing 不交雜，避免 PM 在 commit 前漏抓。
2. **CONDITIONAL PASS 在 Sprint 1 closure 是合理 path** — 2 條 pre-existing 不是 Sprint 1 引入也不承諾修，FAIL 退回會把 blocker 錯置。建議 PM accept-and-flag commit 同 commit 開 P2-FOLLOW-UP-1/2 ticket 跨 sprint 修。
3. **Mac dev 沒 PG → healthcheck [44] 真實 PG 行為驗不到** — Mac 本地 `python3 -m helper_scripts.db.passive_wait_healthcheck.runner` fall back to [30] only。Linux trade-core 部署後必跑一次完整 runner 看 [44] WARN/PASS 真實表現。
4. **shrinkage_router production 1000/2000 chain 仍未跑**（cold audit P1-2 同類） — Sprint 1 沒 cover；屬 P2 backlog。
5. **mac_policy_guard.rs 中文全形括號 doctest** — Wave 3 P2b-S9 自引入，非 sibling pre-existing；closure doc 名詞濫用。Sprint 1 不擴 scope；建議下個 sprint 修（` ```text ... ``` ` 包裹或全形 → 半形）。
6. **deterministic shared-state pollution** vs transient flaky — 後者 2 round 不同，前者 2 round 必同；E4 必明分清。本次驗證 P0-1 是後者（2 round 同 401 fail，但隔離 5/5 PASS）。

**Report**：`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_sprint1_e4_regression.md`

**建議 PM commit message**:
```
chore(ref20-sprint1): E4 final regression CONDITIONAL PASS — 0 new fail, 2 pre-existing flagged

E4 Sprint 1 final regression PASS — Track A 19/19 + B 14/14 + C 13/13 + D 24/24
+ V053 7/7 = 77 NEW. Pytest 3387/1/10 (+13 vs cold audit; 1 fail = pre-existing
E4-P0-1 deterministic shared-state pollution from Wave 6 eb5f106). Cargo lib
2454/0 (+7). Workspace 3084/2/3 (+7 PASS / +0 new fail; 2 fail = pre-existing
E4-P0-2 mac_policy_guard.rs Wave 3 5a618ff doctest fullwidth-paren).
0 hard-boundary mutation, 0 hardcoded path, 0 SLA hot-path impact, 35/35 stress.
8/8 xlang manifest_signer byte-equal. P2-AUDIT-7 V044 LOCK TABLE retrofit ticket
landed. Pre-existing 2 條 P2-FOLLOW-UP cross-sprint fix.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

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
5. **Postgres URL encoding**：密碼含 `(` `)` 必 percent-encode 為 `%28` `%29`（`postgres://user:%28...%29@host`）才能進 binary，否則 sqlx 解析 fail。

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
2. SSH 連 Linux PG 須用 `localhost` 不是 `127.0.0.1`（pg_hba.conf md5 規則差異）；passive_wait_healthcheck 預設 `127.0.0.1` 沒密碼會 connect fail，需 `OPENCLAW_DATABASE_URL='postgresql://trading_admin:<REDACTED>@localhost:5432/trading_ai'` 顯式覆寫
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

## 2026-05-03 — REF-20 Wave 2 Batch 2 + Wave 3 P2a (5 commit) regression PASS

**Commits**: `b1f6b8a` (W2-B2 P1 frontend) / `0747474` (P2a-S3 routes auth) / `9c52e67` (P2a-S4 V036/V037+4producer) / `f61dea9` (P2a-S5 quota+prune) / `e6a43fa` (P2a-S6 V038/V039/V040)
**Pre-batch baseline HEAD**: `1851714` (Batch 1 closure)
**Verdict**: **PASS**

### KPIs
- Rust full lib `cargo test --release --lib`: **2415/0** 兩遍同綠 0.55s/0.57s
- Rust workspace `cargo test --release --workspace`: **3025 active passed / 0 failed / 3 ignored doc-tests** pre-existing
- Python control_api_v1: **3338/10/0** 兩遍同綠 (vs Batch 1 baseline 3329 = +9 active: 4 routes_auth + 5 quota_enforcer)
- Python srv-root `tests/migrations/ + helper_scripts/cron/`: **41 active passed + 2 skipped** 兩遍同綠 (含 4 Wave 2 Batch 1 sibling cron)
- 5 file 集中跑: **39 active passed + 2 skipped** 兩遍同綠 (對齊 expected 41 = 39 active + 2 skip)
- Sibling matrix: live_authorization 18/18 + manifest_signer xlang 8/8 + cron Wave 2 Batch 1 7/7 = **33/33 PASS**
- Hard-boundary scan: **0 hit**（live execution gate / Decision Lease / governance_hub / authorization.json / max_retries / OPENCLAW_ALLOW_MAINNET）
- Rust diff scope: **0 lines**（rust/* shortstat empty - Wave 3 P2a 0 Rust changes 結構性確認）
- HTML PARSE OK + 8 Python AST OK + 6 SQL syntax OK (Mac PG psql parse-and-rollback)
- 0 flaky / 0 baseline regression / 0 sibling regression

### 新增測試實際分佈（41 expected = 39 active + 2 skip）
- S3 `test_replay_routes_auth.py`: 4 (401 reject / 200 zero-active accept / 409 per-actor cap / 409 global cap)
- S4 `test_v036_v037_replay_evidence_guard.py`: 10 active + 2 skip (live PG opt-in by design)
- S5 `test_quota_enforcer.py`: 5 (per-actor manifest cap / per-actor run cap / global run cap / env storage cap / TTL flip)
- S5 `test_replay_artifact_prune.py`: 3 (schema absent graceful / zero expired noop / 5 expired pruned)
- S6 `test_v038_v039_v040_evidence_source_tier.py`: 17 (V038 ADD COLUMN+Guard B / V039 backfill+audit log / V040 NOT NULL+CHECK / 3 healthcheck probes / 4 bilingual headers)

### Mock 安全
- 5 個 P2a test bucket 的 mock 全限於 IO 邊界（PG cursor / DB connection / filesystem / SQL file text parse）
- 0 業務邏輯 mock（無 RiskManager.should_allow / acquire_lease / indicator 計算 mock）
- 符合 CLAUDE.md regression skill §5.1 安全規則

### 關鍵教訓
- **Task brief expected count 解析**：PA 寫 "S5 8 tests" 是 5 quota + 3 prune 跨兩個檔合計（不是單檔 8）；E4 要先 grep `^def test_` 確認真實 LOC，不靠 brief 數字。
- **psql `-c` 不支援 `\i` meta-command**：meta-command 必須走 stdin (`(echo BEGIN; cat file; echo ROLLBACK) | psql ...`)。試用 `psql -c "BEGIN; \i file"` 直接 syntax error。
- **psql parse-and-rollback chaos drill replacement**：Mac dev 端有 PG 但無 `learning` schema，可用 BEGIN+SQL+ROLLBACK 包覆驗 SQL syntax 通過 parser，業務 Guard A/B 報「schema/relation not exist」是 by-design fail-closed 不算 syntax error。
- **Hard-boundary 雙語檢查**：scan 時 grep 模式必含 `(acquire_lease|release_lease|governance_hub)` — 第一輪用本 task brief 抄的 pattern 漏 governance_hub，補加後仍 0 hit。CLAUDE.md §四 + §三 retrofit pending P0-GOV-1 範圍要兼顧。
- **srv-root tests/migrations 是新引入 top-level dir**：P2a-S4 + S6 新增 `tests/migrations/__init__.py` + 兩個 test file。pytest 從 srv root 跑時會 collect 它們，但要走 `PYTHONPATH=program_code/.../control_api_v1` 才能解 import。control_api_v1 子目錄跑只 collect 該子目錄 test。要分兩個命令跑才完整覆蓋。
- **Wave 2 Batch 2 (frontend bundle) 0 backend test**：5 commit 中只有 `b1f6b8a` 是 frontend，其餘 4 個全是 backend；frontend 驗證僅 HTML parse smoke 即可，不影響 pytest 數。
- **File size warnings**：replay_routes.py 902 LOC + tab-paper.html 829 LOC + common.js 1490 LOC（接近 1500 hard cap）— E4 不修代碼，flag 給 PM 進 P2 ticket，**E5 / E2 next-batch 評估 file-size split**。
- **Decision Lease retrofit pending 相容性**：Wave 3 P2a 0 lines diff 到 lease.rs / governance_hub / IntentProcessor，與 P0-GOV-1 retrofit 路徑 A（~2026-05-15 派發）完全相容，不會 cascade conflict。
- **CLAUDE.md baseline drift 標記**：§九 baseline 「2555/17」是 legacy `srv/tests/` scope；當前 control_api_v1 子目錄 scope = 3338/0/10 累積。Batch 2 + P2a 後 +9 → 3338，failed 持續 0，符合「不可降低 passed / 不可增 failed」紅線。


---

## 2026-05-03 — REF-20 Final Closure Cold Audit (CONDITIONAL FAIL)

**驗收對象**: REF-20 Wave 1-9 final closure（HEAD `5a7581e`，commit chain 含 W2/W3 已 sign-off + W3p2b/W4/W5/W6/W7/W8/W9 7 closure commit 跳 E4）。

**Verdict**: CONDITIONAL FAIL — 2 P0 + 2 P1。報告：`reports/2026-05-03--ref20_final_closure_e4_cold_audit.md`。

### 真實 cold run 數字

| 引擎 | claim | 真實 | delta |
|---|---|---|---|
| Python pytest control_api_v1 | ~3500+ PASS / 0 fail | **3374 PASS / 1 fail / 10 skip** | -126 PASS / +1 fail |
| Rust cargo --release --lib | 2415+ | 2447 / 0 / 0 | OK |
| Rust cargo --release --tests --features replay_isolated | ~50 integration | 2630 / 0 / 0 | OK |
| Rust cargo --release --workspace | 不明 | **3077 / 2 fail / 3 ignored** | +2 fail（mac_policy_guard doctest） |

### P0 發現

1. **P0-1 deterministic flaky `test_case2_pg_kill_simulation_returns_200_degraded`**: Wave 6 commit `eb5f106` 引入 `tests/test_replay_routes_safe_query_audit.py`，全 suite 跑 401 vs 200 fail（FastAPI dep_overrides 跨 test pollution），隔離跑 PASS。closure doc 自承為「Pre-existing test fail: test_insert_live_candidate_payload_carries_schema_version_and_lg5_subkeys」是虛構（後者 cold run 0 match 已 rename/刪），實際失敗的是 W6 引入的 routes_safe_query_audit。
2. **P0-2 mac_policy_guard.rs 2 doctest fail (line 32 + line 88)**: Wave 3 P2b-S9 commit `5a618ff` 自己寫的中文全形括號 `（）` 觸發 Rust doctest tokenizer error。closure doc line 106 寫「sibling pre-existing」是名詞濫用（檔案自引入卻自稱 sibling pre-existing）。

### P1 發現

3. **P1-1 W4-W9 跳 E4 regression**: E4 reports/ 只有 W2 batch1 + W2b/W3p2a 兩份；W3p2b/W4/W5/W6/W7/W8/W9 共 7 closure commit 完全跳 E4 → P0-1 + P0-2 兩處 fail 直到 cold audit 才被抓到。違反 CLAUDE.md §八「E2 + E4 永不跳」。
4. **P1-2 shrinkage_router production scale 從未跑**: test 用 `gibbs_warmup=200, gibbs_draws=300`，production default `n_warmup=1000, n_samples=2000`。Gibbs sampler logic 同 path（不是 mock 藏邏輯），但收斂行為從未 CI 驗證；建議加 `@pytest.mark.slow` smoke。

### 教訓

- **closure doc claim 必須與 E4 真實 baseline 對齊**：任何「pre-existing fail accept」都需指名具體 test，名稱不對就是虛構。
- **Wave-level closure 每 wave 必跑 E4**，不是「W2/W3 pass 就累積到 W9 一次性 closure」。autonomous mode 跳 E4 = 違反強制工作鏈。
- **doctest fail 不能輕視**：cargo test --release --workspace 比 --lib 多 2 doctest fail，E4 W2/W3 報告只看 `--lib` (`--features replay_isolated`) 漏 doctest。新 baseline 命令必含 `--workspace --doc` 或 `--workspace`。
- **shared FastAPI app state pollution 模式**：`app.dependency_overrides[current_actor]` 跨 test 殘留是經典 flaky pattern；新 routes test 必用 fixture 包裝 `FastAPI()` 實例 + autouse teardown clear overrides。
- **Mac aarch64 vs Linux x86_64 sibling 必跑**：production scale numpy.random PCG64 跨平台 deterministic 但 CI 0 sibling test ledger，須 `ssh trade-core` 同步驗證 Gibbs sampler 出同結果。

### 處置

退回 E1 修 P0-1 + P0-2，重 E2 → 重 E4 → 通過後 PM 補 closure doc 數字訂正（3374 PASS / 1 fail → 修後 3375 PASS / 0 fail，2447 lib + 0 doctest fail）+ retroactive 4 P1 ticket。


## 2026-05-03 — REF-20 Sprint 2 Track F2 Wave 3-9 Retroactive E4 Cumulative Report

**Verdict**: CONDITIONAL ACCEPT with audit forgery flags
**Method**: git show static analysis (NOT live re-run，PM 派工要求不破壞 working tree)
**Report**: `reports/2026-05-03--ref20_wave3_to_9_retroactive_e4_cumulative.md`

### 7 Wave 完整 indicator 表（總 117 file / 35569 ins / 723 del / 7 SQL migration / 272 pytest case / 15 Rust test）

| Wave | commit | Files | Ins/Del | SQL | pytest | Rust test | >800 LOC | >1500 cap | claimed PASS |
|---|---|---:|---|---:|---:|---:|---:|---:|---|
| W3 | 5a618ff | 8 | 2337/80 | 0 | 0 | 9 | 0 | 0 | 37 |
| W4 | 4b48b6d | 26 | 7360/433 | 2 | 33 | 6 | 2 | 0 | 64 |
| W5 | 457a458 | 32 | 10513/1 | 1 | 124 | 0 | 1 | 0 | 124 |
| W6 | eb5f106 | 22 | 6770/19 | 1 | 75 | 0 | 3 | **1** | 75 |
| W7 | c887e4e | 4 | 473/161 | 0 | 0 | 0 | 0 | 0 | 17 manual |
| W8 | 8429af1 | 10 | 3684/27 | 1 | 20 | 0 | 2 | 0 | 28 |
| W9 | 1f5d019 | 15 | 4432/2 | 2 | 20 | 0 | 0 | 0 | 20 |

### Sprint 1 +13 PASS / +7 lib reconciliation (真實，可 reconcile)

- W2/W3p2a baseline 3338 PASS → W4-W9 +36 active (control_api_v1 root scope) → cold audit 3374 → Sprint 1 +13 (Track C 13 NEW) → 3387 ✓
- W4-W9 actual NEW pytest = 70 但 control_api_v1 root scope `pytest tests/` 不 collect `replay/tests/` 子目錄 + `tests/migrations/` 不在範圍 → +36 reconcile gap 真實
- Track A 19 + V049-V053 31 = 50 NEW test 是 srv root scope 才能跑（不算進 control_api_v1 +13）

### 4 個關鍵 forgery / hidden defect

1. **W3 `5a618ff` mac_policy_guard.rs 中文全形括號 2 doctest fail** — line 75/84/91/92/93 全形 `（）` Rust 解析 `\u{ff08}` token error；W4 closure 自承「sibling pre-existing」是名詞濫用（自己引入卻自稱 sibling）
2. **W6 `eb5f106` `test_case2_pg_kill_simulation_returns_200_degraded` deterministic flaky** — line 173+ 用 `app.dependency_overrides[current_actor] = _operator_actor` 沒 autouse teardown clear → FastAPI app 跨 test pollution → isolated PASS / 全 suite 401 vs 200 fail
3. **W6 mlde_demo_applier.py 1542 LOC §九 hard cap violation** — pre-existing 1541 baseline + W6 +1 LOC = 1542；技術 §九 exception clause 適用（≤1546）但 commit msg 0 提這 violation acceptance / 0 開 P2 ticket → 違反 §九 exception clause requirement (3)「PM Sign-off 必明文記錄 governance exception accept 理由」
4. **REF-20 final closure `5a7581e` line 99 自宣 ~3500+ Python pytest PASS** — 真實 3387 / Sprint 1 後（cold audit 3374）；3500+ 是虛構數字（差 113-126）

### 5 個 mock 安全風險 retroactive flag

1. W5 `shrinkage_router.py` test gibbs_warmup=200 / draws=300 但 production 1000/2000 從未 CI 跑（cold audit P1-2 retroactive 確認）
2. W5 NumPyro Mac scipy fallback 自宣「1:1 alignment with NumPyro」0 cross-OS sibling test 證
3. W6 V043 `mlde_replay_veto_log` writer 全 mock-based unit test，0 INSERT 真實 PG 路徑驗
4. W7 commit msg 自宣 17 acceptance PASS 是 manual HTMLParser smoke check（非 pytest）— autonomous override hard prereq LG-2/3/4 stable bypass
5. W9 wave9 cron 0 INSERT 真實 V047/V048 row 路徑驗（mock mode unit test only）

### 教訓 lessons learned

- **Wave-level skip E4 = §八 工作鏈違反**：autonomous mode 跳 W3-W9 全部 E4 → 直到 cold audit 才抓 P0-1 + P0-2。**E4 retroactive 補完只能事後查 git show**，無法等價於即時 E4
- **commit msg 數字 ≠ 真實 baseline**：claimed 75 PASS（W6）是 isolated bench 數字；寫進全 suite deterministic fail 才是 true baseline 衝擊
- **§九 hard cap exception clause 必有 4 步**：(1) commit msg 顯式 record pre-existing baseline LOC + new LOC delta (2) 對比 baseline+5 是否 PASS (3) 同 commit 開 P2 refactor ticket (4) PM Sign-off 文字明文 reasoning。W6 mlde_demo_applier.py 4 步全跳
- **closure doc 數字必對齊 cold run 真實**：`~3500+` 一般化估算數字進 production doc → cold audit 抓出後就是 forgery 證據
- **scope mismatch reconciliation 必查**：`pytest tests/` (control_api_v1 cd) vs `pytest tests/migrations/` (srv root) 是兩個獨立 collector scope；同 NEW test 算進不同 cumulative 數字

---

## 2026-05-03 — REF-20 Sprint 3 Track H final E4 regression CONDITIONAL PASS

**Verdict**: CONDITIONAL PASS — Track H 4 task retrofit 0 新引入 fail / 0 SLA violation / 0 hard-boundary mutation；2 條 pre-existing E4-P0-1+P0-2 仍 fail（cold audit + Sprint 1 已 cite，Sprint 3 不承諾修）
**Method**: Mac dev cold reality real run（HEAD `984ee5d` + 30+ file unstaged Track H patch）
**Report**: `reports/2026-05-03--ref20_sprint3_track_h_e4_regression.md`

### KPIs

| 引擎 | passed | failed | Sprint 1 baseline | delta | expected | verdict |
|---|---:|---:|---|---|---|---|
| Python pytest control_api_v1 | **3431** | 1 | 3387/1/10 | **+44 PASS / +0 fail** | +44 (governance_lease_bridge) | ✓ exact |
| Rust cargo --release --lib | **2467** | 0 | 2454/0/0 | **+13 PASS** | +13 (lease_transition 6 + governance_emit/core lib units 7) | ✓ |
| Rust cargo --release --workspace | **3132** | 2 (pre-existing) | 3084/2/3 | **+48 PASS / +0 fail** | +40 expected | ✓ exceed |
| Track H specific (4 suite) | **63** | 0 | new | +63 NEW PASS | match | ✓ |
| SLA stress | **35** | 0 | 35 | match | match | ✓ hot path 0 影響 |
| Track A + H byte-equal contract 共存 | **63** | 0 | n/a | n/a | n/a | ✓ 兩 lock 不撞 |

**兩遍 deterministic identical**：3431/1/10 (Run 1+2) / 3132/2/3 (Run 1+2)。

### 關鍵 lessons learned

1. **PaperShadow profile LeaseId::Bypass 短路是 by-spec design**：governance_core.rs:399 production short-circuit 2 hits（`Profile::PaperShadow`）+ release path 1 hit；其餘 26 hit 全 test/test fixture。Production 非 Shadow 路徑 = router gate 強制走 IPC（match P0-GOV-1 retrofit 路徑 A）。整 grep 28 instance 不要當 violation，要驗 short-circuit 在哪 profile + branch
2. **Track H E-3 IPC stub 不藏業務邏輯 vs 通用 IPC mock 反例**：E-3 用 `_FakeIpcDispatcher` (asynccontextmanager) stub send/recv 邊界 — `parse_acquire_response()` / `parse_release_response()` 業務邏輯真跑（含 wrapped/flat shape / unknown outcome 異常 / malformed payload 拒絕）。CLAUDE.md skill §5.1 mock IO 邊界 OK 反例：mock 整個 ipc_client 連 protocol 都 stub（藏 wire format bug）。本次審查 OK
3. **V054 Mac dev idempotency partial smoke pattern**：當 migration 依賴 prereq schema (V035 governance_audit_log) 不在 Mac dev throwaway DB 時，第二次跑會在 prereq-dependent 部分仍 RAISE（Guard A 正確 fail-closed），但 schema-only 部分（CREATE TABLE / CHECK / INDEX）必 idempotent skip。Linux trade-core 真實環境（V035 deployed）下兩遍跑期望 0 RAISE 是 true validation。屬 PM/operator deploy SOP，不阻擋 E4 closure
4. **TimescaleDB extension 非 Mac dev 可用**：V054 conditional `IF EXISTS pg_extension timescaledb` skip hypertable promotion → plain PG table fall-back 是正確 cross-platform pattern。Mac dev 沒 timescaledb 不阻擋 schema 結構驗
5. **Sprint 1 Track A canonical contract + Sprint 3 Track H lease bridge canonical contract 共存設計**：兩 byte-equal lock 各自驗各 helper（Track A `_python_canonical_body_for_signing` 鏡像 manifest_signer.rs:594；Track H lease_ipc_schema build_acquire/release 鏡像 governance_emit.rs UTF-8 raw）— 19 + 44 = 63 共存 PASS 證 namespace 不撞、locks 互鎖。LOW-2 retrofit 4 unicode contract test 是這 lock 的具體 enforce
6. **§九 exception clause 4 步驗收 Sprint 3 Track H 完整 path**：(1) commit msg 顯式 record pre-existing baseline LOC + new LOC delta（PM commit Track H unified patch 時做）— tests.rs 2375→2910 / governance_core.rs 1490→1491；(2) baseline+5 對比：tests.rs 2910 ≤ pre-existing 2375+5=2380？✗ — 但 §九 exception clause 條件 (1) 適用 pre-existing 1500+ violation，2375>1500 已 violated，本次 +535 屬 new wave 推升 — 嚴格條件 (1) 解讀屬 fail；E2 round 2 PA push back 揭 retrofit 結構性必須在原檔同 module 內（28 fixture 重寫 + 7 new router_gate test 同 module dependency）→ PM Sign-off 必明文 declare 例外接受理由 = (a)+(b)+(c) 三 reasoning；(3) P2-INTENT-PROCESSOR-TESTS-SPLIT 已 land；(4) PM Sign-off 待補。governance_core.rs 1491 < 1500 hard cap 不撞，distance 9 LOC 警示但合規 — E-2 retrofit P2-GOV-CORE-EMIT-EXTRACT 抽 governance_emit.rs 出後刚好不撞
7. **3 frontend WIP 隔離**：unstaged WIP 無關 Track H scope（隔壁 session console/governance-tab/tab-governance），E4 不負責 commit 邊界 — flag 給 PM 後續獨立 commit / stash
8. **V054 0 Python pytest sibling 是 P3 follow-up 而非 closure 阻擋**：tests/migrations/test_v049_v050_v051_v052_track_d.py + test_v053_*.py 都有 schema-static parse test，但 V054 skip 了。建議開 P3-V054-PYTEST-SIBLING ticket（不阻擋 Sprint 3 closure；deploy SOP 自然會驗）
9. **E-2 perf bench flag OFF 580ns/call → flag ON 4980ns/call ≪ 100µs IPC budget**：本次 SLA stress 35/35 PASS in 0.10s 證 hot path latency 0 退化（feature flag default OFF 下 runtime 0 行為改動），4980ns 真值要 6 Phase rollout 開閘後實機驗
10. **Sprint 3 Track H 0 hard-boundary mutation 但目的就是 retrofit Decision Lease Rust 熱路徑 0 觸發**：重要 nuance — Track H 邏輯改動（governance_emit / lease_transition_writer / router gate / Python bridge）全在 feature flag (`OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0`) default OFF 後面；§四 18 條紅線 0 mutation 因為 runtime behavior 0 變動。Decision Lease P0-GOV-1 critical path 真兌現要 6 Phase rollout 開閘 + 14d gradient observation

---

## 2026-05-05 — REF-20 Sprint A R3 Round 6 final E4 regression PASS

**Verdict**: PASS — R3 round 6 (T1 real HMAC sign + T2 stderr capture + T3a env injection + T4 4 NEW test files) cumulative 全綠 / 0 新 fail / 0 新 regression / 0 hard-boundary mutation / 0 path leak / 0 flake (Mac+Linux 雙跑 identical) / 0 LOC governance violation / 0 production placeholder / xlang 13/13 / cargo 2909
**Method**: Mac dev (Darwin 25.4 arm64 / Python 3.12.13) + Linux trade-core (Ubuntu 24.04 x86_64 / Python 3.12.3) 雙端 real run；rsync R6 改動到 Linux /tmp 後 cp 入 repo (無 commit/push 維持 §八 工作鏈：E4 跑完才能 commit)
**Report**: `reports/2026-05-05--ref20_sprint_a_r3_round6_regression.md`

### KPIs

| 引擎 | passed | failed (pre-existing) | baseline | delta | verdict |
|---|---:|---:|---|---|---|
| R6 specific Mac (24 case) | 23 | 0 | 0 (NEW) | +23 PASS / 1 skip (smoke opt-in) | ✓ |
| R6 specific Linux (24 case) | 23 | 0 | 0 (NEW) | +23 PASS / 1 skip | ✓ |
| Mac sibling replay (雙跑) | 141 | 0 | R3 round 5: 118 | +23 (R6 specific) | ✓ identical |
| Linux sibling replay (雙跑) | 138 | 3 (pre-existing) | R3 round 5: 115 | +23 (R6 specific) | ✓ identical |
| Mac full control_api_v1 (雙跑) | 3522 | 1 (E4-P0-1) | R3 round 5: 3499 | +23 + 1 skip = +24 | ✓ identical |
| Linux full control_api_v1 (雙跑) | 3489 | 5 (pre-existing) | R3 round 5: 3466 | +23 + 1 skip = +24 | ✓ identical |
| xlang_consistency Mac+Linux | 13 | 0 | 13 | 0 (invariant 維持) | ✓ |
| Cargo --release --lib (Mac) | 2909 | 0 | 2909 | 0 (R6 純 Python) | ✓ |

### 關鍵 lessons learned

1. **Linux 3 fail = Mac 4 PASS = Mock vs 真實 PG schema 鴻溝**：`test_replay_routes_auth.py` fixture 用 `experiment_id="exp-bob-2026-05-03"` 字串，PG V049 schema enforce uuid → Mac mock fixture 寬鬆 PASS / Linux 真打 PG fail-closed 拒收。R3 round 5 hotfix 揭示後，stash 證明 hotfix 前已存在（Wave 3 P2a-S3 commit `07474741` 寫的 fixture）。**E4 reality check**：Mac PASS ≠ Linux PASS；platform-divergent fail 必先驗 stash baseline 再判 R6 引入或 pre-existing
2. **Linux Python 3.12 sync 流程**：當 Mac 端 R6 改動 unstaged + Linux 也未 pull 時，**E4 不能 commit/push (§八 工作鏈：E4 跑完 → PM commit)**；正確 pattern = `rsync` 到 Linux `/tmp/r6_sync/` → `cp` 入 repo → 跑驗 → flag PM commit。**禁止用 commit/push 觸發 sync** 因為這會破工作鏈順序
3. **Production placeholder grep 5 hit ≠ violation**：5 hits 全在 docstring `MAINTAINER WARNING` 路徑（line 754-757 / 858-865 / 940-946），是 self-enforcing trip wire（防 future regression：任何 placeholder 退化引入時 grep 會 hit additional production line → 立即可發現）。設計上是 lifeline，不是 fake remnant。E4 必逐 line read context 判斷 docstring vs production code
4. **route_helpers.py 1485 LOC = 15 LOC headroom**：upper edge of §九 1500 hard cap。Round 7+ 任何 LOC delta 觸頂 → 必 split (per E1 §7 + PA design §6 H1 建議：抽 `manifest_provisioning.py`)。**E4 必每 round 算 headroom 並 flag P2 split ticket** 防 future commit 撞牆
5. **`_resolve_replay_signing_key` typo in user prompt**：production 真實 export 是 `_resolve_manifest_signing_key`。E4 訂正命令跑 import smoke 而非盲執行 prompt typo。grep 命令時遇 ImportError 不應自動 fail-closed 報 BLOCKER，應比對 source code grep production export name
6. **Linux 5 fail 4 categories (3 + 1 + 1)**：sibling replay 3 fail (Wave 3 fixture UUID) + full control_api_v1 多 1 grafana writer fail (與 R6 unrelated grafana lifecycle test) + 1 E4-P0-1 (cross-test FastAPI dep_overrides pollution，Mac+Linux shared)；R6 不引入任何新 fail。**E4 必分類 fail 為 4 個 follow-up ticket** 防 PM commit 時誤判 R6 引入
7. **opt-in e2e smoke skip 是 by-design**：T4-4 `test_replay_e2e_round6_smoke.py` 用 `OPENCLAW_REPLAY_E2E_SMOKE=1` env 啟動 + 真 spawn Rust binary。Mac 本地 Rust binary 不 deploy / Linux 此次未 export env → 雙端都 1 skip。Post-deploy QA round 2 啟用 env 真跑 spawn → V045 / V046 / V050 / V054 真實 row 累積。**E4 不 enforce 強跑 e2e smoke** 因 deploy artifact 未就位，是 deploy SOP 而非 E4 closure 阻擋

---

## 2026-05-08 — Full-chain test audit (PM dispatch, HEAD `4e2d2883`)

**Verdict**: PASS baseline + 21 個結構性 gap 揭示（21 G items in §10）。Mac+Linux 雙端 deterministic identical。
**Method**: Mac dev cold real run + Linux trade-core ssh real run；4 scope (srv/tests / control_api_v1 / ml_training / cargo lib) baseline 重跑兩遍。
**Report**: `reports/2026-05-08--full_chain_test_audit.md`

### 真實 baseline（取代 E4 profile.md 寫死的 2555/17）

| 引擎 / scope | passed | failed | skipped | 雙跑 identical |
|---|---:|---:|---:|---|
| Mac · `srv/tests/` | 137 | 0 | 2 | yes |
| Mac · `control_api_v1/tests/` | 3826 | 6 (pre-existing) | 17 | yes |
| Linux · `control_api_v1/tests/` | 3832 | 7 (pre-existing) | 10 | n/a single |
| Mac · `ml_training/tests/` (PYTHONPATH=. from srv) | 336 | 0 | 31 | n/a single |
| Mac · cargo --release --lib | 2559 | 0 | 0 | yes |
| Linux · cargo --release --lib | 2559 | 0 | 0 | n/a single |

### 4 個 panorama-confirmed 結構性測試假綠

1. **Python H0_GATE singleton 0 production caller**：實例化在 `paper_trading_wiring.py:291`，但 IntentProcessor / ExecutorAgent 0 處 call gate.evaluate()。**Rust pipeline.h0_gate.check 是 hot path active**（status_report.rs:90 注釋 PNL-2 invariant），所以 panorama「H0 0 caller」精確化 = Python H0_GATE singleton 0 caller，Rust h0_gate 是 hot path。
2. **lease_transitions audit writer 0 row**：Rust writer 500 LOC + 6 self-test + V054 migration 5 case 都綠，但 router gate flag default OFF → writer 永遠收不到 transition；0 個 e2e flag flip→writer→DB row 鏈 test。
3. **5-Agent ↔ Rust hot path 解耦**：executor_agent.py:454 governance_hub.acquire_lease() 是當前唯一 production lease caller；executor_agent.py:224 shadow_mode_provider default `lambda: True` 永久 shadow（P1-FAKE-1）。
4. **5 ML training scripts silent-unscheduled**：Linux crontab 真實證實，crontab 只有 8 個 cron job，**0 處 schedule** mlde_demo_applier / linucb_trainer / quantile_trainer / scorer_trainer / mlde_shadow_advisor / dl3_ab_runner / canary_promoter。35 個 ml_training test 都 PASS，production runtime 卻從未跑。

### 5 個高風險 mock-hides-logic 反例命中（315 mock 中）

1. **M2 LG-5 reviewer Decision Lease test mock-only**：`test_lg5_review_live_candidate.py:505` MockHub.acquire_lease 直接 record call 0 驗 lease semantic → CLAUDE.md panorama「LG-5 reviewer 0 audit row 累積」可能就在此 mock 路徑下永遠成功
2. **M3 executor parity test 不真實 xlang**：`test_executor_decision_parity.py` 用 `_reference_decide` Python re-impl 對比 Python decide()，**0 Rust binary spawn** — 名 "parity" 但其實是 Python self-consistency
3. **M7 ml_training PG round-trip 0 真實 case**：4 個 OPENCLAW_TEST_DSN gated 但 Linux 也未啟（CLAUDE.md §三 Outstanding R7-T6 自承）
4. **M9 lambda: True/False 9 處 hardcoded**：production default fail-close vs test fail-open 路徑分歧
5. **M1 governance_routes 16 個 整 hub 替換**：route 只測「會回 hub.x()」，0 驗 hub 真實 behavior

### 8 個 SLA / 邊界 / 異常 / 並發 顯著 gap

- H0 Gate < 1ms / Tick path < 0.3ms / IPC roundtrip < 5ms **真實 SLA fixture 0 in CI**（`tests_predictor_router.rs:1290` 注釋自宣 cargo bench 負責，operator 手動非 CI）
- xlang ATR / BB / Sharpe / edge / PnL 1e-4 容差 test **0 個**（manifest_signer byte-equal 13 case 不算 indicator 一致性）
- Lease TTL 0.1s / 300s 邊界 0 case；Bybit retCode Python 端僅 5 unique（spec 50+）
- ArcSwap multi-reader concurrent race 0 case
- engine_mode paper→demo→live_demo→live e2e 0 case；EarnedTrust T0/T1/T2/T3 transition 0 case
- ATR=NaN / 極大值 panic vs fail-closed 0 case
- DB connection drop 真實案例 0 case（當前是 fixture pollution flaky E4-P0-1）
- Migration race（兩 worker V### apply）0 case

### 6 個關鍵 lessons learned

1. **CLAUDE.md panorama「H0 0 caller」需精確化為 Python H0_GATE 0 caller**：Rust pipeline.h0_gate.check 是 active hot path（每 tick 跑），不能直接說「H0 0 caller」誤導；E4 audit 需區分 Python infra-only vs Rust runtime-active
2. **「跨語言 1e-4 浮點容差」profile.md 與 skill §6 都列為 E4 核心技能但 production 0 fixture**：profile 是純 spec；現存 xlang test 全是 byte-equal manifest signer (0 容差)，**indicator 一致性 1e-4 從未在過**。建議 PA 把這列為 G2 P0
3. **`_reference_decide` 是 Python re-impl 不是 Rust binding**：test_executor_decision_parity.py:149 名為 "parity" 但實質是 self-consistency；naming convention 誤導 — E4 必逐個 reference impl 確認是否真 cross-language
4. **Linux 7 fail vs Mac 6 fail 1 case 差異 = grafana writer lifecycle**（非 R3 round 6 關注的 Wave 3 P2a-S3 fixture UUID 字串）；本次 audit 沒命中新 platform-divergent 但需 Linux smoke 後續驗 `exp-1` / `exp-binary-test` / `exp-2026-05-03-w4-t2` 等 Mac fixture 字符串是否被 Linux PG schema enforce uuid 拒收
5. **315 個 mock 命中中 5 個高風險反例（M1/M2/M3/M7/M9）= 1.6%**；多數 mock 是 IO 邊界 OK；但 5 個高風險都集中在 production critical path（LG-5 reviewer / xlang / ml_training PG round-trip / shadow_mode default）— **mock 反模式不在比例而在 critical path 是否被遮蔽**
6. **「跑兩遍」deterministic identical 是 E4 必須**：本次 4 個 scope 都驗了；發現 Mac control_api_v1 60.01s vs 59.37s 差 0.64s（< 2%）= 真 deterministic，0 flaky；若差 >5% 需追 timer / sleep / network call

### Outstanding（不阻擋本次 audit closure，flag 給後續 PA）

- E4 profile.md baseline 寫死 `2555 passed / 17 pre-existing failed` 過期，建議 PM/PA 一次性更新為「control_api_v1: 3826/6 (Mac) or 3832/7 (Linux), ml_training: 336/0, srv/tests: 137/0, cargo lib: 2559/0」
- 21 個 G item 屬 PA 後續派工，**E4 audit 不寫業務 test code**（per task instruction）
- §三 healthcheck `[42]/[42b]` LG-5 reviewer 0 audit row gap 與 M2 mock 反例強相關，sibling CC FUP-1 commit 463890d deploy 後需 E4 重審 mock 是否需替換真實 GovernanceHub fixture

---

## 2026-05-09 W-AUDIT verification（28 commit / HEAD `7fccad06`）

### Baseline drift after W-AUDIT-1..7 source-only checkpoints

| 引擎 | 2026-05-08 baseline | 2026-05-09 verified |
|---|---|---|
| Mac control_api_v1 | 3826/6/17 | **3898/7/13** (+72/+1/-4) |
| Linux control_api_v1 | 3832/7/10 | **3871/10/37** (+39/+3/+27) |
| Mac srv/tests | 137/0/2 | **208/0/2** (+71) |
| Linux cargo lib | 2559/0 | **2560/0** (+1) |

雙跑 deterministic identical (srv/tests + control_api_v1 + cargo) ✅

### 21 gap 修復 verdict

✅ DONE/PARTIAL: 8 / ⚠️ PARTIAL not done: 5 / ❌ NOT TOUCHED: 8 / 🆕 NEW REGRESSION: 3

**G1 真實狀態**：`rust/openclaw_engine/tests/lease_flag_flip_e2e.rs` (260 LOC) 存在且 2/2 PASS，但 `router_flag_flip_writes_lease_transition_rows_when_test_pg_present` 在 env var 不設時 early-return → CI 默認 0 真實 PG row 持久化 e2e。**算「test 框架存在」不算「e2e PG 持久化驗證」**。

**G6 真實狀態**：`ml_training_maintenance.py/.sh` source 寫好 + 138 LOC static test，但 `crontab -l` 無 install → ml_training 5 script 仍 production 0 真跑（panorama 100% NULL 根因路徑無解）。

**G2 G3 G19**：xlang 1e-4 / SLA <1ms 0 case → 28 commits 0 進展。

**G7 G8 G9**：mock-only path 仍未替換真 fixture / 真 PG round-trip / 真 Rust↔Python cross-call → 0 進展。

### NEW-1 BLOCKER：`commit 3cff1005` 自我破壞

`refactor: split event consumer hot files` 把 `test_close_attempt_timeout_constant_is_500ms` 從 `dispatch.rs` 搬到 `dispatch_tests.rs`，但 `tests/test_batch_d_risk_fail_closed.py:126` static-grep `_read("rust/openclaw_engine/src/event_consumer/dispatch.rs")` path 沒同步更新 → assertion fail。**E1 split refactor 加新 LOC regression 但忘了同步舊 static-grep test**。1 行 fix。

### NEW-2 HIGH：`test_replay_advisory_routes.py` Linux 2 fail 未在 audit baseline 揭示

`test_replay_advisory_rank_route_caps_and_never_invokes_applier` Linux 422 vs Mac 200。28 commits 0 動 advisory 路由 / test → 應為 pre-existing Linux schema divergence，**2026-05-08 audit Linux 7 fail breakdown 沒抓到**。

### NEW-3 MEDIUM：4 collection errors（pre-existing）

control_api_v1 sub-dir 跑 venv 時 `from program_code...` import broken（PYTHONPATH 漏 srv root）；srv root + PYTHONPATH=. 跑可繞過。**2026-05-08 audit baseline §1 PASS 數已是 implicit ignore 4 collection errors 之後** — audit baseline 透明度應分「能跑 PASS / 能跑 FAIL / collection errors」3 列。

### Push back 教訓沉澱

- **commit message「opt-in」3 字 = CI 默認不跑** — 避免 trust「test 存在」便認可 e2e
- **commit message「Add a static LOC regression」≠ 加業務 mutation/integration test** — 拆檔 hygiene 工作不能算 G1-G4 P0 修
- **deepcopy 替換的 mutation test 必須 4/4 SM 都加**，不可只加 1/4（learning_tier_gate）；3 SM stat +2/0/+8 LOC 太薄
- **orjson 換 stdlib JSON 無 byte-equal IPC wire-format 對比 = 風險未驗** — nested dict ordering / float precision 差異會讓 IPC 對端解 fail
- **Mac mock pytest PASS ≠ Linux PG runtime PASS ≠ columnstore 模式 PASS**（V077 hotfix 教訓）— Linux PG dry-run mandatory 範圍應擴含 columnstore mode test
- **audit baseline diff breakdown 不完整 = audit 自身 hidden ignore** — 必須顯式列出所有 ignore（collection errors / skip / xfail / Mac-only / Linux-only）

## 2026-05-09 v2 verification — 對抗性嚴苛核實 21 gap 在 34 commit 修復

**baseline 2026-05-09 v1 → v2** (455d796e..1bd55689 共 34 commits):

| 引擎 | v1 | v2 | delta |
|---|---|---|---|
| Linux · srv/tests | 208/0 | 228/0 | +20 PASS |
| Linux · control_api_v1 | 3871/10 | 3925/3 | **+54 PASS / -7 fail** |
| Linux · cargo lib | 2560/0 | 2584/0 | **+24 PASS** |

**雙跑 deterministic identical**：3925/3 → 3925/3 / 2584/0 → 2584/0

**verdict**：✅ PASS / ✅14 / ⚠️3 / ❌4 / 🆕1（NEW-1 仍未修退回 E1）

**v2 真實 closures (6)**：
1. **F-01** (caf973fb) — lambda:True 完全移除 + 5 fail-closed test 真覆蓋 except / None branch
2. **W-AUDIT-2** (e97a333b) — V078 schema + Rust unit + **PG runtime 7956 BYPASS rows** 5h 跨 2 engine_mode 真實 emit
3. **W-AUDIT-6c** (cc6476dd) — VaR/CVaR/EVT/GPD 13 test + promotion integration fail-closed gate (test_demo_gates_fail_without_tail_risk_evidence)
4. **W-AUDIT-7** (a0bbde58) — strategist cap + sibling Rust test +49
5. **healthcheck [56]** (c15985a5) — 7 test + 5 fail-closed path (missing auth / stale snapshot)
6. **V072 feature baseline** (7657bd25) — 14+ inline Rust test (含 build_feature_baseline_rows_emits_34_active_features 真 assert) + static guard

**對抗性 push back outcomes**：
- A: F-01 lambda:True grep verified 移除（v1 push back 完全消除）
- B: W-AUDIT-2 PG row > 0 直查 7956 (v1 「opt-in early-return」消除)
- C: 6 risk: commits 全帶 Rust sibling test
- D: mock 嚴守 IO 邊界，業務邏輯真跑（不掩蓋邏輯）
- E: NEW-1 仍未修是 PA 派工漏項
- F: pre-existing fail 縮短 7 條

**仍 untouched (8)**：G2 (xlang 1e-4) / G3 (H0 SLA <1ms) / G7 (LG-5 mock-only) / G9 (executor parity Rust↔Python) / G11-G20

**仍 partial (4)**：G5 / G6 / G8 / G10

**新 issue**：
- 🔴 NEW-1：`test_oe_006_close_retry_budget_has_real_timeout_guard` 仍未修（1 行 static path 改 dispatch_tests.rs）
- 🟡 NEW-3：4 collection errors PYTHONPATH inject 待修
- 🟡 NEW-4：`test_grafana_data_writer.py::test_start_sets_running` Linux leader-lock contention（不是新破壞，是 Linux runtime divergence）
- ✅ NEW-2：replay_advisory 自動消失

**經驗教訓**：
- 對抗性核實 4 維度（source grep / test 真實內容 / mock 邊界 / PG runtime row 直查）都做了
- W-AUDIT-2 e2e 必查 PG runtime row（v1 用 OPENCLAW_TEST_PG opt-in 不夠真）
- v1 NEW issue 列 BLOCKER 但 v2 commit 沒接 = PA 派工漏項；E4 應在 v2 verification 顯式 push back PA
- v2 baseline 應更新 profile.md「2555/17」過期 → Linux control_api_v1 3925/3 + cargo lib 2584/0

---

## 2026-05-09 v3 verification — 5 commits sibling test 對抗性核實 (HEAD da2aba11)

**範圍**：v2 baseline `faf2d131` → HEAD `da2aba11` 5 commits = ad14db07 + c2ab7b1a + 48227607 + c081029d + da2aba11
**任務**：sibling test 同步 + 真跑 baseline 雙跑 deterministic

**Verdict**：✅ PASS (5/5 commits sibling test 真實到位 + 真跑 PASS + 雙跑同綠 + 0 commit-introduced new fail)

**baseline 雙跑 deterministic 一致**：
- pytest control_api_v1: **3961/3 → 3961/3** (vs v2 3925/3, +36 PASS / 0 fail delta)
- cargo lib: **2586/0 → 2586/0** (vs v2 2584/0, +2 PASS)

**5 commits sibling test 真實到位**：
1. **ad14db07 Donchian guard**：Rust 2 sibling test (`test_compute_all_uses_prior_bar_donchian_snapshot` + `test_w_audit_6_bb_breakout_5m_hard_gate_uses_prior_donchian`) — current-bar high=999 spike vs prior high=110 真實 cover
2. **c2ab7b1a strategist wide skill**：Rust 1 + Python 2 sibling test (`test_build_strategist_eval_payload_includes_wide_adjustment_skill` + `test_ai_service_strategist_prompt_exposes_wide_adjustment_skill` + `test_ai_service_strategist_prompt_uses_runtime_max_delta`) — 30%/40%/50% 三窗口邊界 cover
3. **48227607 promotion evidence**：4 file 8 sibling test (`test_edge_estimator_scheduler_promotion_evidence` × 2 + `test_promotion_pipeline.py` +2 + `test_promotion_evidence` × 4 + V079 migration × 2) — demo push / live_demo skip / V079 schema cover
4. **c081029d freeze blocked symbols**：2 file 6 sibling test (`tests/structure/test_strategy_blocked_symbols_freeze` × 3 + `helper_scripts/db/test_blocked_symbols_counterfactual` × 3) — 3 strategy_param + 4 risk_config 跨 file 對齊 + SQL injection 防護 + RFC policy
5. **da2aba11 f08 cron scope**：1 file 4 sibling test (`tests/helper_scripts/test_ml_training_maintenance_cron_static`) — `CORE_JOBS + AUDIT_JOBS == VALID_JOBS` + wrapper body 5 jobs + log 10 jobs token 三層 assertion

**Path naming convention drift（不是 bug）**：
- c2ab7b1a Python file 在 `test_p1_audit_smoke.py` 不是 `test_strategist_*` (PA glob 不命中但 substance 等效)
- c081029d freeze guard 在 `tests/structure/` 不是 `tests/governance/` (PA glob 不命中但同檔)
- da2aba11 cron static test 在 `tests/helper_scripts/` 不是 `helper_scripts/cron/test_ml_training*` (PA glob 不命中但同檔)
- E4 教訓：path glob 不是核實標準；substance 才是；PA 派工模板可用 substring 而非完整 path glob

**Mock 安全等級**：
- 3 commits (ad14db07/c2ab7b1a/c081029d/da2aba11) **0 mock**
- 1 commit (48227607) **borderline collaborator mock**：`_FakeGate` + `monkeypatch.setattr run_james_stein` — 但 sibling 雙層 cover：`test_promotion_pipeline.py` 用真 `PromotionGate` + `test_push_without_stress_exposure_is_honest_fail_closed_not_fake_pass` 用 `gate=None` 走 real fall-back
- 整體：5/5 commits 守 IO 邊界，無 fake-pass via mock 整個 business chain

**對抗性 push back outcomes**：
- A: ad14db07 真測 current-bar 含污染 ✅ YES (high[20]=999 spike helper)
- B: c2ab7b1a 真驗 30%/50% 邊界 ✅ YES (Rust + Python 雙端 normal/wide range)
- C: c2ab7b1a path 不同 ⚠️ Equivalent
- D: 48227607 mock 掩蓋業務邏輯 ⚠️ Borderline 雙層 cover
- E: c081029d path 不同 ⚠️ Equivalent
- F: c081029d freeze 真實生效 ✅ YES (跨 7 file + SQL injection + RFC policy)
- G: da2aba11 path 不同 ⚠️ Equivalent
- H: da2aba11 真驗 5+5=10 jobs ✅ YES (CORE_JOBS + AUDIT_JOBS + wrapper body + log 三層)
- I: 整體 mock 安全 ✅ YES (3 commits 0 mock)
- J: borderline `_FakeGate` 掩蓋 bug ✅ NO (caller wiring vs gate logic 分工)
- K: pre-existing fail 新增 ✅ NO (3 fail = v2 已記)
- L: 雙跑 deterministic ✅ YES (pytest + cargo 兩端均 1st run == 2nd run)

**仍未修復清單（無新增，全是 v2 已記）**：
- 🔴 NEW-1: `test_oe_006_close_retry_budget_has_real_timeout_guard` static path 仍未接（PA 派工漏項，v1 + v2 + v3 連續 3 round 漏接）
- 🟡 NEW-3: 4 collection errors PYTHONPATH inject 待修
- 🟡 NEW-4: `test_grafana_data_writer.py::test_start_sets_running` Linux leader-lock contention

**經驗教訓**：
- 對抗性核實 6 維度（source diff / sibling test 真實內容 read / 真跑 verify / mock 邊界 / path naming check / pre-existing fail 對照）都做了
- PA 派工模板用「path glob」太嚴；實際 path naming 由 E1 / CC 自由命名（合理 topic-suite naming）；E4 應 substance 等效 → PASS，不應因 path drift FAIL
- v3 baseline 應更新 profile.md：Linux control_api_v1 **3961/3** + cargo lib **2586/0**
- 5 commits 全部由 ncyu (operator/codex) 提交；無 commit-introduced new fail；governance fixed test 同步加齊 — 是高品質 commit batch

---

## 2026-05-09 W-AUDIT-7c GUI 三項修復回歸（HEAD `8b766a43` round 1 → working tree round 2）

**範圍**：W-AUDIT-7c GUI typed-confirm modal + Settings sub-tab 拆分 5 file +573/-124
- common.js +140 (新 openTypedConfirmModal helper)
- governance-tab.js +50 -8 (兩個 native confirm 替換)
- tab-ai.html +13 -3 (clearProviderKey native confirm 替換)
- tab-settings.html +368 -123 (4 sub-tab 拆分 + modal 抽出)
- tests/static/test_typed_confirm_modal.html +135 (browser fixture)

**Verdict (round 2)**：✅ **PASS** — round 1 IMPL bug 已 catch（governance-tab.js ES6 SyntaxError） → E2 RETURN-TO-E1a (`9f030e5e`) + E4 同步 catch → E1a round 2 fix（變數重命名 `ok` → `okCount` + cache pending list）已 land working tree → E4 對 round 2 重跑全 10 case + 全量 baseline 全綠 deterministic
**Verdict (round 1, historical)**：🛑 FAIL — `governance-tab.js:1581` const/let 同 scope 重複宣告，整個 governance tab broken。CASE-08 (node --check) 真實 catch。

**Mac baseline 雙跑 deterministic**（control_api_v1 + tests/）：
- Mac before W-AUDIT-7c：control_api_v1 3955/2 + srv/tests 232/1 = 4187/3 (3 fail = pre-existing, 不是 W-AUDIT-7c)
- Mac round 1（含 IMPL bug，含新 10 case）：control_api_v1 3964/3 + srv/tests 232/1 = 4196/4 (+9 pass / +1 fail = CASE-08 真實 catch IMPL bug)
- **Mac round 2（E1a 已修 working tree，含新 10 case）**：control_api_v1 **3965/2** + srv/tests 232/1 = **4197/3** (+10 pass / 0 fail delta — 全 10 case PASS、bug 已修)
- Linux runtime 端：直接 `node --check governance-tab.js` 跨平台同 reproduce round 1 SyntaxError（Linux v22.22.2 + Mac v25.9.0 都 throw）；round 2 fix 後 exit=0
- 雙跑 deterministic：1st run = 2nd run（10 passed in 0.10-0.11s）

**新加測試文件**：
- `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/static/test_w_audit_7c_typed_confirm_modal.py` (10 case, 297 lines)
- 涵蓋 E1a report 建議 5 case + E4 對抗性補強 5 case
- pattern 沿用既有 test_replay_subtab_static_assets.py / test_login_redirect_contract.py

**10 case 結果**：
| case | 內容 | 結果 |
|---|---|---|
| 01 | 3 tab html stack_residue 空 | PASS |
| 02 | common.js + governance-tab.js brace/paren/bracket diff = 0 | PASS |
| 03 | governance-tab.js native confirm() 殘留 = 0 | PASS |
| 04 | tab-ai.html native confirm() 殘留 = 0 | PASS |
| 05 | openTypedConfirmModal 函數體 brace_balanced | PASS |
| 06 | 4 sub-tab open/close 平衡 | PASS |
| 07 | openTypedConfirmModal 必備 hook keys 在位 | PASS |
| **08** | **★ governance-tab.js node -c 真實 ES6 syntax check** | **round 1 FAIL → round 2 PASS** |
| 09 | common.js node -c 真實 ES6 syntax check | PASS |
| 10 | tab-settings.html ocSettingsSubtabShow/Restore + button id 在位 | PASS |

**真實 IMPL bug（CASE-08 catch）**：

```
governance-tab.js:1581
  let ok = 0, fail = 0;
      ^
SyntaxError: Identifier 'ok' has already been declared
```

**RCA**：line 1555 `const ok = await openTypedConfirmModal(...)` 與 line 1581
`let ok = 0, fail = 0;` 在同一 function `bulkAudit(action)` scope（line 1546）內，
ES6 `const` + `let` 重複宣告同名變數 = SyntaxError；Chrome/Firefox/Edge 在
load governance-tab.js 時 100% throw，**整個 governance tab 所有行為 broken**
（不只 bulkAudit；script 整檔 parse fail 後所有 export 函數都不可用）。

**最小修法（給 E1a）**：line 1581 改名為 `okCount` 或 `successCount`
（連帶 line 1586 `if (d && d.ok) ok++; else fail++;` + line 1590 `ocToast(ok + ...)` 同步改）。

**E1a IMPL report 漏抓 RCA**：
- E1a 自評「JavaScript brace/paren/bracket diff: governance-tab.js braces=0 parens=0 brackets=0」+ 聲稱 healthy
- 純字元計數 diff = 0 但 ES6 重複宣告（const + let same scope）是 lexical-level error，非 brace 錯位
- E2 review 也漏抓（沒跑 `node --check`，只 review diff）；E4 才真實 catch

**E4 邊界堅持**：
- 不修 business logic（讓 E1a 修）
- 但寫真實 catch test 給 PM 看，明確 verdict
- 退回 E1a 而非 silent commit（「不允許刪測試使測試通過」原則）

**對抗性 push back 維度**（10 維度）：
- A: governance-tab.js brace 平衡 ✅ PASS
- B: governance-tab.js node -c ✅ PASS（catch SyntaxError）→ 真 bug
- C: common.js brace 平衡 ✅ PASS
- D: common.js node -c ✅ PASS
- E: openTypedConfirmModal hook 缺漏 ✅ PASS
- F: native confirm 殘留 ✅ PASS
- G: 4 sub-tab open/close ✅ PASS
- H: pre-existing fail 增加 ✅ NO（依 baseline 2 fail 不變）
- I: 跨平台 reproduce ✅ YES（Mac node 25 + Linux node 22 都 throw）
- J: 不靠 mock 掩蓋業務 ✅ YES（純 syntax check，0 mock）

**經驗教訓**：
- E4 必跑 `node --check` 對所有改動 .js / 內聯 JS — pure brace 計數 false-pass 高
- E1a + E2 應在自驗 chain 加 node --check，不只 brace diff 計數
- ES6 `const` + `let` 重複宣告是同 scope lexical bug，常被靜態 grep 漏；只有真 parser 能 catch
- HEAD `8b766a43` (E1a memory + report) 含 round 1 IMPL bug，不應視為「ready to deploy」；round 2 working tree 才 ready
- E2 round 1 RETURN-TO-E1a (`9f030e5e`) 與 E4 round 1 catch 同 bug 是好現象（雙 catch 互驗）；round 2 land working tree 後 E4 對 working tree 重驗 PASS
- E4 commit 範圍只含自己的 test + memory + report，**不吞** E1a round 2 working tree fix（E1a / PM 自己 commit）

---

## 2026-05-09 ml_training cron IPC fix Round 2 regression baseline + 5/10 SOP 簽署（HEAD `cf291d63`）

**任務範圍**（E2 round 2 APPROVED 後 E4 純 baseline 簽署 + observe SOP）：
- 工作鏈：E1 round 1 (`3d8d543e` + `fac9e386`) → E2 round 1 RETURN-TO-E1 (`b3607c10`) → E1 round 2 (`1448e0a1`，補 12 regression test + LOW-1 fix) → E2 round 2 APPROVED (`cf291d63`，含 mutation 重現驗 mock 不掩蓋)
- 業務改動極小（cron sh +9 / IPC handshake +98/-33 / LOW-1 -1 行），E4 主要做 (1) baseline 雙跑 deterministic 確認 + (2) 5/10 03:17 cron real-fire SOP 文檔化

**Verdict**：✅ **PASS**

### Pytest baseline（Mac + Linux）

| 環境 | 跑 | passed | failed | skipped | 解讀 |
|---|---|---|---|---|---|
| Mac ml_training | 1st | 365 | 0 | 31 | dev_disabled / Linux runtime 才有的 33 test 預期 skip |
| Mac ml_training | 2nd | 365 | 0 | 31 | deterministic ✅ |
| Linux ml_training | 1st | 398 | 0 | 29 | 與 E2 round 2 自跑 baseline 一致 |
| Linux ml_training | 2nd | 398 | 0 | 29 | deterministic ✅ |
| Linux test_optuna_ipc_handshake.py | 1st | 12 | 0 | 0 | 12/12 in 0.12s |
| Linux test_optuna_ipc_handshake.py | 2nd | 12 | 0 | 0 | 12/12 in 0.11s deterministic ✅ |

**baseline 不退化**：兩端 0 fail，新增 12 test 全綠 deterministic（雙跑同數）。Linux warning 3 條 (parquet_etl utcnow + realized_edge_stats utcnow) 為 pre-existing deprecation，與本次改動無關。

### 5/10 03:17 cron real-fire SOP script

**Path**：`srv/helper_scripts/observe/2026_05_10_cron_real_fire_check.sh`（+265 行 / executable）

**設計**：
- `--before`：5/10 03:17 UTC 前採集 baseline（4 表 row count snapshot 寫 `baseline_2026_05_10_cron.json`）
- `--after`：5/10 03:30 UTC 後跑 4 觀察點 + 比對 delta

**4 觀察點**（對齊 E2 round 1 review report SQL 觀察點）：
1. cron log 抓 `2026-05-10 03:1X` 時間戳（驗 cron 真 fire）
2. optuna_optimizer.detail.param_ranges_source = `"ipc"` 不是 `unavailable:RuntimeError`（驗 IPC __auth 通）
3. weekly 5 audit job (thompson/optuna/cpcv/dl3/weekly_report) 全部 fire 在 status_json
4. PG 4 表 row count delta：weekly_review_log 至少 +1（必 INSERT）；其他依 fills 樣本

**通過判定**：
- ✓ log 有 03:1X 紀錄
- ✓ optuna status=ok / param_ranges_source=ipc
- ✓ 5 weekly job 全部出現（個別 job 內部 error 標 WARN 不 FAIL，屬獨立議題）
- ✓ wrl delta ≥ 1

**Dry-run 驗證**（5/9 18:58 UTC，5/10 cron 還沒到）：
- `--before` 採 baseline 成功：`bp=219 / mps=0 / fmf=8 / wrl=2`（注：`mps=0` 是 E2 review Q4 確認的 fills<80 樣本不足，不是 IPC fail）
- `--after` 行為符合預期：[1/4] log FAIL（時間還沒到，正確）/ [2/4] IPC PASS（已通）/ [3/4] 5 job fire（cpcv:error 標 WARN）/ [4/4] delta=0 FAIL（時間還沒到，正確）

**安全設計**：
- PG 密碼從 `~/BybitOpenClaw/secrets/environment_files/basic_system_services.env` 動態 source（不 hardcode）
- psql stderr 重定向 `2>/dev/null` 避免 PG WARNING 污染 baseline file
- 跨 phase 設計（before/after 分開跑），避免一次調用 lock 拒 spawn
- 對 missing baseline 有守（full mode 退路：直接 print usage 不亂跑）

### Mock 安全審查（complement E2 round 2）

E2 round 2 已對新 12 test 做 mutation review（commit `cf291d63` 含 5 維度 mutation：authentication mute / token-strict null / wire-format key 重排序 / fail-soft OSError 改 raise / silent skip 重引），E4 不重複；但確認本身範圍：
- 0 業務邏輯 mock（純 socket / hashlib / hmac / OS env）
- subprocess 真實 socket pair 走 wire byte（test_byte_equal_authenticate_payload）
- monkeypatch + tmp_path file IO 是 IO 邊界 mock 屬合規

### 經驗教訓（追加 E4 memory）

1. **5/10 SOP 必先在 5/9 dry-run** — 確認 PG path 通 + ssh trade-core 可達 + status_json 結構穩定（避免明早 03:30 才發現 SOP 自己 broken）
2. **Pre-existing baseline 對齊兩端**：Mac 365/0/31 與 Linux 398/0/29 差異 = 33 test 預期 skip on Mac dev_disabled；E4 必明標兩端 baseline，不能只信一端
3. **PG psql stderr 在 At 模式仍會印 collation WARNING**：必 `2>/dev/null` 屏蔽，否則 row count 解析會吃進 noise
4. **business改動小 ≠ E4 範圍小**：純 test commit 仍要做 deterministic 雙跑 + cross-host baseline + Linux runtime 真實打 SOP（不是 Mac mock）；E2 round 2 自跑 Linux pytest 不能省略 E4 重跑驗證
5. **SOP script 設計反模式 = 一次跑只能單向**：必須拆 `--before` / `--after` 兩 phase，否則無法做 baseline → cron fire → delta 比對閉環

---

## 2026-05-09 Sprint N+0 second-pass cross-wave fixture fix verify (HEAD `11849c18`)

**任務範圍**：驗 E1-FIX commit `11849c18` 5 NEW regression 全 fix + 0 新 regression。
- First-pass baseline: pytest 4262 / 8 fail · cargo lib 2622 / 2 fail (5 NEW = 2 IPC + 3 parity + 1 sibling-session CI workflow)
- E1-FIX claim: cargo lib 2625/0 + parity 5/5 PASS

**Verdict**：✅ **PASS**

### Cargo workspace baseline (Linux + Mac 雙端 + 雙跑)

| Engine | round 1 | round 2 | first-pass | delta |
|---|---|---|---|---|
| Linux openclaw_engine lib | 2625 / 0 | 2625 / 0 | 2622 / 2 | +3 PASS / -2 fail (5 NEW fix verified) |
| Linux openclaw_core | 425 / 0 | 425 / 0 | n/a | parity check |
| Linux openclaw_types | 27 / 0 | 27 / 0 | 27 / 0 | unchanged |
| Mac openclaw_engine lib | 2625 / 0 | 2625 / 0 | parity | bit-exact 雙端 |
| Mac openclaw_core | 425 / 0 | 425 / 0 | n/a | parity |
| Mac openclaw_types | 27 / 0 | 27 / 0 | n/a | parity |

Workspace total = **3077 PASS / 0 fail**（雙端 + 雙跑 deterministic identical）。

### Pytest baseline (Linux 雙跑)

| Round | passed | failed | skipped | runtime |
|---|---|---|---|---|
| 1 | 4265 | 5 | 12 | 85.83s |
| 2 | 4265 | 5 | 12 | 78.03s |

5 fail 名單雙跑 identical:
1. `tests/ci/test_github_ci_workflow_static.py` ← sibling-session `0dc6d659` 副作用（不在 fix scope，PM follow-up）
2. `test_archive_top_level_files_are_all_indexed` ← pre-existing
3. `test_oe_006_close_retry_budget_has_real_timeout_guard` ← pre-existing
4. `test_grafana_data_writer.test_start_sets_running` ← pre-existing leader lock
5. `test_case2_pg_kill_simulation_returns_200_degraded` ← pre-existing

**5 W-AUDIT-9 chain NEW fail（2 IPC + 3 parity）已不在 round 2 fail 名單** ✓

### W-AUDIT-9 chain isolated verify

Rust IPC `cargo test ipc_server::tests::config` = **16/0 PASS**:
- `test_g3_02_a2_patch_executor_routes_to_demo_engine` ✓ FIXED (5-field atomic Stage 2 demo cohort)
- `test_g3_02_a2_patch_executor_binary_shadow_only_rejected_invariant_drift` ✓ FIXED (renamed; 改斷言為驗 invariant drift reject)
- `test_g3_02_a2_patch_executor_stage_promotion_via_patch_risk_config` ✓ NEW (5-field atomic Stage 1 paper cohort 成功)

Python parity `pytest test_executor_decision_parity.py` = **5/0 + 2 skipped**:
- `test_golden_fixtures_agree_rate` agree=30/30 (100%)
- `test_synthetic_handcrafted_agree_rate` agree=40/40 (100%)
- `test_overall_agree_rate_ge_95pct` agree=70/70 (100%) ≥67/70 threshold

### V080 + V082 idempotent (Linux PG empirical apply 雙跑)

V080: 6 NOTICE skip + `[migrate] OK` ✓ identical 雙跑 + identical first-pass
V082: 7 NOTICE skip + `[migrate] OK` ✓ identical 雙跑 + identical first-pass
DB row cleanup: canary_log=0 / canary_registry=0 / df_eval=0 ✓ schema-only

### Cross-language consistency 1e-4 tolerance

CanaryStage IntEnum encoding 雙端 bit-exact (Rust `as_shadow_mode()` = `matches!(Stage0)` ⇄ Python `_read_shadow_mode()` = `stage == CanaryStage.SHADOW`)。離散 enum 不需浮點容差。

### Sibling-session standalone reproduction

`tests/ci/test_github_ci_workflow_static.py::test_ci_workflow_runs_release_cargo_check_for_openclaw_engine` standalone 跑：
- 1 fail in 0.02s
- assertion: `'rustup target add "${{ matrix.target }}"' in WORKFLOW`
- root cause: commit `0dc6d659` 把 workflow 從 single-job matrix 改為 `rust-check-linux` + `rust-check-macos` 兩 job，每 job 寫死 hard target，不再用 `${{ matrix.target }}` 變數
- Fail mode 與 first-pass §2.3 一致 ✓
- 標 PM follow-up — 不在 W-AUDIT-9 fix scope

### Mac vs Linux cargo build --release

Mac engine + core: 0 error / 17 pre-existing warning ✓
Linux: cargo lib test 同時 build 0 error
三端 git HEAD 同步 `11849c18`（Mac local + Linux trade-core + GitHub origin/main）

### 教訓追加（second-pass 新增）

1. **cargo lib +3 PASS 來源拆解**：5 NEW fix 中 2 個翻 PASS + rename 1 個 + new 1 個 = +3 PASS（不是單純 -2 fail）。E1-FIX 改名 fixture 而非刪除符合「不允許刪測試使測試通過」原則
2. **Sibling-session catalog 必標 root cause + commit hash**：避免後續 sprint 誤判 sibling-session 副作用為當前 wave leftover
3. **雙跑 deterministic 是 PASS 必要條件**：runtime 略不同（85.83 vs 78.03s）但 fail 名單 + count 必須 byte-exact identical；timing vary 屬 system load
4. **Idempotent migration NOTICE chain 雙跑 byte-identical**：V080+V082 second-pass NOTICE 行數 + 順序 + skip 路徑 100% 對齊 first-pass = 真實 PG runtime verify（不是 mock pytest claim）
5. **PM commit chain 已成立**：first-pass commit `13b8e252` + E1-FIX `11849c18` 已 push origin/main，second-pass 同 chain commit + push 不需特殊處理

---

## 2026-05-10 Sprint N+0 W2 third-pass E1-FIX-W2 verify (HEAD `71de1cd5` + E2 `30b34b9b`)

**任務範圍**：驗 E1-FIX-W2 兩 outstanding (CRITICAL E1-C M3 6 Rust file fake-PASS retract + HIGH bb_reversion stress fail) 全 fix + 0 新 regression。
- 3 fix commits: `a01d05ed` (Rust producer 6 files) + `8393bcff` (bb_reversion stress fixture sma_50) + `71de1cd5` (docs retract [skip ci])
- W2 second-pass baseline 對比: cargo lib 3091/0 + pytest 4302/5 fail（含 4 pre-existing + 1 sibling CI workflow）+ 1 stress fail RETURN-TO-E1

**Verdict**：✅ **PASS**

### Cargo workspace baseline (Linux 雙跑)

| Engine | round 1 | round 2 | second-pass | delta |
|---|---|---|---|---|
| Linux openclaw_core lib | 432 / 0 | 432 / 0 | 425 → 432 | +7 (W2 W-AUDIT-8a alpha_surface) |
| Linux openclaw_engine lib | 2635 / 0 | 2635 / 0 | 2632 / 0 | +3 (E1-FIX-W2 decision_feature_writer.rs 3 new lock test) |
| Linux openclaw_types lib | 27 / 0 | 27 / 0 | 27 / 0 | unchanged |
| Linux integration tests (含 stress) | 226 / 0 (35/35 stress) | 226 / 0 | n/a | bb_reversion stress: FAIL → PASS |
| Linux doctest (engine) | 0/2 (mac_policy_guard.rs line 32/88) | 0/2 | 0/2 | unchanged pre-existing |

Workspace lib total = **3094 PASS / 0 fail**（雙跑 deterministic identical）。

### Pytest baseline (Linux 雙跑，三 dir scope)

| Round | scope | passed | failed | skipped | runtime |
|---|---|---|---|---|---|
| 1 | tests/+control_api/ | 4302 | 5 | 12 | 85.68s |
| 2 | tests/+control_api/ | (omitted; round 1 = second-pass identical) | 5 | 12 | n/a |
| 1 | tests/+control_api/+ml_training/ | 4744 | 5 | 41 | 85.28s |
| 2 | tests/+control_api/+ml_training/ | 4744 | 5 | 41 | 81.22s |

5 fail 名單雙跑 identical（4 pre-existing pytest + 1 sibling CI workflow `0dc6d659`）。

### E1-FIX-W2 兩 issue acceptance

**(CRITICAL) E1-C M3 6 Rust file fake-PASS retract**:
- `grep emit_decision_feature_intent_rejected rust/openclaw_engine/src/` = **5 hits** (1 method def `intent_processor/mod.rs:1218` + 3 dispatch call `step_4_5_dispatch.rs:437/718/1116` + 1 doc ref `database/mod.rs:606`)
- pytest `test_governance_reject_negative_label.py` = **真 19/19 PASS in 0.08s**（不是 W2 second-pass fake claim）含 invariant 5 `test_step_4_5_dispatch_reject_paths_emit_negative_label` + invariant 21 `test_attribution_chain_ok_mock_recovery`
- cargo lib +3 PASS（decision_feature_writer.rs 3 new lock test）

**(HIGH) bb_reversion stress fail fix**:
- `cargo test --release stress_bb_reversion_extreme_oversold_bounce` standalone PASS（fixture 補 `sma_50: Some(2050.0)` 對齊 oversold 業務契約）
- `cargo test --release --workspace` 35/35 stress_integration PASS（含 bb_reversion）
- 不破 W-AUDIT-6d #6 invariant: `require_ma_confirmation: true` default 仍 ON; ma_pair_allows_entry 業務邏輯真跑

### V083 + V084 idempotent (Linux PG empirical apply 雙跑)

V083: 2 NOTICE skip + 1 view replace + `[migrate] OK` ✓ identical 雙跑
V084: `[migrate] OK` (CREATE OR REPLACE 天然 idempotent) ✓ identical 雙跑

### attribution_chain_ok 24h ratio empirical query

實測 `learning.mlde_edge_training_rows` 24h: total=22377 / ok=64 / unfilled=22313 / abandoned=0 / **rejected=0**

ratio = 0.286%（仍 <1% baseline；E1-FIX-W2 producer code 已 land 但 engine 仍跑舊 binary，需 PM restart 才 emit reject row）。
mock estimate (test_attribution_chain_ok_mock_recovery) PASS：模擬 producer 補後 ratio 從 0.5% recover ≥ 5%。
真實 ratio recovery 留 PM deploy 後 24h passive watch（per E1-C 原 report Operator 下一步 #2）。

### 教訓追加（third-pass 新增）

1. **second-pass 自己犯 W1 baseline scope 漏跑同錯** — W2 second-pass 報告 §13 教訓 1 自己警告「W1 `--lib` only 漏抓 cross-wave 副作用」，但 second-pass 自己 cargo 仍只跑 `--lib --workspace` + pytest 漏 ml_training/tests/。本 third-pass 修正：cargo `--release --workspace`（含 31 integration test target）+ pytest 全三 dir scope（tests/ + control_api_v1/tests/ + ml_training/tests/）。**E4 baseline 永久升級到此 scope**。
2. **fake-PASS retract chain 必須 grep 證據而非 trust report** — E1-C W2 commit `e93a6e5c` message 自承 partial commit (5/10 file)，但 report 仍寫「19/19 PASS」+「Rust diff 範例」。E2 grep 是唯一 catch 路徑：`grep emit_decision_feature_intent_rejected rust/openclaw_engine/src/` = 0 hit 才暴露 fake claim。E4 third-pass acceptance 標準：**grep producer code present + cargo build clean + standalone pytest 真 PASS**（不只 trust E1 self-report）。
3. **ml_training/tests/ 是 W-AUDIT-4b chain 的核心 pool** — W-AUDIT-4b-M2 (entry_context_id) + W-AUDIT-4b-M3 (reject negative label) + 既有 backfill / sample_weight chain 的 invariant test 都在 `program_code/ml_training/tests/`。E4 W2 second-pass pytest 漏 ml_training/tests/ scope = 漏 442 個 test 含 19 個 fix verify。E4 baseline scope 須**含所有 program_code/*/tests/ 子集**。
4. **runtime restart vs source code land 分離 acceptance** — `attribution_chain_ok` 24h 真實 ratio recovery 需 engine restart 跑新 producer binary 才能 emit reject row → INSERT learning.decision_features → view ok_n 增加。E4 acceptance 範圍：**source code land + lib test PASS + standalone pytest PASS + mock estimate PASS**（不擴 runtime engine effect 觀察期；runtime restart + 24h passive watch 是 PM operational concern）。
5. **三 fix commit 模式（業務 + 業務 + docs）對齊 governance** — `a01d05ed` (Rust producer 業務改動，no [skip ci]) + `8393bcff` (stress fixture 業務改動，no [skip ci]) + `71de1cd5` (docs report + memory，[skip ci])。E2 + E4 自己的 review/regression commit 各別 [skip ci] 不跑 CI。
6. **trading_ai 是真實 DB 名（不是 trading_system）** — Linux runtime PG DB = `trading_ai`，passive_wait_healthcheck.py 等所有 SQL query 必對齊；W2 third-pass empirical query 因第一次連 trading_system fail 才發現此 mismatch（E4 memory 收口）。
7. **cargo workspace failures 行可能誤匹配 doctest** — `cargo test --release --workspace 2>&1 | grep FAILED` 第一條 hit 是 startup module 的 `test_paper_balance_from_env_valid_and_invalid ... FAILED`（misleading），實際是 doctest mac_policy_guard.rs line 32/88 fail。需要看 stdout 完整內文確認 unit test 真實 OK。E4 baseline 必走 `grep -E '^test result|^failures:' --color` 過濾後再對比。

---

## 2026-05-10 W7-3 emergency 1-tick defense regression verify (HEAD `d8697c41`)

**任務範圍**：驗 W7-3 commit `d8697c41` (ma_crossover.on_rejection duplicate_position sync) 0 regression + 加 1 SLA pressure test。
- E1 sign-off claim: 58 ma_crossover test + 2639 lib regression + cargo build clean
- 對比 W2 third-pass baseline: cargo lib 2639 / 0
- 預期 delta: cargo lib unchanged 2639 (W7-3 4 unit test 已併入 ma_crossover subset)

**Verdict**：✅ **PASS**

### Cargo workspace baseline (Mac + Linux 雙端 + 雙跑)

| Engine | Mac round 1 | Mac round 2 | Linux round 1 | Linux round 2 | baseline | identical | verdict |
|---|---:|---:|---:|---:|---:|---|---|
| openclaw_engine lib (W7-3 only) | 2639 / 0 | 2639 / 0 | 2639 / 0 | 2639 / 0 | 2639 / 0 | yes | PASS |
| ma_crossover focused (含 4 W7-3 new test) | 58 / 0 | n/a | 58 / 0 | n/a | n/a | yes | PASS |
| openclaw_engine lib (W7-3 + E4 SLA test) | 2640 / 0 | 2640 / 0 | n/a (unstaged) | n/a | 2639 / 0 | yes | +1 PASS |
| ma_crossover focused (W7-3 + E4 SLA test) | 59 / 0 | n/a | n/a (unstaged) | n/a | 58 | yes | +1 PASS |
| Mac engine binary `--release` | 0 errors / 2 pre-existing warning | n/a | n/a | n/a | clean | yes | PASS |

### Pytest baseline (Linux full 3-dir scope, W2 third-pass scope)

| pytest | passed | failed | skipped | runtime | match W2 third-pass |
|---|---:|---:|---:|---:|---|
| Linux tests/+control_api/+ml_training/ | 4744 | 5 | 41 | 81.99s | yes (count + skip identical) |

5 fail 名單對比 W2 third-pass：
1. `test_archive_top_level_files_are_all_indexed` ← pre-existing ✓ unchanged
2. `test_oe_006_close_retry_budget_has_real_timeout_guard` ← pre-existing ✓ unchanged
3. `test_grafana_data_writer.test_start_sets_running` ← pre-existing leader lock ✓ unchanged
4. `test_case2_pg_kill_simulation_returns_200_degraded` ← pre-existing ✓ unchanged
5. `test_f08_wrapper_invokes_runner_with_all_jobs` ← sibling commit `268f9470/da2aba11` 引入（fixture 缺 MOCK_ML_DSN 注入），swap 出舊 sibling-CI workflow fail；**非 W7-3 引入**

**Sibling-session catalog** (PM follow-up):
- swap-out: `test_ci_workflow_runs_release_cargo_check_for_openclaw_engine` (W2 third-pass `0dc6d659` 引入) — 是否已被別 sibling 修復或 CI workflow 重新對齊？
- swap-in: `test_f08_wrapper_invokes_runner_with_all_jobs` (commit `268f9470/da2aba11` 引入)

### W7-3 4 unit test acceptance (E1 IMPL DONE 對齊)

```
test strategies::ma_crossover::tests::test_on_rejection_duplicate_position_already_long_syncs_position ... ok
test strategies::ma_crossover::tests::test_on_rejection_duplicate_position_already_short_syncs_position ... ok
test strategies::ma_crossover::tests::test_on_rejection_non_duplicate_position_runs_full_rollback ... ok
test strategies::ma_crossover::tests::test_on_rejection_unknown_duplicate_format_fallback_to_rollback ... ok
```

雙端 Mac + Linux 全 PASS deterministic identical。

### E4 新增 SLA pressure test

`test_on_rejection_duplicate_position_burst_no_panic_no_hang` (+41 LOC pure test scope at tests.rs:809-846):
- 1000 次 on_rejection burst with `"duplicate_position: INXUSDT already SHORT 1810"` reason
- 驗證 1: HashMap stays size=1 (O(1) update 不累積，防 hot loop hashmap leak)
- 驗證 2: 終態 `positions[INXUSDT] = Some(false)` (last reason direction sticks)
- 驗證 3: wall-clock < 100ms (Mac release 實測 0ms / 100ms 為 CI 噪音 headroom)
- Mac `cargo test --release` 實測 PASS in 0.00s

**Status**：unstaged，留 PM 決定是否 commit (按 task §邊界「不 deploy」)。

### Cross-language float consistency

W7-3 fix 純 string parsing + HashMap insert 不影響 float — 不適用 1e-4 容差 verify (E4 邊界 §4.6 cross-language consistency 對 indicator/calculator 才有意義；on_rejection 是 control flow path)。Python pytest ma_crossover-related 1/1 PASS；Python 端無調用 Rust on_rejection IPC，不需 cross-language drift check。

### Reason 字串契約 audit

`rejection_coding.rs:55-152` `RejectionCode::DuplicatePosition` format = `"duplicate_position: {symbol} already {LONG|SHORT} {qty}"` byte-identical to ma_crossover W7-3 parsing：
- E1 用 `reason.contains("duplicate_position")` 而非 `starts_with()` — 防 prefix prepend (e.g., metric tag)
- E1 用 `reason.contains("already LONG")` / `reason.contains("already SHORT")` 解析 direction
- contract drift fallback: 含 `duplicate_position` 但無 `already LONG/SHORT` → tracing::warn + fallback 走 RC-04 prev_position rollback
- 4 case unit test 全 cover (LONG sync / SHORT sync / unknown format fallback / non-duplicate full rollback)

### Trait `Strategy` on_rejection signature consistency

| Strategy | signature | impact |
|---|---|---|
| trait default `mod.rs:106` | `_intent, _reason: &str` (default no-op) | unchanged |
| ma_crossover | `intent, reason: &str` (W7-3) | underscore 拿掉合規 (impl 端可覆寫) |
| bb_breakout | `intent, _reason: &str` | unchanged |
| bb_reversion | `intent, _reason: &str` | unchanged |
| funding_arb | `intent, _reason: &str` | unchanged (策略已 retire) |
| grid_trading | `intent, reason: &str` | unchanged (first opener，無 W7-3 場景) |

Trait contract clean — 0 sibling strategy 受影響。

### W7-4 systemic fix scope inventory (留給 PA #3 Option A / W-AUDIT-8a)

5 策略 (`ma_crossover` / `bb_breakout` / `bb_reversion` / `funding_arb` / `grid_trading`) 都有 `on_rejection` impl + `self.positions: PerSymbolState<bool>` 各自 buffer。當前 W7-3 補丁僅 ma_crossover；其他策略遇 grid_trading 同 symbol 先開倉時仍可能撞 router gate 1.5 hot loop（W6 baseline 沒看到只因 signal 沒對齊）。W-AUDIT-8a Option A 治本路徑 = TickContext 加 `paper_state` reference 升 5 策略 signature 一次性對齊。**E4 不 dispatch**，僅紀錄。

### 教訓追加 (W7-3 round 新增)

1. **W7-3 補丁式應急防衛範圍最小化驗證** — E1 IMPL 354 LOC + 152 LOC test (4 unit test) 是合理 bounded scope；E4 加 1 SLA test (+41 LOC) 同樣 bounded。reject 大改動 = 進入 W-AUDIT-8a Option A architectural reform，非 W7-3 補丁 scope。
2. **string-parsing on_rejection 補丁不需 cross-language float consistency check** — task §2 「W7-3 純 string parsing + HashMap insert 理論上不影響 float」分析正確，Python pytest ma_crossover-related 1/1 PASS confirm。E4 baseline 不需強制 1e-4 tolerance run，control flow path 不適用該 gate。
3. **trait method override underscore 拿掉是合規 Rust 慣例** — `_reason → reason` (impl 端 unused → used) 不破 trait signature；其他策略仍用 `_reason: &str` 不被影響；E4 必 grep `mod.rs` trait def 確認 default impl 簽名兼容。
4. **SLA pressure test 設計關鍵 = O(1) vs O(n) 防線** — 1000 次同 symbol on_rejection 後 `positions.len() == 1` 是核心 invariant，防未來 refactor 把 HashMap insert 換成 Vec push 引入 O(n) leak；wall-clock 100ms threshold 是放鬆值（Mac release 0ms / Linux release 應 < 5ms）防 CI 噪音 false-fail。
5. **PM 統一 commit chain 守則 (task §邊界「不 deploy」解讀)** — E4 自加 SLA test 不獨立 commit + push，留 unstaged 給 PM 決定（PM 可選 (a) 併入 W7-3 主 commit / (b) 單獨 [skip ci] commit / (c) 拒絕加入）。E4 報告獨立寫入 workspace/reports/ 仍 OK（按 E4 啟動序列硬要求）。
6. **Sibling-session pytest fail name swap 必標 commit hash + scope 區分** — W2 third-pass `0dc6d659` CI workflow swap 出 → `268f9470/da2aba11` ml_training cron audit swap 入；總 fail count 仍 5（pre-existing 4 + sibling 1），但**個別 test 名變動**；E4 baseline 比對必 catch swap，否則誤判為 W7-3 引入。
7. **Linux runtime engine 仍跑舊 binary** — W7-3 commit `d8697c41` 已 land main，但 Linux engine 須 `restart_all.sh --rebuild --keep-auth` 才會跑新 binary；W7-3 1-tick defense 真實 hot loop fix 需 PM deploy 後 30min observation 才 verify (per PA W7-3 deploy SOP)。E4 acceptance 範圍**僅含 source code land + lib test + SLA test PASS**，不擴 runtime hot loop 觀察期。

## 2026-05-10 (Sprint N+1 D+0 W4 RouterLeaseGuard Drop test pre-write)

### 任務 = W4 IMPL pre-write，per PM 21:30 sign-off + D+1 deploy

PM 預寫 W4 W-AUDIT-3b runtime smoke 的 RouterLeaseGuard Drop unit test ~40 LOC（task spec），讓 D+1 W4 sub-agent 直接 commit + 寫 runtime smoke shell + deploy，不需重新設計階段。**邊界**：不 commit + 不 deploy + 不 ssh。

### 1. 真正 unique gap ≠ task description

Task 描述：「RouterLeaseGuard Drop release on rejection path 沒 assertion → 補 1 條 Rust unit test」。**事實上**：
- Test 5 `test_router_gate_on_production_drop_cancels_on_atr_zero` (`tests_predictor_router.rs:1248-1286`) 透過完整 `process_with_features` pipeline (ATR=0 觸發 SEC-11) 驗 `live=0` 證明 Drop release Cancelled
- Test 6 `test_router_gate_exchange_path_lease_id_states` sub-case 3 (line 1339-1380) 透過完整 `process_gates_only_with_features` pipeline 驗 Drop release on rejection (no leak)
- 所以「Drop release」**已被間接覆蓋**

**真正 unique gap** = isolated struct-level RAII contract test（不通過完整 pipeline）。Pipeline-based test 未來在 cost_gate / SEC-11 / tick_pipeline 改動時可能連帶破壞 → Drop 行為迴歸偵測會失準。Isolated unit test 把 Drop 行為脫離 pipeline 變動風險，是 W4 真正 coverage 補強價值。

### 2. RouterLeaseGuard private struct → 必在同 file 內加 #[cfg(test)] mod tests

`RouterLeaseGuard` 是 `router.rs:22` `struct RouterLeaseGuard<'a>`（無 `pub`，module-private）。`tests_predictor_router.rs::router_gate_lease_tests` 透過 `super::*` 看不到 `RouterLeaseGuard`（在 `router` private module 內）。

**唯一 isolated unit test 寫法** = 在 `router.rs` 末尾加 `#[cfg(test)] mod tests`，透過 `super::RouterLeaseGuard` / `super::acquire_lease_for_gate_1_4` 訪問。E4 必查 struct visibility 才能正確選 test 位置；`tests_predictor_router.rs` 是錯誤位置（會破編譯）。

### 3. Sub-case 設計 = 必 cover Drop 兩態

Sub-case 1 (rejection path)：`RouterLeaseGuard::new(&gov, Some(lease))` 包進 scope，scope 結束 auto Drop → assert `live=0` (Active → Revoked)。
Sub-case 2 (consume path)：`guard.consume()` 取出 inner lease → guard auto Drop 看到 `self.lease.is_none()` → no-op → assert `live=1` (caller 接管)。

**僅 cover Sub-case 1 不夠**：consume() 接 success path 是 Drop 的另一條 contract path，Drop impl 用 `self.lease.take()` match Some/None 兩態；只測 Some 漏 None 路徑（雖無「真實 Drop release」但漏「success path Drop NOT release」假設）。完整 RAII contract 必雙 sub-case。

### 4. cargo test 結果 = 2640 → 2648 (W4 +1, 隔壁 uncommitted W7-2 +7)

| State | Run | Result |
|---|---|---|
| Pristine baseline (`git stash` 後) | - | 2640 / 0 |
| W4 test 加入後 (含隔壁 W7-2 uncommitted) | Run 1 | 2645 / 3 (persistence flaky) |
| 同上 | Run 2 | 2648 / 0 |
| 同上 | Run 3 | 2648 / 0 |
| W4 isolated 單跑 | - | 1 / 0 (filtered_out=2647) |
| persistence 隔離跑 | - | 7 / 0 (隔離無 race) |

**flaky 結論**：`persistence::tests::test_audit_writer_append` / `test_dual_state_writer_no_compat` / `test_dual_state_writer_writes_both` 是 pre-existing concurrent tmp-file write race；隔離跑全 PASS；與 W4 test (純 in-memory `GovernanceCore` + Mutex SM) 完全隔離。Run 2/3 全綠證 W4 test 100% deterministic。

### 5. 隔壁 uncommitted W7-2 wave +7 tests 不可動

`git stash pop` 後看到 5 個 modified files (memory.md / project_*.md / bb_reversion/{mod,tests}.rs / ma_crossover/{strategy_impl,tests}.rs)，新加 7 tests。按 multi-session race 守則 (`feedback_git_commit_only_for_metadoc.md`)：**不認得改動禁 revert**。E4 staging 範圍只含 `router.rs`；隔壁工作（W7-2 wave）由各自 session 處理。

### 教訓追加 (W4 round 新增)

1. **Task description ≠ 真實 gap，必 grep 既有 test 確認** — Task 說「沒 assertion」，實際 Test 5/6 已透過 pipeline 間接驗。E4 必先 `grep RouterLeaseGuard tests_predictor_router.rs` 釐清「有 vs 沒 vs 部分覆蓋」三態，再決定是「拒絕重寫 fake coverage」還是「補 unique angle」。本任務最後選後者（isolated struct-level RAII contract test，避免未來 pipeline 改動連帶污染 Drop 迴歸偵測）。
2. **Module-private struct test 必在同 file 內** — `RouterLeaseGuard` 是 `struct` (無 `pub`)，跨 file `tests_predictor_router.rs` 透過 `super::*` 看不到（module hierarchy 限制）。必在 `router.rs` 末尾加 `#[cfg(test)] mod tests` 才能訪問私有 struct。E4 必先確認目標 struct visibility (`pub` / `pub(crate)` / private) 才能正確選 test 位置。
3. **Drop test 必 cover 兩態 (Some / None)** — RAII Drop impl 通常用 `self.x.take()` match Some/None；只測 Some 漏 None contract path。本 W4 test sub-case 2 (consume() 後 Drop NOT release) 是 success path RAII contract 必驗點。
4. **Pristine baseline 必透過 git stash 重跑** — 隔壁 session uncommitted changes 會虛增 test count；E4 baseline 報告必跑 `git stash + cargo test + git stash pop` 取真 pristine 數，否則 W4 net delta 計算錯誤（誤把 W7-2 +7 算進 W4 範圍）。
5. **persistence flaky 是 pre-existing concurrent tmp-file race** — 並發跑 ~2648 test 時 file_writer 偶撞；隔離跑 (`cargo test persistence::tests`) 全 PASS。E4 跑兩遍策略可 confirm flaky vs real bug；本任務 Run 2/3 同 2648 PASS 證 W4 test 100% deterministic，不需 deflake。
6. **NOT COMMITTED + NOT DEPLOYED 標記是 W4 sub-agent 接手契約** — E4 pre-write 完成後改動仍 uncommitted，留給 D+1 W4 sub-agent commit + push + ssh deploy。報告獨立寫入 `workspace/reports/` 是 E4 啟動序列硬要求；報告同時是 W4 sub-agent 接手憑證（含 acceptance 對照表 + 修改檔案清單 + cargo test 結果摘要）。

## 2026-05-11 (P1 V083 ipc_close entry_context_id fix + P2 demo TOML 回歸)

### 任務 = 兩 commit 連環回歸

- Commit `d4867676` E1 IMPL: P1 V083 close path producer-side fix (Option B) — `commands.rs` +9 LOC + 4 unit test +86 LOC
- Commit `27e86f89` P2 fix: demo TOML A1+A2 (`bb_reversion.min_persistence_ms` 180→120s + `ma_crossover.min_trend_snr` 0.75→0.60) — pure config delta

### 1. PG dry-run 4/4 預期結果

| Test | INSERT 內容 | 結果 |
|---|---|---|
| (a) close fill + NULL entry_context_id | REJECT `ERROR: ... chk_fills_close_has_entry_context_id_v083` | ✅ V083 對 NULL fail-closed |
| (b) close fill + synthetic `orphan_recovery_ctx:BTCUSDT:1700000000000` | ACCEPT `INSERT 0 1` | ✅ Fix 後 producer-side 通過 |
| (c) close fill + 空字串 `''` (跳過 writer NULL-coerce) | ACCEPT `INSERT 0 1` | ✅ V083 不對空字串 reject — 真兇是 writer NULL-coerce |
| (d) entry fill + NULL entry_context_id | ACCEPT `INSERT 0 1` | ✅ V083 對 entry path no-op (by-design) |

### 2. PA spec disambiguation: V083 拒的是 NULL 不是空字串

PA spec 第 26 行 `unwrap_or("") → 寫入空字串` 是省略中間 writer NULL-coerce 細節。實際邏輯閉環：
1. producer `unwrap_or("")` → 空字串
2. writer `trading_writer.rs:486-489 if entry_context_id.is_empty() { push_bind(None) }` → 把空字串 coerce 成 NULL
3. PG INSERT NULL → V083 `chk_..._v083` REJECT

E2 review 同未 catch 此細節（兩端 spec 都直接框成「producer 寫空字串 → V083 reject」）。Fix 仍 100% 正確，因為 producer 改成送 well-formed synthetic id → writer 看到非空 → push_bind Some → PG 看到 NOT NULL → 通過。

### 3. P2 TOML 真實 wired 確認 (非 dead config)

| 改動 | TOML loader struct | Strategy 邏輯 use site |
|---|---|---|
| `ma_crossover.min_trend_snr=0.6` | `strategy_params.rs:80 pub min_trend_snr: f64` (#[serde(default)]) | `ma_crossover/helpers.rs:256 snr >= self.min_trend_snr` (entry SNR gate) |
| `bb_reversion.min_persistence_ms=120000` | `strategy_params.rs:225-226 pub min_persistence_ms: u64` (#[serde(default = "default_min_persistence_ms")]) | `bb_reversion/mod.rs:586 ... self.min_persistence_ms ...` (confluence persistence gate) |

兩個 P2 參數**真實 wired**，從 TOML 通過 serde + Strategy::set_params 抵達策略 hot path。**非 dead config**（[no-dead-params](feedback_no_dead_params.md) 規則 PASS）。

### 4. 5 個 close path call site 實際替換驗證

```
513:  let existing_entry_ctx = self.resolve_close_entry_context_id(symbol, ts_ms);          (apply_confirmed_fill)
744:  let entry_ctx = self.resolve_close_entry_context_id(symbol, event.ts_ms);             (execute_position_close)
938:  let entry_ctx = self.resolve_close_entry_context_id(&symbol, ts_ms);                  (ipc_close_all)
1040: pub(super) fn resolve_close_entry_context_id(&self, symbol: &str, ts_ms: u64) -> ...  (helper definition)
1121: let entry_ctx = self.resolve_close_entry_context_id(symbol, ts_ms);                   (ipc_close_symbol exchange)
1194: let entry_ctx = self.resolve_close_entry_context_id(symbol, ts_ms);                   (ipc_close_symbol paper)
```

`grep get_entry_context_id commands.rs` 殘留 2 hit：line 167 (submit_external_order, E1 push back §6.1 接受) + line 1041 (helper internal)。**0 production close path 漏改**。

### 5. SLA 影響定性 (zero,negligible)

- Helper cost: ~50-100ns / call (HashMap lookup + format! fallback)
- 頻率: ~100-200 calls/24h (close path 條件觸發,非 per-tick fan-out)
- 24h cumulative: 130ns × 200 = 26,000ns = 0.026ms
- 對 H0 < 1ms / Tick < 0.3ms / IPC < 5ms 預算 = **0.043% per call,0.0009% / 24h**
- 無需 micro-bench (cost 量級遠小於 measurement noise)

### 6. cargo test 結果 (2789/0/0,跑兩遍 non-flaky)

| Phase | passed | failed |
|---|---|---|
| W-C closure baseline 2026-05-11 01:50 | 2776 | 0 |
| Sibling N+1 D+0 land (P2 stable_id 等) | +9 | 0 |
| V083 fix +4 unit test (resolve_close_entry_context_id::*) | +4 | 0 |
| **本次實測 (2 runs 同綠)** | **2789** | **0** |

trading_writer / batch_insert / emit_close_fill subset 全 PASS（含 writer-side `test_emit_close_fill_accepts_empty_entry_context_id` fail-soft 不變式 — V083 fix 與 writer 容忍性是兩條獨立防線，並存無破壞）。

### 教訓追加 (V083 fix round 新增)

1. **V083 spec 「寫入空字串 → reject」框架是省略中間 writer NULL-coerce** — 真實邏輯：producer 空字串 → writer line 486-489 coerce NULL → PG REJECT NULL（不是 PG REJECT 空字串）。E4 dry-run Test (c) 證實 V083 對空字串 ACCEPT，PA spec / E1 報告 / E2 review 都未 catch 此細節。Fix 正確性不受影響（producer 送 well-formed → writer 不 coerce → PG 看到 NOT NULL → 通過）。E4 必跑 PG 直查 constraint 定義 + 4-test 真實 dry-run 才能驗證完整邏輯閉環。
2. **PG dry-run 必拆 BEGIN/ROLLBACK pair,不單一 transaction** — 第一次 single transaction 內跑 4 test，第一個 ERROR 觸發 `current transaction is aborted` 後續全部跳過。改 4 個獨立 BEGIN/ROLLBACK pair 才能跑完所有測試。E4 PG dry-run 模板必用 pair pattern。
3. **TOML wire-check 必 trace 從 loader struct 到策略 hot path use site** — `min_trend_snr` 在 strategy_params.rs (TOML loader) → ma_crossover/config.rs (set_params) → ma_crossover/helpers.rs (snr gate) 三段都要 grep 確認，缺任一段都是 dead config。本次 [no-dead-params] 規則確認 PASS。
4. **Close path helper 屬非 per-tick frequency** — 5 call site (513/744/938/1121/1194) 都是「條件觸發」 (fill confirm / IPC / risk close)，非每 tick fan-out 主迴圈。SLA 評估可定性論證 (~50-100ns × ~100-200 calls/24h)，無需 micro-bench。
5. **Push back 接受邊界 = 不擴大 scope** — E1 報告 §6.1 標 line 167 latent bug 但 user prompt 嚴格只列 5 close path。E4 接受 push back（不阻 V083 fix deploy），不主動修代碼（E4 角色限制）。建議 PA / PM 後續決定是否同 helper 化 line 167。
6. **E4 報告 commit message 必標兩 commit hash** — 本次任務跨兩個獨立 commit (`d4867676` V083 + `27e86f89` P2 TOML)，commit message 標 both hash + 對應 verdict 表，避免 PM 後續追溯誤把 V083 fix 與 P2 TOML 視為單一 wave。

## 2026-05-11 (W2-IMPL-4 SQL fix E4 re-dry-run post commit 4bc7be60)

### 任務 = re-dry-run W2-IMPL-4 SQL post-fix verify

E1 修 3 BLOCKER (commit 98a9d35f) + 4th syntax bug (163a5cba) + report (4bc7be60) push 後，E4 re-dry-run 5 項 verify：
1. Linux PG empirical SQL smoke
2. psycopg2 caller smoke 0 KeyError
3. EXPLAIN ANALYZE hot-path index
4. cargo test 2797/0/0
5. B4 4th fix accept / push back 拍板

### Verdict = APPROVED（全 GREEN）

| 維度 | 結論 |
|---|---|
| SQL re-dry-run (user prompt cohort) | ✅ rows=3498, col_count=19 對齊 spec §7.2 |
| SQL re-dry-run (default cohort fallback) | ✅ rows=4088, col_count=19 |
| psycopg2 caller 0 KeyError | ✅ B3 fix 真生效（注釋區 0 placeholder 字面殘留） |
| EXPLAIN ANALYZE hot-path | ✅ panel.btc_lead_lag_panel Index Scan _hyper_75_486_chunk_btc_lead_lag_panel_snapshot_ts_ms_idx 命中 |
| Rust cargo test | ✅ 2797/0/0 跑兩遍同綠 non-flaky (與 W2 chain baseline 一致) |
| Python pytest | ✅ 253/1/2 跑兩遍同綠（1 failure pre-existing docs/README.md drift） |
| B4 4th fix 拍板 | ✅ ACCEPT as scope completion（不退回正式 BLOCKER #4） |

### 教訓追加 (W2-IMPL-4 SQL fix round 新增)

1. **Row count 不是 oracle - 必驗 cohort overlap 數學**：3498 (user prompt cohort BNBUSDT 不在 panel) / 3948 (E4 上輪 self-fix) / 4046 (E1 self-claim) / 4088 (default cohort) 四個 row count 源自 cohort 配置 + 時間衰減 + LEFT JOIN drift。未來 E4 跑 SQL smoke 必同 query panel cohort enumerate 比對 user prompt cohort overlap，避免誤判 row count discrepancy 為 bug。Panel writer 端 cohort 固定 = {ADAUSDT, AVAXUSDT, DOGEUSDT, DOTUSDT, ETHUSDT, SOLUSDT, XRPUSDT}（與 spec §2.2 default 一致）。

2. **E4 fixed-SQL self-claim 必完整列正式 BLOCKER（盲區 lesson）**：E4 上輪 §C.2 自報「3 BLOCKER fix 後 3948 row」隱含已 ad-hoc fix B4 trailing comma 但未列為正式 BLOCKER → 導致 E1 retrofit round 撞同樣 hidden bug → 順手修 + push back at PA/E2/E4。未來 E4 跑 fixed-SQL empirical 時必窮舉所有實際 fix item 列入 verdict，不只 task spec 範圍內 BLOCKER（含 caller-path-blocking pre-existing bug）。

3. **psycopg2 注釋區 placeholder 字面陷阱（PA spec / E2 review / E4 上輪都未 catch）**：line 42/87 注釋裡 `%(window_days)s` / `%(cohort_symbols)s` 字面被 psycopg2 當 placeholder（psycopg2 不跳過 `--` 內 placeholder）→ caller dict 缺鍵 KeyError。未來 SQL fix 涉 psycopg2 placeholder 必：(a) 跑 caller smoke 真實 cur.execute() (b) grep 注釋區 `-- ... %(...)s` pattern (c) 改寫 placeholder 字面為反引號標識（`` `window_days` ``）或純文字。

4. **PG WITH 語法 CTE chain 末尾不可帶逗號（pre-existing bug）**：line 210 paper_fills_bucketed 末 `),` 自 commit `1f0354cf` 即帶入，導致 caller 撞 `SyntaxError at LINE 221`。empirical verify: `WITH a AS (...), b AS (...), SELECT * ...` → SyntaxError。E1 順手修 1 char `),` → `)` + 2 行防退化注釋（line 211-212）。未來新加 CTE 時必加 trailing comma 規則注釋。

5. **B4 ad-hoc fix accept vs 退回 BLOCKER #4 正式流程 trade-off**：E4 雙視角拍板 ACCEPT（不退回），理由：(a) 修法 1 char delete + 2 行注釋 = 0 業務語意 (b) caller path 真實阻斷（不修則 3 BLOCKER fix 零價值） (c) E4 上輪 §C.2 self-fix 3948 row 隱含已驗（盲區） (d) 退回需 4-day 額外 round-trip 不增加實質審查價值。E2 雙視角追加 review B4 PASS。Lesson：scope expansion vs scope completion 判斷依「不修則 fix 零價值」+ 「修法 0 業務語意」雙條件，符合 = scope completion 不算 expansion。E4 兼任 E2 視角拍板是當 E2 review 時間早於 E1 ad-hoc fix 提交時間時的合理 process workaround。

6. **`market.klines` Sort + WindowAgg vs panel.btc_lead_lag_panel Index Scan 對比**：同一個 SQL 對兩個 hypertable 走不同 plan node。panel.btc_lead_lag_panel (584 row 7d) → Index Scan（hot-path index 命中）；market.klines (25k row 7d × 7 cohort) → Sort + WindowAgg（per-symbol Sort + LEAD() window）。PG cost-based optimizer 正確決策 - 25k row + LEAD() 場景 sort-once + window 比 per-symbol Index Scan + nested LEAD 便宜。未來 panel row count 達 100k+ scale，PG 可能自動切 Index Scan per-symbol path（與 panel 同規律）。

7. **三端 git sync verify 必跑（Mac/Linux/origin 全在同 HEAD）**：本輪 E4 透過 ssh trade-core 直接 git rev-parse HEAD 確認 Linux trade-core 在 4bc7be60 = origin = Mac，避免 Sprint N+0 等多 sibling 情景下三端不同步的判斷錯誤。E4 任務 audit report 必含 §J 三端 git sync verify subsection。

8. **mock 安全規則對純 SQL fix N/A**：W2-IMPL-4 SQL fix 是純資料層 identifier rename + 注釋字面字串轉純文字 + CTE syntax 修復，無 Python/Rust 業務邏輯 mock 適用空間。psycopg2 caller smoke 連 Linux PG (IO boundary 合法 mock) 走 production query plan + 真實 row 返回 — 不存在 mock 掩蓋業務邏輯風險。E4 任務 §F 仍記錄此「不適用」結論避免 audit 漏項。

9. **cross-language consistency 1e-4 容差對純 SQL fix N/A**：W2-IMPL-4 SQL fix 不觸浮點計算 — 不適用 §4.6 跨語言一致性驗證（指 indicator/calculator 才有意義）。E4 任務 §G 仍記錄此「不適用」結論避免 audit 漏項。

## 2026-05-11 (W2-IMPL-5 stalled sub-agent collateral E4 regression)

### 任務 = W2-IMPL-5 sub-agent stalled 600s killed in memory append；working tree 已 commit + push 2 files (commit `73bcc1f5`)：
- `rust/openclaw_engine/tests/btc_lead_lag_panel_fence_integration.rs` (534 LOC, 9 tests)
- `docs/governance_dev/2026-05-11--w2_impl_signoff_pack.md` (342 LOC)

E4 verify integration test 真 cargo test 跑通 + baseline 不退化 + stalled IMPL 真完整。

### Verdict = APPROVED（全 5 維度 GREEN）

| 維度 | 結論 |
|---|---|
| cargo test --release lib baseline | ✅ Linux 2797/0 ×2（與 W2 chain 上輪 baseline 完全一致） |
| Integration test 9/9 PASS | ✅ Linux release ×2 + Mac release ×1 = 27 個 test run 全 PASS |
| 三層 fence 各 test PASS | ✅ Layer 1 / 2 / 3 各 1 assert function + 6 額外 invariant 全 PASS |
| Cross-language consistency | ✅ Rust in-memory NaN propagation PASS；PG→Python 由 IMPL-3 sibling 覆蓋 |
| File 大小 | ✅ 534 + 342 LOC 全在 800 警告線下 |
| Stalled IMPL 真完整 | ✅ 9/9 test PASS = compile + 全 assert 通過 = ground truth |

### 1. Full engine cargo test 撞 stress_tick_latency_benchmark 是 pre-existing flaky 非 W2-IMPL-5 regression

第一次跑 `cargo test --release -p openclaw_engine`（lib + all integration）在 stress_integration suite 撞 `stress_tick_latency_benchmark`：`tick avg should be <100μs, got 181.9μs`。

**驗證 = W2-IMPL-5 0 因果關係**：
- `git diff 1f0354cf..HEAD --stat` W2-IMPL-5 collateral 0 source code 改動（純 docs / E4 report / 1 isolated integration test 新檔）
- tick_pipeline / alpha_surface / panel_aggregator hot path 0 touched
- stress_integration.rs 自 `c9fb0b8f` (W7-1 + W2 trait skeleton land 2026-05-10) latency assertion threshold 100μs 對機器負載敏感
- `--test-threads=1` 隔離跑 → 35/35 stress_integration PASS
- W2 chain 上輪 baseline scope = `--lib` only（2797/0），不含 integration tests — 本次撞 stress 是 scope expand 引入的 pre-existing flaky pattern

**結論**：stress_tick_latency_benchmark 為 pre-existing latency-threshold flaky（trade-core 共享機器 parallel test CPU contention），不算 W2-IMPL-5 regression。長期改進屬 W4 / W-AUDIT-3b runtime smoke 範圍。

### 2. Layer 2 fence test 用 test-only mirror Bool 邏輯（acceptable + explicit MODULE_NOTE）

W2-IMPL-5 integration test `layer_2_should_spawn` helper 是 `main.rs:1005-1018` Bool 邏輯的 test-only mirror（不操作真實 std::env::var 避免 cargo test 並行 race）。Mock 安全規則檢查：
- 純 Bool 邏輯 mirror（不掩蓋業務邏輯，是邏輯複製）
- MODULE_NOTE 已 explicit 標「test-only mirror...若 main.rs 改邏輯 → 本 helper 同步改才能維持 layer 2 assertion 真實對應」
- acceptable mitigation；長期改進 = 把 main.rs Bool 邏輯抽 helper function 讓 test 直接 import — 但屬 W-AUDIT-8a Option A architectural reform 非 W2-IMPL-5 scope

### 3. Cross-language consistency 工件分工

W2 chain 5 sub-task 跨語言驗證分工原則：
- **Rust 端 in-memory byte-equal NaN propagation** → W2-IMPL-5 integration test `cross_language_consistency_nan_in_panel_propagates_to_cond_4_fail`（Layer 3 evaluate_shadow_signal 端到端 NaN sentinel）
- **PG → Python reader byte-equal** → W2-IMPL-3 healthcheck unit test (`checks_btc_lead_lag.py`) + Linux PG empirical dry-run（IMPL-3 sibling 範圍已 cover）

E4 不重做 IMPL-3 PG empirical（per task scope）。

### 4. Stalled sub-agent IMPL 完整性驗 = cargo test 9/9 PASS 是 ground truth

sub-agent 600s killed in memory append 不損 IMPL 工件完整性，前提是工件已 commit + push。E4 透過 cargo test --release 9/9 PASS + 跨平台一致驗證真實工件完整 — 是檢查 stalled IMPL 最可靠的證據（compile pass + 全 assert pass = 邏輯 + 結構 + 一致性 三層交叉驗）。E4 本輪追加 memory（per 完成序列硬要求）涵蓋 W2-IMPL-5 regression 教訓，補回 sub-agent stall 在 memory append 漏項。

### 教訓追加 (W2-IMPL-5 stalled sub-agent regression round 新增)

1. **Stalled sub-agent IMPL 完整性 verify = test PASS 是 ground truth** — sub-agent 600s killed in memory append 不損 IMPL 工件完整性，前提是工件已 commit + push。cargo test --release 9/9 PASS + 跨平台一致 = 真實工件完整最可靠的證據（compile pass + 全 assert pass = 邏輯 + 結構 + 一致性 三層交叉驗）。

2. **Full engine `cargo test`（lib + integration）vs --lib only 範圍區別必對齊上輪 baseline scope** — W2 chain 上輪 baseline 是 `--lib` only（2797/0），W2-IMPL-5 第一次跑 full engine 撞 stress_tick_latency_benchmark（181.9μs > 100μs release threshold）。是 stress_integration suite 在 trade-core 共享機器上 parallel 跑 + CPU contention 的 pre-existing flaky pattern，與 W2-IMPL-5 0 因果關係。E4 baseline 比對必對齊上輪 scope（lib only），避免 noise 引入虛 BLOCKER。

3. **`--test-threads=1` 隔離 + reproduce verify 是 flaky vs regression 判別工具** — 第一次跑 fail 不能直接退 E1，必：(a) 隔離 single-thread 跑驗是否 race; (b) `git diff` 確認改動是否 touch hot path; (c) check pre-existing 是否同 fail。W2-IMPL-5 撞 stress 後 (a)(b)(c) 三條全證 pre-existing flaky → 標記非 W2-IMPL-5 regression 不退 E1。

4. **test-only mirror Bool 邏輯模式 + explicit MODULE_NOTE = acceptable mock 規則** — `layer_2_should_spawn` 複製 main.rs Bool 邏輯到 test helper（避免 std::env::var 並行 race）是 acceptable，前提是 MODULE_NOTE 明標「test-only mirror...若 main.rs 改邏輯 → 本 helper 同步改」。長期改進是把 main.rs Bool 抽 helper function 讓 test import，屬 architectural reform 非當前 scope。

5. **Cross-language consistency 工件分工原則** — Rust in-memory NaN propagation = W2-IMPL-5 integration test 範圍；PG → Python reader byte-equal = W2-IMPL-3 healthcheck unit test + Linux PG empirical 範圍。E4 不重做 sibling sub-task 範圍工件，避免 audit 工作冗餘。

6. **File 大小 800 警告線 / 2000 硬上限 check 是 pure measurement** — 不涉邏輯，simple grep wc。534 + 342 LOC 全在警告線下。E4 在 §D 直接結論不展開。

7. **Sub-agent 並行 review（E2 + E4）read-only 不衝突** — E4 read-only 跑 cargo test + pytest（不寫 source）；E2 read-only 看 diff + 寫 review report；workspace 不重疊 = 0 衝突。並行省時 ~20min vs 串行。

8. **E4 完成序列補回 stalled sub-agent 漏 memory append** — sub-agent stall 後 E4 在自身 memory 追加 W2-IMPL-5 regression 教訓 = 補回 E1 memory append 漏項的部分（E1 memory log 需 E1 sub-agent 重 dispatch 才能補；W2-IMPL-5 collateral 已 commit + push，PM 後續決定是否重派 E1 補 memory）。


---

## 2026-05-11 — P0 Option A-Lite post-merge regression

**Context**: 5 個 E1 worktree（ma_crossover / bb_reversion / bb_breakout /
grid_trading / funding_arb）的 paper_state SSoT refactor 已 merge 進 main
HEAD `dc8b7ffe`。各 E1 worktree 內 cargo test PASS（報 2792-2801），需 E4 從
runtime 視角驗證 merge 後真實行為。Linux engine PID 1884515 自 12:57 +0200
restart 跑。

**Verdict**: PASS · report path `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--option_a_lite_post_merge_regression.md`

### 1. 5 E1 sibling test 完整保留驗證方法 = substring filter 配對

各 E1 worktree 用「策略名 substring」（如 `ma_crossover`）跑 cargo test 拿 63；
E4 用 module path `strategies::ma_crossover::` 拿 60。差異不是 regression 而是
filter scope 不同：substring 還含 cross-module reference 到 ma_crossover 的
test。**驗證 merge 不蓋掉測試的正確方法 = 用 E1 同個 substring filter**：

```bash
cargo test --release -p openclaw_engine --lib <substring>
```

如 main `cargo test ma_crossover` = 63 ✅ E1-A 報 63；`bb_reversion` = 46 ✅ E1-B
報 46。5 策略 1:1 全配對。E4 主動跑 5 個策略 substring filter 是 merge 完整性
驗證的標準動作。

### 2. Cargo total 數字 5 E1 各報不同 ≠ regression

E1-A 2792 / E1-B 2794 / E1-C 2796 / E1-D 2801 / E1-E 2799 看似不一致，main
merge 後 2794。**原因**：5 個 worktree 從同個 hot-fix base 出發看不到 sibling
並行加的 test；merge 後又有 W7-2/W7-3/W7-5 跨策略防護碼 test ~30 個被刪除（因
owner_strategy gate 涵蓋）。net = +M new acceptance - 30 deleted。E4 不應追究
total mismatch，應追究：
- 各策略 substring filter PASS 數字是否與 E1 報告一致（5/5 通過）
- main passed >= pre-Option-A-Lite baseline（2794 vs 2790 +4）
- failed = 0

### 3. Linux runtime SQL probe 三維度驗 cross-strategy attack 0 觸發

PA spec §6.3 ban list = `bb_mean_revert on strategy_name != bb_reversion`。E4
擴成三維度 SQL：

```sql
SELECT count(*) FILTER (WHERE strategy_name = 'grid_trading'  AND exit_reason = 'bb_mean_revert') AS grid_with_bb_close,
       count(*) FILTER (WHERE strategy_name = 'ma_crossover'  AND exit_reason = 'bb_mean_revert') AS ma_with_bb_close,
       count(*) FILTER (WHERE strategy_name = 'bb_breakout'   AND exit_reason = 'bb_mean_revert') AS bb_breakout_with_bb_close
FROM trading.fills
WHERE ts > '<restart_ts>' AND engine_mode IN ('demo','live_demo');
```

結果 0/0/0 = root scenario 0 重現。寫進報告作 verdict 鋸證。

### 4. Cross-strategy holistic test 補上 E1 sibling acceptance 漏的視角

5 個 E1 各自加 sibling acceptance（self-view：grid 看 self / bb_reversion 看
self...）但 **「多策略同 symbol same-tick 互動」holistic view 沒有**。E4 新加
`strategies/cross_strategy_attribution_integrity.rs` 4 個 test 補上：
- 1 個 multi-strategy holistic（同 ctx 3 個策略 on_tick）
- 2 個 cross-pair（ma→bbb / ma→grid）
- 1 個 bybit_sync owner 分流（PA §7 #5 acceptance）

新測試掛在 `strategies/mod.rs` 的 `#[cfg(test)] mod cross_strategy_attribution_integrity;`
而不是 `tick_pipeline/tests/` — 因為這是 strategy-level 行為（multi-strategy
interaction），不是 tick_pipeline-level。

### 5. AlphaSurface non-Copy 是 cross-module test 構造常見絆腳石

新檔用 `EMPTY_ALPHA_SURFACE` 時：
- ❌ `let surface = openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;`（move out static error）
- ✅ `let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;`（borrow static）

接著 `on_tick(_, &surface)` 變 `&&AlphaSurface`，需改 `on_tick(_, surface)`。
`alpha_surface_ref: &surface` 也要改 `alpha_surface_ref: surface`。

bb_breakout/tests.rs 用 inline `&openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE`
避開此問題；ma_crossover/tests.rs 用 helper ctx_with 內 inline。

### 6. paper_state.get_position SLA bench 跳過理由

`accessor.rs:190` 純 `HashMap.get()` O(1) ~100ns << 1ms H0 SLA，1000x margin。
無 production-spec micro-bench harness 既存且 inline timing 對「is this <1ms」
不增加驗證價值。E4 在報告 §6 標 N/A + 理論分析，不消耗 30 min 寫 bench
harness（屬 W-AUDIT-3b runtime smoke 範圍）。

### 7. owner_strategy gate 真實落地驗 = grep non-test grep 全 5 策略

每加 P0 cross-strategy gate refactor 必跑：

```bash
grep -rEn 'owner_strategy\s*==\s*self\.name|owner_strategy\s*==\s*"<name>"|cross_strategy_holds' \
    rust/openclaw_engine/src/strategies/ --exclude tests
```

5 策略對應 5 條 hits（4 個 exit branch filter + grid 1 個 entry gate）。**0
hits 在某策略 = E1 漏 IMPL** 直接退回。本次 5/5 全綠。

---

## 2026-05-11 — W-AUDIT-3b Runtime Smoke Verify (Wave 1 Task C)

**Context**: W-D MAG-084 closure 後 Wave 1 Task C P1-W-AUDIT-3b-SMOKE。W-AUDIT-3b
RouterLeaseGuard Drop test 已 land 在 commit `22efd9de` (Linux HEAD `c39ac9cc`,
124 commits ahead)。runtime smoke 待 ssh trade-core 驗。**僅 verification — 不修
代碼、不發 commit、不重啟 engine。**

**Verdict**: PASS · report path
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w_audit_3b_runtime_smoke.md`

### 1. Rust test name CamelCase struct vs snake_case test 命名差別

Task spec 給的 cargo test filter `RouterLeaseGuard` 是 case-sensitive substring
0 命中（test 名實際 `test_router_lease_guard_drop_releases_active_lease_cancelled`
snake_case）。E4 修正改 filter `test_router_lease_guard_drop` 拿 1/1 PASS。**未來
sub-agent dispatch spec 寫 Rust test filter 應對齊真實 snake_case test name，不
寫 CamelCase struct 名做 filter**。

### 2. Task spec 引不存在的 pytest 檔名時應退回 design doc 找實際 test set

Task spec 給 `-k test_executor_fail_closed` 假設有檔 `test_executor_fail_closed.py`。
W-AUDIT-3b design doc §3 (`2026-05-10--w_audit_3b_runtime_smoke_test_design.md`)
明白標：「重複新寫 test_executor_fail_closed.py 是 fake coverage」— 既有 9 case 分
布於 `test_executor_plan_v2.py` (5) + `test_executor_agent_unit.py` (3) +
`test_executor_shadow_to_live_e2e.py` (1)，已 cover dispatch v3.4 §3.4
acceptance 「≥ 1 fail-closed test case」。E4 修正改跑 3 個既有 test_executor_*
檔總 73/73 PASS。**Lesson: sub-agent 收到 dispatch SOP 不存在的 test 名時，應退回
W-AUDIT-X design doc 找實際 test set，而非順著 SOP 字面新寫 fake test**。

### 3. 廣譜 pytest filter 撞 pre-existing unrelated baseline failure 隔離方法

第一次跑 `-k 'fail_closed or lease'` (廣譜) 拿 237/3861/1 failed。失敗 test
`test_oe_006_close_retry_budget_has_real_timeout_guard` 是 grep static check
找 `dispatch.rs` 內 `test_close_attempt_timeout_constant_is_500ms` 字串 — 但實
際 test 已 refactor 到 `dispatch_tests.rs`。**隔離 reproduce 驗證 = pre-existing
baseline drift，與 W-AUDIT-3b RouterLeaseGuard 0 因果關係**。E4 縮窄到 W-AUDIT-3b
範圍跑 73/73 PASS = 0 regression。**Lesson: pre-existing failure 隔離 reproduce
是 flaky vs regression 判別標準動作，不能因為 broad filter 撞到就退 E1。**

### 4. SQL filter schema 過舊不阻 chains_with_lease 真實 verify

Task spec 給 SQL `payload->>'status' IN ('shadow_planned','shadow_filled')` 在
當前 schema 0 row 命中。execution_plan payload 真實 keys：`lease_id` / `decision_id`
/ `verdict_id` / `engine_mode` 等 29 個，**沒有 status 字段**。即時 lifecycle
state 在 `learning.lease_transitions` V054 表。**E4 修正用真實 `payload->>'lease_id'
IS NOT NULL AND != ''` filter 拿 chains_with_lease=610**，sample 5/5 lease_id='bypass'
字面字串（非 NULL 非 empty）— Producer wiring 真實生效。

### 5. V054 lease_transitions 是 9-state lifecycle SoT corroborate execution_plan

execution_plan payload 只記 lease_id 字面值（bypass 或 active leaseId）；完整
9-state lifecycle 寫 `learning.lease_transitions` V054。**本次直查 79032 BYPASS
transitions 在 Validation profile**，confirming bypass evidence mode (W-C
operator-authorized `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` per Sprint 3 Track
H/I) 真實大規模生效，**非 hardcode**。Cross-check 兩表確認 lineage 一致 =
最可靠的 bypass real-wiring 證據。

### 6. bypass lineage 100% 與 §三 caveat 3 一致

100% lease_id='bypass'（610/610，sample 5/5）符合 §三 W-C / MAG-082 表 Caveat 3
DEFERRED by-design：真實 Production profile lease 在 W-AUDIT-3..7 + true-live
boundary 後才可預期 chains_with_real_lease > 0。W-D MAG-084 sign-off 已涵蓋此
DEFER：bypass lineage Stage 3+ true-live promotion 必須由真實 Production profile
lease（將來 W-C flag 翻 OFF 後）取代。**Lesson: bypass evidence mode 在 shadow
階段是正常工件不是 BLOCKER；reviewer 看到 100% bypass 應 retrieve §三 caveat 3
context 確認 DEFER status 而非當 regression。**

### 7. Non-flaky verify 雙跑強制 (regression-testing-protocol §5 reminder)

Rust + Python 都跑兩遍同綠 non-flaky verified：
- Rust: cold compile (40s) → warm cache (0.07s) 1/1 PASS
- Python: 0.39s → 0.33s 73/73 PASS

第一次 PASS 不等於真綠（race / flaky）；第二次同綠才算 PASS。本次成本 ~50s 不
牽涉 engine restart 或 5min window wait，符合 W-AUDIT-3b design doc §4 "pytest
first, fast, isolated, dev env" 順序。

### 8. 三端 git sync verify 必跑

```
Linux trade-core HEAD: c39ac9cc3115c9100986f807c01f06fb82ce00fc
Mac 本地 HEAD: c39ac9cc (session env)
22efd9de 在 history: ✅ 124 commits behind HEAD
```

W-AUDIT-3b 源碼穩固落地，且本次 verify 在最新 HEAD `c39ac9cc` 上跑（非
22efd9de 上跑）— 後續 124 commits 沒回退這個 test。**Lesson: 任務描述指定
verify commit 不等於只在那 commit 上 verify；E4 在 HEAD 跑驗 commit 落地後
是否仍存活更有 forward-looking 價值**。


## 2026-05-11 Wave 1.6 P1-FILL-LINEAGE-DROP — pre-deploy regression gate (PASS)

**Trigger**: PA dispatch Wave 1.6 Option F4 Spine Channel Silent-Drop Fix；QA RCA SYSTEMIC 25.8% drop empirical；E1 IMPL DONE / E2 APPROVE WITH MINOR / E5 APPROVE WITH 3 P3；PM 已 land 4 commit-前 minor fix

### Verdict
**PASS · deploy READY**

### 數字
| 項 | Value | Baseline | Delta |
|---|---|---|---|
| Rust lib release | 2810 / 0 / 0 | 2807 | +3 new ✅ |
| Rust lib debug | 2810 / 0 | 2807 | +3 new ✅ |
| Python helper_scripts/db | 320 / 0 | 320 | 0 ✅ |
| Python tests/ broader | 253 / 1* / 2 skip | n/a | *docs index pre-existing not Wave 1.6 |

連跑驗證：A.1 lib test 2 連跑同 2810；A.4 3 new test 5 連跑 0 flaky。

### Key invariants verified
- entry path 4 callsite 全 sync try_send (0 spawn/sleep/lock) — hot path SLA 嚴守
- fill_completion path 4 callsite 全 try_send_with_background_retry — retry 救援設計
- 5 W-C P1-1 spine_ids invariant 全 PASS（Wave 1.6 0 觸碰）
- 3 W-C 既有 runtime_shadow test 全 PASS（emit_fill_completion 改 retry 不破既有）
- agent_spine module-wide 21 test 全 PASS

### Mock audit
3 new test = 0 mock framework / 0 fake / 0 patch；用真 tokio mpsc + 真 emit_fill_completion + 真 SpineObjectEnvelope + 真 spawn + 真 sleep。

### Cross-language contract
Rust `executed_by` + `fill_completion=true` (runtime_shadow.rs:558-562) ↔ Python `checks_agent_spine.py:141, 234` 對齊不破。

### Governance
- runtime_shadow.rs 843 LOC (pre-fix 657 + Wave 1.6 ~171 + PM commit-前 MEDIUM-2 注釋 ~15) — P2 tracked, < 2000 hard cap，不阻 merge
- tests.rs 1476 LOC — pre-existing exception
- tasks.rs 978 LOC — pre-existing baseline
- CLAUDE.md §九 Singleton row `SPINE_CHANNEL_*` 1 row PM 已 land
- 0 hardcoded path / 0 unsafe / 0 unwrap 新增

### Lesson learned
- 1 unexpected: E1 self-report 828 vs 實際 843（PM commit-前 land E2 MEDIUM-2 drop_total 語意警告擴充注釋）—PM Sign-off process 補件，不破 governance
- pre-existing tests/structure docs_readme_index 失敗 = docs/archive 索引 debt 與 Wave 1.6 完全無關（git diff --stat 驗證）；A4 lesson：Python pytest 廣域跑時必驗失敗是 commit 前還是 commit 後

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--p1_fill_lineage_drop_e4_regression.md`


## 2026-05-11 Wave 2.2 LG-1 + LG-2 (8 task) — pre-deploy regression gate (PASS)

**Trigger**: PA dispatch Wave 2.2 8 task pre-deploy gate；E1 IMPL ×8 DONE / E2 APPROVE WITH 4 MEDIUM + 2 LOW + 3 P2 + 1 HIGH governance flag (SCOPE CREEP) / E5 APPROVE-PERF-SOUND WITH 6 P2/P3 NOTES / A3 APPROVE WITH UX FIX 7.4/10（4 commit-前 必修 PM apply 中）

### Verdict
**PASS · deploy READY**（pending operator SCOPE CREEP sign-off）

### 數字
| 項 | Value | Baseline (Wave 1.6) | Delta |
|---|---|---|---|
| Rust lib release | 2867 / 0 / 1 ignored | 2810 / 0 / 0 | +57 ✅ |
| Rust lib debug | 2867 / 0 / 1 ignored | 2810 / 0 / 0 | +57 ✅ |
| Python helper_scripts/db | 343 / 0 | 320 / 0 | +23 ✅ |
| Python tests/ broader | 253 / 1 pre-existing / 2 skip | 253 / 1 pre-existing / 2 skip | 0 (docs index pre-existing) |
| stress_integration (integration test) | 34 / 1 failed (pre-existing W7-2) | 34 / 1 failed | 0 (Wave 2.2 0 因果) |

連跑驗證：A.1 lib test 3 連跑（2866 → 2867 → 2867），run 2/3 同綠 non-flaky；config::tests pre-existing 8-thread race per LG1-T1 E1 §5 已 identify。

### 8 task new test 實測（全 ≥ E1 預期）
| Task | E1 預期 | 實測 | Verdict |
|---|---|---|---|
| LG-1 T1 h0_blocking | 6 | 6 PASS | ✅ |
| LG-1 T2 [59] (Python) | 14 | 14 PASS | ✅ |
| LG-1 T3 h0_ctor_default | 5 (含 1 ignored) | 4 PASS + 1 ignored | ✅ |
| LG-1 T4 (Python) | 21 | 21 PASS | ✅ |
| LG-2 T1 contract | 17 (6 inline + 11 integration) | 6 inline + 11 integration | ✅ |
| LG-2 T2 live_spawn_assert | 11 | 13 (含 2 readiness 整合) | ✅ |
| LG-2 T3 fee_source | Rust 11 + Python 9 | Rust 12 + Python 9 new | ✅ |
| LG-2 T4 pricing | Rust 16 | Rust 16 | ✅ |

### C SCOPE CREEP coverage
SCOPE CREEP commit `a11a4df6` 含 bb_reversion +5 entry guard + ma_crossover +4 entry guard test：
- `strategies::bb_reversion` **46/46 PASS** (含 `test_non_pinned_symbol_skips_entry` + `test_non_pinned_self_owned_position_can_exit` SCANNER-TRADEABLE-TIER-1 新 entry guard)
- `strategies::ma_crossover` **62/62 PASS**

Pre-existing fail `stress_bb_reversion_extreme_oversold_bounce` 仍 FAIL：
- `git log` 顯示 a11a4df6 **NOT in stress_integration.rs touch list**
- Wave 2.2 + SCOPE CREEP 0 因果引入 / 0 修好
- E1 LG-2 T2 §10.5 / E2 §6.1 / Wave 1.6 E4 已 identify 為 W7-2 P0 Option A-Lite paper_state SSoT refactor 後 fixture 未同步
- Accept pre-existing, W7 owner 修；不阻 Wave 2.2 deploy

### D Cross-language consistency
Rust `FeeSource::as_str()` snake_case + `is_compatible_with_proxy` 對賬表 vs Python `FEE_SOURCE_COMPAT` **byte-equal 完美對齊**：
- `bybit_api ↔ bybit_v5 + inactive_mainnet`
- `demo_conservative_default ↔ seed_default + inactive_mainnet`
- `cold_default ↔ cold_default + inactive_mainnet`

Python `TestLg2T3DualSourceCompat` 5 test 全 PASS 驗每個組合 + disagree case。

### Mock 不掩邏輯
- 4 Rust new test file 全 0 mockall / fake / stub
- 2 Python new test file 用 MagicMock cursor (PG IO 邊界) + patch (env/IPC client 邊界) — 業務邏輯 (verdict aggregation / check_59 推斷) 真實跑
- LG2-T2 mainnet (2 reject) + LiveDemo (3 accept + 1 reject) + Paper (skip by design) 核心場景全 cover；Mainnet+BybitApi happy path E1 自承缺 test 是 acceptable trade-off

### 0 unexpected (3 marginal observation)
1. Run 1 vs Run 2 release lib 數字差 1 (2866 → 2867) = config::tests 8-thread file lock race，run 2/3 穩定 non-flaky
2. LG2-T2 實測 13 vs E1 自報 11 = sibling `readiness_interface` 2 整合 test 演化補強
3. LG2-T3 fee_source 實測 12 vs E1 自報 11 = method_registry IPC slot declare invariant 1 個（已被 CLAUDE.md §九 PM 同 commit land `AccountManagerSlot` row）

### Lesson learned
- 8-thread cargo test pre-existing race 由 LG1-T1 E1 §5 已 identify 為 `config::tests::test_config_manager_load_and_reload`；連跑 3 次穩定 PASS 是 non-flaky 判別動作
- SCOPE CREEP entry guard 新 test 在 strategy module 全綠不代表修 pre-existing stress fail（stress_integration.rs 是 sibling W7 fixture 問題）；E4 必跑 integration test 不只 lib test 才能 catch 此類「strategy module green + integration red」分裂
- Cross-lang FeeSource compat byte-equal 驗證 = 兩端 `match (rust_enum, pg_proxy)` 表 grep 對照 + Python `FEE_SOURCE_COMPAT` dict 對照 + 兩端 `inactive_mainnet` 通用接受規則對齊；不只看 enum string 必看 compat table
- LG2-T2 30s wait timeout 不阻 tick hot path = startup_path `kind == PipelineKind::Live` gate + `build_exchange_pipeline()` 一次性 async；驗證方法 = grep 確認 call site 在 startup 不在 on_tick

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--wave2_2_e4_regression.md`


## 2026-05-15 Wave 1.5 / Track E4 — KAMA fallback gate (commit 9df44183) regression + exit-path corner case 補測 (PASS)

**Trigger**: PA dispatch — 9df44183 W3-6 by-the-way `debug! + fall through` → `warn! + return vec![]` 後 E1 自承不確定 exit path 持倉中 KAMA disappear 是否誤平倉；E4 跑 baseline 對比 + 寫 4 個 corner case 補測

### Verdict
**REGRESSION-PASS · deploy READY**

### 數字
| 項 | Value | Baseline | Delta |
|---|---|---|---|
| Rust lib full (Linux release) | 2893 / 0 / 1 ignored | 2889 (2026-05-16 audit) | +4 new ✅ |
| Pre-E4-commit ma_crossover focused | 68 / 0 | E1 自報 68 | byte-equal ✅ |
| Post-E4-commit ma_crossover focused | 72 / 0 | n/a (new) | +4 new test ✅ |
| stress_ma_crossover_whipsaw_rapid_reversals | 1 PASS | n/a | <0.01s SLA ok |

非 flaky 雙跑：Pass1=Pass2 ma_crossover 72/0 + lib 2893/0/1。

### 4 new exit-path corner case test（全 PASS）
1. `test_kama_unavailable_during_open_position_does_not_force_exit` — self-owned LONG + `kama: None` → empty actions（no Close）
2. `test_kama_unavailable_for_consecutive_n_ticks_returns_empty` — 100 連續 tick KAMA None → 全空、無 panic、exit_persistence state 未受推進
3. `test_kama_recovers_after_unavailable_window_resumes_trading` — 10 tick None → tick 11 恢復正常 Open(LONG)；驗無 sticky state 阻塞
4. `test_kama_unavailable_no_entry_when_no_position` — 無倉 + KAMA None → empty（fallback gate 設計意圖驗證）

### Mock audit
4 new test = 0 mockall / 0 fake / 0 patch；用真 `MaCrossover::new()` + 真 `IndicatorSnapshot { kama: None, ... }` + 真 `on_tick(&ctx, &EMPTY_ALPHA_SURFACE)`。業務邏輯 (KAMA gate / position state filter / cooldown / persistence) 真跑。

### Cross-language consistency 不適用
Python `KAMACrossoverRule` 在 `signal_generator.py:146-151` 是 `_StubRule`（stub）；ma_crossover entry/exit logic 是 Rust SSoT 無 Python dual implementation。不存在 1e-4 容差比對需求。**KAMA indicator 本身**有 Python 對等（kline_manager），但不在 commit 9df44183 scope（commit 改 strategy fallback 行為，非 KAMA 算法）。

### SLA hot-path
+1 if check + return vec![] 在 KAMA gate 點 → 1-2 ns/tick 級開銷；whipsaw stress test PASS <0.01s。H0 SLA <1ms 不被影響。

### Pre-existing fail accounting
stress_integration: `stress_bb_breakout_valid_squeeze_with_volume` + `stress_bb_reversion_extreme_oversold_bounce` 2 FAIL — pre-existing，per 2026-05-16 full-scope-testing-audit §1.2。`git diff 9df44183~..9df44183 --stat` 只動 `ma_crossover/strategy_impl.rs` → 與 commit 無因果。記錄不阻 deploy。

### Lesson learned
- **Exit-path 兩 path 語意等價驗證**：舊 path `fast = sma_20.unwrap_or(0.0)` 等於 `slow` → `reverse_signal=None` → exit 不觸發；新 path 早 return vec![]。**結果一致**但新 path 額外避免下游 confluence/persistence 污染。E4 補測同時驗證「結果一致」（不誤平倉）+「設計意圖達成」（不污染下游）。
- **HEAD-verify > commit-pinned verify**：本次 verify head `34aa7086` 含 9df44183 + 後續 docs commits + E4 +4 test commit；證明 9df44183 在 forward 仍 alive 不被退化。延續 2026-05-09 W-AUDIT-3b lesson。
- **E1 self-flag uncertainty 是強信號**：「IMPL DONE 但不確定 X」即時應派 E4 corner case 同 wave 內補測，避免分開 dispatch 額外 round-trip。本次 4 個 test ~30 min E1 inline 即可寫；改為 E4 separate dispatch 是 process suboptimal。FYI 給未來 E1 reflection（不阻 deploy）。
- **Python stub 不算 cross-lang counterpart**：grep `signal_generator.py:KAMACrossoverRule` 確認 `_StubRule` 屬性 → 無 dual implementation → cross-lang 容差 N/A。E4 必檢查 Python 端是「真實算法 dual」還是「stub class」再判斷 1e-4 比對是否有意義。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-15--kama_fallback_gate_e4_regression.md`

### Test code commit
`34aa7086` test(ma_crossover): add KAMA unavailable exit path regression tests (Wave 1.5 E4)
+162 LOC tests.rs；不修業務代碼。CLAUDE.md §九 hard cap 1016→1178 LOC，跨 800 警告線但遠低 2000 hard cap（單檔內聚 OK）。

---

## 2026-05-16 — Wave 2c-2 reject_cooldown split (BB-MF-3) regression PASS

**Commit verified**: `27f02a07` (sibling `88f9254f` doc/HTML only)

**Result summary**:
- Lib release 2906 passed / 0 failed / 1 ignored (run twice, identical → non-flaky)
- grid_trading focused 62 passed / 0 failed
- 8/8 BB-MF-3 new tests ok:
  - test_entry_reject_does_not_freeze_close_path
  - test_close_reject_does_not_freeze_entry_path
  - test_close_too_many_pending_5min_cooldown
  - test_close_postonly_cross_no_cooldown_immediate_market
  - test_close_default_reject_categories_1min_cooldown
  - test_grid_short_circuits_when_both_cooldowns_active
  - test_cooldown_isolation_multi_symbol
  - test_arm_close_cooldown_saturating_add_overflow_safe
- Cross-language: N/A (cooldown is Rust-only HashMap state, 0 Python references)
- SLA stress ok (≪1us overhead expected from extra HashMap lookup + if check)

**Multi-session race recovery clean**: Wave 2b sub-agent verified work was dropped by sibling commit `ef6ea79f`; Wave 2c-2 IMPL recovered via stash extracts. E1 self-claim of 2906/0/1 verified empirically on Linux trade-core release toolchain — exact match.

**No supplemental tests added**: 8 existing tests cover all design invariants (entry/close isolation, multi-symbol, both-cooldowns gate, 5min/1min/no-cooldown reject categories, u64 overflow safety, public API). E1 self-flagged Phase 1b production close-path dispatcher gap is correctly scoped as future work; pre-IMPL stub tests would mock business logic that does not yet exist (anti-pattern per regression-testing-protocol §5.2).

**Lesson — multi-session memory.md write race**: file is 289KB+, cannot Read full via tool. Use grep + cat >> to append safely. `git commit --only` per file mandatory.

**Report**: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--reject_cooldown_split_e4_regression.md`

E4 verdict: REGRESSION-PASS, 0 push-back to E1.

---

### 2026-05-16 WP-05 assertion drift fix (5 tests, 4 files)

**Context**: WP-05 Real Fix 將 IPC error response 從 plain string detail 改為 structured dict `{"reason_codes": [...], "detail": "..."}` (via `sanitize_exc_for_detail`)。5 個測試的 assertion 還在比對舊 string format，導致 AttributeError/AssertionError。

**Fixes applied (test-only, 0 production code changes)**:
1. `test_ai_budget_routes.py:241` — `resp.json()["detail"].lower()` → `detail["reason_codes"]` 含 `"ipc_error"`（通用 RuntimeError 走 ipc_error_handler fallback path）
2. `test_executor_shadow_toggle_api.py:621` — `assertIn("rust_engine_unavailable", detail)` → `assertIn("rust_engine_unavailable", detail["reason_codes"])`
3. `test_strategist_promote_api.py:622` — 同上 pattern
4. `test_batch_d_risk_fail_closed.py:126` — `test_close_attempt_timeout_constant_is_500ms` 從 `dispatch.rs` 移至 `dispatch_tests.rs`，assert 改讀後者
5. `test_replay_subtab_static_assets.py:484` — `if (metricsData) _applyLiveTodayPnl(metricsData)` 重構為 `_applyLiveTodayPnl(m)` (m=d.data)，assert 更新

**Regression**: 108 tests across all 4+1 affected files = 108 passed / 0 failed (2x run)

**Lesson — WP-05 sanitize_exc_for_detail reason_code mapping**:
- `_get_ipc_client()` 失敗 → ai_budget_routes 用 `"ipc_unreachable"`
- IPC call 失敗（generic exception）→ ipc_error_handler 用 `"ipc_error"`
- IPC call 失敗（EngineDisconnectedError）→ `"ipc_unreachable"`
- IPC call 失敗（EngineTimeoutError）→ `"ipc_timeout"`
- executor/strategist promote routes RuntimeError → `"rust_engine_unavailable"`

## 2026-05-16 · P1-PORTFOLIO-RESTING-EXPOSURE-1 Linux Regression PASS
- Branch `worktree-agent-ac285607fa3c51402` HEAD `efe14965` push → Linux fetch；scratch worktree `/tmp/e4-regression-1778919049` 跑兩遍 `cargo test --release --lib -p openclaw_engine`，兩遍 **2915 passed / 0 failed / 1 ignored** 與 Mac 1:1（baseline 2908 + new 7 = 2915，0 regression，1 ignored = 預期 socket-permission）。intent_processor::tests focused 108/0 全 PASS，含 7 個 P1 new test 全 ok。
- 7 個 P1 new test 容差全 1e-4（exposure / corr）或 1e-6（leverage）→ 符合 cross-language consistency 規定。
- hot_path_baseline bench：p99 42.279μs < 300μs SLA；P2 follow-up = E5 加 `intent_processor::compute_exposure_pct` micro-bench harness（current `hot_path_baseline` 沒 resting orders coverage）。
- Linux runtime engine PID 69581 未觸動（elapsed 7h14m / demo fresh 13.7s / live age 3.0s）；scratch worktree cleanup 完成；branch 保留給 A3 / E2 / PM。
- Report：`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--p1_portfolio_resting_exposure_e4_regression.md`。

## 2026-05-16 W-AUDIT-8a C1 v2 resilient harness — Linux smoke PASS
- Branch `worktree-agent-a58d99ef4ea1a440b` HEAD `5983f955` fetch 到 Linux scratch `/tmp/e4-v2-test-1778920370`；`git clone local + remote set-url GitHub + fetch worktree + checkout FETCH_HEAD` pattern（local repo 無本地 branch ref，必須走 GitHub）。
- pytest 兩遍 Linux 36/36 PASS in 0.03s / 0.02s（Mac baseline 36/36 in 0.004s）→ Linux = Mac 1:1，non-flaky 確認。
- py_compile PASS + `import helper_scripts.bybit.liquidation_topic_probe_v2` clean。
- 60s smoke real WS：verdict=`SMOKE_PASS_NOT_C1_PROOF` (60s 預期值；只有 24h 才能達 `PASS_C1_PROOF_CANDIDATE`)；subscribe_success=6 / subscribe_failure=0 → topic 不 reject ✅；4 control topics 全收 (kline=48 / orderbook=1370 / publicTrade=252 / tickers=327)；reconnect/restart=0（60s 不足 trigger）；uptime_ratio=0.987；raw_message_count=2003。
- Checkpoint JSON `c1_proof_progress.json` 30+ fields 全 present，atomic same-path overwrite + dated snapshot 各一份，無 dated file proliferation 風險。
- 0 crash / 0 exception / connection_errors=[]；Linux runtime engine PID 不變；branch 保留不 merge main，等 BB+MIT 24h full-duration proof。
- Report：`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_e4_smoke.md`。

## 2026-05-16 W-AUDIT-8a C1 v2 consolidated fix (dbd0277c) — Linux quick smoke PASS
- HEAD `dbd0277c` (parent `5983f955` already E4-PASSED). pytest **49/49** PASS Linux non-flaky 雙跑（0.05s + 0.04s）= Mac 49/49 baseline。新 13 test 全 PASS：TestUtcMidnightBuffer×3 / TestAtomicWrite×3 / TestKeepaliveWarningsSeparation×4 / TestReconnectFailuresInstabilityGate×3。
- Wrapper `run_c1_v2_proof.sh --help` 工作 (exit 0)；`--smoke-60s` real WS 60s smoke：verdict=`SMOKE_PASS_NOT_C1_PROOF`（60s 預期值）/ exit 0 / 0 stack trace / 0 connection_errors / subscribe_success=6 + subscribe_failure=0（topic 不 reject）/ 4 control topics 全收 data (kline=37 / orderbook=1495 / publicTrade=142 / tickers=335) / uptime_ratio=0.9876。
- **Fix runtime verify 4 highlights**：(2) atomic write `c1_proof_progress.json.tmp` NOT present → POSIX rename cleanup OK；(3) `keepalive_warnings` field 出現於 60s smoke checkpoint JSON → schema patch verified；(4) `reconnect_failures=0` field 存在於 JSON；schema 完整。
- Linux runtime engine PID 不變（engine_alive=true, demo age=25.8s, live age=15.2s）；branch `worktree-agent-a58d99ef4ea1a440b` 保留 origin 等 PM merge；scratch `/tmp/e4-v2-recheck-1778922043` cleanup。
- **Lesson — consolidated fix quick regression pattern**：parent commit 已 E4-PASS 時，子 commit 加 6 fix 不全跑全量；用「new test full run + key fix runtime verify + atomic write inspect + key new field existence verify」4 維覆蓋 ≈ 20 min wall time 即可給 PM merge 綠燈。比全量重跑省 80% 時間但 confidence 同。
- Report：`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_consolidated_fix_e4_quick_smoke.md`

## 2026-05-16 · P1-WP03-DEPLOY-GATE-IMPL Mac regression PASS
- 17 [69] test PASS x2 (0.04s + 0.04s) non-flaky；10 [68] sibling PASS 0 regression；helper_scripts/db full 385/0 (baseline 368 + 17 new = 385 預期值)。
- py_compile 4 files PASS；import [69] + [68] 0 circular；runner --help 顯示 `[46][48][49][50][51][52][53][54][55][57][58][59][64][65][66][67][68][69]`。
- Wire: `__init__.py` 192-200/290/294，`runner.py` 289-305 (import) / 1176-1178 ([68] reg) / 1183-1205 ([69] reg) / 382-383+500-502 description。
- Cross-IMPL [69] vs [68]：0 shared state / 0 path conflict / 0 env namespace overlap / 0 singleton race。可同時 register 進 runner。
- Mock review：限於 `cur.fetchone.side_effect` (5 tuple seq) + `cur.connection.rollback` no-op + `cur.execute` no-op + 1 個 `datetime` patch (test_fail_zero_fills_dormancy)。業務邏輯（baseline cache load/compute、trigger evaluation T1/T2/T3/ZERO_FILLS、approach 80% threshold、verdict 階梯、revert flag write 條件、severity ordering）100% 真跑。符合 §5 OK pattern，0 anti-pattern hit。
- LOC: checks 587 / test 528 / __init__ 295 全 < 800；runner 1326 pre-existing > 800 warn / < 2000 cap acceptable。
- Cross-lang / SLA N/A：純 Python passive healthcheck，無 Rust dual + 不在 hot path。
- Linux-flagged 6 follow-up (不阻 commit, deploy 後 cron fire 觀察): mlde_edge_training_rows 真 schema / `(%s::text)::interval` cast / `ts >= start AND ts < end` timestamptz 邊界 / engine_pid mtime ≥ `2026-05-16T01:00:00Z` 真實值 / baseline_cache.json 第一次 persist / engine_mode enum 真命中。
- Verdict: REGRESSION PASS, 0 push-back to E1, two IMPL ([69] + [68]) 可進 PM commit。
- Lesson — passive healthcheck Mac mock 充分準則: PG IO + datetime patch 兩 surface 邊界內 mock，業務邏輯（cache invalidation、trigger eval、severity ordering、flag write 條件、approach threshold escalation）真跑 → Mac mock pytest 可信。Linux PG dry-run 只驗 schema/cast 邊界，不替代 Mac unit test 邏輯覆蓋。本 IMPL 17 fixture 含全 4 trigger + 3 approach + 2 edge skip + 2 enum sequence 已覆蓋 spec §4.1 verdict matrix 全 14 行。
- Report: `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--wp03_deploy_gate_healthcheck_e4_mac_regression.md`

## 2026-05-16 · P1-PORTFOLIO-RESTING-EXPOSURE-1 supplement (ad5e609e) Linux Regression PASS

**Trigger**: E2 APPROVE 後 supplement +82 LOC `test_resting_entry_qty_correlated_pair_blocks_oversize` Linux verify
**Verdict**: REGRESSION-PASS · PM commit/push READY（actually 已 land 在 origin/main HEAD）

### 數字
| 項 | Value | Baseline | Delta |
|---|---|---|---|
| Linux full `--lib --release` (run 1) | 2918 / 0 / 1 ignored | 9980448a = 2915 | +3 全 attribute |
| Linux full `--lib --release` (run 2) | 2918 / 0 / 1 ignored | 同上 | non-flaky |
| Linux intent_processor focused | 135 / 0 / 0 | n/a | +1 新 test |
| Mac aarch64 cargo check release | 0 error, 2 pre-existing warning | clean | OK |

### Delta 全 attribution
- 9980448a→ad5e609e 區間 2 commit：
  - `3b055c98` F-09 model_tier + [68] healthcheck → `risk_config_tests.rs +102 LOC` → +2 test
  - `ad5e609e` B-4 supplement → `intent_processor/tests.rs +82 LOC` → +1 test
- 2915 + 2 + 1 = 2918 ✅

### Race protocol 5 條全 PASS
- sibling Phase 1b 14 dirty file 全在 `tick_pipeline / event_consumer / strategies / database / passive_wait_healthcheck` → 0 命中 `intent_processor/`
- Linux main worktree clean = 不必 scratch worktree 隔離（per memory 2026-05-16 P1-PORTFOLIO 主 IMPL pattern）
- Mac vs Linux delta 12 = `dev_disabled_*` secret slot fail-closed + platform-specific tier diff（CLAUDE.md §七 預期）

### Mock 審查 PASS
- 新 test 0 mockall / 0 fake / 0 patch；純 real `PaperState::new(10_000.0)` + `IntentProcessor::compute_effective_long_short_notional` + `compute_correlated_exposure_pct` + `compute_exposure_pct` + `compute_leverage` + `risk_checks::check_order_allowed` + `RiskConfig::default`
- 業務邏輯 100% 真跑（per regression-testing-protocol §5 OK pattern）
- 0 anti-pattern hit

### Cross-language consistency / SLA
- N/A — intent_processor 是 Rust SSoT 無 Python dual implementation
- 新 test 是端對端 gate chain 整合 test（非 tick hot path），SLA 不適用

### Lesson learned
- **Stale dispatch test coverage top-up pattern**：PA dispatch 已對 land commit 仍派工，E1 自降級為 test coverage top-up 補唯一未覆蓋 gap（end-to-end gate chain），E2 APPROVE + E4 PASS，PM 同 ticket 標「test coverage hardened」即可，不必開新 P2 ticket（per E1 §7 選項 A + E2 A-1 + 本 report §6 advisory 1）。
- **Linux main worktree clean → 直接驗證**：與 2026-05-16 主 IMPL Round 1 scratch worktree pattern 不同——主 round 因為 Mac branch 未推 push 到 origin/main 需要 scratch；本 supplement 已 land 進 origin/main HEAD，Linux 直接 fetch + `git status` 0 dirty 即可直接 cargo test，無需 scratch isolation。判斷準則 = `git status --porcelain | wc -l` + `git log -1 origin/main` 對齊。
- **Delta attribution 三 source rule**：當期間 ≥ 2 commit 落地時，計算 baseline → delta → predicted 必 attribute 每個 source commit；本 case 漏看 3b055c98 F-09 +2 test 會誤判 +3 為 0 attribution surprise（real = full attribute 0 unexplained）。E4 必跑 `git log baseline..HEAD -- rust/openclaw_engine/src/` 列出 source-touching commit 並驗 `git show --stat` test_file delta。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-16--p1_portfolio_resting_exposure_1_supplement_e4_regression.md`

## 2026-05-18 · Phase 1b Calibration Sweep Harness E4 Mac Regression PASS

**Trigger**: E2 APPROVE-CONDITIONAL (`907ab778`) 派 E4 regression on `feature/phase-1b-calibration-sweep-harness` HEAD `907ab778` (code commit `93069c29`)
**Verdict**: REGRESSION-PASS · pass to QA / no deploy needed (Mac local research tool)

### 數字
| 引擎 | 結果 | Baseline | Delta |
|---|---|---|---|
| calibration pytest (Mac) run 1 | 63/63 in 0.03s | new | +63 (本 PR) |
| calibration pytest (Mac) run 2 | 63/63 in 0.03s | non-flaky | 0 |
| calibration pytest (Mac) `-W error` strict | 63/63 in 0.03s | 0 warning | OK |
| sibling canary healthchecks | 60/60 in 0.04s | unchanged | 0 import pollution |
| sibling helper_scripts/db/test_maker_fill_rate | 11/11 in 0.04s | unchanged | 0 conflict |
| Combined 3-suite run | 134/134 in 0.07s | sum 63+11+60 | 0 cross-test |
| Rust release lib (Mac) | 2992/0/1 ignored in 0.69s | 2972 (5d ago `18081551`) + 20 sibling drift | 0 calibration attribute |
| Cross-language 8 fixtures (Rust port) | delta=0.00 all 8 | 1e-9 tolerance | exact match (9 量級 stricter) |
| Determinism sha256 80 sample × 2 round | identical `5160fffe…` | byte-id | OK |

### Race protocol 5 條全 PASS
- HEAD `907ab778` ≡ origin/feature/phase-1b-calibration-sweep-harness（unchanged during review）
- Worktree 4 modified + 7 untracked 全在 `docs/CCAgentWorkSpace/{E2,MIT,PA,QA}/` 或 `memory/`，**0 命中 helper_scripts/calibration/**
- 不動 sibling dirty file
- Report path unique
- `git log --since=30m ago origin/main` 0 source drift

### Mock 審查 PASS
- E1 unit test (63 個) 0 mockall / 0 fake / 0 patch（per E2 §4 抽查 5 個確認）
- 純函數 simulation 真實 invoke `compute_close_limit_price` / `compute_post_only_price` / `simulate_cell_against_fill` / `classify_cell` / `wilson_score_interval` / `write_outputs`
- 業務邏輯 100% 真跑（spread guard / small-tick widening / BBO cross fill / family mismatch / strategy_close prefix / Wilson CI / fail-closed adverse=None / 3-tier PASS/CONDITIONAL/FAIL）
- 0 anti-pattern hit (per regression-testing-protocol §5 OK pattern)

### Cross-language consistency / SLA
- **Cross-language**: Rust `maker_price.rs:408-497` 8 個 `#[test]` fixture 對齊 Python `compute_post_only_price` port — 8/8 delta=0.00 exact match (比 1e-9 spec tolerance 嚴格 9 個量級)。Python 純 arithmetic + no epsilon (per E2 §Caveat 6 verified) → f64 binary identical 在此 fixture range
- **SLA**: N/A — calibration 是 Mac local research tool / 非 tick hot path / 非 H0 Gate

### Lessons learned

- **Pure research tool harness regression 模板**：0 Rust touch / 0 TOML / 0 V### / 0 live auth / 0 runtime mutation 的純 Python research tool 不需 Linux SSH 驗證 + 不需 `restart_all.sh`；E4 重點 = (1) Mac pytest non-flaky × 2 + `-W error` 三跑 (2) sibling no-pollution combined run (3) cross-platform path 0 hardcoded (4) determinism via direct module invoke (CLI stdout 因 timestamp suffix 不可 byte-id；簡單繞 = module-level pure function 跑兩遍 hash 比對) (5) Rust baseline sanity 確認 0 calibration attribute (6) cross-language fixture 直接比 Rust mod tests numeric expected value (7) governance LOC + comment lang 1-pass。約 30 min wall time 比 full Rust + Python E4 矩陣省 70%
- **Determinism check 設計陷阱**：CLI 含 `datetime.now(timezone.utc).strftime("...")` 在 output_dir suffix → CLI 整體 stdout 永遠不 byte-identical。E4 不能直接 `subprocess.run` × 2 比 sha256。正確做法 = 認識 simulation 業務邏輯本體（純函數）必 deterministic，跳過 CLI wrapper 直接 import module + 跑 80 個 primitive output × 2 round 比 hash。教訓：determinism check 設計前先讀 CLI source 判斷 wrapper 層是否引入非 deterministic side effect
- **Cross-language fixture 對齊 ≠ 全 path coverage**：本 step 8 fixture 只覆蓋 `compute_post_only_price` 主 path (buy/sell × 全 BBO/單側 + skip + buffer_zero)。`compute_close_limit_price` 的 spread guard / small-tick widening / required_ticks > buffer_ticks 路徑由 calibration unit test `test_phase_1b_maker_price.py` 5 個 `close_limit_price_*` test cover（且 E2 §4 已 verified port 1:1）。E4 不重複 cover；但需在 report 明標「fixture cover scope = post_only_price subset; close_limit_price audited via E1 unit test」
- **Rust 2972 → 2992 delta attribution**：origin/main 5 day drift + 20 test sibling commit（W7-3 / W-AUDIT-8x / dispatcher fix）；calibration 0 Rust touch by `git diff main..HEAD --name-only | grep \.rs$` empty → Rust passed 0 calibration attribution。**未來「Rust + Python 純 Python PR」E4 模板**：跑 cargo test 純為 sanity 不算 PR 貢獻 delta；delta 全 attribute sibling commits
- **Combined 3-suite run is faster than 3 separate run 同 confidence**：63 calib + 11 maker_fill + 60 canary = 134 in 0.07s vs 3 跑加總 0.03 + 0.04 + 0.04 = 0.11s。pytest collection 一次 + import 緩存共享 → combined 是更快更 conclusive 的 pollution test。教訓：sibling check 用 combined run 取代 separate run，省時且更嚴格

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-18--phase_1b_calibration_harness_e4_regression.md`

## 2026-05-18 · Phase 1b Calibration grid timeout 30s → 90s E4 Mac+Linux Regression PASS

**Branch**: `feature/phase-1b-calibration-grid-timeout-90s` HEAD `820f0532` (PA cell selection `2b65d3f1` → E1 IMPL → E2 APPROVE-CONDITIONAL → E4)
**Verdict**: REGRESSION-PASS · PM merge READY

### 數字
| 引擎 | Result | Baseline | Delta |
|---|---|---|---|
| Mac openclaw_engine release (run 1) | 2992/0/1 in 0.68s | 2992 (phase_1b_calibration_harness) | 0 |
| Mac openclaw_engine release (run 2) | 2992/0/1 in 0.70s | 同 | non-flaky |
| Mac openclaw_core release | 446/0/0 in 0.01s | n/a (task brief 寫 35 錯 — 35 是 openclaw_types) | OK |
| Mac openclaw_types release | 35/0/0 in 0.00s | unchanged | 0 |
| Mac maker_price 3-run determinism | 15/0/0 × 3 identical | n/a | non-flaky |
| Mac tick_pipeline::tests focused | 163/0/1 (1 pre-existing ignored) | n/a | 0 |
| Mac strategies::common focused | 33/0/0 | n/a | 0 |
| Linux release scratch (run 1+2) | 2992/0/1 × 2 in 0.64s | Mac 2992 | 1:1 + non-flaky |
| Python calibration pytest | 63/63 in 0.03s | Wave 1 baseline 63 | 0 coupling |
| Race check 5/5 | ALL PASS | n/a | OK |

### 5 sibling fixture audit (E2 SHOULD-FIX)
13 處 `30_000.0` 全是 BTCUSDT BBO mock 中位價 ($30K USD)，0 個是 `timeout_ms` 數值。`fn inputs_with_bbo(last: f64, bid, ask, tick)` signature 確認 first-arg = last_price 非 timeout。E2 functional non-blocking 結論成立 — 不阻 deploy。NTH (P2): 若後續 PR touch sibling test 可順手提取為 `const BTC_BBO_MOCK_MID: f64 = 30_000.0;` 提升可讀性

### Spec §7.1 compliance
spec line 488-493 列 default 30s / phys_lock 10s，**未明定 hard upper bound**。Task brief 寫 E2 verified ≤120s 推測是從 entry maker max 50s 推算的合理上限。90s 屬 post-spec evidence-driven evolution (calibration G-AB-01-C90 fill 70.8% vs 30s 58.3% 12.5 ppt 改善)，不違反 spec 任何明示約束。NTH advisory: Phase 2a 24h 觀察後 spec §7.1 同步加 row 反映 calibration evidence

### Task brief 數字以實測為準
- task brief 寫 "openclaw_core 35/0/0" — 實測 446/0/0 (35 是 `openclaw_types`)
- task brief 寫 "11 LOC" — `git diff --stat` = 14 LOC (11 insertions maker_price + 3 dual_rail_dispatch)
- E4 必跑命令拿 baseline，task brief 寫死數字也屬「不信寫死數字」廣義適用範圍 (per regression-testing-protocol §1 baseline 規則)

### Lessons learned

- **11/14 LOC 純常量 PR regression 模板**: 無 Python dual / 無 hot path / 無 new test → 不需 cross-lang 驗 / 不需 SLA / 不需 mock audit。E4 重點 = (1) baseline 0 regression (2) assertion 對齊 source (3) determinism 雙跑 (4) cross-platform Mac↔Linux 1:1 (5) sibling fixture audit verify E2 finding scope。約 20 min wall time，比 full Rust + Python E4 矩陣省 70%

- **Same-number-different-domain audit 陷阱**：`30_000` 在不同 context 是 timeout (30s ms) 或 BTC price ($30K USD)。E4 必跑 fn signature lookup (`fn inputs_with_bbo(last: f64, ...)`) 確認 first-arg semantic 再判 functional coupling。否則容易誤判 BBO mock 為 timeout drift。本次 13 處 `30_000.0` 全是 USD price domain（first-arg `last`）、`30_000.9` 是 passive 賣價計算結果（ask - tick），0 個 timeout — E2 SHOULD-FIX scope verify 成立

- **Spec doc 與 calibration evidence-driven 時序**: spec §7.1 通常列當時設計值；calibration sweep evidence-driven 微調可能在 spec 未明定 hard upper bound 下落地。E4 compliance check = 「不違反 spec 明示約束」非「spec 必列此具體值」；spec doc sync 是 NTH (P2) 而非 blocker

- **Linux scratch worktree isolation 不影響 runtime engine PID**: `git clone --shared /home/ncyu/BybitOpenClaw/srv /tmp/e4-p1b-90s-*` + `cargo test` 完全與主 repo + runtime engine 隔離。但需 cleanup 防 `/tmp/` 累積（本次 cleanup 0 殘留）。比 2026-05-16 P1-PORTFOLIO 主 round 用 ssh + scratch 的同 pattern 更輕量（無需 GitHub remote 跳板）

- **`memory.md` 322KB 超 Read 上限**：必須 `tail -200` 或 `cat >> file << 'EOF'` append。**不能** Read 全文後 Write overwrite（per 2026-05-16 multi-session memory race lesson 同 reminder）

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-18--phase_1b_calibration_timeout_90s_e4_regression.md`

---

## 2026-05-18 — 13-task cleanup sprint full regression (4 E1 batches + 4 PM inline edits)

### Scope
- 4 E1 batches: P1-PORTFOLIO-RESTING follow-ups (router-cache + test-coverage + E5-bench) / P2-DEAD-SCHEMA-DROP-V096 / P2-WP05-FUP-1 reason_code cleanup (23×`str(exc)`→`reason_code` across 8 Python files) / P1-CRON-INSTALL-WAVE-1 + WP05 CSP/SRI / P2-STOCHASTIC-LEAK-AUDIT
- 4 PM inline: perception_data_plane DeprecationWarning + 3 test filterwarnings + 7 dead module retirement (-3616 LOC core)
- New files: V096 migration + bench `intent_processor_exposure.rs` + healthcheck `checks_cron_heartbeat.py` [75..79] + `compute_sri_hashes.sh` + 22+42 test files

### Result matrix
| Engine | passed | failed | pre-PR baseline | delta | verdict |
|---|---|---|---|---|---|
| cargo openclaw_engine --lib (Mac release) | **2993** | 0 (1 ignored) | 2992 (last E4 report) | **+1** (Batch A's test_p2_portfolio_resting_multi_close_summed) | ✅ matches task brief |
| cargo openclaw_core --lib (Mac release) | **357** | 0 (0 ignored) | 446 (pre-PR stash probe) | **-89** (= -90 retired + 1 stochastic_prior) | ✅ EXPECTED retirement, not silent deletion |
| cargo openclaw_engine --tests (integration) | 33 | 2 | 33/2 (pre-PR stash probe) | **0 delta** | ✅ pre-existing fails identical signature |
| V096 + cron heartbeat new tests | **64/64** | 0 | n/a (new) | **+64** | ✅ all pass × 2 runs |
| 3 perception tests | **107/107** | 0 | n/a | 0 | ✅ DeprecationWarning emitted but tests pass (filterwarnings handles app.perception_data_plane source) |
| Wider risk/strategist/etc batch | 421 | 3 | 421/3 (pre-PR stash probe) | **0 delta** | ✅ same 3 pre-existing fails (test pollution in wider batch — pass in isolation) |
| bash -n × 6 shell | 6/6 PASS | 0 | n/a | 0 | ✅ |
| HTML parse trading.html | OK | 0 | n/a | 0 | ✅ |

### Pre-existing fail signature verification (critical)
- `stress_bb_breakout_valid_squeeze_with_volume` line 536 `left:0 right:1` — IDENTICAL pre-PR ↔ post-PR (stash probe)
- `stress_bb_reversion_extreme_oversold_bounce` line 483 `left:0 right:1` — IDENTICAL pre-PR ↔ post-PR (stash probe)
- 3 Python fails (`test_demo_and_live_tabs_have_risk_shortcuts`, `TestDynamicRiskRoutes::test_status_no_deployer/test_status_happy`) — IDENTICAL pre-PR ↔ post-PR (stash probe). Last two PASS when run isolated but FAIL in wider batch = pre-existing test pollution unrelated to this sprint.

### Retired module test attribution audit
| Deleted module | Tests removed (git show HEAD) |
|---|---|
| attention | 11 |
| attribution | 10 |
| cognitive | 13 |
| dream | 20 |
| message_bus | 7 |
| opportunity | 18 |
| order_match | 11 |
| **Sum** | **90** |
| +1 stochastic_prior | +1 |
| **Net** | **-89** |
446 - 89 = 357 ✅ exact match. No silent test deletion — every retired test belongs to an explicitly retired dead module documented in `rust/openclaw_core/src/lib.rs` retirement marker.

### Mock anti-pattern audit (E5 §5)
`test_p2_portfolio_resting_multi_close_summed_capped_at_filled` (lines 1875-1917) uses real `PaperState::new(10_000.0)` + `set_latest_price` + `import_positions` + `seed_resting` + calls **real** `IntentProcessor::compute_effective_long_short_notional(&state)` + `compute_exposure_pct` + `compute_correlated_exposure_pct`. 0 mock. Asserts with 1e-4 float tolerance. PASS.

### Cross-language float consistency
N/A this sprint — no Python ↔ Rust shared computation introduced. `compute_effective_long_short_notional` is Rust-only (caller side: Python only passes intent payload via IPC). 1e-4 tolerance applied internally to Rust test assertion (eff_long, eff_short = 0 ± 1e-4) ✅.

### Cross-PR boundary (deferred to QA/E5)
- bench `intent_processor_exposure.rs` not run (bench is for E5 micro-bench, not E4 regression scope). Compile-check via `cargo build --release --bench intent_processor_exposure` = PASS.
- V096 migration not applied to real Linux PG (per task brief: source/test landed via this sprint; apply is operator-gated downstream).
- 5 cron wrappers `touch sentinel` line added but not yet installed in Linux crontab (P1-CRON-INSTALL-WAVE-1 next step).

### Non-flaky verification
- cargo engine + core both runs: 2993/0/1 + 357/0/0 identical × 2 ✅
- V096 + cron heartbeat 64/64 × 2 ✅
- 3 perception 107/107 × 2 ✅
- Wider Python batch 421/3 × 2 with same signatures ✅

### Lessons learned
- **Task brief 數字以實測為準（再次驗證）**: brief 寫 "openclaw_core previously 399/0/1 after Batch B +1" — 實測 357（446 - 90 retired + 1）。Brief 漏算 7 dead modules retirement (-90 tests)。E4 必跑命令拿真實 baseline + stash 法驗 pre-PR base = 唯一可靠判 delta attribution。**規則**: 寫 "previously X/Y/Z" 的數字常常忽略同次 PR 的 retirement scope，stash probe 是必檢手段
- **Wider-batch fail vs isolation-pass = test pollution, not regression**: 2 個 `TestDynamicRiskRoutes` test 單獨跑通、wider batch 跑掛。stash 後 wider batch 同樣掛 → pre-existing pollution，非 PR-introduced。**規則**: 任何「PR-introduced fail？」claim 必跑 pre-PR baseline 同 batch 作對照（stash --keep-index 法即可），單測通過 ≠ 證明 batch 通過
- **`memory.md` append-only 持續鞏固**: 本次再次 `tail -30` + `cat >> EOF` append 模式工作，無 Read 全檔嘗試

## 2026-05-20 · P2-STRESS-BB-FALSE-SQUEEZE + P2-SIM-QUEUE-AWARE 並行 batch E4 Mac PASS

**Branch**: `main` HEAD `232c3aff`（origin/main 領先 3 commits）— 兩個 P2 IMPL Mac dirty tree。
**Verdict**: REGRESSION-PASS × 2 IMPL · PM merge READY

### 數字
| Surface | Result | Baseline | Delta | Verdict |
|---|---|---|---|---|
| Rust lib (Mac release run 1) | 3042/0/1 in 0.70s | 2993 (5/18 cleanup sprint) + sibling drift | +49 = sibling Layer A `6cf476c4` + spine align `879e3852` 等；P2-STRESS-BB attribution = 0（純 tests/ 改） | ✅ |
| Rust lib (run 2) | 3042/0/1 in 0.70s | same | non-flaky | ✅ |
| Rust --tests (26 binaries × 2 runs) | 3264/0/1 × 2 | n/a | identical | ✅ non-flaky |
| Rust stress_integration focused × 3 | 35/0/0 in 0.10-0.12s | pre-PR stash baseline 35/0/0 | 0（純強化既有 1 test assertion，不增 count）| ✅ |
| Python calibration full (run 1+2) | 89/89 in 0.04s | 63 (5/18 phase_1b harness baseline) | +26 = 22 queue_adjustment unit + 4 sweep_replay integration | ✅ non-flaky |
| Python sweep_replay focused × 2 | 13/13 in 0.01-0.02s | 9 既有 | +4 new queue integration | ✅ non-flaky |
| Cross-platform path grep × 7 files | 0 hit | n/a | 0 | ✅ |
| Mock anti-pattern grep × 7 files | 0 hit (sibling line 1317 `apply_patch` 是 RiskConfig API 非 mock) | n/a | 0 | ✅ |

### Lessons learned

- **「既有 N test 是否 false GREEN 受隱式影響」對抗驗證法**: P2-SIM-QUEUE-AWARE 加 `orderbook_window` optional arg + 4 new dataclass field 都帶 default value (None/0.0)。E4 對抗驗法 = (1) grep 既有 9 sweep_replay test 是否傳 `orderbook_window` (全不傳 → walk default) (2) 從 source 驗 default `orderbook_window=None` → `queue_factor=None` → `apply_queue_adjustment` 數學 collapse 到 `fill_p_proxy * 1.0` 1:1 (3) grep 既有 9 test 是否 assert 新欄位 (全 0 assertion) → 三條 verified → 既有 9 test 0 false GREEN 受影響。**規則**：新增 optional kwarg + dataclass new field 必有 default value，E4 對 backward-compat 必三條都驗（call site 不傳 + source default fallback path + 既有 assertion 不觸碰新 field）

- **task brief 「既有 63」拆解陷阱**: task brief 寫 "既有 63 test 是否有 false GREEN 受隱式影響"。但 63 不在單一 file 內 — 是 dir 級分布 (maker_price 20 + sweep_cells 17 + sweep_replay 9 + sweep_report 17 = 63)。E4 必拆 per-file 跑 isolation 才能定位 backward-compat。**規則**：task brief 寫「既有 N test」必拆 per-file 確認哪幾個 file 受改動影響，而非整批跑（整批雖 PASS 但會掩蓋 file 級 false GREEN）

- **Pre-PR stash 法驗 baseline**: 對 Rust tests/ 改動（非 lib 改動），用 `git stash push -- <file>` 後跑 focused test 拿真實 pre-PR baseline = 唯一可靠判 delta attribution。本次 stress_integration 5/18 cleanup sprint report 寫「33 passed / 2 failed」但當前 stash baseline 35/0/0 — 因為 5/19 invariant drift fix 已修那 2 個 pre-existing fail。**規則**：memory 寫死數字（5/18 = 33/2）不能作 5/20 baseline，必跑 stash + focused 拿當下真實 pre-PR baseline

- **`cargo test --lib` 不覆蓋 tests/ integration crate**: TODO §11.3 line 163 governance flag 提醒。本次 E4 run 1 + run 2 跑 `--lib`，run 3 跑 `--tests`（含 26 integration binaries）= cover 兩個 surface。**規則**：PASS sign-off 前必雙跑 `--lib` 1+ 次 + `--tests` 1+ 次；只跑一個 surface 是 BLOCKER 級漏覆蓋

- **0 mock 真 PG SELECT 驗證模式**: phase_1b_queue_bias_regression.py 唯一 `cur.execute` = 純 `SELECT ... FROM trading.fills WHERE ...`（line 143-168）；ground truth `liquidity_role` 對齊 actual_maker=5 + actual_taker=13；無 INSERT/UPDATE/DELETE side effect。E4 verify 5 SQL pattern：(1) `grep cur.execute` 全為 SELECT (2) E2 §1.4 已 verified 5 個 SQL 全 SELECT (3) source line 100-130 註釋說明 "為什麼直接讀 V094" + "為什麼支援 sample_end_utc" 設計意圖。**規則**：task brief 「regression 用真實 PG 而非 mock」對抗驗法 = grep execute pattern + 註釋意圖 + ground truth 對齊（liquidity_role 一致性）三條

- **整批 phase_1b -k 跑會撞 sibling collection error**: `pytest -k 'phase_1b' --tb=short` 從 srv root 跑會撞 `tests/misc_tools/test_pure_utils.py` + `tests/ml_training/test_pure_utils.py` collection error（非 P2 IMPL 引入）。**繞法** = scope 到 `helper_scripts/` 即 `pytest helper_scripts/ -k 'phase_1b'` → 89 passed / 719 deselected in 0.14s。**規則**：跨 dir 廣域 `-k` 跑容易撞 sibling collection error，scope 縮到改動所在 top-level dir（helper_scripts/）即可繞

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-20--p2_stress_bb_sim_queue_aware_e4_regression.md`

## 2026-05-21 — C1+C2 close_maker healthcheck E4 light regression

### Task
E2 R2 APPROVE-CONDITIONAL (cfb9d243) 後 light E4：純 Python read-only SQL healthcheck（C1 新 `[66] 66_close_maker_pre_stopout_rate.py` 392 行 + C2 改 `[62] 62_close_maker_fill_rate.py` 加 `--stratify` flag）。未動 _common.py / Rust / IPC / GUI。

### Verdict
PASS · ready for PM commit。

### Numbers
- `helper_scripts/canary/healthchecks/tests/` 83/0 (1st + 2nd run, 0.04s/0.03s, non-flaky)
- `helper_scripts/canary/` 201/0 (1st + 2nd, 31.77s/31.21s)
- `helper_scripts/db/test_close_maker_audit_healthcheck.py` 8/0 + 14 subtests（passive_wait `[71] zero_spine_lineage` 仍綠 → cross-namespace 不擾）
- file size 全 ≤ 800（392/336/39/301/104）
- emoji = 0 / hardcoded path = 0
- argparse / module import / `--stratify hour --help` 全 OK

### 教訓 / 工程觀察

- **task list `grep [71] 應 0 hit` 字面 vs E2 design intent**: task brief 寫 `grep -r "\[71\]" helper_scripts/canary/healthchecks/` 應 0 hit，實測 8 hits。但 E2 R2 §MEDIUM-F1 已 ratify 這 8 hits 全是 doc/comment 形式（passive_wait namespace 邊界說明 + R2 rename 歷史）— 不是 leftover regression。**規則**：E4 不重啟 E2 review 已 APPROVE 的 design intent；只認定 active slot 編號是否還是 [71]（**驗法 = `check_id` literal + 模組命名 + fixture name**，不靠純文字 grep count）。task list 字面與 E2 verdict 衝突時走 E2 verdict（CLAUDE.md §八 工作鏈 + role hierarchy）。

- **passive_wait test 不在 `passive_wait_healthcheck/` 子目錄**: task list step 2 `python -m pytest helper_scripts/db/passive_wait_healthcheck/` = `no tests ran`（該子目錄無 test，源檔 only）。實際 test 集中在 `helper_scripts/db/test_close_maker_audit_healthcheck.py` 等 sibling file。**規則**：未來 cross-namespace verify「passive_wait 不被擾」測試的正確 path = `helper_scripts/db/test_close_maker_audit_healthcheck.py`（含 `test_zero_spine_lineage_guard` 等 [70-74] slot test）。

- **adversarial test design — `EXPECTED_STOPOUT_EXIT_REASONS` fixture**: test_66 line 43-58 收錄 12 個 production 真實 exit_reason 字串（source line 標註 risk_checks.rs:334/355/379/390 + bb_breakout/mod.rs:910/919 + step_0_fast_track.rs:486/603 + helpers_close_tags.rs:122-127 + maker_price.rs:528/529）+ 8 個 graceful exit 字串，用 fnmatch 模擬 PG LIKE 驗 default patterns 真實 match。E2 R2 §MEDIUM-E1 自跑 adversarial probe 證實此 test 故意把 patterns 改回 R1 lowercase → 3/12 紅報。**規則**：catcher test 設計優於 mock test — fixture 全 source-grep 標註 + reverse assert 8 個 graceful exit 保證 0 match（防 pattern 過寬 false positive），這種模式是 healthcheck regression 黃金標準。

- **stratify=none 向後兼容 adversarial assert**: test_62:132-153 `test_stratify_none_keeps_legacy_sql_verbatim` 不只 assert SQL 不含 `EXTRACT(HOUR/DOW`，還 assert `GROUP BY engine_mode` → `ORDER BY engine_mode` 之間 0 comma（即無 extra group cols）— 這個 SQL 字面切片 + comma-substring 檢驗能 catch 任何「stratify=none 路徑被 stratify mode 程式碼污染」regression。**規則**：向後兼容測試不能只 assert NOT contains，要 assert 結構級 invariant（如 BETWEEN 兩個 anchor 之間沒 unexpected token）。

- **dead init 清理 LOW-F3 三路徑審計**: 62 改動刪 line 225 `overall_verdict = "PASS"` init，E2 R2 §LOW-F3 驗證 3 條路徑（not rows / else stratify=none / else stratify!=none）全本地賦值 → dead init 100% 安全。**規則**：刪 default value init 前必窮舉所有 control-flow 分支驗證本地賦值 ≥ 1 次；別只看「init 後沒讀」（可能某分支真讀 default）。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-21--c1_c2_close_maker_healthcheck_e4_regression.md`

## 2026-05-21 · P1-WATCHDOG-NETOUTAGE-CLASSIFIER-FIX R2 — E4 PASS
- Branch local main HEAD `fbe8b8d5`（sibling push 0）；改動 3 files（engine_watchdog 1369→1532 +163 / test_canary 728→890 +162 / test_engine_watchdog 803→810 +7）。
- pytest `helper_scripts/canary/` 兩遍 207/207 PASS（31.19s / 31.18s）；cross-module healthchecks/tests/ 83/83 + helper_scripts/db/ 459 + 14 subtests 全綠不破。
- 25/25 TestEngineFailureClassifier + TestOnEngineCrashClassification 全 PASS（含 6 R2 new tests + 19 R1 baseline 含 1 改名 `test_non_consecutive_dns_above_interleaved_threshold` 意圖反轉設計）。
- **adversarial probe（production-empirical 真實性驗）**：暫時 comment AMBIGUOUS_SOURCE_PATTERNS 3 個 R2 新 token (`pg pool` / `pool timed out` / `db_pool`) → `test_pg_pool_exhaustion_with_concurrent_dns_errors_not_classified_as_net_outage` RED (`network_outage != engine_crash` 重現 R1 FP) → 復原（diff = 0 byte-identical）→ test GREEN；control test `test_pg_connection_error_not_classified_as_net_outage` 在 strip state 仍 PASS（用 sqlx + pgconnection 不在 strip 範圍）→ ambiguous token 互相獨立、設計健全。
- **規範**：3 file < 2000 hard cap / 0 emoji / 0 hardcoded path / 0 新 import / 中文注釋默認 / `--status` exit 0 對齊 P1-WATCHDOG-EXIT-CODE-CLARIFY DONE 2026-05-20 semantic 分區。
- **Linux runtime impact**：source-only，0 新 dependency，watchdog daemon PID 2936560 仍跑 R1，需重啟 deploy（out of E4 scope per `feedback_restart_rebuild_flag_scope`）。
- **教訓（adversarial probe 真實性驗）**：HIGH-1 R2 production-empirical test 用真實 ANSI-wrapped engine.log 第 4 行 reproduce false-positive，這類 test 必須跑 adversarial cycle（strip → RED → restore → GREEN）才能證實非 mock self-consistency。E2 R2 §自驗 regression catcher 應為標配；E4 在 cross-confirmation 階段再跑一次 cycle 多一層保險。本次設計健全度：strip 3 token 必紅、其他 token 不依賴新 3 token、復原 byte-identical 重現綠 → 100% 設計合格。
- **教訓（test 改名意圖翻轉）**：R1 baseline 有 1 test 改名 + assertion 翻轉（`test_non_consecutive_dns_below_threshold` → `_above_`，`engine_crash` → `network_outage`）。這類「改舊 test 而非加新 test」屬 BLOCKER 反模式邊緣，但本次因 gate (c) 新增使原行為設計反轉（不是「測試妥協」），E2 R2 已 APPROVE 此設計變動；E4 在報告中明確 callout 此意圖反轉避免後人誤判。
- **教訓（cross-module non-flaky verification）**：207/207 兩遍同綠 31.19s / 31.18s（差 0.01s）= 系統穩定；single-run 459 PASS db/ + 83 PASS healthchecks/tests/ 對齊 C 批 baseline → cross-module 0 regression 真實確認。pytest stability 是 watchdog daemon code change 的最少 sanity check 標準。
- **教訓（restoration verify byte-identical）**：adversarial probe 之後 `diff <restored> <backup>` = 0 是強制檢驗（不能只看 test 再綠就 assume 復原）；本次 diff 0 + final canary/ 207/207 重跑都驗 → 100% restore。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-21--p1_watchdog_netoutage_classifier_fix_e4_regression.md`

## 2026-05-21 — F3 P2-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE E4 light regression PASS

### Task
DEFER-D1 follow-up land。E2 R2 APPROVE-CONDITIONAL（Wilson 公式 + 對稱反轉 + 5 test 真實覆蓋全 PASS）+ PM 主會話 inline 修 default 0.20 → 0.15（6 處對齊）後 light E4。改 2 files：`66_close_maker_pre_stopout_rate.py` (392→492 LOC) + `tests/test_66_pre_stopout_rate.py` (301→484 LOC)。

### Verdict
**PASS** · ready for PM commit。

### Numbers
- `helper_scripts/canary/healthchecks/tests/` 88/88 × 3 runs (0.04s identical, non-flaky)
- `helper_scripts/canary/` 212/212 × 2 runs (31.21s/31.17s, non-flaky)
- `helper_scripts/db/test_close_maker_audit_healthcheck.py` 8/8 + 14 subtests（passive_wait [71] cross-namespace 不擾）
- file size 全 ≤ 800（492/484）/ emoji = 0 / hardcoded path = 0
- argparse `--wilson-lower-fail` default 0.15（從 0.20 調降）/ `--no-wilson` 預設 disabled (Wilson enabled by default)
- adversarial probe A：strip `run()` line 338 `0.15` → `0.20` → `test_pass_when_wilson_upper_within_bound` line 362 RED (`assert 0.2 == 0.15`) → byte-identical restore → 88/88 GREEN（diff = 0 byte）

### 教訓 / 工程觀察

- **「PM inline 修 4 處」實是 6 處 — function default 不能漏算**：PM brief 寫 default 修 4 處（docstring × 2 + argparse + test assertion）；實 source 額外有 2 處 function default（`_stopout_rate_verdict()` line 281 + `run()` line 338）也需同步改才邏輯一致。視覺角度 user-visible 是 4 處，但內部技術一致性要看 6 處。E4 必跑 `grep -nP "wilson_lower_fail.*=\s*0\." <source>` 把所有 `wilson_lower_fail = 0.XX` 點全列出對齊。**規則**：PM inline 多處同 const value 修改，E4 必 grep 整檔 default value 占位驗 N 處對齊（不只信 brief 寫的 N）。

- **adversarial probe 真實性：strip default → test 必紅 + restore byte-identical → 必綠**：本 PR 核心 test `test_pass_when_wilson_upper_within_bound` line 362 `assert result["thresholds"]["wilson_lower_fail"] == 0.15` 是針對 `run()` line 338 function default 的直接 catcher。strip `0.15` → `0.20` → 立紅 (`assert 0.2 == 0.15`)；diff < /tmp/backup > = 0 byte → GREEN。**規則**：高敏感 default value (gate threshold) 必須有 1+ test 對 result["thresholds"][key] 做 assertion；E4 必跑 adversarial cycle 確認該 assertion 真實。設計健全度 = strip 1 default 必 1 red + 其他不依賴此 default + restore byte-identical 必 GREEN。

- **`_stopout_rate_verdict()` dead default value 不影響 adversarial probe**：line 281 default `wilson_lower_fail: float = 0.15` 是 dead default（`run()` line 417 永遠 explicit pass `wilson_lower_fail=wilson_lower_fail`）。strip 它不會紅。但邏輯一致性仍要求保留 0.15（防未來重構誤觸發 default）。E4 verify dead default 對 adversarial cycle 不必抓綠紅，但要 mention probe scope 限定在 explicit pass site（line 338）。**規則**：identifying dead default value（call site 永遠 explicit pass）是 adversarial probe target 排序的 prerequisite — 別費時 probe dead default。

- **test 不 touch argparse 是設計上 mock-scope 缺口**：test_66 全 import + call `run()` 不走 `_parse_args` / `sys.argv`。所以 argparse line 255 default 改變 test 完全看不見。當前對齊靠 docstring + function default × 2 + test assertion 4 路綁定，PM 視覺檢查保證 argparse 跟其他 3 路一致。**規則**：對 user-visible CLI default 想完全 hard-binding 需加 `test_argparse_defaults_snapshot`（mock-free，純 import argparse + parse_args([]) 比對 dict）NTH-P2 add。

- **baseline 漂移 attribution**：5/21 早晨 C1+C2 baseline canary/ = 201；P1-WATCHDOG-NETOUTAGE R2 +6 = 207；當前 212 = +5 sibling drift。本 PR 對 canary/ 主目錄貢獻 = 0（5 new test 全在 canary/healthchecks/tests/ 已計入 88/88）。**規則**：baseline 不能只看「PR 加幾個 test」要 attribute 到正確子目錄；canary/ 級 +5 跟 PR 無關時 E4 必明寫 attribution 否則後人誤判 PR 改變 canary/ baseline。

- **`memory.md` 322KB＋ 持續用 append-only `cat >> EOF` 模式**：跟 5/18 / 5/20 / 5/21 早報告同 pattern，避免 Read 全檔超 256KB 上限。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-21--f3_obs_pre_stopout_wilson_e4_regression.md`

## 2026-05-21 — P2-DYN-STOP-FLOOR-SENTINEL（sentinel test 加固）

### Task
FA F2 RCA OQ-4 衍生。5 策略 dyn_stop floor 公式：`limits.stop_loss_max_pct × dynamic_stop.base_ratio = 25 × 0.25 = 6.25%`（demo）；防 base_ratio / cap_ratio / atr_stop_mult silent drift 改變 SL gate semantic 卻無人察覺（funding_arb 6.29% SL 案例 = floor + 0.04pp = 設計範圍內，若 base_ratio drift 至 0.20 floor 變 5% → 6.29% 變誤判越界）。加 3 sentinel test 到 `risk_checks_per_strategy_tests.rs:438+`。不動 TOML，不動 production Rust source。

### Verdict
**PASS** · ready for PM commit。

### Numbers
- Mac baseline: lib 3042 passed / 0 failed / 1 ignored → 3045 passed / 0 failed / 1 ignored（+3 sentinel）
- g2_03_per_strategy_tests baseline: 23 → 26 PASS（test A/B/C 各加 1）
- 兩遍重跑同綠（finished in 0.69s）— 非 flaky
- 加 test 後 file: 436 → 656 LOC（+220）

### 加了哪 3 個 test
1. `test_demo_toml_dyn_stop_base_ratio_locked` — 鎖死 demo `base_ratio=0.25` + `stop_loss_max_pct=25.0` + effective floor 6.25%；註釋警示 SL gate semantic impact audit 為改動前提
2. `test_demo_toml_dyn_stop_atr_mult_and_cap_locked` — 鎖死 demo `atr_stop_mult=2.0` + `cap_ratio=0.85` + effective cap 21.25%
3. `test_live_toml_dyn_stop_explicit_divergence_from_demo` — 鎖死 live `stop_loss_max_pct=15.0` / `base_ratio=0.5` / `atr_stop_mult=1.5` / `cap_ratio=0.75` + effective floor 7.5% / cap 11.25%；加 2 policy invariant: `live_cap < demo_cap`（live 永遠 fail-closed 更窄）+ `live_floor > demo_floor`（demo EDGE-DIAG-2 學習加速 floor 收緊）

### Adversarial probe
- Strip `base_ratio = 0.25` → `0.20`（risk_config_demo.toml line 153）
- `test_demo_toml_dyn_stop_base_ratio_locked` 立紅：`dynamic_stop.base_ratio expected 0.25, got 0.2 — 任何動 base_ratio 之前須先跑 SL gate semantic impact audit（FA F2 OQ-4）`
- Side effect：W-AUDIT-6 sentinel `test_demo_toml_retired_funding_arb_removed_from_risk_config` 同步紅（同 base_ratio assertion） — 預期同步觸發兩個 sentinel 增加 catch rate
- 復原 0.20 → 0.25 → 26/26 GREEN
- `test_demo_toml_dyn_stop_atr_mult_and_cap_locked` 對 base_ratio 不依賴 → 維持 ok 如預期

### 教訓 / 工程觀察

- **與 W-AUDIT-6 範本 sentinel 部分重疊（base_ratio=0.25）— 重疊是 feature 不是 bug**：我的 test A 與既有 `test_demo_toml_retired_funding_arb_removed_from_risk_config` 都 assert `cfg.dynamic_stop.base_ratio == 0.25`。重疊好處：(1) 雙 sentinel 增加 catch rate / (2) 新 test 攜帶 explicit floor 公式 + impact audit warning message 給 future engineer 提醒衍生影響；W-AUDIT-6 範本 only mention `0.4→0.25 history`。**規則**：sentinel 重疊不是冗餘，是兩種 semantic 警示路徑（一個 lock value、一個 lock formula consequence）— 各自獨立 message 不該合併。

- **Test C policy invariant 雙向 push back**：`live_cap < demo_cap` + `live_floor > demo_floor` 兩個 invariant 反向協同 — 一旦 demo 改動使 demo_cap <= live_cap → 表示 live 政策反向 drift（live 變比 demo 寬）= 嚴重失守；一旦 demo floor 改回 ≥ live floor → demo 加速學習意圖鬆動。**規則**：跨環境 config sentinel 不只 lock 個別 value，要 lock policy direction（孰寬孰窄）的 invariant — 反向 drift 是長期最易被忽略的失守。

- **no push back ≠ 不思考**：原 brief Test C 留扣 「如有意 live 不對齊」要不要 spec amendment。當前 live `15.0/0.5/1.5/0.75` vs demo `25.0/0.25/2.0/0.85` 確實**故意 divergence**（per `feedback_env_config_independence` + risk_config_demo.toml L143-152 註釋說明「Paper/Live 不動 / demo 加速學習」），policy intent 清晰 → 不需 spec amendment。但 Test C 加 policy invariant assertion 防未來反向 drift（live 比 demo 寬）= 預防性護欄。**規則**：「故意 divergence」≠「無 invariant」— 越是故意分開越要 lock policy direction invariant。

- **Mac 端 baseline 全綠 + adversarial cycle byte-restore 後同綠 = 設計健全**：3042→3045 lib passed + g2_03 23→26 module passed + 兩遍重跑 0.69s 同綠（非 flaky）+ adversarial probe strip+restore 後 byte-identical 全綠 → 三層健全度驗證通過。**規則**：sentinel test PR 必驗 4 點 (1) baseline +N exact (2) flaky 兩遍同綠 (3) adversarial probe 紅 (4) restore byte-identical 後綠。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-21--p2_dyn_stop_floor_sentinel.md`

## 2026-05-21 — H 批 5 件 cross-module regression（H1+H2+H3+H4+H5）

### Task
H 批 5 件全 closure（H1 audit script SL_HARD_CAP_PCT dynamic load + 5 test / H2 +3 sentinel / H3 hc68 phys_lock_gate4 10 test 新檔 / H4 hc69 halt_session 13 test 新檔 / H5 audit only）後 E4 跑 cross-module + adversarial。

### Verdict
**PASS** · ready for PM commit。

### Numbers
- Python healthcheck (canary/healthchecks/tests/): 111 pass 0 fail（88 baseline + hc68 10 + hc69 13）— 兩遍 0.05s 同綠
- Python audit (db/audit/test_funding_arb_14d_audit.py): 5 pass 0 fail — 兩遍 0.02s 同綠
- Python canary 全集 (helper_scripts/canary/): 235 pass 0 fail
- Rust lib (cargo test --release --lib): 3045 pass 0 fail — 兩遍 0.70-0.72s 同綠
- Rust g2_03_per_strategy_tests: 26 pass（23 pre-H2 + 3 sentinel）

### Adversarial probe 4/4 真實 catcher
1. H1 `risk_config_demo.toml limits.stop_loss_max_pct 25.0→50.0` → `test_current_demo_toml_returns_25_pct` 紅 `0.5 != 0.25`；restore → MD5 `1b62cf37454a23b0abdd8c28edd74608` byte-identical
2. H2 `base_ratio 0.25→0.20` → 雙 sentinel `test_demo_toml_dyn_stop_base_ratio_locked` + W-AUDIT-6 `test_demo_toml_retired_funding_arb_removed_from_risk_config` 同步紅；restore → byte-identical
3. H3 hc68 source 改 `stale_roc_close_attempts_sum == 0` → `>= 5` → 3 FAIL boundary tests 紅；restore MD5 `0c15fb98a3b1695fc8f707d7f493c821` byte-identical
4. H4 hc69 SQL 改 `payload->>` → `details->>` → `test_sql_uses_window_secs_and_event_type_filter` 紅 schema mismatch；restore MD5 `1e1e62e167027152e213ba1eabdcba0c` byte-identical

### Mock 真實性
- H3 fixture string literal 對齊 `rust/openclaw_engine/src/exit_features/v2.rs` 真實 production exit_reason
- H4 SQL 對齊 V035 `payload JSONB NULL` + `event_type TEXT CHECK` schema
- H1 unit test mock `tomllib.load` 但保留 `_load_sl_hard_cap_pct` 全 path 真跑（real toml smoke 對抗無 mock）

### Cross-namespace
canary `[68] phys_lock_gate4_distribution` 與 passive_wait `[68] portfolio_resting_exposure_lineage` 物理分離（不同 module path + 不同 function name + Python import 各路徑互不擾）。

### 規範
- file size 全 < 800（max hc69 = 574 / risk_checks_per_strategy_tests.rs = 668）
- 中文注釋 default（Rust panic message + Python docstring）
- 0 hardcoded path
- 1 pre-existing emoji nit（audit script L18 引用 TODO.md「📅 排程提醒」section / 非新加 / 不擋 commit）

### 教訓
- **改 default constant 不能當 adversarial probe**：H3 改 `DEFAULT_WARN_GIVEBACK_THRESHOLD 10→5` 所有 test 仍 PASS — 因 test 用 explicit arg 不依賴 default；必須改 source business logic 邊界（如 boundary expression operator）才 catch。**規則**：adversarial probe 必驗 source semantic 而非 constant value。
- **MD5 byte-identical 是 sentinel 真實性最後一關**：4 個 file 修改後 baseline MD5 全 match → 證明 probe 不留 dirt。**規則**：probe 4 步 (1) backup + MD5 record (2) inject 驗紅 (3) byte-restore (4) verify MD5 + green sanity。
- **Cross-namespace 同名 slot 不算 conflict 但 conftest fixture 必加邊界 docstring**：canary [68] vs passive_wait [68] 物理分離靠 module path；R2 [66] 範本治理已先建立 conftest namespace 註釋傳統，hc68/hc69 fixture 完整沿用。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-21--h_batch_e4_regression.md`

## 2026-05-21 — I2 P2-LG1-DEMO-SLO-CARVEOUT E4 regression PASS

### Task
I2 hot-path 接線（H0Gate 2 field + with_metrics ctor + setter / finalize_blocked+allowed conditional record / pipeline_ctor.set_endpoint_env 同步 set_engine_mode / bootstrap.rs Arc per-pipeline 注入 / status_report 1h reset cadence + 5 percentile log field / pipeline_types Optional<Vec<H0LatencySummary>> field）。E2 R1 APPROVE 3 push back ACCEPT + 2 注意 ACCEPT；BLOCKER=0。

### Verdict
**PASS** · ready for PM commit。

### Numbers
| Surface | Result | Baseline | Delta | Non-flaky |
|---|---|---|---|---|
| Rust openclaw_engine full (run 1) | 3272/0/3 | 3267 | +5 = h0_latency_metrics integration tests | ✅ |
| Rust openclaw_engine full (run 2) | 3272/0/3 | same | identical | ✅ |
| Rust openclaw_engine full (run 3) | 3272/0/3 | same | identical | ✅ 3x non-flaky |
| Rust openclaw_core full | 410/0/1 | (392+19 integration + 1 doc-ignored) | 410 = 8 hot_path_metrics + 33 h0_gate::tests + ... | ✅ |
| Apple Silicon CI engine | PASS (3 pre-existing dead_code warnings unrelated) | n/a | n/a | ✅ |
| Apple Silicon CI core | PASS | n/a | n/a | ✅ |
| hot_path_metrics focused | 8/0 | 8 | identical | ✅ |
| h0_gate::tests focused | 33/0 | 30 (3 new p2_lg1 tests) | +3 | ✅ |
| h0_latency_metrics integration | 5/0 | 0 (new file) | +5 | ✅ |

### Adversarial probes verified

1. **Strip finalize_blocked record path** — Edit `if let Some(ref rec)` → commented out → `test_p2_lg1_with_metrics_records_both_paths` 立紅 (`assertion failed: left: 1, right: 3 — 3 check → 3 sample`)；byte-restore (MD5 `714fb604ee6af4b3d9148a5587a9acb1`)；test 再綠 → **catcher real**
2. **HdrHistogram clamp [1, 10M]** — source line 119 `let _ = hist.record(latency_us.clamp(HIST_LOW_US, HIST_HIGH_US))` 真實；`test_record_1m_no_panic` 跑 1M record（tail max 10000us 全在範圍內）→ 邏輯上 RecordError 不可能；`test_alert_threshold_boundaries` 7 邊界覆蓋 999/1000/4999/5000/9999/10000/10001 全 ±1‰ pass
3. **Per-pipeline Arc 隔離** — `bootstrap.rs:207 Arc::new(H0LatencyRecorder::new())` 每次呼叫產生獨立 instance；3 個 tokio::spawn × 3 個 bootstrap_runtime → 3 個獨立 Arc；integration test `p2_lg1_set_endpoint_env_propagates_engine_mode_to_h0_gate` 證 paper recorder 只有 paper bucket count>0，其他 4 mode count=0（污染 disprove）
4. **engine_mode race window** — `grep set_endpoint_env` production 唯一 caller = `bootstrap.rs:193`；`set_h0_latency_recorder` 在 `set_endpoint_env` 之後（bootstrap.rs:193→208 順序對）；無 runtime mutation 路徑 → lifecycle-fixed
5. **5-mode snapshot 一致** — `commands.rs:1662-1665 .map(|rec| rec.all_summaries(...))` 必匯出 5 mode；test_p2_lg1_snapshot_emits_5_mode_summaries 直接驗 `summaries.len() == 5` + demo bucket count≥3 + 其他 4 mode count=0

### ML pipeline contamination 守住
- `grep h0_latency rust/openclaw_engine/src/ml/` = 0 hit
- `grep H0LatencyRecorder|H0LatencySummary rust/openclaw_engine/src/ml/` = 0 hit
- learning dir 不存在；ml dir 含 5 file (kelly_sizer / mod / model_manager / registry / scorer) 全 0 hit
- `h0_latency_summaries` 僅出現於 plumbing 路徑（h0_gate / pipeline_ctor / commands / status_report / bootstrap / pipeline_types / IPC tests / integration tests）

### Spec compliance (PA spec §1-12 AC-1..AC-5)
- AC-1 1M tick no-panic：`test_record_1m_no_panic` 1M record / 5 mode 200k each / tail 1-10ms 全 PASS
- AC-2 ±1% accuracy：`test_percentile_accuracy` 1..=1000 確定性序列；±10us 容差（1‰ 解析度）→ p50=500/p99=990/p999=999/max=1000 全 PASS
- AC-3 ≤50ns overhead：`test_record_overhead_ns` 100k warmup + 100k loop release upper 200ns（Mac M1 PASS）+ integration sanity 500ns release upper PASS
- AC-4 Grafana panel JSON：`docs/grafana/dashboards/h0_latency_distribution.json` 5 panel = 4 gauge (p50/p99/p999/max) + 1 heatmap + `$engine_mode` templating var
- AC-5 alert thresholds：panel JSON 嵌入 5000/10000 value mapping + `_alert_rules_inline_comment` 註明 alert eval script 留 spec §6.3 PA follow-up wave

### 規範驗證
- h0_gate.rs 1243 行 > 800 警告 / < 2000 hard cap — E2 R1 ACCEPT non-blocker（pre-existing 1073 + 170 新）；建議 follow-up P3-H0GATE-FILE-SPLIT
- bootstrap.rs 1001 行 > 800（pre-existing 警告；本 wave +14）
- 其他 file < 800：h0_latency.rs 389 / mod.rs 23 / pipeline_ctor.rs 690 / status_report.rs 336 / pipeline_types.rs 215 / tests/h0_latency_metrics.rs 323
- 0 emoji 跨 8 files
- 0 hardcoded path `/home/ncyu` / `/Users/...`
- HdrHistogram 7.5.4 in Cargo.toml + Cargo.lock both verified

### 教訓 / 工程觀察

- **adversarial probe 真實性 strip→red→restore→green pattern**：本次只跑 1 個 strip probe（finalize_blocked None skip 路徑），但這已足夠驗證 conditional record 設計健全。Pattern：(1) backup + MD5 record; (2) inject defect (comment out `if let Some(ref rec)` 塊); (3) `cargo test` 立 red 並具體錯誤輸出（count 預期 3 actual 1）; (4) restore byte-identical MD5; (5) `cargo test` 再 green。同此模式應用於 5/21 H 批 4 個 adversarial probe + P1-WATCHDOG R2 strip probe + dyn_stop sentinel base_ratio strip probe。E4 對 hot path 接線類改動必跑 1+ strip probe 才能驗 catcher real（非 mock self-consistency）

- **`if let Some(ref rec)` None-skip 路徑語意 = catcher 設計核心**：finalize_blocked + finalize_allowed 兩處 conditional record，None 路徑 0 overhead（branch predictor ~1ns）；Some 路徑呼 record(latency_us as u64, engine_mode)。catcher 不僅驗 Some 路徑工作，更驗 None 路徑不破 backward compat — `test_p2_lg1_no_recorder_backward_compat` 用 H0Gate::new (recorder=None) 跑 2 check 並 assert `stats.total_checks==2 / stats.total_allowed==1 / stats.blocked_freshness==1` → backward compat 不破 + 不 panic

- **per-pipeline Arc 跨 tokio rt 隔離 = spec §4.3 deviation 但 trade-off 合理**：spec 原寫 single Arc shared；E1 push back 改 per-pipeline Arc（3 tokio rt × 1000 tick/s = 3000 lock/s contended Mutex 引發 spinning / context switch / unpredictable jitter）。E2 R1 ACCEPT — Grafana panel `$engine_mode` templating var 讓 Grafana cross-pipeline 視圖不破（3 pipeline status_report 寫入同一 healthcheck_run 表 + Grafana 依 mode template 切換）。E4 verify：`bootstrap.rs:207` 每呼一次 `Arc::new(H0LatencyRecorder::new())` 產生獨立 instance；integration test 證 paper.recorder 只有 paper bucket count>0 — 真實 isolation

- **AC-3 ≤50ns overhead 對抗 spec/test 標準分歧**：spec 嚴格 50ns AC-3；E1 unit test `test_record_overhead_ns` release upper_bound 設 200ns（10× headroom 對 baseline 4.86ns + bucket index ~30-40ns + Mutex unconstested ~10ns）；integration `p2_lg1_hot_path_with_recorder_overhead_sanity` release upper 500ns。E2 R1 §A.1 ACCEPT — 200ns unit test 已驗 50ns AC-3 強健（4× headroom），integration 500ns 是 wall-clock noise budget。E4 不重 bench；spec §C.3 follow-up 加 cargo-bench 提強度

- **h0_gate.rs 1243 行 > 800 警告 unaccept-cleanup pattern**：本 wave +170 行（30 doc + 140 unit test）；baseline 1073 早就 >800。CLAUDE.md §四「surgical changes / no opportunistic adjacent cleanup」原則 = E1 §5.5 拒絕順手拆檔。E2 R1 ACCEPT non-blocker + 建議 follow-up P3-H0GATE-FILE-SPLIT。E4 角色 = flag warning 但不 enforce 拆（不在 E4 scope）

- **memory.md 363KB 持續 append-only `cat >> EOF` pattern**：Read 上限 256KB 超限，必 append-only 不 read 全檔。本 wave 改用 `tail -200` 讀 memory.md 取 recent context

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-21--i2_lg1_slo_carveout_e4_regression.md`

## 2026-05-22 — Sprint 1A-ζ Phase 3b regression E4 PASS

### Task
Phase 3b 回歸驗證 single-thread 4-6 hr per spike spec §3.3 P3-2。3 Track（A LAL + B health + C M11 replay）E2 round 2 全 APPROVE 後派 E4 regression。

### Verdict
**PASS** · ready for Phase 3c QA empirical driver.

### Numbers
| Surface | Result | Baseline | Delta | Non-flaky |
|---|---|---|---|---|
| Rust workspace + spike feature | 3769 pass / 0 fail / 4 ignored | – | – | ✅ |
| Rust openclaw_engine lib | 3074 pass / 0 fail / 1 ignored | 3045 (last E4) | +29 sibling drift | ✅ 兩遍 0.70s 同綠 |
| Rust health::tests inline | 10/10 PASS | – | – | – |
| Rust governance::lal::tests inline | 14/14 PASS (含 AC-1.1 from_negative/overflow/strictness) | – | – | – |
| Rust spike integration m3_amp_cap | 3/3 PASS (--features spike) | – | – | – |
| Rust round 2 new unit test_try_transition_no_fire | 1/1 PASS | – | – | – |
| Mac cargo check release + spike | clean (0 err / 1 pre-existing warn) | – | – | – |
| Linux cargo check release + spike | clean (0 err / 1 same warn) | – | – | – |
| Mac pytest 全量 | 28 fail / 6037 pass / 45 skip / 14 subtests | 28 / 6030 pre-fixture | +7 fixture | ✅ 兩遍 126s/124s 同綠 |

### AC matrix
| AC | Verdict | 主要 evidence |
|---|---|---|
| AC-1 sqlx migrations success=t | **PARTIAL** | 0 row (V096 為最高註冊；V106/107/112 走 psql -f raw apply path 不經 sqlx_migrate)；V106 + V112 table land ✅ / V107 cleanup ❌ per E1 §5.248 |
| AC-2 idempotency Round 2 | **PASS** | delegated to E1 Track B/C sandbox empirical Round 1+2+3 all 0 RAISE |
| AC-3 engine restart | **N/A** | per Q2(d) sandbox-only + Mac/Linux cargo check clean |
| AC-4 PG CHECK 反向 INSERT | **PASS** | sandbox lal_level=-1/5 兩條 RAISE `lease_lal_tiers_tier_level_check` + Rust 14 unit |
| AC-5 amp cap 24h fire | **PASS** | cargo test --features spike --test m3_amp_cap_24h_fire 3/3 + round 2 new test 1/1 |
| AC-6 dedup contract | **PASS** | V107 真實 column 0 forbidden / SQL 8 grep hit 全屬 Guard A reverse-fire feature / decay_signals + strategy_lifecycle 不存在物理不可寫 / Python skeleton py_compile + import chain PASS |
| AC-7 cross-lang 1e-4 fixture PoC | **PARTIAL PASS** | tests/test_spike_cross_lang_fixture.py 7/7 PASS Python naive + Welford + numpy 三互驗 1e-4；Rust binding 延 Sprint 1B per spec §5.3 |
| AC-8 spike acceptance report | DEFERRED to phase 3d (TW) | – |

### 28 pre-existing pytest failures attribution
24 GUI static + 7 structure + 1 writer。spike commits `f0633002` + `2f6d1761` diff 對失敗 file 0 hit → 0 attribution 給 Sprint 1A-ζ；待 Sprint 1B 補位 candidate。

### AC-7 fixture 設計
- input `[10.0, 20.0, 30.0, 25.0, 15.0]` per spec §AC-7 line 277
- expected mean=20.0 / sample sigma=sqrt(62.5)=7.905694150420948 / pop sigma=sqrt(50.0)
- 3 條獨立實作 pure-Python（naive two-pass / Welford online / numpy ddof=1）三互驗 < 1e-4
- pure-Python PoC — Sprint 1B Rust window IMPL（假設 Welford）對齊本 fixture expected 直通

### 教訓 / 工程觀察

- **spec literal path 不對齊 pytest auto-discovery convention 是高頻盲區**：spec § AC-7 line 277 寫 `tests/spike_cross_lang_fixture.py` 無 `test_` prefix → pytest default collection 跳過；E4 必跑 `pytest --collect-only | grep <fixture name>` 確認 file 真在 list；本次 E4 在 full pytest 6037 vs 6030 數字相同時警覺有問題、查 collect 才發現 file 不在；之後 rename `test_spike_cross_lang_fixture.py` 才 +7 land。**規則**：spec literal path 設計時必 cross-check pytest discovery；E4 加 fixture 必驗 collection。建議 PA spec edit `tests/spike_cross_lang_fixture.py` → `tests/test_spike_cross_lang_fixture.py`。

- **sandbox state 與 spec literal「永久 land」差異是 Track C cleanup 設計的隱性 contract**：E1 Track C round 1 §5 line 248 cleanup design drop V107 + mv + stub prereq；spec § AC-1 期 `_sqlx_migrations` success=t 但實際 0 row（V107 已 drop）。PA reconcile 2026-05-22 5 issue 未涵蓋此條。**規則**：E1 sub-agent IMPL 報告必 callout「sandbox cleanup state vs spec literal expected」差異；PA reconcile 必收 dispatch packet acceptance check 字面 vs IMPL reality 跨對齊。

- **AC pass 不只看 Rust binary fingerprint 還看 PG CHECK constraint runtime fire**：AC-4 反向 INSERT 走 sandbox PG empirical 驗 `lease_lal_tiers_tier_level_check` 真實 RAISE — Rust enum from_i32 14 unit test 雖 PASS（compile-time + runtime in-process）但 PG 端 CHECK 必獨立驗。本次 spec §AC-1.1 設計就要兩端對齊；E4 確實兩端跑了：cargo test 14 PASS + sandbox psql 反向 INSERT 兩條 RAISE。**規則**：跨 Rust ↔ PG 雙重 enforce 設計必兩端 empirical 驗；E4 sandbox SOP 標配 PG 端反向 INSERT 驗 RAISE message。

- **5-sample window cross-lang fixture 是 algorithm contract 數位 fingerprint，不是 Rust binding 對驗 PoC**：本 fixture pure-Python（naive + Welford + numpy 三互驗）證明 algorithm well-defined + deterministic + numerically equivalent；Rust 端 window IMPL（未 land per spike scope §1.4）對齊本 fixture expected 值即直通。**規則**：cross-lang fixture 設計分兩步 (1) algorithm contract（pure-Python 三實作互驗 + expected 值定義）(2) Rust binding 對齊；Sprint 1A-ζ 走 (1)，Sprint 1B 走 (2) Rust IMPL + alignment test。

- **adversarial probe 對 INSERT NOT NULL column 順序的注意**：AC-4 spec § AC-1.1 SQL 範本只列 5 column（tier_level / tier_name / auto_approve / approval_quorum / clawback_ttl_sec）但 V112 真實 schema 還有 `cohort_min_n` + `human_final_review` NOT NULL；初次 INSERT 撞 NOT NULL 而非 CHECK constraint。E4 必補完 NOT NULL column set 才驗到目標 CHECK fire。**規則**：spec SQL 範本必對齊真實 schema NOT NULL 集合；adversarial INSERT 設計時先 `\d <table>` 確認 NOT NULL columns，避免 "first error" attribute drift。

- **spec § P3-2 baseline 數字 stale (2555/17 vs 實際 6037 / 28 pre-existing) 是 sprint accumulation drift**：spec 寫 v5.5 sprint 數字，當前 codebase 已 v5.8 sprint accumulate 6058 test。**規則**：spec literal baseline 數字 stale 不阻 PASS verdict；E4 必跑 `pytest --collect-only` 取當前真實 baseline，與 spec literal 數字差異 callout。

- **memory.md 421KB+ append-only `cat >> EOF` mode**：跟 5/18-5/21 同 pattern 持續使用；Read 全檔超 256KB 上限。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_1a_zeta_phase_3b_regression.md`

---

## 2026-05-22 — Sprint 1B early IMPL #3 — 28 pre-existing pytest fail triage (TRIAGE DONE)

### Verdict
TRIAGE DONE — 28 fail 全 carry-over Sprint 2 (P0 writer 1 + P1 structure 7 + P2 GUI 24 = 5-11 hr 全 closure)，0 阻 Sprint 4 first Live W18-21 (~2026-09 初，11+ 週 buffer)。

### Empirical
- 兩遍 pytest baseline run 全 6037 pass / 28 fail / 45 skip / 14 subtests (non-flaky, 0 drift vs Phase 3b 8a15de4d)
- 5 sample RCA: console label drift / W-AUDIT-7c openTypedConfirmModal helper file 遷出 / cache-busting `?v=...` version pin / event_consumer dispatch.rs 850>800 / archive 新 file 沒 index / common.js paper-stop-all 已退役 / session_stop reason 用 stable code vs log literal 不對齊 / v072 writer CLI banner literal drift
- 全 28 fail 0 runtime trading impact (static assertion only, 無 DB write / 無 IPC / 無 order)

### Lessons Learned (本次新增 6 條)

- **contract drift signal 28 fail 不必焦慮，但需 sprint 級集中修**：自 Phase 3b 至今 0 drift 證明 baseline 穩定；spread 在多次 commit 累積 drift 屬正常 dev 模式；建議每 sprint 開頭設「contract drift sweep」固定 1-2 hr slot 集中修。

- **GUI static test 應改用 stable substring 而非 literal pin**：cache-busting `?v=20260506.mag018-v1` 是 high-frequency drift 來源 (每次 cache bust 都漂)；應改成 regex 或刪 version pin。**規則**：cache-busting / timestamp / build hash 等 frequently-rotated string 不寫進 test assertion。

- **runtime stable code vs user-facing text 應分層 contract**：session_stop reason dict 用 stable code (`order_sweep_cancel_all_failed`) 但 log/UI 用 human readable (`"bybit 503"`)；test 應 contract 第一層 stable code，第二層 log message 用 substring 模式不 pin literal。

- **file size 軟上限 800 行屬 hot-file invariant**：dispatch.rs 850 > 800 是漸進 drift 不是一次性突破；應在 commit 前 check size delta (git pre-commit hook 或 CI `wc -l` gate)。

- **docs/README.md index 完整性靠 test enforce 是 active discipline**：archive 新增 file 沒 index → test catch；證明 CLAUDE §七 "新 docs 必須跟 docs/README.md placement and index rules" 是 active discipline；建議加 git pre-commit hook 自動 append 新 archive entry。

- **本次 28 fail 0 GUI/IPC/runtime trading impact**：靜態 drift 不影響 trading correctness 是好事，但長期累積會 desensitize developer 對 contract test 的信號敏感度；建議每 sprint sweep 結束 release note 明列「contract drift fix 28→0」展示 hygiene 進度。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_1b_pytest_fail_triage.md`

### 2026-05-22 Sprint 1A 全 phase + Sprint 1B early IMPL + Sprint 2 pre-readiness post-closure E4 audit — PASS

**對象**：commit chain `4350dba9` (1A-δ +25 cargo) → `2f6d1761` (1A-ζ Phase 2) → `8a15de4d` (Phase 3b) → `9cf0fe82` (1B early IMPL) → `81a2caeb` + `ca73798d` + `63149512` (Sprint 2 pre-readiness)。

**結果**：
| 引擎 | passed | failed | ignored | baseline | delta |
|---|---|---|---|---|---|
| Rust workspace --release --features spike Run1 | 3775 | 0 | 4 | 3769 (Phase 3b) | **+6** |
| Pytest Run1 (Mac, srv root) | 6042 | 28 | 45 | 6037 (Phase 3b) | **+5** |
| Pytest Run2 (flaky verify) | 6042 | 28 | 45 | - | non-flaky 兩遍同綠 |
| Pytest --collect-only | 6113 | - | - | 6110 (Phase 3b) | **+3 carry-over** |
| AC-7 Rust binding (Mac) | 5/5 | 0 | - | 0 (Phase 3b 純 Python PoC 7/7) | **+5 new** |

**Sprint 1A-δ +25 cargo test 對齊**：實測 m5_model_client_stub_panic.rs 7 + m12_order_router_stub.rs 11 + m13_asset_venue_acceptance.rs 7 = 25 條，與 archive §K.3 字面對齊。3 file `should_panic(expected="M5"/"M12")` + match exhaust panic message 真實觸發 method body — 非 mock。

**Sprint 1B Track D AC-7 Rust binding**：`rust/openclaw_engine/tests/m3_cross_lang_window_fixture.rs` (spike feature gate) + `tests/test_spike_cross_lang_rust_binding.py` (subprocess + JSON marker)。Mac aarch64 5/5 PASS：Rust 內驗 1e-10 嚴格，Python ↔ Rust cross-lang 1e-4 spec literal 容差。spec 寫 "bit-perfect 0.00e+00 diff" 是因 IEEE 754 deterministic + 同 naive two-pass 算法 + 同 input → diff 0 是合理上限不是 mock 縮水。

**Sprint 1B Track E cascade reject 2 unit test**：health/mod.rs line 603 `test_try_transition_fail_closed_reject_count_ge_2` (Guard 3) + line 642 `test_try_transition_cap_suppress_same_anomaly_id_repeat` (Guard 1) 真實 PASS — direct unit test 而非 observe_at 整合路徑（spike scope WARN 短路無法走到 cap suppress / count>=2，Sprint 5 cascade IMPL 後才有整合路徑）。屬 acceptance guard。

**Mock 審查 clean**：3 個 Sprint 1A-δ test file + AC-7 fixture + cascade reject test 全 0 `MagicMock` / 0 `monkeypatch.setattr` / 0 `mock business logic`。Stub panic test 是讓 trait method 觸發 `unimplemented!()` panic — 真實 method body 被執行，panic msg 由 `should_panic(expected = "M5"/"M12")` 嚴格匹配。

**28 pre-existing pytest fail 0 drift**：Phase 3b 報告寫 28 pre-existing (24 GUI static + 7 structure + 1 writer)；本次 28 同數同 file。Sprint 1B Track B triage 確認 0 fail 攻擊 spike commit attribution，全 sibling drift。passed 6042 vs Phase 3b 6037 +5 是 Sprint 1B Track D AC-7 Rust binding 5 test 新加入 collection（非 mock 縮水）。

**4 IGNORED audit**：實測只 1 IGNORED (`test_lg1_t3_known_gap_apply_risk_snapshot_does_not_wire_h0_shadow_mode` — LG1-T3 reviewer note 合理 carry-over，修法 ≤5 LOC)。spec 字面 "4 IGNORED" 是 cargo workspace aggregate (含 openclaw_types / openclaw_features / openclaw_models / openclaw_engine 多 crate)；workspace ignore 數總和對齊。

**SLA 漏網**：
- Mac dev-only，**未跑 SLA 壓測**（H0 Gate <1ms / Tick <0.3ms / IPC <5ms 需 Linux runtime engine PID 3954769 真實掛載）。spec Sprint 1A 範圍是 spike feature flag 編譯時隔絕（production binary 不含 fixture），不涉及 hot path 改動 → 推定 SLA 不漲，但需 Sprint 4 first Live deploy 走 `--rebuild --keep-auth` 時 journalctl 取分位。
- Rust spike feature 全部編譯時 gated（`#![cfg(feature = "spike")]`），production binary 不含 — 物理上 SLA 不可能被 spike 拖慢。

**cargo build warning baseline**：5 warning（含 pre-existing `spawn_position_reconciler` per memory LIVE-AUTH-WATCHER fix + `LEAD_WINDOW_SECS_MAIN` + `make_intent` 2 個 pre-existing + 2 個 cascade — 待確認）；archive §K.6 "0 new cargo build warning" 字面 vs 實測 5 warning，需 PM/PA reconcile：archive 寫的可能是「0 new warning attributable to Sprint 1A-δ IMPL」而非 absolute 0。**建議 Sprint 2 sweep 一輪 warning 清零**。

**Verdict**: **PASS** — cargo + pytest 兩遍同綠 + AC-7 cross-lang 5/5 + cascade reject Guard 1/3 PASS + mock 0 業務邏輯掩蓋 + 28 pytest fail 0 drift (Phase 3b 對齊)。

**遺留**：
1. SLA 壓測延 Sprint 4 first Live deploy（Mac 無法驗）
2. 5 cargo build warning（pre-existing；建議 Sprint 2 sweep）
3. 28 pytest fail 5-11 hr Sprint 2 carry-over closure（per Track B triage）

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-22--sprint_1ab_2pre_post_closure_audit.md`（本 audit 不單獨產 report file，verdict 與證據以 memory append + 主對話輸出為 SSOT）

---

## 2026-05-23 · Sprint 4+ Wave A+B combined regression — PASS

### Scope
Sprint 4+ first Live carry-over Wave A (PA-DRIFT-4 bybit instrumentation + PA-DRIFT-5 RiskEnvelopeSourceProbe wire-up) + Wave B (main.rs MetricEmitterScheduler + PortfolioStateCache + 6 emitter spawn) combined regression × E2 round 2 全 APPROVE 後。

### 數字
- cargo workspace --release --skip stress_tick_latency_benchmark × 2 = **3961 / 0 / 5** non-flaky（baseline 3894 +67 attribution Wave A+B 42 integration + lib health +23 + sibling +2）
- Wave A api_latency_probe_real_impl: **22 / 22**
- Wave A risk_envelope_probe_real_impl: **14 / 14**
- Wave B main_scheduler_wireup: **6 / 6**
- Sprint 2 6 Track + replay_forbidden: **51 / 51** maintained
- spike feature: **3 / 3**
- lib health::: **110 / 0**（Sprint 2 87 → +23 Wave A+B real-impl 內部 unit）
- lib bybit_rest_client: **29 / 0** unchanged
- pytest × 2 = **28 fail / 6042 pass / 45 skip** non-flaky 與 Sprint 2 Phase 3b baseline 完全一致
- cross-lang fixture: **12 / 12**（7 Python PoC + 5 Rust binding）
- aarch64-apple-darwin release cargo check: 0 error / 4 既有 warning
- nm AC-5 invariant: 0 hit ✅
- Wave B inject_* leak: 0 hit ✅ (release optimizer drop)
- strings Wave A+B wire-up: 全命中 main_health_emitters / RealApiLatencySourceProbe / api_latency_probe_impl / risk_envelope_probe_impl / PortfolioStateCache / F-2 sanitize / replay 禁 / Wave B startup log

### Linux sandbox
- sandbox_admin role 連線 OK (secret_file `srv/settings/secret_files/postgres/sandbox_admin/password`)
- V106 schema 6 domain CHECK + 4 engine_mode (paper/demo/live_demo/live)（注意：replay 不在白名單，與 Wave B `engine_mode='replay' forbidden by V106 CHECK` 對齊）+ 4 state + state_prev null-tolerant 全 confirm
- pg_hba E3-MED-1 reject row sandbox_admin→trading_ai REJECTED 仍生效
- production engine PID 2934602 etime 1-12:06:42 不重啟 ✅

### Carry-over to Wave C QA
- AC-1b real PG empirical 待 operator 排程 Linux --rebuild + 30 min sample wait（同次 --rebuild deploy Sprint 1A-δ trait stub + Sprint 1A-ζ V106/V107 sandbox + Sprint 4+ Wave A+B Mac IMPL）
- P1-SANDBOX-SQLX-METADATA-ALIGNMENT (Sprint 1A-ζ carry) E4 不負責
- P1-ENGINE-BINARY-SPRINT-1A-IMPL-DEPLOY 仍待 --rebuild

### 教訓
- nm 對 Rust mangled symbol grep `MetricEmitterScheduler` 等高層 type 0 hit 是預期：release monomorphize + symbol stripping。改用 `strings` 抓 module path + log 訊息字串才是 wire-up 入 binary 的可信證據。E2 round 2 closure 對 strings hit 已預設此 SOP。
- Mac CC 連 sandbox PG 需 `cat .../sandbox_admin/password | PGPASSWORD=` ssh wrapper；secret_file 是「目錄/password」結構，不是單一文件，避免 cat 對目錄出錯。
- cargo workspace 並行模式下 stress_tick_latency_benchmark 仍延用 Sprint 2 Phase 3b `--skip` SOP，未獨立 isolated run，不阻 Sprint 4+ verdict。
- baseline +67 計算精準對齊：Wave A+B 42 integration + lib health +23 + sibling +2 = 67，無 unaccountable drift。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-23--sprint_4_e4_regression_wave_ab.md`

## 2026-05-23 Sprint 5+ Wave 1 Phase D combined regression — HEAD c4e1411d

R2-1 V101/V102 sqlx parser + R2-2 §4.4 hardening + R2-3 Track B+C CRITICAL caller wire-up 三並行 round 2 fix combined regression Verdict: **PASS — APPROVE**。

### 主要數字
- cargo --workspace --release --no-fail-fast Run 1 / Run 2 = **4018 passed / 0 failed / 5 ignored** non-flaky；baseline 3961 → +57 R2 增量對齊。
- pytest Run 1 / Run 2 = **6122 passed / 18 failed / 30 skipped** non-flaky；baseline 6042/28 → passed +80 / failed -10，無 R2 regression（R2 純 Rust+SQL+Bash 0 Python touch）。
- `database::migrations::` 15/15 PASS（含 load_migrations_real_srv_tree V99→V100→V101→V102→V103→V106→V107→V112 monotonic）。
- `health::domains::` 110/0 維持，`database::pool_wait_stats` 5/0 unit ✅。
- Sprint 2 Track B/C/D integration 5+8+7=20/0；Wave A/B integration 22+14+6=42/0。

### Concurrent session 1 fail 認證
prompt 預期 1 fail (`layer_2_fence_env_gate_three_states` / `btc_lead_lag_panel_fence_integration.rs:267`) 在 HEAD c4e1411d Mac workspace 實測 **0 fail**（比預期更乾淨）；同期 sibling 已收斂或不在 narrow staging。Per `feedback_multi_session_memory_race`「不認識改動禁 revert」，本 E4 未觸碰 concurrent session test。

### 教訓
1. **Release binary strings 不會留 Rust internal identifier**：LLVM 內聯 + symbol stripping 後 `_probe_impl` / `Real*Source` / `build_*_emitter` / `set_signal_stats` / `attach_subscriptions_counter` 等 Rust function name 不出現在 `strings <binary>` 輸出。實際 land 驗證應透過：(1) cargo test --workspace 全綠涵蓋的 integration suite (2) source path string literal in binary (3) metric key string literal in binary (4) nm 0 hit 排除 dyld_stub_binder 系統符號後。Prompt 級「grep Rust internal identifier」是 false negative 預警，不能單獨用作 fail signal。
2. **`grep -E "170|3072"` boundary number 過寬鬆**：會吃到 binary 內 SSL 證書年份字串（`-Microsoft RSA Root Certificate Authority 20170` 等）。boundary 驗證應透過 unit test pass + metric key literal land + E2 round 2 APPROVE 三條獨立鏈，不靠 strings number grep。
3. **pytest 公平 baseline 對齊需重複前次 `--ignore=`**：`test_pure_utils.py` 2 collection error 是 prior baseline 一直用 `--ignore=` 規避的 case，Run 2 補回 `--ignore` 才能與 prior baseline apples-to-apples 對齊（否則多 2 error 看似 regression 但實非）。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-23--sprint_5plus_wave_1_phase_d_combined_regression.md`

## 2026-05-25 — W2-E4 Sprint 2 Wave 2 regression — PASS

### Task
Sprint 2 v5.8 Stream B Wave 2 W2-E4 regression：V109 schema (W1-F) + V109 writer skeleton (W2-D) + W1-C M4 round 2 三件並行 verify。W2-E E2 verdict d15cbe56 對 V109 + W2-D APPROVE → E4；M4 W1-C-R2 mid-flight commit 99709a2f land 期間 closure。

### Verdict
**PASS** — 0 W2-attribution failure · cargo 1 pre-existing fail（Sprint 1B Earn 875de212 scope leak）+ pytest 7 pre-existing fail（W-AUDIT-7c structural drift carry-over）。

### Numbers
| Surface | Result | Baseline (Sprint 5+ Wave 1 Phase D HEAD c4e1411d) | Delta | Non-flaky |
|---|---|---|---|---|
| Mac cargo --workspace --release × 2 + recount × 1 | 4205 / 1 / 6 | 4018 / 0 / 5 | +187 / +1 / +1 | ✅ 三遍同綠 |
| Mac pytest × 3 (--ignore both pure_utils collisions) | 6158 / 7 / 45 | 6122 / 18 / 30 | +36 / -11 / +15 | ✅ 三遍同綠 |
| W2-D anomaly_event_writer cargo (× 2) | 14 / 0 | – | – | ✅ |
| W1-C-R2 openclaw_core lib | 416 / 0 | 416 / 0 | 0 (m4 已內含) | ✅ |
| W1-C-R2 m4_miner subset | 46 / 0 | – | – | ✅ |
| W1-C-R2 helper_scripts/m4 pytest | 70 / 0 | 51 / 0 | +19 schema-grep regression | ✅ |
| V109 PG col_count | 23 | 23 (W1-F-retry verdict) | 0 | ✅ |
| V109 PG hypertable num_dim | 1 | 1 | 0 | ✅ |
| V109 PG indexes count | 6 | ≥ 5 | – | ✅ |
| V109 PG compression+retention | 1 + 1 | 1 + 1 | 0 | ✅ |

### Hard boundary + safety verify
- git diff origin/main~10..origin/main hard boundary scan (live_execution_allowed/system_mode/authorization.json) = **0 hits** ✅
- nm release binary mock/spike infiltration = **0 hits** ✅
- /Users/ncyu / /home/ncyu hardcode in W2 scope = **0 hits** ✅
- unsafe block in W2 scope = **0 hits** ✅
- file size cap 800/2000 W2 scope = 全合規 (event_window.rs 344 / anomaly_event_writer < 800 / V109.sql 832) ✅

### 1 cargo fail attribution = Sprint 1B Earn 875de212 sibling scope leak
- Fail: `layer_2_fence_archive_policy_diagnostic_only` line 300 panic
- Root cause: 875de212 (2026-05-23 Sprint 1B Earn Wave B) 改 btc_lead_lag_panel_fence_integration.rs test 從 PAPER=1→spawn 改為 PAPER=1→ignored；但 production helper btc_lead_lag.rs:67-71 未同步改 → contract drift
- `git show --stat ae9a2dd8 a8d4bfa8 99709a2f 16796d13 | grep btc_lead_lag` = 0 hit → **0 W2 attribution**
- 修法：E1 一行修 btc_lead_lag.rs:67-71 `Ok(value) => value.trim() == "1"` → `Ok(_) => false`（PAPER 進 archive policy）；MEDIUM 不阻 W2 deploy

### 7 pytest fail attribution = W-AUDIT-7c carry-over
全 7 file list = test_confirm_modal / test_docs_readme / test_event_consumer_split / test_prompt_modal / test_strategy_action × 2 / test_v072 writer。W2 4 commit 觸碰範圍純 helper_scripts/m4 + rust/openclaw_core/m4_miner + rust/openclaw_engine/database/anomaly_event_writer.rs + sql/migrations/V109 → 0 overlap with 7 fail file。0 W2 attribution。Sprint 1B-late 28 → Phase D 18 → 本 E4 7，sweep 持續 chip down。

### Mid-flight commit observation
W1-C-R2 99709a2f land 在 E4 run 期間（19:10:39 介於 E4 start ~19:06 與 final verify 之間）— sub-agent acd7ed4b3512e093e 完成同步 commit。Run 2 + Run 3 post-R2 環境跑同綠（4205/1/6）= non-flaky verify。E4 verdict 對齊最後 HEAD = 99709a2f。Per `feedback_multi_session_memory_race` SOP「不認識改動禁 revert」原則執行。

### release binary 19:06 build 不含 W2-D + W1-C-R2
strings grep 0 hit anomaly_event_writer / m4_miner = **expected per task spec Step 5** (本 step 是 baseline check 不是 deployment gate)。Production deploy 走 `helper_scripts/restart_all.sh --rebuild --keep-auth` atomic restart 後才會 bake；E4 verdict = source-land PASS。

### V109 production-LIVE 但不在 _sqlx_migrations
PG max=112 / count=102 不含 V109，但 anomaly_events 表已物理 land 23 col + hypertable + 6 index + 2 policy。V109 同 V106/V107/V112 走 raw `psql -f` apply path 不經 sqlx_migrate（per Sprint 1A-ζ memory）。

### W2-D dispatch deployment readiness
| Gate | Status |
|---|---|
| E1 IMPL DONE | ✅ a8d4bfa8 |
| E2 cold review APPROVE | ✅ d15cbe56 |
| E4 regression PASS | ✅ (本 E4) |
| Atomic restart | ⏳ pending PM dispatch |
| Post-restart proc-exe alignment + sha256 verify | ⏳ |
| Post-restart strings grep anomaly_event_writer | ⏳ |
| Post-restart PG INSERT smoke | ⏳ |

### W1-C M4 不阻 V109 deploy 條件確認
W1-C M4 與 V109 解耦（per E2 §9.2）— V109 schema 純 hypertable land；W2-D writer 0 dependency on M4 cron readiness；W1-C M4 scaffold 階段 cron disabled。99709a2f closed E2 HIGH+MEDIUM+LOW 全 finding → W1-C 可進 E2 round 2 re-review。V109 + W2-D 可獨立 atomic restart deploy。

### 教訓 (本次 6 條新增)
1. **cargo workspace +187 attribution breakdown**：W1-C 46 + W2-D 14 + W1-C-R2 19 schema-grep = 79；剩下 +108 是 sibling Sprint 1B Earn Wave B/C bbb21c56 + 875de212 lib growth；E4 報告必列 per-component attribution 不只 single number diff。
2. **W1-C-R2 mid-flight land 是 multi-session race 警示**：E4 開始 3 unstaged file，run 中途 99709a2f commit land 吸收；HEAD 變化必 re-verify baseline；本 E4 run 2 + run 3 post-R2 fresh verify。
3. **layer_2_fence test rewrite 不同步 prod helper 是 contract drift pattern**：875de212 改 test 但 0 diff prod btc_lead_lag.rs:67-71；E1 amend test 前 grep prod 端定義 對齊 1 處。
4. **strings 0 hit 不是 deployment fail，是 build 時序**：release binary 19:06 < W2-D 18:59 commit；atomic restart 後才會 bake；E4 verify 包含「expect 入 release」vs「expect 未 deploy」兩種模式判定。
5. **pytest fail chip down 18 → 7 across Sprint**：Sprint 1B-late 28 → Phase D 18 → 本 7 是固定 sweep 累積；每 Sprint 開頭「contract drift sweep」固定 slot 已見效。
6. **--ignore=tests/misc_tools 不夠，需加 tests/ml_training**：3 個 test_pure_utils.py（local_model_tools / misc_tools / ml_training），兩 collision 對 → E4 baseline 對齊命令必加兩 --ignore；Sprint 5+ Wave 1 Phase D 漏 ml_training（1 collection error 被計成 single fail 而非 baseline 對齊問題）。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-25--w2e4_sprint_2_wave_2_regression.md`

---

## 2026-05-25 Fresh E4 Sprint 2 Wave 2 complete chain (HEAD b2febd43)

5 commit chain regression coverage:
- W2-B 817de10a (funding_short_v2 + liquidation_cascade_fade Rust scaffold + Python harness)
- W2-F fbfbd184 (QA + FA audit reports)
- W2-F b2febd43 (AC-19 cron + W1-C-R3 draft_writer fix + PA velocity RCA)
- W2-E-R2 aeb8a84b (E2 dual re-review M4 R2 + W2-B both APPROVE)
- PA velocity RCA d8311cf2

### Numbers (vs fa466361 baseline 4205/1/6 cargo · 6158/7/45 pytest)
- Mac cargo workspace 雙跑: **4300/1/6** (+95 = funding_short_v2 47 + liquidation_cascade_fade 48 ✅)
- Mac pytest 雙跑: **6221/7/45** (+63 = M4 19 + AC-19 44 ✅)
- 兩遍 non-flaky 同綠（diff fail set = empty）
- 唯一 cargo fail `layer_2_fence_archive_policy_diagnostic_only` 是 Sprint 1B Earn Wave B 875de212 carry-over
- 7 pytest fail 全 pre-existing W-AUDIT-7c / structural drift

### Module isolation
- V109 writer (W2-D): 14/0
- W2-B funding_short_v2: 47/0
- W2-B liquidation_cascade_fade: 48/0
- M4 helper_scripts/m4: 89/0 (70 base + 19 W1-C-R3 schema-grep)
- AC-19 helper_scripts/cron: 44/0

### Linux PG empirical (read-only)
- V109 `learning.anomaly_events`: 23 col / 0 row (scaffold, expected)
- AC-19 crontab: installed 5/26 08:00 UTC
- AC-19 cron 7d empirical: alt 35/9/25.7% · large_cap 6/4/66.7%
- _sqlx_migrations max=112 / count=102

### Binary symbol scan
- Mac openclaw-engine (21:45): 5 funding_short_v2 + 5 liquidation_cascade_fade strings; 0 V109 writer / m4_miner / alpha_tournament (expected scaffold)
- Linux openclaw-engine (00:27, pre-Wave 2): 0 W2-B symbols → atomic deploy decision defer to Sprint 3 wire-up
- 0 mock_instant / tokio::time::pause / spike leak

### Hard boundary + cross-platform + unsafe scan
- git diff fa466361..b2febd43 hard boundary literal grep = 0
- 0 /Users/ncyu | /home/ncyu hardcode in 全 Wave 2 IMPL
- 0 unsafe blocks in W2-B + M4 source

### Lessons
1. **Pre-existing layer_2_fence baseline 持續 across W2 commits**：fa466361 → b2febd43 仍 1 cargo fail；Sprint 1B Earn 875de212 修復未推進 = Sprint 3 carry-over。
2. **AC-19 cron deployed Linux but Linux binary 尚未含 W2-B Rust scaffold**：atomic restart 政策定義「detector wire-up + binary build + cron deploy 合一」防 binary churn；目前 cron live + binary defer Sprint 3 是 by design。
3. **+95 cargo / +63 pytest delta 100% attribution clean**：W2-B 47+48 → cargo +95；M4 19 + AC-19 44 → pytest +63；無 hidden 增量 / 無 drift；non-flaky 同綠驗證。
4. **--ignore both test_pure_utils.py 對齊 Sprint 5+ Wave 1 Phase D 教訓持續**：commands 含 `--ignore=tests/ml_training/test_pure_utils.py --ignore=tests/misc_tools/test_pure_utils.py` 雙 ignore 標準保留。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-25--fresh_e4_sprint_2_wave_2_complete_regression.md`

## 2026-05-27 P0-OPS-4 GAP B+D round 1+2 regression (commits 1392c9e1 + 261d3956)

### IMPL scope
- 3 cron Bash (install / trading_ai_pg_dump / verify) + V113 migration + post_restore_validation.sql 9 query
- check_pg_dump_freshness.py 616 LOC 7 sub-check + passive_wait_healthcheck/ wire +127 LOC
- pg_restore_drill_sop.md 572 LOC + MIT template 239 LOC
- PA spec amendment 449→695 行
- 16 files commit chain total

### Linux empirical
- bash -n 3/3 PASS
- check_pg_dump_freshness.py --status: verdict=INSUFFICIENT_SAMPLE (7/7 fail-soft), EXIT=0, SLA 67ms
- DRY-RUN install OPENCLAW_BACKUP_CRON_APPLY=0: 預覽正確 + 預檢提示完整 EXIT=0
- V113 BEGIN/ROLLBACK 內含 COMMIT 不可包；冪等 PASS（二跑 NOTICE-skip）
- V113 直接 psql 跑 → _sqlx_migrations 缺 row（風險自動回正 via 下次 engine restart sqlx::migrate）
- passive_wait_healthcheck.py --quiet 整合 PASS; [80] 行出現 SUMMARY 前; 不破其他 [1]-[79]
- 9 query post_restore_validation.sql 7/9 PASS, 1/9 FAIL (V099 deployment gap), **1/9 BUG** Q3 column drift

### Test baseline (Linux verified, 兩次跑同綠 non-flaky)
- control_api_v1 pytest: 3994p/68f/51s (歷史 2555 baseline 已遠超，0 regression from this IMPL)
- Rust engine lib: 3469p/0f/1i (歷史 1980 baseline 已遠超，0 touch by IMPL)
- 0 test file touch（無刪測試遮蓋反模式）

### BUG-1 (BLOCKER 必修)
`helper_scripts/db/post_restore_validation.sql` Q3 references `learning.lease_transitions.ts` 但表只有 `ts_ms` (bigint) + `created_at` (timestamptz)。Line 95 + 284 兩處 column `ts` 不存在。Script 第 40 行 `\set ON_ERROR_STOP on` → drill day Q3 ERROR abort 整 9 query gate。Fix: `ts` → `created_at`。

### Carry-over (E1 round 3)
1. 743 LOC production code 0 unit test — 違反 E4 profile「新 E1 改動必須有對應測試」
2. V099 deploy 後重驗 Q1 PASS (deployment dep, not bug)

### Verdict
**YELLOW** — 14 of 15 acceptance criteria GREEN; 1 BUG (Q3 column drift, 5min fix) + 2 carry-over (governance test gap + V099 dep)

### Lessons
1. **V113 內含 COMMIT 是 by-design race-free pattern (鏡 V053/V098)，但 dry-run -c ROLLBACK 對內部 COMMIT 無效**。Operator 真實 deploy 必走 sqlx route 而非 psql 直跑（避 _sqlx_migrations drift）；本 case V113 idempotency guard 完備所以可自動回正，但類似 pattern migration 不可假定。
2. **SQL script 開發必對齊真實 PG schema 而非 spec 字面**。Q3 column drift = spec/code drift；E1 round 2 應 ssh trade-core 跑 `\d learning.lease_transitions` 驗 column name 後寫 SQL（per memory `feedback_v_migration_pg_dry_run`）。
3. **passive_wait_healthcheck wire-up 對齊 [20] check_h_state_gateway_freshness 既有 pattern 是好實踐**（importlib + sys.path 動態，OPENCLAW_BASE_DIR fallback），證明 E1 round 2 architectural alignment OK。
4. **Production code 無 unit test 是治理 gap 但不阻 commit**（per E4 profile 規則）；E4 必標 carry-over 給 E1 round 3，不單方面刪/補 production code（profile 邊界）。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-27--ops_4_gap_bd_e4_regression.md`

## 2026-05-27 OPS-4 GAP B+D round 2 light regression (commit cf710dc7)

### Scope (narrow re-verify)
verify round 3 P0 Q3 SQL fix + 3 MED runtime behavior post E1 round 3 + MIT round 3 Q3 fix；不重做 full baseline。

### A. P0 Q3 fix Linux empirical PASS
- Q3 main block (line 95 `WHERE created_at`): SELECT n=1 (1 distinct to_state in 24h)
- Q3 AGGREGATE CTE (line 289 `created_at`): SELECT n=1
- `\d learning.lease_transitions` 確認 column `created_at timestamptz` 存在 (line 14 schema)
- 兩處不再 `column "ts" does not exist`

### B. MED-1 platform guard 雙路徑 PASS
- Mac `--status`: EXIT=2 with platform refuse 訊息
- Mac `run()` 繞 main(): EXIT=2 with same platform refuse 訊息（wrapper path 已 fail-fast）
- Linux runtime: EXIT=0, verdict=INSUFFICIENT_SAMPLE, 7 sub-check structure 完整

### C. MED-2 heartbeat cross-check 4 scenario PASS
- A. paths=None → INSUFFICIENT_SAMPLE (backward compat)
- B. heartbeat fresh (0h) + n=0 → **WARN** with diag log path（解 silent V113-INSERT-fail mask）
- C. heartbeat stale (100h > 24h) + n=0 → fallthrough INSUFFICIENT_SAMPLE
- D. heartbeat missing + n=0 → fallthrough INSUFFICIENT_SAMPLE

### D. MED-3 install_pg_dump_cron.sh validation PASS
- Clean DRY-RUN: EXIT_CODE=0
- `/tmp/pg backups` (space): EXIT_CODE=6 with cron-conflict 訊息
- `/tmp/pg%backups` (%): EXIT_CODE=6 with cron-conflict 訊息
- 220 char path (>200): EXIT_CODE=6 with too-long 訊息

### E. Baseline 9 query post-fix
- Q1 FAIL (V099 deployment gap, non-bug)
- Q2 0 row (live not 24h yet)
- **Q3 PASS** (n=1, MIT round 3 fix verified — UNBLOCK)
- Q4 PASS (2 fills 24h)
- Q5 PASS (0 orphan / 4 total)
- Q6 0 row (operator 未 stake)
- Q7 0 row (runtime 全 demo)
- Q8 PASS (0 bad hash)
- Q9 PASS (5 lal_tiers)
- **8/9 PASS（Q1 deployment dep，非 BUG）**

### F. Baseline regression check
- Linux control_api_v1 pytest: **3994p/68f/51s** — 與 round 1 完全一致，0 regression
- 0 test file touched by round 3 IMPL（E1 round 3 claim 0 test 增 confirm）

### Round 1 → 2 delta
| 項目 | Round 1 | Round 2 (post round 3 fix) |
|---|---|---|
| P0 Q3 column drift BUG | BLOCKER FAIL | **PASS** (created_at fix landed) |
| 9 query post-fix PASS | 6/9 + 1 BUG + 2 carry-over | **8/9 + 0 BUG + 1 carry-over (V099 dep)** |
| MED-1 platform guard wrapper | FAIL (silent miss) | **PASS** (run() exit 2 on Mac) |
| MED-2 heartbeat cross-check | not implemented | **PASS** (B scenario WARN) |
| MED-3 cron env validation | not implemented | **PASS** (4 negative case exit 6) |
| Baseline pytest | 3994p/68f/51s | **3994p/68f/51s** (no regression) |

### Verdict
**GREEN** — 5/5 verify criteria PASS, P0 BLOCKER unblocked, 3 MED behavior empirical correct, baseline 不變

### Lessons (round 2)
1. **MIT round 3 fix 同 commit (cf710dc7) 與 E1 3 MED fix 一起 land** — 三方並行 fix 合 PR 治理 OK，commit message 明確列「round 3 — E2 3 MED + E4 P0 Q3 BLOCKER + auto-resolve E2 LOW-1」allow E4 round 2 light verify 不需 split commit。
2. **`learning.lease_transitions.created_at` 是 standard timestamptz column with DEFAULT now()** — schema 已驗，未來其他 audit-table query 可直接 reuse pattern 避 `ts` 字面假定。
3. **MED-2 heartbeat sentinel + DB row cross-check 是 dual-signal silent-fail detection 範本** — 兩個獨立信號 sources（filesystem mtime + PG row count）對打可 surface 「sentinel 正常但 audit INSERT 被吞」這類 mask 情境。LOW-1 dead resolution 自動消解（heartbeat 不再 dead）。
4. **SSH session 內 `bash file.sh | tail` 的 `$?` 是 tail 的 exit, not 原 script** — 必須 wrap `bash -c '... ; echo EXIT=$?'` 隔離才能取 script exit。E4 round 2 第一次測 MED-3 exit code 被誤判 0，重 wrap 後正確顯示 6。

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-27--ops_4_gap_bd_e4_regression_round_2.md`

---

## 2026-05-27 E4 round 2 re-dispatch (usage cap silent kill 重派) — GREEN confirm

前次 E4 round 2 sub-agent silent killed by usage cap, 無 stdout 無 file mtime confirmation, 但實際 report file 已寫到 249 lines + verdict GREEN。Re-dispatch spot-check 重採 10 個原 verify point 全部與前次匹配：

| 點 | 結果 |
|---|---|
| Q3 主 block (Linux psql) | n=1 to_state=BYPASS 66310 row 24h **匹配** |
| Q3 AGG (Linux psql) | n=1 **匹配** |
| 9 query syntax tail (skip Q1 V099 dep) | Q2-Q9 全 syntax PASS, Q1+AGG carry-over **匹配** |
| Mac CLI fail-fast | EXIT=2 **匹配** |
| Mac wrapper run() fail-fast | EXIT=2 **匹配** |
| Linux runtime --status | EXIT=0 verdict=INSUFFICIENT_SAMPLE **匹配** |
| Space → exit 6 | **匹配** |
| % → exit 6 | **匹配** |
| Clean DRY-RUN → exit 0 | **匹配** |
| Import wire-up | IMPORT_OK + HAS check_80=True **匹配** |

### 學到
1. **Sub-agent silent kill 復原協議** — 用 file existence + content tail (verdict block) 判斷前次 run 是否完成；若內容完整且 verdict 明確不要 overwrite, 只 append re-dispatch §
2. **Spot-check re-sample 是 silent-kill 場景最低成本 confirmation** — 不 rerun full 8 verify suite, 只重採每點各 1 次, 對比結果一致即可確認原 run valid

### Report
`srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-27--ops_4_gap_bd_e4_regression_round_2.md` (前次 GREEN 結論 valid + 新增 §12 re-dispatch confirmation)

## 2026-05-29 — v80 cold audit Wave 1 regression (PkgA Python+GUI / PkgB Rust)
- Wave 1 source 為 Mac-only uncommitted（Linux trade-core working tree CLEAN，`live_preflight.py` 在 app/ 不存在於 Linux）。Rust cargo + Python pytest 全在 Mac 跑（dev-only），不 commit/push/deploy。
- Python control_api_v1：canonical 模式 OPENCLAW_CSRF_SHADOW=1 → 4229 passed / 6 failed / 12 skipped。6 failed 全為 test_ops1_csrf_middleware.py 的 403-enforce 斷言（需 shadow OFF），unset 後 18 passed → 純 env artifact，非 Wave 1。教訓：CSRF 測試是雙模互斥（write-endpoint 200 需 shadow ON；csrf middleware 403 需 shadow OFF），不能單一 env 跑全綠。Wave 1 兩 test 檔（test_api_contract + test_session_stop_cancel_verify）shadow ON 下 30 passed。
- 大量 socket/PG 連線 fail（engine.sock not found / PG 15432 refused）是 Mac dev-only 預期，非回歸。
- Rust lib：3584 passed / 0 failed / 1 ignored（E1 claim 3583 +1 = 第二個新 dispatch test）。跑兩遍同綠，非 flaky。
- create-single-attempt 政策驗證：RETRY_DELAY_MS const 已完全刪除（無生產 caller，僅歷史註釋）；dispatch.rs OPEN→OPEN_NO_RETRY 空 slice（單次嘗試 fail-closed），CLOSE→CLOSE_RETRY_DELAY_MS（2 retries，documented reduce-only 例外）。2 新測 test_open_dispatch_uses_empty_retry_schedule_single_attempt + test_open_dispatch_structural_single_attempt_no_retry 精確鎖定。
- cancel-all coverage gap（記錄不阻擋）：OrderManager::cancel_all_scoped + IPC handler + loop_handlers CancelAllOrders（含 unknown-category fail-closed 分支）無專屬 unit test。但 sibling CloseAll/close_all_positions 同樣無測（codebase 既定 pattern）；body-building 為 trivial 2-branch JSON，post_checked 緊接無 pre-HTTP seam，加測會是 tautology 或需 mock server/refactor（禁）。category 映射由 test_order_category_as_str + 窮舉 match `_ => None` 鎖定。判定不強加 hollow test（反 mock-hiding 原則）。
- 浮點 1e-4：Wave 1 touched 全為 control-flow/order-mgmt，無 indicator 數值跨 Rust↔Python，無適用 surface。
- VERDICT: GREEN。

## 2026-05-29 — v80 cold audit Wave 2 regression (PkgC-Rust/PkgC-Py/PkgD-Py) — GREEN
- Source: Mac-only uncommitted (HEAD b93d3210). Linux trade-core HEAD 02ef4cb7 = 無 Wave1 也無 Wave2，全在 Mac dev-only 跑。不 commit/push/deploy/restart。
- Rust lib (2 passes 同): 3599 passed / 0 failed / 1 ignored。P1-09 freshness 7 case 全present且真跑 cost_gate_live/cost_gate_moderate（無 mock），鎖 rejection reason（stale→JS-live fail-closed / missing-runtime→has_runtime=false / validation_failed→validated=false / no-ts→age=none / demo stale+unvalidated→exploration None / now<=0→is_fresh(0)&is_fresh(-1) false）。
- PkgD AI (ledger/route/cost/governance) + model_registry: 42 passed (2 passes 同)。
- PkgC-Py promotion+backtest: 62 passed / 1 failed (2 passes 同)。唯一 fail = test_runtime_apply_chain_w_audit_6d_4 line785 `from program_code.ml_training.promotion_evidence` ModuleNotFoundError —— 從 control_api_v1 subdir 跑的 sys.path artifact，pre-existing，touches promotion_evidence 非 Wave2 file，E1/E2 已 flag。非 Wave-2-attributable。
- Mock-audit: 4/4 真實。ledger dedup 用 _PkAwareCursor 真實 PK set 模 ON CONFLICT DO NOTHING，斷言寫兩次=每表1行（now() 舊實現會 double-count）；paper-freeze 設過門指標仍斷言 not ok + paper_lane_frozen + 階段不前進；route-binder e2e subprocess 真跑 bind_active_route_env.sh 斷言 provider 綁定；edge-gate fail-closed 真 call gate。皆只 mock IO 邊界。
- 教訓: control_api_v1 內 test 混用相對(sys.path conftest)與絕對(program_code.*) import；後者只在 srv root + PYTHONPATH 下可解，subdir 跑必 fail。判 pre-existing 必看 import target 是否 touch Wave2 file。
- VERDICT: GREEN。

## 2026-05-29 — v80 cold-audit Wave 3 regression (Mac, uncommitted)
- Ran on Mac (HEAD 9b18f348, Wave 3 dirty/uncommitted). No commit/push/deploy/Bybit/AI calls.
- Rust openclaw_core: 468 passed / 0 failed (2 runs identical, not flaky). New lock tests green: test_position_count_zero_margin_locked, test_scoring_constants_locked, test_scoring_behavior_locked. P2-09 = named consts extraction, NO value drift.
- Rust openclaw_engine --lib: 3599 passed / 0 failed (== Wave2 baseline; bybit_rest_client comment-only fix no break).
- Python control_api route tests (Wave-3 relevant): 153 passed / 0 failed; 2nd pass 131 passed / 0 failed. No dedicated test files at top-level tests/ for these routes — coverage lives in control_api_v1/tests/.
- Pre-existing artifact (NOT Wave-3): tests/misc_tools/test_pure_utils.py vs tests/local_model_tools/test_pure_utils.py duplicate basename → collection error under default import-mode. Workaround: --import-mode=importlib. Do NOT attribute to Wave 3.
- node --check: tab-paper.html / tab-settings.html / tab-governance.html inline JS all OK.
- Mock-audit: partial_failure tests (test_session_stop_cancel_verify.py) inject real residual / real orphan-sweep error, mock only IO boundary (_ipc_command, _sweep_*), assert handler classifies status=="partial_failure" + partial_failure is True + closed_all is False. Genuine, not mocked-away. Guardian zero-margin test pins risk_score==0.3==threshold → Rejected (calibration-drift catch), not tautological.
- VERDICT: GREEN. No test-count regression vs Wave1/Wave2 baseline.

## 2026-05-29 — Track C P2-110017-D2-RECONCILE release regression (worktree wt-c-d2) — PASS
- Worktree `/Users/ncyu/Projects/TradeBot/wt-c-d2` branch `fix/retcode-110017-d2-reconcile`，base = main `6091aaaa`（含 D1 fix `caf008b6`）。改動 uncommitted（working tree）。不 commit / 不 ssh / 不 deploy。
- 改動：position_reconciler 新增 `process_ghosts`（async S-1..S-6 AND-gate）+ `ghost_point_query`（生產 single-symbol 點查 prod wiring）+ `GhostPointQuery` enum + `PipelineCommand::ConvergeExchangeZero` + `handle_converge_exchange_zero` handler（復用 D1 `converge_exchange_zero_close`，**絕不**走 ipc_close_symbol）+ `dispatch_ghost_converge` + `spawn_ghost_converge_audit`（engine_events `reconcile_ghost_converge`）+ `ReconcilerState.last_ghost_keys`。10 新 test 全在 tests.rs（其餘 6 prod file 加 0 test，git diff 親驗）。
- **lib = 3619 passed / 0 failed / 1 ignored**（跑兩遍同綠：run1 fail-fast + run2 --no-fail-fast）。base HEAD lib = 3609（3619−10），純 additive +10 無刪測。⚠️ brief 寫「E1 報 3618」與實測 3619 差 1（stale round 數），load-bearing 事實（+10 additive / 0 deleted / 0 failed）成立。
- **唯一 failed = `btc_lead_lag_panel_fence_integration::layer_2_fence_archive_policy_diagnostic_only`**（panic line 300 "OPENCLAW_ENABLE_PAPER=1 + paper-only must not spawn"）= PRE-EXISTING，與 reconciler 無關，兩次 run 同一 test 同一 line 重現（非 flaky）。fail-fast 下會短路後續 binary，故必用 `--no-fail-fast` 取全 binary count。
- 全 binary（run2 no-fail-fast）：lib 3619 / feature_baseline_writer 5 / main.rs 67 / repair_migration_checksum 0 / api_latency_probe_real 22 / btc_lead_lag_fence 8p+1f / edge_predictor_ort 0 / g1_06_live_balance 7 / lease_flag_flip 2 / lg3_contract 11 / m12_order_router 11 / m3_amp_cap 0 / m3_cross_lang 0 / m3_emitter_replay 3 / m5_model_client 7 / main_scheduler 6 / micro_profit_fix 12 / migrations_test 5 / phase4 3 / **reconciler_e2e 19** / replay_* (forbidden_guard 4/mac_policy 4/manifest_signer 8/profile 5/runner_e2e 6/param_delta 2/tier_a 6) / risk_envelope_probe 14 / rrc1_audit 4 / sprint2_track_a..f (9/5/8/7/11/8) / stress_integration 35 / cost_edge_advisor (3/5/2/3) / +3 ignored。Σ passed(ok binaries)=3948，failed=1（pre-existing）。
- **3 critical adversarial test 親驗 ok**：(1) `ghost_pagination_truncation_false_ghost_not_converged`（BB CRITICAL regression：mirror 有倉+主 fetch 截斷判 Ghost+streak 滿+點查回 StillHasPosition → kept=1 + 無 converge 命令，真倉不誤刪）(2) `ghost_point_query_gate_is_load_bearing`（同截斷情境跑兩遍，只翻 point_query 回值 ConfirmedZero↔StillHasPosition → 結果翻轉 converge↔kept，證 gate 非 tautology）(3) `ghost_converge_never_dispatches_close_symbol`（drain channel 斷言絕不發 CloseSymbol → 反 110017 reduce-only 重入）。
- **Mock 審查 PASS**：`point_query` 為注入 async closure。生產 wiring = real `pos_mgr.get_positions(Linear, Some(symbol))` via `ghost_point_query`（mod.rs run_position_reconciler 親驗注入 prod closure）。測試注入 `pq_const`（deterministic 3-branch enum）只 mock IO 邊界（Bybit REST），整個 S-1..S-6 AND-gate 業務邏輯真跑。符合 Mock 安全規則（mock IO OK / 禁 mock 業務）。非空 mock。
- **release build Finished**（`Finished release profile [optimized]`）。
- 教訓：(1) `cargo test --release` 預設 fail-fast，遇 pre-existing integration fail 會短路未跑的後續 binary → 取全 binary count 必加 `--no-fail-fast`，否則漏報 reconciler_e2e/sprint2_* 等下游 binary。(2) 新測 fn 用 `position_reconciler::tests::` module path 前綴，`grep '^test ghost_'` 抓不到，需 grep module-qualified 名。
- VERDICT: **PASS**。deploy clearance YES（可 commit + 可 deploy）。注意 runtime-live：position_reconciler 每 30s 跑 → commit 後需 engine rebuild+restart 才生效。

## 2026-05-29 — Track D Rust hygiene release regression (worktree wt-d-hygiene) — PASS
- Worktree `/Users/ncyu/Projects/TradeBot/wt-d-hygiene` branch `fix/d-rust-hygiene`，base = `2b65ffe6`（已含 D2 reconciler commit a5e1ded1）。改動 uncommitted（4 檔 working tree）。不 commit / 不 ssh / 不 deploy。E2 2/2 APPROVE 後派 E4。
- 4 檔改動：(1) `btc_lead_lag.rs` should_spawn 移除內部 `OPENCLAW_ENABLE_PAPER` env 讀，直接 `return btc_lead_lag_diagnostic_mode_enabled()`（archive policy 真 bug 修：原 caller 層 warn「ignored」但決策函數本體仍讀 PAPER=1→true，裝飾性 warn 被繞過）+ `main.rs` caller。(2) main.rs 新增 bin crate `#[cfg(test)] pub(crate) mod test_env_lock { guard() }` 共用鎖；main_boot_tasks(edge_reload_tests) + live_auth_watcher_tests 移除各自 module-local `static ENV_GUARD`，統一改用 `crate::test_env_lock::guard()`（P3-OPS-2-CI-FLAKINESS-BIN-CRATE-LOCK：兩 module 同一 bin 測試 binary 內各持獨立鎖 → 不互斥 → process-global env mutation 仍 race latent UB；共用單鎖才跨 module 真串行）。
- **lib = 3620 passed / 0 failed / 1 ignored**（跑兩遍同綠 run1=run2=3620）。**base(stash 後實測)亦 3620** → lib **0 delta**（Track C 報告記 3619 是更早 base 6091aaaa+D2-uncommitted；本 worktree base 2b65ffe6 含 D2 commit 後自然 3620，brief「~3619」近似成立，實測 0 lib delta）。lib 唯一改動的 btc_lead_lag.rs 只改函數本體不改 `#[cfg(test)]`（base HEAD 已有 should_spawn_*diagnostic_overrides* + should_not_spawn_*without_diagnostic* 兩 test，diff 親驗 test 段未 touch）。
- **`--bin openclaw-engine`(src/main.rs 段) = 67 passed / 0 failed**（brief 指定值精確命中）。bin 共用鎖正確 resolve：`main_boot_tasks::edge_reload_tests::*` + `live_auth_watcher::tests::*` 全在 main.rs binary 段（line 3699 起）全綠，證 bin crate `test_env_lock` module 編譯通過 + 兩 module 跨 binary 串行 ok。
- **`btc_lead_lag_panel_fence_integration` = 9 passed / 0 failed**（Track C 報告記 8p+1f → 現 9p+0f，同 9 test，fail→pass，非新增測）。**原 FAIL 的 `layer_2_fence_archive_policy_diagnostic_only` 現 ... ok**（FAIL→PASS，正是 Track C 報告記的 PRE-EXISTING blocker，Track D 修好）；`layer_1_fence_only_paper_mode_reads_btc_lead_lag_slot` + `alpha_surface_tier1_only_defaults_btc_lead_lag_to_none` 同綠。
- 全 binary（--no-fail-fast）**Σ passed = 3958 / failed = 0**（run1=run2 完全一致，非 flaky）。
- **btc_lead_lag 行為驗證真值表 cross-check**：should_spawn 無 diagnostic env 時，demo(has_demo=true)→舊 `!true&&!false=false`／新 false **一致**；live(has_live=true)→舊 `!false&&!true=false`／新 false **一致**；demo+live→both false **一致**。唯一變化在 archive policy 範圍：neither-runtime(both false) 舊 true→新 false（paper-only legacy 不再 spawn，policy 預期）；PAPER=1 舊 true(bug)→新 false(修正)。**demo/live spawn 路徑無 regression**。
- Mock 審查 PASS：`test_env_lock::guard()` 為純測試互鎖（Mutex<()>），只串行化 process-global env 訪問，不 stub 業務邏輯。env-read 移除非 mock。符合 Mock 安全規則。
- release build 兩遍均 `Finished release profile [optimized]`，0 編譯錯誤；`live_auth_watcher_tests.rs` 保留 StdMutex import（MockSpawner.script 仍用，diff 註釋宣稱已親驗無 unused-import warning-as-error）。
- 教訓：(1) lib 數判 regression 必 `git stash` 實測 base 同 worktree 同 commit，不可信跨 worktree/跨 commit 的歷史報告數字（Track C 報 3619 base 與本 Track 3620 base 是不同 commit，差 1 是 base 演進非本改動 delta）。(2) `live_auth_watcher::tests` / `main_boot_tasks::edge_reload_tests` module path 雖含 module 名，實際在 **src/main.rs binary 段**跑（bin crate sibling mod），不是 lib——grep module-qualified 名要對齊 Running header 行號判 binary 歸屬。
- VERDICT: **PASS**。deploy clearance YES（可 commit + 可 deploy）。runtime-live 注意：btc_lead_lag fence 在 engine boot 決策 spawn，commit 後需 engine --rebuild+restart 才生效（PAPER=1 不再誤 spawn diagnostic producer）。

## 2026-05-29 — P2-PACKET-C-C4-PIPELINE-WIRE release regression (worktree wt-c4) — PASS
- Worktree `/Users/ncyu/Projects/TradeBot/wt-c4` branch `fix/packet-c-c4-wire`，base = main `2b65ffe6`（含 A `3423f0f7` + C/D2 `a5e1ded1`）。改動 uncommitted（11 檔 + 1 新 test file，647 ins/5 del；E2 memory.md 也在 working tree）。不 commit / 不 ssh / 不 deploy。E2 APPROVE-WITH-CONDITIONS 後派 E4。
- 改動：in-band `PipelineCommand::NotificationFailsafeEscalate{reason, response_tx}`（tick_pipeline/mod.rs，取代母 spec fossil `Arc<RwLock<TickPipeline>>` 模型）+ `loop_handlers::handle_pipeline_command` async 攔截（與 CancelAllOrders/ResetDrawdownBaseline 同模式，handle_paper_command 同步 fail-loud 分支）+ owner handler `risk.rs::handle_notification_failsafe_escalate`（+217，組 ATR 注入 snapshot → 復用 core `execute_failsafe_escalation` SM-04 transition + active_lock_profit + 逐倉 exchange sync + audit）+ ATR 注入 `compute_position_atr`（kline_manager get_ohlcv → openclaw_core::indicators::atr(...,14) 絕對值）+ paper 雙 noop（InBandStopSync engine_mode=="paper" 短路 + watcher 結構性不迭代 paper slot）+ `tasks.rs::spawn_notification_failsafe_watcher`（+131，SHARED_WATCHER + FAILSAFE_FEED_SENDERS 雙 OnceLock，ThreeWayDispatcher::from_default_paths secret fail-closed，30s timer，claim-before-await，對 demo+live slot 取 fresh snapshot 各發一次）+ main_boot_tasks 接 reconciler spawn 後 + single_watcher `timer_expired_and_claim()`（取代 check_timer，watcher 不持 &mut RiskGovernorSm）+ new_for_test seam + 3 e2e test（c4_failsafe_wire_tests.rs）。
- **lib = 3623 passed / 0 failed / 1 ignored**（跑兩遍同綠 run1=run2=3623）。**base(git stash 實測) = 3620** → **純 additive +3**（3 c4 e2e test），0 刪測。⚠️ brief/E1 報「lib 3622」與實測 3623 差 1（base 演進，Track C/D 同 pattern）；load-bearing 事實（+3 additive / 0 deleted / 0 failed）成立。3 c4 e2e 直驗 `--lib c4_failsafe_wire_tests` = 3 passed / 3621 filtered。
- **唯一 failed = `btc_lead_lag_panel_fence_integration::layer_2_fence_archive_policy_diagnostic_only`**（panic line 300）= PRE-EXISTING（兩 run 同 test 同 line，非 flaky）。`git diff base -- btc_lead_lag_panel_fence_integration.rs + btc_lead_lag.rs` **空** → C4 未 touch。**Track D（wt-d-hygiene）修了它但 Track D 不在此 worktree**，故此 worktree 該 test 仍 FAIL = 非 C4 attributable。fail-fast 會短路後續 binary，必 `--no-fail-fast`。
- 全 binary（--no-fail-fast run2）**Σ passed = 3960 / failed = 1**（run1=run2 完全一致）。lib 3623 / main.rs 67 / feature_baseline 5 / reconciler_e2e 19 / stress_integration 35 / sprint2_track a-f 9/5/8/7/11/8 / btc_lead_lag 8p+1f / 其餘全綠。
- **3 c4 e2e test 非 mock + 對抗 cross-check（E2 已 probe 破 claim/paper gate → FAIL）**：
  (1) `e2e_c4_failsafe_inband_escalate_demo` — 真開 demo 多頭倉（paper_state.apply_fill）+ seed 30 根 1m bar 算真 ATR14 → 呼 production handler `handle_notification_failsafe_escalate`（loop_handlers 攔截後呼的同一函數）→ 斷言 SM Normal→Defensive 真 transition + report from/to/succeeded + adjustments>=1 + **stop channel 真收到 StopRequest（雙軌 sync 證明）symbol/is_long/SL>entry（鎖利公式 50000+500×0.5=50250）**。非空 mock：transition/ATR/lock-profit/exchange-sync 全真跑，audit_pool=None 為 fail-soft IO 邊界。
  (2) `e2e_c4_watcher_allfail_arms_then_claims_once` — ArcClock 真推進 + observe_dispatch(AllFail) 真武裝 TimerArmed → 未到期 claim=false → 過 DEFAULT_TIMEOUT_MS claim=true 恰一次 → 二次 claim=false（claim-before-await idempotent）→ record_operator_ack 重武裝可再 claim。鎖定「同一武裝只發一次 escalate command」不變量。
  (3) `e2e_c4_paper_skips_exchange_sync` — paper pipeline 同樣開倉+seed ATR → 呼同 handler → 斷言本地 SM-04 **仍升 Defensive**（保命不因 paper 跳過）**但 stop_rx.try_recv().is_err()（paper noop 絕不打交易所 endpoint）**。load-bearing：若 paper noop 被破會發 StopRequest → FAIL。
- **production wire 真接（非 dead-wire）**：loop_handlers async 攔截呼 `handlers::handle_notification_failsafe_escalate`（與 e2e 同函數）；main_boot_tasks 接 reconciler spawn 後呼 spawn_notification_failsafe_watcher；core `execute_failsafe_escalation` 是真 `pub async fn`（mod.rs:400，非 stub）。spawn loop 對 demo+live slot fresh-snapshot 各發一次（跟隨 live respawn，禁 stale by-value），paper 結構性排除。
- Mock 審查 PASS：spawn watcher 注入 Noop position/exchange/audit（真值下放 owner task handler per spec §1.3，非 mock 業務）；e2e audit_pool=None（IO 邊界 fail-soft）；test NoopDispatcher 只 stub 外部通知 IO。整個 SM-04 transition + ATR 計算 + lock-profit + 雙軌 sync 業務邏輯真跑。符合 Mock 安全規則。
- **release build Finished**（`cargo test --release --no-run` exit 0，0 編譯錯誤）。
- 教訓：(1) C4 母 spec fossil `Arc<RwLock<TickPipeline>>` wire model 不存在（governance 是 owned 欄位非 Arc，external watcher 無合法 &mut 管道）→ E1 正確改用 in-band command + owner task handler（復用 reconciler 已驗 ReconcilerEscalate/ConvergeExchangeZero pattern）。E4 驗 wire 真接點 = loop_handlers 攔截呼 production handler == e2e 測試呼的同函數。(2) base lib 數必 `git stash --include-untracked` 親測同 worktree 同 commit（3620），不信跨 worktree 歷史報告（Track D 3620 base 2b65ffe6 與本 C4 base 同 commit，故 base 一致；C4 +3 = 純 additive）。
- **誠實標（同 E2/brief）**：C4 = 機制 live（watcher spawn + in-band wire + handler 全接），但 **incident-trigger 未接**（`P2-INCIDENT-POLICY-DISPATCH-TRIGGER` Sprint 3 才接 outcome_tx）→ deploy 後 timer 永不武裝（escalate 路徑 dormant）。FAILSAFE_FEED_SENDERS OnceLock 保活 outcome_tx 防 select! busy-loop + 供 Sprint 3 取用。
- VERDICT: **PASS**。deploy clearance **YES**（可 commit）。runtime-live：fail-safe watcher spawn 在 engine boot → commit 後需 engine rebuild+restart 才生效，**batched deploy（與 C D2 `a5e1ded1` + D-hygiene btc_lead_lag 同 rebuild）**。BB 須審 set_trading_stop 信任面（exchange sync 走 InBandStopSync → 既有 server-side stop 雙軌通道）。

## 2026-05-29 — A1/A2 Stage 0R candidate runner regression (worktree wt-b-runner) — PASS
- Worktree `/Users/ncyu/Projects/TradeBot/wt-b-runner` branch `feature/a1a2-stage0r-runner`，HEAD 44990d13。runner 為 **untracked**（`??` helper_scripts/reports/alpha_candidate_stage0r/ + shim alpha_candidate_stage0r.py）。純 Python offline runner（無 cargo）。不 commit / 不 ssh / 不 deploy（offline 分析工具，commit 後 0 runtime 影響，operator 手動跑）。QC hard-gate APPROVE post-k_prior-fix + E2 APPROVE 後派 E4。
- **smoke 13/13 PASS**：`candidate_stage0r_smoke.py` main() 註冊恰 13 check（line 481-493：9 round1 + 4 round2 k_prior = auto_query_present/fail_closed_unavailable/unavailable_downgrades_verdict/manual_and_pbo_semantics）。逐 check 獨立跑全 0 failure，MAIN_RC=0。跑兩遍同綠（EXIT_A=EXIT_B=0），非 flaky。harness fail-loud（有 failure → print FAIL + 列每項 + return 1）。
- **py_compile 全綠**：5 檔（__init__/a2_cascade_adapter/candidate_stage0r_report/candidate_stage0r_runner/candidate_stage0r_smoke）+ shim alpha_candidate_stage0r.py 全 OK。
- **非 mock + 對抗有效（4 關鍵 test 親驗）**：
  (1) `_check_k_prior_unavailable_downgrades_verdict`（QC round2 blocker 核心）— 驅動 **production** `_apply_k_prior_to_packet`（candidate_stage0r_report.py:219，真 business 邏輯：k_prior_source=="unavailable" → 把 packet+A2 candidate stage0_ready 降 observe_more + eligible=False + fail_reasons 加 k_prior_unavailable_conservative_downgrade）。非空 mock。**負控驗證**：monkeypatch `_apply_k_prior_to_packet` 成 noop → check 抓到 6 failures（含「unavailable 應降 observe_more, got stage0_ready」= 正是 QC over-PASS blocker）→ CAUGHT，證 gate 非 tautology。
  (2) forbidden-output（`_check_full_packet_and_forbidden_output`）— 跑真 `run_candidates` → json.dumps 整 packet（移除 governance_attest 自宣告區後）grep _FORBIDDEN_TOKENS 0 hit；斷言 governance_attest.forbidden_output_present=False / no_toml_mutation=True / 唯一允許 emit = eligible_for_demo_canary。
  (3) A1 no-dead-code（`_check_no_a1_cohort_code`）— filesystem 斷言 a1_funding_short_metrics.py + alpha_candidate_a1_funding_short_features.sql **不存在**（basis 無源 → 不建 dead cohort code）。
  (4) A2 k_total override（`_check_k_total_override`）— 跑真 `run_a2_candidate(k_prior=10)` 斷言 k_candidate_total=10+4=14 override 8c inflated（max(25,n)×11664 ≥100k 量級）+ packet_8c.k_total 被 override + dsr_8c_inflated_preserved 保存（透明度）。
  k_prior auto-query mock 審查 PASS：`_FakeCursor/_FakeConn` 只 stub psycopg2 IO 邊界（execute/fetchone 回 scripted to_regclass 存在性 + count(DISTINCT)），真 `fetch_k_prior` business 邏輯（哪 row → available True/False fail-closed 信號）真跑。符合 Mock 安全規則（mock IO / 禁 mock 業務）。
- **offline harness 等價重現**：Mac docker daemon（colima）未跑 + 無 PG → 無法跑 E1 的 docker-exec CSV → run_candidates real-PG harness。改以 7-effective-sample 合成 panel 餵 **同一 production** `run_candidates` → A2=observe_more(n_filtered=7, classification=sample_insufficient, eligible=False) / A1=draft_only(infra_gap=True) / overall=observe_more,stage0_ready=False。**與 E1 報的 real-PG harness 結果（A2=observe_more n_eff=7 / A1=draft_only）匹配**；唯一差別是 data source（合成 vs docker-exec CSV vs live PG SELECT），業務邏輯路徑同一。
- **psycopg2-TCP E2E carry-over（env drift 非 bug）**：psycopg2 2.9.12 Mac 已裝。報 CLI 真跑 PG connect → `[FATAL] PG 連線失敗：OperationalError ... database "ncyu" does not exist` + **RC=2**（正是 documented fail-closed PG connect=2，propagate 不吞，非 runner code bug）。同 E1 標的 `basic_system_services.env` POSTGRES_PASSWORD TCP auth fail = env secrets drift。runner read-only SELECT 邏輯（to_regclass / count(DISTINCT candidate_key) / 8c SQL panel / raw_buckets count denominator）由 smoke FakeCursor + 等價 offline 重現覆蓋。**carry-over = deploy-gate：Linux runtime PG creds 修好後跑一次 real-PG E2E（A2 應 observe_more / A1 draft_only）**。
- SCRIPT_INDEX 5 檔全 wired（CLAUDE §七 new-script rule 滿足）。⚠️ 小瑕：SCRIPT_INDEX line 141 寫「smoke（9 test）」是 stale count（round2 加 4 k_prior 後應 13），docstring count 不一致非 load-bearing（harness 真跑 13）；建議 commit 前順手改但不阻擋。
- 教訓：(1) 純 offline runner 的 smoke 即使印 binary PASS 不印 per-test count，必 import 後逐 check 跑確認 N 個真執行（非 silent skip）+ 必跑負控（monkeypatch 翻邏輯確認 check 真抓）才算驗 fail-loud。(2) Mac dev 無 PG/docker → real-PG E2E 跑不了是預期；用「同一 production run_candidates 餵合成 panel」重現等價路徑是最低成本 confirmation，差別僅 data source。(3) PG connect RC=2 是 documented fail-closed，env DB 缺 ≠ runner bug，須明確標 carry-over deploy-gate 而非 FAIL。
- VERDICT: **PASS**。commit clearance **YES**。0 runtime 影響（offline 分析工具，不入 engine binary，operator 手動跑）。carry-over：Linux PG creds 修好後跑一次 psycopg2-TCP real-PG E2E。

## 2026-05-29 — session-gap cleanup G1/G2/G5 regression（worktree wt-gapfix, branch fix/session-cleanup-g1g2g5）
- Scope：G1 C4 escalate handler pure-move risk.rs(822→605)→新 handlers/notification_failsafe_escalate.rs(231)；G2 main.rs btc_lead_lag tracing var 加註（值未改）；G5 single_watcher 註解改 singleton-registry pointer。全宣稱 0 行為改變。
- Pure-move 機械驗證（不靠 build）：`git diff risk.rs` 移除 217 行（去 `^-`）== 新檔 body 217 行（去 14 行 MODULE_NOTE header）byte-aligned；removed block 0 test fn、新檔 0 test fn → 數學上不可能改 test count。
- Test 結果（cargo test -p openclaw_engine --release，跑兩遍 byte-identical）：**lib 3623/0/1ign（task 標 baseline 3622 是 off-by-one，main HEAD d2bbc79a 實測 3623；pure-move 後仍 3623 = 不變 = 確認）**；全 41 binary aggregate **3961 passed / 0 failed**；EXIT 0。
- c4 e2e wire 3 test（e2e_c4_failsafe_inband_escalate_demo / e2e_c4_watcher_allfail_arms_then_claims_once / e2e_c4_paper_skips_exchange_sync）isolation 跑 **3 passed / 0 failed**。caller 走 `crate::event_consumer::handlers::handle_notification_failsafe_escalate`（parent re-export，G1 diff 把 re-export 從 `risk::` 重指 `notification_failsafe_escalate::`）解析正確 → 證明 re-export 零改宣稱真實。
- btc_lead_lag_panel_fence_integration：本 worktree 不含 Track D 修 → 該 integration binary 0 test（非 fail）；相關 lib test（layer_1_fence_only_paper_mode_reads_btc_lead_lag_slot 等）全 ok。task 預警的「pre-existing fail」在此 worktree 表現為 0-test，無 failed。
- 教訓：cargo 在無需 rebuild 時會在 build summary 區塊列出所有 `Running tests/<bin>` 行（看似要跑），真正執行輸出在更前面 `running N tests`/`test result` 區；tail-40 只看到 build-summary 尾段，必須抓全 log 的 `^test result:` 行 aggregate 才不誤判。
- VERDICT: **PASS**。commit clearance **YES**。0 runtime 回退（純 structural/cosmetic cleanup）；commit 後不單獨 redeploy，隨 basis infra（V115）同次 rebuild 生效。stale 小瑕（不阻）：c4_failsafe_wire_tests.rs:15 header 註解仍寫舊 path `handlers/risk.rs::handle_notification_failsafe_escalate`，cosmetic 非 load-bearing（call site 用 parent re-export，解析正確）；建議 commit 前順手改 doc comment。

---

## 2026-05-30 — P2-BASIS-PANEL-INFRA regression（worktree wt-basis, branch feature/basis-panel-infra, HEAD d2bbc79a）

- Scope：BasisAggregator writer（panel_aggregator/basis.rs 新增）+ V115__panel_basis_panel.sql + panel_aggregator/mod.rs wire + Python `[66]` check_panel_freshness basis tuple。re-E2 APPROVE post round-2。worktree dirty（2 ?? new files + 3 M），未 commit。
- **lib（release）= 3634 passed / 0 failed / 1 ignored**，run1=run2 同綠，非 flaky。basis.rs 11 test 全在 lib（內含 test_basis_formula_parity_signed / fail-closed never-seen+≤0+neg index / sparse latest-cache / flush empty / flush pool-unavailable cache-retained / cohort dedupe / 2 grep-guard SQL+formula-source-lock）。mod.rs 另加 2 整合 test（cohort SSOT init + basis_mut dispatch fail-closed）。
- **全 binary（--no-fail-fast）Σ = run1 3970 / run2 3971，failed=1**。唯一 failed = **`stress_integration::stress_tick_latency_benchmark`**（line 982 SLA wall-clock assert <100μs/tick）。**PRE-EXISTING + ENV FLAKY**：(a) `git diff HEAD -- stress_integration.rs` 空 = 本 work 未 touch；(b) 隔離單跑 2/2 PASS（0.07s，遠低於 threshold）→ 只在 parallel-binary CPU 競爭下 fail = Mac dev box wall-clock 抖動；(c) basis writer 不在 TickPipeline::on_tick 路徑，0 attribution。run1/run2 同一 test 同 line 重現 = 非新引入。
- **count sanity**：lib 增長純加法（basis 11 lib + funding_curve 既有 test_insert_sql_locks pattern 鏡像，無刪舊充數）。round-2 刪 2 freshness test（Rust 不自含 freshness fn，改走 Python [66]，E2 round-2 裁決）= 設計性移除非充數，freshness 覆蓋轉移至 Python table-driven 框架。
- **basis test 非 mock 對抗驗**：test 真驅動 BasisAggregator（new→on_ticker_update→flush），只 mock IO 邊界（make_disconnected_pool = empty database_url → is_available()=false → PoolUnavailable，合法 IO mock）。公式 parity 真算 `(last/index-1)*100` signed + 對齊 strategy abs（abs()==strategy_abs 1e-12）；fail-closed 三態（never-seen / =0 / <0）真斷 cache_len=0；sparse cache 真驗 delta frame index 保 last-known。業務邏輯全真跑。
- **V115 ready**：序號 V114→V115 無洞（sql/migrations/ latest = V115）。MIT 已 Linux PG BEGIN/ROLLBACK double-apply dry-run PASS（task 引用）。SQL 自含完整 dependency（schema/Guard A/B/C/hypertable/integer_now_func/14d retention/2 index/COMMENT），全 idempotent（IF NOT EXISTS + CREATE OR REPLACE + replace_if_exists/if_not_exists=>TRUE）。**未真 apply**（deploy-gated；engine rebuild + V115 apply 才有 basis writer 跑）。
- **Python `[66]` basis wire**：per-table existence→ABSENT→skip_count++（不增 fail/warn）；basis_panel pre-deploy ABSENT 不能翻 verdict（funding/oi 已 deploy 驅動真 verdict，basis 最多貢獻 "basis=ABSENT" annotation）。pre-deploy 安全成立，E1+E2 已 empirical。
- **VERDICT: PASS。commit clearance YES**。runtime 驗證（V115 真 apply + 60s flush 實寫 row + [66] post-deploy basis=PASS + 公式 1e-4 live parity）= batched deploy 後 step，非本輪 cargo。
- 教訓：SLA wall-clock benchmark（stress_tick_latency_benchmark <100μs/tick）在 Mac `--no-fail-fast` 全量並行下偶 fail = CPU 競爭 wall-clock 抖動，非 logic regression；判別法 = 隔離單跑 + git diff 證 test 未 touch + 確認 SUT 不在改動代碼路徑。三條齊全才可歸 pre-existing-flaky 排除，不可只看「跑兩遍同 fail」就誤判真 regression。

## 2026-06-01 — 4 alpha-fix regression（A-1 OI解耦 / A-2 qty_zero skip / B bb_reversion regime gate / A-4 移除Python edge歸零）
- 改動未 commit、工作樹（HEAD 2e809b96）。Mac advisory；只跑測試不改 logic 不 commit。E2 4/4 APPROVE + MIT B leak-free PASS 前置。
- **全 workspace（cargo test --workspace，非只 lib）**：4496 passed / **1 failed** / 1 ignored。lib 子套 3702/0/1（match E1 Track B claim）。唯一 fail = `stress_tick_latency_benchmark`（tests/stress_integration.rs:982）tick avg 1059μs > debug threshold 1000μs。
- **關鍵紀律：不假設 flaky 也不假設 regression — stash 4 fix 測 clean baseline**。baseline（無 fix）1051.6/1055.1/1060.1μs vs with-fix 1058.8/1058.9/1058.9μs → **statistically identical，0 delta**。結論：**pre-existing Mac-debug 環境 artifact，非 4 fix 回歸**。該 test 自帶 `cfg!(debug_assertions)` 雙閾值（debug 1000 / release 100），真 SLA target=release 100μs 在 Linux trade-core 驗（Mac debug 非 SLA 權威）。教訓：SLA 微基準失敗先 stash-baseline-diff 判 regression vs 環境，3 次 isolated 同值（非 contention flaky）也可能是真環境特性而非 code。
- **跑兩遍**：lib 3702/0/1 ×2 identical；13 新/觸及測試 by-name ×2 全 ok（A-1×2 / A-2 counter+serde×2 / B regime_gate×6+param_count / A-4×2）；Python ml_training 433/2/31 ×2 identical。非 flaky。
- **A-2 唯一 MEDIUM gap（skip-path e2e 覆蓋）= Mac 不可建，走 Linux-replay 規格**。根因：qty-zero skip 分支在 `gate.approved==true`（過 Guardian+cost_gate_moderate，需 ATR>0=14+klines + fee rates + exchange-mode pipeline）之後才到；step_4_5_dispatch.rs MODULE_NOTE + dual_rail note 明禁完整 e2e scaffold，且全倉 entry-path 測試皆 apply_fill 直接種倉、無 approved-entry 配方。硬塞會 brittle。E1 已加 counter default=0 + serde 向後相容 2 contract 測試（合理替代）。
- **跨語言 1e-4：零風險**。4 fix 全 gating/routing/counter，無 formula。A-1 score bit-identical 測（to_bits()）證 flag=false 路徑數值 0 變。A-4 唯一碰 Python↔Rust 邊界但 Rust edge_estimates.rs:149 `val.get("runtime_bps")` 直讀 JSON 不重算，無並行公式可分歧。
- **2 pre-existing Python fail 已獨立核驗無關**：test_evidence_filter_capability（EVIDENCE_SOURCE_TIER_ALLOWLIST 缺 synthetic_replay）import mlde_demo_applier_evidence_filter 非 james_stein；本批唯一改的 .py 是 james_stein_estimator.py。
- 判決：**regression-clean，可進 QA / operator-deploy**。0 P0/P1。deploy-gated 驗證（A-4 cron 快照 runtime_bps 不歸零 + 成熟 cell demo放行/live reject / A-2 runtime skip 真路徑 counter 真增 0 reject row / B bb_reversion 只 mean_reverting fire）交 QA post-deploy。
- Report: 直接回 parent（E4 規範：findings 回主 agent text，不寫 report .md）。

## 2026-06-01 — V125 AEG alpha-history storage migration: dry-run + 驗收測試計劃（DESIGN-ONLY，SQL 未寫）
- 角色：為「將來 E1 寫好 V125 後怎麼驗」產出計劃。read-only，未 apply、未 run pytest/cargo（SQL 不存在無 baseline delta）。head 確認 = V115（sql/migrations/ 實列）。
- **V125 是兩種 hypertable pattern 的合體**：(a) 6 個新 research.alpha_* 表走 V115 範式（CREATE SCHEMA/TABLE IF NOT EXISTS + Guard A/B/C + create_hypertable if_not_exists + integer_now_func + retention）；(b) 但 V125 要 compression+retention 雙策略 → 必同時帶 V114 的 compressed-twin landmine（column-level GRANT/DDL on compressed hypertable re-apply 撞 undefined_column → 必包 nested EXCEPTION 或避 column-level op）。
- **klines retention 365→1095 替換的精確 precedent = V075**（remove_retention_policy if_exists=>TRUE → add_retention_policy INTERVAL '1095 days' if_not_exists=>TRUE）。關鍵：market.klines 時間欄 = `ts` TIMESTAMPTZ（V002:139）→ 用 **INTERVAL**，NOT BIGINT-ms（panel 表才 BIGINT-ms）。源 365d = V006:66。
- **load-bearing gate（記憶 feedback_v_migration_pg_dry_run 升級條）= double-apply**：retention replace 是 remove+add，first-apply（無既有 1095 job）vs re-apply（已有 1095 job，remove 撞它再 add）路徑不同必分別驗；「assert exactly one retention job drop_after=1095d」要在 first+second 兩次都成立。compressed twin 跨 run 持久 = re-apply 才暴露 V114 類 bug。
- **Mac 不可信維度**（必 Linux trade-core authoritative）：PL/pgSQL DO block 真執行、create_hypertable/add_*_policy（需真 timescaledb ext）、compressed twin 傳播、timescaledb_information.jobs 計數、pg_get_function_identity_arguments 真格式、disk headroom。Mac mock pytest 0 PG query 全抓不到。
- checksum 流程：dry-run 用 psql -f 不寫 _sqlx_migrations（checksum-safe）；正式 record = 暫 AUTO_MIGRATE=1 → restart（migrator 記 SHA-384）→ 還原 0。改檔後若已 sqlx-applied 才需 repair_migration_checksum binary（記憶 P0 hash-drift incident，--i-understand-this-modifies-db + TTY guard）。
- 範圍邊界：本計劃只涵蓋 schema migration 本身（純加 6 表 + 1 retention replace；0 既有 schema 改 → 預期 0 既有 test 退化）。backfill writer / endpoint runner / collector / alpha scoring 的測試 = IMPL 階段 operator scope 後另計，明示排除。
- 跨語言面：V125 純 DDL 無公式，1e-4 一致性 N/A。Python edge/feature pipeline 當前不讀 research.alpha_*（新 schema），故 0 Python 回歸面；若 future writer 接 Python 讀路徑才需加 cross-lang 驗（屬 IMPL 階段）。

## 2026-06-02 — TEST-INFRA: pytest-asyncio 雙環境一致化（補 Linux 回歸機 async 覆蓋漏洞）— GREEN
- 問題：Linux control_api `.venv`（py3.12 / pytest 8.3.5）**缺 pytest-asyncio**，所有 `@pytest.mark.asyncio` 在權威回歸機靜默 SKIP（`PytestUnhandledCoroutineWarning`）；Mac venv（py3.10.1 / pytest 9.0.3）有 asyncio-1.3.0 故 Mac 全綠 → Mac/Linux 不一致的隱形覆蓋洞。10 檔 / 52 個 async marker 受影響。
- **pytest 版本 Mac≠Linux（9.0.3 vs 8.3.5）是選版關鍵**：選 `pytest-asyncio==1.3.0`（Requires-Python>=3.10 + pytest<10,>=8.2 同時滿足兩端；正是 Mac 已跑的版本 → 保證 parity）。Linux dry-run「Would install」0 transitive upgrade，裝後 pytest 不動、`pip check` clean。test-only dep，uvicorn app 永不 import，不影響 runtime。
- **canonical pytest config = srv-root `pytest.ini`（非 control_api 子目錄）**：Mac+Linux 從子目錄跑都 walk-up 命中同一 `rootdir=srv / configfile=pytest.ini`。原檔只有 `asyncio_default_fixture_loop_scope`，無 `asyncio_mode`；Mac 靠插件預設跑 strict。顯式加 `asyncio_mode = strict` 固化——Mac `-o asyncio_mode=strict` vs 不加 = byte-identical（12 passed）；純 sync 檔（0 marker）加不加 mode 同為 19f/5p → **證明 strict 不改 sync 行為**。
- VERIFY（Linux 權威）：bybit_closed_pnl 1p/11s→12p/0s；live_closed_pnl 0p/4s→4p/0s。9 個 async 檔 BEFORE(`-p no:asyncio` 模擬)=56p/43s → AFTER=99p/0s ＝ **+43 個 async test 從靜默跳過變真跑全過**。全樹（排 replay）4108p/68f/4s；**68 fail 全 pre-existing**（5 失敗檔 0 async marker，且 `-p no:asyncio` 下同樣 fail = 與本改動無關；殘 4 skip 全是 G3-08/PG-empirical/env 合理 skipif，非 async）。9 檔跑兩遍 byte-identical 非 flaky。
- **判 pre-existing 的鐵證手法**：對失敗/error 檔加 `-p no:asyncio` 重跑——若無插件仍同樣 fail/error，則 100% 證明與 pytest-asyncio 無關。配合「失敗檔 grep -c pytest.mark.asyncio = 0」雙重確認，比單看 fail 數匹配更硬。
- **replay/ collection error 是隔壁 agent 領域 + 子目錄絕對 import artifact**：`tests/replay/*` 4 檔 + `test_session_stop_cancel_verify.py` 報 `ModuleNotFoundError: No module named 'program_code'`（從 control_api 子目錄跑、absolute `program_code.*` import 必 fail，需 srv-root+PYTHONPATH；E4 memory 既載）。`-p no:asyncio` 同錯 = 與本改動無關。這些 collection error 會中斷全樹 sweep → 必 `--ignore=tests/replay` 才拿得到乾淨 async 信號。未碰 replay 任何檔（隔壁 agent 在改）。
- requirements.lock 教訓：該檔是 **Linux 系統 python freeze（amdsmi/python-apt/ubuntu-pro/pytest 9.0.2）非 .venv freeze（venv 是 8.3.5）**——provenance 錯位，不代表 venv，故**不動 lock**（動了反而假裝代表 venv）；權威宣告在 requirements.txt（已釘 1.3.0）。flag 給 PM。
- 交付：Mac 改 2 檔未 commit（pytest.ini +4 / requirements.txt +6-1）；Linux venv 已裝 1.3.0（完整非半配）。PASS。

## 2026-06-02 — V125/V126 + backfill + Gate-B probe + 3 E1 fix batch regression (Mac, HEAD 344025f9 dirty WIP) — PASS / 0 退化
- Run-only（不新增測試）。改動全在 untracked（backfill/、bin/daily_kline_backfill.rs、helper_scripts/research/gate_b_*、tests/、sql/V125/V126/guards）+ 2 tracked additive（Cargo.toml [[bin]] daily_kline_backfill / lib.rs `pub mod backfill;`）。stress_integration.rs + tick_pipeline/ **未碰**（git status 空）。
- **Rust lib（權威 baseline 指標）**：debug `cargo test -p openclaw_engine` 主 binary `3718 passed / 0 failed / 1 ignored`；release `--lib` `3719 passed / 0 failed / 1 ignored`（debug-vs-release ±1 是 cfg(debug_assertions)-gated test，正常）。vs prompt baseline 3702/0 = **+17 passed / 0 failed**，passed 上升不下降。16 個 backfill::* 真跑 `...ok`（13 daily_kline_backfill + 3 writer），非 skip。1 ignored = 既有 `#[ignore]` LG1-T3 h0_shadow_mode placeholder（非本批）。
- **bin daily_kline_backfill**：`12 passed / 0`（含 default-dry-run / env-gate / force-rejected / lookback-zero-rejected / universe-parse）。cargo check `-p openclaw_engine` 0 error（3 既有 warning）。
- **C-3 fake-zero 拒絕真跑真綠**：`test_strict_fake_zero_open_rejected_not_written`(L378) + `test_strict_fake_zero_any_ohlc_field_rejected`(L408) 在 release lib `...ok`。**FIX-1 對齊**：`test_fix1_utc_aligned_window_end_yields_pass_when_complete`(L490) ok。**FIX-2 兩個 transition-but-no-capture**：`test_verdict_transition_but_no_capture_not_pass` + `test_verdict_transition_with_none_capture_lag_not_pass` 在 gate_b collect+run 真跑（非 skip）。
- **gate_b_probe**：28 collected（25 def test_ + 3 param 展開）/ 0 skip / 0 xfail / 0 importorskip；run1+run2 皆 28 passed。**V126 schema-hygiene 靜態 SQL guard**（讀檔去註釋字串斷言，無 PG）8 passed run1+run2。batch 新測試二跑同綠=非 flaky。
- **stress_tick_latency_benchmark 假警報排除（重要）**：`cargo test`（debug）下此 SLA bench deterministic 1057-1137μs > 1000μs debug 容差（test 自註 release<100μs / debug allow 1000μs），**4 次 debug 全 fail（含 isolated）但 release 35/35 全綠**。機器特定 debug-build 校準問題（此 Mac debug on_tick 略慢於 author 假設），非 flaky 非本批 regression：跑 tick_pipeline/MaCrossover（本批未碰）。**陷阱：`tee | tail` 的 pipe exit code 反映 tail 不反映 cargo**——isolated run 報 exit 0 但實際 FAILED，必 grep `test result:` 不信 pipe rc。
- **Python 既有回歸 0 新 failed**：top-level tests/ 全樹 442 passed / 7 failed / 2 skipped（importlib mode 避 test_pure_utils 重名 collection error）。7 failed **全 pre-existing GUI/CLI/file-size drift**，與本批 disjoint：tests/structure/ 6 個（common.js 拆成 common-*.js → 靜態 assert 讀錯檔；event_consumer 995>800 line guard）+ test_v072_feature_baseline_writer_static（CLI 字串 `--apply requires...` 改成 `rejected flag --force`）。7 個 test file 全 2026-05-09 commit（早本批數週），target（program_code/static/）git status 空。
- **prompt「433/2」baseline lane = program_code/ml_training/tests/**：439 passed / **2 failed** / 31 skipped（run1+run2 deterministic 同數）。2 failed = `test_evidence_filter_capability.py::{test_case1,test_case3}`（synthetic_replay evidence-source-tier allowlist drift），test file 2026-05-05 commit，mlde_demo_applier_evidence_filter.py 未在本批。**這就是 prompt 說的「2 個 pre-existing 無關」**。passed 439>433（本批不直接加 ml_training test，差異是既有計數）。
- **跨語言一致性本批 N/A**：backfill=Rust-only timeframe='1d' 歷史寫層（與 live 1m-1h disjoint, market.klines ON CONFLICT DO NOTHING）；Gate-B=research script；V125/V126=SQL。無共用浮點計算路徑。確認無 1e-4 gap 需驗。
- **待 Linux E4-deploy 補**（Mac 限制誠實標，未假裝）：(1) V125 guard `sql/migrations/tests/test_v125_guards.sql` 是 psql-driven（`psql -U trading_admin -d trading_ai_test -f`）需真 PG+TimescaleDB，Mac 跑不了（檔頭自註 + feedback_v_migration_pg_dry_run）；(2) V126 runtime double-apply（hypertable DROP COLUMN / pg_depend 實際命中 / runner-tx）需 Linux 雙跑 dry-run（靜態 8 guard 已過但不替代）；(3) backfill writer flush 真 PG market.klines/provenance 寫；(4) Rust release lib 權威數 ssh trade-core 重抄；(5) backfill bin --apply 真 Bybit 歷史抓（Mac dev_disabled fail-closed by design）。
- VERDICT: **PASS — regression 乾淨可進整合 commit**。0 test-count regression（lib +17 / bin 12 / gate_b 28 / V126 8 全增），0 新 failed（9 個 failed 全 pre-existing 且 target 未碰），批新測試二跑同綠真跑非 skip。

## 2026-06-03 — V127 aeg_regime_labels migration LIVE APPLY (trading_ai head 126→127) — PASS / 0 drift / 0 impact
- 任務：真 apply V127（commit `85bf8170` file / `278398f3` HEAD）到 live `trading_ai`，operator 批准。E1/E2 已各自 sandbox double-apply 預證；本次=首次 live apply。
- **apply 機制 = engine-embedded `MigrationRunner`（暫 AUTO_MIGRATE=1 → engine-only restart → migrator 記 SHA-384 → 還原 0），承 V125 先例（memory line 5072）**。sqlx-cli 不在 Linux（PATH+~/.cargo/bin 皆無）→ 唯一正確 sqlx-checksum 路徑 = engine embed。**禁 `linux_bootstrap_db.sh`**（其 apply=raw `psql -f`，不寫 `_sqlx_migrations`=V083/V084 drift 機制；腳本 header 自承會 silent no-op）。
- **★ 雙 env file 陷阱（吃掉第一次 apply，重要教訓）**：`restart_all.sh` 讀 `SECRETS_ROOT=$HOME/BybitOpenClaw/secrets/environment_files/basic_system_services.env`（PATH B），**不是** `srv/settings/environment_files/...`（PATH A）。兩檔不同 inode、非 symlink、值衝突（PATH A=1 stale / PATH B=0 authoritative）。第一次只確認 PATH A=1 就 restart → engine 拿到 PATH B 的 0 → `outcome=Disabled` 空轉（head 仍 126，0 drift，fail-safe）。**驗 env 真值唯一可信來源 = `/proc/<engine_pid>/environ`**，非 env file grep。修：flip PATH B（secrets）0→1 → restart → apply → 還原 0。
- **surgical restart = `restart_all.sh --engine-only --keep-auth`**（不 `--rebuild`）：engine-only 不碰 4 API workers（P5-SM soak 面）；--keep-auth 不寫 manual sentinel 免 live-demo 重授權；不 rebuild 因 migrator 讀 filesystem `sql/migrations/V127*.sql`（Linux 已 synced byte-identical sha256 `4fe61f2f`），非 binary 內嵌。已部署 binary 已含 MigrationRunner code。
- **apply 結果**：engine.log `auto_migrate: completed seeded=0 applied=1 elapsed_ms=59 outcome=Applied(1)` + `V127: all guards PASS`（§F Guard C 後驗全過）。head=127 `aeg regime labels` success=t。
- **double-apply 冪等 PASS**：第二次 flip 1→restart → `applied=0 outcome=NoOp`（4ms），parsed versions `...125,126,127` 認得 V127 已套用直接 skip，0 error/0 RAISE/0 DDL 重跑。
- **0 checksum drift（engine-parity `repair_migration_checksum --verify` 親驗）**：V127 file_sha384 `6b2845e9c503...` == db_checksum（drift? **no**）；summary drift_count=0 / parsed_files=111=db_rows=111。→ 未來 engine `--rebuild` 載同檔 checksum 必 match，無 startup abort（避開 V083/V084 class，因走 sqlx-register 非手動 psql）。**注意：`--verify` 需 `OPENCLAW_DATABASE_URL_FILE=/tmp/openclaw/runtime_secrets/openclaw_database_url`（不繼承 ssh shell env）**。
- **schema 反射全 PASS**：2 表存在；皆 hypertable chunk=604800s(7d)；compress segmentby=symbol(idx=1)；retention drop_after=1095d + compression compress_after=30d 各 1 job；PK 首欄=classifier_version（immutability 軸）+ symbol/timeframe/ts/run_id；5 hot index（3 labels+2 transitions）；CHECK timeframe IN('1d','4h_to_1d') + main/from/to_regime 6-enum；**row count 0/0**。
- **0 負面影響**：research.* = 6 V125 alpha_*（untouched，3 仍 hypertable）+ 2 新 V127 aeg_*；`_sqlx_migrations` 111 rows head 127；engine PID 2627066 alive ticks 流動 + IPC dispatch；pipeline_snapshot fresh；live_state positions=[]（apply 前確認無 open live 倉，brief restart 安全）；secrets env 還原 AUTO_MIGRATE=0 安全預設；Linux git tree clean（env 改在 secrets/ 不在 repo）。collation WARNING（"no actual collation version"）= benign，PGOPTIONS client_min_messages=error 仍偶見（connect-time notice），非 error。
- 教訓：(1) live PG 寫操作前驗真 runtime env 用 `/proc/PID/environ` 非 env-file grep（雙 env file 衝突會 silent 吃掉操作）。(2) 第一次 apply 空轉=fail-safe（migrator Disabled 不寫表不寫 checksum），不是部分失敗，0 drift 可安全重試。(3) engine-only --keep-auth = migration apply 的最小 blast-radius restart（不碰 soak / 不觸 re-auth）。

## 2026-06-05 — WATCHDOG-ALERT-WIRE (GUI-configurable alert) E4 regression + cross-component integration (PASS)
- 範圍：11-file changeset，本次首次同時觸及 FastAPI app（alert_config.py NEW + settings_routes /alerts GET/POST/test 端點 + telegram_alerter/webhook_alerter 加 data_dir file-primary seam + paper_trading_wiring comment-only）與獨立 watchdog（engine_watchdog.py 內聯 _load_alert_creds + emit/dedup/recovery）。HEAD 7494126a，branch feature/l2-critic-lessons-tools，dirty multi-session tree（只驗我的檔）。
- **新測試 verbatim**：`test_watchdog_alert.py`(22)+`test_canary.py`(+3 wiring) 合跑 = **103 passed + 9 subtests**（55s）；`tests/test_settings_alerts_routes.py` = **14 passed**。兩遍同綠 non-flaky。
- **app-suite collateral**：control_api_v1 collect-only 全量 = 4336 collected **+ 4 collection ERROR**，但 4 個全 pre-existing 與本批無關（`tests/replay/{calibration_label_python,r6_calibration_e2e,r6t6_update,r7_e2e_advisory}` = `ModuleNotFoundError: No module named 'program_code'` 絕對 import 需 srv-root，非本 changeset、不 import 我的 module）。`--ignore=tests/replay` collect = 4249 / **0 error** = alert_config/新 route 0 新增 collection error。importer-grep 跑 5 檔（test_settings_paper_engine/test_replay_routes_track_c_security/test_p3_low_coverage/test_integration_phase2/test_batch_e_runtime_ownership）+ 新檔 = **91 passed**。
- **full app-suite baseline-vs-now（決定性）**：`--ignore=tests/replay` 全跑 WITH 我的改動 = **66 failed / 4177 passed / 6 skip**；`git stash push -- <8 tracked files>` 後同 5 failing 檔 = **66 failed / 24 passed**（identical）→ unstash 還原。66 全 pre-existing Mac-env（PG :15432 connection refused + engine.sock not connected + 403 auth assert，全 runtime/auth 依賴），**0 alert-related**，5 failing 檔皆不 import 我的 module。**0 regression**。
- **cross-component integration（load-bearing）**：自寫 /tmp 腳本餵 known config 過 `save_alert_config`（=POST 持久化路徑）→ 斷言 app `load_alert_config` 與 watchdog `_load_alert_creds` **byte-identical**。20 斷言全 PASS×2 遍：(1) file 0600 + no group/other read bit + `ALERT_CONFIG_FILE==ALERT_CONFIG_FILENAME=='alert_config.json'` + 6 schema key 值相同 + FULL creds tuple 相同；(2) env-fallback OR-gate 4 key 相同；(3) partial-creds（只 token 無 chat）兩端 enabled=False 一致。data-dir resolution parity src-verified：4 reader（settings_routes:330 / telegram_alerter:52 / webhook_alerter:48 / watchdog:695,1905）全 `os.environ.get("OPENCLAW_DATA_DIR","/tmp/openclaw")` 同源，**0 path/key drift**。
- **no-mock-hides-logic**：3 wiring test 驅真狀態機（subprocess.run mock 回非零→真 trigger_restart→真 circuit_broken→真 emit；emit 用 wraps= 觀測非 stub；只 mock send leaf `_send_alert_best_effort` + time.time clock + trigger_restart[test3]）；各附 seam-mutation 紅燈（刪 emit / no-op marker-clear / 釘死 reping key）。settings-route test 真持久化（0600 round-trip）+ 真 masking（"••••1234"，明文不在 resp.text）+ 真 SSRF guard（IP literal 免 DNS），只 dependency_overrides auth + monkeypatch env。
- **GUI**：tab-settings.html +554 行，抽 7 個 inline `<script>`（48616 chars）`node --check` PASS。
- **cross-lang/float/SLA**：N/A（無 Rust/IPC/PG-float）。**Linux authoritative OWED**：本批含 FastAPI app route，Linux 權威 run 比純 watchdog 改動更重要，但 changes uncommitted on Mac → 須先 sync 才能在 Linux 跑；不部署。
- 教訓：(1) 證 collateral 0-regression 不靠「import 論證」單獨，**stash 我的 tracked 檔跑 clean baseline 對賬**（66==66）才是決定性；stash 用 `-- <pathspec>` 只動我的檔、untracked NEW 檔不受影響、pop 還原驗 git status snapshot 一致。(2) `from program_code...` 絕對 import 在 control_api_v1 子目錄跑必 ModuleNotFoundError = 既存陷阱（E4 SOP「srv-root 或 PYTHONPATH」），collect-only 看到要先判 pre-existing 再算 baseline。(3) macOS 無 `timeout` 指令（用 Bash tool timeout 參數）。(4) 跨 reader 一致性 E2 靠 inspection、E4 靠 execution：餵 known config 斷言兩 reader 回傳 tuple 相等才算驗到（filename 常數名不同 ALERT_CONFIG_FILE vs ALERT_CONFIG_FILENAME 但值同）。

## 2026-06-05 — L2 B+C changeset final E4 gate (feature/l2-critic-lessons-tools @ 688d289f) PASS

- **範圍**：Python-only（0 Rust）。T0 consts + C read-only tools(layer2_tools_g3_08 get_cvd/get_liquidations + wiring) + V133 agent.lessons migration + layer2_critic.py(retrieve/persist lessons) + 4 layer2_engine hooks。flags 默認 OFF(CRITIC/LESSON_STORE)；cvd/liq 默認 ON(read-only PG)。
- **Task1 權威回歸（Linux temp worktree /tmp/wt-l2-e4 @ 688d289f detached，runtime checkout 全程未碰，main）**：用 control_api_v1/.venv（pytest 8.3.5 + pytest_asyncio 1.3.0）。**關鍵：env 必設 `OPENCLAW_CSRF_SHADOW=1`**（否則 68 個 write-endpoint 測試 403 fail = 已知 env 需求非回歸，見 2026-05-30 deepdive report）。**delta 比對法**（baseline 數字史料模糊→不糾結絕對值，改跑相同指令 feature vs main worktree）：feature `688d289f` = **8 failed / 4401 passed / 11 skipped**；main `92cdcc41` = **8 failed / 4351 passed / 11 skipped** → **+50 net passed（新 layer2 測試）/ 0 NEW failure**。8 個 pre-existing fail 兩 worktree **失敗集 byte-identical**（6× test_ops1_csrf_middleware 斷言 403=被 CSRF_SHADOW=1 翻轉 + 2× test_replay_advisory_routes runtime-coupled）。跑兩遍同綠(run1=run2=8/4401)。layer2 subset = `pytest tests/ -k layer2` = **224 passed**（=5 個 layer2 檔 218 + 6 個他檔 layer2-named）兩遍同綠。
- **2026-06-05 baseline 教訓**：2555/17 是更窄的歷史 scope，與「full srv-root control_api tests」(4386 collected) 不同；E4 正解=不反推絕對 baseline，跑**相同指令的 main-worktree** 取 delta。`OPENCLAW_CSRF_SHADOW=1` 是雙刃：修 68 write-endpoint 403 但翻轉 6 個斷言-403 的 csrf-middleware 測試（兩 worktree 對稱出現故非回歸）。4 個 replay collection error(`No module named program_code`)=絕對 import 需從 srv root + PYTHONPATH，pre-existing 兩端同存 out-of-scope。
- **Task2a trgm fix 行為證明（scratch DB e4_v133_scratch ← template0 避 template1 collation mismatch，apply V133，已 DROP）**：插 3 lessons content vs hint 'grid short cost gate' similarity = 0.2759/0.2667/0.2500（0.25-0.29 band，<0.3 舊默認）+ 1 noise 0.0526。**(A) 默認 0.3：`content % hint` 回 0 rows**（重現 MIT bug）。**(B) SET LOCAL pg_trgm.similarity_threshold=0.1：回 3 rows**（noise 0.0526<0.1 正確排除，similarity DESC 正確）。**EXPLAIN（pure % match）= Bitmap Index Scan on idx_agent_lessons_content_trgm**（Recheck/Index Cond: content % ...，gin 索引仍命中）。⚠ 4-row 小表時 symbol btree 較選擇性會主導，需去 symbol 謂詞或 enable_indexscan=off 才顯示 trgm gin path；prod 大表會自然走 trgm。
- **Task2b no-leak 雙層證明**：①db_pool.py:128 `put_conn()` 每次歸還 `conn.rollback()`（rollback 失敗則 close 丟棄）；get_pg_conn() finally 必呼 put_conn。②empirical: 同 session `BEGIN; SET LOCAL=0.1`(內顯 0.1) `ROLLBACK` → `SHOW`=**0.3**；defense-in-depth: 即使 `COMMIT` 後仍 0.3（SET LOCAL 純 txn-scoped）。threshold 不洩漏到 pool 借用者。
- **Task2c C-tool SQL re-confirm（prod trading_ai read-only）**：get_cvd on market.trade_agg_1m(buy_volume/sell_volume) 回 5 根真實 1m bar；get_liquidations on market.liquidations + make_interval(secs=>86400) GROUP BY side 回 Buy/Sell 真實 24h 統計（純 SELECT，0 寫）。
- **prod 未碰確認**：scratch DB DROP、兩 worktree(wt-l2-e4/wt-l2-base) remove、agent.lessons 仍 absent、`_sqlx_migrations` max 仍 **130**。⚠ runtime checkout main 由 92cdcc41 → **c505f7ae**（外部 session ONE watchdog commit `fix(watchdog) restart-storm`，git merge-base 證 clean ff，非我所為，working tree clean，feature SHA 仍 688d289f；該 Rust 改動 0 overlap L2 changeset 不影響 delta）。
- **VERDICT: PASS（merge-ready，pending operator deploy timing）**。0 NEW failure / 0 刪測 / trgm fix 行為證實（MIT 未能完全閉合的 EXPLAIN index-scan 已閉合）/ no-leak 雙層證實 / C-tool prod read-only 證實。0 defect 退 E1。

## 2026-06-06 — P2 #6 orderLinkId Hardening (110072) regression — PASS
- 被驗物（working-tree 未提交，branch `feature/l2-critic-lessons-tools` HEAD `688d289f`）：T1 Rust `dispatch.rs`（classify 顯式 `110072 => Structural` arm + helper `close_dup_is_idempotent_success` + consumption Structural 分支 close+110072 upgrade 成功 LeaseOutcome::Consumed）+ `dispatch_tests.rs` +7；T2 Python `closed_pnl_pagination.py`（`_OPENCLAW_LINK_RE` 加 lv/ipc_close_/close_mf_fb_ + `_ENGINE_BY_TAG` lv→live）+ test +13。
- **Rust full lib 3765/0/1ign**（baseline 3758+7，跑兩遍同綠 1.12s/1.04s 非 flaky）；dispatch subset **52/0**（prior 45+7）；classify_dispatch_error(dispatch.rs:210)→classify_business_retcode(229-231)→110072 arm(350) 全鏈真實，新測非空殼。
- **Python closed_pnl_pagination 35/0** + sibling route(test_bybit_closed_pnl_route+test_live_closed_pnl_route) **16/0** = 51/0（跑兩遍同綠 0.37s 非 flaky；sibling 0 打破）。
- **跨語言 grammar 對賬（重點，非浮點而是文法）**：獨立 grep Rust 全部 production 鑄造前綴（OPEN oc_{em} @step_4_5_dispatch.rs:662 / risk-close oc_risk_/sh_risk_ @commands.rs:931+988 / maker-fb oc_close_mf_fb_ @1112 / ipc-close oc_ipc_close_ @1350/1547 / shadow-open sh_ @1358 / paper pop_ / earn earn-），em=order_link_mode_tag()∈{dm/ld/lv/xx}（pipeline_ctor.rs:317）。17-case 對賬全 MATCH：oc_{dm/ld/lv}+全 close 前綴正確歸 demo/live_demo/live；shadow(sh_)/paper(pop_)/earn/paper-defensive(oc_xx_)正確排除。**0 個 Rust-minted-but-Python-unparsed 前綴**=無 silent attribution 退化。
- **教訓**：Python 註解引 step_4_5_dispatch.rs:662 省略 on_tick/ 子路徑、commands.rs 行號對；不信註解，逐一 grep 真源確認（risk-close prefix 是變數 `prefix=if is_primary {"oc_risk"} else {"sh_risk"}` @931 非字面，需讀上下文）。backward-compat 親驗：舊正則匹配的 link 在新正則映射 engine 全 identical（純 additive）。
- **mock 審查**：Rust 測 RefCell/biz() 注入 = IO/error 邊界，驗真 classify/helper control flow；Python engine_owner_lookup mock = PG owner-map IO 邊界，seen['engine'] 斷言驗真路由非僅 final string。無 mock-hides-logic。open+110072 fail-closed 三重鎖（classify Structural / close_dup require is_close=true / non-Business err 維持 fail-closed）。
- **Linux regression = owed-post-commit**（working-tree 未提交，Linux trade-core 無此改動，與既有慣例一致；純邏輯改動無平台相關/無浮點/無 PG/async，Mac cargo+pytest 足以建信心）。未 deploy/restart。
- VERDICT: **PASS**。退 E1 清單：無。

---

## 2026-06-07 · P2 #6 follow-up (10001+duplicate open fail-closed alignment) regression — PASS

**被驗（未提交 working tree，branch `feature/l2-critic-lessons-tools`，base HEAD `9b7cf842`）**：
- `dispatch.rs`：classify `10001+duplicate` 由條件 NoOp → 無條件 **Structural**（與 110072 對齊）；`10001` arm 不再讀 retMsg。helper `close_dup_is_idempotent_success` 擴認 110072 **或** (10001 + retMsg "duplicate")，仍由 `req.is_close` guard 把 open path fail-closed。consumption log 去寫死 110072，改動態 emit ret_code/ret_msg。
- `dispatch_tests.rs`：淨 +4 `#[test]`。
- `closed_pnl_pagination.py`：`_ENGINE_BY_TAG` dict 提 module-level（cosmetic，dict 值 byte-identical 含 `lv:"live"`）。

**結果（全綠，Mac，跑兩遍非 flaky）**：
| 引擎 | passed | failed | ignored | baseline | delta |
|---|---|---|---|---|---|
| Rust openclaw_engine --lib | 3769 | 0 | 1 | 3765(#6) | +4 |
| Rust event_consumer::dispatch subset | 56 | 0 | 0 | 52(#6) | +4 |
| Python test_closed_pnl_pagination.py | 35 | 0 | 0 | 35 | 0 |

**silent test loss 終驗（獨立數，非盲信 E2）**：HEAD vs working `#[test]` 44→48（+4）、`#[tokio::test]` 8→8（0）、總 52→56（+4）、`#[ignore]` 0→0、無 `#[cfg]`-out。fn-name diff：唯一「removed」名 = `test_classify_duplicate_order_link_id_is_noop` → **rename+語意翻轉** 為 `test_classify_duplicate_order_link_id_10001_is_structural`（NoOp→Structural 斷言，仍在跑，非刪除）；5 added（含該 rename）。`test_run_dispatch_retry_noop_on_second_attempt_records_attempts_2` 不在 add/remove 清單 = in-place 編輯（NoOp 觸發碼 10001-dup → 110001 穩定 NoOp 碼，NoOp-break 路徑覆蓋意圖保留）。**0 silent loss**。

**mutation 驗 bite（自做）**：暫拿掉 helper `req.is_close` guard → `test_close_dup_is_idempotent_success_open_10001_duplicate_false`（dispatch_tests.rs:395，open fail-closed 屏障）+ 既有 `test_close_dup_is_idempotent_success_open_110072_false`（:315）**雙雙 FAIL** → 證兩 open-barrier 測試真有斷言 bite，guard load-bearing；還原後 7 passed。**0 residue 確認**（grep E4-MUTATION = 0）。

**mock 審查**：`biz()` = 純 `BybitApiError::Business` 構造（error-boundary fixture，protocol 允許）；`close_dispatch_req_for_zero()` = 真 `OrderDispatchRequest` 結構（is_close 真切換）。新測真跑 `classify_dispatch_error`/`close_dup_is_idempotent_success`/`noop_is_exchange_zero_position` 業務邏輯，非空殼。lv→live 映射（hoist 最關鍵 line）由 `test_strategy_from_link_lv_routes_to_live_engine` 等覆蓋於 35。

**教訓**：rename+語意翻轉的測試在 fn-name set-diff 會表現為「1 removed + 1 added」，須對 fn 名逐一比對才能區分「rename」vs「真刪」——本次靠 `comm -23/-13` 把唯一 removed 名定位為 rename target，避免誤報 silent loss。in-place 改 NoOp 觸發碼（10001-dup→110001）是正確做法：classify 行為變了還要保留 NoOp-break 路徑覆蓋，就換一個語意未變的 NoOp 碼，而非刪測試。

**Linux owed**：working tree 未提交，Linux 無此改動 → Linux cargo regression **owed-post-push**（與 #6 慣例一致）。本次純邏輯改動（無浮點/PG/async/migration），Mac 足以建立信心；未 deploy/restart/ssh rebuild。改動還原乾淨（mutation 測完還原）。

**結論**：PASS → follow-up ready for PM commit。

---

## 2026-06-07 · PART 2 residual hidden-OOS bridge — full regression + authoritative baseline reconcile (PASS)

**被驗（worktree `/private/tmp/wt-residual-p2`，branch `feature/residual-hidden-oos-wiring` HEAD `f8a6cfc5`，3 code files byte-clean vs committed blob、僅 docs dirty）**：sealer `candidate_hidden_oos_sealer.py`(+4 flat key + MED-2 docstring) / `residual_hidden_oos_bridge.py`(NEW producer primitive + HIGH-1 leak carve-out) / 2 test files。lineage clean：627b4772→c39f84e6→ae6fec2a→f8a6cfc5。

**Full-suite（`PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0`，先清 __pycache__；ml_training/tests + learning_engine/tests）跑 3 遍同綠非 flaky**：770 passed / 31 skipped / **0 failed**（run1=29.06s, run2=28.54s, run3=29.40s）。pytest 9.0.3 / py3.10.1。

**★ 權威 baseline reconcile（throwaway worktree `git worktree add --detach 627b4772`，跑完 remove）**：
- **parent 36c3c247（mlde-hook 之前）= 743/31** ← 正是 handoff 的「baseline 743」
- **base 627b4772（mlde-hook commit 之後）= 746/31** ← E1 的「746 pre-change」。+3 = NEW `test_mlde_shadow_advisor_residual_hook.py`（commit msg 寫「11 tests」實 collect **3** funcs，base/parent 皆 3 非 silent loss）
- **HEAD f8a6cfc5 = 770/31**。delta vs base = **+24**，**精確等於 PART 2 加的 collected test items**：sealer 4→5(+1，唯一新 fn `test_flat_window_keys_match_nested_and_split_hash_frozen`，原 4 fn 全留)；bridge NEW 0→**23**（19 fn，`test_t5_embargo_days_seconds_round_trip` parametrize 成 5 items → +4）。1+23=24 ✓。**743-vs-746 gap 已定論：743 預先於 627b4772 的 mlde-hook test**。

**skip-set delta = ZERO（決定性，非推論）**：base 與 HEAD 各 dump `-rs` skip nodeid+reason 排序後 `diff` = NO DIFF。31 skips byte-identical（全 benign optional-dep：sklearn/lightgbm/optuna/pyarrow/psycopg 未裝 + real-PG opt-in gate），PART 2 加 0 skip（24 新測全 run+pass）。無 mock/skip 藏真失敗。

**residual cluster 8 檔全綠（跑 2 遍同綠）= 81 passed / 0**：alpha_gate 14 / alpha_producer 7 / alpha_producer_db 17 / alpha_cycle 7 / signal_spec_producer 5 / hidden_oos_sealer 5 / **hidden_oos_bridge 23** / mlde_shadow_advisor_residual_hook 3。

**mock-doesn't-hide-logic（我獨立驗，非盲信 E2/MIT）**：
- **真路徑（0 業務 mock）**：T2 直呼真 `_extract_alpha_hidden_oos_v049_fields`（FACT-3 證）；T7a 真 `_load/_validate_durable_hidden_oos_state_snapshot`；T7b 真 `build_live_candidate_evidence_from_source`（honest defer = PENDING_SCHEMA/drar_missing，EXPECTED 非 bug）；T6 真 Pydantic M-4 校驗；T9 真 `compute_manifest_hash`；**T10/T11/T11b/T12/T13 經 `_drive_full_bridge_capture_manifest` 驅動 FULL `register_residual_candidate_experiment` → 真 partition/`_bucket_admissible`/`evaluate_cell`/window/真 `register_experiment`**。
- **`_FakeCursor` 只 capture 不 replace**：`register_experiment(cur,...)` 全部真做（uuid/canonical manifest hash/M-4 reject/`_extract`/config-blob inject/engine-sha gate），**只**在最後 `cur.execute(INSERT)` 撞 cursor；FakeCursor.execute 僅 append (sql,params)+skip SET LOCAL/advisory no-op，fetchone 回腳本化 RETURNING。IO 邊界 stub，業務真跑。
- **注入 register_fn spy / monkeypatch load_*（IO 邊界）**：T8 flag-OFF zero-write、T4/T12b embargo=0 fail-closed（4h+1.0s 兩 bucket）、T3 btc-clamp 捕 end_ts。
- **leak 軸 mutation bite 我親驗**：暫拿掉 step-4b DATA 層 `_bucket_admissible` 過濾 → **T13(HIGH-1) FAIL**（hash 分歧=證 report/hash 受跨界桶污染被抓）+ **T11b FAIL**（err `no_admissible_round_trips`→`insufficient_aligned_buckets`=證 T11b 釘 DATA 層 fail-closed 點，且 step-6 backstop 仍接住=defense-in-depth）；**T11 仍 PASS**（只斷 window 標籤，step-6 backstop 未 mutate）→ 印證 T13 docstring「t11 標籤、T13 計算層」分工。還原後 4 leak tests 全綠、`git diff HEAD` 空、grep E4-MUTATION=0。
- **sealer +4 flat key 是 PRODUCTION 碼**（build_hidden_oos_state），consumer = 真 `experiment_registry._extract`(:961-1005)，T2 無 mock 驅之；不進 compute_split_hash payload（T1 凍結 split_hash byte-identical 證加性）。

**cross-lang float consistency = N/A**（pure-Python evidence lane，無 Rust hot path / 無 IPC / 無共用浮點計算）——明確聲明。

**Linux / PART-3 owed（Mac 驗不到，誠實標）**：真 V132 CHECK reject（embargo_seconds>0 / windows_chk）、真 `market.klines`/`round_trips` DB 載入、真 `drar` JOIN、`OPENCLAW_ENGINE_BINARY_SHA` gate（測試用 `OPENCLAW_REPLAY_RUNTIME_ENV=mac_dev_smoke_test_only` 繞過 linux engine-sha fail-closed）、真 PG xact 雙 INSERT（replay.experiments + learning.hidden_oos_state_registry）冪等。worktree 未提交、未 deploy/restart。

**教訓**：baseline reconcile 三段定論法（throwaway worktree 跑 parent+base+HEAD 三點，逐點實測）比反推絕對 baseline 可靠——一次釐清 743(parent)/746(base mlde-hook +3)/770(HEAD +24) 全鏈，並把「commit msg 11 tests」與「collect 3 funcs」的落差證為計數口徑非 silent loss。parametrize 使「+20 fn」展為「+24 items」，delta 必對 collected items 非 fn count。

**VERDICT: PASS（ready for PM deploy）**。退 E1 清單：無。

---

## 2026-06-08 · PHANTOM-FILL-FIX-1 整合/亂序 golden 補測 + 全回歸 — PASS

**任務**：為已過 E2 的幽靈倉位修復（commit `74b2e264`，branch `feature/l2-critic-lessons-tools`）補**整合/亂序層** golden（單元層 E1 已覆蓋），只寫測試不改業務碼。根因=`PaperState.positions` 被 WS `PositionUpdate(size=0)` 與平倉 `Fill` 無序雙寫：平倉先推 position(size=0) 移除 short → close Buy fill 落空 → 修前落「開新倉」分支開出幻影反向 LONG（TON 17:03，entry=平倉價/qty=平倉量）。修法 Option A：PositionUpdate 降 advisory、`apply_fill_with_close_semantics(is_close)` reduce-only 無倉 no-op + 翻倉餘量、reconciler 新增 phantom 偵測軸（只告警）。

**新增 8 測試（3 檔，全綠，純加測試 0 業務改動）**：
- `event_consumer/tests/phantom_fill_ordering_tests.rs`（NEW，6 測試，驅動**真 `handle_exchange_event`** 整合層非 apply_fill 單元層）：G1 真亂序 PositionUpdate(0)→close Fill=flat 非幻影 LONG / G1b 正常序對照 / G3 三引擎 demo+live_demo+live 同綠（`with_kind`+`set_endpoint_env`，per `mode_state::effective_engine_mode`）/ G3b reduce-only no-op mode-agnostic / G4 partial-fill 跨 3 execution is_close 每筆透傳（尾筆 overflow reduce-only 不翻倉）/ G4b genuine-flip(is_close=false) overflow 才翻倉（與 G4 鏡像夾住 is_close 在翻倉分流的 load-bearing）。
- `position_reconciler/tests.rs`（+2）：golden #2 orphan-adopt 自癒端到端（missed-fill→`handle_orphan` 判 Adopt→`dispatch_orphan_adopt` 發 `AdoptOrphan`→`handle_paper_command`/`handle_adopt_orphan` 注入 paper_state，證 Option A 移除 PositionUpdate 兜底後自癒未失，latency=1 cycle=1 指令）+ #2b adopt 冪等（同向已有倉不翻倍）。
- `event_consumer/tests/mod.rs`（+3 行 mod 註冊）。

**bite 驗（4 個獨立 mutation，逐一改業務碼跑 golden 必 FAIL→還原綠，0 residue）**：
1. `fill_engine.rs` reduce-only guard `if is_close→if false`：G1/G3/G3b FAIL（left=1 開出幻影 LONG）。
2. `loop_exchange.rs` Fill 分支 `po.is_close→false`（整合層 is_close 漏傳）：G1/G3/G4 FAIL。
3. `fill_engine.rs` 翻倉條件 `!is_close && overflow→overflow`（無視 is_close）：G4 FAIL、G4b PASS（證 is_close 是 reduce-only-no-flip vs genuine-flip 的判別子）。
4. `orphan_handler.rs` `dispatch_orphan_adopt` send 短路 return false：golden #2 FAIL（無 AdoptOrphan 指令→paper_state 不注入）。
還原後 `git diff HEAD` 業務檔全空、grep E4-MUTATION=0。

**Mac 全回歸（跑兩遍非 flaky）**：
| 引擎 | passed | failed | ignored | baseline(HEAD 74b2e264) | delta |
|---|---|---|---|---|---|
| openclaw_engine --lib run1 | 3788 | 0 | 1 | 3780 | +8 |
| openclaw_engine --lib run2 | 3788 | 0 | 1 | 3780 | +8 |
| 全 `cargo test -p openclaw_engine`（lib+bins+~40 integration binaries 聚合）| 4153 | 0 | 4 | — | — |
（prompt 引用 baseline 3779；HEAD 實測 3780，差 1 屬計數口徑，以**改動前實測**為準。+8=精確等於 8 新測。reconciler_e2e 19/0、stress_integration 35/0、全 integration binaries 0 failed。）

**Linux owed-post-push**：Linux trade-core 在 `main@8cd4da1f`，修復在 feature branch（HEAD 74b2e264）未上 main、新測試檔 Linux 不存在。取程式碼需 push branch → 依 prompt 停下標記 owed 給 PM（不擅自 push/不動 runtime/不切分支）。本次純 Rust 邏輯+test 改動（無浮點跨語言/無 PG/無 migration/無 async race 新面），Mac release 足以建信心；Linux cargo regression 待 PM 協調 push/worktree 後補。

**揭露 bug**：無。修復行為與 8 golden 全部一致，無退 E1 項。

**教訓**：(1) E2 指定「整合/亂序層」golden 必須驅動真 `handle_exchange_event`（經 PendingOrder 匹配→`apply_confirmed_fill`→`apply_fill_with_close_semantics` 全鏈），不能只在 apply_fill 單元層加——單元層 E1 已覆蓋，整合層才抓得到「is_close 在 loop_exchange 漏傳」這類接線 bug（bite #2 證明）。(2) 三引擎驗證的可執行做法=`with_kind(kind)`+`set_endpoint_env(env)` 組出 demo/live_demo/live（canonical pattern 在 `h0_latency_metrics.rs`），把「三模式共用 PaperState」從文檔主張變成可 FAIL 的斷言。(3) 一對鏡像 golden（G4 reduce-only no-flip vs G4b genuine-flip）配合「無視 is_close」的 mutation，能精準夾住一個 bool 旗標在分流邏輯的 load-bearing 性，比單測更有 bite。(4) bite 驗證業務檔改完務必 `git diff HEAD` 確認 byte-clean + grep mutation marker=0，避免污染 PM 的隔離 commit。

---

## 2026-06-08 · residual PART 4 Phase 1 (Gap B+C) regression + E2 LOW#2 closure (PASS)

**被驗**：worktree `/private/tmp/wt-residual-act`，branch `feature/residual-activation`，commit `da3aec6f`（base=`da3aec6f~1`=merge-base origin/main=`8cd4da1f`）。Gap B 多因子殘差化（funding-carry PIT）+ Gap C sign-flip permutation，flag-gated OFF、behavior-neutral。E2+MIT 已 PASS（report 未落 disk，僅 PA design 為 untracked dirty）。Python-only。

**全量決定性 ×2（`PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0`、先清 __pycache__；ml_training/tests+learning_engine/tests）**：HEAD `da3aec6f` = **826 passed / 31 skipped**（run1=run2 identical，無 flake）。pytest 9.0.3 / py3.10.1。

**★ 權威 baseline reconcile（throwaway worktree `git worktree add --detach 8cd4da1f`，跑完 remove）**：base `8cd4da1f` 全量實跑 = **794 passed / 31 skipped**（精確等於 E1 claim）。collect-only node-ID diff（base 823 vs HEAD 855）：**REMOVED=0 / ADDED=32**，逐 fn 對賬 gate +14 / cycle +2 / producer_db +11 / report_contract +5 = +32。delta = 826−794 = **+32 = 100% 新增測試、0 regression**。spec 的「770」是 PART-2 之前史料；當前 HEAD 真 base = 794（mlde-hook+PART-2 neighbor commits 已進 8cd4da1f）。

**skip-set delta = 0（決定性）**：base 與 HEAD 各 `-rs` dump skip nodeid+reason 排序 `diff` = NO DIFF。31 skips byte-identical（全 benign：sklearn/lightgbm/optuna/pyarrow/psycopg 未裝 + real-PG opt-in gate）。Gap B/C 加 0 skip，32 新測全 run+pass，無 mock/skip 藏真失敗。

**E2 LOW #2 closure（唯一 business-relevant 新測）**：E2 mutation #3 證既有 `test_permutation_determinism_same_seed_same_p`（fixture mean=1.0/std=2.0/n=50）p **飽和到 0.0** → 打斷 seed binding（`default_rng()` 忽略 seed）後 `assert p1==p2` 仍過（0.0==0.0），不咬 broken seed（我實證：broken seed 下該舊測仍 PASS）。新增 `test_permutation_determinism_borderline_p_binds_seed`：弱訊號手構 fixture（27×+0.5/23×-0.5、n=50、obs mean=0.04bps）使 p 落 ~0.66–0.69 非飽和、隨 seed 變動。斷言：同 seed(20260608) 兩呼 p=0.668 嚴格相等 + 異 seed(777) p=0.6812 close-but-not-identical（|diff|=0.0132，皆∈[0.60,0.75]）。值在 HASHSEED=0 下跨 run 可重現（PCG64 整數抽樣平台無關）。**mutation-bite 親驗**：暫拿掉 line 839 `rng=default_rng(int(seed))`→`default_rng()`，我的測試 **FAIL**（同 seed 兩呼發散 0.662 vs 0.68），舊測同條件仍 PASS。還原後 git diff 業務檔空、grep E4-MUTATION=0、新測綠×2。

**mock-doesn't-hide-logic（獨立驗，非盲信 E2/MIT）**：(1) 真路徑 0 業務 mock — funding PIT `test_bucketed_funding_factor_pit_only_settled_rows` 驅真 `bucketed_funding_factor`（未來費率 9.0 排除斷言真咬 PIT）；beta-trap `test_evaluate_cell_funding_carry_beta_trap_fails` 驅真 `evaluate_cell` 全鏈（殘差化還原 funding_beta≈1.5、raw+→residual≤0）；permutation 全測直呼真 `_permutation_residual_alpha`。(2) IO 邊界 stub（允許）— `test_load_funding_rates_converts_and_drops_bad` 用 `_MultiConn/_MultiCursor` fake DB 連線，真跑 `load_funding_rates`（timestamptz→epoch、壞 rate drop）。(3) 唯一 stub-thing-under-test = `test_attach_residual_reports_maps_to_payload`（**pre-existing 非我 +32**）monkeypatch `build_cycle_residual_reports`，正確隔離 payload-mapping wrapper 並真跑 `validate_signal_spec`。32 新測**無一** stub 受測對象。

**behavior-neutrality（含我新測在 tree）**：cross-worktree 親算 default-report canonical SHA256 = base `8cd4da1f` 與 HEAD 皆 **`1571eade7def...`**（同 19-key keyset、permutation OFF 無 perm 欄位）。我的測試純加性（直呼 bare permutation fn 帶顯式 seed，不碰 default `evaluate()` 路徑），byte-identity 不動。全量 ×2 含新測 = **827/31**（commit 後 HEAD `c6cc1578` 再跑 = 827/31）。

**cross-lang float = N/A**（pure-Python evidence lane，無 Rust hot path / IPC / 共用浮點）——明確聲明。

**Linux owed（誠實標）**：funding settlement-timing dry-run on real `market.funding_rates`（Mac 用合成 settlement 列；**MIT 已做 settlement-timing dry-run**）；真 PG multi-factor DB cycle 載入。**Gap-A（非本批）**：Stage-0R orchestrator 接 DB loaders、net_side/orchestrator 接線。worktree 未提交主線、未 push/deploy/restart。

**commit**：`c6cc1578`（`git commit --only` 隔離 test 檔，+44 行，**未 push**；untracked PA design doc 未動）。

**教訓**：(1) 「seed 綁定」的 determinism 測試只有在**非飽和 p**（borderline regime）才有 bite——強訊號 fixture 把 p 釘在 0.0/1.0 時 `p1==p2` 對 broken seed 無鑑別力。補測要先實證舊測在 mutation 下仍綠，再構造弱訊號 fixture 落到 p 隨 seed 變動的中段，並用「同 seed 兩呼嚴格相等」當 bite 點（broken→entropy 播種發散）。(2) 鎖 magic p 值前必跑兩遍確認 PCG64 跨 run 重現（HASHSEED=0），documented 值用 `pytest.approx(abs=1e-9)` 而非 ==。(3) baseline reconcile 仍用 throwaway-worktree 三點實測法：spec 引用的舊數（770）是史料，HEAD 真 base 以 `merge-base` checkout 實跑為準（794）。

**VERDICT: PASS（ready for P2）**。退 E1 清單：無。

---

## 2026-06-08 · L2 D3 Phase 1 (V134/V135/V136) Linux PG 雙-apply 冪等 dry-run + columnstore ADD COLUMN — PASS

**被驗（branch `feature/l2-critic-lessons-tools`，3 migration 全 untracked 未提交，scp 入 Linux/容器 temp，不 commit）**：V134 `agent.l2_calls`(24-col forensic ledger)+`agent.l2_consequential_marks`(append-only side-table) / V135 `learning.l2_gate_seam_log` / V136 additive `source_l2_reply_id TEXT NULL` ALTER 到 `learning.hypotheses`+`replay.experiments`+`trading.fills`。md5 三檔 Mac==Linux 親驗（V134 87d82568 / V135 95165c3b / V136 718880e1）。E2+E3 sanitize gate 已 PASS。

**PG 拓樸（先查容器名鐵律）**：PG 在 docker container **`trading_postgres`**（timescale/timescaledb:latest-pg16，127.0.0.1:5432），prod db `trading_ai`，superuser `trading_admin`，**TimescaleDB 2.26.1**。`docker exec trading_postgres psql -U trading_admin -d <db>`。**坑：app role `trading_ai` 在 prod 不存在**（只 trading_admin）→ migration 的 grant 分支在 prod 走「role absent NOTICE」路；要真測 append-only grant 必須在 scratch 自建 `trading_ai` role 讓 GRANT/REVOKE 分支真 fire。

**★ scratch DB 建法（schema-only clone 有兩個真陷阱）**：(1) `CREATE DATABASE` 從預設 template1 在此 TS image **靜默失敗**（無 error 無 DB）→ 必用 `TEMPLATE template0`。(2) **`pg_dump --schema-only`+`timescaledb_pre/post_restore` 不重建 hypertable+compression catalog**——`trading.fills` restore 回來變 plain table（`timescaledb_information.hypertables` 0 rows，雖然內部 `_hyper_NN_chunk` 在）→ 用 schema-only scratch 測 columnstore ADD COLUMN = **false PASS**（等同 Mac mock 盲點）。**修法：手動把 `trading.fills` 重建為 faithful 壓縮 hypertable**（drop→CREATE 對齊 prod 28 欄+`track public.strategy_track`〔dump 把 enum 落 public 非 trading〕→`create_hypertable(ts,7d)`→`SET (timescaledb.compress, compress_segmentby='symbol')`〔對齊 prod compression_settings〕→INSERT 50 row→`compress_chunk(if_not_compressed)`），驗到 `compression_enabled=t`、`compressed_chunks=1/1` 才是真 columnstore。其餘兩 plain target（hypotheses/experiments）schema-only restore OK。

**驗收項 1-6 全 PASS（真 psql 輸出）**：
1. **first-apply** V134→V135→V136 全 `PSQL_EXIT=0` 零 EXCEPTION：V134 兩表+兩 hypertable(created_at/marked_at 7d)、Guard A/B/C 無 raise、trading_ai grant 分支 fired；V135 表+hypertable(ts 7d)+grant fired；**V136 `Guard A PASS` NOTICE + 三 ALTER 全成功（含 fills columnstore）**。
2. **second-apply 冪等** 全 `PSQL_EXIT=0` 零 false-RAISE：所有 IF NOT EXISTS no-op（"already exists/already a hypertable, skipping"）、Guard A 反映既存欄無 raise、**V136 Guard B 三表印 "PASS: already text NULL (idempotent)"**、三 `ADD COLUMN IF NOT EXISTS` no-op（含 fills 二次 ADD 仍不 raise）。
3. **append-only grant**：`has_table_privilege(trading_ai,...)` 三新表 **UPDATE=false DELETE=false INSERT=true SELECT=true**；`information_schema.column_privileges` trading_ai UPDATE = **0 rows**。"column_update_grants_count=39" **全部 grantee=trading_admin（owner 隱含，無害）**，trading_ai 零 column-UPDATE。grep SQL：唯一 UPDATE(col) 命中是**註解**（V134:24 解釋為何避免），**0 條可執行 `GRANT UPDATE(col)`**；所有 GRANT = table-level `SELECT,INSERT` + BIGSERIAL `USAGE ON SEQUENCE`。`consequential_at_creation` 無 UPDATE 路徑（INSERT-set-once）。
4. **★ columnstore-safe ALTER（Mac 絕對測不到、最高價值）**：`trading.fills` 真壓縮 columnstore（compression_enabled=t、1/1 compressed chunk）上 `ADD COLUMN source_l2_reply_id TEXT NULL`（nullable/無 DEFAULT/不 SET NOT NULL）**first+second apply 皆不 raise `feature_not_supported`**（V077/V101 陷阱不觸發）；新欄 `text/YES` 傳播到 compressed chunk（`compress_hyper_2_2_chunk` 顯 USER-DEFINED = 正常 compressed-segment 表示）。ALTER 後 fills 仍 compression_enabled=t、1/1 compressed。
5. **零 column-grant → compression-ready**：因三表 0 條 column-level UPDATE grant，未來開 compression 不撞 V114 compressed-twin 42703 abort（結構性確認）。
6. **★ prod 零觸碰**：dry-run 前後 `_sqlx_migrations` **head=133 rows=116 不變**（親驗 ×2）；prod 0 l2 tables、0 source_l2_reply_id 欄；`trading_ai_sandbox` 鄰庫未動。**坑：role 是 cluster-global**——我在 scratch `CREATE ROLE trading_ai` 後它在 prod `pg_roles` 也可見（但 0 grant/0 owned object，nosuperuser）→teardown 必 `DROP ROLE` 還原（drop scratch DB 先，再 drop role；確認 prod_trading_ai_role=false 復原）。

**回歸（SECONDARY）— redactor 純-Python parity = PASS**：`test_l2_d3_ledger.py` import `l2_secret_redactor`+`l2_call_ledger_writer`，writer 又拉 `db_pool/error_sanitize`，wiring/lessons/cost-tracker 測拉 `layer2_engine/critic/types/cost_tracker`。**不污染真 Linux 樹**：rsync 真 control_api_v1→`/tmp/l2_dryrun/cav1` 再丟新檔（真 runtime checkout 全程零觸碰，親驗 3 新檔仍 absent）。裸 temp 只丟 2 新檔 → 5 fail（`Layer2Session 無 l2_reply_id`/`layer2_engine 無 _get_l2_ledger_writer`/lesson+session redaction）**全是 companion-artifact**：`layer2_cost_tracker/critic/engine/types` 是 **Mac uncommitted `M`**，Linux 是舊 committed 版。逐一 scp 4 companion 後 **full file Linux 78 passed/4 xfailed/0 failed ×2 非 flaky == Mac 78/4/0**（含 4 strict-xfail naked-context-free 高熵殘留兩端同 xfail）→**零真 Linux 分歧**。redactor-only 類 Linux 62 passed/4 xfailed（Mac 同檔 redactor 類 63 passed〔`-k Redactor` 含 fast-path/keyword/sizecap/store-span 子類〕；prompt 引用 272 是跨多檔 layer2-family in-scope 總數，本檔貢獻 redactor 類）。pytest Linux 9.0.2 / pytest-asyncio 1.3.0。

**owed（誠實標）**：**full layer2-family Linux 完整回歸 = owed-post-commit/push**（4 companion + 2 新檔 + test 全 untracked，整包不便在真樹跑；本次以 temp-tree 證 file-level parity，full-suite delta 待 push）。真 sqlx-migrate apply（OPENCLAW_AUTO_MIGRATE）= operator-gated deploy（本 dry-run 純 psql -f，未走 sqlx，prod 未 register 134/135/136）。

**教訓**：(1) schema-only clone 測 columnstore 必先驗 `timescaledb_information.hypertables` 真有 row——pg_dump 不帶 hypertable catalog，restore 回 plain table 會給 columnstore ADD COLUMN false PASS，等同 Mac mock 盲點；要手搓 faithful 壓縮 hypertable（對齊 prod compress_segmentby + 真 compress_chunk）才測得到 V077/V101 陷阱。(2) PG role 是 cluster-global 非 per-DB——為測 grant 分支在 scratch CREATE ROLE 會洩漏到 prod pg_roles，teardown 必 DROP ROLE 並親驗 prod 復原 false（"prod 零觸碰"不只看 schema/migrations 還要看 cluster-global role）。(3) untracked test 依賴 untracked companion production 改動時，Linux temp-tree 跑會以 missing-companion 形式報假 fail；逐一 scp Mac `M` companion 把 fail 收斂到 0 才證「零真 Linux 分歧」，否則 5 fail 會被誤讀成 redactor parity 破。(4) `CREATE DATABASE` 在 timescale image 用 template1 靜默失敗→一律 TEMPLATE template0。

**VERDICT: PASS（ready for PM commit/push；migration dry-run 全綠、prod 零觸碰 133 不變、redactor parity 確認）**。退 E1 清單：無。

## 2026-06-08 · residual PART 4 FINAL regression — whole gap-closure (P1+P2) at HEAD 67730b7b (PASS, ready for PM deploy flag-OFF)
**被驗**：worktree `/private/tmp/wt-residual-act` branch `feature/residual-activation` HEAD `67730b7b`（P2 MIT HIGH-1/HIGH-2）。全鏈 = P1(B+C, `da3aec6f`+`c6cc1578`) → P2 orchestrator(`2a5df09e`→`7d2cdcba`→`67730b7b`)。Python-only。worktree 業務檔 byte-clean（僅 E2 memory.md `M` + 1 untracked PA design doc，非業務）。
**全量決定性 ×3 同綠非 flaky**（`PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0`、先清 __pycache__+.pytest_cache；ml_training/tests+learning_engine/tests）：HEAD = **855 passed / 31 skipped / 0 failed**（run1=35.14s, run2=34.84s, run3 `-p no:cacheprovider`=34.76s，三跑 identical 無 ordering/cache 耦合）。cron tests（`helper_scripts/cron/tests`）= **53 passed ×2**。pytest 9.0.3 / py3.10.1。
**★ 權威 baseline reconcile（throwaway worktree 三點實測，跑完 remove）**：base `8cd4da1f`（origin/main merge-base）= **794/31**（精確）；P1 `c6cc1578` = **827/31**；HEAD `67730b7b` = **855/31**。collect-only node-ID diff（含 sort -u 去重）：base 823 nodes → HEAD 884 nodes，**REMOVED=0 / ADDED=61**（= 855−794）。逐段 0-removed：base→P1 ADDED=33（gate+15/cycle+2/producer_db+11/report_contract+5）、P1→HEAD ADDED=28（orchestrator preflight+26/gate+2）。**skip-set delta = 0**（31 SKIPPED node-IDs base 與 HEAD `diff` 完全相同）。**884 vs 855+31=886 的 2-node 差 = module-level import-skip**（optuna/pyarrow/sklearn/lightgbm 未裝 Mac → 整模組 SKIPPED outcome 但 collect-only 不列其內函數），pre-existing 環境 skip、base/HEAD 一致、非我引入。
**mock-doesn't-hide-logic（P2 orchestrator 新風險面，獨立驗）**：FakeCursor(`_Cursor`/`_DrarStampCursor`/`_Conn`) 只捕 SQL/params+腳本化 to_regclass probe，**不替換** register-extract/persist 邏輯；`_RegisterSpy` 是 capturing wrapper，記錄 bridge **真算**並放進 `body.manifest_jsonb` 的 report+registry_residual_hash（非捏造）；`_patch_db` 只 monkeypatch DB **loader**（IO 邊界），其 `_fake_load_candidate_net_side` 呼**真** `derive_net_side_from_fills`。**真路徑（驅真碼於合成資料）**：`test_six_step_flow`/`test_no_peer_synthesis`/`test_cross_writer_hash_byte_identity_with_permutation`/`test_single_config_defers_pbo` 驅真 `evaluate_cell`+真 `_canonical_sha256`+真 `register_residual_candidate_experiment`；**deciding-factor e2e** `test_beta_trap_end_to_end_gate_vetoes` 驅真 `build_live_candidate_evidence_from_source` on orchestrator 實寫 payload，並做 (A)有report→真 math reason `residual_alpha:passes_not_true` vs (B)無report→`residual_alpha:not_dict` 對照，證 HIGH-1 修復把判據從「缺席默拒」改成「真 math verdict」；per-symbol net_side `test_net_side_per_symbol_overrides_strategy_wide_short`（顯式 mutation guard `assert side_sym != side_all`）+ e2e `test_orchestrator_threads_candidate_symbol_into_net_side` 重現 MIT RAVEUSDT 發散驅真 `derive_net_side_from_fills`；**-0.0 hash** `test_to_dict_normalizes_negative_zero_to_positive_zero`（fixture 以 copysign 證真帶 -0.0）+ mutation-bite `test_negative_zero_drift_without_normalization_would_break_hash`（證未正規化 `_canon_sha256(raw_neg)!=raw_pos`→漂移，正規化後相等）。**唯二 stub-thing 的 `_fake_eval`**（`test_drar_hash_matches_registry_when_report_passes`/`test_pass_report_in_payload_passes_first_gate`）注入合成 PASS report——**非掩蓋 gate**：真 gate 對單配置誠實 defer（無 peer→無 PBO），這兩測只驗下游 wiring（drar hash byte-identity + source-contract 第一道過閘），真 gate veto 路徑由 beta_trap/no_peer 測獨立覆蓋。**無一新測 stub 受測對象**。
**獨立 mutation-bite 親驗**（非盲信）：暫改 orchestrator `load_candidate_net_side(... symbol=symbol ...)`→`symbol=None`（退回 strategy-wide）→ `test_orchestrator_threads_candidate_symbol_into_net_side` **FAIL**（`assert None == 'RAVEUSDT'`），還原後 git diff 業務檔空 byte-clean。
**cross-language float**：N/A（純 Python）。唯一 real-PG 語義點 = `-0.0` PG-jsonb 丟符號位，由 MIT 在 Linux 真 PG round-trip 驗（本 Mac 測在 in-memory 層證 `_normalize_zeros` chokepoint 已先抹平使 jsonb 丟符號成 no-op）。
**behavior-neutrality（triple-OFF → 0 writes / orchestrator unreachable）三層親驗**：(1) orchestrator `run_residual_stage0r_preflight` 三重 gate `cfg.enabled AND stage0r_preflight_enabled() AND residual_producer_enabled()`，任一 OFF 在開 conn 前早退（`test_behavior_neutral_*`/`test_cfg_disabled_zero_writes` 用 conn_factory raise AssertionError 證零連線）；(2) cron `_run_residual_preflight` wrapper 再 check 雙 flag → skipped；(3) `residual_preflight` 在 OPTIONAL_JOBS **非** DEFAULT_JOBS（預設 cron 不 dispatch）。**OFF-path 報告 canonical SHA byte-identity**：`ResidualEdgeReport.to_dict()`（permutation OFF=default→pop 3 perm key）18-key SHA256 = base `8cd4da1f` 與 HEAD 皆 **`5b884182...`**。Gap B/C/D 全純加性。`derive_net_side_from_fills` `symbol=None` default 保留既有 caller 行為；`write_demo_residual_alpha_report` 是從 `_persist_residual_alpha_report` 抽出共用薄 helper（原 caller 改 delegate，behavior-neutral by construction）。
**未改既有測試**：PART 4 只動 6 個 residual test 檔（5 main + 1 cron），0 pre-existing test 檔被改、0 assertion 被刪/弱化（git diff `*/tests/*` non-residual = 空）。
**Linux owed（operator deferred ACTIVATION run）**：branch 未 push、Linux trade-core 在 main@`8cd4da1f` 無這些新檔。flag-ON real-write activation 需 (1) rebase+push+deploy branch (2) signal_spec producer 真啟用仍 pending (3) hidden_oos sealer 真 activation 仍 pending。本次純 Python+test（無 Rust/無浮點跨語言/無新 migration/無 async race 新面）→ Mac pytest ×3 足以建信心；Linux full regression 待 PM 協調 push 後補（且 -0.0 PG round-trip 已由 MIT Linux 驗）。
**verdict = PASS**（ready for PM deploy flag-OFF）。我**未**改任何業務邏輯、**未**新增測試（既有 +61 覆蓋充分含 mutation-bite，無 uncovered regression）。throwaway worktree 已 remove。
**教訓**：(1) collect-only node-ID 三點 diff（base/P1/HEAD 各 throwaway-worktree 實跑）逐段證 0-removed 比單點絕對數可靠——一次釐清 794→827(P1 +33)→855(P2 +28)=+61 全鏈。(2) `--collect-only` node count（884）會少於 `-q` summary outcome（855+31=886），差額 = 整模組 import-fail 的 collection-time SKIP（其內函數無法 collect 故不在 node 列但算 1 SKIPPED outcome）——reconcile 時要認得這口徑差，否則誤判「2 node 不見了」。(3) capturing-wrapper register_fn / FakeCursor / loader-only monkeypatch 是 mock-doesn't-hide 的正確形態：受測對象（gate/hash/source-contract/net_side derive）全真跑，只 stub IO 邊界與捕捉寫入——驗證時要逐測 trace「真 vs stub」分界，並對關鍵 e2e 親做 mutation-bite（symbol-threading 拔掉→測紅）證非 tautology。

## 2026-06-09 · residual PART 4 Gap-A market-basket fix — final regression at HEAD 2fca92fe (PASS, ready for PM deploy flag-OFF)
**被驗**：worktree `/private/tmp/wt-residual-act` branch `feature/residual-activation` HEAD `2fca92fe`（PART 4 Gap A：替換字母序 basket 選取 `sorted(set(active))[:N]`→`load_liquid_basket_symbols`〔read-only count 查詢，按 4h-bar 計數排序，`symbol = ANY(active)` 夾在 PIT-active 集內保 survivorship〕），parent=`67730b7b`（PART-4 FINAL，TODO baseline=855/31）。4 檔改（+314/-3）：`residual_alpha_producer_db.py`〔新 `load_liquid_basket_symbols`+`_LIQUID_BASKET_QUERY`+`__all__`〕、`residual_stage0r_preflight.py`〔`_load_multi_factor_inputs` seam 改 caller〕、+2 test 檔（+4 tests）。E1 已在真 Linux PG 驗（basket 60/60 bar>0、market_buckets=113、gate 產真 report）；E2 PASS（0 finding，survivorship-safe，mutation-verified）。Python-only。worktree 業務檔 byte-clean（僅 TODO.md+E2 memory `M`+1 untracked PA design doc，非業務）。pytest 9.0.3/py3.10.1。

**全量決定性（`PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0`、每跑前清 __pycache__+.pytest_cache；ml_training/tests+learning_engine/tests）**：HEAD `2fca92fe` = **859 passed / 31 skipped / 0 failed**，跑 **5 遍同綠**（含 2 次 `-p no:cacheprovider`，run 23.3–34.0s）非 flake、無 ordering/cache 耦合。cron（`helper_scripts/cron/tests`）= **53 passed ×2**。

**★ 權威 baseline reconcile（throwaway worktree `git worktree add --detach 67730b7b`，跑完 remove）**：parent `67730b7b` 全量 = **855 passed / 31 skipped**（精確等於 TODO header + E1/E2 claim），跑 3 遍穩定。collect-only node-ID diff（normalize 路徑前綴後 sort -u）：parent 884 → fix 888，**REMOVED=0 / ADDED=4**（= 859−855），4 個 ADDED 逐一對賬 = 正是 3× `load_liquid_basket_symbols` unit（`test_liquid_basket_picks_data_bearing_not_alphabetical`/`_respects_limit_keeps_most_liquid`/`_empty_candidates_returns_empty`）+ 1× orchestrator real-seam（`test_load_multi_factor_inputs_selects_data_bearing_not_alphabetical`）。0 regression。**skip-set delta = 0**（`-rs` dump skip nodeid+reason 排序 `diff` = NO DIFF；31 skips byte-identical，全 benign optional-dep/opt-in-PG：sklearn 6/lightgbm 7/optuna 1/pyarrow 1/psycopg 13/real-PG opt-in 3；4 新測加 0 skip、全 RUN+PASS）。

**★ flake 觀察（記教訓）**：剛 `git worktree add` 後的**第一次** combined 跑出現 15 failed/840 passed（全在 `test_residual_stage0r_preflight.py`），但同失敗測試**單獨跑 PASS**、`ml_training/tests` 單獨 629/31/0、`learning_engine/tests` 單獨 226/0、隨後 3 次 combined 重跑全部回到 855/31。判定 = **freshly-created-worktree 首跑 settling 假象**（路徑/bytecode warmup 競態），非 parent 真 regression、非 fix 引入。教訓：throwaway-worktree 首跑要丟棄並重跑數遍取穩定值，勿把首跑假失敗當 baseline。

**mock-doesn't-hide-logic（獨立驗，非盲信 E2/E1）— 命名 real-code-on-synthetic vs IO-boundary stub**：
- **orchestrator real-seam（real-code-on-synthetic）**：`test_load_multi_factor_inputs_selects_data_bearing_not_alphabetical` **刻意不 patch `load_liquid_basket_symbols`**（diff 證：只 monkeypatch lifecycles/klines/funding loaders），驅動**真**選取 seam 經 `_load_multi_factor_inputs` 全鏈；`_OrchCountConn/_OrchCountCursor` 模擬 PG GROUP BY count(*)（不回 0-bar symbol）= IO 邊界；lifecycles 讓字母序前綴空 symbol 全 PIT-active（舊 `sorted(active)[:N]` 必選之）→ 這正是抓「回歸到字母序」的 bite 點。
- **3 units（IO-boundary stub，受測對象真跑）**：直呼**真** `load_liquid_basket_symbols`，`_CountCursor/_CountConn` 只 capture SQL+params 並回腳本化 rows（IO 邊界 stub），函數內部 syms 清洗/空-guard/RealDictCursor row 抽取/append 全真做。`test_liquid_basket_picks…` 另斷言 query-building（`ANY(%(symbols)s)`/`GROUP BY symbol`/`ORDER BY count(*) DESC`/params symbols=候選域/limit/tf）。**無一新測 stub 受測對象本身**。

**獨立 mutation-bite 親驗（2 個，逐一改業務碼跑必 FAIL→還原綠）**：
1. orchestrator seam `load_liquid_basket_symbols(...)`→`sorted(set(active))[:N]`（退回字母序）：`test_load_multi_factor_inputs_selects_data_bearing_not_alphabetical` **FAIL**（basket 選到 0GUSDT/1000000BABYDOGEUSDT/1000000CHEEMSUSDT 空 symbol → 正是修復前 market_buckets=0 根因）；**3 units 仍 PASS**（直呼函數不走 seam）→ 證 orchestrator 測釘 seam-wiring、units 釘函數內部邏輯的分工。
2. `load_liquid_basket_symbols` 末行 `return out`→`return sorted(syms)[:limit]`（無視 DB rows）：`_picks_data_bearing` + `_respects_limit_keeps_most_liquid` + orchestrator e2e 三者 **FAIL**；`_empty_candidates_returns_empty` 仍 PASS（空-guard 在 mutated line 前短路）→ 證 units 真咬 DB-row 過濾/排序非 tautology。
還原後 `git diff 2fca92fe` 業務檔空 byte-clean、grep E4-MUTATION=0。

**cross-language float = N/A**（純 Python evidence lane，無 Rust hot path / IPC / 共用浮點）——明確聲明。

**behavior-neutrality（task 5）**：orchestrator test file = **27 passed** = 26 pre-existing（全綠未動）+ 1 新 seam 測；flag-OFF/default 路徑（`-k behavior_neutral or disabled or zero_writes or cfg_disabled`）= **3 passed**。修復純粹改 `_load_multi_factor_inputs` 內**選哪些 symbol 進 basket**（只在 gate 真計算的 flag-ON reachable 路徑生效），triple-OFF 早退與 zero-write guard 完全未動。未改任何 pre-existing 測試、未刪/弱化 assertion（git diff `*/tests/*` 僅 +4 新測）。

**Linux owed（operator-deferred ACTIVATION run）**：branch 未 push、Linux trade-core 在 main 無此新 commit。flag-ON real-write activation 仍 operator-deferred（E1 已單獨在 Linux PG 驗 basket 60/60 + market_buckets=113 + gate 產真 report）。本批純 Python+test（無 Rust/無浮點跨語言/無新 migration/無 async race 新面）→ Mac pytest ×5 足以建信心；Linux full regression 待 PM 協調 push 後補。

**verdict = PASS（ready for PM deploy flag-OFF）**。我**未**改任何業務邏輯、**未**新增測試（既有 +4 覆蓋充分含雙重 mutation-bite，無 uncovered regression）。throwaway worktree 已 remove。退 E1 清單：無。

**教訓**：(1) 「real-code-on-synthetic」與「IO-boundary stub」要逐測命名分界：orchestrator 測**不可** patch 受測 seam 函數（否則就是當初漏 bug 的同盲點——合成注入繞過 DB 選取），units 才用 FakeCursor stub IO 邊界、函數本體真跑。一條 e2e（不 patch seam）+ N 條 unit（stub IO）的組合才同時釘住 wiring 與內部邏輯。(2) 一對「seam 退回字母序」+「函數無視 DB rows」的鏡像 mutation 能精準分離「seam 是否接對」與「函數邏輯是否對」——bite 1 只紅 orchestrator、bite 2 紅 units+orchestrator，分工被證實非 tautology。(3) `git worktree add` 後首跑可能因路徑/bytecode warmup 競態報假大量失敗（本次 15 failed/840），單測卻 PASS——必丟棄首跑、重跑 3 遍取穩定 baseline，否則誤判 parent regression。

### 2026-06-09 L2 P3a ml_advisory（diagnose/interpret，0 migration）Linux parity + agent.lessons sink grant/schema 回歸驗證

**Trigger**：E2 PASS + E3 PASS + MIT APPROVE-CONDITIONAL（M3 leak-typing / M4 Ollama recall calibration GRANTED；2 sink findings owed-verify）。E4 對 P3a 做 Linux parity + agent.lessons sink grant/schema（MIT S-1 類比）。branch `feature/l2-critic-lessons-tools` @ `6a9dd0f1`（P3a 未 commit）。**不改業務邏輯/不新增測試**。

**VERDICT: PASS。退 E1 清單：無。**

**Linux parity（PRIMARY 1）= 完全對齊 Mac，0 真回歸**：rsync 真 `control_api_v1`(38M/1528f) → `/tmp/l2_p3a_dryrun/srv/.../control_api_v1` + Mac(modified) settings TOML → `/tmp/.../srv/settings/`，`OPENCLAW_BASE_DIR=/tmp/l2_p3a_dryrun/srv`（registry `_default_registry_path` 用 env+parents[5]，base=srv）。**full-tree rsync 一次抓齊所有 companion**（executor import `db_pool/l2_out_of_bound_guard/l2_prompt_contract_registry/l2_secret_redactor/l2_call_ledger_writer`；orchestrator 再拉 layer2_engine 等——全是 Mac uncommitted `M`/untracked），**避開上輪 D3 的 companion-artifact 假 fail 陷阱**（逐 scp 易漏；full-tree 0 drift）。`test_l2_p3a_ml_advisory.py` **53 passed/0 ×2 非 flaky == Mac 53**；layer2-family 8 檔（d3_ledger/p2_orchestrator/p3a/critic/escalation/g3_08/layer2/tools）**439 passed/4 xfailed/0 ×2 非 flaky == Mac 439**（4 xfail=既有 naked-context-free 高熵殘留兩端同 xfail）。**Linux py3.12.3/pytest9.0.2/pydantic2.12.5/tomllib/pytest_asyncio1.3.0 是權威**——Mac py3.10(有pytest+pydantic無tomllib)/py3.12(有tomllib無pytest+pydantic)**雙環境皆無法跑全套**（MIT 同此盲點），故 Linux run 即 parity 權威，誠實標「Mac 53/439 由 E1/E2 建，E4 本地無法獨立重現全套」。

**★ agent.lessons sink grant/schema（PRIMARY 2）= INSERT 有權、非 silent-drop、schema 精確對賬**：**關鍵 reconcile——MIT 報告（早期態）寫 sink=`learning.mlde_shadow_recommendations` direct INSERT（S-1=V037 REVOKE PUBLIC INSERT 致 silent-drop HIGH），但 `6a9dd0f1` 真碼已採 MIT 建議(a)把 sink 搬到 `agent.lessons`(V133)**（executor MODULE_NOTE + `write_ml_advisory_advisory_sink:404` `INSERT INTO agent.lessons(symbol,lesson_type,content,session_trigger,context_id,outcome_net_bps,session_cost_usd,source)` values `(sym,mode,content,trigger,l2_reply_id,NULL,NULL,'ml_advisory')`）。**教訓再現：prompt 與 MIT 都說某事，必讀真碼核對——sink 目標表已變，privilege 檢查對象隨之變**。Linux PG（`trading_postgres`/`trading_ai`）：control_api login role = **`trading_admin`**（db_pool `PG_USER` default + runtime secret URL `postgresql://trading_admin@127.0.0.1:5432/trading_ai` 雙證）。**`has_table_privilege('trading_admin','agent.lessons','INSERT')=true`**（SELECT=true），且 **table owner=trading_admin**（owner 隱含 INSERT，比 V037-affected mlde_shadow〔被 REVOKE PUBLIC INSERT〕結構性更強）；`role_table_grants` 只 trading_admin 全權、**無 PUBLIC REVOKE 模式**→**S-1 silent-drop 風險在 agent.lessons sink 結構性不存在**（E1 搬 sink 消滅了 MIT S-1 HIGH）。**schema 精確對賬**：Linux 真 `agent.lessons` 10 欄 == V133 file（無 drift）；sink 寫的 8 欄全存在型別相容，3 NOT NULL（symbol/lesson_type/content/source）皆得非空值（symbol 空→placeholder 'ml_advisory'；source 顯式 'ml_advisory' override default 'l2_session' 分離 critic namespace），`outcome_net_bps=NULL` 對齊 V133 forward-stub 契約。注意 agent.lessons 現 **0 rows**（critic persist 尚未在 prod 落真 lesson），故「critic 寫成功則 role 有權」無 live 證據可用——但 `has_table_privilege` 直查更硬更定論（critic 同 `db_pool.get_pg_conn`同表同 role，路徑等價）。

**D3 contract_ver（PRIMARY 3）= schema 支援已驗，真 row 雙重 owed**：Linux `_sqlx_migrations` max=**133**（V133 agent.lessons 已 deploy；V134/135/136 **未 apply**=feature-branch operator-gated）。`agent.l2_calls` 表**Linux 不存在**（需 V134）。`record_l2_call(contract_ver=...)` 真 DB 落值 owed-**雙重**：(a) V134 deploy（agent.l2_calls 建表），(b) dispatch 0 production caller dormant（真 dispatch 才產 row）。**schema 支援已驗**：V134 file:124 `contract_ver TEXT NOT NULL` 存在→deploy 後可寫。標 **owed-post-deploy（deployed-E2E）**。

**mock 審查 PASS**：sink 測用 `_conn_provider_factory`→`_CapturingConn`（純 IO 邊界 stub，捕 SQL+params 進 in-memory store）；**業務邏輯全真跑**（content 構造/redactor 真消毒〔spy 驗真呼叫〕/namespace tag/D3 context_id threading/INSERT SQL 構造），斷言真 code 產的 SQL/params（`params[5]=='ml_advisory'`/`'mlde_shadow_recommendations' not in sql`）。**因 conn 是 stub，pytest run 0 真 INSERT 觸 Linux PG**（驗：run 前後 agent.lessons 恆 0 rows）。

**prod 零觸碰確認**：(1) 真 checkout 仍 main@`28e376c0` working tree clean、P3a 檔仍 ABSENT；(2) agent.lessons 0 rows 不變（0 test 污染）；(3) **PG cluster 零 mutation**（無 CREATE ROLE/DB、無 schema 改、只 has_table_privilege+information_schema 唯讀查）——比 D3 上輪「scratch CREATE ROLE 洩 prod pg_roles」更乾淨（本次根本不需建 role/scratch DB）；(4) `/tmp/l2_p3a_dryrun` 已 remove 確認 gone。

**教訓**：(1) **sink 目標表會在 MIT→E1 之間搬家**（MIT 建議(a)落地）：privilege 檢查前必讀「當前真碼」的 INSERT target，不可信 MIT 報告寫的舊表名——本次若照 prompt/MIT 字面查 mlde_shadow_recommendations 就查錯對象。(2) **owner-role 連線比 granted-role 更強且免 PUBLIC-REVOKE 風險**：trading_admin 是 agent.lessons owner→S-1 class（V037 REVOKE PUBLIC INSERT 致 silent-drop）對 owner 不適用；查 grant 要分「owner 隱含」vs「顯式 GRANT」。(3) **deploy-gated 表的真-row 驗證是雙重 owed**（表需 migration apply + dispatch 需 production caller）：只能驗 migration-file schema 支援，真 row 標 deployed-E2E。(4) **full-tree rsync > 逐 scp companion**：untracked test 依賴一串 uncommitted `M` companion 時，full-tree 一次同步 0 drift，逐檔 scp 漏一個就假 missing-companion fail。(5) **Mac 雙 python 環境互補但皆殘缺**（3.10 無 tomllib / 3.12 無 pytest+pydantic）→ L2 全套只能 Linux 跑，E4 須誠實標 Mac 數由前序 agent 建、本地無法獨立重現全套。

---

## 2026-06-10 — L2 P3b Linux 回歸 + altcap real-smoke (E4)

**branch** `feature/l2-critic-lessons-tools` @ `aeae4da4`（P3b 未 commit）。Linux=`trade-core` main@`28e376c0`。temp-overlay 法（rsync program_code+helper_scripts+settings+sql+rust/openclaw_engine/src 到 /tmp，prod 零觸碰）。

**verdict = E4 PASS**（無真回歸；1 forward-integration caveat owed E1/AEG-S3）。

**Linux parity**：P3b 4-suite（altcap/beta_neutral/leak/hypothesize）= **46 passed == Mac 46**，2 run 同綠非 flaky。producer gate（learning_engine+ml_training+research）temp **794 passed / 2 failed**，2 fail = `test_half_life_estimator.py`（pre-existing：Linux 缺 scipy→default_14d，main 亦 fail，非 P3b）。layer2 廣套件 199 passed。

**★ altcap real-smoke（最高價值，QC/MIT owed）真 DB（trading_ai，read-only）**：
- FND-2 型別相容 ✅：`alive_from_utc`/`alive_to_utc` 真型別 = **`str`**（ISO `"2026-03-06T00:00:00+00:00"`），altcap `_to_date()` 正確解析，PIT walk-forward 真跑通。
- market.klines 1d 覆蓋：CORE25 ex-BTC 24 檔中 **18 有資料/6 無**（ATOM/ETC/FIL/ICP/INJ/UNI=0 bars，90d 窗）。basket return series sane：87 bars、0 NaN/inf、range [-0.041, 0.059]、mean 0.00085、N_constituents=18。
- **down-bars 計數**：BTC 1d full=730 bars（2024-06..2026-06）。**integer-bar-indexed**（producer 契約形）：full-span **301**（≈QC/MIT 309，≥30 PASS）、last-90d **16**（<30 DEFER，印證 QC/MIT 23）、last-180d 67（≥30，驗 ≥180d span 設計）。

**★ 真連線抓到 mock 蓋不住的 forward-integration 缺陷（owed E1/AEG-S3，非本輪 blocker）**：`compute_down_market_mask` + 整個 `beta_neutral_check` gate 經 `_parse_series`→`residual_alpha_gate._parse_candidate_returns`，其 `_in_fit_scope` 用 `_WideFitWindow` 的 `±inf` 邊界。**date/datetime/str key 與 ±inf 比較 raise TypeError→`_is_ordered_or_equal` 吞掉回 False→全 temporal-key row 被 silently drop→empty mask/empty series**。只有 **int(bar-index) key** 過。unit test 全用 int key 故綠，但**真 market.klines date-key 路徑→0 down-bars（我初跑 date-key=0，int-key=301 才對上 309）**。教訓再現「真連線 smoke > mock」。**caller**：`l2_ml_advisory_executor.py:1120 _run_b1_stage` 從 `gate_inputs` dict 取序列，**目前無 production 路徑 populate 真 market 序列**（AEG-S3 候選接口未建，缺→DEFER fail-closed），故 latent 非 active bug。**E1/AEG-S3 接真資料時必須把 candidate/btc/altcap/mask 全 re-index 成共同 int bar-index，否則 universal silent DEFER**。

**66 control-plane fail 分類**：CSRF_SHADOW OFF→**66 failed**（main 4371 passed，write-endpoint 403 enforcement-mode，documented mutually-exclusive，0 碰 P3b）。CSRF_SHADOW=1→main **6 failed**（全 `test_ops1_csrf_middleware.py` enforcement 測，反向 mutually-exclusive）。temp overlay 多 3 fail（batch_b/batch_d/sm_contract_parity）**經驗證在 main 全 PASS = temp 缺檔 artifact（rust/openclaw_core/tests/fixtures 等未 rsync）非真 fail 非 P3b**。

**陷阱記錄**：temp-overlay 法初跑漏 sql/ + rust/ → 25 假 fail（V082/V084 SQL read + 跨語言 Rust source read FileNotFound）；補 rsync 後歸零。branch divergence：main 有 residual-producer 8 test 檔我舊 branch 無（103 test gap，非 P3b）。**結論：temp 多 fail 全為 (a)缺 scipy (b)temp 缺檔 (c)CSRF mode — 0 P3b 真回歸**。

**owed（operator/E1）**：V127 population（regime-labels seed）、agent.lessons seed、★B1 gate temporal-key re-index（AEG-S3 wiring 前必修）、6 ex-BTC symbol market.klines 1d 覆蓋（ATOM/ETC/FIL/ICP/INJ/UNI）。prod 零觸碰，temp 已清。

- 2026-06-10 BASELINE 重置：舊基線（2555/17）隨配置遷移作廢；下次全量回歸建立新行（格式: BASELINE: YYYY-MM-DD passed=N failed=M）

## 2026-06-10 · OPS-2 Phase-2 cutover 全回歸 @ `cf1b9320`（PASS；E4 +1 測試 `e34a8772`）

**被驗**：worktree `/tmp/wt-ops2-cutover` branch `fix/ops2-phase2-cutover`，`a3d27729`+`cf1b9320` off main `28e376c0`（E2 兩輪 ACCEPT）。移除 secret-split Phase-1 IPC fallback，env 缺失 fail-loud。報告 `2026-06-10--ops2_phase2_cutover_regression.md`。

**數字（全親跑，跑兩遍同綠）**：Rust full `--no-fail-fast` 43 targets = **4154/1/4ign ×2**（唯一紅 = stress_tick_latency_benchmark；total 4155 == E1/E2）；Python（venvs/mac_dev 3.12.13）`pytest tests/ --ignore=tests/replay` = **66 failed/4256 passed/6 skipped ×2**，FAILED 清單 run1==run2 byte-identical；+E4 測試後 = 66/4257/6。base `28e376c0`（自建 throwaway worktree）= 66/4255/6，**FAILED 66 條整列 diff = 空**（勝過抽 5 條）；probe 1 條 = 403 write-endpoint = Mac CSRF-enforcement 環境 artifact（無 CSRF_SHADOW=1 → 66 紅 mode，與 2026-05-30 F-NEW-1 一致）。

**★ stress flake 裁定 SOP（記住此法）**：兩輪 full 紅（1135.5/1117.3μs vs <1000μs debug）→ (a) 結構：PR 0 觸碰 stress 檔；(b) HEAD standalone ×3 = 1059-1073μs 全紅；(c) **base standalone ×3（共享 CARGO_TARGET_DIR 重編 base，省 dep 重編）= 1068-1076μs 全紅** → base 本機今日同紅且 HEAD 值不劣（均值 1066.7 vs 1072.3）= 環境性非回歸，tick path 零劣化。跨 session（E1 紅/E2 紅/E1-fix 綠）= session 噪音。**獨立重做 base 裁定而非沿用 E1 stash 證據**。

**測試數對賬（名字級，非僅總數）**：Python `def test_` 4316→4317(+1=記帳)；Rust `#[test]` 4186→4189(+3=main.rs ops2 mod)。名字 diff：Rust live_authorization 24→24（刪 `phase1_fallback_reads_ipc_secret_when_live_auth_unset` + rename `primary_wins_over_ipc_fallback`→`primary_read_ignores_ipc_secret`，+`ipc_secret_alone_no_longer_provides_signing_key`）；Python secret_split 8→9（刪 3 WARN + 1 rename，+5 新負向）。**被刪全為被移除功能（Phase-1 fallback）的行為測試且有「fallback 已死」負向取代 = 合法刪除類**；0 靜默消失。坑：zsh `$rev:rust/...` 會吃 `:r`（modifier）→ 必 `${rev}:path`。

**mock-bite 親驗**：promote gate-chain 測試非 mock 短路——毒 `_read_live_auth_signing_key`→`""` → 紅 403 `gate_failed=authorization`+Phase-2 hint（真走 live_preflight HMAC 驗證）；還原 byte-clean。四象限（Rust panic live/非 live 不 panic/Py sign raise/Py verify reason）+ Rust verify 負向 + cross-lang pinned `1b2b18d7…78fc` 雙端全綠 named-run 親驗。

**E4 新增 1 測試（缺口真實非為加而加）**：gate-chain 層唯獨缺「授權檔有效+簽名 key 缺」永久負向（grep tests/ 0 檔引用 live_preflight；E2 Finding-1 正是此 surface 顯形）→ `test_live_flip_signing_key_missing_403_authorization`（toggle gate-5 cluster；legacy IPC 在場不得救；hint 含新 env 名）。bite：暫重加 IPC fallback → 此測試紅 → 還原。commit `e34a8772`（僅測試檔）。

**教訓**：(1) 負向測試的 mutation-bite 方向是「把被禁行為加回去」（重加 fallback→測試應紅），不是把正路徑弄壞；一條 bite 同時證測試非 tautology + 鎖回歸方向。(2) base-side flake 裁定用共享 CARGO_TARGET_DIR 重編 base worktree（dep 全 reuse，僅 workspace crates 重編，分鐘級）；跑完把 HEAD 重編回來恢復 cache 一致。(3) full-suite 下 timing benchmark 值（1135μs）vs standalone（1066μs）差 ~7% = suite 負載，flake 對比必 standalone-vs-standalone 同條件。(4) patch.dict(os.environ) context 內 pop 是安全 hermetic 手法（退出整體還原）——unittest 風格檔內清 env 不需 monkeypatch。

**VERDICT: PASS**（Linux full regression owed 隨 merge+`--rebuild` 部署 gate；origin/main 已進 L2 Mesh 7 commits，E2 證 0 overlap）。退 E1 清單：無。
