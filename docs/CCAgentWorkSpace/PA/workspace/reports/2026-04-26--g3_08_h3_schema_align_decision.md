# G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN — A/B/C 決策設計（PA Plan Only）

- **作者**：PA（Project Architect）
- **日期**：2026-04-26
- **狀態**：Plan only — 不寫實作代碼
- **Tier**：6 Track 2（Tier 5 sign-off `f4c5bad` MED-1 follow-up）
- **依賴前置**：G3-08 Phase 2 H1+H3 已 land（commits `9120948` + `f2ed286`，2026-04-26）
- **解阻 後續**：G3-08 Phase 3 接 real EngineIPCClient fetcher（H2+H4+H5，3.5d 預估）
- **本 RFC 範圍**：H3RouteStats schema 對齊單一決策，**不**動 H1/H2/H4/H5/AgentState

---

## §1 背景：Tier 5 MED-1 Finding 重述

E2 Tier 5 batch review report `docs/CCAgentWorkSpace/E2/workspace/reports/2026-04-26--tier5_batch_review.md` §T5.3-MED-1（line 98-108）發現：

> Python `model_router.get_h3_snapshot()` 10 keys vs Rust `H3RouteStats` 7 fields **0/7 完全對齊**。Runtime impact = 0（Phase 2 production 仍跑 `StubHStateFetcher` 回 `default()`，`main_boot_tasks.rs:385` 接線確認），但 Phase 3 接 real fetcher 時 Rust serde 會把所有 H3 欄位 silently default 成 0（因 `#[serde(default)]` forward-compat 規則 → unknown key 落地時被 ignore，known key 缺則默認 0）。**Silent regression 潛在 schema 契約**。

E2 推薦 PM 開 `G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN`（~30min，Phase 3 落地前必修），由 PA design 主導 A/B/C 三選一。**本報告即此設計**。

### 1.1 為什麼 Phase 3 前必修

Phase 3（PA G3-08 design plan §10.3，commits 預計 ~3.5d）會：

1. 新建 `RealHStateFetcher`（替換 `poller.rs:99 StubHStateFetcher`）→ 透過 `EngineIPCClient` reverse-IPC pull `query_h_state_full`
2. Phase 3 同時接 H2（Layer2CostTracker）/ H4（h4_validator）/ H5（cost_logging）
3. 接通後 Rust hot-path consumers（cost_edge_ratio、healthcheck [20] 升級版、未來 G3-09 cost-aware shrink）開始查 `cache.snapshot().h3.l1_9b` 等欄位

**Phase 3 land 後若 schema 不修**：`cache.snapshot().h3.l1_9b == 0`、`h3.cache_hit == 0`（forward-compat 把 `l1_9b_count` / `l2_cache_hit` 當未知欄位 ignored，known field `l1_9b` 未填默認 0）。**所有 H3 觀測數值永遠 0**，cost_edge_ratio 演算法 + healthcheck [20] 升級會看到完全錯誤的 routing 分布。**最危險**：因為 schema parse 不會 raise（forward-compat 設計），bug 是純 silent — log 看不到任何錯誤，只會看到 H3 永遠空。

**因此 Phase 3 land 前必先做完此 RFC + 對應 align fix commit**，否則 Phase 3 是 silent-regression 隱形地雷。

---

## §2 現況對照表

### 2.1 Side-by-Side schema mismatch

| 概念 | Python `get_h3_snapshot()` key（model_router.py:471-481） | Rust `H3RouteStats` field（types.rs:75-92） | 對齊度 |
|---|---|---|---|
| 路由總呼叫次數 | `total_routes` | **缺** | ❌ Rust 無 |
| L1-9B tier 計數 | `l1_9b_count` | `l1_9b` | ⚠️ 後綴差 |
| L1-27B tier 計數 | `l1_27b_count` | `l1_27b` | ⚠️ 後綴差 |
| L1.5 tier 計數 | `l1_5_count` | `l1_5` | ⚠️ 後綴差 |
| L2 tier 計數 | `l2_count` | `l2` | ⚠️ 後綴差 |
| 預算拒絕計數 | `budget_denied_count` | **缺** | ❌ Rust 無 |
| L2 cache 命中 | `l2_cache_hit` | `cache_hit` | ⚠️ 前綴差 |
| L2 cache 過期清除 | `l2_cache_expired` | `cache_expired` | ⚠️ 前綴差 |
| L2 cache 寫入 | `l2_cache_stored` | **缺** | ❌ Rust 無 |
| L2 cache 當前大小 | `cache_size` | `cache_size` | ✅ 唯一對齊 |

