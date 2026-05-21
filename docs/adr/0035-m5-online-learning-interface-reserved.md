# ADR 0035: M5 Online Learning Interface Reserved — Trait Stub + V114 Placeholder, IMPL Deferred Y3+

Date: 2026-05-21
Status: **Proposed**（v5.8 thesis 接受 M5 為 13 module 圖佔位；IMPL deferred 至 Y3+，Sprint 1A-δ 僅交 ModelClient trait stub + V114 reserved migration placeholder）
Operator Sign-off: 2026-05-21（主會話 PM dispatch via D1 v5.8 §2 M5 ADD-per-operator LOW priority interface reservation only + D4 interface-stub policy for M5/M12/M13 已批）
Related: ADR-0021 (Alpha Source Architecture Upgrade) / ADR-0034 (M1 Decision Lease LAL) / ADR-0039 (M12 OrderRouter interface reservation 同 pattern) / ADR-0040 (M13 multi-venue interface reservation 同 pattern) / v5.8 §2 M5 (lines 188-217) / v5.8 §3.5 Sprint 1A-δ / v5.8 §10 ADR roster line 749 / v5.8 §10 Risk #2 "DESIGN-only debt mitigated by ADR-0035/0039/0040 explicit retirement criteria" / PA dispatch consolidation `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` 行 163 Sprint 1A-δ deliverable / memory `project_ml_dl_learning_architecture` (LightGBM + Optuna + 3DL daily-batch baseline)

## Context

### 起源 — v5.8 13 module 圖中 M5 佔位但 Y1 不 IMPL

v5.8 主檔 §2 M5（lines 188-217）將「Online learning / incremental model update」列為 13 module 之一，但同條目明示：

```
v5.8 design (interface reservation only Sprint 1A; IMPL Y3+):
  Sprint 1A: Interface stub + ADR-0035 (8-12 hr)
  Y3+: actual IMPL (estimated 200-400 hr) when:
    (a) daily retrain proven insufficient (e.g., regime shift faster than daily granularity matters)
    (b) AUM > $50k (justify ML infra investment)
    (c) operator opt-in
```

operator 2026-05-21 D1 明寫「M5 must add at low priority — 這是個後續開發的點」（per PA report 行 21）。v5.8 §10 ADR roster 行 749 列 ADR-0035 為 Sprint 1A-δ 新增 ADR，但既有 12-check Sprint 1A-β dispatch readiness checklist 漏列；ADR-0036 / ADR-0040 已 land，0035 + 0037 + 0038 在 v5.8 §10 7 ADR 名單但僅 0036 / 0040 + 0038 + 0039 已 draft，0035 缺。本 ADR 補齊以維持 §10 一致性 + 為 Sprint 1A-δ M5 trait stub dispatch 提供 ADR 級邊界。

### 既有 ML 架構不被取代（memory `project_ml_dl_learning_architecture`）

OpenClaw 既有 ML 為 daily-batch retrain：

| 元素 | 既有設計 | Y1 + Y2 角色 |
|---|---|---|
| LightGBM | Teacher-Student baseline | daily cron 訓練，daily boundary swap |
| Optuna | hyperparameter search | weekly / monthly cron |
| 3DL | 三層 deep learning（Teacher / Student / Distill） | daily cron + 模型版本 register |

本 ADR **不取代** 上述既有 ML 路徑。M5 online learning 是「在 daily-batch 之上加 streaming 更新層」，前提是 daily-batch 已證實不足以承載 regime shift 速度。Y1 + Y2 daily-batch 仍是主路徑。

### 為什麼 trait stub 只列在 Sprint 1A-δ（不在 Sprint 1A-β / γ）

per PA dispatch packet（行 159-167）Sprint 1A-δ deliverable = M5 + M12 + M13 三個 interface stub 一起 land：

- M5 ModelClient trait stub（6 method slots default panic）
- M12 OrderRouter trait stub（5 method slots default panic + maker_fill_rate_30d metric）
- M13 AssetClass + Venue enum（DEX/Hyperliquid hardcode 拒絕）

三個 stub 共享同一個治理 pattern：**interface 預留 + V### reserved migration placeholder + retirement criteria 明示**。本 ADR 為 M5 對應 ADR；ADR-0039 為 M12 對應；ADR-0040 為 M13 對應。三者同 Sprint 派發、同 dispatch 紀律。

