# E2 PR Adversarial Review — OPS-2 Phase-2 cutover · `fix/ops2-phase2-cutover` @ `a3d27729` · 2026-06-10

**Verdict: RETURN to E1（1 HIGH + 1 MEDIUM + 1 LOW；production 代碼本體 0 defect，HIGH 是漏掃 collateral 測試）**

審查對象：worktree `/tmp/wt-ops2-cutover`（off main `28e376c0`，單 commit，9 檔 +365/−306）。
規格基準：runbook `docs/runbooks/credential_rotation.md` §13（v1.0）+ spec `docs/execution_plan/specs/2026-05-26--p1-ops-2-secret-split-design.md` §3.2/§4.1/§9.5 + A3 review。
E1 報告：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-10--ops2_phase2_cutover.md`。

---

## 親跑驗證數字（全部本機 Mac，worktree HEAD=a3d27729）

| 驗證 | 結果 |
|---|---|
| Rust full `cargo test -p openclaw_engine --no-fail-fast` | **4154 passed / 1 failed**（43 test targets；唯一 fail = `stress_tick_latency_benchmark` tests/stress_integration.rs:982，PR 9 檔不含該檔，timing benchmark 與 auth 路徑結構性無關；E1 已附 stash 基線同紅證據）— 與 E1 宣稱一致 |
| Rust targeted | lib live_authorization **24/24**；bin `ops2_phase2_cutover_tests` **3/3**；live_auth_watcher_tests **12/12**（E1 報「15/15」計數不符，檔內 `#[test]` 實為 12 — LOW nit） |
| Python E1 的 5 檔 | **62 passed / 0 failed**（總數對；per-file 拆分 E1 報「signing 16」實為 13 — LOW nit） |
| **Python 全套 control_api_v1**（E1 未跑） | base(HEAD~1 檔案) **66 failed** vs HEAD **67 failed** → **唯一新增紅 = `test_strategist_promote_api.py::TestApplyLiveGateChain::test_live_apply_all_gates_green_succeeds`**（66 條為 Mac 環境既有紅，與 PR 無關；tests/replay 4 檔 collection error 既有，已排除） |
| Mutation（Rust） | panic gate 鎖死 false → `live_auth_signing_key_missing_panics_when_live` **FAILED**（bite 證實），餘 2 綠；已還原 |
| Mutation（Python） | `_read_live_auth_signing_key` 重加 IPC fallback → secret_split **3 failed**（`ipc_secret_alone…` / `…raises_even_when_ipc_secret_set` / `…reason_is_live_auth_signing_key_missing`）— 三條 cutover 定義性測試全咬；已還原 |
| Collateral 真紅驗證 | 舊 fixture（HEAD~1 test_live_authorization_signing.py）對新 app 代碼 = **7 failed**（與 E1 宣稱完全一致）；promote_api 紅在 HEAD~1 app 代碼下 **1 passed** → 確證 cutover 所致非既有 |

---

## 必查軸結論

### 軸 1 — fallback 真死 ✅
- Rust `read_live_auth_signing_key()` = 純 `secret_env::var_or_file("OPENCLAW_LIVE_AUTH_SIGNING_KEY")`；`FALLBACK_WARN_INTERVAL_SECS`/`LAST_FALLBACK_WARN_TS`/`tracing::warn` import 全刪。
- Python `_read_live_auth_signing_key()` 純讀新 env；`_fallback_warn_state`/`_FALLBACK_WARN_INTERVAL_SECS` 刪除且有 hasattr 反證測試；`threading`/`time` import 非 dead（:614/:253 等仍用）。
- 全庫 grep：`ops2_secret_split_phase1_fallback` emit 點 0（僅註釋+負向測試）；`IpcSecretMissing` 變體 0 殘留；`ipc_secret_missing` 字串 0 production 殘留（optuna 測試名是 IPC 域同名非殘留）。
- 殘留 `OPENCLAW_IPC_SECRET` 讀取點全部 IPC-transport 域（main.rs:456 FIX-10 / connection.rs:122 / optuna_optimizer / ipc_client(_sync) / earn_routes:420 Stage-0R 防偽 = spec §2.3/§9.2 指名保留清單）✅ 無誤遷移。
- `restart_all.sh:157` seed 只在 `[ ! -f ]` 時 cp（atomic tmp+mv，rotation 不可覆蓋保護在），**只 seed 檔案、零 fallback-read**；fresh_start/clean_restart 只注入 `_FILE` env 不 seed — §13.5 rollback 依賴完好。

