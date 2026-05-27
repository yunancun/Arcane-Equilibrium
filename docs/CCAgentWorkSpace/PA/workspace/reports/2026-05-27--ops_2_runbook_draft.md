# PA Draft Report — P1-OPS-2-RUNBOOK v0.9

| 欄位 | 值 |
|---|---|
| **Report ID** | `2026-05-27--ops_2_runbook_draft` |
| **作者** | PA |
| **任務** | P1-OPS-2-RUNBOOK draft（TODO §6） |
| **Deliverable** | `docs/runbooks/credential_rotation.md` v0.9（495 行）|
| **HEAD baseline** | per `CLAUDE.md §四`（未 fetch；doc-only 改動） |
| **Status** | DRAFT v0.9 — pending OP-1 first dry-run timing → v1.0 patch |

---

## 1. Source mirror（replay_signing_key_rotation.md 章節對應）

| sibling §（replay_signing_key_rotation.md）| 本 runbook § | 對應度 |
|---|---|---|
| §1 用途 | §1 用途 | direct mirror |
| §2 治理約束 invariants（9 row）| §3 治理約束（9 row）| direct mirror（換 invariant 內容）|
| §3 Initial Deployment | §4 Initial Deployment | direct mirror 但分 per-class subsection |
| §4 Scheduled Rotation（90d）+ Cron | §5 Scheduled Rotation + cadence table | direct mirror；cron drift monitoring 屬 P2 follow-up 不在本 runbook |
| §5 Emergency Rotation | §6 Emergency Rotation | direct mirror + per-class 子節 |
| §6 4 Fail-Mode | §7.1 Fail Modes 對照表（8 row）| 擴充至 8 fail-mode |
| §7 Rollback Procedure | §7.2 Rollback procedure | direct mirror |
| §8 Audit / 稽核驗證 | §8 Audit Verification SQL（4 SQL Query）| direct mirror + SQL 由 stat 命令改 PG audit log query |
| §9 修訂歷史 | §11 修訂歷史 | direct mirror |
| §10 Cross-References | §12 Cross-References | direct mirror |
| **新增**（無 sibling 對應）| §2 Secret class inventory | 新增；3 primary + 6 auxiliary table |
| **新增**（無 sibling 對應）| §9 Operator Acknowledge SOP | 新增；per task AC §9 要求 |
| **新增**（無 sibling 對應）| §10 Cross-System Verification | 新增；per task AC §8 |

9 章 mirror **PASS**（task AC）；§2/§9/§10 為 OPS-2 場景 supplementary，不替代 sibling 對應。

---

## 2. 3 secret class + 6 auxiliary 清單

### Primary（3 class，5-gate 直接依賴）
| ID | Env var | gate | Cadence |
|---|---|---|---|
| P-1 | `OPENCLAW_IPC_SECRET` | #4 secret slot（IPC handshake） | 180d |
| P-2 | `OPENCLAW_LIVE_AUTH_SIGNING_KEY` | #5 authorization HMAC | 90d |
| P-3 | `OPENCLAW_BYBIT_API_KEY` / `_API_SECRET` | #4 secret slot（exchange auth） | 90d |

### Auxiliary（6 class）
| ID | Class | Cadence |
|---|---|---|
| A-1 | `authorization.json` signed artefact | TTL auto-renew |
| A-2 | `POSTGRES_PASSWORD` | 365d |
| A-3 | `OPENCLAW_API_TOKEN` | 365d |
| A-4 | Provider AI keys（Anthropic/OpenAI/DeepSeek）| 90d per provider |
| A-5 | `replay_signing_key`（独立 runbook cross-ref） | 90d |
| A-6 | `replay_earn_preflight` HMAC（reuse P-1） | follows P-1 |

3+6 全涵蓋 **PASS**（task AC）。

---

## 3. 與 OPS-2-SECRET-SPLIT design 的 cross-ref

| OPS-2 spec § | 本 runbook 對應 § | cross-ref 內容 |
|---|---|---|
| §1 dual-purpose key 問題 | §2.1 P-1/P-2 split 標註 | runbook §2.1 標 "split 為 OPS-2-SECRET-SPLIT spec scope" |
| §2.1 兩 key 完全獨立 | §2.1 P-1/P-2 cadence table | cadence 180d/90d 同 spec §2.1 + §6 |
| §3.1 Phase 1 backward-compat | §2.1 note + §3 invariants | "Phase 1 期間 P-1+P-2 同值；first rotation 後獨立" |
| §3.2 Phase 2 panic check | §3 invariant 行 9 + §7.1 `LiveAuthSigningKeyMissing` fail-mode | "Phase 2 land 後 Live + missing → panic" |
| §6 cadence table | §5.1 cadence + alert lead | direct mirror |
| §9 hidden risk 5 條 | §3 invariants + §4 deploy + §5 rotation | 9.1（IPC 誤遷移）→ negative checklist 在 spec §8.6 已守；9.4（seed vs initial deploy）→ runbook §3 invariant "first rotation 必 from urandom"；9.5（panic ordering）→ spec 已 E1 IMPL 守；9.6（alert string）→ runbook §7.1 採新字串 |
| §10 out-of-scope | §2.2 A-5 cross-ref + §12 | A-5 走 sibling runbook；POSTGRES/API_TOKEN/AI keys 屬 auxiliary cadence 不展開 IMPL |

