# W1 spec v1 → v1.1 BB WS-first revision report

**Author**: PA
**Date**: 2026-05-10
**Trigger**: BB W1+W2 rate budget review `2026-05-10--w1_w2_bybit_v5_rate_budget_review.md` §6 HIGH push back 採納
**Spec edit**: `srv/docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md` v1 → v1.1
**Pre-condition**: PA D+0 trait skeleton HEAD `c9fb0b8f` 已 land；W1 spec v1 採 REST polling 100 req/min；BB review 揭露 WS topic 已 broadcast 所需 field

## 1. WS-first revision summary（spec section 改動）

| Section | v1 | v1.1 |
|---|---|---|
| §1.1 Background | Python writer pulls Bybit V5 endpoint → 寫 PG | Rust `panel_aggregator` 訂閱 WS broadcast Ticker events → 60s flush PG + slot 雙寫 |
| §1.2 Scope | 3 子任務 producer = Python writer + slot puller | E1-α leader = Rust aggregator + event channel mpsc→broadcast migration；E1-β/γ rebase parallel |
| §2.1 funding source | REST `/v5/market/tickers` 25 req/min (4.2%) | WS `tickers.{sym}` broadcast (0 ongoing) + funding 不需 cold-start backfill |
| §2.3 funding producer | Python `funding_curve_writer.py` httpx polling loop | Rust `panel_aggregator/funding_curve.rs` broadcast subscriber + 60s flush |
| §2.4 slot 寫入機制 | `panel_puller.rs` 從 PG round-trip 拉 → 寫 slot | aggregator 直接 write slot（PG 雙寫保留作 audit / ML / healthcheck）|
| §2.5 freshness | 30s WARN / 300s FAIL；puller stale 寫 None | aggregator buffer 5s WS-tick threshold + flush 全 stale → slot None；PG 30s/300s 寬鬆 |
| §3.1 OI source | REST `/v5/market/open-interest` 75 req/min (12.5%) 三 interval | WS broadcast oi_abs (0 ongoing) + cold-start REST batch 75 req once + aggregator 1h sliding window 算 5m/15m/1h delta |
| §3.3 OI producer | Python `oi_delta_panel_writer.py` 三 interval 並行拉 | Rust `panel_aggregator/oi_delta.rs` broadcast subscriber + sliding window |
| §5 BB rate review | TODO BB B-3 deliverable D+1 integrate | DONE — BB report 採納 → v1.1 設計 |
| §6 sub-agent dispatch | 3 E1 完全並行 | E1-α leader (event channel migration gating) → E1-β/γ rebase parallel |
| §7.5 risk | rate budget 中、puller stale 中 | rate budget 解除；新增 event channel migration silent break **極高** + WS reconnect gap stale 中 + OI rolling delta vs Bybit 5m close-bar 偏差 中 |

## 2. 既有 WS subscription pattern 對齊（reuse 哪個 connection / 加哪個 topic）

**Reuse 既有 WS public connection**：
- `srv/rust/openclaw_engine/src/main_ws.rs:47-66` — `enable_extended_ws=true` 預設（per `config/mod.rs:144,208`）
- `srv/rust/openclaw_engine/src/multi_interval_topics.rs:128-147` — `full_subscription_list()` 25 sym × 10 topics (kline.1/3/5/15/60/D + tickers + orderbook.50 + publicTrade)
- 既有 25 sym × tickers topic = 25 已訂閱，**0 額外 connection / topic 新加**

**Reuse 既有 parser**：
- `srv/rust/openclaw_engine/src/ws_client/dispatch.rs:111-114` — `topic.starts_with("tickers.")` route to `parse_ticker_item`
- `srv/rust/openclaw_engine/src/ws_client/parsers.rs:225-263` — `parse_ticker_item()` 已 extract `fundingRate` + `openInterest` → `PriceEvent.funding_rate / open_interest`
- **W1 IMPL 必加** `PriceEvent.next_funding_ms: Option<i64>` field + parsers.rs 加 `nextFundingTime` extract（`event.next_funding_ms = item.get("nextFundingTime").and_then(|v| v.as_str()).and_then(|s| s.parse::<i64>().ok())`）

**新加 broadcast subscriber**：
- `main.rs` 既有 `event_tx: mpsc::Sender<PriceEvent>` 改成 `tokio::sync::broadcast::Sender<PriceEvent>` capacity 2048
- `panel_aggregator` task 拿 `event_rx.resubscribe()` 一個 receiver，filter `event_kind == Some(Ticker)` + `cohort.contains(symbol)` → 寫 buffer

## 3. REST cold-start backfill + reconnect gap fill 設計

**Funding cold-start**: **不需**。`nextFundingTime` 在 WS connect 第一個 ticker tick 即帶（Bybit 每秒 push tickers update），cold-start 1-5s 內 25 sym buffer fill。30s 內某 sym 仍未收 ticker → fail-closed `next_funding_ms = None` for 該 sym。

**OI cold-start**: 必須。WS 只有 instantaneous oi_abs，沒有 prior interval baseline 算 delta。Rust 啟動跑 1 次 `bybit_rest_client::get_open_interest_batch()` 25 sym × 3 interval (5min/15min/1h) × limit=12 = 75 req batch 1 次（~0.6s burst, 12.5% of 600/5s window, well under cap）。Cold-start 後 baseline 寫進 aggregator state `windows: HashMap<String, VecDeque<(ts_ms, oi_abs)>>`，後續 WS push 即時更新。

