# E2 Memory — 工作記憶

> 本檔=長期教訓+近期記錄；超 300 行由 R4 巡檢標記、PM 派工壓實，舊條目原文遷 memory-archive.md（append-only）；agent 完成序列照常追加於檔尾。

## 長期教訓

1. 對抗驗證三層缺一不可：跑綠（必要不充分）→ mutation 注入「最像 E1 會犯的錯」證每條 load-bearing claim 有 test-bite → 真資料/真 artifact 撈 bug-signature 計數證非 vacuous；mutant 改 /tmp copy 或改後還原，結束 `git status --porcelain` 驗空。
2. 永不採信自報：E1/MIT 的測試數、coverage、「byte-identical」「我都 re-export 了」全部親跑/親 grep 重驗；re-review 抽驗優先找算術 invariant（test 總數守恆、`git diff | grep -cE '^\+\s*(async )?def test_'` 計數）；per-file 拆分宣稱要抽查。
3. behavior-preserving 拆分/搬移黃金證法：AST 逐 symbol body byte-compare（比肉眼讀長 diff 可靠）+ 全套 test count 不變 + caller namespace/re-export 同級；「某檔 0 改動」宣稱用 `git diff -- <path>` 空輸出一條命令證實。
4. 拆分/DI/rename/tuple 擴張後必 grep 全 repo 窮舉 caller（含跨模塊 importer、test mock return_value、multi-value unpack）；symbol importable ≠ 簽名兼容；helper 回 N 個值要反問「沒串接的是 by design 還是漏」。
5. 註釋/spec/docstring 每句當 claim 對源碼逐路徑證偽——comment-accuracy fix 自己最易寫進新錯；「宣稱的保證」（per-cap 上限、fail-loud panic、依賴聲明）要追 data-flow 上游實證可達，「mirror 既有 pattern」可能 mirror 到不可達性；spec 內部矛盾應 escalate 仲裁而非自行 invent。
6. silent-fail 同族一律標 issue：Python `except: pass`、SQL `EXCEPTION WHEN OTHERS`、bash `2>/dev/null`/`|| echo 0`、cron wrapper「non-fatal」echo、healthcheck 預設 PASS；cron review 必先 grep non-fatal/set -e/env export（cron cwd=$HOME，env 必顯式 export 不靠繼承）。
7. 「代碼存在 ≠ 接線可達」：新 check/producer/handler 必驗接進真會 fire 的中央 runner/conductor（`git grep <module> -- '**/runner.py'` 0 hit = silent-dead）；dormant/deferred code 的 latent bug 仍要退，dormant≠免審。
8. 監測儀器自身要驗有效：shadow comparator「0 divergence/0 mismatch」可能是 gate-placement artifact 非一致性證據；必畫「能 fire 的分歧子空間」+ 雙向 mutation（短路 record→測試紅、echo 全 match→測試紅）證 instrument 真活；fail-closed 正確 ≠ soak 證據有效。
9. verdict 命脈與 fail 方向必查：先查 verdict emit 在哪個函數、被哪個 test 直接斷言（CLI-only override 是假安心）；手刻統計必測退化輸入（constant/zero-dispersion），fail-open（false-GO）比 false-NOGO 危險；小樣本終局 kill verdict 用 power 模擬破「低 power 假陰性當鐵證」。
10. 測試 bite 隱形殺手：同向 soft scorer 掩蓋 gate 測試（必中性化隔離使 gate 成唯一決定因素）、unit 注入參數遮上游解析錯（provenance/版本欄需 caller→registry→落庫 e2e 斷言）、test 手放被測欄位遮 absence-regression、邊界 test 對 spec 核非對 code 核。
11. collateral 抓漏靠全套 sweep 不靠點名：受影響檔案清單由 grep 推導必漏 test fixture 隱性依賴；base-vs-HEAD 全套失敗清單 sorted diff 是決定性手法（既有紅會淹沒肉眼）。
12. migration/PG 審查：V### 必獨立 Linux sandbox 親跑 double-apply + 經驗 schema 反射 + 對抗 INSERT 探針；Mac mock-PG 抓不到 NOT NULL/grant/jsonb 數值正規化（此類必標 Linux-owed 不默認 PASS）；`CREATE OR REPLACE VIEW` 只能 APPEND 不能 DROP column；跨表同義異名欄（actor_id vs created_by）逐表 grep 不信 mental model。
13. §5 multi-session race 紀律：review 前 fetch 比 `origin/main...HEAD`；髒樹他人改動/外來 stash 一律不碰不 revert；review 期間 sibling push 用檔案集 comm/diff 證 0 overlap，照 SOP 記錄不忽略；meta-doc narrow-stage `git commit --only`。
14. 角色與報告慣例：E2 發現 issue 退回 E1 不代寫；re-review/second-pass 限 fix delta 不 scope creep；report 默認 inline 回 parent 不寫檔，長報告才放 workspace/reports/；over-redaction（過遮毀用途）與漏遮同為 finding。
15. 審查強制清單（原文已歸檔，要點不變）：中文優先註釋/MODULE_NOTE、innerHTML 必 ocEsc()、SQL 參數化、`except HTTPException: raise` 穿透、governance route 必 `_require_operator_role()`、`submit_order()` 前 `acquire_lease()` fail-closed、治理不可被 env-var 禁用、測試數 ≥ 任務前基準、§九 800 行警告/2000 hard cap（exact-touch 默認補 split follow-up）。
16. 資料怪象先分視角再判 bug：aggregate（max(delisted_at)）vs latest（is_delisted_at_asof）不一致可能是「已公告未來下市」等真實資料形狀非 corruption；判 source-data 特性 vs 實作缺陷看 window-clip/statuses_seen 是否正確處理。

## 近期記錄

