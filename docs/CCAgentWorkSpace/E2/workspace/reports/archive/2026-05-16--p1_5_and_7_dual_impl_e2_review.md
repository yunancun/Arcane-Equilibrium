# E2 adversarial review — P1 #5 F-09 model_tier + P1 #7 [68] portfolio resting healthcheck

- 日期：2026-05-16
- 角色：E2（senior backend code reviewer + adversarial auditor）
- 範圍：兩個 P1 IMPL DONE 並行 review；read-only。
- E1 sign-off：
  - F-09：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--f09_model_tier_toml_extraction.md`
  - healthcheck [68]：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-16--healthcheck_58_portfolio_resting_exposure.md`

---

## 1. F-09 model_tier TOML extraction — **APPROVE**

### 8 條 §九 + 9 條 OpenClaw checklist
- 改動 scope tight，與 PA 一致；7 files / 308 LOC / 0 unrelated diff。
- `except: pass` 0 命中（純 Rust）。
- 跨平台 grep：F-09 區段 0 命中 `/home/ncyu` / `/Users/[^/]+`。
- 雙語注釋：default to 中文（CLAUDE.md §七 2026-05-05 governance），舊 STRATEGIST-TUNE-TARGET-CONFIG-1 bilingual block 保留未動 — 合規。
- Migration Guard / healthcheck / 私有屬性穿透 / async-blocking — N/A。
- 文件大小：`risk_config_advanced.rs` 1300 / `evaluate.rs` 537 / `mod.rs` 495 — 全 < 2000 hard cap，全 < 800 warning。
- Singleton：`StrategistConfig` 在既有 `RiskConfig` Arc<ArcSwap> 下，不需新登記。
- cargo check：Mac `aarch64-apple-darwin --lib` PASS（0 新 warning，2 pre-existing dead_code 與 F-09 無關）。

### 對抗驗證（重點 6 項）
1. **ArcSwap snapshot path 與 race**：`current_model_tier()` 與 `current_max_param_delta_pct()` **100% 對稱** — `risk_store.as_ref().map(|s| s.load().strategist.<field>).unwrap_or(default)`。`store.load()` 是 ArcSwap 無鎖讀取，每次 IPC `patch_risk_config` `ArcSwap::store(new)` 後下一次 `load()` 立即見新值；hot-reload 無 race。
2. **三層 fallback 安全**：
   - 缺 store（測試 / 啟動瞬間）→ `unwrap_or(DEFAULT_STRATEGIST_MODEL_TIER)` = `"l1_9b"`
   - 缺 `[strategist]` section → `#[serde(default = "default_strategist_model_tier")]` = `"l1_9b"`（test `_partial_fallback` 覆蓋）
   - 缺欄位 / 純空 → `validate()` 早期失敗（test `_rejects_empty_or_whitespace_model_tier` 覆蓋）
3. **Backward compat**：實測 `risk_config_{paper,demo,live}.toml` 三檔都新增 `model_tier = "l1_9b"`；既有 partial TOML（無 `[strategist]` 或 section 內無 model_tier）皆走 `#[serde(default)]` 兜底，0 行為差。
4. **Lexical scope shadow (W-AUDIT-7c 教訓)**：`evaluate.rs:154-164` 加 `let model_tier = self.current_model_tier();` — 此名稱在 `evaluate_cycle` scope 內無前綴 shadow（既有 `let max_delta_pct` 採同 pattern）。`build_strategist_eval_payload` signature 加 `model_tier: &str` — caller 顯式傳，無默認回填覆寫風險（test `_honors_custom_model_tier` 顯式驗 caller 傳 `"l1_27b"` 必鏡像）。
5. **注釋默認中文**：F-09 新增 doc block 全中文；舊 STRATEGIST 區段保留 bilingual — 對齊 2026-05-05 governance「修改既有對照塊移除英文」**未觸發**因 F-09 沒動到舊 bilingual block。合規。
6. **hot path 邏輯 0 改動**：`evaluate.rs:412` 周邊 IPC dispatch / verdict shape / param validation / decision-lease 路徑全部不變；F-09 只在 `build_payload` 加一個字串欄位來源切換。

