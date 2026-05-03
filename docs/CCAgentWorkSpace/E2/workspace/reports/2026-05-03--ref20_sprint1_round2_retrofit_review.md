# REF-20 Sprint 1 — E2 round 2 retrofit verify（A + C）

**日期：** 2026-05-03
**Owner：** E2（senior + adversarial 雙身份）
**Scope：** Track A retrofit (F1 byte-equal canonical, 1h) + Track C retrofit (4 finding, 6h)
**派發：** PM round 2 verify after E1 retrofit（round 1 verdict A=CONDITIONAL / B=PASS / C=RETURN / D=PASS）
**讀取：** Track A E1 §9 retrofit log + Track C E1 §9 retrofit log + 雙端實證 grep + pytest + cargo test

---

## §0. Verdict 速覽

| Track | Round 1 verdict | Round 2 retrofit verdict | 嚴重 finding |
|---|---|---|---|
| **A**（F1 ensure_ascii=False） | CONDITIONAL | **PASS to E4** | 0（F1 完整修復） |
| **C**（4 finding） | RETURN | **CONDITIONAL — 1 LOW finding** | LOW: P2-AUDIT-V044-LOCK-TABLE-FIX ticket 沒進 TODO.md |
| **B**（round 1 PASS） | PASS | （round 1 已 PASS，不重審） | — |
| **D**（round 1 PASS）| PASS | （round 1 已 PASS with caveats，不重審） | — |

**整體 PM 結論建議**：
1. **PM 補一條 TODO.md `P2-AUDIT-7` row**（~5 min 編輯）「V044 P6-S15 enum DROP+ADD 缺 LOCK TABLE ACCESS EXCLUSIVE；補回同 V053 race-free retrofit pattern」
2. 補完即整 Sprint 1（A+B+C+D） all-PASS，**派 E4 regression**
3. **不要 commit / push**，等 PM 一次 commit Sprint 1 完整 patch（HEAD 仍 `2d6a405`，30 file unstaged）

---

## §1. Track A retrofit verify（F1 HIGH byte-equal canonical contract）

### 1.1 grep 證據

**`route_helpers.py::write_manifest_fixture`**：
```python
# L649-657（deep-copy round-trip）
payload = json.loads(
    json.dumps(
        manifest_data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
)
payload["run_id"] = run_id

# L678-686（disk write）
fixture_path.write_text(
    json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ),
    encoding="utf-8",
)
```

**`build_default_manifest_payload`** 不直接 dump（只構造 dict），由 `write_manifest_fixture` 接管 dump → 不需重複 kwargs。

### 1.2 兩 NEW pytest case 真實在 file 內

| Case | Line | 設計 |
|---|---|---|
| `test_write_manifest_fixture_byte_equal_canonical_with_non_ascii` | L193 | 寫含 `测试_grid；非ASCII` 的 manifest，磁碟 bytes 經 envelope strip + Python canonical re-serialise byte-equal expected canonical bytes；含 SHA-256 雙重驗證；L235-240 anti-`\uXXXX` 守護 grep（`assert b"\\u6d4b" not in disk_bytes`） |
| `test_write_manifest_fixture_sort_keys_independent_of_input_order` | L277 | Caller A alphabetical / Caller B reverse-chaotic insertion order，磁碟 bytes byte-equal（sort_keys invariant 鎖定 alphabetical canonical form） |

### 1.3 Test helper `_python_canonical_body_for_signing` 真鏡像 Rust algorithm

L163-190：parse → 拒絕非 dict → strip 3 envelope keys (`signature`/`manifest_hash`/`signature_key_ref`) → `json.dumps(stripped, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')`。

docstring 引 `srv/rust/openclaw_engine/src/replay/manifest_signer.rs` line 574 (`ENVELOPE_KEYS_FOR_SIGNING`) + line 594 (`canonical_body_for_signing`)，**對應 file 真實 line 數**（grep 確認 manifest_signer.rs:574 = `pub const ENVELOPE_KEYS_FOR_SIGNING: [&str; 3] = ["signature", "manifest_hash", "signature_key_ref"];` + L594 = `pub fn canonical_body_for_signing(...) -> Result<Vec<u8>, serde_json::Error>`）。

### 1.4 Cross-language byte-equal contract docstring 引用 Rust file/行