**統計**：10 Python key vs 7 Rust field，**1/7 真正對齊（cache_size）**，6/7 命名 drift（後綴 `_count` 或前綴 `l2_`），3/10 Python key 在 Rust 不存在。

### 2.2 字面差異本質

差異可拆兩類：

| 類別 | 範圍 | 可逆性 |
|---|---|---|
| **A. 命名 drift（cosmetic）** | 6 個欄位後綴 `_count` 或前綴 `l2_` | 雙邊都好改，無資訊損失 |
| **B. 缺欄（語意）** | Rust 缺 `total_routes` / `budget_denied_count` / `l2_cache_stored` | Rust 必須加（否則 H3 觀測不完整） |

**B 必須擴 Rust schema**（無法靠重命名解決），**A 是純風格選擇**（rename Python or rename Rust）。

### 2.3 語意正確性：哪邊是 SSOT？

- Python `get_h3_snapshot()` 是 **真實 source-of-truth**：`_routing_stats` dict（model_router.py:114）內部維護，每次 `route()` exit branch + L2 cache event 即時更新。10 key 是**設計意圖**（含 `total_routes` 用於 ratio 計算、`budget_denied_count` 用於 H2 預算 gate 觀測、`l2_cache_stored` 用於 cache turnover 觀測）。
- Rust `H3RouteStats` 是 **PA design plan §5.2 的草稿 schema**（commit `7564d07` PA 寫的，Phase 1 stub fetcher 不需要真實欄位故當時偷懶只列 7 個典型 H3 metric）。**這是 PA 草稿失誤的 schema**，非 source-of-truth。

**結論**：Python 端是正確 schema，Rust 端 PA 草稿不全。

### 2.4 Test 阻力盤點

`test_model_router.py` 對 Python 命名硬編碼依賴的 callsite 數：

```bash
grep -E '_routing_stats\["(l1_9b_count|l1_27b_count|l1_5_count|l2_count|budget_denied_count|l2_cache_hit|l2_cache_expired|l2_cache_stored)"\]|snap\["[a-z_]+"\]' \
  test_model_router.py | wc -l
```
實測 **30+ 個 assertion 直引 Python key 名**（如 `r._routing_stats["l1_9b_count"]` / `snap["l1_9b_count"]`）。

`test_h_state_query_handler.py` line 70-77 同樣 hardcode `l1_9b_count` / `l2_cache_hit` / `l2_cache_stored` 等 Python key。

**外部 Python consumer**：grep 確認 `_routing_stats` 在 `strategist_agent.py` 也有同 key 使用（caller stats 共享 `l2_cache_hit` / `l2_cache_stored` key，model_router.py:408 寫入）→ 改 Python rename = 連鎖改 StrategistAgent stats 字典 + Strategist 內所有 metric 顯示 + 任何 GUI 走 stats endpoint 的 consumer。

**Rust consumer**：grep `H3RouteStats` 確認**目前 0 個 hot-path consumer**，只 types.rs 定義 + mod.rs re-export 兩處。改 Rust schema = 純內部 struct rename + 對應 4-5 unit test fixture 改動。

---

## §3 Option A：Python 端 rename 對齊 Rust

### 3.1 機制

把 Python `get_h3_snapshot()` 改回傳 Rust 既有 7 個 field 名（drop `_count` 後綴 / drop `l2_` 前綴），同時擴 Rust 加 3 個缺欄（`total_routes` / `budget_denied_count` / `l2_cache_stored`）—— 因為 B 類缺欄無法只靠 Python rename 解決。

**Python diff（model_router.py:471-481）**：
```python
snapshot: Dict[str, Any] = {
    "total_routes":        stats_copy["total_routes"],         # 保留（Rust 也加）
    "l1_9b":               stats_copy["l1_9b_count"],          # rename (drop _count)
    "l1_27b":              stats_copy["l1_27b_count"],
    "l1_5":                stats_copy["l1_5_count"],
    "l2":                  stats_copy["l2_count"],
    "budget_denied":       stats_copy["budget_denied_count"],  # rename (drop _count)
    "cache_hit":           stats_copy["l2_cache_hit"],         # rename (drop l2_)
    "cache_expired":       stats_copy["l2_cache_expired"],
    "cache_stored":        stats_copy["l2_cache_stored"],
    "cache_size":          cache_size,                          # 已對齊
}
```
**Python `_routing_stats` 字典 key 也得跟改**（114-124 行）以維持 single-source naming。

