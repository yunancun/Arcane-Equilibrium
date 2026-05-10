# E3 Sprint N+1 D+0 Security Pre-Audit · 2026-05-10

**範圍**: HEAD `1d9dccf1`，N+0 baseline `b6ed4975` → N+1 D+0 dispatch fire 前 PR ready / spec
**方法**: read-only attacker mindset；OWASP Top 10 + secret-leak grep 雙 skill
**目標**: D+0 sub-agent dispatch fire 前 sign-off 安全姿態，sign-off 後 IMPL phase 不重做 E3 review

---

## §1 攻擊面 Mapping

| 變更 | 入口 / 邊界 | 攻擊向量 | 既有防線 |
|---|---|---|---|
| W7-3 (`b42731f6` + `d8697c41`) ma_crossover.on_rejection reason 字串 parse | Rust 內部 `IntentProcessor.per_strategy_new_entry_rejection()` → `RejectionCode::format()` byte-identical 出 | reason 內含 fake `"already LONG/SHORT"` → strategy.positions 寫錯方向 | reason 來源 = Rust enum `format!()` 100% 內部，**無外部 user input 入口**；contract drift fallback 走完整 RC-04 + `tracing::warn` |
| W7-1 (`c9fb0b8f`) TickContext.position_state per-iteration borrow | Rust pipeline 內部 immutable `&'a PaperPosition` borrow | use-after-free / dangling reference / data race | `paper_state.get_position()` 回 `Option<&PaperPosition>`，借 `'a` lifetime；NLL per-iteration 釋放後再 mutable mirror_insert / apply_fill；TickContext `#[derive(Clone)]` shallow copy 不 own data；0 unsafe 塊 |
| W2 BtcLeadLagPanel paper-only fence 三層 | Layer 1 `step_4_5_dispatch.rs::effective_engine_mode()` match arm；Layer 2 Python writer env gate；Layer 3 strategy `if let Some(...)` defensive | demo / live_demo / live engine 收到 panel → 5 策略 demo edge baseline 被污染 | Layer 1 由 Rust enum `(PipelineKind, BybitEnvironment) → &'static str` enforce，default `_ => None`；`mode_state.rs:38-55` 已 type-safe；E2 必 grep verify default branch |
| W1 panel_aggregator WS-first（`fundingRate` / `openInterest` payload parse） | Bybit V5 WS broadcast `tickers.{symbol}` topic | malformed JSON / NaN / Inf / 負值 → Rust panic | `parsers.rs:225-263 parse_ticker_item()` 全 fail-closed: `.parse::<f64>().ok()` + `.filter(\|p\| p.is_finite() && *p >= 0.0)`；無 unwrap / 無 expect；既有 24h Mainnet 流量已驗 |
| V086 column add + backfill UPDATE | `learning.decision_features.{reject_reason_code, close_reason_code}` 新 TEXT column + NOT VALID CHECK + backfill UPDATE 9757 row + `trading.fills.strategy_name` REPLACE 17 row | (a) `SELECT *` pattern 偷新 column；(b) trading.fills UPDATE 破歷史 audit blame chain；(c) NOT VALID 後 ALTER VALIDATE 鎖表 | (a) backfill SQL 100% parameterized DDL/UPDATE，無 user input concat；(b) trading.fills 17 row 可 trace fix commit `46a9cadc` (2026-04-23)，forensic chain 可重建；(c) NOT VALID 鎖窗 < 30 sec on 9757 row |
| V088 panel.btc_lead_lag_panel + V089 cohort_freq_cap_attempts + V090 unblock_candidates | TimescaleDB hypertable + 4 CHECK constraint | jsonb / array column 注入 / over-permission DB role | 全 DDL，0 user-controlled string；`alt_xcorr real[]` / `alt_expected_dir smallint[]` / `regime_tag text` 由 Python writer normalize 寫入；DB role = `trading_admin` migration only |
| Strategy paper-only fence Layer 2 (Python writer) | `btc_lead_lag_writer.py` 啟動讀 `OPENCLAW_ENABLE_PAPER` env | env 未設 fallback 行為錯 → demo PG 累積污染樣本 | spec §6.2 寫「未設 + demo/live 偵測 → writer 不啟動或只寫 placeholder」；E2 必驗該 fail-closed branch grep |