## 2026-06-08 — L2 Advisory Mesh Phase 2（Orchestrator+registry+admission+adjudication+fail-safe+guard）E2 對抗審 → RETURN E1（1 HIGH + 2 MED + 2 LOW；全 dormant，0 P2-runtime-blocker，但需修正 spec-claim 才 PASS）
- **範圍**：branch `feature/l2-critic-lessons-tools`，P2 疊 P1 `f1c3c1ca` 未 commit。5 新模塊（l2_capability_registry/l2_prompt_contract_registry/l2_out_of_bound_guard/l2_conflict_adjudicator/l2_advisory_orchestrator，共 1275 行全 <800）+ wiring delta（layer2_engine +20/layer2_routes +95）+ TOML(48) + 60 test + singleton §2.6.2-2.6.4。全用 `venvs/mac_dev/bin/python`（3.12 tomllib）。
- **裁決 = RETURN E1**。linchpin 全綠（mutation 親證有 bite），但 **HIGH-1 per-capability daily ceiling 是 no-op**——code/comment 宣稱 PA §F.1 stage4「per-capability 硬日上限→NO_ADVICE」但實際只 re-read 全域 `remaining`，零 per-cap spend accounting。實證：cap_daily=0.01 + 全域 remaining=1.5 → 30/30 distinct-subject trigger 全 admitted，per-cap ceiling 從不 fire。**load-bearing 全域 $2/day storm 閘正確**（test_storm 綠），HIGH-1 只是被宣稱卻未交付的「額外」per-cap 細化。dormant（dispatch 0 production caller）但 spec-claim 不實必修。
- **★ 關鍵 framing（嚴控 severity）：dispatch() + report_call_outcome() 在 P2 皆 0 production caller**（grep `app/` 證；`.dispatch(` 命中是 ai_service_dispatch/listener 別物件；routes 只呼 status/reload/reset 不呼 dispatch）。整個 admission loop + fail-safe SM 是 **dormant skeleton**（PA §A.2「P3 才接 executor」一致）。唯一 P2-live 路徑 = layer2_engine wiring delta（contract_ver/schema_ver 改 registry-resolved，fail-soft fallback 既有常數）。故所有 SM/admission finding 都是 **latent**（P3 wire trigger surface 才 bite），非 P2 runtime hazard。
- **MED-1 fail-safe SM ollama_available 分支序 bug**：`report_call_outcome` :388-397，`elif ollama_available: DEGRADE_OLLAMA` 在 `<5 NO_ADVICE`/`<10 TRIPPED`/`else GLOBAL_CONSERVATIVE` **之前**→ 實證：ollama 持續 available 時 SM 永卡 DEGRADE_OLLAMA，50 連敗仍到不了 TRIPPED/GLOBAL_CONSERVATIVE（unique states 只 {RETRY,DEGRADE_OLLAMA}）。PA §H「repeated failure/guard storm→TRIPPED→systemic→GLOBAL_CONSERVATIVE」escalation 在 ollama-up 場景不可達。測試只測 ollama_available=False 路徑（漏 ollama-up persistent-fail）。方向（不代寫）：escalation 須與 ollama-availability 解耦——consecutive_failures 累積到閾值該 TRIP（即便 ollama 還活），或 DEGRADE_OLLAMA 本身要計次升級；+補 ollama-up persistent-fail 測試。
- **MED-2 admission state race（dedup/debounce 無鎖）**：`dispatch`→`_admit` 改 `self._admission.last_served_ts[k]`(:322)/`debounce_pending`(:275/287) **不持 self._lock**；而 report_call_outcome/reload_registry/reset_fail_safe 都持鎖但碰的是別 state(_fail_safe/_registry_cache)。鎖保護不對稱：admission 窗口裸奔。dispatch 是 **sync 無 await**（驗 :163 無 async/await）→ 單 event-loop 內不交錯（asyncio 邊界 #7 PASS），唯多 OS thread 並發呼 dispatch 才 race（兩同 dedup_key trigger 各讀 last_served=None 各放行=破 dedup storm-control identity）。P2 0 caller 故 dormant；P3 多執行緒 trigger surface 會 bite。方向：admission 窗口 mutation 納入同一 self._lock（或獨立 admission lock）。
- **LOW-1 cold-cache 壞 TOML 讀路徑 500**：boot 後 operator 手改 TOML 成 malformed（繞過 validated /registry/reload）+ 冷快取 → 下次 `_registry_obj()`（status() 讀路徑亦呼）raise L2RegistryLoadError **uncaught** → GET /orchestrator/status 回 500 非結構化 degraded envelope。實證 status()/dispatch() 皆裸 raise。安全意義 fail-closed（不採壞 config），唯 graceful 不如 /registry/capabilities route（該 route 有 catch）。方向：_registry_obj 或 status 對 L2RegistryLoadError fail-soft 回上次good/empty+degraded flag。
- **LOW-2 adjudicate_vs_gate 未知 verdict fail-open（gate-recognition 軸）**：:89 只 reject/fail/block→a_wins，其餘（含 'warn'/''/None/未知）→b_wins。「gate reject 永勝」不變式成立（reject→gate 勝），且 b_wins=「L2 走自身下游 gate 非直接 apply」（docstring 明載），故非 safety bypass。唯未知 gate verdict 默認「放 L2 續走」是 gate-辨識軸的溫和 fail-open。as-designed 可接受，P3 真 gate verdict 接線時建議未知→fail-closed。
- **全綠（實證非讀碼）**：① LANE_DIRECTION linchpin：無 'live' key（test 驗 key+value 皆無）；STEP-1 expand→MANUAL 在函數頂（inspect 剝 docstring 驗 idx_step1<idx_tier<idx_posture）；mutation 改 STEP-1 return AUTO_VIA_GATE → **4 test 紅**（含 dispatch :239 防禦性 fail-closed 補抓 leak 的 expand）；model_construct 繞 validator 給 lane='live' → STEP-1 subscript **KeyError fail-loud**（可接受）；validated 構造 reject live(ValidationError)。② 三 reject 分支全綠（autonomy_level 宣告/can_auto_deploy_to_paper-as-posture/lane∉表 + min_tier 非法 + unknown-field extra=forbid + unknown-top-key + 重複 capability_id）；enabled 預設 false；TOML 不存在→空 registry fail-closed；解析錯→L2RegistryLoadError。③ adjudication：mutation flip PRECEDENCE(contract=0/expand=2) → 2 test 紅；adjudicate_vs_gate 9 verdict 變體（含 case/None/空）全對；stateless 純函數。④ guard：inf→clamp10、-5→clamp0、neg cost→reject、NaN→reject、empty available_axes+referenced→reject(fail-closed)、==cap 邊界 pass；無 model。⑤ **carbon-grep tokenizer-strip 真有 bite**：注入 promote_tier 為**真碼**→C1 test 紅；既有 promote_tier 在**註解/docstring**→baseline C1 綠（strip 區分碼 vs 散文，非空測）。⑥ wiring delta：reachable（run_session:671 呼 _record_l2_call_to_ledger）；非死碼；**fail-soft 親證**——強制 resolve_contract_versions raise → fallback l2_contract.v1/l2_schema.v1 且 **D3 row 仍寫出**（零回歸）；lazy import 破 cycle（engine 端 lazy，registry 端 module-level import 常數）。⑦ 2 write route（/registry/reload、/orchestrator/fail-safe/reset）首句 require_scope_and_operator("ai_budget:write")（同 /cost/reset 範式，raise fail-closed）；reload 先驗載入成功才換 cache（壞 config 不換，HTTPException 400）；2 GET 唯讀。⑧ C1/C2/order-lease grep 跨**全 advisory-loop 模塊集**：每 hit 全在 comment/docstring/MODULE_NOTE 或 _FORBIDDEN_POSTURE_GATE_TOKEN 字面（C2 reject-target 非 flag-branch）。
- **標準項全綠**：60 test pass（0.17s）；layer2/l2 family 358 pass+4 xfailed（wiring delta 零回歸，含 test_layer2_critic 走 engine 路徑）；py_compile 7 檔 OK；0 hardcoded path（2 hit 全註解「禁硬編」policy ref）；0 f-string log；0 bare except；0 detail=str(e)；0 私有屬性穿透；0 stray print；threading.Lock 無跨 await（dispatch sync）；5 MODULE_NOTE 全在；comment 中文優先（0 大段英文）；singleton §2.6.2-2.6.4 class/binding/getter 名對；**0 production-code scope creep**（diff 只動 L2 P2 + 已知 wiring 檔）。
- **out-of-scope 確認**：test_layer2_critic.py(+26) 0 ref P2 模塊=他 session WIP（D3 l2_reply_id context_id，brief 指明勿審）；aeg builder/test_aeg ` M`=他 session；4 replay collection error=pre-existing import-path harness。
- **§5 race 5/5 PASS**：5a/5e `git fetch` 後 origin/main=`b6f918d9`（residual PART4 track，非 L2），`git log origin/main -- <P2 3 檔>` **0 commit**（greenfield uncommitted local，0 file-scope overlap）；HEAD=`f1c3c1ca` 落後 origin/main 因 P2 疊 P1 未 rebase（PM merge 前 rebase，非 P2 blocker）；5b unstaged 全 L2 P2 scope+agent memory；5c 3 stash 全 pre-existing/別 session（標「not mine」）未動；5d N/A（未 commit）；review 中無新 sibling push 進 P2 scope。mutation 全 cp backup + 還原（非 git destructive），每次還原 git diff --stat empty 親驗。
- **教訓**：(1) **「宣稱的保證」要實證它真交付**——HIGH-1 comment 寫「per-capability 硬日上限」但 code 只讀全域 remaining，跑 cap_daily=0.01+remaining=1.5 才抓到 30/30 全放行；不能信 comment+變數名（cap_daily 讀了但沒比 per-cap spend）。(2) **dormant skeleton 的 latent bug 仍要退**——P2 dispatch/SM 0 caller，但 PA §M row 明列 SM 為 E1 交付物且要求轉移正確；fail-safe ollama-up 卡 DEGRADE_OLLAMA 是真 SM bug，P3 wire 就 bite，不能因「現在沒跑」放行（對抗審查 = 找 root cause 非症狀，dormant≠免審）。(3) **鎖保護不對稱是隱性 race**——3 處 with self._lock 給人「有併發保護」錯覺，但 admission 窗口（storm-control 命脈）裸奔；要逐一對照「哪些 mutable state 被哪把鎖蓋」，sync-no-await 只擋 event-loop 內交錯非多執行緒。(4) **fail-soft 要親跑**——強制 resolver raise 證 D3 row 仍寫得出 + fallback 值對，比讀 try/except 可靠。(5) carbon-grep 這種「剝註解驗真碼」測試必親自 mutate（注入真碼 vs 註解兩路）證 strip 有 bite，否則可能是空測。

