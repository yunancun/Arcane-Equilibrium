# RFC — EDGE-P2-flip shadow→live SOP

**日期**：2026-04-26 CEST
**作者**：PA (Project Architect)
**範圍**：EDGE-P2-flip（Wave 3）Combine Layer `shadow_enabled false → true` 翻轉操作流程 + 回滾路徑 + 與 P1-10 並行範疇釐清
**狀態**：DRAFT，待 PM + QC + FA review → 第三波 E1 派發前定稿

---

## § 1. 目標範疇

EDGE-P2-flip 的「shadow flip」**不是** ExecutorAgent shadow→live（那是 G3-02 / G3-03 處理的不同範疇），而是 **Combine Layer (Track P + Track L) 的 shadow exit observation 翻轉**：

| 系統 | shadow 標誌 | 控制平面 |
|---|---|---|
| **Combine Layer**（本 RFC 範圍）| `RiskConfig.exit.shadow_enabled` | Rust 全自動 close-path 觀察寫 `learning.decision_shadow_exits` |
| ExecutorAgent（G3-02/03 範圍） | `RiskConfig.executor.shadow_mode` | Python 5-Agent intent 是否真實送 SubmitOrder IPC |

兩者**不可**混淆。本 RFC 只處理前者。

當前狀態（per CLAUDE.md §三 + `exit_features/v2.rs:181-187`）：
- `ExitConfig.shadow_enabled = false`（默認，Phase 1a dormant）
- 0 emit / 0 row / `fills.exit_source` 除 PHYS-LOCK 外全 NULL
- IPC `patch_risk_config` deep-merge 已 live（test_g3_05 驗證）

flip 後狀態（Phase 2）：
- `shadow_enabled = true`
- close-path 從 `edge_estimates` cell 建構 mock `MLInference`（score = sigmoid(shrunk_bps/floor)）
- 每筆 close 發一條 `ShadowExitMsg` 寫 `learning.decision_shadow_exits`
- `ml_override_high=2.0` sentinel **仍守不變式**（ML 無法翻 Physical Hold → Lock）
- `fills.exit_source` 開始有 4 vocab 之一（Physical / Hybrid / ML-shadow / TimeStop / HardStop）

---

## § 2. flip acceptance criteria（量化）

### § 2.1 主指標：healthcheck [15] `shadow_exit_agreement_phase2`

per `passive_wait_healthcheck.py:1683`：
- **PASS**：24h 0 rows（dormant）OR `1 - disagreed_ratio ≥ 0.95`
- **WARN**：80% ≤ agreement < 95%
- **FAIL**：agreement < 80% 且非空

`disagreed BOOLEAN` column 直接反映 Combine vs Physical baseline 一致性。Phase 2 啟動後該 check 必有非 0 sample。

**主驗收**：`agreement ≥ 95%` over 24h window

### § 2.2 樣本量需求

| 階段 | 需求 |
|---|---|
| flip 前 24h dry-run | 假樣本驗 IPC + writer pipeline 不掛（用 mock event injector） |
| flip 後 6h | ≥30 close events（demo 24h ~150 rows / 4 = ~37）→ 觀察 disagreed 分佈 |
| flip 後 24h | ≥150 close events 且 healthcheck [15] PASS |
| flip 後 7d | ≥1000 close events + agreement 連 7 個 24h window 均 ≥95% |
| flip 後 14d | per-strategy stratified agreement ≥95%（避免 dominant 策略遮蔽） |

**case-level binary 還是 sample-level proportion**：採 **sample-level**（per-row disagreed=FALSE/TRUE → ratio）。case-level binary（每個 close event 算 1 case）= 同一個 statistic（每 row 對應 1 close）；本系統下兩者等價。

### § 2.3 per-strategy stratification

flip 後 24h pass 不夠 — 還需檢查 per-strategy agreement：
- grid_trading agreement ≥95%
- ma_crossover agreement ≥95%
- bb_reversion agreement ≥95%
- bb_breakout 因 disabled (G2-06) 跳過
- funding_arb 因 dormant 跳過

任一 active strategy < 95% → **不**能 flip 完成 / FAIL。

---

## § 3. flip 步驟 SOP

### § 3.1 Pre-flight（必過 5 條）

