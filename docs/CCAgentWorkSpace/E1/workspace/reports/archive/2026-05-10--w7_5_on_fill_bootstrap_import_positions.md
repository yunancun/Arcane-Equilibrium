# W7-5 IMPL — on_fill update self.positions + bootstrap import_positions（5 策略對齊）

**Date**: 2026-05-10
**Owner**: E1
**Status**: IMPL DONE — **NOT COMMITTED, NOT DEPLOYED**（PM 21:30 sign-off 後派 deploy）
**Scope**: PA W7-4 systemic audit §6 + W6 RFC PA-view Q2(a)/(b) — strategy-side close cold-start & fill-confirm desync gap
**Trigger**: PM 派工 prewrite W7-5 IMPL（D+0 sign-off 後直接收，不需 D+1 重設計）
**Rebase base**: W7-2 commit `22efd9de`（同 wave 一次 deploy）

---

## 0. TL;DR

兩處 trait + 5 策略 + Orchestrator + bootstrap.rs 接線改動：

- **Strategy trait**（mod.rs）：on_fill docstring 升級 + **新增 `import_positions(&PaperState)` default no-op**
- **5 策略 on_fill 實 impl**（fill confirm safety net）：
  - ma_crossover / bb_reversion：sync `self.positions.insert(symbol, intent.is_long)`
  - bb_breakout：sync `self.symbols.get_or_init(symbol).position = Some(intent.is_long)`
  - funding_arb：sync `self.positions.insert(...)` + dormant 場景 warn log
  - grid_trading：no-op + tracing::trace（W7-4 §1 LOW，inventory 由 entry path 自管）
- **5 策略 import_positions 實 impl**（cold-start desync 治本）：filter `pos.owner_strategy == self.name()` 重建 `self.positions / self.net_inventory / self.symbols`
- **Orchestrator** 加 `import_positions_for_all(&PaperState)` helper
- **bootstrap.rs:763** 在 `StrategyFactory::create_for_engine` register 之後、`grant_paper_auth` 之前單次呼叫 `pipeline.orchestrator.import_positions_for_all(&pipeline.paper_state)`

12 unit test 全 PASS（5 ma_crossover + 2 bb_reversion + 2 bb_breakout + 1 grid_trading + 2 funding_arb）。`cargo build --release --bin openclaw-engine` PASS。`cargo test --lib --release` total **2660/2660 PASS**（baseline 2648 + W7-5 12 = 2660）。

W7-3 Option B（commit `b42731f6`）+ W7-2 Option A（commit `22efd9de`）+ W7-5 三 wave 一致性 verified（ma_crossover #5 end-to-end test）。

---

## 1. 修改 file + line range

### Trait 接線（API 升級）

| 檔 | line range | 性質 | LOC |
|---|---|---|---|
| `srv/rust/openclaw_engine/src/strategies/mod.rs` | 110-135 (on_fill docstring 升級) + 137-153 (新 import_positions default no-op) | new + edit | +23 |
| `srv/rust/openclaw_engine/src/orchestrator.rs` | 55-65 (新 `import_positions_for_all` helper) | new | +11 |
| `srv/rust/openclaw_engine/src/event_consumer/bootstrap.rs` | 765-774 (register 後 import_positions_for_all 接線) | new | +11 |

### 5 策略 on_fill + import_positions impl

| 檔 | line range | 性質 | LOC |
|---|---|---|---|
| `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs` | 122-180 (on_fill + import_positions) | new | +59 |
| `srv/rust/openclaw_engine/src/strategies/bb_reversion/mod.rs` | 374-414 (on_fill + import_positions) | new | +41 |
| `srv/rust/openclaw_engine/src/strategies/bb_breakout/mod.rs` | 328-374 (on_fill + import_positions) | new | +47 |
| `srv/rust/openclaw_engine/src/strategies/grid_trading/mod.rs` | 332-378 (on_fill + import_positions) | new | +47 |
| `srv/rust/openclaw_engine/src/strategies/funding_arb.rs` | 386-446 (on_fill + import_positions) | new | +60 |

### Unit tests

