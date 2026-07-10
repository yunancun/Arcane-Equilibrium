# PROFIT-1 cost_gate 雙重扣成本溯源 — E1 · 2026-07-10

任務：R3 修復包 charter WP-A 第 5 點。溯源 cost_gate 的 edge 語義——輸入 edge 是否已扣成本、gate 內是否再扣一次。證實則最小範圍修+測試；證偽則記錄證據。

## 結論：證實（CONFIRMED），但修法依三條硬約束交會後取最小安全解＝本任務不改 gates.rs（偏差理由見 §5）

三層結論：
1. **輸入 edge 已扣成本**（已實現淨值：fee＋實際成交價內含滑點＋funding）。
2. **gate 內再扣一次**（前瞻 `fee_bps = 2×(fee_rate+slippage)×1e4` 作門檻分子）→ 成本語義上被計兩次。
3. **active 面唯一在 demo side-specific 分支（PROFIT-RCA-2026-06-19d）**；live 與 demo coarse validated 路徑因 `validation_passed` 前置維持 dormant。2026-06-18 的 NO-FIX 裁決「dormant」前提自 06-19 起已 stale——PG 實證 30d 內 71,207 筆正淨 edge 被門檻拒（全 demo mode）。

## 1. 證據鏈（producer：edge 是淨值）

| file:line | 事實 |
|---|---|
| `program_code/ml_training/realized_edge_stats.py:405-408` | `net_bps_raw = _bps(gross_pnl_usd − entry_fee_usd − exit_fee_usd, denom_bps)`——入場+出場 fee 已扣；`gross_pnl_usd` 來自 DB fill `realized_pnl`（實際成交價 → 已實現滑點內含） |
| `realized_edge_stats.py:523-525` | funding 併入 `net_pnl_bps`（winsorize 後） |
| `program_code/ml_training/james_stein_estimator.py:384` | JS 收縮輸入 `raw_values = [stats[k].mean_net_bps]`（淨值均值） |
| `james_stein_estimator.py:436-442` | `runtime_bps = shrunk_values[i]`（=收縮後淨值；A-4(B2) 後不歸零） |
| `james_stein_estimator.py:188-228` | side overlay cell：`net_pnl_bps` 原始均值直接寫 `shrunk_bps`/`runtime_bps`；`:224` `validation_passed: False` 硬編碼（`entry_side_overlay_demo_only_not_promotion_evidence`） |
| `rust/openclaw_engine/src/edge_estimates.rs:168-206` | Rust 讀 `runtime_bps`（fallback `shrunk_bps`）→ `CellEstimate.shrunk_bps`；無成本語義轉換 |

## 2. 證據鏈（gate：第二次扣成本）

| file:line | 事實 |
|---|---|
| `rust/openclaw_engine/src/intent_processor/gates.rs:33`（paper）`:145`（demo）`:448`（live） | `fee_bps = 2.0×(fee_rate+slippage)×10_000`——前瞻來回成本（runtime per-symbol fee + tier slippage），第二份成本 |
| `gates.rs:45`（paper）/ `:147-152` 閉包（demo，用於 `:236,:243,:350`）/ `:475-478`（live） | `threshold_bps = fee_bps / clamp(win_rate, floor, 1.0) × safety_multiplier`；`shrunk_bps < threshold_bps → reject` |
| Linux `settings/risk_control_rules/risk_config_demo.toml` | floor=0.3、safety=1.3、min_n=15（親讀 2026-07-10） |

語義：淨 edge（已付真實成本）被要求再蓋過一份完整來回成本 ×1.3/wr。以 modal 拒絕為例（見 §4）：+3.61bps 淨 edge（已付 ~4bps maker 來回費，gross≈7.6bps）被要求 ≥8.80bps ⇔ gross ≥12.8bps ≈ 3.2× 來回費。成本計兩次成立。

## 3. Active / dormant 面分類（本次溯源的關鍵更新）

| 路徑 | file:line | 前置 | 狀態 |
|---|---|---|---|
| live `cost_gate_live_with_slippage` | gates.rs:437-502（門檻 :479） | `fresh && from_runtime_field && validation_passed`（:457） | **dormant**：Linux `settings/edge_estimates.json`（`_meta.updated_at=2026-07-09T21:58Z`，236 cells）validated-positive=0 |
| demo coarse positive | gates.rs:327-363（門檻 :351） | 同上三前置（:334），unvalidated → 探索放行 return None | **dormant**（unvalidated 是放行非誤拒） |
| demo side-specific positive | gates.rs:235-267（**19d**） | **無** validation / freshness / n_trades 前置；side cell 由構造恆 `validation_passed=false` | **ACTIVE**——唯一現行雙重扣成本誤拒面 |
| paper `cost_gate_paper` | gates.rs:36-57 | 有 cell 且正即比門檻 | paper 管線預設關閉（OPENCLAW_ENABLE_PAPER），非本輪重點 |

lookup provenance 乾淨：`edge_estimates.rs:355-369` `CellLookupSource::SideSpecific` 僅真 `strategy::symbol::{Buy,Sell}` cell；coarse fallback 標 `Coarse`，不會誤入 19d 分支。

## 4. Runtime 實證（PG read-only，可重跑）

```bash
ssh trade-core "psql -h 127.0.0.1 -U trading_admin -d trading_ai -Atc \"SELECT count(*), min(ts)::date, max(ts)::date FROM trading.risk_verdicts WHERE reason LIKE 'cost_gate(JS-demo): edge=%' AND ts > now() - interval '30 days';\""
# → 71207|2026-06-20|2026-07-08   （engine_mode 全部 = demo）
```