| # | 檢查 | 驗證命令 / 實證 |
|---|---|---|
| 1 | engine alive + binary mtime fresh | `ssh trade-core "python3 helper_scripts/canary/engine_watchdog.py --status"` |
| 2 | healthcheck 全綠（[1]-[16] PASS / 容忍 [11] WARN） | `ssh trade-core "bash helper_scripts/db/passive_wait_healthcheck_run.sh"` |
| 3 | exit_features writer 24h 累積 ≥150 rows | check [3] PASS |
| 4 | edge_estimates cells ≥150（per check [13]） | mock MLInference 來源 |
| 5 | combine_layer mock 構造路徑驗證 | dry-run 跑 `cargo test --release combine_layer::test_mock_inference_*` |

**任一 FAIL → flip 中止**。

### § 3.2 flip 操作（推薦 IPC patch 路徑）

**選項 A**（推薦）：IPC patch_risk_config 熱重載
```bash
ssh trade-core 'curl -sS -X POST -H "Content-Type: application/json" \
  --data "{\"jsonrpc\":\"2.0\",\"method\":\"patch_risk_config\",\"params\":{\"engine\":\"demo\",\"source\":\"operator\",\"patch\":{\"exit\":{\"shadow_enabled\":true}},\"id\":\"flip_20260507\"}}" \
  http://localhost:8002/ipc/jsonrpc'
```
- 0 重啟，~10s 內生效
- TOML 自動 persist（per ConfigStore::apply_patch 規則）
- 可同步寫 demo+live 環境（兩個 patch 命令）

**選項 B**：TOML 編輯 + reload
```bash
ssh trade-core 'sed -i "s/^shadow_enabled = false/shadow_enabled = true/" \
  settings/risk_control_rules/risk_config_demo.toml && \
  curl -sS -X POST http://localhost:8002/api/v1/ipc/reload_risk_config?engine=demo'
```
- 30-60s 生效（reload 流程）
- 適合 operator 需要先 review TOML diff 場景

**禁用選項 C**：engine restart（180s+，無必要）

### § 3.3 灰度 vs 直接 flip

**直接 flip 全策略**（PA 推薦）—
- Combine Layer 是 close-path 觀察工具，**不影響任何 entry / exit 真實決策**（`ml_override_high=2.0` sentinel 守不變式）
- shadow row 寫 `learning.decision_shadow_exits` 是純觀察，沒有交易副作用
- 灰度（per-strategy 翻）會破壞 cross-strategy disagreement 分析
- 唯一風險 = writer 掛或 mock construction 錯，這由 dry-run + healthcheck [8] silent-dead 偵測捕獲

**例外**：若任一 pre-flight FAIL → 該 engine（demo / live）**不**翻；其他 engine 可獨立翻。

### § 3.4 flip 後立即驗證（前 6h）

| 時間點 | 檢查 | PASS 標準 |
|---|---|---|
| flip + 30min | healthcheck [8] shadow_exits_24h | rows > 0 + 不亮 silent-dead FAIL |
| flip + 1h | row sample > 10 | manual SQL count |
| flip + 6h | healthcheck [15] | agreement ≥ 80%（warm-up）|
| flip + 24h | healthcheck [15] | agreement ≥ 95% PASS |

任一階段紅 → § 4 立即回滾。

---

## § 4. 回滾路徑

### § 4.1 自動回滾（Phase 2.1 升級項，目前 manual）

**未來功能** — 新增 cron `helper_scripts/canary/shadow_exit_auto_revert.py`：
- 每 1h 跑一次
- 檢 healthcheck [15] 連續 3 個 1h window FAIL（< 80%）→ 自動 IPC patch shadow_enabled=false + 寫 incident log

**本 RFC 不要求自動化**，operator manual 即可。

### § 4.2 Manual 回滾（90s SOP）

```bash
# Step 1: IPC flip back
ssh trade-core 'curl -sS -X POST -H "Content-Type: application/json" \
  --data "{\"jsonrpc\":\"2.0\",\"method\":\"patch_risk_config\",\"params\":{\"engine\":\"demo\",\"source\":\"operator\",\"patch\":{\"exit\":{\"shadow_enabled\":false}},\"id\":\"revert_20260507\"}}" \
  http://localhost:8002/ipc/jsonrpc'

# Step 2: verify dormant
sleep 30 && ssh trade-core 'bash helper_scripts/db/passive_wait_healthcheck_run.sh' | grep "shadow_exits_24h"
# Expected: PASS dormant

# Step 3: incident log
ssh trade-core 'echo "$(date) -- EDGE-P2-flip reverted: agreement <80% / writer FAIL" >> docs/incidents/log.md'
```

