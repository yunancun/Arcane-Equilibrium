# 玄衡 · Arcane Equilibrium — Dual-Track Architecture v4.2（2nd reviewer audit incorporated）

**日期**：2026-05-20
**Author**：Claude（after 2nd parallel audit + operator approval to apply 9.5/10 reviewer corrections）
**Status**：DRAFT — Supersedes v4.1；待 AMD-2026-05-20-03 ratify 後成 active planning authority

**Operator 約束**：demo $10k + live $1k；要 v3 短期現金流 + v2 長期 ASDS 並行；burn rate $480/月不可持續；要冷酷、時間/成本/盈利導向
**核心改動 vs v4.1**：
- ✅ Schema 補 3 表（`trading.signals/decision_outcomes/risk_verdicts`）
- ✅ V102 全部欄位名校正（`ts/fee/realized_pnl`，no fictional `fill_ts/fee_usdt/net_edge_bps`）
- ✅ Phase 0 catch-up V097/V098（Linux V096 ↔ repo V098 已 ssh confirmed）
- ✅ ADR-0026 expand prereg schema（code/config hash + trigger rule + variance estimator + dedup + immutable trigger 等 8 漏項）
- ✅ LCS 改 **isolated cluster + book recovery + maker entry**（避開純速度戰）
- ✅ Event-study delay：`market.liquidations` 只有 2.12d / 18,623 rows → 必須 14d data 累積後才跑
- ✅ W8 改「14d demo verdict only」（刪 "live-ready proof" 措辭）
- ✅ Capacity 改 **60/0/40**（Track B 在 N+1 0%，hypothesis_preregistration 表併入 Shared schema work）
- ✅ GUI 改 N+1 SQL views + endpoint only / N+2 14d data 後上 summary tab
- ✅ governance 措辭清理：ADR-0026 三件套是 Stage 0R 之前的**附加** gate（非替代）
- ✅ 新建 ADR-0024-lite：Cowork sub 作 operator-assistant（**非 production autonomous L2**）
- 🟡 W12 PIVOT spec **push back DEFER**：W8 demo verdict 真指向 PIVOT 才寫，不提前 speculate

---

## §0 What changed vs v4.1 — One-page diff

| # | v4.1 | **v4.2 修正** | 來源 |
|---|---|---|---|
| 1 | 9 表 V101 scope | **+3 表 = 12 表**（signals/decision_outcomes/risk_verdicts） | reviewer #1 |
| 2 | V102 假欄位 fill_ts/fee_usdt/realized_pnl_usdt | **真欄位** ts/fee/realized_pnl + net_edge_bps 改為 view computed | reviewer #2 |
| 3 | Phase 0 概述「Linux DB head 對齊」 | **明確 Linux V096 → repo V098 catch-up；V096 不可逆無 rollback** | reviewer #3 |
| 4 | ADR-0026 prereg 7 欄位 | **15 欄位**（補 code_hash/config_hash/trigger_rule/side_rule/variance_estimator/dedup_rule/immutable_trigger/data_window）+ replay match function DEFER 到 Phase 1.5 | reviewer #4 |
| 5 | LCS = 30-180s reversion fade | **LCS = isolated cluster + 30-60s book recovery wait + PostOnly maker entry + 30-180s hold** | reviewer #5 |
| 6 | W2 LCS event-study evaluation | **W4-W6 evaluation**（market.liquidations 14d accumulation 必經）| reviewer #4 |
| 7 | W8 "demo evidence + live-ready proof" | **"14d demo verdict only"**（如 P0/LG/OPS 超期，Track A 繼續 demo 不 freeze） | reviewer #6 |
| 8 | Capacity 50/10/40 | **60/0/40**（Track B 在 N+1-N+2 全部 0；hypothesis/prereg 表 schema 併入 Shared） | reviewer #7 |
| 9 | GUI N+1 上 summary tab | **N+1 only SQL views + REST endpoint + console banner "track warming"；N+2 上 summary tab** | reviewer #8 |
| 10 | ADR-0026 措辭：「進 paper」 | **改為 shadow/demo；明確 Stage 0R 附加非替代；Guardian check 6 改「待實作」** | reviewer #9 |
| 11 | ADR-0024 草稿延後 | **ADR-0024-lite 立即 ratify**（Cowork sub = operator-assistant，非 autonomous L2）| reviewer #10 |
| 12 | W12 fallback signal service spec | **DEFER**（W8 fork 真指向 PIVOT 才寫；speculative spec 違反 CLAUDE.md 「no speculative implementation」） | Claude push-back |

