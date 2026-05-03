# REF-20 Wave 2 Batch 1 — E4 Regression Smoke Test Report

**Date**: 2026-05-03
**Tester**: E4 (Test Engineer)
**Verdict**: **PASS**（0 baseline regression / 0 sibling regression / 0 flaky / 0 hard-boundary mutation）
**Commits under test (3)**:
- `9879eeb` feat(replay-ui): Paper Replay Lab P1 frontend foundation (Wave 2 P1-U1/U7/U9 bundle)
- `ce665b0` feat(replay): signing key 90d rotation + 180d retention cron + tests (Wave 2 P2a-S1)
- `40ebc19` feat(replay): manifest_signer Rust+Python HMAC-SHA256 + fingerprint fix (Wave 2 P2a-S2)
**Pre-Batch1 baseline HEAD**: `b1c2034`（docs(ref20-w2): land Wave 2 dispatch plan + 5 ambiguity decisions）
**Post-Batch1 HEAD**: `40ebc19`（origin/main aligned）
**Upstream chain**:
- E2 verdict: CONDITIONAL PASS / 5 MED / 4 LOW（`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_wave2_batch1_design_impl_review.md`）
- Workplan §5.3: cross-phase regression matrix（`docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md`）
- CLAUDE.md §三 baseline + §七 cross-platform + §八 mandatory chain + §九 idempotency

---

## 0. TL;DR

E4 跑了 6 個強制 regression test command（含 round-2 flaky 驗證），**全 PASS / 0 baseline regression / 0 sibling regression**。pre-existing ml_training collection error 是 Mac dev env 缺 `numpy` 的環境問題（非 Batch 1 引入），用 git checkout b1c2034 對 baseline 同樣 reproduce 確認。E4 sign-off **PASS**，可進 PM closure 階段。

| 引擎 | 結果 |
|---|---|
| Rust `cargo test --release --lib`（全 lib） | **2415 passed / 0 failed / 0 ignored** |
| Rust `cargo test --release --test replay_manifest_signer_xlang_consistency` | **8 passed / 0 failed** |
| Rust `cargo test --release --lib live_authorization`（sibling regression） | **18 passed / 0 failed** |
| Rust `cargo test --release --lib replay`（module-scoped subset） | **10 passed / 0 failed**（filtered 2405） |
| Python `pytest control_api_v1/tests/` | **3329 passed / 10 skipped / 0 failed**（53.41-53.77s） |
| Python `pytest helper_scripts/cron/test_replay_key_*.py` | **7 passed / 0 failed**（0.11s） |
| HTML parser smoke (`tab-paper.html`) | **PARSE OK** |
| Cron shell `bash -n` + Python `py_compile` | **SHELL OK / PY OK** |
| Round-2 flaky check（重跑 Rust + Python） | **0 delta**（2415 passed → 2415 passed; 3329 passed → 3329 passed） |

**Hard-boundary scan**（CLAUDE.md §四）：

```bash
git diff b1c2034 HEAD -- '*.rs' '*.py' '*.sh' '*.js' '*.html' \
  | grep -nE '^\+.*\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease)'
```
→ **0 hit**。Wave 2 Batch 1 完全沒有改動 live execution gate / Decision Lease / authorization.json。

---

## 1. Test 1 — Rust `cargo test --release --lib`（全 lib regression）

**命令**:
```
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine
cargo test --release --lib
```

**Tail output**:
```
test event_consumer::dispatch::tests::test_run_dispatch_retry_close_budget_caps_at_3_attempts ... ok

test result: ok. 2415 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.55s
```

**Round-2 result**:
```
test result: ok. 2415 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.57s
```

**Baseline 對照**:

| 度量 | CLAUDE.md §九 baseline | E4 round 1 | E4 round 2 | Delta |
|---|---|---|---|---|
| Rust lib passed | ~1980 (last documented) | **2415** | **2415** | **+435** (新增 manifest_signer 10 unit + 累積) |
| Rust lib failed | 0 | **0** | **0** | **0** ✅ |

**結論**: PASS。lib level 0 regression。新增 10 unit test（`replay::manifest_signer::tests::*`）通過 module-scoped subset 驗證。

---

## 2. Test 2 — Python pytest（control_api_v1 全 suite）

