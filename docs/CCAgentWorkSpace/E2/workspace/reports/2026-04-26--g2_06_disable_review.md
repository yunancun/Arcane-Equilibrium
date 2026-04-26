# E2 Adversarial Review — Wave 3 G2-06 bb_breakout 永久 disable 落地

**日期**：2026-04-26
**Agent**：E2（Senior Backend Code Reviewer + Adversarial Auditor）
**前置**：PA RFC `2026-04-26--g2_06_bb_breakout_disposal_rfc.md` 推 C + PM approve；E1 落地報告 `2026-04-26--g2_06_bb_breakout_disable_landing.md`
**範圍**：4 子任務 8 檔（3 TOML + 1 Python healthcheck + 1 Rust comment + 1 sweep tool comment + CLAUDE.md + TODO.md）

---

## §1 必查 3 點（per PA RFC §5）

### 必查 1：TOML 三環境同方向（demo / paper / live）`active=false`

**驗證命令**：
```bash
grep -A 6 '^\[bb_breakout\]' settings/strategy_params_{demo,paper,live}.toml
```

**結果**：
- `demo`: `active = false` + 雙語 G2-06 comment ✅
- `paper`: `active = false` + 雙語 G2-06 comment ✅
- `live`: `active = false` + 雙語 G2-06 comment ✅

三環境 comment block 模板完全相同（4 行：英 2 + 中 2，G2-06 (2026-04-26) 標籤一致）。

**判定**：**PASS** ✅

### 必查 2：healthcheck [12] 改判邏輯不擴張 PASS 條件以外

**驗證**：對比 [12] diff（git diff 的 +148/-3）
- Line 765-770：新加 `if bb_active is False: return ("PASS", "...skip")` 早 return，**fail-soft 設計**
- Line 772-814：原 3 態 triage（FAIL/WARN/PASS）邏輯**完全保留**，無任何鬆綁

**Adversarial 重審**：
- `if bb_active is False:` vs `if not bb_active:` — 前者 `None`（fail-soft）正確 fall-through 走原邏輯，後者會誤吸 `None` 跳過 → E1 用對了 idiom
- StubCur 測試：`bb_active=False` 時 SQL **0 次執行**（SQL list `[]`），驗證早 return ✅
- 邊界：`(True, "ok")` → fall-through 跑 SQL；`(False, "ok")` → skip PASS；`(None, "...")` → fall-through fail-soft ✅

**判定**：**PASS** ✅

### 必查 3：CLAUDE.md §三 數值更新含「採集時間 + healthcheck id」（G6-04）

