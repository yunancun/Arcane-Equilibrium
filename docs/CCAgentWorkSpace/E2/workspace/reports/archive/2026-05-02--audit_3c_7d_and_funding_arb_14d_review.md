# E2 PR Adversarial Review — `audit/2026-05-09-and-16-3c-funding-arb-followup` @ 5abb00e · 2026-05-02

## Branch / Commits
- `2d67c95 feat(audit): add 2026-05-09 3C 7d + 2026-05-16 funding_arb 14d audit scripts`
- `5abb00e docs(todo): add 2026-05-09 + 2026-05-16 audit reminder section`

## 改動範圍（diff stats）
```
TODO.md                                              |  10 +
helper_scripts/db/audit/2026-05-09_3c_7d_audit.py    | 793 +++++++++
helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh    |  69 ++
helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py | 463 ++++++
helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh |  67 ++
5 files changed, 1402 insertions(+)
```
- 純 read-only audit script + TODO 排程提醒
- 不觸 Rust / migration / risk_config / healthcheck / API
- 不觸 P0 修復路徑（V028-V034 sqlx hash drift）

## E1 Hint 結論

### Hint #2（net_bps 公式 double-count）— FALSE ALARM
- 1A audit Metric 1 用 `learning.mlde_edge_training_rows.net_bps_after_fee`（pre-computed），與 healthcheck `[40]` 同源同 column
- 無 `(SUM(realized_pnl) - SUM(fee)) / SUM(notional) × 10000` 公式存在
- E1 描述場景在 commit 中不存在
- Funding_arb 14d audit 用 `realized_pnl - entry_fee - close_fee` 計 net，經 Rust `paper_state/fill_engine.rs:300-306` 驗證 `realized_pnl = (fill_price - entry_price) * close_qty` **純 gross**，公式正確

### Hint #1（partial fill row_number()=1）— OK
- 與 healthcheck `[38] check_grid_trading_lifecycle_drift` 完全一致 pairing 樣式
- V017 entry_context_id JOIN + first close per partition (rn=1) 取樣
- 已知 limitation：subsequent partial close 不計入；monitor scope choice，非 bug

### `trade_executions` vs `trading.fills`
- V005:449: `CREATE OR REPLACE VIEW public.trade_executions AS SELECT … FROM trading.fills`
- Audit 直讀 `trading.fills` 等價且更直白；無問題

## 8 條 §九 Checklist
| Item | 狀態 | 備註 |
|---|---|---|
| 改動範圍 vs PA 方案 | PASS | |
| 無 except:pass | PASS | |
| log %s 非 f-string | N/A | 無 logging.* |
| _require_operator_role | N/A | 非 API |
| HTTPException order | N/A | |
| detail=str(e) | N/A | |
| asyncio + threading.Lock | N/A | 同步腳本 |
| 私有屬性穿透 | ACCEPT | `passive_wait_healthcheck.db._get_conn` underscore 命名但模組級 helper，已被全 healthcheck 系列重用，等同公共 API |

## 9 條 OpenClaw Checklist
| Item | 狀態 | 備註 |
|---|---|---|
| 跨平台 grep `/home/ncyu` `/Users/` | PASS | 0 命中 |
| 雙語 MODULE_NOTE + docstring | PASS | 兩 .py 頂 + 主函數均有 |
| Rust unsafe / unwrap / panic | N/A | |
| IPC schema | N/A | |
| Migration Guard A/B/C | N/A | |
| Healthcheck 配對 | OBSERVATION | 「📅 排程提醒」屬事件驅動 cutoff trigger（非「被動等待 Nd」passive-wait），§七 healthcheck-pair 嚴格不適用；建議 audit script 跑前可呼叫 `passive_wait_healthcheck.sh --quick` 驗 baseline pipeline 仍活著（LOW finding） |
| Singleton 登記 | N/A | |
| 文件大小 800/1500 | OBSERVATION | 793 行接近 800 警告線；建議下次 split metric 1-5 |
| Bybit API | N/A | |

## 對抗反問