## 2026-06-09 — E2 residual PART 4 Gap A market-basket selection fix `2fca92fe` — PASS to E4

審 `feature/residual-activation` 上 `2fca92fe`（parent `67730b7b`）：`_load_multi_factor_inputs` basket 選取由字母序改流動性排序。**verdict PASS-to-E4（0 finding）**。

- **★ survivorship/PIT 全綠（key risk）**：候選域**仍是** `pit_active_symbols(lifecycles, s_epoch, e_epoch)`（line 378，與舊碼 byte-identical），新 `load_liquid_basket_symbols` 只用 `symbol = ANY(active)` 在該 PIT 集**內**按 `count(*)` 排序+過濾無資料者，**從不擴/縮候選域**。關鍵推理：`pit_active_symbols` 成員條件 `delisted_at > exit_ts`（=活過整窗）→ 任何 PIT-active symbol 必在 `[since,oos_start]` 有 bar → count 查詢必留它；mid-window 下市者本就被 `pit_active_symbols` 排除（舊新碼皆不選）。故**修復不可能引入新 survivorship bias**——只重排既有集。窗 = `start=cfg.since`/`end=cfg.oos_start`（line 349-351），與 `pit_active_symbols` 及 `load_klines_by_symbols` 三者**同一 PIT 窗**，非「recent」。
- **real-seam test 真關盲點 + mutation 親跑有 bite**：`test_load_multi_factor_inputs_selects_data_bearing_not_alphabetical`（:1117）**不** patch `load_liquid_basket_symbols`（:1148 明示），走真選取 seam，lifecycles 讓字母序前綴 symbol 全 PIT-active（舊碼必選）。**親手 mutation**：把 orchestrator 還原成 `sorted(set(active))[:N]` → 該 test **紅**（`AssertionError: Extra items: 0GUSDT/1000000BABYDOGEUSDT/1000000CHEEMSUSDT`，精準重現真 bug）；`git checkout` 還原後 4 新 test 全綠。E1 claim 誠實。
- **query 安全（read-only/參數化/no-crash）全綠**：`_LIQUID_BASKET_QUERY` 靜態常數 + `%(...)s` bind；唯一 `execute(` 傳 dict params（無 f-string/format 拼 SQL）；新碼 0 INSERT/UPDATE/DELETE/commit；`if not syms: return []` 在開 cursor 前→空候選 0 查詢（test 驗 `conn.cursors==[]`）；`RealDictCursor` lazy import 同模塊既有 8 處精確範式。
- **behavior-neutral 全綠**：唯一 caller = flag-gated orchestrator :475；diff 4 處 `min_basket_symbols` **全是註解**（下游 guard 0 邏輯改）；`_patch_db` stub 簽名與真 fn **完全一致**（kwarg-only `start_ts/end_ts/timeframe/limit`）→ 26 既有 test 為對的理由攔截非簽名漂移；`_process_candidate` 在 `oos_start/data_end is None` 時 :432-433 fail-closed `_skip` **早於** :475，故 `end_dt else start_dt` 退化窗在生產不可達（防禦性）；新 basket-window 表達式與相鄰 `load_klines_by_symbols` byte-identical（選到的 symbol 必同窗載到 bar，無 window mismatch）。
- **§3 OpenClaw 全綠**：0 hardcoded `/home/ncyu`/`/Users`；comment 中文優先（英文僅 `market.klines`/`pit_active_symbols`/symbol 名等識別符）；註解解釋 why（survivorship rationale + Gap A 根因）；`residual_alpha_producer_db.py` 943→1012（+69，未到 800 review-attention 增量門檻外、距 2000 hard cap 遠）。
- **全綠（實證）**：full `ml_training+learning_engine` **859 passed/31 skipped**（baseline 855/31，+4 新 test，0 regression）；mutation probe 親跑紅+還原綠。
- **§5 race 5/5 PASS**：5a/5e `git fetch` 後 origin/main=`b6f918d9`（residual PART4 track 的**前身** lineage `7b5d92e9`=Gap A orchestrator 已 rebase 上 main，與本 fix 同一 workstream 非競爭 sibling；本 fix `2fca92fe` 尚未上任何 remote）；overlap 屬同 track 預期非 5e RETURN trigger；5b unstaged 僅 meta（TODO v120→v121 / E2 memory 本人 / PA report `??`）**無 impl leak**；5c 3 舊 stash 未動；5d N/A（未 commit）。
- **教訓**：(1) 「選取/排序 fix」的 survivorship 審查 = 證**候選域未變**（domain 同一函數同一窗）比逐行讀排序邏輯更關鍵——bias 只能從 domain 擴縮來，重排既有集不引入新 bias。(2) 「修 synthetic-test 漏掉的 DB-seam bug」的 regression test 必須**不 patch 被修的 seam**（否則就是當初漏 bug 的同一盲點）；mutation = 還原舊實作看真 test 紅，是唯一可信證明。(3) stub 簽名 vs 真 fn 簽名要逐字對——kwarg-only 不一致會讓既有 test 為錯的理由 pass（本次一致，PASS）。