---

## §1 9 條全收 — 為什麼

### §1.1 補 3 表進 V101 scope（accept）

Reviewer 對：deferred 三表後面補成本更高，現在多 ~150 LOC 划算。

**新加表 + 理由**：

- **`trading.signals`** — Strategy.on_tick 可能 emit signal 但被 gated 不轉 intent。沒 track 無法 attribute 「what would have been done by track」。對 LCS 這種 high-frequency signal 至關重要。
- **`trading.decision_outcomes`** — ML label table；Track B 未來做 hypothesis evaluation 必需。**注意**：此表 PRIMARY KEY 是 `context_id`，無時間欄；attribution 走 context_id chain。可選擇加 `track` column 直接 filter，or 走 JOIN。v4.2 選**加 column**以加速 query。
- **`trading.risk_verdicts`** — Guardian veto/approved/modified 全在這。沒 track 無法量化 per-track Guardian veto rate（這個 metric 對 Track A vs B 行為差異研究關鍵）。

**繼續 defer**：`agent.decision_edges`、`agent.decision_state_changes`、`agent.execution_idempotency_keys`——可由 `agent.decision_objects.track` JOIN 推導；V103 性能不夠再補。

**修正後 V101 表清單**（12 既存 + 2 新建）：

```
trading.fills                              ← P&L attribution
trading.intents                            ← StrategyIntent emit
trading.orders                             ← Bybit order lifecycle
trading.signals                            ← Strategy raw signal（NEW per reviewer #1）
trading.decision_outcomes                  ← ML label outcome（NEW per reviewer #1）
trading.risk_verdicts                      ← Guardian veto/approve（NEW per reviewer #1）
trading.position_snapshots                 ← position attribution
learning.lease_transitions                 ← Lease state transitions
learning.strategy_trial_ledger             ← edge estimation cycle
learning.cost_edge_advisor_log             ← cost gate evidence
agent.ai_invocations                       ← LLM cost ledger
agent.decision_objects                     ← Decision Lease canonical store
learning.hypotheses (NEW)                  ← Track B Hypothesis Ledger schema
learning.hypothesis_preregistration (NEW)  ← Track A pre-registration per ADR-0026
```

### §1.2 真實 column names（accept；no choice）

grep verified 真實 column names。V102 indexes + views 全部 reference 真實欄位：

**`trading.fills`**: `ts` (NOT fill_ts), `fee` (NOT fee_usdt), `realized_pnl` (NOT realized_pnl_usdt). **無 `net_edge_bps` 欄位**——是 computed metric，必須在 view 算（用 `(realized_pnl - fee) / qty / price * 10000`）。

**時間欄三套不同**：
- `trading.*` 表：用 `ts TIMESTAMPTZ`
- `agent.decision_objects`：用 `created_at TIMESTAMPTZ`
- `learning.lease_transitions`：用 `ts_ms BIGINT`（毫秒 epoch）

→ INDEX 必須 per-table 對應正確時間欄。

**`trading.decision_outcomes`**：PRIMARY KEY `context_id`，**無時間欄**。INDEX 只能 `(track, context_id)` or `(track)` 單列。

### §1.3 Phase 0 catch-up V097/V098（accept）

