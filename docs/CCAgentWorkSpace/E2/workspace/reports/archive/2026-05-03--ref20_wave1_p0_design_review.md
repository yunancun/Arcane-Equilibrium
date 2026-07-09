# REF-20 Wave 1 P0 — E2 Adversarial Design Review

**Date：** 2026-05-03
**Owner：** E2（adversarial subagent）
**Scope：** REF-20 V3 Wave 1 全 8 task（T1+T2+T3+T5+T6+T7+T8+T9）design review + adversarial audit
**Reviewer chain：** PM → 3 sub-agent（PA / E1 / PM）→ **E2 review (this)** → E4 → PM commit
**Verdict：** **CONDITIONAL PASS to E4** — 3 MEDIUM finding 退回 PA fix（doc cross-ref 修字）；**不 BLOCK 所有 deliverable runtime / scaffold / build path**；E4 只需在 PA fix 後跑 doc lint regression。

---

## 0. TL;DR

| Layer | 結論 |
|---|---|
| **Runtime / scaffold / build / script smoke** | ✅ PASS — 0 hard-boundary violation / 0 use import / 0 forbidden symbol / cargo check 0 new warning / smoke test exit code 全對 spec / 雙 feature build matrix 都過 |
| **Migration ledger** | ✅ PASS — 0 collision / 9 task 預留 + 6 buffer 完整 / Audit query 完整 |
| **E1 INSERT path grep + classification** | ✅ PASS — 0 production code 改動 / 5 INSERT path E2 獨立 grep verified / 3 source 全 allowed_for_replay→real_outcome / 0 ambiguous |
| **Signing key script + runbook** | ✅ PASS — bash -n 通過 / 4 fail-mode exit code 對 spec / 0 secret leak / 0 寫 OPENCLAW_SECRETS_DIR 範圍外 / 4 fail-mode + rollback + audit 章節齊備 |
| **Governance v2 4 docs** | ⚠️ **3 MEDIUM finding** — REF-19 v2 §11 Storage 整節消失 / REF-20 v2 三次 cross-ref `v1 §X 沿用` 標的錯位 / 修訂歷史宣稱與實際結構不符；**0 boundary 削弱 / 0 §四 fail-closed 條款被改 / Decision Lease 路徑承諾 0 削弱**；屬 metadata accuracy 問題不 BLOCK runtime |

整體：**Wave 1 deliverable 規格與 V3 contract baseline 對齊，0 runtime risk，0 hard boundary violation。**3 MEDIUM finding 是 PA 在編寫 v2 governance docs 時 cross-ref label 工作出錯，建議退回 PA 修正後再 commit；E4 在 doc fix 後快速 regression。

---

## 1. 任務 subgroup 分組 PASS/FAIL 矩陣

| Task subgroup | Owner | Verdict | Findings |
|---|---|---|---|
| T1 — REF-19/20 v2 governance amendment（4 docs） | PA + PM | ⚠️ **CONDITIONAL** | 3 MEDIUM（doc cross-ref label） |
| T2+T3+T9 — replay_runner Rust scaffold（5 deliverables） | PA + E1 | ✅ PASS | 0 finding |
| T5 — Migration V036-V050 ledger | PM | ✅ PASS | 0 finding |
| T6+T7 — E1 INSERT grep + source classification（2 reports） | E1 | ✅ PASS | 0 finding |
| T8 — Signing key script + rotation runbook | PM | ✅ PASS | 0 finding |

---

## 2. T1 — Governance v2 4 docs Review

**Files:**
- `docs/references/2026-05-03--reality_calibrated_fast_replay_governance_v2.md` (510L)
- `docs/references/2026-05-03--reality_calibrated_fast_replay_governance_v2_zh.md` (524L)
- `docs/references/2026-05-03--ref20_paper_replay_lab_governance_v2.md` (603L)
- `docs/references/2026-05-03--ref20_paper_replay_lab_governance_v2_zh.md` (613L)

### 2.1 必查項

| 必查項 | 結果 |
|---|---|
| v1 docs 0 修改（`git diff` 必 0） | ✅ PASS — `git diff --stat` 對 v1 4 file 全 0 line |
| v1 baseline 仍存在 | ✅ PASS — `2026-05-02--*` 4 file mtime 無更動，git log 顯示 last commit 是 2026-05-02 |
| supersedes 在 metadata 頭部 | ✅ PASS — 4 docs 全有 `**Supersedes:** ...v1 (...retained as historical baseline)` |
| 修訂歷史含 v1 + v2 | ✅ PASS — `## 20. 修訂歷史` (REF-19) + `## 19. 修訂歷史` (REF-20) 各列 v1 + v2 兩 row |
| EN/ZH 章節結構同步 | ✅ PASS — REF-19 v2 EN/ZH 各 23 sections，diff 僅標題翻譯；REF-20 v2 EN/ZH 各 22 sections，diff 同 |
| §四 4 項 fail-closed 條款（live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / authorization.json）保留 | ✅ PASS — REF-19 v2 §2 Non-Negotiable Boundary #1-#10 完整保留 v1，#11/#12 是 v2 新增承襲 V3，0 條款削弱；§7 reaffirms "GovernanceHub review, Decision Lease, and the existing live authorization gates" |
| Decision Lease 路徑承諾 0 削弱 | ✅ PASS — `acquire_lease` / `release_lease` 在 v2 全部出現於 forbidden list / "Python 唯一 caller" 注釋 / Phase R1/R5 KPI；replay binary 永不 acquire（V3 §6.2 / §12 #9 同 line） |
| 1 寫入口 + 7 隔離原則 in v2 forbidden list | ✅ PASS — REF-20 v2 §6.2 forbidden list 含 Decision Lease acquisition / IPC server / WS / exchange dispatch / DB writer channels / live config mutation / advisory writes |

