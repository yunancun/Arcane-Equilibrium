# REF-20 Sprint A R3 Round 6 — Task DAG Design

**Date**: 2026-05-05
**Author**: PA (Project Architect)
**Status**: design ready (read-only; no IMPL, no commit)
**Sprint context**: REF-20 Sprint A R3 round 5 ran 5-commit chain (`c1ab7ea9` / `353db3fe` / `66b650ea` / `cad8ed84` / `e9d547c0`+`2ae93992`); QA smoke E2E round 3 揭第 4 層 blocker → operator decision (A) 走 §八 強制鏈 PA→E1→E2→E4→QA。

---

## §0. Trigger root cause stack（spawn 時序展開）

依 spawn 路徑時序排列。修 `1` 後若不修 `2`，下次 spawn fail 仍會 silent-dead；修 `1+2` 後若不修 `3`，runner load_fixture fail。三條互相獨立、必須同 round 成。

| # | Layer | 真實位點 | 表面症狀 | Root cause |
|---|---|---|---|---|
| 1 | Manifest sign | `route_helpers.py::build_default_manifest_payload:669-670` 寫 `placeholder_signature_wave6_v042_pending` + `placeholder_hash_wave6_v042_pending` | subprocess exit=1, 1.5s grace 內早死 | Sprint 1 Track B (commit `edf33c0`) fail-closed verifier `manifest_signer.rs:548-557` 拒 placeholder（既不在 KeyArchive，sig 也不對 canonical_body 真 HMAC） |
| 2 | Spawn observability | `route_helpers.py::spawn_replay_runner:549` `stderr=subprocess.DEVNULL` | API only 寫「likely CLI schema mismatch / manifest fail-closed」模糊 reason；無 stderr 落 disk | Silent-dead 反模式（CLAUDE.md §九）— 任何 spawn fail 都需 ssh manual reproduce |
| 3 | Fixture provision | API process 缺 `OPENCLAW_REPLAY_FIXTURE_URI` env 或自動 fixture provision 機制 | runner load_fixture fail（fixture.json 不存在於 output_dir） | restart_all.sh::restart_api() 不 export 此 env；route_helpers.build_default_manifest_payload 預設指向 `<output_dir>/fixture.json` 但 nobody put it there |

**真正修 = 1+2+3 同 round。**

---

## §1. R3-R6-T1 — `write_manifest_fixture` 真 HMAC sign

### Spec

把 `build_default_manifest_payload` + `write_manifest_fixture` 兩函式組合升級為「真 HMAC sign manifest 並寫 sibling key.hex」。**重用既有 helper**：

| 已有 helper（不動） | 來源 | 用途 |
|---|---|---|
| `replay/manifest_signer.py::compute_body_hash` | manifest_signer.py:216 | sha256 hex |
| `replay/manifest_signer.py::ManifestSigner.from_bytes_for_test(key_bytes, fingerprint)` | manifest_signer.py:386 | T1 sign-time signer constructor（test path / spawn path 同模） |
| `replay/manifest_signer.py::ManifestSigner.sign(canonical_bytes)` | manifest_signer.py:424 | HMAC-SHA256 hex |
| `replay/manifest_signer.py::compute_key_fingerprint(file_content_bytes)` | manifest_signer.py:181 | 16-hex fingerprint，對齊 generate_replay_signing_key.sh L91/93/111 |
| `replay/manifest_signer.py::load_signing_key_from_secrets_dir` | manifest_signer.py:514 | R2-T3 已 ship；env_label allowlist + live profile mode/symlink 守門 |
| `replay/experiment_registry.py::compute_manifest_canonical_bytes` | experiment_registry.py:416 | sort_keys+separators+ensure_ascii=False canonical bytes |

### 簽名 key 來源優先級

```
(a) OPENCLAW_REPLAY_SIGNING_KEY_FILE env override (dev/test path; 直指 key.hex)
        ↓ 不存在或無效
(b) load_signing_key_from_secrets_dir(env_label)
        env_label 來自 OPENCLAW_REPLAY_ENV_LABEL（default "demo"，allowlist 見 R2-T3）
        ↓ 不存在或無效
(c) NULL → 不可 sign → raise ValueError("manifest_signing_key_unavailable")
        → caller 進 503 路徑（既有 manifest_fixture_write_failed 分支即可吸收）
```

**永不 fallback 回 placeholder**；T1 完成後 placeholder 字串徹底從 codebase 移除。

