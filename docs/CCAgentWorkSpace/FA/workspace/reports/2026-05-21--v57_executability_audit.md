# v5.7 Dispatch-Safe Patch 執行性審核 — FA 視角

**日期**：2026-05-21
**Verdict**：GO-WITH-CONDITIONS
**One-line summary**：6/6 reviewer fix 已落地且 thesis 一致；但 5 個 strategy 與 Stage gate 的 acceptance criteria 從未在 v5.7 文檔內定義（指向「per AMD-2026-05-15-01」/「Sprint 2 evidence」），Sprint 1A 派發前必須收口 C10 端到端 + Earn governance + V103/V104 schema 三條業務鏈，否則 PA dispatch 會撞無錨點 acceptance。

## 0. 5 個 strategy 業務規格清晰度

| Strategy | 清晰度 | 證據 / 缺口 |
|---|---|---|
| **C10 funding harvest** | PARTIAL | v5.6 §2 line 62-63「spot+perp delta-neutral / 4.5-7% APR baseline」、Sprint 1B「主帳 $2,000 / Top-1 BTCUSDT / 簡單 long spot + short perp + quarterly rebalance」（v5.7 §8）— 缺：(a) 持倉檢測 / rebalance 觸發條件 / 偏離閾值；(b) funding rate 入場閾值；(c) 平倉條件；(d) Earn governance 與 spot leg 的資金路徑衝突解（C10 用 spot $2,000 vs Earn $800 USDT，誰先誰後沒寫） |
| **Unlock SHORT** | PARTIAL | v5.6 §6「Multi-condition triggers (T-3d + microstructure + funding state + macro state)」+ SSRN 24mo event study — 缺：(a) Tokenomist 信號 schema；(b) T-3d 是日曆日還是交易日；(c) microstructure / funding / macro 各 state 的具體閾值；(d) 入場 size formula；(e) 結算條件（unlock 後幾天平倉）；(f) macro state 在 Y1 是 counterfactual-only（§5），但 §6「Multi-condition triggers」仍引用 macro state — **內部矛盾** |
| **Pairs trading** | MISSING | v5.6 §3「BTC/ETH, ETH/SOL, etc」+ Sprint 2「rolling cointegration analysis (15m/1h)」— 缺：(a) 確定哪些 pair；(b) cointegration test statistic / p-value 閾值；(c) z-score 入場 / 平倉閾值；(d) hedge ratio 計算頻率；(e) max holding period；(f) correlation breakdown 自動退出規則 |
| **C13 defined-risk** | PARTIAL | v5.6 §5 詳列 default mode + 3 advanced modes + 4-confluence rule — 缺：(a) put 履約價選擇 algorithm（「8-12% OTM」是一個區間，不是 selection rule）；(b) DTE 範圍；(c) 多少 contracts；(d) roll 條件；(e) 觸發 advanced modes 的 4-confluence 各自閾值（IV-RV 15 vol points 有但 BTC 30d > +5%、cash buffer ≥ 2x、margin headroom > 50% 都是規則 OK 但「IV-RV 15 vol points」是經驗值還是工具量出來？沒交叉錨點） |
| **Funding short-only** | MISSING | v5.6 §2「20-40% APR when deployed (rare)」+ Sprint 2「high-threshold analysis」— 缺：(a)「high-threshold」是什麼 funding rate 閾值；(b) 入場 / 平倉條件；(c) max position；(d) 與 C10 funding harvest 業務隔離（兩者都用 funding rate，但方向相反，operator 拿什麼分流條件決定走哪個）；(e) §9 kill criteria「forced exit -20%」是被動 stop，但主動退出規則沒寫 |

## 0.5 Stage 0R/1/2/3/4 gate 條件清晰度

