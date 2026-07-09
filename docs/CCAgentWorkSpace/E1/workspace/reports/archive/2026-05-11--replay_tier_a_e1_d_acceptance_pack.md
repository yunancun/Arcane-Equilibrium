# E1-D — P0 Replay Tier A T6 acceptance test pack IMPL DONE（2026-05-11）

**Owner**：E1-D
**Trigger**：PA Tier A `2026-05-11--p0_replay_engine_counterfactual_fix_design.md` §3.3 T6 + §3.4；operator 拍板 ship；E1-A (`ffc57d7f`) + E1-B (`7f6182b2`) + E1-C (`a17ff37a`) 已 land。
**Scope**：T6 acceptance test pack — 新檔 `tests/replay_tier_a_acceptance.rs` 集中 6 個 test 驗 T1+T2+T2.5+T3+T4+T5 五個 land 後的 wire-up 鏈
**Branch**：main HEAD `77046b62`（E1-C land）→ 本次新檔 unstaged，待 PM 統一 commit + push
**16 原則合規**：16/16；**§四 5 硬邊界觸碰**：0；**forbidden_guard 違反**：0

---

## 1 任務摘要

按 PA Tier A §3.3 T6 + §3.4 E1-D 派發 acceptance test pack：驗證 T1（is_pinned wire）+ T2（position_state wire）+ T2.5（owner_strategy）+ T3（scanner_config echo）+ T4（strategy_params echo）+ T5（per-symbol price anchor）五個 sub-task 在 land 後對 IsolatedPipeline 行為產生可觀測差異，覆蓋 3 個 production-aligned 場景 + 3 個 unit 邊界。

選擇將 6 個 test 集中於新檔 `tests/replay_tier_a_acceptance.rs`（PA spec 允許「`tests/replay_counterfactual_tier_a.rs` 新檔 + 既有 `runner_tests.rs` 加 3 test」，集中放可讀性 > 分散）。1 新檔；686 LOC（< 800 警告線、< 2000 hard cap）。

---

## 2 修改清單

| 檔 | 變動 | LOC |
|---|---|---|
| `rust/openclaw_engine/tests/replay_tier_a_acceptance.rs`（新檔） | 6 acceptance test + 2 stub Strategy impl + 4 fixture helper | +686 |

**Total**：+686 LOC（PA estimate ~40 LOC test — 我們最終 686 LOC 含 helpers + 6 inline-stub Strategy impl + 詳細中文注釋，仍 < 800 警告線）。

---

## 3 6 個 acceptance test

### Integration（IsolatedPipeline + adapter pipeline）

1. **`test_replay_pinned_tier_excludes_dynamic_add_symbols`**（T1 wire 整合）
   - Setup：3 tick BTCUSDT/HYPEUSDT/WLDUSDT；scanner_timeline cycle active=[BTC, HYPE]
   - Assertion：WLDUSDT 不在 active 又無倉 → timeline skip → 不出現在 decision_trace；BTC 出現
   - 對齊 **Option 2 SCANNER-PINNED-GATE-1**（PA §3.1 acceptance 第 1 點）

2. **`test_replay_cross_strategy_position_blocks_secondary_open`**（T2 + T2.5）
   - Setup：2 tick BTCUSDT；ma_crossover first-tick emit Open
   - Assertion：first-tick fill (qty>0, fill_status=filled/partial) → paper_snapshot 內存 owner_strategy="ma_crossover" 倉位；second-tick ContextObserver first-tick-emit-once 不再 emit → fills.count=1
   - 對齊 **Phase 0 + A-Lite cross-strategy 防禦**（PA §3.1 acceptance 第 2 點）

3. **`test_replay_uses_production_strategy_params`**（T4 整合 via factory）
   - Setup：baseline `StrategyParamsConfig::default()` vs candidate `bb_reversion.min_persistence_ms=120000`
   - Assertion：兩條 factory path 都通 `StrategyFactory::create_with_params` 接受；兩 pipeline `status=Completed`
   - 對齊 **P2 demo TOML commit 27e86f89** + T4 manifest.strategy_params echo 鏈

### Unit（ReplayPaperSnapshot helper / lifecycle / timeline API）

4. **`test_per_symbol_price_anchor_independence`**（T5 unit）
   - Setup：3 sym 預種 BTC=50000 / ETH=3000 / SOL=200；fallback latest_price=Some(0.2717) 模擬污染
   - Assertion：`latest_price_for(BTC/ETH/SOL)` 取真值不退；unmapped ADA 退 fallback 0.2717；全空 → None
   - 對齊 **PA §2.6 Kelly ETH 3 億 fix**

5. **`test_position_state_lifecycle_tracked_in_replay`**（T2 unit）
   - Setup：OpenThenCloseStub first-tick Open + second-tick Close BTCUSDT
   - Assertion：≥2 BTC fills（open + close）；ending_balance 與 starting_balance 差異於合理 fee 範圍
   - 對齊 production PaperPosition lifecycle 鏡射

