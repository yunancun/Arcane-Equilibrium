# REF-20 Sprint 1 Task Partition + Interface Design — PA 主筆

**日期：** 2026-05-03
**Owner：** PA
**Sprint scope：** 4 並行 Track（A/B/C/D）解 19 P0 + 修 PA 自身 W1 派發 schema drift
**Read-only：** 不寫業務碼，僅派發/接口/依賴/風險

---

## §1. Track 全景與並行依賴 DAG

```
                ┌─────────────────────────────────────┐
   START ──┬──→ │ Track D (V049/V050/V051 + redirect)│ ──┐
           │    └─────────────────────────────────────┘   │
           │                                              ↓ schema land
           ├──→ Track A (spawn argv schema 修)  ←─────────┤
           │                                              │
           ├──→ Track B (Rust manifest 簽名 verify)       │ 共用 fixture
           │                                              │
           └──→ Track C (Python /replay/* 3 安全洞修)     │
                                                          ↓
                            E4 cross-track integration smoke
```

**依賴關鍵：** Track D 必先做（schema 是其他三 Track 寫入靶子）。Track A/B/C 在 D land schema 後可全並行；A 與 C 雖同檔（route_helpers + replay_routes）但改點區段不同 → 同 E1 連 commit、不同 E1 並行皆可。Track B 純 Rust → 與 Python 三 track 完全解耦。

---

## §2. Track-by-Track 派發

### Track D — V049/V050/V051 schema 補造 + V045/V046 FK redirect（最高優先 / 阻塞他 3 Track）

**E1 task 數：3 並行 + 1 串行 = 共 4 task（單一 E1 連跑或 ≤3 E1 並行）**

| Task ID | 路徑 | 範圍 | 並行 | 預估 |
|---|---|---|---|---|
| T-D1 | `srv/sql/migrations/V049__replay_experiments.sql`（新建）| V3 §4.1 22 column 全造（experiment_id PK / parent_experiment_id 自參考 / runtime_environment / engine_binary_sha conditional NOT NULL / 3 對 window timestamptz / oos_embargo_seconds / total_candidates_K / manifest_jsonb + manifest_hash + manifest_signature + signature_key_ref / status enum / output_policy_jsonb 等）+ Guard A/B/C + window 排他約束（CHECK start<end + EXCLUDE USING gist tstzrange `&&` 為三 window 加，需 `CREATE EXTENSION IF NOT EXISTS btree_gist`）+ 雙語 MODULE_NOTE | A | 1 day |
| T-D2 | `srv/sql/migrations/V050__replay_simulated_fills.sql`（新建）| V3 §4.1 17 column 全造（sim_fill_id PK / experiment_id FK to V049 / intent_id / decision_lease_id / idempotency_key / ts_ms / symbol / strategy_name / side / qty / price / fee / fee_rate / liquidity_role / evidence_source_tier / execution_model_version / ci_low/mid/high_bps / payload jsonb）+ FK CASCADE to `replay.experiments(experiment_id)` + CHECK liquidity_role enum + Guard A/B/C + 雙語 | A（依賴 T-D1 land） | 0.75 day |
| T-D3 | `srv/sql/migrations/V051__mlde_evidence_source_guard_retrofit.sql`（新建）| 對 `learning.mlde_shadow_recommendations` 補 `replay_experiment_id UUID` + `manifest_hash TEXT` 兩欄；ADD 雙路 CHECK constraint per V3 §4.2 L220-234（real_outcome NULL/replay-derived NOT NULL）；FK `replay_experiment_id → replay.experiments(experiment_id)`（V049 land 後）；Guard B 驗 V038/V039/V040 已 land + 新欄不存在；雙語 | A（依賴 T-D1） | 0.5 day |
| T-D4 | `srv/sql/migrations/V052__replay_run_state_artifacts_fk_redirect.sql`（新建，**不**改 V045/V046 file）| 對 V045 `replay.run_state` 加 FK `manifest_id → replay.experiments(experiment_id) DEFERRABLE INITIALLY DEFERRED`；對 V046 `replay.report_artifacts` 加 FK `experiment_id → replay.experiments(experiment_id) ON DELETE CASCADE`；ALTER ADD CONSTRAINT IF NOT EXISTS pattern；Guard B 驗 V045+V046+V049 三表都在；雙語 | S（必後 T-D1 + T-D2） | 0.5 day |

