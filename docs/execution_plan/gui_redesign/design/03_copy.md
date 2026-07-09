# COPY, MICROCOPY & BILINGUAL LABEL SYSTEM — S1 "Terminal" (文字系統)

The definitive content/voice specification for the OpenClaw operator console. Every string a designer or E1a writes must resolve against this document. Anchored to the S1 tokens; bilingual rules are enforceable (a lint target, not a vibe).

---

## 0. SCOPE & GOVERNING PRINCIPLE

This console is a **real-money algo-trading operator console**. The reader is one expert operator (the owner), fluent in trading jargon, reading fast, often under P&L stress, frequently on a phone. Copy is an **instrument readout**, not marketing and not a chat assistant.

**The one rule that generates all others:** *The interface states what is true and what will happen. It never softens, apologizes, editorializes, or narrates its own feelings.* A gauge does not say "oops". Neither does this console.

Three hard bans, enforceable in review:
- **No apology strings** anywhere (`抱歉/對不起/sorry/oops/我們`). A failure state names the failure and the fix.
- **No first-person assistant voice** (`我幫你/讓我/I'll/we've`). The console has no "I". Buttons are imperatives the operator issues; readouts are third-person facts.
- **No hedging** (`可能大概/似乎/it seems/should be/try to`). If a value is uncertain, that is a *named state* (stale / estimated / degraded), not a hedge word.

---

## 1. VOICE & TONE

### 1.1 The four voice attributes

| Attribute | Meaning | Test |
|---|---|---|
| **Precise** 精確 | Exact noun, exact number, exact unit. Never "some", "a lot", "recently". | Could two operators disagree on what this string means? If yes, rewrite. |
| **Active / imperative** 主動 | Buttons are verbs the operator commands. Readouts are declarative facts. | Does the button say the *action*, not the *feature*? "Flatten" not "Position tool". |
| **Name-what-happens** 明說後果 | State the mechanical consequence, especially for money-moving actions. | After I click, exactly what changes? Is that in the string? |
| **Unhedged** 不打太極 | No softeners, no apologies, no anthropomorphic filler. | Remove every adjective that isn't load-bearing. Still true? Ship it. |

### 1.2 Register by surface

Copy register shifts with **consequence**, not with screen:

- **Readouts / labels** — terse, telegraphic. Fragment, not sentence. `今日淨 +$1,204`, not `今天你的淨利是...`.
- **Confirmations (benign)** — one plain sentence, active voice. `已儲存風控設定。`
- **Confirmations (real-money)** — formal, complete, imperative, with the mechanical consequence spelled out. This is the *only* place verbosity is correct.
- **Errors** — cause + fix, no blame. Two clauses max.
- **Empty states** — what's absent + how to populate it.

### 1.3 Good vs bad — domain examples

| Context | ❌ Bad | ✅ Good | Why |
|---|---|---|---|
| Save risk config | 設定似乎已經儲存成功了！ | 已儲存風控設定 · 3 項變更 | No hedge, no exclamation; names count |
| Engine offline | 哎呀,好像連不上引擎 😅 | 引擎離線 · 最後心跳 14:32:07 | Names state + evidence, no apology/emoji |
| Flatten button | 平倉工具 | 市價平倉 BTCUSDT | Verb + object, not a feature name |
| No fills yet | 目前沒有任何資料喔~ | 尚無成交 · 今日 0 筆 | Specific absence, not generic "no data" |
| Blocked feature | 功能維護中,敬請期待 | 帳戶未連線 · 待 Phase 2 | Real reason + real timeline |
| Gate rejected order | 訂單被系統拒絕了 | 成本閘攔截 · edge 1.2bps < 門檻 11bps | Names *which* gate + *why*, quantified |
| Stale price | 資料可能不是最新的 | 報價過期 · 8s 未更新 | State + measurement, not a hedge |
| Live confirmation | 你確定要這樣做嗎? | 此操作動用實盤資金 · BTCUSDT 市價平倉 0.42 | Names funds + exact action + size |
| AI reasoning idle | AI 正在思考中... | L2 推理閒置 · 上次 03:17 | Named state + timestamp, no anthropomorphism |
| Loss shown | 今天虧了不少呢 | 今日淨 −$842 | The number *is* the message. No commentary. |

### 1.4 Numbers, signs, units — the numeric voice