### 為什麼必須在 Sprint 1A-δ DESIGN 階段 land ADR

per `feedback_v_migration_pg_dry_run.md` + Sprint 1A-δ V114 reserved migration placeholder：V114 不寫 DDL（per v5.8 §9 行 797「V114 reserved frontmatter only, not used Y1」），但 frontmatter 必引用 ADR-0035 作為 schema 預留意圖的權威來源；無本 ADR → V114 placeholder spec doc 引用懸空 → Sprint 1A-ε cross-ADR consistency audit fail。

### 與 ADR-0021 Alpha Source Architecture Upgrade 關係

ADR-0021 R-2 Strategist 是 alpha-source orchestrator；R-3 hypothesis pipeline 是 first-class governance object。M5 online learning **不繞 R-2 / R-3**：

- M5 streaming 模型更新後的 prediction 仍走 R-2 Strategist 統一發 proposal
- 任何 streaming 更新引發的 strategy parameter shift 仍走 R-3 hypothesis pipeline + ADR-0034 LAL 1 (intra-strategy reparam) 或 LAL 2 (cross-strategy reweight) 路徑
- M5 不創旁路寫入口（per §二 原則 1）

## Decision

**Proposed**：以下 4 項決策合併鎖入 M5 interface reservation 治理紀律。

### Decision 1 — ModelClient Trait Stub（6 method slot, default panic）

Rust 端 `openclaw_engine` 預留 `ModelClient` trait 為 ML 模型推論統一介面；Sprint 1A-δ 只實作 trait 骨架，6 method slot 默認 `unimplemented!()` panic（即「未實作即 fail-loud」）。

| Method slot | 用途 | Y1 + Y2 行為 | Y3+ IMPL 行為 |
|---|---|---|---|
| `get_predict(features) -> Prediction` | 同步預測（既有 daily-batch 模型路徑） | **既有 LightGBM / 3DL daily-batch 已 IMPL；本 trait method 為其包裝介面** | 包裝不變；增加 streaming model fallback |
| `get_predict_streaming(features) -> StreamingPrediction` | 即時推論（streaming 更新版） | **default panic（trait stub only）** | Sprint Y3+ IMPL：streaming weight 增量更新後即時推論 |
| `drift_callback(distribution_metrics)` | feature distribution 漂移回呼（KL divergence trigger） | **default panic** | Sprint Y3+ IMPL：drift detection → 觸發 Strategist propose model rollback |
| `rollback(version)` | 回滾到指定模型版本（safety net） | **default panic** | Sprint Y3+ IMPL：streaming 模型 degrade → rollback to daily-batch baseline |
| `throttle(rate_per_sec)` | streaming 更新速率限流（防 over-fit single fill） | **default panic** | Sprint Y3+ IMPL：rate-limited streaming update + cooldown |
| `health() -> ModelHealth` | 模型健康度（per ADR-0034 LAL gate criteria 對齊 evidence） | **default panic** | Sprint Y3+ IMPL：streaming model 誤差 + drift + 樣本量綜合 health metric |

**反模式（明示禁止）**：

- (a) Y1 + Y2 在任何 module 呼叫 `get_predict_streaming` / `drift_callback` / `rollback` / `throttle` / `health`：違反 stub-only 紀律，trait fail-loud 設計就是要 panic
- (b) Sprint 1A-δ 把任一 method 改為 default no-op（`Ok(())` 回傳）：違反 fail-closed 紀律，後續 caller 誤以為 stub 已 IMPL
- (c) trait 預留 method slot 但未對齊 §Decision 2 V114 schema column：trait + schema 必同步預留

### Decision 2 — V114 Reserved Migration Placeholder（Y1 不寫 DDL）

per v5.8 §9 line 797 + PA report 行 163 reserve 路徑：