**並行/串行：** T-D1 起頭做 → T-D2/T-D3 並行（兩檔不衝突）→ T-D4 殿後（須等 V049 表存在加 FK）。
**禁改 V045/V046 file**：避免再撞 P0 sqlx hash drift（memory `project_2026_05_02_p0_sqlx_hash_drift.md`）；FK 用 V052 ALTER ADD 路徑。
**REF-20_RESERVATION.md 更新**：T-D 完成後 PM 同 commit 把 V049/V050/V051/V052 row 從 `reserved buffer` → `land`，附 task ID。
**Idempotency**：每 V### file 在 Mac dev `psql -f V### -d <test_db>` 跑 2 次第二次 0 RAISE（Guard B 偵測 column exists + type 對即 NOTICE skip）。

---

### Track A — spawn argv schema 修（E3-P0-3，解封整個 IMPL 從未跑過根因）

**E1 task 數：1 task（同 E1 跨檔連改）**

**3 個必須回答的決策：**

1. **CLI flag 對齊方向**：**Python 改用 `--manifest <path>` + `--output-dir <path>` 對齊 Rust**（不是 Rust 加 alias）。
   - 理由：Rust cli.rs 已有完整測試（11 unit test PASS）+ POSIX 風格 + workplan §4 boundary report 已凍結 forbidden-list；改 Rust 會破 boundary。
   - 副作用：Python 端要把 `manifest_id<UUID>` 改傳「manifest fixture file 絕對路徑」；fixture 路徑由 Python 端在 INSERT V045 後寫 `/tmp/openclaw/replay/<run_id>/manifest.json`（`OPENCLAW_DATA_DIR/replay/<run_id>/`）+ key.hex（Track B 仍允此 fallback）。

2. **`--run-id` 在 Rust 不必要**：V045 PK `run_id` Python 端 server-side gen（`uuid.uuid4().hex`），不需 caller 傳。Rust runner 從 manifest 內 read（manifest 內 embed `run_id` 字段或從 `output-dir` basename derive）。
   - 推薦：manifest JSON 加 `run_id` 字段（Rust 已用 `serde_json::from_str` 解析整 manifest，加欄位無破壞性）。

3. **spawn 後 poll 確認 alive 再 INSERT 'running' 是 Python 責任**：當前 INSERT `status='starting'` → spawn → UPDATE `'running'` 流程（route_helpers L266-271 + replay_routes L522-578）已 sequence 對；**真正 bug 是 spawn 失敗 Rust binary exit non-zero，但 Python 沒 wait poll**。
   - 修復：spawn 後 `await asyncio.sleep(1.5)` + `proc.poll()` 檢查；returncode is not None 且 ≠ 0 → 走 `UPDATE status='failed' exit_code=<code> cancel_reason='spawn_argv_mismatch:exit=<rc>'` 路徑（已存在於 L550-565，新加 poll 之後分支即可）；returncode is None → `UPDATE status='running'`（既有 L569-577）。

**派發（單 E1 連 commit）：**

| 改點 | 路徑 | 行 | 方向 |
|---|---|---|---|
| 1 | `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py` | L266-271 | `argv` 改成 `["--manifest", str(manifest_fixture_path), "--output-dir", str(output_dir)]`；`spawn_replay_runner` 簽名加 `manifest_fixture_path: Path` 參數；移除 `manifest_id` 與 `run_id` 直接 argv 傳遞（仍當 logging 用） |
| 2 | `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py` | L498-577 | INSERT V045 status='starting' 後、spawn 前先寫 manifest fixture 到 `output_dir / "manifest.json"`（含 `run_id` 字段）+ key.hex；spawn 後加 `await asyncio.sleep(1.5)` + `proc.poll()` 失敗 → UPDATE failed 帶 exit_code |
| 3 | `srv/rust/openclaw_engine/src/bin/replay_runner.rs` | manifest struct（L335-362）| `ReplayManifest` struct 加 `#[serde(default)] pub run_id: Option<String>` 欄位（向後相容，None 時 fallback 從 output_dir basename 取）|

**E2 必查 3 點：**
- argv 改後 `subprocess.Popen(argv, env=child_env, ...)` env whitelist 不變（`SUBPROCESS_ENV_WHITELIST` L275-279 不洩 secrets）
- `manifest_fixture_path` 必在 `OPENCLAW_DATA_DIR/replay/<run_id>/` 內（路徑遍歷防護，不接受 caller 直接傳路徑）
- poll timeout 1.5s 不阻塞 FastAPI event loop（用 `asyncio.sleep` + `proc.poll()` 同步檢查 returncode 即可，**不用** `proc.wait()`）