**驗證 CLAUDE.md §三 P1-11 條目改寫**：
- ✅ 日期：2026-04-26（commit 同次）
- ✅ healthcheck id：`[12]`、`[18]` 兩個皆引用
- ✅ runtime 數值：`squeeze_bw=0.03 noise floor 內 100% 觸發 / expansion_bw=0.04 永不達`
- ✅ commit hash 引用：`bcc5401`+`63957ad`、`0528d96`+`38a14ca`
- ✅ PA RFC 完整路徑引用：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g2_06_bb_breakout_disposal_rfc.md`
- ✅ 已完成里程碑索引表加 2026-04-26 條目

**判定**：**PASS** ✅

---

## §2 E1 funding_arb push back 判定（adversarial 重審）

### E1 主張
paper TOML `funding_arb.active=true` 與 demo/live `active=false` 不一致，但**不在 G2-06 範疇** — 引用 memory `feedback_env_config_independence`「三 config 故意分開」。

### E2 adversarial 重審

**關鍵 evidence chain**：

1. **memory `project_g2_funding_arb_monitor` 明寫**：「2026-04-18 v2 結案 NEGATIVE EDGE -36.76 bps / 0% 勝率 → daemon killed → demo `active=false`（Rust IPC + TOML 雙路徑）」
2. **demo TOML comment**：「停用 2026-04-18：G-2 v2 判決 NEGATIVE EDGE...待 R-02 Strategist 重評...再啟」← 結案 disable，明確
3. **live TOML comment**：「OC-5 FundingArb — inactive for live until paper/demo validated」← 保守 default，明確
4. **paper TOML comment**：「G-2 VALIDATION COMPLETE (2026-04-14): reverted to defaults after 21 paper fills」← **v1 完成時的 comment**，不是 v2 結案後的狀態

### 判定：E1 push back **技術上正確但 adversarial 視角 incomplete**

**`feedback_env_config_independence` 適用範圍辨析**：
- 原 memory（2026-04-19）寫「**risk_config TOML 故意分開**」：fee/cost/freshness/buffer 等**風控閾值**故意三環境不同
- **`active` 不是風控閾值，是策略 binary 開關**（active=結案啟用 vs disabled=結案/驗證待）
- funding_arb 已**全策略結案 NEGATIVE EDGE** → 三環境一致 disable 才符合「結案 disable」語義
- paper `active=true` 是 v1 (2026-04-14) → v2 (2026-04-18) 過渡期的歷史殘留 oversight，**沒被 v2 結案 sync**

**為什麼不阻擋 G2-06 PASS**：
1. PA RFC §5 明確劃定 G2-06 scope = bb_breakout 三環境同方向，不含 funding_arb
2. E1 在報告 5.1 主動 self-disclose 此問題 + 標明「不擴大範圍」← 透明且符合 minimal-scope 原則
3. funding_arb paper 仍 active=true 的後果：paper compute 浪費 + edge_estimates_paper.json 污染（已 NEGATIVE EDGE，繼續跑無價值）— 但**不影響 demo/live runtime**，不破壞 G2-06 disable 的有效性

### E2 結論：

**E1 push back 局部正確（不擴大 G2-06 scope ✅）**，但**揭發 separate finding**（funding_arb paper sync miss）需 PM 開新 ticket（建議命名 G2-FUP-FUNDING-ARB-PAPER-SYNC，工時 ~5min）。**不阻擋本次 G2-06 PASS**。

判定：**E1 push back ACCEPT**，funding_arb 觀察項另列 §3 Finding F2（MEDIUM，新 ticket）。

---

## §3 額外 Finding（severity + owner）

### F1 [LOW] [18] inventory 只讀 demo TOML 單檔，跨環境誤導風險

**證據**：line 687 `toml_path = base / "settings" / "strategy_params_demo.toml"`
**問題**：[18] 顯示「funding_arb disabled」但 paper `active=true` → 對「disabled 全範圍」誤導
**Owner**：E1（report 5.6 已 self-disclose）→ PM 決定是否開 G2-06-FUP（不阻擋）
**建議修法**（新 ticket）：(a) check name 改 `disabled_strategy_inventory_demo`；或 (b) 加 message disclaimer「per demo TOML; cross-env not checked」；或 (c) 擴展讀三 TOML 對比並警告差異
**E2 判定**：不阻擋本次 PASS（PA RFC §5 沒指定此細節，E1 self-disclose 透明）

### F2 [MEDIUM] funding_arb paper TOML active=true 與 demo/live 不一致（separate ticket）

**證據**：見 §2 完整論證
**問題**：v1 完成 → v2 結案的 sync miss；paper 繼續跑已驗無 edge 的策略
**Owner**：PM 開新 ticket（建議 G2-FUP-FUNDING-ARB-PAPER-SYNC，工時 ~5min）
**建議修法**：paper TOML `[funding_arb].active=true → false` + comment「2026-04-18 G-2 v2 結案 NEGATIVE EDGE」與 demo 同步
**E2 判定**：不阻擋本次 G2-06 PASS（不在 PA RFC scope）

### F3 [LOW] healthcheck.py 文件 2103 行 > §九 1200 硬上限

**證據**：`wc -l helper_scripts/db/passive_wait_healthcheck.py = 2103`
**問題**：累積 17+ check 歷史長文件，但本次 G2-06 增 ~148 行非 root cause
**Owner**：未來 G6/G7 audit（既存技術債，非 G2-06 引入）
**建議修法**：拆分 helper（如 `passive_wait_healthcheck/{checks_pipeline,checks_edge,checks_governance,checks_inventory}.py`）
**E2 判定**：不阻擋本次 PASS（既存問題；E1 報告未提及但這是合理省略，scope 控制好）

### F4 [LOW] [18] 在 `--quiet` 模式下被 hide（drift 防線設計打折）

**證據**：line 2083 `if args.quiet and status == "PASS": continue`
**問題**：[18] 設計為「audit 時 visible」但 `--quiet` PASS 會被過濾；不過 cron 6h（`passive_wait_healthcheck_cron.sh`）**無 `--quiet` flag**，default visible
**Owner**：E1 / 未來改進（不阻擋）
**建議修法**：(a) [18] 改 always-print（特殊 hook 在 quiet loop 加例外）；或 (b) 文檔化「audit 時建議不加 --quiet」；或 (c) status='WARN' 強制 visible（但語義變動）
**E2 判定**：不阻擋本次 PASS（cron 配置 default 無 quiet → drift 防線實際運作正常）

### F5 [INFO] Rust comment block 設計合理，doc-attribute 不破壞

**驗證**：
- `cargo check --lib` PASS（無 error，9 個 warning 為 pre-existing）
- `cargo doc --no-deps -p openclaw_engine` 生成 enum.BbBreakoutProfile.html
- meta description 含原 docstring「P1-11 (3): A/B profile preset...」 ✅
- sidebar variants：Aggressive / Balanced / Conservative 三變體完整 ✅
- 對抗測試：最小 reproducer 驗證 `///` + `//` + `#[derive]` sandwich pattern，diff 無變化 ✅

