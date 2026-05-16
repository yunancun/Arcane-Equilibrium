# E2 對抗審核 — P1-WP03-DEPLOY-GATE-IMPL · 2026-05-16

## 改動範圍
- 新檔 `helper_scripts/db/passive_wait_healthcheck/checks_wp03_deploy_gate.py` 587 LOC（主檔 + 7 helper + check_69）
- 新檔 `helper_scripts/db/test_wp03_deploy_gate_healthcheck.py` 528 LOC, 17 PASS
- `helper_scripts/db/passive_wait_healthcheck/__init__.py` +13 LOC re-export
- `helper_scripts/db/passive_wait_healthcheck/runner.py` +51 LOC wire `[69]`
- 0 業務代碼動到（grid_helpers.rs / mlde writer / risk_config / live auth / lease 0 hit）

## §九 8 條 checklist
| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | ✅ |
| 沒有 except:pass 或靜默吞異常 | ✅（fail-soft 都有 diag 記錄 + 返回 WARN/PASS，不靜默） |
| 日誌使用 %s 格式 | N/A（純 SQL 端 `%s` 參數化；無 logger.info 呼叫，全 verdict msg 經 return 給 runner） |
| 新 API 端點 _require_operator_role() | N/A（純 healthcheck） |
| except HTTPException: raise 在 except Exception 之前 | N/A |
| detail=str(e) 已改為 "Internal server error" | N/A |
| asyncio blocking threading.Lock | ✅ 同步 healthcheck 路徑無 asyncio |
| 私有屬性穿透 ._xxx | ✅ 無；module 內部 `_helper()` private function 是合理慣例 |

## OpenClaw 9 條
| Item | 狀態 |
|---|---|
| 跨平台 grep `/home/ncyu` `/Users/[^/]+/` | ✅ 0 命中 |
| 雙語注釋 | ✅ 中文 default per 2026-05-05 governance；MODULE_NOTE 完整 |
| Rust unsafe / unwrap | N/A 純 Python |
| 跨語言 IPC schema | N/A |
| Migration Guard A/B/C | N/A（無新 SQL migration；複用 V031 既有表）|
| healthcheck 配對 | ✅ 本檔本身就是 [69] healthcheck，配對 cron 既有 entry，per CLAUDE.md §七 強制 |
| Singleton 登記 §九 | N/A 純 function module 無新 singleton |
| 文件大小 800/2000 行 | ✅ 587 / 2000；test 528 / 2000 |
| Bybit API 字典 | N/A 純 PG / FS |

## 對抗反問

**Q1：SQL injection check 結果？**
**A**：✅ 全參數化。
- 3 處 `cur.execute()`：
  - L444 `to_regclass(...) IS NOT NULL` — 純常量字串，無外部輸入
  - L250 `_query_grid_window` — `(%s::text)::interval` 參數化，傳 `"12 hours"` / `"24 hours"` / `"7 days"`，傳的字串源自 hardcoded `f"{int(hours)} hours"` 經 `int()` cast，無 user input 注入面
  - L316 `_load_or_compute_baseline` — `%s::timestamptz` × 2 參數化，傳 `WP03_BASELINE_START_UTC` / `WP03_BASELINE_END_UTC` 常量
- E1 自承 #2 `(%s::text)::interval` cast — 我交叉看 [40] L1162 是 hardcoded `interval '24 hours'` 全字面，與 [40] 的 L157 `_query_kpis` 同檔 `(%s::int || ' minutes')::interval` 已有 cast 先例 — 語義一致。E4 應在 Linux PG 驗實際 cast plan 一致

**Q2：Threshold logic correctness？**
**A**：✅ 對。
- T1 `t1["avg_net_bps"] < T1_AVG_NET_FLOOR_BPS`（-10）+ `n >= 30`：嚴格 < 不含邊界，per PA spec §4.1 `< -10.0`
- T2 `< -5.0` + `n >= 50`：同
- T3 `< (baseline.avg - 3.0)` + `n >= 200`：spec §4.1 「`< (baseline_avg_net_bps_grid_14d - 3.0)`」對齊
- WARN approach floor T1 = `-10 × 0.8 = -8`；T2 = `-4`；T3 = `baseline - 2.4` — 三個方向都是「比 trigger floor 更接近 0 / baseline」**符合語意**（avg 比 trigger 嚴重 → trigger；比 trigger 輕但比 approach 嚴 → WARN）
- 邊界 case：avg = trigger floor 正好（即 `-10.0`）→ 不觸發（< 嚴格），不算 off-by-one；avg = approach floor 正好（即 `-8.0`）也不觸發 WARN — **這是 acceptable conservative bias**

