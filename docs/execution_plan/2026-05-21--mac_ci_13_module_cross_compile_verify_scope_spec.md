---
spec: Mac CI 13-Module Cross-Compile Verify Scope Specification
date: 2026-05-21
author: E5（Optimization Engineer）— Sprint 1A-ε deliverable
phase: v5.8 Sprint 1A-ε（W6.5-8.5）integration verify + cross-ADR consistency
status: SPEC-DRAFT-V0（analysis + scope spec only；本 spec 不寫 IMPL `.yml` file，亦不寫 Rust/Python code；E1 future IMPL 寫實 workflow）
parent specs:
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 13 module + §9 V099-V116 schema migration roster
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md §Sprint 1A-ε deliverable（Mac CI 全 13 module cross-compile verify）+ H-19 sibling structure + H-20 Apple Silicon CI tuple
  - srv/.github/workflows/ci.yml（既有 ci.yml 範式：push Linux only / PR + 週一 cron macOS）
  - memory `feedback_github_actions_cost`（Private repo 2000 min/月免費；macOS 10x cost；macOS PR only + 週一 cron）
  - memory `project_mac_deployment_target`（Apple Silicon Mac；CI tuple `aarch64-apple-darwin` 必含；linux-arm64 非主路徑）
related ADRs:
  - ADR-0034（M1 LAL）/ ADR-0035（M5 online learning interface reserved trait stub）/ ADR-0036（M8 anomaly + M10 Tier D model blacklist）/ ADR-0037（M9 A/B framework）/ ADR-0038（M11 continuous counterfactual replay）/ ADR-0039（M12 OrderRouter trait + maker_fill_rate_30d metric 6-method）/ ADR-0040（M13 multi-venue gate spec；DEX/Hyperliquid hardcode reject + Binance trade Y3+ at earliest）/ ADR-0041（ContextDistiller v4 + AI cost cap）
related V###:
  - V099-V104（v5.7 baseline；Sprint 1A-α land）
  - V105/V106/V107/V108/V109/V110/V111/V112/V113（v5.8 CRITICAL + ADD module；Sprint 1A-β/γ land）
  - V114/V115/V116（M5/M12/M13 reserved frontmatter only；Sprint 1A-δ land）
scope:
  - analysis + scope spec（13 module × 2 OS × 2 target verify matrix）
  - CI workflow `.github/workflows/sprint_1a_module_verify.yml` 結構（spec only；不寫實 .yml）
  - Acceptance Criteria 5-7 條
  - IMPL phase split（Sprint 1A-ζ spike for 3 critical module / Sprint 4-8 全 13 module）
  - Risk + mitigation（macOS 10x cost / Apple Silicon vs Linux platform diff / Python ↔ Rust IPC schema drift）
  - Cross-V### + cross-ADR alignment
  - Open Q + Sign-off matrix
non-scope:
  - 寫實 Rust / Python IMPL code（13 module 各自走 Sprint 4-8 IMPL）
  - 寫實 `.github/workflows/sprint_1a_module_verify.yml` file（E1 future IMPL 寫；本 spec 只設計結構）
  - 改現有 `.github/workflows/ci.yml`（既有 ci.yml 不動；本 spec 是 new sibling workflow proposal）
  - 派下游 sub-agent
  - 改 ADR / 改 TODO / commit
---

# Mac CI 13-Module Cross-Compile Verify Scope Specification

## §1 Context + 為什麼

### 1.1 Sprint 1A 完整 13 module DESIGN land 但 0 IMPL code

per `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §3 + `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §Sprint 1A 五階段：

- Sprint 1A-β/γ/δ 已 land 全 13 module 的 **DESIGN spec + V### schema spec + 7 ADR**
- Sprint 1A-ζ spike（per `2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md`）只覆蓋 critical-path 3 module（M1 LAL / M3 health / M11 replay）的 IMPL skeleton
- 其餘 10 module（M2/M4/M5/M6/M7/M8/M9/M10/M12/M13）IMPL 走 Sprint 4-8 per module spec §IMPL phase split
- v5.8 §3 上方表預期 Sprint 1A-ε deliverable 之一 = **「Mac CI 全 13 module cross-compile verify」**

本 spec 為 Sprint 1A-ε 這一條 deliverable 的設計文件，**不是 IMPL workflow file**（IMPL `.yml` 由 E1 在 spike pass 後或 Sprint 4 first IMPL wave 啟動時寫）。

### 1.2 Mac CI 為 Apple Silicon 跨平台 portability gate

per `CLAUDE.md` §六 Runtime Reality And Startup：

```
Mac is the development machine.
Linux trade-core is the active runtime machine.
New code must remain portable to future Apple Silicon deployment: no
hard-coded /home/ncyu, /Users/ncyu, or machine-specific TradeBot paths in
production code.
```

per memory `project_mac_deployment_target`：

- 未來部署目標 = **Apple Silicon Mac**（M5 Ultra / M5 Max；統一記憶體 + Neural Engine + Metal）
- CI tuple `aarch64-apple-darwin` 必含
- linux-arm64 非主路徑（NAS / Pi 升 ARM 才議）
- 跨平台 invariant：psutil Linux-specific API、`epoll`-only async stack、SSE/AVX intrinsics 必 `#[cfg]` 守衛

per memory `feedback_cross_platform`：

- Mac/Linux 同等性能
- 不得硬編碼 user home（`/home/ncyu` / `/Users/ncyu`）
- LLM 走 `LocalLLMClient`-style 抽象，不直接 HTTP

13 module 在 Sprint 1A 階段 IMPL 體量小（多為 schema + trait skeleton），**正是建立 cross-platform CI guardrail 的最佳時機** — 越晚補越貴（IMPL 體量增長後 retrofit cost 高）。

