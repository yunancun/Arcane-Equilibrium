# P0-OPS-2 Credential Rotation SOP + RTO Audit

**Auditor**: E3 (Security Auditor)
**Date**: 2026-05-26
**Scope**: authorization.json + Bybit api_key/secret + auxiliary long-lived secret rotation SOP design + RTO + secret-leak scan of last 30d commits (1320 commits / 1.175M diff lines)
**Baseline**: 2026-04-28 SC-001..SC-007 + 2026-05-22 full-chain audit; HEAD `4bbd4a17`
**Verdict**: **CONDITIONAL BLOCK** — 1 CRITICAL + 2 HIGH + 2 MEDIUM + 2 LOW；E3-CRIT-1 必先 closure 才能寫 OPS-2 runbook。

---

## A. Severity Summary

| Sev | Count | Finding |
|---|---:|---|
| CRITICAL | 1 | C-1 `OPENCLAW_IPC_SECRET` 同時是 IPC HMAC + authorization.json signing key（設計級缺陷）|
| HIGH | 2 | H-1 Bybit api_key 無 hot reload（rotation = engine restart ≥45s Live blackout）；H-2 三類 secret 0 rotation runbook |
| MEDIUM | 2 | M-1 IPC secret rotation 無 audit trail；M-2 emergency revoke path 無 documented procedure |
| LOW | 2 | L-1 IPC secret + POSTGRES_PASSWORD 無 drift monitoring cron；L-2 OP-1 path 45+ 天未 exercise = SOP 從未 end-to-end run |
| Secret leak | **0 NEW** | 1320 commits / 1.175M diff lines / 6 patterns；唯一 hit `replay/manifest_signer.rs:663` test fixture（false positive）|

---

## B. Three Long-Lived Secret Class Inventory

| Class | Path | TTL | Cadence today | Hot reload | Audit trail |
|---|---|---|---|---|---|
| (a) `authorization.json` | `$OPENCLAW_SECRETS_DIR/live/` | T0 hrs / T3 24h+ | 自動 via TTL；operator renew per TTL | **YES** ≤5s via `live_auth_watcher` | YES via `_write_signed_live_authorization` WARN log + GovernanceHub SM |
| (b) `OPENCLAW_IPC_SECRET` (dual purpose: IPC HMAC + live-auth signing) | `$SECRETS_ROOT/environment_files/ipc_secret.txt` | **無 TTL** | **0 rotation cadence** | NO | **NO** |
| (c) Bybit `api_key/secret` | `$OPENCLAW_SECRETS_DIR/<slot>/api_key + api_secret` | Bybit policy ~90d | Operator OP-1 hand action | **NO** — Rust `BybitRestClient` 至 ctor time owned String；rotation 需 full engine restart | YES masked log only (correct) |
| (d) `POSTGRES_PASSWORD` | `basic_system_services.env` | None | None | NO | NO |
| (e) `OPENCLAW_API_TOKEN` | env / `.secrets/api_token` | None (per SC-001) | None | NO | Partial |
| (f) Anthropic / OpenAI / DeepSeek | `$SECRETS_ROOT/secret_files/ai/<provider>/api_key` | Per provider | None | NO | NO |

---

## C. Findings (root-cause + fix)

### [E3-CRIT-1] Single key conflation: `OPENCLAW_IPC_SECRET` dual purpose

**Files**: `rust/openclaw_engine/src/live_authorization.rs:360`（用 `OPENCLAW_IPC_SECRET` 簽 authorization.json）+ `rust/openclaw_engine/src/main.rs:399-407`（fatal-panic if Live + missing IPC secret）+ `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py:221`（Python 簽名 path 用同 env var）。

**Attack path**：
1. `OPENCLAW_IPC_SECRET` leak（process memory dump / same-uid env-var inspection per SC-005 / launchd env leak per SC-006）→ 攻擊者 BOTH (a) 簽偽造 IPC commands AND (b) 偽造 authorization.json with arbitrary tier/TTL/operator_id 並寫入磁碟。
2. Rust 會接受偽造 authorization（HMAC verify 通過，key 對的），Live pipeline 用 attacker-chosen parameters 啟動。
3. Rotation pressure：rotate `OPENCLAW_IPC_SECRET` atomically invalidates ALL current signed authorizations → Live pipeline pause with `AuthError::BadSignature` until operator re-run `/auth/renew`。

**為何 CRITICAL 非 HIGH**：dual-purpose 設計使 rotation 邏輯**inherently fragile** — 不能只 rotate IPC HMAC key 而不破 live authorization，也不能只 rotate live-auth signing key（不存在獨立 concept）。**Design defect**，OPS-2 SOP 無法解決，必須 split。

