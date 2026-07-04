# P1-1 over-gate 複合體殘差分析與統一設計(PA,2026-07-04)

> 角色 PA;冷酷審計 R2 修復前置「取證/設計 wave」產出,直接餵實現 wave(E1/E1a/E4/E5)。
> 基線:Mac repo HEAD 含 3a050b60;Linux runtime checkout `3a050b60`(HEAD==origin/main,worktree clean,親測);engine PID 3159871 rebuild 自 3a050b60(IMPL-A/B+d0eeafb41 已上線);SSOT 已遷 `/home/ncyu/BybitOpenClaw/var/openclaw`。
> 本報告 fact / inference / assumption 分標;所有 FACT 帶 file:line 或 runtime 取證錨點。
> 【本任務零業務代碼改動;runtime 全程 read-only。】

---

## 0. 結論(≤10 行)

IMPL-A/B 上線後,四組件中 **CC exact-sha 批准循環=判準側已解(待 v739 實走)**、**QC TTL 12h=僅「安全側」已解,「吞吐側」殘留**、**FA plan-stale=完全未解**、**FA exact-head pin=僅手動止血(3a050b60 inline pin),自動派生未建=復發保證**。
v710-v738 拒真率 100% 的死循環由「四個獨立新鮮度判準 × 各自過期時鐘 × 全部需人工重走」疊乘而成;IMPL-A/B 只拆了其中一個乘數(批准後源漂移)。統一殘差設計核心=**把「人工介入」壓縮到唯一合法點(operator typed-confirm 簽名),其餘新鮮度維護全部自動化**,分五件套:①soak-window TTL 對齊(demo-only 放寬,簽名時 operator 顯式指定)②plan freshness 與 authority 解耦(簽名塊 byte-preserve 自動 re-materialization)③pin 隨部署自動派生 + drift-classify 公共 lib(復用 IMPL-B policy)④path/env 衛生收口(D3 遷移殘留 /tmp 默認 + Python/Rust plan path 不對稱)⑤refresh round ledger + soak 哨兵(讓「無人工介入」可量測)。live 5 gates 零觸碰;全部改動 demo learning lane 源碼側,0 Rust 改動,0 engine rebuild 需求。

---

## 1. 事實基線(重啟後新現實,2026-07-04 親證)

| # | 事實 | 證據 |
|---|---|---|
| B1 | engine PID 3159871 env:`OPENCLAW_DATA_DIR=/home/ncyu/BybitOpenClaw/var/openclaw`、`OPENCLAW_DEMO_LEARNING_LANE_PLAN=.../cost_gate_learning_lane/bounded_demo_probe_soak_plan.json`、`OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0`(soak 未武裝) | ssh `/proc/3159871/environ` 親讀 |
| B2 | Linux checkout `3a050b60`=origin/main,worktree clean(0 dirty) | ssh `git rev-parse HEAD origin/main`+`status --short` |
| B3 | crontab 現 7 條;5 條 learning lane 全帶 inline `OPENCLAW_EXPECTED_SOURCE_HEAD=3a050b60`(手寫字面量) | ssh `crontab -l` |
| B4 | canonical soak plan(新 SSOT 路徑)`generated_at=2026-06-30T21:43Z`(stale>24h);內嵌 bounded auth `expires=2026-07-01T09:02:17Z`(已過期);standing auth 檔 `expires=2026-07-01T17:16:05Z`(已過期) | ssh 親讀 plan JSON;TODO.md:16 |
| B5 | `/tmp/openclaw/cost_gate_learning_lane/` 遺留副本仍在(同名 plan/auth 舊檔) | ssh ls 親證 |
| B6 | probe_ledger.jsonl 490MB 仍無界(P1-10 另行處理,D3/D9 已批) | ssh ls -la |
| B7 | IMPL-A 已上線:soak gate `demo_learning_lane_soak_gate.rs`(三態圍欄)+dispatch withhold `step_4_5_dispatch.rs:49,894-940`;IMPL-B 已上線:`standing_envelope_post_approval_drift_gate.py`(695 行,policy `docs_tests_codex_exempt_v1`)+packet 生成器已 emit policy 字段(`current_candidate_e3_bb_signoff_request_packet.py:379`) | 源碼親讀+B1 世代證明 |

---

## 2. 四組件 × IMPL-A/B 覆蓋度映射(任務 1)

### 2.1 組件一:standing envelope TTL 12h 殘留側(QC F4)