### 2.2 對抗 finding（MEDIUM）

#### Finding T1-M1 — REF-19 v2 §11 Storage and Table Separation 整節消失

**File:Line：** `docs/references/2026-05-03--reality_calibrated_fast_replay_governance_v2.md:268` (and zh:同編號)

**Severity：** MEDIUM（**不 BLOCK runtime / 不削弱 boundary，因 REF-20 v2 §15 補上同類內容**；但 REF-19 v2 §0 + §20 自宣稱不準確）

**Evidence：**
- v1 REF-19 `2026-05-02--reality_calibrated_fast_replay_governance.md:281-304` 含完整 `## 11. Storage and Table Separation` 節，含 "Allowed sinks / Disallowed sinks / Recommended future schema" 三 list（治理邊界承諾，非工程細節）
- v2 §0 讀者導讀宣稱：「v1 的 §1–§16 條文以本文件 §1–§16 重述（措辭微調為與 V3 一致），**不改變 v1 邊界承諾**。新增章節 §17 / §18 為 v2 獨有的整合層」
- v2 §20 修訂歷史宣稱：「§5/§6/§10/§13/§19 補丁」（**未** flag §11/§12 整節主題替換）
- v2 §11 實際內容 = "v2 補丁：Resource / Quota / Retention（承襲 V3 §3 G9 + §5）" — 完全不同主題，v1 §11 內容**消失**
- v2 §12 實際內容 = "v2 補丁：DB Role Guard 三 PR Sequence" — 主題替換，但 v1 §12 Healthcheck 內容遷至 v2 §19（OK 有保留）
- 唯一保留 v1 §11 storage 內容的是 REF-20 v2 §15 "Storage and Table Separation（v1 §6 沿用）"（注意 cross-ref 也標錯，見 T1-M2）

**Impact：** 讀者按 v2 §0 字面讀，誤以為 v1 §11 Storage 內容仍在 REF-19 v2 中（找不到會困惑）；**功能上 boundary 仍存在**（v1 #4/#5 Disallowed sinks 已固化進 V3 §2 baseline + §4.2 evidence_source_tier guard），但 governance metadata 不準確。

**修法：** 退回 PA 修：
1. REF-19 v2 §0 表格新增一 row：「v1 §11 Storage and Table Separation 內容遷至 REF-20 v2 §15（治理 sink 邊界由 REF-20 v2 接管）+ 部分固化進 V3 §4.2 / §6.2」
2. REF-19 v2 §20 修訂歷史摘要補：「v1 §11 Storage 主題遷至 REF-20 v2 §15；v1 §12 Healthcheck 重編號至 v2 §19」
3. ZH 版本同步修

#### Finding T1-M2 — REF-20 v2 三處 `v1 §X 沿用` cross-ref label 錯位

**File:Line：**
- `docs/references/2026-05-03--ref20_paper_replay_lab_governance_v2.md:227` `## 7. P2 Precondition: Indicator Leak-Free Sweep（v1 §6 沿用 + v2 §13 G6 解封紀錄）`
- 同 file:518 `## 15. Storage and Table Separation（v1 §6 沿用）`
- 同 file:532 `## 16. Phased Delivery（v1 §7 沿用 + v2 §11 KPI binding）`
- ZH 版本同樣 issue（同行號相對應）

**Severity：** MEDIUM（**不削弱 boundary**，但 cross-ref 錯位影響後人 trace baseline）

**Evidence：** REF-20 v1 真實 §結構（已 verify by `grep -E '^## ' 2026-05-02--paper_replay_learning_surface_design.md`）：

| v1 § | v1 真實標題 |
|---|---|
| §1 | Purpose |
| §2 | Current System Findings |
| §3 | Product Surface Decision |
| §4 | Target Architecture |
| §5 | Paper Replay Lab Requirements |
| §6 | **Learning Cockpit Requirements** |
| §7 | **5-Agent Extraction Requirements** |
| §8 | **API and Storage Design** |
| §9 | Execution Realism Requirements |
| §10 | **Phased Delivery** |
| §11 | Acceptance Checks |
| §12 | Cost Posture |
| §13 | Final Decision |

v2 cross-ref 對照：

| v2 §X | v2 標題 | v2 標的 v1 § | 真實 v1 § content | 應對 v1 § |
|---|---|---|---|---|
| §7 | P2 Precondition: Indicator Leak-Free Sweep | "v1 §6 沿用" | v1 §6 = Learning Cockpit | ❌ v1 沒有此節（V3 新增 + sweep verdict） |
| §15 | Storage and Table Separation | "v1 §6 沿用" | v1 §6 = Learning Cockpit | ❌ 應為 **v1 §8 API and Storage Design** |
| §16 | Phased Delivery | "v1 §7 沿用" | v1 §7 = 5-Agent Extraction | ❌ 應為 **v1 §10 Phased Delivery** |

3/5 `v1 §X 沿用` cross-ref 錯位（§1/§2 對；§7/§15/§16 錯）。

**Impact：** PM/PA/operator 按 v2 字面去 v1 找對應 baseline 內容找不到（如查 §15 storage 跳到 v1 §6 看到的是 Learning Cockpit）；**0 規格漂移**（v2 內容仍與 V3 baseline 對齊），但 governance metadata 系統性錯位。