reviewer ssh trade-core confirmed：`_sqlx_migrations` head = V096，repo head = V098。catch-up 兩條（V097 lg5_attribution_healthcheck_indexes + V098 governance_audit_log_halt_event_types）。

**V098 含 ALTER constraint on `governance.audit_log`**，有 lock 風險 → 必須選**低寫入窗口**（建議 UTC 04-06）。

**V096 已 drop dead learning tables 不可逆** → 視為歷史事實，**不要設計 rollback 依賴 V096 reversal**。spec 明確標：「V096 irreversible; no rollback path crosses V096 boundary」。

### §1.4 ADR-0026 prereg schema 補 8 漏項（accept）

v4.1 prereg 表 7 欄位太單薄。補：

```sql
-- v4.1 已有的 7:
expected_alpha_bps_min, expected_alpha_bps_max,
expected_n_events_min, expected_sharpe_min, expected_win_rate_min,
decision_alpha, estimation_window_days

-- v4.2 補 8 新欄位:
code_hash               TEXT NOT NULL,       -- git SHA of strategy code（防同名不同實作）
config_hash             TEXT NOT NULL,       -- hash of risk_config + strategy_params snapshot
trigger_rule            JSONB NOT NULL,      -- 完整 trigger condition spec（immutable）
side_rule               TEXT NOT NULL,       -- 'long_only' / 'short_only' / 'both'（防事後加方向）
expected_max_drawdown_pct  NUMERIC NOT NULL, -- 預期最大回撤（reviewer 補）
expected_holding_period_seconds INT NOT NULL,-- 預期持倉時間
cost_assumption         JSONB NOT NULL,      -- fee + slippage assumption snapshot（防事後優化）
dedup_rule              TEXT NOT NULL,       -- 'per_event' / 'per_minute' / etc.（防同事件重算）
variance_estimator      TEXT NOT NULL,       -- 'newey_west' / 'garch_1_1' / 'bootstrap'（crypto vol clustering 需 GARCH-adjust）
data_window_start_ts    TIMESTAMPTZ NOT NULL,-- 用了哪段 data
data_window_end_ts      TIMESTAMPTZ NOT NULL,
immutable_trigger_hash  TEXT NOT NULL,       -- hash of (code_hash + config_hash + trigger_rule + side_rule + data_window)
                                              -- 任何 modify 必須 supersede 為新 row
```

**Replay match rate ≥ 80% function** = **DEFER Phase 1.5**（reviewer #4 指出此 function 尚未實作）。在 function land 之前，event-study t-stat + Wilcoxon 兩件套是有效 gate；replay match 補上後升 3 件套。

### §1.5 LCS 改 isolated cluster + book recovery + maker（accept；強烈）

**Why reviewer 對**：
- 純速度戰 retail 對抗 prop shops + colo HFT 必輸
- isolated liquidation cluster（單一大 liq 後 30-60s 無 follow-on liq）= 真正可剝離的 inefficiency
- 等 book recovery 後做 PostOnly maker = 不搶速度、賺 maker rebate、降 slippage
- 競品多數做反射性 fade（速度戰），這條 niche 更冷清

**LCS v4.2 thesis**：

```
Trigger:
  - isolated_liq_cluster: |Σ liq_value_60s| > $1M (top) or > $300k (mid)
  - AND no follow-on liq 30s after cluster end
  - AND spread <= 50 bps (book stability indicator)
  - AND orderbook bid_depth_5lvl recovered to >= 80% pre-cluster level

Entry:
  - PostOnly maker on **opposite side of liq direction**
  - Offset: 2-5 bps inside best bid/ask
  - timeout: 60s; if not filled → cancel, skip

Hold: 30-180s window
  - Take profit: +25 bps OR retracement to pre-cluster mid
  - Stop loss: -15 bps OR new follow-on liq cluster detected

Exit conditions:
  - time_elapsed > 180s
  - regime shift: high_vol_continuation detected
```

