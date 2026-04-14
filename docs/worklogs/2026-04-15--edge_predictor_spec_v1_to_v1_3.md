# 2026-04-15 · EDGE-P3-1 Realized Edge Predictor 規格四輪演化（v1.0 → v1.3 GREEN）

**Scope**: FA 功能規格 `docs/references/2026-04-15--edge_predictor_spec.md` 的完整演化 — 從 v1.0 初稿到 v1.3 GREEN，歷經 3 次修訂 + 4 輪跨學科審查（QC / QA / ML-MIT / AI-E），最終取得 Stage 0 開工許可。
**Role chain**: PM+FA → 4× 平行 sub-agent 審查（round-1/2/3）→ FA inline 修訂（主會話寫碼符合 `feedback_subagent_code_writing_refusal.md`）→ AI-E round-4 covering review → PM 簽核。
**Outcome**: 規格 816 → **1101 行**（+285 行）· 10 F-patch（F1-F10）+ 4 U-patch（U1-U4）+ 1 M-patch（M1）· CC 檢查清單 10 → **13 項**（+30%）· 命名測試 T1 → **T23**· 新增副產物 project memory `project_mac_deployment_target.md`。Stage 0 可開工（task #25 PA SQL migration + task #27 AI-E `edge_predictor/features.rs`）。

---

## 一、立項背景：為何需要 Realized Edge Predictor

### 1.1 三個洞匯流成一個根因

TODO.md W25+ 長期工作中的 EDGE-P3-1 是 2026-04-14 operator 確認的定稿思路，用一句話概括：

> `shrunk_bps` 是「策略**歷史平均**賺多少」（靜態 James-Stein 收縮）；此項改為「**這一筆**在現在市場條件下預期賺多少」（per-strategy quantile LightGBM 動態預測）。

三個獨立觀察指向同一個缺口：

| 觀察 | 症狀 |
|---|---|
| Phase 5 PAUSED（2026-04-12 reframe）| `shrunk_bps` 全部塌到 -35.72 bps，B=1.0 完全池化，cost_gate 形同虛設 |
| LightGBM 管線（P2-1）| 管線骨架在位但**無推理接線** — 是空殼 |
| LinUCB（Phase 4）| 只做 arm 選擇，不預測單筆 edge |

共同根因：**沒有模型把「決策瞬間 features」映射到「實現 edge」**。

### 1.2 與既有系統的關係

- **不取代 LinUCB**：LinUCB 仍做「選哪個策略家族」，edge predictor 做「這一筆值不值得放行」
- **接替 `shrunk_bps`**：`cost_gate` 比較邏輯改為 `predicted_median_edge − k×(median−q10) > cost` 才放行，`q10 > 0` 才加倉
- **Shadow-first**：≥14d paper shadow + pinball loss 對比常數模型 >10% 才 promote active
- **Fail-closed**：推理失敗回退現有 shrinkage，不觸 LinUCB

---

## 二、四輪審查總覽

| 輪次 | 啟動時機 | 審查者 | 主要輸入 | 產出 patch | 規格行數 |
|---|---|---|---|---|---|
| Round-1 | v1.0 發布後 | QC + QA | v1.0 | 多項 round-1 fix（已併入 v1.1，歷史合併）| 約 800 |
| Round-2 | v1.1 發布後 | QC + QA + ML-MIT + AI-E 平行 | v1.1 | 去重後 **7 共識 must-fix**（F1-F7）+ F8-F10 補強 | 816 → 1019 |
| Round-3 | v1.2 發布後 | QC + QA + ML-MIT + AI-E 平行 | v1.2 | AI-E YELLOW：**U1-U3 real gaps** + 附加 U4 + M1 Mac CI | 1019 → 1101 |
| Round-4 | v1.3 發布後 | AI-E covering review | v1.3 | **GREEN** — Stage 0 開工許可 | 1101（不變）|

**圖示演化**：

