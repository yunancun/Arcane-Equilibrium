# S2 Operator Action Packet v1 — `DRAFT_NOT_EXECUTABLE`

- **Program**: `AIML-LONG-LIVED-LANDING-V2` · Sprint 2（runtime 修復）
- **Packet 狀態**: `DRAFT_NOT_EXECUTABLE`（2026-07-28 獨立審核校正）
- **Source 綁定**: 全部五個 effect-session source predicates 已 `SOURCE_READY` 並 landed
  （S2.2A PR #121、S2.3 PR #122、S2.0 PR #127、S2.1 PR #129、S2.4 PR #145/#146、
  S2.5＋S2.2B seam PR #148/#150）。本 packet 綁定其宣告 head（見 TODO marker 與
  `receipts/S2.4-WP4-W5/`：八件 artifact bound to `5be472193`、
  `obligation_ledger_digest = sha256:57696d69eb258c0202faea5541859b05e53fd1985e1b09914d34ddd08c8e53ea`、28 條未關閉義務）。
- **這不是授權，也不是可執行 packet**：本文件保留 effect DAG 與逐步草案，但
  `S2E.0`–`S2E.5` 尚未完成；fresh external operator authorization **不是唯一
  blocker**。九項 authority 全 false；`S1` disposable 授權**不可沿用**
  （AGENTS.md／delivery-protocol A2 明文）；每一步都要**新的、exact、typed、
  out-of-band** 授權，簽章私鑰不在 Mac 也不在 trade-core。

> **禁止執行**：本版缺 S2.4-AMEND-1/2、claim-gated effect routing、trusted-host
> runners、S2.5 durable-state hardening、S2.2B runtime-attestor execution/verification
> 與整鏈 disposable rehearsal。Current authority 以 `TODO.md` 的
> `S2_EFFECT_EXECUTION_READINESS_ACTIVE` 為準；完整證據與重發條件見
> `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-28--aiml_s2_source_and_effect_readiness_audit.md`。

## Effect DAG（串行，§1.2 更正版）

```
S2.0 → S2.4 → S2.5A → S2.1 → S2.5B → S2.2B
```

S2.1 的 quiesce/restore drill 在 S2.4 install＋S2.5A start 之後（真 drill 需要
installed+started runtime）；`S2.1@EFFECT_DONE` 不是 S2.4 predecessor。

## 逐步（每步：fresh SSHSIG permit → typed intent → Adapter → 獨立 OPS postcheck）

| # | Step | Adapter／source seam | 授權形制 | Rollback | Postcheck |
|---|---|---|---|---|---|
| 1 | `S2.0` production PG observer bootstrap（role/auth/ACL only） | `pg_observer_bootstrap_adapter_v1`（design `S2.0-observer-bootstrap-source-adapter.md`） | operator SSHSIG over exact intent＋source head | typed revoke/drop script（seam 內建） | 獨立 write/role/search-path denial 驗證 |
| 2 | 中繼 exact-head 三端 sync（非 deploy） | — | — | — | 三端 head 相等 |
| 3 | `S2.4` credential/PG/unit/install＋one-component restore | `s2_4` aggregate（design `S2.4-install-source-seams.md`；`w5-emit` 鏈為 source 證據） | 每 component 一張 profile-bound permit（§5.6 家族） | per-component typed rollback＋journal/WAL | 獨立 OPS per-component postcheck；`s2_4_install_effect_receipt_v1` |
| 4 | `S2.5A` `enable --now`＋running attestation | `agent_governance_s2_5.py`（design `S2.5-running-attestation-source-seam.md`） | `S2_5A_START` permit（TTL≤15min、consume-once ledger、TTL 預算不等式） | rollback-to-disabled（identity-tuple 執法；NOT_RESTORED ⇒ RECOVERY） | 五維 running attestation 由 trusted-host attestor 簽章（`RUNNING_ATTESTED`） |
| 5 | `S2.1` quiesce/restore drill | `alr_quiesce_fence_adapter_v1`（design `S2.1-quiesce-source-seam.md`） | 該 seam 既定 permit 形制 | drill restore（S2.1 §4） | 獨立 quiesce observation |
| 6 | `S2.5B` watchdog-reset-last＋final attestation | 同 step 4 seam（`S2_5B_FINAL`） | `S2_5B_FINAL` permit（綁 pre-drill attestation digest＋drill receipt digest） | 同 seam rollback；consumed permit 永不因 rollback 釋放 | `FINAL_ATTESTED`（supervening restart ⇒ 不可達 RESET_CLEAN） |
| 7 | `S2.2B` ingestion compatibility revalidation（`REMOTE_READONLY`） | `agent_governance_s2_2b.py`＋`ingestion_compatibility_receipt_v1` | 消費 `S2.5B@EFFECT_DONE` 的 production `FINAL_ATTESTED` 錨（runtime attestor SSHSIG 於本步驗） | 無 mutation（readonly） | V151-V160 逐項 revalidation 全 MATCH；唯一簽發 LR1 runtime `DONE` |

## 重發前置（全部完成後才可重新簽發 Operator packet）

1. **`S2.4-AMEND-1`**（gate step 3）：dependency-refresh 進 APPLY 的 ingress＋terminal
   receipt 的 §3 refresh-digest 欄位＋§9.1 profile 穿線（PROGRESS「W5 PM-owned
   obligations adjudication」rows 16/23/26）。shipped 依賴身分已過期，無此修正案
   step 3 無法出具 §3-conformant receipt。
2. **`S2.4-AMEND-2`**（gate step 3 的 `PG_ROLE_ACL_MIGRATION`）：plan-derived
   `expected_topology`（row 25）。
3. **S2.5 effect-lane 深度項**（arm step 4 前建議收口）：reconcile 摺進鎖窗（E2
   tranche-2 F2）、install-lock 與 lifecycle-lock 語義分離（F3）、release 失敗
   observability（F4）、journal integrity 綁定（tranche-1b note-1）。
4. **W6/W6B ledger**：28 條義務（`receipts/S2.4-WP4-W5/S2.4-WP4-W5-derivation-record.json`
   `remaining_owned_obligations`）中 owner=W6(4)/W6B(15) 者屬 install-execution 波次，
   在對應 step 的 intake 逐條消化。

## S2_CLOSED 判準（本 packet 全部執行完的驗收）

Linux `trade-core` 上 learning service 真實 installed/enabled/active、具
platform-attested running evidence（trusted-host attestor 簽章鏈）、
`ingestion_compatibility_receipt_v1` 有效（V151-V160 全 MATCH＋production
`FINAL_ATTESTED` 錨）、全部 postcheck/rollback 證據落 repo。缺任一項即非
`S2_CLOSED`。

## 誠實邊界

source seams 的全部測試證據（committed clone 6306/46/0 於 tranche-2 head）只證
source 結構；runtime/effect 事實需 `PLATFORM_OR_EXTERNAL_ATTESTED` 證據。本 packet
簽發當下 runtime 現況＝2026-07-27 Linux 唯讀觀察 learning service
`inactive`/`not-found`，未變更。