| Stage | 清晰度 | 證據 / 缺口 |
|---|---|---|
| **Stage 0R Replay Preflight** | PARTIAL | v5.6 §12「per AMD-2026-05-15-01」+ §6「30d shadow + Sharpe > 1.0 → Stage 0R」— 缺：(a) replay 數據窗口長度；(b) replay 必須對齊哪些真實 fill 路徑；(c) replay PASS / FAIL 觀察指標；(d) v5.7 / v5.6 都未 inline 抄這部分，全依賴 AMD-01 外部文件 — **PA dispatch 必須讀 AMD-2026-05-15-01 才能寫 acceptance**，但該文件未在 v5.7 §13 references 列出 |
| **Stage 1 Demo Micro-Canary** | PARTIAL | v5.6 §12「1 strategy × 1 symbol × 7d, REAL fills, Demo env」— 缺：(a) micro-canary 期間風險預算；(b) 失敗 rollback 流程；(c) attribution_chain_ok 等 invariant 是否強制 100%；(d) 7d 內最小樣本量（fills 數量） |
| **Stage 2 Demo Extended (14d)** | MISSING | v5.6 §12 僅一行 — 缺：(a) Stage 1 → Stage 2 promote 條件；(b) Stage 2 期間 size 是否擴大；(c) 與 Stage 1 的觀察指標差異 |
| **Stage 3 Demo Full (21d)** | MISSING | v5.6 §12 僅一行 — 缺：(a) 整套 acceptance；(b) attribution_chain_ok / per-strategy MIN_SAMPLES 是否在這階段達標 |
| **Stage 4 Live Pending** | PARTIAL | v5.6 §12「operator approval + 5-gate boundary」— 缺：(a) 5-gate 與 CLAUDE.md §四「五道閘」是否等價（CLAUDE.md §四列了 5 gate：live_reserved / Operator role / OPENCLAW_ALLOW_MAINNET / secret slot / authorization.json — v5.6 沒 inline 抄這個對照）；(b) Live size 起始額；(c) Live 階段觀察期長度；(d) 異常時自動降回 Demo 規則 |
| **v5.7 §11「5 reviewer conditions」** | CLEAR | 5/5 都有 inline reference / ✅ 標記，這部分清晰 |

## 1. Top 3 執行性風險（排序）

### Risk 1：Stage gate acceptance criteria 全部外掛 AMD-2026-05-15-01
- 嚴重度：CRITICAL
- 位置：v5.6 §12 / v5.7 §11
- 描述：v5.7 §11 列出 STAGE_0R → STAGE_4 5 階段，但每階段只一行；具體 PASS/FAIL 規則「per AMD-2026-05-15-01」外掛；v5.7 §13 references 未列 AMD-2026-05-15-01；v5.6 §15 references 也未列。**PA dispatch 寫 acceptance 時將無錨點**。
- 為何屬「執行性」（非邏輯）：思路本身 OK（依賴 governance 既有規範），但「執行可派發」要求文件能被 sub-agent 在離線 context 內讀完即懂；目前必須再 grep AMD 文件才能補完。
- Must-fix 建議：v5.7 patch 增 §11A 段或 appendix，inline 抄 AMD-2026-05-15-01 對應條文（5-10 行即可），並在 §13 references 加路徑。

### Risk 2：5 strategy 的 acceptance criteria 從未明文化
- 嚴重度：HIGH
- 位置：v5.6 §2-§6 / v5.7 §1
- 描述：5 strategy 都有「APR target」「expected DD」「LOC estimate」，但**沒有任何一條業務 acceptance criteria 形如「symbol X 上，funding > 0.01% 且 OI > $Y，則開倉 Z USDT，當 funding < 0.005% 平倉」**。v5.7 §1 income recompute 把 5 strategy 直接列了 APR × capital × calendar weight，但 PA 派發到 E1 寫業務代碼時將無 acceptance 對齊。
- 為何屬「執行性」（非邏輯）：APR / DD 是 outcome metric，不是 entry/exit logic；E1 不能用 outcome 來寫代碼。
- Must-fix 建議：Sprint 1A 派發前，至少 C10（第一個要寫的）必須有一份 acceptance criteria 表（最小 5 條：入場條件 / size formula / 平倉條件 / rebalance 觸發 / 異常退出）。其他 4 strategy 在各自 Sprint 派發前補。

### Risk 3：Earn governance vs C10 spot leg 資金路徑衝突
- 嚴重度：HIGH
- 位置：v5.7 §4 + v5.6 §2 capital structure
- 描述：v5.7 §4 寫 Earn「Auto-redeem trigger: trading margin headroom < 30%」+「Manual rebalance initially (first 3 months); auto after proven」+「Each stake operation = asset write, requires authorization」。但 v5.6 §2 寫 C10 = $2,000 spot+perp delta-neutral；C10 spot leg 需要 USDT 才能買 spot，Earn 也佔 $800 USDT。**業務鏈未定**：(a) C10 啟動時 USDT 是先進 Earn 再被 auto-redeem 回 spot，還是先 deploy 到 C10 後剩餘進 Earn？(b)「manual stake initially」與 Sprint 1B「first small manual stake $200-400」一致，但 v5.7 §4「manual rebalance」與「auto-redeem trigger margin headroom < 30%」內部矛盾（first 3 months 純手動 vs auto-redeem 自動觸發）。
- 為何屬「執行性」（非邏輯）：governance 規則本身合理；矛盾在於 v5.7 §4 自己用了「manual initially」+「auto-redeem trigger」兩個並列規則，PA 派發到 E1 時不知該寫哪個。
- Must-fix 建議：v5.7 §4 改成「first 3 months: 100% manual stake AND manual redeem; auto-redeem disabled; after operator sign-off → auto-redeem trigger enabled」。