```
v1.0 ─ round-1 ─→ v1.1 ─ round-2 (F1-F10) ─→ v1.2 ─ round-3 (U1-U4 + M1) ─→ v1.3 ─ round-4 GREEN
816 行                                        1019 行                          1101 行
```

---

## 三、Round-2：F1-F10 修訂（v1.1 → v1.2）

### 3.1 去重後的 7 共識 must-fix

4 個 sub-agent 平行審查 v1.1 後返回的原始 finding 有重疊。經 FA 合併去重：

| Patch | 來源 | 問題 | 修復 |
|---|---|---|---|
| **F1** | QC-D1 | grid_trading 拆單與非拆單策略 label 口徑不一 | §4.2/§4.3 明定：`grid_trading` VWAP merge（split_flag=false）；其他 qty-weighted blend（split_flag=true）|
| **F2** | QC-D2 + AI-E B2（雙確認）| §7.3 pseudocode `store.load_for()` 在 `predictor.age_seconds()` 之後，未綁定變量 | 調換順序，`load_for()` 先 |
| **F3a** | QA-D2 | `disagreed` GENERATED 欄 NULL 污染 | 改 `COALESCE(..., '') <> COALESCE(..., '')` |
| **F3b** | QA-D4 | DisableEdgePredictorAll 不持久化，watchdog 重啟後自動復活 | 寫 per-engine `RiskConfig.toml` + fsync |
| **F4** | QA-D3 + ML-MIT-D2 + ML-MIT-B5（三重確認）| ε-greedy shadow fill 無 schema 隔離，可能污染 training label | 新增 `learning.decision_shadow_fills` + `CHECK (engine_mode='paper')` + 雙閘 SQL WHERE |
| **F5** | ML-MIT-D1 | §12.4 測試清單為概念性描述，無枚舉 | T1..T22 具名測試 + 斷言 |
| **F6** | AI-E B1 | Live/Demo `edge_fallback_terminal` 首次即需 P2 | §10.2 新增 Live/Demo 首次 → P2；Paper 保留 P3/1h |
| **F7** | ML-MIT 自查 | CHANGELOG 誤宣稱加入 `recent_slippage_bps_ewma`（實際延後）| 修正 CHANGELOG |
| **F8** | AI-E B3 | Cargo 雙 feature 互斥未強制 | `compile_error!` macro |
| **F9** | AI-E B4 | `load_for()` RwLock guard 跨 ArcSwap load 可能死鎖 + rand 種子問題 | guard drop discipline 明文 + `SmallRng` per-engine 種子 |
| **F10** | QA-D5 | 運維 runbook 路徑只在 code comment 中 | §10.2 + §12.5 明文 `docs/runbooks/edge_predictor_on_call.md` |

### 3.2 Round-2「未採納 / 延後處理」

不進入 v1.2 但文件化（避免「我提過你沒理」的 tension）：~17 項，包括 `recent_slippage_bps_ewma` feature、CPCV fold 數討論、online learning 支線等，寫入 v1.2 CHANGELOG 的「未採納」子段落。

### 3.3 輸出

- 816 行 → **1019 行**（+203 行）
- CC 檢查清單 10 → 12 項（新增 #11 shadow-fill 排除 / #12 kill-switch 持久化）

---

## 四、Round-3：U1-U4 + M1（v1.2 → v1.3）

### 4.1 AI-E 通過直讀 Rust 源碼找出的 3 個 real gap

Round-3 QC/QA/ML-MIT 回 GREEN，但 **AI-E YELLOW** —— sub-agent 對比規格與實際 Rust 源碼發現 3 個非字面吻合：