| 檔 | line range | 性質 | LOC |
|---|---|---|---|
| `srv/rust/openclaw_engine/src/strategies/ma_crossover/tests.rs` | 1008-1190 (5 W7-5 test + use crate::paper_state::PaperState) | new | +183 |
| `srv/rust/openclaw_engine/src/strategies/bb_reversion/tests.rs` | 1187-1260 (2 W7-5 test + use OrderIntent + use PaperState) | new | +73 |
| `srv/rust/openclaw_engine/src/strategies/bb_breakout/tests.rs` | 1196-1259 (2 W7-5 test) | new | +63 |
| `srv/rust/openclaw_engine/src/strategies/grid_trading/tests.rs` | 916-952 (1 W7-5 test) | new | +36 |
| `srv/rust/openclaw_engine/src/strategies/funding_arb.rs` | 1122-1180 (2 W7-5 test) | new | +58 |

無動：TickContext signature（W7-1 已 land）/ router.rs Gate 1.5 / paper_state.rs / W7-3 on_rejection / W7-2 on_tick entry path。

---

## 2. 設計 design rationale

### Part 1: on_fill update self.positions（5 策略）

**callsite**: `tick_pipeline/on_tick/step_4_5_dispatch.rs:925` — 於 `paper_state.apply_fill` 之前。

**5 策略的 entry path 早已 eager mutate `self.positions`** 在 intent emit 時（ma_crossover:301 / bb_reversion:553 / bb_breakout:756 / funding_arb:493 / grid_trading signal.rs:185）— 並非「等 fill 才同步」的設計。on_fill 此處是 **fill-confirm safety net**，防 entry path 與 paper_state 在 race window（W7-3 on_rejection 改動 self.positions / W7-2 ctx.position_state 路徑改動 / 部分成交 fill 結果與 intent 偏離）的 misalignment。

| 策略 | on_fill IMPL | 邊際成本 |
|---|---|---|
| ma_crossover | `self.positions.insert(intent.symbol, intent.is_long)` + tracing::debug | O(1) |
| bb_reversion | 同 ma_crossover (PerSymbolState<bool>::insert) | O(1) |
| bb_breakout | `self.symbols.get_or_init(symbol).position = Some(intent.is_long)`（不動 entry_price/trailing_stop 避覆寫真實值） | O(1) |
| funding_arb | `self.positions.insert(symbol, FundingPosition{is_positive_funding: !is_long, entry_ms: 0})` + dormant warn | O(1) + 若 active=false 觸發 warn |
| grid_trading | **NO-OP + tracing::trace**（W7-4 §1 LOW；inventory 由 entry path signal.rs:185 自管，on_fill 不重複寫避免與 qty_per_grid 累積邏輯相撞） | O(1) trace only |

**Close 路徑不走 on_fill**（走 `on_close_confirmed` / `on_close_skipped`），故 W7-5 on_fill 只處理 Open 路徑 sync。

### Part 2: bootstrap import_positions（5 策略）

**真實 cold-start desync gap**：重啟後 `event_consumer/bootstrap.rs:308` 已從 Bybit REST snapshot 把所有倉位 import 到 paper_state（owner_strategy="bybit_sync"）；P0-6 startup triage（line 370+）會把符合 scanner active universe 的 bybit_sync 倉位歸給對應策略（owner_strategy 改為 strategy name）。**但** strategy 端 `self.positions` / `self.net_inventory` / `self.symbols` 是 `HashMap::new()` 全空。第一個 tick 進 entry path 時：
- ma_crossover/bb_reversion：`self.positions.get(symbol)` 回 None → 走 entry None 分支 → 撞 router gate 1.5 duplicate_position（paper_state 有倉但 strategy 不知）
- bb_breakout：`self.symbols.get(symbol)` 預設或回 None → 同上
- grid_trading：`net_inventory` 為空 → cross signal 計算偏差
- funding_arb：dormant，理論不發生

**W7-5 part 2 的治本路徑**：在 strategy 註冊後加一道 `import_positions(&paper_state)` 從 paper_state 重建 strategy 端 internal state。

