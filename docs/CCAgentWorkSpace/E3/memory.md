# E3 Memory — 工作記憶

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；agent 完成序列照常追加於檔尾。

## 長期教訓

- 審計閉合 SOP：source-fixed ≠ runtime closed——修碼/寫 cron 後必須 reload（uvicorn/engine restart、crontab install）並 runtime 重驗才算 closed；API 與 engine 同步 restart 的部署協調也在審計範圍內。
- 五項 Live 門控（live_reserved／Operator auth／OPENCLAW_ALLOW_MAINNET／secret slot／authorization.json HMAC+TTL+env）是全鏈審計固定軸；`live_preflight.verify_signed_authorization` 是唯一驗簽 SSOT（兩個共用門控函數皆 delegate 它）；Rust `order_manager.rs place_order` 是唯一 OMS 寫入口。
- 平行門控不等於漏洞：Python soft gate（preflight/display）旁必有 Rust binding gate 才算守住——只看 Python 會誤報、只看 Rust 會漏 IPC 偽造面，兩端都讀到才能下 verdict（Earn 9-gate 案例）。
- LiveDemo 只跳 mainnet-only Gate3，其餘 1/2/4/5 全保留；endpoint label 未知一律當 mainnet（取嚴不降級）。
- grep glob 永遠加引號（`--include="*.py"`）；整批 parallel 空輸出先疑 shell 引號/工具假象，換引號或單命令重試；絕不從空/可疑輸出 ship finding 或 clean verdict。
- 設計安全性 ≠ 實作安全性：design review 中撞見的現存代碼漏洞（如未 gate 的寫端點）立即標修，不等新模組建構排程。
- redactor/消毒審計方法：keyword-anchored 結構性漏 bare secret；完整防線=keyword 臂+結構臂（DSN/JWT/IP）+編碼正規化（NFKC/url-decode/zero-width strip）+裸高熵臂；keyword-gated 方案的 keyword-set 完整性本身是 attack surface，須逐一打 named-asset 的 customary keyword（如 hmac_key/signing_key）。
- 殘留誠實度以 code 驗證：`xfail(strict=True)` + 0 XPASS 才算文件化殘留，prose 自陳不算。
- ReDoS 審計分兩軸：regex catastrophic backtracking（almost-match payload 探）vs Python per-char/per-match 迴圈 polynomial（match-density scaling 探）；準則是線性 vs 超線性（200K/400K/800K ratio），非絕對 ms 牆；off-hot-path fail-soft 固定開銷不 flag。
- 消毒範圍必掃 adjacent durable stores（agent.lessons、cost_state JSON、任何 `_write_raw`/`to_dict` 落盤面），不只主 forensic ledger；untrusted 通道（web fetch/free-text context/LLM echo）按 zero-tolerance 校準。
- path-leak 防線必須在源頭（loader 只回 basename）：dict-detail HTTPException 與 200-body 都繞 str-only `_LEAK_PATTERN` sanitizer；驗修要同時證「源頭乾淨」與「route 確實繞 sanitizer 故源頭是唯一防線」兩面。
- auth gate 審計：「對抗 actor 全 403」必須用 mutation spy 證 gate-before-mutation（無 TOCTOU），不能只看 status code；AND-composition gate 的 reason_code 順序要求 role/scope 兩維獨立打矩陣。
- fail-safe／posture 審計：subtraction-only 要驗到 dispatch 終態 routed_to 而非只 SM state enum；「只標記不自動切換」要 grep 該欄位唯一 write site 在 `__init__`，別只信 docstring。
- 並發/deadlock 審計：先找「持鎖函數→再取鎖」具體 call pair，再高並發 stress + still-alive watchdog 證無 deadlock；macOS 無 `timeout` 指令，腳本內用 stop Event + join(timeout) 自帶 watchdog。
- in-memory dict 以 attacker-influenceable 維度為 key 時必須有 evict/TTL/maxsize，否則 latent memory DoS；dormant（0 route caller）面記為 latent/P3-gated 不阻 gate，但 wire 前必須收口。
- PG role/權限：PUBLIC default CONNECT 是真 DB 攻擊面（查 `pg_database.datacl`）；SCRAM-SHA-256 要在 CREATE ROLE 同 session 先 SET password_encryption；新 secret 檔對齊 `settings/secret_files/<subdir>/<name>`（0600、gitignored）既有 pattern。
- Migration 真入口是 engine startup `MigrationRunner::run_if_enabled`（OPENCLAW_AUTO_MIGRATE=1），不存在獨立 sqlx_migrate binary；治理文件引用的指令/binary 要實證存在再簽。
- 嚴重度校準看真實攻擊路徑：資產是否真會進該通道（如 auth_signing_key 不入 L2 context→LOW 非 HIGH）、是否有第二道防護（str(e) 雙防），不按理論最壞拍嚴重度。
- E3 報告慣例：對抗審計結果返回 text output 給 parent agent（不存 .md）；長週期全鏈審計存 `workspace/reports/` 並在 memory 留索引行；承前輪用 [[條目標題]] 鏈接。

## 近期記錄

### 2026-07-07 Demo test runtime/loss-control unblock pre-review

Verdict: `BLOCKED_STOP_LOSS_CONTROL`. Operator assertion that runtime/loss-control was unblocked and demo testing could proceed was not sufficient: latest PM packet remains `BLOCKED/STOP_LOSS_CONTROL` on `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0` plus expired standing auth; no guardrail/materialization occurred; AI/ML WP7 packet still classifies neighbor state as `RUNTIME_LOSS_CONTROL_BLOCKED`; Mac source is ahead/dirty while GitHub and Linux are aligned at `77f0b567...`. BB should not be dispatched for demo testing until PM produces a new exact-scope source-stable runtime/env or loss-control packet. Report: `docs/CCAgentWorkSpace/E3/workspace/reports/2026-07-07--demo_test_runtime_loss_control_unblock_e3_review.md`.

### 2026-06-07 L2 Advisory Mesh v3 設計安全審計

**評級：CONCERNS（0 CRITICAL / 2 HIGH / 3 MEDIUM / 4 LOW）**

**範圍**：PA design `2026-06-05--l2-advisory-mesh-design-draft.md` v3 + 相關 live code（`layer2_engine.py`, `layer2_routes.py`, `layer2_tools.py`, `governance_autonomy_service.py`, `provider_keys_store.py`, `engine_watchdog.py`, V131-V133 migrations）

**架構安全性**：
- `expand=human / contract=auto` 非對稱設計正確，LANE_DIRECTION typed invariant 邏輯無誤
- §F fail-safe 最壞路徑=NO_ADVICE=今日行為，不阻交易/風控
- 5 hard gate 未觸及，Orchestrator 無 trading-scope lease / order path / IntentProcessor import
- V134 設計無 credential 欄位，`provider_keys_store.status()` 永不回明文 key
- MIT-MF-1 grep: 0 hits — CLEAN

**HIGH findings（需修才能過 E2）**：
1. HIGH-1：`/cost/reset` (POST) + `/cost/pricing` (POST) 缺 `require_operator_role` → 任何已認證用戶可歸零每日預算計數器（DOC-08 $2/day cap 繞過）或修改 pricing table。`layer2_routes.py:354` + `layer2_routes.py:389`
2. HIGH-2：`layer2_engine.py:703` `str(e)[:500]` 進 `session.final_summary` → GET sessions 回 `current_actor`（無 operator 要求）→ 內部錯誤細節洩漏給 viewer role

**MEDIUM findings**：
- MEDIUM-1：§F fail-safe state machine（TRIPPED/GLOBAL_CONSERVATIVE/circuit trip）設計正確但 code 不存在，Orchestrator 實作時必須第一天包含
- MEDIUM-2：`canary_events.jsonl` 仍無告警消費者，sentinel 告警功能在 watchdog alert wiring 未完成前無運營價值（20h 宕機缺口未關）
- MEDIUM-3：V134 `agent.l2_calls` 不存在（最高遷移 V133），D3 基礎未建；per §J step 1 order，任何能力不得在 V134 前部署

**LOW findings**：
- LOW-1：L1 triage `str(e)[:100]` 在 trigger response（operator-only 端點，影響較低）
- LOW-2：`L2AdvisoryOrchestrator` / `ResearchAlphaWealthController` 未在 singleton-registry.md 預登記
- LOW-3：`LANE_DIRECTION` typed loader 只在設計，未在代碼；建議在 E1 前寫 RED test
- LOW-4：trigger request `context` 自由文字無 prompt injection 清洗（MEDIUM-D 遺留；PromptContract 是結構修法）

**關鍵教訓**：設計安全性 ≠ 實作安全性。HIGH-1 是現存代碼漏洞（非設計問題），應立即修復不等 Orchestrator 建構。

報告：見本次 assistant 訊息（不存 .md 檔，返回 text output 給 parent agent）

### 2026-06-08 L2 D3 Phase 1 sanitize-before-persist 對抗審計（E3-HIGH gate）

**Verdict：RETURN（sanitize gate 未過）— 1 HIGH（redactor 涵蓋率對抗失敗）+ 2 MEDIUM + 2 LOW**

**範圍**：E1 工作樹未 commit（branch `feature/l2-critic-lessons-tools`）：`l2_secret_redactor.py`（新）/ `l2_call_ledger_writer.py`（新）/ `layer2_engine.py:323-375,649-662` 接線 / `error_sanitize.py`（reuse）/ V134/V135/V136 / `test_l2_d3_ledger.py`。規格 = PA `2026-06-08--l2-d3-phase1-tech-design.md` §B（LOCKED）。

**真正在寫入路徑、無窗口？ → 是（結構正確）。** writer `record_l2_call` Step1-2 消毒 → Step4 sha256 算已消毒文本 → Step5 INSERT，同函數內順序，非 async post-hoc。engine 只把 raw 傳 writer，不自寫。sha256-over-sanitized 親驗對（test_sha256_over_sanitized_text 真 bite）。append-only DDL V134/V135/V136 三表全 REVOKE UPDATE/DELETE + trading_ai 只 INSERT/SELECT + 零 column-level UPDATE grant（親 grep 確認）。**結構/順序層 PASS。**

**合成密鑰 100% 被 `[REDACTED:*]`？ → 否。** 親跑 24 個合成 payload（無真鑰）打真 redactor 碼：
- **keyword-adjacent（api_key= / password= / Bearer / DSN / X-BAPI-SIGN= header 名）全 redact ✓**
- **bare secret 無相鄰 keyword 全 LEAK**：裸 Bybit-key 形（18 alnum）/ 裸 36-char / 裸 64-hex HMAC / base64 blob(JWT 形 + `+/=`)= 全 verbatim 落庫，hits=[]。
- zero-width space 插入 key 中 → LEAK（unicode 規避）。url-encoded `%3D` → LEAK。`api_key=` 值 <16 char → LEAK（min-length window）。`172.16.*` / `192.0.*` 私有 IP 不在 pattern → LEAK。JSON header-echo `"X-BAPI-SIGN":"<hex>"` dict 形 → LEAK。
- **根因**：redactor 是 keyword-anchored（regex 全要相鄰 `key=`/scheme/`Bearer`）；無「裸高熵 token / base64-blob / 結構性無 keyword secret」arm。與設計 §B.2 自陳「寧可多遮也不漏遮 secret」矛盾——實際漏遮 bare 形。

**exploitability 校準（為何 HIGH 非 CRITICAL）**：本 box 高值具名資產（Bybit key material / authorization.json / DSN）洩漏時幾乎總帶 keyword/結構脈絡（scheme / `password=` / `X-BAPI-*` 名 / `Bearer`）→ redactor 接得住；且 str(e)→durable 路徑雙重防護（production error_sanitize 只回 classified message，OPENCLAW_DEBUG=1 時 writer 再過 redactor 接住 DSN，親驗）。但 `raw_response`/`input_context` 非可信乾淨通道：L2 有 TOOL_WEB_SEARCH + TOOL_FETCH_URL（抓任意外部內容）+ free-text `context`（MEDIUM-D prompt-injection 未清洗未解）→ 攻擊者可植入 bare token/blob，LLM echo 進 raw_response → 裸形繞過。zero-tolerance 政策下任何 bare 規避即未達「100% [REDACTED]」→ gate RETURN。

