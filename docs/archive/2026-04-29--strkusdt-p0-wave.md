---
date: 2026-04-29 CEST (歸檔日)
wave_date: 2026-04-26 ~ 2026-04-27
topic: STRKUSDT Dust Spiral P0 Wave — 7 fix（F1 deploy + F2-F7 6 PR）歸檔
type: archive (TODO.md 頭部敘述歸檔)
status: ✅ COMPLETED — 6 PR merged，2nd deploy 預備指令明確
primary_signoff: docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-27--strkusdt_p0_wave_signoff.md
related_pa_rfc: docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--three_p0_fixes_design.md
related_audits:
  - docs/CCAgentWorkSpace/Operator/2026-04-26--strkusdt_dust_spiral_rca.md
  - docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-26--exit_features_writer_bug_audit.md
deploy_commits:
  f1_deploy: af48ee1   # 直 main，2026-04-26 16:00 CEST 第 1 次 rebuild
  f2_merge:  1dff948   # cross-symbol price contamination
  f6_merge:  5ac7a80   # edge_estimates 1h reload daemon
  f3_merge:  310ae29   # phantom dust evict-on-dust 4 trigger
  f4_merge:  31c8206   # trading_writer LIVE WS fills audit + ML pipeline filter
  f7_merge:  1341c01   # 8 silent-regression sentinels [22]-[29]
  f5_merge:  1edc6fe   # GUI Live label anti-human-design fix
e4_combined: 2252 / 0 failed (兩遍同綠)
healthcheck_added: 8 silent-regression sentinels [22]-[29]
---

# STRKUSDT Dust Spiral P0 Wave 歸檔

本檔案承接 TODO.md 頭部敘述（含 STRKUSDT P0 wave merge 順序、commit 數字、E4 regression 數據、新 healthcheck 名稱、RCA 三層、sign-off 路徑），TODO.md 隨後以一行索引取代。

---

## 觸發事件

2026-04-26 上午 STRKUSDT 倉位出現 dust spiral：
- `fast_track ReduceToHalf` 每 60s 半倉 × 37 次直到 float epsilon
- `learning.exit_features` 寫 37 個 noise label 行（污染 ML training set）
- `trading.fills` 寫 41 個 phantom fill 行
- 部分 fills 跨 symbol contamination（per F2 RCA）

引發 4 個並行獨立 audit + 7 個 fix 的 P0 Wave。

## 4 個並行獨立 audit

| Agent | 發現 | 報告 |
|---|---|---|
| **PA** | RCA 三層因果鏈 + Operator 直觀視角報告 | `docs/CCAgentWorkSpace/Operator/2026-04-26--strkusdt_dust_spiral_rca.md` + 隔壁 PA session 內聯 RFC |
| **MIT** | EXIT-FEATURES-WRITER-BUG-1 雙 root cause（RCA-A primary + RCA-B 併發）| `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-26--exit_features_writer_bug_audit.md` |
| **E5** | Silent-regression 8 sentinel spec ([22]-[29])| 併入 F7 |
| **A3** | LIVE GUI fake-success「demo data 套 live 皮」設計缺陷 | 併入 F5 |

