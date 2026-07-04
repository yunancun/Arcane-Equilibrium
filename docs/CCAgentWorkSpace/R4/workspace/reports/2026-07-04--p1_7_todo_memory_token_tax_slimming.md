# R4 — P1-7 TODO + memory token 稅瘦身方案(取證/設計 wave)

> 落盤註記:本報告由 conductor 代落盤(R4 無 Bash/Write;內容=R4 structured output report_markdown 原文,wf_8c488f52-f7c)。

日期:2026-07-04 · 角色:R4(唯讀,只出方案不執行) · 執行方:PM(Phase B)
基準:Mac repo `/Users/ncyu/Projects/TradeBot/srv`(多 session 髒樹,未取 SHA——本任務純文檔取證);TODO.md v738(2026-07-02)
方法:TODO.md 全文四段 Read 實測(239 行);PM memory header 全掃(grep -n);體量為字符累加估算 ±20%(無 Bash,無法 wc)

---

## 0. 現況測繪(fact)

### TODO.md(239 行,非空 224,132KB ≈ 59k tokens @2.24 chars/token)

| 節 | 行範圍 | 行數 | 估算體量 | 性質 |
|---|---|---|---|---|
| masthead | L1-8 | 8 | ≈3.7KB | L4/L5 為 v738 版本增量敘事(違 todo-maintenance「header 不放 vN 敘事」) |
| §0 Current Facts | L10-49 | 36 事實行 | ≈39KB | 多數為 v684-v738 演進殘骸,17 行 superseded/historical |
| §1 Active Queue | L51-87 | override 段+30 行 | ≈37KB | **16 行 DONE_WITH_CONCERNS=主要肥肉**;L82 單行 ≈6.8KB(v700-v709 九代 packet 墓場) |
| §2 No-Repeat Markers | L88-152 | 60 行 | ≈39KB | 兩大家族(P0-LEARN-* 8 行、P1-RUNTIME-HEALTH-HYGIENE-* 32 行)可各併一行 |
| §3 Hard Gates | L153-163 | 7 行 | ≈1.3KB | 權威濃度最高,全留 |
| §4 Handoff | L165-235 | 55 條 /tmp 路徑 sha-dump | ≈4.5KB | D3 裁決後雙重過期(/tmp volatile+SSOT 遷移) |
| 尾段 | L237-238 | 2 行 | ≈3.6KB | L238 自檢段 3.3KB,與 masthead 重複 |

**截斷風險(HIGH/confidence 高)**:59k tokens 超 25k Read cap,單次預設 Read 約在 §1 中段(~L64-70)截斷——§1 尾部 6 個 BLOCKED 行、§2 全部 no-repeat 禁令、**§3 Hard Gates** 對單次讀取不可見。這不只是 token 稅,是治理禁令靜默失效面。

### PM memory(`docs/CCAgentWorkSpace/PM/memory.md`,總行 ≈4353,非空 3051,~650 條目)

注意:**不是** `.claude/agents/PM.md`(僅 101 非空行,合規)。

| 區塊 | 行範圍 | 內容 |
|---|---|---|
| 檔頭+壓實規則 blockquote | L1-3 | 已有規則(300 行線/archive append-only/檔尾追加) |
| 長期教訓 | L5-25 | 18 條蒸餾(2026-06-10 壓實產物),合規 |
| 近期記錄·頭部倒序區 | L28-1997 | 07-01→06-18 倒序,~380 條 |
| **檔尾追加區(結構缺陷)** | L1998-4353 | 05-15→**07-02** 升序,~270 條 |

**雙累積區缺陷(HIGH/confidence 高)**:最新 07-02 條目在 L4256-4347(14 條),超出預設 2000 行 Read 窗口——PM 讀自己 memory 會誤認頭部 07-01 為最新,漏讀自己最新完成序列條目。壓實同時必須根修此結構。

`memory-archive.md` 現 2141 非空行,append-only 正常,無需處理。

### 其他體量普查(非空行)