### 1.3 為什麼 Sprint 1A-ε 做 verify spec 而非 IMPL

- Sprint 1A-ε 是 integration verify + cross-ADR consistency phase（per v5.8 §3 上方表 + PA dispatch consolidation §Sprint 1A 五階段）
- 體量上「設計 verify SOP」+「列 acceptance matrix」+「定 dispatch packet」屬於 spec phase；E1 IMPL `.yml` 在 Sprint 1A-ε 期末或 Sprint 4 first wave 才動
- Spec 階段先 land cross-V### / cross-ADR / Mac vs Linux 差異點清單，避免 IMPL 時臨時補 = 重複 audit
- E5 不寫 IMPL code 是角色硬約束（per `E5/profile.md` 角色定位）

### 1.4 既有 CI workflow 不動

`srv/.github/workflows/ci.yml`（2026-05-09 land）已含 3 個 job：

| Job | Runner | Target | Trigger |
|---|---|---|---|
| `stable-id-duplication-guard` | `ubuntu-latest` | n/a（bash check） | push + PR + cron |
| `rust-check-linux` | `ubuntu-latest` | `x86_64-unknown-linux-gnu` | push + PR + cron |
| `rust-check-macos` | `macos-latest` | `aarch64-apple-darwin` | PR + cron only（per `if: github.event_name != 'push'`）|

既有 ci.yml 為 baseline 不動。本 spec 提的新 workflow（`sprint_1a_module_verify.yml`）作為 **sibling workflow**：

- 觸發條件同 ci.yml（PR + 週一 cron；不 push trigger macOS）
- Scope 為 13 module 對 cargo check / cargo test --no-run / clippy / Python lint 的 verify matrix
- 與 ci.yml 並存；不取代

---

## §2 13 module Workspace Structure（Target Sprint 4-8 IMPL 階段）

per `srv/rust/Cargo.toml` 現 workspace 3 member：`openclaw_types` / `openclaw_core` / `openclaw_engine`。13 module IMPL 階段預期 workspace structure：

### 2.1 Rust module → crate / sub-module 對應建議

| # | Module | 建議 Rust 路徑 | 性質 | IMPL 階段 |
|---|---|---|---|---|
| M1 | LAL（Layered Approval Lease） | `rust/openclaw_engine/src/governance/lal/` 子模組（不新 crate；governance/ 已存在 module path）| sub-module；hot path 鄰近 decision lease | Sprint 4 LAL 1 IMPL；spike Track A 已 land |
| M2 | Overlay state machine | `rust/openclaw_engine/src/overlay/` sub-module | sub-module；state machine + ArcSwap cold path | Sprint 8-10 IMPL；Y2 Q1 enable |
| M3 | Health domain | `rust/openclaw_engine/src/health/` sub-module（spike Track B 已建 path）| sub-module；6 domain probe + 4-state ladder | Sprint 2 metric emitter + Sprint 5 cascade |
| M4 | Hypothesis discovery（pattern miner）| `srv/helper_scripts/research/m4_pattern_miner/` Python primary；`rust/openclaw_engine/src/m4_miner_bridge/` 薄 sub-module（read-only signal emitter） | Python primary（與 Cowork + LLM hybrid）；Rust 只接 IPC bridge | Sprint 2-3 stage 1 + Sprint 8 stage 2 |
| M5 | Model client（online learning）| `rust/openclaw_engine/src/ml_client/` sub-module trait stub | trait + `unimplemented!()` Sprint 1A-δ；Y3+ IMPL | Sprint 1A-δ trait stub；Y3+ active |
| M6 | Bayesian reward weight | `rust/openclaw_engine/src/bayesian_reward/` sub-module + `helper_scripts/cron/m6_reward_optimizer.py` cron | Rust hot path read（weight ArcSwap）+ Python optimization cron | Sprint 7 Advisory + Y2 Auto |
| M7 | Decay（DECAY_ENFORCED）| `rust/openclaw_engine/src/decay/` sub-module + `helper_scripts/cron/m7_decay_detector.py` | Rust state machine + Python detection cron | Sprint 8 IMPL + Sprint 10 auto-demote via LAL 1 |
| M8 | Anomaly | `rust/openclaw_engine/src/anomaly/` sub-module + `helper_scripts/research/m8_detectors/` Python | Rust anomaly_events writer + Python detector（statistical + Y2 ML autoencoder） | Sprint 1A-γ schema + Sprint 3 read-only + Y1 H2 alerting + Y2 active trigger |
| M9 | A/B framework | `rust/openclaw_engine/src/ab_test/` sub-module + `helper_scripts/research/m9_mSPRT/` Python | Rust assignment + Python mSPRT statistical | Sprint 4 read-only + Sprint 7-8 manual + Y2 auto |
| M10 | Discovery tier | `rust/openclaw_engine/src/discovery_tier/` sub-module（cold path；tier gate read on strategy spawn） | Rust hot config + cron 自動 demote on M3 HEALTH_DEGRADED | Sprint 1A-γ schema + Sprint 2 Tier A productionize + Y2 Tier C/D |
| M11 | Replay nightly | `srv/helper_scripts/replay/m11_nightly/` Python primary（cron job）；spike Track C 已建 path | Python primary（cron 24h scope；不在 hot path）；Rust 只 emit signal（M7 dedup） | Sprint 3 nightly IMPL Phase A + Sprint 5+ hookups |
| M12 | OrderRouter（adaptive routing）| `rust/openclaw_engine/src/router/` sub-module + trait stub Sprint 1A-δ | trait + `unimplemented!()` Sprint 1A-δ；Sprint 6 maker-vs-taker IMPL；Y2 cross-venue | Sprint 1A-δ trait stub；Sprint 6-7 IMPL |
| M13 | AssetClass + Venue enum | `rust/openclaw_engine/src/venue/` sub-module + enum hardcode DEX/Hyperliquid reject | enum 字面 reject（compile-time guard）；Y3+ Binance trade enable per ADR-0040 | Sprint 1A-δ enum stub；Y3+ active |