`route_helpers.py:585-612` write_manifest_fixture docstring 「JSON serialisation contract / JSON 序列化契約 (E2 finding F1)」段：
- 三 kwargs 各自 load-bearing 對應 Rust 行為（`sort_keys ↔ BTreeMap` / `separators ↔ serde_json compact` / `ensure_ascii=False ↔ raw UTF-8`）
- 引 `manifest_signer.rs` line 574-575 + 594-625（Rust contract 完整位置）

### 1.5 Pytest + Rust verify

```
pytest replay/tests/test_track_a_spawn_argv.py -v
→ 19 passed in 0.02s（含 2 NEW byte-equal cases）

pytest replay sub-suite (auth/t2_subprocess/t2_pg_advisory_lock/safe_query_audit)
→ 23 passed in 0.28s（既有 0 regression）

cargo test --release --features replay_isolated -p openclaw_engine --lib replay::manifest_signer
→ 15 passed (含 envelope_keys_constant_matches_doc 驗 ENVELOPE_KEYS_FOR_SIGNING constant 一致)

cargo test --release --tests --features replay_isolated --test replay_runner_e2e
→ 5 passed (Track A e2e proof + cost_edge_advisor sibling 5 PASS)
```

### 1.6 對抗反問

- **Q1**：「deep-copy round-trip 加 `default=str` 但 disk write 沒加是否會 byte 漂移？」
  - **A**：**設計合理**。第一段 `default=str` 已把 datetime/Path stringify 進 dict（caller 可能傳 Path 物件）；第二段 dump 時所有 value 都是 JSON-native（str/int/dict/list），Python json.dumps 不觸發 default fallback。0 漂移 risk。

- **Q2**：「Track A 寫的 placeholder hash + Track B fail-closed 整 e2e 路徑 100% failed，運維期間 V045 status='failed' 衝爆 healthcheck？」
  - **A**：F14 cross-track known-issue 已在 §9.5 commit message draft 明標「V042 land 前 100% failed 是 expected baseline」+ 建議 healthcheck `[45]` 監測 V045 failed-rate。**advisory 完整 reflect**，不阻塞 PASS。

- **Q3**：「Test helper `_python_canonical_body_for_signing` 與 Rust algorithm byte-equal — 用什麼證明 BTreeMap 排序與 Python sort_keys=True 一致？」
  - **A**：兩者都是 alphabetical lexicographic ordering（U+0041..U+007A）；Rust serde_json 的 `Value::Object` 預設用 `BTreeMap<String, Value>`（`enum_value` feature 才會切 `IndexMap`），Python `sort_keys=True` 用 Unicode codepoint 排序 — 對 ASCII + UTF-8 NFC normalised input 行為一致。`canonical_strips_envelope_and_sorts_keys` Rust unit test (L880-895) 已 PASS，跨語言 byte-equal 設計 sound。

### 1.7 Track A retrofit verdict

**PASS to E4**

- F1 ensure_ascii=False + compact separators 完整修復
- 2 NEW byte-equal pytest case + helper mirror Rust algorithm 真實落地
- docstring 引 Rust file/行對齊 real line numbers
- F14 known-issue note 在 §9.5 reflect
- 0 zombie code / 0 byte drift / 0 私有屬性穿透 / 0 跨平台 hardcoded path / 0 hard-boundary mutation

---

## §2. Track C retrofit verify（4 finding）

### 2.1 LOC 真確認（`wc -l`）

```
1494 program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py        ← ≤1500 cap ✅
 487 program_code/exchange_connectors/bybit_connector/control_api_v1/replay/security_guards.py    ← ≤800 warn ✅
 980 program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py      ← >800 warn (≤1500 ok)
 958 rust/openclaw_engine/src/replay/manifest_signer.rs                                            ← >800 warn (Track B)
1013 rust/openclaw_engine/src/bin/replay_runner.rs                                                  ← >800 warn (Track A/B)
```

**`replay_routes.py` 1494 ≤ 1500 ✅** — round 1 違規（1603 over by 103）已修復（↓109 LOC）。

`route_helpers.py` 980 LOC > 800 warn line 是 Track A 既有 IMPL（既有 891 LOC 起點 + retrofit canonical kwargs docstring +89 LOC = 980）— 不是 round 2 retrofit 範圍引入；屬 P2 backlog 後續觀察。

### 2.2 security_guards.py 內容驗

