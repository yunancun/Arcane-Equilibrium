# S2E Tier 1 durability anchor — 實作交付報告

日期：2026-08-02
分支：`agent/aiml-s2e-tier1-durability-anchor-20260802`（`209793b70`、`74ee80be6`）
基準：`097c879b9`（PR #176 merge）
裁決依據：operator 2026-08-02 採納 Tier 1（提案見
`2026-08-02--s2e_external_evidence_downgrade_proposal.md`）
狀態：**source landed on branch，未開 PR，未 merge**

## 一、實作要點

實作的是 **carrier schema 早已宣告但從未實作的 adapter**：
`receipt_carrier_attestation_v1` 的 `immutable_readback.adapter` enum 本來就有
`TRUSTED_HOST_SSHSIG_APPEND_ONLY_V1`（與 `EXTERNAL_WORM_V1` 並列），這正是 §LW1 spec
anchor 選言的第二支。舊實作把選言收斂成第一支，再收窄成 AWS 專屬。

保留的五項語義完全未動：獨立 key custody、monotonic generation/previous-head 連續性、
entry/head digest 重算、≤10 分鐘 freshness window、immutable readback 已證。
換掉的是：付費外部 custody、不可逆 COMPLIANCE 保留期。durability 改由 off-host 副本承擔，
且副本必須回讀到與本機 anchor **完全相同的 head**（`replica_head_digest == anchor_head_digest`），
副本落後即 fail closed。

改動面：新 schema `s2e_durability_anchor_attestation_v1`（取代 S3 provider schema）、
registry locator class `registry:external-append-only:` → `registry:host-append-only:`、
launch carrier/review/issue 三條路徑移除 `external_sink` 的 intent/result/ack 三件套、
LW1 action packet 前置改為 host 側、`aiml_gate_receipt_s2e_launch.py` 2000 → 1849 行。

`agent_governance_terminal_receipt_external_sink.py` **未動**：它仍是 S8.6 terminal WORM
receipt 的載體，只是 S2E 不再依賴它。

## 二、測試證據

| 範圍 | 結果 |
|---|---|
| `test_agent_governance_s2e_external_evidence.py` | **26 passed**（改前 9 個案例） |
| `test_agent_governance_s2e_launch_receipts.py` | 23 passed |
| `test_agent_governance_s2e_launch_hardening.py` | 10 passed |
| `test_agent_governance_s2e_lw1_action_packet.py` | 13 passed |
| `test_agent_governance_s2_4_install_render.py` 等 blob-bound | 75 passed（commit 後才綠，屬設計） |
| 全量 `tests/structure/`（排除需 PG 的檔） | **5339 passed, 16 skipped, 1 failed, 62 errors** |

負向覆蓋是**增加**而非等量：新增 replica locator class、replica 落後 head（rollback）、
readback 三個旗標各自為 false、generation/head 不連續兩式、TTL 超 10 分鐘、
attestation 早於 readback 的時序倒置。

**兩類非本次造成的紅燈，據實列出**：
- 62 errors：`test_agent_governance_s2_4_install_engine_scanner_disposable.py` 全檔，
  根因是 Mac 本機 `/opt/homebrew/bin/initdb` 起不了 PG 叢集，屬環境限制（該類須 Linux 跑）。
- 1 failed：`test_aiml_s2_effect_host_run.py::test_registry_tracked_bytes_leave_headroom…`。
  **已在基準 `097c879b9` 以 detached worktree 復現，數值同為 `107089`（headroom 23983 < 24576）**，
  本次改動對該計數位元組中性。已另立 follow-up，不在本次範圍內修。

## 三、必須更正的先前說法

降級提案 §五說 Tier 1 會讓 blocker「14 → 11」。**這個數字是錯的**，更正如下：

blocker 總數維持 14。真正改變的是組成：

| | Tier 0 | Tier 1 |
|---|---|---|
| 付費外部 custody 服務 | 3 | **0** |
| 不可逆承諾（COMPLIANCE 保留期） | 有 | **無** |
| 免費 keypair／路徑安裝 | 9 | **10** |
| 待實作的 root-owned 能力 | 1（`attest-v2`） | **3**（＋durability anchor、predecessor registry） |

原估漏算了「取代外部服務的 host 側能力本身也要寫」。誠實地說：Tier 1 的**開發量比 Tier 0 大**，
換來的是零帳單、零不可逆、以及不依賴任何外部供應商。Tier 0 那三個服務也不是白得的
（要找到並持續付費一個 distinct-custody append-only registry 服務），但那是採購不是開發。

## 四、未完成與已知殘留

1. **durability anchor 與 predecessor registry 兩支 root-owned 產生器未實作**，與 `attest-v2`
   同級。本次只做驗證端契約。沒有這三支能力，W0/LW1 receipt 仍發不出來。
2. **`BLOCKED_EXTERNAL_PREREQUISITES_ACTION_PACKET_READY` 這個 state token 保留未改名**。
   Tier 1 之後已無外部前置，token 語義漂移；改名會動到 TODO/PROGRESS/測試的治理投影，
   屬另一次 projection 變更。**此處具名記錄為 drift，待 operator 裁。**
3. Operator provisioning prompt 已同步更新（9 → 10 把、三個 `attestor_class` 新值、
   Phase B 改為「契約已落地但能力未實作」）。

## 五、誠實邊界

- **本 session 未執行 E2／E4 對抗複核**：本次會話沒有可用的獨立 subagent 執行工具，
  依「不虛構角色」原則不偽造 E2/E4 身分。上述測試由 PM 直接執行，數字可自行復算。
  **這是一次安全路徑改動，PR 前應補獨立對抗複核。**
- 未執行任何 runtime／PG／broker／order effect；`task_issued_authority_count` 0/9、
  production effect 0/6 未變；未 provision 任何 host 物件。
- 未開 PR、未 merge、未推遠端。
- Tier 1 反轉了 `d3a21f4e4` 的 Codex P2 修法（該修法在「provider 必須外部」前提下正確）。
  這是 operator 裁決改前提，不是繞過修法；PR 說明必須明載此點。
