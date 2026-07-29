# S2 Operator Action Packet v1 — `DRAFT_NOT_EXECUTABLE`

- **Program**: `AIML-LONG-LIVED-LANDING-V2` · Sprint 2（runtime 修復）
- **Packet 狀態**: `DRAFT_NOT_EXECUTABLE`（2026-07-29 W0 交接校正）
- **Source 綁定**: 全部七個 narrow source predicates 已 `SOURCE_READY` 並 landed
  （S2.2A PR #121、S2.3 PR #122、S2.0 PR #127、S2.1 PR #129、S2.4 PR #145/#146、
  S2.5＋S2.2B seam PR #148/#150）。本 packet 綁定其宣告 head（見 TODO marker 與
  `receipts/S2.4-WP4-W5/`：八件 artifact bound to
  `f30ede36134f1464cef4bc025f808b931aebe180`，carrier
  `3df9d2f451ceb7ab66117de6e33fd882d59a9531`，
  `obligation_ledger_digest = sha256:90f9261845b4782e577ef34e40369b3bcaf30381ce46d62d7246c087b3ed208e`；
  28-row ledger 中五列已是 `CLOSED_BY_*`，其餘仍依 owner 關閉／裁決）。
- **Effect-readiness**: 九個拆分包已完成 **5/9**：`S2E.0`、`S2E.1`、
  `S2E.2a`、`S2E.2b-1`、`S2E.3`。唯一 ACTIVE 入口為
  `S2E.2b-2`；剩餘順序 `S2E.2b-2 → S2E.2b-3 → S2E.4 → S2E.5`。
  production effect 仍為 **0/6**，S2 未關閉。
- **這不是授權，也不是可執行 packet**：本文件保留 effect DAG 與逐步草案，但
  `S2E.2b-2`–`S2E.5` 尚未完成；fresh external operator authorization **不是唯一
  blocker**。九項 authority 全 false；`S1` disposable 授權**不可沿用**
  （AGENTS.md／delivery-protocol A2 明文）；每一步都要**新的、exact、typed、
  out-of-band** 授權，簽章私鑰不在 Mac 也不在 trade-core。

> **禁止執行**：S2.4-AMEND-1/2、claim-gated routing、S2.0/S2.1 runners、
> S2.5 durability hardening 與 S2.4 recovery core 已 source-landed；本版仍缺
> 真 S2.5 host/recovery lane、S2.4 五支 row drivers 與 kernel amendments、
> authenticated runtime capture／closure／trusted-attestor lane，以及整鏈
> disposable rehearsal。Current authority 以 `TODO.md` 的
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

## S2.0 EFFECT operator 前置（本 draft 只記錄，不授權執行）

1. `pg_observer_bootstrap_adapter_v1` 的 adapter step 6 會拒絕預先存在的
   observer role，而 observer role 於 step 7 才建立；因此
   `GRANT <observer> TO <login>` 必須 **lazy** 執行，位置嚴格在 adapter
   steps **7/8 之間**，不得預建 membership。
2. 專用 login role 必須是 **`NOSUPERUSER`**；否則 42501 denial proof 無效。
3. 授權窗口結束後必須執行對稱的 **`REVOKE <observer> FROM <login>`**，並由
   獨立 postcheck 證明 membership 已撤回。
4. `credential_escalation_connect` 必須由 operator **帶外配置**；不得由 repo、
   packet、runner 或 disposable fixture 自行生成／冒充。

## 重發前置（全部完成後才可重新簽發 Operator packet）

1. **已完成、不得重派**：`S2E.0` 已落地 S2.4-AMEND-1/2；`S2E.1` 已落地
   claim-gated routing/closure binding；`S2E.2a` 已落地 trusted-host kernel、
   observer 與 S2.0/S2.1 runners；`S2E.3` 已落地 S2.5 dual-lock/durability；
   `S2E.2b-1` 已落地 S2.4 recovery core。這五包只有 source effect=`NONE`。
2. **`S2E.2b-2`（唯一 ACTIVE）**：關閉 `ImportFrom` 私有穿透；
   `runpy`／`imp`／`code`／`pdb`／`timeit`／`concurrent.futures` 除名穿透；
   阻止 nonce/self-claimed verifier 取得 `COMPLETED_EXACT`；完成
   `aiml_gate_receipt_validator.py` 2004-line 正式裁決；新增 S2.5 state-root
   directory anchor/manifest 使 journal 刪除可偵測；建立合法、具授權、可重放的
   startup recovery/repair（禁止手工刪檔）；交付真 S2.5 host runner、五維獨立
   observer、雙 lock、封閉 kernel session 與 CLI。
3. **`S2E.2b-3`**：交付 S2.4 五支 row drivers、逐項 kernel hard-boundary
   amendments 與 T2 tier；不可用 raw command 或 source-simulation 冒充 host
   execution。
4. **`S2E.4`**：完成 approved remote-readonly observer、authenticated runtime
   `command_capture_v2`、signed-bundle execution kind、`scope=runtime` typed
   closure schema、exact bytes/digest + signature coverage、apply actor↔independent
   verifier↔receipt/postcheck identity cross-binding，以及 trusted-attestor SSHSIG
   producer/verifier 的 identity/namespace/key/freshness/trusted-clock 驗證與
   CLI/route/closure；對 2231-line
   `tests/structure/test_agent_governance_s2_effect_binding.py` 作明確
   keep/split/exception size adjudication。
5. **`S2E.5`**：在 non-production disposable target 完成六段 DAG 的 positive
   與 forgery-negative rehearsal，證明 distinct applier/verifier，拒絕
   caller/self-claimed capture、nonce、attestor、schema substitution；從 live ABI
   枚舉 28-row ledger 並逐列 CLOSED 或 PM reasoned adjudication。
6. **Terminal packet gate**：GitHub CodeQL alert #95 必須先真實修復或有證據裁決；
   `S2E.4` 的 capture/schema/identity/attestor 條件任一未關閉時不得重發 packet。
   上方 S2.0 EFFECT operator 前置必須原樣進入 fresh packet。

## S2_CLOSED 判準（本 packet 全部執行完的驗收）

Linux `trade-core` 上 learning service 真實 installed/enabled/active、具
platform-attested running evidence（trusted-host attestor 簽章鏈）、
`ingestion_compatibility_receipt_v1` 有效（V151-V160 全 MATCH＋production
`FINAL_ATTESTED` 錨）、全部 postcheck/rollback 證據落 repo。缺任一項即非
`S2_CLOSED`。

## 誠實邊界

source seams 與後續 S2E packages 的全部綠色測試證據只證 source 結構；
runtime/effect 事實需 `PLATFORM_OR_EXTERNAL_ATTESTED` 證據。最近一次已記錄的
runtime 現況＝2026-07-28T15:55:23+02:00 Linux 唯讀觀察：兩個候選 learning
units 均 `not-found/inactive/dead`，兩個 canonical AIML roots 均不存在。W0
只校正文檔並做 source sync，不 deploy、restart 或改變此 runtime 邊界。