### 2.2 H-19 sibling structure 預先拆原則（避 G5-09 tick_pipeline 3524 LOC 重蹈）

per memory 2026-04-26 `G5-09 tick_pipeline/tests.rs 拆分` 教訓：13 module IMPL 階段必預先拆 sibling file structure（`mod.rs` aggregator + `<feature>.rs` siblings）；警告線 800 LOC / 硬上限 2000 LOC（per CLAUDE.md §九）。預先拆比 retrofit 拆便宜 5-10x。

建議拆法摘要（spike + Sprint 4+ IMPL phase 對齊）：

- **M1 LAL**: `lal/{mod,state_machine,eligibility,clawback,tests}.rs`（spike Track A 已建 skeleton）
- **M2 Overlay**: `overlay/{mod,state_machine,auto_disable,auto_enable,tests}.rs`
- **M3 Health**: `health/{mod,state_machine,<6 domain>,amplification_cap,tests}.rs`（spike Track B 已建前 4 個）
- **M4 Bridge**: `m4_miner_bridge/{mod,draft_writer,tests}.rs`；Python primary 在 `helper_scripts/research/m4_pattern_miner/`
- **M5 ML client**: `ml_client/{mod,trait,null_backend}.rs`（Sprint 1A-δ stub）
- **M6 Reward**: `bayesian_reward/{mod,weight_arcswap,tests}.rs` + `helper_scripts/cron/`
- **M7 Decay**: `decay/{mod,state_machine,decay_signals,tests}.rs` + cron
- **M8 Anomaly**: `anomaly/{mod,writer,severity,tests}.rs`
- **M9 A/B**: `ab_test/{mod,assignment,result_recorder,tests}.rs`
- **M10 Tier**: `discovery_tier/{mod,tier_config,tier_state,tests}.rs`
- **M11 Replay bridge**: `replay/m11_bridge/{mod,divergence_writer,tests}.rs`；Python primary 在 `helper_scripts/replay/m11_nightly/`
- **M12 Router**: `router/{mod,trait,maker_fill_rate_metric,tests}.rs`
- **M13 Venue**: `venue/{mod,asset_class_enum,venue_enum,tests}.rs`（compile-time DEX/Hyperliquid reject）

**注意**：M4 + M11 Python primary；M1/M3/M6/M7/M10 Rust+Python hybrid；其餘 Rust only。Mac CI 必對應分類 lint。

---

## §3 Cross-Compile Targets

### 3.1 Target Tuple 矩陣（per 既有 ci.yml + memory `project_mac_deployment_target`）

| Target | Runner | 觸發 |
|---|---|---|
| `x86_64-unknown-linux-gnu` | `ubuntu-latest` | push + PR + 週一 cron |
| `aarch64-apple-darwin` | `macos-latest` | PR + 週一 cron only（per `feedback_github_actions_cost` macOS 10x cost）|

### 3.2 為什麼不加 `aarch64-unknown-linux-gnu`

per memory `project_mac_deployment_target` `Decision：linux-arm64 支援延後`：

- linux-arm64（NAS / Pi）非主目標路徑
- QA-E6 在 EDGE-P3-1 round-2 提的 `aarch64-unknown-linux-gnu` CI 已延後 W24+
- 未來 40TB NAS 若升級 ARM controller 再議

本 spec 不擴 linux-arm64 target；維持 Mac + Linux 雙 target。

### 3.3 為什麼不加 `x86_64-pc-windows-msvc` / `x86_64-apple-darwin`

- 操作員 Mac 已是 Apple Silicon；`x86_64-apple-darwin` 不需要
- Windows 從未在 deployment target；不擴
- 維持 Mac CI 矩陣最小化 = 控 macOS cost

---

## §4 CI Workflow `.github/workflows/sprint_1a_module_verify.yml` 結構（spec only）

### 4.1 觸發策略（per memory `feedback_github_actions_cost`）

```yaml
on:
  pull_request:
    paths:
      - 'rust/**'
      - 'helper_scripts/**'
      - 'sql/migrations/V1[0-1][0-9]_*.sql'  # V100-V116 範圍
      - '.github/workflows/sprint_1a_module_verify.yml'
  schedule:
    - cron: '0 4 * * 1'  # 每週一 04:00 UTC（與 ci.yml 03:00 UTC 錯開 1h；UI dashboard 視覺分隔）
```

**設計理由**：

- **不 push trigger macOS**：per `feedback_github_actions_cost` macOS 10x 計費 + 2000 min/月免費 cap
- **PR trigger**：保留人工開 PR 時的 full coverage
- **週一 cron**：每週一次 macOS verify 確保 13 module Apple Silicon target 持續編得過
- **path filter**：只在 13 module 相關 path 觸發；非 13 module path PR（如 docs/）走 ci.yml 不觸發本 workflow
- **與 ci.yml 並存**：本 workflow 為 sibling，scope 限 13 module verify；ci.yml 為 baseline production-ready engine binary check

### 4.2 Job structure 草圖