**機制錨點(FACT)**:
- TTL 默認 12h/硬帽 24h:`standing_demo_authorization_refresh_guardrail.py:52-53`(`DEFAULT_AUTHORIZATION_TTL_HOURS=12`/`DEFAULT_MAX_AUTHORIZATION_TTL_HOURS=24`),越界拒絕 `:647-650`(`max_authorization_ttl_hours_exceeds_guardrail`)。
- 同名常量重複於 `standing_demo_loss_control_envelope_review.py:52-53`,但該檔支持上限實為 168h(`:546` `max>24*7` 才拒)。
- bounded probe auth:`bounded_probe_operator_authorization.py:70`(默認 max 24h)、`:684-685`(API 支持 [1,168]h);CLI 已有 `--max-authorization-ttl-hours` 參數(`bounded_probe_operator_authorization_cli.py:104-106`)。
- Rust 消費端 `validate_operator_authorization_envelope`(`demo_learning_lane.rs:783-834`)**只驗 expires>now,無 max-TTL 帽**——長 TTL envelope 引擎側天然可消費。

**IMPL-A/B 解到什麼程度**:
- ✅ **安全側已解**:過期=確定性 soak 退出。`SoakEnvelopeState::Expired→解除`+`last_good_expires_ms` 硬上界(檔被刪也在親簽時刻結束)(`demo_learning_lane_soak_gate.rs:54-79,106-110`);guard 與 admission 共用同一純函數判準(`demo_learning_lane.rs:776-782` 註釋+`soak_envelope_state :878-910`),判準漂移結構性不可能。
- ❌ **吞吐側未解**:TTL 12h(≤24h 帽)vs E3/BB exact-packet 週期(多小時-跨日)vs soak 窗 72h——v731 實例 envelope 剩 80.38s 到期(QC F4 `qc-full-repo-math-audit.md:46-55`);06-27 教訓 bounded TTL ~11h<72h soak 中途過期無人能續(設計正本 Part 3)。**每 12-24h 一次全鏈人工 refresh 的結構未變。**

### 2.2 組件二:plan-stale(FA F3 主體,87.6% 拒因)

**機制錨點(FACT)**:
- `max_plan_age_hours=24` 默認(`demo_learning_lane.rs:42`),判定 `plan_is_stale_or_missing_generated_at`(`:912-932`),admission 第 4 檢查即拒(`:644-652`,`PlanStaleOrMissingGeneratedAt`)。
- FA F3 量化:07-03 5h 內 12,646 筆 admission decision,`PLAN_STALE_OR_MISSING_GENERATED_AT`=11,075(87.6%),admitted=0(`FA/2026-07-03--full_repo_functional_audit.md:40-41`)。
- canonical soak plan 的**再生產者不存在**:全 repo grep `bounded_demo_probe_soak_plan` 僅 `bounded_demo_runtime_readiness.py`(讀者)+其測試——plan 是 refresh 鏈末端「preview materialization」人工/會話產物,無自動再生腳本(FACT:grep 0 producer)。
- cron 每小時再生的 `demo_learning_lane_plan_latest.json`(07-04 17:28 仍新鮮,親證)是**無 order authority 的自動 plan**,與 canonical soak plan 是兩個物種。

**IMPL-A/B 解到什麼程度**:
- ❌ **完全未解**。IMPL-A 刻意把 plan generated_at staleness 排除在圍欄判準外(`demo_learning_lane_soak_gate.rs:283-298` 測試註明「stale plan 下 admission 必拒一切,soak 窗口仍以親簽 expires 為準」)——這是正確的安全分工,但意味 admission 側 plan-stale 拒真在 IMPL-A/B 後原封不動:**即使 TTL 修好,24h 後 plan 過期照樣 100% 拒**。

### 2.3 組件三:exact-head pin 死循環(FA F4)

**機制錨點(FACT)**:
- pin=crontab 行內手寫字面量(現 `3a050b60`,B3);消費鏈三態不一:
  - 真消費+fail-close:`demo_learning_evidence_audit_cron.sh:30,140-141`→`demo_learning_evidence_audit.py:224-232`(mismatch→`RUNTIME_SOURCE_SYNC_REQUIRED_BEFORE_COST_GATE_CHANGE` 全面 block);`demo_learning_stack_healthcheck_cron.sh:23,81-83`→`demo_learning_stack_healthcheck.py:143-155,391-400`(mismatch→`runtime_source_not_clean_or_expected_head_mismatch` 不健康);`alpha_discovery_throughput_cron.sh:24,475-479`。
  - **惰性 pin(假防線)**:`sealed_horizon_probe_preflight_cron.sh` 與 `ml_training_maintenance_cron.sh` 的 cron 行帶 `OPENCLAW_EXPECTED_SOURCE_HEAD` 但腳本內 **0 消費**(grep 0 hits)——pin 幻覺。
  - 安裝腳本僅裝機時要求 pin 非空(`install_cost_gate_learning_lane_cron.sh:147` 等)。

