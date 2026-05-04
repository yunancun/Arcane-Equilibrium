# E2 R3 Round 6 Adversarial Review — RETURN to E1

**Date**: 2026-05-05 · **HEAD**: `e9d547c0` (working tree only, not committed)
**Reviewer**: E2
**E1 sign-off**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_a_r3_round6_impl.md`
**PA design**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_a_r3_round6_task_dag.md`
**Persistence**: Persisted by PM per E2 closure protocol.

---

## §1. Executive verdict — RETURN to E1

| 嚴重性 | Count | 動作 |
|---|---:|---|
| CRITICAL | 0 | — |
| **HIGH** | **1** | **退 E1 修：FINDING-1 env override 缺 live profile gate** |
| MEDIUM | 0 | — |
| LOW | 1 | 退 E1 修（建議併入 round 7 PR）：FINDING-2 503 detail leak |

**Verdict**: RETURN to E1 — FINDING-1 是 secret-leak design hole（HIGH），不 block live trading 但違反 CLAUDE.md §九 SEC-08 / Sprint 1 Track C P0-2 既有 pattern；必修才能進 E4。FINDING-2 LOW 可同 round fix（10 LOC 範圍）。

8 條 §九 checklist + 9 條 OpenClaw 特殊：全 PASS（除 finding 1/2）。xlang invariant 13/13 PASS · replay sibling 141/142 PASS（1 skip opt-in / 0 fail）· 跨平台 grep 0 hit · placeholder grep 0 production hit · stderr=DEVNULL 0 hit · bash -n PASS · LOC 1485 < 1500 hard cap.

---

## §2. T1 placeholder retirement + fail-closed + canonical_bytes — PASS

- placeholder grep on production paths: route_helpers.py 3 hits 全在 MAINTAINER warning docstring（line 756 / 863-864 / 944-945，後兩處是 `‘‘`-quoted reference）；runtime emit 0 hit ✓
- fail-closed 路徑: `_resolve_manifest_signing_key()` step 3 `raise ValueError("manifest_signing_key_unavailable")` 永不 fallback 回 placeholder ✓
- env override path 缺 file / wrong length / non-hex 全 fail-closed：5 個 ValueError sub-reason ✓
- canonical_bytes contract: 完整重用 helper、不複製 sort_keys/separators kwargs；xlang 13/13 PASS confirms ✓
- key.hex 寫 disk 對齊 Rust：output_dir / "key.hex"（Python L969）對齊 Rust replay_runner.rs:544-547 ✓；compute_key_fingerprint(file_content) Python L802 對齊 Rust manifest_signer.rs:480 ✓
- envelope leak defense: 簽前 body dict 移除 envelope，簽後再 inject (L967-1003) ✓

FINDING-1 (HIGH) — 見 §7。

---

## §3. T2 stderr capture + path traversal + 2KB cap — PASS（FINDING-2 LOW）

- DEVNULL 完全移除：stderr=stderr_fh (route_helpers.py:584)，grep stderr=subprocess.DEVNULL 0 hit ✓
- path allowlist 守門：stderr_path = output_dir / "replay_runner.stderr" → artifact_path_within_allowlist(stderr_path) (L548-554) ✓
- 2KB read cap 演算法：SEEK_END + max(0, size - 2048) + read(2048) 驗算 64KB → 2048 char 正確 ✓
- subprocess fd safety: parent stderr_fh 在 try/finally close ✓
- child writes disk → 永不 block buffer (PA H4 緩解) ✓
- 256-byte reason_code excerpt cap + 2KB disk file cap 兩層 ✓
- post-mortem 路徑保留：subprocess alive / dies / exits 0 三種路徑 stderr file 都落盤 ✓

FINDING-2 (LOW) — spawn_died_early reason 含 stderr excerpt 進 503 detail JSON message → leak server path / fingerprint hex 給 API client。詳見 §7。

---

## §4. T3a env injection + override 優先級 — PASS

- env block 對齊既有 pattern：與 OPENCLAW_BASE_DIR / OPENCLAW_DATA_DIR 同 line（restart_all.sh:442-450）✓
- default fixture 真存在：rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json git tracked + schema_version=1 + **10 events**（E1 報告 / PA 都聲稱 6 events，**實際 10 events** — 對 acceptance 不影響但 E1 文檔需勘誤）
- if [ ! -f ] empty-string fallback：fixture 缺時 register handler 走明確 503 ✓
- 跨平台：$base_dir = ${OPENCLAW_BASE_DIR:-$REPO_ROOT}，Mac dev / Linux 部署都對齊 ✓
- 3-tier fallback chain：URI override > DEFAULT env > legacy <output_dir>/fixture.json ✓

---

## §5. T4 test 覆蓋面 + placeholder grep + xlang reuse — PASS

- 24 個 test case + 1 skip：T4-1 (11) + T4-2 (7) + T4-3 (5) + T4-4 (1 skip opt-in) = 24 unit + 1 e2e；141 PASS / 1 skip / 0 fail
- placeholder grep 在 test 中：test 真用 grep `assert "placeholder_signature_wave6" not in written / serialised`（覆蓋 PA H9 mitigation）✓
- cross-language fixture 重用：T4-1 reconstruct canonical body + signer.verify(canonical, hash, sig, fp, archive) 完整 mirror Rust verify path ✓
- e2e smoke 真實 spawn Rust binary（不 mock subprocess）：T4-4 透過 OPENCLAW_REPLAY_E2E_SMOKE=1 opt-in ✓
- mock-only 假綠教訓對齊 ✓

---

## §6. 跨平台 + LOC + Singleton 合規 — PASS