| Job | Runner | Target | Steps |
|---|---|---|---|
| `module_verify_linux` | `ubuntu-latest` | `x86_64-unknown-linux-gnu` | (1) cargo check 13 module；(2) cargo test --no-run 13 module；(3) clippy --no-deps -D warnings；(4) Python M4/M11 lint（mypy + ruff）|
| `module_verify_macos` | `macos-latest`（if: PR or schedule）| `aarch64-apple-darwin` | (1) cargo check 13 module；(2) cargo test --no-run 13 module；(3) clippy --no-deps -D warnings；Python lint Linux job 已覆蓋（macOS skip 省 cost）|
| `module_sibling_split_guard` | `ubuntu-latest` | n/a | 13 module 各自 LOC ceiling check（800 警告 / 2000 hard）；超 hard 直接 FAIL |
| `module_v_migration_dry_run_static` | `ubuntu-latest` | n/a | V099-V116 spec doc Guard A/B/C grep check；確保 spec doc 沒漏 Guard（per CR-9 + H-15 PG dry-run mandate；static review-only；真實 PG dry-run 走 Linux trade-core sub-agent dispatch）|

**Job 並行性**：

- `module_verify_linux` 是基線（每 PR 跑）
- `module_verify_macos` 為 portability gate（每 PR + 週一 cron 跑）
- `module_sibling_split_guard` 是輕量 LOC check
- `module_v_migration_dry_run_static` 是 spec doc grep；不跑 PG

### 4.3 cargo check 13 module 命令範例（spec only；不寫實 .yml）

```bash
# Linux Job M1 example
cd rust && cargo check \
  --target x86_64-unknown-linux-gnu \
  --release \
  -p openclaw_engine \
  --lib

# macOS Job M5/M12/M13 trait stub verify
cd rust && cargo check \
  --target aarch64-apple-darwin \
  --release \
  -p openclaw_engine \
  --lib

# Python M4 / M11 lint（mypy + ruff）
ruff check helper_scripts/research/m4_pattern_miner/ \
  helper_scripts/replay/m11_nightly/
mypy --strict helper_scripts/research/m4_pattern_miner/ \
  helper_scripts/replay/m11_nightly/
```

**注意**：實際 IMPL `.yml` 由 E1 在 Sprint 1A-ε 末或 Sprint 4 first IMPL wave 寫。本 spec 只設計命令骨架。

### 4.4 cargo test --no-run vs cargo test 選擇

- `cargo test --no-run`：只編譯 test binary，不執行 — Mac CI 不跑 PG 真實 dry-run（per `feedback_v_migration_pg_dry_run` Mac mock pytest 抓不到 PL/pgSQL runtime semantic）；用 `--no-run` 證明 test 編得過，runtime 走 Linux trade-core
- `cargo test`：完整跑 test — Mac CI 不適合（mock pytest 失真 + 跑 test 時間長 + macOS 10x cost）
- 本 spec 採 `cargo test --no-run` for Mac；Linux 可選擇跑 unit test 子集（不跑 integration test）

### 4.5 clippy 邊界

- `cargo clippy --no-deps -D warnings`：13 module 警告當錯誤
- 排除 third-party crate 警告（`--no-deps`）
- 既有 codebase 若有 pre-existing warning，先 baseline 一輪後逐步收緊；不立即 `-D warnings` 否則阻 PR

---

## §5 Verify Matrix（13 module × 2 OS × 2 target）

### 5.1 矩陣表

| Module | Linux x86_64 cargo check | Linux x86_64 cargo test --no-run | macOS aarch64 cargo check | macOS aarch64 cargo test --no-run | Python mypy + ruff（M4 + M11 only）|
|---|---|---|---|---|---|
| M1 LAL | ✓ | ✓ | ✓（PR + cron）| ✓（PR + cron）| n/a |
| M2 Overlay | ✓ | ✓ | ✓ | ✓ | n/a |
| M3 Health | ✓ | ✓ | ✓ | ✓ | n/a |
| M4 Hypothesis（Rust bridge）| ✓ | ✓ | ✓ | ✓ | ✓（Python primary）|
| M5 ML client（trait stub）| ✓ | ✓ | ✓ | ✓ | n/a |
| M6 Reward | ✓ | ✓ | ✓ | ✓ | n/a（cron Python 但簡單 script；不走 mypy strict）|
| M7 Decay | ✓ | ✓ | ✓ | ✓ | n/a |
| M8 Anomaly | ✓ | ✓ | ✓ | ✓ | n/a（Y2 ML autoencoder Python 但 Y2 加）|
| M9 A/B | ✓ | ✓ | ✓ | ✓ | n/a |
| M10 Tier | ✓ | ✓ | ✓ | ✓ | n/a |
| M11 Replay（Rust bridge）| ✓ | ✓ | ✓ | ✓ | ✓（Python primary）|
| M12 OrderRouter（trait stub）| ✓ | ✓ | ✓ | ✓ | n/a |
| M13 Venue enum | ✓ | ✓ | ✓ | ✓ | n/a |

**矩陣總計**：13 × 2 OS × 2 cargo command = 52 cargo verify + 2 Python lint = 54 verify operations / PR + cron

### 5.2 macOS-specific 風險點 per H-20

per PA dispatch consolidation `H-20`（Apple Silicon CI tuple 全 13 module）：

> M4 ndarray-stats / linfa-clustering / M8 tch-rs / burn / M11 inotify-epoll 等 Linux-only crate 篩選

需特別檢查的 crate（13 module IMPL 階段加入 dependency 時）：

