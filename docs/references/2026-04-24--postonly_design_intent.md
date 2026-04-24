# PostOnly 配置設計意圖（demo / live / paper 三環境對照）

**創建**：2026-04-24（G1-05 Wave 1 修正 FA v1 誤判）
**作者**：FA + E1 sub-agent
**對應 TODO**：G1-05 PostOnly 配置驗證
**對應 audit**：
- FA v1 誤判 → `docs/CCAgentWorkSpace/FA/workspace/reports/2026-04-24--4.24TodoAudit.md` § 7
- PA 核實正確 → `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-24--4.24TodoAudit_FixPlan_v2.md` § 1.2 Finding 2

---

## 1. TL;DR

系統存在 **兩個獨立的 PostOnly 控制旗**，FA v1 audit 將兩者混淆才得出「demo/live 反向」誤判。實測核驗：

| 控制層 | 欄位路徑 | demo | live | paper | 性質 |
|---|---|---|---|---|---|
| **策略入場（真實熱路徑）** | `strategy_params_*.toml::[<strategy>].use_maker_entry` | `true` | `false` | `true` | 真實 enforce，Rust strategy 內每次入場 tick 讀 |
| **Agent 風控偏好旗** | `risk_control_rules/risk_config_*.toml::[agent].post_only_limit` | `false` | `true` | `false` | 配置欄位存在但 Rust 引擎無 enforce point；GUI alias `use_post_only_for_limit`，待整合 |

**結論**：
- 策略熱路徑 `use_maker_entry` 配置 **完全符合原則 #6（失敗默認收縮）**：demo/paper 先驗證 PostOnly 正 net edge，live 維持 Market 保守路徑。
- 風控旗 `post_only_limit` 看似「demo/live 反向」是 declared-but-unread 配置欄位，**不影響運行時行為**；FA v1 把這個 surface 當主要 PostOnly 開關才產生誤判。

**修復動作**：本 doc 存檔 + TODO.md G1-05 標記 ✅ 完成 + memory log。**不修改任何 TOML**。

---

## 2. 兩個欄位的角色釐清

### 2.1 `strategy_params_*.toml::use_maker_entry`（策略入場真實開關）

**讀取點**：Rust 策略 mod.rs，每 tick 入場決策路徑。
- `rust/openclaw_engine/src/strategies/bb_breakout/mod.rs:661`
- `rust/openclaw_engine/src/strategies/ma_crossover/mod.rs`（同 pattern）
- `rust/openclaw_engine/src/strategies/grid_trading/mod.rs`（同 pattern）

**運行時邏輯**：
```rust
let (order_type, limit_price, time_in_force, maker_timeout_ms) =
    if self.use_maker_entry {
        let offset = self.maker_price_offset_bps / 10_000.0;
        let limit = if is_long {
            ctx.price * (1.0 - offset)  // BUY 掛 last_price 下方
        } else {
            ctx.price * (1.0 + offset)  // SELL 掛 last_price 上方
        };
        ("limit", Some(limit), Some("PostOnly"), Some(self.maker_limit_timeout_ms))
    } else {
        ("market", None, None, None)
    };
```

**Rust struct cold-boot default**：`use_maker_entry: false`（`bb_breakout/mod.rs:221`，註解明寫「冷啟動保守默認（根原則 #6）」）。TOML 才覆蓋為 true。

**本欄位三環境配置**（2026-04-21 EDGE-P2-3 Phase 1a/2+ 部署後）：

| 策略 | demo | live | paper |
|---|---|---|---|
| `[ma_crossover]` | `true` | `false` | `true` |
| `[bb_breakout]` | `true` | `false` | `true` |
| `[grid_trading]` | `true` | `false` | `true` |
| `[bb_reversion]` | （無此欄位）| （無此欄位）| （無此欄位）|
| `[funding_arb]` | （無此欄位）| （無此欄位）| （無此欄位）|

> bb_reversion 走 `use_limit` + `limit_offset_bps`（不同的 limit 路徑，非 PostOnly）。
> funding_arb 設計上吃 funding window，入場用 Market 即時對沖，無 PostOnly entry。

