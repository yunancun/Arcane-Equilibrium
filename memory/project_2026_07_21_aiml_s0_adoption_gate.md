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

## 2026-08-03：S2E-LW1 Tier 1 durability anchor 三路複核 FAIL

- 承 2026-08-02 operator 裁 Tier 1（S2E-LW1 receipt chain 去掉三個付費 distinct-custody
  外部服務，改 host 側 `TRUSTED_HOST_SSHSIG_APPEND_ONLY_V1`）。分支
  `agent/aiml-s2e-tier1-durability-anchor-20260802`，未 push、無 PR。
- **PM 進場先驗真實情況，抓到一個 CI 抓不到的真缺陷**：committed 的 operator action
  packet 還是 Tier 0 舊件，用本分支自己的 validator 跑就 FAIL（3 errors）——**沒有任何
  測試把 artifact 綁到 generator**。放著不管，operator 會照 packet 去買 S3 Object Lock。
  已用 fresh 唯讀 Linux 觀測重建（`c13142b4…`→`d4ad8ede…`），TODO/PROGRESS 過期 pin 一併校正。
- **E2/E3/E4 三路獨立派工全 FAIL，收斂到同一組缺陷，PM 逐條複驗成立**。決定性一條：
  實作**違反它引用來授權自己的那句 spec**——§LW1 全文要求 monotonic counter/head 必須
  **外部**、明寫**單一簽章不能防 rollback**、**同一 writer 可 coherent rewrite 時只能得
  `UNVERIFIED`**，實作是 host-local + 單簽 + 同 writer，三條逐字違反（誤讀源=TODO 摘要
  投影漏抄「外部」，見 [[feedback_evidence_discipline_under_degraded_tools]]）。
- 四條 P1：①連續性只檢查 null/non-null 形狀、零持久化 head ⇒ 可無限重放創世／掛空前手
  （慣犯缺陷③原封重現）②readback 三旗標 schema `const:true` 由 anchor key 自簽自證，
  Tier 0 與 `.codex/agent_registry_v1.json` 明文的 distinct-actor 要求**無替代物**
  ③「off-host」零強制純命名，`replica:offhost-append-only:localhost` 通過
  ④新寫的 carrier/review anchor 綁定執法可整段刪除而 72 測試全綠（E2/E4 各自獨立抓到）。
- **不可被 FAIL 抹掉的 PASS**：trust-root TOCTOU 防護（品質很高）、SSHSIG domain
  separation 真隔離、digest 逐項真重算（本次「digest 綁定只是名字」不適用）、零注入面、
  三件套移除無覆蓋淨損失、交付報告**所有可驗證數字皆誠實**（含 headroom 紅燈 baseline
  位元組中性，E4 以 detached worktree 獨立復現）。工藝紮實，錯在信任模型。
- 放行條件（三路收斂）：跨 receipt 單調性 gate（**git 本身就是 spec 要的那個外部持久層**
  ——receipt 已把 anchor_generation/head 釘進 git，只差 transition gate 沒比對）／replica
  必須有自己的 key identity+trust root+簽章（同時解掉單簽違規與 TTL 回歸）／locator 排除
  loopback／補 P1-4 regression（禁 `assert errors` 弱斷言）。全文＝
  `docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-03--s2e_tier1_adversarial_review_fail.md`。
- 真瓶頸未變：`attest-v2`／durability anchor／predecessor registry 三支 root-owned
  producer 能力**都還沒寫**，repo 內只有驗證端契約，故 W0/LW1 receipt 發不出、LW2 永遠
  locked。runtime 仍 dormant（2026-08-02T22:13:32Z 唯讀複查：11 fixed path 全 ABSENT、
  兩 unit not-found/inactive、兩 canonical root 全 ABSENT），authority 0/9、effect 0/6。

### 2026-08-03 續：remediation source landed（branch-local，18 commits，未 push）

- operator 裁：修成真的合 spec（非退回 Tier 0）＋replica 私鑰真的放 `ncyu-nas`＋600s 本輪一併修。
  已落地：committed anchor floor（`GENESIS_ARMED` gen=0；驗證器以 `git show <commit>:<path>`
  讀 **commit 位元組**——關鍵論證是「資料在 git ≠ 驗證器讀得到」，transition gate 三個輸入
  原本全是 caller 給的檔案路徑，必須有 code-owned pin 才算 gate）、replica 2-of-2 第二簽章、
  三個 `const:true` 刪除、host fingerprint 綁定、`require_current_freshness`。
  前置 14→16；五個 S2E 檔 **100 passed**。
- **可省未來 session 大量時間的順序事實**：`w5-emit` 需 `--test-evidence` 與
  `--review-provenance`，所以 **W5 發射必然在對抗複核之後**，不可能先發。任何「先把 W5 債
  清掉再審」的計畫都是錯的。
- **反模式（新）**：只存在於測試、source 無強制、且**正好卡滿**的數值上界（此處 LW1 review
  manifest `<= 256`）＝latent trap，任何人新增一個受治理檔案都會踩到並被迫「為了讓自己的改動
  過而放寬測試」。遇到時要查它是否有 source 端推導，沒有就是成本護欄而非不變式，調整要具名
  留給下一輪 reviewer 複核。
- 仍未做：remediation 的 E2/E3/E4 複核、W5 re-emission（須併還 `209793b70` 漏發射）、
  provisioning prompt（仍寫 10 把應為 11）。真瓶頸未變：三支 root-owned producer 未實作，
  且 `ncyu-nas` 無 SSH listener ⇒ receipt 仍發不出。