| 策略 | import_positions 過濾條件 | 寫入 |
|---|---|---|
| ma_crossover | `pos.owner_strategy == "ma_crossover"` | `self.positions.insert(symbol, is_long)` |
| bb_reversion | `pos.owner_strategy == "bb_reversion"` | 同上 |
| bb_breakout | `pos.owner_strategy == "bb_breakout"` | `self.symbols.get_or_init(symbol).position = Some(is_long)` + `entry_price = Some(pos.entry_price)`（trailing_stop 留 None，第一個 1m tick 由 ATR 重算） |
| grid_trading | `pos.owner_strategy == "grid_trading"` | `self.net_inventory.insert(symbol, if is_long { qty } else { -qty })`（signed inventory） |
| funding_arb | `pos.owner_strategy == "funding_arb"` | `self.positions.insert(symbol, FundingPosition{is_positive_funding: !is_long, entry_ms: pos.entry_ts_ms})`（dormant 通常 0 import） |

**安全性**：`bybit_sync` / `orphan_adopted` 倉位 owner 不對應任何 strategy `name()` → 自然不被任何策略 import → **避免誤領 orphan**。P0-6 startup triage 會把符合條件的 bybit_sync 改 owner_strategy 為策略名（dispatched in dust_gate.rs / orphan_handler.rs），那之後 W7-5 import 才會撿到。

### Part 3: bootstrap.rs 接線順序

```
event_consumer/bootstrap.rs:
  line 308: pipeline.paper_state.import_positions(seed_positions)   // ← exchange snapshot 種入 paper_state
  line 351: pipeline.paper_state.set_positions_mirror(...)            // ← shared mirror
  line 370+: P0-6 triage (bybit_sync → strategy adopt OR close)       // ← owner_strategy 改寫
  line 752: dispatch::spawn_order_dispatch(...)
  line 761: for strategy in StrategyFactory::create_for_engine(kind): // ← register strategies
              pipeline.orchestrator.register(strategy)
  line 765: pipeline.orchestrator.import_positions_for_all(&pipeline.paper_state)  // ★ W7-5 NEW
  line 776: pipeline.grant_paper_auth()                                // ← auth
```

W7-5 的 import_positions_for_all 接線**在 P0-6 triage 之後**，所以 bybit_sync orphan 已被 P0-6 dispatch（adopt 或 close），剩下的 bybit_sync 倉位是 P0-6 跳過的（理論上不應發生；若發生則被 W7-5 的 owner_strategy filter 排除）。

---

## 3. Unit tests（共 12 個 W7-5 test）

### ma_crossover (5 test, tests.rs:1008-1190)

| test name | scenario | assertion |
|---|---|---|
| `test_on_fill_updates_self_positions_long` | LONG fill confirmed | self.positions[BTC] = Some(true) |
| `test_on_fill_updates_self_positions_short` | SHORT fill confirmed | self.positions[ETH] = Some(false) |
| `test_bootstrap_imports_paper_state_positions_for_ma_crossover` | paper_state 含 ma_crossover BTC LONG + grid_trading ETH SHORT + bybit_sync SOL LONG | 只 import BTC（owner filter 正確，不誤領 orphan） |
| `test_bootstrap_filters_non_eligible_symbol_for_ma_crossover` | paper_state 全是非 ma_crossover owner（4 種） | self.positions.len() = 0 |
| `test_w7_5_consistent_with_w7_3_w7_2_chain` | end-to-end: bootstrap import → on_tick (W7-2 path) reverse exit → on_fill 後新 LONG → final state 一致 | step-by-step 驗 W7-3+W7-2+W7-5 三 wave 共存無衝突，size=1 (O(1)) |

### bb_reversion (2 test, tests.rs:1187-1260)

| test name | scenario | assertion |
|---|---|---|
| `test_bbr_on_fill_updates_self_positions` | LONG fill | self.positions[BTC] = Some(true) |
| `test_bbr_bootstrap_imports_paper_state_positions` | bb_reversion BTC LONG + ma_crossover ETH | 只 import BTC |

### bb_breakout (2 test, tests.rs:1196-1259)

| test name | scenario | assertion |
|---|---|---|
| `test_bbb_on_fill_updates_per_symbol_state_position` | LONG fill | symbols[BTC].position = Some(true) |
| `test_bbb_bootstrap_imports_paper_state_positions` | bb_breakout BTC SHORT + ma_crossover ETH | 只 import BTC + entry_price 還原 |

### grid_trading (1 test, tests.rs:916-952)

| test name | scenario | assertion |
|---|---|---|
| `test_grid_bootstrap_imports_signed_inventory_from_paper_state` | grid BTC LONG 1.5 + grid ETH SHORT 2.0 + ma_crossover SOL | net_inventory[BTC]=+1.5, [ETH]=-2.0, SOL 不被 import |