| Crate | 用途 | macOS 兼容性 | Mitigation |
|---|---|---|---|
| `ndarray-stats` | M4 + M8 統計 | ✓ 純 Rust ✓ | 加 dependency 時驗 macOS build |
| `linfa-clustering` | M4 stage 2 clustering | ✓ 純 Rust ✓ | 同上 |
| `tch-rs` | Y2 M8 autoencoder（PyTorch binding） | ⚠️ macOS Apple Silicon 需 libtorch dylib bundling；Y2 才加 | Y2 加時走 `feature flag` like edge_predictor_ort pattern（既有 `Cargo.toml` 範式）|
| `burn` | Y2 M8 ML alternative | ✓ pure Rust ✓ | 優先選 burn 避 libtorch bundling |
| `inotify` | Linux-only file watcher | ✗ macOS 無 inotify | M11 Python primary；不使用 Rust inotify；改 polling 或 `notify` crate（跨平台）|
| `procfs` | M3 Linux /proc reader | ✗ macOS 無 /proc | M3 spike Track B 已 spec sysctl Mac fallback per `feedback_cross_platform`；platform guard `#[cfg(target_os = "linux")]` + `#[cfg(target_os = "macos")]` |
| `epoll` direct | Tokio runtime 用 | tokio 已抽象（kqueue Mac / epoll Linux）；不需手動處理 | 不在 13 module hot path |

**設計原則**：13 module IMPL 階段加任何新 crate 必先檢查 `aarch64-apple-darwin` build。`Cargo.toml` 既有 `edge_predictor_ort` feature flag pattern 是最佳範式（默認 stub null_backend；feature 開啟才拉 libonnxruntime）。

### 5.3 Python lint scope

per §2.1 M4 + M11 Python primary：

| Path | mypy | ruff | 備註 |
|---|---|---|---|
| `helper_scripts/research/m4_pattern_miner/` | `--strict` | enabled | Sprint 2-3 stage 1 開始；Sprint 8 stage 2 active |
| `helper_scripts/replay/m11_nightly/` | `--strict` | enabled | Sprint 3 IMPL Phase A 起 active |

不在 Python lint scope（已有專屬 lint workflow 或不需要）：

- `helper_scripts/cron/m6_reward_optimizer.py` — 簡單 cron；不走 mypy strict
- `helper_scripts/cron/m7_decay_detector.py` — 同上
- `helper_scripts/research/m8_detectors/` — Y1 statistical only；Y2 ML 加 mypy
- M9 mSPRT helper — Sprint 7-8 IMPL 時加 mypy

---

## §6 Acceptance Criteria（5-7 條）

### AC-1：13 module cargo check pass

13 module 各自的 Rust sub-module path 在 macOS aarch64 + Linux x86_64 雙 target 上 `cargo check` 成功（exit 0）。

**驗證方式**：`module_verify_linux` + `module_verify_macos` job 各自的 cargo check step 通過。

**Sprint 1A-ζ spike pass 後可分階段達成**：spike pass 後 M1/M3/M11 3 module 達標；其餘 10 module 走 Sprint 4-8 IMPL phase 階段達標。

### AC-2：Python M11 + M4 mypy + ruff pass

`helper_scripts/research/m4_pattern_miner/` + `helper_scripts/replay/m11_nightly/` 各自 `mypy --strict` + `ruff check` 通過。

**驗證方式**：`module_verify_linux` job Python lint step。

**Sprint 1A-ζ spike phase 不阻**：spike 階段 M11 只在 `tests/spike_m11_m7_dedup_contract.py` 路徑；M4 完全不在 spike scope。本 AC 啟用走 Sprint 2-3 M4 stage 1 + Sprint 3 M11 nightly IMPL。

### AC-3：No-network mock test pass

per `CLAUDE.md` §六（Mac is dev machine；Linux is runtime）+ memory `feedback_v_migration_pg_dry_run`：

- Mac CI 不連 production PG
- Mac CI 不連 Bybit endpoint
- Mac CI 不連 Tailscale Linux trade-core
- 所有 test 在 Mac CI 上跑必為 mock / fixture / `--no-run` 編譯

**驗證方式**：cargo test --no-run 不真實執行；Python pytest 跑時 `pytest -m "not network"` 排除 network mark。

**設計理由**：

- macOS GitHub Actions runner 不在 Tailnet
- 連外網有 secret leak 風險
- Mac mock pytest 抓不到 PG runtime semantic 是已知 limitation；真實 PG 走 Linux trade-core sub-agent dispatch

### AC-4：Sibling test file structure verified（per H-19）

13 module 預先拆 sibling 結構在 `module_sibling_split_guard` job grep check 通過：

- 每個 `<module>/mod.rs` 不超過 800 LOC（警告線）
- 每個 sibling file 不超過 800 LOC（警告線）
- 任何 file 超過 2000 LOC 直接 FAIL（per CLAUDE.md §九硬上限）
- Test file 與 production file 分離（`<feature>_tests.rs` 或 `tests/` sibling directory）

**驗證方式**：`module_sibling_split_guard` job 跑 `find rust/openclaw_engine/src -name "*.rs" -exec wc -l {} \;` + threshold awk filter。

**設計理由**：避 G5-09 tick_pipeline 3524 LOC 重蹈（per E5 memory 2026-04-26 教訓）。

### AC-5：CI cost < $5/month（per memory `feedback_github_actions_cost`）

per `feedback_github_actions_cost` 2026-05-09：

- Private repo `yunancun/BybitOpenClaw` 2000 billable minutes / month free
- macOS-latest 10x billing multiplier
- 既有 ci.yml 已 PR + 週一 cron only（不 push trigger macOS）

本 workflow 加入後 estimated monthly cost：

| Trigger | runner | duration estimate | per-run minutes（含 10x multiplier macOS）| 月 estimated runs | 月 minutes |
|---|---|---|---|---|---|
| PR `module_verify_linux` | `ubuntu-latest` | ~5min | 5min × 1 | ~30 PR/month | 150 min |
| PR `module_verify_macos` | `macos-latest` | ~7min | 7min × 10 = 70min | ~30 PR/month | **2100 min** ⚠️ |
| Weekly cron `module_verify_macos` | `macos-latest` | ~7min | 70min | 4-5 runs | 280-350 min |
| `module_sibling_split_guard` | `ubuntu-latest` | ~30s | 0.5min | ~30 PR | 15 min |
| `module_v_migration_dry_run_static` | `ubuntu-latest` | ~1min | 1min | ~30 PR | 30 min |

