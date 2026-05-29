---
status: accepted
---

# LiveDemo runs the Live pipeline against Bybit demo endpoint with Live-grade gating

When the Bybit endpoint slot points at `api-demo.bybit.com`, the engine runs `BybitEnvironment::LiveDemo` — the full Live pipeline (SM-01 Authorization, EarnedTrust TTL, signed `authorization.json` HMAC verification, every risk gate) — against play-money. The only LiveDemo-vs-Mainnet difference is the `OPENCLAW_ALLOW_MAINNET=1` env requirement; all other gates are byte-identical.

## Considered alternatives

A "relaxed LiveDemo" tier (skip TTL, skip signing, looser cost gate) was rejected: LiveDemo is the only online surface to exercise live code paths before real capital flows; degrading it would leave Mainnet promotion as the first time those gates ever execute.

## Addendum 2026-05-29 — Scheduled ML training-lane data-source policy (cold-audit P2-05)

背景：`helper_scripts/cron/ml_training_maintenance.py:57` 將排程的 supervised/quantile
訓練固定在 `DEFAULT_TRAINING_ENGINE_MODES="demo"`，而 shadow advisor 在 `:58`
`DEFAULT_SHADOW_ENGINE_MODES="demo,live_demo"` 已經涵蓋 live_demo。runtime（MIT 2026-05-29）
已存在 live_demo 證據：`trading.fills` live_demo 3,230 筆、`trading.decision_outcomes`
live_demo 825,286 筆。`parquet_etl.py:107-118 engine_mode_scope()` 在 schema 層已支援把
`live` 展開為 `('live','live_demo')`，因此「不擴 live_demo 訓練 lane」是政策選擇而非結構限制。

決策（PA，與 2026-05-29 pkgC evidence/promotion spec §6 一致）：
**維持排程訓練 demo-only，刻意如此，現階段不新增 live_demo-widened 訓練 lane。**

理由：
1. LiveDemo = live 控制流走 demo endpoint，其 fills 是有效 edge 資料；但把 live_demo
   併入訓練 lane，必須先有能驗證更寬 lane 的 promotion gate。
2. 目前 promotion gate 的經驗證據面尚空：`observability.model_performance=0`、
   `observability.drift_events=0`（P2-06）、Stage-B replay 尚未實作（P2-07）。在這些
   證據面填滿前擴 lane，等於訓練在 gate 還無法驗證的資料分佈上。
3. live_demo 資料現階段仍由 shadow advisor（`:58`）消費，不浪費——只是不進入會直接
   產生 promotion 候選 artifact 的訓練 lane。

重啟條件（sequencing，明確 reopen gate）：
`P2-06 evidence 表填滿（mode-scoped 非空）→ Stage 0R / Stage-B replay green（P2-07）
→ 才以獨立 ticket 評估 live_demo-widened 訓練 lane`，且該 lane 必須有隔離指標、embargo、
且在 registry/performance gate 通過前不得 auto-promote。

現在要做（doc/comment only，無行為改動）：在 `ml_training_maintenance.py:57` 加註解說明
demo-only 是刻意、附上述 reopen gate。code 行為不變。Owner: E1（註解）+ TW（文件）。
驗證: MIT + QC 核對 sequencing 理由。