### funding_arb (2 test, funding_arb.rs:1122-1180)

| test name | scenario | assertion |
|---|---|---|
| `test_funding_arb_on_fill_updates_self_positions` | SHORT fill (dormant) | positions[BTC].is_positive_funding=true（短永續收正費率對齊） |
| `test_funding_arb_bootstrap_imports_paper_state_positions` | funding_arb BTC LONG + ma_crossover ETH | 只 import BTC |

---

## 4. cargo build + test 結果

### cargo build

```
$ cd srv/rust/openclaw_engine && cargo build --release --bin openclaw-engine
    Finished `release` profile [optimized] target(s) in 22.31s
```

PASS（無 W7-5 引入 warning；既有 18 lib + 2 bin warnings 為 pre-existing dead_code 與本任務無關）。

### cargo test --lib --release -p openclaw_engine

```
test result: ok. 2660 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s
```

- baseline pre-W7-5 (W7-2 已 land at `22efd9de`) = **2648**
- W7-5 新增 = **12**（5 ma_crossover + 2 bb_reversion + 2 bb_breakout + 1 grid_trading + 2 funding_arb）
- Total = **2660 PASS**

### 局部 W7-5 spec test

```
$ cargo test --lib --release -p openclaw_engine -- "test_on_fill_updates" "test_bootstrap_imports" "test_bootstrap_filters" "test_w7_5" "test_bbr_on_fill" "test_bbr_bootstrap" "test_bbb_on_fill" "test_bbb_bootstrap" "test_grid_bootstrap" "test_funding_arb_on_fill" "test_funding_arb_bootstrap"
test result: ok. 12 passed; 0 failed
```

---

## 5. PA W7-4 §6 + W6 RFC Q2 對照

### W7-4 §6 W7-5 same-Wave optional 對照

| W7-4 §6 規格項 | 本 IMPL 對照 |
|---|---|
| 「W7-5 IMPL 任務：on_fill update self.positions（5 策略）」 | ✅ 5 策略 on_fill 實 impl（grid 是 by-design no-op 對齊 W7-4 §1 LOW） |
| 「W7-5 IMPL 任務：bootstrap import_positions（5 策略）」 | ✅ Strategy trait 加 default no-op + 5 策略 override + Orchestrator helper + bootstrap.rs 接線 |
| 「不阻 W5 IMPL，可 Sprint N+2」 | ✅ Sprint N+1 D+0 prewrite 提早完成，避 D+1 重設計 |

### W6 RFC PA-view Q2 三建議對照

| Q2 建議 | 本 IMPL 對照 |
|---|---|
| (a) on_fill() 更新 self.positions（遠端真實 fill 後） | ✅ 5 策略 on_fill 實 impl |
| (b) bootstrap 階段從 paper_state import_positions 重建 strategy.positions | ✅ Strategy::import_positions trait method + 5 策略 override + bootstrap.rs 接線 |
| (c) reject 走 RC-04 prev_position rollback（W7-3 已處理） | ✅ W7-3 Option B 補丁不動（`b42731f6`），與 W7-5 共存無衝突（test #5 end-to-end 驗證） |

---

## 6. W7-3 + W7-2 + W7-5 三 wave 一致性 verify

| Wave | commit | 觸發時機 | 修改層 |
|---|---|---|---|
| W7-3 (Option B) | `b42731f6` | router gate 1.5 reject 時（reactive） | on_rejection |
| W7-2 (Option A) | `22efd9de` | 每 tick entry path 進入時（preventive） | on_tick None 分支起點 + ctx.position_state |
| W7-5 part 1 | (本 IMPL，待 commit) | fill confirmed 後（safety net） | on_fill |
| W7-5 part 2 | (本 IMPL，待 commit) | bootstrap 啟動時（cold-start 治本） | import_positions |

**共存無衝突**：
- W7-2 在 entry None 分支起點 sync self.positions → 下 tick 走 Some 分支不撞 router gate 1.5 → W7-3 on_rejection 不會被觸發 happy path
- W7-5 part 1 (on_fill) 在 paper_state.apply_fill 之前 sync → 與 W7-2 ctx.position_state 不衝突（兩者寫值方向一致：fill direction = intent.is_long）
- W7-5 part 2 (bootstrap import) 在 strategies register 之後、第一個 tick 之前單次寫入 → 第一個 tick 進 entry path 時 self.positions 已含真實倉位，走 Some 分支（既有 exit logic）