PA Design RFC（F3+F4+F6 三 Rust 工作組）：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--three_p0_fixes_design.md`

---

## Merge 順序（per E2 推薦）

```
main → F2 → F6 → F3 → F4 → F7 → F5
```

**理由**：
- F2 first：cross-symbol price contamination 是底層 fix，後續 F3/F4 在此基礎上做 evict + audit
- F6 early：edge_reload daemon 純獨立，無 cross-cut
- F3 → F4：F3 status arm @ L1160 + F4 unattributed_emit re-export @ L83 不撞區（E2 推薦順序設計奏效）
- F7 後：FUP-23 SQL exclude 依賴 F4 audit row schema
- F5 last：純 Python，不影響 Rust merge tree

**6 個 merge commits**：
| 順序 | Fix | Branch HEAD | Merge commit |
|---|---|---|---|
| 1 | F2 cross-symbol price contamination | `e1-f2-cross-symbol-price` (HEAD `faebe51`) | `1dff948` |
| 2 | F6 edge_estimates 1h reload daemon | `e1-f6-edge-reload-daemon` (HEAD `0bb71d4`) | `5ac7a80` |
| 3 | F3 phantom dust evict-on-dust 4 trigger | `e1-f3-phantom-dust-evict-isolated` (HEAD `8a2c42a`) | `310ae29` |
| 4 | F4 trading_writer LIVE WS audit + ML filter | `e1-f4-trading-writer-live-isolated` (HEAD `db1c012`) | `31c8206` |
| 5 | F7 8 silent-regression sentinels [22]-[29] | `e1-f7-healthchecks-isolated` (HEAD `e437a87`) | `1341c01` |
| 6 | F5 GUI Live label anti-human-design fix | `e1-f5-gui-live-anti-human-design` (HEAD `2f353ab`) | `1edc6fe` |

F1 已先期 deploy 直接到 main：commit `af48ee1`（2026-04-26 16:00 CEST 第 1 次 rebuild）

---

## Findings（7 fix 對應）

| # | Fix | Owner | E2 verdict | E4 verdict |
|---|---|---|---|---|
| **F1** | EXIT-FEATURES-WRITER-BUG-1-FIX cohesive 1+2 RCA repair（dust spiral primary fix）| E1 | E2 Tier 5 PASS（`1209a9b` review）| 已 deploy（2026-04-26 16:00 CEST 第 1 次 rebuild）|
| **F2** | Cross-symbol price contamination on close dispatch | E1 | round 1 PASS | 2216 / 0 |
| **F3** | Phantom dust evict-on-dust 4 trigger | E1 | round 1 PASS | 2225 / 0 |
| **F4** | trading_writer LIVE WS fills audit + ML pipeline filter | E1 | round 1 RETURN（unattributed_emit split）→ round 2 PASS | 2228 / 0 + 38 / 0 bins |
| **F5** | GUI Live label anti-human-design fix | E1a | round 1 RETURN（HIGH server-side phantom guard 缺）→ round 2 PASS | 17 pytest |
| **F6** | edge_estimates 1h reload daemon + manual IPC | E1 | round 1 PASS | 2219 / 0 + 50 bins |
| **F7** | 8 silent-regression sentinels [22]-[29] | E1 | round 1 PASS w/ FUP-23 → round 2 PASS（FUP-23 SQL exclude 落地）| 39 pytest |

**E2 雙輪 review**：
- Round 1：Rust 4 PR + Python 2 PR 並行 review，3 個 RETURN（F4 / F5 / F7 FUP-23）
- Round 2 re-review：3 個 RETURN 修復後 batch agent 內聯 verdict（system 限制不寫 .md，verdict 在 batch 回應內）

---

## Verification

### E4 combined regression

報告：`docs/CCAgentWorkSpace/E4/workspace/reports/2026-04-27--p0_wave_combined_regression.md`

- Combined merged tree cargo lib **2252 / 0 failed**（兩遍同綠 = 非 flaky）
- Math check 完美對齊：baseline 2212 + F2(+4) + F3(+13) + F4(+16) + F6(+7) = 2252
- Merge dry-run 6 stages：4 clean + 2 doc-only union-resolvable conflicts in `docs/CCAgentWorkSpace/E1/memory.md`

### Pytest 新增

- F4：7 / 0
- F5：17 / 0
- F7：39 / 0
- **合計 63 / 0**

### Test baseline 升級

| 指標 | Pre-wave | Combined | 變化 |
|---|---|---|---|
| cargo lib | 2161 / 0（TODO L10）| **2252 / 0** | +91（+4 F2 / +13 F3 / +16 F4 / +7 F6 / +51 Tier 8/9 Phase 1A H state cache buffer）|
| pytest（本 wave 新）| — | **63 / 0** | F4 7 + F5 17 + F7 39 |
| healthcheck | 19 check | 27 check | +8（F7 [22]-[29]）|

baseline drift 警告（已 acked）：origin/main `82bbe5e` 實測 2212（pre-wave）+4+13+16+7 = 2252 combined。TODO/CLAUDE.md §十一 寫 2161 過期 → sign-off Step 3 同 commit 更新。

### 8 個新 healthcheck checks（F7 [22]-[29]）

| ID | 名稱 |
|---|---|
| [22] | trading_pipeline_silent_gap |
| [23] | orders_fills_consistency（FUP-23 SQL exclude `unattributed:%`）|
| [24] | signals_writer_freshness |
| [25] | dust_qty_distribution |
| [26] | dust_spiral_noise_in_ef |
| [27] | intents_counter_freeze |
| [28] | phantom_fills_attribution |
| [29] | reconciler_paper_state_divergence |

合計 healthcheck cron 6h 跑 **27 check**（19 既有 [1-15]+[Xa]+[Xb]+[16]+[18] + 8 新 STRKUSDT P0 wave F7 [22-29] silent-regression sentinel）。

---

## STRKUSDT Dust Spiral RCA — 三層因果鏈

PA + MIT 雙獨立 RCA 結論一致。

### Layer 1（root entry_notional=0）：MICRO-PROFIT-FIX-1 fail-open

```rust
// step_0_fast_track.rs:317（pre-fix）
if entry_notional <= 0.0 { return true; }
```

對 legacy/restored dust 倉位（`bybit_sync` adopted positions / `phys_lock` 殘餘 / boot 重啟後 paper_state 重建）失效 → fast_track 永遠 emit ReduceToHalf — STRKUSDT smoking gun。

### Layer 2（fail-open Gate 2）：cross-symbol price contamination

`pipeline_helpers.rs:217 try_emit_exit_feature_row` 對 partial reduce 也寫 EF row（無 `is_partial_reduce_tag` skip）→ 37 次半倉 × 1 EF row each = **37 個 noise label** 進 `learning.exit_features` 污染 ML training set 8 dim feature。

### Layer 3（cross-symbol price contamination on close dispatch）

F2 揭發 — close dispatch 在 multi-symbol concurrent 寫入時，price 來源誤用 cross-symbol last_price → **41 個 phantom fill** 寫進 wrong symbol（per F2 RCA `e44755a` commit message + E2 round 1 review）。

### 致命組合

3 層 bug 同時生效時 → STRKUSDT-like 突發事件（任一夠用 partial 倉位 + symbol concurrency + entry_notional=0）→ 50ms 內 phantom fill cascade。

### 為什麼 7 月 18 日後第一次顯露

- 2026-04-19 多策略上線後，dust 倉位 baseline 提高（grid_trading rotation + bb_breakout cross-pair）
- Layer 3 cross-symbol 條件：≥3 symbol concurrent close（4-26 早上 STRKUSDT + LINKUSDT + DOGEUSDT 同時觸發）
- Layer 1 entry_notional=0 條件：legacy bybit_sync adopted positions（4-19 後新增 6 strategies adopted positions），entry_fee=0 + entry_notional=0

---

## 三大 P0 確認 fix 細節

### (a) F1 deploy 修 dust spiral primary（已 live）

- **commit `af48ee1`**
- **位置**：`step_0_fast_track.rs:317-360` 4-layer dust filter（取代原 `entry_notional <= 0` fail-open）
  - Layer A1：`entry_notional > MIN_ENTRY_NOTIONAL_USD` 硬檢
  - Layer A2：legacy/restored 倉位特例 fallback
  - Layer A3：paper_state 重建後 entry_fee 推算
  - Layer A4：dust qty floor + fast_track skip emit
- **deploy**：2026-04-26 16:00 CEST（第 1 次 rebuild，binary mtime 16:00）
- **驗證**：F1 deploy 後 STRKUSDT-like spiral 0 reproduce（24h post-deploy 觀察通過）

### (b) F4 audit row + F7 [23] cross-cut 收尾

**F4 commit `db1c012`** 在 `trading.fills` 寫 unattributed audit row（`strategy_name='unattributed:bybit_auto'` + `context_id='unattrib-{exec_id}-{ts_ms}'`）但**不寫對應 `trading.orders`**（per design：只 audit 不重寫 order entry）。

**F7-FUP-23 cross-cut**：F4 audit row 觸發 [23] orders_fills_consistency 誤 FAIL（fills_n=1 / orders_n=0 → pairs_with_missing_orders）。

**修法（commit `bdde091`）**：F7 [23] SQL 加 `AND f.strategy_name NOT LIKE 'unattributed:%'` filter。
**FUP-23-DOC（commit `e437a87`）**：fix docstring reference `learning.execution_orphans` → `trading.fills strategy_name`。

E4 round 2 verify：[23] FAIL 6 pairs/11 dropped 是 pre-existing real finding（與 F4 audit row 無關），exclude filter 生效。

### (c) F5 GUI fake-success「demo data 套 live 皮」修

A3 audit 揭發：`tab-live.html` 在 engine_kind=demo + Mainnet slot configured 時，會用 demo 數據填 Live tab dashboard（fake-success），且「全部平倉」按鈕無 client+server-side 雙重 guard，curl bypass 後 IPC fail → REST fallback 用 demo client → 誤平 demo 倉。

**5 邊界齊備修法**（commits `51be82f` + `3d1fb1f` + `2f353ab`）：
1. **Integrity-fail view**：`actual_engine_kind != 'live'` → hide dashboard
2. **Action-guard write button**：`engine_kind != 'live' OR execution_authority != 'granted'` → disable
3. **Body class CSS modes**：live/demo/paper/unknown 4 態
4. **Manual refresh defensive**：path 外呼用 `actual_engine_kind !== 'live' return`
5. **Account endpoint phantom envelope**：`_phantom_view_guard()` server-side detect + `_phantom_view_guard_write()` write-side（F5-RETURN issue-1 HIGH fix）

E2 round 2 verify：5 邊界 + 11 + 6 pytest 全綠（17 / 0）

---

## Acceptance criteria 全達標

### 16 root principles 對應

11/11 適用條目全合規（5 條 ➖ 不適用）。

| # | 原則 | 對應 fix | 狀態 |
|---|---|---|---|
| 1 | 單一寫入口 | F4 unattributed audit 經 trading_writer 唯一入口 | ✅ |
| 2 | 讀寫分離 | F5 GUI server-side phantom guard 寫端 422 | ✅ |
| 4 | 策略不繞風控 | F1 entry_notional 硬檢守住 fast_track 入口 | ✅ |
| 5 | 生存 > 利潤 | F1 4-layer dust filter 防 dust spiral cascade | ✅ |
| 6 | 失敗默認收縮 | F1 fail-open 改 fail-closed | ✅ |
| 7 | 學習 ≠ 改寫 Live | F4 ML pipeline filter `strategy_name NOT LIKE 'unattributed:%'` | ✅ |
| 8 | 交易可解釋 | F4 audit row 含 context_id + exec_id + ts_ms | ✅ |
| 9 | 災難保護 | F3 evict-on-dust 4 trigger 雙重清掃 | ✅ |
| 10 | 認知誠實 | RCA 三層 by PA + MIT 雙獨立 + 結論一致 | ✅ |
| 12 | 持續進化 | F4 audit row 進 ML pipeline filter 後保留 RCA 信號 | ✅ |
| 16 | 組合級風險 | F2 cross-symbol price contamination fix 防組合級 phantom | ✅ |

### §九 file size

| 檔案 | combined 行數 | §九 cap | 狀態 |
|---|---|---|---|
| `loop_handlers.rs` | **1212**（baseline 1187 + F3 +25 + F4 抽 sibling 215 行）| 1200 hard cap | ⚠️ 超 12 行 — follow-up STRK-FUP-LOOP-HANDLERS-SPLIT P2 |
| `unattributed_emit.rs`（F4 抽 sibling）| 215 | — | ✅ |
| `checks_strategy.py` | 1154 | 1200 hard cap | ✅（46 行 buffer）|
| `tab-live.html` | HTML 不適用 §九 | — | ➖ |

雙語注釋 / 跨平台 grep / 測試全綠詳見 sign-off 報告 §4。

---

## Sign-off + 後續 FUP

### Sign-off

PM Sign-off：`docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-27--strkusdt_p0_wave_signoff.md`
（含 16 根原則對照、§九 file size、雙語注釋、跨平台、test baseline、deploy plan、test baseline 升級表、PM signature block）

```
pm_approval:
  strkusdt_p0_wave: APPROVED
  rcA_three_layer: VERIFIED (PA + MIT 雙獨立 RCA 結論一致)
  fix_count: 7 (F1 deploy + F2-F7 6 PR)
  e2_dual_round_review: PASS (round 1: 3 RETURN; round 2: all PASS)
  e4_combined_regression: PASS (2252/0 兩遍同綠 + 63 pytest 全綠)
  merge_ready: TRUE