---

## §2 Vulnerability Scan Findings

### [LOW-N1-1] (A03 Injection) reason 字串 parse 契約 drift 風險

**證據**：`strategy_impl.rs:55-87` 對 `reason.contains("already LONG")` / `("already SHORT")` 字面 match。`RejectionCode::DuplicatePosition.format()` 由 `rejection_coding.rs:147-152` 產出格式 `"duplicate_position: {symbol} already {LONG|SHORT} {qty}"` 鎖死。

**攻擊路徑**：純內部 Rust enum format → strategy parse；無外部 user input 入口（reason 不從 HTTP / WS / IPC 注入）。**真實攻擊面 = 0**。

**Risk vector**：未來改 RejectionCode format（例：本地化、改用 emoji）→ 字面 match 漏接 → fallback 走原 RC-04 path（仍正確 + tracing::warn），**降級而非破壞**。

**Mitigation**：E2 已標 LOW；建議 W-AUDIT-8a Phase B Option A（`ctx.position_state` 直查 paper_state）落地後此 LOW 自然 close。

### [LOW-N1-2] (A09 Logging) trading.fills UPDATE 不寫 change_audit_log entry

**證據**：V086 backfill 含 `UPDATE trading.fills SET strategy_name = REPLACE(...)` 對 17 row 上游清理。`change_audit_log.py` (governance hub append-only) 不會自動接到此 SQL UPDATE。

**攻擊路徑**：非攻擊；治理 forensic chain 一次性破壞。但 PA `2026-05-10--p2_decision_features_double_prefix_bug_audit.md` 已 trace 17 row 來源 = pre-fix-commit `46a9cadc` 9.3h 期間，**git commit chain 仍可重建 forensic**。

**Mitigation**：V086 deploy commit message 強制 reference `46a9cadc` 作 audit anchor；future migration UPDATE trading.* 應加 governance audit hook（W6-3c E1 IMPL 之後 P3 backlog）。

### [LOW-N1-3] (A05 Misconfiguration) N+0 sign-off SOP shell 含 PG_PASS 變數展開

**證據**：`PA/workspace/reports/2026-05-10--n0_signoff_n1_dispatch_fire_sop.md:50` 含 `ssh trade-core "PG_PASS=\$(awk -F= '/^POSTGRES_PASSWORD=/{print \$2}' ...env)" && PGPASSWORD=\$PG_PASS psql ...`

**攻擊路徑**：operator 手貼此 ssh 命令 → PG_PASS 透過 ssh 命令字串傳輸 + 短暫進 Linux process 環境 + psql `PGPASSWORD` env 已是 PostgreSQL 標準 + ssh tty 不寫 history（per-shell config）→ same-uid attacker 可從 `/proc/<pid>/environ` 讀 → known same-uid trust boundary，符合 §五 Mac dev-only / Linux runtime 模型。

**Mitigation**：建議改用 `~/.pgpass` (chmod 600) 取代 inline `PGPASSWORD` env；不阻 N+1 sign-off。

### [INFO-N1-1] (A04 Insecure Design) governance.canary_stage_log CHECK extend `manual_promote_override`

V089 `cohort_freq_cap_attempts` 設 24h max=2 promote override；W5-E1-B 須加 lease-bound role gate (per spec §6 LeaseScope::CanaryStagePromotion)，IMPL phase E2 必驗。

---

## §3 Secret Leak Scan

| Pattern | 命中 | 結果 |
|---|---|---|
| Pattern A — secret hardcode in spec/code/report | 0 | PASS |
| Pattern B — high-entropy hex/base64 ≥32 char | 0 | PASS |
| Pattern C — Bybit `X-BAPI-SIGN` header literal / API key 字面 | 0 | PASS |
| Pattern D — log/print 含 api_key / secret / token | 0 | PASS |
| Pattern E — env var (KEY/SECRET/PASSWORD) 寫入 log | 0 | PASS |
| Pattern G — cross-platform path hardcode (`/home/ncyu` / `/Users/ncyu`) | 7 (governance index doc + sign-off SOP shell) | LOW (非 runtime code) |
| W2 V088 `panel.btc_lead_lag_panel` schema | 0 secret column | PASS |