**Rust diff（types.rs H3RouteStats）**：加 3 個欄位 `total_routes` / `budget_denied` / `cache_stored`：
```rust
pub struct H3RouteStats {
    #[serde(default)] pub total_routes: u64,         // 新增
    #[serde(default)] pub l1_9b: u64,
    #[serde(default)] pub l1_27b: u64,
    #[serde(default)] pub l1_5: u64,
    #[serde(default)] pub l2: u64,
    #[serde(default)] pub budget_denied: u64,        // 新增
    #[serde(default)] pub cache_size: u64,
    #[serde(default)] pub cache_hit: u64,
    #[serde(default)] pub cache_expired: u64,
    #[serde(default)] pub cache_stored: u64,         // 新增
}
```

### 3.2 五維評估

| 維度 | Option A 評分 |
|---|---|
| **影響範圍** | Python `model_router.py` ~12 行（`_routing_stats` dict + 4 個 `_record_route` counter_key + `get_h3_snapshot` 10 行） · Rust `types.rs` +3 fields ~10 行 · `test_model_router.py` ~30+ assertion 全改 · `test_h_state_query_handler.py` ~7 行 · `strategist_agent.py` 內呼叫 `_routing_stats["l2_cache_hit"]` / 寫入 `caller_stats["l2_cache_hit"]` 等 ~3-5 處需更新 · GUI 端**未 inventory**（任何 GUI 走 H3 stats endpoint 的 callsite 全潛在 break）。**淨改動：Rust ~10 行 + Python+test ~50+ 行**。 |
| **語意正確性** | ⚠️ **倒退**。Python 是真實 SSOT，naming intent 是「明示 metric 性質」（`l1_9b_count` 比 `l1_9b` 更清楚是 counter；`l2_cache_hit` 比 `cache_hit` 更明示是 L2 cache 而非 model_router 自身 cache）。Drop suffix/prefix 失資訊。 |
| **Phase 3 affordability** | ✅ Rust hot-path lookup 看到 `cache.snapshot().h3.l1_9b` 即真實值。但需 Rust 端在 Phase 3 land 前已被改完（因 Rust 加 3 fields）。 |
| **Backward compat** | ⚠️ **break**。Python `_routing_stats` 內部 key + GUI endpoint response field name 同步變動，任何外部 consumer（cron / Mac GUI / 第三方 dashboard）需同步更新。 |
| **執行工時** | ~1.5h（Python rename + Rust 3 field add + 30+ test assertion 改 + Strategist callsite 改 + GUI inventory + smoke）。 |

**致命短板**：語意倒退 + 連鎖改 Python ecosystem（30+ test + Strategist + GUI 全 break）。

---

## §4 Option B：Rust 端 rename 對齊 Python

### 4.1 機制

擴 Rust `H3RouteStats` 加 3 個缺欄 + 重命名 4 個既有 field 用 Python 名。Python 端 0 變動。

**Rust diff（types.rs H3RouteStats）**：
```rust
pub struct H3RouteStats {
    #[serde(default)] pub total_routes: u64,             // 新增
    #[serde(default)] pub l1_9b_count: u64,              // rename: l1_9b → l1_9b_count
    #[serde(default)] pub l1_27b_count: u64,
    #[serde(default)] pub l1_5_count: u64,
    #[serde(default)] pub l2_count: u64,
    #[serde(default)] pub budget_denied_count: u64,      // 新增
    #[serde(default)] pub l2_cache_hit: u64,             // rename: cache_hit → l2_cache_hit
    #[serde(default)] pub l2_cache_expired: u64,
    #[serde(default)] pub l2_cache_stored: u64,          // 新增
    #[serde(default)] pub cache_size: u64,               // 已對齊
}
```

**Python**：0 變動（保持既有 10 key）。

**Test fixture**：`rust/openclaw_engine/src/h_state_cache/types.rs` 內 5 個 unit test 改 4 個 field 引用（`h3.l1_9b` → `h3.l1_9b_count`）。

### 4.2 五維評估

| 維度 | Option B 評分 |
|---|---|
| **影響範圍** | Rust `types.rs` 改 4 fields + 加 3 fields ~13 行 · Rust `tests.rs` 5 tests fixture ~10 行 · Python **0 行變動**（含 model_router / strategist_agent / handler / 30+ existing tests）· Rust `mod.rs` re-export ~0 變動（pub use 自動跟）· GUI **0 行變動**（Python endpoint 字符不變） · Phase 3 real fetcher Rust 端**0 額外 alignment 工**（forward parse 直接對齊）。**淨改動：Rust ~25 行 + Python+GUI 0 行**。 |
| **語意正確性** | ✅ Python intent 是 SSOT，Rust 跟 Python 命名 = 兩邊一致 + 真實表達 metric 語意（`l1_9b_count` 比 `l1_9b` 清楚是 counter；`l2_cache_*` 明示來源）。 |
| **Phase 3 affordability** | ✅ 最佳。Phase 3 `RealHStateFetcher` parse Python JSON → 全 10 key 直接對齊 Rust struct field name → serde deserialize 一條 line 完事，0 額外 mapping。Hot-path consumer (`cache.snapshot().h3.l1_9b_count`) lookup 直接看到 Python push 的數字。 |
| **Backward compat** | ✅ Python `_routing_stats` 0 變動 → 任何 Python ecosystem consumer 不破。Rust H3RouteStats 從未被 hot-path 消費（grep 0 callsite），改命名等於改未公開 API。**唯一破壞**：rust unit tests fixture（在同 file 內）跟改即可。 |
| **執行工時** | ~30min（Rust 改 4 rename + 加 3 field + 5 tests fixture 同步 + cargo test --release）。 |