OPS-2 spec land 前本 runbook 為 **forward reference**（v0.9 draft）；spec Phase 2 land 後 runbook 升 v1.0（移除 backward-compat 註解）。

---

## 4. 待 OP-1 first dry-run 收 timing 後 v1.1 patch list

per E3 audit §L-2 + task §3 note，OP-1 為 OPS-2 SOP 第一次 end-to-end dry-run，**必收**下列 timing / observation 後 v1.1 patch：

| Patch ID | Section | 待收 data | 預期 patch |
|---|---|---|---|
| v1.1-T1 | §6.2.1 P-3 emergency RTO | 實測 step 1-7 cumulative duration | 校準 ≤7 min target；如 >10min → 升 §3 invariant cadence 至 60d |
| v1.1-T2 | §5.2.2 P-2 scheduled | watcher 5s respawn 實測秒數 | 如 watcher >10s → 加 §6.2.3 emergency 用 sync `/auth/renew` 替代 await |
| v1.1-T3 | §4.2.2 Bybit validate | `/api/v1/settings/api-key/live/validate` response shape | 校準 expected jq path（`.valid` vs `.is_valid` 等）|
| v1.1-T4 | §10.3 healthcheck | `passive_wait_healthcheck.py --check secret_rotation` 是否實裝 | 如未實裝 → §10.3 改 "P2 follow-up；以 §8 SQL 替代" |
| v1.1-T5 | §9 operator SOP | operator 實跑 5-step ack 是否每 step 有摩擦 | 簡化 step / 改善 wording |
| v1.1-T6 | §8 audit SQL | `governance_audit_log` table schema 是否確存 `payload->>'class'` field | 如不存 → 改 `payload->>'secret_class'` 或加 V### migration |
| v1.1-T7 | §6 emergency | operator 觀察是否漏簽 audit row（最高優先 step）| 如漏簽 → 加 mandatory pre-flight check |
| v1.1-T8 | §7.2 rollback | `.rotated.<UTC_TS>` 命名規約是否 restart_all.sh 實際輸出 | 校準 file pattern |

v1.1 patch 由 PA 在 OP-1 完成 24h 內 commit。

---

## 5. AC 自核

| AC 項 | 狀態 | 證據 |
|---|---|---|
| runbook ≥ 200 行 ≤ 500 行 | ✅ | `wc -l = 495` |
| 9 章結構 mirror replay_signing_key_rotation.md | ✅ | §1 用途，§3 治理，§4 initial，§5 scheduled，§6 emergency，§7 fail+rollback，§8 audit，§11 revision，§12 cross-ref（+ §2/§9/§10 extension）|
| 3 secret class 全涵蓋 | ✅ | §2.1 P-1/P-2/P-3 table |
| 6 auxiliary 全涵蓋 | ✅ | §2.2 A-1..A-6 table |
| audit SQL ≥ 3 query | ✅ | §8 共 4 SQL Query（rotation event / 漏排檢測 / mode drift / fingerprint collision）|
| 含 emergency path | ✅ | §6 三 primary class + 4 auxiliary class emergency steps + RTO target |
| 不引入新 code | ✅ | doc-only；引用既有 restart_all.sh / `/api/v1/*` endpoint / governance_audit_log table |
| 不派 sub-agent | ✅ | PA 直 draft；無 sub-agent 派發 |
| 不 patch TODO.md | ✅ | runbook file path 已記在 TODO §6 P1-OPS-2-RUNBOOK；本 task 不動 TODO |

**PA DESIGN DONE**：runbook 495 行、12 章節（9 章 mirror + 3 章 extension）、3+6 secret class 全涵蓋、4 SQL query、emergency RTO ≤5-7min per class。

---

## 6. Follow-up

- **CC review trigger**：本 runbook 雖 doc-only 但 reference 5-hard-gate + root principle #8 audit invariant → 建議 CC 過一遍 16 root principles checklist
- **OP-1 dry-run**：runbook v1.1 patch list 待 OP-1 first run timing capture
- **OPS-2 SECRET-SPLIT Phase 2 land 後**：runbook 升 v1.0（移除 backward-compat 註解）
- **healthcheck integration**：§10.3 提到的 `passive_wait_healthcheck.py --check secret_rotation` 屬 P2-OPS-2-AUDIT-ENDPOINT follow-up（不在本任務 scope）

**END OF DRAFT REPORT**