### Sibling key.hex 寫入

write_manifest_fixture sign 完成後：
1. 取得 `(key_bytes, fingerprint)` from 上述 (a) or (b)
2. file content bytes 重建：`hex_encode(key_bytes) + "\n"`（對齊 helper script 的 trailing newline 不變式）
3. write `<output_dir>/key.hex` permission `0o600`（Mac umask 022 default 0o644 / Linux secrets dir 期望 0o600）
4. fingerprint 對齊：`signature_key_ref` 寫 fingerprint（取代 placeholder_key_ref）

### Manifest 簽名流程（write_manifest_fixture 內部）

```python
# Build payload (no signature/hash/key_ref yet — 簽前剝除 envelope)
body = {
    "experiment_id": experiment_id,
    "data_tier": "S3",
    "fixture_uri": resolve_fixture_uri(output_dir),  # T3 提供 default
    "run_id": run_id,
}
canonical = compute_manifest_canonical_bytes(body)  # body 不含 envelope keys
manifest_hash = compute_body_hash(canonical)
key_bytes, fingerprint = resolve_signing_key()  # raise on failure
signer = ManifestSigner.from_bytes_for_test(key_bytes, fingerprint)
signature = signer.sign(canonical)

# Final manifest_jsonb (寫 disk 時加入 envelope 三鍵)
final = dict(body)
final["signature"] = signature
final["manifest_hash"] = manifest_hash
final["signature_key_ref"] = fingerprint

# Disk write (canonical settings — sort_keys+separators+ensure_ascii=False)
fixture_path.write_text(json.dumps(final, sort_keys=True, ...), encoding="utf-8")

# Sibling key.hex
key_hex_path = output_dir / "key.hex"
key_hex_path.write_text(key_bytes.hex() + "\n", encoding="utf-8")
os.chmod(key_hex_path, 0o600)
```

**不變量**（Sprint 1 F1 retrofit canonical bytes contract）：
- `compute_body_hash(canonical)` 與 Rust `canonical_body_for_signing(disk_bytes)` 對齊（envelope 剝除規則 + sort_keys + separators + ensure_ascii=False）
- `signer.sign(canonical)` HMAC-SHA256 byte-equal 與 Rust `ManifestSigner::sign(canonical_body)`
- 8/8 cross-language fixture regression test 已鎖此契約（`tests/replay/test_manifest_signer_xlang_consistency.py`）

### Acceptance

1. **placeholder 字串完全消失**：`grep -n placeholder_signature_wave6_v042_pending` 0 hit。
2. **真 HMAC sign**：`build_default_manifest_payload` 移除（或改為純 body 構造）；`write_manifest_fixture` 接管 envelope 加註。
3. **fail-closed key resolution**：(a)/(b) 都 fail → raise ValueError；caller `manifest_fixture_write_failed` 503 路徑可消化。
4. **Round 6 + e2e smoke**：register → run → wait → finalize → V045 status='succeeded' / V046 1 row / V050 N rows / V054 audit 三 row。

### LOC 估算

- Edit `build_default_manifest_payload`（保留為純 body builder，移除 envelope 三鍵）：-15 / +10
- Refactor `write_manifest_fixture` 接管 sign + sibling key.hex 寫入：+85
- New helper `_resolve_manifest_signing_key()` private function：+30
- 雙語 docstring + MAINTAINER warning（R3 round 6 fix 動機 + Sprint 1 Track B 對齊）：+25
- **小計 +135 LOC** → route_helpers.py 1249 → 1384

### 雙語 MAINTAINER warning（draft）