## 2026-06-09 L2 P2 fix round-2 delta re-review → PASS to E4
narrow re-review（上輪 RETURN 1 MED+1 LOW，E1 修 + 折入 /cost/reset+/cost/pricing operator-scope）。branch feature/l2-critic-lessons-tools，P2 未 commit 疊 P1 f1c3c1ca。改 4 檔：l2_advisory_orchestrator.py(untracked 新檔)、layer2_routes.py(M)、test_l2_p2_orchestrator.py(+14)、test_layer2.py(2 collateral)。**verdict PASS，0 BLOCKER/HIGH/MED/LOW**。

關鍵判定（實證非讀碼）：
- **MED-1 prune 純回收無語意變**：`_prune_stale_spend(today)` list-comp 收 `k[1]!=today` 後 del；wired 進 record_capability_spend lock 內 **prune-then-accumulate-today**。今日 key（k[1]==day）不被 prune→accumulate 仍對；`_cap_spend_today` 只讀今日 day_key→prune 只刪非今日→今日恆存。**per-cap 獨立性未退化**：同日 20 cap 共存（prune 只跨日 fire），test_spend_dict_bounded_multi_cap_single_day 證 20 key 全今日。跨日刪昨日桶=純回收（閘永不再讀昨日，daily-reset 語義本就存在於「新 day_key 無紀錄」）。
- **★ mutation 真 bite（親跑非信 docstring）**：把 prune 改 no-op → TestPerCapSpendBounded **3 紅**（across_many_days 10≠1 / prune_drops_only_stale / mutation_bite_without_prune）；2 同日 test 仍綠（prune 對同日本就 no-op）=正確。revert 已驗 clean 無殘留。
- **★ collateral test = 正當更新非弱化遮測（關鍵，親跑 auth 證）**：test_layer2.py 的 test_update_pricing_empty/valid 原用 **bare MagicMock()** actor（pre-gate update_pricing 只有 Depends(current_actor)無 scope 閘故穿透）；fold-in 後 update_pricing 首句 require_scope_and_operator。**親跑證 bare MagicMock → 403 operator_role_required**（MagicMock.__contains__ default False → 'operator' not in mock.roles → True → 403）。即舊 test gate 落地後**必 403**→collateral 更新**必要**。改後加 roles={"operator"}/scopes={"ai_budget:write"} 真 set（非 MagicMock auto-viv）→親跑證**genuinely 通過 gate**（非繞過）。仍驗原意圖（empty→no-updates / valid→success）只補 auth。grep reset_today_costs/update_pricing tests/ 確認**無遺漏 caller**：645/328 是 tracker.update_pricing(method 非 route 無閘)；1139/1153 已改；test_l2_p2 的 1125-1175 是新 +14 affirmative auth test。
- **/cost/reset 三態 auth 正確**：親跑 require_scope_and_operator：viewer→403 operator_role_required / operator+scope→PASS / operator-missing-scope→403 forbidden_scope。gate 在 state 變更**前**（reset :373 gate < :375 mutation；pricing :413 gate < :430 mutation；empty-update early-return 在 gate 後）。鏡像 :731/:757 同 first-statement 範式。test_handlers_source_calls_scope_gate_before_mutation 用 inspect.getsource 斷言 idx_gate<idx_tracker=結構序 bite。:675-680 訂正註釋誠實（明寫「先前誤稱已 scope 化」）與實況一致。
- **docstring LOW-1 準確**：cold-cache→空 fail-closed（無 cap=無 advisory=baseline） vs warm→last-good 已驗證 config（subtraction-only 保守降級非放未驗壞 cap）—與碼 _registry_obj :205-223 一致。
- **無回歸（親跑 mac_dev py3.12）**：test_l2_p2_orchestrator 88 passed / test_layer2 94 / 7 L2 檔 386 passed+4 xfailed（critic linchpin 綠）。full-suite 66 failed/4492 passed=**pre-existing PG/engine.sock IPC**（grep 證 0 FAILED 在 l2_advisory/layer2_routes/test_l2_p2/test_layer2 scope；4 collection-error 是 replay ModuleNotFoundError program_code，不 import 本 2 模塊）。
- OpenClaw 特殊：cross-platform grep 命中只在 leak-prevention test（斷言 /home /Users 不洩，§3.1 政策反例不在限）；無 except:pass；logger 用 %s 無 f-string；新註釋中文優先；檔 582/760 行 < 800。
- race check：5a HEAD 18ahead/32behind(已知 P2 疊 P1)，sibling push 全 residual PART4/phantom-fill = file scope disjoint(helper_scripts/research + rust，非 L2 app)；5b/5d 我 working tree 僅 task-scope 2 檔；5c stash 3 個 pre-existing 不碰；mutation-probe 已 revert clean。