| U-patch | 規格原文 | 實際代碼 | 修復 |
|---|---|---|---|
| **U1** | §8.8「authorization envelope 同 RevokeExecutionAuthority」| `RevokeExecutionAuthority` 是 Python-layer 概念，不是 Rust IPC | 明拆：Python 層 `_EXECUTION_AUTHORITY_OVERRIDE == "granted"`，Rust IPC 帶 `operator_token: String` + UUID v4 + len≥32 校驗 |
| **U2** | §8.8「TOML fsync before ArcSwap swap」| 讀 `rust/openclaw_engine/src/config/store.rs:231-244`：`write_toml_atomic()` **無** `File::sync_all()`，**無** 父目錄 fsync | 新 helper `write_toml_atomic_fsynced()` 同時 fsync tmp 檔 + 父目錄；Task #27 包含升級；CC #13 + T23 用 strace 驗證 |
| **U3** | §7.3 引用 `emit_shadow_fill_ipc()`| IPC 訊息形狀未定義 | 定義 `PipelineCommand::EmitShadowFill { context_id, strategy, symbol, features_jsonb, prediction: (f64,f64,f64), cost_bps, ts_ms }` |

### 4.2 FA 自發加的補強

| Patch | 動機 |
|---|---|
| **U4** | 多引擎 TOML partial-failure 語義 — 兩階段提交（stage 1 全 fsync，stage 2 全 swap）；kill-switch 永不處於「半啟用」狀態 |
| **M1** | operator 確認未來部署 Apple Silicon Mac（M5 Ultra/Max）→ §12.4 CC #10 明定 `aarch64-apple-darwin`（`macos-14`/`macos-15` runner），顯式排除 `aarch64-unknown-linux-gnu`（Linux-on-ARM，與 macOS ARM 是不同 platform tuple）|

### 4.3 Mac 移植子線（M1 的衍生物）

Operator 在審視 round-2 QA-E6 延後項「linux-arm64 CI」時提出疑問：
> 我剛才看見你提到（QA-E6 linux-arm64 CI / red-CI merge block）你記得後面我們是要移到 mac 去的吧？這個不會有影響嗎？

FA 澄清：`aarch64-unknown-linux-gnu`（Linux-on-ARM，NAS/Pi 場景）與 `aarch64-apple-darwin`（macOS Apple Silicon）是不同 platform tuple，常被混為一談。QA-E6 的延後不影響 Mac 部署路徑。

Operator 進一步確認：「Apple silicon 的 mac 預計會是 M5 ultra 或者 m5 max」—— 寫入 project memory `project_mac_deployment_target.md`（2026-04-15 新增），MEMORY.md 索引同步更新。memory 內容涵蓋：
- CI tuple `aarch64-apple-darwin` 必須
- tract-onnx 跨平台純 Rust 為主線；ort 在 macOS 需捆 `libonnxruntime.dylib`
- systemd → launchd 遷移路徑
- 禁 x86_64-only SIMD intrinsics、CUDA-only crate、Linux-only Python 擴展
- EDGE-P3-1 v1.3 CC #10 已強制該 tuple + precision + ArcSwap concurrent test

### 4.4 輸出

- 1019 行 → **1101 行**（+82 行）
- CC 檢查清單 12 → **13 項**（新增 #13 `strace -e fsync` 驗證）
- 命名測試 T22 → **T23**（新增 `test_write_toml_atomic_fsynced_survives_sigkill`）

---

## 五、Round-4：AI-E Covering Review（v1.3 GREEN）

### 5.1 審查設計

Operator 指令：「跑第四輪 AI-E 覆審確認 U1-U3 乾淨。然後確保未來我移植 mac 不會有問題」。

派單一 AI-E sub-agent 做 covering review，3 個 scope：

| Scope | 問題 |
|---|---|
| A | U1-U4 + M1 每項逐條驗證（引用 spec line / §）|
| B | F1-F10 回歸 — v1.3 additions 是否破壞前輪 GREEN |
| C | Mac 移植全規格審計（ONNX/Rust crate/服務腳本/filesystem/Python dep/CI matrix/hardcoded path/timing）|

### 5.2 結果

**GREEN — spec ready for operator sign-off and Stage 0 kickoff.**