### 軸 2 — fail-loud 邊界 ✅（含一條 PA-級 advisory）
- `enforce_live_auth_signing_key_or_panic(live_bindings.is_some())` 與 FIX-10 gating **逐字相同**；`live_bindings` 僅在 live slot try_spawn 成功（= live 憑證 + 簽名授權驗過）才 Some → **demo-only / 無 live 授權啟動結構上不可能誤 panic**，部署炸彈方向安全。位置 main.rs:470 緊跟 FIX-10(:456)、遠在 watcher spawn(:1472) 前 = spec §9.5 滿足。
- **Advisory（PA/PM，非 E1 缺陷）**：spec §3.2 偽碼自身使 panic 在「典型缺 key 啟動」下不可達 — LIVE-GATE-BINDING-1 的 `load_and_verify`（startup/mod.rs:557-580）在 try_spawn 內先因 `LiveAuthSigningKeyMissing` 失敗 → live_bindings=None → panic gate false。實際症狀 = 引擎照常啟動、live 拒絕 spawn、WARN `error_kind=live_auth_signing_key_missing`（startup 1 次 + watcher 5s deny-loop，watcher :742/:927 走 auth_error_kind）。fail-closed 完整、§13.2 log-alert 可命中；但 runbook §13.5「panic 阻 boot」的症狀描述與實況不符（rollback 步驟本身仍然有效）。panic block 實際是防 mid-boot key/file 消失 race 的 belt-and-suspenders。實作=spec 逐字，責任在 spec 措辭 → 建議 PA 校準 §13.4/§13.5 文字 + operator 監控以 log-kind 為主信號而非 crash。

### 軸 3 — collateral 修改合法性 ✅（已修的 2 檔）/ ❌（漏 1 檔 → HIGH）
- signing/toggle 兩檔 diff = **純 fixture env-key 換名**（assertion 零改動）；舊 fixture 對新代碼 7 紅親證；toggle 6 處全換的 scope 判斷正確（其餘 4 處僅因前序 gate 先 trip 而僥倖綠，留 IPC 注入會誤導）。
- 雙語言 mutation 全 bite（見上表）→ 新測試真鎖 cutover 行為，非測試遷就。
- **漏網**：見 Finding 1。

### 軸 4 — 跨語言一致 ✅
Rust kind `live_auth_signing_key_missing`（live_authorization.rs:223）== Python reason（live_trust_routes.py:501）== runbook §13.2 兩條 alert pattern（含 `AuthError::LiveAuthSigningKeyMissing` 變體名）三方對齊；panic 文案含 §13.4 AC 要求的 `OPENCLAW_LIVE_AUTH_SIGNING_KEY` 字眼（測試斷言）。`auth_error_kind` match **無 wildcard**、10 變體全列 → 漏 arm 編譯期不可能。Display arm 同為窮舉。cross-lang pinned hex `1b2b18d7…78fc` 與 runbook §10.5 一致，Python/Rust 雙端測試保留。
（LOW 觀察：live_preflight.py:147 既有 gate log token `live_auth_key_missing` 與新 kind `live_auth_signing_key_missing` 是兩套相近 taxonomy（HEAD~1 已存在，非本 PR 改動）— alert rule 撰寫者須知，不退 E1。）