教訓：collateral test「弱化 vs 正當」判定硬方法=**親跑 gate on 舊 actor 看是否 403**。bare MagicMock 在 require_operator_role 下 403（__contains__ default False）→舊 test 必破→更新必要且正當。對照 5/31 memory line 4150 ai_budget caller-guard 判斷亦同模式（grep caller + 親驗臨界區）。

## 2026-06-09 · L2 P3a ml_advisory cascade 對抗審查 → RETURN E1（1 CRITICAL sink-DB）

審查面：`l2_ml_advisory_executor.py`（新698）+ orchestrator dispatch_and_execute 活化 + guard ml_advisory.guard.v1 + 2 contract + TOML 2 stanza。branch `feature/l2-critic-lessons-tools` P3a 未 commit。

**verdict = RETURN E1（1 CRITICAL）**。其餘 7 軸全綠（cost/cascade/dispatch/coarse-subject/sink-0exec/no-regression/comment）。

- **★ CRITICAL（decision #1 sink）**：`write_ml_advisory_advisory_sink` 直接 `INSERT INTO learning.mlde_shadow_recommendations` **省略 `evidence_source_tier`**。V040 已把該欄 `SET NOT NULL`（無 column DEFAULT；`DEFAULT 'real_outcome'` 只是 V036/V055 **SQL 函數參數**預設，非欄位預設）→ 真 Linux DB INSERT **必 NOT NULL violation = sink 永遠寫不進**。三重問題：(a) V040 NOT NULL；(b) V051 paired CHECK lineage（real_outcome→replay_experiment_id+manifest_hash 皆 NULL，否則 FK 必填）→ 唯一可用值 'real_outcome' 對「斷言無 alpha 診斷」語意錯；(c) V037 REVOKE PUBLIC INSERT，唯一合規寫路是 `verify_replay_evidence_and_insert()`（V036/V055），全庫**唯一**直接 INSERT 就是 E1 新碼 line 430（grep 證），canonical producer mlde_shadow_advisor.py:470 走 SQL 函數。**為何 44 綠測抓不到**：test `_CapturingConn.execute` 只 append SQL+params list，**不打真 PG**=不驗 NOT NULL/CHECK/grant → 經典「mock 遮真 DB fail」。建議轉 operator：方向 A 換 sink 走既有 `verify_replay_evidence_and_insert`（過 V037 grant，但函數帶 replay-evidence 語意 mismatch）｜B 開 V137 新 advisory 表（乾淨但 migration+Linux dry-run）｜C 既有表加 `evidence_source_tier='real_outcome'`+確認 db_pool role 屬 replay_writer_role（最小改但語意臟）。E2 傾向 B 或 A，operator 拍。

- **decision #2 cost = CONFIRMED 正確**：`_record_call_cost`→`engine._cost_tracker.record_claude_cost(tmp_session,...)`→delegate `layer2_cost_recording.record_claude_cost`→`_add_daily_claude_cost` 更新 `daily_spend.<day>.total_usd`（line 194）。admission stage-4 `_check_budget`→`_get_cost_tracker().check_daily_budget()`→讀**同一** total_usd。instance 同一：layer2_routes:101 engine 用 `cost_tracker=_get_cost_tracker()` singleton。**ml_advisory cloud 花費真進 $2/day counter，無 bypass**。tmp Layer2Session 是既有範式（engine 自身 triage_session line440 同樣）；daily rollup 是 tracker-level persist 非 session-scoped → cost 非永 0。local: tier→cost 0 但仍記（Ollama 免費正確）。

- **dispatch 活化 = 真非死碼**：dispatch_and_execute 先 sync dispatch（admission/RLock 不變）再對 `admitted+routed_to==neutral_sink+capability_id.startswith("ml_advisory")` 才接 cascade；disabled/deduped/tier_locked/非-ml_advisory/engine-None 全短路（test 8 條驗 eng.calls==[]）。executor_ok 把 screen_rejected/guard_rejected/unknown_mode 算 healthy（確定性閘正確擋下≠故障），只 cloud_unavailable/sink_fail 推 fail-safe = 對。

