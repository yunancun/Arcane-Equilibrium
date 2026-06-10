# P5-SM-OPTION2 step-(i) Soak 監測面重設計（第二輪）— DESIGN-ONLY

- Date: 2026-06-10
- Author: PA
- Repo: srv @ `aeae4da4`（branch `feature/l2-critic-lessons-tools`，含他人 L2 WIP；本設計 0 代碼寫入）
- Status: DESIGN-ONLY，待 PM/operator 裁定後派 E1
- 承接: `2026-06-02--sm_option2_convergence_migration_design.md`（原始遷移設計）+ 2026-06-03 B-3 第一輪 soak 觀測鏈（commits `b904125f` → `87047e32` → `b847ae28`）+ operator (b)+(b-i) gate rework（2026-06-03）

## Executive Summary（5 行）

1. **Brief 過時一半**：2026-06-03 已有一輪 soak 重設計落地（V129 PG 投影 + flusher + `[81]` SQL healthcheck + sampler 棄用 + operator 拍板 gate rework (b)+(b-i)：comparator 降為觀測、gate = 4a CI 綠 AND P-LIVE）。brief 的問題 #2（讀法缺口）已解、#1（空轉偽 pass）已被 gate 重定義解、#3（flag 易失）機制已在（`restart_all.sh:717` 讀 `basic_system_services.env`）但未被使用且無斷點偵測。
2. **真正殘留缺口 = Python→IPC→Rust 生產管線零 runtime 曝險**：P-LIVE 只證 Rust 內部路徑活著，4a 只證 SM 邏輯等價；7 個 IPC dispatch arm（cutover 後 Python 控制面的唯一依賴）在生產環境 organic≈0 次被呼叫。
3. **推薦方案 = 唯讀 IPC canary（in-process、leader-elected、300s 一拍）+ epoch/flag 事件帳本（小 migration）+ `[82]` soak-window 評估 check + 運維 SOP（soak 期 flag 寫入 `basic_system_services.env`）**。不重建雙邊 divergence gate（結構性語意不可達，見 §2.4）。
4. **新 gate（S1-S5）**：4a CI 綠 + `[81]` P-LIVE 全程綠 + canary ≥48h 連續有效窗、≥500 probe、結構成功率 ≥99%、無 ≥15min 失敗連段 + flag 全程 ON（任何 OFF 觀測 = soak invalid 自動重置錨點）+ 收口時 operator 一次性 mutating IPC smoke（N≥10 acquire/release）。
5. **E1 規模：5 個 task、3 個 wave、約 2-3 個工作天**（1 小 migration + canary 模組 + flusher 擴充 + `[82]` check + SOP/smoke script）；0 Rust 改動、0 live-auth 5 閘接觸、0 新 HTTP/CSRF 面。

---

## 0. 現實修正（brief vs 當前 HEAD，全 grep/git 親證）

本節是本報告最 load-bearing 的部分：brief 描述的是 2026-06-03 PM 發現問題「當下」的狀態，但同日稍晚已有一輪修復落地。**設計若照 brief 字面做會重複建設三件已存在的東西。**

### 0.1 已存在的觀測鏈（brief 未提及）