**Q3：Baseline + cache file 安全評估？**
**A**：✅ 設計合理。
- Baseline window 寫 module-level 常量 `WP03_BASELINE_START_UTC` / `WP03_BASELINE_END_UTC`，非從 PG 動態 query — **per spec §12 R1 mitigation 明確 lock 5-day post-V083 window**，避 V083 transition contamination
- First-run 走 `_load_or_compute_baseline` 從 PG query baseline window stats → persist 至 `$OPENCLAW_DATA_DIR/wp03_baseline_cache.json`，後續 cron reuse — `$OPENCLAW_DATA_DIR` 走 env override fallback `/tmp/openclaw`，跨 Mac/Linux 一致
- PG empty fallback：`n < BASELINE_MIN_SAMPLE (30)` → 回 `(None, "樣本不足")` → main check 返 WARN 「baseline compute failed」**不寫 cache**（避免 contaminate cache 樣本不足的結果）→ 下次 cron 重 query；**正確 fail-soft**
- Cache schema 含 `window_start / window_end / window_label / computed_at`，operator 強制重算只需 `rm wp03_baseline_cache.json`

**Q4：Revert flag design 爭議 (E1 vs PA spec)？**
**A**：E1 設計 acceptable，但 message 有 minor confuse 可改善（**LOW-1**）。
- PA spec §4.3 「任一 T1/T2/T3/ZERO_FILLS 觸發 → revert flag SET」明確 — E1 IMPL hard trigger 寫 flag ✅ 對齊
- E1 自承 #5「approach + REQUIRED env → FAIL 不寫 flag」— 本 IMPL `_status_for(required, "WARN") == "FAIL"` 升級時不 hit `_write_revert_flag`，符合「approach 是趨勢警告非 hard trigger」semantic
- PA spec **沒明說** approach 升 FAIL 寫不寫 flag — E1 設計 = approach FAIL 是 verdict escalation strict mode，不影響 advisory action — **合 §11 原則 5 生存 > 利潤 + 11 Agent 最大自主**（不過度 advisory）
- **但** Step 4 FAIL msg 已含 `revert_recommended=true` 字串，Step 5 REQUIRED escalation FAIL msg 無此字串 — operator GUI/alert 路徑若 grep `revert_recommended=true` 判 flag，逻辑正確；若 grep 整 FAIL line 判 flag，會 false expect file exists
- **MINOR push back**：E1 在 REQUIRED escalation FAIL msg 應 explicit 加 `revert_recommended=false (approach_escalation)` 或 `flag_not_written` hint，方便 operator / GUI 區分（per E1 自承 7.3 #6 也提到此疑慮）
- **裁定**：APPROVE-CONDITIONAL — 不阻塞，但 P2 ticket / minor msg 強化建議 land

**Q5：Lexical scope shadow（W-AUDIT-7c 教訓）？**
**A**：✅ 無。
- 587 LOC + 51 LOC runner.py wire — module-level 常量 + 7 helper + 1 main check，全 explicit name；無 var rebinding / no closure capture
- runner.py L286-305 import block 與既有 [40] / [68] 同 pattern；無 import shadow（`check_69_wp03_ou_sigma_deploy_gate` 全 unique，0 既有 symbol）
- test 用 `unittest.mock.patch` + `_FakeDT` subclass — `datetime` import 在 module 頂 + test patch 路徑 explicit `helper_scripts.db.passive_wait_healthcheck.checks_wp03_deploy_gate.datetime` 正確（不會誤 patch global datetime）
- `node --check` GUI sign-off SOP N/A（純 Python，無 JS / inline-JS）

**Q6：Env vars naming 對齊？**
**A**：✅ 可接受。
- `OPENCLAW_WP03_DEPLOY_GATE_REQUIRED` / `OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS` — 對齊 [68] `OPENCLAW_PORTFOLIO_RESTING_LOOKBACK_HOURS` + [52] `OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED` 既有 `<TOPIC>_<...>_REQUIRED` / `<TOPIC>_LOOKBACK_HOURS` pattern
- 雖然不同 prefix 結尾（DEPLOY_GATE vs PORTFOLIO_RESTING_HEALTH）但仍是 `<scope>_REQUIRED`，合 OpenClaw env naming 慣例