- engine interface 全對：`_provider_complete`(provider_name/tier/system_prompt/messages/tools/max_tokens/timeout) + `_resolve_effective_provider`(base_provider/base_tier/role) + PROVIDER_ANTHROPIC/TIER_HAIKU/TIER_SONNET + L2Response.input_tokens/output_tokens/text 全存在 → cascade 對真 engine 結構通（非 mock-only）。
- coarse_subject DoS（E3 域，碼正確）：_evict_admission_windows 在臨界區 top 持鎖呼，只清 >TTL(24h)≫dedup窗(≤900s)→不破 dedup 語意（test_dedup_still_works 證）。_derive_coarse_subject 折白名單+upper 降基數。
- M3 typing guard（clause B）+ regime_caveat（clause C）+ axes-subset（clause D）+ per-mode 必填（clause A）確定性無 model；run_guard API 對；_guard_ml_advisory_v1 呼 guard_output（非 run_guard）無遞迴。
- TOML 2 stanza 全 enabled=false，hypothesize（P3b）正確不含；P2 test 從 empty-skeleton→2-stanza 是**正當**更新（enabled_capabilities()==[] 仍成立 + 加 hypothesize-not-in 強斷言），非遮測。
- no-regression：P3a 44 + L2 全樹 430 passed（親跑驗）；replay 4 collection error 是 pre-existing 無關。
- 教訓：**advisory sink 落 schema CHECK 重表（V031→V038/V040/V051/V055 疊 5 層 retrofit）時，必查「V031 後加的 NOT NULL/CHECK/REVOKE 欄」+「唯一合規寫路是否 SQL 函數」**。code-review grep `INSERT INTO <table>` 比讀 V031 base schema 更快定位「全庫唯一直接 INSERT = 繞合規路」。Mac mock-PG 永遠抓不到 NOT NULL/grant → 此類 finding 必標「需 Linux PG dry-run 證」。

## 2026-06-09 — L2 P3a sink delta re-review + LOW-2 adjudication（narrow re-review；RETURN to E1）

承上輪（2026-06-08 CRITICAL #1 sink）。E1 已把 sink 從 `mlde_shadow_recommendations` 改寫成 `agent.lessons`（operator 拍板 = 上輪 decision-B「開乾淨 advisory 表」的等價：複用既有 inert lessons store，免 V137 migration）。本輪只審 sink delta + 評 E1 flag 的 LOW-2。**測試用 `venvs/mac_dev/bin/python`（3.12）**。

### sink delta = CONFIRMED 正確 + inert 真閉（S-2 結構性成立）
- **schema 對 V133**：`sql/migrations/V133__agent_lessons.sql` 8 欄 INSERT 全對齊（symbol/lesson_type/content NOT NULL 由 placeholder+mode+redacted-content 滿足；context_id=l2_reply_id；outcome_net_bps/session_cost_usd 內聯 NULL literal；source 覆寫 default 'l2_session' 為 'ml_advisory'）。param tuple index 與 INSERT 順位**逐位對**（test params[0..5] 全核）。type 對（TEXT←str / REAL←NULL）。
- **content 過 redactor = 真**：line 441 `content = _redactor.redact(content).text[:4000]`。**親跑 mutation-kill**：strip 掉 redactor → `test_sink_content_passes_through_redactor` FAIL（`KeyError: 'called_with'` spy 未被呼）→ 還原 → 綠。**bite 確認有牙**。
- **inert 安全閉合（獨立驗，非採信註解）**：grep 全庫 `agent.lessons` 的 prod consumer 只有 `layer2_critic.retrieve_lessons`（line 329/366 SELECT，唯讀 trigram+recency 回 rows 進 LLM 推理）+ critic persist（line 486 寫）。**對比驗 applier**：`program_code/ml_training/mlde_demo_applier.py` line 649 `FROM learning.mlde_shadow_recommendations` + line 451 `recommendation_type != "regret_summary"` + line 353/445 `_derived_strategy_targets`/`_bounded_risk_patch`→IPC mutate RiskConfig；該檔 **0 個 agent.lessons 引用**（grep EXIT=2）。⇒ P3a sink 寫 agent.lessons ⇒ **0 applier 撿 ⇒ 0 新執行權結構性成立**（非旗標約束）。上輪 CRITICAL（寫 mlde_shadow_recommendations 會被 applier line 649 撿去改配置）**因此被正確閉合**。
- **0 mlde_shadow_recommendations INSERT 殘留**：executor+test 的命中全在「解釋為何棄用」的註解 + test 反向斷言（`assert "INSERT INTO learning.mlde_shadow_recommendations" not in raw`）。0 真 INSERT。
- scope 整潔：跨平台 0 硬編（line 148 命中是「禁硬編」註解）；0 新 mutable singleton；0 except:pass / detail=str(e) / f-string log。cost/dispatch/cascade/M3/M4/coarse_subject guard 碼**未擾動**（上輪已 PASS，本輪確認 sink-only delta）。

### ★ LOW-2 = CONFIRMED 真 D3 provenance bug（退 E1；修在 orchestrator 非 sink）
E1 flag 對。`l2_advisory_orchestrator.py:429-432` `dispatch_and_execute` 傳 `resolve_contract_versions(contract_ref=None, schema_ref=None)` → 這個 contract_ver/schema_ver 是**寫進每條 D3 ledger row**（traverse run_ml_advisory_cascade → `_ledger` → record_l2_call）。但 `contract_ref=None` 使 `resolve_contract_versions`（registry line 271）跳過 branch1（顯式 ref）、跳過 branch2（`_CAPABILITY_SEED_CONTRACT` line 256 **只含 manual cap**，ml_advisory 不在）→ 落 **branch3 fallback** = `L2_PROMPT_CONTRACT_VER='l2_contract.v1'` / `L2_OUTPUT_SCHEMA_VER='l2_schema.v1'`（通用引擎常數）。
**親跑兩 branch 實測**（mac_dev py）：
- diagnose_leak：D3 記 `l2_contract.v1`/`l2_schema.v1`；**executor 實際用** `ml_advisory_diagnose.v1`/`ml_advisory_schema.v1`（registry line 173/137）→ **match=False/False**
- interpret_result：D3 記 `l2_contract.v1`/`l2_schema.v1`；實際 `ml_advisory_interpret.v1`/`ml_advisory_schema.v1`（line 212）→ **match=False/False**
⇒ D3 ledger 的 contract_ver/schema_ver **記成通用 fallback，與 cascade 實際送 cloud 的 per-mode 契約模板不符** → 違 root principle 8（reconstructable）+ D3 provenance 準確性。contract drift 時 ledger 會指向錯模板。**非無害**。修法：`dispatch_and_execute` 改傳 cap 的 ref（重取 cap 或把 dispatch() 已解析的 contract_ver/schema_ver thread 下來，line 354-360 已算對值只是沒用）。
**為何測試漏**：P3a test 全部**直接把 contract_ver 當參數注入 run_ml_advisory_cascade**（line 278 傳 `ml_advisory_diagnose.v1` 並 line 284 斷言 ledger 收到）→ 驗的是「executor 忠實 thread 收到的值」（對），**0 test 跑 dispatch_and_execute 對真 registry 的解析**→ divergence 漏網。RETURN 時建議 E1 補一條 dispatch_and_execute→真 registry→D3 contract_ver 斷言（鎖 regression）。