**ReDoS/DoS → CLEAN**：7 條 adversarial regex payload（200K-400K char）全 <50ms，無 catastrophic backtracking；redact_jsonb 5000-key dict 313ms 線性，writer fail-soft 離交易熱路徑。

**adjacent durable store 不過 redactor（範圍邊界 finding）**：`agent.lessons`（`layer2_critic.py:480` INSERT）落 LLM-distilled lesson content（`title: detail` ≤4000），**不經 redactor**；本 PR 只動它設 `context_id`（非引入）。但 D.1.1「applies everywhere」對它不成立——lesson 文本若 echo secret 即裸落 durable。MEDIUM。`layer2_cost_tracker._save`（:189/214）= config/pricing/adaptive only，無 prompt/summary → CLEAN（合 PA §0）。

**新寫端點 → 0**（無 route 檔改動，git diff 確認；prior HIGH-1 `/cost/reset` 不在本 PR scope 非重引入）。`layer2_types.py` 只加 `l2_reply_id` lineage handle 非 secret 欄。

**修補方向（過 gate 三選）**：(1) redactor 加「結構無關」arm：裸高熵 token（shannon-entropy gate 或 `[A-Za-z0-9_\-]{32,}` + base64/hex 形）+ 補 172.16/192.0 私有段 + unicode normalize（NFKC + strip zero-width）+ url-decode-then-scan；(2) 對 raw_response/web-fetch/context 視為 untrusted，落庫前強制 entropy-scan 高熵子串遮罩；(3) 把 `agent.lessons` content 也路由過 redactor（D.1.1 applies-everywhere 真落實）。E1 測試只覆 keyword-adjacent，須補 bare/blob/unicode/url-enc 負向對抗 case。

報告：返回 text output 給 parent agent（不存 .md）。承 [[2026-06-07 L2 Advisory Mesh v3 設計安全審計]]（HIGH-2 str(e) 此 PR 在 ledger 路徑已結構性閉合；HIGH-1 cost route 仍 P2 open）。

### 2026-06-08 L2 D3 Phase 1 sanitize gate re-audit（redactor v2 — E3 PASS）

**Verdict：E3 PASS（sanitize gate 過）— 0 CRITICAL / 0 HIGH / 0 MEDIUM（前輪 HIGH 已封）/ 2 LOW（1 pre-existing scope + 1 over-redact UX）**

**範圍**：重驗上輪 RETURN（v1 keyword-anchored 漏 bare/編碼，1 HIGH+2 MED）；E1 重寫 `l2_secret_redactor.py`→v2（`REDACTOR_VERSION="l2_redactor.v2"`），branch `feature/l2-critic-lessons-tools` HEAD `6d312405` 未 commit。親跑真 redactor 碼（無 mock），合成密鑰（無真鑰）。

**核心結論（親跑 27-payload 矩陣 + 邊界 probe + ReDoS 800K + str(e) 雙防）**：
1. **合成密鑰 100%（除文件化殘留）被遮 = 是**。0 unexpected leak。上輪全部 bare 漏點封死：24/36-char alnum、64-hex HMAC、bare JWT（`s_jwt` 結構臂）、base64 blob、zero-width-in-keyword（NFKC+strip）、url-enc password/DSN（decode-once）、fullwidth（NFKC）、私有 IP 10/172.16-31/192.168/192.0.2/169.254/IPv6 fc00·fe80、JSON header-echo dict（`_SENSITIVE_KEY_RE` key-name 臂）全 `[REDACTED:*]`。
2. **殘留誠實度 = 誠實**。殘留**只剩** `<24-char short-bare-context-free`（邊界 probe 證：≥24+≥2 字元類才遮；18/20/23-char bare LEAK，24+ caught）。E1 用 `@pytest.mark.xfail(strict=True)` 在 `test_l2_d3_ledger.py:240` 明寫此殘留 + 資訊論理由，未藏未誇；`strict=True` 意味未來誤「修好」會 XPASS fail 逼重決。**真無法以合理 FP 代價封**（降 floor<24 會大量誤遮散文）。
3. **v2 無新 bypass**。double-encode（`%2561`）decode-once 後殘 `%XX` 文字，trailing 高熵 run 仍被高熵臂接住（defense-in-depth，非乾淨繞過）；512-cap >cap 分支直接遮（不漏後段）；NFKC ligature（ﬁ→fi）不拆解密鑰反而還原；all-special `+/=` keyworded value 仍遮。合併 dispatch（`__keyworded__`/`__struct__`）無漏臂。
4. **ReDoS = CLEAN（嚴格線性，非超線性）**。10 條 adversarial payload @200K/400K/800K：800/400 = 1.87-2.02x、800/200 = 3.92-4.07x，**全線性無 catastrophic backtracking**。worst=Bearer-spam 241ms@800K 仍 1.87x 線性（退化全-keyword 輸入，真實 L2 文本不可能）。`redact_jsonb` 5K→20K key = 22.7→91.2ms（4x 線性）。
5. **64ms@400K 不 flag**。安全準則是「線性 vs catastrophic」非「informal 50ms 牆」；固定開銷（off hot-path、fail-soft、低頻 manual-trigger、writer 內已吞 NEVER raise）非漏洞。informal 50ms 是 perf guidance 非 security gate。
6. **agent.lessons 真過 redactor = 是**（上輪 MED 已閉）。`layer2_critic.py:463 content = _redactor.redact(content).text` 在 `agent.lessons` executemany INSERT（:484）之前。import :50。
7. **str(e) 雙防完好**。production `error_sanitize` 只回 classified message（`_DEBUG` module-cache）；DEBUG 模式 detail 夾 `str(exc)[:200]` 會漏 DSN，但 writer Step3（`l2_call_ledger_writer.py:190 safe_reason=_redactor.redact(...)`）第二道接住 DSN+private_ip+sign。親驗 fresh-import DEBUG=1 確認。sha256 算在已消毒文本（`prompt_sha256/response_sha256`，:196-197），raw≠redacted hash 確認。

**2 LOW（不阻 gate）**：
- **LOW-1（pre-existing，非本 PR）**：`layer2_cost_tracker.record_session`（engine :801 live 呼叫）→ `Layer2Session.to_dict()` 含 `final_summary`（可為 `response.text[:2000]` 原始 LLM 輸出或 `str(e)[:500]`，engine :678/:789）+ `recommendation.reasoning` + `insights` → `_write_raw` 落 durable `runtime/layer2_cost_state.json`，**不過 redactor**。但檔 gitignored + chmod 0600（owner-only）+ 非 append-only forensic + MAX_SESSION_HISTORY rotated；本 PR 未動 cost_tracker（`layer2_types.py` 只加 `l2_reply_id`，diff 證 final_summary/reasoning 是 pre-existing）。D.1.1「applies everywhere」是 D3 forensic ledger scope，此 JSON 是另一較低嚴重面。與上輪 agent.lessons MED 同類但更低（local-only 0600）。建議後續把 `final_summary`/`reasoning` 落 cost_state 前也過 redactor（小修，非 gate-blocker）。
- **LOW-2（over-redact UX）**：高熵臂對 benign 散文 2/8 FP（`OPENCLAW_ALLOW_MAINNET=1`-含長 run、`scope=CanaryStagePromotion` 20-char）誤遮 → forensic 可讀性降。§B.2 north star 明示可接受（寧多遮）；L2 prompt/response 非 prose-fidelity-graded。記錄非阻擋。

**教訓**：(1) redactor 從 keyword-anchored→「keyword + 結構(DSN/JWT/IP) + 編碼正規化(NFKC/url) + 裸高熵」多臂，是封 bare/編碼規避的正解；單 keyword 臂結構性漏 bare。(2) 殘留誠實度看「code 內 xfail strict + 資訊論理由」非 prose 自陳——E1 此次做對。(3) ReDoS 真準則是線性 vs 超線性（壓 200K/400K/800K 看 ratio），非絕對 ms 牆；固定開銷 off-hot-path 不 flag。(4) 重審範圍要再掃 adjacent durable store（cost_state JSON 是 ledger 外平行面，grep `_write_raw`/`to_dict` 才抓到）。

報告：返回 text output 給 parent agent（不存 .md）。承 [[2026-06-08 L2 D3 Phase 1 sanitize-before-persist 對抗審計]]（上輪 1 HIGH+2 MED 全閉：bare/編碼 HIGH→v2 多臂封；agent.lessons MED→:463 接線；str(e) MED→雙防確認）。

### 2026-06-08 L2 D3 sanitize gate FINAL re-audit（redactor v3 — E3 PASS）

**Verdict：E3 PASS（sanitize gate 過）— 0 CRITICAL / 0 HIGH / 0 MEDIUM / 3 LOW（1 keyword-set gap + 1 worst-case superlinear + 1 pre-existing scope）**

**範圍**：重驗 v2→v3（operator 拍板 A 移除 blanket bare 高熵臂回 keyword-gated + 結構臂，接受 naked-context-free 殘留；E1 加 store-original-by-span + cost_tracker LOW-1 fix）。`l2_secret_redactor.py` v3（`REDACTOR_VERSION="l2_redactor.v3"`）+ `layer2_cost_tracker.py`，branch `feature/l2-critic-lessons-tools` HEAD `6d312405` 未 commit。親跑真 redactor 碼（無 mock），合成密鑰（無真鑰）。E1 suite 46 passed + 4 xfailed（0 XPASS）。

**核心結論（親跑 70+ payload 多部矩陣）**：
1. **移除高熵臂沒弄壞任何結構/keyworded/編碼臂 = 確認**。29 coverage 向量（api_key=/apiKey/api_secret/secret_key/access_token/password/PGPASSWORD/token<16/X-BAPI-SIGN/sign/Authorization-Bearer/裸Bearer/signature/approval_token/secret_slot + 結構 JWT/DSN(postgres·redis·mongodb+srv)/私有IP 10·172.16·192.168·127·169.254·192.0.2·IPv6 fc00·fe80/internal-host/.local）全 `[REDACTED:*]` 0 secret-byte 殘留。7 編碼規避（zero-width-in-keyword/fullwidth-keyword/url-enc-password/url-enc-DSN/zero-width-Bearer）帶 keyword 全接住。
2. **★ store-original-by-span 0 partial-residual leak（新攻擊面）= 確認**。13 對抗（ZW 插值中/首/尾邊界、url-enc 片段 %41%42、fullwidth 折疊、ligature ﬁ→fi、secret 在文本結尾無下一字元邊界、DSN cred url-enc、ZW 每字元間插）→ 存入 original 文本零 raw-secret-bytes、零 ≥8-char fragment。offset map「下一字元起始當 end」fail-safe 寧多遮不漏。零-secret 輸入 byte-identical（中文全形/合法 %2F/zero-width）確認。
3. **fast-path 不漏偵測 = 確認**。4 clean-ASCII secret 走 fast-path（_NEEDS_OFFSET_MAP_RE 無命中 + NFKC-normalized）皆遮；同輸入 +ZW 強制 slow-path 亦遮，fast/slow parity OK。
4. **ReDoS = 非 catastrophic（polynomial ~n^1.7 worst，realistic linear）**。catastrophic-backtracking 經典觸發（near-JWT-no-3rd-dot / near-DSN-no-@ / Bearer-no-terminator / ipv6-colons-only）全 flat ~45ms@200K = regex 臂無回溯（互斥字元類，docstring 屬實）。decompose：worst 成本在 normalize per-char Python 迴圈（86ms）非 regex（23ms）。realistic sparse-secret prose 25→206ms@100K→800K 嚴格線性；pure-prose fast-path 196ms@800K。**僅 degenerate 100%-secret-like 輸入（36363 dense evasion token/800K）→9.4s = O(n·matches)，非指數**。store-original per-char map 是 v3 新增 worst-case 複雜度（vs v2 無 map）。
5. **sha256 算在 original-redacted（非 preprocess）+ str(e) 雙防 = 完好**。sha(redacted)≠sha(raw) 確認 hash 不可回推原文；零-secret byte-identical；str(e)-with-DSN（OperationalError postgres://redacted@10.0.0.7）→ `[REDACTED:db_dsn]`，writer Step3 二道接住。
6. **cost_tracker LOW-1 閉 = 確認（真 path）**。`_sanitize_session_dict_for_persist` 真跑：final_summary（DSN+api_key）/recommendation.reasoning（Bearer）/insights[].detail（X-BAPI-SIGN）全遮、cost_usd·symbol 結構欄保留、落 layer2_cost_state.json 前消毒。critic lessons :463 redact-before :484 executemany（上輪 MED 持續閉）。
7. **JSONB-key 臂（header-echo dict）= OK**。{"Authorization":bare-value} / nested {"api_key":...} / value-內私有IP 全遮、User-Agent 保留。