E1 報告 4.1 點驗證**完全準確** — `//` plain comment 在 `///` doc-comment 與 `#[derive]` 之間是合法 orphan comment，不影響 doc-attribute attachment。

**判定**：**PASS** ✅（E1 設計選擇合理；未用 `#[deprecated]` 符合 RFC §6「保留 future investment」語義）

---

## §4 跨平台 ★★ 檢查（CLAUDE.md §七）

### 4.1 路徑硬編碼 grep
```bash
grep -nE 'Path\.home\(\)|/home/ncyu|/Users/' \
  helper_scripts/db/passive_wait_healthcheck.py \
  rust/openclaw_engine/src/strategies/bb_breakout/params.rs \
  helper_scripts/research/bb_breakout_threshold_sweep.py \
  settings/strategy_params_*.toml
```

**結果**：
- `helper_scripts/db/passive_wait_healthcheck.py:636,686` — `Path(os.environ.get("OPENCLAW_BASE_DIR", str(Path.home() / "BybitOpenClaw/srv")))` ← 與 codebase 既有 fallback pattern（line 384/844/1527）一致 ✅
- 其他檔案：0 命中 ✅
- TOML 檔：0 命中 ✅
- Rust params.rs：0 命中 ✅

**判定**：**PASS** ✅（fallback `Path.home() / "BybitOpenClaw/srv"` 是 cross-platform 正確 idiom，env var override 優先，與 INFRA-PREBUILD-1 L2-5 同模式）

### 4.2 雙語注釋（CLAUDE.md §七 ★★）
- TOML 三環境 disable comment：4 行（英 2 + 中 2）✅
- Python `_read_bb_breakout_active_from_toml()`：docstring 中英對照 ✅
- Python `check_disabled_strategy_inventory()`：docstring 中英對照 ✅
- Python `check_bb_breakout_post_deadlock_fix()` 修改部分：中英對照新增 ✅
- Rust params.rs G2-06 comment block：4 行（英 2 + 中 2）✅
- sweep tool header comment：4 行（英 2 + 中 2）✅

**判定**：**PASS** ✅

### 4.3 § 九 8 條 checklist
| 項 | 狀態 | 備註 |
|---|---|---|
| 改動範圍與 PA 方案一致 | ✅ | 4 子任務符合 PA RFC §5；無多改 |
| 沒有 except:pass | ✅ | 6 處 `except Exception as e:` 全 return WARN/FAIL/None+diag |
| 日誌使用 %s 格式 | n/a | healthcheck 是 return message buffer，非 logger |
| 新 API 端點有 _require_operator_role() | n/a | 無新 API |
| except HTTPException: raise 在 except Exception 之前 | n/a | 無 HTTPException |
| detail=str(e) 已改為 "Internal server error" | n/a | 無 HTTP layer |
| asyncio 路由中沒有 blocking threading.Lock | n/a | 純 sync filesystem check |
| 沒有私有屬性穿透 | ✅ | 無 ._xxx access |

**判定**：**PASS** ✅

---

## §5 E2 結論

### 結論：**PASS to E4**（with 1 separate ticket recommendation）

#### G2-06 落地主體完成度 ✅
- TOML 三環境 disable + 雙語 comment 模板一致
- healthcheck [12] 改判 fail-soft + 早 return PASS skip（0 SQL 副作用）
- healthcheck [18] 純 observability + always PASS（drift 防線設計符合 G6-04）
- Rust comment block 不破壞 doc-attribute attachment（已驗 cargo doc + 最小 reproducer）
- 跨平台 ★★ 兼容（OPENCLAW_BASE_DIR fallback 與 codebase 既有 pattern 一致）
- 雙語注釋全覆蓋
- CLAUDE.md / TODO.md drift 規則 G6-04 符合