- `.claude/agents/*.md` 18 檔:47~101 行,**無 >1000 行者**。
- workspace memory 超 300 行規格線(doc-cross-reference 壓實規格):**PM 3051、E4 699(BASELINE 特例)、E1 660、E2 364、MIT 321**。其餘 13 檔合規。

---

## 1. TODO.md 瘦身方案

### 1.1 目標檔名與守恆

- **歸檔快照**:`docs/archive/2026-07-04--todo_v738_pre_slim_archive.md` = 現行 TODO.md 全文原樣拷貝(cp 即可,守恆最簡;沿用 v110 快照慣例),檔頭加 3 行說明。
- masthead v738 敘事全文 → `docs/CLAUDE_CHANGELOG.md`「TODO Version-Increment Log」(L8 節已存在)。
- 索引補新 archive 檔(按 docs/README.md 規則入 `_indexes/document_index.md`)。
- 驗收:快照 wc -l = 239;`wc -c TODO.md ≤ 45000`(≈20k tokens 留 buffer;硬線 56000≈25k)。

### 1.2 masthead / 尾段

| 行 | 處置 |
|---|---|
| L3 | 留,版號按落地時 CHANGELOG 序遞增 |
| L4(1.4KB) | 壓 ≤2 行:HEAD 指針+runtime 指針;敘事移 CHANGELOG |
| L5(1KB) | 壓 ≤2 行:候選 grid_trading\|ETHUSDT\|Buy+auth expired+next dispatch=`P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD` |
| L6 | 留 docs 鏈接,刪 3 條 /tmp 檔案級鏈接 |
| L237 | 留 |
| L238(3.3KB) | 壓 ≤4 行(next dispatch id+v738 ROTATED 一句+核心禁令一句) |

### 1.3 §0 逐行處置表(L14-49,36 行)

留(輕壓):L14,15,36,46,47。
壓縮保留(≤3 句):L16(併 L39:expired auth sha 8c891b4e+expiry+canonical plan sha 30056993+勿食本地 stale AVAX)、L32(connector demo mode 四事實)、L42(GUI percent 語義+TOML 三值,equity 數字標 stale)、L43(3.4KB→2 行:結論+commit 區間 00680f2b..451be917+archive 指針)。
壓成一行+鏈接:L17,L19,L22,L25,L26,L31,L35,L37(標 STALE+指向 §1-L57 為權威),L38(標 STALE)。
整行移 archive:L18,L20,L21,L23,L24,L27,L28,L29,L30,L33,L34,L39,L40,L41,L44,L45,L48,L49(共 18 行,其中 L39-41/44/45/49 與 §2 既有 marker 重複零損失)。

### 1.4 §1 逐行處置表(L53-86)

機械規則:**Status=DONE_WITH_CONCERNS 一律移出 §1**;ACTIVE/BLOCKED/WAITING/DEFERRED 留。
- L53 override 段:留但壓 ~50%。
- 留原樣:L57-61(cold audit 5 行)、L85、L86。
- 留+壓 evidence 欄 ≤400 字:L64(**next action 欄一字不動**,含 post_approval_drift_policy 程序正本)、L69、L73、L84;L80 evidence 壓 2 句+archive 指針;L82(6.8KB)evidence 壓 ≤3 句、next action 欄保留。
- 移出:L62 整行移 archive(§2-L92 同 ID 已存);L63,65,66,67,68,71,72,74,75,76,77,78,79,81,83 共 15 行各壓一行 marker(ID+status+報告鏈+一句 reopen 條件)移入 §2。
- 驗收:§1 僅剩 ACTIVE/BLOCKED/WAITING/DEFERRED 共 13 行。

### 1.5 §2 家族合併(L92-151,60 行)