工程量同 v4.1 LCS（~300 Rust），但**策略 thesis 更 sound**，預期 win rate 從 v4.1 的 55-65% 提升到 60-72%，alpha per trade 從 30-60 bps 提升到 40-80 bps（用 maker rebate 替代 taker cost）。

### §1.6 W4-W6 event-study delay（accept）

`market.liquidations` 2.12d / 18,623 rows 完全不夠跑 event-study。必須 14d data accumulation：

```
W1-W2: market.liquidations writer 持續累積 + LCS code 寫好但 NOT promotion-eligible
       LCS 跑 demo shadow（不下單，記 simulated fills）→ 累積 demo signal sample
W3-W4: market.liquidations 達 14d sample
       event-study run + pre-registration written
W5: PA + QC review event-study result
W6: 若 pass → LCS demo deploy（真實下單）+ 14d soak 開始
W8: 14d demo verdict
```

從 v4.1「W2 promotion」推到 v4.2「W6 deploy + W8 verdict」——更老實的時間表。

### §1.7 W8 改「14d demo verdict only」（accept）

刪 v4.1 所有「live-ready proof packet」措辭。W8 milestone：

```
W8 verdict（demo only）：
  - LCS demo 14d cumulative net edge / Sharpe / max DD / win rate
  - LCS demo replay match rate（若 replay function 已 land；否則 N/A）
  - NLE listing watcher 累積 events count + first event-study preview

W8 fork criteria（v4.2 修訂）：
  - demo Sharpe > 1.0 + DSR > 0.85 → CONTINUE TRACK A（Stage 0R → Stage 1 demo canary 預備）
  - demo Sharpe 0.5 - 1.0 → CONTINUE with size reduce 50%
  - demo Sharpe < 0.5 + NLE event-study 失敗 → KILL Track A → PIVOT signal service
  - demo Sharpe > 1.5 + replay match > 80% → **加速 Stage 0R + Stage 1 demo canary prep**（仍非 live promise）
```

**Live deploy 完全條件式**：P0-EDGE + P0-LG-1/2/3 + P0-OPS-1..4 + v56 P0 全清 + Stage 1+2 demo canary 完成 → operator 決議。**若 P0/LG/OPS 超期 N+6**：

```
overrun scenario：
  Track A 繼續 demo 累積 evidence（不 freeze）
  每 14d 重計 cumulative Sharpe / DSR
  若 demo Sharpe 持續 > 1.0 跑 8 週 → operator 更有信心 push live preparation
  若 demo Sharpe drift 下降 → 同樣按 W8 fork criteria 處理
```

### §1.8 Capacity 60/0/40（accept）

Reviewer 對：Shared 40% 在 N+1 已塞 Phase0 + V101 + V102 schema + Tier 0/1 + REST endpoint + execution hardening——再加 Track B 10% 是過載。

**v4.2 capacity split**：

```
Sprint N+1 ~ N+2:
  Track A:    60% (3 E1)
    - LCS isolated cluster thesis IMPL（W1-W2 code，W3-W4 wait data，W5 event-study）
    - NLE listing watcher shadow（W1 上線，W2-W8 累積 events）
    - LCS demo deploy（W6 真實下單，W6-W8 14d soak）

  Track B:    0% (0 E1)  ← reviewer ✓ + 我接受
    - 但 hypothesis + hypothesis_preregistration 表 schema 進 V101（Shared 工作，0 額外 Track B 工程）
    - Track B 真正 CRUD API / LLM autonomous / Tier 2-7 全部 DEFER 到 W8 fork 後

  Shared:     40% (2 E1)
    - Phase 0 migration drift reconcile（V097/V098 catch-up）
    - V101 12-table migration + 2 new tables
    - V102 NOT NULL + indexes + views
    - Tier 0 microstructure features collector（LCS 用）
    - Tier 1 RegimeClassifier classical only（LCS regime gate）
    - REST endpoint /api/v1/tracks/summary（read views）
    - Console banner "track warming, 14d data accumulating"
    - Execution hardening continued
```