#### 必查 3 點全 PASS ✅
- §1.1 TOML 三環境 active=false 同方向 ✅
- §1.2 healthcheck [12] 改判邏輯不擴張 ✅
- §1.3 CLAUDE.md §三 採集時間 + healthcheck id 規則 ✅

#### 對抗反問結果（自行 push back 自己）
| Q | A |
|---|---|
| E1 說「測試通過」— mock 了什麼？ | StubCur 驗 SQL 0 次執行 ✅；Python 3.12 真實讀 TOML 回 False ✅；Rust cargo doc 真實生成 + 對比 minimal repro 兩處 attached ✅ |
| 「沒副作用」— grep 結果？ | 8 檔 diff、healthcheck 19 個 check fn 全 load OK；無 cross-module 影響 |
| 「edge case 已處理」— None 注入？ | `if bb_active is False:` 排除 None；fail-soft 走原 triage ✅ |
| 「規格一致」— PA RFC 第幾行對應？ | RFC §5 4 子任務 + E2 必查 3 點，逐項對齊 |

#### Separate Ticket Recommendation（不阻擋本次 PASS）
**G2-FUP-FUNDING-ARB-PAPER-SYNC**（建議 PM 開新 ticket）：
- paper TOML `[funding_arb].active=true → false`（與 demo/live 同步）
- 理由：v1 (2026-04-14) → v2 (2026-04-18) 結案 NEGATIVE EDGE 過渡期 sync miss；非 G2-06 scope；E1 透明 self-disclose
- 工時：~5min（TOML 1 行 flip + comment 同步）
- 嚴重性：MEDIUM（影響 paper compute + edge_estimates_paper.json 污染，但不影響 demo/live runtime）

#### 派發給 E4 的回歸測試重點（per E1 報告 6.2）
1. `cargo test --release -p openclaw_engine --lib` baseline 1980 不變（C 路徑無 Rust 業務改動，必綠）
2. `python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -E '\[12\]|\[18\]'`
   - [12] 應 `PASS [12] bb_breakout disabled by G2-06 (active=false in TOML); fill check skipped`
   - [18] 應 `PASS [18] disabled_strategy_inventory disabled strategies: bb_breakout, funding_arb (active count=3: bb_reversion, grid_trading, ma_crossover)`
3. demo restart 後 5min `tail -200 engine.log | grep 'strategy=bb_breakout'` 應只剩 `set_active(false)` 啟動 log，0 個 on_tick / signal eval log

---

## 附錄：本次 review 採集的 evidence

| 驗測 | 命令 / 路徑 | 結果 |
|---|---|---|
| TOML 三環境同方向 | `grep -A 6 '^\[bb_breakout\]' settings/strategy_params_{demo,paper,live}.toml` | 3 檔 active=false + 雙語 comment 同模板 ✅ |
| funding_arb 對比 | `grep -A 8 '\[funding_arb\]' settings/strategy_params_{demo,paper,live}.toml` | demo/live=false, paper=true（separate finding F2）|
| Rust cargo check | `cargo check --lib` | 0 error / 9 pre-existing warning ✅ |
| Rust cargo doc | `cargo doc --no-deps -p openclaw_engine` | enum.BbBreakoutProfile.html 完整 ✅ |
| Rust comment minimal repro | `/tmp/rust_doc_test/{test,test_clean}.rs diff` | doc identical（0 byte diff）✅ |
| Python syntax | `python3.12 -c "import ast; ast.parse(...)"` | OK ✅ |
| Python module load | `importlib spec_from_file_location + exec_module` | 19 check fn 全 load OK ✅ |
| `_read_bb_breakout_active_from_toml()` 真值讀取 | Python 3.12 直跑 | `(False, 'ok')` ✅ |
| `check_disabled_strategy_inventory()` 列舉 | Python 3.12 直跑 | `PASS disabled strategies: bb_breakout, funding_arb (active count=3: ...)` ✅ |
| `check_bb_breakout_post_deadlock_fix()` skip 路徑 | StubCur stub 模擬 | SQL 0 次執行，return PASS skip ✅ |
| 跨平台 grep | `grep -nE 'Path.home...| /home/ncyu | /Users/' <files>` | 0 命中（fallback pattern 與既有一致）✅ |
| cron 配置 | `crontab -l` + `passive_wait_healthcheck_cron.sh` | 6h 無 --quiet flag → [18] visible ✅ |
| File size | `wc -l helper_scripts/db/passive_wait_healthcheck.py` | 2103（既存技術債，F3 informational）|

---

E2 REVIEW DONE: PASS to E4 · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-26--g2_06_disable_review.md`