## 2. Hours sanity check（業務規格工時 vs estimate）

| Item | v5.7 estimate | FA 評估 | 差異 |
|---|---|---|---|
| Earn API integration | 15 hr | 15-20 hr OK | 一致 |
| Earn governance (Guardian + Decision Lease) | 20 hr | 30-40 hr | **低估**：Decision Lease retrofit 上次 REF-20 Sprint 3 用 Track H 才完整收口（commit dbcf845b），Earn 是新 asset write surface，govflow 需重寫 |
| Earn audit log schema + writer | 10 hr | 10 hr OK | 一致 |
| V103 hypotheses + preregistration schema | — | 10-15 hr | **v5.7 未列**：§3 提到「V103: NEW v5.7 schema」但 hours 在 §9 Sprint 1A 60-80 hr 內未拆分 |
| V104 trading.fills.track | — | 8-12 hr | **v5.7 未列**：跨 V101 與 V104 字段重疊風險（PA dispatch consolidate），hours 不明 |
| Macro counterfactual logger | 25-35 hr | 25-35 hr OK | 一致 |
| On-chain counterfactual logger | 30-40 hr | 30-40 hr OK | 一致 |
| Stage 0R replay preflight 5-strategy 各別實裝 | — | 20-30 hr/strategy | **v5.7 / v5.6 都未列**：AMD-2026-05-15-01 要求每 strategy 有 replay 對齊，這個工時被吞 |

**結論**：Sprint 1A 60-80 hr 偏緊。建議 75-95 hr。

## 3. 未識別的依賴 / 阻塞（業務鏈）

1. **AMD-2026-05-15-01 文件**：v5.7 reference 未列；Stage gate 全靠它；PA dispatch 前必須驗證該文件 active 狀態
2. **Tokenomist 試用 license**：v5.7 §6「Token unlock calendar: NEW (Tokenomist trial integration)」— 試用是 trial，trial 到期後付費 / 替代源未定；Sprint 1A 派發前必須鎖試用期長度（>= 3 個月 / 涵蓋 Sprint 2 alpha tournament）
3. **Bybit options API access**：C13 在 Sprint 4 才啟動，但 Sprint 1A 已要寫 options chain recorder；Bybit options API 需 KYC 等級或子賬戶 — 派發前必須確認 demo + live 雙環境 options API 可用
4. **市場數據隔離**：v5.7 §6 寫 Binance perp WebSocket 是 NEW，但 ADR-0006 amend 寫「Binance market data approved」 — Binance API 對中國 IP 是否可達 / 是否需 VPN / 是否需地理區隔（Tailscale 路由）未在 Sprint 1A 工時內
5. **v5.7 §5 內部矛盾**：Macro Y1 = counterfactual only；但 v5.6 §6 Sprint 3 仍寫「Macro overlay activation for active strategies / C10 + Unlock SHORT receive macro context」 — v5.7 patch 只改了 §5 income counting，沒改 §6 Sprint 3 macro overlay 業務語言，**v5.6 §6 Sprint 3 與 v5.7 §5 直接衝突**
6. **Pairs trading 在 Y1 是否被建**：v5.7 §1 列了 Pairs $40 income，但 Sprint 3+ build 是 evidence-based（v5.6 §6）；如果 Sprint 2 evidence 顯示 Pairs t-stat < 1.5 則不建 — income estimate 與 evidence-gated build 互不對齊
7. **GovernanceHub 既有狀態**：Earn 加進 govflow 需要 hub 額外新 entry；Sprint N+0 closure (2026-05-10) 后 hub 接線狀態未在 v5.7 內 reference
8. **Alpha Tournament 數據準備**：Sprint 1B 列「Alpha Tournament dataset readiness check」，但具體要哪些數據 / 多少回看 / 計算引擎在哪 — Sprint 1B 50-70 hr 內未拆

## 4. 對 PA+FA 匯總的必收 top 3