**亮點**：影響範圍最小（純 Rust 內部）+ 語意對齊 SSOT + Phase 3 affordability 最高。

---

## §5 Option C：加 explicit mapping/adapter layer

### 5.1 機制

兩端各保留現有 schema，**在 Rust `RealHStateFetcher` 解析時加一層 explicit field-name mapping**：

```rust
// rust/openclaw_engine/src/h_state_cache/poller.rs (Phase 3 RealHStateFetcher)
fn parse_h3_with_mapping(json: &serde_json::Value) -> Result<H3RouteStats, ParseError> {
    Ok(H3RouteStats {
        total_routes:    json.get("total_routes").and_then(|v| v.as_u64()).unwrap_or(0),  // Rust 仍需加 field
        l1_9b:           json.get("l1_9b_count").and_then(|v| v.as_u64()).unwrap_or(0),
        l1_27b:          json.get("l1_27b_count").and_then(|v| v.as_u64()).unwrap_or(0),
        l1_5:            json.get("l1_5_count").and_then(|v| v.as_u64()).unwrap_or(0),
        l2:              json.get("l2_count").and_then(|v| v.as_u64()).unwrap_or(0),
        budget_denied:   json.get("budget_denied_count").and_then(|v| v.as_u64()).unwrap_or(0),
        cache_size:      json.get("cache_size").and_then(|v| v.as_u64()).unwrap_or(0),
        cache_hit:       json.get("l2_cache_hit").and_then(|v| v.as_u64()).unwrap_or(0),
        cache_expired:   json.get("l2_cache_expired").and_then(|v| v.as_u64()).unwrap_or(0),
        cache_stored:    json.get("l2_cache_stored").and_then(|v| v.as_u64()).unwrap_or(0),
    })
}
```

**或** 用 serde `#[serde(rename = "l1_9b_count")]` 在 Rust struct 加 rename attr：
```rust
pub struct H3RouteStats {
    #[serde(default, rename = "l1_9b_count")]  pub l1_9b: u64,
    #[serde(default, rename = "l2_cache_hit")] pub cache_hit: u64,
    // ... 其他 4 fields rename
    #[serde(default)] pub total_routes: u64,         // 新增（無 rename，名同）
    #[serde(default)] pub budget_denied: u64,        // 新增（serde rename = "budget_denied_count"）
    #[serde(default)] pub cache_stored: u64,         // 新增（serde rename = "l2_cache_stored"）
}
```
（serde rename = 等價但更乾淨，不必寫 manual parse fn）。

### 5.2 五維評估

| 維度 | Option C 評分 |
|---|---|
| **影響範圍** | Rust `types.rs` H3RouteStats 加 3 fields + 6 個 `#[serde(rename)]` attr ~16 行 · Rust `tests.rs` ~3-5 unit tests 補 serde round-trip 驗證 · **2 個 vocabulary（Python 一個 / Rust 一個）持續維護** · Python 0 變動 · 文檔（PA design §5.2）必須註明 mapping 雙語對照表 |
| **語意正確性** | ⚠️ **2 vocabulary 並存**。讀 Rust code 看到 `cache.h3.cache_hit` 但讀 Python JSON 看到 `l2_cache_hit`，跨語言 debug 需查 mapping 表。Cognitive load 增加。 |
| **Phase 3 affordability** | 🟡 中。serde rename 在 deserialize 路徑透明對齊（Phase 3 fetcher 0 額外手寫 parse）。但 Rust hot-path consumer 寫成 `cache.h3.cache_hit` 而非 `cache.h3.l2_cache_hit`，code review 需多一步翻譯。 |
| **Backward compat** | ✅ 兩端都 0 break（Python schema 不動 + Rust 既有 H3RouteStats public API 名稱保留）。 |
| **執行工時** | ~45min（Rust 加 3 fields + 6 rename attr + 3-5 round-trip tests + 文檔 mapping 表）。 |