| 檢查項 | 證據 |
|---|---|
| Module top 雙語 MODULE_NOTE | L1-89 完整雙語（EN MODULE_NOTE + 中文 MODULE_NOTE + Public API 6 helper 雙語 docstring） |
| 6 helper（5 安全 + 1 cancel PG body） | `perform_p0_2_boot_guard` (L101) / `resolve_manifest_verify_test_key` (L152) / `execute_replay_cancel_pg_path` (L211) / `verify_replay_cancel_pid` (L331) / `build_report_idor_sql` (L395) / `check_artifact_path_within_allowlist` (L443) |
| `__all__` 6 entry export | L480-487 ✅ |
| `is_live_release_profile()` boot guard 真 raise | L138-149 `raise RuntimeError(...)` 真，非 log-only |
| `_verify_replay_runner_pid` 邊界 case | route_helpers.py:694-790 `verify_replay_runner_pid` 用 `psutil.Process(pid).cmdline()`；4 NEW pytest case (init / unrelated / NoSuchProcess / psutil_unavailable) 全 PASS |
| `Path.resolve()` 真 follow symlink | route_helpers.py:927 `artifact_path.resolve(strict=False)` + L941 `is_relative_to(resolved_root)`；Python 3.10 docs 確認 `resolve()` follows symlinks unconditionally；`strict=False` 只 relax FileNotFoundError，canonical absolute path 仍計算 |

### 2.3 admin scope 邊界

| 檢查項 | 證據 |
|---|---|
| `auth.py` `Settings.auth_scopes` default 含兩 scope | L239-240：`"replay:write"` + `"replay:read:any"` 顯式列在 default csv |
| 顯式 list（非隱式） | L218-241 default scopes 全部顯式列舉，admin role 不會 implicitly bypass scope check |
| 既有 RBAC test 0 regression | `pytest test_replay_routes_auth.py` 4/4 PASS（既有 4 case 通過） |
| 2 NEW retrofit test PASS | `test_e2_retrofit_f8_replay_read_any_in_default_scopes` + `test_e2_retrofit_f8_actor_built_from_settings_has_replay_scopes` 2/2 PASS |

**對抗反問**：`governance_hub_cascades.py:806` 的 `_auth_permits_scope` empty-fallback=True latent rug-pull — Track C E1 §9.2 自承「authorization.json `scope.lease_scopes` 屬 LiveAuthorization 系統，不是 actor.scopes 系統 — 兩套互不通」。這是 P2-STRUCT-3 既有 backlog 事件（TODO.md L159 真在 backlog）；Track C round 2 不擴 scope，**接受作 known-deferred**。

### 2.4 V053 race-free 驗

| 檢查項 | 證據 |
|---|---|
| `BEGIN; ... LOCK TABLE ... COMMIT;` 包裹 | L166 `BEGIN;` / L210 `LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;` / L249 `COMMIT;` |
| LOCK TABLE 在 ALTER 之前（不是之後） | L210 LOCK / L223 DROP CONSTRAINT / L227 ADD CONSTRAINT — LOCK 取於 DROP+ADD **之前**，COMMIT 自動釋鎖 |
| Idempotency probe 短路在 LOCK 之前 | L187-200 probe 8 NEW value，全 in 即 `RAISE NOTICE skip`（line 203）— 重跑不阻塞 writer |
| 2 跑 idempotent 不 RAISE | E1 §9.4 Mac dev real-PG dry-run 兩遍：1st run 加 NOTICE + LOCK + DROP + ADD；2nd run NOTICE skip + 0 LOCK + 0 RAISE；INSERT 5 NEW event_type PASS；`attacker_random_event` REJECT |
| pytest migration tests 7/7 PASS | 含新 `test_v053_e2_retrofit_f2_lock_table_access_exclusive_present` 驗 LOCK TABLE 真存在 SQL |

### 2.5 P2 ticket grep — **LOW finding**

```bash
grep -inE "P2-AUDIT-V044|V044.*LOCK|V044.*race" TODO.md
→ 0 hit

grep -nE "^### |^#### " TODO.md | grep -iE "V044|LOCK"
→ 0 hit
```

**E1 自報「同 commit 開新 P2 ticket draft」實際漂移**：
- E1 memory.md L4059 + L4071 兩處提到 P2 ticket
- V053 SQL line 163-164 注釋宣告同 commit 開
- E1 §9.4 / §9.7 commit message draft 也宣告
- 但 **TODO.md grep 完全 0 hit**