```python
# REF-20 Sprint A R3 Round 6 (2026-05-05) — REAL HMAC SIGN + KEY.HEX SIBLING:
# Round 5 (commits c1ab7ea9 / 353db3fe / 66b650ea / cad8ed84 / e9d547c0)
# left build_default_manifest_payload writing placeholder strings for
# signature/manifest_hash/signature_key_ref because the original Wave 4
# T1 contract assumed Wave 6 V042 SQL archive would be the production key
# source. Sprint 1 Track B (commit edf33c0) hardened load_and_verify_manifest
# to FAIL-CLOSED on placeholder/missing-key paths — which immediately broke
# the spawn flow (subprocess exit=1, V046/V050 stuck at 0 rows). Round 6
# closes the loop: write_manifest_fixture now performs real HMAC-SHA256
# sign using the env-override-or-secrets-file key source (R2-T3 helper
# load_signing_key_from_secrets_dir is reused; placeholder code-path is
# removed permanently). Sibling key.hex is written under 0o600 so the Rust
# runner's load_and_verify_manifest can locate the signing key for verify.
# DO NOT regress to placeholder values — the Rust verifier no longer has a
# fall-through path. CR/QA must grep for placeholder_signature on every
# subsequent edit to this file.
#
# REF-20 Sprint A R3 Round 6（2026-05-05）— 真 HMAC sign + key.hex sibling：
# Round 5 留下 build_default_manifest_payload 寫 placeholder 字串，因為原
# Wave 4 T1 契約假設 Wave 6 V042 SQL archive 為 prod key 源。Sprint 1 Track
# B 把 load_and_verify_manifest 改為 fail-closed → spawn 流程立刻斷
# （subprocess exit=1, V046/V050 卡在 0 行）。Round 6 補完：write_manifest_
# fixture 用 (env override) 或 (R2-T3 secrets file) 真 HMAC-SHA256 sign，
# 並落 sibling key.hex 0o600 給 Rust runner verify 用。Placeholder 路徑徹底
# 刪除；CR/QA 每次後續 edit 必 grep placeholder_signature 0 hit。
```

---

## §2. R3-R6-T2 — `spawn_replay_runner` stderr capture

### Spec

把 `stderr=subprocess.DEVNULL` 換成 disk file handle，使 spawn fail 後 stderr 內容可從 disk 讀回作 reason 細化。

```python
# Round 6 stderr capture path:
stderr_path = output_dir / "replay_runner.stderr"
with open(stderr_path, "wb") as stderr_fh:
    proc = subprocess.Popen(
        argv,
        env=child_env,
        stdout=subprocess.DEVNULL,
        stderr=stderr_fh,           # ← Round 6 fix
        close_fds=True,
    )

# poll grace period 後若早死，讀 stderr 寫入 spawn_err detail
if rc is not None and rc != 0:
    stderr_excerpt = ""
    try:
        if stderr_path.exists():
            stderr_bytes = stderr_path.read_bytes()
            # Cap excerpt to 2KB（avoid huge bytes leak進 logs/JSON detail）
            stderr_excerpt = stderr_bytes[-2048:].decode("utf-8", errors="replace")
    except OSError:
        stderr_excerpt = "<stderr_read_failed>"
    log.warning(
        "replay_runner died early: pid=%d exit=%d run_id=%s stderr=%r",
        proc.pid, rc, run_id, stderr_excerpt,
    )
    return None, f"spawn_died_early:exit={rc}:stderr={stderr_excerpt[:256]}"
```

### Path allowlist 守門

`stderr_path = output_dir / "replay_runner.stderr"` 落在 `<resolve_artifact_output_dir(run_id)>` 之下，已在 P0-5b artifact_path_within_allowlist 範圍 — **不需新增 allowlist 條目**。E3 重審需確認 path 不超越 `OPENCLAW_DATA_DIR/replay_artifacts/<run_id>/` root。

### Buffer-fill block 風險

DEVNULL 永不 block；改 file handle 也永不 block（disk write 阻塞理論可能但 OS 級限制）。**重要**：Popen 後 Python parent 立刻 close 自己持有的 fh（with 區塊自動 close）；child 持 fd 寫入即可。**1.5s grace 內 stderr 量級 < 100KB**（一條 fail-closed error stack） — 安全。

### LOC 估算

- New stderr_path resolve + Path → file open：+10
- Read-back logic + 2KB cap + utf-8 decode：+25
- Log message 細化 + 雙語 docstring：+15
- **小計 +50 LOC**

### Acceptance

1. spawn_died_early 路徑寫 disk file `replay_runner.stderr`（路徑在 allowlist 之下）
2. /run handler 503 detail.reason_codes 加 stderr 摘要（2KB cap）
3. operator 不需 ssh manual reproduce 即可從 API response + `<output_dir>/replay_runner.stderr` 看到完整 stderr
4. spawn 成功路徑也保留 stderr file（runner 跑完後 stderr 留在 disk for post-mortem）

---

## §3. R3-R6-T3 — Fixture provisioning（PA 推薦 (a)）

### Decision: (a) restart_all.sh + route_helpers env fallback