| 資產 | 位置 | 落地 commit | 狀態 |
|---|---|---|---|
| V129 PG 投影表 `learning.lease_ipc_divergence_snapshot` | `sql/migrations/V129__lease_ipc_divergence_snapshot.sql` | `b904125f`（V128）→ `b847ae28`（renumber V129） | 表設計含 freshness 權威 `updated_at` + `flag_enabled` 欄；TEXT `snapshot_key` 明文保留多 key 擴充 |
| Counter→PG flusher（30s、flock leader-elected、fail-soft） | `app/governance_divergence_flush.py`；wire 於 `main.py:585-605` startup | `b904125f` | 解 brief #2「total 只能經 CSRF-gated GUI 讀」——cron 已可 SQL 讀 |
| SQL healthcheck `[81] lease_ipc_soak` | `helper_scripts/db/passive_wait_healthcheck/checks_governance_lease_ipc.py`；runner 註冊 `runner.py:191-202` | `b904125f` + rework `87047e32` | gate 唯一條件 = **P-LIVE**（V054 `lease_transitions` 表在 + 有 row + 最新 row age <3600s，fail-closed FAIL 非 WARN）；comparator counter 降為觀測欄（讀不到不致 FAIL） |
| EQUIV sampler（歷史 row 回放驅動 comparator） | `helper_scripts/db/lease_ipc_equiv_sampler.py` | `b904125f` 建、`87047e32` **DEPRECATED** | **operator 拍板 (b)+(b-i)（2026-06-03）**：Option 2 下「歷史 Rust-GRANTED row 對撞 Python hub 當前 auth state」語意不可達 → 永久卡死 gate；檔案保留僅防重寫同一設計 |
| flag 跨 restart 持久機制 | `helper_scripts/restart_all.sh:716-717`：operator-env 優先，否則讀 `$SECRETS_ROOT/environment_files/basic_system_services.env` | `e6aa5e37`（E1b 本體） | **機制自 step-i E1b 起就在**；兩次 soak 終結（06-03/06-07）是因 flag 以 operator-env 一次性設定、未寫入 env 檔（TODO.md:14「flag revert OFF 如預期」自證） |

### 0.2 brief 引用行號核對（當前 HEAD）

- `governance_divergence.py:33` gate 公式 — ✅ 仍在（MODULE_NOTE 行 32-33），但**它只是 docstring 殘文**：真 gate 已被 `[81]` rework 取代為 P-LIVE-only。該 MODULE_NOTE 與 `governance_extended_routes.py:424-429` 的「soak 查 0 divergence over N」註解均為 **stale 文字**（cleanup debt，E1-E 順手修註解）。
- `hub.py:933/1053/1179` `record_divergence` 三觸點 — ✅ 全對（933=A1 auth-axis 於 `_compare_auth_axis`；1053=acquire scope-axis；1179=release presence-axis；另 1245=get）。
- `executor_agent.py:554` 主 caller — ✅ 對，但**比 brief 更糟**：shadow 默認時 `acquire_lease` 在 **Step 1 SHADOW_BYPASS 短路（hub.py:990-1001）**，連 Step 1.5 auth-axis 比對都不會跑 → shadow 流量對 comparator 貢獻**恰好為 0**，非「少」。organic≈0 是結構性的（paper 亦默認 OFF）。
- Rust dispatch arms — ✅ 7 個全在：`ipc_server/dispatch.rs:362-372`（acquire/release/get_lease/is_authorized/get_status/list_leases/get_risk_state）。
- **Python client 端只有 4 個 METHOD 常數**（`lease_ipc_schema.py:69-81`：ACQUIRE/RELEASE/GET/IS_AUTHORIZED）；`get_status`/`get_risk_state`/`list_leases` 的 Rust arm 存在但 **Python client 尚未建** —— 影響 canary 軸選擇（§3.2）。
- `TODO.md` §5 row 75（P5 條目）**整條 stale**：仍寫舊 comparator gate + 「soak RUNNING」；未反映 (b)+(b-i) rework 與 06-07 二次終結。PM 須更新。

### 0.3 結論：本輪要解的不是 brief 的三個問題，而是三個殘留缺口

- **G1（最 load-bearing）**：Python→IPC→Rust 生產管線（7 dispatch arm + PipelineCommand round-trip + serde + socket auth + fail-closed timeout）**零 organic runtime 曝險**。P-LIVE 不覆蓋它（`lease_transitions` 由 Rust 內部 event_consumer 寫，不經 IPC arm）；4a 不覆蓋它（離線邏輯 parity）。**step-iii 刪掉 Python SM 後，Python 控制面所有治理讀寫全騎在這條管線上**；若它在生產有微妙故障（event-loop dispatch、serde 漂移、socket auth、timeout），cutover 當天 Python 全面 fail-closed = 自製控制面停擺。
- **G2**：soak 窗連續性無人記帳——counter 是 process-local 記憶體（restart 歸零）、V129 是 current-value UPSERT（無歷史）、`[81]` 是 point-in-time 判定（無「連續 48h 綠」概念）、flag 狀態變遷無 append-only 痕跡。
- **G3**：flag-OFF 無告警、soak-invalid 無自動標記。env-file 持久機制在但 SOP 未用；6h cron 只寫 log 檔（exit code 無消費者——與 canary_events.jsonl 同病）。