| 元素 | 設計 |
|---|---|
| V114 SQL file | **Sprint 1A-δ 不創建** `sql/migrations/V114__online_learning_models.sql`；spec doc placeholder only |
| V114 spec doc | `docs/execution_plan/2026-05-21--v114_online_learning_models_schema_spec.md`（frontmatter + cross-ref 本 ADR + Y3+ activation trigger condition；不含 DDL） |
| Y3+ activation 時點 | 本 ADR §Decision 4 三條件 (a)(b)(c) 全滿足 → 開新 amendment ADR + V114 full DDL Sprint land |
| Y3+ activation 觸發後 schema 草案（不在本 ADR 鎖定） | `learning.online_learning_models`（含 `model_id` / `version` / `streaming_enabled BOOL DEFAULT FALSE` / `drift_threshold` / `last_streaming_update_ts` / `rollback_baseline_version`）+ `learning.streaming_updates_audit`（per update audit row）— 草案僅參考，Y3+ activation 時走完整 IMPL DESIGN |
| `streaming_enabled` 預留欄 | **既有 `learning.model_versions` 表加 `streaming_enabled BOOL NOT NULL DEFAULT FALSE` column** Sprint 1A-δ；Y3+ activation 時改 DEFAULT TRUE 並啟用 streaming 路徑 |

**反模式（明示禁止）**：

- (a) Sprint 1A-δ 真寫 V114 SQL：違反 reserved placeholder 紀律 + sqlx checksum drift 風險（per memory `project_2026_05_02_p0_sqlx_hash_drift`）
- (b) `streaming_enabled` 預設 TRUE：違反 fail-closed + default-OFF 紀律
- (c) V114 spec doc 缺 cross-ref 本 ADR：cross-ADR consistency audit fail

### Decision 3 — IMPL 觸發 6 條件（3 必要 + 3 hardening）

Y3+ M5 online learning 真實 IMPL 開始的 6 條件，必 6 條全 PASS：

| # | Condition | 來源 | 評估方法 |
|---|---|---|---|
| (a) | **daily-batch retrain 已證實不足** | v5.8 §2 M5 line 211 + 本 ADR | 兩個並行條件：(a1) regime shift latency 觀察 ≥ 6 month 樣本顯示 daily granularity 失靈 + (a2) M11 nightly replay divergence ≥ N bps 持續觸發 |
| (b) | **AUM > $50k sustained 30d** | v5.8 §2 M5 line 212 | per v5.8 §5 capital-tier ladder Y3 Q2 estimate $75-150k；$50k 是 ML infra 投入 break-even 點 |
| (c) | **operator opt-in** | v5.8 §2 M5 line 213 | per ADR-0034 LAL 4 capital structure / 新模塊啟用 → operator approval mandatory；走 5-gate review session |
| (d) | **M9 A/B framework 已 GA** | 本 ADR 新增 | streaming 模型必透過 ADR-0037 M9 A/B framework 做 control vs variant 對比；無 M9 = 無 framework 驗 streaming 真有 alpha；per ADR-0037 GA 條件 |
| (e) | **Live PnL 連續 3 month > 0** | 本 ADR 新增 | per §二 原則 5 生存 > 利潤；Live 失血期間禁啟新 ML 模型路徑；3 month 是 minimum stable window |
| (f) | **既有 LightGBM / 3DL daily-batch 連續 30d Sharpe > X** | 本 ADR 新增 | streaming 是「在穩定 baseline 之上加層」；若 daily-batch baseline 本身 unstable，streaming 只放大 noise；Sharpe threshold 由 Y3+ activation 時 PM + MIT 仲裁 |

**6 條 AND 邏輯**：6 條全 PASS → 開新 ADR amend 本 ADR Decision 4 + Y3+ V114 full DDL Sprint land；任一 FAIL → 維持 trait stub 狀態，繼續 defer。

### Decision 4 — Retirement Criteria（per v5.8 §10 Risk #2 explicit）

per v5.8 §10 Risk #2 "DESIGN-only debt mitigated by ADR-0035/0039/0040 explicit retirement criteria"：trait + V114 placeholder 不是永久債務，必有明示退役條件。

| Retirement 條件 | 觸發行為 |
|---|---|
| **R1**：Y3 末（Sprint 30 / W144 預估）仍無 Decision 3 (a)+(b)+(c) 觸發 | 開新 ADR Supersede 本 ADR + dead-code removal PR（移除 ModelClient trait + V114 placeholder + `streaming_enabled` column）|
| **R2**：M5 範疇被其他 module 吸收 | 例：M9 A/B framework 擴展為「variant-as-streaming-update」途徑，或 M6 Bayesian reward weight tuning 已涵蓋 streaming 更新需求 → 開新 ADR Supersede 本 ADR + 移除冗餘 trait |
| **R3**：operator 永久放棄 online learning 路徑 | 例：Live evidence 連續 12 month 顯示 daily-batch 足夠 + AUM 增長已穩定 → 開新 ADR Supersede + ADR-debt closure |
| **R4**：替代技術出現 | 例：未來出現 OpenClaw 採用的 streaming ML framework（如 vendor SaaS / 開源 streaming library）+ 經 evaluation 後 trait 設計不適用 → 開新 ADR amend |

