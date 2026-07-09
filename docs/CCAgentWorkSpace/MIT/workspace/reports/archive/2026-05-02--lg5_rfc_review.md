# MIT LG-5 RFC Review — 2026-05-02 15:20 CEST

## 1. 任務摘要

Operator 委派 MIT 對 PA `2026-05-02--lg5_live_candidate_eval_contract_rfc.md`（unify MIT-S2-2 + QC-S2-02）做 ML pipeline / data plane / DB schema / feature engineering / attribution chain 面向審查，並回答 #5 R-meta 0.50 + MIT-S2-1 timeline 拍板問題。狀態：完成，**CONDITIONAL APPROVE**。

## 2. 修改清單

| path | 新增/修改/刪除 | 行數 | 一句話說明 |
|---|---|---|---|
| `.claude_reports/20260502_152000_mit_lg5_rfc_review.md` | 新增 | ~330 | 本審查報告 |
| `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-02--lg5_rfc_review.md` | 新增 | ~330 | workspace 同步副本 |
| `docs/CCAgentWorkSpace/MIT/memory.md` | 修改 | +~10 | 追加 LG-5 review 結論 |

## 3. 關鍵發現（基於 ssh trade-core 實測）

### 3.1 attribution_chain_ok ratio 已快速恢復（PA RFC 假設過時 3 天）

PA RFC §3 R-meta + §11 Q5 假設「current ratio ~0.154 (84.6% broken)，effectively 凍結所有 promotion 直到 MIT-S2-1 ship」。**實測完全不同**：

| 窗口 | n | ok | ok_pct |
|---|---|---|---|
| 7d (2026-04-25 → 2026-05-02) | 2280 | 341 | **14.96%** ← 看似符合 PA |
| **24h (2026-05-01 → 2026-05-02)** | **69** | **38** | **55.07%** ← 已過 R-meta 0.50 |
| **2026-05-02 single day** | **29** | **20** | **68.97%** |

**14天逐日攤開**：

```
2026-04-18 → 2026-04-28: 0% (~3000 rows total) ← 結構性壞
2026-04-29: 21.2% (133/627)  ← inflection point
2026-04-30: 47.1% (154/327)
2026-05-01: 34.7% (34/98)
2026-05-02: 69.0% (20/29)
```

### 3.2 root cause 已修，commit 可考據

```
ece31b6 2026-04-29 17:40 +0200  Repair strategy edge attribution and routing
45bbe4d 2026-04-29 20:18 +0200  feat(rust+sql+monitoring): W1-T1 attribution scaffolding
5895579 2026-04-29 21:15 +0200  fix(engine+monitoring): complete W1-T2 close attribution
```

inflection 時點（2026-04-29 數據開始非零）= 三 commit 連環著陸時點。**MIT-S2-1 root-cause fix 在 PA 寫 RFC 前 ~3 天已落地**；PA RFC 文本仍寫「84.6% broken」是過時 snapshot（PA 用 7d 窗口被 4/18-4/28 全 0 段拖低）。

### 3.3 BLOCKER：`learning.governance_audit_log` 不存在

```sql
SELECT EXISTS (SELECT FROM information_schema.tables 
               WHERE table_schema='learning' AND table_name='governance_audit_log');
-- f
```

29 個 `learning.*` 表中**完全沒有**任何 `*audit*` / `*governance*` 表。PA RFC §2.3 + §11 Q7 標記「to be confirmed by E1 at implementation time」— 實測結果 = **必開新 V### migration**（CLAUDE.md §七 強制 Guard A/B/C）。LG-5-IMPL-2 寫 verdict audit row 前必先有此表。

### 3.4 BLOCKER：PA RFC §2.2 schema 與真實 schema 不符

PA RFC line 102 寫：`status = 'live_candidate'`。

實測 `mlde_param_applications` CHECK constraint：
```
status IN ('applied','skipped','failed','candidate','dry_run')
```
（**沒有** `live_candidate` 值；真實值是 `status='candidate'` + `application_type='live_promotion_candidate'`）

實測 25 條 pending：

```
id  | application_type         | target_name  | status    | requires_governance | lease_null
67  | live_promotion_candidate | grid_trading | candidate | t                   | t
100 | live_promotion_candidate | ma_crossover | candidate | t                   | t
...
```