---

## 1. 問題重述（修正後）

step-(i) 的 soak 要回答兩個問題：

- **Q-EQUIV**：Rust SM 與 Python SM 邏輯等價嗎？——**已由 4a contract test（190-vector、兩獨立實作、CI 物）回答**，operator (b)+(b-i) 已把它定為 P-EQUIV 的 authoritative proof。runtime comparator 對此**不可能**再提供有效證據（§2.4）。
- **Q-PLUMBING**：cutover 後 Python 要依賴的那條 IPC 管線，在真實生產環境（真 engine、真 socket、真 4-worker uvicorn、真 PipelineCommand 佇列）下持續健康嗎？——**目前無人回答**。這是本輪設計的核心標的。

加上兩個運維性需求：soak 窗的連續性/有效性可機器判定（G2）、soak 中斷可偵測可告警（G3）。

---

## 2. 方案選型

### 2.1 (a) 驅動 lease ops 過 Python hub（mutating 合成流量）— ❌ 不採（連續用途）

- 每筆合成 acquire 在 Rust GovernanceCore 註冊**真 lease** + 寫真 `lease_transitions` audit row → 污染審計鏈（root principle 8）與 lease 活躍計數；持續流量 = 持續污染。
- 即使做了，**比對 gate 仍然無效**（§2.4 結構性原因），等於白冒 mutation 風險。
- 違反任務 root principle：「任何驅動流量方案不可影響生產 lease 行為」——acquire 即是生產 lease 行為。
- **保留一個受控變體**：收口時 operator 手動跑**一次性** mutating smoke（N≥10、demo profile、`intent_id` 帶 `soak_smoke:` 前綴標記、立即 release），驗 acquire/release 兩個 mutating arm + audit row shape。這本來就是 2026-06-02 原設計 step-(i) gate 的「Linux empirical」條款，是否已在 `a99bfa1d` 部署後跑過屬 owed-Linux-verify（§5.4）。

### 2.2 (b) instrument Rust 權威路徑 — ✅ 已做完，保留不動

`[81]` P-LIVE 即是此路：讀 V054 `lease_transitions`（Rust event_consumer 真寫）count + freshness，fail-closed。它證「Rust 權威熱路徑活著」= cutover 後系統真相層的健康證據。**不重複建設。**

### 2.3 (c) replay 第三路 — ❌ 已試過、已棄用，禁止復活

`lease_ipc_equiv_sampler.py` 頭部 DEPRECATED 標記 + SCRIPT_INDEX.md:96 已記載棄用理由。任何「拿歷史 row 餵 comparator」的變體都會撞同一面牆。

### 2.4 為什麼**任何**雙邊 divergence gate 都死了（含 canary 驅動的）——本輪最重要的設計判斷

第一輪只證明了 sampler（歷史 row）不可達。本輪設計時必須把結論推到底：**contemporaneous 合成流量也救不回雙邊比對**，因為：

- Rust 側 auth 是 per-pipeline `GovernanceCore` 在構造時 `new_with_profile` 自動授予（engine 內部生命週期）；Python 側 auth 是 hub-level `grant_paper_authorization` 控制面授予（API 進程生命週期，steady-state 未授權——sampler post-mortem 已證）。
- 兩者是**兩個獨立狀態實例、各自獨立的 transition 流**，不是「同一狀態的兩份實作」。comparator 的前提（same state, two engines）在 step-(i) 之後就結構性不成立——而 step-ii/iii（Python 變投影）一旦完成，Python 視圖 = Rust 投影，比對對象消失。
- 推論：canary 若做 `rust.is_authorized vs python.is_authorized` 雙邊比對並 gate 它，會像 sampler 一樣**永久卡死在結構性分歧上**（rust=GRANTED / python=DENIED 每拍一筆）。
- **設計鐵則**：comparator 維持 operator (b)+(b-i) 的「觀測性信號、非 gate」地位；canary **不寫 comparator**、不做雙邊判定；canary 的 gate 軸是**結構有效性**（response 形狀、型別、fail-closed 行為），不是等價性。