**Retirement audit cadence**：Sprint 10 Y1 Review + Y2 Q4 + Y3 Q2 各一次 evaluation（per v5.8 Sprint roster）；evaluation 結果寫入 `learning.adr_retirement_audit` table（per ADR-0034 audit pattern 延伸）。

## Alternatives Considered

| Alternative | 棄因 |
|---|---|
| **Drop M5 entirely**（v5.8 §12 optional shortcut option）—— 不 land trait stub | 違反 operator 2026-05-21 D1「M5 must add at low priority」directive；M5 是 13 module 圖完整性要素；trait stub cost 僅 8-12 hr，未來 Y3+ 真需要時無 schema breaking change cost；ROI 顯著傾向保留 stub |
| **Y1 真實 IMPL streaming 更新** | 違反 v5.8 §2 M5 design「IMPL Y3+」+ operator low priority directive；Y1 $10k AUM 下 streaming marginal gain ≤ 1-2% APR（per v5.8 §2 M5 line 217）；200-400 hr IMPL cost 對 Y1 ROI 不成立 |
| **Trait method 只列 2-3 個（不列 6 個）** | 6 個 method slot 對應完整 online learning lifecycle（predict / streaming predict / drift / rollback / throttle / health）；列少於 6 個 → Y3+ activation 時需 amend 補 missing method → trait breaking change；一次列足 6 個雖 stub 階段都 panic，但 retirement criteria audit 時知道哪些是 dead code |
| **Trait method 默認 no-op（`Ok(())`）而非 panic** | no-op 違反 fail-loud / fail-closed 紀律；Y1 + Y2 任何 caller 誤呼 streaming method 會 silent 通過 → 後續 review 階段才發現「咦這 method 根本沒實作」；panic 是強制 caller 在 Y1 + Y2 不該呼叫的 fail-loud 邊界 |
| **不創 V114 placeholder，Y3+ activation 時再分配 V### number** | sqlx migration 順序是 git 歷史強制單向；Y3+ 才分配 V### 會撞既有 V114-V200 已 land 的 number；提前 reserve V114 + 不寫 DDL 是 schema number planning 紀律（per v5.8 §9 + ADR-0009 ArcSwap 對齊） |
| **不立本 ADR，只在 v5.8 §10 列名 ADR-0035** | v5.8 §10 ADR roster 是高階索引，無法替代 ADR 級邊界；Sprint 1A-δ M5 trait stub dispatch 時 sub-agent 必引用本 ADR 為 trait 6 method 設計 + V114 reserved migration + retirement criteria 來源；無本 ADR → sub-agent 缺權威，可能誤把 stub 寫成 no-op 或漏列 method |
| **本 ADR 涵蓋 Decision 3 詳細 streaming 更新算法 design** | streaming 算法選型（incremental gradient descent / online RandomForest / streaming PCA 等）是 Y3+ 真實 IMPL DESIGN 階段範疇；本 ADR 級紀律應只鎖 interface + V### placeholder + 觸發條件 + 退役條件；algorithm-level 決策走未來 amendment + spec doc |

## Consequences

### Positive

- **v5.8 §10 ADR list 完整性** — 7 ADR 名單（0034-0040 + 0041）皆有對應 ADR draft；Sprint 1A-β D+5~D+6 派發 readiness 12-check #5 可勾
- **Sprint 1A-δ trait stub dispatch 治理紀律明示** — 6 method slot 預留 + default panic + V114 reserved 三件一次性鎖入；sub-agent dispatch 時零 ambiguity
- **未來 Y3+ activation 路徑明確** — 6 條件 AND gate + retirement audit cadence 對齊 §二 原則 6 失敗默認收縮 + 原則 12 evidence-based evolution
- **零 schema breaking 風險** — V114 reserved + `streaming_enabled` DEFAULT FALSE 預留欄都是 Y3+ activation 時即 ALTER table flip default 即可，不需 schema rewrite
- **與 ADR-0021 R-2/R-3 對齊** — M5 streaming 不繞 Strategist orchestrator + hypothesis pipeline；保 alpha-source governance 紀律
- **與 ADR-0034 LAL 對齊** — Y3+ activation 走 LAL 4（新模塊啟用 = capital structure 級）operator approval mandatory；不創 autonomy 旁路