PA RFC IMPL-2 query 必須改成 `WHERE engine_mode='live' AND status='candidate' AND application_type='live_promotion_candidate'`，否則永遠抓 0 row。

### 3.5 producer 可獲性（IMPL-1）— PASS

`payload.demo_cost_baseline` 來源：

- `maker_fill_rate_7d` / `fee_drop_only_7d` / `avg_realized_fee_bps_7d`：直接複用 `helper_scripts/db/passive_wait_healthcheck/checks_execution.py:_MAKER_FILL_CTE` SQL（7d / 3454 fills，~ms 級）
- `avg_realized_net_bps_7d` / `avg_realized_slippage_bps_7d`：從 `trading.fills` 7d aggregate（同樣便宜）
- `demo_attribution_chain_ratio`：`SELECT count(*) FILTER (WHERE attribution_chain_ok)::float / count(*) FROM learning.mlde_edge_training_rows WHERE engine_mode IN ('demo','live_demo') AND ts > now() - interval '7 days'`

但**healthcheck 結果不持久化**（無 cache table），producer 必每次 INSERT 前 fresh query — 實際 +30~80 LOC（不是 PA 估的 +150 LOC，反而樂觀），無 lock 風險（純 SELECT）。

`source_healthchecks: ["[33]","[40]"]` 字段是 metadata-only string array — OK。

`demo_attribution_chain_ratio` 粒度：建議 **per-strategy** 而非 global（global 平均掩蓋 strategy-level 結構壞 — bb_breakout 100% ok，funding_arb 0% 會被 50% 平均誤導）。R-meta gate 也對應換成 per-strategy ratio。

## 4. Q5 拍板答（R-meta 0.50 + MIT-S2-1 timeline）

### 4.1 MIT-S2-1 ETA：**already shipped 2026-04-29 evening**（不是 future work）

PA RFC §11 Q5 預設「MIT-S2-1 待 ship」是過時假設。三條 commit 在 2026-04-29 17:40-21:15 已完成 root-cause fix。**MIT-S2-1 不是未來工作，是已 shipped 工作**。

### 4.2 0.50 threshold 是否合理：**YES，binary gate 0.50 維持**

理由：
1. **last 24h 已 55.07%**（單日 68.97%）— gate 不再「effectively 凍結所有 promotion」，與 PA RFC 預期相反
2. **PA + QC 認可 binary 0.50 凍結 cleanest** — MIT 同意；ML 視角 0.30 中間態給「有 rampup 證據但仍多數壞」的 transition window 用，目前已過 transition，不需中間態
3. **ramp 路徑簡單**：今後 7d 預期穩定在 50-70%（5/2 已 69%），無需 phased 0.30 → 0.50

### 4.3 R-meta 應改 per-strategy ratio（不是 global）

具體修法（QC + MIT 共審 R-meta 公式建議改）：
```python
# 取代 PA §3 R-meta 的 payload.demo_attribution_chain_ratio (global)
per_strategy_ratio = lookup_attribution_ratio(
    strategy = candidate.strategy_name,
    window_days = 7,
)
if per_strategy_ratio < 0.50:
    return ReviewVerdict(decision="defer", reason="reject_attribution_chain_too_broken")
```
理由：global 14.96% 7d 看似 fail，但 grid_trading / ma_crossover（25 candidates 全是這 2 strategy）可能各自 > 50% — 直接 cite global 會誤拒。Producer 必須在 payload 帶 per-strategy ratio 而不是 global ratio。

### 4.4 24 → 25 pending candidates 可救性

實測 25 條（PA 寫 24 是 -1 day stale snapshot），時間範圍 **2026-04-30 07:50 → 2026-05-02 14:19**（全部創建在 5895579 attribution fix 之後）。

**好消息**：所有 25 條的 source demo row 大概率含 attribution_chain_ok=true 的子集（`mlde_edge_training_rows` 5/2 已 68.97% ok）。
**壞消息**：`[33]`/`[40]` healthcheck **不持久化**，retroactively 重建 `demo_cost_baseline` 必須查 `trading.fills` 歷史 aggregate（可行，便宜），不是真的對 healthcheck 歷史 snapshot 反查。