---

### Track B — Rust manifest signature 路徑修（E3-P0-1）

**E1 task 數：1 task（純 Rust，1 檔）**

**3 個必須回答的決策：**

1. **改 verify 輸入而非重簽結果**：當前 `replay_runner.rs:L448-461` `signer.sign(canonical_body) → signer.verify(canonical_body, &body_hash, &signature_hex, ...)` 是 tautology。修改方向：
   - L455 刪除 `let signature_hex = signer.sign(canonical_body);`（不重簽）
   - L454 `let body_hash = compute_body_hash(canonical_body);` 改用 `manifest.manifest_hash` 為 expected（並比對 `compute_body_hash(canonical_body)` 與 `manifest.manifest_hash` 是否相符；不符即 `Err("manifest_hash_mismatch: declared=<x> actual=<y>")`）
   - L456-462 `signer.verify(canonical_body, &manifest.manifest_hash, &manifest.signature, &fingerprint, &archive)` 用 manifest 自帶的 signature + hash 為 expected
   - L345/L349 `#[allow(dead_code)]` 移除（兩字段現在 read 為 verify 輸入）

2. **key.hex 缺失改 hard error**：當前 L404-411 `if !key_hex_path.exists() { eprintln!(warning); return Ok(manifest); }` 是 fail-open 漏洞。
   - 修改：`return Err("replay_runner: sibling key.hex missing at <path>; production path requires V042 SQL archive (Wave 6 deploy) — fail-closed".into());`
   - **但 Track D 不含 V042**（V042 reserved 至 Wave 3 但 PM 未派；Track B 改 hard error 後 dev 環境必須有 sibling key.hex）。

3. **與 V042 archive deploy 時序銜接**：V042 真 land 前的 production 路徑 → 走 sibling key.hex（所有 fixture 都有）；V042 land 後 → 改用 SQL-backed archive。
   - **Sprint 1 範圍只做 fail-closed key.hex hard error**；V042 SQL archive integration 是 Wave 6 任務（不在 Sprint 1）。
   - Track B 完成後狀態：dev / fixture 路徑 100% verify；production 路徑暫時阻塞於 sibling key.hex availability（V042 deploy 前 operator 必須在 manifest 旁手動放 key.hex —— 這是已知 P1，Wave 6 ETA 2026-05-15-之後）。

**派發（單 E1）：**

| 改點 | 路徑 | 行 | 方向 |
|---|---|---|---|
| 1 | `srv/rust/openclaw_engine/src/bin/replay_runner.rs` | L345-361 | 移除 `signature` + `manifest_hash` 兩 `#[allow(dead_code)]` 標記 |
| 2 | 同上 | L386-411 | `if !key_hex_path.exists()` 從 `eprintln + return Ok` → `return Err("manifest_signer_key_missing: ...")` |
| 3 | 同上 | L448-470 | 刪除 `signer.sign(canonical_body)` line + 改 `verify` 用 manifest 自帶 `manifest.signature` + `manifest.manifest_hash` 為 expected；新增 `compute_body_hash(canonical_body) != manifest.manifest_hash → Err` 分支（manifest_hash_mismatch）|
| 4 | 同上 | tests mod | 加 unit test：(a) signature_mismatch fixture（改 1 byte 簽名）→ Err；(b) hash_mismatch fixture → Err；(c) key_missing fixture → Err；(d) happy path 仍 PASS |

**E2 必查 3 點：**
- 確認 `compute_body_hash` 對 `raw.as_bytes()` 與 Python sibling signer 的 canonicalisation byte-equal（V3 §6.2 sorted-keys serde_json）；若 Mac/Linux 序列化差 1 byte → 必走 byte-stripped canonical body 重算路徑
- `manifest.signature` 是 hex string，verify 內部 `hex::decode` 失敗的 mode → `signature_format_invalid`（4 fail-mode 之一，V3 §5）
- T-B 修完不可破壞 `tests/fixtures/replay_manifest_signer/` 既有 fixture（fixture 內 manifest 必有 signature + manifest_hash + key.hex 鄰旁）

---

### Track C — Python `/replay/*` 3 安全洞修（E3-P0-2 + P0-4 + P0-5）