| | (a) restart_all 加 env export | (b) route_helpers 自動 cp fixture |
|---|---|---|
| 實作面 | restart_api() 加 export `OPENCLAW_REPLAY_FIXTURE_DEFAULT=$REPO_ROOT/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json`；build_default_manifest_payload `fixture_uri` 預設讀此 env | write_manifest_fixture 對 client `manifest_jsonb.fixture_uri` 自動 cp 到 `<output_dir>/fixture.json` 並 mutate manifest |
| 失敗點 | 0 disk I/O；symlink 安全（fixture 是 git tracked） | 多 mkdir+copy 失敗點（OSError on FS full、ENOENT、permission 等） |
| Manifest 不變式 | 不變動 client manifest_jsonb（fixture_uri 由 server-side default 填）| 違背：server silently mutate client 給的 fixture_uri |
| Multi-run 隔離 | 共享單一 fixture（read-only OK） | 每 run cp 一份（disk space cost）|
| R4 UI integration | UI subtab 直接受益（client 不需傳 fixture_uri） | UI 需先 upload fixture 才能 run（額外端點）|
| 跨平台 | 純 env export（restart_all 已 portable）| Mac dev 路徑 `/tmp/replay_artifacts_test_only` 必驗 cp 跨 FS |

**(a) 推薦理由**：fixture 是 git tracked 的 read-only 文件，所有 run 共享一份是正確語意；(b) 引入額外失敗點 + manifest mutation 是違背契約。

### restart_all.sh::restart_api() 改動

```bash
# REF-20 Sprint A R3 Round 6 (2026-05-05) — fixture provisioning env:
# Sprint A R3 Round 5 closed the binary path / engine SHA / register schema
# blockers but smoke E2E still fell to manifest fixture file not present
# at <output_dir>/fixture.json. Round 6 wires a process-level env so the
# API process resolves OPENCLAW_REPLAY_FIXTURE_DEFAULT to the in-tree
# synthetic fixture used by Sprint A smoke runs. R4+ UI runs override via
# client-supplied manifest_jsonb.fixture_uri; this env is server-side
# fallback only.

local fixture_default
if [ -f "$REPO_ROOT/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json" ]; then
    fixture_default="$REPO_ROOT/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json"
else
    fixture_default=""
fi

OPENCLAW_BASE_DIR="$base_dir" \
    OPENCLAW_DATA_DIR="$DATA_DIR" \
    OPENCLAW_DATABASE_URL_FILE="$OPENCLAW_DATABASE_URL_FILE" \
    OPENCLAW_IPC_SECRET_FILE="$OPENCLAW_IPC_SECRET_FILE" \
    OPENCLAW_ENGINE_BINARY_SHA="$engine_sha" \
    OPENCLAW_REPLAY_FIXTURE_DEFAULT="$fixture_default" \
    nohup "$API_VENV/bin/python3" "$API_VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 --port 8000 --workers "$WORKERS" \
    > "$DATA_DIR/api.log" 2>&1 &
```

### route_helpers.build_default_manifest_payload 配套

```python
def build_default_manifest_payload(*, experiment_id, output_dir):
    fixture_uri = (
        os.environ.get("OPENCLAW_REPLAY_FIXTURE_URI", "").strip()
        or os.environ.get("OPENCLAW_REPLAY_FIXTURE_DEFAULT", "").strip()
        or str(output_dir / "fixture.json")
    )
    return {
        "experiment_id": experiment_id,
        "data_tier": "S3",
        "fixture_uri": fixture_uri,
        # signature/manifest_hash/signature_key_ref intentionally absent;
        # write_manifest_fixture (T1) computes envelope from canonical body.
    }
```

### LOC 估算

- restart_all.sh 加 export + comment：+18
- route_helpers env fallback chain：+7
- **小計 +25 LOC**

### Acceptance

1. API process 重啟後 `printenv OPENCLAW_REPLAY_FIXTURE_DEFAULT` 顯示 absolute fixture path
2. /run flow 不傳 manifest_jsonb.fixture_uri 時自動 fallback 到 env default
3. 客戶端供 fixture_uri 時優先用客戶端值（既有行為）

---

## §4. R3-R6-T4 — Tests + verification

### 4 個 test case