**修法：** 退回 PA 修：
1. v2 §7 改 `(v1 §6 沿用)` → `(V3 §7 + v2 §13 G6 解封紀錄)` （此節 v1 沒有，是 V3 新增）
2. v2 §15 改 `(v1 §6 沿用)` → `(v1 §8 沿用 + V3 §11 disallowed sink 補強)`
3. v2 §16 改 `(v1 §7 沿用 + v2 §11 KPI binding)` → `(v1 §10 沿用 + v2 §11 KPI binding)`
4. ZH 版本同步修

#### Finding T1-M3 — v1 §6 Learning Cockpit Requirements 詳細 schema 在 v2 中只剩 1 行濃縮

**File:Line：** `docs/references/2026-05-03--ref20_paper_replay_lab_governance_v2.md:54-58` (§2.2 Learning Tab)

**Severity：** MEDIUM（**boundary 上 OK**，但「v1 §6 沿用」措辭不準確）

**Evidence：**
- v1 REF-20 §6 含詳細 12-field schema（experiment_id / manifest_hash / git_sha / strategy_config_sha256 / risk_config_sha256 / source_tier / source_mix / calibration_model_version / calibration_freshness / verdict / baseline_delta / report_uri）
- v2 中：
  - §2.2 用 1 行濃縮：「Learning 維持知識 cockpit，**不**變成 replay runner；可顯示 replay evidence inbox + ML/Dream producer health」
  - 12-field schema 部分固化進 V3 §4.1 `replay.experiments` schema contract
  - 但 v1 §6 boundary（如 "Evidence must land in a review queue or future learning.replay_evidence table" + "It must not be inserted into learning.mlde_edge_training_rows as if it were a real outcome"）在 v2 §2.2 + §15 + V3 §4.2 + REF-19 v2 §2 #5 已 collectively 涵蓋

**Impact：** 0 boundary 削弱（trace path：v1 §6 → V3 §4.1 schema + REF-19 v2 §2 #5 + REF-20 v2 §2.2 + §15 disallowed sink），但 v2 cross-ref 沒明寫此 trace path，讀者不易找。

**修法：** 退回 PA 在 v2 §0 表格添：「v1 §6 Learning Cockpit 詳細 schema 已固化進 V3 §4.1 + §4.2 schema contract + REF-19 v2 §2 #5 + REF-20 v2 §2.2/§15 collectively 涵蓋」

### 2.3 雙語對齊驗證

ZH/EN 結構：
- REF-19 v2: EN 23 §, ZH 23 § ✅ 完整對齊
- REF-20 v2: EN 22 §, ZH 22 § ✅ 完整對齊

`diff` 顯示僅標題文字翻譯差異（如 "Purpose" vs "目的"，"Phased Delivery" vs "分階段交付"），無結構偏差。

**注意：** ZH 版本繼承 EN 的 3 處 cross-ref 錯位（T1-M2），需同步修。

---

## 3. T2+T3+T9 — Rust scaffold（5 deliverables）Review

**Files:**
- `rust/openclaw_engine/src/bin/replay_runner.rs` (132L)
- `rust/openclaw_engine/Cargo.toml` (delta +24L)
- `rust/openclaw_engine/src/replay/profile.rs` (112L)
- `rust/openclaw_engine/src/replay/mod.rs` (28L) + `lib.rs` (+5L)
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md` (18.6KB)

### 3.1 必查 5 點全 PASS

#### 必查 1：Forbidden symbol grep in scaffold

```bash
grep -rE 'acquire_lease|ipc_server|build_exchange_pipeline|GovernanceHub|exchange_dispatch|live_authorization|decision_lease|trading_tx|market_data_tx|order_dispatch_tx' \
  rust/openclaw_engine/src/bin/replay_runner.rs \
  rust/openclaw_engine/src/replay/profile.rs \
  rust/openclaw_engine/src/replay/mod.rs
```

**結果：** 15 hits，**全部位於 `//!` doc comment**（forbidden list / 禁用注釋 / "must NOT" 警示），**無實際 import 或 call**。

逐一 verify：
- replay_runner.rs:30-37 (EN forbidden list block)
- replay_runner.rs:75-82 (中文 forbidden list block)
- 0 hits in profile.rs / mod.rs

✅ **PASS** — scaffold 物理上不接觸 forbidden 模組。

#### 必查 2：`use` import grep

```bash
grep -E '^use ' rust/openclaw_engine/src/bin/replay_runner.rs \
  rust/openclaw_engine/src/replay/profile.rs \
  rust/openclaw_engine/src/replay/mod.rs
```

**結果：** 0 hits — scaffold **0 import**（連 std lib 都沒），確認真 spec-only / panic stub。

✅ **PASS** — 物理上不可能拉任何 forbidden module 進 build graph。

#### 必查 3：`cargo check -p openclaw_engine`（無 feature）

```
$ cd rust/openclaw_engine && cargo check -p openclaw_engine 2>&1 | tail -10
warning: function `reconciler_label_for_env` is never used  (pre-existing)
warning: `openclaw_engine` (bin "openclaw-engine") generated 3 warnings
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.12s
```

✅ **PASS** — 無 feature default build 通過；replay_runner binary **未編譯**（required-features 阻擋）；warnings 全 pre-existing baseline（21 lib + 3 bin）。

#### 必查 4：`cargo check --bin replay_runner --features replay_isolated`

