# CC 合規審計 — OPS-2 Phase-2 cutover · `a3d27729`+`cf1b9320` (base `28e376c0`) · 2026-06-10

> **PM 代落盤註記**:本報告由 CC agent 產出,該 session 無 Write/Edit/Bash 工具,內容由 PM 逐字代存(2026-06-10);CC 自述:diff 重建=worktree 直讀+token 計數對照(PR 檔集以 E2 兩輪一手審查為準),soak runtime 數字未獨立重測。

**評級:A-(APPROVE-CONDITIONAL)** · 合規 16/16(PASS 或 N/A)· 9/9 不變量 · 硬邊界 0 觸碰 · **BLOCKER:0** · **Block merge:NO** · 條件 4 項(1 doc-reconcile + 3 deploy/sign-off 證據閘)

本 PR 是**收緊方向**變更:移除 live-auth 簽名域的 legacy fallback。所有缺 key 路徑 fail-loud;任何失敗模式都是「live 不可用」而非「live 失防」——不對稱性決定了條件項都是 sign-off 閘而非代碼缺陷。

## 六軸逐一結論

| 軸 | 結論 |
|---|---|
| 1. 5-gate 完整性 | **PASS,Gate 5 強化**。G1 `live_reserved`:簽發路由 `_require_live_reserved_global_mode`(live_trust_routes.py:183 精確等值、fail-closed on unreadable)+ 驗證端 `approved_system_mode` 入 canonical payload + Rust `APPROVED_SYSTEM_MODE_LIVE_RESERVED`(live_authorization.rs:325)不變。G2 Operator:`_require_operator` 在兩條寫路由 :963/:1089 不變。G3 `OPENCLAW_ALLOW_MAINNET`:PR 11 檔 0 命中,bybit_rest_client 兩語言守門未動。G4 secret slot:`has_credentials` gate(startup/mod.rs:586)未動。G5 簽名 authorization.json:**強化**——專用簽名 key 單一來源,IPC secret 單獨存在不能再簽/驗(雙語言 mutation 經 E2 親證咬合)。無新增例外路徑。 |
| 2. 無靜默降級 | **PASS**。四路徑全 loud:Rust 啟動 = panic gate(main.rs:124-136,:470 呼叫,緊跟 FIX-10、先於 watcher spawn);Rust 驗證 = `AuthError::LiveAuthSigningKeyMissing`(load_and_verify 第一步 :385-386)→ LIVE-GATE-BINDING-1 拒 spawn(startup/mod.rs:570-581 WARN+return None)+ watcher 5s 重驗、teardown 不受 backoff 限制;Python sign = RuntimeError 先於一切(live_trust_routes.py:240-249);Python verify = `unverifiable`+`live_auth_signing_key_missing`(:494-502),preflight gate fail-closed(live_preflight.py:143-154)。`auth_error_kind` 窮舉無 wildcard。**0 個「缺 key 視為已授權」分支**。 |
| 3. 授權檔寫入路徑 | **PASS**。raise 在 :241 任何構造/寫入之前 = 結構上不可能部分寫入;`_atomic_write_json`(:152-180)mkstemp 同目錄 + fsync + chmod 600 + `os.replace` 原子 rename + 異常 unlink tmp。生產 caller 恰 2 個 = `/auth/renew`(:1023) + `/auth/renew-review`(:1123),均 Operator+live_reserved 雙閘;簽失敗時前授權已被 revoke 刪除 → 留下的是「無授權」(Rust 拒 live)= 收縮方向(原則 6)。 |
| 4. 回退安全 | **PASS(附 CC-MED-1 doc 條件)**。restart_all.sh:157 seed 是 `[ ! -f ]` 嚴守的**檔案 provisioning**(原子 tmp+mv+600),**不讀 legacy env、不構成 runtime fallback**(引擎/Python 只讀新 env/file);rotated key 不可被覆蓋。runbook §13.5 rollback step 3 是獨立的手動 cp,不依賴自動 seed。但注意:seed 複製的是 **ipc_secret.txt 同 material 而非新生成 urandom**——任何未來 missing-file 重啟會靜默重耦合兩 secret 域(直到 §13.6 規定的 2026-09-08 首次 90d urandom rotation),且 runbook §4.2.1 line 85 明文宣稱「Phase 2 後 restart_all 不再 seed」與出貨腳本矛盾(詳 CC-MED-1)。 |
| 5. demo/LiveDemo | **PASS**。非 live 啟動不 panic(`live_pipeline_active=false` 直接通過,測試 main.rs:1757 鎖死);watcher 只動 Live slot,demo/paper 結構上不可能被誤殺。LiveDemo 不放鬆:`env_label(LiveDemo)="live_demo"` 走完整 verify(schema/mode/HMAC/expiry/env_allowed),Demo/Testnet → `UnsupportedEnv` 根本不入此 gate;`expires_at_ms <= now` 嚴格拒絕;模組頭 2026-04-18 operator 設計註記原文保留。授權-TTL-風險-審計 0 弱化。 |
| 6. 16 原則 + 9 不變量 | **16/16、9/9**(細表見下)。#1/#5/#6/#8 重點全 PASS;唯 #8/#10 的證據鏈掛 4 條件。 |