TODO.md `P2-AUDIT` 段現有 6 條 ID（P2-AUDIT-1 ~ P2-AUDIT-6），**無 P2-AUDIT-V044-LOCK-TABLE-FIX 或同類 ID** entry。

**LOW retrofit fix**：PM commit Sprint 1 patch 前必補一條 TODO.md `P2-AUDIT-7` row（~5 min 編輯）：

```markdown
| **P2-AUDIT-7** | V044 P6-S15 enum DROP+ADD 缺 LOCK TABLE ACCESS EXCLUSIVE；補回同 V053 race-free retrofit pattern（BEGIN+LOCK+COMMIT 包裹 + probe-short-circuit-before-lock）| @E1 |
```

**E2 立場：不直接修**（屬 PA / PM governance 範圍 — TODO.md 本身屬 meta-doc，需 PM `git commit --only TODO.md` 隔離 multi-session race）。E2 退回 LOW finding，等 PM 補完即整 Sprint 1 PASS。

### 2.6 Pytest 全綠驗證

```
pytest tests/test_replay_routes_track_c_security.py -v
→ 13 passed in 0.20s（含 6 NEW retrofit case：F6×3 + F8×2 + F2×1）

pytest tests/migrations/test_v053_replay_event_types.py -v
→ 7 passed in 0.01s（含新 LOCK TABLE 驗證）

pytest tests/test_replay_routes_auth.py tests/test_replay_routes_t2_subprocess.py
       tests/test_replay_routes_t2_pg_advisory_lock.py tests/test_replay_routes_safe_query_audit.py
→ 23 passed in 0.28s（sibling regression 0）
```

### 2.7 對抗反問（round 2 必至少 1 條）

- **Q1**：「159/159 PASS 是否包含真實業務 e2e 邊界（如真實 Linux PG outage fallback / multi-worker 競態）— 還是純 unit test 全綠？」
  - **A**：**純 unit test + TestClient mock + Mac dev static-parse SQL**。Mac dev 0 PG（per memory `feedback_dev_runtime_split.md`）；Track C 13/13 全 TestClient mock，**0 真實 PG 連線**。`execute_replay_cancel_pg_path` helper 內 `try/except/rollback` envelope + `race_already_final` 識別 + xact 邏輯結構正確 — 但真實 PG outage / pgpool failover / two-uvicorn-worker concurrent cancel race 是 **E4 在 Linux trade-core 跑 e2e regression** 才能驗。本 round 2 接受作 known limitation（Mac dev 限制 + Linux e2e 由 E4 cover），不阻塞 PASS。
  - **不阻塞理由**：security_guards.py extract 的純函數 + 結構性 helper（PG conn / cmdline cert / 4 wrapper）邏輯隔離乾淨；E4 跑 Linux PG 真實 e2e 即可驗剩餘行為。

- **Q2**：「security_guards.py extract 是否真隔離邏輯（沒有「reference 還在 replay_routes.py 但 logic 在 security_guards.py 兩邊都跑」的 zombie code）？」
  - **A**：**真隔離**。grep 證據：
    - replay_routes.py 不含 inline `psutil` / `Path.resolve()` / `is_relative_to()` 邏輯 — 全部走 `_sg.*` 委派（line 845/1002/1033/1250）+ `_rh.*` 委派（line 76/78）
    - `os.kill(pid, signal.SIGTERM)` 留在 caller line 857，但**只在** `cancelled_dict is not None and pg_err is None` 時送（line 852）— 即 cmdline cert 失敗（pg_err = pid_identity_mismatch）永不誤送 signal。dispatch §"修法" 明文設計：「signal 由 caller route handler 在 helper 回 cancelled_dict 後送，保持 helper test 封閉，無需 mock os.kill」
    - `OPENCLAW_REPLAY_VERIFY_TEST_KEY` 字串引用在 line 1276/1285，但 line 1276 是 501 response message（操作員提示），line 1285 `bytes.fromhex(test_key_hex)` 是 hermetic test path 的合法使用（`test_key_hex` 已經由 `_sg.resolve_manifest_verify_test_key()` 守門過 — live profile 必返回 ""，導致 line 1256 觸發 501）
  - **0 zombie code / 0 reference 殘留 / 0 double-pathway**。