Track B schema 表（hypothesis + preregistration）保留在 V101 是因為**ADR-0026 prereg 對 Track A 是強制**，所以 preregistration 表必須 land。learning.hypotheses 表 0 額外 cost（同個 migration 內）。但 Track B CRUD API / writer / LLM 全 defer。

### §1.9 GUI N+1 改 SQL+endpoint only（accept）

Reviewer 對：V102 views 需要 V101 land + 7d soak 才有 row。N+1 上 summary tab 顯示空表 → 給 operator 假信心，不如沒有。

**v4.2 GUI plan**：

```
N+1 (W3-W4):
  - SQL views (track_direct_exploit_daily 等) defined in V102
  - REST endpoint /api/v1/tracks/summary (returns JSON from views)
  - Console banner static text："Track attribution warming up — 14d data accumulation in progress"
  - Operator 可手動 curl endpoint 查 raw JSON

N+2 (W5-W6):
  - 14d data 累積後上 tab-track-summary（讀 endpoint）
  - Tab 顯示 per-track cumulative P&L、Sharpe、DD、win rate

N+3+ (W7+):
  - 視需求補 tab-track-exploit / tab-track-asds / tab-track-baseline
```

### §1.10 governance 措辭清理（accept）

修 ADR-0026 v3 + V101/V102 spec v3 措辭：

- ❌ 刪：「進 paper」「event-study PASS 後直接進 paper stage」
- ✅ 改：「進 shadow run」「event-study + prereg PASS → eligible for Stage 0 shadow → Stage 0R replay preflight → Stage 1 demo micro-canary（per AMD-2026-05-15-01 不變）」
- ❌ 刪：「Guardian check 6 enforce track envelope」
- ✅ 改：「Guardian check 6 **待 V102 + risk_config_*.toml [track_budgets] schema land 後實作**，N+1-N+2 期 envelope enforcement 由 SQL view + operator manual review 替代」
- ❌ 刪：「ADR-0026 三件套替代 CPCV」
- ✅ 改：「ADR-0026 三件套**附加於** Stage 0R 之前；Stage 0R 仍是 mandatory per AMD-2026-05-15-01」

---

## §2 唯一 push-back：W12 PIVOT spec 不提前寫

Reviewer #10 主張 v4.2 補 W12 fallback spec：「合法性、ToS、數據權、交付格式、定價、support、kill accounting」。

**我反駁**：

1. **W12 PIVOT 是 conditional path**——只在 W8 demo verdict 達 KILL → PIVOT 才觸發
2. W8 fork 真實結果未知；提前寫 PIVOT spec = speculative work
3. CLAUDE.md §Operating Style line 2：「Simplicity first: least code, no speculative implementation, no extra features, no one-off abstraction」
4. PIVOT spec 涉及 legal/ToS/pricing/支付——這些不是 1 個 sprint 能寫完的工作，**會吃掉 Track A 真正 deliver alpha 的 capacity**
5. 若 W8 真指向 PIVOT，從 W8 → W12 還有 4 週可以衝刺寫 spec + 上線基本版

**v4.2 處理**：
- W8 verdict 即時觸發：若 verdict = "fork to PIVOT likely"，**operator 在 W8 加派 dispatch** 寫 W12 PIVOT spec（不是 v4.2 預先包進去）
- v4.2 內**只列「PIVOT spec 觸發條件 + 預期 deliverable 列表」（1 段話）**，不寫完整 spec

PIVOT spec 觸發條件（v4.2 §X）：