**IMPL-A/B 解到什麼程度**:
- ❌ **未解,僅運維窗口手動止血**。下次部署(或 codex 直駕在 Linux checkout 前進)pin 即再度 stale→lane 再凍→FA F4「06-24 已修類別復發」第三次應驗。TODO.md:39 亦標「殘餘:pin 自動派生(B1/B2 resume)」。

### 2.4 組件四:exact-sha 批准循環(CC)

**機制錨點(FACT)**:
- 舊判準:Step 1 final check=approved_head 與 origin/main 逐位相等,codex 高頻 commits 下 28 輪(v710-v738)100% ROTATED(TODO.md:17 v738 終態;QC F4:49)。
- IMPL-B 新判準(`standing_envelope_post_approval_drift_gate.py`):deny-by-default 四步分類(hard-deny `:69-91`→tests 豁免→docs/.codex 豁免→默認 ROTATED),EXEMPT=`POST_APPROVAL_DRIFT_EXEMPT_APPROVAL_STILL_VALID`(`:49`);packet 需內嵌 `post_approval_drift_policy` 字段且 sha256 相符(`:381-414,441-454`);EXEMPT 延續必須從 approved-head clean detached worktree 執行(`:602-607`);worktree dirty/HEAD≠origin 降為僅記錄。v734 collector 假陰性(binary rename/gitlink/symlink)已由 `db80212f4` 關閉(`standing_envelope_source_impact_guard.py` mode-aware)。

**IMPL-A/B 解到什麼程度**:
- ✅ **批准後漂移側已解(源碼已上線,v739 實走待驗)**——docs/tests/.codex-only 前進不再作廢批准。
- ⚠️ **殘留三點**:(a)**pre-approval 側未動**:`source_stability_window_guard.py` 仍要求兩樣本 exact-sha 相等+worktree 全 clean+HEAD==origin/main(`:167-171,195-204`)——當前 B2 狀態可過,但 codex 直駕恢復時 quiet window 可被高頻 docs commits 反覆打斷(與 IMPL-B 豁免哲學不一致);(b)首次 v739+ 使用前需 **one-time E3/BB 對 policy 條款簽核**(TODO.md:44,程序性);(c)非豁免類漂移仍 ROTATED=**設計如此**(fail-closed 正確),驗收判準必須把它計為「真 fail-close」而非拒真。

### 2.5 覆蓋度總表

| 組件 | IMPL-A | IMPL-B | 重啟上線後淨狀態 |
|---|---|---|---|
| QC TTL 12h | 安全側解(過期=確定退出) | 間接縮短批准週期 | **吞吐側殘留**:12-24h 人工 refresh 節拍不變 |
| plan-stale | 無(刻意分工排除) | 無 | **未解**:24h 後 admission 100% 拒 |
| exact-head pin | 無 | 無 | **未解**:手動 pin 3a050b60,復發保證+2 條假 pin |
| exact-sha 批准 | 無 | **判準側解** | 待 v739 實走;pre-approval quiet window 殘留 |

---

## 3. 殘差清單(任務 2;RES 編號供實現 wave 引用)

**TTL 12h 殘留側是否已解:未解(吞吐側)。** envelope 過期的「危險」已由 IMPL-A 變成確定性安全退出,但「過期後恢復學習」仍需全鏈人工 refresh;12h 默認 TTL 決定了節拍。

**envelope refresh 仍需人工介入的環節(全枚舉)**:

| # | 環節 | 性質 |
|---|---|---|
| RES-1 | operator typed-confirm 簽名(standing guardrail 運行+bounded auth CLI `--typed-confirm`) | **合法且不可消除**(治理鐵則:授權=人簽);但頻率可由 12-24h/次 → 每 soak 窗 1 次 |
| RES-2 | canonical soak plan 過期(24h)後的 re-materialization——無自動再生腳本,靠 PM 會話手工 | 可自動化(§4.B) |
| RES-3 | refresh 鏈 ~10 步人工 shepherding(fetch→quiet window ×2 樣本→packet 生成→E3/BB 派發→Step 1 兩段檢→detached worktree→fast-balance `--forbid-env-token`→readiness `--redact-secret-derivatives`→guardrail `--allow-expired-standing-auth-readiness-only`→materialization→post-validation;TODO.md:44 全 prose) | 可腳本化(§4.E orchestrator);E3/BB 審查本身留 agent |
| RES-4 | 部署後 crontab pin 手動重寫 | 可自動化(§4.C=P1-4) |
| RES-5 | soak 再武裝=engine env `OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=1`+重啟(env 進程級固定,`step_4_5_dispatch.rs:68-74` 讀進程 env) | operator 窗口動作,保留(kill-switch 對稱性) |
| RES-6 | one-time E3/BB policy 條款簽核(v739 前) | 程序性,一次性 |

**遷移/對稱性殘留(D3 後新增,v739 實走危害)**:

| # | 殘差 | 錨點 | 危害 |
|---|---|---|---|
| RES-7 | lane 腳本硬編碼 `/tmp/openclaw` 默認:`bounded_demo_runtime_readiness.py:36-41`(DEFAULT_PLAN_JSON/DEFAULT_STANDING_AUTH_JSON)、`standing_demo_authorization_refresh_guardrail.py:56-58`(DEFAULT_RUNTIME_ENVELOPE_PATH)——非 OPENCLAW_DATA_DIR 派生 | 親 grep;/tmp 遺留副本仍在(B5) | refresh 鏈默認參數會讀/寫 /tmp 舊檔,engine 讀新 SSOT→**雙真相分裂**,v739 直接踩 |
| RES-8 | Python/Rust plan path 不對稱(E4 F3 實錘):Rust 尊重 `OPENCLAW_DEMO_LEARNING_LANE_PLAN` env(`demo_learning_lane_writer.rs:41,211-231`);Python `runtime_adapter.py:695-697` 默認 `demo_learning_lane_plan_latest.json` 且**不讀該 env** | 親 grep | 引擎消費 soak plan、Python adapter 消費 hourly plan→兩實現對賬失義 |
| RES-9 | §1.4 soak 哨兵(武裝中 N 小時零 admission 活動告警)設計了未實作(E4/TW F6:withhold/Indeterminate 無消費者) | IMPL-A commit 無哨兵;grep healthcheck 無 soak 軸 | over-gate 誤殺不可觀測 |
| RES-10 | 惰性 pin ×2(sealed_horizon/ml_training cron 行帶 pin 腳本不消費) | §2.3 | 治理幻覺;審計誤判「有防線」 |

---

## 4. 統一殘差設計(任務 3;單一方案,禁零敲碎打)

### 設計原則
把 v710-v738 的失敗抽象成一句話:**四個新鮮度時鐘(標準 envelope TTL、plan generated_at、cron pin、批准 sha)各自獨立過期,且每個過期都要人工重走全鏈**。統一設計=「一次 operator 簽名定義整個 soak 授權窗;窗內所有新鮮度維護自動;窗外/越權/存疑一律 fail-closed」。授權(operator 簽名,不可自動)與新鮮度(數據時效,必須自動)嚴格解耦。

### A. soak-window TTL 對齊(demo-only 放寬;Demo 放寬/Live 收緊政策內)
- `standing_demo_authorization_refresh_guardrail.py` 新增 `--soak-window-hours N`(1..96):設定時 `authorization_ttl_hours=N`,max 帽檢查改用新常量 `SOAK_MAX_AUTHORIZATION_TTL_HOURS=96`(=72h soak+24h margin;PA 小決策,理由:`bounded_probe_operator_authorization.py:684` API 天花板 168h 內取保守半值,QC F4 fix 方向「TTL≥2× p95 refresh-cycle」滿足);**未設此參數時 12/24 默認完全不變**(非 soak refresh 不放寬)。envelope payload 記錄 `soak_window_hours` 與理由字段,審計可見。
- bounded auth:CLI 已支持 `--max-authorization-ttl-hours`≤168,**零代碼改動**,operator 簽名時傳同窗值;typed-confirm 模板改為內嵌 TTL 小時數(簽名字符串顯式含「96H」類 token),使放寬逐次顯式。
- **全鏈一致性 AC(E4)**:以 72h TTL 簽出的 envelope 走 review(`standing_demo_loss_control_envelope_review.py`)/readiness/guardrail/Rust admission 全鏈 accept——防某環節殘留 24h 硬帽(已知 review `:546` 支持 168h、Rust 無帽,但必測實走)。
- **不碰**:live 5 gates、`authorization.json`(live 簽署路徑)、`bounded_probe_operator_authorization_cli` 簽名語意(仍 typed-confirm 人簽,禁腳本代簽)。