### 軸 5 — caller 完整性 ⚠️（app 層完整；test 層漏 1）
app 層：Python 唯一 env 讀點 = live_trust_routes:63；delegation 鏈（live_preflight:59→:143→executor_routes）全更新；Rust 唯一 caller = load_and_verify:386。E1 grep 在 **app 代碼**層完整。但 E1 只跑 5 個測試檔未全套 sweep → 漏 promote_api（Finding 1）。

### 軸 6 — secret 衛生 ✅
panic/RuntimeError/Display/log 全部只含 env **名**不含值；seed echo 印路徑非內容；無 `detail=str(e)`；移除的 WARN 機制本就不印值；測試用 dummy key。

### 軸 7 — naming debt 裁決
spec §4.1.1 表把 `verify_in_memory`/`compute_signature` 參數 `ipc_secret: &str` rename 同列 Phase 1 與 Phase 2 欄（「同」）→ **裁決：in-scope，本輪一併修**（Finding 2）。理由：純機械（live_authorization.rs:285/:287/:316/:334 四處 + 註釋），Rust 無 named-arg 故外部 caller（僅 live_auth_watcher_tests.rs:179 位置參數）零影響；既然 Finding 1 已開修復輪，bundle 零成本；不修則安全關鍵函數簽名永久帶誤導名（參數實為簽名 key 而非 IPC secret —— 這正是本次 split 要分離的概念）。按鏈紀律由 E1 執行，E2 不代寫。

### 軸 8 — Rust 測試紀律 ✅
`--no-fail-fast` 必要性屬實（43 targets；default fail-fast 在首個紅 target 即停）。4154/1 親證複現；唯一紅與 PR 結構性無關（檔案 disjoint + timing 性質 + E1 stash 基線）。同意另開 follow-up 不阻本 PR。

---

## 8 條 reviewer checklist
| Item | 狀態 |
|---|---|
| 範圍 vs PA 方案一致 | ⚠️ §13.3 4 檔 + 合理增檔（live_preflight=P1-01 後新 caller、executor docstring、3 test）；漏 promote_api collateral（F1）；§4.1.1 rename 偏離（F2） |
| 無 except:pass / 吞異常 | ✅ |
| 日誌 %s 格式 | ✅（新增 0 log；刪 1 WARN；觸及 log 均 %s） |
| 新寫入端點 operator role | N/A（0 新端點） |
| HTTPException 順序 | N/A（未觸及） |
| detail=str(e) | N/A（0） |
| asyncio 中 blocking Lock | ✅（反向：刪除了一個 threading.Lock） |
| 私有屬性穿透 | ✅（測試訪問模組私有函數 = 既有沿用模式） |

## OpenClaw §3 checklist
| Item | 狀態 |
|---|---|
| 跨平台路徑 | ✅ diff 0 hit |
| 注釋中文優先 | ✅（新/改註釋全中文 rationale，MODULE_NOTE 在新測試檔） |
| Rust unsafe/unwrap/panic | ✅ 0 unsafe；0 新 prod unwrap；panic=startup fail-closed mirror FIX-10，非交易 tick 路徑 |
| 跨語言 IPC schema | ✅ connection.rs 0 改（spec §4.1.4）；HMAC pinned fixture 雙端鎖 |
| Migration Guard | N/A（0 migration） |
| healthcheck 配對 | ✅ 無新被動等待；§13.6 SOP 在 runbook/TODO 域 |
| Singleton | ✅ 0 新；刪 2（AtomicU64 static + module dict state） |
| 檔案大小 | ✅ main.rs 1784 / live_authorization 1015 / live_trust_routes 1168（>800 既有，<2000） |
| Bybit API | N/A（未觸 /v5；BB sign-off 仍在 §13.3 鏈上） |