**致命短板**：永久維持 2 vocabulary 增 cognitive overhead。對 1 個 schema 而言 acceptable，但設下「Rust ↔ Python 鏡射 IPC 用 mapping 解決命名 drift」的 anti-pattern 模板，未來 Phase 3-4 接 H2/H4/H5/AgentState 都會被引用為「就這樣 mapping 就好」 → 累積 4-5 vocabulary 並存負債。

---

## §6 Recommend

### **選 Option B（Rust rename + 加 3 field 對齊 Python）**

**一句話理由**：Python 是 H3 真實 SSOT、Rust H3RouteStats 是 PA 草稿且尚未被任何 hot-path 消費 → 改 Rust 影響面（~25 行 Rust 內部）遠小於改 Python（~50+ 行跨檔含 30+ test + Strategist callsite + GUI inventory），且避免 Option C 的雙詞彙永久維護負債。

### 6.1 Trade-off 表（決策矩陣）

| 評分 | A Python rename | B Rust rename ★ | C adapter mapping |
|---|---|---|---|
| 影響範圍 | ❌ Python ~50+ 行跨檔 | ✅ Rust ~25 行內部 | 🟡 Rust ~16 行 + 文檔 mapping |
| 語意正確性 | ❌ 倒退（drop intent） | ✅ Python SSOT 命名 | ⚠️ 2 vocab 並存 |
| Phase 3 affordability | ✅ direct lookup | ✅ direct lookup（最佳） | 🟡 Rust 端 rename 透明但需 cognitive 翻譯 |
| Backward compat | ❌ Python ecosystem break | ✅ 0 break（含 GUI） | ✅ 0 break |
| 執行工時 | ~1.5h | ~30min | ~45min |
| **總分** | 1/5 | **5/5** | 3/5 |

### 6.2 為什麼不是 Option C（細節）

C 的 serde rename 技術上完全可行，但 PA 視角看 4 個結構性問題：

1. **「Rust hot-path code 看到的 field 名 ≠ Python push JSON 的 key」** 是 schema drift 的形式化容忍，未來 reviewer / new maintainer 必須記住 mapping。對 1 個 schema 可接受，對 5 個 H module + 5 Agent = 10 schema 全用此 pattern → 10 個 mapping 表並存。
2. **Phase 3-4 接 H2/H4/H5/AgentState 時，每個 PA 草稿都會撞同樣命名 drift**（PA design plan §5.2 同樣是 PA 偷懶寫的草稿），若 C 模板被采用，後續每個 Phase 都會走 mapping 路徑 → 永久 N vocabulary。
3. **Phase 1A H State Cache 程式碼（mod.rs 200 LOC + poller.rs 200 LOC + types.rs 220 LOC）**還在嬰兒期，是改命名最便宜的時間點（無 hot-path consumer 鎖死命名）。一旦 Phase 3+ 有 consumer 引用 `cache.h3.cache_hit`，命名就會被鎖死，後悔重命名變難。
4. **Python is SSOT, Rust is mirror** 的 G3-08 設計大原則（PA design §1.4）：mirror 應該對齊 source，不該反過來逼 source 跟 mirror 妥協。Option C 是「mirror 不變、加翻譯層」 = 違反 mirror semantic。

### 6.3 為什麼不是 Option A（細節）

A 的吸引力是「Rust struct 命名簡潔（`l1_9b` 比 `l1_9b_count` 短）」，但：

1. Python 端 30+ test assertion + Strategist 內部 stats + 未盤點 GUI consumer = 改動風險未知總量
2. memory `feedback_risk_changes_scoped`：應「只改被要求的參數」，A 的命名變動連鎖到 Strategist + 全 test fixture，超出 G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN ticket scope
3. 改 Python rename 後若任何外部 consumer 漏 catch（如 GUI tab 顯示 `l1_9b_count`） = silent regression 出口（恰是本 RFC 想避免的問題）
4. memory `feedback_no_dead_params`：Python schema 是 already-live 真實 API，動 live API 命名 vs 動 dormant Rust struct，後者風險低 99%

---

## §7 執行 prompt template（給下次 session E1）

下次 session 主會話派 1 個 E1（單實例）執行此修。Plan 期估 30min，含 cargo test。**不需 isolation worktree**（單檔 Rust 改動 + tests）。

### 7.1 任務 prompt