回滾**不會丟資料**（Phase 1a 期間累積的 shadow row 仍在 DB），可後續離線分析 disagreement_reason 找 root cause。

### § 4.3 回滾觸發條件

| Trigger | 等級 | 動作 |
|---|---|---|
| healthcheck [15] 連 3h FAIL | P0 | 立即 manual 回滾 |
| shadow_exit_writer 0 row > 6h（[8] silent-dead） | P0 | 立即 manual 回滾 + investigate writer |
| disagreed > 50% in 1h slice | P1 | observable 6h 再決策 |
| operator judgement | any | 隨時可回 |

---

## § 5. 「P1-10 並行」範圍釐清

PM 派發指令含「P1-10 並行」，FA report §gap-1 標模糊。**本 RFC 釐清**：

P1-10 = STRATEGY-ASYMMETRY-1（grid 過度交易 + ma R:R 不對稱）。當前狀態（per CLAUDE.md §三）：
- EDGE-P2-3 PostOnly 已部署 demo（2026-04-21）
- ≥1w demo 等待 maker fee 驗證（healthcheck [3] maker_fill_rate）
- G2-01 PostOnly 1-2w 驗收 ETA ~5/07-5/08

**「並行」含義**（PA 解讀）：

| 解讀 | 釐清 |
|---|---|
| **A. 同時觀察 P1-10 PostOnly 數據** | P1-10 已自然在 passive 等候，與 EDGE-P2-flip 無關，本身在跑 |
| **B. 同時做 P1-10 結案決策** | G2-01/G2-04 屬獨立議程，不依賴 EDGE-P2-flip |
| **C. P1-10 fix 影響 shadow disagreement 分析** | ❌ 否 — Combine Layer 觀察的是 exit 決策（giveback / micro_profit / phys_lock），P1-10 是 entry fee 結構問題，物理不交集 |

**PA 推薦範圍**：採 A — flip 期間同時觀察 P1-10 PostOnly fee drop（healthcheck [3] maker_fill_rate）。**不**等 P1-10 結案，**不**將 P1-10 結果作為 flip acceptance criteria。

兩條 timeline 各自進行，5/07 maker fee 驗收 + 5/10 EDGE-P2-flip 各按各的 acceptance 走。

---

## § 6. 與其他治理面互動

### § 6.1 EX-04 Reconciler（FA report §gap-2）

EX-04 對賬範圍 = paper vs live/demo position consistency。Combine Layer shadow 寫 `decision_shadow_exits`（純觀察表）**不**影響 reconciler input — reconciler 對的是 `paper_state.positions` vs `bybit_demo` actual positions，shadow exit 不寫 positions。

**結論**：EX-04 與 EDGE-P2-flip 物理隔離；flip 後 reconciler 無新檢查項。

### § 6.2 SM-02 Decision Lease（FA report §gap-4）

ExecutorAgent acquire_lease 路徑（per `executor_agent.py:364`）只在 ExecutorAgent **真實送 SubmitOrder** 時觸發。本 RFC 範圍（Combine Layer shadow）是 close-path 觀察，**不**經 ExecutorAgent，**不**走 lease 路徑。

ExecutorAgent shadow→live 屬 G3-02/G3-03 範疇，**不在本 RFC**。

但有一個跨 RFC 互動值得記：若未來 G3-02 Phase C 完成（ExecutorAgent live），同時 EDGE-P2-flip 完成（Combine Layer live），則同一筆訂單會：
1. ExecutorAgent acquire_lease 寫 lease state
2. Combine Layer 寫 shadow exit observation（與 lease 無關）

兩者獨立，**無**循環依賴。

### § 6.3 DOC-04 Agent Learning Evolution（FA report §gap-1）

EDGE-P2-flip 不觸發策略 promotion / tier advancement。flip 後產生的 shadow data 是 **離線研究輸入**（為未來 ML 訓練 + edge_predictor 升級做準備），不是 in-loop 決策路徑。

DOC-04 tier advancement 由 STRATEGIST-AUTO-PROMOTE backlog 處理（P3 deferred），與本 RFC 無關。

---

## § 7. E1 子任務拆分（推薦 ≤3 並行）