**E1 task 數：1 task（同 E1 連 commit；3 改點獨立 endpoint，無共用 helper 衝突）**

**3 個必須回答的決策：**

1. **`OPENCLAW_REPLAY_VERIFY_TEST_KEY` 改 release-profile feature gate**：env var 在 production 仍生效是 attacker-control surface（attacker 設 env → seed 假 InMemoryKeyArchive → 任意簽假 manifest 都過 verify）。
   - 修復方向：L1259 加 guard：
     ```python
     if os.environ.get("OPENCLAW_RELEASE_PROFILE", "").lower() == "live":
         # Production / live profile: test key MUST NOT be honored.
         test_key_hex = ""
     else:
         test_key_hex = os.environ.get("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "")
     ```
   - 即使 attacker 設 `OPENCLAW_REPLAY_VERIFY_TEST_KEY` 也被 live profile 強制清空。
   - 進一步：startup 檢查 `OPENCLAW_RELEASE_PROFILE=live` 時必須 raise 若 `OPENCLAW_REPLAY_VERIFY_TEST_KEY` 在 environ（fail-closed boot guard）。

2. **`os.kill(pid, SIGTERM)` 加 process identity 校驗**：當前 L847-864 任意 pid 寫進 V045 `subprocess_pid` → SIGTERM 給系統任意 pid（PID reuse / DB 注入 / race 三路徑都打）。
   - 修復方向：先 `psutil.Process(pid).cmdline()` → 取 argv list → 驗 `argv[0].endswith('replay_runner')` 或 `'replay_runner' in ' '.join(argv)`（Linux）；macOS `psutil` 同 API。
   - PID reuse 邊界：psutil API 對「pid 已死、新 process 復用 pid」會回新 cmdline（不是舊的）→ 仍會 reject（cmdline 不含 `replay_runner`）→ 安全。
   - 額外保護：cmdline check 失敗 → 不送 SIGTERM、UPDATE V045 `cancel_reason='pid_identity_mismatch:got=<cmdline>'` 標記後 commit。

3. **`replay:read:any` scope 用既有 `_require_replay_admin`** + IDOR/路徑遍歷修：
   - **IDOR**：L993 `get_replay_report(experiment_id)` 缺 `WHERE actor_id = %s` → 任何 authenticated actor 可讀任何人 experiment。
     修復方向：SELECT 加 `JOIN replay.run_state s ON ... WHERE s.actor_id = %s`，把 `actor.actor_id` 加 SQL parameter；加分支「`actor` 是 admin（`_require_replay_admin` PASS）→ skip actor_id filter 可讀任何 experiment」。
   - **路徑遍歷**：L1064 `Path(row[2])` 直接 open without `is_relative_to`。
     修復方向：定 allowlist root = `OPENCLAW_DATA_DIR / "replay"`，open 前 `resolved = artifact_path.resolve(); if not resolved.is_relative_to(allowlist_root.resolve()): raise HTTPException(403, "artifact_path_outside_allowlist")`。

**派發（單 E1，3 改點獨立區段）：**

| 改點 | 路徑 | 行 | 方向 |
|---|---|---|---|
| 1（P0-2 / verify env） | `srv/program_code/.../app/replay_routes.py` | L1255-1284 | env-var 加 release-profile gate；boot guard（同檔 module-init 區段加 startup check） |
| 2（P0-4 / cancel pid identity） | 同檔 | L843-864 | 加 `psutil.Process(pid).cmdline()` cmdline substring 驗 `replay_runner`；fail → 不送 SIGTERM |
| 3a（P0-5 / IDOR） | 同檔 | L1020-1034 | SELECT 加 `s.actor_id = %s` filter + admin bypass（`_require_replay_admin` 試呼，PASS 則 skip filter）|
| 3b（P0-5 / 路徑遍歷） | 同檔 | L1063-1068 | Path resolve + `is_relative_to(allowlist_root)` 驗 |

**互斥分析**：3 改點分別在 L843 / L993 / L1255 三段不同 endpoint；無共用 helper / SQL fragment 重疊 → **可在同 E1 一個 commit 連改**（3 改點各加 1 unit test）。