### Negative / Risk

- **trait 死碼 Y1~Y3 約 6 method panic** — sibling test 必驗 panic 行為，但 trait 物件存在 + 6 method body 都是 `unimplemented!()`；mitigation = sibling panic test `tests/m5_model_client_stub_panic.rs` 5 case（每 method 各一 + trait 整體 not-implemented assertion）+ retirement audit cadence Sprint 10 / Y2 Q4 / Y3 Q2 三輪
- **V114 reserved number 佔位 Y1~Y3 不用** — schema number 序列保留 V114 為 placeholder；mitigation = v5.8 §9 已將 V114-V116 全列為 reserved frontmatter only；Sprint 1A-ε cross-V### dependency graph audit 確認 V114 是 reserved 而非 active
- **6 觸發條件中 (d) M9 GA 依賴 ADR-0037 land** — 本 ADR Decision 3 (d) 引用 M9 framework GA；ADR-0037 屬同集合 7 ADR 之一；mitigation = ADR-0037 與本 ADR 在 Sprint 1A-β prerequisite #5 同集合補位；不存在跨 ADR 循環依賴（M9 不依賴 M5）
- **(e) Live PnL 連續 3 month > 0 對 Y3+ activation timing 可能延遲** — Y1 + Y2 P0-EDGE-1 / P0-LG-3 / P0-OPS-1..4 closure 後才開 Live；Live 3 month sustained 可能 Sprint 5+ 才達到；mitigation = (e) 條件本意就是 evidence-gated 紀律，延遲是 by design
- **(f) daily-batch baseline Sharpe threshold X 待 Y3+ PM + MIT 仲裁** — 本 ADR 不鎖 X 數值；mitigation = Y3+ activation 真接近時 PM 仲裁定 X，避免本 ADR 寫死過時 threshold；evidence-based amendment 路徑符合 §二 原則 12
- **retirement criteria R4「替代技術出現」評估較主觀** — vendor SaaS / 開源 library 出現後 evaluation 需要時間；mitigation = retirement audit cadence 三輪 + Sprint 10 Y1 Review 是 evaluation 啟動點

### 與既存設計協作

| 既存元素 | 與本 ADR 關係 |
|---|---|
| 既有 LightGBM / Optuna / 3DL daily-batch（memory `project_ml_dl_learning_architecture`） | **不變**；M5 streaming 是「在 baseline 之上加層」非取代；Y1 + Y2 daily-batch 仍是主路徑 |
| ADR-0021 Alpha Source Architecture Upgrade | **M5 streaming 不繞 R-2 Strategist + R-3 hypothesis pipeline**；任何 streaming-derived prediction 仍走統一 alpha-source orchestrator |
| ADR-0034 M1 Decision Lease LAL | **Y3+ activation 走 LAL 4 capital structure**（新模塊啟用 = operator approval mandatory）；M5 streaming 更新引發的 strategy reparam 走 LAL 1（intra-strategy） |
| ADR-0037 M9 A/B framework（待 land） | **Decision 3 (d) 引用 M9 GA 為觸發條件**；streaming 模型必透過 M9 control vs variant 驗 alpha |
| ADR-0039 M12 OrderRouter interface reservation | **同 Sprint 1A-δ deliverable + 同 interface-reservation pattern**；6 method slot 對應 M12 5 method slot 相似治理紀律 |
| ADR-0040 M13 multi-venue interface reservation | **同 Sprint 1A-δ deliverable + 同 interface-reservation pattern**；retirement criteria 紀律同樣明示 |
| v5.8 §2 M5 (lines 188-217) | **本 ADR 為 v5.8 §2 M5 module 治理 ADR 級落地**；Y3+ IMPL 觸發 3 條件被本 ADR Decision 3 擴為 6 條 |
| v5.8 §9 V114 reserved | **本 ADR Decision 2 為 V114 placeholder 設計權威**；V114 spec doc cite 本 ADR |
| v5.8 §10 Risk #2 retirement criteria | **本 ADR Decision 4 為其落地**；R1-R4 retirement 條件 + audit cadence 明示 |
| memory `project_2026_05_02_p0_sqlx_hash_drift` | **V114 不寫 DDL 即避免 sqlx checksum drift**；本 ADR Decision 2 反模式 (a) 明示禁止 Sprint 1A-δ 真寫 V114 SQL |
| `feedback_v_migration_pg_dry_run.md` | **V114 placeholder spec doc 不需 dry-run**（無 DDL）；Y3+ activation 真寫 V114 SQL 時必走 PG dry-run |