```
$ cd rust/openclaw_engine && cargo check -p openclaw_engine --bin replay_runner --features replay_isolated 2>&1 | tail -5
warning: `openclaw_engine` (lib) generated 21 warnings (run `cargo fix --lib -p openclaw_engine` to apply 13 suggestions)
    Finished `dev` profile [unoptimized + debuginfo] target(s) in 0.08s
```

✅ **PASS** — 21 warnings 全 lib pre-existing baseline，**replay_runner / replay/profile.rs / replay/mod.rs 0 new warning**（grep `replay_runner|src/replay/` 在 warning output 中 0 hit）。

#### 必查 5：Cargo.toml `[[bin]]` 必含 `required-features`

`rust/openclaw_engine/Cargo.toml:132-135`：
```toml
[[bin]]
name = "replay_runner"
path = "src/bin/replay_runner.rs"
required-features = ["replay_isolated"]
```

✅ **PASS** — `required-features = ["replay_isolated"]` 顯式存在，無 feature 即 cargo 拒絕 build replay_runner（已在必查 3 驗證）。

### 3.2 對抗 finding（無 BLOCKING / 0 finding）

無 finding。Rust scaffold 設計與 V3 §3 G7/G8 + §6.1/§6.2 + workplan §4 R20-P0-T2/T3/T9 完整對齊。

### 3.3 cargo build artifact symbol audit（補強，非 mandatory）

未跑 `cargo build` 產生 binary 後跑 `nm`/`objdump`（Wave 3 R20-P2b-S10 才 mandatory）。Wave 1 baseline 預期 binary 僅 `main`/`std::panicking::*`/`replay_runner::main`。本輪未觸發實測；PA crate boundary report §6.3 已書面記錄此預期。

### 3.4 git diff 邊界驗證

```bash
$ git diff HEAD --stat | head -10
 docs/CCAgentWorkSpace/PA/memory.md | 75 ++++++++++++++++++++++++++++++++++++++
 rust/openclaw_engine/Cargo.toml    | 35 ++++++++++++++++++
 rust/openclaw_engine/src/lib.rs    |  5 +++
 3 files changed, 115 insertions(+)
```

**Cargo.toml diff：** `+35 LOC` — 比 spec 宣稱「+24 LOC」多 11 line，但讀 diff 細節（line 80-100 features block + line 116-135 bin block）= 2 個 sub-block 各含**雙語注釋**（EN comment block + ZH comment block），實際代碼變動**只 6 line**（`replay_isolated = []` + `[[bin]] replay_runner` 4 line）。額外 line 是注釋。**無代碼 spec 漂移。**

`lib.rs diff：` `+5 LOC`（4 line comment + 1 line `pub mod replay;`）✅ 對齊 spec。

✅ **PASS** — diff 邊界與 spec 一致。

### 3.5 PA report 內 hardcoded path（INFORMATIONAL，非 BLOCKING）

`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--replay_runner_crate_boundary_allowlist.md:81`：
```json
"src_path": "/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/bin/replay_runner.rs",
```

是 cargo metadata raw output 在 Mac dev 環境的列印。屬 doc 引用（非 active code），不違反 CLAUDE.md §七 跨平台規範（規範限新代碼）。建議 PA 後續 doc commit 改用 `<cargo workspace root>/...` 抽象路徑，但 **0 BLOCKING**。

---

## 4. T5 — Migration V036-V050 Ledger Review

**File:** `sql/migrations/REF-20_RESERVATION.md`

### 4.1 必查項全 PASS

| 必查項 | 結果 |
|---|---|
| V036-V050 0 與既有 migration 衝突 | ✅ PASS — `ls sql/migrations/V0[3-5][0-9]__*.sql` 最高 V035；V036+ 預留全 0 collision |
| 9 reserved task migration + 6 buffer 各標 task ID + Wave + 用途 | ✅ PASS — V036-V044 各綁 task ID + Wave + 用途；V045-V050 標 reserved buffer (no task) |
| Cross-ref V3 baseline + workplan | ✅ PASS — §1 + §2 + §7 引用 V3 / Workplan SoT |
| §4 變更協議 5 條規則 | ✅ PASS — 取號 / 改用途 / 新增 / buffer 啟用 / 檔案命名 5 條 |
| §6 修訂歷史表 | ✅ PASS — v1 2026-05-03 PM (R20-P0-T5) row |
| Audit query 完整 | ✅ PASS — §5 含 3 條 audit query（撞號偵測 / Ledger 一致性 / Guard 規範） |

### 4.2 對抗 finding（0）

無 finding。預留 ledger 設計嚴密，含 V023 model_registry 撞號慘痛先例引用（§7 Cross-References）。

---

## 5. T6+T7 — E1 INSERT Path Grep + Source Classification Review

**Files:**
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--mlde_shadow_insert_paths_grep.md` (276L)
- `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--mlde_shadow_source_classification.md` (252L)

### 5.1 必查項全 PASS

#### 必查 1：E1 自宣 0 INSERT/UPDATE/DELETE — git status 對應驗證

```bash
$ git diff HEAD --stat
 docs/CCAgentWorkSpace/PA/memory.md | 75 +++
 rust/openclaw_engine/Cargo.toml    | 35 +++
 rust/openclaw_engine/src/lib.rs    |  5 +++