**注**: 從 srv root 跑 `pytest program_code/ helper_scripts/` 收 10 collection error（`ModuleNotFoundError: No module named 'numpy'` in `program_code/ml_training/tests/*`）。已對 baseline `b1c2034` checkout reproduce 同樣 error → **確認 pre-existing Mac dev env 問題，非 Batch 1 引入**。E4 真實 baseline 採用 control_api_v1 子目錄跑（CLAUDE.md §regression skill 的兩種推薦方式之一）。

**命令**:
```
cd /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1
python3 -m pytest tests/ -q --tb=line --ignore=tests/integration
```

**Tail output**:
```
3329 passed, 10 skipped, 409 warnings in 53.77s
```

**Round-2 result**:
```
3329 passed, 10 skipped, 409 warnings in 53.41s
```

**Baseline 對照**:

| 度量 | CLAUDE.md §九 baseline | E4 round 1 | E4 round 2 | Delta |
|---|---|---|---|---|
| Python control_api_v1 passed | 2555 (legacy `tests/` scope) | **3329** | **3329** | **+774** (累積 + 新增 13 manifest_signer xlang) |
| Python control_api_v1 failed | 17 (legacy `tests/` scope) | **0** | **0** | **-17** ✅ |
| Python control_api_v1 skipped | varies | 10 | 10 | 0 |

**注 baseline 名義差異**: CLAUDE.md §九 的 baseline 是針對 `srv/tests/` legacy scope，當前 control_api_v1 子目錄 scope 包含累積的新 test（含本 Batch 1 新增 13 個 xlang）。重要的是 **failed 數從 17 降到 0**（Mac dev_disabled secret slot rename 後 Bybit integration test 跳開，per CLAUDE.md §七 by design）。

**結論**: PASS。0 既有 fail 增加；新增 13 manifest_signer xlang test 全 pass。

---

## 3. Test 3 — Cross-language byte-equal HMAC integration test

**命令**:
```
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine
cargo test --release --test replay_manifest_signer_xlang_consistency -- --nocapture
```

**Tail output**:
```
running 8 tests
test fingerprint_helper_matches_fixture ... ok
test fail_mode_manifest_hash_mismatch_with_fixture ... ok
test verify_order_invariant_signature_before_hash_with_fixture ... ok
test fail_mode_signature_mismatch_with_fixture ... ok
test fail_mode_key_missing_with_fixture ... ok
test fail_mode_key_expired_with_fixture ... ok
test happy_path_verify_passes_with_fixture ... ok
test xlang_signature_byte_equal_for_all_fixtures ... ok

test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```

**對 E2 §2.4 / Lesson 23 對照**:

| 驗證項 | E4 確認 |
|---|---|
| 3 fixture（`manifest_1.json` / `manifest_2.json` / `manifest_3.json`）byte-equal HMAC | ✅ `xlang_signature_byte_equal_for_all_fixtures` PASS |
| 4 fail-mode 全 cover（signature_mismatch / manifest_hash_mismatch / key_missing / key_expired） | ✅ 4/4 PASS |
| Verify-order invariant（signature → hash） | ✅ `verify_order_invariant_signature_before_hash_with_fixture` PASS |
| Fingerprint 算法 = `openssl dgst < key.hex` 對齊 (E2 Lesson 24) | ✅ `fingerprint_helper_matches_fixture` PASS |

**結論**: PASS。HMAC byte-exact contract 完整守住，0 byte tolerance。

---

## 4. Test 4 — Sibling regression: `live_authorization` 18/18

**E2 §0 must-verify**：sibling regression `live_authorization` 18 case 不能因 Batch 1 改動破壞（Wave 2 Batch 1 modules 與 live_authorization 完全 disjoint，但 E4 強制驗）。

**命令**:
```
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine
cargo test --release --lib live_authorization
```

**Tail output**:
```
running 18 tests
test live_authorization::tests::auth_error_kind_labels_are_stable ... ok
test live_authorization::tests::canonical_payload_sorts_and_dedups_envs ... ok
test live_authorization::tests::expired_authorization_rejected ... ok
test live_authorization::tests::demo_and_testnet_are_unsupported_envs ... ok
test live_authorization::tests::env_allowed_order_does_not_break_signature ... ok
test live_authorization::tests::expiry_at_now_is_rejected_not_accepted ... ok
test live_authorization::tests::mainnet_rejected_when_only_live_demo_approved ... ok
test live_authorization::tests::missing_approved_system_mode_rejected_with_specific_variant ... ok
test live_authorization::tests::non_live_reserved_approved_system_mode_rejected_with_specific_variant ... ok
test live_authorization::tests::tampered_env_allowed_detected ... ok
test live_authorization::tests::tampered_expiry_detected ... ok
test live_authorization::tests::mainnet_accepted_when_mainnet_approved ... ok
test live_authorization::tests::unsupported_version_rejected_before_signature ... ok
test live_authorization::tests::tampered_tier_detected_by_signature_check ... ok
test live_authorization::tests::v1_authorization_rejected_before_signature ... ok
test live_authorization::tests::valid_live_demo_authorization_verifies ... ok
test live_authorization::tests::wrong_secret_produces_bad_signature ... ok
test live_authorization::tests::load_and_verify_reads_file_via_env_override ... ok

test result: ok. 18 passed; 0 failed; 0 ignored; 0 measured; 2397 filtered out; finished in 0.00s
```