**E2 必查 3 點：**
- `psutil` 為 cross-platform（Mac + Linux 皆 PASS） — Mac dev 可跑（CLAUDE.md §七 ★★ 跨平台）
- IDOR 修補後既有 owner 的 experiment 仍可讀（pytest fixture 用兩 actor_id 驗 owner PASS / non-owner 403 / admin PASS）
- `is_relative_to` Python 3.9+ 支援；若需要 Python 3.8 fallback 寫 `str(resolved).startswith(str(allowlist_root.resolve()) + os.sep)`

---

## §3. Track 間真正依賴

| 依賴 | 性質 | 影響 |
|---|---|---|
| Track D → Track A INSERT path | **強**（INSERT V045 不變但 V049 表必先在）| Track A 寫 manifest fixture 路徑後 INSERT V045 沒新欄位需求；但 V045 `manifest_id` FK 在 V052 後指 V049，Track A 的 UUID5 衍生路徑（replay_routes L515-520）**不變**（仍寫到 V045，FK 約束自動由 V052 強制）|
| Track D → Track B 簽名驗證 | **無**（Rust 不直接讀 V049/V050/V051；只讀 manifest fixture file）| Track B 跟 Track D 完全解耦 |
| Track D → Track C IDOR/路徑修 | **弱**（C 只讀 V045 + V046；不讀 V049）| Track C 不依賴 Track D |
| Track A → Track B fixture 寫入路徑 | **強**（Track A 必先寫 manifest.json + key.hex 到 output_dir，Track B 才有 file 可 verify）| Track A E1 寫 fixture writer code 後 Track B 改 fail-closed 才不會破現有 fixture-based test |
| Track A → Track C cancel pid 驗證 | **無**（C 改的 cancel endpoint 跟 A 改的 spawn 路徑時序對齊上互相支援，但同 endpoint 不重疊）| 同檔 replay_routes.py 兩 E1 並行需注意 PR rebase（建議同 E1 連 commit Track A + Track C 部分；或分 2 E1 但 commit 順序 A→C）|

**結論：4 Track 真正並行可達 = D 起頭 → A+B+C 三者同時開工 → A 完成 fixture writer 後 B 換 fail-closed → 全 Track E4 跨 track smoke。**
**最大並行度 = 3 E1（A/B/C 三人同時，D 由其中一 E1 起頭做完再回 A 或 C）。Sprint 1 預估 3.5-4 day（含 E2 + E4）。**

---

## §4. Interface Contract Surface（API 變更總表）

| 改變類別 | 對象 | 變更 | 影響範圍 |
|---|---|---|---|
| **CLI flag** | `replay_runner` Rust binary | 已存在 `--manifest <path> --output-dir <path> --baseline-id <str>`（不變）| Python spawn 改用相同；其他 caller 0 |
| **Python 函數簽名** | `route_helpers.spawn_replay_runner` | 新增 `manifest_fixture_path: Path` 參數；移除 `run_id` argv 傳遞語意（保留為 logging 用）| 1 個 caller（replay_routes L544-548）|
| **Python 函數簽名** | `replay_routes.post_replay_run` 內 `_do_pg_path` | 加 fixture writer 步驟 + spawn poll 步驟（內部變更，外部 API contract 不變）| 0 caller，Python 內部 |
| **Rust struct** | `ReplayManifest` | 加 `pub run_id: Option<String>` 欄位（`#[serde(default)]`）| `replay_runner.rs` 內部使用，serde 向後相容 |
| **SQL column** | V049 `replay.experiments` | 22 個全新欄 + 3 對 window EXCLUDE GIST | replay_routes（讀 V045 + V046 不變；新代碼若引用 V049 由 Track A `_v045_table_present` 模式擴展 `_v049_table_present`）|
| **SQL column** | V050 `replay.simulated_fills` | 17 個全新欄 + FK to V049 | 0 production caller（P3a/P3b writer 是 Wave 5/6 任務）|
| **SQL column** | V051 `learning.mlde_shadow_recommendations` | 加 2 column + 雙路 CHECK | `mlde_demo_applier.py` `mlde_shadow_advisor.py` 等 producer 必加 `evidence_source_tier='real_outcome'` + 2 NULL 寫入（已有 V038-V040 做 `evidence_source_tier`，新加 2 column 寫 NULL 為 default 即兼容）|
| **SQL FK** | V052 ALTER ADD CONSTRAINT | V045.manifest_id → V049.experiment_id；V046.experiment_id → V049.experiment_id | 上線 dry-run 必驗既有 V045/V046 row 對應 V049 row 存在（**警告**：V045 已 land 的 row 若 manifest_id 未在 V049 → V052 會 fail；**對策** Track D Mac dev 必先 dry-run 統計 dangling 數）|
| **Python env var** | `OPENCLAW_RELEASE_PROFILE` | 新增（讀，未存即非 live）；`OPENCLAW_REPLAY_VERIFY_TEST_KEY` 在 release=live 時被強制清空 | 啟動腳本（restart_all.sh）建議加註，但不強制 |