## §5 multi-session race
5a ✅ fetch 後 origin/main 領先 3 commit（`72738f5a`/`4201bf08`/`9de97d6e`）全 docs/TODO/memory `[skip ci]`，與 PR 9 檔 **0 overlap**，base `28e376c0` 仍有效；5b ✅ status clean（mutation/基線比對全程後還原，逐次 `git status --porcelain` 驗空）；5c ✅ 3 條外來 stash（含 recovered-not-mine）一律未動；5d ✅ 本報告為唯一新檔；5e ✅ review 中重 fetch 無代碼側 sibling push。

---

## Findings

| # | 嚴重性 | 位置 | 描述 | 修法 |
|---|---|---|---|---|
| 1 | **HIGH** | `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_strategist_promote_api.py:574` | 漏掃 collateral：該測試以 `_build_signed_authorization(secret=…)` 簽授權後僅注入 `"OPENCLAW_IPC_SECRET": secret`，Phase-1 靠 fallback 過；cutover 後 `live_preflight` gate=authorization FAIL（`reason=live_auth_key_missing`）→ `test_live_apply_all_gates_green_succeeds` **紅**。本分支 ship 即帶紅套件。已親證：HEAD~1 app 代碼下同測試綠；全套 base-vs-HEAD diff 唯一新增紅 | 同 toggle 檔同類修法：:574 `"OPENCLAW_IPC_SECRET"` → `"OPENCLAW_LIVE_AUTH_SIGNING_KEY"`（該檔僅此 1 注入點）。**驗證 SOP 升級**：修後跑全套 `pytest tests/ --ignore=tests/replay`，與 base 失敗清單 diff 必須回到 0 新增（不可只跑點名檔） |
| 2 | MEDIUM | `rust/openclaw_engine/src/live_authorization.rs:285,287,316,334` | spec §4.1.1 Phase 2 欄指名的參數 rename 未做：`compute_signature(auth, ipc_secret: &str)` / `verify_in_memory(…, ipc_secret: &str)` 參數實體已是 live-auth 簽名 key，名字仍叫 ipc_secret = 概念誤導正中本次 split 要消除的混淆 | rename → `live_auth_signing_key`（4 處 + 鄰近註釋若提及）；純機械、無 caller 影響（Rust 位置參數）；E2 裁決 in-scope 本輪做 |
| 3 | LOW | `helper_scripts/fresh_start.sh:81` | 陳舊註釋：「若 file 缺 → engine 走 Phase 1 fallback path」cutover 後為假——實況是 live spawn 拒絕（log kind `live_auth_signing_key_missing`），無 fallback | 註釋改 Phase-2 語義（缺 key → live 拒 spawn / Python sign raise；operator 走 runbook §13.5 seed 或 §5.2.2 urandom）。comment-only |

**Advisory notes（不退 E1）**：
- **A1（PA/PM）**：§3.2 panic block 在典型缺-key 啟動下被 LIVE-GATE-BINDING-1 post-dominate（細節見軸 2）→ 建議 PA 校準 runbook §13.4/§13.5 症狀措辭；operator 監控以 §13.2 log-kind 為主信號。
- **A2（E1 報告精度）**：watcher「15/15」實 12/12；signing「16」實 13（62 總數正確）。
- **A3**：live_preflight gate token `live_auth_key_missing` 與新 kind 為兩套相近字串（既有，非本 PR）。
- **A4**：Rust `var_or_file` 接受 whitespace-only 直接 env 值、Python `.strip()` 拒絕 — 既有不對稱，fail-closed 方向不破（簽不出 / BadSignature），非本 PR 引入。

## 結論

**RETURN to E1（3 findings）**。production 代碼本體（Rust 2 檔 + Python 3 檔 app 層）經對抗審查 + 雙語言 mutation 驗證為正確且 fail-closed 強化屬實；唯收尾不完整：1 個漏掃 collateral 測試紅在分支上（HIGH）、1 個 spec 指名 rename 未做（MEDIUM）、1 個陳舊註釋（LOW）。三項全為機械修復，修後重 E2（預期快速 PASS）→ 按 §13.3 鏈 CC → BB → PM。