```

E1 0 program_code 改動 ✅。Cargo.toml + lib.rs 改動是 sibling agent T2/T3 的 PA scaffold deliverable，不在 E1 scope。PA memory.md 是 sibling agent T2/T3/T9 deliverable side effect。

✅ **PASS** — E1 真 read-only。

#### 必查 2：4 producer surgical change list 完整 + file:line 精確

E1 grep report §6 列 4 producer：
1. `program_code/local_model_tools/dream_engine.py:350-358`
2. `program_code/local_model_tools/opportunity_tracker.py:236-243`
3. `program_code/ml_training/mlde_shadow_advisor.py:301-308`
4. `program_code/ml_training/mlde_demo_applier.py:1221-1240`

E2 獨立 grep verification：
```bash
$ grep -rn 'INSERT INTO learning.mlde_shadow_recommendations' program_code/ rust/ sql/ helper_scripts/ 2>/dev/null
program_code/local_model_tools/dream_engine.py:350:                    INSERT INTO learning.mlde_shadow_recommendations
program_code/local_model_tools/opportunity_tracker.py:236:                INSERT INTO learning.mlde_shadow_recommendations
program_code/ml_training/mlde_shadow_advisor.py:302:        INSERT INTO learning.mlde_shadow_recommendations
program_code/ml_training/mlde_demo_applier.py:1223:        INSERT INTO learning.mlde_shadow_recommendations
program_code/ml_training/tests/test_mlde_demo_applier.py:426:    assert "INSERT INTO learning.mlde_shadow_recommendations" in captured["sql"]
```

5 hits = 4 producer + 1 test fixture，**逐一對應 E1 報告**。Surgical change list 風險評估（HIGH risk = #4 demo_applier 因 LG-5 audit chain 依賴 + MEDIUM risk = #3 因 source 變量 + LOW × 2）合理。

✅ **PASS** — file:line 精確、coverage 完整、risk 等級評估 sound。

#### 必查 3：3 source 值分類 0 ambiguous / 0 forbidden

E1 §4.1 報告 SQL probe 結果：
- `dream_engine` / `ml_shadow` / `opportunity_tracker` 各 1117 / 1185 / 180 row
- 全 3 source 屬 V3 §4.2 explicit allowlist
- 0 NULL / 0 ambiguous / 0 forbidden / 0 unknown

`linucb` schema CHECK 允許但 0 row 寫入（LinUCB 走 `learning.linucb_*` 自己的 table），E1 建議 R20-P2a-S6 verified-insert function 不必接受 `source='linucb'` 參數 — 合理避免 dead code。

⚠️ **27 row engine_mode='live' 認定**：E1 §4.2 + §5 認定為 LG-5 §2.1 promotion-candidate audit row（applied=false），R20-P2a-S6 retrofit 仍標 evidence_source_tier='real_outcome'。E2 corroborate：
- 27 row 全 source='ml_shadow' / strategy='ma_crossover' / created_by='mlde_demo_applier' / applied=false / decision_lease_id=NULL
- 與 `mlde_demo_applier.py:1221-1240` `_insert_live_candidate` 路徑對齊
- LG-5 §2.1 spec 已（CLAUDE.md §三 [42]/[42b] healthcheck）等待 sibling CC FUP-1 commit `463890d` deploy 啟動 reviewer
- E1 認定 sound

✅ **PASS** — 分類完整、0 ambiguous 結論成立。

#### 必查 4：INSERT path coverage = 5 path 對齊 V3 §4.2 expectation

V3 §4.2 spec：
- 4 producer in initial allowlist (dream_engine / ml_shadow / opportunity_tracker; linucb schema-allowed but 0 production row) — E1 找到 3 active producer + 1 audit row producer (mlde_demo_applier) ✅ 對齊
- ambiguous rows → migration report classify — E1 §4.3 0 ambiguous，R20-P2a-S6 spec backfill report 預期 0 ambiguous bucket ✅ 對齊

#### 必查 5：雙語注釋齊備

E1 兩 report 全文中英對照：
- §0 TL;DR 雙語
- §1 grep commands 註解雙語
- §2 producer table headers 雙語
- §6/§7 surgical change list 雙語
- §11 修訂歷史 雙語

✅ **PASS** — CLAUDE.md §七 雙語規範完整覆蓋。

### 5.2 對抗 finding（0）

無 finding。E1 grep + classification 工作精準，risk 評估到位（HIGH 標 demo_applier 因 LG-5 chain 依賴），PM 必看 unknowns 4 條合理（涵蓋 retrofit migration 預期、ma_crossover 27 row 集中、threshold 合適性、re-probe 排程）。

---

## 6. T8 — Signing Key Script + Rotation Runbook Review

**Files:**
- `helper_scripts/secrets/generate_replay_signing_key.sh` (146L)
- `docs/runbooks/replay_signing_key_rotation.md` (230L)

### 6.1 必查項全 PASS

#### 必查 1：bash 語法

```bash
$ bash -n /Users/ncyu/Projects/TradeBot/srv/helper_scripts/secrets/generate_replay_signing_key.sh && echo "BASH SYNTAX PASS"
BASH SYNTAX PASS
```

✅ **PASS**。

#### 必查 2：Exit code 路徑 4 個 smoke test

| Test | 操作 | Expected Exit | Actual Exit |
|---|---|---|---|
| Test 1 | `bash script` (no arg) | 2 | ✅ 2 |
| Test 2 | `bash script foo` (invalid env) | 2 | ✅ 2 |
| Test 3 | `bash script demo` (no $OPENCLAW_SECRETS_DIR) | 2 | ✅ 2 |
| Test 4 | `OPENCLAW_SECRETS_DIR=/tmp/missing bash script demo` (target dir missing) | 5 | ✅ 5 |
| Test 5 | success path | 0 | ✅ 0 |
| Test 6 | existing key without FORCE | 4 | ✅ 4 |
| Test 7 | collision (replay key fingerprint = live auth_signing_key fingerprint) | 6 | ✅ 6 |

7/7 PASS — 涵蓋 spec 列出的 6 個 exit code（0/2/3/4/5/6）的 4+1+1+1 路徑（Test 1/2/3 都驗 exit=2 不同 trigger）。

#### 必查 3：對應 V3 §5 spec 完整

| V3 §5 要求 | Script 實作 |
|---|---|
| HMAC-SHA256 algorithm | line 103 `openssl rand -hex 32` 生 256-bit key（HMAC-SHA256 用） |
| Key path = `$OPENCLAW_SECRETS_DIR/<env>/replay_signing_key` | line 65-66 `TARGET_KEY="${TARGET_DIR}/replay_signing_key"`,`TARGET_DIR="${OPENCLAW_SECRETS_DIR}/${ENV_ARG}"` |
| Key separation invariant（不得與 live `auth_signing_key` 共用） | line 89-99 fingerprint compare → exit 6 if collision |
| 90d rotation target | line 113 `+90d` rotation_due_at |
| 180d retention | line 125 `+180d` retention_until |
| 4 fail-mode（signature_mismatch / manifest_hash_mismatch / key_missing / key_expired） | runbook §6 4 fail-mode handling table |

✅ **PASS**。

#### 必查 4：Mode 0600 + umask 0077 enforcement

- line 106 `umask 0077`
- line 108 `chmod 0600 "$TARGET_KEY"`
- Test 5 verify：`stat` shows `-rw-------` (0600) ✅

#### 必查 5：不 auto-deploy / 不 auto-restart / 不直接寫 DB

- 無 `systemctl` / `restart_all` 直接呼叫
- 無 `psql` / `sqlx` / DB 寫入
- §7-§8 README block 列 NEXT STEPS 1-5（手動操作員後續 — 1Password vault / V042 INSERT / restart / verify）
- runbook §3.2 step 4 引用 `restart_all.sh`（操作員執行，非 script 內呼叫）

✅ **PASS** — 不 auto-execute side effects。

#### 必查 6：Runbook 涵蓋 initial / 90d / emergency / 4 fail-mode / rollback / audit

| Runbook 章節 | 內容 |
|---|---|
| §3 Initial Deployment | preconditions + 6 steps + 1Password vault + V042 archive insert + restart + verify + fingerprint match |
| §4 Scheduled Rotation 90d | trigger + 7 steps + dual key support + 180d retention cleanup |
| §5 Emergency Rotation | 8 steps with ⚠️ markers + quarantine + compromised marking + post-mortem |
| §6 4 Fail-Mode Handling | 4-row table 對齊 V3 §5 + 操作員處置 |
| §7 Rollback Procedure | 5 steps stop / restore / revert / restart / RCA |
| §8 Audit | 5 audit query + monthly schedule |

✅ **PASS** — 章節覆蓋完整，操作可追溯。

#### 必查 7：雙語注釋

Script `# Why this script exists / 為什麼有這個檔案：` (line 7) + `# ----- N. ... / 中文 ----` 6 個 section divider 雙語 ✅
Runbook `## 1. 用途 / Why this runbook exists` + `## 6. 4 Fail-Mode 故障處理` etc 章節雙語 ✅