**取捨可接受**：
- `validate()` 不綁 enum：E1 sign-off §6.3 明列 trade-off；保留 P2-F-09b dynamic routing 設計空間。寬鬆 validate + 大小寫敏感 = Python `_handle_strategist` `params.get("model_tier", "l1_9b")` 拿不到 match 會落 default — 即 typo 不 panic 但會 silent fallback 到 9B。**E4 應做端到端 dispatch test 驗證**（E1 自己也指出，§6 不確定之處 #1）— 屬 E4 回歸範圍，不阻 E2 PASS。
- Python 端 `params.get("model_tier", "l1_9b")` default 保留 = dead code path 兜底保險絲。E1 選擇不清，可接受。

**verdict：APPROVE**（無必修，E4 補跑 Python `_handle_strategist` IPC dispatch + 真實 Ollama tier 字串等值即可進入 PM commit。）

---

## 2. P1 [68] portfolio resting exposure healthcheck — **APPROVE-CONDITIONAL**

### 10 條 review 點
1. **SQL injection / parameterization**：✅ CRITICAL safe。`_resting_notional_from_pg` 兩條 query 全用 `%s` placeholder + tuple params（`(lookback_hours, engine, lookback_hours)`），engine 字串雖來自 const `ENGINE_MODES`（hardcoded 4 值）非外部輸入，但仍走 driver-side bind，無 f-string concat。`to_regclass()` 預檢用純字面 query — OK。
2. **Per-engine race / connection pool**：✅ safe。`runner.py` main loop 用**單一 conn + 單一 cur** serial 跑所有 check；本 check 內部 4-engine loop 在同一 cur，**無並發**。defensive `cur.connection.rollback()` 在 check 開頭與 sibling `[55]/[57]/[58]/[67]` 對齊 — cursor 在 sibling 間乾淨。
3. **Env naming**：✅ `OPENCLAW_PORTFOLIO_RESTING_HEALTH_REQUIRED` / `OPENCLAW_PORTFOLIO_RESTING_LOOKBACK_HOURS` 與既有 `OPENCLAW_AGENT_SPINE_HEALTH_REQUIRED` / `OPENCLAW_H0_BLOCK_HEALTH_REQUIRED` / `OPENCLAW_LIVE_PIPELINE_HEALTH_REQUIRED` 命名 pattern 完全對齊。
4. **Threshold logic 邊界**：✅ 設計合理。PASS 用嚴格 `<` / WARN 用 `>=` lower bound `<` upper bound / FAIL 用 `>=` upper bound，無 off-by-one 漏網。`divergence_pct = total_resting / max(total_filled, 1.0)` — `total_filled=0` 時 `max(0, 1)=1` 避免除零，但這也意味 resting=10 + filled=0 時 divergence=10.0=1000% 強行觸 FAIL。**取捨 OK**：resting-only 路徑另有 `r_total >= 0.5 × cap` 觸 FAIL，雙覆蓋。`max(_, 1.0)` 不會 mask resting-only 路徑因為 `0.5 × cap` 比較是絕對值不是 ratio。
5. **10 unit test 強度**：✅ 邊界覆蓋足。三 fixture（PASS / WARN / FAIL）+ 7 edge（snapshot 缺 / 表缺 / no Working / REQUIRED env / resting-only / short side 80% boundary / malformed snapshot）。**warning**：缺顯式 fixture 「aggregate ≥ cap 直接 FAIL」測試（E1 自承 §4.2「logic verified by code review」）— 但 `test_fixture_3` 的 r/f=1.67 同時觸 divergence-FAIL + per_symbol-FAIL，邏輯線已通。LOW，不阻 PASS。
6. **Test mock PG vs real semantics**：⚠️ mock 假設 `trading.orders` schema 含 `(symbol, side, qty, price, engine_mode, ts)` + `trading.order_state_changes` 含 `(order_id, to_status, ts)` + 兩表都接受 lookback ts filter。**E1 自承（§6.3 #1）E4 必驗真實 PG schema** — mock 只能驗 logic 不能驗 schema 對齊；per 2026-05-05 `feedback_v_migration_pg_dry_run` 規則 = 強制 Linux PG dry-run。E4 回歸前 reviewer mandate；不阻 E2 PASS。
7. **跨檔 lexical / circular import**：✅ `runner.py` import 從 `.checks_portfolio_resting_exposure` 區段；`__init__.py` re-export 加在既存 list 尾。Python `import` 已實測通過（`from helper_scripts.db.passive_wait_healthcheck import check_68_portfolio_resting_exposure` 成功）。無 circular。
8. **236 sibling regression**：✅ 0 fail。本 check 純 add — runner 入口加在最尾，前面 sibling 不受影響。
9. **CLAUDE.md §七 跨平台 + 注釋**：✅ grep `/home/ncyu` / `/Users/[^/]+` 0 命中；`OPENCLAW_DATA_DIR` env fallback + `OPENCLAW_BASE_DIR` env fallback 對齊 Mac/Linux 雙端。注釋全中文（per 2026-05-05 governance）。
10. **§九 文件大小**：✅ 562 + 408 + runner +43 + `__init__` +14 — 全 < 800 warning（562 / 408），全 < 2000 hard cap。