**Fix**：
- 新增 `$SECRETS_ROOT/environment_files/live_auth_signing_key.txt`（獨立 file + 獨立 env `OPENCLAW_LIVE_AUTH_SIGNING_KEY`）。
- Python `_write_signed_live_authorization` 讀新 env；Rust `live_authorization::load_and_verify` 讀新 env。
- Migration：首次 deploy 若新 env unset 則 fallback `OPENCLAW_IPC_SECRET` + WARN。14d soak 後移除 fallback。
- 兩 key cadence 獨立記錄（live-auth signing 90d / IPC HMAC 180d — different blast radius）。
- Owner：E1 + CC sign-off（touches 5-hard-gate #4 secret slot + #5 authorization.json HMAC）。

**Verification**：unit test `verify_in_memory` mismatched key → `BadSignature`；integration test rotate IPC HMAC while old-key signed authorization.json 仍 valid → Live pipeline 保持 running，IPC reconnect required。

**Block**：YES for Sprint 4 first Live W18-21。

---

### [E3-HIGH-1] Bybit api_key/secret 無 hot reload — rotation = engine restart 強制 Live downtime

**Files**: `rust/openclaw_engine/src/bybit_rest_client.rs:929-989`（REST client owns `api_key` / `api_secret` String at ctor）+ `helper_scripts/restart_all.sh:148-170`（`--keep-auth` flag 不 reload credentials）。

**Evidence**：grep `reload_key|reload_credentials|hot.?reload.*credentials|api_key.*reload` → 0 hits。對比 `authorization.json` IS hot-reloaded by `live_auth_watcher` 每 5s + IPC trigger。

**Operational path**：
1. Operator Bybit Web UI key reissue (OP-1-a..c) → `POST /api/v1/settings/api-key/live` 寫盤。
2. Settings route validate via Bybit REST + 寫盤 (`settings_routes.py:1099`)。
3. **Running Rust engine 仍用 OLD api_key** — in-flight orders 由 old key 簽（可能成功若 Bybit 未 invalidate，或 auth error）。
4. Take effect：`bash helper_scripts/restart_all.sh --rebuild`（full engine teardown ~30s + spawn）。
5. 該 window 內：Live pipeline OFFLINE，in-flight orders 可能 orphan，position 不被 actively managed。

**RTO Impact**: ≥30s engine restart + ≥10s IPC reconnect + Live pipeline spawn + auth re-verify = **≥45s Live blackout per rotation**。在 operator 15-min RTO budget 內，但**需 explicit pre-rotation pause + post-rotation healthcheck**。

**Fix (short-term Sprint 4 blocker)**：SOP 含 pre-rotation steps：
1. `POST /api/v1/live/auth/revoke`（刪 authorization.json → Rust watcher 拆 Live ≤5s）
2. `POST /api/v1/settings/api-key/live`（寫新 key）
3. `bash helper_scripts/restart_all.sh --rebuild`（engine reload 拾新 key）
4. `POST /api/v1/live/auth/renew`（簽新 authorization.json → watcher respawn）
5. Healthcheck: GET `/api/v1/live/auth/trust-status` verify `signed_authorization.present=true` + `bybit_endpoint` match expected

**Fix (long-term P2 post-Sprint 4)**：`Arc<ArcSwap<BybitCredentials>>` to REST client + IPC handler `reload_bybit_credentials`（5s rotation parity with authorization.json）。

**Block**：YES for Sprint 4 first Live W18-21（SOP must draft + dry-run on OP-1 path before mainnet）。

---

### [E3-HIGH-2] 三類 secret 0 rotation runbook（只 replay_signing_key 有）

**Evidence**：`find docs/runbooks/ -name "*.md"` 唯一 `replay_signing_key_rotation.md` + sibling 子目錄。`docs/audit/secrets_credentials.md`（2026-04-28）defer rotation runbook design。

**Operational risk**：無 runbook → OP-1 a-f hand actions ad-hoc → 高機率漏 step（e.g. 忘 `--rebuild` 後 key swap → Live 用 old key）。Emergency rotation 無 playbook = 高 failure mode。No rollback path 文件。

**Fix**：撰寫 `docs/runbooks/credential_rotation.md` mirror `replay_signing_key_rotation.md` 結構（§G skeleton 見下）。

**Block**：YES — SOP 本身是 deliverable。

---

### [E3-MED-1] `OPENCLAW_IPC_SECRET` rotation 無 audit trail

**Files**: `helper_scripts/restart_all.sh:143-145` 只做 `chmod 600`，無 rotation event 寫入 `learning.governance_audit_log`。