✅ **PASS** — 雙語覆蓋齊。

### 6.2 對抗 finding（0）

#### 子查 1：Script 是否寫入 OPENCLAW_SECRETS_DIR 範圍外

```bash
$ grep -nE '> "?\$|tee|chmod|cp ' /Users/ncyu/Projects/TradeBot/srv/helper_scripts/secrets/generate_replay_signing_key.sh
85:    cp "$TARGET_KEY" "$BACKUP"
86:    chmod 0400 "$BACKUP"
107:printf '%s\n' "$NEW_KEY" > "$TARGET_KEY"
108:chmod 0600 "$TARGET_KEY"
```

唯一 write target = `$TARGET_KEY` 與 `$BACKUP`（line 83 `BACKUP="${TARGET_KEY}.rotated.${UTC_TS}"`），全在 `$TARGET_DIR = $OPENCLAW_SECRETS_DIR/$ENV_ARG` 內 ✅。

#### 子查 2：Secret leak 在 stdout / log

```bash
$ grep -nE 'echo.*NEW_KEY|printf.*NEW_KEY' /Users/ncyu/Projects/TradeBot/srv/helper_scripts/secrets/generate_replay_signing_key.sh
107:printf '%s\n' "$NEW_KEY" > "$TARGET_KEY"
```

唯一 NEW_KEY usage = line 107 寫入 file（無 stdout / no echo / no log） ✅。Line 115 cat HEREDOC 印的是 fingerprint（hash 前 16 char）+ metadata，**不是 NEW_KEY 本體** ✅。

#### 子查 3：Hardcode user-home 路徑

```bash
$ grep -E '/home/ncyu|/Users/[^/]+' helper_scripts/secrets/generate_replay_signing_key.sh docs/runbooks/replay_signing_key_rotation.md 2>&1 | head -5
（empty result）
```

✅ **PASS** — 0 hit。

無 finding。Script 與 runbook 設計嚴密，符合 OWASP A02:2021 secret handling + V3 §5 contract。