- **A** 五項全 PASS，每項有 spec line 引用（U1 L731-735 / U2 L737-757 / U3 L592-600 / U4 L759-775 / M1 L916-920）
- **B** 無回歸。F3b↔U2 additive（U2 強化 F3b 已宣示的 fsync 承諾），F4↔U3 互補（U3 定義 IPC，F4 定義 schema + label 排除）
- **C** Mac 部署乾淨，僅兩個 YELLOW-nit（**非阻塞**，Stage 2 / 前置 CI 房務）：
  1. §7.1 可加一句 Stage 2 ort 切換時 `libonnxruntime.dylib` bundling 提醒
  2. CC #13 `strace -e fsync` 是 Linux-only，可註明「Linux CI 跑 strace，macOS CI 跑 T23 behavioral 斷言」

---

## 六、Commit 與交付

### 6.1 單一 commit

`9141e08` · `docs(edge-p3-1): evolve spec v1.0→v1.3 through 3 rounds of review` · 1 file changed, 864 insertions, 353 deletions.

選擇**單一 commit 而非多 commit**的理由：規格演化是一個連續思考過程（v1.0 → v1.3 每輪都引用前輪），拆分會讓 reviewer 難以追蹤 U1-U4 如何自然從 F1-F10 的 AI-E 學科透視演化而來。CHANGELOG 在 spec 內部分段，足夠 granular。

### 6.2 Memory 副產物

`~/.claude/projects/-home-ncyu-BybitOpenClaw-srv/memory/project_mac_deployment_target.md`（type=project）+ MEMORY.md 新增索引行 `- [未來 Mac 部署目標](project_mac_deployment_target.md) — Apple Silicon Mac（預計 M5 Ultra/Max）；CI tuple aarch64-apple-darwin 必含，linux-arm64 非主路徑`

這個 memory 會影響未來**所有**跨平台相關決策（不限於 EDGE-P3-1）：新增 CI matrix、引入 Rust crate、服務部署腳本、Python 依賴選擇等。

---

## 七、規格結構快覽（供 Stage 0 工作者參考）