| # | 文件 | 類型 | 跨檔依賴 |
|---|---|---|---|
| T4-1 | `tests/replay/test_route_helpers_real_hmac_sign.py` | unit | mock secrets dir + fixture key.hex |
| T4-2 | `tests/replay/test_route_helpers_stderr_capture.py` | unit | tmp_path + 故意 spawn 失敗 binary |
| T4-3 | `tests/replay/test_route_helpers_fixture_default_env.py` | unit | monkeypatch env |
| T4-4 | `tests/replay/test_replay_e2e_round6_smoke.py` | integration | mock PG + 真實 spawn replay_runner subprocess + 跑 fixture |

### T4-1 unit test for write_manifest_fixture real HMAC

```python
def test_write_manifest_fixture_real_hmac_with_env_override(tmp_path, monkeypatch):
    """T1 acceptance: env override path produces real HMAC + sibling key.hex."""
    # Setup fixture key
    key_hex = "aabbccddeeff00112233445566778899aabbccddeeff00112233445566778899"
    key_path = tmp_path / "test_key.hex"
    key_path.write_text(key_hex + "\n")
    monkeypatch.setenv("OPENCLAW_REPLAY_SIGNING_KEY_FILE", str(key_path))

    output_dir = tmp_path / "run_xyz"
    run_id = "test-run-xyz"
    payload = build_default_manifest_payload(
        experiment_id="test-exp", output_dir=output_dir,
    )
    fixture_path = write_manifest_fixture(
        run_id=run_id, manifest_data=payload, output_dir=output_dir,
    )

    # Assert no placeholder strings
    written = fixture_path.read_text()
    assert "placeholder" not in written

    # Assert HMAC valid (sign canonical body with same key + compare)
    manifest = json.loads(written)
    assert "signature" in manifest and len(manifest["signature"]) == 64
    assert "manifest_hash" in manifest and len(manifest["manifest_hash"]) == 64
    body = {k: v for k, v in manifest.items()
            if k not in ENVELOPE_KEYS_FOR_SIGNING}
    canonical = compute_manifest_canonical_bytes(body)
    expected_sig = hmac.new(
        bytes.fromhex(key_hex), canonical, hashlib.sha256
    ).hexdigest()
    assert manifest["signature"] == expected_sig

    # Assert sibling key.hex written 0o600
    key_sibling = output_dir / "key.hex"
    assert key_sibling.exists()
    assert oct(key_sibling.stat().st_mode & 0o777) == "0o600"
    assert key_sibling.read_text().strip() == key_hex
```

### T4-2 unit test for stderr capture

```python
def test_spawn_replay_runner_stderr_captured_on_early_death(tmp_path, monkeypatch):
    """T2 acceptance: subprocess early death writes stderr to <output_dir>/replay_runner.stderr."""
    # Use `/bin/sh -c "echo HMAC FAIL >&2; exit 1"` shim as fake runner
    fake_bin = tmp_path / "fake_runner"
    fake_bin.write_text('#!/bin/sh\necho "HMAC verify failed: signature_mismatch" >&2\nexit 1\n')
    fake_bin.chmod(0o755)
    monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", str(fake_bin))

    output_dir = tmp_path / "run_xyz"
    output_dir.mkdir()
    manifest_fixture = output_dir / "manifest.json"
    manifest_fixture.write_text("{}")  # 沒檢內容,只測 stderr capture

    pid, err = spawn_replay_runner(
        run_id="test-run", manifest_id="test-mid",
        output_dir=output_dir, manifest_fixture_path=manifest_fixture,
    )
    assert pid is None
    assert err is not None
    assert err.startswith("spawn_died_early:exit=1")
    # Stderr file must exist
    stderr_path = output_dir / "replay_runner.stderr"
    assert stderr_path.exists()
    assert "HMAC verify failed" in stderr_path.read_text()
    # Reason code includes excerpt
    assert "stderr=" in err and "HMAC" in err
```

### T4-3 unit test for fixture default env

```python
def test_build_default_manifest_payload_uses_fixture_default_env(monkeypatch, tmp_path):
    """T3 acceptance: OPENCLAW_REPLAY_FIXTURE_DEFAULT used when client fixture_uri absent."""
    fixture_path = tmp_path / "synthetic.json"
    fixture_path.write_text("{}")
    monkeypatch.delenv("OPENCLAW_REPLAY_FIXTURE_URI", raising=False)
    monkeypatch.setenv("OPENCLAW_REPLAY_FIXTURE_DEFAULT", str(fixture_path))
    output_dir = tmp_path / "run_xyz"
    payload = build_default_manifest_payload(
        experiment_id="test-exp", output_dir=output_dir,
    )
    assert payload["fixture_uri"] == str(fixture_path)
```