- L92-99 P0-LEARN-*(8 行)→ 1 家族行:commits `ed8c3595/f1d1a26c/1a8cedb3/ed54bf93/300ee0af/7cfec46e/6b93cf2a/f2a827c2`+共同 reopen 規則+報告 `…/2026-06-29--learning_*.md`。
- L100-131 P1-RUNTIME-HEALTH-HYGIENE-*(32 行)→ 1 家族行(共同 reopen 規則=candidate/GUI RiskConfig/equity/Guardian/standing envelope/order shape 變更;註明 3 行 BLOCKED_BY_LOSS_CONTROL 快照)。
- L132/133/135 → 1 家族行(P0-GUI-RISK-CAP-RESOLVER-*)。
- L136-143 → 1 家族行(P0-STANDING-DEMO-*+P0-ALIGNED-ETH-*)。
- L144-151 獨立 8 行留、各壓 ≈40%;+自 §1 移入 ~16 個一行 marker。

### 1.6 §3 / §4

- §3 全留不動。
- §4:55 條 /tmp sha-dump → 8 條核心命令+一行「D3 落地後 /tmp/openclaw 統一改 `~/BybitOpenClaw/var/openclaw`,本節需同步更新」。

### 1.7 瘦身後預算

masthead 0.9 + §0 5.2 + §1 10.4 + §2 6.1 + §3 1.3 + §4 2.0 ≈ **26KB ≈ 11-12k tokens**。

---

## 2. PM memory 節級處置表

| 區塊 | 行範圍 | 處置 |
|---|---|---|
| 檔頭+規則 blockquote | L1-3 | 留;blockquote 改「新條目統一倒序插入近期記錄標題後,禁雙累積區」 |
| 長期教訓 18 條 | L5-25 | 留;可選補 ≤3 條蒸餾,總數 ≤30 行 |
| 頭部區最新 19 條(07-01) | L28-124 | 留 |
| 中段+檔尾舊段 | **L125-4255** | 機械切分 append 至 memory-archive.md,分隔行「--- 2026-07-04 P1-7 壓實遷入(原 memory.md L125-L4255)」 |
| 檔尾 07-02 最新 14 條 | L4256-4353 | 留,**移回近期記錄節內倒序歸位**(根修雙區) |

結果:新 memory.md ≈221 行 <300。驗收:wc -l 守恆(舊 memory+舊 archive=新 memory+新 archive−分隔行)。

## 3. 其他超標 memory

`.claude/agents/` 無 >1000 行檔。另批派工:E4 699(先 grep BASELINE 永留)、E1 660、E2 364、MIT 321。

## 4. Findings 總表

| 維度 | 問題 | 位置 | 修法/severity |
|---|---|---|---|
| token 稅+截斷 | 59k tokens 超 25k cap,§1尾/§2/§3 單次讀不可見 | TODO.md | 本方案(HIGH) |
| header 越界 | v738 敘事佔 masthead 2.5KB | L4-5 | 移 CHANGELOG(MEDIUM) |
| 重複雙寫 | §0-L39 vs L16;§0 六行 vs §2 同 ID;§1-L62 vs §2-L92 | 見處置表 | 去重(MEDIUM) |
| G6-04 stale | §0-L37/L38 runtime 事實被 07-03 冷審計推翻 | L37-38 | 標 STALE+指向 §1-L57(HIGH) |
| 過期指令 | §4 55 條 /tmp 路徑,D3 後失效 | L165-235 | 壓 8 條+D3 指針(MEDIUM) |
| memory 結構 | PM memory 雙累積區,07-02 條目超出 2000 行 Read 窗 | PM/memory.md | 壓實+單區化(HIGH) |
| memory 超標 | E4 699/E1 660/E2 364/MIT 321 | workspace memory | 另批(LOW-MED) |

**假陽性候選/裁量註記**:①§0-L22/L31 判「壓一行」非 archive(canonical plan sha 30056993 與 v702 input 仍被 §1-L82/L84 引用);②§1-L75 status=BLOCKED 但自述 closed,按語義移出;③PM memory 兩區邊界 L124/L125、L4255/L4256 已驗為 header 行,跨區時戳重疊未逐條驗。

## 5. 執行順序(Phase B)

1. re-fetch+確認無並行 TODO 寫入 → 2. cp 快照+CHANGELOG → 3. 重寫 TODO.md+驗收 → 4. PM memory 機械切分+守恆驗收 → 5. 索引+`git commit --only`+[skip ci] → 6. R4/memory.md 檔尾追加(conductor 代寫)。
