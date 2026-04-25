---
name: ml-pipeline-maturity-audit
description: ML pipeline 成熟度審計 — 5 階段（Foundation / Skeleton / Shadow / Canary / Production）+ 4 維度（writer-spawn / consumer-exists / row-accumulation / decision-impact）評級框架。MIT agent 主用，避免「表存在 = pipeline live」假象。
allowed-tools: Read, Grep, Glob, Bash
---

# ML Pipeline Maturity Audit（ML 管線成熟度審計）

> **優先序**：runtime RiskConfig TOML > Rust schema > CLAUDE.md > 治理 .md > memory > 本 skill
> **衝突時向 PM / operator push back，不單方面執行 skill 內 SOP**

## 何時觸發

- MIT 收到「ML pipeline 進度評估」「H1-H5 / Layer 2 / 5-Agent / Combine Layer 接線狀態」
- TODO 出現 dormant / shadow / canary 字眼需要驗證
- V023 / V019 / V021 silent-noop 類事件後重新 audit
- Phase 2/3 launch 前的 pipeline readiness 評估

## ★ 黃金法則

**對抗性驗證**：
- **「表存在」≠「pipeline live」**
- **「writer 有 spawn」≠「有 row」**
- **「有 row」≠「consumer 存在」**
- **「consumer 存在」≠「影響真實決策」**

每個 ML 階段必須對 4 維度逐項驗，不能用「應該」「設計上」當證據。

## 5 階段成熟度

| 階段 | 定義 | 例子 | 驗證 SQL / shell |
|---|---|---|---|
| **Foundation** | 表 + 索引 + writer 代碼到位，runtime 暫時全空 | V021 `learning.decision_shadow_exits` 接線後 0 row | `SELECT count(*) FROM learning.X` = 0 但 schema check pass |
| **Skeleton** | writer spawn 且接線但 shadow_enabled=false / `None` send / flag 關（仍 0 row）| Combine Layer Part A `shadow_enabled=false`（CLAUDE.md §三） | flag 在 RiskConfig 開即 row 開始累 |
| **Shadow** | writer 實際寫 row，但消費端不回影響真實決策（pure observation）| `decision_shadow_exits` rows 有累但 ExecutorAgent shadow_mode=true | row > 0 且 SubmitOrder IPC 仍未發 |
| **Canary** | 有 model/signal 走 gate 但僅 gating shadow inference（非 live 倉位）| `model_registry` canary status 但 production_id null | promotion 路由 `/api/v1/ml/model_promote` 已可呼 |
| **Production** | 消費端實質改變倉位/風控決策、灰度放量中 | Strategist live=true 走實際 IPC SubmitOrder（CLAUDE.md §十） | engine PID active + SubmitOrder count > 0 in last 24h |

## 4 維度評級表

每階段對應每個 pipeline component 必填：

> ⚠️ **警告：以下表是 2026-04-24 baseline 快照**。Sub-agent **必須先 re-verify** 才能用作 audit 結論：每行的 Writer/Consumer/Rows/Decision 都會隨 commit / TOML flag flip / row 累積變動。**任何用本表內容當「現在事實」直接結論 = 違反本檔 §★ 黃金法則對抗性驗證**。

| Component | Writer spawn? | Consumer exists? | Row累積? | Decision impact? | Stage |
|---|---|---|---|---|---|
| `decision_shadow_exits` | ✅ Rust task | ❌ none | ❌ flag off | ❌ no | Skeleton |
| `model_registry` | ✅ Python | ✅ Rust read helper | ❌ awaiting V024+ | ❌ all 404 | Foundation |
| `exit_features` | ✅ Rust | ⚠️ partial | ✅ ~0.05-0.5 atr | ⚠️ shadow only | Shadow |
| `edge_estimates` | ✅ scheduler | ✅ cost_gate | ✅ 187 cells | ⚠️ gate not bound | Skeleton+ |

## 工作流（11 步審計，含 step 0 強制重驗）

0. **Re-verify 不信表內快照**（強制）：對每 component 跑 SQL（`SELECT count(*), max(ts) FROM learning.X`）+ grep writer spawn（`grep -r "spawn_X_writer" rust/openclaw_engine/src/`）+ grep consumer SELECT（`grep -r "FROM learning.X" rust/openclaw_engine/src/ control_api_v1/`）。**確認與本檔 §「OpenClaw 已知 ML pipeline 狀態」表一致**；不一致即更新表 + audit 報告開頭 RETRACT 漂移點。

