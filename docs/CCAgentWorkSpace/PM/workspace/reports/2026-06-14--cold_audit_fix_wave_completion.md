# 冷酷審計修復 Fix-Wave — 完成總結

**日期**: 2026-06-14 ｜ **觸發**: operator `/loop` 「確保盈利完整修復…每一條逐條核實…簡潔美麗；1.對齊 2.批准 3.可以但僅此一次」
**模式**: 4 batch workflow（E1→E2→(E3)→E4 鏈，主會話逐項親核 diff）｜ **凍結基底**: 審計於 `976d420e`；修復期間 parallel session 推進至 HEAD `48cdbfe2`（ADPE activation）
**邊界**: 全程 report-to-worktree，**未 commit/push/部署/rebuild/restart**（commit operator-gated）；只動指派檔，未碰 parallel session（ADPE/explore-gate/closed_pnl/m4）WIP

---

## 1. 已修復並驗證（10 項，皆綠 checkpoint，待 operator commit）

| 項 | 修法（簡潔美麗） | 驗證 |
|---|---|---|
| **AUTH-1** P1 | `update_per_engine_global_config` engine=="live" 先過 `all_five_live_gates_ok(require_authz=True)`→409 fail-closed（複用唯一 primitive，鏡 post_live_session_start）；Rust risk/live audit-only `warn!`（非硬擋，留 g2 直連） | E2+**E3**+E4；+8 測；Python 4746/66、Rust 3817/0；demo/paper 不受門 |
| **PROFIT-1** P1 | **NO-FIX 裁決**（replay-gated）：雙重扣成本數學為真但 threshold-reject 路徑 dormant（validation_passed 前置先擋；runtime 0 eligible cell）；released cell 不可轉移 live（demo 樂觀/無 slippage）。守 survival-first 不翻 | QC 源碼 + MIT read-only replay + PA 裁；親驗 gates.rs:200/219 互斥 |
| **PROFIT-1-HC** P1 衍生 | 哨兵 `[90]` `check_cost_gate_double_deduct`：per-cell threshold 鏡 gates.rs，alert if validation_passed∧runtime_bps>0∧<threshold | E2 抓 scalar-vs-per-cell HIGH-1 已修；28 測；Linux 真 117-cell=PASS/0；**positive-bite=WARN/exit1（證非 no-op）** |
| **PERF-1** P1 | `step_4_5` 5m 指標 bar-close gated cache（gate-safe 指標才快取，bb_breakout live-price 仍每 tick） | QC 驗 intra-bar 獨立；E4 **bit-identical**（byte+1e-4）+mutation-bite；p99 ~1.5µs↓；3825/0 |
| **PERF-2** P1 | `Cargo.toml` `lto="thin"`+`codegen-units=1`（fat 探測後 revert） | avg −4.2%/p99 −3.3%（E2 獨立復現）；bit-identical 3825/0；clean build +45~89% 一次性 deploy-only |
| **PERF-3** P1 | `get_ollama_status` `is_available()`→`await is_available_async()`+`raise_for_status()` 還原 fail-soft | E2 抓 503+JSON 退化已修；4750/66 |
| **SCHEMA-1** P1 | `schema_contract_test.rs`（6 probe，column-drift bite 真 PG 親證）+ PR-only Linux PG CI job（尊重成本「僅此一次」）+ `audit_migrations.py` relabel informational | E2+E4；Linux read-only 6/6 probe 0 drift；未改 93 call site |
| **MODEL-REGISTRY-HC** P2 | freshness check：stale shadow model 現可見 WARN（區分新鮮 vs 過齡，不誤報 FAIL） | E2+E4；+9 測；Linux read-only 驗 |
| **SEAM-GUARDS-RUST** P3 | submit_external_order engine=="live"→reject（鎖死 latent，僅擋真錢 mainnet，demo/livedemo 不擋）+ method_registry docstring 去誤導 + strategy.rs 註釋 | E2+E4；fail-closed 新測+mutation-bite |
| **SHADOW-QTY-PREROUND** P3 | 移除 client 3-bucket pre-round（Rust authoritative round 擁有精度）+ qty_rounds_to_zero 加 log（paper-only 靜默丟單可見） | E2+E4 |
| **PERF-3/GUI/funding-doc/doc-drift** | PERF-3(上)；GUI 死 Paper 按鈕+engine_alive 第一屏+Earn jargon（E1a node --check）；funding_arb doc-vs-code 訂正（7 doc，0 碼）；README/SCRIPT_INDEX/MEMORY 漂移訂正 | E2 APPROVE（doc 無回歸） |
| **AI-PRICING** P2 ⚠️ | ai_pricing.yaml 補 opus-4-8/sonnet-4-6/haiku-4-5、退役舊型號 active:false、對齊 layer2_types 雙副本（選項2 最小） | E2+E4。**⚠️ 價格值（opus-4-8 $5/$25 等）agent-sourced，commit 前須 operator 對 anthropic.com 核實**（opus 由 $15/$75 大降，存疑） |