Because half this console is numbers, numeric formatting *is* copy:

- **Always signed** for any delta/PnL: `+$1,204`, `−$842` (U+2212 minus, not hyphen, for tabular alignment).
- **Redundant encoding (CVD-safe):** color + sign + (where directional) arrow/label. Never color alone. `▲ +2.4%` / `▼ −1.1%`.
- **Units inline, muted, 11px:** `12.4 bps`, `0.42 BTC`, `$18,204`. Unit token uses `--text-muted`; the number uses `--text-primary` + `tabular-nums slashed-zero`.
- **Precision fixed per metric** (never variable): price 2dp for USDT pairs, size to instrument step, bps 1dp, % 2dp, equity 0dp for tiles / 2dp for statements.
- **Zero is em-dash when "no data", but `0` when genuinely zero.** `尚無成交` shows `—`; a real 0-count shows `0 筆`. Do not conflate.
- **No approximations in a data cell.** "~$18k" is banned in tables; allowed only in prose summaries.

---

## 2. BILINGUAL DISCIPLINE — killing the ~480 inline double-labels

### 2.1 The problem

Current GUI renders `總覽 Overview`, `保證金 Margin`, `未實現 uPnL` inline everywhere — ~480 instances. This doubles scan width, fights the austere aesthetic, and has no single source of truth (drift guaranteed). The fix is a **three-tier resolution rule** plus one lookup mechanism.

### 2.2 The three resolution modes

Every human-readable string resolves to **exactly one** of three modes:

**Mode A — Primary + tooltip (the default, ~90% of labels).**
Chinese visible; English on `title=` (desktop hover) and long-press (mobile). One channel visible, one on demand.
```html
<abbr class="lbl" title="Unrealized PnL">未實現</abbr>
```

**Mode B — Technical token, inline English, no translation.**
Irreducible tokens that are *already* the operator's working vocabulary and have no better Chinese form. These stay bare English, styled as tokens (mono or muted).
```html
<span class="tok">BTCUSDT</span> · <span class="tok">bps</span> · <span class="tok">S3</span>
```

**Mode C — Bilingual visible, deliberately (rare, ~5–8 strings total).**
Reserved for **first-encounter high-consequence** surfaces where ambiguity is unacceptable: the real-money confirm modal heading, the IBKR governance banner, the environment-ladder legend on first render. Here the English is a safety redundancy, not decoration.

### 2.3 The decision tree

```
Is the string a fixed technical token?
  (symbol, unit, system_mode, S0–S4 gate id, endpoint,
   env name, bps, orderLinkId, HTTP verb, cron id)
│
├─ YES ─────────────────────────────────────────► MODE B  (inline English, .tok)
│
└─ NO → Does misreading it risk real money or an
        irreversible action, AND is this a first-
        encounter / low-frequency surface?
        │
        ├─ YES ─────────────────────────────────► MODE C  (bilingual visible)
        │
        └─ NO → Default ────────────────────────► MODE A  (中文 + title= English)
```

Frequency rule that overrides toward A: **if a label appears >3× per screen, it must be Mode A or B** (never C) — repeated bilingual pairs are the exact disease we are curing.

### 2.4 The mechanism — single source of truth

One flat dictionary, `t_zh` / `t_en`, keyed by a stable term id. No string literals in templates.

```js
// labels.js — the ONLY place a label string is authored
export const L = {
  overview:   { zh: '總覽',   en: 'Overview' },
  positions:  { zh: '開倉',   en: 'Positions' },
  net_today:  { zh: '今日淨', en: 'Net Today' },
  upnl:       { zh: '未實現', en: 'Unrealized PnL', short: 'uPnL' },
  // ...
};
```

```js
// render helper — Mode A default
function lbl(id) {
  const t = L[id];
  const el = document.createElement('abbr');
  el.className = 'lbl';
  el.textContent = t.zh;          // visible = Chinese
  el.title = t.en;                // English on hover / long-press
  return el;
}
```

- **Mode B tokens** are *not* in `L` — they are literal data, rendered via `.tok` class, never translated.
- **Mode C** uses an explicit `lblBoth(id)` that emits `<span class="lbl-zh">…</span><span class="lbl-en">…</span>` — auditable by grep, so the ~5–8 legitimate uses stay countable and can't silently multiply.
- **Global lang toggle** flips `document.document
Element.lang`; CSS `[lang=en] .lbl { … }` can surface English as primary for a non-CJK operator without touching markup. `title=` swaps to `zh` in that mode.