1. **Q: `trading.fills.realized_pnl` 是 gross 還是 net？**
   A: Rust `fill_engine.rs:300-306` `pnl = (fill_price - entry_price) * close_qty`；fee 從 `self.balance -= fee` 另算。**Pure gross**。Funding_arb audit 用 `pnl - entry_fee - close_fee` 算 net 公式正確；3C audit 用 `net_bps_after_fee` precomputed column 與 [40] 同源也正確。

2. **Q: row_number()=1 partial close 漏 pnl？**
   A: 與 [38] 一致 pairing 取樣；monitor scope 共識；非 bug。

3. **Q: DEPLOY_UTC = 17:42 UTC 來源？**
   A: commit `a19797d` ts 為 `2026-05-02 17:20:35 +0200` = `15:20 UTC`。Audit 硬編 17:42 UTC（19:42 CEST）差 ~2.4h；E1 必須提供 restart_all log 證據或改 cutoff 時刻。**真實 risk，MEDIUM finding**。

4. **Q: dead `net_pnl` 變數是 leftover 還是 intentional？**
   A: line 247 inline 英文注釋「already net of fee」與緊接後中英 NOTE block 直接矛盾；E1 在 dev 時 semantics 改變但忘刪舊行；leftover dead code + misleading comment。**MEDIUM finding**。

## Findings

| 嚴重性 | 位置 | 描述 | 建議修法 |
|---|---|---|---|
| **MEDIUM** | `2026-05-16_funding_arb_14d_audit.py:247` | `net_pnl = stats.gross_bps_sum - 0.0   # gross_pnl already net of fee in fills.realized_pnl` — dead var + 英文 inline 注釋與緊接後中英 NOTE block + Rust source-of-truth **直接矛盾**。下個接手 reader 會誤判 fee semantics。 | 刪除 line 247 整行；保留 line 248-254（正確中英 NOTE + `net_after_fee = stats.gross_bps_sum - stats.fee_sum` 真實計算） |
| **MEDIUM** | `2026-05-09_3c_7d_audit.py:67` | `DEPLOY_UTC = "2026-05-02 17:42:00+00"` 缺證。3C TOML commit ts 為 15:20 UTC，差 ~2.4h；restart_all log 未驗。Window 偏移可能洩漏 ~2h pre-deploy 樣本進 post，扭曲所有 5 metric delta | E1 提供 `journalctl --since "2026-05-02 14:00" -u openclaw-engine \| grep "engine.*start"` 證據；或改 cutoff 18:00 UTC 整點 + disclaimer ±N min uncertainty |
| **LOW** | 兩 .py SL cap section | partial-close notional bias：`abs(pnl)/entry_notional` 在 partial close 時偏高（entry_notional 用 close_qty × entry_price 而非 entry_qty × entry_price），FAIL 偏多。E1 自陳「conservative bias 可接受」 | 報告 output 加一行 disclaimer：「Note: SL cap pct uses close_qty × entry_price; partial-close fills may inflate ratio (over-flag)」 |
| **LOW** | 兩 .sh wrapper prologue | 「📅 排程提醒」屬事件 cutoff，非 passive-wait；但跑前無 healthcheck 預檢，若 baseline pipeline 已死會錯把「沒 fire」當「3C 改進」 | 可選：wrapper 開頭加 `bash helper_scripts/db/passive_wait_healthcheck.sh --quick` 預檢；E1 不改也接受 |

## 結論

**RETURN to E1**（2 個 MEDIUM 待修；2 個 LOW 可選）

## 退回 E1 修復清單

1. **`2026-05-16_funding_arb_14d_audit.py:247`** — 刪除整行 dead `net_pnl = stats.gross_bps_sum - 0.0   # gross_pnl already net of fee in fills.realized_pnl`。
2. **`2026-05-09_3c_7d_audit.py:67` DEPLOY_UTC** — 提供 17:42 UTC 來源證據；或改用 commit ts 15:20:35 UTC + buffer；或選 18:00 UTC 整點 + 報告 disclaimer。
3.（LOW，可選）兩 audit 報告 output 加 SL cap partial-close bias disclaimer。
4.（LOW，可選）兩 .sh wrapper prologue 加 healthcheck `--quick` 預檢 hint。

修完重 E2，通過後可進 E4（純 read-only audit script，E4 只需 syntax + import smoke + DRY-RUN，不需 runtime trading-loop 驗證）。