**問題識別**：PR 觸發 macOS 30 PR/month × 70min = 2100 min 直接超 2000 min quota ⚠️

**Mitigation 三選一**：

| 方案 | 描述 | 月 macOS minutes | 取捨 |
|---|---|---|---|
| A | PR macOS 只在 `rust/**` path 變更才觸發（filter 收緊）| ~10-15 PR/month × 70min = 700-1050 min | 推薦（與既有 ci.yml policy 一致）|
| B | PR macOS 只在 label `needs-mac-verify` 才觸發 | ~5-10 PR/month × 70min = 350-700 min | 操作員手動 label；摩擦高 |
| C | PR macOS skip；只週一 cron + 必要 PR 時操作員手動 trigger workflow_dispatch | 280-350 min | 最省 cost；但 PR 階段失去 Mac portability gate |

**E5 推薦**：方案 A（path filter `rust/**` + `sql/migrations/V1[0-1][0-9]_*.sql`）。理由：

- 與既有 ci.yml `macos PR + cron` policy 一致
- 大多數 docs / TODO PR 不會觸 path filter
- Sprint 1A-β/γ/δ 期 spec doc 為主 PR，Mac verify 自動 skip
- Sprint 4+ IMPL phase PR 才觸 Mac verify（這時候才真的需要）

**AC-5 量化目標**：方案 A 落實後 estimated 月 macOS minutes ≤ 1050 min（總 quota 1245 min/月含 Linux）≤ 2000 min cap ≤ free tier；月 cost ≈ $0（cap 內）。

### AC-6（optional）：cross-V### dependency static check

V099-V116 schema spec doc 之間的 cross-V### 引用一致性（per CR-9 cross-V### dependency graph）。

**驗證方式**：`module_v_migration_dry_run_static` job grep V### references；確保 spec doc 沒有 dangling V### 引用。

**Sprint 1A-ε 期內 land**；非阻 Sprint 1A-ζ spike。

### AC-7（optional）：cross-ADR alignment static check

ADR-0034 / 0035 / 0036 / 0037 / 0038 / 0039 / 0040 / 0041 在 Rust code 內被 reference 的位置（mostly comment + struct doc）一致性 grep check。

**驗證方式**：grep `ADR-00[3-4][0-9]` 出現位置與 ADR file 存在性對齊。

**Sprint 1A-ε 期末 land**；非阻 Sprint 1A-ζ spike。

---

## §7 IMPL Phase Split

### 7.1 Sprint 1A-ζ spike（per `2026-05-21--sprint_1a_zeta_impl_spike_scope_spec.md`）

spike 階段 3 critical-path module（M1 / M3 / M11）的 IMPL 路徑與 Mac CI 對應：

| Track | Module | Mac CI 影響 |
|---|---|---|
| Track A | M1 LAL + V112 | spike 階段在 Linux 跑 cargo test PG empirical；Mac CI 走 cargo check + cargo test --no-run + sibling LOC check（不跑 PG）|
| Track B | M3 Health + V106 | 同上；Mac CI 走 platform guard `#[cfg(target_os = "macos")]` sysctl fallback path 編得過 |
| Track C | M11 Replay + V107 | spike 階段 Python primary；Mac CI 走 Python mypy + ruff（spike script 在 `tests/` 不在 lint scope）|

**spike Mac CI 工作項**：

- spike 階段 cargo check Linux + macOS 兩 target 跑通（exit 0）
- spike 階段 sibling LOC ceiling 不破
- spike 階段不啟動 `module_v_migration_dry_run_static` job（V### dry-run 走 Linux trade-core 真實 PG）

### 7.2 Sprint 4-8 全 13 module IMPL 階段

13 module 各自 IMPL phase 對 Mac CI 啟動 timing：

- **Sprint 1A-δ**: M5 + M12 + M13 trait/enum stub（cargo check `unimplemented!()` 編得過）
- **Sprint 2**: M4 stage 1（Python lint enable）+ M10 Tier A + M3 metric emitter
- **Sprint 3**: M11 nightly Phase A（Python lint enable）+ M8 read-only logging
- **Sprint 4**: M1 LAL 1 IMPL + M9 read-only
- **Sprint 5**: M3 cascade + M11 hookups
- **Sprint 6**: M12 maker-vs-taker
- **Sprint 7**: M6 Advisory reward + M1 LAL 2 + M9 manual A/B
- **Sprint 8**: M7 DECAY_ENFORCED + M4 stage 2 + M8 alerting

**設計原則**：每 Sprint 對應 module IMPL phase 完成後啟動該 module Mac CI verify；不在 IMPL 未開始時啟動（會 false alarm）。Sprint 1A-δ 後 13 module 全 trait/stub level cargo check pass 是最小 AC。

### 7.3 過渡期 fallback

Sprint 1A-ε 期間 IMPL 大多未開始；Mac CI 主要 verify：Sprint 1A-δ 後 M5/M12/M13 stub 編得過 + Sprint 1A-ζ spike 後 M1/M3/M11 skeleton 編得過；其餘 7 module（M2/M4/M6/M7/M8/M9/M10）只 spec/V###/ADR 階段，cargo check 對它們 no-op。過渡期 AC-1 部分達標即可。

---

## §8 Risk + Mitigation

### 8.1 R-1：GitHub Actions macOS 10x cost vs cron schedule