### B. plan freshness 與 authority 解耦(自動 re-materialization)
- 新腳本 `helper_scripts/research/cost_gate_learning_lane/soak_plan_rematerializer.py`:
  - 輸入:canonical plan 路徑、standing envelope、scorecard latest。
  - 前置全 fail-closed:envelope 有效(未過期/schema 對)∧ 內嵌 operator_authorization 塊 **sha256 逐字節不變**(byte-preserve,禁任何欄位重寫)∧ side_cell_key/caps/order_authority 與簽名一致 ∧ 以 fresh scorecard 重跑候選選擇後該 side_cell 仍被選中。任一不成立→no-op+告警 artifact(不 rotate、不改檔)。
  - 動作:僅重生 plan wrapper 的 `generated_at_utc` 與候選數據快照,原子寫回(temp+rename,0600)。
  - **為何合法**:授權由簽名塊的 expires_at 硬界定(re-wrap 不延長任何 authority);plan 24h staleness 的保護目的(候選/scorecard 數據時效)由「重跑候選選擇+fresh scorecard」保留;安全兜底(ledger disable rows/risk_state/budget)全在 admission 鏈獨立生效(`demo_learning_lane.rs:690-737`)。不觸「不得手寫 authorization」鐵則——簽名塊只搬運不生成。
  - 接線:`cost_gate_learning_lane_cron.sh` 新步驟,flag `OPENCLAW_COST_GATE_REFRESH_SOAK_PLAN`(默認 0,soak 期由 operator 開)。
- **替代方案已評估並否決**:把 `max_plan_age_hours` 調到 96——否決理由:staleness 保護的是候選數據時效(真實價值),一刀切放寬=丟保護;解耦方案兩者兼得,LOC 相當。

### C. P1-4 pin 隨部署自動派生 + 世代判準公共 lib(統一組件三/四判準)
- **pin SSOT 檔**:`$OPENCLAW_DATA_DIR/runtime_generation/expected_source_head.json`(`{head, derived_at_utc, writer, base_dir}`,原子寫)。
- **派生點(寫者,恰兩個)**:①`restart_all.sh` 每次成功啟動服務後(不限 --rebuild)以 `git -C $BASE rev-parse HEAD` 派生;②新單檔 `helper_scripts/deploy/derive_expected_source_head.sh`(source-only 部署——lane 是 Python,git pull 即部署,無 engine 重啟時用;pull SOP 尾接一行)。
- **消費端統一**:新公共模組 `helper_scripts/research/cost_gate_learning_lane/source_generation.py`(D6+D7 已授權 learning-lane 公共 lib 方向):
  - `resolve_expected_source_head()`:env 鏈(既有變量名不變,向後兼容)→ pin 檔 → None。
  - `classify_source_generation(repo_root, expected_head)` → `MATCH` / `DRIFT_EXEMPT` / `DRIFT_ROTATED` / `INDETERMINATE`:mismatch 時對 `expected..HEAD` 跑 **IMPL-B 同一分類器**(import `standing_envelope_post_approval_drift_gate` 的分類函數,**禁複製豁免表**——單一 policy SSOT);docs/tests/.codex-only 前進→`DRIFT_EXEMPT` 放行+記錄;任何 hard-deny/默認類→`DRIFT_ROTATED` fail-close;git 命令失敗/pin 缺失但 lane 要求 pin→`INDETERMINATE` fail-close。
  - 三個真消費 lane(evidence_audit/healthcheck/alpha_discovery)改走公共 lib;`MATCH|DRIFT_EXEMPT` 綠、其餘照舊 fail-close 語意不變。
- **crontab 收口**:install 腳本去掉 inline SHA(pin 從檔解析);兩條惰性 pin(RES-10)——sealed_horizon preflight 補真消費(走同 lib),ml_training cron 行刪掉無效 env(誠實化)。
- **為何 drift-classify 而非純 pin 檔**:純 pin 檔只解「部署後忘改 crontab」;復發主因是 **codex 直駕在 Linux checkout 前進**(422 commits 教訓)——docs/.codex 前進不應凍 lane,這正是 operator 已批准的 IMPL-B 放寬條款,對 pin 復用=同一policy 治理兩個判準面,不另設第二套豁免規則。