1. **Migration 對照** — V001-V024 全部 schema 是否套用：`SELECT * FROM _sqlx_migrations` + `audit_migrations.py`
2. **Hypertable 確認** — TimescaleDB chunk 是否實際建：`SELECT show_chunks('learning.X')`
3. **Index 存在** — `\d+ table` 看 partial / unique / hot-path index
4. **Writer code path** — grep `INSERT INTO learning.X` 在 Rust + Python
5. **Writer spawn** — startup log 看 `spawn_X_writer` 是否真執行
6. **Row count + freshness** — `SELECT count(*), max(ts) FROM learning.X`
7. **Consumer existence** — grep `SELECT FROM learning.X` 找 reader
8. **Decision impact** — 對應 IPC 路徑 / API endpoint 是否 active
9. **Healthcheck wiring** — `passive_wait_healthcheck.py` 是否有對應 check_X()
10. **Stage 評級** — 5 階段 + 4 維度填表

## OpenClaw 已知 ML pipeline 狀態（2026-04-24 baseline）

> ⚠️ **警告：以下表是 2026-04-24 採集 baseline**。Pipeline 狀態 / 阻塞原因會隨日期變動，sub-agent **必須對每 component 重跑 SQL + grep verify** 才能引用本表。**直接信用 = 違反本檔 §★ 對抗性驗證**。

| Pipeline | 階段 | 阻塞 |
|---|---|---|
| LinUCB shadow compare | Skeleton | Phase 4 子任務 4-06 deferred（memory `project_linucb_shadow_compare_retention`）|
| Combine Layer (decision_shadow_exits) | Skeleton | shadow_enabled=false TOML flag |
| Model Registry (V023) | Foundation | P1-7 C labels 47/200 累積中 |
| Edge Estimator | Skeleton+ | cost_gate 門檻 grand_mean > -50 bps 未滿足 |
| StrategistAgent | Production | shadow=False (Sprint 5a live) |
| ExecutorAgent | Skeleton | `_shadow_mode=True` hardcoded（G3-02 Wave 2 fix）|
| Exit features writer | Shadow | atr scale 修復後（P0-13）但 consumer 未接 |

## 反模式（見即懷疑）

- 「Phase X live」聲明但 row count = 0
- writer 代碼在但 startup.rs 沒 spawn
- `CREATE TABLE IF NOT EXISTS` 後 schema 不符（V023 silent-noop 類事件，依 §sql/migrations/templates Guard A）
- consumer SQL 在但 IPC 路徑未 wire
- healthcheck 沒對應 check_X() 函數
- shadow flag default ON（risk: 上線即真寫）

## 與 V023 / V019 / V021 silent-noop postmortem 的關聯

CLAUDE.md §七「新 SQL migration 規範」要求 Guard A/B/C，但 audit 時要二次確認：
- Guard A 是否有 RAISE EXCEPTION 觸發過（測試環境）
- 既有 legacy stub 有沒有 retrofit
- `audit_migrations.py` 是否定期跑

MIT 審計時若發現 V### 沒 Guard A → 列為 BLOCKER，回 E2 改。

## OpenClaw 特定核心

- **engine_mode IN ('live', 'live_demo')**：filter 必含兩者
- **outcome_backfiller fix**（commit `5e2981d`）：timeframe '1' → '1m' + engine_mode INSERT
- **edge_estimator JSON**：strategy::symbol top-level，不是 cells{}
- **Engine auto-migrate (V024)**：`OPENCLAW_AUTO_MIGRATE=1` opt-in，refuse-to-start on ambiguous（CLAUDE.md §七）
- **passive_wait_healthcheck**：cron 6h 跑 17 個 check
- **5 strat × 25 symbol × 1m**：data row 量級高，hypertable + chunk 必須

## Cross-Skill 互引（避免重述）

- **C1.c feature pipeline 細節**：本 skill 看 pipeline 「writer/consumer/row/decision-impact」4 維度評級；**leakage 6 維度**（look-ahead / target / survivorship / cross-section / time-zone / resample boundary）+ **shift(1) compliance** 走 `feature-engineering-protocol`
- **C1.h V### Guard A/B/C / hypertable schema / chunk / partial index**：本 skill 引用 schema 設計教訓（V023 silent-noop），但**真正 schema audit + retrofit SOP** 走 `db-schema-design-financial-time-series`
- **CV 設計**：ML 訓練 CV / Purge / Embargo 走 `time-series-cv-protocol`（MIT）；策略 alpha 顯著性走 `walk-forward-validation-protocol`（QC）

## 輸出格式

```markdown
# MIT ML Pipeline Maturity Audit — <date>

## Migration 套用狀態
| V### | name | applied | guard A retrofit |

## Component 評級表
| Component | Writer | Consumer | Rows | Decision | Stage | Blocker |

## 整體系統評級
- Production: X 個 component
- Canary: Y
- Shadow: Z
- Skeleton: W
- Foundation: V

## V023/V019/V021 類風險
（list 任何缺 Guard A/B/C 的 migration）

## Healthcheck 覆蓋
| component | check id | last status |

## 結論 + 建議行動
1. <具體 + 修復路徑>

MIT AUDIT DONE: <report_path>
```