**Risk**：Operator silent rotate IPC secret → 6 個月後 forensic review 無法判定何時 rotation、哪些 old authorizations 應 invalid、是否 coincide with anomalous behavior。違反 root principle 8 ("每筆交易必須可重建可解釋") at secret-management layer。

**Fix**：`POST /api/v1/security/ipc-secret/rotate` endpoint（operator-gated）：
1. Read new value from request body
2. Backup old to `ipc_secret.txt.rotated.<UTC_TS>` (chmod 0000)
3. Write new (chmod 600)
4. Audit row：`actor + action='ipc_secret_rotation' + old_fingerprint_first8 + new_fingerprint_first8 + ts`
5. Return required follow-ups："engine restart required + Live re-renew required"

---

### [E3-MED-2] Emergency revoke path undocumented

**Risk**：operator 疑 Bybit api_key leak → 必須 6-step：
1. Bybit Web UI revoke key (5min)
2. OpenClaw revoke local copy via `POST /api/v1/live/auth/revoke`（拆 Live ≤5s）
3. Verify via `GET /api/v1/live/session/status`
4. Quarantine old key file: `mv api_key api_key.QUARANTINED.<UTC_TS> && chmod 0000`
5. Issue new Bybit key
6. Full SOP per H-1

**Today**：6-step path 0 documented，operator 緊急下自己 derive。

**Fix**：runbook §5 (mirror `replay_signing_key_rotation.md §5`)。

---

### [E3-LOW-1] 無 drift monitoring cron for IPC HMAC + POSTGRES_PASSWORD

**Risk**：無 cron / healthcheck 追 `ipc_secret.txt` mtime → 18-month-old IPC secret 不被偵測。對比 `replay_key_rotation_check.sh` cron 已存在。

**Fix**：`helper_scripts/cron/long_lived_secret_drift_check.sh` report mtime + alert (exit 1 + audit row) if mtime > 365d (IPC HMAC) or > 90d (Bybit live key)。

---

### [E3-LOW-2] OP-1 path 45+ 天未動 = SOP 從未 end-to-end exercised

**Evidence**：TODO §6 `P1-EARN-WAVE-C-FIRST-STAKE-RUNTIME` "Bybit Web UI key 重發（< 2026-04-09 key 已過期 ≥45 天）"；TODO §7 OP-1 a-f 5-10 min。

**Risk**：operator 真跑 OP-1 = 跑**untested procedure on production rotation path**。

**Recommend**：用 OP-1 當 **OPS-2 SOP 第一次 end-to-end dry-run** — capture timing + fail-modes + observations → feed back into runbook v1.1 BEFORE Sprint 4 first Live。

---

## D. Proposed Rotation Cadence

| Secret class | Scheduled | Emergency revoke | RTO target | Audit |
|---|---|---|---|---|
| (a) authorization.json | 自動 via TTL | `/api/v1/live/auth/revoke` ≤5s | ≤5s teardown / ≤5s respawn | SM-01 + WARN log existing |
| (b) IPC HMAC + live-auth signing (split per C-1) | **180d each** (different blast radius)；alert 165d，force 180d | per §5 | **≤15min total** | new audit endpoint per M-1 |
| (c) Bybit api_key/secret | **90d** (align Bybit policy)；alert 75d (15d lead time) | Bybit Web UI revoke + local quarantine + per §5 | **≤15min total** (per H-1 SOP) | `settings_routes.py` log + governance audit row |
| (d) POSTGRES_PASSWORD | **365d**；alert 350d | PG `ALTER USER` + coordinated restart | ≤30min | new audit row |
| (e) OPENCLAW_API_TOKEN | per SC-001 fix（default fail-closed on `change-me`）；365d | regenerate + invalidate old | ≤5min (API restart only) | log + audit row |
| (f) Provider AI keys | per provider 90d default | Provider Web UI revoke | ≤5min | per provider |

---

## E. RTO Estimate for H-1 6-step SOP

| Step | Action | Duration | Cumulative |
|---|---|---|---|
| 1 | `/api/v1/live/auth/revoke` → Rust teardown | 5s | 5s |
| 2 | Bybit Web UI key reissue | 2-5 min | 2-5 min |
| 3 | `/api/v1/settings/api-key/live` validate + write | 5-10s | 2-5 min |
| 4 | `restart_all.sh --rebuild` engine + API | 30-60s | 3-6 min |
| 5 | `/api/v1/live/auth/renew` sign authorization.json | 1s | 3-6 min |
| 6 | Healthcheck loop until watcher respawn | ≤5s | 3-6 min |
| 7 | Verify orders accepted (small test order) | 30-60s | **4-7 min** |

**Target ≤15min RTO 達成**（SOP 遵循）；**≥20min likely** w/o SOP under operator improvisation。

---

## F. Secret-Leak Scan Result