### 2.5 (d) 推薦：唯讀 IPC canary + epoch/flag 事件帳本 + `[82]` soak-window check — ✅ 採用

覆蓋 G1（管線曝險）、G2（連續性記帳）、G3（斷點偵測），同時：

- Python 不成為真相層：canary 純讀、零 mutation、零 SM 影響、失敗只記數。
- 讀法維持 B-3 的 E3 決策：**全走 PG**，不開 CSRF-exempt endpoint、不動 CSRF 豁免清單、不加無 auth HTTP 面。
- flag 革除語義不變：operator-env 仍一次性；soak 期使用**既有的** env-file 持久層（`restart_all.sh:717` 已支援，與 `OPENCLAW_COST_EDGE_ADVISOR`/`OPENCLAW_H_STATE_GATEWAY` 同模式）；`[82]` 在觀測到 flag-OFF 時自動標 soak invalid（錨點重置）並 FAIL。

### 2.6 A1/A3 既有覆蓋盤點（brief 要求，避免重複建設）

| 既有資產 | 覆蓋軸 | 對本輪的意義 |
|---|---|---|
| A1 `_compare_auth_axis`（hub.py:904-941） | acquire 開頭、Step-2 前、Rust `is_authorized` IPC vs Python `is_authorized()` 雙邊比對 | 解掉了「Rust-grant/Python-deny 被 Step-2 預過濾」的近盲——**但只在 organic 非-shadow acquire 觸發（≈0 次）**。保留原樣（觀測性）；canary 不重建此軸的雙邊語義（§2.4），只重用其 IPC client（`is_authorized_via_ipc`） |
| A3 no-opinion 排除（governance_divergence.py:123-133） | release/get presence 弱通道 UNKNOWN 不算分歧 | 已解 over-fire；本輪不碰 comparator 任何一行 |
| acquire scope-axis（hub.py:1046-1059） | Rust acquire outcome vs Python 完整影子 | organic≈0；保留觀測性 |
| `[81]` P-LIVE | Rust 權威路徑活性 | 新 gate 支柱之一，原樣保留 |
| 4a contract test（`sm_contract.rs` + `test_sm_contract_parity.py`） | SM transition 邏輯離線全分支 parity | 新 gate 支柱之一，原樣保留 |

---

## 3. 推薦設計

### 3.1 架構總覽

```
[API process（4 workers，flock 各選 1 leader）]
  ├─ governance_ipc_canary.py（NEW，E1-C）
  │    leader-elected asyncio task，每 300s：
  │    probe-1 governance.is_authorized（既有 client is_authorized_via_ipc）
  │    probe-2 governance.get_status（新 client 常數 + thin parser，additive）
  │    → 結構驗證（型別/欄位/fail-closed）→ 更新 module-level canary counters
  │    （attempts/ok/fail/last_ok_ts；登記 singleton-registry §2.5.x）
  │    失敗連 3 拍（15min）→ 一條 WARN "SM_IPC_CANARY_DOWN"（log 可 grep）
  │    鐵則：模組內 0 個 METHOD_ACQUIRE/RELEASE 引用（grep-verifiable）
  │
  ├─ governance_divergence_flush.py（EXTEND，E1-B）
  │    既有：30s UPSERT comparator counters → V129 key='singleton'（不動）
  │    新增：30s UPSERT canary counters → V129 key='canary'
  │          （欄位映射 total=attempts / matches=ok / divergences=fail，
  │           COMMENT 文檔化；V129 CHECK 不變式天然成立，0 schema 改動）
  │    新增：leader 啟動時讀舊 'singleton'/'canary' row → INSERT epoch_rollover
  │          事件（保前一 epoch 終值，損失 ≤30s）→ 才開始覆寫
  │    新增：flag 狀態變遷偵測 → INSERT flag_change 事件
  │
  └─ governance_divergence.py / governance_hub.py — 0 改動（comparator 原樣）

[PG]
  ├─ V129 lease_ipc_divergence_snapshot — 'singleton' + 'canary' 兩 row（schema 0 改）
  └─ V###（NEW，E1-A）learning.lease_ipc_soak_events — append-only 小表
       (id BIGSERIAL PK, event_type TEXT CHECK IN
        ('flusher_start','epoch_rollover','flag_change','canary_leader_start'),
        flag_enabled BOOL, prev_total/prev_matches/prev_divergences BIGINT NULL,
        prev_canary_attempts/prev_canary_ok/prev_canary_fail BIGINT NULL,
        detail JSONB, created_at TIMESTAMPTZ DEFAULT now())
       低速（soak 兩週 < 100 row）；非 hypertable；step-(iv) 連同退役 DROP

[cron（既有 6h passive_wait_healthcheck_cron.sh，0 改）]
  ├─ [81] lease_ipc_soak — 原樣（P-LIVE gate）
  └─ [82] lease_ipc_soak_window（NEW，E1-D）
       讀 V129 兩 row + soak_events：
       - soak-active 推定：flag_enabled=true 於最近觀測 OR 近 72h 有 soak 事件
       - 非 active → PASS-skip（"soak not active"）
       - active → 計算連續有效窗錨點 anchor = max(最近 flag-OFF 觀測,
         最近 invalid 事件, soak 手動起點)；輸出 window_hours +
         累計 probe 數（跨 epoch 求和：Σ epoch_rollover.prev + 當前 snapshot）+
         成功率 + 失敗連段 → 按 §4 gate 判 PASS/FAIL（fail-closed）
       - 偵測 counter regression 無對應 epoch_rollover 事件 → FAIL（記帳完整性破洞）
```