---

## 2. Deferred（已文檔化，不自動修——需 operator 決策 / 他人 WIP / Linux mutation）

| 項 | 為何不自動修 | 歸屬 |
|---|---|---|
| **DIRTY-FIX**（closed_pnl fail-closed 測 / m4 fee JOIN fan-out / docstring 中文化） | closed_pnl/m4 8 檔是**他人未提交 WIP**，多 session 協議禁碰；審計已документ fix 方向（PA §2 P2-DIRTY-*、E3/MIT/DIRTY 報告） | 該 WIP owner，commit 前修 |
| **COST-EDGE 治理**（`cost_edge_max_ratio=100.0` 關 Root#13 + ratio 三義 + advisor 永久 B_shadow） | **政策決策**：重啟 AI 成本-edge 防守關倉閘會影響正在跑的 ADPE AI 調用；故意關閉帶 stale TODO | operator 裁是否復閘 |
| **broken cron** `daily_cost_snapshot.sh` 指向缺失腳本 | crontab 增刪=Linux runtime mutation（read-only 邊界禁） | operator |
| **sizing 嚴謹性**（dynamic_risk_sizer un-annualized Sharpe / Kelly 無 shrinkage） | sizing 數學改動屬 QC 領域決策，非機械修 | QC + operator |
| **MIGRATION-TREE-1**（virgin V001→V139 在 V023 RED：model_registry V004/V005 vs V023 衝突） | SCHEMA-1 contract test 揭露的 pre-existing migration 樹不一致；改 migration 高風險須 Linux PG dry-run+double-apply；live 不破（增量 migrate 成功）非緊急 | PA migration-hygiene 設計 |
| **AI-PRICING 殘項** F-B（Rust 硬編 stale 真名 tasks.rs:270 等）/ F-D（layer2_cost_recording fail-OPEN）/ 選項1 SSOT 合一 vs 選項2 | 超 operator named 兩檔 scope；選項1/2 架構決策 | operator 裁 + 後續 E1 |
| **PERF-1 1m timeframe** | 5m 已 gated（高價值）；1m bar 短、每 bar ticks 少、價值低 | minor follow-up |

---

## 3. 關鍵交互（profitability 相關，operator 須知）
- **ADPE × cost_gate**：parallel session 已 commit ADPE activation（`a81a6c7e` keep-explore-arms-active + explore sink）。這正是把 cost_gate 雙重扣成本從 dormant 轉 active 的觸發器（一旦 explore-gate 把 validation_passed=true 設到正 cell）。**PROFIT-1-HC 哨兵 `[90]` 已就位監測**：屆時 WARN→啟 pre-locked fix（QC 方案 A lower-CI floor）。系統設計閉環，無需現在翻 gate。
- **AUTH-1 殘留**：direct-socket bypass（持 IPC secret 直連）仍可繞，受 socket trust tier 約束（0600+HMAC=已等同 engine 級存取）；全閉需把 live authz 移進 Rust（較大改，flag operator）。

---

