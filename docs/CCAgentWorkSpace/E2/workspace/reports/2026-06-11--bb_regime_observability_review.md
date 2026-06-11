# E2 PR Adversarial Review — feat/bb-regime-observability @ 52727d82 · 2026-06-11

**對象**：P1-BB-REVERSION-REGIME-OBSERVABILITY（hurst regime 觀測欄）。Worktree `/tmp/wt-bb-regime`，base `62085d17`，3 檔 +217/−1。
**設計權威**：PA `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-11--bb_reversion_regime_observability_design.md`
**E1 報告**：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-06-11--bb_reversion_regime_observability_impl.md`

## Verdict：PASS to E4（0 個需修 finding；5 INFO 不阻）

---

## 改動範圍

`git diff 62085d17..52727d82 --stat`：
- `on_tick_helpers.rs` +19/−1（persist_intent 第 12 參數 `hurst: Option<&HurstResult>` + `#[allow(clippy::too_many_arguments)]` + 兩鍵 + FUP-8 註釋修正），792→809 行
- `step_4_5_dispatch.rs` +6（record_pre_risk_rejection +param 透傳 + 3 call site 各 +1 行 `indicators.and_then(|i| i.hurst.as_ref())`），1813→1819 行
- `tests/fast_track_reduce.rs` +193（3 既有契約測試恰各 +1 行 `None,`、零刪行零斷言弱化〔awk 逐 hunk 證〕；+4 新測試 + probe helper），666→859 行

scope 紀律：commands.rs 未動（grep 唯一命中=既有註釋 :388）；OrderIntent / trading_writer / openclaw_types / 策略碼 0 觸碰（3 檔 diff 自證）。與 PA §6 完全一致；2 處申報偏差均驗證合理（見下）。

## 六軸結論（各一行 + 證據）

1. **熱路徑紀律 PASS** — diff 逐行 0 新鎖/0 IO/0 重算/0 await/0 spawn（grep `unsafe|unwrap|expect|panic!|\.lock\(|std::fs|File::|spawn` 對 production diff 0 hit）；`h.regime.as_str()` 回借用 `&str`（HurstResult.regime 是 String，volatility.rs:119-122）→ json! 構造時一次 ~14B String 拷貝 + 1 f64，僅 per-intent（3 call site 全在 intent-emission 分支內，非 intent tick 0 新指令）；量級=既有 30+ 鍵 details json 的 noise。
2. **fail-soft PASS** — None→兩鍵 present-null 且 intent 照常入列（親跑 test 2，`.get()` 區分 present-null vs absent）；NaN→hurst_value=null 不 panic、label 不受擾（親跑 test 3）；persist_intent 尾部 `let _ = try_send_trading_msg(...)` byte-未動（diff 只加鍵於 "signal_id" 前），intent 執行不依賴 persist 結果的結構不變。
3. **4 call site 完整性 PASS** — 親 grep 全 repo：persist_intent production caller 恰 3（dispatch :114 record 內/:752 exchange/:1059 paper），test caller 7，commands.rs 僅註釋；record_pre_risk_rejection 單 caller :549，實參=同函數 `indicators` 參數（無第 5 漏網）；hurst 參數插在 `scanner_gate` 後 `reason` 前，鄰位型別互異（Option<&ScannerGateAudit>/Option<&HurstResult>/&str）誤排必不編譯。
4. **同 snapshot 宣稱 PASS（全鏈親證）** — dispatch 簽名 :152 `indicators: Option<&IndicatorSnapshot>` → ctx :290 直接引用 → iter_ctx :374 `ctx.clone()`（Copy 同一引用，僅覆寫 position_state）→ strategy.on_tick :407 → bb_reversion :421 `let ind = match ctx.indicators` → gate :563-570 讀 `ind.hurst`；persist 三點讀同一 `indicators` 局部（grep `let indicators` 證 dispatch 內無 shadowing，唯一近名=indicators_5m :222 別軸）；同一函數調用域、共享引用不可變 → 結構上不可能 stale。`from_legacy_str` 僅 `"mean_reverting"`→AntiPersistent（hurst.rs:67-73）→ PA §3 驗收 SQL「gate-on 100% mean_reverting」語義成立。
5. **E1 三項自報全核實** — (a) clippy 阻斷=pre-existing：base `62085d17` 已含 `price_tracker.rs:132 since="2026-04-22"`（git show 證；真實路徑 `openclaw_core/src/risk/price_tracker.rs`，E1 報告省 `risk/` 段，無礙定位）；臨時修補不在 commit（diff 3 檔 + porcelain 全程空）；我複製同款臨時修補親跑 clippy lib+tests → **E1 3 檔 0 警告證實**（`-->` grep 0 hit），修補已還原驗空。(b) 測試置檔偏差成立：helpers :96=`#[cfg(test)]` sigma、:749-750=liquidation_tests，persist_intent 既有契約測試確實全在 fast_track_reduce.rs（:404/:463/:519）——置同檔正確。(c) FUP-8 註釋順改與代碼現實一致（regime 已落地、改後句僅除 regime 字，無虛假宣稱）。
6. **測試質量 PASS（親跑數字）** — HEAD lib **3791 passed/0 failed/1 ignored**（親跑）；diff +4/−0 test fn（grep 計數）→ base 算術=3787 與 E1 宣稱閉合；4 新測試在 module 內真執行（24/24）；**雙 mutation 親打全 bite**：①exchange site 改傳 `None` → 結構測試紅 `n=2`（與 E1 paper-site mutation 不同點，獨立性更強）②刪 `"hurst_value"` 鍵 → 恰 3 新測試紅（records/none/nan）；各還原後綠 + porcelain 驗空。