### 3.2 Canary 軸選擇與理由

- **probe-1 `governance.is_authorized`（主軸，必做）**：唯一已有完整 Python client（`governance_lease_bridge.py:524-551`）的唯讀 arm，端到端重用生產 dispatcher（one-shot IPC + timeout + fail-closed 解析）。結構驗證 = 回傳為 bool 或 None（None=IPC 失敗，計 fail）。**不**與 Python `is_authorized()` 比對（§2.4）。
- **probe-2 `governance.get_status`（次軸，建議做）**：Rust arm 在（dispatch.rs:370）但 Python client 缺 → 補 `METHOD_GET_STATUS` 常數 + thin parser（additive ~40 LOC 於 `lease_ipc_schema.py`/bridge）。價值：step-ii 的 Python 投影就要靠它讀 Rust 狀態——**提前在 soak 曝險 step-ii 的依賴**。結構驗證 = dict 含 `enabled`/`mode`/`risk_level` 等欄且型別對。
- **不做** `get_risk_state`/`list_leases` probe（step-ii 再說，避免本輪做大）；**不做** acquire/release probe（mutating，見 §2.1 一次性 smoke）。
- 載荷評估：1 probe/300s ≈ GUI 既有 `get_risk_runtime_status` 輪詢的零頭；PipelineCommand 佇列影響可忽略（E2 確認項）。

### 3.3 Flag 持久性與斷點偵測（G3）

- **SOP（operator 一行）**：soak 起點把 `OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1` 寫入 `$SECRETS_ROOT/environment_files/basic_system_services.env`；soak 結束（或 cutover 後 step-(iv)）移除。機制已 shipped（`restart_all.sh:717`，e6aa5e37），與 `OPENCLAW_AUTO_MIGRATE` 運維模式一致。env 檔在 secrets 目錄非 git——**不違反 operator-env 一次性 revert 語義**（operator-env 仍是 override 層）。
- **斷點偵測（機制兜底，不信 SOP）**：flusher 每 30s 記 flag 狀態 → 變遷寫 `flag_change` 事件；`[82]` 觀測到窗內任何 flag-OFF → soak invalid、錨點重置、check FAIL（exit 1 → cron log）。即使 operator 忘了寫 env 檔、即使有人全量 restart，**soak 中斷不再無聲**。
- **告警面誠實標記**：`[82]` FAIL 的消費面 = 6h cron log + exit code，與全部既有 check 相同——**無 push 告警**（與 canary_events.jsonl no-consumer、phantom-fix alert defer 同一既有債）。本輪不擴 scope 建 forwarder；soak 是 operator-timed 活動，SOP 寫明「soak 期間每日看一次 cron log 或手跑 `--check` 」。若 operator 要 push 告警，另開 task 接既有 reconciler alert 通道（defer，operator 選）。