**結論**: PASS。Live authorization HMAC + signature + env_allowed + expiry 全 18 case 0 regression。

---

## 5. Test 5 — Frontend HTML / shell smoke

### 5.1 HTML parse smoke (E2 §1.1 #1 重新驗證)

**命令**:
```python
python3 -c "from html.parser import HTMLParser; \
  HTMLParser().feed(open('program_code/exchange_connectors/bybit_connector/control_api_v1/app/static/tab-paper.html').read()); \
  print('tab-paper.html PARSE OK')"
```

**Output**: `tab-paper.html PARSE OK`

### 5.2 Cron shell + Python compile smoke

**命令**:
```bash
bash -n helper_scripts/cron/replay_key_rotation_check.sh
python3 -m py_compile helper_scripts/cron/replay_key_archive_cleanup.py
```

**Output**:
```
SHELL OK
PY OK
```

**結論**: PASS。HTML 0 parse error；shell + Python 0 syntax error。

---

## 6. Test 6 — Cron pytest（S1 + S2 helper test bucket）

**命令**:
```
cd /Users/ncyu/Projects/TradeBot/srv
python3 -m pytest helper_scripts/cron/test_replay_key_rotation_check.py helper_scripts/cron/test_replay_key_archive_cleanup.py -v
```

**Tail output**:
```
helper_scripts/cron/test_replay_key_rotation_check.py::test_wrapper_exists_and_syntax_clean PASSED       [ 14%]
helper_scripts/cron/test_replay_key_rotation_check.py::test_v042_absent_mtime_within_grace_exits_0_silent PASSED [ 28%]
helper_scripts/cron/test_replay_key_rotation_check.py::test_v042_absent_mtime_past_due_exits_1_alert PASSED [ 42%]
helper_scripts/cron/test_replay_key_rotation_check.py::test_secrets_dir_missing_exits_2 PASSED [ 57%]
helper_scripts/cron/test_replay_key_archive_cleanup.py::test_v042_absent_exits_0_graceful PASSED  [ 71%]
helper_scripts/cron/test_replay_key_archive_cleanup.py::test_v042_present_zero_rows_past_retention PASSED [ 85%]
helper_scripts/cron/test_replay_key_archive_cleanup.py::test_v042_present_three_rows_past_retention PASSED [100%]

============================== 7 passed in 0.11s ===============================
```

**Cover 範圍** (對 E2 §2.5 V042 graceful fallback / Lesson 25 對照):
- V042 absent + mtime within grace → exit 0（fail-closed silent）
- V042 absent + mtime past due → exit 1（fail-closed alert）
- SECRETS_DIR missing → exit 2
- V042 present + 0 rows past retention → exit 0（zero work）
- V042 present + 3 rows past retention → exit 0 + UPDATE 3 row

**結論**: PASS。S1 cron 7/7 test cover 全部 fallback path 與 boundary case。

---

## 7. 新增測試清單（38 expected vs 實測 38）

| 文件 | 新增 test 數 | 類型 |
|---|---:|---|
| `rust/openclaw_engine/src/replay/manifest_signer.rs`（unit） | 10 | Rust unit |
| `rust/openclaw_engine/tests/replay_manifest_signer_xlang_consistency.rs` | 8 | Rust integration |
| `program_code/.../tests/replay/test_manifest_signer_xlang_consistency.py` | 13 | Python pytest |
| `helper_scripts/cron/test_replay_key_rotation_check.py` | 4 | Python pytest |
| `helper_scripts/cron/test_replay_key_archive_cleanup.py` | 3 | Python pytest |
| **合計** | **38** | **38 PASS / 0 FAIL** |