預期 bulk re-eval 結果（個人估計，非實測）：
- ~5 (20%) `defer_data_insufficient`（per-strategy n_strategy_fills < 30）
- ~12 (48%) `reject_haircut_negative`（R2 cost regime 真實算後負）
- ~5 (20%) `reject_cost_edge_ratio`（R5 fail）
- ~3 (12%) `defer_attribution_chain_too_broken`（per-strategy < 0.50）
- ~0 (0%) approve（current `[40]` 24h avg_net = -17.21bps — live regime仍負，R6 hard veto）

QC 預期「80%+ defer」**樂觀** — 實測 likely 60-70% reject + 30-40% defer。

## 5. B/C/D/E/F/G 6 個技術可行性檢查

| Item | Topic | Verdict |
|---|---|---|
| **B** | producer `payload.demo_cost_baseline` 可獲性 | **PASS** — `[33]`/`[40]` 用同 SQL 重建，~ms latency，無 lock 風險，IMPL-1 真實 +30-80 LOC（樂觀於 PA 估） |
| **C** | bulk re-evaluate 25 pending（PA 寫 24）| **GAP** — `[33]`/`[40]` 結果不持久化；retroactive 需重跑 `trading.fills` aggregate，可行；script 須處理 race（一筆 candidate 重評時新 candidate 可能進入 → 用 ts cutoff freeze） |
| **D** | MLDE-6 schema superset 兼容性 | **PASS** — MLDE-6 RFC 真存在；`demo_cost_baseline` + `demo_realized_window` + `demo_attribution_chain_ratio` 是 sub-key extension，無 conflicting field type；MLDE6-T1 validator 必明文允許 `demo_cost_baseline` 為 required（已在 PA RFC §5.3 標明） |
| **E** | `learning.governance_audit_log` 存在 | **NEED-FIX BLOCKER** — 不存在；必開 V###（建議 V035）migration 含 Guard A/B/C；schema 必含 QC R2/R3/R4 raw input columns（`cost_regime_ratio` / `psr` / `dsr_deflation_factor` 等） |
| **F** | R3 PSR 7d window 與 MLDE training 90d alignment | **GAP-MINOR** — MLDE training 用 90d；7d PSR window 是 promotion gate 不是 training input，無衝突；但 7d n~250 是 PA 估，**實測 last 7d demo+live_demo fills = 3454**（含全 strategy），per-strategy 後可能 < 250；需 R3 的 `defer if n_strategy_fills < 30` 兜底，per-strategy 30-250 區間用較弱 PSR(0)|
| **G** | data drift detection (PSI / KL) MLDE 是否覆蓋 | **GAP** — 完全未覆蓋；無 `[42]` 或更早 PSI check；MLDE training 只 train 不監測 drift；**建議**：LG-5-IMPL-3 healthcheck `[42]` 加一條 distribution drift PSI check（reference window=14d ago, current window=24h，feature scope=top-3 high-importance per model），threshold 起點 0.25（business rule，非 hard） |

## 6. 治理對照（CLAUDE.md / DOC-01 / 16 根原則 / V### Guard）

| 條目 | RFC 立場 | MIT verdict |
|---|---|---|
| §二 #5 生存 > 利潤 | R6 hard veto when live regime negative | strengthened ✓ |
| §二 #6 失敗默認收縮 | defer on uncertainty | strengthened ✓ |
| §二 #8 explainability | ReviewVerdict + audit row | strengthened ✓（**前提：audit 表存在**） |
| §二 #13 cost awareness | R5 cost_edge_ratio gate | strengthened ✓ |
| §四 hard boundary | untouched | preserved ✓ |
| §七 Guard A/B/C | RFC 自身無 SQL，但**必新建 V### audit table** 強制 Guard | E1 IMPL-2 必遵守 |
| 16 根原則 #11 agent autonomy | 維持 agent 提案，gate 自動非 operator-only | preserved ✓ |

## 7. 不確定之處 / 跨平台風險