### 3.4 為什麼 restart 不再終結 soak

- flag：env-file 持久（3.3）→ restart 後 flag 仍 ON。
- counter：歸零，但 flusher 啟動時先寫 `epoch_rollover` 事件保前值 → `[82]` 跨 epoch 求和，累計 probe 數不丟（≤30s 損失）。
- 窗：restart 期間 API down → canary 停拍 → `[82]` 容忍單次 epoch 間隙 ≤30min（原子部署實測 <2min）；超過 → 視為窗中斷、錨點重置（fail-closed）。
- divergence WARN log：`SM_DIVERGENCE` / `SM_IPC_CANARY_DOWN` 都在 api.log（持久），收口 grep 不受 restart 影響。

---

## 4. Gate 定義（step-(i) soak PASS 判準）

**S1-S5 全滿足才算 step-(i) soak PASS**（S1/S2 = operator (b)+(b-i) 既有支柱，原樣；S3/S4/S5 = 本輪新增）：

| # | 支柱 | 判準（明確數字） | 證據源 |
|---|---|---|---|
| S1 | 4a 離線 parity | `sm_contract.rs` + `test_sm_contract_parity.py` 於 soak 收口 commit 綠（Mac+Linux） | CI / cargo+pytest |
| S2 | P-LIVE | soak 窗內每次 6h cron `[81]` 全 PASS（lease_transitions fresh <3600s、無 silent-dead） | `[81]` + cron log |
| S3 | P-IPC（新） | 連續有效窗 **≥48h** AND 跨 epoch 累計 canary probe **≥500**（300s 拍 ≈ 48h=576，留 13% 容差）AND 結構成功率 **≥99%** AND 無 **≥3 連拍（15min）** 失敗連段 | `[82]`（V129 'canary' + soak_events） |
| S4 | soak 有效性（新） | 窗內 **0 次 flag-OFF 觀測**；epoch 間隙各 **≤30min**；0 次「counter regression 無對應 epoch_rollover」 | `[82]`（soak_events） |
| S5 | 收口 checklist（operator 一次性） | (a) `grep SM_DIVERGENCE api.log` 命中數=報告並逐筆歸因（觀測性，預期為 0 或全部結構性 auth 軸——**非自動 gate**，per (b)+(b-i)）；(b) mutating IPC smoke：N≥10 acquire+release（demo profile、`soak_smoke:` intent 前綴）全成功且 `lease_transitions` row shape 對 V054 CHECK；(c) comparator counter 終值入收口報告 | 人工 + smoke script |

**與 step-ii / step-iii 銜接**：

- **step-ii 進入條件** = S1-S5 PASS + 原設計 §5(ii) 的 reconcile-mismatch 路徑決策（IPC-escalate vs advisory-only，Linux 查證後定）。step-ii 的 Python 投影改讀 Rust 後，probe-2（get_status）的曝險證據直接複用。
- **step-iii cutover gate 不變**（原設計 §5(iii)/§6：operator sign-off + CC + E2 + BB-若觸 live-auth + E4 + audit-schema parity Linux 證明），其中原「soak 0 divergence + N ops」條款**正式替換為 S1-S5 證據包**。audit-schema parity（原設計 R1，auth/risk transition row Rust 是否已寫）仍是 cutover 前必解的最高殘留風險，不在本輪 scope 但在 checklist 留位。
- **step-(iv)**：canary、flusher 擴充、soak_events 表、`[82]`、V129 連同 comparator 一起退役（原設計既定）。

---

## 5. 風險與合規檢查點

### 5.1 改動風險評級：**中**

純 additive 觀測面：0 Rust 改動、0 comparator 改動、0 hub transition 邏輯、0 API schema 改動。觸 `main.py` startup（+1 task 排程）與 `governance_divergence_flush.py`（高耦合度低風險）。最敏感點 = canary 是新的 engine-facing 週期 IPC caller（唯讀、1/300s、有既有 GUI 輪詢先例）。

