---
name: bilingual-comment-style
description: OpenClaw §七 強制雙語注釋規範；TW agent 主寫；E2 PR 審查必查。中文寫「為什麼」/ 英文寫技術名詞與 invariant。
allowed-tools: Read, Grep, Glob, Edit, Write
---

# Bilingual Comment Style（雙語注釋規範）

## 何時觸發

- TW 收到「補注釋」「文檔翻譯」「雙語對照修正」
- E2 PR 審查時 `grep -L "中文"` 或 `grep -L 'MODULE_NOTE'` 等揭露缺注釋的新代碼
- 新增 函數 / 類 / 模組 / fail-closed 路徑 / 安全代碼

## CLAUDE.md §七 規定（必背）

> 每個新建/修改的函數、類、模塊必須中英對照注釋（MODULE_NOTE / docstring / inline / fail-closed 路徑 / 安全代碼）。

關鍵字：**MODULE_NOTE**（模組頂部）+ **docstring**（函數/類）+ **inline 雙語**（複雜邏輯/不變量）。

## 何處中文 / 何處英文

| 內容 | 語言 | 原因 |
|---|---|---|
| 模組目的 | 中 + 英 | operator 中文母語 + 全球可讀 |
| 業務邏輯「為什麼這樣做」 | **中文優先** | 表達精準、上下文濃 |
| 技術術語（`async/await`/`tokio`/`PyO3`） | **English** | 專有名詞不譯 |
| API 端點命名 / SQL schema | **English** | 跨工具一致 |
| 不變量 / SAFETY 注釋 | 中 + 英 | 安全代碼雙保險 |
| 過去式（commit message / PR） | English | git 工具鏈友好 |
| 錯誤訊息（user-facing） | 中 + 英 | GUI 雙標 |
| TODO / FIXME / NOTE | 中文（含上下文） | tag 用 English |

## 模板

### Rust 模組頂部
```rust
// ─────────────────────────────────────────────────────────
// MODULE_NOTE
// 模組目的：tick pipeline 處理單筆 K-line tick，產出 intent 候選後送
//          governance 審批。屬交易 hot path，~1ms SLA。
// Module purpose: handle single K-line tick, generate intent candidates,
//                 forward to governance approval. Trading hot path, ~1ms SLA.
//
// 關聯文件：CLAUDE.md §五 架構總覽 · DOC-01 §5.9 hard stop-loss
// 上游：BybitWsListener 推 PriceEvent
// 下游：IntentProcessor → Guardian → submit_intent
// ─────────────────────────────────────────────────────────
```

### Rust 函數
```rust
/// 計算 ATR 倍數動態止損（持倉期 Wilder's ATR）。
/// Compute ATR-based dynamic stop-loss (in-position Wilder's ATR).
///
/// SAFETY / 不變量：
/// - `period` 必為 1m，視窗 14（CLAUDE.md §三 P0-13 ATR scale 修正後）
/// - 回傳 `None` 時呼叫端必 fail-closed（不進場 / 持倉繼續舊 stop）
///
/// # Arguments
/// - `kline`: 1m OHLCV，最近 ≥ 14 根
///
/// # Returns
/// - `Some(stop_pct)`：0.05% – 0.5% 範圍
/// - `None`：資料不足或 NaN
pub fn compute_atr_stop(kline: &[Ohlcv]) -> Option<f64> { ... }
```

### Python 模組
```python
"""
模組目的：edge_estimator scheduler daemon，每小時刷新
          settings/edge_estimates.json（每 strategy::symbol 的 grand_mean / shrunk_bps）。

Module purpose: edge_estimator scheduler daemon, refresh
                settings/edge_estimates.json hourly (per strategy::symbol
                grand_mean / shrunk_bps).

CLAUDE.md §三 G1-01 / TODO.md Wave 1
上游：trading.fills / learning.exit_features
下游：cost_gate / promotion 邊界門檻

Leader election：flock 在 $OPENCLAW_DATA_DIR/edge_scheduler.lock，
                 確保 uvicorn --workers 4 只一個 worker 跑。
"""
```

### Python 函數
```python
async def submit_intent(
    intent: TradeIntent,
    actor: str,
    lease_id: str,
) -> SubmitResult:
    """
    提交交易意圖經 Guardian 審批 / Submit trade intent through Guardian.

    必經路徑（CLAUDE.md §二 原則 1 + 4）：
    意圖 → Guardian.evaluate → 通過 → IntentProcessor.dispatch
    任一拒絕 → fail-closed（return SubmitResult(ok=False, reason=...)）

    Args:
        intent: 交易意圖（symbol/qty/side/price）
        actor: 執行者（must be in ['operator', 'strategist'])
        lease_id: 已 acquired 的 lease id（未過期）

    Returns:
        SubmitResult.ok=True 表示已下單成功；False 帶 reason

    Raises:
        AuthError: actor 角色不夠
        LeaseExpiredError: lease 已過期
    """
    ...
```

### Inline 不變量
```rust
// 不變量 / Invariant: positions.len() ≤ MAX_OPEN_POSITIONS
// 違反 = Guardian P0 拒絕新單前已有 race；報 telemetry。
debug_assert!(positions.len() <= MAX_OPEN_POSITIONS);
```

```python
# 為什麼 fail-closed：authorization.json 失效時，下游 IPC 還沒收到
# cancel_token，但本路徑必須立即拒絕，避免新單漏網。
# Why fail-closed: when authorization.json invalidates, downstream IPC may
# not have received cancel_token yet; this path must reject immediately to
# prevent leaking new orders.
if not auth.is_valid():
    return Err("authorization invalid")
```

## E2 必查 Grep

```bash
# 新檔無 MODULE_NOTE
grep -L 'MODULE_NOTE\|模組目的' <new-files>

# 新函數無 docstring
# Python：def 後無 """ 開頭即標
# Rust：fn 前無 /// 即標

# 純英文長段（≥ 5 行 comment 全英）→ 業務說明缺中文
# 純中文長段（無任何 English 技術詞）→ 跨團隊不友好
```

## 反模式（見即標）

- 只英文不解釋為什麼（純翻譯式 doc）
- 只中文無技術詞（`use ArcSwap` 譯成「原子交換」反而不清）
- `# TODO: fix this`（無中文上下文 / 無 ticket）
- 抽象描述「處理數據」/「Process data」（無資訊）
- inline 注釋 chinese-only 但 stack trace / log 全英文 → debug 時對不上
- 重要不變量（SAFETY / Invariant）只一種語言

## 工作流（TW 補注釋）

1. `git diff <base>...HEAD` 抽改動範圍
2. 對每個新增 / 重大修改 函數、類、模組逐一檢查 6 種注釋是否齊備（MODULE_NOTE / docstring / inline / fail-closed / SAFETY / TODO 上下文）
3. 缺項 Edit 補上（**只補注釋，禁改邏輯**）
4. 報告：補了 N 處 / 哪些檔 / 是否觸發 §七 違規 → E2 通報

## 輸出格式

```markdown
# TW 雙語注釋審查 — <commit> · <date>

範圍：<files>

## 補上的注釋
| 檔:行 | 類型 | 補前 | 補後 |
|---|---|---|---|
| foo.rs:42 | docstring | 缺 | 中英對照 + SAFETY |

## E2 違規警示
（觸發 §七 規則的點）

## 邏輯問題（順帶發現，回 E1）
（不在本職範圍但發現的 bug）
```