**Q7：Mock review verdict？**
**A**：✅ 真實 PG semantic 對齊，無嚴重 mock-hide。
- mock cursor `fetchone.side_effect = [...]` 模擬 3-tuple `(n, avg, std)` — 與 [40] L1168 `total, wins, avg_net = cur.fetchone()` 既有 PG return shape 對齊（[40] 是 `(int, int, float8)`，本 IMPL `(int, float8, float8)` — N/AVG/STDDEV — 都是 PG `COUNT/AVG/STDDEV` aggregate 標準 return）
- baseline query mock 用 `(n, avg, std)` 3-tuple — 但 L332-335 `row[0] / row[1] / row[2]` 索引讀取 + `n_raw or 0` / `avg_raw or 0.0` / `std_raw or 0.0` None-safe — Mac 端假設與真 PG 一致
- ZERO_FILLS path 用 `(0, None, None)` mock — `_query_grid_window` 中 `int(n or 0)` / `float(avg or 0.0)` / `float(std or 0.0)` 處理 None — 對 PG `AVG(NULL) = NULL` 真實行為兼容（E4 Linux 驗 confirm）

**Q8：17 test 強度？**
**A**：✅ 邊界覆蓋足；非 trivial pass。
- PASS / WARN×3 window approach / FAIL T1/T2/T3/ZERO_FILLS + 3 PASS-skip path + table absent + baseline insufficient + low_sample skip + REQUIRED escalation + LOOKBACK env override + cache reuse = 17 條全打到 spec acceptance §6.1/§6.2/§4.1
- ZERO_FILLS test 用 `_FakeDT` 過去寫法繞 wall-clock dependence — sound（無 sleep / 無 real time）
- Cache reuse test 用 4 fetchone（不含 baseline query）證明 cache hot path 真不打 PG — 真實 functional test 非 mock pass
- 個別 fixture 各自 assert 具體 `severity` / `flag JSON.wp03_commit` / `msg contain` — 不是 `assertIsNone` 寬鬆

**Q9：ADR-0020 honored 驗證？**
**A**：✅ 真實 advisory only。
- `_write_revert_flag` 純 `flag_path.write_text(json.dumps(...))` filesystem write，無 IPC / subprocess.Popen / no `os.kill` / no git revert / no engine restart 呼叫
- Flag JSON 含 `severity / triggers / baseline / wp03_commit / deploy_ts` — 完整 audit trail
- Operator 看 flag 後 manual action（path A TOML flip / path B git revert）per spec §5.3 decision matrix — IMPL 不觸發任何自動

**Q10：跨檔 runner.py wire 安全性？**
**A**：✅ 無破壞。
- runner.py 既有 [40]/[68] 等 wire pattern 都是 `s, m = check_X(cur); results.append((label, s, m))` 順序 append；[69] 接 [68] 後 L1204-1205 同 pattern
- `_RUNNER_DESCRIPTION` doc 補 `[69]` 完整描述
- import order：__init__.py L192-201 + L291-294 `__all__` — 一致；無 circular import（pure helper module 0 上游 dep）