## 8 條 reviewer checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 一致 | PASS（2 偏差均申報且驗證合理） |
| 無靜默吞異常 | PASS（`let _ = try_send` 為既有 fail-soft 設計，未新增） |
| 日誌格式 | N/A（0 新日誌） |
| API 端點權限 | N/A |
| except 順序 / detail=str(e) | N/A（Rust） |
| asyncio blocking | N/A（同步函數 0 await） |
| 私有屬性穿透 | N/A |
| 測試數 ≥ 基準 | PASS（3787→3791，0 刪） |

## OpenClaw §3 checklist

| Item | 狀態 |
|---|---|
| 3.1 跨平台路徑 | PASS（diff 0 hit） |
| 3.2 注釋中文優先 | PASS（新註釋全中文含 why；INFO-1 見下） |
| 3.3 Rust 專條 | PASS（0 unsafe/unwrap/expect/panic 於交易路徑；Option 全 map） |
| 3.4 IPC 邊界 | PASS（0 觸碰） |
| 3.5 Migration Guard | N/A（jsonb additive，PA §2.6 論證 0 migration 成立） |
| 3.6 healthcheck 配對 | N/A（部署後 SQL 驗收歸 E4/QA 鏈） |
| 3.7 singleton | N/A |
| 3.8 檔案大小 | 809/859 >800 注意線（PA §4.7 預申報+E1 申報；INFO-4） |
| 3.9 Bybit API | N/A |
| 3.10/3.11 | N/A（無 leak/bias finding；無 ML pipeline 觸碰） |

## 對抗反問結果（自證摘錄）

1. Q:「details 兩鍵會否與既有鍵/別軸撞名？」· 證據：grep `hurst_label|hurst_value` 全 repo——僅 `hurst_label_for_symbol`（函數名子串）與 market_regime.py 局部參數名，0 個 details JSON key 生產者撞名；scanner 軸鍵 `market_regime` 嵌於 "scanner" 子物件無頂層衝突 · 結論：唯一。
2. Q:「Python 讀方會破嗎？PA 稱唯一讀方 opportunity_tracker」· 證據：grep `details->>` 全 program_code——canary_promoter.py :303-309 也讀 details 但對象是 `observability.drift_events`（:297 FROM 證）非 trading.intents · 結論：PA 宣稱成立，0 讀方受擾。
3. Q:「stress 紅是不是 E1 回歸？」· 證據：親跑 HEAD stress_integration=34p/1f，唯一紅=`stress_tick_latency_benchmark` 1076.8μs vs 1000μs debug 閾值，與 E1 數字（1053-1058μs）及 memory 2026-06-10 同款 flake 前科同形 · 結論：pre-existing flake 佐證成立；Linux base-vs-HEAD 權威歸 E4。
4. Q:「fmt clean 宣稱？」· 證據：`cargo fmt --check` dispatch 漂移恰 :1632/:1708（diff hunks :100-126/:554-560/:757-764/:1063-1070 不含），helpers/fast_track_reduce 0 漂移；dispatch_tests.rs 漂移=另檔未動 · 結論：宣稱成立。
5. Q:「既有 3 契約測試是否被弱化遮測？」· 證據：awk 逐 hunk 抽 ± 行——3 hunk 恰各 +1 行 `None,`，0 刪行 · 結論：純簽名適配，斷言原樣。