### no-regression（環境噪音已隔離）
- L2 全綠：P3a 48 + P2 orchestrator + critic = **172 passed**（親跑）。redactor bite 等 16 sink/inert/alpha test 全 run（非 skip）。
- 全樹 `tests/` 67 failed/4539 passed：**0 在 L2**。失敗 5 檔（api_contract/learning_chapter/product_family_business_settings/runtime_snapshot_bridge/snapshot_stable_entrypoint）**0 import P3a/L2 碼**（grep EXIT=1）；failure = `assert 403==200` + `engine.sock 未連` + `PG port 15432 Connection refused` = Mac sandbox 無 engine/DB 的 pre-existing 環境失敗（CLAUDE §六：真 runtime 在 Linux）。replay/ 4 collection error = `No module named 'program_code'` import-path artifact，pre-existing 無關。
- 教訓：**「executor 單元測試把 X 當參數注入並斷言被 thread」≠「X 的上游解析正確」**。本次 contract_ver 在 executor 層測得完美（注入 ml_advisory_diagnose.v1）卻遮蔽 orchestrator 傳 l2_contract.v1 的真相。provenance/版本欄這類「值由 caller 算、callee 只搬運」的欄位，**必須有一條 caller→真 registry→落庫值的端到端斷言**，否則 unit 注入會說謊。

## 2026-06-09 — L2 P3a contract_ver fix narrow re-review → PASS to E4（D3 bug 真閉、mutation-bite 驗證）

上輪 RETURN 的 LOW-2（真 D3 provenance bug：`dispatch_and_execute` 傳 `resolve_contract_versions(contract_ref=None)` → branch-3 generic fallback `l2_contract.v1`，D3 記錯 per-mode 契約）E1 已修。narrow re-review **只審此 fix**。

### ★ 兩 branch 收斂實測（PASS）
- 修法 `orchestrator:435-439`：`cap = self._registry_obj().get(capability_id)` 後傳 `cap.prompt_contract_ref`/`cap.output_schema_ref`。`_registry_obj().get()` 與 `dispatch():311-312` 同路徑同物件 → **同 registry 同 ref 同版本，解析等價**（非另開 registry）。
- **per-mode 機制澄清**：per-mode contract_ver 不是「一個 cap 內 mode 分支」，而是**兩個獨立 capability**——`ml_advisory.diagnose_leak` cap.prompt_contract_ref=`ml_advisory.diagnose_leak.v1`→`ml_advisory_diagnose.v1`；`ml_advisory.interpret_result` cap→`ml_advisory_interpret.v1`（TOML 兩 stanza 各一 ref）。`capability_id`→cap.ref→registry→contract_ver 鏈成立。
- executor 用 `mode`（`_MODE_CONTRACT_REF[mode]`:318）選**實際送 cloud 的 prompt template**；D3 contract_ver 用 orchestrator 傳入值（cascade 不 re-resolve，:603/627/729 忠實 thread）。consistent-pair（diagnose cap↔diagnose mode）下 D3 == 實際 prompt 契約 → **bug 真閉**。
- 實測 D3-recorded：diagnose→`ml_advisory_diagnose.v1`/`ml_advisory_schema.v1`；interpret→`ml_advisory_interpret.v1`/`ml_advisory_schema.v1`（`TestD3ContractVerProvenance` 5/5 PASS，對真 registry 非 inject）。`record_l2_call` 簽名顯式收 contract_ver/schema_ver（無 silent drop）。
- cap=None fail-soft：`(cap.prompt_contract_ref or None) if cap is not None else None`→generic fallback，防 registry reload race（防禦性；註解註明 cap 必非 None 因 dispatch 已 admit）=對。

### ★ mutation-bite 親驗（revert 真紅）
- 暫 revert fix（contract_ref=None/schema_ref=None）→ `TestD3ContractVerProvenance` **5/5 紅**（`AssertionError: 'l2_contract.v1' == 'ml_advisory_diagnose.v1'`=正是 bug）；restore 後 5/5 綠。**非空驗非遮測**。
- E1 自糾的 `test_mutation_bite_orchestrator_never_resolves_via_none_for_ml_advisory` 推理**正確且有 bite**：斷言「無任何 contract_ref=None 解析」而非「存在真 ref」——因 dispatch() 內部本就用真 ref 解析一次（:354-359），「存在真 ref」對 buggy 版也成立（0 bite）；bug 是 dispatch_and_execute **額外**一次 None 解析。revert→出現 None 解析→紅（已親驗在 5 紅內）。上輪 memory:5245 預判的 subtlety 被正確處理。

### scoped（PASS）
- contract_ver threading 改動限 `orchestrator:435-439`（re-fetch+resolve）+ `:444`（cascade 傳 resolved 值）。registry diff **0 `resolve_contract_versions` 邏輯改**（純 ADD 新 ml_advisory 契約=prior P3a，非本輪）。executor/sink/cost/cascade/M3/M4/coarse_subject guard/linchpin **0 改**（coarse_subject DoS 上輪已 review PASS、memory:5222/5237 確認未擾動）。
- P2 test 1 處改（`test_default_checked_in_toml_loads_p3a_stanzas_all_disabled`）=TOML 換 P3a 2 stanza 的合理後果，斷言全 enabled=false（fail-closed 保留）=對。
- 跨平台 0 硬編；0 except:pass/detail=str(e)；0 f-string log（exception 用 `%s`+fail-soft 再 raise，advisory 失敗減 L2 能力不阻 baseline=對）。