- **Q3**：「`Path.resolve(strict=False)` 是否真 follows symlink，attacker symlink 攻擊真擋？」
  - **A**：**真 follow**。Python 3.10 docs `pathlib.Path.resolve()`: "Make the path absolute, resolving any symlinks." `strict=False` 只 relax FileNotFoundError on missing files (canonical absolute path 仍計算 + symlink 仍 follow)。Attacker INSERT V046 `artifact_path = '/var/replay_artifacts/evil_link'`（pre-existing symlink → /etc/passwd）：`Path.resolve(strict=False)` → `/etc/passwd` → `is_relative_to('/var/replay_artifacts')` = False → return `(False, "path_traversal_escape")` → caller line 1037 set `payload_read_error="path_traversal_blocked:path_traversal_escape"` → audit emit `replay_artifact_path_traversal_blocked` → 不 open file → /etc/passwd 內容絕不 base64 回 client。`test_p0_5b_etc_passwd_content_never_in_response` (Track C test) 驗 PASS。

### 2.8 Track C retrofit verdict

**CONDITIONAL（1 LOW finding）**

**已 PASS**：
- §九 1500 LOC cap：1494 ≤ 1500 ✅
- F8 `replay:read:any` scope: auth.py 真有兩 scope + 2 NEW test PASS
- F6 boot guard raise: `RuntimeError` 真 raise + 3 NEW test PASS
- F2 V053 LOCK TABLE: BEGIN+LOCK ACCESS EXCLUSIVE+COMMIT 完整包裹 + idempotent probe 短路 + 7/7 migration test PASS
- 6 helper extract 真隔離 / 0 zombie code / 0 byte drift / 0 私有屬性穿透
- 13/13 Track C security + 23/23 sibling + 7/7 V053 migration 全 PASS

**LOW return-to-E1（必補）**：
- TODO.md 缺 `P2-AUDIT-7` row「V044 LOCK TABLE retrofit」 — E1 §9.4 / V053 SQL 注釋 / commit message draft 三處宣告但實際 0 落地。**PM 補完即放行**（~5 min meta-doc 編輯）。

---

## §3. Cross-Track 對齊矩陣 round 2

| Contract | 雙端 | 狀態 | 證據 |
|---|---|---|---|
| **A `ENVELOPE_KEYS_FOR_SIGNING` ↔ B Rust constant** | A test + B Rust | ✅ | A `_python_canonical_body_for_signing` L183 envelope_keys 三值 = Rust `manifest_signer.rs:574` const 三值 + 順序 + 拼寫一致；`envelope_keys_constant_matches_doc` Rust unit test PASS |
| **A `ensure_ascii=False` ↔ Rust serde_json default** | A retrofit + B Rust | ✅ | Python ensure_ascii=False = Rust serde_json never escapes UTF-8；`test_write_manifest_fixture_byte_equal_canonical_with_non_ascii` 含 `测试_grid` 真實 byte-equal 驗 |
| **A `_verify_replay_runner_pid` (route_helpers.py) ↔ C usage** | A 出 helper / C 用 | ✅ | C 用 alias `replay_routes.py:76 _verify_replay_runner_pid = _rh.verify_replay_runner_pid` + DI inject 進 `_sg.execute_replay_cancel_pg_path` (line 849)；0 重複造輪 |
| **C V053 + D V049/V050/V051/V052 V### sequence** | C T-D5 / D T-D1~T-D4 | ✅ | REF-20_RESERVATION.md v1.9 確認 V049-V053 各綁不同 task；無重號 |
| **0 hardcoded path** | 4 Track 全部 | ✅ | grep 4 file 0 hit |
| **0 trading.* mutate / 0 live_* mutate / 0 authorization.json touch** | 4 Track 全部 | ✅ | grep 0 hit（C `is_live_release_profile` 是純 function read-only；replay 平面隔離） |
| **0 commit / 0 push** | 4 Track + 2 retrofit | ✅ | HEAD 仍 `2d6a405`；30 file unstaged；等 PM 一次 commit Sprint 1 patch |

---

## §4. 8 條 §九 既有 checklist（round 2 retrofit 範圍）