## §二 16 根原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | M5 streaming prediction 仍走 R-2 Strategist 統一發 proposal；不創旁路寫入口 |
| 2 | 讀寫分離 | ✅ | streaming model 訓練 / 推論純讀；任何 live state mutation 經 Strategist + Decision Lease |
| 3 | AI 輸出 ≠ 命令 | ✅ | streaming prediction 仍是 proposal，必經 LAL gate（per ADR-0034）；M5 不繞 Decision Lease |
| 4 | 策略不繞風控 | ✅ | Guardian gate / 5-gate kill / risk envelope check 對 M5 streaming 路徑生效；Y3+ activation 走 LAL 4 operator approval |
| 5 | 生存 > 利潤 | ✅ | Decision 3 (e) Live PnL 連續 3 month > 0 條件 = evidence-gated；失血期間禁啟新 ML 模型路徑 |
| 6 | 失敗默認收縮 | ✅ | Decision 1 trait method default panic（fail-loud）+ Decision 2 `streaming_enabled` DEFAULT FALSE + Decision 4 retirement R1 Y3 末未觸發 → dead-code removal |
| 7 | 學習 ≠ live | ✅ | M5 streaming 是 learning surface；Y3+ activation 必經 ADR-0037 M9 A/B framework 驗 alpha；不直接寫 live state |
| 8 | 交易可解釋 | ✅ | streaming 模型版本經 `learning.model_versions` 表 register + per-streaming-update audit row（Y3+ activation 時 V114 schema）；audit trail 完整 |
| 9 | 雙重防線 | ✅ | trait method `rollback()` + `health()` + LAL gate + Guardian = 多層；streaming model 誤差 → rollback to daily-batch baseline |
| 10 | 分離事實 / 推論 / 假設 | N/A | trait stub 不涉 reasoning 紀錄；reasoning lineage 由既有 lineage 系統處理 |
| 11 | Agent 在 P0/P1 內自主 | ✅ | Y3+ activation 後 streaming 更新在 P0/P1 內自主；新模塊啟用本身走 LAL 4 operator approval |
| 12 | Evidence-based evolution | ✅ | Decision 3 6 條件全 evidence-based（regime shift latency / AUM / operator opt-in / M9 GA / Live PnL / baseline Sharpe） |
| 13 | cost 感知 | ✅ | trait stub Y1 cost = 8-12 hr；full IMPL 200-400 hr 推 Y3+ AUM > $50k 後 ROI 成立才啟動；retirement R1 Y3 末未觸發 → dead-code removal 防永久債 |
| 14 | 零外部成本 | ✅ | streaming framework 默認自建（沿用既有 LightGBM / 3DL infrastructure）；retirement R4 若引入 vendor SaaS 需新 ADR amend |
| 15 | 多 agent 形式化協作 | ✅ | M5 dispatch 涉及 PA / MIT / TW / E1 / E4 等 role；per Sign-off table |
| 16 | Portfolio > 孤立 trade | ✅ | streaming 更新引發的 strategy reparam 走 LAL 1（intra-strategy）或 LAL 2（cross-strategy reweight），後者明示 portfolio-level 治理 |

## Cross-References