## 16 原則逐條

| # | 狀態 | 證據 |
|---|---|---|
| 1 單一寫入口 | PASS | authorization.json 唯一寫點 `_write_signed_live_authorization`(2 operator 路由);刪除唯 revoke 路徑;訂單寫入口未觸及 |
| 2 讀寫分離 | PASS | trust-status 為只讀診斷(回狀態不 raise,by-design);0 新寫 endpoint |
| 3 AI≠命令 | N/A | lease 面 0 觸及(`decision_lease_required→true` 不變) |
| 4 不繞風控 | PASS | 0 風控路徑觸及;只收緊 |
| 5 生存>利潤 | PASS | 移除寬鬆 fallback;失敗=live 下線非失防 |
| 6 失敗收縮 | PASS | 四路徑 fail-loud;E2 雙語言 mutation 驗咬合 |
| 7 學習≠Live | N/A | 未觸及 |
| 8 可解釋 | PASS* | 錯誤變體窮舉、audit log、跨語言 fixture pin `1b2b18d7…78fc`;*doc 漂移記 CC-MED-1 |
| 9 雙重防線 | N/A | 未觸及 |
| 10 認知誠實 | PASS* | 代碼註釋誠實標明 soak 依據;*soak 證據本身須隨 sign-off 附件(C-A) |
| 11 最大自主 | PASS | 0 能力削減;demo lane 不受影響 |
| 12-16 | N/A/PASS | 學習/成本/組合面 0 觸及 |

## 9 安全不變量

I1 pre-trade audit N/A·未觸 / I2 lease PASS·未觸 / I3 fills N/A / I4 風控降級 N/A / **I5 授權失效→teardown PASS·強化**(missing key 現同樣觸發 deny/teardown,teardown 永不受 backoff)/ I6 mainnet env gate PASS·未觸 / I7 retCode N/A / I8 reconciler N/A / I9 Operator+live_reserved PASS(:963/:965/:1089/:1091)。

## 硬邊界

**無觸碰**。`execution_state`/`execution_authority`/`live_execution_allowed`/`decision_lease_emitted`/`max_retries`/`OPENCLAW_ALLOW_MAINNET` 在 3 個被改 Python 生產檔 token 計數 worktree=checkout 完全一致(4/5/5);Rust main.rs 兩側皆 0;跨平台路徑 0 新增;殘留 `OPENCLAW_IPC_SECRET` 讀點全數 IPC-transport 域(main.rs:456 FIX-10、connection.rs、ipc_client(_sync)、earn_routes:420 Stage-0R 防偽 = spec §2.3 指名保留);`IpcSecretMissing` 變體與 `ipc_secret_missing` reason 僅存註釋。

## 違規清單 + 條件

**BLOCKER:無。**