1. **5 strategy × Stage gate 矩陣**：以 strategy × stage 2D 表，每格寫 acceptance criteria（最小 entry 條件 + exit 條件 + risk envelope）+ 觀察期 + PASS/FAIL 規則。沒這個表，PA 派發等於跨大坑。
2. **資金路徑流圖**：$10,000 → $2,500 off-exchange + $7,500 Bybit；Bybit $7,500 內 $800 Earn / $6,700 strategy；strategy 啟動順序 + Earn auto-redeem 在哪個策略 margin < 30% 觸發 + redeem 後分配規則 — 流程化，非 capital table。
3. **v5.7 → v5.6 殘留矛盾清單**：v5.7 是 patch over v5.6，但 v5.6 §6 Sprint 3 / Sprint 4-7 macro overlay 業務語言未改；需要列「v5.6 哪幾段在 v5.7 後 deprecated / 替換 / 共存」。

## 5. Sprint 1A 派發前 must-fix（業務規格 acceptance criteria）

1. **C10 端到端 acceptance**：5 條最小規格（入場條件 / size formula / 平倉條件 / rebalance 觸發 / 異常退出）— Sprint 1B 寫 C10 minimal viable，但 1B 直到 1A done 才派；1A 派發前必須收口
2. **V103/V104 schema 字段**：v5.7 §3 只列「hypotheses + hypothesis_preregistration tables / trading.fills.track column add」，沒列字段。Sprint 1A 工時 60-80 hr 含 V103/V104 但無 schema = E1 寫不出來
3. **Earn governance flow**：v5.7 §4 「manual initially」與「auto-redeem trigger」內部矛盾收口（Risk 3 must-fix）
4. **Stage 0R replay preflight 抄一份到 v5.7 inline 或 appendix**（Risk 1 must-fix），不能繼續純外掛 AMD-2026-05-15-01
5. **Macro 業務模式統一**：v5.7 §5 counterfactual-only vs v5.6 §6 Sprint 3「Macro overlay activation」收口；如果 Y1 真 counterfactual-only，則 Sprint 3 「Macro overlay activation for active strategies」必須改成「Macro counterfactual logger activation」

## 6. Sprint 1B-3 should-fix

- Sprint 1B：C10 acceptance 必須在派發前 sign-off；Earn first stake $200-400 流程化（不光 amount，含 redeem path）；Alpha Tournament dataset readiness check 列具體驗收項
- Sprint 2：Alpha Tournament 對 5 strategy 各自寫 hypothesis preregistration 條目；t-stat threshold（v5.6 §6 寫 1.5）+ 數據窗口長度 inline
- Sprint 3：Top-1 build 對應 strategy 的 acceptance criteria 在 Sprint 2 evidence 確認後最遲在 Sprint 3 第 1 周完成；Stage 0 shadow Sharpe > 1.0 gate 改成 governance compliant「shadow diagnostic only」（v5.6 §12 明文「NO paper Sharpe gates / Shadow is diagnostic only」，但 v5.6 §6 仍寫「Stage 0 shadow Sharpe > 1.0 → Sprint 4 promotion」，**內部矛盾**）

## 7. 可優化 / 拆分 / 並行

- **Sprint 1A 內並行**：governance amend (ADR-0006/0029/0030) + V103/V104 schema + sensor (liquidation healthcheck + Binance WS + Macro feed) 是 3 條獨立工作鏈，可派 3 個 sub-agent 並行；Earn API recorder（read-only 部分）也可並行
- **拆分**：Sprint 4 160-210 hr「peak engineering week」風險高；C13 Options Stack Phase 1（600 LOC Rust + 250 LOC Python）建議獨立 Sprint 4.5 或 Sprint 5 提前；Top-1 live + Top-2 build 已經佔重
- **可後置**：On-chain counterfactual logger 30-40 hr 在 Sprint 2 派；但 v5.7 §5 寫 Y1「counterfactual only」+ Y1 末「if 真 alpha → Y2 enable」— 如果 Y1 末才看結果，logger 可在 Sprint 2 中後段才上線，不必 Sprint 2 一開始就佔工時
- **複用既有**：v5.7 §6 確認 market.liquidations writer 已 running；同模式可查 funding rate aggregator（v5.7 §6 寫「HEALTHCHECK existing rate logger; add Binance polling」）— Sprint 1A 派 sub-agent grep `rust/openclaw_engine/src/database/` + `panel_aggregator/` 確認還有哪些 sensor 已存在，避免重複建
- **v5.6/v5.7 patch 模式**：建議 v5.8 把 v5.6 § 主體 + v5.7 § patch 合併成單文件，否則 dispatch 時兩文件並讀且需自行 reconcile diff