### 2.5 The lint gate (how the 480 die and stay dead)

Add a CI check (cheap regex, `feedback_gui_node_check` style):
1. **Ban inline bilingual pairs in templates:** grep for `[\u4e00-\u9fff]+\s+[A-Za-z]` adjacent in JSX/HTML text nodes → fail unless the node carries `data-lbl-both` (the sanctioned Mode C escape hatch).
2. **Ban raw label literals:** any CJK text node not produced by `lbl()`/`lblBoth()`/`.tok` → fail.
3. **Mode C budget:** count `lblBoth(` call sites; hard cap (e.g. 8). Exceeding the cap fails CI — forces a design review, not a silent creep back to 480.

### 2.6 Irreducible Mode-B token registry

These stay inline English, always, everywhere:

| Category | Tokens |
|---|---|
| Symbols | `BTCUSDT`, `ETHUSDT`, `AAPL`, `SPY`, … |
| Units | `bps`, `USDT`, `USD`, `%`, `x` (leverage) |
| System enums | `system_mode`, `live_demo`, `paper`, `demo`, `live`, `replay` |
| Gate / stage ids | `S0`–`S4`, `Gate 1.6`, `Gate-B`, `cost_gate` |
| Identifiers | `orderLinkId`, endpoints (`/v5/order/create`), cron ids, commit SHAs |
| Protocol | `L0`/`L1`/`L2`, `ONNX`, `PG`, `IPC`, `ATR` |

Rule: a token is Mode B only if translating it would *reduce* precision for the expert operator. `保證金/Margin` is Mode A (Chinese is clearer). `bps` is Mode B (「基點」is slower to read than `bps` for this reader).

---

## 3. LABELS LEXICON — canonical bilingual glossary

**Authoring rule:** `SHORT` is what renders (`.lbl` visible text = the zh SHORT). `TOOLTIP` is the `title=` English full form. `MODE` per §2.2. Never invent a synonym at call-site — add a row here.

### 3.1 Core financial readouts

| Term id | zh SHORT (visible) | EN TOOLTIP (title=) | Mode | Notes |
|---|---|---|---|---|
| overview | 總覽 | Overview | A | Nav |
| positions | 開倉 | Open Positions | A | "持倉" acceptable synonym — **use 開倉**, canonical |
| net_today | 今日淨 | Net PnL Today | A | Always signed, colored |
| equity | 權益 | Account Equity | A | |
| balance | 餘額 | Wallet Balance | A | |
| upnl | 未實現 | Unrealized PnL | A | short token `uPnL` allowed in ultra-dense headers |
| rpnl | 已實現 | Realized PnL | A | |
| margin | 保證金 | Margin | A | |
| margin_ratio | 保證金率 | Margin Ratio | A | |
| liq_price | 強平價 | Liquidation Price | A | short label `Liq.` in cramped col headers (Mode B fallback) |
| leverage | 槓桿 | Leverage | A | value shown as `10x` (Mode B token) |
| entry | 開倉均價 | Avg Entry | A | |
| mark | 標記價 | Mark Price | A | |
| size | 倉位 | Position Size | A | value in base units + symbol |
| exposure | 曝險 | Net Exposure | A | |
| fees_today | 今日費用 | Fees Today | A | |
| funding | 資金費 | Funding | A | perp-only |
| drawdown | 回撤 | Drawdown | A | |
| fill | 成交 | Fill | A | |
| order | 訂單 | Order | A | |
| slippage | 滑價 | Slippage | A | |
| turnover | 週轉 | Turnover | A | |

### 3.2 System / governance / environment