**ma_crossover test #5 end-to-end** 已 cover 完整 chain：
1. cold-start: paper_state 已 import + ma_crossover BTC LONG 倉位
2. W7-5 part 2: import_positions → self.positions[BTC] = Some(true)
3. on_tick reverse cross: 走 Some(true) exit 分支（W7-2 None 分支不觸及）→ 1 close intent + self.positions.remove(BTC)
4. on_fill (W7-5 part 1): 新 LONG entry fill → self.positions[BTC] = Some(true)
5. final state size = 1 (O(1) chain 不洩漏)

---

## 7. 已知不確定 / E2 重點

### E2 必審

1. **W7-5 part 1 與 entry path eager mutate 的 idempotency**：5 策略 entry path 已在 `make_intent_with_qty` 後 `self.positions.insert(symbol, is_long)`；W7-5 on_fill 在 `step_4_5_dispatch.rs:925` 又做一次 `self.positions.insert(symbol, intent.is_long)`。兩次寫入方向一致時為冪等 O(1) HashMap update（無副作用）。E2 確認 race window：若 W7-3 on_rejection 在 entry path 與 on_fill 之間改動 self.positions（W7-3 Option B 對 duplicate_position sync 為 paper_state direction），on_fill 後又 sync 為 intent.is_long — 兩者方向**可能不一致**（duplicate_position 場景下 paper_state 的方向與 intent.is_long 反向）。但 router gate 1.5 拒絕的 intent 不會走到 fill confirmed 路徑（reject 後 IntentResult.fill = None），所以 on_fill 不被呼叫 → 無實際衝突。E2 必驗 reject path 不會誤呼 on_fill。

2. **bootstrap 順序契約**：W7-5 import_positions_for_all 接線在 P0-6 triage 之後（line 370+）+ register 之後（line 761）+ grant_paper_auth 之前（line 776）。P0-6 triage 把 bybit_sync owner 改寫為策略名。E2 確認順序契約**沒被任何 inserted callback / async race 打破**（特別是 `set_positions_mirror` 路徑不會反向覆寫 owner_strategy）。

3. **bb_breakout import 時 `entry_price` 還原但 `trailing_stop` 留 None**：第一個 1m tick 時 `on_tick` 內 ATR 計算會重算 trailing_stop。E2 確認重算時 `entry_price` 已存在不會被誤覆寫；以及 trailing_stop=None 不會被當作「未持倉」誤判（`bb_breakout/mod.rs` 的 stop logic 用 `position.is_some()` 而非 `trailing_stop.is_some()` 作為持倉判斷依據）。

4. **funding_arb dormant on_fill warn 路徑**：dormant 策略理論不發 intent，故 on_fill 不會被觸發；warn log 是「異常診斷」用途。E2 確認 dormant warn 不會在 production 持續刷屏（active=true 且 fill 正常時無 warn）。

### 不確定（請 E2 / E4 確認）

- **import_positions 對 P0-6 triage 已處理過的 bybit_sync 殘留**：理論上 P0-6 已 dispatch（adopt → owner_strategy 改寫 / close → 移除）；若殘留 bybit_sync owner_strategy 倉位，W7-5 owner filter 會 skip（safe）。E4 deploy 後可觀察首次重啟 log 確認 import_positions counter 與 P0-6 triage counter 對齊。
- **跨重啟 entry_ms 還原**：funding_arb 的 import_positions 用 `pos.entry_ts_ms`；ma_crossover/bb_reversion 不重建 cooldown / persistence（W7-5 scope 限縮在 self.positions）。E2 確認重啟後第一個 tick 對 cooldown 的影響：cooldown 用 `last_ms.unwrap_or(0)` → 未見 = 已冷卻，符合預期。
- **bb_breakout 重啟後 trailing_stop 重置 vs 持倉**：trailing_stop=None + position=Some 場景需 ATR 計算；若首個 tick 沒 ATR snapshot，trailing 邏輯可能跳過。E4 deploy 後可觀察重啟首 5min trailing_stop 重建 log。

---

## 8. 邊界對齊（task spec 對照）

