# ADR 0041: ContextDistiller v4 — Layered Snapshot + Token Hard Cap + DOC-08 AI Cost Amendment

Date: 2026-05-21
Status: **Proposed-pending-commit**（per AI-E 5.21 v5.8 executability audit must-fix 6 條第 1 條 + PA dispatch consolidation CR-16 + PM 仲裁建議 #8「(b) 砍頻率 + Y2 Q1 重評」；本 ADR 為 ADR-0027 (AI Plan Mode Time-Based Budgeting) 的 v4 ContextDistiller 級擴展，不取代）
Operator Sign-off: 2026-05-21（主會話 PM dispatch via v5.8 §2 13 module thesis + AI-E audit GO-WITH-CONDITIONS 第 1 條 must-fix「ADR-0041 ContextDistiller v4 補入 Sprint 1A-β」）
Related: ADR-0027 (AI Plan Mode Time-Based Budgeting — 本 ADR 為其 v4 級延伸，operator-hours discipline 不變) / DOC-08 §4 AI 預算管理（每日 $2.00 硬上限 + 保守模式 ~$17/月 baseline；本 ADR 為其 cap amendment）/ DOC-08 §5 AI 注意力稅 cost_edge_ratio 等級 / ADR-0024-lite (Cowork subscription operator-assistant 邊界) / ADR-0034 (LAL 4 capital structure / venue change always operator) / AMD-2026-05-21-01 (autonomy-vs-human-final-review opt-in path) / v5.8 §2 M4 (Self-Supervised Hypothesis Discovery + Cowork review) / v5.8 §2 M8 (Anomaly Detection) / v5.8 §2 M11 (Counterfactual Replay Automation) / token-cost-analysis skill (`srv/.claude/skills/token-cost-analysis/SKILL.md` — AI-E) / AI-E v5.8 audit (`docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-21--v58_executability_audit.md`) / PA dispatch consolidation (`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §1 CR-16 + §8 仲裁 #8)

## Context

### 起源 — v5.8 13 module thesis 引爆 token 預算 / Y2 LLM cost 超 cap

v5.7 ContextDistiller v3 token 預算 700-900 tokens / 推理；命中 L1 Ollama 9B `<3s` SLA 邊際 OK（Linux trade-core 量測 P95 ~2.5s @ 800 token）。

v5.8 §2 在 v5.7 baseline 上新增 13 module，其中 6 個 module 的當前 state 需要注入 ContextDistiller 供 Layer 2 Claude 推理使用：

| Module | 注入內容 | 估算 token |
|---|---|---|
| M1 LAL（Layered Approval Lease）per-strategy tier state | per-strategy current LAL n + 30d stable flag + sample count | +80-120 |
| M3 Self-monitoring health 6 維度 | WS latency / REST / DB / Disk / CPU / 策略指標 current level (健康 / WARN / CRITICAL) | +100-150 |
| M4 Self-supervised hypothesis DRAFT preview | per-trial 最近 3 DRAFT 的 pattern summary + supporting stats | +200-300 |
| M6 Multi-objective reward weights | 5 λ 值（dd / tail / turnover / slippage / decay）+ bound + last change ts | +40-60 |
| M7 Strategy decay signal | rolling 30d Sharpe / DD / consec loss / replay delta | +60-100 |
| M8 Anomaly detection current state | market regime + own behavior 共 8 維 z-score + severity level (INFO/WARN/CRITICAL/HALT) | +100-180 |
| M11 Last replay divergence summary | per-strategy PnL/decision count/slippage divergence delta | +80-200 |

累計 v5.8 ContextDistiller v3 注入：**1,180-1,630 token / 推理**（v5.7 700-900 + v5.8 新增 480-730）。

### 為什麼直接撞 DOC-08 兩條紅線

**紅線 1：DOC-08 §8 延遲預算 L1 Ollama `<3s` SLA**

| Context tokens | Ollama 9B P50 | Ollama 9B P95 | Ollama 27B P50 | DOC-08 §8 SLA |
|---|---|---|---|---|
| 520（v5.6） | ~1.5s | ~2.8s | ~3.5s | `<3s` |
| 700（v5.7） | ~2.2s | ~4.0s | ~5.5s | **9B P95 撞 SLA** |
| 1,200（v5.8） | ~3.8s | ~6.5s | ~9.0s | **9B P50 直接撞 SLA** |
| 1,500（v5.8 high） | ~4.5s | ~8.0s | ~11s | **全撞** |

（AI-E 量測推估 per Linux trade-core RTX/CPU；Mac Apple Silicon 略快但仍超）

**紅線 2：DOC-08 §4 AI 預算管理每日 $2.00 硬上限 + 保守模式 ~$17/月 baseline**

AI-E v5.8 audit token-cost-analysis 估算（per token-cost-analysis skill「OpenClaw AI 三層成本結構」+ Anthropic Sonnet pricing）：

| 階段 | inference / 月 | 平均 token / inference | Y2 月成本估算 | vs DOC-08 baseline |
|---|---|---|---|---|
| v5.7 baseline | 250 | 800 | $42-78 / 月 | 2-4x baseline，仍 under $60 informal cap |
| v5.8 Y1（M2/M6 stub, M11 daily reduced） | 300 | 1,200-1,500 | $90-150 / 月 | 1.5-2.5x baseline |
| **v5.8 Y2 active（M2/M6 active, M11 daily, M4 DRAFT active）** | **400** | **1,500** | **$112-213 / 月** | **1.9-3.5x baseline，遠超 informal $60 cap** |

DOC-08 §4 真實 cap baseline：每日 $2.00 硬上限 = 月 ~$60 informal ceiling（per 4.4 保守模式 ~$17/月 trading baseline + 推理用 inflation）。Y2 推估月 $112-213 顯然超 cap 1.9-3.5x。

> **註**：先前 prompt 與部分 audit report 引用「DOC-08 §12 AI cost cap」，實際 DOC-08 §12 章節為「安全不变量」（Safety Invariants），AI cost cap 真實位置為 **DOC-08 §4 AI 预算管理 + §5 AI 注意力税**。本 ADR cross-reference 統一更正為 §4 + §5；其他 doc 引用 §12 為書面誤標，建議後續批次以 PA + TW 集中修正（不在本 ADR 範圍）。

### 為什麼這是 ADR 級決定不是 spec 級

| 維度 | 依據 |
|---|---|
| 跨 ADR 影響 | 觸及 ADR-0027 (Plan Mode budget) / ADR-0020 (Layer 2 manual-only) / ADR-0024-lite (Cowork 邊界) 三個 ADR 的執行邊界 |
| 治理權威 | 牽涉 DOC-08 §4 AI 預算 cap 字面 amendment，需 ADR 級對齊 |
| Cost 感知原則 | §二 priority order #13「AI 成本感知」+ #14「零外部成本 baseline」直接受影響 |
| SLA contract | L1 Ollama `<3s` 是 v5.7 dispatch baseline contract，跌穿則 6 module 設計 cycle time 全部 fail |

故立為 ADR-0041，並走 PM final verdict + AI-E + TW 三方 sign-off。

### 為什麼是 ADR-0027 的 v4 級擴展不取代

ADR-0027 已建立「time-budget discipline / subscription = sunk cost / API + hosting = variable bound / Build/Observe/Low Activity 三 mode」的根本框架。本 ADR 不挑戰那個框架；只在「per-inference token budget」這個 ADR-0027 未涵蓋的次層建立硬 enforcement，並對 DOC-08 §4 month-level cap 提 conditional amendment（Y2 opt-in）。

ADR-0027 是「operator hours discipline」；ADR-0041 是「per-inference token discipline」；兩者正交。

## Decision

**Proposed**：以下六項決定 land 於 Sprint 1A-β ADR-0041 + ContextDistiller v4 IMPL 工作。

### Decision 1 — ContextDistiller v4 Layered Snapshot

| 層 | 用途 | 注入時機 | Token 上限 |
|---|---|---|---|
| **L0 always-inject** | Agent identity / current task / hard boundaries excerpt（§二 16 條 + §四 hard boundaries 摘要 + role contract） | 每次推理永遠注入 | ≤ 400 token |
| **L1 conditional-inject** | Relevant module state per current task（例：M4 DRAFT review → 注入 M4 最近 3 DRAFT；不注入 M11；M3 health check → 注入 M3 + M8；不注入 M4） | 按 task type 路由 | ≤ 200 token |
| **L2 per-request-inject** | Dynamic state pulled per query（latest market state / anomaly current level / 最後 1 次 lease decision） | 按 query 動態組裝 | ≤ 200 token |

**累計上限**：`L0 + L1 + L2 ≤ 800 token / 推理`（hard cap，per §Decision 2 enforcement）。

#### 為什麼三層而不是兩層或四層

| Alternative | 棄因 |
|---|---|
| 一層 flat budget | 失去 task-specific 路由能力 → M11 narrative 任務也會 inject M4 state 浪費 token |
| 兩層（always + conditional） | per-request dynamic state（latest market / anomaly current level）與「task type 關聯的 module state」不同性質，混在 conditional 會破壞 cacheability |
| 四層以上 | 注入 logic 過於碎片化 → ContextDistiller v4 IMPL 工程 cost 翻倍且無 token 收益 |

三層是「task-binding L1 + dynamic L2 + always L0」的最小可分割集。

#### Task type → L1 module state 路由規則

| Task type 範例 | L1 注入 module state |
|---|---|
| M4 DRAFT review / Cowork hypothesis review | M4 最近 3 DRAFT summary + M10 Tier B activation status |
| M11 nightly replay narrative | M11 latest divergence + M7 decay signal（同來源） |
| M1 LAL Tier 1/2 auto-approval judgment | M1 per-strategy LAL + M3 health current + M7 decay signal |
| M8 anomaly alert narrative | M8 current state + M3 health + M11 recent divergence |
| Allocator monthly proposal | M6 reward weights + M7 decay + M10 capital tier |
| Strategy parameter wide adjustment skill | M1 LAL + M7 decay + M11 divergence（per ADR-0022） |
| Generic governance / SOP question | L1 = empty（只 L0 + L2） |

路由表本身放 ContextDistiller v4 Python config（runtime hot-reload，per ADR-0009 ArcSwap pattern 對齊）；不寫 Rust hot path。

### Decision 2 — Token Hard Cap ≤ 800 Enforcement

| 規則 | 設計 |
|---|---|
| Hard cap 位置 | `ContextDistiller.assemble_prompt()` 入口 |
| 計算方式 | `current_total = len(tokenize(L0)) + len(tokenize(L1)) + len(tokenize(L2))`（用 Claude tokenizer / Anthropic SDK 真實 token 計） |
| Pre-check | 任何 `inject_*()` call 必 pre-check `(current_total + new_inject_size) ≤ 800`；超出 → reject 該 inject 並 log `over_budget=true` |
| 超 cap → fail-safe path | 觸發 statistical-only mode（per §Decision 3）；不靜默截斷 prompt（會 corrupt L1 推理） |
| Audit log | 寫 `agent.ai_invocations` 表 `prompt_token_count` + `over_budget` + 若 fallback 則 `fallback_reason='token_budget_exhausted'` |
| Daily cap monitoring | M3 health domain 監測 `daily_token_budget_exhausted_count`；>5 / 日 → HEALTH_WARN |

**為什麼是 800 token cap 而不是 1000 / 1200**：

| Cap 值 | 對應 SLA | 對應月 cost（400 inf/月 Y2） |
|---|---|---|
| 600 token | 9B P50 ~1.7s，P95 ~3.2s（仍邊際撞 3s SLA P95） | $54-95 / 月 |
| **800 token（選定）** | **9B P50 ~2.5s，P95 ~4.5s**（P50 安全，P95 邊際） | **$72-126 / 月** |
| 1000 token | 9B P50 ~3.2s，P95 ~5.5s（P50 撞 SLA） | $90-158 / 月 |
| 1200 token | 9B P50 ~3.8s，P95 ~6.5s（全撞） | $108-189 / 月 |

800 是「P50 安全 + P95 邊際可接受 + Y2 月 cost 控制在 $72-126（≈ DOC-08 informal cap 1.2-2.1x）」的綜合最優點。P95 不嚴格滿足 `<3s` 是接受的妥協，因為：

1. L1 P95 偶發超 3s 對 trading hot path 無直接影響（L1 是 thought gate 路由層，超時 fallback 到 statistical-only path 仍可下單 per Decision 3）
2. v5.8 §2 M3 self-monitoring 會把 P95 SLA breach 寫進 health domain，超頻則 auto-degrade
3. 真正 P95 `<3s` 嚴格化留到 ADR-0042（未來 ContextDistiller v5 + 模型量化或 Apple Silicon 部署後）

### Decision 3 — Statistical-Only Fallback Path

當 `token_budget_exhausted` 或 LLM provider unavailable 或 L1 latency P95 連續 5 次破 SLA 時，ContextDistiller v4 切換至「不呼叫 LLM 純規則」path：

| 元素 | 設計 |
|---|---|
| Trigger | (a) token cap 違規 / (b) LLM provider 5xx / (c) L1 latency P95 連續 5 次 >5s / (d) 月度 cost > 80% Y2 cap（per Decision 4）|
| Fallback 行為 | 用既有 statistical signals 走 conservative default：rolling z-score / percentile / M3 health current state / M8 severity / M7 decay flag 純規則 decision tree |
| 設計 reference | per v5.8 §2 M4 Cowork review pattern (CR-16 末段) — pattern miner stage 1 (cross-correlation + event-window) 純 numpy 已驗證可獨立運作 |
| 寫 audit | `agent.ai_invocations` 寫 `fallback_reason='token_budget_exhausted' / 'llm_unavailable' / 'sla_breach' / 'month_cost_cap'` + `decision_path='statistical_only'` |
| 不影響權威 | Statistical-only path 仍走 GovernanceHub + Decision Lease + Guardian（per ADR-0008 + ADR-0034 LAL）— 不繞風控 |
| Recover 條件 | (a) token budget 恢復 / (b) LLM provider 健康 / (c) L1 latency P95 連續 30 min `<3s` / (d) operator 手動 reset cost cap |

### Decision 4 — DOC-08 §4 AI Cost Cap Amendment（Conditional Two-Tier）

| Tier | 月 cap | 適用 | 觸發條件 |
|---|---|---|---|
| **Y1 baseline cap** | **$60 / 月** | 預設；不需 operator opt-in | 永久（Sprint 1A-β 至 Sprint 10 W36-39 Y1 末） |
| **Y2 conditional cap** | **$150-200 / 月**（opt-in） | operator opt-in 後生效 | Y2 Q1 evaluation packet 通過：(a) M4/M11/M8 narrative ROI 達標（per Y1 末 evidence）+ (b) ContextDistiller v4 800 token cap 在 production 穩定 60d + (c) AI-E + PM + operator 三方 sign-off |

**Y2 opt-in 路徑明示**：

- opt-in 不是 auto-enable；走 LAL 4（capital structure / venue change always operator approval, per ADR-0034）等級 approval
- opt-in granted = operator 在 Console 主動觸發 + AI-E + PM 兩方 review evidence packet
- opt-in 可隨時撤銷（per AMD-2026-05-21-01 opt-in scope counter-mitigation 機制）

**Cost monitoring**：

| 元素 | 設計 |
|---|---|
| Daily AI cost alert threshold | `> $7 / day`（= $200 / 月 prorate）→ M3 HEALTH_WARN |
| Daily AI cost hard halt | `> $10 / day`（= $300 / 月 prorate, Y2 opt-in cap 1.5x buffer）→ M3 HEALTH_CRITICAL + 全 LLM call fallback 到 statistical-only |
| Weekly digest | M3 每週末 digest 報告 cost trend + LAL projection |
| Y2 Q1 evaluation packet 內容 | (1) Y1 末 8w 月平均 cost (2) ContextDistiller v4 800 token P95 stability (3) M4 DRAFT → operator approve 率 (4) M11 narrative actionability （divergence 後 operator real action count）(5) M8 alert true-positive 率 |

**為什麼不直接 cap 升 $200-300 不設 opt-in gate**（per 仲裁 #8 (a)）：

違反 §二 priority order #13「AI 成本感知」+ #14「零外部成本 baseline」。直接升 cap 等同於 ADR-0027 的 Build mode 月 cost 默認膨脹，沒有 evidence 對齊的 Y1 → Y2 transition。Y2 opt-in 是 evidence-gated 路徑，與 ADR-0030/0031/0032 的 Y2 evidence-gated pattern 一致。

**為什麼不直接 Y2 Q1 重評 cap 不立刻 amendment**（per 仲裁 #8 (c) 棄因）：

當下 Sprint 1A-β 派發 即需要 ContextDistiller v4 800 token hard cap enforcement 才能保 L1 SLA。沒有 ADR 級 cap 路徑 = 工程組沒有 Y2 evidence packet 設計目標 = Y2 Q1 重評時無 evidence 可審 = circular。本 ADR 設立 Y2 opt-in path 是讓 evidence accumulation 路徑明確（Sprint 4-9 期間積累上述 5 項 evidence）。

### Decision 5 — M4 Cowork Review Path：純規則 + LLM 混合明示

per AI-E audit Risk 3 + 仲裁 #8 (b) 「砍頻率」核心執行落地：

| 階段 | Path | LLM 用法 |
|---|---|---|
| **M4 Pattern miner stage 1**（Sprint 2-3, 80-120 hr per v5.8 §M4） | **純規則** — cross-correlation + event-window 純 numpy / statsmodels | 0 LLM |
| **M4 Pattern miner stage 2**（Sprint 8, 60-90 hr） | **純規則** — clustering + regime detection 純 sklearn | 0 LLM |
| **DRAFT 寫入 `learning.hypotheses`** | **純規則** — Pattern miner 用 template 自產 1-page summary（pattern + supporting stats + suggested setup） | 0 LLM |
| **Cowork review（Sprint 8+, Y2 active）** | **Hybrid** — 純規則 statistical first（驗 sample size N ≥ 30 / Bonferroni p < 0.05/K / effect size ≥ 0.2 / 6mo sub-period stability / Harvey-Liu-Zhu graveyard / cluster K silhouette 5-fold CV per CR-6）；LLM 僅用於 narrative summary 給 operator | **L2 Claude narrative ≤ 5k token / DRAFT × ≤ 5 DRAFT 月**（Sprint 8 試運行）/ **≤ 20-30 DRAFT 月**（Y2 active） |
| **LLM 不參與 hypothesis ranking / promotion** | 強硬約束 per ADR-0024-lite Cowork operator-assistant scope | L2 Claude 不 read full raw data；只讀 Pattern miner template summary（≤ 3k input token） |
| **Operator final approve / reject** | 走 Console GUI | 不計 LLM cost |

**為什麼 Pattern miner 自產 template summary 取代「LLM 讀 raw 全資料」**：

input token 從 15k → 3k（節 80%）；節 ~$0.024-0.045/DRAFT → ~$0.005-0.010/DRAFT；M4 Y2 月 cost $7.5 → $1.5（縮減 5x）。對齊仲裁 #8 「砍頻率 5-10x」目標。

**月度 cap 配套**：每月 DRAFT 上限 ≤ 30（避免 pattern miner 噪音淹沒 review）；超 30 → 該月 Pattern miner pause + M3 HEALTH_WARN。

### Decision 6 — M11 Counterfactual Replay Narrative Cadence

per AI-E audit Risk 2 + 仲裁 #8 (b) 「砍頻率」核心執行落地：

| 路徑 | Cadence | LLM provider | 預估月 cost |
|---|---|---|---|
| **Daily replay quality digest**（per v5.8 §M11 「Daily replay quality report → operator (Slack)」） | 每日 EOD | **L1 Ollama 9B（self-hosted, 0 LLM cost）** | $0 |
| **Per-divergence narrative**（divergence ≥ threshold OR CRITICAL severity） | 觸發式 | **L1 Ollama 9B** for INFO/WARN；**L2 Claude Sonnet** 僅當 divergence amount ≥ $X (operator-set, default $50) OR CRITICAL severity（per CR-7 dedup contract M11 emit CRITICAL only when 3σ） | 30 daily L1 narrative × $0 + 1-5 L2 narrative / 月 × $0.10 each = **$0.10-0.50 / 月** |
| **Weekly digest（試運行期前 60 day）** | 每週 EOD | **L1 Ollama 9B** | $0 |
| **High volatility week burst（5-10 divergence / day）** | 超 weekly cap → 降級為 weekly digest 而非 daily | 仍 L1（avoid L2 burst） | $0 |

**Divergence threshold 設計（per CR-7 statistical derivation）**：

| Level | 條件 | LLM routing |
|---|---|---|
| INFO | `0 < divergence ≤ 2.5σ` | L1 only（template fill） |
| WARN | `2.5σ < divergence ≤ 3σ OR amount ≥ $50` | L1 only（含 root cause hypothesis prompt） |
| CRITICAL | `divergence > 3σ AND amount ≥ $200` | L2 Claude（深度 narrative + auto trigger M3 HEALTH_WARN） |
| HALT | `divergence > 5σ OR strategy production drift detected` | L2 Claude + M3 HEALTH_CRITICAL + Decision Lease 暫停該策略新單（per ADR-0034 LAL 1 demote） |

**為什麼 daily L1 取代 daily L2**：

L1 self-hosted = 0 LLM cost；template fill 模式 + cache_read ≥ 70% 設計（per token-cost-analysis skill 第 110 行「cache_read / total_input_tokens 比例應 ≥ 50% 為健康」對齊）。M11 narrative 是「日常 status report」性質而非「critical reasoning」，L1 9B 足夠且 latency 充裕（非 hot path，可接受 P95 5-10s）。L2 升級僅留 CRITICAL/HALT level 真正需要深度 reasoning 場景。

**月度 cap 配套**：M11 月度 narrative 預算 ≤ $5（L2 only line）；超出 → 降級全 narrative 為 weekly digest 並 M3 HEALTH_WARN。

### Decision 1-6 之間的依賴拓撲

```
ADR-0027 (operator hours discipline)
  └─ ADR-0041 §Decision 1 (Layered snapshot 三層架構)
     └─ ADR-0041 §Decision 2 (800 token hard cap enforcement)
        ├─ ADR-0041 §Decision 3 (Statistical-only fallback)
        └─ ADR-0041 §Decision 4 (DOC-08 §4 cap amendment, Y1 $60 / Y2 opt-in $150-200)
           ├─ ADR-0041 §Decision 5 (M4 Cowork hybrid path — 5-10x cost reduction)
           └─ ADR-0041 §Decision 6 (M11 narrative L1-first cadence — 10-20x cost reduction)

DOC-08 §4 + §5（baseline，本 ADR Decision 4 amend §4 month cap）
  ├─ Decision 4 對 §4 cap 為 Y1 informal $60 keeping + Y2 conditional opt-in $150-200
  └─ Decision 5/6 對 §5 cost_edge_ratio 計算分子加 M4/M11/M8 attribution（per AI-E audit §3 cost_edge_ratio v2 公式）
```

**ADR-0027 與本 ADR-0041 的關係**：

ADR-0027 治「月度時間預算」；ADR-0041 治「per-inference token 預算 + 月度 cost cap amendment」。兩者並存：ADR-0027 在 Mode level（Build/Observe/Low Activity）控制 operator hour 總量；ADR-0041 在 inference level 控制 token 用量 + 月 cost ceiling。任何未來進一步修改必須開新 ADR amend ADR-0041 + 標明對 ADR-0027 / DOC-08 §4 的相對立場。

## Engineering Scope（per PA dispatch CR-16）

| 階段 | 工時 | Owner | 內容 |
|---|---|---|---|
| **Sprint 1A-β** | **6-10 hr** | AI-E + TW + PM | 本 ADR + ContextDistiller v4 spec design（Layered snapshot 路由表 / Token cap enforcement logic / Fallback path 規範 / DOC-08 §4 amendment language） |
| **Sprint 1B** | **40-60 hr** | E1 + AI-E | ContextDistiller v4 Python IMPL（layered assembly + tokenizer + pre-check + audit logging + statistical-only fallback）+ tests（unit + integration over `agent.ai_invocations` ledger） |
| **Sprint 2-3** | **incremental** | E5 | L1 SLA P95 measurement + 800 token P95 stability validation（Linux trade-core 量測 + Apple Silicon CI tuple sanity） |
| **Sprint 4-9** | **ongoing** | E3 + AI-E | AI cost dashboard（per-day cost trend + cap proximity + fallback rate visualization）+ M3 health domain 新增 `daily_token_budget_exhausted_count` + `daily_ai_cost_usd` metric |
| **Y1 末 Sprint 10 W36-39** | **5-8 hr** | AI-E + PM | Y2 opt-in evaluation packet 起草（5 項 evidence per Decision 4）+ operator review session |

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **(a) Raise cap to $200-300/月 immediately（無 opt-in gate）** | 違反 §二 priority order #13「AI 成本感知」+ #14「零外部成本 baseline」；直接升 cap 等於 ADR-0027 Build mode 默認 spend，沒有 Y1 → Y2 evidence transition；對齊不上 ADR-0030/0031/0032 Y2 evidence-gated pattern |
| **(c) Y2 Q1 重評 cap without amend now** | 當下 Sprint 1A-β 派發即需 ContextDistiller v4 800 token hard cap enforcement 才能保 L1 SLA；沒有 ADR 級 cap 路徑 = 工程組沒 Y2 evidence packet 設計目標 = Y2 Q1 重評時無 evidence 可審 = circular |
| **純 L1 only（no L2 ever）** | M4 alpha hypothesis narrative quality 要求 cluster reasoning + multi-step inference，L1 9B 不足；M11 CRITICAL/HALT divergence narrative 需要深度 reasoning；強行純 L1 = narrative quality 崩盤但 cost = 0 = 工程實際 abandon narrative 功能 |
| **Multi-tier LLM routing（Claude / GPT / Gemini per cost）** | 違反 §一 Product Boundary「baseline 系統必須可在無外部付費服務下運作」+ §十一 External Tools「multi-provider 路由非 declined provider 範圍」；Bring more cost source 不是 cost cap 解法 |
| **Token cap 設 1000-1200（更寬）** | Ollama 9B P50 直接撞 SLA + Y2 月 cost $90-189 vs DOC-08 $60 cap 超 1.5-3x；800 是 P50 安全 + P95 邊際 + cost 適中綜合最優 |
| **Token cap 設 600（更嚴）** | M4 DRAFT review + M11 narrative 在 600 token 內無法提供 useful context；800 是 inject 完整 module state 的最小可行集 |
| **不分層 flat 800 cap** | 失去 task-specific 路由能力 → 任務無關 module state 占 token budget = useful context 壓縮；分層才能優先保留 L0 always + 動態 L2 |
| **不設 fallback path（cap 超即拒絕 inference）** | 違反 §二 priority order #6「失敗默認收縮」應有 conservative degrade path 而非直接 fail；statistical-only fallback 對齊 §二 #6 + #14 |

## Consequences

### Positive

- **L1 Ollama `<3s` SLA P50 安全** — 800 token cap 在 9B P50 ~2.5s，hot path module 設計 cycle time 穩定
- **Y2 LLM cost 控制在 $72-126 / 月** — 約 DOC-08 informal cap 1.2-2.1x；無 Y2 opt-in 也可運作（statistical-only fallback 保底）
- **M4 + M11 narrative cost 縮減 5-20x** — M4 月 $7.5 → $1.5；M11 月 $6-10.5 → $0.10-0.50；合計縮減 ~10x
- **Y2 opt-in path 明示** — 對齊 ADR-0030/0031/0032 evidence-gated pattern，避免 cap 默認膨脹
- **Statistical-only fallback 保底** — token cap 超 / LLM unavailable / SLA breach 三種 failure mode 都有 conservative degrade path
- **DOC-08 §4 amendment 不取代** — DOC-08 baseline 月 ~$60 informal cap 字面表述保留；Y2 opt-in 為 conditional 擴展
- **ADR-0027 framework 不擾動** — operator hours discipline 不變；本 ADR 在 inference-level 補充
- **§二 16 原則合規** — 全 16 條相容（per §二 16 根原則合規確認），核心 #6 / #7 / #13 / #14 / #15 直接受益

### Negative / Risk

- **800 token cap 對未來新 module state 注入造成壓力** — v5.9+ 若新增 M14-M16（per 仲裁 #10 defer v5.9 + ETA）會撞 cap；mitigation = 新 module state 加入 ContextDistiller v4 必走 ADR-0041 amendment（per ADR-0009 ArcSwap hot-reload 對齊，但 schema 變動需 ADR），不可默默膨脹
- **L1 P95 邊際撞 3s SLA**（800 token P95 ~4.5s）— 接受妥協 per Decision 2 三項理由；mitigation = M3 self-monitoring + M8 anomaly 雙層觀察；若 P95 連續 30d 破 5s → 觸發 ContextDistiller v5（ADR-XX future to be assigned；ADR-0042 已用於 M3 health monitoring）
- **Y2 opt-in path 走 LAL 4 等級可能影響 operator 度假時 cap raise 速度** — opt-in 等待 operator session = bot autonomy 邊際受限；mitigation = ADR-0041 接受該妥協（per 仲裁 #8 (b)），Y2 evidence accumulation 期間 cost 維持 Y1 $60 cap 是設計意圖
- **M11 daily L1 narrative quality 不如 L2** — L1 9B 表達能力 limited；mitigation = template fill 模式 + L2 fallback CRITICAL/HALT level 保留；先試運行 60d 評估 quality；若 quality 持續不達標 → 起新 ADR 重議 L1/L2 routing
- **Statistical-only fallback 在 M4 / M11 active 場景的 informativeness 損失** — 純規則 narrative 比 LLM 弱；mitigation = fallback 是 conservative degrade 不是 normal path；M3 health monitoring 確保 fallback 不長期 active（超 30% inference 走 fallback → HEALTH_CRITICAL）
- **DOC-08 §4 cap amendment 在 cross-doc reference 上的協調成本** — token-cost-analysis skill + 其他 ADR / spec 引用 DOC-08 §12 為「AI cost cap」需要批量更正為 §4；mitigation = TW + PA 在 Sprint 1A-β-γ 集中修正 doc cross-ref（不在本 ADR 範圍，列為 H 級 follow-up）
- **每日 cost monitoring threshold $7/day 對 high-burst day 造成 false alert** — Y2 active 階段 multi-DRAFT day 可能 burst；mitigation = M3 health 區分 single-day burst vs 7d 滾動 trend；只有 7d 滾動 > $50 才升 HEALTH_CRITICAL

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| ADR-0027 (AI Plan Mode Time-Based Budgeting, 2026-05-20) | **本 ADR 為其 v4 級延伸**；operator hours discipline 不變，本 ADR 在 inference-level 補 token + cost 預算 |
| ADR-0020 (Layer 2 manual+supervisor-only, 2026-05-09) | **不擾動**；L2 Claude 仍 manual+supervisor-only；本 ADR Decision 6 CRITICAL/HALT L2 narrative 屬「supervisor escalation」allowance |
| ADR-0024-lite (Cowork subscription operator-assistant) | **協作**；M4 Cowork review path（Decision 5）落實 ADR-0024-lite 的 operator-assistant scope，不允許 Cowork 自動 ranking / promotion |
| ADR-0034 (LAL 4 capital structure / venue change always operator) | **協作**；Y2 cap opt-in 路徑（Decision 4）走 LAL 4 等級 approval |
| AMD-2026-05-21-01 (autonomy-vs-human-final-review) | **協作**；opt-in scope 可撤銷 counter-mitigation 直接套用於 Y2 cap opt-in granted 後 |
| DOC-08 §4 AI 預算管理 + §5 注意力稅 | **本 ADR Decision 4 為 §4 cap amendment**；§4 每日 $2.00 硬上限 + 4.4 保守模式 ~$17/月 baseline 保留為 Y1 default；Y2 opt-in 為 conditional 擴展 |
| DOC-08 §8 延遲預算 L1 `<3s` SLA | **本 ADR Decision 2 設 800 token cap 保 P50 SLA**；P95 邊際撞 SLA 接受妥協 |
| token-cost-analysis skill | **本 ADR 為 skill 內「cost_edge_ratio gate / 三大分析」的 ADR 級對應**；skill 為 AI-E 工作 SOP，本 ADR 為治理 contract |
| v5.8 §2 M3 (Self-monitoring/health) | **協作**；新增 `daily_token_budget_exhausted_count` + `daily_ai_cost_usd` health 維度 |
| v5.8 §2 M4 Self-Supervised Hypothesis Discovery | **本 ADR Decision 5 為 M4 Cowork review path 明示**；Pattern miner stage 1/2 純規則設計不變；DRAFT writeback 走 Decision Lease + HMAC 對齊 CR-15 |
| v5.8 §2 M8 Anomaly Detection | **協作**；Decision 6 M11 CRITICAL/HALT 觸發 M3 HEALTH_WARN 與 M8 alert→action（Y2）整合一致 |
| v5.8 §2 M11 Counterfactual Replay | **本 ADR Decision 6 為 M11 narrative cadence 明示**；replay engine 純 numeric 設計不變；narrative routing L1-first |
| v5.8 §M11 ADR-0038（Continuous Validation schema） | **協作**；ADR-0038 IMPL 階段參考本 ADR Decision 6 narrative threshold + L1/L2 routing |
| ADR-0022 wide_parameter_adjustment skill | **協作**；Strategist L1 推理路徑會 inject M1 LAL + M7 decay + M11 divergence（per Decision 1 路由表）→ token budget 800 cap 涵蓋該路徑 |
| `agent.ai_invocations` ledger（per ADR-0027） | **協作**；新增 `prompt_token_count` + `over_budget` + `fallback_reason` 欄位（schema 為 H 級 V### follow-up）|

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | ContextDistiller v4 不影響 order/execution 寫入口；statistical-only fallback 仍走 Decision Lease + Guardian |
| 2 | 讀寫分離 | ✅ | ContextDistiller v4 純讀 + 純組裝 prompt；不寫 runtime state |
| 3 | AI 輸出 ≠ 命令 | ✅ | L1 / L2 narrative 仍走 GovernanceHub + Decision Lease + LAL approval；fallback 路徑同樣走風控鏈 |
| 4 | 策略不繞風控 | ✅ | Statistical-only fallback 仍走 H0 Gate + Guardian；不繞 |
| 5 | 生存 > 利潤 | ✅ | Token cap + cost cap = 對 cost 控制；degrade-not-fail 保 trading 不阻 |
| 6 | **失敗默認收縮** | ✅ **核心受益** | Token cap 超 → statistical-only fallback；不靜默截斷 prompt；不靜默 escalate L2 |
| 7 | **學習 ≠ Live** | ✅ **核心受益** | M4 Cowork review 純規則 + LLM narrative summary；LLM 不參與 hypothesis ranking / promotion；對齊 ADR-0024-lite |
| 8 | 交易可解釋 | ✅ | `agent.ai_invocations` 新增 token count + fallback reason 欄位，trace 完整 |
| 9 | 雙重防線 | ✅ | Local rule (statistical-only) + LLM narrative 雙路徑；fallback 永遠可用 |
| 10 | Fact / inference / assumption 分離 | ✅ | L1 路由表內每條 task-binding 標明「為什麼 inject 該 module state」 |
| 11 | Agent 最大自主 | ✅ | Decision 1-3 不限制 P0/P1 內 agent 自主性；Decision 4-6 限制是 cost 層面非決策層面 |
| 12 | Evolution by evidence | ✅ | Y2 cap opt-in 5 項 evidence packet 走 evidence-gated transition |
| 13 | **AI cost 感知** | ✅ **核心受益** | 800 token hard cap + Y1 $60 / Y2 conditional opt-in $150-200 + M4/M11 narrative cost reduction 5-20x |
| 14 | **零外部成本 baseline** | ✅ **核心受益** | Y1 cap $60 ≈ 月 ~$17 保守模式 (per DOC-08 4.4) 1.5-3.5x 增量；statistical-only fallback 確保 LLM unavailable 也能運作 |
| 15 | **Cowork ≠ 第六 trading agent** | ✅ **核心受益** | Decision 5 明示「LLM 不參與 hypothesis ranking」；Cowork review 走 hybrid path 但 LLM 只 narrative summary |
| 16 | Portfolio > 孤立 trade | ✅ | Cost 控制是 portfolio-level survival 紀律；ContextDistiller v4 routing 表設計考慮 cross-strategy state aggregation |

## Cross-References

- **ADR-0027**：`docs/adr/0027-ai-plan-mode-time-based-budgeting.md`（本 ADR 為其 v4 級擴展，operator-hours discipline 不變）
- **ADR-0020**：Layer 2 manual+supervisor-only（本 ADR Decision 6 CRITICAL/HALT L2 narrative 屬 supervisor escalation allowance）
- **ADR-0024-lite**：`docs/adr/0024-cowork-subscription-operator-assistant.md`（本 ADR Decision 5 M4 Cowork review path 落實其邊界）
- **ADR-0034**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（本 ADR Decision 4 Y2 cap opt-in 走 LAL 4 等級 approval）
- **AMD-2026-05-21-01**：`docs/governance_dev/amendments/2026-05-21--AMD-2026-05-21-01-autonomy-vs-human-final-review.md`（opt-in scope 可撤銷 counter-mitigation 套用於本 ADR Y2 opt-in cap）
- **DOC-08 §4 AI 預算管理**：`docs/decisions/DOC-08_OpenClaw_Bybit_Implementation_Bridge_实施桥梁_V1.md` §4（本 ADR Decision 4 為其 cap amendment；每日 $2.00 / 月 ~$17 baseline 保留為 Y1 default）
- **DOC-08 §5 AI 注意力稅**：同檔 §5（本 ADR Decision 6 narrative cadence + Decision 5 M4 cost reduction 與其 cost_edge_ratio 等級相容）
- **DOC-08 §8 延遲預算**：同檔 §8（本 ADR Decision 2 800 token cap 對應其 L1 `<3s` SLA P50 安全）
- **token-cost-analysis skill**：`srv/.claude/skills/token-cost-analysis/SKILL.md`（AI-E 工作 SOP；本 ADR 為其治理 contract 對應）
- **v5.8 主檔 §2 M4**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §M4 (line 153-186)（Cowork review hybrid path 落地點）
- **v5.8 主檔 §2 M8**：同檔 §M8 (line 279-317)（Anomaly detection Y1 read-only + Y2 trigger）
- **v5.8 主檔 §2 M11**：同檔 §M11 (line 391-423)（Counterfactual replay narrative cadence 落地點）
- **AI-E v5.8 audit**：`docs/CCAgentWorkSpace/AI-E/workspace/reports/2026-05-21--v58_executability_audit.md` Risk 1-3 + must-fix 6 條第 1 條
- **PA dispatch consolidation**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §1 CR-16 + §8 仲裁 #8 + §9 prerequisite #13
- **`agent.ai_invocations` ledger schema**：per ADR-0027 既有；本 ADR 觸發 H 級 V### follow-up（`prompt_token_count` + `over_budget` + `fallback_reason` 新欄位 — schema 不在本 ADR 範圍）

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via PA 仲裁 #8 「(b) 砍頻率 + Y2 Q1 重評」採納 + ADR-0041 立 | 2026-05-21 | 🟡 PROPOSED-pending-commit |
| AI-E | v5.8 executability audit must-fix 6 條第 1 條 + 仲裁 #8 (b) 推薦 + Risk 1-3 分析 | 2026-05-21 | ✅ Drafted（audit recommendation） |
| TW | 本文件起草（per PA dispatch CR-16 Owner = AI-E + TW + PM） | 2026-05-21 | ✅ Drafted |
| PM | 仲裁 #8 (b) 批准 + ADR-0041 立 + Y2 cap opt-in path 框架 | 2026-05-21 | 🟡 Applying（per PA 仲裁 #8） |
| E5 | ContextDistiller v4 800 token P95 SLA validation（Linux trade-core + Apple Silicon CI tuple 量測） | TBD（Sprint 1A-β-ε） | 🟡 PENDING |
| Operator Y2 opt-in | Y2 Q1 cap raise 5 項 evidence packet review | TBD（Y2 Q1 = Sprint 10 W36-39 後 60-90d） | 🟡 PENDING（D+TBD） |

---

*OpenClaw / Arcane Equilibrium ADR-0041 — ContextDistiller v4 (Layered Snapshot + Token Hard Cap ≤ 800 + DOC-08 §4 AI Cost Cap Amendment Y1 $60 / Y2 opt-in $150-200) · M4 Cowork hybrid path · M11 daily L1-first cadence (Proposed, v4 級擴展 ADR-0027；ADR-0027 operator-hours discipline 不變；DOC-08 §4 baseline 保留 Y1 default)*