```

### 5 個 follow-up tickets（per E4 push backs）

1. **STRK-FUP-LOOP-HANDLERS-SPLIT P2** — `loop_handlers.rs` 1212 > §九 1200 hard cap 12 行；下次 G5 wave split status arm reaper 區段（L1160-1171 F3 contribution）到 sibling，與 F4 `unattributed_emit.rs` pattern 一致；E1 ~30min
2. **STRK-FUP-MEMORY-CONFLICT-RESOLVED P3** — F6→main + F7→main 兩處 `docs/CCAgentWorkSpace/E1/memory.md` union conflict；採 `git merge -X union` 自動 union 策略 / 衝突時 PM 手動 resolve；已在 Step 2 完成
3. **STRK-FUP-BASELINE-UPDATE P3** — TODO L9-L10 + CLAUDE.md §十一 baseline 「2161」過期，merge 後實測 2252；本 sign-off Step 3 同 commit 更新
4. **STRK-FUP-F7-CRON-CD-CHECK P3** — F7 cron wrapper `cd $BASE_DIR` 跑 stale main worktree runner；wrapper 加 grep `[22]`-`[29]` 在 latest log 內自驗（防 wrapper 路徑漂移）；E1 / operator ~15min
5. **STRK-FUP-HEALTHCHECK-PRE-EXISTING P2** — 5 個 pre-existing healthcheck FAIL（[3]/[19]/[23]/[24]/[26]/[27]）暴露的 silent-dead pipelines；屬 PA Wave 4 / G3-08+ scope，非本 wave 引入；F7 [22-29] 正確發現它們即達 silent-dead sentinel 設計目的；PA 1-3d design RFC

### Deploy

**2nd Deploy 指令**（`source ~/.cargo/env` 必加 — per F1 第一次失敗教訓 cargo not found）：

```bash
ssh trade-core 'cd ~/BybitOpenClaw/srv && source ~/.cargo/env && bash helper_scripts/restart_all.sh --rebuild 2>&1 | tail -50'
```

**Post-deploy verify**：
1. `engine_watchdog --status` engine alive=true + new PID
2. `passive_wait_healthcheck.py` 跑齊 27 check
3. `engine.log | grep -iE "edge_estimates|reload"` F6 daemon spawn 驗證
4. `engine.log | grep -iE "EVICT-ON-DUST"` F3 boot reaper trigger 驗證

### Hard boundary（本 wave 0 觸碰）

```
live_execution_allowed: UNCHANGED (false)
decision_lease_emitted: UNCHANGED (false)
max_retries: UNCHANGED (0)
OPENCLAW_ALLOW_MAINNET: UNCHANGED (unset)
authorization.json: UNCHANGED (no live deploy this wave)
```

---

## 備註

- 本檔案僅做「TODO.md 頭部敘述歸檔」用途，不改動代碼、不改動 sign-off 報告
- 進一步細節請查 PM Sign-off 報告 + PA RFC + MIT audit + Operator RCA 4 份原文
- TODO.md 將以一行索引指向本檔