### 5.2 CC 合規覆核點（SM 治理核心鄰域，必過 CC）

- 硬邊界 grep（`live_execution_allowed|execution_authority|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease_emitted`）對 diff 預期 **0 命中**。
- **live-auth 5 閘 0 接觸**：本設計不碰 live-session/auth-routes 層任何檔（`authorization.json` HMAC、operator-role、`live_reserved`、mainnet env、secret slot）。canary 讀的 `governance.is_authorized` 是 SM-01 治理投影，**不是** 5 閘。
- 原則 1/2（單一寫入口/讀寫分離）：canary 純讀；mutating smoke 是 operator 手跑一次性腳本、不接任何 scheduler、demo-profile-only（mainnet fail-closed 斷言，仿 `clean_restart_flatten.py:36-42` 模式）。
- 原則 6（fail-closed）：canary/flusher/`[82]` 全 fail-soft 對權威路徑、fail-closed 對自身判定（讀不到→FAIL 非綠）。
- 原則 8：canary 不產 audit row；smoke 的 row 帶 `soak_smoke:` 前綴可追溯。
- 新 module-level 可變單例（canary counters + leader fd）須登記 `singleton-registry.md` §2.5.x（merge 前置）。

### 5.3 E2 重點審查 3 點

1. **隔離性**：canary/flusher 擴充的任何例外或延遲不得進入 hub lease 權威路徑、comparator、或 5 live-auth 閘；PG/IPC I/O 不持 comparator lock；canary timeout 有界。
2. **無假綠路徑**：`[82]` 在 soak-active 下對「flag-OFF / flusher 死（snapshot stale）/ canary 死（probe 數不增長）/ counter regression 無 epoch 事件」四種情形**逐一 FAIL**——用 mutation 測試驗 bite（把每個偵測支路弄壞，斷言 FAIL）。
3. **零 mutation 鐵則**：canary 模組 grep 0 個 `METHOD_ACQUIRE_LEASE|METHOD_RELEASE_LEASE` 引用；smoke script 無 cron/scheduler 接線、demo-only 斷言在 client 層。

### 5.4 Owed Linux verify（Mac 不可證，sign-off 前置）

- V### migration 雙跑 dry-run（冪等）於 Linux PG。
- `basic_system_services.env` 是否已含/寫入 flag（soak 起點 SOP 步驟）。
- canary 真 round-trip（真 engine socket）一拍成功 + `[82]` 真值輸出。
- **查證 `a99bfa1d` 部署後是否已跑過原設計 step-(i) 的 acquire/release Linux empirical**（若無，S5(b) smoke 是首次，須 BB 過目其 demo-only guard）。
- E3 視角複核：無新 HTTP 面（全 PG + in-process）、新 lock 檔在 `$OPENCLAW_DATA_DIR`、IPC 走既有 hmac socket——預期 0 新攻擊面，E3 快審即可。

### 5.5 既有債順手標記（不擴 scope）

`governance_divergence.py` MODULE_NOTE:32-33 與 `governance_extended_routes.py:424-427` 的舊 gate 註解 stale → E1-E 一併修字；TODO.md §5 row 75 stale → PM 更新；cron exit-code 無 push 消費者 → 既有債，另案。

---

## 6. E1 任務分解（5 task、3 wave、估 2-3 工作天）