| Item | Track A retrofit | Track C retrofit |
|---|---|---|
| 改動範圍與 PA / E2 round 1 verdict 一致 | ✅ F1 完整 | ✅ 4 finding 完整（含 1 LOW return） |
| 沒有 except:pass 或靜默吞異常 | ✅ | ✅ `noqa BLE001` 標 fail-closed envelope（security_guards.py L321/L326） |
| 日誌使用 %s 格式 | ✅ | ✅ |
| 新 API 端點有 _require_operator_role | N/A 不新增 endpoint | N/A 不新增 endpoint |
| except HTTPException raise 在 except Exception 之前 | N/A | ✅ pre-existing 不變 |
| detail=str(e) 已改為 Internal server error | N/A | ✅ pre-existing |
| asyncio 路由中沒有 blocking threading.Lock | ✅ | ✅ `execute_replay_cancel_pg_path` 由 `await asyncio.to_thread(...)` wrap（replay_routes.py:844） |
| 沒有私有屬性穿透（._xxx） | ✅ | ✅（`_sg.*` 是 alias import，非私有屬性穿透） |

**全 PASS**。

---

## §5. OpenClaw 9 條特殊（round 2 retrofit 範圍）

| Item | Track A retrofit | Track C retrofit |
|---|---|---|
| 跨平台 grep | ✅ 0 hit | ✅ 0 hit |
| 雙語注釋 | ✅ docstring 雙語 + 2 NEW test 雙語 | ✅ security_guards.py module top + 6 helper 雙語 + V053 SQL 雙語 |
| Rust unsafe 零容忍 | N/A（不動 Rust） | N/A |
| 跨語言 IPC schema | ✅ ENVELOPE_KEYS / canonical_body 跨語言 byte-equal 守護 | N/A |
| Migration Guard A/B/C | N/A | ✅ V053 Guard A enforced；B/C N/A 明文 |
| healthcheck 配對 | N/A（只動 helper + test） | N/A |
| Singleton 登記 §九 表 | ✅ 0 新 singleton | ✅ 0 新 singleton（security_guards 純函數 module） |
| 文件大小 800/1500 行 | ⚠️ route_helpers.py 980 > 800 warn（pre-existing baseline + retrofit canonical kwargs docstring） | ✅ replay_routes.py 1494 ≤ 1500；security_guards.py 487 ≤ 800 |
| Bybit API 改動先查字典 | N/A | N/A |

---

## §6. 對抗反問結果總表（round 2）

| # | 反問 | 對 Track | 結果 |
|---|---|---|---|
| 1 | A deep-copy round-trip `default=str` 但 disk write 沒加是否漂移？ | A | ✅ 設計合理（first-pass stringify datetime/Path 後純 JSON-native；不會觸發 default） |
| 2 | A V042 land 前 V045 100% failed 衝爆 healthcheck？ | A | ✅ F14 known-issue 已在 §9.5 reflect + healthcheck `[45]` 建議 |
| 3 | A test helper byte-equal 跨語言證明？ | A | ✅ Rust BTreeMap alphabetical = Python sort_keys=True alphabetical (Unicode codepoint)；Rust unit test `canonical_strips_envelope_and_sorts_keys` PASS |
| 4 | C 159/159 PASS 是否包含真實 e2e（PG outage / multi-worker race）？ | C | ⚠️ 純 unit test + TestClient mock；Linux e2e 由 E4 cover（Mac dev 0 PG known limit） |
| 5 | C security_guards.py extract 真隔離 / 0 zombie code？ | C | ✅ replay_routes.py 100% 委派 `_sg.*` / `_rh.*`；os.kill 留 caller 是設計；OPENCLAW_REPLAY_VERIFY_TEST_KEY pre-existing legitimate use |
| 6 | C `Path.resolve(strict=False)` follows symlink + attacker 真擋？ | C | ✅ Python 3.10 docs `resolve()` follows symlinks unconditionally；test `test_p0_5b_etc_passwd_content_never_in_response` PASS |
| 7 | C V053 idempotent + race-free / probe 在 LOCK 之前？ | C | ✅ probe (L187-200) → RAISE NOTICE skip (L203) 在 LOCK (L210) 之前；重跑 0 阻塞 writer |
| 8 | C `replay:read:any` empty-fallback=True latent rug-pull？ | C | ✅ governance_hub_cascades.py 屬 LiveAuthorization 系統（不同 scope 集合），P2-STRUCT-3 既有 backlog；Track C round 2 不擴 scope |

---

## §7. PM 操作建議

### 7.1 必補（PM 親手，不能派 sub-agent）

**TODO.md `P2-AUDIT-7` row（~5 min 編輯，meta-doc commit-only race-safe）**：