**Risk**：未審慎 trigger → macOS minutes 過 2000 min cap → 月 cost $5+ → 違背 `feedback_github_actions_cost`。

**Mitigation**：採方案 A path filter（`rust/**` + `sql/migrations/V1[0-1][0-9]_*.sql`）收緊 PR macOS trigger；週一 cron 維持 portability gate；月 quota usage GitHub Actions billing dashboard 觀察，超 80% 升級方案 C；操作員可 `workflow_dispatch` 手動補位。

### 8.2 R-2：Apple Silicon vs Linux platform diff

**Risk**：M3 `engine_runtime_domain` 用 procfs（Linux-only；macOS 無 /proc）；M11 nightly 若用 inotify（Linux-only）；Y2 M8 autoencoder 若用 tch-rs/libtorch 需 dylib bundling；SSE/AVX intrinsics 需 `#[cfg]` 守衛。

**Mitigation**：spike Track B 已 spec procfs / sysctl Mac fallback（per `feedback_cross_platform`）；M11 Python primary 用 `notify` crate（跨平台）非 inotify；Y2 M8 優先 burn（pure Rust）避 libtorch；新 Rust dependency 必驗 `aarch64-apple-darwin` build；走 `edge_predictor_ort` feature flag pattern。

### 8.3 R-3：Python ↔ Rust IPC schema drift

**Risk**：M4 / M11 Python primary；V### schema 改動後 Rust struct + Python pydantic 兩端同步漂移；Mac CI 不跑 PG dry-run，編譯期 schema 不對齊風險仍在。

**Mitigation**：採 cross-language 1e-4 容差 fixture harness（per H-18），fixture 在 `tests/fixtures/` 共用；V### spec doc grep check（per AC-6）確保 column 命名一致；Rust IPC message type 增量清單（per H-13）每 Sprint 1A-β/γ DESIGN 必補；Mac CI 跑 cargo check + Python mypy 雙端靜態驗證。

### 8.4 R-4：Sprint 1A-ε deliverable scope creep + spec/.yml 漂移

**Risk**：Sprint 1A-ε 還有 cross-ADR / docs index / Monthly Review Wizard / Lv 3-4 modal helper 等 deliverable；本 spec 寫過深 → 排擠其他；spec vs 實 `.yml` 兩份各自演化 → 後續 audit 對不上。

**Mitigation**：本 spec 限 spec phase（不寫 IMPL `.yml`）控制 scope；實 `.yml` 順延 Sprint 1A-ε 末或 Sprint 4 first wave，E1 走標準 dispatch chain；本 spec 標 `SPEC-DRAFT-V0`；E1 IMPL 後升 `SPEC-FINAL-V1` 並列 commit SHA + `.yml` head；13 module Mac CI verify 不阻 Sprint 1A-ζ spike（spike 用 Linux PG empirical）。

---

## §9 Cross-V### Dependency for CI（V099-V116 schema spec ↔ Rust struct alignment）

per `2026-05-21--v58_dispatch_consolidation.md` §5.3 cross-V### 依賴：

```
V099/V100 (Track v3)              — Sprint 1A-α DONE
V101/V102 (Earn schema)           — Sprint 1A-α DONE
V103/V104 (hypotheses)            — Sprint 1A-α DONE + EXTEND for M4 (1A-γ)
V105 (M2 overlay)                 — 1A-γ ← V107
V106 (M3 health)                  — 1A-β (hypertable)
V107 (M11 replay div)             — 1A-β ← V103/V109/V113 (hypertable)
V108 (M9 A/B)                     — 1A-γ ← V103
V109 (M8 anomaly)                 — 1A-γ → V112 (hypertable)
V110 (M6 reward)                  — 1A-β
V111 (M10 discovery tier)         — 1A-γ
V112 (M1 LAL)                     — 1A-β ← V113
V113 (M7 decay)                   — 1A-β (hypertable; M7 single decay authority)
V114/V115/V116 (M5/M12/M13)       — 1A-δ reserved only
```

Mac CI 對 V099-V116 的 alignment 責任：

- **不跑 PG**（per AC-3 no-network）
- **跑 spec doc grep**（per AC-6 cross-V### dependency static check）
- **跑 Rust struct schema 編譯期 alignment**（cargo check 對 sqlx prepare offline 模式或 sqlx::query! macro 編譯時 reject mismatch）

未來 Sprint 4+ IMPL 階段加 `cargo sqlx prepare --check`：

- 需 `.sqlx/` query cache 提前生成（per sqlx 0.8 offline mode）
- 加 to `module_verify_linux` job
- Mac CI skip（macOS 不裝 PG client）

---

## §10 Cross-ADR Alignment for CI

7 個 v5.8 新 ADR 與 Mac CI 對應重點：

- **ADR-0034（M1 LAL）**：LAL 0-4 數字方向「越大越嚴」必對齊 Rust enum + PG CHECK；spike Track A 已 spec runtime test；Mac CI 走 cargo check enum 編譯
- **ADR-0035（M5 trait stub `unimplemented!()`）**：6 method stub Sprint 1A-δ；Mac CI 走 cargo check + cargo test --no-run（不真實跑避觸 stub panic）
- **ADR-0036（M8/M10 Tier D 黑名單 HMM/Markov/GARCH）**：Rust 若 import 黑名單 crate（hmm-rs / markov_chains）compile-time reject；Mac CI grep `Cargo.toml` 黑名單 crate
- **ADR-0037（M9 mSPRT）**：mSPRT IMPL 在 Python；M9 Python lint 階段加 i.i.d. 假設邊界 assertion
- **ADR-0038（M11 historical source = 自家 `market.liquidations` 非 Bybit API）**：grep check `bybit_rest_client.rs` + Python `helper_scripts/` 不出現 `/v5/market/liquidations` 字面
- **ADR-0039（M12 OrderRouter 6 method）**：trait 簽名鎖；Mac CI 必驗 trait 編譯；sibling test 必含 6 method `unimplemented!()` stub
- **ADR-0040（M13 multi-venue；DEX/Hyperliquid compile-time reject）**：Rust `Venue` enum 字面 reject DEX/Hyperliquid；sibling test 含 `compile_fail` doctest 或 grep check `Venue::DEX` / `Venue::Hyperliquid` 不存在
- **ADR-0041（ContextDistiller v4）**：ContextDistiller IMPL 在 Python LocalLLMClient；Python lint 階段加 token cap assertion