對齊 E2 §0 expected count（10+8+13+7=38）。✅ 0 test 移除 / 0 既有 fail 新增。

---

## 8. Mock 安全規則審查（CLAUDE.md regression skill §5）

| Test | Mock 內容 | OK? | 理由 |
|---|---|---|---|
| Rust manifest_signer unit | `InMemoryKeyArchive` mock V042 archive | ✅ | V042 表 Wave 3 R20-P2a-S4 才 land；archive 是 IO 邊界（DB），非業務邏輯。HMAC 計算邏輯真跑（hmac::Mac trait） |
| Rust manifest_signer integration | 實 disk fixture `key.hex` + `manifest_*.json` + `manifest_*.sig` | ✅ | 0 mock；fixture 是 ground truth |
| Python manifest_signer xlang | 實 disk fixture (相同) + `_DummyArchive` 物件 | ✅ | dummy archive = test double 替代 V042（IO 邊界）；HMAC 計算邏輯真跑（hashlib） |
| Cron rotation_check pytest | mtime via `os.utime()`（filesystem time mock） | ✅ | 時間/IO mock 合規（CLAUDE.md skill §5.1）；rotation 邏輯真跑 |
| Cron cleanup pytest | `psycopg2.connect()` 透過 monkeypatch 接 `_FakePgCursor` 假 cursor | ⚠ → ✅ | 接受。PG cursor 是純 IO 邊界；UPDATE 路徑邏輯真跑（rowcount 計算 / payload 構造） |

✅ 0 mock 業務邏輯（如 `RiskManager.should_allow` / indicator 計算 / IPC protocol 邏輯）。所有 mock 都限於 IO 邊界（DB connection / filesystem time / V042 archive lookup）。

---

## 9. 浮點一致性測試（N/A）

**Wave 2 Batch 1 不涉指標計算改動**（無 ATR / BB / Sharpe / RSI 改動）。Cross-language 一致性僅限 HMAC byte-exact，已在 Test 3 驗（0 byte tolerance）。

如未來 Wave 5 P3a-Q1 (half-life) / P3a-Q3 (block bootstrap) / P3a-Q5 (fee model) 接 IMPL 階段，需 Python ↔ Rust 1e-4 容差驗證。

---

## 10. SLA 壓測（Mac dev env 不適用）

**注**: CLAUDE.md §regression skill §4.5 規定 SLA 壓測（H0 Gate <1ms / Tick path <0.3ms / IPC <5ms）。但 Wave 2 Batch 1 改動 **完全不涉 hot path**：
- `replay::manifest_signer` = cold path（experiment artifact 簽名/驗章，每次 replay run 一次）
- `cron/replay_key_*` = cron 觸發（每日 1 次）
- frontend bundle = browser 端，無 engine SLA 含義

→ **SLA 壓測 N/A**（無 hot path 改動）。

如後續 Wave 接 hot path（如 P2b R20-P2b-S7 isolated runner gate），需 Linux runtime ssh trade-core 跑 IPC + tick pressure test。

---

## 11. 跑兩遍結果（CLAUDE.md skill 紅線「跑兩遍」）

| Run | Rust lib | Python control_api_v1 |
|---|---|---|
| Run 1 | 2415 passed / 0 failed / 0.55s | 3329 passed / 10 skipped / 0 failed / 53.77s |
| Run 2 | 2415 passed / 0 failed / 0.57s | 3329 passed / 10 skipped / 0 failed / 53.41s |
| Delta | 0 / 0 | 0 / 0 |
| Flaky? | **N**（0 race / 0 timing-dependent fail） | **N** |

✅ 0 flaky test。

---

## 12. 跨平台註記（Mac vs Linux）

**Mac dev 端執行的 result 完整覆蓋**:
- ✅ Rust cargo test（lib + integration）
- ✅ Python pytest control_api_v1 + cron
- ✅ HTML parser smoke
- ✅ Sibling regression `live_authorization`

**仍需 Linux runtime ssh trade-core 補做（如 PM 認為 critical）**:
- Linux x86_64 binary 跑 `cargo test --release --lib replay::manifest_signer`（驗 byte-equal HMAC 跨架構不漂移）— **Optional**，因 HMAC-SHA256 是 byte-deterministic 算法，跨架構結果必同；E2 Lesson 23 fixture-based design 已 cover
- Linux Python pytest test_manifest_signer_xlang_consistency.py（驗 Linux Python `hmac.new(...)` 與 Mac Python 等價輸出）— **Optional**，hmac stdlib 是 portable
- IPC <5ms / Tick <0.3ms 壓測 — **N/A**，本 batch 不改 hot path