- **v5.8 §2 M5 Online Learning**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:188-217`（本 ADR module 來源）
- **v5.8 §3.5 Sprint 1A-δ**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:573`（Sprint 1A-δ deliverable 列 M5 trait stub）
- **v5.8 §9 V114 reserved**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:797`（V114 reserved frontmatter only）
- **v5.8 §10 ADR roster**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:749`（ADR-0035 列入 7 新 ADR 名單）
- **v5.8 §10 Risk #2**：`docs/execution_plan/2026-05-20--execution-plan-v5.8.md:817`（DESIGN-only debt mitigated by ADR-0035/0039/0040 explicit retirement criteria）
- **ADR-0021 Alpha Source Architecture Upgrade**：`docs/adr/0021-alpha-source-architecture-upgrade.md`（R-2 Strategist orchestrator + R-3 hypothesis pipeline 對齊）
- **ADR-0034 M1 Decision Lease LAL**：`docs/adr/0034-decision-lease-layered-approval-lal.md`（Y3+ activation 走 LAL 4 + streaming reparam 走 LAL 1）
- **ADR-0037 M9 A/B framework**（待 land）：本 ADR Decision 3 (d) 引用 M9 GA 為觸發條件
- **ADR-0039 M12 OrderRouter interface reservation**（待 land）：同 Sprint 1A-δ deliverable + 同 interface-reservation pattern
- **ADR-0040 M13 multi-venue interface reservation**：`docs/adr/0040-multi-venue-gate-spec.md`（同 Sprint 1A-δ deliverable + retirement criteria 紀律同源）
- **PA dispatch consolidation report**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md`（行 163 Sprint 1A-δ M5 trait stub deliverable）
- **PM final verdict**：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-21--v58_pm_final_verdict.md`（D1 ADD-per-operator + D4 interface-stub policy 已批）
- **memory `project_ml_dl_learning_architecture`**：既有 LightGBM / Optuna / 3DL daily-batch baseline（M5 streaming 為「baseline 之上加層」非取代）
- **memory `project_2026_05_02_p0_sqlx_hash_drift`**：V114 不寫 DDL 即避免 sqlx checksum drift（Decision 2 反模式 (a) 對應）
- **`feedback_v_migration_pg_dry_run.md`**：Y3+ activation 真寫 V114 SQL 時必走 Linux PG empirical dry-run

## Engineering Scope Reference

| Sprint | Item | Workload |
|---|---|---|
| Sprint 1A-δ | ModelClient trait stub（6 method default panic）+ V114 reserved placeholder spec + `streaming_enabled` column 加入既有 `learning.model_versions` | 8-12 hr |
| Sprint 10 Y1 Review | retirement audit #1（評估 Decision 3 6 條件 + R1-R4 retirement signal） | 1-2 hr |
| Y2 Q4 | retirement audit #2 | 1-2 hr |
| Y3 Q2 | retirement audit #3 + 若 6 條件 PASS → 開新 amendment ADR + Y3+ activation Sprint planning | 2-4 hr audit + 200-400 hr full IMPL（若 activation） |
| Y3 末（若未 activation） | Decision 4 R1 觸發 → dead-code removal PR + Supersede ADR | 4-8 hr |

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | 主會話 PM dispatch via D1 v5.8 §2 M5 ADD-per-operator LOW priority + D4 interface-stub policy 已批 | 2026-05-21 | ✅ APPROVED-pending-commit |
| TW | 本文件起草（v5.8 §10 ADR-0035 補位 + Sprint 1A-β prerequisite #5 一致性 + Sprint 1A-δ M5 trait stub dispatch 邊界） | 2026-05-21 | ✅ Drafted |
| MIT | trait 6 method slot 設計確認 + V114 schema 草案 review | TBD（Sprint 1A-δ） | 🟡 PENDING |
| E1 | ModelClient trait IMPL（Sprint 1A-δ default panic）+ V114 reserved spec doc IMPL | TBD（Sprint 1A-δ） | 🟡 PENDING |
| E4 | sibling panic test `tests/m5_model_client_stub_panic.rs` 5 case + retirement audit cadence 對齊 | TBD（Sprint 1A-δ） | 🟡 PENDING |
| QA | Sprint 1A-δ trait stub dispatch grep gate（防 default no-op 反模式）對齊 dispatch SOP | TBD（Sprint 1A-δ） | 🟡 PENDING |
| PM | Y3+ activation 觸發評估仲裁 + retirement audit 仲裁（Sprint 10 / Y2 Q4 / Y3 Q2） | TBD（Sprint 10 起） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0035 — M5 Online Learning Interface Reserved: ModelClient Trait Stub (6 method default panic) + V114 Reserved Migration Placeholder + 6 Condition AND Gate Y3+ Activation Trigger + Explicit Retirement Criteria (Proposed per 2026-05-21 v5.8 §10 ADR roster 一致性 + Sprint 1A-β prerequisite #5 補位 + Sprint 1A-δ M5 dispatch 治理邊界)*