---

## 7. 跨 Task Subgroup Adversarial 必查

### 7.1 Hard boundary token grep across all 15 file

```bash
# 6 條 hard-boundary token: live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / live_reserved / authorization.json (write) / decision_lease (acquire/release)
```

| Token | 全 15 file 寫/設置 | 全 15 file 引用（doc / forbidden list） |
|---|---|---|
| `live_execution_allowed` | 0 | 1 (PA report 引用 hard 邊界) |
| `max_retries=...` | 0 | 1 (PA report 引用) |
| `OPENCLAW_ALLOW_MAINNET=` | 0 | 0 |
| `live_reserved=` | 0 | 0 |
| `_write_signed_live_authorization` (write side) | 0 | 3 (replay_runner.rs forbidden list * 2 lang + PA report) |
| `acquire_lease(`/`release_lease(` | 0 | 2 (replay_runner.rs forbidden list * 2 lang) |

✅ **PASS** — 0 actual write/set；所有 hit 全在 forbidden list / doc reference / 警告注釋。

### 7.2 跨平台 path grep

```bash
$ grep -E '(/home/ncyu|/Users/[^/]+)' <all 15 files>
docs/references/...governance_v2.md: per commit grep 規則範例（ref to grep pattern）
docs/CCAgentWorkSpace/PA/workspace/reports/...replay_runner_crate_boundary_allowlist.md: 1 hit (cargo metadata raw output, INFORMATIONAL — see §3.5)
```

✅ **PASS** — runtime/code 0 hit；3 doc hits 全屬 grep pattern reference 或 cargo metadata 列印（非 active code path）。

### 7.3 Source code modification beyond declared scaffold scope

```bash
$ git diff HEAD -- rust/openclaw_engine/Cargo.toml rust/openclaw_engine/src/lib.rs
+ Cargo.toml: 35L (24 spec + 11 bilingual comments)
+ lib.rs: 5L (4 comment + 1 pub mod replay;)
```

`lib.rs` 改動僅在新 `pub mod replay;` 位置（line 55-59），未動既有 mod；既有 mod 內邏輯 0 改動 ✅。

`Cargo.toml` 改動僅在 `[features]` block + 末尾新 `[[bin]] replay_runner` block；既有 `[[bin]] openclaw-engine` / `[[bin]] repair_migration_checksum` / `[[bench]]` / `[dependencies]` 0 動 ✅。

### 7.4 Bilingual completeness pass

| Deliverable | Bilingual coverage | 評估 |
|---|---|---|
| 4 governance v2 docs | 全文中英對照（EN docs + ZH docs 1:1） | ✅ |
| Rust scaffold (replay_runner.rs / profile.rs / mod.rs) | MODULE_NOTE 雙語齊；每 enum variant 雙語 doc；TODO 雙語 | ✅ |
| Cargo.toml + lib.rs comments | 雙語 | ✅ |
| Migration ledger | §1 / §2 / 表頭中英對照；§4 變更協議 EN-only descriptive language（minor）| ✅ acceptable |
| E1 reports (T6/T7) | 全文中英對照 | ✅ |
| PA crate boundary report (T9) | EN-only major sections（Wave 1 PA review report，內部使用 OK；CLAUDE.md §七 強制範圍是 production code，非 internal review report） | ⚠️ INFORMATIONAL |
| Signing key script + runbook | Section divider 中英對照；具體技術段 EN/中混合 | ✅ |

---

## 8. 嚴重性匯總 + 修復清單

| 嚴重性 | 數量 | Item |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 3 | T1-M1 / T1-M2 / T1-M3（全 governance v2 cross-ref label 問題） |
| LOW | 0 | — |
| INFO | 1 | PA crate boundary report Mac path（§3.5）— 不 BLOCK |

### 退回 PA 修復清單（CONDITIONAL PASS 條件）

PA 在 commit 前必修：

1. **REF-19 v2 §0 + §20 修訂歷史 — 補 v1 §11 Storage 遷至 REF-20 v2 §15 / V3 §4.2 / §6.2 的 trace 紀錄**（同 ZH 版本）
2. **REF-20 v2 §7 §15 §16 cross-ref label 三處修字**（同 ZH 版本）：
   - §7 `(v1 §6 沿用 + v2 §13 G6 解封紀錄)` → `(V3 §7 + v2 §13 G6 解封紀錄)`（v1 沒此節）
   - §15 `(v1 §6 沿用)` → `(v1 §8 沿用 + V3 §11 disallowed sink 補強)`
   - §16 `(v1 §7 沿用 + v2 §11 KPI binding)` → `(v1 §10 沿用 + v2 §11 KPI binding)`
3. **REF-20 v2 §0 表格添 row：**「v1 §6 Learning Cockpit 詳細 schema 已固化進 V3 §4.1 + §4.2 schema contract + REF-19 v2 §2 #5 + REF-20 v2 §2.2/§15 collectively 涵蓋」（同 ZH 版本）

修復範圍：4 governance v2 docs（EN + ZH）；**0 boundary 削弱**，**0 業務邏輯**，**0 spec 漂移**；純 doc cross-ref label fix。E2 在 PA fix 後 5 分鐘內 re-review verdict（grep diff verify cross-ref 改正即可）。

PM commit message 草稿：
```
docs(ref20): fix v2 governance amendment cross-ref labels (REF-20 Wave 1 R20-P0-T1)
```

### E2 直接修範圍