**Verdict**: PASS（0 CRITICAL / 0 HIGH secret leak；7 path hardcode 全在 governance index + ssh SOP shell，非 runtime code path）

---

## §4 ToS / 法律邊界

**BB W1+W2 rate budget review (`2026-05-10--w1_w2_bybit_v5_rate_budget_review.md` §5)**:
- 25 symbol cohort KYC tier 風險 = 0（USDT-perp linear，demo + LiveDemo 不要求 KYC）
- W1/W2 全 read-only market data fetch + 0 order create/quote → anti-spam / market-maker rebate 0 觸發
- 30d Bybit V5 changelog 0 breaking change
- W1+W2+W3+baseline 合計 < 1.2 req/s (~99% IP cap headroom)
- W2 BTCUSDT spot orderbook = `/v5/market/orderbook` snapshot top-10，**屬 public market data 公開取用**，不觸發 redistribution clause（OpenClaw 內部 PG 寫入 + Strategy 內部消費 + shadow log only，0 二次發布到外部 platform）

**Verdict**: PASS（0 ToS / KYC / geographic 觸發；W2 paper IMPL 0 redistribution risk）

---

## §5 Authorization Integrity

| 5 hard gate | N+1 D+0 影響 | Verdict |
|---|---|---|
| Python `live_reserved` global mode | 不變（W7 純 Rust 改） | PASS |
| Operator 角色 auth | 不變（W5 P1 spec 增加 lease-bound role gate `LeaseScope::CanaryStagePromotion`，IMPL phase E2 必驗） | PASS |
| `OPENCLAW_ALLOW_MAINNET=1` | 不變（W2 paper-only fence Layer 1 不影響 live boundary） | PASS |
| secret slot api_key + api_secret | 不變 | PASS |
| `authorization.json` HMAC + TTL + env_allowed | 不變（W1 WS-first 不需 auth；既有 RE-2 supervisor 重連繼承既有 sig） | PASS |

**W7-1 ctx.position_state IPC inject 攻擊面**：position_state 從 `paper_state.get_position()` 直接 borrow，paper_state 自身寫入只走 `proactive_mirror_insert` + `apply_fill`，無 IPC inject 路徑可繞過寫入 paper_state HashMap。

**W7-3 on_rejection 跨 lease 干擾 SM-02 throughput**：on_rejection 純 strategy 內部 cooldown HashMap 操作，0 lease/governance/reconciler IPC 觸發。SM-02 / Decision Lease lifecycle 完全解耦。

**Verdict**: PASS（5 hard gate 全綠，N+1 D+0 無新繞過路徑）

---

## §6 OWASP Top 10 (2021) 覆蓋

| 類 | 範圍內變化 | Verdict |
|---|---|---|
| A01 Broken Access Control | W5 V089 promote override 加 lease-bound gate（IMPL phase E2 驗） | 強化 (pending IMPL) |
| A02 Cryptographic Failures | 0 改動 | 不變 |
| A03 Injection | W7-3 reason parse 純內部契約；V086 backfill 100% DDL/parameterized | 不變 |
| A04 Insecure Design | W2 paper-only fence 三層深度防禦設計（type-safe enum + Python env + Rust Option<T>） | 強化 |
| A05 Security Misconfiguration | LOW-N1-3 SOP shell PG_PASS env (same-uid trust boundary) | LOW backlog |
| A06 Vulnerable Components | 0 新依賴 | 不變 |
| A07 Authentication Failures | 0 新 auth 改動 | 不變 |
| A08 Software/Data Integrity | V086 NOT VALID CHECK + 4 V### Guard A/B/C 強制 | 強化 |
| A09 Logging Failures | LOW-N1-2 trading.fills UPDATE 缺 governance audit hook | LOW backlog |
| A10 SSRF | W1 WS-first 0 新 external URL；既有 wss://stream.bybit.com 已驗 | 不變 |

---

## §7 Sign-off Recommendation

**Verdict: ALL PASS — D+0 sub-agent dispatch fire 可進**