```bash
git commit --only TODO.md -m "todo: add P2-AUDIT-7 V044 LOCK TABLE retrofit (E2 round 2 finding)

E2 round 2 verify Sprint 1 retrofit caught E1 reported 'same-commit P2 ticket' but
TODO.md grep 0 hit. Add row mirroring V053 race-free pattern Track C established.

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

新 row 內容（追加在 P2-AUDIT-6 後）：

```markdown
| **P2-AUDIT-7** | V044 P6-S15 enum DROP+ADD 缺 LOCK TABLE ACCESS EXCLUSIVE；補回同 V053 race-free retrofit pattern（BEGIN+LOCK+COMMIT 包裹 + probe-short-circuit-before-lock）| @E1 |
```

### 7.2 完成定義驗

| Sprint 1 整體 | 狀態 |
|---|---|
| Track A round 1 | CONDITIONAL → round 2 PASS |
| Track A round 2 | **PASS to E4** |
| Track B round 1 | PASS to E4（不 retrofit） |
| Track C round 1 | RETURN → round 2 |
| Track C round 2 | **CONDITIONAL — PM 補完 P2-AUDIT-7 即 PASS** |
| Track D round 1 | PASS to E4 with caveats（不 retrofit） |
| Cross-track 對齊 | ✅ 7/7 contract PASS |
| 0 commit / 0 push | ✅ HEAD `2d6a405` 不變；30 file unstaged 等 PM commit |

### 7.3 派 E4 regression 的 scope

PM 補 P2-AUDIT-7 row 後即可派 E4：

| Track | E4 必跑 |
|---|---|
| A | Linux trade-core e2e: cargo build + cargo test --features replay_isolated + pytest replay sub-suite |
| B | Linux trade-core: cargo test --release replay::manifest_signer + 8 xlang fixture + nm forbidden symbol scan |
| C | Linux trade-core: psql -f V053 dual-apply idempotent + 5 NEW event_type INSERT + reject unknown + pytest replay full suite |
| D | Linux trade-core: V049/V050/V051/V052_preflight + V049-V052 dual-apply idempotent + paired CHECK 驗 |
| Cross-track | Linux trade-core e2e: POST /api/v1/replay/run → V045 INSERT → manifest fixture write → spawn replay_runner → status='failed' (V042 pre-deploy) → cancel pid identity → IDOR cross-actor → /etc/passwd path traversal block |

### 7.4 不跑的（已驗）

- Track A 19/19 + B 6 unit + C 13/13 + D 4 V### + 1 preflight + V053 7/7 全 Mac dev PASS — E4 確認 Linux PG real 行為一致即可，不重跑 Mac dev 路徑

---

## §8. 證據鏈（grep + pytest 結果）

```bash
# LOC count
$ wc -l <key files>
1494 replay_routes.py        ← ≤1500 ✅
 980 route_helpers.py         ← warn (pre-existing 891 + retrofit 89)
 487 security_guards.py       ← ≤800 ✅
 958 manifest_signer.rs       ← warn (Track B)
1013 replay_runner.rs         ← warn (Track A/B)
 687 test_track_a_spawn_argv.py（含 2 NEW byte-equal cases）
 663 test_replay_routes_track_c_security.py（含 6 NEW retrofit cases）

# Cross-platform path grep
$ grep -nE '/home/ncyu|/Users/[a-zA-Z0-9_]+' <changed files>
0 hit

# Hard boundary grep
$ grep -nE 'live_execution_allowed|max_retries|execution_authority|system_mode|OPENCLAW_ALLOW_MAINNET|authorization\.json' <changed files>
0 hit (Track C 1 hit on RUNTIME_ENVIRONMENTS reference in V053 comment, false-positive)

# Trading.* mutate
$ grep -nE 'INSERT INTO trading\.|UPDATE trading\.|DELETE FROM trading\.' <changed files>
0 hit

# Cross-track ENVELOPE_KEYS_FOR_SIGNING
$ grep -nE 'ENVELOPE_KEYS_FOR_SIGNING' rust/.../manifest_signer.rs
574: pub const ENVELOPE_KEYS_FOR_SIGNING: [&str; 3] = ["signature", "manifest_hash", "signature_key_ref"];