| 子任務 | 範圍 | 工時 | 依賴 | E1 instance |
|---|---|---|---|---|
| **P2-flip-T1** | flip 前 dry-run smoke test 工具：`helper_scripts/canary/edge_p2_flip_dry_run.py`（mock event injector + writer pipeline 驗證） | 1d | 無 | E1-Alpha |
| **P2-flip-T2** | per-strategy stratified agreement healthcheck 升級（[15] 加 strategy 切片）+ disagreement_reason 分佈報告工具 | 1d | 無（與 T1 並行） | E1-Beta |
| **P2-flip-T3** | manual flip + revert SOP shell wrappers：`helper_scripts/operator/edge_p2_flip.sh` + `edge_p2_revert.sh`（封裝 § 3.2 + § 4.2 IPC 命令）| 0.5d | T1 + T2 | E1-Alpha（與 T1 同實例） |

**檔案 isolation**：
- T1: `helper_scripts/canary/edge_p2_flip_dry_run.py`（新檔）
- T2: `helper_scripts/db/passive_wait_healthcheck.py:1683+` 區段擴展 + 新工具 `helper_scripts/research/shadow_disagreement_breakdown.py`
- T3: `helper_scripts/operator/edge_p2_*.sh`（新檔）

**衝突風險**：
- T2 與 EDGE-P1b RFC §5.T4 同檔（healthcheck）→ 派發前**先**確認 P1b T4 是否已 merge；若衝突 → T2 等 P1b T4 完成
- T3 純新檔，0 衝突

**強制鏈**：T1+T2 → E2 review（dry-run 邏輯 + per-strategy filter 正確性） → E4 regression → QC review（agreement metric 統計合理性） → PM Sign-off → operator manual flip approve

---

## § 8. isolation 評估

**動態 isolation per PM.md §35-39**：
- T1 + T3 同 E1-Alpha（串接），T2 獨立 E1-Beta
- 並行 ≤2 instance，T2 與 P1b-T4 同檔風險（時序解決）→ **NOT** isolation（順序派發）
- 純研究 / SOP 工具 → **NOT** destructive
- **主樹進行即可**，0 worktree

---

## § 9. E2 重點審查 3 點

1. **dry-run mock construction 不污染 production data**：T1 mock injector 必須走獨立 mock fields（如 `learning.decision_shadow_exits_dry_run` 表 or 用 `engine_mode='dry_run'` 過濾），**不**寫 production shadow 表
2. **per-strategy filter SQL 防 prefix 撞名**：T2 SQL `strategy_name = 'grid_trading'` 必精確比對，**不**用 LIKE 'grid%'（會撞 grid_oddity / grid_helpers）
3. **revert SOP idempotency**：T3 revert.sh 多次執行不應改變最終狀態（IPC patch 已 idempotent；但 incident log append 需 dedup 防同一事件多 entry）

---

## § 10. 治理對照

- **DOC-01 §5.7 學習 ≠ 改寫 Live**：shadow 寫的是 learning plane（learning.decision_shadow_exits），不影響 live trading；符合
- **DOC-08 §12 安全不變量 #4**：flip 不降低風控；shadow_enabled 切 true 純觀察；invariant 保持
- **CLAUDE.md §四 硬邊界**：shadow_enabled 不在 5 項 live 門控；flip 不觸碰
- **CLAUDE.md §七 被動等待 TODO 必附 healthcheck**：[8] + [15] 已存在，符合
- **memory `feedback_risk_changes_scoped`**：flip 只改 1 字段（shadow_enabled），不連帶改其他 ExitConfig；遵守

---

## § 11. 不確定 / 未決問題

1. **per-strategy < 95% 但 aggregate ≥ 95% 是否算 PASS**：當前 healthcheck [15] 只算 aggregate；T2 升級後 per-strategy FAIL 但 aggregate PASS 應如何處理？PA 推薦 **per-strategy 是必過項**（任一 active 策略 < 95% → 整體 FAIL），但需 PM 拍板
2. **flip 與 G2-06 disabled 順序**：G2-06 已 disable bb_breakout（per `strategy_params_demo.toml`），此 flip 期間 bb 0 fill → shadow 0 row → 不影響 agreement metric。但若 future re-enable bb，需先補 ≥150 row 觀察期再 flip 全策略
3. **flip 失敗的 retry policy**：若 flip + 24h disagreement 在 80%-95% 之間（WARN），是延長觀察 7d 還是立刻 revert？PA 推薦 **延 3d 觀察** 看是否自然收斂 ≥95%（regime 適應），3d 仍 WARN 才 revert

---

**PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--edge_p2_flip_sop_rfc.md`**