**Scope**: 1320 commits since 2026-04-26（30 days）/ 1.175M diff lines / 6 patterns（A/B/C/D/E/G）。

| Pattern | Hits | Note |
|---|---:|---|
| A hardcoded secrets | 0 | — |
| B high-entropy hex/base64 | 1 | `rust/openclaw_engine/src/replay/manifest_signer.rs:663` `FIXTURE_KEY_HEX`（false positive，inside `#[cfg(test)]`）|
| C Bybit markers `X-BAPI-SIGN` | 8 | All legitimate header construction，no leak |
| D log statements with secret name in scope | 7 files | Manual inspection: all for routing/metadata（`authorization_id`, masked `key_hint`），no payload leak |
| E env var with secret name in log | 0 | — |
| G `/home/ncyu` or `/Users/<name>` in secret path | 0 | Production；only doc/runbook examples |
| F commit messages | 0 | — |

**Net new leak findings**: **0 CRITICAL / 0 HIGH / 0 MEDIUM / 0 LOW**。

**Pre-Sprint 4 P2 recommendation**：install `gitleaks` or `detect-secrets` pre-commit hook（`ls .git/hooks/` 只有 `.sample`，**無 enforcement hook**）。

---

## G. Proposed OPS-2 Runbook Skeleton

撰寫 at `docs/runbooks/credential_rotation.md` mirror `replay_signing_key_rotation.md` structure：

- §1 Why this runbook exists（cover 3 + auxiliary classes）
- §2 Governance Invariants（HMAC algo / file modes / audit row req / retention windows）
- §3 Initial Deployment（per class）
- §4 Scheduled Rotation（per class，cadence table per §D）
- §5 Emergency Rotation（per class，quarantine + immediate revoke + post-mortem req）
- §6 Fail Modes（per class — `AuthError::*` 意義 + operator action）
- §7 Rollback（per class — restore previous secret from `.rotated.*` backup）
- §8 Audit Verification（SQL queries per class to verify rotation actually landed）
- §9 Revision History

**Owner**: PA + E1 (drafts) → E3 + CC (review) → PM (approve) → BB sign-off (exchange-facing impact)
**ETA**: 1 sprint after C-1 split lands（runbook references new env var names）

---

## H. P1/P2 Follow-up Backlog

| ID | Sev | Description | Owner | Sprint |
|---|---|---|---|---|
| `P1-OPS-2-SECRET-SPLIT` | P1 | Split `OPENCLAW_IPC_SECRET` → IPC HMAC + live-auth signing key（C-1）| E1 + CC | Sprint 3 |
| `P1-OPS-2-RUNBOOK` | P1 | Author `docs/runbooks/credential_rotation.md`（H-2）| PA + E1 | Sprint 3 |
| `P1-OPS-2-DRY-RUN` | P1 | OP-1 = first end-to-end dry-run of OPS-2 SOP（L-2）| Operator + PM | OP-1 unblock D+2-D+3 |
| `P2-OPS-2-HOTRELOAD` | P2 | `Arc<ArcSwap<BybitCredentials>>` + IPC reload handler（H-1 long-term）| E1 | Post-Sprint 4 |
| `P2-OPS-2-AUDIT-ENDPOINT` | P2 | `POST /api/v1/security/ipc-secret/rotate` + governance audit row（M-1）| E1 | Post-Sprint 4 |
| `P2-OPS-2-CRON-DRIFT` | P2 | `helper_scripts/cron/long_lived_secret_drift_check.sh`（L-1）| E1 | Post-Sprint 4 |
| `P2-OPS-2-GITLEAKS` | P2 | `gitleaks` pre-commit hook | E1 + PA | Pre-Sprint 4 |
| `P2-OPS-2-SC-FOLLOWUP` | P2 | SC-001/002/004..007 跟進（outside OPS-2 scope）| per-finding | Post-Sprint 4 |

---

## I. Safety Invariants Check (I2 / I3)

- **I2 (Signed authorization)**: Maintained。C-1 fix **strengthens** I2（separates IPC trust boundary from authorization trust boundary）。
- **I3 (LiveDemo no degradation)**: Maintained。所有 rotation cadence 同 for LiveDemo vs Mainnet（per `live_authorization.rs:23` 設計）。
- **5 hard gates**: C-1 touches gate #4（secret slot）+ #5（authorization.json HMAC）— 需 E3 + CC dual review per CLAUDE.md Hard Boundaries。

---

**E3 AUDIT DONE**：1 CRITICAL / 2 HIGH / 2 MEDIUM / 2 LOW；0 NEW secret leak finding。Sprint 4 first Live W18-21 closure 條件 = E3-CRIT-1 + H-1 + H-2 land。
