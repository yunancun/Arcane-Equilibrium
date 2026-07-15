# W2 — P2 production seal/supersession caller authority 設計(追認式收口)

**日期** 2026-07-15 | **性質**:**retroactive design sign-off** — 實作已先行落地於 main(W1/W2 commit 鏈 `0c90de9c2`→`324fb87a8`→`7902efe71`),本文檔是 PA 追認式設計收口,不是先行設計。凡本文與 as-built 不一致處,均在 §9 明標「as-built 偏差+處置建議」。
**權威出典**:AMD-2026-07-11-01(W2 controlled seal 授權)> AMD-2026-07-08-01 Post-Acceptance Clarification #2(option A 6-binding + HMAC 升級觸發器)> ADR-0048 §Mandatory Phase Gates(seal 生命週期段)> `IBKR_TODO.md` §2/§3/§5-W2。
**申報梯度**(IBKR_TODO §3):本包封頂 `source-ready` + `external-gate-ready`(capability)。**本文檔任何一句都不是 broker 授權**;production 從未 seal(trade-core `<DATA_DIR>/governance/ibkr_phase2/` 不存在,2026-07-15 實測),真實接觸仍由 EA 跑道 + `ibkr_activation_envelope_v1` 單獨把關。
**as-built 正本**:`rust/openclaw_engine/src/ibkr_phase2_gate_producer.rs`(module note L39-43、W2 常量 L75-81、`Phase2SealControlApprovalV1` L1116、`Phase2ApplyLock` L1214、replay 驗證 L2004-2058、`phase2_seal_dry_run` L2135、apply 入口 L2906、summary L2985)+ `rust/openclaw_engine/src/bin/ibkr_phase2_seal.rs`(111 行)+ `tests/structure/test_ibkr_phase2_seal_control_static.py`。

---

## 1. Caller 身份與場地:誰可以跑 `ibkr_phase2_seal` CLI

**裁決:唯一合法 caller = Operator,手動、逐次、於 trade-core 本機 shell(含既有 SSH bridge 進入的互動 shell)執行 standalone bin `ibkr_phase2_seal`。** 結構前提:euid 必須是 `<OPENCLAW_DATA_DIR>` owner-only 0700 鏈的擁有者(as-built 全鏈 euid+exact-mode 檢查),且執行的 binary 之 `BUILD_GIT_SHA` 必須等於批准檔 `approved_source_commit`——從過期 build 執行必然被拒(anti-replay)。Mac 開發機無 production data dir,天然無法誤 seal。

被禁面與理由(每面均有 as-built 或治理錨):

| 被禁面 | 為什麼禁 |
|---|---|
| GUI | IBKR_TODO §2 永久 denied:「GUI/client 狀態當授權」。seal 是治理簽核行為,GUI 按鈕會把 client state 變成 authority 輸入;GUI lane 契約為 display-only。 |
| FastAPI/Python | §2 永久 denied:「Python/FastAPI/GUI 成為 order/risk/activation authority」;Rust 是唯一權威。批准材料經 Python 轉手違反 W8 既定分工(Python 只能 request/display,不得創建/轉發授權材料);structure 守衛已 pin 全部 stock-etf route 為 GET-only。 |
| 引擎 runtime 自動觸發 | as-built 明文:「IPC/display surface remains read-only and cannot invoke the apply entry」(summary 只走 dry-run);靜態守衛 pin `phase2_apply_seal_if_explicitly_requested` 的唯一 caller = standalone bin。批准檔「存在」若能自動 seal,即複製 §2 活化鐵律所禁的「憑證/slot 存在=自動活化」反模式到治理層。 |
| cron/排程 | 雙閘設計(§2 本文)是**逐次出席的 operator ceremony**;無人值守重放會把 exit code 3 / `already_applied_no_contact` 變成無人解讀的噪音,且與批准檔 30 天 freshness/expiry 的「有界人工窗」語義矛盾。crash-retry 冪等是為斷電恢復設計,不是排程重跑授權。 |

## 2. 雙閘語義:`--apply` × `OPENCLAW_IBKR_PHASE2_SEAL_APPLY=1` + 6-binding

寫入 ledger 需**三層全過**,缺任一 = fail-closed 拒絕、零寫入:

**閘 1(CLI)**:預設 dry-run;`--apply` 必須顯式、單次、與 `--dry-run` 互斥(未知參數/重複參數 exit 2)。無 `--apply` 時即使 env 已設也只回 `dry_run`+`apply_flag_required`(測試 `w2_apply_requires_explicit_cli_flag_even_when_env_gate_is_set`)。
**閘 2(env)**:literal `OPENCLAW_IBKR_PHASE2_SEAL_APPLY=1`;缺席/非 "1" → `blocked`+`OPENCLAW_IBKR_PHASE2_SEAL_APPLY=1_required`。
**閘 3(approval file 6-binding,W2 production 形態 = `phase2_seal_control_approval.json` 經 `phase2_control_approval_is_valid`)**:

1. **檔案 custody**:owner-only 精確模式檔(as-built **0o400**,見 §9-D1)+ data-root→`governance`→`ibkr_phase2` 全鏈 owner-only 精確 0o700 + symlink-reject(`AT_SYMLINK_NOFOLLOW` lstat → `O_NOFOLLOW|O_NONBLOCK` openat → inode equality,無任何 path-based re-open)。
2. **source_commit 綁定**:`approved_source_commit == BUILD_GIT_SHA` 且必須為 40-hex 真 SHA(`source_commit_is_known`;"unknown" build 直接拒,防 applied-but-unconsumable 假成功)。
3. **治理綁定**:`contract_id == ibkr_phase2_seal_control_v1` ∧ `authorization_amd == AMD-2026-07-11-01`(as-built 對 Clarification #2「adr+amd」綁定的重指向,見 §9-D2);ADR-0048 / shape-AMD `2026-06-29-01` / contact-AMD `2026-07-08-01` 在 artifact 層由 `validate()` + hash 覆蓋強制。
4. **expiry/freshness**:`issued_at_ms>0` ∧ `issued_at≤now<expires_at` ∧ `expires>issued` ∧ 齡 ≤30 天(`MAX_APPROVAL_AGE_MS`,clock-guard fail-closed)。
5. **lineage 入 hash**:`approval_digest`(canonical approval 全欄 sha256,roles 排序後)寫入 generation 與 control record;`approval_lineage_hash` 進 artifact 且被 `raw_artifact_hash` 覆蓋;`approval_id`/digest 全鏈查重,重放 → `controlled phase2 approval replay rejected`。
6. **永不自注入 Operator**:`reviewer_roles` 只能來自批准檔,且必須同時含 `"PM"` 與 `"Operator"`(as-built 比 Clarification #2 更嚴,見 §9-D3);批准檔缺席 → `Ok(None)` → `external_verification_pending:control_approval_missing`,producer 不注入任何角色。

另有 inputs 閘:`phase2_seal_inputs.json`(`Phase2SealProductionInputsV1`)四 leg 必須各自 `validate().accepted` 且 secret-slot 與 topology 的 `account_fingerprint_hash` 相等(T2 triangulation);缺檔 → `external_verification_pending:controlled_inputs_missing`,零寫。production path 從不把 fixture/template 當 seal input(靜態守衛斷言)。

## 3. 生命週期權威:Seal genesis → Supersede → Revoke terminal

as-built replay evaluator(單一 root、單一 leaf、hash 鏈連續、無環、無 fork,否則 `ambiguous immutable control chain`)+ pre-write guard,與 ADR-0048 §Phase 2 段逐字一致:

- **genesis Seal 只准空鏈**:active 存在 → 拒;**鏈非空(含 revoke 後 tail_hash=Some)→ 在任何不可變寫入「前」拒**(`seal rejected: build sha lineage already exists (revoke is terminal)`)。這就是防 brick 的 pre-write guard:若放行,0400 記錄寫下後才被 post-write evaluator 拒,ledger 從此 load 失敗且無法再 apply。genesis 批准不得帶 predecessor 綁定。
- **Supersede 需 active predecessor + hash 相符**:批准檔 `predecessor_artifact_id`/`predecessor_raw_hash` 必須同時等於現行 active generation 的 id 與 `raw_artifact_hash`,否則 `predecessor binding mismatch`。
- **Revoke terminal per build SHA**:target 必須就是 active predecessor(id+hash 雙符);revoke 後同 build SHA **不可 reseal**(上一條 guard 結構性擋死)。Revoke 只寫 control record,不產生 generation。
- **並發/崩潰紀律**:`Phase2ApplyLock` 對 `governance/` 與 `ibkr_phase2/` 雙 dirfd `flock`(crash 自動釋放),critical section 內全部 I/O 綁 inode(拒 whole-directory swap);中斷後 retry 只補寫缺失 sibling(單一 orphan 且與批准/lineage 全符才收養,否則 fail-closed),完成後 post-write 全鏈重驗。

**何時用 Supersede vs 新 build SHA**:同一 build SHA 下要換代 artifact(如批准窗續期、inputs leg 更正、T2 對齊後 re-attest)→ **Supersede**(保留 lineage,predecessor 綁定可審計)。以下情況必須走**新 build SHA**:①該 build 已 Revoke(terminal,無路可走);②源碼已變(`BUILD_GIT_SHA` 變了,批准的 `approved_source_commit` 綁定自動強制換鏈)。「先 Supersede 後 Revoke、或換 build SHA」即 ADR-0048 的 re-attestation 語義。

## 4. 時點約束:合法時機 = EA3 前置;seal ≠ 活化

- **合法時機**:IBKR_TODO §6 EA3 行明文——production seal(W2 路徑,option A 批准檔)是 EA3「G4 首次接觸(readonly)」的第一步,序在 readonly envelope + 活化紀錄之前。**EA1 憑證 custody 完成前 seal 沒有意義且不應執行**:`Phase2SealProductionInputsV1` 的 secret-slot leg 與 topology triangulation 要求真實 slot 指紋對齊,EA1 前無真 slot 可誠實填充;且批准檔 30 天 freshness 令過早 seal 自然腐化。現狀一致:trade-core 從未 seal(§4.3 實測),fail-closed 成立。
- **seal ≠ 活化(AMD-2026-07-11-01 明文;ADR-0048 同段:「This seal is never IBKR activation authority」)**:as-built 已把此鐵律硬寫進讀面——`phase2_gate_producer_summary()` 硬編 `activation_authority: "separate_rust_activation_envelope_required"`、`ibkr_call_performed: false`、`no_contact: true`;bin 的 apply 出口同樣只回 `applied_no_contact`。sealed PASS artifact 只解除「production 永不 seal」的 gate 阻塞,**不創造任何接觸**;G4 一次性批准與 Rust activation envelope 是其後的獨立硬閘。

## 5. 禁擴清單:option A 批准機制的邊界(HMAC option B 觸發器)

AMD-2026-07-08-01 Clarification #2 原文三項觸發器,**任一命中即強制升級 option B(HMAC-signed、與 `authorization.json` 同紀律),option A 僅限 read-only / zero-money gate-seal**:

1. any **paper order-write**;
2. any **`tiny_live_adr_eligibility_v1` discussion**;
3. any **capital exposure**。

工程對位:W7(order lifecycle)第 4 項已把 option B 定為 blocking 前置,與 W8 活化紀錄設計合流;EA5 開窗硬前置含「option B 落地」。**本 W2 caller 的批准檔格式、6-binding 驗證器、ledger 語義,一律不得被複用或「順手擴充」到上述三面**——那是不同的 authorization 軸(live-money 執行軸),不是本檔可追認的範圍。

## 6. 審計軌:現狀與 W8 銜接點

**現狀** = ledger 本身就是 append-only 審計軌:`generations/<build-sha>/*.sealed.json` + `controls/<build-sha>/*.control.json`,全部 0400 write-once(`create_new`→`sync_all`→`hard_link`,絕不 rename overwrite)、control record 以 `previous_control_hash` 鏈接、`control_hash`/`generation_hash` 自證、fsync 父目錄。無 mutable `current` 檔,consumer 只從鏈 derive 唯一 active leaf。尚無 DB 事件(設計如此:本包零 DB migration)。

**W8 銜接點**(IBKR_TODO §5-W2 設計要點 3 的兌現路徑):W8 落地 `audit.asset_lane_events_v1` runtime 產生器後,每次 Seal/Supersede/Revoke 的 apply outcome 追掛一條 lane-scoped audit event,**join key = (`source_commit`, `control_id`, `control_hash`)**,payload 引用 `target_raw_hash` 與 action;ledger 保持唯一權威、DB 事件只是引用(redaction 邊界:零路徑明文之外的 secret 材料本就不存在於 record)。在 W8 之前,審計查驗手段 = dry-run 讀面 + ledger 檔案本身;不新增模組(deletion test:第二個 adapter 要到 W8 才出現,現在建 producer 是無主抽象)。

## 7. fake-only 測試邊界:47 in-file 測試 + production 零效果證明

**47 個 `#[cfg(all(test, unix))]` in-file 測試**(另 bin 內 2 個 CLI parse 測試、`tests/structure/` 6 個靜態守衛),主題群:

- **legacy seal/consume 硬化**(t1–t12):全綠 seal、二次 seal 拒、secret/approval 缺席、tamper hash、`ibkr_call_performed` 拒、unknown commit、policy flag、redacted summary、目錄權限、真 TOML 載入。
- **sealed consume 攻擊矩陣**(sealed_consume_* ×8):跨 generation/unknown build、非法檔型/mode/special bits、owner 不符、lstat→open replacement/FIFO race、production wrapper 只認 current-build。
- **approval A-model 負測試**(a_model_* ×6 + lineage hash 決定性):過期、commit 不符重放、錯 AMD、future-dated、非 owner-only、symlink。
- **triangulation / refuse-ephemeral**(f1、f3)。
- **W2 ledger 生命週期**(w2_* ×15):seal→supersede→revoke 全鏈與批准單次消費、reseal-after-revoke 防 brick ×3 變體、fork/跨 build/過期拒、ledger child replacement、**env 已設仍需 CLI flag**、中斷後 retry(orphan 收養/只補 control/冪等成功)、flock 串行化+crash 釋放+inode swap 拒+整目錄 swap 拒、單一 dirfd 組鏈、malformed build SHA 零寫。
- **verify/summary 形態**(on-disk tamper 偵測、blocked shape)。

**production 零效果證明**:①無批准檔 → `external_verification_pending`,`wrote_generation=false`/`wrote_control=false`(代碼路徑 + 測試雙證);②runtime 實測 trade-core `governance/ibkr_phase2/` 不存在 = 從未 seal;③本模組與 bin 結構性無 socket——靜態守衛禁 `TcpStream`/`tokio::net`/`reqwest`/order verbs/`sqlx` 於 bin,`no_contact` 硬編 true。**fake-only 邊界**:本包唯一「對手」是 tempdir 檔案系統與故障注入 hooks(production 中 inert),不存在也不需要 fake-TWS——任何真接觸提案都是 EA 事項。

## 8. 設計裁決表

| # | 問題 | 裁決 | 出典 |
|---|---|---|---|
| D-W2-1 | 誰可跑 seal CLI | Operator 手動、trade-core 本機 shell、逐次執行;GUI/FastAPI/engine-runtime/cron 四面全禁 | §1;IBKR_TODO §2/§5-W2;producer L2984、靜態守衛 caller-pin |
| D-W2-2 | 寫入需要什麼 | 雙閘(`--apply` × env literal `1`)+ 6-binding 批准檔 + inputs 四 leg + triangulation,缺一零寫 | §2;AMD-07-08 Clarification #2;`phase2_control_approval_is_valid` |
| D-W2-3 | 生命週期 | genesis 只准空鏈;Supersede 需 active predecessor id+hash 雙符;Revoke terminal per build SHA;pre-write guard 防 brick | §3;ADR-0048 §Phase 2 seal 段;apply L2780-2811 |
| D-W2-4 | Supersede vs 新 build SHA | 同 build 換代=Supersede;revoke 後或源碼變=新 build SHA | §3;ADR-0048 re-attestation 語義 |
| D-W2-5 | 何時 seal | EA3 前置,EA1 custody 前不執行;seal ≠ 活化(summary 硬編 `activation_authority`) | §4;IBKR_TODO §6 EA3;AMD-07-11 |
| D-W2-6 | option A 邊界 | 禁延伸到 paper order-write / tiny_live 討論 / 資本暴露;命中即 option B(HMAC) | §5;AMD-07-08 Clarification #2 觸發器原文 |
| D-W2-7 | 審計軌 | 現狀=append-only hash-chain ledger 即審計軌;W8 以 (`source_commit`,`control_id`,`control_hash`) 追掛 `audit.asset_lane_events_v1`;W8 前不建 producer | §6;IBKR_TODO §5-W2 要點 3 |
| D-W2-8 | 測試邊界 | 47 in-file(fake-only、零 socket)+ 靜態守衛;production 零效果三重證明 | §7 |

## 9. as-built 偏差清單 + 處置建議

- **D1(mode 0400 vs 文件 0600)**:Clarification #2 寫批准檔「owner-only 0o600」;as-built W2 production 的 `phase2_seal_control_approval.json`/`phase2_seal_inputs.json` 走 W1 secure consumer primitive,要求**精確 0o400**(0600 語義只殘留於 `#[cfg(test)]` legacy A-model)。方向=更嚴(去 owner 寫位),fail-closed 不變。**處置**:不改代碼;EA3 操作 runbook 必須寫 `chmod 400`,W2 收口紀錄此差異,免 operator 按 0600 佈檔被拒後誤判為故障。
- **D2(AMD 綁定重指向)**:Clarification #2 的綁定為 `adr==ADR-0048 ∧ amd==AMD-2026-07-08-01`;as-built W2 控制批准無 `adr` 欄,綁 `authorization_amd==AMD-2026-07-11-01`,而 ADR-0048/shape-AMD/contact-AMD 三者下沉到 artifact 層由 `validate()`+hash 強制。依 IBKR_TODO §2 權威鏈(新者優先),W2 受 AMD-07-11 授權,重指向成立。**處置**:接受為 as-built 設計並以本檔記錄;批准檔模板必須填 `authorization_amd="AMD-2026-07-11-01"`;W8 設計 option B 時再統一批准檔欄位族,W2 不回改。
- **D3(reviewer_roles 更嚴)**:文件只要求 Operator;as-built 要求 `PM` ∧ `Operator` 同列。**處置**:接受(更嚴方向);批准檔模板兩角色並列。

---

本文檔為**追認式收口**:PA leg 於 2026-07-15 補簽;實作先行落地 SHA `0c90de9c2` / `324fb87a8` / `7902efe71`(+ seam#2 基準 `c4b52c2e2`、W1 consume 硬化 `c082bc569`)。本檔不改變任何 runtime 姿態,不構成任何 broker 接觸/活化授權。