**明確答**：
- 「除文件化 naked 殘留外是否 0 leak」→ **否，有 1 個額外 keyword-set gap（LOW-1，見下）**。其餘除 4 個 xfail-strict 文件化殘留（bare 24/35-char alnum、bare 64-hex、bare base64）外 0 leak。
- 「store-original 是否曾部分殘留 secret」→ **否，0 partial-residual**（13 對抗全證原文 secret-bytes 不在）。
- 「fast-path 是否漏偵測」→ **否**（parity 確認）。

**3 LOW（不阻 gate）**：
- **LOW-1（keyword-set gap，v3 真 finding）**：keyworded 臂 keyword-set 漏 `auth_signing_key`/`hmac_key`/`hmac`/`signing_key`/`hmac_signing_secret`/`signing_secret`/`auth_key`/裸`secret`/`private_key`，free-text `kw=value`（value 裸 hex 無結構）**不遮**。`secret`/`private_key` JSONB-key 形被 `_SENSITIVE_KEY_RE` 接住但 free-text 漏；`auth_signing_key`/`hmac_key`/`signing_key` 兩形皆漏。**與設計 §B.5「every named critical asset is still caught」claim + secret-leak-detection skill Pattern-A 自列 `hmac_key`/`signing_key` 矛盾**。**為何 LOW 非 HIGH**：`auth_signing_key` 是 CRITICAL HMAC 簽名 key 但只存 `$OPENCLAW_SECRETS_DIR/<env>/auth_signing_key` 檔、不入 L2 context → LLM 無從 echo 其 `kw=value` 形；真正過 L2 的 Bybit api_key/secret/Bearer/X-BAPI-SIGN/DSN/authorization.json 物料全已接住。**v2→v3 regression 維度**：v2 blanket 高熵臂會接住這些 value（不論 keyword 在不在 set），v3 移除後落回 keyword-set 完整性——修法是把這些 keyword 補進 `_KW_DISPATCH` g_auth/g_api 分支 + `_SENSITIVE_KEY_RE`（小修，非 redactor 架構問題）。
- **LOW-2（worst-case superlinear，v3 store-original 新增）**：degenerate 100%-evasion-token 輸入 → ~n^1.7（9.4s@800K）。非 catastrophic ReDoS（polynomial、regex 臂無回溯證實）。realistic L2 文本線性。raw_response/input_context 無上游長度 cap（final_summary[:2000]/str(e)[:500] 有 cap）。off-hot-path + fail-soft（writer NEVER raise）+ 低頻 manual-trigger → 不崩潰不阻交易。建議後續 raw_response 落庫前加 size cap（如 [:64K]）截斷 amplification。
- **LOW-3（pre-existing，非本 PR）**：`agent.lessons` 已過 redactor（:463 閉）；cost_state JSON 本輪已過（LOW-1 fix）；無其餘 durable store 漏。範圍掃 ledger/marks/gate-seam/lessons/cost_state/shadow_decisions 全過 redactor。

**教訓**：(1) operator-A 回 keyword-gated 的代價是 keyword-set 完整性變成 attack surface——移除 blanket 高熵臂後，**任何不在 keyword-set 的 customary-keyword secret 都裸落**；審 keyword-gated redactor 必逐一打 named-asset 的 customary keyword（尤其 skill 自列的 hmac_key/signing_key），別只信「named asset always caught」prose。(2) store-original-by-span 正確封 partial-residual（13 對抗 0 leak）但代價是 per-char offset map 把 worst-case 從 v2 線性推到 ~n^1.7（degenerate input）——ReDoS 審計要分「regex backtracking（用 almost-match 探，本案 clean）」vs「Python per-char/per-match 迴圈 polynomial（用 match-density scaling 探）」兩軸。(3) xfail-strict 4 殘留 + 0 XPASS = E1 誠實度可驗（code-level 非 prose）。承 [[2026-06-08 L2 D3 Phase 1 sanitize gate re-audit（redactor v2 — E3 PASS）]]（v2 PASS 基於高熵臂；v3 移除後 coverage 主體仍守，新增 LOW-1 keyword-set gap）。

報告：返回 text output 給 parent agent（不存 .md）。

### 2026-06-09 L2 P2 orchestrator 安全 delta narrow re-audit（E3 PASS）