| 嚴重性 | 數量 | 詳情 |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 0 | — |
| LOW | 3 | LOW-N1-1 reason contract drift / LOW-N1-2 trading.fills audit hook / LOW-N1-3 SOP shell PG_PASS |
| INFO | 1 | INFO-N1-1 V089 cohort override lease gate IMPL phase E2 verify |
| **NEW unauth endpoint** | 0 | — |
| **NEW secret leak** | 0 | — |
| **NEW SQL injection** | 0 | — |
| **NEW shell injection** | 0 | — |
| **NEW path hardcode in runtime code** | 0 | — |

**Block sign-off until fix list**: 無（無 HIGH / CRITICAL）

**IMPL phase E2 必驗 4 點**（sign-off carry-over）：
1. W2 `step_4_5_dispatch.rs` paper-only fence Layer 1 default branch grep verify `_ => None`（非 `_ => Some(...)`）
2. W2 Python writer Layer 2 fence: `OPENCLAW_ENABLE_PAPER` env gate fail-closed branch
3. W7-2 future ma_crossover entry path 加 `ctx.position_state` query 後 LOW-N1-1 contract drift 風險才能完全 close
4. W5 V089 cohort_freq_cap_attempts promote override LeaseScope::CanaryStagePromotion 接線

---

## §8 對抗性 push back

### §8.1 trait skeleton pre-write 模式（c9fb0b8f）的安全評估
PA D+0 一個 commit 把 trait skeleton 全寫死 + 5 策略 callsite signature 對齊，技術上是 **best-practice anti-merge-conflict**；安全角度 **0 attack surface 引入**（field 默認 None / fallback EMPTY_ALPHA_SURFACE 全部 fail-closed）。建議後續 W-AUDIT-8a Phase C/D trait extension 沿用此 pattern。

### §8.2 W7-3 happy path early-return 保留 cooldown 設計
on_rejection match 到 `duplicate_position: ... already SHORT/LONG ...` → return early 不 rollback cooldown。E2 review 已標「刻意保留 cooldown 作 hot loop 雙重防護」，安全立場 **PASS**。

### §8.3 W2 三層深度防禦 vs Layer 3 redundancy
Layer 3 strategy `if let Some(panel) = surface.btc_lead_lag` 已被 Rust type system 保證（None → 跳過）；Layer 1 + Layer 2 已 fail-closed → Layer 3 是 Rust 型別系統自然 enforce 的「免費」防護，0 額外 LOC，**接受 redundancy**。

### §8.4 V086 NOT VALID CHECK 與 ALTER VALIDATE timing
PA spec 明寫 D+1 evening land + D+2 14:00 UTC 24h dual-write drift healthcheck PASS + 14:30 ALTER VALIDATE。E2 必驗 deployment runbook 含 atomic deploy step（V086 land 與 producer dual-write code deploy 不能差 >5 min；否則 NULL drift → ALTER VALIDATE 失敗）。

### §8.5 Sprint N+1 D+0 timing race
PA D+0 trait skeleton (`c9fb0b8f` 15:06) + W7-3 review chain (`b42731f6` 14:20) **均標 NOT DEPLOYED**，等 21:30 UTC HIGH-5 sign-off + N+1 dispatch fire 同次 `restart_all --rebuild --keep-auth` deploy（省 1 次 restart cost）。安全角度 PASS — engine PID 仍跑 N+0 baseline；deploy 前任何 RUST source-fix 都尚未 runtime 生效 = 與 v1/v2/v3 NEW-VULN-4 phase4 stale 同類教訓對齊。

---

## §9 報告元數據

- **撰寫者**: E3 (Security Auditor, attacker mindset 對抗性核實)
- **撰寫時間**: 2026-05-10 19:30 UTC+1
- **基準範圍**: HEAD `1d9dccf1` (D+0 dispatch fire 前 PR ready / spec)
- **基準對比**: N+0 sign-off `b6ed4975` (2026-05-10 ~03:30 UTC)
- **0 個 exploit 嘗試 / 0 個 secret 內容寫入本報告**
- **下次審計觸發點**:
  - W6-3c V086 IMPL E1 land + ALTER VALIDATE post 24h
  - W2 C-IMPL-2 panel_aggregator + V088 land
  - W5-E1-B/-C P1-CANARY-COHORT-FREQ-23 + P1-DYNAMIC-UNBLOCK-CHECK-1 IMPL land
  - W1 IMPL chain land（WS-first 切換 + V085/V087 land）