```
PM Tier 6 Track 2 派發 — G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN E1 落地

## 背景

PA design RFC `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_h3_schema_align_decision.md` 推薦 Option B：Rust H3RouteStats rename 對齊 Python `get_h3_snapshot()` 10 keys。Phase 3 接 real fetcher 前必修。

## 改動文件

1. `rust/openclaw_engine/src/h_state_cache/types.rs`：H3RouteStats struct
2. `rust/openclaw_engine/src/h_state_cache/tests.rs`（若 unit test 引用 H3 fields）

## 具體修改

### types.rs H3RouteStats（line 75-92）替換為：

```rust
/// H3 ModelRouter route distribution / H3 路由分佈。
///
/// MODULE_NOTE (EN): Schema mirrors Python `model_router.get_h3_snapshot()`
///   10 keys (the SSOT). PA RFC `2026-04-26--g3_08_h3_schema_align_decision.md`
///   chose Option B (Rust rename to match Python) over Option A/C.
///   Reason: Python is SSOT, Rust H3RouteStats is mirror, mirrors should
///   align to source. All field names match Python `_routing_stats` dict
///   keys (model_router.py:114-124).
/// MODULE_NOTE (中)：Schema 鏡射 Python `model_router.get_h3_snapshot()` 10
///   個 key（SSOT）。PA RFC 採 Option B（Rust rename 對齊 Python）。所有
///   欄位名與 Python `_routing_stats` dict 相同。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct H3RouteStats {
    /// Total invocations of `route()` since boot. / 啟動以來 route() 總呼叫次數。
    #[serde(default)]
    pub total_routes: u64,
    /// L1-9B tier count (complexity < 0.5). / L1-9B tier 計數。
    #[serde(default)]
    pub l1_9b_count: u64,
    /// L1-27B tier count (moderate / no-upgrade / budget fallback). / L1-27B tier 計數。
    #[serde(default)]
    pub l1_27b_count: u64,
    /// L1.5 tier count (context-driven upgrade). / L1.5 tier 計數。
    #[serde(default)]
    pub l1_5_count: u64,
    /// L2 tier count (context-driven escalation). / L2 tier 計數。
    #[serde(default)]
    pub l2_count: u64,
    /// Budget-denied count (budget_checker rejected, fallback to l1_27b). / 預算拒絕次數。
    #[serde(default)]
    pub budget_denied_count: u64,
    /// L2 cache hit count from `check_l2_cache`. / L2 cache 命中次數。
    #[serde(default)]
    pub l2_cache_hit: u64,
    /// L2 cache expired-eviction count. / L2 cache 過期清除次數。
    #[serde(default)]
    pub l2_cache_expired: u64,
    /// L2 cache successful store count from `_store_l2_result`. / L2 cache 寫入次數。
    #[serde(default)]
    pub l2_cache_stored: u64,
    /// Current `_l2_result_cache` size (live snapshot, not counter). / 當前 cache 大小。
    #[serde(default)]
    pub cache_size: u64,
}
```

### tests.rs 任何引用 `h3.l1_9b` / `h3.cache_hit` 等舊名的測試 → 改為新名（`h3.l1_9b_count` / `h3.l2_cache_hit`）。
- 如 `snapshot_deserializes_with_unknown_fields` test 若有 H3 field 引用要對齊
- 跑 `cargo test --release -p openclaw_engine --lib h_state_cache` 確認綠

### 不改

- Python `model_router.py` / `h_state_query_handler.py` / `strategist_agent.py` / `test_model_router.py` / `test_h_state_query_handler.py`：**0 改動**（Option B 核心理由）
- Rust `mod.rs`：pub use 自動跟，0 改動
- Rust `poller.rs` Phase 1 stub fetcher：0 改動

## 加新 test

加 1 個 round-trip test 在 `tests.rs`，驗證 Python schema parse 正確：

```rust
#[test]
fn h3_route_stats_parses_python_schema() {
    let python_json = serde_json::json!({
        "total_routes": 100,
        "l1_9b_count": 60,
        "l1_27b_count": 25,
        "l1_5_count": 10,
        "l2_count": 5,
        "budget_denied_count": 2,
        "l2_cache_hit": 12,
        "l2_cache_expired": 1,
        "l2_cache_stored": 8,
        "cache_size": 7,
    });
    let h3: H3RouteStats = serde_json::from_value(python_json).expect("parse");
    assert_eq!(h3.total_routes, 100);
    assert_eq!(h3.l1_9b_count, 60);
    assert_eq!(h3.l1_27b_count, 25);
    assert_eq!(h3.l1_5_count, 10);
    assert_eq!(h3.l2_count, 5);
    assert_eq!(h3.budget_denied_count, 2);
    assert_eq!(h3.l2_cache_hit, 12);
    assert_eq!(h3.l2_cache_expired, 1);
    assert_eq!(h3.l2_cache_stored, 8);
    assert_eq!(h3.cache_size, 7);
}
```

## 驗證

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib h_state_cache"
# 期望：所有 h_state_cache tests pass + 新 round-trip 1 個 pass，total +1 vs baseline
```