| Term id | zh SHORT | EN TOOLTIP | Mode | Notes |
|---|---|---|---|---|
| governance | 治理 | Governance | A | |
| risk | 風控 | Risk Controls | A | |
| gates | 閘 | Gates | A | individual gate ids `S0`–`S4` = Mode B |
| gate_cost | 成本閘 | Cost Gate | A | |
| ai_layer | AI 推理 | AI Reasoning (L2) | A | `L2` inline = Mode B |
| learning | 學習 | Learning | A | ML pipeline |
| monitor | 監控 | Monitor | A | |
| settings | 設定 | Settings | A | |
| audit | 稽核 | Audit Log | A | |
| live | 實盤 | Live · Real Funds | **C** | real-money — see §5 |
| demo | 演示 | Demo | B/A | keep `Demo` inline as env token; zh 演示 in tooltip |
| paper | Paper | Paper Trading | B | no good short zh; keep inline |
| replay | 回測 | Replay | A | |
| research | 研究 | Research | A | env-ladder rung 1 |
| autonomy | 自主 | Autonomy | A | |
| heartbeat | 心跳 | Heartbeat | A | |
| lease | 租約 | Execution Lease | A | |
| flatten | 平倉 | Flatten Position | A | action — see §5 |
| flatten_all | 全平 | Flatten All | A | high-consequence — Mode C in confirm |
| pause | 暫停 | Pause Engine | A | |
| resume | 恢復 | Resume Engine | A | |
| kill | 急停 | Kill Switch | **C** | emergency stop |

### 3.3 Asset-lane peers

| Term id | zh SHORT | EN TOOLTIP | Mode |
|---|---|---|---|
| lane_crypto | 加密永續 | Crypto Perp · Bybit | A (Bybit = B) |
| lane_stock | 股票 / ETF | Stock · ETF · IBKR | A (IBKR = B) |

---

## 4. STATE & STATUS COPY — every data state, distinctly worded

The cardinal sin is **state collapse** — using one string ("無資料 / N/A / --") for six different conditions. Each state below has a *distinct, non-overlapping* phrasing so the operator instantly knows which reality they're in. All bilingual per Mode A unless noted.

### 4.1 The state matrix

| State | Visual token | zh copy (visible) | EN tooltip | Rule |
|---|---|---|---|---|
| **Real value** | normal number | `+$1,204` | — | The number is the message. No label needed. |
| **Loading** | skeleton shimmer, no text | *(no words — animated bar)* | — | Never write "載入中..." in a data cell; skeleton *is* the copy. Spinner text only for >2s blocking ops. |
| **Loading (blocking >2s)** | inline spinner + text | `讀取中 · {source}` | Loading {source}… | Names the source so operator knows what's slow |
| **No data (empty, valid)** | em-dash `—` | `—` in cell; `尚無成交 · 今日 0 筆` in empty-panel | No fills yet · 0 today | Genuine absence. Em-dash in cells, sentence in panels. |
| **Stale / not fresh** | amber dot + age | `報價過期 · 8s 未更新` | Quote stale · 8s since update | **Always show the age.** Staleness without a number is a hedge. |
| **Disconnected** | red hairline + timestamp | `引擎離線 · 最後心跳 14:32:07` | Engine offline · last heartbeat 14:32:07 | Names last-known-good time. Never just "離線". |
| **Blocked / not-collected** | muted, dashed border | `帳戶未連線 · 待 Phase 2` | Account not linked · pending Phase 2 | Real reason + real roadmap. This is a *plan*, not an error. |
| **Degraded (source down, fallback active)** | amber badge `降級` | `數據降級 · {source} 不可用 · 用 {fallback}` | Degraded · {source} unavailable · using {fallback} | Names what failed AND what's substituting. Value still shown but flagged. |
| **Estimated (computed, not confirmed)** | `~` prefix + italic | `~ 估算 · 待對帳` | Estimated · pending reconcile | For values derived before broker confirm |
| **Contract violation (LOUD)** | red banner `--neg`, full-width | `契約違反 · {field} 缺 column · 已 fail-closed` | Contract violation · {field} missing column · failed closed | **Loudest non-live state.** Must be impossible to miss; blocks the panel, logs to audit. |

### 4.2 State-copy anti-patterns

- ❌ `N/A` used for empty, stale, and blocked alike → ✅ three distinct strings above.
- ❌ `錯誤` alone → ✅ name the error class + fix (§6).
- ❌ Stale data shown identically to fresh → ✅ amber dot + age is **mandatory**; a number older than its SLA must visibly degrade.
- ❌ Skeleton that says "Loading..." as literal text → ✅ animated bar, zero text.
- ❌ Degraded value shown as if authoritative → ✅ `降級` badge is non-negotiable.

### 4.3 Staleness thresholds (drives the amber dot)