## Findings（全量，含 INFO；過濾裁決歸 PM）

| # | 嚴重性 | confidence | 位置 | 描述 | 建議 |
|---|---|---|---|---|---|
| INFO-1 | INFO | high | on_tick_helpers.rs:425-431 | FUP-8 被觸碰的雙語塊保留英文散文（僅刪一詞+追加中文更新）；skill 規定觸碰塊應去英文重複留中文，但此塊英文（edge/funding_rate/basis 待 G-1 + 原則 8 理據）未被中文完整重複，surgical 最小改保信息量可辯護 | 下次觸碰時中文化；不阻本輪 |
| INFO-2 | INFO | high | openclaw_engine 測試碼 4+1 處 | E1 建議的 clippy follow-up「1 行改 since」**不足以解鎖整鏈**：臨時修補 price_tracker 後另暴露 4 個 deny-level pre-existing error（pipeline_throughput_probe_impl.rs:466 / param_extractor.rs:428 / ipc_server/tests/risk_update.rs:141 / linucb/state_io.rs:257）+ stress_integration.rs:601，全非本 diff 檔 | PM 開 clippy-debt 單時納入全部 5 處 |
| INFO-3 | INFO | high | fast_track_reduce.rs:801 | 結構測試 `forward_expr` 精確字串 count==3：合法重構（如表達式抽變數）會紅——E1 已申報為有意 fail-loud，斷言訊息已指路 | 接受 as-designed |
| INFO-4 | INFO | high | helpers 809 行 / 測試檔 859 行 | 雙檔跨 800 注意線；PA §4.7 預申報「不拆檔，拆檔另案」 | PM 追蹤 split 另案備忘 |
| INFO-5 | INFO | medium | E1 報告 :51 | price_tracker 路徑寫 `openclaw_core price_tracker.rs:132` 省略 `risk/` 目錄段（真實 `src/risk/price_tracker.rs`）；行號/內容正確 | 無需動作，記錄供 follow-up 單援引 |

CRITICAL/HIGH/MEDIUM/LOW：無。

## §5 Multi-session race（5/5 PASS）

- 5a：`git fetch --prune` 後 origin/main=`d46b5cee`（P4 全鏈 16 commits 領先 base）；本 PR 3 檔 vs sibling 34 檔 `comm -12` **0 overlap**（sibling 0 個 rust/ 檔）；HEAD 落後屬預期（E1 已申報，rebase 歸 PM 裁）。
- 5b：review 起點 porcelain 空，unstaged 0 外洩檔。
- 5c：3 條 stash 全 pre-existing（與 memory 既錄一致，含 "not mine" 標註），未碰。
- 5d：本報告寫於主 repo workspace（additive 新檔），不涉 commit；worktree 0 寫入殘留。
- 5e：review 結束前 re-fetch——origin/main 無新 push，verdict 不受擾。
- mutation 紀律：3 次臨時改動（call-site None / 刪鍵 / price_tracker semver 診斷修補）全部改完即測即還原，每次 `git status --porcelain` 驗空。

## 結論

**PASS to E4**。E4 注意事項：Linux 全量 rebuild + 43 targets 基線對照 + stress base-vs-HEAD（Mac debug 閾值 flake 已三方佐證 pre-existing，Linux 為權威）+ 部署後 PA §3 驗收 SQL；merge 前 PM 處理 16-commit rebase（0 檔重疊，預期零衝突）。