| Task | 檔案（互不重疊） | 內容 | 估規模 |
|---|---|---|---|
| **E1-A**（Wave 1） | `sql/migrations/V137__lease_ipc_soak_events.sql`（**號碼 E1 時重驗 next-free**；V136 為當前 max，V137 為 L2 reserved-not-used 的自由號——若被並行 session 取走則順延） | append-only soak 事件表，Guard A + CHECK(event_type) + 冪等雙跑；非 hypertable | ~130 LOC SQL |
| **E1-C**（Wave 1，與 A 並行） | `app/governance_ipc_canary.py`（NEW）+ `app/lease_ipc_schema.py`（additive：`METHOD_GET_STATUS` 常數 + parser）+ `tests/test_governance_ipc_canary.py` | leader-elected asyncio canary（300s、probe-1/2、結構驗證、counters、WARN 連段）；counter getter 契約：`get_canary_counters() -> dict[str,int]`（PA 在此鎖定簽名，供 E1-B 並行依賴） | ~300 + 300 LOC |
| **E1-B**（Wave 2） | `app/governance_divergence_flush.py`（EXTEND）+ `app/main.py`（canary task + 既有 flusher 區塊兩處 wiring 同檔同人改，避免並行衝突）+ `tests/test_governance_divergence_flush.py`（EXTEND） | 'canary' key flush、epoch_rollover 捕捉、flag_change 事件、canary task 排程 | ~150 + 200 LOC |
| **E1-D**（Wave 2，與 B 並行） | `helper_scripts/db/passive_wait_healthcheck/checks_governance_lease_ipc.py`（EXTEND，加 `check_82_lease_ipc_soak_window`；檔案未近行數上限）+ `runner.py`（註冊）+ `helper_scripts/db/test_lease_ipc_soak_healthcheck.py`（EXTEND） | `[82]` 窗評估 + 四 FAIL 支路 + PASS-skip；mutation 測試 | ~220 + 250 LOC |
| **E1-E**（Wave 3，serial 收尾） | `helper_scripts/db/lease_ipc_mutating_smoke.py`（NEW，operator-run）+ `SCRIPT_INDEX.md` + stale 註解修字 + soak SOP 段落（入 TODO §5 P5 row 重寫稿） | S5(b) smoke + 運維文檔 | ~150 LOC + docs |

依賴關係：E1-B 依賴 E1-A（表）與 E1-C（getter 契約，已由本報告鎖定簽名可並行）；E1-D 依賴 E1-A。Wave1(A∥C) → Wave2(B∥D) → Wave3(E)。角色鏈：E1 → E2（§5.3 三點 + mutation bite）→ E4（Mac+Linux regression）→ CC（§5.2）→ operator（soak 起點 SOP + S5 收口）。BB 僅在 smoke script 觸 lease mutation 時過目（demo-only guard）。

與當前 branch WIP 隔離：dirty 檔全在 `l2_*` / aeg test / memory 域，與本設計目標檔 **0 重疊**（`governance_hub.py` 不在 dirty 清單且本設計不改它）。

---

## 附錄 — 本次親證 anchor（當前 HEAD `aeae4da4`）

- comparator：`governance_divergence.py`（counters 69-73、record 91-178、gate 殘文 32-33）；in-memory、restart 歸零。
- hub 觸點：`governance_hub.py` 990-1001（SHADOW_BYPASS 短路）、1014-1015（A1 入口）、904-941（`_compare_auth_axis`）、1036-1060（acquire IPC 權威 + scope-axis）、933/1053/1179/1245（record_divergence）。
- flusher：`governance_divergence_flush.py`（30s、flock、UPSERT 'singleton'）；wire `main.py:585-605`。
- V129：`sql/migrations/V129__lease_ipc_divergence_snapshot.sql`（TEXT key 多 row 擴充明文允許：44-48）。
- `[81]`：`checks_governance_lease_ipc.py`（P-LIVE gate 83-123、comparator 觀測欄 138-190、3600s 閾值 52）；runner 註冊 `runner.py:191-202`；6h cron `passive_wait_healthcheck_cron.sh`（log-only 消費）。
- flag：`governance_lease_bridge.py:126-137`（嚴格 "1"）；`restart_all.sh:716-717`（operator-env 優先 → env-file 持久 fallback，e6aa5e37 引入）。
- Rust arms：`ipc_server/dispatch.rs:361-372`（7 arm）；Python client 常數僅 4（`lease_ipc_schema.py:69-81`）。
- sampler 棄用：`lease_ipc_equiv_sampler.py:1-12` DEPRECATED 頭 + commit `87047e32` 訊息（operator (b)+(b-i)）。
- 歷史鏈：`e6aa5e37`（E1b + flag 持久機制）→ `b904125f`（B-3 三件套 + sampler）→ `87047e32`（rework：P-LIVE-only gate）→ `b847ae28`（V128→V129）。

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--p5sm_soak_observability_redesign.md