### T4-4 integration test (4 表 row > 0)

- monkeypatch `psycopg2.connect` 回 真 PG（CI infra 提供 ephemeral PG `trading_ai`）
- spawn 真 replay_runner binary（cargo build_release 已 ship Linux + Mac dev）
- POST /api/v1/replay/experiments/register → 200 + experiment_id row in V049
- POST /api/v1/replay/experiments/{id}/run → 202 + V045 row status='running'
- 等 fixture 6 events 跑完（~5s polling loop）
- POST /api/v1/replay/runs/{run_id}/finalize → 200 + V046/V050 row > 0

**Acceptance**：4 表 V049/V045/V046/V050 + V054 audit 合計 ≥ 5 row 真實寫入；`SELECT COUNT(*) FROM replay.simulated_fills WHERE replay_run_id = $run_id` 返回 6（fixture 6 events）。

### Test LOC 估算

- T4-1：60 LOC
- T4-2：50 LOC
- T4-3：30 LOC
- T4-4：100 LOC + 10 LOC test fixture loader
- **小計 +250 LOC** 跨 4 新檔，0 影響 baseline route_helpers.py LOC。

---

## §5. 派工 DAG + 並行決策

### 為何 T1+T2 不可分兩 E1

兩 task 都改 `route_helpers.py`（T1 改 build_default_manifest_payload + write_manifest_fixture / T2 改 spawn_replay_runner）— 同檔同 wave 並行 = git merge conflict 或 force resolve（CLAUDE.md §八「並行 ≥2 sub-agent 操作可能重疊檔 → 需 isolation: worktree」）。**合併到 1 E1 比 isolation worktree 開銷低**（T1+T2 邏輯相關：T2 是觀察 T1 失敗的工具）。

### DAG（serial 3 commit）

```
Commit-1 (E1-A): T1 + T2 同檔 → +135 (T1) + +50 (T2) = +185 LOC route_helpers.py
   ↓ 必先 land 才能跑 e2e
Commit-2 (E1-B): T3a restart_all.sh export + route_helpers env fallback chain → +25 LOC
   ↓ Commit-1 + Commit-2 都 land 後才能 e2e
Commit-3 (E1-C): T4 4 個 test → +250 LOC 跨 4 新檔（不修 production code）
```

**並行可能性**：
- E1-A + E1-C 可並行（T4 是 test 文件，不衝突 production code）
- E1-B 依賴 E1-A 是 e2e 路徑前置（必先 land 才能驗）；但純 code 改動本身不衝突 → **PA 推薦 E1-A + E1-B + E1-C 三 sub-agent 並行**，三 commit 完成後 E2 統一 review，E4 統一 regression。

### LOC 預估匯總

| 文件 | baseline | round 6 增 | 結果 | 警告線（800）/ 硬限（1500） |
|---|---:|---:|---:|---|
| route_helpers.py | 1249 | +185 (T1+T2) | 1434 | 已破 800 警告線（Wave 4 P2b-T2 已知接受）；< 1500 硬限 ✅ |
| restart_all.sh | 470 | +18 (T3a) | 488 | < 800 ✅ |
| 4 新 test 檔 | 0 | +250 | 250 | < 800 ✅ |
| **合計** | | **+453 LOC** | | |

**Pre-existing baseline exception clause 不觸發**（route_helpers.py 1249 是 Wave 4 既有，本 round 從 1249 → 1434 < 1500，不需 PM Sign-off governance exception）。

### E2/E3/E4 review 重點