| # | 級別 | 內容 | 處置 |
|---|---|---|---|
| CC-MED-1 | MEDIUM(doc-governance,唯一待修) | runbook §4.2.1 line 85 宣稱「Phase 2 後 `restart_all` 不再 seed;missing = startup panic 阻 boot」雙重失真:(a) 出貨 restart_all.sh:157 保留 auto-seed(與 §13.3 PR 範圍表一致——該表本就不含 restart_all.sh);(b) panic 被 LIVE-GATE-BINDING-1 post-dominate(E2 A1),典型症狀=live 拒 spawn 非 panic。同措辭亦在 spec §3.3 line 185、runbook §13.5 step 2。operator 執行的 live-auth SOP 與實況矛盾 = 原則 8/10 追溯性缺口 | PM 拍板 seed 去留(保留=改 §4.2.1/§13.4/§13.5 措辭為「seed 保留作 rollback 墊、缺 key 症狀=live 拒 spawn + log kind」;移除=另開 PR 並補 §13.5 依賴分析)。doc-only,可同鏈 commit,**deploy 前完成** |
| CC-LOW-1 | LOW(cosmetic) | Python `_sign_authorization_payload(payload, ipc_secret)`(live_trust_routes.py:146-148)參數名殘留 `ipc_secret`——F2 在 Rust 消滅的同類概念誤導;spec §4.1.1 rename 表只列 Rust 函數故不屬漏做 | 非阻塞 debt,下次觸檔時改 |
| CC-LOW-2 | LOW(既有,承 E2 A3) | preflight gate token `live_auth_key_missing`(live_preflight.py:147)與 canonical kind `live_auth_signing_key_missing` 雙 taxonomy;runbook §13.2 alert 清單未含前者 | §13.2 checklist 加一行或統一 token |

**Sign-off / deploy 條件(非代碼缺陷,過 PM 閘前必清):**
- **C-A(承 Phase-1 C-2)**:soak WARN=0 的判定依據在 TODO v122(CC 本機兩份 checkout 僅 v119/v120,無法親驗;任務自述含 log 截斷 caveat,且 /tmp log + 三次全量重啟天然有覆蓋缺口)。按 CC drift 防線,PM sign-off 包必須附 §13.1 grep 實際輸出 + 覆蓋面佐證(log mtime/size 或 journald 跨 05-27..06-10 區間)。註:即使覆蓋不完美,cutover 失敗模式只有可用性損失、無失防路徑——故為條件非 blocker。
- **C-B(承 Phase-1 C-3)**:TODO 顯示「≥1 次 /auth/renew」仍操作員阻擋(纏 OP-1)。§13.1 自帶救濟(cutover 時手動 renew + 5s watcher respawn 驗 trust-status)——必須執行並留證。
- **C-C(承 Phase-1 C-5)**:§13.2 外部 Grafana/journald alert 同步 + operator 親簽 audit row(`ops2_phase2_external_alert_aligned`)為 repo 外不可 audit 項,Linux `--rebuild` 前完成。
- **鏈序**:§13.3 規定 CC 之後仍有 **BB sign-off + PM approve**,本判定不替代。Phase-1 C-1 已由本 PR 滿足;C-4 為 P2 追蹤項(`P2-OPS-2-AUDIT-ENDPOINT`)不阻 cutover。〔**PM 核註 2026-06-10(二次修訂)**:CC 原文保真。PM 初判 BB 可跳過(diff 零 Bybit-facing 面),後經 runbook §13 owner 行(:586)發現明列 BB exchange-facing sign-off→撤回裁定補派;**BB 已完成 SIGN-OFF(0 FLAG)**,報告 `docs/CCAgentWorkSpace/BB/workspace/reports/2026-06-10--ops2_phase2_cutover_bb_signoff.md`。鏈序條件就此關閉。〕

## 判定

**APPROVE-CONDITIONAL(A-)**。代碼本體 16/16 + 9/9 + 5-gate 0 弱化(G5 強化),fallback 真死、fail-loud 全覆蓋、寫入原子、回退不復活 legacy env、demo/LiveDemo 不誤殺不放鬆。不阻 merge;CC-MED-1 + C-A/B/C 清完才過 PM deploy 閘。

關鍵檔案:`rust/openclaw_engine/src/live_authorization.rs` · `rust/openclaw_engine/src/main.rs:124,456,470` · `rust/openclaw_engine/src/startup/mod.rs:556-583` · `program_code/exchange_connectors/bybit_connector/control_api_v1/app/live_trust_routes.py:48,152,240,494,963,1089` · `app/live_preflight.py:43-154` · `helper_scripts/restart_all.sh:152-172` · `docs/runbooks/credential_rotation.md:79-86,582-688`