**WS reconnect gap fill**: 既有 RE-2 supervisor (`main_ws.rs:75-131`) exponential backoff cap 60s 自動重連。Aggregator 觀察 broadcast `RecvError::Lagged(n)` 觸發：
- Funding aggregator: 下次 flush slot 寫 None（funding 8h cycle 不需重 backfill）
- OI aggregator: 觸發 cold-start backfill 重跑（25 × 3 = 75 req 1 batch；恢復 baseline）
- Reconnect gap window 預期 < 60s，cold-start backfill rerun ~0.6s burst 不影響 cap

## 4. Rate budget update（從 100 req/min → 0 req/s）

| 來源 | v1 設計 | **v1.1 設計** |
|---|---|---|
| Funding ongoing | 25 req/min (4.2%) | **0 req/s** |
| OI ongoing | 75 req/min (12.5%) | **0 req/s** |
| Cold-start (1 次 startup) | 0 | **75 req batch (~0.6s burst, 12.5% of 600/5s)** |
| Reconnect gap fill (per event) | 0 | ~75 req batch (cold-start 重跑, ~0.6s burst) |
| **Total ongoing increment** | **100 req/min (16.7%)** | **0 req/s (0%)** |
| **W1+W2+W3+baseline 總計** | ~1.7 req/s | **~1.2 req/s (~99% headroom)** |

## 5. Spec v1 → v1.1 change log

1. Header — 加 v1.1 注記 + Reference BB report + Reference WS code paths + Change Log table
2. §1.1 Background — 加「v1.1 WS-first design」段落 + 「為什麼 WS-first 是更好設計」4 點論證
3. §1.2 Scope — 子任務表 v1.1 column；out of scope 加「Python writer files (deprecate)」
4. §2.1 — REST polling → WS broadcast；rate budget v1.1 number；cohort 25 sym 加 SymbolRegistry alignment 說明
5. §2.3 — Python writer 整段刪除 → Rust `panel_aggregator/funding_curve.rs` 設計 + broadcast channel migration 副作用分析
6. §2.4 — `panel_puller.rs` 模組刪除說明 + aggregator 直接 write slot 雙寫意義
7. §2.5 — freshness 5s WS-tick threshold（嚴於 v1 30s）+ PG-side 30s/300s 寬鬆閾值
8. §3.1 — OI WS broadcast + cold-start REST batch 設計 + ongoing delta 算法 + REST 加固 optional fence + WS rolling delta vs Bybit 5m close-bar 偏差 risk
9. §3.3 — Python writer 整段刪除 → Rust `panel_aggregator/oi_delta.rs` 設計 + cold-start backfill fn + sliding window
10. §3.4 — freshness 同 §2.5 pattern
11. §5 — BB B-3 status TODO → DONE；rate budget table v1.1 number；BB §6 MEDIUM 採納項說明
12. §6 — sub-agent dispatch table v1.1（Files + 關鍵交付 update）+ sequential gating 說明 + E2 重點審查 3 點 v1.1（event channel migration 列為第 1 點）
13. §7.5 — risk table v1.1（rate budget 解除 + 3 新 risk: event channel migration / WS reconnect gap / OI rolling delta 偏差）
14. §8 — D+1 sign-off checklist v1.1（4 項已 DONE marker）
15. §9 — 一句總結 v1.1 重寫
16. Footer — PA SPEC DONE (v1.1 WS-first revision)

## 6. D+1 W1 sign-off 預期（PA + BB 直接收）

**Joint sign-off rationale**：BB B-3 deliverable 已出 (HEAD 2026-05-10)，PA v1.1 已採納 BB §6 HIGH push back 全部 design change，BB §6 MEDIUM rate burst 預警在 v1.1 設計下 **解除**（0 ongoing REST cost）。PA + BB 立場已 align，**無需 D+1 PA edit + BB integrate 再走一輪**。

**Sign-off path**:
- D+1 09:00 UTC：PM 整合 spec v1.1 進 dispatch v3.6 §3.1 W1 update（producer side 改 Rust aggregator + B-3 status DONE + sub-agent dispatch sequence v1.1 update）
- D+1 12:00 UTC：PA + BB joint sign-off（PA 確認 trait shape 0 改 + 16 原則 0 觸碰；BB 確認 v1.1 rate budget table 與 §6 推薦一致 + cold-start 75 req burst well under cap）
- D+2 09:00 UTC：PM dispatch W1 IMPL E1-α leader（event channel migration + funding aggregator + V085 + slot + dispatch wire + healthcheck [57]）
- D+3 09:00 UTC：E1-α push → PM dispatch E1-β rebase (oi_delta aggregator + V087 + cold-start backfill helper + healthcheck [58]) + E1-γ parallel (V086 + bb_breakout consume + fail-closed evaluation_outcome)
- D+5-D+6：land + E2 + E4
- W1 land 後 ≥ 24h：W3 Stage 1 cohort entry

**Saved cycle**：v1 設計需 D+1 PA edit + BB integrate（1 day），v1.1 直接收（0 day），**Sprint N+1 W1 整體 saved 1 day**，且 IMPL 路徑更乾淨（純 Rust producer + 0 Python writer file 落地 + 0 ongoing REST cost）。

---

**16 原則 + DOC-08 §12 + 硬邊界 5 項**：v1.1 全 0 觸碰（producer side 切換為純 read-only WS broadcast subscribe + PG write，不動 lease/auth/SM-04/live boundary/IntentProcessor 寫入路徑）。

PA REPORT DONE: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w1_spec_v1_1_bb_ws_first_revision.md