### 2.2 `risk_control_rules/risk_config_*.toml::[agent].post_only_limit`（風控偏好旗）

**Rust struct 定義**：`rust/openclaw_engine/src/config/risk_config.rs:520`
```rust
pub struct AgentConfig {
    pub prefer_limit: bool,
    pub reduce_only_close: bool,
    #[serde(default)]
    pub post_only_limit: bool,    // ← 此欄位
    pub partial_tp_enabled: bool,
    ...
}
```

**讀取狀態（2026-04-24 grep 結果）**：
- Rust 全 codebase 中 `post_only_limit` 僅出現在 `risk_config.rs` struct 定義 + `Default::default() { post_only_limit: false }`，**無任何業務邏輯讀此欄位**。
- Python 端 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_view_client.py:85` alias `"use_post_only_for_limit": "post_only_limit"` —— GUI 顯示用 view client，非執行路徑。

**性質**：declared-but-unread 配置欄位（GUI 偏好旗）；運行時 PostOnly 行為完全由 §2.1 的 `use_maker_entry` 決定。

**本欄位三環境配置**：

| 環境 | `[agent].post_only_limit` | 設計意圖（依配置脈絡推測，GUI surface only） |
|---|---|---|
| demo | `false` | demo 容忍 maker 不成交退 Market 的速度 |
| live | `true` | live 偏好強制 PostOnly（嚴格只做 maker） |
| paper | `false` | paper 最大探索，不限制下單型態 |

> 此「設計意圖」是依當前 TOML 數值反推的合理化敘述，並非真實在 Rust enforce — 故當 G3-02 ExecutorAgent live wiring 落地時須一併把這個欄位接到 OrderBuilder，否則 `use_maker_entry=false` + `post_only_limit=true` 在 live 會落到「Market 入場」而非「PostOnly only」。**已列為 G3-02/G3-03 隱含工作項**。

---

## 3. 設計理由（per environment × per layer）

### 3.1 `use_maker_entry` per env（策略熱路徑 — 真正執行的決策）

**demo = `true`**：
- EDGE-P2-3 Phase 1a/2+ 主要驗證面。原則 「Demo 先驗證」（CLAUDE.md §三 / `risk_config_demo.toml` 註腳）。
- 用意：grid_trading / bb_breakout / ma_crossover 的入場改 PostOnly Limit，將每次成交費率從 taker ~5.5 bps 降至 maker ~2 bps，攻 P1-10 結構性 fee-drag。
- 配套：`use_maker_entry=true` + `maker_price_offset_bps=1.0`（BUY 掛 last 下方 1 bps、SELL 掛上方 1 bps）+ `maker_limit_timeout_ms=45000`（45s 後 sweep timeout 防永久 resting）。
- 驗收門檻（G2-01）：1-2w demo 數據 maker fill rate ≥60% + 真實 fee 降幅達標。
- Healthcheck：`passive_wait_healthcheck.py` check `[3] maker_fill_rate`。

**live = `false`**：
- 嚴守原則 #6（失敗默認收縮）：未經 demo 驗證正 net edge 前 live 維持 Market 入場確定性。
- TOML 註腳明寫「live 維持 Market（根原則 #6）。Flip to true after demo validates positive net edge.」
- 為何 live 不一起用 PostOnly：(a) PostOnly 拒絕 → 等 sweep timeout → 錯失突破窗口，**滑點成本可能 > maker fee 節省**（ma_crossover/bb_breakout 對及時性敏感）；(b) demo 驗證未完成前 live 引入新行為違反 #6；(c) Phase 1b 拒絕/超時處理完成後才評估翻轉（TOML grid_trading 註腳）。
- 雖然 `use_maker_entry=false` 但 `maker_price_offset_bps` / `maker_limit_timeout_ms` 仍同步寫入 → schema parity，避免環境配置漂移；TOML 註腳「Plumbed for live TOML parity even though use_maker_entry=false means no PostOnly submits happen in live today; prevents schema drift between envs.」

**paper = `true`**：
- 紙盤鏡像 demo，保持探索資料的「費率代表性」與 live-target profile 對齊。
- TOML 註腳「mirrors demo so paper exploration matches live-target fee profile」。
- 本身 paper engine 在 2026-04-16 已預設關閉（`OPENCLAW_ENABLE_PAPER=1` 才 spawn，見 memory `project_paper_pipeline_disabled_by_default.md`），這個欄位主要是冷啟動 + 偶爾啟用紙盤 ad-hoc 驗證時生效。

### 3.2 `post_only_limit` per env（GUI/Agent 偏好旗 — 目前無 enforce）

> **重要免責聲明**：以下「設計理由」是依現存配置脈絡推測，因 Rust enforce point 不存在，無法以行為驗證；G3-02/G3-03 落地 ExecutorAgent live IPC 時要重新確認意圖。

**demo = `false`**：寬鬆，允許 PostOnly 拒絕後退 Market；配合 `use_maker_entry=true` 在策略層做主控制。

**live = `true`**：保守，「若要下 limit 必走 PostOnly」(GUI Agent 偏好)；嚴格 maker-only 行為，與 live 整體保守姿態一致。

**paper = `false`**：最大探索自由度，與 paper engine 設計（cascade tolerant、agent 有效止損 9%–54%）一致。

### 3.3 funding_arb 的 PostOnly 設定

**結論**：funding_arb 兩層都不掛 PostOnly。

- **`strategy_params_*.toml::[funding_arb]`** 三環境均**無** `use_maker_entry` 欄位 → struct cold-boot default `false` → 入場走 Market。
- **`risk_config_*.toml::[agent].post_only_limit`** 是全 agent 偏好旗，funding_arb 沒有單獨覆蓋；當前 funding_arb 在 demo + live 都 `active = false`（G-2 v2 NEGATIVE EDGE 結案），paper 為 `active = true`。
- **設計意圖**：funding_arb 收益模式 = 在 funding window 前抓 spot vs perp basis → 必須對沖即時建倉，PostOnly resting 風險過高（錯過 window = 收益歸零）。Market 入場是這類策略的標準做法。
- 待 R-02 Strategist 重評三參數後若重啟 funding_arb，仍維持 Market 入場路徑。

---

## 4. FA v1 為何誤判（避免將來再誤）

### 4.1 誤判內容

FA v1 audit（`2026-04-24--4.24TodoAudit.md` § 7）提：
> 配置檔 demo/live 反向：demo `post_only_limit = false`、live `post_only_limit = true`，違反原則 #6。

### 4.2 根因

1. **抓錯欄位**：FA v1 跑 `grep "post_only" settings/risk_control_rules/risk_config_*.toml`，命中 `[agent].post_only_limit`，當成主 PostOnly 開關；忽略策略熱路徑在 `strategy_params_*.toml::[<strategy>].use_maker_entry`。
2. **未做 enforce point 反查**：FA v1 沒進 Rust codebase 確認哪個欄位真正被讀；若做了會發現 `post_only_limit` 全 codebase 0 read site，是 GUI surface only。
3. **未對照 EDGE-P2-3 Phase 1a/2+ 部署敘述**：CLAUDE.md §三 / commit history 已詳述 EDGE-P2-3 Phase 1a/2+ demo 先 enable，FA v1 未交叉驗證。

### 4.3 防誤判規則（給未來 audit）

任何「PostOnly 配置反向」/「策略行為與宣稱不符」的指控，audit 流程必含：

1. **先抓 Rust codebase enforce site**：`grep` 對應欄位名在 `rust/openclaw_engine/src/`，確認有 business logic 讀，不只 struct define。declared-but-unread = config drift bait，非 runtime bug。
2. **對照部署敘述**：CLAUDE.md §三「已完成里程碑索引」/ commit message / memory 是否已記錄相關行為變更（本案 EDGE-P2-3 Phase 1a/2+ 在 2026-04-20/04-21 已部署且記載完整）。
3. **多欄位混淆檢查**：搜尋同關鍵字若命中多檔，逐一確認語意；若兩個欄位都叫 PostOnly 卻一個在 risk_config、一個在 strategy_params，必須各自分析。
4. **與 PM/PA cross-check**：FA 高嚴重度結論落地前先派一次 PA reality-check（本次 PA Round 2 verify 即時 catch FA v1 誤判）。

---

## 5. 與其他項目的關聯

### 5.1 P0-2 21d demo 穩定期（→ 2026-05-07 解鎖）

`use_maker_entry` 在 demo 驗證的 1-2w 窗口正落在 21d 穩定期內，本表是當期最大代碼/行為變更之一。21d 穩定期不重置時鐘的前提是「計劃性 rebuild/deploy 不重置」（見 CLAUDE.md §三），EDGE-P2-3 PostOnly 部署為計劃性，符合此排除規則。

### 5.2 G2-01 PostOnly 1-2w 驗證（→ 2026-05-07/08 出結果）

被動等待型 TODO，依賴 demo `use_maker_entry=true` 累積 ≥1w fills，由 `passive_wait_healthcheck.py` check `[3] maker_fill_rate` 6h cron 監控。本 doc 存檔不影響 G2-01 進度（純 design intent 釐清）。

### 5.3 G3-02 ExecutorAgent shadow→live toggle（Wave 2）

落地時須一併處理 `[agent].post_only_limit` 真實 enforce point：
- 若 G3-02 將 ExecutorAgent 接到 Rust IPC `SubmitOrder`，OrderBuilder 應讀 `risk_config.agent.post_only_limit` 決定 limit 訂單是否強制 PostOnly。
- 否則 live 環境 `post_only_limit=true` 是 silent dead config，未來 audit 會再被誤判。

---

## 6. 驗證清單（給未來 audit/operator）

| 項目 | 命令 | 預期 |
|---|---|---|
| 確認三環境 `use_maker_entry` | `grep "use_maker_entry" settings/strategy_params_*.toml` | demo/paper=true（ma_crossover/bb_breakout/grid_trading）、live=false |
| 確認三環境 `post_only_limit` | `grep "post_only_limit" settings/risk_control_rules/risk_config_*.toml` | demo/paper=false、live=true |
| 確認 Rust enforce point | `rg "use_maker_entry" rust/openclaw_engine/src` | mod.rs 入場路徑 + tests/params.rs |
| 確認 `post_only_limit` declared-but-unread | `rg "post_only_limit" rust/openclaw_engine/src` | 僅 `risk_config.rs` struct + Default |
| 確認 G3-02 落地時補接線 | TODO.md G3 群 | G3-02 RFC 應提及 post_only_limit enforce |

---

## 7. 結論

- **demo/live `use_maker_entry` 配置正確**：符合原則 #6 失敗默認收縮（live=false 保守，demo=true 先驗證）。
- **demo/live `post_only_limit` 配置不引發運行時問題**（無 enforce point），但屬於 latent config 須在 G3-02 落地時補接線，否則未來會再被誤判。
- **funding_arb 兩層都不掛 PostOnly** 是設計意圖（Market 即時對沖 funding window），無需 PostOnly。
- **FA v1 「demo/live 反向」誤判正式收回**，本 doc 存檔作為未來 audit 防誤判參考。

---

**參考文件**：
- TOML 三檔：`settings/strategy_params_demo.toml` / `_live.toml` / `_paper.toml`
- TOML 三檔：`settings/risk_control_rules/risk_config_demo.toml` / `_live.toml` / `_paper.toml`
- Rust 入場熱路徑：`rust/openclaw_engine/src/strategies/{bb_breakout,ma_crossover,grid_trading}/mod.rs`
- Rust 風控 struct：`rust/openclaw_engine/src/config/risk_config.rs:517-557`
- Python view alias：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/risk_view_client.py:85`
- EDGE-P2-3 部署敘述：CLAUDE.md §三 + 2026-04-20/04-21 commits（`7178d63` / `9edc6a4` / `b2d8ac5` / `f5f4dc2` / `8280132`）
- 相關 memory：`memory/project_track_p_runtime_live.md`、`memory/project_paper_pipeline_disabled_by_default.md`