## Commit

```
git commit -m "$(cat <<'EOF'
G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN: Rust H3RouteStats rename + 3 field add per PA Option B

- types.rs H3RouteStats: rename l1_9b→l1_9b_count, cache_hit→l2_cache_hit etc.
  + add total_routes / budget_denied_count / l2_cache_stored (3 missing)
- tests.rs: update existing fixture + add round-trip parse test for Python
  10-key schema
- Phase 3 unblock: Rust poller's RealHStateFetcher will now correctly
  deserialize Python's get_h3_snapshot() output without silent default-zero

Per PA RFC docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_h3_schema_align_decision.md
- Option B chosen (Rust rename to align Python) over A (Python rename) and
  C (serde rename adapter): Python is SSOT, Rust H3RouteStats had 0
  hot-path consumer, smallest blast radius (~25 LOC Rust internal vs A's
  ~50 LOC Python+test+GUI break vs C's permanent dual-vocab maintenance)
- Closes E2 Tier 5 batch review T5.3-MED-1

E1 落地，Linux verified cargo test --release -p openclaw_engine --lib +N

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git push origin main
ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"
```

## E2 review 重點

1. Rust struct field 名與 Python `_routing_stats` 字典 key (model_router.py:114-124) **逐一對齊**（10/10）
2. Round-trip test parse Python JSON dict 後所有 10 fields 值正確
3. cargo test --release lib 全綠（baseline 2210 + ~1 round-trip = ~2211）
4. Python 端**完全 0 改動**（grep `_routing_stats` Python 檔 / `get_h3_snapshot` callsite 無 diff）

## 完成標準

- E1：commit + push 成功，Linux pull 成功
- E2：approve（單檔 Rust 修改 + 1 unit test add，明顯）
- E4：cargo test --release h_state_cache 子集 pass

## 一行回報