## Findings 

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| **MEDIUM-1** | `checks_wp03_deploy_gate.py:514` | **ZERO_FILLS 條件用 hardcoded `T2_WINDOW_HOURS_DEFAULT (24)` 但 t2 query 用 env override `t2_window_hours`** — 當 `LOOKBACK_HOURS=48`, age=30h, T1 12h 有 fills, T2 48h n=0（因 age<48），會 false-positive 觸 ZERO_FILLS + 寫 revert flag。實測重現：t1=50/+5bps active，T2 0 fills 純粹 query window > engine age，IMPL 仍 report `48h grid_trading n=0 dormancy` → 寫 flag | (a) 把 L514 改 `if age_h >= t2_window_hours and t2["n"] == 0` — t2 window 與 age 對齊；(b) 或加 secondary guard `t1["n"] == 0`（如 12h 也 0 fills 才算真 dormancy）；(c) 或 ZERO_FILLS 只在 default 24h 不被 override 時 trigger（`os.getenv("OPENCLAW_WP03_DEPLOY_GATE_LOOKBACK_HOURS")` 未設才檢測）|
| **LOW-1** | `checks_wp03_deploy_gate.py:572-576` | REQUIRED escalation FAIL msg 無 `revert_recommended=...` hint — operator 看到 FAIL 但找不到 `wp03_revert_flag` 檔會困惑（per E1 自承 7.3 #6）。Step 4 hard FAIL msg 已含 `revert_recommended=true` | 在 L573 FAIL msg 加 `revert_recommended=false (approach_escalation, no flag written)` |
| **LOW-2** | `checks_wp03_deploy_gate.py:531-540` | hard FAIL msg 中 `revert_recommended=true` 是 msg substring 但無 structural marker，GUI / alert downstream 若 regex parse 易斷裂；妥當為 emit JSON-friendly hint | （optional）msg 末加 `flag_path={path}` 已有；可加 `[FLAG_SET]` 結構化 prefix 給 alert grep |
| **LOW-3** | `checks_wp03_deploy_gate.py:391-392` | `_write_revert_flag` fail-soft 寫失敗回 `"flag write failed: ..."`，但 verdict 仍 FAIL — operator 看到 FAIL + `flag written failed` 雙重訊息會誤判 advisory 是否 active | 可接受（fail-soft 設計合理）；建議補 P2 alert 邏輯不依賴 flag file 存在性，改 grep msg substring |
| **WATCH** | concurrent flag write race | 8 thread 並行測試證明 last-writer-wins 無 corrupt，但 atomic tmp+rename pattern 更穩 — 跨 cron / manual operator run 同時刻機率低 | 接受；P2 ticket 視需要 land atomic write |

## E1 5 verification points 評估

| # | E1 claim | E2 verdict |
|---|---|---|
| 1 | `learning.mlde_edge_training_rows` 3-tuple n/avg/std PG schema | ✅ 與 [40] L1162-1168 同表 + 同 COUNT/AVG/STDDEV pattern，schema 對齊；E4 Linux PG verify 是 SOP，不阻塞 |
| 2 | `(%s::text)::interval` cast | ✅ 與 [40] L157 `(%s::int || ' minutes')::interval` 同檔內既有 cast pattern；PG `'12 hours'::text::interval` 是 documented behavior；E4 Linux verify 是 SOP |
| 3 | `engine_pid` mtime after v35 rebuild | ✅ CLAUDE.md §三 寫 2026-05-16 01:00 UTC rebuild PID 69581，per restart_all.sh 一定 touch engine_pid；E4 Linux ls verify 是 SOP |
| 4 | First-run cache persist | ✅ `_data_dir() / "wp03_baseline_cache.json"` 用 `cache_path.parent.mkdir(parents=True, exist_ok=True)` + `write_text(json.dumps)` Linux safe |
| 5 | Approach + REQUIRED env → FAIL does NOT write flag | ✅ 設計合理（per Q4）；建議 LOW-1 msg 強化提示 |

## Verdict

**RETURN to E1**（1 MEDIUM 強制修 + 3 LOW 建議修；MEDIUM-1 是真實邊界 bug 可造成 false-positive revert flag write）。

### 必修
1. **MEDIUM-1**：ZERO_FILLS 邊界 — `checks_wp03_deploy_gate.py:514` 改 `age_h >= t2_window_hours and t2["n"] == 0`，或加 t1["n"]==0 secondary guard，避 env override 48h + age=30h false-positive
2. **LOW-1**：REQUIRED escalation FAIL msg 加 `revert_recommended=false (approach_escalation)` hint

### 建議（非阻塞）
3. **LOW-2**：FAIL msg 結構化 `[FLAG_SET]` prefix
4. **LOW-3**：flag write fail 路徑 — 補 P2 alert downstream 不依賴 flag exists 邏輯

### 17 test 補建議
新增 1 test：`test_zero_fills_env_override_age_mismatch` — `LOOKBACK_HOURS=48` + age=30h + T1 12h 有 fill + T2 48h n=0，應 PASS / WARN（不應 false-positive ZERO_FILLS）

修完 → 重 E2 → 才 E4。

---

E2 PASS Items：
- 587/528 LOC 合 governance
- 0 hardcode path
- SQL 全參數化
- §九 + OpenClaw 9 條全綠
- 17 test 邊界覆蓋足
- ADR-0020 manual-only 真實 honor
- runner.py wire 不破壞既有 [40]/[68]
- baseline cache + flag JSON 完整 audit trail