### D. path/env 衛生收口(RES-7/RES-8)
- RES-7:`bounded_demo_runtime_readiness.py:36-41`、`standing_demo_authorization_refresh_guardrail.py:56-58` 的 `/tmp/openclaw` 字面默認改 `OPENCLAW_DATA_DIR` 派生(鏡像 `policy.py:823` 既有慣例);其餘 7 檔已是 env-default 慣例僅逐檔複核。跨平台準則同時滿足(不硬編碼 Linux 路徑)。
- RES-8:`runtime_adapter.py` `_default_plan_path` 補 `OPENCLAW_DEMO_LEARNING_LANE_PLAN` env 優先(語意=Rust `demo_learning_lane_writer.rs:211-231` 逐位鏡像,含空白 trim/空串回退);`bounded_probe_plan_inclusion_review.py` 同批複核。E4 加 Rust/Python path 解析 parity 測試(P1-8 golden-vector 家族的一員)。

### E. 觀測面:refresh round ledger + soak 哨兵(RES-3/RES-9;驗收判準的量測基礎)
- 新 `helper_scripts/research/cost_gate_learning_lane/refresh_round_orchestrator.py`:把 TODO.md:44 的 prose SOP 碼化為確定性步驟機(fetch→quiet window 兩樣本→packet 生成→**停:E3/BB 審查**→Step 1 兩段檢(sha 相等 pass;前進跑 drift gate)→**停:operator 簽名**→detached worktree 步驟→fast-balance/readiness/guardrail/materialization/post-validation),每步結果 append `refresh_round_ledger.jsonl`(round_id、步驟、耗時、人工介入標記、終態)。兩個「停」是僅有的人類/agent 交接點;其餘任何人工繞行都會在 ledger 缺步驟=可審計。deterministic routing 進代碼、判斷留人/agent(Operating Style #5)。
- soak 哨兵(設計正本 §1.4 補欠):`demo_learning_stack_healthcheck.py` 新軸——soak 武裝中(flag=1∧envelope Active)而滾動 N 小時 admission decision 分布全空或 withheld/candidate 比異常→WARN;**判據用 admission 結果分布,禁用 probe_ledger 有無新行**(§1.4 評審實證 capture-error rows 會餵飽行數使哨兵失明)。

### 降級 / rollback 路徑(設計完成必要件)
- 全部改動 additive/參數門控:A(`--soak-window-hours` 不傳=舊行為)、B(cron flag 默認 0)、C(env 鏈優先於 pin 檔——crontab 現存 inline pin 在割接完成前繼續生效;drift-classify 僅在 mismatch 時才介入,行為包絡=舊 fail-close 的放鬆而非收緊,rollback=lane 改回直接比對)、D(默認值變更,CLI 顯式傳參者不受影響)、E(純新增觀察面)。
- rollback=逐 commit `git revert`(無 schema/migration/IPC 變更;0 Rust 改動→無 rebuild;crontab 由 `~/BybitOpenClaw/var/crontab_backup_20260704T_pre_window.txt` 可整表還原)。
- kill-switch 不變:`OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED=0` 全滅 soak;`OPENCLAW_COST_GATE_REFRESH_SOAK_PLAN=0` 停自動 re-materialization。
- 失敗方向自檢:每件套的存疑態(pin 檔壞/JSON 壞/git 失敗/簽名塊 sha 不符/候選變更)全部收斂到 fail-close+告警,無一 fail-open 邊。

---

## 5. E1 派發計劃(檔零重疊;PM 掌時序)

| 任務 | 檔案 | 內容 | 依賴 |
|---|---|---|---|
| E1-A | `standing_demo_authorization_refresh_guardrail.py`+其測試 | §4.A soak-window TTL 參數+§4.D 該檔 /tmp 默認修+typed 證據字段 | 無 |
| E1-B | `source_generation.py`(新)+`demo_learning_evidence_audit_cron.sh`/`demo_learning_stack_healthcheck_cron.sh`/`alpha_discovery_throughput_cron.sh`/`sealed_horizon_probe_preflight_cron.sh`/`ml_training_maintenance_cron.sh`+install 腳本+tests | §4.C 公共 lib+pin 檔解析+惰性 pin 收口 | 無(import IMPL-B 既有分類函數) |
| E1-C | `soak_plan_rematerializer.py`(新)+`cost_gate_learning_lane_cron.sh`+tests | §4.B | 無 |
| E1-D | `restart_all.sh`+`helper_scripts/deploy/derive_expected_source_head.sh`(新)+`SCRIPT_INDEX.md` | §4.C 派生點 | 無 |
| E1-E | `bounded_demo_runtime_readiness.py`+`runtime_adapter.py`+`bounded_probe_plan_inclusion_review.py`+tests | §4.D 其餘 path/env 收口 | 無 |
| E1-F | `demo_learning_stack_healthcheck.py`+tests;`refresh_round_orchestrator.py`(新) | §4.E | 無 |
- Wave 1 全六件並行(檔互不重疊;`SCRIPT_INDEX.md` 僅 E1-D 觸,其餘新腳本登記由 E1-D 統一收尾或 PM 收口時一次補)。
- Wave 2(串行):E4 全鏈回歸(§6 AC)→ E3/BB one-time policy 條款簽核(RES-6)→ v739 實走。
- **前置紅線**:P1-8 contract test 是 v739 放行前置(TODO.md:5),不在本設計範圍但序在 E4 同批。

## 6. E2 重點審查 3 點

1. **E1-C rematerializer 的簽名塊 byte-preserve 與 refuse-on-delta**:任何 authority 欄位重寫/candidate 漂移下重簽=災難類(等同腳本代簽授權);必雙向 mutation 自證(篡改一個欄位→必 no-op+告警)。
2. **E1-B drift-classify 的 fail 方向與 policy SSOT**:豁免表必須 import IMPL-B 模組,repo 內不得出現第二份豁免清單;git 失敗/pin 缺失/解析失敗全部 fail-close;`DRIFT_EXEMPT` 放行必留記錄 artifact。
3. **E1-A TTL 放寬的作用域封鎖**:`--soak-window-hours` 不傳時 12/24 默認逐位不變;放寬路徑不可達 live/live_demo 授權面(本 lane 為 demo envelope,E2 逐字驗無 live 字面滲漏);typed-confirm 含 TTL 小時 token。

## 7. v739 驗收判準(任務 4;可量測,round ledger 為證據源)

**Round 定義**:一次完整 refresh 週期(orchestrator round_id 界定:fetch→…→post-refresh validation 終態)。

**單輪 PASS(全滿足)**:
1. 人工介入=僅兩個合法停點(E3/BB 審查、operator 簽名);round ledger 無缺步驟、無 ledger 外手工動作(自報+ledger 交叉)。
2. Step 1 若遇源前進:豁免類→`POST_APPROVAL_DRIFT_EXEMPT_APPROVAL_STILL_VALID` 延續成功(**0 次豁免類 ROTATED=拒真清零**);非豁免類→ROTATED 且事後複核分類正確(≥1 個真 hard-deny/默認類路徑)=**計「真 fail-close」,不算輪失敗,round 重啟**。
3. 產出 envelope TTL ≥ 本輪聲明的 soak 窗;runtime plan/auth 落新 SSOT 路徑、mode 0600、engine env plan path 一致(readiness `engine_env_plan_path_mismatch` 綠)。
4. envelope 有效期內 admission decision 中 governance-freshness 拒因(`PLAN_STALE_OR_MISSING_GENERATED_AT`+`OPERATOR_AUTHORIZATION_*` 過期類)佔比 <1%(基線 87.6%);soak 哨兵綠。

**總判準**:v739 起**連續 3 輪 PASS**(3 輪=初次 refresh+至少 2 次跨 24h 邊界的自動 plan re-stamp 或後續 renewal checkpoint,即必須實證跨越舊 plan-stale 死點),或每次 fail-close 均複核為真判準(2 類:非豁免代碼漂移/真 blocker),期間 0 次豁免類拒真、0 次 pin 凍結(checkout==部署世代時 lane 全綠)。

**QC 淨貢獻翻正量法**(按 `feedback_goal_oriented_review` 計價,QC 出具):
- **淨貢獻 = 避免虧損 − 誤殺 − 摩擦**,窗口=soak 起訖:
  - 避免虧損(gate 保護價值):envelope caps 實際約束驗證——probe 訂單數 ≤ 簽名 budget(≤`HARD_MAX_AUTHORIZED_PROBE_ORDERS=3`)、realized loss ≤ 損控帽、0 次越權放行(demo 語境下本應≈0,若>0 即 gate 正貢獻實錘)。
  - 誤殺(拒真流量):armed 窗內 governance-freshness 拒因筆數×該 cell 反事實學習價值;基線=11,075 筆/5h、admitted=0、28 輪零 probe outcome;目標=govern-freshness 拒因 <1% 且 `probe_outcome` rows ≥1(帶真 fill 數據,承 P1-2 保守成本模型)。
  - 摩擦(人工成本):operator 簽名次數/soak 窗(基線≈每 12h 一次全鏈;目標=1)+expiry→fresh envelope 墙鐘(目標 <TTL/4)+PM shepherding 步驟數(ledger 計,目標=2 停點)。
- **翻正宣告條件**:三項合成為正(誤殺、摩擦項趨近 0,保護項未鬆動),由 QC 以 round ledger+probe_ledger admission 分布+fills 對賬出具,不得以「輪次通過」自動視同翻正。

## 8. 副作用清單與硬邊界確認

- **副作用**:①cron 行為變化僅在 pin-mismatch 分支(舊=必 fail-close,新=豁免類放行+記錄)——監測面 WARN 語意變化需在 healthcheck 文檔標注;②`runtime_adapter.py` 默認 plan 換 env 優先後,離線對賬腳本若依賴舊默認需同步(E1-E caller 盤點:grep `--plan` 調用點);③crontab 去 inline pin 需與 P0-2 FA 對帳 resume(`wf_8c488f52-f7c`)協調,避免互踩 crontab(PM 序控);④orchestrator 引用的各腳本 CLI 形態=today 之 FACT,E1-F 落地前逐一 `--help` 重驗(prompt 數字 6h 即漂移教訓)。
- **硬邊界(16 根原則快掃)**:live 5 gates(`live_reserved`/Operator auth/`OPENCLAW_ALLOW_MAINNET`/secret slot/`authorization.json`)**零觸碰**(全改動位於 demo learning lane helper_scripts+restart 腳本;grep 指紋面 `live_execution_allowed|max_retries|system_mode|authorization\.json` 在改動集 0 命中預期,E2 複掃);原則 4(admission 鏈不繞 Guardian/risk_state 檢查原封)、5/6(全存疑態 fail-close)、7(學習不寫 live)、8(round ledger 強化可重構性)、10(本報告 fact/inference 分標)、11(設計目的=硬邊界內自主性恢復)合規。原則 13 不涉。
- **NEEDS_CONTEXT/待證實(不作 P0/P1 阻塞結論)**:①`alpha_discovery_throughput` runtime_runner pin-mismatch 的具體 block 範圍(僅讀 :475-479 傳參,未逐行讀 4500 行 runner 的消費分支——E1-B 落地時親讀);②soak 哨兵閾值 N 小時(建議 6h,QC/MIT 定案);③96h 帽值 operator 可在簽名時否決(TTL 本就是逐簽輸入,帽只是允許)。

## 9. 代碼足跡與持續開發成本

- 預估 LOC:新增 ~700(source_generation ~120/rematerializer ~180/orchestrator ~250/derive 腳本 ~40/哨兵軸 ~60/pin 檔寫入 ~50)+改動 ~250(guardrail ~60/5 cron shells ~80/install ~40/path 收口 ~40/healthcheck cron ~30)+測試 ~450。合計 ~1,400。
- 觸及熱檔:`restart_all.sh`(914 行,+~50)、`cost_gate_learning_lane_cron.sh`(+~25);均遠離 2000 帽。**不觸** `status.py`(2238,超標熱檔)與任何 Rust 檔(0 rebuild)。
- 臃腫辯護:orchestrator 250 行換掉 TODO.md:44 巨型 prose SOP 的每輪人工執行+驗收可量測性,屬 token 稅負轉正;rematerializer/公共 lib 消除的是每 24h/每部署的重複人工,按重複成本計價為正。等效更薄方案(只調 max_plan_age_hours+手冊)已在 §4.B 否決並給理由。

## 10. 交接

- PM:派發 Wave 1(六 E1 並行)→E2(§6 三點)→E4(AC:TTL 全鏈一致/re-stamp 跨 24h 綠/pin drift-classify 矩陣/path parity)→E3/BB one-time 簽核→v739 實走(P1-8 前置)。
- QC:§7 淨貢獻量法認領;probe 反事實成本與 P1-2 同批。
- 與 P0-1 B1(boot/build SHA 可觀測面)協同:pin 檔與 boot SHA 同目錄 `runtime_generation/`,healthcheck 可三方對表(pin vs checkout vs engine build SHA)。

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-04--overgate_residual_unified_design_p11.md