### no-regression（PASS）
- P3a **53 passed**（48 prior + 5 新 D3）；P2+critic+P3a **177 passed**；全 L2 surface（8 檔）**439 passed/4 xfailed**（xfail=strict bare/short 殘留，prior 已知）。replay/ 4 collection error=`No module named 'program_code'` pre-existing import-path artifact，無關。
- 0 production caller of `dispatch_and_execute`（grep 唯一 hit 是自身註解）⇒ 路徑 wired-but-dormant；cap/mode consistency 由未來 conductor 建立，本 fix 不引入新 hazard。

### 教訓（承上輪）
- provenance/版本欄「值由 caller 算、callee 搬運」**必須**一條 caller→真 registry→落庫值端到端斷言；本輪 E1 補的 5 test 正是此鎖。mutation-bite 對「caller 內部已有正確解析、bug 是額外錯誤解析」場景，**斷言點要選 buggy 版會違反的不變式（無 None 解析）**，不是「存在正確值」（會被內部正確解析遮蔽=0 bite）。
- 親跑 revert→紅→restore→綠 是驗 mutation-bite 非空的硬手段，不採信「test 有寫斷言」。

**verdict：E2 PASS to E4**（0 finding 待修）。

## 2026-06-10 · E2 review — OPS-2 Phase-2 cutover `a3d27729` (RETURN to E1)

**Verdict: RETURN**（1 HIGH + 1 MED + 1 LOW；production 代碼 0 defect，HIGH=漏掃 collateral 測試）。report: `workspace/reports/2026-06-10--ops2_phase2_cutover_review.md`。

**抓法（可複用）**：
- **base-vs-HEAD 全套失敗清單 diff** 是抓漏掃 collateral 的決定性手法：分支單 commit off base → `git checkout HEAD~1 -- <9 files>` 跑全套存 sorted FAILED 清單，還原 HEAD 再跑一次，`diff` 出唯一新增紅 = `test_strategist_promote_api.py::test_live_apply_all_gates_green_succeeds`（:574 注入 `OPENCLAW_IPC_SECRET` 當簽名 key，Phase-1 fallback 養出來的隱性依賴）。E1 只跑點名 5 檔（62 綠）就宣稱 collateral 清完 — **「受影響檔案清單」由 grep app-caller 推導必然漏「test fixture 對舊行為的隱性依賴」**，必須全套 sweep + 與 base diff（Mac 既有紅 66 條會淹沒肉眼，diff 才乾淨）。
- **雙語言 mutation 全 bite**：Rust panic gate 鎖 false → 指名測試紅；Python 重加 fallback → 3 條 cutover 定義性測試紅。新測試非遷就。
- **panic post-domination 結構分析**：spec §3.2 偽碼 gate `live_bindings.is_some()` 被 LIVE-GATE-BINDING-1 的 load_and_verify（try_spawn 內先 fail → live_bindings=None）post-dominate → 典型缺-key 啟動 panic 永不 fire，實際症狀=engine 起、live 拒 spawn、WARN kind deny-loop。實作=spec 逐字 → 定性為 PA advisory 非 E1 defect（fail-closed 完整 + §13.2 log-alert 可命中）。**教訓：fail-loud 聲明要追 gate 變數的 data flow 上游，「mirror 既有 pattern」可能 mirror 到不可達性**。
- 舊 fixture 對新代碼跑出 7 紅 = 親證 E1「collateral 紅」宣稱的最快手法（git show HEAD~1:file > 覆蓋 → 跑 → 還原）。
- E1 報告數字 2 處不符（watcher 15/15 實 12；signing 16 實 13；總數 62 對）— per-file 拆分宣稱要抽查。

**naming debt 裁決前例**：spec 兩 phase 欄都列的 rename（§4.1.1 `ipc_secret`→`live_auth_signing_key` param）+ 已有修復輪 → 裁 in-scope bundle 給 E1，不自修（PA 方案範圍內），不另開 debt ticket。

**§5 race**：origin/main 領先 3 commit 全 docs `[skip ci]` 0 overlap；3 條外來 stash 照例不動；mutation 後逐次 `git status --porcelain` 驗空還原。

## 2026-06-10 · re-E2 — OPS-2 cutover fix `cf1b9320` → ACCEPT (PASS to E4)

三項修復（HIGH env-key collateral / MED 4 處 param rename / LOW 註釋語義）全機械到位；diff 恰 3 檔 +11/−7 零漂移。親跑：promote_api 18/18 + 原紅單測綠；cargo lib live_authorization 24/24 + bin watcher 12/12 + cutover 3/3；`bash -n` 過。report 同檔追加 section（不開新檔）。

- **省 full-suite 的算術核驗法（可複用）**：E1「passed 4255→4256=淨增 1 測試」用 `git diff base..HEAD -- '*.py' | grep -cE '^\+\s*(async )?def test_'`（+6/−5=+1）零成本核實，不重跑全套；Rust flake 宣稱用 **total 不變性**核（上輪 4154+1=4155 = 本輪 4155+0，fix 0 新 test）。re-review 抽驗宣稱優先找這類 invariant。
- **rename 零 caller 影響實證**：Rust 位置參數 rename 理論不可能破 caller，但便宜實證 = 跑「唯一外部 caller 所在 test target」編譯+綠。注意 openclaw_engine **bin 名 `openclaw-engine`（連字號）**，watcher/cutover tests 都是 main.rs/src `#[cfg(test)]` mod 在 **bin target**（`--bin openclaw-engine <filter>`），不是 `--test` integration target（`--test` 會報 no target + 列可用清單）。
- **殘留字串域判定**：rename 後 grep `ipc_secret` 殘 6 處全 comment/負向測試名（IPC-transport 域概念引用）= 合法；抽 2 處讀上下文驗，不只看 grep 行。
- **5e 真 fire 案例**：review 中 L2 Mesh 7 commits 推上 origin/main（含 E2/memory.md +574 行 sibling 寫入）→ `comm -12` 比對 PR 11 檔 vs sibling 檔 = 0 overlap → verdict 不受影響、照 SOP 記錄不忽略。
- E1 本輪採上輪校正計數（watcher 12 非 15），數字 0 不符 → RETURN 輪揪 per-file 精度有效，re-review 輪信任度可升但仍抽驗。