| 檢查 | 結果 |
|---|---|
| /home/ncyu / /Users/ncyu 在 6 改動 file | 0 hit ✓ |
| route_helpers.py LOC | 1485 / 1500 hard cap ✓（800 警告線 Wave 4 已破，PA accepted；R7+ 必拆 manifest_provisioning.py） |
| restart_all.sh LOC | 492 / 800 ✓ |
| 4 新 test file LOC | 全 < 800 ✓ |
| Singleton 表 §九 | 4 新 module-level constant 全 immutable str/tuple，**不需** 登記（對齊 ADVISORY_LOCK_GLOBAL_KEY 既有 pattern）✓ |
| 雙語注釋 | MODULE_NOTE / docstring / inline 中英對照齊備 ✓ |
| bash -n restart_all.sh | PASS ✓ |
| git status --porcelain sign-off | 6 file 對應 round 6 IMPL；3 sibling-CC artifact 不 block ✓ |

---

## §7. 退回 E1 修的條目

### FINDING-1 (HIGH) — `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env override 缺 live profile gate

**位置**：`route_helpers.py:765-803`（`_resolve_manifest_signing_key()` step 1）

**問題**：production live profile 下，operator/attacker 設此 env 指向任意 path（任意 mode、任意 symlink）會繞過 R2-T3 step 2 既有的 mode 0o600 + symlink-injection guard + path traversal guard。step 1 完全沒檢查 file mode、沒做 symlink resolve、沒 fail-closed。

**PA 設計與實作不一致**：PA design §7 Q2 + §5 E3 #3 自承「dev/test only path」「Live profile 守門由 (b) R2-T3 既有 mode/symlink 邏輯涵蓋」— 但 step 1 在 step 2 之前，step 1 完全沒 live profile gate，PA 描述的「dev/test only」並未實作為 production gate。

**對齊既有 pattern**：Sprint 1 Track C P0-2 已立過模式：`OPENCLAW_REPLAY_VERIFY_TEST_KEY` 在 production 由 `is_live_release_profile()` 阻斷（route_helpers.py:1188-1205 + 1441）；Round 6 新增 `OPENCLAW_REPLAY_SIGNING_KEY_FILE` 是同類測試/dev override env，**沒對齊** P0-2 gate。

**修法（最小改動 + 對齊既有 pattern）**：step 1 開頭加 live profile gate：

```python
override_path_str = os.environ.get(SIGNING_KEY_FILE_ENV_VAR, "").strip()
if override_path_str:
    if is_live_release_profile():
        log.warning(
            "signing key env override blocked under live profile: "
            "OPENCLAW_REPLAY_SIGNING_KEY_FILE=%s; falling through to secrets-dir",
            override_path_str,
        )
        raise ValueError("signing_key_file_env_override_blocked_in_live_profile")
    # ... rest of step 1 unchanged ...
```

**測試新增**：`test_resolve_signing_key_env_override_blocked_in_live_profile`：set `OPENCLAW_RELEASE_PROFILE=live` + `OPENCLAW_REPLAY_SIGNING_KEY_FILE=...` → expect ValueError contains `signing_key_file_env_override_blocked_in_live_profile`。

**LOC**：production code +5 LOC，test +10 LOC，total +15 LOC（< 1500 限）。

### FINDING-2 (LOW) — spawn_died_early 503 detail leak stderr excerpt

**位置**：
- route_helpers.py:628-630（reason_code 含 stderr excerpt）
- app/replay_routes.py:678（`detail.message = f"replay_runner failed to spawn: {pg_err}"` leak 給 client）

**問題**：spawn_died_early reason 含 256 byte stderr excerpt 進 HTTPException 503 detail JSON。stderr 主要含 server-side 已知資訊（output_dir absolute path、fingerprint hex、verify mode label），不含 OS secret / API key，但仍違反 §九 SEC-04「detail=str(e) → 'Internal server error'」原則 + 可作為 IDOR 線索（path leak）。

**修法（最小改動）**：
- spawn_replay_runner 仍寫 stderr file disk + log warning 含 stderr excerpt（不變）
- 但 `return None, f"spawn_died_early:exit={rc}"`（**不含** stderr= excerpt）
- replay_routes.py:678 的 503 detail 從 `f"replay_runner failed to spawn: {pg_err}"` 改為 `"replay_runner failed to spawn; check stderr file at <output_dir>/replay_runner.stderr"` 或加 reason_code `replay_runner_spawn_failed:exit=N` 不含 stderr text

**LOC**：~10 LOC + 微調 1 個 unit test。

**嚴重性 LOW**：實際洩漏的是 absolute path / fingerprint 16-hex，無 secret value；但收緊符合 SEC-04 原則。可同 finding-1 round 7 fix。

---

## §8. E2 直修記錄

無。Finding 1/2 屬業務邏輯邊界（live profile gate / detail leak design），E2 不代寫業務代碼。皆退回 E1 修。

---

## §9. E2 → E4 接手條件（**未滿足**）

- ✗ FINDING-1 HIGH 必修（live profile gate；阻斷 secret leak design hole）
- ✗ FINDING-2 LOW 建議同 round fix（detail leak 收緊；對齊 SEC-04）
- ✓ xlang invariant 13/13 PASS（已驗）
- ✓ replay sibling 141 PASS / 1 skip / 0 regression（已驗）
- ✓ 跨平台 / 雙語 / LOC / Singleton / placeholder grep 全合規

**接手條件**：E1 修 FINDING-1（HIGH 必）+ FINDING-2（LOW 建議）後 → E2 round 7 verification（pin-point fix verdict 即可）→ PASS to E4.

---

E2 REVIEW DONE: RETURN to E1 (1 HIGH + 1 LOW) · 0 E2 直修