| §  | 章節 | 關鍵交付 |
|---|---|---|
| §1-3 | Goal / Non-goals / Success criteria | — |
| §4 | Label schema | F1 split_flag 語意 · VWAP merge for grid · 17-feature schema |
| §5 | Data stores | F3a `disagreed` COALESCE · F4 `learning.decision_shadow_fills` · schema_hash / definition_hash drift 偵測 |
| §6 | 訓練管線 | Quantile LGBM (q10/q50/q90) · CQR · monotone rearrangement · CPCV |
| §7 | Rust 推理接線 | F2 pseudocode 順序 · F8 compile_error! 互斥 · F9 RwLock guard 紀律 + SmallRng 種子 · U3 EmitShadowFill IPC |
| §8.8 | Kill switch 協議 | F3b per-engine TOML fsync · U1 auth split · U2 write_toml_atomic_fsynced · U4 two-stage commit |
| §9 | Promotion gate | Shadow ≥14d · pinball loss >10% gain |
| §10 | 運維 / Fallback | F6 Live/Demo first-hit P2 · F10 runbook path |
| §12.3 | 13-step kickoff runbook | Stage 0 step 1-7（AI-E + PA 並行）|
| §12.4 | CC 13 項 + T1-T23 | Mac CI (#10 / M1) · fsync strace (#13 / U2) |
| §12.5 | Runbook 骨架 | P2/P3 escalation ladder |

---

## 八、Stage 0 開工就緒度

| 任務 | 負責角色 | 前置 | 狀態 |
|---|---|---|---|
| #25 | PA | SQL migration（`learning.decision_features` + `learning.decision_shadow_fills` + index）+ `parquet_etl.py` 補實現 | ⬜ ready |
| #26 | ML-MIT | quantile LGBM + CPCV + isotonic calibration + 離線 pinball loss / decile lift | ⬜ blocked by #25（feature store 就緒後）|
| #27 | AI-E | Rust `edge_predictor/` module + PyO3 ONNX runtime + `cost_gate` 接入 + shadow flag + IPC 熱重載 + `write_toml_atomic_fsynced` helper 升級 + `EmitShadowFill` IPC | ⬜ ready（step 1 `features.rs` 無前置）|
| #28 | CC | 13 項必查（v1.3 CC clist）+ T1-T23 regression | ⬜ blocked by #27 |
| #29 | — | Shadow mode 14d paper | ⬜ blocked by #26 #27 #28 |
| #30 | — | Paper engine promote 7d | ⬜ blocked by #29 |
| #31 | — | Demo engine promote + operator 確認 | ⬜ blocked by #30 |

**可並行啟動**：#25 + #27（PA SQL 與 AI-E features.rs 無相互依賴）。
**Stage 0 收尾前 doc housekeeping**：Round-4 兩個 YELLOW-nit（ort dylib / strace Linux-only 註記）。

---

## 九、時序

| 時間 | 事件 |
|---|---|
| 2026-04-14 | operator 確認 EDGE-P3-1 思路定稿，進入 TODO.md W25+ |
| 2026-04-15 早段 | FA 起草 v1.0 → round-1 QC+QA → v1.1 |
| （中段）| round-2 4× 平行審查（QC/QA/ML-MIT/AI-E）|
| 2026-04-15 午段 | operator 選 Option A（inline patch 而非 rollback）→ FA 併入 F1-F10 → v1.2 |
| （下午）| round-3 4× 平行審查 → AI-E YELLOW 提 U1-U3 |
| 2026-04-15 傍晚 | operator 指示「修掉」+ 確認 Mac 部署目標 → FA 併入 U1-U4 + M1 → v1.3 |
| 2026-04-15 傍晚 | operator「先 commit 我 compact 完再跑」→ commit `9141e08` |
| 2026-04-15 晚 | compact 後 operator 指示 round-4 AI-E 覆審 → **GREEN** |
| 本文產出 | Stage 0 kickoff 前留檔 |

---

## 十、留尾 / 非本 PR 範圍

### 已知但不在 v1.3 範圍（Stage 2 或之後）
- **ort macOS bundling 提醒**（AI-E round-4 YELLOW-nit 1）— §7.1 加一句
- **CC #13 strace Linux-only 註記**（AI-E round-4 YELLOW-nit 2）— CC #13 加一句
- **Round-2 未採納 17 項**（詳見 v1.2 CHANGELOG 未採納段）— `recent_slippage_bps_ewma`、CPCV fold 數、online learning 支線等

### 特意不處理
- **取代 LinUCB** — 本項目非 LinUCB 替代，兩者並存（LinUCB 選策略家族，edge predictor 單筆 gate）
- **觸碰現有 shrinkage fallback path** — 失敗回退現有 `shrunk_bps`，不推倒重來
- **強行綁 Phase 5 cost_gate 啟用**（與 EDGE-P3-1 同步進行）— 互為前置但解耦合實施

---

## 十一、關鍵教訓（供未來多輪規格審查參考）

1. **學科平行審查去重前要保留原始 raw finding** — 三次確認的 finding（F4）遠比單次強，沒有保留 raw 就看不出權重。
2. **AI-E 類審查要求「讀代碼反驗」而非「讀規格找矛盾」** — U1-U3 都是規格內部自洽但與實際代碼脫節，只看 spec 永遠查不出來。
3. **Round-4 covering review 可用單一 sub-agent**（相對 round-2/3 的 4× 平行）— scope 收斂時成本節約顯著。
4. **衍生 memory 副產物要當場寫入**（Mac deployment target）— 跨會話跨項目的 constraint 必須落盤，不能只留在當前規格文件。
5. **commit 粒度服務 reviewer 心智模型** — 此處選 1 commit 而非 4 commit，因為演化是連續推理而非獨立改動。