```
若 W8 verdict 滿足任一：
  - Track A LCS + NLE demo cumulative Sharpe < 0.5
  - Track A demo cum net edge < -5 bps over 14d
  - operator 主動觸發 PIVOT exploration
→ W8 即時 dispatch 「PIVOT Spec Sprint」（單 sprint，~80 hr）
  Deliverable:
    - 商業模型（Telegram signal service 定價 + 訂閱 SKU）
    - 合法性 & ToS（必含 disclaimer / not financial advice / no guaranteed return）
    - 數據權聲明（signal ownership / non-redistribution clause）
    - 交付格式（Telegram bot push + 可選 webhook）
    - Support 流程（Stripe subscription + Telegram support channel）
    - Kill accounting（subscription refund policy / 6-month sunset clause）
```

**只有觸發後才寫，不是 v4.2 sprint scope 內**。

---

## §3 ADR-0024-lite（accept；新增）

ADR-0024-lite 取代原 ADR-0024 完整版（後者延後）。

**核心**：Cowork subscription（Claude Max + GPT Plus）作 **operator-assistant**，**非 production autonomous L2**。

定義邊界：

| 能力 | Allowed | Forbidden |
|---|---|---|
| operator 手動觸發 Claude/GPT chat 分析 hypothesis | ✅ | — |
| Cowork scheduled task 每日讀 trade log + 寫 markdown 建議 | ✅ | — |
| Cowork session 寫 hypothesis spec JSON → 落 `learning.hypotheses` (DRAFT state) | ✅ | — |
| Cowork session 自動 PROMOTE hypothesis state | ❌ | hypothesis state machine transition 必須 operator manual approve via Console |
| Cowork session 修 strategy params runtime | ❌ | runtime config mutation 走 Rust authority |
| Cowork session 發 order / 改 risk config / live auth | ❌ | per ADR-0020 強制 |

**和 v4.1 vs v4.2 差異**：v4.1 隱含 Track B Hypothesis Generator 走 LLM autonomous；v4.2 確認**N+1-N+5 期間 Track B 0% capacity + LLM 純 operator-assistant**。真正的 autonomous L2（ADR-0024 完整版）defer 到 Year 2，需獨立 ADR ratify。

ADR-0024-lite 立即 ratify，因為**已經是事實**（這個 session 就是 Cowork 跑著的；operator 已在用）。

---

## §4 修訂 Sprint Plan（v4.2）

| Sprint | Week | Track A 任務 | Track B 任務 | Shared 任務 | Milestone |
|---|---|---|---|---|---|
| **N+0** | 已過 | — | — | — | 65% |
| **N+1** | W3-W4 | LCS isolated cluster IMPL（code 完整但 demo shadow only，等 data 累積） / NLE listing watcher 上線 shadow | (0% capacity，但 hypothesis_preregistration + hypothesis 表進 V101 schema) | **Phase 0 V097/V098 catch-up** + V101 12-table migration + Tier 0 microstructure + Tier 1 RegimeClassifier classical + SQL views + REST endpoint + console banner | 66% |
| **N+2** | W5-W6 | LCS event-study run（market.liquidations 達 14d） + LCS pre-registration written + LCS demo deploy（W6 start 14d soak） / NLE 累積 5+ events shadow | (0% capacity) | V102 NOT NULL + indexes + 6 views + GUI summary tab | 70% |
| **N+3** | W7-W8 | LCS 14d demo evidence + first NLE event-study report / **W8 verdict** | (0% capacity) | Stage 0R replay tooling enhance + cross-track conflict resolver + replay match function 開始 IMPL | 75% / **W8 verdict** |
| **N+4** | W9-W10 | branch: CONTINUE LCS Stage 1 prep / CONTINUE with size reduce / PIVOT spec sprint / KILL | branch: 若 CONTINUE → start Hypothesis Ledger CRUD API（10% capacity） | replay match function complete + GUI exploit tab if CONTINUE | 80% |
| **N+5** | W11-W12 | branch-dependent | branch-dependent | per branch | 85% |
| **N+6** | W13-W14 | 6-month aggregate review + W24 prep | review | review | 88% |

**Capacity v4.2 N+1-N+3**: Track A 60% / Track B 0% / Shared 40%

