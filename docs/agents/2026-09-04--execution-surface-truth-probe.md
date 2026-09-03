# W1｜execution-surface truth probe

日期：2026-09-04  
狀態：W1 DONE（source-only closure）  
正典介面：`agent_governance.py execution-surface-probe`、`execution_surface_truth_probe_v1`、`development_agent_execution_policy_v1.surface_profiles`

## 結論

W1 新增的是可重播的來源設定報告，不是宿主實際選取的證明。公開 CLI 只安全讀取 repo-local
`@request` file；它必須是小於等於 64 KiB 的嚴格 UTF-8／JSON、repo-relative regular file。request
內的 allowlisted declaration envelope 仍是 caller-provided replay snapshot：雜湊可綁完整性，卻不
證明 provenance/authenticity、actual file state 或 selection。它拒絕 absolute/traversal/symlink/
nonregular/oversize/duplicate key/non-finite/過深或畸形輸入，且拒絕訊息不回顯輸入值。

SHA-256 只保護來源與報告完整性。沒有公開 verifier 時，合法的 caller-filled host config、
prompt selection、cwd 與 surface-profile 都是 `CALLER_CLAIMED`；實際選取為 `UNVERIFIED`，報告
為 `COMPLETE_WITH_UNVERIFIED`。只有 embedding host 注入、且精確涵蓋 profile ID、profile digest
與 whole source envelope 的 verifier，才可產生 `HOST_VERIFIED`／`HOST_OBSERVED`／`COMPLETE`。
目前沒有此 production host verifier。

## 宣告、診斷與不可推導事項

- repo `.codex/config.toml` 宣告：`agents.enabled=true`、最大 threads=`3`、default model=`gpt-5.6-terra`、effort=`medium`、`interrupt_message=false`。Registry 只提供 surface profile，不提供這五個 agents 值。
- 本機 global user config 的 diagnostic 未見 `[agents]`；它不能證明實際選取，selected config 仍是 `UNVERIFIED`。
- 未認證的 `codex-cli 0.149.0-alpha.4.1 debug prompt-input` 診斷：workspace root 觀察到 outer workspace shim；canonical repo 與 linked worktree 觀察到 canonical repo `AGENTS`；KnowledgePilot rule 三處皆出現。分類為 `PM_REPORTED_UNATTESTED_DIAGNOSTIC`，不是 causal 或 selected truth；app-server config/read 不可用。

## 關閉證據

- checkpoints：initial probe `9c34aa4b28e30e495146cdb880ae889d3ea59b4f`；authenticity/path repair `86ae98c5bcbb50f5d897811327c8c118b0ff166f`。
- admission `51e52ad9c349f21aa81a4d37e79dbfa0`；writer lease `f6ca2f0a6230701e7d3aa44ba1e8e725`（owner `PM-codex-root`）；Context `sha256:1de49888093ee1808669cf363d8f01840a13319994b6eca45bc5106cbaa63698`；task `sha256:ec618559cfd5f84ffe7c763257a78f68c8146280799b9cf57025e77f5f990760`。
- initial E2 FAIL：兩個 P1；final E2 PASS：P0/P1/P2=`0`、`24 passed`，capture `sha256:d6108aae9973524b35a4aac984f50a9a400a1e96d9366007b7b3dcaa2aed5be0`。
- final E4 PASS：combined `84 passed`，capture `sha256:4ed4015154a4408f5018bf026cab6089aab46519a04d53f0ef4499e244975e7e`；probe `24 passed`，capture `sha256:71c9c8b074d56b33109f4aa1fa2f0c52b1a9deb0eebebef18440aa0fa91f24e8`。registry validate、renderer 與 diff captures 已綁 Context。
- E4 standalone `py_compile` 為 `SKIPPED/DENIED`；syntax/import 僅依已執行 pytest 重用，E1 的獨立 `py_compile` 已 PASS。
- source-verifiable selected signal 不可得，故依 stop rule 以 `UNVERIFIED`／`COMPLETE_WITH_UNVERIFIED` 關閉；不是取得實際 selected config。

## 範圍外與後續

未執行 full suite、Rust、Linux、remote、runtime 或 broker 驗證；沒有任何實際效率、節省、採用、runtime、trading 或 profit 結論。

另有已確認、獨立於 W1 的 source-generation drift：current Registry 為
`sha256:0ab769848bb7490b9be067ae601b76b8e557d068bf0c481aca00b835e8ca8b23`，三份 saved workflow
仍嵌入 `sha256:9ce2dbd2bca32268cac32b6941537c9e305458f97ea5fe6590cada78dad300ff`；focused codegen 結果為
`1 failed, 6 passed`，capture `sha256:1537dd292937ba41eb2beaca68978ca4a22bf73a65c65362b5b78d07bb679b7b`。
它不是 W1 config mismatch 或因果結論，且未於此處修復；W7 直接承接其 source-projection 修復，無 runtime effect。