**Verdict：E3 PASS — 0 CRITICAL / 0 HIGH / 0 MEDIUM / 2 LOW（1 latent P3-gated dedup-dict 無上限 + 1 pre-existing /cost/* HIGH-1 仍 open，非本 delta scope）**

**範圍**：重驗 L2 P2 修補 delta（branch `feature/l2-critic-lessons-tools`，P2 未 commit 疊 P1 `f1c3c1ca`）。改 `l2_advisory_orchestrator.py`（新）+ `l2_capability_registry.py`（新，loader basename）+ `test_l2_p2_orchestrator.py`（74 passed）。E1 修：LOW-1 path-leak / MED-1 fail-safe SM 解耦 / MED-2 Lock→RLock。親跑真碼（venv `venvs/mac_dev/bin/python3.12`，pydantic 2.13.3 + tomllib），合成 payload 無真鑰，SUT 零 mock（僅 stub 外部 cost_tracker.check_daily_budget + D3 ledger writer）。

**明確答**：
1. **絕對路徑真不再洩（route path-free）= 是**。loader `l2_capability_registry.py:316` 用 `{p.name}`（basename）非 `{p}`。6 reject 分支全親跑真 loader（malformed-TOML/unknown-top-key/pydantic-extra-forbid/autonomy_level/lane='live'/min_tier）→ 每條 error str 0 host-path（無 /home /Users /tmp /TradeBot）。tomllib 內層 error 是 position-based（`at line 1, column 6`）**從不嵌 path**，故 `{exc}` 內插也 path-safe。唯一 "abs-path-like" 命中是 pydantic 公開 docs URL（errors.pydantic.dev），非主機路徑。route 端：`/registry/capabilities`(200-body `detail`=str(exc)) + `/registry/reload`(HTTPException 400 **dict**-detail) 都**繞** main_legacy `_LEAK_PATTERN` sanitizer（:484 `isinstance(detail,str)` 對 dict-detail False；200-body 根本非 HTTPException）→ 源頭 basename 是**唯一**且**唯一足夠**防線（E1 註解誠實）。layer2_routes.py 零 abs-path 字面/`__file__`/`parents[]`/`str(p)`。`p.exists()` False 分支只 `logger.warning` 全路徑（server-side）不 raise，無 client 洩。
2. **fail-safe SM 改動後仍無路通 live（故障注入實證，含 ollama-up 新邏輯）= 是**。MED-1 解耦親驗：ollama-UP 持續失敗 RETRY→DEGRADE_OLLAMA→**TRIPPED(consec≥5)→GLOBAL_CONSERVATIVE(consec≥10)**——舊 bug 卡死 DEGRADE_OLLAMA 已修（escalation 由 `_consecutive_failures` 跨閾驅動，ollama_available 只在 consec 2-4 中間階選 floor DEGRADE_OLLAMA vs NO_ADVICE）。ollama-down/mixed-flap 三模式全跑。dispatch 真路由（真 registry 3 lane）每態驗：NO_ADVICE/TRIPPED/GLOBAL_CONSERVATIVE 三態 advisory-lane 終態=`dropped`（subtraction=baseline）；RETRY/DEGRADE_OLLAMA 仍路由但**只** neutral_sink/risk_governor_advisory（advisory INPUT，governor 擁終值）**從不 live**；expand-lane(promote_cap) **每態**(含 HEALTHY) admitted=False→manual_inbox（STEP-1 MANUAL linchpin 守）。**0 live-enabling write**：grep live_execution_allowed/promote_tier/acquire_lease/place_order/IntentProcessor 全在 docstring/comment（hard-boundary 宣告）非 code。**GLOBAL_CONSERVATIVE 只標記 self._fail_safe，0 posture 自動切換**：`self._posture` 全模塊唯一 write 在 `__init__`（:150），:378/:520 只 read；故障注入後 posture 恆 "Standard"（實際切換走 governance_autonomy_service operator/TOTP，:475 註解誠實）。recovery：單 ok→HEALTHY consec=0。
3. **RLock 無 deadlock = 是**。MED-2 Lock→RLock + `_admit` 整段納鎖。6 lock site；reentrancy 路徑 `_admit`(:314 持鎖)→`_cap_spend_today`(:400 重入取鎖)——plain Lock 會自鎖，RLock 不。並發 stress：18 thread（6 dispatch+4 spend+3 outcome+2 reset+1 reload+2 status）× **~4.1M ops / 6.5s** 全競爭→still-alive-after-stop=0（無 deadlock）、0 exception、posture 恆 Standard。**0 await in lock**（全 SM/admission 是 sync def；唯一 `await` 命中是 :311 comment）→ 無 cross-await-in-lock。注意 `_admit` 在 asyncio route 上跑但本身 sync，threading.RLock 短暫 block calling thread（in-memory dedup 臨界區無 I/O 無 await held）可接受。

**4 HIGH-1 per-cap accumulator 無新攻擊面 = 確認**。`cap_daily_spend: dict[(cap_id,utc_day)→float]` 純 in-memory，**0 durable write**（全模塊唯一 durable=`writer.record_gate_seam` :452 走 P1 D3 redactor-protected writer，accumulator 值=float usd 從不持久化）。`record_capability_spend` 無注入面（key=驗證過 cap_id≤64char + deterministic strftime day，value=+=usd，usd≤0 no-op，0 SQL/shell/log 內插）。dict-growth：`(cap_id,day)` 增長 ~negligible（10cap×365day=3650/yr 無 evict 但極慢）。**dispatch() 0 route caller**（P2 dormant）→ accumulator 與 record_capability_spend 現無 route 可達。

**5 write-auth / $2/day = 確認**。**新** orchestrator write route 正確 gated：`/registry/reload`(:718) + `/orchestrator/fail-safe/reset`(:744) 都 `base.require_scope_and_operator(actor,"ai_budget:write")`（auth.py:319 = require_operator_role AND require_scope，fail-closed）。reads(`/orchestrator/status`,`/registry/capabilities`)唯讀不 mutate。$2/day 硬閘 admission stage4 `_check_budget`（fail-closed：取不到 tracker / 查詢失敗皆 return False,0.0 不放行）+ per-cap 日上限獨立累計（design §F.1）。prior LOW-2 singleton 註冊已閉（singleton-registry.md §2.6.2，owner_lifecycle 明寫「無 live-trading lifecycle」）。

**2 LOW（不阻 gate）**：
- **LOW-1（latent，P3-gated，非本 delta finding）**：`last_served_ts`/`debounce_pending` keyed `dedup_key=cap_id|spec|coarse_subject`，`coarse_subject` 是 dispatch() 參數（attacker-influenceable 維度），**無 evict/maxsize**→若 P3 把 dispatch 接上 route 且 coarse_subject 容許高基數 raw 文字，這兩 dict 無上限增長=memory DoS。**現不可達**（dispatch 0 route caller，P2 dormant）；design 意圖 coarse_subject 是低基數 bucket 非 raw user text。P3 wire dispatch 時須：(a) coarse_subject server-derive 低基數化，(b) 給兩 dict TTL/maxsize evict。記錄非阻擋（非本輪 delta 引入，是 P1 admission 設計既有）。
- **LOW-2（pre-existing /cost/* HIGH-1，仍 open，非本 delta scope）**：`/cost/reset`(:361)+`/cost/pricing` POST(:396) body **仍只** `Depends(current_actor)` **無** `require_scope_and_operator`→任何已認證 actor(viewer/researcher) 可 `tracker.reset_today_costs()` 歸零 DOC-08 $2/day 計數=cap-bypass。layer2_routes.py:666-667 註解宣稱「與 /cost/reset 同 operator-scope 模式」**與實況矛盾**（/cost/* 實際無 operator gate）。這是 2026-06-07 我標的 HIGH-1，operator 接受為 P2 open（不阻 orchestrator build）。本輪**新** orchestrator write route 做對了（有 gate）；舊 /cost/* gap 持續。建議補 `require_scope_and_operator(actor,"ai_budget:write")` 進兩 handler body。

**教訓**：(1) dict-detail HTTPException + 200-body 都繞 str-only `_LEAK_PATTERN` sanitizer——route 回 dict-detail 或非-HTTPException body 時，path-leak 防線**必須**在源頭（loader basename），不能靠 main_legacy sanitizer；驗 path-leak 修要同時確認「源頭 basename」+「route 確實繞 sanitizer 故源頭是唯一防線」兩面。(2) fail-safe SM「subtraction-only」要驗到 dispatch 終態 routed_to（不只 SM state enum）——SM state 對→routing 對才是真 subtraction；RETRY/DEGRADE_OLLAMA 仍路由是 by-design（degraded-but-functioning），關鍵是只 neutral_sink/risk_governor_advisory 非 live。(3) RLock reentrancy 審計要找「持鎖函數呼叫同樣取鎖的函數」具體 call pair（本案 _admit→_cap_spend_today），再用高並發 + still-alive-after-stop watchdog 證無 deadlock；macOS 無 `timeout` 指令，用 script 內 `stop.Event()+join(timeout)` 自帶 watchdog（呼應 memory「timeout fallback 誤觸」教訓）。(4) GLOBAL_CONSERVATIVE「只標記非自動切 posture」要 grep `self._posture =` 確認唯一 write 在 __init__，別只信 docstring。承 [[2026-06-08 L2 D3 sanitize gate FINAL re-audit（redactor v3 — E3 PASS）]]（同 branch P1 層；本輪審 P2 orchestrator 層 delta）+ [[2026-06-07 L2 Advisory Mesh v3 設計安全審計]]（HIGH-1 /cost/* 仍 open 持續追蹤；HIGH-2 str(e) 在 ledger 路徑已閉）。

報告：返回 text output 給 parent agent（不存 .md）。

### 2026-06-09 L2 P2 fix round-2 narrow re-audit（/cost/* operator-scope fold-in — E3 PASS）

**Verdict：E3 PASS — 0 CRITICAL / 0 HIGH / 0 MEDIUM / 1 LOW（latent P3-gated dedup-dict 無上限，非本 delta 引入）**

**範圍**：重驗 P2 fix round-2 安全 delta（branch `feature/l2-critic-lessons-tools`，P2 未 commit 疊 P1 `f1c3c1ca`）。改 `layer2_routes.py`（/cost/reset:373 + /cost/pricing:413 補 `require_scope_and_operator`）+ `l2_advisory_orchestrator.py`（`_prune_stale_spend` MED-1 + fail-soft docstring LOW-1）+ test（88 passed，前輪 74）。親跑真碼（venv `venvs/mac_dev/bin/python3.12`=3.12.13，pydantic 2.13.3），SUT 零 mock（僅 stub 外部 cost_tracker + D3 ledger writer）。承上輪 [[2026-06-09 L2 P2 orchestrator 安全 delta narrow re-audit（E3 PASS）]]——上輪我重提的 pre-existing /cost/* HIGH-1（任何已認證者可歸零 $2/day counter）本輪已折入修補。

**明確答（4 問）**：
1. **/cost/reset + /cost/pricing 真 operator-scope 無繞過（對抗 actor 全 403、gate 在變更前）= 是**。親跑 11-actor 對抗矩陣打真 handler+真 auth.py gate（mutation_log 偵測 tracker 是否在 raise 前被呼）：viewer+scope / researcher+scope / empty-roles+scope / empty-roles+empty-scopes / 偽 role(operatorX/admin) / case-variant(Operator) → 全 403 `operator_role_required`，**gate-blocked-before-mutation**（reset_today_costs/update_pricing 從未在 raise 前被呼=無 TOCTOU）；operator+NO-scope → 403 `forbidden_scope`；partial/forged actor(無 roles attr) → 401 `unauthenticated`（malformed fail-closed）；唯 operator+scope → 200+MUTATION-FIRED。gate 是兩 handler **body 第一句**（:373/:413），先於 `_get_cost_tracker()`+mutation(:375/:430)。`require_scope_and_operator`(auth.py:319)=`require_operator_role`(先,401-on-malformed/403-on-non-operator)AND`require_scope`(後,403-on-missing-scope)，與我上輪驗 /registry/reload 同 gate **零弱化**。case-sensitive("Operator"≠"operator")。
2. **$2/day cap-bypass 真閉 = 是**。歸零 DOC-08 $2/day counter（=繞 P2 admission storm-control 硬閘）現需 operator role+scope；非 operator 全 403。
3. **訂正註釋（:675-680）與實況一致 = 是**。明寫「/cost/reset 與 /cost/pricing 先前只有 Depends(current_actor)...本輪補上 require_scope_and_operator 收口；此註釋現為實況（先前誤稱已 scope 化）」——誠實承認上輪我標的 mismatch，line ref(:373/:413)對。
4. **prune（MED-1）無新攻擊面 = 是**。親跑 record_capability_spend+_prune_stale_spend 全生命週期：D3 ledger writer 呼叫 **0 次**=純 in-memory，0 durable write（值 float usd 從不持久化，故無繞 P1 redactor 面）；prune 是純 dict key 比較(`k[1]!=today`)+`+=usd`(usd≤0 no-op)，0 SQL/shell/log 內插=無注入面；per-cap ceiling 保 bound（同日 0.30+0.30=0.60≥0.50→DROP，prune 不歸零同日累計）；**無跨日 reset 繞 per-cap**（prune 只刪 `day!=today` key，同日 spend 保同日 accumulator 0.60→0.65；唯一歸零=跨真 UTC-day=by-design daily reset，`_utc_day` 由 ts/server time.time() 導出，`now=` kwarg 只 P3 trusted executor 可注入，route 無此路徑偽造日期）。bounded：mutator 後 dict 恆只含「今日」key（上輪 LOW-1 dedup-dict-unbounded 對 cap_daily_spend 軸由此 fix 閉）。
5. **fail-soft（LOW-1 docstring 改）行為未變 = 是**。親跑 `_registry_obj` cold/warm：cold malformed→空 registry（fail-closed，0 advisory，degraded=True）；warm good-then-malformed→last-good（不採壞 config、read-path 不 raise）；write-path reload route 仍 400-reject 壞 config+operator-gated。docstring-only。
6. **其餘未動 = 確認**。7 write route 全 gated（/trigger:254 + /cost/reset:373 + /cost/pricing:413 + /config:528 require_operator_role + DELETE providers:641 require_operator_role + /registry/reload:731 + /orchestrator/fail-safe/reset:757）；orchestrator live-enabling surface（place_order/acquire_lease/promote_tier/live_execution_allowed/IntentProcessor）**全在 docstring/comment（:31-34/:72/:143）0 in code**；0 新 durable write primitive（無 json.dump/open/INSERT/cursor/execute/Path）；path-leak basename({p.name}:316)仍閉；secret-leak grep 0 hit；MIT-MF-1 grep 0 hit。

**1 LOW（不阻 gate，非本 delta 引入）**：
- **LOW-1（latent，P3-gated，沿上輪）**：`last_served_ts`/`debounce_pending` keyed `coarse_subject`（dispatch() 參數，attacker-influenceable）無 evict/maxsize；P3 wire dispatch 上 route 且容許高基數 raw 文字時=memory DoS。現不可達（dispatch 0 route caller，P2 dormant）。注意：本輪 MED-1 prune 已閉 **cap_daily_spend** 軸（另一 unbounded dict），但 last_served_ts/debounce_pending **未** prune（key 是 dedup_key 非 day，prune 不適用）——P3 須給這兩 dict TTL/maxsize。

