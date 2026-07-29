---
name: project_2026_07_21_aiml_s0_adoption_gate
description: AIML roadmap through V2 Sprint 0; forge-resistant source landed 2026-07-21 and trusted-host PROGRAM_ADOPTED issued 2026-07-22 with source-only, zero-authority boundaries.
metadata:
  node_type: memory
  type: project
  originSessionId: 07e83463-9c2c-4475-8221-65951702b432
  modified: 2026-07-22T09:33:14Z
---

> 這是 2026-07-21 source landing 的時點紀錄；當時尚待執行的 trusted-host
> finalization 已於 2026-07-22 完成，當前狀態見文末「演變軌跡」。本弧承接
> [[project_2026_07_07_ai_ml_maturity_roadmap]]，舊 topic 保留原始 WP1-WP7 歷史。

**AIML-LONG-LIVED-LANDING-V2 Sprint 0 landed (2026-07-21).** Continued the prior
session's stalled `agent/aiml-s0-3-adoption-v1` worktree and closed the S0
program-adoption gate as **source**, three-end synced at `0034a406089`.

- **S0.1** DONE (V2 planning, PR #100). **S0.2** DONE — advisory-serving authority:
  `docs/adr/0051-registry-authorized-advisory-model-serving.md` + `AMD-2026-07-21-01`
  + ADR-0049 addendum + `serving_authority_receipt_v1`. ADR-0051 A3 makes model
  output monotone (`NO_OP|VETO|SIZE_DOWN`, `final_notional<=baseline`); A9 permanently
  denies direct model→broker/order; Guardian/Decision-Lease/Cost-Gate stay superior.
- **S0.3** = `SOURCE_READY` (NOT `PROGRAM_ADOPTED`). Landed the 7 `aiml_gate_receipts`
  JSON schemas, fail-closed `program_code/ml_training/aiml_gate_receipt_validator.py`,
  Registry/router/closure integration, `terminal_receipt_sink_v1` contract-only
  (owner S1.2), and a strict GitHub repo-policy attestation contract. Merged PR #104
  (`b945fe0f8`); ledger projection PR #105 (`0034a406089`).
- **Review**: 7-role adversarial (E2 P1 = bind changed `agent_governance_execution.py`
  into the manifest; E4 P1×3 = negative tests locking authority_limits/7-reviewer/
  dep-graph invariants — both fixed + re-verified). Then the **Codex PR bot** (8th
  reviewer) found **3 real P1 forge-resistance gaps**; per PA min-coherent design all
  fixed + CC/E3/E2 re-review PASS: (1) route the 7 mandatory reviewers into the
  finalization DAG bound to authenticated PASS fragments (reuse `validate_closure`
  recomputed-generation + `validate_execution_attestations`); (2) `SourceManifestVerifier`
  contract must prove `git merge-base --is-ancestor reviewed_head merge_head`;
  (3) `session_attempt_v1` phase-conditional lease (read-only `POST_MERGE_FINALIZATION`
  uses `read_only_admission`, forbids writer lease).

**KEY: `PROGRAM_ADOPTED` emission is a trusted-host (Linux) step, not offline-mintable.**
The hardened gate requires the enforced closure path — 7 governed reviews authenticated
by an out-of-band `execution_attestation_verifier` + `source_manifest_verifier` ancestry
+ live GitHub ruleset. Per the Typed Authority Matrix the offline Mac CLI cannot
authenticate a closure PASS (ORCHESTRATOR_BOUND insufficient; needs PLATFORM_ATTESTED).
The exact follow-up recipe + accepted P2 coverage-debt are in
`docs/execution_plan/ai_ml_landing/PROGRESS.md` "Trusted-Host Follow-Ups". Next real
work = that Linux emission → then S1. See [[project_ssh_bridge_workflow]] for the
Codex-reviewer merge-gate. Boundary held throughout: authority_limits all-const-false,
`source_adoption_only`, four-zero-effects; no ML5/ML6/live/broker/order/Decision-Lease.

## 演變軌跡

- **2026-07-22 — `SOURCE_READY` → `PROGRAM_ADOPTED`:** Linux `trade-core` 已對
  reviewed head `1a933fcc28e9f7341e023b5d401c479957c14c5f` 與 merge head
  `fed223bebd278c50b0ab3330980e66441a30c9ed` 完成 trusted-host finalization；
  governed E4 `275/275`，finalizer closure
  `sha256:27f7b0041a418298ef49943f6f37283b603fce38f48f67f9a825f249f2615c63`，
  receipt `sha256:1a124bcaebb741a69c97e37a828e5b85c9b6499cdf053e8ef62451448878f93b`。
  原文「Next real work = that Linux emission」只描述 07-21 時點，現已被此事件推進；
  receipt 仍為 `source_adoption_only=true`、九項 authority grants 全 false，不代表
  runtime readiness、model promotion、broker/order 或任何 trading authority。權威證據見
  `docs/execution_plan/ai_ml_landing/PROGRESS.md` 的 2026-07-22 ledger 與
  「S0.3 Trusted-Host Finalization (completed)」。
- **索引合併:** 為守住 `memory/MEMORY.md` Project context ≤40 條，本 topic 吸收
  07-05~07 WP1-WP7 roadmap 的索引弧；原始內容仍完整保存在
  [[project_2026_07_07_ai_ml_maturity_roadmap]]，沒有刪除歷史。

## 2026-07-28：S2.4@SOURCE_READY 宣告＋WP5（S2.5 seam）開建

- W5 round-6（operator PM 工單 PR#145 comments 5091757764/5091776706）收口：TODO/PROGRESS 投影校正至 round-5 世代、discriminator regression `tests/structure/test_aiml_w5_receipt_binding_projection.py`（artifact 實值↔兩檔 W5-RECEIPT-BINDING marker↔活 ABI PM-owned 集合三方機械等值）、PM-owned 六 obligations 裁決（0 source-closure blocker；S2.4-AMEND-1=refresh ingress+終端 receipt §3 refresh-digest 欄位+§9.1 profile 穿線、S2.4-AMEND-2=plan-derived expected_topology，兩修正案 gate `S2.4@EFFECT_DONE` 入 operator packet 前置）。五路 exact-generation 複驗（E2/E4/CC/OPS/QA）全 PASS 後 PR#145 exact-head merge `e1b14b7d5`；**PM post-merge 宣告 `S2.4@SOURCE_READY`（PR#146 merge `3dd27b5e2`，TODO v854/PROGRESS ledger v13）**；三端 ff-only 同步。
- 機械事實：W5 receipts 驗證必須在 **bound head** 重放（W2 exported-ABI 重導出 tree-dependent——carrier commit 把 receipts 寫進樹即改變量測面）；`three_head_projection_digest` 只 hash「哪些檔含 effect-DAG 字串」非全文，TODO/PROGRESS 可安全編輯。
- WP5 tranche 1（branch `agent/aiml-s2-wp5-s25-seam`）：PA 設計正本 `design/S2.5-running-attestation-source-seam.md`＋PM 六裁決（O-1 帳本納入 owned scope+接受 re-emission 連鎖；O-2 watchdog=restart-機制謂詞 sd_notify 留 S3.4；O-3 core+authorization_set 分離；O-4 additive v3 classifier；O-5 單一 WATCHDOG_ROLLBACK_TEST lineage 兩 phase step；O-6 WantedBy+manager 語義為足）；E1 建成五 schema+三模組+CLI+三態 fixtures+雙向 latch，關閉 `S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST`（typed_status→CLOSED_BY_S2_5_SOURCE）；PM 於 `0faa6499d` 再發射 W5 receipts（round-6 世代，carrier `0b06982e0`）。
- **對抗審查退回（教訓）**：E2 FAIL（F1=production S2.5B 可錨 simulated-lane pre-drill 直達 FINAL_ATTESTED）＋E3 FAIL（effect 後例外裸逸無 rollback／上游 receipt 綁定只信自報 self_digest 字串不重算／replay ledger 尾截斷不可測且零持久化）——**「digest 綁定」若不重算 `artifact_self_digest` 就只是名字**；tranche 1b remediation 進行中。E4 head 實測 6248/46/0。
- 既有 flaky：`test_e18_a_dropped_lock_token_cannot_be_satisfied_by_address_reuse`（id() 位址重用類，全 suite 壓力下偶發；已 spawn 修復 task）。

## 2026-07-28 終態：S2 全 source predicates SOURCE_READY → 單一 operator packet

- 續前節：WP5 tranche 1b（E2/E3 四 P1 全修）→ E2 delta PASS → PR#148 merge `dab875882`；tranche 2（攜帶 P2×3+notes 收口＋`S2.2B` `ingestion_compatibility_receipt_v1` seam）→ E2 delta PASS → PR#150 merge `6be29043c`；final projection PR#151 merge **`a7c36775d`**（三端同一 head）。
- **PM 宣告 `S2.5@SOURCE_READY`＋`S2.2B@SOURCE_READY`**：S2 七個 source predicates（S2.0/S2.1/S2.2A/S2.3/S2.4/S2.5/S2.2B）全 landed，**無可執行 source 工作剩餘**；終態＝`BLOCKED_OPERATOR_ACTION_PACKET_READY`，packet＝`docs/execution_plan/ai_ml_landing/S2-operator-action-packet-v1.md`（串行 DAG S2.0→S2.4→S2.5A→S2.1→S2.5B→S2.2B＋逐步授權/rollback/postcheck＋前置 S2.4-AMEND-1/2＋S2_CLOSED 判準）。TODO v855／PROGRESS ledger v14。
- **W5 receipt 世代鏈**（每次觸 W5-owned path 即須 re-emit＋三腿投影同 commit 更新）：`fcc44eca7`→`c2a7263ce`→`aaee7f1a2`→`0faa6499d`（round6）→**`5be472193`（round7，carrier `0eb90e40c`）**；ledger digest 現值 `sha256:57696d69…`。中央註冊（SCHEMA_FILES／facade dispatch／closure allowlist／count pin）全在 W5-owned path 內＝任何新 schema 必觸發 re-emission，此為結構性而非疏失。
- **反覆抓到的同一家族缺陷（教訓）**：①「digest 綁定」若不重算 `artifact_self_digest` 就只是名字（stub 自報即通過）；②effect 之後的例外裸逸＝unit 留在 active 而無 rollback；③hash-chain ledger 不持久化/無 head anchor ⇒ 尾截斷不可測；④probe-only 鎖 ≠ 交易互斥（需 hold 到 persist 完成）；⑤lane 混用（simulated 錨解鎖 production attested）。⑥文檔「現行/in this tree」現在式殘留會逃過只認 `source_head=` 格式的 discriminator。
- runtime 未變：Linux `openclaw-learning.service` = inactive／not-found，`/var/lib/arcane-equilibrium/aiml` 不存在（2026-07-28 唯讀複核）。九項 authority 全 false。