## 4. 建議 operator 行動
1. **commit 已驗證綠 checkpoint**（10 項，建議分 P1-safety / P1-perf / P2P3-hygiene 三個 coherent commit；fix-wave 改動與 parallel ADPE 改動 disjoint，未衝突）。**先核 AI-PRICING 價格值**再 commit 該檔。
2. 裁 deferred 政策項（COST-EDGE 復閘 / AI-PRICING 選項1vs2 / sizing）。
3. Linux：commit+push 後跑 full regression（Rust release 54-target 4665+ / Python Linux）+ SCHEMA-1 CI 首跑驗 + MIGRATION-TREE-1 PA 設計。
4. DIRTY-FIX 交 closed_pnl/m4 WIP owner 於 commit 前處理。

---

## 5. Batch 5 addendum（operator 再啟 loop 後處理 deferred 安全項）

| 項 | 結果 | 驗證 |
|---|---|---|
| **DIRTY-FIX** P2 | ✅ FIXED（增補於 14-20h stalled WIP）：m4 fan-out→LATERAL+`e.fee IS NOT NULL`、net label NULL-guard、closed_pnl fail-closed 對稱化、docstring 中文化 | QC/MIT 定聚合→E1→E2+E4；m4 116+closed_pnl 61 測 0 回歸；**owed Linux 真 fills row-count 複驗** |
| **SIZING-RIGOR** P2 | ✅ FIXED：dynamic_risk_sizer UP 路徑 Sharpe LCB+顯著性 gate（樣本不足不放大）、DOWN 不 gate；kelly Wilson 下界（只縮）。**default 嚴格只更保守** | QC 設計 go=true（只增保守）→E1→E2+E4；3846/0 +20 測；mutation-bite ×2 |
| **AI-PRICING** P2 ⚠→✅ | 值經 AI-E **對官方查證=正確**（opus-4-8 $5/$25 確認非 stale）；F-B Rust stale 真名改 config / F-D fail-OPEN→fail-closed | E2 技術 APPROVE（RETURN 僅 commit-邊界 doc 註記）+E4 PASS |
| **MIGRATION-TREE-1** P1 衍生 | ✅ DESIGN-VALIDATED（apply operator-gated）：V005 IF EXISTS wrap + V023 self-heal drop-empty-stub；scratch virgin V001→V139 GREEN+雙跑冪等+非空 legacy 仍 RAISE；揭 brief 漏的 V005 brownfield 缺陷 | PA 設計+Linux scratch 彩排（prod 未碰）；⚠ checksum drift→未來 AUTO_MIGRATE=1 前須 repair |

**Batch 5 邊界**：DIRTY 增補於他人 stalled WIP（非並發，mtime 14-20h 證）；MIGRATION 僅設計+scratch 驗證未 apply prod；全未 commit。

## 6. 剩餘全 operator-gated（無更多自主可修項）
1. **cost-edge 復閘決策**（政策；影響正在跑的 ADPE AI 調用）— 主會話已 surface 二擇一。
2. **broken cron** `daily_cost_snapshot.sh`（Linux crontab；腳本 2026-03 已佚）— operator 刪 cron 或重建。
3. **MIGRATION-TREE-1 apply** + **commit 已驗證綠 checkpoint**（含 repair_migration_checksum 前置）。
4. **AI-PRICING 選項1 SSOT 合一**（架構決策）；**DIRTY-FIX commit** 須 closed_pnl/m4 WIP owner sign-off。
5. PERF-1 1m timeframe（minor follow-up）。

**fix-wave 最終自評**：confirmed **13 項修/驗** + MIGRATION 設計驗證 + PROFIT-1 NO-FIX 裁決；deferred 全為真 operator/政策/Linux/architecture 決策（非偷懶分流）；全程 0 commit/0 部署/0 runtime mutation；他人 WIP 僅在確認 14-20h stalled 後 surgical 增補（非並發 clobber）；E2/E4 全鏈未跳（auth+E3、sizing+QC、migration+scratch dry-run）；survival-first 一以貫之（PROFIT-1 不翻 / sizing 只更保守 / fail-closed 全程不弱化 / migration 不 apply prod）。pricing ⚠ 經官方查證解除。