---

## §5. 5 個 Push Back（PA 看到的設計坑）

### Push Back #1：V045 既有 row 對 V052 FK redirect 的 dangling 風險（**HIGH**）
V045 至今已 land 多個 run（每次 POST /run 寫一 row），其 `manifest_id` 欄位是 UUID5 衍生（replay_routes L515-520）但 **無對應 V049 row 存在**（V049 還沒造）。Track D T-D4 對 V045.manifest_id 加 FK 直接 fail。
**對策：** T-D4 ALTER ADD CONSTRAINT 前必加 preflight：
```sql
SELECT COUNT(*) FROM replay.run_state r
LEFT JOIN replay.experiments e ON r.manifest_id = e.experiment_id
WHERE e.experiment_id IS NULL;
```
> 0 → T-D4 必先做 reconciliation：(a) 把 dangling V045 row 寫入 V049（INSERT SELECT 補造 minimal 22 column），或 (b) DELETE/archive dangling V045 row。**operator 決定 a 或 b**；不可繞 FK 直接 redirect。

### Push Back #2：Track A 把 `run_id` 從 argv 移走但 Rust 從 manifest 讀 → manifest_id 與 run_id 一致性無 enforce（**MEDIUM**）
Python INSERT V045 用 `uuid.uuid4().hex`（V045 PK），但 manifest fixture 內 `run_id` 是 Python 寫進去的；若 attacker / bug 讓兩者不一致，Rust 報告寫到 wrong run_id 的 output_dir（output_dir 由 Python 端用 V045 run_id 決定）。
**對策：** Rust replay_runner 啟動時自驗：`manifest.run_id` 必等於 `output_dir.basename()`；不等 → CliError + fail-closed。Track A E1 改 replay_runner.rs 加這段 guard（與 Track A 同 task 不外加）。

### Push Back #3：Track B fail-closed 後 production 路徑「key.hex 必在 manifest 旁」是運維契約 not engineering（**MEDIUM**）
Track B 把 sibling key.hex 缺改 hard error；Wave 6 V042 SQL archive land 前的 production deploy 必須由 operator 手動把 key.hex 放到每個 manifest 旁。這個運維契約**沒有 healthcheck 監測**。
**對策：** PA 提案 Sprint 1 順手加一個 `helper_scripts/db/passive_wait_healthcheck.py` 的 `check_replay_manifest_key_presence()`：對 V045 status='running' row 的 output_dir 檢查 sibling key.hex 是否存在；缺 → WARN（不 FAIL，因 V042 land 前是已知過渡）。**列入 Track D scope**（schema land 順手加 healthcheck）。

### Push Back #4：Track C `_require_replay_admin` 不保證已存在（**MEDIUM**）
我假設 `_require_replay_admin` 已是既有 RBAC primitive；若 codebase 內無此 helper，Track C 必須先建（會把 1 task 變 2 task）。
**對策：** Track C E1 起手必先 `grep -n "_require_replay_admin\|replay:admin\|replay:read:any" srv/program_code/`；若 0 hit → 加任務 `_require_replay_admin` 借用 `_require_replay_write` pattern（既有，replay_routes.py 內 helper），加新 scope `replay:admin` 進 actor.scopes 檢查；若已有 → 直接用。（**E1 起手檢查；發現缺則 SCOPE EXPAND PA 認可**）

### Push Back #5：5 Track 間 Mac dev pytest 必在 Linux dry-run 之前過（**HIGH，跨平台合規）
Mac CC 不可實際 deploy migration 到 Linux PG；所有 V049-V052 file 必先在 Mac dev local PG 跑 idempotency × 2 + Guard A/B/C 全 NOTICE PASS（無 RAISE）+ pytest fixture（`tests/migrations/test_v049_*` 等）→ Linux operator 才 `psql -f` 真 land。
**對策：** Track D 每 task 同 commit 帶 pytest fixture（mock psql parser 或 testcontainer PG）；E4 必驗 fixture full PASS。違反 = E2 打回（CLAUDE.md §七 跨平台 + memory `feedback_cross_platform.md`）。