### 對抗反問
- **「`pipeline_kind.db_mode()` 只回 paper/demo/live — `live_demo` snapshot 路徑你怎麼處理？」** 驗 `event_consumer/bootstrap.rs:901` — 確認 `kind_tag = pipeline.pipeline_kind.db_mode()` 只回三字串，**LiveDemo runtime 寫的也是 `pipeline_snapshot_live.json`**。E1 IMPL 把 live + live_demo 都 map 到 `pipeline_snapshot_live.json`（`ENGINE_TO_SNAPSHOT` line 86-87）— 正確。但下一層問題 ↓
- **「live + live_demo 同 paper_state snapshot，filled positions 會雙計嗎？」** 是的，**LOW 風險**：當 LiveDemo runtime 跑（`OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow` 當前狀態），`engine_mode='live'` 跑會拿 `pipeline_snapshot_live.json` 的 filled vs PG `WHERE engine_mode='live'`（當前為 0 row），`engine_mode='live_demo'` 跑會拿同一 snapshot 的 filled vs PG `WHERE engine_mode='live_demo'`。當前 Mainnet 未啟動 = `live` engine 永遠 resting=0 → PASS；**未來 Mainnet 啟動後**，live + live_demo 同時有 filled，這個 snapshot 共讀會把 live 的 filled positions 也算進 live_demo 的 effective notional（反之亦然）→ 雙計、verdict 過於保守（更易觸 WARN/FAIL）。**FA 視角**：保守 verdict bias 是 acceptable for Stage 1 demo lineage monitoring，不傷正確性方向；但建議 future enhancement 加注釋說明 snapshot 共讀代價。
- **「Fallback cap_pct=65 對 paper(80%)/live(40%) 環境語意錯誤？」** 確認三 TOML 都有 `correlated_exposure_max_pct`（paper=80 / demo=65 / live=40）；fallback 只在三檔都缺時觸發 — 當前 0 觸發路徑。但 `FALLBACK_CORRELATED_CAP_PCT = 65.0` 註解寫「對齊 demo」— 對 live 環境 fallback 會「比實際 cap 寬鬆 25%」，**LOW**。若 TOML 真缺失，建議按 engine 用不同 fallback（live=40, paper=80）；或乾脆 FAIL 帶診斷不 fallback。

### Findings