| Data class | Fresh | Stale (amber + age) | Disconnected (red) |
|---|---|---|---|
| Mark price / quotes | <2s | 2–15s | >15s or no tick |
| Position / equity | <5s | 5–30s | >30s |
| Fills / orders | <3s | 3–20s | >20s |
| AI L2 reasoning | <heartbeat interval | 1–2× interval | >2× interval |

---

## 5. ACTION COPY — buttons, confirms, real-money danger

### 5.1 Button verb rules

- **Verb + object, imperative.** `市價平倉 BTCUSDT`, not `平倉工具` / `執行`.
- **The button says what happens; the toast confirms it happened** in the same words.
- **Destructive/irreversible verbs are visually and lexically distinct** — `--neg`/`--live` color, never share a style with a benign save.
- **No generic `確定 / 提交 / OK`** on a consequential action — the verb must name the deed.

| Action | Button label (zh) | title= (en) | Success toast | Style |
|---|---|---|---|---|
| Save benign config | 儲存 | Save | `已儲存 · {n} 項變更` | default |
| Save risk config | 儲存風控 | Save Risk Config | `已儲存風控設定 · {n} 項變更 · 即時生效` | `--warn` accent |
| Pause engine | 暫停引擎 | Pause Engine | `引擎已暫停 · {ts}` | `--warn` |
| Resume engine | 恢復引擎 | Resume Engine | `引擎已恢復 · {ts}` | `--accent` |
| Cancel order | 撤單 | Cancel Order | `已撤單 · {orderLinkId}` | default |
| Flatten one | 市價平倉 {SYM} | Flatten {SYM} (market) | `已送出平倉 · {SYM} {size}` | `--neg` |
| Flatten all | 全平所有倉位 | Flatten ALL Positions | `已送出全平 · {n} 倉` | `--live` |
| Kill switch | 急停 | Kill Switch | `已急停 · 全數暫停 · {ts}` | `--live` |

### 5.2 Confirm-modal copy structure (universal skeleton)

Every consequential confirm uses the **same five-slot structure**, in this order. Benign actions may collapse slots 4–5; **real-money actions must fill all five plus the typed phrase.**

```
① ACTION   — what verb, in bold, imperative
② PARAMS   — exact object(s): symbol, size, price, count
③ ACTOR    — who/what executes + which environment
④ IMPACT   — the mechanical consequence, money named if real
⑤ ROLLBACK — is this reversible? if not, say so plainly
[TYPED CONFIRM] — for real-money only
```

### 5.3 Benign confirm example (risk config)

```
┌─ 確認儲存風控設定 ────────────────────────────
│ ① 儲存風控設定變更                    Save Risk Config
│ ② 3 項變更:
│      max_position   25 → 20
│      daily_loss_cap  $2,000 → $1,500
│      per_trade_risk  3% → 2.5%
│ ③ 套用至 · Live · Bybit 引擎          Applies to Live engine
│ ④ 即時生效於下一筆訂單                 Effective next order
│ ⑤ 可隨時再次調整                      Reversible anytime
│                          [ 取消 ]  [ 儲存風控 ]
└──────────────────────────────────────────────
```
No typed phrase — reversible, no funds moved *now*.

### 5.4 Real-money danger wording (the sacred path)

Live money-moving actions get the **maximum-friction pattern**. This is the one place the console is deliberately verbose and slow.

Requirements:
1. **`--live` red header** with `⚠ REAL FUNDS · 實盤資金` (Mode C — bilingual visible, safety redundancy).
2. **All five slots filled**, funds named explicitly.
3. **Physical separation:** the confirm button is disabled until the typed phrase matches, and sits apart from Cancel (not adjacent, not same size/color as benign).
4. **Typed confirmation phrase** = a string the operator must type exactly, containing the *specific* object so muscle-memory can't fire it: `FLATTEN BTCUSDT`, not `CONFIRM`.
5. **No pre-fill, no paste-to-bypass** intent — the phrase names the exact instrument/action.