- **71,207 = charter WP-A #4 的「正 edge<threshold」母集本體**；起始日 2026-06-20 = 19d 落地（06-19）次日 → 母集由 19d 分支產生。此母集每一筆的 edge 都是**已扣成本後仍為正**的淨值。
- Modal reason：`cost_gate(JS-demo): edge=3.61bps < threshold=8.80bps (fee=4.00bps, wr=0.59)` ×49,388（ETHUSDT 合計 63,006）——fee=4.00bps=PostOnly maker 2×0.02%。
- `edge=24.90 < threshold=53.30 (fee=41.00, wr=1.00)` ×3,556（FILUSDT）——與當前 `bb_reversion::FILUSDT::Buy` cell（runtime_bps=24.8955、win_rate_shrunk=1.0、n=4）精確吻合 → side cell → 19d 分支歸因實證。
- 對照組（正確語義、非雙重扣）：同期負 edge 阻擋量遠大（單一 reason 最高 289,727 筆），threshold 家族佔 cost_gate 拒絕的少數。
- 當前 engine.log（僅 07-09T21:59 起，rotation 窗口小）0 筆 19d 命中、5 筆 side-negative——07-09 快照 cell 漂移後 19d 命中減少，但分支仍為現行代碼、30d 母集成立（max(ts)=07-08 如實記錄）。

## 5. 治理對照與修法決策（偏差聲明）

**前史（本次溯源重新發現，charter 未載）**：
- 2026-06-14 冷審計 PROFIT-1（PA plan `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-14--cold_audit_validated_fix_plan.md:54-60`）→ 2026-06-18 fix-wave **PM 裁 NO-FIX**（「雙重扣成本數學為真但 threshold-reject 路徑 dormant」）＋哨兵 `[90] check_cost_gate_double_deduct` 部署＋pre-locked fix「QC 方案 A lower-CI floor」（activation=哨兵 WARN）。見 `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-14--cold_audit_fix_wave_completion.md:14-15,43`。
- **該裁決的 dormant 前提已 stale**：19d（2026-06-19，PROFIT-RCA）把 threshold-reject 擴到永不 validated 的 side cell——71,207 筆為證。
- **哨兵盲區**：`helper_scripts/canary/healthchecks/check_cost_gate_double_deduct.py:243-247` 謂詞要求 `validation_passed is True` → 對 19d active 面（恆 false）**結構性不可見**；其 MODULE_NOTE「全部偏差方向=over-report 不漏報」（:52）自 06-19 起不再為真。

**為何本任務不改 gates.rs（charter「證實則修」的最小安全解偏差）**：
1. charter 同句硬約束「live 路徑 fail-closed 語義不得鬆動」——live 門檻是雙重扣成本公式的實例之一，任何去重複化＝量化放寬 live，禁改。
2. 唯一 active 面 = 19d 分支 = PROFIT-RCA-2026-06-19d **刻意** loss-control 邏輯（E2 過審，堵 PostOnly churn 虧損）＝charter「不動其他 gate 邏輯」範圍；且今日命中 cell 多為 n=1..5 噪音 cell（如 `bb_reversion::OPUSDT::Sell` n=2），把門檻改 net>0 會立即重開 06-19 關閉的虧損面（冷審計 PM 原話「避免一翻就放閘進負期望單」）。
3. WP-A #1-#4（本修復包**並行進行**）正是對這 71,207 母集做 pre-registered 反事實重跑 → verdict artifact → PM 裁修法。此刻單方改門檻會把重跑基線變成移動靶並 preempt QC 預註冊判準；且 2026-06-18 已存在 pre-locked 修法（方案 A lower-CI floor）待 activation 裁決。

→ 本任務交付＝語義 ground truth＋母集分支歸因（供 WP-A #3 QC 預註冊、#4 重跑裁決直接引用），gate 改碼留待 PM 依新 verdict artifact 裁決。0 行代碼改動、0 測試改動（無行為改動則無新測試對象；為現行「已知待裁」行為加特徵化測試徒增 churn，違 simplicity-first）。

## 6. 不確定之處（fact / inference / assumption 分離）

- [inference] 71,207 全數歸因 19d 分支：基於「當前快照 validated-positive=0」（fact）＋「驗證管線 DSR/Bonferroni 歷史從未通過、2026-06-18 PM 報告『runtime 0 eligible cell』」（documented）。若 06-20~07-08 間曾短暫存在 validated-positive coarse cell，少量可能來自 :351 分支——不影響雙重扣成本結論（兩分支同公式）。
- [fact] modal ETHUSDT（wr=0.59）對應的歷史 side cell 已隨 30d 滑窗漂移，無歷史快照可逐 cell 復原。
- [fact] `gates.rs:472` 注釋「aligned with Python cost_gate.py」為 stale 引用——repo 內已無 `cost_gate.py`（grep 0 hit）；僅注釋債，未動。

## 7. Operator / PM 下一步

1. WP-A #3/#4 引用本結論：重跑判準必須以「edge 已為淨值」為 baseline（門檻的 fee 份量是第二次扣除）。
2. 哨兵 `[90]` 盲區收口（謂詞擴到 side-specific 面或加獨立 check id）——alert 語義屬 policy，建議另開小票走 PA→E1→E2，不在本任務私改。
3. gate 修法裁決：pre-locked 方案 A（lower-CI floor）vs WP-A 重跑 verdict——PM 於 verdict artifact 產出後裁。
4. `gates.rs:472` stale 注釋可併入下次觸碰該檔的變更順修（不單獨開票）。

---
修改清單：無代碼改動（本報告＋E1 memory 追加 2 行）。
E1 IMPLEMENTATION DONE: 待 E2 審查（report path: docs/CCAgentWorkSpace/E1/workspace/reports/2026-07-10--profit1_cost_gate_double_deduct_tracing.md）