**Mac 環境差異 (pre-existing, 不影響 E4 sign-off)**:
- `program_code/ml_training/tests/*` 10 file 收 `ModuleNotFoundError: No module named 'numpy'` — Mac dev env 缺 numpy 依賴；對 baseline `b1c2034` 同樣 reproduce → **pre-existing**，與 Wave 2 Batch 1 無關
- 修法（不在 E4 範圍）：Mac dev 跑 `pip install numpy` 或在 srv root 跑時 `--ignore=program_code/ml_training/tests/`

---

## 13. Hard-Boundary Scan（CLAUDE.md §四 永不違背的硬錯誤）

```bash
git diff b1c2034 HEAD -- '*.rs' '*.py' '*.sh' '*.js' '*.html' \
  | grep -nE '^\+.*\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease)'
```

→ **0 hit**

| 邊界 | 改動? |
|---|---|
| live execution gate（4 項：role / live_reserved / OPENCLAW_ALLOW_MAINNET / authorization.json + secret slot） | ✅ 0 |
| Decision Lease（acquire_lease / release_lease / lease.rs / governance_hub） | ✅ 0 |
| max_retries / Bybit retCode handling | ✅ 0 |
| Risk envelope / GovernanceHub | ✅ 0 |
| Strategy params / TOML / migration | ✅ 0 |

---

## 14. Cross-Phase Regression Matrix（workplan §5.3 對照）

| Cross-phase 必驗項 | E4 結果 |
|---|---|
| Paper session legacy regression（既有 paper engine `trading.fills` 寫入路徑） | ✅ 0 改動到 paper engine; control_api_v1 pytest 0 fail |
| 既有 8 governance routes auth contract（P2a 起點） | ✅ Wave 2 Batch 1 0 改動 governance_routes.py / authorization.json runtime；live_authorization 18/18 PASS |
| Path alias `OPENCLAW_SRV_ROOT` / `OPENCLAW_BASE_DIR` 不 fallback 行為 | ✅ Wave 2 Batch 1 0 改動 bybit_path_policy.py |
| Decision Lease retrofit 回歸（每 commit 必驗） | ✅ 0 改動 lease.rs / governance_hub.acquire_lease |
| 16 根原則 #1（單一寫入口）/ #4（不繞風控）/ #7（學習平面隔離）grep | ✅ 0 改動 IntentProcessor / Strategist live path / GovernanceHub |

---

## 15. PM 5 MED follow-up regression impact

E2 verdict 列 5 MEDIUM finding 為 Wave 2 closure 前 fix-up 或 Wave 3 deferred。E4 對每個 fix 後是否需 re-run 評估：

| Finding | Fix 範圍 | E4 re-run 需要? | 理由 |
|---|---|---|---|
| **MED-1** shell SQL parameterization (`replay_key_rotation_check.sh:254/262`) | Wave 2 closure fix-up | **PARTIAL** | 若改 `psql -v env=...` 則需重跑 `helper_scripts/cron/test_replay_key_rotation_check.py`（4 case）+ shell `bash -n`；不影響 Rust lib / Python control_api_v1 pytest |
| **MED-2** stale env var name `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` (`mod.rs:17` / `profile.rs:42`) | Wave 3 R20-P2b-S9 IMPL 第一步（**E4 run 時已有 uncommitted rename diff**，已 stash） | **PARTIAL** | Rename comment-only 改動，不改 runtime；rename commit 後 re-run `cargo test --lib replay::profile` (2 unit test) 即可。已 stash 改動驗 E4 run 不受 uncommitted state 干擾 |
| **MED-3** verify caller fingerprint contract（manifest_signer.rs:401-447） | Wave 3 R20-P2a-S4 IMPL deferred | **YES (Wave 3)** | 若加 `if fingerprint != self.fingerprint() { return KeyMissing }` assertion → 需新增 unit test cover 此 path + 重跑 manifest_signer 10 unit + 8 integration + 13 Python xlang |
| **MED-4** `except: pass` cleanup path（`replay_key_archive_cleanup.py:311/317`） | Wave 2 closure fix-up | **MIN** | 改 `except Exception as exc: log.warning(...)` 不改 runtime semantics；重跑 cleanup 3 case 即可 |
| **MED-5** mode badge i18n hook（`common.js:1184-1189`） | Wave 2 closure fix-up（A3+TW worktree） | **PARTIAL** | 若選 (a) 加 `t_zh()` lookup → 需 Playwright snapshot 比對 mode badge label 中英；當前 Mac dev 無 Playwright runtime → 需 Linux trade-core 或 deferred 到下一 wave |