---

## §11 Open Questions（≥3）

### Q-1：13 module Mac CI verify spec 是 Sprint 1A-ε 阻 1B gate 嗎？

**選項**：(a) spec done 即解 gate；實 `.yml` 順延 Sprint 4 first wave；(b) 必須 spec + 實 `.yml` 雙 done；(c) spec done + macOS PR trigger 啟動即解；Linux 部分順延

**E5 推薦**：(a) — spec 是 Sprint 1A-ε deliverable；實 `.yml` 適合 Sprint 4 first wave（這時至少 5 個 module 開始 IMPL 才有意義跑）。**PA / PM 決定**

### Q-2：Sprint 1A-ζ spike 階段是否啟動本 workflow？

**選項**：(a) spike 階段不啟動（避混淆 spike-only path）；(b) spike 階段啟動 minimal Mac CI（只 M1/M3/M11 子集）；(c) spike 階段啟動 full Mac CI（13 module 但大多 skip）

**E5 推薦**：(b) — spike 是 critical-path；Mac CI 同步驗 Mac 編譯能避 Sprint 4 first Live 才暴露 platform diff。**PA / PM 決定**

### Q-3：Python lint scope 啟動 timing？

**選項**：(a) 立即啟動空 path lint（走過場）；(b) 等 IMPL 真實 land 第一個 .py 才啟動；(c) spike Track C land 第一個 m11 .py 後啟動

**E5 推薦**：(c) — spike Track C 已 land M11 spike script；以此為 lint scope 啟動點。**PA / PM 決定**

### Q-4（optional）：libtorch Mac dylib bundling Y2 加時策略？

Y2 M8 autoencoder 若選 tch-rs 需 libtorch.dylib bundling。**E5 推薦**：(a) burn 優先（pure Rust）；fallback (b) tch-rs + feature flag pattern（如 `edge_predictor_ort` 範式）。**E5 → MIT 後續評估**

### Q-5（optional）：cargo sqlx prepare --check 加入 timing？

**選項**：(a) Sprint 4 first IMPL wave 加；(b) Sprint 8 後 IMPL 較全才加；(c) 每 module IMPL phase 各自加

**E5 推薦**：(a) — sqlx schema drift 是 silent error class；早加早控。**PA / PM 決定**

---

## §12 Sign-off

| Role | 簽核項 | 期待 verdict |
|---|---|---|
| E5（本 spec author） | spec 設計範式 / Mac CI cost AC / 13 module workspace structure / risk + mitigation | ✓ SPEC-DRAFT-V0 land |
| PA | spec 與 PA dispatch consolidation `2026-05-21--v58_dispatch_consolidation.md` Sprint 1A-ε 對齊 / H-19 sibling structure 對齊 / H-20 Apple Silicon CI tuple 對齊 / cross-V### + cross-ADR alignment 完整 | ⏳ pending |
| E1 | 實 `.yml` IMPL 範式對齊既有 ci.yml + GitHub Actions YAML 語法 / job structure 可 IMPL / cargo check + cargo test --no-run 命令對齊 workspace member | ⏳ pending |
| E4 | regression test scope 不衝突 / cargo test --no-run vs cargo test 選擇邊界 / Python lint scope 對齊既有 helper_scripts/ test 規範 | ⏳ pending |
| PM | spec 範圍對齊 Sprint 1A-ε deliverable / 不擴 scope / Open Q 5 條決議 / 採方案 A trigger filter | ⏳ pending |

**Sign-off 流程**：

1. PA cross-check 本 spec 與 PA dispatch consolidation 一致性 + Sprint 1A-ε scope（est. 1-2 hr）
2. E1 cross-check `.yml` IMPL feasibility（est. 1-2 hr）
3. E4 cross-check test scope（est. 1 hr）
4. PM Open Q 決議 + sign-off（est. 1-2 hr）
5. Sign-off 後 spec 升 `SPEC-FINAL-V1`；E1 排期 `.yml` IMPL（Sprint 1A-ε 末或 Sprint 4 first wave）

**Sign-off 工時合計**：3-7 hr / 4-5 並行 sub-agent

---

## §13 附錄 — 對照表

**與既有 ci.yml 對照**：本 spec sibling workflow scope 限 13 module；既有 ci.yml engine binary baseline 不動。Trigger 同（PR + 週一 cron；不 push macOS）。本 workflow 加 4 個 job；月 estimated 1000-1200 min（含路徑 filter mitigation）。

**與 H-19 / H-20 對照**：H-19 sibling structure → §2.2 + AC-4 + `module_sibling_split_guard` job；H-20 Apple Silicon CI tuple → §3 + §5 + §8.2 R-2。

**與 memory `feedback_github_actions_cost` 對照**：2000 min/月免費 → AC-5；macOS 10x → §8.1 R-1 + AC-5；不 push trigger macOS → §4.1；週一 cron → §4.1 `0 4 * * 1`；月 cost ≤ free tier → AC-5 + 方案 A path filter。

---

**END Mac CI 13-Module Cross-Compile Verify Scope Specification**