| 角色 | 任務 | 檢查點 |
|---|---|---|
| E2 | T1+T2+T3 code review | (1) T1 簽名 key fallthrough 順序對齊；不 fallthrough 回 placeholder。(2) T2 stderr_path 經 `artifact_path_within_allowlist` 守門。(3) T1 重用 `compute_manifest_canonical_bytes` + `compute_body_hash` + `ManifestSigner.sign`，不複製 sort_keys/separators kwargs。 |
| E3 | path/env 安全審計 | (1) stderr_path 必落 `<output_dir>/replay_runner.stderr` 並在 P0-5b allowlist 之下。(2) sibling key.hex permission 0o600（Mac umask 022 不破）。(3) `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env override 不破 R2-T3 live profile symlink-injection 守門（dev/test only path）。(4) `OPENCLAW_REPLAY_FIXTURE_DEFAULT` env 不被 client 直接控制（restart_all.sh server-side resolve）。 |
| E4 | regression + integration | (1) Round 5 mock-only 假綠教訓 — T4-4 必 spawn 真 binary，不 mock subprocess。(2) 4 表 row > 0 binding：V045 status='succeeded' / V046 1 row / V050 ≥ 1 row / V054 audit ≥ 3 row。(3) Sprint 1 8/8 cross-language fixture HMAC byte-equal regression test 仍 PASS（不被 T1 改動破壞）。 |

---

## §6. Hidden risk

| # | 風險 | 影響 | 緩解 |
|---|---|---|---|
| H1 | route_helpers.py 1249 → 1434 越過 §九 800 警告線 | 後續 round 7+ 越接近 1500 硬限 | 不拆檔本 round；R4 UI subtab 啟動時評估抽 `manifest_provisioning.py` |
| H2 | canonical_bytes contract drift | T1 不重用 helper 而獨立 sort_keys/separators 設定 → 跨語言 byte-equal 破裂 → Sprint 1 8/8 regression test fail | E2 必查 T1 import `compute_manifest_canonical_bytes` 從 experiment_registry.py（不複製 kwargs） |
| H3 | sibling key.hex permission Mac dev 0o600 vs Linux production 期望差異 | umask 022 寫入 0o644，後續 verify 時 R2-T3 live profile mode check 拒絕 | T1 顯式 `os.chmod(0o600)` 強制；live profile 守門邏輯不變 |
| H4 | stderr file 1.5s grace 內 buffer fill block | 理論可能；fail-closed error stack 通常 < 100KB → 安全 | 保留風險 acknowledgment；若 round 6 後觀察到 block，後續加 thread-pool stderr drain |
| H5 | T4-4 e2e test CI infra 依賴 | CI 無 PG → test skip → 無 evidence 證 4 表寫入 | E4 必跑 Linux runtime 真 PG e2e（非僅 unit test）；報告附 `SELECT COUNT(*)` SQL 證據 |
| H6 | sha256sum (Linux) vs shasum -a 256 (Mac) cross-platform | restart_all.sh round 4 已 portable 處理；T3a 不引入新 OS 命令 | 保留現狀，不破 |
| H7 | multi-worker uvicorn race | M-1 V045 FOR UPDATE 已修；T1 process-internal sign 不涉跨 worker 共享狀態 | 不變 |
| H8 | Sprint 1 F1 retrofit canonical contract 對齊 — Rust `ENVELOPE_KEYS_FOR_SIGNING` 在 manifest_signer.rs:574 hardcoded `["signature", "manifest_hash", "signature_key_ref"]` | T1 必嚴格剝除這三鍵 sign | E2 必 grep T1 sign 路徑 strip 三鍵；helper `compute_manifest_canonical_bytes` 已假設 caller 傳入「不含 envelope」的 body dict — 對齊責任在 T1 caller |
| H9 | placeholder 殘留 grep 漏網 | round 5 grep 漏掉某個 callsite 仍寫 placeholder | E2 必跑 `grep -rn 'placeholder_signature\|placeholder_hash' srv/program_code` 0 hit；T1 commit message 必含 grep 結果 evidence |

---

## §7. PM open question + answer

| # | Question | Answer |
|---|---|---|
| 1 | T3 (a) vs (b) 哪個？ | **(a)**。理由 §3 對比表；(b) 引入額外失敗點 + manifest mutation 違背契約。 |
| 2 | 簽名 key 來源優先級 | **(a) `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env override → (b) R2-T3 `load_signing_key_from_secrets_dir(env_label)` → (c) NULL → 報 ValueError**。永不 fallback 回 placeholder。Live profile 守門由 (b) R2-T3 既有 mode/symlink 邏輯涵蓋。 |
| 3 | key.hex 寫 disk permission | **0o600 強制 `os.chmod`**。Mac umask 022 default 0o644 必明確收緊；Linux secrets dir 期望 0o600 一致。dev mode（Mac）下 0o600 不破任何效能（restart_all run-as-user 寫入即可讀回）。 |
| 4 | LOC 越過 800 警告線拆檔 | **本 round 不拆**（1434 < 1500 硬限，pre-existing exception clause 不觸發）。R4 UI subtab 啟動時若繼續加碼可考慮抽 `manifest_provisioning.py`。 |
| 5 | 是否疊 Decision Lease canary 24h 視窗 | **NO**（與 Sprint 3 Track H 灰度分離，AMD-2026-05-02-01 §5.4 flag flip 待 ~05-15 P0-EDGE-2 後 operator action） |
| 6 | E1 並行還是 serial | **3 sub-agent 並行**（E1-A T1+T2 同檔 / E1-B T3a 跨檔 / E1-C T4 純 test）；E2/E4 統一 review。`isolation: worktree` 不需要（三檔不重疊）。 |