```
┌─ ⚠ REAL FUNDS · 實盤資金 ──────────────────────  [--live red]
│
│ ① 市價平倉                              Flatten position (market)
│ ② BTCUSDT · Long 0.42 · 標記價 $61,204
│      估算平倉損益  −$842  (已實現)
│ ③ 執行者 · Operator (你) · Live · Bybit
│ ④ 動用實盤資金 · 立即以市價成交 · 不可撤回
│      This uses REAL FUNDS. Market fill. Cannot be undone.
│ ⑤ 無回滾 · 平倉後需重新開倉             No rollback
│
│ 輸入以下字串以確認:
│   ┌────────────────────────────────┐
│   │ FLATTEN BTCUSDT                │  ← operator types
│   └────────────────────────────────┘
│
│   [ 取消 ]                    [ 平倉 BTCUSDT ]  ← disabled until match
└────────────────────────────────────────────────
```

**Flatten-all / kill escalates further:** typed phrase `FLATTEN ALL` + a count echo the operator must confirm (`確認平掉 4 個倉位?`), because the object is plural and the blast radius is the whole book.

### 5.5 Toast/feedback timing copy

- **Optimistic actions** (cancel, pause): toast immediately, reconcile silently. If reconcile fails → replace toast with error (§6), don't stack.
- **Real-money actions**: NO optimistic toast. `已送出平倉 · 待成交` (submitted, pending fill) → then `已成交 · {SYM} {fillPrice}` on broker confirm. Never claim "done" before the fill.

---

## 6. EMPTY & ERROR STATES

### 6.1 Empty-state formula

`{什麼不存在} · {為何/如何填充}` — specific absence + the populating action. Never a shrug.

| Screen | ❌ Bad | ✅ Good (zh · en tooltip) |
|---|---|---|
| Positions (flat) | 沒有資料 | `無開倉 · 引擎待信號` · No open positions · engine awaiting signal |
| Fills today | 空 | `尚無成交 · 今日 0 筆` · No fills yet · 0 today |
| Audit log filtered | 找不到結果 | `無稽核紀錄符合 · 調整篩選` · No audit entries match · adjust filter |
| AI L2 output | — | `L2 推理閒置 · 上次 03:17` · L2 reasoning idle · last 03:17 |
| Replay results | 無回測 | `尚未執行回測 · 選區間後執行` · No replay run · pick range then run |
| IBKR positions | N/A | `帳戶未連線 · 待 Phase 2` · Account not linked · pending Phase 2 |

### 6.2 Error-state formula

`{發生什麼} · {怎麼修}` — cause then fix, no blame, no apology, two clauses max. Include the machine-actionable detail (endpoint, code, field) so the operator can act or escalate.

| Error class | zh copy | EN tooltip |
|---|---|---|
| Save failed (validation) | `儲存失敗 · daily_loss_cap 須 > 0` | Save failed · daily_loss_cap must be > 0 |
| Save failed (write) | `儲存失敗 · 引擎未回應 · 重試或檢查心跳` | Save failed · engine unresponsive · retry or check heartbeat |
| Order rejected (gate) | `成本閘攔截 · edge 1.2bps < 門檻 11bps` | Rejected by cost gate · edge 1.2bps < 11bps threshold |
| Order rejected (risk) | `風控攔截 · 超 max_position (20)` | Rejected · exceeds max_position (20) |
| Auth failure | `授權失效 · 重新認證` | Authorization expired · re-authenticate |
| API rate limit | `Bybit 限流 · {retry}s 後重試` | Rate limited · retry in {retry}s |
| Contract violation | `契約違反 · fills 缺 fee column · 已 fail-closed` | Contract violation · fills missing fee column · failed closed |
| Network | `連線中斷 · 檢查 Tailscale` | Connection lost · check Tailscale |
| Unknown 5xx | `引擎錯誤 5xx · 已記錄 · {req_id}` | Engine error 5xx · logged · {req_id} |

**Error voice rule:** an error is a *fact about the system state*, delivered flat. `成本閘攔截 · edge 1.2bps < 門檻 11bps` — no "unfortunately", no "we couldn't", no emoji. The operator reads it, knows exactly why, decides next move.

---

## 7. WORKED EXAMPLES — real console screens

### 7.1 Live tab — header & KPI strip