6. **`test_scanner_config_parsed_into_pinned_set`**（T3 unit via scanner_timeline）
   - Setup：`from_scan_results` 注入 cycle pinned=[BTC,ETH] + active=[BTC,ETH,SOL]，scan_ts_ms=1000
   - Assertion：is_active_at 對 pinned/dynamic/未列入 3 類 + lowercase 正規化 + pre-cycle ts_ms<scan_ts → false 全部正確
   - 對齊 T3 manifest.scanner_config echo 後 Rust deserialise 路徑

---

## 4 治理對照

| 規範 | 對齊 |
|---|---|
| CLAUDE.md §一 玄衡定位 | ✅ replay isolated subprocess |
| §二 16 原則 | ✅ 16/16（特別 #8 交易可解釋 — acceptance test 驗 decision_trace + fills 可重建） |
| §四 硬邊界 5 條 | ✅ 0 觸碰（live_execution / lease emit / max_retries / OPENCLAW_ALLOW_MAINNET / live_reserved） |
| §五 架構總覽 | ✅ replay subprocess，不動 main pipeline |
| §七 跨平台 | ✅ 0 硬編碼路徑（grep `/home/ncyu` `/Users/[a-z]+` 0 hit） |
| §七 注釋（2026-05-05 中文默認） | ✅ MODULE_NOTE + 全部 inline 注釋中文 |
| §七 SQL migration | N/A |
| §八 工作流 | ✅ E1-D IMPL → E2 review → E4 regression → PM commit |
| §九 文件大小 2000 | ✅ replay_tier_a_acceptance.rs **686 LOC** < 800 警告線 < 2000 hard cap |
| forbidden_guard / V3 §6.2 | ✅ 6 test 全於 IsolatedPipeline / ReplayPaperSnapshot / ReplayScannerTimeline 內，0 forbidden surface |
| V3 §12 #10/#11/#14 | ✅ pre-existing proof_1/4/5 + R5-T7 proof_7/8 全保 PASS |

---

## 5 forbidden_guard / V3 §6.2 對齊驗證

### 5.1 7 條 forbidden surface 檢查

| Surface | T6 test pack 觸碰? |
|---|---|
| Decision Lease acquire/release | not touched |
| IPC server start | not touched |
| WS client start | not touched |
| Exchange dispatch | not touched |
| DB writer channel use | not touched |
| Live/demo config mutate | not touched |
| Advisory write outside PL/pgSQL | not touched |

T6 純整合測：構造 ReplayPaperSnapshot / 注入 ReplayScannerTimeline / 跑 IsolatedPipeline + ContextObserver stub strategy。引用面：
- `openclaw_engine::replay::{fixture_loader, profile, risk_adapter, runner, scanner_timeline, strategy_adapter}`（replay-pure 既綠路徑）
- `openclaw_engine::scanner::types::ScanResult`（純 data struct）
- `openclaw_engine::strategies::{Strategy, StrategyAction, StrategyFactory, StrategyParamsConfig}`（factory 是 pure constructor，無 mutate side）
- `openclaw_engine::intent_processor::OrderIntent`（純 structural type，PA §5 既綠）
- `openclaw_core::{guardian::GuardianConfig, alpha_surface}`（既綠路徑）

### 5.2 cargo test 驗證鏈

```
$ cargo build --release -p openclaw_engine --test replay_tier_a_acceptance --features replay_isolated --no-run  → PASS
$ cargo test --release -p openclaw_engine --test replay_tier_a_acceptance --features replay_isolated           → 6/6 PASS (0.00s)

$ cargo test --release -p openclaw_engine --lib                                                                  → 2807 passed (baseline 維持，acceptance test 在 --test 不在 --lib count)
$ cargo test --release -p openclaw_engine --test replay_runner_e2e --features replay_isolated                  → 6/6 PASS (incl proof_1/4/5 byte-equal)
$ cargo test --release -p openclaw_engine --test replay_runner_e2e_param_delta --features replay_isolated      → 2/2 PASS (R5-T7 xlang proof_7/8)
$ cargo test --release -p openclaw_engine --test replay_forbidden_guard_acceptance --features replay_isolated  → 4/4 PASS
$ cargo test --release -p openclaw_engine --test replay_profile_acceptance --features replay_isolated          → 5/5 PASS
$ cargo test --release -p openclaw_engine --test replay_mac_policy_acceptance --features replay_isolated       → 4/4 PASS
$ cargo test --release -p openclaw_engine --test replay_manifest_signer_xlang_consistency --features replay_isolated → 8/8 PASS
```

**Baseline**：E1-C land 後 2807 lib + replay-specific 6+2+4+5+4+8 = 29 → **Post-E1-D**：2807 lib（不變）+ **6 acceptance test 新加** + 29 既有 replay regression 維持 PASS；0 regression。

---

## 6 PA §3.5 E2 重點審查 3 點對齊

PA spec §3.5 列了 E2 review 3 點重點。T6 acceptance test 部分對齊：

