# G0 / S2E-LW1 工程 checkpoint 與外部前置阻塞報告

日期：2026-08-02
任務：`AIML-S2E-LW1-20260802`
終態：`BLOCKED_EXTERNAL_PREREQUISITES_ACTION_PACKET_READY`

## PM 結論

| 範圍 | 真實狀態 | 不成立的宣稱 |
|---|---|---|
| G0 | `SOURCE_COMPLETE_RUNTIME_INDETERMINATE` | 不等於 runtime/process/build PASS |
| S2E-LW1 source | implementation checkpoint 已完成 | 不等於 wave exit 或 package closure |
| W0 genesis receipt | 未發行 | 不得由 source/tests 代替 |
| LW1 wave receipt / transition | 未發行；未 `ADVANCE` | `S2E_2B_2A_SECURITY_RECOVERY_READY` 尚未成立 |
| LW2 | locked | 不得開始 LW2 |
| S2 / production | open；authority 0/9，effect 0/6 | 無 deploy/restart/PG/broker/order/runtime effect |

本輪不能誠實宣告「完成 LW1 exit」。可自行完成的 source/security 工作已形成 clean
checkpoint；剩餘阻塞是 Linux 固定 trust/signer roots 與獨立 external WORM/provider/
predecessor-registry 的真實配置及證據。缺少這些前置時，繼續修改 receipt 或重跑 source
loop 都不會產生合法 W0/LW1 receipt。

## G0 核實

- intake source generation 為 PR #175 merge `8656dd80df3c332ecb84ac57d8bf09aca9f72e37`；
  當時 Mac/GitHub/Linux source 已對齊。
- G0 所需 governance/source ratification 已 landed；但 Linux learning units、install root、
  state root 均不存在，且沒有 current runtime process/build attestation。
- 因此 G0 僅能投影 `SOURCE_COMPLETE_RUNTIME_INDETERMINATE`，不能升格成 runtime PASS。

## S2E-LW1 source 交付

1. `afcbf6a32`：封閉 dispatch 與 host-clock gaps，將中央 validator 拆至行數政策內。
2. `1df28dd4c`：新增零 caller-selected 參數的 fixed-profile host-capture producer，綁 signed
   admission provenance。
3. `5242b60a1`：receipt issuance 強制獨立 external WORM provider attestation 與 append-only
   single-use predecessor registry；caller-shaped S3/self-signing 不能解鎖。
4. `913b1c898`：把 external-evidence adversarial test 納入 genesis governed review argv。
5. `488077156` / `cbaacecc3`：新增 closed action-packet schema、builder/validator 與 13 個
   focused tests；blocker helper 刻意不擴張 256-item launch acceptance manifest。
6. `1716307d8`：對抗回歸發現 producer 直接持有 `subprocess` 後，改由唯一
   `HostExecutionKernel` 固定 Git argv 與 signer path/protocol；generic `run()` 不能呼叫
   signer，只有 bounded stdin 專用方法可進入。
7. current-head 對抗複核補上固定 porcelain status；host capture 現在會拒絕 tracked、staged、
   untracked 或 ignored 任一污染，包含 `__pycache__`／`*.pyc`。
8. `13c813968`：GitHub Codex review 的 2 P1＋2 P2 全部修復：ignored executable artifacts、
   Ubuntu canonical `/usr/lib/os-release`、provider locator canonicalization，以及只允許
   `registry:external-append-only:*` predecessor registry locator。
9. `d3a21f4e4`：final Codex delta review 發現 generic provider locator 仍容許 `file:`／
   `unix:` 本地 backend；schema exact pattern 與 validator semantic allowlist 現只接納
   `aws:s3-object-lock-attestor:<external-id>`，本地／任意 URI 均 fail closed。

## Current machine observation

唯讀 inventory：
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-02--s2e_lw1_readonly_inventory.json`

- observation：`2026-08-02T04:06:52Z`，evidence class 固定為
  `UNAUTHENTICATED_READ_ONLY_OBSERVATION`。
- Linux source：`8656dd80df3c332ecb84ac57d8bf09aca9f72e37`，worktree clean。
- `openclaw-learning.service`、`arcane-equilibrium-aiml-engine-scanner.service`：
  `not-found/inactive/dead`。
- `/opt/arcane-equilibrium/aiml`、`/var/lib/arcane-equilibrium/aiml`：absent。
- 10 個固定 public trust roots 加一個 fixed signer capability：全部 absent。
- external WORM destination、distinct provider attestor、append-only predecessor registry：
  沒有可驗證配置證據，記 `NOT_OBSERVED`，不自稱 `READY`。
- 追加唯讀 host check 確認 `/etc/os-release → /usr/lib/os-release`；canonical target 為
  root-owned `0644` regular file，`ID=ubuntu`。

Machine action packet：
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-08-02--s2e_lw1_external_prerequisite_action_packet.json`

- schema：`s2e_lw1_operator_action_packet_v1`
- source checkpoint：`d3a21f4e4be4206c34254967459406c558581ca8`
- blocked prerequisites：14/14
- packet digest：`sha256:453733c8b4d9e05713553f416abffe4fed9cd564a3f0bcd6b75b86bab65524ee`
- packet 只排序下一步，不帶 secret、不執行 action、不授權 production effect。

## 驗證與對抗複驗

- launch receipts / external evidence / action packet / central validator / launch hardening：
  `180 passed, 3 skipped`。
- recovery / host capture / host kernel 全集合第一輪：`759 passed, 9 skipped, 9 failed`；
  9 個 failure 全部指向 host-capture producer 的 raw `subprocess` 與缺失 scanner policy。
- 修復後同一 recovery/kernel 全集合：`773 passed, 9 skipped`。
- 修復 focused set：`144 passed`。
- `13c813968` reviewed-head launch/receipt set：`200 passed, 3 skipped`。
- `13c813968` recovery/kernel adjacent set：`904 passed, 9 skipped`。
- `d3a21f4e4` final provider-class delta 的 S2E 關聯集合：`90 passed`；另有
  `file:`／`unix:`／`https:` 負向 mutation 覆蓋。
- action packet CLI validation：PASS；JSON parse、`py_compile`、`git diff --check`：PASS。

本 session 沒有可用的獨立 subagent execution tool，故未虛構 E2/E4 身分；PM 直接執行
fail-first 回歸、負向 mutation 與 source/runtime boundary review。GitHub Codex 在 `d3bc5c011`
提出四項 finding，並於 final delta review 再提出一項 provider-class P2；五項均已於
source checkpoint `d3a21f4e4` 閉合。publication 仍要求 current-head classified checks。

## 唯一後續序列

1. Operator 在帶外安全通道 provision fixed trust roots；不得把 private key/credential 寫入 packet。
2. provision root-owned fixed host-capture signer capability。
3. 配置 Object-Lock `COMPLIANCE` external WORM destination，只記 named credential channel。
4. 配置與 receipt signer 不同 custody 的 provider attestor。
5. 配置與 receipt/provider signer 均不同 custody 的 append-only single-use predecessor registry。
6. 取得 fresh machine evidence 後重新跑 W0 genesis -> LW1 receipt/transition chain。

只有第 6 步的 current-head receipts 與 transition gate 真正 `ADVANCE`，才可投影
`S2E_2B_2A_SECURITY_RECOVERY_READY` 並解鎖 LW2。