| 嚴重性 | 位置 | 描述 | 建議 |
|---|---|---|---|
| LOW | checks_portfolio_resting_exposure.py:118 | `FALLBACK_CORRELATED_CAP_PCT = 65.0` 不分 engine — live fallback 比實際 40% cap 鬆 25%；當前三 TOML 都有 cap 不觸發，但 future TOML drift 風險 | 改為 `ENGINE_TO_FALLBACK_CAP_PCT = {"paper": 80.0, "demo": 65.0, "live": 40.0, "live_demo": 65.0}` dict；不阻 commit |
| LOW | checks_portfolio_resting_exposure.py:80-88 | live + live_demo 共讀 `pipeline_snapshot_live.json` filled positions — 未來 Mainnet 啟動後可能 double-count filled 於兩 engine verdict | 加注釋說明共讀代價；future enhancement 區分（需 Rust 側 LiveDemo 寫獨立 snapshot 才能根治）；不阻 commit |
| LOW | runner.py docstring (line 491) | 自寫 invariant 清單把 `[68]` 加進「post-cursor」位 — 但實際 `check_68_*` 是在 cursor 上下文跑（line 1130 `with conn.cursor() as cur:`內）。應在 cursor 區 | docstring fix only，不影響執行 |

### verdict：**APPROVE-CONDITIONAL**

- E2 條件 PASS。3 個 LOW 不阻 PM commit；建議 PM commit 同 batch 加 LOW-1 fallback dict 一行修，LOW-2/3 留到 follow-up。
- 強制：**E4 必走 Linux PG dry-run**（per `feedback_v_migration_pg_dry_run`）— 驗 `trading.orders.engine_mode` 真實 enum、`order_state_changes` 真實 ts column / DISTINCT ON index hit、snapshot path resolve。E4 GREEN 才進 PM commit。

---

## 3. ID 衝突 final 建議：**採用 `[68]`**

- 既有 `[58]` = W-AUDIT-9 T4 `check_58_graduated_canary_stage_invariant`（runner.py line 1071 region，2026-05-09 land）— 確認占用。
- 既有 `[58a]` = W5-E1-A `check_58a_stage_criteria_eval`（runner.py 同檔，2026-05-10 land）— **`[58a]` 也已占用**。
- E1 取 `[68]` — runner free slot list `[59]-[67]` 已連續，`[68]` 是下一 free index — **無新衝突**。
- E1 提的「`[58b]` 或 `[58c]`」會破壞 ID 數字單調 + 與 sibling check `[57]/[58]/[58a]/[59]/[64]/[65]/[66]/[67]` 命名一致性；**[68] 是正確選擇**。
- W-AUDIT-9 T4 既得 `[58]` 不應強搶。

**建議 PM 採用 `[68]`，不退回 E1 改名。**

---

## 4. 新引入 issue（順帶發現，不阻 commit）

- runner.py:491 docstring 把 `[68]` 列在 invariant 清單 cursor 區 line 491 `[42][42b]...[57][58][58a][59][64][65][66][67][68]` — 正確；但 line 491 是 cursor 行，無錯。**clean.**
- 三 TOML doc block（paper/demo/live）有重複的「F-09：model_tier 抽至 TOML，operator 熱切 9B / 27B / L1.5 不需 rebuild。」一句出現兩次（一次中英對照舊 block 下，一次補新 doc tail）— **LOW redundancy**，不阻。

---

## 5. Commit go/no-go

| IMPL | Verdict | PM commit | 條件 |
|---|---|---|---|
| F-09 model_tier | **APPROVE** | ✅ 可進 PM commit + push | 0 必修。E4 補 Python dispatch 端 IPC test 屬 follow-up，不阻。 |
| [68] healthcheck | **APPROVE-CONDITIONAL** | ✅ 可進 PM commit + push（建議 batch 加 LOW-1 dict 修） | **E4 必跑 Linux PG dry-run**（trading.orders schema / engine_mode enum / DISTINCT ON index）+ 真實 cron fire 驗 fail-soft 走通；E4 GREEN 才合入 main。 |

---

**E2 REVIEW DONE: APPROVE (F-09) + APPROVE-CONDITIONAL ([68])** · report: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-16--p1_5_and_7_dual_impl_e2_review.md`