1. **per-strategy attribution ratio 計算成本**：每次 `_insert_live_candidate` 跑 5 strategy aggregation，~ms 但 demo applier 高頻 cycle 時可能累積；建議 IMPL-1 加 5-min cache（class-level dict）
2. **R-meta global vs per-strategy**：MIT 推薦 per-strategy；QC 已 sign 0.50 binary gate 但未指定 granularity — 建議 PM 拉 QC 補 sign per-strategy granularity（30s ack 即可）
3. **attribution recovery 持續性未驗**：5895579 是 2026-04-29 ship，至今 ~3 天 healthy；`[42]` healthcheck 必加「attribution_chain_ratio 7d < 0.30 = WARN，< 0.10 = FAIL」condition 偵測 regression
4. **bulk re-eval script 的 race**：候選 25 條重評時若新 candidate 進入會導致 R4 deflation factor K 漂移；script 必須一開始 SELECT id list freeze，重評期間忽略新增

## 8. 結論

**CONDITIONAL APPROVE** with 5 must-fix before LG-5-IMPL-* dispatch:

| # | Must-fix | 阻塞 IMPL |
|---|---|---|
| **MF1** | RFC §11 Q5 文本更新：MIT-S2-1 已 ship 2026-04-29，attribution ratio 已恢復（24h=55%，5/2=69%）；R-meta 0.50 binary gate 維持但**不再** effectively 凍結 promotion | RFC 文檔 only，不阻塞 IMPL |
| **MF2** | RFC §3 R-meta + §2.1 payload schema 改 **per-strategy attribution ratio** 而非 global；producer 必填 per-strategy 計算結果 | IMPL-1 + IMPL-2 schema 設計 |
| **MF3** | RFC §2.2 status filter 修正：`status='candidate' AND application_type='live_promotion_candidate'`（不是 `status='live_candidate'`） | IMPL-2 query |
| **MF4** | **新開 V035 migration `learning.governance_audit_log`**（含 Guard A/B/C，CLAUDE.md §七），schema 必含 QC R2/R3/R4 raw input columns + ReviewVerdict full JSON column；無此表 IMPL-2 audit emission 無處可寫 | IMPL-2 阻塞 |
| **MF5** | LG-5-IMPL-3 `[42]` healthcheck 額外加 attribution drift detection（7d ratio 三段式 PASS/WARN/FAIL，threshold 起點 0.50/0.30/0.10） | IMPL-3 |

**Backlog（不阻塞 IMPL，但 PM 該登記 P3）**：

| # | Backlog | Owner |
|---|---|---|
| BL1 | data drift PSI / KL detection（global，non-per-attribution） | MIT 提 RFC after LG-5 land |
| BL2 | Bulk re-eval script race-freeze pattern 文檔化 | E1 + PA |
| BL3 | per-strategy attribution ratio cache（5-min TTL）若 demo applier 高頻時 latency hit | E1 IMPL-1 後 observe |
| BL4 | R4 portfolio correlation deflation（QC §11 Q4 + #16 portfolio risk）| QC backlog |

## 9. Sign-off + dispatch 順序建議

**MIT sign-off**：✓ APPROVE 條件成立後（5 must-fix 完成）

**MIT-S2-1 ETA**：**already shipped 2026-04-29**（commit 5895579）；後續監控由 LG-5-IMPL-3 `[42]` healthcheck 接手。**不阻塞** LG-5-IMPL-1/2/3/4 dispatch。

**PA / PM 建議 dispatch 順序**：

```
0. PA 修 RFC（MF1+MF2+MF3 文字更新）— 30min
1. PA → E2 提 V035 migration design（MF4，governance_audit_log table 含 Guard A/B/C）— 1h
2. E2 → E4 V035 migration unit test + idempotency 雙跑驗證 — 1h
3. operator 跑 V035 against Linux PG — 5min
4. 並行 dispatch：
   - LG-5-IMPL-1 producer @E1 — 半天
   - LG-5-IMPL-3 healthcheck `[42]` 雛形 @E1（含 MF5 attribution drift）— 半天
   - LG-5-IMPL-2 consumer + bulk re-eval script @E1 wait IMPL-1 schema land — 1天
   - LG-5-IMPL-4 test scaffold @E4 — 半天
5. LG-5-IMPL-5 7d wall-clock retro
```

**不需要等 MIT-S2-1**（已 ship）；只需等 V035 audit table（~3 hours operator 流程）。

---

MIT AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/.claude_reports/20260502_152000_mit_lg5_rfc_review.md