| Task spec 項 | 對照 |
|---|---|
| 不動 TickContext signature（W7-1 已 land） | ✅ 不動 |
| 不動 router.rs Gate 1.5 邏輯 | ✅ 不動 |
| 不動 W7-3 on_rejection 邏輯 | ✅ ma_crossover/strategy_impl.rs:55-112 不動 |
| 不動 W7-2 on_tick entry path 邏輯 | ✅ ma_crossover/strategy_impl.rs:188-211 + bb_reversion/mod.rs:449-471 不動 |
| 不動 paper_state.rs（read-only borrow only） | ✅ 只用既有 `paper_state.positions()` 公共 API |
| Rebase on W7-2 commit `22efd9de` | ✅ git pull 確認 base = 22efd9de（W7-2 + W4 IMPL pre-write） |
| 不 deploy | ✅ NOT COMMITTED, NOT DEPLOYED |
| ssh trade-core 不需要 | ✅ 純 Mac cargo build/test |

---

## 9. NOT COMMITTED, NOT DEPLOYED 標記

按 PM 派工：
- **NOT COMMITTED**：本 IMPL 改動仍 local (uncommitted)；commit 留 PM 21:30 sign-off 後
- **NOT DEPLOYED**：未 push、未 ssh trade-core、未 restart_all
- 待 D+0 sign-off 後同 W7-1 + W7-3 + W7-2 + W7-5 同 wave 一次 `restart_all --rebuild --keep-auth` 部署到 Linux trade-core

---

## 10. Operator 下一步

1. **PM sign-off W7-5 IMPL**（21:30 UTC 窗口內）— 對照本 report §5 PA W7-4 + W6 RFC Q2 規格項，確認 12 test 全 PASS、cargo build 綠、無 regression
2. **派 E2 review**（per CLAUDE.md §八 強制 E1→E2 chain）— 重點 §7 四點
3. **派 E4 regression**（per CLAUDE.md §八 強制 E2→E4 chain）— 跑 5 策略 subset + 全 lib test 確認 baseline + 12 = 2660 PASS
4. **D+0 21:30 後**：commit W7-5 + W7-2 + W7-1 + W7-3 + W2 trait skeleton 同 wave 一次 deploy 到 Linux trade-core（per dispatch v3.7 Sprint N+1 D+0）
5. **D+1 起**：W7-5 land 後 24h passive watch：
   - INXUSDT 重啟後第一個 tick 是否仍撞 router gate 1.5 duplicate_position（預期：W7-5 part 2 cold-start 治本，第一個 tick self.positions 已 sync → 不撞）
   - 5 策略 import_positions log 體量確認與 P0-6 triage 對齊
   - bb_breakout trailing_stop 重啟首 5min 重建 log 確認 ATR-aware 重算

---

## Evidence Files

- 本 report：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_5_on_fill_bootstrap_import_positions.md`
- PA W7-4 systemic audit：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w7_4_systemic_position_sync_audit.md`
- W7-2 IMPL report：`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_2_ma_crossover_bb_reversion_entry_path_query.md`
- W7-1 trait skeleton commit（已 land NOT DEPLOYED）：`c9fb0b8f`
- W7-3 Option B commit（已 land NOT DEPLOYED）：`b42731f6`
- W7-2 Option A commit（已 land NOT DEPLOYED）：`22efd9de`（base）
- 修改檔（uncommitted）：
  - `srv/rust/openclaw_engine/src/strategies/mod.rs:110-153`
  - `srv/rust/openclaw_engine/src/orchestrator.rs:55-65`
  - `srv/rust/openclaw_engine/src/event_consumer/bootstrap.rs:765-774`
  - `srv/rust/openclaw_engine/src/strategies/ma_crossover/strategy_impl.rs:122-180`
  - `srv/rust/openclaw_engine/src/strategies/bb_reversion/mod.rs:374-414`
  - `srv/rust/openclaw_engine/src/strategies/bb_breakout/mod.rs:328-374`
  - `srv/rust/openclaw_engine/src/strategies/grid_trading/mod.rs:332-378`
  - `srv/rust/openclaw_engine/src/strategies/funding_arb.rs:386-446`
  - 5 tests file 共 +413 LOC

---

E1 IMPLEMENTATION DONE: 待 E2 審查 + E4 regression（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w7_5_on_fill_bootstrap_import_positions.md）