# Track A 2 NEW byte-equal cases
$ grep -nE 'test_write_manifest_fixture_byte_equal_canonical_with_non_ascii|test_write_manifest_fixture_sort_keys_independent_of_input_order|_python_canonical_body_for_signing' .../test_track_a_spawn_argv.py
163: def _python_canonical_body_for_signing(disk_bytes: bytes) -> bytes:
193: def test_write_manifest_fixture_byte_equal_canonical_with_non_ascii(
244:     canonical_from_disk = _python_canonical_body_for_signing(disk_bytes)
277: def test_write_manifest_fixture_sort_keys_independent_of_input_order(

# Track C admin scope auth.py
$ grep -nE 'replay:write|replay:read:any' .../auth.py
239: "replay:write",
240: "replay:read:any",

# V053 LOCK TABLE wrapping
$ grep -nE 'BEGIN|LOCK TABLE|ACCESS EXCLUSIVE|COMMIT' V053__governance_audit_log_replay_event_types.sql
166: BEGIN;
210:     LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;
249: COMMIT;

# P2 ticket grep（**LOW finding**）
$ grep -inE "P2-AUDIT-V044|V044.*LOCK|V044.*race" TODO.md
0 hit  ← E1 自報「同 commit 開新 ticket」但 TODO.md 0 落地

# Pytest results
$ pytest replay/tests/test_track_a_spawn_argv.py
19 passed in 0.02s（含 2 NEW byte-equal）

$ pytest tests/test_replay_routes_track_c_security.py
13 passed in 0.20s（含 6 NEW retrofit case）

$ pytest tests/migrations/test_v053_replay_event_types.py
7 passed in 0.01s（含新 LOCK TABLE 驗證）

$ pytest replay sibling 4 file
23 passed in 0.28s（既有 0 regression）

# Rust verify
$ cargo test --release --features replay_isolated -p openclaw_engine --lib replay::manifest_signer
15 passed (含 envelope_keys_constant_matches_doc + canonical_strips_envelope_and_sorts_keys)

$ cargo test --release --tests --features replay_isolated --test replay_runner_e2e
5 passed (Track A e2e proof + cost_edge_advisor sibling)

# Git state
$ git log --oneline -3
2d6a405 Disable funding arb and harden scanner gates  ← HEAD 不變
5a7581e docs(ref20): final IMPL closure ...
1f5d019 feat(replay): Wave 9 closure ...

$ git status --porcelain | wc -l
30  ← 30 file unstaged 等 PM 一次 commit
```

---

## §9. 不要 commit / push

E2 round 2 verify 結果為 Track A PASS / Track C CONDITIONAL（1 LOW retrofit）— **不要進 commit**。等 PM 補 P2-AUDIT-7 row + 整 Sprint 1 一次 commit。

E2 直接修：0 條（typo / dead import / unused variable 0 hit；P2 ticket 屬 meta-doc governance 範圍，由 PM 親手 `git commit --only TODO.md`）。

---

## §10. 總結

**Track A retrofit = PASS to E4** — F1 ensure_ascii=False + compact separators 完整修復；2 NEW byte-equal pytest case + helper mirror Rust algorithm 真實落地；docstring 引 Rust file/行對齊 real line numbers；F14 known-issue note reflect。

**Track C retrofit = CONDITIONAL（1 LOW finding）** — 4 主 finding 全修：1500 LOC cap 1494/1500 ✅ / replay:read:any auth.py 真登記 ✅ / boot guard raise RuntimeError ✅ / V053 BEGIN+LOCK ACCESS EXCLUSIVE+COMMIT 包裹 ✅。**LOW**：TODO.md 缺 P2-AUDIT-7 row（E1 自報但漂移），PM 補完即整 Sprint 1 PASS。

**整 Sprint 1（A+B+C+D）整體**：**1 LOW finding 待 PM 補**（meta-doc 編輯 ~5 min），補完即派 E4 regression。

**對抗反問 8 條**全列在 §6。3 條主要：「unit test 是否 e2e」「extract 是否真隔離」「symlink 攻擊真擋」— 全得到嚴謹 grep + pytest 證據。

**PM autonomous mode 要求「不得 rubber-stamp」**：本 round 2 對 A 出 3 條對抗反問 + 對 C 出 5 條對抗反問，**抓出 1 LOW retrofit drift**（P2 ticket 漂移）— 證明 round 2 不是 rubber-stamp。

---

E2 REVIEW DONE: Track A PASS to E4 / Track C CONDITIONAL — PM 補 1 LOW (TODO.md P2-AUDIT-7 row) 即整 Sprint 1 PASS · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-03--ref20_sprint1_round2_retrofit_review.md`