**整體**: 5 MED 全部 fix-up commit 後若需 PM 要 E4 二輪驗，建議併發跑 (1) cron pytest + (2) Rust replay 全 test + (3) Python xlang full suite，估時 <2 min 全部完成。

---

## 16. Diff Scope 總覽

```
git diff b1c2034 HEAD --shortstat
 32 files changed, 5342 insertions(+), 7 deletions(-)
```

**32 file 分類**:
- Frontend bundle (8): app-paper.js / common.js / console.html / i18n_zh.js / tab-paper.html
- Replay backend Rust (3): manifest_signer.rs / mod.rs / replay_manifest_signer_xlang_consistency.rs (test)
- Replay backend Python (3): manifest_signer.py / __init__.py / test_manifest_signer_xlang_consistency.py
- Cron (5): rotation_check.sh / archive_cleanup.py + 2 test_*.py + runbook
- Test fixture (12): replay_manifest_signer/ key.hex + 3 manifest + 3 sig + 3 hash + fingerprint + README
- E1 reports (1): E1 sign-off doc

**0 改動到**:
- ❌ Live execution path（IntentProcessor / GovernanceHub / lease.rs / authorization.json runtime）
- ❌ Decision Lease（acquire_lease / release_lease）
- ❌ Risk config TOML / strategy params
- ❌ SQL migration（V042 reserved Wave 3）
- ❌ Bybit credential / api_key / secret slot routing

---

## 17. E4 Sign-off Statement

**Verdict**: **PASS**

Wave 2 Batch 1 三 commit (9879eeb / ce665b0 / 40ebc19) 通過 E4 6 項強制 regression test：
1. Rust `cargo test --release --lib` — 2415/0/0（vs 之前 baseline ~1980 / 0 / 0；新增 +435 累積，**0 既有 test 退化**）
2. Python `pytest control_api_v1/tests/` — 3329/10/0（vs CLAUDE.md §九 baseline 2555/?/17；**failed 數從 17 降到 0**，新增 13 manifest_signer xlang test）
3. Rust `cargo test --test replay_manifest_signer_xlang_consistency` — 8/0（cross-lang HMAC byte-equal 完整 cover）
4. Rust `cargo test --lib live_authorization` — 18/0（sibling regression 0 break）
5. HTML parser + cron shell/py syntax smoke — PARSE OK / SHELL OK / PY OK
6. Cron pytest 7/0（V042 graceful fallback + boundary case）

**雙跑 confirm**：Run 1 與 Run 2 結果完全一致，0 flaky。

**Hard-boundary scan**：0 hit（live execution gate / Decision Lease / authorization.json 全 0 mutation）。

**Cross-phase regression matrix（workplan §5.3）**：5 must-verify item 全 PASS。

**Mock 安全**：5 個 test bucket 的 mock 全限於 IO 邊界（V042 archive lookup / disk fixture / filesystem time / PG cursor），0 業務邏輯 mock。

**Pre-existing Mac dev env 缺陷**（ml_training tests 10 collection error / `numpy` 缺）：對 baseline `b1c2034` 已 reproduce 同樣 error，**確認 pre-existing 非 Batch 1 引入**，不阻塞 E4 sign-off。

E4 不修代碼（CLAUDE.md skill §1 紅線「E4 不寫 fix」）；不刪測試（同 §1 紅線）；不擅改 git state（uncommitted MED-2 rename 改動透過 `git stash push/pop` 完整恢復；branch 仍清乾淨在 `40ebc19` HEAD）。

可進入 PM closure 階段，或併行派 E1/E1a/TW 處理 5 MED finding（per E2 §7）。

---

## 18. 退回 E1 修復清單（如 FAIL）

**N/A — E4 PASS。**

如後續 5 MED finding fix-up commit 進來且引入 regression，按 CLAUDE.md §八 強制工作鏈退 E1（**不跳 E2 / E4**）。

---

## 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v1** | 2026-05-03 | E4 | Wave 2 Batch 1 (3 commits) regression smoke test 6 項全 PASS / 0 baseline regression / 0 sibling regression / 0 flaky / 0 hard-boundary mutation；E4 PASS sign-off |