```
LIVE · 實盤   ● 引擎在線 14:41:22        [--live env chip, top-left, red hairline]
─────────────────────────────────────────────────────────────
今日淨            權益            未實現         保證金率
+$1,204          $48,207         −$842          18.4%
▲ +2.5%          —               ▼ Long 0.42     🟡 注意
```
- Env chip `LIVE · 實盤` = Mode C (bilingual, real-money surface).
- Column labels 今日淨/權益/未實現/保證金率 = Mode A (`title=` English).
- `▲/▼` = redundant directional encoding; sign + color + arrow.
- `保證金率 18.4%` with amber `注意` = margin-ratio warning band, second-channel (icon + text) not color-only.
- Values `tabular-nums slashed-zero`, `−` = U+2212.

### 7.2 IBKR governance banner (blocked / not-collected state)

Full-width, `--bg-raised`, `--border-subtle`, dashed left edge, **not** an error color (it's a plan, not a fault):

```
┌ ▢ 股票 / ETF · IBKR ──────────────────────────────────────
│  帳戶未連線 · 待 Phase 2
│  Account not linked · pending Phase 2
│  此車道為唯讀佔位 · 無下單路徑 · 資料採集未啟動
│                                          [ 查看路線圖 → ]
└───────────────────────────────────────────────────────────
```
- Heading = Mode C (lane label bilingual, first-encounter cross-lane surface).
- Body states three facts: read-only, no order path, collection not started — kills any ambiguity about whether it's broken vs. not-yet-built.
- CTA `查看路線圖` is the only affordance — no fake "連線" button (would violate `feedback_no_dead_params`).

### 7.3 Risk-config save (benign confirm → toast)

Flow:
1. Operator edits 3 fields; a `● 3 項未儲存變更` dirty-indicator appears (amber dot + count).
2. Clicks `儲存風控` (`--warn` accent).
3. Modal §5.3 renders (five slots, no typed phrase — reversible).
4. Confirms → toast: `已儲存風控設定 · 3 項變更 · 即時生效` (auto-dismiss 4s).
5. Dirty indicator clears to `● 已同步 14:42:05`.

If write fails: toast replaced (not stacked) by `儲存失敗 · 引擎未回應 · 重試或檢查心跳`, dirty state **retained** (changes not lost).

### 7.4 Flatten confirm (real-money, full friction)

Exactly the §5.4 modal. Sequence of copy states after confirm:
1. Button label while submitting: `送出中…` (disabled).
2. Toast on submit: `已送出平倉 · BTCUSDT · 待成交` (**not** "done").
3. Toast on broker fill: `已成交 · BTCUSDT 平倉 @ $61,198 · 已實現 −$838`.
4. Positions row transitions to empty state: `無開倉 · 引擎待信號`.

Note the estimated `−$842` in the confirm becomes the *actual* `−$838` in the fill toast — the estimated-state (§4.1 `~ 估算`) resolves to a confirmed number, and the copy makes that transition visible rather than silently swapping.

### 7.5 Gate rejection in the audit stream

```
14:43:18  拒單 · grid_short BTCUSDT     Rejected
          成本閘 · edge 1.2bps < 門檻 11bps
          cost_gate · S2
```
- `拒單` Mode A; `cost_gate` / `S2` Mode B tokens inline.
- Names the strategy, the gate, and the quantified reason — an operator can decide "expected" vs "investigate" in one glance, no drill-down needed.

---

## APPENDIX — Authoring checklist (paste into PR template)

- [ ] No apology / first-person-assistant / hedge strings.
- [ ] Every label resolves via `lbl()` / `lblBoth()` / `.tok` — zero raw CJK literals in templates.
- [ ] Mode C budget not exceeded (grep `lblBoth(` ≤ cap).
- [ ] New recurring terms added to `labels.js` lexicon (§3), not synonym-invented at call-site.
- [ ] Every numeric: signed if delta, unit muted 11px, `tabular-nums`, U+2212 minus, fixed precision.
- [ ] Every data state distinct — no `N/A` collapse (§4 matrix). Stale shows age. Degraded shows fallback.
- [ ] Buttons = verb + object; toast echoes button words; destructive verbs `--neg`/`--live` styled.
- [ ] Real-money action = five-slot confirm + `⚠ REAL FUNDS · 實盤資金` + typed object-specific phrase + separated disabled button + no optimistic "done" toast.
- [ ] Errors = cause + fix, machine detail included, no blame.

---

*This is content-layer spec only. It presumes the S1 token set (surfaces, `--pos/--neg/--warn/--live`, type scale, `tabular-nums`) already in place; every string above must render against those exact tokens.*