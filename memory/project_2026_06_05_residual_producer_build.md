---
name: project_2026_06_05_residual_producer_build
description: residual alpha producer 三件套(compute assembler+signal_spec+hidden_oos sealer)+殘差 gate end-to-end 建成並部署；PART1-3 flag-on cron daily 03:17，PART4 gap-closure flag-OFF；誠實結果=fail-closed defer 閘，單配置 demo 一律 defer，非吐-alpha
metadata: 
  node_type: memory
  type: project
  originSessionId: 02609da3-dfb2-4b95-913a-0f995648f446
---

# Residual alpha producer 建構 + 部署 (2026-06-05~09)

承 [[project_2026_06_04_external_framework_audit_and_self_audit]]。命門：Codex 建了 fail-closed evidence 格架（SignalSpec / EvidenceManifest / Hidden-OOS-sealed / residual gate / promotion validators）**但三個 evidence artifact 全無 producer → 整套 inert、對真候選 100% fail-close**。本線把 producer end-to-end 補完並部署。

## 耐久成果
- **PART 1-3（compute assembler + signal_spec producer + hidden_oos sealer + replay 註冊接線 + mlde hook）已於 2026-06-07 隨 main 全量 rebuild+restart 部署**，flag-on：`OPENCLAW_RESIDUAL_ALPHA_PRODUCER=1` 寫進 crontab（cron daily 03:17 UTC），首輪 attach 7/7 無 fail-soft。flag 至今仍存在於 production code（`ml_training/mlde_shadow_advisor.py`、cron template 等，2026-07 驗）。
- **PART 4 gap-closure（多因子 btc/market/funding-carry residualization + sign-flip permutation + `residual_stage0r_preflight.py` orchestrator）於 2026-06-08 部署 flag-OFF**（triple-OFF inert）；末項修 multi-factor basket 選流動 symbol（非字母序）。真實活化＝operator 決策（set `OPENCLAW_RESIDUAL_STAGE0R_PREFLIGHT=1` + 加 cron job + 活化前 Linux flag-ON 真寫一輪驗）。
- 關鍵 SHA：signal_spec attach `598ed5d4` → mlde hook `627b4772` → PART2 replay-bridge `d5ec22d5` → full rebuild+migration `8cd4da1f` → PART4 `14e94532` → multi-factor basket fix `6c1b015f`。

## 誠實狀態（不變、耐久）
producer 讓晉升閘**可信、會誠實 defer**；**現單配置 demo（無參數變體、N_eff 低）→ PBO 不適用 → 正確數學一律 defer**（舊壞公式才假性放行）。**非吐-alpha 機器；真 alpha 仍須他處來。** 對照 2026-06-04 P0 裁定：beta-masquerade veto 閘正確、fail-closed、拓樸無 bypass，但 runtime 上因 evidence 從未產出，**從未對真候選用殘差數學做過一次 PASS/FAIL**——安全（不誤放），尚非設計意圖的 deciding factor（PART 4 後閘接好會 RUN 殘差/DSR/beta/permutation，但單配置仍誠實 defer；genuine PBO 需 A-full Rust variant replay=未建）。

## 教訓（耐久）
- 對抗審查抓到我真 bug 並修不辯護：MIT CRITICAL duration-blind embargo leak（→非重疊 4h bucket 按 exit 歸桶）/ QC HIGH round-trip 重疊非 i.i.d. / **QC BLOCKING gate 三統計手搓錯**（_normal_approx_psr / _deflated_psr / 非CSCV pbo → 改呼倉內 vetted `dsr_gate` / `pbo_gate`）；審自己用審 Codex 同把尺。
- **MIT Linux-empirical 是必要的**：PG jsonb `-0.0→0.0` drop（registry hash pre-jsonb vs source_contract post-jsonb 不一致→閘破）+ net_side strategy-wide 非 per-symbol（funding sign 反→放大 carry=false-promote 向量）兩個真 prod-breaker，Mac pure-core 抓不到。
- **synthetic 測試過 ≠ 真資料能算**：multi-factor basket 字母序選到零-kline 冷門 symbol → 真資料上永遠 `no_aligned_buckets`；DB-selection 路徑須 read-only 真 PG eval（no-op register_fn＝零寫入跑真計算的好工具）。修後真驗：grid_trading::BTCUSDT raw −13.70bps、**扣 funding beta 後 residual +12.44bps**（grid 的虧主因 carry 曝險非純負 alpha）。
- cron 的「env」是 crontab inline 非 env file（wrapper/restart 只 grep allowlist）；別讓兩個 mutation-probe agent（E2+MIT）並行同 worktree（edit/revert race）；別偽造 PBO peers（invalid CSCV=theater）。

## 演變軌跡 / point-in-time
- 部署當時查 runtime `_sqlx_migrations` head=130，V131(drar)/V132(hos)/V133 隨此次 rebuild 套用到 133——**皆當時點狀態；2026-07 起 migration head 已推進到 150**（V141-150 陸續落地）。
- evidence-foundation 這條線的**當前領先者已是 AI/ML roadmap WP1-WP3（PIT manifest / ProofPacket，2026-07-05+）**；本檔的殘差 evidence 鏈是其前身。

---

## [index-archive 2026-06-10] 原 MEMORY.md 索引條目全文(壓縮索引前歸檔,內容為當時點狀態；「剩餘未完成」claim 已被上方耐久成果取代)

- [Residual alpha producer 完整建構 (2026-06-05)](project_2026_06_05_residual_producer_build.md) — 接手 Codex 命門缺口（evidence 格架建好但**三 artifact 全無 producer→inert**），把 **residual producer** end-to-end 建成於 **`feature/residual-producer`**（worktree `/private/tmp/wt-residual-producer`，off main@4b97d344，**5 commit 6cc06005/e4bfd54e/f8ed11f0/5545d712/0aa88c64，未 push/未部署**）。對抗審查抓到我**真 bug**並修：MIT CRITICAL duration-blind embargo leak（→改非重疊 4h bucket 按 exit 歸桶）、QC HIGH 重疊非 i.i.d.、**QC BLOCKING gate 三統計手搓錯**（_normal_approx_psr/_deflated_psr/非CSCV pbo→改呼叫倉內 vetted dsr_gate/pbo_gate，E1 實作+E2 ACCEPT，Sharpe convention 親驗 per-period 對）。R-2b orchestrator（變體 peers+n_trials K≥10+單配置診斷 defer）+R-3 attach primitive（env-flag OPENCLAW_RESIDUAL_ALPHA_PRODUCER OFF）。79 測試綠。**誠實：讓閘可信會誠實 defer，現單配置 demo 一律 defer（QC 對的），非吐-alpha**。**剩餘已驗未完成：signal_spec producer（只 validator/pass-through 無構造）、hidden_oos sealer（零 state='sealed' 寫入）、mlde hook（attach_residual_reports 零 caller）+ deploy**。承 [[project_2026_06_04_external_framework_audit_and_self_audit]]
</content>