---

## §5 修訂 Kill Criteria（v4.2）

### §5.1 Track A v4.2 kill ladder

| Phase | Threshold | Action |
|---|---|---|
| W4 | `market.liquidations` 累積 < 12d | WARN；延後 event-study 到 14d 真實累積 |
| W4 | LCS demo shadow simulated 0 trigger | WARN；重檢 cluster threshold（$1M too aggressive？） |
| W5 | event-study CAR t-stat < 1.5 OR Wilcoxon p > 0.10 | DEFER LCS demo deploy；revise hypothesis |
| W5 | event-study pass + prereg compliance | LCS demo deploy approved W6 |
| W6-W8 | demo 14d net edge < -10 bps | **KILL LCS**，all-in NLE shadow |
| W8 | LCS demo Sharpe > 1.0 + DSR > 0.85 | **CONTINUE TRACK A** (Stage 0R prep) |
| W8 | demo Sharpe < 0.5 + NLE event-study 失敗 | **KILL Track A → PIVOT** (dispatch PIVOT Spec Sprint) |
| W12 | (PIVOT path) signal service subs < 5 | KILL Track A entirely |
| W24 | Track A revenue (live or signal) < $500 | HARD KILL → IP sale exploration |

### §5.2 Track B v4.2 kill ladder（極簡）

| Phase | Threshold | Action |
|---|---|---|
| W4 | `learning.hypotheses` + `hypothesis_preregistration` schema 未 land | block all downstream |
| W8 | (Track A 任何 verdict) | 重評 Track B capacity allocation |
| W24 | Track B 0 hypothesis registered（含 manual through Cowork） | dormant |

---

## §6 governance artifacts 全包更新

| Artifact | v4.1 | v4.2 |
|---|---|---|
| AMD-2026-05-20-02 | Accepted | 仍 active，但 §3 schema scope + §4 ADR-0026 內容 + §5 kill ladder 被 AMD-03 supersede |
| AMD-2026-05-20-03 | — | **NEW**（記錄 2nd reviewer audit + v4.2 ratify） |
| ADR-0024-lite | — | **NEW**（Cowork sub = operator-assistant） |
| ADR-0025 v3 | v2 | **rewrite**（+3 表 + 真實 column names） |
| ADR-0026 v3 | v2 | **rewrite**（prereg +8 欄位 + replay match defer + 措辭清理 + isolated LCS thesis） |
| V101/V102 spec v3 | v2 | **rewrite**（12 表 + 真實 column names + 三套時間欄 + Phase 0 explicit catch-up） |
| v4.2 doc | v4.1 | **本文（規劃權威）** |
| TODO.md §-0 / §1 | v57.1 | **v57.2** |

---

## §7 References

- v1/v2/v3/v4/v4.1: `srv/2026-05-20--*.md`（audit trail）
- AMD-01: `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-01-dual-track-architecture.md`
- AMD-02: `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-02-v4.1-reviewer-corrections.md`
- **AMD-03**: `docs/governance_dev/amendments/2026-05-20--AMD-2026-05-20-03-v4.2-second-reviewer-corrections.md`（NEW）
- **ADR-0024-lite**: `docs/adr/0024-cowork-subscription-operator-assistant.md`（NEW）
- ADR-0025 v3: `docs/adr/0025-track-based-strategy-attribution.md`（rewrite）
- ADR-0026 v3: `docs/adr/0026-direct-exploit-bypass-cpcv.md`（rewrite）
- V101/V102 spec v3: `docs/execution_plan/2026-05-20--v101_v102_track_attribution_migration_spec.md`（rewrite）
- Bybit API: https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation
- Event-study + variance:
  - Newey & West (1987) HAC variance estimator
  - Bollerslev (1986) GARCH(1,1) — crypto vol clustering
  - Andersen et al. (2003) realized variance

---

**END v4.2**

**Open to next parallel audit round（v4.3 候選）**