1. **PaperPosition stack-local borrow lifetime（PA §3.5 #1）** — 本 E1-D test 不重做 E1-A 已驗證的 borrow checker 路徑；test 2 + test 5 在 IsolatedPipeline 內部隱式驗證（builder 透過 build_replay_position_borrow 對應 ctx.position_state，per-iteration NLL 自然釋放）。**E2 重點仍在 E1-A 範圍**。
2. **TOML→JSON byte-equal（PA §3.5 #2）** — 本 E1-D test 不涉 Python tomllib → Rust serde 路徑；test 6 用 `from_scan_results` 直接 inject 構造好的 ScanResult，bypass TOML 解析。**E2 重點仍在 E1-B 範圍**。
3. **per-symbol anchor backward compat（PA §3.5 #3）** — test 4 直接驗 `latest_price_for(symbol)` fallback chain 三場景；fallback 至全域 latest_price 路徑 PASS，per-symbol vs 全域優先順序 PASS。**T5 backward-compat 不變式由本 test 守住**。

---

## 7 不確定之處 + Operator 決定點

1. **test 3 用 factory propagation 而非 Strategy field accessor 是 trade-off**：Strategy trait 沒 public field accessor 供 test 直接讀 `bb_reversion.min_persistence_ms`；test 用「factory accept candidate config + pipeline run 完成」作為等價證據。若 operator / E2 認為應加 trait method `get_strategy_params_snapshot()` 給 test 直接讀，需 trait 改動（不在本 E1-D 範圍）。

2. **test 2 cross-strategy guard 在 replay 內非「真實 fail-closed」**：production 是 strategy module 內部讀 `ctx.position_state.owner_strategy` 自決定不 emit；replay test 用 ContextObserver first-tick-emit-once 控制 stub 邏輯。**這對齊 replay 「驗 wiring，不驗 strategy 內邏輯」的設計邊界** — 真實 fail-closed 路徑由 production strategy unit test 守。E2 spot-check 此 framing 是否合理。

3. **test 1 WLDUSDT skip 路徑驗證為 `scanner_timeline_skipped_events ≥ 1`**：因 WLD 既無倉位又不在 active → `should_skip_for_scanner_timeline` 返回 true → skip event。此 indirect 證據 sufficient；direct 證據是 strategy.observations.iter().filter(WLD).count() == 0 但 ContextObserver consumed-by-pipeline 不可取出。

4. **memory.md 累積大小**：E1 memory.md 已 ~1MB，整檔 Read 超 256KB limit。後續 sub-agent 啟動可能要 selective offset/limit Read 或 PM 介入 memory archive。

---

## 8 Operator 下一步

1. 派 **E2 review**（per PA §3.5 對 E1-A/B/C 已派；E1-D 主要驗 acceptance test 是否真實覆蓋 sub-task wire-up）：
   - 確認 6 test 對應 T1-T5 sub-task 充分（test 2 ContextObserver 等價證據是否 sufficient）
   - 確認 test 中 ContextObserver / OpenThenCloseStub inline-Strategy impl 不洩 forbidden surface
   - nm symbol audit（Mac strip + Linux 重跑確認無 paper_state mutator symbol 漏入 acceptance test 編譯產物）
2. 派 **E4 regression**：跑 R5-T7 cross-language parameter delta + proof_1/4/5 byte-equal + 新 acceptance 6/6（local 已過，Linux 端再驗）
3. Tier A 至此 IMPL chain DONE（E1-A → E1-B → E1-C → E1-D 全 land）；等 E2 + E4 sign-off → PM bundle commit + push + 三端 rebuild + 跑真實 replay 驗 27h 數據
4. 跑 Tier A acceptance（PA §3.1）：Option 2 ON/OFF + Phase 0 ON/OFF + A-Lite 4-combo replay 量化 PnL delta

---

## 9 完成序列

- [x] PA spec 讀完（§3.3 T6 + §3.4 + §3.1 acceptance criteria）
- [x] E1-A / E1-B / E1-C 三 report 讀完（確認 IMPL 真實 land 範圍 + API surface）
- [x] 6 acceptance test IMPL（3 integration + 3 unit）
- [x] cargo build --test replay_tier_a_acceptance --features replay_isolated PASS
- [x] cargo test --test replay_tier_a_acceptance 6/6 PASS
- [x] cargo test --lib：baseline 2807 不變；0 regression
- [x] replay regression 全 PASS：runner_e2e 6/6 + param_delta 2/2 + forbidden_guard 4/4 + profile 5/5 + mac_policy 4/4 + xlang signer 8/8
- [x] forbidden_guard / V3 §6.2 0 violation；§四 5 硬邊界 0 觸碰
- [x] 跨平台 grep `/home/ncyu` / `/Users/[a-z]+` 0 hit
- [x] §九 2000 LOC cap 全綠（686 < 800 < 2000）
- [x] IMPL DONE report 寫
- [x] E1 memory entry 追加
- [ ] E2 review（pending）
- [ ] E4 regression Linux 端再驗（pending）
- [ ] PM 統一 commit + push（pending E2 + E4 sign-off）

---

E1-D IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--replay_tier_a_e1_d_acceptance_pack.md`）