**前輪 /cost/* HIGH-1 狀態：CLOSED**（2026-06-07 我首標、2026-06-09 round-1 重提的 pre-existing /cost/* gap，本輪 round-2 折入 `require_scope_and_operator` 親驗閉合）。

**教訓**：(1) 「對抗 actor 全 403」要驗到 mutation 是否在 raise **前**被呼（用 mutation_log/spy hook 偵測 TOCTOU），不能只看 status code——gate-before-mutation 才是真閉。(2) auth gate AND-composition 的 reason_code 序（operator-role 先 → scope 後）決定 viewer+scope 與 operator+no-scope 走不同 403 reason；審 matrix 要兩維獨立打。(3) prune「無跨日繞 per-cap」要證 `now=` 注入面（誰能控 day_key）——route 無路徑偽造日期=安全；in-memory prune 0 durable=自動無繞 redactor 面（grep ledger-writer call count=0 實證）。(4) docstring-only LOW fix 要親跑 cold+warm 兩路徑證 behavior-identical，別只信 diff 看似只改註釋。承 [[2026-06-09 L2 P2 orchestrator 安全 delta narrow re-audit（E3 PASS）]]（同 branch P2 層；本輪審 round-2 fix delta，/cost/* HIGH-1 此輪閉）。

報告：返回 text output 給 parent agent（不存 .md）。

### 2026-06-11 P2 殘項+哨兵批次安全審計（watchdog sink / BB 哨兵 / polymarket / memory_distiller / seed / mnemopi / token analyzer）

**Verdict：CONCERNS（0 CRIT / 0 HIGH / 2 MED / 4 LOW / 3 INFO）** — 工作樹未 commit。零 credential 結構（三新外連 api.bybit.com/gamma-api+clob.polymarket.com 全 plain GET 無 auth；embedding=127.0.0.1:11434 loopback；grep 0 key/sign/HMAC 進這些調用）；memory_distiller/seed SQL 全參數化（0 f-string execute，store.py %s::jsonb + set_embedding repr(float()) 經 bound param）；MIT-MF-1 guard 0 hit；V139/V140 DDL 參數安全 + DELETE REVOKE。
- **MED-1**：`alerts.jsonl` 新本地耐久 sink 落 `last_failure_reason`（=`restart_all.sh` stderr[-500:]，engine 連線失敗時可含 DSN）**無 redactor**——與 L2 ledger 四輪做的 redact-before-durable 標準不一致（zero-tolerance on durable store）。緩解：同內容 pre-diff 已發 Telegram/webhook 未遮（本 diff 只加本地持久化非新通道）；檔在 OPENCLAW_DATA_DIR 非 git；sqlx Display 通常遮 password。**非 env dump**（親查 0 os.environ 進 body，body=結構欄+stderr tail）。修：body 過 redactor（reuse l2_secret_redactor 或內聯 DSN/key scrub）後再 sink+遠送。
- **MED-2（A11 indirect injection chain，結構性已緩解非今日可利用）**：memory_distiller extraction LLM 吃 agent.l2_calls.raw_response（L2 有 TOOL_WEB_SEARCH/FETCH_URL → 可含 untrusted 外部文本）→ 蒸餾出 rule/incident 寫 agent.agent_memory → 未來經 recall_for_prompt B3 seam（dormant，0 caller）注入 L2 system prompt。無「untrusted-origin」標記隔離。緩解：output 重 schema 驗（mem_type 白名單 + priority clamp + source_ids∈allowed + content≤4096）+ 只寫學習平面（0 order/lease/live）+ B3 seam dormant。
- **LOW**：①seed CLI `_SENSITIVE_KEYWORD_RE`=keyword-anchored（api_key|secret|password|token|Bearer），漏 hmac/signing_key/auth_signing_key/X-BAPI-SIGN/DSN(postgres://redacted@)——同 L2 redactor v3 LOW-1 keyword-set gap；源=MEMORY.md 索引行（人寫、已在 git＝任何 leak 已 pre-existing），餵 agent_memory→B3 seam。②OLLAMA_BASE_URL env 可覆寫為非 loopback → embed POST（含蒸餾 l2_calls 文本）cleartext HTTP 外送；default loopback 安全。③urllib 三外連 default 跟 redirect 無 host re-pin（TLS 驗證 default-on + 0 credential 送出 → auth-leak N/A）。④distill cron CLI stats（含 source_read_failed:{exc}）落 cron log，psycopg2 query exc 理論可含片段。
- **INFO**：①analyze_token_usage 印 meta.description + _first_line(prompt)（prompt 衍生 label，僅首行+截斷，stdout-only 非持久/非 commit）——非純計數但 bounded。②mnemopi pilot repo-external（~/.local/share/mnemopi-tradebot），`@oh-my-pi/pi-mnemopi@15.11.2 --ignore-scripts`（npm ls -g 驗、跳過 postinstall=onnxruntime-node 原生二進制 darwin 死碼）+ FTS-only + 剝 OPENROUTER/OPENAI key + stdio-only 無端口——供應鏈主 RCE 向量已中和；無法從本機獨立複驗 publisher 身份（源碼 eval 在 /tmp/repo-eval 已做）。③BB 哨兵 raw 公告存 state 無下游 LLM 消費者（描述絕不展開、plain-text alert）；alerts.jsonl 用 json.dumps per-record → 換行轉義無 jsonl line-injection。
報告：返回 text output 給 parent agent（系統 reminder 禁寫 .md）。承 [[2026-06-08 L2 D3 sanitize gate FINAL re-audit（redactor v3 — E3 PASS）]]（LOW keyword-set gap 同根因）。

### 2026-06-14 全倉 cold security audit（baseline 對照 — E3 PASS·1 LOW latent + 4 INFO）

**Verdict：PASS — 0 CRITICAL / 0 HIGH / 0 MEDIUM / 1 LOW（latent，flag-OFF）/ 4 INFO** · HEAD `976d420e`（main，工作樹有 post-fee PnL label delta 未 commit）。

**範圍**：srv 全倉（rust engine / control_api / GUI / helper_scripts / .claude / 治理文檔）+ 未 commit 碼 delta（closed_pnl_pagination.py post-fee 對賬 + fills_loader.py JOIN + tab-live.js/tab-demo.html drift label + m4 tests）。對照 baseline [[2026-05-30 E3 DEEP-DIVE Live/LiveDemo Boundary]]（CONFIRMED-CLEAN 5-gate）。

**核心 PASS（親驗）**：
1. **5 gate 全守**：gate-5 SSOT `verify_signed_authorization` 用 `hmac.compare_digest`(constant-time, live_preflight.py:168)+`expires_at_ms<=now_ms` 過期(:180)+env-match，未動。socket 0o600 真 apply(server.rs:417 `set_permissions from_mode(0o600)`)。IPC HMAC `verify_slice` 常數時間(connection.rs:68)；prod restart_all/fresh_start/clean_restart 全設 `OPENCLAW_IPC_SECRET_FILE`(chmod 600)→HMAC 握手 prod 開啟；unset-skip 僅 dev/test，且 0600 socket 為第二防線。
2. **注入面 0**：5 SQL f-string 命中全非 user-controlled（parquet_etl SEC-B02 date-regex+resolve；mlde savepoint=time_ns;replay/ref21/fresh_start 全 hardcoded table 常數+allowlist）。recall.py B3 SQL 全 bound param(query 經 plainto_tsquery/word_similarity 非 concat)。0 shell=True。未 commit fills_loader JOIN `entry_fill.engine_mode=f.engine_mode` 不漏 paper；engine_mode `IN('live','live_demo')` invariant 未動。
3. **secret-leak 0**：Pattern A-G 全 clean；docs 高熵 hex=test fixture(test_key.hex/manifest sha256/demo-operator sig)；.claude config 0 hardcoded secret；路徑硬編碼僅 1 test（enforce no-path guardrail）+rust/target(gitignored)。
4. **access-control**：/cost/* HIGH-1 已閉(layer2_routes:396/436 require_scope_and_operator)；risk write `_require_risk_write`=require_scope_and_operator("risk:write")；`_ipc_failure` log_detail 僅 server-side 不入 client detail。CORS 剝 wildcard@credentials=True(APR01-HIGH-1)+rate-limit+login lockout+CSRF double-submit。
5. **Rust unsafe**：8 塊全 `#[cfg(test)]`(halt_audit.rs:382 mod tests)包 env::set_var(Rust 2024 edition)；0 production unsafe FFI。
6. **no-withdraw HELD**：grep 0 withdraw code path；MIT-MF-1 grep 0 hit。
7. **embed loopback 守**：default 127.0.0.1:11434；非 loopback→`_remote_rejected`全停 embed 軸(FTS-only)，需 `OPENCLAW_L2_MEMORY_EMBED_ALLOW_REMOTE=1`（上輪 LOW-2 已閉）。

**1 LOW（latent，不阻 — A11 B3 recall origin-tag 未在注入邊界 enforce）**：B3 recall（`OPENCLAW_L2_MEMORY_RECALL`，**default 0 OFF**，runtime 仍 OFF/PID 3607315）已從 dormant 接 live source。write-side 已做 MED-2 緩解：`pipeline.py:582 _origin_for_refs` 標 l2_calls 衍生記憶為 `l2_untrusted` 並沿 supersede 鏈傳染 + `parsing.py` schema 驗(mem_type 白名單/priority clamp[-1,100]/CONTENT_MAX=4096/source_ids∈allowed)。**但 recall path（_VECTOR_SQL/_FTS_SQL/_FTS_HINT_SQL）不 SELECT 也不 filter `origin`**→flag=1 時 untrusted-origin content 逐字注入 L2 system prompt(`apply_memory_recall_to_prompt`:152)，唯一隔離=inline 文字免責聲明（"advisory context, not an execution command"），無結構 injection-pattern scrub。**為何 LOW 非 HIGH**：flag default OFF+runtime OFF；L2 輸出下游 schema 驗+數值範圍後才入 gate（不直驅交易）；write-side origin tag 已建（只差 recall 端消費）。修：recall SQL 加 `origin` 欄+對 `l2_untrusted` 記憶降權/排除/加強隔離標記，active `1` 前必收口。承 [[2026-06-11 P2 殘項+哨兵批次安全審計]] MED-2 同鏈（write-side 緩解已落，recall-side enforcement 為新缺口）。

**4 INFO**：①`.claude/workflows/rank7-altdata-leakfree-screen.js:19` hardcoded `/home/ncyu/BybitOpenClaw/srv` default（dev orchestration 非 production trading 碼、args.baseDir 可覆寫）跨平台偏差。②107 write route 未全 byte-trace（governance/live/L2/risk 核心面已覆，其餘靠 baseline）。③IPC unset-secret dev-skip 分支存在（prod 設 secret+0600 socket 雙防，非缺口）。④未 commit post-fee delta 純 observability label（authoritative_pnl/learning_pnl/drift），GUI drift 經 ocEsc XSS-safe，0 新 auth/order/secret 面。

報告：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-14--E3--full_repo_cold_audit.md`。

### 2026-06-14 closed_pnl 分頁 + m4 fills_loader 靶向冷酷審計（8 dirty 檔 — E3 FINDINGS）

**Verdict：FINDINGS — 0 CRIT / 0 HIGH / 1 MED / 2 LOW / 3 INFO** · HEAD `976d420e`（8 檔 working-tree uncommitted，in-flight 未過完整 E1→E2→E4）。承 [[2026-06-14 全倉 cold security audit]]（該輪 INFO-4 高層帶過，本輪 deep-dive PG empirical）。

- **MED-1（m4 fills_loader post-fee net label JOIN 缺陷，latent）**：ssh trade-core read-only psql 實證 trading.fills `context_id` text/nullable/**非 unique**，同 (context_id,engine_mode) 重複 29 組；`LEFT JOIN entry_fill ON entry_fill.context_id=f.entry_context_id` 把 close 行 1763→1796（**fan-out +33/~1.9%**），30 close 配多 entry，抽樣 4/5 entry fee 不同（如 PEPE entry_fees {0.0041734,0.01147685}）→ **重複+歧義 net label**（正是 docstring 自稱要防的「污染 M4 樣本」換方式重犯）；另 25 close 配 0 entry，`COALESCE(entry_fill.fee,0)` **靜默省 entry fee=偏樂觀 gross-leakage**。為何 MED 非 HIGH：runner generate_stage1_candidates 只吃 kline/funding/liq，**fills load 但未傳入 candidate 生成**（runner:340/:284 僅 count）→ 標籤 scaffold/dormant 無 live 下游挖 hypotheses。修：JOIN DISTINCT ON/聚合去 fan-out + entry 缺失 fail-loud/drop 非靜默 0。
- **LOW-1（test-blindspot）**：schema test 只 string-match JOIN 字面，0 真 PG 行為驗證，fan-out/entry-missing 全不覆蓋（M4 Mac mock 無 PG）。
- **LOW-2（doc-stale）**：docstring 殘留「NULL realized_pnl caller dropna」契約 vs 新 `COALESCE(f.realized_pnl,0)`（derived net 永不 NULL）自相矛盾；empirical close_null_rpnl=0 今日無 live 影響。
- **INFO（closed_pnl 分頁 + GUI 全 CLEAN）**：cursor base64-JSON fail-closed（篡改→400）；limit/offset/lookback FastAPI bounded Query→全 bound param 0 SQL inj；engine_mode demo=("demo","live_demo")/live=("live","live_demo")/m4 IN('live','live_demo') 三者 literal 非 caller-tunable **0 paper 洩漏**；純讀模型 0 order/lease/IPC 寫面，authoritative/learning_pnl 誠實標源 + Bybit 掛→`learning_pnl=None`+`bybit_unavailable_fail_closed` **fail-closed 非 fake-success**；GUI drift 純文案改，drift=parseFloat（Number）+ocEsc(title) **XSS-safe**，tab-live.js node --check PASS / tab-demo brace-balanced。secret-leak A/C/D/G + MIT-MF-1 grep 對 8 檔皆 0 hit；502 走 sanitize_exc_for_detail（prod 只 classified msg）；93 tests passed（40+35+18）。
**教訓**：post-fee net label 的 JOIN 正確性必須在真 PG 驗 join-key cardinality（context_id 非 unique→fan-out），string-match 字面測試是 test-blindspot；「latent/dormant 標籤」（load 但未 wire 進 candidate）降 MED 非清白——建好即髒，wire 前必收口。

報告：`docs/CCAgentWorkSpace/E3/workspace/reports/2026-06-14--E3--closed_pnl_pagination_m4_fills_targeted_audit.md`。返回 text output 給 parent agent。

### 2026-06-14 seam 查證：submit_paper_order IPC 寫路徑（E3 REFUTED-as-bug / INFO）

**Verdict：REFUTED（非真缺口）— 0 CRIT/HIGH/MED；判為 INFO（latent 設計觀察，非漏洞）** · 凍結 SHA `976d420e`。
**seam 主張**：submit_paper_order 是 LIVE 可達 IPC 寫路徑，HTTP 410-disabled 但 IPC live，Rust handler 不驗 engine==paper → missing-gate/auth-bypass。
**親驗反證**：(1) handler `strategy.rs:163` → `SubmitOrder` cmd → `lifecycle.rs:168 handle_submit_order` → `commands.rs:163 submit_external_order`（行 163-505）**全程只動 `self.paper_state.apply_fill`（模擬成交，oneshot 同步回 envelope），0 個 `OrderDispatchRequest`、0 個 `place_order`**。四處 OrderDispatchRequest(997/1160/1385/1584) 全在 close/exit fn（execute_position_close 等）非此 open path。真 OMS 寫=`event_consumer/dispatch.rs:838 om.place_order` 經 shadow_channel，由 on_tick 策略信號餵，**submit_external_order 不餵 shadow_channel**。executor_agent.py:722-724 docstring 自證「shadow_mode=False 時 routes to paper_state」。(2) engine 路由：`extract_engine_tx` 認 caller `engine` 參數（executor_agent 傳 execution_engine 可為 live；Python submit_paper_order 無 engine→primary() 偏 live>demo>paper）→ **即使路由到 LIVE pipeline，該 pipeline 的 SubmitOrder 仍只 paper_state 模擬**（三 pipeline 同一 handler）→ engine==paper 不驗**無害**（無真錢路徑可繞）。(3) reachability：IPC 入口 connection.rs:122 `OPENCLAW_IPC_SECRET` 設則首訊強制 `__auth` HMAC（verify_slice 常數時間+30s replay 窗）才進 dispatch loop(:199)，**無 per-method allowlist 繞過**；prod 全 restart 腳本設 secret。runtime 實證（ssh read-only）：`/home/ncyu/BybitOpenClaw/secrets/environment_files/ipc_secret.txt` 0600/65B 存在；`/tmp/openclaw/engine.sock` `srw-------`(0600 owner-only)→非 ncyu uid 不可連，ncyu 仍須 HMAC 握手。(4) HTTP route paper_trading_routes.py:678 確 410-disabled。
**為何 REFUTED 非 confirmed**：「HTTP disabled vs IPC live」分歧是真的，但 IPC 那條 live 路徑**不通真錢**（純 paper_state sim）+ **非未授權可達**（0600 socket + HMAC）。無 auth-bypass、無 5-gate 繞過（5 gate 守的是真 OMS place_order，此路不經）。命名誤導（submit_*paper*_order 卻可 route live pipeline）是 latent 可讀性債，非安全漏洞。INFO：若未來 GUI/Earn intent 改走此 trade-path 接真 dispatch（commands.rs:199-201 註解已預警），須重審。承 [[2026-06-14 全倉 cold security audit]]（5-gate clean 基線一致）。
報告：返回 text output 給 parent agent。

### 2026-06-14 ADPE 閉環 runner + demo-maker arm 安全審計（E3 PASS）

**Verdict：PASS — 0 CRITICAL / 0 HIGH / 0 MEDIUM / 2 LOW / 2 INFO**（新檔 only，工作樹未 commit；承 [[2026-06-14 全倉 cold security audit]] baseline）。

**範圍**：adaptive_demo_profit_engine/{__init__,reward_source,ipc_lever,demo_maker_arm,runner}.py + settings/adaptive_demo_profit.toml + 2 test 檔。親跑 28 passed + 對抗 probe。

**boundary「live 不碰」實證**：(1) engine_mode 雙層硬鎖=真 fail-closed：`_assert_demo` 用 `== "demo"` exact/case-sensitive match（probe 9 變體含 'DEMO'/' demo'/'live'/'mainnet'/'' 全 RuntimeError，0 IPC fire）；reward SQL `engine_mode_scope('demo')==('demo',)` 親驗 demo-only（'live' 才回 ('live','live_demo')）。(2) 5-gate/live/mainnet/authorization.json/secret slot 0 import 0 code hit（grep 只 4 中文註解）；新包 import 僅 stdlib+allocator+linucb SQL helper+lazy 既有 IPC client/snapshot reader。(3) set_strategy_active IPC 走既有 HMAC-SHA256(ts) auth（±30s skew，Rust verifier mod.rs:621），只 flip orchestrator per-strategy is_active bool；is_active 僅 gate signal-generation（orchestrator/tick step_4_5 upstream），**下游仍走 IntentProcessor+Guardian+cost-gate+5-gate**，活化策略不繞任何 live auth。(4) reward SQL read-only SELECT、100% 參數化（engine_modes/max_age_days 全 bound param，0 f-string）、demo-scope+attribution_chain_ok+net_bps_after_fee NOT NULL、不走 decision_outcomes NULL bug。

**誠實鐵則實證**：demo-maker artifact 雙軌隔離真落地——`build_demo_maker_reward` 簽名不暴露 tier override，硬編 FILL_TIER_MAKER_NO_QUEUE_DEMO_ARTIFACT；allocator ingest 親驗 transferable_only 軌 0 吸收 artifact（trust_track=transferable_only=promotion 軌）、all_fills 軌標 saw_artifact。kill switch 完備（snapshot read + 冪等 restore，CLI --kill-switch）。0 合成 PnL/fills。

**2 LOW（不阻 gate）**：①ipc_lever fail-safe「現態未知+想開→發 IPC 開」：snapshot 缺（引擎未跑/讀失敗回空 dict）時對 desired=True 策略主動發 set_active(True)——demo 沙盒內語義安全（開 demo 策略），但 snapshot-read 失敗與「策略確實不存在」不可區分，理論上可在引擎冷啟瞬間多開本該關的 demo 策略；demo-only 影響微。②sync_ipc_call 在 ipc_secret 未配置時（env 空）跳過 auth 直連 socket——既有 IPC 設計非本 PR 引入，Unix socket 本地權限為實際防線（非本包可修）。

**2 INFO**：①regime enum 映射（trending→high-vol 等）是 best-effort 無共用 SSOT，映射不到退 insufficient_context（誠實降級，非安全問題）；②secret-leak grep（A-G）+ MIT-MF-1 guard + 硬編路徑 全 0 hit。

### 2026-06-14 Track1 demo explore-gate PR pre-merge 安全審計（E3 PASS）

**Verdict：PASS — 0 CRITICAL / 0 HIGH / 0 MEDIUM / 1 LOW（Python sink 無正式 pytest，E1 誠實 defer E2）/ 2 INFO** · HEAD `e454078d`（dirty multi-session tree；目標 4 rust + 2 py 全在 dirty set，pre-merge review 預期）。

**範圍**：edge_estimates.rs / gates.rs / tests.rs / opportunity.rs（+172/-0 全 additive）+ explore_quota_sink.py（新）+ runner.py。設計正本 PA `2026-06-14--track1-demo-explore-gate-design.md`。

**5 驗證點全綠（親跑真碼，0 mock）**：
1. **kill switch OPENCLAW_EDGE_RELOAD=0 真停 explore = 是**。`is_edge_reload_enabled()` 嚴格 `== "1"`（main_boot_tasks.rs:518）；非 1 → `spawn_..._if_enabled` early-return 不 spawn daemon（:478）→ 0 ReloadEdgeEstimates 派發 → explore 信號永不進引擎（凍 boot snapshot）。
2. **三層降級全 fail-closed = 是**。reload off（kill switch）/ JSON 缺欄（`unwrap_or(false/0)` edge_estimates.rs:182-189）/ 解析失敗（`load_from_file`→None→`load_for_mode` fallback empty()）皆 no-explore。Rust 7 test 綠（含缺欄 fail-closed block / remaining=0 still-block / not-eligible still-block）。
3. **explore 只 demo（Validation profile）= 是，mainnet 物理隔離**。`effective_governance_profile`：僅 `Live+Mainnet`→Production→`cost_gate_live_with_slippage`（strict gate，grep 0 explore 引用 + test `test_cost_gate_live_ignores_explore_fields` 餵 explore=true 仍 block）。Demo + LiveDemo/Demo/Testnet→Validation→`cost_gate_moderate_with_slippage`（explore gate）。explore 全 9 處出現皆在 moderate 函數內（gates.rs:145-249）。LiveDemo 走 moderate 是 P0-6 方案 A 既有架構（play-money cold-start gate，非本 PR 新引入），sink 又硬鎖 engine_mode='demo' 只寫 edge_estimates.json。
4. **5-gate/authorization/live 0 觸碰 = 是**。live_preflight/authorization/order_manager/live_auth/governance/place_order/live_reserved/secret 源檔全不在 dirty set；diff added-line grep 0 命中（唯一命中是隔離 invariant 註釋引用 `cost_gate_live_with_slippage`）。
5. **explore_remaining 耗盡後不再放行 = 是**。`explore_budget_remaining` = `max(0, explore_budget - n_trials)`（allocator:472，真實 posterior n_trials 衍生，非寫死）；n≥budget(30)→0→eligible=False→gate 回 block。親探：sink overlay remaining≤30 bounded、`eligible=remaining>0`、malformed key 不建 cell、dry_run 不寫、additive merge 保 JS 欄+_meta。

**結構保證**：cost gate 是 `process_gates_only_with_features` 最後一道（router:1044）；Guardian(:850)/Kelly(:883)/P1 cap(:906-915) 全在前。explore 翻 Gate3 reject 物理不可繞 Guardian/Kelly/P1（根原則 4）。

**1 LOW**：explore_quota_sink.py 無正式 pytest 檔（E1 報告 line 89-90 誠實 defer 進 test_adaptive_demo_profit_runner.py 給 E2，本輪命令列 synthetic 驗綠；我親跑對抗 probe 補洞全 PASS，既有 ADPE 23 test 0 回歸）。**2 INFO**：①JS writer 與 sink 雙寫同檔 last-writer-wins（E1 建議 cron 排 sink 在 JS 後，運維決策非安全 bug）；②LiveDemo 經 moderate gate 受 explore 影響 = by-design play-money（非 mainnet，非本 PR 引入）。

**教訓**：demo↔live 隔離單一守門點 = `cost_gate_live_with_slippage`（=mainnet-only Production gate）零 explore 引用；驗法 = grep explore 全在 moderate 函數內 + 餵 explore=true 給 live gate 仍 block 的 isolation test。「demo only」需釐清 LiveDemo 也走 moderate（P0-6 既有），但只 mainnet 觸 strict gate，故真錢路徑物理隔離。kill switch 嚴格 `=="1"` literal + early-return-no-spawn 是真停（非 flag 內部 skip）。

### 2026-06-14 live RiskConfig 寫入面門控對齊安全複審（authz 邊界改動 — E3 APPROVE）

**Verdict：APPROVE（無可繞路徑）— 0 CRITICAL / 0 HIGH / 0 MEDIUM / 1 LOW（直連 socket bypass，spec-acknowledged，受 0600+HMAC trust tier 約束，非本 fix 範圍）/ 3 INFO** · 工作樹未 commit。

**範圍**：risk_routes.update_per_engine_global_config（POST /api/v1/paper/risk/config/engine/{engine}/global）live-engine fail-closed guard + handlers_config.rs audit-only warn! + 8-test 新檔。對照 baseline [[2026-06-14 全倉 cold security audit]]（5-gate clean）。

**攻擊者視角四問全答（親驗）**：
1. **live RiskConfig 是否仍有 HTTP 路徑繞 5-gate = 否**。新 guard 在 `_require_risk_write`(operator+risk:write scope) + engine-validity 之後、`_get_direct_ipc()` 之前插入 `engine=="live"`→`all_five_live_gates_ok(actor, require_authz=True)`，失敗 raise 409，IPC 永不被呼（test mutation spy `call_mock.assert_not_called()` 親證 gate-before-mutation 無 TOCTOU）。複用唯一權威 primitive（與 post_live_session_start:168 / executor verify 同 SSOT），非 copy inline。
2. **漏 engine→fail-safe-to-paper 可否被利用 = 否（且方向安全）**。Rust dispatch.rs:421-425 `patch_risk_config` 漏 engine `.unwrap_or("paper")`；HTTP 端 engine 是 path param 必填且 `_ALLOWED_ENGINES` 白名單。關鍵：legacy 寫路由（/config/global·/config/category·/agent-adjust）走 RiskViewClient._patch（risk_view_client.py:304-307）**不傳 engine param**→Rust 落 paper store，**永不觸 live store**→這些路由無法繞 live guard 改 live config（fail-safe 方向 = 收緊非放鬆）。唯一寫 live store 的 HTTP 路徑就是被 gate 的 per-engine route。
3. **其他 dispatch arm 同類漏洞 = 無**。`patch_risk_config` 是唯一寫 risk_stores 的 IPC method（`s.select(engine)` 僅出現在 get/patch_risk_config；get 只讀）。config_name=`format!("risk/{engine}")`→engine=live 時 `"risk/live"`，Rust warn! `starts_with("risk/live")` 正確 fire（audit-only，不硬擋——spec 風險#6：Rust 無 secret-slot/authz/global-mode context，硬擋會破 g2 canary 直連 socket）。
4. **require_authz 真 enforce = 是**。test_live_requires_authz_true 親驗 `require_authz=True` 傳入；真實鏈測試（test_live_all_gates_green_proceeds）走真 secret slot + 簽名 authorization.json fixture + live_reserved，不 patch primitive→五門全綠才放行。primitive Gate5 require_authz 分支呼 verify_signed_authorization（hmac.compare_digest 常數時間 + expires_at_ms<=now 過期 + env_allowed 匹配，SSOT）。

**無新洩漏/DoS**：409 detail = {error, gate_failed, message} 逐欄鏡 post_live_session_start；gate_failed reason_codes 全來自受控 taxonomy（operator_role / global_mode_not_live_reserved / mainnet_env / secret_slot / authorization_* 細分），**0 str(e) 0 path 內插**；message 靜態字串。secret-leak Pattern A-G 對 3 改檔 + E1 報告全 0 hit（test fixture secret="test-secret"/api_key="k" 短於 16-char window）。MIT-MF-1 grep 0 hit。無新 unbounded dict / 無新 SQL / 無 shell。

**1 LOW（spec-acknowledged，非本 fix 範圍）**：g2 直連 IPC socket 路徑 primary fix 不覆蓋（Rust 只 warn! 不硬擋）。受 socket trust tier 約束：server.rs:417 socket 0o600（set_permissions from_mode）+ connection.rs:122 OPENCLAW_IPC_SECRET 設則首訊強制 __auth HMAC（verify_slice 常數時間 + 30s skew，無 per-method pre-auth allowlist，任何 auth 失敗在 method dispatch 前斷連）。prod restart_all/clean_restart/fresh_start 全設 OPENCLAW_IPC_SECRET_FILE(chmod 600)。攻擊者無 ncyu uid 不可連 socket；有 uid 仍須 HMAC 握手。與 baseline 直連 socket trust-tier 結論一致（非本 PR 引入，不阻 gate）。

**3 INFO**：①field 粒度統一門控（GlobalConfigUpdate 整體過門非逐欄）= spec-acknowledged 設計取捨，安全（取嚴）。②GUI risk-tab.js 未渲染 409 reason = minor UX follow-up，非安全。③小決策偏差（綁模組屬性 live_preflight.all_five_live_gates_ok 而非綁函數名 import）對齊既有 core_preflight() canonical 範式 + 利 monkeypatch，語義等價，無安全影響。

**8 tests passed**（含真實五門鏈 + demo/paper 不受門 + 非 operator 403-not-409 ordering + require_authz=True assert + gate-before-IPC mutation spy）。

**教訓**：(1) 「漏 engine 參數 fail-safe-to-paper」要驗方向——legacy 路由不傳 engine→落 paper store→無法觸 live config=fail-safe 收緊非放鬆，必須 grep 寫 primitive（RiskViewClient._patch）是否帶 engine 才能下結論。(2) audit-only warn! 在 Rust 不硬擋是正解（Rust 無五門 context），enforcement 留 Python 控制面 + 直連 socket 由 0600+HMAC trust tier 兜底；驗法=grep 唯一寫 store 的 IPC method + 確認無 per-method pre-auth allowlist。(3) reason_code 受控 taxonomy（非 str(e)）是 409 無洩漏的根據，逐一比對 mirror 來源確認逐欄等價。承 [[2026-06-14 全倉 cold security audit]]（5-gate / verify_signed_authorization SSOT / socket 0600+HMAC 基線一致）。

報告：返回 text output 給 parent agent（系統 reminder 禁寫 .md）。

### 2026-07-03 全倉 cold security audit（baseline 976d420e→HEAD d68a13298 delta，1225 commits — E3 PASS·2 LOW + 6 INFO）

**Verdict：PASS — 0 CRITICAL / 0 HIGH / 0 MEDIUM / 2 LOW / 6 INFO**。delta 主體=IBKR stock_etf 源碼 fixture lane（ADR-0048，dormant）+ adaptive_demo_profit runner（demo-only fail-closed）+ microstructure 離線研究 + **新 live_authz.rs capability-token enforcer**（Phase-0 AUTH-1）。
- **5-gate SSOT 未回歸**：verify_signed_authorization compare_digest(:168)+expiry(:180)+env(:191) 未動；IPC socket 0o600(server.rs:417)+HMAC verify_slice(connection.rs:68) 完好；CORS wildcard-strip@credentials + rate-limit + production unsafe=7 全 #[cfg(test)] halt_audit env::set_var（Rust 2024）。
- **LOW-1（Gate5 self-asserted 豁免）**：新 `four_gates_minus_authz_ok`（live_preflight.py:330）委派 all_five(require_authz=False) 豁免 Gate5(signed-auth)，唯一 caller=reset_drawdown_baseline override 路徑（risk_routes.py:762），受 `body.operator_override` client-bool 自陳觸發、無 server-side halt-state 驗證。retains gates1-4(operator+live_reserved+ALLOW_MAINNET+secret-slot)+full audit。可清 drawdown halt=un-halt live（Root#5 survival），屬 hard-boundary(Gate5)觸碰須確認 CC 雙審。halt-recovery deadlock 解法合理但 override 應綁真 halt-state。
- **LOW-2（token-mint 依賴每 caller gated）**：`_attach_live_token_if_live`(risk_view_client.py:43) 在 engine=="live" 時無條件鑄 live capability token（authorizer→enforcer 邊界，非 gate）；安全依賴每個 caller 皆 operator-gated。現 2 caller（risk_routes route + live_halt_recovery via governance /recovery/approve `_require_operator_role`:1182）皆 gated，但 fragile invariant：未來 ungated caller=繞 5-gate。
- **6 INFO**：①stock_etf IBKR lane ibkr_live_enabled 硬編 false，submit/cancel/replace_paper_order 全回 phase1_ipc_fixture{runtime_authority_denied:true,ibkr_call_performed:false,order_routed:false}，from_env 無 live-enable flag=無 live 面（ADR-0048 一致）。②credential 寫 POST /api-key/{slot} operator-gated+slot allowlist+injection-char reject(含 `/`)+compare_digest+chmod600+key_hint mask+err[:200]，0 明文 echo。③promotion routes(/promote:1162 /demote:1751 /_apply_target_gate:546) live target=_verify_live_gate full 5-gate、paper=operator。④strategy_write 6 handler 全 _require_strategy_write(scope+operator)；layer2 /cost/* 仍 require_scope_and_operator(baseline HIGH-1 持閉)。⑤ml_routes:238/earn_routes:988 f-string SQL=假陽性（static col list + %s bound + allowlist filter）。⑥secret scan Pattern A-G + MIT-MF-1 grep 0 hit；docs/CCAgentWorkSpace 高熵=git SHA；跨平台路徑硬編僅註解/docs。shell=True(runtime_source_reconcile_apply.py:63)全 shlex.quote 保護+operator-gated。
承 [[2026-06-14 全倉 cold security audit]]（5-gate/socket/HMAC baseline 一致）。報告：返回 text output（harness 禁寫 .md，findings 走 structured output）。

### 2026-07-09 IBKR P1 fingerprint-only SecretSlotLoader 設計安全審查（E3 DONE_WITH_CONCERNS）

**Verdict：DONE_WITH_CONCERNS — 0 CRIT / 0 HIGH / 3 MED / 4 LOW / 3 INFO（設計階段，碼未實現）**。審 PA `2026-07-09--ibkr_p1_secret_slot_loader_tech_design.md`（消費既有 `IbkrSecretSlotContractV1`，落 openclaw_engine）。
- **Q1 經驗證（只有 E3 能做，ssh trade-core read-only）**：engine PID 1042142 environ **OPENCLAW_SECRETS_DIR 未設**（count=0；只有 OPENCLAW_DATA_DIR/BASE_DIR/IPC_SECRET_FILE/HOME）。bybit `read_secret_file`+`authorization_path` env-set 時把 `OPENCLAW_SECRETS_DIR` 當 `secret_files/bybit`（fallback=`$HOME/BybitOpenClaw/secrets/secret_files/bybit`）；restart_all.sh:79 `BYBIT_SECRETS_DIR=${OPENCLAW_SECRETS_DIR:-$SECRETS_ROOT/secret_files/bybit}` 佐證。PA loader 卻把同一 env 當 secrets ROOT（fallback=`.../secrets/external/ibkr`）=**語義衝突（MED-1）**。runtime env 未設→兩者皆走 HOME fallback→P1 實際解析 `/home/ncyu/BybitOpenClaw/secrets/external/ibkr`。**應建槽絕對路徑**：`/home/ncyu/BybitOpenClaw/secrets/external/ibkr/{readonly,paper}/`（live/ 永不建）。secrets/external 現不存在。建議：base 綁 secrets ROOT（OPENCLAW_SECRETS_ROOT 或 HOME fallback），勿 overload OPENCLAW_SECRETS_DIR；resolved-but-nonexistent base 須回 Err→denied fallback（不得標 live-absent proven）。
- **Q3 裁決**：recommend **stat-only（PM 傾向），非 content-digest**。理由：只讀 account_id（不可避免）不碰最敏感憑證位元組→零逃逸更強；P5 triangulation 只需 slot-identity 綁定，stat(mode+len+filename 排序)可跨腿重算免讀內容；content-digest 會在合法憑證輪替時誤判 tamper 卻無額外防護（cross-account swap 已被 account_id hash 捕捉）；契合 AMD 字面「stat + emit sha256」。
- **MED-2 symlink 覆蓋不全**：PA symlink fail-closed 只講「槽內檔」，未覆蓋槽目錄本身(readonly/paper/live/)為 symlink→須對三槽目錄 lstat，是 symlink 即 fail-closed（否則 live/→空目錄 symlink 可偽造 live-absent）。**MED-3 父目錄權限**：只驗槽 0o700/檔 0o600，未驗 external//ibkr//root 父目錄 owner-only→可寫父目錄=整槽掉包。
- **1a/1b/1c 明文零逃逸**：struct 全 enum/bool/hex-String 無明文欄=結構性安全（Debug/Serialize 帶不出）；io::Error Display 不含檔內容（account_id 讀失敗不洩內容）；須 E2 grep 確認無 log 內插 account_id/descriptor。account_fingerprint_hash 是低熵 paper 帳號無 salt 之 sha256=binding 非 confidentiality（unsalted 正確，triangulation 要求，勿當可公開 secret 過度宣稱）。
- sha2/hex/libc 在 engine crate 已備（libc→O_NOFOLLOW 硬化可行，無新 dep）；zeroize 無（PA 建議手動 Drop 歸零，威脅模型 LOW 可接受）。
- **E1 開工前必鎖**：base-path 約定（CC 需就 AMD 字面 vs runtime 實值裁定）+ Q3 stat-only + symlink 覆蓋槽目錄 + 父目錄 owner-only + nonexistent-base→Err。報告以 text output 交 parent（harness 禁寫 .md）。

### 2026-07-09 IBKR P2 external-surface gate producer 設計安全審查（E3 DONE_WITH_CONCERNS）
**Verdict：DONE_WITH_CONCERNS — 0 CRIT / 1 HIGH / 3 MED / 5 LOW（設計階段，producer 碼未實現；現況正確 fail-closed BLOCKED）**。審 PA `ibkr_phase2_gate_producer.rs` 設計（消費既有 `IbkrPhase2GateArtifactV1::validate()`+P1 loader）。
- **HIGH-1（consume/precontact 必須 re-verify 非 file-exists）**：`validate()` 只查 hash SHAPE（`is_sha256_hex` 64-hex，不重算內容）→ 任何能寫 seal 路徑者（gov_dir 0o700 同-uid）可捏 sealed=true+PM/Operator+假 hash 過 validate()。**唯一防線=`verify_sealed_artifact()` 重算**，必須在 seal 前**且 consume/precontact `immutable_pass_artifact_present` 讀取時**都跑；precontact 現硬編 false，改 1 行必為 full validate()+verify（重算 hash）非 exists 檢查，否則 = 假 unlock G4。
- **Q1 經驗證（ssh trade-core read-only）**：`OPENCLAW_DATA_DIR` code 預設 `/tmp/openclaw`（main.rs:319/541/1053/1667 等全預設，restart_all.sh:45 `${OPENCLAW_DATA_DIR:-/tmp/openclaw}`）。trade-core **兩路徑皆存在**：`/home/ncyu/BybitOpenClaw/var/openclaw`(0o700 ncyu 持久) + `/tmp/openclaw`(0o700 ncyu, ephemeral)→證引擎曾在兩解析下跑過。**recommend**：reuse DATA_DIR+`governance/ibkr_phase2/` 子目錄（絕對路徑 `/home/ncyu/BybitOpenClaw/var/openclaw/governance/ibkr_phase2/`），**不新增 OPENCLAW_GOVERNANCE_ARTIFACT_DIR**（新 knob 會與持久 mount 漂移）；**MED-2 refuse-ephemeral**：producer 必 refuse-to-seal 若解析到 `/tmp/*` 或 OPENCLAW_DATA_DIR 未顯式設（用 code 預設）。secrets/external 現 absent→P1 loader Err→denied fallback→**現況必然 BLOCKED 已驗**。
- **Q2 裁決（MED-1 approval 模型）**：owner-only 0o600 approval TOML **單獨不足**（同-uid ncyu 進程/被入侵 Python 控制面/agent shell 皆可捏，無法證「人類 Operator」）。**recommend 最低**：source_commit==BUILD_GIT_SHA[PA有]+adr/amd[PA有]+**expiry/freshness 窗**（防 reboot 後 stale replay）+**approval 內容 hash 嵌入 sealed artifact**（tamper-evident lineage）+owner-only 0o700 ancestor+symlink-reject（reuse P1 `ensure_ancestor_owner_only`）。**目標=HMAC-signed via controlled approve path**（對齊 authorization.json 硬邊界#5，避免弱平行 auth 面）；誠實 caveat：同-uid 可讀 signing key 故 HMAC 邊際增益有限，主值=防手寫/意外+可審 approve path。read-only/zero-money blast radius（premature paper 讀連非 live order）→ operator 接受風險則「0o600+source_commit+expiry+content-hash+owner-only ancestor」為可辯護 MED 方案。**CC 需回場裁 Q2**。producer 絕不自注 Operator=結構正確（reviewer_roles 預設[]→validate BLOCK）。
- **Q3 裁決**：topology.account_fingerprint_hash **綁 P1 真槽 hash（yes）**；**MED-3**：validate() 不 cross-check `secret_slot_contract.account_fingerprint_hash == api_session_topology.account_fingerprint_hash`（template 用 "b"*64 vs "c"*64）→producer 必 enforce 兩者相等（同帳號 evidence-integrity）。
- **write-once**：`create_new(O_EXCL)`/`hard_link`(EEXIST) 皆真原子 fail-if-exists（非 rename overwrite，persistence.rs:69 rename 是 mutable 模式不可用於 seal），防二次 seal 正確。**LOW**：①gov_dir owner-only+owner==euid 必在 create_new **前**驗（勿假設 DATA_DIR perms）；②seal 後 fsync **parent dir**（dir entry durability）+ tmp 用唯一名；③chmod 0o400 是 advisory（owner 仍可 rm/chmod）—write-once 防意外/雙seal/非-owner tamper 非 determined-owner 刪，真 immutable 需 chattr+i(特權/運維)；④build.rs 無 dirty-tree marker(git rev-parse HEAD only)→dirty build artifact 誆報 clean HEAD commit；⑤precontact 狀態行禁 echo immutable_storage_path 絕對路徑(path-leak)。
- **fail-closed 完整性**：0 fake-PASS at seal（validate+verify 雙綠才寫）；ibkr_call_performed 硬編 false（validate 拒 true）；net-free/0 socket/0 DB/Bybit 不變；immutable 寫=governance evidence（同 halt_audit.log/boot_history.jsonl 落 DATA_DIR）在引擎既有寫面內，非越只讀邊界。
- **E1 開工前必鎖**：HIGH-1 consume re-verify + Q1 refuse-ephemeral + Q2(CC 裁 approval 模型) + Q3 cross-contract equality + gov_dir owner-only verify。P1 loader 需 `ibkr_secret_slot_contract()`(:473) + `denied_..._fallback()`(:492) 由 private→pub(crate)（現私有，PA 2-行 bump 屬實）。**CC 回場（Q2 auth 模型）；BB 不需（P2 非 exchange-facing，IBKR contact 硬編 false）；FA 輕度（確認 approval 機制入 ADR/AMD lineage 非未文件化 auth 面）**。承 [[2026-07-09 IBKR P1 fingerprint-only SecretSlotLoader 設計安全審查]]。報告=text output 交 parent（harness 禁寫 .md）。

### 2026-07-09 IBKR B1 read-only TWS client (G4 first-contact) 設計安全審查（E3 DONE_WITH_CONCERNS）
**Verdict：DONE_WITH_CONCERNS — 0 CRIT / 0 HIGH / 3 MED / 5 LOW / 4 INFO（設計階段，碼未實現；build now / run=G4）**。審 B1=engine 內單一只讀 TWS wire subset（connect handshake + reqCurrentTime）3 層惰性 gate（compile `#[cfg(feature="ibkr_g4_contact")]`+required-features bin / runtime re-verify sealed PASS ∧ 新 `phase2_g4_first_contact_approval.toml` A-model / structural hardcoded 127.0.0.1:4002）。
- **MED-1 out-of-band-auth loopback TCP 面**：127.0.0.1:4002 非 uid-gated（不同於 engine 0o600 unix socket）→ 任何本機進程可連已認證 Gateway；B1 碼只讀不使系統只讀，防 order-write 的 load-bearing 控制在 Gateway 側「Read-Only API」勾選。G4 setup 必鎖（read-only API + loopback bind + trusted IP 127.0.0.1 + master client id）。
- **MED-2 managedAccounts(msgId 15) 握手洩帳號**：START_API 握手令 gateway push paper 帳號 + nextValidId（不論只問 currentTime）→ B1 wire 收 account-identifying 材料；parser 必 fingerprint-hash-or-drop、絕不 log/serialize 明文。
- **MED-3 compile-gate 是 build-config 不變量**：`--all-features`（測試矩陣常見）會把 socket 編進 artifact（runtime gate 仍守=僅破 layer-1）。鎖：default/live CI 禁 --all-features + 加 nm/objdump symbol-audit（復用 replay_runner_symbol_audit.sh pattern）證 IBKR G4 socket 符號不在 default artifact。
- LOW：①host 必 literal `127.0.0.1` const 非 "localhost"（is_loopback_or_unix_local_host 收 localhost/unix: 可被 hosts/DNS 重導；connect 勿走該 helper）②G4 approval 必與 seal approval 不同檔+不同 token（reader 不得接受 phase2_seal_approval.toml；6 綁定 amd==AMD-2026-07-08-01+含 Operator+source_commit anti-replay+freshness+symlink-reject+euid+0o600+0o700 ancestor）③MAX_FRAME_LEN 小（≤64K）+ length-before-alloc + read budget/timeout ④driver 保 pub(crate) 只 monomorphize duplex/測試,default 只拉 tokio::io traits 非 tokio::net ⑤無 production caller（main.rs/boot 不 invoke，grep 可證，bin standalone）。
- INFO：runtime-gate #2 今日已正確 fail-closed（`phase2_immutable_pass_artifact_present()` production 恒 false=無 sealed artifact/triangulation mismatch pre-P5 → G4 run 已被封，須先 P2-seal-wiring）；B1 之外連實為 local-to-gateway（憑證不經外網）；MIT-MF-1 N/A；secret-leak grep 0。
- **G4 approval 模型確認**：仿 P2 A-model 6 綁定=足（AMD clarification #2 明訂 dual Operator gate=seal approval + 獨立 G4 approval；option A 授權 read-only/zero-money，無需 HMAC）。**E1 可開工 build**；G4 run 需 BB+E3+Operator（AMD 表）。CC 輕度回場確認 G4 approval 合既定模型（非阻擋）。承 [[2026-07-09 IBKR P2 external-surface gate producer 設計安全審查]]（HIGH-1 consume re-verify 已閉=phase2_immutable_pass_artifact_present 全 re-verify）。報告=text output 交 parent（harness 禁寫 .md）。

### 2026-07-09 IBKR engine rebuild+restart deploy security proposal (E3 DONE_WITH_CONCERNS — CONDITIONAL-GO)
**Verdict: engine-only rebuild is technically safe on IBKR axis but CANNOT avoid un-dormanting ALR P2-8 notifier → requires ALR-session coordination + operator explicit accept + BB (exchange-facing demo).** Running engine PID 1561777 = stale build_sha `54d5fbf99`(07-05T16:25Z), restarted 07-09 08:28 WITHOUT --rebuild so ran 07-05 code; API PID 3771536 even staler (07-05 18:32). Rebuild deploys 7 rust commits 54d5fbf99..2787042d0: IBKR P0(c66338e8b display-only stock_etf,Bybit unchanged)/P1(3217e94b4 loader 0-caller,slots absent→denied)/P2(b89c7b2d8 never-seals-prod)/T1T2(58d0e9749)/B1(aedca2291 **compile-gated `ibkr_g4_contact`, default build excludes socket**) + **ALR notifier f894d6401** + registry serving 30776e586. **CORE go/no-go**: `notify_alr_scanner_snapshots` (trading_writer.rs:1016) fires `pg_notify('alr_scanner_snapshot_v1')` **UNCONDITIONALLY** on scanner flush — NO env gate; scanner live (79761 rows, +118/2h) → ANY HEAD rebuild auto-activates P2-8 notifier (identity-only payload, LOW technical blast radius, research-only consumer openclaw-alr-shadow.service PID 1958773 running poll-based) but crosses TODO v774 core-prohibition "no service restart/rebuild" + "P2-8 needs separately safe notifier path". Cannot keep notifier dormant via any flag; only via not-restarting or building pre-f894d6401 (loses B1). **Demo write flags already ON in running engine** (BOUNDED_PROBE_ADAPTER=1/DEMO_LEARNING_LANE_WRITER=1/FLASH_DIP_PILOT=1); restart_all engine env == running env (no NEW demo-write). **Safe scope = `--engine-only --rebuild` (via build_then_restart_atomic.sh, explicit OPENCLAW_DATA_DIR=.../var/openclaw + IPC_SOCKET to avoid /tmp inherit per 07-07 precedent)**: avoids restart_api which would NEWLY activate OPENCLAW_STRATEGIST_PROMOTION_ENABLED=1 + SM_IPC_CANARY=1 (in env-file, absent from running API). **Bybit**: BYBIT_MODE=demo + BYBIT_CONNECTOR_WRITE_ENABLED=true → engine reconnect exchange-facing(demo/play-money); bounded-probe adapter re-inits enabled on boot → BB must confirm demo book clean + soak plan no-order + standing auth expired (status ACTIVE but TODO expiry 00:12Z<now) so no probe fires. **Rollback gap**: cargo build overwrites 07-05 binary in place, no auto-backup → cp binary aside pre-rebuild for fast swap. Report=text output to parent (harness no .md).