E2 REVIEW DONE: RETURN to E1 · report path: srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-06-10--ops2_phase2_cutover_review.md

---

## re-E2 2026-06-10 cf1b9320

**Verdict: ACCEPT — PASS to E4。** 三項修復全驗收、0 漂移、0 新 finding。範圍嚴格限定修復驗證（production 本體上輪已全面審過，不重審）。E1 修復報告：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-10--ops2_phase2_cutover_e2_fixes.md`。

| 複審項 | 結果（全部親跑/親查） |
|---|---|
| Scope `git diff a3d27729..cf1b9320 --stat` | **恰好 3 檔 +11/−7** = 三項修復對應檔（promote_api test / live_authorization.rs / fresh_start.sh），0 額外檔漂移；E1 報告檔在主 checkout 未入 commit（可接受）；worktree porcelain clean |
| **HIGH F1** | :574 `OPENCLAW_IPC_SECRET` → `OPENCLAW_LIVE_AUTH_SIGNING_KEY`（+2 行中文注釋）；grep 證該檔 **0 殘留** IPC_SECRET 注入；親跑 `test_strategist_promote_api.py` **18/18 綠**；原紅 `TestApplyLiveGateChain::test_live_apply_all_gates_green_succeeds` **單測綠** |
| **MEDIUM F2** | 4 處 rename 全到位（:285/:287 compute_signature 簽名+body、:316 verify_in_memory 簽名、:334 body 引用）；殘餘 `ipc_secret` 恰 6 處（:114/:220/:749/:761/:803/:988），抽驗 :114（LiveAuthSigningKeyMissing 變體 rationale 注釋）+ :749-:813（負向測試攻擊情境/cutover 定義性測試名）= 全 IPC-transport 域合法引用非參數殘留；`cargo test -p openclaw_engine --lib live_authorization` **24/24**；唯一外部 caller（live_auth_watcher_tests.rs:179 位置實參）所在 target 編譯+綠（bin `openclaw-engine` filter watcher **12/12** + ops2_phase2_cutover **3/3**）= rename 零 caller 影響實證 |
| **LOW F3** | fresh_start.sh:79-83 註釋改 Phase-2 語義「缺 key → engine live 拒 spawn（log kind `live_auth_signing_key_missing`）、Python sign raise」= 與本報告 A1 advisory 實況一致（不再宣稱 fallback，亦未誤稱 panic 阻 boot）；引用段落實存（runbook §13.5 Rollback :651 / §5.2.2 urandom :192）；`bash -n` 過 |
| E1 全套宣稱抽驗 | Python「passed 4255→4256 = 淨增 1 測試」算術核實：branch diff（base..HEAD `*.py`）`def test_` **+6/−5 = 淨 +1** ✅ 自洽（fix commit 0 新測試）；Rust total 不變性：上輪 4154 passed+1 flake = 本輪 4155 passed+0 = **4155 total 兩輪一致** ✅（唯一 delta = 已知 stress timing flake 本輪綠）。本輪 E1 報告數字 **0 處不符**（採上輪校正計數 watcher 12/12） |

§5 race：5a ✅（fetch 後 base `28e376c0` 仍 ancestor）；5b ✅ porcelain clean；5c ✅ 3 條外來 stash 照例未動；**5e fire**：review 進行中 origin/main `9de97d6e`→`7b8fae45`（L2 Mesh P1-P3b 7 commits 入 main）→ 重 fetch + `comm` 比對 PR 全部 11 檔 vs sibling 改動檔 = **0 overlap**（L2 域完全 disjoint），verdict 不受影響；PM merge file-level 無衝突，merge 後 E4 全套將自然涵蓋 L2 新測試。

下一步：E4 回歸 → §13.3 鏈 CC → BB → PM（部署 gate 不變：§13.2 alert rule + Linux `--rebuild` operator-gated）。

E2 RE-REVIEW DONE: ACCEPT (PASS to E4)
