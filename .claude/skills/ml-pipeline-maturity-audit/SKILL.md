---
name: ml-pipeline-maturity-audit
description: MIT agent 主用：評估 ML pipeline 真實成熟度與接線狀態、驗證 dormant/shadow/canary 宣稱、phase launch 前 readiness、或疑「表存在=pipeline live」假象時讀。
allowed-tools: Read, Grep, Glob, Bash
---

# ML Pipeline Maturity Audit（ML 管線成熟度審計）

> Authority 使用 `.codex/agent_registry_v1.json` typed matrix：normative policy、implementation contract、active work state、runtime observation、external policy、claim evidence 只在同類內比較。跨類不一致標 DRIFT/CONFLICT；runtime 不得合法化 policy denial。
> 即時內容依相應 authority class 與 fresh evidence 取得，本 skill 不寫死也不建立全局總排序。

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
| **Skeleton** | writer spawn 且接線但 shadow_enabled=false / `None` send / flag 關（仍 0 row）| Combine Layer Part A `shadow_enabled=false`（實際值查 RiskConfig / TODO） | flag 在 RiskConfig 開即 row 開始累 |
| **Shadow** | writer 實際寫 row，但消費端不回影響真實決策（pure observation）| `decision_shadow_exits` rows 有累但 ExecutorAgent shadow_mode=true | row > 0 且 SubmitOrder IPC 仍未發 |
| **Canary** | 有 model/signal 走 gate 但僅 gating shadow inference（非 live 倉位）| `model_registry` canary status 但 production_id null | promotion 路由 `/api/v1/ml/model_promote` 已可呼 |
| **Production** | 消費端實質改變倉位/風控決策、灰度放量中 | Strategist live=true 走實際 IPC SubmitOrder（當前狀態查 TODO / runtime） | engine PID active + SubmitOrder count > 0 in last 24h |

## 4 維度評級表（空白模板，sub-agent 必跑 SQL/grep 自行填）

每階段對應每個 pipeline component 必填以下 4 維度。**本 skill 不示範 baseline 表**（會 drift；用過期 component 狀態當結論違反 §★ 對抗性驗證）：

| Component | Writer spawn? | Consumer exists? | Row 累積? | Decision impact? | Stage |
|---|---|---|---|---|---|
| (sub-agent 跑 §0 step 0 SQL+grep 後填) | | | | | |

每行真值來源：`SELECT count(*), max(ts) FROM learning.X` + `grep -r "spawn_X_writer" rust/openclaw_engine/src/` + `grep -r "FROM learning.X" rust/openclaw_engine/src/ control_api_v1/` + IPC/API endpoint 確認。

## 工作流（step 0-10，含 step 0 強制重驗）

0. **Re-verify 從 SSOT 拿真值**（強制）：對每 component 跑 SQL（`SELECT count(*), max(ts) FROM learning.X`）+ grep writer spawn（`grep -r "spawn_X_writer" rust/openclaw_engine/src/`）+ grep consumer SELECT（`grep -r "FROM learning.X" rust/openclaw_engine/src/ control_api_v1/`）。**本 skill 不寫死 baseline；任何 audit 結論必基於本次 step 0 實測值**。

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

## Model Registry 審計軸

對 `model_registry` 類 component 額外驗 4 項：
- **Promotion gate 存在性**：canary → production 升級是否有明確 gate（API / 審批路徑），非默認直升
- **Rollback 路徑**：production model 可否一步回退到上一版本；回退是否留 audit 記錄
- **Model-data lineage**：模型版本 ↔ 訓練數據窗口（date range + engine_mode filter）對應可追溯
- **Canary 評估記錄**：canary 期間的評估 metric 是否實際落表（非只有 status 字段）

## OpenClaw component 狀態 — 必現場重驗

OpenClaw 各 ML component 的階段 + 阻塞原因隨 commit + Phase 演進變動，本 skill 不寫死狀態表。實際各 component 狀態：跑 step 0-10 工作流（V### migration check + SQL row count + grep writer spawn + grep consumer + IPC 確認 + healthcheck wiring），現場填表；**禁直接 cite 本 skill 內的 component 階段**。

## 反模式（見即懷疑）

- 「Phase X live」聲明但 row count = 0
- writer 代碼在但 startup.rs 沒 spawn
- `CREATE TABLE IF NOT EXISTS` 後 schema 不符（V023 silent-noop 類事件，依 §sql/migrations/templates Guard A）
- consumer SQL 在但 IPC 路徑未 wire
- healthcheck 沒對應 check_X() 函數
- shadow flag default ON（risk: 上線即真寫）

## 與 V023 / V019 / V021 silent-noop postmortem 的關聯

新 SQL migration 規範要求 Guard A/B/C，但 audit 時要二次確認：
- Guard A 是否有 RAISE EXCEPTION 觸發過（測試環境）
- 既有 legacy stub 有沒有 retrofit
- `audit_migrations.py` 是否定期跑

MIT 審計時若發現 V### 沒 Guard A → 列為 BLOCKER，回 E2 改。

## 穩定 schema rule（不會 drift）

`engine_mode IN ('live','live_demo')` filter 必含兩者；edge_estimator JSON = `strategy::symbol` top-level key；`OPENCLAW_AUTO_MIGRATE=1` opt-in 路徑 refuse-to-start on ambiguous（架構級）。

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

MIT returns an immutable `role_fragment_v1` with `payload_kind=finding_fragment_v1` for the task closure; no automatic report or memory append.
```