---

## §6. 跨 Track 共同 helper 提醒（避重複造）

| Helper / Type | 已存在路徑 | 跨 Track 用法 |
|---|---|---|
| `_v045_table_present(cur)` | `replay/route_helpers.py:200-223` | Track D 須加 `_v049_table_present` `_v050_table_present` `_v051_table_present` 同 pattern；E1 一次造 3 個 + 1 個 helper factory `_table_present(cur, schema, table)` |
| `_emit_audit_stub(...)` | `replay_routes.py` 多處 | Track A/C 改後續 audit 寫 V035 governance_audit_log，event_type 加 `replay_argv_mismatch_blocked` / `replay_signature_test_key_blocked` / `replay_pid_identity_mismatch` / `replay_idor_blocked` / `replay_artifact_path_traversal_blocked` 五新 event；V035 CHECK enum 必擴展 → 同 commit 加 V053 migration（**新增 task T-D5**，PA 補登）|
| `psutil.Process` cmdline check | 新增 helper `_verify_replay_runner_pid(pid: int) -> bool` | Track C 用；放 `replay/route_helpers.py` 不是 replay_routes.py（route_helpers 是 sibling pattern）|
| Manifest fixture writer | 新增 `_write_manifest_fixture(run_id: str, manifest_data: dict, output_dir: Path) -> Path` | Track A 用；放 `replay/route_helpers.py`；同 commit 加 sibling 寫 `key.hex`（dev only；prod 由 operator 部署）|

---

## §7. PA 自審：W1 派發 schema drift 自爆認領

**確認漏洞：** PA Wave 1 派發 R20-P2a-T1 + T3 + T5 為 migration（V049 `replay_experiments` / V050 `replay_simulated_fills` / V051 `mlde_shadow_recommendations` 補欄），IMPL 偷換成 fixture（V045 SQL L17-21 自承「`replay.experiments` lives in P2b runner SQL fixture, NOT a migration」）—— **PA W1 沒 catch 這個偷換，導致 V3 §4.1 22 column + V3 §4.1 17 column 全藏 fixture 繞 Guard A/B/C；V3 §4.2 雙路 CHECK 殘缺**。

**根因（PA 自審）：**
1. Wave 1 派發 reservation 預留時用詞「fixture」沒看出是繞 migration 的偷換（Reservation L47-48 寫「P2b runner SQL fixture，不佔 migration 編號」當時讀過去視為合法選項）。
2. PM 簽收 V045 + V046 時 PA review 沒交叉檢查 V3 §4.1 22 column 是否在 V045 / V046 內（V045 + V046 加起來只 covers run lifecycle + report artifacts，不含 experiments 本表）。

**未來防線：**
- 任何 V### reservation 從「fixture」回 migration 必 PA + PM 雙簽（不單方面決定）
- V### file land 同 commit 必對 spec source（V3 §4.1 等）full column count 對齊（22 column → SQL 22 column hit；不漏）
- E2 PR review 必加 spec-vs-SQL column count 檢查 task

---

## §8. PM Sign-off 必檢清單

| 項目 | 狀態 |
|---|---|
| 16 條根原則：原則 1（單一寫入口）/ 原則 8（交易可解釋）/ 原則 4（風控門控）覆蓋 | Track 不觸 trading hot path；只動 replay 平面 → ✅ |
| 硬邊界 grep | 4 Track 全部不觸 `live_execution_allowed` / `max_retries` / `system_mode` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` → ✅ |
| 跨平台（Mac dev 可跑） | psql Mac dev / psutil Mac PASS / Rust binary cargo build Mac PASS → ✅ |
| Idempotency（V### × 2）| Track D 每 file 必驗 → strong gate |
| 雙語 MODULE_NOTE | 4 Track 全 file（新加 / 修改）必有 → strong gate |
| Healthcheck（被動等待 + 新監測）| Push Back #3 加 `check_replay_manifest_key_presence()` → strong gate |

---

**派發指令格式回 PM：4 Track 共 ~7-8 E1 task，最大並行 3 E1，Sprint 1 預估 3.5-4 day（含 E2 + E4 全跑）。Track D 優先（schema 阻塞），其他 3 Track 起頭做 D 完工後即可全並行。**
