# E4 Workspace Report — LG-5 W3 IMPL-3 + risk_config_demo TOML Linux Regression

- Date: 2026-05-02
- Commit (Linux + Mac + origin): `a51cdc5`
- Two streams folded:
  - Stream A — LG-5 Wave 3 IMPL-3 (Mac dispatch)
  - Stream B — Linux operator risk_config_demo TOML promote + Rust G2-03 sibling test extract

## Verdict

**PASS — ready for PM Sign-off**

## Suite-by-suite

| Suite | passed | failed | baseline | delta |
|---|---|---|---|---|
| Cargo lib (`--lib`) | 2405 | 0 | ≥2404 | +1 ✓ |
| Cargo aggregate (`--tests`) | 2561 | 0 | ≥2560 | ✓ |
| g2_03_per_strategy runtime (Stream B) | 8 | 0 | new | +8 |
| `test_demo_toml_funding_arb_3pct_override_2026_05_02` (Stream B) | 1 | 0 | new | +1 |
| Pytest test_lg5_healthchecks (Stream A new) | 13 | 0 | new | +13 |
| Pytest helper_scripts/db (full) | 100 | 0 | 87 | +13 ✓ |
| Pytest control_api_v1 (excl integration) | 3306 | 1 pre-existing grafana | 3306 | +0 (skipped 3) |
| Pytest IMPL-1 + IMPL-2 regression | 59 | 0 | 59 | ✓ |
| `audit_migrations.py` V035 | OK | — | — | no drift |
| Runner: [42] + [42b] verdict emitted | ✓ | (production FAIL by design) | new wire-up | ✓ |
| 2nd run W3 + g2_03 | identical | 0 | — | no flake |

## Stream A vs Stream B 隔離

互不耦合 — Stream A Python healthchecks 不依賴 Stream B Rust risk_checks 改動；測試結果無交叉污染；commit `a51cdc5` merge 後同框入庫，但 LOC region 完全分離。

## Mock 審查（Stream A W3）

`test_lg5_healthchecks.py` 13 tests 用 `Mock` 對 `_get_conn` 注入測試資料。業務邏輯（4 boundary verdict 計算、ratio 彙總、SQL fragment）真跑於 mock conn 之上，未 mock 業務邏輯本身。OK。

## Production runner 真實 verdict (Step 9/10)

兩 newly wired healthcheck 立即在 production fire 真實 FAIL signal，**屬 healthcheck 履行設計目的，非 W3 code 問題**：

### `[42] live_candidate_eval_contract` = FAIL
```
recent_24h_total=8, unaudited_over_1h=27 — review_live_candidate contract broken;
check GovernanceHub.review_live_candidate consumer health
(RFC v2 §4 lease_revoke_trigger fires)
```

### `[42b] live_candidate_attribution_drift` = FAIL
```
7d per-strategy attribution_chain_ok ratio:
  grid_trading=0.135(n=1277)   ← worst, FAIL (<0.30 floor)
  ma_crossover=0.152(n=871)
  bb_breakout=0.500(n=30)
  bb_reversion=0.333(n=6)
  funding_arb=0.433(n=67)
worst=grid_trading@0.135 — investigate producer (MIT-S2-1 attribution_chain_ok writer)
```

## PM 建議

1. **Promote PASS** — 此 regression 不阻擋；W3 healthcheck 已正確 wire-up 並履行職責
2. **新建 G6 follow-up tickets**（HIGH 優先級）：
   - `LG5-W3-FUP-1`：修復 `GovernanceHub.review_live_candidate` consumer（治理 stale 致 [42] FAIL）
   - `LG5-W3-FUP-2`：補 `MIT-S2-1 attribution_chain_ok` writer producer（grid_trading 1277 rows 86.5% 漏寫致 [42b] FAIL）
3. **無需 commit**：merge `a51cdc5` 已存 origin；Mac/Linux 均 sync。

## 反模式檢查

- [x] 沒刪測試使測試通過
- [x] 沒改 assertion value 而非修代碼
- [x] mock 審查（W3 tests 只 mock IO，業務邏輯真跑）
- [x] 二跑驗證無 flake
- [x] failed 數無增加
- [x] PG password 未 echo 至報告

## 結束

**E4 REGRESSION DONE: PASS** · primary report: `srv/.claude_reports/20260502_e4_lg5_w3_impl3_plus_risk_toml_linux_regression.md`