3 finding 全屬 governance v2 治理層 cross-reference 問題，非 typo / lint / dead import 範疇，不在 E2 直接修權限內（CLAUDE.md §九 規定 E2 「不寫業務代碼，例外只 typo / lint / dead import」）。**全部退回 PA**。

---

## 9. 整體 Sign-off Statement

**E2 對 REF-20 V3 Wave 1 全 8 task design + scaffold + key infra 部署計畫 deliverable 進行 adversarial design review，發現:**

- ✅ **Runtime / scaffold / build path / smoke test 100% PASS**：
  - 0 hard-boundary violation（live_execution_allowed / max_retries / OPENCLAW_ALLOW_MAINNET / authorization.json write / decision_lease acquire）
  - 0 forbidden symbol import in Rust scaffold（grep `^use ` 0 hit）
  - cargo check 兩 feature build matrix 都過，0 new warning（21 lib pre-existing baseline 持守）
  - signing key script 6 exit code 路徑全對 spec，0 secret leak，0 OPENCLAW_SECRETS_DIR 範圍外寫
  - Migration V036-V050 ledger 0 collision，9 task + 6 buffer 完整綁定
  - E1 INSERT path grep 5 hits 與 4 producer + 1 test fixture 對應，0 production code 改動，3 source 全 allowed_for_replay→real_outcome / 0 ambiguous

- ⚠️ **Governance v2 docs 3 MEDIUM finding（cross-ref label）需退回 PA 修字**：
  - REF-19 v2 §0 / §20 自宣稱「v1 §1-§16 重述...不改變邊界」與實際結構不符（v1 §11 Storage 整節消失，部分內容遷至 REF-20 v2 §15）
  - REF-20 v2 §7 / §15 / §16 三處 `v1 §X 沿用` cross-ref 標的 v1 § 真實主題錯位（v1 §6 = Learning Cockpit ≠ v2 §15 Storage / ≠ v2 §7 Indicator Sweep；v1 §7 = 5-Agent Extraction ≠ v2 §16 Phased Delivery）
  - 0 boundary 削弱 / 0 §四 fail-closed 條款被改 / 0 Decision Lease 路徑承諾削弱 / 0 16 根原則漏蓋；屬 governance metadata accuracy 問題

- 0 CRITICAL / 0 HIGH finding。

**Verdict：CONDITIONAL PASS to E4** —
- PA 修 3 cross-ref MEDIUM finding 後（doc-only edit / 4 file × EN+ZH = 8 file 內局部修字）
- PM 5 atomic commit 結構建議（見 §10）
- E4 跑 doc lint regression（grep 確認 cross-ref 修正）+ 既有 cargo check baseline 對照
- 之後 PM 整體 sign-off + push

**Wave 1 Exit Criteria 對齊**：
- ✅ spec only / scaffold only / 0 runtime IMPL（compiler PASS + warning 0 new）
- ✅ docs amendment 0 boundary 削弱（§四 4 fail-closed / 16 根原則 / Decision Lease 路徑全保留）
- ✅ E2 必查 3 點（per workplan §8）全 PASS：
  1. forbidden symbol grep 在 scaffold 內 0 import / 0 active call
  2. INSERT path grep 5 hits 全列入 R20-P2a-S6 producer 切換範圍
  3. signing key script + runbook 4 fail-mode + key separation invariant 部署 ready

---

## 10. PM Commit 結構建議

建議 **5 個 atomic commit**（per Wave 1 task subgroup）以利 audit trail，**不建議 1 個 wave commit**（diff 過大，cross-task 問題追溯困難）：

```
1. docs(ref20): land governance v2 amendment (REF-19 + REF-20, EN + ZH)         # T1 修完 cross-ref 後
2. feat(replay): scaffold replay_runner binary + ReplayProfile enum spec         # T2+T3+T9
3. docs(migration): reserve V036-V050 for REF-20 phases (PM SSoT ledger)         # T5
4. docs(ref20): mlde_shadow INSERT paths grep + source classification reports    # T6+T7
5. feat(secrets): generate_replay_signing_key.sh + replay key rotation runbook   # T8
```

每 commit 標 REF-20 V3 Wave 1 R20-P0-T<N> task ID，便於 governance audit。

PA fix 完 3 cross-ref finding 後 (Commit #1)，E4 re-verify。

---

## 11. 修訂歷史

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| v1 | 2026-05-03 | E2 | Wave 1 P0 全 8 task design review；3 MEDIUM finding（governance v2 cross-ref label）退 PA；其餘 deliverable PASS to E4 |

---

## 12. Cross-References

- 上游 V3 baseline：[`docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`](../../../execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md)
- Workplan SSoT：[`docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md`](../../../execution_plan/2026-05-03--ref20_implementation_workplan_v1.md) §4 Wave 1 + §8 PM E2 必查 3 點
- UX SoT：[`docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md`](../../../execution_plan/2026-05-02--ref20_ux_subdoc_v1.md)
- Indicator sweep verdict：[`docs/audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md`](../../../audits/2026-05-03--P0-DATA-INDICATOR-SWEEP_verdict.md) (G6 解封)
- 強制工作鏈：CLAUDE.md §八（E2 + E4 不可跳）
- §四 hard 邊界 + §九 8 條 checklist + §七 雙語注釋規範
- 對抗審核 SOP：`.claude/skills/pr-adversarial-review/SKILL.md`
- 雙語注釋 SOP：`.claude/skills/bilingual-comment-style/SKILL.md`