```
TRACK 2 FUP DONE — G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN E1 commit <hash> pushed; cargo test pass; Phase 3 unblock
```
```

### 7.2 為什麼不必派 sub-agent

- 單檔 Rust 改動 + 加 1 個 unit test ~30min，主 agent 直寫即可
- 0 並行收益（單檔修改）
- E2 review 也只需單實例
- E4 只跑 cargo test --release h_state_cache 子集

---

## §8 Phase 3 dependency check

### 8.1 Phase 3 land 前**必先**做完此 fix

| Phase 3 步驟 | 對 H3 schema 對齊的依賴 |
|---|---|
| 8.1.1 Phase 3 Sub-task A：替換 `poller.rs:99 StubHStateFetcher` 為 `RealHStateFetcher`（透過 EngineIPCClient pull `query_h_state_full`） | ⚠️ **強依賴**。Real fetcher 解析 Python JSON → 所有 H3 fields 必須名稱對齊，否則 silent 落零（Phase 1 stub 永遠回 default 故未發現）。 |
| 8.1.2 Phase 3 Sub-task B：擴 `h_state_query_handler.py` 加 H2/H4/H5 buckets | 🟡 弱依賴。H3 桶已 land，schema align 與 H2/H4/H5 加新桶獨立，但 PA 建議 H3 修完再 land H2-H5（避免 1 commit 帶 4 個 schema mismatch 風險）。 |
| 8.1.3 Phase 3 Sub-task C：Rust hot-path consumer 開始查 H3 fields（如 G3-09 cost_edge_ratio 用 `cache.h3.l2_cache_hit` 估 cache turnover） | ⚠️ **強依賴**。一旦 hot-path code 出現 `cache.h3.<field>` 引用，命名鎖死，Option B 改名變更困難（callsite 連改）。 |

**結論**：Phase 3 開工**前**必先完成本 H3 schema align ticket。否則 8.1.1 + 8.1.3 落地時就成 silent regression / 後續難改的 schema lock-in。

### 8.2 Phase 3 派發前置 checklist（PM 用）

- [ ] G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN E1 commit landed
- [ ] cargo test --release `-p openclaw_engine --lib h_state_cache` 全綠
- [ ] Linux ssh `cd ~/BybitOpenClaw/srv && git pull --ff-only` 同步成功
- [ ] PA design plan §5.2 H3RouteStats schema 文檔同步更新（cosmetic，可此 commit 內 inline 改 docs/references 路徑或標 followup）

完成後 Phase 3 即可 land：H2 + H4 + H5 buckets + RealHStateFetcher + Rust hot-path consumer 一波 ~3.5d 派發。

### 8.3 Phase 4 (5-Agent) schema align 預警

PA design plan §5.2 `AgentState` 已用 `HashMap<String, i64>` forward-compat 設計，**Phase 4 不會撞 Phase 3 同類 schema mismatch 問題**（dynamic dict 不需 lock-step 命名對齊）。本 RFC 結論不外推到 Phase 4。

但 Phase 3 的 H2/H4/H5 各 struct（`H2BudgetState` / `H4ValidationStats` / `H5CostStats` 各約 3-5 fields）可能也有 PA 草稿命名 drift，**Phase 3 派發前 PA 應同類 audit 一次**（grep Python `get_h2_snapshot` / `get_h4_snapshot` / `get_h5_snapshot` 是否存在 + 對比 Rust types.rs 預設名）。建議 Phase 3 派發 prompt 加一條 prerequisite「先驗 H2/H4/H5 schema mirror 對齊」。

---

## §9 治理對照（CLAUDE.md §二 16 根原則）

- **原則 #6 失敗默認收縮** ✅：本 fix 解決的問題正是「H3 schema 不對齊 → silent 落零 → Rust hot-path 看到全 0 還照常運作 = 違反 fail-closed」。Option B 修完後 H3 fields 真實值流通，無 silent fallback。
- **原則 #8 交易可解釋** ✅：H3 路由統計（哪 tier 跑了多少次 / cache 命中率多少 / 預算拒絕了多少）是交易解釋的觀測層。schema 對齊後此觀測恢復可信。
- **原則 #10 認知誠實** ✅：silent regression 是認知誠實反例。本 fix 確保「Rust 端看到的 H3 數值 = Python 真實 source」這一基本誠實合約。
- **原則 #14 零外部成本可運行** ✅：本 fix 0 外部成本（不增 LLM call / 不需 Bybit API / 不需新 infra）。
- **§四 5 項 live 硬邊界** ✅：本 fix 0 觸碰（純 observability schema 對齊，與 live_reserved / authorization.json / OPENCLAW_ALLOW_MAINNET 全無交集）。

---

## §10 沒做的事（E1/E2 領域）

- 沒寫 Rust types.rs / tests.rs 任何實作代碼（E1 任務）
- 沒跑 cargo test --release -p openclaw_engine --lib h_state_cache
- 沒派 sub-agent（純 PA design 主 agent 串行讀+寫）
- 沒擴範圍到 H2/H4/H5 schema audit（Phase 3 派發前再做）
- 沒改 PA design plan §5.2 文檔（建議 E1 commit 同次 inline 加備註指本 RFC，或標 PM-followup）

---

## §11 教訓備忘

1. **PA 草稿 schema 是技術債** — PA design plan §5.2 H3RouteStats 是寫 design RFC 時偷懶（Phase 1 stub 不需要真實欄位故只列典型）。Mirror schema 應在 RFC 階段就**直接抄 SSOT 結構**，不要編造草稿。未來 PA 寫 IPC mirror RFC 必註明「此 schema = 抄 X 模組 Y 函數的真實 return dict」並引用 source code line。
2. **Phase 1 stub fetcher 隱藏 schema bug** — `StubHStateFetcher` 永遠回 `default()`，即 schema 命名錯誤也不會被任何測試 catch（fixture 全用 default 值）。Phase N+ 接 real producer 才會爆。**Plan 規範**：未來 stub fetcher pattern 必加一 round-trip test 用真實 producer 範例 JSON 驗證 schema 對齊（即使 stub 不真用此 JSON）。
3. **Schema mismatch ≠ schema drift** — 本案是 PA 草稿失誤，命名從 Phase 1 day 1 就錯，非演化 drift。未來 audit IPC schema 時應分清「同 commit 一致就 OK」vs「PA 草稿 vs 真實 SSOT 對齊」兩類問題。
4. **Option B 是「mirror 對齊 source」原則的具體實踐** — G3-08 design 一開始就說 Python = SSOT / Rust = mirror，但 PA RFC §5.2 自寫了 Rust schema，違反自己定的 SSOT 規則。本 RFC 是回歸該規則的修正。
5. **改 dormant 結構成本最低** — Rust H3RouteStats 0 hot-path consumer 是黃金時間窗，過 Phase 3 land 後成本陡增。**未來凡 Phase N stub → Phase N+1 real** 的過渡期必驗 schema 對齊（不要等 Phase N+1 接通才發現要改）。

---

## §12 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | G3-08-PHASE-2-FUP-H3-SCHEMA-ALIGN A/B/C 決策（推 Option B Rust rename 對齊 Python）| workspace/reports/2026-04-26--g3_08_h3_schema_align_decision.md |