---

## §8. 預期 R3 Round 6 commit 後 4 表 row > 0 達成路徑

```
[client] POST /api/v1/replay/experiments/register
   ↓
[V049 replay.experiments] 1 row INSERT (R2-T1 already ships)
   ↓
[client] POST /api/v1/replay/experiments/{id}/run
   ↓
[route_helpers.write_manifest_fixture] T1 真 HMAC sign
   - canonical body = {experiment_id, data_tier, fixture_uri, run_id}
   - signature = HMAC-SHA256(key_bytes, canonical_bytes)
   - manifest_hash = SHA-256(canonical_bytes)
   - signature_key_ref = compute_key_fingerprint(key_file_content_bytes)[:16]
   - sibling key.hex written 0o600
   ↓
[route_helpers.spawn_replay_runner] T2 stderr→file
   - argv = [bin, --manifest <path>, --output-dir <path>]
   - stderr_path = <output_dir>/replay_runner.stderr
   ↓
[Rust replay_runner] load_and_verify_manifest
   - read manifest JSON ✓
   - locate sibling key.hex ✓ (T1 写入)
   - canonical_body_for_signing(disk_bytes) ✓
   - signer.verify(canon_body, manifest.manifest_hash, manifest.signature, fp, archive)
     - archive lookup ✓ (in-memory contains disk_fingerprint)
     - signature byte-equal ✓ (T1 sign with real HMAC)
     - manifest hash byte-equal ✓ (T1 SHA-256 over canonical bytes)
   - ✓ verify OK
   ↓
[Rust replay_runner] load_fixture(manifest.fixture_uri)
   - URI = $REPO_ROOT/.../synthetic_btcusdt.json (T3a env default)
   - parse 6 BTCUSDT 1m events ✓
   ↓
[V045 replay.run_state] UPDATE pid + status='running' (route_helpers Track A)
   ↓
[Rust replay_runner] walk events + write replay_report.json
   ↓
[V050 replay.simulated_fills] N rows INSERT (replay_runner Wave 5 internal writer)
   - evidence_source_tier = 'synthetic_replay'
   ↓
[Rust replay_runner] exit 0 + report at <output_dir>/replay_report.json
   ↓
[client] POST /api/v1/replay/runs/{run_id}/finalize
   ↓
[route_helpers.run_finalize_route] read report + validate path allowlist
   ↓
[V046 replay.report_artifacts] 1 row INSERT
[V045 replay.run_state] UPDATE status='succeeded' + completed_at + exit_code=0
   ↓
[V054 replay.audit_trail] 3 row INSERT (register/run_started/run_completed)
   ↓
[client] returns 200 with {run_id, status='succeeded', report_artifact_id, simulated_fills_count}
```

**4 表 ≥ row > 0 binding**：

| Table | Min row | Source |
|---|---:|---|
| V049 replay.experiments | 1 | R2-T1 register |
| V045 replay.run_state | 1 | T2 spawn-then-poll path + finalize UPDATE |
| V046 replay.report_artifacts | 1 | finalize handler |
| V050 replay.simulated_fills | 6 | runner walks 6 fixture events |
| V054 replay.audit_trail | 3 | register / run_started / run_completed |

**Round 7 風險**：若 V050 評估發現 `evidence_source_tier='synthetic_replay'` 違反 CLAUDE.md §九「下游 SELECT 必含 WHERE evidence_source_tier IN ('calibrated_replay', 'counterfactual_replay')」 → MLDE/Dream/attribution writer training data 不得包含此 row。**Sprint A R3 仍是 first-evidence smoke**（synthetic 是預期 tier）；R7+ 升級為 calibrated 才解封下游。

---

**PA 邊界遵守**：
- read-only design（檔案唯讀，0 修改）
- 不寫業務代碼
- 不 commit
- 派工計劃 + 副作用清單 + E2/E3/E4 重點審查 3+ 點
- 完成序列：memory.md 已追加（同次 commit 由 operator 推送或 PM Sign-off 後執行）

**End of report.**
